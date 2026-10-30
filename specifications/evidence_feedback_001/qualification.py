"""Finite contract tests. All numeric/model fixtures live outside protocol.py."""
from dataclasses import replace, asdict
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import numpy as np
from .protocol import Binding, Boundary, EvidenceToken, FeedbackMessage, History, WindowOwnership, ContractError, digest
from experiments.incremental_history_001 import token as gaussian
from experiments.structured_joint_001.qualify import ident, write

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]


def pack(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def unpack(x):return json.loads(x.decode())


class GaussianFixture:
    """Exact declared Gaussian-family control, not a battery compressor."""
    def validate_message(self,payload):
        p=unpack(payload)
        if set(p)!={'mean','covariance','log_evidence'}:raise ContractError('fixture message schema')
        mean=np.array(p['mean']);cov=np.array(p['covariance'])
        if (mean.ndim!=1 or cov.shape!=(len(mean),len(mean)) or not np.isfinite(mean).all() or
            not np.isfinite(cov).all() or not math.isfinite(p['log_evidence']) or
            not np.allclose(cov,cov.T,rtol=0,atol=1e-14) or np.linalg.eigvalsh(cov).min()<-1e-14):
            raise ContractError('fixture invalid numeric message')

    def advance(self,prior,token):
        p=unpack(prior);k=unpack(token.payload);b=token.binding
        if set(k)!={'J','h','c','A','b','Q'}:raise ContractError('fixture requires likelihood/transport, not posterior')
        ctx=gaussian.Context(b.source_id,b.model_id,b.noise_id,b.calibration_id,b.dimension,b.tick_hz)
        g=gaussian.Token(ctx,gaussian.Boundary(token.entry.sequence,token.entry.ticks),
             gaussian.Boundary(token.exit.sequence,token.exit.ticks),0.,0.,
             np.array(k['J']),np.array(k['h']),k['c'],np.array(k['A']),np.array(k['b']),np.array(k['Q']))
        view=g.query(np.array(p['mean']),np.array(p['covariance']))
        return pack(dict(mean=view.mean.tolist(),covariance=view.covariance.tolist(),
                         log_evidence=p['log_evidence']+view.log_evidence))


def binding():
    names=['source','model','chart','noise','calibration','evolution','domain','representation']
    return Binding(*(digest(x) for x in names),dimension=2,tick_hz=1050)


def root(cov=None,backend=None,capacity=10000):
    p=pack(dict(mean=[0.,0.],covariance=([[1.,0.],[0.,1.]] if cov is None else cov),log_evidence=0.))
    return History(binding(),digest('public prior'),p,backend or GaussianFixture(),capacity,tier='exact_declared_family')


def kernel(head,first,last,H=None,y=None,ticks=None):
    b=head.binding;ctx=gaussian.Context(b.source_id,b.model_id,b.noise_id,b.calibration_id,2,b.tick_hz)
    # Independent static-state measurement factors with no process noise/drift.
    g=gaussian.identity(ctx,gaussian.Boundary(first,head.boundary.ticks))
    for i in range(first,last):
        matrix=np.array([[1.,.2+.1*(-1)**i]]) if H is None else np.array(H,dtype=float)
        observed=np.array([.1*(i+1)]) if y is None else np.array(y,dtype=float)
        end_ticks=g.exit.ticks+30 if ticks is None else ticks
        row=gaussian.observation(ctx,g.exit,end_ticks,0.,np.eye(2),np.zeros(2),np.zeros((2,2)),matrix,observed,np.eye(len(observed)))
        g=g.then(row)
    p={n:getattr(g,n).tolist() for n in ['J','h','A','b','Q']};p['c']=g.c
    return EvidenceToken(b,Boundary(g.entry.sequence,g.entry.ticks),Boundary(g.exit.sequence,g.exit.ticks),
                         head.message_id,pack(p),tier='exact_declared_family')


def main():
    out=Path(sys.argv[1]) if len(sys.argv)>1 else HERE/'qualification001';out.mkdir(parents=True,exist_ok=False)
    prev=ROOT/'experiments/system_history_001'
    preserved=unpack((prev/'campaign001/reservation.json').read_bytes())['preserved_artifacts']
    preserved.update(unpack((prev/'verification.json').read_bytes())['artifacts'])
    preserved[str((prev/'verification.json').relative_to(ROOT))]=ident(prev/'verification.json')
    for p,expected in preserved.items():
        if ident(ROOT/p)!=expected:raise ValueError('earlier artifact changed: '+p)
    files=list(HERE.glob('*.py'))+list(HERE.glob('*.json'))+list(HERE.glob('*.md'))
    files+=[ROOT/'experiments/incremental_history_001/token.py',ROOT/'experiments/structured_joint_001/qualify.py']
    sources={str(p.relative_to(ROOT)):ident(p) for p in files}
    for p in files:
        dest=out/'source_snapshot'/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    write(out/'reservation.json',dict(source_identities=sources,preserved_artifacts=preserved,command=sys.argv,
         source_revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
         branch=subprocess.check_output(['git','branch','--show-current'],text=True).strip()))
    checks=[]
    def check(name,ok):checks.append(dict(name=name,passed=bool(ok)))
    def close(name,a,b):check(name,np.allclose(a,b,rtol=2e-12,atol=2e-13))
    def reject(name,fn):
        try:fn()
        except (ValueError,TypeError):check(name,True)
        else:check(name,False)

    history=root();old=history.read();window=WindowOwnership(old)
    for i in range(8):window.offer(i)
    token=kernel(old,0,3);ticket=history.prepare(token,window.end)
    check('prepare does not publish',history.read()==old)
    check('prepare retry idempotent',history.prepare(token,window.end)==ticket)
    reject('different pending retirement rejected',lambda:history.prepare(kernel(old,0,2),window.end))
    receipt=history.commit(ticket);new=history.read()
    check('one root prior retained',new.root_prior_id==old.root_prior_id)
    check('committed owned prefix',new.boundary==Boundary(3,90) and new.generation==1)
    check('lost acknowledgement commit retry',history.commit(ticket)==receipt and history.read()==new)
    reject('new feedback plus old prefix prohibited',lambda:window.query_scope(new))
    window.acknowledge(receipt,new);window.acknowledge(receipt,new)
    check('acknowledge leaves suffix',window.query_scope(new)==(3,8))
    reject('old feedback rejected after acknowledgement',lambda:window.query_scope(old))
    reject('reappend committed evidence rejected',lambda:history.prepare(token,window.end))
    reject('duplicate rebranded with new feedback rejected',lambda:history.prepare(replace(token,base_feedback_id=new.message_id),window.end))
    reject('feedback is not evidence',lambda:history.prepare(new,window.end))
    reject('estimate view is not evidence',lambda:history.prepare({'kind':'EstimateView','Q':.06},window.end))
    reject('prior included flag rejected',lambda:replace(token,includes_root_prior=True))
    reject('feedback included flag rejected',lambda:replace(token,includes_feedback=True))
    reject('posterior payload rejected even with kernel label',lambda:history.prepare(replace(kernel(new,3,4),payload=new.payload),window.end))
    check('rejections preserve committed message',history.read()==new)
    reject('future observations rejected',lambda:history.prepare(kernel(new,3,9),window.end))
    reject('gap rejected',lambda:history.prepare(kernel(new,4,5),window.end))
    reject('epoch mismatch rejected',lambda:history.prepare(replace(kernel(new,3,4),entry=Boundary(3,91)),window.end))
    reject('stale feedback rejected',lambda:history.prepare(replace(kernel(new,3,4),base_feedback_id=old.message_id),window.end))
    for field in asdict(new.binding):
        value=digest('different '+field) if field.endswith('_id') else getattr(new.binding,field)+1
        reject('binding mismatch/'+field,lambda f=field,v=value:history.prepare(replace(kernel(new,3,4),binding=replace(new.binding,**{f:v})),window.end))
    reject('empty retirement rejected',lambda:replace(token,exit=token.entry))
    reject('reversed time rejected',lambda:replace(kernel(new,3,4),exit=Boundary(4,89)))
    reject('mutable payload rejected',lambda:replace(token,payload=bytearray(token.payload)))
    reject('source order rejected',lambda:window.offer(10))
    reject('negative sequence rejected',lambda:Boundary(-1,0))
    reject('invalid identity rejected',lambda:replace(new.binding,source_id='unbound'))
    reject('false coverage certification rejected',lambda:replace(new,coverage_validated=True))
    reject('unknown ticket rejected',lambda:history.commit(digest('missing')))
    staging=history.prepare(kernel(new,3,4),window.end);history.abort(staging)
    check('abort preserves message/window',history.read()==new and window.query_scope(new)==(3,8))
    reject('aborted commit rejected',lambda:history.commit(staging))
    tail=kernel(new,3,8);candidate=GaussianFixture().advance(new.payload,tail)
    for _ in range(20):GaussianFixture().advance(new.payload,tail)
    check('read-only overlapping query',history.read()==new and window.query_scope(new)==(3,8))
    # Independent batch posterior and marginal likelihood: same eight rows/prior.
    H=np.array([[1.,.2+.1*(-1)**i] for i in range(8)]);y=.1*np.arange(1,9)
    P=np.linalg.inv(np.eye(2)+H.T@H);mean=P@H.T@y;S=np.eye(8)+H@H.T
    logZ=-.5*(y@np.linalg.solve(S,y)+np.linalg.slogdet(S)[1]+8*math.log(2*math.pi))
    result=unpack(candidate)
    close('one-prior disjoint evidence batch mean',result['mean'],mean)
    close('joint covariance retained',result['covariance'],P)
    close('normalizer retained',result['log_evidence'],logZ)
    check('cross covariance not discarded',abs(result['covariance'][0][1])>.01)
    for chunk in [1,2,4,8]:
        h=root()
        for k in range(0,8,chunk):h.commit(h.prepare(kernel(h.read(),k,k+chunk),8))
        p=unpack(h.read().payload)
        close('retirement partition mean/'+str(chunk),p['mean'],mean)
        close('retirement partition covariance/'+str(chunk),p['covariance'],P)
        close('retirement partition normalization/'+str(chunk),p['log_evidence'],logZ)
    # Independent unexcited direction versus legitimately correlated correction.
    for cov in [[[1.,0.],[0.,1.]],[[1.,.5],[.5,1.]]]:
        h=root(cov=cov);t=kernel(h.read(),0,1,H=[[0.,1.]],y=[1.]);h.commit(h.prepare(t,1))
        p=unpack(h.read().payload);expected=np.array(cov)-np.outer(np.array(cov)[:,1],np.array(cov)[1,:])/2
        close('quiet direction mean/'+str(cov),p['mean'],np.array(cov)[:,1]/2)
        close('quiet direction covariance/'+str(cov),p['covariance'],expected)
    h=root();p0=h.read();quiet=kernel(p0,0,1,H=[[0.,0.]],y=[0.]);h.commit(h.prepare(quiet,1))
    close('no inferred aging from time alone',unpack(h.read().payload)['mean'],unpack(p0.payload)['mean'])
    close('no artificial process noise',unpack(h.read().payload)['covariance'],unpack(p0.payload)['covariance'])
    h=root();zero=kernel(h.read(),0,1,ticks=0);h.commit(h.prepare(zero,1))
    check('zero duration advances source',h.read().boundary==Boundary(1,0))
    class FailedBackend(GaussianFixture):
        def advance(self,p,t):raise ValueError('injected numeric failure')
    h=root(backend=FailedBackend());before=h.read()
    reject('backend failure explicit',lambda:h.prepare(kernel(before,0,1),1))
    check('backend failure atomic',h.read()==before)
    class TooLargeBackend(GaussianFixture):
        def advance(self,p,t):return p+b' '*1000
    h=root(backend=TooLargeBackend(),capacity=200);before=h.read()
    reject('payload overflow explicit',lambda:h.prepare(kernel(before,0,1),1))
    check('payload overflow atomic',h.read()==before)
    h=root();local=replace(kernel(h.read(),0,1),tier='local_approximate');h.commit(h.prepare(local,1))
    h.commit(h.prepare(kernel(h.read(),1,2),2))
    check('approximation status not erased',h.read().tier=='local_approximate' and h.read().error_bound is None)
    check('ledger changes with evidence',h.read().ledger_id!=old.ledger_id)
    # User-proposed transport: dimensionless gamma, Ah/second units, plusHh.
    def physical(Q,b,z0,gamma,I,dt,h0=0.):
        z=z0-I*dt/(3600*Q);e=math.exp(-gamma*abs(I)*dt/(3600*Q))
        h=h0 if I==0 else e*h0+(1-e)*np.sign(I)
        return z,h,3.+b*z+.015*h-I*.1
    for I in [-.03,0.,.03]:
        for dt in [0.,1/35,70.]:
            for h0 in [-1.,0.,1.]:
                z,h,v=physical(.06,1.15,.6,6.,I,dt,h0)
                check('hysteresis bounded/'+str((I,dt,h0)),-1<=h<=1)
                if I==0:close('zero-currenth holds/'+str((dt,h0)),h,h0)
                else:close('charge units/'+str((I,dt,h0)),z,.6-I*dt/216.)
    for dt in [0.,1/35,70.,300.]:
        # Exact continuous scaling ambiguity in the proposed linear-OCV model.
        a=physical(.06,1.15,.6,6.,.03,dt);b=physical(.075,1.4375,.48,7.5,.03,dt)
        close('OCV-Q-gamma scaling leaves voltage/'+str(dt),a[2],b[2])
        close('OCV-Q-gamma scaling leavesh/'+str(dt),a[1],b[1])
    a=physical(.06,1.15,.6,6.,.03,70.);b=physical(.075,1.15,.6,6.,.03,70.)
    check('Q influences hysteresis under normalized throughput',a[1]!=b[1])
    check('userplusHh sign',physical(.06,1.15,.6,6.,0.,0.,1.)[2]>physical(.06,1.15,.6,6.,0.,0.,-1.)[2])
    check('no plant imports in protocol',all(x not in (HERE/'protocol.py').read_text() for x in ['import numpy','import scm','from experiments','from .qualification']))
    for p,expected in sources.items():check('source identity/'+p,ident(ROOT/p)==expected)
    report=dict(status='passed' if all(c['passed'] for c in checks) else 'failed',passing_checks=sum(c['passed'] for c in checks),
                failed_checks=[c for c in checks if not c['passed']],checks=checks,
                preserved_artifacts=len(preserved),scope='Finite lifecycle, linear-Gaussian ownership and user-model algebra controls; not physical estimator/coverage qualification')
    write(out/'result.json',report);print(json.dumps({k:report[k] for k in ['status','passing_checks','failed_checks','preserved_artifacts']}))
    if report['failed_checks']:raise SystemExit(1)


if __name__=='__main__':main()
