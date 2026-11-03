"""Fixed-budget shared RC query feasibility fits using the unchanged reviewed solver and frozen evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from .readouts import add_readouts
from experiments.hysteresis_mixed_completion_001.run import CommonDomain,choose_fit
from experiments.slow_likelihood_diagnostic_001.numerics import Exact
from .field import SharedField,Compressed
import time
from experiments.hysteresis_sensitivity_basis_001.run import field,verify
from experiments.foster_campaign_001.backend import ROOT,identity
from experiments.foster_campaign_001.compact import StimulusStream
from experiments.foster_feedback_001.estimator import Model
from experiments.h7_history_quality_001.history import source_receipt,verify_sources,write


ARMS=['TaylorRC_TaylorH2','CayleyRC_TaylorH2','TaylorRC_H7','R5_H7']


def refit(fields,model,obs,mean,L):
    raw=Exact(model,obs,mean,L,chunk=4096);exact=CommonDomain(raw,fields['TaylorRC_TaylorH2'])
    objectives={'direct':exact,**{name:Compressed(f,mean,L) for name,f in fields.items()}}
    report={};began=time.process_time()
    for name,objective in objectives.items():
        fit,row=choose_fit(objective);report[name]=row
        if fit is not None:
            cost,g,P,_,_=exact(fit['w'])
            row['same_anchor']=dict(direct_cost=cost,direct_gradient_dual_norm=float(np.linalg.norm(np.linalg.solve(np.linalg.cholesky(P),g))))
        print(json.dumps(dict(stage='fit',records=len(obs),arm=name,status=row['status'])),flush=True)
    return dict(arms=report,direct_evaluations=raw.calls,host_cpu_s=time.process_time()-began)


def control_parity(report,old):
    records={}
    for name in ['direct','TaylorRC_TaylorH2','TaylorRC_H7','R5_H7']:
        now,previous=report['arms'][name],old['fits']['arms'][name]
        exact=now['status']==previous['status'] and now.get('selected_start')==previous.get('selected_start')
        if 'selected' in now and 'selected' in previous:
            for key in ['w','x','root','diagnostic']:
                a,b=now['selected'][key],previous['selected'][key]
                exact=exact and (a==b if isinstance(a,dict) else np.array_equal(a,b))
        elif ('selected' in now)!=('selected' in previous):exact=False
        if not exact:raise ValueError('unchanged control changed: '+name)
        records[name]=dict(status='exact_match')
    return records


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--runs',nargs='+',type=Path,default=[Path('experiments/rc_sensitivity_basis_001/pilot001'),Path('experiments/rc_sensitivity_basis_001/full001')])
    p.add_argument('--loads',nargs='+',choices=['rest','multiscale','embedded'],default=['rest','multiscale','embedded'])
    p.add_argument('--kernel-build',type=Path,default=Path('experiments/hysteresis_sensitivity_basis_001/build001'))
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    hs=ROOT/'provenance/hysteresis_sensitivity_basis_001/result.json';study=json.loads(hs.read_text())
    binaries={k:args.kernel_build/k/'response.so' for k in ['collocation','derivative']};bindings={str(hs):identity(hs)}
    for k,path in binaries.items():verify(path,study['binaries'][k],bindings)
    for path,expected in study['protocol'].items():verify(ROOT/path,expected,bindings)
    sources=source_receipt();protocol=ROOT/'specifications/shared_operator_budget_001/README.md'
    artifacts={str(p):identity(p) for p in [ROOT/'specifications/shared_operator_budget_001/C1.md']}
    prior_study=json.loads((ROOT/'provenance/rc_partition_repair_001/result.json').read_text())
    registration=dict(source=sources,protocol=identity(protocol),inputs=bindings,new_artifacts=artifacts,new_binaries={},arms=['direct']+ARMS,
        starts=['zero prior-whitened coordinates','alternating +/-0.05 prior-whitened coordinates'],
        max_rounds=60,prior_and_centres='identical frozen registrations',support='unchanged original rate box and physical path gate',
        optimizer='unchanged choose_fit/solve; legacy covariance retained, separate QR diagnostics added')
    write(args.out/'registration.json',registration);cases=[]
    for directory in args.runs:
        inputs={}
        for suffix,filename in [('registration','registration.json'),('summary','summary.json')]:
            frozen=ROOT/'provenance/rc_sensitivity_basis_001'/f'{directory.name}_{suffix}.json'
            verify(directory/filename,identity(frozen),inputs)
        reg=json.loads((directory/'registration.json').read_text());verify_sources(reg['source'])
        for path,expected in reg['new_artifacts'].items():verify(ROOT/path,expected,inputs)
        for path,expected in [(directory/'backend_c/estimator.so',reg['direct_binary']),
                              (directory/'response/response.so',reg['response_binary']),
                              (directory/'response_taylor2/response.so',reg['sensitivity_binaries']['taylor2'])]:verify(path,expected,inputs)
        model=Model(directory/'backend_c/estimator.so',reg['config'])
        mean,L,center=np.array(reg['prior_mean']),np.array(reg['prior_root']),np.array(reg['center'])
        manifest=json.loads((directory/'summary.json').read_text())
        for entry in manifest['cases']:
            path=directory/entry['file'];verify(path,entry['identity'],inputs)
            old=json.loads(path.read_text())
            if old['load'] not in args.loads:continue
            base=Path(old['baseline_result']['path']);verify(base,old['baseline_result']['identity'],inputs)
            recipe=json.loads(base.read_text());source=recipe['source_id'];recipe=recipe['recipe']
            if len(old['prefixes'])!=1:raise ValueError('one frozen prefix expected')
            prefix=old['prefixes'][0];sp=Path(prefix['snapshot']['path']);verify(sp,prefix['snapshot']['identity'],inputs)
            def factory(name):
                if name=='CayleyRC_TaylorH2':
                    return SharedField(reg['config'],reg['center'],directory/'response_taylor2/response.so',binaries['derivative'],source)
                return field(name,reg,directory,source,binaries)
            previous=Path('experiments/rc_partition_repair_001/run001')/f"{directory.name}_{old['load']}.json"
            verify(previous,prior_study['raw_bindings'][str(previous)],inputs)
            prior_case=json.loads(previous.read_text())
            fields={name:factory(name) for name in ARMS}
            stream=StimulusStream(reg['config'],recipe['cell'],recipe['case'],recipe['settings'])
            chunks=[];digest=hashlib.sha256()
            while stream.index<prefix['records']:
                start=stream.index;o,_,_=stream.read(min(1024,prefix['records']-start))
                if stream.failure or not len(o):raise ValueError('frozen stream regeneration failed')
                digest.update(o.astype('<f8',copy=False).tobytes());chunks.append(o.copy())
                for f in fields.values():f.update(start,o,source)
            if digest.hexdigest()!=prefix['observation_sha256']:raise ValueError('observation hash')
            prior_snapshot=Path(prior_case['snapshot']['path']);verify(prior_snapshot,prior_case['snapshot']['identity'],inputs)
            with np.load(prior_snapshot,allow_pickle=False) as saved:
                for name in ['TaylorRC_TaylorH2','TaylorRC_H7','R5_H7']:
                    if not np.array_equal(fields[name].state,saved[name+'_state']) or not np.array_equal(fields[name].root,saved[name+'_root']):raise ValueError('frozen factor/state changed')
            if not np.array_equal(fields['CayleyRC_TaylorH2'].root,fields['TaylorRC_TaylorH2'].root) or not np.array_equal(fields['CayleyRC_TaylorH2'].state,fields['TaylorRC_TaylorH2'].state):raise ValueError('shared streamed factor/state changed')
            obs=np.vstack(chunks);report=refit(fields,model,obs,mean,L)
            parity=control_parity(report,prior_case)
            add_readouts(fields,factory,model,obs,mean,L,center,report)
            snapshot={}
            for name,f in fields.items():snapshot[name+'_root']=f.root;snapshot[name+'_state']=f.state
            label=f"{directory.name}_{old['load']}";spout=args.out/(label+'_factors.npz')
            np.savez_compressed(spout,**snapshot)
            result=dict(run=str(directory),load=old['load'],records=len(obs),observation_sha256=digest.hexdigest(),
                input_bindings=inputs.copy(),prior_mean=mean,prior_root=L,center=center,config=reg['config'],
                fits=report,control_parity=parity,storage={name:f.storage() for name,f in fields.items()},
                snapshot=dict(path=str(spout),identity=identity(spout)),direct_observation_array_B=obs.nbytes)
            out=args.out/(label+'.json');write(out,result)
            cases.append(dict(run=str(directory),load=old['load'],records=len(obs),file=out.name,identity=identity(out)))
            print(json.dumps(dict(stage='case_complete',run=directory.name,load=old['load'],records=len(obs))),flush=True)
    verify_sources(sources)
    for path,expected in artifacts.items():verify(Path(path),expected,{})
    if identity(protocol)!=registration['protocol']:raise ValueError('protocol changed')
    write(args.out/'summary.json',dict(status='completed_joint_refit_exploration_no_promotion',cases=cases,
        scope='Same public prior/centre/support, numerical fits and local uncertainty, not truth accuracy or coverage'))


if __name__=='__main__':main()
