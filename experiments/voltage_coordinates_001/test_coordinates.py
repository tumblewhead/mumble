"""Numerical controls independent of battery held-out samples."""
import json
import math
import unittest
import numpy as np
from experiments.voltage_coordinates_001 import coordinates as c


class Controls(unittest.TestCase):
    def setUp(self):
        self.rng = np.random.default_rng(70103)

    def samples(self, n=1024):
        return c.old.LOW+c.old.WIDTH*self.rng.uniform(.1, .9, (n, 16))

    def test_inverse_global_roundtrip_and_rejection(self):
        z = np.r_[np.linspace(1e-10, 1-1e-10, 1001), 1e-14, 1-1e-14]
        np.testing.assert_allclose(c.inverse_ocv(c.ocv(z)), z, atol=1e-15, rtol=0)
        for w in [c.ocv(0), c.ocv(1), float('nan')]:
            with self.assertRaises(c.old.Unavailable):
                c.inverse_ocv(np.array([w]))

    def test_full16_jacobian(self):
        x = self.samples(1)
        def transform(x):
            out = c.old.logit(c.old.to_unit(x))
            out[:, 11] = c.voltage(x)
            return out[0]
        jac = np.empty((16, 16))
        for j in range(16):
            h = c.old.WIDTH[j]*1e-6
            a, b = x.copy(), x.copy()
            a[0, j] += h
            b[0, j] -= h
            jac[:, j] = (transform(a)-transform(b))/(2*h)
        expected = c.old.log_jacobian(c.old.to_unit(x), c.OTHER)[0]+np.log(c.ocv_derivative(x[0, 11]))
        self.assertAlmostEqual(np.linalg.slogdet(jac)[1], expected, places=7)

    @staticmethod
    def numerical_integral(a, b):
        nodes, weights = np.polynomial.legendre.leggauss(256)
        t = (a+b)/2+(b-a)*nodes/2
        center = min(b, max(a, 0))
        v = weights*(b-a)/2*np.exp(-.5*(t-center)*(t+center))
        logz = np.log(v.sum())-.5*center*center-.5*c.old.LOG2PI
        v /= v.sum()
        mean = v @ t
        return logz, mean, v @ ((t-mean)**2)

    def test_normalizer_tail_narrow_and_crossing(self):
        for a, b in [(-12, 12), (-1, 2), (1, 2), (-2, -.9), (8, 8.001), (40, 41), (-41, -40), (-1e-10, 2e-10)]:
            expected, _, _ = self.numerical_integral(a, b)
            self.assertAlmostEqual(float(c.log_mass(a, b)), expected, delta=2e-10)
        self.assertTrue(np.isfinite(c.log_mass(1000., 1001.)))

    def test_sampler_all_proposals_moments(self):
        for a, b in [(-12, 12), (-1, 2), (-.2, .3), (.2, .8), (1, 2), (8, 8.001), (-41, -40)]:
            expected_z, mean, variance = self.numerical_integral(a, b)
            x, _ = c.truncated_standard_draw(np.full(32768, a), np.full(32768, b), self.rng)
            self.assertTrue(np.all((x > a) & (x < b)))
            self.assertLess(abs(x.mean()-mean), 6*math.sqrt(variance/len(x)))
            self.assertLess(abs(np.var(x)-variance), .04*variance)

    def test_conditional_physical_density_integrates(self):
        nodes, weights = np.polynomial.legendre.leggauss(512)
        x = np.tile(self.samples(1), (512, 1))
        x[:, 11] = (nodes+1)/2
        shift = c.offset(x)[0]
        for mu, sd in [(3.6-shift, .3), (c.ocv(0)-shift-.1, .05), (c.ocv(1)-shift+.1, .05)]:
            reg = dict(voltage_coeff=np.r_[mu, np.zeros(15)], voltage_logsd=np.log(sd))
            density, _ = c.conditional_logpdf(reg, np.zeros((512, 15)), x)
            mass = np.sum(weights/2*np.exp(density)*c.ocv_derivative(x[:, 11]))
            self.assertAlmostEqual(mass, 1., delta=3e-11)

    def test_regression_cross_terms_and_variance(self):
        features = self.rng.normal(size=(2048, 15))
        design = np.column_stack((np.ones(2048), features))
        residual = self.rng.normal(size=2048)
        residual -= design @ np.linalg.lstsq(design, residual, rcond=None)[0]
        residual *= .002/np.std(residual)
        beta = np.linspace(-.01, .01, 15)
        values = 3.7+features @ beta+residual
        reg = c.fit_voltage(features, values)
        np.testing.assert_allclose(reg['voltage_coeff'], np.r_[3.7, beta], atol=1e-14)
        self.assertAlmostEqual(math.exp(reg['voltage_logsd']), .002, places=14)

    def test_dependent_support_is_not_global_box(self):
        x = self.samples(2)
        x[:, 12:15] = [[.2, .2, .2], [-.2, -.2, -.2]]
        x[:, 10] = .05
        x[:, 15] = [.8, -.8]
        reg = dict(voltage_coeff=np.r_[3.6, np.zeros(15)], voltage_logsd=np.log(.3))
        _, _, a, b = c.conditional_parameters(reg, np.zeros((2, 15)), x)
        self.assertGreater(abs(float(c.log_mass(a[0], b[0])-c.log_mass(a[1], b[1]))), .1)

    def test_replication_serialization_and_packed_size(self):
        x = self.samples()
        for arm in ['fixed_partition_gaussian_mixture', 'fixed_probability_atlas', 'adaptive_probability_atlas']:
            a = c.fit(x, 2, arm)
            b = c.fit(np.tile(x, (2, 1)), 2, arm)
            np.testing.assert_allclose(a.logpdf(x[:20]), b.logpdf(x[:20]), atol=2e-10)
            restored = c.Message.restore(json.loads(json.dumps(a.export())))
            np.testing.assert_array_equal(restored.logpdf(x[:20]), a.logpdf(x[:20]))
            self.assertEqual(a.numeric_bytes, 2472 if 'mixture' in arm else 2488)
            draw, _ = restored.draw(2048, 123)
            c.old.to_unit(draw)
            self.assertTrue(np.isfinite(restored.logpdf(draw)).all())

    def test_physical_voltage_probe_identity(self):
        x = self.samples()
        expected, valid = c.old.stationary_probe(x, [])
        np.testing.assert_allclose(c.voltage(x), expected, atol=1e-15)
        self.assertTrue(valid.all())

    def test_singular_fit_failure(self):
        with self.assertRaises(c.old.Unavailable):
            c.fit_voltage(np.zeros((64, 15)), np.ones(64))


if __name__ == '__main__':
    unittest.main()
