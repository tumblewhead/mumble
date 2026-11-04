"""Experimental full-model distinct-pole RC history with unchanged TaylorH2.

The supplied signed map is NUM evidence, not a physical/error certificate. Three
separate fixed banks retain uncertain incoming branch states and continuous RC
queries. One joint QR factor keeps all cross terms. No truth or pickle is read.
"""
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from experiments.hysteresis_sensitivity_basis_001.basis import HField
from experiments.foster_uncertainty_audit_001.conditional_packet import partition


class DistinctMap:
    """Safe JSON map; preserve supplied coefficients, coordinates and defects."""
    def __init__(self, source):
        if isinstance(source, (str, Path)):
            raw = Path(source).read_bytes()
            data = json.loads(raw)
        elif isinstance(source, dict):
            data = source
            raw = json.dumps(data, sort_keys=True, allow_nan=False).encode()
        else:
            raise ValueError('map must be a JSON path or mapping')
        self.sha256 = hashlib.sha256(raw).hexdigest()
        self.uj = np.array(data['uj13'] if 'uj13' in data else data['uj'], dtype=float, copy=True)
        self.um = np.array(data['um27'] if 'um27' in data else data['um'], dtype=float, copy=True)
        self.hu = float(data['hu'])
        self.A = np.array(data['A13x27'] if 'A13x27' in data else data['A'], dtype=float, copy=True)
        if (self.uj.shape != (13,) or self.um.shape != (27,) or
                self.A.shape != (13, 27) or not math.isfinite(self.hu) or
                not all(np.isfinite(v).all() for v in (self.uj, self.um, self.A))):
            raise ValueError('finite N13e map dimensions required')
        # The supplied decimal coordinates have small rounding defects. Validate
        # their declared lattice, but evaluate the original numbers without snaps.
        if (self.hu <= 0 or np.any(np.diff(self.uj) <= 0) or
                np.any(np.diff(self.um) <= 0) or
                not np.allclose(self.uj, np.arange(-6, 7) / 4., rtol=0, atol=1e-8) or
                not np.allclose(self.um, np.arange(-13, 14) / 12., rtol=0, atol=1e-8) or
                not math.isclose(self.hu, 1 / 12., rel_tol=0, abs_tol=1e-8)):
            raise ValueError('unsupported N13e pole/spline lattice')
        if 'domain' in data and not np.array_equal(np.asarray(data['domain']), [-1., 1.]):
            raise ValueError('original log-rate domain must remain [-1,1]')
        self.domain = (-1., 1.)
        self.normalization_defect = float(np.max(np.abs(self.A.sum(axis=0) - 1.)))
        # Sampled arithmetic diagnostics only: rounded spline centers/spacing can
        # violate unity independently of the column sums. Neither is repaired.
        sample = np.linspace(-1., 1., 1001)
        t = np.abs((sample[:, None]-self.um)/self.hu)
        beta = np.where(t <= 1, (4-6*t*t+3*t*t*t)/6,
                        np.where(t < 2, (2-t)**3/6, 0.))
        self.spline_partition_unity_sampled_defect = float(np.max(np.abs(beta.sum(axis=1)-1)))
        self.weight_sum_sampled_defect = float(np.max(np.abs((beta @ self.A.T).sum(axis=1)-1)))
        for value in (self.uj, self.um, self.A):
            value.flags.writeable = False

    def weights(self, u, derivative=0):
        """Value or first/second derivative in physical log(tau/tau_center)."""
        if derivative not in (0, 1, 2):
            raise ValueError('cardinal cubic supports derivatives 0,1,2')
        u = np.asarray(u, dtype=float)
        if not np.isfinite(u).all() or np.any(u < -1.) or np.any(u > 1.):
            raise ValueError('outside original log-rate domain [-1,1]')
        x = (u[..., None] - self.um) / self.hu
        t = np.abs(x)
        if derivative == 0:
            b = np.where(t <= 1, (4 - 6*t*t + 3*t*t*t)/6,
                         np.where(t < 2, (2-t)**3/6, 0.))
        elif derivative == 1:
            b = np.sign(x)*np.where(t <= 1, -2*t + 1.5*t*t,
                                   np.where(t < 2, -.5*(2-t)**2, 0.))/self.hu
        else:
            b = np.where(t <= 1, -2 + 3*t,
                         np.where(t < 2, 2-t, 0.))/self.hu**2
        return b @ self.A.T

    def jets(self, u):
        return tuple(self.weights(u, k) for k in range(3))


