"""Matched coordinate comparison using the frozen earlier population split."""
import argparse
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
from experiments.region_compression_001.test_regions import Controls as OldControls
from experiments.voltage_coordinates_001 import coordinates as c
from experiments.voltage_coordinates_001.test_coordinates import Controls

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def norm_stats(values):
    return dict(count=len(values), min_logZ=float(np.min(values, initial=0)),
                max_removed_probability=float(np.max(-np.expm1(values), initial=0)),
                mean_removed_probability=float(np.mean(-np.expm1(values))) if len(values) else 0.)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default=str(HERE/'attempt001'))
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    plan = json.loads((HERE/'plan.json').read_text())
    baseline_path = ROOT/plan['baseline']
    baseline = json.loads(baseline_path.read_text())
    original = json.loads((baseline_path.parent/'reservation.json').read_text())
    old_verification = json.loads((baseline_path.parent.parent/'verification.json').read_text())
    bindings = dict(original['identities'])
    bindings.update(old_verification['artifacts'])
    for name, expected in bindings.items():
        c.require(base.identity(ROOT/name) == expected, 'prior artifact changed: '+name)
    for path in [HERE/'plan.json', HERE/'derivation.md', HERE/'coordinates.py', HERE/'test_coordinates.py', Path(__file__)]:
        bindings[str(path.relative_to(ROOT))] = base.identity(path)
    base.write(out/'reservation.json', dict(status='before_controls_and_candidate_evaluation',
        plan=plan, identities=bindings, command=sys.argv,
        revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        branch=subprocess.check_output(['git', 'branch', '--show-current'], text=True).strip(),
        python=sys.version, numpy=np.__version__,
        thread_environment={k: os.getenv(k) for k in ['OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS']}))
    suite = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(OldControls),
                                unittest.defaultTestLoader.loadTestsFromTestCase(Controls)])
    with (out/'controls.txt').open('x') as stream:
        tests = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    base.write(out/'controls.json', dict(tests_run=tests.testsRun, failures=len(tests.failures), errors=len(tests.errors), passed=tests.wasSuccessful()))
    if not tests.wasSuccessful():
        raise RuntimeError('controls failed; no candidate evaluation')
    counts = {key: 0 for key in plan['work_caps']}

    def charge(key, amount):
        counts[key] += amount
        c.require(counts[key] <= plan['work_caps'][key], 'work cap '+key)

    start = time.process_time()
    cases = []
    for prefix, ref in baseline['references'].items():
        def load(path):
            with np.load(ROOT/path, allow_pickle=False) as archive:
                return archive['projected'][:, :16].copy()
        train = np.concatenate([load(p) for p in ref['train']])
        populations = [load(p) for p in ref['heldout']]
        heldout = np.concatenate(populations)
        probes = original['plan']['stationary_predictive_probes']
        for k in plan['regions']:
            for arm in plan['arms']:
                charge('cases', 1)
                begin = time.process_time()
                case = dict(prefix=int(prefix), K=k, arm=arm, coordinate='physical_boundary_rest_voltage',
                            causal_update_implemented=False, deployment_qualified=False)
                previous = next(b for b in baseline['cases'] if b['prefix'] == int(prefix) and b['K'] == k and b['arm'] == arm)
                try:
                    if arm.startswith('adaptive'):
                        charge('placement_sample_visits', 16*len(train))
                    msg = c.fit(train, k, arm)
                    case.update(build_CPU_s=time.process_time()-begin,
                        regions=msg.diagnostics, retained_numeric_B=msg.numeric_bytes,
                        construction_known_array_lower_B=train.nbytes*2+msg.numeric_bytes,
                        construction_lower_scope='Input full16 and unit-coordinate arrays plus payload only; additional fit/library arrays excluded',
                        complete_target_SRAM_B=None, edges_normalized_logQ=msg.edges)
                    c.require(msg.numeric_bytes == previous['retained_numeric_B'], 'unmatched numeric payload')
                    np.testing.assert_array_equal(msg.edges, previous['edges_normalized_logQ'])
                    payload = dict(schema='voltage_conditioned_message_v1', posterior=msg.export(),
                        source_id=ref['source_id'], observation_interval=ref['observation_interval'],
                        transition_interval=ref['transition_interval'], owns_initial_prior=ref['owns_initial_prior'],
                        physical_support_low=c.old.LOW.tolist(), physical_support_high=c.old.HIGH.tolist(),
                        coordinate='w=OCV(SOC)-sum(v)-H*h', normalization='other15 marginal times physically truncated conditional voltage',
                        status='offline_approximation_not_qualified_for_causal_update')
                    base.write(out/f'prefix{prefix}_K{k}_{arm}.json', payload)
                    scores, norms = [], []
                    before = time.process_time()
                    for pop in populations:
                        charge('heldout_density_points', len(pop))
                        logs = []
                        for i in range(0, len(pop), 512):
                            values, normalizers = msg.logpdf_details(pop[i:i+512])
                            logs.append(values)
                            norms.append(normalizers)
                        logs = np.concatenate(logs)
                        c.require(np.isfinite(logs).all(), 'nonfinite heldout density')
                        scores.append(float(-logs.mean()))
                    case.update(heldout_mean_negative_log_density_by_population=scores,
                        heldout_mean_negative_log_density=float(np.mean(scores)),
                        heldout_score_improvement_by_population=(np.array(previous['heldout_mean_negative_log_density_by_population'])-scores).tolist(),
                        heldout_density_CPU_s=time.process_time()-before,
                        heldout_component_normalizers=norm_stats(np.concatenate(norms)))
                    charge('inverse_OCV_sample_iterations', plan['draws_per_case']*52)
                    draws, info = msg.draw(plan['draws_per_case'], plan['seed_base']+counts['cases'])
                    charge('predictive_sample_steps', len(draws)*sum(len(p['steps']) for p in probes))
                    case.update(draw_moments=base.moments(draws), draw_heldout_difference=base.difference(draws, heldout),
                        physical_outputs=base.physical_outputs(draws, probes),
                        generated_conditional_normalizers=norm_stats(info.pop('log_normalizers')), sampler_work=info,
                        status='offline_comparison_completed')
                    restored = c.Message.restore(payload['posterior'])
                    np.testing.assert_array_equal(msg.logpdf(heldout[:16]), restored.logpdf(heldout[:16]))
                except (c.old.Unavailable, np.linalg.LinAlgError, FloatingPointError) as e:
                    case.update(status='unavailable', reason=str(e))
                case['total_CPU_s'] = time.process_time()-begin
                cases.append(base.plain(case))
                base.write(out/f'case_{counts["cases"]:02}.json', base.plain(case))
                print(prefix, k, arm, case['status'], flush=True)
    base.write(out/'result.json', dict(schema='voltage_coordinate_result_v1', status='matched_offline_comparison_completed',
        cases=cases, references=baseline['references'], work=counts, CPU_s=time.process_time()-start,
        process_peak_RSS_B=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        baseline_identity=base.identity(baseline_path), truth_reads=0, new_particle_inference=False,
        rolling_solver_changed=False, physical_aging_added=False, coverage_validated=False,
        deployment_qualified=False, four_hour_gate_passed=False,
        limits=['Saved prefixes only0.229/0.914seconds; no long-term learning conclusion.',
                'Source populations passed finite moment checks, not full density or coverage qualification.',
                'Reuses previous heldout populations for a predefined coordinate hypothesis; not a new independent validation campaign.',
                'Projection then conditional support normalization is not a truncated-family maximum-likelihood fit.',
                'Small packed numeric payload does not account for causal update, subsystem, stack or library workspace.',
                'Probability atlas and scalar placement chain remain narrower than the original general proposals.']))


if __name__ == '__main__':
    main()
