"""Matched mixed-term probes, joint fits and sampled load-voltage diagnostics."""
import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from .basis import CompletedField
from experiments.response_basis_attribution_001.basis import BasisField
from experiments.partitioned_coefficients_001.run import Direct, compare, chart_shape_jacobian
from experiments.conditional_architecture_001.conditional import chart_amplitude_jacobian
from experiments.foster_campaign_001.backend import ROOT, identity, prepare_c
from experiments.foster_campaign_001.coordinates import prior
from experiments.foster_campaign_001.compact import StimulusStream
from experiments.foster_feedback_001.estimator import Model
from experiments.foster_uncertainty_audit_001.conditional_packet import chart_from, partition
from experiments.hysteresis_refinement_001.field import MixedField, Compressed, build, features_jacobian, transported
from experiments.slow_likelihood_diagnostic_001.numerics import Exact, solve
from experiments.uncertainty_weak_stimulus_001.diagnostics import CONVERGED
from experiments.h7_history_quality_001.history import write, source_receipt, verify_sources


class CommonDomain:
    def __init__(self, objective, gate):
        self.objective, self.gate = objective, gate
        self.mean, self.root = objective.mean, objective.root
    def __call__(self, w):
        self.gate.features(self.mean+self.root@w)
        return self.objective(w)


def choose_fit(objective):
    attempts=[]; fits=[]
    for label,start in [('public_mean',np.zeros(16)),('public_alternating',.05*(-1.)**np.arange(16))]:
        try:
            fit=solve(objective,start=start,max_rounds=60)
            attempts.append(dict(start=label,status='converged' if fit['diagnostic']['stop'] in CONVERGED else 'unresolved',
                                 diagnostic=fit['diagnostic'],w=fit['w']))
            fits.append((len(attempts)-1,fit))
        except (ValueError,OverflowError,FloatingPointError,np.linalg.LinAlgError) as error:
            attempts.append(dict(start=label,status='failed',reason=str(error)))
    converged=[item for item in fits if item[1]['diagnostic']['stop'] in CONVERGED]
    available=converged or fits
    if not available:return None,dict(status='failed',attempts=attempts)
    index,fit=min(available,key=lambda item:item[1]['diagnostic']['cost'])
    return fit,dict(status='converged' if converged else 'unresolved',selected_start=index,
                    attempts=attempts,selected=dict(w=fit['w'],x=fit['x'],root=fit['root'],diagnostic=fit['diagnostic']))


def future_tasks():
    tasks={}
    for name,parts in [('rest60',[(60.,0.)]),('pulse120mA10s_rest30',[(10.,.12),(30.,0.)])]:
        blocks=[]
        for seconds,current in parts:
            n=round(seconds*35);o=np.zeros((n,5));o[:,0]=1/35;o[:,1]=current;o[:,2]=25.;o[:,4]=1.
            blocks.append(o)
        tasks[name]=np.vstack(blocks)
    return tasks


def prediction(model,end,root,obs):
    voltage,J,_,_=model.evaluate(end,obs)
    sd=np.linalg.norm(J@root,axis=1)
    return voltage,sd


def forecast_metrics(candidate,reference):
    v,sd=candidate;rv,rsd=reference
    if np.any(rsd<=0):raise ValueError('unresolved reference forecast width')
    delta=v-rv
    return dict(RMS_difference_mV=float(1000*np.sqrt(np.mean(delta**2))),
                maximum_difference_mV=float(1000*np.max(abs(delta))),
                sampled_minimum_difference_mV=float(1000*(v.min()-rv.min())),
                local_SD_ratio_range=[float((sd/rsd).min()),float((sd/rsd).max())],
                maximum_difference_in_reference_local_SD=float(np.max(abs(delta)/rsd)))


