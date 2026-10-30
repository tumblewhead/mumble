"""Read-only evidence verification, then exclusive-write summary and receipt."""
import json
from .qualify import HERE, ROOT, ident, write


def main():
    main = json.loads((HERE/'attempt001/result.json').read_text())
    supplemental = json.loads((HERE/'support001/result.json').read_text())
    for name, result, key in [('attempt001', main, 'source_identities'), ('support001', supplemental, 'sources')]:
        assert result['status'] == 'passed' and not result['failed_checks']
        assert all(x['passed'] for x in result['checks'])
        reservation = json.loads((HERE/name/'reservation.json').read_text())
        for p, expected in reservation[key].items():
            assert ident(ROOT/p) == expected, p
            assert ident(HERE/name/'source_snapshot'/p) == expected, p
        for p, expected in reservation['preserved_artifacts'].items():
            assert ident(ROOT/p) == expected, p
    source_review = json.loads((HERE/'sources.json').read_text())
    matched = 0
    for entry in source_review['files']:
        actual = ident(HERE/'sources/naia'/entry['path'])
        assert actual == entry['retrieved_identity']
        if entry['locked_identity'] is not None:
            assert actual == entry['locked_identity']
            matched += 1
    total = main['passing_checks']+supplemental['passing_checks']
    summary = dict(schema='structured_joint_layout_summary_v1',
        status='joint_elimination_finitely_qualified_support_mass_and_complete_resources_open',
        report='experiments/structured_joint_001/README.md', derivation='experiments/structured_joint_001/derivation.md',
        support_addendum='experiments/structured_joint_001/support_addendum.md',
        result='experiments/structured_joint_001/attempt001/result.json', support_result='experiments/structured_joint_001/support001/result.json',
        verification='experiments/structured_joint_001/verification.json', sources='experiments/structured_joint_001/sources.json',
        source_revision='a3878e17c720ee399b458a005f47e809e4bdd5cc', branch='experiments/structured-joint-layout-001',
        identity_scope='Uncommitted sources bound by per-file hashes and snapshots; git HEAD alone does not contain these changes',
        finite_checks=total, main_checks=main['passing_checks'], supplemental_checks=supplemental['passing_checks'],
        preserved_earlier_artifacts=main['preserved_artifacts'],
        scm_review=dict(revision=source_review['revision'], scope=source_review['review_scope'],
                        files=len(source_review['files']), matching_selected_locked_files=matched,
                        A_informative_Q_support_width_reduction=0.4117918976069711,
                        original_matrix_status='FAIL', correction_completed=False,
                        semantics='necessary joint support constraints; not normalized likelihood posterior', remote_execution=False),
        findings=[
            'Common scalar voltage residuals couple physical partitions; conditional battery amplitude Gram is dense',
            'Block partition retains all uncertainty but saves no generic storage without retirement',
            'Chronological Markov separators can have bounded dimension, but message shape need not be Gaussian or bounded size',
            'Constrained elimination equals Gaussian marginal times joint support probability; scalar implementation and correlated controls pass',
            'Omitting the support mass can cause unbounded log error near the support boundary',
            'Normalized monotone transitions require state-dependent normalizers and carried nonquadratic shape'],
        storage=main['evidence']['storage'], adversaries=main['evidence']['adversaries'],
        gaussian=main['evidence']['gaussian'], constrained=main['evidence']['constrained'],
        support_evidence=supplemental['evidence'],
        resources=dict(main_cpu_seconds=main['cpu_seconds'], main_wall_seconds=main['wall_seconds'], maximum_RSS_B=main['maximum_RSS_B'],
                       scope='Main finite algebra tests, not estimator throughput; Python dense storage'),
        decision='Preserve a joint boundary quadratic plus explicit support/normalization factor; no independent parameter blocks selected',
        next_gate='Specify normalized monotone aging transition; small two-health thermal/SOC constrained-message retirement vs batch integral, with nuisance uncertainty and measured shape/query/resource errors',
        multivariate_constrained_solver_implemented=False, calibrated_aging_kernel=False,
        full_aging_battery_integrated=False, production_solver_changed=False,
        old_nonlinear_field_repaired=False, complete_SRAM_B=None, numerical_lifetime_bound=None,
        coverage_validated=False, deployment_qualified=False, ten_year_certificate=False)
    write(HERE/'summary.json', summary)
    files = sorted(p for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p != HERE/'verification.json')
    write(HERE/'verification.json', dict(status='passed', finite_checks=total,
          preserved_earlier_artifacts=main['preserved_artifacts'], matching_selected_scm_locks=matched,
          artifacts={str(p.relative_to(ROOT)): ident(p) for p in files},
          scope='Artifact integrity and finite controls; not trajectory reproduction or physical/firmware/lifetime certification'))
    print(json.dumps(dict(status='passed', checks=total, artifacts=len(files), matched_scm_locks=matched)))


if __name__ == '__main__': main()
