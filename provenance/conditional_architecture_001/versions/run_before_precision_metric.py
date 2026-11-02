"""Stage A common-query comparison; fixed-shape controls are not fitted batteries."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import time
import numpy as np
from .conditional import FixedShape, chart_amplitude_jacobian
from experiments.foster_campaign_001.backend import ROOT, prepare_c
from experiments.foster_campaign_001.h7_backend import prepare_h7
from experiments.foster_campaign_001.coordinates import prior
from experiments.foster_campaign_001.compact import StimulusStream
from experiments.foster_campaign_001.stimulus import cells
from experiments.foster_campaign_001.run import parser
from experiments.foster_feedback_001.estimator import Model
from experiments.foster_uncertainty_audit_001.conditional_packet import partition, chart_from
from experiments.hysteresis_refinement_001.field import MixedField, features_jacobian
from experiments.h7_history_quality_001.history import write, source_receipt, verify_sources, ReplayRows


def public_queries(config):
    mean,_=prior(config);amplitude,center=partition(mean)
    shapes=[center.copy(),center*np.exp([.1,-.08,.06,.12,-.1]),
            center*np.exp([-.12,.1,-.08,-.1,.12])]
    other=amplitude.copy();other[0]+=.03;other[4]*=.98;other[5:10]*=1.03;other[10]=.2*other[9]
    third=amplitude.copy();third[0]-=.03;third[4]*=1.02;third[5:10]*=.97;third[10]=-.2*third[9]
    return center,shapes,[amplitude,other,third]


def direct(model,factory,count,digest,amplitude,shape):
    rows=ReplayRows(factory,count,digest);state=chart_from(amplitude,shape)
    D=chart_amplitude_jacobian(amplitude);g=np.zeros(11);P=np.zeros((11,11));cost=0.
    for first in range(0,count,4096):
        obs=rows[first:first+4096];v,J,end,F=model.evaluate(state,obs)
        B=(J@D)/obs[:,4,None];r=(v-obs[:,3])/obs[:,4]
        cost+=.5*float(r@r)+float(np.log(obs[:,4]).sum()+len(obs)*.5*math.log(2*math.pi))
        g+=B.T@r;P+=B.T@B;state=end;D=F@D
    return cost,g,P,partition(state)[0],rows.verified_passes


def differences(candidate,reference,scale):
    c,g,P,end=candidate;rc,rg,rP,rend=reference[:4]
    dg=(g-rg)*scale;dP=scale[:,None]*(P-rP)*scale[None,:]
    cost_relative=abs(c-rc)/max(1.,abs(rc))
    g_relative=float(np.linalg.norm(dg)/max(1.,np.linalg.norm(rg*scale)))
    p_relative=float(np.linalg.norm(dP)/max(1.,np.linalg.norm(scale[:,None]*rP*scale[None,:])))
    endpoint=float(np.max(abs(end-rend)))
    return dict(nll_difference=float(c-rc),relative_nll_error=float(cost_relative),
        scaled_gradient_error_norm=float(np.linalg.norm(dg)),scaled_gradient_relative_error=g_relative,
        scaled_precision_relative_error=p_relative,endpoint_amplitude_max_error=endpoint,
        endpoint_SOC_difference_pp=float(100*(end[0]-rend[0])),
        endpoint_hysteresis_voltage_difference_V=float(end[10]-rend[10]),
        arithmetic_gate=bool(cost_relative<=1e-9 and g_relative<=1e-8 and p_relative<=1e-8 and endpoint<=1e-9))


def run_case(out,builds,config,load,prefixes,shapes,amplitudes,center):
    out.mkdir();settings=vars(parser().parse_args([]));settings.update(sample_rate_hz=35,
        current_a=.06,temperature='fixed',temperature_mean_c=25.,field_refresh_seconds=60)
    case=dict(cell='B',load=load,noise_v=.0002,seed=1103,load_seed=7)
    recipe=dict(case=case,settings=settings,cell=cells()['B'])
    source=hashlib.sha256(json.dumps(recipe,sort_keys=True).encode()).hexdigest()
    factory=lambda:StimulusStream(config,cells()['B'],case,settings)
    packets=[FixedShape(config,s,source) for s in shapes]
    field=MixedField(config,center,1.,7,prepare_h7(builds)[0],source)
    model=Model(prepare_c(builds,35,config)[0],config)
    stream=factory();digest=hashlib.sha256();records=[]
    timing=dict(conditional_update_cpu_s=0.,H7_field_update_cpu_s=0.,direct_queries_cpu_s=0.)
    scale=np.maximum(abs(amplitudes[0]),[.1,.01,.01,.01,1.,.01,.01,.01,.01,.001,.001])
    result=dict(status='running',recipe=recipe,source_id=source,prefixes=records)
    write(out/'result.json',result)
    for target in sorted({max(16,math.ceil(s*35/16)*16) for s in prefixes}):
        while stream.index<target:
            first=stream.index;obs,_,_=stream.read(min(1024,target-first))
            if stream.failure or not len(obs):raise ValueError('fixture stopped')
            digest.update(obs.astype('<f8',copy=False).tobytes())
            start=time.process_time()
            for packet in packets:packet.advance(first,obs,source)
            timing['conditional_update_cpu_s']+=time.process_time()-start
            start=time.process_time();field.update(first,obs)
            timing['H7_field_update_cpu_s']+=time.process_time()-start
        queries=[]
        for si,(packet,shape) in enumerate(zip(packets,shapes)):
            for ai,a in enumerate(amplitudes):
                query=dict(shape_index=si,amplitude_index=ai)
                try:
                    conditional=packet.evaluate(a,shape)
                    start=time.process_time();reference=direct(model,factory,target,digest.hexdigest(),a,shape)
                    timing['direct_queries_cpu_s']+=time.process_time()-start
                    query.update(status='supported',direct_nll=reference[0],verified_replays=reference[4],
                        conditional=differences(conditional,reference,scale))
                    x=chart_from(a,shape);r=field.residual(x)
                    J=field.root@features_jacobian(field,x)@chart_amplitude_jacobian(a)
                    h7=(.5*float(r@r)+field.noise,J.T@r,J.T@J,field.outgoing(x))
                    query['H7']=differences(h7,reference,scale)
                    # Only the fixed-shape representation has the numerical parity gate.
                    query['H7'].pop('arithmetic_gate')
                except ValueError as error:
                    query.update(status='unsupported',reason=str(error))
                queries.append(query)
        records.append(dict(records=target,hours=target/35/3600,observation_sha256=digest.hexdigest(),queries=queries))
        result.update(timing=timing,conditional_per_shape_storage=packets[0].storage(),H7_storage=field.storage(),
            max_input_chunk_B=1024*5*8,gradient_scale=scale,
            timing_scope='Host process CPU; conditional update is SUM of three fixed-shape factors, H7 is one continuous field. Python response versus native response; not M23 timing.')
        write(out/'result.json',result)
        print(json.dumps(dict(load=load,records=target,supported=sum(q['status']=='supported' for q in queries))),flush=True)
    result['status']='completed' if all(q['status']=='supported' and q['conditional']['arithmetic_gate'] for r in records for q in r['queries']) else 'unresolved'
    write(out/'result.json',result);return result


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--out',required=True,type=Path)
    p.add_argument('--prefix-seconds',nargs='+',type=float,default=[600,3600])
    p.add_argument('--loads',nargs='+',choices=['rest','multiscale','embedded'],default=['rest','multiscale','embedded'])
    args=p.parse_args()
    if not args.prefix_seconds or any(not math.isfinite(x) or x<=0 for x in args.prefix_seconds):p.error('positive finite prefix seconds')
    args.out.mkdir(parents=True,exist_ok=False)
    config=json.loads((ROOT/'experiments/foster_feedback_001/calibration.json').read_text());config['hysteresis_chart']='bounded'
    center,shapes,amplitudes=public_queries(config);sources=source_receipt()
    write(args.out/'registration.json',dict(arguments={**vars(args),'out':str(args.out)},source=sources,config=config,
        shapes=shapes,amplitudes=amplitudes,selection='All probes from public calibration before observations; no fitted shape or truth.',
        contract='specifications/conditional_architecture_001/README.md'))
    results=[];write(args.out/'summary.json',dict(status='running',cases=results))
    for load in args.loads:
        directory=args.out/f'case_{len(results):04d}'
        try:result=run_case(directory,args.out,config,load,args.prefix_seconds,shapes,amplitudes,center)
        except Exception as error:
            result=json.loads((directory/'result.json').read_text()) if (directory/'result.json').exists() else {}
            result.update(status='unresolved',error=str(error));write(directory/'result.json',result)
        results.append(result);write(args.out/'summary.json',dict(status='running',cases=results))
    verify_sources(sources)
    status='completed' if all(r['status']=='completed' for r in results) else 'unresolved'
    write(args.out/'summary.json',dict(status=status,cases=results))
    return 0 if status=='completed' else 1


if __name__=='__main__':raise SystemExit(main())