def fit_prefix(fields,model,obs,mean,L):
    raw=Exact(model,obs,mean,L,chunk=4096)
    exact=CommonDomain(raw,fields['R2_H2'])
    objectives={'direct':exact,**{name:Compressed(f,mean,L) for name,f in fields.items()}}
    fits={}; report={}; began=time.process_time()
    for name,objective in objectives.items():
        fit,record=choose_fit(objective);report[name]=record
        if fit is not None:fits[name]=fit
        print(json.dumps(dict(stage='fit',records=len(obs),arm=name,status=record['status'],
                              stop=fit['diagnostic']['stop'] if fit else None)),flush=True)
    reference=fits.get('direct') if report['direct']['status']=='converged' else None
    ref_forecasts={}; refend=refF=refroot=None
    if reference is not None:
        _,_,_,refend,refF=exact(reference['w']);refroot=refF@reference['root']
        for task,o in future_tasks().items():
            try:ref_forecasts[task]=prediction(model,refend,refroot,o)
            except (ValueError,OverflowError,FloatingPointError) as e:
                report['direct'].setdefault('forecast_failures',{})[task]=str(e)
    for name,fit in fits.items():
        row=report[name]
        try:
            cost,g,P,end,F=exact(fit['w']);chol=np.linalg.cholesky(P)
            _,fg,fP,_,_=objectives[name](fit['w']);dg=fg-g
            relative=np.linalg.solve(chol,np.linalg.solve(chol,fP).T).T
            direct_standard=np.linalg.solve(chol.T,np.eye(16))
            row['same_anchor']=dict(direct_cost=cost,direct_gradient_dual_norm=float(np.linalg.norm(np.linalg.solve(chol,g))),
                compression_gradient_dual_norm=float(np.linalg.norm(np.linalg.solve(chol,dg))),
                relative_joint_GN_precision_eigenvalues=np.linalg.eigvalsh((relative+relative.T)/2),
                Q_log_SD_ratio=float(np.linalg.norm(fit['root'][5])/np.linalg.norm(L[5]@direct_standard)))
            transports={'direct_C':(end,F)}
            if name!='direct':
                try:transports['compressed']=transported(fields[name],fit['x'])
                except (ValueError,OverflowError,FloatingPointError) as error:
                    row['compressed_transport']=dict(status='unsupported',reason=str(error))
            if 'compressed' in transports:
                native,D=transports['compressed']
                row['compressed_transport']=dict(status='supported',SOC_difference_pp=float(100*(native[0]-end[0])),
                    RC_max_difference_mV=float(1000*np.max(abs(native[1:4]-end[1:4]))),
                    hysteresis_difference=float(np.tanh(native[4])-np.tanh(end[4])),
                    joint_transport_derivative_max_difference=float(np.max(abs(D-F))))
            if reference is not None and row['status']=='converged':
                delta=fit['x']-reference['x'];rsd=np.linalg.norm(reference['root'],axis=1)
                row['fit_comparison']=dict(status='local_converged_diagnostic',
                    Q_relative_difference_percent=float(100*np.expm1(delta[5])),
                    Q_log_difference_in_reference_local_SD=float(delta[5]/rsd[5]),
                    exact_transport_SOC_difference_pp=float(100*(end[0]-refend[0])),
                    exact_transport_SOC_difference_in_reference_local_SD=float((end[0]-refend[0])/np.linalg.norm(refroot[0])),
                    origin_joint_local_distance=float(np.linalg.norm(np.linalg.solve(reference['root'],delta))))
                row['forecasts']=[]
                for transport,(endpoint,D) in transports.items():
                    for task,o in future_tasks().items():
                        info=dict(transport=transport,task=task)
                        try:
                            pred=prediction(model,endpoint,D@fit['root'],o)
                            if task not in ref_forecasts:raise ValueError('reference forecast unavailable')
                            info.update(status='supported',**forecast_metrics(pred,ref_forecasts[task]))
                        except (ValueError,OverflowError,FloatingPointError) as e:info.update(status='unsupported',reason=str(e))
                        row['forecasts'].append(info)
            else:row['fit_comparison']=dict(status='unresolved_candidate_or_reference_fit')
        except (ValueError,OverflowError,FloatingPointError,np.linalg.LinAlgError) as error:
            row['diagnostic_failure']=str(error)
    return dict(arms=report,direct_evaluations=raw.calls,host_cpu_s=time.process_time()-began,
                scope='Same public prior once, full joint local GN fits on common support; no truth accuracy, global optimum, calibrated coverage or continuous-time safety claim')


