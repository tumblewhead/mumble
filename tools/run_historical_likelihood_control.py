#!/usr/bin/env python3
"""Execute the frozen one-prefix historical-likelihood control at most once.

All relative arguments resolve against --root. Both --output-dir and
--scratch-dir must be new; the latter must be outside the repository. The
existing C solver is never modified, warmed up, or retried by this driver.
"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import sys
import time

sys.dont_write_bytecode = True
import run_conditional_belief_probe as supervisor


PLAN = 'plans/historical_likelihood_control_001.json'
DRIVER = 'tools/run_historical_likelihood_control.py'
SUPERVISOR = 'tools/run_conditional_belief_probe.py'
AUDIT = 'experiments/historical_likelihood_control_001/source_audit.json'
REFERENCE_SOURCE = (
    'src/main.c', 'src/scm_estimator.c', 'src/scm_model.c',
    'src/scm_features.c', 'src/scm_assess.c',
    'include/scm_estimator.h', 'include/scm_model.h',
    'include/scm_features.h', 'include/scm_assess.h',
)
REQUIRED_SOURCE = REFERENCE_SOURCE + (DRIVER, SUPERVISOR)
FIT_IDS = ('free', 'fixed_recursive_Q', 'fixed_recursive_SOC')
PREFIX_RECORDS = 252000
ARCHIVED_RECORDS = 504000
RECORD = struct.Struct('<Qddd')
CSV_HEADER = b'sample_index,dt_s,current_A,voltage_V\n'
CAPS = {
    'child_CPU_s_max': 120,
    'child_wall_s_max': 180,
    'child_address_space_bytes_max': 536870912,
    'child_RSS_bytes_max': 536870912,
    'supervisor_RSS_bytes_max': 134217728,
    'supervisor_total_wall_s_max': 600,
    'child_combined_output_bytes_max': 1048576,
    'closed_output_bytes_max': 8388608,
    'scratch_CSV_bytes_max': 33554432,
}
require = supervisor.require


def check_supervisor(started, caps):
    require(time.monotonic() - started <= caps['supervisor_total_wall_s_max'],
            'Supervisor total wall limit exceeded')
    require(supervisor.own_peak_bytes() <= caps['supervisor_RSS_bytes_max'],
            'Supervisor peak RSS limit exceeded')


def read_json(path, maximum=1048576):
    require(path.stat().st_size <= maximum, 'JSON input too large: ' + str(path))
    return supervisor.strict_json(path.read_bytes())


def finite_tree(value, label='output'):
    """JSON permits null diagnostics; numeric infinity is never accepted."""
    if isinstance(value, float):
        require(math.isfinite(value), 'Nonfinite numeric value: ' + label)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            finite_tree(item, label + '[' + str(index) + ']')
    elif isinstance(value, dict):
        for key, item in value.items():
            finite_tree(item, label + '.' + key)


def tree_bytes(directory):
    return sum(path.stat().st_size for path in directory.rglob('*') if path.is_file())


def save_json(output, path, value):
    # Keep a fixed small reserve for the final failure/success receipt.
    remaining = CAPS['closed_output_bytes_max'] - tree_bytes(output) - 262144
    return supervisor.write_new_json(path, value, max(0, remaining))


def commit_identity(root, revision, relative, actual):
    content = supervisor.git_bytes(root, revision, relative)
    require(hashlib.sha256(content).hexdigest() == actual['sha256'],
            'Pinned Git blob differs: ' + revision + ':' + relative)


def validate_preflight(args, root, records, started):
    require(re.fullmatch(r'[0-9a-f]{40}', args.source_revision) is not None,
            'Source revision must be a full40-character commit SHA')
    require(Path(__file__).resolve() == supervisor.beneath(root, DRIVER),
            'Executing driver is not the pinned repository file')
    require(Path(supervisor.__file__).resolve() == supervisor.beneath(root, SUPERVISOR),
            'Imported supervisor is not the pinned repository file')
    plan_path = supervisor.beneath(root, PLAN)
    plan_id = supervisor.bind_file(records, plan_path, label=PLAN)
    plan = read_json(plan_path)
    require(plan['schema'] == 'mumble_historical_likelihood_control_contract_v1'
            and plan['status'] == 'frozen_before_new_fit_or_target_extraction',
            'Unexpected or unfrozen historical-control contract')
    require(re.fullmatch(r'[0-9a-f]{40}', plan['base_revision']) is not None,
            'Plan base revision is not a full commit SHA')
    inputs, model, execution = plan['inputs'], plan['model'], plan['execution']
    require(inputs['prefix_records'] == PREFIX_RECORDS
            and inputs['archived_records'] == ARCHIVED_RECORDS
            and inputs['observation_member_bytes'] == RECORD.size * ARCHIVED_RECORDS,
            'Input extent differs from the single frozen prefix')
    require(re.fullmatch(r'[0-9a-f]{64}', inputs['source_id']) is not None
            and re.fullmatch(r'[0-9a-f]{64}', inputs['observation_member_sha256']) is not None,
            'Invalid source or observation digest')
    require(inputs['truth_in_inference'] is False, 'Truth is not an inference input')
    require(model['modes'] == 3 and model['method'] == 'full' and model['sigma_V'] == .001,
            'Reference model differs from the frozen experiment')
    require(execution['fit_invocations_max'] == 3
            and execution['parallel_fit_processes'] == 1 and execution['retries'] == 0,
            'Unexpected fit invocation policy')
    require([row['id'] for row in plan['fits']] == list(FIT_IDS)
            and all(row['starts'] == 3 and row['max_iterations_per_start'] == 120
                    for row in plan['fits']), 'Unexpected fit sequence or optimizer budget')
    require(all('public starts0,1' in row['initial'] for row in plan['fits'][1:]),
            'Contract must disclose the unchanged CLI has_initial start indexing')
    require(all(plan['resources'][key] == value for key, value in CAPS.items()),
            'Resource caps differ from this frozen driver')
    check_supervisor(started, CAPS)

    receipt_path = supervisor.argument_path(root, args.executable_receipt)
    supervisor.bind_file(records, receipt_path, label='executable_receipt')
    receipt = read_json(receipt_path)
    require(receipt['schema'] == 'mumble_historical_likelihood_executable_receipt_v1'
            and receipt['status'] == 'qualified_before_historical_fits',
            'Unexpected executable receipt or qualification state')
    require(receipt['source_revision'] == args.source_revision
            and receipt['plan_sha256'] == plan_id['sha256'],
            'Executable receipt is not bound to this source and contract')
    require(receipt['qualification']['help_passed'] is True
            and receipt['qualification']['optimizer_calls'] == 0,
            'Preflight must contain successful help only and zero optimizer calls')
    command = receipt['compile_command']
    require(isinstance(command, list) and command
            and all(isinstance(arg, str) and arg for arg in command),
            'Missing compiler command argv')
    hashes = receipt['source_sha256']
    require(isinstance(hashes, dict) and set(REQUIRED_SOURCE) <= set(hashes),
            'Receipt omits a required C/header/driver/supervisor source')
    for relative, expected in hashes.items():
        require(isinstance(expected, str) and re.fullmatch(r'[0-9a-f]{64}', expected) is not None,
                'Invalid source hash: ' + str(relative))
        identity = supervisor.bind_file(records, supervisor.beneath(root, relative),
                                        {'sha256': expected}, relative)
        commit_identity(root, args.source_revision, relative, identity)
        if relative in REFERENCE_SOURCE or relative == SUPERVISOR:
            commit_identity(root, plan['base_revision'], relative, identity)
        check_supervisor(started, CAPS)
    commit_identity(root, args.source_revision, PLAN, plan_id)
    audit_id = supervisor.bind_file(records, supervisor.beneath(root, AUDIT), label=AUDIT)
    commit_identity(root, args.source_revision, AUDIT, audit_id)

    review = receipt['independent_source_review']
    require(review['passed'] is True, 'Independent source review has not passed')
    review_path = supervisor.beneath(root, review['path'])
    review_id = supervisor.bind_file(records, review_path, {'sha256': review['sha256']},
                                     'independent_source_review')
    commit_identity(root, args.source_revision, review['path'], review_id)
    review_content = read_json(review_path)
    require(review_content['status'] == 'pass'
            and review_content['plan_sha256'] == plan_id['sha256'],
            'Independent review is not a pass for this contract')
    for relative in (DRIVER, SUPERVISOR):
        require(review_content['source_sha256'][relative] == hashes[relative],
                'Independent review does not bind executing source: ' + relative)

    binary = supervisor.argument_path(root, args.binary)
    supervisor.bind_file(records, binary, {'sha256': receipt['binary_sha256'],
                                         'bytes': receipt['binary_bytes']}, 'reference_binary')
    require(os.access(binary, os.X_OK), 'Reference binary is not executable')
    evidence_root = supervisor.argument_path(root, args.evidence_root)
    observations = supervisor.beneath(evidence_root, inputs['observation_member'])
    supervisor.bind_file(records, observations,
                         {'sha256': inputs['observation_member_sha256'],
                          'bytes': inputs['observation_member_bytes']}, 'archived_observations')
    witness = supervisor.beneath(root, inputs['witness_path'])
    witness_id = supervisor.bind_file(records, witness, label='raw_witness_queries')
    require(witness_id['bytes'] <= 1048576, 'Unexpectedly large raw witness file')
    commit_identity(root, plan['base_revision'], inputs['witness_path'], witness_id)
    commit_identity(root, args.source_revision, inputs['witness_path'], witness_id)
    check_supervisor(started, CAPS)
    return plan, receipt, binary, observations, witness


def extract_targets(witness):
    """Read only the selected query's two target values and validity metadata."""
    selected = None
    matches = 0
    with witness.open('rb') as stream:
        for line_number, line in enumerate(stream, 1):
            query = supervisor.strict_json(line)
            require(isinstance(query, dict), 'Witness row must be a JSON object')
            if query.get('next_index') != PREFIX_RECORDS:
                continue
            matches += 1
            require(query['event'] == 'query'
                    and query['schema'] == 'mumble_continuous_query_v1',
                    'Selected witness is not a raw continuous query')
            aggregate = query['aggregate']
            require(aggregate['next_index'] == PREFIX_RECORDS
                    and aggregate['point_available'] == 1
                    and aggregate['capacity_available'] == 1,
                    'Selected recursive targets are not available at the exact prefix')
            q = supervisor.number(aggregate['capacity_Ah'], 'aggregate.capacity_Ah')
            soc = supervisor.number(aggregate['current_soc'], 'aggregate.current_soc')
            require(.03 <= q <= .10 and 0 <= soc <= 1,
                    'Selected target lies outside the public physical domain')
            selected = {'next_index': PREFIX_RECORDS, 'selector': 'aggregate',
                        'capacity_Ah': q, 'current_soc': soc,
                        'witness_line_number': line_number,
                        'witness_line_sha256': hashlib.sha256(line).hexdigest(),
                        'inference_fields': ['aggregate.capacity_Ah', 'aggregate.current_soc'],
                        'truth_fields_read_or_used': False}
    require(matches == 1, 'Expected exactly one matching aggregate witness query')
    return selected


