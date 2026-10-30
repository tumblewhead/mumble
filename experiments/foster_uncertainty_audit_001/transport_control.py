"""Candidate only: relinearize deterministic state transport after conditioning."""
import json,subprocess,time
from pathlib import Path
import numpy as np
from experiments.foster_c_baseline_001.reference import Baseline,library
from experiments.foster_campaign_001.coordinates import prior
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
RUN=Path('/home/easy/proj/mumble/experiments/foster_campaign_001/run_bounded_20261030_185906_868310')

def main():
    out=HERE/'transport001';out.mkdir(exist_ok=False)
    core=ROOT/'experiments/foster_c_history_001';base=ROOT/'experiments/foster_c_baseline_001';model=ROOT/'experiments/foster_bounded_hysteresis_001/model.c'
    cfg=json.loads((RUN/'calibration.json').read_text());commands=[]
    for stage in [0,1]:
        binary=out/f'stage{stage}.so';cmd=['cc','-std=c11','-O2','-fno-fast-math','-ffp-contract=off','-Wall','-Wextra','-Werror','-pedantic','-shared','-fPIC','-DFB_PROFILE','-D_POSIX_C_SOURCE=200809L','-DFB_CLOCK_HZ=1050','-DFB_OPT_STAGE=3','-DFB_MODEL_STAGE=2','-DFB_HISTORY_STAGE=2',f'-DFB_TRANSPORT_STAGE={stage}','-include',str(core/'baseline.h'),'-I',str(core),str(HERE/'rolling_transport.c'),str(base/'numeric.c'),str(core/'history.c'),str(model),'-lm','-o',str(binary)];subprocess.run(cmd,check=True);commands.append(cmd)
    reference=library(RUN/'backend_c/estimator.so');cases=[]
    for seed in [1000,1006]:
        folder=RUN/f'case_{seed-1000:04d}';n=720000;obs=np.asarray(np.load(folder/'observations.npy',mmap_mode='r')[:n]);truth=np.load(folder/'truth.npy',mmap_mode='r')[n-1]
        original=Baseline(reference,8,initial=prior(cfg));assert original.replay(obs)[0]==0
        for stage in [0,1]:
            bank=Baseline(library(out/f'stage{stage}.so'),8,initial=prior(cfg));started=time.perf_counter();status,trace=bank.replay(obs);elapsed=time.perf_counter()-started
            if stage==0:assert bank.snapshot().tobytes()==original.snapshot().tobytes()
            m=bank.snapshot();root=m[16:272].reshape(16,16);sd=np.sqrt(np.sum(root*root,axis=1));factor=np.exp(cfg['arrhenius_A_K'][0]*(1/(obs[int(trace[-1,33])-1,2]+273.15)-1/cfg['reference_temperature_K']));q=np.exp(m[5])*factor
            record=dict(seed=seed,stage=stage,status=status,retired_records=int(trace[-1,33]),wall_s=elapsed,context_bytes=bank.lib.fb_context_bytes(),Q_error_percent=float(100*(q/truth[5]-1)) if status==0 else None,SOC_error_pp=float(100*(m[0]-truth[0])) if status==0 else None,Q_3sd_upper_width_percent=float(100*np.expm1(3*sd[5])),SOC_3sd_width_pp=float(300*sd[0]))
            cases.append(record);print(json.dumps(record),flush=True)
    (out/'result.json').write_text(json.dumps(dict(commands=commands,cases=cases,stage0_matches_saved_binary=True,production_modified=False),indent=2)+'\n')
if __name__=='__main__':main()
