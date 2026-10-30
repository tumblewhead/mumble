"""Post-comparison physical variance decomposition; no refit or correction."""
import json
from pathlib import Path
import numpy as np
from experiments.voltage_coordinates_001 import coordinates as c
from experiments.voltage_coordinates_001.compare import HERE, ROOT
from experiments.region_compression_001 import compare as base


NAMES = ['boundary_voltage', 'OCV_charge_change', 'free_RC_release', 'forced_RC', 'ohmic_drop', 'hysteresis_change']


def terms(x, current, dt=1.):
    z = x[:, 11]
    ocv_change = c.ocv(z-current*dt/(3600*np.exp(x[:, 5])))-c.ocv(z)
    attenuation = -np.expm1(-dt/np.exp(x[:, :3]))
    free = (attenuation*x[:, 12:15]).sum(1)
    forced = -current*(attenuation*x[:, 7:10]).sum(1)
    hyst = np.zeros(len(x))
    if current:
        attenuation_h = -np.expm1(-np.exp(x[:, 3 if current > 0 else 4])*abs(current)*dt/3600)
        hyst = x[:, 10]*attenuation_h*(x[:, 15]-np.sign(current))
    result = np.column_stack((c.voltage(x), ocv_change, free, forced, -current*x[:, 6], hyst))
    expected, valid = c.old.stationary_probe(x, [[current, dt]])
    c.require(valid.all(), 'support loss in audit')
    np.testing.assert_allclose(result.sum(1), expected, rtol=0, atol=3e-15)
    return result


def stats(x, current):
    a = terms(x, current)
    cov = np.cov(a, rowvar=False, bias=True)
    np.testing.assert_allclose(cov.sum(), np.var(a.sum(1)), rtol=1e-10, atol=1e-18)
    return dict(mean_V=a.mean(0), covariance_mV2=cov*1e6, voltage_variance_mV2=float(cov.sum()*1e6))


def main():
    out = HERE/'audit001'
    out.mkdir(exist_ok=False)
    primary = HERE/'attempt001'
    source = json.loads((primary/'reservation.json').read_text())
    for path, expected in source['identities'].items():
        c.require(base.identity(ROOT/path) == expected, 'source changed '+path)
    base.write(out/'reservation.json', dict(status='post_comparison_before_decomposition',
        primary=base.identity(primary/'result.json'), audit_source=base.identity(Path(__file__)),
        question='Which declared physical terms contribute to remaining predictive variance discrepancy?',
        method='Exact additive decomposition of1s constant-current voltage for0A and0.05A. Compare full covariance matrices; half of each pair covariance allocated to each term via row sums. Signed attribution depends on this physical partition, not unique causal blame.',
        data='Same construction/heldout samples and frozen generated draws; no refit, new measurements, truth or parameter changes.',
        work_accounting='Primary heldout_density_points counts98304 scoring points. Serialization parity adds384 control queries;20 controls also have separate work. Whole-process RSS includes controls. No measured MCU resources.'))
    result = json.loads((primary/'result.json').read_text())
    rows = []
    for prefix, ref in result['references'].items():
        def load(name):
            with np.load(ROOT/name, allow_pickle=False) as data:
                return data['projected'][:, :16].copy()
        train = np.concatenate([load(p) for p in ref['train']])
        held = [load(p) for p in ref['heldout']]
        pooled = np.concatenate(held)
        reference = {name: stats(pooled, current) for name, current in [('rest', 0.), ('load', .05)]}
        item = dict(prefix=int(prefix), reference=reference,
            training={name: stats(train, current) for name, current in [('rest', 0.), ('load', .05)]},
            heldout_populations=[{name: stats(pop, current) for name, current in [('rest', 0.), ('load', .05)]} for pop in held],
            candidates=[])
        for i, case in enumerate(result['cases']):
            if case['prefix'] != int(prefix) or case['status'] != 'offline_comparison_completed':
                continue
            arm, k = case['arm'], case['K']
            payload = json.loads((primary/f'prefix{prefix}_K{k}_{arm}.json').read_text())
            msg = c.Message.restore(payload['posterior'])
            x, _ = msg.draw(16384, 928001+i+1)
            entry = dict(K=k, arm=arm)
            for name, current in [('rest', 0.), ('load', .05)]:
                candidate = stats(x, current)
                delta = candidate['covariance_mV2']-reference[name]['covariance_mV2']
                candidate['excess_variance_contribution_mV2'] = delta.sum(1)
                candidate['diagonal_variance_difference_mV2'] = np.diag(delta)
                candidate['cross_covariance_difference_mV2'] = delta-np.diag(np.diag(delta))
                entry[name] = candidate
            item['candidates'].append(entry)
        rows.append(item)
    base.write(out/'result.json', base.plain(dict(status='exact_physical_decomposition_checks_passed',
        term_order=NAMES, prefixes=rows, primary_unchanged=True,
        warning='Signed row-sum allocation is descriptive and can be negative; it neither identifies a unique cause nor permits fixing nuisance parameters.')))


if __name__ == '__main__':
    main()
