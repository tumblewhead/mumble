"""Local continuous Foster campaigns; cells, loads and telemetry stay in the harness."""
import argparse
import csv
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import itertools
import json
import os
from pathlib import Path
import shutil
import sys
import time
import traceback
from .execution import THREAD_ENV, completed_cases

# CLI qualification and jobs=1 use the same native thread budget as workers.
# Imported library users retain control of their already-loaded NumPy runtime.
if __name__ == '__main__':
    os.environ.update(THREAD_ENV)
import numpy as np
from experiments.foster_feedback_001.estimator import Rolling
from experiments.foster_feedback_001.run import prepare
from experiments.foster_feedback_001.history import numeric_storage
from experiments.structured_joint_001.qualify import write
from specifications.evidence_feedback_001.protocol import digest
from .stimulus import cells, LOADS, generate
from .telemetry import OBS_COLUMNS, TRUTH_COLUMNS, TRACE_COLUMNS, trace_row
from .charger import DEFAULTS as CHARGER_DEFAULTS, validate as validate_charger

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = ROOT / 'experiments/foster_feedback_001'


def ident(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return dict(bytes=path.stat().st_size, sha256=h.hexdigest())


def metrics():
    return dict(outputs=0, Q_squared=0., SOC_squared=0., max_Q_percent=0., max_SOC_pp=0.,
                joint_within_target=0, Q_3sd_misses=0, SOC_3sd_misses=0)


def score(m, r, truth):
    q = 100 * (r['Q'] / truth[5] - 1)
    z = 100 * (r['SOC'] - truth[0])
    m['outputs'] += 1
    m['Q_squared'] += q*q; m['SOC_squared'] += z*z
    m['max_Q_percent'] = max(m['max_Q_percent'], abs(q))
    m['max_SOC_pp'] = max(m['max_SOC_pp'], abs(z))
    m['joint_within_target'] += int(abs(q) <= .5 and abs(z) <= .5)
    m['Q_3sd_misses'] += int(not r['Q_interval_3sd'][0] <= truth[5] <= r['Q_interval_3sd'][1])
    m['SOC_3sd_misses'] += int(abs(r['SOC'] - truth[0]) > 3*r['SOC_sd'])
    m['final_Q_percent'] = q; m['final_SOC_pp'] = z


def finish(m):
    n = m['outputs']
    m['Q_RMSE_percent'] = (m.pop('Q_squared') / n)**.5 if n else None
    m['SOC_RMSE_pp'] = (m.pop('SOC_squared') / n)**.5 if n else None
    m['joint_within_target_fraction'] = m['joint_within_target'] / n if n else None


def run_case(out, campaign, config, model_id, scenario, cell, args):
    out.mkdir()
    charger_settings={k:getattr(args,k,v) for k,v in CHARGER_DEFAULTS.items()} if scenario['load']=='charge-discharge' else None
    write(out / 'scenario.json', dict(**scenario, cell_definition=cell,
          stimulus_sign='positive discharge', reference_parameters='stationary',
          charger=charger_settings,
          temperature=dict(mode=args.temperature, mean_C=args.temperature_mean_c,
                           amplitude_C=args.temperature_amplitude_c, period_s=args.temperature_period_s)))
    n = round(args.hours * 126000)
    started = time.perf_counter()
    obs, truth, generated = generate(out, config, n, cell, scenario['load'], args.current_a,
        scenario['noise_v'], scenario['seed'], args.temperature, args.temperature_mean_c,
        args.temperature_amplitude_c, args.temperature_period_s,
        charger_settings=charger_settings,
        progress=lambda count: print(json.dumps(dict(case=out.name, generating_records=count,
                                                     simulated_hours=count/126000)), flush=True))
    write(out / 'inputs.json', dict(**generated, requested_records=n, sample_rate_Hz=35,
          observation_columns=OBS_COLUMNS, truth_columns=TRUTH_COLUMNS,
          observation_identity=ident(out / 'observations.npy'), truth_identity=ident(out / 'truth.npy'),
          incomplete_array_rule='Only rows below valid_records are valid; unused preallocated rows must not be read.'))
    if generated['status'] != 'generated':
        result = dict(**generated, wall_s=time.perf_counter()-started, scenario=scenario)
        write(out / 'result.json', result)
        return result
    source = digest(dict(observations=ident(out / 'observations.npy'), model_id=model_id))
    kinds = ['float64', 'float32'] if args.encoding == 'both' else [args.encoding]
    banks = {k: Rolling((campaign / 'model.so').resolve(), config, source, model_id, k) for k in kinds}
    max_outputs = (n + config['numerical']['block_records'] - 1) // config['numerical']['block_records']
    stats = {k: dict(status='running', all=metrics(), current_nonzero=metrics(), current_zero=metrics(),
                    stops={}, outputs=0, storage=numeric_storage(k)) for k in kinds}
    arrays = {k: np.lib.format.open_memmap(out / (k+'_trace.npy'), mode='w+', dtype='float64',
                                         shape=(max_outputs, len(TRACE_COLUMNS))) for k in kinds}
    charts = {k: np.lib.format.open_memmap(out / (k+'_chart.npy'), mode='w+', dtype='float64',
                                         shape=(max_outputs, 32)) for k in kinds}
    encoding_difference = dict(Q_percent=0., SOC_pp=0., paired_outputs=0) if len(kinds) == 2 else None
    last_print = time.perf_counter()
    with ExitStack() as stack:
        writers = {}
        for k in kinds:
            f = stack.enter_context((out / (k+'_trace.csv')).open('x', newline=''))
            writers[k] = csv.writer(f)
            writers[k].writerow(TRACE_COLUMNS + ['truth_'+c for c in TRUTH_COLUMNS])
        for i, row in enumerate(obs):
            reads = {}
            for k, bank in banks.items():
                stat = stats[k]
                if stat['status'] != 'running':
                    continue
                try:
                    value = bank.offer(i, *map(float, row))
                    if i == n-1 and value is None:
                        value = bank.retire()
                except (ValueError, RuntimeError, np.linalg.LinAlgError, OverflowError) as e:
                    stat.update(status='unresolved', failure=dict(index=i, reason=str(e)))
                    continue
                if value is None:
                    continue
                r, d = value
                output = trace_row(r, row, config)
                arrays[k][stat['outputs']] = output
                charts[k][stat['outputs']] = r['chart_mean'] + r['chart_sd']
                writers[k].writerow([*output, *truth[i]])
                stat['outputs'] += 1
                score(stat['all'], r, truth[i])
                score(stat['current_nonzero' if row[1] != 0 else 'current_zero'], r, truth[i])
                stat['stops'][d['stop']] = stat['stops'].get(d['stop'], 0)+1
                reads[k] = r
            if len(reads) == 2:
                a, b = reads['float64'], reads['float32']
                encoding_difference['paired_outputs'] += 1
                encoding_difference['Q_percent'] = max(encoding_difference['Q_percent'], abs(100*(b['Q']/a['Q']-1)))
                encoding_difference['SOC_pp'] = max(encoding_difference['SOC_pp'], abs(100*(b['SOC']-a['SOC'])))
            if time.perf_counter()-last_print >= 25:
                print(json.dumps(dict(case=out.name, simulated_hours=(i+1)/126000,
                                      wall_s=time.perf_counter()-started)), flush=True)
                last_print = time.perf_counter()
            if all(s['status'] != 'running' for s in stats.values()):
                break
    for k, bank in banks.items():
        stat = stats[k]
        if stat['status'] == 'running':
            stat['status'] = 'completed'
        stat.update(received_records=bank.next_index, retired_records=bank.history.read().boundary.sequence,
                    pending_records=len(bank.rows), tokens=bank.history.read().generation)
        for key in ['all', 'current_nonzero', 'current_zero']:
            finish(stat[key])
        arrays[k].flush(); charts[k].flush()
    write(out / 'telemetry.json', dict(trace_columns=TRACE_COLUMNS, truth_columns=TRUTH_COLUMNS,
          observation_columns=OBS_COLUMNS, valid_trace_rows={k: s['outputs'] for k, s in stats.items()},
          chart_columns='first16: chart mean; last16: marginal chart SD; chart defined in parent plan.json',
          voltage_semantics='Endpoint voltage reconstructed from assimilated boundary mean, not an out-of-sample forecast',
          uncertainty='Local Gaussian chart marginals only; coverage unvalidated. Full covariance remains in live history.',
          cadence='Observations/truth35Hz; estimated states and parameters every16records, including final partial block',
          fitted_quantity='Transformed chart mean, not posterior physical mean; positive log quantities use median',
          current_buckets='Classified by current at each block endpoint, not whole-window excitation'))
    result = dict(status='completed' if all(s['status']=='completed' for s in stats.values()) else 'unresolved',
                  scenario=scenario, arms=stats, records=n, source_id=source, model_id=model_id,
                  encoding_difference=encoding_difference, simulation_hours=n/126000,
                  charger=generated.get('charger'),
                  wall_s_before_plots=time.perf_counter()-started, coverage_validated=False, aging_implemented=False)
    if args.sample_csv:
        with (out / 'samples.csv').open('x', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['record_count', 'time_s'] + OBS_COLUMNS + ['truth_'+c for c in TRUTH_COLUMNS])
            for i in range(n):
                writer.writerow([i+1, (i+1)/35, *obs[i], *truth[i]])
    if not args.no_plots:
        from .plot import render
        try:
            render(out, result, config, cell)
            result['plots'] = 'completed'
        except Exception as e:
            result['plots'] = dict(status='failed', reason=str(e))
            (out / 'plot_error.txt').write_text(traceback.format_exc())
    write(out / 'result.json', result)
    return result


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--jobs', type=int, default=1, help='maximum independent case workers (default:1; native math threads:1 each)')
    p.add_argument('--hours', type=float, default=4.)
    p.add_argument('--cells', nargs='+', default=['B'])
    p.add_argument('--cell-file', help='JSON mapping custom names to named parameters and initial_state')
    p.add_argument('--loads', choices=LOADS, nargs='+', default=['cycle'])
    p.add_argument('--current-a', type=float, default=.03, help='peak commanded amplitude in A')
    p.add_argument('--nominal-capacity-ah', type=float, default=.06, help='nameplate Ah for C-rate conversion; harness only')
    p.add_argument('--charge-c', type=float, nargs='+', default=[2.,1.,1.5], help='CC/CV charger current-capability schedule in C')
    p.add_argument('--discharge-c', type=float, nargs='+', default=[.2,.45,.7], help='discharge load schedule in C')
    p.add_argument('--charge-step-s', type=float, default=900., help='global-time dwell for each charger capability')
    p.add_argument('--discharge-step-s', type=float, default=600., help='global-time dwell for each discharge rate')
    p.add_argument('--cv-voltage', type=float, default=4.06, help='synthetic CC-to-CV voltage setpoint')
    p.add_argument('--discharge-cutoff-v', type=float, default=3.18)
    p.add_argument('--cycle-rest-s', type=float, default=300.)
    p.add_argument('--taper-end-c', type=float, default=.05, help='CC/CV taper termination current in C')
    p.add_argument('--taper-hold-s', type=float, default=30., help='continuous low-current dwell before charge ends')
    p.add_argument('--cv-gain', type=float, default=.5, help='voltage-loop integral gain in A/(V s); harness only')
    p.add_argument('--noise-v', type=float, nargs='+', default=[.004], help='Gaussian voltage noise SD in V; ADC remains')
    p.add_argument('--seeds', type=int, nargs='+', default=[314159])
    p.add_argument('--temperature', choices=['cycle', 'constant'], default='cycle')
    p.add_argument('--temperature-mean-c', type=float, default=25.)
    p.add_argument('--temperature-amplitude-c', type=float, default=8.)
    p.add_argument('--temperature-period-s', type=float, default=3600.)
    p.add_argument('--encoding', choices=['both', 'float32', 'float64'], default='both')
    p.add_argument('--sample-csv', action='store_true', help='also export all35Hz samples and truth to large CSV')
    p.add_argument('--no-plots', action='store_true')
    p.add_argument('--out')
    return p


def read_config_for_worker(out):
    return (json.loads((out/'campaign_plan.json').read_text()),
            json.loads((out/'calibration.json').read_text()))


def main():
    p = parser(); args = p.parse_args()
    if args.jobs < 1:
        p.error('--jobs must be a positive integer')
    if 'charge-discharge' in args.loads:
        try:validate_charger({k:getattr(args,k) for k in CHARGER_DEFAULTS})
        except ValueError as e:p.error(str(e))
    numbers = [args.hours, args.current_a, *args.noise_v, args.temperature_mean_c,
               args.temperature_amplitude_c, args.temperature_period_s]
    if not np.isfinite(numbers).all() or args.hours <= 0 or round(args.hours*126000) < 16:
        p.error('finite values and at least16samples required')
    if not 0 <= args.current_a <= .25 or min(args.noise_v) < 0 or min(args.seeds) < 0:
        p.error('current amplitude must be0..0.25A; noise and seeds nonnegative')
    amp = args.temperature_amplitude_c if args.temperature == 'cycle' else 0.
    if args.temperature_amplitude_c < 0 or args.temperature_period_s <= 0 or not (15 <= args.temperature_mean_c-amp <= args.temperature_mean_c+amp <= 35):
        p.error('temperature must remain15..35C; nonnegative amplitude and positive period required')
    try:
        definitions = cells(args.cell_file)
        if any(c not in definitions for c in args.cells):
            raise ValueError('unknown cell; use A/B or supply --cell-file')
    except (ValueError, TypeError, KeyError, OSError) as e:
        p.error(str(e))
    scenarios = [dict(cell=c, load=l, noise_v=v, seed=s) for c, l, v, s in
                 itertools.product(dict.fromkeys(args.cells), dict.fromkeys(args.loads),
                                   dict.fromkeys(args.noise_v), dict.fromkeys(args.seeds))]
    out = Path(args.out).resolve() if args.out else HERE / ('run_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f'))
    preserved = json.loads((BASE / 'verification.json').read_text())['artifacts']
    for name, expected in preserved.items():
        if ident(ROOT / name) != expected:
            raise ValueError('preserved parent evidence changed: '+name)
    config, model_id = prepare(out, args)
    sources = list(HERE.glob('*.py')) + list(HERE.glob('*.json')) + list(HERE.glob('*.md'))
    for path in sources:
        target = out / 'source_snapshot' / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    write(out / 'campaign_plan.json', dict(configuration=vars(args), scenarios=scenarios, model_id=model_id,
          execution=dict(requested_jobs=args.jobs, effective_jobs=min(args.jobs,len(scenarios)),
                         native_thread_environment=THREAD_ENV, case_order='stable scenario order, independent of completion order'),
          cells={k: definitions[k] for k in args.cells}, preserved_parent_artifacts=preserved,
          campaign_sources={str(f.relative_to(ROOT)):ident(f) for f in sources},
          assumptions='Stationary synthetic reference parameters, known linearOCV/Arrhenius; unchanged parent solver/prior',
          scope='Independent case workers; chronological samples within each case; no retries or truth-based tuning; point errors are not coverage'))
    print(json.dumps(dict(output=str(out), cases=len(scenarios), hours_per_case=args.hours,
                          jobs=min(args.jobs,len(scenarios)),
                          numeric_disk_MB_per_case=round(args.hours*126000*(176+35.5*(2 if args.encoding=='both' else 1))/1e6, 1),
                          disk_note='Plus block CSV, plots, snapshots; --sample-csv substantially increases disk use')), flush=True)
    completed = {}
    for index, result in completed_cases(out, config, model_id, scenarios, definitions, args):
        case = out / ('case_%04d' % index)
        completed[index] = dict(directory=case.name, **result)
        reports = [completed[i] for i in sorted(completed)]
        summary = dict(status='running' if len(reports) < len(scenarios) else
                       ('completed' if all(r['status']=='completed' for r in reports) else 'completed_with_failures'),
                       requested_cases=len(scenarios), completed_cases=len(reports), cases=reports,
                       requested_jobs=args.jobs, effective_jobs=min(args.jobs,len(scenarios)))
        temp = out / 'summary.tmp'
        temp.write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')
        temp.replace(out / 'summary.json')
        with (out / 'summary.csv').open('w', newline='') as f:
            writer=csv.writer(f)
            writer.writerow(['case','cell','load','noise_v','seed','encoding','status','retired_records',
                             'final_Q_percent','final_SOC_pp','max_Q_percent','max_SOC_pp',
                             'joint_within_target_fraction','Q_3sd_misses','SOC_3sd_misses'])
            for r in reports:
                for kind,arm in r.get('arms',{'none':dict(status=r['status'])}).items():
                    m=arm.get('all',{})
                    writer.writerow([r['directory'],*[r['scenario'][key] for key in ['cell','load','noise_v','seed']],
                                     kind,arm['status'],arm.get('retired_records'),
                                     *[m.get(key) for key in ['final_Q_percent','final_SOC_pp','max_Q_percent',
                                       'max_SOC_pp','joint_within_target_fraction','Q_3sd_misses','SOC_3sd_misses']]])
        print(json.dumps(dict(case=case.name, status=result['status'], result=str(case/'result.json'))), flush=True)
    write(out / 'manifest.json', dict(artifacts={str(f.relative_to(out)):ident(f)
          for f in sorted(out.rglob('*')) if f.is_file() and '__pycache__' not in f.parts}))
    print('Summary: '+str(out / 'summary.json'), flush=True)
    return 0 if all(r['status']=='completed' for r in reports) else 1


if __name__ == '__main__':
    sys.exit(main())
