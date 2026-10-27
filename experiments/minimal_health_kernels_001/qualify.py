"""Finite fabricated qualification; independent formulas, no canonical inputs."""
import dataclasses
from decimal import Decimal, localcontext
import importlib.util
import json
import math
from pathlib import Path
import pickle
import sys
import traceback
import numpy as np
import kernel as k
import path as target

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location('oracle', ROOT/
    'experiments/live_anchor_integration_001/qualification/independent_oracle.py')
oracle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)
RESULT = dict(cases=[], checks=0, posterior_quadrature_evaluations=0,
              canonical_records=0, posterior_solver_calls=0, independent_reviewer=False)


def check(ok, label):
    RESULT['checks'] += 1
    if not ok:
        raise AssertionError(label)


def close(a, b, label, atol=1e-10, rtol=1e-10):
    check(np.allclose(a, b, atol=atol, rtol=rtol),
          label + ': max gap ' + str(float(np.max(abs(np.asarray(a)-np.asarray(b))))))


def rejects(fn, status):
    try:
        fn()
    except k.ModelError as exc:
        check(exc.status == status, 'expected '+status+', got '+exc.status)
    else:
        check(False, 'missing '+status)


def case(fn):
    row = dict(name=fn.__name__, status='failed')
    before = RESULT['checks']
    try:
        row['diagnostics'] = fn()
        row['status'] = 'passed'
    except Exception:
        row['error'] = traceback.format_exc()
    row['checks'] = RESULT['checks']-before
    RESULT['cases'].append(row)
    print(json.dumps(row), flush=True)


def records():
    return [k.Record('fixture', j, dt, i, v) for j, (dt, i, v) in enumerate([
        (.03, .07, 3.85), (0., -.02, 3.86), (.04, -.08, 3.87),
        (.2, 0., 3.86), (.8, .12, 3.84)])]


def stationary_equivalence():
    stationary = k.Profile((0.,)*8)
    rs = records()
    samples = [[r.dt, r.current, r.voltage] for r in rs]
    max_v = 0.
    for logq in (-3.0907210901048416, k.MEAN[5], -2.536100343415231):
        x = k.MEAN.copy()
        x[5], x[12:15], x[15] = logq, [.01, -.02, .03], -.3
        got = target.evaluate(x, rs, stationary)
        ref = oracle.block_ad(x, samples, k.SIGMA)
        pr, _ = oracle.public_prior_ad(x)
        close(got['prior_nll'], pr.v, 'original mixture prior')
        close(got['nll'], pr.v+ref['cost'].v+len(rs)*math.log(k.SIGMA*math.sqrt(2*math.pi)),
              'normalized stationary path density', atol=1e-7)
        close(got['gradient']*k.SD, (np.array(pr.g)+ref['cost'].g)*k.SD,
              'stationary gradient', atol=1e-7, rtol=1e-5)
        for row, rr in zip(got['rows'], ref['rows']):
            max_v = max(max_v, abs(row['voltage']-rr['voltage'].v))
            close(row['voltage'], rr['voltage'].v, 'stationary voltage')
            close(row['fast'], [rr['SOC'].v]+[v.v for v in rr['v']]+[rr['h'].v], 'fast states')
        check(got['free_health_coordinates'] == (), 'zero variance removes path dimensions')
        check(got['owns_initial_prior'] and got['transition_nll'] == 0, 'ownership and Dirac')
    close(k.MEAN, oracle.PUBLIC_MEAN, 'public constants mean', atol=0, rtol=0)
    close(k.SD, oracle.PUBLIC_SD, 'public constants SD', atol=0, rtol=0)
    return dict(max_voltage_difference_V=max_v, samples=len(rs), points=3)


