"""Paired hysteresis-degree/coordinate intervention, same physical support and inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from .basis import BasisField
from experiments.partitioned_coefficients_001.run import Direct,compare
from experiments.foster_campaign_001.backend import ROOT,identity,prepare_c
from experiments.foster_campaign_001.compact import StimulusStream
from experiments.foster_feedback_001.estimator import Model
from experiments.hysteresis_refinement_001.field import build
from experiments.h7_history_quality_001.history import write,source_receipt,verify_sources


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--out',required=True,type=Path);p.add_argument('--baseline',type=Path,default=Path('experiments/partitioned_coefficients_001/followup002'));args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=False);reg=json.loads((args.baseline/'registration.json').read_text());config=reg['config'];queries=reg['queries'];center=reg['center']
    binary=build(args.out/'response');cbinary=prepare_c(args.out,35,config)[0];model=Model(cbinary,config);sources=source_receipt()
    write(args.out/'registration.json',dict(source=sources,protocol=identity(ROOT/'specifications/response_basis_attribution_001/README.md'),baseline_registration=identity(args.baseline/'registration.json'),queries=queries,config=config,center=center,response_binary=identity(binary),direct_binary=identity(cbinary)))
    results=[]
    for path in sorted(args.baseline.glob('case_*/result.json')):
        old=json.loads(path.read_text());recipe=old['recipe'];source=old['source_id'];stream=StimulusStream(config,recipe['cell'],recipe['case'],recipe['settings']);digest=hashlib.sha256()
        fields={f'R2_H{degree}_{coordinate}':BasisField(config,center,binary,degree,coordinate,source) for degree in (2,3) for coordinate in ('log','rate')}
        refs=[Direct(model,np.array(q['a']),np.array(q['s'])) for q in queries];timing={k:0. for k in fields};timing['direct_all_queries']=0.;prefixes=[]
        for prefix in old['prefixes']:
            target=prefix['records']
            while stream.index<target:
                first=stream.index;obs,_,_=stream.read(min(1024,target-first))
                if stream.failure or not len(obs):raise ValueError('fixture stopped')
                digest.update(obs.astype('<f8',copy=False).tobytes())
                for name,field in fields.items():
                    start=time.process_time();field.update(first,obs,source);timing[name]+=time.process_time()-start
                start=time.process_time()
                for ref in refs:ref.advance(obs)
                timing['direct_all_queries']+=time.process_time()-start
            if digest.hexdigest()!=prefix['observation_sha256']:raise ValueError('baseline stream mismatch')
            records=[]
            for q,ref,prior_result in zip(queries,refs,prefix['queries']):
                a=np.array(q['a']);s=np.array(q['s']);record=dict(id=q['id'],selection=q['selection'],arms={},legacy_response_degree2=prior_result['arms']['response_degree2'],legacy_H7=prior_result['arms']['H7'])
                try:reference=ref.evaluate();record['direct']=dict(status='supported',nll=reference['nll'])
                except ValueError as e:reference=None;record['direct']=dict(status='unsupported',reason=str(e))
                scale=np.maximum(abs(a),[.1,.01,.01,.01,1.,.01,.01,.01,.01,.001,.001])
                for name,field in fields.items():
                    try:
                        value=field.evaluate(a,s);record['arms'][name]=dict(status='supported',metrics=compare(value,reference,scale) if reference else None)
                    except ValueError as e:record['arms'][name]=dict(status='unsupported',reason=str(e))
                if q['selection']=='public':
                    m=record['arms']['R2_H2_log'];oldm=record['legacy_response_degree2']
                    if m['status']!=oldm['status']:raise ValueError('legacy baseline status mismatch')
                    for key in ('relative_joint_gradient_defect','relative_amplitude_precision_defect','endpoint_RC_max_error_V','endpoint_Hh_error_V'):
                        if abs(m['metrics'][key]-oldm['metrics'][key])>1e-7*max(1,abs(oldm['metrics'][key])):raise ValueError('legacy metric mismatch')
                records.append(record)
            prefixes.append(dict(records=target,hours=target/35/3600,observation_sha256=digest.hexdigest(),queries=records,cumulative_cpu_s=timing.copy()))
            print(json.dumps(dict(load=old['load'],records=target,timing=timing)),flush=True)
        result=dict(load=old['load'],baseline_result=dict(path=str(path),identity=identity(path)),prefixes=prefixes,storage={k:f.storage() for k,f in fields.items()});results.append(result)
        write(args.out/f'case_{len(results)-1:04d}.json',result)
    verify_sources(sources);write(args.out/'summary.json',dict(status='completed_exploratory_not_qualified',cases=results))

if __name__=='__main__':main()
