#!/usr/bin/env python3
"""Fabricated numerical qualification only. Never opens canonical data or truth."""
import copy
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest

import numpy as np
import shape as s


class ShapeTests(unittest.TestCase):
    def fixture(self, coupled=False):
        x = np.zeros(16)
        x[5], x[11] = math.log(.06), .5
        sd = np.array([.1] * 11 + [.05] + [.01] * 3 + [.2])
        a = np.eye(16)
        if coupled:
            v = np.arange(1., 17.) / 20
            a += np.outer(v, v)
        metric = a / np.outer(sd, sd)
        lo, hi = np.full(16, -10.), np.full(16, 10.)
        design = s.make_design(x, metric, sd, lo, hi, 0., 0., 0.)
        return design, x, metric, sd, lo, hi

    def rows(self, design, offset=0., dg=None, dh=None):
        basis = np.array(design['basis_original_x_units'])
        x0 = np.array(design['anchor'])
        g = np.arange(1., 17.) / 100
        h = np.eye(16) * 2
        h[2, 9] = h[9, 2] = .25
        dg = np.zeros(16) if dg is None else dg
        dh = np.zeros((16, 16)) if dh is None else dh
        out = []
        for node in design['nodes']:
            w = np.linalg.solve(basis, np.array(node['x']) - x0)
            ref = 10_000. + g @ w + .5 * w @ h @ w
            rep = ref + offset + dg @ w + .5 * w @ dh @ w
            out.append(dict(id=node['id'], x=node['x'], status='available',
                            represented_likelihood_cost=float(rep), reference_likelihood_cost=float(ref),
                            represented_cost_allowance=0., reference_cost_allowance=0.))
        return out

    def test_01_count_and_determinism(self):
        d, *_ = self.fixture()
        self.assertEqual(len(d['nodes']), 545)
        self.assertEqual(d, self.fixture()[0])
        self.assertEqual(len({n['id'] for n in d['nodes']}), 545)

    def test_02_coupled_whitening(self):
        d, _, metric, *_ = self.fixture(True)
        b = np.array(d['basis_original_x_units'])
        np.testing.assert_allclose(b.T @ metric @ b, np.eye(16), atol=2e-14)
        self.assertGreater(np.count_nonzero(np.abs(b) > 1e-12), 16)

    def test_03_constant_offset_cancels(self):
        d, *_ = self.fixture(True)
        out = s.compare(d, self.rows(d, offset=-5894.936088744114))
        self.assertEqual(out['decision'], 'keep_on_tested_points_only')
        self.assertLess(out['centered_error_oscillation_NLL'], 1e-9)
        self.assertLess(out['anchor_represented_minus_reference_NLL'], -5000)

    def test_04_recovers_complete_quadratic(self):
        d, *_ = self.fixture(True)
        out = s.compare(d, self.rows(d))
        expected_h = np.eye(16) * 2
        expected_h[2, 9] = expected_h[9, 2] = .25
        for level in out['reference_second_differences']:
            np.testing.assert_allclose(level['gradient_whitened'], np.arange(1., 17.) / 100, atol=2e-10)
            np.testing.assert_allclose(level['symmetric_second_difference_matrix_whitened'], expected_h, atol=2e-10)

    def test_05_cross_coupling_axes_alone_miss(self):
        d, *_ = self.fixture()
        dh = np.zeros((16, 16)); dh[5, 11] = dh[11, 5] = 1
        out = s.compare(d, self.rows(d, dh=dh))
        axis_errors = [r['centered_discrepancy_NLL'] for r in out['per_node'] if '_axis_' in r['id']]
        self.assertLess(max(map(abs, axis_errors)), 1e-12)
        self.assertEqual(out['decision'], 'repair_computed_shape_witness')
        for level in out['discrepancy_second_differences']:
            np.testing.assert_allclose(level['symmetric_second_difference_matrix_whitened'], dh, atol=2e-10)

    def test_06_linear_bias_is_not_curvature(self):
        d, *_ = self.fixture(True)
        dg = np.zeros(16); dg[5] = .2
        out = s.compare(d, self.rows(d, dg=dg))
        self.assertEqual(out['decision'], 'repair_computed_shape_witness')
        for level in out['discrepancy_second_differences']:
            np.testing.assert_allclose(level['gradient_whitened'], dg, atol=2e-10)
            np.testing.assert_allclose(level['symmetric_second_difference_matrix_whitened'], 0, atol=2e-10)

    def test_07_large_allowance_is_unresolved(self):
        d, *_ = self.fixture()
        rows = self.rows(d)
        for row in rows:
            row['represented_cost_allowance'] = .1
        self.assertEqual(s.compare(d, rows)['decision'], 'unresolved')

    def test_08_missing_node_cannot_pass(self):
        d, *_ = self.fixture()
        rows = self.rows(d)
        rows[7].update(status='unavailable', reason='endpoint invalid')
        out = s.compare(d, rows)
        self.assertEqual(out['decision'], 'unresolved')
        self.assertEqual(out['available_nodes'], 544)
        self.assertNotIn('reference_second_differences', out)

    def test_09_resolved_partial_witness_still_repairs(self):
        d, *_ = self.fixture()
        dg = np.ones(16)
        rows = self.rows(d, dg=dg)
        rows[7].update(status='unavailable', reason='endpoint invalid')
        self.assertEqual(s.compare(d, rows)['decision'], 'repair_computed_shape_witness')

    def test_10_anchor_unavailable_rejected(self):
        d, *_ = self.fixture(); rows = self.rows(d)
        rows[0].update(status='unavailable', reason='missing anchor')
        with self.assertRaises(s.ContractError):
            s.compare(d, rows)

    def test_11_node_identity_and_point_are_binding(self):
        d, *_ = self.fixture(); rows = self.rows(d)
        rows[1], rows[2] = rows[2], rows[1]
        with self.assertRaises(s.ContractError):
            s.compare(d, rows)
        rows = self.rows(d); rows[1]['x'] = list(rows[1]['x']); rows[1]['x'][0] += .01
        with self.assertRaises(s.ContractError):
            s.compare(d, rows)

    def test_12_nonfinite_cost_and_negative_allowance_rejected(self):
        d, *_ = self.fixture()
        for key, value in [('reference_likelihood_cost', float('nan')), ('reference_cost_allowance', -1)]:
            rows = self.rows(d); rows[1][key] = value
            with self.assertRaises(s.ContractError):
                s.compare(d, rows)

    def test_13_bad_metric_is_not_repaired(self):
        _, x, metric, sd, lo, hi = self.fixture()
        for change in ('indefinite', 'asymmetric', 'nonfinite'):
            m = metric.copy()
            if change == 'indefinite': m[0, 0] = -1
            elif change == 'asymmetric': m[0, 1] += 1
            else: m[0, 0] = np.nan
            with self.assertRaises(s.ContractError):
                s.make_design(x, m, sd, lo, hi, 0., 0., 0.)

    def test_14_support_only_global_halving(self):
        _, x, metric, sd, lo, hi = self.fixture()
        hi[7], lo[7] = .02, -.02
        d = s.make_design(x, metric, sd, lo, hi, 0., 0., 0.)
        self.assertEqual(d['support_only_halvings'], 3)
        self.assertEqual(d['radii'], [.125, .0625])
        xx = np.array([n['x'] for n in d['nodes']])
        self.assertTrue(s.common_support(xx, lo, hi, 0., 0.))

    def test_15_boundary_anchor_has_no_symmetric_stencil(self):
        _, x, metric, sd, lo, hi = self.fixture(); x[11] = 0.
        with self.assertRaises(s.ContractError):
            s.make_design(x, metric, sd, lo, hi, 0., 0., 0.)

    def test_16_horizon_and_count_binding(self):
        d, *_ = self.fixture(); rows = self.rows(d)
        bad = copy.deepcopy(d); bad['prefix'] = 504000
        with self.assertRaises(s.ContractError): s.compare(bad, rows)
        with self.assertRaises(s.ContractError): s.compare(d, rows[:-1])

    def test_17_derived_soc_uses_original_entering_chart(self):
        _, x, metric, sd, lo, hi = self.fixture()
        d = s.make_design(x, metric, sd, lo, hi, 0., .003, .003)
        node = next(n for n in d['nodes'] if n['id'] == 'r0_axis_05_p')
        xx = node['x']
        expected = 100 * (xx[11] - .003 / math.exp(xx[5]) - (x[11] - .003 / math.exp(x[5])))
        self.assertAlmostEqual(node['current_SOC_relative_anchor_pp'], expected)
        self.assertNotEqual(expected, 0)

    def test_18_capture_requires_real_hash_bound_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'bank.bin'
            path.write_bytes(b'fabricated unit-test checkpoint, not estimator state')
            c = dict(schema='mumble_fixed_prefix_capture_v1', prefix=s.PREFIX,
                     base_revision=s.BASE, observations_sha256=s.OBS_SHA, trace_sha256=s.TRACE_SHA,
                     snapshot_scope='pointer_free_host_ABI_bank_inputs_calibration',
                     snapshot_bytes=path.stat().st_size, snapshot_sha256=s.file_sha(path),
                     reconstruction=dict(method='commit_only', optimizer_calls=0, truth_reads=0,
                                         records=s.PREFIX, blocks=s.PREFIX//16,
                                         checked_snapshots=s.PREFIX//16+1, parity='bitwise'))
            s.validate_capture(c, path)
            path.write_bytes(b'changed')
            with self.assertRaises(s.ContractError): s.validate_capture(c, path)
            path.unlink()
            with self.assertRaises(s.ContractError): s.validate_capture(c, path)

    def test_19_missing_capture_and_optimizer_replay_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'missing'
            with self.assertRaises(s.ContractError): s.validate_capture({'anchor': [0]*16}, path)

    def test_20_output_exclusive_and_strict_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'result.json'
            s.save_new(path, {'state': 'first'})
            before = s.file_sha(path)
            with self.assertRaises(FileExistsError): s.save_new(path, {'state': 'second'})
            self.assertEqual(before, s.file_sha(path))
            path.write_text('{"value": NaN}')
            with self.assertRaises(s.ContractError): s.load(path)

    def test_21_packed_order_and_unexcited_quantities_remain_joint(self):
        d, _, metric, *_ = self.fixture(True)
        packed = [metric[i, j] for i in range(16) for j in range(i+1)]
        np.testing.assert_array_equal(s.unpack_metric(packed), metric)
        labels = {n['direction'] for n in d['nodes'] if n['level'] == 0}
        self.assertEqual(len(labels), 136)
        self.assertIn('pair_05_15', labels)
        self.assertIn('pair_11_15', labels)


if __name__ == '__main__':
    unittest.main(verbosity=2)