def physical_ledger_and_local_derivatives():
    x = k.MEAN.copy()
    x[11], x[5], x[12:15], x[15] = .6, math.log(.06), [.01, -.02, .03], -.2
    state = k.initial_state(x, 'fixture')
    original_q = state.fast[0]*math.exp(state.health[0])
    max_balance = 0.
    for j, (dt, current, q, r0) in enumerate([(1., 0., .059, .1),
            (1., .1, .058, .12), (.43, -.08, .057, .13), (0., .03, .057, .13)]):
        record = k.Record('fixture', j, dt, current, None, False)
        old = state
        state, mu, jac, vg = k.advance(old, record, (math.log(q), r0))
        # Independently differentiated voltage-state equations with the same
        # 16 local inputs, without invoking candidate algebra.
        a = [oracle.AD.variable(v, n) for n, v in enumerate(
            old.fast+old.static+(math.log(q), r0))]
        z = a[0]-current*dt/3600./a[14].exp()
        v = []
        for n in range(3):
            e = (-dt/a[5+n].exp()).exp()
            v.append(e*a[1+n]+(1-e)*a[10+n]*current)
        h = a[4]
        if dt and current:
            idx = 8 if current > 0 else 9
            e = (-a[idx].exp()*abs(current)*dt/3600.).exp()
            h = e*h+(1-e)*(1 if current > 0 else -1)
        ref = 3+1.15*z+.08*(8*(z-.5)).tanh()-current*a[15]-sum(v)-a[13]*h
        close(mu, ref.v, 'local physical voltage')
        close(vg, ref.g, 'local analytic voltage gradient', atol=1e-7, rtol=1e-5)
        close(jac, [s.g for s in [z]+v+[h]], 'local state Jacobian', atol=1e-7, rtol=1e-5)
        balance = state.fast[0]*q-original_q-state.availability_charge_Ah+state.terminal_charge_Ah
        max_balance = max(max_balance, abs(balance))
        close(balance, 0, 'cumulative accessible charge identity', atol=1e-12, rtol=0)
        if j == 0:
            close(state.fast[0], .6, 'Q-only rest leaves SOC unchanged')
            close(state.availability_charge_Ah, -.0006, 'availability ledger', atol=1e-12)
        if dt == 0:
            close(state.fast, old.fast, 'dt zero identity', atol=0, rtol=0)
    record = k.Record('fixture', 0, 0., .1, None, False)
    start = k.initial_state(x, 'fixture')
    a, va, _, _ = k.advance(start, record, start.health)
    b, vb, _, _ = k.advance(start, record, (start.health[0], .2))
    close(a.fast, b.fast, 'R0-only map leaves fast state')
    close(vb-va, -.01, 'R0 ohmic change')
    return dict(max_charge_balance_error_Ah=max_balance)


def decimal_tail(a, b, order=8192):
    # Independent high precision composite Simpson integration; exp relative
    # to lower standardized bound, with no normal-CDF subtraction.
    with localcontext() as context:
        context.prec = 70
        a, b = Decimal(str(a)), Decimal(str(b))
        step = (b-a)/order
        mass = moment = Decimal(0)
        for j in range(order+1):
            t = a+j*step
            w = 1 if j in (0, order) else (4 if j % 2 else 2)
            density = ((a*a-t*t)/2).exp()
            mass += w*density
            moment += w*density*t
        mass *= step/3
        moment *= step/3
        return float(mass.ln()-a*a/2-Decimal(str(2*math.pi)).ln()/2), float(moment/mass-a)


