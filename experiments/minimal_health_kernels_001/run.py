#!/usr/bin/env python3
"""Freeze and supervise one finite qualification; never overwrite or retry."""
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent/'fixed_prefix_shape_001'))
import runner
import numpy as np


def main(out):
    out.mkdir(parents=True)
    names = [str(p.relative_to(ROOT)) for p in sorted(HERE.glob('*.py'))]
    names += [str((HERE/'plan.json').relative_to(ROOT)),
              'specifications/minimal_health_model_001/model.json',
              'specifications/minimal_health_model_001/test_profiles.json',
              'experiments/live_anchor_integration_001/qualification/independent_oracle.py',
              'experiments/live_anchor_integration_001/public_contract.c',
              'experiments/fixed_prefix_shape_001/runner.py',
              'experiments/fixed_prefix_shape_001/shape.py']
    sources = {n: runner.identity(ROOT/n) for n in names}
    for n in names:
        dest = out/'source_snapshot'/n
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/n, dest)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    manifest = dict(base_revision=revision, sources=sources, python=platform.python_version(),
                    numpy=np.__version__, command=[sys.executable, '-B', str(HERE/'qualify.py'), str(out/'checks.json')],
                    source_binding='Working source snapshots + SHA256; base revision is not an implementation commit')
    runner.save(out/'manifest.json', manifest)
    budget = runner.Budget(out, cpu=120, wall=180, output=16777216, rss=268435456)
    result = dict(status='failed', automatic_retries=0, independent_review=False)
    try:
        budget.run(manifest['command'], 'qualification')
        if {n: runner.identity(ROOT/n) for n in names} != sources:
            raise RuntimeError('source changed during qualification')
        checks = json.loads((out/'checks.json').read_text())
        if checks['activity']['physical_steps']+checks['oracle_activity']['AD_steps'] > 200000:
            raise RuntimeError('kernel step cap')
        if checks['posterior_quadrature_evaluations'] > 200000:
            raise RuntimeError('posterior quadrature cap')
        budget.check()
        result.update(status='passed', checks=checks['checks'], cases=len(checks['cases']))
    except Exception as exc:
        result['error'] = type(exc).__name__+': '+str(exc)
    result.update(children=budget.children, CPU_s=budget.used_cpu(),
                  sources_unchanged={n: runner.identity(ROOT/n) for n in names} == sources,
                  output_bytes_before_receipt=budget.output_bytes())
    runner.save(out/'receipt.json', result)
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main(Path(sys.argv[1]).resolve()))
