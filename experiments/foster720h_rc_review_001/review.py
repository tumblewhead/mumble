"""Read-only sampled trace/physical-response diagnostic; no fitting or truth feedback."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ.setdefault('MPLCONFIGDIR','/tmp/foster720h-review-mpl')
import argparse,json,hashlib
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from experiments.foster_campaign_001.telemetry import PARAMETERS,thermal
from experiments.foster_feedback_001.estimator import Model
ROOT=Path(__file__).resolve().parents[2]

def identity(p):return dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def statistics(x):return dict(min=float(np.min(x)),max=float(np.max(x)),mean=float(np.mean(x)),RMS=float(np.sqrt(np.mean(np.asarray(x)**2))))
def spectral_peak(t,x):
    dt=float(t[1]-t[0]);x=x-np.polyval(np.polyfit(t-t[0],x,1),t-t[0]);power=abs(np.fft.rfft(x))**2;freq=np.fft.rfftfreq(len(x),dt);power[0]=0.;i=np.argmax(power)
    return dict(period_hours=float(1/freq[i]/3600),fraction_of_detrended_power=float(power[i]/power.sum()))
def ref_sd(message):
    m=message[:16];L=message[16:272].reshape(16,16);p=np.exp(m[5:]);G=np.zeros((11,16))
    for i in range(11):G[i,5+i]=p[i]
    for i,parts in [(5,[3,5]),(7,[3,5,7])]:
        G[i]=0
        for j in parts:G[i,5+j]=p[j]
    p[5]+=p[3];p[7]+=p[5]
    sd=np.linalg.norm(G@L,axis=1);return p,sd

def main():
    a=argparse.ArgumentParser();a.add_argument('--run',type=Path,required=True);a.add_argument('--out',type=Path,required=True);args=a.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    run=args.run;cfg=json.loads((run/'calibration.json').read_text());plan=json.loads((run/'campaign_plan.json').read_text());build=json.loads((run/'backend_c/build.json').read_text());summary=json.loads((run/'summary.json').read_text());reservation=json.loads((run/'reservation.json').read_text())
    files=[run/'calibration.json',run/'campaign_plan.json',run/'summary.json',run/'backend_c/build.json',run/'backend_c/estimator.so']
    assert identity(run/'backend_c/estimator.so')==build['binary']
    verified={}
    for name,expected in build['sources'].items():
        p=run/'backend_c/source_snapshot'/name;assert identity(p)==expected,name;verified[name]=expected
    report=dict(run=str(run),run_source_revision=reservation['source_revision'],chart=cfg.get('hysteresis_chart','legacy'),configuration=plan['configuration'],run_status=summary['status'],verified_saved_C_sources=verified,scope='Original artifacts read only. Final values for all8cases; regular10.24s sample of final48h for completed cases, not exhaustive extrema. Case3 final24h error decomposition. No raw-array full rehash. No estimator refit.',cases=[])
    snapshots={};arrays={}
    for folder in sorted(run.glob('case_*')):
        if not (folder/'result.json').exists():continue
        result=json.loads((folder/'result.json').read_text());scenario=json.loads((folder/'scenario.json').read_text());files +=[folder/'result.json',folder/'scenario.json',folder/'inputs.json',folder/'float64_message.npy',folder/'float32_message.npy']
        count=result['arms']['float64']['outputs'];trace=np.load(folder/'float64_trace.npy',mmap_mode='r');trace32=np.load(folder/'float32_trace.npy',mmap_mode='r');truth=np.load(folder/'truth.npy',mmap_mode='r');x=np.array(trace[count-1]);m=np.load(folder/'float64_message.npy');p,sd=ref_sd(m);true=np.array([scenario['cell_definition']['parameters'][k] for k in PARAMETERS]);np.testing.assert_allclose(x[22:33],p,rtol=1e-13,atol=1e-13)
        entry=dict(case=folder.name,seed=scenario['seed'],status=result['status'],hours=x[1]/3600,arms={k:dict(status=v['status'],retired_records=v['retired_records'],failure=v.get('failure')) for k,v in result['arms'].items()},final_Q_percent=result['arms']['float64']['all']['final_Q_percent'],final_SOC_pp=result['arms']['float64']['all']['final_SOC_pp'],final_parameters=dict(zip(PARAMETERS,p.tolist())),reference_truth=dict(zip(PARAMETERS,true.tolist())),parameter_error_percent=dict(zip(PARAMETERS,(100*(p/true-1)).tolist())),parameter_local_sd=dict(zip(PARAMETERS,sd.tolist())),total_R_ohm=float(p[[1,2,4,6]].sum()),total_R_error_percent=float(100*(p[[1,2,4,6]].sum()/true[[1,2,4,6]].sum()-1)),RC_first_moment_ohm_s=float(p[[2,4,6]]@p[[3,5,7]]),encoding_final_parameter_difference_percent=dict(zip(PARAMETERS,(100*(trace32[count-1,22:33]/p-1)).tolist())))
        if result['status']=='completed':
            start=max(0,count-round(48*3600*50/16));ix=np.arange(start,count,32);rows=np.asarray(trace[ix]);indices=rows[:,0].astype(int)-1;tr=np.asarray(truth[indices]);qerr=100*(rows[:,11]/tr[:,5]-1);zerr=100*(rows[:,6]-tr[:,0]);v=1000*(rows[:,5]-tr[:,16])
            entry['last48h_sampled']=dict(outputs=len(ix),sampling_seconds=10.24,Q_error_percent=statistics(qerr),SOC_error_pp=statistics(zerr),assimilated_voltage_error_mV=statistics(v),reference_parameter_range_percent=dict(zip(PARAMETERS,(100*np.ptp(rows[:,22:33],axis=0)/true).tolist())),Q_3sd_miss_fraction=float(np.mean(abs(np.log(rows[:,11]/tr[:,5]))>3*rows[:,36])),SOC_3sd_miss_fraction=float(np.mean(abs(zerr)>300*rows[:,37])))
            if folder.name=='case_0003':
                selection=rows[:,1]>=696*3600;rows=rows[selection];tr=tr[selection];zerr=zerr[selection]
                dtc=thermal(cfg,rows[:,3]);np.testing.assert_allclose(rows[:,11:22],rows[:,22:33]*dtc,rtol=1e-13,atol=1e-13)
                contributions=np.column_stack((1000*cfg['ocv_slope_V_per_SOC']*(rows[:,6]-tr[:,0]),1000*(rows[:,19]*rows[:,10]-tr[:,13]*tr[:,4]),-1000*rows[:,2]*(rows[:,12]-tr[:,6]),-1000*(rows[:,7:10]-tr[:,1:4]).sum(axis=1)))
                np.testing.assert_allclose(contributions.sum(axis=1),1000*(rows[:,5]-tr[:,16]),atol=2e-12,rtol=1e-10)
                entry['oscillation']=dict(temperature=spectral_peak(rows[:,1],rows[:,3]),SOC_error=spectral_peak(rows[:,1],zerr),reference_tau1=spectral_peak(rows[:,1],rows[:,25]),SOC_error_true_SOC_correlation=float(np.corrcoef(zerr,tr[:,0])[0,1]),SOC_error_h_correlation=float(np.corrcoef(zerr,tr[:,4])[0,1]),effective_reference_temperature_ratio_max_abs_difference=float(abs(rows[:,11:22]/rows[:,22:33]-dtc).max()))
                entry['voltage_error_decomposition_mV']={name:statistics(contributions[:,j]) for j,name in enumerate(['OCV_from_SOC','hysteresis','ohmic_R0','sum_RC'])};entry['voltage_error_decomposition_mV']['total']=statistics(contributions.sum(axis=1));entry['ohmic_RC_error_correlation']=float(np.corrcoef(contributions[:,2],contributions[:,3])[0,1])
                arrays['rows']=rows;arrays['truth']=tr;arrays['contributions']=contributions
                entry['history_snapshots']=[]
                for hour in [1,4,24,100,360,672,720]:
                    row=trace[min(round(hour*3600*50/16)-1,count-1)];entry['history_snapshots'].append(dict(hour=hour,reference_parameters=dict(zip(PARAMETERS,row[22:33].tolist()))))
        snapshots[folder.name]=(p,true);report['cases'].append(entry)
    completed=[c for c in report['cases'] if c['status']=='completed'];report['completed_bias_counts']={k:dict(high=sum(c['parameter_error_percent'][k]>0 for c in completed),low=sum(c['parameter_error_percent'][k]<0 for c in completed)) for k in PARAMETERS}
    # Transfer-function diagnostic at25C, using final estimated parameters only.
    t=np.geomspace(.0001,60,2000);freq=np.geomspace(.001,25,1000);discrete={};responses={};true=snapshots['case_0003'][1]
    def response(p,t):return p[1]+np.sum(p[[2,4,6]][None,:]*(-np.expm1(-t[:,None]/p[[3,5,7]][None,:])),axis=1)
    def transfer(p,f):
        decay=np.exp(-.02/p[[3,5,7]]);return p[1]+np.sum(p[[2,4,6]][None,:]*(1-decay)[None,:]/(1-decay[None,:]*np.exp(-2j*np.pi*f[:,None]*.02)),axis=1)
    Htrue=transfer(true,freq)
    for name,(p,_) in snapshots.items():
        if next(c for c in report['cases'] if c['case']==name)['status']!='completed':continue
        H=transfer(p,freq);responses[name]=response(p,t)
        discrete[name]=dict(step_0p12A_error_mV_at_times=dict(zip(map(str,[.02,.05,.1,.5,1,5,20]),(120*(response(p,np.array([.02,.05,.1,.5,1,5,20]))-response(true,np.array([.02,.05,.1,.5,1,5,20])))).tolist())),tau_over_sample_period=(p[[3,5,7]]/.02).tolist(),complex_impedance_error_magnitude_ohm_at_Hz={str(f):float(abs(transfer(p,np.array([f]))[0]-transfer(true,np.array([f]))[0])) for f in [.001,.01,.1,1,10,25]})
    report['RC_response_diagnostics']=discrete
    report['original_small_artifacts']={str(p.relative_to(run)):identity(p) for p in files}
    (args.out/'review.json').write_text(json.dumps(report,indent=2)+'\n')
    fig,ax=plt.subplots(3,1,figsize=(13,10),sharex=True);rows=arrays['rows'];tr=arrays['truth'];hours=rows[:,1]/3600
    ax[0].plot(hours,rows[:,3],color='red',label='Measured temperature');ax[0].set_ylabel('Temperature (C)');ax[0].legend()
    for j in [1,2,4,6]:ax[1].plot(hours,100*(rows[:,11+j]/rows[:,22+j]-1),label=PARAMETERS[j]+' thermal factor')
    ax[1].set_ylabel('Thermal change (%)');ax[1].legend(ncol=4)
    ax[2].plot(hours,100*(rows[:,6]-tr[:,0]),label='SOC error (pp)');ax[2].plot(hours,.1*tr[:,4],label='True hysteresis x0.1 (phase guide)',alpha=.6);ax[2].set_ylabel('SOC error / phase guide');ax[2].set_xlabel('Simulated hours');ax[2].legend()
    for a in ax:a.grid(alpha=.25)
    fig.suptitle('Case0003: temperature response and charge-cycle SOC error — sampled every10.24s');fig.tight_layout();fig.savefig(args.out/'oscillation.png',dpi=150);plt.close(fig)
    fig,ax=plt.subplots(1,2,figsize=(13,5));ax[0].semilogx(t,120*response(true,t),'k',lw=2,label='Plant truth')
    for name in ['case_0000','case_0002','case_0003']:
        p=snapshots[name][0];ax[0].semilogx(t,120*response(p,t),label=name);ax[1].loglog(freq,abs(transfer(p,freq)-Htrue),label=name)
    ax[0].axvline(.02,color='gray',ls=':',label='One sample');ax[0].set_xlabel('Time after0.12A step (s)');ax[0].set_ylabel('Ohmic + Foster voltage drop (mV)');ax[1].set_xlabel('Frequency (Hz)');ax[1].set_ylabel('Discrete RC transfer error (ohm)')
    for a in ax:a.legend();a.grid(alpha=.25)
    fig.suptitle('Final estimated response at25C — diagnostic only; excludes SOC and hysteresis');fig.tight_layout();fig.savefig(args.out/'RC_response.png',dpi=160);plt.close(fig)
    print(json.dumps(dict(completed=len(completed),bias=report['completed_bias_counts'],case3=next(c for c in completed if c['case']=='case_0003')),indent=2))
if __name__=='__main__':main()
