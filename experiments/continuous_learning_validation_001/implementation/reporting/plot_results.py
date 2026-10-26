#!/usr/bin/env python3
"""Extract immutable saved scores and plot their recorded query-grid errors.

This reporting program does not import or call the frozen scorer, generator,
learner, optimizer, or RNG. It never recomputes point errors or target gates.
All new files stay in the explicitly selected reporting output directory.
Requires NumPy and Matplotlib. Existing output files are never overwritten.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
import numpy as np

ROOT = Path(__file__).resolve().parents[4]
STUDY = ROOT / 'experiments/continuous_learning_validation_001/implementation'
ARMS = ('A_uninterrupted', 'A_warm_suffix', 'A_cold_suffix', 'B_continuous')
BLUE, ORANGE, HARD, PREF = '#155C9B', '#C45A24', '#AB374A', '#23856A'
GRAY, INK = '#7B8792', '#203244'


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def relative(path):
    return str(Path(path).resolve().relative_to(ROOT))


def citation(path, *parts):
    pointer = '/' + '/'.join(str(p).replace('~', '~0').replace('/', '~1') for p in parts) if parts else ''
    return {'path': relative(path), 'json_pointer': pointer}


def selected(value, keys):
    return {key: value[key] for key in keys}


def target_extract(target):
    return selected(target, ('threshold', 'classification', 'entry_pass',
        'required_interval_samples', 'observed_interval_samples',
        'first_observed_hit', 'first_interval_end_hit',
        'all_later_required_samples_pass_from', 'last_violating_or_unavailable',
        'pass_fraction_all_required_intervals', 'passed_samples',
        'available_outside_target_samples', 'available_outside_target_duration_s',
        'longest_available_outside_target_duration_s', 'unavailable_samples',
        'unavailable_duration_s', 'longest_unavailable_duration_s'))


def window_extract(window):
    out = selected(window, ('start_index', 'end_index', 'start_nominal_s',
        'end_nominal_s', 'completed_declared_window', 'retention_window', 'observed_samples'))
    out['quantities'] = {}
    for name, quantity in window['quantities'].items():
        entry, end = quantity['entry'], quantity['last_observed']
        drift = (abs(end['error']) - abs(entry['error'])
                 if entry and end and entry['error'] is not None and end['error'] is not None else None)
        out['quantities'][name] = {
            'entry': entry, 'last_observed': end,
            'raw_finite_point_errors': quantity['raw_finite_point_errors'],
            'available_current_point_errors': quantity['available_current_point_errors'],
            'targets': {level: target_extract(value) for level, value in quantity['targets'].items()},
            'derived_absolute_error_drift_end_minus_entry': drift,
            'drift_interpretation': 'Arithmetic difference of saved raw endpoint magnitudes; positive drift alone is not a target failure.'}
    out['voltage'] = window['voltage']
    return out


def query_series(path):
    """Copy saved errors and labels; aggregate counts of saved oracle labels."""
    time_s, q_error, z_error, q_available, z_available, w1 = [], [], [], [], [], []
    dominant_counts = Counter()
    oracle_counts = {q: Counter() for q in ('SOC_pp', 'Q_percent')}
    dominant_differs_oracle = Counter()
    useful_alternative = {q: Counter() for q in ('SOC_pp', 'Q_percent')}
    switches = []
    previous = None
    first, last = None, None
    count = 0
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        for line_no, line in enumerate(stream, 1):
            row = json.loads(line)
            count += 1
            if first is None:
                first = row
            last = row
            a = row['entities'][0]
            t = row['at']['nominal_time_s']
            time_s.append(t)
            q_error.append(a['errors']['Q_percent'])
            z_error.append(a['errors']['SOC_pp'])
            q_available.append(a['capacity_available'] and a['valid_for_useful_scoring'])
            z_available.append(a['point_available'] and a['valid_for_useful_scoring'])
            lw = row['log_weights']
            raw = [math.exp(value) for value in lw]
            w1.append(raw[1] / (raw[0] + raw[1]))
            dominant = 0 if lw[0] > lw[1] else 1 if lw[1] > lw[0] else None
            dominant_counts[str(dominant) if dominant is not None else 'tie'] += 1
            if dominant is not None and previous is not None and dominant != previous['component']:
                switches.append({'from_component': previous['component'], 'to_component': dominant,
                    'previous_saved_query': previous['at'], 'current_saved_query': row['at'],
                    'source': {'path': relative(path), 'jsonl_line': line_no,
                               'next_index': row['next_index'], 'keys': ['/log_weights']}})
            if dominant is not None:
                previous = {'component': dominant, 'at': row['at']}
            for quantity, availability_key in [('SOC_pp', 'point_available'), ('Q_percent', 'capacity_available')]:
                mechanism = row['mechanism'][quantity]
                oracle = mechanism['post_scoring_oracle_best_component']
                oracle_counts[quantity][str(oracle) if oracle is not None else 'unavailable'] += 1
                if dominant is not None and oracle is not None and dominant != oracle:
                    dominant_differs_oracle[quantity] += 1
                for level in ('hard', 'preferred'):
                    passes = mechanism[level]['raw_point_passes_aggregate_component0_component1']
                    # Count the already saved decisions; never apply a new threshold.
                    if (not passes[0] and a[availability_key] and a['valid_for_useful_scoring']
                            and any(passes[j + 1] and row['entities'][j + 1][availability_key]
                                    and row['entities'][j + 1]['valid_for_useful_scoring'] for j in (0, 1))):
                        useful_alternative[quantity][level] += 1
    arrays = {'time_s': np.asarray(time_s), 'Q_percent': np.asarray(q_error, dtype=float),
              'SOC_pp': np.asarray(z_error, dtype=float),
              'Q_available': np.asarray(q_available, dtype=bool),
              'SOC_available': np.asarray(z_available, dtype=bool), 'weight1': np.asarray(w1)}
    observations = {'saved_queries_read': count, 'dominant_weight_component_counts': dict(dominant_counts),
        'saved_grid_dominance_switches': switches,
        'saved_oracle_best_component_counts': {q: dict(c) for q, c in oracle_counts.items()},
        'dominant_weight_component_differs_from_saved_oracle_counts': dict(dominant_differs_oracle),
        'saved_queries_aggregate_misses_with_available_passing_component':
            {q: {level: useful_alternative[q][level] for level in ('hard', 'preferred')} for q in useful_alternative},
        'first_log_weights': first['log_weights'], 'final_log_weights': last['log_weights'],
        'final_displayed_normalized_weight1': w1[-1],
        'source': {'path': relative(path), 'jsonl_scope': 'all saved rows',
            'keys': ['/log_weights', '/mechanism/{quantity}/post_scoring_oracle_best_component',
                     '/mechanism/{quantity}/{level}/raw_point_passes_aggregate_component0_component1',
                     '/entities/{entity}/point_available', '/entities/{entity}/capacity_available',
                     '/entities/{entity}/valid_for_useful_scoring']},
        'scope': 'Descriptive counts on the saved1Hz+event/checkpoint grid, not35Hz durations. Oracle labels were computed by the frozen scorer and never selected runtime output.'}
    return arrays, observations


def extract(scores_dir):
    summaries, series, result = {}, {}, {}
    inputs = []
    for arm in ARMS:
        path = scores_dir / (arm + '.json')
        detail = scores_dir / (arm + '.full_scores.jsonl.gz')
        data = json.loads(path.read_text())
        summaries[arm] = data
        arrays, mechanism = query_series(detail)
        series[arm] = arrays
        if len(arrays['time_s']) != data['full_query_audit']['saved_queries_scored']:
            raise ValueError('Saved query count differs from immutable summary: ' + arm)
        for p in (path, detail):
            inputs.append({'path': relative(p), 'bytes': p.stat().st_size, 'sha256': digest(p)})
        endpoint = data['full_query_audit']['last_full_query']
        result[arm] = {
            'validity': selected(data, ('completed_valid_arm', 'intended_start_index', 'intended_end_index',
                'last_scored_consumed_index', 'epoch_begin', 'consumed_intervals_scored', 'metric_records_read',
                'invalid_transaction_records', 'input_or_accounting_issues', 'capacity_startup_deadline')),
            'validity_source': citation(path),
            'initial_raw_point': data['initial_raw_point'],
            'initial_raw_point_source': citation(path, 'initial_raw_point'),
            'endpoint': selected(endpoint, ('next_index', 'at', 'truth_SOC', 'truth_Q_Ah', 'log_weights',
                'natural_coordinate_names', 'truth_natural_vector', 'entities', 'mechanism')),
            'endpoint_source': citation(path, 'full_query_audit', 'last_full_query'),
            'windows': {name: {'source': citation(path, 'windows', name), **window_extract(w)}
                        for name, w in data['windows'].items()},
            'selected_points': data['selected_points'],
            'selected_points_source': citation(path, 'selected_points'),
            'uncertainty': data['full_query_audit']['uncertainty'],
            'uncertainty_source': citation(path, 'full_query_audit', 'uncertainty'),
            'local_status_counts': data['full_query_audit']['status_counts'],
            'local_status_source': citation(path, 'full_query_audit', 'status_counts'),
            'log_weight_diagnostics': data['full_query_audit']['log_weight_diagnostics'],
            'log_weight_diagnostics_source': citation(path, 'full_query_audit', 'log_weight_diagnostics'),
            'raw_component_target_disagreements': data['full_query_audit']['raw_component_target_disagreements'],
            'raw_component_target_disagreements_source': citation(path, 'full_query_audit', 'raw_component_target_disagreements'),
            'saved_grid_mechanism_observations': mechanism}
    primary = scores_dir.parent
    receipt_path, completion_path, parity_path = primary/'receipt.json', primary/'completion.json', primary/'A_warm_suffix/parity.json'
    receipt, completion, parity = [json.loads(p.read_text()) for p in (receipt_path, completion_path, parity_path)]
    study = {'primary': selected(receipt, ('status', 'learner_processes', 'learner_input_deliveries',
        'generator_evaluations', 'generator_evaluations_exact', 'primary_wall_s', 'B_started', 'B_learner_started')),
        'primary_source': citation(receipt_path), 'completion': completion,
        'completion_source': citation(completion_path), 'warm_parity': parity,
        'warm_parity_source': citation(parity_path),
        'warm_parity_scope': 'Scalar bytes and canonical checkpoints match exactly. Full queries match under frozen resume-entry workspace/reason exclusions.'}
    for p in (receipt_path, completion_path, parity_path):
        inputs.append({'path': relative(p), 'bytes': p.stat().st_size, 'sha256': digest(p)})
    target = summaries['B_continuous']['windows']['renewed_excitation']['quantities']['SOC_pp']['targets']['preferred']
    if target['available_outside_target_duration_s'] == target['longest_available_outside_target_duration_s'] and target['unavailable_samples'] == 0:
        first = target['last_violating_or_unavailable']['next_index'] - target['available_outside_target_samples'] + 1
        result['B_continuous']['derived_SOC_preferred_excursion'] = {
            'first_outside_index':first, 'first_outside_nominal_s':first/35,
            'last_outside':target['last_violating_or_unavailable'],
            'first_subsequent_sustained_pass':target['all_later_required_samples_pass_from'],
            'outside_duration_s':target['available_outside_target_duration_s'],
            'derivation':'One contiguous saved-score excursion: total outside duration equals longest outside duration and unavailable count is zero; first index = last outside index - outside sample count +1.',
            'source':citation(scores_dir/'B_continuous.json','windows','renewed_excitation','quantities','SOC_pp','targets','preferred')}
    return summaries, series, {'schema': 'mumble_continuous_observed_results_v1',
        'method': 'Read-only extraction of frozen scores and recorded full-query diagnostics. No scoring, learning, generation or noise draws.',
        'interpretation': ['All target attainment, pass fractions, excursions and retention decisions are copied from35Hz frozen score reducers.',
            'Plotted curves and descriptive oracle/weight counts use the saved1Hz+event/checkpoint grid.',
            'Raw finite errors remain separate from useful-point availability; public/cold priors are not useful attainment.',
            'Local provisional status and empirical interval inclusion do not establish calibrated coverage or application accuracy.',
            'There is no capacity startup deadline. A finite preferred-target miss neither proves eventual failure nor authorizes extension.',
            'Differences between endpoint absolute errors describe drift; stored target classifications determine retention.'],
        'inputs': inputs, 'study': study, 'arms': result}


def style_axis(ax, *, kind, maximum):
    ax.set_yscale('symlog', linthresh=.5, linscale=1.0, base=10)
    ticks = [-50, -5, -.5, 0, .5, 5, 50] if kind == 'Q_percent' else [-10, -.5, 0, .5, 10]
    ax.set_yticks(ticks)
    ax.set_yticklabels([f'{v:g}' for v in ticks])
    ax.set_ylim(-maximum, maximum)
    hard = 5 if kind == 'Q_percent' else 10
    for y in (-hard, hard):
        ax.axhline(y, color=HARD, linestyle=(0, (5, 3)), lw=1.0, zorder=1)
    for y in (-.5, .5):
        ax.axhline(y, color=PREF, linestyle=(0, (2, 2)), lw=1.05, zorder=1)
    ax.axhline(0, color='#ADB6BE', lw=.7, zorder=1)
    ax.grid(axis='x', color='#E6EBEF', lw=.6)
    ax.set_ylabel('Capacity error (%)' if kind == 'Q_percent' else 'SOC error (pp)')
    for spine in ('top', 'right'):
        ax.spines[spine].set_visible(False)
    ax.spines['left'].set_color('#BCC6CF')
    ax.spines['bottom'].set_color('#BCC6CF')
    ax.tick_params(colors=INK)


def error_curve(ax, data, quantity, scale, color, label):
    t = data['time_s'] / scale
    key = 'Q_available' if quantity == 'Q_percent' else 'SOC_available'
    known = data[key]
    ax.plot(t, np.where(known, data[quantity], np.nan), color=color, lw=1.4, label=label, zorder=4)
    ax.plot(t, np.where(~known, data[quantity], np.nan), color=GRAY, lw=1, linestyle=':', zorder=3)
    if np.any(~known):
        ax.scatter(t[~known], data[quantity][~known], s=12, facecolors='white', edgecolors=GRAY,
                   linewidths=.65, zorder=5, clip_on=False)


def endpoint_label(ax, x, y, text, color, offset):
    ax.scatter([x], [y], color=color, s=17, zorder=6)
    ax.annotate(text, xy=(x, y), xytext=offset, textcoords='offset points',
                ha='right', va='center', fontsize=10.5, color=color,
                bbox={'facecolor':'white', 'edgecolor':'none', 'alpha':.9, 'pad':2.0},
                arrowprops={'arrowstyle':'-', 'color':color, 'lw':.7}, zorder=7)


def b_plot(summaries, series, output):
    data, score = series['B_continuous'], summaries['B_continuous']
    fig = plt.figure(figsize=(12.5, 10.3), facecolor='white')
    grid = fig.add_gridspec(4, 1, height_ratios=[.24, 2.65, 2.55, 1.05],
                           left=.105, right=.97, top=.84, bottom=.13, hspace=.15)
    band = fig.add_subplot(grid[0])
    qax = fig.add_subplot(grid[1], sharex=band)
    zax = fig.add_subplot(grid[2], sharex=band)
    wax = fig.add_subplot(grid[3], sharex=band)
    phases = [(0, 2100, 'Initial learning', '#E6EDF5'), (2100, 3000, 'Rest', '#E3E5E8'),
              (3000, 7200, 'Weak 3 mA', '#DDEEE6'), (7200, 10800, 'Renewed excitation', '#FAE6D5'),
              (10800, 14400, 'Weak 1 mA', '#DDEEE6')]
    for start, end, label, color in phases:
        x, width = start/3600, (end-start)/3600
        band.add_patch(Rectangle((x, 0), width, 1, facecolor=color, edgecolor='white', linewidth=1))
        band.text(x+width/2, .5, label, ha='center', va='center', fontsize=9.5, color=INK)
        for ax in (qax, zax, wax):
            ax.axvspan(x, x+width, color=color, alpha=.22, zorder=0)
    band.set_ylim(0, 1)
    band.set_axis_off()
    for ax, quantity, maximum in ((qax, 'Q_percent', 55), (zax, 'SOC_pp', 13)):
        style_axis(ax, kind=quantity, maximum=maximum)
        error_curve(ax, data, quantity, 3600, BLUE, 'Aggregate, available')
        ax.tick_params(labelbottom=False)
    final = score['full_query_audit']['last_full_query']['entities'][0]['errors']
    endpoint_label(qax, 4, final['Q_percent'], f"Final {final['Q_percent']:+.3f}%", BLUE, (-12, -20))
    endpoint_label(zax, 4, final['SOC_pp'], f"Final {final['SOC_pp']:+.4f} pp", BLUE, (-12, 21))
    for ax, quantity in ((qax, 'Q_percent'), (zax, 'SOC_pp')):
        at = score['windows']['whole_arm']['quantities'][quantity]['targets']['preferred']['all_later_required_samples_pass_from']
        h = at['nominal_time_s']/3600
        ax.annotate(f'Preferred sustained to 4 h\nfrom {h:.3f} h', xy=(h, -.5),
            xytext=(h-.27, -9 if quantity=='Q_percent' else -4), fontsize=9.5,
            ha='center', color=INK, arrowprops={'arrowstyle':'->','color':INK,'lw':.8},
            bbox={'facecolor':'white','edgecolor':'none','alpha':.94,'pad':3})
    excursion = score['windows']['renewed_excitation']['quantities']['SOC_pp']['targets']['preferred']
    first_outside = (excursion['last_violating_or_unavailable']['next_index'] - excursion['available_outside_target_samples'] + 1)/35
    return_to_target = excursion['all_later_required_samples_pass_from']['nominal_time_s']
    zax.axvspan(first_outside/3600,return_to_target/3600,color='#E6A975',alpha=.25,zorder=.5)
    discharge = score['windows']['phase:renewed_sustained_discharge']
    zax.annotate(f'Preferred SOC excursion\n{first_outside:.2f}–{return_to_target:.2f} s',
        xy=(discharge['end_nominal_s']/3600,discharge['quantities']['SOC_pp']['last_observed']['error']),
        xytext=(1.5,3.6),ha='center',fontsize=9.5,color=INK,
        arrowprops={'arrowstyle':'->','color':ORANGE,'lw':.9},
        bbox={'facecolor':'white','edgecolor':'none','alpha':.94,'pad':3})
    wax.plot(data['time_s']/3600, data['weight1'], color='#70559A', lw=1.3)
    wax.set_ylim(-.08, 1.08)
    wax.set_yticks([0, .5, 1])
    wax.set_ylabel('Component 1\nweight')
    wax.set_xlabel('Global nominal elapsed time (hours)')
    wax.set_xlim(0, 4.04)
    wax.set_xticks(np.arange(0, 4.01, .5))
    wax.spines[['top','right']].set_visible(False)
    wax.grid(axis='x', color='#E6EBEF', lw=.6)
    handles = [Line2D([], [], color=BLUE, lw=1.6, label='Aggregate, available'),
               Line2D([], [], marker='o', color=GRAY, markerfacecolor='white', linestyle=':', label='Unavailable raw points'),
               Line2D([], [], color=HARD, linestyle='--', label='Hard: ±5% Q / ±10 pp SOC'),
               Line2D([], [], color=PREF, linestyle=':', label='Preferred: ±0.5% Q / ±0.5 pp SOC')]
    fig.legend(handles=handles, loc='upper left', bbox_to_anchor=(.1,.905), ncol=2,
               frameon=False, fontsize=10, columnspacing=2.5)
    fig.suptitle('Cell B: recorded learning and retention', x=.105, y=.978, ha='left', fontsize=19, color=INK)
    fig.text(.105,.938,'Final hour: both preferred targets retained at every required 35 Hz sample.',fontsize=12,color=INK)
    fig.text(.105,.068,'Curves: saved 1 Hz + event/checkpoint grid (14,654 queries). Target gates: all 504,000 interval ends at 35 Hz.',fontsize=9.4,color=INK)
    fig.text(.105,.046,'Error axes: symmetric log scale, linear within ±0.5. Weights are descriptive; local precision does not certify accuracy or coverage.',fontsize=9.4,color=INK)
    fig.text(.105,.024,'Renewed excitation includes discharge, rest, charge, pulses and reversals. No capacity startup deadline is imposed.',fontsize=9.4,color=INK)
    with output.open('xb') as stream:
        fig.savefig(stream, format='png', dpi=180, facecolor='white')
    plt.close(fig)


def a_plot(summaries, series, parity, output):
    fig, axes = plt.subplots(2, 1, figsize=(12.5, 8.4), sharex=True)
    fig.subplots_adjust(left=.105, right=.97, top=.79, bottom=.14, hspace=.18)
    for ax, quantity, maximum in ((axes[0], 'Q_percent', 75), (axes[1], 'SOC_pp', 15)):
        style_axis(ax, kind=quantity, maximum=maximum)
        ax.axvspan(30,35,color='#DDEEE6',alpha=.38,zorder=0)
        for arm, color, label in [('A_uninterrupted', BLUE, 'Uninterrupted / warm'),
                                  ('A_cold_suffix', ORANGE, 'Cold suffix')]:
            error_curve(ax, series[arm], quantity, 60, color, label)
        ax.axvline(15, color=INK, lw=.9, linestyle=(0,(3,3)), zorder=2)
        for arm, color, offset in [('A_uninterrupted', BLUE, (-12,-23)), ('A_cold_suffix', ORANGE, (-12,23))]:
            value = summaries[arm]['full_query_audit']['last_full_query']['entities'][0]['errors'][quantity]
            unit = '%' if quantity=='Q_percent' else ' pp'
            endpoint_label(ax,35,value,f'{value:+.3f}{unit}',color,offset)
    axes[0].text(.48,.16,'Warm restore at 15 min: exact recorded parity\n'
        f"{parity['metric_bytes']//80:,} scalar records; {parity['query_records']:,} full queries",
        transform=axes[0].transAxes,va='top',ha='left',fontsize=10.5,color=INK,
        bbox={'facecolor':'white','edgecolor':'#CDD6DE','boxstyle':'round,pad=.45','alpha':1},zorder=7)
    axes[1].text(15.3,2.0,'Cold reset / warm restore',fontsize=9.5,color=INK,ha='left')
    axes[1].text(32.5,2.0,'Weak tail',fontsize=9.5,color=PREF,ha='center')
    axes[1].set_xlim(0,35.3)
    axes[1].set_xticks(np.arange(0,36,5))
    axes[1].set_xlabel('Global nominal elapsed time (minutes)')
    handles = [Line2D([],[],color=BLUE,lw=1.7,label='Uninterrupted / warm suffix'),
               Line2D([],[],color=ORANGE,lw=1.7,label='Cold suffix after reset at 900 s'),
               Line2D([],[],color=HARD,linestyle='--',label='Hard: ±5% Q / ±10 pp SOC'),
               Line2D([],[],color=PREF,linestyle=':',label='Preferred: ±0.5% Q / ±0.5 pp SOC')]
    fig.legend(handles=handles,loc='upper left',bbox_to_anchor=(.1,.88),ncol=2,frameon=False,fontsize=10,columnspacing=2.2)
    fig.suptitle('Cell A: warm continuity and cold reacquisition',x=.105,y=.978,ha='left',fontsize=19,color=INK)
    fig.text(.105,.931,'All lifecycle arms valid. Final SOC meets preferred accuracy; capacity meets the hard target and misses preferred.',fontsize=11.5,color=INK)
    fig.text(.105,.073,'Curves: saved 1 Hz + event/checkpoint grid; target gates used every 35 Hz interval. Gray hollow points are unavailable raw priors.',fontsize=9.3,color=INK)
    fig.text(.105,.050,'Error axes: symmetric log scale, linear within ±0.5. Warm scalar bytes and canonical checkpoints match; query parity uses frozen entry exclusions.',fontsize=9.3,color=INK)
    fig.text(.105,.027,'The cold suffix reuses the same physical observations. No capacity startup deadline or eventual-convergence claim is inferred.',fontsize=9.3,color=INK)
    with output.open('xb') as stream:
        fig.savefig(stream,format='png',dpi=180,facecolor='white')
    plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scores-dir',type=Path,default=STUDY/'primary/scoring')
    parser.add_argument('--output-dir',type=Path,default=STUDY/'reporting')
    args=parser.parse_args()
    out=args.output_dir.resolve()
    if not out.is_relative_to(STUDY/'reporting'):
        raise ValueError('All outputs must stay within implementation/reporting')
    out.mkdir(parents=True,exist_ok=True)
    names=('observed_results.json','B_learning_retention.png','A_lifecycle.png')
    if any((out/name).exists() for name in names):
        raise FileExistsError('Reporting outputs already exist; choose a new reporting subdirectory')
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.labelcolor':INK,
                         'text.color':INK,'xtick.color':INK,'ytick.color':INK,
                         'axes.labelsize':11,'xtick.labelsize':10,'ytick.labelsize':10})
    summaries,series,result=extract(args.scores_dir.resolve())
    b_plot(summaries,series,out/'B_learning_retention.png')
    a_plot(summaries,series,result['study']['warm_parity'],out/'A_lifecycle.png')
    result['reporting_code']={'path':relative(Path(__file__)),'sha256':digest(__file__),
                              'matplotlib_version':matplotlib.__version__,'numpy_version':np.__version__}
    result['figures']=[{'path':relative(out/name),'sha256':digest(out/name),'bytes':(out/name).stat().st_size}
                       for name in names[1:]]
    with (out/'observed_results.json').open('x') as stream:
        json.dump(result,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps({'status':'extracted_and_plotted_saved_scores','output_dir':relative(out),
                      'files':list(names),'saved_queries':{arm:len(series[arm]['time_s']) for arm in ARMS},
                      'new_scoring_runs':0,'learner_calls':0,'noise_draws':0}))


if __name__=='__main__':
    main()
