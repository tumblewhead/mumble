#!/usr/bin/env python3
"""Fabricated qualification for observation-only mismatch continuation."""
import argparse
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import traceback

import census


def main(output):
    output.mkdir(parents=True,exist_ok=False)
    budget=census.runner.Budget(output,cpu=60,wall=90)
    result={'schema':'mumble_parity_census_qualification_v1','status':'failed','sources':census.bindings(),
            'canonical_observation_reads':0,'canonical_model_steps':0,'optimizer_calls':0,'truth_reads':0,
            'review':'same assistant; not an independent review'}
    snapshots=output/'source_snapshot';snapshots.mkdir()
    for name in ('census.c','census.py','test_census.py','qualify.py','plan.json'):
        (snapshots/name).write_bytes((census.HERE/name).read_bytes())
    try:
        binary=output/'census';budget.run(census.build(binary),'build')
        symbols=subprocess.check_output(['nm',str(binary)],text=True)
        assert not any(s in symbols for s in (' re_refine',' re_process',' ss_propose',' scm_model_step',' scm_model_predict'))
        budget.run([sys.executable,'-B','-m','unittest','discover','-s',str(census.HERE),'-p','test_census.py','-v'],'unit_tests')
        fixture=census.PARENT/'qualification/backend_development003'
        obs=fixture/'case1.observations.bin';expected=fixture/'case1.expected.bin'
        source='0100000000000000000000000000000000000000000000000000000000000000'
        fixtures={str(p.relative_to(census.ROOT)):census.runner.identity(p) for p in (obs,expected)}
        def run(name,exp=expected,observations=obs,success=True):
            directory=output/name;directory.mkdir()
            command=[str(binary),str(observations),str(exp),str(directory/'actual.bin'),str(directory/'bank.bin'),source,'96']
            try:log=budget.run(command,name)
            except census.shape.ContractError:
                if success:raise
                assert budget.children[-1]['returncode']!=0
                return json.loads((output/(name+'.stdout')).read_text().splitlines()[-1]),directory
            if not success:raise AssertionError('Expected structural failure')
            return json.loads(log.read_text().splitlines()[-1]),directory
        terminal,base=run('exact')
        assert terminal['snapshots']==7 and terminal['mismatch_snapshots']==0
        assert (base/'actual.bin').read_bytes()==expected.read_bytes()
        data=bytearray(expected.read_bytes())
        def set_value(row,field,value):struct.pack_into('<d',data,row*census.RECORD.size+8+field*8,value)
        set_value(0,16,-0.)
        value=struct.unpack_from('<d',data,census.RECORD.size+8+17*8)[0]
        set_value(1,17,math.nextafter(value,math.inf))
        set_value(3,19,1000000.)
        set_value(5,21,.2)
        offset=6*census.RECORD.size+224
        struct.pack_into('<I',data,offset,struct.unpack_from('<I',data,offset)[0]^4)
        changed=output/'changed.expected.bin';changed.write_bytes(data)
        terminal,modified=run('all_mismatches',changed)
        assert terminal['snapshots']==7 and terminal['mismatch_snapshots']==5
        assert terminal['floating_mismatches']==4 and terminal['integer_mismatches']==1
        assert (modified/'actual.bin').read_bytes()==(base/'actual.bin').read_bytes(), 'comparison must not correct state'
        assert (modified/'bank.bin').read_bytes()==(base/'bank.bin').read_bytes(), 'mismatch reporting changed bank'
        assert (base/'bank.bin').read_bytes()[:8]==b'FPSHC01\0'
        summary=census.analyze(modified/'actual.bin',changed,modified,planned_snapshots=7)
        assert summary['floating_mismatches']==4 and summary['integer_mismatches']==1
        structural=[]
        for name,offset,encoding in [('nonfinite_expected',8+17*8,struct.pack('<d',math.nan)),
                                      ('wrong_index_expected',census.RECORD.size,struct.pack('<Q',32))]:
            changed_data=bytearray(expected.read_bytes());changed_data[offset:offset+len(encoding)]=encoding
            path=output/(name+'.bin');path.write_bytes(changed_data)
            terminal,_=run(name,path,success=False)
            assert terminal['status']=='structural_failure';structural.append(name)
        truncated=output/'short_observations.bin';truncated.write_bytes(obs.read_bytes()[:40])
        terminal,_=run('short_input',observations=truncated,success=False)
        assert terminal['status']=='structural_failure';structural.append('short_input')
        result.update(status='passed',binary=census.runner.identity(binary),compiler=subprocess.check_output(['cc','--version'],text=True).splitlines()[0],
                      unit_tests=8,continuation_checks=['exact_output_reproduction','five_injected_mismatch_snapshots_all_recorded',
                      'late_large_numeric_difference_continues','flag_difference_continues','signed_zero_recorded',
                      'all_reconstructed_snapshots_unchanged','bank_unchanged','distinct_checkpoint_schema'],
                      structural_failure_checks=structural,fixtures=fixtures,forbidden_symbols_absent=True)
    except BaseException as exc:
        result['error']=type(exc).__name__+': '+str(exc);(output/'failure.txt').write_text(traceback.format_exc())
    result['children']=budget.children
    result['files']={str(p.relative_to(output)):census.runner.identity(p) for p in output.rglob('*') if p.is_file()}
    census.runner.save(output/'receipt.json',result)
    print(json.dumps({k:result[k] for k in ('status','error') if k in result}))
    return 0 if result['status']=='passed' else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    sys.exit(main(parser.parse_args().output.resolve()))
