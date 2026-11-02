"""Deterministic compact reduction of attribution and paired basis intervention."""
import argparse
import json
from pathlib import Path
import numpy as np
from experiments.foster_campaign_001.backend import identity
from experiments.h7_history_quality_001.history import write


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--attribution',type=Path,required=True);p.add_argument('--basis',type=Path,required=True);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    attribution=[];basis=[];bindings={};exceptions=[];active=0;hfirst=0;storage={}
    for path in sorted(args.attribution.glob('case_*.json')):
        x=json.loads(path.read_text());bindings[str(path)]=identity(path)
        for prefix in x['prefixes']:
            qs=prefix['queries'];groups={}
            for name in qs[0]['groups']:
                groups[name]=dict(max_relative_single_group_defect=max(q['groups'][name]['one_group_relative_gradient_defect'] for q in qs),
                    max_voltage_RMS_V=max(q['groups'][name]['voltage_RMS_V'] for q in qs),max_voltage_error_V=max(q['groups'][name]['voltage_max_V'] for q in qs))
            if x['load']!='rest':
                for q in qs:
                    active+=1;winner=max(q['groups'],key=lambda k:q['groups'][k]['one_group_relative_gradient_defect'])
                    if winner=='hysteresis':hfirst+=1
                    else:exceptions.append(dict(load=x['load'],records=prefix['records'],query=q['id'],largest_group=winner))
            peak=max(qs,key=lambda q:q['relative_total_gradient_defect'])
            attribution.append(dict(load=x['load'],records=prefix['records'],observation_sha256=prefix['observation_sha256'],groups=groups,
                max_relative_closure=max(q['relative_attribution_closure'] for q in qs),max_relative_QR_closure=max(q['relative_QR_gradient_closure'] for q in qs),
                max_response_partition_closure_V=max(q['response_partition_closure_max_V'] for q in qs),
                max_relative_pair_interaction=max(max(q['relative_pair_interaction_norms']) for q in qs),
                max_shape_derivative_RMS_V=np.max([q['shape_derivative_RMS_V'] for q in qs],axis=0),
                peak_total_query=dict(id=peak['id'],relative_total_gradient_defect=peak['relative_total_gradient_defect'],
                    hysteresis_signed_terms=peak['groups']['hysteresis']['signed_gradient_terms'],
                    hysteresis_scaled_term_norms=peak['groups']['hysteresis']['scaled_gradient_term_norms'],
                    term_order=['exact_J_times_response_defect','sensitivity_defect_times_exact_residual','self_interaction'])))
    for path in sorted(args.basis.glob('case_*.json')):
        x=json.loads(path.read_text());bindings[str(path)]=identity(path);storage=x['storage']
        for prefix in x['prefixes']:
            public=[q for q in prefix['queries'] if q['selection']=='public']
            for name in public[0]['arms']:
                supported=[q for q in public if q['arms'][name]['status']=='supported' and q['arms'][name]['metrics'] is not None]
                ms=[q['arms'][name]['metrics'] for q in supported]
                pairs=[(q['arms'][name]['metrics']['relative_joint_gradient_defect'],q['arms']['R2_H2_log']['metrics']['relative_joint_gradient_defect']) for q in supported]
                basis.append(dict(load=x['load'],records=prefix['records'],arm=name,public_count=len(public),compared=len(ms),
                    better_than_baseline=sum(a<b for a,b in pairs),worse_than_baseline=sum(a>b for a,b in pairs),equal_to_baseline=sum(a==b for a,b in pairs),
                    max_relative_gradient_defect=max(m['relative_joint_gradient_defect'] for m in ms),max_relative_precision_defect=max(m['relative_amplitude_precision_defect'] for m in ms),
                    max_abs_NLL_defect=max(abs(m['nll_defect']) for m in ms),max_RC_error_V=max(m['endpoint_RC_max_error_V'] for m in ms),
                    max_Hh_error_V=max(abs(m['endpoint_Hh_error_V']) for m in ms),min_precision_eigen_ratio=min(m['precision_min_to_max'] for m in ms),
                    domain_exit_status=[q['arms'][name]['status'] for q in prefix['queries'] if q['selection']!='public'],update_cpu_s=prefix['cumulative_cpu_s'][name],observation_sha256=prefix['observation_sha256']))
    write(args.out,dict(schema='response_basis_attribution_reduction_v1',source=identity(Path(__file__)),input_bindings=bindings,
        scope='Adaptive finite public probes; relative gradient defect is not fitted parameter error or calibrated uncertainty',
        hysteresis_largest_group_on_active_probes=dict(count=hfirst,total=active,exceptions=exceptions),attribution=attribution,basis=basis,storage=storage))

if __name__=='__main__':main()
