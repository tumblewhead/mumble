"""Finite fixed-eta battery algebra witness, not a deployable compressor.

Each block is valid at ONE conditioning argument. It cannot answer changed
rates/SOC/capacity without reconstructing from the owned observations.
"""
from dataclasses import dataclass
import math
import numpy as np


def ocv(z):
    return 3+1.15*z+.08*np.tanh(8*(z-.5))


def upper(rows):
    _, r = np.linalg.qr(rows, mode='reduced')
    # Padding allows the identity and blocks shorter than ten rows.
    out = np.zeros((10, 10)); out[:len(r)] = r
    sign = np.where(np.diag(out) < 0, -1., 1.)
    return sign[:, None]*out


@dataclass(frozen=True)
class Block:
    eta: np.ndarray
    sigma: float
    first: int
    stop: int
    S: np.ndarray
    a: np.ndarray
    f: np.ndarray
    ha: float
    hb: float
    charge: float
    charge_min: float
    charge_max: float
    elapsed: float
    source: str = 'fabricated-partition-closure-291003'

    @property
    def next_eta(self):
        eta = self.eta.copy(); eta[5] -= self.charge/math.exp(eta[6])
        return eta

    @property
    def T(self):
        out = np.eye(9)
        for i in range(3):
            out[5+i, 5+i] = self.a[i]; out[5+i, 1+i] = self.f[i]
        out[8, 8] = self.ha; out[8, 4] = self.hb
        return out

    def nll(self, alpha):
        residual = self.S@np.r_[alpha, 1.]
        return float(.5*(residual@residual)+(self.stop-self.first)*math.log(self.sigma*math.sqrt(2*math.pi)))

    def then(self, other):
        if self.source != other.source or self.stop != other.first or self.sigma != other.sigma:
            raise ValueError('source, ownership or noise mismatch')
        expected = self.next_eta
        if (not np.array_equal(expected[[0, 1, 2, 3, 4, 6]], other.eta[[0, 1, 2, 3, 4, 6]])
                or abs(expected[5]-other.eta[5]) > 64*np.finfo(float).eps*max(1., abs(expected[5]))):
            raise ValueError('incompatible conditioning argument; reconstruction required')
        m = np.eye(10); m[:9, :9] = self.T
        return Block(self.eta.copy(), self.sigma, self.first, other.stop,
                     upper(np.vstack((self.S, other.S@m))),
                     other.a*self.a, other.a*self.f+other.f,
                     other.ha*self.ha, other.ha*self.hb+other.hb,
                     self.charge+other.charge,
                     min(self.charge_min, self.charge+other.charge_min),
                     max(self.charge_max, self.charge+other.charge_max),
                     self.elapsed+other.elapsed, self.source)


def build(eta, rows, sigma=.001, first=0):
    eta = np.asarray(eta, dtype=float)
    rows = np.asarray(rows, dtype=float).reshape((-1, 3))
    if eta.shape != (7,) or not np.isfinite(eta).all() or not np.isfinite(rows).all():
        raise ValueError('nonfinite or wrong-shaped arguments')
    if not math.isfinite(sigma) or sigma <= 0 or type(first) is not int or first < 0:
        raise ValueError('invalid noise or source index')
    a = np.ones(3); f = np.zeros(3); ha, hb = 1., 0.
    q = qlo = qhi = elapsed = 0.; S = np.zeros((10, 10))
    tau = np.exp(eta[:3]); gamma = np.exp(eta[3:5]); Q = math.exp(eta[6])
    if not 0 <= eta[5] <= 1:
        raise ValueError('invalid entering SOC')
    for dt, current, observed in rows:
        if not 0 <= dt <= 1 or abs(current) > .25:
            raise ValueError('outside inherited input domain')
        q += current*dt/3600; qlo = min(qlo, q); qhi = max(qhi, q); elapsed += dt
        z = eta[5]-q/Q
        if not 0 <= z <= 1:
            raise ValueError('intermediate SOC outside support')
        e = np.exp(-dt/tau); om = -np.expm1(-dt/tau)
        a = e*a; f = e*f+om*current
        if current != 0 and dt != 0:
            exposure = abs(current)*dt/3600
            exponent = gamma[0 if current > 0 else 1]*exposure
            eh = math.exp(-exponent); oh = -math.expm1(-exponent)
            ha = eh*ha; hb = eh*hb+oh*np.sign(current)
        x = np.r_[-current, -f, -hb, -a, -ha]
        S = upper(np.vstack((S, np.r_[x, ocv(z)-observed]/sigma)))
    return Block(eta.copy(), sigma, first, first+len(rows), S, a, f, ha, hb,
                 q, qlo, qhi, elapsed)


def from_original(x):
    x = np.asarray(x, dtype=float)
    return x[[0, 1, 2, 3, 4, 11, 5]], np.r_[x[6:11], x[12:15], x[10]*x[15]]


def mobius(t, decrement):
    u = np.tanh(8*np.asarray(decrement))
    return (t-u)/(1-u*t)


def nll_bound(residual_bound, prediction_bound, sigma):
    M, eps = np.asarray(residual_bound), np.asarray(prediction_bound)
    if np.any(M < 0) or np.any(eps < 0) or sigma <= 0:
        raise ValueError('invalid error premises')
    return float(np.sum((M*eps+.5*eps*eps)/(sigma*sigma)))
