#!/usr/bin/env python3
"""Bounded, once-only supervisor for the registered fixed-prefix diagnostic."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import resource
import shutil
import signal
import struct
import subprocess
import sys
import time

# Establish these before importing NumPy through shape.
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
import shape

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCES = [
    'experiments/fixed_prefix_shape_001/backend.c',
    'experiments/live_anchor_integration_001/rolling_engine.c',
    'experiments/live_anchor_integration_001/rolling_model.c',
    'experiments/live_anchor_integration_001/public_contract.c',
    'experiments/live_anchor_integration_001/host_input.c',
    'experiments/live_anchor_bootstrap_001/adc12.c',
    'experiments/live_anchor_bootstrap_001/history_translation.c',
    'experiments/live_anchor_bootstrap_001/support_step.c', 'src/scm_model.c']
FLAGS = ['-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-pedantic',
         '-fno-fast-math', '-ffp-contract=off', '-ffunction-sections', '-fdata-sections',
         '-Wl,--gc-sections', '-Iinclude']


def identity(path):
    return {'bytes': path.stat().st_size, 'sha256': shape.file_sha(path)}


def save(path, value):
    with path.open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True, allow_nan=False)
        f.write('\n'); f.flush(); os.fsync(f.fileno())
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def build_command(destination, qualification=False):
    sources = SOURCES.copy()
    if qualification:
        sources[0] = 'experiments/fixed_prefix_shape_001/qualify_backend.c'
    return ['cc', *FLAGS, *sources, '-lm', '-o', str(destination)]


class Budget:
    def __init__(self, directory, cpu=600, wall=900, output=67108864, rss=268435456):
        self.directory = directory
        self.cpu_limit, self.wall_limit, self.output_limit, self.rss_limit = cpu, wall, output, rss
        self.started = time.monotonic()
        u = resource.getrusage(resource.RUSAGE_SELF)
        self.cpu_start = u.ru_utime + u.ru_stime
        self.children_cpu = 0.
        self.children = []

    def used_cpu(self):
        u = resource.getrusage(resource.RUSAGE_SELF)
        return u.ru_utime + u.ru_stime - self.cpu_start + self.children_cpu

    def output_bytes(self):
        return sum(p.stat().st_size for p in self.directory.rglob('*') if p.is_file())

    def check(self):
        shape.require(time.monotonic()-self.started <= self.wall_limit, 'wall budget exceeded')
        shape.require(self.used_cpu() <= self.cpu_limit, 'CPU budget exceeded')
        shape.require(self.output_bytes() <= self.output_limit, 'output budget exceeded')
        parent = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        child = max((r['peak_RSS_bytes'] for r in self.children), default=0)
        shape.require(parent + child <= self.rss_limit, 'conservative combined RSS budget exceeded')

    def run(self, command, name):
        self.check()
        remaining = max(1, math.ceil(self.cpu_limit-self.used_cpu()))
        log = self.directory / (name+'.stdout')
        err = self.directory / (name+'.stderr')
        def limits():
            resource.setrlimit(resource.RLIMIT_CPU, (remaining, remaining))
            resource.setrlimit(resource.RLIMIT_AS, (1073741824, 1073741824))
            resource.setrlimit(resource.RLIMIT_FSIZE, (self.output_limit, self.output_limit))
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        started = time.monotonic()
        failure = None
        with log.open('xb') as stdout, err.open('xb') as stderr:
            p = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr,
                                 start_new_session=True, preexec_fn=limits)
            usage = None
            try:
                while True:
                    pid, status, usage_result = os.wait4(p.pid, os.WNOHANG)
                    if pid:
                        usage = usage_result
                        p.returncode = os.waitstatus_to_exitcode(status)
                        break
                    self.check()
                    # Bound live RSS as well as recording terminal peak RSS.
                    status_path = Path(f'/proc/{p.pid}/status')
                    try:
                        fields = dict(line.split(':', 1) for line in status_path.read_text().splitlines() if ':' in line)
                        rss = int(fields.get('VmRSS', '0 kB').split()[0])*1024
                        parent = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
                        shape.require(parent+rss <= self.rss_limit, 'live combined RSS budget exceeded')
                    except FileNotFoundError:
                        pass
                    time.sleep(.025)
            except BaseException as exc:
                failure = exc
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                _, status, usage = os.wait4(p.pid, 0)
                p.returncode = os.waitstatus_to_exitcode(status)
            finally:
                stdout.flush(); stderr.flush(); os.fsync(stdout.fileno()); os.fsync(stderr.fileno())
                if usage is not None:
                    cpu = usage.ru_utime+usage.ru_stime
                    self.children_cpu += cpu
                    row = {'command': command, 'returncode': p.returncode, 'CPU_s': cpu,
                           'wall_s': time.monotonic()-started, 'peak_RSS_bytes': usage.ru_maxrss*1024,
                           'stdout': identity(log), 'stderr': identity(err)}
                    self.children.append(row)
                    save(self.directory/(name+'.process.json'), row)
        # Preserve a distinct-inode, read-back-verified copy of original stdout.
        copy = self.directory/(name+'.stdout.copy')
        with log.open('rb') as src, copy.open('xb') as dst:
            shutil.copyfileobj(src, dst); dst.flush(); os.fsync(dst.fileno())
        shape.require(identity(log) == identity(copy) and log.stat().st_ino != copy.stat().st_ino,
                      'independent capture preservation failed')
        if failure is not None:
            raise failure
        self.check()
        shape.require(p.returncode == 0, f'{name} failed; original output preserved')
        return log


def prepare_expected(trace, output):
    count = 0
    source = None
    with trace.open() as src, output.open('xb') as dst:
        for line in src:
            r = json.loads(line)
            if r['kind'] == 'header':
                shape.require(source is None and count == 0, 'duplicate/misplaced trace header')
                source = r['source_id']
            elif r['kind'] in ('initial', 'block'):
                if r['next_index'] > shape.PREFIX:
                    break
                shape.require(source is not None and r['next_index'] == count*16, 'trace order differs')
                ep = r['endpoint']
                v = [*r['x'], r['elapsed_s'], r['likelihood_cost'], r['prior_cost'], r['total_cost'],
                     ep['SOC'], *ep['v_V'], ep['h'], ep['min_support_slack'], ep['min_endpoint_slack']]
                shape.require(len(v) == 27 and all(math.isfinite(x) for x in v), 'invalid expected snapshot')
                dst.write(struct.pack('<Q27dIII', r['next_index'], *v, r['flags'], r['phase_and_flags'], int(r['available'])))
                count += 1
        dst.flush(); os.fsync(dst.fileno())
    shape.require(count == shape.PREFIX//16+1 and source is not None, 'incomplete saved trace prefix')
    return source


def bound_sources():
    manifest = shape.load(ROOT/'experiments/live_anchor_integration_001/attempt001/source_manifest.json')
    result = {}
    for name, expected in manifest['model_contract_sources'].items():
        actual = identity(ROOT/name)
        shape.require(actual == expected, 'inherited source changed: '+name)
        result[name] = actual
    for name in [*SOURCES, 'experiments/fixed_prefix_shape_001/runner.py',
                 'experiments/fixed_prefix_shape_001/shape.py',
                 'experiments/fixed_prefix_shape_001/plan.json',
                 'experiments/fixed_prefix_shape_001/backend_contract.json',
                 'experiments/fixed_prefix_shape_001/qualify_backend.py',
                 'experiments/fixed_prefix_shape_001/qualify_backend.c']:
        result[name] = identity(ROOT/name)
    return result


def run(qualification, publication):
    plan = shape.load(HERE/'plan.json')
    qualified = shape.load(qualification)
    shape.require(qualified['status'] == 'passed', 'backend qualification did not pass')
    sources = bound_sources()
    shape.require(qualified['sources'] == sources, 'sources differ from qualified source')
    published = shape.load(publication)
    shape.require(published['sources'] == sources and published['status'] == 'verified_remote', 'source publication gate')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    shape.require(revision == published['revision'], 'published revision differs from current tip')
    for key in ('observations', 'trace'):
        r = plan['input'][key]
        shape.require(identity(ROOT/r['path']) == {k:r[k] for k in ('bytes','sha256')}, key+' identity differs')
    binary = qualification.parent/'backend'
    shape.require(identity(binary) == qualified['binary'], 'qualified binary differs')
    out = HERE/'attempt001'
    # This durable reservation is never removed, including on failure.
    save(HERE/'scientific_reservation.json', {
        'schema':'mumble_fixed_prefix_reservation_v1', 'source_revision':revision,
        'capture_invocations':1, 'comparison_invocations':1, 'retries':0,
        'finite_caps':plan['finite_caps'], 'sources':sources,
        'qualification':identity(qualification), 'publication':identity(publication)})
    out.mkdir()
    budget = Budget(out)
    result = {'schema':'mumble_fixed_prefix_execution_v1', 'status':'unresolved',
              'source_revision':revision, 'sources':sources, 'capture_invocations':0,
              'comparison_invocations':0, 'optimizer_calls':0, 'truth_reads':0,
              'source_generation_calls':0, 'retries':0}
    try:
        source = prepare_expected(ROOT/plan['input']['trace']['path'], out/'expected.bin')
        obs = str(ROOT/plan['input']['observations']['path'])
        snapshot = out/'bank.bin'
        result['capture_invocations'] = 1
        log = budget.run([str(binary), 'capture', obs, str(out/'expected.bin'), str(snapshot), source, str(shape.PREFIX)], 'capture')
        rows = [json.loads(s) for s in log.read_text().splitlines()]
        c = rows[-1]
        shape.require(c['kind'] == 'capture' and c['checked_snapshots'] == 15751, 'capture incomplete')
        c.update(schema='mumble_fixed_prefix_capture_v1', base_revision=shape.BASE,
                 observations_sha256=shape.OBS_SHA, trace_sha256=shape.TRACE_SHA,
                 snapshot_scope='pointer_free_host_ABI_bank_inputs_calibration',
                 snapshot_bytes=snapshot.stat().st_size, snapshot_sha256=shape.file_sha(snapshot),
                 reconstruction={'method':'commit_only','optimizer_calls':0,'truth_reads':0,'records':shape.PREFIX,
                                 'blocks':15750,'checked_snapshots':15751,'parity':'bitwise'},
                 host_platform=platform.platform(), byteorder=sys.byteorder, source_id=source)
        save(out/'capture.json', c)
        shape.validate_capture(c, snapshot)
        design = shape.make_design(c['anchor'], shape.unpack_metric(c['metric_packed_lower']),
                                   c['public_sd'], c['lower'], c['upper'], c['charge_min_Ah'], c['charge_max_Ah'], c['charge_Ah'])
        design.update(capture_sha256=shape.file_sha(out/'capture.json'), snapshot_sha256=shape.file_sha(snapshot),
                      common_prior_source_sha256=shape.PRIOR_SHA)
        save(out/'nodes.json', design)
        with (out/'nodes.bin').open('xb') as f:
            for node in design['nodes']:
                f.write(struct.pack('<16d', *node['x']))
            f.flush(); os.fsync(f.fileno())
        freeze = {name:identity(out/name) for name in ('bank.bin','capture.json','nodes.json','nodes.bin')}
        save(out/'nodes_frozen.json', {'files':freeze, 'reference_calls':0, 'adaptive_radius_after_comparison':False})
        shape.require(bound_sources() == sources, 'sources changed after preflight')
        shape.require(identity(binary) == qualified['binary'], 'binary changed after capture')
        result['comparison_invocations'] = 1
        log = budget.run([str(binary),'evaluate',obs,str(snapshot),str(out/'nodes.bin'),'545',str(shape.PREFIX)], 'comparison')
        rows = [json.loads(s) for s in log.read_text().splitlines()]
        terminal = rows.pop()
        shape.require(terminal['kind'] == 'terminal' and terminal['nodes'] == 545 and len(rows) == 545, 'comparison incomplete')
        shape.require(terminal['model_steps'] <= 137340000 and terminal['predict_calls'] <= 137340000 and
                      terminal['represented_queries'] <= 545, 'work caps exceeded')
        for k, row in enumerate(rows):
            shape.require(row['index'] == k and row['x'] == design['nodes'][k]['x'], 'node identity mismatch')
            row['id'] = design['nodes'][k]['id']
        shape.require(all(identity(out/name) == expected for name,expected in freeze.items()), 'frozen input changed')
        for key in ('observations', 'trace'):
            r = plan['input'][key]
            shape.require(identity(ROOT/r['path']) == {k:r[k] for k in ('bytes','sha256')}, key+' changed during execution')
        ev = {'schema':'mumble_fixed_prefix_evaluations_v1', 'design_sha256':shape.file_sha(out/'nodes.json'),
              'snapshot_sha256':shape.file_sha(snapshot), 'prefix':shape.PREFIX, 'observations_sha256':shape.OBS_SHA,
              'common_prior_source_sha256':shape.PRIOR_SHA, 'closed':True, 'rows':rows, 'work':terminal}
        save(out/'evaluations.json', ev)
        analysis = shape.compare(design, rows)
        analysis.update(design_sha256=shape.file_sha(out/'nodes.json'), evaluations_sha256=shape.file_sha(out/'evaluations.json'))
        save(out/'analysis.json', analysis)
        result.update(status='completed', decision=analysis['decision'], work=terminal,
                      capture_work={k:c[k] for k in ('model_steps','qr_rows','query_evaluations','prior_evaluations')})
        budget.check()
    except BaseException as exc:
        result.update(status='unresolved', error=type(exc).__name__+': '+str(exc))
    finally:
        if result['status'] != 'completed':
            result['partial_backend_records'] = {}
            for name in ('capture','comparison'):
                log = out/(name+'.stdout')
                if log.exists():
                    records = []
                    for line in log.read_text().splitlines():
                        try: records.append(json.loads(line))
                        except ValueError: pass
                    result['partial_backend_records'][name] = {'complete_JSON_records':len(records),
                                                               'last_record':records[-1] if records else None}
        result.update(children=budget.children, CPU_s=budget.used_cpu(), wall_s=time.monotonic()-budget.started,
                      supervisor_peak_RSS_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
                      closed_files={p.name:identity(p) for p in out.iterdir() if p.is_file()})
        save(out/'receipt.json', result)
    print(json.dumps({k:result[k] for k in ('status','capture_invocations','comparison_invocations')},sort_keys=True))
    return 0 if result['status'] == 'completed' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qualification',type=Path,required=True)
    parser.add_argument('--publication',type=Path,required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(InterruptedError('SIGTERM')))
    sys.exit(run(args.qualification.resolve(), args.publication.resolve()))