def convert_prefix(observations, csv_path, started):
    """Write17-digit decimal CSV and independently reread its complete prefix."""
    prefix_hash = hashlib.sha256()
    csv_hash = hashlib.sha256()
    count_bytes = 0
    elapsed = charge = 0.
    with observations.open('rb') as source, csv_path.open('xb') as converted:
        converted.write(CSV_HEADER)
        csv_hash.update(CSV_HEADER)
        count_bytes += len(CSV_HEADER)
        for index in range(PREFIX_RECORDS):
            record = source.read(RECORD.size)
            require(len(record) == RECORD.size, 'Truncated original observation prefix')
            actual_index, dt, current, voltage = RECORD.unpack(record)
            require(actual_index == index and all(math.isfinite(v) for v in (dt, current, voltage))
                    and dt >= 0, 'Invalid observation index or numerical input')
            fields = [str(index), format(dt, '.17g'), format(current, '.17g'), format(voltage, '.17g')]
            require(RECORD.pack(int(fields[0]), *(float(v) for v in fields[1:])) == record,
                    'Decimal conversion does not preserve the original32-byte record')
            line = (','.join(fields) + '\n').encode('ascii')
            require(count_bytes + len(line) <= CAPS['scratch_CSV_bytes_max'],
                    'Scratch CSV exceeds its frozen byte budget')
            converted.write(line)
            count_bytes += len(line)
            csv_hash.update(line)
            prefix_hash.update(record)
            elapsed += dt
            charge += current * dt / 3600.
            if index % 1024 == 0:
                check_supervisor(started, CAPS)
        converted.flush()
        os.fsync(converted.fileno())
    reconstructed = hashlib.sha256()
    checked = 0
    with observations.open('rb') as source, csv_path.open('rb') as converted:
        require(converted.readline() == CSV_HEADER, 'Written CSV header mismatch')
        for index in range(PREFIX_RECORDS):
            fields = converted.readline().decode('ascii').rstrip('\n').split(',')
            require(len(fields) == 4, 'Written CSV row shape mismatch')
            record = RECORD.pack(int(fields[0]), *(float(v) for v in fields[1:]))
            require(record == source.read(RECORD.size), 'Written CSV record failed bitwise round-trip')
            reconstructed.update(record)
            checked += 1
            if index % 1024 == 0:
                check_supervisor(started, CAPS)
        require(converted.read(1) == b'', 'CSV includes records beyond the selected prefix')
    identity = supervisor.digest(csv_path)
    require(identity == {'bytes': count_bytes, 'sha256': csv_hash.hexdigest()}
            and reconstructed.hexdigest() == prefix_hash.hexdigest(),
            'Written CSV or reconstructed prefix digest mismatch')
    return {'prefix_records': checked, 'binary_prefix_bytes': checked * RECORD.size,
            'binary_prefix_sha256': prefix_hash.hexdigest(),
            'CSV_path': str(csv_path), 'CSV_bytes': identity['bytes'],
            'CSV_sha256': identity['sha256'], 'bitwise_roundtrip_passed': True,
            'roundtrip': 'All32-byte original records compared after17-digit formatting and after closed-file reread',
            'elapsed_s': elapsed, 'charge_Ah': charge}


