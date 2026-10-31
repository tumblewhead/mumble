"""Separate truth scoring after frozen inference; no fitting or selection here."""
import argparse
import json
from pathlib import Path
import numpy as np
from .diagnostics import identity,write


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--inputs',type=Path,required=True)
    p.add_argument('--diagnostics',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    index=json.loads((args.diagnostics/'index.json').read_text())
    if index['status']!='finished':raise ValueError('inference still running')
    rows=[]
    for item in index['cases']:
        path=args.diagnostics/item['label']/'result.json'
        if identity(path)!=item['result']:raise ValueError('inference changed after index froze')
        r=json.loads(path.read_text())
        if 'comparison' not in r:
            rows.append(dict(label=item['label'],status=r['status']));continue
        truthpath=args.inputs/item['label']/'truth_for_postfit_only.json'
        truth=json.loads(truthpath.read_text());q=truth['reference_parameters']['Q_Ah'];soc=truth['endpoint'][0]
        endpoints={'rolling':r['saved_endpoints']['float64'],'saved_field':r['saved_endpoints']['field64'],
                   'fresh_field':r['field']['native_endpoint'],'retained_reference':r['exact']['endpoint']}
        scores={}
        for name,e in endpoints.items():
            scores[name]=dict(Q_error_percent=100*(e['Q_Ah']/q-1),SOC_error_pp=100*(e['SOC']-soc),
                Q_local_SD_percent=100*e['Q_log_sd'],SOC_local_SD_pp=100*e['SOC_sd'],
                Q_error_local_SD=float(np.log(e['Q_Ah']/q)/e['Q_log_sd']),
                SOC_error_local_SD=(e['SOC']-soc)/e['SOC_sd'])
        field_anchor=r['anchors']['field']
        parts=field_anchor['partition']
        comparison=r['comparison']
        data_root=np.asarray(parts['data_root_whitened']);P=np.eye(16)+data_root.T@data_root
        gradient_difference=(np.asarray(field_anchor['exact_gradient'])-field_anchor['field_gradient']
                             -np.asarray(parts['gradient_contributions']).sum(axis=0))
        projected_assembly_error=-np.linalg.solve(P,gradient_difference)
        L=np.asarray(r['prior_root'])
        assembly_Q_SD=float(L[5]@projected_assembly_error/r['exact']['endpoint']['Q_log_sd'])
        rows.append(dict(label=item['label'],status=r['status'],fit_hours=r['fit_hours'],scores=scores,
            field_reference=comparison,predicted_Q_correction_percent=field_anchor['predicted_Q_correction_percent'],
            same_anchor_Q_SD_ratio=field_anchor['same_anchor_Q_SD_ratio_field_exact'],
            gradient_Q_correction_by_group=dict(zip(parts['groups'],parts['predicted_Q_correction_percent_by_group'])),
            forecast_NLL=r['predictions'],profiles=r['profiles'],profile_limits=r['profile_limits'],
            observed_directions=r['observed_directions'],chunk_check=r['chunk_check'],
            partition_checks={k:parts[k] for k in ['contribution_sum_max_abs_error','partition_sum_vs_objective_gradient_max_abs',
                'voltage_partition_sum_max_abs_error','jacobian_partition_sum_max_abs_error','instrumented_vs_archived_model_max_abs']},
            data_Q_information=parts['data_Q_information'],inference_identity=item['result'],truth_identity=identity(truthpath)))
        rows[-1]['partition_vs_objective_assembly_Q_error_local_SD']=assembly_Q_SD
    write(args.out/'scores.json',dict(status='postfit_scoring_complete',cases=rows,
        scope='Selected synthetic witnesses; local GN widths are not validated coverage. Truth never entered fitting.',
        source_index=identity(args.diagnostics/'index.json'),scoring_source=identity(Path(__file__))))
    render(rows,args.out)
    print('Scores: '+str(args.out/'scores.json'),flush=True)


def render(rows,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    rows=[r for r in rows if 'scores' in r];labels=[r['label'] for r in rows];x=np.arange(len(rows))
    fig,axes=plt.subplots(2,2,figsize=(13,9),layout='constrained')
    for name,offset,color in [('rolling',-.27,'#777777'),('saved_field',-.09,'#8b3d9c'),
                              ('fresh_field',.09,'#c45b00'),('retained_reference',.27,'#0674a6')]:
        axes[0,0].errorbar(x+offset,[r['scores'][name]['Q_error_percent'] for r in rows],
            yerr=[r['scores'][name]['Q_local_SD_percent'] for r in rows],fmt='o',color=color,label=name,capsize=3)
        axes[0,1].plot(x,[r['scores'][name]['Q_error_local_SD'] for r in rows],'o-',color=color,label=name)
    axes[0,0].set(title='Capacity point error with ±1 local GN SD',ylabel='Q error (%)')
    axes[0,1].set(title='Error normalized by reported local width',ylabel='log(Q estimate / truth) / SD')
    for ax in axes[0]:ax.set_xticks(x,labels,rotation=20,ha='right');ax.axhline(0,color='black',lw=.6);ax.grid(alpha=.2)
    axes[0,0].legend()
    for g in ['OCV_charge','ohmic','RC1','RC2','RC3','hysteresis']:
        axes[1,0].plot(x,[r['gradient_Q_correction_by_group'][g] for r in rows],'o-',label=g)
    axes[1,0].set(title='Predicted correction to field Q, retaining cross terms',ylabel='Linearized Q correction (%)')
    axes[1,0].set_xticks(x,labels,rotation=20,ha='right');axes[1,0].legend(ncol=2);axes[1,0].grid(alpha=.2)
    weak=next((r for r in rows if r['label']=='weak_B_cycle'),None)
    if weak:
        for name,color in [('exact','#0674a6'),('field','#c45b00')]:
            points=sorted((p['Q_Ah'],p[name]['delta_from_selected']) for p in weak['profiles'] if p[name]['status']=='converged')
            if points:axes[1,1].plot(*np.asarray(points).T,'o-',label=name,color=color)
        axes[1,1].set(title='Weak cycle: fixed-Q nuisance-refitted objectives',xlabel='Q (Ah)',ylabel='Objective difference')
        axes[1,1].set_yscale('symlog',linthresh=1);axes[1,1].legend();axes[1,1].grid(alpha=.2)
    fig.suptitle('Four-hour diagnostic witnesses — no coverage certification')
    fig.savefig(out/'diagnostics.png',dpi=160);plt.close(fig)


if __name__=='__main__':main()
