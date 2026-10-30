"""Normalized voltage-conditioned full16 messages; offline construction only."""
from dataclasses import dataclass
import math
import numpy as np
from experiments.region_compression_001 import regions as old

OTHER = np.array([i for i in range(16) if i != 11])
ETA = np.array([i for i in range(16) if i not in (5, 11)])
require = old.require


def ocv(z):
    return 3 + 1.15*z + .08*np.tanh(8*(z-.5))


def ocv_derivative(z):
    return 1.15 + .64*(1-np.tanh(8*(z-.5))**2)


def offset(x):
    return x[:, 12:15].sum(axis=1) + x[:, 10]*x[:, 15]


def voltage(x):
    return ocv(x[:, 11])-offset(x)


def inverse_ocv(w):
    w = np.asarray(w)
    require(np.isfinite(w).all() and np.all((w > ocv(0)) & (w < ocv(1))), 'inverse OCV outside open support')
    lo, hi = np.zeros_like(w), np.ones_like(w)
    for _ in range(52):
        mid = (lo+hi)/2
        below = ocv(mid) < w
        lo, hi = np.where(below, mid, lo), np.where(below, hi, mid)
    z = (lo+hi)/2
    require(np.max(abs(ocv(z)-w), initial=0) <= 2e-13, 'inverse OCV residual')
    return z


def log_mass(a, b):
    """Standard Gaussian interval mass, with scaled integral fallback.

    The 1e-8 cancellation guard selects arithmetic, not retained probability.
    A shift keeps the inherited kernel's auxiliary exp-coordinate finite.
    """
    a, b = np.broadcast_arrays(a, b)
    require(np.isfinite(a).all() and np.isfinite(b).all() and np.all(a < b), 'normalizer interval')
    shape = a.shape
    af, bf = a.ravel(), b.ravel()
    out = np.empty(len(af))
    for i, (left, right) in enumerate(zip(af, bf)):
        if left >= 0:
            large, small = .5*math.erfc(left/math.sqrt(2)), .5*math.erfc(right/math.sqrt(2))
        elif right <= 0:
            large, small = .5*math.erfc(-right/math.sqrt(2)), .5*math.erfc(-left/math.sqrt(2))
        else:
            large, small = 1., .5*math.erfc(-left/math.sqrt(2))+.5*math.erfc(right/math.sqrt(2))
        if large > 0 and large-small > 1e-8*large:
            out[i] = math.log(large)+math.log1p(-small/large)
        else:
            center = min(right, max(left, 0.))
            try:
                out[i] = old.kernel.normalizer(-center, 1., left-center, right-center).log_Z
            except (old.kernel.ModelError, OverflowError) as e:
                raise old.Unavailable('scaled normalizer unresolved: '+str(e)) from e
    require(np.isfinite(out).all() and np.all(out <= 1e-12), 'normalizer result')
    return out.reshape(shape)


def truncated_standard_draw(a, b, rng):
    """Rejection sampler with exact target and a bounded attempt count.

    Proposal switches affect efficiency only. No target mass is discarded.
    """
    a, b = np.broadcast_arrays(a, b)
    require(a.ndim == 1 and np.isfinite(a).all() and np.isfinite(b).all() and np.all(a < b), 'sampler support')
    out = np.empty(len(a))
    pending = np.arange(len(a))
    proposals = 0
    for _ in range(128):
        if not len(pending):
            break
        left, right = a[pending], b[pending]
        proposal = np.empty(len(pending))
        log_accept = np.zeros(len(pending))
        tail = (left >= 1) | (right <= -1)
        sign = np.where(left >= 1, 1., -1.)
        aa, bb = np.where(sign > 0, left, -right), np.where(sign > 0, right, -left)
        span = -np.expm1(-aa[tail]*(bb[tail]-aa[tail]))
        delta = -np.log1p(-rng.random(tail.sum())*span)/aa[tail]
        proposal[tail] = sign[tail]*(aa[tail]+delta)
        log_accept[tail] = -.5*delta*delta
        uniform = ~tail & (right-left < 2)
        proposal[uniform] = left[uniform]+(right[uniform]-left[uniform])*rng.random(uniform.sum())
        mode = np.minimum(right[uniform], np.maximum(left[uniform], 0.))
        log_accept[uniform] = -.5*(proposal[uniform]**2-mode**2)
        normal = ~tail & ~uniform
        proposal[normal] = rng.normal(size=normal.sum())
        accepted = ((proposal > left) & (proposal < right)
                    & (np.log(rng.random(len(pending))) < log_accept))
        out[pending[accepted]] = proposal[accepted]
        proposals += len(pending)
        pending = pending[~accepted]
    require(not len(pending), 'truncated sampler round cap')
    return out, proposals


