"""Bounded exponential/quadratic conditionals and constrained convex fitting.

This is an offline reference. Quadrature disagreement is an explicit failure,
not a license to change the support, add a penalty, or discard uncertainty.
"""
from functools import lru_cache
import numpy as np
from experiments.partition_coordinate_fit_001 import coordinates as c


@lru_cache(None)
def rule(order):
    z, w = np.polynomial.legendre.leggauss(order)
    return z, w, np.array([z**j for j in range(1, 5)])


def exponential_log_partition(eta):
    m = np.abs(np.asarray(eta, dtype=float))
    out = np.full(m.shape, np.log(2.))
    take = m > 0
    out[take] = m[take]+np.log(-np.expm1(-2*m[take])/m[take])
    return out


def quadrature(eta, precision, order):
    eta = np.atleast_1d(eta)
    z, w, powers = rule(order)
    result = np.empty((len(eta), 5))
    for start in range(0, len(eta), 256):
        exponent = eta[start:start+256, None]*z-.5*precision*z*z
        shift = exponent.max(1)
        mass = np.exp(exponent-shift[:, None])*w
        total = mass.sum(1)
        result[start:start+256, 0] = shift+np.log(total)
        result[start:start+256, 1:] = (mass @ powers.T)/total[:, None]
    return result


def statistics(eta, precision, charge=None):
    eta = np.atleast_1d(eta)
    c.old.require(np.isfinite(eta).all() and np.isfinite(precision) and precision >= 0,
                  'invalid natural parameter')
    if charge is not None:
        charge('fit_objective_rows', len(eta))
        charge('fit_quadrature_nodes', len(eta)*192)
    low = quadrature(eta, precision, 64)
    high = quadrature(eta, precision, 128)
    discrepancy = float(np.max(np.abs(low-high)))
    c.old.require(discrepancy <= 2e-11, 'natural quadrature refinement unresolved')
    if precision == 0:
        exact = exponential_log_partition(eta)
        c.old.require(np.max(np.abs(exact-high[:, 0])) <= 2e-11,
                      'exponential quadrature disagrees with analytic partition')
        high[:, 0] = exact
    return high, discrepancy


def log_partition(eta, precision):
    if precision == 0:
        c.old.require(np.isfinite(eta).all(), 'invalid exponential parameter')
        return exponential_log_partition(eta)
    return statistics(eta, precision)[0][:, 0]


def objective(theta, design, target, charge=None):
    stats, discrepancy = statistics(design @ theta[:-1], theta[-1], charge)
    A, m1, m2, m3, m4 = stats.T
    n = len(target)
    value = np.mean(A-(design @ theta[:-1])*target+.5*theta[-1]*target**2)
    gradient = np.r_[design.T @ (m1-target)/n, .5*np.mean(target**2-m2)]
    hessian = np.empty((len(theta), len(theta)))
    hessian[:-1, :-1] = (design.T*(m2-m1*m1)) @ design/n
    hessian[:-1, -1] = -.5*(design.T @ (m3-m1*m2))/n
    hessian[-1, :-1] = hessian[:-1, -1]
    hessian[-1, -1] = .25*np.mean(m4-m2*m2)
    c.old.require(np.isfinite(value) and np.isfinite(gradient).all()
                  and np.isfinite(hessian).all(), 'nonfinite natural objective')
    return float(value), gradient, hessian, discrepancy


def residual(theta, gradient):
    projected = gradient.copy()
    if theta[-1] == 0:
        projected[-1] = min(gradient[-1], 0.)
    return float(np.max(np.abs(projected)))


