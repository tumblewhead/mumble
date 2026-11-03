"""Finite algebra controls and a shared-kernel witness; no fits or kernel edits."""
import argparse
from fractions import Fraction
import json
from pathlib import Path
import numpy as np
from experiments.foster_campaign_001.backend import ROOT,identity
from experiments.h7_history_quality_001.history import write,source_receipt,verify_sources
from experiments.hysteresis_sensitivity_basis_001.run import field,verify
from experiments.rc_partition_repair_001.field import PartitionField
from experiments.rc_partition_repair_001.probe import projected,exact


def algebra():
    rng=np.random.default_rng(2718);errors=[]
    for _ in range(20):
        J=rng.normal(size=(15,4));E=.03*rng.normal(size=(15,4));r=rng.normal(size=15);e=.02*rng.normal(size=15)
        L=np.diag([1.,2.,3.,4.]);P=L+J.T@J;Ph=L+(J+E).T@(J+E)
        dg=J.T@e+E.T@r+E.T@e
        # Prior gradient -J.T r makes theta=0 stationary for the direct objective.
        direct_g=-J.T@r+J.T@r;approx_g=-J.T@r+(J+E).T@(r+e)
        errors.append(float(np.max(abs(approx_g-direct_g-dg))))
        dp=J.T@E+E.T@J+E.T@E;errors.append(float(np.max(abs(Ph-P-dp))))
        s,U=np.linalg.eigh(P);M=(U/s**.5)@U.T;W=(U*s**.5)@U.T
        A=M@dp@M;b=M@dg;delta=-np.linalg.solve(Ph,dg)
        errors.append(float(np.max(abs(W@delta+np.linalg.solve(np.eye(4)+A,b)))))
        eps=np.linalg.norm(A,2);assert eps<1
        assert np.linalg.norm(W@delta)<=np.linalg.norm(b)/(1-eps)+1e-12
        G=rng.normal(size=(3,4));dG=.02*rng.normal(size=(3,4));T=G@M;D=dG@M
        errors.append(float(np.max(abs((G+dG)@np.linalg.solve(Ph,(G+dG).T)-(T+D)@np.linalg.solve(np.eye(4)+A,(T+D).T)))))
        S=np.eye(4)+.1*rng.normal(size=(4,4));newg=S.T@dg;newP=S.T@P@S
        errors.append(float(abs(dg@np.linalg.solve(P,dg)-newg@np.linalg.solve(newP,newg))))
        errors.append(float(np.max(abs(G@np.linalg.solve(P,G.T)-(G@S)@np.linalg.solve(newP,(G@S).T)))))
        Hr=rng.normal(size=(15,4,4));Hr=(Hr+Hr.transpose(0,2,1))/2
        He=.03*rng.normal(size=(15,4,4));He=(He+He.transpose(0,2,1))/2
        H=P+np.einsum('i,ijk->jk',r,Hr)
        Hh=Ph+np.einsum('i,ijk->jk',r+e,Hr+He)
        predicted=dp+np.einsum('i,ijk->jk',e,Hr)+np.einsum('i,ijk->jk',r+e,He)
        errors.append(float(np.max(abs(Hh-H-predicted))))
    assert max(errors)<1e-11
    repeat=[]
    for n in [1,100,10000,1000000]:
        shift=Fraction(n,100*(n+4));z2=Fraction(n*n,10000*(n+4))
        repeat.append(dict(N=n,absolute_shift=float(shift),SD=1/np.sqrt(n+4),shift_in_SD=float(z2)**.5))
    A=np.ones((1,3));v=np.array([1.,-1.,0.]);assert np.array_equal(A@v,A@(-v));assert v@v==(-v)@(-v)
    values=[float(v@np.exp(-q*np.array([1.,2.,3.]))) for q in [.2,.7,1.3]]
    assert max(values)-min(values)>1e-3
    return dict(random_joint_controls=20,maximum_identity_defect=max(errors),
        coherent_repair_counterexample=dict(old_component_A=.1,unchanged_component_B=-.09,old_total=.01,new_component_A=0.,new_total=-.09),
        fixed_prior_repetition=repeat,linear_summary_ambiguity=dict(A=A,v=v,lambda_queries=[.2,.7,1.3],sum_v_exp=values),
        factor_B={str(w):4*w*(w+1) for w in [34,43]})


