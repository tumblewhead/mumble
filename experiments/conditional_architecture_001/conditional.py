"""Fixed-public-shape likelihood control; not an unknown-rate estimator.

Uses the existing affine block response and composition, retaining a packed
factor. No priors, posterior feedback, truth or replay inside the accumulator.
"""
import copy
import numpy as np
from experiments.foster_uncertainty_audit_001.conditional_packet import Packet, make, compose

TRI = np.triu_indices(12)


class FixedShape:
    def __init__(self, config, shape, source):
        self._config = copy.deepcopy(config)
        self._store(make(np.empty((0, 5)), shape, self._config, source))

    def _store(self, packet):
        # Prepare every replacement before committing. The dense factor is scratch.
        packed = packet.root[TRI].copy()
        coeff = packet.coeff.copy()
        shape = packet.shape.copy()
        if not all(np.isfinite(x).all() for x in (packed, coeff, shape)) or not np.isfinite(packet.noise_constant):
            raise ValueError('nonfinite conditional accumulator')
        self._packed, self._coeff, self._shape = packed, coeff, shape
        self._source, self.count = packet.source, packet.end
        self._noise, self._minimum, self._maximum = packet.noise_constant, packet.charge_min, packet.charge_max
        self._calibration = packet.calibration

    def snapshot(self):
        root = np.zeros((12, 12)); root[TRI] = self._packed
        return Packet(self._source, 0, self.count, self._shape.copy(), root,
                      self._noise, self._coeff.copy(), self._minimum, self._maximum, self._calibration)

    def advance(self, first, rows, source):
        if type(first) is not int or first != self.count or source != self._source:
            raise ValueError('source/order mismatch')
        rows = np.asarray(rows, dtype=float)
        if rows.ndim != 2 or rows.shape[1] != 5 or not 1 <= len(rows) <= 4096:
            raise ValueError('bounded nonempty block required')
        block = make(rows, self._shape, self._config, source, first)
        trial = compose(self.snapshot(), block)
        self._store(trial)

    def evaluate(self, amplitude, shape):
        if not np.array_equal(shape, self._shape):
            raise ValueError('fixed-shape history cannot be reinterpreted at new rates')
        packet = self.snapshot()
        nll = packet.nll(amplitude)
        r = packet.root @ np.r_[amplitude, 1.]
        J = packet.root[:, :11]
        return nll, J.T @ r, J.T @ J, packet.outgoing(amplitude)

    def storage(self):
        return dict(packed_likelihood_B=self._packed.nbytes,
                    response_coefficients_B=self._coeff.nbytes,
                    fixed_shape_B=self._shape.nbytes,
                    scalar_payload_B=32,
                    subtotal_B=self._packed.nbytes+self._coeff.nbytes+self._shape.nbytes+32,
                    scope='Numeric retained payload only. Calibration/source/config/Python objects, dense QR/block scratch, prior and optimizer excluded; no unknown-shape storage included.')


def chart_amplitude_jacobian(amplitude):
    """Derivative of existing chart_from at FIXED tau and gamma/Q."""
    a = np.asarray(amplitude); q, H, B = a[4], a[9], a[10]
    if q <= 0 or H <= abs(B):
        raise ValueError('interior amplitude chart required')
    D = np.zeros((16, 11)); D[:4, :4] = np.eye(4)
    D[4, 9] = -B / (H*H-B*B); D[4, 10] = H / (H*H-B*B)
    D[5, 4] = D[14, 4] = D[15, 4] = -1/q
    for row, col in ((6, 5), (7, 6), (9, 7), (11, 8), (13, 9)):
        D[row, col] = 1/a[col]
    return D
