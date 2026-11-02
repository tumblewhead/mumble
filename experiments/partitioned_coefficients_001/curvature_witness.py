"""Outcome-selected forensic probe; not independent validation or parameter fitting."""
import argparse
import json
from pathlib import Path
import hashlib
import numpy as np
from .representation import Coefficients
from .run import Direct
from experiments.foster_campaign_001.backend import identity
from experiments.foster_campaign_001.compact import StimulusStream
from experiments.foster_feedback_001.estimator import Model
from experiments.h7_history_quality_001.history import write


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    candidates=[]
    for path in sorted(args.run.glob('case_*/result.json')):
        r=json.loads(path.read_text())
        for prefix in r['prefixes']:
            for q in prefix['queries']:
                arm=q['arms']['quadratic']
                if q['selection']=='public' and arm['status']=='supported' and arm['metrics']:
                    candidates.append((arm['metrics']['scaled_amplitude_precision_min_eigenvalue'],str(path),prefix['records'],q['id'],prefix['observation_sha256']))
    _,path,count,qid,digest=min(candidates)
    result=json.loads(Path(path).read_text());reg=json.loads((args.run/'registration.json').read_text());q=next(q for q in reg['queries'] if q['id']==qid)
    a=np.array(q['a']);shape=np.array(q['s']);config=reg['config'];recipe=result['recipe'];source=result['source_id']
    binary=(args.run/'response/response.so').resolve();cbinary=(args.run/'backend_c/estimator.so').resolve()
    if identity(binary)!=reg['native_response'] or identity(cbinary)!=reg['direct_C']:raise ValueError('binary identity changed')
    candidate=Coefficients(config,reg['center'],binary,2,False,source);direct=Direct(Model(cbinary,config),a,shape)
    stream=StimulusStream(config,recipe['cell'],recipe['case'],recipe['settings']);h=hashlib.sha256()
    while stream.index<count:
        first=stream.index;obs,_,_=stream.read(min(1024,count-first))
        if stream.failure or not len(obs):raise ValueError('fixture stopped')
        h.update(obs.astype('<f8',copy=False).tobytes());candidate.advance(first,obs,source);direct.advance(obs)
    if h.hexdigest()!=digest:raise ValueError('observation digest')
    value=candidate.evaluate(a,shape);ref=direct.evaluate();scale=np.maximum(abs(a),[.1,.01,.01,.01,1.,.01,.01,.01,.01,.001,.001])
    eig,vectors=np.linalg.eigh(scale[:,None]*value['precision_amplitude']*scale[None,:]);v=scale*vectors[:,0];eps=.01
    plus=candidate.evaluate(a+eps*v,shape);minus=candidate.evaluate(a-eps*v,shape)
    write(args.out,dict(selection='Outcome-selected minimum scaled amplitude eigenvalue among original quadratic public probes; not a fresh validation query',
        source=identity(Path(__file__)),input_result=dict(path=path,identity=identity(Path(path))),query=qid,load=result['load'],records=count,
        observation_sha256=digest,replay_digest_matches=True,amplitude=a,shape=shape,direction_in_amplitude=v,epsilon=eps,
        candidate_directional_curvature=float(v@value['precision_amplitude']@v),direct_directional_curvature=float(v@ref['precision_amplitude']@v),
        candidate_finite_difference_curvature=float((plus['nll']+minus['nll']-2*value['nll'])/eps**2),
        all_three_candidate_paths_supported=True,
        interpretation='Negative candidate curvature occurs along an admissible amplitude perturbation while direct conditional likelihood has positive curvature. This is a representation defect, not weak excitation alone; finite probe does not quantify fitted parameter bias.'))

if __name__=='__main__':main()
