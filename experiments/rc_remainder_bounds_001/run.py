"""Produce compact, source-bound diagnostics without running new fitted campaigns."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np
from . import check


ROOT = Path(__file__).resolve().parents[2]


def identity(path):
    data = path.read_bytes()
    return dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError('refuse overwrite')
    certificates = [check.certificate(n) for n in [3, 4]]
    public = check.public_probe()
    previous_path = ROOT/'provenance/rc_sensitivity_basis_001/response_probe.json'
    previous = json.loads(previous_path.read_text())
    comparisons = []
    for now, old in zip(public['queries'], previous['queries']):
        assert now['log_tau_offset'] == old['common_log_tau_offset']
        candidate = old['arms']['Taylor2_H2']
        comparisons.append(max(
            max(abs(1000*np.array(now['branch_value_error_V'])-candidate['max_branch_voltage_defect_mV'])),
            max(abs(1000*np.array(now['branch_slope_error_V'])-candidate['max_branch_log_tau_derivative_defect_mV']))))
    if max(comparisons) > 1e-8:
        raise AssertionError('public analytical probe does not reproduce previous native probe')
    # A public illustration only; these budgets are not adopted product requirements.
    m3 = np.array(public['M3_V'])
    voltage_budget = 1e-5
    slope_budget = 1e-4
    radius_v = (6*voltage_budget/sum(m3))**(1/3)
    radius_s = min(np.sqrt(2*slope_budget/m3))
    files = [*Path(__file__).parent.glob('*.py'),
             * (ROOT/'specifications/rc_remainder_bounds_001').glob('*.md'), previous_path]
    result = dict(schema='rc_remainder_bounds_result_v1',
        status='exact_constants_certified_and_finite_diagnostics_pass',
        source_revision=subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT,text=True).strip(),
        bindings={str(p.relative_to(ROOT)):identity(p) for p in sorted(files)},
        certificates=certificates, public_probe=public,
        max_prior_native_probe_difference_mV=float(max(comparisons)),
        illustrative_admission=dict(voltage_budget_V=voltage_budget,
            per_branch_log_tau_slope_budget_V=slope_budget,
            radius_from_voltage=float(radius_v),radius_from_slope=float(radius_s),
            common_radius_within_original_box=float(min(1., radius_v, radius_s)),
            scope='Fixed public amplitudes only, ordinary float illustration, not a runtime certificate or posterior support change'),
        accumulation_counterexample=check.accumulation_example(),
        storage=dict(factor_B=4760,partial_subtotal_B=5168,new_runtime_storage_B=0,
            scope='No runtime changes; complete firmware memory remains unqualified'),
        limits=['Stationary exact-input mathematical response only; no aging or rounding proof',
                'Likelihood bound retains horizon dependence',
                'H2 uncertainty remains independent blocker; no production promotion'])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(dict(status=result['status'], out=str(args.out),
                         max_prior_native_probe_difference_mV=result['max_prior_native_probe_difference_mV'],
                         illustrative_admission=result['illustrative_admission']), indent=2))


if __name__ == '__main__':
    main()
