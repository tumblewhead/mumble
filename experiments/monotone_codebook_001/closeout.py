"""Bind monotone/codebook implementation and its finite qualification."""
import json
from .qualify import HERE,ROOT,ident,write


def main():
    a=json.loads((HERE/'attempt001/reservation.json').read_text())
    b=json.loads((HERE/'packing001/reservation.json').read_text())
    for folder,res in [('attempt001',a),('packing001',b)]:
        for path,expected in res['source_identities'].items():
            assert ident(ROOT/path)==expected,path
            assert ident(HERE/folder/'source_snapshot'/path)==expected,path
    for path,expected in a['preserved_artifacts'].items():assert ident(ROOT/path)==expected,path
    main=json.loads((HERE/'attempt001/result.json').read_text())
    packing=json.loads((HERE/'packing001/result.json').read_text())
    assert main['passing_checks']==1082 and not main['failed_checks']
    assert all(x['passed'] for x in main['checks']) and all(x['passed'] for x in packing['checks'])
    assert len(packing['checks'])==36
    assert packing['packing'][1]['contiguous_payload_B']==90
    summary=dict(schema='monotone_codebook_summary_v1',
        status='recenterable_square_root_monotone_curve_support_and_codecs_finitely_qualified',
        report='experiments/monotone_codebook_001/README.md',derivation='experiments/monotone_codebook_001/derivation.md',
        result='experiments/monotone_codebook_001/attempt001/result.json',packing='experiments/monotone_codebook_001/packing001/result.json',
        verification='experiments/monotone_codebook_001/verification.json',
        source_revision=a['revision'],branch=a['branch'],identity_scope='Uncommitted source hashes and snapshots, not revision alone',
        user_model_direction=dict(monotone_reference_condition_aging=True,R0_Ri='nondecreasing',Q_Ci='nonincreasing',tau='no monotonicity implied',
                                  temperature_representations=['measured T(t)','reversible parameter response g(T)'],physical_calibration=False),
        finite_checks=1118,main_checks=1082,packing_checks=36,
        principal_results=[
            'Upper-square-root re-centering updates the last column and preserves likelihood/gradient/normalization/cross terms in real arithmetic',
            'Quantized chart centers with compensated residual factors preserve the target; physical curve quantization has a separate bound',
            'Ordered coefficients and common-grid rounding preserve monotonicity for degree-one splines and cubic Bernstein segments',
            'Reference-anchored thermal functions separate reversible response from latent aging but do not remove age-temperature confounding',
            '60 coefficient values pack into90B at12bits; joint uncertainty remains the main unresolved storage obligation'],
        curve_quantization_controls=main['evidence']['curves'],battery_control=main['evidence']['battery'],
        storage_B=dict(eight_health_age_coefficients_12bit=48,temperature_history_coefficients_12bit=6,
                       eight_health_thermal_coefficients_contiguous_12bit=36,combined_contiguous_12bit=90,
                       combined_per_curve_padded_12bit=94,combined_float64_coefficients=480,
                       scalar_p8_packed_square_root=360,scalar_p8_center_12bit=12,scalar_p8_factor_plus_center=372,
                       dense_p64_augmented_factor=17160,complete_subsystem=None),
        next='Structured joint square-root layout from physical dependencies, preserving age/thermal/residual coupling and curve/nonlinear-response remainders before battery aging integration',
        resources=dict(cpu_seconds=main['cpu_seconds'],wall_seconds=main['wall_seconds'],maximum_RSS_B=main['maximum_RSS_B'],scope='Main finite controls including plots, excluding compilation; not estimator throughput'),
        monotone_trajectory_support_implemented=True,monotone_normalized_health_kernel_implemented=False,
        temperature_representations_implemented=True,temperature_calibrated=False,
        full_support_aware_posterior_qualified=False,production_solver_changed=False,
        old_zero_order_nonlinear_field_repaired=False,curve_model_remainder_bound=None,
        numerical_lifetime_bound=None,coverage_validated=False,ten_year_certificate=False,deployment_qualified=False)
    write(HERE/'summary.json',summary)
    files=sorted(p for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p!=HERE/'verification.json')
    write(HERE/'verification.json',dict(status='passed',finite_checks=1118,preserved_earlier_artifacts=len(a['preserved_artifacts']),
        artifacts={str(p.relative_to(ROOT)):ident(p) for p in files},
        scope='Source integrity, finite exact-algebra and codebook checks; not full aging posterior, model calibration, SRAM or lifetime qualification'))
    print(json.dumps(dict(status='passed',checks=1118,artifacts=len(files),preserved=len(a['preserved_artifacts']))))


if __name__=='__main__':main()
