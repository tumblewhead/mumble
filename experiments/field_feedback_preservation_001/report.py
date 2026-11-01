"""Separate postfit scoring and plots; no fit selection or fitting."""
import argparse
import json
from pathlib import Path
import numpy as np
from experiments.uncertainty_weak_stimulus_001.diagnostics import write,identity


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    base=Path(__file__).resolve().parent;args.out.mkdir(parents=True,exist_ok=False)
    boundary=json.loads((base/'gaussian002/result.json').read_text())
    cases=[]
    for label in ['owner_case_0000','owner_case_0002','owner_case_0004','owner_case_0006','weak_B_cycle']:
        path=base/'short002'/label/'result.json';r=json.loads(path.read_text())
        truthpath=base.parent/'uncertainty_weak_stimulus_001/attempt001'/label/'truth_for_postfit_only.json'
        truth=json.loads(truthpath.read_text());q=truth['reference_parameters']['Q_Ah'];soc=truth['endpoint'][0]
        endpoints=r['endpoints'][str(r['end_record'])]
        scores={a:dict(Q_error_percent=100*(e['Q_Ah']/q-1),SOC_error_pp=100*(e['SOC']-soc),Q_local_SD_percent=100*e['Q_log_sd']) for a,e in endpoints.items()}
        cases.append(dict(label=label,scores=scores,fit_identity=identity(path),truth_identity=identity(truthpath),
            max_Q_difference_percent=r['max_abs_Q_difference_percent'],max_SOC_difference_pp=r['max_abs_SOC_difference_pp'],
            Q_width_ratio_range=r['Q_width_ratio_range'],timing=r['timing']))
    path=base/'extended001/weak_B_cycle/result.json';extended=json.loads(path.read_text())
    write(args.out/'scores.json',dict(cases=cases,extended_fit=identity(path),source=identity(Path(__file__)),
          scope='Truth scored only after inference. Local widths, not calibrated coverage.'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    h=extended['history'];hours=np.array([r['sequence'] for r in h])/35/3600
    fig,axes=plt.subplots(3,1,figsize=(12,10),sharex=True,layout='constrained')
    for name,color in [('rolling','#777777'),('oracle','#0674a6'),('tangent','#c45b00')]:
        axes[0].plot(hours,[100*r[name+'_Q_log_sd'] for r in h],label=name,color=color,lw=1)
        axes[1].plot(hours,[100*(r[name+'_Q']/r['oracle_Q']-1) for r in h],label=name,color=color,lw=1)
        axes[2].plot(hours,[100*(r[name+'_SOC']-r['oracle_SOC']) for r in h],label=name,color=color,lw=1)
    axes[0].set(ylabel='100 × log-Q SD (%)',title='Weak use: identical data and scheduled field refreshes')
    axes[1].set(ylabel='Q difference from oracle (%)')
    axes[2].set(ylabel='SOC difference from oracle (pp)',xlabel='Simulated hour')
    for ax in axes:ax.grid(alpha=.2)
    axes[0].legend();fig.savefig(args.out/'weak_feedback.png',dpi=160);plt.close(fig)


if __name__=='__main__':main()
