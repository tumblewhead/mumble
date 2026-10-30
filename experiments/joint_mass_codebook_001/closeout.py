"""Verify all immutable attempts and publish a separate local summary/receipt."""
import json
from .qualify import HERE,ROOT
from experiments.structured_joint_001.qualify import ident,write


def main():
    results={}
    for name in ['attempt001','tails001','log16_001']:
        r=json.loads((HERE/name/'result.json').read_text());reservation=json.loads((HERE/name/'reservation.json').read_text())
        assert r['status']=='passed' and not r['failed_checks'] and all(x['passed'] for x in r['checks'])
        for p,expected in reservation['source_identities'].items():
            assert ident(ROOT/p)==expected,p
            assert ident(HERE/name/'source_snapshot'/p)==expected,p
        for p,expected in reservation['preserved_artifacts'].items():assert ident(ROOT/p)==expected,p
        results[name]=r
    development=json.loads((HERE/'development001/receipt.json').read_text())
    for name,expected in development['source_identities'].items():assert ident(HERE/'development001'/name)['sha256']==expected
    primary=results['attempt001'];tail=results['tails001'];log16=results['log16_001']
    dictionary=primary['evidence']['dictionary'];assert ident(HERE/'attempt001/dictionary.json')==dictionary['identity']
    base={(r['fixture'],r['aging_scale'],s['index']):s['exact_queries'] for r in primary['evidence']['held_out'] for s in r['steps']}
    metrics={}
    for codec in ['sphere8','sphere12','shapes','log12']:
        rows=[(r['fixture'],r['aging_scale'],s['index'],s['codecs'][codec]) for r in tail['evidence']['uncertainty'] for s in r['steps']]
        metrics[codec]=dict(payload_B=rows[0][3]['packet_B'],dictionary_parameter_B=864 if codec=='shapes' else 0,
            max_TV=max(x[3]['TV'] for x in rows),max_Q_mean_relative_error_percent=max(100*abs(x[3]['mean_error']['Q'])/base[x[:3]]['Q'] for x in rows),
            max_SOC_mean_error_pp=max(100*abs(x[3]['mean_error']['soc']) for x in rows),
            SOC_std_ratio_range=[min(x[3]['std']['soc']['ratio'] for x in rows),max(x[3]['std']['soc']['ratio'] for x in rows)],
            Q_std_ratio_range=[min(x[3]['std']['Q']['ratio'] for x in rows),max(x[3]['std']['Q']['ratio'] for x in rows)],
            max_local_log_oscillation=max(x[3]['local_log_oscillation'] for x in rows))
    steps=[s for r in log16['evidence']['runs'] for s in r['steps']]
    metrics['log16']=dict(payload_B=steps[0]['packet_B'],dictionary_parameter_B=0,max_TV=max(s['TV'] for s in steps),
        max_Q_mean_relative_error_percent=max(abs(s['Q_relative_error_percent']) for s in steps),
        max_SOC_mean_error_pp=max(abs(s['SOC_error_pp']) for s in steps),
        SOC_std_ratio_range=[min(s['std']['soc']['ratio'] for s in steps),max(s['std']['soc']['ratio'] for s in steps)],
        Q_std_ratio_range=[min(s['std']['Q']['ratio'] for s in steps),max(s['std']['Q']['ratio'] for s in steps)],
        max_local_log_oscillation=max(s['local_log_oscillation'] for s in steps),
        max_accumulated_TV_bound=max(s['TV_ledger'] for s in steps))
    refinement=primary['evidence']['refinement']['results'];coarse,fine=refinement[0]['queries'],refinement[-1]['queries']
    summary=dict(schema='joint_mass_codebook_summary_v1',status='finite_joint_model_and_codecs_qualified_log16_reference_selected_continuous_transport_open',
        report='experiments/joint_mass_codebook_001/README.md',derivation='experiments/joint_mass_codebook_001/derivation.md',
        tail_derivation='experiments/joint_mass_codebook_001/tail_derivation.md',verification='experiments/joint_mass_codebook_001/verification.json',
        result='experiments/joint_mass_codebook_001/attempt001/result.json',tail_result='experiments/joint_mass_codebook_001/tails001/result.json',
        log16_result='experiments/joint_mass_codebook_001/log16_001/result.json',figure='experiments/joint_mass_codebook_001/figures001/joint_mass_geometry.png',
        source_revision=json.loads((HERE/'attempt001/reservation.json').read_text())['source_revision'],branch='experiments/joint-mass-codebook-001',
        identity_scope='Uncommitted source hashes and snapshots; no claim git HEAD contains this work',
        finite_checks=sum(x['passing_checks'] for x in results.values()),checks_by_stage={k:r['passing_checks'] for k,r in results.items()},
        preserved_earlier_artifacts=primary['preserved_earlier_artifacts'],
        model='Six-coordinate joint finite-state comparator, monotone Q/R0 pure-birth boundary transition, separate T(t)/g(T), carried SOC and three joint RC/hysteresis nuisance candidates',
        model_limit='Discrete prior/support and barycentric SOC transport; boundary aging split; engineering rates, not calibrated continuous aging or replacement of original16-coordinate prior',
        criteria='Finite algebra/integrity checks and all comparative distortion measurements; no selected physical accuracy or arbitrary NLL success threshold',
        main_findings=[
            'Probability geometry is encodable: joint square roots lie on a sphere; log relative amplitudes additionally control rare-tail ratios',
            'Linear-amplitude quantization can preserve means but severely distort variance and future rare-event inference',
            'Log-ratio oscillation is common-likelihood invariant and Markov nonexpansive; quantization adds an explicit error increment',
            'Codebook idempotence prevents unchanged storage from drifting; it does not prove indefinite stability under successive physical updates',
            'A five-template Gaussian dictionary loses substantial non-Gaussian shape on held-out fixtures',
            'SOC-grid refinement moves Q/SOC estimates substantially; codebook quality does not repair that discretization'],
        codec_metrics=metrics,rare_tail=tail['evidence']['rare_tail']+[dict(codec='log16',**log16['evidence']['rare_tail'])],
        batch_oracle=primary['evidence']['batch'],C_control=primary['evidence']['C_reference'],
        geometry_code=primary['evidence']['geometry'],grid_refinement=primary['evidence']['refinement'],
        coarse_to_fine_changes=dict(Q_relative_percent=100*(coarse['Q']-fine['Q'])/fine['Q'],SOC_pp=100*(coarse['soc']-fine['soc'])),
        storage=dict(joint_cells=4131,float64_probability_B=33048,linear8_B=4131,linear12_or_log12_B=6197,log16_B=8262,
                     shape_index_and_mask_B=518,shape_dictionary_parameters_B=864,complete_SRAM_B=None,
                     python_cached_dictionary_B=dictionary['dense_cached_shapes_B'],python_feature_grid_B=dictionary['feature_grid_B']),
        resources=dict(cpu_seconds_by_stage={k:r['cpu_seconds'] for k,r in results.items()},main_maximum_RSS_B=primary['maximum_RSS_B'],
                       scope='Qualification runs, not battery-estimator throughput; plots excluded'),
        selected_diagnostic_reference='Log16 fixed-span512 amplitude codec; preserve joint support and log-ratio error ledger',
        next='Control/replace coarse SOC-grid transport while retaining capacity-path and temperature dependence; then reduce shape coordinates with bounded log-residual distortion and complete workspace accounting. Keep exactly composable pending physical transport separate where commutation permits.',
        original_rounding_failure=development,
        no_remote_execution=True,production_changed=False,aging_calibrated=False,continuous_posterior_qualified=False,
        coverage_validated=False,complete_memory_qualified=False,lifetime_qualified=False)
    write(HERE/'summary.json',summary)
    files=sorted(p for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p!=HERE/'verification.json')
    write(HERE/'verification.json',dict(status='passed',finite_checks=summary['finite_checks'],preserved_earlier_artifacts=primary['preserved_earlier_artifacts'],
          artifacts={str(p.relative_to(ROOT)):ident(p) for p in files},scope='Immutable-source/evidence verification and finite controls; not physical or lifetime qualification'))
    print(json.dumps(dict(status='passed',checks=summary['finite_checks'],artifacts=len(files),preserved=primary['preserved_earlier_artifacts'])))


if __name__=='__main__':main()
