#!/usr/bin/env python3
"""Render the completed probe; no physical-model or learner calls."""
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


ROOT = Path(__file__).resolve().parent
ATTEMPT = ROOT / 'attempt001'
raw = json.loads((ATTEMPT / 'raw_probe.json').read_text())
result = json.loads((ATTEMPT / 'result.json').read_text())
receipt = json.loads((ATTEMPT / 'receipt.json').read_text())
assert result['interpretation_eligible'] and receipt['status'] == 'completed'
assert receipt['canonical_probe_invocations'] == 1
rows = []
for snapshot in raw['snapshots']:
    for component in snapshot['components']:
        reduced = next(row for row in result['components']
                       if row['checkpoint_next_index'] == snapshot['checkpoint_next_index']
                       and row['component'] == component['component'])
        h = reduced['bounded_scalar_moments'][15]
        rows.append({
            'nominal_seconds': snapshot['nominal_checkpoint_s'],
            'next_index': snapshot['checkpoint_next_index'],
            'component': component['component'],
            'next_current_A': snapshot['current_A'],
            'next_dt_s': snapshot['dt_s'],
            'rule_admissible': reduced['moment_rule_admissible'],
            'invalid_nodes': len(reduced['invalid_nodes']),
            'node_propagations': reduced['node_propagations'],
            'saved_h_mean': h['mean'],
            'saved_h_SD': math.sqrt(h['variance']),
            'bounded_moment_violations': [row for row in reduced['bounded_scalar_moments'] if row['violation']],
            'comparison': reduced['nonlinear_comparison'],
        })

figure_dir = ROOT / 'figures'
figure_dir.mkdir(exist_ok=True)
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                     'axes.spines.top': False, 'axes.spines.right': False,
                     'axes.titleweight': 'bold', 'savefig.facecolor': 'white'})
fig, (left, right) = plt.subplots(1, 2, figsize=(13.2, 6.3), gridspec_kw={'width_ratios': [1.05, 1.1]})
fig.subplots_adjust(left=0.095, right=0.975, bottom=0.18, top=0.76, wspace=0.34)
fig.suptitle('Small local nonlinear corrections; one physically incompatible belief',
             x=0.05, y=0.965, ha='left', fontsize=18, weight='bold')
fig.text(0.05, 0.91, 'Three saved checkpoints · two components each · one next archived observation',
         fontsize=11, color='#475569')

labels = []
for y, row in enumerate(rows):
    labels.append(f"{row['nominal_seconds']:,.0f} s  /  C{row['component']}")
    if row['rule_admissible']:
        value = abs(row['comparison']['signed_mean_change_V']) * 1e6
        left.scatter(value, y, s=55, color='#087f8c', zorder=4)
        left.text(value * 1.28, y, f'{value:.3f}', va='center', color='#155e75', fontsize=10)
    else:
        left.text(0.8, y, 'Rule inadmissible: 16 nodes outside h bound',
                  va='center', color='#b42333', fontsize=9)
left.set_yticks(range(len(rows)), labels)
left.invert_yaxis()
left.set_ylim(5.6, -0.6)
left.set_xscale('log')
left.set_xlim(0.7, 1800)
left.set_xticks([1, 10, 100, 1000], ['1', '10', '100', '1,000'])
left.axvline(100, color='#9a6700', linestyle='--', linewidth=1.2)
left.axvline(1000, color='#475569', linestyle=':', linewidth=1.5)
left.text(100, -0.83, 'Decision\nscale', ha='center', va='bottom', color='#9a6700', fontsize=9)
left.text(1000, -0.83, 'Noise\nSD', ha='center', va='bottom', color='#475569', fontsize=9)
left.set_xlabel('Absolute voltage-mean change (µV, logarithmic scale)', labelpad=12)
left.set_title('Nonlinear versus linearized prediction', loc='left', pad=52, fontsize=12)
left.grid(axis='x', color='#e2e8f0', linewidth=0.7)

