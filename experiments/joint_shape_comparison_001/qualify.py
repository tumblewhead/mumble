#!/usr/bin/env python3
"""Small fabricated-input bridge qualification; no battery archive access."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

import run
from run import HERE, ROOT, runner, shape


def main():
    out=HERE/'qualification/development001'; out.mkdir(parents=True)
    bound=run.sources(); snapshot=out/'source_snapshot'; snapshot.mkdir()
    for name in bound:
        dest=snapshot/name; dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,dest)
    budget=runner.Budget(out,cpu=60,wall=120)
    result={'status':'failed','sources':bound,'source_review_independent':False,
            'canonical_input_reads':0,'checks':0}
    def check(condition,message):
        shape.require(condition,message); result['checks']+=1
    try:
        binary=out/'bridge'
        budget.run(run.build_command(binary),'build')
        result['binary']=runner.identity(binary)
        fixture=HERE.parent/'fixed_prefix_shape_001/qualification/backend_development003'
        records=[json.loads(l) for l in (fixture/'fabricated.stdout').read_text().splitlines()]
        captures=[r for r in records if r['kind']=='capture']
        original_nodes=[r for r in records if r['kind']=='node']
        check(len(captures)==4 and len(original_nodes)==20,'fixture rows')
        result['inherited_qualification']=runner.identity(fixture/'receipt.json')
        result['fixtures']={p.name:runner.identity(p) for p in fixture.iterdir()
                            if p.name.startswith('case') or p.name=='fabricated.stdout'}
        for i in range(4):
            bank=fixture/f'case{i}.bank.bin'; original=bank.read_bytes()
            diagnostic=out/f'case{i}.diagnostic.bin'
            diagnostic.write_bytes(b'FPSHC01\0'+original[8:])
            derived=out/f'case{i}.adapter.bin'
            manifest=run.adapt_bank(diagnostic,derived,runner.identity(diagnostic))
            check(derived.read_bytes()==original and manifest['changed_byte_offsets']==[4], 'exact adapter')
            check(not manifest['strict_parity_certified'],'honest adapter semantics')
            log=budget.run([str(binary),'metric',str(derived)],f'metric{i}')
            metric=json.loads(log.read_text())
            for key in ('anchor','metric_packed_lower','public_sd','lower','upper','charge_min_Ah',
                        'charge_max_Ah','charge_Ah','prefix'):
                check(metric[key]==captures[i][key],'saved fabricated metric '+key)
            check(metric['model_steps']==0 and metric['query_evaluations']==1
                  and metric['prior_evaluations']==1,'metric-only work')
            log=budget.run([str(binary),'evaluate',str(fixture/f'case{i}.observations.bin'),
                           str(derived),str(fixture/f'case{i}.nodes.bin'),'5','96'],f'evaluate{i}')
            rows=[json.loads(l) for l in log.read_text().splitlines()]
            check(rows[:-1]==original_nodes[i*5:(i+1)*5],'unchanged qualified reference results')
            check(rows[-1]['model_steps']==480 and rows[-1]['represented_queries']==5
                  and rows[-1]['optimizer_calls']==0 and rows[-1]['prior_calls']==0,'reference work')
            check(derived.read_bytes()==original and bank.read_bytes()==original,'input preservation')
            try: run.adapt_bank(diagnostic,derived,runner.identity(diagnostic))
            except FileExistsError: check(True,'overwrite rejected')
            else: check(False,'overwrote adapter')
        base=(fixture/'case1.bank.bin').read_bytes()
        for name,data in [('diagnostic_magic',b'FPSHC01\0'+base[8:]),('short',base[:-1]),
                          ('trailing',base+b'x'),('ABI',base[:8]+b'\0'*8+base[16:])]:
            path=out/(name+'.bank.bin');path.write_bytes(data)
            proc=subprocess.run([str(binary),'metric',str(path)],capture_output=True,timeout=5)
            runner.save(out/(name+'.rejection.json'),{'command':proc.args,'returncode':proc.returncode,
                        'stdout':proc.stdout.decode(),'stderr':proc.stderr.decode()})
            check(proc.returncode!=0 and not proc.stdout,'invalid snapshot rejected '+name)
        for name,data,expected in [('strict_magic',base,None),('bad_ABI',b'FPSHC01\0'+b'\0'*8+base[16:],None),
                                   ('wrong_hash',b'FPSHC01\0'+base[8:],{'bytes':6864,'sha256':'0'*64})]:
            path=out/(name+'.input.bin');path.write_bytes(data)
            dest=out/(name+'.output.bin')
            try: run.adapt_bank(path,dest,expected or runner.identity(path))
            except shape.ContractError: check(not dest.exists(),'invalid adapter did not create output')
            else: check(False,'invalid adapter accepted')
        symbols=subprocess.check_output(['nm',str(binary)],text=True)
        check(all((' '+s+'\n') not in symbols for s in
                  ('re_refine','re_process','ch_refine','capture','inherited_backend_main')),
              'capture/optimizer entry points absent from linked executable')
        budget.run([sys.executable,'-B','-m','unittest','discover','-s',
                    'experiments/fixed_prefix_shape_001','-p','test_shape.py'],'geometry_tests')
        check(run.sources()==bound,'source preservation')
        result['status']='passed'
    except BaseException as exc:
        result['error']=type(exc).__name__+': '+str(exc)
    finally:
        result.update(children=budget.children,CPU_s=budget.used_cpu(),
                      files={p.name:runner.identity(p) for p in out.iterdir() if p.is_file()})
        runner.save(out/'receipt.json',result)
    print(json.dumps({k:result[k] for k in ('status','checks')}))
    return int(result['status']!='passed')


if __name__=='__main__': sys.exit(main())
