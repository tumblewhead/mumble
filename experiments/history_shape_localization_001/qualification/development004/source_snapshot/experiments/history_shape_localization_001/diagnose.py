#!/usr/bin/env python3
"""Bounded diagnosis only. Never installs the retrospective oracle as a candidate."""
import argparse
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE.parent/'fixed_prefix_shape_001'))
import runner
import shape
import numpy as np


def sources():
    result=runner.bound_sources()
    for n in ('localize.c','diagnose.py','localization_plan.json','continuation_plan.json'):
        p=HERE/n;result[str(p.relative_to(ROOT))]=runner.identity(p)
    return result


def build(binary):
    return ['cc',*runner.FLAGS,str(HERE/'localize.c'),*runner.SOURCES[2:],'-lm','-o',str(binary)]


def input_paths(plan):
    return {k:ROOT/v['path'] for k,v in plan['inputs'].items()}


def run_worker(budget,binary,out,name,obs,expected,bank,nodes,prefix,checkpoints,selected,node_count):
    cp=out/(name+'.checkpoints.bin');cp.write_bytes(struct.pack('<'+'Q'*len(checkpoints),*checkpoints))
    sel=out/(name+'.selected.bin');sel.write_bytes(struct.pack('<'+'I'*len(selected),*selected))
    command=[str(binary),str(obs),str(expected),str(bank),str(nodes),str(prefix),str(cp),
             str(len(checkpoints)),str(node_count),str(sel),str(len(selected))]
    log=budget.run(command,name)
    records=[json.loads(line) for line in log.read_text().splitlines()]
    shape.require(records[-1]['kind']=='terminal','missing terminal')
    work=records[-1]
    shape.require(work['prefix']==prefix and work['merge_steps']==prefix+sum(checkpoints)
                  and work['reference_steps']==prefix and work['qr_rows']==prefix
                  and work['oracle_queries']==node_count,'work accounting')
    return records


def qualify():
    out=HERE/'qualification/development004';out.mkdir(parents=True)
    bound=sources()
    for n in bound:
        p=out/'source_snapshot'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,p)
    budget=runner.Budget(out,cpu=60,wall=120)
    result={'status':'failed','sources':bound,'checks':0,'canonical_input_reads':0,'independent':False}
    def check(ok,msg):shape.require(ok,msg);result['checks']+=1
    try:
        paths=input_paths(shape.load(HERE/'localization_plan.json'))
        check(len(paths)==6 and all(isinstance(p,Path) and p.is_absolute() for p in paths.values()),
              'canonical path preparation without opening inputs')
        binary=out/'localize';budget.run(build(binary),'build');result['binary']=runner.identity(binary)
        fixture=HERE.parent/'fixed_prefix_shape_001/qualification/backend_development003'
        old=[json.loads(l) for l in (fixture/'fabricated.stdout').read_text().splitlines()]
        nodes=[r for r in old if r['kind']=='node'];result['fixture_receipt']=runner.identity(fixture/'receipt.json')
        for i in range(4):
            records=run_worker(budget,binary,out,f'case{i}',fixture/f'case{i}.observations.bin',
                              fixture/f'case{i}.expected.bin',fixture/f'case{i}.bank.bin',
                              fixture/f'case{i}.nodes.bin',96,[16,32,48,96],list(range(5)),5)
            saved=records[0];windows=[r for r in records if r['kind']=='window']
            direct=[r for r in records if r['kind']=='direct_row_sum']
            oracle=[r for r in records if r['kind']=='oracle_node']
            check(len(windows)==4 and len(direct)==5 and len(oracle)==5,'complete qualification output')
            for j,row in enumerate(direct):
                known=nodes[5*i+j]['represented_likelihood_cost']
                check(abs(row['cost']-known)<=1e-10*(1+abs(known)),'direct row sum vs qualified QR')
            g=sum(np.array(r['rolling_rows']['gradient']) for r in windows)
            check(np.max(abs(g-saved['gradient']))<=1e-10*(1+np.max(abs(g))),'gradient preservation')
            ref=sum(r['original_recurrence']['cost'] for r in windows)
            known=nodes[5*i]['reference_likelihood_cost']
            check(abs(ref-known)<=1e-10*(1+abs(known)),'original reference operand mapping')
            check(abs(oracle[0]['cost']-ref)<=1e-10*(1+abs(ref)),'exact-origin oracle anchor')
            check(records[-1]['max_origin_residual_gap']<=1e-9,'exact-origin residual kernel agreement')
            check(records[-1]['max_origin_derivative_gap']<=1e-9,'exact-origin derivative kernel agreement')
            # At the first block there is no earlier boundary to approximate.
            first=next(r for r in records if r['kind']=='block_decomposition')
            check(first['rolling_rows']==first['exact_origin_rows'],'zero-prefix boundary transport exact')
            last=[r for r in records if r['kind']=='block_decomposition'][-1]
            check(abs(last['exact_origin_rows']['cost']-last['original_recurrence']['cost'])
                  <=1e-10*(1+abs(last['original_recurrence']['cost'])),'last block no anchor displacement')
        check(sources()==bound,'source preservation');result['status']='passed'
    except BaseException as exc:result['error']=type(exc).__name__+': '+str(exc)
    finally:
        result.update(children=budget.children,CPU_s=budget.used_cpu(),
                      files={p.name:runner.identity(p) for p in out.iterdir() if p.is_file()})
        runner.save(out/'receipt.json',result)
    print(json.dumps({k:result[k] for k in ('status','checks')}))
    return int(result['status']!='passed')


