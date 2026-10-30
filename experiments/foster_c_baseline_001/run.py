"""Replay an existing campaign case through C; never regenerate observations or fit truth."""
import argparse,hashlib,json,platform,time
from pathlib import Path
import numpy as np
from .reference import Baseline,HERE,ROOT,library

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def run(case,out,encodings=(8,4),limit=None,binary=None):
    if limit is not None and limit<=0:raise ValueError('records must be positive')
    case=Path(case).resolve();out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    obs=np.load(case/'observations.npy',mmap_mode='r');obs=obs[:limit] if limit else obs
    if obs.ndim!=2 or obs.shape[1]!=5 or not len(obs) or not np.isfinite(obs).all():raise ValueError('invalid observation file')
    old=json.loads((case/'result.json').read_text()) if (case/'result.json').exists() else {}
    lib=library(binary);summary=dict(case=str(case.relative_to(ROOT)),observations_sha256=sha(case/'observations.npy'),records=len(obs),simulated_s=float(obs[:,0].sum()),machine=platform.platform(),context_bytes=lib.fb_context_bytes(),arms={},source_revision='a3878e17c720ee399b458a005f47e809e4bdd5cc',limits='Host timing; no target cycles. Gaussian uncertainty and aging remain unqualified.')
    for enc in encodings:
        name='float'+str(enc*8);c=Baseline(lib,enc);t=time.perf_counter();status,trace=c.replay(obs);elapsed=time.perf_counter()-t
        np.save(out/(name+'_trace.npy'),trace);np.save(out/(name+'_message.npy'),c.snapshot())
        p=c.profile();report=dict(status='completed' if status==0 else 'failed',code=status,outputs=len(trace),wall_s=elapsed,simulated_seconds_per_wall_second=summary['simulated_s']/elapsed,profile=p)
        phases={k:p[k] for k in ['before_s','fit_s','token_s','history_s','domain_s']};report['phase_percent_of_sum']={k:100*v/sum(phases.values()) for k,v in phases.items()}
        refpath=case/(name+'_chart.npy');trpath=case/(name+'_trace.npy')
        if refpath.exists() and trpath.exists():
            ref=np.load(refpath,mmap_mode='r');tr=np.load(trpath,mmap_mode='r')
            valid=old.get('arms',{}).get(name,{}).get('outputs',len(ref))
            n=min(len(trace),valid);ref=ref[:n];tr=tr[:n];a=trace[:n]
            # Compare only matching source boundaries (partial-prefix flush differs).
            match=a[:,33]==tr[:,0];a=a[match];ref=ref[match];tr=tr[match]
            if not len(a):
                report['python_comparison']={'paired_outputs':0,'status':'no_matching_outputs'}
                summary['arms'][name]=report
                (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
                continue
            q=100*np.expm1(a[:,5]-ref[:,5]);soc=100*(a[:,0]-ref[:,0]);sd_diff=a[:,16:32]-ref[:,16:32]
            report['python_comparison']=dict(paired_outputs=len(a),max_Q_percent=float(max(abs(q))),max_SOC_pp=float(max(abs(soc))),final_Q_percent=float(q[-1]),final_SOC_pp=float(soc[-1]),max_chart_mean_abs=np.max(abs(a[:,:16]-ref[:,:16]),axis=0).tolist(),max_chart_sd_abs=np.max(abs(sd_diff),axis=0).tolist(),max_logZ_abs=float(max(abs(a[:,32]-tr[:,38]))),final_logZ_difference=float(a[-1,32]-tr[-1,38]),within_application_scales=bool(max(abs(q))<.5 and max(abs(soc))<.5),reference_hashes={str(path.relative_to(ROOT)):sha(path) for path in [refpath,trpath,case/'result.json']})
        summary['arms'][name]=report
        (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        print(name,report,flush=True)
    return summary
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--case',type=Path,default=ROOT/'experiments/foster_cccv_stimulus_001/cycle001/case_0000');p.add_argument('--out',type=Path,required=True);p.add_argument('--encoding',choices=['float64','float32','both'],default='both');p.add_argument('--records',type=int);p.add_argument('--binary',type=Path);a=p.parse_args()
    run(a.case,a.out,(8,4) if a.encoding=='both' else (8 if a.encoding=='float64' else 4,),a.records,a.binary)
