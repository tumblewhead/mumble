#!/usr/bin/env python3
"""Finite fabricated qualification; every invocation gets a fresh receipt directory."""
import argparse
from decimal import Decimal as D, localcontext
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import traceback

import runner
import shape

PAIRS = [(0,0),(0,7),(0,12),(1,1),(1,8),(1,13),(2,2),(2,9),(2,14),
         (3,3),(3,4),(4,4),(3,10),(3,15),(4,10),(4,15),(10,15),(11,11),(5,11),(5,5)]


def polynomial(fixture, point):
    x = [(D(a)-D(b))/D(s) for a,b,s in zip(point,fixture['origin'],fixture['public_sd'])]
    features = [x[i]*x[j] for i,j in PAIRS]+x+[D(1)]
    cost, k = D(0), 0
    for row in range(37):
        residual = D(0)
        for col in range(row,37):
            residual += D(fixture['upper'][k])*features[col]; k += 1
        cost += residual*residual/2
    return cost


def independent_recurrence(x, operands):
    x = list(map(D,x)); tau=[v.exp() for v in x[:3]];gamma=[v.exp() for v in x[3:5]]
    q=x[5].exp();v=x[12:15].copy();h=x[15];charge=D(0)
    maximum=D(0)
    for row in operands:
        dt,current=D(row['dt']),D(row['I'])
        charge+=current*dt/3600;z=x[11]-charge/q
        t=(16*(z-D('.5'))).exp()
        mu=3+D('1.15')*z+D('.08')*(t-1)/(t+1)-x[6]*current
        for i in range(3):
            e=(-dt/tau[i]).exp();v[i]=e*v[i]+(1-e)*x[7+i]*current;mu-=v[i]
        if current and dt:
            e=(-gamma[0 if current>0 else 1]*abs(current)*dt/3600).exp()
            h=e*h+(1-e)*(1 if current>0 else -1)
        mu-=x[10]*h
        maximum=max(maximum,abs(mu-D(row['mu'])))
    return maximum,[z,*v,h]


def check_numerics(log):
    fixture=None;operands=[];checks=0;max_prediction=0.;max_poly_ratio=0.;max_ref_ratio=0.
    with localcontext() as context:
        context.prec=60
        for row in map(json.loads,log.read_text().splitlines()):
            if row['kind']=='polynomial_fixture':fixture=row
            elif row['kind']=='computed_operand':operands.append(row)
            elif row['kind']=='node':
                assert row['status']=='available' and len(operands)==96
                represented=polynomial(fixture,row['x'])
                poly_error=abs(represented-D(row['represented_likelihood_cost']))
                assert poly_error<=D(row['represented_cost_allowance']), 'polynomial arithmetic allowance'
                exact=sum(((D(o['mu'])-D(o['V']))/D(.001))**2/2 for o in operands)
                ref_error=abs(exact-D(row['reference_likelihood_cost']))
                assert ref_error<=D(row['reference_cost_allowance']), 'reference arithmetic allowance'
                prediction,endpoints=independent_recurrence(row['x'],operands)
                assert prediction<D('2e-12'), 'original recurrence versus independent physical recurrence'
                assert max(abs(a-D(b)) for a,b in zip(endpoints,row['reference_endpoint']))<D('2e-12')
                checks+=4;max_prediction=max(max_prediction,float(prediction))
                max_poly_ratio=max(max_poly_ratio,float(poly_error/D(row['represented_cost_allowance'])))
                max_ref_ratio=max(max_ref_ratio,float(ref_error/D(row['reference_cost_allowance'])))
                operands=[]
    assert checks==80
    return {'checks':checks,'Decimal_precision':60,'maximum_prediction_difference_V':max_prediction,
            'maximum_polynomial_error_to_allowance':max_poly_ratio,'maximum_reference_error_to_allowance':max_ref_ratio}


