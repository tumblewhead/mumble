"""Frozen backward decomposition of saved finite predictive discrepancies."""
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
from experiments.backward_response_001 import algebra as a
from experiments.backward_response_001.test_algebra import Controls
from experiments.natural_hysteresis_001.message import Message
from experiments.region_compression_001 import compare as base

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default=str(HERE/'attempt001'))
    out = Path(parser.parse_args().output)
    out.mkdir(parents=True, exist_ok=False)
    plan = json.loads((HERE/'plan.json').read_text())
    old_path = ROOT/plan['baseline']
    old = json.loads(old_path.read_text())
    verification = json.loads((old_path.parent.parent/'verification.json').read_text())
    bindings = dict(verification['artifacts'])
    bindings.update(json.loads((old_path.parent/'reservation.json').read_text())['identities'])
    for path, identity in bindings.items():
        a.c.old.require(base.identity(ROOT/path) == identity, 'changed predecessor '+path)
    for path in [*HERE.glob('*.py'), HERE/'plan.json', HERE/'derivation.md',
                 ROOT/'experiments/minimal_health_kernels_001/kernel.py',
                 ROOT/'experiments/joint_health_posterior_001/model.py',
                 old_path.parent.parent/'verification.json']:
        bindings[str(path.relative_to(ROOT))] = base.identity(path)
    base.write(out/'reservation.json', dict(plan=plan, identities=bindings, command=sys.argv,
        revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        branch=subprocess.check_output(['git', 'branch', '--show-current'], text=True).strip(),
        python=sys.version, numpy=np.__version__,
        thread_environment={k:os.getenv(k) for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']}))
    with (out/'controls.txt').open('x') as stream:
        tested = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
    base.write(out/'controls.json', dict(passed=tested.wasSuccessful(), tests_run=tested.testsRun,
        errors=len(tested.errors), failures=len(tested.failures)))
    a.c.old.require(tested.wasSuccessful(), 'algebra controls failed')
    work = {key:0 for key in plan['work_caps']}
    checks, worst = [], dict(voltage_sum_error_V=0., variance_identity_error_V2=0., reversal_closed_error_V=0.)

    def check(name, condition):
        checks.append(dict(name=name, passed=bool(condition)))
        if not condition:
            raise AssertionError(name)

    def charge(key, amount):
        check('work cap '+key, work[key]+amount <= plan['work_caps'][key])
        work[key] += amount

    def assess(x, label):
        result = {}
        for probe in old['probe_definitions']:
            count = len(x)*len(probe['steps'])
            charge('recurrence_sample_steps', count)
            voltage, valid = a.c.old.stationary_probe(x, probe['steps'])
            charge('decomposition_sample_steps', count)
            terms = a.terms(x, probe['steps'])
            moments = a.moments(terms)
            error = float(np.max(np.abs(terms.sum(1)-voltage)))
            varerror = float(abs(moments['covariance'].sum()-voltage.var()))
            worst['voltage_sum_error_V'] = max(worst['voltage_sum_error_V'], error)
            worst['variance_identity_error_V2'] = max(worst['variance_identity_error_V2'], varerror)
            tag = label+' '+probe['name']
            check(tag+' support', valid.all())
            check(tag+' voltage identity', error <= plan['arithmetic_controls']['voltage_sum_absolute_tolerance_V'])
            check(tag+' variance identity', varerror <= plan['arithmetic_controls']['variance_sum_absolute_tolerance_V2'])
            if probe['profile'] == 'reversal':
                closed = a.reversal_closed(x, .05, probe['horizon_s'])
                cerr = float(np.max(abs(closed-voltage)))
                worst['reversal_closed_error_V'] = max(worst['reversal_closed_error_V'], cerr)
                check(tag+' closed reversal', cerr <= 2e-12)
                check(tag+' OCV cancellation', np.max(abs(terms[:, 1])) <= 2e-14)
            result[probe['name']] = moments
        return result

    started = time.process_time()
    cases = []
    for prefix in plan['prefixes']:
        ref = old['references'][str(prefix)]['inherited']
        populations = {}
        for kind in ['train', 'heldout']:
            rows = []
            for index, path in enumerate(ref[kind]):
                with np.load(ROOT/path, allow_pickle=False) as archive:
                    x = archive['projected'][:, :16].copy()
                charge('source_rows', len(x))
                rows.append(assess(x, f'prefix{prefix} {kind}{index}'))
            populations[kind] = rows
        saved = next(case for case in old['cases'] if case['prefix'] == prefix and case['arm'] == 'natural_refit')
        payload = json.loads((old_path.parent/f'prefix{prefix}_natural_refit_message.json').read_text())
        msg = Message.restore(payload['posterior'])
        batches = []
        for index, batch in enumerate(saved['batches']):
            charge('generated_rows', batch['draws'])
            charge('inverse_OCV_sample_iterations', batch['draws']*52)
            x, _ = msg.draw(batch['draws'], batch['seed'])
            rows = assess(x, f'prefix{prefix} generated{index}')
            for name, stats in rows.items():
                previous = batch['probes'][name]['voltage_V']
                check(f'prefix{prefix} batch{index} {name} saved mean', abs(stats['mean'].sum()-previous['mean']) <= 2e-12)
                check(f'prefix{prefix} batch{index} {name} saved variance', abs(stats['covariance'].sum()-previous['SD']**2) <= 2e-15)
            batches.append(rows)
        by_probe = {}
        for probe in old['probe_definitions']:
            name = probe['name']
            reference = a.pool([row[name] for row in populations['heldout']])
            construction = a.pool([row[name] for row in populations['train']])
            generated = a.pool([row[name] for row in batches])
            comparisons = [a.contrast(row[name], reference) for row in batches]
            by_probe[name] = dict(reference=reference, construction=construction, generated=generated,
                model_minus_reference=a.contrast(generated, reference),
                construction_minus_reference=a.contrast(construction, reference),
                model_batch_minus_reference=comparisons,
                reference_population_difference=a.contrast(populations['heldout'][0][name], populations['heldout'][1][name]))
            check(f'prefix{prefix} {name} grouped mean closure', abs(sum(by_probe[name]['model_minus_reference']['group_mean_differences_V'].values())-
                by_probe[name]['model_minus_reference']['mean_difference_V']) <= 2e-14)
            check(f'prefix{prefix} {name} grouped variance closure', abs(sum(by_probe[name]['model_minus_reference']['group_variance_contributions_V2'].values())-
                by_probe[name]['model_minus_reference']['variance_difference_V2']) <= 2e-15)
        case = dict(prefix=prefix, source=ref, probes=by_probe)
        cases.append(case)
        base.write(out/f'prefix{prefix}.json', base.plain(case))
        print('prefix', prefix, 'mean groups mV', {key:value*1000 for key,value in by_probe['reversal_10s']['model_minus_reference']['group_mean_differences_V'].items()}, flush=True)
    k = a.c.old.kernel
    curvature = []
    for j in [3, 4]:
        threshold = float(np.exp(k.MEAN[j]+1-k.SD[j]**2))
        curvature.append(dict(coordinate=j, log_prior_mean=float(k.MEAN[j]), log_prior_SD=float(k.SD[j]),
            gamma_support=np.exp([k.LOW[j],k.HIGH[j]]), log_convex_above_gamma=threshold,
            scope='Actual initial transformed prior only; not a claim about posterior conditional curvature'))
    inherited_audit = json.loads((old_path.parent.parent/'independent_fit_audit.json').read_text())
    result = dict(schema='backward_response_result_v1', status='finite_backward_decomposition_completed',
        cases=cases, labels=a.LABELS, groups=a.GROUPS, prior_curvature=curvature,
        inherited_conditional_residuals=inherited_audit['conditionals'], checks=checks, max_errors=worst,
        work=work, CPU_s=time.process_time()-started,
        process_peak_RSS_B=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        retained_message_numeric_B=2496, one_probe_12term_moment_diagnostic_numeric_B=720,
        complete_target_SRAM_B=None, new_fits=False, truth_reads=0, rolling_solver_changed=False,
        coverage_validated=False, aging_qualified=False, lifetime_stability_qualified=False)
    base.write(out/'result.json', base.plain(result))
    print('checks', len(checks), 'max errors', worst, flush=True)


if __name__ == '__main__':
    main()