class DistinctBankField:
    """Composition adapter; the existing HField implementation is unmodified."""
    def __init__(self, config, center, rc_binary, h_binary, bank_map, source='fixture'):
        self.map = bank_map if isinstance(bank_map, DistinctMap) else DistinctMap(bank_map)
        self.legacy = HField(config, center, rc_binary, h_binary, 'TaylorH2', source)
        self.config = config
        self.center = self.legacy.center
        self.halfwidth = self.legacy.halfwidth
        self.poles = np.exp(-self.map.uj)[None, :] / self.center[:3, None]
        if not np.isfinite(self.poles).all() or np.any(self.poles <= 0):
            raise ValueError('finite positive fixed bank rates required')
        self.rc_free = np.ones((3, 13))
        self.rc_forced = np.zeros((3, 13))
        self.n = 13
        self.b = self.legacy.b
        self.hstart = 3 + 6*self.n
        self.legacy_hstart = 3 + 6*self.legacy.n
        self.width = self.hstart + 2*self.b + 1
        self.root = np.zeros((self.width, self.width))

    @property
    def state(self):
        """Legacy native RC/H/path state; bank state is separately retained."""
        return self.legacy.state

    @property
    def count(self):
        return self.legacy.count

    @property
    def noise(self):
        return self.legacy.noise

    @property
    def source(self):
        return self.legacy.source

    def _stage_rows(self, first, observations, source=None):
        if isinstance(first, (bool, np.bool_)) or not isinstance(first, (int, np.integer)):
            raise ValueError('integer observation sequence required')
        # Native staging validates source, chronology, finite values, actual dt,
        # current, sigma and T=25C, without mutating legacy response or root.
        obs = np.ascontiguousarray(observations, dtype=float)
        old_rows, state, count, noise = self.legacy._stage_rows(first, obs, source)
        free, forced = self.rc_free.copy(), self.rc_forced.copy()
        rows = np.empty((len(obs), self.width))
        rows[:, :3] = old_rows[:, :3]
        rows[:, self.hstart:] = old_rows[:, self.legacy_hstart:]
        for k, (dt, current, _T, _y, sigma) in enumerate(obs):
            dose = self.poles * dt
            decay = np.exp(-dose)
            one = -np.expm1(-dose)
            free *= decay
            forced = decay*forced + one*current
            for branch in range(3):
                start = 3 + 2*branch*self.n
                rows[k, start:start+self.n] = -free[branch]/sigma
                rows[k, start+self.n:start+2*self.n] = -forced[branch]/sigma
        if not all(np.isfinite(v).all() for v in (rows, free, forced)):
            raise ValueError('nonfinite bank recurrence')
        return rows, state, free, forced, count, noise

    def _commit(self, state, free, forced, count, noise):
        self.legacy.state, self.rc_free, self.rc_forced = state, free, forced
        self.legacy.count, self.legacy.noise = count, noise

    def rows(self, first, observations, source=None):
        """Advance responses only; intended for retained-row diagnostics."""
        rows, state, free, forced, count, noise = self._stage_rows(first, observations, source)
        self._commit(state, free, forced, count, noise)
        return rows

    def update(self, first, observations, source=None, return_rows=False):
        rows, state, free, forced, count, noise = self._stage_rows(first, observations, source)
        root = np.linalg.qr(np.vstack((self.root, rows)), mode='r')
        root *= np.where(np.diag(root) < 0, -1., 1.)[:, None]
        if not np.isfinite(root).all():
            raise ValueError('nonfinite joint likelihood root')
        # All fallible numerical work precedes commit. Single synchronous owner;
        # this does not certify asynchronous interruption or concurrent access.
        self.root = root
        self._commit(state, free, forced, count, noise)
        return rows if return_rows else None

    def basis_query(self, amplitude, shape):
        old, old_J, T = self.legacy.basis_query(amplitude, shape)
        a, s = np.asarray(amplitude, dtype=float), np.asarray(shape, dtype=float)
        u = np.log(s[:3]/self.center[:3])
        w, dw = self.map.weights(u), self.map.weights(u, 1)
        values = np.empty(self.width)
        J = np.zeros((self.width, 16))
        values[:3], J[:3] = old[:3], old_J[:3]
        values[self.hstart:], J[self.hstart:] = old[self.legacy_hstart:], old_J[self.legacy_hstart:]
        for branch in range(3):
            for kind, amp in enumerate((1+branch, 6+branch)):
                start = 3 + (2*branch+kind)*self.n
                values[start:start+self.n] = a[amp]*w[branch]
                J[start:start+self.n, amp] = w[branch]
                J[start:start+self.n, 11+branch] = a[amp]*dw[branch]
        return values, J, T

    @staticmethod
    def _partition(chart):
        x = np.asarray(chart, dtype=float)
        if x.shape != (16,) or not np.isfinite(x).all():
            raise ValueError('finite 16D physical chart required')
        with np.errstate(over='ignore', invalid='ignore', divide='ignore'):
            a, s = partition(x)
        return x, a, s

    def features(self, chart):
        _x, a, s = self._partition(chart)
        return self.basis_query(a, s)[0]

    def features_jacobian(self, chart):
        x, a, s = self._partition(chart)
        _, J, _ = self.basis_query(a, s)
        chain = np.zeros((16, 16))
        chain[:4, :4] = np.eye(4)
        chain[4, 5] = -a[4]
        for row, col in ((5, 6), (6, 7), (7, 9), (8, 11), (9, 13)):
            chain[row, col] = a[row]
        e = math.exp(-2*abs(x[4]))
        chain[10, 4] = a[9]*4*e/(1+e)**2
        chain[10, 13] = a[10]
        gaps = np.exp(x[[8, 10, 12]])
        for branch in range(3):
            chain[11+branch, [8, 10, 12][:branch+1]] = gaps[:branch+1]/s[branch]
        for row, col in ((14, 14), (15, 15)):
            chain[row, col] = 1.
            chain[row, 5] = -1.
        return J @ chain

    def physical_transport_matrix(self):
        W = np.zeros((5, self.width))
        W[0, 0], W[0, 1] = 1., -self.state[-3]
        for branch in range(3):
            start = 3 + 2*branch*self.n
            W[branch+1, start:start+self.n] = self.rc_free[branch]
            W[branch+1, start+self.n:start+2*self.n] = self.rc_forced[branch]
        hstate = 6*self.legacy.n
        nn = self.legacy.m**2
        W[4, self.hstart:self.hstart+self.b] = self.legacy.p2 @ self.state[hstate+nn:hstate+2*nn]
        W[4, self.hstart+self.b:self.hstart+2*self.b] = self.legacy.p2 @ self.state[hstate:hstate+nn]
        return W

    def transported(self, chart):
        x, _, _ = self._partition(chart)
        W = self.physical_transport_matrix()
        physical = W @ self.features(x)
        D = np.eye(16)
        D[:5] = W @ self.features_jacobian(x)
        H = math.exp(x[13])
        h = physical[4]/H
        if not -1 < h < 1 or not 0 <= physical[0] <= 1:
            raise ValueError('field endpoint outside physical chart support')
        D[4] /= H
        D[4, 13] -= h
        D[4] /= 1-h*h
        end = x.copy()
        end[:4], end[4] = physical[:4], np.arctanh(h)
        return end, D

    def residual(self, chart):
        return self.root @ self.features(chart)

    def nll(self, chart):
        r = self.residual(chart)
        return .5*float(r @ r) + self.noise

    def evaluate(self, amplitude, shape):
        f, J, _ = self.basis_query(amplitude, shape)
        r, B = self.root @ f, self.root @ J
        g = B.T @ r
        end = np.array(amplitude, dtype=float, copy=True)
        physical = self.physical_transport_matrix() @ f
        end[:4], end[10] = physical[:4], physical[4]
        return dict(nll=.5*float(r @ r)+self.noise, gradient_amplitude=g[:11],
                    gradient_shape=g[11:], precision_amplitude=B[:, :11].T @ B[:, :11], end=end)

    def outgoing(self, chart):
        _x, a, s = self._partition(chart)
        return self.evaluate(a, s)['end']

    def storage(self):
        arrays = {}
        for label, obj in (('adapter', self), ('legacy', self.legacy), ('map', self.map)):
            for key, value in vars(obj).items():
                if isinstance(value, np.ndarray):
                    arrays[label+'.'+key] = value
        # Count distinct backing arrays once (adapter center/halfwidth alias legacy).
        unique = {id(v): v for v in arrays.values()}
        packed = 8*self.width*(self.width+1)//2
        response = self.rc_free.nbytes+self.rc_forced.nbytes+self.state.nbytes
        return dict(lifted_width=self.width, width=self.width, packed_factor_B=packed,
                    packed_root_B=packed, live_response_B=response,
                    distinct_RC_state_B=self.rc_free.nbytes+self.rc_forced.nbytes,
                    legacy_native_state_B=self.state.nbytes, bank_count=3, poles_per_bank=13,
                    response_state_scalars=response//8,
                    comparison_W34_pass=self.width <= 34, comparison_response312B_pass=response <= 312,
                    map_table_B=self.map.A.nbytes+self.map.uj.nbytes+self.map.um.nbytes+8,
                    map_sha256=self.map.sha256, map_column_sum_defect=self.map.normalization_defect,
                    map_spline_partition_unity_sampled_defect=self.map.spline_partition_unity_sampled_defect,
                    map_weight_sum_sampled_defect=self.map.weight_sum_sampled_defect,
                    map_unity_diagnostic_scope='1001 uniformly spaced queries; not a uniform bound',
                    map_status='supplied_NUM_not_certified_no_renormalization',
                    retained_numpy_arrays_B=sum(v.nbytes for v in unique.values()),
                    array_breakdown_B={k: v.nbytes for k, v in arrays.items()},
                    input_chunk_B=1024*5*8, native_rows_B=1024*self.legacy.width*8,
                    response_rows_B=1024*self.width*8,
                    stacked_QR_input_B=(1024+self.width)*self.width*8,
                    trial_response_B=response, new_dense_root_B=self.root.nbytes,
                    query_root_product_J_B=self.width*16*8,
                    exclusions='Not complete SRAM: Python/BLAS, metadata, prior, solver, scratch and stack excluded; legacy RC/native root retained and counted. No W34,312B,physical coverage or firmware qualification.')


def features_jacobian(field, chart):
    return field.features_jacobian(chart)


def transported(field, chart):
    return field.transported(chart)


class Compressed:
    def __init__(self, field, mean, root):
        self.field, self.mean, self.root = field, mean, root

    def __call__(self, w):
        x = self.mean + self.root @ w
        r = self.field.residual(x)
        B = self.field.root @ self.field.features_jacobian(x) @ self.root
        return .5*float(w @ w+r @ r), w+B.T @ r, np.eye(16)+B.T @ B, None, None
