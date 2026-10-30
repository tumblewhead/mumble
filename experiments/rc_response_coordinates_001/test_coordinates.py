import json
import math
import unittest
import numpy as np
from experiments.rc_response_coordinates_001 import coordinates as c
from experiments.rc_response_coordinates_001.probes import definitions


class Controls(unittest.TestCase):
    def setUp(self):
        self.rng = np.random.default_rng(391028)
        self.x = c.old.LOW+c.old.WIDTH*self.rng.uniform(.15, .85, (1024, 16))
        self.frames = ['physical_amplitude_control', 'response_1s', 'response_public_mode_scale']

    def test_roundtrip_all_frames_and_atlas(self):
        for frame in self.frames:
            values = c.frame_values(frame)
            for interval in [None, (0., 1.)]:
                y, _, _ = c.encode(self.x, values, interval)
                np.testing.assert_allclose(c.decode(y, values, interval), self.x, atol=2e-15, rtol=1e-14)

    def test_full16_jacobian(self):
        x = self.x[:1]
        for frame in self.frames:
            values = c.frame_values(frame)
            for interval in [None, (0., 1.)]:
                jac = np.empty((16, 16))
                for j in range(16):
                    step = 1e-6*c.old.WIDTH[j]
                    left, right = x.copy(), x.copy()
                    left[0, j] += step
                    right[0, j] -= step
                    jac[:, j] = (c.encode(left, values, interval)[0][0]-c.encode(right, values, interval)[0][0])/(2*step)
                expected = c.encode(x, values, interval)[2][0]
                self.assertAlmostEqual(np.linalg.slogdet(jac)[1], expected, places=7)

    def test_RC_composition_across_horizons(self):
        for frame in self.frames:
            y, a, _ = c.encode(self.x, c.frame_values(frame))
            for dt in [1/35, .1, 1., 10.]:
                exposure = dt/np.exp(self.x[:, :3])
                ratio = -np.expm1(-exposure)/a
                for current in [0., .05, -.05]:
                    predicted = ratio*(y[:, 9:12]-current*y[:, 12:15])
                    direct = self.x[:, 12:15]-(np.exp(-exposure)*self.x[:, 12:15]-np.expm1(-exposure)*self.x[:, 7:10]*current)
                    np.testing.assert_allclose(predicted, direct, atol=1e-16)

    def test_dependent_bounds(self):
        for frame in self.frames:
            y, a, _ = c.encode(self.x, c.frame_values(frame))
            for step in range(7):
                lo, hi = c.chain_bounds(self.x, a, step)
                self.assertTrue(np.all((y[:, 9+step] > lo) & (y[:, 9+step] < hi)))
        a = c.attenuation(self.x, np.ones(3))
        self.assertGreater(np.ptp(a[:, 2]), .1)

    def test_chain_matches_joint_gaussian_before_support_correction(self):
        x = self.x
        for frame in self.frames:
            msg = c.fit(x, 1, 'fixed_partition_gaussian_mixture', frame)
            y, _, jac = c.encode(x, msg.frame)
            delta = y-y.mean(0)
            packed = c.old.pack_factor(delta.T @ delta/len(y))
            joint = c.old.gaussian_logpdf(y, y.mean(0), packed)
            actual, logz = msg.logpdf_details(x)
            np.testing.assert_allclose(actual+logz.sum(1)-jac, joint, atol=2e-10)

    def test_replication_serialization_and_payload(self):
        for arm in ['fixed_partition_gaussian_mixture', 'fixed_probability_atlas', 'adaptive_probability_atlas']:
            a = c.fit(self.x, 2, arm, 'response_public_mode_scale')
            b = c.fit(np.tile(self.x, (2, 1)), 2, arm, 'response_public_mode_scale')
            np.testing.assert_allclose(a.logpdf(self.x[:32]), b.logpdf(self.x[:32]), atol=2e-10)
            restored = c.Message.restore(json.loads(json.dumps(a.export())))
            np.testing.assert_array_equal(a.logpdf(self.x[:32]), restored.logpdf(self.x[:32]))
            self.assertEqual(a.numeric_bytes, 2496 if 'mixture' in arm else 2512)
            draw, _ = a.draw(2048, 193)
            c.old.to_unit(draw)
            self.assertTrue(np.isfinite(a.logpdf(draw)).all())

    def test_chain_conditional_normalization(self):
        msg = c.fit(self.x, 1, 'fixed_partition_gaussian_mixture', 'response_public_mode_scale')
        reg = msg.regions[0]
        y, a, _ = c.encode(self.x[:1], msg.frame)
        nodes, weights = np.polynomial.legendre.leggauss(256)
        for step in range(7):
            lo, hi = c.chain_bounds(self.x[:1], a, step)
            coef = c.coefficients(reg, step)
            mu = coef[0]+y[:, :9+step] @ coef[1:]
            sd = np.exp(reg['chain_logsd'][step])
            t = (lo+hi)/2+(hi-lo)*nodes/2
            logz = c.v.log_mass((lo-mu)/sd, (hi-mu)/sd)
            integral = np.sum(weights*(hi-lo)/2*np.exp(-.5*((t-mu)/sd)**2-.5*c.old.LOG2PI-np.log(sd)-logz))
            self.assertAlmostEqual(integral, 1., delta=2e-11)

    def test_probe_intervals_and_chronology(self):
        probes = definitions([1/35, .1, 1., 10.])
        self.assertEqual(sum(len(p['steps']) for p in probes), 52)
        for p in probes[1:]:
            self.assertTrue(all(0 < step[1] <= 1 for step in p['steps']))
            scale = 2 if p['profile'] == 'reversal' else 1
            self.assertAlmostEqual(sum(s[1] for s in p['steps']), scale*p['horizon_s'])
        long = next(p for p in probes if p['name']=='reversal_10s')
        self.assertEqual([s[0] for s in long['steps']], [.05]*10+[-.05]*10)

    def test_frame_domains(self):
        np.testing.assert_array_equal(c.frame_values('response_public_mode_scale'), np.exp((c.old.LOW[:3]+c.old.HIGH[:3])/2))
        with self.assertRaises(c.old.Unavailable):
            c.attenuation(self.x, np.array([-1., 1., 1.]))


if __name__ == '__main__':
    unittest.main()
