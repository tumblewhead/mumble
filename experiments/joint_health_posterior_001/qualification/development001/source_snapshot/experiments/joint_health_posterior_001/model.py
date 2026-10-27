"""Vectorized full-path target in a noncentered health chart.

u[:16]=(initial_x-public_mean)/public_sd; remaining u are Gaussian health
innovations. Every static parameter and initial physical state stays uncertain.
The health change of variables cancels sqrt(variance), NOT the truncation Z.
No truth, fitted anchor, previous posterior or curvature enters this target.
"""
from dataclasses import replace
import math
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'minimal_health_kernels_001'))
import kernel as k

Q_MEANS = np.array([-3.0907210901048416, -2.536100343415231])
Q_SD = .20951093757861336
LOG2PI = math.log(2*math.pi)


def truncated_draw(rng, mean, sd, lower, upper, max_rounds=256):
    """Exact normal rejection draws within finite work; never clip a sample."""
    mean = np.asarray(mean, dtype=float)
    out = np.empty_like(mean)
    pending = np.arange(mean.size)
    for _ in range(max_rounds):
        if not len(pending):
            return out
        values = mean[pending]+sd*rng.normal(size=len(pending))
        good = (values >= lower) & (values <= upper)
        out[pending[good]] = values[good]
        pending = pending[~good]
    raise k.ModelError('sampling_unresolved', 'bounded normal rejection limit')


def initial_draw(rng, size):
    x = np.empty((size, 16))
    for j in range(16):
        if j != 5:
            x[:, j] = truncated_draw(rng, np.full(size, k.MEAN[j]), k.SD[j], k.LOW[j], k.HIGH[j])
        else:
            # Redraw mixture LABEL as well as value when rejected. Equal
            # post-truncation labels would silently change the original prior.
            pending = np.arange(size)
            for _ in range(256):
                if not len(pending):
                    break
                q = Q_MEANS[rng.integers(0, 2, len(pending))]+Q_SD*rng.normal(size=len(pending))
                good = (q >= k.LOW[5]) & (q <= k.HIGH[5])
                x[pending[good], 5] = q[good]
                pending = pending[~good]
            if len(pending):
                raise k.ModelError('sampling_unresolved', 'initial mixture rejection limit')
    return x


def initial_log_density(x):
    d = (x-k.MEAN)/k.SD
    d[:, 5] = 0.
    terms = -.5*((x[:, 5, None]-Q_MEANS)/Q_SD)**2
    logq = np.logaddexp(terms[:, 0], terms[:, 1])-math.log(2)-math.log(Q_SD)-.5*LOG2PI
    other_norm = np.log(k.SD).sum()-math.log(k.SD[5])+7.5*LOG2PI
    return -.5*np.sum(d*d, axis=1)-other_norm+logq


def log_normalizer(mean, variance, lower, upper):
    """erfc on safe intervals; qualified scaled scalar integral in difficult tails."""
    s = math.sqrt(variance)
    mean = np.asarray(mean)
    left, right = (mean-lower)/(s*math.sqrt(2)), (upper-mean)/(s*math.sqrt(2))
    z = 1.-.5*np.fromiter((math.erfc(v) for v in left), float, len(mean))
    z -= .5*np.fromiter((math.erfc(v) for v in right), float, len(mean))
    # For cancellation-prone small probabilities use the bound kernel, never
    # turn an unresolved normalizer into rejection or zero posterior mass.
    hard = (z < .01) | ~np.isfinite(z)
    result = np.empty_like(z)
    result[~hard] = np.log(z[~hard])
    for j in np.flatnonzero(hard):
        result[j] = k.normalizer(float(mean[j]), variance, lower, upper).log_Z
    return result


