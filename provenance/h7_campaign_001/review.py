"""Review compact H5/H7 campaign evidence without loading raw trajectories."""
import argparse
import json
from pathlib import Path
import numpy as np
from experiments.foster_campaign_001.backend import identity
from experiments.foster_campaign_001.telemetry import TRACE_COLUMNS,PARAMETERS


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run=a.run.resolve();summarypath=run/'summary.json';summary=json.loads(summarypath.read_text())
    if summary['completed_cases']!=summary['requested_cases']:raise ValueError('campaign still running')
    if a.out.exists():raise FileExistsError(a.out)
    records=[];endpoints=[]
    for case in summary['cases']:
        path=run/case['directory'];result=json.loads((path/'result.json').read_text())
        if not (path/'plot_summary.npz').exists():
            records.append(dict(case=case['directory'],scenario=result.get('scenario'),status=result['status'],reason=result.get('reason'),arms={},identities={'result.json':identity(path/'result.json')}))
            continue
        cell=json.loads((path/'scenario.json').read_text())['cell_definition']
        ref=np.array([cell['parameters'][k] for k in PARAMETERS]);arms={}
        with np.load(path/'plot_summary.npz') as z:
            for name,arm in result.get('arms',{}).items():
                m=np.load(path/(name+'_message.npy'));mean=m[:16];L=m[16:272].reshape(16,16)
                pp=np.exp(mean[5:]);pp[5]+=pp[3];pp[7]+=pp[5]
                error=100*(pp/ref-1);count=z[name+'_count'];last=z[name+'_last']/result['sample_rate_Hz']/3600
                low=z[name+'_low'];high=z[name+'_high'];avg=z[name+'_mean']
                late={}
                for hour in (3,24,48):
                    mask=(last>hour)&(count>0)
                    if not mask.any():continue
                    # Intersecting bin retained whole; at most0.036h straddles the threshold.
                    qe_low=low[mask,-4];qe_high=high[mask,-4];se_low=low[mask,-3];se_high=high[mask,-3]
                    late[str(hour)]=dict(bins=int(mask.sum()),outputs=int(count[mask].sum()),
                        Q_error_range_percent=[float(qe_low.min()),float(qe_high.max())],
                        SOC_error_range_pp=[float(se_low.min()),float(se_high.max())],
                        Q_mean_error_percent=float(np.average(avg[mask,-4],weights=count[mask])),
                        Q_mean_local_SD_percent=float(100*np.average(avg[mask,TRACE_COLUMNS.index('Q_log_sd')],weights=count[mask])),
                        RC_parameter_error_range_percent={PARAMETERS[j]:[float(100*(low[mask,22+j].min()/ref[j]-1)),float(100*(high[mask,22+j].max()/ref[j]-1))] for j in range(1,8)})
                arms[name]=dict(status=arm['status'],failure=arm.get('failure'),outputs=arm['outputs'],
                    retired_records=arm['retired_records'],field_history=arm['field_history'],metrics=arm['all'],
                    final_reference_parameter_error_percent=dict(zip(PARAMETERS,error.tolist())),
                    final_Q_local_SD_percent=float(100*np.linalg.norm(L[5])),
                    final_Q_error_local_SD=float((mean[5]-np.log(ref[0]))/np.linalg.norm(L[5])),
                    final_max_abs_RC_error_percent=float(np.max(abs(error[1:8]))),late=late)
        records.append(dict(case=case['directory'],scenario=result['scenario'],status=result['status'],
            records=result['records'],arms=arms,plots=result.get('plots'),
            identities={name:identity(path/name) for name in ('result.json','inputs.json','plot_summary.npz','checkpoints/index.json')}))
    sizes={}
    for f in run.rglob('*'):
        if f.is_file():sizes[f.suffix]=sizes.get(f.suffix,0)+f.stat().st_size
    r=dict(status='reviewed',source_revision=json.loads((run/'reservation.json').read_text()).get('source_revision'),
        campaign=str(run),summary_identity=identity(summarypath),cases=records,
        total_filesystem_bytes=sum(sizes.values()),bytes_by_suffix=sizes,
        scope='Paired stationary streaming cases; local uncertainty diagnostics, correlated time samples; no lifetime or calibrated coverage claim',
        bin_boundary_policy='Include complete bins intersecting interval after3/24/48h; original extrema/means preserved')
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(r,indent=2)+'\n')
    for c in records:
        print(c['case'],c['scenario'],{k:dict(status=v['status'],Q=v['metrics'].get('final_Q_percent'),Q_SD_units=v['final_Q_error_local_SD'],RC=v['final_max_abs_RC_error_percent']) for k,v in c['arms'].items()})
    print('Review:',a.out)

if __name__=='__main__':main()
