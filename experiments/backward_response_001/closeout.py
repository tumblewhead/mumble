"""Preserve all backward-diagnostic receipts and summarize measured attribution."""
import json
from pathlib import Path
import numpy as np
from experiments.region_compression_001 import compare as base

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def main():
    first=json.loads((HERE/'attempt001/result.json').read_text())
    second=json.loads((HERE/'rc_factor001/result.json').read_text())
    bindings={}
    for directory in ['attempt001','rc_factor001']:
        reservation=json.loads((HERE/directory/'reservation.json').read_text())
        bindings.update(reservation['identities'])
        result=json.loads((HERE/directory/'result.json').read_text())
        for key, cap in reservation['plan']['work_caps'].items():
            assert result['work'][key]<=cap,key
    for path,expected in bindings.items():
        assert base.identity(ROOT/path)==expected,path
    assert all(check['passed'] for check in first['checks'])
    summary=dict(schema='backward_response_summary_v1',
        status='response_error_isolated_to_RC_mixed_moments_with_source_mean_disagreement',
        primary_result='experiments/backward_response_001/attempt001/result.json',
        adaptive_followup='experiments/backward_response_001/rc_factor001/result.json',
        derivation='experiments/backward_response_001/derivation.md',
        reformulation='experiments/backward_response_001/reformulation.md',
        next_repair='experiments/backward_response_001/next_repair.json',
        controls=5,primary_checks=len(first['checks']),preserved_identity_count=len(bindings),
        max_identity_errors=first['max_errors'],prefixes={},
        prior_curvature=first['prior_curvature'],
        storage_B=dict(unchanged_two_component_retained_numeric=2496,complete_subsystem=None,
            offline_12term_mean_covariance_per_probe=720,offline_10term_factor_mean_covariance=520,
            primary_desktop_peak_RSS=first['process_peak_RSS_B']),
        primary_CPU_s=first['CPU_s'],no_new_fits=True,
        qualifications=dict(coverage=False,causal_update=False,aging=False,lifetime_stability=False,M23=False),
        conclusion='Prioritize physical scaling of carried-RC conditional variance; do not correct mean source-population disagreement or blame the hysteresis boundary for the dominant variance mismatch.',
        limitations=['Finite populations and generated draws; descriptive batch differences are not confidence bounds',
            'Additive covariance attribution depends on chosen coordinates and anchors, not causal intervention',
            'The proposed scale law is a discriminating candidate, not a demonstrated complete repair',
            'Only0.229/0.914seconds of source history; prediction probes do not extend estimator history'])
    for case,factor in zip(first['cases'],second['cases']):
        assert case['prefix']==factor['prefix']
        row=case['probes']['reversal_10s']
        direct=row['model_minus_reference']
        source=row['construction_minus_reference']
        fitted=factor['contrasts']['model_minus_construction']
        dc=np.array(factor['pooled']['generated']['parts']['covariance'])-factor['pooled']['train']['parts']['covariance']
        coupling=float(2*dc[:3,6:9].sum())
        summary['prefixes'][str(case['prefix'])]=dict(
            reversal_mean_mV=dict(model_minus_heldout=direct['mean_difference_V']*1000,
                construction_minus_heldout=source['mean_difference_V']*1000,
                model_minus_construction=fitted['mean_difference_V']*1000),
            reversal_variance_mV2=dict(model_minus_heldout=direct['variance_difference_V2']*1e6,
                construction_minus_heldout=source['variance_difference_V2']*1e6,
                model_minus_construction=fitted['variance_difference_V2']*1e6),
            mean_groups_model_minus_heldout_mV={key:v*1000 for key,v in direct['group_mean_differences_V'].items()},
            variance_groups_model_minus_construction_mV2={key:(v-source['group_variance_contributions_V2'][key])*1e6 for key,v in direct['group_variance_contributions_V2'].items()},
            amplitude_interaction_cross_covariance_change_mV2=coupling*1e6,
            fraction_of_excess_variance_from_this_signed_term=coupling/fitted['variance_difference_V2'],
            slow_mode_self_cross_covariance_change_mV2=float(2*dc[2,8]*1e6),
            model_batch_variance_excess_vs_construction_mV2=[r['variance_difference_V2']*1e6 for r in factor['batch_model_minus_construction']],
            slow_F_SD_construction_model_mV=[float(np.sqrt(factor['pooled'][k]['F']['covariance'][2][2])*1000) for k in ['train','generated']])
    base.write(HERE/'summary.json',summary)
    files=[p for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='verification.json']
    base.write(HERE/'verification.json',dict(status='passed',primary_checks=len(first['checks']),controls=5,
        preserved_identity_count=len(bindings),source_identities=bindings,
        artifacts={str(p.relative_to(ROOT)):base.identity(p) for p in sorted(files)},
        scope='Frozen primary arithmetic checks, separately registered adaptive factor identity, all work caps and source hashes; no new inference or qualification'))
    print(json.dumps(dict(primary_checks=len(first['checks']),preserved_identities=len(bindings),artifacts=len(files))))


if __name__=='__main__':
    main()
