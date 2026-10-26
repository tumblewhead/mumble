#!/usr/bin/env python3
"""Bounded host-adapter fixtures; no primary seeds, cell streams or fit campaign."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import struct
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
OBS = struct.Struct('<Qddd')
METRIC = struct.Struct('<Q7dQiI')
SOURCE = '11' * 32
HELPER = r'''
#include "scm_hypothesis_checkpoint.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
static scm_hypothesis b,saved;
static scm_hypothesis_workspace w;
static scm_hypothesis_query_result q;
static scm_hypothesis_config c;
static unsigned char buf[SCM_HYPOTHESIS_CHECKPOINT_BUFFER_BYTES];
static char path[512];
static int save(const char*dir,const char*name){
 int n=snprintf(path,sizeof path,"%s/%s.bin",dir,name);
 return n<0||(size_t)n>=sizeof path?-1:scm_hypothesis_checkpoint_save(&b,path,buf);
}
static int init(void){scm_hypothesis_config_default(&c);memset(c.source_id,0x11,sizeof c.source_id);return scm_hypothesis_init(&b,&c,SCM_HYPOTHESIS_PUBLIC_LOGQ_SPLIT);}
int main(int argc,char **argv){
 int j;unsigned char bad[32];scm_sample x={1./35.,.03,3.8};
 if(argc!=2||init())return 1;
 saved=b;
 for(j=-1;j<2;j++)if(scm_hypothesis_query(&b,j,&q)||memcmp(&saved,&b,sizeof b))return 2;
 memset(bad,0x22,sizeof bad);
 if(scm_hypothesis_ingest(&b,bad,0,&x,1,&w)!=SCM_ONLINE_ERR_SOURCE||memcmp(&saved,&b,sizeof b))return 3;
 if(scm_hypothesis_ingest(&b,c.source_id,1,&x,1,&w)!=SCM_ONLINE_ERR_ORDER||memcmp(&saved,&b,sizeof b))return 4;
 if(init())return 5;
 b.component[1].factor[SCM_HYPOTHESIS_FACTOR_INDEX(11,0)]=1e200;
 if(scm_hypothesis_validate(&b)||save(argv[1],"rejection"))return 6;
 if(init())return 7;
 b.component[1].mean[11]=0.;
 if(scm_hypothesis_validate(&b)||save(argv[1],"recovery"))return 8;
 if(init())return 9;
 memset(b.component[0].factor,0,sizeof b.component[0].factor);
 if(scm_hypothesis_ingest(&b,c.source_id,0,&x,1,&w)||scm_hypothesis_validate(&b))return 10;
 if(b.component[0].evidence_next_index!=0||b.component[1].evidence_next_index!=1||b.header.bank_evidence_next_index!=1)return 11;
 if(save(argv[1],"lag"))return 12;
 puts("{\"checks\":8,\"input_deliveries\":3,\"query_byte_purity\":true,\"source_order_atomicity\":true,\"fixtures_created\":3}");
 return 0;
}
'''


def read_queries(path):
    rows = [json.loads(s) for s in path.read_text().splitlines()]
    return {r['next_index']: r for r in rows}


def read_metrics(path):
    b = path.read_bytes()
    assert len(b) % METRIC.size == 0
    return list(METRIC.iter_unpack(b))


def independent_prediction(mean, dt, current):
    z = mean[11] - current * dt / (3600 * math.exp(mean[5]))
    v = [mean[7+j] * current + (mean[12+j] - mean[7+j] * current)
         * math.exp(-dt / math.exp(mean[j])) for j in range(3)]
    h = mean[15]
    if current:
        target = 1.0 if current > 0 else -1.0
        gamma = math.exp(mean[3 if current > 0 else 4])
        h = target + (h-target) * math.exp(-gamma*abs(current)*dt/3600)
    return 3 + 1.15*z + .08*math.tanh(8*(z-.5)) - mean[6]*current - sum(v) - mean[10]*h


def signal_fixture(binary, out):
    """One cooperative-stop fixture, capped at512 delivered toy intervals."""
    data=out/'observations.bin'
    data.write_bytes(b''.join(OBS.pack(i,1/35,.03 if i%70<35 else 0.,3.8+.001*math.sin(i/13)) for i in range(512)))
    indices=out/'queries.txt'
    indices.write_text(''.join(str(i)+'\n' for i in range(513)))
    cmd=[str(binary),'--data',str(data),'--source',SOURCE,'--end','512',
         '--metrics',str(out/'metrics.bin'),'--queries',str(out/'queries.jsonl'),
         '--query-indices',str(indices),'--checkpoint-prefix',str(out/'learner'),
         '--checkpoint-indices','64,512']
    checks=[];error=None;receipt=None;proc=None;sent=None;finish=None;stdout='';stderr=''
    def ck(ok,name):
        checks.append({'name':name,'passed':bool(ok)})
        if not ok:raise AssertionError(name)
    try:
        proc=subprocess.Popen(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        deadline=time.monotonic()+5
        # Query-file creation follows handler installation. Wait for the early
        # checkpoint as well so the existing35-record ring is exercised.
        while not (out/'queries.jsonl').exists():
            ck(proc.poll() is None,'alive_until_query_file')
            if time.monotonic()>deadline:raise TimeoutError('query-file synchronization')
            time.sleep(.0002)
        while not (out/'learner-64.bin').exists():
            ck(proc.poll() is None,'alive_until_early_checkpoint')
            if time.monotonic()>deadline:raise TimeoutError('checkpoint synchronization')
            time.sleep(.0002)
        sent=time.monotonic();os.kill(proc.pid,signal.SIGINT)
        stdout,stderr=proc.communicate(timeout=1)
        finish=time.monotonic();receipt=json.loads(stdout)
        ck(proc.returncode!=0,'cooperative_stop_has_nonzero_exit')
        ck(receipt['operation']=='supervisor_stop' and receipt['supervisor_signal']==signal.SIGINT,'signal_reason_recorded')
        ck(64<=receipt['input_deliveries']<512,'stop_occurs_inside_declared_fixture')
        n=receipt['next_index']
        ck(receipt['metric_records']==receipt['consumed_intervals']==receipt['input_deliveries']==n,'complete_exactly_once_prefix_before_stop')
        ck(receipt['failure_capture_ok'],'cooperative_first_failure_capture_complete')
        failure=json.loads((out/'learner-failure.json').read_text())
        ck(failure['entering_index']==failure['next_index']==failure['failed_input_index']==n,'captured_entering_bank_is_current_safe_boundary')
        ck((out/'learner-failure-entering.bin').read_bytes()==(out/'learner-failure-state.bin').read_bytes(),'safe_boundary_canonical_banks_identical')
        ring=list(OBS.iter_unpack((out/'learner-failure-inputs.bin').read_bytes()))
        ck(len(ring)==35 and all(ring[j+1][0]==ring[j][0]+1 for j in range(34)),'existing35_observation_ring_preserved')
        ck(ring[-1][0] in (n-1,n),'ring_marks_last_consumed_or_read_unconsumed_input')
        ck(finish-sent<1,'diagnostic_flush_completes_inside_one_second')
    except BaseException as exc:
        error={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
        if proc is not None and proc.poll() is None:
            proc.kill();stdout,stderr=proc.communicate();finish=time.monotonic()
    (out/'run.stdout.txt').write_text(stdout)
    (out/'run.stderr.txt').write_text(stderr)
    result={'schema':'mumble_continuous_adapter_signal_preflight_v1',
            'status':'passed' if error is None else 'failed','checks':checks,
            'checks_passed':sum(x['passed'] for x in checks),'input_deliveries':receipt['input_deliveries'] if receipt else None,
            'maximum_possible_fixture_deliveries':512,'previous_adapter_deliveries':217,
            'cumulative_known_adapter_deliveries':217+receipt['input_deliveries'] if receipt else None,
            'stop_to_exit_s':finish-sent if finish is not None and sent is not None else None,
            'command':cmd,'worker_receipt':receipt,'error':error,'primary_runs':0,'primary_noise_draws':0,
            'adapter_sha256':hashlib.sha256((ROOT/'tools/continuous_probe.c').read_bytes()).hexdigest(),
            'test_sha256':hashlib.sha256((ROOT/'tests/test_continuous_probe.py').read_bytes()).hexdigest(),
            'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest()}
    (out/'receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['status','checks_passed','input_deliveries','cumulative_known_adapter_deliveries','stop_to_exit_s','error']},indent=2))
    return 0 if error is None else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output-root', type=Path, required=True)
    ap.add_argument('--binary', type=Path, default=ROOT/'build/continuous_probe')
    ap.add_argument('--signal-only', action='store_true',help='Run only one <=512-delivery cooperative-stop fixture.')
    args = ap.parse_args()
    out = args.output_root.resolve()
    out.mkdir(parents=True, exist_ok=False)
    binary = args.binary.resolve()
    if args.signal_only:
        return signal_fixture(binary,out)
    checks, invocations = [], []
    used = 0
    error = None
    started = time.monotonic()

    def check(ok, name, detail=None):
        checks.append({'name': name, 'passed': bool(ok), **({'detail': detail} if detail is not None else {})})
        if not ok:
            raise AssertionError(name)

    def invoke(cmd, directory, name, expected_success=True, max_new_deliveries=0):
        nonlocal used
        check(used + max_new_deliveries <= 1024, name+'_within_delivery_budget')
        t = time.monotonic()
        proc = subprocess.run([str(x) for x in cmd], cwd=ROOT, capture_output=True, text=True, timeout=30)
        (directory/(name+'.stdout.txt')).write_text(proc.stdout)
        (directory/(name+'.stderr.txt')).write_text(proc.stderr)
        row = {'name': name, 'command': [str(x) for x in cmd], 'returncode': proc.returncode,
               'elapsed_s': time.monotonic()-t, 'expected_success': expected_success}
        parsed = None
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
            except json.JSONDecodeError:
                pass
        if parsed and 'input_deliveries' in parsed:
            used += parsed['input_deliveries']
            row['input_deliveries'] = parsed['input_deliveries']
            row['receipt'] = parsed
        invocations.append(row)
        (directory/(name+'.execution.json')).write_text(json.dumps(row,indent=2)+'\n')
        check((proc.returncode == 0) == expected_success, name+'_expected_exit', row)
        return parsed

    def case(name, observations, end, *, query_indices=None, checkpoints=None,
             restore=None, cold=False, data_start=0, source=SOURCE, cap=None,
             success=True, max_new_deliveries=None):
        d = out/name
        d.mkdir()
        data = d/'observations.bin'
        data.write_bytes(b''.join(OBS.pack(*row) for row in observations))
        indices = d/'queries.txt'
        indices.write_text(''.join(str(i)+'\n' for i in (query_indices if query_indices is not None else range(data_start,end+1))))
        cp = checkpoints if checkpoints is not None else [end]
        cmd = [binary,'--data',data,'--data-start-index',data_start,'--source',source,
               '--end',end,'--metrics',d/'metrics.bin','--queries',d/'queries.jsonl',
               '--query-indices',indices,'--checkpoint-prefix',d/'learner',
               '--checkpoint-indices',','.join(map(str,cp))]
        if restore:
            cmd += ['--restore',restore]
        if cold:
            cmd += ['--cold-reset']
        if cap is not None:
            cmd += ['--max-output-bytes',cap]
        receipt = invoke(cmd,d,'run',success, max_new_deliveries if max_new_deliveries is not None else len(observations))
        check(receipt is not None, name+'_receipt_parse')
        return d,receipt

    try:
        helper_dir = out/'helper'
        helper_dir.mkdir()
        helper_src = helper_dir/'fixture.c'
        helper_src.write_text(HELPER)
        helper_bin = helper_dir/'fixture'
        invoke(['cc','-std=c99','-O2','-Wall','-Wextra','-Wpedantic','-Werror','-Iinclude',helper_src,
                'src/scm_hypothesis.c','src/scm_hypothesis_checkpoint.c','src/scm_model.c','-lm','-o',helper_bin],helper_dir,'compile')
        hr = invoke([helper_bin,helper_dir],helper_dir,'fixtures',max_new_deliveries=3)
        check(hr['query_byte_purity'] and hr['source_order_atomicity'],'API_queries_pure_and_source_order_atomic')

        obs = [(i,1/35,0.0 if i<21 or i>=56 else .03 if i<42 else -.02,3.8+.002*math.sin(i/7)) for i in range(70)]
        whole, wr = case('whole',obs,70,checkpoints=[0,35,70])
        qs, ms = read_queries(whole/'queries.jsonl'), read_metrics(whole/'metrics.bin')
        check(wr['input_deliveries']==70 and wr['consumed_intervals']==70 and len(ms)==70,'one_metric_per_exactly_once_interval')
        check(wr['owned_subtotal_bytes']==7152,'core_owned_7152_and_observers_separate')
        check(max(len(s)+1 for s in (whole/'queries.jsonl').read_text().splitlines())<=8192,'full_queries_fit_frozen_record_limit')
        check(len(qs)==71 and sorted(qs)==list(range(71)),'query_indices_deduplicated_and_complete')
        init=qs[0]['aggregate']
        check(init['point_available']==0 and init['capacity_available']==0 and init['current_soc']==0 and init['capacity_Ah']==0,'initial_API_unavailable_placeholders_present')
        check(abs(init['raw_soc']-.68)<1e-15 and abs(init['raw_capacity_Ah']-.06)<1e-15,'raw_prior_centers_not_zero_placeholders')
        forecast_errors=[]
        for i,row in enumerate(ms):
            prior=qs[i]
            weights=[math.exp(x) for x in prior['log_weights']]
            total=weights[0]+weights[1]
            predicted=sum(weights[j]/total*independent_prediction(prior['components'][j]['mean'],obs[i][1],obs[i][2]) for j in range(2))
            forecast_errors.append(abs(row[4]-predicted))
            check(row[0]==i+1 and row[9]==0 and row[8]&4 and row[8]&8,'scalar_schema_and_forecast_availability_'+str(i))
        check(max(forecast_errors)<3e-14,'causal_forecast_matches_independent_preupdate_physics',max(forecast_errors))
        check(abs(ms[0][4]-ms[0][5])>1e-4,'preupdate_forecast_distinct_from_filtered_fit')

        sparse, sr = case('sparse_queries',obs,70,query_indices=[0,70],checkpoints=[70])
        check((whole/'learner-70.bin').read_bytes()==(sparse/'learner-70.bin').read_bytes(),'query_frequency_does_not_change_canonical_state')
        check((whole/'metrics.bin').read_bytes()==(sparse/'metrics.bin').read_bytes(),'query_frequency_does_not_change_scalar_outputs')

        warm, warmr=case('warm',obs[35:],70,data_start=35,restore=whole/'learner-35.bin',checkpoints=[70],query_indices=range(71))
        check((warm/'learner-70.bin').read_bytes()==(whole/'learner-70.bin').read_bytes(),'fresh_process_warm_final_checkpoint_byte_parity')
        check((warm/'metrics.bin').read_bytes()==(whole/'metrics.bin').read_bytes()[35*80:],'warm_scalar_suffix_byte_parity')
        wq=read_queries(warm/'queries.jsonl')
        check(all(wq[n]==qs[n] for n in range(36,71)),'warm_subsequent_full_query_parity')
        check(wq[35]['pre_correction_log_likelihood']==[None,None] and not wq[35]['current_score_attempt'],'resume_scratch_marked_unavailable')

        cold, cr=case('cold',obs[35:],70,data_start=35,restore=whole/'learner-35.bin',cold=True,checkpoints=[70])
        cq=read_queries(cold/'queries.jsonl')[35]
        check(cq['aggregate']['cold_resets']==1 and cq['aggregate']['epoch_begin']==35 and cq['aggregate']['elapsed_s']==qs[35]['aggregate']['elapsed_s'],'cold_retains_clock_cursor_and_records_history_loss')
        check(cq['aggregate']['point_available']==0 and cq['aggregate']['capacity_available']==0 and cq['aggregate']['excitation']==0 and cq['log_weights']==[-math.log(2),-math.log(2)],'cold_loses_knowledge_and_resets_public_weights')
        check(abs(cq['aggregate']['raw_soc']-.68)<1e-15 and abs(cq['aggregate']['raw_capacity_Ah']-.06)<1e-15,'cold_uses_public_prior_not_scoring_truth')

        rejected, rr=case('rejected_voltage',[(0,1/35,.03,3.8)],1,restore=helper_dir/'rejection.bin',success=False,max_new_deliveries=1)
        rm=read_metrics(rejected/'metrics.bin')[0]
        check(rr['operation']=='voltage_transaction' and rr['input_deliveries']==1 and rr['consumed_intervals']==1 and rr['rejected_voltage_count']==1 and rm[9]==0 and rm[10]&16,'zero_ingest_return_rejection_still_stops')
        check(not rm[8]&4 and math.isnan(rm[4]),'rejected_transaction_has_no_causal_forecast')
        check(rr['failure_capture_ok'] and (rejected/'learner-failure-entering.bin').read_bytes()==(helper_dir/'rejection.bin').read_bytes(),'rejection_preserves_exact_entering_checkpoint')

        recovered, rec=case('recovery',[(0,1/35,.03,3.8)],1,restore=helper_dir/'recovery.bin',success=False,max_new_deliveries=1)
        rcm=read_metrics(recovered/'metrics.bin')[0]
        check(rec['operation']=='recovery' and rec['input_deliveries']==1 and rec['consumed_intervals']==1 and rcm[9]>0 and rcm[8]==0,'accepted_recovery_stops_and_withholds_current_output')
        check(rec['failure_capture_ok'],'recovery_first_failure_capture')

        lag, lr=case('lagging_evidence',[(1,1/35,.03,3.8)],2,data_start=1,restore=helper_dir/'lag.bin',checkpoints=[2])
        lq=read_queries(lag/'queries.jsonl')[2]
        check(lq['components'][0]['evidence_next_index']==0 and lq['components'][1]['evidence_next_index']==2 and lq['bank_evidence_next_index']==2,'legitimate_conditional_cursor_lag_is_accepted')

        _, ir=case('wrong_index',[(1,1/35,.03,3.8)],1,success=False,max_new_deliveries=0)
        check(ir['operation']=='input_index' and ir['input_deliveries']==0 and ir['failure_capture_ok'],'wrong_input_index_stops_before_assimilation')
        _, dr=case('duplicate',[(0,1/35,.03,3.8),(0,1/35,.03,3.8)],2,success=False,max_new_deliveries=1)
        check(dr['operation']=='input_index' and dr['input_deliveries']==1 and dr['consumed_intervals']==1,'duplicate_never_assimilated_twice')
        _, zr=case('zero_interval',[(0,0.0,.03,3.8)],1,success=False,max_new_deliveries=0)
        check(zr['operation']=='input_domain' and zr['input_deliveries']==0,'zero_dt_boundary_observation_refused')
        _, source_r=case('wrong_restore_source',obs[35:],70,data_start=35,restore=whole/'learner-35.bin',source='22'*32,checkpoints=[70],success=False,max_new_deliveries=0)
        check(source_r['operation']=='restore' and source_r['input_deliveries']==0,'restore_source_identity_is_enforced')
        _, capr=case('output_cap',[(0,1/35,.03,3.8)],1,cap=32768,success=False,max_new_deliveries=0)
        check(capr['operation']=='initial_checkpoint' and capr['output_bytes']<=32768 and capr['input_deliveries']==0 and capr['failure_capture_ok'],'budget_stop_retains_reserved_failure_artifacts')
        check(used<=1024,'total_fixture_delivery_budget',used)
    except BaseException as exc:
        error={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
    receipt={'schema':'mumble_continuous_adapter_preflight_v1','status':'passed' if error is None else 'failed',
             'checks_passed':sum(x['passed'] for x in checks),'checks':checks,
             'input_deliveries':used,'delivery_budget':1024,'primary_runs':0,'primary_noise_draws':0,
             'elapsed_s':time.monotonic()-started,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
             'adapter_sha256':hashlib.sha256((ROOT/'tools/continuous_probe.c').read_bytes()).hexdigest(),
             'invocations':invocations,'error':error}
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({k:receipt[k] for k in ['status','checks_passed','input_deliveries','elapsed_s','error']},indent=2))
    return 0 if error is None else 1


if __name__=='__main__':
    sys.exit(main())