def transition_normalization_and_derivatives():
    diagnostics = []
    for mu, variance, lo, hi, y in [(.4, .01, 0., 1., .43),
            (0., .01, 0., 1., .03), (1., .01, 0., 1., .97),
            (-40., 1., 0., 1., .02), (41., 1., 0., 1., .98),
            (-80., 1., 0., 1., .01), (.4, 1e-14, 0., 1., .40000003)]:
        n = k.normalizer(mu, variance, lo, hi)
        x, weights = k.gauss(192)
        # Independent outer density integration restricted to +/-12 SD for
        # a very narrow interior kernel; excluded mass < 4e-33.
        left, right = max(lo, mu-12*math.sqrt(variance)), min(hi, mu+12*math.sqrt(variance))
        if left >= right:
            left, right = lo, hi
        nodes = (left+right)/2+(right-left)/2*x
        vals = np.array([math.exp(-k.transition(.5, float(z), mu-.5, variance, lo, hi)[0])
                         for z in nodes])
        total = float(weights@vals)*(right-left)/2
        close(total, 1., 'bounded density integrates to one', atol=1e-8, rtol=0)
        got = k.transition(.5, y, mu-.5, variance, lo, hi)
        # Vary previous while increment stays fixed: includes d log Z / d mu.
        eps = 2e-5*math.sqrt(variance)
        fp = k.transition(.5+eps, y, mu-.5, variance, lo, hi)[0]
        fm = k.transition(.5-eps, y, mu-.5, variance, lo, hi)[0]
        # Scale derivatives by SD. Tiny SD finite differences have unavoidable
        # input subtraction error; compare analytic formulas independently below.
        if variance > 1e-12:
            close((fp-fm)/(2*eps)*math.sqrt(variance), got[1]*math.sqrt(variance),
                  'normalizer derivative previous', atol=1e-7, rtol=1e-5)
            gy = (k.transition(.5, y+eps, mu-.5, variance, lo, hi)[0]
                  -k.transition(.5, y-eps, mu-.5, variance, lo, hi)[0])/(2*eps)
            close(gy*math.sqrt(variance), got[2]*math.sqrt(variance),
                  'transition derivative following', atol=1e-7, rtol=1e-5)
        ev = 1e-5
        gv = (k.transition(.5, y, mu-.5, variance*math.exp(ev), lo, hi)[0]
              -k.transition(.5, y, mu-.5, variance*math.exp(-ev), lo, hi)[0])/(2*ev)
        close(gv, got[3], 'log variance derivative', atol=1e-7, rtol=1e-5)
        if mu in (-40., -80.):
            ref_logz, ref_mean = decimal_tail(-mu, 1-mu)
            close(n.log_Z, ref_logz, '70 digit tail logZ', atol=1e-8, rtol=0)
            close(n.mean, ref_mean, '70 digit tail mean', atol=1e-8, rtol=0)
        elif 0 <= mu <= 1:
            z = .5*(math.erf((hi-mu)/math.sqrt(2*variance))-math.erf((lo-mu)/math.sqrt(2*variance)))
            close(n.log_Z, math.log(z), 'independent erf normalizer', atol=1e-10, rtol=0)
        diagnostics.append(dict(mu=mu, variance=variance, integral=total, log_Z=n.log_Z,
                                quadrature_change=n.quadrature_relative_change,
                                omitted_tail_bound=n.tail_relative_bound))
    close(k.transition(.4, .39, -.01, 0, 0, 1), (0, 0, 0, 0), 'exact Dirac')
    rejects(lambda: k.transition(.4, .39000001, -.01, 0, 0, 1), 'dirac_constraint_violated')
    rejects(lambda: k.transition(0., 0., -.01, 0, 0, 1), 'model_domain_exceeded')
    rejects(lambda: k.normalizer(-20000., 1., 0., 1.), 'transition_numeric_unresolved')
    return diagnostics


def exposure_and_prediction_moments():
    profile = k.Profile((-.001, -.01, .0001, .001, .002, .005, .0002, .0005))
    for current in (-.1, 0., .1):
        means, variances = profile.increments(1., current)
        d, a = 1/86400, abs(current)/3600
        close(means, (-.001*d-.01*a, .0001*d+.001*a), 'calendar and throughput mean', atol=1e-18)
        close(variances, (.002**2*d+.005**2*a, .0002**2*d+.0005**2*a),
              'calendar and throughput variance', atol=1e-20)
        check(all(v > 0 for v in variances), 'rest/calendar uncertainty continues')
    close(profile.increments(0., .1), ((0, 0), (0, 0)), 'dt zero exact exposures', atol=0, rtol=0)
    x = math.log(.06)
    n = k.normalizer(x, .0004, k.LOW[5], k.HIGH[5])
    close(n.mean, x, 'interior log mean')
    close(n.variance, .0004, 'interior variance')
    close(n.mean_exp, math.exp(x+.0002), 'physical Q mean includes transform')
    close(n.variance_exp, math.exp(2*x+.0004)*math.expm1(.0004), 'physical Q variance')
    boundary = k.normalizer(0., .0004, 0., 1.)
    close(boundary.mean, .02*math.sqrt(2/math.pi), 'boundary half normal mean')
    close(boundary.variance, .0004*(1-2/math.pi), 'boundary half normal variance')
    return dict(interior_Q_mean_Ah=n.mean_exp, boundary_R0_mean=boundary.mean)


