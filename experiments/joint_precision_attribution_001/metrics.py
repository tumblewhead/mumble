"""Read-only common-anchor attribution, keeping one prior and all cross terms."""
import numpy as np
from experiments.foster_uncertainty_audit_001.conditional_packet import partition
from experiments.conditional_architecture_001.conditional import chart_amplitude_jacobian
from experiments.partitioned_coefficients_001.run import chart_shape_jacobian
from experiments.hysteresis_mixed_completion_001.run import future_tasks
from experiments.rc_remainder_bounds_001.check import UPPER

RC = [1, 2, 3, 6, 7, 8, 11, 12, 13]
H = [9, 10, 14, 15]
OTHER = [0, 4, 5]
NAMES = ['z0', 'v10', 'v20', 'v30', 'inverse_Q', 'R0', 'R1', 'R2', 'R3',
         'H', 'Hh0', 'log_tau1', 'log_tau2', 'log_tau3', 'log_gamma_plus_over_Q', 'log_gamma_minus_over_Q']


def coordinates(x, prior_root):
    a, shape = partition(x)
    B = np.column_stack((chart_amplitude_jacobian(a), chart_shape_jacobian(shape)))
    return a, shape, B, np.linalg.solve(B, prior_root)


def separate(delta):
    rc, h = np.zeros_like(delta), np.zeros_like(delta)
    rc[:, RC], h[:, H] = delta[:, RC], delta[:, H]
    return rc, h


def append(root, rows):
    return np.linalg.qr(np.vstack((root, rows)), mode='r')


def rc_envelope(a, shape, center, imax):
    t = np.log(shape[:3]/np.asarray(center)[:3])
    A, B = map(float, UPPER[3])
    M = A*abs(a[1:4])+B*a[6:9]*imax
    bound = np.zeros(16)
    bound[1:4] = A*abs(t)**3/6
    bound[6:9] = B*imax*abs(t)**3/6
    bound[11:14] = M*t*t/2
    return bound


def query_metrics(g, gh, precision_root, M, epsilon):
    g, gh = np.atleast_2d(g), np.atleast_2d(gh)
    q = np.linalg.norm(g@M, axis=1)
    h = np.linalg.norm((gh-g)@M, axis=1)
    sd = np.linalg.norm(np.linalg.solve(precision_root.T, gh.T), axis=0)
    if np.any(q <= 0):
        raise ValueError('zero reference query width; relative readout unavailable')
    result = dict(SD_ratio_range=[float(min(sd/q)), float(max(sd/q))],
                  maximum_relative_transport_gradient_defect=float(max(h/q)))
    if epsilon < 1:
        low = np.maximum(0., q-h)/np.sqrt(1+epsilon)
        high = (q+h)/np.sqrt(1-epsilon)
        # Floating diagnostic allowance, not a physical threshold or interval proof.
        if np.any(sd < low-1e-10*q) or np.any(sd > high+1e-10*q):
            raise AssertionError('P3 query inequality inconsistency')
        result['P3'] = dict(status='sufficient_test_passes_at_sampled_anchor',
                            lower_SD_ratio_range=[float(min(low/q)), float(max(low/q))],
                            upper_SD_ratio_range=[float(min(high/q)), float(max(high/q))])
    else:
        result['P3'] = dict(status='inconclusive_epsilon_ge_1')
    return result


def hybrid_transport(direct, compressed, variant):
    end, D = (a.copy() for a in direct)
    ce, cd = compressed
    rows = [1, 2, 3] if variant == 'RC_only' else [4] if variant == 'H_only' else [1, 2, 3, 4]
    end[rows], D[rows] = ce[rows], cd[rows]
    return end, D


