"""Compact immutable evidence extraction; no refitting or selection changes."""
import argparse
import json
from pathlib import Path
import numpy as np
from experiments.foster_campaign_001.backend import identity
from experiments.hysteresis_sensitivity_basis_001.run import verify
from experiments.h7_history_quality_001.history import write,verify_sources


def summarize(directory):
    bindings={};manifest=json.loads((directory/'summary.json').read_text())
    reg=json.loads((directory/'registration.json').read_text());verify_sources(reg['source'])
    bindings[str(directory/'summary.json')]=identity(directory/'summary.json')
    bindings[str(directory/'registration.json')]=identity(directory/'registration.json')
    result=dict(status=manifest['status'],scope=manifest['scope'],source=reg['source'],protocol=reg['protocol'],
                inputs=reg['inputs'],raw_bindings=bindings,cases=[])
    for entry in manifest['cases']:
        path=directory/entry['file'];verify(path,entry['identity'],bindings)
        d=json.loads(path.read_text());arms={}
        for name,fit in d['fits']['arms'].items():
            q=d['fits']['QR_readouts'][name].copy()
            if q['fit_comparison']['status']=='local_converged_diagnostic':
                reference=d['fits']['QR_readouts']['direct']['physical']
                q['physical_difference_from_direct_fit']={k:(np.asarray(v)-np.asarray(reference[k])).tolist() for k,v in q['physical'].items()}
                q['direct_objective_excess_at_candidate_fit']=fit['same_anchor']['direct_cost']-d['fits']['arms']['direct']['same_anchor']['direct_cost']
            detail=q.pop('partition_diagnostics',None)
            if detail:
                q['partition_diagnostics']={k:v for k,v in detail.items() if k!='variants'}
                q['partition_diagnostics']['variants']={}
                for variant,v in detail['variants'].items():
                    q['partition_diagnostics']['variants'][variant]={k:v[k] for k in [
                        'eta','epsilon','sufficient_test','relative_precision_eigenvalues','actual_relative_precision_defect',
                        'cost_difference','gradient_defect_dual_norm','Q_direct_transport','SOC_direct_transport']}
            arms[name]=dict(status=fit['status'],selected_start=fit.get('selected_start'),
                attempts=fit['attempts'],selected=fit.get('selected'),
                legacy_same_anchor=fit.get('same_anchor'),legacy_transport=fit.get('compressed_transport'),QR=q)
        result['cases'].append(dict(label=path.stem,records=d['records'],load=d['load'],
            observation_sha256=d['observation_sha256'],input_bindings=d['input_bindings'],
            prior_mean=d['prior_mean'],prior_root=d['prior_root'],center=d['center'],config=d['config'],
            control_parity=d['control_parity'],arms=arms,storage=d['storage'],
            direct_observation_array_B=d['direct_observation_array_B'],host_cpu_s=d['fits']['host_cpu_s']))
    return result


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.out.exists():raise ValueError('preserve existing evidence')
    write(a.out,summarize(a.run))


if __name__=='__main__':main()
