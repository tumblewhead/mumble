"""Local stationarity and future-data checks; no refitting or truth reads."""
import json,math
from pathlib import Path
import numpy as np
from experiments.foster_feedback_001.estimator import Model
from experiments.foster_campaign_001.coordinates import prior
HERE=Path(__file__).resolve().parent
RUN=Path('/home/easy/proj/mumble/experiments/foster_campaign_001/run_bounded_20261030_185906_868310')

def main():
    output=HERE/'predictive001';output.mkdir(exist_ok=False)
    cfg=json.loads((RUN/'calibration.json').read_text());model=Model(RUN/'backend_c/estimator.so',cfg);audit=json.loads((HERE/'attempt001/result.json').read_text());results=[]
    for case in audit['cases']:
        seed=case['seed'];n=case['records'];obs=np.load(RUN/f'case_{seed-1000:04d}/observations.npy',mmap_mode='r');future=np.asarray(obs[n:n+90000])
        retained=case['retained'];x=np.array(retained['initial_chart']);m,L=prior(cfg)
        v,J,_,_=model.evaluate(x,np.asarray(obs[:n]));B=J@L/obs[:n,4,None];res=(v-obs[:n,3])/obs[:n,4];w=np.linalg.solve(L,x-m);g=w+B.T@res;P=np.eye(16)+B.T@B
        step=np.linalg.solve(P,g);decrement=float(g@step)
        stationarity=dict(gradient_inf=float(abs(g).max()),GN_newton_decrement_squared=decrement,estimated_cost_improvement=.5*decrement,cost_ulp=float(np.spacing(retained['cost'])),max_prior_latent_step=float(abs(step).max()),scope='Local GN stationarity only; not a global-optimum or posterior-coverage proof.')
        predictions=[]
        bank=[]
        for c in case['streaming']:
            message=np.array(c['message']);bank.append((f"rolling_rounds{c['rounds']}",message[:16],message[16:272].reshape(16,16)))
        bank.append(('retained',np.array(retained['endpoint']),np.array(retained['endpoint_root'])))
        for name,mean,root in bank:
            v,J,_,_=model.evaluate(mean,future);r=(v-future[:,3])/future[:,4];B=J@root/future[:,4,None];C=np.linalg.cholesky(np.eye(16)+B.T@B);proj=np.linalg.solve(C,B.T@r);quad=float(r@r-proj@proj);logdet=float(2*np.log(np.diag(C)).sum())
            predictions.append(dict(method=name,records=len(future),joint_predictive_NLL_without_common_noise_constant=.5*(quad+logdet),fixed_point_standardized_RMS=float(np.sqrt(np.mean(r*r))),mean_residual_mV=float(1000*np.mean(v-future[:,3])),joint_quadratic=quad,log_covariance_determinant_ratio=logdet))
        results.append(dict(seed=seed,stationarity=stationarity,predictions=predictions));print(json.dumps(results[-1]),flush=True)
    (output/'result.json').write_text(json.dumps(dict(scope='Next30minutes, not assimilated into either fitted posterior. Full low-rank cross-time predictive covariance included via Woodbury, not independent pointwise interval counting. All approximations remain local Gaussian.',cases=results),indent=2)+'\n')
if __name__=='__main__':main()
