"""Analyze frozen system trials; no estimator changes or truth-based fitting."""
import json
from pathlib import Path
import numpy as np
from .campaign import HERE, ROOT, CASES, read
from experiments.structured_joint_001.qualify import ident, write


def main():
    campaign=HERE/'campaign001';out=HERE/'review001';out.mkdir(exist_ok=False)
    reports={};inputs={}
    for name in CASES:
        path=campaign/name/'result.json';r=read(path);inputs[str(path.relative_to(ROOT))]=ident(path)
        legacy=np.load(campaign/name/'legacy_blocks.npy')
        inputs[str((campaign/name/'legacy_blocks.npy').relative_to(ROOT))]=ident(campaign/name/'legacy_blocks.npy')
        lookup={int(row[0])-1:row for row in legacy}
        paired=[]
        for cp in r['checkpoints']:
            if cp['index'] not in lookup or 'float32' not in cp['arms']:continue
            row=lookup[cp['index']];h=cp['arms']['float32']
            paired.append(dict(time_s=cp['time_s'],history_Q_percent=100*(h['Q']/cp['truth_Q']-1),
                               legacy_Q_percent=100*(row[1]/cp['truth_Q']-1),
                               history_SOC_pp=100*(h['SOC']-cp['truth_SOC']),legacy_SOC_pp=100*(row[3]-cp['truth_SOC'])))
        phases={}
        for label,lo,hi in [('learning',0,5400),('weak',5400,10800),('renewed',10800,14401)]:
            cps=[c for c in r['checkpoints'] if lo<c['time_s']<=hi and c['predictive']]
            innovations=[c['predictive']['standardized_innovation'] for c in cps]
            phases[label]=dict(count=len(cps),innovation_mean=float(np.mean(innovations)) if cps else None,
                 innovation_RMS=float(np.sqrt(np.mean(np.square(innovations)))) if cps else None,
                 innovation_3sd_misses=sum(abs(x)>3 for x in innovations),
                 interpretation='Saved-checkpoint pre-update predictive diagnostics; single correlated trajectory, not calibrated coverage')
        h=r['arms']['float32'];ref=r['arms']['float64']
        reference_complete=ref['status']=='completed' and ref['records']==504000
        encoding_complete=h['status']=='completed' and h['records']==504000
        reports[name]=dict(arms=r['arms'],wall_s=r['wall_s'],cpu_s=r['cpu_s'],
            predictive_phases=phases,common_checkpoints=paired,
            gates=dict(reference_complete=reference_complete,encoding_complete=encoding_complete,
                 encoding_preserves_preferred_scales=reference_complete and encoding_complete and
                      h.get('max_history_Q_percent',float('inf'))<=.5 and h.get('max_history_SOC_pp',float('inf'))<=.5,
                 weak_all_preferred=h['phase']['weak']['count']==189000 and h['phase']['weak']['joint_preferred_fraction']==1,
                 renewed_all_preferred=h['phase']['renewed']['count']==126000 and h['phase']['renewed']['joint_preferred_fraction']==1))

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,4,figsize=(16,7),layout='constrained',sharex=True)
    for col,name in enumerate(CASES):
        r=read(campaign/name/'result.json');legacy=np.load(campaign/name/'legacy_blocks.npy')
        truth=np.load(campaign/'inputs'/(name+'_truth.npy'),mmap_mode='r')
        for kind,color in [('float64','#222222'),('float32','#17806e')]:
            cps=[c for c in r['checkpoints'] if kind in c['arms']]
            t=[c['time_s']/3600 for c in cps]
            axes[0,col].plot(t,[100*(c['arms'][kind]['Q']/c['truth_Q']-1) for c in cps],color=color,label=kind,lw=1.3)
            axes[1,col].plot(t,[100*(c['arms'][kind]['SOC']-c['truth_SOC']) for c in cps],color=color,label=kind,lw=1.3)
        if len(legacy):
            rows=legacy[::100];ix=rows[:,0].astype(int)-1
            axes[0,col].plot(rows[:,0]/126000,100*(rows[:,1]/truth[ix,0]-1),color='#b55e28',label='legacy rolling',lw=1)
            axes[1,col].plot(rows[:,0]/126000,100*(rows[:,3]-truth[ix,2]),color='#b55e28',label='legacy rolling',lw=1)
        for row in range(2):
            ax=axes[row,col];ax.axhspan(-.5,.5,color='#d9edd9',alpha=.55)
            ax.axvspan(1.5,3,color='#999999',alpha=.15);ax.set_yscale('symlog',linthresh=.5)
            ax.grid(alpha=.2);ax.set_xlim(0,4)
        axes[0,col].set_title(name.replace('_',' '));axes[1,col].set_xlabel('Simulated hours')
    axes[0,0].set_ylabel('Q error (% relative)');axes[1,0].set_ylabel('SOC error (percentage points)')
    axes[0,0].legend(fontsize=8)
    fig.suptitle('System controls: shaded rest interval; linear error scale within ±0.5, logarithmic outside')
    fig.savefig(out/'system_errors.png',dpi=160);fig.savefig(out/'system_errors.pdf');plt.close(fig)
    summary=dict(schema='system_history_review_v1',cases=reports,input_identities=inputs,
                 records_per_case=504000,total_distinct_observations=2016000,simulated_hours_total=16,
                 qualification_checks=read(campaign/'qualification/result.json')['passing_checks'],
                 partial_history_payload_B=14580,complete_SRAM_B=None,
                 inference_modified=False,feedback_integrated=False,coverage_validated=False,
                 scope='Independent whole-stream system comparison. Binary32/binary64 isolates encoding; legacy has different prior/noise/model/history and is not a causal compressor contrast.')
    write(out/'result.json',summary)
    print(json.dumps({name:dict(gates=r['gates'],arms={k:dict(status=s['status'],final=s.get('final'),
        weak=s['phase']['weak'],renewed=s['phase']['renewed']) for k,s in r['arms'].items()}) for name,r in reports.items()}))


if __name__=='__main__':main()
