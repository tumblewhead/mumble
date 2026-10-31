"""Regenerate a full-resolution interval from a compact campaign checkpoint."""
import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np

from .compact import CHUNK, atomic_json, restore_checkpoint
from .charger import EVENT_COLUMNS
from .telemetry import TRACE_COLUMNS, trace_row


def replay(case, destination, start_hour, duration_s, plots=True):
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
    end = min(n, math.floor((start_hour*3600+duration_s)*rate))
    if not 0 <= first < end <= n:
        raise ValueError('Requested interval contains no samples inside the recorded campaign duration')
    scenario_file = json.loads((case/'scenario.json').read_text())
    cell = scenario_file['cell_definition']
    scenario = {k: scenario_file[k] for k in ['cell','load','noise_v','seed']}
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
    with (destination/'stimulus_events.csv').open('x',newline='') as f:
        writer = csv.DictWriter(f, fieldnames=EVENT_COLUMNS)
        writer.writeheader()
        while stream.index < stop:
            begin = stream.index
            obs, truth, events = stream.read(min(CHUNK, stop-begin))
            writer.writerows(e for e in events if first <= e['record_count'] <= end)
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
            if stream.failure:
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
                  requested_start_hour=start_hour, requested_duration_s=duration_s,
                  warmup_records=first-entry['sequence'], solver_stop_record=stop,
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
    parser.add_argument('--start-hour',type=float,required=True)
    parser.add_argument('--duration-s',type=float,default=10.)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--no-plots',action='store_true')
    args = parser.parse_args()
    result = replay(args.case,args.out,args.start_hour,args.duration_s,not args.no_plots)
    print('Replay: '+str(args.out/'result.json'),flush=True)
    return 0 if result['status']=='completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
