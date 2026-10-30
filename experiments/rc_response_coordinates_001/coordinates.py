"""Full16 RC response coordinate chains with exact conditional support."""
from dataclasses import dataclass
import math
import numpy as np
from experiments.voltage_coordinates_001 import coordinates as v

old = v.old
BASE = np.array([0, 1, 2, 3, 4, 5, 6, 10, 15])
ATLAS_BASE = np.array([i for i in BASE if i != 5])
OFFSETS = np.r_[0, np.cumsum(np.arange(10, 17))]


def frame_values(name):
    if name == 'physical_amplitude_control':
        return np.zeros(3)
    if name == 'response_1s':
        return np.ones(3)
    if name == 'response_public_mode_scale':
        return np.exp((old.LOW[:3]+old.HIGH[:3])/2)
    raise old.Unavailable('unknown response frame')


def attenuation(x, frame):
    if np.all(frame == 0):
        return np.ones((len(x), 3))
    old.require(np.all(frame > 0), 'nonpositive response interval')
    a = -np.expm1(-frame/np.exp(x[:, :3]))
    old.require(np.isfinite(a).all() and np.all(a > 0), 'unresolved RC coordinate scale')
    return a


def chain_bounds(x, a, step):
    if step < 3:
        return -.25*a[:, step], .25*a[:, step]
    if step < 6:
        return np.zeros(len(x)), a[:, step-3]
    shift = v.offset(x)
    return v.ocv(0)-shift, v.ocv(1)-shift


def coefficients(region, step):
    return region['chain_coefficients'][OFFSETS[step]:OFFSETS[step+1]]


def encode(x, frame, interval=None):
    u = old.to_unit(x)
    a = attenuation(x, frame)
    y = np.empty((len(x), 16))
    if interval is None:
        y[:, :9] = old.logit(u[:, BASE])
        jacobian = old.log_jacobian(u, BASE)
    else:
        lo, hi = interval
        y[:, 0] = 2*(u[:, 5]-lo)/(hi-lo)-1
        y[:, 1:9] = old.logit(u[:, ATLAS_BASE])
        jacobian = old.log_jacobian(u, ATLAS_BASE)+math.log(2/((hi-lo)*old.WIDTH[5]))
    y[:, 9:12] = a*x[:, 12:15]
    y[:, 12:15] = a*x[:, 7:10]
    y[:, 15] = v.voltage(x)
    jacobian += 2*np.log(a).sum(axis=1)+np.log(v.ocv_derivative(x[:, 11]))
    return y, a, jacobian


def decode(y, frame, interval=None):
    """Deterministic inverse used by controls, without clipping or inference."""
    x = np.full(y.shape, np.nan)
    if interval is None:
        x[:, BASE] = old.LOW[BASE]+old.WIDTH[BASE]*old.from_logits(y[:, :9])
    else:
        lo, hi = interval
        x[:, 5] = old.LOW[5]+old.WIDTH[5]*(lo+(hi-lo)*(y[:, 0]+1)/2)
        x[:, ATLAS_BASE] = old.LOW[ATLAS_BASE]+old.WIDTH[ATLAS_BASE]*old.from_logits(y[:, 1:9])
    a = attenuation(x, frame)
    x[:, 12:15], x[:, 7:10] = y[:, 9:12]/a, y[:, 12:15]/a
    x[:, 11] = v.inverse_ocv(y[:, 15]+v.offset(x))
    old.to_unit(x)
    return x


def chain_density(region, y, x, a):
    values = np.zeros(len(x))
    logz = np.empty((len(x), 7))
    for step in range(7):
        j = 9+step
        coef = coefficients(region, step)
        mu = coef[0]+y[:, :j] @ coef[1:]
        sd = math.exp(float(region['chain_logsd'][step]))
        lower, upper = chain_bounds(x, a, step)
        logz[:, step] = v.log_mass((lower-mu)/sd, (upper-mu)/sd)
        values += -.5*((y[:, j]-mu)/sd)**2-math.log(sd)-.5*old.LOG2PI-logz[:, step]
    return values, logz


