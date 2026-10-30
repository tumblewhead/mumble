"""Minimal health model: immutable desktop kernels, not a posterior solver.

Local derivatives use (old fast[5], static[9], new health[2]). Bounded
normalization uses scaled Gaussian integrals, with checked quadrature error
and an analytic omitted-tail bound; it does not clip states or samples.
"""
from dataclasses import dataclass
from functools import lru_cache
import math
import numpy as np

STATIC = (0, 1, 2, 3, 4, 7, 8, 9, 10)
FAST = (11, 12, 13, 14, 15)
HEALTH = (5, 6)
MEAN = np.array([-3.0484125313829042, -.7458274383888583, 1.90333124488516,
    5.0106352940962555, 5.703782474656201, -2.8134107167600364,
    .1, .1, .1, .1, .024, .68, 0., 0., 0., 0.])
SD = np.array([.664699061636066, .664699061636066, .8647934172782233,
    1.5821241788613198, 1.5821241788613198, .347557011337284,
    .2886751345948129, .2886751345948129, .2886751345948129,
    .2886751345948129, .02886751345948129, .21650635094610968,
    .046188021535170064, .046188021535170064, .046188021535170064,
    .5773502691896258])
LOW = np.array([-4.199705077879927, -1.8971199848858813, .40546510810816438,
    1.6094379124341003, 1.6094379124341003, -3.5065578973199818,
    0., 0., 0., 0., 0., .2, -.08, -.08, -.08, -1.])
HIGH = np.array([-1.8971199848858813, .40546510810816438, 3.4011973816621555,
    7.0900768357760917, 7.0900768357760917, -2.3025850929940455,
    1., 1., 1., 1., .1, .95, .08, .08, .08, 1.])
for _a in (MEAN, SD, LOW, HIGH):
    _a.flags.writeable = False
SIGMA = .001
ACTIVITY = dict(physical_steps=0, transition_queries=0, normalizer_nodes=0)


class ModelError(ValueError):
    def __init__(self, status, detail):
        self.status, self.detail = status, detail
        super().__init__(status + ': ' + detail)


def require(ok, status, detail):
    if not ok:
        raise ModelError(status, detail)


def vector(values, n, name):
    a = np.asarray(values, dtype=float)
    require(a.shape == (n,) and np.isfinite(a).all(), 'invalid_input', name)
    return a


@dataclass(frozen=True)
class Profile:
    # All eight rates must be supplied. Engineering assumptions, not calibration.
    rates: tuple

    def __post_init__(self):
        a = vector(self.rates, 8, 'rates')
        require(np.all(a[:2] <= 0) and np.all(a[2:4] >= 0)
                and np.all(a[4:] >= 0), 'invalid_input', 'rate signs')
        object.__setattr__(self, 'rates', tuple(a))

    def increments(self, dt, current):
        require(math.isfinite(dt) and 0 <= dt <= 1 and math.isfinite(current)
                and abs(current) <= .25, 'invalid_input', 'exposure domain')
        d, a = dt / 86400., abs(current) * dt / 3600.
        require(dt == 0 or d > 0, 'transition_numeric_unresolved', 'calendar exposure underflow')
        require(dt == 0 or current == 0 or a > 0,
                'transition_numeric_unresolved', 'throughput exposure underflow')
        r = self.rates
        with np.errstate(over='ignore', under='ignore', invalid='ignore'):
            means = (r[0]*d+r[1]*a, r[2]*d+r[3]*a)
            variances = (r[4]**2*d+r[5]**2*a, r[6]**2*d+r[7]**2*a)
        require(np.isfinite(means + variances).all(),
                'transition_numeric_unresolved', 'exposure overflow')
        for j in range(2):
            active = (d > 0 and r[4+2*j] > 0) or (a > 0 and r[5+2*j] > 0)
            require(not active or variances[j] > 0,
                    'transition_numeric_unresolved', 'positive diffusion underflow; not a Dirac')
        return means, variances


@lru_cache(maxsize=8)
def gauss(order):
    x, w = np.polynomial.legendre.leggauss(order)
    x.flags.writeable = w.flags.writeable = False
    return x, w


@dataclass(frozen=True)
class Normalizer:
    pivot: float
    sd: float
    a: float
    log_integral_t: float
    mean_t: float
    second_t: float
    variance_t: float
    mean_exp: float
    variance_exp: float
    quadrature_relative_change: float
    tail_relative_bound: float

    @property
    def log_Z(self):
        return -.5*self.a*self.a - .5*math.log(2*math.pi) + self.log_integral_t

    @property
    def mean(self):
        return self.pivot + self.sd*self.mean_t

    @property
    def variance(self):
        return self.sd*self.sd*self.variance_t


