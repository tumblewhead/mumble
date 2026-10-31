"""Five matched Stage-1 diagnostics; never reads a plant or truth file."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import numpy as np
from experiments.foster_campaign_001.coordinates import prior
from experiments.foster_campaign_001.field_backend import transported
from experiments.foster_feedback_001.estimator import Model
from experiments.foster_uncertainty_audit_001.conditional_packet import partition
from experiments.joint_rate_history_001.field import Field,build
from experiments.slow_likelihood_diagnostic_001.numerics import Exact,Compressed,solve,predictive
from .diagnostics import (ROOT,CONVERGED,Parts,build_parts,write,identity,fit_record,
                          attempt_starts,endpoint,partition_audit,observed_directions)


def analyze(case,out,binary,parts_binary):
    reg=json.loads((case/'regeneration.json').read_text())
    if (reg['status']!='validated' or identity(case/'observations.npy')!=reg['observations']
            or identity(case/'messages.npz')!=reg['messages']):
        raise ValueError('unvalidated or changed observations/messages')
    source=Path(reg['source_case']).parent
    if identity(case/'calibration.json')!=identity(source/'calibration.json'):
        raise ValueError('copied public calibration differs from source')
    modelbinary=source/'backend_c/estimator.so'
    if identity(modelbinary)!=json.loads((source/'backend_c/build.json').read_text())['binary']:
        raise ValueError('archived model binary identity changed')
    cfg=json.loads((case/'calibration.json').read_text());mean,L=prior(cfg)
    model=Model(modelbinary,cfg);parts=Parts(parts_binary,model)
    allobs=np.load(case/'observations.npy',mmap_mode='r')
    n=reg['fit_records'];obs=allobs[:n];future=allobs[n:]
    if allobs.shape!=(n+reg['holdout_records'],5):
        raise ValueError('observation shape or prefix count mismatch')
    saved=dict(np.load(case/'messages.npz',allow_pickle=False))
    offset=np.zeros(16);offset[[5,13,14,15]]=[.3,-.3,.3,.3]
    starts=[('public_prior',np.zeros(16)),('declared_offset',offset),('negative_offset',-offset),
            ('saved_field_origin',saved['field_origin_w'])]
    row=dict(label=case.name,status='running',fit_records=n,fit_hours=n/reg['sample_rate_Hz']/3600,
             heldout_records=len(future),prior_mean=mean,prior_root=L,inference_truth_reads=0,
             regeneration=identity(case/'regeneration.json'),model_binary=identity(modelbinary))
    out.mkdir(parents=True,exist_ok=False)
    def save(stage):
        row['stage']=stage;write(out/'result.json',row)
        print(json.dumps(dict(label=case.name,stage=stage)),flush=True)
    row['saved_endpoints']={k:endpoint(v[:16],v[16:272].reshape(16,16)) for k,v in saved.items() if v.shape==(273,)}
    row['saved_field_counts']=reg['field_counts']
    save('exact_fits')
    exact=Exact(model,obs,mean,L);best,runs=attempt_starts(exact,starts)
    row['exact']=dict(starts=runs)
    if best is None:
        row['status']='exact_fit_unresolved';save('finished');return row
    ec,eg,eP,end,F=exact(best['w'])
    eroot=F@best['root']
    row['exact'].update(selected=fit_record(best),endpoint=endpoint(end,eroot))
    save('field_build_and_fits')
    field=Field(cfg,partition(mean)[1],1.,5,binary)
    began=time.perf_counter()
    for first in range(0,n,4096):field.update(first,obs[first:first+4096])
    obj=Compressed(field,mean,L);fb,fruns=attempt_starts(obj,starts)
    row['field']=dict(build_wall_s=time.perf_counter()-began,storage=field.storage(),starts=fruns)
    if fb is None:
        row['status']='field_fit_unresolved';save('finished');return row
    row['field']['selected']=fit_record(fb)
    _,_,_,fe,fF=exact(fb['w'])
    ne,nD=transported(field,fb['x'])
    row['field']['exact_transport_endpoint']=endpoint(fe,fF@fb['root'])
    row['field']['native_endpoint']=endpoint(ne,nD@fb['root'])
    row['observed_directions']={}
    row['anchors']={}
    for label,fit in [('exact',best),('field',fb)]:
        save('common_anchor_'+label)
        c,g,P,ee,FF=exact(fit['w']);fc,fg,fP,_,_=obj(fit['w'])
        correction=-np.linalg.solve(P,g)
        Croot=L@np.linalg.solve(np.linalg.cholesky(P).T,np.eye(16))
        froot=L@np.linalg.solve(np.linalg.cholesky(fP).T,np.eye(16))
        audit=partition_audit(parts,model,obs,fit['x'],L,cfg,binary)
        # Neither decomposition nor its normalization drops cross terms.
        pc=-np.linalg.solve(P,np.asarray(audit['gradient_contributions']).T).T
        audit['predicted_Q_correction_percent_by_group']=100*(pc@L[5])
        audit['predicted_SOC_correction_pp_by_group']=100*(pc@(FF@L)[0])
        audit['partition_sum_vs_objective_gradient_max_abs']=float(np.max(abs(np.sum(audit['gradient_contributions'],axis=0)-(g-fg))))
        row['anchors'][label]=dict(exact_cost=c,field_cost=fc,exact_gradient=g,field_gradient=fg,
            exact_GN_decrement_squared=float(g@np.linalg.solve(P,g)),field_GN_decrement_squared=float(fg@np.linalg.solve(fP,fg)),
            predicted_Q_correction_percent=float(100*np.expm1(L[5]@correction)),
            predicted_SOC_correction_pp=float(100*(FF@L)[0]@correction),
            same_anchor_Q_SD_ratio_field_exact=float(np.linalg.norm(froot[5])/np.linalg.norm(Croot[5])),
            relative_GN_precision_difference=float(np.linalg.norm(fP-P)/np.linalg.norm(P)),partition=audit)
        row['observed_directions'][label]=observed_directions(exact,fit['w'],L)
    save('chunk_check')
    small=exact(fb['w']);large=Exact(model,obs,mean,L,chunk=32768)(fb['w'])
    dc=-np.linalg.solve(small[2],large[1]-small[1])
    row['chunk_check']=dict(chunks=[16384,32768],cost_difference=large[0]-small[0],
        gradient_difference=large[1]-small[1],relative_GN_difference=float(np.linalg.norm(large[2]-small[2])/np.linalg.norm(small[2])),
        predicted_Q_shift_local_SD=float(L[5]@dc/np.linalg.norm(best['root'][5])),
        endpoint_max_difference=float(np.max(abs(large[3]-small[3]))))
    qsd=np.linalg.norm(best['root'][5])
    grid=[('prior_'+str(k),mean[5]+np.linalg.norm(L[5])*k) for k in range(-3,4)]
    grid += [('local_'+str(k),best['x'][5]+qsd*k) for k in range(-3,4)]
    grid += [('rolling',saved['float64'][5]),('saved_field',saved['field64'][5]),('fresh_field',fb['x'][5])]
    row['profiles']=[]
    for label,q in grid:
        entry=dict(label=label,logQ=float(q),Q_Ah=float(np.exp(q)))
        for name,objective,fit in [('exact',exact,best),('field',obj,fb)]:
            try:
                pf=solve(objective,start=fit['w'],logq=float(q))
                entry[name]=dict(status='converged' if pf['diagnostic']['stop'] in CONVERGED else 'unresolved',
                    **fit_record(pf),delta_from_selected=pf['diagnostic']['cost']-fit['diagnostic']['cost'])
            except (ValueError,OverflowError,np.linalg.LinAlgError) as e:
                entry[name]=dict(status='unresolved',reason=str(e))
        row['profiles'].append(entry);save('profile_'+label)
    save('heldout_predictions')
    row['predictions']={k:predictive(model,v[:16],v[16:272].reshape(16,16),future)
                        for k,v in saved.items() if v.shape==(273,)}
    row['predictions'].update(exact=predictive(model,end,eroot,future),
        field_exact_transport=predictive(model,fe,fF@fb['root'],future),
        field_native_transport=predictive(model,ne,nD@fb['root'],future))
    row['comparison']=dict(field_minus_exact_Q_percent=float(100*np.expm1(fb['x'][5]-best['x'][5])),
        field_minus_exact_Q_local_SD=float((fb['x'][5]-best['x'][5])/qsd),
        field_minus_exact_SOC_pp=float(100*(ne[0]-end[0])),
        saved_field_minus_fresh_Q_percent=float(100*np.expm1(saved['field64'][5]-fb['x'][5])),
        saved_field_minus_fresh_SOC_pp=float(100*(saved['field64'][0]-ne[0])))
    row['exact']['successful_objective_evaluations']=exact.calls
    row['profile_limits']=[dict(label=p['label'],method=m,status=p[m]['status'],reason=p[m].get('reason',p[m].get('diagnostic',{}).get('stop')))
        for p in row['profiles'] for m in ['exact','field'] if p[m]['status']!='converged']
    row['status']='diagnostic_complete_with_explicit_profile_limits' if row['profile_limits'] else 'diagnostic_complete'
    save('finished');return row


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--inputs',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--labels',nargs='+',default=['owner_case_0000','owner_case_0002','owner_case_0004','owner_case_0006','weak_B_cycle'])
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    paths=list(Path(__file__).parent.glob('*.py'))
    paths += [ROOT/n for n in ['experiments/slow_likelihood_diagnostic_001/numerics.py',
        'experiments/joint_rate_history_001/field.py','experiments/joint_rate_history_001/probe.c',
        'experiments/foster_bounded_hysteresis_001/model.c','experiments/foster_c_history_001/baseline.h',
        'experiments/foster_campaign_001/coordinates.py','experiments/foster_feedback_001/estimator.py',
        'experiments/foster_campaign_001/field_backend.py','experiments/foster_uncertainty_audit_001/conditional_packet.py']]
    for path in paths:
        dest=args.out/'sources'/path.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)
    write(args.out/'reservation.json',dict(command=sys.argv,source_revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        sources={str(p.relative_to(ROOT)):identity(p) for p in paths},inference_truth_reads=0,original_prior_once=True,
        starts='public prior, declared signed offsets, saved field origin; only converged starts eligible',
        scope='Stage1 only; no longer-prefix sweep or production estimator changes'))
    binary=build(args.out/'field_build');parts=build_parts(args.out/'parts_build')
    results=[]
    for label in args.labels:
        began=time.perf_counter()
        result=analyze(args.inputs/label,args.out/label,binary,parts)
        results.append(dict(label=label,status=result['status'],wall_s=time.perf_counter()-began,
                            result=identity(args.out/label/'result.json')))
        write(args.out/'index.json',dict(cases=results,status='running'))
    write(args.out/'index.json',dict(cases=results,status='finished',inference_truth_reads=0))


if __name__=='__main__':main()
