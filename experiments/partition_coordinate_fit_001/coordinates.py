"""Linked transport/probability views and one full16 conditional mixture."""
from dataclasses import dataclass
import math
import numpy as np
from experiments.rc_response_coordinates_001 import coordinates as rc
from experiments.partition_coordinate_fit_001 import fitting

v, old = rc.v, rc.old
OFFSETS = np.r_[0, np.cumsum(np.arange(1, 17))]
PIVOTS = np.exp(-(old.LOW[:3]+old.HIGH[:3])/2)
RHO = np.tanh((old.HIGH[:3]-old.LOW[:3])/4)
GLO, GHI = np.exp(old.LOW[3:5]), np.exp(old.HIGH[3:5])
KLO, KHI = np.exp(-old.HIGH[5]), np.exp(-old.LOW[5])


def encode(x, chart, frame):
    y, a, jacobian = rc.encode(x, frame)
    if chart == 'current':
        return y, a, jacobian
    old.require(chart == 'specialized', 'unknown chart')
    u = old.to_unit(x)
    jacobian -= old.log_jacobian(u, rc.BASE)
    rate = np.exp(-x[:, :3])
    y[:, :3] = (rate-PIVOTS)/(rate+PIVOTS)/RHO
    jacobian += np.log(2*PIVOTS*rate/(RHO*(rate+PIVOTS)**2)).sum(1)
    gamma = np.exp(x[:, 3:5])
    y[:, 3:5] = 2*(gamma-GLO)/(GHI-GLO)-1
    jacobian += np.log(2*gamma/(GHI-GLO)).sum(1)
    kappa = np.exp(-x[:, 5])
    y[:, 5] = 2*(kappa-KLO)/(KHI-KLO)-1
    jacobian += np.log(2*kappa/(KHI-KLO))
    y[:, 6] = 2*x[:, 6]-1
    y[:, 7] = 2*x[:, 10]/old.HIGH[10]-1
    y[:, 8] = x[:, 15]
    jacobian += math.log(2)+math.log(2/old.HIGH[10])
    return y, a, jacobian


def set_coordinate(x, values, j, chart, frame):
    if j < 9:
        index = rc.BASE[j]
        if chart == 'current':
            x[:, index] = old.LOW[index]+old.WIDTH[index]*old.from_logits(values)
        elif j < 3:
            rate = PIVOTS[j]*(1+RHO[j]*values)/(1-RHO[j]*values)
            x[:, index] = -np.log(rate)
        elif j < 5:
            gamma = GLO[j-3]+(values+1)*(GHI[j-3]-GLO[j-3])/2
            x[:, index] = np.log(gamma)
        elif j == 5:
            x[:, index] = -np.log(KLO+(values+1)*(KHI-KLO)/2)
        elif j == 6:
            x[:, index] = (values+1)/2
        elif j == 7:
            x[:, index] = old.HIGH[10]*(values+1)/2
        else:
            x[:, index] = values
    elif j < 12:
        x[:, j+3] = values/rc.attenuation(x, frame)[:, j-9]
    elif j < 15:
        x[:, j-5] = values/rc.attenuation(x, frame)[:, j-12]
    else:
        x[:, 11] = v.inverse_ocv(values+v.offset(x))


def decode(y, chart, frame):
    x = np.full(y.shape, np.nan)
    for j in range(16):
        set_coordinate(x, y[:, j], j, chart, frame)
    old.to_unit(x)
    return x


def bounds(x, a, j, chart):
    if j < 9:
        if chart == 'current':
            return np.full(len(x), -np.inf), np.full(len(x), np.inf)
        return np.full(len(x), -1.), np.full(len(x), 1.)
    return rc.chain_bounds(x, a, j-9)


def normalizers(mu, sd, lower, upper):
    if np.isneginf(lower).all() and np.isposinf(upper).all():
        return np.zeros(len(mu))
    return v.log_mass((lower-mu)/sd, (upper-mu)/sd)


def coefficients(region, j):
    return region['coefficients'][OFFSETS[j]:OFFSETS[j+1]]


