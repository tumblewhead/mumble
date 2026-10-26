#!/usr/bin/env python3
"""Bounded synthetic source for the frozen continuous-learning diagnostic.

The estimator must never import this module or receive its truth artifacts.
Only observations.bin (index, dt, current, measured voltage) crosses that
boundary. Creating a manifest or source does not draw noise; primary draws
require an explicit allow_primary=True after the executable receipt is frozen.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import math
import platform
import signal
import struct
import sys
import time
import zlib
from fractions import Fraction
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RATE_HZ = 35
DT = 1.0 / RATE_HZ
OBSERVATION = struct.Struct('<Qddd')
SCALAR_TRUTH = struct.Struct('<Qddd')
PRIMARY_SEEDS = frozenset((2026102601, 2026102602))
CHAIN_TAG = b'mumble-stream-chain-v1'
JOURNAL_HEADER = struct.Struct('<8sIIQQ32s')
JOURNAL_PAYLOAD = struct.Struct('<QII6d8d16s16sII32s')
JOURNAL_CHECK = struct.Struct('<II')
JOURNAL_RECORD_BYTES = JOURNAL_PAYLOAD.size + JOURNAL_CHECK.size
JOURNAL_HEADER_BYTES = JOURNAL_HEADER.size + JOURNAL_CHECK.size
CHARGE_KEYS = ('signed_Ah', 'positive_Ah', 'negative_magnitude_Ah', 'absolute_Ah')
SNAPSHOT_SCHEMA = 'mumble_continuous_source_snapshot_v1'
TOTAL_NOISE_DRAWS = 0  # Process-local audit counter; never part of plant state.


class SourceError(RuntimeError):
    pass


class SourceStopped(SourceError):
    """A host stop observed only after a complete source/output transaction."""
    def __init__(self, signum):
        self.signum = int(signum)
        super().__init__('Deferred ' + signal.Signals(signum).name + ' at complete record boundary')


class _DeferredSourceSignals:
    """Main-thread guard; Python signal handlers never interrupt a mutation.

    A second cooperative signal remains deferred while the first failure record
    is written. SIGKILL, interpreter termination and I/O faults are outside this
    guarantee and must retain explicitly uncertain accounting when necessary.
    """
    def __init__(self):
        self.signum = None
        self.received = 0
        self.previous = {}

    def receive(self, signum, _frame):
        if self.signum is None:
            self.signum = signum
        self.received += 1

    def __enter__(self):
        try:
            for signum in (signal.SIGINT, signal.SIGTERM):
                self.previous[signum] = signal.signal(signum, self.receive)
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, _kind, _value, _traceback):
        for signum, previous in self.previous.items():
            signal.signal(signum, previous)

    def check(self):
        if self.signum is not None:
            raise SourceStopped(self.signum)


def canonical_bytes(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), allow_nan=False,
                      ensure_ascii=False).encode('utf-8')


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


def inherited_constants():
    """Read only the pinned literal cell table and current-profile function."""
    path = ROOT / 'tools/generate_cases.py'
    tree = ast.parse(path.read_text())
    cells = next(node.value for node in tree.body if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == 'CELLS'
                         for target in node.targets))
    profile = next(node for node in tree.body
                   if isinstance(node, ast.FunctionDef) and node.name == 'profile')
    namespace = {'Fraction': Fraction}
    module = ast.fix_missing_locations(ast.Module(body=[profile], type_ignores=[]))
    exec(compile(module, str(path), 'exec'), namespace)
    return ast.literal_eval(cells), namespace['profile']()


def _validated_events(events):
    out, cursor = [], 0
    for k, item in enumerate(events):
        start = item.get('start_index', cursor)
        end = item.get('end_index', start + item.get('count', 0))
        current = float(item['current_A'])
        if (type(start) is not int or type(end) is not int or start != cursor
                or end <= start or end >= 2**64 or not math.isfinite(current)
                or abs(current) > 0.25):
            raise SourceError('Invalid or noncontiguous current event')
        out.append({'start_index': start, 'end_index': end, 'count': end - start,
                    'current_A': current,
                    'duration_fraction_s': str(Fraction(end - start, RATE_HZ)),
                    'label': str(item.get('label', 'event_' + str(k))),
                    'phase': str(item.get('phase', item.get('label', 'event_' + str(k))))})
        cursor = end
    if not out:
        raise SourceError('Empty current schedule')
    return out


def build_events(plan, cell):
    """Expand prescribed currents only; this performs no state or RNG step."""
    if cell not in ('cell_a', 'cell_b'):
        raise SourceError('Unknown synthetic cell')
    _, initial_blocks = inherited_constants()
    blocks = []
    if cell == 'cell_a':
        blocks = [(i, d, label, 'initial_learning') for i, d, label in initial_blocks]
    else:
        for phase in plan['B_continuous_4h']['phases']:
            if phase['kind'] == 'inherited_current_protocol':
                part = initial_blocks
            elif phase['kind'] == 'constant':
                part = [(phase['current_A'], Fraction(phase['end_s'] - phase['start_s']), phase['id'])]
            elif phase['kind'] == 'repeat':
                part = [(entry['current_A'], Fraction(str(entry['duration_s'])),
                         phase['id'] + '_' + str(repeat) + '_' + str(j))
                        for repeat in range(phase['repeats'])
                        for j, entry in enumerate(phase['pattern'])]
            else:
                raise SourceError('Unknown phase kind')
            start = sum((duration for _, duration, _, _ in blocks), Fraction())
            if start != phase['start_s']:
                raise SourceError('Phase start does not match prescribed input')
            if sum((d for _, d, _ in part), Fraction()) != phase['end_s'] - phase['start_s']:
                raise SourceError('Phase duration mismatch')
            blocks.extend((i, d, label, phase['id']) for i, d, label in part)
    cursor, events = 0, []
    for current, duration, label, phase in blocks:
        samples = duration * RATE_HZ
        if samples.denominator != 1 or samples <= 0:
            raise SourceError('Nonintegral current-event sample count')
        end = cursor + int(samples)
        events.append({'start_index': cursor, 'end_index': end,
                       'current_A': float(current), 'label': label, 'phase': phase})
        cursor = end
    result = _validated_events(events)
    expected = (plan['A_second_cell_lifecycle']['unique_observations'] if cell == 'cell_a'
                else plan['B_continuous_4h']['samples'])
    if cursor != expected:
        raise SourceError('Cell duration differs from frozen contract')
    return result


def runtime_identity():
    return {'python': sys.version, 'python_implementation': platform.python_implementation(),
            'numpy': np.__version__, 'platform': platform.platform(),
            'libc': list(platform.libc_ver()),
            'generator_path': 'tools/continuous_source.py',
            'generator_sha256': sha256_file(Path(__file__)),
            'inherited_path': 'tools/generate_cases.py',
            'inherited_sha256': sha256_file(ROOT / 'tools/generate_cases.py'),
            'math': 'Python math.exp/tanh/log with the recorded host libm/runtime',
            'rng': 'numpy.random.Generator(numpy.random.PCG64(seed)); scalar normal(0,0.001)'}


def make_source_manifest(plan, contract_sha256, cell, *, fixture_events=None, fixture_seed=None):
    """Create an immutable source identity without generating any observations."""
    if not isinstance(contract_sha256, str) or len(bytes.fromhex(contract_sha256)) != 32:
        raise SourceError('Invalid contract SHA256')
    truth_source = plan['physical_and_noise_model']['truth_source']
    inherited = (ROOT / truth_source['path']).read_bytes()
    if _git_blob(inherited) != truth_source['git_blob']:
        raise SourceError('Inherited truth/current source no longer matches its pinned blob')
    normal_events = build_events(plan, cell)
    fixture = fixture_events is not None or fixture_seed is not None
    if fixture:
        if type(fixture_seed) is not int or fixture_seed < 0 or fixture_seed in PRIMARY_SEEDS:
            raise SourceError('Toy fixtures require a nonprimary nonnegative seed')
        events = _validated_events(fixture_events) if fixture_events is not None else normal_events
        seed = fixture_seed
    else:
        events = normal_events
        seed = plan['physical_and_noise_model']['noise']['seeds'][cell]
        if seed not in PRIMARY_SEEDS:
            raise SourceError('Primary seed differs from frozen contract')
    return {'schema': 'mumble_continuous_source_manifest_v1', 'contract_sha256': contract_sha256,
            'cell': cell, 'fixture': fixture, 'seed': seed, 'rate_Hz': RATE_HZ,
            'dt_s': DT, 'sigma_V': 0.001, 'events': events,
            'model': {'temperature_C': 25, 'modes': 3,
                      'truth_source_path': truth_source['path'],
                      'truth_source_git_blob': truth_source['git_blob'],
                      'truth_symbol': 'CELLS[' + cell + ']',
                      'OCV': '3+1.15*z+0.08*tanh(8*(z-0.5))',
                      'closed_form': 'event-entry states, elapsed=within_event_count*(1.0/35.0)'},
            'environment': runtime_identity(),
            'sample_semantics': 'Point voltage at END of constant-current interval; positive current discharges.',
            'normal_draws': 'One scalar Generator.normal(0.0,0.001) per global index; none at query/checkpoint.',
            'observation_record': '<Qddd sample_index,dt_s,current_A,voltage_V',
            'scalar_truth_record': '<Qddd next_index,Q_Ah,SOC,clean_voltage_V',
            'hash_chain': 'h0=SHA256(ASCII mumble-stream-chain-v1 || source_id); hnext=SHA256(hprev || observation_record)'}


def source_id(manifest):
    return hashlib.sha256(canonical_bytes(manifest)).hexdigest()


def _finite_state(state):
    if set(state) != {'z', 'v', 'h'} or len(state['v']) != 3:
        raise SourceError('Invalid physical state shape')
    values = [state['z'], *state['v'], state['h']]
    if not all(isinstance(value, (float, int)) and math.isfinite(value) for value in values):
        raise SourceError('Nonfinite physical state')
    if not 0 <= state['z'] <= 1 or not -1 <= state['h'] <= 1 or any(abs(v) > 0.25 for v in state['v']):
        raise SourceError('Physical state leaves declared generator domain')


class StatefulSource:
    """Constant-size physical/RNG state plus the finite prescribed event table."""
    def __init__(self, manifest, *, allow_primary=False):
        self.manifest = copy.deepcopy(manifest)
        self.source_id = source_id(self.manifest)
        self.events = _validated_events(self.manifest['events'])
        if self.events != self.manifest['events']:
            raise SourceError('Noncanonical manifest events')
        if self.manifest['environment'] != runtime_identity():
            raise SourceError('Source environment or executable hash mismatch')
        if self.manifest['rate_Hz'] != RATE_HZ or self.manifest['dt_s'] != DT or self.manifest['sigma_V'] != 0.001:
            raise SourceError('Measurement configuration mismatch')
        fixture = self.manifest.get('fixture')
        seed = self.manifest['seed']
        if type(fixture) is not bool or type(seed) is not int or seed < 0:
            raise SourceError('Invalid fixture/seed identity')
        if fixture and seed in PRIMARY_SEEDS or not fixture and seed not in PRIMARY_SEEDS:
            raise SourceError('Fixture and primary seed identities overlap')
        self.allow_primary = bool(allow_primary)
        cells, _ = inherited_constants()
        self.parameters = copy.deepcopy(cells[self.manifest['cell']])
        model = self.manifest['model']
        if model['truth_source_git_blob'] != _git_blob((ROOT / model['truth_source_path']).read_bytes()):
            raise SourceError('Truth source hash mismatch')
        self.rng = np.random.Generator(np.random.PCG64(seed))
        p = self.parameters
        self.current_state = {'z': float(p['z0']), 'v': list(map(float, p['v0'])), 'h': float(p['h0'])}
        self.event_entering_state = copy.deepcopy(self.current_state)
        self.next_index = 0
        self.event_index = 0
        self.within_event_count = 0
        self.actual_elapsed_s = 0.0
        self.last_current_A = None
        self.last_clean_voltage_V = None
        self.last_event_index = None
        self.charge = dict.fromkeys(CHARGE_KEYS, 0.0)
        self.charge_compensation = dict.fromkeys(self.charge, 0.0)
        self.hash_chain = hashlib.sha256(CHAIN_TAG + bytes.fromhex(self.source_id)).digest()
        _finite_state(self.current_state)

    @property
    def end_index(self):
        return self.events[-1]['end_index']

    def _physical_at(self, entering, current, count):
        p = self.parameters
        elapsed = count * DT
        z = entering['z'] - current * elapsed / (3600.0 * p['Q_Ah'])
        v = [R * current + (old - R * current) * math.exp(-elapsed / tau)
             for R, tau, old in zip(p['R'], p['tau'], entering['v'])]
        if current == 0:
            h = entering['h']
        else:
            target = 1.0 if current > 0 else -1.0
            gamma = p['gamma_plus'] if current > 0 else p['gamma_minus']
            h = target + (entering['h'] - target) * math.exp(-gamma * abs(current) * elapsed / 3600.0)
        return {'z': z, 'v': v, 'h': h}

    def _charge_add(self, name, value):
        y = value - self.charge_compensation[name]
        total = self.charge[name] + y
        self.charge_compensation[name] = (total - self.charge[name]) - y
        self.charge[name] = total

    def _clean_voltage(self, state, current):
        p = self.parameters
        return (3.0 + 1.15 * state['z'] + 0.08 * math.tanh(8.0 * (state['z'] - 0.5))
                - p['R0'] * current - sum(state['v']) - p['H'] * state['h'])

    def next_record(self):
        """Advance one physical interval and draw exactly one new voltage noise."""
        global TOTAL_NOISE_DRAWS
        if not self.manifest['fixture'] and not self.allow_primary:
            raise SourceError('Primary generation requires the root-frozen executable receipt and allow_primary=True')
        if self.next_index == self.end_index:
            raise StopIteration
        event = self.events[self.event_index]
        if self.next_index != event['start_index'] + self.within_event_count:
            raise SourceError('Generator index/event cursor mismatch')
        current = event['current_A']
        trial = self._physical_at(self.event_entering_state, current, self.within_event_count + 1)
        _finite_state(trial)
        p = self.parameters
        clean = self._clean_voltage(trial, current)
        if not math.isfinite(clean):
            raise SourceError('Nonfinite clean voltage before noise draw')
        noise = float(self.rng.normal(0.0, 0.001))
        TOTAL_NOISE_DRAWS += 1
        observed = clean + noise
        if not math.isfinite(observed):
            raise SourceError('Nonfinite observed voltage')
        observation = OBSERVATION.pack(self.next_index, DT, current, observed)
        truth = SCALAR_TRUTH.pack(self.next_index + 1, p['Q_Ah'], trial['z'], clean)
        self.current_state = trial
        self.last_current_A = current
        self.last_clean_voltage_V = clean
        self.last_event_index = self.event_index
        self.hash_chain = hashlib.sha256(self.hash_chain + observation).digest()
        charge = current * DT / 3600.0
        self._charge_add('signed_Ah', charge)
        self._charge_add('positive_Ah', max(charge, 0.0))
        self._charge_add('negative_magnitude_Ah', max(-charge, 0.0))
        self._charge_add('absolute_Ah', abs(charge))
        self.actual_elapsed_s += DT
        self.next_index += 1
        self.within_event_count += 1
        if self.next_index == event['end_index']:
            self.event_index += 1
            self.within_event_count = 0
            self.event_entering_state = copy.deepcopy(self.current_state)
        return observation, truth

    def truth_query(self):
        """Generation/scoring artifact only; not an estimator initialization."""
        p, state = self.parameters, self.current_state
        mean = ([math.log(tau) for tau in p['tau']]
                + [math.log(p['gamma_plus']), math.log(p['gamma_minus']), math.log(p['Q_Ah'])]
                + [p['R0'], *p['R'], p['H'], state['z'], *state['v'], state['h']])
        phase_event = self.last_event_index if self.last_event_index is not None else 0
        return {'next_index': self.next_index, 'nominal_time_s': self.next_index / RATE_HZ,
                'actual_elapsed_s': self.actual_elapsed_s, 'mean': mean,
                'SOC': state['z'], 'Q_Ah': p['Q_Ah'],
                'clean_voltage_V': self.last_clean_voltage_V, 'current_A': self.last_current_A,
                'prediction_observed': self.last_event_index is not None,
                'event_index': self.last_event_index, 'next_event_index': self.event_index,
                'phase': self.events[phase_event]['phase'], 'charge': dict(self.charge)}

    def snapshot(self):
        payload = {'schema': SNAPSHOT_SCHEMA, 'manifest': self.manifest, 'source_id': self.source_id,
                   'next_index': self.next_index, 'event_index': self.event_index,
                   'within_event_count': self.within_event_count,
                   'event_entering_state': self.event_entering_state,
                   'current_state': self.current_state, 'actual_elapsed_s': self.actual_elapsed_s,
                   'last_current_A': self.last_current_A, 'last_clean_voltage_V': self.last_clean_voltage_V,
                   'last_event_index': self.last_event_index,
                   'charge': self.charge, 'charge_compensation': self.charge_compensation,
                   'rng_state': self.rng.bit_generator.state,
                   'normal_generator_state': self.rng.__getstate__(),
                   'normal_state_semantics': 'Generator.__getstate__ is null under pinned NumPy; full PCG64 bit_generator.state is saved. Scalar fixtures verify future-byte parity; no unseen normal cache is assumed.',
                   'noise_draws_total': self.next_index, 'hash_chain_hex': self.hash_chain.hex()}
        payload = copy.deepcopy(payload)
        return {'schema': SNAPSHOT_SCHEMA + '_envelope', 'payload': payload,
                'sha256': hashlib.sha256(canonical_bytes(payload)).hexdigest()}

    @classmethod
    def from_state(cls, snapshot, *, expected_manifest=None, allow_primary=False):
        """Validate a complete temporary instance; no caller object is mutated."""
        if (not isinstance(snapshot, dict) or snapshot.get('schema') != SNAPSHOT_SCHEMA + '_envelope'
                or set(snapshot) != {'schema', 'payload', 'sha256'}):
            raise SourceError('Source snapshot envelope mismatch')
        payload = snapshot['payload']
        if hashlib.sha256(canonical_bytes(payload)).hexdigest() != snapshot['sha256']:
            raise SourceError('Source snapshot checksum mismatch')
        if payload.get('schema') != SNAPSHOT_SCHEMA:
            raise SourceError('Source snapshot model version mismatch')
        manifest = payload['manifest']
        if expected_manifest is not None and canonical_bytes(manifest) != canonical_bytes(expected_manifest):
            raise SourceError('Source snapshot does not match expected immutable manifest')
        result = cls(manifest, allow_primary=allow_primary)
        if payload['source_id'] != result.source_id:
            raise SourceError('Snapshot source ID mismatch')
        for name in ('next_index', 'event_index', 'within_event_count', 'noise_draws_total'):
            if type(payload[name]) is not int or payload[name] < 0:
                raise SourceError('Invalid source snapshot counter')
        n, ei, within = payload['next_index'], payload['event_index'], payload['within_event_count']
        if n > result.end_index or payload['noise_draws_total'] != n:
            raise SourceError('Source snapshot observation accounting mismatch')
        if n == result.end_index:
            if ei != len(result.events) or within != 0:
                raise SourceError('Final event cursor mismatch')
        elif ei >= len(result.events) or within >= result.events[ei]['count'] or n != result.events[ei]['start_index'] + within:
            raise SourceError('Source snapshot event/index mismatch')
        _finite_state(payload['current_state'])
        _finite_state(payload['event_entering_state'])
        if within:
            expected = result._physical_at(payload['event_entering_state'], result.events[ei]['current_A'], within)
            if canonical_bytes(expected) != canonical_bytes(payload['current_state']):
                raise SourceError('Within-event physical state mismatch')
        elif canonical_bytes(payload['event_entering_state']) != canonical_bytes(payload['current_state']):
            raise SourceError('Event boundary does not carry physical state')
        elapsed = payload['actual_elapsed_s']
        if not isinstance(elapsed, (float, int)) or not math.isfinite(elapsed) or elapsed < 0:
            raise SourceError('Invalid source elapsed time')
        # Bound accumulated binary64 time error, without changing carried bytes.
        if abs(elapsed - n * DT) > max(1e-12, 4 * sys.float_info.epsilon * max(1, n) * max(1.0, n * DT)):
            raise SourceError('Source time/index mismatch')
        last = payload['last_event_index']
        if n == 0:
            if any(payload[key] is not None for key in ('last_event_index', 'last_current_A', 'last_clean_voltage_V')):
                raise SourceError('Initial source claims an observed voltage')
        else:
            if type(last) is not int or last < 0 or last >= len(result.events):
                raise SourceError('Invalid last observed event')
            event = result.events[last]
            if not event['start_index'] < n <= event['end_index'] or payload['last_current_A'] != event['current_A']:
                raise SourceError('Last event/current mismatch')
            if not isinstance(payload['last_clean_voltage_V'], (float, int)) or not math.isfinite(payload['last_clean_voltage_V']):
                raise SourceError('Nonfinite saved clean voltage')
        for key in ('charge', 'charge_compensation'):
            if set(payload[key]) != set(result.charge) or not all(math.isfinite(v) for v in payload[key].values()):
                raise SourceError('Invalid charge accounting state')
        if any(payload['charge'][key] < 0 for key in ('positive_Ah', 'negative_magnitude_Ah', 'absolute_Ah')):
            raise SourceError('Negative charge magnitude')
        if len(bytes.fromhex(payload['hash_chain_hex'])) != 32:
            raise SourceError('Invalid source hash-chain length')
        if payload['normal_generator_state'] is not None or result.rng.__getstate__() is not None:
            raise SourceError('Unexpected separate Generator state under pinned NumPy')
        try:
            result.rng.bit_generator.state = copy.deepcopy(payload['rng_state'])
        except (TypeError, ValueError, KeyError, OverflowError) as exc:
            raise SourceError('Invalid random-generator state') from exc
        if result.rng.bit_generator.state != payload['rng_state']:
            raise SourceError('Random-generator restore changed state')
        for name in ('next_index', 'event_index', 'within_event_count', 'actual_elapsed_s',
                     'event_entering_state', 'current_state', 'last_current_A',
                     'last_clean_voltage_V', 'last_event_index', 'charge', 'charge_compensation'):
            setattr(result, name, copy.deepcopy(payload[name]))
        result.hash_chain = bytes.fromhex(payload['hash_chain_hex'])
        return result


def _journal_record(source):
    state = source.event_entering_state
    rng = source.rng.bit_generator.state
    payload = JOURNAL_PAYLOAD.pack(
        source.next_index, source.event_index, source.within_event_count,
        state['z'], *state['v'], state['h'], source.actual_elapsed_s,
        *(source.charge[name] for name in CHARGE_KEYS),
        *(source.charge_compensation[name] for name in CHARGE_KEYS),
        rng['state']['state'].to_bytes(16, 'little'), rng['state']['inc'].to_bytes(16, 'little'),
        rng['has_uint32'], rng['uinteger'], source.hash_chain)
    return payload + JOURNAL_CHECK.pack(zlib.crc32(payload), 0)


def _checked_record(block, payload_size):
    if len(block) != payload_size + JOURNAL_CHECK.size:
        raise SourceError('Truncated source journal record')
    payload, tail = block[:payload_size], block[payload_size:]
    checksum, reserved = JOURNAL_CHECK.unpack(tail)
    if reserved != 0 or zlib.crc32(payload) != checksum:
        raise SourceError('Source journal checksum mismatch')
    return payload


def snapshot_at(journal_path, next_index, manifest, *, expected_sha256=None, allow_primary=False):
    """Reconstruct one exact source snapshot without RNG draws or history replay.

    Event-entering values are stored exactly. A single deterministic closed-form
    evaluation recovers current values inside a dwell; at its boundary the
    stored entering values already are current. The frozen implementation and
    environment are checked before reconstruction. The record and header have
    CRCs; an optional whole-file SHA verifies the primary receipt binding.
    """
    path = Path(journal_path)
    if expected_sha256 is not None and sha256_file(path) != expected_sha256:
        raise SourceError('Source journal does not match expected whole-file SHA256')
    if type(next_index) is not int or next_index < 0:
        raise SourceError('Invalid requested source journal index')
    with path.open('rb') as stream:
        header = _checked_record(stream.read(JOURNAL_HEADER_BYTES), JOURNAL_HEADER.size)
        magic, version, record_bytes, begin, count, identity = JOURNAL_HEADER.unpack(header)
        if magic != b'SCMSRC01' or version != 1 or record_bytes != JOURNAL_RECORD_BYTES or identity.hex() != source_id(manifest):
            raise SourceError('Source journal version/format/manifest mismatch')
        size = path.stat().st_size - JOURNAL_HEADER_BYTES
        if size < 0 or size % JOURNAL_RECORD_BYTES or size // JOURNAL_RECORD_BYTES > count:
            raise SourceError('Source journal size does not match complete records')
        available = size // JOURNAL_RECORD_BYTES
        if not begin <= next_index < begin + available:
            raise SourceError('Requested source journal index is not recorded')
        stream.seek(JOURNAL_HEADER_BYTES + (next_index - begin) * JOURNAL_RECORD_BYTES)
        record = stream.read(JOURNAL_RECORD_BYTES)
    snapshot = _snapshot_from_journal_record(record, manifest, allow_primary=allow_primary)
    if snapshot['payload']['next_index'] != next_index:
        raise SourceError('Source journal record index mismatch')
    return snapshot


def _snapshot_from_journal_record(record, manifest, *, allow_primary=False):
    """Reconstruct a preserved complete record even if a later write failed."""
    fields = JOURNAL_PAYLOAD.unpack(_checked_record(record, JOURNAL_PAYLOAD.size))
    n, ei, within = fields[:3]
    source = StatefulSource(manifest, allow_primary=allow_primary)
    source.next_index, source.event_index, source.within_event_count = n, ei, within
    source.event_entering_state = {'z': fields[3], 'v': list(fields[4:7]), 'h': fields[7]}
    source.actual_elapsed_s = fields[8]
    source.charge = dict(zip(CHARGE_KEYS, fields[9:13]))
    source.charge_compensation = dict(zip(CHARGE_KEYS, fields[13:17]))
    if n > source.end_index or ei > len(source.events) or within < 0:
        raise SourceError('Source journal cursor leaves schedule')
    if within:
        if ei >= len(source.events) or within >= source.events[ei]['count']:
            raise SourceError('Source journal within-event count mismatch')
        source.current_state = source._physical_at(source.event_entering_state, source.events[ei]['current_A'], within)
    else:
        source.current_state = copy.deepcopy(source.event_entering_state)
    source.last_event_index = (ei if within else ei - 1) if n else None
    if n:
        if source.last_event_index is None or not 0 <= source.last_event_index < len(source.events):
            raise SourceError('Source journal last-event mismatch')
        source.last_current_A = source.events[source.last_event_index]['current_A']
        source.last_clean_voltage_V = source._clean_voltage(source.current_state, source.last_current_A)
    source.rng.bit_generator.state = {
        'bit_generator': 'PCG64',
        'state': {'state': int.from_bytes(fields[17], 'little'), 'inc': int.from_bytes(fields[18], 'little')},
        'has_uint32': fields[19], 'uinteger': fields[20]}
    source.hash_chain = fields[21]
    # Reuse full snapshot structural/physical validation without advancing it.
    return StatefulSource.from_state(source.snapshot(), expected_manifest=manifest,
                                     allow_primary=allow_primary).snapshot()


def _index_set(values):
    result = set(values)
    if any(type(value) is not int or value < 0 for value in result):
        raise SourceError('Query/checkpoint indices must be nonnegative integers')
    return result


def generate_files(source, end_index, output_dir, *, query_indices=(), checkpoint_indices=(),
                   chunk_size=35, max_output_bytes=536870912):
    """Stream bounded chunks; defer SIGINT/SIGTERM to complete output boundaries.

    Call from the worker's main thread. Previous handlers are restored on exit.
    A cooperative stop flushes the observation, truth and source journal files
    before raising SourceStopped and saving failure.json. No signal is allowed
    to split the RNG draw, physical-state update or record output transaction.
    """
    with _DeferredSourceSignals() as stop:
        return _generate_files(source, end_index, output_dir, query_indices=query_indices,
                               checkpoint_indices=checkpoint_indices, chunk_size=chunk_size,
                               max_output_bytes=max_output_bytes, stop=stop)


def _generate_files(source, end_index, output_dir, *, query_indices, checkpoint_indices,
                    chunk_size, max_output_bytes, stop):
    if type(end_index) is not int or not source.next_index <= end_index <= source.end_index:
        raise SourceError('Invalid generation endpoint')
    if type(chunk_size) is not int or not 1 <= chunk_size <= 4096:
        raise SourceError('Invalid host I/O chunk size')
    if type(max_output_bytes) is not int or max_output_bytes < 262144:
        raise SourceError('Output cap must reserve at least256KiB for checkpoint/failure metadata')
    queries = _index_set(query_indices) | {source.next_index}
    checkpoints = _index_set(checkpoint_indices)
    start = source.next_index
    out = Path(output_dir)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.mkdir(exist_ok=False)
    used, full_count, snapshot_files = 0, 0, []
    reserved_failure_bytes = 131072
    limit = max_output_bytes - reserved_failure_bytes
    digest_obs, digest_truth, digest_full, digest_journal = (hashlib.sha256() for _ in range(4))
    started = time.monotonic()
    initial_snapshot = source.snapshot()
    complete_record, complete_index = None, start
    generated_records, source_step_in_progress = 0, False
    flushed_index = None

    def write(stream, block):
        nonlocal used
        if used + len(block) > limit:
            raise SourceError('Generation output budget reached before write')
        written = stream.write(block)
        if type(written) is not int or not 0 <= written <= len(block):
            raise SourceError('Invalid output write count')
        used += written
        if written != len(block):
            raise SourceError('Incomplete output write')

    def write_json(path, obj):
        with path.open('xb') as stream:
            write(stream, canonical_bytes(obj) + b'\n')

    def checkpoint():
        name = 'source-cp-' + str(source.next_index) + '.json'
        envelope = source.snapshot()
        write_json(out / name, envelope)
        snapshot_files.append({'path': name, 'next_index': source.next_index,
                               'payload_sha256': envelope['sha256'], 'file_sha256': sha256_file(out / name)})

    try:
        write_json(out / 'source_manifest.json', source.manifest)
        with (out / 'observations.bin').open('xb') as obs_stream, (out / 'truth.bin').open('xb') as truth_stream, (out / 'truth.jsonl').open('xb') as full_stream, (out / 'source_states.bin').open('xb') as journal_stream:
            def check_stop():
                nonlocal flushed_index
                if stop.signum is not None:
                    for stream in (obs_stream, truth_stream, full_stream, journal_stream):
                        stream.flush()
                    flushed_index = complete_index
                    stop.check()

            def full_query():
                nonlocal full_count
                record = canonical_bytes(source.truth_query()) + b'\n'
                write(full_stream, record)
                digest_full.update(record)
                full_count += 1

            full_query()
            header = JOURNAL_HEADER.pack(b'SCMSRC01', 1, JOURNAL_RECORD_BYTES, start,
                                         end_index - start + 1, bytes.fromhex(source.source_id))
            header += JOURNAL_CHECK.pack(zlib.crc32(header), 0)
            write(journal_stream, header)
            digest_journal.update(header)
            def journal_state():
                record = _journal_record(source)
                write(journal_stream, record)
                digest_journal.update(record)
                return record
            record = journal_state()
            if source.next_index in checkpoints:
                checkpoint()
            complete_record = record
            check_stop()
            while source.next_index < end_index:
                # Chunks control scheduling only; fixed-size buffered file
                # writes preserve all committed records if a later step fails.
                for _ in range(min(chunk_size, end_index - source.next_index)):
                    check_stop()
                    if used + 64 + JOURNAL_RECORD_BYTES > limit:
                        raise SourceError('Generation output budget reached before draw')
                    source_step_in_progress = True
                    observation, truth = source.next_record()
                    generated_records += 1
                    source_step_in_progress = False
                    write(obs_stream, observation)
                    write(truth_stream, truth)
                    record = journal_state()
                    digest_obs.update(observation)
                    digest_truth.update(truth)
                    if source.next_index in queries:
                        full_query()
                    if source.next_index in checkpoints:
                        checkpoint()
                    complete_record, complete_index = record, source.next_index
                    check_stop()
        flushed_index = complete_index
        stop.check()
        write_json(out / 'source_final.json', source.snapshot())
        stop.check()
        receipt = {'schema': 'mumble_continuous_source_generation_v1', 'status': 'complete',
                   'source_id': source.source_id, 'manifest_sha256': source_id(source.manifest),
                   'fixture': source.manifest['fixture'], 'start_index': start, 'end_index': source.next_index,
                   'records': source.next_index - start, 'noise_draws_generated': source.next_index - start,
                   'observation_record_bytes': OBSERVATION.size, 'scalar_truth_record_bytes': SCALAR_TRUTH.size,
                   'observation_sha256': digest_obs.hexdigest(), 'scalar_truth_sha256': digest_truth.hexdigest(),
                   'full_truth_sha256': digest_full.hexdigest(), 'full_query_records': full_count,
                   'source_state_journal_sha256': digest_journal.hexdigest(),
                   'source_state_journal_record_bytes': JOURNAL_RECORD_BYTES,
                   'source_state_journal_header_bytes': JOURNAL_HEADER_BYTES,
                   'source_state_journal_records': source.next_index - start + 1,
                   'source_state_journal_bytes': JOURNAL_HEADER_BYTES + JOURNAL_RECORD_BYTES * (source.next_index - start + 1),
                   'final_hash_chain_hex': source.hash_chain.hex(), 'source_checkpoints': snapshot_files,
                   'final_snapshot_sha256': sha256_file(out / 'source_final.json'),
                   'charge': dict(source.charge), 'actual_elapsed_s': source.actual_elapsed_s,
                   'chunk_size_samples': chunk_size, 'bounded_record_payload_bytes': 64 + JOURNAL_RECORD_BYTES,
                   'output_bytes_before_receipt': used, 'output_limit_bytes': max_output_bytes,
                   'signal_stop_policy': 'SIGINT/SIGTERM deferred through complete record and flushed output/journal boundary.',
                   'wall_time_s': time.monotonic() - started}
        write_json(out / 'receipt.json', receipt)
        return receipt
    except BaseException as exc:
        # Never serialize a possibly half-mutated live source as resumable.
        # This fixed-size last-complete journal record predates an interrupted
        # step even when the last output record is partial or cannot be read.
        snapshot = (_snapshot_from_journal_record(complete_record, source.manifest,
                                                  allow_primary=source.allow_primary)
                    if complete_record is not None else initial_snapshot)
        exact_draws = None if source_step_in_progress else generated_records
        sizes = {}
        for name, size, header_bytes in [('observations.bin', OBSERVATION.size, 0),
                                        ('truth.bin', SCALAR_TRUTH.size, 0),
                                        ('source_states.bin', JOURNAL_RECORD_BYTES, JOURNAL_HEADER_BYTES)]:
            path = out / name
            if path.exists():
                total = path.stat().st_size
                payload_bytes = max(0, total - header_bytes)
                sizes[name] = {'bytes': total, 'complete_records': payload_bytes // size,
                               'trailing_bytes': payload_bytes % size,
                               'header_complete': total >= header_bytes}
        failure = {'schema': 'mumble_continuous_source_failure_v1', 'status': 'failed',
                   'error': type(exc).__name__ + ': ' + str(exc), 'start_index': start,
                   'next_index': complete_index, 'last_complete_record_index': complete_index,
                   'noise_draws_generated': exact_draws, 'noise_draws_exact': exact_draws is not None,
                   'noise_draws_generated_lower_bound': generated_records,
                   'noise_draws_generated_upper_bound': generated_records + int(source_step_in_progress),
                   'source_step_in_progress': source_step_in_progress,
                   'source_live_next_index_unvalidated': source.next_index,
                   'source_snapshot_scope': 'Last complete record boundary; never the in-progress live source.',
                   'signal_number': stop.signum, 'signal_count': stop.received,
                   'cooperative_stop': isinstance(exc, SourceStopped),
                   'outputs_flushed_through_index': flushed_index, 'persisted_binary_files': sizes,
                   'unknown_draw_reason': ('The interrupted scalar RNG/state transaction did not return; zero or one additional draw may have occurred.'
                                           if source_step_in_progress else None),
                   'normal_output_bytes': used, 'wall_time_s': time.monotonic() - started,
                   'source_snapshot': snapshot}
        block = canonical_bytes(failure) + b'\n'
        if used + len(block) <= max_output_bytes:
            with (out / 'failure.json').open('xb') as stream:
                stream.write(block)
        raise


def load_indices(path):
    if path is None:
        return []
    text = Path(path).read_text().strip()
    if not text:
        return []
    if text.startswith('['):
        return list(json.loads(text))
    return [int(word) for word in text.replace(',', ' ').split()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--end', type=int, required=True)
    parser.add_argument('--query-indices', type=Path)
    parser.add_argument('--checkpoint-indices', type=Path)
    parser.add_argument('--restore', type=Path)
    parser.add_argument('--allow-primary', action='store_true', help='Use only after executable receipt/source freeze.')
    parser.add_argument('--chunk-size', type=int, default=35)
    parser.add_argument('--max-output-bytes', type=int, default=536870912)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    source = (StatefulSource.from_state(json.loads(args.restore.read_text()), expected_manifest=manifest,
                                      allow_primary=args.allow_primary)
              if args.restore else StatefulSource(manifest, allow_primary=args.allow_primary))
    receipt = generate_files(source, args.end, args.output_dir,
                             query_indices=load_indices(args.query_indices),
                             checkpoint_indices=load_indices(args.checkpoint_indices),
                             chunk_size=args.chunk_size, max_output_bytes=args.max_output_bytes)
    print(json.dumps(receipt, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
