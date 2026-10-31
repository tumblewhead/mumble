"""Offline plots and zoomed rerenders from saved telemetry; no estimator rerun."""
import argparse
import json
from functools import partial
from pathlib import Path
import numpy as np
from .rate import LEGACY_RATE
from .telemetry import PARAMETERS, TRACE_COLUMNS, STATES


def draw(ax, y, time_at, label, color, points=4000, alpha=1., linestyle='-'):
    """Bin large traces with min/max envelopes so narrow current pulses survive."""
    n = len(y)
    if not n:
        return
    if n <= points:
        ax.plot(time_at(np.arange(n))/3600, y, label=label, color=color, lw=.9, alpha=alpha, linestyle=linestyle)
        return
    starts = np.linspace(0, n, points+1, dtype=int)[:-1]
    counts = np.diff(np.r_[starts, n])
    lo = np.minimum.reduceat(y, starts)
    hi = np.maximum.reduceat(y, starts)
    mean = np.add.reduceat(y, starts)/counts
    t = time_at(starts+counts//2)/3600
    ax.fill_between(t, lo, hi, color=color, alpha=.2*alpha)
    ax.plot(t, mean, color=color, label=label+' (bin mean/range)', lw=.8, alpha=alpha, linestyle=linestyle)


def derived(ax, n, values, time_at, label, color, points=4000, alpha=1., linestyle='-'):
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
    ax.fill_between(t,low,high,color=color,alpha=.2*alpha)
    ax.plot(t,means,label=label+(' (bin mean/range)' if n>points else ''),color=color,lw=.9,alpha=alpha,linestyle=linestyle)


def save_plot(fig, axes, destination, name, heading, title):
    import matplotlib.pyplot as plt
    shared = getattr(fig, '_campaign_shared_legend', False)
    figure_labels = {}
    for ax in np.asarray(axes).ravel():
        if ax.get_visible():
            ax.grid(alpha=.2)
            ax.set_xlabel('Simulated hours')
            handles, labels = ax.get_legend_handles_labels()
            unique = dict(zip(labels, handles))
            if shared:
                figure_labels.update({label.replace(' (bin mean/range)', ''):handle for label,handle in unique.items()})
            elif unique:
                ax.legend(unique.values(), unique.keys(), fontsize=7)
    if shared and figure_labels:
        fig.legend(figure_labels.values(), figure_labels.keys(), loc='outside right upper', fontsize=7, title='Seed / arm', frameon=False)
    heading_artist=fig.suptitle(heading+'\n'+title, fontsize=12)
    if shared:
        # Center the heading over the panels, excluding the wide seed legend.
        fig.canvas.draw()
        bounds=[ax.get_position() for ax in np.asarray(axes).ravel() if ax.get_visible()]
        heading_artist.set_x((min(b.x0 for b in bounds)+max(b.x1 for b in bounds))/2)
    for suffix in ['png','pdf']:
        path = destination/(name+'.'+suffix)
        if path.exists():
            raise FileExistsError('plot exists; use a fresh --out directory: '+str(path))
        fig.savefig(path, dpi=150)
    plt.close(fig)


def render(case, result, config, cell, destination=None, start_hour=0., end_hour=None,
           *, overlays=None, alpha=1., styles=None, case_style=None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    destination = destination or case
    destination.mkdir(parents=True, exist_ok=True)
    if result.get('recording') == 'compact':
        from .compact_plot import render_compact
        return render_compact(case, result, cell, destination, start_hour, end_hour, overlays, alpha, styles, case_style)
    obs = np.load(case/'observations.npy', mmap_mode='r')
    truth = np.load(case/'truth.npy', mmap_mode='r')
    if result.get('recording') == 'replay':
        obs = obs[:result['records']]
        truth = truth[:result['records']]
    record_offset = result.get('record_offset', 0)
    rate = result.get('sample_rate_Hz', LEGACY_RATE)
    begin = max(0, int(start_hour*3600*rate)-record_offset)
    end = min(len(obs), int(end_hour*3600*rate)-record_offset if end_hour is not None else len(obs))
    if end <= begin:
        raise ValueError('plot time range contains no samples')
    o = obs[begin:end]; tr = truth[begin:end]
    sample_time = lambda ix: (record_offset+begin+ix+1)/rate
    traces = {}
    for k, stat in result['arms'].items():
        rows = np.load(case/(k+'_trace.npy'), mmap_mode='r')[:stat['outputs']]
        first = np.searchsorted(rows[:,1], (record_offset+begin)/rate, side='right')
        last = np.searchsorted(rows[:,1], (record_offset+end)/rate, side='right')
        traces[k] = rows[first:last]
    colors = dict(float64='#3165b4', float32='#dc7822')
    styles = styles or {k:dict(label=k,color=colors[k],linestyle='-') for k in traces}
    case_style = case_style or {}
    truth_color=case_style.get('color','#151515')
    truth_label=case_style.get('label','')
    truth_prefix=(truth_label+' / ') if truth_label else ''
    truth_style=case_style.get('truth_linestyle','-')
    title = ', '.join(str(result['scenario'][k]) for k in ['cell','load','noise_v','seed'])
    if 'load_seed' in result['scenario']:title+=f", load seed {result['scenario']['load_seed']}"
    draw_line = partial(draw, alpha=alpha)
    draw_derived = partial(derived, alpha=alpha)
    first_case = overlays is None or not overlays

    def panels(name, *args, **kwargs):
        if overlays is not None and name in overlays:
            return overlays[name][:2]
        fig, axes = plt.subplots(*args, **kwargs)
        if overlays is not None:
            fig._campaign_shared_legend = True
        return fig, axes

    def save(fig, axes, name, heading):
        if overlays is not None:
            overlays[name] = (fig, axes, heading)
        else:
            save_plot(fig, axes, destination, name, heading, title)

    fig, ax = panels('signals',3,1,figsize=(12,9),layout='constrained')
    draw_line(ax[0], o[:,3], sample_time, truth_prefix+'measured/input', case_style.get('color','#999999'))
    draw_line(ax[0], tr[:,16], sample_time, truth_prefix+'truth', truth_color, linestyle=truth_style)
    for k, rows in traces.items():
        draw_line(ax[0], rows[:,5], lambda ix,r=rows:r[ix,1], **styles[k])
    draw_line(ax[1], o[:,1], sample_time, truth_prefix+'measured/input' if truth_label else 'Current (+ discharge)', case_style.get('color','#3165b4'))
    draw_line(ax[2], o[:,2], sample_time, truth_prefix+'measured/input' if truth_label else 'Exogenous temperature', case_style.get('color','#dc7822'))
    for a, unit in zip(ax,['V','A','°C']):
        a.set_ylabel(unit)
    save(fig, ax, 'signals', 'V / I / T — estimated V is an assimilated fit, not a forecast')

    fig, axes = panels('states',5,1,figsize=(12,13),layout='constrained')
    for j,a in enumerate(axes):
        draw_line(a,tr[:,j],sample_time,truth_prefix+'truth',truth_color,linestyle=truth_style)
        for k,rows in traces.items():
            draw_line(a,rows[:,6+j],lambda ix,r=rows:r[ix,1],**styles[k])
        a.set_ylabel(STATES[j])
    save(fig,axes,'states','Five continuous dynamic states — SOC is a fraction')

    for reference in [False, True]:
        fig,axes = panels('parameters_reference' if reference else 'parameters_effective',
                          4,3,figsize=(15,13),layout='constrained')
        for j,name in enumerate(PARAMETERS):
            a = axes.flat[j]
            if reference:
                a.plot(sample_time(np.array([0,len(o)-1]))/3600,
                       [cell['parameters'][name]]*2,color=truth_color,
                       label=truth_prefix+'truth',lw=1,alpha=alpha,linestyle=truth_style)
            else:
                draw_line(a,tr[:,5+j],sample_time,truth_prefix+'truth',truth_color,linestyle=truth_style)
            for k,rows in traces.items():
                draw_line(a,rows[:,(22 if reference else 11)+j],lambda ix,r=rows:r[ix,1],**styles[k])
            a.set_ylabel(name)
        axes.flat[-1].set_visible(False)
        save(fig,axes,'parameters_reference' if reference else 'parameters_effective',
             'Eleven continuous parameters at '+('25°C reference' if reference else 'measured temperature'))

    fig,axes = panels('capacitances',3,1,figsize=(12,9),layout='constrained')
    for j,a in enumerate(axes):
        draw_derived(a,len(tr),lambda sl,j=j:tr[sl,8+2*j]/tr[sl,7+2*j],sample_time,truth_prefix+'truth',truth_color,linestyle=truth_style)
        for k,rows in traces.items():
            draw_line(a,rows[:,33+j],lambda ix,r=rows:r[ix,1],**styles[k])
        a.set_ylabel('C%d (F)'%(j+1))
    save(fig,axes,'capacitances','Derived RC capacitances at measured temperature')

    fig,axes = panels('errors',4,1,figsize=(12,12),layout='constrained',sharex=True)
    for k,rows in traces.items():
        t = lambda i,r=rows:r[i,1]
        draw_derived(axes[0],len(rows),lambda sl,r=rows:100*(r[sl,11]/truth[r[sl,0].astype(int)-record_offset-1,5]-1),t,**styles[k])
        draw_derived(axes[1],len(rows),lambda sl,r=rows:100*(r[sl,6]-truth[r[sl,0].astype(int)-record_offset-1,0]),t,**styles[k])
        draw_derived(axes[2],len(rows),lambda sl,r=rows:1000*(r[sl,5]-r[sl,4]),t,**styles[k])
        draw_derived(axes[3],len(rows),lambda sl,r=rows:1000*(r[sl,5]-truth[r[sl,0].astype(int)-record_offset-1,16]),t,**styles[k])
    for a in axes[:2]:
        if first_case:
            a.axhspan(-.5,.5,color='#cfe5ce',alpha=.5)
        a.set_yscale('symlog',linthresh=.5)
    for a in axes[2:]:
        if first_case:
            a.axhline(0,color='#555555',lw=.7)
    axes[0].set_ylabel('Q relative error (%)')
    axes[1].set_ylabel('SOC error (percentage points)')
    axes[2].set_ylabel('V fit − measured (mV)')
    axes[3].set_ylabel('V fit − noiseless plant (mV)')
    save(fig,axes,'errors','Q / SOC errors and assimilated endpoint voltage fit\nVoltage residuals are in-sample; uncertainty coverage remains unvalidated')


def render_summary(campaign, destination=None, start_hour=0., end_hour=None):
    """Overlay recorded cases once, retaining each trace's own time axis."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    destination = destination or campaign/'case_summary'
    destination.mkdir(parents=True, exist_ok=False)
    config = json.loads((campaign/'calibration.json').read_text())
    reports = json.loads((campaign/'summary.json').read_text())['cases']
    overlays = {}
    included, skipped = [], []
    alpha = .8
    # Sorting makes colors independent of worker completion order or zoom skips.
    ordered = sorted(reports,key=lambda r:r['directory'])
    total = sum(len(r.get('arms',{})) for r in ordered)
    palette=plt.get_cmap('tab20' if total<=20 else 'hsv')
    style_map={};style_receipt=[];position=0
    seed_pairs=[(r.get('scenario',{}).get('seed'),r.get('scenario',{}).get('load_seed')) for r in ordered]
    for report in ordered:
        seed=report.get('scenario',{}).get('seed','?')
        label=f'seed {seed}'
        load_seed=report.get('scenario',{}).get('load_seed')
        if load_seed is not None:label=f'noise seed {seed}, load seed {load_seed}'
        if seed_pairs.count((seed,load_seed))>1:label+=f" ({report['directory']})"
        arms={}
        for arm in sorted(report.get('arms',{}),reverse=True):
            color=palette(position if total<=20 else position/max(total,1))
            style=dict(label=label+' / '+arm,color=color,linestyle='-' if arm=='float64' else '--')
            arms[arm]=style;style_receipt.append(dict(directory=report['directory'],seed=seed,load_seed=load_seed,arm=arm,**style));position+=1
        style_map[report['directory']]=(arms,dict(label=label,color=next(iter(arms.values()))['color'] if arms else '#555555',truth_linestyle=':'))
    try:
        for report in reports:
            case = campaign/report['directory']
            compact = report.get('recording') == 'compact'
            required = (['plot_summary.npz', 'scenario.json'] if compact else
                        ['observations.npy', 'truth.npy', 'scenario.json']+
                        [k+'_trace.npy' for k in report.get('arms', {})])
            missing = [name for name in required if not (case/name).is_file()]
            if not report.get('arms') or missing:
                skipped.append(dict(directory=case.name, status=report['status'],
                                    reason='No arm telemetry' if not report.get('arms') else
                                           'Missing files: '+', '.join(missing)))
                continue
            n = report['records'] if compact else len(np.load(case/'observations.npy', mmap_mode='r'))
            rate = report.get('sample_rate_Hz', LEGACY_RATE)
            end = min(n, int(end_hour*3600*rate) if end_hour is not None else n)
            if end <= int(start_hour*3600*rate):
                skipped.append(dict(directory=case.name, status=report['status'],
                                    reason='No samples in requested time range'))
                continue
            cell = json.loads((case/'scenario.json').read_text())['cell_definition']
            render(case, report, config, cell, destination, start_hour, end_hour,
                   overlays=overlays, alpha=alpha, styles=style_map[case.name][0],case_style=style_map[case.name][1])
            included.append(dict(directory=case.name, status=report['status'],
                                 scenario=report['scenario']))
        title = (f'{len(included)} cases overlaid; trace opacity {alpha:g}; '
                 f'{len(skipped)} cases skipped (see cases.json)')
        if any(r.get('recording') == 'compact' for r in reports):
            title += '\nCompact traces show bin means and min/max ranges; use replay for detail.'
        for name, (fig, axes, heading) in overlays.items():
            save_plot(fig, axes, destination, name, heading, title)
        receipt = dict(status='completed' if included else 'no_plottable_cases',
                       alpha=alpha, included=included, skipped=skipped, arm_styles=style_receipt,
                       start_hour=start_hour, end_hour=end_hour)
        (destination/'cases.json').write_text(json.dumps(receipt, indent=2)+'\n')
        return receipt
    finally:
        for fig, _, _ in overlays.values():
            plt.close(fig)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('case',type=Path)
    p.add_argument('--start-hour',type=float,default=0.)
    p.add_argument('--end-hour',type=float)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--summary',action='store_true',
                   help='Treat the input as a campaign directory and overlay its cases')
    args = p.parse_args()
    if args.out.exists():
        p.error('--out must be a new directory; original plots are preserved')
    if not np.isfinite(args.start_hour) or args.start_hour < 0 or (args.end_hour is not None and
            (not np.isfinite(args.end_hour) or args.end_hour <= args.start_hour)):
        p.error('finite increasing nonnegative hour range required')
    if args.summary:
        render_summary(args.case,args.out,args.start_hour,args.end_hour)
    else:
        result = json.loads((args.case/'result.json').read_text())
        calibration = args.case/'calibration.json'
        if not calibration.exists():
            calibration = args.case.parent/'calibration.json'
        config = json.loads(calibration.read_text())
        cell = json.loads((args.case/'scenario.json').read_text())['cell_definition']
        render(args.case,result,config,cell,args.out,args.start_hour,args.end_hour)
    print(args.out.resolve())


if __name__ == '__main__':
    main()
