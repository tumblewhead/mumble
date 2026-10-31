"""Read-only owner-run review: compact bins and final joint messages, no refitting."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
from experiments.foster_campaign_001.telemetry import physical,PARAMETERS


def identity(path):
    return {'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--run',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    if args.out.exists():raise ValueError('preserve previous review')
    def read(path):return json.loads(path.read_text())
    root=args.run;summary=read(root/'summary.json');cfg=read(root/'calibration.json')
    files=[root/f for f in ['summary.json','campaign_plan.json','reservation.json','calibration.json']]
    results=[]
    for entry in summary['cases']:
        case=root/entry['directory'];receipt=read(case/'result.json');meta=read(case/'telemetry.json')
        cell=read(case/'scenario.json')['cell_definition'];truth=np.array([cell['parameters'][p] for p in PARAMETERS])
        cols=meta['estimate_columns'];q=cols.index('Q_error_percent');z=cols.index('SOC_error_pp')
        rate=receipt['sample_rate_Hz'];row={'case':case.name,'scenario':receipt['scenario'],'arms':{}}
        files += [case/f for f in ['result.json','scenario.json','telemetry.json','plot_summary.npz','checkpoints/index.json']]
        with np.load(case/'plot_summary.npz') as bins:
            for arm,stats in receipt['arms'].items():
                msgfile=case/(arm+'_message.npy');files.append(msgfile);msg=np.load(msgfile)
                mean=msg[:16];L=msg[16:272].reshape(16,16);params,_=physical(mean,cfg,25)
                # Log-parameter Jacobian: cumulative tau gaps retain joint covariance.
                J=np.eye(16)[5:];gaps=np.exp(mean[[8,10,12]])
                for j,pi in enumerate([3,5,7]):
                    J[pi]=0;J[pi,[8,10,12][:j+1]]=gaps[:j+1]/params[pi]
                sd=np.linalg.norm(J@L,axis=1)
                low,high,av=[bins[arm+'_'+s] for s in ['low','high','mean']]
                times=bins[arm+'_last']/rate/3600
                assert int(bins[arm+'_count'].sum())==stats['outputs']
                outside=(low[:,q]<-.5)|(high[:,q]>.5)|(low[:,z]<-.5)|(high[:,z]>.5)
                last=np.flatnonzero(outside)
                horizon=times[-1]-72;late=times>horizon
                row['arms'][arm]={
                    'final_parameters':dict(zip(PARAMETERS,params.tolist())),
                    'signed_parameter_error_percent':dict(zip(PARAMETERS,(100*(params/truth-1)).tolist())),
                    'parameter_local_log_SD_percent':dict(zip(PARAMETERS,(100*sd).tolist())),
                    'signed_parameter_log_error_in_local_SD':dict(zip(PARAMETERS,(np.log(params/truth)/sd).tolist())),
                    'last_outside_Q_SOC_target_bin_hours':None if not len(last) else
                        [float((bins[arm+'_first'][last[-1]]-1)/rate/3600),float(times[last[-1]])],
                    'last72h_max_abs_Q_error_percent':float(max(abs(low[late,q]).max(),abs(high[late,q]).max())),
                    'last72h_max_abs_SOC_error_pp':float(max(abs(low[late,z]).max(),abs(high[late,z]).max())),
                    'recorded_all_run_metrics':stats['all'],
                    'Q_reported_3SD_miss_fraction':stats['all']['Q_3sd_misses']/stats['all']['outputs'],
                    'field_history':stats.get('field_history'),
                    'DC_resistance_ohm':float(params[[1,2,4,6]].sum()),
                    'truth_DC_resistance_ohm':float(truth[[1,2,4,6]].sum()),
                    'selected_bin_means':[{'requested_hour':h,'bin_end_hour':float(times[i]),
                         **{name:float(av[i,cols.index(name)]) for name in ['Q_error_percent','SOC_error_pp','R0_ohm_ref','R1_ohm_ref','tau1_s_ref','tau2_s_ref','tau3_s_ref']}}
                        for h in [1,4,6,9,12,24,72,196,360,648,720]
                        for i in [min(int(np.searchsorted(times,h)),len(times)-1)]]}
        results.append(row)
    report={'status':'read_only_review_complete','run':str(root.resolve()),
            'run_source_revision':read(root/'reservation.json')['source_revision'],
            'fit_or_replay_executed':False,'estimator_changed':False,'original_results_modified':False,
            'cases':results,'source_identities':{str(f):identity(f) for f in files},
            'limits':['Bins cover 0.36 hours; last out-of-band times are bin intervals, not exact events.',
                      'Final point errors and local GN widths are not validated posterior coverage.',
                      'Compensating parameters and noise-dependent paths are evidence of history/identification difficulty, not proof of a unique causal mechanism.',
                      'No exact retained-data reference was fitted at 720h; low-noise field bias attribution remains a hypothesis.']}
    args.out.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(args.out)


if __name__=='__main__':main()
