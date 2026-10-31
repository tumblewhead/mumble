"""Regenerate a full-resolution interval from a compact campaign checkpoint."""
import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np

from .compact import CHUNK, atomic_json, restore_checkpoint
from .charger import EVENT_COLUMNS
from .workload import EVENT_COLUMNS as WORKLOAD_COLUMNS
from .telemetry import TRACE_COLUMNS, trace_row


def replay(case, destination, start_hour, duration_s=10., plots=True, *, stop_hour=None):
    if stop_hour is not None:
        if not math.isfinite(stop_hour) or stop_hour <= start_hour:
            raise ValueError("Debug stop hour must be finite and greater than start hour")
        duration_s = (stop_hour-start_hour)*3600
    if not math.isfinite(start_hour) or start_hour < 0 or not math.isfinite(duration_s) or duration_s <= 0:
        raise ValueError('Finite nonnegative start hour and positive duration required')
    campaign = case.parent
    plan = json.loads((campaign/'campaign_plan.json').read_text())
    settings = plan['configuration']
    if settings.get('recording') != 'compact':
        raise ValueError('Replay requires a campaign recorded with --recording compact')
    rate = settings['sample_rate_hz']
    n = round(settings['hours']*3600*rate)
    first = math.floor(start_hour*3600*rate)
    requested_stop = stop_hour*3600 if stop_hour is not None else start_hour*3600+duration_s
    end = min(n, math.floor(requested_stop*rate))
    if not 0 <= first < end <= n:
        raise ValueError('Requested interval contains no samples inside the recorded campaign duration')
    inputs_path = case/'inputs.json'
    if inputs_path.exists() and first >= json.loads(inputs_path.read_text())['valid_records']:
        raise ValueError('Debug window starts after the recorded plant prefix')
    scenario_file = json.loads((case/'scenario.json').read_text())
    cell = scenario_file['cell_definition']
    scenario = {k: scenario_file[k] for k in ['cell','load','noise_v','seed']}
    if 'load_seed' in scenario_file:
        scenario['load_seed'] = scenario_file['load_seed']
    config = json.loads((campaign/'calibration.json').read_text())
    entries = json.loads((case/'checkpoints/index.json').read_text())['checkpoints']
    eligible = [entry for entry in entries if entry['sequence'] <= first]
    if not eligible:
        raise ValueError('No preceding checkpoint available')
    entry = max(eligible, key=lambda e: e['sequence'])
    stream, banks, metadata = restore_checkpoint(case, entry, config, cell, scenario, settings)
    if not banks:
        raise ValueError('No active estimator at the selected checkpoint')
    destination.mkdir(parents=True, exist_ok=False)
    print(json.dumps(dict(replay_checkpoint_hours=stream.index/(3600*rate),
                          requested_start_hour=start_hour, warmup_seconds=(first-stream.index)/rate)), flush=True)
    arrays = {name: np.lib.format.open_memmap(destination/(name+'.npy'), mode='w+', dtype='float64',
                                             shape=(end-first, columns))
              for name, columns in [('observations',5),('truth',17)]}
    traces = {kind: np.lib.format.open_memmap(destination/(kind+'_trace.npy'), mode='w+', dtype='float64',
                                             shape=((end-first)//16+2, len(TRACE_COLUMNS))) for kind in banks}
    charts = {kind: np.lib.format.open_memmap(destination/(kind+'_chart.npy'), mode='w+', dtype='float64',
                                             shape=((end-first)//16+2, 32)) for kind in banks}
    arms = {kind: dict(status='running', outputs=0) for kind in banks}
    # Never retire a different-sized window solely to stop at a requested timestamp.
    stop = min(n, math.ceil(end/16)*16)
    valid = 0
    with (destination/'stimulus_events.csv').open('x',newline='') as f, \
         (destination/'workload_events.csv').open('x',newline='') as wf:
        writer = csv.DictWriter(f, fieldnames=EVENT_COLUMNS)
        writer.writeheader()
        workload_writer = csv.DictWriter(wf, fieldnames=WORKLOAD_COLUMNS)
        workload_writer.writeheader()
        while stream.index < stop:
            begin = stream.index
            obs, truth, events = stream.read(min(CHUNK, stop-begin))
            writer.writerows(e for e in events if first <= e['record_count'] <= end)
            workload_writer.writerows(e for e in stream.workload_events
                                      if first*1_000_000 <= e['start_us']*rate < end*1_000_000)
            a, b = max(first, begin), min(end, stream.index)
            if b > a:
                arrays['observations'][a-first:b-first] = obs[a-begin:b-begin]
                arrays['truth'][a-first:b-first] = truth[a-begin:b-begin]
                valid += b-a
            for offset in range(0,len(obs),16):
                block = obs[offset:offset+16]
                for kind, bank in banks.items():
                    stat = arms[kind]
                    if stat['status'] != 'running':
                        continue
                    try:
                        r, _ = bank.advance(begin+offset, block)
                    except (ValueError, RuntimeError, np.linalg.LinAlgError, OverflowError) as e:
                        stat.update(status='unresolved', failure=dict(index=bank.failure_index, reason=str(e)))
                        continue
                    if first < r['records'] <= end:
                        ix = stat['outputs']
                        traces[kind][ix] = trace_row(r, block[-1], config)
                        charts[kind][ix] = r['chart_mean']+r['chart_sd']
                        stat['outputs'] += 1
            if stream.failure or all(a['status'] != 'running' for a in arms.values()):
                break
    for kind, bank in banks.items():
        if arms[kind]['status'] == 'running':
            arms[kind]['status'] = 'plant_failed' if stream.failure else 'completed'
        arms[kind].update(bank.counts())
        np.save(destination/(kind+'_message.npy'), bank.full_message())
    for array in [*arrays.values(), *traces.values(), *charts.values()]:
        array.flush()
    result = dict(status='completed' if all(a['status']=='completed' for a in arms.values()) else 'unresolved',
                  scenario=scenario, sample_rate_Hz=rate, records=valid, record_offset=first, arms=arms,
                  recording='replay', source_id=metadata['source_id'], model_id=metadata['model_id'],
                  checkpoint=entry, original_case=str(case.resolve()),
                  requested_start_hour=start_hour, requested_stop_hour=requested_stop/3600,
                  requested_duration_s=duration_s, window_semantics="sample indices [floor(start*3600*Fs), floor(stop*3600*Fs)); stop clipped to campaign duration",
                  warmup_records=first-entry['sequence'], requested_solver_stop_record=stop,
                  solver_stop_record=max(a['retired_records'] for a in arms.values()),
                  failure=stream.failure,
                  semantics='Same evidence continued from full joint checkpoint; no posterior reset or replayed evidence double-counting. Sample arrays start at record_offset; read only records valid rows. Trace/chart arrays use arm outputs. Final messages may extend to next original block boundary.')
    atomic_json(destination/'scenario.json', scenario_file)
    atomic_json(destination/'calibration.json', config)
    atomic_json(destination/'result.json', result)
    if plots and valid:
        from .plot import render
        render(destination, result, config, cell)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case',type=Path)
    parser.add_argument('--debug-start-hour','--start-hour',dest='start_hour',type=float,required=True,
                        help='absolute simulated start hour (inclusive sample index)')
    window = parser.add_mutually_exclusive_group()
    window.add_argument('--debug-stop-hour','--end-hour',dest='stop_hour',type=float,
                        help='absolute simulated stop hour (exclusive sample index)')
    window.add_argument('--duration-s',type=float,
                        help='duration instead of an absolute stop hour (default:10 seconds)')
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--no-plots',action='store_true')
    args = parser.parse_args()
    if not math.isfinite(args.start_hour) or args.start_hour < 0:
        parser.error('finite nonnegative debug start hour required')
    if args.stop_hour is not None and (not math.isfinite(args.stop_hour) or args.stop_hour <= args.start_hour):
        parser.error('finite debug stop hour greater than start hour required')
    if args.duration_s is not None and (not math.isfinite(args.duration_s) or args.duration_s <= 0):
        parser.error('finite positive duration required')
    result = replay(args.case,args.out,args.start_hour,args.duration_s if args.duration_s is not None else 10.,
                    not args.no_plots,stop_hour=args.stop_hour)
    print('Replay: '+str(args.out/'result.json'),flush=True)
    return 0 if result['status']=='completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
