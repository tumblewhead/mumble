import unittest
import numpy as np
from experiments.backward_response_001 import algebra as a
from experiments.joint_health_posterior_001.model import initial_draw
from experiments.region_compression_001.regions import stationary_probe


class Controls(unittest.TestCase):
    def setUp(self):
        self.x = initial_draw(np.random.default_rng(20261030), 64)

    def test_general_partition(self):
        for steps in [[], [[.05, .2]], [[-.05, .4]], [[0., .5]], [[.03, .2], [0., .7], [-.02, .4]]]:
            voltage, valid = stationary_probe(self.x, steps)
            self.assertTrue(valid.all())
            np.testing.assert_allclose(a.terms(self.x, steps).sum(1), voltage, atol=2e-12, rtol=0)

    def test_reversal_closed_and_OCV_cancellation(self):
        steps = [[.05, 1.]]*10+[[-.05, 1.]]*10
        out = a.terms(self.x, steps)
        np.testing.assert_allclose(out[:, 1], 0., atol=2e-14, rtol=0)
        np.testing.assert_allclose(a.reversal_closed(self.x, .05, 10.), stationary_probe(self.x, steps)[0], atol=2e-12, rtol=0)

    def test_directional_inverse_jacobian(self):
        H, h = self.x[:, 10], self.x[:, 15]
        U, D = a.directional_amplitudes(H, h)
        recovered = a.directional_inverse(U, D)
        np.testing.assert_allclose(recovered[0], H, atol=2e-17, rtol=0)
        np.testing.assert_allclose(recovered[1], h, atol=3e-16, rtol=0)
        step = 1e-6
        dH = (np.array(a.directional_amplitudes(H+step, h))-np.array(a.directional_amplitudes(H-step, h)))/(2*step)
        dh = (np.array(a.directional_amplitudes(H, h+step))-np.array(a.directional_amplitudes(H, h-step)))/(2*step)
        determinant = dH[0]*dh[1]-dH[1]*dh[0]
        np.testing.assert_allclose(determinant, -2*H, atol=2e-11, rtol=0)

    def test_prior_curvature(self):
        k = a.c.old.kernel
        for j in [3, 4]:
            for gamma in [10., 100., 700.]:
                step = gamma*1e-3
                fd = (a.prior_log_density_shape(gamma+step,k.MEAN[j],k.SD[j])-
                      2*a.prior_log_density_shape(gamma,k.MEAN[j],k.SD[j])+
                      a.prior_log_density_shape(gamma-step,k.MEAN[j],k.SD[j]))/step**2
                self.assertAlmostEqual(fd, a.prior_log_curvature(gamma,k.MEAN[j],k.SD[j]), delta=1e-8)

    def test_mean_covariance_identity_and_pooling(self):
        values = a.terms(self.x, [[.05, .7], [-.05, .9]])
        stats = a.moments(values)
        pooled = a.pool([a.moments(values[:20]), a.moments(values[20:])])
        np.testing.assert_allclose(stats['mean'], pooled['mean'], atol=2e-15, rtol=0)
        np.testing.assert_allclose(stats['covariance'], pooled['covariance'], atol=2e-16, rtol=0)
        self.assertAlmostEqual(stats['covariance'].sum(), values.sum(1).var(), delta=2e-16)
        delta = a.contrast(stats, a.moments(values*.99))
        self.assertAlmostEqual(sum(delta['group_variance_contributions_V2'].values()), delta['variance_difference_V2'], delta=2e-16)


if __name__ == '__main__':
    unittest.main()
