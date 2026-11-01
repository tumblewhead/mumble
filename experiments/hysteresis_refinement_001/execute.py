"""Reproduce the registered matched refinements from existing validated caches."""
import argparse
import os
from pathlib import Path
import subprocess
import sys


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False);root=Path(__file__).resolve().parents[2]
    env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','PYTHONDONTWRITEBYTECODE':'1'}
    runs=[]
    def call(module,*args):subprocess.run([sys.executable,'-B','-m','experiments.hysteresis_refinement_001.'+module,*map(str,args)],cwd=root,env=env,check=True)
    for seed in (1100,1103):
        run=out/f'seed{seed}';runs.append(run)
        call('run','--seed',seed,'--out',run)
        call('ablation','--seed',seed,'--run',run,'--out',out/f'ablation{seed}')
    call('postfit','--runs',*runs,'--out',out/'scoring')

if __name__=='__main__':main()
