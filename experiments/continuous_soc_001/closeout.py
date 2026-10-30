"""Verify preserved evidence and summarize; never rerun or alter inference."""
import ast
import json
from pathlib import Path
from experiments.structured_joint_001.qualify import ident, write

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def read(path):
    return json.loads(path.read_text())


def main():
    checks = []

    def check(name, ok):
        checks.append(dict(name=name, passed=bool(ok)))

    for attempt in ['qualification001', 'qualification002', 'campaign001']:
        reservation = read(HERE / attempt / 'reservation.json')
        for path, expected in reservation['preserved_artifacts'].items():
            check(attempt + '/preserved/' + path, ident(ROOT / path) == expected)
        for path, expected in reservation['source_identities'].items():
            check(attempt + '/snapshot/' + path,
                  ident(HERE / attempt / 'source_snapshot' / path) == expected)
            # First attempt's qualifier contains the preserved faulty fixture.
            if attempt != 'qualification001':
                check(attempt + '/current_source/' + path, ident(ROOT / path) == expected)

    qualification = read(HERE / 'qualification002/result.json')
    check('qualification_passed', qualification['status'] == 'passed'
          and qualification['passing_checks'] == 168 and not qualification['failed_checks'])
    check('original_failure_retained', read(HERE / 'qualification001/result.json')['status'] == 'failed')
    check('native_build_passed', read(HERE / 'campaign001/build.json')['returncode'] == 0)
    manifest = read(HERE / 'campaign001/inputs/manifest.json')
    for case, entry in manifest.items():
        for suffix, key in [('observations', 'observation_identity'), ('truth', 'scoring_truth_identity')]:
            check(case + '/' + suffix, ident(HERE / 'campaign001/inputs' / (case + '_' + suffix + '.npy')) == entry[key])

    review = read(HERE / 'review001/result.json')
    for path, expected in review['input_identities'].items():
        check('review_input/' + path, ident(ROOT / path) == expected)
    for gate in review['gates']:
        for name, value in gate.items():
            if name != 'case':
                check(gate['case'] + '/' + name, value)

    cases = {}
    for case, reviewed in review['cases'].items():
        result = read(HERE / 'campaign001' / case / 'result.json')
        arm = result['arms']['float32']
        check(case + '/full_source_consumption', arm['records'] == 504000
              and arm['final']['readout']['source_next_index'] == 504000)
        check(case + '/fixed_hypothesis_count', all(
            row['arms']['float32']['hypotheses'] == 729 for row in result['checkpoints']))
        for phase in ['1', '2']:
            check(case + '/preferred_phase_' + phase,
                  arm['phase'][phase]['joint_preferred_count'] == arm['phase'][phase]['records'])
        failed = result['arms']['log16']
        check(case + '/fixed_log16_failure_explicit', failed['status'] == 'unresolved'
              and failed['records'] == 9532 and failed['retained_source_next_index'] == 9532)
        cases[case] = dict(
            observations=arm['records'], simulated_s=14400,
            wall_s=result['wall_seconds'], cpu_s=result['cpu_seconds'],
            last_joint_outside_s=arm['last_joint_outside_s'],
            phase=arm['phase'], final=arm['final'],
            maximum_history_Q_difference_percent=arm['maximum_history_Q_difference_percent'],
            maximum_history_SOC_difference_pp=arm['maximum_history_SOC_difference_pp'],
            checkpoint_uncertainty=reviewed['checkpoint_uncertainty'],
            log16_failure=failed['failure'], storage=arm['storage'])

    for path in HERE.glob('*.py'):
        ast.parse(path.read_text(), filename=str(path))
        check('python_syntax/' + path.name, True)
    rows = [step for case in qualification['cases'] for step in case['steps']]
    summary = dict(
        schema='continuous_soc_longrun_summary_v1',
        status='continuous_SOC_repair_and_two_4h_controls_passed_fixed_log16_range_rejected',
        source_revision=reservation['source_revision'], branch=reservation['branch'],
        qualification_checks=qualification['passing_checks'],
        prior_artifacts_preserved=qualification['preserved_earlier_artifacts'],
        short_oracle_maxima={key: max(abs(row[key]) for row in rows) for key in [
            'continuous_Q_error_percent', 'continuous_SOC_error_pp',
            'grid_Q_error_percent', 'grid_SOC_error_pp']},
        cases=cases, distinct_observations=1008000, simulated_hours_total=8,
        wall_seconds_total=sum(case['wall_s'] for case in cases.values()),
        retained_hypotheses=729, selected_diagnostic_encoding='binary32_centered_log_weights',
        partial_packed_payload_B=14580, complete_SRAM_B=None,
        preferred_scales=dict(Q_relative_percent=.5, SOC_percentage_points=.5),
        interpretation='Finite in-support reduced-model stream controls; no application-scale history degradation observed. Not coverage or lifetime qualification.',
        approximation='Conditional Gaussian moment projection and first-order OCV conditioning; discrete health/thermal/nuisance support',
        next='Compare overall system behavior on off-support cells, gradual aging, varied loads/noise and long weak use; define rolling/history source ownership before feedback. Optimize measured resource limits after behavior, not already-small codec point errors.',
        original_rolling_optimizer_integrated=False, production_changed=False,
        aging_calibrated=False, coverage_validated=False, lifetime_qualified=False)
    failures = [item for item in checks if not item['passed']]
    if failures:
        raise RuntimeError(json.dumps(failures))
    write(HERE / 'summary.json', summary)
    artifacts = {str(path.relative_to(ROOT)): ident(path) for path in sorted(HERE.rglob('*'))
                 if path.is_file() and '__pycache__' not in path.parts and path.name != 'verification.json'}
    write(HERE / 'verification.json', dict(status='passed', checks=checks,
          passing_checks=len(checks), artifacts=artifacts,
          scope='Saved-evidence identity, source-snapshot, practical gate and syntax checks; no new inference run'))
    print(json.dumps(dict(status='passed', checks=len(checks), artifacts=len(artifacts),
                         short_oracle_maxima=summary['short_oracle_maxima'],
                         wall_seconds_total=summary['wall_seconds_total'])))


if __name__ == '__main__':
    main()
