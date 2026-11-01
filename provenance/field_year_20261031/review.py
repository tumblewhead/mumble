"""Read bounded summaries, not raw streams; preserve original evidence identities."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import numpy as np

PARAMETERS=['Q_Ah','R0_ohm','R1_ohm','tau1_s','R2_ohm','tau2_s','R3_ohm','tau3_s','H_V','gamma_plus','gamma_minus']


def identity(path):
    b=path.read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())


def review(run,out,plots):
    manifest=json.loads((run/'manifest.json').read_text())['artifacts'];identities={}
    def checked(name):
        path=run/name;value=identity(path)
        if name in manifest and value!=manifest[name]:raise ValueError('Evidence checksum mismatch: '+name)
        identities[name]=value
        return path
    summary=json.loads(checked('summary.json').read_text())
    plan=json.loads(checked('campaign_plan.json').read_text())
    reservation=json.loads(checked('reservation.json').read_text())
    checked('calibration.json')
    rows=[];plotdata=[]
    for case in summary['cases']:
        name=case['directory'];telemetry=json.loads(checked(name+'/telemetry.json').read_text())
        scenario=json.loads(checked(name+'/scenario.json').read_text());checked(name+'/result.json')
        cols=telemetry['estimate_columns'];true=np.array([scenario['cell_definition']['parameters'][k] for k in PARAMETERS])
        report=dict(directory=name,scenario=case['scenario'],hours=case['simulation_hours'],records=case['records'],arms={})
        with np.load(checked(name+'/plot_summary.npz'),allow_pickle=False) as bins:
            for arm in ('float64','field64'):
                original=case['arms'][arm];means=bins[arm+'_mean'];low=bins[arm+'_low'];high=bins[arm+'_high'];count=bins[arm+'_count']
                first=bins[arm+'_first']/case['sample_rate_Hz']/3600;last=bins[arm+'_last']/case['sample_rate_Hz']/3600
                assert int(count.sum())==original['all']['outputs']
                assert int(bins[arm+'_last'][-1])==case['records']==original['retired_records']
                message=np.load(checked(name+'/'+arm+'_message.npy'),allow_pickle=False)
                assert message.shape==(273,) and np.isfinite(message).all()
                L=message[16:272].reshape(16,16);physical=np.exp(message[5:16]);physical[5]+=physical[3];physical[7]+=physical[5]
                errors=100*(physical/true-1)
                a=dict(status=original['status'],all=original['all'],final_reference_parameter_errors_percent=dict(zip(PARAMETERS,map(float,errors))),
                    final_Q_log_SD_percent=float(100*np.linalg.norm(L[5])),
                    final_Q_signed_local_SD=float((message[5]-np.log(true[0]))/np.linalg.norm(L[5])),
                    final_SOC_SD_pp=float(100*np.linalg.norm(L[0])),
                    Q_3SD_miss_fraction=original['all']['Q_3sd_misses']/original['all']['outputs'],
                    SOC_3SD_miss_fraction=original['all']['SOC_3sd_misses']/original['all']['outputs'],
                    field_history=original.get('field_history'),storage=original['storage'],bands=[])
                for begin,end in [(24,720),(720,2160),(2160,4320),(4320,6480),(6480,8766),(720,8766)]:
                    select=(first>=begin)&(last<=end);w=count[select]
                    band=dict(requested_hours=[begin,end],actual_hours=[float(first[select][0]),float(last[select][-1])],outputs=int(w.sum()),metrics={})
                    for quantity in ('Q_error_percent','SOC_error_pp','Q_log_sd','SOC_sd','V_truth_error_mV'):
                        j=cols.index(quantity);scale=100 if quantity in ('Q_log_sd','SOC_sd') else 1
                        band['metrics'][quantity]=dict(weighted_mean=float(np.average(means[select,j],weights=w)*scale),
                            maximum_absolute=float(max(abs(low[select,j]).max(),abs(high[select,j]).max())*scale),scale=scale)
                    if begin==6480:
                        band['RC_maximum_absolute_percent']={k:float(max(abs(100*(low[select,cols.index(k+'_ref')]/true[i]-1)).max(),abs(100*(high[select,cols.index(k+'_ref')]/true[i]-1)).max())) for i,k in enumerate(PARAMETERS) if 1<=i<=7}
                    a['bands'].append(band)
                report['arms'][arm]=a
                plotdata.append(dict(case=name,scenario=case['scenario'],arm=arm,hours=means[:,cols.index('time_s')]/3600,first_hours=first,
                    q=means[:,cols.index('Q_error_percent')],qsd=100*means[:,cols.index('Q_log_sd')],
                    tau1=100*(means[:,cols.index('tau1_s_ref')]/true[3]-1)))
        rows.append(report)
    pooled={}
    for noise in (.002,.02):
        group=[r for r in rows if r['scenario']['noise_v']==noise];pooled[str(noise)]={}
        for arm in ('float64','field64'):
            values=[r['arms'][arm]['all'] for r in group];n=sum(x['outputs'] for x in values)
            pooled[str(noise)][arm]=dict(Q_RMSE_percent=float(np.sqrt(sum(x['outputs']*x['Q_RMSE_percent']**2 for x in values)/n)),
                SOC_RMSE_pp=float(np.sqrt(sum(x['outputs']*x['SOC_RMSE_pp']**2 for x in values)/n)),
                joint_0p5_target_fraction=sum(x['joint_within_target'] for x in values)/n,
                Q_3SD_miss_fraction=sum(x['Q_3sd_misses'] for x in values)/n,
                SOC_3SD_miss_fraction=sum(x['SOC_3sd_misses'] for x in values)/n)
    sizes={}
    for base,_,files in os.walk(run):
        for name in files:
            f=Path(base)/name;category='checkpoints' if 'checkpoints' in f.parts else f.suffix
            sizes[category]=sizes.get(category,0)+f.stat().st_size
    result=dict(schema='stationary_field_year_review_v1',status='completed_review',source_run=str(run),
        source_revision=reservation['source_revision'],source_branch=reservation['branch'],configuration=plan['configuration'],
        scope=plan['assumptions'],cases=rows,pooled=pooled,total_samples=sum(r['records'] for r in rows),
        total_case_hours=sum(r['hours'] for r in rows),refresh_attempts=sum(r['arms']['field64']['field_history']['attempts'] for r in rows),
        refresh_rejections=sum(r['arms']['field64']['field_history']['rejected'] for r in rows),
        file_storage_B=dict(total=sum(sizes.values()),by_category=sizes),
        summary_semantics='Global RMSE from original every-update counters, including startup. Time-band means are weighted by counts; extrema are extrema of actual updates in fully contained4.383hbins. No RMS of bin means is presented as sample RMS.',
        interpretation=['Eight8766hstationary-cell cases completed, with both arms surviving. This does not test tangent, aging, cellB or real battery mismatch.',
            'Field point errors remain small late; RC identification greatly improves over the rolling-only arm on difficult seeds.',
            'Low-noise Q bias persists around minus0.0045..0.0048percent while final localSD is0.000095percent:47..50localSD. High-noise finalQ is4.6..5.2localSD.',
            'Observed behavior is consistent with a persistent approximation/model bias plus shrinking local curvature uncertainty, not proof of its cause. No full retained-data reference was solved here.',
            'Repeated outputs are correlated; miss fractions are diagnostics, not independent coverage trials. Assimilated voltage residuals are not proposed-load forecast errors.'],
        next='Use early,720h and late checkpoints to separate compressed-likelihood gradient/state-transport error, numerical accumulation and sensor/model likelihood bias. Propagate identified discrepancy jointly; no arbitrary forgetting or scalar inflation.',
        evidence=identities)
    plots.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault('MPLCONFIGDIR',tempfile.mkdtemp(prefix='mumble-year-mpl-'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    colors=['#0072b2','#d55e00','#009e73','#cc79a7']
    fig,axes=plt.subplots(2,2,figsize=(13,8),sharex=True,constrained_layout=True)
    for col,noise in enumerate((.002,.02)):
        selected=[r for r in plotdata if r['scenario']['noise_v']==noise and r['arm']=='field64']
        for color,r in zip(colors,selected):
            mask=r['first_hours']>=24;t=r['hours'][mask];q=r['q'][mask];sd=r['qsd'][mask]
            label=f"seed {r['scenario']['seed']} / load {r['scenario']['load_seed']}"
            axes[0,col].plot(t,q,color=color,lw=1,label=label)
            axes[0,col].fill_between(t,q-3*sd,q+3*sd,color=color,alpha=.1)
            axes[1,col].plot(t,abs(q)/sd,color=color,lw=1)
        axes[0,col].axhline(0,color='black',lw=.7);axes[0,col].set_title(f'Field history / {1000*noise:g} mV noise')
        axes[0,col].legend(fontsize=8);axes[1,col].axhline(3,color='black',ls=':',lw=.8)
        axes[0,col].set_ylabel('Capacity error (%)\nBin mean and ±3 mean local SD')
        axes[1,col].set_ylabel('|Bin mean Q error| / mean local SD\nDescriptive ratio, not coverage')
        axes[1,col].set_xlabel('Simulated hours (log scale)')
        for ax in axes[:,col]:ax.set_xscale('log');ax.grid(alpha=.2)
    fig.suptitle('One stationary year: small persistent bias, shrinking reported uncertainty\nOriginal 4.383 h summaries; first 24 h omitted to show sustained behavior')
    fig.savefig(plots/'uncertainty.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(13,5),constrained_layout=True)
    for ax,noise in zip(axes,(.002,.02)):
        for index,r in enumerate([r for r in plotdata if r['scenario']['noise_v']==noise]):
            case_index=int(r['case'].split('_')[1])%4;mask=r['first_hours']>=24
            label=f"{r['arm']} / seed {r['scenario']['seed']} / load {r['scenario']['load_seed']}"
            ax.plot(r['hours'][mask],r['tau1'][mask],color=colors[case_index],ls='-' if r['arm']=='field64' else '--',lw=1,label=label)
        ax.axhline(0,color='black',lw=.7);ax.set_xscale('log');ax.set_yscale('symlog',linthresh=1)
        ax.set_title(f'{1000*noise:g} mV noise');ax.set_xlabel('Simulated hours (log scale)');ax.set_ylabel('Fast RC time-constant error (%)\nSigned symlog, linear within ±1%');ax.legend(fontsize=7);ax.grid(alpha=.2)
    fig.suptitle('Fast RC identification: field history versus rolling only / bin means')
    fig.savefig(plots/'rc_tau1.png',dpi=170);plt.close(fig)
    result['derived_plots']={str(f):identity(f) for f in plots.glob('*.png')}
    for name,value in identities.items():
        if identity(run/name)!=value:raise ValueError('Evidence changed during review')
    out.write_text(json.dumps(result,indent=2)+'\n')
    print('Review: '+str(out))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--out',type=Path,required=True);p.add_argument('--plots',type=Path,required=True)
    a=p.parse_args();review(a.run.resolve(),a.out.resolve(),a.plots.resolve())
