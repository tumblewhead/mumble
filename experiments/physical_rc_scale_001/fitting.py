"""Physical-v regression with a nonconstant intercept; preserved BFGS policy.

Adapted from partition_coordinate_fit_001/fitting.py; earlier source unchanged.
"""
import math
import numpy as np
from experiments.voltage_coordinates_001 import coordinates as v
from experiments.partition_coordinate_fit_001.stable_normalizer import log_mass


def objective(theta, design, target, lower, upper, charge=None):
    if charge is not None:
        charge(len(target))
    v.require(np.isfinite(theta).all() and abs(theta[-1]) <= 40, 'optimizer arithmetic domain')
    mu = design @ theta[:-1]
    sd = math.exp(float(theta[-1]))
    residual = (mu-target)/sd
    if np.isneginf(lower).all() and np.isposinf(upper).all():
        logz = np.zeros(len(target))
        correction = np.zeros(len(target))
        scale_correction = np.zeros(len(target))
    else:
        a, b = (lower-mu)/sd, (upper-mu)/sd
        logz = log_mass(a, b)
        pa = np.exp(-.5*a*a-.5*v.old.LOG2PI-logz)
        pb = np.exp(-.5*b*b-.5*v.old.LOG2PI-logz)
        correction = pa-pb
        scale_correction = a*pa-b*pb
    loss = float(np.mean(.5*residual**2+theta[-1]+.5*v.old.LOG2PI+logz))
    grad = np.r_[design.T @ ((residual+correction)/sd)/len(target),
                 np.mean(1-residual**2+scale_correction)]
    v.require(np.isfinite(loss) and np.isfinite(grad).all(), 'nonfinite conditional objective')
    return loss, grad


def prepare(raw, values, lower, upper):
    # raw includes the nonconstant intercept1/a. Do not add or center it.
    n = len(values)
    q, r = np.linalg.qr(raw, mode='reduced')
    v.require(np.all(abs(np.diag(r)) > 0), 'singular physical-scale features')
    design = q*math.sqrt(n)
    initial = design.T @ values/n
    residual = values-design @ initial
    scale = float(np.sqrt(np.mean(residual*residual)))
    v.require(math.isfinite(scale) and scale > 0, 'nonpositive residual scale')
    target = values/scale
    theta = np.r_[initial/scale, 0.]
    return design, target, lower/scale, upper/scale, theta, r/math.sqrt(n), 0., scale


def fit(features, values, lower, upper, method, config, charge=None):
    design, target, lo, hi, theta, transform, center, scale = prepare(features, values, lower, upper)
    evaluations = 0

    def evaluate(t):
        nonlocal evaluations
        if evaluations >= config['evaluations_per_conditional']:
            raise v.old.Unavailable('conditional evaluation cap')
        evaluations += 1
        return objective(t, design, target, lo, hi, charge)

    loss, grad = evaluate(theta)
    initial_loss, initial_gradient = loss, float(abs(grad).max())
    rejected = 0
    iterations = 0
    resets = 0
    status = 'projection_not_optimized'
    if method == 'bounded_likelihood':
        size = len(theta)
        metric = np.eye(size)
        metric[-1, -1] = .5
        status = 'iteration_limit'
        for iteration in range(config['iterations_per_conditional']):
            if abs(grad).max() <= config['gradient_infinity_tolerance']:
                status = 'gradient_tolerance_met'
                break
            direction = -metric @ grad
            if not np.isfinite(direction).all() or direction @ grad >= 0:
                metric = np.eye(size)
                metric[-1, -1] = .5
                direction = -metric @ grad
                resets += 1
            accepted = False
            exhausted = False
            for backtrack in range(config['backtracking_attempts']):
                alpha = 2.**(-backtrack)
                trial = theta+alpha*direction
                try:
                    new_loss, new_grad = evaluate(trial)
                except v.old.Unavailable as error:
                    if 'cap' in str(error):
                        exhausted = True
                        break
                    rejected += 1
                    continue
                if new_loss <= loss+config['armijo']*alpha*(grad @ direction):
                    accepted = True
                    break
                rejected += 1
            if not accepted:
                status = 'evaluation_limit' if exhausted else 'line_search_failed'
                break
            step, change = trial-theta, new_grad-grad
            curvature = step @ change
            if curvature > config['curvature_relative_guard']*np.linalg.norm(step)*np.linalg.norm(change):
                matrix = np.eye(size)-np.outer(step, change)/curvature
                metric = matrix @ metric @ matrix.T+np.outer(step, step)/curvature
            else:
                metric = np.eye(size)
                metric[-1, -1] = .5
                resets += 1
            theta, loss, grad = trial, new_loss, new_grad
            iterations = iteration+1
        if abs(grad).max() <= config['gradient_infinity_tolerance']:
            status = 'gradient_tolerance_met'
    elif method != 'moment_projection':
        raise v.old.Unavailable('unknown fit method')
    coefficients = scale*np.linalg.solve(transform, theta[:-1])
    coefficients[0] += center
    logsd = math.log(scale)+theta[-1]
    v.require(loss <= initial_loss+1e-12, 'optimizer increased construction objective')
    return coefficients, logsd, dict(status=status, iterations=iterations, evaluations=evaluations,
        rejected_trials=rejected, metric_resets=resets,
        initial_mean_NLL=initial_loss+math.log(scale), final_mean_NLL=loss+math.log(scale),
        initial_gradient_infinity=initial_gradient, final_gradient_infinity=float(abs(grad).max()),
        coefficient_count=len(coefficients), stationarity_scope='Whitened fixed-membership conditional objective, not global mixture likelihood or posterior coverage')
