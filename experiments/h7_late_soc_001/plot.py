"""Plot original per-output diagnostic errors, without averaging the miss test."""
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from .diagnostic import OUT
p=OUT/'diagnostic.png'
if p.exists():raise FileExistsError(p)
fig,axes=plt.subplots(2,3,figsize=(14,6),layout='constrained')
for row,name in zip(axes,('case_0007','case_0006')):
    with np.load(OUT/name/'traces.npz') as z:
        a=z['tangent_h7'];t=a[:,1];miss=abs(a[:,6])>3
        row[0].plot(t,a[:,2]*1000,color='#0072B2');row[0].set_ylabel('Current (mA)')
        row[1].plot(t,a[:,4],color='#D55E00',lw=.8,label='SOC error')
        row[1].plot(t,3*a[:,5],color='#555555',ls='--',lw=.7,label='±3 local SD')
        row[1].plot(t,-3*a[:,5],color='#555555',ls='--',lw=.7)
        row[1].set_ylabel('SOC error (percentage points)')
        row[2].plot(t,a[:,6],color='#D55E00',lw=.8);row[2].scatter(t[miss],a[miss,6],color='#222222',s=2,label='3SD misses')
        row[2].axhline(3,color='#555555',ls='--',lw=.7);row[2].axhline(-3,color='#555555',ls='--',lw=.7)
        row[2].set_ylabel('SOC error / local SD')
        for ax in row:ax.set_xlabel('Simulated hours');ax.set_title(name+' · H7');ax.grid(alpha=.2)
axes[0,1].legend(fontsize=8);axes[0,2].legend(fontsize=8)
fig.suptitle('Selected first-crossing windows: exact checkpoint replay, correlated diagnostic outputs',fontsize=12)
fig.savefig(p,dpi=160)
print(p)