class Target:
    def __init__(self, records, profile, source_id='fixture', max_paths=8_000_000):
        self.records, self.profile = tuple(records), profile
        self.source_id, self.max_paths = source_id, max_paths
        self.path_evaluations = self.model_steps = 0
        state = k.initial_state(k.MEAN, source_id)
        for n, r in enumerate(self.records):
            k.validate_record(replace(state, next_index=n), r)
        self.increments = tuple(profile.increments(r.dt, r.current) for r in self.records)
        self.coordinates = tuple((n, j) for n, (_, v) in enumerate(self.increments) for j in range(2) if v[j] > 0)
        self.dimension = 16+len(self.coordinates)
        self.log_jacobian = float(np.log(k.SD).sum())+sum(
            .5*math.log(self.increments[n][1][j]) for n, j in self.coordinates)

    def draw(self, rng, size):
        """Joint prior conditioned on physical support, via whole-path rejection."""
        accepted = []
        remaining = size
        for _ in range(64):
            if remaining == 0:
                return np.concatenate(accepted)
            x = initial_draw(rng, remaining)
            u = np.zeros((remaining, self.dimension))
            u[:, :16] = (x-k.MEAN)/k.SD
            health = x[:, [5, 6]].copy()
            cursor = 16
            valid = np.ones(remaining, dtype=bool)
            for means, variances in self.increments:
                for j in range(2):
                    mu = health[:, j]+means[j]
                    if variances[j] > 0:
                        y = truncated_draw(rng, mu, math.sqrt(variances[j]), k.LOW[5+j], k.HIGH[5+j])
                        u[:, cursor] = (y-mu)/math.sqrt(variances[j])
                        cursor += 1
                    else:
                        y = mu
                        valid &= (y >= k.LOW[5+j]) & (y <= k.HIGH[5+j])
                    health[:, j] = y
            prior, _, _ = self.evaluate(u)
            valid &= np.isfinite(prior)
            accepted.append(u[valid])
            remaining -= int(valid.sum())
        raise k.ModelError('sampling_unresolved', 'whole-path prior support rejection limit')

    def evaluate(self, u):
        u = np.asarray(u, dtype=float)
        k.require(u.ndim == 2 and u.shape[1] == self.dimension and np.isfinite(u).all(),
                  'invalid_input', 'path chart')
        self.path_evaluations += len(u)
        k.require(self.path_evaluations <= self.max_paths, 'resource_limit', 'path evaluation cap')
        x = k.MEAN+k.SD*u[:, :16]
        good = np.all((x >= k.LOW) & (x <= k.HIGH), axis=1)
        logprior = np.full(len(u), -np.inf)
        loglike = np.zeros(len(u))
        # Original16 order with current fast/health; Q in Ah, capacity-mixture
        # responsibility, then previous-boundary Q/R0 are extra diagnostics.
        projected = np.zeros((len(u), 20))
        ix = np.flatnonzero(good)
        if not len(ix):
            return logprior, loglike, projected
        xx, uu = x[ix], u[ix]
        lp = initial_log_density(xx)+float(np.log(k.SD).sum())
        ll = np.zeros(len(ix))
        z, rc, hyst = xx[:, 11].copy(), xx[:, 12:15].copy(), xx[:, 15].copy()
        health = xx[:, [5, 6]].copy()
        previous_health = health.copy()
        valid = np.ones(len(ix), dtype=bool)
        cursor = 16
        for n, r in enumerate(self.records):
            self.model_steps += len(ix)
            previous_health = health.copy()
            means, variances = self.increments[n]
            for j in range(2):
                mu = health[:, j]+means[j]
                if variances[j] > 0:
                    innovation = uu[:, cursor]
                    health[:, j] = mu+math.sqrt(variances[j])*innovation
                    # Noncentered density: Gaussian innovation / Z(previous).
                    # Only still-valid paths require a normalizer evaluation.
                    active = np.flatnonzero(valid)
                    lp[active] += -.5*innovation[active]**2-.5*LOG2PI-log_normalizer(
                        mu[active], variances[j], k.LOW[5+j], k.HIGH[5+j])
                    cursor += 1
                else:
                    health[:, j] = mu
                valid &= (health[:, j] >= k.LOW[5+j]) & (health[:, j] <= k.HIGH[5+j])
            # Invalid proposals have zero density. Use a finite placeholder
            # solely to avoid overflow in subsequently discarded arithmetic.
            safe_q = np.where(valid, health[:, 0], k.MEAN[5])
            z -= r.current*r.dt/3600./np.exp(safe_q)
            t = r.dt/np.exp(xx[:, :3])
            rc = np.exp(-t)*rc-np.expm1(-t)*xx[:, 7:10]*r.current
            if r.current != 0 and r.dt != 0:
                t = np.exp(xx[:, 3 if r.current > 0 else 4])*abs(r.current)*r.dt/3600.
                hyst = np.exp(-t)*hyst-np.expm1(-t)*math.copysign(1., r.current)
            valid &= (z >= 0) & (z <= 1) & np.all(abs(rc) <= .25, axis=1) & (abs(hyst) <= 1)
            voltage = 3+1.15*z+.08*np.tanh(8*(z-.5))-r.current*health[:, 1]-rc.sum(axis=1)-xx[:, 10]*hyst
            if r.measurement_valid:
                ll += -.5*((voltage-r.voltage)/k.SIGMA)**2-math.log(k.SIGMA)-.5*LOG2PI
        out = xx.copy()
        out[:, 5:7], out[:, 11], out[:, 12:15], out[:, 15] = health, z, rc, hyst
        terms = -.5*((xx[:, 5, None]-Q_MEANS)/Q_SD)**2
        component = np.exp(terms[:, 0]-np.logaddexp(terms[:, 0], terms[:, 1]))
        p = np.column_stack((out, np.exp(np.where(valid, health[:, 0], k.MEAN[5])),
                             component, np.exp(previous_health[:, 0]), previous_health[:, 1]))
        logprior[ix[valid]], loglike[ix[valid]], projected[ix[valid]] = lp[valid], ll[valid], p[valid]
        k.require(np.isfinite(lp[valid]).all() and np.isfinite(ll[valid]).all()
                  and np.isfinite(p[valid]).all(), 'transition_numeric_unresolved', 'target arithmetic')
        return logprior, loglike, projected

    def centered_path(self, u):
        """Diagnostic conversion for comparison with the qualified scalar code."""
        x = k.MEAN+k.SD*np.asarray(u[:16])
        health = x[[5, 6]].copy()
        free, cursor = [], 16
        for means, variances in self.increments:
            for j in range(2):
                health[j] += means[j]
                if variances[j] > 0:
                    health[j] += math.sqrt(variances[j])*u[cursor]
                    free.append(health[j])
                    cursor += 1
        return x, free
