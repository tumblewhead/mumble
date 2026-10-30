"""Repeat an owner's campaign settings with repaired coordinates and a fresh output."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import shlex
import subprocess
import sys
from experiments.foster_campaign_001.run import parser as campaign_parser
ROOT=Path(__file__).resolve().parents[2]


def command(source,hours,jobs,out):
    config=json.loads((source/'campaign_plan.json').read_text())['configuration'].copy()
    config.update(hours=hours,jobs=jobs,hysteresis_chart='bounded',out=str(out))
    known={a.dest for a in campaign_parser()._actions}
    if set(config)-known:raise ValueError('Unknown saved campaign settings: '+str(sorted(set(config)-known)))
    args=[]
    for name,value in config.items():
        if value is None or value is False:continue
        args.append('--'+name.replace('_','-'))
        if value is True:continue
        args.extend(map(str,value if isinstance(value,list) else [value]))
    parsed=vars(campaign_parser().parse_args(args))
    for key,value in config.items():
        actual=parsed[key]
        if isinstance(actual,Path):actual=str(actual)
        if actual!=value:raise ValueError('Saved setting not preserved: '+key)
    return [sys.executable,'-B','-m','experiments.foster_campaign_001.run',*args]


def main():
    p=argparse.ArgumentParser();p.add_argument('source_run',type=Path);p.add_argument('--hours',type=float,default=196.);p.add_argument('--jobs',type=int,default=8);p.add_argument('--out',type=Path);p.add_argument('--dry-run',action='store_true');a=p.parse_args()
    source=a.source_run.resolve()
    out=a.out.resolve() if a.out else source.parent/('run_bounded_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f'))
    if out.exists():raise FileExistsError(out)
    cmd=command(source,a.hours,a.jobs,out)
    print('Output: '+str(out),flush=True);print(shlex.join(cmd),flush=True)
    if not a.dry_run:raise SystemExit(subprocess.run(cmd,cwd=ROOT).returncode)
if __name__=='__main__':main()
