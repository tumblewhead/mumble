#!/usr/bin/env python3
"""One fixed-node comparison of the already saved numerical-reconstruction bank."""
import argparse
import json
import os
from pathlib import Path
import resource
import signal
import struct
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent/'fixed_prefix_shape_001'))
import runner
import shape

OWN = ['bridge.c', 'run.py', 'qualify.py', 'plan.json']
SEMANTICS = ('census numerical reconstruction; original strict parity failed; '
             'original bank coefficient equality unproved; census scalar drift is not a bound at new nodes')


def sources():
    result = runner.bound_sources()
    for name in OWN:
        p = HERE/name
        result[str(p.relative_to(ROOT))] = runner.identity(p)
    return result


def build_command(destination):
    return ['cc', *runner.FLAGS, str(HERE/'bridge.c'), *runner.SOURCES[1:], '-lm', '-o', str(destination)]


def adapt_bank(source, destination, expected):
    """Explicit format-only adapter, never a bitwise-parity certification."""
    shape.require(runner.identity(source) == expected, 'diagnostic bank identity mismatch')
    raw = source.read_bytes()
    shape.require(len(raw) == 6864 and raw[:8] == b'FPSHC01\0', 'diagnostic bank schema/size')
    shape.require(struct.unpack('<3Q', raw[8:32]) == (6368, 408, 56), 'diagnostic host ABI')
    derived = b'FPSH001\0' + raw[8:]
    with destination.open('xb') as f:
        f.write(derived); f.flush(); os.fsync(f.fileno())
    shape.require(destination.read_bytes() == derived and source.read_bytes() == raw, 'adapter preservation')
    return {'schema':'mumble_diagnostic_bank_adapter_v1', 'source':str(source.relative_to(ROOT))
            if source.is_relative_to(ROOT) else str(source), 'source_identity':expected,
            'derived_identity':runner.identity(destination),
            'changed_byte_offsets':[i for i,(a,b) in enumerate(zip(raw,derived)) if a != b],
            'payload_bytes_8_onward_identical':True, 'strict_parity_certified':False,
            'semantics':SEMANTICS}


