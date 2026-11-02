"""Matched exact-reuse qualification; generated binaries/results remain local."""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import time
from types import SimpleNamespace
import numpy as np
from .build import build, ReuseBackend
from .contracts import load,validate
from .test_reuse import observations
from experiments.foster_campaign_001.backend import ROOT,identity
from experiments.foster_campaign_001.coordinates import prior
from experiments.foster_campaign_001.h7_backend import H7Backend
from experiments.foster_campaign_001.compact import StimulusStream
from experiments.foster_campaign_001.run import parser
from experiments.foster_campaign_001.stimulus import cells
from experiments.foster_uncertainty_audit_001.conditional_packet import partition
from experiments.hysteresis_refinement_001.field import MixedField
from experiments.field_tangent_native_001.native import ptr
from experiments.h7_history_quality_001.history import write,source_receipt,verify_sources


def response_control(out,config):
    out.mkdir();mean,_=prior(config);center=partition(mean)[1]
    paths=[build(out/name,candidate=c)[0] for name,c in [('base',False),('candidate',True)]]
    fields=[MixedField(config,center,1.,7,p,'response') for p in paths]
    rows=observations(4096);states=[f.state.copy() for f in fields]
    buffers=[np.empty((len(rows),112)) for _ in fields]
    def call(i,obs=rows):
        f=fields[i]
        status=f.fn(ptr(obs),len(obs),ptr(f.cal),6,8,36,ptr(f.rates),ptr(f.p1),ptr(f.p2),ptr(states[i]),ptr(buffers[i]))
        if status:raise ValueError('response status '+str(status))
    for i in range(2):call(i)
    if states[0].tobytes()!=states[1].tobytes() or buffers[0].tobytes()!=buffers[1].tobytes():
        raise AssertionError('response bitwise parity')
    # Repeated timing never changes the initial state or input sequence.
    timings=[[],[]]
    for repetition in range(9):
        for i in ((0,1) if repetition%2==0 else (1,0)):
            states[i][:]=fields[i].state
            start=time.process_time_ns();call(i);elapsed=time.process_time_ns()-start
            timings[i].append(elapsed)
    counter_results=[]
    for candidate in (False,True):
        binary=build(out/('candidate_count' if candidate else 'base_count'),candidate=candidate,counters=True)[0]
        f=MixedField(config,center,1.,7,binary,'count');lib=C.CDLL(str(binary))
        lib.ar_exp_count.restype=lib.ar_expm1_count.restype=C.c_uint64
        for current in (0.,.04,-.04):
            lib.ar_reset();f.rows(f.count,np.array([[1/35,current,25.,3.7,.002]]))
            actual=(lib.ar_exp_count(),lib.ar_expm1_count())
            expected=(29,18) if current==0 else (37,26) if candidate else (93,82)
            if actual!=expected:raise AssertionError('call count')
            counter_results.append(dict(candidate=candidate,current=current,exp=actual[0],expm1=actual[1]))
    result=dict(records=len(rows),input_sha256=hashlib.sha256(rows.tobytes()).hexdigest(),bitwise_parity=True,
        response_CPU_ns=timings,median_base_ns=float(np.median(timings[0])),median_candidate_ns=float(np.median(timings[1])),
        median_speedup=float(np.median(timings[0])/np.median(timings[1])),instrumented_call_counts=counter_results,
        timing_scope='Nine alternating host process-CPU trials, state reset outside timing; no call counters in timed libraries.',
        state_bytes=fields[0].state.nbytes,added_persistent_bytes=0,local_table_payload_bytes=128)
    write(out/'result.json',result);return result


