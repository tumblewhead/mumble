"""Paired replay with return-code-only instrumentation of the H7 domain checks."""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import numpy as np
from experiments.foster_campaign_001.backend import ROOT, identity, prepare_c
from experiments.foster_campaign_001.h7_backend import H7Backend
from experiments.field_tangent_native_001.native import Native, build, ptr
from experiments.foster_campaign_001.compact import StimulusStream
from experiments.foster_campaign_001.stimulus import cells
from experiments.foster_campaign_001.run import parser
from experiments.foster_feedback_001.estimator import Model
from experiments.h7_history_quality_001.history import write, source_receipt, verify_sources, ReplayRows
from experiments.hysteresis_refinement_001.field import transported
from experiments.slow_likelihood_diagnostic_001.numerics import solve

LABELS = {-301: 'computational_shape_box', -302: 'SOC_path_support', -303: 'hysteresis_endpoint_chart'}


def instrument(directory):
    binary = build(directory, hdegree=7)
    path = directory/'kernel.c'; original = path.read_text()
    replacements = {
        'if(!isfinite(t)||fabs(t)>1+1e-12)return -3;': 'if(!isfinite(t)||fabs(t)>1+1e-12)return -301;',
        'if(w->x[0]-q*state[FT_STATE-1]<0||w->x[0]-q*state[FT_STATE-2]>1)return -3;':
            'if(w->x[0]-q*state[FT_STATE-1]<0||w->x[0]-q*state[FT_STATE-2]>1)return -302;',
        'if(!(h>-1&&h<1))return -3;': 'if(!(h>-1&&h<1))return -303;'}
    modified = original
    for before, after in replacements.items():
        if modified.count(before) != 1: raise ValueError('diagnostic patch source mismatch')
        modified = modified.replace(before, after)
    path.write_text(modified)
    command = ['cc','-DFT_HDEG=7','-std=c11','-O2','-fno-fast-math','-ffp-contract=off',
               '-Wall','-Wextra','-Werror','-pedantic','-fPIC','-shared',str(path),
               str(directory/'response.c'),'-lm','-o',str(binary)]
    subprocess.run(command,check=True)
    write(directory/'diagnostic_build.json',dict(command=command,binary=identity(binary),
        original_kernel_sha256=hashlib.sha256(original.encode()).hexdigest(),
        sources={p.name:identity(p) for p in (path,directory/'kernel.h',directory/'response.c')},
        replacements=replacements))
    return binary


class DiagnosticBackend(H7Backend):
    def _make_native(self,campaign):
        return Native(instrument(campaign/'diagnostic_native'),self.field,self.mean,self.prior_root)


def rejected_query(bank):
    n = bank.native; f = bank.field; out = np.full(307,np.nan)
    status = n.lib.ft_query(n.context,n.work,n.count,ptr(n.mean),ptr(n.L),
        ptr(f.center),ptr(f.halfwidth),ptr(bank.live_state),ptr(f.p1),ptr(f.p2),ptr(out))
    if status not in LABELS: raise ValueError('unexpected diagnostic query status '+str(status))
    # Query always writes this candidate before the three domain predicates.
    w = out[:16].copy(); x = n.mean.copy()
    for i in range(16):
        for j in range(16): x[i] += n.L[i,j]*w[j]
    from experiments.foster_uncertainty_audit_001.conditional_packet import partition
    a,s = partition(x)
    answer = dict(status=status,predicate=LABELS[status],candidate_w=w,candidate_chart=x,
                  shape=s,normalized_log_shape=np.log(s/f.center)/f.halfwidth,
                  origin_h=float(np.tanh(x[4])),SOC_path_min=float(a[0]-a[4]*bank.live_state[-1]),
                  SOC_path_max=float(a[0]-a[4]*bank.live_state[-2]))
    # This diagnostic computation does not alter the accumulator.
    field = f; saved = field.state
    try:
        field.state = bank.live_state
        outgoing = field.outgoing(x)
        answer['field_outgoing_amplitude'] = outgoing
        answer['field_endpoint_h'] = float(outgoing[10]/outgoing[9])
    except ValueError as error: answer['field_query_error'] = str(error)
    finally: field.state = saved
    return answer


