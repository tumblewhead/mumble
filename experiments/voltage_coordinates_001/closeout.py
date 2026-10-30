"""Receipt verification and compact summary; no inference rerun."""
import json
from pathlib import Path
import numpy as np
from experiments.voltage_coordinates_001.compare import HERE, ROOT
from experiments.voltage_coordinates_001 import coordinates as c
from experiments.region_compression_001 import compare as base


def main():
    primary = HERE/'attempt001'
    result = json.loads((primary/'result.json').read_text())
    reservation = json.loads((primary/'reservation.json').read_text())
    baseline = json.loads((ROOT/reservation['plan']['baseline']).read_text())
    controls = json.loads((primary/'controls.json').read_text())
    checks = []

    def check(ok, name):
        checks.append(dict(name=name, passed=bool(ok)))

    for path, expected in reservation['identities'].items():
        check(base.identity(ROOT/path) == expected, 'identity:'+path)
    check(controls['passed'] and controls['tests_run'] == 20, 'twenty_numerical_controls')
    check(len(result['cases']) == 12, 'twelve_cases')
    for key, used in result['work'].items():
        check(used <= reservation['plan']['work_caps'][key], 'declared_comparison_work:'+key)
    rows = []
    for case, before in zip(result['cases'], baseline['cases']):
        tag = f"prefix{case['prefix']}_K{case['K']}_{case['arm']}"
        check(case['status'] == 'offline_comparison_completed', 'completed:'+tag)
        if case['status'] != 'offline_comparison_completed':
            continue
        payload = json.loads((primary/(tag+'.json')).read_text())
        msg = c.Message.restore(payload['posterior'])
        ref = result['references'][str(case['prefix'])]
        check(all(case[k] == before[k] for k in ['prefix', 'K', 'arm']), 'matched_case:'+tag)
        check(all(payload[k] == ref[k] for k in ['source_id', 'observation_interval', 'transition_interval', 'owns_initial_prior']), 'ownership:'+tag)
        check(msg.numeric_bytes == case['retained_numeric_B'] == before['retained_numeric_B'], 'matched_payload:'+tag)
        check(abs(sum(np.exp(reg['logweight']) for reg in msg.regions)-1) < 1e-14, 'normalized_region_masses:'+tag)
        check(np.array_equal(msg.edges, before['edges_normalized_logQ']), 'matched_placement:'+tag)
        refv = ref['heldout_outputs']
        def sd(outputs, name):
            return outputs[name]['voltage_V']['SD']*1000
        outputs = case['physical_outputs']
        rv, nv, ov = sd(refv, 'load_1s'), sd(outputs, 'load_1s'), sd(before['physical_outputs'], 'load_1s')
        rows.append(dict(prefix=case['prefix'], K=case['K'], arm=case['arm'], retained_numeric_B=msg.numeric_bytes,
            boundary_voltage_SD_mV=sd(outputs, 'boundary_rest_voltage'), reference_boundary_SD_mV=sd(refv, 'boundary_rest_voltage'),
            old_load_voltage_SD_mV=ov, new_load_voltage_SD_mV=nv, reference_load_voltage_SD_mV=rv,
            excess_load_variance_reduction_fraction=1-(nv*nv-rv*rv)/(ov*ov-rv*rv),
            heldout_density_improvement_by_population=case['heldout_score_improvement_by_population']))
    audit_reservation = json.loads((HERE/'audit001/reservation.json').read_text())
    audit = json.loads((HERE/'audit001/result.json').read_text())
    check(audit_reservation['primary'] == base.identity(primary/'result.json'), 'primary_preserved_after_audit')
    check(audit_reservation['audit_source'] == base.identity(HERE/'audit.py'), 'audit_source_identity')
    check(audit['status'] == 'exact_physical_decomposition_checks_passed', 'physical_decomposition')
    base.write(HERE/'summary.json', dict(schema='voltage_coordinate_summary_v1',
        status='boundary_voltage_repaired_future_RC_response_compression_unresolved',
        plan='experiments/voltage_coordinates_001/plan.json', report='experiments/voltage_coordinates_001/README.md',
        primary='experiments/voltage_coordinates_001/attempt001/result.json', audit='experiments/voltage_coordinates_001/audit001/result.json',
        cases=rows, numerical_controls=controls, receipt_checks=len(checks), CPU_s=result['CPU_s'],
        work=result['work'], additional_serialization_control_density_points=384,
        process_peak_RSS_B=result['process_peak_RSS_B'], complete_target_SRAM_B=None,
        outcome='Boundary voltage distribution and all heldout density scores improve at unchanged numeric payload. Future load/rest spread remains excessive; decomposition localizes most remaining variance excess to free/forced RC responses.',
        next='Retain physical voltage; derive uncertain RC response coordinates with exact inverse and dependent support, then compare multiple predictive timescales before causal integration.',
        rolling_solver_changed=False, fresh_posterior_inference=False, physical_aging_added=False,
        coverage_validated=False, deployment_qualified=False, four_hour_gate_passed=False))
    paths = [p for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in str(p)]
    base.write(HERE/'verification.json', dict(status='passed' if all(t['passed'] for t in checks) else 'failed',
        checks=checks, scope='Identities, numerical controls, matched regions/payload, ownership and declared scored work. Separate controls add work. No coverage or firmware qualification.',
        artifacts={str(p.relative_to(ROOT)): base.identity(p) for p in sorted(paths)}))
    if not all(t['passed'] for t in checks):
        raise RuntimeError('receipt checks failed')
    print(len(checks), 'receipt checks passed')


if __name__ == '__main__':
    main()
