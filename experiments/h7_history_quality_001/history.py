"""Common-likelihood H7/direct audit with regeneration from the physical origin.

No particle solver, raw stream retention, posterior feedback, or coverage claim.
Run from the repository root: python3 -B -m experiments.h7_history_quality_001.history.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

import numpy as np
from experiments.foster_campaign_001.backend import ROOT, identity, prepare_c
from experiments.foster_campaign_001.compact import StimulusStream
from experiments.foster_campaign_001.h7_backend import H7Backend
from experiments.foster_campaign_001.h7_backend import DEPENDENCIES
from experiments.foster_campaign_001.run import parser as campaign_parser
from experiments.foster_campaign_001.stimulus import cells
from experiments.foster_feedback_001.estimator import Model
from experiments.hysteresis_refinement_001.field import Compressed, transported
from experiments.slow_likelihood_diagnostic_001.numerics import Exact, solve


def write(path, value):
    def native(x):
        if isinstance(x, np.ndarray):return x.tolist()
        if isinstance(x, np.generic):return x.item()
        raise TypeError(type(x).__name__)
    path.write_text(json.dumps(value, indent=2, allow_nan=False, default=native)+'\n')


def source_receipt():
    names=set(DEPENDENCIES)
    for module in list(sys.modules.values()):
        path=getattr(module,'__file__',None)
        if path:
            path=Path(path).resolve()
            if path.suffix=='.py' and path.is_relative_to(ROOT):names.add(str(path.relative_to(ROOT)))
    return dict(revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                python=sys.version,numpy=np.__version__,sources={name:identity(ROOT/name) for name in sorted(names)})


def verify_sources(receipt):
    for name,expected in receipt['sources'].items():
        if identity(ROOT/name)!=expected:raise ValueError('source changed during experiment: '+name)


class ReplayIntegrityError(RuntimeError):pass


class ReplayRows:
    """Exact's slice interface, using a fresh deterministic source each full pass."""
    def __init__(self, factory, count, expected_sha256):
        self.factory,self.count,self.expected=factory,count,expected_sha256
        self.stream=None;self.hash=None;self.verified_passes=0

    def __len__(self):return self.count

    def __getitem__(self, key):
        if not isinstance(key,slice) or key.step not in (None,1):raise ReplayIntegrityError('ordered slices only')
        first,stop=key.start,min(key.stop,self.count)
        if first==0:
            self.stream=self.factory();self.hash=hashlib.sha256()
        if self.stream is None or first!=self.stream.index:raise ReplayIntegrityError('replay chronology')
        rows,_,_=self.stream.read(stop-first)
        if self.stream.failure or len(rows)!=stop-first:raise ReplayIntegrityError('incomplete reference stream')
        self.hash.update(rows.astype('<f8',copy=False).tobytes())
        if stop==self.count:
            if self.hash.hexdigest()!=self.expected:raise ReplayIntegrityError('regenerated observations changed')
            self.verified_passes+=1
        return rows


def field_snapshot(bank):
    field=copy.copy(bank.field)
    if bank.buffered:field.update(field.count,bank.pending_rows[:bank.buffered])
    if field.count!=bank.live_count or not np.array_equal(field.state,bank.live_state):
        raise ValueError('audit snapshot transport mismatch')
    return field


