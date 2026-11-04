"""Fresh-build controls for representation, ownership and full joint derivatives."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from .field import DistinctBankField, DistinctMap, Compressed, features_jacobian, transported
from .run import MAP, build_kernels, fixture, observation_inputs, public_registration
from experiments.foster_feedback_001.estimator import Model
from experiments.foster_uncertainty_audit_001.conditional_packet import chart_from, partition


class BankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='distinct-bank-tests-')
        cls.reg = public_registration()
        cls.mean, cls.L, cls.center = map(np.asarray,
            (cls.reg['prior_mean'], cls.reg['prior_root'], cls.reg['center']))
        cls.bins, _ = build_kernels(Path(cls.temporary.name)/'build', cls.reg['config'])
        cls.model = Model(cls.bins['direct'], cls.reg['config'])
        cls.obs, _ = fixture(cls.model, cls.mean, cls.L, 127)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def make(self, mapping=MAP):
        return DistinctBankField(self.reg['config'], self.center,
            self.bins['rc'], self.bins['h'], mapping)

    def node_map(self):
        A = np.zeros((13, 27)); A[6] = 1.
        return dict(uj=np.arange(-6, 7)/4, um=np.arange(-13, 14)/12,
                    hu=1/12, A=A)

    @staticmethod
    def snapshot(field):
        return (field.root.copy(), field.state.copy(), field.rc_free.copy(),
                field.rc_forced.copy(), field.count, field.noise)

    def assert_snapshot(self, field, expected):
        for actual, before in zip(self.snapshot(field), expected):
            np.testing.assert_array_equal(actual, before)

    def test_exact_node_response_and_native_post_step_alignment(self):
        # Constant central readout map is a diagnostic control, not N13e evidence.
        mapping = {key: value.tolist() if isinstance(value, np.ndarray) else value
                   for key, value in self.node_map().items()}
        field = self.make(mapping)
        x = self.mean.copy(); x[1:4] = [.006, -.004, .003]; x[4] = .3
        obs = observation_inputs(73)
        rows = field.update(0, obs, return_rows=True)
        direct, _, endpoint, _ = self.model.evaluate(x, obs)
        represented = rows@field.features(x)*obs[:, 4]+obs[:, 3]
        np.testing.assert_allclose(represented, direct, atol=3e-14, rtol=0)
        np.testing.assert_allclose(transported(field, x)[0], endpoint, atol=3e-14, rtol=0)
        initial_voltage = self.reg['config']['ocv_intercept_V'] + self.reg['config']['ocv_slope_V_per_SOC']*x[0]
        initial_voltage += np.exp(x[13])*np.tanh(x[4])-np.exp(x[6])*obs[0, 1]-sum(x[1:4])
        self.assertGreater(abs(direct[0]-initial_voltage), 1e-5)

    def test_joint_QR_preserves_residual_score_precision_cross_terms(self):
        f = self.make(); rows = f.update(0, self.obs, return_rows=True)
        w = np.linspace(-.03, .03, 16); x = self.mean+self.L@w
        r = rows@f.features(x); B = rows@features_jacobian(f, x)@self.L
        cost, gradient, precision, _, _ = Compressed(f, self.mean, self.L)(w)
        self.assertAlmostEqual(cost, .5*(w@w+r@r), places=8)
        np.testing.assert_allclose(gradient, w+B.T@r, atol=2e-7, rtol=1e-9)
        np.testing.assert_allclose(precision, np.eye(16)+B.T@B, atol=3e-7, rtol=1e-9)
        self.assertGreater(abs(precision[5, 14]), 1e-5)
        self.assertGreater(abs(precision[7, 9]), 1e-5)

    def test_feature_and_transport_finite_differences_all_16_coordinates(self):
        f = self.make(); f.update(0, self.obs)
        a, shapes = partition(self.mean); a[1:4] = [.003, -.002, .001]; a[10] = .002
        for offsets in (np.zeros(5), np.array([-.61, .53, .31, -.43, .47])):
            x = chart_from(a, shapes*np.exp(offsets)); eps = 2e-6
            fj, tj = [], []
            for j in range(16):
                plus, minus = x+eps*self.L[:, j], x-eps*self.L[:, j]
                fj.append((f.features(plus)-f.features(minus))/(2*eps))
                tj.append((transported(f, plus)[0]-transported(f, minus)[0])/(2*eps))
            np.testing.assert_allclose(features_jacobian(f, x)@self.L, np.asarray(fj).T,
                                       atol=3e-8, rtol=3e-5)
            np.testing.assert_allclose(transported(f, x)[1]@self.L, np.asarray(tj).T,
                                       atol=3e-8, rtol=3e-5)

    def test_chunking_preserves_chronology_response_and_joint_likelihood(self):
        one, chunks = self.make(), self.make()
        one.update(0, self.obs)
        for start in range(0, len(self.obs), 19): chunks.update(start, self.obs[start:start+19])
        np.testing.assert_array_equal(one.state, chunks.state)
        np.testing.assert_array_equal(one.rc_free, chunks.rc_free)
        np.testing.assert_array_equal(one.rc_forced, chunks.rc_forced)
        np.testing.assert_allclose(one.root.T@one.root, chunks.root.T@chunks.root,
                                   atol=2e-6, rtol=2e-14)
        self.assertEqual(one.count, len(self.obs))

    def test_bad_rows_order_source_and_QR_failure_do_not_commit(self):
        f = self.make(); f.update(0, self.obs[:9]); before = self.snapshot(f)
        for column, value in [(0, -.1), (1, .3), (2, 26.), (3, np.nan), (4, 0.)]:
            bad = self.obs[9:12].copy(); bad[-1, column] = value
            with self.assertRaises(ValueError): f.update(9, bad)
            self.assert_snapshot(f, before)
        for first, source in [(8, None), (10, None), (9, 'different-source'), (True, None)]:
            with self.assertRaises(ValueError): f.update(first, self.obs[9:12], source)
            self.assert_snapshot(f, before)
        with patch('numpy.linalg.qr', side_effect=np.linalg.LinAlgError('injected')):
            with self.assertRaises(np.linalg.LinAlgError): f.update(9, self.obs[9:12])
        self.assert_snapshot(f, before)

    def test_map_jets_and_finite_public_probe_are_not_certificate(self):
        mapping = DistinctMap(MAP); eps = 2e-6
        for u in [-.91, -.42, .013, .57, .89]:
            value, d1, d2 = mapping.jets(u)
            np.testing.assert_allclose(d1, (mapping.weights(u+eps)-mapping.weights(u-eps))/(2*eps),
                                       atol=1e-7, rtol=2e-5)
            np.testing.assert_allclose(d2, (mapping.weights(u+eps, 1)-mapping.weights(u-eps, 1))/(2*eps),
                                       atol=1e-7, rtol=2e-5)
            self.assertTrue(np.isfinite(value).all())
        for u in [-1.01, 1.01, np.nan]:
            with self.assertRaises(ValueError): mapping.weights(u)
        with self.assertRaises(ValueError): mapping.A[0, 0] = 7
        f = self.make(); storage = f.storage()
        self.assertEqual(f.width, 94)
        self.assertEqual(storage['packed_factor_B'], 35720)
        self.assertFalse(storage['comparison_W34_pass'])
        self.assertFalse(storage['comparison_response312B_pass'])


if __name__ == '__main__': unittest.main()
