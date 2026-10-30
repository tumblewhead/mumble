"""Frozen finite algebra/codec controls; no physical aging or thermal fit."""
import argparse
import copy
import ctypes as C
import hashlib
import json
import math
from pathlib import Path
import pickle
import platform
import resource
import shutil
import subprocess
import time
import traceback
import numpy as np
from experiments.minimal_health_kernels_001 import kernel
from experiments.partitioned_battery_closure_001 import conditional
from experiments.partitioned_battery_closure_001.witnesses import Physical,State,c_replay
from .factor import Factor,translate_upper
from .splines import basis,monotone,thermal_basis,lipschitz,Codebook

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]


def ident(p):
    b=p.read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())


def write(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2,allow_nan=False);f.write('\n')


class Checks:
    def __init__(self):self.items=[]
    def ok(self,name,value,**details):self.items.append(dict(name=name,passed=bool(value),**details))
    def close(self,name,a,b,atol=2e-10,rtol=2e-10):
        a,b=np.asarray(a),np.asarray(b)
        self.ok(name,np.isfinite(a).all() and np.all(abs(a-b)<=atol+rtol*abs(b)),max_absolute_error=float(np.max(abs(a-b),initial=0.)))
    def reject(self,name,f):
        try:f()
        except ValueError:self.ok(name,True)
        else:self.ok(name,False)
    def case(self,name,f):
        try:return f()
        except Exception:self.ok(name+'/exception',False,traceback=traceback.format_exc())


def signature(x):return hashlib.sha256(pickle.dumps(x)).hexdigest()


def regression(c,rng,plan,family):
    n=plan['fixtures']['regression_records'];t=np.linspace(0,1,n);sites=np.linspace(0,1,4);Tk=np.linspace(-20,60,4)
    T=25+18*np.sin(t*9);drive=.2*np.cos(t*13)
    X=np.column_stack((basis(t,sites,family),thermal_basis(T,Tk,family),drive))
    y=1+.04*np.sin(t*7)+.02*np.cos(t*17) # independently fabricated observations
    sigma=.02+.003*(np.arange(n)%3)
    center=np.r_[[1,1.02,1.06,1.1],np.zeros(4)]
    def make(start,stop,origin):
        out=Factor(origin,'synthetic-linear-v1',family+'-age4-thermal3-residual1',start,float(t[start-1]) if start else 0.)
        for k in range(start,stop):out.append(X[k],y[k],sigma[k],k,float(t[k]),out.source,residual_error=1e-5)
        return out
    full=make(0,n,center);left=make(0,87,center);right=make(87,n,center+.013);merged=left.then(right)
    points=[]
    for j in range(plan['fixtures']['queries']):
        beta=np.r_[np.sort(rng.uniform(.7,1.3,4)),rng.uniform(-.15,.15,3),rng.uniform(-.1,.1)]
        monotone(beta[:4],1);points.append(beta)
        residual=(X@beta-y)/sigma
        nll=float(.5*residual@residual+sum(np.log(sigma*math.sqrt(2*math.pi))))
        answer=full.query(beta);name=f'{family}/query{j}'
        c.close(name+'/batch_NLL',answer['nll'],nll)
        c.close(name+'/batch_gradient',answer['gradient'],X.T@((X@beta-y)/sigma**2))
        c.close(name+'/merge_NLL',merged.query(beta)['nll'],nll)
    before=signature(full)
    for beta in points:full.query(beta)
    c.ok(family+'/read_only_query',signature(full)==before)
    c.close(family+'/merge_error_ledger',merged.E2,full.E2)
    baseline=[full.query(beta) for beta in points]
    for k in range(plan['fixtures']['recenter_operations']):
        full.recenter(center+.1*np.sin(k+np.arange(8)))
    for j,beta in enumerate(points):
        answer=full.query(beta)
        c.close(f'{family}/recenter{j}/NLL',answer['nll'],baseline[j]['nll'])
        c.close(f'{family}/recenter{j}/gradient',answer['gradient'],baseline[j]['gradient'])
        c.close(f'{family}/recenter{j}/defect',answer['residual_defect_bound'],baseline[j]['residual_defect_bound'])
    lo=(.5,)*4+(-.3,)*3+(-.2,);hi=(1.5,)*4+(.3,)*3+(.2,)
    packet_results=[]
    for bits in (8,12,16):
        book=Codebook(lo,hi,bits);before=signature(full);packet=full.packet(book)
        packet=json.loads(json.dumps(packet))
        restored=Factor.restore(packet,book,full.source,full.basis_id)
        c.ok(f'{family}/codec{bits}/immutable_export',signature(full)==before)
        c.close(f'{family}/codec{bits}/ledger_preserved',restored.E2,full.E2)
        for j,beta in enumerate(points):c.close(f'{family}/codec{bits}/query{j}',restored.query(beta)['nll'],full.query(beta)['nll'])
        c.ok(f'{family}/codec{bits}/center_error',np.all(abs(restored.center-full.center)<=book.delta/2+1e-14))
        wrong=copy.deepcopy(packet);wrong['basis_id']='wrong'
        c.reject(f'{family}/codec{bits}/contract_reject',lambda:Factor.restore(wrong,book,full.source,full.basis_id))
        packet_results.append(dict(bits=bits,center_B=len(bytes.fromhex(packet['codes_hex'])),packed_factor_B=360))
    # Independent unbounded-Gaussian algebra oracle, not monotone posterior coverage.
    J=X.T@(X/sigma[:,None]**2);h=X.T@(y/sigma**2)
    prior_mean=np.zeros(8);prior_precision=np.eye(8)
    ref_cov=np.linalg.solve(J+prior_precision,np.eye(8));ref_mean=ref_cov@(h+prior_mean)
    A=full.R[:,:-1];Jf=A.T@A;hf=Jf@full.center-A.T@full.R[:,-1]
    cov=np.linalg.solve(Jf+prior_precision,np.eye(8));mean=cov@hf
    c.close(family+'/Gaussian_algebra/covariance',cov,ref_cov)
    c.close(family+'/Gaussian_algebra/mean',mean,ref_mean)
    c.ok(family+'/joint_cross_terms_present',np.max(abs(cov[:4,4:]))>1e-5)
    const_design=thermal_basis(np.full(10,25.),Tk,family)
    c.close(family+'/thermal_reference_is_unexcited',const_design,np.zeros((10,3)))
    # Temperature correlated with age makes linear trends confounded even after anchoring.
    Tt=10+30*t;Xa=basis(t,sites,'linear');Xt=thermal_basis(Tt,Tk,'linear')
    direction=np.r_[-(10+30*sites-25),Tk[:3]-Tk[3]]
    c.close(family+'/age_temperature_confounding',np.column_stack((Xa,Xt))@direction,np.zeros(n))
    return dict(family=family,records=n,dimension=8,recenter_operations=full.recenter_count,
                maximum_age_other_covariance=float(np.max(abs(cov[:4,4:]))),packets=packet_results,
                posterior_scope='Unbounded Gaussian algebra only; monotone supported posterior not integrated')


