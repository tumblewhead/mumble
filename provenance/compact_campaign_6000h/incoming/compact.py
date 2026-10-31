"""Bounded plotting summaries and local C replay checkpoints; no raw stream files.

Summaries are visualization/scoring evidence only. The estimator receives the
original samples. Checkpoints retain the full pointer-free C context and are
bound to the exact binary, source files and host runtime, not a portable ABI.
"""
import copy
import csv
import ctypes as C
import hashlib
import json
import math
import platform
import sys
import time
from pathlib import Path

import numpy as np

from experiments.foster_feedback_001.plant import scalar_step
from specifications.evidence_feedback_001.protocol import digest
from .backend import CBackend, identity
from .charger import ChargeDischarge, DEFAULTS, EVENT_COLUMNS
from .stimulus import current, temperatures
from .telemetry import PARAMETERS, TRACE_COLUMNS, thermal, trace_row

CHUNK = 8192  # Multiple of the unchanged 16-record estimation window.


def atomic_json(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')
    temp.replace(path)


class StimulusStream:
    """Same scalar plant/controller/noise sequence as full recording, in chunks."""
    def __init__(self, config, cell, scenario, settings):
        self.config, self.cell, self.scenario, self.settings = config, cell, scenario, settings
        self.rate = settings['sample_rate_hz']
        self.ref = np.array([cell['parameters'][k] for k in PARAMETERS])
        self.state = cell['initial_state'].copy()
        self.index = 0
        self.rng = np.random.default_rng(scenario['seed'])
        self.controller = (ChargeDischarge({k: settings.get(k, v) for k, v in DEFAULTS.items()}, self.rate)
                           if scenario['load'] == 'charge-discharge' else None)
        self.failure = None

    def snapshot(self):
        return copy.deepcopy(dict(index=self.index, state=self.state,
                                  rng=self.rng.bit_generator.state,
                                  controller=vars(self.controller) if self.controller else None))

    def restore(self, state):
        self.index = state['index']
        self.state = list(state['state'])
        self.rng.bit_generator.state = state['rng']
        if self.controller:
            self.controller.__dict__.update(copy.deepcopy(state['controller']))
            sig = self.controller.last_signature
            self.controller.last_signature = tuple(sig) if sig is not None else None

    def read(self, count):
        s, scenario = self.settings, self.scenario
        ix = np.arange(self.index, self.index+count)
        currents = (np.empty(count) if self.controller else
                    current(ix, scenario['load'], s['current_a'], self.rate))
        temp = temperatures(ix, s['temperature'], s['temperature_mean_c'],
                            s['temperature_amplitude_c'], s['temperature_period_s'], self.rate)
        params = self.ref*thermal(self.config, temp)
        errors = self.rng.normal(0, scenario['noise_v'], count)
        sigma = math.sqrt(scenario['noise_v']**2+(1/1024)**2/12)
        obs, truth = np.empty((count, 5)), np.empty((count, 17))
        events = []
        valid = 0
        for j, index in enumerate(ix):
            index = int(index)
            if self.controller:
                currents[j] = self.controller.current(index)
                events.extend(self.controller.take_events())
            try:
                state, voltage = scalar_step(self.state, params[j], 1/self.rate, float(currents[j]),
                                             self.config['ocv_intercept_V'], self.config['ocv_slope_V_per_SOC'])
                code = math.floor((voltage+errors[j]-1.5)*1024+.5)
                if not 0 <= code <= 4095:
                    raise ValueError('voltage ADC range; no clipping')
            except ValueError as e:
                self.failure = dict(index=index, reason=str(e))
                break
            self.state = state
            measured = 1.5+code/1024
            obs[j] = 1/self.rate, currents[j], temp[j], measured, sigma
            truth[j] = *state, *params[j], voltage
            self.index += 1
            valid += 1
            if self.controller:
                self.controller.observe(index, measured)
                events.extend(self.controller.take_events())
        return obs[:valid], truth[:valid], events


class Bins:
    """Fixed-duration bins with sample counts, exact extrema and summed values."""
    def __init__(self, records, bins, columns):
        self.records, self.bins = records, min(records, bins)
        self.count = np.zeros(self.bins, dtype=np.int64)
        self.first = np.full(self.bins, np.iinfo(np.int64).max, dtype=np.int64)
        self.last = np.zeros(self.bins, dtype=np.int64)
        self.low = np.full((self.bins, columns), np.inf)
        self.high = np.full((self.bins, columns), -np.inf)
        self.total = np.zeros((self.bins, columns))

    def add(self, counts, values):
        counts = np.asarray(counts, dtype=np.int64)
        values = np.asarray(values)
        if not len(counts):
            return
        ids = (counts-1)*self.bins//self.records
        boundaries = np.r_[0, np.flatnonzero(np.diff(ids))+1, len(ids)]
        for start, end in zip(boundaries[:-1], boundaries[1:]):
            b = ids[start]
            rows = values[start:end]
            self.count[b] += end-start
            self.first[b] = min(self.first[b], counts[start])
            self.last[b] = max(self.last[b], counts[end-1])
            self.low[b] = np.minimum(self.low[b], rows.min(axis=0))
            self.high[b] = np.maximum(self.high[b], rows.max(axis=0))
            self.total[b] += rows.sum(axis=0)

    def arrays(self, prefix):
        used = self.count > 0
        return {prefix+'_'+k: v[used] for k, v in
                dict(count=self.count, first=self.first, last=self.last, low=self.low,
                     high=self.high, mean=self.total/np.maximum(self.count[:, None], 1)).items()}


def runtime_identity():
    return dict(python=sys.version, numpy=np.__version__, machine=platform.machine(),
                system=platform.system(), libc=platform.libc_ver(), byteorder=sys.byteorder)


def replay_binding(campaign, case):
    """Validate current replay code against the run's archived source identities."""
    from .backend import ROOT
    plan = json.loads((campaign/'campaign_plan.json').read_text())
    reserved = json.loads((campaign/'reservation.json').read_text())['source_identities']
    names = ['compact.py', 'replay.py', 'backend.py', 'stimulus.py', 'charger.py', 'rate.py', 'telemetry.py']
    expected = {f'experiments/foster_campaign_001/{n}': plan['campaign_sources'][f'experiments/foster_campaign_001/{n}']
                for n in names}
    name = 'experiments/foster_feedback_001/plant.py'
    expected[name] = reserved[name]
    for name, value in expected.items():
        if identity(ROOT/name) != value:
            raise ValueError('Replay source differs from recorded run: '+name)
    # The ctypes ABI/readout adapter is outside the editable campaign package.
    # Bind its actual bytes too; metadata comparison rejects a later change.
    adapter = 'experiments/foster_c_baseline_001/reference.py'
    expected[adapter] = identity(ROOT/adapter)
    return dict(runtime=runtime_identity(), sources=expected,
                binary=identity(campaign/'backend_c/estimator.so'),
                calibration=identity(campaign/'calibration.json'),
                plan=identity(campaign/'campaign_plan.json'), scenario=identity(case/'scenario.json'))


def checkpoint(out, stream, banks, stats, source, model_id, binding, entries):
    """Only checkpoint a shared committed boundary; never replay a posterior twice."""
    active = [k for k in banks if stats[k]['status'] in ('running', 'completed')]
    if any(banks[k].counts()['retired_records'] != stream.index or
           banks[k].counts()['pending_records'] for k in active):
        raise ValueError('checkpoint requires aligned committed estimator/plant boundary')
    directory = out/'checkpoints'
    directory.mkdir(exist_ok=True)
    name = f'checkpoint_{stream.index:012d}.npz'
    metadata = dict(schema='foster_local_checkpoint_v1', sequence=stream.index,
                    source_id=source, model_id=model_id, binding=binding,
                    stimulus=stream.snapshot(), active=active, stats=copy.deepcopy(stats))
    arrays = {k: np.frombuffer(bytes(bank.context), dtype=np.uint8) for k, bank in banks.items()}
    arrays['metadata'] = np.frombuffer(json.dumps(metadata, allow_nan=False).encode(), dtype=np.uint8)
    temp = directory/(name+'.tmp')
    with temp.open('xb') as f:
        np.savez_compressed(f, **arrays)
    temp.replace(directory/name)
    entries.append(dict(sequence=stream.index, file=name, **identity(directory/name)))
    atomic_json(directory/'index.json', dict(schema='foster_local_checkpoint_index_v1', checkpoints=entries))


def restore_checkpoint(case, entry, config, cell, scenario, settings):
    campaign = case.parent
    path = case/'checkpoints'/entry['file']
    if identity(path) != {k: entry[k] for k in ['bytes', 'sha256']}:
        raise ValueError('Checkpoint checksum mismatch')
    with np.load(path, allow_pickle=False) as data:
        metadata = json.loads(data['metadata'].tobytes())
        # JSON normalizes runtime tuples to arrays.
        if metadata['binding'] != json.loads(json.dumps(replay_binding(campaign, case))):
            raise ValueError('Checkpoint binary, runtime or source identity mismatch')
        if metadata['sequence'] != entry['sequence']:
            raise ValueError('Checkpoint sequence mismatch')
        stream = StimulusStream(config, cell, scenario, settings)
        stream.restore(metadata['stimulus'])
        banks = {}
        for kind in metadata['active']:
            bank = CBackend(campaign, config, metadata['source_id'], metadata['model_id'], kind, stream.rate)
            state = data[kind].tobytes()
            if len(state) != C.sizeof(bank.context):
                raise ValueError('Checkpoint context size mismatch')
            C.memmove(bank.context, state, len(state))
            if bank.counts()['retired_records'] != stream.index or bank.counts()['pending_records']:
                raise ValueError('Restored context boundary mismatch')
            banks[kind] = bank
    return stream, banks, metadata


def run_compact(out, campaign, config, model_id, scenario, cell, args):
    from .run import metrics, score, finish
    from experiments.foster_feedback_001.history import numeric_storage
    out.mkdir()
    started = last_print = time.perf_counter()
    settings = vars(args).copy()
    rate = args.sample_rate_hz
    n = round(args.hours*3600*rate)
    kinds = ['float64', 'float32'] if args.encoding == 'both' else [args.encoding]
    recipe = dict(scenario=scenario, cell_definition=cell, settings=settings, model_id=model_id)
    # Identity is bound before streaming; actual observation bytes are hashed below.
    source = digest(dict(kind='deterministic_stimulus_recipe_v1', recipe=recipe))
    atomic_json(out/'scenario.json', dict(**scenario, cell_definition=cell, sample_rate_Hz=rate,
                backend='c', recording='compact', recipe=recipe))
    stream = StimulusStream(config, cell, scenario, settings)
    banks = {k: CBackend(campaign, config, source, model_id, k, rate) for k in kinds}
    stats = {k: dict(status='running', all=metrics(), current_nonzero=metrics(), current_zero=metrics(),
                    outputs=0, stops={}, storage={**numeric_storage(k), **banks[k].storage()}) for k in kinds}
    bins = {'plant': Bins(n, args.summary_bins, 25)}
    bins.update({k: Bins(n, args.summary_bins, len(TRACE_COLUMNS)+32+4) for k in kinds})
    interval = max(CHUNK, math.ceil(args.checkpoint_hours*3600*rate/CHUNK)*CHUNK)
    binding = replay_binding(campaign, out)
    entries = []
    checkpoint(out, stream, banks, stats, source, model_id, binding, entries)
    obs_hash, truth_hash = hashlib.sha256(), hashlib.sha256()
    encoding = dict(Q_percent=0., SOC_pp=0., paired_outputs=0) if len(kinds) == 2 else None
    with (out/'stimulus_events.csv').open('x', newline='') as events_file:
        writer = csv.DictWriter(events_file, fieldnames=EVENT_COLUMNS)
        writer.writeheader()
        while stream.index < n:
            begin = stream.index
            obs, truth, events = stream.read(min(CHUNK, n-begin))
            writer.writerows(events)
            obs_hash.update(obs.astype('<f8', copy=False).tobytes())
            truth_hash.update(truth.astype('<f8', copy=False).tobytes())
            capacitances = truth[:, [8,10,12]]/truth[:, [7,9,11]]
            bins['plant'].add(np.arange(begin+1, stream.index+1), np.c_[obs, truth, capacitances])
            # Buffer one chunk's readouts; reduces summaries without per-output allocation overhead.
            outputs = {k: [] for k in kinds}
            for offset in range(0, len(obs), 16):
                block = obs[offset:offset+16]
                endpoint = offset+len(block)-1
                row, target = block[-1], truth[endpoint]
                reads = {}
                for k, bank in banks.items():
                    stat = stats[k]
                    if stat['status'] != 'running':
                        continue
                    try:
                        r, d = bank.advance(begin+offset, block)
                    except (ValueError, RuntimeError, np.linalg.LinAlgError, OverflowError) as e:
                        stat.update(status='unresolved', failure=dict(index=bank.failure_index, reason=str(e)))
                        continue
                    output = trace_row(r, row, config)
                    errors = [100*(output[11]/target[5]-1), 100*(output[6]-target[0]),
                              1000*(output[5]-row[3]), 1000*(output[5]-target[16])]
                    outputs[k].append(np.r_[output, r['chart_mean'], r['chart_sd'], errors])
                    stat['outputs'] += 1
                    score(stat['all'], r, target)
                    score(stat['current_nonzero' if row[1] != 0 else 'current_zero'], r, target)
                    stat['stops'][d['stop']] = stat['stops'].get(d['stop'], 0)+1
                    reads[k] = r
                if len(reads) == 2:
                    a, b = reads['float64'], reads['float32']
                    encoding['paired_outputs'] += 1
                    encoding['Q_percent'] = max(encoding['Q_percent'], abs(100*(b['Q']/a['Q']-1)))
                    encoding['SOC_pp'] = max(encoding['SOC_pp'], abs(100*(b['SOC']-a['SOC'])))
                if all(s['status'] != 'running' for s in stats.values()):
                    break
            for k, values in outputs.items():
                if values:
                    values = np.asarray(values)
                    bins[k].add(values[:, 0], values)
            if stream.failure or all(s['status'] != 'running' for s in stats.values()):
                break
            if stream.index % interval == 0 or stream.index == n:
                checkpoint(out, stream, banks, stats, source, model_id, binding, entries)
                print(json.dumps(dict(case=out.name, checkpoint_hours=stream.index/(3600*rate))), flush=True)
            if time.perf_counter()-last_print >= 25:
                print(json.dumps(dict(case=out.name, simulated_hours=stream.index/(3600*rate),
                                      wall_s=time.perf_counter()-started, recording='compact')), flush=True)
                last_print = time.perf_counter()
    for k, bank in banks.items():
        stat = stats[k]
        if stat['status'] == 'running':
            stat['status'] = 'plant_failed' if stream.failure else 'completed'
        stat.update(bank.counts())
        np.save(out/(k+'_message.npy'), bank.full_message())
        for bucket in ['all', 'current_nonzero', 'current_zero']:
            finish(stat[bucket])
    data = {}
    for name, summary in bins.items():
        data.update(summary.arrays(name))
    np.savez_compressed(out/'plot_summary.npz', **data)
    atomic_json(out/'inputs.json', dict(status=('plant_failed' if stream.failure else
                                              'generated' if stream.index == n else 'generated_prefix'),
                requested_records=n, valid_records=stream.index, failure=stream.failure,
                sample_rate_Hz=rate, observation_sha256=obs_hash.hexdigest(), truth_sha256=truth_hash.hexdigest(),
                hash_format='C-order little-endian float64 row bytes, without NPY header',
                source_identity='recipe bound before streaming; independent content hashes above'))
    atomic_json(out/'telemetry.json', dict(recording='compact', bins=args.summary_bins,
                plant_columns=['dt_s','current_A','temperature_C','voltage_V','sigma_V']+
                              ['truth_'+str(i) for i in range(17)]+['C1_F','C2_F','C3_F'],
                estimate_columns=TRACE_COLUMNS+['chart_mean_'+str(i) for i in range(16)]+
                                 ['chart_sd_'+str(i) for i in range(16)]+
                                 ['Q_error_percent','SOC_error_pp','V_measured_error_mV','V_truth_error_mV'],
                bin_semantics='Counts, mean and min/max of actual samples; derived quantities evaluated before reduction. No interpolation or estimator input reduction.',
                checkpoint_interval_records=interval, checkpoint_interval_hours=interval/(3600*rate),
                replay_scope='Same binary, sources and host runtime only; complete joint context, plant, controller and RNG. Not portable firmware persistence.',
                raw_telemetry_saved=False))
    result = dict(status='completed' if all(s['status']=='completed' for s in stats.values()) else 'unresolved',
                  scenario=scenario, arms=stats, records=stream.index, requested_records=n,
                  source_id=source, model_id=model_id, recording='compact', sample_rate_Hz=rate, backend='c',
                  simulation_hours=stream.index/(3600*rate), encoding_difference=encoding,
                  charger=stream.controller.summary() if stream.controller else None,
                  failure=stream.failure, wall_s_before_plots=time.perf_counter()-started,
                  coverage_validated=False, aging_implemented=False)
    if not args.no_plots:
        from .plot import render
        try:
            render(out, result, config, cell)
            result['plots'] = 'completed'
        except Exception as e:
            import traceback
            result['plots'] = dict(status='failed', reason=str(e))
            (out/'plot_error.txt').write_text(traceback.format_exc())
    atomic_json(out/'result.json', result)
    return result
