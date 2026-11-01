"""Preserved-prefix C/Python parity and host timings; no truth in inference."""
import argparse
import json
from pathlib import Path
import time
import numpy as np
from experiments.field_feedback_preservation_001.numerics import Tangent
from experiments.foster_campaign_001.backend import identity
from experiments.foster_campaign_001.coordinates import prior
from experiments.foster_uncertainty_audit_001.conditional_packet import partition
from experiments.joint_rate_history_001.field import Field,build as build_field
from experiments.slow_likelihood_diagnostic_001.numerics import Compressed,solve
from .native import Native,build

BASE=Path(__file__).resolve().parents[1]/'uncertainty_weak_stimulus_001/attempt001'
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=False);binary=build(args.out/'native');probe=build_field(args.out/'response');results=[]
    for label in ['owner_case_0000','owner_case_0002','owner_case_0004','owner_case_0006','weak_B_cycle']:
        case=BASE/label;reg=json.loads((case/'regeneration.json').read_text())
        if identity(case/'observations.npy')!=reg['observations']:raise ValueError('preserved observations changed')
        cfg=json.loads((case/'calibration.json').read_text());mean,L=prior(cfg)
        f=Field(cfg,partition(mean)[1],1.,5,probe,source=reg['observations']['sha256'])
        obs=np.load(case/'observations.npy',mmap_mode='r');n=reg['fit_records'];interval=reg['field_counts']['field_history']['refresh_interval_records']
        first=(n//interval*interval if label=='weak_B_cycle' else n-interval)
        for i in range(0,first,4096):f.update(i,obs[i:min(i+4096,first)])
        objective=Compressed(f,mean,L);fit=solve(objective)
        if fit['diagnostic']['stop'] not in ('GN_decrement_at_cost_roundoff','gradient'):raise ValueError('anchor unresolved')
        a=Native(binary,f,mean,L);a.initialize(fit['w']);b=Tangent(objective,fit['w'],first)
        errors=dict(w_abs=0.,endpoint_abs=0.,covariance_abs=0.,Q_percent=0.,SOC_pp=0.,Q_SD_relative=0.)
        timing=dict(native_s=0.,python_s=0.);windows=0
        for i in range(first,n,16):
            rows=f.update(i,obs[i:i+16],return_rows=True)
            start=time.perf_counter();a.update(i,rows);actual=a.query();timing['native_s']+=time.perf_counter()-start
            start=time.perf_counter();b.update(i,rows);expected=b.query();timing['python_s']+=time.perf_counter()-start;windows+=1
            ar=actual['endpoint_root'];br=expected['endpoint_root']
            values=dict(w_abs=np.max(abs(actual['w']-expected['w'])),endpoint_abs=np.max(abs(actual['end']-expected['end'])),
                        covariance_abs=np.max(abs(ar@ar.T-br@br.T)),Q_percent=abs(100*np.expm1(actual['end'][5]-expected['end'][5])),
                        SOC_pp=100*abs(actual['end'][0]-expected['end'][0]),Q_SD_relative=abs(np.linalg.norm(ar[5])/np.linalg.norm(br[5])-1))
            for key,value in values.items():errors[key]=max(errors[key],float(value))
        result=dict(label=label,windows=windows,first_record=first,end_record=n,errors=errors,timing=timing,
                    storage=a.storage(),observations=reg['observations'],status='passed' if errors['endpoint_abs']<1e-8 and errors['covariance_abs']<1e-9 else 'failed')
        results.append(result);print(json.dumps(result),flush=True)
    output=dict(schema='native_tangent_parity_v1',cases=results,truth_reads=0,binary=identity(binary),
                sources={name:identity(Path(__file__).parent/name) for name in ('kernel.c','kernel.h','native.py','qualify.py')},
                timing_scope='Same preserved suffixes, single BLAS thread; ctypes update+nonlinear readout, common field accumulation and refresh excluded; host only')
    (args.out/'result.json').write_text(json.dumps(output,indent=2)+'\n')
    if any(r['status']!='passed' for r in results):raise SystemExit(1)
if __name__=='__main__':main()
