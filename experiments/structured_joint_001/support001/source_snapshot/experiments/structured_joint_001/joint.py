"""Square-root elimination controls. No source replay, prior or state model implicit.

Rows denote residuals A @ [retired, retained] + b, already whitened.
Inputs must include each owned likelihood/prior factor exactly once. Gaussian
elimination is valid only for an unrestricted retired domain; bounded scalar
elimination explicitly supplies its mass. This is a desktop algebra primitive.
"""
from dataclasses import dataclass
import math
import numpy as np


def upper(rows):
    rows = np.asarray(rows, dtype=float)
    if rows.ndim != 2 or rows.shape[1] < 1 or not np.isfinite(rows).all():
        raise ValueError('finite augmented matrix required')
    width = rows.shape[1]
    r = np.zeros((width, width))
    if len(rows):
        qr = np.linalg.qr(rows, mode='reduced')[1]
        r[:len(qr)] = qr
    return np.where(np.diag(r) < 0, -1., 1.)[:, None]*r


def normal_log_mass(lo, hi):
    """Moderate-domain normal interval mass; underflow is explicitly unresolved.

    Symmetry avoids subtracting CDFs near one. This is not directed rounding,
    an arbitrary-tail algorithm, or a certificate of probability coverage.
    """
    if math.isnan(lo) or math.isnan(hi) or not lo < hi:
        raise ValueError('nonempty ordered interval required')
    if lo >= 0:
        mass = .5*(math.erfc(lo/math.sqrt(2))-math.erfc(hi/math.sqrt(2)))
    elif hi <= 0:
        mass = .5*(math.erfc(-hi/math.sqrt(2))-math.erfc(-lo/math.sqrt(2)))
    else:
        mass = .5*(math.erf(hi/math.sqrt(2))-math.erf(lo/math.sqrt(2)))
    if not 0 < mass <= 1 or not math.isfinite(mass):
        raise ValueError('normal interval mass numerically unresolved')
    return math.log(mass)


@dataclass(frozen=True)
class Split:
    eliminated_root: np.ndarray
    cross: np.ndarray
    offset: np.ndarray
    retained_root: np.ndarray
    log_multiplier: float
    log_constant: float

    def _s(self, s):
        s = np.asarray(s, dtype=float)
        if s.shape != (self.cross.shape[1],) or not np.isfinite(s).all():
            raise ValueError('retained coordinate shape/finite')
        return s

    def conditional(self, s):
        s = self._s(s)
        mean = np.linalg.solve(self.eliminated_root, -self.cross@s-self.offset)
        inv = np.linalg.solve(self.eliminated_root, np.eye(len(mean)))
        return mean, inv@inv.T

    def log_joint(self, x, s):
        s = self._s(s); x = np.asarray(x, dtype=float)
        if x.shape != self.offset.shape or not np.isfinite(x).all():
            raise ValueError('eliminated coordinate shape/finite')
        a = self.eliminated_root@x+self.cross@s+self.offset
        b = self.retained_root@np.r_[s, 1.]
        return float(-.5*(a@a+b@b)-self.log_constant)

    def log_marginal_unbounded(self, s):
        s = self._s(s); residual = self.retained_root@np.r_[s, 1.]
        return float(-.5*(residual@residual)-self.log_constant+self.log_multiplier)

    def log_marginal_scalar_interval(self, s, lo, hi):
        if len(self.offset) != 1:
            raise ValueError('only one eliminated coordinate is implemented')
        mean, cov = self.conditional(s); sd = math.sqrt(cov[0, 0])
        mass = normal_log_mass((lo-mean[0])/sd, (hi-mean[0])/sd)
        return self.log_marginal_unbounded(s)+mass


def split(rows, retired, log_constant=0.):
    rows = np.asarray(rows, dtype=float)
    r = upper(rows); p = r.shape[0]-1
    if type(retired) is not int or not 0 < retired <= p or not math.isfinite(log_constant):
        raise ValueError('invalid partition or normalization')
    # Rank diagnostics are numerical resolution checks, never a physical prior.
    # No jitter or pseudo-inverse makes a flat retired likelihood integrable.
    if np.linalg.matrix_rank(rows[:, :retired]) != retired:
        raise ValueError('retired Gaussian integral unresolved/rank deficient')
    xx = r[:retired, :retired].copy()
    shift = retired*.5*math.log(2*math.pi)-float(np.log(np.diag(xx)).sum())
    return Split(xx, r[:retired, retired:p].copy(), r[:retired, p].copy(),
                 r[retired:, retired:].copy(), shift, float(log_constant))


def packed_factor_bytes(p):
    if type(p) is not int or p < 0:
        raise ValueError('invalid dimension')
    return 8*(p+1)*(p+2)//2


def graph_from_scopes(nodes, scopes):
    graph = {n: set() for n in nodes}
    for scope in scopes:
        for n in scope:
            graph[n].update(set(scope)-{n})
    return graph


def eliminate_graph(graph, order):
    """Symbolic generic fill; zero/cancellation coincidences are not assumed."""
    g = {n: set(neighbors) for n, neighbors in graph.items()}
    fill = []; peak = 0
    for x in order:
        neighbors = sorted(g[x]); peak = max(peak, len(neighbors)+1)
        for i, a in enumerate(neighbors):
            for b in neighbors[i+1:]:
                if b not in g[a]:
                    g[a].add(b); g[b].add(a); fill.append([a, b])
            g[a].remove(x)
        del g[x]
    return g, fill, peak
