"""Offline full16 probability messages. No rolling or physical aging update.

Each chart describes alternative mass of ONE posterior, including its prior.
No clipping, diagonalization, covariance jitter, or uncertainty / sample-count.
"""
from dataclasses import dataclass
from functools import lru_cache
import math
import numpy as np
from experiments.minimal_health_kernels_001 import kernel

LOW = kernel.LOW.copy()
HIGH = kernel.HIGH.copy()
LOW[11:15] = [0., -.25, -.25, -.25]
HIGH[11:15] = [1., .25, .25, .25]
WIDTH = HIGH - LOW
OTHER = np.array([i for i in range(16) if i != 5])
LOG2PI = math.log(2 * math.pi)


class Unavailable(ValueError):
    pass


def require(ok, reason):
    if not ok:
        raise Unavailable(reason)


def to_unit(x):
    x = np.asarray(x, dtype=float)
    require(x.ndim == 2 and x.shape[1] == 16 and np.isfinite(x).all(), 'invalid full16 input')
    u = (x - LOW) / WIDTH
    require(np.all((u > 0) & (u < 1)), 'outside open support; no clipping')
    return u


def logit(u):
    return np.log(u) - np.log1p(-u)


def from_logits(y):
    # Stable logistic, without converting endpoint rounding into clipped mass.
    e = np.exp(-np.abs(y))
    u = np.where(y >= 0, 1 / (1 + e), e / (1 + e))
    require(np.all((u > 0) & (u < 1)), 'inverse transform rounded to support boundary')
    return u


def log_jacobian(u, indices):
    return (-np.log(WIDTH[indices]) - np.log(u[:, indices]) - np.log1p(-u[:, indices])).sum(axis=1)


def pack_factor(cov):
    require(np.isfinite(cov).all(), 'nonfinite covariance')
    try:
        l = np.linalg.cholesky(cov)
    except np.linalg.LinAlgError as e:
        raise Unavailable('nonpositive covariance; no jitter repair') from e
    return l[np.tril_indices(len(l))]


def unpack_factor(p, d):
    l = np.zeros((d, d))
    l[np.tril_indices(d)] = p
    return l


def gaussian_logpdf(y, mean, packed):
    d = y.shape[1]
    l = unpack_factor(packed, d)
    v = np.linalg.solve(l, (y - mean).T).T
    return -.5 * (v * v).sum(axis=1) - np.log(np.diag(l)).sum() - .5 * d * LOG2PI


@lru_cache(maxsize=2)
def quadrature(order):
    t, w = np.polynomial.legendre.leggauss(order)
    return np.column_stack((t, t*t)), np.log(w)


def quad_stats(theta, order=128):
    features, lw = quadrature(order)
    v = features @ theta + lw
    peak = v.max()
    w = np.exp(v - peak)
    z = w.sum()
    w /= z
    mean = w @ features
    delta = features - mean
    return float(peak + np.log(z)), mean, (delta.T * w) @ delta


def fit_quadratic(t):
    target = np.array([np.mean(t), np.mean(t*t)])
    theta = np.zeros(2)
    for iteration in range(64):
        logz, mean, hess = quad_stats(theta)
        residual = mean - target
        if abs(residual).max() <= 1e-9:
            z256, m256, _ = quad_stats(theta, 256)
            require(abs(z256-logz) <= 1e-9 and abs(m256-target).max() <= 2e-9,
                    'quadrature verification failed')
            return theta, logz, dict(iterations=iteration+1,
                moment_residual=float(abs(residual).max()), logZ_refinement=abs(z256-logz))
        direction = np.linalg.solve(hess, residual)
        objective = logz - theta @ target
        for backtrack in range(32):
            trial = theta - 2.**(-backtrack) * direction
            nz, _, _ = quad_stats(trial)
            if nz - trial @ target <= objective + 1e-14:
                theta = trial
                break
        else:
            raise Unavailable('maxent line search exhausted')
    raise Unavailable('maxent iteration cap')


def placement(q, k, adaptive):
    edges = np.linspace(0., 1., k+1)
    centers = (edges[:-1] + edges[1:]) / 2
    if adaptive:
        for _ in range(16):
            labels = np.searchsorted(edges[1:-1], q, side='right')
            counts = np.bincount(labels, minlength=k)
            require(np.all(counts >= 32), 'undersupported placement region')
            centers = np.array([q[labels == j].mean() for j in range(k)])
            edges[1:-1] = (centers[:-1] + centers[1:]) / 2
    return edges


