"""Read-only current-task forecasts. No plant, truth or estimator update inputs."""
import math
import numpy as np


def parameters(x, config, temperature):
    x = np.asarray(x, dtype=float)
    if x.shape != (16,) or not np.isfinite(x).all() or not 0 <= x[0] <= 1:
        raise ValueError('invalid endpoint chart')
    if not 15 <= temperature <= 35:
        raise ValueError('temperature outside calibrated model domain')
    p = np.exp(x[5:]).copy()
    p[5] += p[3]
    p[7] += p[5]
    p *= np.exp(np.array(config['arrhenius_A_K']) *
                (1/(temperature+273.15)-1/config['reference_temperature_K']))
    if not np.isfinite(p).all() or np.any(p <= 0) or not p[3] < p[5] < p[7]:
        raise ValueError('invalid parameters or temperature pole ordering')
    return p


def segments(task, rate):
    """Round durations once to the declared acquisition period; record the result."""
    if not math.isfinite(rate) or rate <= 0:
        raise ValueError('positive rate required')
    source = task['segments'] * task.get('repeat', 1)
    if task.get('recovery_s'):
        source = source + [dict(duration_s=task['recovery_s'], current_A=0.)]
    result = []
    for s in source:
        duration, current = float(s['duration_s']), float(s['current_A'])
        if not math.isfinite(duration) or duration <= 0 or not math.isfinite(current) or abs(current) > .25:
            raise ValueError('invalid public current task')
        n = round(duration*rate)
        if n < 1:
            raise ValueError('task segment shorter than one sample')
        result.append(dict(duration_s=n/rate, requested_duration_s=duration,
                           rounding_s=n/rate-duration, current_A=current, samples=n))
    return result


def exp_roots(coefficients, rates, duration):
    """All isolated roots of a real exponential sum on [0,duration].

    Factor the slowest exponential, differentiate, and recursively partition at
    derivative roots. Each resulting interval is monotone. At most four levels
    for this model; no time grid can hide a fast RC extremum. Identically zero
    functions need no isolated roots (endpoints suffice for a flat voltage).
    """
    combined = {}
    for a, r in zip(coefficients, rates):
        combined[float(r)] = combined.get(float(r), 0.) + float(a)
    pairs = sorted((r, a) for r, a in combined.items() if a != 0.)
    if len(pairs) <= 1:
        return []
    r = np.array([v[0]-pairs[0][0] for v in pairs])
    a = np.array([v[1] for v in pairs])
    a /= np.max(abs(a))
    critical = exp_roots(-r[1:]*a[1:], r[1:], duration)
    points = [0., *critical, float(duration)]
    def value(t):
        return float(a @ np.exp(-r*t))
    roots = []
    for lo, hi in zip(points[:-1], points[1:]):
        fl, fh = value(lo), value(hi)
        if fl == 0.:
            roots.append(lo)
        if fl*fh < 0.:
            for _ in range(80):
                mid = (lo+hi)/2
                if mid == lo or mid == hi:
                    break
                fm = value(mid)
                if fm == 0.:
                    lo = hi = mid
                    break
                if (fl < 0) == (fm < 0):
                    lo, fl = mid, fm
                else:
                    hi = mid
            roots.append((lo+hi)/2)
    if value(duration) == 0.:
        roots.append(float(duration))
    return sorted(set(roots))


def at_time(state, p, current, times, config):
    """Independent closed form used for extrema and nonlinear direction probes."""
    t = np.atleast_1d(times)
    z = state[0]-current*t/(3600*p[0])
    if np.any(z < 0) or np.any(z > 1):
        raise ValueError('proposed task leaves SOC support')
    R, tau = p[[2, 4, 6]], p[[3, 5, 7]]
    v = R*current+(np.asarray(state[1:4])-R*current)*np.exp(-t[:, None]/tau)
    g = p[9 if current > 0 else 10]*abs(current)/(3600*p[0])
    h = np.sign(current)+(state[4]-np.sign(current))*np.exp(-g*t) if current else np.full(len(t), state[4])
    voltage = config['ocv_intercept_V']+config['ocv_slope_V_per_SOC']*z+p[8]*h-current*p[1]-v.sum(axis=1)
    return np.column_stack([z, v, h]), voltage


