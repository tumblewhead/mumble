"""Registered two-case24/72h diagnostic; compact caches, no new campaign."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    root=Path(__file__).resolve().parents[2]
    source=Path('/home/easy/proj/mumble/.worktrees/rolling-joint-field')
    campaign=source/'experiments/foster_campaign_001/run_20261031_182600_810547'
    env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','PYTHONDONTWRITEBYTECODE':'1'}
    for seed,case in ((1100,'case_0000'),(1103,'case_0002')):
        inputs=out/f'inputs{seed}'
        subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('regenerate.py')),
            '--source-root',str(source),'--case',str(campaign/case),'--out',str(inputs),'--hours','24','72'],cwd=root,env=env,check=True)
        for entry in json.loads((inputs/'validated.json').read_text())['selected']:
            n=entry['sequence']
            subprocess.run([sys.executable,'-B','-m','experiments.shared_uncertainty_growth_001.audit',
                '--inputs',str(inputs),'--sequence',str(n),'--out',str(out/f'audit{seed}_{n}')],cwd=root,env=env,check=True)

if __name__=='__main__':main()