def conditional_parameters(reg, features, x):
    mu = reg['voltage_coeff'][0] + features @ reg['voltage_coeff'][1:]
    sd = math.exp(float(reg['voltage_logsd']))
    shift = offset(x)
    a, b = (ocv(0)-shift-mu)/sd, (ocv(1)-shift-mu)/sd
    return mu, sd, a, b


def conditional_logpdf(reg, features, x):
    mu, sd, a, b = conditional_parameters(reg, features, x)
    z = log_mass(a, b)
    return -.5*((voltage(x)-mu)/sd)**2-math.log(sd)-.5*old.LOG2PI-z, z


def fit_voltage(features, values):
    center, mean = features.mean(axis=0), values.mean()
    delta = features-center
    slope, _, rank, _ = np.linalg.lstsq(delta, values-mean, rcond=None)
    require(rank == features.shape[1], 'rank-deficient voltage regression')
    residual = (values-mean)-delta @ slope
    variance = np.mean(residual*residual)
    require(np.isfinite(variance) and variance > 0, 'nonpositive voltage residual variance')
    return dict(voltage_coeff=np.r_[mean-center @ slope, slope], voltage_logsd=np.array(.5*math.log(variance)))


def quadratic_draw(region, size, rng):
    a, b = region['theta']
    maximum = max(a+b, -a+b)
    if b < 0 and abs(-a/(2*b)) < 1:
        maximum = max(maximum, -a*a/(4*b))
    remaining, values, proposed = size, [], 0
    for _ in range(128):
        if remaining == 0:
            break
        batch = max(256, remaining*2)
        t = rng.uniform(-1, 1, batch)
        accepted = t[np.log(rng.random(batch)) < a*t+b*t*t-maximum][:remaining]
        remaining -= len(accepted)
        values.append(accepted)
        proposed += batch
    require(remaining == 0, 'quadratic sampler cap')
    return np.concatenate(values) if size else np.empty(0), proposed


