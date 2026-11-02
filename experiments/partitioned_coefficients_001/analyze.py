"""Compact deterministic reduction; preserves input results and their identities."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from experiments.h7_history_quality_001.history import write
from experiments.foster_campaign_001.backend import identity


def reduce(run):
    rows=[];bindings={};storage=None
    for path in sorted(run.glob('case_*/result.json')):
        result=json.loads(path.read_text());bindings[str(path)]=identity(path)
        storage=dict(coefficient_candidates=result['storage'],response_fields=result.get('response_field_storage',{}),H7=result['H7_storage'])
        for prefix in result['prefixes']:
            public=[q for q in prefix['queries'] if q['selection']=='public']
            arms=public[0]['arms']
            for name in arms:
                valid=[q['arms'][name]['metrics'] for q in public if q['arms'][name]['status']=='supported' and q['arms'][name]['metrics'] is not None]
                aggregate={}
                if valid:
                    for key in valid[0]:
                        values=np.array([m[key] for m in valid]);aggregate[key]=dict(min=float(values.min()),max=float(values.max()),max_abs=float(abs(values).max()),median=float(np.median(values)))
                rows.append(dict(load=result['load'],records=prefix['records'],hours=prefix['hours'],arm=name,public_queries=len(public),compared=len(valid),
                    unsupported_or_no_reference=len(public)-len(valid),metrics=aggregate,update_cpu_s=prefix['timing_cpu_s'][name],
                    observation_sha256=prefix['observation_sha256'],preserved_witness_digest_matches=prefix['preserved_witness_digest_matches'],
                    domain_query_status=[q['arms'][name]['status'] for q in prefix['queries'] if q['selection']!='public']))
    return dict(run=str(run),result_bindings=bindings,registration=identity(run/'registration.json'),rows=rows,storage=storage)


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('runs',nargs='+',type=Path);p.add_argument('--plot',type=Path)
    args=p.parse_args();runs=[reduce(r) for r in args.runs]
    # Followup repetitions must match original numerical arms exactly; timings are excluded.
    matched=True;comparisons=0
    if len(runs)==2:
        follow={(r['load'],r['records'],r['arm']):r for r in runs[1]['rows']}
        for r in runs[0]['rows']:
            f=follow[(r['load'],r['records'],r['arm'])]
            for key in ('metrics','observation_sha256','compared','domain_query_status'):
                if r[key]!=f[key]:matched=False
            comparisons+=1
    write(args.out,dict(schema='partitioned_coefficient_reduction_v1',scope='Finite unfitted common-query diagnostics, not population/coverage/estimation or uniform approximation claims',runs=runs,
        repeated_original_arms_exactly_match=matched,repeated_arm_prefixes=
        comparisons,source=identity(Path(__file__))))
    if args.plot:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        latest=runs[-1]['rows'];fig,axs=plt.subplots(1,2,figsize=(12,4.5))
        colors=dict(linear='tab:orange',quadratic='tab:blue',sparse_quadratic='tab:red',response_degree1='tab:olive',response_degree2='tab:purple',H7='black')
        for ax,load in zip(axs,['multiscale','embedded']):
            for name,color in colors.items():
                points=[r for r in latest if r['load']==load and r['arm']==name]
                ax.semilogy([r['hours'] for r in points],[r['metrics']['relative_joint_gradient_defect']['max'] for r in points],marker='o',color=color,label=name)
            ax.set_title(load);ax.set_xlabel('Simulated hours');ax.set_ylabel('Worst relative joint gradient defect');ax.grid(True,alpha=.3)
        axs[1].legend(fontsize=8);fig.suptitle('Fixed public probes; gradient fidelity, not fitted parameter error')
        fig.tight_layout();fig.savefig(args.plot,dpi=150);plt.close(fig)

if __name__=='__main__':main()
