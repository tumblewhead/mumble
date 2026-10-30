"""Frozen free-response representation comparison; no fitting or truth access."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback
import numpy as np
from kernel import FreeHistory,carriers

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
PREV=HERE.parent/'response_symbolic_diagnostic_001'
OLD=HERE.parent/'partitioned_history_001';FIXED=HERE.parent/'history_basis_comparison_001'
sys.path.insert(0,str(PREV));from response import ResponseBasis,exact_trace,approximate_parts,summarize
sys.path.insert(0,str(OLD));from partition import Partition,dynamic_rows
sys.path.insert(0,str(HERE.parent/'history_provider_001'));from qualify import Harness,ptr,identity,save


def run(out):
    out.mkdir(parents=True,exist_ok=False);plan=json.loads((HERE/'plan.json').read_text())
    source=ROOT/plan['inputs'];binary=OLD/'comparison001/provider.so'
    tracked=list(HERE.glob('*.py'))+[HERE/'plan.json',PREV/'response.py',OLD/'partition.py',FIXED/'basis.py',
        HERE.parent/'history_provider_001/qualify.py',source,binary,PREV/'attempt001/receipt.json',
        PREV/'followup001/receipt.json',FIXED/'comparison002/reference_64.json',
        FIXED/'comparison002/reference_4096.json',ROOT/'src/scm_model.c']
    bindings={str(p.relative_to(ROOT)):identity(p) for p in tracked}
    for p in tracked:
        dest=out/'sources'/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    save(out/'reservation.json',dict(status='before_evaluation',plan=plan,sources=bindings,command=sys.argv,
        revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()))
    result=dict(status='failed',arms=[],raw_controls=[],optimizer_calls=0,truth_reads=0,solver_modified=False,
                aging_added=False,compressor_qualified=False)
    checks=0;steps=0;values=0;mismatches=[];case='setup';start=time.monotonic()
    def check(v,label):
        nonlocal checks
        checks+=1
        if not v:raise AssertionError(case+': '+label)
    def close(a,b,label,atol=2e-8,rtol=2e-10):
        nonlocal checks
        a=np.asarray(a);b=np.asarray(b);check(np.all(np.isfinite(a)) and np.all(np.isfinite(b)),label+' finite')
        ratio=abs(a-b)/(atol+rtol*abs(b));checks+=1
        if np.any(ratio>1):mismatches.append(dict(case=case,label=label,max_gap=float(np.max(abs(a-b))),max_allowance_ratio=float(np.max(ratio))))
    def work(n,free=False):
        nonlocal steps,values
        if free:
            check(values+n<=plan['work_caps']['new_free_kernel_scalar_values_upper'],'pre-call free work cap');values+=n
        else:
            check(steps+n<=plan['work_caps']['model_steps_upper'],'pre-call model work cap');steps+=n
    def qualify(design,queries,query,score):
        v=np.stack([z[0] for z in queries]);jac=np.stack([z[1] for z in queries])
        check(np.all(np.isfinite(design)) and np.all(np.isfinite(v)) and np.all(np.isfinite(jac)),'finite representation')
        qr=np.linalg.qr(design,mode='r');direct=v@design.T;encoded=v@qr.T
        close(.5*np.sum(encoded**2,axis=1),score['direct_approx_costs'],'QR cost versus component evaluation')
        close(.5*np.sum(direct**2,axis=1),score['direct_approx_costs'],'direct rows versus components')
        dg=np.einsum('qf,qfj->qj',direct@design,jac);qg=np.einsum('qf,qfj->qj',encoded@qr,jac)
        close(qg,dg,'QR gradient versus direct rows')
        dj=design@jac[0];qj=qr@jac[0];gn=dj.T@dj
        close(qj.T@qj,gn,'QR GN versus direct rows')
        merged=np.linalg.qr(np.vstack((np.linalg.qr(design[:17],mode='r'),np.linalg.qr(design[17:],mode='r'))),mode='r')
        mr=v@merged.T;mj=merged@jac[0]
        close(.5*np.sum(mr**2,axis=1),.5*np.sum(encoded**2,axis=1),'global-coordinate merged QR cost')
        close(np.einsum('qf,qfj->qj',mr@merged,jac),qg,'global-coordinate merged QR gradient')
        close(mj.T@mj,qj.T@qj,'global-coordinate merged QR GN')
        for j in range(16):
            xp=h.mean.copy();xm=h.mean.copy();step=1e-5*h.sd[j];xp[j]+=step;xm[j]-=step
            fd=(query(xp)[0]-query(xm)[0])/(2*step)
            scaled=jac[0,:,j]*h.sd[j]
            close((fd*h.sd[j]-scaled)/np.maximum(1,abs(scaled)),0,'original-coordinate derivative '+str(j),atol=1e-5,rtol=0)
        return qr
    try:
        h=Harness(binary);inp=json.loads(source.read_text());points=np.array(inp['queries']);rows=[]
        lower=np.array(inp['lower']);upper=np.array(inp['upper']);limits=[(upper[11]-1)*np.exp(lower[5]),lower[11]*np.exp(lower[5])]
        for raw in inp['raw_cycle']:
            row=np.zeros(3);check(h.lib.hp_decode(*raw,ptr(row))==0,'decode');rows.append(row)
        rows=np.tile(rows,(inp['repeat_count'],1));prior=json.loads((PREV/'attempt001/receipt.json').read_text())
        save(out/'frozen_inputs.json',dict(input_identity=identity(source),charge_domain_Ah=limits,query_count=len(points)))
        composition_max=0.;bound_max_ratio=0.
        for n in plan['fixed']['prefixes']:
            case=f'exact/{n}';obs=np.ascontiguousarray(rows[:n]);elapsed=np.cumsum(obs[:,0]);charges=np.cumsum(obs[:,0]*obs[:,1]/3600)
            work(n*len(points));exact,offset,_,endpoint,meta=exact_trace(obs,points)
            reference=json.loads((FIXED/f'comparison002/reference_{n}.json').read_text())
            exact_cost=.5*np.sum((exact.astype(np.longdouble).sum(axis=2)+offset.astype(np.longdouble))**2,axis=1)
            close(exact_cost,reference['costs'],'original recurrence cost versus saved C')
            close(endpoint,reference['endpoints'],'original recurrence endpoint versus saved C')
            for domain in plan['fixed']['domains']:
                case=f'{n}/{domain}/baseline'
                basis=ResponseBasis(dict(physical_RC=False,physical_hysteresis=True,tensor_hysteresis=False),domain,h.mean,h.sd,lower,upper)
                work(n*65);full=basis.rows(obs);p=Partition(basis,12,limits)
                ids=[i for i,x in enumerate(points) if basis.features(x) is not None];xx=points[ids]
                check(len(ids)==(97 if domain=='public_half_SD' else 129),'declared query domain')
                base_parts,base_queries=approximate_parts(basis,p,full,obs,charges,xx)
                design=np.column_stack((dynamic_rows(basis,full,obs),p.charge_rows(charges)[:,:p.k]))
                score=summarize(base_parts,exact[ids],offset[ids],ids)
                previous=next(a for a in prior['arms'] if (a['records'],a['domain'],a['arm'])==(n,domain,'physical_hysteresis'))
                close(score['cost_gaps'],previous['score']['cost_gaps'],'reproduce selected predecessor')
                qualify(design,base_queries,p.query,score)
                result['arms'].append(dict(records=n,domain=domain,family='baseline',scope='none',coefficients=5,score=score,memory=p.memory(),source=meta))
                for scope in plan['free_modes']:
                    indices=[5] if scope=='slowest_only' else [1,3,5]
                    trial=base_parts.copy();trial[:,:,indices]=exact[ids][:,:,indices]
                    result['raw_controls'].append(dict(records=n,domain=domain,scope=scope,score=summarize(trial,exact[ids],offset[ids],ids)))
                for family in plan['candidate_families']:
                    for scope in plan['free_modes']:
                        for k in plan['coefficients_per_selected_mode']:
                            case=f'{n}/{domain}/{family}/{scope}/{k}';bank=FreeHistory(p,family,scope,k)
                            work(n*k*len(bank.modes),free=True);dd=bank.rows(design,elapsed)
                            queries=[bank.query(x) for x in xx];v=np.stack([q[0] for q in queries])
                            approx=bank.replace_components(base_parts,dd,v);score=summarize(approx,exact[ids],offset[ids],ids)
                            close(score['attribution_identity_max_gap'],0,'signed attribution identity')
                            bound=128*np.finfo(np.longdouble).eps*score['cost_identity_roundoff_scale']+2e-12
                            close(score['cost_identity_max_gap'],0,'long-double square identity',atol=bound,rtol=0)
                            qualify(dd,queries,bank.query,score)
                            for i in set(range(len(points)))-set(ids):check(bank.query(points[i]) is None,'domain rejection')
                            if family=='log_tau_interpolation' and k==5:
                                close(score['cost_gaps'],previous['score']['cost_gaps'],'matched K5 reproduces predecessor')
                            ee=np.stack([bank.endpoint(x,elapsed[-1]) for x in xx])
                            endpoint_error=np.max(abs(ee-endpoint[ids]),axis=0)
                            # Endpoint free part is exact; approximation still applies to forced response.
                            for mode in bank.modes:
                                u=np.array([basis.coordinate(x[mode],mode)[0] for x in xx]);tv=np.polynomial.chebyshev.chebvander(u,4)
                                forced=xx[:,7+mode]*(tv@(basis.inv@basis.boundary[0][mode]))
                                close(ee[:,mode+1]-forced,xx[:,12+mode]*np.exp(-elapsed[-1]/np.exp(xx[:,mode])),'exact free endpoint')
                            if family=='time_kernel':
                                for mode in bank.modes:
                                    c=bank.pivots[mode];rho=bank.rho[mode]
                                    zz=(np.exp(-xx[:,mode])-c)/(np.exp(-xx[:,mode])+c)
                                    work(n*k+k,free=True)
                                    free_approx=zz[:,None]**np.arange(k)@carriers(elapsed,c,k).T
                                    error=np.max(abs(free_approx-np.exp(-np.exp(-xx[:,mode,None])*elapsed)))
                                    tail=rho**k/(1-rho);bound_max_ratio=max(bound_max_ratio,float(error/tail))
                                    check(error<=tail+128*np.finfo(float).eps,'uniform analytic attenuation bound on sampled points')
                                    close(carriers(0.,c,k),np.r_[1.,np.zeros(k-1)],'entering coefficient state',atol=1e-14,rtol=0)
                                    if n==64:
                                        for t in [0,.01,.1,1,10,120]:
                                            for s in [0,.03,2,30]:
                                                work(4*k,free=True)
                                                a=carriers(t,c,k);b=carriers(s,c,k);d=carriers(1.,c,k)
                                                product=np.convolve(a,b)[:k];target=carriers(t+s,c,k)
                                                composition_max=max(composition_max,float(np.max(abs(product-target))))
                                                close(product,target,'coefficient time convolution')
                                                close(np.convolve(product,d)[:k],np.convolve(a,np.convolve(b,d)[:k])[:k],'coefficient merge associativity')
                            if (n,domain,family,scope,k)==(4096,'public_half_SD','time_kernel','all_three',9):
                                synthetic=dd.copy();constant=int(np.flatnonzero(bank.keep==p.m-1)[0]);vv=queries[0][0]
                                check(vv[constant]==1.,'measurement feature identity')
                                synthetic[:,constant]=0;synthetic[:,constant]=-(synthetic@vv)
                                rr=np.linalg.qr(synthetic,mode='r')@vv;direct=synthetic@vv
                                result['cancellation']=dict(direct_cost=float(.5*(direct@direct)),QR_cost=float(.5*(rr@rr)),clipped=False)
                                close(.5*(rr@rr),.5*(direct@direct),'zero represented residual QR control')
                            entry=dict(records=n,domain=domain,family=family,scope=scope,coefficients=k,score=score,
                                memory=bank.memory(),endpoint_error_by_coordinate=endpoint_error.tolist(),source=meta)
                            result['arms'].append(entry)
                            print(json.dumps(dict(case=case,oscillation_NLL=score['error_oscillation_NLL'])),flush=True)
        check(len(result['arms'])==plan['primary_cases'],'all frozen cases completed')
        check(all(identity(ROOT/name)==value for name,value in bindings.items()),'bound sources unchanged')
        result.update(status='completed_with_numerical_mismatches' if mismatches else 'numerical_controls_passed',
            time_composition_max_abs_gap=composition_max,sampled_attenuation_error_over_uniform_bound_max=bound_max_ratio,
            long_double_mantissa_bits=np.finfo(np.longdouble).nmant)
    except Exception:result['error']=traceback.format_exc()
    result.update(checks=checks,model_steps_upper=steps,new_free_kernel_scalar_values=values,numerical_mismatches=mismatches,wall_s=time.monotonic()-start)
    save(out/'receipt.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ['arms','raw_controls']},indent=2),flush=True)
    return 0 if result['status']=='numerical_controls_passed' else 1


if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('usage: analyze.py EXCLUSIVE_OUTPUT_DIRECTORY')
    raise SystemExit(run(Path(sys.argv[1]).resolve()))
