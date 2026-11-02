"""Readout-only SOC covariance supplement; never refits or overwrites original evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from .basis import CompletedField
from .rc_control import RC5Control
from experiments.response_basis_attribution_001.basis import BasisField
from experiments.hysteresis_refinement_001.field import MixedField,transported
from experiments.slow_likelihood_diagnostic_001.numerics import Exact
from experiments.foster_campaign_001.backend import ROOT,identity
from experiments.foster_campaign_001.compact import StimulusStream
from experiments.foster_feedback_001.estimator import Model
from experiments.h7_history_quality_001.history import source_receipt,verify_sources,write


def field_for(name,config,center,binary,source):
    if name=='R5_H7':return MixedField(config,center,1.,7,binary,source)
    if name.startswith('R5_H2'):
        kind={'R5_H2':'td2','R5_H2_c22':'c22','R5_H2_tensor':'tensor'}[name]
        return RC5Control(config,center,binary,kind,source)
    if name in ['R2_H2_c22','R2_H2_tensor']:
        return CompletedField(config,center,binary,'c22' if name.endswith('c22') else 'tensor',source)
    return BasisField(config,center,binary,3 if name=='R2_H3' else 2,'log',source)


def measure(directory):
    reg=json.loads((directory/'registration.json').read_text())
    manifest=json.loads((directory/'summary.json').read_text())
    config=reg['config'];mean=np.array(reg['prior_mean']);L=np.array(reg['prior_root'])
    binary=directory/'response/response.so';cbinary=directory/'backend_c/estimator.so'
    if identity(binary)!=reg['response_binary'] or identity(cbinary)!=reg['direct_binary']:raise ValueError('binary identity')
    model=Model(cbinary,config);rows=[];bindings={str(directory/'registration.json'):identity(directory/'registration.json')}
    for case in manifest['cases']:
        casepath=directory/case['file']
        if identity(casepath)!=case['identity']:raise ValueError('case identity')
        bindings[str(casepath)]=identity(casepath)
        data=json.loads(casepath.read_text());bp=Path(data['baseline_result']['path'])
        if identity(bp)!=data['baseline_result']['identity']:raise ValueError('baseline recipe identity')
        old=json.loads(bp.read_text());recipe=old['recipe']
        stream=StimulusStream(config,recipe['cell'],recipe['case'],recipe['settings'])
        digest=hashlib.sha256();chunks=[]
        for prefix in data['prefixes']:
            while stream.index<prefix['records']:
                obs,_,_=stream.read(min(777,prefix['records']-stream.index))
                if stream.failure or not len(obs):raise ValueError('regeneration failure')
                digest.update(obs.astype('<f8').tobytes());chunks.append(obs.copy())
            if digest.hexdigest()!=prefix['observation_sha256']:raise ValueError('observation identity')
            sp=Path(prefix['snapshot']['path'])
            if identity(sp)!=prefix['snapshot']['identity']:raise ValueError('snapshot identity')
            bindings[str(sp)]=identity(sp)
            with np.load(sp,allow_pickle=False) as saved:
                snapshot={k:saved[k].copy() for k in saved.files}
            exact=Exact(model,np.vstack(chunks),mean,L,chunk=4096)
            per=[];reference_sd=None
            for name,fit in prefix['fits']['arms'].items():
                row=dict(load=data['load'],records=prefix['records'],arm=name,fit_status=fit['status'])
                if 'selected' not in fit:
                    row['status']='no_selected_fit';per.append(row);continue
                chosen=fit['selected'];w=np.array(chosen['w']);x=np.array(chosen['x']);C=np.array(chosen['root'])
                if not np.allclose(x,mean+L@w,rtol=0,atol=1e-12):raise ValueError('origin coordinates')
                try:
                    _,_,P,end,F=exact(w)
                    localC=L@np.linalg.solve(np.linalg.cholesky(P).T,np.eye(16))
                    same_anchor=100*float(np.linalg.norm(F[0]@localC))
                    direct_transport=100*float(np.linalg.norm(F[0]@C))
                    if same_anchor<=0:raise ValueError('zero reference width')
                    row.update(status='local_diagnostic',direct_transport_SOC_SD_pp=direct_transport,
                        direct_same_anchor_SOC_SD_pp=same_anchor,
                        direct_transport_to_same_anchor_SD_ratio=direct_transport/same_anchor)
                    if name=='direct' and fit['status']=='converged':reference_sd=direct_transport
                    if name!='direct':
                        field=field_for(name,config,reg['center'],binary,old['source_id'])
                        field.state=snapshot[name+'_state'];field.root=snapshot[name+'_root'];field.count=prefix['records']
                        try:
                            _,D=transported(field,x)
                            native=100*float(np.linalg.norm(D[0]@C))
                            row.update(compressed_transport_status='supported',compressed_transport_SOC_SD_pp=native,
                                compressed_to_direct_transport_SD_ratio=native/direct_transport,
                                compressed_to_same_anchor_SD_ratio=native/same_anchor)
                        except (ValueError,OverflowError,FloatingPointError) as e:
                            row.update(compressed_transport_status='unsupported',reason=str(e))
                except (ValueError,OverflowError,FloatingPointError,np.linalg.LinAlgError) as e:
                    row.update(status='unresolved_readout',reason=str(e))
                per.append(row)
            for row in per:
                if reference_sd is not None and row['fit_status']=='converged' and row['status']=='local_diagnostic':
                    row['reference_fit_SOC_SD_pp']=reference_sd
                    row['direct_transport_to_reference_fit_SD_ratio']=row['direct_transport_SOC_SD_pp']/reference_sd
                    if 'compressed_transport_SOC_SD_pp' in row:
                        row['compressed_to_reference_fit_SD_ratio']=row['compressed_transport_SOC_SD_pp']/reference_sd
                else:row['fit_to_fit_status']='unresolved_candidate_or_reference'
            rows.extend(per)
    return dict(run=str(directory),input_bindings=bindings,rows=rows)


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--runs',nargs='+',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    if args.out.exists():raise ValueError('refuse overwrite')
    sources=source_receipt();protocol=ROOT/'specifications/hysteresis_mixed_completion_001/SOC_WIDTH_SUPPLEMENT.md'
    runs=[measure(directory) for directory in args.runs]
    verify_sources(sources)
    write(args.out,dict(status='completed_readout_only',source=sources,protocol=identity(protocol),runs=runs,
                       scope='Full joint local GN covariance and state transport; selected fits unchanged, not calibrated physical coverage'))


if __name__=='__main__':main()
