"""Render compact summaries without rereading or reconstructing raw samples."""
import numpy as np
from .telemetry import PARAMETERS, STATES, TRACE_COLUMNS


def render_compact(case, result, cell, destination, start_hour, end_hour, overlays, alpha, styles=None, case_style=None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from .plot import save_plot
    rate = result['sample_rate_Hz']
    first_case = overlays is None or not overlays
    title = ', '.join(str(result['scenario'][k]) for k in ['cell','load','noise_v','seed'])
    if 'load_seed' in result['scenario']:
        title += f", load seed {result['scenario']['load_seed']}"
    title += ' — compact bin means/ranges; zoom resolution limited by stored bins'
    colors = dict(float64='#3165b4', float32='#dc7822')
    styles = styles or {k:dict(label=k,color=colors[k],linestyle='-') for k in result['arms']}
    case_style = case_style or {}
    truth_color = case_style.get('color','#151515')
    truth_prefix = (case_style['label']+' / ') if case_style.get('label') else ''
    with np.load(case/'plot_summary.npz', allow_pickle=False) as stored:
        data = {k: stored[k] for k in stored.files}

    def draw(ax, prefix, column, label, color, linestyle='-'):
        if prefix == 'plant':
            label = truth_prefix+label
            color = case_style.get('color',color)
            linestyle = case_style.get('truth_linestyle',linestyle)
        low_t = data[prefix+'_first']/(3600*rate)
        high_t = data[prefix+'_last']/(3600*rate)
        mask = high_t > start_hour
        if end_hour is not None:
            mask &= low_t <= end_hour
        if not mask.any():
            return
        # Stair-step bins retain temporal support, including a single occupied bin.
        # A zoom includes whole intersecting bins, never fabricated fine detail.
        t = np.column_stack([low_t[mask], high_t[mask]]).ravel()
        low = np.repeat(data[prefix+'_low'][mask, column], 2)
        high = np.repeat(data[prefix+'_high'][mask, column], 2)
        mean = np.repeat(data[prefix+'_mean'][mask, column], 2)
        ax.fill_between(t, low, high, color=color, alpha=.2*alpha)
        ax.plot(t, mean, color=color, alpha=alpha, lw=.9, label=label+' (bin mean/range)',linestyle=linestyle)

    def panels(name, rows, cols, size, heading):
        if overlays is not None and name in overlays:
            fig, axes = overlays[name][:2]
        else:
            fig, axes = plt.subplots(rows, cols, figsize=size, layout='constrained', squeeze=False)
            axes = axes.ravel()
            if overlays is not None:
                fig._campaign_shared_legend = True
        return fig, np.asarray(axes).ravel(), heading

    def save(group, name):
        fig, axes, heading = group
        if overlays is None:
            save_plot(fig, axes, destination, name, heading, title)
        else:
            overlays[name] = (fig, axes, heading)

    def estimates(ax, column):
        for kind in result['arms']:
            draw(ax, kind, column, **styles[kind])

    group = panels('signals',3,1,(12,9),'V / I / T — estimated V is an assimilated fit, not a forecast')
    axes = group[1]
    draw(axes[0],'plant',3,'Measured V','#999999')
    draw(axes[0],'plant',21,'Noiseless plant V',truth_color)
    estimates(axes[0],5)
    draw(axes[1],'plant',1,'Current (+ discharge)','#3165b4')
    draw(axes[2],'plant',2,'Exogenous temperature','#dc7822')
    for ax, unit in zip(axes,['V','A','°C']):
        ax.set_ylabel(unit)
    save(group,'signals')

    group = panels('states',5,1,(12,13),'Five continuous dynamic states — SOC is a fraction')
    for j, ax in enumerate(group[1]):
        draw(ax,'plant',5+j,'Plant truth',truth_color)
        estimates(ax,6+j)
        ax.set_ylabel(STATES[j])
    save(group,'states')

    for reference in [False, True]:
        name = 'parameters_reference' if reference else 'parameters_effective'
        group = panels(name,4,3,(15,13),'Eleven continuous parameters at '+('25°C reference' if reference else 'measured temperature'))
        for j, parameter in enumerate(PARAMETERS):
            ax = group[1][j]
            if reference and len(data['plant_first']):
                first, last = data['plant_first'][0]/(3600*rate), data['plant_last'][-1]/(3600*rate)
                ax.plot([max(first,start_hour),min(last,end_hour) if end_hour is not None else last],
                        [cell['parameters'][parameter]]*2,color=truth_color,alpha=alpha,lw=1,label=truth_prefix+'Plant reference truth',linestyle=case_style.get('truth_linestyle','-'))
            elif not reference:
                draw(ax,'plant',10+j,'Plant at T(t)',truth_color)
            estimates(ax,(22 if reference else 11)+j)
            ax.set_ylabel(parameter)
        group[1][-1].set_visible(False)
        save(group,name)

    group = panels('capacitances',3,1,(12,9),'Derived RC capacitances at measured temperature')
    for j, ax in enumerate(group[1]):
        draw(ax,'plant',22+j,'Plant C=tau/R',truth_color)
        estimates(ax,33+j)
        ax.set_ylabel('C%d (F)'%(j+1))
    save(group,'capacitances')

    group = panels('errors',4,1,(12,12),'Q / SOC errors and assimilated endpoint voltage fit\nVoltage residuals are in-sample; uncertainty coverage remains unvalidated')
    for j, ax in enumerate(group[1]):
        estimates(ax,len(TRACE_COLUMNS)+32+j)
        if j < 2:
            if first_case:
                ax.axhspan(-.5,.5,color='#cfe5ce',alpha=.5)
            ax.set_yscale('symlog',linthresh=.5)
        elif first_case:
            ax.axhline(0,color='#555555',lw=.7)
        ax.set_ylabel(['Q relative error (%)','SOC error (percentage points)',
                       'V fit − measured (mV)','V fit − noiseless plant (mV)'][j])
    save(group,'errors')
