"""Separate 16-bit precision follow-up; no primary/tail artifact is changed."""
from dataclasses import dataclass
import json
import math
from pathlib import Path
import shutil
import sys
import time
import numpy as np
from . import codecs,fixtures,model
from .log_codec import LogSphereCodebook,oscillation
from .qualify import HERE,ROOT
from experiments.structured_joint_001.qualify import Checks,ident,write


@dataclass(frozen=True)
class Log16Codebook(LogSphereCodebook):
    bits:int=16

    def __post_init__(self):
        if type(self.size) is not int or self.size<1 or self.bits!=16 or self.span!=512.:
            raise ValueError('log16 descriptor')


def main():
    output=Path(sys.argv[1]) if len(sys.argv)>1 else HERE/'log16_001';output.mkdir(parents=True,exist_ok=False)
    old=json.loads((HERE/'tails001/reservation.json').read_text());preserved=dict(old['preserved_artifacts'])
    for p in (HERE/'tails001').rglob('*'):
        if p.is_file():preserved[str(p.relative_to(ROOT))]=ident(p)
    for p,expected in preserved.items():
        if ident(ROOT/p)!=expected:raise ValueError('earlier artifact changed: '+p)
    sources=[HERE/name for name in ['log16_checks.py','log_codec.py','codecs.py','model.py','fixtures.py','log16_plan.json']]
    for p in sources:
        dest=output/'source_snapshot'/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    write(output/'reservation.json',dict(source_identities={str(p.relative_to(ROOT)):ident(p) for p in sources},preserved_artifacts=preserved,command=sys.argv))
    start=time.process_time();c=Checks();runs=[]
    p=np.array([1-1e-12,1e-12]);L=np.array([1e-10,1.]);raw,q,local=Log16Codebook(2).encode_checked(p)
    ep=p*L;ep/=ep.sum();eq=q*L;eq/=eq.sum()
    adversary=dict(encoded_rare_mass=float(q[1]),reference_rare_posterior=float(ep[1]),encoded_rare_posterior=float(eq[1]),
                   posterior_TV=codecs.distances(ep,eq)['TV'],log_oscillation=oscillation(ep,eq))
    c.check('16bit rare posterior bound',adversary['posterior_TV']<=math.tanh(local['log_oscillation']/4)+1e-12)
    for name in fixtures.HELD_OUT:
        for scale in fixtures.PROFILE_SCALES:
            m=model.Model(17,scale);p=m.prior.copy();q=p.copy();codec=Log16Codebook(p.size);D=0.;steps=[]
            for frame in fixtures.frames(name):
                op=m.prepare(frame);pp=model.predict(p,op);qp=model.predict(q,op)
                c.check(f'16bit transition ratio/{name}/{scale}/{frame.index}',oscillation(pp.ravel(),qp.ravel())<=oscillation(p.ravel(),q.ravel())+1e-10)
                p,_,_=model.observe(pp,op);candidate,_,_=model.observe(qp,op)
                raw,decoded,error=codec.encode_checked(candidate.ravel());q=decoded.reshape(m.shape);D+=error['log_oscillation']
                c.check(f'16bit idempotent/{name}/{scale}/{frame.index}',codec.encode(decoded)==raw)
                c.check(f'16bit local ratio/{name}/{scale}/{frame.index}',error['log_oscillation']<=error['a_priori_log_oscillation_bound']+1e-10)
                c.check(f'16bit joint ratio ledger/{name}/{scale}/{frame.index}',oscillation(p.ravel(),decoded)<=D+1e-10)
                distance=codecs.distances(p.ravel(),decoded)
                c.check(f'16bit TV ledger/{name}/{scale}/{frame.index}',distance['TV']<=math.tanh(D/4)+1e-10)
                ep=model.moments(p,op);eq=model.moments(q,op);std={}
                for field in ['Q','soc']:
                    vp=float(np.sum(p*(op[field]-ep[field])**2));vq=float(np.sum(q*(op[field]-eq[field])**2))
                    std[field]=dict(reference=math.sqrt(vp),encoded=math.sqrt(vq),ratio=math.sqrt(vq/vp))
                steps.append(dict(index=frame.index,TV=distance['TV'],TV_ledger=math.tanh(D/4),log_ledger=D,
                                  log_oscillation=oscillation(p.ravel(),decoded),local_log_oscillation=error['log_oscillation'],
                                  Q_relative_error_percent=100*(eq['Q']-ep['Q'])/ep['Q'],SOC_error_pp=100*(eq['soc']-ep['soc']),
                                  std=std,packet_B=len(raw)))
            runs.append(dict(fixture=name,aging_scale=scale,steps=steps))
    for p,expected in preserved.items():
        if ident(ROOT/p)!=expected:c.check('preservation/'+p,False)
    result=dict(status='passed' if all(x['passed'] for x in c.items) else 'failed',passing_checks=sum(x['passed'] for x in c.items),
                failed_checks=[x for x in c.items if not x['passed']],checks=c.items,evidence=dict(rare_tail=adversary,runs=runs),
                cpu_seconds=time.process_time()-start,scope='16-bit precision tradeoff on the same finite-state comparator; not a lifetime or complete-SRAM pass')
    write(output/'result.json',result);print(json.dumps({k:result[k] for k in ['status','passing_checks','failed_checks','cpu_seconds']}))
    if result['failed_checks']:raise SystemExit(1)


if __name__=='__main__':main()
