"""Matched refinement diagnostics; inference never opens scenario/truth files."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import numpy as np
from experiments.shared_uncertainty_growth_001.audit import load_inputs,require_identity
from experiments.uncertainty_weak_stimulus_001.diagnostics import write,identity,fit_record,CONVERGED
from experiments.slow_likelihood_diagnostic_001.numerics import Exact,solve
from experiments.foster_feedback_001.estimator import Model
from experiments.foster_campaign_001.field_backend import transported as old_transport
from experiments.foster_uncertainty_audit_001.conditional_packet import partition
from experiments.tangent_development_001.forecast import predict
from .field import MixedField,Compressed,build,transported

TASKS={
 'rest60':dict(segments=[dict(duration_s=60,current_A=0)]),
 'pulse120mA10s':dict(segments=[dict(duration_s=10,current_A=.12)],recovery_s=30)}


def analyze(field,oldfield,cfg,mean,L,obs,entry,baseline,out):
    out.mkdir(parents=True,exist_ok=False)
    model=Model(Path(entry['model_binary']),cfg);exact=Exact(model,obs,mean,L)
    reference=baseline['selected_exact'];refx=np.array(reference['x']);refroot=np.array(reference['root'])
    _,_,_,refend,refF=exact(np.array(reference['w']))
    refendpointroot=refF@refroot
    row=dict(status='running',hours=entry['hours'],records=len(obs),storage=field.storage(),original_prior_once=True,inference_truth_reads=0)
    candidates={}
    obj=Compressed(field,mean,L);began=time.perf_counter()
    fit=solve(obj,start=np.array(baseline['field']['w']));row['fit']=fit_record(fit)
    row['fit_wall_s']=time.perf_counter()-began
    if fit['diagnostic']['stop'] not in CONVERGED:
        row['status']='fit_unresolved';write(out/'result.json',row);return row
    c,g,P,end,F=exact(fit['w']);_,fg,fP,_,_=obj(fit['w'])
    sd=np.linalg.norm(refroot,axis=1);delta=fit['x']-refx
    correction=-np.linalg.solve(P,g)
    eroot=L@np.linalg.solve(np.linalg.cholesky(P).T,np.eye(16))
    row['diagnostics']=dict(exact_cost=c,field_gradient=fg,exact_gradient=g,
        predicted_Q_correction_percent=float(100*np.expm1(L[5]@correction)),
        predicted_Q_correction_local_SD=float((L[5]@correction)/np.linalg.norm(eroot[5])),
        candidate_minus_reference_Q_percent=float(100*np.expm1(delta[5])),
        candidate_minus_reference_Q_local_SD=float(delta[5]/sd[5]),
        origin_chart_shift_local_SD=delta/sd,
        joint_center_distance=float(np.linalg.norm(np.linalg.solve(refroot,delta))),
        Q_width_ratio_same_anchor=float(np.linalg.norm(fit['root'][5])/np.linalg.norm(eroot[5])),
        Q_width_ratio_at_optima=float(np.linalg.norm(fit['root'][5])/sd[5]))
    candidates['candidate_exact_transport']=(end,F@fit['root'])
    oldfit=baseline['field'];oldend,oldD=old_transport(oldfield,np.array(oldfit['x']))
    candidates['baseline_native']=(oldend,oldD@np.array(oldfit['root']))
    candidates['reference']=(refend,refendpointroot)
    try:
        native,D=transported(field,fit['x']);candidates['candidate_native']=(native,D@fit['root'])
        row['transport']=dict(status='supported',chart_difference=native-end,
            h_difference=float(np.tanh(native[4])-np.tanh(end[4])),
            endpoint_native=native,endpoint_exact=end)
    except (ValueError,OverflowError) as e:
        row['transport']=dict(status='unresolved',reason=str(e))
    row['forecasts']=[];temp=float(obs[-1,2])
    for taskname,task in TASKS.items():
        predictions={}
        for arm,(center,root) in candidates.items():
            try:
                p=predict(model,center,root,task,cfg,temp,50.)
                filename=f'{taskname}_{arm}.npz'
                np.savez(out/filename,**{k:p[k] for k in ('times','voltage','current','dt','local_sd_V')},endpoint=center,root=root)
                o=np.c_[p['dt'],p['current'],np.full(len(p['dt']),temp),np.zeros(len(p['dt'])),np.ones(len(p['dt']))]
                rv,rJ,_,_=model.evaluate(refend,o);rsd=np.linalg.norm(rJ@refendpointroot,axis=1)
                diff=p['voltage']-rv
                info=dict(arm=arm,task=taskname,status='supported',file=filename,file_identity=identity(out/filename),
                    task_definition=task,temperature_C=temp,rate_Hz=50.,
                    minimum_V=p['minimum_V'],recovery_V=p['recovery_V'],
                    reference_RMS_difference_uV=float(1e6*np.sqrt(np.mean(diff**2))),
                    reference_max_difference_uV=float(1e6*np.max(abs(diff))),
                    reference_max_standardized_difference=float(np.max(abs(diff)/rsd)),
                    local_SD_ratio_range=[float(np.min(p['local_sd_V']/rsd)),float(np.max(p['local_sd_V']/rsd))],
                    unsupported_probes=p['unsupported_probes'],probes=p['probes'],
                    C_closed_form_max_difference_V=p['closed_form_C_max_difference_V'])
                predictions[arm]=info
            except (ValueError,OverflowError,np.linalg.LinAlgError) as e:
                predictions[arm]=dict(arm=arm,task=taskname,status='unresolved',reason=str(e))
        ref=predictions.get('reference',{})
        for p in predictions.values():
            if p['status']=='supported' and ref.get('status')=='supported':
                p['reference_minimum_difference_uV']=1e6*(p['minimum_V']-ref['minimum_V'])
                p['reference_recovery_difference_uV']=1e6*(p['recovery_V']-ref['recovery_V'])
            row['forecasts'].append(p)
    row['status']='complete_local_diagnostic' if row['transport']['status']=='supported' else 'complete_with_transport_limit'
    write(out/'result.json',row);return row


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--seed',type=int,choices=(1100,1103),required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--degrees',type=int,nargs='+',default=[6,7])
    a=p.parse_args();root=Path(__file__).resolve().parents[2]
    inputs=root/f'experiments/shared_uncertainty_growth_001/inputs{a.seed}'
    parent=root/'experiments/shared_uncertainty_growth_001'
    receipt=json.loads((root/'provenance/shared_uncertainty_growth_001/receipt.json').read_text())
    sequences=[4325376,12976128]
    loaded={n:load_inputs(inputs,n) for n in sequences}
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    sources=list(Path(__file__).parent.glob('*.py'))+[Path(__file__).with_name('response.c'),Path(__file__).with_name('registration.json')]
    for path in sources:
        dest=out/'sources'/path.name;dest.parent.mkdir(exist_ok=True);shutil.copy2(path,dest)
    write(out/'reservation.json',dict(command=sys.argv,source_revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        sources={str(p.relative_to(root)):identity(p) for p in sources},degrees=a.degrees,
        inputs=identity(inputs/'validated.json'),parent_receipt=identity(root/'provenance/shared_uncertainty_growth_001/receipt.json')))
    cfg,mean,L,_,_,obs,entry=loaded[max(sequences)];binary=build(out/'build')
    fields={d:MixedField(cfg,partition(mean)[1],1.,d,binary,source=str(inputs)) for d in a.degrees}
    elapsed={d:0. for d in fields};last=0;results=[];began=time.perf_counter()
    for n in sequences:
        for first in range(last,n,4096):
            rows=obs[first:min(first+4096,n)]
            for d,f in fields.items():
                t=time.perf_counter();f.update(first,rows,source=str(inputs));elapsed[d]+=time.perf_counter()-t
        cfg,mean,L,old,_,prefix,entry=loaded[n]
        path=parent/f'audit{a.seed}_{n}/result.json'
        original=next(c for c in receipt['cases'] if c['seed']==a.seed and c['records']==n)
        require_identity(path,original['evidence']['result']);baseline=json.loads(path.read_text())
        for degree,f in fields.items():
            directory=out/f'n{n}_h{degree}'
            r=analyze(f,old,cfg,mean,L,prefix,entry,baseline,directory)
            np.savez(directory/'field.npz',root=f.root,state=f.state)
            r['build_wall_s']=elapsed[degree];r['field_identity']=identity(directory/'field.npz')
            write(directory/'result.json',r)
            results.append(dict(degree=degree,records=n,result=str(directory/'result.json'),identity=identity(directory/'result.json')))
            print(json.dumps(dict(seed=a.seed,degree=degree,hours=entry['hours'],status=r['status'],Q_shift_SD=r.get('diagnostics',{}).get('candidate_minus_reference_Q_local_SD'),build_s=elapsed[degree])),flush=True)
        last=n
        write(out/'index.json',dict(status='running',cases=results,wall_s=time.perf_counter()-began))
    write(out/'index.json',dict(status='complete',cases=results,wall_s=time.perf_counter()-began))

if __name__=='__main__':main()
