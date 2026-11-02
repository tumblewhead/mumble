"""Separate public mechanism probe: isolate RC values/slopes from unchanged H error."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from .basis import SensitivityField
from experiments.response_basis_attribution_001.basis import BasisField
from experiments.hysteresis_mixed_completion_001.rc_control import RC5Control
from experiments.foster_campaign_001.backend import ROOT,identity
from experiments.foster_feedback_001.estimator import Model
from experiments.foster_uncertainty_audit_001.conditional_packet import chart_from
from experiments.conditional_architecture_001.conditional import chart_amplitude_jacobian
from experiments.partitioned_coefficients_001.run import chart_shape_jacobian
from experiments.h7_history_quality_001.history import source_receipt,verify_sources,write


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--run',required=True,type=Path);p.add_argument('--out',required=True,type=Path);args=p.parse_args()
    if args.out.exists():raise ValueError('refuse overwrite')
    reg=json.loads((args.run/'registration.json').read_text());config=reg['config'];center=np.array(reg['center'])
    a=np.array(next(q for q in reg['queries'] if q['id']=='t0_a0')['a']);a[1:4]=[.004,-.002,.003]
    original=args.run/'response/response.so';direct=args.run/'backend_c/estimator.so'
    binaries={k:args.run/('response_'+k)/'response.so' for k in ['taylor2','hermite3']}
    for k,path in binaries.items():
        if identity(path)!=reg['sensitivity_binaries'][k]:raise ValueError('candidate binary changed')
    if identity(original)!=reg['response_binary'] or identity(direct)!=reg['direct_binary']:raise ValueError('control binary changed')
    fields={'R2_H2':BasisField(config,center,original),'Taylor2_H2':SensitivityField(config,center,binaries['taylor2'],'taylor2'),
            'Hermite3_H2':SensitivityField(config,center,binaries['hermite3'],'hermite3'),
            'R3_H2':SensitivityField(config,center,original,'chebyshev3'),'R5_H2':RC5Control(config,center,original,'td2')}
    k=np.arange(600);obs=np.c_[np.array([0.,1/35,1/50,.2,.8])[k%5],
        np.array([0.,.03,-.02,.012,-.025,0.])[(k//25)%6],np.full(600,25.),np.full(600,3.7),np.full(600,.001)]
    sources=source_receipt();rows={name:f.rows(0,obs) for name,f in fields.items()};model=Model(direct,config);records=[]
    for offset in [0.,-.35,.35,-1/np.sqrt(2),1/np.sqrt(2),-.9,.9]:
        shape=center.copy();shape[:3]*=np.exp(offset)
        _,J,_,_=model.evaluate(chart_from(a,shape),obs)
        directJ=J@np.column_stack((chart_amplitude_jacobian(a),chart_shape_jacobian(shape)))
        record=dict(common_log_tau_offset=offset,arms={})
        for name,f in fields.items():
            _,D,_=f.basis_query(a,shape);approx=(rows[name]@D)*obs[:,4,None]
            value=(approx[:,1:4]-directJ[:,1:4])*a[1:4]+(approx[:,6:9]-directJ[:,6:9])*a[6:9]
            slopes=approx[:,11:14]-directJ[:,11:14]
            record['arms'][name]=dict(max_branch_voltage_defect_mV=(1000*np.max(abs(value),axis=0)).tolist(),
                                      max_branch_log_tau_derivative_defect_mV=(1000*np.max(abs(slopes),axis=0)).tolist())
        records.append(record)
    # Mathematical identities are tests, not thresholds for battery performance.
    for key in ['max_branch_voltage_defect_mV','max_branch_log_tau_derivative_defect_mV']:
        if max(records[0]['arms']['Taylor2_H2'][key])>1e-9:raise ValueError('Taylor central identity')
        for index in [3,4]:
            if max(records[index]['arms']['Hermite3_H2'][key])>1e-9:raise ValueError('Hermite anchor identity')
    verify_sources(sources)
    write(args.out,dict(status='finite_mechanism_checks_pass',source=sources,run_registration=identity(args.run/'registration.json'),
        observations_sha256=hashlib.sha256(obs.astype('<f8').tobytes()).hexdigest(),records=600,duration_s=float(obs[:,0].sum()),
        public_boundary_RC_V=a[1:4],queries=records,
        scope='Outcome-informed public deterministic mechanism probe; no fitting/truth, no uniform-domain bound or independent confirmation'))


if __name__=='__main__':main()
