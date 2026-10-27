#!/usr/bin/env python3
"""Close both controlled-arm comparisons using existing frozen references only."""
from decimal import Decimal, localcontext
import ctypes as C
import importlib.util
import json
import math
import os
from pathlib import Path
import struct

os.environ.setdefault('MPLCONFIGDIR','/tmp/mumble-structured-history-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import study
from study import HERE, ROOT, runner, shape


def cost_allowance(scale):
    with localcontext() as ctx:
        ctx.prec=100
        nu=Decimal(65536)*Decimal.from_float(2**-53)
        v=nu/(1-nu)*Decimal.from_float(scale)+Decimal(65536)*Decimal.from_float(2**-1074)
        return math.nextafter(float(v),math.inf)


def main():
    out=HERE/'attempt001';receipt=shape.load(out/'receipt.json');plan=shape.load(HERE/'plan.json')
    shape.require(receipt['status']=='completed','complete controlled execution required')
    for name,v in receipt['files'].items():shape.require(runner.identity(out/name)==v,'closed file '+name)
    inputs=study.paths(plan)
    for k,p in inputs.items():shape.require(runner.identity(p)=={t:plan['inputs'][k][t] for t in ('bytes','sha256')},'input '+k)
    shape.require(study.sources()==receipt['sources'],'sources unchanged')
    design=shape.load(inputs['nodes']);references=shape.load(inputs['evaluations'])
    baseline=shape.load(HERE.parent/'joint_shape_comparison_001/attempt001/analysis.json')
    shapes={};summaries={};all_records={}
    for arm in ('control','full'):
        for name in (arm+'.stdout',arm+'.bank.bin'):
            a,b=out/name,out/(name+'.copy')
            shape.require(runner.identity(a)==runner.identity(b) and a.stat().st_ino!=b.stat().st_ino,'copy '+name)
        records=json.loads((out/(arm+'.records.json')).read_text());all_records[arm]=records[:-1]
        rows=[];max_centering_gap=Decimal(0)
        for k,(r,ref,node) in enumerate(zip(records[:-1],references['rows'],design['nodes'],strict=True)):
            shape.require(r['kind']=='node' and r['index']==k and r['x']==node['x']==ref['x'],'node identity')
            row={'id':node['id'],'x':node['x']}
            if r['status'] or ref['status']!='available':row.update(status='unavailable',reason=f"candidate_{r['status']}_reference_{ref['status']}")
            else:row.update(status='available',represented_likelihood_cost=r['cost'],represented_cost_allowance=cost_allowance(r['absolute_scale']),
                            reference_likelihood_cost=ref['reference_likelihood_cost'],reference_cost_allowance=ref['reference_cost_allowance'])
            rows.append(row)
        analysis=shape.compare(design,rows)
        analysis.update(source_revision=receipt['source_revision'],arm=arm,
                        design_identity=runner.identity(inputs['nodes']),reference_identity=runner.identity(inputs['evaluations']),
                        scope='controlled saved-anchor schedule; no autonomous-inference or target claim',
                        additional_arithmetic_exclusions=['feature_libm_forward_error','factor_coefficient_construction'])
        runner.save(HERE/(arm+'_analysis.json'),analysis);shapes[arm]=analysis
        with localcontext() as ctx:
            ctx.prec=100;d=Decimal.from_float
            for r,a in zip(rows,analysis['per_node']):
                if r['status']!='available':continue
                e=(d(r['represented_likelihood_cost'])-d(rows[0]['represented_likelihood_cost']))-(
                    d(r['reference_likelihood_cost'])-d(rows[0]['reference_likelihood_cost']))
                gap=abs(e-d(a['centered_discrepancy_NLL']));max_centering_gap=max(max_centering_gap,gap)
                shape.require(gap<=d(a['computed_arithmetic_allowance_NLL']),'Decimal centering')
        per=analysis['per_node'];valid=[(i,a) for i,a in enumerate(per) if a['status']=='available']
        minimum=min(valid,key=lambda t:t[1]['centered_discrepancy_NLL']);maximum=max(valid,key=lambda t:t[1]['centered_discrepancy_NLL'])
        radii=[]
        for level,h in enumerate(design['radii']):
            v=[a['centered_discrepancy_NLL'] for n,a in zip(design['nodes'],per) if n['level'] in (-1,level) and a['status']=='available']
            radii.append({'radius':h,'oscillation_NLL':max(v)-min(v)})
        ep={}
        for name,index in [('SOC_pp',0),('h',4)]:
            field='SOC' if index==0 else 'h';scale=100 if index==0 else 1
            gaps=[scale*(r[field]-ref['reference_endpoint'][index]) for r,ref in zip(records[:-1],references['rows']) if not r['status'] and ref['status']=='available']
            ep[name]={'anchor_signed_difference':gaps[0],'max_absolute_difference':max(abs(v) for v in gaps)}
        summaries[arm]={'decision':analysis['decision'],'available_nodes':analysis['available_nodes'],
            'oscillation_NLL':analysis['centered_error_oscillation_NLL'],
            'oscillation_computed_arithmetic_interval_NLL':analysis['oscillation_computed_arithmetic_interval_NLL'],
            'reduction_from_original_percent':100*(1-analysis['centered_error_oscillation_NLL']/baseline['centered_error_oscillation_NLL']),
            'anchor_cost_difference_NLL':analysis['anchor_represented_minus_reference_NLL'],
            'minimum_witness':minimum[1],'maximum_witness':maximum[1],'by_radius':radii,
            'max_Decimal_centering_gap_NLL':str(max_centering_gap),'endpoint_differences_not_truth':ep}
        if analysis['complete_stencil']:
            summaries[arm]['slope_errors']=[{'radius':m['radius'],
                'norm':float(np.linalg.norm(m['gradient_whitened'])),
                'max_absolute':max(abs(v) for v in m['gradient_whitened'])}
                for m in analysis['discrepancy_second_differences']]
    # ABI-qualified structural comparison of the two saved banks. This is
    # read-only inspection; the old coefficient family is never imported.
    path=HERE.parent/'live_anchor_integration_001/qualification/independent_qualification.py'
    spec=importlib.util.spec_from_file_location('bank_layout',path);types=importlib.util.module_from_spec(spec);spec.loader.exec_module(types)
    banks={}
    for arm,magic in [('control',b'SHC0001\0'),('full',b'SHF0001\0')]:
        raw=(out/(arm+'.bank.bin')).read_bytes();shape.require(raw[:8]==magic and len(raw)==6864,'new bank schema')
        banks[arm]=types.Bank.from_buffer_copy(raw[32:32+6368])
    forced_equal={}
    for field in ('f','df','hb','dhb'):
        av=getattr(banks['control'].jet.model,field);bv=getattr(banks['full'].jet.model,field)
        forced_equal[field]=(struct.pack('<d',av)==struct.pack('<d',bv)) if field=='hb' else bytes(av)==bytes(bv)
    for field in ('ddf','ddhb'):forced_equal[field]=bytes(getattr(banks['control'].jet,field))==bytes(getattr(banks['full'].jet,field))
    delta=np.array([r['cost'] for r in all_records['full']])-np.array([r['cost'] for r in all_records['control']]);delta-=delta[0]
    summary={'schema':'mumble_structured_repair_review_v1','status':'passed_saved_result_verification','independent':False,
        'source_revision':receipt['source_revision'],'original_oscillation_NLL':baseline['centered_error_oscillation_NLL'],
        'arms':summaries,'full_minus_control_centered_oscillation_NLL':float(np.ptp(delta)),
        'forced_response_jets_bitwise_equal_between_arms':forced_equal,
        'causal_probe_allowed':shapes['full']['decision']=='keep_on_tested_points_only',
        'causal_probe_started':False,'new_reference_steps':0,'new_optimizer_calls':0,'truth_reads':0,
        'CPU_s':receipt['CPU_s'],'wall_s':receipt['wall_s'],
        'conservative_combined_peak_RSS_bytes':receipt['supervisor_peak_RSS_bytes']+max(c['peak_RSS_bytes'] for c in receipt['children']),
        'closed_execution_bytes_including_receipt':sum(p.stat().st_size for p in out.iterdir() if p.is_file()),
        'script':runner.identity(Path(__file__)),
        'interpretation':'The preselected implementation improves the frozen witness but must meet the original0.1NLL gate before a causal probe. Same forced-response jets isolate the attenuation ablation; residual rate/OCV approximation and f/hb transport are not separately apportioned by this comparison.',
        'limits':['Controlled old anchor schedule, not autonomous learning','No independent reviewer','Computed-cost scope excludes feature/libm/recurrence/coefficient-construction error','No coverage, convergence or M3 promotion']}
    report=HERE/'reporting001';report.mkdir()
    fig,axes=plt.subplots(2,1,figsize=(10,7),layout='constrained',gridspec_kw={'height_ratios':[2,1]})
    for name,a,color in [('Original',baseline,'#777777'),('Structured features',shapes['control'],'#bd7b22'),('Full candidate',shapes['full'],'#245f9a')]:
        axes[0].plot([r['centered_discrepancy_NLL'] for r in a['per_node']],linewidth=.6,label=name,color=color)
    axes[0].set_xlabel('Frozen node index');axes[0].set_ylabel('Centered discrepancy (NLL)');axes[0].legend();axes[0].grid(alpha=.2)
    names=['Original','Structured features','Full candidate'];values=[baseline['centered_error_oscillation_NLL'],summaries['control']['oscillation_NLL'],summaries['full']['oscillation_NLL']]
    axes[1].barh(names,values,color=['#777777','#bd7b22','#245f9a']);axes[1].set_xlabel('Finite-node error oscillation (NLL); gate = 0.1')
    for i,v in enumerate(values):axes[1].text(v+2,i,f'{v:.2f}',va='center')
    axes[1].set_xlim(0,max(values)*1.16);axes[1].axvline(.1,color='black',linewidth=1)
    fig.suptitle('Structured-history repair: both controlled arms, all 545 frozen points',fontweight='bold')
    fig.savefig(report/'comparison.png',dpi=160);fig.savefig(report/'comparison.svg');plt.close(fig)
    summary['figures']={n:runner.identity(report/n) for n in ('comparison.png','comparison.svg')}
    runner.save(HERE/'result_review.json',summary)
    print(json.dumps({k:summary[k] for k in ('status','causal_probe_allowed','arms','forced_response_jets_bitwise_equal_between_arms')}))


if __name__=='__main__':main()
