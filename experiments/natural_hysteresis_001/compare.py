"""Eight focused fits, matched draws, frozen heldout populations; no inference."""
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
from experiments.partition_coordinate_fit_001 import compare as predecessor
from experiments.partition_coordinate_fit_001.compare_repaired import RepairControls
from experiments.partition_coordinate_fit_001.stable_normalizer import log_mass
from experiments.natural_hysteresis_001 import natural
from experiments.natural_hysteresis_001.message import Message, NATURAL, unchanged, change_bound
from experiments.natural_hysteresis_001.test_natural import Controls

c, probes = predecessor.c, predecessor.probes
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default=str(HERE/'attempt001'))
    out = Path(parser.parse_args().output)
    out.mkdir(parents=True, exist_ok=False)
    plan = json.loads((HERE/'plan.json').read_text())
    prior_path = ROOT/plan['baseline']
    prior = json.loads(prior_path.read_text())
    bindings = json.loads((prior_path.parent/'reservation.json').read_text())['identities']
    bindings.update(json.loads((prior_path.parent.parent/'verification.json').read_text())['artifacts'])
    for path, expected in bindings.items():
        c.old.require(base.identity(ROOT/path) == expected, 'previous evidence changed: '+path)
    for path in [*HERE.glob('*.py'), HERE/'plan.json', HERE/'derivation.md',
                 prior_path.parent.parent/'verification.json']:
        bindings[str(path.relative_to(ROOT))] = base.identity(path)
    base.write(out/'reservation.json', dict(status='before_battery_fits_and_heldout_evaluation',
        identities=bindings, plan=plan, command=sys.argv, python=sys.version, numpy=np.__version__,
        revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        branch=subprocess.check_output(['git', 'branch', '--show-current'], text=True).strip(),
        thread_environment={key: os.getenv(key) for key in ['OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS']},
        control_arithmetic='Inherited controls run under predecessor stable log_mass substitution; new message calls stable normalizer explicitly'))
    groups = [predecessor.OriginalControls, predecessor.VoltageControls, predecessor.RCControls, RepairControls, Controls]
    suite = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(g) for g in groups])
    original = c.v.log_mass
    try:
        c.v.log_mass = log_mass
        with (out/'controls.txt').open('x') as stream:
            tested = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    finally:
        c.v.log_mass = original
    base.write(out/'controls.json', dict(tests_run=tested.testsRun, failures=len(tested.failures),
        errors=len(tested.errors), passed=tested.wasSuccessful()))
    c.old.require(tested.wasSuccessful(), 'controls failed; no battery evaluation')
    work = {key: 0 for key in plan['work_caps']}

    def charge(key, amount):
        c.old.require(work[key]+amount <= plan['work_caps'][key], 'work cap '+key)
        work[key] += amount

    def load(path):
        with np.load(ROOT/path, allow_pickle=False) as archive:
            return archive['projected'][:, :16].copy()

    definitions = probes.definitions(plan['probe_horizons_s'])
    steps = sum(len(p['steps']) for p in definitions)
    started = time.process_time()
    cases, repairs = [], []
    for prefix in [8, 32]:
        charge('messages', 1)
        ref = prior['references'][str(prefix)]['inherited']
        train = np.concatenate([load(path) for path in ref['train']])
        held = [load(path) for path in ref['heldout']]
        pooled = np.concatenate(held)
        parent_path = prior_path.parent/f'prefix{prefix}_specialized_bounded_likelihood_message.json'
        parent_payload = json.loads(parent_path.read_text())
        parent = c.Message.restore(parent_payload['posterior'])
        baseline = Message.from_gaussian(parent)
        fitted = Message.restore(baseline.export())
        y, _, _ = c.encode(train, parent.chart, parent.frame)
        labels = np.searchsorted(parent.edges[1:-1], c.old.to_unit(train)[:, 5], side='right')
        fits = []
        build_start = time.process_time()
        for region_index, reg in enumerate(fitted.regions):
            local = y[labels == region_index]
            for j in NATURAL:
                charge('refitted_conditionals', 1)
                try:
                    beta, k, diag = natural.fit(local[:, :j], local[:, j],
                        c.coefficients(reg, j), float(reg['shape'][j]), plan['optimizer'], charge)
                    c.coefficients(reg, j)[:] = beta
                    reg['shape'][j] = k
                except (c.old.Unavailable, np.linalg.LinAlgError, FloatingPointError) as error:
                    diag = dict(status='unavailable_preserved_converted_baseline', reason=str(error))
                diag.update(component=region_index, coordinate=j, construction_rows=len(local))
                fits.append(diag)
                print('prefix', prefix, 'component', region_index, 'coordinate', j, diag, flush=True)
        unchanged(parent, baseline)
        unchanged(parent, fitted)
        repair = dict(prefix=prefix, fits=fits, build_CPU_s=time.process_time()-build_start,
                      change_bound=change_bound(baseline, fitted), non_rate_parameters_unchanged=True)
        repairs.append(repair)
        base.write(out/f'prefix{prefix}_repair.json', base.plain(repair))
        scores_by_arm = []
        for arm_index, (arm, msg) in enumerate([('converted_baseline', baseline), ('natural_refit', fitted)]):
            tag = f'prefix{prefix}_{arm}'
            payload = dict(parent_payload, schema='natural_hysteresis_joint_payload_v1', posterior=msg.export(),
                           parent_message=str(parent_path.relative_to(ROOT)), parent_identity=base.identity(parent_path),
                           representation='same joint conditional mixture; physical rates use bounded natural parameters')
            base.write(out/(tag+'_message.json'), payload)
            begin = time.process_time()
            logs = []
            for pop in held:
                charge('heldout_density_points', len(pop))
                values = np.concatenate([msg.logpdf(pop[i:i+512]) for i in range(0, len(pop), 512)])
                c.old.require(np.isfinite(values).all(), 'nonfinite heldout density')
                logs.append(values)
            scores = [-float(values.mean()) for values in logs]
            scores_by_arm.append(np.concatenate(logs))
            if arm_index == 0:
                previous = next(row for row in prior['cases'] if row['prefix'] == prefix
                                and row['chart'] == 'specialized' and row['method'] == 'bounded_likelihood')
                np.testing.assert_allclose(scores, previous['heldout_mean_negative_log_density_by_population'], rtol=0, atol=2e-8)
            case = dict(prefix=prefix, arm=arm, retained_numeric_B=msg.numeric_bytes, complete_target_SRAM_B=None,
                        heldout_mean_negative_log_density_by_population=scores,
                        heldout_density_CPU_s=time.process_time()-begin)
            draws, batches = [], []
            for batch in range(plan['draw_batches']):
                seed = plan['seed_base']+prefix*100+arm_index*10+batch
                charge('inverse_OCV_sample_iterations', plan['draws_per_batch']*52)
                x, info = msg.draw(plan['draws_per_batch'], seed)
                charge('predictive_sample_steps', len(x)*steps)
                batches.append(dict(seed=seed, draws=len(x), sampler_work=info,
                    probes=probes.assess(x, definitions),
                    marginals=dict(SOC=base.scalar_stats(x[:, 11]), Q_Ah=base.scalar_stats(np.exp(x[:, 5])),
                                   R0_ohm=base.scalar_stats(x[:, 6]))))
                draws.append(x)
            x = np.concatenate(draws)
            # Pooled probe moments are reconstructed exactly from the batches;
            # quantiles stay per batch to avoid a second unbudgeted propagation.
            pooled_probes = {}
            for name in batches[0]['probes']:
                rows = [b['probes'][name] for b in batches]
                supported = all(row['voltage_V'] is not None for row in rows)
                p = dict(status='finite_all_draws_supported' if supported else 'unavailable_support_loss',
                         invalid_mass_fraction=float(np.mean([r['invalid_mass_fraction'] for r in rows])))
                if supported:
                    means = np.array([r['voltage_V']['mean'] for r in rows])
                    sds = np.array([r['voltage_V']['SD'] for r in rows])
                    # scalar_stats uses population variance (ddof=0).
                    p['voltage_V'] = dict(mean=float(means.mean()), SD=float(np.sqrt(np.mean(sds*sds+(means-means.mean())**2))))
                    p['batch_mean_range_V'] = [float(means.min()), float(means.max())]
                    p['batch_SD_range_V'] = [float(sds.min()), float(sds.max())]
                    p['batch_mean_SD_V'] = float(means.std(ddof=1))
                    p['batch_SD_SD_V'] = float(sds.std(ddof=1))
                pooled_probes[name] = p
            case.update(batches=batches, draws=len(x), probes=pooled_probes,
                draw_moments=base.moments(x), draw_heldout_difference=base.difference(x, pooled),
                marginals=dict(SOC=base.scalar_stats(x[:, 11]), Q_Ah=base.scalar_stats(np.exp(x[:, 5])),
                               R0_ohm=base.scalar_stats(x[:, 6])))
            charge('serialization_density_points', 16)
            restored = Message.restore(json.loads((out/(tag+'_message.json')).read_text())['posterior'])
            np.testing.assert_array_equal(msg.logpdf(pooled[:8]), restored.logpdf(pooled[:8]))
            case.update(status='offline_comparison_completed', CPU_s=time.process_time()-begin)
            base.write(out/(tag+'.json'), base.plain(case))
            cases.append(case)
            print(tag, case['status'], scores, flush=True)
        repair['heldout_max_absolute_log_density_change'] = float(np.max(np.abs(scores_by_arm[1]-scores_by_arm[0])))
        c.old.require(repair['heldout_max_absolute_log_density_change'] <=
                      repair['change_bound']['mixture_log_density_ratio_bound']+1e-10, 'finite change bound violated')
    result = dict(schema='natural_hysteresis_result_v1', status='focused_comparison_completed',
        repairs=repairs, cases=cases, references=prior['references'], work=work,
        CPU_s=time.process_time()-started, process_peak_RSS_B=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        probe_definitions=definitions, truth_reads=0, new_particle_inference=False,
        rolling_solver_changed=False, coverage_validated=False, deployment_qualified=False,
        history_error_stability_validated=False, aging_update_implemented=False,
        scope='Fixed-membership conditional fits and finite source-population comparison only')
    base.write(out/'result.json', base.plain(result))


if __name__ == '__main__':
    main()
