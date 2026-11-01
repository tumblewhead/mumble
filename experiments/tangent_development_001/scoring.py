"""Post-prediction scoring only. Truth is never passed to forecast.predict."""
import numpy as np
from forecast import path, segments


def truth_chart(state, ref):
    p = np.array(ref, copy=True)
    p[7] -= ref[5]
    p[5] -= ref[3]
    if not -1 < state[4] < 1:
        raise ValueError('truth chart requires interior h for scoring ablations')
    return np.r_[state[:4], np.arctanh(state[4]), np.log(p)]


def score(prediction, truth_state, truth_ref, task, config, temperature, rate, endpoint):
    from experiments.foster_feedback_001.plant import scalar_step
    from experiments.foster_campaign_001.telemetry import thermal
    chart = truth_chart(truth_state, truth_ref)
    ss = segments(task, rate)
    candidate = path(chart, ss, config, temperature, rate, grid=True)
    p = np.array(truth_ref)*thermal(config, temperature)
    # Score predicted timestamps with an independent scalar recurrence. Include
    # exact stationary candidates separately for the true trajectory minimum.
    def scalar(times, currents):
        state = list(truth_state)
        prior = 0.
        values = []
        for t, current in zip(times, currents):
            state, voltage = scalar_step(state, p, float(t-prior), float(current),
                                         config['ocv_intercept_V'], config['ocv_slope_V_per_SOC'])
            values.append(voltage)
            prior = t
        return np.array(values)
    actual = scalar(prediction['times'], prediction['current'])
    truth = scalar(candidate['times'], candidate['current'])
    error = prediction['voltage']-actual
    ix = int(np.argmin(truth))
    vmin = float(truth[ix])
    # Admission disagreement exists exactly between the two point minima.
    lo, hi = sorted([prediction['minimum_V'], vmin])
    ablations = {}
    for name, indices in [('inherited_states', list(range(5))),
                          ('RC_and_R0', list(range(6, 13))),
                          ('SOC_and_Q', [0, 5]), ('hysteresis', [4, 13, 14, 15])]:
        x = endpoint.copy()
        x[indices] = chart[indices]
        try:
            v = path(x, ss, config, temperature, rate)
            ablations[name] = dict(status='scoring_only', minimum_error_V=v['minimum_V']-vmin,
                                   recovery_error_V=v['recovery_V']-float(truth[-1]))
        except (ValueError, OverflowError, FloatingPointError) as e:
            ablations[name] = dict(status='unresolved_scoring_ablation', reason=str(e))
    return dict(truth_minimum_V=vmin, truth_minimum_time_s=float(candidate['times'][ix]),
                minimum_error_V=prediction['minimum_V']-vmin,
                minimum_time_error_s=prediction['minimum_time_s']-float(candidate['times'][ix]),
                recovery_error_V=prediction['recovery_V']-float(truth[-1]),
                trajectory_RMS_V=float(np.sqrt(np.mean(error**2))), max_abs_error_V=float(np.max(abs(error))),
                pointwise_3sd_misses=int(np.sum(abs(error) > 3*prediction['local_sd_V'])),
                evaluation_points=len(error),
                diagnostic_cutoff_disagreement=dict(lower_V=lo, upper_V=hi,
                    type='unsafe_point_admission' if prediction['minimum_V'] > vmin else 'unnecessary_point_rejection',
                    semantics='For cutoff in (lower,upper], point estimates disagree; no calibrated risk or hardware cutoff assumed'),
                truth_scalar_closed_form_difference_V=float(np.max(abs(truth-candidate['voltage']))),
                scoring_only_substitutions=ablations,
                attribution_limit='Overlapping substitution groups are diagnostic and not additive error contributions')
