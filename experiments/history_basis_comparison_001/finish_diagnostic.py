"""Recover completed attribution after list/abs reporting error; no basis rerun."""
import ctypes as C
import json
from pathlib import Path
import sys
import numpy as np
from compare import ROOT,HERE,Harness,Result,ptr,identity,save

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=False)
old=HERE/'diagnostic001';source=HERE/'comparison002'
reservation=json.loads((old/'reservation.json').read_text())
# Validate the immutable original source snapshots, including the failed script.
for name,expected in reservation['sources'].items():
    if identity(old/'sources'/name)!=expected:raise RuntimeError('original snapshot changed')
receipt=json.loads((old/'receipt.json').read_text())
if len(receipt['arms'])!=24:raise RuntimeError('incomplete attribution')
steps_before=receipt['aggregate_model_steps_upper'];additional=33*4096
if steps_before+additional>10000000:raise RuntimeError('aggregate work cap')
save(out/'reservation.json',dict(status='before_composition_recovery',
    reason='All 24 component attributions completed; list passed to abs caused reporting failure after exact composition calls. Fix report and repeat only 33 exact two-block controls.',
    script=identity(Path(__file__)),prior_receipt=identity(old/'receipt.json'),
    source_reservation=identity(old/'reservation.json'),prior_steps=steps_before,additional_steps=additional,
    unchanged_candidate_and_gate=True))
(out/'finish_diagnostic_source.py').write_bytes(Path(__file__).read_bytes())
inputs=json.loads((source/'frozen_inputs.json').read_text());h=Harness(source/'provider.so');rows=[]
for raw in inputs['raw_cycle']:
    row=np.zeros(3)
    if h.lib.hp_decode(*raw,ptr(row)):raise RuntimeError('decode')
    rows.append(row)
rows=np.tile(rows,(64,1));reference=json.loads((source/'reference_4096.json').read_text())
gaps=[];state_gaps=[]
for i,point in enumerate(inputs['queries'][:33]):
    x=np.array(point);first=Result();second=Result()
    if h.lib.hp_exact_query(ptr(rows[:17]),17,ptr(x),C.byref(first)):raise RuntimeError('first block')
    x[11]=first.endpoint[0];x[12:15]=first.endpoint[1:4];x[15]=first.endpoint[4]
    if h.lib.hp_exact_query(ptr(rows[17:]),4079,ptr(x),C.byref(second)):raise RuntimeError('second block')
    gaps.append(first.likelihood+second.likelihood-reference['costs'][i])
    state_gaps.append(np.array(second.endpoint)-reference['endpoints'][i])
receipt['exact_composition']=dict(queries=33,partition=[17,4079],
    max_cost_gap_NLL=float(np.max(np.abs(gaps))),max_endpoint_gap_by_coordinate=np.max(np.abs(state_gaps),axis=0).tolist(),
    passed=bool(np.allclose(np.array(reference['costs'][:33])+gaps,reference['costs'][:33],rtol=2e-10,atol=2e-8)
                and np.allclose(state_gaps,0,rtol=2e-10,atol=2e-8)),
    scope='Exact physical two-block control; not finite-basis closure.')
receipt['preserved_reporting_error']=receipt.pop('error');receipt.pop('wall_s')
receipt.update(status='attribution_and_composition_completed',model_steps_upper=additional,
    aggregate_model_steps_upper=steps_before+additional,
    component_order=['RC1','RC2','RC3','forced_hysteresis','free_hysteresis','OCV_minus_observed','ohmic'],
    preserved_attempt='diagnostic001/receipt.json',gate_status='Original numerical mismatch and all representation failures remain.')
save(out/'receipt.json',receipt)
print(json.dumps({k:v for k,v in receipt.items() if k not in ['arms','preserved_reporting_error']},indent=2))