def curves(c,rng,plan):
    t=np.linspace(0,1,plan['fixtures']['curve_queries']);sites=np.linspace(0,1,4);Tk=np.linspace(-20,60,4)
    records=[]
    for family in ('linear','bernstein'):
        B=basis(t,sites,family)
        c.close(family+'/basis_partition',B.sum(axis=1),np.ones(len(t)))
        c.ok(family+'/basis_positive',np.all(B>=0))
        for bits in (8,12,16):
            agebook=Codebook((.5,)*4,(1.5,)*4,bits)
            for direction in (-1,1):
                for trial in range(8):
                    coeff=np.sort(rng.uniform(.5,1.5,4))[::direction]
                    # Sorted ascending with direction+1, descending with-1.
                    codes=agebook.encode_monotone(coeff,direction);decoded=agebook.decode(codes)
                    f=B@coeff;fq=B@decoded
                    name=f'{family}/{bits}/{direction}/{trial}'
                    c.ok(name+'/monotone',np.all(direction*np.diff(fq)>=-2e-15))
                    c.ok(name+'/curve_error_bound',np.max(abs(fq-f))<=agebook.delta[0]/2+2e-15)
                    c.ok(name+'/code_roundtrip',agebook.encode(decoded)==codes)
            age=np.array([1.,.95,.82,.7]);Tcoeff=np.array([25.,45.,5.,30.]);gcoeff=.003*(Tk[:3]-Tk[3])
            Tbook=Codebook((-20.,)*4,(60.,)*4,bits);gbook=Codebook((-.3,)*3,(.3,)*3,bits)
            ageq=agebook.decode(agebook.encode_monotone(age,-1));Tq=Tbook.decode(Tbook.encode(Tcoeff));gq=gbook.decode(gbook.encode(gcoeff))
            T=B@Tcoeff;temperature_q=B@Tq
            exact=B@age+thermal_basis(T,Tk,family)@gcoeff
            decoded=B@ageq+thermal_basis(temperature_q,Tk,family)@gq
            L=lipschitz(np.r_[gcoeff,0.],Tk,family)
            bound=float(agebook.delta[0]/2+gbook.delta[0]+L*Tbook.delta[0]/2)
            error=float(np.max(abs(exact-decoded)))
            c.ok(f'{family}/{bits}/composed_bound',error<=bound+3e-15,measured_error=error,bound=bound)
            c.close(f'{family}/{bits}/thermal_anchor',thermal_basis([25.],Tk,family)@gq,[0.])
            records.append(dict(family=family,bits=bits,age_curve_bound=float(agebook.delta[0]/2),
                temperature_path_bound_C=float(Tbook.delta[0]/2),thermal_response_bound=float(gbook.delta[0]),
                composed_bound=bound,observed_composed_error=error,
                eight_health_age_values_B=8*len(agebook.encode(age)),temperature_values_B=len(Tbook.encode(Tcoeff)),
                eight_health_thermal_values_B=8*len(gbook.encode(gcoeff))))
    c.reject('curve/order_reject',lambda:monotone([1,1.2,1.1,1.3],1))
    c.reject('curve/outside_domain',lambda:basis([1.01],sites,'linear'))
    c.reject('code/outside_range',lambda:Codebook((.5,)*4,(1.5,)*4,12).encode([.4,1,1,1]))
    c.reject('code/invalid_padding',lambda:Codebook((0.,)*3,(1.,)*3,12).decode(bytes([0,0,0,0,240])))
    # Common rounding can create ties; this remains non-strict monotonicity.
    book=Codebook((.5,)*4,(1.5,)*4,8);tie=book.decode(book.encode_monotone([1.,1.00001,1.00002,1.00003],1))
    c.ok('code/ties_valid',np.all(np.diff(tie)==0))
    return records


