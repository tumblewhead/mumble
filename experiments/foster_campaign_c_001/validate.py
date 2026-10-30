"""Small real campaigns, backend parity and end-to-end timing; no long sweeps."""
import json,os,subprocess,sys,time
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
ENV={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MPLCONFIGDIR':'/tmp/mumble-matplotlib'}
def run(name,options):
    out=HERE/name;cmd=[sys.executable,'-B','-m','experiments.foster_campaign_001.run',*options,'--out',str(out)]
    t=time.perf_counter();r=subprocess.run(cmd,env=ENV,text=True,capture_output=True)
    report={'command':cmd,'returncode':r.returncode,'wall_s':time.perf_counter()-t,'stdout':r.stdout,'stderr':r.stderr}
    (HERE/(name+'_command.json')).write_text(json.dumps(report,indent=2)+'\n')
    if r.returncode:raise RuntimeError(r.stdout+r.stderr)
    return out,json.loads((out/'summary.json').read_text()),report

def main():
    common=['--hours','.05','--cells','A','B','--loads','cycle','charge-discharge','--noise-v','.004','--no-plots']
    python,p,pt=run('python35',['--backend','python',*common])
    native,c,ct=run('c35',['--backend','c',*common])
    comparisons=[]
    for pr,cr in zip(p['cases'],c['cases']):
        pc=python/pr['directory'];cc=native/cr['directory']
        for file in ['observations.npy','truth.npy']:
            if (pc/file).read_bytes()!=(cc/file).read_bytes():raise AssertionError('input changed '+file)
        row={'scenario':cr['scenario'],'arms':{}}
        for enc in ['float64','float32']:
            a=np.load(pc/(enc+'_trace.npy'));b=np.load(cc/(enc+'_trace.npy'))
            q=float(np.max(abs(100*(b[:,11]/a[:,11]-1))));z=float(np.max(abs(100*(b[:,6]-a[:,6]))))
            if q>=.5 or z>=.5:raise AssertionError(('application scales',q,z))
            row['arms'][enc]={'max_Q_percent':q,'max_SOC_pp':z,'max_fitted_voltage_V':float(np.max(abs(a[:,5]-b[:,5]))),'max_logZ_abs':float(np.max(abs(a[:,38]-b[:,38])))}
        comparisons.append(row)
    plotted,h,ht=run('c100_plots',['--backend','c','--sample-rate-hz','100','--hours','.15','--cells','A','--loads','charge-discharge','--encoding','both'])
    hc=h['cases'][0];case=plotted/hc['directory'];obs=np.load(case/'observations.npy',mmap_mode='r')
    assert len(obs)==54000 and np.all(obs[:,0]==.01)
    assert hc['plots']=='completed' and h['plots']['status']=='completed'
    for enc in ['float64','float32']:
        rows=np.load(case/(enc+'_trace.npy'),mmap_mode='r');assert rows[-1,1]==540
    est_py=sum(sum(v['timing']['estimator_s'].values()) for v in p['cases'])
    est_c=sum(sum(v['timing']['estimator_s'].values()) for v in c['cases'])
    case_py=sum(v['wall_s_before_plots'] for v in p['cases']);case_c=sum(v['wall_s_before_plots'] for v in c['cases'])
    report={'status':'passed','paired_cases':comparisons,'timing_single_measurement':{'python_estimator_s':est_py,'C_estimator_s':est_c,'estimator_speedup':est_py/est_c,'python_case_wall_s':case_py,'C_case_wall_s':case_c,'case_speedup':case_py/case_c,'python_entire_command_s':pt['wall_s'],'C_entire_command_s':ct['wall_s'],'scope':'One four-case run per backend at35Hz; case time includes generation/export, command time also includes build and startup qualification; plots excluded from paired runs'},'rate100':{'case':str(case),'records':len(obs),'simulated_s':540,'case_and_summary_plots':'completed','charger':hc['charger']},'limits':'Small integration controls; long-run C numerical qualification remains in frozen core receipts. No new physical coverage/aging claims.'}
    (HERE/'validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report['timing_single_measurement']),flush=True)
if __name__=='__main__':main()
