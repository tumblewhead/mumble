#!/usr/bin/env python3
"""Freeze and execute the one preregistered continuous-learning diagnostic.

No learner/model source is changed. Source generation and scoring run in
separate helper processes; the C learner receives observations and public IDs.
All outputs are exclusive-created. First validity failure closes the study.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import resource
import signal
import shutil
import struct
import subprocess
import sys
import time
import traceback
from fractions import Fraction

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / 'plans/continuous_learning_validation_001.json'
CONTRACT_SHA = '8fa48af8ce027cfb82a7bac1f943a48517a30d311825c90e833d90c0ff551851'
IMPL = ROOT / 'experiments/continuous_learning_validation_001/implementation'
BINARY = ROOT / 'reference_binaries/continuous_learning_validation_001/continuous_probe'
LIMIT = 536870912
METADATA_RESERVE = 1048576
_OUTPUT_ROOT = None
RECORD = struct.Struct('<Q7dQiI')


class StopStudy(RuntimeError):
    pass


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def save(path, obj, *, emergency=False):
    path = Path(path)
    body=(json.dumps(obj,indent=2,allow_nan=False)+'\n').encode()
    if _OUTPUT_ROOT is not None and path.resolve().is_relative_to(_OUTPUT_ROOT):
        ceiling=LIMIT if emergency else LIMIT-METADATA_RESERVE
        if tree_bytes(_OUTPUT_ROOT)+len(body)>ceiling:
            raise StopStudy('Metadata output budget reached before write')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:stream.write(body)


def rel(path):
    return Path(path).resolve().relative_to(ROOT).as_posix()


def emit(event, **values):
    print(json.dumps({'event': event, **values}, allow_nan=False), flush=True)


def tree_bytes(root):
    return sum(p.stat().st_size for p in Path(root).rglob('*') if p.is_file())


def rss_bytes(pid):
    try:
        for line in Path(f'/proc/{pid}/status').read_text().splitlines():
            if line.startswith('VmRSS:'):
                return int(line.split()[1]) * 1024
    except (FileNotFoundError, ProcessLookupError):
        pass
    return 0


def environment():
    import numpy
    return {'python': sys.version, 'numpy': numpy.__version__, 'platform': platform.platform(),
            'libc': list(platform.libc_ver()), 'machine': platform.machine(),
            'OPENBLAS_NUM_THREADS': os.environ.get('OPENBLAS_NUM_THREADS'),
            'OMP_NUM_THREADS': os.environ.get('OMP_NUM_THREADS'),
            'compiler': subprocess.run(['cc', '--version'], check=True, text=True,
                                       capture_output=True).stdout.splitlines()[0]}


def source_paths(plan):
    return sorted({pin['path'] for pin in plan['frozen_estimator']['git_blobs']} | {
        'Makefile', 'tools/generate_cases.py', 'tools/continuous_source.py',
        'tools/continuous_probe.c', 'tools/score_continuous_learning.py',
        'tools/run_continuous_learning.py', 'tools/validate_continuous_learning_contract.py',
        'tests/test_continuous_source.py', 'tests/test_continuous_probe.py',
        'tests/test_continuous_scoring.py', 'tests/test_continuous_integration.py',
        'plans/continuous_learning_validation_001.json'})


def source_hashes(plan):
    return {p: sha(ROOT / p) for p in source_paths(plan)}


def check_plan():
    if sha(PLAN) != CONTRACT_SHA:
        raise StopStudy('Frozen contract hash changed')
    plan = json.loads(PLAN.read_text())
    for pin in plan['frozen_estimator']['git_blobs']:
        body = (ROOT / pin['path']).read_bytes()
        got = hashlib.sha1(b'blob ' + str(len(body)).encode() + b'\0' + body).hexdigest()
        if got != pin['sha']:
            raise StopStudy('Frozen estimator source changed: ' + pin['path'])
    return plan


def freeze(source_revision, output, preflight):
    plan = check_plan()
    qualification = json.loads(Path(preflight).read_text())
    if qualification.get('status') != 'passed' or qualification['learner_deliveries'] > 4096:
        raise StopStudy('Preflight is not qualified within the frozen delivery budget')
    if qualification['execution_wall_s']>600 or qualification['source_sha256']!=source_hashes(plan) or qualification['binary_sha256']!=sha(BINARY):
        raise StopStudy('Preflight source/binary/wall identity mismatch')
    if len(source_revision) != 40 or any(c not in '0123456789abcdef' for c in source_revision):
        raise StopStudy('An exact published source commit is required')
    receipt = {'schema': 'mumble_continuous_executable_receipt_v1',
               'status': 'frozen_before_primary_independent_receipt_review_required',
               'source_revision': source_revision, 'contract_sha256': CONTRACT_SHA,
               'source_sha256': source_hashes(plan), 'binary': rel(BINARY),
               'binary_sha256': sha(BINARY), 'environment': environment(),
               'compile_command': ['cc', '-std=c99', '-O2', '-Wall', '-Wextra', '-Wpedantic',
                                   '-Werror', '-Iinclude', 'tools/continuous_probe.c',
                                   'src/scm_hypothesis.c', 'src/scm_hypothesis_checkpoint.c',
                                   'src/scm_model.c', '-lm', '-o', 'build/continuous_probe'],
               'preflight': rel(preflight), 'preflight_sha256': sha(preflight),
               'learner_deliveries_in_preflight': qualification['learner_deliveries'],
               'primary_noise_draws': 0, 'primary_learner_deliveries': 0,
               'source_publishing': 'Git data commit from verified complete canonical base tree; selective local source snapshot',
               'created_UTC': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    save(output, receipt)
    emit('executable_frozen', path=str(output), sha256=sha(output), source_revision=source_revision)
    return receipt


def verify_freeze(receipt_path, review_path):
    plan = check_plan()
    receipt = json.loads(Path(receipt_path).read_text())
    review = json.loads(Path(review_path).read_text())
    if review.get('status') != 'pass' or review.get('executable_receipt_sha256') != sha(receipt_path):
        raise StopStudy('Independent executable receipt review missing or mismatched')
    if receipt['source_sha256'] != source_hashes(plan) or receipt['binary_sha256'] != sha(BINARY):
        raise StopStudy('Executable source/binary changed after freeze')
    if receipt['contract_sha256'] != CONTRACT_SHA or receipt['environment'] != environment():
        raise StopStudy('Contract or runtime environment changed after freeze')
    if sha(ROOT / receipt['preflight']) != receipt['preflight_sha256']:
        raise StopStudy('Preflight receipt changed after freeze')
    return plan, receipt, review


def monitor(command, logs, label, deadline, budget_root):
    """One child, exact wait4 peak RSS, bounded wall/output monitoring."""
    logs = Path(logs)
    logs.mkdir(parents=True, exist_ok=True)
    stdout_path, stderr_path = logs / (label + '.stdout'), logs / (label + '.stderr')
    started = time.monotonic()
    if started>=deadline:
        raise StopStudy(label+' deadline already expired before launch')
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
    cause = None
    cooperative_requested = None
    hard_killed = False
    supervisor_error = None
    sampled_peak = 0
    last_progress = started
    with stdout_path.open('xb') as out, stderr_path.open('xb') as err:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=out, stderr=err)
        def send(signum):
            # wait4 is the sole reaper. Popen.send_signal calls poll/waitpid.
            try:os.kill(process.pid,signum)
            except ProcessLookupError:pass
        try:
            emit('process_started', label=label, pid=process.pid)
            while True:
                waited, status, usage = os.wait4(process.pid, os.WNOHANG)
                if waited:
                    process.returncode = os.waitstatus_to_exitcode(status)
                    break
                now = time.monotonic()
                child_rss = rss_bytes(process.pid)
                sampled_peak = max(sampled_peak, child_rss)
                total = tree_bytes(budget_root)
                if cause is None:
                    if now > deadline:
                        cause = 'wall_time_budget'
                    elif max(child_rss, rss_bytes(os.getpid())) > LIMIT:
                        cause = 'host_RSS_budget'
                    elif total > LIMIT-METADATA_RESERVE:
                        cause = 'output_budget'
                    if cause:
                        send(signal.SIGINT)
                        cooperative_requested = now
                if cooperative_requested is not None and not hard_killed and now-cooperative_requested > 1:
                    send(signal.SIGKILL)
                    hard_killed = True
                if now - last_progress >= 5:
                    emit('process_progress', label=label, wall_s=round(now-started, 3),
                         output_bytes=total, sampled_RSS_bytes=child_rss)
                    last_progress = now
                time.sleep(0.1)
        except BaseException as exc:
            # No exceptional parent path can leave a generating/learning child
            # behind while the outer supervisor proceeds to scoring.
            supervisor_error={'type':type(exc).__name__,'message':str(exc),
                              'traceback':traceback.format_exc()}
            cause=cause or 'supervisor_exception'
            cooperative_requested=cooperative_requested or time.monotonic()
            send(signal.SIGINT)
            while True:
                waited,status,usage=os.wait4(process.pid,os.WNOHANG)
                if waited:
                    process.returncode=os.waitstatus_to_exitcode(status)
                    break
                if time.monotonic()-cooperative_requested>1:
                    send(signal.SIGKILL);hard_killed=True
                time.sleep(.01)
    peak = int(usage.ru_maxrss) * 1024
    if time.monotonic()>deadline and cause is None:
        cause='wall_time_budget_at_reap'
    if peak > LIMIT and cause is None:
        cause = 'host_RSS_high_water_budget'
    if tree_bytes(budget_root) > LIMIT and cause is None:
        cause = 'output_budget'
    result = {'label': label, 'command': command, 'pid':process.pid,'returncode': process.returncode,
              'wall_s': time.monotonic()-started, 'peak_RSS_bytes': peak,
              'sampled_peak_RSS_bytes': sampled_peak, 'stop_cause': cause,
              'cooperative_stop_requested': cooperative_requested is not None,
              'hard_killed': hard_killed,
              'supervisor_error':supervisor_error,
              'capture_policy': 'SIGINT at safe worker boundary; at most1s diagnostic flush, then hard kill. A cap breach fails regardless of exit status; hard kill may leave no entering checkpoint.',
              'stdout': rel(stdout_path), 'stderr': rel(stderr_path)}
    save(logs / (label + '.execution.json'), result, emergency=bool(cause))
    try:emit('process_finished', **{k: result[k] for k in ('label','returncode','wall_s','peak_RSS_bytes','stop_cause')})
    except (BrokenPipeError,OSError):pass
    return result


def query_indices(events, start, end, checkpoints):
    values = {start, end}
    values.update(range(((start+34)//35)*35, end+1, 35))
    for event in events:
        values.update(n for n in (event['start_index'], event['start_index']+1, event['end_index'])
                      if start <= n <= end)
    values.update(n for n in checkpoints if start <= n <= end)
    return sorted(values)


def write_indices(path, values):
    body=''.join(str(n)+'\n' for n in values)
    if _OUTPUT_ROOT is not None and tree_bytes(_OUTPUT_ROOT)+len(body.encode())>LIMIT-METADATA_RESERVE:
        raise StopStudy('Query-index output budget reached before write')
    with Path(path).open('x') as stream:
        stream.write(body)


def equal_suffix(baseline, suffix, offset):
    with Path(baseline).open('rb') as left, Path(suffix).open('rb') as right:
        left.seek(offset)
        count = 0
        while True:
            a, b = left.read(1<<20), right.read(1<<20)
            if a != b:
                raise StopStudy('Suffix byte mismatch at or after byte ' + str(count))
            if not a:
                return count
            count += len(a)


def query_rows(path, *, lexemes=False):
    with Path(path).open() as stream:
        for line in stream:
            row = json.loads(line, **({'parse_float':str,'parse_int':str} if lexemes else {}))
            if row.get('event') == 'query':
                yield row


def compare_queries(baseline, suffix, begin):
    expected = (x for x in query_rows(baseline, lexemes=True) if int(x['next_index']) >= begin)
    got = query_rows(suffix, lexemes=True)
    count = 0
    while True:
        a, b = next(expected, None), next(got, None)
        if a is None or b is None:
            if a is not None or b is not None:
                raise StopStudy('Warm full-query count mismatch')
            return count
        for row in (a,b):
            row.pop('reason', None)
            if int(row['next_index']) == begin:
                for key in ('current_score_attempt','score_transaction_accepted','pre_correction_log_likelihood'):
                    row.pop(key, None)
        if a != b:
            raise StopStudy('Warm full-query mismatch at ' + str(a['next_index']))
        count += 1


def coupled_checkpoint(stage, source_dir, learner_prefix, index, manifest):
    learner = Path(str(learner_prefix) + '-' + str(index) + '.bin')
    source = Path(source_dir) / ('source-cp-' + str(index) + '.json')
    snapshot = json.loads(source.read_text())
    from continuous_source import StatefulSource, source_id
    restored = StatefulSource.from_state(snapshot, expected_manifest=manifest, allow_primary=True)
    if restored.next_index != index or learner.stat().st_size != 3004:
        raise StopStudy('Coupled checkpoint cursor/extent mismatch')
    envelope = {'schema':'mumble_coupled_source_learner_checkpoint_v1','next_index':index,
                'source_id':source_id(manifest),'contract_sha256':CONTRACT_SHA,
                'learner':rel(learner),'learner_sha256':sha(learner),
                'source':rel(source),'source_sha256':sha(source)}
    save(Path(stage)/('coupled-'+str(index)+'.json'), envelope)
    return envelope


def verify_source_files(source_dir,manifest,start,end,required_queries):
    """Validate recorded source identity and exact finite accounting before C."""
    from continuous_source import source_id,StatefulSource
    directory=Path(source_dir)
    receipt=json.loads((directory/'receipt.json').read_text())
    conditions=[receipt['status']=='complete',receipt['source_id']==source_id(manifest),
                receipt['manifest_sha256']==source_id(manifest),receipt['start_index']==start,
                receipt['end_index']==end,receipt['records']==end-start,
                receipt['noise_draws_generated']==end-start,
                receipt['full_query_records']==len(required_queries),
                json.loads((directory/'source_manifest.json').read_text())==manifest]
    for name,key in [('observations.bin','observation_sha256'),('truth.bin','scalar_truth_sha256'),
                     ('truth.jsonl','full_truth_sha256'),('source_states.bin','source_state_journal_sha256'),
                     ('source_final.json','final_snapshot_sha256')]:
        conditions.append(sha(directory/name)==receipt[key])
    conditions.extend([(directory/'observations.bin').stat().st_size==(end-start)*32,
                       (directory/'truth.bin').stat().st_size==(end-start)*32,
                       (directory/'source_states.bin').stat().st_size==72+208*(end-start+1)])
    final=StatefulSource.from_state(json.loads((directory/'source_final.json').read_text()),
                                  expected_manifest=manifest,allow_primary=True)
    conditions.extend([final.next_index==end,final.hash_chain.hex()==receipt['final_hash_chain_hex']])
    actual_indices=[]
    with (directory/'truth.jsonl').open() as stream:
        for line in stream:actual_indices.append(json.loads(line)['next_index'])
    conditions.append(actual_indices==required_queries)
    # Audit constant-input charge algebra only: no new plant/noise evaluation.
    expected={k:Fraction() for k in ('signed_Ah','positive_Ah','negative_magnitude_Ah','absolute_Ah')}
    for event in manifest['events']:
        count=max(0,min(end,event['end_index'])-event['start_index'])
        if not count:continue
        term=Fraction.from_float(event['current_A']*(1.0/35.0)/3600.0)*count
        expected['signed_Ah']+=term
        expected['positive_Ah']+=max(term,0)
        expected['negative_magnitude_Ah']+=max(-term,0)
        expected['absolute_Ah']+=abs(term)
    bound=8*sys.float_info.epsilon*float(expected['absolute_Ah'])+4*math.ulp(0.0)*end
    conditions.append(set(final.charge)==set(expected))
    comparisons={}
    for key,value in final.charge.items():
        if key not in expected:raise StopStudy('Unknown source charge ledger key:'+key)
        error=abs(value-float(expected[key]))
        comparisons[key]={'error_Ah':error,'bound_Ah':bound}
        conditions.append(error<=bound)
    clock=0.0
    for _ in range(end):clock+=1.0/35.0
    conditions.extend([clock==final.actual_elapsed_s,receipt['actual_elapsed_s']==clock])
    if not all(conditions):raise StopStudy('Source identity/digest/grid/charge/clock audit failed')
    return {'status':'passed','checks':len(conditions),'source_id':source_id(manifest),
            'charge_accounting':comparisons,'actual_elapsed_s':clock,'new_noise_draws':0}


def verify_cold_entry(base_queries, cold_queries, begin):
    initial = next(query_rows(base_queries))
    cold = next(query_rows(cold_queries))
    a = cold['aggregate']
    conditions = [cold['next_index']==begin,a['epoch_begin']==begin,
                  cold['bank_evidence_next_index']==begin, bool(a['flags'] & 1),
                  not a['point_available'],not a['capacity_available'],a['excitation']==0,
                  a['cold_resets']==1,a['prediction_count']==begin,
                  cold['log_weights']==initial['log_weights']]
    for j in range(2):
        c, p = cold['components'][j], initial['components'][j]
        conditions.extend([c['mean']==p['mean'],c['coordinate_sd']==p['coordinate_sd'],
                           c['evidence_next_index']==begin])
    if not all(conditions):
        raise StopStudy('Cold reset semantics differ from public initialization/known cursor')
    return {'passed':True,'checks':len(conditions),'global_next_index':begin,
            'history_lost':True,'truth_initialization':False}


def capture_source_failure(source_dir, manifest, learner_prefix, target_dir):
    from continuous_source import snapshot_at, StatefulSource
    failure_path = Path(str(learner_prefix)+'-failure.json')
    if not failure_path.exists():
        return {'status':'unavailable_after_hard_or_early_stop','reason':'C first-failure record absent; preserve partial logs and scheduled checkpoints. Do not infer an exact failing state.'}
    failure = json.loads(failure_path.read_text())
    out = Path(target_dir)
    out.mkdir(exist_ok=True)
    indices = sorted({failure['entering_index'],failure['next_index']})
    rows = []
    source_receipt=json.loads((Path(source_dir)/'receipt.json').read_text())
    for index in indices:
        snapshot = snapshot_at(Path(source_dir)/'source_states.bin', index, manifest,
                               expected_sha256=source_receipt['source_state_journal_sha256'],allow_primary=True)
        save(out/('source-failure-'+str(index)+'.json'),snapshot,emergency=True)
        rows.append(StatefulSource.from_state(snapshot,expected_manifest=manifest,allow_primary=True).truth_query())
    body=b''.join(canonical(row)+b'\n' for row in rows)
    if _OUTPUT_ROOT is not None and tree_bytes(_OUTPUT_ROOT)+len(body)>LIMIT:
        raise StopStudy('Failure truth output budget exhausted before write')
    with (out/'supplemental_truth.jsonl').open('xb') as stream:stream.write(body)
    return {'status':'captured','source_indices':indices,'extra_noise_draws':0,'chronological_replay':False,
            'supplemental_truth':rel(out/'supplemental_truth.jsonl')}


def preserve_failure_source(source_dir,manifest,learner_prefix,target_dir):
    try:return capture_source_failure(source_dir,manifest,learner_prefix,target_dir)
    except BaseException as exc:
        return {'status':'secondary_capture_failure','error_type':type(exc).__name__,
                'error':str(exc),'traceback':traceback.format_exc(),
                'original_learner_stop_preserved':True,'extra_noise_draws':0}


def read_learner_receipt(stage,expected_source_id):
    stage=Path(stage)
    try:
        receipt=json.loads((stage/'learner.stdout').read_text())
        if not isinstance(receipt,dict) or receipt.get('schema')!='mumble_continuous_adapter_receipt_v1':
            raise ValueError('Missing or malformed adapter schema')
        required=('start_index','end_index','next_index','input_deliveries','consumed_intervals',
                  'metric_records','query_records','checkpoint_records','output_bytes',
                  'owned_subtotal_bytes','rejected_voltage_count','flags')
        if any(type(receipt.get(key)) is not int or receipt[key]<0 for key in required):
            raise ValueError('Missing or invalid adapter counters')
        if receipt.get('status') not in ('complete','failed') or receipt.get('source_id')!=expected_source_id:
            raise ValueError('Missing or invalid adapter status/source identity')
        return receipt
    except (OSError,ValueError,TypeError) as exc:
        metric_path=stage/'metrics.bin'
        persisted=metric_path.stat().st_size if metric_path.exists() else 0
        return {'status':'interrupted_or_malformed_receipt','input_deliveries':None,
                'persisted_complete_metric_records':persisted//80,
                'persisted_metric_trailing_bytes':persisted%80,
                'exact_consumption_unknown':True,'source_id':expected_source_id,
                'receipt_error':type(exc).__name__+': '+str(exc)}


def generate_job(job_path):
    from continuous_source import StatefulSource, generate_files
    job=json.loads(Path(job_path).read_text())
    verify_freeze(job['executable_receipt'],job['independent_review'])
    manifest=json.loads(Path(job['manifest']).read_text())
    source=(StatefulSource.from_state(json.loads(Path(job['restore']).read_text()),
             expected_manifest=manifest,allow_primary=True) if job.get('restore')
            else StatefulSource(manifest,allow_primary=True))
    result=generate_files(source,job['end_index'],job['output_dir'],
             query_indices=job['query_indices'],checkpoint_indices=job['checkpoint_indices'],
             chunk_size=35,max_output_bytes=job['max_output_bytes'])
    print(json.dumps(result,sort_keys=True,allow_nan=False),flush=True)


def generation_accounting(directories):
    rows=[]
    for directory in sorted(set(directories)):
        d=Path(directory)
        draws=None;exact=False;metadata_errors=[]
        for filename in ('receipt.json','failure.json'):
            path=d/filename
            if not path.exists():continue
            try:
                receipt=json.loads(path.read_text())
                if not isinstance(receipt,dict):raise ValueError('Metadata is not an object')
                value=receipt.get('noise_draws_generated')
                if type(value) is int and value>=0 and receipt.get('noise_draws_exact',True):
                    draws=value;exact=True;break
                if value is not None:raise ValueError('Invalid draw count')
            except (OSError,ValueError,TypeError) as exc:
                metadata_errors.append({'file':filename,'error':type(exc).__name__+': '+str(exc)})
        journal=d/'source_states.bin'
        committed=max(0,(journal.stat().st_size-72)//208-1) if journal.exists() else 0
        rows.append({'source_directory':rel(d),'noise_draws':draws,'exact':exact,
                     'persisted_complete_journal_records':committed,'journal_count_status':'file_extent_only_unverified',
                     'metadata_errors':metadata_errors})
    exact=all(row['exact'] for row in rows)
    return {'exact':exact,'total':sum(row['noise_draws'] for row in rows) if exact else None,
            'known_draws':sum(row['noise_draws'] or 0 for row in rows),'sources':rows}


def score_job(job_path):
    global _OUTPUT_ROOT
    from score_continuous_learning import score_arm
    job=json.loads(Path(job_path).read_text())
    _OUTPUT_ROOT=Path(job['budget_root']).resolve()
    results=[];invalid=[]
    for item in job['arms']:
        if not Path(item['metrics']).exists() or not Path(item['queries']).exists():
            results.append({'arm':item['arm'],'status':'unavailable','reason':'metrics_or_queries_absent',
                            'expected_complete':item['expected_complete']})
            if item['expected_complete']:invalid.append(item['arm']+':missing_required_logs')
            continue
        args={key:item[key] for key in ('metrics','truth','queries','full_truth','cell','arm','start_index','end_index','observations','observations_start_index','expected_complete')}
        args['plan']=str(PLAN)
        args['output']=str(Path(job['output_dir'])/(item['arm']+'.json'))
        args['required_query_indices']=item['required_query_indices']
        args['max_output_bytes']=LIMIT-tree_bytes(_OUTPUT_ROOT)-METADATA_RESERVE
        capture=item.get('failure_source_capture') or {}
        if capture.get('supplemental_truth'):args['supplemental_full_truth']=str(ROOT/capture['supplemental_truth'])
        result=score_arm(**args)
        results.append({'arm':item['arm'],'result':result})
        if item['expected_complete'] and not result.get('completed_valid_arm'):
            invalid.append(item['arm']+':scorer_validity_checks_failed')
    save(Path(job['output_dir'])/'scores.json',{'schema':'mumble_continuous_scores_v1','arms':results,
          'contract_sha256':CONTRACT_SHA,'unexpected_invalid_arms':invalid,
          'scope':'Post-inference only; no truth enters C processes.'})
    emit('scoring_complete',arms=len(results),unexpected_invalid_arms=invalid)
    if invalid:raise StopStudy('Scorer found invalid expected-complete arms: '+','.join(invalid))


def run_study(receipt_path,review_path,output):
    global _OUTPUT_ROOT
    from continuous_source import build_events,make_source_manifest,source_id
    plan,frozen,review=verify_freeze(receipt_path,review_path)
    output=Path(output).resolve()
    output.parent.mkdir(parents=True,exist_ok=True)
    output.mkdir(exist_ok=False)
    _OUTPUT_ROOT=output
    started=time.monotonic()
    arm_results=[]
    processes=[]
    failure=None
    a_gate=None
    manifests={}
    stage_sources={}
    save(output/'execution_authority.json',{'executable_receipt':rel(receipt_path),
         'executable_receipt_sha256':sha(receipt_path),'independent_review':rel(review_path),
         'independent_review_sha256':sha(review_path),'source_revision':frozen['source_revision'],
         'contract_sha256':CONTRACT_SHA})
    stages=[dict(arm,cell='cell_a') for arm in plan['A_second_cell_lifecycle']['arms']]
    b=plan['B_continuous_4h']
    stages.append({'id':'B_continuous','cell':'cell_b','start_index':0,'end_index':b['samples'],
                   'input_deliveries':b['samples'],'checkpoint_next_indices':[35*t for t in b['checkpoint_times_s']],
                   'timeout_s':b['timeout_s']})
    try:
        for spec in stages:
            if spec['id']=='B_continuous' and not a_gate:
                raise StopStudy('A validity gate did not pass')
            stage_start=time.monotonic()
            deadline=min(stage_start+spec['timeout_s'],started+3600)
            name=spec['id'];cell=spec['cell']
            stage=output/name;stage.mkdir()
            events=build_events(plan,cell)
            queries=query_indices(events,spec['start_index'],spec['end_index'],spec['checkpoint_next_indices'])
            query_path=stage/'query_indices.txt';write_indices(query_path,queries)
            prefix=stage/'learner'
            if cell not in manifests:
                manifests[cell]=make_source_manifest(plan,CONTRACT_SHA,cell)
                save(output/(cell+'_manifest.json'),manifests[cell])
            manifest=manifests[cell]
            source_dir=(output/'A_uninterrupted'/'source') if name=='A_cold_suffix' else stage/'source'
            stage_sources[name]=source_dir
            restore_learner=None
            if spec['start_index']:
                envelope=json.loads((output/'A_uninterrupted'/'coupled-31500.json').read_text())
                restore_learner=ROOT/envelope['learner']
                if sha(restore_learner)!=envelope['learner_sha256'] or sha(ROOT/envelope['source'])!=envelope['source_sha256']:
                    raise StopStudy('Coupled checkpoint changed before restore')
            if name!='A_cold_suffix':
                job={'manifest':str(output/(cell+'_manifest.json')),'output_dir':str(source_dir),
                     'executable_receipt':str(Path(receipt_path).resolve()),
                     'independent_review':str(Path(review_path).resolve()),
                     'end_index':spec['end_index'],'query_indices':queries,
                     'checkpoint_indices':spec['checkpoint_next_indices'],
                     'max_output_bytes':LIMIT-tree_bytes(output)-METADATA_RESERVE}
                if name=='A_warm_suffix':job['restore']=str(ROOT/envelope['source'])
                save(stage/'generation_job.json',job)
                execution=monitor([sys.executable,str(Path(__file__).resolve()),'--generate-job',str(stage/'generation_job.json')],
                                  stage,'generate',deadline,output)
                processes.append(execution)
                if execution['returncode'] or execution['stop_cause']:
                    raise StopStudy(name+' source generation failed')
            source_receipt=json.loads((source_dir/'receipt.json').read_text())
            data_start=source_receipt['start_index']
            source_queries=(query_indices(events,0,73500,[31500,63000,73500])
                            if name=='A_cold_suffix' else queries)
            source_audit=verify_source_files(source_dir,manifest,
                          31500 if name=='A_warm_suffix' else 0,spec['end_index'],source_queries)
            save(stage/'source_audit.json',source_audit)
            source_parity=None
            if name=='A_warm_suffix':
                base_source=output/'A_uninterrupted'/'source'
                source_parity={'observation_bytes':equal_suffix(base_source/'observations.bin',source_dir/'observations.bin',31500*32)}
                for n in spec['checkpoint_next_indices']:
                    if (base_source/('source-cp-'+str(n)+'.json')).read_bytes()!=(source_dir/('source-cp-'+str(n)+'.json')).read_bytes():
                        raise StopStudy('Warm generator checkpoint mismatch before learner launch')
                if (base_source/'source_final.json').read_bytes()!=(source_dir/'source_final.json').read_bytes():
                    raise StopStudy('Warm complete final generator state mismatch before learner launch')
                source_parity['passed']=True
                save(stage/'source_parity_before_learner.json',source_parity)
            command=[str(BINARY),'--data',str(source_dir/'observations.bin'),
                     '--data-start-index',str(data_start),'--source',source_id(manifest),
                     '--end',str(spec['end_index']),'--metrics',str(stage/'metrics.bin'),
                     '--queries',str(stage/'queries.jsonl'),'--checkpoint-prefix',str(prefix),
                     '--checkpoint-indices',','.join(str(n) for n in spec['checkpoint_next_indices']),
                     '--query-indices',str(query_path),'--max-output-bytes',str(LIMIT-tree_bytes(output)-METADATA_RESERVE)]
            if restore_learner:command+=['--restore',str(restore_learner)]
            if name=='A_cold_suffix':command+=['--cold-reset']
            item={'arm':name,'cell':cell,'start_index':spec['start_index'],'end_index':spec['end_index'],
                  'metrics':str(stage/'metrics.bin'),'queries':str(stage/'queries.jsonl'),
                  'truth':str(source_dir/'truth.bin'),'full_truth':str(source_dir/'truth.jsonl'),
                  'observations':str(source_dir/'observations.bin'),'observations_start_index':data_start,
                  'expected_complete':False,'learner_receipt':None,'process':None,
                  'source_dir':rel(source_dir),'required_query_indices':queries}
            arm_results.append(item)
            execution=monitor(command,stage,'learner',deadline,output)
            processes.append(execution);item['process']=execution
            learner=read_learner_receipt(stage,source_id(manifest))
            item['learner_receipt']=learner
            save(stage/'learner_receipt.json',learner,emergency=bool(execution['stop_cause']))
            complete=(not execution['returncode'] and not execution['stop_cause'] and learner['status']=='complete')
            item['expected_complete']=complete
            if not complete:
                item['failure_source_capture']=preserve_failure_source(source_dir,manifest,prefix,stage/'failure_source')
                raise StopStudy(name+' first learner validity/resource failure')
            if learner['input_deliveries']!=spec['input_deliveries'] or learner['next_index']!=spec['end_index'] or learner['owned_subtotal_bytes']!=7152:
                raise StopStudy(name+' delivery/owned-resource receipt mismatch')
            if learner['query_records']!=len(queries):
                raise StopStudy(name+' query-grid count mismatch')
            if learner['rejected_voltage_count'] or learner['flags'] & (2|4|8|16):
                raise StopStudy(name+' unexpected numerical/availability flag')
            for n in spec['checkpoint_next_indices']:
                coupled_checkpoint(stage,source_dir,prefix,n,manifest)
            if name=='A_warm_suffix':
                base=output/'A_uninterrupted'
                parity={'metric_bytes':equal_suffix(base/'metrics.bin',stage/'metrics.bin',31500*80),
                        'observation_bytes':source_parity['observation_bytes'],
                        'query_records':compare_queries(base/'queries.jsonl',stage/'queries.jsonl',31500)}
                for n in spec['checkpoint_next_indices']:
                    if (base/('learner-'+str(n)+'.bin')).read_bytes()!=(stage/('learner-'+str(n)+'.bin')).read_bytes():
                        raise StopStudy('Warm canonical learner checkpoint mismatch')
                parity['passed']=True;save(stage/'parity.json',parity)
            if name=='A_cold_suffix':
                cold=verify_cold_entry(output/'A_uninterrupted'/'queries.jsonl',stage/'queries.jsonl',31500)
                save(stage/'cold_semantics.json',cold)
                if time.monotonic()>deadline:
                    raise StopStudy(name+' arm deadline exceeded before validity gate')
            emit('arm_complete',arm=name,input_deliveries=learner['input_deliveries'],
                 query_records=learner['query_records'],output_bytes=tree_bytes(output))
            if time.monotonic()>deadline:
                raise StopStudy(name+' total arm wall-time budget exceeded including verification')
            if name=='A_cold_suffix':
                a_gate={'status':'passed','accuracy_used_for_admission':False,
                        'scope':'Numerical/accounting/lifecycle/known-owned-resource validity only'}
                save(output/'A_gate.json',a_gate)
    except BaseException as exc:
        failure={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
        save(output/'first_failure.json',failure,emergency=True)
        emit('study_stopped',**{k:failure[k] for k in ('type','message')})
    primary_wall=time.monotonic()-started
    generation=generation_accounting(stage_sources.values())
    receipt={'schema':'mumble_continuous_primary_receipt_v1','status':'completed' if failure is None else 'stopped_first_failure',
             'source_revision':frozen['source_revision'],'contract_sha256':CONTRACT_SHA,
             'executable_receipt_sha256':sha(receipt_path),'arms':arm_results,'processes':processes,
             'A_gate':a_gate or {'status':'not_passed'},'B_started':'B_continuous' in stage_sources,
             'B_learner_started':any(a['arm']=='B_continuous' and a['process'] is not None for a in arm_results),
             'learner_processes':sum(p['label']=='learner' for p in processes),
             'learner_input_deliveries':sum(a['learner_receipt']['input_deliveries'] for a in arm_results)
                  if all(a['learner_receipt'] is not None and a['learner_receipt']['input_deliveries'] is not None for a in arm_results) else None,
             'known_learner_input_deliveries':sum((a['learner_receipt'] or {}).get('input_deliveries') or 0 for a in arm_results),
             'generator_evaluations':generation['total'],'generation_accounting':generation,
             'primary_wall_s':primary_wall,'output_bytes_before_scoring':tree_bytes(output),'failure':failure,
             'truth_in_inference':False,'estimator_source_changed':False,'optimizer_calls':0,'old_study_reruns':0}
    receipt['generator_evaluations_exact']=generation['exact']
    if failure is None and (receipt['learner_processes']!=4 or receipt['learner_input_deliveries']!=661500
                            or receipt['generator_evaluations']!=619500 or primary_wall>3600):
        failure={'type':'FinalAccountingFailure','message':'Completed-stage count/time differs from frozen totals'}
        receipt['status']='stopped_first_failure';receipt['failure']=failure
        save(output/'first_failure.json',failure,emergency=True)
    save(output/'receipt.json',receipt,emergency=bool(failure))
    if arm_results:
        score_dir=output/'scoring';score_dir.mkdir()
        job={'arms':arm_results,'output_dir':str(score_dir),'budget_root':str(output)}
        save(output/'scoring_job.json',job,emergency=bool(failure))
        try:
            score_exec=monitor([sys.executable,str(Path(__file__).resolve()),'--score-job',str(output/'scoring_job.json')],
                               output,'scoring',min(time.monotonic()+600,started+4200),output)
            save(output/'scoring_status.json',score_exec,emergency=bool(failure or score_exec['stop_cause']))
            if score_exec['returncode'] or score_exec['stop_cause']:
                failure=failure or {'type':'ScoringFailure','message':'Post-inference scoring failed; preserve original primary.'}
        except BaseException as exc:
            scoring_failure={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
            save(output/'scoring_failure.json',scoring_failure,emergency=True)
            failure=failure or scoring_failure
    if time.monotonic()>started+4200:
        failure=failure or {'type':'TotalWallBudget','message':'Primary plus scoring exceeded4200s'}
    final={'status':'completed' if failure is None else 'stopped_or_incomplete',
           'primary_receipt':rel(output/'receipt.json'),'output_bytes':tree_bytes(output),
           'wall_including_scoring_s':time.monotonic()-started,'failure':failure}
    save(output/'completion.json',final,emergency=bool(failure))
    emit('study_finished',**final)
    return 0 if failure is None else 1


def main():
    os.environ['OPENBLAS_NUM_THREADS']='1'
    os.environ['OMP_NUM_THREADS']='1'
    def termination(signum,frame):
        raise StopStudy('Supervisor received '+signal.Signals(signum).name)
    signal.signal(signal.SIGTERM,termination)
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--freeze',action='store_true')
    group.add_argument('--run',action='store_true')
    group.add_argument('--generate-job',type=Path)
    group.add_argument('--score-job',type=Path)
    parser.add_argument('--source-revision')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--preflight',type=Path)
    parser.add_argument('--executable-receipt',type=Path)
    parser.add_argument('--review',type=Path)
    args=parser.parse_args()
    if args.freeze:
        if not args.source_revision or not args.output or not args.preflight:parser.error('freeze requires source-revision,output,preflight')
        freeze(args.source_revision,args.output,args.preflight)
    elif args.generate_job:generate_job(args.generate_job)
    elif args.score_job:score_job(args.score_job)
    else:
        if not args.output or not args.executable_receipt or not args.review:parser.error('run requires output,executable-receipt,review')
        return run_study(args.executable_receipt,args.review,args.output)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
