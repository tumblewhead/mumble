"""Read-only aggregate scoring and plots; no fitting or input mutation."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ.setdefault('MPLCONFIGDIR','/tmp/vi-event-mpl')
import argparse,json,hashlib
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from .build import HERE,ROOT,identity

COLORS={'fixed16_gaussian':'#1f77b4','joint_vi_gaussian':'#d62728','sparse_vi_gaussian':'#ff7f0e','fixed16_mixture':'#2ca02c','sparse_vi_mixture':'#9467bd'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    rows=[];cases={};receipts={}
    for folder in ['attempt001','attempt002','multiscale001']:
        path=HERE/folder/'result.json';data=json.loads(path.read_text());receipts[str(path.relative_to(ROOT))]=identity(path)
        for c in data['cases']:
            seed=c['seed'];cases[seed]=c
            for r in c['arms']:
                row={k:r[k] for k in ['seed','condition','schedule','likelihood','status','retired_records','tokens','wall_s','model_calls','fit_evaluations','fit_rounds','estimated_glitch_count','effective_precision_sum','broad_component_more_probable_count','retired_ticks','context_bytes','injected_faults','score','prediction','detector'] if k in r}
                row['experiment']=folder;row['source_observation_sha256']=r['observation_sha256'];row['prefix_and_future_sha256']=c['observation_prefix_and_future_sha256'];rows.append(row)
    # Older four-hour baseline has the exact same public-prior replay; compare all273 values.
    old=json.loads((ROOT/'experiments/foster_uncertainty_audit_001/attempt001/result.json').read_text());parity=[]
    initial=json.loads((HERE/'attempt001/result.json').read_text())
    for c in initial['cases']:
        new=next(r for r in c['arms'] if r['condition']=='original' and r['schedule']=='fixed16' and r['likelihood']=='gaussian')
        previous=next(x for x in old['cases'] if x['seed']==c['seed']);prior=next(x for x in previous['streaming'] if x['rounds']==4)
        m=np.array(new['final_message']);b=np.array(prior['message']);parity.append(dict(seed=c['seed'],array_equal=bool(np.array_equal(m,b)),max_absolute_difference=float(abs(m-b).max()),retained_reference_score=previous['retained']['score']))
    summary=dict(schema='vi_event_windows_results_v1',complete_arms=sum(r['status']=='completed' for r in rows),total_arms=len(rows),hours_per_arm=4,future_minutes=30,baseline_parity=parity,result_receipts=receipts,arms=rows,limits=['Three streams, two cell definitions and two noise levels; not an independently randomized coverage study.','All parameters stationary; no aging claim.','Original Gaussian and mixture local surrogates remain overconfident on some paths.','Event detector has24-record horizon and only step/first-order templates.','No samples duplicated or dropped from committed likelihood; mixture downweights rather than discards.','Offline schedule shuffles control grouping but are not a deployable scheduler.'],storage=dict(existing_C_context_bytes=19416,detector_raw24_record_buffer_bytes=960,context_plus_separate_raw_buffer_bytes=20376,mixture_token_additional_explicit_stack_array_bytes=640,total_embedded_SRAM_measured=False,detector_implementation='NumPy/Python desktop reference; native RTL timing unmeasured'))
    (a.out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    for seed,c in cases.items():
        truth=np.load(Path(c['source_directory'])/'truth.npy',mmap_mode='r');obs=np.load(Path(c['source_directory'])/'observations.npy',mmap_mode='r');cfg=json.loads((HERE/next(r['experiment'] for r in rows if r['seed']==seed)/'manifest.json').read_text())['config']
        fig,axes=plt.subplots(2,2,figsize=(13,8),sharex=True)
        for col,condition in enumerate(['original','glitches']):
            for r in rows:
                key=r['schedule']+'_'+r['likelihood']
                if r['seed']!=seed or r['condition']!=condition or key not in COLORS:continue
                trace=np.load(HERE/r['experiment']/f"seed{seed}"/f"{condition}_{key}_trace.npy",mmap_mode='r');ix=trace[:,33].astype(int)-1
                # Small min/max bins retain extrema; chronological point order within bin preserved.
                factor=np.exp(cfg['arrhenius_A_K'][0]*(1/(obs[ix,2]+273.15)-1/cfg['reference_temperature_K']))
                err=[100*(np.exp(trace[:,5])*factor/truth[ix,5]-1),100*(trace[:,0]-truth[ix,0])]
                for j,y in enumerate(err):
                    keep=[]
                    for begin in range(0,len(y),64):
                        stop=min(begin+64,len(y));local=y[begin:stop];keep.extend(sorted({begin,stop-1,begin+int(local.argmin()),begin+int(local.argmax())}))
                    keep=np.array(keep);axes[j,col].plot((ix[keep]+1)/50/3600,y[keep],label=key.replace('_',' '),color=COLORS[key],lw=.9,alpha=.85)
            axes[0,col].set_title(f'Seed {seed}: {condition}')
            for j in range(2):
                axes[j,col].axhspan(-.5,.5,color='gray',alpha=.12);axes[j,col].set_yscale('symlog',linthresh=.5);axes[j,col].grid(alpha=.2);axes[j,col].set_ylabel('Q error (%)' if j==0 else 'SOC error (pp)')
            axes[1,col].set_xlabel('Simulated hours')
        handles,labels=axes[0,0].get_legend_handles_labels();fig.legend(handles,labels,loc='lower center',ncol=3,fontsize=9);fig.suptitle('Event windows and explicit ADC-noise model — shaded band ±0.5; symmetric log error axes');fig.tight_layout(rect=(0,.09,1,.96));fig.savefig(a.out/f'errors_seed{seed}.png',dpi=160);plt.close(fig)
    print(json.dumps(dict(complete=summary['complete_arms'],arms=summary['total_arms'],baseline_parity=parity)),flush=True)
if __name__=='__main__':main()
