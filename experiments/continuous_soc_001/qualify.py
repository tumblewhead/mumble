"""Transport analysis before long replay. No precision tuning or large sweep."""
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time
import numpy as np
from .history import Operator,History,encode_log
from .oracle import Paths
from experiments.joint_mass_codebook_001 import fixtures,model as old
from experiments.structured_joint_001.qualify import Checks,ident,write

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]


def main():
    out=Path(sys.argv[1]) if len(sys.argv)>1 else HERE/'qualification001';out.mkdir(parents=True,exist_ok=False)
    previous=json.loads((ROOT/'experiments/joint_mass_codebook_001/verification.json').read_text())
    older=json.loads((ROOT/'experiments/joint_mass_codebook_001/attempt001/reservation.json').read_text())['preserved_artifacts']
    preserved={**older,**previous['artifacts'],'experiments/joint_mass_codebook_001/verification.json':ident(ROOT/'experiments/joint_mass_codebook_001/verification.json')}
    for p,e in preserved.items():
        if ident(ROOT/p)!=e:raise ValueError('previous evidence changed: '+p)
    files=list(HERE.glob('*.py'))+[HERE/'plan.json',HERE/'analysis.md']
    files+=[ROOT/p for p in ['experiments/joint_mass_codebook_001/model.py','experiments/joint_mass_codebook_001/fixtures.py',
                            'experiments/structured_joint_001/qualify.py']]
    sources={str(p.relative_to(ROOT)):ident(p) for p in files}
    for p in files:
        target=out/'source_snapshot'/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    write(out/'reservation.json',dict(source_identities=sources,preserved_artifacts=preserved,command=sys.argv,
          source_revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
          branch=subprocess.check_output(['git','branch','--show-current'],text=True).strip()))
    c=Checks();reports=[];started=time.process_time()
    # A deterministic shift creates no real variance; grid deposition creates
    # h^2*f*(1-f). Check the mechanism independently of the complete filter.
    for h in [1/16,1/32,1/64]:
        for f in [.1,.4,.8]:
            nodes=np.array([0.,h]);w=np.array([1-f,f]);mu=w@nodes
            c.close(f'grid injected variance/{h}/{f}',w@(nodes-mu)**2,h*h*f*(1-f))
    for name in fixtures.HELD_OUT:
        for scale in fixtures.PROFILE_SCALES:
            operator=Operator(name,scale);history=History(name);oracle=Paths(name)
            grid=old.Model(17,scale);p=grid.prior.copy();rows=[]
            for frame in fixtures.frames(name):
                op=operator.prepare(frame,name);history.step(op);oracle.step(op)
                grid_op=grid.prepare(frame);p,_,_=old.observe(old.predict(p,grid_op),grid_op)
                actual=history.readout(op);ref=oracle.readout(op);grid_queries=old.moments(p,grid_op)
                qe=100*(actual['Q']-ref['Q'])/ref['Q'];ze=100*(actual['SOC']-ref['SOC'])
                c.check(f'practical Q transport/{name}/{scale}/{frame.index}',abs(qe)<=.5,Q_error_percent=qe)
                c.check(f'practical SOC transport/{name}/{scale}/{frame.index}',abs(ze)<=.5,SOC_error_pp=ze)
                c.check(f'finite variance/{name}/{scale}/{frame.index}',np.isfinite(history.variance).all() and np.min(history.variance)>=0)
                rows.append(dict(index=frame.index,continuous=actual,oracle=ref,old_grid=grid_queries,
                                 continuous_Q_error_percent=qe,continuous_SOC_error_pp=ze,
                                 grid_Q_error_percent=100*(grid_queries['Q']-ref['Q'])/ref['Q'],
                                 grid_SOC_error_pp=100*(grid_queries['soc']-ref['SOC'])))
            reports.append(dict(fixture=name,aging_scale=scale,steps=rows))
    # The stationary deterministic limit has no mixing variance to accumulate.
    operator=Operator('translation',0.);history=History('translation');initial=history.variance.copy()
    for k in range(256):
        frame=old.Frame(k,1/35,.02 if k%2 else -.02,25,3.7,.04)
        history.step(operator.prepare(frame,'translation'))
    c.close('no artificial variance under repeated translation',history.variance,initial,atol=0,rtol=0)
    c.reject('duplicate history source rejects',lambda:history.step(operator.prepare(old.Frame(255,1/35,0,25,3.7),'translation')))
    c.reject('wrong source rejects',lambda:operator.prepare(old.Frame(256,1/35,0,25,3.7),'foreign'))
    # Atomic representation failure: do not drop tiny tails or replace prior.
    h=History('range',encoding='log16');h.logw.flat[0]=-1e5
    op=Operator('range',0.).prepare(old.Frame(0,0,0,25,3.7),'range');saved=h.logw.copy()
    c.reject('fixed range explicitly rejects',lambda:h.step(op))
    c.check('range failure does not advance',h.next_index==0 and np.array_equal(h.logw,saved))
    for kind in ['float32','log16']:
        decoded,packet,error=encode_log(np.array([0.,-1.,-50.]),kind)
        c.check('encoding idempotence/'+kind,encode_log(decoded,kind)[1]==packet)
    for p,e in sources.items():c.check('source identity/'+p,ident(ROOT/p)==e)
    for p,e in preserved.items():
        if ident(ROOT/p)!=e:c.check('previous evidence changed/'+p,False)
    result=dict(status='passed' if all(x['passed'] for x in c.items) else 'failed',passing_checks=sum(x['passed'] for x in c.items),
                failed_checks=[x for x in c.items if not x['passed']],checks=c.items,cases=reports,cpu_seconds=time.process_time()-started,
                preserved_earlier_artifacts=len(preserved),scope='Continuous moment transport vs unmerged continuous paths on frozen prefixes; local first-order likelihood and shape approximation remain explicit')
    write(out/'result.json',result);print(json.dumps({k:result[k] for k in ['status','passing_checks','failed_checks','cpu_seconds']}))
    if result['failed_checks']:raise SystemExit(1)


if __name__=='__main__':main()
