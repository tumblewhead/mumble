#!/usr/bin/env python3
"""Frozen once-only scaling campaign; independent probes, gated inference."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from common import HERE,ROOT,runner,save
import numpy as np


def sources():
    names=[str(p.relative_to(ROOT)) for p in sorted(HERE.glob('*.py'))]
    names += [str((HERE/'plan.json').relative_to(ROOT))]
    names += ['experiments/joint_health_posterior_001/'+n for n in ('model.py','smc.py','posterior.py')]
    names += ['experiments/minimal_health_kernels_001/kernel.py',
              'experiments/fixed_prefix_shape_001/runner.py','experiments/fixed_prefix_shape_001/shape.py']
    return {n:runner.identity(ROOT/n) for n in names}


def main(out):
    out.mkdir(parents=True)
    plan=json.loads((HERE/'plan.json').read_text());bound=sources();caps=plan['caps']
    for name in bound:
        dest=out/'source_snapshot'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
    save(out/'manifest.json',dict(base_revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        sources=bound,python=platform.python_version(),numpy=np.__version__,
        source_binding='Working source snapshots and hashes; inherited solver unchanged',
        command=[sys.executable,'-B',str(HERE/'run.py'),str(out)]))
    budget=runner.Budget(out,cpu=caps['CPU_s'],wall=caps['wall_s'],rss=caps['RSS_bytes'],output=caps['output_bytes'])
    results=[];probes=[];status='execution_failed';reason=None;active=None
    try:
        inputs=out/'inputs'
        budget.run([sys.executable,'-B',str(HERE/'generate.py'),str(inputs)],'generate')
        budget.run([sys.executable,'-B',str(HERE/'qualify.py'),str(out/'qualification'),str(inputs)],'qualify')
        for n in plan['prefixes']:
            active=('probe',n)
            dest=out/f'probe_{n}'
            budget.run([sys.executable,'-B',str(HERE/'worker.py'),'probe',str(n),str(inputs),str(dest)],f'probe_{n}')
            probes.append(json.loads((dest/'result.json').read_text()))
            if probes[-1]['status']!='completed_cost_probe_only':raise RuntimeError('cost probe failed')
        for n in plan['prefixes']:
            active=('posterior',n)
            dest=out/f'prefix_{n}'
            budget.run([sys.executable,'-B',str(HERE/'worker.py'),'posterior',str(n),str(inputs),str(dest)],f'prefix_{n}')
            result=json.loads((dest/'result.json').read_text());results.append(result)
            if result['status']!='finite_moment_checks_passed':
                status='closed_at_numerical_or_resource_limit';reason=dict(prefix=n,status=result['status']);break
        else:status='completed_all_registered_prefixes'
        if sources()!=bound:raise RuntimeError('source changed during campaign')
        budget.check()
    except Exception as exc:
        reason=dict(active=active,error=type(exc).__name__+': '+str(exc))
        status='closed_at_supervisor_or_execution_limit'
        # Include an explicit interrupted prefix, retaining any populations that
        # were already written, without inventing a posterior summary.
        if active is not None and active[0]=='posterior' and all(r['prefix']!=active[1] for r in results):
            dest=out/f'prefix_{active[1]}'
            results.append(dict(prefix=active[1],status='interrupted_uncertainty_unresolved',
                                saved_population_files=len(list(dest.glob('population_*.npz')))))
    launched={r['prefix'] for r in results}
    for n in plan['prefixes']:
        if n not in launched:results.append(dict(prefix=n,status='not_launched_by_gate'))
    report=dict(status=status,stop_reason=reason,prefix_results=results,cost_probes=probes,
        children=budget.children,CPU_s=budget.used_cpu(),sources_unchanged=sources()==bound,
        automatic_retries=0,independent_review=False,output_bytes_before_receipt=budget.output_bytes(),
        total_conservative_completed_worker_steps=sum(r.get('work',{}).get('conservative_steps',0) for r in results+probes),
        interrupted_work_scope='If a supervisor interruption occurred, completed worker counters are a lower bound; process CPU/RSS covers interrupted work too')
    save(out/'receipt.json',report)
    print(json.dumps(dict(status=status,stop_reason=reason,prefixes=[{'prefix':r['prefix'],'status':r['status']} for r in results],CPU_s=report['CPU_s']),indent=2))
    return 0 if status in ('completed_all_registered_prefixes','closed_at_numerical_or_resource_limit') else 1


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1]).resolve()))
