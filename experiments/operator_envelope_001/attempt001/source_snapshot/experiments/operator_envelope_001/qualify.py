"""Finite envelope and centroid controls. No battery fit or particle inference."""
import argparse
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
from experiments.partitioned_battery_closure_001.witnesses import Physical, State, c_replay
from .envelope import Envelope, build
from .centroid import Statistics, basis

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def ident(p):
    raw = p.read_bytes()
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def write(p, obj):
    with p.open('x') as f:
        json.dump(obj, f, indent=2, allow_nan=False); f.write('\n')


class Census:
    def __init__(self): self.checks = []
    def check(self, name, ok, **details):
        self.checks.append(dict(name=name, passed=bool(ok), **details))
    def close(self, name, a, b, atol=2e-11, rtol=2e-10):
        a, b = np.asarray(a), np.asarray(b)
        self.check(name, np.isfinite(a).all() and np.all(abs(a-b) <= atol+rtol*abs(b)),
                   maximum_absolute_error=float(np.max(abs(a-b), initial=0.)))
    def reject(self, name, fun):
        try: fun()
        except ValueError: self.check(name, True)
        else: self.check(name, False)
    def case(self, name, fun):
        try: return fun()
        except Exception: self.check(name+'/exception', False, traceback=traceback.format_exc())


def signature(obj): return hashlib.sha256(pickle.dumps(obj)).hexdigest()


def domains():
    ix = [0,1,2,3,4,11,5]
    m, lo, hi = kernel.MEAN[ix].copy(), kernel.LOW[ix].copy(), kernel.HIGH[ix].copy()
    half = .01*(hi-lo)
    return m, [('public', lo, hi), ('conditional', m-half, m+half), ('singleton', m, m)]


def records(kind, n):
    k = np.arange(n)
    # The four-step cycle cancels signed charge using matching real intervals.
    dt = np.array([.027, .031, .027, .031])[k % 4]
    current = np.zeros(n) if kind == 'rest' else np.array([.18, -.12, -.18, .12])[k % 4]
    voltage = 3.7+(.003*np.sin(k*.4) if kind == 'mixed' else np.zeros(n))
    return np.column_stack((dt, current, voltage))


def field_case(c, lib, rng, label, kind, n, m, lo, hi, queries):
    rows = records(kind, n); f = build(m, lo, hi, rows)
    before = signature(f); observed = []; ratios = []
    # Non-cycle-aligned split exercises entering SOC and uncertain carry.
    split = 17
    a = build(m, lo, hi, rows[:split])
    blo, bhi = lo.copy(), hi.copy(); blo[5], bhi[5] = a.soc_range()
    b = build(a.node.next_eta, blo, bhi, rows[split:], split, .25)
    merged = a.then(b)
    c.check(f'{label}/{kind}/{n}/retained_size', f.node.S.shape == (10,10) and f.exit_error.shape == (4,))
    c.check(f'{label}/{kind}/{n}/no_spent_error_reset', merged.E2+1e-20 >= a.E2)
    for j in range(queries):
        eta = m.copy() if j == 0 else rng.uniform(lo, hi)
        x = kernel.MEAN.copy(); x[:5] = eta[:5]; x[11] = eta[5]; x[5] = eta[6]
        x[6:10] = rng.uniform(0, 1, 4); x[10] = rng.uniform(0, .1)
        x[12:15] = rng.uniform(-.08, .08, 3); x[15] = rng.uniform(-1, 1)
        alpha = np.r_[x[6:11], x[12:15], x[10]*x[15]]
        _, exact, endpoint = c_replay(lib, x, rows, .001)
        name = f'{label}/{kind}/{n}/query{j}'
        answer = f.query(eta, alpha); ma = merged.query(eta, alpha)
        tolerance = 2e-6+2e-10*abs(exact)
        error = abs(answer['nll']-exact); observed.append(error)
        c.check(name+'/likelihood_enclosure', error <= answer['representation_bound']+tolerance,
                observed_error=error, bound=answer['representation_bound'], numerical_allowance=tolerance)
        c.check(name+'/merged_enclosure', abs(ma['nll']-exact) <= ma['representation_bound']+tolerance)
        c.close(name+'/reference_merge', answer['nll'], ma['nll'], atol=2e-6)
        physical = np.r_[endpoint[1:4], x[10]*endpoint[4]]
        c.check(name+'/outgoing_enclosure', np.all(abs(answer['outgoing_v_Hh']-physical) <= answer['outgoing_error']+2e-11))
        c.check(name+'/merged_outgoing_enclosure', np.all(abs(ma['outgoing_v_Hh']-physical) <= ma['outgoing_error']+2e-11))
        c.close(name+'/SOC_exact_chart', answer['SOC'], endpoint[0])
        c.check(name+'/uniform_bound', answer['representation_bound'] <= f.uniform_bound()+tolerance)
        if answer['representation_bound'] > 0: ratios.append(error/answer['representation_bound'])
    c.check(f'{label}/{kind}/{n}/query_immutable', before == signature(f))
    c.reject(f'{label}/{kind}/{n}/out_of_domain', lambda:f.query(hi+1, np.zeros(9)))
    c.reject(f'{label}/{kind}/{n}/overlap', lambda:f.then(f))
    return dict(domain=label, stimulus=kind, records=n, elapsed_s=f.node.elapsed,
                uniform_NLL_bound=f.uniform_bound(), E2=f.E2, maximum_observed_NLL_error=max(observed),
                maximum_error_to_query_bound_ratio=max(ratios, default=None),
                outgoing_error_V=f.exit_error.tolist(), merge_E2=merged.E2,
                logical_payload_B=816, numerical_certificate=False)


