"""Plot saved evidence only; no fitting, dictionary changes or model execution."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent


def main():
    output=HERE/'figures001';output.mkdir(exist_ok=False)
    tail=json.loads((HERE/'tails001/result.json').read_text())['evidence']['uncertainty']
    log16=json.loads((HERE/'log16_001/result.json').read_text())['evidence']['runs']
    fig,axes=plt.subplots(1,2,figsize=(11.5,4.3),layout='constrained')
    colors={'sphere8':'#d78226','sphere12':'#147d92','shapes':'#a74758','log12':'#8162aa','log16':'#24783e'}
    labels={'sphere8':'Linear amplitude, 8 bit','sphere12':'Linear amplitude, 12 bit','shapes':'Five shape templates','log12':'Log amplitude, 12 bit','log16':'Log amplitude, 16 bit'}
    for ax,fixture,metric in [(axes[0],'reversal','TV'),(axes[1],'weak','std')]:
        run=next(x for x in tail if x['fixture']==fixture and x['aging_scale']==20.)
        extended=next(x for x in log16 if x['fixture']==fixture and x['aging_scale']==20.)
        for key in colors:
            values=[(s['TV'] if metric=='TV' else s['std']['soc']['ratio']) for s in extended['steps']] if key=='log16' else [(s['codecs'][key]['TV'] if metric=='TV' else s['codecs'][key]['std']['soc']['ratio']) for s in run['steps']]
            ax.plot(range(1,9),values,marker='o',ms=3,label=labels[key],color=colors[key])
        ax.set_yscale('log');ax.set_xlabel('Held-current event');ax.grid(True,which='both',alpha=.18)
    axes[0].set_title('Joint distribution distortion: temperature reversals')
    axes[0].set_ylabel('Total variation from uncompressed grid reference')
    axes[1].set_title('SOC uncertainty distortion: weak excitation')
    axes[1].set_ylabel('Encoded / reference SOC standard deviation')
    axes[1].axhline(1,color='black',lw=.8,ls='--')
    axes[0].legend(fontsize=8,loc='lower right')
    fig.suptitle('Codebook preservation checks — finite-state comparator, accelerated aging stress',fontsize=11)
    fig.savefig(output/'joint_mass_geometry.png',dpi=170)
    fig.savefig(output/'joint_mass_geometry.pdf')
    plt.close(fig)
    print(str(output))


if __name__=='__main__':main()
