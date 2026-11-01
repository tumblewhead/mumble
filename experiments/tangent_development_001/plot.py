"""Focused task-error facets and a resource/forecast summary; no raw logs needed."""
import argparse
import json
import os
from pathlib import Path
import tempfile


def render(out):
    os.environ.setdefault('MPLCONFIGDIR', tempfile.mkdtemp(prefix='mumble-tangent-mpl-'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    summary = json.loads((out/'summary.json').read_text())
    styles = dict(field64=('#248544', 'o'), tangent64=('#7b38a3', 's'))
    phases = ('before_refresh', 'after_refresh', 'mid_interval')
    totals = []
    for prefix in summary['prefixes']:
        case = out/prefix['directory']
        if not (case/'forecasts.json').exists():
            continue
        rows = json.loads((case/'forecasts.json').read_text())
        tasks = list(dict.fromkeys(r['task'] for r in rows))
        fig, axes = plt.subplots(2, 3, figsize=(17, 9), sharex=True, sharey='row', constrained_layout=True)
        for col, phase in enumerate(phases):
            for row, (metric, label) in enumerate((('minimum_error_V', 'Minimum voltage error (mV)'),
                                                  ('recovery_error_V', 'End-of-task/recovery error (mV)'))):
                ax = axes[row, col]
                for arm, (color, marker) in styles.items():
                    selected = {r['task']: r for r in rows if r['arm'] == arm and r['phase'] == phase and 'scoring' in r}
                    y = [1000*selected[t]['scoring'][metric] if t in selected else np.nan for t in tasks]
                    ax.plot(range(len(tasks)), y, color=color, marker=marker, markersize=4, lw=.8, label=arm)
                ax.axhline(0, color='black', lw=.6)
                ax.grid(alpha=.2)
                ax.set_xticks(range(len(tasks)), [t.replace('pulse_', '') for t in tasks], rotation=75, ha='right', fontsize=7)
                if col == 0:
                    ax.set_ylabel(label)
                if row == 0:
                    ax.set_title(phase.replace('_', ' '))
        axes[0, 0].legend()
        unresolved = sum(r['status'] != 'diagnostic' for r in rows)
        fig.suptitle(prefix['directory']+f' — signed forecast errors; {unresolved} unresolved rows\nTasks are separate forks, not a time series; geometry ablation and support diagnostics in forecasts.json')
        fig.savefig(case/'forecast_errors.png', dpi=160)
        plt.close(fig)
        profile = json.loads((case/'profile.json').read_text())
        totals.append((prefix['directory'], profile, rows))
    if not totals:
        return
    fig, axes = plt.subplots(1, 3, figsize=(16, max(4, .4*len(totals)+2)), constrained_layout=True)
    for j, (arm, (color, marker)) in enumerate(styles.items()):
        y = np.arange(len(totals))+(j-.5)*.25
        mean = [1e6*p[arm]['uninstrumented_seconds']['mean'] for _, p, _ in totals]
        worst = [1e3*p[arm]['uninstrumented_seconds']['maximum'] for _, p, _ in totals]
        error = [max((1000*abs(r['scoring']['minimum_error_V']) for r in rows if r['arm']==arm and 'scoring' in r), default=np.nan) for _, _, rows in totals]
        for ax, values in zip(axes, (mean, worst, error)):
            ax.scatter(values, y, color=color, marker=marker, label=arm)
            ax.set_yticks(range(len(totals)), [x[0] for x in totals])
            ax.grid(alpha=.2)
    for ax, label in zip(axes, ('Mean advance per 16 samples (µs)', 'Largest observed advance (ms)', 'Worst absolute voltage-minimum error (mV)')):
        ax.set_xlabel(label)
    axes[0].legend()
    fig.suptitle('Development witnesses — host costs and point prediction; uncertainty is not calibrated')
    fig.savefig(out/'scorecard.png', dpi=160)
    plt.close(fig)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('out', type=Path)
    render(p.parse_args().out)
