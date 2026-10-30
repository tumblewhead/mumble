"""Source-bound backward error attribution and fixed coordinate interventions."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
import ctypes as C
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback
import numpy as np
from response import ResponseBasis,cheb,exact_trace,approximate_parts,approximate_hysteresis,summarize

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
OLD=HERE.parent/'partitioned_history_001';FIXED=HERE.parent/'history_basis_comparison_001'
sys.path.insert(0,str(OLD));from partition import Partition,dynamic_rows
sys.path.insert(0,str(HERE.parent/'history_provider_001'));from qualify import Harness,ptr,identity,save


def run(out):
    out.mkdir(parents=True,exist_ok=False);plan=json.loads((HERE/'plan.json').read_text())
    source=ROOT/plan['inputs'];binary=OLD/'comparison001/provider.so'
    tracked=list(HERE.glob('*.py'))+[HERE/'plan.json',OLD/'partition.py',FIXED/'basis.py',
        HERE.parent/'history_provider_001/qualify.py',source,binary,OLD/'comparison001/receipt.json',
        FIXED/'comparison002/reference_64.json',FIXED/'comparison002/reference_4096.json',ROOT/'src/scm_model.c']
    bindings={str(p.relative_to(ROOT)):identity(p) for p in tracked}
    for p in tracked:
        dest=out/'sources'/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    save(out/'reservation.json',dict(status='before_evaluation',plan=plan,sources=bindings,command=sys.argv,
        revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()))
    result=dict(status='failed',arms=[],weak_exposure=[],optimizer_calls=0,truth_reads=0,solver_modified=False,
                aging_added=False,compressor_qualified=False);checks=0;steps=0;mismatches=[];case='setup';start=time.monotonic()
    def check(v,label):
        nonlocal checks
        checks+=1
        if not v:raise AssertionError(case+': '+label)
    def close(a,b,label):
        nonlocal checks
        a=np.asarray(a);b=np.asarray(b);check(np.all(np.isfinite(a)) and np.all(np.isfinite(b)),label+' finite')
        ratio=abs(a-b)/(2e-8+2e-10*abs(b));checks+=1
        if np.any(ratio>1):mismatches.append(dict(case=case,label=label,max_gap=float(np.max(abs(a-b))),max_allowance_ratio=float(np.max(ratio))))
    def work(n):
        nonlocal steps
        check(steps+n<=plan['checks']['model_steps_upper_cap'],'pre-call work cap');steps+=n
    try:
        h=Harness(binary);inp=json.loads(source.read_text());points=np.array(inp['queries']);rows=[]
        lower=np.array(inp['lower']);upper=np.array(inp['upper']);limits=[(upper[11]-1)*np.exp(lower[5]),lower[11]*np.exp(lower[5])]
        for raw in inp['raw_cycle']:
            row=np.zeros(3);check(h.lib.hp_decode(*raw,ptr(row))==0,'decode');rows.append(row)
        rows=np.tile(rows,(inp['repeat_count'],1));old=json.loads((OLD/'comparison001/receipt.json').read_text())
        save(out/'frozen_inputs.json',dict(input_identity=identity(source),charge_domain_Ah=limits,
            unchanged_query_count=len(points),current_scales=plan['diagnostics']['weak_exposure']['current_scale']))
        for n in plan['baseline']['prefixes']:
            case=f'exact/{n}';obs=np.ascontiguousarray(rows[:n]);charges=np.cumsum(obs[:,0]*obs[:,1]/3600)
            work(n*len(points));exact,offset,hs,endpoint,meta=exact_trace(obs,points)
            reference=json.loads((FIXED/f'comparison002/reference_{n}.json').read_text())
            exact_cost=.5*np.sum((exact.astype(np.longdouble).sum(axis=2)+offset.astype(np.longdouble))**2,axis=1)
            close(exact_cost,reference['costs'],'independent physical recurrence cost versus original C')
            close(endpoint,reference['endpoints'],'independent physical endpoint versus original C')
            check(meta['max_free_response_closed_form_gap']<2e-10,'free responses versus closed form')
            for domain in plan['baseline']['domains']:
                for arm in plan['candidate_arms']:
                    case=f'{n}/{domain}/{arm["name"]}'
                    basis=ResponseBasis(arm,domain,h.mean,h.sd,lower,upper)
                    work(n*(3*basis.m+2*basis.m*basis.m));full=basis.rows(obs);p=Partition(basis,12,limits)
                    ids=[i for i,x in enumerate(points) if basis.features(x) is not None];xx=points[ids]
                    check(len(ids)==(97 if domain=='public_half_SD' else 129),'declared domain')
                    approx,queries=approximate_parts(basis,p,full,obs,charges,xx)
                    score=summarize(approx,exact[ids],offset[ids],ids)
                    check(score['attribution_identity_max_gap']<2e-8,'signed attribution identity')
                    bound=128*np.finfo(np.longdouble).eps*score['cost_identity_roundoff_scale']+2e-12
                    check(score['cost_identity_max_gap']<=bound,'long-double direct square identity')
                    s=dynamic_rows(basis,full,obs);t=p.charge_rows(charges)[:,:p.k]
                    design=np.column_stack((s,t));v=np.stack([z[0] for z in queries]);jac=np.stack([z[1] for z in queries])
                    qr=np.linalg.qr(design,mode='r');qr_values=v@qr.T
                    close(.5*np.sum(qr_values**2,axis=1),score['direct_approx_costs'],'full square-root query versus component evaluation')
                    direct_j=design@jac[0];qr_j=qr@jac[0]
                    close(direct_j.T@direct_j,qr_j.T@qr_j,'full square-root GN')
                    for j in range(16):
                        xp=h.mean.copy();xm=h.mean.copy();step=1e-5*h.sd[j];xp[j]+=step;xm[j]-=step
                        fd=(p.query(xp)[0]-p.query(xm)[0])/(2*step)
                        check(np.all(abs(fd-jac[0,:,j])*h.sd[j]<=1e-5*np.maximum(1,abs(jac[0,:,j])*h.sd[j])),
                            'analytic derivative in original coordinates')
                    for i in set(range(len(points)))-set(ids):check(p.query(points[i]) is None,'no out-of-domain extrapolation')
                    if arm['name']=='baseline':
                        prior=next(a for a in old['arms'] if (a['records'],a['dynamic_degree'],a['OCV_charge_degree'],a['domain'])==(n,4,12,domain))
                        close(score['direct_approx_costs'],np.array(prior['cost_gaps'])+np.array(reference['costs'])[ids],'reproduce inherited baseline')
                    substitutions={}
                    if arm['name']=='baseline':
                        for label,indices in [('exact_hysteresis',[6,7]),('exact_RC',list(range(6))),
                                              ('exact_free_attenuations',[1,3,5,7]),('exact_forced_hysteresis',[6])]:
                            trial=approx.copy();trial[:,:,indices]=exact[ids][:,:,indices]
                            detail=summarize(trial,exact[ids],offset[ids],ids)
                            substitutions[label]=dict(error_oscillation_NLL=detail['error_oscillation_NLL'],
                                peak_component_voltage_error_V=detail['peak_component_voltage_error_V'])
                    endpoint_approx=np.stack([basis.endpoint(x) for x in xx])
                    entry=dict(records=n,domain=domain,arm=arm['name'],query_count=len(ids),score=score,
                        memory=p.memory(),endpoint_error_by_coordinate=np.max(abs(endpoint_approx-endpoint[ids]),axis=0).tolist(),
                        source=meta,substitution_diagnostics=substitutions)
                    result['arms'].append(entry)
                    print(json.dumps(dict(records=n,domain=domain,arm=arm['name'],oscillation=score['error_oscillation_NLL'],
                        maximum_quadratic=score['max_quadratic_error_NLL'])),flush=True)
        # Independent analytical current-scaling control; no ADC reinterpretation.
        ids=list(range(97));xx=points[ids];previous_errors={}
        for scale in plan['diagnostics']['weak_exposure']['current_scale']:
            obs=rows.copy();obs[:,1]*=scale;work(len(obs)*len(xx))
            _,_,exact_h,_,meta=exact_trace(obs,xx)
            qp=np.cumsum(np.maximum(obs[:,1],0)*obs[:,0]/3600);qm=np.cumsum(np.maximum(-obs[:,1],0)*obs[:,0]/3600)
            for arm in [v for v in plan['candidate_arms'] if v['name'] in ['baseline','physical_hysteresis']]:
                case=f'weak_exposure/{scale}/{arm["name"]}'
                basis=ResponseBasis(arm,'public_half_SD',h.mean,h.sd,lower,upper)
                work(len(obs)*65);full=basis.rows(obs);approx_h=approximate_hysteresis(basis,full,xx);error=approx_h-exact_h
                peak=np.max(abs(error),axis=(0,1));delta_gamma=[]
                for j in [3,4]:
                    features=np.stack([cheb(basis.coordinate(x[j],j)[0],4)[0] for x in xx])
                    delta_gamma.append(features@(basis.inv@np.exp(basis.grid[j]))-np.exp(xx[:,j]))
                lead_plus=delta_gamma[0][:,None]*qp[None,:];lead_minus=delta_gamma[1][:,None]*qm[None,:]
                leading=np.stack((lead_plus-lead_minus,-lead_plus-lead_minus),axis=2)
                residual_norm=np.sqrt(np.sum(error**2,axis=(0,1)));remainder_norm=np.sqrt(np.sum((error-leading)**2,axis=(0,1)))
                ratio=[float(a/b) if b else None for a,b in zip(remainder_norm,residual_norm)]
                entry=dict(scale=scale,arm=arm['name'],peak_forced_free_h_error=peak.tolist(),
                    first_order_prediction_relative_L2_remainder=ratio,
                    above_roundoff_orientation=[bool(x>128*np.finfo(float).eps) for x in peak],
                    source=meta)
                if arm['name'] in previous_errors:
                    entry['observed_order_when_halving_current']=(np.log(previous_errors[arm['name']]/peak)/np.log(2)).tolist()
                previous_errors[arm['name']]=peak;result['weak_exposure'].append(entry)
        check(all(identity(ROOT/name)==value for name,value in bindings.items()),'bound sources unchanged')
        result.update(status='completed_with_numerical_mismatches' if mismatches else 'numerical_controls_passed',
                      long_double_mantissa_bits=np.finfo(np.longdouble).nmant)
    except Exception:result['error']=traceback.format_exc()
    result.update(checks=checks,model_steps_upper=steps,numerical_mismatches=mismatches,wall_s=time.monotonic()-start)
    save(out/'receipt.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ['arms','weak_exposure']},indent=2),flush=True)
    return 0 if result['status']=='numerical_controls_passed' else 1


if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('usage: analyze.py EXCLUSIVE_OUTPUT_DIRECTORY')
    raise SystemExit(run(Path(sys.argv[1]).resolve()))
