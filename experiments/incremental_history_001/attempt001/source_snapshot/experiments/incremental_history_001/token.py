"""Desktop closed-family reference. No battery model or certified arithmetic.

Immutable prior-free operators; normalized conditionals can be degenerate.
See derivation.md for the composition proof and ownership assumptions.
"""
from dataclasses import dataclass
import hashlib
import json
import math
import numpy as np


class ContractError(ValueError):
    pass


def _integer(x, name):
    if type(x) is not int or x < 0 or x > 2**64-1:
        raise ContractError(name + ' must be uint64')
    return x


def _array(x, shape):
    a = np.asarray(x, dtype=np.float64)
    if a.shape != shape or not np.all(np.isfinite(a)):
        raise ContractError('nonfinite value or invalid shape')
    # Immutable bytes backing: callers cannot re-enable writes on the view.
    return np.frombuffer(a.tobytes(), dtype=np.float64).reshape(shape)


def _psd(x, d, positive=False):
    a = _array(x, (d, d))
    tol = 64*np.finfo(float).eps*max(1., float(np.linalg.norm(a, ord=2)))
    if np.max(np.abs(a-a.T), initial=0.) > tol:
        raise ContractError('asymmetric matrix')
    a = (a+a.T)*.5
    ev = np.linalg.eigvalsh(a)
    if (positive and ev[0] <= 0) or ev[0] < -tol:
        raise ContractError('invalid covariance/information matrix')
    return _array(a, (d, d))


@dataclass(frozen=True)
class Context:
    source: str
    model: str
    noise: str
    calibration: str
    dimension: int
    tick_hz: int

    def __post_init__(self):
        if not all(type(s) is str and s for s in
                   (self.source, self.model, self.noise, self.calibration)):
            raise ContractError('missing immutable contract identity')
        if type(self.dimension) is not int or self.dimension < 1:
            raise ContractError('invalid dimension')
        if not _integer(self.tick_hz, 'tick frequency'):
            raise ContractError('zero tick frequency')


@dataclass(frozen=True)
class Boundary:
    sequence: int
    ticks: int

    def __post_init__(self):
        _integer(self.sequence, 'sequence')
        _integer(self.ticks, 'elapsed ticks')


@dataclass(frozen=True, eq=False)
class View:
    mean: np.ndarray
    covariance: np.ndarray
    log_evidence: float
    boundary: Boundary
    records: int
    uncertainty_status: str = 'conditional_on_declared_Gaussian_model_not_validated_coverage'
    arithmetic_bound: object = None


def _tilt(mean, covariance, J, h, c):
    d = len(mean)
    mat = np.eye(d)+covariance@J
    sign, ld = np.linalg.slogdet(mat)
    if sign <= 0 or not np.isfinite(ld):
        raise ContractError('unresolved Gaussian tilt determinant')
    B = np.linalg.solve(mat, np.eye(d))
    S = _psd(np.linalg.solve(mat, covariance), d)
    D = _psd(J-J@S@J, d)
    g = h-J@S@h
    k = c+.5*ld-.5*h@S@h
    m = B@mean+S@h
    log_z = -.5*mean@D@mean+g@mean-k
    return m, S, float(log_z), B, D, g, float(k)


@dataclass(frozen=True, eq=False)
class Token:
    context: Context
    entry: Boundary
    exit: Boundary
    signed_Ah: float
    throughput_Ah: float
    J: np.ndarray
    h: np.ndarray
    c: float
    A: np.ndarray
    b: np.ndarray
    Q: np.ndarray
    # Explicit unresolved ledger; no finite arithmetic bound is claimed.
    representation_defect_real_arithmetic: float = 0.
    arithmetic_bound: object = None
    physical_model_bound: object = None

    def __post_init__(self):
        d = self.context.dimension
        if self.exit.sequence < self.entry.sequence or self.exit.ticks < self.entry.ticks:
            raise ContractError('reversed interval')
        if not all(np.isfinite(v) for v in (self.signed_Ah, self.throughput_Ah, self.c)):
            raise ContractError('nonfinite scalar')
        if self.throughput_Ah < abs(self.signed_Ah)-64*np.finfo(float).eps*max(1., self.throughput_Ah):
            raise ContractError('invalid exposure')
        for name in ('J', 'Q'):
            object.__setattr__(self, name, _psd(getattr(self, name), d))
        for name, shape in [('A', (d, d)), ('b', (d,)), ('h', (d,))]:
            object.__setattr__(self, name, _array(getattr(self, name), shape))
        if self.entry.sequence == self.exit.sequence:
            if (self.entry != self.exit or self.c != 0 or self.signed_Ah != 0 or
                self.throughput_Ah != 0 or np.any(self.J) or np.any(self.h) or
                np.any(self.b) or np.any(self.Q) or not np.array_equal(self.A, np.eye(d))):
                raise ContractError('empty interval must be identity')
        if (self.representation_defect_real_arithmetic != 0 or self.arithmetic_bound is not None
                or self.physical_model_bound is not None):
            raise ContractError('unsupported error certificate')

    @property
    def records(self):
        return self.exit.sequence-self.entry.sequence

    @property
    def duration_s(self):
        return (self.exit.ticks-self.entry.ticks)/self.context.tick_hz

    @property
    def numeric_bytes(self):
        return sum(a.nbytes for a in (self.J, self.h, self.A, self.b, self.Q))+8

    def fingerprint(self):
        meta = dict(schema='prior_free_gaussian_operator_v1', context=vars(self.context),
                    entry=vars(self.entry), exit=vars(self.exit),
                    signed_Ah=self.signed_Ah, throughput_Ah=self.throughput_Ah, c=self.c)
        dig = hashlib.sha256(json.dumps(meta, sort_keys=True).encode())
        for a in (self.J, self.h, self.A, self.b, self.Q):
            dig.update(a.tobytes())
        return dig.hexdigest()

    def then(self, other):
        if type(other) is not Token or self.context != other.context:
            raise ContractError('not a compatible prior-free token')
        if self.exit != other.entry:
            raise ContractError('overlap, gap or boundary mismatch')
        if not self.records:
            return other
        if not other.records:
            return self
        mz, S, _, B, D, g, k = _tilt(self.b, self.Q, other.J, other.h, other.c)
        return Token(self.context, self.entry, other.exit,
                     self.signed_Ah+other.signed_Ah, self.throughput_Ah+other.throughput_Ah,
                     self.J+self.A.T@D@self.A,
                     self.h+self.A.T@(g-D@self.b),
                     self.c+k+.5*self.b@D@self.b-g@self.b,
                     other.A@B@self.A, other.A@mz+other.b,
                     other.A@S@other.A.T+other.Q)

    def query(self, prior_mean, prior_covariance):
        d = self.context.dimension
        m = _array(prior_mean, (d,))
        P = _psd(prior_covariance, d)
        mt, Pt, log_z, *_ = _tilt(m, P, self.J, self.h, self.c)
        out_mean = _array(self.A@mt+self.b, (d,))
        out_cov = _psd(self.A@Pt@self.A.T+self.Q, d)
        if not math.isfinite(log_z):
            raise ContractError('nonfinite query evidence')
        return View(out_mean, out_cov, log_z, self.exit, self.records)


