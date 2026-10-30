"""Read-only full-output scan; no fitting or original-file modification."""
import argparse,hashlib,json,subprocess
from pathlib import Path
import numpy as np

def identity(path):
    with path.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
    return dict(bytes=path.stat().st_size,sha256=sha)

def empty():
    return dict(n=0,Q_sum=0.,SOC_sum=0.,Q_squares=0.,SOC_squares=0.,max_abs_Q_percent=0.,max_abs_SOC_pp=0.,joint_inside=0,Q_3sd_misses=0,SOC_3sd_misses=0,voltage_squares=0.,h_squares=0.)

def add(a,q,z,qmiss,zmiss,v,h):
    if not len(q):return
    a['n']+=len(q);a['Q_sum']+=float(q.sum());a['SOC_sum']+=float(z.sum());a['Q_squares']+=float(q@q);a['SOC_squares']+=float(z@z)
    a['max_abs_Q_percent']=max(a['max_abs_Q_percent'],float(abs(q).max()));a['max_abs_SOC_pp']=max(a['max_abs_SOC_pp'],float(abs(z).max()))
    a['joint_inside']+=int(((abs(q)<=.5)&(abs(z)<=.5)).sum());a['Q_3sd_misses']+=int(qmiss.sum());a['SOC_3sd_misses']+=int(zmiss.sum());a['voltage_squares']+=float(v@v);a['h_squares']+=float(h@h)

