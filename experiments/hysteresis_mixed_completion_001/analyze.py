"""Compact, reproducible accounting of every prefix and matched arm; no promotion gate."""
import argparse
import json
from pathlib import Path
import numpy as np
from experiments.foster_campaign_001.backend import identity
from experiments.h7_history_quality_001.history import write


def analyze(directory):
    manifest=json.loads((directory/'summary.json').read_text())
    rows=[];probes=[];storage=None
    for case in manifest['cases']:
        path=directory/case['file']
        if identity(path)!=case['identity']:raise ValueError('changed case receipt')
        result=json.loads(path.read_text());storage=result['storage']
        for prefix in result['prefixes']:
            for name,fit in prefix['fits']['arms'].items():
                row=dict(load=result['load'],records=prefix['records'],arm=name,status=fit['status'],
                         comparison=fit.get('fit_comparison'),same_anchor=fit.get('same_anchor'),
                         compressed_transport=fit.get('compressed_transport'),diagnostic_failure=fit.get('diagnostic_failure'),
                         forecasts=fit.get('forecasts',[]),
                         selected_stop=fit.get('selected',{}).get('diagnostic',{}).get('stop'),
                         selected_domain_rejections=fit.get('selected',{}).get('diagnostic',{}).get('domain_rejections'))
                rows.append(row)
            public=[q for q in prefix['probes'] if q['selection']=='public']
            for name in storage:
                pairs=[(q['arms'][name]['metrics'],q['arms']['R2_H2']['metrics']) for q in public
                       if q['arms'][name]['status']=='supported' and q['arms']['R2_H2']['status']=='supported']
                values=np.array([a['relative_joint_gradient_defect'] for a,b in pairs])
                old=np.array([b['relative_joint_gradient_defect'] for a,b in pairs])
                probes.append(dict(load=result['load'],records=prefix['records'],arm=name,count=len(pairs),
                    improved=int(np.sum(values<old-1e-12)),worsened=int(np.sum(values>old+1e-12)),
                    tied_within_absolute_1e_12=int(np.sum(abs(values-old)<=1e-12)),
                    maximum_relative_joint_gradient_defect=float(values.max()),
                    median_relative_joint_gradient_defect=float(np.median(values)),
                    max_endpoint_Hh_defect_mV=float(1000*max(abs(a['endpoint_Hh_error_V']) for a,b in pairs))))
            witness=[q for q in prefix['probes'] if q['selection']!='public']
            if any(a['status']!='unsupported' for q in witness for a in q['arms'].values()):
                raise ValueError('preserved domain exit unexpectedly supported')
    return dict(run=str(directory),manifest=identity(directory/'summary.json'),registration=identity(directory/'registration.json'),
                case_files=manifest['cases'],fit_rows=rows,public_probe_rows=probes,storage=storage,
                scope='All local fit statuses and finite public probes retained; signed point differences are relative to direct fits, not truth')


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--primary',required=True,type=Path)
    p.add_argument('--rc-control',required=True,type=Path);p.add_argument('--out',required=True,type=Path);args=p.parse_args()
    if args.out.exists():raise ValueError('refuse to overwrite summary')
    primary=analyze(args.primary);followup=analyze(args.rc_control)
    # Explicitly quantify repeated original arms at the final prefix after chunk regrouping.
    repeat=[]
    for row in followup['fit_rows']:
        matches=[x for x in primary['fit_rows'] if all(x[k]==row[k] for k in ['load','records','arm'])]
        if not matches:continue
        old=matches[0];record={k:row[k] for k in ['load','records','arm']}
        record['status_matches']=row['status']==old['status']
        c=row['comparison'];b=old['comparison']
        if c and b and c['status']==b['status']=='local_converged_diagnostic':
            record['Q_comparison_change_percentage_points']=c['Q_relative_difference_percent']-b['Q_relative_difference_percent']
            record['SOC_comparison_change_pp']=c['exact_transport_SOC_difference_pp']-b['exact_transport_SOC_difference_pp']
        repeat.append(record)
    write(args.out,dict(status='completed_exploratory_not_promoted',primary=primary,RC_followup=followup,
                        repeated_original_fit_controls=repeat,
                        exclusions='Two direct primary fits unresolved; no physical accuracy, calibrated coverage, complete memory or default promotion'))


if __name__=='__main__':main()
