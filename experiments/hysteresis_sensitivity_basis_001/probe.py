"""Public two-rate locality probe; no fitting, recentering or hidden truth."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import numpy as np
from numpy.polynomial.chebyshev import chebder,chebval
from .run import ARMS,field
from .reference import jet,INDICES,envelope
from experiments.foster_campaign_001.backend import ROOT,identity
from experiments.foster_feedback_001.estimator import Model
from experiments.foster_uncertainty_audit_001.conditional_packet import chart_from
from experiments.joint_precision_attribution_001.metrics import coordinates
from experiments.hysteresis_refinement_001.field import features_jacobian,transported
from experiments.h7_history_quality_001.history import source_receipt,verify_sources,write


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--build-dir',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--study',type=Path,required=True);args=p.parse_args()
    if args.out.exists():raise ValueError('refuse overwrite')
    study=json.loads(args.study.read_text())
    binaries={k:args.build_dir/k/'response.so' for k in ['collocation','derivative']}
    for k,path in binaries.items():
        if identity(path)!=study['binaries'][k]:raise ValueError('H binary changed')
    directory=Path('experiments/rc_sensitivity_basis_001/full001')
    rp=directory/'registration.json';reg=json.loads(rp.read_text())
    if identity(rp)!=identity(ROOT/'provenance/rc_sensitivity_basis_001/full001_registration.json'):
        raise ValueError('frozen registration changed')
    for path,expected in [(directory/'backend_c/estimator.so',reg['direct_binary']),
                          (directory/'response/response.so',reg['response_binary']),
                          (directory/'response_taylor2/response.so',reg['sensitivity_binaries']['taylor2'])]:
        if identity(path)!=expected:raise ValueError('frozen binary changed')
    model=Model(directory/'backend_c/estimator.so',reg['config'])
    a,s,_,_=coordinates(np.array(reg['prior_mean']),np.array(reg['prior_root']));a[10]=.002
    k=np.arange(512)
    obs=np.c_[np.array([0.,1/35,.2,1.])[k%4],np.array([0.,.12,-.08,.2,-.18])[(k//11)%5],
              np.full(512,25.),np.full(512,3.7),np.full(512,.001)]
    fields={name:field(name,reg,directory,'public_probe',binaries) for name in ARMS}
    rows={name:f.rows(0,obs) for name,f in fields.items()}
    queries=list(itertools.product([-.9,0.,.9],repeat=2))+[(.35,0.),(-.35,0.),(0.,.35),(0.,-.35),(.35,-.35),(-.35,.35)]
    sources=source_receipt();records=[]
    for t in queries:
        shape=s.copy();shape[3:]*=np.exp(t);x=chart_from(a,shape)
        _,_,B,_=coordinates(x,np.array(reg['prior_root']))
        _,J,_,_=model.evaluate(x,obs);Jc=(J@B)/obs[:,4,None]
        ref=jet(obs,shape[3:]);mixed=a[10]*ref[:,0,INDICES.index((1,1))]+a[9]*ref[:,1,INDICES.index((1,1))]
        b,vbound=envelope(a,shape,reg['center']);record=dict(log_rate_offsets=list(t),arms={})
        for name,f in fields.items():
            diff=(rows[name]@features_jacobian(f,x)@B-Jc)*obs[:,4,None]
            hv=diff[:,9:11]@a[9:11]
            derivatives=np.array([[chebval(ti,chebder(np.eye(f.m)[i])) for i in range(f.m)] for ti in t])
            hm=np.array([derivatives[0,i]*derivatives[1,j] for i,j in f.pairs])
            start=3+6*f.n
            approx_mixed=(a[9]*rows[name][:,start:start+f.b]+a[10]*rows[name][:,start+f.b:start+2*f.b])@hm*obs[:,4]
            item=dict(max_voltage_error_V=float(max(abs(hv))),
                max_log_rate_derivative_error_V=np.max(abs(diff[:,14:16]),axis=0),
                max_amplitude_derivative_error=np.max(abs(diff[:,9:11]),axis=0),
                max_mixed_log_rate_derivative_error_V=float(max(abs(approx_mixed-mixed))))
            try:
                end,_=transported(f,x);item['endpoint_transport']=dict(status='supported',h=float(np.tanh(end[4])))
            except ValueError as error:
                item['endpoint_transport']=dict(status='unsupported',reason=str(error))
            if name=='TaylorRC_TaylorH2':
                if item['max_voltage_error_V']>vbound+1e-10 or np.any(item['max_log_rate_derivative_error_V']>b[14:16]+1e-10):
                    raise AssertionError('H6 public probe consistency')
                if t==(0.,0.) and max(item['max_voltage_error_V'],max(item['max_log_rate_derivative_error_V']),item['max_mixed_log_rate_derivative_error_V'])>1e-9:
                    raise AssertionError('central value/gradient/mixed identity')
                item['H6']=dict(voltage_bound_V=float(vbound),log_rate_derivative_bounds_V=b[14:16])
            record['arms'][name]=item
        records.append(record)
    verify_sources(sources)
    write(args.out,dict(status='completed_public_locality_probe',source=sources,
        study=identity(args.study),frozen_registration=identity(rp),binaries={k:identity(v) for k,v in binaries.items()},
        observation_sha256=hashlib.sha256(obs.astype('<f8').tobytes()).hexdigest(),records=512,
        duration_s=float(sum(obs[:,0])),public_amplitude=a,queries=records,
        scope='Public artificial chronological inputs; finite locality and central-identity diagnostics, not independent population confirmation or fitted accuracy'))


if __name__=='__main__':main()