witness = next(snapshot for snapshot in raw['snapshots'] if snapshot['checkpoint_next_index'] == 294000)['components'][0]
extent = max(abs(node['pre_state'][15] - 1) * 1e6 for node in witness['nodes']) * 1.15
right.axvspan(0, extent, color='#fce7e9', zorder=0)
right.axvspan(-extent, 0, color='#e6f4f1', zorder=0)
right.axvline(0, color='#334155', linewidth=1.2)
for k in range(16):
    pair = [node for node in witness['nodes'] if node['column'] == k]
    values = [(node['pre_state'][15] - 1) * 1e6 for node in pair]
    positions = [k + 1 + (-0.15 if node['pre_failure_mask'] else 0.15) for node in pair]
    right.plot(values, positions, color='#94a3b8', linewidth=0.7, zorder=1)
    for node, value, position in zip(pair, values, positions):
        right.scatter(value, position, s=23,
                      color='#b42333' if node['pre_failure_mask'] else '#087f8c', zorder=3)
right.set_xlim(-extent, extent)
right.set_ylim(16.8, 0.2)
right.set_yticks([1, 4, 8, 12, 16])
right.set_ylabel('Factor-column direction (paired nodes offset)')
right.set_xlabel('Node displacement from upper bound: (h − 1) × 10⁶', labelpad=12)
right.set_title('8,400 s / C0: mean h = 1, SD = 9.056 × 10⁻⁶', loc='left', pad=52, fontsize=12)
right.text(-extent * 0.5, -0.8, '16 nodes in range', ha='center', color='#087f8c', fontsize=10)
right.text(extent * 0.5, -0.8, '16 nodes outside', ha='center', color='#b42333', fontsize=10)
fig.text(0.05, 0.075, 'At a physical upper bound, an exact bounded distribution must have zero variance. '
         'This saved pair has Var(h) = 8.200 × 10⁻¹¹.', fontsize=10, color='#334155')
fig.text(0.05, 0.035, 'The node counts are properties of this quadrature rule, not probability estimates. '
         'No nonlinear moment was formed from the surviving nodes.', fontsize=9, color='#64748b')
figure = figure_dir / 'conditional_probe.png'
fig.savefig(figure, dpi=160)
plt.close(fig)

comparisons = [row['comparison'] for row in rows if row['rule_admissible']]
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
summary = {
    'schema': 'mumble_conditional_belief_adequacy_summary_v1',
    'status': 'probe_complete_constraint_moment_incompatibility_confirmed',
    'source_revision': result['source_revision'],
    'plan_sha256': result['plan_sha256'],
    'canonical_probe_invocations': receipt['canonical_probe_invocations'],
    'decision_class': result['decision_class'],
    'node_propagations': result['node_propagations'],
    'center_propagations': result['center_propagations'],
    'admissible_components': len(comparisons),
    'inadmissible_components': result['inadmissible_components'],
    'bounded_scalar_checks': len(rows) * 16,
    'bounded_scalar_violations': result['bounded_scalar_violations'],
    'numerical_checks': result['numerical_checks'],
    'maximum_absolute_mean_change_V': max(abs(row['signed_mean_change_V']) for row in comparisons),
    'maximum_absolute_variance_change_V2': max(abs(row['signed_variance_change_V2']) for row in comparisons),
    'maximum_absolute_mean_change_over_sigma_V': max(abs(row['mean_change_over_sigma_V']) for row in comparisons),
    'maximum_absolute_variance_change_over_sigma_V_squared': max(abs(row['variance_change_over_sigma_V_squared']) for row in comparisons),
    'decision_scales': result['decision_scales'],
    'components': rows,
    'resources': {'probe': receipt['probe'], 'supervisor': receipt['supervisor'],
                  'closed_derived_bytes': receipt['closed_derived_bytes']},
    'all_bound_inputs_unchanged': receipt['all_bound_inputs_unchanged'],
    'new_learner_ingests': 0, 'new_source_generations': 0, 'old_scorer_runs': 0,
    'new_estimator_SRAM_bytes': 0, 'coverage_validated': False, 'candidate_promoted': False,
    'input_artifacts': {name: sha(ATTEMPT / name) for name in ['raw_probe.json', 'result.json', 'receipt.json']},
    'reporting_source_sha256': sha(Path(__file__)),
    'figure_sha256': sha(figure),
    'limits': result['limits'],
}
(ROOT / 'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n')
print(json.dumps({'summary': str(ROOT / 'summary.json'), 'figure': str(figure),
                  'admissible': len(comparisons), 'bounded_moment_violations': result['bounded_scalar_violations']}))
