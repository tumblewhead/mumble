"""Frozen offline representation comparison; no fresh particle inference."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time
import unittest
import numpy as np
from experiments.region_compression_001 import regions as r
from experiments.region_compression_001.test_regions import Controls

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def identity(path):
    return dict(bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def write(path, value):
    with path.open('x') as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write('\n')


def moments(x):
    delta = x-x.mean(axis=0)
    return dict(mean=x.mean(axis=0), covariance=delta.T@delta/len(x),
                quantiles_05_50_95=np.quantile(x, [.05, .5, .95], axis=0))


def plain(value):
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def difference(candidate, reference):
    a, b = moments(candidate), moments(reference)
    sd = np.sqrt(np.diag(b['covariance']))
    return dict(max_mean_difference_in_reference_SD=float(np.max(abs(a['mean']-b['mean'])/sd)),
                max_covariance_difference_standardized=float(np.max(abs(a['covariance']-b['covariance'])/np.outer(sd, sd))),
                max_quantile_difference_in_reference_SD=float(np.max(abs(a['quantiles_05_50_95']-b['quantiles_05_50_95'])/sd)))


def scalar_stats(x):
    return dict(mean=float(np.mean(x)), SD=float(np.std(x)), quantiles_05_50_95=np.quantile(x, [.05, .5, .95]).tolist())


def physical_outputs(x, probes):
    result = dict(SOC=scalar_stats(x[:, 11]), Q_Ah=scalar_stats(np.exp(x[:, 5])), R0_ohm=scalar_stats(x[:, 6]))
    for p in [dict(name='boundary_rest_voltage', steps=[]), *probes]:
        v, valid = r.stationary_probe(x, p['steps'])
        # No silent normalization after dropping invalid draws.
        result[p['name']] = dict(invalid_mass_fraction=float(1-valid.mean()),
                                voltage_V=scalar_stats(v) if valid.all() else None,
                                status='finite_all_draws_supported' if valid.all() else 'unavailable_support_loss')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default=str(HERE/'attempt001'))
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    plan = json.loads((HERE/'plan.json').read_text())
    source_paths = [HERE/'plan.json', HERE/'regions.py', HERE/'test_regions.py', HERE/'compare.py',
                    ROOT/'experiments/minimal_health_kernels_001/kernel.py',
                    ROOT/'experiments/joint_health_posterior_001/model.py',
                    ROOT/'experiments/joint_health_posterior_001/smc.py',
                    ROOT/'specifications/minimal_health_model_001/model.json']
    selected = {}
    for prefix, directory in plan['reference_directories'].items():
        directory = ROOT/directory
        paths = sorted(directory.glob('population_n4096_seed*.npz'))
        r.require(len(paths) == 4, 'expected four independent populations')
        selected[prefix] = paths
        source_paths.extend([directory/'result.json', *paths, *(p.with_suffix('.json') for p in paths)])
    write(out/'reservation.json', dict(status='before_controls_and_candidate_evaluation', plan=plan,
        identities={str(p.relative_to(ROOT)): identity(p) for p in source_paths},
        revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        branch=subprocess.check_output(['git', 'branch', '--show-current'], text=True).strip(),
        command=sys.argv, python=sys.version, numpy=np.__version__,
        thread_environment={k: os.getenv(k) for k in ['OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS']}))
    with (out/'controls.txt').open('x') as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
    write(out/'controls.json', dict(tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors), passed=result.wasSuccessful()))
    if not result.wasSuccessful():
        raise RuntimeError('numerical controls failed; candidate evaluation not started')
    started = time.process_time()
    cases, references = [], {}
    counts = dict(cases=0, fresh_posterior_model_steps=0, predictive_physical_steps=0, candidate_density_points=0, placement_sample_visits=0)

    def charge(key, n):
        counts[key] += n
        r.require(counts[key] <= plan['work_caps'][key], 'work cap: '+key)

    for prefix, paths in selected.items():
        receipt = json.loads((paths[0].parent/'result.json').read_text())
        r.require(receipt['status'] == 'finite_moment_checks_passed', 'unqualified source moments')
        pops = []
        for path in paths:
            with np.load(path, allow_pickle=False) as archive:
                pop = archive['projected'][:, :16].copy()
            r.require(pop.shape == (4096, 16), 'wrong projected shape')
            r.to_unit(pop)
            pops.append(pop)
        train = np.concatenate(pops[:2])
        heldout = np.concatenate(pops[2:])
        probes = plan['stationary_predictive_probes']
        probe_steps = sum(len(p['steps']) for p in probes)
        charge('predictive_physical_steps', len(heldout)*probe_steps)
        refs = physical_outputs(heldout, probes)
        references[prefix] = dict(source_id=receipt['source_id'], elapsed_s=receipt['elapsed_s'],
            observation_interval=receipt['observation_interval'], transition_interval=receipt['transition_interval'],
            owns_initial_prior=receipt['owns_initial_prior'], source_status=receipt['status'],
            source_adequacy=receipt['adequacy'], current_order=receipt['current_order'][:16],
            train=[str(p.relative_to(ROOT)) for p in paths[:2]], heldout=[str(p.relative_to(ROOT)) for p in paths[2:]],
            heldout_moments=moments(heldout), heldout_outputs=refs,
            heldout_population_difference=difference(pops[2], pops[3]),
            train_heldout_difference=difference(train, heldout))
        for k in plan['regions']:
            for arm in plan['arms']:
                charge('cases', 1)
                case = dict(prefix=int(prefix), K=k, arm=arm)
                begin = time.process_time()
                try:
                    if arm.startswith('adaptive'):
                        charge('placement_sample_visits', 16*len(train))
                    msg = r.fit(train, k, arm)
                    case['build_CPU_s'] = time.process_time()-begin
                    case['regions'] = msg.diagnostics
                    case['edges_normalized_logQ'] = msg.edges
                    case['retained_numeric_B'] = msg.numeric_bytes
                    case['construction_known_array_lower_B'] = train.nbytes * 2 + msg.numeric_bytes
                    case['construction_lower_scope'] = 'input full16 sample matrix plus unit-coordinate matrix plus payload; additional arrays and library workspace excluded'
                    case['complete_target_SRAM_B'] = None
                    case['online_update_implemented'] = False
                    case['deployment_qualified'] = False
                    tag = f'prefix{prefix}_K{k}_{arm}'
                    payload = dict(schema='offline_joint_message_v1', posterior=msg.export(),
                        owns_initial_prior=True, source_id=receipt['source_id'],
                        observation_interval=receipt['observation_interval'],
                        transition_interval=receipt['transition_interval'],
                        support_low=r.LOW.tolist(), support_high=r.HIGH.tolist(),
                        status='offline_approximation_unqualified_for_causal_update')
                    write(out/(tag+'.json'), payload)
                    scores = []
                    before = time.process_time()
                    for pop in pops[2:]:
                        charge('candidate_density_points', len(pop))
                        logs = np.concatenate([msg.logpdf(pop[i:i+512]) for i in range(0, len(pop), 512)])
                        r.require(np.isfinite(logs).all(), 'nonfinite heldout density')
                        scores.append(float(-logs.mean()))
                    case['heldout_mean_negative_log_density_by_population'] = scores
                    case['heldout_mean_negative_log_density'] = float(np.mean(scores))
                    case['heldout_density_CPU_s'] = time.process_time()-before
                    draws, proposals = msg.draw(plan['numerics']['draws_per_case'], plan['numerics']['draw_seed_base']+counts['cases'])
                    charge('predictive_physical_steps', len(draws)*probe_steps)
                    case['sampler_uniform_proposals'] = proposals
                    case['draw_moments'] = moments(draws)
                    case['draw_heldout_difference'] = difference(draws, heldout)
                    case['physical_outputs'] = physical_outputs(draws, probes)
                    case['status'] = 'offline_comparison_completed'
                except (r.Unavailable, np.linalg.LinAlgError, FloatingPointError) as e:
                    case['status'] = 'unavailable'
                    case['reason'] = str(e)
                case['total_CPU_s'] = time.process_time()-begin
                cases.append(plain(case))
                write(out/(f'case_{counts["cases"]:02}.json'), plain(case))
                print(prefix, k, arm, case['status'], flush=True)
    summary = dict(schema='joint_region_compression_result_v1',
        status='bounded_offline_comparison_completed', cases=cases, references=plain(references),
        work=counts, CPU_s=time.process_time()-started,
        process_peak_RSS_B=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        prior_or_truth_used_for_compressor_fitting=False, source_posterior_owns_prior=True,
        coverage_validated=False, online_update_implemented=False, deployment_qualified=False,
        likelihood_atlas_implemented=False, full16_network_implemented=False,
        physical_aging_added=False, four_hour_gate_passed=False,
        limits=['Finite source moment checks do not validate joint density or coverage.',
                'Current samples are dependent; heldout population differences are not IID sampling errors.',
                'All arms compress the same posterior; probability atlas is an adaptation of the earlier likelihood-atlas proposal.',
                'Adaptive placement is one-dimensional logQ vector quantization, not a general self-organizing full16 network.',
                'Retained numeric payload excludes ownership metadata, solver, queue, stack and update workspace.',
                'Current offline builder requires samples; it is not a bounded-memory causal update.',
                'Predictive probes are stationary and brief. No aging, long-duration convergence or speed claim follows.'])
    write(out/'result.json', summary)


if __name__ == '__main__':
    main()
