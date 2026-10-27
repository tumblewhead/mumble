#!/usr/bin/env python3
"""One finite, fabricated-only qualification. Invocation reserves attempt001.

This harness never opens observations, saved anchors, historical results or truth.
The shared library is the candidate plus field access only; the oracle uses full
16D forward AD of the physical equations and direct polynomial residual sums.
"""
import ctypes as C
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import subprocess
import sys
import time
import traceback

import independent_oracle as oracle

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EXP = HERE.parent
PLAN = HERE / 'independent_plan.json'
ATTEMPT = HERE / 'attempt001'
N = 16


def identity(path):
    b = path.read_bytes()
    return {'path': str(path.relative_to(ROOT)), 'bytes': len(b),
            'sha256': hashlib.sha256(b).hexdigest()}


def save_new(path, value):
    b = (json.dumps(value, indent=2, allow_nan=False) + '\n').encode()
    with path.open('xb') as f:
        f.write(b)
        f.flush()
        os.fsync(f.fileno())
    return identity(path)


class Endpoint(C.Structure):
    _fields_ = [('SOC', C.c_double), ('v', C.c_double * 3), ('h', C.c_double),
                ('min_support_slack', C.c_double), ('min_endpoint_slack', C.c_double)]


class Step(C.Structure):
    _fields_ = [(name, C.c_double) for name in
                ('slope', 'slope_allowance', 'model_decrease', 'model_allowance',
                 'cost_decrease', 'cost_allowance', 'armijo_required',
                 'combine_allowance', 'alpha')]


class Detail(C.Union):
    _fields_ = [('endpoint', Endpoint), ('step', Step)]


class Result(C.Structure):
    _fields_ = [('likelihood_cost', C.c_double), ('prior_cost', C.c_double),
                ('total_cost', C.c_double), ('cost_absolute_scale', C.c_double),
                ('flags', C.c_uint32), ('stop_reason', C.c_uint32),
                ('detail', Detail), ('round', C.c_uint32), ('fraction', C.c_uint32)]