@lru_cache(maxsize=512)
def normalizer(mu, variance, lower, upper):
    require(all(map(math.isfinite, (mu, variance, lower, upper)))
            and variance > 0 and lower < upper,
            'invalid_input', 'normalizer arguments')
    s = math.sqrt(variance)
    c = min(upper, max(lower, mu))
    a = (c-mu)/s
    require(math.isfinite(a) and abs(a) <= 1e4,
            'transition_numeric_unresolved', 'standardized tail exceeds qualified range')
    # Truncate the integration domain only, at exp(-60) relative to its mode.
    reach = 120. / (math.hypot(a, math.sqrt(120.)) + abs(a))
    raw_lo, raw_hi = (lower-c)/s, (upper-c)/s
    lo, hi = max(raw_lo, -reach), min(raw_hi, reach)
    require(math.isfinite(lo) and math.isfinite(hi) and hi > lo,
            'transition_numeric_unresolved', 'unrepresentable integration interval')
    previous = None
    for order in (32, 64, 128):
        x, w = gauss(order)
        t = (lo+hi)/2 + (hi-lo)/2*x
        mass = w*(hi-lo)/2*np.exp(-a*t-.5*t*t)
        integral = float(mass.sum())
        ACTIVITY['normalizer_nodes'] += order
        require(integral > 0 and math.isfinite(integral),
                'transition_numeric_unresolved', 'integral underflow')
        p = mass/integral
        mt, t2 = float(p@t), float(p@(t*t))
        vt = float(p@((t-mt)**2))
        # Q transform in the bounded health chart; expm1 retains tiny variance.
        center_exp = math.exp(c)
        delta = np.expm1(s*t)
        md = float(p@delta)
        em, ev = center_exp*(1+md), center_exp**2*float(p@((delta-md)**2))
        current = np.array([integral, mt, t2, vt, em, ev])
        if previous is not None:
            change = float(np.max(abs(current-previous)/np.maximum(abs(current), 1.)))
            change = max(change, abs(integral-previous[0])/integral)
            if change <= 2e-12:
                tail = 0.
                if raw_lo < lo:
                    tail += math.exp(-60.)/abs(a+lo)
                if raw_hi > hi:
                    tail += math.exp(-60.)/abs(a+hi)
                require(tail/integral <= 1e-12, 'transition_numeric_unresolved', 'tail allowance')
                return Normalizer(c, s, a, math.log(integral), mt, t2, vt,
                                  em, ev, change, tail/integral)
        previous = current
    raise ModelError('transition_numeric_unresolved', 'quadrature did not converge')


def transition(previous, following, mean_increment, variance, lower, upper):
    """Return NLL, dNLL/dprevious, dNLL/dfollowing, dNLL/dlogvariance.

    Zero variance is an exact constraint; callers eliminate that variable.
    """
    ACTIVITY['transition_queries'] += 1
    require(all(map(math.isfinite, (previous, following, mean_increment, variance,
                                   lower, upper))) and variance >= 0 and lower < upper,
            'invalid_input', 'transition arguments')
    require(lower <= previous <= upper and lower <= following <= upper,
            'model_domain_exceeded', 'health support')
    mu = previous + mean_increment
    if variance == 0:
        require(lower <= mu <= upper, 'model_domain_exceeded', 'deterministic health')
        require(following == mu, 'dirac_constraint_violated', 'redundant health variable')
        return (0., 0., 0., 0.)
    n = normalizer(mu, variance, lower, upper)
    t = (following-n.pivot)/n.sd
    nll = n.a*t + .5*t*t + math.log(n.sd) + n.log_integral_t
    gp = ((n.pivot-following)+n.sd*n.mean_t)/variance
    gy = (following-mu)/variance
    gv = .5*(2*n.a*(n.mean_t-t)+n.second_t-t*t)
    require(all(map(math.isfinite, (nll, gp, gy, gv))),
            'transition_numeric_unresolved', 'density or derivative overflow')
    return nll, gp, gy, gv


@dataclass(frozen=True)
class Record:
    source_id: str
    index: int
    dt: float
    current: float
    voltage: float | None
    measurement_valid: bool = True
    input_known: bool = True
    temperature_C: float = 25.


@dataclass(frozen=True)
class State:
    fast: tuple
    health: tuple
    static: tuple
    source_id: str
    next_index: int = 0
    elapsed: float = 0.
    terminal_charge_Ah: float = 0.
    availability_charge_Ah: float = 0.
    observation_count: int = 0
    flags: tuple = ()


