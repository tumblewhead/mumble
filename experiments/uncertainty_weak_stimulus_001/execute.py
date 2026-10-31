"""Reproduce the five registered Stage-1 cases; never launches long sweeps."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--labels',nargs='+',help='optional subset of registered cases')
    args=p.parse_args()
    root=Path(__file__).resolve().parents[2]
    plan=json.loads((root/'specifications/uncertainty_weak_stimulus_001/plan.json').read_text())
    cases=plan['stage1']['cases'];known={c['label'] for c in cases}
    if args.labels and set(args.labels)-known:p.error('unknown registered case label')
    cases=[c for c in cases if args.labels is None or c['label'] in args.labels]
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','PYTHONDONTWRITEBYTECODE':'1',
         'MPLCONFIGDIR':'/tmp/mumble-uncertainty-mpl'}
    commands=[]
    for c in cases:
        campaign=Path(c['source_campaign'])
        command=[sys.executable,'-B',str(Path(__file__).with_name('regenerate.py')),
                 '--source-root',str(campaign.parents[2]),'--case',str(campaign/c['source_case']),
                 '--out',str(out/'inputs'/c['label'])]
        if c['label']=='weak_B_cycle':command.append('--weak')
        commands.append(command)
    commands.append([sys.executable,'-B','-m','experiments.uncertainty_weak_stimulus_001.run',
                     '--inputs',str(out/'inputs'),'--out',str(out/'diagnostics'),
                     '--labels',*[c['label'] for c in cases]])
    commands.append([sys.executable,'-B','-m','experiments.uncertainty_weak_stimulus_001.postfit',
                     '--inputs',str(out/'inputs'),'--diagnostics',str(out/'diagnostics'),'--out',str(out/'scoring')])
    (out/'commands.json').write_text(json.dumps(dict(commands=commands,plan_status='Stage1 only'),indent=2)+'\n')
    for command in commands:subprocess.run(command,cwd=root,env=env,check=True)


if __name__=='__main__':main()
