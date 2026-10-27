#!/usr/bin/env python3
"""Verify and summarize closed comparison outputs; no model/inference calls."""
from decimal import Decimal, localcontext
import json
import math
import os
from pathlib import Path
import struct

os.environ.setdefault('MPLCONFIGDIR','/tmp/mumble-joint-shape-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import run
from run import HERE, ROOT, runner, shape


def main():
    out=HERE/'attempt001'
    receipt=shape.load(out/'receipt.json')
    shape.require(receipt['status']=='completed','execution incomplete; preserve unresolved receipt')
    for name,expected in receipt['closed_files'].items():
        shape.require(runner.identity(out/name)==expected,'closed hash '+name)
    plan=shape.load(HERE/'plan.json')
    for spec in plan['inputs'].values():
        shape.require(runner.identity(ROOT/spec['path'])=={k:spec[k] for k in ('bytes','sha256')},'input identity')
    shape.require(run.sources()==receipt['sources'],'source identity')
    for name in ('metric','comparison'):
        a,b=out/(name+'.stdout'),out/(name+'.stdout.copy')
        shape.require(runner.identity(a)==runner.identity(b) and a.stat().st_ino!=b.stat().st_ino,'distinct capture copy')
    design=shape.load(out/'nodes.json');ev=shape.load(out/'evaluations.json');analysis=shape.load(out/'analysis.json')
    for key,value in shape.compare(design,ev['rows']).items():
        shape.require(analysis[key]==value,'reproduced analysis '+key)
    nodes=list(struct.iter_unpack('<16d',(out/'nodes.bin').read_bytes()))
    shape.require(len(nodes)==545 and all(list(x)==n['x'] for x,n in zip(nodes,design['nodes'])),'frozen binary points')
    for name,expected in shape.load(out/'nodes_frozen.json')['files'].items():
        shape.require(runner.identity(out/name)==expected,'frozen identity '+name)
    raw=(ROOT/plan['inputs']['diagnostic_bank']['path']).read_bytes()
    derived=(out/'adapter.bank.bin').read_bytes()
    shape.require(raw[:8]==b'FPSHC01\0' and derived[:8]==b'FPSH001\0' and raw[8:]==derived[8:], 'adapter bytes')
    available=[(n,r,a) for n,r,a in zip(design['nodes'],ev['rows'],analysis['per_node']) if r['status']=='available']
    r0=ev['rows'][0];decimal_errors=[];max_centering_gap=Decimal(0)
    with localcontext() as context:
        context.prec=100
        d=Decimal.from_float
        for n,r,a in available:
            e=(d(r['represented_likelihood_cost'])-d(r0['represented_likelihood_cost']))-(
                d(r['reference_likelihood_cost'])-d(r0['reference_likelihood_cost']))
            gap=abs(e-d(a['centered_discrepancy_NLL']));max_centering_gap=max(max_centering_gap,gap)
            scale=sum(abs(d(v)) for v in (r['represented_likelihood_cost'],r0['represented_likelihood_cost'],
                                          r['reference_likelihood_cost'],r0['reference_likelihood_cost']))
            shape.require(gap<=d(6*shape.U/(1-6*shape.U))*scale,'independent Decimal centering check')
            decimal_errors.append(e)
        decimal_oscillation=max(decimal_errors)-min(decimal_errors)
    witness_min=min(available,key=lambda t:t[2]['centered_discrepancy_NLL'])
    witness_max=max(available,key=lambda t:t[2]['centered_discrepancy_NLL'])
    def witness(t):
        n,r,a=t
        return {**a,'level':n['level'],'direction':n['direction'],'sign':n['sign'],
                'Q_relative_anchor_percent':n['Q_relative_anchor_percent'],
                'current_SOC_relative_anchor_pp':n['current_SOC_relative_anchor_pp']}
    endpoint={}
    for j,(name,scale) in enumerate((('SOC_pp',100),('v1_V',1),('v2_V',1),('v3_V',1),('h',1))):
        t=max(available,key=lambda t:abs(t[1]['represented_endpoint'][j]-t[1]['reference_endpoint'][j]))
        endpoint[name]={'max_absolute_difference':scale*abs(t[1]['represented_endpoint'][j]-t[1]['reference_endpoint'][j]),
                        'node':t[0]['id'],'anchor_signed_difference':scale*(r0['represented_endpoint'][j]-r0['reference_endpoint'][j])}
    by_radius=[]
    for level,h in enumerate(design['radii']):
        subset=[t for t in available if t[0]['level'] in (-1,level)]
        errors=[t[2]['centered_discrepancy_NLL'] for t in subset]
        by_radius.append({'radius':h,'available_nodes_including_anchor':len(subset),
                          'centered_error_oscillation_NLL':max(errors)-min(errors),
                          'max_abs_discrepancy_NLL':max(abs(x) for x in errors)})
    peak=receipt['supervisor_peak_RSS_bytes']+max(c['peak_RSS_bytes'] for c in receipt['children'])
    output_bytes=sum(p.stat().st_size for p in out.iterdir() if p.is_file())
    shape.require(peak<=plan['finite_caps']['host_RSS_bytes'] and output_bytes<=plan['finite_caps']['closed_output_bytes'], 'closed caps')
    report=HERE/'reporting001';report.mkdir()
    fig=plt.figure(figsize=(11,8),layout='constrained');grid=fig.add_gridspec(2,2,height_ratios=[1,1.3])
    top=fig.add_subplot(grid[0,:])
    for level,color in ((0,'#2564a3'),(1,'#c06b21')):
        points=[(i,t) for i,t in enumerate(zip(design['nodes'],analysis['per_node']))
                if t[0]['level']==level and t[1]['status']=='available']
        top.scatter([i for i,t in points],[t[1]['centered_discrepancy_NLL'] for i,t in points],
                    s=7,color=color,label=f"Radius {design['radii'][level]:g}")
    top.axhline(0,color='#777777',linewidth=.7);top.grid(alpha=.2);top.legend()
    top.set_xlabel('Frozen node index');top.set_ylabel('Centered shape discrepancy (NLL)')
    top.set_title(f"Joint history comparison: {analysis['available_nodes']}/545 points available",loc='left')
    if analysis['complete_stencil']:
        matrices=[np.array(m['symmetric_second_difference_matrix_whitened'])
                  for m in analysis['discrepancy_second_differences']]
        limit=max(float(np.max(np.abs(m))) for m in matrices) or 1
        for level,m in enumerate(matrices):
            ax=fig.add_subplot(grid[1,level]);im=ax.imshow(m,cmap='RdBu_r',vmin=-limit,vmax=limit)
            ax.set_title(f"Second-difference error, radius {design['radii'][level]:g}")
            ax.set_xlabel('Whitened coordinate');ax.set_ylabel('Whitened coordinate')
            fig.colorbar(im,ax=ax,label='NLL / squared whitened displacement',shrink=.8)
    fig.suptitle('Numerically reconstructed bank; represented minus original recurrence. No truth or coverage claim.',fontsize=10)
    fig.savefig(report/'joint_shape.png',dpi=160);fig.savefig(report/'joint_shape.svg');plt.close(fig)
    summary={'schema':'mumble_joint_shape_saved_review_v1','status':'passed','independent':False,
             'method':'Verify closed hashes/copies and frozen points, recompute analysis, independently check centering using100-digit Decimal arithmetic on saved cost operands.',
             'source_revision':receipt['source_revision'],'script':runner.identity(Path(__file__)),
             'decision':analysis['decision'],'available_nodes':analysis['available_nodes'],
             'radii':design['radii'],'support_only_halvings':design['support_only_halvings'],
             'whitening_residual_inf':design['whitening_residual_inf'],
             'budget_NLL':analysis['budget_NLL'],
             'centered_error_oscillation_NLL':analysis['centered_error_oscillation_NLL'],
             'oscillation_computed_arithmetic_interval_NLL':analysis['oscillation_computed_arithmetic_interval_NLL'],
             'Decimal_saved_operand_oscillation_NLL':str(decimal_oscillation),
             'max_Decimal_centering_gap_NLL':str(max_centering_gap),
             'anchor_represented_minus_reference_NLL':analysis['anchor_represented_minus_reference_NLL'],
             'anchor_costs':{k:r0[k] for k in ('represented_likelihood_cost','reference_likelihood_cost')},
             'minimum_witness':witness(witness_min),'maximum_witness':witness(witness_max),
             'by_radius':by_radius,'endpoint_discrepancies_not_truth_errors':endpoint,
             'CPU_s':receipt['CPU_s'],'wall_s':receipt['wall_s'],
             'conservative_combined_peak_RSS_bytes':peak,'closed_execution_bytes_including_receipt':output_bytes,
             'work':receipt['work'],'new_model_calls_during_reporting':0,
             'semantics':run.SEMANTICS,'limitations':analysis['no_claims']+analysis['arithmetic_excludes'],
             'figures':{n:runner.identity(report/n) for n in ('joint_shape.png','joint_shape.svg')}}
    runner.save(HERE/'result_review.json',summary)
    print(json.dumps({k:summary[k] for k in ('status','decision','centered_error_oscillation_NLL','by_radius','endpoint_discrepancies_not_truth_errors')}))


if __name__=='__main__':main()
