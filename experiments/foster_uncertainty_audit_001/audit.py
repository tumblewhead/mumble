"""Retained-observation MAP diagnostic; no truth in objectives or initial guesses."""
import argparse,json,time
from pathlib import Path
import numpy as np
from experiments.foster_feedback_001.estimator import Model,fit
from experiments.foster_campaign_001.coordinates import prior
from experiments.foster_c_baseline_001.reference import Baseline,library


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--hours',type=float,default=4);p.add_argument('--seeds',type=int,nargs='+',default=[1000,1006]);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    config=json.loads((a.run/'calibration.json').read_text());summary=json.loads((a.run/'summary.json').read_text());n=round(a.hours*3600*summary['sample_rate_Hz']);binary=a.run/'backend_c/estimator.so';model=Model(binary,config);lib=library(binary);reports=[]
    for case in summary['cases']:
        if case['scenario']['seed'] not in a.seeds:continue
        folder=a.run/case['directory'];obs=np.ascontiguousarray(np.load(folder/'observations.npy',mmap_mode='r')[:n]);mean,L=prior(config)
        streams=[]
        for rounds in [4,12,32]:
            bank=Baseline(lib,8,initial=(mean,L),settings={'rounds':rounds});started=time.perf_counter();status,trace=bank.replay(obs)
            streams.append(dict(rounds=rounds,status=status,wall_s=time.perf_counter()-started,message=bank.snapshot().tolist(),profile=bank.profile()))
        print('streaming controls complete seed',case['scenario']['seed'],flush=True)
        settings={**config['numerical'],'max_rounds':40,'fractions':16}
        started=time.perf_counter()
        try:
            anchor,physical,diag=fit(model,mean,L,obs,settings)
            v,J,end,F=physical;residual=(v-obs[:,3])/obs[:,4];B=(J@L)/obs[:,4,None];w=np.linalg.solve(L,anchor-mean)
            chol=np.linalg.cholesky(np.eye(16)+B.T@B);initial_root=np.linalg.solve(chol,L.T).T;endroot=F@initial_root
            gradient=w+B.T@residual
            retained=dict(status='completed',diagnostics=diag,gradient_inf=float(abs(gradient).max()),wall_s=time.perf_counter()-started,initial_chart=anchor.tolist(),endpoint=end.tolist(),endpoint_root=endroot.tolist(),initial_root=initial_root.tolist(),cost=float(.5*(w@w+residual@residual)),residual_RMS=float(np.sqrt(np.mean(residual**2))))
        except Exception as e:retained=dict(status='failed',error=repr(e),wall_s=time.perf_counter()-started)
        # Truth is opened only after every inference objective above has finished.
        truth=np.load(folder/'truth.npy',mmap_mode='r')[n-1];factor=np.exp(config['arrhenius_A_K'][0]*(1/(obs[-1,2]+273.15)-1/config['reference_temperature_K']))
        def score(m,root):
            sd=np.sqrt(np.sum(root*root,axis=1));q=np.exp(m[5])*factor
            return dict(Q_error_percent=float(100*(q/truth[5]-1)),SOC_error_pp=float(100*(m[0]-truth[0])),Q_3sd_upper_width_percent=float(100*np.expm1(3*sd[5])),SOC_3sd_width_pp=float(300*sd[0]),Q_log_zscore=float(abs(np.log(q/truth[5]))/sd[5]),SOC_zscore=float(abs(m[0]-truth[0])/sd[0]))
        for stream in streams:
            m=np.array(stream['message']);stream['score']=score(m[:16],m[16:272].reshape(16,16))
        if retained['status']=='completed':retained['score']=score(end,endroot)
        reports.append(dict(seed=case['scenario']['seed'],records=n,hours=a.hours,streaming=streams,retained=retained))
        (a.out/'result.json').write_text(json.dumps(dict(scope='Same observations and public prior. Retained MAP/GN curvature is a local diagnostic, not an exact posterior or coverage oracle.',cases=reports),indent=2)+'\n')
        print(json.dumps(dict(seed=case['scenario']['seed'],streaming=[dict(rounds=s['rounds'],score=s['score']) for s in streams],retained={k:retained[k] for k in retained if k not in ['initial_chart','endpoint','endpoint_root','initial_root']})),flush=True)
if __name__=='__main__':main()
