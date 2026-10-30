"""Post-attribution exact-component controls; no new compressed candidate."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
import json
from pathlib import Path
import shutil
import sys
import numpy as np
from analyze import HERE,ROOT,OLD,FIXED,Harness,ptr,identity,save,Partition
from response import ResponseBasis,exact_trace,approximate_parts,summarize

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=False)
plan=json.loads((HERE/'followup_plan.json').read_text());primary_plan=json.loads((HERE/'plan.json').read_text())
paths=[HERE/'followup.py',HERE/'followup_plan.json',HERE/'analyze.py',HERE/'response.py',HERE/'plan.json',
       HERE/'attempt001/receipt.json',OLD/'partition.py',FIXED/'basis.py',OLD/'comparison001/provider.so',
       HERE.parent/'history_provider_001/qualify.py',ROOT/primary_plan['inputs']]
bindings={str(p.relative_to(ROOT)):identity(p) for p in paths}
for p in paths:
    dest=out/'sources'/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
save(out/'reservation.json',dict(plan=plan,sources=bindings,command=sys.argv,status='before_followup_evaluation'))
inp=json.loads((ROOT/primary_plan['inputs']).read_text());points=np.array(inp['queries'][:97]);rows=[]
h=Harness(OLD/'comparison001/provider.so');lower=np.array(inp['lower']);upper=np.array(inp['upper'])
for raw in inp['raw_cycle']:
    row=np.zeros(3)
    if h.lib.hp_decode(*raw,ptr(row)):raise RuntimeError('decode')
    rows.append(row)
rows=np.tile(rows,(64,1));limits=[(upper[11]-1)*np.exp(lower[5]),lower[11]*np.exp(lower[5])]
arm=next(a for a in primary_plan['candidate_arms'] if a['name']=='physical_hysteresis');steps=0;results=[]
for n in plan['prefixes']:
    proposed=n*(97+65)
    if plan['prior_model_steps_upper']+steps+proposed>plan['aggregate_cap']:raise RuntimeError('aggregate work cap')
    steps+=proposed;obs=rows[:n];charges=np.cumsum(obs[:,0]*obs[:,1]/3600)
    exact,offset,_,_,_=exact_trace(obs,points)
    basis=ResponseBasis(arm,'public_half_SD',h.mean,h.sd,lower,upper);full=basis.rows(obs);p=Partition(basis,12,limits)
    approx,_=approximate_parts(basis,p,full,obs,charges,points)
    reference=summarize(approx,exact,offset,list(range(97)))
    results.append(dict(records=n,substitution='none',score=reference))
    for label,indices in plan['substitutions'].items():
        trial=approx.copy();trial[:,:,indices]=exact[:,:,indices]
        result=summarize(trial,exact,offset,list(range(97)))
        if result['attribution_identity_max_gap']>2e-8:raise AssertionError('attribution identity')
        results.append(dict(records=n,substitution=label,score=result))
if not all(identity(ROOT/name)==value for name,value in bindings.items()):raise RuntimeError('sources changed')
result=dict(status='completed',results=results,model_steps_upper=steps,
            aggregate_model_steps_upper=plan['prior_model_steps_upper']+steps,
            compressor_qualified=False,optimizer_calls=0,truth_reads=0)
save(out/'receipt.json',result)
print(json.dumps(dict(status=result['status'],aggregate_model_steps_upper=result['aggregate_model_steps_upper'],
    controls=[dict(records=r['records'],substitution=r['substitution'],oscillation=r['score']['error_oscillation_NLL']) for r in results]),indent=2))