@dataclass
class Message(old.Message):
    frame: np.ndarray

    @property
    def numeric_bytes(self):
        return super().numeric_bytes+self.frame.nbytes

    def export(self):
        value = super().export()
        value['frame'] = self.frame.tolist()
        return value

    @classmethod
    def restore(cls, data):
        return cls(data['arm'], np.array(data['edges']),
                   [{k: np.asarray(z) for k, z in reg.items()} for reg in data['regions']], [], np.array(data['frame']))

    def logpdf_details(self, x):
        if self.arm == 'fixed_partition_gaussian_mixture':
            y, a, jacobian = encode(x, self.frame)
            values, normalizers = [], []
            for reg in self.regions:
                chain, logz = chain_density(reg, y, x, a)
                values.append(reg['logweight']+old.gaussian_logpdf(y[:, :9], reg['mean'], reg['factor'])+chain)
                normalizers.append(logz)
            return np.logaddexp.reduce(values)+jacobian, np.concatenate(normalizers)
        u = old.to_unit(x)
        labels = np.searchsorted(self.edges[1:-1], u[:, 5], side='right')
        values, normalizers = np.empty(len(x)), []
        for j, reg in enumerate(self.regions):
            take = labels == j
            y, a, jacobian = encode(x[take], self.frame, self.edges[j:j+2])
            t = y[:, 0]
            mean = reg['intercept']+t[:, None]*reg['slope']
            chain, logz = chain_density(reg, y, x[take], a)
            values[take] = (reg['logweight']+reg['theta'][0]*t+reg['theta'][1]*t*t-reg['logZ']
                            +old.gaussian_logpdf(y[:, 1:9], mean, reg['factor'])+chain+jacobian)
            normalizers.append(logz)
        return values, np.concatenate(normalizers)

    def logpdf(self, x):
        return self.logpdf_details(x)[0]

    def draw(self, n, seed):
        rng = np.random.default_rng(seed)
        labels = rng.choice(len(self.regions), size=n, p=np.exp([reg['logweight'] for reg in self.regions]))
        x = np.full((n, 16), np.nan)
        normalizers, proposals, quadratic_proposals = [], 0, 0
        for j, reg in enumerate(self.regions):
            take = np.flatnonzero(labels == j)
            size = len(take)
            y = np.empty((size, 16))
            local = np.full((size, 16), np.nan)
            if self.arm == 'fixed_partition_gaussian_mixture':
                y[:, :9] = rng.normal(size=(size, 9)) @ old.unpack_factor(reg['factor'], 9).T+reg['mean']
                local[:, BASE] = old.LOW[BASE]+old.WIDTH[BASE]*old.from_logits(y[:, :9])
            else:
                t, count = v.quadratic_draw(reg, size, rng)
                quadratic_proposals += count
                y[:, 0] = t
                y[:, 1:9] = (rng.normal(size=(size, 8)) @ old.unpack_factor(reg['factor'], 8).T
                              +reg['intercept']+t[:, None]*reg['slope'])
                lo, hi = self.edges[j:j+2]
                local[:, 5] = old.LOW[5]+old.WIDTH[5]*(lo+(hi-lo)*(t+1)/2)
                local[:, ATLAS_BASE] = old.LOW[ATLAS_BASE]+old.WIDTH[ATLAS_BASE]*old.from_logits(y[:, 1:9])
            a = attenuation(local, self.frame)
            logz = np.empty((size, 7))
            for step in range(7):
                index = 9+step
                coef = coefficients(reg, step)
                mu = coef[0]+y[:, :index] @ coef[1:]
                sd = math.exp(float(reg['chain_logsd'][step]))
                lower, upper = chain_bounds(local, a, step)
                left, right = (lower-mu)/sd, (upper-mu)/sd
                logz[:, step] = v.log_mass(left, right)
                draw, count = v.truncated_standard_draw(left, right, rng)
                proposals += count
                y[:, index] = mu+sd*draw
                if step < 3:
                    local[:, 12+step] = y[:, index]/a[:, step]
                elif step < 6:
                    local[:, 7+step-3] = y[:, index]/a[:, step-3]
                else:
                    local[:, 11] = v.inverse_ocv(y[:, index]+v.offset(local))
            old.to_unit(local)
            x[take] = local
            normalizers.append(logz)
        return x, dict(log_normalizers=np.concatenate(normalizers), normal_proposals=proposals,
                       quadratic_proposals=quadratic_proposals)


def fit(x, k, arm, frame_name):
    old.require(arm in ('fixed_partition_gaussian_mixture', 'fixed_probability_atlas', 'adaptive_probability_atlas'), 'unknown arm')
    u = old.to_unit(x)
    frame = frame_values(frame_name)
    edges = old.placement(u[:, 5], k, arm.startswith('adaptive'))
    labels = np.searchsorted(edges[1:-1], u[:, 5], side='right')
    counts = np.bincount(labels, minlength=k)
    old.require(np.all(counts >= 32), 'undersupported region')
    regions, diagnostics = [], []
    for j, count in enumerate(counts):
        take = labels == j
        interval = None if 'mixture' in arm else edges[j:j+2]
        y, a, _ = encode(x[take], frame, interval)
        reg = dict(logweight=np.array(math.log(count/len(x))))
        if interval is None:
            mean = y[:, :9].mean(0)
            delta = y[:, :9]-mean
            reg.update(mean=mean, factor=old.pack_factor(delta.T @ delta/count))
            diagnostic = {}
        else:
            t = y[:, 0]
            theta, logz, diagnostic = old.fit_quadratic(t)
            tc, yc = t-t.mean(), y[:, 1:9]-y[:, 1:9].mean(0)
            slope = tc @ yc/(tc @ tc)
            residual = yc-tc[:, None]*slope
            reg.update(theta=theta, logZ=np.array(logz), intercept=y[:, 1:9].mean(0)-slope*t.mean(),
                       slope=slope, factor=old.pack_factor(residual.T @ residual/count))
        fitted = [v.fit_voltage(y[:, :index], y[:, index]) for index in range(9, 16)]
        reg.update(chain_coefficients=np.concatenate([p['voltage_coeff'] for p in fitted]),
                   chain_logsd=np.array([p['voltage_logsd'] for p in fitted]))
        _, norms = chain_density(reg, y, x[take], a)
        diagnostic.update(count=int(count), construction_max_removed_mass_by_step=np.max(-np.expm1(norms), axis=0).tolist(),
                          construction_mean_removed_mass_by_step=np.mean(-np.expm1(norms), axis=0).tolist())
        regions.append(reg)
        diagnostics.append(diagnostic)
    return Message(arm, edges, regions, diagnostics, frame)