def failure_controls(c):
    f=Factor(np.zeros(2),'source','basis');before=signature(f)
    for name,fun in [('order',lambda:f.append([1,0],1,1,1,0,'source')),
        ('source',lambda:f.append([1,0],1,1,0,0,'wrong')),
        ('time',lambda:f.append([1,0],1,1,0,-1,'source')),
        ('sigma',lambda:f.append([1,0],1,0,0,0,'source')),
        ('nonfinite_center',lambda:f.recenter([float('nan'),0]))]:
        c.reject('atomic/'+name,fun);c.ok('atomic/'+name+'/unchanged',signature(f)==before)
    f.append([1,2],.5,.2,0,0,'source')
    c.reject('ownership/overlap',lambda:f.then(f))
    before=signature(f);f.query([0,0]);c.ok('query/immutable',signature(f)==before)
    empty=Factor([0,0],'source','basis',1,0)
    c.close('identity/no_evidence',f.then(empty).query([.2,.4])['nll'],f.query([.2,.4])['nll'])


def battery_control(c,lib,rng,plan):
    n=plan['fixtures']['battery_records'];k=np.arange(n)
    rows=np.column_stack((np.full(n,1/35),.18*np.sin(k*.13),3.7+.002*np.cos(k*.2)))
    eta,center=conditional.from_original(kernel.MEAN)
    block=conditional.build(eta,rows)
    book=Codebook((0.,)*5+(-.08,)*3+(-.1,), (1.,)*4+(.1,)+(.08,)*3+(.1,),12)
    cq=book.decode(book.encode(center));R=translate_upper(block.S,np.zeros(9),cq)
    error=[]
    for j in range(plan['fixtures']['queries']):
        x=kernel.MEAN.copy();x[6:10]=rng.uniform(0,1,4);x[10]=rng.uniform(0,.1)
        x[12:15]=rng.uniform(-.08,.08,3);x[15]=rng.uniform(-1,1)
        _,alpha=conditional.from_original(x);_,reference,_=c_replay(lib,x,rows,.001)
        residual=R@np.r_[alpha-cq,1.]
        value=float(.5*residual@residual+n*math.log(.001*math.sqrt(2*math.pi)))
        c.close('battery/recentered_C_NLL/'+str(j),value,reference,atol=2e-6)
        error.append(abs(value-reference))
    return dict(records=n,queries=len(error),maximum_NLL_difference=max(error),
                scope='Original stationary fixed-eta amplitude likelihood; no temperature or aging model modification')


