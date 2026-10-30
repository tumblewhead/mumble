"""Offline plots and zoomed rerenders from saved telemetry; no estimator rerun."""
import argparse
import json
from pathlib import Path
import numpy as np
from .telemetry import PARAMETERS, TRACE_COLUMNS, STATES


def draw(ax, y, time_at, label, color, points=4000):
    """Bin large traces with min/max envelopes so narrow current pulses survive."""
    n = len(y)
    if not n:
        return
    if n <= points:
        ax.plot(time_at(np.arange(n))/3600, y, label=label, color=color, lw=.9)
        return
    starts = np.linspace(0, n, points+1, dtype=int)[:-1]
    counts = np.diff(np.r_[starts, n])
    lo = np.minimum.reduceat(y, starts)
    hi = np.maximum.reduceat(y, starts)
    mean = np.add.reduceat(y, starts)/counts
    t = time_at(starts+counts//2)/3600
    ax.fill_between(t, lo, hi, color=color, alpha=.2)
    ax.plot(t, mean, color=color, label=label+' (bin mean/range)', lw=.8)


def derived(ax, n, values, time_at, label, color, points=4000):
    """Compute ratios/errors in bounded chunks, retaining plot-bin extrema."""
    if not n:
        return
    edges = np.linspace(0,n,min(n,points)+1,dtype=int)
    low=[]; high=[]; means=[]
    for start,end in zip(edges[:-1],edges[1:]):
        lo=float('inf'); hi=-lo; total=0.
        for a in range(start,end,8192):
            v=values(slice(a,min(end,a+8192)))
            lo=min(lo,float(np.min(v)));hi=max(hi,float(np.max(v)));total+=float(np.sum(v))
        low.append(lo);high.append(hi);means.append(total/(end-start))
    t=time_at((edges[:-1]+edges[1:]-1)//2)/3600
    ax.fill_between(t,low,high,color=color,alpha=.2)
    ax.plot(t,means,label=label+(' (bin mean/range)' if n>points else ''),color=color,lw=.9)


def render(case, result, config, cell, destination=None, start_hour=0., end_hour=None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    destination = destination or case
    destination.mkdir(parents=True, exist_ok=True)
    obs = np.load(case/'observations.npy', mmap_mode='r')
    truth = np.load(case/'truth.npy', mmap_mode='r')
    begin = max(0, int(start_hour*126000))
    end = min(len(obs), int(end_hour*126000) if end_hour is not None else len(obs))
    if end <= begin:
        raise ValueError('plot time range contains no samples')
    o = obs[begin:end]; tr = truth[begin:end]
    sample_time = lambda ix: (begin+ix+1)/35
    traces = {}
    for k, stat in result['arms'].items():
        rows = np.load(case/(k+'_trace.npy'), mmap_mode='r')[:stat['outputs']]
        first = np.searchsorted(rows[:,1], begin/35, side='right')
        last = np.searchsorted(rows[:,1], end/35, side='right')
        traces[k] = rows[first:last]
    colors = dict(float64='#3165b4', float32='#dc7822')
    title = ', '.join(str(result['scenario'][k]) for k in ['cell','load','noise_v','seed'])

    def save(fig, axes, name, heading):
        for ax in np.asarray(axes).ravel():
            if ax.get_visible():
                ax.grid(alpha=.2)
                ax.set_xlabel('Simulated hours')
                handles, _ = ax.get_legend_handles_labels()
                if handles:
                    ax.legend(fontsize=7)
        fig.suptitle(heading+'\n'+title, fontsize=12)
        for suffix in ['png','pdf']:
            path = destination/(name+'.'+suffix)
            if path.exists():
                raise FileExistsError('plot exists; use a fresh --out directory: '+str(path))
            fig.savefig(path, dpi=150)
        plt.close(fig)

    fig, ax = plt.subplots(3,1,figsize=(12,9),layout='constrained')
    draw(ax[0], o[:,3], sample_time, 'Measured V', '#999999')
    draw(ax[0], tr[:,16], sample_time, 'Noiseless plant V', '#151515')
    for k, rows in traces.items():
        draw(ax[0], rows[:,5], lambda ix,r=rows:r[ix,1], k+' assimilated endpoint V', colors[k])
    draw(ax[1], o[:,1], sample_time, 'Current (+ discharge)', '#3165b4')
    draw(ax[2], o[:,2], sample_time, 'Exogenous temperature', '#dc7822')
    for a, unit in zip(ax,['V','A','°C']):
        a.set_ylabel(unit)
    save(fig, ax, 'signals', 'V / I / T — estimated V is an assimilated fit, not a forecast')

    fig, axes = plt.subplots(5,1,figsize=(12,13),layout='constrained')
    for j,a in enumerate(axes):
        draw(a,tr[:,j],sample_time,'Plant truth','#151515')
        for k,rows in traces.items():
            draw(a,rows[:,6+j],lambda ix,r=rows:r[ix,1],k,colors[k])
        a.set_ylabel(STATES[j])
    save(fig,axes,'states','Five continuous dynamic states — SOC is a fraction')

    for reference in [False, True]:
        fig,axes = plt.subplots(4,3,figsize=(15,13),layout='constrained')
        for j,name in enumerate(PARAMETERS):
            a = axes.flat[j]
            if reference:
                a.axhline(cell['parameters'][name],color='#151515',label='Plant reference truth',lw=1)
            else:
                draw(a,tr[:,5+j],sample_time,'Plant at T(t)','#151515')
            for k,rows in traces.items():
                draw(a,rows[:,(22 if reference else 11)+j],lambda ix,r=rows:r[ix,1],k,colors[k])
            a.set_ylabel(name)
        axes.flat[-1].set_visible(False)
        save(fig,axes,'parameters_reference' if reference else 'parameters_effective',
             'Eleven continuous parameters at '+('25°C reference' if reference else 'measured temperature'))

    fig,axes = plt.subplots(3,1,figsize=(12,9),layout='constrained')
    for j,a in enumerate(axes):
        derived(a,len(tr),lambda sl,j=j:tr[sl,8+2*j]/tr[sl,7+2*j],sample_time,'Plant C=tau/R','#151515')
        for k,rows in traces.items():
            draw(a,rows[:,33+j],lambda ix,r=rows:r[ix,1],k,colors[k])
        a.set_ylabel('C%d (F)'%(j+1))
    save(fig,axes,'capacitances','Derived RC capacitances at measured temperature')

    fig,axes = plt.subplots(2,1,figsize=(12,7),layout='constrained')
    for k,rows in traces.items():
        t = lambda i,r=rows:r[i,1]
        derived(axes[0],len(rows),lambda sl,r=rows:100*(r[sl,11]/truth[r[sl,0].astype(int)-1,5]-1),t,k,colors[k])
        derived(axes[1],len(rows),lambda sl,r=rows:100*(r[sl,6]-truth[r[sl,0].astype(int)-1,0]),t,k,colors[k])
    for a in axes:
        a.axhspan(-.5,.5,color='#cfe5ce',alpha=.5)
        a.set_yscale('symlog',linthresh=.5)
    axes[0].set_ylabel('Q relative error (%)')
    axes[1].set_ylabel('SOC error (percentage points)')
    save(fig,axes,'errors','Point errors — uncertainty coverage remains unvalidated')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('case',type=Path)
    p.add_argument('--start-hour',type=float,default=0.)
    p.add_argument('--end-hour',type=float)
    p.add_argument('--out',type=Path,required=True)
    args = p.parse_args()
    if args.out.exists():
        p.error('--out must be a new directory; original plots are preserved')
    if not np.isfinite(args.start_hour) or args.start_hour < 0 or (args.end_hour is not None and
            (not np.isfinite(args.end_hour) or args.end_hour <= args.start_hour)):
        p.error('finite increasing nonnegative hour range required')
    result = json.loads((args.case/'result.json').read_text())
    config = json.loads((args.case.parent/'calibration.json').read_text())
    cell = json.loads((args.case/'scenario.json').read_text())['cell_definition']
    render(args.case,result,config,cell,args.out,args.start_hour,args.end_hour)
    print(args.out.resolve())


if __name__ == '__main__':
    main()
