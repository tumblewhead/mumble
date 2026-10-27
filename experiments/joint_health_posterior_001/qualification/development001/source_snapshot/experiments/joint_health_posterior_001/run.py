#!/usr/bin/env python3
"""Exclusive source-frozen qualification supervisor; no automatic retry."""
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE.parent/'fixed_prefix_shape_001'))
import runner
import numpy as np


def main(out):
    out.mkdir(parents=True)
    names=[str(p.relative_to(ROOT)) for p in sorted(HERE.glob('*.py'))]
    names += [str((HERE/'plan.json').relative_to(ROOT)),
        'experiments/minimal_health_kernels_001/kernel.py','experiments/minimal_health_kernels_001/path.py',
        'specifications/minimal_health_model_001/model.json','experiments/fixed_prefix_shape_001/runner.py',
        'experiments/fixed_prefix_shape_001/shape.py']
    sources={n:runner.identity(ROOT/n) for n in names}
    for n in names:
        dest=out/'source_snapshot'/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,dest)
    manifest=dict(base_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        source_binding='Working source SHA256 and snapshots; base revision is not implementation commit',
        sources=sources,python=platform.python_version(),numpy=np.__version__,
        command=[sys.executable,'-B',str(HERE/'qualify.py'),str(out)])
    runner.save(out/'manifest.json',manifest)
    caps=json.loads((HERE/'plan.json').read_text())['caps']
    budget=runner.Budget(out,cpu=caps['CPU_s'],wall=caps['wall_s'],rss=caps['RSS_bytes'],output=caps['output_bytes'])
    receipt=dict(status='failed',automatic_retries=0,independent_review=False)
    try:
        budget.run(manifest['command'],'qualification')
        if {n:runner.identity(ROOT/n) for n in names} != sources:raise RuntimeError('source mutation')
        checks=json.loads((out/'checks.json').read_text())
        budget.check()
        receipt.update(status='passed',checks=checks['checks'],cases=len(checks['cases']))
    except Exception as exc:receipt['error']=type(exc).__name__+': '+str(exc)
    receipt.update(children=budget.children,CPU_s=budget.used_cpu(),
        sources_unchanged={n:runner.identity(ROOT/n) for n in names}==sources,output_bytes_before_receipt=budget.output_bytes())
    runner.save(out/'receipt.json',receipt)
    print(json.dumps(receipt,indent=2))
    return 0 if receipt['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1]).resolve()))
