"""Post-comparison attribution; candidates and gates remain frozen."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
import ctypes as C
import json
from pathlib import Path
import shutil
import sys
import time
import traceback
import numpy as np
from basis import Basis
from compare import ROOT,HERE,Harness,Result,DP,ptr,identity,save


def run(out):
    out.mkdir(parents=True,exist_ok=False)
    source=HERE/'comparison002';plan=json.loads((HERE/'diagnostic_plan.json').read_text())
    binding=[HERE/'diagnostic_plan.json',HERE/'diagnose.py',HERE/'basis.py',HERE/'compare.py',
             HERE.parent/'history_provider_001/qualify.py',source/'provider.so',source/'receipt.json',source/'frozen_inputs.json',
             source/'reference_64.json',source/'reference_4096.json']
    hashes={str(p.relative_to(ROOT)):identity(p) for p in binding}
    for p in binding:
        dest=out/'sources'/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    save(out/'reservation.json',dict(plan=plan,sources=hashes,command=sys.argv))
    result=dict(status='failed',arms=[]);steps=0;start=time.monotonic()
    def work(n):
        nonlocal steps
        if steps+n+plan['prior_model_steps_upper']>plan['aggregate_model_step_cap_including_comparisons']:
            raise RuntimeError('aggregate pre-call work cap')
        steps+=n
    try:
        inp=json.loads((source/'frozen_inputs.json').read_text());comparison=json.loads((source/'receipt.json').read_text())
        x=np.array(inp['queries']);h=Harness(source/'provider.so');lib=h.lib
        lib.hb_qr_append.argtypes=[DP,DP,C.c_size_t,C.c_uint]
        rows=[]
        for raw in inp['raw_cycle']:
            row=np.zeros(3)
            if lib.hp_decode(*raw,ptr(row)):raise RuntimeError('decode')
            rows.append(row)
        rows=np.tile(rows,(64,1))
        for n in [64,4096]:
            obs=np.ascontiguousarray(rows[:n]);work(n*len(x))
            # Exact physical contribution trajectories, independently constructed.
            parts=np.zeros((len(x),n,7));tau=np.exp(x[:,:3]);f=np.zeros_like(tau);a=np.ones_like(tau)
            hb=np.zeros(len(x));ha=np.ones(len(x));charge=0
            for k,(dt,current,voltage) in enumerate(obs):
                e=np.exp(-dt/tau);f=e*f-np.expm1(-dt/tau)*current;a=e*a
                if current and dt:
                    q=np.exp(x[:,3 if current>0 else 4])*abs(current)*dt/3600
                    e=np.exp(-q);hb=e*hb-np.expm1(-q)*np.sign(current);ha=e*ha
                charge+=current*dt/3600;z=x[:,11]-charge/np.exp(x[:,5])
                parts[:,k,:3]=-(x[:,7:10]*f+x[:,12:15]*a)
                parts[:,k,3]=-x[:,10]*hb;parts[:,k,4]=-x[:,10]*x[:,15]*ha
                parts[:,k,5]=3+1.15*z+.08*np.tanh(8*(z-.5))-voltage
                parts[:,k,6]=-current*x[:,6]
            exact_residual=parts.sum(axis=2)/.001
            ref=json.loads((source/f'reference_{n}.json').read_text())
            if not np.allclose(.5*np.sum(exact_residual**2,axis=1),ref['costs'],rtol=2e-10,atol=2e-8):
                raise AssertionError('independent component sum versus C')
            for arm in [v for v in comparison['arms'] if v['records']==n]:
                b=Basis(arm['family'],arm['degree'],arm['domain'],h.mean,h.sd,np.array(inp['lower']),np.array(inp['upper']))
                work(n*(3*b.m+2*b.m*b.m));d=b.rows(obs);ids=arm['available_indices']
                phi=np.stack([b.features(x[i])[0] for i in ids]);approx=np.zeros((len(ids),n,7))
                m=b.m;p=len(b.pairs);ends=[0,2*m,4*m,6*m,6*m+p,6*m+2*p,6*m+3*p,b.dim]
                for j in range(7):approx[:,:,j]=phi[:,ends[j]:ends[j+1]]@d[:,ends[j]:ends[j+1]].T
                delta=approx-parts[ids]/.001;total=delta.sum(axis=2)
                attribution=np.sum(delta*(exact_residual[ids]+total/2)[:,:,None],axis=1)
                if not np.allclose(attribution.sum(axis=1),arm['cost_gaps'],rtol=2e-7,atol=2e-5):
                    raise AssertionError('attribution identity versus saved QR cost gaps')
                groups={}
                for label,selected in [('axis',list(range(33))),('all_available',list(range(len(ids))))]:
                    groups[label]=dict(peak_voltage_gap_by_component_V=(np.max(abs(delta[selected]),axis=(0,1))*.001).tolist(),
                        RMS_voltage_gap_by_component_V=(np.sqrt(np.mean(delta[selected]**2,axis=(0,1)))*.001).tolist(),
                        signed_cost_contribution_oscillation_by_component_NLL=np.ptp(attribution[selected],axis=0).tolist())
                result['arms'].append({k:arm[k] for k in ['records','family','degree','domain']} | {'groups':groups})
                if (n,arm['family'],arm['degree'],arm['domain'])==(4096,'log_chebyshev',4,'full_public'):
                    # Recorded index (73,6): cancellation in the R0 gradient.
                    p73,j73=b.features(x[73]);packed=np.zeros(b.dim*(b.dim+1)//2)
                    if lib.hb_qr_append(ptr(packed),ptr(d),len(d),b.dim):raise RuntimeError('QR')
                    r=np.zeros((b.dim,b.dim));r[np.triu_indices(b.dim)]=packed
                    ld=np.longdouble;dl=d.astype(ld);pl=p73.astype(ld);jl=j73[:,6].astype(ld)
                    terms=(dl@pl)*(dl@jl);gld=terms.sum(dtype=ld)
                    qrld=((r.astype(ld)@pl)*(r.astype(ld)@jl)).sum(dtype=ld)
                    result['gradient_diagnostic']=dict(query=73,coordinate=6,
                        long_double_mantissa_bits=np.finfo(ld).nmant,direct_long_double=float(gld),
                        QR_factor_long_double_evaluation=float(qrld),QR_factor_gap=float(qrld-gld),
                        cancellation_ratio=float(np.sum(abs(terms),dtype=ld)/abs(gld)),
                        original_mismatch=comparison['numerical_mismatches'][0],
                        gate_changed=False,interpretation='Distinguishes accumulation cancellation from representation error; does not waive frozen failure.')
            if n==4096:
                gaps=[];state_gaps=[]
                for i in range(33):
                    first=Result();second=Result();work(n)
                    if lib.hp_exact_query(ptr(obs[:17]),17,ptr(x[i]),C.byref(first)):raise RuntimeError('first block')
                    next_x=x[i].copy();next_x[11]=first.endpoint[0];next_x[12:15]=first.endpoint[1:4];next_x[15]=first.endpoint[4]
                    if lib.hp_exact_query(ptr(obs[17:]),n-17,ptr(next_x),C.byref(second)):raise RuntimeError('second block')
                    gaps.append(first.likelihood+second.likelihood-ref['costs'][i])
                    state_gaps.append(np.array(second.endpoint)-ref['endpoints'][i])
                result['exact_composition']=dict(queries=33,partition=[17,4079],
                    max_cost_gap_NLL=float(np.max(abs(np.array(gaps)))),max_endpoint_gap_by_coordinate=np.max(np.abs(state_gaps),axis=0).tolist(),
                    passed=bool(np.allclose(np.array(ref['costs'][:33])+gaps,ref['costs'][:33],rtol=2e-10,atol=2e-8)
                                and np.allclose(state_gaps,0,rtol=2e-10,atol=2e-8)),
                    scope='Exact physical two-block control; not closure of the finite candidate bases.')
        if not all(identity(ROOT/name)==value for name,value in hashes.items()):raise AssertionError('source changed')
        result.update(status='completed',component_order=['RC1','RC2','RC3','forced_hysteresis','free_hysteresis','OCV_minus_observed','ohmic'],
            gate_status='Original comparison failures preserved; no new candidate pass.')
    except Exception:result['error']=traceback.format_exc()
    result.update(model_steps_upper=steps,aggregate_model_steps_upper=steps+plan['prior_model_steps_upper'],wall_s=time.monotonic()-start)
    save(out/'receipt.json',result);print(json.dumps({k:v for k,v in result.items() if k!='arms'},indent=2))
    return 0 if result['status']=='completed' else 1


if __name__=='__main__':raise SystemExit(run(Path(sys.argv[1]).resolve()))
