"""Numerical controls; synthetic distributions are not battery fit truth."""
import json
import math
from types import SimpleNamespace
import unittest
import numpy as np
from experiments.region_compression_001 import regions as r


class Controls(unittest.TestCase):
    def setUp(self):
        self.rng = np.random.default_rng(81245)

    def sample(self, n=1024):
        return r.LOW + r.WIDTH * self.rng.uniform(.05, .95, (n, 16))

    def test_transform_and_jacobian(self):
        x = self.sample(20)
        u = r.to_unit(x)
        np.testing.assert_allclose(r.from_logits(r.logit(u)), u, rtol=1e-14)
        for j in range(16):
            step = r.WIDTH[j]*1e-6
            a, b = x.copy(), x.copy()
            a[:, j] += step
            b[:, j] -= step
            derivative = (r.logit(r.to_unit(a))[:, j]-r.logit(r.to_unit(b))[:, j])/(2*step)
            analytic = 1/(r.WIDTH[j]*u[:, j]*(1-u[:, j]))
            np.testing.assert_allclose(derivative, analytic, rtol=1e-8)

    def test_gaussian_density_full_covariance(self):
        a = self.rng.normal(size=(16, 16))
        cov = a @ a.T + np.eye(16)
        mean = self.rng.normal(size=16)
        x = self.rng.normal(size=(24, 16))
        delta = x-mean
        expected = -.5*np.einsum('ni,ij,nj->n', delta, np.linalg.inv(cov), delta)
        expected -= .5*(16*r.LOG2PI + np.linalg.slogdet(cov)[1])
        np.testing.assert_allclose(r.gaussian_logpdf(x, mean, r.pack_factor(cov)), expected, atol=2e-13)

    def test_analytic_mixture_moments_and_weak_direction(self):
        means = [np.zeros(16), np.ones(16)*.5]
        cov = np.eye(16)
        cov[1, 1] = 4.
        cov[0, 1] = cov[1, 0] = .7
        parts = [dict(logweight=np.array(math.log(w)), mean=m, factor=r.pack_factor(cov))
                 for w, m in zip([.3, .7], means)]
        msg = r.Message('fixed_partition_gaussian_mixture', np.array([0, .5, 1]), parts, [])
        x, _ = msg.draw(65536, 9021)
        y = r.logit(r.to_unit(x))
        expected_mean = .3*means[0]+.7*means[1]
        expected_cov = cov + .3*.7*np.outer(means[1]-means[0], means[1]-means[0])
        np.testing.assert_allclose(y.mean(0), expected_mean, atol=.035)
        np.testing.assert_allclose(np.cov(y, rowvar=False, bias=True), expected_cov, atol=.07)

    def test_quadratic_normalization_and_uniform(self):
        for theta in [np.zeros(2), np.array([1.2, -2.]), np.array([-3., 2.])]:
            z, m, h = r.quad_stats(theta)
            z2, m2, h2 = r.quad_stats(theta, 256)
            np.testing.assert_allclose([z, *m], [z2, *m2], atol=2e-13)
            self.assertGreater(np.linalg.eigvalsh(h).min(), 0)
            np.testing.assert_allclose(h, h2, atol=2e-13)
        z, m, _ = r.quad_stats(np.zeros(2))
        self.assertAlmostEqual(z, math.log(2), places=13)
        np.testing.assert_allclose(m, [0, 1/3], atol=1e-14)

    def test_quadratic_fit_recovers_moments(self):
        t = self.rng.beta(2, 3, 4096)*2-1
        theta, _, _ = r.fit_quadratic(t)
        _, m, _ = r.quad_stats(theta, 256)
        np.testing.assert_allclose(m, [t.mean(), (t*t).mean()], atol=2e-9)

    def test_conditional_cross_covariance(self):
        n = 1024
        t = (np.arange(n)+.5)*2/n-1
        design = np.column_stack((np.ones(n), t))
        noise = self.rng.normal(size=(n, 15))
        noise -= design @ np.linalg.lstsq(design, noise, rcond=None)[0]
        slope = np.linspace(-.4, .6, 15)
        intercept = np.linspace(-.2, .2, 15)
        y = intercept + t[:, None]*slope + noise*.2
        u = np.empty((n, 16))
        u[:, 5] = (t+1)/2
        u[:, r.OTHER] = r.from_logits(y)
        msg = r.fit(r.LOW+r.WIDTH*u, 1, 'fixed_probability_atlas')
        np.testing.assert_allclose(msg.regions[0]['slope'], slope, atol=1e-12)
        np.testing.assert_allclose(msg.regions[0]['intercept'], intercept, atol=1e-12)
        l = r.unpack_factor(msg.regions[0]['factor'], 15)
        np.testing.assert_allclose(l@l.T, .04*noise.T@noise/n, atol=1e-12)

    def test_probability_ownership_replication_and_serialization(self):
        x = self.sample()
        for arm in ['fixed_partition_gaussian_mixture', 'fixed_probability_atlas', 'adaptive_probability_atlas']:
            a = r.fit(x, 2, arm)
            b = r.fit(np.tile(x, (2, 1)), 2, arm)
            self.assertAlmostEqual(sum(math.exp(p['logweight']) for p in a.regions), 1., places=14)
            np.testing.assert_allclose(a.logpdf(x[:25]), b.logpdf(x[:25]), atol=1e-10)
            c = r.Message.restore(json.loads(json.dumps(a.export())))
            np.testing.assert_array_equal(a.logpdf(x[:25]), c.logpdf(x[:25]))
            if 'mixture' not in arm:
                at_edge = x[:1].copy()
                at_edge[:, 5] = r.LOW[5]+r.WIDTH[5]*a.edges[1]
                self.assertTrue(np.isfinite(a.logpdf(at_edge)).all())
            draws, _ = a.draw(1024, 912)
            r.to_unit(draws)
            self.assertTrue(np.isfinite(a.logpdf(draws)).all())

    def test_explicit_failure_support_and_singularity(self):
        x = self.sample(64)
        x[0, 0] = r.LOW[0]
        with self.assertRaises(r.Unavailable):
            r.fit(x, 2, 'fixed_probability_atlas')
        with self.assertRaises(r.Unavailable):
            r.pack_factor(np.zeros((16, 16)))
        with self.assertRaises(r.Unavailable):
            r.placement(np.full(64, .1), 4, True)

    def test_physical_probe_scalar_kernel_parity(self):
        for _ in range(12):
            x = r.kernel.MEAN + .1*r.kernel.SD*self.rng.normal(size=16)
            state = r.kernel.initial_state(x, 'test')
            steps = [[.05, 1.], [-.05, 1.]]
            for i, (current, dt) in enumerate(steps):
                record = SimpleNamespace(source_id='test', index=i, current=current, dt=dt,
                    temperature_C=25., input_known=True, measurement_valid=False, voltage=None)
                state, expected, _, _ = r.kernel.advance(state, record, tuple(x[[5, 6]]))
            actual, valid = r.stationary_probe(x[None], steps)
            self.assertTrue(valid[0])
            self.assertAlmostEqual(actual[0], expected, places=14)

    def test_probe_invalid_mass_is_retained(self):
        x = self.sample(2)
        x[0, 11] = 1e-8
        v, valid = r.stationary_probe(x, [[.05, 1.]])
        self.assertEqual(len(v), 2)
        self.assertFalse(valid[0])


if __name__ == '__main__':
    unittest.main()
