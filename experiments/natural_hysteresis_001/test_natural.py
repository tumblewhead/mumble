import json
from pathlib import Path
import unittest
import numpy as np
from experiments.natural_hysteresis_001 import natural as n
from experiments.natural_hysteresis_001.message import Message, unchanged
from experiments.partition_coordinate_fit_001 import coordinates as c
from experiments.partition_coordinate_fit_001.stable_normalizer import log_mass

HERE = Path(__file__).resolve().parent
CONFIG = json.loads((HERE/'plan.json').read_text())['optimizer']


class Controls(unittest.TestCase):
    def test_partition_refinement(self):
        eta = np.array([-20., -3., -1e-12, 0., 1e-12, 3., 20.])
        for k in [0., .001, .8, 1., 3., 20.]:
            actual, _ = n.statistics(eta, k)
            np.testing.assert_allclose(actual, n.quadrature(eta, k, 512), atol=3e-12, rtol=0)

    def test_positive_precision_gaussian_equivalence(self):
        eta = np.array([-4., -1., 0., 1., 4.])
        y = np.array([-.9, -.4, 0., .4, .9])
        for k in [.001, .01, .5, 1., 4.]:
            mu, sd = eta/k, 1/np.sqrt(k)
            gaussian = -.5*((y-mu)/sd)**2-np.log(sd)-.5*c.old.LOG2PI-log_mass((-1-mu)/sd, (1-mu)/sd)
            actual = eta*y-.5*k*y*y-n.log_partition(eta, k)
            np.testing.assert_allclose(actual, gaussian, atol=2e-11, rtol=0)

    def test_derivatives_all_entries(self):
        rng = np.random.default_rng(120)
        design = np.column_stack([np.ones(80), rng.uniform(-1, 1, (80, 3))])
        target = rng.uniform(-1, 1, 80)
        theta = np.array([-.7, .2, -.1, .4, .2])
        _, gradient, hessian, _ = n.objective(theta, design, target)
        for j in range(len(theta)):
            step = np.zeros(len(theta))
            step[j] = 1e-5
            plus, minus = n.objective(theta+step, design, target), n.objective(theta-step, design, target)
            self.assertAlmostEqual((plus[0]-minus[0])/2e-5, gradient[j], delta=2e-10)
            np.testing.assert_allclose((plus[1]-minus[1])/2e-5, hessian[:, j], atol=2e-10, rtol=0)

    def test_boundary_kkt(self):
        target = np.tile([-.8, .8], 256)
        beta, k, diag = n.fit(np.empty((len(target), 0)), target, np.array([.1]), .01, CONFIG)
        self.assertEqual(diag['status'], 'constrained_gradient_tolerance_met')
        self.assertEqual(k, 0.)
        self.assertGreater(diag['precision_gradient'], .15)
        self.assertAlmostEqual(beta[0], 0., delta=1e-7)

    def test_interior_recovery(self):
        rng = np.random.default_rng(121)
        features = rng.uniform(-1, 1, (12000, 1))
        target, _ = n.draw(.2+.6*features[:, 0], 3., rng)
        beta, k, diag = n.fit(features, target, np.zeros(2), .01, CONFIG)
        self.assertEqual(diag['status'], 'constrained_gradient_tolerance_met')
        np.testing.assert_allclose(beta, [.2, .6], atol=.08, rtol=0)
        self.assertAlmostEqual(k, 3., delta=.18)

    def test_nonconvergence_explicit(self):
        _, _, diag = n.fit(np.empty((20, 0)), np.full(20, .7), np.array([0.]), .01,
                           dict(CONFIG, iterations=0))
        self.assertEqual(diag['status'], 'iteration_cap')
        self.assertGreater(diag['constrained_gradient_infinity'], CONFIG['gradient_tolerance'])

    def test_uniform_exponential_and_positive_sampling(self):
        rng = np.random.default_rng(122)
        for eta, k in [(0., 0.), (1e-12, 0.), (-3., 0.), (3., 0.), (-3., .001), (2., .8), (2., 3.)]:
            samples, count = n.draw(np.full(40000, eta), k, rng)
            stats = n.quadrature(np.array([eta]), k, 512)[0]
            self.assertTrue(np.all(np.abs(samples) < 1))
            self.assertGreaterEqual(count, len(samples))
            self.assertAlmostEqual(samples.mean(), stats[1], delta=.012)
            self.assertAlmostEqual(np.mean(samples**2), stats[2], delta=.012)
        self.assertEqual(float(n.exponential_log_partition(np.array([0.]))[0]), np.log(2.))

    def test_negative_precision_rejected(self):
        with self.assertRaises(c.old.Unavailable):
            n.statistics(np.array([0.]), -.01)

    def test_message_roundtrip_storage_and_preservation(self):
        path = HERE.parent/'partition_coordinate_fit_001/attempt002/prefix8_specialized_bounded_likelihood_message.json'
        parent = c.Message.restore(json.loads(path.read_text())['posterior'])
        msg = Message.from_gaussian(parent)
        unchanged(parent, msg)
        restored = Message.restore(msg.export())
        x, _ = msg.draw(32, 123)
        np.testing.assert_array_equal(msg.logpdf(x), restored.logpdf(x))
        original = c.v.log_mass
        try:
            c.v.log_mass = log_mass
            np.testing.assert_allclose(parent.logpdf(x), msg.logpdf(x), atol=2e-11, rtol=0)
        finally:
            c.v.log_mass = original
        with self.assertRaises(c.old.Unavailable):
            Message.restore(parent.export())


if __name__ == '__main__':
    unittest.main()
