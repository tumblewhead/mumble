#!/usr/bin/env python3
"""Run and summarize the separately authorized non-aborting parity census."""
import argparse
import csv
import gzip
import io
import json
import math
import os
from pathlib import Path
import platform
import resource
import shutil
import struct
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PARENT = ROOT/'experiments/fixed_prefix_shape_001'
sys.path.insert(0,str(PARENT))
import runner
import shape

RECORD = struct.Struct('<Q27dIII')
COORDINATES = ['logtau1','logtau2','logtau3','loggamma_plus','loggamma_minus','logQ',
               'R0','R1','R2','R3','H','initial_SOC','initial_v1','initial_v2','initial_v3','initial_h']
FIELDS = ['x.'+x for x in COORDINATES]+['elapsed_s','likelihood_cost','prior_cost','total_cost',
          'endpoint.SOC','endpoint.v1_V','endpoint.v2_V','endpoint.v3_V','endpoint.h',
          'min_support_slack','min_endpoint_slack','flags','phase_and_flags','available']
BINS = ['signed_zero','1','2_to_4','5_to_16','17_to_256','257_to_4096','above_4096']


def ordered(x):
    bits=struct.unpack('<Q',struct.pack('<d',x))[0]
    return (1<<63)-(bits&((1<<63)-1)) if bits>>63 else (1<<63)+bits


def difference(actual,expected):
    if not (math.isfinite(actual) and math.isfinite(expected)):
        raise ValueError('Nonfinite scalar cannot be summarized as a numerical mismatch')
    signed=actual-expected
    absolute=abs(signed)
    scale=max(abs(actual),abs(expected))
    return signed,absolute,absolute/scale if scale else 0.,abs(ordered(actual)-ordered(expected))


def bin_name(ulp):
    if ulp==0:return 'signed_zero'
    if ulp==1:return '1'
    if ulp<=4:return '2_to_4'
    if ulp<=16:return '5_to_16'
    if ulp<=256:return '17_to_256'
    if ulp<=4096:return '257_to_4096'
    return 'above_4096'


def records(path):
    with path.open('rb') as f:
        while data:=f.read(RECORD.size):
            if len(data)!=RECORD.size:raise ValueError('Truncated snapshot record')
            yield RECORD.unpack(data)