def plot(dest,results):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(10,4),layout='constrained')
    t=np.linspace(0,1,401);sites=np.linspace(0,1,4);Tk=np.linspace(-20,60,4)
    B=basis(t,sites,'linear');age=B@np.array([1,.95,.82,.7]);T=B@np.array([25,45,5,30])
    total=age+thermal_basis(T,Tk,'linear')@(.003*(Tk[:3]-Tk[3]))
    axes[0].plot(t,age,label='Monotone reference-condition health')
    axes[0].plot(t,total,label='With reversible temperature effect')
    axes[0].set(xlabel='Normalized time: algebraic example',ylabel='Relative parameter',title='Keep aging and temperature separate')
    axes[0].legend(fontsize=8);axes[0].grid(alpha=.2)
    for family in ('linear','bernstein'):
        q=[r for r in results if r['family']==family]
        axes[1].semilogy([r['bits'] for r in q],[r['observed_composed_error'] for r in q],'o-',label=family+' measured')
    q=[r for r in results if r['family']=='linear']
    axes[1].semilogy([r['bits'] for r in q],[r['composed_bound'] for r in q],'k--',label='Derived quantization bound')
    axes[1].set(xlabel='Bits per coefficient',ylabel='Relative-parameter quantization error',title='Curve and model remainders are additional')
    axes[1].set_xticks([8,12,16]);axes[1].legend(fontsize=8);axes[1].grid(alpha=.2)
    fig.savefig(dest/'monotone_temperature_codebook.png',dpi=170);fig.savefig(dest/'monotone_temperature_codebook.pdf');plt.close(fig)


def main():
    p=argparse.ArgumentParser();p.add_argument('destination',type=Path);args=p.parse_args()
    dest=args.destination.resolve();dest.mkdir(parents=True,exist_ok=False)
    plan=json.loads((HERE/'plan.json').read_text())
    sources=[str(p.relative_to(ROOT)) for p in HERE.glob('*') if p.suffix in ('.json','.md','.py')]
    sources+=['src/scm_model.c','include/scm_model.h','experiments/minimal_health_kernels_001/kernel.py','experiments/partitioned_battery_closure_001/conditional.py','experiments/partitioned_battery_closure_001/witnesses.py']
    identities={s:ident(ROOT/s) for s in sorted(set(sources))};preserved={}
    for path in ['experiments/operator_envelope_001/verification.json','experiments/partitioned_battery_closure_001/verification.json','experiments/incremental_history_001/verification.json','experiments/ten_year_history_001/verification.json']:
        preserved[path]=ident(ROOT/path);preserved.update(json.loads((ROOT/path).read_text())['artifacts'])
    command=['cc','-std=c99','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC','-Iinclude','src/scm_model.c','-lm','-o',str(dest/'reference.so')]
    write(dest/'reservation.json',dict(source_identities=identities,preserved_artifacts=preserved,
          revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),branch=subprocess.check_output(['git','branch','--show-current'],text=True).strip(),
          python=platform.python_version(),numpy=np.__version__,C_build=command,
          command=['python3','-B','-m','experiments.monotone_codebook_001.qualify',str(args.destination)]))
    for s in identities:
        target=dest/'source_snapshot'/s;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/s,target)
    compiled=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
    write(dest/'build.json',dict(command=command,exit_code=compiled.returncode,stdout=compiled.stdout,stderr=compiled.stderr))
    if compiled.returncode:return 1
    lib=C.CDLL(str(dest/'reference.so'));lib.scm_physical_step.argtypes=[C.POINTER(Physical),C.POINTER(State),C.c_void_p,C.c_double,C.c_double,C.POINTER(C.c_double)];lib.scm_physical_step.restype=C.c_int
    c=Checks();rng=np.random.default_rng(plan['fixtures']['seed']);cpu=time.process_time();wall=time.perf_counter()
    evidence={}
    for family in ('linear','bernstein'):evidence[family]=c.case(family,lambda family=family:regression(c,rng,plan,family))
    evidence['curves']=c.case('curves',lambda:curves(c,rng,plan));c.case('atomic',lambda:failure_controls(c))
    evidence['battery']=c.case('battery',lambda:battery_control(c,lib,rng,plan))
    if evidence['curves'] is not None:c.case('plot',lambda:plot(dest,evidence['curves']))
    for s,expected in {**preserved,**identities}.items():c.ok('preservation/'+s,ident(ROOT/s)==expected)
    failed=[r for r in c.items if not r['passed']]
    result=dict(status='passed' if not failed else 'failed',checks=c.items,passing_checks=len(c.items)-len(failed),failed_checks=len(failed),evidence=evidence,
                cpu_seconds=time.process_time()-cpu,wall_seconds=time.perf_counter()-wall,maximum_RSS_B=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
                battery_fits=0,particle_steps=0,production_solver_changed=False,temperature_calibrated=False,
                monotone_health_kernel_implemented=False,monotone_trajectory_support_implemented=True,
                numerical_lifetime_bound=None,ten_year_certificate=False)
    write(dest/'result.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('checks','evidence')},indent=2))
    if failed:print(json.dumps(failed,indent=2))
    return bool(failed)


if __name__=='__main__':raise SystemExit(main())