def run(qualification, publication):
    plan = shape.load(HERE/'plan.json')
    qualified, published = shape.load(qualification), shape.load(publication)
    bound = sources()
    shape.require(qualified['status']=='passed' and qualified['sources']==bound, 'qualification gate')
    revision = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    shape.require(published['status']=='verified_remote' and published['sources']==bound
                  and published['revision']==revision, 'publication gate')
    binary = qualification.parent/'bridge'
    shape.require(runner.identity(binary)==qualified['binary'], 'qualified binary identity')
    for spec in plan['inputs'].values():
        shape.require(runner.identity(ROOT/spec['path'])=={k:spec[k] for k in ('bytes','sha256')},
                      'input identity: '+spec['path'])
    census = shape.load(ROOT/plan['inputs']['census_summary']['path'])
    shape.require(census['status']=='complete_inventory' and census['snapshots']==15751,
                  'census incomplete')
    runner.save(HERE/'scientific_reservation.json', {
        'source_revision':revision,'sources':bound,'metric_invocations':1,'comparison_invocations':1,
        'retries':0,'prefix_replay_invocations':0,'finite_caps':plan['finite_caps'],
        'qualification':runner.identity(qualification),'publication':runner.identity(publication)})
    out=HERE/'attempt001'; out.mkdir()
    budget=runner.Budget(out)
    result={'schema':'mumble_joint_shape_execution_v1','status':'unresolved','source_revision':revision,
            'sources':bound,'semantics':SEMANTICS,'metric_invocations':0,'comparison_invocations':0,
            'prefix_replay_invocations':0,'optimizer_calls':0,'truth_reads':0,'retries':0}
    try:
        bank=plan['inputs']['diagnostic_bank']; snapshot=out/'adapter.bank.bin'
        adapter=adapt_bank(ROOT/bank['path'],snapshot,{k:bank[k] for k in ('bytes','sha256')})
        runner.save(out/'adapter.json',adapter)
        result['metric_invocations']=1
        log=budget.run([str(binary),'metric',str(snapshot)],'metric')
        c=json.loads(log.read_text())
        shape.require(c['kind']=='metric' and c['prefix']==shape.PREFIX and c['model_steps']==0
                      and c['query_evaluations']==1 and c['prior_evaluations']==1, 'metric contract')
        c.update(schema='mumble_census_bank_geometry_v1',semantics=SEMANTICS,
                 diagnostic_bank=bank,adapter=runner.identity(out/'adapter.json'))
        runner.save(out/'geometry.json',c)
        design=shape.make_design(c['anchor'],shape.unpack_metric(c['metric_packed_lower']),
                                c['public_sd'],c['lower'],c['upper'],c['charge_min_Ah'],
                                c['charge_max_Ah'],c['charge_Ah'])
        design.update(geometry_sha256=shape.file_sha(out/'geometry.json'),
                      snapshot_sha256=shape.file_sha(snapshot),semantics=SEMANTICS,
                      common_prior_source_sha256=shape.PRIOR_SHA)
        runner.save(out/'nodes.json',design)
        with (out/'nodes.bin').open('xb') as f:
            for node in design['nodes']: f.write(struct.pack('<16d',*node['x']))
            f.flush(); os.fsync(f.fileno())
        freeze={name:runner.identity(out/name) for name in
                ('adapter.bank.bin','adapter.json','geometry.json','nodes.json','nodes.bin')}
        runner.save(out/'nodes_frozen.json',{'files':freeze,'reference_calls':0,
                    'adaptive_radius_after_comparison':False,'semantics':SEMANTICS})
        shape.require(sources()==bound and runner.identity(binary)==qualified['binary'], 'source/binary changed')
        result['comparison_invocations']=1
        obs=ROOT/plan['inputs']['observations']['path']
        log=budget.run([str(binary),'evaluate',str(obs),str(snapshot),str(out/'nodes.bin'),
                       str(shape.NODE_COUNT),str(shape.PREFIX)],'comparison')
        rows=[json.loads(line) for line in log.read_text().splitlines()]; terminal=rows.pop()
        shape.require(terminal['kind']=='terminal' and terminal['nodes']==545 and len(rows)==545,
                      'comparison incomplete')
        shape.require(terminal['model_steps']<=137340000 and terminal['predict_calls']<=137340000
                      and terminal['represented_queries']==545 and terminal['optimizer_calls']==0
                      and terminal['prior_calls']==0 and terminal['truth_reads']==0,'work contract')
        for k,row in enumerate(rows):
            shape.require(row['kind']=='node' and row['index']==k and row['x']==design['nodes'][k]['x'],
                          'frozen node identity')
            row['id']=design['nodes'][k]['id']
        shape.require(all(runner.identity(out/n)==v for n,v in freeze.items()),'frozen files changed')
        for spec in plan['inputs'].values():
            shape.require(runner.identity(ROOT/spec['path'])=={k:spec[k] for k in ('bytes','sha256')},
                          'input changed during comparison')
        shape.require(sources()==bound and runner.identity(binary)==qualified['binary'],'source/binary changed')
        ev={'schema':'mumble_fixed_prefix_evaluations_v1','design_sha256':shape.file_sha(out/'nodes.json'),
            'snapshot_sha256':shape.file_sha(snapshot),'prefix':shape.PREFIX,'observations_sha256':shape.OBS_SHA,
            'common_prior_source_sha256':shape.PRIOR_SHA,'closed':True,'rows':rows,'work':terminal,
            'semantics':SEMANTICS}
        runner.save(out/'evaluations.json',ev)
        analysis=shape.compare(design,rows)
        analysis.update(design_sha256=shape.file_sha(out/'nodes.json'),
                        evaluations_sha256=shape.file_sha(out/'evaluations.json'),semantics=SEMANTICS)
        runner.save(out/'analysis.json',analysis)
        result.update(status='completed',decision=analysis['decision'],work=terminal)
        budget.check()
    except BaseException as exc:
        result.update(status='unresolved',error=type(exc).__name__+': '+str(exc))
    finally:
        result.update(children=budget.children,CPU_s=budget.used_cpu(),wall_s=time.monotonic()-budget.started,
                      supervisor_peak_RSS_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
                      closed_files={p.name:runner.identity(p) for p in out.iterdir() if p.is_file()})
        runner.save(out/'receipt.json',result)
    print(json.dumps({k:result[k] for k in ('status','metric_invocations','comparison_invocations')}))
    return int(result['status']!='completed')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--qualification',type=Path,required=True)
    p.add_argument('--publication',type=Path,required=True)
    args=p.parse_args()
    signal.signal(signal.SIGTERM,lambda *_: (_ for _ in ()).throw(InterruptedError('SIGTERM')))
    sys.exit(run(args.qualification.resolve(),args.publication.resolve()))