def extrema(state, p, current, duration, config):
    tau = p[[3, 5, 7]]
    g = p[9 if current > 0 else 10]*abs(current)/(3600*p[0])
    coeff = np.r_[-config['ocv_slope_V_per_SOC']*current/(3600*p[0]),
                  (np.asarray(state[1:4])-p[[2, 4, 6]]*current)/tau,
                  p[8]*g*(np.sign(current)-state[4])]
    return exp_roots(coeff, np.r_[0., 1/tau, g], duration)


def path(x, task_segments, config, temperature, rate, grid=False):
    p = parameters(x, config, temperature)
    state = np.r_[x[:4], np.tanh(x[4])]
    elapsed = 0.
    times, volts, currents, intervals = [], [], [], []
    sampled_min = math.inf
    for s in task_segments:
        d, current = s['duration_s'], s['current_A']
        stationary = extrema(state, p, current, d, config)
        regular = np.arange(1, s['samples']+1)/rate
        # Both sides of every current edge are distinct, ordered dt=0 records.
        local = np.unique(np.r_[0., regular if grid else [], stationary, d])
        states, values = at_time(state, p, current, local, config)
        if grid:
            sampled_min = min(sampled_min, float(at_time(state, p, current, np.r_[0., regular], config)[1].min()))
        times.extend(elapsed+local)
        volts.extend(values)
        currents.extend([current]*len(local))
        intervals.extend(np.r_[0., np.diff(local)])
        state = states[-1]
        elapsed += d
    t, v = np.array(times), np.array(volts)
    if not np.isfinite(v).all():
        raise ValueError('nonfinite prediction')
    ix = int(np.argmin(v))
    return dict(times=t, voltage=v, current=np.array(currents), dt=np.array(intervals),
                minimum_V=float(v[ix]), minimum_time_s=float(t[ix]), recovery_V=float(v[-1]),
                sample_grid_minimum_excess_V=sampled_min-float(v[ix]) if grid else None)


def predict(model, mean, root, task, config, temperature, rate, *, transport=None):
    """Full joint local covariance plus 64 deterministic joint direction probes.

    transport, if present, maps original-history coordinates to the endpoint;
    it is used only for the separately labeled nonlinear geometry ablation.
    """
    mean, root = np.array(mean, copy=True), np.array(root, copy=True)
    if root.shape != (16, 16) or not np.isfinite(root).all():
        raise ValueError('finite full joint root required')
    ss = segments(task, rate)
    endpoint = mean if transport is None else transport(mean)[0]
    endpoint_root = root if transport is None else transport(mean)[1] @ root
    result = path(endpoint, ss, config, temperature, rate, grid=True)
    # No observed voltage is supplied: unused V/sigma slots are fixed constants.
    observations = np.column_stack([result['dt'], result['current'],
                                    np.full(len(result['dt']), temperature),
                                    np.zeros(len(result['dt'])), np.ones(len(result['dt']))])
    v, J, _, _ = model.evaluate(endpoint, observations)
    result['closed_form_C_max_difference_V'] = float(np.max(abs(v-result['voltage'])))
    result['voltage'] = v
    sensitivity = J @ endpoint_root
    result['local_sd_V'] = np.sqrt(np.sum(sensitivity*sensitivity, axis=1))
    ix = int(np.argmin(v))
    result.update(minimum_V=float(v[ix]), minimum_time_s=float(result['times'][ix]),
                  recovery_V=float(v[-1]), local_sd_at_point_minimum_V=float(result['local_sd_V'][ix]))
    probes = []
    for radius in (1., 3.):
        for j in range(16):
            for sign in (-1, 1):
                info = dict(radius=radius, direction=j, sign=sign)
                try:
                    x = mean+sign*radius*root[:, j]
                    end = x if transport is None else transport(x)[0]
                    probe = path(end, ss, config, temperature, rate)
                    info.update(status='supported', minimum_V=probe['minimum_V'],
                                minimum_time_s=probe['minimum_time_s'], recovery_V=probe['recovery_V'])
                except (ValueError, OverflowError, FloatingPointError, np.linalg.LinAlgError) as error:
                    info.update(status='unresolved', reason=str(error))
                probes.append(info)
    result.update(segments=ss, probes=probes, unsupported_probes=sum(p['status'] != 'supported' for p in probes),
                  uncertainty='Full joint local linear covariance and deterministic directions; not calibrated coverage or path-minimum probability bounds')
    return result