def analyze(root, K, L, x, direct, compressed, model, envelope, sigma_inv_square_sum):
    J = root[:, :16]
    DRc, DHc = root[:, 16:32], root[:, 32:48]
    DR, DH = DRc@K, DHc@K
    root_P = np.linalg.qr(np.vstack((np.eye(16),J)), mode='r')
    M = np.linalg.solve(root_P, np.eye(16))
    A = J@M
    ER, EH = DR@M, DH@M
    interaction = ER.T@EH+EH.T@ER
    out = dict(reference_precision_condition=float(np.linalg.cond(root_P)**2),
               whitening_identity_defect=float(np.linalg.norm(A.T@A+M.T@M-np.eye(16), 2)),
               interaction_spectral_norm=float(np.linalg.norm(interaction, 2)),
               canonical_column_defect_norms={}, variants={})
    for columns, D in [(RC, DRc), (H, DHc)]:
        for k in columns:
            # One column's rank-one contribution; not additive uncertainty fractions.
            out['canonical_column_defect_norms'][NAMES[k]] = float(np.linalg.norm(D[:, k])*np.linalg.norm((K@M)[k]))
    if envelope is not None:
        eta = np.sqrt(sigma_inv_square_sum)*np.linalg.norm(envelope@abs(K@M))
        measured = np.linalg.norm(ER, 2)
        if measured > eta+1e-8:
            raise AssertionError('P2 envelope smaller than measured RC defect')
        out['P2_RC_envelope'] = dict(eta_upper=float(eta), epsilon_upper=float(2*eta+eta*eta),
                                   measured_eta=float(measured), scope='Conditional float diagnostic, fixed anchor and supplied current envelope')
    de, dD = direct
    direct_forecasts = {}
    for task, obs in future_tasks().items():
        try:
            v, j, _, _ = model.evaluate(de, obs)
            direct_forecasts[task] = (v, j@dD@L, obs)
        except ValueError as error:
            direct_forecasts[task] = str(error)
    for variant, D, eindex in [('RC_only', DR, 49), ('H_only', DH, 50), ('combined', DR+DH, None)]:
        E = D@M
        eta = float(np.linalg.norm(E, 2));eps = 2*eta+eta*eta
        W = A.T@E+E.T@A+E.T@E
        eigen = np.linalg.eigvalsh(np.eye(16)+(W+W.T)/2)
        norm = float(np.linalg.norm(W, 2))
        if norm > eps+1e-8:
            raise AssertionError('P3 precision inequality inconsistency')
        root_Ps = np.linalg.qr(np.vstack((np.eye(16),J+D)), mode='r')
        r = root[:, 48];e = root[:, 49]+root[:, 50] if eindex is None else root[:, eindex]
        delta_gradient = J.T@e+D.T@r+D.T@e
        row = dict(eta=eta, epsilon=eps, sufficient_test='passes' if eps < 1 else 'inconclusive',
                   relative_precision_eigenvalues=eigen.tolist(),actual_relative_precision_defect=norm,
                   cost_difference=float(r@e+.5*(e@e)),
                   gradient_defect_dual_norm=float(np.linalg.norm(M.T@delta_gradient)),
                   Q_direct_transport=query_metrics(L[5], L[5], root_Ps, M, eps),
                   SOC_direct_transport=query_metrics(dD[0]@L, dD[0]@L, root_Ps, M, eps),
                   forecasts={})
        if isinstance(compressed, str):
            row['hybrid_transport'] = dict(status='unsupported_compressed_endpoint',reason=compressed)
            transport = None
        else:
            transport = hybrid_transport(direct, compressed, variant)
            row['hybrid_transport'] = dict(status='supported',
                SOC=query_metrics(dD[0]@L, transport[1][0]@L, root_Ps, M, eps))
        for task, ref in direct_forecasts.items():
            if isinstance(ref, str):
                row['forecasts'][task] = dict(status='direct_unsupported',reason=ref);continue
            rv, g, obs = ref
            forecast = dict(direct_transport=query_metrics(g, g, root_Ps, M, eps))
            if transport is not None:
                try:
                    v, j, _, _ = model.evaluate(transport[0], obs)
                    gh = j@transport[1]@L
                    forecast['hybrid_transport'] = dict(status='supported',
                        RMS_voltage_difference_uV=float(1e6*np.sqrt(np.mean((v-rv)**2))),
                        **query_metrics(g, gh, root_Ps, M, eps))
                except ValueError as error:
                    forecast['hybrid_transport'] = dict(status='unsupported',reason=str(error))
            row['forecasts'][task] = forecast
        out['variants'][variant] = row
    return out, M
