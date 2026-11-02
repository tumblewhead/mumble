"""Replay frozen public queries and attribute square-root degree2 defects."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from .attribution import Attribution
from experiments.partitioned_coefficients_001.run import chart_shape_jacobian
from experiments.conditional_architecture_001.conditional import chart_amplitude_jacobian
from experiments.foster_uncertainty_audit_001.conditional_packet import chart_from
from experiments.foster_campaign_001.backend import ROOT,identity,prepare_c
from experiments.foster_campaign_001.compact import StimulusStream
from experiments.foster_feedback_001.estimator import Model
from experiments.joint_rate_history_001.field import Field,build
from experiments.hysteresis_refinement_001.field import features_jacobian
from experiments.h7_history_quality_001.history import write,source_receipt,verify_sources


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--out',required=True,type=Path);p.add_argument('--baseline',type=Path,default=Path('experiments/partitioned_coefficients_001/followup002'));args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=False);registration=json.loads((args.baseline/'registration.json').read_text())
    config=registration['config'];center=registration['center'];queries=[q for q in registration['queries'] if q['selection']=='public']
    binary=build(args.out/'response');cbinary=prepare_c(args.out,35,config)[0];model=Model(cbinary,config)
    sources=source_receipt();protocol=ROOT/'specifications/response_basis_attribution_001/README.md'
    write(args.out/'registration.json',dict(source=sources,protocol=identity(protocol),baseline_registration=identity(args.baseline/'registration.json'),queries=queries,config=config,response_binary=identity(binary),direct_binary=identity(cbinary)))
    results=[]
    for path in sorted(args.baseline.glob('case_*/result.json')):
        old=json.loads(path.read_text());recipe=old['recipe'];source=old['source_id'];stream=StimulusStream(config,recipe['cell'],recipe['case'],recipe['settings']);digest=hashlib.sha256()
        field=Field(config,center,1.,2,binary,source);field.m=field.n;states=[]
        for q in queries:
            a=np.array(q['a']);s=np.array(q['s']);x=chart_from(a,s);D=np.column_stack((chart_amplitude_jacobian(a),chart_shape_jacobian(s)))
            states.append(dict(x=x,D=D,W=field.features(x),DW=features_jacobian(field,x)@D,acc=Attribution(a)))
        prefixes=[]
        for prefix in old['prefixes']:
            target=prefix['records']
            while stream.index<target:
                first=stream.index;obs,_,_=stream.read(min(1024,target-first))
                if stream.failure or not len(obs):raise ValueError('fixture stopped')
                digest.update(obs.astype('<f8',copy=False).tobytes());rows=field.update(first,obs,return_rows=True)
                for state in states:
                    v,J,end,F=model.evaluate(state['x'],obs);exact_J=(J@state['D'])/obs[:,4,None];r=(v-obs[:,3])/obs[:,4]
                    state['acc'].advance(r,exact_J,rows@state['W'],rows@state['DW'],obs[:,4]);state['x']=end;state['D']=F@state['D']
            if digest.hexdigest()!=prefix['observation_sha256']:raise ValueError('baseline stream mismatch')
            reports=[]
            for query,state,original in zip(queries,states,[q for q in prefix['queries'] if q['selection']=='public']):
                residual=field.root@state['W'];J=field.root@state['DW'];report=state['acc'].report(J.T@residual)
                expected=original['arms']['response_degree2']['metrics']['relative_joint_gradient_defect']
                if abs(report['relative_total_gradient_defect']-expected)>1e-7*max(1,expected):raise ValueError('legacy baseline gradient mismatch')
                reports.append(dict(id=query['id'],baseline_relative_gradient_defect=expected,**report))
            prefixes.append(dict(records=target,observation_sha256=digest.hexdigest(),queries=reports))
            print(json.dumps(dict(load=old['load'],records=target,max_closure=max(q['relative_attribution_closure'] for q in reports))),flush=True)
        result=dict(load=old['load'],baseline_result=dict(path=str(path),identity=identity(path)),prefixes=prefixes);results.append(result)
        write(args.out/f'case_{len(results)-1:04d}.json',result)
    verify_sources(sources);write(args.out/'summary.json',dict(status='completed_diagnostic_not_qualified',cases=results))

if __name__=='__main__':main()
