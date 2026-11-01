"""Read-only campaign review; raw inputs, checkpoints and results stay unchanged."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from experiments.foster_campaign_001.telemetry import PARAMETERS,physical,thermal

ROOT=Path(__file__).resolve().parents[2]
ARMS=('float64','field64','tangent64')
LABELS=('Original rolling','Current field arm','Native tangent')
COLORS=('#3165b4','#009E73','#9b4db5')
def identity(p):return dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def rc_step(p,t):
    return p[1]+np.sum(p[[2,4,6]][None,:]*(-np.expm1(-t[:,None]/p[[3,5,7]][None,:])),axis=1)
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('campaign',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=True);summary=json.loads((a.campaign/'summary.json').read_text());cfg=json.loads((a.campaign/'calibration.json').read_text());plan=json.loads((a.campaign/'campaign_plan.json').read_text())
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    artifacts={};cases=[];t=np.r_[0.,np.geomspace(.001,60,1500)]
    np.testing.assert_array_equal(rc_step(np.array([1,.1,.04,.05,.08,.5,.12,5,1,1,1]),np.array([0.])),[.1])
    source_differences=[name for name,h in plan['campaign_sources'].items() if identity(ROOT/name)!=h]
    for c in summary['cases']:
        case=a.campaign/c['directory'];cell=json.loads((case/'scenario.json').read_text())['cell_definition'];truth=np.array([cell['parameters'][k] for k in PARAMETERS]);arms={}
        for name in ('result.json','scenario.json','plot_summary.npz','checkpoints/index.json'):
            artifacts[str((case/name).relative_to(a.campaign))]=identity(case/name)
        with np.load(case/'plot_summary.npz') as z:
            for arm in ARMS:
                path=case/(arm+'_message.npy');artifacts[str(path.relative_to(a.campaign))]=identity(path)
                message=np.load(path);ref,_=physical(message[:16],cfg,25);L=message[16:272].reshape(16,16);sd=np.linalg.norm(L,axis=1)
                corr=float(L[5]@L[13]/sd[5]/sd[13]);rc=[]
                for T in (17,25,33):
                    _,param=physical(message[:16],cfg,T);error=.12*(rc_step(param,t)-rc_step(truth*thermal(cfg,T),t))*1000
                    rc.append(dict(temperature_C=T,max_abs_RC_step_error_mV=float(np.max(abs(error)))))
                late=z[arm+'_first']/(50*3600)>=48
                relative_band=100*(z[arm+'_high'][late,22:33]-z[arm+'_low'][late,22:33])/truth
                metrics=c['arms'][arm]['all']
                arms[arm]=dict(metrics=metrics,history=c['arms'][arm].get('field_history'),
                    final_parameter_errors_percent=dict(zip(PARAMETERS,(100*(ref/truth-1)).tolist())),
                    final_C_errors_percent=(100*((ref[[3,5,7]]/ref[[2,4,6]])/(truth[[3,5,7]]/truth[[2,4,6]])-1)).tolist(),
                    final_Q_log_SD_percent=float(100*sd[5]),final_SOC_SD_pp=float(100*sd[0]),Q_H_log_correlation=corr,
                    final_SOC_standardized_error=float(metrics['final_SOC_pp']/(100*sd[0])),
                    late48_72h_p95_within_bin_parameter_span_percent=dict(zip(PARAMETERS,np.quantile(relative_band,.95,axis=0).tolist())),
                    isolated_RC_step_120mA=rc)
        cases.append(dict(case=c['directory'],scenario=c['scenario'],arms=arms))
    groups={}
    for load in ('embedded','cycle'):
        selected=[c for c in cases if c['scenario']['load']==load];group={}
        for arm in ARMS:
            count=sum(c['arms'][arm]['metrics']['outputs'] for c in selected)
            group[arm]={k:float(np.sqrt(sum(c['arms'][arm]['metrics'][k]**2*c['arms'][arm]['metrics']['outputs'] for c in selected)/count)) for k in ('Q_RMSE_percent','SOC_RMSE_pp')}
            group[arm].update({k+'_percent':100*sum(c['arms'][arm]['metrics'][k] for c in selected)/count for k in ('Q_3sd_misses','SOC_3sd_misses')})
            group[arm]['refresh_rejections']=sum((c['arms'][arm]['history'] or {}).get('rejected',0) for c in selected)
        groups[load]=group
    replays={}
    for case_id in ('case_0006','case_0007','case_0011'):
        directory=a.out/(case_id+'_replay');r=json.loads((directory/'result.json').read_text());assert r['status']=='completed'
        cell=json.loads((directory/'scenario.json').read_text())['cell_definition']['parameters']
        names=['Q_Ah','H_V','gamma_plus','gamma_minus'];truth=np.array([cell[k] for k in names]);arms={}
        fig,axes=plt.subplots(5,3,figsize=(15,12),sharex=True,sharey='row',layout='constrained')
        with np.load(a.campaign/case_id/'plot_summary.npz') as bins:
            for col,arm in enumerate(ARMS):
                x=np.load(directory/(arm+'_trace.npy'))[:r['arms'][arm]['outputs']];v=x[:,[22,30,31,32]];error=100*(v/truth-1)
                difference=np.diff(error,axis=0);refresh=x[1:,0].astype(np.int64)%3008==0;corr=np.corrcoef(np.diff(np.log(v),axis=0).T)[0,1]
                verified=0;physical_mean_error=0.
                for b in np.flatnonzero((bins[arm+'_first']>=x[0,0])&(bins[arm+'_last']<=x[-1,0])):
                    rows=x[(x[:,0]>=bins[arm+'_first'][b])&(x[:,0]<=bins[arm+'_last'][b])]
                    assert len(rows)==bins[arm+'_count'][b]
                    np.testing.assert_array_equal(rows.min(axis=0),bins[arm+'_low'][b,:39]);np.testing.assert_array_equal(rows.max(axis=0),bins[arm+'_high'][b,:39])
                    physical_mean_error=max(physical_mean_error,float(np.max(abs(rows.mean(axis=0)[2:]-bins[arm+'_mean'][b,2:39]))));verified+=1
                arms[arm]=dict(span_percent_of_true=dict(zip(names,np.ptp(error,axis=0).tolist())),
                    median_abs_refresh_jump_percentage_points=dict(zip(names,np.median(abs(difference[refresh]),axis=0).tolist())),
                    median_abs_other_jump_percentage_points=dict(zip(names,np.median(abs(difference[~refresh]),axis=0).tolist())),
                    log_Q_H_increment_correlation=float(corr),verified_complete_bin_min_max_pairs=verified,max_physical_bin_mean_difference=physical_mean_error)
                minute=(x[:,1]-r['record_offset']/50)/60
                for j in range(4):
                    axes[j,col].plot(minute,error[:,j],lw=.7,color=COLORS[col]);axes[j,col].axhline(0,color='black',lw=.5)
                    if col==0:axes[j,col].set_ylabel(names[j]+' error (% of truth)')
                axes[4,col].plot(minute,x[:,2]*1000,lw=.7,color='#555555');axes[4,col].set_xlabel('Minutes from replay start')
                axes[4,0].set_ylabel('Current (mA)');axes[0,col].set_title(LABELS[col])
                if arm!='float64':
                    for point in minute[x[:,0].astype(np.int64)%3008==0]:
                        for j in range(4):axes[j,col].axvline(point,color='#777777',ls=':',lw=.5,alpha=.5)
                for ax in axes[:,col]:ax.grid(alpha=.15)
        fig.suptitle(case_id+' — '+str(r['scenario'])+'\nFull-resolution outputs; reference-temperature parameters; dotted lines = 60.16 s refresh. Shared scales across arms.')
        target=a.out/(case_id+'_Q_H_gamma.png');fig.savefig(target,dpi=150);plt.close(fig)
        replays[case_id]=dict(interval_hours=[r['record_offset']/50/3600,(r['record_offset']+r['records'])/50/3600],arms=arms,
                             result_identity=identity(directory/'result.json'),plot=str(target.resolve().relative_to(ROOT)))
    receipt=dict(schema='field_tangent_72h_review_v1',source_campaign=str(a.campaign),source_summary=identity(a.campaign/'summary.json'),configuration=plan['configuration'],
        source_differences=source_differences,completed_cases=summary['completed_cases'],completed_arms=sum(v['status']=='completed' for c in summary['cases'] for v in c['arms'].values()),
        pooled_by_load=groups,Q_RMSE_improved_cases=sum(c['arms']['tangent64']['metrics']['Q_RMSE_percent']<c['arms']['field64']['metrics']['Q_RMSE_percent'] for c in cases),
        SOC_RMSE_improved_cases=sum(c['arms']['tangent64']['metrics']['SOC_RMSE_pp']<c['arms']['field64']['metrics']['SOC_RMSE_pp'] for c in cases),
        cases=cases,replay_diagnostics=replays,original_artifacts=artifacts,
        response_diagnostic=dict(formula='DeltaV_RC(t)=-DeltaI*(R0+sum Ri*(1-exp(-t/taui)))',current_step_A=.12,time_grid_s=[0,.001,60],positive_grid_points=1500,
        scope='Final point parameters; isolated incremental ohmic/Foster step at fixed temperature. Excludes SOC/OCV/hysteresis changes, existing polarization, joint uncertainty, wiring/regulator and cutoff. Not a brownout qualification. Sub-sample times are model extrapolation.'),
        interpretation=['48/48 arms complete; candidate reduces SOC RMSE in16/16 and Q RMSE in13/16 cases.',
        'Large late Q/H/gamma excursions are primarily current field arm in weak cycle controls; replay confirms reset-aligned jumps. Candidate strongly suppresses them.',
        'Both field arms share weak-cycle capacity/hysteresis ambiguity and late embedded overconfidence. Neither current result proves calibrated brownout bounds.',
        'Final RC estimates nearly identical between field and tangent; RC accuracy and held-out voltage forecasts remain separate work.'],
        recommendation='Merge as an opt-in implementation; retain current default until explicit promotion review. Next qualify causal proposed-load forecasts with joint uncertainty, keeping weak-Q/H ambiguity and field approximation bias visible.',
        limits=['16 stationary synthetic cases, two noise seeds and one embedded load seed; no aging or real hardware.',
        'Empirical3SD misses count correlated time outputs, not independent coverage trials.',
        'Compact-bin span metrics do not identify frequency; full-resolution replays cover selected intervals only.',
        'Reference-temperature parameter comparisons use truth for scoring only; inference and replay are unchanged.'])
    target=Path(__file__).parent/'receipt.json';target.write_text(json.dumps(receipt,indent=2,allow_nan=False)+'\n');print(target)
if __name__=='__main__':main()
