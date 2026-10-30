"""Frozen offline RC-frame comparison; saved voltage baseline extended only."""
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
from experiments.region_compression_001.test_regions import Controls as OriginalControls
from experiments.voltage_coordinates_001.test_coordinates import Controls as VoltageControls
from experiments.rc_response_coordinates_001 import coordinates as c
from experiments.rc_response_coordinates_001 import probes
from experiments.rc_response_coordinates_001.test_coordinates import Controls

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def norm_stats(z):
    return dict(count=len(z), min_logZ_by_step=np.min(z, axis=0),
        max_removed_mass_by_step=np.max(-np.expm1(z), axis=0), mean_removed_mass_by_step=np.mean(-np.expm1(z), axis=0))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default=str(HERE/'attempt001'))
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    plan = json.loads((HERE/'plan.json').read_text())
    baseline_path = ROOT/plan['baseline']
    baseline = json.loads(baseline_path.read_text())
    prior_bindings = json.loads((baseline_path.parent/'reservation.json').read_text())['identities']
    prior_bindings.update(json.loads((baseline_path.parent.parent/'verification.json').read_text())['artifacts'])
    for path, expected in prior_bindings.items():
        c.old.require(base.identity(ROOT/path) == expected, 'previous artifact changed: '+path)
    bindings = dict(prior_bindings)
    for path in [HERE/'plan.json', HERE/'derivation.md', HERE/'coordinates.py', HERE/'probes.py', HERE/'test_coordinates.py', Path(__file__)]:
        bindings[str(path.relative_to(ROOT))] = base.identity(path)
    base.write(out/'reservation.json', dict(status='before_controls_and_evaluation', plan=plan, identities=bindings,
        command=sys.argv, revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        branch=subprocess.check_output(['git', 'branch', '--show-current'], text=True).strip(),
        python=sys.version, numpy=np.__version__,
        thread_environment={k: os.getenv(k) for k in ['OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS']}))
    suite = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(group)
                                for group in [OriginalControls, VoltageControls, Controls]])
    with (out/'controls.txt').open('x') as stream:
        test = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    base.write(out/'controls.json', dict(tests_run=test.testsRun, failures=len(test.failures), errors=len(test.errors), passed=test.wasSuccessful()))
    if not test.wasSuccessful():
        raise RuntimeError('controls failed; no candidate evaluation')
    work = {key: 0 for key in plan['work_caps']}

    def charge(key, n):
        work[key] += n
        c.old.require(work[key] <= plan['work_caps'][key], 'work cap '+key)

    definitions = probes.definitions(plan['probe_horizons_s'])
    steps = sum(len(p['steps']) for p in definitions)

    def assess(x):
        charge('predictive_sample_steps', len(x)*steps)
        return probes.assess(x, definitions)

    started = time.process_time()
    references, baseline_extended, cases = {}, [], []
    for prefix, reference in baseline['references'].items():
        def load(path):
            with np.load(ROOT/path, allow_pickle=False) as data:
                return data['projected'][:, :16].copy()
        train = np.concatenate([load(p) for p in reference['train']])
        held = [load(p) for p in reference['heldout']]
        pooled = np.concatenate(held)
        references[prefix] = dict(inherited=reference, probes=assess(pooled),
                                  population_probes=[assess(pop) for pop in held])
        for old_index, old_case in enumerate(baseline['cases']):
            if old_case['prefix'] != int(prefix):
                continue
            tag = f"prefix{prefix}_K{old_case['K']}_{old_case['arm']}"
            payload = json.loads((baseline_path.parent/(tag+'.json')).read_text())
            old_message = c.v.Message.restore(payload['posterior'])
            draw, _ = old_message.draw(16384, 928001+old_index+1)
            extended = dict(prefix=int(prefix), K=old_case['K'], arm=old_case['arm'], probes=assess(draw),
                            original_draw_seed=928001+old_index+1, refitted=False)
            # Preserve exact1s baseline draw identity through its output moments.
            np.testing.assert_allclose(extended['probes']['load_1s']['voltage_V']['SD'], old_case['physical_outputs']['load_1s']['voltage_V']['SD'], rtol=0, atol=1e-15)
            baseline_extended.append(extended)
        for k in plan['regions']:
            for arm in plan['arms']:
                previous = next(z for z in baseline['cases'] if z['prefix'] == int(prefix) and z['K'] == k and z['arm'] == arm)
                for frame in plan['frames']:
                    charge('cases', 1)
                    begin = time.process_time()
                    case = dict(prefix=int(prefix), K=k, arm=arm, frame=frame)
                    try:
                        if arm.startswith('adaptive'):
                            charge('placement_sample_visits', 16*len(train))
                        msg = c.fit(train, k, arm, frame)
                        case.update(build_CPU_s=time.process_time()-begin, retained_numeric_B=msg.numeric_bytes,
                            frame_values_s=msg.frame, regions=msg.diagnostics, edges_normalized_logQ=msg.edges,
                            construction_array_lower_B=train.nbytes*2+msg.numeric_bytes, complete_target_SRAM_B=None)
                        c.old.require(msg.numeric_bytes == previous['retained_numeric_B']+24, 'unexpected payload')
                        np.testing.assert_array_equal(msg.edges, previous['edges_normalized_logQ'])
                        tag = f'prefix{prefix}_K{k}_{arm}_{frame}'
                        payload = dict(schema='rc_response_message_v1', posterior=msg.export(),
                            source_id=reference['source_id'], owns_initial_prior=reference['owns_initial_prior'],
                            observation_interval=reference['observation_interval'], transition_interval=reference['transition_interval'],
                            physical_support_low=c.old.LOW.tolist(), physical_support_high=c.old.HIGH.tolist(),
                            chain=['F1', 'F2', 'F3', 'G1', 'G2', 'G3', 'boundary_rest_voltage'],
                            status='offline_approximation_not_qualified_for_causal_update')
                        base.write(out/(tag+'.json'), payload)
                        scores, normalizers = [], []
                        before = time.process_time()
                        for pop in held:
                            charge('heldout_density_points', len(pop))
                            logs = []
                            for i in range(0, len(pop), 512):
                                values, norms = msg.logpdf_details(pop[i:i+512])
                                logs.append(values)
                                normalizers.append(norms)
                            values = np.concatenate(logs)
                            c.old.require(np.isfinite(values).all(), 'nonfinite density')
                            scores.append(float(-values.mean()))
                        case.update(heldout_mean_negative_log_density_by_population=scores,
                            heldout_mean_negative_log_density=float(np.mean(scores)),
                            heldout_improvement_from_voltage_by_population=np.array(previous['heldout_mean_negative_log_density_by_population'])-scores,
                            heldout_density_CPU_s=time.process_time()-before,
                            heldout_component_normalizers=norm_stats(np.concatenate(normalizers)))
                        charge('inverse_OCV_sample_iterations', plan['draws_per_case']*52)
                        draw, info = msg.draw(plan['draws_per_case'], plan['draw_seed_base']+work['cases'])
                        case.update(draw_moments=base.moments(draw), draw_heldout_difference=base.difference(draw, pooled),
                            marginals=dict(SOC=base.scalar_stats(draw[:, 11]), Q_Ah=base.scalar_stats(np.exp(draw[:, 5])), R0_ohm=base.scalar_stats(draw[:, 6])),
                            probes=assess(draw), generated_normalizers=norm_stats(info.pop('log_normalizers')), sampler_work=info)
                        restored = c.Message.restore(payload['posterior'])
                        charge('serialization_density_points', 32)
                        np.testing.assert_array_equal(restored.logpdf(pooled[:16]), msg.logpdf(pooled[:16]))
                        case['status'] = 'offline_comparison_completed'
                    except (c.old.Unavailable, np.linalg.LinAlgError, FloatingPointError) as error:
                        case.update(status='unavailable', reason=str(error))
                    case['CPU_s'] = time.process_time()-begin
                    cases.append(base.plain(case))
                    base.write(out/f'case_{work["cases"]:02}.json', base.plain(case))
                    print(prefix, k, arm, frame, case['status'], flush=True)
    base.write(out/'result.json', dict(schema='rc_response_comparison_v1', status='bounded_comparison_completed',
        cases=cases, references=references, baseline_extended=baseline_extended,
        probe_definitions=definitions, work=work, CPU_s=time.process_time()-started,
        process_peak_RSS_B=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        baseline_extension_inverse_OCV_iterations=12*16384*52,
        work_scope='Candidate caps plus all predictive evaluations; baseline regeneration inverse work separately disclosed. Controls excluded.',
        truth_reads=0, new_particle_inference=False, causal_update_implemented=False, physical_aging_added=False,
        coverage_validated=False, deployment_qualified=False, four_hour_gate_passed=False))


if __name__ == '__main__':
    main()
