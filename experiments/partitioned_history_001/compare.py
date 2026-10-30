"""Frozen partitioned-history comparison. No optimizer, truth or long trajectory."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
import ctypes as C
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback
import numpy as np
from partition import Partition,Basis,ocv,dynamic_rows

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
PREVIOUS=HERE.parent/'history_basis_comparison_001'
sys.path.insert(0,str(HERE.parent/'history_provider_001'))
from qualify import Harness,Result,DP,ptr,identity,save,SOURCES


def run(out):
    out.mkdir(parents=True,exist_ok=False)
    plan=json.loads((HERE/'plan.json').read_text());fixture=ROOT/plan['sources']['fixture']
    tracked=list(SOURCES)+list(HERE.glob('*.py'))+[HERE/'moments.c',HERE/'plan.json',
        PREVIOUS/'basis.py',PREVIOUS/'qr.c',HERE.parent/'history_provider_001/qualify.py',fixture,
        PREVIOUS/'comparison002/reference_64.json',PREVIOUS/'comparison002/reference_4096.json',
        PREVIOUS/'comparison002/receipt.json',HERE.parent/'live_anchor_integration_001/REPORT.md']
    for directory in [ROOT/'include',HERE.parent/'history_provider_001',HERE.parent/'live_anchor_integration_001',
                      HERE.parent/'live_anchor_bootstrap_001',HERE.parent/'compact_nonlinear_history_001']:
        tracked.extend(sorted(directory.glob('*.h')))
    sources={str(p.relative_to(ROOT)):identity(p) for p in tracked}
    for p in tracked:
        dest=out/'sources'/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    manuscript=Path(plan['sources']['manuscript'])
    if identity(manuscript)['sha256']!=plan['sources']['manuscript_sha256']:raise RuntimeError('manuscript identity')
    save(out/'reservation.json',dict(plan=plan,sources=sources,manuscript=identity(manuscript),command=sys.argv,
         revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
         branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip(),
         status='reserved_before_build_or_evaluation'))
    checks=0;steps=0;ocv_nodes=0;mismatches=[];arms=[];case='setup';start=time.monotonic()
    result=dict(status='failed',arms=arms,optimizer_calls=0,truth_reads=0,canonical_runs=0,
                solver_modified=False,aging_added=False,compressor_qualified=False)
    def check(condition,label):
        nonlocal checks
        checks+=1
        if not condition:raise AssertionError(case+': '+label)
    def close(a,b,label):
        nonlocal checks
        a=np.asarray(a);b=np.asarray(b)
        check(np.all(np.isfinite(a)) and np.all(np.isfinite(b)),label+' finite');checks+=1
        delta=abs(a-b);ratio=delta/(2e-8+2e-10*abs(b))
        if np.any(ratio>1):
            index=np.unravel_index(np.argmax(ratio),ratio.shape)
            mismatches.append(dict(case=case,label=label,max_absolute_gap=float(np.max(delta)),
                max_allowance_ratio=float(np.max(ratio)),worst_index=list(map(int,index)),
                actual=float(a[index]),reference=float(b[index])))
    def work(n):
        nonlocal steps
        check(steps+n<=plan['checks']['work_cap_model_steps_upper'],'pre-call model work cap');steps+=n
    def query(p,x):
        nonlocal ocv_nodes
        check(ocv_nodes+p.k<=plan['checks']['cap_OCV_node_evaluations'],'pre-query OCV-node cap')
        ocv_nodes+=p.k;return p.query(x)
    try:
        command=['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-pedantic','-fno-fast-math','-ffp-contract=off',
            '-shared','-fPIC','-I'+str(ROOT/'include'),*map(str,SOURCES),str(PREVIOUS/'qr.c'),str(HERE/'moments.c'),
            '-lm','-o',str(out/'provider.so')]
        build=subprocess.run(command,capture_output=True,text=True)
        save(out/'build.json',dict(command=command,returncode=build.returncode,stdout=build.stdout,stderr=build.stderr))
        check(build.returncode==0,'build');h=Harness(out/'provider.so');lib=h.lib
        lib.ph_append.argtypes=[DP,DP,DP,DP,DP,C.c_size_t,C.c_uint,C.c_uint]
        lib.hb_qr_append.argtypes=[DP,DP,C.c_size_t,C.c_uint]
        inp=json.loads(fixture.read_text());points=np.array(inp['queries'])
        lower=np.array(inp['lower']);upper=np.array(inp['upper']);rows=[]
        close(h.mean,inp['mean'],'frozen public mean');close(h.sd,inp['sd'],'frozen public SD')
        for raw in inp['raw_cycle']:
            row=np.zeros(3);check(lib.hp_decode(*raw,ptr(row))==0,'decode');rows.append(row)
        rows=np.tile(rows,(inp['repeat_count'],1))
        limits=[(upper[11]-1)*np.exp(lower[5]),lower[11]*np.exp(lower[5])]
        save(out/'frozen_inputs.json',dict(source=str(fixture.relative_to(ROOT)),identity=identity(fixture),
            charge_domain_Ah=limits,query_count=len(points),prefixes=plan['arms']['prefixes']))
        previous=json.loads((PREVIOUS/'comparison002/receipt.json').read_text())
        def moments(s,t,p,ends=None):
            g=np.zeros(p.m*(p.m+1)//2);b=np.zeros((p.m,p.k));mom=np.zeros(2*p.k-1);first=0
            for end in ends or [len(s)]:
                check(lib.ph_append(ptr(g),ptr(b),ptr(mom),ptr(s[first:end]),ptr(t[first:end]),end-first,p.m,p.k)==0,'moment append')
                first=end
            check(first==len(s),'source rows covered once')
            return g,b,mom,p.gram(g,b,mom)
        def qr(s):
            f=s.shape[1];packed=np.zeros(f*(f+1)//2)
            check(lib.hb_qr_append(ptr(packed),ptr(s),len(s),f)==0,'full QR append')
            r=np.zeros((f,f));r[np.triu_indices(f)]=packed;return r
        for n in plan['arms']['prefixes']:
            case=f'reference/{n}';obs=np.ascontiguousarray(rows[:n]);charges=np.cumsum(obs[:,0]*obs[:,1]/3600)
            ref=json.loads((PREVIOUS/f'comparison002/reference_{n}.json').read_text())
            costs=np.array(ref['costs']);grads=np.array(ref['gradients']);endpoints=np.array(ref['endpoints']);exact_gn=[]
            for i,x in enumerate(points):
                work(n);r=Result();check(lib.hp_exact_query(ptr(obs),n,ptr(x),C.byref(r))==0,'exact C query')
                close(r.likelihood,costs[i],'saved exact cost');close(r.gradient,grads[i],'saved exact gradient');close(r.endpoint,endpoints[i],'saved endpoint')
                gn=np.zeros((16,16));gn[np.tril_indices(16)]=r.gn_packed;gn=gn+np.tril(gn,-1).T;exact_gn.append(gn)
            check(limits[0]<=np.min(charges)<=np.max(charges)<=limits[1],'entire charge prefix within fixed domain')
            for d in plan['arms']['dynamic_degrees']:
                for domain in plan['arms']['domains']:
                    case=f'{n}/d{d}/{domain}'
                    basis=Basis('log_chebyshev',d,domain,h.mean,h.sd,lower,upper)
                    work(n*(3*basis.m+2*basis.m*basis.m));full=basis.rows(obs);s=dynamic_rows(basis,full,obs)
                    ids=[i for i,x in enumerate(points) if basis.features(x) is not None]
                    fp=np.stack([basis.features(points[i])[0] for i in ids]);uniform=.5*np.sum((fp@full.T)**2,axis=1)
                    old=next((a for a in previous['arms'] if a['records']==n and a['degree']==d and a['domain']==domain and a['family']=='log_chebyshev'),None)
                    if old:close(uniform,np.array(old['cost_gaps'])+costs[ids],'uniform predecessor parity')
                    exact_u=ocv(points[ids,11,None]-np.exp(-points[ids,5,None])*charges[None,:])/.001
                    for q in plan['arms']['OCV_charge_degrees']:
                        case=f'{n}/d{d}/q{q}/{domain}';began=time.monotonic();p=Partition(basis,q,limits);t=p.charge_rows(charges)
                        check(t is not None,'charge availability');check(p.charge_rows([limits[0]-1e-9]) is None,'charge exit unavailable')
                        results=[query(p,points[i]) for i in ids];check(all(v is not None for v in results),'query availability')
                        v=np.stack([z[0] for z in results]);j=np.stack([z[1] for z in results])
                        for i in set(range(len(points)))-set(ids):check(query(p,points[i]) is None,'parameter exit unavailable')
                        g,b,mom,gram=moments(s,t,p);combined=np.ascontiguousarray(np.column_stack((s,t[:,:p.k])))
                        reference_r=qr(combined);rp=v@reference_r.T;qr_cost=.5*np.sum(rp**2,axis=1)
                        qr_gradient=np.einsum('nf,nfj->nj',rp@reference_r,j)
                        raw=v@combined.T;direct_cost=.5*np.sum(raw**2,axis=1)
                        cost=.5*np.einsum('nf,nf->n',v@gram,v);gradient=np.einsum('nf,nfj->nj',v@gram,j)
                        close(qr_cost,direct_cost,'QR versus direct residual cost')
                        close(cost,direct_cost,'partition versus direct residual cost')
                        close(gradient,np.einsum('nf,nfj->nj',raw@combined,j),'partition versus direct gradient')
                        close(gradient,qr_gradient,'partition versus QR gradient')
                        direct_j=combined@j[0];metric=j[0].T@gram@j[0];qr_j=reference_r@j[0]
                        close(metric,direct_j.T@direct_j,'partition GN versus direct Jacobian')
                        close(metric,qr_j.T@qr_j,'partition GN versus QR')
                        for aa,bb in zip((g,b,mom),moments(s,t,p,[17,n])[:3]):close(aa,bb,'same-order partition append')
                        left=moments(s[:17],t[:17],p);right=moments(s[17:],t[17:],p)
                        for aa,bb,cc in zip((g,b,mom),left[:3],right[:3]):close(aa,bb+cc,'global-coordinate block addition')
                        eig=np.linalg.eigvalsh(gram);norm=float(np.max(abs(eig)));allowance=128*np.finfo(float).eps*len(gram)*norm
                        psd_ok=bool(eig[0]>=-allowance)
                        if not psd_ok:mismatches.append(dict(case=case,label='PSD roundoff allowance',minimum_eigenvalue=float(eig[0]),allowance=allowance))
                        check(np.all(np.isfinite(eig)),'finite Gram spectrum')
                        # Analytic query derivatives checked without differentiating data/history.
                        for k in range(16):
                            xp=h.mean.copy();xm=h.mean.copy();step=1e-5*h.sd[k];xp[k]+=step;xm[k]-=step
                            vp=query(p,xp)[0];vm=query(p,xm)[0]
                            finite=(vp-vm)/(2*step)
                            check(np.all(abs(finite-j[0,:,k])*h.sd[k]<=1e-5*np.maximum(1,abs(j[0,:,k])*h.sd[k])),
                                  'analytic feature derivative')
                        approx_u=v[:,p.m:]@t[:,:p.k].T;ocv_gap=(approx_u-exact_u)*.001
                        oracle_residual=v[:,:p.m]@s.T+exact_u;oracle=.5*np.sum(oracle_residual**2,axis=1)
                        endpoint=np.stack([basis.endpoint(points[i]) for i in ids])
                        groups={}
                        for name,lo,hi in [('axis',0,33),('joint_local',33,97),('global',97,129),('all_available',0,129)]:
                            sel=[k for k,i in enumerate(ids) if lo<=i<hi];groups[name]=dict(available=len(sel),requested=hi-lo)
                            if sel:
                                gap=cost[sel]-costs[np.array(ids)[sel]];qgap=qr_cost[sel]-costs[np.array(ids)[sel]]
                                groups[name].update(error_oscillation_NLL=float(np.ptp(gap)),QR_error_oscillation_NLL=float(np.ptp(qgap)),
                                    uniform_error_oscillation_NLL=float(np.ptp(uniform[sel]-costs[np.array(ids)[sel]])),
                                    exact_OCV_dynamic_basis_error_oscillation_NLL=float(np.ptp(oracle[sel]-costs[np.array(ids)[sel]])),
                                    max_OCV_voltage_error_V=float(np.max(abs(ocv_gap[sel]))),
                                    max_scaled_gradient_error=float(np.max(abs(gradient[sel]-grads[np.array(ids)[sel]])*h.sd)),
                                    max_endpoint_error_by_coordinate=np.max(abs(endpoint[sel]-endpoints[np.array(ids)[sel]]),axis=0).tolist(),
                                    finite_cost_gate_pass=bool(np.ptp(gap)<=.1))
                        arm=dict(records=n,dynamic_degree=d,OCV_charge_degree=q,domain=domain,available_indices=ids,
                            groups=groups,memory=p.memory(),minimum_Gram_eigenvalue=float(eig[0]),PSD_allowance=allowance,
                            PSD_roundoff_check_pass=psd_ok,max_moment_QR_cost_gap_NLL=float(np.max(abs(cost-qr_cost))),
                            mean_max_scaled_GN_error=float(np.max(abs(metric-exact_gn[0])*h.sd[:,None]*h.sd[None,:])),
                            cost_gaps=(cost-costs[ids]).tolist(),wall_s=time.monotonic()-began)
                        arms.append(arm)
                        if (n,d,q,domain)==(4096,2,8,'full_public'):
                            # Pure arithmetic control: cancel the represented residual at public mean.
                            null=s.copy();null[:,-1]=-(null[:,:-1]@v[0,:p.m-1]+t[:,:p.k]@v[0,p.m:])
                            _,_,_,nullgram=moments(null,t,p)
                            nullrows=np.ascontiguousarray(np.column_stack((null,t[:,:p.k])))
                            nullr=qr(nullrows);exact_null=nullrows@v[0]
                            null_cost=float(.5*v[0]@nullgram@v[0]);null_ref=float(.5*exact_null@exact_null)
                            close(null_cost,null_ref,'zero-residual cancellation control')
                            result['cancellation_control']=dict(moment_cost_NLL=null_cost,direct_cost_NLL=null_ref,
                                QR_cost_NLL=float(.5*np.sum((nullr@v[0])**2)),scope='Constructed represented-row arithmetic only; no battery inference.')
                        print(json.dumps({k:arm[k] for k in ['records','dynamic_degree','OCV_charge_degree','domain']}
                            |dict(oscillation=groups['all_available']['error_oscillation_NLL'],planned_B=p.memory()['moment_planned_subsystem_B'])),flush=True)
        check(all(identity(ROOT/name)==value for name,value in sources.items()),'sources unchanged')
        result.update(status='completed_with_numerical_mismatches' if mismatches else 'numerical_controls_passed',
            complete_SRAM_qualified=False,uncertainty_qualified=False,elapsed_seconds=[float(rows[:n,0].sum()) for n in plan['arms']['prefixes']])
    except Exception:result['error']=traceback.format_exc()
    result.update(checks=checks,model_steps_upper=steps,OCV_node_evaluations_upper=ocv_nodes,numerical_mismatches=mismatches,wall_s=time.monotonic()-start)
    save(out/'receipt.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ['arms','numerical_mismatches']}
          |dict(numerical_mismatch_count=len(mismatches)),indent=2),flush=True)
    return 0 if result['status']=='numerical_controls_passed' else 1


if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('usage: compare.py EXCLUSIVE_OUTPUT_DIRECTORY')
    raise SystemExit(run(Path(sys.argv[1]).resolve()))
