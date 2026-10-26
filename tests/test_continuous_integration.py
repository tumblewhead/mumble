#!/usr/bin/env python3
"""Bounded coupled source/learner and supervisor preflight; no primary seeds."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import continuous_source as cs
import run_continuous_learning as run


def main(out):
    started=time.monotonic();out.mkdir(parents=True,exist_ok=False)
    checks=[];executions=[];accounting=[];draws=0;deliveries=0;error=None
    def check(condition,name):
        checks.append({'name':name,'passed':bool(condition)})
        if not condition:raise AssertionError(name)
    def child(command,directory,label):
        nonlocal draws,deliveries
        execution=run.monitor(command,directory,label,time.monotonic()+30,out)
        executions.append(execution)
        try:receipt=json.loads((directory/(label+'.stdout')).read_text())
        except (OSError,json.JSONDecodeError):
            failure_path=directory/'source'/'failure.json'
            receipt=json.loads(failure_path.read_text()) if failure_path.exists() else {}
        key='noise_draws_generated' if label=='source' else 'input_deliveries'
        count=receipt.get(key)
        accounting.append({'worker':directory.name+'/'+label,'quantity':key,'count':count,
                           'exact':count is not None})
        if label=='source':draws+=count or 0
        else:deliveries+=count or 0
        check(execution['returncode']==0 and execution['stop_cause'] is None,label+'_successful_process')
        return receipt
    try:
        plan=run.check_plan()
        manifest=cs.make_source_manifest(plan,run.CONTRACT_SHA,'cell_a',fixture_seed=424242,
             fixture_events=[{'count':70,'current_A':current,'label':label,'phase':label}
                             for current,label in [(0.,'toy_rest'),(.03,'toy_discharge'),(-.03,'toy_charge')]])
        run.save(out/'manifest.json',manifest)
        binary=ROOT/'build/continuous_probe'
        base_queries=run.query_indices(manifest['events'],0,210,[53,70,210])
        def source(label,begin,restore=None):
            d=out/label;d.mkdir()
            q=[n for n in base_queries if n>=begin]
            run.save(d/'queries.json',q);run.save(d/'checkpoints.json',[n for n in [53,70,210] if n>=begin])
            command=[sys.executable,str(ROOT/'tools/continuous_source.py'),'--manifest',str(out/'manifest.json'),
                     '--output-dir',str(d/'source'),'--end','210','--query-indices',str(d/'queries.json'),
                     '--checkpoint-indices',str(d/'checkpoints.json')]
            if restore is not None:command+=['--restore',str(restore)]
            receipt=child(command,d,'source')
            audit=run.verify_source_files(d/'source',manifest,begin,210,q)
            run.save(d/'source_audit.json',audit)
            return d,q
        def learner(d,q,source_dir,begin,restore=None,cold=False):
            indices=d/'queries.txt';run.write_indices(indices,q)
            source_receipt=json.loads((source_dir/'receipt.json').read_text())
            command=[str(binary),'--data',str(source_dir/'observations.bin'),
                     '--data-start-index',str(source_receipt['start_index']),'--source',cs.source_id(manifest),
                     '--end','210','--metrics',str(d/'metrics.bin'),'--queries',str(d/'queries.jsonl'),
                     '--query-indices',str(indices),'--checkpoint-prefix',str(d/'learner'),
                     '--checkpoint-indices',','.join(str(n) for n in [53,70,210] if n>begin)]
            if restore is not None:command+=['--restore',str(restore)]
            if cold:command+=['--cold-reset']
            receipt=child(command,d,'learner')
            check(receipt['status']=='complete' and receipt['input_deliveries']==210-begin,
                  d.name+'_exact_deliveries')
            check(receipt['owned_subtotal_bytes']==7152 and receipt['query_records']==len(q),
                  d.name+'_query_and_owned_accounting')
            run.save(d/'learner_receipt.json',receipt)
            return receipt
        base,bq=source('base',0)
        learner(base,bq,base/'source',0)
        for begin,label in [(53,'interior'),(70,'boundary')]:
            run.coupled_checkpoint(base,base/'source',base/'learner',begin,manifest)
            suffix,sq=source(label,begin,base/'source'/('source-cp-'+str(begin)+'.json'))
            check(run.equal_suffix(base/'source'/'observations.bin',suffix/'source'/'observations.bin',begin*32)==(210-begin)*32,
                  label+'_new_process_source_byte_parity_before_learner')
            check((base/'source'/'source_final.json').read_bytes()==(suffix/'source'/'source_final.json').read_bytes(),
                  label+'_new_process_complete_source_state_parity')
            learner(suffix,sq,suffix/'source',begin,base/('learner-'+str(begin)+'.bin'))
            check(run.equal_suffix(base/'metrics.bin',suffix/'metrics.bin',begin*80)==(210-begin)*80,
                  label+'_all_scalar_bytes_equal')
            check(run.compare_queries(base/'queries.jsonl',suffix/'queries.jsonl',begin)==len(sq),
                  label+'_full_query_lexemes_equal')
            check((base/'learner-210.bin').read_bytes()==(suffix/'learner-210.bin').read_bytes(),
                  label+'_canonical_final_learner_checkpoint_equal')
        cold=out/'cold';cold.mkdir();cq=[n for n in base_queries if n>=70]
        learner(cold,cq,base/'source',70,base/'learner-70.bin',True)
        check(run.verify_cold_entry(base/'queries.jsonl',cold/'queries.jsonl',70)['passed'],
              'cold_public_reset_semantics_and_original_physical_suffix')
        check(draws==507 and deliveries==647,'declared_toy_counts507_draws647_deliveries')
        from score_continuous_learning import score_arm
        score=score_arm(metrics=base/'metrics.bin',truth=base/'source'/'truth.bin',queries=base/'queries.jsonl',
              full_truth=base/'source'/'truth.jsonl',plan=plan,cell='cell_a',arm='A_uninterrupted',
              start_index=0,end_index=210,output=out/'integrated_score.json',observations=base/'source'/'observations.bin',
              observations_start_index=0,required_query_indices=base_queries)
        check(score['completed_valid_arm'],'real_fixture_metrics_truth_and_full_query_scoring_join')
        # An invalid completed arm is a validity failure even if scoring returns
        # normally; point-accuracy target misses do not affect this gate.
        import score_continuous_learning as scoring
        invalid_dir=out/'invalid_score_gate';invalid_dir.mkdir()
        item={'arm':'fabricated_invalid','metrics':str(base/'metrics.bin'),
              'truth':str(base/'source'/'truth.bin'),'queries':str(base/'queries.jsonl'),
              'full_truth':str(base/'source'/'truth.jsonl'),'cell':'cell_a',
              'start_index':0,'end_index':210,'observations':str(base/'source'/'observations.bin'),
              'observations_start_index':0,'expected_complete':True,'required_query_indices':base_queries}
        run.save(invalid_dir/'job.json',{'arms':[item],'output_dir':str(invalid_dir),'budget_root':str(out)})
        original_score=scoring.score_arm;original_budget=run._OUTPUT_ROOT
        scoring.score_arm=lambda **kwargs:{'completed_valid_arm':False,'fixture':'fabricated_invalid_result'}
        try:
            try:run.score_job(invalid_dir/'job.json')
            except run.StopStudy:checks.append({'name':'invalid_completed_arm_propagates_scoring_failure','passed':True})
            else:raise AssertionError('scorer_invalid_result_accepted')
        finally:scoring.score_arm=original_score;run._OUTPUT_ROOT=original_budget
        # Exercise supervisor gates with non-learner workers and no RNG.
        supervisor=out/'supervisor';supervisor.mkdir()
        try:run.monitor([sys.executable,'-c','raise SystemExit(99)'],supervisor,'expired',time.monotonic()-1,out)
        except run.StopStudy:checks.append({'name':'expired_deadline_never_launches_worker','passed':True})
        else:raise AssertionError('expired_deadline_launch')
        original_emit=run.emit
        def injected(event,**values):
            if event=='process_started':raise OSError('injected supervisor logging error')
            return original_emit(event,**values)
        run.emit=injected
        try:failed=run.monitor([sys.executable,'-c','import time; time.sleep(10)'],supervisor,'parent_error',time.monotonic()+5,out)
        finally:run.emit=original_emit
        executions.append(failed)
        check(failed['stop_cause']=='supervisor_exception' and failed['cooperative_stop_requested'],
              'parent_error_stops_child_before_return')
        try:os.waitpid(failed['pid'],os.WNOHANG)
        except ChildProcessError:checks.append({'name':'parent_error_child_reaped_exactly_once','passed':True})
        else:raise AssertionError('child_not_reaped')
        timeout=run.monitor([sys.executable,'-c','import signal,time; signal.signal(signal.SIGINT,signal.SIG_IGN); time.sleep(10)'],
                  supervisor,'hard_stop',time.monotonic()+.2,out)
        executions.append(timeout)
        check(timeout['stop_cause']=='wall_time_budget' and timeout['hard_killed'] and timeout['returncode']==-9,
              'uncooperative_worker_reaped_after_bounded_hard_stop')
    except BaseException as exc:
        error={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
    result={'schema':'mumble_continuous_integration_preflight_v1','status':'passed' if error is None else 'failed',
            'checks':checks,'checks_passed':sum(row['passed'] for row in checks),'executions':executions,
            'toy_noise_draws':draws if all(a['exact'] for a in accounting if a['quantity']=='noise_draws_generated') else None,
            'learner_deliveries':deliveries if all(a['exact'] for a in accounting if a['quantity']=='input_deliveries') else None,
            'known_toy_noise_draws':draws,'known_learner_deliveries':deliveries,'worker_accounting':accounting,
            'maximum_planned_learner_deliveries':647,
            'primary_noise_draws':0,'primary_learner_deliveries':0,'execution_wall_s':time.monotonic()-started,
            'source_sha256':run.source_hashes(run.check_plan()),'binary_sha256':run.sha(ROOT/'build/continuous_probe'),
            'error':error}
    run.save(out/'receipt.json',result)
    print(json.dumps({key:result[key] for key in ['status','checks_passed','toy_noise_draws','learner_deliveries','execution_wall_s','error']},indent=2))
    return 0 if error is None else 1


def metadata_failures(out):
    """Only malformed failure evidence; no source or learner process."""
    started=time.monotonic();out.mkdir(parents=True,exist_ok=False);checks=[];error=None
    def check(value,name):
        checks.append({'name':name,'passed':bool(value)})
        if not value:raise AssertionError(name)
    try:
        for i,body in enumerate(['','{','[]','{}','{"noise_draws_generated":null,"noise_draws_exact":false}']):
            d=out/('source_'+str(i));d.mkdir();(d/'receipt.json').write_text(body)
            (d/'failure.json').write_text('{')
            result=run.generation_accounting([d])
            check(result['total'] is None and not result['exact'],'damaged_source_metadata_unknown_'+str(i))
        d=out/'learner';d.mkdir();(d/'metrics.bin').write_bytes(b'0'*83)
        for i,body in enumerate(['','{','[]','{}','{"status":"complete","input_deliveries":3}']):
            (d/'learner.stdout').write_text(body)
            receipt=run.read_learner_receipt(d,'11'*32)
            check(receipt['input_deliveries'] is None and receipt['persisted_complete_metric_records']==1
                  and receipt['persisted_metric_trailing_bytes']==3,'damaged_learner_metadata_unknown_'+str(i))
        original=run.capture_source_failure
        def fault(*args,**kwargs):raise ValueError('fabricated journal digest error')
        run.capture_source_failure=fault
        try:captured=run.preserve_failure_source(None,None,None,None)
        finally:run.capture_source_failure=original
        check(captured['status']=='secondary_capture_failure' and captured['original_learner_stop_preserved'],
              'secondary_capture_error_does_not_replace_original_stop')
    except BaseException as exc:
        error={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
    result={'schema':'mumble_continuous_metadata_failure_preflight_v1','status':'passed' if error is None else 'failed',
            'checks':checks,'checks_passed':sum(row['passed'] for row in checks),'error':error,
            'learner_deliveries':0,'toy_noise_draws':0,'primary_noise_draws':0,
            'execution_wall_s':time.monotonic()-started,'source_sha256':run.source_hashes(run.check_plan())}
    run.save(out/'receipt.json',result)
    print(json.dumps({k:result[k] for k in ['status','checks_passed','learner_deliveries','toy_noise_draws','execution_wall_s','error']},indent=2))
    return 0 if error is None else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--failure-metadata-only',action='store_true')
    args=parser.parse_args()
    raise SystemExit((metadata_failures if args.failure_metadata_only else main)(args.output_dir.resolve()))
