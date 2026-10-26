#!/usr/bin/env python3
"""Post-inference, streaming scores for the frozen continuous-learning study.

This module never imports or invokes an estimator, generator, optimizer or RNG.
Truth and learner outputs meet only here. Reducer storage is independent of the
number of samples; full-query scores are streamed to a deterministic gzip file.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import math
import struct
from contextlib import ExitStack
from pathlib import Path

METRIC = struct.Struct('<Q7dQiI')
TRUTH = struct.Struct('<Qddd')
OBSERVATION = struct.Struct('<Qddd')
RATE = 35
DT = 1.0 / RATE
AVAIL_SOC, AVAIL_Q, AVAIL_CAUSAL, AVAIL_POSTFIT = 1, 2, 4, 8
BAD_FLAGS = (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4)
KNOWN_FLAGS = (1 << 6) - 1
NAMES = ['tau1_s', 'tau2_s', 'tau3_s', 'gamma_plus_per_Ah',
         'gamma_minus_per_Ah', 'Q_Ah', 'R0_ohm', 'R1_ohm', 'R2_ohm',
         'R3_ohm', 'H_V', 'SOC', 'v1_V', 'v2_V', 'v3_V', 'h']


class ScoringError(ValueError):
    pass


class OutputLimitError(ScoringError):
    pass


class OutputBudget:
    """Shared cap on actual output bytes, including gzip framing and summary."""
    FAILURE_RESERVE = 4096

    def __init__(self, limit):
        if type(limit) is not int or limit < self.FAILURE_RESERVE:
            raise ScoringError('max_output_bytes must reserve at least4096 failure bytes')
        self.limit, self.used = limit, 0

    def write(self, stream, block, *, failure=False):
        ceiling = self.limit if failure else self.limit - self.FAILURE_RESERVE
        if len(block) > ceiling - self.used:
            raise OutputLimitError('Scoring output allowance reached before write')
        written = stream.write(block)
        if written is None:
            written = len(block)
        self.used += written
        if written != len(block):
            raise OSError('Short scoring artifact write')
        return written


class CappedBinary:
    """Minimal gzip file object; compressed writes share the arm allowance."""
    def __init__(self, stream, budget):
        self.stream, self.budget = stream, budget

    def write(self, block):
        return self.budget.write(self.stream, block)

    def flush(self):
        self.stream.flush()

    def tell(self):
        return self.stream.tell()


def finite(x):
    return type(x) in (int, float) and math.isfinite(x)


def clean_json(x):
    if isinstance(x, float) and not math.isfinite(x):
        return None
    if isinstance(x, dict):
        return {k: clean_json(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean_json(v) for v in x]
    return x


def dumps(x):
    return json.dumps(clean_json(x), allow_nan=False, separators=(',', ':'))


def file_identity(path):
    p = Path(path)
    h = hashlib.sha256()
    with p.open('rb') as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return {'path': str(p), 'bytes': p.stat().st_size, 'sha256': h.hexdigest()}


class Sum:
    """Neumaier accumulation without retaining summands."""
    __slots__ = ('s', 'c')

    def __init__(self):
        self.s = self.c = 0.0

    def add(self, x):
        t = self.s + x
        self.c += (self.s - t) + x if abs(self.s) >= abs(x) else (x - t) + self.s
        self.s = t

    def value(self):
        return self.s + self.c


def stamp(index, elapsed=None, epoch=0):
    return {'next_index': index, 'nominal_time_s': index / RATE,
            'actual_elapsed_s': elapsed,
            'nominal_time_since_epoch_s': (index - epoch) / RATE}


class ErrorStats:
    __slots__ = ('n', 'weight', 'total', 'square', 'peak', 'peak_at', 'first', 'last')

    def __init__(self):
        self.n = 0
        self.weight, self.total, self.square = Sum(), Sum(), Sum()
        self.peak = None
        self.peak_at = self.first = self.last = None

    def add(self, error, weight, at):
        if not finite(error) or not finite(weight) or weight <= 0:
            return
        self.n += 1
        self.weight.add(weight)
        self.total.add(weight * error)
        self.square.add(weight * error * error)
        point = {'signed_error': error, **at}
        if self.first is None:
            self.first = point
        self.last = point
        if self.peak is None or abs(error) > self.peak:
            self.peak, self.peak_at = abs(error), point

    def result(self, weight_kind='interval_seconds'):
        w = self.weight.value()
        return {'finite_samples': self.n, 'weight_kind': weight_kind, 'weight': w,
                'signed_mean': self.total.value() / w if w else None,
                'RMS': math.sqrt(max(0.0, self.square.value() / w)) if w else None,
                'maximum_absolute_error': self.peak, 'first_peak': self.peak_at,
                'first': self.first, 'last': self.last}


class Target:
    """Useful target hits; unavailable/invalid samples cannot pass."""
    def __init__(self, limit):
        self.limit = limit
        self.observed = self.passed = self.outside = self.unavailable = 0
        self.first_hit = self.tail_start = self.last_failure = None
        self.not_met_run = self.outside_run = self.unavailable_run = 0
        self.max_not_met = self.max_outside = self.max_unavailable = 0

    def add(self, error, available, at):
        self.observed += 1
        good = available and finite(error)
        passed = good and abs(error) <= self.limit
        if passed:
            self.passed += 1
            if self.first_hit is None:
                self.first_hit = at
            if self.tail_start is None:
                self.tail_start = at
            self.not_met_run = 0
        else:
            self.tail_start = None
            self.last_failure = at
            self.not_met_run += 1
            self.max_not_met = max(self.max_not_met, self.not_met_run)
        if not good:
            self.unavailable += 1
            self.unavailable_run += 1
            self.max_unavailable = max(self.max_unavailable, self.unavailable_run)
        else:
            self.unavailable_run = 0
        if good and not passed:
            self.outside += 1
            self.outside_run += 1
            self.max_outside = max(self.max_outside, self.outside_run)
        else:
            self.outside_run = 0

    def result(self, required, complete, entry=None, retention=False):
        entry_pass = (entry is not None and entry.get('learned', True)
                      and entry['available'] and finite(entry['error'])
                      and abs(entry['error']) <= self.limit)
        first_hit = entry['at'] if entry_pass else self.first_hit
        sustained = self.tail_start if complete else None
        if complete and self.passed == required and entry_pass:
            sustained = entry['at']
        if not complete:
            classification = 'incomplete_window'
        elif retention and not entry_pass:
            classification = 'not_acquired_at_entry'
        elif retention:
            classification = 'retained' if self.passed == required else 'retention_failed'
        else:
            classification = 'sustained_through_finite_endpoint' if sustained else 'not_sustained_at_finite_endpoint'
        return {'threshold': self.limit, 'classification': classification,
                'required_interval_samples': required, 'observed_interval_samples': self.observed,
                'unobserved_interval_samples': max(0, required - self.observed),
                'passed_samples': self.passed,
                'pass_fraction_all_required_intervals': self.passed / required if required else None,
                'first_observed_hit': first_hit,
                'first_interval_end_hit': self.first_hit,
                'all_later_required_samples_pass_from': sustained,
                'observed_prefix_tail_pass_from': self.tail_start,
                'last_violating_or_unavailable': self.last_failure,
                'entry_pass': entry_pass if entry is not None else None,
                'available_outside_target_samples': self.outside,
                'available_outside_target_duration_s': self.outside * DT,
                'longest_available_outside_target_duration_s': self.max_outside * DT,
                'unavailable_samples': self.unavailable,
                'unavailable_duration_s': self.unavailable * DT,
                'longest_unavailable_duration_s': self.max_unavailable * DT,
                'longest_observed_not_met_duration_s': self.max_not_met * DT,
                'denominator_scope': 'Interval-end samples only; retention entry is a separate required point with zero duration.',
                'sustained_scope': 'Only through the declared completed finite window; never eventual convergence.'}


class Quantity:
    def __init__(self, hard, preferred):
        self.raw = ErrorStats()
        self.available = ErrorStats()
        self.targets = {'hard': Target(hard), 'preferred': Target(preferred)}
        self.entry = None
        self.last = None

    def set_entry(self, error, available, at, learned=True):
        self.entry = {'error': error if finite(error) else None,
                      'available': bool(available and finite(error)), 'at': at,
                      'learned': bool(learned)}

    def add(self, error, available, dt, at):
        self.raw.add(error, dt, at)
        if available:
            self.available.add(error, dt, at)
        self.last = {'error': error if finite(error) else None,
                     'available': bool(available and finite(error)), 'at': at}
        for target in self.targets.values():
            target.add(error, available, at)

    def result(self, required, complete, retention):
        return {'raw_finite_point_errors': self.raw.result(),
                'available_current_point_errors': self.available.result(),
                'entry': self.entry, 'last_observed': self.last,
                'targets': {k: t.result(required, complete, self.entry, retention) for k, t in self.targets.items()}}


class Window:
    def __init__(self, name, begin, end, targets, retention=False):
        self.name, self.begin, self.end, self.retention = name, begin, end, retention
        self.n = 0
        self.last_index = None
        self.quantities = {'SOC_pp': Quantity(**targets['SOC_error_pp']),
                           'Q_percent': Quantity(**targets['capacity_error_percent'])}
        self.voltage = {k: ErrorStats() for k in ['causal_clean_mV', 'noisy_innovation_mV', 'filtered_fit_clean_mV']}
        self.charge = {k: Sum() for k in ['signed_Ah', 'positive_Ah', 'negative_magnitude_Ah', 'absolute_Ah']}
        self.charge_samples = 0

    def feed(self, index, elapsed, errors, avail, voltage, dt, current, epoch,
             entry_is_learned=True):
        at = stamp(index, elapsed, epoch)
        if index == self.begin:
            for name, q in self.quantities.items():
                q.set_entry(errors[name], avail[name], at, entry_is_learned)
            return
        if not (self.begin < index <= self.end):
            return
        self.n += 1
        self.last_index = index
        for name, q in self.quantities.items():
            q.add(errors[name], avail[name], dt, at)
        for name, value in voltage.items():
            self.voltage[name].add(value, dt, at)
        if current is not None:
            d = current * dt / 3600
            for name, value in [('signed_Ah', d), ('positive_Ah', max(d, 0)),
                                ('negative_magnitude_Ah', max(-d, 0)), ('absolute_Ah', abs(d))]:
                self.charge[name].add(value)
            self.charge_samples += 1

    def result(self, valid_through_index=None):
        all_observed = self.n == self.end - self.begin and self.last_index == self.end
        complete = all_observed and (valid_through_index is None or self.end <= valid_through_index)
        return {'start_index': self.begin, 'end_index': self.end,
                'start_nominal_s': self.begin / RATE, 'end_nominal_s': self.end / RATE,
                'completed_declared_window': complete, 'retention_window': self.retention,
                'all_required_intervals_observed': all_observed,
                'validity_verified_through_index': valid_through_index,
                'observed_samples': self.n,
                'quantities': {k: q.result(self.end - self.begin, complete, self.retention)
                               for k, q in self.quantities.items()},
                'voltage': {k: s.result() for k, s in self.voltage.items()},
                'charge': {**{k: s.value() if self.charge_samples else None for k, s in self.charge.items()},
                           'observed_samples': self.charge_samples}}


def make_windows(plan, cell, start, end):
    targets = plan['measurements']['targets']
    spec = [('whole_arm', start, end, False)]
    if cell == 'cell_b':
        for name, times in plan['B_continuous_4h']['analysis_windows'].items():
            spec.append((name, int(times[0] * RATE), int(times[1] * RATE), name in ['first_retention', 'final_retention']))
        for p in plan['B_continuous_4h']['phases']:
            spec.append(('phase:' + p['id'], p['start_index'], p['end_index'],
                         p['id'] in ['retention_rest', 'retention_weak', 'final_weak_retention']))
    else:
        spec += [('prompt_after_arm_entry', start, min(end, start + 600 * RATE), False),
                 ('weak_tail', 1800 * RATE, 2100 * RATE, True)]
    # Do not clip a requested retention window into a false completed claim.
    return [Window(name, a, b, targets, retain) for name, a, b, retain in spec
            if a >= start and b <= end and b > a]


class IndexedReader:
    """Constant-memory direct access to contiguous canonical records."""
    def __init__(self, path, fmt):
        self.path, self.fmt = Path(path), fmt
        self.f = self.path.open('rb')
        size = self.path.stat().st_size
        if size % fmt.size:
            self.f.close()
            raise ScoringError(f'partial record in {path}')
        self.count = size // fmt.size
        first = self.f.read(fmt.size)
        self.first_index = fmt.unpack(first)[0] if first else None
        self.next_index = None

    def close(self):
        self.f.close()

    def read(self, index):
        if self.first_index is None or not (self.first_index <= index < self.first_index + self.count):
            raise ScoringError(f'missing index {index} in {self.path}')
        if self.next_index != index:
            self.f.seek((index - self.first_index) * self.fmt.size)
        raw = self.f.read(self.fmt.size)
        if len(raw) != self.fmt.size:
            raise ScoringError(f'truncated record {index} in {self.path}')
        row = self.fmt.unpack(raw)
        if row[0] != index:
            raise ScoringError(f'wrong record index {row[0]} expected {index} in {self.path}')
        self.next_index = index + 1
        return row


def json_rows(path, *, query=False):
    last = -1
    with Path(path).open() as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if query and row.get('event') != 'query':
                raise ScoringError(f'unexpected query event at {path}:{line_no}')
            index = row.get('next_index')
            if type(index) is not int or index <= last:
                raise ScoringError(f'nonmonotone/duplicate JSON index at {path}:{line_no}')
            if query and len(line.encode()) > 8192:
                raise ScoringError(f'full query exceeds8192 bytes at {path}:{line_no}')
            last = index
            yield row


def first_query(path):
    return next(json_rows(path, query=True), None)


def merged_truth_rows(path, supplemental=None):
    """Two sorted streams, one pending row each; no copied truth artifact."""
    left = iter(json_rows(path))
    right = iter(json_rows(supplemental)) if supplemental is not None else iter(())
    a, b = next(left, None), next(right, None)
    while a is not None or b is not None:
        if b is None or a is not None and a['next_index'] < b['next_index']:
            yield a
            a = next(left, None)
        elif a is None or b['next_index'] < a['next_index']:
            yield b
            b = next(right, None)
        else:
            if a != b:
                raise ScoringError('Conflicting supplemental full truth at index ' + str(a['next_index']))
            yield a
            a, b = next(left, None), next(right, None)


def find_truth(path, index, supplemental=None):
    for row in merged_truth_rows(path, supplemental):
        if row['next_index'] == index:
            return row
        if row['next_index'] > index:
            return None
    return None


def raw_centers(entity, *, strict=True):
    mean = entity.get('mean', [])
    if not isinstance(mean, list) or len(mean) != 16:
        if strict:
            raise ScoringError('query mean must contain all16 coordinates')
        return None, None
    if strict and natural(mean) is None:
        raise ScoringError('query mean must contain finite valid16 coordinates')
    soc = mean[11] if finite(mean[11]) else None
    try:
        q = math.exp(mean[5]) if finite(mean[5]) else None
    except OverflowError:
        q = None
    if not finite(q) or q <= 0:
        q = None
    return soc, q


def error_pair(soc, q, true_soc, true_q):
    if not (finite(true_soc) and finite(true_q) and true_q > 0):
        raise ScoringError('invalid scoring truth')
    return {'SOC_pp': 100 * (soc - true_soc) if finite(soc) else None,
            'Q_percent': 100 * (q / true_q - 1) if finite(q) else None}


def query_point(row, truth, epoch):
    entity = row['aggregate']
    soc, q = raw_centers(entity)
    flags = int(entity.get('flags', 0))
    valid = not (flags & BAD_FLAGS or flags & ~KNOWN_FLAGS)
    errors = error_pair(soc, q, truth['SOC'], truth['Q_Ah'])
    raw_prior = row.get('reason') in ['initial', 'cold_reset']
    available = {'SOC_pp': bool(entity.get('point_available')) and valid and not raw_prior,
                 'Q_percent': bool(entity.get('capacity_available')) and valid and not raw_prior}
    return {'at': stamp(row['next_index'], entity.get('elapsed_s', row.get('elapsed_s')), epoch),
            'raw_SOC': soc, 'raw_Q_Ah': q, 'errors': errors, 'available': available,
            'reported_availability': {'SOC': entity.get('point_available'), 'Q': entity.get('capacity_available')},
            'reason': row.get('reason'), 'raw_prior_or_reset': raw_prior}


class RangeAudit:
    def __init__(self):
        self.total = self.available = self.included = self.provisional = self.breaches = 0
        self.width = ErrorStats()
        self.first_miss = self.first_breach = None

    def add(self, low, high, truth, available, provisional, error, hard, at, width_scale=1):
        self.total += 1
        if provisional:
            self.provisional += 1
            if finite(error) and abs(error) > hard:
                self.breaches += 1
                if self.first_breach is None:
                    self.first_breach = {**at, 'raw_point_error': error}
        if available and finite(low) and finite(high) and low <= high:
            self.available += 1
            self.width.add((high - low) * width_scale, 1, at)
            if low <= truth <= high:
                self.included += 1
            elif self.first_miss is None:
                self.first_miss = {**at, 'lower': low, 'upper': high, 'truth': truth}

    def result(self):
        return {'saved_queries': self.total, 'available_ranges': self.available,
                'unavailable_ranges': self.total - self.available, 'truth_inclusions': self.included,
                'empirical_inclusion_among_available': self.included / self.available if self.available else None,
                'empirical_inclusion_all_saved_queries': self.included / self.total if self.total else None,
                'first_miss': self.first_miss, 'width_summary': self.width.result('one_per_saved_query'),
                'raw_local_provisional_queries': self.provisional,
                'raw_local_provisional_hard_error_breaches': self.breaches,
                'first_raw_local_provisional_hard_breach': self.first_breach,
                'scope': 'Descriptive serial-sample inclusion and raw local labels; not calibrated coverage or hard support.'}


def natural(mean):
    if not isinstance(mean, list) or len(mean) != 16 or not all(finite(v) for v in mean):
        return None
    try:
        values = [math.exp(x) if j < 6 else x for j, x in enumerate(mean)]
    except OverflowError:
        return None
    return values if all(finite(v) for v in values) and all(v > 0 for v in values[:6]) else None


def expected_grid(values, start, end):
    if values is None:
        return None
    grid = list(values)
    if (len(grid) > 24000 or any(type(n) is not int or not start <= n <= end for n in grid)
            or grid != sorted(set(grid)) or not grid or grid[0] != start or grid[-1] != end):
        raise ScoringError('required_query_indices must be the ordered unique full arm grid including entry and intended end')
    return set(grid)


def valid_interval(low, high):
    return finite(low) and finite(high) and low <= high


def full_query_scores(queries, full_truth, scalar_truth, output, epoch, targets,
                      selected_indices, last_consumed_index, *, start_index,
                      intended_end_index, required_query_indices=None,
                      supplemental_full_truth=None, budget=None):
    """Stream all full-query natural-unit and uncertainty scores to gzip."""
    labels = ['aggregate', 'component0', 'component1']
    ranges = {label: {q: RangeAudit() for q in ['SOC_pp', 'Q_percent']} for label in labels + ['all_component_hull']}
    vector = {label: [ErrorStats() for _ in NAMES] for label in labels}
    status_counts = {label: {'SOC': {}, 'Q': {}} for label in labels}
    disagreements = {quantity: {level: {'component_aggregate_disagreement': 0, 'both_components_miss': 0}
                                for level in ['hard', 'preferred']} for quantity in ['SOC_pp', 'Q_percent']}
    weights = [{'minimum_log_weight': None, 'maximum_log_weight': None, 'displayed_exp_underflow_queries': 0} for _ in range(2)]
    truths = iter(merged_truth_rows(full_truth, supplemental_full_truth))
    tr = next(truths, None)
    count, missing_full = 0, []
    selected, last_detail = {}, None
    issues, seen = [], set()
    required_prefix = ({n for n in required_query_indices if n <= last_consumed_index}
                       if required_query_indices is not None else {start_index})
    required_prefix.add(last_consumed_index)
    if required_query_indices is None:
        issues.append({'kind': 'required_query_grid_not_supplied'})
    if budget is None:
        budget = OutputBudget(536870912)
    with ExitStack() as stack:
        stream = stack.enter_context(Path(output).open('xb'))
        gz = stack.enter_context(gzip.GzipFile(filename='', fileobj=CappedBinary(stream, budget),
                                             mode='wb', mtime=0, compresslevel=3))
        writer = stack.enter_context(io.TextIOWrapper(gz, encoding='utf-8', newline='\n'))
        scalar = IndexedReader(scalar_truth, TRUTH)
        stack.callback(scalar.close)
        for row in json_rows(queries, query=True):
            n = row['next_index']
            if count >= 24000:
                raise ScoringError('full-query scoring exceeded declared24000 cap')
            seen.add(n)
            if not start_index <= n <= intended_end_index:
                issues.append({'kind': 'query_outside_intended_arm', 'next_index': n})
            if n > last_consumed_index:
                issues.append({'kind': 'query_beyond_scalar_prefix', 'next_index': n})
            if required_query_indices is not None and n not in required_query_indices and n != last_consumed_index:
                issues.append({'kind': 'unexpected_query_index', 'next_index': n})
            while tr is not None and tr['next_index'] < n:
                tr = next(truths, None)
            matched = tr if tr is not None and tr['next_index'] == n else None
            if matched is None:
                if n == 0:
                    raise ScoringError('initial full truth missing')
                _, tq, tz, tv = scalar.read(n)
                matched = {'next_index': n, 'SOC': tz, 'Q_Ah': tq, 'clean_voltage_V': tv, 'mean': None}
            tq, tz = matched['Q_Ah'], matched['SOC']
            at = stamp(n, row['aggregate'].get('elapsed_s', row.get('elapsed_s')), epoch)
            actual = natural(matched.get('mean'))
            if actual is None:
                missing_full.append(n)
                issues.append({'kind': 'missing_or_invalid_full16_truth', 'next_index': n})
            entities = [row['aggregate'], *row.get('components', [])]
            if len(entities) != 3:
                raise ScoringError('full query must contain aggregate and both components')
            details = []
            errors = []
            for label, entity in zip(labels, entities):
                soc, q = raw_centers(entity, strict=False)
                err = error_pair(soc, q, tz, tq)
                errors.append(err)
                values = natural(entity.get('mean'))
                if values is None:
                    issues.append({'kind': 'invalid_required_full16_estimate', 'next_index': n, 'entity': label})
                nd = [e - t for e, t in zip(values, actual)] if actual is not None and values is not None else None
                relative = ([100 * (values[j] / actual[j] - 1) if j <= 10 and actual[j] != 0 else None
                             for j in range(16)] if actual is not None and values is not None else None)
                if nd is not None:
                    for stat, error in zip(vector[label], nd):
                        stat.add(error, 1, at)
                for name, key in [('SOC', 'soc_status'), ('Q', 'capacity_status')]:
                    status = str(entity.get(key, 'missing'))
                    status_counts[label][name][status] = status_counts[label][name].get(status, 0) + 1
                flags = int(entity.get('flags', 0))
                valid = values is not None and not (flags & BAD_FLAGS or flags & ~KNOWN_FLAGS) and n <= last_consumed_index
                if flags & BAD_FLAGS or flags & ~KNOWN_FLAGS:
                    issues.append({'kind': 'invalid_query_entity_flags', 'next_index': n, 'entity': label, 'flags': flags})
                ranges_reported = bool(entity.get('local_ranges_available'))
                ranges_finite = (valid_interval(entity.get('soc_local_lower'), entity.get('soc_local_upper'))
                                 and valid_interval(entity.get('capacity_local_lower_Ah'), entity.get('capacity_local_upper_Ah')))
                sd = entity.get('coordinate_sd')
                sd_valid = isinstance(sd, list) and len(sd) == 16 and all(finite(v) and v >= 0 for v in sd)
                if ranges_reported and (not ranges_finite or not sd_valid):
                    valid = False
                    issues.append({'kind': 'invalid_asserted_available_local_range_or_sd', 'next_index': n,
                                   'entity': label, 'ranges_finite_ordered': ranges_finite, 'coordinate_sd_valid': sd_valid})
                r_available = ranges_reported and valid
                ranges[label]['SOC_pp'].add(entity.get('soc_local_lower'), entity.get('soc_local_upper'), tz,
                    r_available, entity.get('soc_status') == 'provisional', err['SOC_pp'], targets['SOC_error_pp']['hard'], at, 100)
                ranges[label]['Q_percent'].add(entity.get('capacity_local_lower_Ah'), entity.get('capacity_local_upper_Ah'), tq,
                    r_available, entity.get('capacity_status') == 'provisional', err['Q_percent'], targets['capacity_error_percent']['hard'], at, 100 / tq)
                details.append({'label': label, 'raw_SOC': soc, 'raw_Q_Ah': q, 'errors': err,
                    'point_available': bool(entity.get('point_available')), 'capacity_available': bool(entity.get('capacity_available')),
                    'valid_for_useful_scoring': valid, 'natural_estimate': values, 'natural_errors': nd,
                    'positive_parameter_relative_errors_percent': relative, 'coordinate_sd': entity.get('coordinate_sd'),
                    'soc_status': entity.get('soc_status'), 'capacity_status': entity.get('capacity_status'),
                    'local_ranges_available': entity.get('local_ranges_available'),
                    'local_SOC_interval': [entity.get('soc_local_lower'), entity.get('soc_local_upper')],
                    'local_Q_interval_Ah': [entity.get('capacity_local_lower_Ah'), entity.get('capacity_local_upper_Ah')],
                    'evidence_next_index': entity.get('evidence_next_index'), 'evidence_age_samples': entity.get('evidence_age_samples'),
                    'limited_gain_count': entity.get('limited_gain_count'), 'zero_gain_count': entity.get('zero_gain_count'),
                    'flags': flags, 'excitation': entity.get('excitation')})
            hull = row.get('all_component_hull', [None] * 4)
            if not isinstance(hull, list) or len(hull) != 4:
                issues.append({'kind': 'invalid_hull_shape', 'next_index': n})
                hull = [None] * 4
            hull_finite = all(finite(v) for v in hull)
            hull_ok = hull_finite and valid_interval(hull[0], hull[1]) and valid_interval(hull[2], hull[3])
            if hull_finite and not hull_ok:
                issues.append({'kind': 'reversed_finite_hull', 'next_index': n})
            ranges['all_component_hull']['SOC_pp'].add(hull[0], hull[1], tz, hull_ok, False, None, 0, at, 100)
            ranges['all_component_hull']['Q_percent'].add(hull[2], hull[3], tq, hull_ok, False, None, 0, at, 100 / tq)
            lw = row.get('log_weights')
            if not isinstance(lw, list) or len(lw) != 2 or not all(finite(v) for v in lw):
                raise ScoringError('invalid full-query log weights')
            for j in range(2):
                s = weights[j]
                s['minimum_log_weight'] = lw[j] if s['minimum_log_weight'] is None else min(lw[j], s['minimum_log_weight'])
                s['maximum_log_weight'] = lw[j] if s['maximum_log_weight'] is None else max(lw[j], s['maximum_log_weight'])
                s['displayed_exp_underflow_queries'] += math.exp(lw[j]) == 0.0
            mechanism = {}
            for quantity, config_key in [('SOC_pp', 'SOC_error_pp'), ('Q_percent', 'capacity_error_percent')]:
                mechanism[quantity] = {}
                for level, limit in targets[config_key].items():
                    passes = [finite(e[quantity]) and abs(e[quantity]) <= limit for e in errors]
                    disagreement = any(p != passes[0] for p in passes[1:])
                    both_miss = all(finite(e[quantity]) for e in errors[1:]) and not any(passes[1:])
                    disagreements[quantity][level]['component_aggregate_disagreement'] += disagreement
                    disagreements[quantity][level]['both_components_miss'] += both_miss
                    mechanism[quantity][level] = {'raw_point_passes_aggregate_component0_component1': passes,
                        'component_aggregate_disagreement': disagreement, 'both_components_miss': both_miss}
                candidates = [(abs(errors[j + 1][quantity]), j) for j in range(2) if finite(errors[j + 1][quantity])]
                mechanism[quantity]['post_scoring_oracle_best_component'] = min(candidates)[1] if candidates else None
            detail = {'next_index': n, 'at': at, 'reason': row.get('reason'), 'truth_SOC': tz, 'truth_Q_Ah': tq,
                      'truth_natural_vector': actual, 'natural_coordinate_names': NAMES,
                      'full_truth_available': actual is not None, 'entities': details, 'log_weights': lw,
                      'all_component_hull': hull, 'mechanism': mechanism,
                      'bank_evidence_next_index': row.get('bank_evidence_next_index'),
                      'last_rejection_stage': row.get('last_rejection_stage'),
                      'application_accuracy': 'unresolved', 'coverage': 'unvalidated',
                      'hard_support': 'not_provided', 'numeric_scoring_only': True}
            writer.write(dumps(detail) + '\n')
            count += 1
            last_detail = detail
            if n in selected_indices or n == last_consumed_index:
                selected[str(n)] = detail
        # Validate any remaining supplemental duplicates without copying truth.
        for _ in truths:
            pass
    missing_required = sorted(required_prefix - seen)
    if missing_required:
        issues.append({'kind': 'missing_required_queries_through_scalar_prefix', 'indices': missing_required})
    return {'saved_queries_scored': count, 'missing_full16_truth_indices': missing_full,
            'query_grid_verified': required_query_indices is not None,
            'required_queries_through_scalar_prefix': len(required_prefix),
            'missing_required_query_indices': missing_required,
            'valid_required_full_query_data': not issues,
            'input_or_accounting_issues': issues,
            'uncertainty': {label: {q: x.result() for q, x in byq.items()} for label, byq in ranges.items()},
            'natural_vector_errors': {label: {name: st.result('one_per_saved_query') for name, st in zip(NAMES, stats)}
                                      for label, stats in vector.items()},
            'status_counts': status_counts, 'log_weight_diagnostics': weights,
            'raw_component_target_disagreements': disagreements,
            'selected_full_queries': selected, 'last_full_query': last_detail,
            'full_score_artifact': file_identity(output),
            'scope': 'Saved full-query grid only. Oracle diagnostics never select runtime output; serial inclusion is not calibrated coverage.'}


def score_arm(*, metrics, truth, queries, full_truth, plan, cell, arm,
              start_index, end_index, output, observations=None,
              observations_start_index=None, expected_complete=True,
              required_query_indices=None, supplemental_full_truth=None,
              max_output_bytes=536870912):
    """Score one completed or stopped arm without retaining its history.

    `end_index` is always the frozen intended endpoint, including on failure.
    `expected_complete=False` labels a stopped run; it never shortens a target
    window to make retention pass. Root may call this function repeatedly in one
    scorer process for all four arms. `required_query_indices` is the exact full
    intended grid; its observed prefix plus the stopped endpoint is checked.
    `supplemental_full_truth` is merged by index with identical duplicates only.
    `max_output_bytes` caps actual compressed detail and summary bytes together,
    retaining a4096-byte failure-summary reserve. No explicit required grid means
    completeness is unverified, so completed_valid_arm cannot be true.
    """
    plan_path = None if isinstance(plan, dict) else Path(plan)
    p = plan if isinstance(plan, dict) else json.loads(plan_path.read_text())
    start, end = int(start_index), int(end_index)
    if not (0 <= start < end) or cell not in ['cell_a', 'cell_b']:
        raise ScoringError('invalid arm interval/cell')
    grid = expected_grid(required_query_indices, start, end)
    budget = OutputBudget(max_output_bytes)
    output = Path(output)
    detail_path = output.with_suffix('.full_scores.jsonl.gz')
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() or detail_path.exists():
        raise FileExistsError('Refusing existing scoring outputs')
    # Reserve the result path before reading inputs; any exception is preserved.
    with output.open('xb') as summary_stream:
        try:
            initial = first_query(queries)
            if initial is None or initial['next_index'] != start:
                raise ScoringError('missing initial/restore/cold entry query')
            initial_truth = find_truth(full_truth, start, supplemental_full_truth)
            if initial_truth is None:
                raise ScoringError('missing initial/restore/cold full truth')
            epoch = int(initial.get('epoch_begin', initial['aggregate'].get('epoch_begin', start)))
            prior = query_point(initial, initial_truth, epoch)
            initial_elapsed = prior['at']['actual_elapsed_s']
            if not finite(initial_elapsed) or initial_elapsed < 0:
                raise ScoringError('invalid initial/restore/cold binary64 clock')
            windows = make_windows(p, cell, start, end)
            for w in windows:
                w.feed(start, initial_elapsed, prior['errors'], prior['available'], {}, DT, None, epoch,
                       entry_is_learned=not prior['raw_prior_or_reset'])
            prompt_s = [0, 1, 5, 10, 60, 120, 220, 400, 600, 900, 1800, 2100]
            selected_indices = {start, end}
            selected_indices.update(t * RATE for t in prompt_s if start <= t * RATE <= end)
            selected_indices.update(start + t * RATE for t in prompt_s if start + t * RATE <= end)
            if cell == 'cell_b':
                selected_indices.update(t * RATE for t in p['B_continuous_4h']['checkpoint_times_s'])
            selected = {str(start): prior}
            issues, n_consumed, n_invalid, n_metrics = [], 0, 0, 0
            first_invalid = None
            last_index, last_elapsed = start, initial_elapsed
            regime_voltage = {}
            last_current = None
            with ExitStack() as stack:
                tf = IndexedReader(truth, TRUTH)
                stack.callback(tf.close)
                of = None
                if observations is not None:
                    of = IndexedReader(observations, OBSERVATION)
                    stack.callback(of.close)
                    if observations_start_index is not None and of.first_index != int(observations_start_index):
                        raise ScoringError('observation data_start_index does not match file')
                    if start > (of.first_index if of.first_index is not None else start):
                        last_current = of.read(start - 1)[2]
                metric_path = Path(metrics)
                total_records, partial_bytes = divmod(metric_path.stat().st_size, METRIC.size)
                if partial_bytes:
                    issues.append({'kind': 'partial_metric_record', 'trailing_bytes': partial_bytes})
                mf = stack.enter_context(metric_path.open('rb'))
                for _ in range(total_records):
                    row = METRIC.unpack(mf.read(METRIC.size))
                    n_metrics += 1
                    n, elapsed, z, q, forecast, fit, old0, old1, mask, rc, flags = row
                    if n != last_index + 1 or n > end:
                        issues.append({'kind': 'unexpected_metric_cursor', 'record': n_metrics,
                                       'actual_next_index': n, 'expected_next_index': last_index + 1})
                        break
                    _, tq, tz, clean_v = tf.read(n)
                    if not finite(clean_v):
                        raise ScoringError('nonfinite clean voltage truth')
                    current, observed_v, dt = None, None, DT
                    if of is not None:
                        _, dt, current, observed_v = of.read(n - 1)
                        if not (finite(dt) and dt == DT and finite(current) and finite(observed_v)):
                            raise ScoringError('invalid observation/dt in scored stream')
                    transaction_valid = rc == 0 and not (flags & BAD_FLAGS or flags & ~KNOWN_FLAGS)
                    expected_elapsed = last_elapsed + dt
                    if not finite(elapsed) or elapsed != expected_elapsed:
                        transaction_valid = False
                        issues.append({'kind': 'metric_clock_recurrence_mismatch', 'next_index': n,
                                       'actual_elapsed_s': elapsed, 'expected_elapsed_s': expected_elapsed})
                    if mask & ~15:
                        transaction_valid = False
                        issues.append({'kind': 'unknown_availability_bits', 'next_index': n, 'mask': mask})
                    if not all(finite(x) for x in (z, q, old0, old1)) or q <= 0:
                        transaction_valid = False
                        issues.append({'kind': 'nonfinite_raw_center_or_weight', 'next_index': n})
                    for bit, value, field in [(AVAIL_SOC, z, 'SOC'), (AVAIL_Q, q, 'Q'),
                                               (AVAIL_CAUSAL, forecast, 'causal_forecast'),
                                               (AVAIL_POSTFIT, fit, 'filtered_fit')]:
                        if mask & bit and not finite(value):
                            transaction_valid = False
                            issues.append({'kind': 'nonfinite_asserted_available_output', 'next_index': n, 'field': field})
                    if not transaction_valid:
                        n_invalid += 1
                        if first_invalid is None:
                            first_invalid = {'next_index': n, 'ingest_return': rc, 'flags': flags, 'availability_mask': mask}
                    errors = error_pair(z, q, tz, tq)
                    avail = {'SOC_pp': bool(mask & AVAIL_SOC) and transaction_valid,
                             'Q_percent': bool(mask & AVAIL_Q) and transaction_valid}
                    causal_ok = bool(mask & AVAIL_CAUSAL) and transaction_valid and finite(forecast)
                    fit_ok = bool(mask & AVAIL_POSTFIT) and transaction_valid and finite(fit)
                    voltage = {'causal_clean_mV': 1000 * (forecast - clean_v) if causal_ok else None,
                               'noisy_innovation_mV': 1000 * (observed_v - forecast) if causal_ok and observed_v is not None else None,
                               'filtered_fit_clean_mV': 1000 * (fit - clean_v) if fit_ok else None}
                    at = stamp(n, elapsed, epoch)
                    for w in windows:
                        w.feed(n, elapsed, errors, avail, voltage, dt, current, epoch)
                    if current is not None:
                        regime = 'rest' if current == 0 else 'charge' if current < 0 else 'weak_positive_at_most3mA' if current <= .003 else 'positive_above3mA'
                        regimes = [regime]
                        if last_current is not None and current != last_current:
                            regimes.append('first_interval_after_current_transition')
                        for label in regimes:
                            stats = regime_voltage.setdefault(label, {k: ErrorStats() for k in voltage})
                            for k, value in voltage.items():
                                stats[k].add(value, dt, at)
                        last_current = current
                    if n in selected_indices:
                        selected[str(n)] = {'at': at, 'raw_SOC': z, 'raw_Q_Ah': q, 'errors': errors,
                                            'available': avail, 'reported_availability_mask': mask,
                                            'transaction_valid': transaction_valid, 'voltage_errors_mV': voltage}
                    n_consumed += 1
                    last_index, last_elapsed = n, expected_elapsed
                if n_metrics < total_records:
                    issues.append({'kind': 'unscored_metric_records', 'count': total_records - n_metrics})
            complete = (bool(expected_complete) and n_consumed == end - start
                        and last_index == end and not issues and n_invalid == 0)
            if expected_complete and not complete:
                issues.append({'kind': 'expected_complete_arm_is_incomplete_or_invalid'})
            result = {'schema': 'mumble_continuous_arm_scores_v1', 'cell': cell, 'arm': arm,
                'intended_start_index': start, 'intended_end_index': end, 'epoch_begin': epoch,
                'last_scored_consumed_index': last_index,
                'expected_complete': bool(expected_complete), 'completed_valid_arm': complete,
                'metric_records_read': n_metrics, 'consumed_intervals_scored': n_consumed,
                'invalid_transaction_records': n_invalid, 'first_invalid_transaction': first_invalid,
                'input_or_accounting_issues': issues, 'initial_raw_point': prior,
                'capacity_startup_deadline': None, 'resolution_s': DT,
                'windows': {w.name: w.result() for w in windows}, 'selected_points': selected,
                'regime_voltage': {name: {k: st.result() for k, st in stats.items()} for name, stats in regime_voltage.items()},
                'interpretation': {'point_accuracy': 'Empirical sample-grid point errors, separated from availability and local precision.',
                    'application_accuracy': 'unresolved', 'coverage': 'unvalidated', 'hard_support': 'not_provided',
                    'incomplete_windows': 'No sustained-to-end or full retention claim when the intended window is incomplete.',
                    'renewal': 'Remaining in the preferred target is sufficient; within-target drift is descriptive.',
                    'causality': 'One prescribed chronology does not separate elapsed time from excitation causally.'}}
            result['full_query_audit'] = full_query_scores(queries, full_truth, truth, detail_path, epoch,
                p['measurements']['targets'], selected_indices, last_index, start_index=start,
                intended_end_index=end, required_query_indices=grid,
                supplemental_full_truth=supplemental_full_truth, budget=budget)
            if not result['full_query_audit']['valid_required_full_query_data']:
                result['input_or_accounting_issues'].extend(result['full_query_audit']['input_or_accounting_issues'])
                result['completed_valid_arm'] = False
            valid_through = last_index
            if first_invalid is not None:
                valid_through = min(valid_through, first_invalid['next_index'] - 1)
            for issue in result['input_or_accounting_issues']:
                if 'next_index' in issue:
                    valid_through = min(valid_through, issue['next_index'] - 1)
                elif issue.get('indices'):
                    valid_through = min(valid_through, min(issue['indices']) - 1)
                elif issue['kind'] == 'required_query_grid_not_supplied':
                    valid_through = start
            if not result['completed_valid_arm'] and valid_through == end:
                valid_through = end - 1
            result['validity_verified_through_index'] = valid_through
            result['windows'] = {w.name: w.result(valid_through) for w in windows}
            result['input_files'] = {name: file_identity(path) for name, path in [
                ('metrics', metrics), ('truth', truth), ('queries', queries), ('full_truth', full_truth)]}
            if observations is not None:
                result['input_files']['observations'] = file_identity(observations)
            if supplemental_full_truth is not None:
                result['input_files']['supplemental_full_truth'] = file_identity(supplemental_full_truth)
            if plan_path is not None:
                result['contract'] = file_identity(plan_path)
            result['scorer_sha256'] = file_identity(__file__)['sha256']
            result['output_allowance'] = {'limit_bytes': budget.limit,
                'failure_summary_reserve_bytes': budget.FAILURE_RESERVE,
                'compressed_detail_bytes': budget.used,
                'scope': 'Actual bytes written to compressed detail plus this JSON summary.'}
            block = (json.dumps(clean_json(result), indent=2, allow_nan=False) + '\n').encode('utf-8')
            budget.write(summary_stream, block)
            return clean_json(result)
        except Exception as exc:
            failure = {'schema': 'mumble_continuous_scoring_failure_v1',
                       'error_type': type(exc).__name__, 'error': str(exc)[:1500],
                       'arm': arm, 'intended_start_index': start, 'intended_end_index': end,
                       'partial_outputs_preserved': True, 'learner_calls': 0,
                       'max_output_bytes': budget.limit, 'bytes_before_failure_summary': budget.used}
            budget.write(summary_stream, (dumps(failure) + '\n').encode('utf-8'), failure=True)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['metrics', 'truth', 'queries', 'full-truth', 'plan', 'output']:
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--cell', choices=['cell_a', 'cell_b'], required=True)
    parser.add_argument('--arm', required=True)
    parser.add_argument('--start-index', required=True, type=int)
    parser.add_argument('--end-index', required=True, type=int)
    parser.add_argument('--observations', type=Path)
    parser.add_argument('--observations-start-index', type=int)
    parser.add_argument('--required-query-indices', type=Path,
                        help='Full intended ordered next_index grid, JSON array or one integer per line.')
    parser.add_argument('--supplemental-full-truth', type=Path)
    parser.add_argument('--max-output-bytes', type=int, default=536870912)
    parser.add_argument('--incomplete', action='store_true', help='Keep frozen intended endpoint; label expected stopping.')
    args = vars(parser.parse_args())
    if args['required_query_indices'] is not None:
        text = args['required_query_indices'].read_text().strip()
        args['required_query_indices'] = json.loads(text) if text.startswith('[') else [int(v) for v in text.split()]
    args['expected_complete'] = not args.pop('incomplete')
    result = score_arm(**args)
    print(dumps({'status': 'scored', 'arm': result['arm'], 'completed_valid_arm': result['completed_valid_arm'],
                 'consumed_intervals_scored': result['consumed_intervals_scored'],
                 'output': str(args['output']), 'learner_calls': 0}))


if __name__ == '__main__':
    main()
