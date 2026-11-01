"""Isolated worker: import estimator code exclusively from the frozen replay root."""
import argparse
import ctypes as C
import json
import os
from pathlib import Path
import sys
import time
import traceback
import tracemalloc


def run(job):
    root = Path(job['replay_root']).resolve()
    sys.path.insert(0, str(root))
    import numpy as np
    from experiments.foster_campaign_001 import compact
    from experiments.foster_campaign_001.backend import ROOT
    from experiments.foster_feedback_001.estimator import Model
    from support import (ARMS, identity, write_json, capture, restore, same_arrays,
                         distribution, Phases, c_profile, profile_delta, memory, geometry)
    from forecast import predict
    from scoring import score
    if ROOT.resolve() != root:
        raise ValueError('worker imported an unexpected estimator root')
    campaign = Path(job['campaign'])
    prefix = job['prefix']
    case = campaign/prefix['case']
    destination = Path(job['out'])
    inputs = job['inputs']
    for name in ('summary', 'campaign_plan', 'calibration'):
        if identity(campaign/(name+'.json')) != inputs[name]:
            raise ValueError('source campaign identity mismatch: '+name)
    config = json.loads((campaign/'calibration.json').read_text())
    settings = json.loads((campaign/'campaign_plan.json').read_text())['configuration']
    scenario_file = json.loads((case/'scenario.json').read_text())
    scenario = {k: scenario_file[k] for k in ('cell', 'load', 'noise_v', 'seed', 'load_seed') if k in scenario_file}
    if scenario != prefix['scenario']:
        raise ValueError('selected scenario identity mismatch')
    rate = settings['sample_rate_hz']
    if rate != inputs['sample_rate_Hz']:
        raise ValueError('rate mismatch')
    stream, all_banks, metadata = compact.restore_checkpoint(case, prefix['checkpoint'], config,
        scenario_file['cell_definition'], scenario, settings)
    banks = {k: all_banks[k] for k in ARMS}
    del all_banks
    start = stream.index
    count = job['records']
    if start+count > round(settings['hours']*3600*rate):
        raise ValueError('requested suffix exceeds original campaign')
    if banks['field64'].interval != banks['tangent64'].interval:
        raise ValueError('unmatched refresh cadence')
    interval = banks['field64'].interval
    refresh = (start//interval+1)*interval
    anchors_at = {refresh-16: 'before_refresh', refresh: 'after_refresh',
                  refresh+(interval//32)*16: 'mid_interval'}
    if min(anchors_at) <= start or max(anchors_at) > start+count:
        raise ValueError('suffix must contain all three declared forecast anchors')
    original = {k: capture(b) for k, b in banks.items()}
    # Original owned estimator state exports contain no plant truth. Replay
    # binding is retained; these files are not advertised as portable firmware.
    export = {}
    for kind, saved in original.items():
        export.update({kind+'__'+k: v for k, v in saved.items()})
        export[kind+'__public_prior_mean'] = banks[kind].mean.copy()
        export[kind+'__public_prior_root'] = banks[kind].prior_root.copy()
    np.savez_compressed(destination/'initial_estimator_state.npz', **export)
    write_json(destination/'initial_estimator_state.json', dict(schema='tangent_study_bound_export_v1',
        source_id=metadata['source_id'], model_id=metadata['model_id'], sequence=start,
        sample_rate_Hz=rate, config=config, settings=settings, binding=metadata['binding'],
        checkpoint=prefix['checkpoint'], ownership='Original prior once; complete contexts and field/live/pending/tangent arrays; no truth; same ABI/source/runtime only',
        payload=identity(destination/'initial_estimator_state.npz')))
    obs_parts, truth_parts = [], []
    for offset in range(0, count, compact.CHUNK):
        obs, truth, _ = stream.read(min(compact.CHUNK, count-offset))
        if stream.failure or len(obs) != min(compact.CHUNK, count-offset):
            raise ValueError('original stimulus continuation failed: '+str(stream.failure))
        obs_parts.append(obs)
        truth_parts.append(truth)
    observations, truth = np.vstack(obs_parts), np.vstack(truth_parts)
    np.save(destination/'observations.npy', observations)
    # Separate scoring file; never supplied to the estimator or predictor.
    np.save(destination/'scoring_truth.npy', truth)
    write_json(destination/'scoring_truth.json', dict(reference_parameters=stream.ref.tolist(),
        scope='Harness-only continuation, isolated from estimator export and forecast inputs'))
    # Export/import continuation test, including all checkpoint array contents.
    parity = {}
    with np.load(destination/'initial_estimator_state.npz', allow_pickle=False) as data:
        for kind, bank in banks.items():
            bank.advance(start, observations[:16])
            bank.advance(start+16, observations[16:32])
            direct, message = capture(bank), bank.full_message()
            saved = {k: data[kind+'__'+k] for k in original[kind]}
            restore(bank, saved)
            if not same_arrays(capture(bank), saved):
                raise ValueError('export/import bytes changed')
            bank.advance(start, observations[:16])
            bank.advance(start+16, observations[16:32])
            imported = capture(bank)
            # C context includes host timer counters, deliberately not numerical state.
            exact = np.array_equal(message, bank.full_message()) and same_arrays(
                {k: v for k, v in direct.items() if k != 'context'},
                {k: v for k, v in imported.items() if k != 'context'})
            if not exact:
                raise ValueError('derived-state numerical continuation parity failed: '+kind)
            parity[kind] = dict(status='bitwise_message_and_history_arrays', records=32,
                                context_comparison='raw context import exact; after advance host timing bytes excluded, published numerical state and all extra arrays compared')
            restore(bank, original[kind])
    write_json(destination/'binding_parity.json', dict(binding=metadata['binding'], parity=parity,
        observation_identity=identity(destination/'observations.npy'), scoring_truth_identity=identity(destination/'scoring_truth.npy')))
    anchors = {}
    timing = {k: [] for k in ARMS}
    final_messages = {}
    failures = []
    def advance(bank, first, block):
        before = bank.audit['attempts']
        tick = time.perf_counter()
        result = bank.advance(first, block)
        elapsed = time.perf_counter()-tick
        return elapsed, bank.audit['attempts'] != before, result
    for repeat in range(job['repetitions']):
        for kind, bank in banks.items():
            restore(bank, original[kind])
        active = set(ARMS)
        for offset in range(0, count, 16):
            first = start+offset
            block = observations[offset:offset+16]
            order = ARMS if (repeat+offset//16)%2 == 0 else ARMS[::-1]
            for kind in order:
                if kind not in active:
                    continue
                bank = banks[kind]
                try:
                    elapsed, refreshed, (_, diagnostic) = advance(bank, first, block)
                    timing[kind].append(dict(repeat=repeat, sequence=first+16, seconds=elapsed,
                                              refresh=refreshed, stop=diagnostic['stop']))
                except (ValueError, RuntimeError, OverflowError, FloatingPointError, np.linalg.LinAlgError) as e:
                    failures.append(dict(stage='timing', arm=kind, repeat=repeat, first=first, reason=str(e)))
                    active.remove(kind)
                    continue
                if repeat == 0 and first+16 in anchors_at:
                    boundary = first+16
                    anchors.setdefault(boundary, dict(phase=anchors_at[boundary], arms={},
                        truth_state=truth[offset+15, :5].copy(), temperature_C=float(block[-1, 2])))
                    anchors[boundary]['arms'][kind] = dict(saved=capture(bank), message=bank.full_message(),
                                                          counts=bank.counts(), stop=diagnostic['stop'])
            if not active:
                break
        for kind in active:
            message = banks[kind].full_message()
            if kind in final_messages and not np.array_equal(message, final_messages[kind]):
                raise ValueError('fresh restore timing repeats differ numerically')
            final_messages[kind] = message
        print(json.dumps(dict(prefix=prefix['case'], start=start, timing_repeat=repeat+1)), flush=True)
    profile = {}
    for kind, bank in banks.items():
        restore(bank, original[kind])
        census = memory(bank)
        phases = Phases()
        before = c_profile(bank)
        with phases.instrument(bank):
            for offset in range(0, count, 16):
                try:
                    bank.advance(start+offset, observations[offset:offset+16])
                except (ValueError, RuntimeError, OverflowError, FloatingPointError, np.linalg.LinAlgError) as e:
                    failures.append(dict(stage='instrumented', arm=kind, first=start+offset, reason=str(e)))
                    break
        instrumentation_parity = kind in final_messages and np.array_equal(bank.full_message(), final_messages[kind])
        if kind in final_messages and not instrumentation_parity:
            raise ValueError('instrumentation changed numerical result')
        report = phases.report()
        base_total = sum(v['seconds'] for v in timing[kind])/job['repetitions']
        report['instrumented_over_uninstrumented_ratio'] = report['inclusive_seconds']['advance']['total']/base_total if base_total else None
        report['numerical_parity'] = instrumentation_parity
        report['rolling_C_profile_delta'] = profile_delta(before, c_profile(bank))
        report['objective_calls'] = bank.objective.calls
        # Separate memory pass: tracing overhead must not contaminate timings.
        restore(bank, original[kind])
        tracemalloc.start()
        try:
            for offset in range(0, count, 16):
                bank.advance(start+offset, observations[offset:offset+16])
            traced_current, traced_peak = tracemalloc.get_traced_memory()
            census['advance_pass_traced_allocations_B'] = dict(current=traced_current, peak=traced_peak,
                semantics='Additional traced allocations during full suffix; baseline objects excluded. Python tracer metadata overhead excluded. Native untraced work and stack unknown.')
        except (ValueError, RuntimeError, OverflowError, FloatingPointError, np.linalg.LinAlgError) as e:
            census['memory_pass_failure'] = str(e)
        finally:
            tracemalloc.stop()
        census['phase_lifetimes'] = dict(always='bank/prior/tables/context/raw buffer/dense root',
            recurrence='live state copy and n by 82 response rows',
            field_flush='4096 by 82 rows plus stacked QR input and LAPACK work, coexists with persistent bank',
            refresh='field flush then nonlinear solve, roots and transport; native tangent workspace remains allocated',
            readout='joint endpoint root and output carrier coexist with native query workspace')
        report['operation_accounting'] = dict(field_QR=report['qr_shapes_and_calls'],
            tangent_update='For each lifted row: 16D whitening and 17-column Givens QR; dimensions/call counts recorded',
            nonlinear_solve='16D GN with up to 60 rounds and 18 trial fractions; actual diagnostics recorded',
            unavailable='Exact dynamic scalar/transcendental counts and M23 instruction cycles are not instrumented; no estimated total is substituted')
        values = timing[kind]
        profile[kind] = dict(uninstrumented_seconds=distribution([v['seconds'] for v in values]),
            refresh_seconds=distribution([v['seconds'] for v in values if v['refresh']]),
            ordinary_seconds=distribution([v['seconds'] for v in values if not v['refresh']]),
            phases=report, memory=census)
    write_json(destination/'timing_windows.json', timing)
    write_json(destination/'profile.json', profile)
    forecasts = []
    model = Model((campaign/'backend_c/estimator.so').resolve(), config)
    for boundary in sorted(anchors_at):
        anchor = anchors.get(boundary)
        if anchor is None:
            failures.append(dict(stage='forecast_anchor', sequence=boundary, reason='no surviving arm'))
            continue
        exported = {}
        scoring = dict(truth_state=anchor['truth_state'].tolist(), reference_parameters=stream.ref.tolist())
        write_json(destination/f'anchor_{boundary}_scoring.json', scoring)
        for kind, a in anchor['arms'].items():
            exported.update({kind+'__'+k: v for k, v in a['saved'].items()})
        np.savez_compressed(destination/f'anchor_{boundary}_estimator.npz', **exported)
        write_json(destination/f'anchor_{boundary}.json', dict(sequence=boundary, phase=anchor['phase'],
            source_id=metadata['source_id'], temperature_C=anchor['temperature_C'],
            arms={k: dict(counts=a['counts'], stop=a['stop']) for k, a in anchor['arms'].items()},
            source_interval_current_range_A=[float(observations[:boundary-start, 1].min()), float(observations[:boundary-start, 1].max())],
            excitation_scope='Observed suffix range only; entire prior-prefix excitation support not certified',
            estimator_payload=identity(destination/f'anchor_{boundary}_estimator.npz')))
        for task in job['tasks']:
            frozen = {}
            for kind in ARMS:
                if kind not in anchor['arms']:
                    continue
                bank = banks[kind]
                restore(bank, anchor['arms'][kind]['saved'])
                before = capture(bank)
                msg = bank.full_message()
                variants = [(kind, msg[:16], msg[16:272].reshape(16, 16), None)]
                if kind == 'tangent64':
                    try:
                        m, L, transport = geometry(bank)
                        variants.append(('tangent64_geometry', m, L, transport))
                    except (ValueError, OverflowError, np.linalg.LinAlgError) as e:
                        frozen['tangent64_geometry'] = dict(status='unresolved', reason=str(e))
                for label, m, L, transport in variants:
                    try:
                        p = predict(model, m, L, task, config, anchor['temperature_C'], rate, transport=transport)
                        frozen[label] = dict(status='predicted', prediction=p,
                                             endpoint=m.copy() if transport is None else transport(m)[0])
                    except (ValueError, OverflowError, FloatingPointError, np.linalg.LinAlgError) as e:
                        frozen[label] = dict(status='unresolved', reason=str(e))
                if not same_arrays(before, capture(bank)):
                    raise ValueError('forecast mutated owned history')
            # All arm forecasts are frozen before the scorer receives truth.
            for label in ('field64', 'tangent64', 'tangent64_geometry'):
                item = frozen.get(label, dict(status='unresolved', reason='arm unavailable at anchor'))
                row = dict(sequence=boundary, phase=anchor['phase'], arm=label, task=task['id'],
                           temperature_C=anchor['temperature_C'])
                suffix = observations[:boundary-start, 1]
                currents = [s['current_A'] for s in task['segments']]
                row['outside_observed_suffix_current_range'] = min(currents) < suffix.min() or max(currents) > suffix.max()
                row['outside_observed_suffix_current_range'] = bool(row['outside_observed_suffix_current_range'])
                if item['status'] == 'predicted':
                    p = item['prediction']
                    row.update(status='diagnostic', prediction={k: v for k, v in p.items() if not isinstance(v, np.ndarray)})
                    np.savez_compressed(destination/f'forecast_{boundary}_{label}_{task["id"]}.npz',
                        **{k: v for k, v in p.items() if isinstance(v, np.ndarray)})
                    try:
                        row['scoring'] = score(p, anchor['truth_state'], stream.ref, task, config,
                                               anchor['temperature_C'], rate, item['endpoint'])
                    except (ValueError, OverflowError, FloatingPointError) as e:
                        row.update(status='scoring_unresolved', scoring_reason=str(e))
                else:
                    row.update(item)
                forecasts.append(row)
            print(json.dumps(dict(prefix=prefix['case'], sequence=boundary, task=task['id'], status='forecast_scored')), flush=True)
    write_json(destination/'forecasts.json', forecasts)
    result = dict(status='completed_diagnostic' if not failures else 'partial_unresolved',
        prefix=prefix, source_id=metadata['source_id'], sample_rate_Hz=rate, records=count,
        repetitions=job['repetitions'], profile='profile.json', forecasts='forecasts.json', failures=failures,
        forecast_rows=len(forecasts), unresolved_forecasts=sum(r['status'] != 'diagnostic' for r in forecasts),
        anchors_expected=anchors_at, binding_and_export_parity=parity,
        host=dict(runtime=compact.runtime_identity(), thread_environment={k: os.environ.get(k) for k in
                  ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')}),
        qualification='Development witnesses only. Uncalibrated local uncertainty; no hardware admission, aging or M23 qualification.',
        low_SOC=dict(minimum_truth_SOC=float(truth[:, 0].min()),
            status='Low-SOC coverage not certified; causal discharge continuation is a separate follow-up, never a truth reset'),
        identity=identity(Path(__file__)))
    write_json(destination/'result.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job', type=Path)
    args = parser.parse_args()
    job = json.loads(args.job.read_text())
    try:
        result = run(job)
    except Exception as error:
        failure = dict(status='failed', error=str(error), traceback=traceback.format_exc())
        (Path(job['out'])/'result.json').write_text(json.dumps(failure, indent=2)+'\n')
        raise
    raise SystemExit(0 if result['status'] == 'completed_diagnostic' else 1)
