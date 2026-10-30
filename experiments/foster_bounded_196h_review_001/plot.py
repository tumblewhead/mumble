"""Plot exact hourly maxima/miss fractions from the read-only review."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
HERE=Path(__file__).resolve().parent

def main():
    data=json.loads((HERE/'attempt001/hourly.json').read_text());t=np.arange(196)+.5
    fig,axs=plt.subplots(2,2,figsize=(12,8),layout='constrained')
    for i,(seed,arms) in enumerate(data.items()):
        rows=arms['float64'];color=plt.get_cmap('tab10')(i);kw=dict(color=color,lw=2 if seed=='1006' else 1,alpha=.95,label=seed)
        for ax,key in [(axs[0,0],'max_abs_Q_percent'),(axs[0,1],'max_abs_SOC_pp'),(axs[1,0],'Q_3sd_miss_fraction'),(axs[1,1],'assimilated_voltage_RMS_mV')]:
            ax.plot(t,[r[key] for r in rows],**kw)
    for ax in axs.flat:ax.set_xscale('log');ax.set_xlim(.5,196);ax.set_xticks([.5,1,4,24,72,196],labels=['0.5','1','4','24','72','196']);ax.grid(alpha=.25);ax.set_xlabel('Simulated hours (hourly bins)')
    for ax in axs[0]:ax.set_yscale('log');ax.axhline(.5,color='#555555',ls='--',lw=1,label='application target')
    axs[0,0].set_ylabel('Maximum |Q error| per hour (%)');axs[0,1].set_ylabel('Hourly max |SOC error| (percentage points)')
    axs[1,0].set_ylabel('Fraction outside reported Q ±3 SD');axs[1,0].set_ylim(-.03,1.03)
    axs[1,1].set_yscale('log');axs[1,1].set_ylabel('Assimilated voltage RMS error (mV)')
    handles,labels=axs[0,0].get_legend_handles_labels();fig.legend(handles[:8],labels[:8],loc='outside lower center',ncol=8,title='Noise seed; binary64 shown (binary32 also scanned)')
    fig.suptitle('196-hour bounded-hysteresis review: stable estimates, remaining overconfidence\nAll eight seeds complete; hourly maxima use every saved estimate boundary')
    fig.savefig(HERE/'system_review.png',dpi=160);plt.close(fig)
if __name__=='__main__':main()