def fit(features, target, coefficients, precision, config, charge=None):
    design = np.column_stack([np.ones(len(target)), features])
    q, r = np.linalg.qr(design, mode='reduced')
    transform = r/np.sqrt(len(target))
    white = q*np.sqrt(len(target))
    theta = np.r_[transform @ coefficients, precision]
    evaluations, worst_quad = 0, 0.

    def evaluate(t):
        nonlocal evaluations, worst_quad
        c.old.require(evaluations < config['evaluations'], 'natural evaluation cap')
        evaluations += 1
        ans = objective(t, white, target, charge)
        worst_quad = max(worst_quad, ans[3])
        return ans[:3]

    value, gradient, hessian = evaluate(theta)
    initial_value = value
    status = 'iteration_cap'
    iterations = 0
    for iteration in range(config['iterations']):
        if residual(theta, gradient) <= config['gradient_tolerance']:
            status = 'constrained_gradient_tolerance_met'
            break
        step = np.linalg.solve(hessian, -gradient)
        active = theta[-1]+step[-1] < 0
        if active:
            step[-1] = -theta[-1]
            step[:-1] = np.linalg.solve(hessian[:-1, :-1],
                -gradient[:-1]-hessian[:-1, -1]*step[-1])
        slope = float(gradient @ step)
        if not slope < 0:
            status = 'no_descent_direction'
            break
        accepted = False
        for backtrack in range(config['backtracks']):
            if evaluations >= config['evaluations']:
                status = 'evaluation_cap'
                break
            fraction = 2.**(-backtrack)
            trial = theta+fraction*step
            if active and backtrack == 0:
                trial[-1] = 0.  # Exact feasible-bound quadratic subproblem.
            candidate = evaluate(trial)
            if candidate[0] <= value+config['armijo']*fraction*slope:
                theta, (value, gradient, hessian) = trial, candidate
                accepted = True
                iterations = iteration+1
                break
        if not accepted:
            if status != 'evaluation_cap':
                status = 'line_search_unresolved'
            break
    if residual(theta, gradient) <= config['gradient_tolerance']:
        status = 'constrained_gradient_tolerance_met'
    beta = np.linalg.solve(transform, theta[:-1])
    return beta, float(theta[-1]), dict(status=status, iterations=iterations,
        evaluations=evaluations, initial_mean_NLD=initial_value, final_mean_NLD=value,
        constrained_gradient_infinity=residual(theta, gradient),
        eta_gradient_infinity=float(np.max(np.abs(gradient[:-1]))),
        precision_gradient=float(gradient[-1]), precision=float(theta[-1]),
        boundary=bool(theta[-1] == 0), complementarity=float(abs(theta[-1]*gradient[-1])),
        quadrature_max_discrepancy=worst_quad, feature_transform_condition=float(np.linalg.cond(transform)))


def exponential_draw(eta, rng):
    eta = np.asarray(eta, dtype=float)
    m = np.abs(eta)
    u = rng.random(len(eta))
    # RNG's exact zero is an endpoint, not a physical draw to be clipped.
    while np.any(u == 0):
        u[u == 0] = rng.random(np.count_nonzero(u == 0))
    result = 2*u-1
    take = m > 0
    distance = -np.log1p(-u[take]*(-np.expm1(-2*m[take])))/m[take]
    result[take] = np.sign(eta[take])*(1-distance)
    c.old.require(np.all(np.abs(result) < 1), 'natural inverse draw rounded to support endpoint')
    return result


def draw(eta, precision, rng):
    eta = np.asarray(eta, dtype=float)
    c.old.require(np.isfinite(eta).all() and np.isfinite(precision) and precision >= 0,
                  'invalid natural sampling parameter')
    if precision == 0:
        return exponential_draw(eta, rng), len(eta)
    if precision >= 1:
        mu, sd = eta/precision, 1/np.sqrt(precision)
        z, count = c.v.truncated_standard_draw((-1-mu)/sd, (1-mu)/sd, rng)
        result = mu+sd*z
        c.old.require(np.all(np.abs(result) < 1), 'natural Gaussian draw outside support')
        return result, count
    # Tangent envelope of a concave quadratic; this mode is an envelope
    # calculation, not a clipped state or a modified target distribution.
    mode = np.clip(eta/precision, -1., 1.)
    slope = eta-precision*mode
    pending, count = np.arange(len(eta)), 0
    result = np.empty(len(eta))
    for _ in range(128):
        if not len(pending):
            return result, count
        proposed = exponential_draw(slope[pending], rng)
        count += len(pending)
        accepted = rng.random(len(pending)) < np.exp(-.5*precision*(proposed-mode[pending])**2)
        result[pending[accepted]] = proposed[accepted]
        pending = pending[~accepted]
    raise c.old.Unavailable('natural sampler round cap')
