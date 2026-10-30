"""Bind conditional derivation, finite controls and next-gate specification."""
import json
from collections import Counter
from .witnesses import HERE, ROOT, PROOF, identity, write


def main():
    reservation = json.loads((HERE/'attempt001/reservation.json').read_text())
    result = json.loads((HERE/'attempt001/result.json').read_text())
    for path, expected in reservation['source_identities'].items():
        assert identity(ROOT/path) == expected, path
        assert identity(HERE/'attempt001/source_snapshot'/path) == expected, path
    for path, expected in reservation['preserved_artifacts'].items():
        assert identity(ROOT/path) == expected, path
    assert result['checks_failed'] == 0 and result['checks_passed'] == 844
    assert all(c['passed'] for c in result['checks'])
    claims = json.loads((PROOF/'claims.json').read_text())
    assert len(claims['claims']) == 10 and not claims['full_battery_closure']
    graph = json.loads((PROOF/'dependencies.json').read_text())
    pairs = graph['upper_triangular_coefficients']
    assert len(pairs) == 55 and len({(p['i'], p['j']) for p in pairs}) == 55
    for p in pairs:
        left = set(graph['row_columns'][p['i']]['coordinates'])
        right = set(graph['row_columns'][p['j']]['coordinates'])
        assert set(p['coordinates']) == left | right
    assert Counter(len(p['coordinates']) for p in pairs) == {0:1, 1:15, 2:19, 3:18, 4:2}
    comparisons = {}
    for label in ('C_likelihood', 'merged_likelihood', 'associated_likelihood',
                  'C_endpoint', 'C_voltage_series', 'gram_merge', 'gram_associativity', 'OCV/', 'quadrature'):
        c = [q for q in result['checks'] if label in q['name'] and 'max_absolute_error' in q]
        comparisons[label] = dict(count=len(c), maximum_absolute_error=max(q['max_absolute_error'] for q in c))
    summary = dict(schema='partitioned_battery_closure_summary_v1',
        status='P3_structure_nonclosure_and_error_obligations_derived_conditional_witnesses_passed',
        source_revision=reservation['git_revision'], branch=reservation['branch'],
        identity_scope='Source snapshots and hashes include uncommitted work; revision alone is insufficient',
        report='experiments/partitioned_battery_closure_001/README.md',
        derivation='proofs/partitioned_battery_001/derivation.md',
        contract='proofs/partitioned_battery_001/contract.json',
        dependencies='proofs/partitioned_battery_001/dependencies.json',
        next_gate='proofs/partitioned_battery_001/next_gate.json',
        result='experiments/partitioned_battery_closure_001/attempt001/result.json',
        verification='experiments/partitioned_battery_closure_001/verification.json',
        written_conditional_claims=10, finite_checks=844, independent_review=False,
        principal_results=[
            'Exact fixed-eta nine-amplitude quadratic and chronological compatible-point operator composition',
            '55 underlying coefficient functions depend on at most four nonlinear coordinates individually; full posterior still joint16',
            'Exact Mobius transport for the existing tanh OCV; distinct poles and RC exponentials obstruct a fixed finite exact additive likelihood span',
            'Original support/chart measure and bounded per-record aging normalizers prevent automatic Gaussian closure',
            'Voltage residual envelope implies explicit accumulated likelihood and conditional physical-query bounds under shared exact maps/support'],
        nonlinear_dependency_histogram=graph['counts_by_nonlinear_dimension'],
        comparisons=comparisons, controls={k:result['evidence'][k] for k in ('aging', 'bounded_kernel', 'error_budget')},
        storage_B=dict(conditional_square_root=440, per_node_with_eta_and_transport=560,
                       shared_charge_extrema_time_count=40, one_conditional_node=600,
                       sixteen_conditional_nodes=9000, selected_node_count=None, complete_subsystem=None),
        resources=dict(cpu_seconds=result['cpu_seconds'], wall_seconds=result['wall_seconds'],
                       maximum_RSS_B=result['maximum_RSS_B'], compilation_excluded=True,
                       scope='Small algebraic controls, not estimator throughput'),
        preserved_launch_issue='development_import001/receipt.json: missing optional SciPy import before reservation; replaced by standard-library erfc, no model/tolerance change',
        next='Stationary conditional operator-field prototype with joint residual/outgoing-state envelopes on declared domains; full ownership/support and peak-live-memory audit before further fitting',
        full_battery_closure=False, finite_gallery_size_proved=False, numerical_lifetime_bound=None,
        physical_query_error_allocation=None, RC_aging_convention_selected=False,
        battery_fits=0, particle_steps=0, production_solver_changed=False,
        aging_calibrated=False, ten_year_certificate=False, deployment_qualified=False)
    write(HERE/'summary.json', summary)
    files = sorted(p for directory in (HERE, PROOF) for p in directory.rglob('*')
                   if p.is_file() and '__pycache__' not in p.parts and p != HERE/'verification.json')
    write(HERE/'verification.json', dict(status='passed', finite_checks=844,
        preserved_earlier_artifacts=len(reservation['preserved_artifacts']),
        graph_coefficients_verified=55, artifacts={str(p.relative_to(ROOT)):identity(p) for p in files},
        scope='Evidence/source preservation, graph consistency and finite conditional controls; no full nonlinear closure or lifetime certificate'))
    print(json.dumps(dict(status='passed', finite_checks=844, artifacts=len(files),
                         preserved_earlier_artifacts=len(reservation['preserved_artifacts']))))


if __name__ == '__main__':
    main()