def audit(bank,model,factory,digest,refit=False,probe_radius=1.):
    field=field_snapshot(bank);compressed=Compressed(field,bank.mean,bank.prior_root)
    fit=solve(compressed,start=bank.w)
    w=fit['w'];rows=ReplayRows(factory,bank.live_count,digest)
    exact=Exact(model,rows,bank.mean,bank.prior_root)
    c,g,P,end,F=exact(w);fc,fg,fP,_,_=compressed(w)
    C=np.linalg.cholesky(P);standard=np.linalg.solve(C.T,np.eye(16))
    root=bank.prior_root@standard
    native,D=transported(field,fit['x'])
    delta_g=fg-g
    shift=-np.linalg.solve(P,delta_g)
    whitened=np.linalg.solve(C,np.linalg.solve(C,fP).T).T
    eig=np.linalg.eigvalsh((whitened+whitened.T)/2)
    query_rows={'SOC':F[0]@bank.prior_root,'logQ':bank.prior_root[5]}
    metrics={}
    directions=[]
    for name,j in query_rows.items():
        sd=float(np.linalg.norm(j@standard))
        metrics[name]=dict(reference_local_sd=sd,
            compression_predicted_shift_SD=float(j@shift/sd),
            field_to_direct_sd_ratio=float(np.linalg.norm(np.linalg.solve(np.linalg.cholesky(fP),j))/sd))
        directions.append((name,np.linalg.solve(P,j)/sd))
    # The weakest prior-whitened direction is selected from likelihood geometry,
    # not plant truth. These are probes, not a uniform support enclosure.
    _,V=np.linalg.eigh(P);directions.append(('weak',V[:,0]/math.sqrt(V[:,0]@P@V[:,0])))
    probes=[dict(name='anchor',offset=0.,delta_nll=float(fc-c))]
    for name,direction in directions:
        for sign in (-1,1):
            trial=w+sign*probe_radius*direction
            try:
                # Check representation/physical support before expensive replay.
                fvalue=compressed(trial)[0];value=exact(trial)[0]
                probes.append(dict(name=name,offset=sign*probe_radius,delta_nll=float(fvalue-value)))
            except (ValueError,OverflowError) as error:
                probes.append(dict(name=name,offset=sign*probe_radius,status='unsupported',reason=str(error)))
    values=[p['delta_nll'] for p in probes if 'delta_nll' in p]
    answer=dict(records=bank.live_count,hours=bank.live_count/factory().rate/3600,
        observation_sha256=digest,field_fit=fit['diagnostic'],
        compression_gradient_dual_norm=float(np.linalg.norm(np.linalg.solve(C,delta_g))),
        direct_gradient_dual_norm=float(np.linalg.norm(np.linalg.solve(C,g))),
        precision_relative_eigenvalues=eig,queries=metrics,
        sampled_nll_error_oscillation=float(max(values)-min(values)),probes=probes,
        anchor_costs=dict(direct=c,compressed=fc,max_cost_ulp=float(max(abs(np.spacing(c)),abs(np.spacing(fc))))),
        transport_chart_difference=native-end,
        transport_SOC_difference_pp=float(100*(native[0]-end[0])),
        transport_h_difference=float(np.tanh(native[4])-np.tanh(end[4])),
        transport_SOC_SD_ratio=float(np.linalg.norm(D[0]@root)/np.linalg.norm(F[0]@root)),
        streaming_vs_full_field_origin_chart=bank.mean+bank.prior_root@bank.w-fit['x'],
        verified_direct_replays=rows.verified_passes,
        field_storage=field.storage(),
        scope='Same Gaussian residual likelihood/prior. Direct means uncompressed double evaluation, not exact real arithmetic. Probe oscillation is not a uniform bound; GN precision is local, not validated coverage.')
    if refit:
        direct_fit=solve(exact,start=w,max_rounds=30)
        answer['direct_refit']=direct_fit['diagnostic']
        answer['direct_refit_minus_field_chart']=direct_fit['x']-fit['x']
        answer['verified_direct_replays']=rows.verified_passes
    return answer


def run_case(directory,campaign,config,case,prefixes,rate,refresh,refit):
    directory.mkdir();settings=vars(campaign_parser().parse_args([]))
    settings.update(sample_rate_hz=rate,current_a=.06,temperature='fixed',
                    temperature_mean_c=25.,field_refresh_seconds=refresh)
    definition=cells()[case['cell']]
    factory=lambda:StimulusStream(config,definition,case,settings)
    recipe=dict(case=case,settings=settings,cell=definition,prefixes=prefixes)
    source=hashlib.sha256(json.dumps(recipe,sort_keys=True).encode()).hexdigest()
    bank=H7Backend(campaign,config,source,'history-quality-v1',rate,SimpleNamespace(**settings))
    model=Model(prepare_c(campaign,rate,config)[0],config)
    stream=factory();digest=hashlib.sha256();audits=[];started=time.perf_counter()
    result=dict(status='running',recipe=recipe,source_id=source,audits=audits,
                source_revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip())
    write(directory/'result.json',result)
    targets=sorted({max(16,math.ceil(s*rate/16)*16) for s in prefixes})
    for target in targets:
        while stream.index<target:
            first=stream.index;rows,truth,_=stream.read(min(4096,target-first))
            if stream.failure or not len(rows):raise ValueError('plant domain '+str(stream.failure))
            for offset in range(0,len(rows),16):
                block=rows[offset:offset+16];digest.update(block.astype('<f8',copy=False).tobytes())
                try:bank.advance(first+offset,block)
                except Exception:
                    result['failed_backend']=dict(counts=bank.counts(),input_first=first+offset,
                        supplied_prefix=first+offset+len(block),supplied_observation_sha256=digest.hexdigest(),
                        last_diagnostic_message=bank.last_message())
                    write(directory/'result.json',result)
                    raise
        answer=audit(bank,model,factory,digest.hexdigest(),refit=refit)
        # Truth is scored only here, after the inference diagnostic has returned.
        point=bank.last_message()
        answer['scoring_only']=dict(SOC_error_pp=float(100*(point[0]-truth[-1,0])),
            Q_error_percent=float(100*(math.exp(point[5])/definition['parameters']['Q_Ah']-1)))
        audits.append(answer);result['wall_s']=time.perf_counter()-started
        write(directory/'result.json',result)
        print(json.dumps(dict(case=directory.name,records=target,hours=answer['hours'],
            gradient_defect=answer['compression_gradient_dual_norm'],wall_s=result['wall_s'])),flush=True)
    result.update(status='completed',backend_counts=bank.counts());write(directory/'result.json',result)
    return result


