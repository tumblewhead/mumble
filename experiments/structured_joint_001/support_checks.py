"""Supplemental joint-support and normalized-transition adversaries.

The uniform monotone transition is a mathematical counterexample, not a
calibrated battery aging law. No fits, trajectories or SCM execution.
"""
import json
import math
from pathlib import Path
import shutil
import sys
import numpy as np
from . import joint
from .qualify import HERE, ROOT, Checks, ident, write


def main():
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE/'support001'
    output.mkdir(parents=True, exist_ok=False)
    before = json.loads((HERE/'attempt001/reservation.json').read_text())
    preserved = dict(before['preserved_artifacts'])
    for p in (HERE/'attempt001').rglob('*'):
        if p.is_file(): preserved[str(p.relative_to(ROOT))] = ident(p)
    for p, expected in preserved.items():
        if ident(ROOT/p) != expected: raise ValueError('earlier artifact changed: '+p)
    sources = [Path(__file__), HERE/'joint.py', HERE/'qualify.py']
    for p in sources:
        target = output/'source_snapshot'/p.relative_to(ROOT); target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
    write(output/'reservation.json', dict(purpose='Additional correlated support and normalization controls',
          sources={str(p.relative_to(ROOT)): ident(p) for p in sources}, preserved_artifacts=preserved,
          command=sys.argv, model_scope='Uncalibrated mathematical counterexample, not a proposed physical aging rate'))
    c = Checks(); nodes, weights = np.polynomial.legendre.leggauss(192)
    evidence = {}
    # The lower/upper age direction reverses without changing the integral.
    rows = np.array([[4., -1.6, -.6], [0., 1.2, -.1], [0., 0., .2]])
    up = joint.split(rows, 1); down = joint.split(rows@np.diag([-1., -1., 1.]), 1)
    for s in [.02, .1, .5, .9]:
        c.close(f'increasing/decreasing support{s}', up.log_marginal_scalar_interval([s], 0., s),
                down.log_marginal_scalar_interval([-s], -s, 0.))
    # P(X>0,Y>0) for a standard correlated bivariate normal.
    records = []
    x = 5*(nodes+1)
    for rho in [-.8, 0., .8]:
        sd = math.sqrt(1-rho*rho)
        integrand = np.array([math.exp(-v*v/2)/math.sqrt(2*math.pi)*.5*math.erfc(-rho*v/sd/math.sqrt(2)) for v in x])
        direct = 5*float(weights@integrand)
        exact = .25+math.asin(rho)/(2*math.pi)
        c.close(f'joint orthant mass{rho}', direct, exact)
        c.check(f'orthant independence only at zero{rho}', (abs(exact-.25) < 1e-12) == (rho == 0))
        records.append(dict(correlation=rho, joint_mass=exact, product_of_marginals=.25))
    evidence['correlated_support'] = records
    # a0 uniform on[0,1); K(a1|a0)=1/(1-a0) for a0<=a1<=1.
    # This normalized monotone kernel illustrates a mandatory Z(a0).
    # After n steps p_n(a)=(-log(1-a))**n/n!, n>=0.
    records = []
    for n in [1, 2, 4]:
        for a in [.1, .5, .9]:
            old = .5*a*(nodes+1)
            density = (-np.log1p(-old))**(n-1)/math.factorial(n-1)
            direct = .5*a*float(weights@(density/(1-old)))
            exact = (-math.log1p(-a))**n/math.factorial(n)
            c.close(f'normalized transition n{n}/a{a}', direct, exact)
            records.append(dict(steps=n, health=a, marginal_density=exact))
        # Change variable z=-log(1-a). Gauss-Laguerre integrates z^n/n! e^-z.
        gn, gw = np.polynomial.laguerre.laggauss(32)
        mass = float(gw@(gn**n/math.factorial(n)))
        c.close(f'transition total mass n{n}', mass, 1.)
    c.check('renormalizing omitted transition normalizer cannot repair shape',
            abs(2*.1-(-math.log(.9))) > .05 and abs(2*.9-(-math.log(.1))) > .4)
    c.check('discarding carried shape changes later marginal',
            abs((-math.log(.1))**4/math.factorial(4)-(-math.log(.1))) > 1.)
    evidence['normalized_monotone_counterexample'] = records
    for p, expected in preserved.items():
        if ident(ROOT/p) != expected: c.check('preservation/'+p, False)
    result = dict(status='passed' if all(x['passed'] for x in c.items) else 'failed',
                  checks=c.items, passing_checks=sum(x['passed'] for x in c.items),
                  failed_checks=[x for x in c.items if not x['passed']], evidence=evidence,
                  interpretation='Finite exact-formula controls; no calibrated health law, multivariate constrained solver or lifetime certificate')
    write(output/'result.json', result)
    print(json.dumps({k: result[k] for k in ['status', 'passing_checks', 'failed_checks']}))
    if result['failed_checks']: raise SystemExit(1)


if __name__ == '__main__': main()