@dataclass
class Message:
    arm: str
    edges: np.ndarray
    regions: list
    diagnostics: list

    @property
    def numeric_bytes(self):
        return self.edges.nbytes + sum(np.asarray(v).nbytes for r in self.regions for v in r.values())

    def logpdf(self, x):
        u = to_unit(x)
        if self.arm == 'fixed_partition_gaussian_mixture':
            y = logit(u)
            values = [gaussian_logpdf(y, r['mean'], r['factor']) + r['logweight'] for r in self.regions]
            return np.logaddexp.reduce(values) + log_jacobian(u, np.arange(16))
        labels = np.searchsorted(self.edges[1:-1], u[:, 5], side='right')
        out = np.empty(len(x))
        for j, r in enumerate(self.regions):
            take = labels == j
            left, right = self.edges[j:j+2]
            t = 2*(u[take, 5] - left)/(right-left)-1
            y = logit(u[take][:, OTHER])
            mean = r['intercept'] + t[:, None] * r['slope']
            out[take] = (r['logweight'] + r['theta'][0]*t + r['theta'][1]*t*t - r['logZ']
                         + gaussian_logpdf(y, mean, r['factor']) + math.log(2/((right-left)*WIDTH[5]))
                         + log_jacobian(u[take], OTHER))
        return out

    def draw(self, n, seed):
        rng = np.random.default_rng(seed)
        labels = rng.choice(len(self.regions), size=n, p=np.exp([r['logweight'] for r in self.regions]))
        u = np.empty((n, 16))
        proposed = 0
        for j, r in enumerate(self.regions):
            take = np.flatnonzero(labels == j)
            size = len(take)
            if self.arm == 'fixed_partition_gaussian_mixture':
                y = rng.normal(size=(size, 16)) @ unpack_factor(r['factor'], 16).T + r['mean']
                u[take] = from_logits(y)
            else:
                # Exact rejection sampling from the finite quadratic, up to FP.
                a, b = r['theta']
                maxima = [a+b, -a+b]
                if b < 0 and abs(-a/(2*b)) < 1:
                    maxima.append(-a*a/(4*b))
                peak = max(maxima)
                values = []
                remaining = size
                for _ in range(128):
                    if remaining == 0:
                        break
                    batch = max(256, 2*remaining)
                    ts = rng.uniform(-1, 1, batch)
                    accepted = ts[np.log(rng.random(batch)) < a*ts + b*ts*ts - peak][:remaining]
                    values.append(accepted)
                    remaining -= len(accepted)
                    proposed += batch
                require(remaining == 0, 'quadratic sampler cap exhausted')
                t = np.concatenate(values) if size else np.empty(0)
                y = (rng.normal(size=(size, 15)) @ unpack_factor(r['factor'], 15).T
                     + r['intercept'] + t[:, None]*r['slope'])
                u[np.ix_(take, OTHER)] = from_logits(y)
                left, right = self.edges[j:j+2]
                u[take, 5] = left + (t+1)*(right-left)/2
        x = LOW + WIDTH*u
        to_unit(x)
        return x, proposed

    def export(self):
        return dict(arm=self.arm, edges=self.edges.tolist(),
                    regions=[{k: np.asarray(v).tolist() for k, v in r.items()} for r in self.regions])

    @classmethod
    def restore(cls, data):
        return cls(data['arm'], np.array(data['edges']),
                   [{k: np.asarray(v) for k, v in r.items()} for r in data['regions']], [])


def fit(x, k, arm):
    require(arm in ('fixed_partition_gaussian_mixture', 'fixed_probability_atlas', 'adaptive_probability_atlas'), 'unknown arm')
    u = to_unit(x)
    edges = placement(u[:, 5], k, arm == 'adaptive_probability_atlas')
    labels = np.searchsorted(edges[1:-1], u[:, 5], side='right')
    counts = np.bincount(labels, minlength=k)
    require(np.all(counts >= 32), 'undersupported fitted region')
    regions, diagnostics = [], []
    for j, count in enumerate(counts):
        sample = u[labels == j]
        r = dict(logweight=np.array(math.log(count/len(x))))
        if arm == 'fixed_partition_gaussian_mixture':
            y = logit(sample)
            mean = y.mean(axis=0)
            delta = y - mean
            r.update(mean=mean, factor=pack_factor(delta.T @ delta/count))
            diag = {}
        else:
            left, right = edges[j:j+2]
            t = 2*(sample[:, 5]-left)/(right-left)-1
            theta, logz, diag = fit_quadratic(t)
            y = logit(sample[:, OTHER])
            tc, yc = t-t.mean(), y-y.mean(axis=0)
            slope = tc @ yc / (tc @ tc)
            intercept = y.mean(axis=0) - slope*t.mean()
            residual = yc - tc[:, None]*slope
            r.update(theta=theta, logZ=np.array(logz), slope=slope, intercept=intercept,
                     factor=pack_factor(residual.T @ residual/count))
        diag.update(count=int(count), min_factor_diagonal=float(np.diag(unpack_factor(r['factor'], 16 if 'mean' in r else 15)).min()))
        regions.append(r)
        diagnostics.append(diag)
    return Message(arm, edges, regions, diagnostics)


def stationary_probe(x, steps):
    """Declared future probes only; exact constant-input RC steps, no health drift.

    Return support status for each original draw, retaining invalid mass.
    Invalid outputs must never be presented as a normalized predictive density.
    """
    x = np.asarray(x)
    z, rc, h = x[:, 11].copy(), x[:, 12:15].copy(), x[:, 15].copy()
    valid = np.ones(len(x), dtype=bool)
    current = 0.
    for current, dt in steps:
        z -= current*dt/(3600*np.exp(x[:, 5]))
        exposure = dt/np.exp(x[:, :3])
        rc = np.exp(-exposure)*rc - np.expm1(-exposure)*x[:, 7:10]*current
        if current:
            exposure = np.exp(x[:, 3 if current > 0 else 4])*abs(current)*dt/3600
            h = np.exp(-exposure)*h - np.expm1(-exposure)*math.copysign(1, current)
        valid &= (z >= 0) & (z <= 1) & np.all(abs(rc) <= .25, axis=1) & (abs(h) <= 1)
    voltage = 3 + 1.15*z + .08*np.tanh(8*(z-.5)) - rc.sum(axis=1) - current*x[:, 6] - x[:, 10]*h
    return voltage, valid
