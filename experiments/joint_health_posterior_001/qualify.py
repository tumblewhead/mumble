"""Finite posterior qualification. Fixed seeds/fixtures; no truth or old runs."""
import dataclasses
import json
import math
from pathlib import Path
import sys
import traceback
import numpy as np
import model as m
import smc
import posterior
import path as scalar

HERE = Path(__file__).resolve().parent
PLAN = json.loads((HERE/'plan.json').read_text())
RESULT = dict(cases=[], checks=0, canonical_records=0, truth_reads=0,
              posterior_populations=0, target_path_evaluations=0, physical_steps=0,
              independent_review=False)
OUT = None


def check(ok, label):
    RESULT['checks'] += 1
    if not ok:
        raise AssertionError(label)


def close(a, b, label, atol=1e-10, rtol=1e-10):
    check(np.allclose(a, b, atol=atol, rtol=rtol), label+': '+str(np.max(abs(np.asarray(a)-b))))


def save(path, value):
    def convert(v):
        if isinstance(v, np.ndarray):return v.tolist()
        if isinstance(v, np.generic):return v.item()
        raise TypeError(type(v).__name__)
    with path.open('x') as f:
        json.dump(value, f, indent=2, default=convert, allow_nan=False)
        f.write('\n')


def case(fn):
    before = RESULT['checks']
    row = dict(name=fn.__name__, status='failed')
    try:
        row['diagnostics'] = fn()
        row['status'] = 'passed'
    except Exception:
        row['error'] = traceback.format_exc()
    row['checks'] = RESULT['checks']-before
    RESULT['cases'].append(row)
    save(OUT/(fn.__name__+'.json'), row)
    print(json.dumps({n:row[n] for n in ('name','status','checks')}), flush=True)


def account(target):
    RESULT['target_path_evaluations'] += getattr(target, 'path_evaluations', 0)
    RESULT['physical_steps'] += getattr(target, 'model_steps', 0)
    check(RESULT['physical_steps'] <= PLAN['caps']['physical_steps_total'], 'total physical-step cap')


def records(dynamic=True):
    name = 'dynamic_records' if dynamic else 'stationary_records'
    return tuple(m.k.Record('fixture', n, *row) for n, row in enumerate(PLAN['qualification'][name]))


def profile(dynamic=True):
    return m.k.Profile(tuple(PLAN['qualification']['dynamic_rates' if dynamic else 'stationary_rates']))


def run_refinement(factory, name, scales):
    result=posterior.refine(factory,scales,registered_study(),
        lambda n,seed,p:retain_population(name,n,seed,p),account)
    save(OUT/(name+'_summary.json'),result)
    return result['levels'][-1],result['adequacy'],None


def registered_study():
    cfg=PLAN['numerics']
    return posterior.Study(tuple(cfg['full_particle_levels']),
        (tuple(cfg['full_population_seeds_low']),tuple(cfg['full_population_seeds_high'])),
        cfg['mutations_per_stage'],cfg['proposal_factor'])


def retain_population(name,n,seed,result):
    RESULT['posterior_populations']+=1
    np.savez_compressed(OUT/(name+f'_n{n}_seed{seed}.npz'),
                        particles=result['particles'],projected=result['projected'])
    save(OUT/(name+f'_n{n}_seed{seed}.json'),{k:v for k,v in result.items() if k not in ('particles','projected')})


def full_path_parity():
    gaps = []
    for dynamic in (False, True):
        target = m.Target(records(dynamic), profile(dynamic))
        samples = target.draw(np.random.default_rng(311), 24)
        lp, ll, projected = target.evaluate(samples)
        for j, u in enumerate(samples):
            x, free = target.centered_path(u)
            ref = scalar.evaluate(x, target.records, target.profile, free)
            gap = abs(lp[j]+ll[j]+ref['nll']-target.log_jacobian)
            gaps.append(gap)
            close(lp[j]+ll[j], -ref['nll']+target.log_jacobian, 'chart Jacobian/density', atol=1e-7, rtol=0)
            close(projected[j, 5:7], ref['state'].health, 'current health')
            close(projected[j, 11:16], ref['state'].fast, 'current physical state')
        check(target.dimension == (24 if dynamic else 16), 'full path dimension')
        account(target)
    for mean, variance in [(-40.,1.),(0.,.01),(.4,1e-12),(41.,1.),(-80.,1.)]:
        close(m.log_normalizer(np.array([mean]), variance, 0., 1.)[0],
              m.k.normalizer(mean, variance, 0., 1.).log_Z, 'tail fallback parity', atol=1e-10)
    return dict(max_density_gap_NLL=max(gaps))


