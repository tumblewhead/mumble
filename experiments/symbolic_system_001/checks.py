"""Finite symbolic-system witnesses; no estimator repair or coverage qualification."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from experiments.foster_campaign_001.backend import ROOT, identity, prepare_c
from experiments.foster_feedback_001.estimator import Model
from experiments.foster_uncertainty_audit_001.conditional_packet import chart_from
from experiments.conditional_architecture_001.conditional import chart_amplitude_jacobian
from experiments.partitioned_coefficients_001.run import chart_shape_jacobian
from experiments.response_basis_attribution_001.basis import BasisField
from experiments.hysteresis_refinement_001.field import build
from experiments.h7_history_quality_001.history import source_receipt, verify_sources, write


def close(actual, expected, tol=1e-10):
    gap = float(np.max(np.abs(np.asarray(actual) - np.asarray(expected))))
    if not np.isfinite(gap) or gap > tol:
        raise AssertionError((gap, tol))
    return gap


def rc_response(obs, tau):
    free, forced = np.ones(3), np.zeros(3)
    dfree, dforced = np.zeros(3), np.zeros(3)
    rows = []
    for dt, current, *_ in obs:
        dose = dt / tau
        decay = np.exp(-dose)
        one = -np.expm1(-dose)
        dforced = decay * dforced + dose * decay * (forced - current)
        dfree = decay * dfree + dose * decay * free
        forced = decay * forced + one * current
        free = decay * free
        rows.append(np.r_[free, forced, dfree, dforced])
    return np.array(rows)


def rc_checks(out, baseline):
    registration = json.loads((baseline / 'registration.json').read_text())
    config = registration['config']
    query = next(q for q in registration['queries'] if q['id'] == 't0_a0')
    a = np.array(query['a']); center = np.array(query['s'])
    # Deliberately public nonzero boundary voltages exercise free and forced terms.
    a[1:4] = [.004, -.002, .003]
    index = np.arange(600)
    obs = np.zeros((600, 5))
    obs[:, 0] = np.array([1/35, 1/50, .2, .8])[index % 4]
    obs[:, 1] = np.array([0., .03, -.02, .012, -.025, 0.])[(index // 25) % 6]
    obs[:, 2] = 25.; obs[:, 3] = 3.7; obs[:, 4] = .001
    binary = build(out / 'response')
    cbinary = prepare_c(out, 35, config)[0]
    model = Model(cbinary, config)
    field = BasisField(config, center, binary, 2, 'log', 'public-symbolic-fixture')
    rows = field.rows(0, obs, 'public-symbolic-fixture')
    probes = []
    shifts = [np.zeros(3)]
    for j in range(3):
        for amount in [.35, -.55]:
            shift = np.zeros(3); shift[j] = amount; shifts.append(shift)
    native_gap = 0.
    for shift in shifts:
        shape = center.copy(); shape[:3] *= np.exp(shift)
        x = chart_from(a, shape)
        _, jac, end, _ = model.evaluate(x, obs)
        chain = np.column_stack((chart_amplitude_jacobian(a), chart_shape_jacobian(shape)))
        direct = jac @ chain
        coeff = rc_response(obs, shape[:3])
        expected_columns = -coeff[:, :6]
        expected_derivative = -(coeff[:, 6:9] * a[1:4] + coeff[:, 9:12] * a[6:9])
        native_gap = max(native_gap, close(direct[:, [1, 2, 3, 6, 7, 8]], expected_columns),
                         close(direct[:, 11:14], expected_derivative))
        _, dw, _ = field.basis_query(a, shape)
        approximate = (rows @ dw) * obs[:, 4, None]
        value_defect = ((approximate[:, 1:4] - direct[:, 1:4]) * a[1:4]
                        + (approximate[:, 6:9] - direct[:, 6:9]) * a[6:9])
        derivative_defect = approximate[:, 11:14] - direct[:, 11:14]
        probes.append(dict(log_tau_offset=shift.tolist(),
                           maximum_per_branch_voltage_defect_V=np.max(abs(value_defect), axis=0).tolist(),
                           maximum_per_branch_log_tau_derivative_defect_V=np.max(abs(derivative_defect), axis=0).tolist()))
    assert max(probes[0]['maximum_per_branch_voltage_defect_V']) < 1e-12
    assert max(probes[0]['maximum_per_branch_log_tau_derivative_defect_V']) > 1e-6

    # Native forecasts from a fixed public boundary: all other contributions retained.
    forecasts = []
    x = chart_from(a, center)
    for horizon in [.02, .07, .7, 6., 60.]:
        count = int(np.ceil(horizon)); future = np.zeros((count, 5))
        future[:, 0] = horizon / count; future[:, 1] = .025
        future[:, 2] = 25.; future[:, 4] = .001
        voltage, jac, end, _ = model.evaluate(x, future)
        decay = np.exp(-horizon / center[:3]); boundary = a[1:4]; R = a[6:9]
        expected_vrc = R * .025 + (boundary - R * .025) * decay
        expected_derivative = -(boundary - R * .025) * (horizon / center[:3]) * decay
        native_shape = jac[-1] @ chart_shape_jacobian(center)
        expected_voltage = (config['ocv_intercept_V'] + config['ocv_slope_V_per_SOC'] * end[0]
                            + a[9] * np.tanh(end[4]) - .025 * a[5] - sum(expected_vrc))
        gap = max(close(end[1:4], expected_vrc), close(native_shape[:3], expected_derivative),
                  close(jac[-1, 1:4], -decay), close(voltage[-1], expected_voltage))
        forecasts.append(dict(horizon_s=horizon, native_identity_max_gap=gap,
                              voltage_log_tau_derivatives_V=expected_derivative.tolist()))
    return dict(status='pass', records=len(obs), duration_s=float(obs[:, 0].sum()),
                observation_sha256=hashlib.sha256(obs.astype('<f8').tobytes()).hexdigest(),
                baseline_registration=identity(baseline/'registration.json'),
                public_query=query, boundary_voltage_override_V=a[1:4].tolist(),
                direct_binary=identity(cbinary), response_binary=identity(binary),
                maximum_native_recurrence_derivative_gap=native_gap, probes=probes, forecasts=forecasts,
                scope='Synthetic public inputs/queries; values and derivatives, no fitted accuracy or brownout authorization')


def uncertainty_checks():
    rng = np.random.default_rng(9083)
    max_shift_gap = max_nuisance_gap = 0.
    for _ in range(24):
        A = rng.normal(size=(20, 5))
        # Nuisance cross columns are deliberately correlated with target columns.
        A[:, 3] += .8*A[:, 0]
        y = rng.normal(size=20)
        D = .005*rng.normal(size=A.shape)
        e0 = .003*rng.normal(size=20)
        fitted = np.linalg.lstsq(A, y, rcond=None)[0]
        r = A@fitted-y; d = D@fitted+e0; B = A+D
        g = A.T@d + D.T@r + D.T@d
        shift = np.linalg.lstsq(B, y-e0, rcond=None)[0]-fitted
        max_shift_gap = max(max_shift_gap, close(shift, -np.linalg.solve(B.T@B, g)))
        P = A.T@A; eigen, V = np.linalg.eigh(P)
        root = (V*np.sqrt(eigen))@V.T; invroot = (V/np.sqrt(eigen))@V.T
        epsilon = np.linalg.norm(D@invroot, 2); assert epsilon < 1
        relative = np.linalg.eigvalsh(invroot@(B.T@B)@invroot)
        assert relative.min() >= (1-epsilon)**2-1e-12
        assert relative.max() <= (1+epsilon)**2+1e-12
        j = rng.normal(size=5)
        bound = np.sqrt(j@np.linalg.solve(P, j))*np.linalg.norm(invroot@g)/(1-epsilon)**2
        assert abs(j@shift) <= bound+1e-12
        assert np.linalg.norm(root@shift) <= np.linalg.norm(invroot@g)/(1-epsilon)**2+1e-12
        X, Z = A[:, :2], A[:, 2:]
        M = np.eye(20)-Z@np.linalg.pinv(Z)
        predicted = -np.linalg.solve(X.T@M@X, X.T@M@e0)
        actual = (np.linalg.lstsq(A, y-e0, rcond=None)[0]-fitted)[:2]
        max_nuisance_gap = max(max_nuisance_gap, close(actual, predicted))
    # A value-exact approximation with a wrong derivative at the fitted point.
    A = np.array([[1.], [0.]])
    y = np.array([0., 1.]); D = np.array([[0.], [.1]])
    shift = float(np.linalg.lstsq(A+D, y, rcond=None)[0][0])
    close(shift, .1/1.01)
    # Tiny absolute change doubles precision-axis scale in a weak direction.
    weak = np.diag([1., 1e-6]); defect = np.diag([0., 1e-6])
    eps = float(np.linalg.norm(defect@np.linalg.inv(weak), 2))
    assert eps == 1.
    # Fresh identical prior-free blocks: bias stays, formal standard deviation shrinks.
    repetitions = [1, 10, 1000]
    sd_units = []
    shifts = []
    for n in repetitions:
        design = np.ones((n, 1)); observations = rng.normal(size=n)
        ref = np.linalg.lstsq(design, observations, rcond=None)[0]
        approx = np.linalg.lstsq(design, observations+.01, rcond=None)[0]
        displacement = float((approx-ref)[0]); close(displacement, .01)
        variance = float(np.linalg.inv(design.T@design)[0, 0]); close(variance, 1/n)
        shifts.append(displacement); sd_units.append(displacement/np.sqrt(variance))
    # Review counterexamples: a retained prior and a changed design break broader claims.
    retained_prior_shifts = [.01*n/(n+1) for n in [1, 2]]
    assert retained_prior_shifts[0] != retained_prior_shifts[1]
    design_defect_shifts = []
    for observations in [np.array([1.]), np.array([1., 3.])]:
        design = np.ones((len(observations), 1))
        delta = (np.linalg.lstsq(1.5*design, observations, rcond=None)[0]
                 - np.linalg.lstsq(design, observations, rcond=None)[0])
        design_defect_shifts.append(float(delta[0]))
    close(design_defect_shifts, [-1/3, -2/3])
    return dict(status='pass', random_designs=24, max_exact_shift_gap=max_shift_gap,
                max_nuisance_projection_gap=max_nuisance_gap,
                zero_value_error_nonzero_fit_shift=shift,
                weak_direction_absolute_design_defect=1e-6, weak_direction_normalized_defect=eps,
                prior_free_repetitions=repetitions, additive_defect_fit_shifts=shifts,
                fixed_bias_in_formal_SD=sd_units,
                retained_prior_counterexample_shifts=retained_prior_shifts,
                fresh_observation_design_defect_counterexample_shifts=design_defect_shifts)


def aging_checks():
    rng = np.random.default_rng(129)
    a = rng.uniform(.2, .95, 40); b = rng.normal(size=40)
    ah = a+.001; bh = b+.002
    x = .3; xh = .32; bound = abs(xh-x)
    for ai, bi, ahi, bhi in zip(a, b, ah, bh):
        local = abs((ahi-ai)*x+(bhi-bi))
        bound = abs(ahi)*bound+local
        x = ai*x+bi; xh = ahi*xh+bhi
        assert abs(xh-x) <= bound+1e-12
    # Same final tau=2, different earlier tau, with a zero-current unit initial state.
    endings = [float(np.exp(-1/tau-1/2)) for tau in [1., 2.]]
    assert abs(endings[0]-endings[1]) > .1
    # Monotone R up/C down admits either tau direction.
    taus = [2*.75, 1.2*.5]; assert taus[0] > 1 and taus[1] < 1
    # Nontrivial positive kernels with bounded, state-dependent log errors.
    mu = np.array([.4, .6]); muh = mu.copy(); lower = upper = 0.
    for k in range(12):
        K = rng.uniform(.1, 1.2, (2, 2))
        delta = rng.uniform(-.01, .02, (2, 2))
        lower += float(delta.min()); upper += float(delta.max())
        mu = mu@K; muh = muh@(K*np.exp(delta))
        ratio = (muh/muh.sum())/(mu/mu.sum())
        assert min(ratio) >= np.exp(-(upper-lower))-1e-12
        assert max(ratio) <= np.exp(upper-lower)+1e-12
    eps = .01
    posterior = [float(1/(1+np.exp(-n*eps))) for n in [1, 100, 1000]]
    return dict(status='pass', state_steps=40, final_state_error=abs(xh-x), state_error_bound=bound,
                same_final_tau_different_path_endpoints=endings,
                R_increase_C_decrease_final_taus=taus, kernel_steps=12,
                kernel_accumulated_log_range=upper-lower, normalized_ratio=ratio.tolist(),
                equal_true_likelihood_label1_probability=.5,
                repeated_bias_log_ratio_per_observation=eps,
                biased_label1_posterior_at_N_1_100_1000=posterior,
                scope='Declared artificial evolution and finite kernels, not a characterized cell-aging law')


def optimization_checks():
    a=.999; ah=.99901; b=.1; eta_b=0.
    independent_equilibrium=b*((1-a)+eta_b)/(1-ah)
    gap=independent_equilibrium-b
    close(gap, b*((ah-a)+eta_b)/(1-ah))
    paired=b
    xp=xi=b
    for _ in range(100000):
        xp=ah*xp+(1-ah)*b
        xi=ah*xi+((1-a)+eta_b)*b
    close(xp,b,1e-12); close(xi,independent_equilibrium,1e-12)
    # Whole joint factor, with feature enclosure and independently bounded gradient.
    rng=np.random.default_rng(193); R=np.triu(rng.normal(size=(8,8)))
    dR=np.triu(rng.normal(size=(8,8))*.0001)
    phi0=rng.normal(size=8); L=rng.normal(size=(8,3))
    bound=np.linalg.norm(dR@phi0)+np.linalg.norm(dR@L,2)
    max_cost_gap=max_gradient_gap=0.
    for _ in range(100):
        z=rng.normal(size=3); z/=max(1.,np.linalg.norm(z)); phi=phi0+L@z
        dphi=rng.normal(size=(8,5)); r=R@phi; e=dR@phi
        J=R@dphi; dJ=dR@dphi
        actual_cost=.5*(np.linalg.norm((R+dR)@phi)**2-r@r)
        max_cost_gap=max(max_cost_gap, close(actual_cost,r@e+.5*(e@e)))
        actual_gradient=((R+dR)@dphi).T@((R+dR)@phi)-J.T@r
        max_gradient_gap=max(max_gradient_gap, close(actual_gradient,J.T@e+dJ.T@r+dJ.T@e))
        assert np.linalg.norm(e)<=bound+1e-12
        assert abs(actual_cost)<=np.linalg.norm(r)*np.linalg.norm(e)+.5*np.linalg.norm(e)**2+1e-12
    # Factor encoding preserves PSD while potentially deleting a weak direction.
    factor=np.diag([1.,.0001]); quantized=np.round(factor,3)
    assert np.linalg.matrix_rank(factor)==2 and np.linalg.matrix_rank(quantized)==1
    return dict(status='pass', coefficient_example=dict(a=a,ahat=ah,equilibrium=b,
                paired_endpoint=xp,independent_endpoint=xi,predicted_independent_bias=gap,steps=100000),
                joint_factor_queries=100, max_cost_identity_gap=max_cost_gap,
                max_gradient_identity_gap=max_gradient_gap, enclosure_defect_bound=bound,
                PSD_rank_loss_negative_control=dict(original_rank=2,encoded_rank=1),
                scope='Artificial coefficient examples and factor identities, no optimized runtime or resource claim')


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--baseline',type=Path,default=Path('experiments/partitioned_coefficients_001/followup002'))
    args=parser.parse_args(); args.out.mkdir(parents=True,exist_ok=False)
    sources=source_receipt()
    binding={str(p.relative_to(ROOT)):identity(p) for directory in ['specifications/symbolic_system_001','experiments/symbolic_system_001']
             for p in (ROOT/directory).glob('*') if p.is_file()}
    write(args.out/'registration.json',dict(source=sources,new_source_bindings=binding,
          scope='Finite deterministic witnesses of conditional symbolic identities, no accuracy/coverage qualification'))
    result=dict(status='finite_controls_pass',RC=rc_checks(args.out,args.baseline),
                uncertainty=uncertainty_checks(),aging=aging_checks(),optimization=optimization_checks())
    verify_sources(sources)
    for name, expected in binding.items():
        if identity(ROOT/name)!=expected:raise ValueError('source changed during control: '+name)
    write(args.out/'result.json',result)
    print(json.dumps(dict(status=result['status'],result=str(args.out/'result.json'))))


if __name__=='__main__':
    main()
