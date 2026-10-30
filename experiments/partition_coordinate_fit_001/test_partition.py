import json
import math
from pathlib import Path
import unittest
import numpy as np
from experiments.partition_coordinate_fit_001 import coordinates as c
from experiments.partition_coordinate_fit_001 import fitting

CONFIG = json.loads((Path(__file__).parent/'plan.json').read_text())['optimizer']


class Controls(unittest.TestCase):
    def setUp(self):
        self.rng = np.random.default_rng(71321)
        self.x = c.old.LOW+c.old.WIDTH*self.rng.uniform(.15, .85, (1024, 16))
        self.frame = c.rc.frame_values('response_public_mode_scale')

    def test_inverse_and_full16_Jacobian(self):
        for chart in ['current', 'specialized']:
            y, _, jacobian = c.encode(self.x, chart, self.frame)
            np.testing.assert_allclose(c.decode(y, chart, self.frame), self.x, atol=2e-15, rtol=1e-14)
            x = self.x[:1]
            matrix = np.empty((16, 16))
            for j in range(16):
                step = c.old.WIDTH[j]*1e-6
                a, b = x.copy(), x.copy()
                a[0, j] += step
                b[0, j] -= step
                matrix[:, j] = (c.encode(a, chart, self.frame)[0][0]-c.encode(b, chart, self.frame)[0][0])/(2*step)
            self.assertAlmostEqual(np.linalg.slogdet(matrix)[1], jacobian[0], places=7)

    def test_OCV_Mobius_interval_specific_capacity(self):
        z = .62
        r = math.tanh(8*(z-.5))
        accumulated = np.eye(2)
        for q, current, dt in [(.06, .05, 1.), (.059, -.03, .1), (.058, .02, 1/35)]:
            charge = current*dt/3600
            b = math.tanh(8*charge/q)
            r = (r-b)/(1-r*b)
            z -= charge/q
            accumulated = np.array([[1., -b], [-b, 1.]]) @ accumulated
            self.assertAlmostEqual(r, math.tanh(8*(z-.5)), places=14)
        initial = math.tanh(8*(.62-.5))
        composed = accumulated @ [initial, 1.]
        self.assertAlmostEqual(composed[0]/composed[1], r, places=14)

    def test_RC_chronology_and_hysteresis_views(self):
        tau, resistance, state = .4, .15, .02
        product = np.eye(2)
        for current, dt in [(.05, .1), (-.05, .2), (0., .3)]:
            operator = c.rc_operator(tau, current, dt)
            state = math.exp(-dt/tau)*state-math.expm1(-dt/tau)*resistance*current
            product = operator @ product
        self.assertAlmostEqual((product @ [.02, resistance])[0], state, places=15)
        h, product = .3, np.eye(2)
        for gamma, sign, throughput in [(150., 1., .002), (300., -1., .003)]:
            before = math.log1p(-sign*h)
            operator = c.hysteresis_operator(gamma, sign, throughput)
            h = (operator @ [h, 1.])[0]
            self.assertAlmostEqual(math.log1p(-sign*h), before-gamma*throughput, places=14)
            product = operator @ product
        self.assertAlmostEqual((product @ [.3, 1.])[0], h, places=14)
        x = self.x[:1].copy()
        x[0, 10] = 0.
        self.assertEqual(c.transport_views(x)['derived_Hh'][0], 0.)
        x[0, 15] = 1.
        with self.assertRaises(c.old.Unavailable):
            c.transport_views(x)
        self.assertEqual((c.hysteresis_operator(150., 1., .002) @ [1., 1.])[0], 1.)

    def test_objective_all_coefficient_derivatives(self):
        design = np.column_stack((np.ones(128), self.rng.normal(size=(128, 3))))
        target = self.rng.uniform(-.5, .5, 128)
        lower, upper = np.full(128, -1.), np.full(128, 1.)
        for theta in [np.array([.2, .1, -.2, .3, -.1]), np.array([3., .1, .2, -.1, -.5])]:
            _, gradient = fitting.objective(theta, design, target, lower, upper)
            for j in range(len(theta)):
                delta = np.zeros(len(theta))
                delta[j] = 1e-5
                measured = (fitting.objective(theta+delta, design, target, lower, upper)[0]
                            -fitting.objective(theta-delta, design, target, lower, upper)[0])/(2e-5)
                self.assertAlmostEqual(measured, gradient[j], delta=3e-7*(1+abs(gradient[j])))

    def test_bounded_regression_recovery(self):
        n = 16384
        feature = self.rng.uniform(-1, 1, (n, 1))
        mu = .2+.6*feature[:, 0]
        sd = .4
        lower, upper = np.full(n, -.5), np.full(n, 1.)
        t, _ = c.v.truncated_standard_draw((lower-mu)/sd, (upper-mu)/sd, self.rng)
        target = mu+sd*t
        beta, logsd, diag = fitting.fit(feature, target, lower, upper, 'bounded_likelihood', CONFIG)
        self.assertEqual(diag['status'], 'first_order_stationary')
        np.testing.assert_allclose(beta, [.2, .6], atol=.025)
        self.assertAlmostEqual(math.exp(logsd), sd, delta=.02)
        self.assertLess(diag['final_mean_NLL'], diag['initial_mean_NLL']-.01)

    def test_limit_is_not_stationarity(self):
        values = self.rng.uniform(0., 1., 1024)
        config = dict(CONFIG, iterations_per_conditional=0)
        _, _, diag = fitting.fit(np.empty((len(values), 0)), values, np.zeros(len(values)), np.ones(len(values)), 'bounded_likelihood', config)
        self.assertEqual(diag['status'], 'iteration_limit')
        self.assertGreater(diag['final_gradient_infinity'], CONFIG['gradient_infinity_tolerance'])

    def test_current_density_parity(self):
        previous = c.rc.fit(self.x, 2, 'fixed_partition_gaussian_mixture', 'response_public_mode_scale')
        current = c.fit(self.x, 'current', 'moment_projection', CONFIG)
        np.testing.assert_allclose(current.logpdf(self.x), previous.logpdf(self.x), atol=2e-9)
        self.assertEqual(current.numeric_bytes, previous.numeric_bytes)

    def test_replication_serialization_support_and_storage(self):
        for chart in ['current', 'specialized']:
            msg = c.fit(self.x, chart, 'moment_projection', CONFIG)
            repeated = c.fit(np.tile(self.x, (2, 1)), chart, 'moment_projection', CONFIG)
            np.testing.assert_allclose(msg.logpdf(self.x[:32]), repeated.logpdf(self.x[:32]), atol=2e-9)
            restored = c.Message.restore(json.loads(json.dumps(msg.export())))
            np.testing.assert_array_equal(msg.logpdf(self.x[:32]), restored.logpdf(self.x[:32]))
            self.assertEqual(msg.numeric_bytes, 2496)
            samples, _ = restored.draw(1024, 801)
            c.old.to_unit(samples)
            self.assertTrue(np.isfinite(restored.logpdf(samples)).all())


if __name__ == '__main__':
    unittest.main()