def original_prior_moments():
    x = m.initial_draw(np.random.default_rng(7001), PLAN['qualification']['prior_draws'])
    nodes, weights = m.k.gauss(192)
    max_z = 0.
    for j in range(16):
        values = (m.k.LOW[j]+m.k.HIGH[j])/2+(m.k.HIGH[j]-m.k.LOW[j])/2*nodes
        if j == 5:
            density = sum(np.exp(-.5*((values-c)/m.Q_SD)**2)/m.Q_SD for c in m.Q_MEANS)/2
        else:
            density = np.exp(-.5*((values-m.k.MEAN[j])/m.k.SD[j])**2)/m.k.SD[j]
        mass = weights*density
        mass /= mass.sum()
        mean = float(mass@values)
        variance = float(mass@((values-mean)**2))
        score = abs(x[:, j].mean()-mean)/math.sqrt(variance/len(x))
        max_z = max(max_z, score)
        check(score < 5, 'original bounded prior mean '+str(j))
        check(abs(x[:, j].var()-variance) < .05*variance, 'prior variance '+str(j))
    check(np.all(x >= m.k.LOW) and np.all(x <= m.k.HIGH), 'prior support')
    return dict(draws=len(x), max_mean_error_standard_errors=max_z)


class Gaussian:
    dimension = 2
    covariance = np.array([[1.,.8],[.8,1.]])
    precision = np.linalg.inv(covariance)

    def draw(self, rng, n):return rng.multivariate_normal([0.,0.], self.covariance, n)

    def evaluate(self, u):
        prior = -.5*np.sum((u@self.precision)*u, axis=1)-.5*math.log(np.linalg.det(self.covariance))-m.LOG2PI
        like = -.5*(u[:,0]-1.)**2/.5-.5*math.log(math.pi)
        return prior, like, u.copy()


def known_mean_covariance(summary, mean, covariance, label):
    sd = np.sqrt(np.diag(covariance))
    check(np.all(abs(summary['mean']-mean) <= np.maximum(5*summary['mean_MCSE'], .04*sd)), label+' mean')
    check(np.all(abs(summary['covariance']-covariance) <= np.maximum(
        5*summary['covariance_MCSE'], .06*np.outer(sd,sd))), label+' covariance')


def correlated_gaussian():
    result, adequate, _ = run_refinement(Gaussian, 'gaussian', np.ones(2))
    covariance = np.linalg.inv(Gaussian.precision+np.diag([2.,0.]))
    mean = covariance@np.array([2.,0.])
    known_mean_covariance(result, mean, covariance, 'conjugate correlated posterior')
    check(adequate['status'] == 'finite_moment_checks_passed', 'Gaussian numerical adequacy')
    check(result['mean'][1] > .4, 'correlation-mediated health update retained')
    return adequate


class Mixture:
    dimension = 1
    means = np.array([-3.,3.])
    masses = np.array([.3,.7])
    def draw(self, rng, n):return (self.means[rng.choice(2,n,p=self.masses)]+.5*rng.normal(size=n))[:,None]
    def evaluate(self, u):
        terms = np.log(self.masses)-.5*((u-self.means)/.5)**2-math.log(.5)-.5*m.LOG2PI
        prior = np.logaddexp(terms[:,0],terms[:,1])
        like = -.5*((u[:,0]-.4)/2.)**2-math.log(2)-.5*m.LOG2PI
        responsibilities = np.exp(terms[:,0]-prior)
        return prior, like, np.column_stack((u[:,0],responsibilities))


def mixture_mass_control():
    result, adequate, _ = run_refinement(Mixture, 'mixture', np.ones(2))
    mass = Mixture.masses*np.exp(-.5*(.4-Mixture.means)**2/4.25)
    mass /= mass.sum()
    variances = 1/(4+1/4)
    means = variances*(4*Mixture.means+.4/4)
    mean = float(mass@means)
    variance = float(mass@(variances+(means-mean)**2))
    check(abs(result['mean'][0]-mean) <= max(5*result['mean_MCSE'][0],.04*math.sqrt(variance)), 'mixture marginal mean')
    check(abs(result['mean'][1]-mass[0]) <= max(5*result['mean_MCSE'][1], .01), 'relative integrated mode mass')
    check(abs(result['covariance'][0,0]-variance) <= max(5*result['covariance_MCSE'][0,0], .06*variance), 'mixture variance')
    check(adequate['status'] == 'finite_moment_checks_passed', 'mixture numerical adequacy')
    return dict(adequacy=adequate, exact_low_mode_probability=float(mass[0]), estimated_low_mode_probability=float(result['mean'][1]))


class ScalarR:
    dimension = 2
    def draw(self,rng,n):
        x = rng.uniform(.1,.2,n)
        y = m.truncated_draw(rng,x,.02,0.,1.)
        return np.column_stack((x,y))
    def evaluate(self,u):
        good=(u[:,0]>=.1)&(u[:,0]<=.2)&(u[:,1]>=0)&(u[:,1]<=1)
        prior=np.full(len(u),-np.inf)
        prior[good]=-math.log(.1)-.5*((u[good,1]-u[good,0])/.02)**2-math.log(.02)-.5*m.LOG2PI-m.log_normalizer(u[good,0],.0004,0.,1.)
        like=-.5*((u[:,1]-.12)/.03)**2-math.log(.03)-.5*m.LOG2PI
        return prior,like,u.copy()


