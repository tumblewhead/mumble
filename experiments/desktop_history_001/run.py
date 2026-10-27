#!/usr/bin/env python3
"""Bounded fidelity test followed by a separate public-start prefix learner."""
import json
from pathlib import Path
import subprocess
import sys
import desktop as d

def main(qpath):
    q=d.load(qpath);plan=d.load(d.HERE/'plan.json');bound=d.sources()
    assert q['status']=='passed' and q['sources']==bound
    binary=qpath.parent/'replay.so';assert d.runner.identity(binary)==q['binary']
    for v in plan['inputs'].values():assert d.runner.identity(d.ROOT/v['path'])=={k:v[k] for k in ('bytes','sha256')}
    out=d.HERE/'attempt001';out.mkdir();budget=d.runner.Budget(out,cpu=600,wall=900,rss=536870912)
    receipt={'status':'unresolved','sources':bound,'source_revision':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
             'qualification':d.runner.identity(qpath),'inputs':plan['inputs'],'arms':{}}
    d.runner.save(out/'reservation.json',{'plan':d.runner.identity(d.HERE/'plan.json'),'sources':bound,'retries':0})
    try:
        for mode in ('fidelity','causal'):
            sub=out/mode;sub.mkdir()
            budget.run([sys.executable,'-B',str(d.HERE/'desktop.py'),mode,str(binary),str(sub)],mode)
            result=d.load(sub/'result.json');receipt['arms'][mode]=result
            if mode=='fidelity':assert result['available_nodes']==545 and result['decision']=='keep_on_tested_points_only','fidelity gate'
        assert d.sources()==bound and d.runner.identity(binary)==q['binary']
        receipt['status']='completed';budget.check()
    except BaseException as exc:receipt['error']=type(exc).__name__+': '+str(exc)
    finally:
        receipt.update(children=budget.children,CPU_s=budget.used_cpu(),
            files={str(p.relative_to(out)):d.runner.identity(p) for p in out.rglob('*') if p.is_file()})
        d.runner.save(out/'receipt.json',receipt)
    print(json.dumps({'status':receipt['status'],'error':receipt.get('error')}))
    if receipt['status']!='completed':raise SystemExit(1)

if __name__=='__main__':main(Path(sys.argv[1]).resolve())
