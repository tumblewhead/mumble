"""Public deterministic RC-only mechanism probes, separate from joint refits."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from numpy.polynomial.chebyshev import chebvander
from .field import PartitionField
from experiments.hysteresis_sensitivity_basis_001.run import field,verify
from experiments.foster_campaign_001.backend import ROOT,identity
from experiments.h7_history_quality_001.history import write,source_receipt,verify_sources


def exact(obs,tau):
    F=np.ones(3);Ft=np.zeros(3);u=np.zeros(3);ut=np.zeros(3);out=[]
    for dt,I,T,_,_ in obs:
        if T!=25:raise ValueError('stationary probe')
        dose=dt/tau;e=np.exp(-dose);e1=dose*e
        Ft,ut=e*Ft+e1*F,e*ut+e1*(u-I)
        F,u=e*F,e*u-np.expm1(-dose)*I
        out.append(np.array([F,Ft,u,ut]))
    return np.array(out)


def projected(f,rows,obs,t):
    T=chebvander(np.repeat(t,3),f.n-1);D=np.zeros_like(T);D[:,1]=1
    for k in range(2,f.n):D[:,k]=2*T[:,k-1]+2*t*D[:,k-1]-D[:,k-2]
    out=np.empty((len(obs),4,3));col=3;nu=getattr(f,'nu',f.n)
    for j in range(3):
        for size,value,derivative in [(f.n,0,1),(nu,2,3)]:
            coefficients=-rows[:,col:col+size]*obs[:,4,None];col+=size
            out[:,value,j]=coefficients@T[j,:size];out[:,derivative,j]=coefficients@D[j,:size]
    return out


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():raise ValueError('preserve existing probe')
    registration=json.loads((a.run/'registration.json').read_text());verify_sources(registration['source']);bindings={}
    for k in [2,5]:verify(a.run/('forced'+str(k))/'response.so',registration['new_binaries'][str(k)],bindings)
    directory=Path('experiments/rc_sensitivity_basis_001/full001');reg=json.loads((directory/'registration.json').read_text())
    verify(directory/'registration.json',identity(ROOT/'provenance/rc_sensitivity_basis_001/full001_registration.json'),bindings)
    verify(directory/'response_taylor2/response.so',reg['sensitivity_binaries']['taylor2'],bindings)
    hs=json.loads((ROOT/'provenance/hysteresis_sensitivity_basis_001/result.json').read_text())
    hbins={k:Path('experiments/hysteresis_sensitivity_basis_001/build001')/k/'response.so' for k in ['collocation','derivative']}
    for k,b in hbins.items():verify(b,hs['binaries'][k],bindings)
    fields={'TaylorRC_TaylorH2':field('TaylorRC_TaylorH2',reg,directory,'probe',hbins)}
    for name,degree,forced in [('Free3_Forced2_TaylorH2',3,2),('Free5_Forced2_TaylorH2',5,2),('RC5_TaylorH2',5,5)]:
        fields[name]=PartitionField(reg['config'],reg['center'],directory/'response_taylor2/response.so',hbins['derivative'],a.run/('forced'+str(forced))/'response.so',degree,forced,'probe')
    k=np.arange(600);obs=np.c_[np.array([0.,1/35,.1,.3,.7])[k%5],np.array([.12,0.,-.08,.05,0.])[(k//19)%5],np.full(600,25.),np.full(600,3.7),np.full(600,.001)]
    rows={name:f.rows(0,obs,'probe') for name,f in fields.items()};b=np.array([.003,-.004,.002]);R=np.array([.035,.07,.1]);records=[]
    for t in [-1.,-.9,-.7,-.13,0.,.13,.7,.9,1.]:
        ref=exact(obs,np.array(reg['center'][:3])*np.exp(t));record=dict(log_tau_offset=t,arms={})
        for name,f in fields.items():
            delta=projected(f,rows[name],obs,t)-ref
            values={label:float(np.max(abs(delta[:,idx,:]))) for label,idx in [('free_value',0),('free_log_tau_slope',1),('forced_value_A',2),('forced_log_tau_slope_A',3)]}
            values['max_total_RC_voltage_defect_uV']=float(1e6*np.max(abs(delta[:,0,:]@b+delta[:,2,:]@R)))
            values['max_sum_absolute_RC_log_tau_derivative_defects_uV']=float(1e6*np.max(np.sum(abs(delta[:,1,:]*b+delta[:,3,:]*R),axis=1)))
            record['arms'][name]=values
        records.append(record)
    sources=source_receipt();verify_sources(sources)
    write(a.out,dict(scope='Sampled public RC responses and log-tau slopes, no truth fitting or full-support certificate',
        source=sources,bindings=bindings,observations_sha256=hashlib.sha256(obs.astype('<f8').tobytes()).hexdigest(),
        recipe=dict(records=600,dt=[0.,1/35,.1,.3,.7],current_A=[.12,0.,-.08,.05,0.],current_hold_records=19,T_C=25.,b_V=b,R_ohm=R),results=records))


if __name__=='__main__':main()