def field_value(field,a,s):
    x=chart_from(a,s);r=field.residual(x)
    chain=np.column_stack((chart_amplitude_jacobian(a),chart_shape_jacobian(s)))
    J=field.root@features_jacobian(field,x)@chain;g=J.T@r
    end=field.evaluate(a,s)['end'] if isinstance(field,BasisField) else field.outgoing(x)
    return dict(nll=.5*float(r@r)+field.noise,gradient_amplitude=g[:11],gradient_shape=g[11:],
                precision_amplitude=J[:,:11].T@J[:,:11],end=end)


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--baseline',type=Path,default=Path('experiments/partitioned_coefficients_001/followup002'))
    parser.add_argument('--rc-control',action='store_true',help='Separately registered RC5 attribution follow-up')
    parser.add_argument('--loads',nargs='+',choices=['rest','multiscale','embedded'],default=['rest','multiscale','embedded'])
    parser.add_argument('--records',nargs='+',type=int,default=[21008,35520,126000])
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    reg=json.loads((args.baseline/'registration.json').read_text());config=reg['config'];center=reg['center'];queries=reg['queries']
    mean,L=prior(config);binary=build(args.out/'response');cbinary=prepare_c(args.out,35,config)[0];model=Model(cbinary,config)
    if args.rc_control:
        from .rc_control import RC5Control
    sources=source_receipt()
    protocol=ROOT/'specifications/hysteresis_mixed_completion_001/README.md'
    registration=dict(source=sources,protocol=identity(protocol),baseline_registration=identity(args.baseline/'registration.json'),
                      config=config,center=center,queries=queries,loads=args.loads,records=args.records,
                      rc_control=args.rc_control,rc_followup=identity(ROOT/'specifications/hysteresis_mixed_completion_001/RC_FOLLOWUP.md') if args.rc_control else None,
                      prior_mean=mean,prior_root=L,response_binary=identity(binary),direct_binary=identity(cbinary),
                      fits='Two common public starts; 60 GN rounds; direct and field share shape/path support',
                      forecasts='Read-only 35 Hz rest60 and +120mA10s/rest30, sampled local comparisons only')
    write(args.out/'registration.json',registration)
    summary=[]
    for path in sorted(args.baseline.glob('case_*/result.json')):
        old=json.loads(path.read_text())
        if old['load'] not in args.loads:continue
        requested=[p for p in old['prefixes'] if p['records'] in args.records]
        if {p['records'] for p in requested}!=set(args.records):raise ValueError('unknown frozen prefix')
        recipe=old['recipe'];source=old['source_id'];stream=StimulusStream(config,recipe['cell'],recipe['case'],recipe['settings'])
        fields={'R2_H2':BasisField(config,center,binary,2,'log',source),
                'R2_H2_c22':CompletedField(config,center,binary,'c22',source),
                'R2_H2_tensor':CompletedField(config,center,binary,'tensor',source),
                'R2_H3':BasisField(config,center,binary,3,'log',source),
                'R5_H7':MixedField(config,center,1.,7,binary,source)}
        if args.rc_control:
            from .rc_control import RC5Control
            for suffix,completion in [('', 'td2'),('_c22','c22'),('_tensor','tensor')]:
                fields['R5_H2'+suffix]=RC5Control(config,center,binary,completion,source)
        refs=[Direct(model,np.array(q['a']),np.array(q['s'])) for q in queries]
        chunks=[];digest=hashlib.sha256();prefixes=[]
        for prefix in requested:
            while stream.index<prefix['records']:
                first=stream.index;obs,_,_=stream.read(min(1024,prefix['records']-first))
                if stream.failure or not len(obs):raise ValueError('fixture stopped')
                digest.update(obs.astype('<f8',copy=False).tobytes());chunks.append(obs.copy())
                for f in fields.values():f.update(first,obs,source)
                for ref in refs:ref.advance(obs)
            if digest.hexdigest()!=prefix['observation_sha256']:raise ValueError('frozen stream mismatch')
            probes=[]
            for q,ref,previous in zip(queries,refs,prefix['queries']):
                a=np.array(q['a']);s=np.array(q['s']);scale=np.maximum(abs(a),[.1,.01,.01,.01,1.,.01,.01,.01,.01,.001,.001])
                row=dict(id=q['id'],selection=q['selection'],arms={})
                try:reference=ref.evaluate();row['direct_status']='supported'
                except ValueError as e:reference=None;row['direct_status']='unsupported';row['direct_reason']=str(e)
                for name,field in fields.items():
                    try:row['arms'][name]=dict(status='supported',metrics=compare(field_value(field,a,s),reference,scale) if reference else None)
                    except ValueError as e:row['arms'][name]=dict(status='unsupported',reason=str(e))
                if q['selection']=='public':
                    for name,key in [('R2_H2','response_degree2'),('R5_H7','H7')]:
                        now=row['arms'][name];before=previous['arms'][key]
                        if now['status']!=before['status']:raise ValueError('baseline support changed')
                        for metric in ['relative_joint_gradient_defect','relative_amplitude_precision_defect','endpoint_RC_max_error_V','endpoint_Hh_error_V']:
                            if abs(now['metrics'][metric]-before['metrics'][metric])>1e-7*max(1,abs(before['metrics'][metric])):
                                raise ValueError('baseline metric changed: '+metric)
                probes.append(row)
            data=np.vstack(chunks)
            fits=fit_prefix(fields,model,data,mean,L)
            snapshots={}
            for name,f in fields.items():snapshots[name+'_root']=f.root;snapshots[name+'_state']=f.state
            file=args.out/f"{old['load']}_{prefix['records']}_factors.npz";np.savez_compressed(file,**snapshots)
            prefixes.append(dict(records=prefix['records'],observation_sha256=digest.hexdigest(),probes=probes,fits=fits,
                                 snapshot=dict(path=str(file),identity=identity(file)),direct_prefix_workspace_B=data.nbytes))
            result=dict(load=old['load'],baseline_result=dict(path=str(path),identity=identity(path)),prefixes=prefixes,
                        storage={name:f.storage() for name,f in fields.items()})
            write(args.out/f"{old['load']}.json",result)
            print(json.dumps(dict(stage='prefix_complete',load=old['load'],records=prefix['records'])),flush=True)
        summary.append(dict(load=old['load'],file=f"{old['load']}.json",identity=identity(args.out/f"{old['load']}.json")))
    verify_sources(sources)
    if identity(protocol)!=registration['protocol']:raise ValueError('protocol changed')
    write(args.out/'summary.json',dict(status='completed_exploration_not_promoted',cases=summary,
          scope='Finite public probes and local fits/forecast comparisons, not truth accuracy or calibrated coverage'))


if __name__=='__main__':main()
