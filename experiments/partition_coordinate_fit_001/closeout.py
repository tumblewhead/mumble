"""Verify both preserved attempts and summarize the registered factorial."""
from collections import Counter
import json
from pathlib import Path
import numpy as np
from experiments.partition_coordinate_fit_001.compare import HERE, ROOT
from experiments.partition_coordinate_fit_001 import coordinates as c
from experiments.region_compression_001 import compare as base


def main():
    primary = HERE/'attempt002'
    result = json.loads((primary/'result.json').read_text())
    reservation = json.loads((primary/'reservation.json').read_text())
    controls = json.loads((primary/'controls.json').read_text())
    original = HERE/'attempt001/result.json'
    checks = []

    def check(ok, name):
        checks.append(dict(name=name, passed=bool(ok)))

    for path, binding in reservation['identities'].items():
        check(base.identity(ROOT/path) == binding, 'source_identity:'+path)
    check(base.identity(original) == reservation['original_result_identity'], 'original_result_preserved')
    check(controls['passed'] and controls['tests_run'] == 39, 'thirty_nine_numerical_controls')
    check(len(result['cases']) == 8, 'eight_factorial_cases')
    for key, used in result['work'].items():
        check(used <= reservation['plan']['work_caps'][key], 'work_cap:'+key)
    tail = json.loads((primary/'tail_control.json').read_text())
    check(max(abs(t['repaired_error']) for t in tail) <= 5e-12, 'tail_arithmetic_repair')
    bounded_status = Counter()
    rows, limits = [], []
    for case in result['cases']:
        prefix, chart, method = case['prefix'], case['chart'], case['method']
        tag = f'prefix{prefix}_{chart}_{method}'
        check(case['status'] == 'offline_comparison_completed', 'completed:'+tag)
        if case['status'] != 'offline_comparison_completed':
            continue
        payload = json.loads((primary/(tag+'_message.json')).read_text())
        msg = c.Message.restore(payload['posterior'])
        ref = result['references'][str(prefix)]['inherited']
        check(all(payload[key] == ref[key] for key in ['source_id', 'observation_interval', 'transition_interval', 'owns_initial_prior']), 'ownership:'+tag)
        check(msg.numeric_bytes == case['retained_numeric_B'] == 2496, 'matched_numeric_payload:'+tag)
        check(abs(sum(np.exp(reg['logweight']) for reg in msg.regions)-1) < 1e-14, 'mixture_mass:'+tag)
        check(np.array_equal(msg.edges, [0., .5, 1.]), 'fixed_partition:'+tag)
        check(all(p['status'] == 'finite_all_draws_supported' for p in case['probes'].values()), 'finite_probe_support:'+tag)
        if method == 'bounded_likelihood':
            bounded_status.update(case['fit_status_counts'])
            for ri, region in enumerate(case['component_fits']):
                for j, diagnostic in enumerate(region['conditionals']):
                    check(diagnostic['final_mean_NLL'] <= diagnostic['initial_mean_NLL']+1e-12, f'nonincreasing_objective:{tag}:{ri}:{j}')
                    if diagnostic['status'] != 'first_order_stationary':
                        reg = msg.regions[ri]
                        precision = float(np.exp(-2*reg['logsd'][j]))
                        natural = precision*c.coefficients(reg, j)
                        limits.append(dict(prefix=prefix, component=ri, coordinate=j,
                            status=diagnostic['status'], gradient=diagnostic['final_gradient_infinity'],
                            precision=precision, natural_linear_coefficients=natural.tolist(),
                            zero_quadratic_log_density_difference_bound=precision/2 if j < 9 and chart=='specialized' else None,
                            interpretation='Near supported exponential shape; no proof of optimal limiting density'))
        reference = result['references'][str(prefix)]['probes']
        metrics = {}
        for name, probe in case['probes'].items():
            if probe['voltage_V'] is None:
                metrics[name] = dict(status=probe['status'])
                continue
            a, b = probe['voltage_V'], reference[name]['voltage_V']
            metrics[name] = dict(SD_mV=1000*a['SD'], reference_SD_mV=1000*b['SD'],
                                 mean_difference_mV=1000*(a['mean']-b['mean']))
        rows.append(dict(prefix=prefix, chart=chart, method=method, retained_numeric_B=2496,
            heldout_log_density_improvement=float(np.mean(case['heldout_improvement_from_saved_current_by_population'])),
            fit_status_counts=case['fit_status_counts'], probes=metrics))
    summary = dict(schema='partition_coordinate_fit_summary_v1',
        status='partition_coordinates_and_bounded_fit_improve_predictions_hysteresis_limit_unresolved',
        actions_completed=dict(transport_and_probability_charts='Derived and inverse/Jacobian/transport controlled',
            joint_coupling='Full16 conditional mixture with all preceding-coordinate dependencies and original source/prior ownership',
            factorial_comparison='Two charts times two fitting methods at8/32records; two fixed components; all eight repaired cases completed'),
        report='experiments/partition_coordinate_fit_001/README.md', plan='experiments/partition_coordinate_fit_001/plan.json',
        primary='experiments/partition_coordinate_fit_001/attempt002/result.json', original='experiments/partition_coordinate_fit_001/attempt001/result.json',
        numerical_adaptation='experiments/partition_coordinate_fit_001/numerical_adaptation.json',
        controls=controls, receipt_checks=len(checks), bounded_conditional_status_counts=dict(bounded_status),
        unresolved_hysteresis=limits, cases=rows,
        storage_estimate=dict(two_component_retained_numeric_B=2496, four_component_formula_only_B=4960,
            tested_components=2, four_components_tested=False, frame_values_included_B=24,
            approximate='2.5kB tested;5.0kB for four by formula. Numeric payload only.',
            construction_arrays_lower_B=2097152, largest_single_BFGS_matrix_B=2312,
            process_peak_RSS_B=result['process_peak_RSS_B'], complete_target_SRAM_B=None,
            exclusions=['source/model metadata','solver, queue and stack','query and fitting workspace']),
        work=result['work'], CPU_s=result['CPU_s'],
        main_finding='Specialized charts repair much of short-time spread; bounded fitting reduces prediction mean shifts and improves heldout density. Long reversals and rate-conditionals remain unresolved.',
        next='Fit bounded hysteresis conditionals in natural parameters, explicitly allowing the zero-precision supported exponential limit with constrained stationarity checks; same retained coefficient count. Keep frozen four-way evidence and all prediction horizons.',
        limits=['Short reused finite-moment reference, not new independent coverage validation',
                'Fixed-membership conditional stationarity is not globally optimal overlapping-mixture inference',
                'Eight hysteresis-rate conditionals retain iteration limits',
                'Deterministic transport views are not a complete streaming history compressor'],
        rolling_solver_changed=False, new_particle_inference=False, physical_aging_added=False,
        coverage_validated=False, deployment_qualified=False, four_hour_gate_passed=False)
    base.write(HERE/'summary.json', summary)
    paths = [p for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in str(p)]
    base.write(HERE/'verification.json', dict(status='passed' if all(t['passed'] for t in checks) else 'failed', checks=checks,
        scope='Finite controls, arithmetic witnesses, preservation, budgets, storage, ownership and sampled support. Optimizer limits retained; no density/coverage/deployment qualification.',
        artifacts={str(p.relative_to(ROOT)): base.identity(p) for p in sorted(paths)}))
    if not all(t['passed'] for t in checks):
        raise RuntimeError('receipt verification failed')
    print(len(checks), 'receipt checks passed;', dict(bounded_status))


if __name__ == '__main__':
    main()