def run(out,limit=35520):
    out.mkdir(parents=True,exist_ok=False)
    config=json.loads((ROOT/'experiments/foster_feedback_001/calibration.json').read_text());config['hysteresis_chart']='bounded'
    settings=vars(parser().parse_args([]));settings.update(sample_rate_hz=35,current_a=.06,
        temperature='fixed',temperature_mean_c=25.,field_refresh_seconds=60)
    case=dict(cell='B',load='embedded',noise_v=.0002,seed=1103,load_seed=7)
    recipe=dict(case=case,settings=settings,cell=cells()['B'])
    source=hashlib.sha256(json.dumps(recipe,sort_keys=True).encode()).hexdigest()
    sources=source_receipt();write(out/'registration.json',dict(recipe=recipe,limit=limit,source=sources,
        method='Paired identical input; diagnostic changes only three return codes. No production source edits.'))
    base=H7Backend(out,config,source,'architecture-domain-v1',35,SimpleNamespace(**settings))
    diag=DiagnosticBackend(out,config,source,'architecture-domain-v1',35,SimpleNamespace(**settings))
    factory=lambda:StimulusStream(config,cells()['B'],case,settings)
    stream=factory();digest=hashlib.sha256();parity=0;errors=[]
    while stream.index<limit:
        first=stream.index;rows,_,_=stream.read(min(16,limit-first))
        if stream.failure or not len(rows):raise ValueError('fixture stopped')
        digest.update(rows.astype('<f8',copy=False).tobytes());errors=[]
        for bank in (base,diag):
            try: bank.advance(first,rows);errors.append(None)
            except ValueError as error:errors.append(str(error))
        # Both committed contexts and response states must agree even on failure.
        if not np.array_equal(base.native.snapshot(),diag.native.snapshot()):raise AssertionError('native context parity')
        if not np.array_equal(base.live_state,diag.live_state):raise AssertionError('response state parity')
        if not np.array_equal(base.last_message(),diag.last_message()):raise AssertionError('publication parity')
        if errors[0] is None and errors[1] is None:parity=stream.index
        else:
            if (errors[0] is None)!=(errors[1] is None):raise AssertionError('failure parity')
            break
    result=dict(status='failure_reproduced' if any(errors) else 'no_failure_in_prefix',
        records=stream.index,last_successful_parity_prefix=parity,observation_sha256=digest.hexdigest(),
        errors=errors,base_counts=base.counts(),diagnostic_counts=diag.counts(),
        context_response_publication_parity=True)
    if any(errors):
        rejection=rejected_query(diag);result['rejection']=rejection
        model=Model(prepare_c(out,35,config)[0],config)
        replay=ReplayRows(factory,stream.index,digest.hexdigest());state=rejection['candidate_chart'].copy()
        try:
            for first in range(0,len(replay),4096):
                _,_,state,_=model.evaluate(state,replay[first:first+4096])
            result['direct_candidate_transport']=dict(status='supported',endpoint_chart=state,
                endpoint_h=float(np.tanh(state[4])),verified_passes=replay.verified_passes)
        except ValueError as error:result['direct_candidate_transport']=dict(status='unsupported',reason=str(error))
        # Explicit outcome-selected solver control; not a repair or new readout.
        fit=solve(diag.objective,start=diag.w,max_rounds=240)
        result['longer_field_solve']=dict(diagnostic=fit['diagnostic'],candidate_chart=fit['x'])
        try:
            end,_=transported(diag.field,fit['x'])
            result['longer_field_solve']['endpoint_chart']=end
            result['longer_field_solve']['transport']='supported'
        except ValueError as error:result['longer_field_solve']['transport']=str(error)
    verify_sources(sources);write(out/'result.json',result)
    print(json.dumps(dict(status=result['status'],records=stream.index,
        predicate=result.get('rejection',{}).get('predicate'))),flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();run(args.out)
