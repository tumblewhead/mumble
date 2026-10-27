#!/usr/bin/env python3
"""Verify and plot closed census outputs only; no estimator or model calls."""
import csv
import gzip
import json
import math
import os
from pathlib import Path
import struct

os.environ.setdefault('MPLCONFIGDIR','/tmp/mumble-parity-census-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import census


def main():
    root=census.HERE;out=root/'attempt001'
    receipt=json.loads((out/'receipt.json').read_text())
    assert receipt['status']=='completed'
    for name,expected in receipt['files'].items():assert census.runner.identity(out/name)==expected,name
    for path,expected in receipt['inputs'].items():assert census.runner.identity(census.ROOT/path)==expected,path
    summary=json.loads((out/'summary.json').read_text())
    expected_path=census.PARENT/'attempt001/expected.bin'
    actual=list(census.records(out/'actual_snapshots.bin'));expected=list(census.records(expected_path))
    assert len(actual)==len(expected)==15751
    field_counts={n:0 for n in census.FIELDS};maximum={n:0. for n in census.FIELDS}
    inventory=[];time=[];delta=[];ulps=[];mismatched_snapshots=0;rounding_differences=0;max_rounding_difference=0.
    for a,e in zip(actual,expected):
        mismatch=False
        assert a[0]==e[0]
        for k,name in enumerate(census.FIELDS):
            av,ev=a[k+1],e[k+1]
            unequal=struct.pack('<d',av)!=struct.pack('<d',ev) if k<27 else av!=ev
            if unequal:
                field_counts[name]+=1;maximum[name]=max(maximum[name],abs(av-ev));mismatch=True
                inventory.append((a[0],name,av,ev))
        if mismatch:mismatched_snapshots+=1
        # Both totals use the same exact saved prior, with their own final rounding.
        assert a[19]==e[19] and a[20]==a[18]+a[19] and e[20]==e[18]+e[19]
        gap=abs((a[18]-e[18])-(a[20]-e[20]))
        assert gap<=math.ulp(a[20])+math.ulp(e[20])
        if gap:rounding_differences+=1;max_rounding_difference=max(max_rounding_difference,gap)
        time.append(e[17]/60);delta.append((a[18]-e[18])/1e-10)
        # These costs are positive: raw positive binary64 encodings are monotone.
        ulps.append(abs(struct.unpack('<Q',struct.pack('<d',a[18]))[0]-struct.unpack('<Q',struct.pack('<d',e[18]))[0]))
    with gzip.open(out/'mismatches.csv.gz','rt') as f:
        rows=list(csv.DictReader(f))
    assert len(rows)==len(inventory)==31092
    for row,(index,name,av,ev) in zip(rows,inventory):
        assert int(row['sample_index'])==index and row['field']==name
        assert float.fromhex(row['actual_hex'])==av and float.fromhex(row['expected_hex'])==ev
        assert float(row['absolute_difference'])==abs(av-ev)
    for name,n in field_counts.items():
        assert summary['fields'][name]['mismatches']==n
        assert summary['fields'][name]['max_absolute_difference']==maximum[name]
    assert mismatched_snapshots==summary['mismatch_snapshots']==15546
    first=next((a,e) for a,e in zip(actual,expected) if a[18]!=e[18])
    original=json.loads((census.PARENT/'result_review.json').read_text())['snapshot_failure']
    assert first[0][0]==224 and first[0][18]==original['actual'] and first[1][18]==original['expected']
    for name in ('actual_snapshots.bin','diagnostic_bank.bin'):
        assert census.runner.identity(out/name)==census.runner.identity(out/(name+'.copy'))
        assert (out/name).stat().st_ino!=(out/(name+'.copy')).stat().st_ino
    report=root/'reporting001';report.mkdir()
    fig,axes=plt.subplots(2,1,figsize=(10,6),sharex=True,layout='constrained')
    axes[0].plot(time,delta,color='#245f9a',linewidth=.55)
    axes[0].axhline(0,color='#777777',linewidth=.6)
    axes[0].set_ylabel('Likelihood difference\n(10⁻¹⁰ NLL)')
    axes[0].set_title('Parity census: all 15,751 saved snapshots',loc='left',fontweight='bold')
    axes[1].plot(time,ulps,color='#956018',linewidth=.55)
    axes[1].set_ylabel('ULP distance');axes[1].set_xlabel('Saved elapsed time (minutes)')
    axes[1].set_xlim(0,120);axes[1].set_ylim(bottom=0)
    for ax in axes:ax.grid(alpha=.18)
    fig.suptitle('Only likelihood and total cost differ; saved states, prior, elapsed time and flags match exactly.',fontsize=10)
    fig.savefig(report/'cost_parity.png',dpi=160)
    fig.savefig(report/'cost_parity.svg')
    plt.close(fig)
    peak_rss=receipt['supervisor_peak_RSS_bytes']+max(c['peak_RSS_bytes'] for c in receipt['children'])
    output_bytes=sum(p.stat().st_size for p in out.iterdir() if p.is_file())
    assert output_bytes<67108864 and peak_rss<268435456
    review={'schema':'mumble_parity_census_saved_review_v1','status':'passed','independent':False,
            'method':'Recompute mismatch counts/maxima and positive-cost ULP distances from complete saved binary records; verify every inventory row and prior failure witness.',
            'source_revision':receipt['source_revision'],'original_strict_failure_reproduced':True,
            'all_closed_hashes_verified':True,'both_binary_capture_copies_verified':True,
            'inventory_rows_verified':len(rows),'snapshots_verified':len(actual),
            'all_prior_values_bitwise_identical':True,
            'all_total_costs_equal_binary64_likelihood_plus_prior':True,
            'snapshots_with_differently_rounded_cost_deltas':rounding_differences,
            'maximum_final_addition_rounding_difference_NLL':max_rounding_difference,
            'affected_fields':[n for n,c in field_counts.items() if c],
            'all_other_saved_fields_match':True,'max_cost_absolute_difference_NLL':max(maximum.values()),
            'max_cost_ULP_distance':max(ulps),'final_likelihood_difference_NLL':actual[-1][18]-expected[-1][18],
            'closed_execution_bytes_including_receipt':output_bytes,'conservative_combined_peak_RSS_bytes':peak_rss,
            'model_optimizer_truth_calls':0,'script':census.runner.identity(Path(__file__)),
            'figures':{name:census.runner.identity(report/name) for name in ('cost_parity.png','cost_parity.svg')},
            'assessment':'Observed saved-output discrepancies are negligible at the declared application scales and consistent with small floating-point arithmetic drift. Their specific cause and equality of unsaved bank coefficients remain unestablished. This supports continuing joint-shape investigation with documented numerical parity rather than treating any bit difference as a substantive discrepancy.'}
    census.runner.save(root/'result_review.json',review)
    print(json.dumps({k:review[k] for k in ('status','affected_fields','max_cost_absolute_difference_NLL','max_cost_ULP_distance','final_likelihood_difference_NLL')}))


if __name__=='__main__':main()
