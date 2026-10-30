"""Frozen forced-RC recurrence comparison with source-bound controls."""
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
from forced import JointRC,forced_coefficients,compose,FreeHistory,carriers

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
FREE=HERE.parent/'free_rc_kernel_001';PREV=HERE.parent/'response_symbolic_diagnostic_001'
OLD=HERE.parent/'partitioned_history_001';FIXED=HERE.parent/'history_basis_comparison_001'
sys.path.insert(0,str(PREV));from response import ResponseBasis,exact_trace,approximate_parts,summarize
sys.path.insert(0,str(OLD));from partition import Partition,dynamic_rows
sys.path.insert(0,str(HERE.parent/'history_provider_001'));from qualify import Harness,ptr,identity,save


def run(out):
    out.mkdir(parents=True,exist_ok=False);plan=json.loads((HERE/'plan.json').read_text())
    source=ROOT/plan['inputs'];binary=OLD/'comparison001/provider.so'
    tracked=list(HERE.glob('*.py'))+[HERE/'plan.json',FREE/'kernel.py',FREE/'attempt001/receipt.json',
        PREV/'response.py',OLD/'partition.py',FIXED/'basis.py',HERE.parent/'history_provider_001/qualify.py',
        source,binary,FIXED/'comparison002/reference_64.json',FIXED/'comparison002/reference_4096.json',ROOT/'src/scm_model.c']
    bindings={str(p.relative_to(ROOT)):identity(p) for p in tracked}
    for p in tracked:
        dest=out/'sources'/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    save(out/'reservation.json',dict(status='before_evaluation',plan=plan,sources=bindings,command=sys.argv,
        revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()))
    result=dict(status='failed',arms=[],raw_controls=[],arithmetic=[],state_algebra=[],optimizer_calls=0,truth_reads=0,
        solver_modified=False,aging_added=False,deployment_qualified=False)
    counts={k:0 for k in plan['work_caps'] if k!='automatic_retries'};checks=0;mismatches=[];case='setup';start=time.monotonic()
    def check(v,label):
        nonlocal checks
        checks+=1
        if not v:raise AssertionError(case+': '+label)
    def work(category,n):
        check(counts[category]+n<=plan['work_caps'][category],'pre-call '+category+' cap');counts[category]+=n
    def close(a,b,label,atol=2e-8,rtol=2e-10):
        nonlocal checks
        a=np.asarray(a);b=np.asarray(b);check(np.all(np.isfinite(a)) and np.all(np.isfinite(b)),label+' finite')
        gap=abs(a-b);ratio=gap/(atol+rtol*abs(b));checks+=1
        stats=dict(max_abs_gap=float(np.max(gap)),max_allowance_ratio=float(np.max(ratio)),failed_entries=int(np.sum(ratio>1)))
        if stats['failed_entries']:mismatches.append(dict(case=case,label=label,**stats))
        return stats
    def coeff(obs,c,k,initial=None):
        work('coefficient_convolution_multiply_adds',len(obs)*k*(k+1)//2)
        work('carrier_values',len(obs)*k)
        return forced_coefficients(obs,c,k,initial)
    def beta(t,c,k):
        work('carrier_values',np.size(t)*k)
        return carriers(t,c,k)
    def score_parts(approx,exact,offset,ids):
        score=summarize(approx,exact,offset,ids)
        close(score['attribution_identity_max_gap'],0,'signed attribution')
        close(score['cost_identity_max_gap'],0,'long-double square identity',
            atol=128*np.finfo(np.longdouble).eps*score['cost_identity_roundoff_scale']+2e-12,rtol=0)
        return score
    def qualify(design,queries,query,score,arithmetic=False):
        v=np.stack([q[0] for q in queries]);jac=np.stack([q[1] for q in queries])
        check(np.all(np.isfinite(design)) and np.all(np.isfinite(v)) and np.all(np.isfinite(jac)),'finite design/query')
        qr=np.linalg.qr(design,mode='r');dr=v@design.T;rr=v@qr.T
        close(.5*np.sum(dr**2,axis=1),score['direct_approx_costs'],'direct rows cost')
        close(.5*np.sum(rr**2,axis=1),score['direct_approx_costs'],'QR cost')
        gd=np.einsum('qf,qfj->qj',dr@design,jac);gq=np.einsum('qf,qfj->qj',rr@qr,jac)
        close(gq,gd,'QR gradient versus direct')
        dj=design@jac[0];qj=qr@jac[0];close(qj.T@qj,dj.T@dj,'QR GN at public mean')
        merged=np.linalg.qr(np.vstack((np.linalg.qr(design[:17],mode='r'),np.linalg.qr(design[17:],mode='r'))),mode='r')
        mr=v@merged.T;mj=merged@jac[0]
        close(.5*np.sum(mr**2,axis=1),.5*np.sum(rr**2,axis=1),'merged QR cost')
        close(np.einsum('qf,qfj->qj',mr@merged,jac),gq,'merged QR gradient')
        close(mj.T@mj,qj.T@qj,'merged QR GN at public mean')
        for j in range(16):
            xp=h.mean.copy();xm=h.mean.copy();step=1e-5*h.sd[j];xp[j]+=step;xm[j]-=step
            fd=(query(xp)[0]-query(xm)[0])/(2*step);scaled=jac[0,:,j]*h.sd[j]
            close((fd*h.sd[j]-scaled)/np.maximum(1,abs(scaled)),0,'feature derivative '+str(j),atol=1e-5,rtol=0)
        if arithmetic:
            scales=np.linalg.norm(design,axis=0);scales=np.where(scales==0,1,scales)
            eq=np.linalg.qr(design/scales,mode='r')*scales
            er=v@eq.T;ge=np.einsum('qf,qfj->qj',er@eq,jac)
            stats=close(ge,gd,'equilibrated QR gradient versus direct')
            close(.5*np.sum(er**2,axis=1),score['direct_approx_costs'],'equilibrated QR cost')
            ej=eq@jac[0];close(ej.T@ej,dj.T@dj,'equilibrated QR GN')
            ratio=abs(gq-gd)/(2e-8+2e-10*abs(gd));witness=int(np.unravel_index(np.argmax(ratio),ratio.shape)[0]);extended=[]
            dld=design.astype(np.longdouble)
            for i in sorted({0,witness}):
                vv,jj=queries[i];reference=(dld@jj.astype(np.longdouble)).T@(dld@vv.astype(np.longdouble))
                extended.append(dict(query_index=ids[i],direct=close(gd[i],reference,'long-double direct gradient'),
                    raw_QR=close(gq[i],reference,'long-double raw QR gradient'),
                    equilibrated_QR=close(ge[i],reference,'long-double equilibrated QR gradient')))
            result['arithmetic'].append(dict(case=case,equilibrated_gradient=stats,extended=extended,
                scale_min=float(scales.min()),scale_max=float(scales.max()),optional_scaling_bytes=8*len(scales)))
        return qr
    def state_tests(bank,obs,dd):
        k=bank.k;errors=[]
        for mode in range(3):
            c=bank.pivots[mode];first=len(bank.keep)+2*mode*k;actual=-.001*dd[:,first:first+k]
            small=obs[:64].copy();zero=small.copy();zero[:,1]=0
            close(coeff(zero,c,k),np.zeros((64,k)),'zero-input forced coefficients')
            const=small.copy();const[:,1]=.23;t=np.cumsum(const[:,0]);expected=-.23*beta(t,c,k);expected[:,0]+=.23
            close(coeff(const,c,k),expected,'constant-input analytical step coefficients')
            for nn in [1,17,64]:
                elapsed=np.cumsum(obs[:nn,0]);lag=elapsed[-1]-np.r_[0.,elapsed[:-1]]
                delta=np.diff(np.r_[0.,obs[:nn,1]])
                independent=-(delta@beta(lag,c,k));independent[0]+=obs[nn-1,1]
                errors.append(float(np.max(abs(actual[nn-1]-independent))))
                close(actual[nn-1],independent,'independent current-step superposition')
            synthetic=np.array([[0.,.2,0.],[.013,-.3,0.],[.7,.1,0.],[0.,-.4,0.],[.019,.25,0.]])
            synthetic_f=coeff(synthetic,c,k);tm=np.cumsum(synthetic[:,0]);di=np.diff(np.r_[0.,synthetic[:,1]])
            for j in range(len(synthetic)):
                expected=-(di[:j+1]@beta(tm[j]-np.r_[0.,tm[:j]],c,k));expected[0]+=synthetic[j,1]
                close(synthetic_f[j],expected,'zero/uneven intervals and signed current')
            blocks=[]
            for lo,hi in [(0,17),(17,45),(45,len(obs))]:
                block=obs[lo:hi];blocks.append((beta(np.sum(block[:,0]),c,k),coeff(block,c,k)[-1]))
            work('coefficient_convolution_multiply_adds',8*k*(k+1)//2)
            left=compose(compose(blocks[0],blocks[1]),blocks[2]);right=compose(blocks[0],compose(blocks[1],blocks[2]))
            close(left[0],right[0],'affine merge associativity A');close(left[1],right[1],'affine merge associativity F')
            close(left[1],actual[-1],'chronological block endpoint versus single stream')
            close(left[0],beta(np.sum(obs[:,0]),c,k),'block attenuation versus elapsed time')
            close(coeff(obs[17:],c,k,actual[16]),actual[17:],'carried forced state across split')
        result['state_algebra'].append(dict(case=case,independent_superposition_max_abs_gap=max(errors)))
    try:
        h=Harness(binary);inp=json.loads(source.read_text());points=np.array(inp['queries']);rows=[]
        lower=np.array(inp['lower']);upper=np.array(inp['upper']);limits=[(upper[11]-1)*np.exp(lower[5]),lower[11]*np.exp(lower[5])]
        for raw in inp['raw_cycle']:
            row=np.zeros(3);check(h.lib.hp_decode(*raw,ptr(row))==0,'source decode');rows.append(row)
        rows=np.tile(rows,(inp['repeat_count'],1));prior=json.loads((FREE/'attempt001/receipt.json').read_text())
        save(out/'frozen_inputs.json',dict(source=identity(source),charge_domain_Ah=limits,queries=len(points)))
        for n in plan['fixed']['prefixes']:
            case=f'exact/{n}';obs=np.ascontiguousarray(rows[:n]);elapsed=np.cumsum(obs[:,0]);charges=np.cumsum(obs[:,0]*obs[:,1]/3600)
            work('model_node_steps',n*len(points));exact,offset,_,endpoints,meta=exact_trace(obs,points)
            reference=json.loads((FIXED/f'comparison002/reference_{n}.json').read_text())
            ec=.5*np.sum((exact.astype(np.longdouble).sum(axis=2)+offset.astype(np.longdouble))**2,axis=1)
            close(ec,reference['costs'],'original C cost');close(endpoints,reference['endpoints'],'original C endpoint')
            for domain in plan['fixed']['domains']:
                basis=ResponseBasis(dict(physical_RC=False,physical_hysteresis=True,tensor_hysteresis=False),domain,h.mean,h.sd,lower,upper)
                work('model_node_steps',n*65);full=basis.rows(obs);p=Partition(basis,12,limits)
                ids=[i for i,x in enumerate(points) if p.query(x) is not None];xx=points[ids]
                check(len(ids)==(97 if domain=='public_half_SD' else 129),'frozen query domain')
                base_parts,base_queries=approximate_parts(basis,p,full,obs,charges,xx)
                old=np.column_stack((dynamic_rows(basis,full,obs),p.charge_rows(charges)[:,:p.k]))
                configs=[('baseline',5),('free_only',9),('free_only',13)]+[(f,k) for f in plan['candidates']['families'] for k in plan['candidates']['K']]
                for family,k in configs:
                    case=f'{n}/{domain}/{family}/{k}';bounds=[]
                    if family=='baseline':bank=None;dd=old;queries=base_queries;query=p.query;approx=base_parts;memory=p.memory()
                    else:
                        if family=='free_only':
                            bank=FreeHistory(p,'time_kernel','all_three',k);work('carrier_values',3*n*k);dd=bank.rows(old,elapsed)
                        else:
                            bank=JointRC(p,family,k)
                            work('carrier_values',6*n*k)
                            if family=='time_kernel':work('coefficient_convolution_multiply_adds',3*n*k*(k+1)//2)
                            else:work('model_node_steps',3*n*k)
                            dd=bank.rows(old,obs)
                        query=bank.query;queries=[query(x) for x in xx];vv=np.stack([q[0] for q in queries])
                        approx=bank.replace_components(base_parts,dd,vv);memory=bank.memory()
                    score=score_parts(approx,exact[ids],offset[ids],ids)
                    qualify(dd,queries,query,score,arithmetic=n==4096 and (family=='baseline' or family=='time_kernel' and k in [9,13]))
                    for i in set(range(len(points)))-set(ids):check(query(points[i]) is None,'out-of-domain rejection')
                    if family in ['baseline','free_only'] or family=='log_tau_interpolation' and k==5:
                        pf='time_kernel' if family=='free_only' else 'baseline';pk=k if family=='free_only' else 5
                        oldcase=next(e for e in prior['arms'] if (e['records'],e['domain'],e['family'],e['coefficients'],e['scope'])==(n,domain,pf,pk,'all_three' if family=='free_only' else 'none'))
                        close(score['cost_gaps'],oldcase['score']['cost_gaps'],'reproduce predecessor')
                    if family=='time_kernel':
                        state_tests(bank,obs,dd)
                        tv=np.cumsum(abs(np.diff(np.r_[0.,obs[:,1]])));imax=np.maximum.accumulate(abs(obs[:,1]))
                        for mode in range(3):
                            rho=bank.rho[mode];r=(1+rho)/2
                            bound=np.minimum(tv*rho**k/(1-rho),imax*(1+r*r)/(1-r*r)*(rho/r)**k/(1-rho/r))
                            err=abs(approx[:,:,2*mode]-exact[ids,:,2*mode])*.001/abs(xx[:,7+mode,None])
                            check(np.all(err<=bound[None,:]+128*np.finfo(float).eps),'forced symbolic bound on sampled queries')
                            bounds.append(dict(mode=mode,terminal_variation_bound_A=float(tv[-1]*rho**k/(1-rho)),
                                uniform_Imax_bound_A=float(imax[-1]*(1+r*r)/(1-r*r)*(rho/r)**k/(1-rho/r)),
                                sampled_max_state_error_A=float(err.max())))
                    substitutions=[]
                    if family=='baseline':substitutions=[('exact_all_RC',list(range(6)))]
                    if family=='free_only' and k==13:substitutions=[('exact_forced',[0,2,4])]
                    if family in plan['candidates']['families'] and k==13:
                        substitutions=[('exact_free',[1,3,5]),('exact_forced',[0,2,4]),('exact_hysteresis',[6,7]),('exact_OCV',[8]),('exact_all_RC',list(range(6)))]
                    for label,components in substitutions:
                        trial=approx.copy();trial[:,:,components]=exact[ids][:,:,components]
                        result['raw_controls'].append(dict(case=case,substitution=label,score=score_parts(trial,exact[ids],offset[ids],ids)))
                    ep=np.stack([bank.endpoint(x,elapsed[-1]) if bank else basis.endpoint(x) for x in xx])
                    if family in plan['candidates']['families']:
                        # Same last forced row, but exact free endpoint, as declared.
                        expected=-.001*approx[:,-1,::2][:,:3]+xx[:,12:15]*np.exp(-elapsed[-1]/np.exp(xx[:,:3]))
                        close(ep[:,1:4],expected,'retained forced endpoint versus last row')
                    if (n,domain,family,k)==(4096,'public_half_SD','time_kernel',9):
                        synthetic=dd.copy();vv=queries[0][0];constant=int(np.flatnonzero(bank.keep==p.m-1)[0])
                        check(vv[constant]==1.,'unit observed-voltage feature');synthetic[:,constant]=0;synthetic[:,constant]=-(synthetic@vv)
                        dr=synthetic@vv;rr=np.linalg.qr(synthetic,mode='r')@vv
                        result['cancellation']=dict(direct_cost=float(dr@dr/2),QR_cost=float(rr@rr/2),clipped=False)
                        close(rr@rr/2,dr@dr/2,'zero-residual cancellation')
                    result['arms'].append(dict(records=n,domain=domain,family=family,coefficients=k,query_count=len(ids),score=score,
                        memory=memory,source=meta,forced_bounds=bounds,endpoint_error_by_coordinate=np.max(abs(ep-endpoints[ids]),axis=0).tolist()))
                    print(json.dumps(dict(case=case,error_NLL=score['error_oscillation_NLL'])),flush=True)
        check(len(result['arms'])==plan['primary_cases'],'all frozen cases completed')
        check(all(identity(ROOT/key)==value for key,value in bindings.items()),'bound source hashes unchanged')
        result['status']='completed_with_numerical_mismatches' if mismatches else 'numerical_controls_passed'
    except Exception:result['error']=traceback.format_exc()
    result.update(checks=checks,work=counts,numerical_mismatches=mismatches,wall_s=time.monotonic()-start)
    save(out/'receipt.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ['arms','raw_controls','arithmetic','state_algebra','numerical_mismatches']},indent=2),flush=True)
    print('numerical comparison flags:',len(mismatches),flush=True)
    return 0 if result['status']=='numerical_controls_passed' else 1


if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('usage: analyze.py EXCLUSIVE_OUTPUT_DIRECTORY')
    raise SystemExit(run(Path(sys.argv[1]).resolve()))