class Qualification:
    def __init__(self, lib, plan):
        self.lib, self.plan = lib, plan
        self.checks, self.records = 0, []
        self.current = None
        self.activity = dict(c_prepare_attempts=0, c_push_attempts=0,
                             independent_AD_physical_steps=0, independent_scalar_physical_steps=0,
                             c_query_evaluations=0, c_prior_evaluations=0, c_QR_insertions=0,
                             c_refinement_calls=0, c_refinement_rounds=0,
                             independent_prior_algebra_evaluations=0,
                             canonical_observation_reads=0, historical_candidate_numeric_reads=0,
                             truth_reads=0, learner_calls=0, canonical_replays=0)
        lib.qa_size.argtypes = [C.c_uint]
        lib.qa_size.restype = C.c_size_t
        ptr, dp, up = C.c_void_p, C.POINTER(C.c_double), C.POINTER(C.c_ubyte)
        signatures = {
            'ch_init': ([ptr, up, dp], C.c_int),
            'ch_prepare': ([ptr, up, C.c_uint64], C.c_int),
            'ch_push': ([ptr, up, C.c_uint64], C.c_int),
            'ch_query': ([ptr, C.c_int, C.c_int, C.c_int], C.c_int),
            'ch_endpoint': ([ptr], C.c_int),
            'qa_sample': ([ptr, C.c_double, C.c_double, C.c_double], None),
            'qa_point': ([ptr, dp], None), 'qa_estimate': ([ptr, dp], None),
            'qa_factor': ([ptr, dp], None),
            'qa_read': ([ptr, C.c_uint, dp], None),
            'qa_result': ([ptr, C.POINTER(Result)], None),
            'qa_count': ([ptr, C.c_uint], C.c_uint64),
            'qa_last_error': ([ptr], C.c_int), 'qa_jet_equal': ([ptr], C.c_int)}
        for name, (args, result) in signatures.items():
            f = getattr(lib, name)
            f.argtypes, f.restype = args, result
        self.callback_type = C.CFUNCTYPE(None, ptr, ptr)
        lib.ch_refine.argtypes = [ptr, C.c_uint, self.callback_type, ptr]
        lib.ch_refine.restype = C.c_int
        self.source = (C.c_ubyte * 32)(*range(32))
        self.wrong_source = (C.c_ubyte * 32)(*([99] * 32))
        self.mean = list((C.c_double * N).in_dll(lib, 'ch_public_mean'))
        self.sd = list((C.c_double * N).in_dll(lib, 'ch_public_sd'))
        self.lo = list((C.c_double * N).in_dll(lib, 'ch_lower'))
        self.hi = list((C.c_double * N).in_dll(lib, 'ch_upper'))
        pair_bytes = list((C.c_ubyte * 40).in_dll(lib, 'ch_pair'))
        self.pairs = list(zip(pair_bytes[0::2], pair_bytes[1::2]))
        p = plan['fixed_base_point']
        self.base = [math.log(v) for v in p['first_six_natural_values']] + p['remaining_original_coordinates']
        self.scales = plan['comparison_scales']
        self.fixture_results = {}

    def check(self, ok, label, **evidence):
        self.checks += 1
        if self.current is not None:
            self.current['assertions'] += 1
        if not ok:
            raise AssertionError(json.dumps({'check': label, **evidence}, allow_nan=False))

    def close(self, actual, reference, tolerance, label, scale=1.0):
        error = abs(actual - reference) * scale
        limit = tolerance * max(1.0, abs(reference * scale))
        self.check(math.isfinite(actual) and math.isfinite(reference) and error <= limit,
                   label, actual=actual, reference=reference, error=error, allowance=limit)
        ratio = error / limit if limit else 0.0
        if ratio > self.current.get('maximum_error_over_allowance', 0.0):
            self.current['maximum_error_over_allowance'] = ratio
            self.current['maximum_error_label'] = label

    @staticmethod
    def array(x):
        return (C.c_double * len(x))(*x)

    def context(self, origin=None):
        c = C.create_string_buffer(self.lib.qa_size(0))
        rc = self.lib.ch_init(c, self.source, self.array(self.base if origin is None else origin))
        self.check(rc == 0, 'fabricated initialization', status=rc)
        return c

    def read(self, c, what, n):
        a = (C.c_double * n)()
        self.lib.qa_read(c, what, a)
        return list(a)

    def result(self, c):
        r = Result()
        self.lib.qa_result(c, C.byref(r))
        return r

    def counts(self, c):
        return [self.lib.qa_count(c, i) for i in range(8)]

    def count_operation(self, c, call):
        before = self.counts(c)
        rc = call()
        after = self.counts(c)
        for key, index in (('c_query_evaluations', 2), ('c_prior_evaluations', 3),
                           ('c_QR_insertions', 1), ('c_refinement_rounds', 4)):
            self.activity[key] += after[index] - before[index]
        return rc

    def push(self, c, index, sample, source=None):
        self.lib.qa_sample(c, *sample)
        self.activity['c_push_attempts'] += 1
        return self.count_operation(c, lambda: self.lib.ch_push(c, self.source if source is None else source, index))

    def prepare(self, c, index, sample):
        self.lib.qa_sample(c, *sample)
        self.activity['c_prepare_attempts'] += 1
        return self.lib.ch_prepare(c, self.source, index)

    def query(self, c, point, kind=2, curvature=2, prior=0):
        self.lib.qa_point(c, self.array(point))
        return self.count_operation(c, lambda: self.lib.ch_query(c, kind, curvature, prior))

    def bank(self, c, ignore_query_prior=False):
        data = bytearray(C.string_at(c, self.lib.qa_size(1)))
        if ignore_query_prior:
            for field in (11, 12):
                offset = self.lib.qa_size(field)
                data[offset:offset + 8] = b'\x00' * 8
        return bytes(data)

    def samples(self, name):
        f = self.plan['physical_fixtures'][name]
        return [(a, b, self.plan['physical_fixture_voltage_V'])
                for a, b in zip(f['dt_s'], f['current_A'])]

    def signed_jet(self, name):
        point = list(self.base)
        if name == 'zero_H_boundary_h':
            point[10], point[15] = 0.0, 1.0
        samples = self.samples(name)
        refs = oracle.physical_ad(point, samples)
        self.activity['independent_AD_physical_steps'] += len(samples)
        self.check({tuple(sorted(p)) for p in self.pairs} ==
                   {tuple(sorted(p)) for p in self.plan['expected_nonzero_lower_Hessian_pairs']},
                   'exact sparse pair set')
        allowed = {tuple(sorted(p)) for p in self.pairs}
        c = self.context(point)
        rows = []
        for index, (sample, ref) in enumerate(zip(samples, refs)):
            before = self.bank(c)
            self.check(self.prepare(c, index, sample) == 0, 'prepare succeeds')
            self.check(self.bank(c) == before, 'prepare does not consume evidence')
            row = self.read(c, 0, 37)
            rows.append(row)
            voltage = ref[0]
            self.close(row[36] * .001 + sample[2], voltage.v,
                       self.plan['numerical_gates']['AD_value_relative_to_max_1'], 'voltage')
            for i in range(16):
                self.close(row[i] * .001 / self.sd[i], voltage.g[i],
                           self.plan['numerical_gates']['AD_scaled_gradient_Hessian_relative_to_max_1'],
                           f'gradient_{i}', self.scales[i])
            for k, (i, j) in enumerate(self.pairs):
                h = row[16 + k] * .001 / (self.sd[i] * self.sd[j]) * (2.0 if i == j else 1.0)
                self.close(h, voltage.h[i * N + j],
                           self.plan['numerical_gates']['AD_scaled_gradient_Hessian_relative_to_max_1'],
                           f'hessian_{i}_{j}', self.scales[i] * self.scales[j])
            for i in range(N):
                for j in range(i + 1):
                    if tuple(sorted((i, j))) not in allowed:
                        self.check(voltage.h[i * N + j] == 0.0,
                                   'structural Hessian zero', row=i, column=j)
            self.check(self.push(c, index, sample) == 0, 'push succeeds')
            self.check(self.lib.qa_jet_equal(c) == 1, 'prospective and committed jet agree')
            self.lib.qa_point(c, self.array(point))
            self.check(self.lib.ch_endpoint(c) == 0, 'origin endpoint succeeds')
            endpoint = self.result(c).detail.endpoint
            for actual, expected in zip([endpoint.SOC, *endpoint.v, endpoint.h],
                                        [ref[1].v, *(v.v for v in ref[2]), ref[3].v]):
                self.close(actual, expected, self.plan['numerical_gates']['AD_value_relative_to_max_1'], 'endpoint')
        self.fixture_results[name] = (point, samples, refs, rows, c)
        self.current['records'] = len(samples)

    def finite_difference(self):
        point, samples, refs, _, _ = self.fixture_results['mixed']
        ref = refs[-1][0]
        h = 2.0 ** -7
        for which in (0, 1):
            d = [self.scales[i] * ((i + 1) if which == 0 else (-1) ** i * (17 - i)) / 16
                 for i in range(N)]
            values = {}
            for k in (-2, -1, 0, 1, 2):
                values[k] = oracle.physical_scalar([point[i] + k * h * d[i] for i in range(N)], samples)
                self.activity['independent_scalar_physical_steps'] += len(samples)
            first = (values[-2] - 8 * values[-1] + 8 * values[1] - values[2]) / (12 * h)
            second = (-values[2] + 16 * values[1] - 30 * values[0] + 16 * values[-1] - values[-2]) / (12 * h * h)
            first_ref = math.fsum(ref.g[i] * d[i] for i in range(N))
            second_ref = math.fsum(ref.h[i * N + j] * d[i] * d[j] for i in range(N) for j in range(N))
            self.close(first, first_ref, self.plan['numerical_gates']['directional_first_relative_to_max_1'], 'five-point first')
            self.close(second, second_ref, self.plan['numerical_gates']['directional_second_relative_to_max_1'], 'five-point second')

    def points(self, origin=None):
        a = self.base if origin is None else origin
        return [list(a), [a[i] + .1 * self.scales[i] * ((i - 7.5) / 8) for i in range(N)],
                [a[i] - .1 * self.scales[i] * ((-1) ** i) * (i + 1) / 16 for i in range(N)]]

    def triangular(self, mode='quartic'):
        rows = [[0.0] * 37 for _ in range(37)]
        for i in range(37):
            for j in range(i, 37):
                rows[i][j] = .25 + (i % 5) / 32 if i == j else (((i + 3) * (j + 5)) % 17 - 8) / 256
                if mode == 'affine' and 16 <= j < 36:
                    rows[i][j] = 0.0
                if mode == 'zero' or (mode == 'rank_deficient' and (i % 3 != 0 or j in (2, 5, 11, 15))):
                    rows[i][j] = 0.0
        return rows

    def set_factor(self, c, rows):
        packed = [rows[i][j] for i in range(37) for j in range(i, 37)]
        self.lib.qa_factor(c, self.array(packed))

    def compare_objective(self, c, point, origin, rows, kind):
        reference, gn = oracle.polynomial(point, origin, self.sd, self.pairs, rows, kind)
        self.check(self.query(c, point, kind, 2, 0) == 0, 'query succeeds')
        result, grad, packed = self.result(c), self.read(c, 1, 16), self.read(c, 2, 136)
        tol = self.plan['numerical_gates']['QR_cost_gradient_Hessian_relative_to_max_1']
        self.close(result.likelihood_cost, reference.v, tol, 'QR cost')
        for i in range(N):
            self.close(grad[i], reference.g[i], tol, f'QR gradient_{i}', self.scales[i])
            for j in range(i + 1):
                self.close(packed[i * (i + 1) // 2 + j], reference.h[i * N + j], tol,
                           f'QR Hessian_{i}_{j}', self.scales[i] * self.scales[j])
        return reference, gn

    def affine(self):
        c = self.context()
        rows = self.triangular('affine')
        self.set_factor(c, rows)
        for point in self.points():
            self.compare_objective(c, point, self.base, rows, 1)
        origin, _, _, physical_rows, physical = self.fixture_results['mixed']
        for point in self.points(origin):
            self.compare_objective(physical, point, origin, physical_rows, 1)

    def quartic(self):
        c = self.context()
        rows = self.triangular()
        self.set_factor(c, rows)
        found_cross_term = False
        for point in self.points():
            ref, gn = self.compare_objective(c, point, self.base, rows, 2)
            found_cross_term |= any(abs(a - b) > 1e-8 for a, b in zip(ref.h, gn))
            self.check(self.query(c, point, 2, 1, 0) == 0, 'GN query succeeds')
            packed = self.read(c, 2, 136)
            for i in range(N):
                for j in range(i + 1):
                    self.close(packed[i * (i + 1) // 2 + j], gn[i * N + j],
                               self.plan['numerical_gates']['QR_cost_gradient_Hessian_relative_to_max_1'],
                               'GN kept distinct', self.scales[i] * self.scales[j])
        self.check(found_cross_term, 'fabricated residual-Hessian cross term is nonzero')
        origin, _, _, physical_rows, physical = self.fixture_results['mixed']
        self.compare_objective(physical, self.points(origin)[1], origin, physical_rows, 2)

    def deficient(self):
        for mode in ('zero', 'rank_deficient'):
            c, rows = self.context(), self.triangular(mode)
            self.set_factor(c, rows)
            self.compare_objective(c, self.points()[1], self.base, rows, 2)

    def chronology(self):
        c, sample = self.context(), (.1, .03, 3.6)
        before = self.bank(c)
        self.check(self.push(c, 0, sample, self.wrong_source) == -2, 'wrong source rejects')
        self.check(self.bank(c) == before, 'wrong source unchanged')
        self.check(self.push(c, 1, sample) == -3, 'skipped index rejects')
        self.check(self.bank(c) == before, 'skipped index unchanged')
        self.check(self.push(c, 0, sample) == 0, 'first original sample accepted')
        once = self.bank(c)
        self.check(self.push(c, 0, sample) == -3, 'duplicate index rejects')
        self.check(self.bank(c) == once, 'duplicate cannot add evidence')
        self.check(self.push(c, 1, sample) == 0, 'next original sample accepted')
        self.check(self.counts(c)[:2] == [2, 2] and self.counts(c)[6] == 2,
                   'cursor/model/QR exactly once')

    def input_support(self):
        c = self.context()
        before = self.bank(c)
        bad_point = list(self.base)
        bad_point[15] = 1.01
        self.check(self.lib.ch_init(c, self.source, self.array(bad_point)) < 0, 'unsupported initialization')
        self.check(self.bank(c) == before, 'failed initialization does not change bank')
        for sample in ((-.01, .03, 3.6), (1.01, .03, 3.6), (.1, .251, 3.6),
                       (float('nan'), .03, 3.6), (.1, .03, float('inf'))):
            self.check(self.push(c, 0, sample) < 0, 'invalid interval/current/voltage rejected')
            self.check(self.bank(c) == before, 'prevalidation leaves bank unchanged')
        self.check(self.query(c, bad_point) < 0, 'unsupported query')
        self.check(self.bank(c) == before, 'unsupported query consumes no evidence/evaluation')

    def fault(self):
        c = self.context()
        rows = [[0.0] * 37 for _ in range(37)]
        for i in range(37):
            rows[i][i] = sys.float_info.max
        self.set_factor(c, rows)
        before = self.bank(c)
        rc = self.push(c, 0, (.1, .03, 1.0e305))
        after = self.bank(c)
        self.check(rc < 0, 'oversized-factor fault surfaced', status=rc)
        self.check(after == before or self.counts(c)[7] == 0, 'mutation requires unavailable latch')
        if after != before:
            self.check(self.query(c, self.base) == -6, 'query rejects unavailable factor')
            self.check(self.push(c, 0, (.1, .03, 3.6)) == -6, 'ingest rejects unavailable factor')
            source = (EXP / 'compact_history.c').read_text()
            refine = source[source.index('int ch_refine('):]
            self.check('if(!c->bank.available)return CH_ERR_UNAVAILABLE;' in refine,
                       'refinement unavailable guard checked statically to retain one-refine-call budget')
        self.current['fault_status'] = rc
        self.current['factor_changed'] = after != before
        self.current['available_after_fault'] = bool(self.counts(c)[7])

    def query_ownership(self):
        _, _, _, _, c = self.fixture_results['mixed']
        before = self.bank(c, True)
        for point in self.points():
            self.check(self.query(c, point, 2, 2, 1) == 0, 'joint query with one exact prior')
            self.check(self.lib.ch_endpoint(c) == 0, 'read-only endpoint')
            self.check(self.bank(c, True) == before, 'query cannot duplicate/recenter carried evidence')

    def prior(self):
        c = self.context(self.mean)
        points = [list(self.mean), list(self.mean), list(self.mean)]
        points[1][5], points[2][5] = -3.0907210901048416, -2.536100343415231
        tol = self.plan['numerical_gates']['QR_cost_gradient_Hessian_relative_to_max_1']
        negative_seen = False
        for point in points:
            ref, majorizer = oracle.public_prior(point, self.mean, self.sd)
            self.activity['independent_prior_algebra_evaluations'] += 1
            self.check(self.query(c, point, 2, 2, 1) == 0, 'exact mixture query')
            result, grad, packed = self.result(c), self.read(c, 1, 16), self.read(c, 2, 136)
            self.close(result.prior_cost, ref.v, tol, 'whole-mixture prior cost')
            self.check(result.flags & 4 and not result.flags & 8, 'exact prior label')
            for i in range(N):
                self.close(grad[i], ref.g[i], tol, 'prior gradient', self.scales[i])
                for j in range(i + 1):
                    self.close(packed[i * (i + 1) // 2 + j], ref.h[i * N + j], tol,
                               'prior Hessian', self.scales[i] * self.scales[j])
            negative_seen |= ref.h[5 * N + 5] < 0.0
            self.check(self.query(c, point, 2, 1, 2) == 0, 'majorizer query')
            result, grad, packed = self.result(c), self.read(c, 1, 16), self.read(c, 2, 136)
            self.close(result.prior_cost, ref.v, tol, 'majorizer preserves exact cost')
            self.check(result.flags & 4 and result.flags & 8, 'majorizer explicit label')
            for i in range(N):
                self.close(grad[i], ref.g[i], tol, 'majorizer preserves exact gradient', self.scales[i])
                for j in range(i + 1):
                    self.close(packed[i * (i + 1) // 2 + j], majorizer[i] if i == j else 0.0,
                               tol, 'majorizer is P inverse', self.scales[i] * self.scales[j])
        self.check(negative_seen, 'exact mixture curvature is not universally positive')

    def refine(self):
        c = self.context(self.mean)
        rows = [[0.0] * 37 for _ in range(37)]
        for i in range(16):
            rows[i][i] = 32.0
        self.set_factor(c, rows)
        entering = [self.mean[i] + .05 * self.sd[i] for i in range(N)]
        self.lib.qa_estimate(c, self.array(entering))
        self.check(self.query(c, entering, 2, 1, 1) == 0, 'initial fabricated objective')
        before_cost = self.result(c).total_cost
        before_factor, before_origin, before_counts = self.read(c, 3, 703), self.read(c, 4, 16), self.counts(c)
        trace = []

        @self.callback_type
        def callback(pointer, _):
            r = self.result(pointer)
            trace.append({'round': int(r.round), 'fraction': int(r.fraction),
                          'flags': int(r.flags), 'point': self.read(pointer, 6, 16),
                          'cost': r.total_cost,
                          **{name: getattr(r.detail.step, name) for name, _ in Step._fields_}})

        self.activity['c_refinement_calls'] += 1
        rc = self.count_operation(c, lambda: self.lib.ch_refine(c, 2, callback, None))
        stop = int(self.result(c).stop_reason)
        self.check(rc == 1 and stop in (1, 2, 3, 4, 5), 'finite explicit unresolved stop', status=rc, stop=stop)
        estimate = self.read(c, 5, 16)
        self.check(self.query(c, estimate, 2, 1, 1) == 0, 'final fabricated objective')
        after_cost = self.result(c).total_cost
        self.check(after_cost < before_cost, 'fabricated refinement decreases same-prior sketch')
        accepted = [event for event in trace if event['fraction'] != 2**32 - 1 and event['flags'] & 16]
        self.check(len(accepted) == self.counts(c)[5] - before_counts[5] and len(accepted) > 0,
                   'accepted trace and installed generations agree')
        last = entering
        for event in accepted:
            self.check(event['slope'] > event['slope_allowance'] and
                       event['model_decrease'] > event['model_allowance'], 'direction arithmetic admitted')
            self.check(event['cost_decrease'] - event['cost_allowance'] >
                       event['armijo_required'] + event['combine_allowance'], 'guarded sketch Armijo decrease')
            self.check(max(abs((event['point'][i] - last[i]) / self.sd[i]) for i in range(N)) <= 1,
                       'represented accepted step respects one public SD')
            last = event['point']
        self.check(last == estimate, 'only accepted points installed')
        self.check(self.read(c, 3, 703) == before_factor and self.read(c, 4, 16) == before_origin,
                   'refinement never changes factor or approximation origin')
        self.check(self.counts(c)[0:2] == before_counts[0:2] and self.counts(c)[6] == before_counts[6],
                   'refinement no model/QR/cursor advance')
        self.current.update({'status_code': rc, 'stop_reason': stop, 'initial_cost': before_cost,
                             'final_cost': after_cost, 'trace': trace,
                             'interpretation': 'Surrogate-only feasible decrease; no nonlinear convergence or uncertainty claim.'})

    def layout(self):
        names = ('context', 'bank', 'jet', 'workspace', 'result', 'operational_layout',
                 'model_state', 'sample', 'workspace_offset', 'result_offset', 'sample_offset')
        sizes = {name: int(self.lib.qa_size(i)) for i, name in enumerate(names)}
        self.check(sizes['result'] == C.sizeof(Result), 'bridge result ABI')
        self.check(sizes['context'] <= 8112 and sizes['workspace'] == 1600, 'single core and full phase liveness')
        self.check(sizes['operational_layout'] == sizes['context'] + 448 + 128, 'ADC and codec separately allocated')
        total = sizes['operational_layout'] + 768 + 768
        self.check(total <= 10224, 'complete declared whole-system ledger', total=total)
        nm = subprocess.run(['nm', '-u', str(ATTEMPT / 'compact_history.o')], text=True,
                            capture_output=True, check=True).stdout
        forbidden = {'malloc', 'calloc', 'realloc', 'free', 'alloca'}
        symbols = [line.split()[-1] for line in nm.splitlines() if line.split()]
        self.check(not forbidden.intersection(symbols), 'candidate has no heap references')
        usage = {}
        for path in (ATTEMPT / 'compact_history.su', ATTEMPT / 'scm_model.su'):
            for line in path.read_text().splitlines():
                fields = line.split('\t')
                function = fields[0].rsplit(':', 1)[-1].split('.')[0]
                self.check(fields[2] == 'static', 'compiler reports bounded static frame', function=function)
                usage[function] = max(usage.get(function, 0), int(fields[1]))
        # Conservative project-call graph: it sums tail-call frames too. Inlined
        # helpers are already in the containing emitted frame; libm/IRQ/caller
        # are explicitly separate, unmeasured allocations in the target ledger.
        children = {'ch_refine': ['ch_query', 'ch_endpoint', 'point_support', 'row_derivative', 'add_prior'],
                    'ch_query': ['ch_endpoint', 'point_support', 'row_derivative', 'add_prior', 'feature'],
                    'ch_endpoint': ['point_support'], 'ch_push': ['advance_jet'],
                    'ch_prepare': ['advance_jet'], 'advance_jet': ['scm_ocv_eval'],
                    'ch_init': ['scm_model_init'], 'scm_ocv_eval': ['scm_ocv_validate']}

        def depth(name):
            return usage.get(name, 0) + max([depth(k) for k in children.get(name, [])] or [0])

        depths = {name: depth(name) for name in ('ch_init', 'ch_push', 'ch_prepare', 'ch_query', 'ch_endpoint', 'ch_refine')}
        self.check(max(depths.values()) <= 768, 'conservative emitted project call-chain stack')
        self.current.update({'sizeof_and_offsets': sizes, 'ledger_total_bytes': total,
                             'headroom_to_10240_bytes': 10240 - total,
                             'undefined_symbols': symbols, 'emitted_frames_bytes': usage,
                             'conservative_call_chain_bytes': depths,
                             'target_limit': 'Host compiler/layout only; Cortex-M23 libm/software FP, ISR, ADC, codec and target stack/timing remain unmeasured.'})

    def run(self):
        operations = [lambda: self.signed_jet('zero_current'), lambda: self.signed_jet('positive'),
                      lambda: self.signed_jet('negative'), lambda: self.signed_jet('mixed'),
                      lambda: self.signed_jet('zero_H_boundary_h'), self.finite_difference,
                      self.affine, self.quartic, self.deficient, self.chronology, self.input_support,
                      self.fault, self.query_ownership, self.prior, self.refine, self.layout]
        for case, operation in zip(self.plan['fixed_cases'], operations):
            record = {'id': case['id'], 'name': case['name'], 'assertions': 0, 'status': 'running'}
            self.current = record
            try:
                operation()
                record['status'] = 'passed'
            except Exception as exc:
                record['status'], record['error'] = 'failed', str(exc)
                record['traceback'] = traceback.format_exc(limit=4)
            self.records.append(record)
            save_new(ATTEMPT / ('case%02d.json' % case['id']), record)
        self.current = None
        activity = self.activity
        activity['fabricated_model_steps_conservative'] = (activity['c_prepare_attempts'] + activity['c_push_attempts']
             + activity['independent_AD_physical_steps'] + activity['independent_scalar_physical_steps'])
        bounds = self.plan['hard_activity_bounds']
        self.check(activity['fabricated_model_steps_conservative'] <= bounds['fabricated_model_steps_max'], 'model count cap')
        self.check(activity['c_QR_insertions'] <= bounds['synthetic_QR_row_insertions_max'], 'QR count cap')
        self.check(activity['c_query_evaluations'] <= bounds['query_evaluations_max'], 'query count cap')
        self.check(activity['c_refinement_calls'] == 1 and activity['c_refinement_rounds'] <= 2, 'one bounded refinement')
        return {'cases': self.records, 'assertions': self.checks, 'activity': activity,
                'passed_cases': sum(r['status'] == 'passed' for r in self.records),
                'failed_cases': sum(r['status'] != 'passed' for r in self.records)}


def main():
    wall_start = time.monotonic()
    ATTEMPT.mkdir(exist_ok=False)
    plan = json.loads(PLAN.read_bytes())
    limit = plan['finite_resources']
    resource.setrlimit(resource.RLIMIT_CPU, (30, 31))
    resource.setrlimit(resource.RLIMIT_AS, (limit['address_space_bytes_max'],) * 2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (limit['retained_output_bytes_max'],) * 2)
    sources = [PLAN, HERE / 'bridge.c', HERE / 'independent_oracle.py', Path(__file__).resolve(),
               EXP / 'compact_history.c', EXP / 'compact_history.h', ROOT / 'src/scm_model.c',
               ROOT / 'include/scm_model.h', HERE / 'amendments/original_plan.json',
               HERE / 'amendments/fixture_alignment.json']
    freeze = {'schema': 'compact_history_independent_pre_execution_freeze_v1',
              'qualification_invocations_before_freeze': 0,
              'sources': [identity(p) for p in sources],
              'interpreter': {'path': sys.executable, 'version': sys.version},
              'compiler': subprocess.run(['cc', '--version'], text=True, capture_output=True, check=True).stdout,
              'scope': 'Fabricated only. No canonical input path is accepted.'}
    save_new(ATTEMPT / 'source_freeze.json', freeze)
    result = {'schema': 'compact_history_independent_qualification_v1', 'status': 'failed',
              'qualification_invocations': 1, 'retry': False, 'source_freeze': identity(ATTEMPT / 'source_freeze.json')}
    try:
        flags = ['cc', '-std=c99', '-O3', '-Wall', '-Wextra', '-Werror', '-fno-fast-math',
                 '-ffp-contract=off', '-fPIC', '-fstack-usage', '-I' + str(ROOT / 'include'), '-I' + str(EXP)]
        commands, objects = [], []
        for source, name in ((EXP / 'compact_history.c', 'compact_history'),
                             (ROOT / 'src/scm_model.c', 'scm_model'), (HERE / 'bridge.c', 'bridge')):
            obj = ATTEMPT / (name + '.o')
            command = flags + ['-c', str(source), '-o', str(obj)]
            p = subprocess.run(command, capture_output=True, text=True, timeout=20)
            commands.append({'command': command, 'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr})
            if p.returncode != 0:
                raise RuntimeError('Compilation failed: ' + p.stderr)
            objects.append(obj)
        library = ATTEMPT / 'candidate.so'
        command = ['cc', '-shared', *map(str, objects), '-lm', '-o', str(library)]
        p = subprocess.run(command, capture_output=True, text=True, timeout=20)
        commands.append({'command': command, 'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr})
        if p.returncode != 0:
            raise RuntimeError('Shared-library link failed: ' + p.stderr)
        save_new(ATTEMPT / 'build.json', {'commands': commands, 'library': identity(library)})
        qa = Qualification(C.CDLL(str(library)), plan)
        details = qa.run()
        result.update(details)
        result['status'] = 'passed' if details['passed_cases'] == 16 and details['failed_cases'] == 0 else 'failed'
    except Exception as exc:
        result['error'] = str(exc)
        result['traceback'] = traceback.format_exc(limit=8)
    result['sources_unchanged'] = all(identity(path) == expected for path, expected in zip(sources, freeze['sources']))
    if not result['sources_unchanged']:
        result['status'] = 'failed'
    own, children = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    result['resources'] = {'CPU_s_including_compiler_children': own.ru_utime + own.ru_stime + children.ru_utime + children.ru_stime,
                           'wall_s_before_final_receipt': time.monotonic() - wall_start,
                           'own_peak_RSS_bytes': own.ru_maxrss * 1024,
                           'compiler_children_peak_RSS_bytes': children.ru_maxrss * 1024,
                           'scope': 'Includes compilation and one in-process fabricated qualification; final receipt close excluded from timing snapshot.'}
    if (result['resources']['CPU_s_including_compiler_children'] > limit['CPU_s_max'] or
        result['resources']['wall_s_before_final_receipt'] > limit['wall_s_max'] or
        max(own.ru_maxrss, children.ru_maxrss) * 1024 > limit['process_RSS_bytes_max']):
        result['status'], result['resource_violation'] = 'failed', True
    result['manifest'] = [identity(p) for p in sorted(ATTEMPT.iterdir()) if p.is_file()]
    result['closed_output_bytes_including_receipt'] = 0
    other_bytes = sum(x['bytes'] for x in result['manifest'])
    for _ in range(8):
        total = other_bytes + len((json.dumps(result, indent=2, allow_nan=False) + '\n').encode())
        if total == result['closed_output_bytes_including_receipt']:
            break
        result['closed_output_bytes_including_receipt'] = total
    if total > limit['retained_output_bytes_max']:
        result['status'], result['resource_violation'] = 'failed', True
    save_new(ATTEMPT / 'receipt.json', result)
    print(json.dumps({'status': result['status'], 'passed_cases': result.get('passed_cases'),
                      'failed_cases': result.get('failed_cases'), 'assertions': result.get('assertions'),
                      'activity': result.get('activity'), 'resources': result['resources'],
                      'receipt': identity(ATTEMPT / 'receipt.json')}, allow_nan=False))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
