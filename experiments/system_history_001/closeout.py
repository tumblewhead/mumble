"""Read-only scientific/evidence checks followed by a compact receipt."""
import ast
import json
from .campaign import HERE, ROOT, CASES, read
from experiments.structured_joint_001.qualify import ident, write


def main():
    campaign=HERE/'campaign001';reservation=read(campaign/'reservation.json');checks=[]
    def check(name,ok):checks.append(dict(name=name,passed=bool(ok)))
    for p,expected in reservation['preserved_artifacts'].items():
        check('preserved/'+p,ident(ROOT/p)==expected)
    for p,expected in reservation['source_identities'].items():
        check('source/'+p,ident(ROOT/p)==expected)
        check('snapshot/'+p,ident(campaign/'source_snapshot'/p)==expected)
    qualification=read(campaign/'qualification/result.json')
    check('targeted_qualification',qualification['status']=='passed' and qualification['passing_checks']==45)
    check('native_binary',ident(campaign/'native.so')==qualification['native_identity'])
    check('strict_native_build',read(campaign/'build.json')['returncode']==0)
    manifest=read(campaign/'inputs/manifest.json')
    review=read(HERE/'review001/result.json')
    for p,expected in review['input_identities'].items():check('review_input/'+p,ident(ROOT/p)==expected)
    cases={}
    for name in CASES:
        for suffix in ['observations','truth']:
            check(name+'/'+suffix,ident(campaign/'inputs'/(name+'_'+suffix+'.npy'))==manifest[name][suffix])
        raw=read(campaign/name/'result.json');r=review['cases'][name]
        check(name+'/source_id',raw['source_id']==manifest[name]['source_id'])
        check(name+'/review_agreement',raw['arms']==r['arms'])
        for kind,arm in raw['arms'].items():
            check(name+'/'+kind+'/completion',arm['status']=='completed' and arm['records']==504000)
            expected=31500 if kind=='legacy' else 504000
            check(name+'/'+kind+'/score_count',arm['all']['count']==expected and
                  sum(b['count'] for b in arm['phase'].values())==expected)
        check(name+'/encoding_scale',r['gates']['encoding_preserves_preferred_scales'])
        check(name+'/shared_checkpoints',len(r['common_checkpoints'])==60)
        h=raw['arms']['float32'];b=h['all']
        cases[name]=dict(final_history=h['final'],final_legacy=raw['arms']['legacy']['final'],
            gates=r['gates'],max_history_Q_percent=h['max_history_Q_percent'],max_history_SOC_pp=h['max_history_SOC_pp'],
            max_SOC_error_pp=b['max_SOC_pp'],Q_3sd_miss_fraction=b['Q_3sd_misses']/b['count'],
            SOC_3sd_miss_fraction=b['SOC_3sd_misses']/b['count'],
            phases=h['phase'],wall_s=raw['wall_s'],cpu_s=raw['cpu_s'],legacy_wall_s=raw['arms']['legacy']['wall_s'])
    for p in HERE.glob('*.py'):
        ast.parse(p.read_text(),filename=str(p));check('syntax/'+p.name,True)
    if any(not c['passed'] for c in checks):raise RuntimeError(json.dumps([c for c in checks if not c['passed']]))
    summary=dict(schema='system_history_summary_v1',
        status='encoding_preservation_passes_capacity_generalization_and_uncertainty_fail',
        source_revision=reservation['source_revision'],branch=reservation['branch'],
        cases=cases,distinct_observations=2016000,simulated_hours=16,completed_estimator_runs=12,
        targeted_checks=45,preserved_earlier_artifacts=len(reservation['preserved_artifacts']),
        max_encoding_Q_difference_percent=max(r['max_history_Q_percent'] for r in cases.values()),
        max_encoding_SOC_difference_pp=max(r['max_history_SOC_pp'] for r in cases.values()),
        cpu_s_total=sum(r['cpu_s'] for r in cases.values()),
        execution='Four independent cases run concurrently, one BLAS thread each; wall times are per-case, not additive elapsed time',
        commands=['OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m experiments.system_history_001.campaign prepare',
                  'OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m experiments.system_history_001.campaign qualify',
                  *['OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m experiments.system_history_001.campaign run experiments/system_history_001/campaign001 '+name for name in CASES],
                  'MPLCONFIGDIR=/tmp/mumble-system-mpl OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m experiments.system_history_001.review',
                  'python3 -B -m experiments.system_history_001.closeout'],
        storage=dict(hypotheses=729,partial_history_payload_B=14580,decoded_primary_arrays_B=17496,
                     legacy_context_B=8680,complete_subsystem_B=None),
        finding='Numerical history preservation remains below preferred scales; unsupported intermediate health and gradual aging expose common capacity bias and false precision. UsefulSOC and near-unit voltage innovations do not validateQ.',
        next='Focused continuousQ/R health representation with jointSOC/nuisance uncertainty on frozen matched/between-node controls, then gradual aging. Preserve matched control and comparebinary32/64. Defer codec polishing, SRAM/runtime optimization and rolling feedback until behavior is addressed.',
        scope='Reduced history and unchanged legacy system compared independently on identical sources; legacy assumptions differ. No feedback integration or causal history-only legacy comparison.',
        production_changed=False,feedback_integrated=False,coverage_validated=False,lifetime_qualified=False)
    write(HERE/'summary.json',summary)
    artifacts={str(p.relative_to(ROOT)):ident(p) for p in sorted(HERE.rglob('*'))
               if p.is_file() and '__pycache__' not in p.parts and p.name!='verification.json'}
    write(HERE/'verification.json',dict(status='passed',passing_checks=len(checks),checks=checks,artifacts=artifacts,
          scope='Evidence/source identities, numerical completion, accounting and encoding checks. Scientific capacity/uncertainty failures are retained, not relabeled as passes.'))
    print(json.dumps(dict(status=summary['status'],verification_checks=len(checks),artifacts=len(artifacts),
                         preserved=len(reservation['preserved_artifacts']),cpu_s=summary['cpu_s_total'])))


if __name__=='__main__':main()
