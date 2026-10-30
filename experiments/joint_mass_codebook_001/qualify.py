"""Finite joint-codebook qualification; no long sweeps or truth-based fitting."""
import ctypes as C
import json
import math
from pathlib import Path
import platform
import resource
import shutil
import subprocess
import sys
import time
import numpy as np
from . import codecs, fixtures, model
from experiments.structured_joint_001.qualify import Checks, ident, write
from experiments.partitioned_battery_closure_001.witnesses import Physical, State

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]


def primitives(c):
    for exposure in [0.,1e-5,.2,1.]:
        P,tail,G=model.transition(3,exposure)
        c.close(f'kernel normalized/{exposure}',P.sum(axis=1),np.ones(9))
        c.check(f'kernel nonnegative/{exposure}',np.all(P>=0))
        forbidden=[P[i*3+j,k*3+l] for i in range(3) for j in range(3) for k in range(3) for l in range(3) if k<i or l<j]
        c.check(f'monotone support/{exposure}',np.all(np.array(forbidden)==0))
        c.close(f'generator conservation/{exposure}',G.sum(axis=1),np.zeros(9))
        c.close(f'semigroup/{exposure}',P@P,model.transition(3,2*exposure)[0])
        c.check(f'uniformization tail/{exposure}',tail<1e-40)
    c.check('shared damage channel exists',model.transition(3,.2)[2][0,4]>0)
    c.reject('exposure workload rejects',lambda:model.transition(3,3.))
    rng=np.random.default_rng(291030)
    for size in [3,31,257]:
        p=rng.random(size);p[::5]=0;p/=p.sum()
        for bits in [8,12]:
            codec=codecs.SphereCodebook(size,bits);raw,q,err=codec.encode_checked(p)
            c.close(f'code normalization/{size}/{bits}',q.sum(),1.)
            c.check(f'code support/{size}/{bits}',np.array_equal(p>0,q>0))
            c.check(f'code bytes/{size}/{bits}',len(raw)==(size*bits+7)//8)
            c.check(f'code bound/{size}/{bits}',err['TV']<=err['a_priori_TV_bound']+1e-12 and err['TV']<=err['spherical_TV_bound']+1e-12)
            c.check(f'code idempotent/{size}/{bits}',codec.encode(q)==raw)
            stable=q.copy()
            for _ in range(100):stable=codec.decode(codec.encode(stable))
            c.close(f'no empty reencoding drift/{size}/{bits}',stable,q,atol=0.,rtol=0.)
            c.reject(f'code empty rejects/{size}/{bits}',lambda codec=codec,raw=raw:codec.decode(bytes(len(raw))))
    c.reject('malformed padding rejects',lambda:codecs.SphereCodebook(3,12).decode(bytes([0,0,0,0,128])))
    m=model.Model();before=(m.next_index,m.temperature,m.v.copy())
    c.reject('source order rejects',lambda:m.prepare(model.Frame(1,1/35,.02,25,3.7)))
    c.check('failed prepare atomic',m.next_index==before[0] and m.temperature==before[1] and np.array_equal(m.v,before[2]))
    # Exact reciprocal-capacity integral for a linear measured temperature path.
    nodes,weights=np.polynomial.legendre.leggauss(96)
    op=m.prepare(model.Frame(0,30,.02,35,3.7))
    t=25+5*(nodes+1)
    for iq in range(3):
        exact_decrement=.02*30/3600*float(.5*weights@(1/(.06*(1+m.gq[iq]*(t-25)))))
        znew=(op['lo'][0,10,iq]+op['upper_weight'][0,10,iq])/(m.nz-1)
        c.close(f'temperature path integral/{iq}',m.z[10]-znew,exact_decrement)
    return dict(scope='Finite stochastic/codec/input controls; semigroup applies only to aging kernel, not split full battery model')


def c_reference(c):
    lib=C.CDLL(str(ROOT/'experiments/monotone_codebook_001/attempt001/reference.so'))
    lib.scm_physical_step.argtypes=[C.POINTER(Physical),C.POINTER(State),C.c_void_p,C.c_double,C.c_double,C.POINTER(C.c_double)]
    lib.scm_physical_step.restype=C.c_int
    m=model.Model();states=[];params=[];z=.625
    for nu in range(3):
        params.append(Physical(3,.1,(C.c_double*3)(*m.Rp[nu]),(C.c_double*3)(*m.tau[nu]),m.H[nu],m.gp[nu],m.gm[nu],.06))
        states.append(State(z,(C.c_double*3)(*m.v0[nu]),m.h0[nu]))
    errors=[]
    for k,(dt,I) in enumerate([(1/35,.02),(.031,0),(.027,-.01),(.029,.03)]):
        m.prepare(model.Frame(k,dt,I,25,3.7));z-=I*dt/(3600*.06)
        for nu in range(3):
            voltage=C.c_double();status=lib.scm_physical_step(C.byref(params[nu]),C.byref(states[nu]),None,dt,I,C.byref(voltage))
            predicted=model.ocv(z)-.1*I-m.v[nu].sum()-m.H[nu]*m.h[nu]
            c.check(f'C status/{k}/{nu}',status==0)
            c.close(f'C physical voltage/{k}/{nu}',predicted,voltage.value,atol=3e-14,rtol=3e-14)
            c.close(f'C physical RC/{k}/{nu}',m.v[nu],list(states[nu].v),atol=3e-14,rtol=3e-14)
            errors.append(abs(predicted-voltage.value))
    return dict(max_voltage_difference_V=float(max(errors)),scope='Stationary physical response submodel only; no aging/SOC-grid certification')


def geometry(c):
    results=[]
    for point in [(-3.,-3.,.8),(-2.,1.,-.8),(0.,0.,0.),(.2,-.3,.6),(3.,3.,.89)]:
        direct=codecs.bivariate_mass(*point)
        refined=codecs.bivariate_mass(*point,order=256)
        c.close('geometry quadrature/'+str(point),direct,refined,atol=2e-12,rtol=2e-11)
        for bits in [8,12]:
            r=codecs.geometry_code(*point,bits);results.append(r)
            c.check(f'geometry probability bound/{point}/{bits}',r['absolute_error']<=r['real_arithmetic_bound']+2e-12)
            c.check(f'geometry packet/{point}/{bits}',r['payload_B']==(3*bits+7)//8)
    c.reject('singular geometry outside range rejects',lambda:codecs.geometry_code(0.,0.,1.,12))
    return results


def train_dictionary(output):
    shapes=[];sources=[]
    for name in fixtures.TRAINING:
        m=model.Model(17,20.);p=m.prior.copy()
        for frame in fixtures.frames(name):
            op=m.prepare(frame);p,_,_=model.observe(model.predict(p,op),op)
            if frame.index in fixtures.TEMPLATE_CHECKPOINTS:
                shapes.append(codecs.moments_shape(p.ravel(),m.features))
                sources.append(dict(fixture=name,index=frame.index))
    value=dict(kind='four_joint_Gaussian_shapes_plus_uniform',shapes=shapes,training_sources=sources,
               support='Exact bitmap supplied by each encoded message',held_out_used=False,
               shape_coordinates=['Q_damage','R_damage','SOC','Q_thermal_index','R_thermal_index','joint_nuisance_coordinate'])
    write(output/'dictionary.json',value)
    return codecs.ShapeDictionary(m.features,shapes),ident(output/'dictionary.json')


def batch_control(c):
    reports=[]
    for name in ['weak','reversal']:
        m=model.Model(17,20.);p=m.prior.copy();ops=[];log_evidence=0
        for frame in fixtures.frames(name)[:2]:
            op=m.prepare(frame);ops.append(op);p,logz,_=model.observe(model.predict(p,op),op);log_evidence+=logz
        unretired,logz,paths=model.batch_paths(m,ops)
        c.close('batch full posterior/'+name,p,unretired)
        c.close('batch evidence/'+name,log_evidence,logz)
        c.close('batch Q/'+name,np.sum(p*ops[-1]['Q']),np.sum(unretired*ops[-1]['Q']))
        c.close('batch SOC/'+name,np.sum(p*ops[-1]['soc']),np.sum(unretired*ops[-1]['soc']))
        reports.append(dict(fixture=name,unmerged_paths=paths,TV=codecs.distances(p.ravel(),unretired.ravel())['TV'],log_evidence_difference=abs(log_evidence-logz)))
    return reports


def held_out(c,dictionary):
    runs=[]
    for name in fixtures.HELD_OUT:
        for scale in fixtures.PROFILE_SCALES:
            m=model.Model(17,scale);p=m.prior.copy();physical_prior=p.copy()
            codecs_by_name={'sphere8':codecs.SphereCodebook(p.size,8),'sphere12':codecs.SphereCodebook(p.size,12),'shapes':dictionary}
            beliefs={key:p.copy() for key in codecs_by_name};ledgers={key:0. for key in beliefs};steps=[];logz=0
            for frame in fixtures.frames(name):
                op=m.prepare(frame);physical_prior=model.predict(physical_prior,op)
                p,lz,amplify=model.observe(model.predict(p,op),op);logz+=lz
                c.close(f'exact normalization/{name}/{scale}/{frame.index}',p.sum(),1.)
                exact_queries=model.moments(p,op)
                if name=='weak':
                    c.close(f'no rest health information/{scale}/{frame.index}',p.sum(axis=(1,2,3,4)),physical_prior.sum(axis=(1,2,3,4)))
                encoded={}
                for key,codec in codecs_by_name.items():
                    before=beliefs[key]
                    predicted=model.predict(before,op)
                    before_error=codecs.distances(p.ravel(),before.ravel())['TV']
                    candidate,_,_=model.observe(predicted,op)
                    raw,decoded,local=codec.encode_checked(candidate.ravel());q=decoded.reshape(m.shape)
                    current=codecs.distances(p.ravel(),decoded)
                    ledgers[key]=min(1.,amplify*ledgers[key]+local['TV'])
                    c.close(f'normalized code/{name}/{scale}/{frame.index}/{key}',q.sum(),1.)
                    c.check(f'coherent support/{name}/{scale}/{frame.index}/{key}',np.array_equal(candidate>0,q>0))
                    c.check(f'geometry TV relation/{name}/{scale}/{frame.index}/{key}',local['TV']<=local['spherical_TV_bound']+1e-11)
                    c.check(f'accumulated ledger/{name}/{scale}/{frame.index}/{key}',current['TV']<=ledgers[key]+1e-10)
                    queries=model.moments(q,op);errors={k:queries[k]-exact_queries[k] for k in queries}
                    for query in queries:
                        span=float(np.ptp(op[query]))
                        c.check(f'query TV bound/{name}/{scale}/{frame.index}/{key}/{query}',abs(errors[query])<=span*current['TV']+1e-12)
                    encoded[key]=dict(packet_B=len(raw),local=local,cumulative=current,TV_ledger=ledgers[key],
                                      query_errors=errors,Q_relative_error_percent=100*errors['Q']/exact_queries['Q'],
                                      SOC_error_pp=100*errors['soc'],codeword_index=raw[0] if key=='shapes' else None)
                    beliefs[key]=q
                steps.append(dict(index=frame.index,elapsed_s=sum(f.dt for f in fixtures.frames(name)[:frame.index+1]),temperature_C=frame.temperature,
                                  exact_queries=exact_queries,log_evidence=logz,likelihood_TV_amplification_bound=amplify,
                                  uniformization_tail_bound=op['tail_bound'],codecs=encoded))
            # Retain a modest final joint covariance, not just separate means.
            mu=p.ravel()@m.features;centered=m.features-mu;cov=(centered.T*p.ravel())@centered
            runs.append(dict(fixture=name,aging_scale=scale,steps=steps,final_feature_covariance=cov.tolist(),
                             final_positive_states=int(np.count_nonzero(p)),final_nuisance_mass=p.sum(axis=(0,1,2,3)).tolist()))
    return runs


def refinement(c):
    out=[]
    for nodes in [17,33,65]:
        m=model.Model(nodes,20.);p=m.prior.copy();log_evidence=0
        for frame in fixtures.frames('reversal'):
            op=m.prepare(frame);p,lz,_=model.observe(model.predict(p,op),op);log_evidence+=lz
        out.append(dict(SOC_nodes=nodes,states=p.size,posterior_B=p.nbytes,queries=model.moments(p,op),log_evidence=log_evidence,
                        SOC_variance=float(np.sum(p*(op['soc']-np.sum(p*op['soc']))**2))))
        c.close(f'refinement normalization/{nodes}',p.sum(),1.)
    return dict(results=out,scope='SOC-grid sensitivity only; fixed discrete health/thermal/nuisance support. Not continuous convergence or calibrated coverage.')


def main():
    output=Path(sys.argv[1]) if len(sys.argv)>1 else HERE/'attempt001';output.mkdir(parents=True,exist_ok=False)
    prior=json.loads((ROOT/'experiments/structured_joint_001/verification.json').read_text())
    older=json.loads((ROOT/'experiments/structured_joint_001/attempt001/reservation.json').read_text())['preserved_artifacts']
    preserved={**older,**prior['artifacts'],'experiments/structured_joint_001/verification.json':ident(ROOT/'experiments/structured_joint_001/verification.json')}
    for path,expected in preserved.items():
        if ident(ROOT/path)!=expected:raise ValueError('earlier evidence changed: '+path)
    dependencies=['experiments/monotone_codebook_001/splines.py','experiments/structured_joint_001/qualify.py',
                  'experiments/partitioned_battery_closure_001/witnesses.py','experiments/partitioned_battery_closure_001/conditional.py',
                  'experiments/minimal_health_kernels_001/kernel.py','experiments/monotone_codebook_001/attempt001/reference.so','src/scm_model.c','include/scm_model.h']
    files=list(HERE.glob('*.py'))+[HERE/'plan.json',HERE/'derivation.md']+[ROOT/p for p in dependencies]
    identities={str(p.relative_to(ROOT)):ident(p) for p in files}
    for p in files:
        dest=output/'source_snapshot'/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    write(output/'reservation.json',dict(source_revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
          branch=subprocess.check_output(['git','branch','--show-current'],text=True).strip(),source_identities=identities,preserved_artifacts=preserved,
          python=platform.python_version(),numpy=np.__version__,command=sys.argv,preliminary_activity='One public single-event smoke check before this qualification; no held-out sweep or codebook tuning'))
    c=Checks();evidence={};started=time.perf_counter();cpu=time.process_time()
    try:
        evidence['primitives']=primitives(c);evidence['C_reference']=c_reference(c);evidence['geometry']=geometry(c)
        dictionary,dictionary_identity=train_dictionary(output)
        evidence['dictionary']=dict(identity=dictionary_identity,templates=1+len(dictionary.shapes),packed_parameter_B=dictionary.packed_parameter_bytes,
                                    dense_cached_shapes_B=sum(x.nbytes for x in dictionary.logs),feature_grid_B=dictionary.features.nbytes)
        evidence['batch']=batch_control(c);evidence['held_out']=held_out(c,dictionary);evidence['refinement']=refinement(c)
        c.check('dictionary unchanged by held-out evaluation',ident(output/'dictionary.json')==dictionary_identity)
    except Exception:
        import traceback
        c.check('unhandled qualification exception',False,detail=traceback.format_exc())
    for p,expected in identities.items():c.check('source integrity/'+p,ident(ROOT/p)==expected)
    for p,expected in preserved.items():
        if ident(ROOT/p)!=expected:c.check('earlier evidence modified/'+p,False)
    result=dict(status='passed' if all(x['passed'] for x in c.items) else 'failed',passing_checks=sum(x['passed'] for x in c.items),
                failed_checks=[x for x in c.items if not x['passed']],checks=c.items,evidence=evidence,
                wall_seconds=time.perf_counter()-started,cpu_seconds=time.process_time()-cpu,maximum_RSS_B=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
                preserved_earlier_artifacts=len(preserved),continuous_posterior_qualified=False,aging_calibrated=False,
                production_changed=False,firmware_qualified=False,lifetime_qualified=False)
    write(output/'result.json',result)
    print(json.dumps({k:result[k] for k in ['status','passing_checks','failed_checks','wall_seconds','cpu_seconds','maximum_RSS_B']}))
    if result['failed_checks']:raise SystemExit(1)


if __name__=='__main__':main()
