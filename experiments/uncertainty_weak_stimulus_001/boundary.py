"""Adaptive short diagnostic: weak-case narrowing after the last field refresh.

No truth access. Compare the same NEW suffix under (a) saved online rolling,
(b) one joint suffix fit using the same boundary Gaussian once, (c) original-
prior full-history field refreshed every16 observations. No prior/data overlap.
"""
import argparse
import json
from pathlib import Path
import time
import numpy as np
from experiments.foster_campaign_001.coordinates import prior
from experiments.foster_campaign_001.field_backend import transported
from experiments.foster_c_baseline_001.reference import Baseline,library
from experiments.foster_feedback_001.estimator import Model
from experiments.foster_uncertainty_audit_001.conditional_packet import partition
from experiments.joint_rate_history_001.field import Field,build
from experiments.slow_likelihood_diagnostic_001.numerics import Exact,Compressed,solve
from .diagnostics import CONVERGED,write,identity,endpoint,attempt_starts,fit_record


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--inputs',type=Path,required=True)
    p.add_argument('--original-inputs',type=Path,required=True)
    p.add_argument('--stage1',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();case=args.inputs
    reg=json.loads((case/'regeneration.json').read_text())
    old=json.loads((args.original_inputs/'regeneration.json').read_text())
    if reg['observations']!=old['observations'] or reg['messages']!=old['messages']:
        raise ValueError('boundary-export regeneration changed original evidence or endpoint')
    for name,key in [('observations.npy','observations'),('messages.npz','messages'),('last_refresh.npz','last_refresh')]:
        if identity(case/name)!=reg[key]:raise ValueError('changed regenerated artifact')
    r=json.loads((args.stage1/'result.json').read_text())
    if not r['status'].startswith('diagnostic_complete'):raise ValueError('Stage1 not frozen')
    cfg=json.loads((case/'calibration.json').read_text());run=Path(reg['source_case']).parent
    binary=run/'backend_c/estimator.so'
    obs=np.load(case/'observations.npy',mmap_mode='r')[:reg['fit_records']]
    first=reg['last_refresh_records'];suffix=obs[first:]
    state=dict(np.load(case/'last_refresh.npz'));initial=state['after']
    m=initial[:16];L=initial[16:272].reshape(16,16)
    args.out.mkdir(parents=True,exist_ok=False)
    write(args.out/'registration.json',dict(status='registered_before_comparison',trigger='Stage1 weak-case narrowing between accepted refresh and endpoint',
        prefix_records=first,suffix_records=len(suffix),suffix_seconds=float(obs[first:,0].sum()),
        source=identity(Path(__file__)),observations=reg['observations'],boundary_message=reg['last_refresh'],
        stage1=identity(args.stage1/'result.json'),starts=['boundary mean','signed slow offsets0.3'],
        numerical_continuation='If all60-round joint suffix fits unresolved, continue each returned state for up to240 rounds; retain both stages.',
        arms=['original16-record rolling','joint suffix MAP/GN with boundary Gaussian','full-history field every16 samples'],
        evidence_ownership='Gaussian boundary summarizes [0,first); suffix likelihood owns [first,end). Full-field arm uses original public prior once.',
        inference_truth_reads=0,production_changes=False))
    started=time.perf_counter();model=Model(binary,cfg)
    num=cfg['numerical'];bank=Baseline(library(binary),8,initial=(m,L),settings=dict(rounds=num['max_rounds'],
        fractions=num['fractions'],gradient_tol=num['gradient_inf_tolerance'],step_tol=num['latent_step_tolerance']))
    assert list(bank.c.cal)==model.cal.tolist()
    status,_=bank.replay(suffix)
    if status<0:raise ValueError('rolling suffix replay failed')
    rolling=bank.snapshot();saved=np.load(case/'messages.npz')['field64']
    parity=float(np.max(abs(rolling[:272]-saved[:272])))
    if parity!=0:raise ValueError(('rolling suffix reproduction differs',parity))
    joint=Exact(model,suffix,m,L)
    offset=np.zeros(16);offset[[5,13,14,15]]=[.3,-.3,.3,.3]
    best,starts=attempt_starts(joint,[('boundary_mean',np.zeros(16)),('offset',offset),('negative_offset',-offset)])
    continuations=[];eligible=[]
    if best is None:
        for previous in starts:
            if 'w' not in previous:continue
            fit=solve(joint,start=previous['w'],max_rounds=240)
            converged=fit['diagnostic']['stop'] in CONVERGED
            continuations.append(dict(start=previous['start'],status='converged' if converged else 'unresolved',**fit_record(fit)))
            if converged:eligible.append(fit)
        if eligible:best=min(eligible,key=lambda f:f['diagnostic']['cost'])
    result=dict(initial=endpoint(m,L),rolling=endpoint(rolling[:16],rolling[16:272].reshape(16,16)),
                rolling_saved_message_max_abs_difference=parity,joint_suffix=dict(starts=starts,continuations=continuations),
                original_prior_full_prefix_reference=r['exact']['endpoint'],
                original_prior_full_prefix_field=r['field']['native_endpoint'])
    if best is not None:
        _,_,_,end,F=joint(best['w'])
        result['joint_suffix'].update(selected=fit_record(best),endpoint=endpoint(end,F@best['root']))
    mean,root=prior(cfg);probe=build(args.out/'response_build')
    field=Field(cfg,partition(mean)[1],1.,5,probe)
    for i in range(0,first,4096):field.update(i,obs[i:min(i+4096,first)])
    obj=Compressed(field,mean,root);w=state['origin_w'];steps=[]
    for i in range(first,len(obs),16):
        field.update(i,obs[i:i+16]);fit=solve(obj,start=w)
        if fit['diagnostic']['stop'] not in CONVERGED:
            steps.append(dict(sequence=i+16,status='unresolved',diagnostic=fit['diagnostic']));break
        w=fit['w'];end,D=transported(field,fit['x']);outroot=D@fit['root']
        steps.append(dict(sequence=i+16,status='converged',Q_Ah=float(np.exp(end[5])),Q_log_sd=float(np.linalg.norm(outroot[5]))))
    result['field_every16']=dict(steps=steps,status='complete' if len(steps)==len(suffix)//16 and steps[-1]['status']=='converged' else 'unresolved')
    if result['field_every16']['status']=='complete':result['field_every16']['endpoint']=endpoint(end,outroot)
    result.update(wall_s=time.perf_counter()-started,inference_truth_reads=0,
        scope='Selected38.4-second weak-case suffix; diagnostic cadence, not production optimization or general coverage validation')
    write(args.out/'result.json',result)
    print('Boundary: '+str(args.out/'result.json'),flush=True)


if __name__=='__main__':main()
