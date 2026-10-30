"""Bounded evaluation-order diagnostic; primary receipt remains untouched."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
import json
from pathlib import Path
import sys
import time
import numpy as np
from analyze import ROOT,HERE,OLD,FIXED,PREV,Harness,ptr,identity,save,ResponseBasis,Partition,dynamic_rows
from kernel import FreeHistory


def run(out):
    out.mkdir(parents=True,exist_ok=False);start=time.monotonic()
    primary=json.loads((HERE/'attempt001/reservation.json').read_text())
    paths=[ROOT/k for k in primary['sources']]+[HERE/'arithmetic.py',HERE/'arithmetic_plan.json',HERE/'attempt001/receipt.json']
    bindings={str(p.relative_to(ROOT)):identity(p) for p in paths}
    assert all(identity(ROOT/k)==v for k,v in primary['sources'].items())
    save(out/'reservation.json',dict(plan=json.loads((HERE/'arithmetic_plan.json').read_text()),sources=bindings,command=sys.argv,
        revision=primary['revision'],branch=primary['branch']))
    h=Harness(OLD/'comparison001/provider.so');inp=json.loads((FIXED/'comparison002/frozen_inputs.json').read_text());rows=[]
    for raw in inp['raw_cycle']:
        row=np.zeros(3);assert h.lib.hp_decode(*raw,ptr(row))==0;rows.append(row)
    obs=np.tile(rows,(inp['repeat_count'],1))[:4096];elapsed=np.cumsum(obs[:,0]);charges=np.cumsum(obs[:,0]*obs[:,1]/3600)
    lower=np.array(inp['lower']);upper=np.array(inp['upper']);points=np.array(inp['queries'])
    limits=[(upper[11]-1)*np.exp(lower[5]),lower[11]*np.exp(lower[5])];cases=[]
    def comparison(a,b):
        gap=abs(a-b);ratio=gap/(2e-8+2e-10*abs(b))
        return dict(max_abs_gap=float(gap.max()),max_allowance_ratio=float(ratio.max()),failed_entries=int(np.sum(ratio>1)))
    for domain in ['public_half_SD','full_public']:
        basis=ResponseBasis(dict(physical_RC=False,physical_hysteresis=True,tensor_hysteresis=False),domain,h.mean,h.sd,lower,upper)
        full=basis.rows(obs);p=Partition(basis,12,limits);ids=[i for i,x in enumerate(points) if p.query(x) is not None]
        old=np.column_stack((dynamic_rows(basis,full,obs),p.charge_rows(charges)[:,:p.k]))
        for family in ['baseline','time_kernel_K9_all_three']:
            if family=='baseline':design=old;query=p.query
            else:
                bank=FreeHistory(p,'time_kernel','all_three',9);design=bank.rows(old,elapsed);query=bank.query
            queries=[query(points[i]) for i in ids];v=np.stack([q[0] for q in queries]);jac=np.stack([q[1] for q in queries])
            qr=np.linalg.qr(design,mode='r');merged=np.linalg.qr(np.vstack((np.linalg.qr(design[:17],mode='r'),np.linalg.qr(design[17:],mode='r'))),mode='r')
            direct=v@design.T;encoded=v@qr.T
            gd=np.einsum('qf,qfj->qj',direct@design,jac);gq=np.einsum('qf,qfj->qj',encoded@qr,jac)
            gap=abs(gd-gq);ratio=gap/(2e-8+2e-10*abs(gd))
            witnesses=sorted({0,int(np.unravel_index(np.argmax(gap),gap.shape)[0]),int(np.unravel_index(np.argmax(ratio),gap.shape)[0])})
            rd=[];rq=[];rm=[]
            for vv,jj in queries:
                rd.append((design@jj).T@(design@vv));rq.append((qr@jj).T@(qr@vv));rm.append((merged@jj).T@(merged@vv))
            rd=np.array(rd);rq=np.array(rq);rm=np.array(rm);extended=[]
            dld=design.astype(np.longdouble)
            for i in witnesses:
                vv,jj=queries[i];truth=(dld@jj.astype(np.longdouble)).T@(dld@vv.astype(np.longdouble))
                extended.append(dict(query_index=ids[i],reference='long-double represented rows; not physical truth',
                    primary_direct=comparison(gd[i],truth),primary_QR=comparison(gq[i],truth),
                    residual_direct=comparison(rd[i],truth),residual_QR=comparison(rq[i],truth),residual_merged=comparison(rm[i],truth)))
            cases.append(dict(domain=domain,family=family,query_count=len(ids),primary=comparison(gq,gd),
                residual_QR_vs_direct=comparison(rq,rd),residual_merged_vs_QR=comparison(rm,rq),extended=extended))
            print(json.dumps(cases[-1]),flush=True)
    assert all(identity(ROOT/k)==v for k,v in bindings.items())
    passed=all(c[key]['failed_entries']==0 for c in cases for key in ['residual_QR_vs_direct','residual_merged_vs_QR'])
    save(out/'receipt.json',dict(status='followup_controls_passed' if passed else 'followup_mismatches_retained',cases=cases,
        source_hashes_unchanged=True,model_steps_upper=532480,primary_modified=False,wall_s=time.monotonic()-start))


if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('usage: arithmetic.py EXCLUSIVE_OUTPUT_DIRECTORY')
    run(Path(sys.argv[1]).resolve())