def scalar_marginal_quadrature():
    result, adequate, _ = run_refinement(ScalarR, 'scalar_r', np.ones(2))
    nodes,w=m.k.gauss(128)
    x=.15+.05*nodes
    y=.5+.5*nodes
    xx,yy=np.meshgrid(x,y,indexing='ij')
    # Independent direct erf normalization and tensor quadrature.
    z=np.array([.5*(math.erf((1-v)/(.02*math.sqrt(2)))-math.erf(-v/(.02*math.sqrt(2)))) for v in x])
    mass=w[:,None]*w[None,:]*np.exp(-.5*((yy-xx)/.02)**2-.5*((yy-.12)/.03)**2)/z[:,None]
    mass/=mass.sum()
    mean=np.array([(mass*xx).sum(),(mass*yy).sum()])
    covariance=np.array([[(mass*(a-mean[i])*(b-mean[j])).sum() for j,b in enumerate((xx,yy))] for i,a in enumerate((xx,yy))])
    known_mean_covariance(result,mean,covariance,'bounded scalar integrated posterior')
    check(adequate['status']=='finite_moment_checks_passed','scalar numerical adequacy')
    return adequate


SCALES = np.r_[m.k.SD, .06, 1., .06, 1.]


def stationary_joint_posterior():
    result, adequate, _ = run_refinement(lambda:m.Target(records(False),profile(False)), 'stationary', SCALES)
    check(adequate['status']=='finite_moment_checks_passed','stationary joint numerical adequacy')
    check(np.all(np.diag(result['covariance'])[:16]>0), 'all16 current quantities uncertain')
    check(abs(result['covariance'][11,12])>1e-7,'SOC/initial-polarization correlation retained')
    return adequate


def dynamic_joint_posterior():
    rs=records()
    result=posterior.solve(rs,profile(),registered_study(),
        lambda name,n,seed,p:retain_population('dynamic_'+name,n,seed,p),account)
    pa,qa=result['prediction']['adequacy'],result['conditioning']['adequacy']
    save(OUT/'dynamic_prediction_summary.json',result['prediction'])
    save(OUT/'dynamic_conditioned_summary.json',result['conditioning'])
    save(OUT/'boundary_report.json',result['report'])
    check(pa['status']=='finite_moment_checks_passed','predictive joint numerical adequacy')
    check(qa['status']=='finite_moment_checks_passed','conditioned joint numerical adequacy')
    check(np.all(np.diag(result['report']['current_covariance'])[:16]>0),'all16 dynamic quantities uncertain')
    check(result['report']['posterior_numerical_status']=='finite_moment_checks_passed','public solver status')
    check(result['report']['valid_observation_count']==4 and result['report']['owns_initial_prior'], 'public ownership')
    return dict(prediction=pa,posterior=qa,report='boundary_report.json')


def failures():
    def rejects(fn,status):
        try:fn()
        except m.k.ModelError as exc:check(exc.status==status,'expected '+status+' got '+exc.status)
        else:check(False,'missing '+status)
    rs=records()
    rejects(lambda:m.Target((dataclasses.replace(rs[0],index=2),),profile()),'source_order_error')
    rejects(lambda:m.Target((dataclasses.replace(rs[0],input_known=False),),profile()),'recovery_required')
    rejects(lambda:smc.population(Gaussian(),smc.Config(32,max_stages=1),33),'resource_limit')
    rejects(lambda:m.truncated_draw(np.random.default_rng(1),np.array([-40.]),1.,0.,1.,2),'sampling_unresolved')
    rejects(lambda:smc.weights(np.array([-np.inf,-np.inf])),'uncertainty_unresolved')
    rejects(lambda:m.Target(rs,profile(),max_paths=1).draw(np.random.default_rng(1),32),'resource_limit')
    rejects(lambda:posterior.Study(seeds=((1,2,3,4),(1,2,3,4))),'invalid_input')
    rejects(lambda:posterior.solve((dataclasses.replace(rs[0],input_known=False),),profile()),'recovery_required')
    result=smc.population(Gaussian(),smc.Config(64),91)
    check(result['posterior_numerical_status']=='requires_independent_replication','single run cannot claim adequacy')
    result2=smc.population(Gaussian(),smc.Config(64),91)
    close(result['particles'],result2['particles'],'seeded reproducibility',atol=0,rtol=0)
    a=smc.level([result]*4);b={key:(value.copy() if isinstance(value,np.ndarray) else value) for key,value in a.items()}
    b['mean']=b['mean']+2.
    check(smc.assess(a,b,np.ones(2))['status']=='uncertainty_unresolved','refinement discrepancy stays unresolved')
    return dict(automatic_retries=0,silent_fallbacks=0)


def main(out):
    global OUT
    OUT=out
    for fn in (full_path_parity,original_prior_moments,correlated_gaussian,mixture_mass_control,
               scalar_marginal_quadrature,stationary_joint_posterior,dynamic_joint_posterior,failures):
        case(fn)
    RESULT['status']='passed' if all(c['status']=='passed' for c in RESULT['cases']) else 'failed'
    save(OUT/'checks.json',RESULT)
    print(json.dumps({key:RESULT[key] for key in ('status','checks','posterior_populations','physical_steps')}),flush=True)
    return 0 if RESULT['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1])))
