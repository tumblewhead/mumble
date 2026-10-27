"""Independent fabricated algebra for the rolling integration qualification.

This module imports no candidate code and opens no evidence.  Its arrays are
host-only reference work, not candidate memory.  The physical recurrence is
written in voltage-state form; the candidate uses carried f/a basis functions.
No function is called until the combined qualification source is frozen.
"""
import math

N = 16
PAIRS = ((0, 0), (0, 7), (0, 12), (1, 1), (1, 8), (1, 13),
         (2, 2), (2, 9), (2, 14), (3, 3), (3, 4), (4, 4),
         (3, 10), (3, 15), (4, 10), (4, 15), (10, 15),
         (11, 11), (5, 11), (5, 5))
PUBLIC_MEAN = (-3.0484125313829042, -.7458274383888583,
               1.90333124488516, 5.0106352940962555,
               5.703782474656201, -2.8134107167600364,
               .1, .1, .1, .1, .024, .68, 0., 0., 0., 0.)
PUBLIC_SD = (.664699061636066, .664699061636066, .8647934172782233,
             1.5821241788613198, 1.5821241788613198, .347557011337284,
             .2886751345948129, .2886751345948129, .2886751345948129,
             .2886751345948129, .02886751345948129, .21650635094610968,
             .046188021535170064, .046188021535170064,
             .046188021535170064, .5773502691896258)
ACTIVITY = {"AD_trajectories": 0, "scalar_trajectories": 0,
            "AD_steps": 0, "scalar_steps": 0, "prior_algebra": 0,
            "polynomial_algebra": 0, "boundary_polynomial_algebra": 0}


class AD:
    """Full original-chart first and second derivatives, without sparsity."""
    __slots__ = ("v", "g", "h")

    def __init__(self, value, gradient=None, hessian=None):
        self.v = float(value)
        self.g = [0.] * N if gradient is None else gradient
        self.h = [0.] * (N * N) if hessian is None else hessian

    @staticmethod
    def variable(value, index):
        gradient = [0.] * N
        gradient[index] = 1.
        return AD(value, gradient)

    def __add__(self, other):
        b = other if isinstance(other, AD) else AD(other)
        return AD(self.v + b.v, [a + c for a, c in zip(self.g, b.g)],
                  [a + c for a, c in zip(self.h, b.h)])

    __radd__ = __add__

    def __neg__(self):
        return AD(-self.v, [-a for a in self.g], [-a for a in self.h])

    def __sub__(self, other):
        return self + (-other if isinstance(other, AD) else -float(other))

    def __rsub__(self, other):
        return -self + other

    def __mul__(self, other):
        b = other if isinstance(other, AD) else AD(other)
        gradient = [self.g[i] * b.v + self.v * b.g[i] for i in range(N)]
        hessian = [self.h[i * N + j] * b.v + self.v * b.h[i * N + j]
                   + self.g[i] * b.g[j] + self.g[j] * b.g[i]
                   for i in range(N) for j in range(N)]
        return AD(self.v * b.v, gradient, hessian)

    __rmul__ = __mul__

    def unary(self, value, first, second):
        return AD(value, [first * a for a in self.g],
                  [first * self.h[i * N + j] + second * self.g[i] * self.g[j]
                   for i in range(N) for j in range(N)])

    def reciprocal(self):
        return self.unary(1. / self.v, -1. / (self.v * self.v),
                          2. / (self.v * self.v * self.v))

    def __truediv__(self, other):
        return self * (other.reciprocal() if isinstance(other, AD) else 1. / other)

    def __rtruediv__(self, other):
        return self.reciprocal() * other

    def exp(self):
        value = math.exp(self.v)
        return self.unary(value, value, value)

    def log(self):
        return self.unary(math.log(self.v), 1. / self.v, -1. / (self.v * self.v))

    def tanh(self):
        value = math.tanh(self.v)
        slope = 1. - value * value
        return self.unary(value, slope, -2. * value * slope)


def variables(point):
    return [AD.variable(value, i) for i, value in enumerate(point)]


def boundary_basis(x, origin, boundary):
    """Evaluate the carried basis polynomials, not an exact earlier path.

    Jet derivatives are in raw log-rate coordinates.  They therefore use raw
    differences here, unlike the public-SD-normalized history features.
    """
    delta = [x[i] - origin[i] for i in range(5)]
    f = [boundary["f"][i] + boundary["df"][i] * delta[i]
         + .5 * boundary["ddf"][i] * delta[i] * delta[i] for i in range(3)]
    a = [boundary["a"][i] + boundary["da"][i] * delta[i]
         + .5 * boundary["dda"][i] * delta[i] * delta[i] for i in range(3)]
    rates = delta[3:5]
    polys = []
    for name in ("hb", "ha"):
        first, second = boundary["d" + name], boundary["dd" + name]
        polys.append(boundary[name] + first[0] * rates[0] + first[1] * rates[1]
                     + .5 * second[0] * rates[0] * rates[0]
                     + second[1] * rates[0] * rates[1]
                     + .5 * second[2] * rates[1] * rates[1])
    return f, a, polys[0], polys[1]


def translated_boundary_ad(point, origin, boundary):
    ACTIVITY["boundary_polynomial_algebra"] += 1
    return boundary_basis(variables(point), origin, boundary)