def dynamic_path_gradient():
    # Accelerated, explicitly artificial diffusion makes finite differences
    # well conditioned; rate selection is frozen independently of observations.
    profile = k.Profile((-.001, -.01, .0001, .001, .2, .5, .1, .3))
    rs = records()
    x = k.MEAN.copy()
    x[12:15], x[15] = [.01, -.02, .03], -.3
    free, health = [], np.array([x[5], x[6]])
    scales = list(k.SD)
    for r in rs:
        means, variances = profile.increments(r.dt, r.current)
        for j, v in enumerate(variances):
            health[j] += means[j]
            if v:
                health[j] += (.2 if j else -.3)*math.sqrt(v)
                free.append(health[j])
                scales.append(math.sqrt(v))
    free = np.array(free)
    all_x = np.r_[x, free]
    got = target.evaluate(x, rs, profile, free)
    errors = []
    for j, scale in enumerate(scales):
        step = 1e-4*scale
        values = []
        for mul in (-2, -1, 1, 2):
            trial = all_x.copy()
            trial[j] += mul*step
            values.append(target.evaluate(trial[:16], rs, profile, trial[16:])['nll'])
        fd = (values[0]-8*values[1]+8*values[2]-values[3])/(12*step)
        close(fd*scale, got['gradient'][j]*scale, 'path derivative '+str(j), atol=1e-7, rtol=1e-5)
        errors.append(abs(fd-got['gradient'][j])*scale)
    masked = [dataclasses.replace(r, measurement_valid=False, voltage=None) for r in rs]
    no_obs = target.evaluate(x, masked, profile, free)
    close(no_obs['observation_nll'], 0, 'masked factors absent')
    close(no_obs['transition_nll'], got['transition_nll'], 'masked transitions retained')
    check(no_obs['state'].observation_count == 0, 'masked ownership')
    return dict(dimension=len(all_x), max_scaled_gradient_gap=max(errors))


def partial_dirac_and_numeric_failures():
    # A drifting but deterministic capacity still carries initial-capacity
    # derivatives. Only resistance contributes new path variables.
    profile = k.Profile((-.001, -.01, .0001, .001, 0., 0., .1, .3))
    rs = records()
    free = [.101, .102, .103, .104]
    got = target.evaluate(k.MEAN, rs, profile, free)
    check(got['free_health_coordinates'] == ((0, 1), (2, 1), (3, 1), (4, 1)),
          'only stochastic coordinates retained')
    health = k.MEAN[5]
    for row, record in zip(got['rows'], rs):
        health += profile.increments(record.dt, record.current)[0][0]
        close(row['health'][0], health, 'deterministic drift exact', atol=0, rtol=0)
    eps = 1e-5*k.SD[5]
    xp, xm = k.MEAN.copy(), k.MEAN.copy()
    xp[5] += eps
    xm[5] -= eps
    fd = (target.evaluate(xp, rs, profile, free)['nll']-
          target.evaluate(xm, rs, profile, free)['nll'])/(2*eps)
    close(fd*k.SD[5], got['gradient'][5]*k.SD[5], 'eliminated capacity chain derivative',
          atol=1e-7, rtol=1e-5)
    again = target.evaluate(k.MEAN, rs, profile, free)
    close(again['gradient'], got['gradient'], 'repeated query stable', atol=0, rtol=0)
    check(again['state'] == got['state'], 'queries create no extra transitions')
    rejects(lambda: target.evaluate(k.MEAN, rs, profile, free+[.1]), 'invalid_input')
    rejects(lambda: k.Profile((0.,)*4+(-1., 0., 0., 0.)), 'invalid_input')
    rejects(lambda: k.Profile((0.,)*4+(1e-300, 0., 0., 0.)).increments(1., 0.),
            'transition_numeric_unresolved')
    rejects(lambda: k.Profile((0.,)*4+(1e300, 0., 0., 0.)).increments(1., 0.),
            'transition_numeric_unresolved')
    rejects(lambda: profile.increments(float.fromhex('0x0.0000000000001p-1022'), .1),
            'transition_numeric_unresolved')
    # A discontinuity is low probability under the registered transition,
    # never grounds for silently increasing diffusion or resetting history.
    ordinary = k.transition(.2, .205, .005, .0004, 0., 1.)[0]
    abrupt = k.transition(.2, .505, .005, .0004, 0., 1.)[0]
    close(abrupt-ordinary, 112.5, 'abrupt innovation penalty', atol=1e-10)
    return dict(free_health_dimension=4, abrupt_minus_expected_transition_NLL=abrupt-ordinary)


