#!/usr/bin/env python3
"""Supervise one frozen conditional-belief probe; never replay or update a learner.

Relative CLI paths are resolved against --root. The output directory must be new.
It is reserved before validation so rejected attempts also retain a receipt.
"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import resource
import selectors
import signal
import stat
import struct
import subprocess
import sys
import time


PLAN = 'plans/conditional_belief_adequacy_001.json'
REVIEW = 'experiments/conditional_belief_adequacy_001/contract_review.json'
REQUIRED_SOURCE = (
    'tools/conditional_belief_probe.c',
    'tools/run_conditional_belief_probe.py',
    'tools/restore_conditional_evidence.py',
    'src/scm_hypothesis.c', 'src/scm_hypothesis_checkpoint.c', 'src/scm_model.c',
    'include/scm_hypothesis.h', 'include/scm_hypothesis_checkpoint.h',
    'include/scm_online.h', 'include/scm_model.h',
)
BUFFER = 1024 * 1024
DIM = 16
NODES = 32


class ProbeError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise ProbeError(message)


def reject_constant(value):
    raise ProbeError('Nonfinite JSON constant: ' + value)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key: ' + key)
        result[key] = value
    return result


def strict_json(data):
    return json.loads(data, parse_constant=reject_constant, object_pairs_hook=unique_object)


def digest(path):
    """Hash a regular file without following its final path as a symlink."""
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    checksum = hashlib.sha256()
    size = 0
    with os.fdopen(descriptor, 'rb') as stream:
        require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'Not a regular file: ' + str(path))
        while chunk := stream.read(BUFFER):
            size += len(chunk)
            checksum.update(chunk)
    return {'bytes': size, 'sha256': checksum.hexdigest()}


def beneath(root, name):
    relative = Path(name)
    require(not relative.is_absolute() and '..' not in relative.parts,
            'Unsafe relative input path: ' + str(name))
    candidate = root / relative
    require(not candidate.is_symlink(), 'Symlink input is not accepted: ' + str(candidate))
    resolved = candidate.resolve()
    require(resolved.is_relative_to(root), 'Input escapes its root: ' + str(name))
    return resolved


def argument_path(root, path):
    return (path if path.is_absolute() else root / path).resolve()


def own_peak_bytes():
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * (1 if sys.platform == 'darwin' else 1024)


def bind_file(records, path, expected=None, label=None):
    actual = digest(path)
    row = {'path': str(path), 'label': label or str(path), **actual}
    if expected is not None:
        require(actual['sha256'] == expected['sha256'], 'SHA256 mismatch: ' + row['label'])
        if 'bytes' in expected:
            require(actual['bytes'] == expected['bytes'], 'Byte-count mismatch: ' + row['label'])
    previous = records.get(str(path))
    require(previous is None or previous['sha256'] == row['sha256'], 'File changed during validation: ' + row['label'])
    records[str(path)] = row
    return row


def git_bytes(root, revision, relative):
    completed = subprocess.run(
        ['git', '-C', str(root), 'show', revision + ':' + relative],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=False,
    )
    require(completed.returncode == 0, 'Cannot read pinned source blob: ' + relative)
    return completed.stdout


def validate_inputs(args, root, records):
    plan_path = beneath(root, PLAN)
    review_path = beneath(root, REVIEW)
    plan_identity = bind_file(records, plan_path, label=PLAN)
    bind_file(records, review_path, label=REVIEW)
    plan = strict_json(plan_path.read_bytes())
    review = strict_json(review_path.read_bytes())
    require(plan['schema'] == 'mumble_conditional_belief_adequacy_contract_v1', 'Unexpected plan schema')
    require(review['status'] == 'pass' and review['plan_sha256'] == plan_identity['sha256'],
            'Contract review does not bind this frozen plan')
    require(re.fullmatch(r'[0-9a-f]{40}', args.source_revision) is not None, 'Source revision must be a full commit SHA')
    scope = plan['scope']
    require(scope['next_indices'] == [252000, 283500, 294000] and scope['components'] == 2
            and scope['dimension'] == DIM and scope['nodes_per_component'] == NODES,
            'Scope differs from the fixed three-checkpoint experiment')
    require(scope['maximum_node_propagations'] == 192 and scope['maximum_center_propagations'] == 6,
            'Unexpected propagation budgets')
    require(plan['resource_bounds']['probe_processes'] == 1, 'Only one probe process is permitted')

    receipt_path = argument_path(root, args.executable_receipt)
    bind_file(records, receipt_path, label='executable_receipt')
    receipt = strict_json(receipt_path.read_bytes())
    require(receipt['schema'] == 'mumble_conditional_probe_executable_receipt_v1', 'Unexpected executable receipt schema')
    require(receipt['status'] == 'qualified_before_canonical_probe', 'Executable has not been qualified')
    require(receipt['source_revision'] == args.source_revision, 'Receipt/source revision mismatch')
    require(receipt['plan_sha256'] == plan_identity['sha256'], 'Receipt/plan mismatch')
    require(receipt['qualification']['passed'] is True, 'Fabricated qualification did not pass')
    require(isinstance(receipt['compile_command'], list) and receipt['compile_command']
            and all(isinstance(part, str) for part in receipt['compile_command']), 'Missing compile command')
    source_hashes = receipt['source_sha256']
    require(isinstance(source_hashes, dict) and set(REQUIRED_SOURCE) <= set(source_hashes),
            'Executable receipt omits required compile/supervisor sources')
    for relative in set(source_hashes) | {PLAN, REVIEW}:
        path = beneath(root, relative)
        expected = {'sha256': source_hashes[relative]} if relative in source_hashes else None
        identity = bind_file(records, path, expected, relative)
        committed = git_bytes(root, args.source_revision, relative)
        require(hashlib.sha256(committed).hexdigest() == identity['sha256'],
                'Working source differs from the published source revision: ' + relative)
    require(Path(__file__).resolve() == beneath(root, 'tools/run_conditional_belief_probe.py'),
            'The executing supervisor is not the pinned repository file')
    for relative, identity in plan['inputs']['identities'].items():
        bind_file(records, beneath(root, relative), identity, relative)
    binary = argument_path(root, args.binary)
    bind_file(records, binary, {'sha256': receipt['binary_sha256'], 'bytes': receipt['binary_bytes']}, 'probe_binary')
    require(os.access(binary, os.X_OK), 'Probe binary is not executable')

    evidence_root = argument_path(root, args.evidence_root)
    members = plan['inputs']['archive_members']
    require(len(members) == 4 and len({item['path'] for item in members}) == 4, 'Unexpected input member set')
    selected = {}
    for item in members:
        path = beneath(evidence_root, item['path'])
        bind_file(records, path, item, item['path'])
        selected[Path(item['path']).name] = path
    observations = selected['observations.bin']
    require(observations.stat().st_size == 32 * plan['inputs']['observation_records'], 'Observation extent mismatch')
    command = [str(binary), '--source-id', plan['inputs']['source_id'], '--observations', str(observations)]
    expected_observations = {}
    with observations.open('rb') as stream:
        for index in scope['next_indices']:
            checkpoint = selected['learner-' + str(index) + '.bin']
            command.extend(['--checkpoint', str(index), str(checkpoint)])
            stream.seek(32 * index)
            raw = stream.read(32)
            require(len(raw) == 32, 'Missing selected next observation')
            actual_index, dt, current, voltage = struct.unpack('<Qddd', raw)
            require(actual_index == index and all(math.isfinite(v) for v in (dt, current, voltage)),
                    'Selected next observation is invalid')
            expected_observations[index] = (dt, current, voltage)
    return plan, receipt, command, expected_observations


def stop_group(pid):
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def supervise(command, output, bounds):
    """Use only this child's wait4 usage; git/compiler children are unrelated."""
    started = time.monotonic()
    stdout_read, stdout_write = os.pipe()
    stderr_read, stderr_write = os.pipe()
    files = {
        'stdout': (output / 'raw_probe.json').open('xb'),
        'stderr': (output / 'probe.stderr').open('xb'),
    }
    pid = os.fork()
    if pid == 0:
        try:
            os.setsid()
            os.dup2(stdout_write, 1)
            os.dup2(stderr_write, 2)
            for descriptor in (stdout_read, stdout_write, stderr_read, stderr_write):
                if descriptor not in (1, 2):
                    os.close(descriptor)
            cpu = math.ceil(bounds['probe_CPU_s_max'])
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
            space = bounds['probe_address_space_bytes_max']
            resource.setrlimit(resource.RLIMIT_AS, (space, space))
            resource.setrlimit(resource.RLIMIT_FSIZE, (bounds['probe_output_bytes_max'],) * 2)
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            os.execve(command[0], command, os.environ.copy())
        except BaseException as error:
            os.write(2, ('Probe exec/setup failed: ' + repr(error) + '\n').encode()[:4096])
            os._exit(127)
    os.close(stdout_write)
    os.close(stderr_write)
    selector = selectors.DefaultSelector()
    for descriptor, name in ((stdout_read, 'stdout'), (stderr_read, 'stderr')):
        os.set_blocking(descriptor, False)
        selector.register(descriptor, selectors.EVENT_READ, name)
    violations = []
    output_bytes = {'stdout': 0, 'stderr': 0}
    observed_bytes = {'stdout': 0, 'stderr': 0}
    wait_status = usage = None
    reaped_wall = None
    killed = False

    def violate(reason):
        nonlocal killed
        if reason not in violations:
            violations.append(reason)
        if not killed:
            stop_group(pid)
            killed = True

    try:
        while selector.get_map() or usage is None:
            elapsed = time.monotonic() - started
            if elapsed > bounds['probe_wall_s_max']:
                violate('probe_wall_limit')
            if own_peak_bytes() > bounds['supervisor_peak_RSS_bytes_max']:
                violate('supervisor_RSS_limit')
            if usage is None:
                completed_pid, status, consumed = os.wait4(pid, os.WNOHANG)
                if completed_pid:
                    wait_status, usage = status, consumed
                    reaped_wall = time.monotonic() - started
            for key, _ in selector.select(timeout=0.02):
                chunk = os.read(key.fd, 65536)
                if not chunk:
                    selector.unregister(key.fd)
                    os.close(key.fd)
                    continue
                name = key.data
                observed_bytes[name] += len(chunk)
                remaining = bounds['probe_output_bytes_max'] - sum(output_bytes.values())
                kept = chunk[:max(0, remaining)]
                files[name].write(kept)
                output_bytes[name] += len(kept)
                if len(kept) != len(chunk):
                    violate('combined_probe_stdout_stderr_limit')
            if killed and usage is not None and time.monotonic() - started > bounds['probe_wall_s_max'] + 1:
                break
    except BaseException as error:
        violate('supervisor_exception:' + type(error).__name__ + ':' + str(error))
    finally:
        if usage is None:
            stop_group(pid)
            _, wait_status, usage = os.wait4(pid, 0)
            reaped_wall = time.monotonic() - started
        for key in list(selector.get_map().values()):
            selector.unregister(key.fd)
            os.close(key.fd)
        selector.close()
        for stream in files.values():
            stream.flush()
            os.fsync(stream.fileno())
            stream.close()
    cpu_s = usage.ru_utime + usage.ru_stime
    peak = int(usage.ru_maxrss) * (1 if sys.platform == 'darwin' else 1024)
    if cpu_s > bounds['probe_CPU_s_max']:
        violations.append('probe_CPU_limit')
    if peak > bounds['probe_peak_RSS_bytes_max']:
        violations.append('probe_RSS_limit')
    if reaped_wall > bounds['probe_wall_s_max'] and 'probe_wall_limit' not in violations:
        violations.append('probe_wall_limit')
    return {
        'child_launched': True, 'pid': pid, 'command': command,
        'exit_code': os.waitstatus_to_exitcode(wait_status),
        'wall_s_through_wait4': reaped_wall,
        'CPU_user_s': usage.ru_utime, 'CPU_system_s': usage.ru_stime, 'CPU_total_s': cpu_s,
        'peak_RSS_bytes': peak,
        'RSS_method': 'wait4 for this exact probe PID only; includes fork/exec setup, excludes git/compiler subprocess usage',
        'stdout_stderr_bytes_written': output_bytes,
        'stdout_stderr_bytes_observed': observed_bytes,
        'output_truncated': output_bytes != observed_bytes,
        'limits': {key: value for key, value in bounds.items() if key.startswith('probe_')},
        'resource_violations': violations,
    }


