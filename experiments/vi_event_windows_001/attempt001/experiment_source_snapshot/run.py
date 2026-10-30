"""Matched-input experiment; inference accepts observations/config only, scoring separate."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
import argparse,ctypes as C,hashlib,json,math,subprocess,time
from pathlib import Path
import numpy as np
from experiments.foster_c_baseline_001.reference import Config,Profile,DP,library,message,ptr
from experiments.foster_campaign_001.coordinates import prior
from experiments.foster_feedback_001.estimator import Model
from .build import build,HERE,ROOT,identity
from .schedule import schedules
UP=C.POINTER(C.c_uint64)
class Bank:
    def __init__(self,binary,cfg):
        self.lib=library(binary);self.context=C.create_string_buffer(self.lib.fb_context_bytes())
        num=cfg['numerical'];c=Config((C.c_double*14)(cfg['reference_temperature_K'],cfg['ocv_intercept_V'],cfg['ocv_slope_V_per_SOC'],*cfg['arrhenius_A_K']),num['max_rounds'],num['fractions'],8,num['gradient_inf_tolerance'],num['latent_step_tolerance'])
        m=message(*prior(cfg));status=self.lib.fb_init(self.context,C.byref(c),C.byref(m),123)
        if status:raise ValueError(('init',status))
        self.lib.experiment_replay.argtypes=[C.c_void_p,DP,C.c_size_t,UP,C.c_size_t,DP,C.c_size_t,C.POINTER(C.c_size_t),DP]
    def replay(self,obs,ends):
        obs=np.ascontiguousarray(obs);ends=np.ascontiguousarray(ends,dtype=np.uint64)
        trace=np.empty((len(ends),36));written=C.c_size_t();stats=np.zeros(4)
        start=time.perf_counter();status=self.lib.experiment_replay(self.context,ptr(obs),len(obs),ends.ctypes.data_as(UP),len(ends),ptr(trace),len(trace),C.byref(written),ptr(stats));elapsed=time.perf_counter()-start
        final=np.empty(273);self.lib.fb_get_message(self.context,ptr(final));p=Profile();self.lib.fb_get_profile(self.context,C.byref(p))
        return trace[:written.value],final,dict(status='completed' if status==0 else 'failed',C_status=status,wall_s=elapsed,retired_records=int(trace[written.value-1,33]) if written.value else 0,tokens=written.value,model_calls=p.model_calls,fit_evaluations=p.fit_evaluations,fit_rounds=p.rounds,estimated_glitch_count=stats[0],effective_precision_sum=stats[1],broad_component_more_probable_count=int(stats[2]),retired_ticks=int(stats[3]),context_bytes=self.lib.fb_context_bytes())

def predict(model,final,future):
    m=final[:16];L=final[16:272].reshape(16,16)
    v,J,_,_=model.evaluate(m,future);r=(v-future[:,3])/future[:,4];B=(J@L)/future[:,4,None]
    chol=np.linalg.cholesky(np.eye(16)+B.T@B);proj=np.linalg.solve(chol,B.T@r)
    quad=float(r@r-proj@proj);logdet=float(2*np.log(np.diag(chol)).sum())
    return dict(records=len(future),joint_predictive_NLL_without_common_noise_constant=.5*(quad+logdet),mean_residual_mV=float(1000*np.mean(v-future[:,3])),RMS_mV=float(1000*np.sqrt(np.mean((v-future[:,3])**2))),scope='Unassimilated original-noise future; full cross-time local Gaussian covariance. Robust arms use their EM surrogate covariance, not exact mixture posterior.')

def score(trace,truth,obs,cfg,rate):
    idx=trace[:,33].astype(int)-1;m=trace[:,:16];sd=trace[:,16:32]
    factor=np.exp(cfg['arrhenius_A_K'][0]*(1/(obs[idx,2]+273.15)-1/cfg['reference_temperature_K']))
    q=np.exp(m[:,5])*factor;true=truth[idx];qe=100*(q/true[:,5]-1);ze=100*(m[:,0]-true[:,0])
    qz=abs(np.log(q/true[:,5]))/sd[:,5];zz=abs(m[:,0]-true[:,0])/sd[:,0]
    late=idx>=len(obs)*.75
    return dict(Q_error_percent=float(qe[-1]),SOC_error_pp=float(ze[-1]),Q_log_zscore=float(qz[-1]),SOC_zscore=float(zz[-1]),Q_3sd_upper_width_percent=float(100*np.expm1(3*sd[-1,5])),SOC_3sd_width_pp=float(300*sd[-1,0]),max_abs_Q_error_percent=float(abs(qe).max()),max_abs_SOC_error_pp=float(abs(ze).max()),late_max_abs_Q_error_percent=float(abs(qe[late]).max()) if late.any() else None,late_max_abs_SOC_error_pp=float(abs(ze[late]).max()) if late.any() else None,late_Q_3sd_miss_fraction=float(np.mean(qz[late]>3)) if late.any() else None,late_SOC_3sd_miss_fraction=float(np.mean(zz[late]>3)) if late.any() else None,scope='Reported-boundary descriptive statistics; correlated misses are not validated coverage.')

def write(path,obj):path.write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')
def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--hours',type=float,default=4);p.add_argument('--future-minutes',type=float,default=30);p.add_argument('--seeds',type=int,nargs='+',default=[1000,1006]);p.add_argument('--conditions',nargs='+',choices=['original','glitches'],default=['original','glitches']);p.add_argument('--schedules',nargs='+',default=['fixed16','fixed12','current','joint_vi','displaced_vi']);p.add_argument('--likelihoods',nargs='+',choices=['gaussian','mixture'],default=['gaussian','mixture']);a=p.parse_args()
    a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=False)
    cfg=json.loads((a.run/'calibration.json').read_text());summary=json.loads((a.run/'summary.json').read_text());rate=summary['sample_rate_Hz'];n=round(a.hours*3600*rate);nf=round(a.future_minutes*60*rate)
    if n<24 or nf<1:raise ValueError('positive prefix>=24 and future required')
    manifest=dict(base_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),command=vars(a).copy(),sources={str(x.relative_to(ROOT)):identity(x) for x in HERE.glob('*') if x.is_file()},input_calibration=identity(a.run/'calibration.json'),input_summary=identity(a.run/'summary.json'),config=cfg)
    manifest['command']['run']=str(a.run);manifest['command']['out']=str(a.out);write(a.out/'manifest.json',manifest)
    binaries={name:build(a.out/name,rate,cfg,0. if name=='gaussian' else .001) for name in a.likelihoods};model=Model(next(iter(binaries.values())),cfg)
    cases=[]
    for case in summary['cases']:
        seed=case['scenario']['seed']
        if seed not in a.seeds:continue
        folder=a.run/case['directory'];source=np.load(folder/'observations.npy',mmap_mode='r')
        if len(source)<n+nf:raise ValueError('source shorter than requested prefix+future')
        original=np.ascontiguousarray(source[:n]);future=np.ascontiguousarray(source[n:n+nf]);reports=[]
        caseout=a.out/f'seed{seed}';caseout.mkdir()
        input_hash=hashlib.sha256(np.ascontiguousarray(source[:n+nf]).tobytes()).hexdigest()
        for condition in a.conditions:
            obs=original.copy();rng=np.random.default_rng(seed+930000)
            mask=rng.random(n)<.001
            if condition=='glitches':obs[mask,3]+=rng.normal(0.,np.sqrt(399.)*obs[mask,4])
            started=time.perf_counter();plans,detector=schedules(obs,cfg['prior_mean_physical']['tau']);detector['wall_s']=time.perf_counter()-started
            for schedule in a.schedules:
                ends=plans[schedule];np.save(caseout/f'{condition}_{schedule}_ends.npy',ends)
                for likelihood,binary in binaries.items():
                    name=f'{condition}_{schedule}_{likelihood}';bank=Bank(binary,cfg)
                    trace,final,result=bank.replay(obs,ends)
                    np.save(caseout/f'{name}_trace.npy',trace)
                    result.update(seed=seed,condition=condition,schedule=schedule,likelihood=likelihood,detector=detector if schedule in ['current','joint_vi','displaced_vi'] else None,final_message=final.tolist(),injected_faults=int(mask.sum()) if condition=='glitches' else 0,observation_sha256=hashlib.sha256(obs.tobytes()).hexdigest(),trace=f'seed{seed}/{name}_trace.npy')
                    if result['status']=='completed':
                        try:result['prediction']=predict(model,final,future)
                        except Exception as exc:result['prediction_error']=repr(exc)
                    reports.append(result);write(caseout/f'{name}.json',result)
                    print(json.dumps({k:result[k] for k in ['seed','condition','schedule','likelihood','status','wall_s','tokens']}),flush=True)
        # Truth is loaded only after all inference and prediction for this case.
        truth=np.load(folder/'truth.npy',mmap_mode='r')
        for r in reports:
            trace=np.load(a.out/r['trace'])
            if len(trace):r['score']=score(trace,truth,original,cfg,rate)
        cases.append(dict(seed=seed,records=n,sample_rate_hz=rate,observation_prefix_and_future_sha256=input_hash,source_directory=str(folder),arms=reports));write(a.out/'result.json',dict(plan=str(HERE/'plan.json'),cases=cases,production_changed=False))
        print('SCORED',seed,flush=True)
    if {c['seed'] for c in cases}!=set(a.seeds):raise ValueError('some requested seeds missing')
if __name__=='__main__':main()
