"""Eight-case coordinate x normalized-fitting factorial; no fresh inference."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time
import unittest
import numpy as np
from experiments.region_compression_001 import compare as base
from experiments.region_compression_001.test_regions import Controls as OriginalControls
from experiments.voltage_coordinates_001.test_coordinates import Controls as VoltageControls
from experiments.rc_response_coordinates_001.test_coordinates import Controls as RCControls
from experiments.rc_response_coordinates_001 import probes
from experiments.partition_coordinate_fit_001 import coordinates as c
from experiments.partition_coordinate_fit_001.test_partition import Controls

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


class BudgetExceeded(RuntimeError):
    pass


def norm_stats(z):
    return dict(count=len(z), min_logZ_by_coordinate=np.min(z, axis=0),
                mean_removed_mass_by_coordinate=np.mean(-np.expm1(z), axis=0),
                max_removed_mass_by_coordinate=np.max(-np.expm1(z), axis=0))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default=str(HERE/'attempt001'))
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    plan = json.loads((HERE/'plan.json').read_text())
    baseline_path = ROOT/plan['baseline']
    baseline = json.loads(baseline_path.read_text())
    bindings = json.loads((baseline_path.parent/'reservation.json').read_text())['identities']
    bindings.update(json.loads((baseline_path.parent.parent/'verification.json').read_text())['artifacts'])
    for path, expected in bindings.items():
        c.old.require(base.identity(ROOT/path) == expected, 'previous artifact changed '+path)
    for path in [HERE/'plan.json', HERE/'derivation.md', HERE/'coordinates.py', HERE/'fitting.py', HERE/'test_partition.py', Path(__file__)]:
        bindings[str(path.relative_to(ROOT))] = base.identity(path)
    base.write(out/'reservation.json', dict(status='before_controls_and_battery_evaluation', plan=plan, identities=bindings,
        command=sys.argv, revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        branch=subprocess.check_output(['git', 'branch', '--show-current'], text=True).strip(),
        python=sys.version, numpy=np.__version__,
        thread_environment={k: os.getenv(k) for k in ['OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS']}))
    suite = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(group)
                                for group in [OriginalControls, VoltageControls, RCControls, Controls]])
    with (out/'controls.txt').open('x') as stream:
        tested = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    base.write(out/'controls.json', dict(tests_run=tested.testsRun, failures=len(tested.failures), errors=len(tested.errors), passed=tested.wasSuccessful()))
    if not tested.wasSuccessful():
        raise RuntimeError('controls failed; no battery evaluation')
    work = {key: 0 for key in plan['work_caps']}

    def charge(key, amount):
        if work[key]+amount > plan['work_caps'][key]:
            raise BudgetExceeded('work cap '+key)
        work[key] += amount

    probe_definitions = probes.definitions(plan['predictive_horizons_s'])
    probe_steps = sum(len(p['steps']) for p in probe_definitions)
    started = time.process_time()
    cases = []
    for prefix in plan['prefixes']:
        ref = baseline['references'][str(prefix)]['inherited']
        def load(name):
            with np.load(ROOT/name, allow_pickle=False) as archive:
                return archive['projected'][:, :16].copy()
        train = np.concatenate([load(path) for path in ref['train']])
        held = [load(path) for path in ref['heldout']]
        pooled = np.concatenate(held)
        previous = next(row for row in baseline['cases'] if row['prefix'] == prefix and row['K'] == 2
                        and row['arm'] == 'fixed_partition_gaussian_mixture' and row['frame'] == plan['response_frame'])
        for chart in plan['coordinates']:
            for method in plan['fit_methods']:
                charge('cases', 1)
                tag = f'prefix{prefix}_{chart}_{method}'
                case = dict(prefix=prefix, chart=chart, method=method, components=2)
                begin = time.process_time()
                try:
                    def progress(region, j, diag):
                        if method == 'bounded_likelihood' and (j == 15 or diag['status'] != 'first_order_stationary'):
                            print(tag, 'component', region, 'coordinate', j, diag['status'], 'gradient', diag['final_gradient_infinity'], flush=True)
                    msg = c.fit(train, chart, method, plan['optimizer'],
                                charge=lambda rows: charge('fit_objective_sample_rows', rows), progress=progress)
                    fits = [fit for region in msg.diagnostics for fit in region['conditionals']]
                    case.update(build_CPU_s=time.process_time()-begin, retained_numeric_B=msg.numeric_bytes,
                        construction_two_arrays_lower_B=train.nbytes*2, complete_target_SRAM_B=None,
                        component_fits=msg.diagnostics, fit_status_counts=dict(Counter(fit['status'] for fit in fits)),
                        max_final_gradient_infinity=max(fit['final_gradient_infinity'] for fit in fits),
                        all_bounded_fits_first_order_stationary=(method == 'bounded_likelihood' and all(fit['status']=='first_order_stationary' for fit in fits)))
                    payload = dict(schema='partition_joint_message_v1', posterior=msg.export(),
                        source_id=ref['source_id'], owns_initial_prior=ref['owns_initial_prior'],
                        observation_interval=ref['observation_interval'], transition_interval=ref['transition_interval'],
                        physical_support_low=c.old.LOW.tolist(), physical_support_high=c.old.HIGH.tolist(),
                        organization='fixed-membership two-component conditional mixture; all16 remain joint',
                        transport_views='deterministic derived coordinates; no additional evidence or independent uncertainty',
                        status='offline_approximation_not_qualified_for_causal_update')
                    base.write(out/(tag+'_message.json'), payload)
                    scores, normalizers = [], []
                    before = time.process_time()
                    for pop in held:
                        charge('heldout_density_points', len(pop))
                        logs = []
                        for i in range(0, len(pop), 512):
                            values, logz = msg.logpdf_details(pop[i:i+512])
                            logs.append(values)
                            normalizers.append(logz)
                        values = np.concatenate(logs)
                        c.old.require(np.isfinite(values).all(), 'nonfinite heldout density')
                        scores.append(float(-values.mean()))
                    if chart == 'current' and method == 'moment_projection':
                        np.testing.assert_allclose(scores, previous['heldout_mean_negative_log_density_by_population'], rtol=0, atol=2e-8)
                    case.update(heldout_mean_negative_log_density_by_population=scores,
                        heldout_mean_negative_log_density=float(np.mean(scores)),
                        heldout_improvement_from_saved_current_by_population=np.array(previous['heldout_mean_negative_log_density_by_population'])-scores,
                        heldout_density_CPU_s=time.process_time()-before,
                        heldout_component_normalizers=norm_stats(np.concatenate(normalizers)))
                    charge('inverse_OCV_sample_iterations', plan['draws_per_case']*52)
                    draws, info = msg.draw(plan['draws_per_case'], plan['seed_base']+work['cases'])
                    charge('predictive_sample_steps', len(draws)*probe_steps)
                    case.update(draw_moments=base.moments(draws), draw_heldout_difference=base.difference(draws, pooled),
                        marginals=dict(SOC=base.scalar_stats(draws[:, 11]), Q_Ah=base.scalar_stats(np.exp(draws[:, 5])), R0_ohm=base.scalar_stats(draws[:, 6])),
                        probes=probes.assess(draws, probe_definitions),
                        generated_normalizers=norm_stats(info.pop('log_normalizers')), sampler_work=info)
                    charge('serialization_density_points', 32)
                    restored = c.Message.restore(payload['posterior'])
                    np.testing.assert_array_equal(msg.logpdf(pooled[:16]), restored.logpdf(pooled[:16]))
                    case['status'] = 'offline_comparison_completed'
                except (c.old.Unavailable, BudgetExceeded, np.linalg.LinAlgError, FloatingPointError) as error:
                    case.update(status='unavailable', reason=str(error))
                case['CPU_s'] = time.process_time()-begin
                cases.append(base.plain(case))
                base.write(out/(tag+'.json'), base.plain(case))
                print(tag, case['status'], flush=True)
    base.write(out/'result.json', dict(schema='partition_coordinate_fit_result_v1', status='factorial_comparison_completed',
        cases=cases, references=baseline['references'], work=work, CPU_s=time.process_time()-started,
        process_peak_RSS_B=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        probe_definitions=probe_definitions, truth_reads=0, new_particle_inference=False,
        transport_scope='Exact deterministic views qualified; no new history storage or aging transition',
        component_objective_scope='Fixed construction membership; no mixture EM/global optimum claim',
        rolling_solver_changed=False, coverage_validated=False, deployment_qualified=False, four_hour_gate_passed=False))


if __name__ == '__main__':
    main()