@dataclass
class Message:
    chart: str
    edges: np.ndarray
    frame: np.ndarray
    regions: list
    diagnostics: list

    @property
    def numeric_bytes(self):
        return self.edges.nbytes+self.frame.nbytes+sum(np.asarray(value).nbytes for reg in self.regions for value in reg.values())

    def export(self):
        return dict(chart=self.chart, edges=self.edges.tolist(), frame=self.frame.tolist(),
                    regions=[{key: np.asarray(value).tolist() for key, value in reg.items()} for reg in self.regions])

    @classmethod
    def restore(cls, data):
        return cls(data['chart'], np.array(data['edges']), np.array(data['frame']),
                   [{key: np.asarray(value) for key, value in reg.items()} for reg in data['regions']], [])

    def logpdf_details(self, x):
        y, a, jacobian = encode(x, self.chart, self.frame)
        components, corrections = [], []
        for reg in self.regions:
            values = np.full(len(x), float(reg['logweight']))
            logz = np.empty((len(x), 16))
            for j in range(16):
                beta = coefficients(reg, j)
                mu = beta[0]+y[:, :j] @ beta[1:]
                sd = math.exp(float(reg['logsd'][j]))
                lo, hi = bounds(x, a, j, self.chart)
                logz[:, j] = normalizers(mu, sd, lo, hi)
                values += -.5*((y[:, j]-mu)/sd)**2-math.log(sd)-.5*old.LOG2PI-logz[:, j]
            components.append(values)
            corrections.append(logz)
        return np.logaddexp.reduce(components)+jacobian, np.concatenate(corrections)

    def logpdf(self, x):
        return self.logpdf_details(x)[0]

    def draw(self, n, seed):
        rng = np.random.default_rng(seed)
        labels = rng.choice(len(self.regions), size=n, p=np.exp([reg['logweight'] for reg in self.regions]))
        x = np.full((n, 16), np.nan)
        corrections, proposals = [], 0
        for region_index, reg in enumerate(self.regions):
            take = np.flatnonzero(labels == region_index)
            local = np.full((len(take), 16), np.nan)
            y = np.empty_like(local)
            logz = np.empty_like(local)
            for j in range(16):
                beta = coefficients(reg, j)
                mu = beta[0]+y[:, :j] @ beta[1:]
                sd = math.exp(float(reg['logsd'][j]))
                a = rc.attenuation(local, self.frame) if j >= 9 else None
                lo, hi = bounds(local, a, j, self.chart)
                logz[:, j] = normalizers(mu, sd, lo, hi)
                if self.chart == 'current' and j < 9:
                    standard = rng.normal(size=len(take))
                    count = len(take)
                else:
                    standard, count = v.truncated_standard_draw((lo-mu)/sd, (hi-mu)/sd, rng)
                proposals += count
                y[:, j] = mu+sd*standard
                set_coordinate(local, y[:, j], j, self.chart, self.frame)
            old.to_unit(local)
            x[take] = local
            corrections.append(logz)
        return x, dict(log_normalizers=np.concatenate(corrections), normal_proposals=proposals)


def fit(x, chart, method, config, charge=None, progress=None):
    frame = rc.frame_values('response_public_mode_scale')
    edges = np.array([0., .5, 1.])
    labels = np.searchsorted(edges[1:-1], old.to_unit(x)[:, 5], side='right')
    y, a, _ = encode(x, chart, frame)
    regions, diagnostics = [], []
    for region_index in range(2):
        take = labels == region_index
        old.require(take.sum() >= 32, 'undersupported construction component')
        yy, xx, aa = y[take], x[take], a[take]
        coefs, scales, fits = [], [], []
        for j in range(16):
            lo, hi = bounds(xx, aa, j, chart)
            beta, logsd, diagnostic = fitting.fit(yy[:, :j], yy[:, j], lo, hi, method, config, charge)
            coefs.append(beta)
            scales.append(logsd)
            fits.append(diagnostic)
            if progress is not None:
                progress(region_index, j, diagnostic)
        regions.append(dict(coefficients=np.concatenate(coefs), logsd=np.array(scales),
                            logweight=np.array(math.log(take.sum()/len(x)))))
        diagnostics.append(dict(count=int(take.sum()), conditionals=fits))
    return Message(chart, edges, frame, regions, diagnostics)


def transport_views(x):
    old.require(np.all(abs(x[:, 15]) < 1), 'directional log chart singular at hysteresis saturation; use affine transport')
    return dict(kappa=np.exp(-x[:, 5]), OCV_projective=np.tanh(8*(x[:, 11]-.5)),
                pole_Cayley=(np.exp(-x[:, :3])-PIVOTS)/(np.exp(-x[:, :3])+PIVOTS),
                hysteresis_plus_log_distance=np.log1p(-x[:, 15]),
                hysteresis_minus_log_distance=np.log1p(x[:, 15]),
                derived_Hh=x[:, 10]*x[:, 15])


def rc_operator(tau, current, dt):
    exposure = dt/tau
    return np.array([[math.exp(-exposure), -current*math.expm1(-exposure)], [0., 1.]])


def hysteresis_operator(gamma, sign, throughput):
    exposure = gamma*throughput
    return np.array([[math.exp(-exposure), -sign*math.expm1(-exposure)], [0., 1.]])
