"""Verify immutable evidence and write a compact completion receipt."""
import json
from .qualify import HERE, ROOT, file_identity, write


def main():
    reservations = []
    for attempt in ('attempt001', 'attempt002'):
        r = json.loads((HERE/attempt/'reservation.json').read_text())
        reservations.append(r)
        for path, expected in r['source_identities'].items():
            assert file_identity(HERE/attempt/'source_snapshot'/path) == expected, path
        for path, expected in r['prior_artifacts'].items():
            assert file_identity(ROOT/path) == expected, path
    for path, expected in reservations[-1]['source_identities'].items():
        assert file_identity(ROOT/path) == expected, path
    old = json.loads((HERE/'attempt001/result.json').read_text())
    new = json.loads((HERE/'attempt002/result.json').read_text())
    assert old['checks_failed'] == 1 and old['checks_passed'] == 1240
    assert new['checks_failed'] == 0 and new['checks_passed'] == 1289
    assert all(c['passed'] for c in new['checks'])
    maxima = {}
    for key in ('operator_vs_batch', 'sequential_vs_batch', 'associativity',
                'grouped_vs_batch', 'conditional_entry', 'rolling/', 'repetition/'):
        checks = [c for c in new['checks'] if key in c['name'] and 'maximum_absolute_error' in c]
        maxima[key] = dict(comparisons=len(checks),
                          maximum_absolute_error=max(c['maximum_absolute_error'] for c in checks))
    summary = dict(schema='incremental_history_summary_v1',
        status='P1_reference_lifecycle_and_P2_closed_Gaussian_operator_finite_qualification_passed',
        parent_roadmap='proofs/ten_year_history_001/roadmap.json',
        source_revision=reservations[-1]['git_revision'], branch=reservations[-1]['branch'],
        source_identity_scope='Uncommitted sources bound by reservation hashes and preserved snapshots, not revision alone',
        report='experiments/incremental_history_001/README.md',
        derivation='experiments/incremental_history_001/derivation.md',
        result='experiments/incremental_history_001/attempt002/result.json',
        verification='experiments/incremental_history_001/verification.json',
        passing_checks=new['checks_passed'], first_attempt=dict(passed=1240, failed=1, preserved=True),
        vector_cases=24, repetition=new['repetition'], comparisons=maxima,
        real_arithmetic_representation_defect=0,
        admitted_family='Known linear Gaussian full-Euclidean operators; PSD process covariance including zero; strictly PD independent observation noise',
        numerical_defect_bound=None, actual_battery_model_defect_bound=None,
        mathematical_proof='Written conditional derivation, not proof-assistant or independent-review certification',
        storage_B=dict(packed_token_d3=224, packed_token_d16=4488,
                       packed_prior_d16=1216, packed_token_plus_prior_d16=5704,
                       dense_token_array_payload_d16=6408, dense_history_and_four_pending_d16=32040,
                       complete_subsystem=None, earlier_posterior_different_object=2544),
        resources=dict(cpu_seconds=new['cpu_seconds'], wall_seconds=new['wall_seconds'],
                       maximum_RSS_B=new['maximum_RSS_B'], scope='Small reference qualification; not estimator throughput'),
        P1='Prior-free token and atomic rolling reference lifecycle implemented; actual C/battery producer remains open',
        P2='Exact real-arithmetic closed-model composition with independent batch/sequential finite checks',
        next='P3 partitioned battery dependency/closure derivation, exact conditional pieces and residual functions, supported domain/query metric; no unstructured fitting sweep',
        open=['Actual battery token producer and C integration', 'Physical RC aging state transfer and calibrated transition uncertainty',
              'Finite nonlinear gallery closure/remainder and lifetime numerical bounds',
              'Actual maximum event rate, whole-subsystem SRAM/work, fresh causal qualification'],
        rolling_solver_changed=False, new_battery_fits=0, particle_steps=0,
        ten_year_simulation=False, ten_year_battery_certificate=False,
        coverage_validated=False, deployment_qualified=False)
    write(HERE/'summary.json', summary)
    files = sorted(p for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts
                   and p.name != 'verification.json')
    # Include any snapshotted predecessor verification file as evidence too.
    files += sorted(p for p in HERE.glob('attempt*/source_snapshot/**/verification.json'))
    write(HERE/'verification.json', dict(schema='incremental_history_verification_v1', status='passed',
        finite_checks=1289, preserved_foundation_artifacts=len(reservations[-1]['prior_artifacts']),
        artifacts={str(p.relative_to(ROOT)): file_identity(p) for p in sorted(set(files))},
        scope='Source/snapshot/result integrity and finite reference checks; no full battery or lifetime certificate'))
    print(json.dumps(dict(status='passed', checks=1289, artifacts=len(set(files)))))


if __name__ == '__main__':
    main()
