"""Matched mixed-term probes, joint fits and sampled load-voltage diagnostics."""
import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from .basis import SensitivityField, build as sensitivity_build
from experiments.hysteresis_mixed_completion_001.rc_control import RC5Control
from experiments.hysteresis_mixed_completion_001.run import fit_prefix, field_value
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


def soc_width_readouts(fields,model,obs,mean,L,report):
    """Full joint endpoint SOC widths; distinct anchor and fitted-reference comparisons."""
    exact=Exact(model,obs,mean,L,chunk=4096);reference_sd=None
    for name,row in report['arms'].items():
        if 'selected' not in row:continue
        fit=row['selected'];w=np.asarray(fit['w']);C=np.asarray(fit['root'])
        try:
            _,_,P,end,F=exact(w)
            directC=L@np.linalg.solve(np.linalg.cholesky(P).T,np.eye(16))
            anchor_sd=100*float(np.linalg.norm(F[0]@directC))
            candidate_sd=100*float(np.linalg.norm(F[0]@C))
            if min(anchor_sd,candidate_sd)<=0:raise ValueError('zero local width')
            value=dict(status='local_diagnostic',direct_same_anchor_SD_pp=anchor_sd,
                direct_transport_SD_pp=candidate_sd,direct_transport_to_same_anchor_ratio=candidate_sd/anchor_sd)
            if name=='direct' and row['status']=='converged':reference_sd=candidate_sd
            if name!='direct':
                try:
                    _,D=transported(fields[name],np.asarray(fit['x']))
                    native=100*float(np.linalg.norm(D[0]@C))
                    value.update(compressed_transport_status='supported',compressed_transport_SD_pp=native,
                        compressed_to_same_anchor_ratio=native/anchor_sd,
                        compressed_to_direct_transport_ratio=native/candidate_sd)
                except (ValueError,OverflowError,FloatingPointError) as e:
                    value.update(compressed_transport_status='unsupported',reason=str(e))
            row['SOC_width']=value
        except (ValueError,OverflowError,FloatingPointError,np.linalg.LinAlgError) as e:
            row['SOC_width']=dict(status='unresolved',reason=str(e))
    for row in report['arms'].values():
        value=row.get('SOC_width',{})
        if reference_sd is not None and row['status']=='converged' and value.get('status')=='local_diagnostic':
            value['reference_fit_SD_pp']=reference_sd
            value['direct_transport_to_reference_fit_ratio']=value['direct_transport_SD_pp']/reference_sd
            if 'compressed_transport_SD_pp' in value:
                value['compressed_to_reference_fit_ratio']=value['compressed_transport_SD_pp']/reference_sd
        else:value['fit_to_fit_status']='unresolved_candidate_or_reference'


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--baseline',type=Path,default=Path('experiments/partitioned_coefficients_001/followup002'))
    parser.add_argument('--loads',nargs='+',choices=['rest','multiscale','embedded'],default=['rest','multiscale','embedded'])
    parser.add_argument('--records',nargs='+',type=int,default=[126000])
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    reg=json.loads((args.baseline/'registration.json').read_text());config=reg['config'];center=reg['center'];queries=reg['queries']
    mean,L=prior(config);binary=build(args.out/'response');cbinary=prepare_c(args.out,35,config)[0];model=Model(cbinary,config)
    sbinaries={k:sensitivity_build(args.out/('response_'+k),k) for k in ['taylor2','hermite3']}
    sources=source_receipt()
    protocol=ROOT/'specifications/rc_sensitivity_basis_001/README.md'
    registration=dict(source=sources,protocol=identity(protocol),baseline_registration=identity(args.baseline/'registration.json'),
                      config=config,center=center,queries=queries,loads=args.loads,records=args.records,
                      sensitivity_binaries={k:identity(v) for k,v in sbinaries.items()},
                      new_artifacts={str(p.relative_to(ROOT)):identity(p) for p in [ROOT/'experiments/rc_sensitivity_basis_001/response.c',ROOT/'specifications/rc_sensitivity_basis_001/P1.md']},
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
                'Taylor2_H2':SensitivityField(config,center,sbinaries['taylor2'],'taylor2',source),
                'Hermite3_H2':SensitivityField(config,center,sbinaries['hermite3'],'hermite3',source),
                'R3_H2':SensitivityField(config,center,binary,'chebyshev3',source),
                'R5_H2':RC5Control(config,center,binary,'td2',source),
                'R5_H7':MixedField(config,center,1.,7,binary,source)}
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
            soc_width_readouts(fields,model,data,mean,L,fits)
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
    for name,expected in registration['new_artifacts'].items():
        if identity(ROOT/name)!=expected:raise ValueError('new artifact changed: '+name)
    if identity(protocol)!=registration['protocol']:raise ValueError('protocol changed')
    write(args.out/'summary.json',dict(status='completed_exploration_not_promoted',cases=summary,
          scope='Finite public probes and local fits/forecast comparisons, not truth accuracy or calibrated coverage'))


if __name__=='__main__':main()
