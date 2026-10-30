"""Independent case processes; only the parent writes campaign summaries."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

THREAD_ENV = {name: '1' for name in ['OPENBLAS_NUM_THREADS', 'OPENBLAS_DEFAULT_NUM_THREADS',
    'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'BLIS_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS']}


def execute_case(out, config, model_id, index, scenario, cell, args):
    from .run import run_case, write
    case = out / ('case_%04d' % index)
    started = time.time_ns()
    print(json.dumps(dict(starting=case.name, pid=os.getpid(), **scenario)), flush=True)
    try:
        result = run_case(case, out, config, model_id, scenario, cell, args)
    except Exception as e:
        case.mkdir(exist_ok=True)
        result = dict(status='execution_failed', reason=str(e), scenario=scenario)
        (case / 'execution_error.txt').write_text(traceback.format_exc())
        if not (case / 'result.json').exists():
            write(case / 'result.json', result)
    write(case / 'worker.json', dict(pid=os.getpid(), started_ns=started, finished_ns=time.time_ns(),
          native_thread_environment={name:os.environ.get(name) for name in THREAD_ENV}))
    return result


def process_case(out, index, scenario):
    """A supervising thread waits on a fresh Python worker, never running the solver."""
    command = [sys.executable, '-B', '-m', 'experiments.foster_campaign_001.worker', str(out), str(index)]
    case = out / ('case_%04d' % index)
    try:
        proc = subprocess.run(command, env={**os.environ, **THREAD_ENV})
        path = case / 'result.json'
        if path.exists() and proc.returncode in (0, 1):
            result = json.loads(path.read_text())
            if (proc.returncode == 0) == (result['status'] == 'completed'):
                return result
        reason = 'worker exited with code '+str(proc.returncode)+' without a consistent result'
    except Exception as e:
        reason = str(e)
    # Keep any partial result intact; the failure receipt identifies the crash.
    from .run import write
    case.mkdir(exist_ok=True)
    result = dict(status='execution_failed', reason=reason, scenario=scenario)
    write(case / 'worker_failure.json', result)
    if not (case / 'result.json').exists():
        write(case / 'result.json', result)
    return result


def completed_cases(out, config, model_id, scenarios, definitions, args):
    if args.jobs == 1:
        for index, scenario in enumerate(scenarios):
            yield index, execute_case(out, config, model_id, index, scenario, definitions[scenario['cell']], args)
    else:
        # Threads supervise subprocesses, avoiding forked BLAS state and shared
        # solver memory. At most jobs worker processes are alive concurrently.
        with ThreadPoolExecutor(max_workers=min(args.jobs, len(scenarios))) as executor:
            futures = {executor.submit(process_case, out, index, scenario): index
                       for index, scenario in enumerate(scenarios)}
            for future in as_completed(futures):
                yield futures[future], future.result()


def worker_main():
    from argparse import Namespace
    from .run import read_config_for_worker
    out = Path(sys.argv[1]); index = int(sys.argv[2])
    plan, config = read_config_for_worker(out)
    scenario = plan['scenarios'][index]
    result = execute_case(out, config, plan['model_id'], index, scenario,
                          plan['cells'][scenario['cell']], Namespace(**plan['configuration']))
    return 0 if result['status'] == 'completed' else 1
