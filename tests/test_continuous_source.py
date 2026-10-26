#!/usr/bin/env python3
"""Bounded source fixtures; never use a primary noise sequence or learner."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import signal
import struct
import subprocess
import sys
import time
import traceback
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import continuous_source as cs


def run(out):
    checks = []
    child_draws = 0
    started = time.monotonic()
    out.mkdir(parents=True, exist_ok=False)

    def check(condition, name):
        if not condition:
            raise AssertionError(name)
        checks.append(name)

    def rejects(call, name):
        try:
            call()
        except (cs.SourceError, ValueError):
            checks.append(name)
        else:
            raise AssertionError(name)

    try:
        plan_path = ROOT / 'plans/continuous_learning_validation_001.json'
        plan = json.loads(plan_path.read_text())
        contract_sha = cs.sha256_file(plan_path)
        events = [
            {'count': 35, 'current_A': 0.030, 'label': 'toy_discharge', 'phase': 'toy_discharge'},
            {'count': 17, 'current_A': -0.045, 'label': 'toy_charge', 'phase': 'toy_charge'},
            {'count': 20, 'current_A': 0.0, 'label': 'toy_rest', 'phase': 'toy_rest'}]
        manifest = cs.make_source_manifest(plan, contract_sha, 'cell_a', fixture_events=events, fixture_seed=1701)
        (out / 'manifest.json').write_bytes(cs.canonical_bytes(manifest) + b'\n')
        check(len(cs.build_events(plan, 'cell_a')) == 106, 'A_current_protocol106_events_no_generation')
        check(len(cs.build_events(plan, 'cell_b')) == 193, 'B_current_protocol193_events_no_generation')
        check(cs.OBSERVATION.size == cs.SCALAR_TRUTH.size == 32, 'canonical_scalar_record_sizes')
        check(cs.JOURNAL_RECORD_BYTES == 208 and cs.JOURNAL_HEADER_BYTES == 72, 'canonical_journal_record_sizes')
        source = cs.StatefulSource(manifest)
        initial = source.snapshot()
        initial_query = source.truth_query()
        check(initial_query['prediction_observed'] is False and initial_query['clean_voltage_V'] is None,
              'initial_truth_has_no_observed_voltage')
        check(len(initial_query['mean']) == 16 and initial_query['SOC'] == 0.8 and initial_query['Q_Ah'] == 0.06,
              'initial_truth_coordinates_order_and_units')
        check(source.snapshot() == initial, 'truth_query_has_no_state_or_rng_side_effect')

        observations, truths, snapshots = [], [], [initial]
        for index in range(72):
            observation, truth = source.next_record()
            observations.append(observation)
            truths.append(truth)
            snapshots.append(source.snapshot())
            ni, q, z, clean = cs.SCALAR_TRUTH.unpack(truth)
            ii, dt, current, measured = cs.OBSERVATION.unpack(observation)
            if not (ii == index and ni == index + 1 and dt == cs.DT and q == 0.06
                    and z == source.current_state['z'] and clean == source.last_clean_voltage_V
                    and math.isfinite(measured) and current == source.last_current_A):
                raise AssertionError('per_record_index_measurement_truth_accounting')
        checks.append('all72_record_index_measurement_truth_accounting')
        check(cs.TOTAL_NOISE_DRAWS == 72, 'one_scalar_noise_draw_per_interval')
        before_query = source.snapshot()
        source.truth_query()
        source.snapshot()
        check(source.snapshot() == before_query and cs.TOTAL_NOISE_DRAWS == 72,
              'queries_and_snapshots_do_not_consume_noise')

        p = source.parameters
        enter = initial['payload']['current_state']
        state35 = snapshots[35]['payload']['current_state']
        expected_v = [old * math.exp(-1.0/tau) + R*0.03*(-math.expm1(-1.0/tau))
                      for old, R, tau in zip(enter['v'], p['R'], p['tau'])]
        expected_z = enter['z'] - 0.03/(3600.0*p['Q_Ah'])
        expected_h = enter['h'] * math.exp(-p['gamma_plus']*.03/3600.0) + (-math.expm1(-p['gamma_plus']*.03/3600.0))
        check(max(abs(a-b) for a,b in zip(expected_v, state35['v'])) < 2e-15,
              'independent_expm1_RC_dwell_closed_form')
        check(abs(expected_z-state35['z']) < 2e-15 and abs(expected_h-state35['h']) < 2e-15,
              'independent_SOC_hysteresis_dwell_closed_form')
        state52 = snapshots[52]['payload']['current_state']
        charge_duration = 17*cs.DT
        e = math.exp(-p['gamma_minus']*.045*charge_duration/3600.0)
        check(abs(state52['h'] - (state35['h']*e + math.expm1(-p['gamma_minus']*.045*charge_duration/3600.0))) < 2e-15,
              'reversal_uses_carried_state_and_negative_gamma')
        check(snapshots[52]['payload']['current_state']['h'] == snapshots[72]['payload']['current_state']['h'],
              'rest_preserves_hysteresis_exactly')
        qpos = Fraction(30, 1000) / 3600
        qneg = Fraction(45, 1000) * Fraction(17, 35) / 3600
        check(abs(source.charge['positive_Ah'] - float(qpos)) < 1e-20
              and abs(source.charge['negative_magnitude_Ah'] - float(qneg)) < 1e-20
              and abs(source.charge['signed_Ah'] - float(qpos-qneg)) < 1e-20,
              'independent_rational_positive_negative_signed_charge')
        check(abs(source.current_state['z'] - (p['z0']-float(qpos-qneg)/p['Q_Ah'])) < 2e-15,
              'full_toy_SOC_matches_integrated_charge')

        for restore_index in (13,35):
            restored = cs.StatefulSource.from_state(snapshots[restore_index], expected_manifest=manifest)
            check(restored.snapshot() == snapshots[restore_index], 'snapshot_roundtrip_' + str(restore_index))
            for index in range(restore_index,72):
                observation, truth = restored.next_record()
                if observation != observations[index] or truth != truths[index]:
                    raise AssertionError('restored_source_future_bytes_' + str(restore_index))
            checks.append('restored_source_future_bytes_' + str(restore_index))
            check(restored.snapshot() == snapshots[72], 'full_final_state_rng_charge_chain_parity_' + str(restore_index))

        query_indices = [0,1,13,35,36,52,53,72]
        checkpoint_indices = [0,13,35,52,72]
        receipts = []
        for chunk in (35,7):
            src = cs.StatefulSource(manifest)
            receipts.append(cs.generate_files(src,72,out/('chunk_'+str(chunk)),
                            query_indices=query_indices,checkpoint_indices=checkpoint_indices,chunk_size=chunk))
        for filename in ('observations.bin','truth.bin','truth.jsonl','source_states.bin','source_final.json'):
            check((out/'chunk_35'/filename).read_bytes() == (out/'chunk_7'/filename).read_bytes(),
                  'chunk_independent_' + filename)
        check((out/'chunk_35'/'observations.bin').read_bytes() == b''.join(observations)
              and (out/'chunk_35'/'truth.bin').read_bytes() == b''.join(truths),
              'file_records_match_direct_chronological_source')
        check(receipts[0]['source_state_journal_bytes'] == 72+73*208
              and receipts[0]['full_query_records'] == len(query_indices),
              'file_journal_query_accounting')
        before_journal = cs.TOTAL_NOISE_DRAWS
        for index in range(73):
            got = cs.snapshot_at(out/'chunk_35'/'source_states.bin',index,manifest)
            if got != snapshots[index]:
                raise AssertionError('journal_exact_snapshot_' + str(index))
        checks.append('all73_journal_snapshots_reconstruct_exactly')
        check(cs.TOTAL_NOISE_DRAWS == before_journal, 'journal_lookup_has_zero_RNG_draws')
        check(cs.snapshot_at(out/'chunk_35'/'source_states.bin',35,manifest,
                             expected_sha256=receipts[0]['source_state_journal_sha256']) == snapshots[35],
              'journal_whole_sha_and_per_record_crc_binding')

        damaged = copy.deepcopy(snapshots[13])
        damaged['payload']['current_state']['z'] += 1e-4
        rejects(lambda:cs.StatefulSource.from_state(damaged,expected_manifest=manifest),
                'corrupt_snapshot_rejected_by_checksum')
        damaged['sha256']=hashlib.sha256(cs.canonical_bytes(damaged['payload'])).hexdigest()
        rejects(lambda:cs.StatefulSource.from_state(damaged,expected_manifest=manifest),
                'checksum_valid_but_inconsistent_physical_state_rejected')
        damaged = copy.deepcopy(snapshots[35])
        damaged['payload']['within_event_count'] = 1
        damaged['sha256']=hashlib.sha256(cs.canonical_bytes(damaged['payload'])).hexdigest()
        rejects(lambda:cs.StatefulSource.from_state(damaged,expected_manifest=manifest),
                'event_index_mismatch_rejected_without_history_replay')
        different = copy.deepcopy(manifest); different['seed'] = 1702
        rejects(lambda:cs.StatefulSource.from_state(snapshots[13],expected_manifest=different),
                'source_manifest_mismatch_rejected')
        journal = bytearray((out/'chunk_35'/'source_states.bin').read_bytes())
        journal[cs.JOURNAL_HEADER_BYTES + 13*cs.JOURNAL_RECORD_BYTES + 48] ^= 1
        (out/'damaged_journal.bin').write_bytes(journal)
        rejects(lambda:cs.snapshot_at(out/'damaged_journal.bin',13,manifest),
                'individual_journal_crc_catches_corruption')
        check(source.snapshot()==snapshots[72], 'failed_restore_does_not_mutate_live_source')

        primary_manifest = cs.make_source_manifest(plan,contract_sha,'cell_a')
        protected = cs.StatefulSource(primary_manifest)
        protected_before = protected.snapshot()
        draws_before = cs.TOTAL_NOISE_DRAWS
        rejects(protected.next_record,'primary_noise_guard_before_frozen_receipt')
        check(protected.snapshot()==protected_before and cs.TOTAL_NOISE_DRAWS==draws_before,
              'primary_guard_is_atomic_and_consumes_zero_noise')
        rejects(lambda:cs.make_source_manifest(plan,contract_sha,'cell_a',fixture_events=events,fixture_seed=2026102601),
                'fixture_cannot_reuse_primary_seed')

        (out/'child_queries.json').write_text(json.dumps([13,14,20])+'\n')
        (out/'child_checkpoints.json').write_text(json.dumps([13,20])+'\n')
        command = [sys.executable,str(ROOT/'tools/continuous_source.py'),
                   '--manifest',str(out/'manifest.json'),'--output-dir',str(out/'fresh_process'),
                   '--end','20','--restore',str(out/'chunk_35'/'source-cp-13.json'),
                   '--query-indices',str(out/'child_queries.json'),
                   '--checkpoint-indices',str(out/'child_checkpoints.json')]
        proc = subprocess.run(command,capture_output=True,text=True,timeout=20,check=False)
        (out/'fresh_process.stdout.txt').write_text(proc.stdout)
        (out/'fresh_process.stderr.txt').write_text(proc.stderr)
        check(proc.returncode==0,'fresh_process_restore_exit')
        receipt = json.loads(proc.stdout)
        child_draws = receipt['noise_draws_generated']
        check(child_draws==7 and (out/'fresh_process'/'observations.bin').read_bytes()==b''.join(observations[13:20])
              and (out/'fresh_process'/'truth.bin').read_bytes()==b''.join(truths[13:20]),
              'fresh_process_future_observation_truth_bytes')
        check(json.loads((out/'fresh_process'/'source_final.json').read_text())==snapshots[20],
              'fresh_process_full_snapshot_parity')
        check(cs.TOTAL_NOISE_DRAWS+child_draws==319<=512, 'bounded_toy_draw_budget319')
        result = {'schema':'mumble_continuous_source_fixture_receipt_v1','status':'passed',
                  'checks_passed':len(checks),'checks':checks,
                  'source_sha256':cs.sha256_file(ROOT/'tools/continuous_source.py'),
                  'test_sha256':cs.sha256_file(Path(__file__)),
                  'contract_sha256':contract_sha,'environment':cs.runtime_identity(),
                  'fixture_seed':1701,'fixture_samples':72,
                  'toy_noise_draws_process':cs.TOTAL_NOISE_DRAWS,'toy_noise_draws_child':child_draws,
                  'toy_noise_draws_total':cs.TOTAL_NOISE_DRAWS+child_draws,
                  'primary_noise_draws':0,'learner_deliveries':0,'primary_runs':0,
                  'child_command':command,'wall_time_s':time.monotonic()-started,
                  'journal_record_bytes':cs.JOURNAL_RECORD_BYTES,'journal_header_bytes':cs.JOURNAL_HEADER_BYTES,
                  'source_manifest_id':cs.source_id(manifest)}
    except BaseException as exc:
        result = {'schema':'mumble_continuous_source_fixture_receipt_v1','status':'failed',
                  'error':type(exc).__name__+': '+str(exc),'traceback':traceback.format_exc(),
                  'checks_passed':len(checks),'checks':checks,
                  'toy_noise_draws_process':cs.TOTAL_NOISE_DRAWS,'toy_noise_draws_child':child_draws,
                  'primary_noise_draws':0,'learner_deliveries':0,'primary_runs':0,
                  'wall_time_s':time.monotonic()-started}
        (out/'receipt.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))
        raise
    (out/'receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['status','checks_passed','toy_noise_draws_total','primary_noise_draws','learner_deliveries','wall_time_s']},indent=2))


def run_signal_safety(out):
    """Only G1 signal/fault qualification; do not rerun the original suite."""
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    checks, cases = [], []
    initial_counter = cs.TOTAL_NOISE_DRAWS
    known_draws_outside_counter = 0
    previous_handlers = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
    original_journal = cs._journal_record

    def check(condition, name):
        if not condition:
            raise AssertionError(name)
        checks.append(name)

    def escaped_signal(signum, _frame):
        # Preserve a failed qualification instead of killing its receipt writer
        # if the generator ever fails to install/retain its deferring handler.
        raise AssertionError('Signal escaped source transaction guard: ' + str(signum))

    class DrawHook:
        def __init__(self, real, signum=None, fault=False):
            self.real, self.signum, self.fault = real, signum, fault
            self.actual_draws = 0

        @property
        def bit_generator(self):
            return self.real.bit_generator

        def __getstate__(self):
            return self.real.__getstate__()

        def normal(self, *args, **kwargs):
            value = self.real.normal(*args, **kwargs)
            self.actual_draws += 1
            if self.fault:
                raise MemoryError('Injected unavoidable fault after RNG state advanced')
            if self.actual_draws == 1:
                os.kill(os.getpid(), self.signum)
            return value

    try:
        for signum in previous_handlers:
            signal.signal(signum, escaped_signal)
        plan_path = ROOT / 'plans/continuous_learning_validation_001.json'
        plan = json.loads(plan_path.read_text())
        manifest = cs.make_source_manifest(plan, cs.sha256_file(plan_path), 'cell_a',
            fixture_events=[{'count': 1, 'current_A': .03, 'label': 'toy_discharge'},
                            {'count': 2, 'current_A': -.045, 'label': 'toy_charge'}],
            fixture_seed=1703)
        (out / 'manifest.json').write_bytes(cs.canonical_bytes(manifest) + b'\n')
        baseline = cs.generate_files(cs.StatefulSource(manifest), 3, out / 'baseline',
                                    query_indices=[0, 1, 3], checkpoint_indices=[0, 1, 3])
        check(baseline['records'] == baseline['noise_draws_generated'] == 3,
              'uninterrupted_new_guard_path_exact_three_draws')
        baseline_snapshots = {n: json.loads((out / 'baseline' / ('source-cp-' + str(n) + '.json')).read_text())
                              for n in (0, 1, 3)}
        specs = [('sigint_after_draw', signal.SIGINT, 'draw', 1),
                 ('sigterm_after_draw', signal.SIGTERM, 'draw', 1),
                 ('sigint_during_journal', signal.SIGINT, 'journal', 1),
                 ('sigterm_during_initial_journal', signal.SIGTERM, 'journal', 0)]
        for name, signum, location, stop_index in specs:
            source = cs.StatefulSource(manifest)
            sent = [False]
            if location == 'draw':
                source.rng = DrawHook(source.rng, signum=signum)
            else:
                def hooked_journal(active_source):
                    if active_source.next_index == stop_index and not sent[0]:
                        sent[0] = True
                        os.kill(os.getpid(), signum)
                    return original_journal(active_source)
                cs._journal_record = hooked_journal
            case_started = time.monotonic()
            case_dir = out / name
            try:
                cs.generate_files(source, 3, case_dir, query_indices=[0, 1, 3],
                                  checkpoint_indices=[0, 1, 3])
            except cs.SourceStopped as exc:
                check(exc.signum == signum, name + ':same_signal_reported')
            else:
                raise AssertionError(name + ':signal_not_stopped')
            finally:
                cs._journal_record = original_journal
            failure = json.loads((case_dir / 'failure.json').read_text())
            check(failure['cooperative_stop'] and failure['signal_number'] == signum,
                  name + ':cooperative_failure_capture')
            check(failure['next_index'] == source.next_index == stop_index
                  and failure['noise_draws_generated'] == stop_index
                  and failure['noise_draws_exact'] and not failure['source_step_in_progress'],
                  name + ':complete_source_and_exact_draw_count')
            check(failure['outputs_flushed_through_index'] == stop_index,
                  name + ':all_binary_and_query_outputs_flushed')
            check(failure['source_snapshot'] == source.snapshot() == baseline_snapshots[stop_index],
                  name + ':full_snapshot_exact_reference_parity')
            check(cs.StatefulSource.from_state(failure['source_snapshot'], expected_manifest=manifest).snapshot()
                  == baseline_snapshots[stop_index], name + ':failure_snapshot_restores_without_draws')
            for filename, size in [('observations.bin', cs.OBSERVATION.size), ('truth.bin', cs.SCALAR_TRUTH.size)]:
                check((case_dir / filename).read_bytes()
                      == (out / 'baseline' / filename).read_bytes()[:stop_index * size],
                      name + ':committed_' + filename)
            journal_end = cs.JOURNAL_HEADER_BYTES + (stop_index + 1) * cs.JOURNAL_RECORD_BYTES
            check((case_dir / 'source_states.bin').read_bytes()
                  == (out / 'baseline' / 'source_states.bin').read_bytes()[:journal_end],
                  name + ':committed_journal_prefix')
            check(cs.snapshot_at(case_dir / 'source_states.bin', stop_index, manifest)
                  == baseline_snapshots[stop_index], name + ':journal_restores_exact_boundary')
            lines = (case_dir / 'truth.jsonl').read_bytes().splitlines(keepends=True)
            check(lines == (out / 'baseline' / 'truth.jsonl').read_bytes().splitlines(keepends=True)[:stop_index + 1],
                  name + ':scheduled_full_truth_is_complete')
            check(json.loads((case_dir / ('source-cp-' + str(stop_index) + '.json')).read_text())
                  == baseline_snapshots[stop_index], name + ':requested_checkpoint_written_before_stop')
            check(not (case_dir / 'receipt.json').exists(), name + ':no_false_complete_receipt')
            check(all(signal.getsignal(s) is escaped_signal for s in previous_handlers),
                  name + ':previous_handlers_restored')
            cases.append({'case': name, 'signal': signal.Signals(signum).name, 'injection': location,
                          'completed_next_index': stop_index, 'toy_noise_draws': stop_index,
                          'wall_time_s': time.monotonic() - case_started})

        # A fault *inside* a normal call after the RNG changed cannot honestly be
        # counted from next_index or TOTAL_NOISE_DRAWS. Exercise explicit unknown.
        source = cs.StatefulSource(manifest)
        hook = DrawHook(source.rng, fault=True)
        source.rng = hook
        fault_dir = out / 'unavoidable_rng_fault'
        try:
            cs.generate_files(source, 3, fault_dir, query_indices=[0, 1, 3])
        except MemoryError:
            known_draws_outside_counter += hook.actual_draws
        else:
            raise AssertionError('Injected RNG fault unexpectedly returned')
        failure = json.loads((fault_dir / 'failure.json').read_text())
        check(hook.actual_draws == 1 and failure['noise_draws_generated'] is None
              and not failure['noise_draws_exact'] and failure['source_step_in_progress'],
              'unavoidable_rng_fault_reports_unknown_not_zero')
        check(failure['noise_draws_generated_lower_bound'] == 0
              and failure['noise_draws_generated_upper_bound'] == 1,
              'unavoidable_rng_fault_has_honest_zero_to_one_bounds')
        check(failure['source_snapshot'] == baseline_snapshots[0]
              and cs.StatefulSource.from_state(failure['source_snapshot'], expected_manifest=manifest).snapshot()
              == baseline_snapshots[0], 'unavoidable_fault_preserves_last_complete_source_not_advanced_rng')
        check(failure['next_index'] == 0 and (fault_dir / 'observations.bin').stat().st_size == 0
              and (fault_dir / 'truth.bin').stat().st_size == 0,
              'unavoidable_fault_claims_no_completed_record')
        counted = cs.TOTAL_NOISE_DRAWS - initial_counter
        check(counted + known_draws_outside_counter == 7, 'targeted_G1_exact_seven_actual_toy_draws')
        result = {'schema': 'mumble_continuous_source_signal_fixture_receipt_v1', 'status': 'passed',
                  'checks_passed': len(checks), 'checks': checks, 'cases': cases,
                  'source_sha256': cs.sha256_file(ROOT / 'tools/continuous_source.py'),
                  'test_sha256': cs.sha256_file(Path(__file__)),
                  'contract_sha256': cs.sha256_file(plan_path), 'fixture_seed': 1703,
                  'toy_noise_draws_process_counter': counted,
                  'toy_noise_draws_known_outside_counter': known_draws_outside_counter,
                  'toy_noise_draws_total': counted + known_draws_outside_counter,
                  'prior_qualification_toy_draws': 319, 'cumulative_generator_qualification_toy_draws': 326,
                  'primary_noise_draws': 0, 'learner_deliveries': 0, 'primary_runs': 0,
                  'wall_time_s': time.monotonic() - started,
                  'scope': 'Targeted G1 cooperative-signal and unavoidable-fault checks only; original319-draw suite not rerun.'}
    except BaseException as exc:
        result = {'schema': 'mumble_continuous_source_signal_fixture_receipt_v1', 'status': 'failed',
                  'error': type(exc).__name__ + ': ' + str(exc), 'traceback': traceback.format_exc(),
                  'checks_passed': len(checks), 'checks': checks, 'cases': cases,
                  'toy_noise_draws_process_counter': cs.TOTAL_NOISE_DRAWS - initial_counter,
                  'toy_noise_draws_known_outside_counter': known_draws_outside_counter,
                  'primary_noise_draws': 0, 'learner_deliveries': 0, 'primary_runs': 0,
                  'wall_time_s': time.monotonic() - started}
        (out / 'receipt.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2))
        raise
    finally:
        cs._journal_record = original_journal
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
    (out / 'receipt.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ['status', 'checks_passed', 'toy_noise_draws_total',
                                           'primary_noise_draws', 'learner_deliveries', 'wall_time_s']}, indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--signal-safety-only',action='store_true',
                        help='Run only the targeted G1 signal/fault fixtures; never the original suite.')
    args=parser.parse_args()
    (run_signal_safety if args.signal_safety_only else run)(args.output_dir.resolve())
