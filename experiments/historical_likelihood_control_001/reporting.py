#!/usr/bin/env python3
"""Reduce the closed historical control; no model, optimizer, or learner calls.

The original endpoint truth is decoded only after the three completed fit
receipts and all their recorded artifacts/inputs have passed identity checks.
The free undamped16-dimensional Gram is solved without clipping or a cutoff.
"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import struct
import sys
import time

sys.dont_write_bytecode = True
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import run_conditional_belief_probe as utilities
import run_historical_likelihood_control as driver

require = utilities.require
N = 252000
FIT_IDS = ('free', 'fixed_recursive_Q', 'fixed_recursive_SOC')
TRUTH_RECORD = struct.Struct('<Qddd')
TRUTH_MEMBER = ('experiments/continuous_learning_validation_001/implementation/'
                'primary/B_continuous/source/truth.bin')
NUMBER = utilities.number


def read_json(path):
    require(path.stat().st_size <= 2097152, 'Unexpectedly large result JSON: ' + str(path))
    value = utilities.strict_json(path.read_bytes())
    driver.finite_tree(value)
    return value


def bind(records, path, expected=None, label=None):
    return utilities.bind_file(records, path, expected, label)


def save_new(path, value):
    return utilities.write_new_json(path, value, 2097152)


def closed_fit_inputs(root, attempt, records):
    receipt_path = attempt / 'receipt.json'
    require(receipt_path.is_file(), 'Inference receipt has not closed; no reduction or truth access')
    bind(records, receipt_path, label='closed_inference_receipt')
    receipt = read_json(receipt_path)
    require(receipt['schema'] == 'mumble_historical_likelihood_control_execution_v1'
            and receipt['status'] == 'completed' and not receipt['errors'],
            'Historical inference did not complete successfully')
    require(receipt['fit_invocations_attempted'] == receipt['observed_children_launched'] == 3
            and receipt['launch_state_fully_recorded'] is True
            and receipt['all_bound_inputs_unchanged'] is True,
            'Three complete, unchanged-input fit receipts are required')
    require([row['fit_id'] for row in receipt['fits']] == list(FIT_IDS), 'Unexpected closed fit set')
    require(receipt['truth_in_inference'] is False and receipt['automatic_retries'] == 0,
            'Unexpected inference evidence or retry policy')
    for row in receipt['fits']:
        worker = row['worker']
        require(row['supervisor_invocation_started'] is True and row['validated_output'] is True
                and worker['child_launched'] is True and worker['exit_code'] == 0
                and not worker['resource_violations'], 'A fit is incomplete or resource-invalid')
    require(sum(path.stat().st_size for path in attempt.rglob('*') if path.is_file())
            == receipt['closed_output_bytes'], 'Closed attempt byte count mismatch')
    for item in receipt['artifacts']:
        bind(records, utilities.beneath(attempt, item['path']), item,
             'closed_attempt/' + item['path'])
    after = {row['path']: row for row in receipt['post_execution_identities']}
    for item in receipt['pre_execution_identities']:
        require(item['path'] in after and after[item['path']]['unchanged'] is True
                and all(after[item['path']][key] == item[key] for key in ('bytes', 'sha256')),
                'Inference before/after identity ledger mismatch')
        bind(records, Path(item['path']), item, 'inference_input/' + item['label'])
    plan_path = root / driver.PLAN
    plan = read_json(plan_path)
    require(utilities.digest(plan_path)['sha256'] == receipt['plan_sha256'], 'Plan identity mismatch')
    require(plan['inputs']['prefix_records'] == N, 'Unexpected reporting endpoint')
    require(receipt['source_revision'] == read_json(Path(receipt['executable_receipt']))['source_revision'],
            'Source revision differs from executable receipt')
    saved = read_json(attempt / 'recursive_targets.json')
    require(saved['next_index'] == N and saved['selector'] == 'aggregate', 'Unexpected frozen targets')
    raws, fits = {}, []
    for fit_id in FIT_IDS:
        raw = read_json(attempt / fit_id / 'stdout.json')
        parsed = driver.validate_fit(raw, fit_id, saved)
        stored = next(row['summary'] for row in receipt['fits'] if row['fit_id'] == fit_id)
        require(parsed == stored, 'Raw fit differs from closed driver reduction: ' + fit_id)
        resources = read_json(attempt / fit_id / 'resources.json')
        require(resources == next(row['worker'] for row in receipt['fits'] if row['fit_id'] == fit_id),
                'Per-fit resource receipt differs from closed receipt')
        raws[fit_id] = raw
        fits.append({'id': fit_id, 'objective': raw['objective'],
                     'objective_full': raw['objective_full'],
                     'delta_NLL_from_free': raw['objective_full'] - raws['free']['objective_full'],
                     'capacity_Ah': parsed['capacity_Ah'], 'current_soc': parsed['endpoint_SOC'],
                     'optimizer_status': raw['status'], 'termination_reason': raw['termination_reason'],
                     'converged_starts': raw['converged_starts'], 'starts': raw['starts'],
                     'iterations': raw['iterations'], 'evaluations': raw['evaluations'],
                     'projected_gradient': raw['projected_gradient'], 'max_inner_kkt': raw['max_inner_kkt'],
                     'voltage_rmse_V': raw['voltage_rmse'], 'charge_Ah': raw['charge_Ah'],
                     'theta': raw['theta'], 'alpha': raw['alpha'],
                     'active_bound_diagnostics': bound_diagnostics(raw),
                     'resources': resources,
                     'unrestricted_precision_eligible_chart': fit_id == 'free',
                     'legacy_assessment': raw['assessment'],
                     'legacy_assessment_used_for_new_SD': False})
    return receipt, plan, saved, raws, fits


def bound_diagnostics(raw):
    names = ['log_tau1', 'log_tau2', 'log_tau3', 'log_gamma_plus', 'log_gamma_minus', 'z0', 'log_Q',
             'R0', 'R1', 'R2', 'R3', 'H', 'v10', 'v20', 'v30', 'u0']
    lower = [math.log(.015), math.log(.15), math.log(1.5), math.log(5), math.log(5), .2,
             math.log(.03), 0, 0, 0, 0, 0, -.08, -.08, -.08, -.1]
    upper = [math.log(.15), math.log(1.5), math.log(30), math.log(1200), math.log(1200), .95,
             math.log(.1), 1, 1, 1, 1, .1, .08, .08, .08, .1]
    values = raw['theta'] + raw['alpha']
    rows = [{'coordinate': name, 'value': value, 'lower': lo, 'upper': hi,
             'lower_margin': value - lo, 'upper_margin': hi - value,
             'exact_lower_contact': value == lo, 'exact_upper_contact': value == hi}
            for name, value, lo, hi in zip(names, values, lower, upper)]
    return {'C_reported_active_linear_constraints': raw['active_linear_constraints'],
            'C_reported_active_outer_bounds': raw['active_outer_bounds'],
            'coordinate_margins': rows,
            'hysteresis_joint_slacks': {'H_minus_u0': raw['alpha'][4] - raw['alpha'][8],
                                        'H_plus_u0': raw['alpha'][4] + raw['alpha'][8]},
            'interpretation': 'Raw solver active counts and exact margins. No new active-bound threshold; unrestricted Gaussian intervals require additional caution at active constraints.'}


def local_precision(raw):
    """Use all16 undamped scaled coordinates; no regularization or pseudoinverse."""
    require(raw['case_id'].endswith('/free') and not raw['has_initial']
            and raw['fixed_mask'] == 0 and raw['fixed_alpha_mask'] == 0
            and raw['has_current_soc'] is False, 'Only the free chart may supply unrestricted precision')
    gram = np.asarray(raw['joint_normal'], dtype=np.float64).reshape(16, 16)
    scales = np.asarray(raw['coordinate_scales'], dtype=np.float64)
    require(np.isfinite(gram).all() and np.isfinite(scales).all() and (scales > 0).all(),
            'Invalid full likelihood Gram or scales')
    asymmetry = float(np.max(np.abs(gram - gram.T)))
    result = {'status': 'unavailable', 'method': 'Cholesky solve of the full undamped16x16 likelihood Gram',
              'matrix_chart': 'scaled theta followed by scaled alpha',
              'sigma_V': raw['sigma_V'], 'sigma_already_in_Gram': True,
              'extra_sigma_multiplier_applied_to_covariance': False,
              'matrix_modified': False, 'eigenvalue_clipping': False,
              'pseudoinverse_or_rank_cutoff': False, 'max_absolute_asymmetry': asymmetry,
              'coordinate_scales': raw['coordinate_scales'], 'eigenvalues': None,
              'condition_number_2_from_eigenvalues': None,
              'logQ_sd': None, 'capacity_sd_Ah': None, 'SOC_sd': None,
              'local_two_SD_intervals': None,
              'qualification': 'Local unconstrained Gauss-Newton precision only; no posterior coverage, global identifiability, confidence calibration, or active-constraint correction.'}
    if asymmetry != 0:
        result['failure'] = 'Raw full Gram is not exactly symmetric; no symmetrization applied'
        return result
    try:
        eigenvalues = np.linalg.eigvalsh(gram)
        require(np.isfinite(eigenvalues).all(), 'Nonfinite full Gram spectrum')
        result['eigenvalues'] = eigenvalues.tolist()
        result['positive_eigenvalues_without_cutoff'] = int(np.count_nonzero(eigenvalues > 0))
        if eigenvalues[0] <= 0:
            result['failure'] = 'Nonpositive computed eigenvalue; no clipping or pseudoinverse used'
            return result
        condition = float(eigenvalues[-1] / eigenvalues[0])
        result['condition_number_2_from_eigenvalues'] = condition
        factor = np.linalg.cholesky(gram)
        reconstructed = factor @ factor.T
        norm_matrix = float(np.linalg.norm(gram, ord=np.inf))
        result['Cholesky_diagonal'] = np.diag(factor).tolist()
        result['Cholesky_reconstruction_relative_inf'] = float(
            np.linalg.norm(reconstructed - gram, ord=np.inf) / norm_matrix)
        q = math.exp(raw['theta'][6])
        soc = raw['theta'][5] - raw['charge_Ah'] / q
        gradients = {'logQ': np.zeros(16), 'Q_Ah': np.zeros(16), 'SOC': np.zeros(16)}
        gradients['logQ'][6] = scales[6]
        gradients['Q_Ah'][6] = q * scales[6]
        gradients['SOC'][5] = scales[5]
        gradients['SOC'][6] = raw['charge_Ah'] / q * scales[6]
        solves = {}
        for name, gradient in gradients.items():
            whitened = np.linalg.solve(factor, gradient)
            solution = np.linalg.solve(factor.T, whitened)
            variance = float(whitened @ whitened)
            residual = gram @ solution - gradient
            residual_inf = float(np.linalg.norm(residual, ord=np.inf))
            relative_residual_2 = float(np.linalg.norm(residual) / np.linalg.norm(gradient))
            denominator = norm_matrix * float(np.linalg.norm(solution, ord=np.inf)) + float(np.linalg.norm(gradient, ord=np.inf))
            require(math.isfinite(variance) and variance > 0 and np.isfinite(solution).all(),
                    'Nonfinite or nonpositive target variance from Cholesky solve')
            solves[name] = {'scaled_gradient': gradient.tolist(),
                            'variance_from_squared_whitened_gradient': variance,
                            'variance_from_gradient_dot_solution': float(gradient @ solution),
                            'SD': math.sqrt(variance), 'solve_residual_inf': residual_inf,
                            'solve_relative_residual_2': relative_residual_2,
                            'normwise_backward_error_inf': residual_inf / denominator,
                            'condition_times_relative_residual_indicator': condition * relative_residual_2,
                            'conditioning_note': 'Floating-point estimates of conditioning/residuals, not rigorous error bounds.'}
        result.update(status='available_local_unconstrained', target_solves=solves,
                      logQ_sd=solves['logQ']['SD'], capacity_sd_Ah=solves['Q_Ah']['SD'],
                      SOC_sd=solves['SOC']['SD'])
        result['Q_SD_relation_error_Ah'] = result['capacity_sd_Ah'] - q * result['logQ_sd']
        result['local_two_SD_intervals'] = {
            'Q_Ah': [math.exp(raw['theta'][6] - 2 * result['logQ_sd']),
                     math.exp(raw['theta'][6] + 2 * result['logQ_sd'])],
            'SOC': [soc - 2 * result['SOC_sd'], soc + 2 * result['SOC_sd']]}
        result['interval_semantics'] = 'Existing two-SD display convention, applied to local full-history curvature. Not a calibrated confidence set or a hard-support interval.'
    except (np.linalg.LinAlgError, utilities.ProbeError, ArithmeticError) as error:
        result['status'] = 'unavailable'
        result['failure'] = str(error)
        result['logQ_sd'] = result['capacity_sd_Ah'] = result['SOC_sd'] = None
        result['local_two_SD_intervals'] = None
    return result


def original_query(root, receipt, plan, saved, records):
    inputs = plan['inputs']
    metadata_path = root / inputs['witness_restoration_record']
    metadata_id = bind(records, metadata_path, label='verified_restoration_metadata')
    driver.commit_identity(root, plan['base_revision'], inputs['witness_restoration_record'], metadata_id)
    driver.commit_identity(root, receipt['source_revision'], inputs['witness_restoration_record'], metadata_id)
    metadata = read_json(metadata_path)
    expected = driver.archived_witness_identity(inputs, metadata)
    path = utilities.beneath(Path(receipt['query_evidence_root']).resolve(), inputs['witness_path'])
    bind(records, path, expected, 'original_queries')
    chosen, matching = None, 0
    with path.open('rb') as stream:
        for line_number, line in enumerate(stream, 1):
            query = utilities.strict_json(line)
            if query.get('next_index') != N:
                continue
            matching += 1
            require(hashlib.sha256(line).hexdigest() == saved['witness_line_sha256']
                    and line_number == saved['witness_line_number'], 'Original endpoint query differs from inference target witness')
            require(query['event'] == 'query' and query['schema'] == 'mumble_continuous_query_v1',
                    'Unexpected original endpoint query schema')
            chosen = query
    require(matching == 1, 'Expected exactly one original endpoint query')
    require(chosen['aggregate']['capacity_Ah'] == saved['capacity_Ah']
            and chosen['aggregate']['current_soc'] == saved['current_soc'],
            'Online target differs from the target used by constrained inference')
    entities = []
    for label, entity in [('aggregate', chosen['aggregate'])] + [
            ('component' + str(index), row) for index, row in enumerate(chosen['components'])]:
        require(entity['next_index'] == N and entity['point_available'] == 1
                and entity['capacity_available'] == 1 and entity['local_ranges_available'] == 1,
                'Unavailable original target/interval at the exact endpoint')
        q = NUMBER(entity['capacity_Ah'], label + '.capacity')
        z = NUMBER(entity['current_soc'], label + '.SOC')
        sdq = NUMBER(entity['coordinate_sd'][5], label + '.logQ_SD')
        sdz = NUMBER(entity['coordinate_sd'][11], label + '.SOC_SD')
        require(q > 0 and sdq >= 0 and sdz >= 0, 'Invalid online local moment')
        intervals = {'Q_Ah': [NUMBER(entity[key], key) for key in ('capacity_local_lower_Ah', 'capacity_local_upper_Ah')],
                     'SOC': [NUMBER(entity[key], key) for key in ('soc_local_lower', 'soc_local_upper')]}
        require(intervals['Q_Ah'][0] <= q <= intervals['Q_Ah'][1]
                and intervals['SOC'][0] <= z <= intervals['SOC'][1],
                'Saved local interval excludes its matching point')
        entities.append({'entity': label, 'capacity_Ah': q, 'current_soc': z,
                         'logQ_sd': sdq, 'capacity_sd_Ah_delta_method': q * sdq,
                         'SOC_sd': sdz, 'local_two_SD_intervals': intervals,
                         'capacity_status': entity['capacity_status'], 'soc_status': entity['soc_status'],
                         'semantics': 'Saved prior-conditioned local Gaussian or mixture-moment diagnostics; coverage unvalidated'})
    return {'query_path': str(path), 'next_index': N,
            'line_number': saved['witness_line_number'], 'line_sha256': saved['witness_line_sha256'],
            'log_weights': chosen['log_weights'], 'all_component_hull': chosen['all_component_hull'],
            'entities': entities}, metadata


def endpoint_truth(evidence_root, metadata, records):
    matching = [row for row in metadata['selected_members_SHA256_and_Git_blob_verified']
                if row['path'] == TRUTH_MEMBER]
    require(len(matching) == 1, 'Missing unique original truth member identity')
    member = matching[0]
    require(member['bytes'] == 504000 * TRUTH_RECORD.size, 'Unexpected original truth extent')
    path = utilities.beneath(evidence_root, TRUTH_MEMBER)
    bind(records, path, member, 'post_inference_endpoint_truth_source')
    # No truth numerical field is decoded before the whole-file digest succeeds.
    with path.open('rb') as stream:
        stream.seek((N - 1) * TRUTH_RECORD.size)
        record = stream.read(TRUTH_RECORD.size)
    require(len(record) == TRUTH_RECORD.size, 'Truncated endpoint truth record')
    index, q, soc, clean_voltage = TRUTH_RECORD.unpack(record)
    require(index == N and all(math.isfinite(value) for value in (q, soc, clean_voltage))
            and q > 0 and 0 <= soc <= 1, 'Invalid endpoint truth index or fields')
    return {'next_index': index, 'capacity_Ah': q, 'SOC': soc,
            'source_path': str(path), 'source_sha256': member['sha256'],
            'source_git_blob_sha1_from_verified_restoration': member['git_blob_sha1'],
            'record_sha256': hashlib.sha256(record).hexdigest(), 'decoded_records': 1,
            'use': 'Post-inference endpoint scoring only; not an initialization, objective or selection input'}


def endpoint_errors(q, soc, truth, intervals=None):
    result = {'capacity_error_Ah': q - truth['capacity_Ah'],
              'capacity_error_percent': 100 * (q / truth['capacity_Ah'] - 1),
              'SOC_error_fraction': soc - truth['SOC'],
              'SOC_error_pp': 100 * (soc - truth['SOC'])}
    if intervals is not None:
        result['truth_in_local_two_SD_Q'] = intervals['Q_Ah'][0] <= truth['capacity_Ah'] <= intervals['Q_Ah'][1]
        result['truth_in_local_two_SD_SOC'] = intervals['SOC'][0] <= truth['SOC'] <= intervals['SOC'][1]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=Path, default=Path(__file__).resolve().parent / 'attempt002')
    parser.add_argument('--truth-evidence-root', type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    attempt = args.attempt.resolve()
    output = Path(__file__).resolve().parent
    require((attempt / 'receipt.json').is_file(), 'Wait for closed inference receipt before executing reporting')
    for name in ('summary.json', 'reporting_receipt.json', 'reporting_reservation.json'):
        require(not (output / name).exists(), 'Reporting is exclusive; existing artifact: ' + name)
    save_new(output / 'reporting_reservation.json',
             {'schema': 'mumble_historical_reporting_reservation_v1', 'attempt': str(attempt),
              'source_sha256': utilities.digest(Path(__file__))['sha256'],
              'new_fit_calls': 0, 'truth_decoded_before_reservation': False})
    records = {}
    errors = []
    truth_records = 0
    phase = 'closed_inference_validation'
    summary = None
    try:
        bind(records, Path(__file__).resolve(), label='reporting_source')
        receipt, plan, saved, raws, fits = closed_fit_inputs(ROOT, attempt, records)
        phase = 'unrestricted_free_curvature'
        precision = local_precision(raws['free'])
        phase = 'exact_original_endpoint_query'
        online, restoration = original_query(ROOT, receipt, plan, saved, records)
        phase = 'post_inference_endpoint_truth'
        truth = endpoint_truth(args.truth_evidence_root.resolve(), restoration, records)
        truth_records = 1
        phase = 'endpoint_comparison'
        for row in fits:
            intervals = precision['local_two_SD_intervals'] if row['id'] == 'free' else None
            row['endpoint_errors'] = endpoint_errors(row['capacity_Ah'], row['current_soc'], truth, intervals)
        for row in online['entities']:
            row['endpoint_errors'] = endpoint_errors(row['capacity_Ah'], row['current_soc'], truth, row['local_two_SD_intervals'])
            row['endpoint_errors']['SOC_error_in_local_SD'] = ((row['current_soc'] - truth['SOC']) / row['SOC_sd']) if row['SOC_sd'] > 0 else None
            row['endpoint_errors']['logQ_error_in_local_SD'] = (math.log(row['capacity_Ah'] / truth['capacity_Ah']) / row['logQ_sd']) if row['logQ_sd'] > 0 else None
        free = fits[0]
        aggregate = online['entities'][0]
        comparison = {'constraint_minus_free_NLL': {row['id']: row['delta_NLL_from_free'] for row in fits[1:]},
                      'constrained_fit_beats_free_baseline': any(row['delta_NLL_from_free'] < 0 for row in fits[1:]),
                      'free_baseline_optimizer_resolved': free['optimizer_status'] == 0,
                      'free_minus_online_capacity_Ah': free['capacity_Ah'] - aggregate['capacity_Ah'],
                      'free_minus_online_SOC_fraction': free['current_soc'] - aggregate['current_soc'],
                      'free_point_in_saved_aggregate_Q_interval': aggregate['local_two_SD_intervals']['Q_Ah'][0] <= free['capacity_Ah'] <= aggregate['local_two_SD_intervals']['Q_Ah'][1],
                      'free_point_in_saved_aggregate_SOC_interval': aggregate['local_two_SD_intervals']['SOC'][0] <= free['current_soc'] <= aggregate['local_two_SD_intervals']['SOC'][1]}
        if precision['status'] == 'available_local_unconstrained':
            comparison['online_aggregate_to_free_SD_ratios'] = {
                'logQ': aggregate['logQ_sd'] / precision['logQ_sd'],
                'Q_Ah_delta_method': aggregate['capacity_sd_Ah_delta_method'] / precision['capacity_sd_Ah'],
                'SOC': aggregate['SOC_sd'] / precision['SOC_sd']}
            free['endpoint_errors']['SOC_error_in_local_SD'] = (free['current_soc'] - truth['SOC']) / precision['SOC_sd']
            free['endpoint_errors']['logQ_error_in_local_SD'] = math.log(free['capacity_Ah'] / truth['capacity_Ah']) / precision['logQ_sd']
        summary = {'schema': 'mumble_historical_likelihood_control_summary_v1', 'status': 'completed',
                   'source_revision': receipt['source_revision'], 'plan_sha256': receipt['plan_sha256'],
                   'reporting_source_sha256': records[str(Path(__file__).resolve())]['sha256'],
                   'prefix_records': N, 'nominal_endpoint_seconds': 7200,
                   'fits': fits, 'free_local_precision': precision, 'online': online, 'truth': truth,
                   'comparisons': comparison,
                   'execution': {'fit_invocations': 3, 'children': 3, 'inference_retries': 0,
                                 'all_inference_inputs_unchanged': True,
                                 'supervisor_wall_s_before_final_receipt': receipt['supervisor']['wall_s_before_final_receipt'],
                                 'closed_inference_output_bytes': receipt['closed_output_bytes']},
                   'coverage_validated': False, 'candidate_promoted': False,
                   'new_fit_model_learner_calls_by_reporting': 0,
                   'limits': [
                       'One fixed archived prefix. The free and constrained fits are bounded local searches, not global optimizers or exclusion certificates.',
                       'All signed NLL differences use objective_full. No likelihood-ratio significance or global exclusion threshold is applied.',
                       'The full-history pure likelihood and online prior-conditioned Gaussian-mixture beliefs are different inferential objects.',
                       'The free full Gram is undamped scaled Gauss-Newton likelihood curvature; it is not the complete nonlinear posterior Hessian or a calibrated confidence region.',
                       'Cholesky, positive numerical spectrum and small residuals do not establish global identifiability, active-bound Gaussian validity or statistical coverage.',
                       'The linked current-SOC constrained chart is not inverted for unrestricted uncertainty; constrained fits have no new reported target SD.',
                       'Single-endpoint truth inclusion is a descriptive score, not a coverage frequency or calibration result.',
                       'A lower constrained cost would mark the free baseline incomplete and would not trigger another fit.',
                       'No production uncertainty repair, historical causal attribution, new learner run, source generation or scalar inflation is established by this comparison.']}
    except BaseException as error:
        errors.append({'phase': phase, 'type': type(error).__name__, 'message': str(error)})
    postchecks = driver.posthash(records)
    for row in postchecks:
        if not row['unchanged']:
            errors.append({'phase': 'posthash', 'message': 'Read-only reporting input changed: ' + row['path']})
    if summary is not None:
        if errors:
            summary['status'] = 'failed_identity_or_reporting_check'
            summary['errors'] = errors
        save_new(output / 'summary.json', summary)
    artifact_names = ['reporting_reservation.json'] + (['summary.json'] if summary is not None else [])
    report_receipt = {'schema': 'mumble_historical_likelihood_reporting_receipt_v1',
                      'status': 'failed' if errors else 'completed', 'errors': errors,
                      'input_identities': list(records.values()), 'posthashes': postchecks,
                      'all_bound_inputs_unchanged': bool(records) and all(row['unchanged'] for row in postchecks),
                      'decoded_truth_records': truth_records,
                      'truth_decoding_gate': 'Three completed unchanged-input fit receipts, raw artifacts and inference inputs validated before truth hashing/decoding',
                      'new_fit_model_learner_calls': 0, 'new_source_generations': 0,
                      'numpy_version': np.__version__, 'python_version': platform.python_version(),
                      'BLAS_threads_requested': 1,
                      'resources': {'own_peak_RSS_bytes': utilities.own_peak_bytes(),
                                    'wall_s_before_receipt': time.monotonic() - started},
                      'artifacts': [{'path': name, **utilities.digest(output / name)} for name in artifact_names]}
    save_new(output / 'reporting_receipt.json', report_receipt)
    key = {'status': report_receipt['status'], 'summary_path': str(output / 'summary.json'),
           'errors': errors, 'truth_records_decoded': truth_records}
    if summary is not None and not errors:
        key.update(truth=summary['truth'],
                   fits=[{k: row[k] for k in ('id', 'objective_full', 'delta_NLL_from_free', 'capacity_Ah', 'current_soc', 'endpoint_errors')} for row in summary['fits']],
                   online_aggregate=summary['online']['entities'][0],
                   free_local_precision={k: summary['free_local_precision'].get(k) for k in
                                         ('status', 'logQ_sd', 'capacity_sd_Ah', 'SOC_sd', 'local_two_SD_intervals', 'condition_number_2_from_eigenvalues')},
                   comparisons=summary['comparisons'])
    print(json.dumps(key, indent=2, allow_nan=False))
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
