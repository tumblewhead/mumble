"""Supplemental uncertainty/tail audit and a separately registered log codec.

The successful primary attempt remains immutable, including its dictionary.
This follow-up tests a limitation of absolute-mass geometry and an alternative
coordinate quantization with a likelihood-invariant ratio-error metric.
"""
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


def main():
    output=Path(sys.argv[1]) if len(sys.argv)>1 else HERE/'tails001';output.mkdir(parents=True,exist_ok=False)
    prior=json.loads((HERE/'attempt001/reservation.json').read_text())
    preserved=dict(prior['preserved_artifacts'])
    for folder in ['attempt001','development001']:
        for p in (HERE/folder).rglob('*'):
            if p.is_file():preserved[str(p.relative_to(ROOT))]=ident(p)
    for p,expected in preserved.items():
        if ident(ROOT/p)!=expected:raise ValueError('earlier artifact changed: '+p)
    sources=[HERE/name for name in ['log_codec.py','tail_checks.py','codecs.py','model.py','fixtures.py','qualify.py','tail_plan.json']]
    for p in sources:
        dest=output/'source_snapshot'/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    write(output/'reservation.json',dict(source_identities={str(p.relative_to(ROOT)):ident(p) for p in sources},preserved_artifacts=preserved,
          command=sys.argv,purpose='Uncertainty/tail adversary and fixed-span log geometry comparison; primary result is not rewritten'))
    c=Checks();evidence={};start=time.process_time()
    try:
        # Tiny probability can become important after a future observation.
        p=np.array([1-1e-12,1e-12]);L=np.array([1e-10,1.])
        truth=p*L;truth/=truth.sum();adversary=[]
        for name,codec in [('sphere8',codecs.SphereCodebook(2,8)),('sphere12',codecs.SphereCodebook(2,12)),('log12',LogSphereCodebook(2))]:
            raw,q,error=codec.encode_checked(p);updated=q*L;updated/=updated.sum()
            row=dict(codec=name,encoded_rare_mass=float(q[1]),prior_TV=error['TV'],posterior_TV=codecs.distances(truth,updated)['TV'],
                     actual_rare_posterior=float(truth[1]),encoded_rare_posterior=float(updated[1]),
                     prior_log_oscillation=oscillation(p,q),posterior_log_oscillation=oscillation(truth,updated))
            c.close('common-likelihood log oscillation/'+name,row['prior_log_oscillation'],row['posterior_log_oscillation'])
            adversary.append(row)
        c.check('absolute-mass bound does not protect future tail',adversary[1]['prior_TV']<1e-6 and adversary[1]['posterior_TV']>.9)
        c.check('log-coded future TV follows ratio bound',adversary[2]['posterior_TV']<=math.tanh(adversary[2]['prior_log_oscillation']/4)+1e-12)
        evidence['rare_tail']=adversary
        rng=np.random.default_rng(291031)
        for n in [3,257]:
            logs=-rng.uniform(0,600,n);p=np.exp(logs-logs.max());p[0]=0;p/=p.sum()
            codec=LogSphereCodebook(n);raw,q,error=codec.encode_checked(p)
            c.check('log theoretical ratio bound/'+str(n),error['log_oscillation']<=error['a_priori_log_oscillation_bound']+1e-12)
            c.check('log encoding idempotent/'+str(n),codec.encode(q)==raw)
            repeated=q.copy()
            for _ in range(100):repeated=codec.decode(codec.encode(repeated))
            c.close('log no empty reencoding drift/'+str(n),repeated,q,atol=0.,rtol=0.)
        c.reject('log dynamic range explicitly rejects',lambda:LogSphereCodebook(2).encode([1.,float(np.nextafter(0.,1.))]))
        dictionary_file=HERE/'attempt001/dictionary.json';dictionary_identity=ident(dictionary_file)
        shapes=json.loads(dictionary_file.read_text())['shapes'];runs=[]
        for name in fixtures.HELD_OUT:
            for scale in fixtures.PROFILE_SCALES:
                m=model.Model(17,scale);p=m.prior.copy();dictionary=codecs.ShapeDictionary(m.features,shapes)
                methods={'sphere8':codecs.SphereCodebook(p.size,8),'sphere12':codecs.SphereCodebook(p.size,12),
                         'shapes':dictionary,'log12':LogSphereCodebook(p.size)}
                beliefs={k:p.copy() for k in methods};Dledger=0.;steps=[]
                for frame in fixtures.frames(name):
                    op=m.prepare(frame);predicted=model.predict(p,op);p,_,_=model.observe(predicted,op);step={}
                    for key,codec in methods.items():
                        before=beliefs[key];qpred=model.predict(before,op)
                        if key=='log12':
                            c.check(f'Markov ratio contraction/{name}/{scale}/{frame.index}',oscillation(predicted.ravel(),qpred.ravel())<=oscillation(p_before.ravel(),before.ravel())+1e-10 if frame.index else oscillation(predicted.ravel(),qpred.ravel())<1e-10)
                        candidate,_,_=model.observe(qpred,op);raw,q,local=codec.encode_checked(candidate.ravel());q=q.reshape(m.shape)
                        error=codecs.distances(p.ravel(),q.ravel());event=(op['Q']<.05)&(op['R']>.115)
                        joint_error=abs(float(np.sum((p-q)*event)))
                        c.check(f'joint event TV bound/{name}/{scale}/{frame.index}/{key}',joint_error<=error['TV']+1e-12)
                        stds={};means={}
                        for query in ['Q','soc']:
                            values=op[query];ep=float(np.sum(p*values));eq=float(np.sum(q*values))
                            vp=float(np.sum(p*(values-ep)**2));vq=float(np.sum(q*(values-eq)**2))
                            stds[query]=dict(reference=math.sqrt(vp),encoded=math.sqrt(vq),ratio=math.sqrt(vq/vp) if vp else None)
                            means[query]=eq-ep
                        a,b=op['Q'],op['soc'];ap,bp=float(np.sum(p*a)),float(np.sum(p*b));aq,bq=float(np.sum(q*a)),float(np.sum(q*b))
                        covp=float(np.sum(p*(a-ap)*(b-bp)));covq=float(np.sum(q*(a-aq)*(b-bq)))
                        cov_bound=(float(np.ptp(a*b))+abs(ap)*float(np.ptp(b))+abs(bq)*float(np.ptp(a)))*error['TV']
                        c.check(f'cross covariance bound/{name}/{scale}/{frame.index}/{key}',abs(covp-covq)<=cov_bound+1e-12)
                        row=dict(TV=error['TV'],packet_B=len(raw),std=stds,mean_error=means,joint_event_error=joint_error,
                                 Q_SOC_covariance_difference=covq-covp,local_log_oscillation=oscillation(candidate.ravel(),q.ravel()))
                        if key=='log12':
                            Dledger+=local['log_oscillation'];actual=oscillation(p.ravel(),q.ravel())
                            c.check(f'log local error bound/{name}/{scale}/{frame.index}',local['log_oscillation']<=local['a_priori_log_oscillation_bound']+1e-10)
                            c.check(f'log cumulative ledger/{name}/{scale}/{frame.index}',actual<=Dledger+1e-10)
                            c.check(f'log posterior TV bound/{name}/{scale}/{frame.index}',error['TV']<=math.tanh(Dledger/4)+1e-10)
                            row.update(log_oscillation=actual,log_ledger=Dledger,TV_ledger=math.tanh(Dledger/4))
                        beliefs[key]=q;step[key]=row
                    p_before=p.copy();steps.append(dict(index=frame.index,codecs=step))
                runs.append(dict(fixture=name,aging_scale=scale,steps=steps))
        c.check('dictionary remains frozen',ident(dictionary_file)==dictionary_identity)
        evidence['uncertainty']=runs
    except Exception:
        import traceback
        c.check('supplemental exception',False,detail=traceback.format_exc())
    for p,expected in preserved.items():
        if ident(ROOT/p)!=expected:c.check('preservation/'+p,False)
    result=dict(status='passed' if all(x['passed'] for x in c.items) else 'failed',passing_checks=sum(x['passed'] for x in c.items),
                failed_checks=[x for x in c.items if not x['passed']],checks=c.items,evidence=evidence,cpu_seconds=time.process_time()-start,
                scope='Finite uncertainty/tail/log-codebook audit; no continuous-posterior or lifetime qualification')
    write(output/'result.json',result);print(json.dumps({k:result[k] for k in ['status','passing_checks','failed_checks','cpu_seconds']}))
    if result['failed_checks']:raise SystemExit(1)


if __name__=='__main__':main()
