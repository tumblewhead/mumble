"""Paired cumulative-stage benchmark and sustained numerical comparison."""
import argparse,json,time,platform,hashlib
from pathlib import Path
import numpy as np
from experiments.foster_c_baseline_001.reference import Baseline,library,ROOT
from experiments.foster_c_baseline_001.run import sha
from .build import HERE
CASES={'cccv':ROOT/'experiments/foster_cccv_stimulus_001/cycle001/case_0000',
       'weak':ROOT/'experiments/foster_campaign_001/run_20261030_064220_507192/case_0001'}

def physical(m):
    p=np.exp(m[:,5:16]);p[:,5]+=p[:,3];p[:,7]+=p[:,5];return p

def compare(a,b,ma,mb):
    n=min(len(a),len(b));a=a[:n];b=b[:n]
    if not n:return {'paired':0,'status':'no_outputs'}
    if not np.array_equal(a[:,33],b[:,33]):return {'paired':0,'status':'boundary_mismatch'}
    q=100*np.expm1(a[:,5]-b[:,5]);z=100*(a[:,0]-b[:,0]);pa=physical(a);pb=physical(b)
    A=ma[16:272].reshape(16,16);B=mb[16:272].reshape(16,16);P=A@A.T;Q=B@B.T
    return {'paired':n,'estimates_sd_logZ_stops_bit_identical':bool(np.array_equal(a[:,:35],b[:,:35])),
      'full_final_message_bit_identical':bool(np.array_equal(ma,mb)),
      'max_Q_percent':float(max(abs(q))),'max_SOC_pp':float(max(abs(z))),
      'max_reference_parameter_percent':np.max(abs(100*(pa/pb-1)),axis=0).tolist(),
      'max_chart_mean_abs':np.max(abs(a[:,:16]-b[:,:16]),axis=0).tolist(),
      'max_chart_SD_abs':np.max(abs(a[:,16:32]-b[:,16:32]),axis=0).tolist(),
      'max_logZ_abs':float(max(abs(a[:,32]-b[:,32]))),'final_logZ_difference':float(a[-1,32]-b[-1,32]),
      'final_covariance_max_abs':float(np.max(abs(P-Q))),'final_covariance_relative_Frobenius':float(np.linalg.norm(P-Q)/np.linalg.norm(Q)),
      'stop_differences':int(np.count_nonzero(a[:,34]!=b[:,34])),
      'within_application_scales':bool(max(abs(q))<.5 and max(abs(z))<.5)}

def main(out,repeats):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    libs={s:library(HERE/f'build_host_{s}/baseline.so') for s in range(3)}
    result={'schema':'foster_c_model_benchmark_v1','platform':platform.platform(),'repeats':repeats,'cases':{},'timing_scope':'Instrumented C ingestion, computation and output arrays; excludes initialization, file IO, build and scoring; alternating stage order; no target cycle claim',
      'source_hashes':{str(p.relative_to(ROOT)):sha(p) for p in [HERE/'rolling.c',HERE/'model.c',HERE/'baseline.h',HERE/'build.py',HERE/'benchmark.py',HERE/'plan.json']},
      'binaries':{str(s):sha(HERE/f'build_host_{s}/baseline.so') for s in range(3)}}
    def save():(out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    for name,case in CASES.items():
        obs=np.load(case/'observations.npy',mmap_mode='r');assert np.isfinite(obs).all()
        entry={'case':str(case.relative_to(ROOT)),'observations_sha256':sha(case/'observations.npy'),'records':len(obs),'arms':{}}
        result['cases'][name]=entry
        for enc in [8,4]:
            arms={str(s):{'wall_s':[]} for s in range(3)};entry['arms'][str(enc)]=arms
            reference=None;ref_message=None;sparse_reference=None;sparse_message=None
            for repeat in range(repeats):
                order=list(range(3)) if repeat%2==0 else list(reversed(range(3)))
                for stage in order:
                    c=Baseline(libs[stage],enc);t=time.perf_counter();status,trace=c.replay(obs);elapsed=time.perf_counter()-t
                    message=c.snapshot();arm=arms[str(stage)];arm['wall_s'].append(elapsed)
                    digest=hashlib.sha256(trace.tobytes()+message.tobytes()).hexdigest()
                    if repeat==0:
                        arm.update(status=status,outputs=len(trace),profile=c.profile(),output_sha256=digest)
                        np.save(out/f'{name}_{enc}_stage{stage}_message.npy',message)
                        if stage==0:reference=trace;ref_message=message
                        else:arm['comparison_to_baseline']=compare(trace,reference,message,ref_message)
                        if stage==1:sparse_reference=trace;sparse_message=message
                        if stage==2:arm['comparison_to_sparse']=compare(trace,sparse_reference,message,sparse_message)
                        if stage in [0,2]:np.save(out/f'{name}_{enc}_stage{stage}_trace.npy',trace)
                    elif digest!=arm['output_sha256']:
                        arm['repeat_output_mismatch']=True
                    save();print(name,enc,'repeat',repeat,'stage',stage,'seconds',round(elapsed,4),'status',status,flush=True)
            for stage in range(3):
                arm=arms[str(stage)];arm['median_s']=float(np.median(arm['wall_s']));arm['range_s']=[min(arm['wall_s']),max(arm['wall_s'])]
                arm['median_time_reduction_percent']=100*(1-arm['median_s']/arms['0']['median_s'])
            save()
    result['status']='completed';save()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--repeats',type=int,default=3);a=p.parse_args()
    if a.repeats<1:p.error('repeats must be positive')
    main(a.out,a.repeats)
