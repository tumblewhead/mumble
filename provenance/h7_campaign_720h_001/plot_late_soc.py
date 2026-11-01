"""Show compact recorded SOC extrema and descriptive local-width curves."""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from experiments.foster_campaign_001.telemetry import TRACE_COLUMNS

run=Path('experiments/foster_campaign_001/run_20261101_071802_121297')
out=Path('experiments/h7_campaign_001/review720_001/late_SOC.png')
if out.exists(): raise FileExistsError(out)
fig,axes=plt.subplots(2,1,figsize=(12,6),layout='constrained')
for ax,name,seed in zip(axes,['case_0006','case_0007'],[1100,1103]):
    with np.load(run/name/'plot_summary.npz') as z:
        arm='tangent_h7';t=(z[arm+'_first']+z[arm+'_last'])/(2*50*3600)
        mask=(t>=648)&(z[arm+'_count']>0);t=t[mask]
        mean=z[arm+'_mean'][mask];low=z[arm+'_low'][mask];high=z[arm+'_high'][mask]
        ax.fill_between(t,low[:,-3],high[:,-3],color='#D55E00',alpha=.2,label='Actual SOC error range in each bin')
        ax.plot(t,mean[:,-3],color='#D55E00',lw=1,label='Bin-mean SOC error')
        sd=100*mean[:,TRACE_COLUMNS.index('SOC_sd')]
        ax.plot(t,3*sd,color='#222222',ls='--',lw=.9,label='±3 × bin-mean local SD')
        ax.plot(t,-3*sd,color='#222222',ls='--',lw=.9)
        ax.axhline(0,color='#999999',lw=.5)
        ax.set_title(f'{name}: cell B, charge-discharge, noise seed {seed}, H7')
        ax.set_ylabel('SOC error (percentage points)');ax.set_xlabel('Simulated hours');ax.grid(alpha=.2)
axes[0].legend(fontsize=8,loc='upper left',ncol=3)
fig.suptitle('Last 72 hours: small physical errors, increasingly demanding local uncertainty\n0.36-hour bins; error extrema and SD curves are not sample-aligned coverage bounds.',fontsize=11)
fig.savefig(out,dpi=160)
print(out)
