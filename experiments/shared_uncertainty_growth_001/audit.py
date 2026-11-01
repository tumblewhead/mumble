"""Matched full-prefix likelihood audit. Never opens scenario or scoring files."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
from experiments.foster_campaign_001.coordinates import prior
from experiments.foster_campaign_001.field_backend import transported
from experiments.foster_feedback_001.estimator import Model
from experiments.foster_uncertainty_audit_001.conditional_packet import partition
from experiments.joint_rate_history_001.field import Field
from experiments.slow_likelihood_diagnostic_001.numerics import Exact,Compressed,solve
from experiments.uncertainty_weak_stimulus_001.diagnostics import (CONVERGED,Parts,build_parts,write,identity,fit_record,partition_audit)


def require_identity(path,expected):
    if identity(path)!=expected:raise ValueError('changed input: '+str(path))


def load_inputs(path,n):
    validated=json.loads((path/'validated.json').read_text())
    if validated['status']!='validated':raise ValueError('unvalidated observations')
    require_identity(path/'observations.npy',validated['observations'])
    require_identity(path/'calibration.json',validated['calibration'])
    entry=json.loads((path/f'prefix_{n}.json').read_text())
    if entry['sequence']!=n or n not in [e['sequence'] for e in validated['selected']]:raise ValueError('prefix mismatch')
    require_identity(path/f'field_{n}.npz',entry['field'])
    for key in ('model','field_binary'):
        filename=entry['model_binary'] if key=='model' else entry[key]
        expected=entry['model_identity'] if key=='model' else entry[key+'_identity']
        require_identity(Path(filename),expected)
    cfg=json.loads((path/'calibration.json').read_text());mean,L=prior(cfg)
    field=Field(cfg,partition(mean)[1],1.,5,entry['field_binary'])
    with np.load(path/f'field_{n}.npz',allow_pickle=False) as f:
        meta=json.loads(f['metadata'].tobytes())
        if meta['count']!=n or len(f['pending']):raise ValueError('unflushed or wrong field prefix')
        field.root=f['root'].copy();field.state=f['state'].copy();field.count=n;field.noise=meta['noise'];w=f['w'].copy()
    obs=np.load(path/'observations.npy',mmap_mode='r')
    if len(obs)<n or obs.shape[1]!=5:raise ValueError('observation shape')
    return cfg,mean,L,field,w,obs[:n],entry


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--inputs',type=Path,required=True);p.add_argument('--sequence',type=int,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();cfg,mean,L,field,w,obs,entry=load_inputs(a.inputs,a.sequence)
    out=a.out;out.mkdir(parents=True,exist_ok=False);began=time.perf_counter()
    row=dict(status='running',sequence=a.sequence,hours=entry['hours'],input_prefix=entry,
        observations=identity(a.inputs/'observations.npy'),command=sys.argv,
        source_revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        inference_truth_reads=0,original_prior_once=True,
        scope='local full-prefix MAP/GN comparison; no global posterior or coverage claim')
    def save(stage):
        row['stage']=stage;row['wall_s']=time.perf_counter()-began;write(out/'result.json',row)
        print(json.dumps(dict(stage=stage,hours=entry['hours'],wall_s=row['wall_s'])),flush=True)
    obj=Compressed(field,mean,L);model=Model(Path(entry['model_binary']),cfg);exact=Exact(model,obs,mean,L)
    save('field_fit')
    fit=solve(obj,start=w);row['field']=fit_record(fit)
    if fit['diagnostic']['stop'] not in CONVERGED:
        row['status']='field_fit_unresolved';save('finished');return
    save('exact_at_field')
    c,g,P,end,F=exact(fit['w']);fc,fg,fP,_,_=obj(fit['w'])
    correction=-np.linalg.solve(P,g)
    eroot=L@np.linalg.solve(np.linalg.cholesky(P).T,np.eye(16));sd=np.linalg.norm(eroot[5])
    native,D=transported(field,fit['x'])
    row['anchor']=dict(exact_cost=c,field_cost=fc,exact_gradient=g,field_gradient=fg,
        predicted_Q_correction_percent=float(100*np.expm1(L[5]@correction)),
        predicted_Q_correction_local_SD=float(L[5]@correction/sd),Q_log_SD=sd,
        Q_width_ratio_field_exact=float(np.linalg.norm(fit['root'][5])/sd),
        native_minus_exact_endpoint=native-end,native_covariance=D@fit['root']@fit['root'].T@D.T,
        exact_transport_covariance=F@fit['root']@fit['root'].T@F.T)
    save('exact_refit')
    ref=solve(exact,start=fit['w']);row['exact']=fit_record(ref)
    # A second, gradient-predicted start checks the local refit, not global uniqueness.
    save('exact_correction_start')
    ref2=solve(exact,start=fit['w']+correction);row['exact_correction_start']=fit_record(ref2)
    converged=[r for r in (ref,ref2) if r['diagnostic']['stop'] in CONVERGED]
    if not converged:
        row['status']='exact_fit_unresolved';save('finished');return
    ref=min(converged,key=lambda r:r['diagnostic']['cost']);row['selected_exact']=fit_record(ref)
    actual=100*np.expm1(ref['x'][5]-fit['x'][5])
    row['comparison']=dict(exact_minus_field_Q_percent=float(actual),
        exact_minus_field_Q_local_SD=float((ref['x'][5]-fit['x'][5])/np.linalg.norm(ref['root'][5])),
        exact_Q_SD_percent=float(100*np.linalg.norm(ref['root'][5])),
        field_Q_SD_percent=float(100*np.linalg.norm(fit['root'][5])),
        two_start_Q_difference_percent=float(100*np.expm1(ref2['x'][5]-row['exact']['x'][5])))
    save('partition_attribution')
    parts=Parts(build_parts(out/'parts'),model)
    audit=partition_audit(parts,model,obs,fit['x'],L,cfg,Path(entry['field_binary']))
    components=np.asarray(audit['gradient_contributions'])
    pc=-np.linalg.solve(P,components.T).T
    audit['predicted_Q_correction_percent_by_group']=100*pc@L[5]
    error=components.sum(axis=0)-(g-fg)
    audit['assembly_Q_error_local_SD']=float(L[5]@np.linalg.solve(P,error)/sd)
    row['partition']=audit
    save('chunk_control')
    large=Exact(model,obs,mean,L,chunk=32768)(fit['w'])
    row['chunk_control']=dict(chunks=[16384,32768],cost_difference=large[0]-c,
        Q_shift_local_SD=float(L[5]@np.linalg.solve(P,large[1]-g)/sd),
        relative_precision_difference=float(np.linalg.norm(large[2]-P)/np.linalg.norm(P)))
    save('directional_curvature')
    _,_,rp,_,_=exact(ref['w']);q=np.linalg.solve(rp,L[5]);q/=np.sqrt(q@rp@q)
    row['Q_direction_curvature']=[]
    for h in (.001,.0003,.0001):
        gp=exact(ref['w']+h*q)[1];gm=exact(ref['w']-h*q)[1]
        row['Q_direction_curvature'].append(dict(step_SD=h,observed_to_GN=float(q@(gp-gm)/(2*h))))
    row['status']='complete_local_diagnostic';save('finished')

if __name__=='__main__':main()
