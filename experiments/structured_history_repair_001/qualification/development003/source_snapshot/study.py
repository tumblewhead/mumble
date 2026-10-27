#!/usr/bin/env python3
"""Finite controlled-schedule test of the preselected structured-history repair."""
import argparse
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE.parent/'fixed_prefix_shape_001'))
import runner
import shape

OWN=['rolling_engine.c','rolling_engine.h','rolling_model.c','rolling_model.h',
     'features.c','features.h','host.c','study.py','qualify.py','plan.json']
SOURCES=[str(HERE/n) for n in ('host.c','rolling_engine.c','rolling_model.c','features.c')]+[
    'experiments/live_anchor_integration_001/public_contract.c',
    'experiments/live_anchor_integration_001/host_input.c',
    'experiments/live_anchor_bootstrap_001/adc12.c',
    'experiments/live_anchor_bootstrap_001/support_step.c','src/scm_model.c']


def sources():
    out=runner.bound_sources()
    for n in OWN:out[str((HERE/n).relative_to(ROOT))]=runner.identity(HERE/n)
    return out


def build(binary,arm,shared=False,stack=False):
    flags=[*runner.FLAGS,f'-DSH_ANALYTIC_ATTENUATION={int(arm=="full")}']
    if shared:flags+=['-DSH_NO_MAIN','-shared','-fPIC']
    if stack:flags+=['-fstack-usage','-fno-inline','-fno-optimize-sibling-calls']
    return ['cc',*flags,*SOURCES,'-lm','-o',str(binary)]


def paths(plan):
    return {k:ROOT/v['path'] for k,v in plan['inputs'].items()}


def execute(qualification,publication):
    plan=shape.load(HERE/'plan.json');q=shape.load(qualification);pub=shape.load(publication)
    bound=sources();revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    shape.require(q['status']=='passed' and q['sources']==bound,'qualification gate')
    shape.require(pub['status']=='verified_remote' and pub['revision']==revision and pub['sources']==bound,'publication gate')
    inputs=paths(plan)
    for k,p in inputs.items():shape.require(runner.identity(p)=={t:plan['inputs'][k][t] for t in ('bytes','sha256')},'input '+k)
    for arm in ('control','full'):
        shape.require(runner.identity(qualification.parent/(arm+'_worker'))==q['binaries'][arm],'binary '+arm)
        shape.require(q['memory'][arm]['planning_total_bytes']<=10240,'memory gate '+arm)
    runner.save(HERE/'reservation.json',{'source_revision':revision,'sources':bound,'arms':['control','full'],
                'worker_invocations':2,'retries':0,'caps':plan['caps'],'qualification':runner.identity(qualification),
                'publication':runner.identity(publication)})
    out=HERE/'attempt001';out.mkdir();budget=runner.Budget(out,cpu=120,wall=180)
    result={'status':'unresolved','source_revision':revision,'sources':bound,'arms':{},
            'optimizer_calls':0,'truth_reads':0,'reference_steps':0,'causal_probe_started':False}
    try:
        frozen={k:runner.identity(p) for k,p in inputs.items()}
        runner.save(out/'inputs_frozen.json',{'files':frozen,'nodes':545,'reference_calls':0,'radius_adaptations':0})
        for arm in ('control','full'):
            try:
                binary=qualification.parent/(arm+'_worker');bank=out/(arm+'.bank.bin')
                log=budget.run([str(binary),'run',str(inputs['observations']),str(inputs['expected']),
                               str(inputs['nodes_binary']),str(bank),'252000','545',plan['source_id']],arm)
                records=[json.loads(l) for l in log.read_text().splitlines()];terminal=records[-1]
                shape.require(terminal['kind']=='terminal' and len(records)==546 and terminal['nodes']==545,'complete nodes')
                shape.require(terminal['model_steps']==504000 and terminal['qr_rows']==252000 and
                              terminal['query_evaluations']==15750+545 and terminal['prior_evaluations']==0,'work accounting')
                copy=out/(arm+'.bank.bin.copy')
                with bank.open('rb') as src,copy.open('xb') as dst:
                    shutil.copyfileobj(src,dst);dst.flush();os.fsync(dst.fileno())
                shape.require(runner.identity(bank)==runner.identity(copy) and bank.stat().st_ino!=copy.stat().st_ino,'bank preservation')
                runner.save(out/(arm+'.records.json'),records)
                result['arms'][arm]={'status':'completed','work':terminal,'bank':runner.identity(bank)}
            except Exception as exc:
                result['arms'][arm]={'status':'unresolved','error':type(exc).__name__+': '+str(exc)}
        shape.require(all(runner.identity(inputs[k])==v for k,v in frozen.items()),'input preservation')
        shape.require(sources()==bound,'source preservation')
        for arm in ('control','full'):
            shape.require(runner.identity(qualification.parent/(arm+'_worker'))==q['binaries'][arm],'binary preservation')
        shape.require(all(r['status']=='completed' for r in result['arms'].values()),'one or more arms unresolved')
        result['status']='completed';budget.check()
    except BaseException as exc:result['error']=type(exc).__name__+': '+str(exc)
    finally:
        result.update(children=budget.children,CPU_s=budget.used_cpu(),wall_s=time.monotonic()-budget.started,
                      supervisor_peak_RSS_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
                      files={p.name:runner.identity(p) for p in out.iterdir() if p.is_file()})
        runner.save(out/'receipt.json',result)
    print(json.dumps({'status':result['status'],'arms':{k:v['status'] for k,v in result['arms'].items()}}))
    return int(result['status']!='completed')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--qualification',type=Path,required=True)
    p.add_argument('--publication',type=Path,required=True);a=p.parse_args()
    sys.exit(execute(a.qualification.resolve(),a.publication.resolve()))