def number(value, label):
    require(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value),
            'Expected finite number: ' + label)
    return value


def vector(value, length, label):
    require(isinstance(value, list) and len(value) == length, 'Unexpected vector shape: ' + label)
    return [number(item, label) for item in value]


def integer(value, label):
    require(type(value) is int and value >= 0, 'Expected nonnegative integer: ' + label)
    return value


def reduce_probe(raw, plan, expected_observations):
    """Reduce only recorded nodes; no model call, state correction or survivor rule."""
    require(raw['schema'] == 'mumble_conditional_belief_probe_v1', 'Unexpected raw probe schema')
    require(raw['status'] in ('completed_all_components_admissible', 'completed_with_inadmissible_components'),
            'Probe did not finish valid centers/references')
    require(raw['source_id'] == plan['inputs']['source_id'], 'Raw source identity differs')
    for field in ('new_learner_updates', 'source_generations', 'truth_inputs'):
        require(type(raw[field]) is int and raw[field] == 0, 'Forbidden activity: ' + field)
    lower = vector(raw['lower'], DIM, 'lower bounds')
    upper = vector(raw['upper'], DIM, 'upper bounds')
    names = raw['coordinate_names']
    require(isinstance(names, list) and len(names) == DIM and len(set(names)) == DIM,
            'Unexpected coordinate labels')
    require(all(a < b for a, b in zip(lower, upper)), 'Invalid public bounds')
    require(len(raw['snapshots']) == 3, 'Expected exactly three snapshots')
    tolerances = plan['numerical_checks']
    failures = []
    checks = 0

    def close(actual, expected, absolute, relative, label):
        nonlocal checks
        checks += 1
        error = abs(number(actual, label) - number(expected, label))
        allowance = absolute + relative * max(abs(actual), abs(expected))
        if error > allowance:
            failures.append({'check': label, 'actual': actual, 'expected': expected,
                             'absolute_error': error, 'allowance': allowance})

    def variance_close(actual, expected, label):
        close(actual, expected, tolerances['variance_reconstruction_abs_V2'],
              tolerances['variance_reconstruction_rel'], label)

    node_total = center_total = inadmissible_total = bounded_total = material_total = 0
    components = []
    for expected_index, snapshot in zip(plan['scope']['next_indices'], raw['snapshots']):
        require(snapshot['checkpoint_next_index'] == snapshot['observation_index'] == expected_index
                and snapshot['predicted_next_index'] == expected_index + 1, 'Snapshot chronology mismatch')
        require(snapshot['saved_state_unchanged'] is True, 'Probe changed its saved state')
        expected = expected_observations[expected_index]
        require(tuple(snapshot[key] for key in ('dt_s', 'current_A', 'observed_voltage_V')) == expected,
                'Probe next observation differs from the archived bytes')
        require(snapshot['nominal_checkpoint_s'] == expected_index / 35, 'Nominal checkpoint time differs')
        vector(snapshot['log_weights'], 2, 'saved log weights')
        require(len(snapshot['components']) == 2, 'Expected exactly two components')
        for expected_component, component in enumerate(snapshot['components']):
            label = str(expected_index) + '/' + str(expected_component)
            require(component['component'] == expected_component, 'Component identity mismatch')
            mean = vector(component['saved_mean'], DIM, label + '/mean')
            packed = vector(component['saved_lower_factor_packed_by_row'], 136, label + '/factor')
            factor = [[packed[i * (i + 1) // 2 + j] if j <= i else 0.0 for j in range(DIM)] for i in range(DIM)]
            require(all(factor[i][i] >= 0 for i in range(DIM)), 'Negative factor diagonal')
            require(all(a <= value <= b for a, value, b in zip(lower, mean, upper)), 'Saved center outside public bounds')
            sigma = number(component['sigma_V'], label + '/sigma_V')
            require(sigma == plan['inputs']['expected_config']['sigma_V'], 'Observation-noise configuration differs')
            require(component['center_valid'] is True and component['linear_reference_valid'] is True,
                    'Invalid center or linearized reference')
            center = component['center']
            require(center['column'] == -1 and center['sign'] == 0 and center['weight'] == 0
                    and center['admitted'] is True and center['propagated'] is True,
                    'Invalid center record')
            require(vector(center['pre_state'], DIM, label + '/center') == mean, 'Center differs from saved mean')
            center_total += 1
            linear = component['linearized']
            mean_linear = number(linear['mean_V'], label + '/linear mean')
            physical_mean = number(linear['physical_center_V'], label + '/physical mean')
            close(physical_mean, mean_linear, tolerances['center_physical_vs_production_voltage_abs_V'], 0, label + '/voltage order')
            close(linear['physical_minus_production_order_V'], physical_mean - mean_linear,
                  tolerances['node_rule_mean_abs'], 0, label + '/voltage order difference')
            require(linear['center_order_tolerance_V'] == tolerances['center_physical_vs_production_voltage_abs_V'],
                    'Center-order tolerance differs from frozen plan')
            close(linear['direct_chain_vs_propagated_factor_max_V'], 0,
                  tolerances['factor_projection_abs_V'], 0, label + '/factor projection')
            projected = vector(linear['projected_factor_V'], DIM, label + '/projected factor')
            latent = math.fsum(value * value for value in projected)
            variance_close(linear['clean_variance_V2'], latent, label + '/linear latent reconstruction')
            variance_close(linear['clean_sd_V'] ** 2, latent, label + '/linear latent SD')
            variance_close(linear['predictive_variance_V2'], latent + sigma * sigma, label + '/linear observation noise once')
            variance_close(linear['predictive_sd_from_hypot_V'] ** 2, latent + sigma * sigma, label + '/linear predictive SD')

            nodes = component['nodes']
            require(component['node_count'] == NODES and len(nodes) == NODES, 'Incomplete intended node rule')
            keys = set()
            valid_pre = []
            invalid_records = []
            propagated = pre_invalid = post_invalid = 0
            for node in nodes:
                column, sign = node['column'], node['sign']
                require(type(column) is int and 0 <= column < DIM and type(sign) is int and sign in (-1, 1), 'Invalid node identity')
                require((column, sign) not in keys, 'Duplicate node identity')
                keys.add((column, sign))
                require(node['weight'] == plan['scope']['node_weight'], 'Node weight changed')
                pre = vector(node['pre_state'], DIM, label + '/node state')
                valid_pre.append(pre)
                for i in range(DIM):
                    close(pre[i], mean[i] + sign * 4.0 * factor[i][column], tolerances['node_rule_mean_abs'], 0,
                          label + '/node formula/' + str(column) + '/' + str(sign) + '/' + str(i))
                expected_mask = sum(1 << i for i in range(DIM) if pre[i] < lower[i] or pre[i] > upper[i])
                require(node['pre_failure_mask'] == expected_mask, 'Node pre-domain mask mismatch')
                require(type(node['propagated']) is bool and type(node['admitted']) is bool, 'Invalid node status type')
                require(node['propagated'] == (expected_mask == 0), 'Invalid node propagation policy')
                propagated += node['propagated']
                pre_invalid += expected_mask != 0
                post = node['post_state']
                if post is not None:
                    post = vector(post, DIM, label + '/post state')
                    post_mask = sum(1 << i for i in range(DIM) if post[i] < lower[i] or post[i] > upper[i])
                    require(node['post_failure_mask'] == post_mask, 'Node post-domain mask mismatch')
                admitted = expected_mask == 0 and node['propagated'] and node['model_code'] == 0 and post is not None and node['post_failure_mask'] == 0
                require(node['admitted'] == admitted, 'Node admission mismatch')
                post_invalid += expected_mask == 0 and not admitted
                if admitted:
                    number(node['voltage_V'], label + '/node voltage')
                else:
                    invalid_records.append({'column': column, 'sign': sign, 'failures': node['failures']})
            require(component['node_propagations'] == propagated and component['pre_invalid_nodes'] == pre_invalid
                    and component['post_invalid_nodes'] == post_invalid and component['invalid_nodes'] == len(invalid_records),
                    'Component propagation/domain accounting mismatch')
            node_total += propagated
            admitted = not invalid_records
            require(type(component['moment_rule_admissible']) is bool and component['moment_rule_admissible'] == admitted,
                    'Partial rule incorrectly admitted')
            if not admitted:
                inadmissible_total += 1
                require(component['nonlinear_moments'] is None, 'Inadmissible rule has nonlinear survivor moments')

            chart_mean = [math.fsum(row[i] for row in valid_pre) / NODES for i in range(DIM)]
            for i in range(DIM):
                close(chart_mean[i], mean[i], tolerances['node_rule_mean_abs'], 0, label + '/chart mean/' + str(i))
                for j in range(i + 1):
                    intended = math.fsum(factor[i][k] * factor[j][k] for k in range(DIM))
                    reconstructed = math.fsum((row[i] - chart_mean[i]) * (row[j] - chart_mean[j]) for row in valid_pre) / NODES
                    close(reconstructed, intended, tolerances['node_rule_covariance_abs'],
                          tolerances['node_rule_covariance_rel'], label + '/chart covariance/' + str(i) + '/' + str(j))
            feasibility = []
            for i, (a, b) in enumerate(zip(lower, upper)):
                variance = math.fsum(value * value for value in factor[i])
                cap = (b - mean[i]) * (mean[i] - a)
                allowance = 128 * sys.float_info.epsilon * (b - a) ** 2
                excess = variance - cap
                violation = excess > allowance
                bounded_total += violation
                feasibility.append({'coordinate': i, 'name': names[i], 'mean': mean[i], 'lower': a, 'upper': b,
                                    'variance': variance, 'cap': cap, 'excess': excess,
                                    'comparison_allowance': allowance, 'violation': violation})
            comparison = None
            if admitted:
                nonlinear = component['nonlinear_moments']
                require(isinstance(nonlinear, dict), 'Admitted rule lacks nonlinear moments')
                offsets = [node['voltage_V'] - physical_mean for node in nodes]
                shift = math.fsum(offsets) / NODES
                mean_nonlinear = physical_mean + shift
                variance = math.fsum((value - shift) ** 2 for value in offsets) / NODES
                mean_change = physical_mean - mean_linear + shift
                variance_change = variance - latent
                close(nonlinear['mean_V'], mean_nonlinear, tolerances['node_rule_mean_abs'], 0, label + '/nonlinear mean')
                close(nonlinear['mean_shift_vs_physical_center_V'], shift, tolerances['node_rule_mean_abs'], 0, label + '/nonlinear physical shift')
                close(nonlinear['mean_shift_vs_production_center_V'], mean_change, tolerances['node_rule_mean_abs'], 0, label + '/nonlinear production shift')
                variance_close(nonlinear['clean_variance_V2'], variance, label + '/nonlinear latent reconstruction')
                variance_close(nonlinear['predictive_variance_V2'], variance + sigma * sigma, label + '/nonlinear observation noise once')
                variance_close(nonlinear['variance_shift_V2'], variance_change, label + '/nonlinear variance shift')
                mean_material = abs(mean_change) >= plan['decision_scales']['absolute_mean_scale_V']
                variance_material = abs(variance_change) >= plan['decision_scales']['absolute_variance_scale_V2']
                material_total += mean_material or variance_material
                comparison = {
                    'linear_mean_V': mean_linear, 'nonlinear_mean_V': mean_nonlinear,
                    'linear_latent_variance_V2': latent, 'nonlinear_latent_variance_V2': variance,
                    'linear_predictive_variance_V2': latent + sigma * sigma,
                    'nonlinear_predictive_variance_V2': variance + sigma * sigma,
                    'signed_mean_change_V': mean_change, 'signed_variance_change_V2': variance_change,
                    'mean_change_over_sigma_V': mean_change / sigma,
                    'variance_change_over_sigma_V_squared': variance_change / (sigma * sigma),
                    'material_mean_shift': mean_material, 'material_variance_shift': variance_material,
                }
            components.append({
                'checkpoint_next_index': expected_index, 'nominal_checkpoint_s': expected_index / 35,
                'component': expected_component, 'node_propagations': propagated,
                'moment_rule_admissible': admitted, 'invalid_nodes': invalid_records,
                'bounded_scalar_moments': feasibility, 'nonlinear_comparison': comparison,
            })
    require(integer(raw['node_propagations'], 'node_propagations') == node_total <= 192, 'Global node budget/accounting mismatch')
    require(integer(raw['center_propagations'], 'center_propagations') == center_total == 6, 'Global center budget/accounting mismatch')
    require(raw['inadmissible_components'] == inadmissible_total, 'Global admissibility count mismatch')
    require((raw['status'] == 'completed_all_components_admissible') == (inadmissible_total == 0), 'Raw status disagrees with component admission')
    decision = ('identity_or_arithmetic_failure' if failures else
                'domain_or_bounded_moment_failure' if inadmissible_total or bounded_total else
                'admitted_material_moment_shift' if material_total else 'admitted_small_moment_shift')
    return {
        'schema': 'mumble_conditional_belief_probe_reduction_v1',
        'status': 'failed_numerical_checks' if failures else 'completed',
        'interpretation_eligible': not failures,
        'decision_class': decision, 'decision_meaning': plan['decision_rules'][decision],
        'node_propagations': node_total, 'center_propagations': center_total,
        'inadmissible_components': inadmissible_total, 'bounded_scalar_violations': bounded_total,
        'admitted_material_shift_components': material_total,
        'numerical_checks': {'count': checks, 'passed': not failures, 'failures': failures},
        'decision_scales': plan['decision_scales'], 'components': components,
        'limits': [plan['node_rule']['not_implied'], plan['bounded_moment_check']['scope'],
                   plan['decision_scales']['meaning'],
                   'Later boundary incompatibility does not establish the earlier dominance-switch cause.'],
        'reducer_model_calls': 0, 'new_learner_updates': 0, 'truth_inputs': 0,
    }


def write_new_json(path, data, limit):
    encoded = (json.dumps(data, indent=2, allow_nan=False) + '\n').encode()
    require(len(encoded) <= limit, 'Derived JSON exceeds the remaining output budget')
    with path.open('xb') as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    return len(encoded)


def directory_bytes(directory):
    return sum(path.stat().st_size for path in directory.iterdir() if path.is_file())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--evidence-root', type=Path, required=True)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--source-revision', required=True)
    parser.add_argument('--executable-receipt', type=Path, required=True)
    args = parser.parse_args(argv)
    started = time.monotonic()
    root = args.root.resolve()
    output = argument_path(root, args.output_dir)
    evidence_root = argument_path(root, args.evidence_root)
    require(not output.is_relative_to(evidence_root) and not evidence_root.is_relative_to(output),
            'Output and restored input trees must be separate')
    original_primary = root / 'experiments/continuous_learning_validation_001/implementation/primary'
    require(not output.is_relative_to(original_primary), 'Cannot write into original primary evidence')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()  # Exclusive attempt reservation; never reuse or overwrite.
    records = {}
    errors = []
    phase = 'preflight'
    plan = executable = command = expected_observations = None
    worker = {'child_launched': False}
    result = None
    postchecks = []
    try:
        plan, executable, command, expected_observations = validate_inputs(args, root, records)
        require(own_peak_bytes() <= plan['resource_bounds']['supervisor_peak_RSS_bytes_max'], 'Supervisor RSS limit before launch')
        phase = 'probe'
        worker = supervise(command, output, plan['resource_bounds'])
        require(worker['exit_code'] == 0, 'Probe process failed with exit code ' + str(worker['exit_code']))
        require(not worker['resource_violations'], 'Probe resource violation: ' + ', '.join(worker['resource_violations']))
        phase = 'strict_parse_and_reduction'
        raw = strict_json((output / 'raw_probe.json').read_bytes())
        result = reduce_probe(raw, plan, expected_observations)
        require(result['interpretation_eligible'], 'Frozen numerical reconstruction checks failed')
    except BaseException as error:
        errors.append({'phase': phase, 'type': type(error).__name__, 'message': str(error)})
    finally:
        for path, before in records.items():
            try:
                after = digest(Path(path))
                unchanged = after == {key: before[key] for key in ('bytes', 'sha256')}
                postchecks.append({'path': path, 'unchanged': unchanged, **after})
                if not unchanged:
                    errors.append({'phase': 'posthash', 'message': 'Bound input changed: ' + before['label']})
            except BaseException as error:
                postchecks.append({'path': path, 'unchanged': False, 'error': str(error)})
                errors.append({'phase': 'posthash', 'message': 'Cannot verify bound input: ' + before['label']})
    bounds = plan['resource_bounds'] if plan else {'total_derived_output_bytes_max': 12582912, 'supervisor_peak_RSS_bytes_max': 268435456}
    if own_peak_bytes() > bounds['supervisor_peak_RSS_bytes_max']:
        errors.append({'phase': 'finalization', 'message': 'Supervisor peak RSS exceeds frozen bound'})
    if result is None:
        result = {'schema': 'mumble_conditional_belief_probe_reduction_v1', 'status': 'not_reduced', 'interpretation_eligible': False}
    if errors:
        result['interpretation_eligible'] = False
        result['execution_errors'] = errors
    result['source_revision'] = args.source_revision
    result['plan_sha256'] = records.get(str(root / PLAN), {}).get('sha256')
    remaining = bounds['total_derived_output_bytes_max'] - directory_bytes(output)
    write_new_json(output / 'result.json', result, max(0, remaining - 262144))
    artifacts = [{ 'path': path.name, **digest(path)} for path in sorted(output.iterdir()) if path.is_file()]
    before_receipt = directory_bytes(output)
    receipt = {
        'schema': 'mumble_conditional_belief_probe_execution_v1',
        'status': 'failed' if errors else 'completed', 'errors': errors,
        'source_revision': args.source_revision,
        'plan_sha256': result['plan_sha256'],
        'executable_receipt': str(argument_path(root, args.executable_receipt)),
        'command': command, 'probe': worker,
        'pre_execution_identities': list(records.values()),
        'post_execution_identities': postchecks,
        'all_bound_inputs_unchanged': bool(records) and all(row['unchanged'] for row in postchecks),
        'artifacts': artifacts, 'derived_bytes_before_receipt': before_receipt,
        'closed_derived_bytes': 0,
        'supervisor': {
            'own_peak_RSS_bytes': own_peak_bytes(),
            'RSS_method': 'getrusage(RUSAGE_SELF), not RUSAGE_CHILDREN; sampled after validation, worker capture, reduction and posthash',
            'wall_s_before_receipt': time.monotonic() - started,
            'peak_RSS_limit_bytes': bounds['supervisor_peak_RSS_bytes_max'],
        },
        'new_learner_ingests': 0, 'new_source_generations': 0, 'old_scorer_runs': 0,
        'canonical_probe_invocations': int(worker['child_launched']),
        'automatic_retries': 0, 'original_inputs_written': False,
    }
    # Resolve self-inclusive output accounting before the only receipt write.
    for _ in range(8):
        measured = before_receipt + len((json.dumps(receipt, indent=2, allow_nan=False) + '\n').encode())
        if receipt['closed_derived_bytes'] == measured:
            break
        receipt['closed_derived_bytes'] = measured
    require(receipt['closed_derived_bytes'] <= bounds['total_derived_output_bytes_max'], 'Total derived output budget exceeded')
    write_new_json(output / 'receipt.json', receipt, bounds['total_derived_output_bytes_max'] - before_receipt)
    print(json.dumps({'status': receipt['status'], 'child_launched': worker['child_launched'],
                      'output_dir': str(output), 'decision_class': result.get('decision_class'),
                      'closed_derived_bytes': directory_bytes(output)}, allow_nan=False))
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
