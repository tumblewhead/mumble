"""Bounded-size stationary field baseline, with real-arithmetic bounds.

Float64 arithmetic is NOT outward rounded. A zero representation bound does
not certify zero numerical error. No posterior or physical aging is supplied.
"""
import copy
import math
import numpy as np
from experiments.partitioned_battery_closure_001 import conditional as op


class Envelope:
    arithmetic_bound = None
    model_error_bound = None

    def __init__(self, center, lower, upper, first=0, entering_vmax=.08,
                 source='operator-envelope-fixture-v1', sigma=.001):
        self.center, self.lower, self.upper = [np.array(x, dtype=float, copy=True) for x in (center, lower, upper)]
        if any(x.shape != (7,) or not np.isfinite(x).all() for x in (self.center, self.lower, self.upper)):
            raise ValueError('invalid nonlinear domain')
        if np.any(self.lower > self.center) or np.any(self.center > self.upper):
            raise ValueError('center must be inside declared box')
        if not 0 <= self.lower[5] <= self.upper[5] <= 1 or not 0 < entering_vmax <= .25:
            raise ValueError('invalid supported state domain')
        if not isinstance(source, str) or not source:
            raise ValueError('invalid source identity')
        self.node = op.build(self.center, [], sigma, first)
        self.source = source; self.vmax = float(entering_vmax)
        self.throughput = np.zeros(2)
        self.exit_error = np.zeros(4)
        self.weights = np.zeros(4)
        self.E2 = 0.

    @property
    def count(self):
        return self.node.stop-self.node.first

    def soc_range(self, charge=None):
        q = self.node.charge if charge is None else charge
        z = [z-q/math.exp(lq) for z in self.lower[5:6].tolist()+self.upper[5:6].tolist()
             for lq in (self.lower[6], self.upper[6])]
        return min(z), max(z)

    def slow_carrier(self):
        return np.r_[np.exp(-self.node.elapsed/np.exp(self.upper[:3])),
                     math.exp(-float(np.exp(self.lower[3:5])@self.throughput))]

    def append(self, row, index, source=None):
        if type(index) is not int or index != self.node.stop or (source is not None and source != self.source):
            raise ValueError('source/order mismatch')
        dt, current, observed = np.asarray(row, dtype=float)
        # Build on scratch and validate through the inherited single-row kernel.
        one = op.build(self.node.next_eta, [[dt, current, observed]], self.node.sigma, index)
        newnode = self.node.then(one)
        zlo, zhi = self.soc_range(newnode.charge)
        if zlo < 0 or zhi > 1:
            raise ValueError('domain_exit: retain caller observation and prior state')
        old = self.node
        e0 = np.exp(-dt/np.exp(self.center[:3]))
        elo = np.exp(-dt/np.exp(self.lower[:3])); ehi = np.exp(-dt/np.exp(self.upper[:3]))
        de = np.maximum(abs(elo-e0), abs(ehi-e0))
        error = self.exit_error.copy()
        error[:3] = ehi*error[:3]+de*(abs(old.a)*self.vmax+abs(old.f-current))
        throughput = self.throughput.copy()
        if current != 0 and dt != 0:
            sign = 1. if current > 0 else -1.; k = 0 if current > 0 else 1
            dq = abs(current)*dt/3600
            throughput[k] += dq
            eh0 = math.exp(-math.exp(self.center[3+k])*dq)
            ehlo = math.exp(-math.exp(self.upper[3+k])*dq)
            ehhi = math.exp(-math.exp(self.lower[3+k])*dq)
            dh = max(abs(eh0-ehlo), abs(eh0-ehhi))
            error[3] = ehhi*error[3]+dh*.1*(abs(old.ha)+abs(old.hb-sign))
        center_z = newnode.next_eta[5]
        ocv_error = max(abs(op.ocv(zlo)-op.ocv(center_z)), abs(op.ocv(zhi)-op.ocv(center_z)))
        voltage_error = float(ocv_error+sum(error))
        E2 = self.E2+(voltage_error/self.node.sigma)**2
        slow = np.r_[np.exp(-newnode.elapsed/np.exp(self.upper[:3])),
                     math.exp(-float(np.exp(self.lower[3:5])@throughput))]
        weights = self.weights+(slow/self.node.sigma)**2
        if not np.isfinite(np.r_[error, E2, weights]).all():
            raise ValueError('arithmetic_unresolved')
        self.node, self.exit_error, self.throughput, self.E2, self.weights = newnode, error, throughput, E2, weights
        return voltage_error

    def query(self, eta, alpha):
        eta, alpha = np.asarray(eta), np.asarray(alpha)
        if (eta.shape != (7,) or alpha.shape != (9,) or not np.isfinite(eta).all()
                or not np.isfinite(alpha).all() or np.any(eta < self.lower) or np.any(eta > self.upper)):
            raise ValueError('outside declared domain')
        if (np.any(alpha[:4] < 0) or np.any(alpha[:4] > 1) or not 0 <= alpha[4] <= .1
                or np.any(abs(alpha[5:8]) > self.vmax) or abs(alpha[8]) > alpha[4]):
            raise ValueError('outside supported amplitude domain')
        r = self.node.S@np.r_[alpha, 1.]
        bound = float(np.linalg.norm(r)*math.sqrt(self.E2)+.5*self.E2)
        return dict(nll=self.node.nll(alpha), representation_bound=bound,
                    arithmetic_bound=None, physical_model_bound=None,
                    outgoing_v_Hh=(self.node.T@alpha)[5:9].copy(),
                    outgoing_error=self.exit_error.copy(),
                    SOC=float(eta[5]-self.node.charge/math.exp(eta[6])))

    def uniform_bound(self):
        low = np.r_[np.zeros(5), np.full(3, -self.vmax), -.1, 1.]
        high = np.r_[np.ones(4), .1, np.full(3, self.vmax), .1, 1.]
        S = self.node.S
        lo = np.maximum(S, 0)@low+np.minimum(S, 0)@high
        hi = np.maximum(S, 0)@high+np.minimum(S, 0)@low
        residual_max = np.linalg.norm(np.maximum(abs(lo), abs(hi)))
        return float(residual_max*math.sqrt(self.E2)+.5*self.E2)

    def then(self, other):
        if self.source != other.source or self.node.sigma != other.node.sigma:
            raise ValueError('incompatible source/noise')
        if np.any(self.lower[[0,1,2,3,4,6]] != other.lower[[0,1,2,3,4,6]]) or np.any(self.upper[[0,1,2,3,4,6]] != other.upper[[0,1,2,3,4,6]]):
            raise ValueError('incompatible rate/capacity domain')
        lo, hi = self.soc_range()
        required_vmax = .25 if self.count else self.vmax
        if other.lower[5] > lo or other.upper[5] < hi or other.vmax < required_vmax:
            raise ValueError('second block must cover entering state domain')
        node = self.node.then(other.node)
        out = copy.deepcopy(self)
        carried = float(self.exit_error@np.sqrt(other.weights))
        out.E2 = self.E2+(math.sqrt(other.E2)+carried)**2
        out.exit_error = other.slow_carrier()*self.exit_error+other.exit_error
        out.weights = self.weights+self.slow_carrier()**2*other.weights
        out.throughput = self.throughput+other.throughput
        out.node = node
        if not np.isfinite(np.r_[out.E2, out.exit_error, out.weights]).all():
            raise ValueError('arithmetic_unresolved')
        return out


def build(center, lower, upper, rows, first=0, entering_vmax=.08):
    field = Envelope(center, lower, upper, first, entering_vmax)
    for k, row in enumerate(rows):
        field.append(row, first+k)
    return field
