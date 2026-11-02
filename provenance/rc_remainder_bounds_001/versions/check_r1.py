"""Offline P2 certificate and P3 diagnostics; not a runtime admission monitor."""
from fractions import Fraction as F
from math import comb, factorial
import numpy as np


P = {3: [-1, 7, -6, 1], 4: [1, -15, 25, -10, 1]}
Q = {3: [0, 1, -3, 1], 4: [0, -1, 7, -6, 1]}
BRACKETS = {
    3: [(1657568156, 1657568157), (13433795689, 13433795690),
        (44908636153, 44908636154)],
    4: [(760038343, 760038344), (7621690715, 7621690716),
        (26516929955, 26516929956), (65101340985, 65101340986)],
}
UPPER = {3: (F('0.42962'), F('1.78302')),
         4: (F('1.11875'), F('4.51031'))}


def value(p, x):
    out = 0
    for c in reversed(p):
        out = out*x+c
    return out


def multiply(a, b):
    products = [x*y for x in a for y in b]
    return min(products), max(products)


def interval_value(p, interval):
    out = (F(0), F(0))
    for c in reversed(p):
        lo, hi = multiply(out, interval)
        out = lo+c, hi+c
    return out


def exp_negative(x, terms=48):
    """Exact rational enclosure; no floating transcendental calculation."""
    if not isinstance(x, F) or x < 0 or x >= terms+2:
        raise ValueError('exponential certificate domain')
    total = F(1)
    term = F(1)
    for k in range(1, terms+1):
        term *= x/k
        total += term
    tail = term*x/(terms+1)/(1-x/(terms+2))
    return 1/(total+tail), 1/total


def abs_upper(interval):
    return max(abs(interval[0]), abs(interval[1]))


def certificate(n, brackets=None, upper=None):
    """Certify the root-based extrema/variation bounds using rational arithmetic."""
    brackets = BRACKETS[n] if brackets is None else brackets
    upper = UPPER[n] if upper is None else upper
    if len(brackets) != n:
        raise ValueError('must isolate all polynomial roots')
    z = [(F(0), F(0))]
    previous = F(0)
    for left, right in brackets:
        lo, hi = F(left, 10**10), F(right, 10**10)
        if not previous < lo < hi or value(P[n], lo)*value(P[n], hi) >= 0:
            raise ValueError('invalid disjoint sign-changing root bracket')
        previous = hi
        exp_interval = exp_negative(hi)[0], exp_negative(lo)[1]
        z.append(multiply(interval_value(Q[n], (lo, hi)), exp_interval))
    z.append((F(0), F(0)))
    a = max(map(abs_upper, z))
    b = sum(abs_upper((y[0]-x[1], y[1]-x[0])) for x, y in zip(z, z[1:]))
    if a > upper[0] or b > upper[1]:
        raise ValueError('proposed constants do not enclose certified fractions')
    return dict(order=n, roots=list(brackets), denominator=10**10,
                extrema_enclosures=[[float(v) for v in row] for row in z[1:-1]],
                enclosure_upper_float=dict(A=float(a), B=float(b)),
                proved_rational_upper=dict(A=str(upper[0]), B=str(upper[1])),
                exact_rational_comparisons_passed=True)


def polynomials(count=4):
    p, q = [[1]], [[1]]
    for _ in range(count):
        pn, qn = [0]*(len(p[-1])+1), [0]*(len(q[-1])+1)
        for k, c in enumerate(p[-1]):
            pn[k+1] += c
            pn[k] -= (k+1)*c
        for k, c in enumerate(q[-1]):
            qn[k+1] += c
            qn[k] -= k*c
        p.append(pn)
        q.append(qn)
    return p, q


def response(dt, current, tau):
    """Independent float derivative recurrence through order four, all prefixes."""
    q = polynomials()[1]
    state = np.zeros(5)
    rows = []
    for interval, amps in zip(dt, current):
        dose = interval/tau
        deriv = np.array([np.exp(-dose)*value(qn, dose) for qn in q])
        old = state.copy()
        for n in range(5):
            state[n] = sum(comb(n, k)*deriv[n-k]*old[k] for k in range(n+1))
            state[n] += amps*((1. if n == 0 else 0.)-deriv[n])
        rows.append(state.copy())
    total = np.cumsum(dt)/tau
    free = np.array([np.exp(-total)*value(qn, total) for qn in q]).T
    return free, np.array(rows)


def public_probe():
    """Same public inputs/amplitudes as prior RC-only mechanism probe, no fit."""
    k = np.arange(600)
    dt = np.array([0., 1/35, 1/50, .2, .8])[k % 5]
    current = np.array([0., .03, -.02, .012, -.025, 0.])[(k//25) % 6]
    b = np.array([.004, -.002, .003])
    resistance = np.array([.035, .07, .10000000000000002])
    center = np.array([.07, .7, 6.])
    a3, b3 = map(float, UPPER[3])
    m3 = a3*abs(b)+b3*resistance*max(abs(current))
    records = []
    for t in [0., -.35, .35, -1/np.sqrt(2), 1/np.sqrt(2), -.9, .9]:
        errors, slopes, derivative_ratios = [], [], []
        for bj, rj, tau, bound in zip(b, resistance, center, m3):
            fc, uc = response(dt, current, tau)
            f, u = response(dt, current, tau*np.exp(t))
            v, vc = bj*f+rj*u, bj*fc+rj*uc
            approx = vc[:, 0]+t*vc[:, 1]+t*t/2*vc[:, 2]
            slope = vc[:, 1]+t*vc[:, 2]
            errors.append(float(max(abs(v[:, 0]-approx))))
            slopes.append(float(max(abs(v[:, 1]-slope))))
            derivative_ratios.append(float(max(abs(v[:, 3]))/bound))
        ev, es = m3*abs(t)**3/6, m3*t*t/2
        # Floating diagnostics have a numerical allowance; not part of the certificate.
        if np.any(np.array(errors) > ev+1e-13) or np.any(np.array(slopes) > es+1e-13):
            raise AssertionError('public response bound violated')
        records.append(dict(log_tau_offset=t, branch_value_error_V=errors,
                            branch_slope_error_V=slopes,
                            branch_value_bound_V=ev.tolist(), branch_slope_bound_V=es.tolist(),
                            third_derivative_bound_ratios=derivative_ratios))
    return dict(records=600, duration_s=float(sum(dt)), Imax_A=.03,
                boundary_V=b.tolist(), resistance_ohm=resistance.tolist(),
                M3_V=m3.tolist(), queries=records)


def accumulation_example():
    epsilon = .001
    # Use log odds to avoid hiding the long-horizon result behind exp underflow.
    return dict(response_error_sigma=epsilon, cases=[
        dict(observations=n, log_odds_second_vs_first=-n*epsilon**2/2)
        for n in [1, 126000, 126000*24*365*10]],
        scope='Abstract Gaussian counterexample, not a Foster trajectory or deployment prediction')