def witness():
    bindings={};directory=Path('experiments/rc_sensitivity_basis_001/full001')
    reg=json.loads((directory/'registration.json').read_text())
    verify(directory/'registration.json',identity(ROOT/'provenance/rc_sensitivity_basis_001/full001_registration.json'),bindings)
    verify(directory/'response_taylor2/response.so',reg['sensitivity_binaries']['taylor2'],bindings)
    hresult=json.loads((ROOT/'provenance/hysteresis_sensitivity_basis_001/result.json').read_text())
    hbins={k:Path('experiments/hysteresis_sensitivity_basis_001/build001')/k/'response.so' for k in ['collocation','derivative']}
    for k,b in hbins.items():verify(b,hresult['binaries'][k],bindings)
    run=Path('experiments/rc_partition_repair_001/run001')
    frozen=ROOT/'provenance/rc_partition_repair_001/result.json'
    frozen_result=json.loads(frozen.read_text());bindings[str(frozen)]=identity(frozen)
    verify(run/'registration.json',frozen_result['raw_bindings'][str(run/'registration.json')],bindings)
    preg=json.loads((run/'registration.json').read_text());verify_sources(preg['source'])
    for path,expected in preg['new_artifacts'].items():verify(Path(path),expected,bindings)
    for k in [2,5]:verify(run/('forced'+str(k))/'response.so',preg['new_binaries'][str(k)],bindings)
    fields={'Taylor2_both':field('TaylorRC_TaylorH2',reg,directory,'witness',hbins)}
    for name,forced in [('Free5_Forced2',2),('Collocation5_both',5)]:
        fields[name]=PartitionField(reg['config'],reg['center'],directory/'response_taylor2/response.so',hbins['derivative'],run/('forced'+str(forced))/'response.so',5,forced,'witness')
    k=np.arange(512);I=.12;R=np.array([.035,.07,.1]);obs=np.c_[np.array([0.,1/35,.1,.3])[k%4],np.full(512,I),np.full(512,25.),np.full(512,3.7),np.full(512,.001)]
    rows={name:f.rows(0,obs,'witness') for name,f in fields.items()};records=[]
    for t in [-.9,0.,.9]:
        true=exact(obs,np.array(reg['center'][:3])*np.exp(t))
        assert np.max(abs(true[:,2]-I*(1-true[:,0])))<1e-13
        record=dict(log_tau_offset=t,arms={})
        for name,f in fields.items():
            p=projected(f,rows[name],obs,t);C=p[:,2]-I*(1-p[:,0]);Ct=p[:,3]+I*p[:,1]
            # b=RI makes exact RC voltage independent of tau and elapsed duration.
            dv=p[:,0]*(R*I)+p[:,2]*R-R*I
            assert np.max(abs(dv-R*C))<1e-15
            record['arms'][name]=dict(max_complement_defect_A=float(np.max(abs(C))),
                max_complement_log_tau_slope_A=float(np.max(abs(Ct))),
                max_branch_equilibrium_defect_uV=float(1e6*np.max(abs(dv))),
                max_summed_equilibrium_defect_uV=float(1e6*np.max(abs(dv.sum(axis=1)))),
                max_branch_equilibrium_log_tau_slope_uV=float(1e6*np.max(abs(R*Ct))))
        for name in ['Taylor2_both','Collocation5_both']:
            assert record['arms'][name]['max_complement_defect_A']<1e-13
            assert record['arms'][name]['max_complement_log_tau_slope_A']<1e-13
        records.append(record)
    return dict(scope='Public constant-current equilibrium identity witness; not a fitted-run causal attribution or accuracy qualification',
        recipe=dict(records=512,dt=[0.,1/35,.1,.3],I_A=I,R_ohm=R,b_V=R*I,T_C=25.,offsets=[-.9,0.,.9]),bindings=bindings,records=records)


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    if args.out.exists():raise ValueError('preserve prior controls')
    sources=source_receipt();proofs={str(p):identity(p) for p in sorted((ROOT/'specifications/symbolic_fixed_budget_001').glob('*.md'))}
    result=dict(status='finite_controls_pass_no_estimator_change',source=sources,proofs=proofs,algebra=algebra(),kernel_witness=witness())
    verify_sources(sources)
    for p,e in proofs.items():assert identity(Path(p))==e,p
    write(args.out,result)


if __name__=='__main__':main()
