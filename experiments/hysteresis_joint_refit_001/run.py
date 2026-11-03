"""Five-arm joint refits using the unchanged reviewed solver and frozen evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from .readouts import add_readouts
from experiments.hysteresis_mixed_completion_001.run import fit_prefix
from experiments.hysteresis_sensitivity_basis_001.run import field,verify
from experiments.foster_campaign_001.backend import ROOT,identity
from experiments.foster_campaign_001.compact import StimulusStream
from experiments.foster_feedback_001.estimator import Model
from experiments.h7_history_quality_001.history import source_receipt,verify_sources,write


ARMS=['TaylorRC_H2','TaylorRC_TaylorH2','TaylorRC_H7','R5_H7']


def refit(fields,model,obs,mean,L):
    # The old engine uses this internal key only to choose its domain gate.
    # The actual object is Taylor-RC/H2; output names retain that fact.
    routed={'R2_H2':fields['TaylorRC_H2'],**{k:v for k,v in fields.items() if k!='TaylorRC_H2'}}
    result=fit_prefix(routed,model,obs,mean,L)
    result['arms']={('TaylorRC_H2' if k=='R2_H2' else k):v for k,v in result['arms'].items()}
    return result


def control_parity(report,old):
    records={}
    for name,legacy in [('direct','direct'),('TaylorRC_H2','Taylor2_H2'),('R5_H7','R5_H7')]:
        now,previous=report['arms'][name],old['fits']['arms'][legacy]
        exact=now['status']==previous['status'] and now.get('selected_start')==previous.get('selected_start')
        if 'selected' in now and 'selected' in previous:
            for key in ['w','x','root','diagnostic']:
                current, frozen = now['selected'][key], previous['selected'][key]
                equal = current == frozen if isinstance(current,dict) else np.array_equal(current,frozen)
                exact = exact and equal
        elif ('selected' in now)!=('selected' in previous):exact=False
        records[name]=dict(status='exact_match' if exact else 'mismatch',old_arm=legacy)
        if not exact:raise ValueError('unchanged fitted control changed: '+name)
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
    sources=source_receipt();protocol=ROOT/'specifications/hysteresis_joint_refit_001/README.md'
    registration=dict(source=sources,protocol=identity(protocol),inputs=bindings,arms=['direct']+ARMS,
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
            factory=lambda name:field(name,reg,directory,source,binaries)
            fields={name:factory(name) for name in ARMS}
            stream=StimulusStream(reg['config'],recipe['cell'],recipe['case'],recipe['settings'])
            chunks=[];digest=hashlib.sha256()
            while stream.index<prefix['records']:
                start=stream.index;o,_,_=stream.read(min(1024,prefix['records']-start))
                if stream.failure or not len(o):raise ValueError('frozen stream regeneration failed')
                digest.update(o.astype('<f8',copy=False).tobytes());chunks.append(o.copy())
                for f in fields.values():f.update(start,o,source)
            if digest.hexdigest()!=prefix['observation_sha256']:raise ValueError('observation hash')
            with np.load(sp,allow_pickle=False) as saved:
                for name,oldname in [('TaylorRC_H2','Taylor2_H2'),('R5_H7','R5_H7')]:
                    if not np.array_equal(fields[name].state,saved[oldname+'_state']) or not np.array_equal(fields[name].root,saved[oldname+'_root']):raise ValueError('frozen factor/state changed')
            obs=np.vstack(chunks);report=refit(fields,model,obs,mean,L)
            parity=control_parity(report,prefix)
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
    if identity(protocol)!=registration['protocol']:raise ValueError('protocol changed')
    write(args.out/'summary.json',dict(status='completed_joint_refit_exploration_no_promotion',cases=cases,
        scope='Same public prior/centre/support, numerical fits and local uncertainty, not truth accuracy or coverage'))


if __name__=='__main__':main()
