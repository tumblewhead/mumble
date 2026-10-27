"""Original prior plus normalized supplied-path density and first derivatives.

No optimizer, posterior, history compression, or calibrated uncertainty here.
Free variables: original x[16], then stochastic health coordinates in record
order (Q then R0). Deterministic coordinates are eliminated exactly.
"""
import math
import numpy as np
from kernel import (MEAN, SD, LOW, HIGH, FAST, STATIC, HEALTH, SIGMA,
                    initial_state, advance, transition, vector, require)


def prior(x):
    x = vector(x, 16, 'prior x')
    require(np.all(x >= LOW) and np.all(x <= HIGH), 'model_domain_exceeded', 'prior support')
    sd = SD.copy()
    sd[5] = .20951093757861336
    d = x-MEAN
    t = (x[5]-np.array([-3.0907210901048416, -2.536100343415231]))/sd[5]
    logp = -.5*t*t
    m = max(logp)
    ls = m+math.log(float(np.exp(logp-m).sum()))
    w = np.exp(logp-ls)
    v = d/sd
    v[5] = 0
    cost = .5*float(v@v)+float(np.log(sd).sum())+8*math.log(2*math.pi)+math.log(2)-ls
    grad = d/sd**2
    grad[5] = float(w@t)/sd[5]
    return cost, grad


def layout(records, profile):
    result = []
    for k, r in enumerate(records):
        _, var = profile.increments(r.dt, r.current)
        result.extend((k, j) for j in range(2) if var[j] > 0)
    return tuple(result)


def evaluate(x, records, profile, free_health=(), source_id='fixture'):
    records = tuple(records)
    coordinates = layout(records, profile)
    free_health = vector(free_health, len(coordinates), 'free health path')
    state = initial_state(x, source_id)
    prior_cost, pg = prior(x)
    dim = 16+len(coordinates)
    grad = np.zeros(dim)
    grad[:16] = pg
    basis = np.eye(dim)[:16]
    fs, hs = basis[list(FAST)].copy(), basis[list(HEALTH)].copy()
    ss = basis[list(STATIC)]
    likelihood, transition_cost, cursor = 0., 0., 0
    rows = []
    for r in records:
        increments, variances = profile.increments(r.dt, r.current)
        new_h, new_hs = [], hs.copy()
        for j in range(2):
            v = variances[j]
            if v > 0:
                y = free_health[cursor]
                new_hs[j] = 0.
                new_hs[j, 16+cursor] = 1.
                cursor += 1
            else:
                y = state.health[j]+increments[j]
            nll, gp, gy, _ = transition(state.health[j], y, increments[j], v,
                                        LOW[HEALTH[j]], HIGH[HEALTH[j]])
            transition_cost += nll
            if v > 0:
                grad += gp*hs[j]+gy*new_hs[j]
            new_h.append(y)
        local_to_path = np.vstack((fs, ss, new_hs))
        state, voltage, jac, vg = advance(state, r, new_h)
        fs, hs = jac@local_to_path, new_hs
        if r.measurement_valid:
            residual = (voltage-r.voltage)/SIGMA
            likelihood += .5*residual*residual+math.log(SIGMA*math.sqrt(2*math.pi))
            grad += residual/SIGMA*(vg@local_to_path)
        rows.append(dict(index=r.index, voltage=voltage, fast=state.fast, health=state.health,
                         measurement_valid=r.measurement_valid, temperature_C=r.temperature_C))
    return dict(nll=prior_cost+transition_cost+likelihood, gradient=grad,
        prior_nll=prior_cost, transition_nll=transition_cost, observation_nll=likelihood,
        state=state, rows=rows, free_health_coordinates=coordinates,
        owns_initial_prior=True, observation_interval=(0, len(records)),
        transition_interval=(0, len(records)),
        point_statistic_kind='supplied_path_density', posterior_numerical_status='not_computed',
        uncertainty_status='unresolved')
