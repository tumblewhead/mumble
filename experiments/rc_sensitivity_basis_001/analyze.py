"""Compact accounting, including every status and endpoint SOC width."""
import argparse
import json
from pathlib import Path
import numpy as np
from experiments.hysteresis_mixed_completion_001.analyze import analyze
from experiments.foster_uncertainty_audit_001.conditional_packet import partition
from experiments.foster_campaign_001.backend import identity
from experiments.h7_history_quality_001.history import write


def summary(directory):
    result=analyze(directory)
    reg=json.loads((directory/'registration.json').read_text());center=np.array(reg['center'])
    for case in result['case_files']:
        v=json.loads((directory/case['file']).read_text())
        for prefix in v['prefixes']:
            for name,fit in prefix['fits']['arms'].items():
                target=next(r for r in result['fit_rows'] if (r['load'],r['records'],r['arm'])==(v['load'],prefix['records'],name))
                target['SOC_width']=fit.get('SOC_width')
                if 'selected' in fit:
                    _,shape=partition(np.array(fit['selected']['x']))
                    target['fitted_log_tau_offset']=np.log(shape[:3]/center[:3]).tolist()
    return result


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--pilot',required=True,type=Path);p.add_argument('--full',required=True,type=Path)
    p.add_argument('--control',type=Path,default=Path('experiments/hysteresis_mixed_completion_001/rc001'));p.add_argument('--out',required=True,type=Path);args=p.parse_args()
    if args.out.exists():raise ValueError('refuse overwrite')
    pilot=summary(args.pilot);full=summary(args.full);controls=[]
    for case in full['case_files']:
        oldpath=args.control/case['file'];old=json.loads(oldpath.read_text());new=json.loads((args.full/case['file']).read_text())
        for prefix in new['prefixes']:
            prev=next(x for x in old['prefixes'] if x['records']==prefix['records'])
            if prev['observation_sha256']!=prefix['observation_sha256']:raise ValueError('control input changed')
            for name in ['direct','R2_H2','R5_H2','R5_H7']:
                a=prefix['fits']['arms'][name];b=prev['fits']['arms'][name]
                shift=float(np.max(abs(np.array(a['selected']['x'])-np.array(b['selected']['x']))))
                controls.append(dict(load=new['load'],records=prefix['records'],arm=name,status_matches=a['status']==b['status'],
                    max_origin_chart_difference=shift,original_case=identity(oldpath)))
    write(args.out,dict(status='completed_exploratory_not_promoted',pilot=pilot,full=full,repeated_controls=controls,
          scope='Finite public probes and local fits, two active one-hour examples; no truth accuracy, coverage, lifetime or firmware qualification'))


if __name__=='__main__':main()
