"""Focused mathematical, uncertainty, ownership and provenance controls."""
import copy
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(ROOT))
from forecast import exp_roots, path, predict, segments
from scoring import score
from support import Phases
from experiments.foster_campaign_001.backend import prepare_c
from experiments.foster_campaign_001.coordinates import prior
from experiments.foster_feedback_001.estimator import Model


class ForecastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.config = json.loads((ROOT/'experiments/foster_feedback_001/calibration.json').read_text())
        cls.config['hysteresis_chart'] = 'bounded'
        binary, _ = prepare_c(Path(cls.tmp.name), 50, cls.config)
        cls.model = Model(binary.resolve(), cls.config)
        cls.x, _ = prior(cls.config)
        cls.L = np.eye(16)*.001
        cls.task = dict(segments=[dict(duration_s=.1, current_A=.12), dict(duration_s=1, current_A=0)])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_all_exponential_roots(self):
        # (exp(-t)-.2)(exp(-t)-.5)(exp(-t)-.8)
        roots = exp_roots([-.08, .66, -1.5, 1], [0, 1, 2, 3], 3.)
        np.testing.assert_allclose(roots, sorted(-np.log([.2, .5, .8])), atol=3e-14, rtol=0)
        self.assertEqual(exp_roots([0, 0], [0, 1], 10), [])
        self.assertEqual(exp_roots([1, -1], [1, 1], 10), [])

    def test_fast_between_sample_minimum(self):
        x = self.x.copy()
        x[1:4] = [-.01, .03, 0.]
        x[[8, 10, 12]] = np.log([.05, .45, 4.5])
        task = dict(segments=[dict(duration_s=1, current_A=0)])
        result = path(x, segments(task, 1), self.config, 25, 1, grid=True)
        self.assertAlmostEqual(result['minimum_time_s'], math.log(.2/.06)/18, places=13)
        self.assertGreater(result['sample_grid_minimum_excess_V'], .001)

    def test_edges_and_explicit_rounding(self):
        result = path(self.x, segments(self.task, 50), self.config, 25, 50, grid=True)
        edge = np.flatnonzero(result['dt'] == 0)
        self.assertEqual(len(edge), 2)
        self.assertEqual(result['times'][edge[1]], .1)
        self.assertEqual(result['times'][edge[1]-1], .1)
        self.assertAlmostEqual(result['voltage'][edge[1]]-result['voltage'][edge[1]-1], .12*math.exp(self.x[6]))
        s = segments(self.task, 35)[0]
        self.assertEqual(s['duration_s'], 4/35)
        self.assertNotEqual(s['rounding_s'], 0)

    def test_C_scalar_agreement_at_three_temperatures(self):
        x = self.x.copy()
        x[:5] = [.64, -.002, .003, -.001, np.arctanh(.2)]
        task = dict(segments=[dict(duration_s=1, current_A=-.06),
                              dict(duration_s=.1, current_A=.12), dict(duration_s=1, current_A=0)])
        for T in (17, 25, 33):
            result = predict(self.model, x, self.L, task, self.config, T, 50)
            self.assertLess(result['closed_form_C_max_difference_V'], 3e-14)
            self.assertEqual(len(result['probes']), 64)

    def test_full_cross_covariance_is_preserved(self):
        # OCV(z) and polarization cancel exactly at the initial current edge.
        L = np.zeros((16, 16))
        L[0, 0] = .002
        L[1, 0] = .002*self.config['ocv_slope_V_per_SOC']
        result = predict(self.model, self.x, L, self.task, self.config, 25, 50)
        diagonal = np.diag(np.sqrt(np.sum(L*L, axis=1)))
        independent = predict(self.model, self.x, diagonal, self.task, self.config, 25, 50)
        self.assertLess(result['local_sd_V'][0], 1e-15)
        self.assertGreater(independent['local_sd_V'][0], .003)

    def test_support_failures_are_not_dropped(self):
        L = self.L.copy()
        L[0, 0] = 1.
        result = predict(self.model, self.x, L, self.task, self.config, 25, 50)
        self.assertEqual(len(result['probes']), 64)
        self.assertEqual(result['unsupported_probes'], 4)
        self.assertTrue(all('reason' in p for p in result['probes'] if p['status'] == 'unresolved'))

    def test_forecast_does_not_change_inputs(self):
        x, L, task = self.x.copy(), self.L.copy(), copy.deepcopy(self.task)
        predict(self.model, x, L, task, self.config, 25, 50)
        np.testing.assert_array_equal(x, self.x)
        np.testing.assert_array_equal(L, self.L)
        self.assertEqual(task, self.task)

    def test_nonlinear_transport_and_rejection(self):
        # A nonlinear map changes probes; the local derivative gives identical
        # endpoint covariance at the expansion point. Unsupported directions stay.
        calls = []
        def transport(x):
            calls.append(x.copy())
            if x[0] > self.x[0]+.0025:
                raise ValueError('test original-history support')
            out = x.copy()
            out[1] += (x[0]-self.x[0])**2
            D = np.eye(16)
            D[1, 0] = 2*(x[0]-self.x[0])
            return out, D
        result = predict(self.model, self.x, self.L, self.task, self.config, 25, 50, transport=transport)
        self.assertEqual(result['unsupported_probes'], 1)
        self.assertGreater(len(calls), 64)

    def test_joint_local_uncertainty_matches_finite_difference(self):
        result = predict(self.model, self.x, self.L, self.task, self.config, 25, 50)
        # The endpoint voltage occurs at a fixed task boundary, so no moving
        # argmin or differing extrema grids enter this finite-difference check.
        grad = []
        for j in range(16):
            step = np.eye(16)[j]*1e-5
            plus = path(self.x+step, segments(self.task, 50), self.config, 25, 50)['recovery_V']
            minus = path(self.x-step, segments(self.task, 50), self.config, 25, 50)['recovery_V']
            grad.append((plus-minus)/2e-5)
        expected = np.linalg.norm(np.array(grad)@self.L)
        self.assertAlmostEqual(result['local_sd_V'][-1], expected, places=11)

    def test_truth_only_changes_scoring(self):
        prediction = predict(self.model, self.x, self.L, self.task, self.config, 25, 50)
        before = prediction['voltage'].copy()
        from forecast import parameters
        state = np.r_[self.x[:4], np.tanh(self.x[4])]
        p = parameters(self.x, self.config, 25)
        a = score(prediction, state, p, self.task, self.config, 25, 50, self.x)
        state[0] += .01
        b = score(prediction, state, p, self.task, self.config, 25, 50, self.x)
        self.assertLess(abs(a['minimum_error_V']), 1e-13)
        self.assertGreater(abs(b['minimum_error_V']), .01)
        np.testing.assert_array_equal(prediction['voltage'], before)

    def test_invalid_tasks_fail_before_model(self):
        for bad in (dict(segments=[dict(duration_s=-1, current_A=.1)]),
                    dict(segments=[dict(duration_s=1, current_A=1)])):
            with self.assertRaises(ValueError):
                predict(self.model, self.x, self.L, bad, self.config, 25, 50)


class ProfileTests(unittest.TestCase):
    def test_partial_campaign_is_not_reported_complete(self):
        from run import summarize
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            self.assertEqual(summarize(out, [], 1, 12)['status'], 'running')
            one = [dict(directory='missing', exit_code=0, result={})]
            self.assertEqual(summarize(out, one, 1, 12)['status'], 'running')
            self.assertEqual(summarize(out, one, 1, 1)['status'], 'completed_diagnostic')
            one[0]['exit_code'] = 1
            self.assertEqual(summarize(out, one, 1, 1)['status'], 'partial_or_failed')

    def test_nested_exclusive_timings_and_failure_cleanup(self):
        phases = Phases()
        def child():
            raise ValueError('test')
        wrapped = phases.wrap(child, 'child')
        parent = phases.wrap(wrapped, 'parent')
        with self.assertRaises(ValueError):
            parent()
        self.assertEqual(phases.stack, [])
        self.assertGreaterEqual(phases.times['parent'][0], phases.times['child'][0])
        self.assertAlmostEqual(phases.exclusive['parent'][0]+phases.times['child'][0], phases.times['parent'][0])


if __name__ == '__main__':
    unittest.main()
