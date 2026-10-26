"""Fabricated Python-only checks; never launches the C reference or learner."""
import contextlib
import hashlib
import io
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import time

sys.dont_write_bytecode = True
ROOT = Path('/workspace/scratch/d8e043c88fda/mumble-repo')
sys.path.insert(0, str(ROOT / 'tools'))
import run_historical_likelihood_control as driver

passed = []
source_hash = hashlib.sha256((ROOT / driver.DRIVER).read_bytes()).hexdigest()
with tempfile.TemporaryDirectory(prefix='historical-driver-fabricated-') as temporary:
    top = Path(temporary)
    original_count = driver.PREFIX_RECORDS
    values = [
        (0., -0., 3.7), (1 / 35, .06, 3.6000000000000005),
        (1 / 35, -.06, 3.5000000000000004),
        (math.nextafter(.1, 1.), math.nextafter(.25, 0.), math.nextafter(4., 0.)),
        (.5, -math.nextafter(.25, 0.), -0.), (1., 0., math.nextafter(3., 4.)),
    ]
    observations = top / 'fabricated-observations.bin'
    original = b''.join(struct.pack('<Qddd', index, *row) for index, row in enumerate(values))
    observations.write_bytes(original)
    driver.PREFIX_RECORDS = len(values)
    conversion = driver.convert_prefix(observations, top / 'prefix.csv', time.monotonic())
    assert conversion['bitwise_roundtrip_passed']
    assert conversion['prefix_records'] == len(values)
    assert conversion['binary_prefix_sha256'] == hashlib.sha256(original).hexdigest()
    assert observations.read_bytes() == original
    driver.PREFIX_RECORDS = original_count
    passed.append('all_fabricated_CSV_records_roundtrip_including_signed_zero')

    witness = top / 'fabricated-witness.jsonl'
    query = {'schema': 'mumble_continuous_query_v1', 'event': 'query',
             'next_index': original_count,
             'aggregate': {'next_index': original_count, 'point_available': 1,
                           'capacity_available': 1, 'capacity_Ah': .061, 'current_soc': .42},
             'components': [{'capacity_Ah': .09, 'current_soc': .8}]}
    witness.write_text(json.dumps(query) + '\n')
    targets = driver.extract_targets(witness)
    assert targets['capacity_Ah'] == .061 and targets['current_soc'] == .42
    witness.write_text((json.dumps(query) + '\n') * 2)
    try:
        driver.extract_targets(witness)
    except driver.supervisor.ProbeError:
        pass
    else:
        raise AssertionError('duplicate exact-index witness accepted')
    passed.append('exact_aggregate_targets_and_duplicate_witness_rejection')

    theta = [math.log(.05), math.log(.5), math.log(5.), math.log(150.), math.log(300.), .68, math.log(.06)]
    free = driver.fit_command(Path('/unused/fabricated-binary'), top / 'prefix.csv', 'free', targets)
    fixed_q = driver.fit_command(Path('/unused/fabricated-binary'), top / 'prefix.csv', 'fixed_recursive_Q', targets, theta)
    fixed_z = driver.fit_command(Path('/unused/fabricated-binary'), top / 'prefix.csv', 'fixed_recursive_SOC', targets, theta)
    assert '--initial' not in free and '--fixed' not in free and '--fixed-current-soc' not in free
    position = fixed_q.index('--fixed')
    assert fixed_q[position + 1:] == ['6', format(math.log(.061), '.17g')]
    assert [float(x) for x in fixed_q[fixed_q.index('--initial') + 1].split(',')] == theta
    assert fixed_z[-2:] == ['--fixed-current-soc', format(.42, '.17g')]
    assert all(command[command.index('--starts') + 1] == '3' for command in (free, fixed_q, fixed_z))
    passed.append('free_and_both_constraint_argv_wiring')

    raw = {'case_id': 'historical_likelihood_control_001/free', 'method': 'full', 'modes': 3,
           'sigma_V': .001, 'ocv_kind': 'illustrative_known_curve', 'ocv_table_rows': 0,
           'has_initial': False, 'fixed_mask': 0, 'fixed_alpha_mask': 0, 'has_current_soc': False,
           'fixed_current_soc': None, 'starts': 3, 'samples': original_count,
           'features': original_count, 'blocks': 0, 'basis_bytes': 0,
           'data_bytes': original_count * 24, 'payload_bytes': original_count * 8,
           'workspace_bytes': original_count * 640, 'joint_normal_dimension': 16,
           'theta': theta, 'alpha': [.1, .1, .1, .1, .024, 0., 0., 0., 0.],
           'coordinate_scales': [1.] * 16,
           'joint_normal': [float(i == j) for i in range(16) for j in range(16)],
           'joint_normal_semantics': 'Scaled likelihood Jacobian Gram matrix before damping and Schur reduction; not a posterior',
           'joint_normal_coordinates': 'Scaled theta followed by scaled alpha; packed row-major',
           'objective': original_count / 2, 'objective_full': original_count / 2, 'voltage_rmse': .001,
           'elapsed_cpu_s': .1, 'projected_gradient': .01, 'max_inner_kkt': 1e-12,
           'basis_seconds': 0., 'basis_max_orthogonality': 0., 'max_discarded_column_norm': 0.,
           'elapsed_physical_s': 7200., 'charge_Ah': .006,
           'status': 1, 'termination_reason': 2, 'iterations': 360, 'evaluations': 400,
           'converged_starts': 0, 'active_linear_constraints': 0, 'active_outer_bounds': 0,
           'retained_bytes': original_count * 672 + 1000, 'setup_peak_bytes': original_count * 672 + 1000,
           'unexcited_theta_mask': 0, 'assessment': {'diagnostic_only': True, 'coverage_certificate': False}}
    result = driver.validate_fit(raw, 'free', targets)
    assert result['optimizer_status'] == 1 and not result['unrestricted_local_precision_computed']
    passed.append('finite_nonconverged_output_retained_as_candidate')
    raw['joint_normal'][0] = None
    try:
        driver.validate_fit(raw, 'free', targets)
    except driver.supervisor.ProbeError:
        pass
    else:
        raise AssertionError('null essential Gram value accepted')
    passed.append('malformed_essential_numeric_output_rejected')

    fake_root = top / 'fake-repository'
    fake_root.mkdir()
    output = top / 'failed-attempt'
    args = ['--root', str(fake_root), '--evidence-root', str(top / 'evidence'),
            '--binary', str(top / 'absent-binary'), '--output-dir', str(output),
            '--scratch-dir', str(top / 'scratch'), '--source-revision', 'a' * 40,
            '--executable-receipt', str(top / 'absent-receipt.json')]
    with contextlib.redirect_stdout(io.StringIO()):
        assert driver.main(args) == 1
    receipt_bytes = (output / 'receipt.json').read_bytes()
    receipt = json.loads(receipt_bytes)
    assert receipt['status'] == 'failed'
    assert receipt['fit_invocations_attempted'] == receipt['observed_children_launched'] == 0
    assert receipt['closed_output_bytes'] == driver.tree_bytes(output)
    try:
        driver.main(args)
    except FileExistsError:
        pass
    else:
        raise AssertionError('existing output directory reused')
    assert (output / 'receipt.json').read_bytes() == receipt_bytes
    passed.append('prelaunch_failure_receipt_exact_bytes_and_no_overwrite')

record = {'schema': 'mumble_historical_driver_fabricated_checks_v1',
          'driver_sha256': source_hash,
          'supervisor_sha256': hashlib.sha256((ROOT / driver.SUPERVISOR).read_bytes()).hexdigest(),
          'fixture_script': str(Path(__file__).resolve()),
          'fixture_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'command': [sys.executable, str(Path(__file__).resolve())],
          'passed': passed, 'failed': [], 'canonical_input_reads': 0,
          'optimizer_calls': 0, 'learner_calls': 0, 'child_processes_launched': 0,
          'limitations': 'Python-only fabricated conversion, argv, parse and prelaunch-failure checks. No canonical target extraction, canonical CSV conversion, C fit or new C qualification.'}
Path('/tmp/mumble-historical-driver-checks.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
