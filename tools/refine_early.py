#!/usr/bin/env python3
"""Supplement the frozen 220 s result using only its same-prefix profile fit.

The frozen 60-fit campaign remains unchanged. No truth or future observations
are supplied to the optimizer. Truth enters independent post-fit scoring only.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np
from assess import assess_result as qualify
from validate import assess_result as score

ROOT = Path(__file__).resolve().parents[1]
CASE = 'cell_a_35hz_s202610240'

def main():
    profiles = json.loads((ROOT/'results/profile_results.json').read_text())
    profile = next(p for p in profiles['profiles']
                   if p['case_id']==CASE and p['checkpoint_s']==220 and p['target']=='Q_Ah')
    evaluated = [p for p in profile['evaluations'] if p['status']=='evaluated']
    best = min(evaluated, key=lambda p:p['result']['objective_full'])
    source = json.loads((ROOT/'results/streaming_results.json').read_text())
    original = next(r for r in source['records']
                    if r['case_id']==CASE and r['checkpoint_s']==220)
    exe = ROOT/'build/scm_estimator_benchmark'
    if not exe.exists(): exe = ROOT/'build/scm_estimator'
    cmd = [str(exe),'--data',str(ROOT/'data'/f'{CASE}.csv'),'--case',CASE,
           '--modes','3','--method','full','--sigma','.001','--prefix','7700',
           '--starts','5','--max-iter','300','--initial',
           ','.join(format(v,'.17g') for v in best['result']['theta'])]
    p = subprocess.run(cmd,capture_output=True,text=True)
    output = {'schema':'scm_same_prefix_refinement_v1','case_id':CASE,
              'checkpoint_s':220,'command':cmd,'returncode':p.returncode,
              'binary_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),
              'initial_source':'Best tested same-prefix capacity-profile candidate',
              'future_data_used':False,'truth_used_by_optimizer':False,
              'original_campaign_unchanged':True,
              'original_objective':original['result']['objective_full'],
              'profile_candidate_objective':best['result']['objective_full']}
    if p.returncode:
        output['stderr']=p.stderr
    else:
        fit=json.loads(p.stdout)
        manifest=json.loads((ROOT/'data/manifest.json').read_text())
        case=next(c for c in manifest['cases'] if c['case_id']==CASE)
        data=np.loadtxt(ROOT/'data'/case['csv'],delimiter=',',skiprows=1)[:7700]
        output.update(result=fit,scores=score(fit,case['truth'],data[:,1],data[:,2],data[:,3],sigma=.001),
                      assessment=qualify(fit),
                      improvement_over_original=original['result']['objective_full']-fit['objective_full'])
    (ROOT/'results/refinement_220.json').write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:output[k] for k in ['case_id','checkpoint_s','returncode','original_objective','profile_candidate_objective','improvement_over_original'] if k in output}))
    if output.get('result'):
        print(json.dumps({'status':output['result']['status'],'Q_Ah':output['scores']['physical_parameters']['Q_Ah'],
                          'SOC_error_pp':output['scores']['current_SOC_error_pp']}))

if __name__=='__main__':main()
