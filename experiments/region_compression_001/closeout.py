"""Verify receipt bindings and summarize the frozen comparison without reruns."""
import json
from pathlib import Path
import numpy as np
from experiments.region_compression_001.compare import identity, write, ROOT, HERE
from experiments.region_compression_001.regions import Message


def main():
    primary = HERE/'attempt001'
    result = json.loads((primary/'result.json').read_text())
    audit = json.loads((HERE/'audit001/result.json').read_text())
    reservation = json.loads((primary/'reservation.json').read_text())
    checks = []

    def check(ok, label):
        checks.append(dict(label=label, passed=bool(ok)))

    for name, binding in reservation['identities'].items():
        check(identity(ROOT/name) == binding, 'source_identity:'+name)
    check(len(result['cases']) == 12, 'twelve_frozen_cases')
    controls = json.loads((primary/'controls.json').read_text())
    check(controls['passed'] and controls['tests_run'] == 10, 'ten_numerical_controls')
    plan = reservation['plan']
    for key, used in result['work'].items():
        check(used <= plan['work_caps'][key], 'work_cap:'+key)
    rows = []
    for case in result['cases']:
        key = f"prefix{case['prefix']}_K{case['K']}_{case['arm']}"
        check(case['status'] == 'offline_comparison_completed', 'completed:'+key)
        if case['status'] != 'offline_comparison_completed':
            continue
        payload = json.loads((primary/(key+'.json')).read_text())
        reference = result['references'][str(case['prefix'])]
        msg = Message.restore(payload['posterior'])
        check(abs(sum(np.exp(region['logweight']) for region in msg.regions)-1) < 1e-14, 'mass:'+key)
        check(msg.numeric_bytes == case['retained_numeric_B'], 'packed_bytes:'+key)
        check(all(payload[k] == reference[k] for k in ['source_id', 'observation_interval', 'transition_interval', 'owns_initial_prior']), 'source_ownership:'+key)
        v = case['physical_outputs']
        ref = reference['heldout_outputs']
        rows.append(dict(prefix=case['prefix'], K=case['K'], arm=case['arm'],
            retained_numeric_B=case['retained_numeric_B'], complete_subsystem_SRAM_B=None,
            mean_heldout_negative_log_density=case['heldout_mean_negative_log_density'],
            load_voltage_SD_mV=1000*v['load_1s']['voltage_V']['SD'],
            reference_load_voltage_SD_mV=1000*ref['load_1s']['voltage_V']['SD'],
            load_voltage_SD_ratio=v['load_1s']['voltage_V']['SD']/ref['load_1s']['voltage_V']['SD'],
            boundary_voltage_SD_mV=1000*v['boundary_rest_voltage']['voltage_V']['SD'],
            reference_boundary_voltage_SD_mV=1000*ref['boundary_rest_voltage']['voltage_V']['SD']))
    check(audit['status'] == 'decomposition_and_retained_moment_identities_passed', 'nonlinear_dependence_audit')
    audit_reservation = json.loads((HERE/'audit001/reservation.json').read_text())
    check(audit_reservation['primary_identity'] == identity(primary/'result.json'), 'primary_unchanged_after_audit')
    check(audit_reservation['audit_source'] == identity(HERE/'audit.py'), 'audit_source_identity')
    summary = dict(schema='region_compression_summary_v1',
        status='three_offline_variants_compared_nonlinear_dependence_not_preserved',
        primary_result='experiments/region_compression_001/attempt001/result.json',
        audit_result='experiments/region_compression_001/audit001/result.json',
        report='experiments/region_compression_001/README.md',
        controls=controls, cases=rows, work=result['work'], CPU_s=result['CPU_s'],
        process_peak_RSS_B=result['process_peak_RSS_B'],
        construction_sample_and_unit_arrays_B=2097152,
        conclusion='Small numeric payloads, but all tested constructions lose nonlinear dependence constraining voltage. No consistent winner or improvement from four capacity regions.',
        adaptation='Geometric probability atlas substitutes for likelihood atlas; self-organizing placement restricted to log-capacity chain.',
        next='Derive physical voltage/state coordinates with exact inverse, Jacobian and dependent support normalization; repeat matched offline comparison before causal integration.',
        reference_coverage_validated=False, new_particle_inference=False,
        rolling_solver_changed=False, physical_aging_added=False,
        likelihood_atlas_implemented=False, full16_self_organizing_network_implemented=False,
        deployment_qualified=False, four_hour_gate_passed=False)
    write(HERE/'summary.json', summary)
    bound_files = [p for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in str(p)]
    write(HERE/'verification.json', dict(status='passed' if all(c['passed'] for c in checks) else 'failed',
        checks=checks, scope='Source identities, numerical controls, work limits, posterior ownership, normalization weights, payload counts and post-comparison identities; not coverage or deployment qualification.',
        artifacts={str(p.relative_to(ROOT)): identity(p) for p in sorted(bound_files)}))
    if not all(c['passed'] for c in checks):
        raise RuntimeError('receipt verification failed')
    print(f'{len(checks)} receipt checks passed')


if __name__ == '__main__':
    main()