def marginal_is_not_profile():
    # Declared scalar semantic control, not the original battery prior:
    # previous R0 uniform [.1,.2], current R0 truncated N(previous,.02^2).
    def density(y, x):
        sd = .02
        z = .5*(math.erf((1-x)/(sd*math.sqrt(2)))-math.erf(-x/(sd*math.sqrt(2))))
        return math.exp(-.5*((y-x)/sd)**2)/(sd*math.sqrt(2*math.pi)*z)
    rows = []
    for y in (.1, .15, .2):
        vals = []
        for order in (64, 128):
            xx, ww = k.gauss(order)
            xx = .15+.05*xx
            vals.append(.5*sum(float(w)*math.exp(-k.transition(float(x), y, 0., .0004, 0., 1.)[0])
                                for x, w in zip(xx, ww)))
            RESULT['posterior_quadrature_evaluations'] += order
        n = 2048
        points = np.linspace(.1, .2, n+1)
        weights = np.array([1]+[4 if j % 2 else 2 for j in range(1, n)]+[1])
        reference = float(weights@np.array([density(y, x) for x in points]))/(3*n)
        RESULT['posterior_quadrature_evaluations'] += n+1
        close(vals[1], reference, 'independent Simpson marginal', atol=1e-8, rtol=0)
        close(math.log(vals[0]), math.log(vals[1]), 'marginal quadrature convergence', atol=1e-5, rtol=0)
        # Max over the same grid; density is nearly flat in y when profiling,
        # unlike the integrated factor near prior support ends.
        profile = max(density(y, x) for x in points)
        rows.append(dict(current_R0=y, marginal=vals[1], profile=profile))
    marginal_contrast = math.log(rows[1]['marginal']/rows[0]['marginal'])
    profile_contrast = math.log(rows[1]['profile']/rows[0]['profile'])
    check(abs(marginal_contrast-profile_contrast) > .5, 'profiling changes target')
    return dict(rows=rows, marginal_log_contrast=marginal_contrast, profile_log_contrast=profile_contrast)


def correlation_mediated_update():
    # Independent two-dimensional standardized Gaussian semantic control.
    # Observe only z; health changes through prior correlation, not excitation.
    n = 64
    x, w = np.polynomial.hermite.hermgauss(n)
    z = math.sqrt(2)*x[:, None]
    health = .8*z+.6*math.sqrt(2)*x[None, :]
    weights = w[:, None]*w[None, :]/math.pi
    observed, variance = 1., .5
    post = weights*np.exp(-.5*(z-observed)**2/variance)
    post /= post.sum()
    mean = float((post*health).sum())
    var = float((post*(health-mean)**2).sum())
    RESULT['posterior_quadrature_evaluations'] += n*n
    close(mean, .8/(1+variance), 'correlated health correction', atol=1e-6, rtol=0)
    close(var, 1-.8**2/(1+variance), 'correlated health variance', atol=1e-6, rtol=0)
    check(mean > 0, 'legitimate correction without direct health observation')
    return dict(health_posterior_mean=mean, health_posterior_variance=var,
                direct_health_excitation=False, correlation_mediated_update=True)


