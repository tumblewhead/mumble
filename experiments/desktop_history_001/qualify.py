#!/usr/bin/env python3
"""Fabricated independent physical recurrence/AD qualification."""
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import sys
import numpy as np
import desktop as d

def main(out):
    out.mkdir(parents=True);bound=d.sources();budget=d.runner.Budget(out,cpu=120,wall=180)
    for name in ('replay.c','desktop.py','qualify.py','run.py','plan.json'):
        dest=out/'source_snapshot'/name;dest.parent.mkdir(exist_ok=True);shutil.copyfile(d.HERE/name,dest)
    result={'status':'failed','sources':bound,'checks':0,'canonical_input_reads':0,'independent_reviewer':False}
    def check(ok,label):
        if not ok:raise AssertionError(label)
        result['checks']+=1
    def close(a,b,label,atol=1e-7,rtol=2e-9):
        check(np.allclose(a,b,atol=atol,rtol=rtol),label)
    try:
        binary=out/'replay.so';budget.run(d.build(binary),'build');r=d.Replay(binary)
        path=d.HERE.parent/'live_anchor_integration_001/qualification/independent_oracle.py'
        spec=importlib.util.spec_from_file_location('oracle',path);ad=importlib.util.module_from_spec(spec);spec.loader.exec_module(ad)
        a=np.array([[.03,.07,3.7],[0.,-.02,3.71],[.04,-.08,3.72],[.2,0.,3.73],[.8,.12,3.69]])
        points=[r.mean.copy(),r.mean.copy(),r.mean.copy()]
        points[1][10]=0;points[1][15]=-.7;points[1][12:15]=[.01,-.02,.03]
        points[2][7:10]=0;points[2][15]=.5
        for x in points:
            ev=r.evaluate(a,x);ref=ad.block_ad(x.tolist(),a.tolist(),.001)
            close(ev[0],ref['cost'].v,'physical cost')
            close(ev[1],ref['cost'].g,'all original-coordinate gradients')
            close(ev[2],np.array(ref['GN']).reshape(16,16),'GN metric')
            last=ref['rows'][-1];end=[last['SOC'].v]+[v.v for v in last['v']]+[last['h'].v]
            close(ev[3],end,'carried endpoint',atol=1e-12)
            prior,metric=ad.public_prior_ad(x.tolist());p,g,h=r.prior(x)
            close(p,prior.v,'mixture prior');close(g,prior.g,'prior gradient');close(np.diag(h),metric,'majorizer')
            for k in range(16):
                xp=x.copy();xm=x.copy();eps=1e-6*r.sd[k];xp[k]+=eps;xm[k]-=eps
                if xm[k]<r.lower[k] or xp[k]>r.upper[k]:continue
                close((r.evaluate(a,xp,False)[0]-r.evaluate(a,xm,False)[0])/(2*eps),ev[1][k],
                      'finite difference '+str(k),atol=.01,rtol=2e-5)
        raw=b''.join(struct.pack('<Qddd',i,*row) for i,row in enumerate(a))
        decoded=r.decode(raw,0);close(decoded[:,0],a[:,0],'actual intervals',atol=1e-8)
        try:r.decode(raw,1)
        except ValueError:check(True,'source order rejected')
        else:check(False,'source order accepted')
        close(r.decode(raw[:64],0),decoded[:2],'prefix decoder')
        xa=r.mean.copy();xa[11]=2;check(r.evaluate(a,xa) is None,'support reject')
        bad=a.copy();bad[0,2]=np.nan;check(r.evaluate(bad,r.mean) is None,'nonfinite reject')
        same=r.evaluate(a,r.mean);long=np.vstack([a,a]);r.evaluate(long,points[1]);again=r.evaluate(a,r.mean)
        for x,y in zip(same,again):check(np.array_equal(x,y),'queries have no state leakage')
        close(r.evaluate(np.empty((0,3)),r.mean)[0],0.,'empty likelihood')
        # Fabricated observations generated from public parameters, used only
        # to test the optimizer; neither canonical truth nor fitted targets.
        fabricated=np.array([[.1,(-1)**i*.08,3.7] for i in range(40)])
        volts=ad.block_scalar(r.mean.tolist(),fabricated.tolist(),.001)['voltage'];fabricated[:,2]=volts
        start=r.mean.copy();start[6]+=.03;initial=r.evaluate(fabricated,start)[0]+r.prior(start)[0]
        fitted=d.fit(r,fabricated,start,30)
        check(fitted['total']<initial,'optimizer improves exact objective')
        check(all(not t['accepted'] or t['after_total']<t['total'] for t in fitted['iterations']),'accepted steps descend')
        check(d.sources()==bound,'source unchanged')
        result.update(status='passed',binary=d.runner.identity(binary),model_steps=r.steps)
    except BaseException as exc:
        result['error']=type(exc).__name__+': '+str(exc)
    finally:
        result.update(children=budget.children,CPU_s=budget.used_cpu())
        d.runner.save(out/'receipt.json',result)
    print(json.dumps({k:result[k] for k in ('status','checks')},sort_keys=True))
    if result['status']!='passed':raise SystemExit(result.get('error','failed'))

if __name__=='__main__':main(Path(sys.argv[1]).resolve())
