#!/usr/bin/env python3
"""Read-only result verification and attribution; no model calls."""
from decimal import Decimal, localcontext
import copy
import json
import math
from pathlib import Path

from diagnose import HERE, ROOT, runner, shape, sources, np


def main():
    out=HERE/'attempt002';receipt=shape.load(out/'receipt.json')
    shape.require(receipt['status']=='completed','complete diagnostic required')
    for n,v in receipt['files'].items():shape.require(runner.identity(out/n)==v,'closed identity '+n)
    plan=shape.load(HERE/'localization_plan.json')
    for v in plan['inputs'].values():
        shape.require(runner.identity(ROOT/v['path'])=={k:v[k] for k in ('bytes','sha256')},'input identity')
    shape.require(sources()==receipt['sources'],'source identity')
    a,b=out/'localization.stdout',out/'localization.stdout.copy'
    shape.require(runner.identity(a)==runner.identity(b) and a.stat().st_ino!=b.stat().st_ino,'capture preservation')
    records=shape.load(out/'records.json');design=shape.load(ROOT/plan['inputs']['nodes']['path'])
    ev=shape.load(ROOT/plan['inputs']['evaluations']['path'])
    basis=np.array(design['basis_original_x_units'])
    win=[r for r in records if r['kind']=='window']
    saved=next(r for r in records if r['kind']=='saved_anchor')
    direct=[r for r in records if r['kind']=='direct_row_sum']
    original_cost=math.fsum(r['original_recurrence']['cost'] for r in win)
    row_cost=math.fsum(r['rolling_rows']['cost'] for r in win)
    row_gradient=sum(np.array(r['rolling_rows']['gradient']) for r in win)
    ref_gradient=sum(np.array(r['original_recurrence']['gradient']) for r in win)
    gradient_gap=basis.T@(row_gradient-np.array(saved['gradient']))
    discrepancy=basis.T@(row_gradient-ref_gradient)
    norm=float(np.linalg.norm(discrepancy))
    chronology=[];blocks=[]
    for r in win:
        g=basis.T@(np.array(r['rolling_rows']['gradient'])-r['original_recurrence']['gradient'])
        chronology.append({'begin':r['begin'],'end':r['end'],
                           'nominal_minutes':[r['begin']/2100,r['end']/2100],
                           'cost_discrepancy_NLL':r['rolling_rows']['cost']-r['original_recurrence']['cost'],
                           'gradient_discrepancy_whitened':g.tolist(),
                           'gradient_discrepancy_norm':float(np.linalg.norm(g)),
                           'signed_projection_on_total_percent':100*float(g@discrepancy)/(norm*norm)})
    for r in records:
        if r['kind']!='block_decomposition':continue
        boundary=basis.T@(np.array(r['rolling_rows']['gradient'])-r['exact_origin_rows']['gradient'])
        truncation=basis.T@(np.array(r['exact_origin_rows']['gradient'])-r['original_recurrence']['gradient'])
        blocks.append({'begin':r['begin'],'end':r['end'],
                       'boundary_cost_difference_NLL':r['rolling_rows']['cost']-r['exact_origin_rows']['cost'],
                       'residual_approximation_cost_difference_NLL':r['exact_origin_rows']['cost']-r['original_recurrence']['cost'],
                       'boundary_gradient_norm':float(np.linalg.norm(boundary)),
                       'residual_approximation_gradient_norm':float(np.linalg.norm(truncation)),
                       'boundary_gradient_whitened':boundary.tolist(),
                       'residual_approximation_gradient_whitened':truncation.tolist()})
    oracle=[r for r in records if r['kind']=='oracle_node'];shape.require(len(oracle)==545,'oracle node count')
    rows=[]
    for old,new in zip(ev['rows'],oracle):
        shape.require(new['index']==len(rows),'oracle order')
        r={k:old[k] for k in ('id','x')}
        if new['status'] or old['status']!='available':
            r.update(status='unavailable',reason='oracle_status_'+str(new['status'])+'_reference_'+old['status'])
        else:
            # Exact Decimal evaluation of the registered16384-operation gamma
            # formula, then one outward binary64 rounding. Same computed-cost
            # scope as the inherited evaluator; no construction/recurrence proof.
            with localcontext() as context:
                context.prec=100
                nu=Decimal(16384)*Decimal.from_float(2**-53)
                bound=nu/(1-nu)*Decimal.from_float(new['cost_absolute_scale'])+Decimal(16384)*Decimal.from_float(2**-1074)
                allowance=math.nextafter(float(bound),math.inf)
            r.update(status='available',represented_likelihood_cost=new['cost'],
                     represented_cost_allowance=allowance,
                     reference_likelihood_cost=old['reference_likelihood_cost'],
                     reference_cost_allowance=old['reference_cost_allowance'])
        rows.append(r)
    analysis=shape.compare(design,rows)
    analysis.update(scope='retrospective exact-final-origin oracle only; not a causal repair or candidate',
                    design_identity=runner.identity(ROOT/plan['inputs']['nodes']['path']),
                    original_evaluations_identity=runner.identity(ROOT/plan['inputs']['evaluations']['path']))
    runner.save(HERE/'oracle_analysis.json',analysis)
    direct_gaps=[{'index':r['index'],'id':design['nodes'][r['index']]['id'],
                 'direct_minus_saved_QR_NLL':r['cost']-ev['rows'][r['index']]['represented_likelihood_cost']}
                for r in direct]
    summary={'schema':'mumble_history_shape_localization_review_v1','status':'passed','independent':False,
             'source_revision':receipt['source_revision'],'script':runner.identity(Path(__file__)),
             'original_reference_anchor_cost_NLL':original_cost,
             'original_reference_anchor_saved_gap_NLL':original_cost-ev['rows'][0]['reference_likelihood_cost'],
             'direct_row_anchor_cost_NLL':row_cost,'saved_QR_anchor_cost_NLL':saved['cost'],
             'max_direct_sum_vs_saved_QR_gap_NLL':max(abs(r['direct_minus_saved_QR_NLL']) for r in direct_gaps),
             'direct_sum_vs_saved_QR_centered_gap_oscillation_NLL':max(r['direct_minus_saved_QR_NLL'] for r in direct_gaps)-min(r['direct_minus_saved_QR_NLL'] for r in direct_gaps),
             'direct_sum_vs_saved_gradient_whitened_norm':float(np.linalg.norm(gradient_gap)),
             'gradient_error_whitened':discrepancy.tolist(),'gradient_error_whitened_norm':norm,
             'direct_checks':direct_gaps,'chronology':chronology,'block_decomposition':blocks,
             'oracle_available_nodes':analysis['available_nodes'],'oracle_decision':analysis['decision'],
             'oracle_oscillation_NLL':analysis['centered_error_oscillation_NLL'],
             'oracle_oscillation_computed_arithmetic_interval_NLL':analysis['oscillation_computed_arithmetic_interval_NLL'],
             'oracle_anchor_gap_NLL':analysis['anchor_represented_minus_reference_NLL'],
             'work':receipt['work'],'CPU_s':receipt['CPU_s'],'wall_s':receipt['wall_s'],
             'new_model_calls_during_reporting':0,'estimator_modified':False,'repair_implemented':False,
             'interpretation':'Strong evidence of accumulated approximation error, not QR/translation roundoff. Existing37-feature form is locally adequate when built at final center. Sparse block controls show residual truncation and transported-boundary error both present. A retrospective rebuilt factor is not a deployable causal repair.',
             'limits':['No independent reviewer','Sparse8-block mechanism decomposition does not apportion the whole history exactly','Chronological gradient norms are not additive; signed projections are','No physical truth, coverage, convergence or M3 claim','Computed arithmetic allowances exclude factor construction and recurrence/libm forward error'],
             'files_verified':len(receipt['files'])}
    runner.save(HERE/'result_review.json',summary)
    print(json.dumps({k:summary[k] for k in ('status','max_direct_sum_vs_saved_QR_gap_NLL',
                     'direct_sum_vs_saved_gradient_whitened_norm','oracle_oscillation_NLL',
                     'oracle_oscillation_computed_arithmetic_interval_NLL')}))


if __name__=='__main__':main()
