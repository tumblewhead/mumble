"""Untuned public response probes and explicit provisional resource live sets."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from .field import SharedField
from experiments.rc_partition_repair_001.probe import exact,projected
from experiments.hysteresis_sensitivity_basis_001.run import field,verify
from experiments.foster_campaign_001.backend import ROOT,identity
from experiments.h7_history_quality_001.history import write,source_receipt,verify_sources


def ledger():
    # An illustrative packed C layout, not allocations of an implemented port.
    persistent=dict(packed_likelihood=4760,response=312,centres=40,halfwidths=40,
        calibration=112,stream_count=8,assumed_source_digest=32,noise_normalizer=8,
        fixture_diagonal_prior_mean=128,fixture_diagonal_prior_scale=128,
        projection_p1=72,projection_p2=432,nodes=24,rate_cache=120)
    stream=dict(staged_factor=4760,staged_response=312,input_sample=40,QR_row=272)
    infer=dict(materialized_feature_Jacobian=34*16*8,packed_precision=16*17//2*8,
        gradient=128,trial_chart=128)
    p=sum(persistent.values());stream_peak=p+sum(stream.values());infer_peak=p+sum(infer.values())
    assert p==6216 and stream_peak==11600 and infer_peak==11912
    return dict(status='naive_packed_port_live_set_exceeds_target_before_full_stack',
        target_B=10240,persistent_components_B=persistent,persistent_subtotal_B=p,
        streaming_scratch_B=stream,streaming_subtotal_B=stream_peak,
        inference_scratch_B=infer,inference_subtotal_B=infer_peak,
        lifetime_rule='Streaming and inference phases assumed serialized; sums include persistent objects once. Do not add phase totals. Actual call lifetimes must be checked in a future port.',
        prior_scope='Only the frozen fixture prior is diagonal; full joint likelihood retained. A generic packed 16D prior root adds 960 B relative to the 128 B diagonal scale.',
        assumptions=['binary64 values and 8-byte count; illustrative 32-byte source digest',
            'immutable projection/rate tables charged to SRAM, no ROM savings assumed',
            'transaction stages a complete second factor and response',
            'inference materializes one 34x16 derivative matrix and packed16 precision'],
        exclusions=['alignment','stack frames and scalar temporaries','libm/QR/solve stack and additional work buffers','query output covariance','input queue/ISR','recovery and reset state','binding/registry metadata beyond listed digest','application state'],
        interpretation='These illustrative lower subtotal designs do not fit10KiB. Neither fixed factor size nor an unimplemented overwrite/workspace reuse plan qualifies full target memory. No target C port or WCET measurement in this study.')


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    if args.out.exists():raise ValueError('preserve probe')
    sources=source_receipt();bindings={};directory=Path('experiments/rc_sensitivity_basis_001/full001')
    reg=json.loads((directory/'registration.json').read_text())
    verify(directory/'registration.json',identity(ROOT/'provenance/rc_sensitivity_basis_001/full001_registration.json'),bindings)
    verify(directory/'response_taylor2/response.so',reg['sensitivity_binaries']['taylor2'],bindings)
    hs=json.loads((ROOT/'provenance/hysteresis_sensitivity_basis_001/result.json').read_text())
    hbins={k:Path('experiments/hysteresis_sensitivity_basis_001/build001')/k/'response.so' for k in ['collocation','derivative']}
    for k,b in hbins.items():verify(b,hs['binaries'][k],bindings)
    factory=lambda:SharedField(reg['config'],reg['center'],directory/'response_taylor2/response.so',hbins['derivative'],'probe')
    fields={'TaylorRC_TaylorH2':field('TaylorRC_TaylorH2',reg,directory,'probe',hbins),'CayleyRC_TaylorH2':factory()}
    k=np.arange(600);obs=np.c_[np.array([0.,1/35,.1,.3,.7])[k%5],np.array([.12,0.,-.08,.05,0.])[(k//19)%5],np.full(600,25.),np.full(600,3.7),np.full(600,.001)]
    rows={name:f.rows(0,obs,'probe') for name,f in fields.items()};b=np.array([.003,-.004,.002]);R=np.array([.035,.07,.1]);results=[]
    for t in [-1.,-.9,-.7,-.13,0.,.13,.7,.9,1.]:
        ref=exact(obs,np.array(reg['center'][:3])*np.exp(t));record=dict(log_tau_offset=t,arms={})
        for name,f in fields.items():
            s=2*np.tanh(t/2) if isinstance(f,SharedField) else t
            pred=projected(f,rows[name],obs,s)
            if isinstance(f,SharedField):pred[:,[1,3],:]*=1-np.tanh(t/2)**2
            delta=pred-ref
            values={label:float(np.max(abs(delta[:,idx,:]))) for label,idx in [('free_value',0),('free_log_tau_slope',1),('forced_value_A',2),('forced_log_tau_slope_A',3)]}
            values['max_total_RC_voltage_defect_uV']=float(1e6*np.max(abs(delta[:,0,:]@b+delta[:,2,:]@R)))
            values['max_sum_absolute_RC_log_tau_derivative_defects_uV']=float(1e6*np.max(np.sum(abs(delta[:,1,:]*b+delta[:,3,:]*R),axis=1)))
            record['arms'][name]=values
        results.append(record)
    # Constant-current identity for original offsets, separate from signed-current errors.
    o=obs.copy();o[:,1]=.12;f=factory();r=f.rows(0,o,'probe');eq=[]
    for t in [-1.,0.,1.]:
        w=np.tanh(t/2);pred=projected(f,r,o,2*w);pred[:,[1,3],:]*=1-w*w
        eq.append(dict(offset=t,complement_A=float(np.max(abs(pred[:,2]-.12*(1-pred[:,0])))),
            slope_complement_A=float(np.max(abs(pred[:,3]+.12*pred[:,1])))))
    assert max(max(v['complement_A'],v['slope_complement_A']) for v in eq)<1e-13
    q=2*np.tanh(.5);dose=1/q+.5;F=float(np.exp(-dose)*(1-(q+q*q/2)*dose+q*q*dose*dose/2));assert F<0
    verify_sources(sources)
    write(args.out,dict(scope='Untuned finite feasibility probes, not uniform error or complete device resources',source=sources,bindings=bindings,
        observation_sha256=hashlib.sha256(obs.astype('<f8').tobytes()).hexdigest(),
        recipe=dict(records=600,dt=[0.,1/35,.1,.3,.7],current_A=[.12,0.,-.08,.05,0.],current_hold_records=19,T_C=25.,b_V=b,R_ohm=R),
        results=results,equilibrium=eq,negative_free_witness=dict(log_tau_offset=-1.,dose_at_centre=dose,Fhat=F,exact_F=float(np.exp(-dose*np.e))),
        resources=ledger(),native_factor_storage={n:f.storage() for n,f in fields.items()}))


if __name__=='__main__':main()
