"""Numerical target profiles using the C optimizer, with no truth input.

These are finite-grid local optimization studies, not certified confidence sets.
Failed optimizations stay missing. Structural non-excitation is recorded exactly.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
EXE=ROOT/'build/scm_estimator'

def atomic(path, obj):
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')
    temp.replace(path)

def proposed_sd(fit, target):
    """Curvature only proposes grid nodes; it never asserts qualification."""
    n=fit['modes'];nt=n+4;p=nt+2*n+3
    H=np.array(fit['joint_normal']).reshape(p,p);s=np.array(fit['coordinate_scales'])
    e,V=np.linalg.eigh((H+H.T)/2);keep=e>max(e[-1]*1e-10,1e-100)
    g=np.zeros(p);t=fit['theta'];a=fit['alpha'];Q=math.exp(t[n+3]);q=fit['charge_Ah']
    if target=='Q_Ah':g[n+3]=Q*s[n+3]
    elif target=='current_soc':g[n+2]=s[n+2];g[n+3]=q/Q*s[n+3]
    elif target=='gamma_minus':g[n+1]=math.exp(t[n+1])*s[n+1]
    elif target.startswith('tau'):
        i=int(target[3:])-1;g[i]=math.exp(t[i])*s[i]
    elif target=='R0':g[nt]=s[nt]
    else:raise ValueError(target)
    if np.sum((V[:,~keep].T@g)**2)>1e-8*(g@g):return None
    return math.sqrt(max(0,float(np.sum((V[:,keep].T@g)**2/e[keep]))))

def build_grid(fit, target, assessment):
    item=assessment['parameters'][target]
    center=item['point'];lo,hi=item['prior_support'];span=hi-lo
    sd=proposed_sd(fit,target)
    if sd is None or not math.isfinite(sd) or sd<=0:
        sd={'Q_Ah':.012,'current_soc':.03,'gamma_minus':250,'R0':.03}.get(target,.20*center)
    # Broad support probes accompany local probes so the study does not only
    # inspect one tiny tangent neighborhood. Endpoints are inset for rounding.
    values=[lo+1e-7*span,lo+.25*span,lo+.5*span,lo+.75*span,hi-1e-7*span]
    values += [center+k*sd for k in [-3,-2,-1,0,1,2,3]]
    values=sorted(set(float(np.clip(x,lo+1e-10*span,hi-1e-10*span)) for x in values))
    return center,sd,values

def fit_value(record,target,value,initial=None):
    fit=record['result'];n=fit['modes'];theta=list(initial or fit['theta'])
    command=[str(EXE),'--data',str(ROOT/'data'/f"{record['case_id']}.csv"),
             '--case',record['case_id'],'--modes',str(n),'--method','full',
             '--sigma',str(fit['sigma_V']),'--prefix',str(fit['samples']),
             '--starts','2','--max-iter','180']
    if target=='current_soc':
        q=fit['charge_Ah'];ql,qh=.03,.10
        if q>0:
            if value>=.95:return {'target':value,'status':'outside_charge_and_initial_SOC_support'}
            ql=max(ql,q/(.95-value))
            if value<.2:qh=min(qh,q/(.2-value))
        elif q<0:
            if value<=.2:return {'target':value,'status':'outside_charge_and_initial_SOC_support'}
            ql=max(ql,-q/(value-.2))
            if value>.95:qh=min(qh,-q/(value-.95))
        if ql>qh:return {'target':value,'status':'outside_charge_and_initial_SOC_support'}
        theta[n+3]=math.log(np.clip(math.exp(theta[n+3]),ql,qh))
        command+=['--fixed-current-soc',format(value,'.17g')]
    elif target=='Q_Ah':command+=['--fixed',str(n+3),format(math.log(value),'.17g')]
    elif target=='gamma_minus':command+=['--fixed',str(n+1),format(math.log(value),'.17g')]
    elif target.startswith('tau'):command+=['--fixed',str(int(target[3:])-1),format(math.log(value),'.17g')]
    elif target=='R0':command+=['--fixed-alpha','0',format(value,'.17g')]
    command+=['--initial',','.join(format(x,'.17g') for x in theta)]
    start=time.perf_counter();p=subprocess.run(command,capture_output=True,text=True)
    out={'target':value,'command':command,'returncode':p.returncode,'wall_s':time.perf_counter()-start}
    if p.returncode==0:
        try:out.update(status='evaluated',result=json.loads(p.stdout))
        except Exception as e:out.update(status='invalid_output',error=str(e),stdout=p.stdout)
    else:out.update(status='missing_optimization',stderr=p.stderr)
    return out

def summarize_profile(out):
    """A feasible low cost is a witness; an unfinished high cost is not exclusion.

    Even converged fits only provide finite-grid local optimization evidence.
    They never certify global exclusion of a target value or confidence coverage.
    """
    if out.get('status')=='structurally_unexcited':return out
    evaluations=out.get('evaluations',[])
    good=[e for e in evaluations if e.get('status')=='evaluated']
    minimum=min([out['baseline_objective']]+[e['result']['objective_full'] for e in good])
    for e in good:
        e['delta_NLL']=e['result']['objective_full']-minimum
        e['optimizer_resolved']=e['result']['status']==0
        e['can_supply_low_cost_witness']=True
        e['can_supply_heuristic_outside_point']=e['optimizer_resolved']
    accepted=sorted(e['target'] for e in good if e['delta_NLL']<=2)
    bracket=list(out['prior_support']);evidence=[None,None]
    if accepted:
        for side,edge in ((0,accepted[0]),(1,accepted[-1])):
            candidates=[e for e in good if e['optimizer_resolved'] and e['delta_NLL']>2
                        and (e['target']<edge if side==0 else e['target']>edge)]
            if candidates:
                chosen=(max if side==0 else min)(candidates,key=lambda e:e['target'])
                bracket[side]=chosen['target']
                evidence[side]={'target':chosen['target'],'optimizer_status':0,
                                'delta_NLL':chosen['delta_NLL']}
    missing=sum(e.get('status') in ('missing_optimization','invalid_output') for e in evaluations)
    unresolved=sum(e['result']['status']!=0 for e in good)
    out.update(status='incomplete_numerical_grid_profile' if missing or unresolved else 'numerical_grid_profile',
               minimum_observed_objective=minimum,
               baseline_improvement=out['baseline_objective']-minimum,
               accepted_sample_range=[accepted[0],accepted[-1]] if accepted else None,
               support_bracket=bracket,bracket_touches_support=any(e is None for e in evidence),
               bracket_outside_evidence=evidence,
               missing_optimizations=missing,optimizer_unresolved=unresolved,
               interpretation='Low-cost feasible candidates are witnesses, including unfinished optimizations. '
               'Only converged high-cost grid candidates can supply a heuristic outside point; otherwise '
               'that side retains prior support. A local optimizer and finite grid do not prove global '
               'exclusion between or at grid points. This is not a calibrated confidence interval.')
    return out

def profile(record,target):
    f=record['result'];item=record['assessment']['parameters'][target]
    out={'case_id':record['case_id'],'checkpoint_s':record['checkpoint_s'],'target':target,
         'baseline_objective':f['objective_full'],'baseline_theta':f['theta'],
         'baseline_status':f['status'],'prior_support':item['prior_support'],
         'likelihood_threshold_delta_NLL':2.0,'coverage_certificate':False}
    absent=(target=='gamma_minus' and bool(f['unexcited_theta_mask']&(1<<(f['modes']+1))))
    if record['checkpoint_s']==10 and target=='Q_Ah':absent=True
    if absent:
        out.update(status='structurally_unexcited',support_bracket=item['prior_support'],evaluations=[],reason='The target does not enter any observation in this retained prefix.')
        return out
    center,sd,values=build_grid(f,target,record['assessment'])
    evaluations=[]
    # Evaluate center-near points first; starts always include the baseline,
    # not any synthetic truth or the eventual full-history solution.
    for value in sorted(values,key=lambda x:abs(x-center)):
        evaluations.append(fit_value(record,target,value))
    good=[e for e in evaluations if e['status']=='evaluated']
    minimum=min([f['objective_full']]+[e['result']['objective_full'] for e in good])
    for e in good:e['delta_NLL']=e['result']['objective_full']-minimum
    accepted=sorted(e['target'] for e in good if e['delta_NLL']<=2.0)
    # One extra midpoint per boundary improves resolution without pretending
    # that a sparse grid supplies a global nonlinear certificate.
    extra=[]
    if accepted:
        ordered=sorted(good,key=lambda e:e['target'])
        for edge,side in ((accepted[0],-1),(accepted[-1],1)):
            outside=[e['target'] for e in ordered if (e['target']-edge)*side>0 and e['delta_NLL']>2]
            if outside:extra.append((edge+(max(outside) if side<0 else min(outside)))/2)
    for value in extra:
        e=fit_value(record,target,value);evaluations.append(e)
        if e['status']=='evaluated':e['delta_NLL']=e['result']['objective_full']-minimum;good.append(e)
    minimum=min([f['objective_full']]+[e['result']['objective_full'] for e in good])
    for e in good:e['delta_NLL']=e['result']['objective_full']-minimum
    accepted=sorted(e['target'] for e in good if e['delta_NLL']<=2)
    bracket=list(item['prior_support']);touches=True
    if accepted:
        below=[e['target'] for e in good if e['target']<accepted[0] and e['delta_NLL']>2]
        above=[e['target'] for e in good if e['target']>accepted[-1] and e['delta_NLL']>2]
        bracket=[max(below) if below else bracket[0],min(above) if above else bracket[1]]
        touches=not below or not above
    missing=[e for e in evaluations if e['status']=='missing_optimization']
    out.update(status='numerical_grid_profile' if not missing else 'incomplete_numerical_grid_profile',
               center=center,grid_proposal_sd=sd,evaluations=sorted(evaluations,key=lambda e:e['target']),
               minimum_observed_objective=minimum,baseline_improvement=f['objective_full']-minimum,
               accepted_sample_range=[accepted[0],accepted[-1]] if accepted else None,
               support_bracket=bracket,bracket_touches_support=touches,
               missing_optimizations=len(missing),
               interpretation='Bracket uses tested outside grid points; it is not a proof of global exclusion between samples. Numerical optimizer failures are missing, not evidence against a physical candidate.')
    return summarize_profile(out)

def main():
    a=argparse.ArgumentParser();a.add_argument('--workers',type=int,default=3);a.add_argument('--output',default='results/profile_results.json');a.add_argument('--resummarize',action='store_true');opts=a.parse_args()
    if opts.resummarize:
        destination=ROOT/opts.output;out=json.loads(destination.read_text())
        out['profiles']=[summarize_profile(p) for p in out['profiles']]
        out['metadata']['summary_policy']='v2: unfinished high-cost optimizations never define outside boundaries'
        atomic(destination,out)
        print(json.dumps({'profiles':len(out['profiles']),'optimizer_unresolved':sum(p.get('optimizer_unresolved',0) for p in out['profiles']),'missing':sum(p.get('missing_optimizations',0) for p in out['profiles'])}))
        return
    source=json.loads((ROOT/'results/streaming_results.json').read_text())
    records={r['checkpoint_s']:r for r in source['records'] if r['case_id']=='cell_a_35hz_s202610240'}
    selection={'Q_Ah':[10,40,220,400,600,900,1200,1800,2100],
               'current_soc':[10,40,220,400,600,900,1200,1800,2100],
               'gamma_minus':[400,600,900,2100], 'tau2':[40,220,2100],
               'tau1':[40,2100], 'R0':[40,2100]}
    jobs=[(records[t],target) for target,times in selection.items() for t in times]
    out={'metadata':{'schema':'scm_target_profiles_v1','binary_sha256':hashlib.sha256(EXE.read_bytes()).hexdigest(),
                     'workers':opts.workers,'noise':'iid1mV','all_optimization':'C','truth_used_for_grids':False,
                     'profile_scope':'Selected first-cell first-seed prefixes; numerical finite-grid comparisons, not a coverage certificate'},'profiles':[]}
    destination=ROOT/opts.output;destination.parent.mkdir(exist_ok=True);atomic(destination,out)
    with concurrent.futures.ThreadPoolExecutor(max_workers=opts.workers) as pool:
        futures={pool.submit(profile,r,target):(r['checkpoint_s'],target) for r,target in jobs}
        for future in concurrent.futures.as_completed(futures):
            t,target=futures[future]
            try:result=future.result()
            except Exception as e:result={'checkpoint_s':t,'target':target,'status':'runner_error','error':repr(e)}
            out['profiles'].append(result);out['profiles'].sort(key=lambda r:(r['checkpoint_s'],r['target']));atomic(destination,out)
            print(t,target,result['status'],result.get('support_bracket'),flush=True)
    out['metadata']['binary_unchanged']=out['metadata']['binary_sha256']==hashlib.sha256(EXE.read_bytes()).hexdigest();atomic(destination,out)

if __name__=='__main__':main()
