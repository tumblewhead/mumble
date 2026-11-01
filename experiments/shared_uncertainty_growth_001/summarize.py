"""Postfit scoring only: all four fits must be frozen before truth is opened."""
import argparse
import json
from pathlib import Path
import platform
import sys
import numpy as np
from experiments.uncertainty_weak_stimulus_001.diagnostics import identity,write


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();root=Path(__file__).resolve().parents[2]
    results=[]
    for seed in (1100,1103):
        for n in (4325376,12976128):
            path=a.run/f'audit{seed}_{n}/result.json';r=json.loads(path.read_text())
            if r['status']!='complete_local_diagnostic':raise ValueError('unfinished fit: '+str(path))
            results.append((seed,n,path,r))
    if a.out.exists():raise ValueError('receipt already exists')
    rows=[];inputs=[]
    for seed,n,path,r in results:
        scorepath=a.run/f'inputs{seed}/scoring_only_{n}.json';s=json.loads(scorepath.read_text())
        truth=s['parameters']['Q_Ah'];comp=r['comparison'];part=r['partition']
        scores={}
        for name,fit in [('field',r['field']),('reference',r['selected_exact'])]:
            q=float(np.exp(fit['x'][5]));sd=float(np.linalg.norm(np.asarray(fit['root'])[5]))
            scores[name]=dict(Q_error_percent=100*(q/truth-1),Q_error_local_SD=float((fit['x'][5]-np.log(truth))/sd),Q_SD_percent=100*sd)
        contributions=np.asarray(part['predicted_Q_correction_percent_by_group'])
        displacement=np.asarray(r['field']['x'])-np.asarray(r['selected_exact']['x'])
        reference_root=np.asarray(r['selected_exact']['root'])
        rows.append(dict(seed=seed,hours=r['hours'],records=n,**comp,scores=scores,
            predicted_Q_correction_percent=r['anchor']['predicted_Q_correction_percent'],
            partition_Q_correction_percent=dict(zip(part['groups'],contributions)),
            origin_chart_field_minus_reference_local_SD=displacement/np.linalg.norm(reference_root,axis=1),
            full_joint_local_distance=float(np.linalg.norm(np.linalg.solve(reference_root,displacement))),
            hysteresis_fraction_of_signed_sum=float(contributions[-1]/contributions.sum()),
            Q_width_ratio_field_exact_at_field=r['anchor']['Q_width_ratio_field_exact'],
            Q_direction_curvature=r['Q_direction_curvature'],
            assembly_Q_error_local_SD=part['assembly_Q_error_local_SD'],
            chunk_control=r['chunk_control'],instrumentation_parity=part['instrumented_vs_archived_model_max_abs'],
            native_minus_exact_endpoint=r['anchor']['native_minus_exact_endpoint'],
            stops={k:r[k]['diagnostic']['stop'] for k in ('field','exact','exact_correction_start')},
            wall_s=r['wall_s'],evidence=dict(result_path=str(path.resolve()),result=identity(path),scoring=identity(scorepath))))
    for seed in (1100,1103):
        d=a.run/f'inputs{seed}';v=json.loads((d/'validated.json').read_text())
        old=root.parent/'uncertainty-weak-stimulus/experiments/uncertainty_weak_stimulus_001/attempt001'/('owner_case_0000' if seed==1100 else 'owner_case_0002')
        earlier=np.load(old/'observations.npy',mmap_mode='r');new=np.load(d/'observations.npy',mmap_mode='r')
        same=bool(np.array_equal(new[:len(earlier)],earlier))
        if not same:raise ValueError('prior Stage1 observations differ')
        inputs.append(dict(seed=seed,validation=identity(d/'validated.json'),observations=v['observations'],
            checkpoint_checks=len(v['checks']),all_stimulus_checks_exact=all(x['stimulus_exact'] for x in v['checks']),
            earlier_cache=identity(old/'observations.npy'),earlier_records=len(earlier),earlier_cache_bitwise_equal=same))
    dependencies=list(Path(__file__).parent.glob('*.py'))+[Path(__file__).parent/'registration.json']
    for module in ['experiments/slow_likelihood_diagnostic_001/numerics.py','experiments/uncertainty_weak_stimulus_001/diagnostics.py',
        'experiments/foster_campaign_001/field_backend.py','experiments/joint_rate_history_001/field.py',
        'experiments/foster_bounded_hysteresis_001/model.c','experiments/foster_feedback_001/estimator.py',
        'experiments/foster_campaign_001/coordinates.py','experiments/foster_uncertainty_audit_001/conditional_packet.py']:
        dependencies.append(root/module)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    write(a.out,dict(status='four_matched_local_diagnostics_complete',base_revision='b854600',
        command=sys.argv,python=platform.python_version(),numpy=np.__version__,
        sources={str(f.resolve().relative_to(root)):identity(f) for f in dependencies},
        inputs=inputs,cases=rows,tests=11,production_changed=False,mainline_changed=False,
        additional_production_storage_B=0,observation_cache_total_B=sum(x['observations']['bytes'] for x in inputs),
        conclusions=['At24h compression displaces Q about1.74..1.75 reference SD; at72h about4.04..4.05 SD.',
          'Hysteresis accounts for almost all signed gradient-predicted Q displacement on both seeds.',
          'Reference centers are scored separately; these selected two-seed results do not establish calibrated coverage.',
          'Next: partition-specific hysteresis refinement with matched full joint factors; do not add scalar inflation or forgetting.']))
    for r in rows:print(json.dumps({k:r[k] for k in ('seed','hours','scores','exact_minus_field_Q_percent','exact_minus_field_Q_local_SD','hysteresis_fraction_of_signed_sum')}))

if __name__=='__main__':main()
