#!/usr/bin/env python3
"""Saved-evidence analysis only: no sampling, model evaluation or truth scoring."""
import json
from pathlib import Path
import sys
import numpy as np
from common import HERE,ROOT,runner,save,smc,posterior


def analyze(attempt,out):
    out.mkdir(parents=True)
    receipt=json.loads((attempt/'receipt.json').read_text())
    manifest=json.loads((attempt/'manifest.json').read_text())
    for name,expected in manifest['sources'].items():
        if runner.identity(ROOT/name)!=expected:raise RuntimeError('original source changed: '+name)
        if runner.identity(attempt/'source_snapshot'/name)!=expected:raise RuntimeError('snapshot changed: '+name)
    cfg=json.loads((attempt/'inputs/inference.json').read_text())
    qualifier=json.loads((attempt/'qualification/receipt.json').read_text())
    if qualifier['status']!='passed':raise RuntimeError('adapter qualification not passed')
    results=[]
    for original in receipt['prefix_results']:
        n=original['prefix'];folder=attempt/f'prefix_{n}'
        population_rows=[]
        for f in sorted(folder.glob('population_*.json')):
            row=json.loads(f.read_text());population_rows.append(row)
            with np.load(f.with_suffix('.npz'),allow_pickle=False) as data:
                nparticles=int(f.stem.split('_')[1][1:])
                if data['particles'].shape!=(nparticles,16+2*n):raise RuntimeError('invalid path shape')
                if data['projected'].shape!=(len(data['particles']),20):raise RuntimeError('invalid projected shape')
        child=next((c for c in receipt['children'] if c['command'][2].endswith('worker.py')
                    and c['command'][3:5]==['posterior',str(n)]),None)
        row=dict(prefix=n,status=original['status'],source_elapsed_s=n/35,
                 dimension=16+2*n,saved_populations=len(population_rows),
                 process_CPU_s=child['CPU_s'] if child else None,
                 process_peak_RSS_bytes=child['peak_RSS_bytes'] if child else None,
                 captured_population_model_steps=sum(p['actual_model_steps'] for p in population_rows),
                 model_steps_exact=original['status']=='finite_moment_checks_passed')
        if population_rows:
            row.update(population_CPU_s=[p['CPU_s'] for p in population_rows],
                stages=[len(p['stages']) for p in population_rows],
                final_acceptance=[p['stages'][-1]['accepted_fraction'] for p in population_rows],
                surviving_initial_ancestors=[p['stages'][-1]['surviving_initial_ancestors'] for p in population_rows],
                ancestor_fraction_is_not_posterior_ESS=True)
        if original['status']=='finite_moment_checks_passed':
            levels=[]
            for level,nparticles in enumerate(cfg['particle_levels']):
                populations=[]
                for replicate in range(1,5):
                    seed=800000+1000*n+100*level+replicate
                    stem=folder/f'population_n{nparticles}_seed{seed}'
                    p=json.loads(stem.with_suffix('.json').read_text())
                    with np.load(stem.with_suffix('.npz'),allow_pickle=False) as data:p['projected']=data['projected']
                    populations.append(p)
                levels.append(smc.level(populations))
            gate=smc.assess(*levels,posterior.SCALES)
            if gate!=original['adequacy']:raise RuntimeError('saved gate mismatch')
            row.update(adequacy=gate,capacity_component_probability=original['capacity_component_probability'],
                       capacity_component_probability_MCSE=original['capacity_component_probability_MCSE'])
        else:
            row['adequacy']='not_computed; required independent refinement incomplete or unlaunched'
        results.append(row)
    children_CPU=sum(c['CPU_s'] for c in receipt['children'])
    summary=dict(status='closed_scaling_assessment_with_resource_limit',prefixes=results,
        cost_probes=[{k:r[k] for k in ('prefix','dimension','elapsed_s','median_CPU_s_per_evaluated_path',
            'one_4096_path_matrix_bytes','one_dense_covariance_bytes')} for r in receipt['cost_probes']],
        total_CPU_s=receipt['CPU_s'],declared_CPU_s=cfg['caps']['CPU_s'],
        CPU_overrun_s=max(0.,receipt['CPU_s']-cfg['caps']['CPU_s']),
        waited_children_CPU_s=children_CPU,parent_accounted_CPU_s=receipt['CPU_s']-children_CPU,
        peak_worker_RSS_bytes=max(c['peak_RSS_bytes'] for c in receipt['children']),
        missing_32_record_populations=[dict(particles=4096,seed=s) for s in (832103,832104)
            if not (attempt/f'prefix_32/population_n4096_seed{s}.npz').exists()],
        CPU_guard_limitation='Inherited supervisor gives child the remaining CPU limit, but active parent monitoring adds CPU before wait4 accounting. Combined budget checked after closure; recorded overrun remains explicit.',
        numerical_conclusion='8records pass;32records unresolved from compute exhaustion;128posterior not tested',
        next_recommendation='Before any separately registered completion, account for live parent+child CPU with stopping headroom. Reuse six saved32-record populations; only two4096-particle populations remain. Keep thresholds and solver fixed to distinguish compute insufficiency from mixing failure.',
        new_sampling_calls=0,new_model_steps=0,truth_scoring_performed=False,
        coverage_validated=False,density_contrast_gate_qualified=False,target_measured=False,
        source_review_independent=False)
    files=sorted(p for p in attempt.rglob('*') if p.is_file())
    save(out/'bindings.json',dict(source_manifest=runner.identity(attempt/'manifest.json'),
        analysis_source=runner.identity(HERE/'analyze.py'),
        files={str(p.relative_to(ROOT)):runner.identity(p) for p in files}))
    save(out/'summary.json',summary)
    print(json.dumps(dict(status=summary['status'],CPU_s=summary['total_CPU_s'],
                         prefixes=[{'prefix':r['prefix'],'status':r['status']} for r in results]),indent=2))


if __name__=='__main__':analyze(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve())
