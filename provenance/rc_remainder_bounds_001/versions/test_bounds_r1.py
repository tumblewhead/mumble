import unittest
from fractions import Fraction as F
from math import factorial
import numpy as np
from . import check as c


class BoundsTests(unittest.TestCase):
    def test_exact_polynomial_identities(self):
        p, q = c.polynomials()
        for n in [3, 4]:
            self.assertEqual(p[n], c.P[n])
            self.assertEqual(q[n], c.Q[n])
        for n in range(1, 5):
            derivative = [(k+1)*q[n][k+1] for k in range(len(q[n])-1)]+[0]
            self.assertEqual([a-b for a, b in zip(q[n], derivative)], p[n])
            self.assertEqual(sum(a*factorial(k) for k, a in enumerate(p[n])), 0)

    def test_rational_certificates_and_rejections(self):
        for n in [3, 4]:
            self.assertTrue(c.certificate(n)['exact_rational_comparisons_passed'])
            with self.assertRaises(ValueError):
                c.certificate(n, upper=(F(0), F(0)))
            with self.assertRaises(ValueError):
                c.certificate(n, brackets=[(1, 2)]*n)
        self.assertEqual(c.exp_negative(F(0)), (F(1), F(1)))
        with self.assertRaises(ValueError):
            c.exp_negative(F(50))

    def test_chronological_derivatives_against_suffix_expression(self):
        rng = np.random.default_rng(1103)
        dt = rng.choice([0., 1/100, 1/35, .25, 1.2], 80)
        current = rng.uniform(-.12, .12, 80)
        q = c.polynomials()[1]
        for tau in [.02, .7, 16.]:
            free, forced = c.response(dt, current, tau)
            for stop in range(1, len(dt)+1):
                right = np.cumsum(dt[:stop][::-1])[::-1]/tau
                left = right-dt[:stop]/tau
                direct = np.array([sum(current[:stop]*(np.exp(-left)*c.value(qn, left)
                                                       -np.exp(-right)*c.value(qn, right))) for qn in q])
                np.testing.assert_allclose(forced[stop-1], direct, atol=2e-14, rtol=3e-11)
            _, constant = c.response(dt, np.full(80, .12), tau)
            want = -.12*free
            want[:, 0] += .12
            np.testing.assert_allclose(constant, want, atol=2e-14, rtol=3e-11)
            for n in [3, 4]:
                a, b = map(float, c.UPPER[n])
                self.assertLessEqual(max(abs(free[:, n])), a)
                self.assertLessEqual(max(abs(forced[:, n])), .12*b)

    def test_public_response_bounds(self):
        p = c.public_probe()
        self.assertEqual(len(p['queries']), 7)
        self.assertLess(max(p['queries'][0]['branch_value_error_V']), 1e-14)
        self.assertLess(max(p['queries'][0]['branch_slope_error_V']), 1e-14)

    def test_likelihood_and_joint_precision_transport(self):
        rng = np.random.default_rng(20261102)
        for _ in range(30):
            # Dense shared geometry, not a diagonal or scalar surrogate.
            j = rng.normal(size=(31, 7))
            d = .015*rng.normal(size=(31, 7))
            residual = rng.normal(size=31)
            err = .002*rng.normal(size=31)
            prior_root = rng.normal(size=(7, 7))
            prior = prior_root.T@prior_root+.1*np.eye(7)
            p = j.T@j+prior
            phat = (j+d).T@(j+d)+prior
            ev, vec = np.linalg.eigh(p)
            invroot = (vec*(1/np.sqrt(ev)))@vec.T
            eta = np.linalg.norm(d@invroot, 2)
            eps = 2*eta+eta*eta
            self.assertLess(eps, 1)
            w = invroot@(phat-p)@invroot
            self.assertLessEqual(np.linalg.norm(w, 2), eps+1e-13)
            delta = .5*((residual+err)@(residual+err)-residual@residual)
            self.assertAlmostEqual(delta, residual@err+.5*(err@err), places=12)
            self.assertLessEqual(abs(delta), sum(abs(residual)*abs(err)+err*err/2)+1e-13)
            gradient = rng.normal(size=7)
            perturbation = .01*rng.normal(size=7)
            q, h = np.linalg.norm(invroot@gradient), np.linalg.norm(invroot@perturbation)
            variance = (gradient+perturbation)@np.linalg.solve(phat, gradient+perturbation)
            self.assertLessEqual(max(0, q-h)**2/(1+eps), variance+1e-13)
            self.assertGreaterEqual((q+h)**2/(1-eps), variance-1e-13)

    def test_gaussian_counterexample(self):
        cases = c.accumulation_example()['cases']
        self.assertEqual(cases[1]['log_odds_second_vs_first'], -.063)
        self.assertLess(cases[2]['log_odds_second_vs_first'], -500)


if __name__ == '__main__':
    unittest.main()
