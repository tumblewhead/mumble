"""Post-comparison diagnostic, separately recorded; does not retune any arm.

Test whether a local linear voltage diagnostic can distinguish representations
which already preserve the transformed first two moments. Also expose exact
variance cancellation between OCV, RC and hysteresis contributions.
"""
import json
from pathlib import Path
import time
import numpy as np
from experiments.region_compression_001 import regions as r
from experiments.region_compression_001.compare import identity, plain, write, ROOT, HERE


def decomposition(x, anchor):
    u = r.to_unit(x)
    z, h, amp = x[:, 11], x[:, 15], x[:, 10]
    terms = np.column_stack((3+1.15*z+.08*np.tanh(8*(z-.5)), -x[:, 12:15].sum(1), -amp*h))
    cov = np.cov(terms, rowvar=False, bias=True)
    ua = r.from_logits(anchor)
    xa = r.LOW + r.WIDTH*ua
    grad = np.zeros(16)
    grad[11] = 1.15+.64*(1-np.tanh(8*(xa[11]-.5))**2)
    grad[12:15] = -1.
    grad[10], grad[15] = -xa[15], -xa[10]
    grad *= r.WIDTH*ua*(1-ua)
    va = 3+1.15*xa[11]+.08*np.tanh(8*(xa[11]-.5))-xa[12:15].sum()-xa[10]*xa[15]
    linear = va + (r.logit(u)-anchor) @ grad
    exact = terms.sum(1)
    residual = exact-linear
    pair = np.cov(np.column_stack((linear, residual)), rowvar=False, bias=True)
    # Algebraic decomposition, not a fitted correction.
    np.testing.assert_allclose(cov.sum(), np.var(exact), rtol=1e-10, atol=1e-18)
    np.testing.assert_allclose(pair.sum(), np.var(exact), rtol=1e-10, atol=1e-18)
    return dict(exact_voltage_SD_mV=1000*np.std(exact), linear_voltage_SD_mV=1000*np.std(linear),
                nonlinear_remainder_SD_mV=1000*np.std(residual),
                linear_remainder_correlation=np.corrcoef(linear, residual)[0, 1],
                terms=['OCV', '-sum_RC', '-H_times_h'], covariance_terms_V2=cov,
                linear_remainder_covariance_V2=pair,
                R0_mean=np.mean(x[:, 6]), R0_variance=np.var(x[:, 6]))


def main():
    out = HERE/'audit001'
    out.mkdir(exist_ok=False)
    primary = HERE/'attempt001'
    result = json.loads((primary/'result.json').read_text())
    reservation = json.loads((primary/'reservation.json').read_text())
    for path, expected in reservation['identities'].items():
        if identity(ROOT/path) != expected:
            raise RuntimeError('primary source changed: '+path)
    write(out/'reservation.json', dict(status='post_comparison_diagnostic_before_evaluation',
        reason='All arms broaden predictive voltage similarly despite close SOC/Q marginals.',
        diagnostic='Exact variance decomposition and linearized voltage in logit coordinates centered at construction sample mean only. No refit, tuning, extra measurements or truth.',
        primary_identity=identity(primary/'result.json'), audit_source=identity(Path(__file__)),
        preservation='All primary input/source hashes verified before audit. Original artifacts unchanged.',
        support_diagnostic='Use same frozen candidate draws/seeds and original saved independent populations.',
        full_covariance_identity='All arms preserve global mean/covariance of the other15 logits in exact arithmetic. Gaussian mixture preserves all16; atlas also preserves t/other15 moments within each chart.' ))
    begin = time.process_time()
    summaries = {}
    for prefix, reference in result['references'].items():
        def load(path):
            with np.load(ROOT/path, allow_pickle=False) as data:
                return data['projected'][:, :16].copy()
        train = np.concatenate([load(p) for p in reference['train']])
        anchor = r.logit(r.to_unit(train)).mean(0)
        held = [load(p) for p in reference['heldout']]
        item = dict(training=decomposition(train, anchor),
                    heldout_populations=[decomposition(p, anchor) for p in held], candidates=[])
        y = r.logit(r.to_unit(train))[:, r.OTHER]
        mean, cov = y.mean(0), np.cov(y, rowvar=False, bias=True)
        for i, case in enumerate(result['cases']):
            if case['prefix'] != int(prefix) or case['status'] != 'offline_comparison_completed':
                continue
            arm, k = case['arm'], case['K']
            payload = json.loads((primary/f'prefix{prefix}_K{k}_{arm}.json').read_text())
            msg = r.Message.restore(payload['posterior'])
            # Exact mixture law for the retained other15 transformed moments.
            mus, covs, weights = [], [], []
            for region in msg.regions:
                weights.append(np.exp(region['logweight']))
                if 'mean' in region:
                    l = r.unpack_factor(region['factor'], 16)
                    mus.append(region['mean'][r.OTHER])
                    covs.append((l @ l.T)[np.ix_(r.OTHER, r.OTHER)])
                else:
                    _, tm, th = r.quad_stats(region['theta'], 256)
                    l = r.unpack_factor(region['factor'], 15)
                    mus.append(region['intercept']+tm[0]*region['slope'])
                    covs.append(l@l.T + th[0, 0]*np.outer(region['slope'], region['slope']))
            weights, mus, covs = np.array(weights), np.array(mus), np.array(covs)
            mm = weights @ mus
            delta = mus-mm
            cc = np.einsum('n,nij->ij', weights, covs)+np.einsum('n,ni,nj->ij', weights, delta, delta)
            sd = np.sqrt(np.diag(cov))
            moment_residual = dict(max_scaled_mean=float(np.max(abs(mm-mean)/sd)),
                                   max_scaled_covariance=float(np.max(abs(cc-cov)/np.outer(sd, sd))))
            np.testing.assert_allclose(mm, mean, rtol=0, atol=1e-8)
            np.testing.assert_allclose(cc, cov, rtol=0, atol=1e-8)
            draws, _ = msg.draw(16384, 928001+i+1)
            item['candidates'].append(dict(arm=arm, K=k, analytic_moment_preservation=moment_residual,
                                           voltage=decomposition(draws, anchor)))
        summaries[prefix] = item
    write(out/'result.json', plain(dict(status='decomposition_and_retained_moment_identities_passed',
        prefixes=summaries, CPU_s=time.process_time()-begin,
        interpretation='These representations keep first two moments in the chosen coordinates but lose nonlinear dependence constraining voltage. Capacity-only partition placement does not resolve it. This is a coordinate/family limitation of the tested variants, not exclusion of mixture, atlas or network families.',
        automatic_repair_applied=False)))


if __name__ == '__main__':
    main()
