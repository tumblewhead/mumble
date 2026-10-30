"""Replay a bounded prefix of saved observations; truth is used only for scoring."""
import argparse
import json
from pathlib import Path
import time
import numpy as np
from experiments.foster_campaign_001.backend import prepare_c
from experiments.foster_campaign_001.coordinates import prior
from experiments.foster_c_baseline_001.reference import Baseline,library

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--hours',type=float,default=4.);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    cfg=json.loads((a.run/'calibration.json').read_text());cfg['hysteresis_chart']='bounded'
    summary=json.loads((a.run/'summary.json').read_text());rate=summary['sample_rate_Hz'];n=round(a.hours*3600*rate)
    binary,build=prepare_c(a.out,rate,cfg);lib=library(binary);results=[]
    for case in summary['cases']:
        folder=a.run/case['directory'];obs=np.load(folder/'observations.npy',mmap_mode='r');truth=np.load(folder/'truth.npy',mmap_mode='r')
        for enc,width in [('float64',8),('float32',4)]:
            bank=Baseline(lib,width,initial=prior(cfg));start=time.perf_counter();status,trace=bank.replay(obs[:n]);elapsed=time.perf_counter()-start
            ix=trace[:,33].astype(int)-1
            q=np.exp(trace[:,5])*np.exp(cfg['arrhenius_A_K'][0]*(1/(obs[ix,2]+273.15)-1/cfg['reference_temperature_K']))
            qe=100*(q/truth[ix,5]-1);ze=100*(trace[:,0]-truth[ix,0]);late=ix>=min(n//2,round(3600*rate))
            record=dict(seed=case['scenario']['seed'],encoding=enc,status=int(status),retired_records=int(trace[-1,33]) if len(trace) else 0,wall_s=elapsed,final_Q_percent=float(qe[-1]),final_SOC_pp=float(ze[-1]),max_abs_eta=float(np.max(abs(trace[:,4]))),late_max_abs_Q_percent=float(np.max(abs(qe[late]))) if late.any() else None,late_max_abs_SOC_pp=float(np.max(abs(ze[late]))) if late.any() else None,profile=bank.profile())
            results.append(record);print(json.dumps({k:v for k,v in record.items() if k!='profile'}),flush=True)
            (a.out/'summary.json').write_text(json.dumps(dict(source=str(a.run),records_per_arm=n,hours=a.hours,rate_Hz=rate,build=build,cases=results),indent=2)+'\n')
if __name__=='__main__':main()
