"""Verify source/receipt integrity and summarize storage and predictive limits."""
import json
from pathlib import Path
import numpy as np
from experiments.rc_response_coordinates_001.compare import HERE, ROOT
from experiments.rc_response_coordinates_001 import coordinates as c
from experiments.region_compression_001 import compare as base


def main():
    primary = HERE/'attempt001'
    result = json.loads((primary/'result.json').read_text())
    reservation = json.loads((primary/'reservation.json').read_text())
    baseline = json.loads((ROOT/reservation['plan']['baseline']).read_text())
    controls = json.loads((primary/'controls.json').read_text())
    audit = json.loads((HERE/'support_audit001/result.json').read_text())
    audit_res = json.loads((HERE/'support_audit001/reservation.json').read_text())
    checks = []

    def check(ok, name):
        checks.append(dict(name=name, passed=bool(ok)))

    for path, binding in reservation['identities'].items():
        check(base.identity(ROOT/path) == binding, 'source_identity:'+path)
    check(controls['passed'] and controls['tests_run'] == 29, 'twenty_nine_controls')
    check(len(result['cases']) == 36, 'thirty_six_cases')
    check(len(result['baseline_extended']) == 12, 'twelve_unfitted_baseline_extensions')
    for key, used in result['work'].items():
        check(used <= reservation['plan']['work_caps'][key], 'work_cap:'+key)
    for case in result['cases']:
        prefix, k, arm, frame = case['prefix'], case['K'], case['arm'], case['frame']
        tag = f'prefix{prefix}_K{k}_{arm}_{frame}'
        check(case['status'] == 'offline_comparison_completed', 'completed:'+tag)
        if case['status'] != 'offline_comparison_completed':
            continue
        payload = json.loads((primary/(tag+'.json')).read_text())
        msg = c.Message.restore(payload['posterior'])
        reference = result['references'][str(prefix)]['inherited']
        old = next(x for x in baseline['cases'] if x['prefix'] == prefix and x['K'] == k and x['arm'] == arm)
        check(all(payload[key] == reference[key] for key in ['source_id', 'observation_interval', 'transition_interval', 'owns_initial_prior']), 'ownership:'+tag)
        check(msg.numeric_bytes == case['retained_numeric_B'] == old['retained_numeric_B']+24, 'packed_payload:'+tag)
        check(np.array_equal(msg.edges, old['edges_normalized_logQ']), 'same_placement:'+tag)
        check(abs(sum(np.exp(reg['logweight']) for reg in msg.regions)-1) < 1e-14, 'mass:'+tag)
        check(all(p['status'] == 'finite_all_draws_supported' for p in case['probes'].values()), 'finite_probe_support:'+tag)
    check(audit_res['primary'] == base.identity(primary/'result.json'), 'primary_unchanged_after_audit')
    check(audit_res['source'] == base.identity(HERE/'support_audit.py'), 'audit_source_identity')
    check(audit['status'] == 'derivative_checks_passed' and len(audit['checks']) == 168 and all(t['passed'] for t in audit['checks']), 'one_hundred_sixty_eight_derivative_checks')
    groups = []
    for prefix in [8, 32]:
        for frame in reservation['plan']['frames']:
            cases = [t for t in result['cases'] if t['prefix'] == prefix and t['frame'] == frame and t['status'] == 'offline_comparison_completed']
            if not cases:
                continue
            metrics = {}
            for name, reference in result['references'][str(prefix)]['probes'].items():
                if reference['voltage_V'] is None:
                    continue
                ref = reference['voltage_V']
                candidates = [t['probes'][name]['voltage_V'] for t in cases if t['probes'][name]['voltage_V'] is not None]
                sd = [x['SD']*1000 for x in candidates]
                mean = [(x['mean']-ref['mean'])*1000 for x in candidates]
                metrics[name] = dict(reference_SD_mV=ref['SD']*1000, candidate_SD_range_mV=[min(sd), max(sd)],
                                     candidate_mean_difference_range_mV=[min(mean), max(mean)])
            improvement = [float(np.mean(t['heldout_improvement_from_voltage_by_population'])) for t in cases]
            groups.append(dict(prefix=prefix, frame=frame, cases=len(cases), probes=metrics,
                               mean_heldout_density_improvement_range_nats=[min(improvement), max(improvement)]))
    summary = dict(schema='rc_response_summary_v1',
        status='RC_response_coordinates_improve_prediction_bounded_conditional_fit_repair_required',
        report='experiments/rc_response_coordinates_001/README.md', primary='experiments/rc_response_coordinates_001/attempt001/result.json',
        audit='experiments/rc_response_coordinates_001/support_audit001/result.json',
        storage_estimate=dict(two_region_mixture_B=2496, two_region_atlas_B=2512,
            four_region_mixture_B=4960, four_region_atlas_B=4992, frame_values_included_B=24,
            approximate_summary='2.5kB with two regions;5.0kB with four. Numeric payload only.',
            remaining_of_10240B_after_two_region_payload=[7728,7744], remaining_after_four_region_payload=[5248,5280],
            constructor_two_arrays_lower_B=2097152, process_peak_RSS_B=result['process_peak_RSS_B'], complete_target_SRAM_B=None,
            exclusions=['ownership/configuration metadata','query scratch','solver/queue/stack','construction and causal update workspace']),
        cases_completed=sum(t['status'] == 'offline_comparison_completed' for t in result['cases']), controls=controls,
        derivative_checks=168, receipt_checks=len(checks), results=groups, work=result['work'], CPU_s=result['CPU_s'],
        baseline_extension_inverse_OCV_iterations=result['baseline_extension_inverse_OCV_iterations'],
        conclusion='Public mode-scale frame offers best heldout density across tested frames and better cross-horizon behavior than common1s. Short-time predictions, mean shifts and long reversals remain unresolved. More regions do not consistently help.',
        next='Fit the same bounded conditional family with the support normalizer in the objective, using construction samples only, and compare against frozen projections across all horizons. No additional retained coefficients needed; fitting workspace still unqualified.',
        source_scope='Saved8/32-record posterior populations,0.229/0.914s history. Predictive probes are not long-term learning or new observations.',
        rolling_solver_changed=False, new_particle_inference=False, physical_aging_added=False,
        coverage_validated=False, deployment_qualified=False, four_hour_gate_passed=False)
    base.write(HERE/'summary.json', summary)
    paths = [p for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in str(p)]
    base.write(HERE/'verification.json', dict(status='passed' if all(t['passed'] for t in checks) else 'failed', checks=checks,
        scope='Finite numerical controls, artifact integrity, budgets, weights, ownership, storage arithmetic and sampled support. Not density adequacy, physical exclusion, coverage or deployment.',
        artifacts={str(p.relative_to(ROOT)): base.identity(p) for p in sorted(paths)}))
    if not all(t['passed'] for t in checks):
        raise RuntimeError('receipt verification failed')
    print(len(checks), 'receipt checks passed')


if __name__ == '__main__':
    main()
