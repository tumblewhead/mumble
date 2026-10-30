"""Prepare/run the user-requested 128/256-record, 192-move desktop comparison."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from common import HERE, ROOT, save
from generate import generate


def identity(path):
    data=path.read_bytes()
    return dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())


def prepare(run):
    run.mkdir(parents=True,exist_ok=False)
    original=HERE/'attempt001/inputs'
    plan=json.loads((HERE/'plan.json').read_text())
    plan.update(prefixes=[128,256],
        adaptation='User-requested duration doubling and 192 moves; separate from original closed study',
        progression='Run both prefixes once, including256 if128 is numerically unresolved. '
                    'Execution failure stops dispatch. No automatic retries or threshold changes. '
                    'A256 result after failed128 is exploratory, not gated promotion.')
    plan['input_fixture']['generation']='Same seeded scalar generator, extended chronologically to256; verify frozen128 prefix before inference'
    plan['inference'].update(mutations=192,max_paths_per_population=80_000_000)
    plan['caps'].update(CPU_s=None,wall_s=None,
        prefix_conservative_steps={'128':64_000_000_000,'256':128_000_000_000})
    plan['resource_accounting']='Direct workers enforce shared prospective model-step and per-population path/stage caps. '
    plan['resource_accounting']+='CPU, wall, RSS and output caps are not enforced by this local runner.'
    # Avoid suggesting that inherited supervisor-only settings are enforced.
    plan['caps'].update(RSS_bytes=None,output_bytes=None)
    save(run/'plan.json',plan)
    generated=run/'generation'
    generate(generated,run/'plan.json')
    old=json.loads((original/'observations_128.json').read_text())
    extended=json.loads((generated/'observations_256.json').read_text())
    old_truth=json.loads((original/'plant_truth_not_inference.json').read_text())
    new_truth=json.loads((generated/'plant_truth_not_inference.json').read_text())
    checks={
        'frozen128_observation_bytes':(generated/'observations_128.json').read_bytes()==(original/'observations_128.json').read_bytes(),
        'nested_observations':extended['records'][:128]==old['records'],
        'source_identity':extended['source_id']==old['source_id'],
        'frozen128_physical_states':new_truth['states'][:128]==old_truth['states'],
        'initial_state':new_truth['initial_x']==old_truth['initial_x'],
        'ordered256':len(extended['records'])==256 and [r['index'] for r in extended['records']]==list(range(256)),
        'duration_doubled':abs(sum(r['dt'] for r in extended['records'])-2*sum(r['dt'] for r in old['records']))<1e-12,
    }
    save(run/'input_checks.json',dict(status='passed' if all(checks.values()) else 'failed',checks=checks))
    if not all(checks.values()):
        raise RuntimeError('Frozen-prefix verification failed; no inference launched')
    inputs=run/'inputs'
    inputs.mkdir()
    for name in ('observations_128.json','observations_256.json','inference.json'):
        shutil.copy2(generated/name,inputs/name)
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    sources=[p for directory in (HERE,HERE.parent/'joint_health_posterior_001',
             HERE.parent/'minimal_health_kernels_001') for p in directory.glob('*.py')]
    sources += [HERE.parent/'fixed_prefix_shape_001/runner.py',HERE/'plan.json']
    save(run/'provenance.json',dict(revision=revision,
        git_status=subprocess.check_output(['git','status','--short'],cwd=ROOT,text=True),
        sources={str(p.relative_to(ROOT)):identity(p) for p in sources},
        inputs={p.name:identity(p) for p in inputs.iterdir()},
        truth_boundary='Generator verifies physical continuity; separate worker processes receive only observations and inference configuration.',
        numpy_version=__import__('numpy').__version__,python=sys.version))
    print(f'Prepared: {run}',flush=True)
    return run


def worker(run,n):
    command=[sys.executable,'-B',str(HERE/'worker.py'),'posterior',str(n),
             str(run/'inputs'),str(run/f'prefix_{n}')]
    save(run/f'command_{n}.json',command)
    with (run/f'prefix_{n}.log').open('x') as log:
        process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        for line in process.stdout:
            log.write(line);log.flush();print(line,end='',flush=True)
        code=process.wait()
    result_path=run/f'prefix_{n}/result.json'
    result=json.loads(result_path.read_text()) if result_path.exists() else {}
    save(run/f'process_{n}.json',dict(returncode=code,status=result.get('status','missing_result')))
    if code or not result or result['status'] in ('failed','execution_failed'):
        raise RuntimeError(f'Prefix{n} execution failed; inspect {run}/prefix_{n}.log')
    return result['status']


def execute(run,run_worker=worker):
    provenance=json.loads((run/'provenance.json').read_text())
    for name,expected in provenance['sources'].items():
        if identity(ROOT/name)!=expected:raise RuntimeError(f'Source changed since preparation: {name}')
    for name,expected in provenance['inputs'].items():
        if identity(run/'inputs'/name)!=expected:raise RuntimeError(f'Input changed since preparation: {name}')
    if json.loads((run/'input_checks.json').read_text())['status']!='passed':
        raise RuntimeError('Input qualification failed')
    # Exclusive claim prevents concurrent execution or accidental reruns.
    save(run/'started.json',dict(time=datetime.now().isoformat(),prefixes=[128,256]))
    statuses={}
    for n in (128,256):
        statuses[str(n)]=run_worker(run,n)
    save(run/'summary.json',dict(statuses=statuses,
        prefix256_exploratory=statuses['128']!='finite_moment_checks_passed',
        coverage_validated=False,density_gate_qualified=False))
    print(f'Results: {run}/summary.json',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--run',type=Path,help='Run a previously prepared directory once')
    args=parser.parse_args()
    if args.run and args.prepare_only:parser.error('Choose --run or --prepare-only')
    run=args.run.resolve() if args.run else prepare(HERE/('local_overnight192_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')))
    if not args.prepare_only:execute(run)
