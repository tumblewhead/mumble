#!/usr/bin/env python3
"""Audit design arithmetic and source identity; never generate or fit a trace."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def frac(value) -> Fraction:
    return Fraction(str(value))


def source_constants(path: Path):
    """Evaluate only the fixed current-profile function and literal cell table."""
    tree = ast.parse(path.read_text())
    profile = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'profile')
    cells = next(n.value for n in tree.body if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == 'CELLS' for t in n.targets))
    namespace = {'Fraction': Fraction}
    module = ast.fix_missing_locations(ast.Module(body=[profile], type_ignores=[]))
    exec(compile(module, str(path), 'exec'), namespace)
    blocks = [(frac(i), d, label) for i, d, label in namespace['profile']()]
    return blocks, ast.literal_eval(cells)


def build_events(plan, inherited):
    events = []
    next_index = 0
    phase_rows = []
    for phase in plan['B_continuous_4h']['phases']:
        assert phase['start_index'] == next_index
        assert phase['start_index'] == 35 * phase['start_s']
        assert phase['end_index'] == 35 * phase['end_s']
        if phase['kind'] == 'inherited_current_protocol':
            blocks = inherited
        elif phase['kind'] == 'constant':
            blocks = [(frac(phase['current_A']), frac(phase['end_s'] - phase['start_s']), phase['id'])]
        else:
            assert phase['kind'] == 'repeat'
            blocks = [(frac(b['current_A']), frac(b['duration_s']), phase['id'])
                      for _ in range(phase['repeats']) for b in phase['pattern']]
        qpos = qneg = Fraction()
        for current, duration, label in blocks:
            assert duration > 0 and (duration * 35).denominator == 1
            assert abs(current) <= frac(plan['frozen_estimator']['config']['max_abs_current_A'])
            count = int(duration * 35)
            events.append((next_index, next_index + count, current, duration, label, phase['id']))
            next_index += count
            qpos += max(current, 0) * duration / 3600
            qneg += max(-current, 0) * duration / 3600
        assert next_index == phase['end_index']
        phase_rows.append({'id': phase['id'], 'start_s': phase['start_s'], 'end_s': phase['end_s'],
                           'samples': phase['end_index'] - phase['start_index'],
                           'signed_charge_Ah_exact': str(qpos - qneg),
                           'positive_charge_Ah_exact': str(qpos),
                           'negative_magnitude_charge_Ah_exact': str(qneg),
                           'absolute_charge_Ah_exact': str(qpos + qneg)})
    assert next_index == plan['B_continuous_4h']['samples'] == 504000
    return events, phase_rows


def full_query_indices(events, begin, end, checkpoints):
    q = {begin, end}
    q.update(range(((begin + 34) // 35) * 35, end + 1, 35))
    for a, b, *_ in events:
        q.update(n for n in (a, a + 1, b) if begin <= n <= end)
    q.update(n for n in checkpoints if begin <= n <= end)
    return q


def audit():
    plan_path = ROOT / 'plans/continuous_learning_validation_001.json'
    data = plan_path.read_bytes()
    p = json.loads(data)
    checks = []

    def checked(label, condition):
        if not condition:
            raise AssertionError(label)
        checks.append(label)

    checked('design_only_zero_primary', p['scope']['no_primary_now'] is True)
    checked('capacity_has_no_startup_deadline', p['scope']['capacity_startup_deadline_s'] is None)
    checked('all16_coordinates_retained', len(p['frozen_estimator']['coordinate_order']) == 16)
    sources = []
    for pin in p['frozen_estimator']['git_blobs']:
        body = (ROOT / pin['path']).read_bytes()
        checked('unchanged:' + pin['path'], git_blob(body) == pin['sha'] and len(body) == pin['size'])
        sources.append({'path': pin['path'], 'git_blob': pin['sha'], 'sha256': hashlib.sha256(body).hexdigest()})
    gen_path = ROOT / p['physical_and_noise_model']['truth_source']['path']
    checked('inherited_generator_source_pinned', git_blob(gen_path.read_bytes()) == p['physical_and_noise_model']['truth_source']['git_blob'])
    inherited, cells = source_constants(gen_path)
    checked('inherited106_blocks2100_seconds', len(inherited) == 106 and sum((d for _, d, _ in inherited), Fraction()) == 2100)
    events, phase_rows = build_events(p, inherited)
    checked('phase_and_sample_contiguity', all(events[j][1] == events[j + 1][0] for j in range(len(events) - 1)))

    a = p['A_second_cell_lifecycle']
    b = p['B_continuous_4h']
    budgets = p['logging_and_budgets']
    adel = sum(arm['end_index'] - arm['start_index'] for arm in a['arms'])
    checked('A157500_deliveries', adel == a['total_input_deliveries'] == 157500)
    checked('arm_delivery_counts', all(arm['input_deliveries'] == arm['end_index'] - arm['start_index'] for arm in a['arms']))
    checked('primary661500_deliveries', adel + b['samples'] == budgets['max_primary_input_deliveries'] == 661500)
    checked('unique577500_observations', a['unique_observations'] + b['samples'] == budgets['max_unique_physical_observations'] == 577500)
    checked('generator619500_evaluations', 73500 + 42000 + b['samples'] == budgets['generator_evaluations_max'])
    checked('four_primary_processes', len(a['arms']) + b['processes'] == budgets['max_primary_processes'] == 4)
    checked('wall_time_cap3600_seconds', sum(arm['timeout_s'] for arm in a['arms']) + b['timeout_s'] == budgets['max_primary_wall_s'] == 3600)
    record = budgets['per_sample_record']
    checked('80_byte_sample_record', 8 + 7 * 8 + 8 + 4 + 4 == record['bytes'])
    checked('scalar_payload52920000_bytes', record['bytes'] * budgets['max_primary_input_deliveries'] == record['max_payload_bytes'] == 52920000)
    qcounts = {}
    for arm in a['arms']:
        qcounts[arm['id']] = len(full_query_indices(events[:106], arm['start_index'], arm['end_index'], arm['checkpoint_next_indices']))
    qcounts['B_continuous'] = len(full_query_indices(events, 0, b['samples'], [35 * t for t in b['checkpoint_times_s']]))
    checked('full_query_cap', sum(qcounts.values()) + 1 <= budgets['max_full_query_records'])
    checked('output_cap_has_room_for_declared_record_caps', record['max_payload_bytes'] + budgets['max_full_query_records'] * budgets['max_full_query_record_bytes'] < budgets['max_output_bytes'])
    checked('target_memory_is_unqualified', budgets['estimator_memory']['owned_bytes_ceiling'] + budgets['estimator_memory']['target_reserve_bytes_unmeasured'] == budgets['estimator_memory']['proposed_complete_target_bytes'])
    checked('target208_byte_headroom', budgets['estimator_memory']['complete_subsystem_limit_bytes'] - budgets['estimator_memory']['proposed_complete_target_bytes'] == budgets['estimator_memory']['headroom_bytes'] == 208)

    domains = {}
    for cell, subset in [('cell_a', events[:106]), ('cell_b', events)]:
        z0, capacity = frac(cells[cell]['z0']), frac(cells[cell]['Q_Ah'])
        q = Fraction()
        zs = [z0]
        qpos = qneg = Fraction()
        for _, _, current, duration, *_ in subset:
            q += current * duration / 3600
            qpos += max(current, 0) * duration / 3600
            qneg += max(-current, 0) * duration / 3600
            zs.append(z0 - q / capacity)
        checked(cell + '_analytic_SOC_inside_domain', min(zs) >= 0 and max(zs) <= 1)
        domains[cell] = {'scope': 'Exact rational prescribed-input SOC at event boundaries; linear within each constant-current event. This is a generator-domain audit, not a learner run or voltage trajectory.',
                         'SOC_min': float(min(zs)), 'SOC_max': float(max(zs)), 'SOC_final': float(zs[-1]),
                         'signed_charge_Ah_exact': str(q), 'signed_charge_Ah': float(q),
                         'positive_charge_Ah_exact': str(qpos), 'negative_magnitude_charge_Ah_exact': str(qneg),
                         'absolute_charge_Ah_exact': str(qpos + qneg)}
    return {'schema': 'mumble_continuous_learning_design_verification_v1',
            'status': 'passed_design_arithmetic_and_source_identity_only',
            'basis_revision': p['basis_revision'], 'contract_sha256': hashlib.sha256(data).hexdigest(),
            'audit_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'checks_passed': len(checks), 'checks': checks, 'frozen_estimator_sources': sources,
            'B_event_blocks': len(events), 'phase_charge': phase_rows, 'analytic_generator_domain': domains,
            'full_query_count_without_failure': qcounts, 'full_query_count_with_one_failure_max': sum(qcounts.values()) + 1,
            'execution': {'primary_runs': 0, 'learner_runs': 0, 'optimizer_calls': 0, 'voltage_trajectory_generations': 0, 'noise_draws': 0, 'completed_study_reruns': 0},
            'not_established': ['Executable harness preflight', 'New accuracy or uncertainty outcomes', 'Actual runtime/RSS/target memory', 'Generalization or indefinite stability']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='New receipt path; existing files are never overwritten.')
    args = parser.parse_args()
    result = audit()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x') as stream:
            json.dump(result, stream, indent=2)
            stream.write('\n')
    print(json.dumps({'status': result['status'], 'checks_passed': result['checks_passed'],
                      'B_event_blocks': result['B_event_blocks'],
                      'full_query_count_with_one_failure_max': result['full_query_count_with_one_failure_max'],
                      'analytic_generator_domain': result['analytic_generator_domain'],
                      'execution': result['execution']}, indent=2))


if __name__ == '__main__':
    main()
