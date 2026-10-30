"""Recompute saved conditional densities and preserve all adaptation evidence."""
import json
from pathlib import Path
import numpy as np
from experiments.region_compression_001 import compare as base
from experiments.physical_rc_scale_001.message import Message as Physical,unchanged as physical_unchanged,c,log_mass
from experiments.physical_rc_scale_001.combined_message import Message as Combined,unchanged as combined_unchanged
from experiments.physical_rc_scale_001.compensation_message import Message as Compensation,unchanged as compensation_unchanged
from experiments.natural_hysteresis_001.message import Message as Original

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def main():
    checks=[];bindings={};runs={};audit=[]
    def check(name,condition):
        checks.append(dict(name=name,passed=bool(condition)))
        if not condition:raise AssertionError(name)
    for directory in ['attempt001','combined001','compensation001']:
        reservation=json.loads((HERE/directory/'reservation.json').read_text())
        bindings.update(reservation['identities'])
        result=json.loads((HERE/directory/'result.json').read_text());runs[directory]=result
        check(directory+' saved checks',all(row['passed'] for row in result['checks']))
        for key,cap in reservation['plan']['work_caps'].items():check(directory+' work '+key,result['work'][key]<=cap)
        check(directory+' controls',json.loads((HERE/directory/'controls.json').read_text())['passed'])
    for path,identity in bindings.items():check('source preserved '+path,base.identity(ROOT/path)==identity)
    original=json.loads((ROOT/'experiments/natural_hysteresis_001/attempt001/result.json').read_text())
    train={}
    for prefix in [8,32]:
        train[prefix]=np.concatenate([np.load(ROOT/path,allow_pickle=False)['projected'][:,:16] for path in original['references'][str(prefix)]['inherited']['train']])
    for directory,result in runs.items():
        cls={'attempt001':Physical,'combined001':Combined,'compensation001':Compensation}[directory]
        for case in result['cases']:
            tag=f"prefix{case['prefix']}_{case['arm']}"
            payload=json.loads((HERE/directory/(tag+'_message.json')).read_text())
            msg=cls.restore(payload['posterior'])
            parent_payload=json.loads((ROOT/payload['parent_message']).read_text())
            if directory=='compensation001':
                parent=Combined.restore(parent_payload['posterior']);compensation_unchanged(parent,msg)
            else:
                parent=Original.restore(parent_payload['posterior'])
                (physical_unchanged if directory=='attempt001' else combined_unchanged)(parent,msg)
            for key in ['source_id','owns_initial_prior','observation_interval','transition_interval','physical_support_low','physical_support_high']:
                check(tag+' ownership '+key,payload[key]==parent_payload[key])
            check(tag+' payload bytes',msg.numeric_bytes==case['retained_numeric_B'])
            check(tag+' all horizons',len(case['probes'])==13)
        # Unique fits: the physical slow-only arm reuses all-carried fits.
        arm={'attempt001':'all_carried','combined001':'combined_information','compensation001':'physical_compensation'}[directory]
        for fit in result['fits']:
            prefix,j,region=fit['prefix'],fit['coordinate'],fit['component']
            msg=cls.restore(json.loads((HERE/directory/f'prefix{prefix}_{arm}_message.json').read_text())['posterior'])
            x=train[prefix];y,a,_=c.encode(x,msg.chart,msg.frame)
            labels=np.searchsorted([.5],c.old.to_unit(x)[:,5],side='right');take=labels==region
            yy,aa=y[take],a[take];reg=msg.regions[region]
            beta=c.coefficients(reg,j);mu=beta[0]+yy[:,:j]@beta[1:]
            if 'compensation' in reg and j==11:mu+=(yy[:,9:11]*(aa[:,2,None]/aa[:,:2]-1))@reg['compensation']
            sd=np.full(len(yy),np.exp(reg['shape'][j]))
            if 'mix' in reg:sd/=np.sqrt(1+reg['mix'][j-9]*(((-np.expm1(-1))/aa[:,j-9])**2-1))
            else:sd*=aa[:,j-9]
            left,right=(-.25*aa[:,j-9]-mu)/sd,(.25*aa[:,j-9]-mu)/sd
            loss=float(np.mean(.5*((yy[:,j]-mu)/sd)**2+np.log(sd)+.5*c.old.LOG2PI+log_mass(left,right)))
            tag=f'{directory} prefix{prefix} component{region} coordinate{j}'
            check(tag+' independently reconstructed conditional density',abs(loss-fit['final_mean_NLD_in_F'])<2e-11)
            check(tag+' numerical gradient',fit['final_gradient_infinity']<=1e-7)
            check(tag+' objective decreased',fit['final_mean_NLL']<=fit['initial_mean_NLL']+1e-12)
            audit.append(dict(run=directory,prefix=prefix,component=region,coordinate=j,
                reconstructed_mean_NLD_in_F=loss,saved_objective_difference=loss-fit['final_mean_NLD_in_F']))
    summary=dict(schema='physical_rc_scale_summary_v1',status='partial_repair_combined_information_candidate_not_promoted',
        controls_passed=66,primary_case_checks=sum(len(r['checks']) for r in runs.values()),
        closeout_checks=len(checks),unique_fits=28,all_fits_meet_numerical_gradient_tolerance=True,
        maximum_gradient_residual=max(f['final_gradient_infinity'] for r in runs.values() for f in r['fits']),
        candidate='combined_information',
        decision='Reject compulsory physical scaling as general replacement. Retain additive-information scale as a partial research candidate. Do not promote added mean compensation: no consistent predictive benefit. Rolling solver unchanged.',
        cases=[],all_probe_comparison={},
        storage_B=dict(original_numeric=2496,physical_scale_numeric=2496,combined_information_numeric=2544,
            mean_compensation_numeric=2576,complete_target_SRAM=None,
            maximum_desktop_process_peak_RSS=max(r['process_peak_RSS_B'] for r in runs.values())),
        CPU_s={key:dict(comparison=r['CPU_s'],fitting=sum(f['CPU_s'] for f in r['fits'])) for key,r in runs.items()},
        limitations=['Later candidates are exploratory adaptations using previously evaluated heldout populations, not fresh confirmation',
            'All13probes matter: combined candidate worsens some shorter-horizon variances',
            'Substantial32record discrepancy persists; predicted uncertainty is not coverage',
            'Only0.229/0.914seconds of source history; no aging, causal update, long-term or M23 qualification'],
        next_step='Trace and repair the generated conditioning-variable distribution and its carried-state coupling before another scale-only change; qualify against all response horizons and new independent sources before promotion.')
    for prefix in [8,32]:
        baseline=next(case for case in runs['attempt001']['cases'] if case['prefix']==prefix and case['arm']=='baseline')
        before=baseline['probes']['reversal_10s']['model_minus_construction']['variance_difference_V2']
        summary['all_probe_comparison'][str(prefix)]={}
        for directory,result in runs.items():
            for case in result['cases']:
                if case['prefix']!=prefix:continue
                rev=case['probes']['reversal_10s']
                after=rev['model_minus_construction']['variance_difference_V2']
                scores=case['heldout_mean_negative_log_density_by_population']
                summary['cases'].append(dict(prefix=prefix,arm=case['arm'],run=directory,
                    retained_numeric_B=case['retained_numeric_B'],reversal_SD_mV=rev['SD_V']*1000,
                    reversal_SD_batch_range_mV=[v*1000 for v in rev['batch_SD_range_V']],
                    reversal_mean_vs_heldout_mV=rev['model_minus_heldout']['mean_difference_V']*1000,
                    reversal_variance_vs_construction_mV2=after*1e6,
                    absolute_variance_discrepancy_reduction_fraction=1-abs(after)/abs(before),
                    amplitude_interaction_covariance_change_mV2=case['amplitude_interaction_covariance_change_mV2'],
                    heldout_mean_NLD=scores,
                    heldout_NLD_improvement_vs_baseline_by_population=(np.array(baseline['heldout_mean_negative_log_density_by_population'])-scores).tolist()))
                summary['all_probe_comparison'][str(prefix)][case['arm']]={name:dict(
                    SD_mV=row['SD_V']*1000,mean_vs_heldout_mV=row['model_minus_heldout']['mean_difference_V']*1000,
                    variance_vs_construction_mV2=row['model_minus_construction']['variance_difference_V2']*1e6,
                    variance_vs_heldout_mV2=row['model_minus_heldout']['variance_difference_V2']*1e6,
                    batch_SD_range_mV=[v*1000 for v in row['batch_SD_range_V']]) for name,row in case['probes'].items()}
    base.write(HERE/'fit_density_audit.json',dict(status='passed',fits=audit,
        scope='Independent reconstruction from serialized means/scales/support without optimizer standardization; shared stable normalizer, not an independent implementation'))
    base.write(HERE/'summary.json',summary)
    files=[p for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='verification.json']
    base.write(HERE/'verification.json',dict(status='passed',checks=checks,
        artifacts={str(p.relative_to(ROOT)):base.identity(p) for p in sorted(files)},
        scope='Controls, source preservation, work caps, ownership, coefficient invariance and28saved conditional objectives; no full prediction/coverage qualification'))
    print(json.dumps(dict(checks=len(checks),artifacts=len(files),controls=66)))


if __name__=='__main__':main()
