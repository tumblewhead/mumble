"""Matched causal replay of a fixed-origin tangent history update."""
import argparse
import copy
import json
from pathlib import Path
import time
import numpy as np
from experiments.foster_campaign_001.coordinates import prior
from experiments.foster_campaign_001.field_backend import transported
from experiments.foster_c_baseline_001.reference import Baseline,library
from experiments.foster_uncertainty_audit_001.conditional_packet import partition
from experiments.joint_rate_history_001.field import Field,build
from experiments.slow_likelihood_diagnostic_001.numerics import Compressed,solve
from experiments.uncertainty_weak_stimulus_001.diagnostics import write,identity,endpoint,CONVERGED
from .numerics import Tangent

BASE=Path(__file__).resolve().parents[1]/'uncertainty_weak_stimulus_001'


def run_case(label,out,probe,extended=False):
    case=BASE/'attempt001'/label;reg=json.loads((case/'regeneration.json').read_text())
    if identity(case/'observations.npy')!=reg['observations']:raise ValueError('observations changed')
    cfg=json.loads((case/'calibration.json').read_text());mean,L=prior(cfg)
    campaign=Path(reg['source_case']).parent
    settings=json.loads((campaign/'campaign_plan.json').read_text())['configuration']
    rate=reg['sample_rate_Hz'];interval=int(reg['field_counts']['field_history']['refresh_interval_records'])
    allobs=np.load(case/'observations.npy',mmap_mode='r');n=reg['fit_records']
    first=(n//interval*interval if label=='weak_B_cycle' else n-interval)
    if extended:
        first=(round(3.5*3600*rate)//interval)*interval
        n=len(allobs)//16*16
    obs=allobs[:n]
    field=Field(cfg,partition(mean)[1],1.,5,probe,source=reg['observations']['sha256']);started=time.perf_counter()
    for i in range(0,first,4096):field.update(i,obs[i:min(i+4096,first)])
    objective=Compressed(field,mean,L);initial=solve(objective)
    if initial['diagnostic']['stop'] not in CONVERGED:raise ValueError(('initial full-prefix fit unresolved',initial['diagnostic']))
    origin_w=initial['w'].copy();end,D=transported(field,initial['x']);root=D@initial['root']
    initial_endpoint=endpoint(end,root)
    tangent=Tangent(objective,origin_w,first)
    num=cfg['numerical'];lib=library(campaign/'backend_c/estimator.so')
    def make_rolling(m,L):
        return Baseline(lib,8,initial=(m,L),settings=dict(rounds=num['max_rounds'],fractions=num['fractions'],
                    gradient_tol=num['gradient_inf_tolerance'],step_tol=num['latent_step_tolerance']))
    rolling=make_rolling(end,root)
    # The online rolling baseline is reset by the same causal field refresh at
    # the existing scheduled boundaries, not a posterior multiplied twice.
    original_first=first;rolling_first=first;history=[];timing=dict(accumulation_s=0.,tangent_s=0.,oracle_s=0.,rolling_s=0.,scheduled_refresh_s=0.)
    snapshots={};resets=0;failures=[];geometry={}
    # Examine curvature of state transport along the initial Q uncertainty direction.
    qdirection=initial['root']@(initial['root'][5]/np.linalg.norm(initial['root'][5]))
    _,sv,V=np.linalg.svd(root.T);U=np.linalg.svd(root,full_matrices=True)[0]
    rank=int((sv>np.finfo(float).eps*16*sv[0]).sum());normal=U[:,rank:]
    for factor in [.25,.5,1.]:
        try:
            shifted=transported(field,initial['x']+factor*qdirection)[0]
            difference=shifted-end-D@(factor*qdirection)
            geometry[str(factor)]=dict(normal_curvature_residual_norm=float(np.linalg.norm(normal.T@difference)),
                                      dynamic_chart_nonlinearity=difference[:5])
        except ValueError as e:geometry[str(factor)]=dict(unresolved=str(e))
    for i in range(first,n,16):
        block=obs[i:i+16];tick=time.perf_counter();rows=field.update(i,block,return_rows=True);timing['accumulation_s']+=time.perf_counter()-tick
        tick=time.perf_counter();tangent.update(i,rows,source=field.source)
        try:fast=tangent.query()
        except (ValueError,np.linalg.LinAlgError) as e:failures.append(dict(sequence=i+16,arm='tangent',reason=str(e)));break
        timing['tangent_s']+=time.perf_counter()-tick
        tick=time.perf_counter();oracle=solve(objective,start=origin_w);timing['oracle_s']+=time.perf_counter()-tick
        if oracle['diagnostic']['stop'] not in CONVERGED:
            failures.append(dict(sequence=i+16,arm='oracle',reason=oracle['diagnostic']['stop']));break
        origin_w=oracle['w'];tick=time.perf_counter();oe,oD=transported(field,oracle['x']);oL=oD@oracle['root'];timing['oracle_s']+=time.perf_counter()-tick
        tick=time.perf_counter();status,_=rolling.replay(block);rm=rolling.snapshot();timing['rolling_s']+=time.perf_counter()-tick
        if status<0:failures.append(dict(sequence=i+16,arm='rolling',reason=str(status)));break
        rolling_endpoint=endpoint(rm[:16],rm[16:272].reshape(16,16))
        fe=endpoint(fast['end'],fast['endpoint_root']);ref=endpoint(oe,oL)
        history.append(dict(sequence=i+16,time_s=(i+16-original_first)/rate,
            tangent_Q=fe['Q_Ah'],oracle_Q=ref['Q_Ah'],rolling_Q=rolling_endpoint['Q_Ah'],
            tangent_Q_log_sd=fe['Q_log_sd'],oracle_Q_log_sd=ref['Q_log_sd'],rolling_Q_log_sd=rolling_endpoint['Q_log_sd'],
            tangent_SOC=fe['SOC'],oracle_SOC=ref['SOC'],rolling_SOC=rolling_endpoint['SOC'],
            tangent_minus_oracle_Q_percent=100*(fe['Q_Ah']/ref['Q_Ah']-1),
            tangent_minus_oracle_SOC_pp=100*(fe['SOC']-ref['SOC']),
            tangent_to_oracle_Q_SD_ratio=fe['Q_log_sd']/ref['Q_log_sd'],
            tangent_endpoint_root=fast['endpoint_root'] if i+16==reg['fit_records'] else None,
            scheduled_refresh=(i+16)%interval==0))
        if i+16==reg['fit_records'] or i+16==n:
            snapshots[str(i+16)]=dict(tangent=fe,oracle=ref,rolling_before_refresh=rolling_endpoint)
        if (i+16)%interval==0:
            # Candidate uses its own scheduled nonlinear solve, initialized from
            # its own prior fast query. Oracle cannot initialize the candidate.
            tick=time.perf_counter();anchor=solve(objective,start=fast['w'])
            if anchor['diagnostic']['stop'] not in CONVERGED:
                failures.append(dict(sequence=i+16,arm='scheduled_refresh',reason=anchor['diagnostic']['stop']));break
            tangent=Tangent(objective,anchor['w'],i+16);timing['scheduled_refresh_s']+=time.perf_counter()-tick
            ae,aD=transported(field,anchor['x']);aL=aD@anchor['root']
            rolling=make_rolling(ae,aL);rolling_first=i+16;resets+=1
        if len(history)%1000==0:print(label,'windows',len(history),flush=True)
    differences=[abs(h['tangent_minus_oracle_Q_percent']) for h in history]
    result=dict(label=label,extended=extended,status='complete' if not failures else 'unresolved',failures=failures,
        first_record=original_first,end_record=n,seconds=(n-original_first)/rate,windows=len(history),scheduled_refreshes=resets,
        initial=initial_endpoint,initial_state_transport_singular_values=sv,initial_numerical_rank=rank,geometry=geometry,
        endpoints=snapshots,history=history,timing=timing,storage=tangent.storage(),build_and_replay_wall_s=time.perf_counter()-started,
        max_abs_Q_difference_percent=max(differences,default=0.),
        max_abs_SOC_difference_pp=max((abs(h['tangent_minus_oracle_SOC_pp']) for h in history),default=0.),
        Q_width_ratio_range=[min(h['tangent_to_oracle_Q_SD_ratio'] for h in history),max(h['tangent_to_oracle_Q_SD_ratio'] for h in history)],
        observations=reg['observations'],truth_reads=0,comparison_scope='All arms same fresh causal prefix field; no future/truth initialization. Shared field accumulation, independent candidate scheduled fitting.')
    write(out/'result.json',result);return result


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--extended',action='store_true');p.add_argument('--labels',nargs='+',default=['owner_case_0000','owner_case_0002','owner_case_0004','owner_case_0006','weak_B_cycle'])
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    write(args.out/'registration.json',dict(labels=args.labels,extended=args.extended,
        source={f.name:identity(f) for f in Path(__file__).parent.glob('*.py')},truth_reads=0,
        rule='Freeze original-origin field tangent between existing scheduled refreshes; new rows once; nonlinear readout never fed back.',
        bounds='If a query/refit fails, mark unresolved; no clipping, variance floor or new adaptive threshold.'))
    probe=build(args.out/'response');results=[]
    for label in args.labels:
        out=args.out/label;out.mkdir();r=run_case(label,out,probe,args.extended)
        results.append({k:r[k] for k in ['label','status','windows','timing','max_abs_Q_difference_percent','max_abs_SOC_difference_pp','Q_width_ratio_range']})
        write(args.out/'summary.json',dict(cases=results,truth_reads=0))
        print(json.dumps(results[-1]),flush=True)


if __name__=='__main__':main()