def initial_physical(x, origin=None, boundary=None):
    if boundary is None:
        return list(x[12:15]), x[15], 0.
    f, a, hb, ha = boundary_basis(x, origin, boundary)
    return [x[7 + i] * f[i] + x[12 + i] * a[i] for i in range(3)], \
        hb + ha * x[15], boundary["charge_Ah"]


def block_ad(point, samples, sigma, origin=None, boundary=None):
    ACTIVITY["AD_trajectories"] += 1
    x = variables(point)
    tau = [x[i].exp() for i in range(3)]
    gamma = [x[i].exp() for i in (3, 4)]
    capacity = x[5].exp()
    v, h, charge = initial_physical(x, origin, boundary)
    rows, cost = [], AD(0.)
    gram = [0.] * (N * N)
    for dt, current, observed in samples:
        ACTIVITY["AD_steps"] += 1
        charge += current * dt / 3600.
        z = x[11] - charge / capacity
        decay = [(-dt / t).exp() for t in tau]
        v = [decay[i] * v[i] + (1. - decay[i]) * x[7 + i] * current
             for i in range(3)]
        if current != 0. and dt != 0.:
            sign = 1. if current > 0. else -1.
            e = (-gamma[0 if current > 0. else 1] * (abs(current) * dt / 3600.)).exp()
            h = e * h + (1. - e) * sign
        mu = 3. + 1.15 * z + .08 * (8. * (z - .5)).tanh()
        mu = mu - current * x[6] - sum(v) - x[10] * h
        residual = (mu - observed) / sigma
        cost = cost + .5 * residual * residual
        for i in range(N):
            for j in range(N):
                gram[i * N + j] += residual.g[i] * residual.g[j]
        rows.append({"voltage": mu, "SOC": z, "v": list(v), "h": h,
                     "residual": residual, "charge_Ah": charge})
    return {"rows": rows, "cost": cost, "GN": gram, "charge_Ah": charge}


def block_scalar(point, samples, sigma, origin=None, boundary=None):
    """Independent scalar form for five-point differences of voltage/cost."""
    ACTIVITY["scalar_trajectories"] += 1
    tau = [math.exp(point[i]) for i in range(3)]
    gamma = [math.exp(point[i]) for i in (3, 4)]
    capacity = math.exp(point[5])
    v, h, charge = initial_physical(point, origin, boundary)
    rows, terms = [], []
    for dt, current, observed in samples:
        ACTIVITY["scalar_steps"] += 1
        charge += current * dt / 3600.
        z = point[11] - charge / capacity
        for i in range(3):
            e = math.exp(-dt / tau[i])
            v[i] = e * v[i] + (1. - e) * point[7 + i] * current
        if current != 0. and dt != 0.:
            e = math.exp(-gamma[0 if current > 0. else 1] * abs(current) * dt / 3600.)
            h = e * h + (1. - e) * (1. if current > 0. else -1.)
        mu = (3. + 1.15 * z + .08 * math.tanh(8. * (z - .5))
              - current * point[6] - sum(v) - point[10] * h)
        rows.append(mu)
        terms.append(.5 * ((mu - observed) / sigma) ** 2)
    return {"voltage": rows, "cost": math.fsum(terms)}


def expected_merge_row(voltage, observed, sigma, sd=PUBLIC_SD):
    quadratics = [(0.5 if i == j else 1.) * voltage.h[i * N + j]
                  * sd[i] * sd[j] / sigma for i, j in PAIRS]
    return quadratics + [voltage.g[i] * sd[i] / sigma for i in range(N)] \
        + [(voltage.v - observed) / sigma]


def factor_ad(point, origin, upper, sd=PUBLIC_SD):
    ACTIVITY["polynomial_algebra"] += 1
    x = variables(point)
    delta = [(x[i] - origin[i]) / sd[i] for i in range(N)]
    features = [delta[i] * delta[j] for i, j in PAIRS] + delta + [AD(1.)]
    cost, gram, cursor = AD(0.), [0.] * (N * N), 0
    for row in range(37):
        residual = AD(0.)
        for column in range(row, 37):
            residual = residual + upper[cursor] * features[column]
            cursor += 1
        cost = cost + .5 * residual * residual
        for i in range(N):
            for j in range(N):
                gram[i * N + j] += residual.g[i] * residual.g[j]
    return cost, gram


def public_prior_ad(point):
    ACTIVITY["prior_algebra"] += 1
    x = variables(point)
    sd = list(PUBLIC_SD)
    sd[5] = .20951093757861336
    qmeans = (-3.0907210901048416, -2.536100343415231)
    normal = sum(math.log(s) for s in sd) + 8. * math.log(2. * math.pi)
    log_density = []
    for qmean in qmeans:
        center = list(PUBLIC_MEAN)
        center[5] = qmean
        scaled = [(x[i] - center[i]) / sd[i] for i in range(N)]
        quadratic = sum(value * value for value in scaled)
        log_density.append(-.5 * quadratic - normal - math.log(2.))
    shift = max(y.v for y in log_density)
    cost = -(((log_density[0] - shift).exp() +
              (log_density[1] - shift).exp()).log() + shift)
    return cost, [1. / (s * s) for s in sd]
