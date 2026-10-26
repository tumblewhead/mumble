#!/usr/bin/env python3
"""Render the completed, immutable weighting audit; no estimator execution."""
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir()) / 'mumble-mpl-cache'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


HERE = Path(__file__).resolve().parent
ATTEMPT = HERE / 'attempt001'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    result = json.loads((ATTEMPT / 'result.json').read_text())
    if result['status'] != 'passed_accounting_and_saved_evidence_audit':
        raise RuntimeError('Do not present a failed audit as a result')
    with (ATTEMPT / 'focus_odds.csv').open() as stream:
        focus = [{k: float(v) for k, v in row.items()} for row in csv.DictReader(stream)]
    with (ATTEMPT / 'query_diagnostics.csv').open() as stream:
        queries = list(csv.DictReader(stream))
    # This is the frozen focus interval, sampled on the saved full-query grid.
    sampled = [row for row in queries if 7800 < float(row['nominal_time_s']) <= 7825]
    sampled_stats = {}
    for key in ['score_delta', 'residual_score_term', 'variance_score_term',
                'innovation0_mV', 'innovation1_mV', 'innovation_sd0_mV', 'innovation_sd1_mV']:
        values = [float(row[key]) for row in sampled]
        sampled_stats[key] = {'count': len(values), 'sum': math.fsum(values),
                             'mean': math.fsum(values) / len(values),
                             'RMS': math.sqrt(math.fsum(x*x for x in values) / len(values))}
    crossing = {int(row['next_index']): row for row in focus if int(row['next_index']) in (273390, 273391)}
    context = [row for row in queries if 7800 <= float(row['nominal_time_s']) <= 7825]
    times = [row['nominal_time_s'] for row in focus]
    qt = [float(row['nominal_time_s']) for row in context]
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11,
                         'axes.spines.top': False, 'axes.spines.right': False})
    fig, (ax, bx) = plt.subplots(2, 1, figsize=(10.5, 7.4), sharex=True,
                                gridspec_kw={'height_ratios': [1.35, 1]})
    fig.suptitle('A weight change moves the reported SOC', fontsize=18, weight='bold', x=.09, ha='left')
    ax.axhspan(-.5, .1, color='#e8f4ec', alpha=.8, label='Within preferred SOC target')
    ax.plot(times, [row['SOC_error_pp'] for row in focus], color='#202937', lw=2.3,
            label='Aggregate: recorded 35 Hz output', zorder=4)
    ax.plot(qt, [float(row['component0_SOC_error_pp']) for row in context], color='#008577',
            marker='o', ms=3, lw=1.5, label='Component 0: saved queries')
    ax.plot(qt, [float(row['component1_SOC_error_pp']) for row in context], color='#b95616',
            marker='o', ms=3, lw=1.5, label='Component 1: saved queries')
    ax.axhline(-.5, color='#668d70', ls='--', lw=1)
    ax.set(ylabel='SOC error (percentage points)', ylim=(-.78, .06))
    ax.legend(loc='upper right', frameon=True, fontsize=9)
    ax.text(.015, .13, '99.963% of the 7,811–7,812 s error change\nis attributed to weight motion by the midpoint identity.',
            transform=ax.transAxes, fontsize=10, bbox={'facecolor': 'white', 'edgecolor': '#d0d7de', 'pad': 7})
    bx.plot(times, [row['weight1_post'] for row in focus], color='#7056a3', lw=2.1)
    bx.axhline(.5, color='#b0b4bb', lw=.8, ls=':')
    bx.set(ylabel='Component 1 normalized weight', xlabel='Time since start (s)', ylim=(-.04, 1.08), xlim=(7800,7825))
    bx.text(7811.8, .43, 'One update: 5.08% → 84.88%\nat 7,811.171 s', fontsize=10,
            bbox={'facecolor': 'white', 'edgecolor': '#d0d7de', 'pad': 5})
    for axis in (ax, bx):
        axis.axvline(273391/35, color='#9d3346', ls='--', lw=1)
        axis.grid(axis='y', color='#e0e4e8', lw=.7)
    fig.text(.09, .012, 'Preserved Cell B evidence. Components remain active. The figure shows output attribution, not a calibrated uncertainty guarantee.', fontsize=9, color='#485260')
    fig.subplots_adjust(left=.09, right=.98, top=.91, bottom=.1, hspace=.2)
    (HERE / 'figures').mkdir(exist_ok=True)
    figure = HERE / 'figures' / 'weight_switch.png'
    fig.savefig(figure, dpi=165)
    plt.close(fig)
    summary = {
        'schema': 'mumble_weighting_output_diagnostic_summary_v1',
        'status': 'saved_evidence_diagnostic_complete_no_production_patch',
        'audit_source_revision': result['source_revision'],
        'audit_status': result['status'], 'new_learner_runs': 0, 'new_source_generations': 0,
        'old_scorer_runs': 0, 'new_estimator_SRAM_bytes': 0,
        'query_counts': result['query_counts'],
        'context_scalar_records': result['context_scalar_scan']['records'],
        'numeric_comparisons': sum(group['comparisons'] for group in result['checks'].values()),
        'mismatches': result['mismatches'],
        'dominance_crossing': result['context_scalar_scan']['dominance_changes'],
        'crossing_scalar_rows': crossing,
        'SOC_error_motion_7811_to_7812': result['SOC_error_motion_7811_to_7812'],
        'sampled_focus_score_statistics': {'scope': '25 saved queries with7800<t<=7825s; not all875 intervening35Hz updates',
                                          'statistics': sampled_stats},
        'interval_counts': result['selected_query_interval_counts'],
        'endpoint_checks': result['endpoint_interval_audit']['checks'],
        'final_B': result['final_B_interval_units'],
        'resources': result['resources'],
        'coverage_validated': False, 'candidate_promoted': False,
        'source_identities': {name: digest(ATTEMPT/name) for name in ['result.json','query_diagnostics.csv','focus_odds.csv']},
        'reporting_code_sha256': digest(Path(__file__)), 'figure_sha256': digest(figure),
    }
    (HERE / 'summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True)+'\n')
    print(json.dumps({'summary': str(HERE/'summary.json'), 'figure': str(figure),
                      'figure_bytes': figure.stat().st_size, 'new_estimator_runs': 0}))


if __name__ == '__main__':
    main()
