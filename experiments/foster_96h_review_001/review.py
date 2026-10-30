"""Saved96h run review. Read only valid prefixes; no full campaign rerun."""
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from .failures import HERE,ROOT,RUN,identity

def main():
    if (HERE/'review.json').exists():raise FileExistsError('preserved receipt already exists: review.json')
    manifest=json.loads((RUN/'manifest.json').read_text())['artifacts'];checked={}
    def verify(path):
        name=str(path.relative_to(RUN));actual=identity(path);assert actual==manifest[name];checked[name]=actual
    for name in ['summary.json','campaign_plan.json','calibration.json','backend_c/build.json','backend_c/estimator.so']:
        verify(RUN/name)
    summary=json.loads((RUN/'summary.json').read_text());plan=json.loads((RUN/'campaign_plan.json').read_text())
    cases=[];samples={};rate=plan['configuration']['sample_rate_hz']
    for c in summary['cases']:
        path=RUN/c['directory'];arms={};seed=c['scenario']['seed']
        for name in ['result.json','telemetry.json','float64_message.npy','float32_message.npy','stimulus_events.csv']:verify(path/name)
        meta=json.loads((path/'telemetry.json').read_text());columns=meta['trace_columns']
        true_ref=np.array([plan['cells']['A']['parameters'][key.removesuffix('_ref')] for key in columns[22:33]])
        for enc in ['float64','float32']:
            saved=c['arms'][enc];n=saved['outputs'];assert n==meta['valid_trace_rows'][enc]
            tr=np.load(path/(enc+'_trace.npy'),mmap_mode='r')[:n]
            ix=np.unique(np.r_[np.arange(0,n,max(1,round(60*rate/16))),n-1]) if saved['status']=='completed' else np.arange(n)
            a=np.array(tr[ix]);truth=np.load(path/'truth.npy',mmap_mode='r')[a[:,0].astype(np.int64)-1]
            samples[f'{seed}_{enc}']=np.c_[a,100*(a[:,11]/truth[:,5]-1),100*(a[:,6]-truth[:,0]),truth[:,-1]]
            end=tr[-1];m=np.load(path/(enc+'_message.npy'));L=m[16:272].reshape(16,16);sd=np.sqrt((L*L).sum(axis=1))
            full=saved['all'];row=dict(status=saved['status'],valid_outputs=n,last_valid_time_s=float(end[1]),
                failure=saved.get('failure'),Q_SOC_statistics=full,
                nominal_three_SD_miss_fraction={k:full[k+'_3sd_misses']/n for k in ['Q','SOC']},
                final_reference_parameters=dict(zip(columns[22:33],end[22:33].tolist())),
                final_parameter_error_percent=dict(zip(columns[22:33],(100*(end[22:33]/true_ref-1)).tolist())),
                final_approx_Q_three_SD_percent=float(300*sd[5]),final_SOC_three_SD_pp=float(300*sd[0]),
                solver_stops=saved['stops'])
            if saved['status']=='completed':
                start=int(24*3600*rate/16);q=100*(tr[start:,22]/true_ref[0]-1)
                row['last72h_Q_reference_error']={'min_percent':float(q.min()),'max_percent':float(q.max()),
                    'within_half_percent_fraction':float(np.mean(abs(q)<=.5)),
                    'method':'All valid boundaries; known common Arrhenius factor cancels in Q error.'}
            arms[enc]=row
        cases.append(dict(directory=c['directory'],seed=seed,status=c['status'],arms=arms,
            encoding_difference=c['encoding_difference']))
    tr=np.load(RUN/'case_0006/float64_trace.npy',mmap_mode='r')
    peaks={}
    for col,name in [(31,'gamma_plus'),(32,'gamma_minus'),(30,'H_V')]:
        index=int(np.argmax(tr[:,col]));peaks[name]=dict(value=float(tr[index,col]),time_h=float(tr[index,1]/3600),trace_index=index)
    previous=ROOT/'experiments/foster_campaign_001/run_20261030_102748_571075'
    before=json.loads((previous/'campaign_plan.json').read_text())
    changes={k:{'previous':before['configuration'].get(k),'current':v} for k,v in plan['configuration'].items() if before['configuration'].get(k)!=v}
    native=json.loads((RUN/'backend_c/build.json').read_text());old_native=json.loads((previous/'backend_c/build.json').read_text())
    report=dict(status='review_complete; three_history_domain_failures_reproduced; one_sustained_Q_bias_case',
        source=str(RUN.relative_to(ROOT)),configuration=plan['configuration'],cases=cases,seed1006_reference_peaks=peaks,
        comparison_with_500Hz=dict(configuration_changes=changes,physical_cell_definitions_equal=plan['cells']==before['cells'],
            native_source_hashes_equal=native['sources']==old_native['sources'],
            scope='Different seeds, rates and durations prevent causal sample-rate comparison.'),
        short_failure_reproductions=json.loads((HERE/'failures.json').read_text()),
        independent_Python_reproductions=json.loads((HERE/'python_failures.json').read_text()),
        source_manifest=identity(RUN/'manifest.json'),selective_manifest_verification=checked,
        large_arrays='Original memmaps, valid prefixes only. Whole-array hashes not recomputed. Full-run metrics from original summaries; last72h Q scans all valid boundaries; plots use minute samples, all rows for failed prefixes.',
        limits='No coverage certificate, aging qualification, new production code or full96h rerun. Failure location is identified; bounded joint repair is not implemented.')
    with (HERE/'review.json').open('x') as f:json.dump(report,f,indent=2);f.write('\n')
    np.savez_compressed(HERE/'samples.npz',**samples)
    fig,axes=plt.subplots(3,2,figsize=(13,10))
    specs=[(39,'Q error (%)',0),(40,'SOC error (percentage points)',0),(30,'H at25°C (V)',.015),
           (31,'gamma+ at25°C',6),(32,'gamma− at25°C',9)]
    palette={1000:'tab:blue',1002:'tab:green',1003:'tab:purple',1005:'tab:orange',1006:'crimson'}
    for ax,(column,label,truth) in zip(axes.flat,specs):
        for c in cases:
            if c['status']!='completed':continue
            a=samples[f"{c['seed']}_float64"]
            ax.plot(a[:,1]/3600,a[:,column],label=str(c['seed']),color=palette[c['seed']],lw=1.2)
        ax.axhline(truth,color='black',ls='--',lw=1)
        if column in [39,40]:ax.axhspan(-.5,.5,color='green',alpha=.08);ax.set_yscale('symlog',linthresh=.1)
        elif column in [31,32]:ax.set_yscale('log')
        ax.set_xlabel('Simulated hours');ax.set_ylabel(label);ax.grid(alpha=.2)
    axes[0,0].legend(title='Completed seeds',ncol=3,fontsize=8)
    ax=axes[-1,-1]
    for seed,color in [(1001,'tab:orange'),(1004,'tab:blue'),(1007,'tab:purple')]:
        a=samples[f'{seed}_float64'];ax.plot(a[:,1],a[:,10],label=str(seed),color=color)
        failed=next(x for x in report['short_failure_reproductions']['failures'] if x['seed']==seed and x['encoding']=='float64')
        ax.scatter([failed['failure_time_s']],[failed['candidate_h']],marker='x',color=color)
    ax.axhline(-1,color='black',ls='--');ax.set_xlabel('Simulated seconds');ax.set_ylabel('h; crosses mark rejected candidates')
    ax.legend(title='Failed seeds');ax.grid(alpha=.2)
    fig.suptitle('35Hz,96h: four accurate completions, one persistent Q bias, three early rejections\nBinary64; minute samples for completed runs, valid prefixes for failed runs')
    fig.tight_layout();fig.savefig(HERE/'review.png',dpi=150);plt.close(fig)
    print(json.dumps({'cases':len(cases),'verified_artifacts':len(checked),'configuration_changes':changes,'peaks':peaks},indent=2))

if __name__=='__main__':main()
