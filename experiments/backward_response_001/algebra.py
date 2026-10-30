"""Exact physical partitions of the inherited stationary probe response."""
import numpy as np
from experiments.partition_coordinate_fit_001 import coordinates as c

LABELS = ['boundary', 'OCV_shift', 'ohmic', *['RC_carried_'+str(i+1) for i in range(3)],
          *['RC_forced_'+str(i+1) for i in range(3)],
          'hysteresis_carried', 'hysteresis_positive', 'hysteresis_negative']
GROUPS = {'boundary': [0], 'OCV_shift': [1], 'ohmic': [2], 'RC_carried': [3, 4, 5],
          'RC_forced': [6, 7, 8], 'hysteresis': [9, 10, 11]}


def terms(x, steps):
    n = len(x)
    A, B = np.ones((n, 3)), np.zeros((n, 3))
    Ah, Bp, Bm = np.ones(n), np.zeros(n), np.zeros(n)
    z = x[:, 11].copy()
    current = 0.
    for current, dt in steps:
        z -= current*dt/(3600*np.exp(x[:, 5]))
        decay = np.exp(-dt/np.exp(x[:, :3]))
        gain = -np.expm1(-dt/np.exp(x[:, :3]))
        A, B = decay*A, decay*B+gain*current
        if current:
            exposure = np.exp(x[:, 3 if current > 0 else 4])*abs(current)*dt/3600
            decayh, gainh = np.exp(-exposure), -np.expm1(-exposure)
            Ah, Bp, Bm = decayh*Ah, decayh*Bp, decayh*Bm
            if current > 0:
                Bp += gainh
            else:
                Bm -= gainh
    out = np.empty((n, 12))
    out[:, 0] = c.v.voltage(x)
    out[:, 1] = c.v.ocv(z)-c.v.ocv(x[:, 11])
    out[:, 2] = -current*x[:, 6]
    out[:, 3:6] = (1-A)*x[:, 12:15]
    out[:, 6:9] = -B*x[:, 7:10]
    out[:, 9] = x[:, 10]*x[:, 15]*(1-Ah)
    out[:, 10] = -x[:, 10]*Bp
    out[:, 11] = -x[:, 10]*Bm
    return out


def directional_amplitudes(H, h):
    return H*(1+h), H*(1-h)  # U, D


def directional_inverse(U, D):
    c.old.require(np.all(U > 0) and np.all(D > 0), 'directional amplitude support')
    return (U+D)/2, (U-D)/(U+D)


def reversal_closed(x, current, duration):
    a = np.exp(-duration/np.exp(x[:, :3]))
    q = current*duration/3600
    ap, am = np.exp(-np.exp(x[:, 3])*q), np.exp(-np.exp(x[:, 4])*q)
    U, D = directional_amplitudes(x[:, 10], x[:, 15])
    rc_carried = ((1-a*a)*x[:, 12:15]).sum(1)
    rc_forced = (current*(1-a)**2*x[:, 7:10]).sum(1)
    hysteresis = U*(1-am)-D*am*(1-ap)
    return c.v.voltage(x)+current*x[:, 6]+rc_carried+rc_forced+hysteresis


def prior_log_density_shape(gamma, mean, sd):
    """Physical-rate log density, omitting the constant truncation normalizer."""
    return -np.log(gamma)-.5*((np.log(gamma)-mean)/sd)**2


def prior_log_curvature(gamma, mean, sd):
    return (1+(np.log(gamma)-mean-1)/sd**2)/gamma**2


def moments(values):
    mean = values.mean(0)
    delta = values-mean
    return dict(mean=mean, covariance=delta.T @ delta/len(values), count=len(values))


def pool(rows):
    count = sum(r['count'] for r in rows)
    mean = sum(r['count']*r['mean'] for r in rows)/count
    covariance = sum(r['count']*(r['covariance']+np.outer(r['mean']-mean, r['mean']-mean)) for r in rows)/count
    return dict(mean=mean, covariance=covariance, count=count)


def contrast(model, reference):
    dm = model['mean']-reference['mean']
    dc = model['covariance']-reference['covariance']
    # Each cross term is allocated once to each endpoint (two in total).
    # This additive bookkeeping does not claim a causal intervention.
    groups = list(GROUPS)
    transform = np.zeros((len(groups), 12))
    for i, name in enumerate(groups):
        transform[i, GROUPS[name]] = 1
    group_cov_delta = transform @ dc @ transform.T
    return dict(mean_difference_V=float(dm.sum()), variance_difference_V2=float(dc.sum()),
        term_mean_differences_V=dict(zip(LABELS, dm)),
        group_mean_differences_V=dict(zip(groups, transform @ dm)),
        group_variance_contributions_V2=dict(zip(groups, group_cov_delta.sum(1))),
        group_covariance_difference_V2=group_cov_delta,
        term_covariance_difference_V2=dc,
        diagonal_variance_difference_V2=float(np.trace(dc)),
        off_diagonal_variance_difference_V2=float(dc.sum()-np.trace(dc)),
        allocation='variance row sums share each covariance pair between its two endpoints; coordinate-dependent diagnostic, not causal attribution')
