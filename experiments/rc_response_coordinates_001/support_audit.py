"""Post-comparison score diagnostic of projection versus normalized fitting.

No parameters or original artifacts are changed. Derivatives refer to the
declared scalar truncated conditional density, not a battery physical claim.
"""
import json
from pathlib import Path
import math
import numpy as np
from experiments.rc_response_coordinates_001 import coordinates as c
from experiments.rc_response_coordinates_001.compare import HERE, ROOT
from experiments.region_compression_001 import compare as base


def score(mu, sd, lower, upper, target):
    a, b = (lower-mu)/sd, (upper-mu)/sd
    logz = c.v.log_mass(a, b)
    pa = np.exp(-.5*a*a-.5*c.old.LOG2PI-logz)
    pb = np.exp(-.5*b*b-.5*c.old.LOG2PI-logz)
    residual = (mu-target)/sd
    intercept = np.mean(residual+pa-pb)
    logsd = np.mean(1-residual**2+a*pa-b*pb)
    return dict(intercept_shift_one_SD_gradient=float(intercept), logsd_gradient=float(logsd),
                mean_support_mean_shift_in_SD=float(np.mean(pa-pb)))


def loss(mu, sd, lower, upper, target):
    z = c.v.log_mass((lower-mu)/sd, (upper-mu)/sd)
    return float(np.mean(.5*((target-mu)/sd)**2+math.log(sd)+.5*c.old.LOG2PI+z))


def main():
    out = HERE/'support_audit001'
    out.mkdir(exist_ok=False)
    primary = HERE/'attempt001'
    result = json.loads((primary/'result.json').read_text())
    reservation = json.loads((primary/'reservation.json').read_text())
    for path, expected in reservation['identities'].items():
        c.old.require(base.identity(ROOT/path) == expected, 'source changed: '+path)
    base.write(out/'reservation.json', dict(status='post_comparison_before_score_evaluation',
        primary=base.identity(primary/'result.json'), source=base.identity(Path(__file__)),
        question='The support correction is non-negligible. Is untruncated regression stationary for the normalized conditional likelihood?',
        design='Use construction samples only. Compute intercept/logSD gradients for all saved regions/steps. Verify derivatives by central differences on first128members in each two-region mixture chart. No refit or heldout tuning.',
        derivative='NLL gradient for intercept shift by sigma: mean((mu-x)/sigma+phi(a)/Z-phi(b)/Z); for log_sigma: mean(1-((mu-x)/sigma)^2+a*phi(a)/Z-b*phi(b)/Z).',
        work='Separate post-comparison diagnostic, outside original candidate counters. No new inference or predictive trajectories.'))
    rows, checks = [], []
    for prefix, reference in result['references'].items():
        pops = []
        for path in reference['inherited']['train']:
            with np.load(ROOT/path, allow_pickle=False) as data:
                pops.append(data['projected'][:, :16].copy())
        x = np.concatenate(pops)
        for case in result['cases']:
            if case['prefix'] != int(prefix) or case['status'] != 'offline_comparison_completed':
                continue
            arm, k, frame = case['arm'], case['K'], case['frame']
            tag = f'prefix{prefix}_K{k}_{arm}_{frame}'
            payload = json.loads((primary/(tag+'.json')).read_text())
            msg = c.Message.restore(payload['posterior'])
            labels = np.searchsorted(msg.edges[1:-1], c.old.to_unit(x)[:, 5], side='right')
            entry = dict(prefix=int(prefix), K=k, arm=arm, frame=frame, regions=[])
            for j, reg in enumerate(msg.regions):
                xx = x[labels == j]
                y, a, _ = c.encode(xx, msg.frame, None if 'mixture' in arm else msg.edges[j:j+2])
                scores = []
                for step in range(7):
                    coef = c.coefficients(reg, step)
                    mu = coef[0]+y[:, :9+step] @ coef[1:]
                    sd = math.exp(float(reg['chain_logsd'][step]))
                    lo, hi = c.chain_bounds(xx, a, step)
                    target = y[:, 9+step]
                    scores.append(score(mu, sd, lo, hi, target))
                    if k == 2 and 'mixture' in arm:
                        mm, ll, hh, tt = mu[:128], lo[:128], hi[:128], target[:128]
                        analytical = score(mm, sd, ll, hh, tt)
                        eps = 1e-5
                        finite = [(loss(mm+eps*sd, sd, ll, hh, tt)-loss(mm-eps*sd, sd, ll, hh, tt))/(2*eps),
                                  (loss(mm, sd*math.exp(eps), ll, hh, tt)-loss(mm, sd*math.exp(-eps), ll, hh, tt))/(2*eps)]
                        for name, measured in zip(['intercept_shift_one_SD_gradient', 'logsd_gradient'], finite):
                            exact = analytical[name]
                            error = abs(measured-exact)
                            checks.append(dict(case=tag, region=j, step=step, derivative=name,
                                               absolute_error=error, passed=bool(error <= 2e-6*(1+abs(exact)))))
                entry['regions'].append(dict(count=len(xx), steps=scores))
            rows.append(entry)
    base.write(out/'result.json', dict(status='derivative_checks_passed' if all(t['passed'] for t in checks) else 'derivative_checks_failed',
        cases=rows, checks=checks, fit_modified=False,
        interpretation='Nonzero score at the projected parameters diagnoses construction/density mismatch. It does not prove that an optimized truncated fit will repair all predictive relationships or coverage.'))
    if not all(t['passed'] for t in checks):
        raise RuntimeError('derivative audit failed')
    print(len(checks), 'derivative checks passed')


if __name__ == '__main__':
    main()