def failures(c):
    m, dd = domains(); lo, hi = dd[1][1:]
    f = Envelope(m, lo, hi); before = signature(f)
    for label, fun in [('index',lambda:f.append([.03,0,3.7],1)),
                       ('source',lambda:f.append([.03,0,3.7],0,'wrong')),
                       ('invalid_dt',lambda:f.append([-1,0,3.7],0)),
                       ('nan',lambda:f.append([.03,0,float('nan')],0))]:
        c.reject('atomic/'+label, fun); c.check('atomic/'+label+'/unchanged', before == signature(f))
    z = m.copy(); z[5] = .00001
    tiny = Envelope(z,z,z); before = signature(tiny)
    c.reject('atomic/domain_exit',lambda:tiny.append([1,.25,3.7],0))
    c.check('atomic/domain_exit/unchanged', signature(tiny) == before)
    data = records('mixed', 32); actual = build(m, lo, hi, data)
    empty = Envelope(m,lo,hi)
    c.close('identity/left',empty.then(actual).node.S.T@empty.then(actual).node.S,actual.node.S.T@actual.node.S,atol=2e-6)
    c.close('identity/no_error_added',empty.then(actual).E2,actual.E2)


def centroid_controls(c):
    knots = np.linspace(0,1,4); times = np.linspace(0,1,97); B = basis(times,knots)
    c.close('spline/partition_of_unity',B@np.ones(4),np.ones(len(times)))
    c.close('spline/linear_reproduction',B@knots,times)
    c.close('spline/knots',basis(knots,knots),np.eye(4))
    c.reject('spline/no_future_extrapolation',lambda:basis([1.1],knots))
    # These are unique fabricated observations, not inferred battery centroids.
    y = 1+.2*times+.01*np.sin(17*times); variance=.04
    stat = Statistics(knots)
    for i,(t,v) in enumerate(zip(times,y)):stat.append(float(t),float(v),variance,i)
    c.close('statistics/batch_Gram',stat.A,B.T@B/variance)
    c.close('statistics/batch_rhs',stat.h,B.T@y/variance)
    c.close('statistics/batch_constant',stat.c,y@y/variance)
    beta=np.linalg.solve(stat.A,stat.h)
    c.close('statistics/batch_coefficient',beta,np.linalg.lstsq(B,y,rcond=None)[0])
    A,h,energy=stat.centered(beta)
    offsets=[np.zeros(4),np.array([.01,-.02,.02,0.])]
    for i,d in enumerate(offsets):
        c.close('statistics/recenter/'+str(i),.5*(d@A@d-2*h@d+energy),.5*np.sum((y-B@(beta+d))**2)/variance)
    before=signature(stat)
    c.reject('statistics/overlap_rejected',lambda:stat.append(.5,1.,variance,0))
    c.check('statistics/overlap_atomic',signature(stat)==before)
    # A joint Gaussian translation needs center/residual covariance.
    cov=np.array([[.04,-.018],[-.018,.01]])
    full=float(np.ones(2)@cov@np.ones(2)); independent=float(np.trace(cov))
    c.check('centroid/joint_covariance_positive',np.linalg.eigvalsh(cov)[0]>0)
    c.close('centroid/cross_term_identity',full,.04+.01-2*.018)
    c.check('centroid/independence_changes_uncertainty',independent>3*full)
    # Exact coordinate shift in a correlated Gaussian observation model.
    x=np.array([.4,.7]); center=np.array([.2,.3]); J=np.array([[3.,1.],[1.,2.]])
    h0=np.array([.1,.2]); c0=.9; u=x-center
    shifted_h=h0-J@center; shifted_c=c0+.5*center@J@center-h0@center
    c.close('centroid/exact_chart_likelihood',.5*x@J@x-h0@x+c0,.5*u@J@u-shifted_h@u+shifted_c)
    grid=np.linspace(0,1,1201)
    first=1+.3*grid; second=first+.01*np.sin(6*math.pi*grid)
    interpolant=basis(grid,knots)@(1+.3*knots)
    knot2=1+.3*knots+.01*np.sin(6*math.pi*knots)
    c.close('trajectory/same_four_values',knot2,1+.3*knots)
    c.check('trajectory/monotone_within_30percent',.3-.06*math.pi>0 and min(second)>=1-1e-14 and max(second)<=1.3+1e-14)
    maximum=float(np.max(abs(second-interpolant)))
    c.close('trajectory/four_knots_miss_one_percent',maximum,.01)
    M=.01*(6*math.pi)**2; linear_bound=M*(1/3)**2/8
    linear=np.interp(grid,knots,knot2)
    c.check('trajectory/linear_curvature_bound',np.max(abs(second-linear))<=linear_bound)
    return dict(knots=knots.tolist(),hidden_monotone_curve_error=maximum,
                piecewise_linear_bound_under_declared_curvature=linear_bound,
                joint_current_variance=full, incorrectly_independent_variance=independent,
                spline_is_selected_battery_law=False, deterministic_curve_values_B=256,
                shared_knot_times_B=32, dense_joint_8health_example_B=6912,
                fitted_control_coefficients=beta.tolist())


