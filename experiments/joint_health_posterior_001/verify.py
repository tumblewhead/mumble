#!/usr/bin/env python3
"""Verify frozen evidence and recompute final gates; no new sampling or fits."""
import hashlib
import json
from pathlib import Path
import numpy as np
import smc
import posterior
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def identity(p):
    return dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())


def main():
    review=json.loads((HERE/'result_review.json').read_text())
    for name,expected in review['evidence_identities'].items():
        assert identity(ROOT/name)==expected, 'evidence changed: '+name
    final=HERE/'qualification/completion001'
    previous=HERE/'qualification/development002'
    manifest=json.loads((ROOT/review['qualified_arithmetic_manifest']).read_text())
    for name,expected in manifest['sources'].items():
        assert identity(ROOT/name)==expected, 'qualified source changed: '+name
        assert identity(final/'source_snapshot'/name)==expected, 'snapshot changed: '+name
    old=json.loads((previous/'checks.json').read_text())
    assert [r['name'] for r in old['cases'] if r['status']=='passed']==review['seven_passed_case_names']
    assert old['status']=='failed', 'original failure must remain failed'
    assert json.loads((final/'checks.json').read_text())['status']=='passed'
    plan=json.loads((HERE/'plan.json').read_text())
    names=('gaussian','mixture','scalar_r','stationary','dynamic_prediction','dynamic_conditioned')
    results={}
    for name in names:
        levels=[]
        offset=10000 if name=='dynamic_conditioned' else 0
        for n,seeds in zip(plan['numerics']['full_particle_levels'],
                (plan['numerics']['full_population_seeds_low'],plan['numerics']['full_population_seeds_high'])):
            populations=[]
            for seed in seeds:
                stem=f'{name}_n{n}_seed{seed+offset}'
                folder=previous if (previous/(stem+'.npz')).exists() else final
                row=json.loads((folder/(stem+'.json')).read_text())
                with np.load(folder/(stem+'.npz'),allow_pickle=False) as data:
                    row['projected']=data['projected']
                assert row['projected'].shape[0]==n
                populations.append(row)
            levels.append(smc.level(populations))
        scales=posterior.SCALES if len(levels[-1]['mean'])==20 else np.ones(2)
        gate=smc.assess(*levels,scales)
        assert gate['status']=='finite_moment_checks_passed', name
        location=final if name.startswith('dynamic_') else previous
        saved=json.loads((location/(name+'_summary.json')).read_text())
        for field in ('mean','covariance','mean_MCSE','quantiles'):
            assert np.allclose(levels[-1][field],saved['levels'][-1][field],atol=1e-13,rtol=1e-13),name+field
        results[name]=gate['status']
    print(json.dumps(dict(status='passed',bound_evidence_files=len(review['evidence_identities']),
        recomputed_refinement_queries=results,new_populations=0,new_model_steps=0),indent=2))


if __name__=='__main__':main()
