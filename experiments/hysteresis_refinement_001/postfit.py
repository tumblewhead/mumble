"""Separate postfit truth scoring; requires all candidate fits already frozen."""
import argparse
import json
from pathlib import Path
import numpy as np
from experiments.uncertainty_weak_stimulus_001.diagnostics import identity,write
from experiments.tangent_development_001.forecast import path,segments
from experiments.foster_feedback_001.plant import scalar_step
from experiments.foster_campaign_001.telemetry import thermal

PARAMS=['Q_Ah','R0_ohm','R1_ohm','tau1_s','R2_ohm','tau2_s','R3_ohm','tau3_s','H_V','gamma_plus','gamma_minus']


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--runs',nargs=2,type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    jobs=[]
    for run in a.runs:
        index=json.loads((run/'index.json').read_text())
        if index['status']!='complete':raise ValueError('unfinished study')
        res=json.loads((run/'reservation.json').read_text());cmd=res['command'];seed=int(cmd[cmd.index('--seed')+1])
        for case in index['cases']:
            file=Path(case['result']);r=json.loads(file.read_text())
            if identity(file)!=case['identity']:raise ValueError('changed fit')
            if r['status'] not in ('complete_local_diagnostic','complete_with_transport_limit'):raise ValueError('unresolved fit')
            jobs.append((seed,file,r))
    if a.out.exists():raise ValueError('output exists')
    a.out.mkdir(parents=True)
    rows=[]
    for seed,file,r in jobs:
        inputs=Path(f'experiments/shared_uncertainty_growth_001/inputs{seed}')
        truthfile=inputs/f"scoring_only_{r['records']}.json";s=json.loads(truthfile.read_text())
        cfg=json.loads((inputs/'calibration.json').read_text());state=np.asarray(s['endpoint'][:5]);ref=np.array([s['parameters'][k] for k in PARAMS])
        pp=ref.copy();pp[7]-=ref[5];pp[5]-=ref[3]
        chart=np.r_[state[:4],np.arctanh(state[4]),np.log(pp)]
        q=r['fit']['x'][5];sd=np.linalg.norm(np.array(r['fit']['root'])[5])
        row=dict(seed=seed,hours=r['hours'],records=r['records'],degree=r['storage']['hysteresis_degree'],
            storage=r['storage'],build_wall_s=r['build_wall_s'],diagnostics=r['diagnostics'],transport=r['transport'],
            Q_error_percent=float(100*np.expm1(q-np.log(ref[0]))),Q_error_SD=float((q-np.log(ref[0]))/sd),
            fit_stop=r['fit']['diagnostic']['stop'],evidence=dict(result=identity(file),result_path=str(file.resolve()),truth=identity(truthfile)),forecasts=[])
        for info in r['forecasts']:
            if info['status']!='supported':row['forecasts'].append(info);continue
            f=file.parent/info['file']
            if identity(f)!=info['file_identity']:raise ValueError('changed forecast')
            with np.load(f) as data:
                physical=ref*thermal(cfg,info['temperature_C']);current=state.tolist();before=0.;actual=[]
                for t,I in zip(data['times'],data['current']):
                    current,v=scalar_step(current,physical,float(t-before),float(I),cfg['ocv_intercept_V'],cfg['ocv_slope_V_per_SOC'])
                    actual.append(v);before=t
                error=data['voltage']-actual
                truepath=path(chart,segments(info['task_definition'],50),cfg,info['temperature_C'],50,grid=True)
                out={k:v for k,v in info.items() if k not in ('probes','file_identity')}
                out.update(truth_RMS_error_uV=float(1e6*np.sqrt(np.mean(error**2))),truth_max_error_uV=float(1e6*np.max(abs(error))),
                    truth_minimum_error_uV=float(1e6*(info['minimum_V']-truepath['minimum_V'])),
                    truth_recovery_error_uV=float(1e6*error[-1]),
                    pointwise_3SD_miss_fraction=float(np.mean(abs(error)>3*data['local_sd_V'])),
                    mean_local_SD_uV=float(1e6*np.mean(data['local_sd_V'])))
                row['forecasts'].append(out)
        rows.append(row)
    write(a.out/'scores.json',dict(status='postfit_scoring_complete',cases=rows,
        limitations='Selected two-seed forecasts, correlated points, not calibrated coverage or lifetime guarantee'))
    print(a.out/'scores.json')

if __name__=='__main__':main()
