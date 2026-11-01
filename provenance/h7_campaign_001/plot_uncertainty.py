"""Compact descriptive uncertainty plots; no samples reconstructed or refitted."""
import argparse
import json
from pathlib import Path
import numpy as np
from experiments.foster_campaign_001.telemetry import TRACE_COLUMNS


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();summary=json.loads((a.run/'summary.json').read_text());a.out.mkdir(parents=True,exist_ok=False)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from experiments.foster_campaign_001.plot import ARM_COLORS
    for quantity in ('Q','SOC'):
        fig,axes=plt.subplots(2,4,figsize=(16,7),layout='constrained',squeeze=False)
        for ax,case in zip(axes.flat,summary['cases']):
            directory=a.run/case['directory'];sc=case['scenario'];cell=json.loads((directory/'scenario.json').read_text())['cell_definition']
            with np.load(directory/'plot_summary.npz') as z:
                for arm,info in case['arms'].items():
                    avg=z[arm+'_mean'];t=(z[arm+'_first']+z[arm+'_last'])/(2*case['sample_rate_Hz']*3600)
                    if quantity=='Q':
                        err=avg[:,len(TRACE_COLUMNS)+5]-np.log(cell['parameters']['Q_Ah']);sd=avg[:,TRACE_COLUMNS.index('Q_log_sd')]
                    else:
                        err=avg[:,-3]/100;sd=avg[:,TRACE_COLUMNS.index('SOC_sd')]
                    selected=(t>=3)&(sd>0);ratio=err[selected]/sd[selected]
                    ax.plot(t[selected],ratio,color=ARM_COLORS[arm],lw=.9,label=arm)
                    misses=info['all'][quantity+'_3sd_misses']
                    miss=misses/max(info['all']['outputs'],1)
                    index=0 if arm=='tangent64' else 1
                    ax.text(.02,.98-.08*index,f'{arm}: {misses:,} misses ({100*miss:.3f}%)',color=ARM_COLORS[arm],transform=ax.transAxes,va='top',fontsize=7)
            for level in (-3,3):ax.axhline(level,color='#555555',ls=':',lw=.8)
            ax.axhline(0,color='#888888',lw=.5);ax.set_yscale('symlog',linthresh=3)
            ax.set_title(f"{case['directory']} · {sc['cell']} · {sc['load']}\nnoise seed {sc['seed']}"+(f" · load {sc['load_seed']}" if 'load_seed' in sc else ''),fontsize=9)
            ax.set_xlabel('Simulated hours');ax.set_ylabel('Bin-mean error / bin-mean local SD');ax.grid(alpha=.2)
        fig.suptitle(f'{quantity}: H5 versus H7 streamed uncertainty\nCurves show ratios of bin means after 3 h; miss counts cover the whole run. Correlated traces, not a coverage validation.',fontsize=12)
        fig.savefig(a.out/(quantity+'_uncertainty.png'),dpi=160);plt.close(fig)

if __name__=='__main__':main()