def finish(a):
    n=a['n']
    if not n:return a
    return dict(outputs=n,mean_Q_percent=a['Q_sum']/n,mean_SOC_pp=a['SOC_sum']/n,Q_RMSE_percent=(a['Q_squares']/n)**.5,SOC_RMSE_pp=(a['SOC_squares']/n)**.5,max_abs_Q_percent=a['max_abs_Q_percent'],max_abs_SOC_pp=a['max_abs_SOC_pp'],joint_within_target_fraction=a['joint_inside']/n,Q_3sd_miss_fraction=a['Q_3sd_misses']/n,SOC_3sd_miss_fraction=a['SOC_3sd_misses']/n,assimilated_voltage_RMS_mV=1000*(a['voltage_squares']/n)**.5,h_RMS=(a['h_squares']/n)**.5)

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--original',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    summary=json.loads((a.run/'summary.json').read_text());manifest=json.loads((a.run/'manifest.json').read_text())['artifacts'];checked={}
    for name,expected in manifest.items():
        if expected['bytes']<=300000 and (Path(name).suffix in ['.json','.py','.c','.h','.so']):
            actual=identity(a.run/name);assert actual==expected,name;checked[name]=actual
    config=json.loads((a.run/'calibration.json').read_text());reservation=json.loads((a.run/'reservation.json').read_text())
    report=dict(run=str(a.run),original=str(a.original),source_revision=reservation['source_revision'],review_revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),status=summary['status'],checked_small_artifacts=checked,scope='Every saved estimate boundary scanned in both encodings. Large input/trace arrays mmap-read, not fully rehashed; input equality compares recorded identities. Truth used only for scoring. Original files unchanged.',cases=[])
    params=['Q_Ah','R0_ohm','R1_ohm','tau1_s','R2_ohm','tau2_s','R3_ohm','tau3_s','H_V','gamma_plus','gamma_minus']
    bins_all={}
    for case in summary['cases']:
        folder=a.run/case['directory'];old=a.original/case['directory'];ins=json.loads((folder/'inputs.json').read_text());orig=json.loads((old/'inputs.json').read_text());scenario=json.loads((folder/'scenario.json').read_text());truth=np.load(folder/'truth.npy',mmap_mode='r')
        entry=dict(seed=case['scenario']['seed'],case=case['directory'],status=case['status'],input_recorded_hashes_match_original={k:ins[k]==orig[k] for k in ['observation_identity','truth_identity']},encoding_difference=case['encoding_difference'],arms={})
        streams={k:np.load(folder/(k+'_trace.npy'),mmap_mode='r')[:v['outputs']] for k,v in case['arms'].items()}
        size=len(streams['float64']);assert all(len(s)==size for s in streams.values())
        groups={k:{w:empty() for w in ['all','after24h','after72h','last48h']} for k in streams};last={k:{w:None for w in ['Q','SOC','joint']} for k in streams};bins={k:[empty() for _ in range(196)] for k in streams};maxh={k:0. for k in streams}
        for start in range(0,size,65536):
            end=min(start+65536,size);counts=streams['float64'][start:end,0].astype(np.int64);np.testing.assert_array_equal(counts,16*np.arange(start+1,end+1));t=streams['float64'][start:end,1]/3600;tr=np.asarray(truth[counts-1]);hours=np.minimum(np.floor(t).astype(int),195)
            for enc,stream in streams.items():
                rows=np.asarray(stream[start:end]);assert np.isfinite(rows).all();np.testing.assert_array_equal(rows[:,0],counts);np.testing.assert_allclose(rows[:,1],counts/50,rtol=0,atol=1e-9)
                assert np.all(abs(rows[:,10])<=1);maxh[enc]=max(maxh[enc],float(abs(rows[:,10]).max()))
                q=100*(rows[:,11]/tr[:,5]-1);z=100*(rows[:,6]-tr[:,0]);qm=abs(np.log(rows[:,11]/tr[:,5]))>3*rows[:,36];zm=abs(z)>300*rows[:,37];v=rows[:,5]-tr[:,16];h=rows[:,10]-tr[:,4]
                for name,mask in [('Q',abs(q)>.5),('SOC',abs(z)>.5),('joint',(abs(q)>.5)|(abs(z)>.5))]:
                    if mask.any():last[enc][name]=float(t[np.flatnonzero(mask)[-1]])
                for name,mask in [('all',np.ones(len(t),dtype=bool)),('after24h',t>24),('after72h',t>72),('last48h',t>148)]:add(groups[enc][name],q[mask],z[mask],qm[mask],zm[mask],v[mask],h[mask])
                for hour in np.unique(hours):
                    mask=hours==hour;add(bins[enc][hour],q[mask],z[mask],qm[mask],zm[mask],v[mask],h[mask])
        for enc,stream in streams.items():
            row=stream[-1];metrics={k:finish(v) for k,v in groups[enc].items()};origall=case['arms'][enc]['all'];assert metrics['all']['outputs']==origall['outputs'];assert abs(metrics['all']['Q_RMSE_percent']-origall['Q_RMSE_percent'])<1e-10;assert abs(metrics['all']['SOC_RMSE_pp']-origall['SOC_RMSE_pp'])<1e-10
            msg=np.load(folder/(enc+'_message.npy'));np.testing.assert_allclose(row[6:10],msg[:4],rtol=0,atol=1e-15);assert abs(row[10]-np.tanh(msg[4]))<1e-15
            entry['arms'][enc]=dict(status=case['arms'][enc]['status'],retired_records=case['arms'][enc]['retired_records'],pending_records=case['arms'][enc]['pending_records'],last_outside_hours=last[enc],metrics=metrics,final_Q_percent=origall['final_Q_percent'],final_SOC_pp=origall['final_SOC_pp'],final_Q_three_sd_upper_width_percent=100*float(np.expm1(3*row[36])),final_SOC_three_sd_width_pp=300*row[37],final_reference_parameters={p:float(row[22+i]) for i,p in enumerate(params)},final_reference_parameter_error_percent={p:100*(float(row[22+i])/scenario['cell_definition']['parameters'][p]-1) for i,p in enumerate(params)},max_abs_h=maxh[enc],final_message=identity(folder/(enc+'_message.npy')))
        bins_all[str(entry['seed'])]={k:[finish(v) for v in rows] for k,rows in bins.items()};report['cases'].append(entry)
        (a.out/'review.json').write_text(json.dumps(report,indent=2)+'\n');(a.out/'hourly.json').write_text(json.dumps(bins_all)+'\n')
        print(json.dumps(dict(seed=entry['seed'],last_outside=last,late={k:entry['arms'][k]['metrics']['last48h'] for k in streams})),flush=True)
    print('Review complete',flush=True)
if __name__=='__main__':main()