def plot(out,results):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,2,figsize=(11,8),layout='constrained')
    for result in results:
        if not result.get('audits'):continue
        case=result['recipe']['case'];label=f"{case['load']} / {case['noise_v']*1000:g} mV"
        a=result['audits'];x=[r['hours'] for r in a]
        ys=[[r['sampled_nll_error_oscillation'] for r in a],
            [r['compression_gradient_dual_norm'] for r in a],
            [abs(r['queries']['logQ']['compression_predicted_shift_SD']) for r in a],
            [abs(r['queries']['SOC']['compression_predicted_shift_SD']) for r in a]]
        for ax,y in zip(axes.flat,ys):ax.plot(x,y,'o-',label=label)
    titles=['Sampled NLL shape error (not a bound)','Joint gradient defect in local precision metric',
            'Predicted logQ shift / direct local SD','Predicted SOC shift / direct local SD']
    for ax,title in zip(axes.flat,titles):
        ax.set_title(title);ax.set_xlabel('Simulated hours');ax.set_xscale('log');ax.set_yscale('symlog',linthresh=1e-8);ax.grid(True,alpha=.3)
    axes[0,0].legend(fontsize=8);fig.savefig(out/'history_errors.png',dpi=150);plt.close(fig)


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--prefix-seconds',nargs='+',type=float,default=[60,600,3600])
    p.add_argument('--loads',nargs='+',choices=['rest','pulses','multiscale','embedded'],default=['rest','multiscale','embedded'])
    p.add_argument('--noise-v',nargs='+',type=float,default=[.0002,.002]);p.add_argument('--cell',choices=['A','B'],default='B')
    p.add_argument('--seed',type=int,default=1103);p.add_argument('--load-seed',type=int,default=7)
    p.add_argument('--sample-rate-hz',type=int,default=35);p.add_argument('--refresh-seconds',type=float,default=60)
    p.add_argument('--refit',action='store_true');args=p.parse_args()
    if not all(math.isfinite(x) and x>0 for x in args.prefix_seconds+[args.refresh_seconds]):p.error('positive finite durations required')
    if not all(math.isfinite(x) and x>=0 for x in args.noise_v):p.error('finite nonnegative noise required')
    if args.sample_rate_hz<1:p.error('positive rate required')
    args.out.mkdir(parents=True,exist_ok=False)
    config=json.loads((ROOT/'experiments/foster_feedback_001/calibration.json').read_text());config['hysteresis_chart']='bounded'
    sources=source_receipt()
    write(args.out/'registration.json',dict(arguments={**vars(args),'out':str(args.out)},source=sources,
        calibration=config,selection='Fixed CLI scenario/prefix manifest before data; same prior, likelihood, source prefix and coordinate anchor.',
        bounds='Empirical diagnostic only; no uniform likelihood bound or physical coverage claim.'))
    results=[]
    for load in args.loads:
        for noise in args.noise_v:
            case=dict(cell=args.cell,load=load,noise_v=noise,seed=args.seed,load_seed=args.load_seed)
            directory=args.out/f'case_{len(results):04d}'
            try:result=run_case(directory,args.out,config,case,args.prefix_seconds,args.sample_rate_hz,args.refresh_seconds,args.refit)
            except Exception as error:
                result=json.loads((directory/'result.json').read_text()) if (directory/'result.json').exists() else dict(recipe=dict(case=case),audits=[])
                result.update(status='unresolved',error=dict(type=type(error).__name__,reason=str(error)));write(directory/'result.json',result)
            results.append(result)
            write(args.out/'summary.json',dict(status='running',cases=results,requested_cases=len(args.loads)*len(args.noise_v)))
    try:
        verify_sources(sources);plot(args.out,results)
    except Exception as error:
        write(args.out/'summary.json',dict(status='unresolved',cases=results,finalization_error=str(error)));return 1
    write(args.out/'summary.json',dict(status='completed' if all(r['status']=='completed' for r in results) else 'unresolved',
        cases=results,source_verified=True,build_receipts={str(p.relative_to(args.out)):identity(p) for p in args.out.glob('backend_*/build.json')}))
    return 0 if all(r['status']=='completed' for r in results) else 1


if __name__=='__main__':raise SystemExit(main())
