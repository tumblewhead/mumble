"""Run the registered checkpoint resource/forecast study without a long warmup."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def identity(path):
    return dict(bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def write(path, obj):
    path.write_text(json.dumps(obj, indent=2, allow_nan=False)+'\n')


def execute(jobfile, worker, replay_root):
    destination = jobfile.parent
    with (destination/'worker.log').open('x') as log:
        completed = subprocess.run([sys.executable, '-B', str(worker), str(jobfile)], cwd=replay_root,
                                   stdout=log, stderr=subprocess.STDOUT)
    result = json.loads((destination/'result.json').read_text()) if (destination/'result.json').exists() else dict(status='worker_failed_without_result')
    return dict(directory=destination.name, exit_code=completed.returncode, result=result)


def summarize(out, results, concurrent, expected_prefixes):
    arms = {}
    for item in results:
        file = out/item['directory']/'forecasts.json'
        if not file.exists():
            continue
        for r in json.loads(file.read_text()):
            a = arms.setdefault(r['arm'], dict(tasks=0, scored=0, unresolved=0, unsupported_probe_count=0,
                worst_abs_minimum_error_mV=0., worst_abs_recovery_error_mV=0.,
                max_closed_form_C_difference_V=0., max_truth_scalar_closed_form_difference_V=0.))
            a['tasks'] += 1
            if 'prediction' in r:
                a['unsupported_probe_count'] += r['prediction']['unsupported_probes']
                a['max_closed_form_C_difference_V'] = max(a['max_closed_form_C_difference_V'], r['prediction']['closed_form_C_max_difference_V'])
            if 'scoring' not in r:
                a['unresolved'] += 1
                continue
            a['scored'] += 1
            a['worst_abs_minimum_error_mV'] = max(a['worst_abs_minimum_error_mV'], 1000*abs(r['scoring']['minimum_error_V']))
            a['worst_abs_recovery_error_mV'] = max(a['worst_abs_recovery_error_mV'], 1000*abs(r['scoring']['recovery_error_V']))
            a['max_truth_scalar_closed_form_difference_V'] = max(a['max_truth_scalar_closed_form_difference_V'], r['scoring']['truth_scalar_closed_form_difference_V'])
    status = ('running' if len(results) < expected_prefixes else
              'completed_diagnostic' if all(r['exit_code'] == 0 for r in results) else 'partial_or_failed')
    return dict(status=status, expected_prefixes=expected_prefixes, finished_prefixes=len(results),
        prefixes=results, forecast_scorecard=arms, concurrent_workers=concurrent,
        timing_scope='Host measurements; concurrent workers contend for CPU/memory. Use --jobs 1 for resource comparisons.' if concurrent > 1 else 'Isolated prefix workers, paired alternating arm order, one BLAS thread; host only, not M23 cycles.',
        limits=['Selected development witnesses, not independent coverage validation',
                'Native transient/stack allocation and exact scalar operation counts remain unmeasured',
                'Current-task forks only; no low-SOC continuation, regulated power path, calibrated admission risk or aging qualification'])


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path)
    p.add_argument('--inputs', type=Path, default=ROOT/'specifications/tangent_development_001/inputs.json')
    p.add_argument('--plan', type=Path, default=ROOT/'specifications/tangent_development_001/plan.json')
    p.add_argument('--replay-root', type=Path, help='Frozen original replay worktree; checks are never bypassed')
    p.add_argument('--campaign', type=Path)
    p.add_argument('--cases', nargs='+', help='e.g. case_0006 case_0011')
    p.add_argument('--prefix-hours', nargs='+', type=int, choices=(3, 24, 69))
    p.add_argument('--records', type=int, default=16384)
    p.add_argument('--repetitions', type=int, default=5)
    p.add_argument('--jobs', type=int, default=1, help='Default 1 for uncontended profiling; >1 labels timings as contended')
    p.add_argument('--workloads', nargs='+', help='Subset of registered workload IDs; default all 20')
    p.add_argument('--no-plots', action='store_true')
    args = p.parse_args(argv)
    if args.records < 4096 or args.records % 16 or args.repetitions < 1 or args.jobs < 1:
        p.error('records must be a multiple of 16 and >=4096; repetitions/jobs positive')
    inputs, plan = json.loads(args.inputs.read_text()), json.loads(args.plan.read_text())
    prefixes = inputs['selected_prefixes']
    known_cases = {x['case'] for x in prefixes}
    if args.cases and set(args.cases)-known_cases:
        p.error('unknown case selection')
    prefixes = [x for x in prefixes if (not args.cases or x['case'] in args.cases) and
                (not args.prefix_hours or x['requested_min_hour'] in args.prefix_hours)]
    tasks = plan['first_study']['workload_bank']
    if args.workloads and set(args.workloads)-{x['id'] for x in tasks}:
        p.error('unknown registered workload')
    tasks = [x for x in tasks if not args.workloads or x['id'] in args.workloads]
    campaign = (args.campaign or Path(inputs['campaign'])).resolve()
    replay_root = (args.replay_root or Path(inputs['preserved_replay_worktree'])).resolve()
    for path in (campaign, replay_root):
        if not path.is_dir():
            p.error('required local evidence directory missing: '+str(path))
    out = (args.out or HERE/('run_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))).resolve()
    out.mkdir(parents=True, exist_ok=False)
    snapshot = out/'source_snapshot'
    snapshot.mkdir()
    for name in ('run.py', 'worker.py', 'forecast.py', 'scoring.py', 'support.py', 'plot.py'):
        shutil.copy2(HERE/name, snapshot/name)
    shutil.copy2(args.inputs, snapshot/'inputs.json')
    shutil.copy2(args.plan, snapshot/'plan.json')
    def git(*cmd):
        return subprocess.check_output(['git', *cmd], cwd=ROOT, text=True).strip()
    manifest = dict(schema='tangent_development_execution_v1', source_revision=git('rev-parse', 'HEAD'),
        source_status=git('status', '--short'), sources={x.name: identity(x) for x in snapshot.iterdir()},
        campaign=str(campaign), replay_root=str(replay_root), jobs=args.jobs,
        records_per_prefix=args.records, repetitions=args.repetitions, selected_prefixes=prefixes,
        selected_workloads=[t['id'] for t in tasks],
        adaptation='Subset/rerun controls recorded explicitly; no estimator changes or source-check bypass.',
        original_plan_complete_selection=len(prefixes)==12 and len(tasks)==20 and args.records==16384 and args.repetitions==5)
    write(out/'manifest.json', manifest)
    # One thread before NumPy is imported in the child. Parallel prefix workers
    # are optional but then resource timings explicitly carry a contention label.
    for var in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'BLIS_NUM_THREADS'):
        os.environ[var] = '1'
    jobs = []
    for prefix in prefixes:
        dest = out/(prefix['case']+'_h'+str(prefix['requested_min_hour']))
        dest.mkdir()
        job = dict(out=str(dest), inputs=inputs, prefix=prefix, campaign=str(campaign),
            replay_root=str(replay_root), records=args.records, repetitions=args.repetitions, tasks=tasks)
        write(dest/'job.json', job)
        jobs.append(dest/'job.json')
    results = []
    write(out/'summary.json', summarize(out, results, args.jobs, len(jobs)))
    print('Study: '+str(out), flush=True)
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        pending = {pool.submit(execute, j, snapshot/'worker.py', replay_root): j for j in jobs}
        for future in as_completed(pending):
            result = future.result()
            results.append(result)
            results.sort(key=lambda x: x['directory'])
            write(out/'summary.json', summarize(out, results, args.jobs, len(jobs)))
            print(result['directory']+': '+result['result']['status'], flush=True)
    print('Results: '+str(out/'summary.json'), flush=True)
    if not args.no_plots:
        plotted = subprocess.run([sys.executable, '-B', str(snapshot/'plot.py'), str(out)])
        write(out/'plot_status.json', dict(exit_code=plotted.returncode,
            note='Plotting is outside resource timings; numerical results remain available if rendering fails'))
    return 0 if all(r['exit_code'] == 0 for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
