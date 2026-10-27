"""Fabricated reference algebra. No candidate/source/model imports or files."""
import math

N = 16


class AD:
    __slots__ = ('v', 'g', 'h')

    def __init__(self, value, gradient=None, hessian=None):
        self.v = float(value)
        self.g = [0.0] * N if gradient is None else gradient
        self.h = [0.0] * (N * N) if hessian is None else hessian

    @staticmethod
    def variable(value, index):
        g = [0.0] * N
        g[index] = 1.0
        return AD(value, g)

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
        g = [self.g[i] * b.v + self.v * b.g[i] for i in range(N)]
        h = [self.h[i * N + j] * b.v + self.v * b.h[i * N + j]
             + self.g[i] * b.g[j] + self.g[j] * b.g[i]
             for i in range(N) for j in range(N)]
        return AD(self.v * b.v, g, h)

    __rmul__ = __mul__

    def unary(self, value, first, second):
        return AD(value, [first * a for a in self.g],
                  [first * self.h[i * N + j] + second * self.g[i] * self.g[j]
                   for i in range(N) for j in range(N)])

    def reciprocal(self):
        return self.unary(1.0 / self.v, -1.0 / (self.v * self.v),
                          2.0 / (self.v * self.v * self.v))

    def __truediv__(self, other):
        return self * (other.reciprocal() if isinstance(other, AD) else 1.0 / other)

    def __rtruediv__(self, other):
        return self.reciprocal() * other

    def exp(self):
        value = math.exp(self.v)
        return self.unary(value, value, value)

    def log(self):
        return self.unary(math.log(self.v), 1.0 / self.v, -1.0 / (self.v * self.v))

    def tanh(self):
        value = math.tanh(self.v)
        slope = 1.0 - value * value
        return self.unary(value, slope, -2.0 * value * slope)


def physical_ad(point, samples):
    x = [AD.variable(v, i) for i, v in enumerate(point)]
    tau = [x[i].exp() for i in range(3)]
    gamma = [x[i].exp() for i in (3, 4)]
    capacity = x[5].exp()
    z, v, h = x[11], x[12:15], x[15]
    values = []
    for dt, current, _ in samples:
        z = z - (current * dt / 3600.0) / capacity
        v = [(1.0 - (-dt / tau[i]).exp()) * x[7 + i] * current
             + (-dt / tau[i]).exp() * v[i] for i in range(3)]
        if dt != 0.0 and current != 0.0:
            sign = 1.0 if current > 0 else -1.0
            e = (-gamma[0 if current > 0 else 1] * (abs(current) * dt / 3600.0)).exp()
            h = e * h + (1.0 - e) * sign
        voltage = 3.0 + 1.15 * z + 0.08 * (8.0 * (z - 0.5)).tanh()
        voltage = voltage - current * x[6] - sum(v) - x[10] * h
        values.append((voltage, z, v, h))
    return values


def physical_scalar(point, samples):
    tau = [math.exp(point[i]) for i in range(3)]
    gamma = [math.exp(point[i]) for i in (3, 4)]
    capacity = math.exp(point[5])
    z, v, h = point[11], list(point[12:15]), point[15]
    for dt, current, _ in samples:
        z -= current * dt / (3600.0 * capacity)
        for i in range(3):
            e = math.exp(-dt / tau[i])
            v[i] = e * v[i] + (1.0 - e) * point[7 + i] * current
        if dt != 0.0 and current != 0.0:
            e = math.exp(-gamma[0 if current > 0 else 1] * abs(current) * dt / 3600.0)
            h = e * h + (1.0 - e) * (1.0 if current > 0 else -1.0)
        voltage = (3.0 + 1.15 * z + 0.08 * math.tanh(8.0 * (z - 0.5))
                   - current * point[6] - sum(v) - point[10] * h)
    return voltage


def polynomial(point, origin, sd, pairs, rows, kind):
    x = [AD.variable(v, i) for i, v in enumerate(point)]
    delta = [(x[i] - origin[i]) / sd[i] for i in range(N)]
    features = delta + [delta[a] * delta[b] if kind == 2 else AD(0.0)
                        for a, b in pairs] + [AD(1.0)]
    cost, gn = AD(0.0), [0.0] * (N * N)
    for row in rows:
        residual = sum((coef * feature for coef, feature in zip(row, features)), AD(0.0))
        cost = cost + 0.5 * residual * residual
        for i in range(N):
            for j in range(N):
                gn[i * N + j] += residual.g[i] * residual.g[j]
    return cost, gn


def public_prior(point, mean, sd):
    x = [AD.variable(v, i) for i, v in enumerate(point)]
    kernel_sd = list(sd)
    kernel_sd[5] = 0.20951093757861336
    component_means = (-3.0907210901048416, -2.536100343415231)
    normal = sum(math.log(s) for s in kernel_sd) + 8 * math.log(2 * math.pi)
    log_density = []
    for q_mean in component_means:
        center = list(mean)
        center[5] = q_mean
        q = sum(((x[i] - center[i]) / kernel_sd[i]) *
                ((x[i] - center[i]) / kernel_sd[i]) for i in range(N))
        log_density.append(-0.5 * q - normal - math.log(2.0))
    shift = max(y.v for y in log_density)
    cost = -(((log_density[0] - shift).exp() +
              (log_density[1] - shift).exp()).log() + shift)
    return cost, [1.0 / (s * s) for s in kernel_sd]