def analyze(actual,expected,output,planned_snapshots=15751):
    fields={name:{'mismatches':0,'first_index':None,'last_index':None,
                  'max_absolute_difference':0.,'max_relative_difference':0.,'max_ULP_distance':0,
                  'ULP_histogram':{b:0 for b in BINS},'longest_consecutive_snapshot_run':0,
                  'maximum_absolute_example':None,'maximum_ULP_example':None} for name in FIELDS}
    windows=[{'nominal_start_s':900*i,'nominal_end_s':900*(i+1),'mismatch_snapshots':0,'fields':{}} for i in range(8)]
    runs={name:0 for name in FIELDS};counts={name:0 for name in ('snapshots','mismatch_snapshots','floating_mismatches','integer_mismatches')}
    expected_iter=records(expected)
    inventory=output/'mismatches.csv.gz'
    with inventory.open('xb') as raw, gzip.GzipFile(fileobj=raw,mode='wb',mtime=0,filename='') as compressed, io.TextIOWrapper(compressed,encoding='utf-8',newline='') as text:
        writer=csv.writer(text)
        writer.writerow(['sample_index','saved_elapsed_s','field','actual','expected','actual_hex','expected_hex',
                         'signed_difference','absolute_difference','relative_difference','ULP_distance'])
        for a in records(actual):
            e=next(expected_iter,None)
            if e is None or a[0]!=e[0] or a[0]!=counts['snapshots']*16:
                raise ValueError('Snapshot count/order mismatch')
            index=a[0];elapsed=e[17];window=windows[min(index//31500,7)];snapshot_mismatch=False
            for j,name in enumerate(FIELDS):
                av,ev=a[j+1],e[j+1];floating=j<27
                unequal=struct.pack('<d',av)!=struct.pack('<d',ev) if floating else av!=ev
                if not unequal:runs[name]=0;continue
                counts['floating_mismatches' if floating else 'integer_mismatches']+=1;snapshot_mismatch=True
                if floating:
                    signed,absolute,relative,ulp=difference(av,ev);ah,eh=av.hex(),ev.hex()
                else:
                    signed=av-ev;absolute=abs(signed);relative=absolute/max(abs(av),abs(ev));ulp=None;ah,eh=hex(av),hex(ev)
                writer.writerow([index,repr(elapsed),name,repr(av),repr(ev),ah,eh,repr(signed),repr(absolute),repr(relative),ulp])
                item={'sample_index':index,'saved_elapsed_s':elapsed,'actual':av,'expected':ev,
                      'absolute_difference':absolute,'relative_difference':relative,'ULP_distance':ulp}
                s=fields[name];s['mismatches']+=1;runs[name]+=1
                if s['first_index'] is None:s['first_index']=index
                s['last_index']=index;s['longest_consecutive_snapshot_run']=max(s['longest_consecutive_snapshot_run'],runs[name])
                if s['maximum_absolute_example'] is None or absolute>s['max_absolute_difference']:
                    s['maximum_absolute_example']=item
                s['max_absolute_difference']=max(s['max_absolute_difference'],absolute)
                s['max_relative_difference']=max(s['max_relative_difference'],relative)
                if ulp is not None:
                    s['ULP_histogram'][bin_name(ulp)]+=1
                    if s['maximum_ULP_example'] is None or ulp>s['max_ULP_distance']:s['maximum_ULP_example']=item
                    s['max_ULP_distance']=max(s['max_ULP_distance'],ulp)
                w=window['fields'].setdefault(name,{'mismatches':0,'max_absolute_difference':0.})
                w['mismatches']+=1;w['max_absolute_difference']=max(w['max_absolute_difference'],absolute)
            counts['snapshots']+=1
            if snapshot_mismatch:counts['mismatch_snapshots']+=1;window['mismatch_snapshots']+=1
    complete=counts['snapshots']==planned_snapshots
    summary={'schema':'mumble_parity_census_summary_v1','status':'complete_inventory' if complete else 'partial_inventory',
             **counts,'matching_snapshots':counts['snapshots']-counts['mismatch_snapshots'],
             'fields':fields,'nominal_900s_windows':windows,'inventory':runner.identity(inventory),
             'strict_bitwise_parity':complete and counts['mismatch_snapshots']==0,
             'tolerance_pass_claimed':False,'bank_identity_proved':False,
             'copied_by_construction':[n for n in FIELDS if n.startswith('x.')],
             'interpretation':'Descriptive replay discrepancies against saved outputs. No full bank-coefficient, joint-shape, coverage or library-cause conclusion.',
             'severity_context':{
                 'max_likelihood_difference_divided_by_existing_0_1_NLL_budget':fields['likelihood_cost']['max_absolute_difference']/.1,
                 'max_SOC_difference_pp':fields['endpoint.SOC']['max_absolute_difference']*100,
                 'max_SOC_difference_divided_by_existing_0_5_pp_target':fields['endpoint.SOC']['max_absolute_difference']*100/.5,
                 'max_RC_voltage_difference_divided_by_existing_1mV_sigma':max(fields['endpoint.v'+str(i)+'_V']['max_absolute_difference'] for i in (1,2,3))/.001,
                 'meaning':'Magnitude context only; these are not acceptance tolerances or physical-truth errors.'}}
    runner.save(output/'summary.json',summary)
    return summary


def bindings():
    result=runner.bound_sources()
    for name in ('census.c','census.py','test_census.py','qualify.py','plan.json'):
        path=HERE/name;result[str(path.relative_to(ROOT))]=runner.identity(path)
    result[str((PARENT/'backend.c').relative_to(ROOT))]=runner.identity(PARENT/'backend.c')
    return result


def build(destination):
    command=runner.build_command(destination)
    command[command.index('experiments/fixed_prefix_shape_001/backend.c')]='experiments/parity_census_001/census.c'
    return command


def main(qualification,publication):
    q=shape.load(qualification);sources=bindings();p=shape.load(publication)
    shape.require(q['status']=='passed' and q['sources']==sources,'qualification/source mismatch')
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    shape.require(p['status']=='verified_remote' and p['revision']==revision and p['sources']==sources,'publication mismatch')
    plan=shape.load(PARENT/'plan.json');inputs={}
    for name in ('observations','trace'):
        row=plan['input'][name];path=ROOT/row['path'];inputs[str(path.relative_to(ROOT))]=runner.identity(path)
        shape.require(inputs[str(path.relative_to(ROOT))]=={k:row[k] for k in ('bytes','sha256')},'input identity mismatch')
    expected=PARENT/'attempt001/expected.bin';old=shape.load(PARENT/'attempt001/receipt.json')
    shape.require(runner.identity(expected)==old['closed_files']['expected.bin'],'expected record identity mismatch')
    inputs[str(expected.relative_to(ROOT))]=runner.identity(expected)
    binary=qualification.parent/'census';shape.require(runner.identity(binary)==q['binary'],'binary changed')
    source=old['children'][0]['command'][-2]
    runner.save(HERE/'reservation.json',{'schema':'mumble_parity_census_reservation_v1','source_revision':revision,
                'canonical_census_invocations':1,'prior_exact_attempt_preserved':True,'sources':sources,'inputs':inputs,
                'qualification':runner.identity(qualification),'publication':runner.identity(publication)})
    output=HERE/'attempt001';output.mkdir();budget=runner.Budget(output,cpu=120,wall=180)
    receipt={'schema':'mumble_parity_census_execution_v1','status':'unresolved','source_revision':revision,
             'sources':sources,'inputs':inputs,'canonical_census_invocations':1,'optimizer_calls':0,'truth_reads':0,
             'reference_passes':0,'prior_exact_attempt_reclassified':False,
             'environment':{'platform':platform.platform(),'compiler':q['compiler'],'libc':platform.libc_ver()}}
    try:
        log=budget.run([str(binary),str(ROOT/plan['input']['observations']['path']),str(expected),
                       str(output/'actual_snapshots.bin'),str(output/'diagnostic_bank.bin'),source,'252000'],'census')
        terminal=json.loads(log.read_text().splitlines()[-1]);receipt['terminal']=terminal
        shape.require(terminal['status']=='completed' and terminal['snapshots']==15751,'incomplete census')
        for name,expected_count in {'model_steps':504000,'qr_rows':252000,'queries':31501,'prior_evaluations':15751}.items():
            shape.require(terminal[name]==expected_count,'work count differs: '+name)
        for name in ('actual_snapshots.bin','diagnostic_bank.bin'):
            path=output/name
            with path.open('rb') as f:os.fsync(f.fileno())
            with path.open('rb') as src,(output/(name+'.copy')).open('xb') as dst:
                shutil.copyfileobj(src,dst);dst.flush();os.fsync(dst.fileno())
            shape.require(runner.identity(path)==runner.identity(output/(name+'.copy')),'capture copy differs')
        summary=analyze(output/'actual_snapshots.bin',expected,output)
        for name in ('snapshots','mismatch_snapshots','floating_mismatches','integer_mismatches'):
            shape.require(summary[name]==terminal[name],'C/Python census count differs')
        shape.require(all(runner.identity(ROOT/path)==value for path,value in inputs.items()),'input changed during census')
        shape.require(bindings()==sources,'source changed during census')
        budget.check();receipt['status']='completed';receipt['summary']=runner.identity(output/'summary.json')
    except BaseException as exc:
        receipt['error']=type(exc).__name__+': '+str(exc)
        path=output/'actual_snapshots.bin'
        if path.exists() and not (output/'summary.json').exists():
            try:analyze(path,expected,output)
            except Exception as failure:receipt['partial_analysis_error']=str(failure)
    finally:
        receipt.update(children=budget.children,CPU_s=budget.used_cpu(),wall_s=time.monotonic()-budget.started,
                       supervisor_peak_RSS_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
                       files={f.name:runner.identity(f) for f in output.iterdir() if f.is_file()})
        runner.save(output/'receipt.json',receipt)
    print(json.dumps({k:receipt[k] for k in ('status','error') if k in receipt}))
    return 0 if receipt['status']=='completed' else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qualification',type=Path,required=True)
    parser.add_argument('--publication',type=Path,required=True)
    args=parser.parse_args()
    sys.exit(main(args.qualification.resolve(),args.publication.resolve()))
