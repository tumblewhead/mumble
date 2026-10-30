"""Desktop diagnostic of delayed factor retirement; not a firmware proposal."""
import json,math,time
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from experiments.foster_feedback_001.estimator import Model,fit
from experiments.foster_feedback_001.history import GaussianBackend,pack_message,message,pack_kernel
from experiments.foster_campaign_001.coordinates import prior
RUN=Path('/home/easy/proj/mumble/experiments/foster_campaign_001/run_bounded_20261030_185906_868310')
HERE=Path(__file__).resolve().parent

def main():
    out=HERE/'windows001';out.mkdir(exist_ok=False);cfg=json.loads((RUN/'calibration.json').read_text());model=Model(RUN/'backend_c/estimator.so',cfg);backend=GaussianBackend();cases=[]
    for seed in [1000,1006]:
        folder=RUN/f'case_{seed-1000:04d}';n=720000;obs=np.load(folder/'observations.npy',mmap_mode='r')[:n]
        for block in [64,256,1024,8192]:
            m,L=prior(cfg);payload=pack_message(m,L,0.);retired=0;started=time.perf_counter();stop='completed';diagnostics={}
            try:
                for first in range(0,n,block):
                    rows=np.asarray(obs[first:first+block]);m,L,_=message(payload)
                    anchor,physical,d=fit(model,m,L,rows,cfg['numerical']);v,J,end,F=physical
                    token=pack_kernel(anchor,end,F,J/rows[:,4,None],(v-rows[:,3])/rows[:,4],float(np.log(rows[:,4]).sum()+len(rows)*.5*math.log(2*math.pi)),'float64')
                    candidate=backend.advance(payload,SimpleNamespace(payload=token));newm,newL,_=message(candidate);model.evaluate(newm,np.empty((0,5)))
                    payload=candidate;retired+=len(rows);diagnostics[d['stop']]=diagnostics.get(d['stop'],0)+1
            except Exception as e:stop=repr(e)
            elapsed=time.perf_counter()-started;m,L,_=message(payload);sd=np.sqrt(np.sum(L*L,axis=1));truth=np.load(folder/'truth.npy',mmap_mode='r')[retired-1];factor=np.exp(cfg['arrhenius_A_K'][0]*(1/(obs[retired-1,2]+273.15)-1/cfg['reference_temperature_K']));q=np.exp(m[5])*factor
            result=dict(seed=seed,block_records=block,block_seconds=block/50,raw_window_bytes=block*5*8,status=stop,retired_records=retired,wall_s=elapsed,stops=diagnostics,Q_error_percent=float(100*(q/truth[5]-1)),SOC_error_pp=float(100*(m[0]-truth[0])),Q_3sd_upper_width_percent=float(100*np.expm1(3*sd[5])),SOC_3sd_width_pp=float(300*sd[0]),Q_log_zscore=float(abs(np.log(q/truth[5]))/sd[5]),SOC_zscore=float(abs(m[0]-truth[0])/sd[0]))
            cases.append(result);print(json.dumps(result),flush=True);(out/'result.json').write_text(json.dumps(dict(scope='Delayed nonlinear retirement on the same observations; prior and Gaussian history unchanged. No re-use of observations as independent evidence. Raw-window byte counts exclude all solver workspace.',cases=cases),indent=2)+'\n')
if __name__=='__main__':main()