def backend_control(out,config,load,records,thermal):
    out.mkdir();settings=vars(parser().parse_args([]));settings.update(sample_rate_hz=35,current_a=.06,
        temperature='fixed',temperature_mean_c=thermal,field_refresh_seconds=60)
    case=dict(cell='B',load=load,noise_v=.0002,seed=1103,load_seed=7)
    recipe=dict(case=case,settings=settings,cell=cells()['B'])
    source=hashlib.sha256(json.dumps(recipe,sort_keys=True).encode()).hexdigest()
    banks=[H7Backend(out,config,source,'reuse',35,SimpleNamespace(**settings)),
           ReuseBackend(out,config,source,'reuse',35,SimpleNamespace(**settings))]
    stream=StimulusStream(config,cells()['B'],case,settings);digest=hashlib.sha256()
    timings=[[],[]];errors=[None,None];boundaries=0
    while stream.index<records:
        first=stream.index;rows,_,_=stream.read(min(16,records-first))
        if stream.failure or not len(rows):raise ValueError('stimulus stopped')
        digest.update(rows.astype('<f8',copy=False).tobytes())
        for i in ((0,1) if boundaries%2==0 else (1,0)):
            start=time.process_time_ns()
            try:banks[i].advance(first,rows)
            except ValueError as error:errors[i]=str(error)
            timings[i].append(time.process_time_ns()-start)
        a,b=banks
        for x,y in ((a.native.snapshot(),b.native.snapshot()),(a.live_state,b.live_state),
                    (a.field.root,b.field.root),(a.field.state,b.field.state),(a.last_message(),b.last_message()),
                    (a.pending_rows[:a.buffered],b.pending_rows[:b.buffered])):
            if x.tobytes()!=y.tobytes():raise AssertionError('backend bitwise mismatch at '+str(first))
        if a.counts()!=b.counts() or errors[0]!=errors[1]:raise AssertionError('backend status/ownership mismatch')
        if a.noise!=b.noise or a.field.noise!=b.field.noise:raise AssertionError('noise normalizer mismatch')
        boundaries+=1
        if errors[0]:break
    result=dict(status='matched_failure' if errors[0] else 'completed',recipe=recipe,records=stream.index,
        observation_sha256=digest.hexdigest(),matched_boundaries=boundaries,bitwise_parity=True,errors=errors,
        final_counts=banks[0].counts(),storage=[b.storage() for b in banks],
        advance_timing=dict(base_total_CPU_ns=sum(timings[0]),candidate_total_CPU_ns=sum(timings[1]),
            aggregate_speedup=sum(timings[0])/sum(timings[1]),base_median_ns=float(np.median(timings[0])),
            candidate_median_ns=float(np.median(timings[1])),
            scope='Single paired stream with alternating per-window order; input generation and parity checks excluded; includes existing refresh/failure work. Exploratory timing, not a repeated target benchmark.'))
    if load=='embedded' and thermal==25 and records==35520:
        original=json.loads((ROOT/'experiments/conditional_architecture_001/domain001/result.json').read_text())
        if stream.index!=35520 or not errors[0] or result['observation_sha256']!=original['observation_sha256']:
            raise AssertionError('preserved failure witness changed')
    write(out/'result.json',result);return result


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=False);validate(load())
    config=json.loads((ROOT/'experiments/foster_feedback_001/calibration.json').read_text());config['hysteresis_chart']='bounded'
    sources=source_receipt()
    for name in ('experiments/architecture_reuse_001/response.c','experiments/hysteresis_refinement_001/response.c',
                 'specifications/architecture_reuse_001/graph.json','experiments/foster_feedback_001/calibration.json'):
        sources['sources'][name]=identity(ROOT/name)
    write(args.out/'registration.json',dict(source=sources,config=config,
        cases=[['rest',4224,15],['multiscale',4224,35],['embedded',35520,25]],
        gates='Exact bytes/status/prefix parity including known failure; source/binary identity; no speedup acceptance threshold.'))
    write(args.out/'summary.json',dict(status='running'))
    try:
        response=response_control(args.out/'response',config)
        cases=[backend_control(args.out/f'case_{i:04d}',config,load,records,T)
               for i,(load,records,T) in enumerate([('rest',4224,15),('multiscale',4224,35),('embedded',35520,25)])]
        verify_sources(sources)
        write(args.out/'summary.json',dict(status='completed',response=response,cases=cases,
            scope='Qualification of exact reuse, not correction of the matched physical/domain failure.'))
    except Exception as error:
        write(args.out/'summary.json',dict(status='unresolved',error=str(error)));raise


if __name__=='__main__':main()
