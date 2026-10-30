"""Verify preserved evidence and independently recompute finite fit residuals."""
import json
from pathlib import Path
import numpy as np
from experiments.region_compression_001 import compare as base
from experiments.natural_hysteresis_001 import natural
from experiments.natural_hysteresis_001.message import Message, unchanged
from experiments.partition_coordinate_fit_001 import coordinates as c

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    out = HERE/'attempt001'
    result = json.loads((out/'result.json').read_text())
    reservation = json.loads((out/'reservation.json').read_text())
    checks = []

    def check(name, condition):
        checks.append(dict(name=name, passed=bool(condition)))
        if not condition:
            raise AssertionError(name)

    for path, expected in reservation['identities'].items():
        check('preserved '+path, base.identity(ROOT/path) == expected)
    for key, cap in reservation['plan']['work_caps'].items():
        check('work '+key, result['work'][key] <= cap)
    check('controls', json.loads((out/'controls.json').read_text()) ==
          dict(tests_run=48, failures=0, errors=0, passed=True))
    check('all fits represented', sum(len(r['fits']) for r in result['repairs']) == 8)
    independent = []
    for repair in result['repairs']:
        p = repair['prefix']
        ref = result['references'][str(p)]['inherited']
        train = []
        for path in ref['train']:
            with np.load(ROOT/path, allow_pickle=False) as archive:
                train.append(archive['projected'][:, :16].copy())
        train = np.concatenate(train)
        labels = np.searchsorted([.5], c.old.to_unit(train)[:, 5], side='right')
        parent_payload = json.loads((HERE.parent/f'partition_coordinate_fit_001/attempt002/prefix{p}_specialized_bounded_likelihood_message.json').read_text())
        parent = c.Message.restore(parent_payload['posterior'])
        payload = json.loads((out/f'prefix{p}_natural_refit_message.json').read_text())
        msg = Message.restore(payload['posterior'])
        unchanged(parent, msg)
        check(f'prefix{p} unchanged coefficients and storage', msg.numeric_bytes == 2496)
        for key in ['source_id', 'owns_initial_prior', 'observation_interval', 'transition_interval',
                    'physical_support_low', 'physical_support_high']:
            check(f'prefix{p} ownership '+key, parent_payload[key] == payload[key])
        y, _, _ = c.encode(train, msg.chart, msg.frame)
        for diag in repair['fits']:
            j, region_index = diag['coordinate'], diag['component']
            local = y[labels == region_index]
            design = np.column_stack([np.ones(len(local)), local[:, :j]])
            reg = msg.regions[region_index]
            eta = design @ c.coefficients(reg, j)
            precision = float(reg['shape'][j])
            # Independent 512-node integration and raw features, no optimizer
            # gradient, Hessian, or feature whitening is reused here.
            stats = natural.quadrature(eta, precision, 512)
            ga = design.T @ (stats[:, 1]-local[:, j])/len(local)
            gk = float(.5*np.mean(local[:, j]**2-stats[:, 2]))
            loss = float(np.mean(stats[:, 0]-eta*local[:, j]+.5*precision*local[:, j]**2))
            kkt = max(float(np.abs(ga).max()), abs(min(gk, 0.)) if precision == 0 else abs(gk))
            tag = f'prefix{p} component{region_index} coordinate{j}'
            check(tag+' boundary', precision == 0)
            check(tag+' numerical convergence', diag['status'] == 'constrained_gradient_tolerance_met' and kkt <= 1e-7)
            check(tag+' decreasing objective', diag['final_mean_NLD'] <= diag['initial_mean_NLD'])
            check(tag+' independent objective', abs(loss-diag['final_mean_NLD']) <= 2e-11)
            independent.append(dict(prefix=p, component=region_index, coordinate=j,
                raw_feature_KKT_residual=kkt, precision_gradient=gk, mean_NLD=loss,
                source_minus_fitted_second_moment=2*gk))
    for case in result['cases']:
        tag = str(case['prefix'])+' '+case['arm']
        check(tag+' draws', case['draws'] == 65536 and len(case['batches']) == 4)
        check(tag+' all probes supported', len(case['probes']) == 13 and all(
            p['status'] == 'finite_all_draws_supported' for p in case['probes'].values()))
    check('no truth/inference', result['truth_reads'] == 0 and not result['new_particle_inference'])
    check('no unearned qualification', not any(result[key] for key in
          ['coverage_validated', 'deployment_qualified', 'history_error_stability_validated', 'aging_update_implemented']))
    fits = [f for r in result['repairs'] for f in r['fits']]
    summary = dict(schema='natural_hysteresis_summary_v1',
        status='eight_conditional_fits_repaired_at_bounded_exponential_boundary',
        scope='Numerical representation repair; no lifetime, coverage, or physical identification claim',
        result='experiments/natural_hysteresis_001/attempt001/result.json',
        controls_passed=48, refitted_conditionals=8,
        iterations=[min(f['iterations'] for f in fits), max(f['iterations'] for f in fits)],
        maximum_constrained_gradient=max(f['constrained_gradient_infinity'] for f in fits),
        maximum_independent_raw_gradient=max(f['raw_feature_KKT_residual'] for f in independent),
        all_precision_zero=all(f['precision'] == 0 for f in fits),
        precision_gradient_range=[min(f['precision_gradient'] for f in fits), max(f['precision_gradient'] for f in fits)],
        refit_CPU_s=sum(r['build_CPU_s'] for r in result['repairs']), comparison_CPU_s=result['CPU_s'],
        storage_B=dict(retained_two_component_numeric=2496, four_component_formula_only=4960,
                       complete_target_SRAM=None, measured_desktop_process_peak_RSS=result['process_peak_RSS_B'],
                       construction_population_array=8192*16*8, pooled_generated_array=65536*16*8),
        heldout_NLD_improvement_by_prefix={}, prefix32_probe_comparison={},
        finite_log_density_change=[dict(prefix=r['prefix'], **r['change_bound'],
            observed_heldout_max_abs=r['heldout_max_absolute_log_density_change']) for r in result['repairs']],
        unresolved=['Remaining longer-reversal and other distribution discrepancies',
            'A boundary optimum is only within the inherited log-concave conditional family',
            'Finite source populations are not an exact posterior or coverage reference',
            'Only0.229/0.914seconds of source history; no streaming accumulation test',
            'Posterior ownership/update integration, physical aging, complete SRAM/work accounting'],
        next_step='Diagnose remaining distribution-shape and coupling residuals on the same references, including whether the inherited nonnegative precision restriction is appropriate; then qualify causal posterior transport and ownership before longer trajectories.')
    for prefix in [8, 32]:
        before, after = [case for case in result['cases'] if case['prefix'] == prefix]
        summary['heldout_NLD_improvement_by_prefix'][str(prefix)] = (
            np.array(before['heldout_mean_negative_log_density_by_population'])-
            after['heldout_mean_negative_log_density_by_population']).tolist()
        if prefix == 32:
            for name in after['probes']:
                ref = result['references']['32']['probes'][name]['voltage_V']
                row = dict(reference_SD_mV=ref['SD']*1000)
                for label, case in [('baseline', before), ('repaired', after)]:
                    p = case['probes'][name]
                    row[label] = dict(SD_mV=p['voltage_V']['SD']*1000,
                        mean_difference_mV=(p['voltage_V']['mean']-ref['mean'])*1000,
                        batch_SD_range_mV=[v*1000 for v in p['batch_SD_range_V']],
                        batch_mean_range_mV=[v*1000 for v in p['batch_mean_range_V']])
                summary['prefix32_probe_comparison'][name] = row
    base.write(HERE/'summary.json', summary)
    base.write(HERE/'independent_fit_audit.json', dict(order=512, conditionals=independent,
        scope='Independent quadrature order/raw-feature residual calculation; same model and source samples, not an independent implementation or reviewer'))
    files = [p for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name != 'verification.json']
    artifacts = {str(p.relative_to(ROOT)): base.identity(p) for p in sorted(files)}
    base.write(HERE/'verification.json', dict(status='passed', checks=checks, artifacts=artifacts,
        scope='Source preservation, frozen work limits, controls, unchanged ownership/non-rate parameters, and independent finite residual recomputation; not coverage or indefinite stability'))
    print(json.dumps(dict(checks=len(checks), controls=48, max_KKT=summary['maximum_constrained_gradient'],
                          refit_CPU_s=summary['refit_CPU_s'], storage_B=2496)))


if __name__ == '__main__':
    main()