@dataclass
class Message(old.Message):
    def logpdf_details(self, x):
        u = old.to_unit(x)
        derivative = np.log(ocv_derivative(x[:, 11]))
        normalizers = []
        if self.arm == 'fixed_partition_gaussian_mixture':
            y = old.logit(u[:, OTHER])
            values = []
            for reg in self.regions:
                conditional, z = conditional_logpdf(reg, y, x)
                values.append(reg['logweight']+old.gaussian_logpdf(y, reg['mean'], reg['factor'])+conditional)
                normalizers.append(z)
            return np.logaddexp.reduce(values)+old.log_jacobian(u, OTHER)+derivative, np.concatenate(normalizers)
        labels = np.searchsorted(self.edges[1:-1], u[:, 5], side='right')
        values = np.empty(len(x))
        for j, reg in enumerate(self.regions):
            take = labels == j
            lo, hi = self.edges[j:j+2]
            t = 2*(u[take, 5]-lo)/(hi-lo)-1
            y = old.logit(u[take][:, ETA])
            features = np.column_stack((t, y))
            conditional, z = conditional_logpdf(reg, features, x[take])
            mean = reg['intercept']+t[:, None]*reg['slope']
            values[take] = (reg['logweight']+reg['theta'][0]*t+reg['theta'][1]*t*t-reg['logZ']
                            + old.gaussian_logpdf(y, mean, reg['factor'])+conditional
                            + math.log(2/((hi-lo)*old.WIDTH[5]))+old.log_jacobian(u[take], ETA)+derivative[take])
            normalizers.append(z)
        return values, np.concatenate(normalizers)

    def logpdf(self, x):
        return self.logpdf_details(x)[0]

    def draw(self, n, seed):
        rng = np.random.default_rng(seed)
        labels = rng.choice(len(self.regions), size=n, p=np.exp([r['logweight'] for r in self.regions]))
        x = np.empty((n, 16))
        norms, normal_proposals, quadratic_proposals = [], 0, 0
        for j, reg in enumerate(self.regions):
            take = np.flatnonzero(labels == j)
            size = len(take)
            if self.arm == 'fixed_partition_gaussian_mixture':
                y = rng.normal(size=(size, 15)) @ old.unpack_factor(reg['factor'], 15).T+reg['mean']
                features = y
                x[np.ix_(take, OTHER)] = old.LOW[OTHER]+old.WIDTH[OTHER]*old.from_logits(y)
            else:
                t, proposed = quadratic_draw(reg, size, rng)
                quadratic_proposals += proposed
                y = (rng.normal(size=(size, 14)) @ old.unpack_factor(reg['factor'], 14).T
                     +reg['intercept']+t[:, None]*reg['slope'])
                features = np.column_stack((t, y))
                x[np.ix_(take, ETA)] = old.LOW[ETA]+old.WIDTH[ETA]*old.from_logits(y)
                lo, hi = self.edges[j:j+2]
                x[take, 5] = old.LOW[5]+old.WIDTH[5]*(lo+(hi-lo)*(t+1)/2)
            # conditional_parameters uses only the initialized other15 values.
            mu, sd, a, b = conditional_parameters(reg, features, x[take])
            norms.append(log_mass(a, b))
            standard, proposed = truncated_standard_draw(a, b, rng)
            normal_proposals += proposed
            w = mu+sd*standard
            x[take, 11] = inverse_ocv(w+offset(x[take]))
        old.to_unit(x)
        return x, dict(normal_proposals=normal_proposals, quadratic_proposals=quadratic_proposals,
                       log_normalizers=np.concatenate(norms))


def fit(x, k, arm):
    require(arm in ('fixed_partition_gaussian_mixture', 'fixed_probability_atlas', 'adaptive_probability_atlas'), 'unknown arm')
    u = old.to_unit(x)
    edges = old.placement(u[:, 5], k, arm.startswith('adaptive'))
    labels = np.searchsorted(edges[1:-1], u[:, 5], side='right')
    counts = np.bincount(labels, minlength=k)
    require(np.all(counts >= 32), 'undersupported region')
    regions, diagnostics = [], []
    for j, count in enumerate(counts):
        take = labels == j
        reg = dict(logweight=np.array(math.log(count/len(x))))
        if arm == 'fixed_partition_gaussian_mixture':
            y = old.logit(u[take][:, OTHER])
            mean = y.mean(axis=0)
            delta = y-mean
            reg.update(mean=mean, factor=old.pack_factor(delta.T @ delta/count))
            features, diagnostic = y, {}
        else:
            lo, hi = edges[j:j+2]
            t = 2*(u[take, 5]-lo)/(hi-lo)-1
            theta, logz, diagnostic = old.fit_quadratic(t)
            y = old.logit(u[take][:, ETA])
            tc, yc = t-t.mean(), y-y.mean(0)
            slope = tc @ yc/(tc @ tc)
            residual = yc-tc[:, None]*slope
            reg.update(theta=theta, logZ=np.array(logz), intercept=y.mean(0)-slope*t.mean(),
                       slope=slope, factor=old.pack_factor(residual.T @ residual/count))
            features = np.column_stack((t, y))
        reg.update(fit_voltage(features, voltage(x[take])))
        _, _, a, b = conditional_parameters(reg, features, x[take])
        z = log_mass(a, b)
        diagnostic.update(count=int(count), voltage_conditional_SD_mV=1000*math.exp(float(reg['voltage_logsd'])),
                          construction_max_removed_probability=float(np.max(-np.expm1(z))),
                          construction_min_logZ=float(z.min()))
        regions.append(reg)
        diagnostics.append(diagnostic)
    return Message(arm, edges, regions, diagnostics)