def conditional_filter(observations, order):
    # Conditional scalar posterior control: all fast/static/Q inputs fixed to
    # declared PUBLIC values. This is deliberately not the full 16D posterior.
    nodes, weights = k.gauss(order)
    nodes, weights = (nodes+1)/2, weights/2
    density = np.exp(-.5*((nodes-.2)/.06)**2)
    mass = weights*density
    mass /= mass.sum()
    profile = k.Profile((0., 0., 432., 0., 0., 0., .04*math.sqrt(86400), 0.))
    increments, variances = profile.increments(1., 0.)
    transition_matrix = np.array([[math.exp(-k.transition(float(old), float(new),
        increments[1], variances[1], 0., 1.)[0]) for old in nodes] for new in nodes])
    state = k.initial_state(k.MEAN, 'fixture')
    rows = []
    previous_mean = float(nodes@mass)
    previous_variance = float(((nodes-previous_mean)**2)@mass)
    for r in observations:
        RESULT['posterior_quadrature_evaluations'] += order*order
        check(RESULT['posterior_quadrature_evaluations'] <= 200000, 'posterior evaluation cap')
        prediction = weights*(transition_matrix@mass)
        normalization_error = abs(float(prediction.sum())-1.)
        prediction /= prediction.sum()
        predicted_mean = float(nodes@prediction)
        predicted_variance = float(((nodes-predicted_mean)**2)@prediction)
        state, voltage, _, _ = k.advance(state, r, (k.MEAN[5], 0.))
        mu = voltage-r.current*nodes
        logs = -.5*((mu-r.voltage)/k.SIGMA)**2
        mass = prediction*np.exp(logs-max(logs))
        mass /= mass.sum()
        mean = float(nodes@mass)
        variance = float(((nodes-mean)**2)@mass)
        rows.append(dict(index=r.index, prediction_mean=predicted_mean,
            posterior_mean=mean, prediction_variance=predicted_variance,
            posterior_variance=variance, model_predicted_change=predicted_mean-previous_mean,
            measurement_correction=mean-predicted_mean,
            prediction_uncertainty_change=predicted_variance-previous_variance,
            conditioning_uncertainty_change=variance-predicted_variance,
            quadrature_prediction_mass_error=normalization_error,
            direct_R0_excitation=r.current != 0, correlation_mediated_update=False))
        previous_mean, previous_variance = mean, variance
    return rows


def gradual_drift_and_renewed_excitation():
    # Plant generation is separate from inference. Truth is never supplied to
    # conditional_filter; scoring begins only after both posterior runs close.
    x = oracle.PUBLIC_MEAN
    v, h, charge = list(x[12:15]), x[15], 0.
    observations, truth = [], []
    for j in range(12):
        current = 0. if j < 6 else .02
        r0 = .2+.012*(j+1)
        truth.append(r0)
        charge += current/3600.
        z = x[11]-charge/math.exp(x[5])
        for n in range(3):
            e = math.exp(-1/math.exp(x[n]))
            v[n] = e*v[n]+(1-e)*x[7+n]*current
        if current:
            e = math.exp(-math.exp(x[3])*current/3600)
            h = e*h+(1-e)
        voltage = 3+1.15*z+.08*math.tanh(8*(z-.5))-sum(v)-x[10]*h-current*r0
        observations.append(k.Record('fixture', j, 1., current, voltage))
    low = conditional_filter(tuple(observations), 48)
    high = conditional_filter(tuple(observations), 96)
    closure = dict(posterior_runs_closed=True, truth_values_passed_to_inference=0,
                   conditional_scope='Only R0 uncertain; other public parameters fixed; noiseless synthetic observations')
    for a, b in zip(low, high):
        for field in ('prediction_mean', 'posterior_mean', 'prediction_variance', 'posterior_variance'):
            close(a[field], b[field], '48/96 posterior convergence '+field, atol=1e-6, rtol=0)
        check(b['quadrature_prediction_mass_error'] < 1e-8, 'transition prediction mass')
        if b['index'] < 6:
            close(b['measurement_correction'], 0., 'rest measurement gives no R0 correction', atol=1e-12)
            check(b['prediction_uncertainty_change'] > 0, 'rest increases uncertainty')
    check(abs(high[-1]['posterior_mean']-truth[-1]) < abs(high[5]['posterior_mean']-truth[-1]),
          'renewed excitation tracks drift better than last rest estimate')
    check(high[-1]['posterior_variance'] < high[5]['posterior_variance'], 'renewed excitation reduces uncertainty')
    closure.update(rows=high, postclosure_truth_R0=truth,
                   final_R0_error=high[-1]['posterior_mean']-truth[-1])
    return closure