def fit_command(binary, csv_path, fit_id, targets, initial=None):
    require(fit_id in FIT_IDS, 'Unknown fit id')
    command = [str(binary), '--data', str(csv_path), '--case',
               'historical_likelihood_control_001/' + fit_id,
               '--method', 'full', '--modes', '3', '--sigma', '0.001',
               '--prefix', str(PREFIX_RECORDS), '--starts', '3', '--max-iter', '120']
    if fit_id != 'free':
        theta = supervisor.vector(initial, 7, 'free_fit_theta')
        command.extend(['--initial', ','.join(format(value, '.17g') for value in theta)])
    if fit_id == 'fixed_recursive_Q':
        command.extend(['--fixed', '6', format(math.log(targets['capacity_Ah']), '.17g')])
    elif fit_id == 'fixed_recursive_SOC':
        command.extend(['--fixed-current-soc', format(targets['current_soc'], '.17g')])
    return command


def validate_fit(raw, fit_id, targets):
    """Validate the unchanged src/main.c JSON schema without fitting or inverting."""
    require(isinstance(raw, dict), 'Fit stdout must contain one JSON object')
    finite_tree(raw)
    expected = {'case_id': 'historical_likelihood_control_001/' + fit_id,
                'method': 'full', 'modes': 3, 'sigma_V': .001,
                'ocv_kind': 'illustrative_known_curve', 'ocv_table_rows': 0,
                'has_initial': fit_id != 'free',
                'fixed_mask': 64 if fit_id == 'fixed_recursive_Q' else 0,
                'fixed_alpha_mask': 0, 'has_current_soc': fit_id == 'fixed_recursive_SOC',
                'starts': 3, 'samples': PREFIX_RECORDS, 'features': PREFIX_RECORDS,
                'blocks': 0, 'basis_bytes': 0, 'data_bytes': PREFIX_RECORDS * 24,
                'payload_bytes': PREFIX_RECORDS * 8, 'workspace_bytes': PREFIX_RECORDS * 640,
                'joint_normal_dimension': 16}
    for key, value in expected.items():
        require(type(raw.get(key)) is type(value) and raw[key] == value,
                'Fit output identity/shape mismatch: ' + key)
    theta = supervisor.vector(raw['theta'], 7, 'theta')
    alpha = supervisor.vector(raw['alpha'], 9, 'alpha')
    scales = supervisor.vector(raw['coordinate_scales'], 16, 'coordinate_scales')
    require(all(value > 0 for value in scales), 'Nonpositive coordinate scale')
    supervisor.vector(raw['joint_normal'], 256, 'joint_normal')
    require(raw['joint_normal_semantics'] ==
            'Scaled likelihood Jacobian Gram matrix before damping and Schur reduction; not a posterior'
            and raw['joint_normal_coordinates'] == 'Scaled theta followed by scaled alpha; packed row-major',
            'Unexpected likelihood-matrix semantics')
    nonnegative = ('objective', 'objective_full', 'voltage_rmse', 'elapsed_cpu_s',
                   'projected_gradient', 'max_inner_kkt', 'basis_seconds',
                   'basis_max_orthogonality', 'max_discarded_column_norm', 'elapsed_physical_s')
    for key in nonnegative:
        require(supervisor.number(raw[key], key) >= 0, 'Negative diagnostic: ' + key)
    charge = supervisor.number(raw['charge_Ah'], 'charge_Ah')
    for key in ('status', 'termination_reason', 'iterations', 'evaluations', 'converged_starts',
                'active_linear_constraints', 'active_outer_bounds', 'retained_bytes',
                'setup_peak_bytes', 'unexcited_theta_mask'):
        supervisor.integer(raw[key], key)
    require(raw['status'] in (0, 1, 2) and raw['termination_reason'] in (0, 1, 2, 3)
            and raw['iterations'] <= 360 and raw['converged_starts'] <= 3,
            'Unexpected optimizer status or iteration count')
    q = math.exp(theta[6])
    soc = theta[5] - charge / q
    require(math.isfinite(q) and math.log(.03) <= theta[6] <= math.log(.10)
            and math.isfinite(soc) and 0 <= soc <= 1, 'Invalid fitted target')
    require(isinstance(raw['assessment'], dict)
            and raw['assessment'].get('diagnostic_only') is True
            and raw['assessment'].get('coverage_certificate') is False,
            'Missing explicit legacy assessment qualification')
    if fit_id == 'fixed_recursive_Q':
        require(theta[6] == math.log(targets['capacity_Ah']), 'Fixed logQ was not applied')
    if fit_id == 'fixed_recursive_SOC':
        require(raw['fixed_current_soc'] == targets['current_soc'], 'Fixed current SOC was not applied')
        rounding = 32 * sys.float_info.epsilon * max(1., abs(theta[5]), abs(charge / q))
        require(abs(soc - targets['current_soc']) <= rounding,
                'Linked current-SOC target fails arithmetic consistency')
    else:
        require(raw['fixed_current_soc'] is None, 'Unexpected linked current-SOC value')
    return {'fit_id': fit_id, 'optimizer_status': raw['status'],
            'termination_reason': raw['termination_reason'], 'iterations': raw['iterations'],
            'evaluations': raw['evaluations'], 'converged_starts': raw['converged_starts'],
            'theta': theta, 'alpha': alpha, 'capacity_Ah': q, 'endpoint_SOC': soc,
            'charge_Ah': charge, 'elapsed_physical_s': raw['elapsed_physical_s'],
            'objective': raw['objective'], 'objective_full': raw['objective_full'],
            'voltage_rmse': raw['voltage_rmse'],
            'matrix_chart': 'linked_current_SOC' if fit_id == 'fixed_recursive_SOC' else 'entering_state',
            'unrestricted_local_precision_computed': False,
            'raw_Gram_scales_and_legacy_assessment': fit_id + '/stdout.json',
            'uncertainty_semantics': 'No covariance inversion by this driver; raw legacy assessment remains diagnostic only'}


