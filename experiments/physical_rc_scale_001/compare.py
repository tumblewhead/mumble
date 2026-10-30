"""Matched physical RC scale comparison with frozen data and resource caps."""
import argparse
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time
import unittest
import numpy as np
from experiments.physical_rc_scale_001 import fitting
from experiments.physical_rc_scale_001.message import Message, unchanged, c
from experiments.physical_rc_scale_001.test_scale import Controls
from experiments.natural_hysteresis_001.message import Message as Parent
from experiments.natural_hysteresis_001.test_natural import Controls as NaturalControls
from experiments.backward_response_001 import algebra, rc_factor
from experiments.backward_response_001.test_algebra import Controls as AlgebraControls
from experiments.region_compression_001 import compare as base
from experiments.partition_coordinate_fit_001 import compare as previous
from experiments.partition_coordinate_fit_001.compare_repaired import RepairControls
from experiments.partition_coordinate_fit_001.stable_normalizer import log_mass

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def numeric_moments(row):
    return dict(count=row['count'],mean=np.array(row['mean']),covariance=np.array(row['covariance']))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default=str(HERE/'attempt001'))
    out=Path(parser.parse_args().output)
    out.mkdir(parents=True,exist_ok=False)
    plan=json.loads((HERE/'plan.json').read_text())
    oldpath=ROOT/plan['parent']
    old=json.loads(oldpath.read_text())
    backward=json.loads((ROOT/'experiments/backward_response_001/attempt001/result.json').read_text())
    factors=json.loads((ROOT/'experiments/backward_response_001/rc_factor001/result.json').read_text())
    verification=json.loads((ROOT/plan['diagnosis']).read_text())
    bindings=dict(verification['source_identities']);bindings.update(verification['artifacts'])
    for path,expected in bindings.items():
        c.old.require(base.identity(ROOT/path)==expected,'prior evidence changed '+path)
    for path in [*HERE.glob('*.py'),*HERE.glob('*.json'),HERE/'derivation.md',*HERE.glob('development_controls/*'),ROOT/plan['diagnosis']]:
        bindings[str(path.relative_to(ROOT))]=base.identity(path)
    base.write(out/'reservation.json',dict(plan=plan,identities=bindings,command=sys.argv,
        revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        branch=subprocess.check_output(['git','branch','--show-current'],text=True).strip(),
        python=sys.version,numpy=np.__version__,
        thread_environment={k:os.getenv(k) for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']}))
    groups=[previous.OriginalControls,previous.VoltageControls,previous.RCControls,RepairControls,NaturalControls,AlgebraControls,Controls]
    original=c.v.log_mass
    try:
        c.v.log_mass=log_mass
        with (out/'controls.txt').open('x') as stream:
            tested=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.TestSuite(
                [unittest.defaultTestLoader.loadTestsFromTestCase(group) for group in groups]))
    finally:
        c.v.log_mass=original
    base.write(out/'controls.json',dict(passed=tested.wasSuccessful(),tests_run=tested.testsRun,errors=len(tested.errors),failures=len(tested.failures)))
    c.old.require(tested.wasSuccessful(),'controls failed; no battery fits')
    work={key:0 for key in plan['work_caps']}
    checks=[]
    def check(name,condition):
        checks.append(dict(name=name,passed=bool(condition)))
        if not condition:raise AssertionError(name)
    def charge(key,n):
        c.old.require(work[key]+n<=plan['work_caps'][key],'work cap '+key)
        work[key]+=n
    def load(path):
        with np.load(ROOT/path,allow_pickle=False) as archive:return archive['projected'][:,:16].copy()
    started=time.process_time()
    cases,fit_records=[],[]
    for prefix in plan['prefixes']:
        ref=old['references'][str(prefix)]['inherited']
        train=np.concatenate([load(path) for path in ref['train']])
        held=[load(path) for path in ref['heldout']]
        parentpath=oldpath.parent/f'prefix{prefix}_natural_refit_message.json'
        payload=json.loads(parentpath.read_text())
        parent=Parent.restore(payload['posterior'])
        y,a,_=c.encode(train,parent.chart,parent.frame)
        labels=np.searchsorted(parent.edges[1:-1],c.old.to_unit(train)[:,5],side='right')
        fitted={}
        for region in range(2):
            take=labels==region
            yy,aa=y[take],a[take]
            for j in [9,10,11]:
                charge('conditional_fits',1)
                scale=aa[:,j-9]
                raw=np.column_stack([np.ones(len(yy)),yy[:,:j]])/scale[:,None]
                target=yy[:,j]/scale
                begin=time.process_time()
                try:
                    beta,logsd,diag=fitting.fit(raw,target,np.full(len(yy),-.25),np.full(len(yy),.25),
                        'bounded_likelihood',plan['optimizer'],lambda n:charge('fit_objective_rows',n))
                    fitted[region,j]=(beta,logsd)
                    diag['final_mean_NLD_in_F']=diag['final_mean_NLL']+float(np.log(scale).mean())
                except (c.old.Unavailable,np.linalg.LinAlgError,FloatingPointError) as error:
                    diag=dict(status='unavailable',reason=str(error))
                diag.update(prefix=prefix,component=region,coordinate=j,CPU_s=time.process_time()-begin,rows=len(yy))
                fit_records.append(diag)
                base.write(out/f'prefix{prefix}_component{region}_coordinate{j}_fit.json',base.plain(diag))
                print(prefix,region,j,diag['status'],diag.get('final_gradient_infinity'),flush=True)
        prior_case=next(row for row in old['cases'] if row['prefix']==prefix and row['arm']=='natural_refit')
        prior_parts=next(row for row in backward['cases'] if row['prefix']==prefix)['probes']
        prior_factors=next(row for row in factors['cases'] if row['prefix']==prefix)
        anchors=(np.array(prior_factors['anchors']['F_mean']),np.array(prior_factors['anchors']['r_mean']))
        for arm,selected in plan['arms'].items():
            begin=time.process_time()
            tag=f'prefix{prefix}_{arm}'
            case=dict(prefix=prefix,arm=arm,scaled_coordinates=selected)
            if any((r,j) not in fitted for r in range(2) for j in selected):
                case.update(status='unavailable_fit_failure')
                cases.append(case);base.write(out/(tag+'.json'),case);continue
            msg=Message.from_parent(parent,selected)
            for region in range(2):
                for j in selected:
                    beta,logsd=fitted[region,j]
                    c.coefficients(msg.regions[region],j)[:]=beta
                    msg.regions[region]['shape'][j]=logsd
            unchanged(parent,msg)
            newpayload=dict(payload,schema='physical_rc_scale_payload_v1',posterior=msg.export(),
                parent_message=str(parentpath.relative_to(ROOT)),parent_identity=base.identity(parentpath),
                scale_law='a(tau)*physical_v_scale at selected carried RC coordinates')
            base.write(out/(tag+'_message.json'),newpayload)
            logs=[]
            for population in held:
                charge('heldout_density_points',len(population))
                values=np.concatenate([msg.logpdf(population[i:i+512]) for i in range(0,len(population),512)])
                check(tag+' finite density',np.isfinite(values).all())
                logs.append(-float(values.mean()))
            if arm=='baseline':
                np.testing.assert_allclose(logs,prior_case['heldout_mean_negative_log_density_by_population'],atol=2e-12,rtol=0)
            batches=[]
            for batch_index,batch in enumerate(prior_case['batches']):
                charge('generated_rows',batch['draws'])
                charge('inverse_OCV_sample_iterations',batch['draws']*52)
                x,info=msg.draw(batch['draws'],batch['seed'])
                report=dict(seed=batch['seed'],draws=len(x),sampler=info,probes={},parts={})
                for probe in old['probe_definitions']:
                    name=probe['name'];steps=probe['steps']
                    charge('predictive_sample_steps',len(x)*len(steps))
                    voltage,valid=c.old.stationary_probe(x,steps)
                    charge('decomposition_sample_steps',len(x)*len(steps))
                    terms=algebra.terms(x,steps)
                    moments=algebra.moments(terms)
                    check(tag+name+' support',valid.all())
                    check(tag+name+' partition',np.max(abs(terms.sum(1)-voltage))<=2e-12)
                    check(tag+name+' covariance',abs(moments['covariance'].sum()-voltage.var())<=2e-15)
                    report['probes'][name]=base.scalar_stats(voltage)
                    report['parts'][name]=moments
                    if arm=='baseline':
                        np.testing.assert_allclose([voltage.mean(),voltage.std()],
                            [batch['probes'][name]['voltage_V']['mean'],batch['probes'][name]['voltage_V']['SD']],atol=2e-14,rtol=0)
                charge('factor_rows',len(x))
                parts,F,r=rc_factor.split(x,msg.frame,anchors)
                report['factor_moments']=algebra.moments(parts)
                report['F_moments']=algebra.moments(F)
                report['rF_moments']=algebra.moments(F*r)
                report['marginals']=dict(SOC=base.scalar_stats(x[:,11]),Q_Ah=base.scalar_stats(np.exp(x[:,5])),R0_ohm=base.scalar_stats(x[:,6]))
                batches.append(report)
            pooled_parts={name:algebra.pool([b['parts'][name] for b in batches]) for name in batches[0]['parts']}
            comparisons={}
            for name,stats in pooled_parts.items():
                comparisons[name]=dict(model_minus_construction=algebra.contrast(stats,numeric_moments(prior_parts[name]['construction'])),
                    model_minus_heldout=algebra.contrast(stats,numeric_moments(prior_parts[name]['reference'])),
                    SD_V=float(np.sqrt(stats['covariance'].sum())),mean_V=float(stats['mean'].sum()),
                    batch_SD_range_V=[min(b['probes'][name]['SD'] for b in batches),max(b['probes'][name]['SD'] for b in batches)],
                    batch_mean_range_V=[min(b['probes'][name]['mean'] for b in batches),max(b['probes'][name]['mean'] for b in batches)])
            factor=algebra.pool([b['factor_moments'] for b in batches])
            factor_delta=factor['covariance']-np.array(prior_factors['pooled']['train']['parts']['covariance'])
            case.update(status='offline_comparison_completed',heldout_mean_negative_log_density_by_population=logs,
                retained_numeric_B=msg.numeric_bytes,complete_target_SRAM_B=None,batches=batches,
                probes=comparisons,pooled_parts=pooled_parts,pooled_factor_moments=factor,
                F_moments=algebra.pool([b['F_moments'] for b in batches]),rF_moments=algebra.pool([b['rF_moments'] for b in batches]),
                amplitude_interaction_covariance_change_mV2=float(2*factor_delta[:3,6:9].sum()*1e6),
                slow_self_covariance_change_mV2=float(2*factor_delta[2,8]*1e6),CPU_s=time.process_time()-begin)
            restored=Message.restore(json.loads((out/(tag+'_message.json')).read_text())['posterior'])
            np.testing.assert_array_equal(msg.logpdf(held[0][:8]),restored.logpdf(held[0][:8]))
            base.write(out/(tag+'.json'),base.plain(case));cases.append(case)
            row=comparisons['reversal_10s']
            print(tag,'NLD',logs,'reversal SD mV',row['SD_V']*1000,'excess variance vs train mV2',row['model_minus_construction']['variance_difference_V2']*1e6,flush=True)
    base.write(out/'result.json',base.plain(dict(schema='physical_rc_scale_result_v1',status='matched_comparison_completed',
        cases=cases,fits=fit_records,checks=checks,work=work,CPU_s=time.process_time()-started,
        process_peak_RSS_B=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        references=old['references'],truth_reads=0,rolling_solver_changed=False,new_particle_inference=False,
        coverage_validated=False,aging_qualified=False,causal_update_qualified=False,deployment_qualified=False)))


if __name__=='__main__':main()