def negative_checks(directory,binary,budget):
    source='0100000000000000000000000000000000000000000000000000000000000000'
    obs=directory/'case1.observations.bin';expected=directory/'case1.expected.bin'
    bank=directory/'case1.bank.bin';nodes=directory/'case1.nodes.bin'
    tests=[]
    def reject(name,command):
        try:
            budget.run(command,name)
        except shape.ContractError:
            assert budget.children[-1]['returncode']!=0
            tests.append(name)
        else:raise AssertionError('Expected rejection: '+name)
    def modified(name,original,change):
        path=directory/name;data=bytearray(original.read_bytes());change(data);path.write_bytes(data);return path
    def capture_with(name,observations=obs,expect=expected):
        reject(name,[str(binary),'capture',str(observations),str(expect),str(directory/(name+'.bank')),source,'96'])
        assert not (directory/(name+'.bank')).exists()
    bad=modified('parity.expected.bin',expected,lambda b:b.__setitem__(8+17*8,b[8+17*8]^1))
    capture_with('reject_parity',expect=bad)
    bad=modified('order.observations.bin',obs,lambda b:b.__setitem__(slice(32,40),struct.pack('<Q',0)))
    capture_with('reject_order',observations=bad)
    bad=modified('short.observations.bin',obs,lambda b:b.__delitem__(slice(40,None)))
    capture_with('reject_short',observations=bad)
    bad=modified('nonfinite.observations.bin',obs,lambda b:b.__setitem__(slice(24,32),struct.pack('<d',math.nan)))
    capture_with('reject_nonfinite',observations=bad)
    bad=modified('trailing.expected.bin',expected,lambda b:b.extend(b'x'))
    capture_with('reject_expected_trailing',expect=bad)
    bad=modified('abi.bank.bin',bank,lambda b:b.__setitem__(8,b[8]^1))
    reject('reject_ABI',[str(binary),'evaluate',str(obs),str(bad),str(nodes),'5','96'])
    bad=modified('short.nodes.bin',nodes,lambda b:b.__delitem__(slice(8,None)))
    reject('reject_short_nodes',[str(binary),'evaluate',str(obs),str(bank),str(bad),'5','96'])
    bad=modified('nonfinite.nodes.bin',nodes,lambda b:b.__setitem__(slice(0,8),struct.pack('<d',math.nan)))
    reject('reject_nonfinite_nodes',[str(binary),'evaluate',str(obs),str(bank),str(bad),'5','96'])
    # A supported-node failure remains an explicit unavailable row, not a missing row.
    bad=modified('unsupported.nodes.bin',nodes,lambda b:b.__setitem__(slice(0,8),struct.pack('<d',100.)))
    log=budget.run([str(binary),'evaluate',str(obs),str(bank),str(bad),'5','96'],'unavailable_node')
    rows=list(map(json.loads,log.read_text().splitlines()))
    assert len(rows)==6 and rows[0]['status']=='unavailable' and rows[-1]['nodes']==5
    tests.append('explicit_unavailable_node')
    # Existing snapshot must never be overwritten, even after a successful replay.
    before=runner.identity(bank)
    reject('reject_snapshot_overwrite',[str(binary),'capture',str(obs),str(expected),str(bank),source,'96'])
    assert runner.identity(bank)==before;tests.append('existing_snapshot_preserved')
    return tests


def supervisor_checks(directory):
    result=[]
    for name,script,kwargs in [
        ('nonzero','raise SystemExit(7)',{}),
        ('wall','import time; time.sleep(5)',{'wall':.15}),
        ('output','import os; os.write(1,b"x"*131072)',{'output':32768})]:
        out=directory/('supervisor_'+name);out.mkdir();budget=runner.Budget(out,**kwargs)
        try:budget.run([sys.executable,'-c',script],name)
        except shape.ContractError:pass
        else:raise AssertionError('Supervisor failed to stop '+name)
        assert len(budget.children)==1
        assert runner.identity(out/(name+'.stdout'))==runner.identity(out/(name+'.stdout.copy'))
        result.append(name)
    out=directory/'exclusive.json';runner.save(out,{'reservation':1})
    try:runner.save(out,{'reservation':2})
    except FileExistsError:pass
    else:raise AssertionError('reservation overwritten')
    assert json.loads(out.read_text())=={'reservation':1};result.append('exclusive_reservation')
    return result


def main(directory):
    directory.mkdir(parents=True,exist_ok=False)
    budget=runner.Budget(directory,cpu=120,wall=180,output=16777216)
    result={'schema':'mumble_fixed_prefix_backend_qualification_v1','status':'failed',
            'canonical_observation_reads':0,'truth_reads':0,'scientific_invocations':0,
            'review':'same assistant; no independent-agent review claimed', 'sources':runner.bound_sources()}
    try:
        binary=directory/'backend';qual=directory/'qualification'
        budget.run(runner.build_command(binary),'build_backend')
        budget.run(runner.build_command(qual,True),'build_qualification')
        symbols=subprocess.check_output(['nm',str(binary)],text=True)
        assert not any(s in symbols for s in (' re_refine',' re_process',' ss_propose',' ch_refine')), 'optimizer reachable in canonical executable'
        log=budget.run([str(qual),str(directory)],'fabricated')
        result['numerics']=check_numerics(log)
        result['C_qualification']=json.loads(log.read_text().splitlines()[-1])
        result['negative_checks']=negative_checks(directory,binary,budget)
        result['supervisor_checks']=supervisor_checks(directory)
        result['binary']=runner.identity(binary)
        result['canonical_executable_optimizer_symbols_absent']=True
        result['status']='passed'
    except BaseException as exc:
        result['error']=type(exc).__name__+': '+str(exc)
        (directory/'failure.txt').write_text(traceback.format_exc())
    result['children']=budget.children
    result['files']={str(p.relative_to(directory)):runner.identity(p) for p in directory.rglob('*') if p.is_file()}
    runner.save(directory/'receipt.json',result)
    print(json.dumps({k:result[k] for k in ('status','error') if k in result}))
    return 0 if result['status']=='passed' else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    sys.exit(main(p.parse_args().output.resolve()))