def execute():
    plan=shape.load(HERE/'localization_plan.json');bound=sources()
    qpath=HERE/'qualification/development004/receipt.json';q=shape.load(qpath)
    publication=shape.load(HERE/'source_publication.json')
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    shape.require(q['status']=='passed' and q['sources']==bound,'qualification gate')
    shape.require(publication['status']=='verified_remote' and publication['revision']==revision
                  and publication['sources']==bound,'source publication gate')
    binary=qpath.parent/'localize';shape.require(runner.identity(binary)==q['binary'],'binary identity')
    for v in plan['inputs'].values():
        shape.require(runner.identity(ROOT/v['path'])=={k:v[k] for k in ('bytes','sha256')},'input identity')
    previous=shape.load(HERE/'attempt001/receipt.json')
    shape.require(previous['status']=='unresolved' and previous['children']==[]
                  and previous['error']=="TypeError: 'PosixPath' object is not subscriptable",
                  'continuation requires preserved zero-worker prelaunch failure')
    runner.save(HERE/'reservation002.json',{'source_revision':revision,'sources':bound,'invocations':1,
                'retries':0,'caps':plan['caps'],'qualification':runner.identity(qpath)})
    out=HERE/'attempt002';out.mkdir();budget=runner.Budget(out,cpu=60,wall=120)
    result={'status':'unresolved','source_revision':revision,'sources':bound,'invocations':1,
            'candidate_updates':0,'optimizer_calls':0,'truth_reads':0}
    try:
        paths=input_paths(plan)
        records=run_worker(budget,binary,out,'localization',paths['observations'],paths['expected'],
                           paths['bank'],paths['nodes_binary'],252000,plan['checkpoints'],
                           plan['selected_node_indices'],545)
        for v in plan['inputs'].values():
            shape.require(runner.identity(ROOT/v['path'])=={k:v[k] for k in ('bytes','sha256')},'input preservation')
        shape.require(sources()==bound and runner.identity(binary)==q['binary'],'source/binary preservation')
        runner.save(out/'records.json',records)
        result.update(status='completed',work=records[-1]);budget.check()
    except BaseException as exc:result['error']=type(exc).__name__+': '+str(exc)
    finally:
        result.update(CPU_s=budget.used_cpu(),wall_s=time.monotonic()-budget.started,children=budget.children,
                      files={p.name:runner.identity(p) for p in out.iterdir() if p.is_file()})
        runner.save(out/'receipt.json',result)
    print(json.dumps({k:result[k] for k in ('status','invocations')}))
    return int(result['status']!='completed')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['qualify','run'])
    a=p.parse_args();sys.exit(qualify() if a.mode=='qualify' else execute())
