#!/usr/bin/env python3
"""Explicit finite continuation of development002; preserve every old result."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
from dataclasses import replace
import json
from pathlib import Path
import shutil
import sys
import numpy as np
import model as m
import posterior
import smc
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE.parent/'fixed_prefix_shape_001'))
import runner


def save(path,value):
    def convert(v):
        if isinstance(v,np.ndarray):return v.tolist()
        if isinstance(v,np.generic):return v.item()
        raise TypeError(type(v).__name__)
    with path.open('x') as f:json.dump(value,f,default=convert,indent=2,allow_nan=False);f.write('\n')


def validate(plan):
    for name,expected in plan['inputs'].items():
        if runner.identity(ROOT/name)!=expected:raise RuntimeError('changed completion input: '+name)
    old=json.loads((HERE/'qualification/development002/manifest.json').read_text())
    for name,expected in old['sources'].items():
        if runner.identity(ROOT/name)!=expected:raise RuntimeError('changed qualified source: '+name)


def worker(out):
    plan=json.loads((HERE/'completion_plan.json').read_text());validate(plan)
    source_plan=json.loads((HERE/'plan.json').read_text())
    records=tuple(m.k.Record('fixture',i,*row) for i,row in enumerate(source_plan['qualification']['dynamic_records']))
    profile=m.k.Profile(tuple(source_plan['qualification']['dynamic_rates']))
    used=actual=checks=0
    def check(ok,label):
        nonlocal checks
        checks+=1
        if not ok:raise AssertionError(label)
    def persist(name,n,seed,result):
        np.savez_compressed(out/f'{name}_n{n}_seed{seed}.npz',particles=result['particles'],projected=result['projected'])
        save(out/f'{name}_n{n}_seed{seed}.json',{k:v for k,v in result.items() if k not in ('particles','projected')})
    result={'status':'failed','automatic_retries':0,'completed_new_population_artifacts':0}
    try:
        for row in plan['complete_populations']:
            remaining=plan['caps']['conservative_physical_steps']-used
            target=m.Target(records,profile,max_paths=remaining//len(records))
            population=smc.population(target,smc.Config(row['particles']),row['seed'])
            persist('dynamic_conditioned',row['particles'],row['seed'],population)
            used+=target.path_evaluations*len(records)
            actual+=target.model_steps
            result['completed_new_population_artifacts']+=1
        # Reconstruct summaries exclusively from bound populations. No target
        # evaluation, resampling or cherry-picking occurs in this aggregation.
        previous=HERE/'qualification/development002'
        refinements={}
        for name,offset in [('dynamic_prediction',0),('dynamic_conditioned',10000)]:
            levels=[]
            for n,seeds in zip(source_plan['numerics']['full_particle_levels'],
                    (source_plan['numerics']['full_population_seeds_low'],source_plan['numerics']['full_population_seeds_high'])):
                populations=[]
                for s in seeds:
                    stem=f'{name}_n{n}_seed{s+offset}'
                    location=previous if (previous/(stem+'.npz')).exists() else out
                    pop=json.loads((location/(stem+'.json')).read_text())
                    with np.load(location/(stem+'.npz'),allow_pickle=False) as arrays:
                        pop['particles']=arrays['particles'];pop['projected']=arrays['projected']
                    populations.append(pop)
                levels.append(smc.level(populations))
            refinements[name]=dict(levels=levels,adequacy=smc.assess(*levels,posterior.SCALES))
            save(out/(name+'_summary.json'),refinements[name])
        report=posterior.boundary_report(records,refinements['dynamic_prediction'],refinements['dynamic_conditioned'])
        save(out/'boundary_report.json',report)
        check(report['posterior_numerical_status']=='finite_moment_checks_passed','dynamic joint numerical adequacy')
        check(np.all(np.diag(report['current_covariance'])[:16]>0),'all16 dynamic quantities uncertain')
        check(report['valid_observation_count']==4 and report['owns_initial_prior'],'factor ownership')
        # Small actual public-API call exercises both paths and failure-status
        # propagation. Its small populations do not replace the refined study.
        def api_account(target):
            nonlocal used,actual
            used+=target.path_evaluations*len(target.records)
            actual+=target.model_steps
        study=posterior.Study((32,64),((501,502,503,504),(601,602,603,604)),
                              max_paths_per_population=50000)
        check(used+16*50000<=plan['caps']['conservative_physical_steps'],'reserve whole API test work before launch')
        api=posterior.solve((m.k.Record('fixture',0,0.,0.,3.86),),m.k.Profile((0.,)*8),study,
            lambda name,n,seed,p:persist('api_'+name,n,seed,p),api_account)
        save(out/'api_report.json',api['report'])
        check(api['report']['elapsed_s']==0 and api['report']['valid_observation_count']==1,'zero-time observation consumed once')
        expected=all(api[name]['adequacy']['status']=='finite_moment_checks_passed' for name in ('prediction','conditioning'))
        check((api['report']['posterior_numerical_status']=='finite_moment_checks_passed')==expected,'public status matches both numerical gates')
        check(api['report']['current_covariance'].shape==(17,17),'public joint covariance includes derived Q')
        validate(plan)
        result.update(status='passed',dynamic_adequacy=report['posterior_numerical_status'],
            reused_population_artifacts=14,new_refinement_population_artifacts=2,api_populations=16,
            previous_seven_passed_cases_preserved=True,coverage_validated=False,density_contrast_gate_qualified=False)
    except Exception as exc:
        import traceback
        result['error']=traceback.format_exc()
    result.update(checks=checks,conservative_physical_steps_reserved=used,actual_physical_steps=actual)
    save(out/'checks.json',result);print(json.dumps(result,indent=2),flush=True)
    return 0 if result['status']=='passed' else 1


def main(out):
    out.mkdir(parents=True)
    plan=json.loads((HERE/'completion_plan.json').read_text());validate(plan)
    old=json.loads((HERE/'qualification/development002/manifest.json').read_text())
    names=list(old['sources'])+[str((HERE/n).relative_to(ROOT)) for n in ('complete.py','completion_plan.json')]
    sources={n:runner.identity(ROOT/n) for n in names}
    for n in names:
        dest=out/'source_snapshot'/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,dest)
    command=[sys.executable,'-B',str(HERE/'complete.py'),'worker',str(out)]
    runner.save(out/'manifest.json',dict(base_revision=old['base_revision'],sources=sources,
        source_binding='Unchanged development002 arithmetic plus separately frozen completion supervisor/plan',
        command=command,inputs=plan['inputs']))
    caps=plan['caps'];budget=runner.Budget(out,cpu=caps['CPU_s'],wall=caps['wall_s'],rss=caps['RSS_bytes'],output=caps['output_bytes'])
    receipt=dict(status='failed',automatic_retries=0,independent_review=False)
    try:
        budget.run(command,'completion');validate(plan)
        if {n:runner.identity(ROOT/n) for n in names}!=sources:raise RuntimeError('source changed')
        budget.check();receipt['status']='passed'
    except Exception as exc:receipt['error']=type(exc).__name__+': '+str(exc)
    receipt.update(children=budget.children,CPU_s=budget.used_cpu(),output_bytes_before_receipt=budget.output_bytes())
    runner.save(out/'receipt.json',receipt);print(json.dumps(receipt,indent=2))
    return 0 if receipt['status']=='passed' else 1


if __name__=='__main__':
    if sys.argv[1]=='worker':raise SystemExit(worker(Path(sys.argv[2])))
    raise SystemExit(main(Path(sys.argv[1]).resolve()))
