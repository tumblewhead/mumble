"""Compact evidence receipt and plotting from frozen fit/scoring artifacts."""
import argparse
import json
from pathlib import Path
import numpy as np
from experiments.uncertainty_weak_stimulus_001.diagnostics import identity,write


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--scores',type=Path,required=True)
    p.add_argument('--ablations',type=Path,nargs=2,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False);root=Path(__file__).resolve().parents[2]
    scores=json.loads(a.scores.read_text());parentpath=root/'provenance/shared_uncertainty_growth_001/receipt.json';parent=json.loads(parentpath.read_text())
    cases=[]
    for r in scores['cases']:
        prior=next(c for c in parent['cases'] if c['seed']==r['seed'] and c['records']==r['records'])
        f=[x for x in r['forecasts'] if x['arm']=='candidate_native' and x['status']=='supported']
        b=[x for x in r['forecasts'] if x['arm']=='baseline_native' and x['status']=='supported']
        def stats(values):
            return dict(reference_pooled_RMS_uV=float(np.sqrt(np.mean([x['reference_RMS_difference_uV']**2 for x in values]))),
                reference_max_path_difference_uV=max(x['reference_max_difference_uV'] for x in values),
                truth_pooled_RMS_uV=float(np.sqrt(np.mean([x['truth_RMS_error_uV']**2 for x in values]))),
                max_pointwise_3SD_miss_fraction=max(x['pointwise_3SD_miss_fraction'] for x in values),
                unsupported_joint_probes=sum(x['unsupported_probes'] for x in values))
        cases.append(dict(seed=r['seed'],hours=r['hours'],records=r['records'],degree=r['degree'],
            Q_shift_reference_SD=r['diagnostics']['candidate_minus_reference_Q_local_SD'],
            baseline_Q_shift_reference_SD=-prior['exact_minus_field_Q_local_SD'],
            Q_shift_reduction=abs(prior['exact_minus_field_Q_local_SD']/r['diagnostics']['candidate_minus_reference_Q_local_SD']),
            joint_center_distance=r['diagnostics']['joint_center_distance'],
            baseline_joint_center_distance=prior['full_joint_local_distance'],
            Q_width_ratio=r['diagnostics']['Q_width_ratio_at_optima'],
            Q_error_percent=r['Q_error_percent'],Q_error_local_SD=r['Q_error_SD'],
            transport_h_difference=r['transport'].get('h_difference'),
            candidate_forecasts=stats(f),baseline_forecasts=stats(b),
            forecast_details=[{k:x[k] for k in ['arm','task','reference_RMS_difference_uV','truth_RMS_error_uV','truth_minimum_error_uV','truth_recovery_error_uV','pointwise_3SD_miss_fraction']} for x in r['forecasts'] if x['status']=='supported'],
            storage=r['storage'],build_wall_s=r['build_wall_s'],fit_stop=r['fit_stop'],evidence=r['evidence']))
    ablations=[]
    for p in a.ablations:
        data=json.loads(p.read_text())
        ablations.append(dict(seed=data['seed'],path=str(p.resolve()),identity=identity(p),cases=[
            dict(records=c['records'],modes=c['modes'],variants=[
                dict(degree=v['degree'],collocation_order=v['collocation_order'],Q_reference_shift_SD=v['Q_reference_shift_SD'],
                    fit_stop=v['fit']['diagnostic']['stop'],transport_status=v['transport_status'],storage=v['storage'])
                for v in c['variants']]) for c in data['cases']]))
    sources=list(Path(__file__).parent.glob('*.py'))+list(Path(__file__).parent.glob('*.c'))+list(Path(__file__).parent.glob('*.json'))
    sources += [root/n for n in ['experiments/shared_uncertainty_growth_001/audit.py','experiments/slow_likelihood_diagnostic_001/numerics.py',
        'experiments/joint_rate_history_001/field.py','experiments/foster_campaign_001/field_backend.py','experiments/foster_campaign_001/coordinates.py',
        'experiments/foster_feedback_001/estimator.py','experiments/foster_feedback_001/plant.py','experiments/tangent_development_001/forecast.py',
        'experiments/foster_uncertainty_audit_001/conditional_packet.py','experiments/uncertainty_weak_stimulus_001/diagnostics.py']]
    write(a.out/'receipt.json',dict(status='eight_matched_refinements_and_fixed_grid_ablations_complete',base_revision='4367e92',
        sources={str(p.relative_to(root)):identity(p) for p in sources},postfit=dict(path=str(a.scores.resolve()),identity=identity(a.scores)),
        parent_receipt=identity(parentpath),tests=20,cases=cases,ablations=ablations,
        forecast_aggregation='Square root of mean task RMS squared; equal task weights, not independent coverage trials',
        numpy_version=np.__version__,
        production_changed=False,default_changed=False,additional_production_storage_B=0,
        selected_reference='RC5/H7; diagnostic reference for leaner implementation, not promoted to campaign',
        limits=['Selected stationary prefixes; local MAP/GN, not calibrated coverage or indefinite aging history.',
          'Full degree7 factor exceeds10KiB SRAM; root49.4KiB before live state/workspace.',
          'Closer likelihood approximation does not guarantee smaller truth error on each noise realization.',
          'No original checkpoint migration; omitted modes require rebuilding data in this offline study.']))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
    colors=['#0072B2','#D55E00','#009E73','#CC79A7']
    for color,(seed,n) in zip(colors,[(1100,4325376),(1103,4325376),(1100,12976128),(1103,12976128)]):
        rows=sorted([c for c in cases if c['seed']==seed and c['records']==n],key=lambda r:r['degree'])
        label=f"seed {seed} / {round(rows[0]['hours'])} h"
        axes[0].plot([5,6,7],[abs(rows[0]['baseline_Q_shift_reference_SD'])]+[abs(r['Q_shift_reference_SD']) for r in rows],marker='o',color=color,label=label,linestyle='--' if seed==1103 else '-')
        axes[1].plot([5,6,7],[rows[0]['baseline_forecasts']['reference_pooled_RMS_uV']]+[r['candidate_forecasts']['reference_pooled_RMS_uV'] for r in rows],marker='o',color=color,label=label,linestyle='--' if seed==1103 else '-')
    for ax in axes:
        ax.set_xticks([5,6,7]);ax.set_xlabel('Hysteresis total degree (RC degree fixed at 5)');ax.grid(alpha=.25);ax.set_yscale('log')
    axes[0].set_ylabel('|Q center difference| / reference local SD');axes[0].set_title('Joint likelihood fit')
    axes[1].set_ylabel('Forecast difference RMS (µV)');axes[1].set_title('60 s rest and 120 mA pulse/recovery');axes[1].legend(fontsize=8)
    fig.suptitle('Approximation relative to the retained-data reference')
    fig.savefig(a.out/'comparison.png',dpi=180);plt.close(fig)
    print(a.out/'receipt.json')

if __name__=='__main__':main()