def initial_state(x, source_id):
    x = vector(x, 16, 'initial x')
    require(np.all(x >= LOW) and np.all(x <= HIGH), 'model_domain_exceeded', 'initial support')
    require(isinstance(source_id, str) and bool(source_id), 'invalid_input', 'source_id')
    return State(tuple(x[list(FAST)]), tuple(x[list(HEALTH)]),
                 tuple(x[list(STATIC)]), source_id)


def validate_record(state, r):
    require(r.source_id == state.source_id and type(r.index) is int
            and r.index == state.next_index, 'source_order_error', 'source/cursor mismatch')
    require(r.input_known, 'recovery_required', 'unknown input gap')
    require(math.isfinite(r.dt) and 0 <= r.dt <= 1 and math.isfinite(r.current)
            and abs(r.current) <= .25 and math.isfinite(r.temperature_C),
            'invalid_record', 'interval/current/temperature domain')
    require(type(r.measurement_valid) is bool and (not r.measurement_valid or
            (r.voltage is not None and math.isfinite(r.voltage))),
            'invalid_record', 'voltage validity')


def advance(state, record, new_health):
    """Pure physical step; health-transition density is owned by path.evaluate.

    Returns committed-value candidate, predicted voltage, state Jacobian and
    voltage gradient. Nothing is mutated on either success or failure.
    """
    validate_record(state, record)
    f = vector(state.fast, 5, 'fast')
    h = vector(new_health, 2, 'new health')
    p = vector(state.static, 9, 'static')
    old_h = vector(state.health, 2, 'old health')
    require(np.all(h >= LOW[list(HEALTH)]) and np.all(h <= HIGH[list(HEALTH)])
            and np.all(old_h >= LOW[list(HEALTH)]) and np.all(old_h <= HIGH[list(HEALTH)])
            and np.all(p >= LOW[list(STATIC)]) and np.all(p <= HIGH[list(STATIC)])
            and 0 <= f[0] <= 1 and np.all(abs(f[1:4]) <= .25) and abs(f[4]) <= 1,
            'model_domain_exceeded', 'physical entering support')
    dt, i = record.dt, record.current
    charge, q = i*dt/3600., math.exp(h[0])
    out = f.copy()
    jac = np.zeros((5, 16))
    out[0] -= charge/q
    jac[0, 0], jac[0, 14] = 1., charge/q
    for j in range(3):
        t = dt/math.exp(p[j])
        e, one_minus = math.exp(-t), -math.expm1(-t)
        out[1+j] = e*f[1+j] + one_minus*p[5+j]*i
        jac[1+j, 1+j] = e
        jac[1+j, 5+j] = e*t*(f[1+j]-p[5+j]*i)
        jac[1+j, 10+j] = one_minus*i
    jac[4, 4] = 1.
    if i != 0 and dt != 0:
        sign, k = (1., 3) if i > 0 else (-1., 4)
        t = math.exp(p[k])*abs(i)*dt/3600.
        e = math.exp(-t)
        out[4] = e*f[4] - math.expm1(-t)*sign
        jac[4, 4], jac[4, 5+k] = e, -t*e*(f[4]-sign)
    require(0 <= out[0] <= 1 and np.all(abs(out[1:4]) <= .25) and abs(out[4]) <= 1,
            'model_domain_exceeded', 'propagated physical support')
    tanh = math.tanh(8*(out[0]-.5))
    mu = 3+1.15*out[0]+.08*tanh-i*h[1]-sum(out[1:4])-p[8]*out[4]
    grad = (1.15+.64*(1-tanh*tanh))*jac[0]-jac[1:4].sum(axis=0)-p[8]*jac[4]
    grad[13] -= out[4]
    grad[15] -= i
    flags = set(state.flags)
    if record.temperature_C != 25:
        flags.add('outside_validated_temperature_scope')
    if record.measurement_valid and abs(mu-record.voltage) > 6*SIGMA:
        flags.add('model_mismatch_suspected')
    availability = f[0]*(q-math.exp(old_h[0]))
    result = State(tuple(out), tuple(h), tuple(p), state.source_id,
        state.next_index+1, state.elapsed+dt, state.terminal_charge_Ah+charge,
        state.availability_charge_Ah+availability,
        state.observation_count+int(record.measurement_valid), tuple(sorted(flags)))
    ACTIVITY['physical_steps'] += 1
    return result, float(mu), jac, grad


class Stream:
    """Atomic physical path cursor, not an estimator or posterior checkpoint."""
    def __init__(self, state):
        self.state = state

    def deliver(self, record, new_health):
        result = advance(self.state, record, new_health)
        self.state = result[0]
        return result