def posthash(records, started=None):
    rows = []
    for path, before in records.items():
        try:
            after = supervisor.digest(Path(path))
            unchanged = after == {key: before[key] for key in ('bytes', 'sha256')}
            rows.append({'path': path, 'unchanged': unchanged, **after})
        except BaseException as error:
            rows.append({'path': path, 'unchanged': False, 'error': repr(error)})
        if started is not None:
            check_supervisor(started, CAPS)
    return rows


def child_bounds(started):
    check_supervisor(started, CAPS)
    remaining = CAPS['supervisor_total_wall_s_max'] - (time.monotonic() - started)
    return {'probe_CPU_s_max': CAPS['child_CPU_s_max'],
            'probe_wall_s_max': min(CAPS['child_wall_s_max'], remaining),
            'probe_address_space_bytes_max': CAPS['child_address_space_bytes_max'],
            'probe_peak_RSS_bytes_max': CAPS['child_RSS_bytes_max'],
            'probe_output_bytes_max': CAPS['child_combined_output_bytes_max'],
            'supervisor_peak_RSS_bytes_max': CAPS['supervisor_RSS_bytes_max']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'evidence-root', 'binary', 'output-dir', 'scratch-dir', 'executable-receipt'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--source-revision', required=True)
    args = parser.parse_args(argv)
    started = time.monotonic()
    root = args.root.resolve()
    output = supervisor.argument_path(root, args.output_dir)
    scratch = supervisor.argument_path(root, args.scratch_dir)
    evidence_root = supervisor.argument_path(root, args.evidence_root)
    original_primary = root / 'experiments/continuous_learning_validation_001/implementation/primary'
    require(not output.is_relative_to(original_primary), 'Cannot write to original primary evidence')
    require(not output.is_relative_to(evidence_root) and not evidence_root.is_relative_to(output),
            'Output and restored evidence must be disjoint')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()  # A failed reserved attempt is never reused.
    records, errors, fits = {}, [], []
    plan = executable = targets = conversion = None
    phase = 'preflight'
    scratch_created = False
    csv_path = scratch / 'observations-prefix.csv'
    final_hashes = []
    try:
        require(not scratch.is_relative_to(root) and not root.is_relative_to(scratch),
                'Scratch conversion must be outside the repository')
        require(not scratch.is_relative_to(evidence_root) and not evidence_root.is_relative_to(scratch)
                and not scratch.is_relative_to(output) and not output.is_relative_to(scratch),
                'Scratch, evidence, and output trees must be disjoint')
        plan, executable, binary, observations, witness = validate_preflight(args, root, records, started)
        phase = 'target_extraction'
        targets = extract_targets(witness)
        save_json(output, output / 'recursive_targets.json', targets)
        phase = 'prefix_conversion'
        scratch.parent.mkdir(parents=True, exist_ok=True)
        scratch.mkdir()
        scratch_created = True
        conversion = convert_prefix(observations, csv_path, started)
        supervisor.bind_file(records, csv_path,
                             {'bytes': conversion['CSV_bytes'], 'sha256': conversion['CSV_sha256']},
                             'verified_prefix_CSV')
        save_json(output, output / 'conversion.json', conversion)
        before = posthash(records, started)
        save_json(output, output / 'before_fits_identities.json', before)
        require(all(row['unchanged'] for row in before), 'Input changed before the first fit')
        initial = None
        for fit_id in FIT_IDS:
            phase = fit_id + ':prelaunch'
            check_supervisor(started, CAPS)
            fit_dir = output / fit_id
            fit_dir.mkdir()
            command = fit_command(binary, csv_path, fit_id, targets, initial)
            bounds = child_bounds(started)
            row = {'fit_id': fit_id, 'command': command, 'supervisor_invocation_started': False,
                   'worker': None, 'validated_output': False}
            fits.append(row)
            save_json(output, fit_dir / 'launch.json',
                      {'fit_id': fit_id, 'command': command, 'adapted_supervisor_bounds': bounds,
                       'source_revision': args.source_revision,
                       'plan_sha256': records[str(root / PLAN)]['sha256'],
                       'starts': ['public0', 'public1', 'public2'] if fit_id == 'free'
                                 else ['free_fit_theta', 'public0', 'public1']})
            phase = fit_id + ':child'
            row['supervisor_invocation_started'] = True
            worker = supervisor.supervise(command, fit_dir, bounds)
            row['worker'] = worker
            worker['RSS_method'] = ('wait4 for this exact fit PID only; includes fork/exec setup, '
                                    'excludes compiler/Git/other-fit usage')
            for old, new in (('raw_probe.json', 'stdout.json'), ('probe.stderr', 'stderr.txt')):
                require(not (fit_dir / new).exists(), 'Unexpected existing raw-output target')
                (fit_dir / old).rename(fit_dir / new)
            save_json(output, fit_dir / 'resources.json', worker)
            phase = fit_id + ':posthash'
            checked = posthash(records, started)
            save_json(output, fit_dir / 'posthash.json', checked)
            require(all(item['unchanged'] for item in checked), 'Bound input changed during a fit')
            require(worker['exit_code'] == 0, 'Reference process failed: ' + str(worker['exit_code']))
            require(not worker['resource_violations'], 'Fit resource limit: ' + ', '.join(worker['resource_violations']))
            phase = fit_id + ':parse'
            raw = read_json(fit_dir / 'stdout.json', CAPS['child_combined_output_bytes_max'])
            row['summary'] = validate_fit(raw, fit_id, targets)
            row['validated_output'] = True
            if fit_id == 'free':
                initial = row['summary']['theta']
            save_json(output, fit_dir / 'summary.json', row['summary'])
            check_supervisor(started, CAPS)
    except BaseException as error:
        errors.append({'phase': phase, 'type': type(error).__name__, 'message': str(error)})
    finally:
        final_hashes = posthash(records)
        for item in final_hashes:
            if not item['unchanged']:
                errors.append({'phase': 'final_posthash', 'message': 'Bound file changed or unreadable: ' + item['path']})

    if supervisor.own_peak_bytes() > CAPS['supervisor_RSS_bytes_max']:
        errors.append({'phase': 'finalization', 'message': 'Supervisor RSS limit exceeded'})
    if time.monotonic() - started > CAPS['supervisor_total_wall_s_max']:
        errors.append({'phase': 'finalization', 'message': 'Supervisor total wall limit exceeded'})
    summaries = [row['summary'] for row in fits if row.get('validated_output')]
    result = {'schema': 'mumble_historical_likelihood_control_result_v1',
              'status': 'failed' if errors else 'completed', 'execution_errors': errors,
              'source_revision': args.source_revision,
              'plan_sha256': records.get(str(root / PLAN), {}).get('sha256'),
              'source_id': plan['inputs']['source_id'] if plan else None,
              'prefix_records': PREFIX_RECORDS, 'recursive_targets': targets,
              'fits': summaries, 'all_three_outputs_validated': len(summaries) == 3 and not errors,
              'local_precision_computed': False, 'coverage_validated': False,
              'candidate_promoted': False, 'statistical_threshold': None}
    if summaries and summaries[0]['fit_id'] == 'free':
        baseline = summaries[0]['objective_full']
        result['signed_NLL_differences_from_free'] = {
            row['fit_id']: row['objective_full'] - baseline for row in summaries[1:]}
        result['constrained_fit_beats_free_baseline'] = any(
            row['objective_full'] < baseline for row in summaries[1:])
    save_json(output, output / 'result.json', result)
    artifacts = [{'path': str(path.relative_to(output)), **supervisor.digest(path)}
                 for path in sorted(output.rglob('*')) if path.is_file()]
    scratch_identity = None
    if scratch_created and csv_path.exists():
        scratch_identity = {'path': str(csv_path), **supervisor.digest(csv_path)}
    before_receipt = tree_bytes(output)
    receipt = {'schema': 'mumble_historical_likelihood_control_execution_v1',
               'status': 'failed' if errors else 'completed', 'errors': errors,
               'source_revision': args.source_revision,
               'plan_sha256': result['plan_sha256'],
               'executable_receipt': str(supervisor.argument_path(root, args.executable_receipt)),
               'fit_invocations_attempted': sum(row['supervisor_invocation_started'] for row in fits),
               'observed_children_launched': sum(bool(row['worker'] and row['worker']['child_launched']) for row in fits),
               'launch_state_fully_recorded': all(not row['supervisor_invocation_started'] or row['worker'] is not None for row in fits),
               'fits': fits, 'conversion': conversion, 'scratch_CSV': scratch_identity,
               'pre_execution_identities': list(records.values()),
               'post_execution_identities': final_hashes,
               'all_bound_inputs_unchanged': bool(records) and all(row['unchanged'] for row in final_hashes),
               'artifacts': artifacts, 'closed_output_bytes': 0,
               'resources': CAPS,
               'supervisor': {'own_peak_RSS_bytes': supervisor.own_peak_bytes(),
                              'RSS_method': 'getrusage(RUSAGE_SELF), not cumulative child usage',
                              'wall_s_before_final_receipt': time.monotonic() - started},
               'new_learner_ingests': 0, 'new_source_generations': 0, 'old_scorer_runs': 0,
               'truth_in_inference': False, 'automatic_retries': 0, 'original_inputs_written': False}
    for _ in range(8):
        measured = before_receipt + len((json.dumps(receipt, indent=2, allow_nan=False) + '\n').encode())
        if receipt['closed_output_bytes'] == measured:
            break
        receipt['closed_output_bytes'] = measured
    require(receipt['closed_output_bytes'] <= CAPS['closed_output_bytes_max'], 'Closed output budget exceeded')
    supervisor.write_new_json(output / 'receipt.json', receipt,
                              CAPS['closed_output_bytes_max'] - before_receipt)
    print(json.dumps({'status': receipt['status'], 'output_dir': str(output),
                      'fit_invocations_attempted': receipt['fit_invocations_attempted'],
                      'observed_children_launched': receipt['observed_children_launched'],
                      'closed_output_bytes': tree_bytes(output)}, allow_nan=False))
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
