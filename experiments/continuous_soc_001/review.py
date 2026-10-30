"""Read-only campaign review, application-scale gates and saved-data plots."""
import json
from pathlib import Path
import numpy as np
from .qualify import HERE,ROOT
from experiments.structured_joint_001.qualify import ident,write


def main():
    out=HERE/'review001';out.mkdir(exist_ok=False)
    results={name:json.loads((HERE/'campaign001'/name/'result.json').read_text()) for name in ['stationary','monotone_stress']}
    report={};gates=[]
    for name,result in results.items():
        summary={}
        for kind,arm in result['arms'].items():
            if arm['records']:
                final=arm['final'];preferred=abs(final['Q_error_percent'])<=.5 and abs(final['SOC_error_pp'])<=.5
            else:final=None;preferred=False
            history_ok=arm['status']=='completed' and arm['maximum_history_Q_difference_percent']<=.5 and arm['maximum_history_SOC_difference_pp']<=.5
            summary[kind]=dict(status=arm['status'],records=arm['records'],failure=arm.get('failure'),
                 final=final,history_difference_within_preferred_scale=history_ok,final_truth_within_preferred_scale=preferred,
                 maximum_history_Q_difference_percent=arm['maximum_history_Q_difference_percent'],
                 maximum_history_SOC_difference_pp=arm['maximum_history_SOC_difference_pp'],
                 first_joint_preferred_s=arm['first_joint_preferred_s'],last_joint_outside_s=arm['last_joint_outside_s'],
                 preferred_Q_fraction=arm['preferred_Q_count']/max(1,arm['records']),preferred_SOC_fraction=arm['preferred_SOC_count']/max(1,arm['records']),
                 phases=arm['phase'],storage=arm['storage'])
        checkpoints=result['checkpoints'];phase_stats=[]
        for label,lo,hi in [('informative',0,5400),('weak',5400,10800),('renewed',10800,14401)]:
            rows=[x for x in checkpoints if lo<=x['time_s']<hi and 'float64' in x['arms'] and 'float32' in x['arms']]
            ratios=[x['arms']['float32']['SOC_sd']/x['arms']['float64']['SOC_sd'] for x in rows]
            qratios=[x['arms']['float32']['Q_sd']/x['arms']['float64']['Q_sd'] for x in rows]
            phase_stats.append(dict(phase=label,checkpoint_count=len(rows),SOC_sd_ratio_range=[min(ratios),max(ratios)] if ratios else None,
                                    Q_sd_ratio_range=[min(qratios),max(qratios)] if qratios else None))
        report[name]=dict(arms=summary,checkpoint_uncertainty=phase_stats,wall_seconds=result['wall_seconds'],cpu_seconds=result['cpu_seconds'],
                          maximum_RSS_B=result['maximum_RSS_B'])
        gates.append(dict(case=name,reference_complete=result['arms']['float64']['records']==504000,
                          float32_complete=result['arms']['float32']['records']==504000,
                          float32_history_preservation=summary['float32']['history_difference_within_preferred_scale'],
                          float32_final_point=summary['float32']['final_truth_within_preferred_scale']))
    # Saved-data figures; plotting cannot alter inference or source observations.
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,2,figsize=(11.5,7),layout='constrained',sharex=True)
    for col,(name,result) in enumerate(results.items()):
        for kind,color in [('float64','#222222'),('float32','#17806e'),('log16','#c46e25')]:
            rows=[x for x in result['checkpoints'] if kind in x['arms']]
            t=[x['time_s']/3600 for x in rows]
            q=[100*(x['arms'][kind]['Q']-x['truth_Q'])/x['truth_Q'] for x in rows]
            z=[100*(x['arms'][kind]['SOC']-x['truth_SOC']) for x in rows]
            axes[0,col].plot(t,q,label=kind,color=color,lw=1.2)
            axes[1,col].plot(t,z,label=kind,color=color,lw=1.2)
        for row in range(2):
            ax=axes[row,col];ax.axhspan(-.5,.5,color='#d9edd9',alpha=.6);ax.axvspan(1.5,3,color='#dddddd',alpha=.35)
            ax.grid(alpha=.2);ax.set_xlim(0,4)
        axes[0,col].set_title(name.replace('_',' '));axes[1,col].set_xlabel('Simulated hours')
    axes[0,0].set_ylabel('Q error (% relative)');axes[1,0].set_ylabel('SOC error (percentage points)')
    axes[0,0].legend();fig.suptitle('Four-hour35Hz controls — shaded interval: weak zero-current use',fontsize=12)
    fig.savefig(out/'long_run_errors.png',dpi=170);fig.savefig(out/'long_run_errors.pdf');plt.close(fig)
    review=dict(scope='All-sample point and history-difference metrics; uncertainty ratios at saved checkpoints; not calibrated coverage or general-cell qualification',
                gates=gates,cases=report,
                input_identities={str((HERE/'campaign001'/name/'result.json').relative_to(ROOT)):ident(HERE/'campaign001'/name/'result.json') for name in results})
    write(out/'result.json',review);print(json.dumps(dict(gates=gates,summary={name:{key:dict(status=v['status'],final_Q_percent=v['final']['Q_error_percent'] if v['final'] else None,final_SOC_pp=v['final']['SOC_error_pp'] if v['final'] else None,max_history_Q_percent=v['maximum_history_Q_difference_percent'],max_history_SOC_pp=v['maximum_history_SOC_difference_pp']) for key,v in r['arms'].items()} for name,r in report.items()})))


if __name__=='__main__':main()