def figure(dest, rows):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes=plt.subplots(1,2,figsize=(10,4),layout='constrained')
    for domain in ('public','conditional'):
        for stimulus in ('rest','mixed'):
            points=[r for r in rows if r and r['domain']==domain and r['stimulus']==stimulus]
            axes[0].loglog([r['records'] for r in points],[r['uniform_NLL_bound'] for r in points],marker='o',label=domain+' / '+stimulus)
    axes[0].set(xlabel='Owned records',ylabel='Uniform real-arithmetic NLL bound',title='Bounded storage does not bound lifetime error')
    axes[0].legend(fontsize=8);axes[0].grid(alpha=.2)
    t=np.linspace(0,1,1201);k=np.linspace(0,1,4)
    axes[1].plot(t,1+.3*t,label='Four-knot spline / path 1')
    axes[1].plot(t,1+.3*t+.01*np.sin(6*np.pi*t),label='Path 2: also smooth and monotone')
    axes[1].scatter(k,1+.3*k,color='black',label='Identical knot values',zorder=3)
    axes[1].set(xlabel='Normalized time (mathematical control)',ylabel='Relative health quantity',title='A smooth center still needs a remainder bound')
    axes[1].legend(fontsize=8);axes[1].grid(alpha=.2)
    fig.savefig(dest/'envelope_and_centroid.png',dpi=170)
    fig.savefig(dest/'envelope_and_centroid.pdf');plt.close(fig)