def scope_and_atomicity():
    state = k.initial_state(k.MEAN, 'fixture')
    stream = k.Stream(state)
    snapshot = pickle.dumps(stream.state)
    valid = k.Record('fixture', 0, 0., 0., 3.85)
    for bad, status in [(dataclasses.replace(valid, index=1), 'source_order_error'),
            (dataclasses.replace(valid, source_id='other'), 'source_order_error'),
            (dataclasses.replace(valid, input_known=False), 'recovery_required'),
            (dataclasses.replace(valid, dt=1.1), 'invalid_record'),
            (dataclasses.replace(valid, voltage=float('nan')), 'invalid_record')]:
        rejects(lambda: stream.deliver(bad, state.health), status)
        check(pickle.dumps(stream.state) == snapshot, 'failed transaction byte preservation')
    rejects(lambda: stream.deliver(valid, (-10., .1)), 'model_domain_exceeded')
    check(pickle.dumps(stream.state) == snapshot, 'health rejection atomic')
    near_empty = dataclasses.replace(state, fast=(1e-7, 0., 0., 0., 0.))
    empty_stream = k.Stream(near_empty)
    rejects(lambda: empty_stream.deliver(dataclasses.replace(valid, dt=1., current=.25), state.health),
            'model_domain_exceeded')
    check(empty_stream.state == near_empty, 'SOC rejection preserves state')
    _, voltage, _, _ = k.advance(state, valid, state.health)
    for name, bias, temp in [('sensor_bias', .02, 25.), ('OCV_mismatch', -.02, 25.),
                             ('abrupt_voltage_change', .1, 25.), ('temperature', 0., 35.)]:
        record = dataclasses.replace(valid, voltage=voltage+bias, temperature_C=temp)
        out = target.evaluate(k.MEAN, [record], k.Profile((0.,)*8))
        flag = 'outside_validated_temperature_scope' if temp != 25 else 'model_mismatch_suspected'
        check(flag in out['state'].flags, name+' scope explicit')
        check(out['uncertainty_status'] == 'unresolved', 'no curvature fallback')
        close(out['state'].health, state.health, 'mismatch does not invent aging')
    zero_records = [dataclasses.replace(valid, index=j, voltage=voltage) for j in range(2)]
    out = target.evaluate(k.MEAN, zero_records, k.Profile((0.,)*8))
    check(out['state'].observation_count == 2 and out['state'].next_index == 2,
          'distinct dt-zero observations counted exactly once')
    close(out['state'].elapsed, 0., 'queries do not create elapsed time')
    close(out['state'].fast, state.fast, 'zero-time state identity', atol=0, rtol=0)
    return dict(mismatch_threshold_sigma=6, unique_aging_attribution=False,
                atomic_scope='Physical cursor; full posterior checkpoint not implemented')


def main(output):
    for fn in (stationary_equivalence, physical_ledger_and_local_derivatives,
               transition_normalization_and_derivatives, exposure_and_prediction_moments,
               dynamic_path_gradient, partial_dirac_and_numeric_failures,
               marginal_is_not_profile, correlation_mediated_update,
               gradual_drift_and_renewed_excitation, scope_and_atomicity):
        case(fn)
    RESULT['activity'] = dict(k.ACTIVITY)
    RESULT['oracle_activity'] = dict(oracle.ACTIVITY)
    RESULT['status'] = 'passed' if all(r['status'] == 'passed' for r in RESULT['cases']) else 'failed'
    with output.open('x') as f:
        json.dump(RESULT, f, indent=2, allow_nan=False)
        f.write('\n')
    print(json.dumps({key: RESULT[key] for key in ('status', 'checks', 'activity', 'posterior_quadrature_evaluations')}))
    return 0 if RESULT['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main(Path(sys.argv[1])))