def identity(context, boundary):
    d = context.dimension
    return Token(context, boundary, boundary, 0., 0., np.zeros((d, d)),
                 np.zeros(d), 0., np.eye(d), np.zeros(d), np.zeros((d, d)))


def observation(context, entry, exit_ticks, current_A, F, offset, W, H, y, R):
    """One admitted transition followed by one vector observation.

    The caller supplies model matrices and independent noise assumptions;
    current/ticks record exposure, they do not calibrate a battery model.
    """
    d = context.dimension
    end = Boundary(entry.sequence+1, exit_ticks)
    if end.ticks < entry.ticks or not np.isfinite(current_A):
        raise ContractError('invalid time/current')
    F = _array(F, (d, d)); offset = _array(offset, (d,)); W = _psd(W, d)
    y = np.asarray(y, dtype=float)
    if y.ndim != 1 or not len(y):
        raise ContractError('invalid observation')
    m = len(y)
    y = _array(y, (m,)); H = _array(H, (m, d)); R = _psd(R, m, positive=True)
    S = _psd(H@W@H.T+R, m, positive=True)
    E = H@F; r = y-H@offset
    K = np.linalg.solve(S, H@W).T
    D = np.eye(d)-K@H
    sign, ld = np.linalg.slogdet(S)
    if sign <= 0:
        raise ContractError('unresolved observation determinant')
    charge = float(current_A)*(end.ticks-entry.ticks)/context.tick_hz/3600
    return Token(context, entry, end, charge, abs(charge), E.T@np.linalg.solve(S, E),
                 E.T@np.linalg.solve(S, r),
                 float(.5*(r@np.linalg.solve(S, r)+ld+m*math.log(2*math.pi))),
                 D@F, offset+K@r, D@W@D.T+K@R@K.T)


class RollingReference:
    """Bounded desktop queue with atomic retirement; external serialization.

    This is a reference lifecycle, not a hook in the existing C optimizer.
    """
    def __init__(self, context, boundary, capacity=4):
        if type(capacity) is not int or capacity < 1:
            raise ContractError('invalid queue capacity')
        self._history = identity(context, boundary)
        self._pending = ()
        self._capacity = capacity

    @property
    def accepted_boundary(self):
        return self._pending[-1].exit if self._pending else self._history.exit

    @property
    def retired_boundary(self):
        return self._history.exit

    def fingerprint(self):
        return self._history.fingerprint(), tuple(t.fingerprint() for t in self._pending)

    def offer(self, row):
        if type(row) is not Token or row.records != 1:
            raise ContractError('only a single new observation token may enter')
        if row.context != self._history.context or row.entry != self.accepted_boundary:
            raise ContractError('source/contract/order/boundary mismatch')
        if len(self._pending) == self._capacity:
            raise ContractError('queue full; caller retains the rejected row')
        self._pending = self._pending+(row,)

    def retire(self, count):
        if type(count) is not int or not 0 <= count <= len(self._pending):
            raise ContractError('invalid retirement count')
        updated = self._history
        for row in self._pending[:count]:
            updated = updated.then(row)
        self._history, self._pending = updated, self._pending[count:]

    def query(self, prior_mean, prior_covariance):
        aggregate = self._history
        for row in self._pending:
            aggregate = aggregate.then(row)
        return aggregate.query(prior_mean, prior_covariance)