def main():
    p=argparse.ArgumentParser();p.add_argument('destination',type=Path);args=p.parse_args()
    dest=args.destination.resolve();dest.mkdir(parents=True,exist_ok=False)
    plan=json.loads((HERE/'plan.json').read_text())
    sources=[str(p.relative_to(ROOT)) for p in HERE.glob('*') if p.suffix in ('.py','.json','.md')]
    sources += ['experiments/partitioned_battery_closure_001/conditional.py','experiments/partitioned_battery_closure_001/witnesses.py','experiments/minimal_health_kernels_001/kernel.py','src/scm_model.c','include/scm_model.h']
    preserved={}
    for v in ['experiments/partitioned_battery_closure_001/verification.json','experiments/incremental_history_001/verification.json','experiments/ten_year_history_001/verification.json']:
        preserved[v]=ident(ROOT/v);preserved.update(json.loads((ROOT/v).read_text())['artifacts'])
    identities={s:ident(ROOT/s) for s in sorted(set(sources))}
    command=['cc','-std=c99','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC','-Iinclude','src/scm_model.c','-lm','-o',str(dest/'reference.so')]
    write(dest/'reservation.json',dict(source_identities=identities,preserved_artifacts=preserved,
          revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
          branch=subprocess.check_output(['git','branch','--show-current'],text=True).strip(),
          python=platform.python_version(),numpy=np.__version__,C_build=command,
          command=['python3','-B','-m','experiments.operator_envelope_001.qualify',str(args.destination)]))
    for s in identities:
        target=dest/'source_snapshot'/s;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/s,target)
    compiled=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
    write(dest/'build.json',dict(command=command,exit_code=compiled.returncode,stdout=compiled.stdout,stderr=compiled.stderr))
    if compiled.returncode:return 1
    lib=C.CDLL(str(dest/'reference.so'))
    lib.scm_physical_step.argtypes=[C.POINTER(Physical),C.POINTER(State),C.c_void_p,C.c_double,C.c_double,C.POINTER(C.c_double)]
    lib.scm_physical_step.restype=C.c_int
    cpu=time.process_time();wall=time.perf_counter();c=Census();rng=np.random.default_rng(plan['fixture_seed'])
    m,ds=domains();results=[]
    for label,lo,hi in ds:
        for kind in ('mixed','rest'):
            for n in plan['prefixes']:
                results.append(c.case(label+'/'+kind+'/'+str(n),lambda label=label,lo=lo,hi=hi,kind=kind,n=n:field_case(c,lib,rng,label,kind,n,m,lo,hi,plan['query_points_per_domain'])))
    c.case('atomic',lambda:failures(c))
    centroid=c.case('centroid',lambda:centroid_controls(c))
    c.case('figure',lambda:figure(dest,results))
    for s,expected in {**preserved,**identities}.items():c.check('preservation/'+s,ident(ROOT/s)==expected)
    failed=[q for q in c.checks if not q['passed']]
    result=dict(status='passed' if not failed else 'failed',checks=c.checks,
                passing_checks=len(c.checks)-len(failed),failed_checks=len(failed),field_cases=results,centroid=centroid,
                cpu_seconds=time.process_time()-cpu,wall_seconds=time.perf_counter()-wall,
                maximum_RSS_B=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
                battery_fits=0,particle_steps=0,production_solver_changed=False,
                rigorous_numerical_enclosure=False,ten_year_certificate=False,aging_model_selected=False)
    write(dest/'result.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('checks','field_cases','centroid')},indent=2))
    if failed:print(json.dumps(failed,indent=2))
    return bool(failed)


if __name__=='__main__':raise SystemExit(main())
