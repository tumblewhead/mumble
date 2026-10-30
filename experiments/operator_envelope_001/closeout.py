"""Verify source preservation and summarize the prototype/centroid evidence."""
import json
from .qualify import HERE,ROOT,ident,write


def main():
    main_res=json.loads((HERE/'attempt001/reservation.json').read_text())
    causal_res=json.loads((HERE/'causal001/reservation.json').read_text())
    for folder,res in [('attempt001',main_res),('causal001',causal_res)]:
        for path,expected in res['source_identities'].items():
            assert ident(ROOT/path)==expected,path
            assert ident(HERE/folder/'source_snapshot'/path)==expected,path
    for path,expected in main_res['preserved_artifacts'].items():assert ident(ROOT/path)==expected,path
    result=json.loads((HERE/'attempt001/result.json').read_text())
    causal=json.loads((HERE/'causal001/result.json').read_text())
    assert result['passing_checks']==1717 and result['failed_checks']==0
    assert len(causal['checks'])==8 and all(q['passed'] for q in causal['checks'])
    assert all(q['passed'] for q in result['checks'])
    summary=dict(schema='operator_envelope_centroid_summary_v1',
        status='prototype_error_accounting_and_centroid_controls_passed_fixed_center_field_not_adequate',
        report='experiments/operator_envelope_001/README.md',derivation='experiments/operator_envelope_001/derivation.md',
        result='experiments/operator_envelope_001/attempt001/result.json',
        causal_control='experiments/operator_envelope_001/causal001/result.json',
        figure='experiments/operator_envelope_001/attempt001/envelope_and_centroid.pdf',
        verification='experiments/operator_envelope_001/verification.json',
        source_revision=main_res['revision'],branch=main_res['branch'],
        identity_scope='Uncommitted sources bound by hashes and snapshots, not revision alone',
        finite_checks=1725,main_checks=1717,causal_checks=8,field_cases=18,likelihood_queries=216,
        results_1024=[q for q in result['field_cases'] if q['records']==1024],
        centroid=result['centroid'],early_unobserved_curve_direction_variance=causal['unobserved_direction_variance'],
        principal_findings=[
            'Bounded-size prior-free field implements likelihood and outgoing-state envelopes with no budget reset on merge',
            'Fixed-center zero-order nonlinear field has large measured errors on tested nonzero-width domains; not promoted as a usable compressor',
            'Center translation is exact only with transformed likelihood/prior/support/transitions; uncertain center and residual require cross dependence',
            'Four-knot natural-cubic scalar regression has exact sufficient statistics under unique independent Gaussian observations',
            'Smooth monotone30percent trajectories can agree at all four knots and differ by1percent of reference between them',
            'Early first-piece data leave a future-curve direction unresolved; uncertainty must remain'],
        storage_B=dict(stationary_cell_logical_payload=816,curve_values_eight_health_four_knots=256,
                       shared_knot_times=32,dense_joint_curve_residual_example=6912,complete_subsystem=None),
        next='Exactly recenterable square-root center/residual representation with curve remainder and joint uncertainty; richer physical response field retaining the same error ledger. Four knots remain a candidate, not an aging-law assumption.',
        resources=dict(cpu_seconds=result['cpu_seconds'],wall_seconds=result['wall_seconds'],maximum_RSS_B=result['maximum_RSS_B'],scope='Main algebraic suite including plots, excluding compilation; not estimator throughput'),
        actual_battery_centroid_fitted=False,aging_law_selected=False,production_solver_changed=False,
        battery_fits=0,particle_steps=0,physical_error_allocation=None,
        arithmetic_error_bound=None,rigorous_numerical_enclosure=False,coverage_validated=False,
        ten_year_certificate=False,deployment_qualified=False)
    write(HERE/'summary.json',summary)
    files=sorted(p for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p!=HERE/'verification.json')
    write(HERE/'verification.json',dict(status='passed',finite_checks=1725,
        preserved_earlier_artifacts=len(main_res['preserved_artifacts']),
        artifacts={str(p.relative_to(ROOT)):ident(p) for p in files},
        scope='Source integrity and finite algebraic controls; prototype field is not promoted and no lifetime bound is certified'))
    print(json.dumps(dict(status='passed',checks=1725,artifacts=len(files))))


if __name__=='__main__':main()
