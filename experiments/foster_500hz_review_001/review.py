"""Read-only review of the saved500Hz campaign; sample large arrays by memmap."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
RUN=ROOT/'experiments/foster_campaign_001/run_20261030_102748_571075'

def identity(path):
    return dict(bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())

def main():
    manifest=json.loads((RUN/'manifest.json').read_text())['artifacts']
    checked={}
    def verify(path):
        rel=str(path.relative_to(RUN));actual=identity(path)
        assert actual==manifest[rel],rel
        checked[rel]=actual
    for name in ['summary.json','campaign_plan.json','calibration.json','backend_c/build.json']:
        verify(RUN/name)
    summary=json.loads((RUN/'summary.json').read_text())
    plan=json.loads((RUN/'campaign_plan.json').read_text())
    cfg=json.loads((RUN/'calibration.json').read_text())
    cases=[];samples={};outlier=[]
    # A minute-spaced sample is diagnostic visualization, not extrema or coverage.
    stride=1875  #16*1875/500=60 seconds
    for c in summary['cases']:
        path=RUN/c['directory'];seed=c['scenario']['seed'];arms={}
        for file in ['result.json','telemetry.json','float64_message.npy','float32_message.npy','stimulus_events.csv']:
            verify(path/file)
        for encoding in ['float64','float32']:
            tr=np.load(path/(encoding+'_trace.npy'),mmap_mode='r')
            n=c['arms'][encoding]['outputs'];assert n==len(tr)
            ix=np.unique(np.r_[np.arange(0,n,stride),n-1]);trace=np.array(tr[ix])
            truth=np.load(path/'truth.npy',mmap_mode='r')[trace[:,0].astype(np.int64)-1]
            qerr=100*(trace[:,11]/truth[:,5]-1);zerr=100*(trace[:,6]-truth[:,0])
            samples[f'{seed}_{encoding}']=np.c_[trace,qerr,zerr,truth[:,-1]]
            m=np.load(path/(encoding+'_message.npy'));L=m[16:272].reshape(16,16)
            endpoint=tr[-1];sd=np.sqrt(np.sum(L*L,axis=1))
            # Parameter order follows the recorded telemetry rather than dictionary order.
            columns=json.loads((path/'telemetry.json').read_text())['trace_columns']
            ref=np.array([plan['cells']['A']['parameters'][key.removesuffix('_ref')] for key in columns[22:33]])
            tau_sd=[]
            for k in range(3):
                derivative=np.zeros(16)
                for j in range(k+1):derivative[8+2*j]=np.exp(m[8+2*j])
                tau_sd.append(float(np.linalg.norm(derivative@L)))
            a=c['arms'][encoding];stats=a['all']
            arms[encoding]=dict(final_reference_parameters=dict(zip(columns[22:33],endpoint[22:33].tolist())),
                final_parameter_error_percent=dict(zip(columns[22:33],(100*(endpoint[22:33]/ref-1)).tolist())),
                Q_SOC_statistics=stats,solver_stops=a['stops'],counts={k:a[k] for k in ['received_records','retired_records','pending_records','tokens']},
                three_SD_miss_fraction={k:stats[k+'_3sd_misses']/n for k in ['Q','SOC']},
                final_Q_3SD_percent_approx=float(300*sd[5]),final_SOC_3SD_pp=float(300*sd[0]),
                final_tau_delta_method_SD_s=tau_sd,
                minute_sample_voltage_RMSE_mV=float(1000*np.sqrt(np.mean((trace[:,5]-truth[:,-1])**2))))
        cases.append(dict(directory=c['directory'],seed=seed,arms=arms,encoding_difference=c['encoding_difference']))
    tr=np.load(RUN/'case_0000/float64_trace.npy',mmap_mode='r')
    for level in [10,100,1000]:
        coarse=np.flatnonzero(tr[::stride,27]>level);end=int(coarse[0]*stride)
        begin=max(0,end-stride);window=np.array(tr[begin:end+1]);index=begin+int(np.flatnonzero(window[:,27]>level)[0])
        outlier.append(dict(tau2_threshold_s=level,trace_index=index,record_count=int(tr[index,0]),time_s=float(tr[index,1]),
            reference_tau_s=tr[index,[25,27,29]].tolist(),current_A=float(tr[index,2]),
            method='first minute-grid detection, refined within preceding minute; earlier unsampled excursions not excluded'))
    with (RUN/'case_0000/stimulus_events.csv').open() as f:events=list(csv.DictReader(f))
    nearby=[e for e in events if 4.25*3600<=float(e['time_s'])<=5*3600]
    report=dict(source=str(RUN.relative_to(ROOT)),source_manifest=identity(RUN/'manifest.json'),
        configuration=plan['configuration'],status='saved_run_review_complete; RC_and_uncertainty_failures_unresolved',
        review_base_revision=__import__('subprocess').check_output(['git','rev-parse','HEAD'],text=True).strip(),
        cases=cases,seed5_growth_markers=outlier,seed5_nearby_stimulus_events=nearby,
        selective_manifest_verification=checked,
        large_array_handling='Read original memmaps at minute spacing, endpoints and bounded onset slices; full multi-gigabyte array hashes not recomputed. Large-array declared hashes remain in source manifest.',
        scope='No solver rerun or mutation. Full-run metrics are original summaries; sampled voltage/plots are labeled. No causal attribution or physical coverage qualification.')
    with (HERE/'review.json').open('x') as f:json.dump(report,f,indent=2);f.write('\n')
    np.savez_compressed(HERE/'minute_samples.npz',**samples)
    plot_samples(samples,cases)
    print(json.dumps({'cases':len(cases),'verified_small_artifacts':len(checked),'seed5_markers':outlier},indent=2))

def plot_samples(samples,cases):
    palette=['crimson','tab:blue','tab:orange','tab:green','tab:purple','tab:brown','tab:pink','tab:gray']
    fig,axes=plt.subplots(3,2,figsize=(13,10),sharex=True)
    configs=[(39,'Q error (%)',0),(40,'SOC error (percentage points)',0),(23,'R0 at25°C (ohm)',.1),
             (25,'tau1 at25°C (s)',.05),(27,'tau2 at25°C (s)',.5),(29,'tau3 at25°C (s)',5)]
    for ax,(column,label,truth) in zip(axes.flat,configs):
        for case_index,c in enumerate(cases):
            a=samples[f"{c['seed']}_float64"];color=palette[case_index]
            ax.plot(a[:,1]/3600,a[:,column],label=f"seed {c['seed']}",color=color,linewidth=1.2,alpha=.9)
        ax.axhline(truth,color='black',linestyle='--',linewidth=1)
        if column in [39,40]:ax.axhspan(-.5,.5,color='green',alpha=.08);ax.set_yscale('symlog',linthresh=.1)
        elif column in [25,27,29]:ax.set_yscale('log')
        ax.set_ylabel(label);ax.grid(alpha=.2)
    axes[0,0].legend(ncol=2,fontsize=8)
    for ax in axes[-1]:ax.set_xlabel('Simulated hours')
    fig.suptitle('500Hz,48h: Q/SOC settle while one seed loses the RC spectrum\nMinute-spaced binary64 samples; dashed lines are plant truth')
    fig.tight_layout();fig.savefig(HERE/'review.png',dpi=150);plt.close(fig)

if __name__=='__main__':main()
