#!/usr/bin/env python3
"""Common supported reference prior and two bounded surrogate solves.

This module never reads observations and has no model/learner entry point.
Density is with respect to the original entering x chart.  The common support
normalizer is deliberately omitted only from MAP/cost differences; no evidence
or posterior-probability calculation is provided here.  SciPy is a host solver,
not part of the proposed embedded estimator.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any
import warnings

import numpy as np
import scipy
from scipy.optimize import Bounds, NonlinearConstraint, minimize


DIM = 16
Q_INDEX = 5
Z_INDEX = 11
EPS = float(np.finfo(np.float64).eps)
PINNED_NUMPY = "2.3.5"
PINNED_SCIPY = "1.17.0"
ROOT12 = 3.4641016151377545871
SPLIT_ALPHA = 0.7978845608028654
SPLIT_BETA = 0.6028102749890869
BASE_TOL = EPS ** (2.0 / 3.0)
KKT_TOL = 64.0 * BASE_TOL
GTOL = KKT_TOL
XTOL = 128.0 * EPS
MAX_ITERATIONS = 100
MAX_COMBINED_EVALUATIONS = 1024

COORDINATES = (
    "log_tau1", "log_tau2", "log_tau3", "log_gamma_plus",
    "log_gamma_minus", "log_Q", "R0", "R1", "R2", "R3", "H",
    "z0", "v10", "v20", "v30", "h0",
)
PUBLIC_LOWER = np.array([
    -4.199705077879927, -1.8971199848858813, .40546510810816438,
    1.6094379124341003, 1.6094379124341003, -3.5065578973199818,
    0., 0., 0., 0., 0., 0., -.25, -.25, -.25, -1.,
])
PUBLIC_UPPER = np.array([
    -1.8971199848858813, .40546510810816438, 3.4011973816621555,
    7.0900768357760917, 7.0900768357760917, -2.3025850929940455,
    1., 1., 1., 1., .1, 1., .25, .25, .25, 1.,
])
ENTERING_LOWER = PUBLIC_LOWER.copy()
ENTERING_UPPER = PUBLIC_UPPER.copy()
ENTERING_LOWER[11:15] = [.2, -.08, -.08, -.08]
ENTERING_UPPER[11:15] = [.95, .08, .08, .08]
PUBLIC_MEAN = np.zeros(DIM)
PUBLIC_MEAN[:3] = PUBLIC_LOWER[:3] + .5 * (PUBLIC_UPPER[:3] - PUBLIC_LOWER[:3])
PUBLIC_MEAN[3:6] = [5.0106352940962555, 5.7037824746562009, -2.8134107167600364]
PUBLIC_MEAN[6:10] = .1
PUBLIC_MEAN[10:12] = [.024, .68]
PUBLIC_SD = (PUBLIC_UPPER - PUBLIC_LOWER) / ROOT12
PUBLIC_SD[11] = .75 / ROOT12
PUBLIC_SD[12:15] = .16 / ROOT12
KERNEL_MEANS = np.tile(PUBLIC_MEAN, (2, 1))
KERNEL_MEANS[0, 5] -= SPLIT_ALPHA * PUBLIC_SD[5]
KERNEL_MEANS[1, 5] += SPLIT_ALPHA * PUBLIC_SD[5]
KERNEL_SD = PUBLIC_SD.copy()
KERNEL_SD[5] *= SPLIT_BETA
KERNEL_VARIANCE = KERNEL_SD * KERNEL_SD
KERNEL_PRECISION = 1.0 / KERNEL_VARIANCE
RANK_VECTOR = KERNEL_PRECISION * (KERNEL_MEANS[1] - KERNEL_MEANS[0])
for _array in (PUBLIC_LOWER, PUBLIC_UPPER, ENTERING_LOWER, ENTERING_UPPER,
               PUBLIC_MEAN, PUBLIC_SD, KERNEL_MEANS, KERNEL_SD,
               KERNEL_VARIANCE, KERNEL_PRECISION, RANK_VECTOR):
    _array.setflags(write=False)


def _vector(value: Any, size: int, name: str) -> np.ndarray:
    out = np.asarray(value, dtype=np.float64)
    if out.shape != (size,) or not np.all(np.isfinite(out)):
        raise ValueError(f"{name}: expected {size} finite values")
    return out.copy()


def _finite_float(value: Any, name: str) -> float:
    out = float(value)
    if not math.isfinite(out):
        raise ValueError(f"{name}: nonfinite")
    return out


def pack_lower(matrix: np.ndarray) -> list[float]:
    return np.asarray(matrix)[np.tril_indices(DIM)].tolist()


def unpack_lower(packed: Any) -> np.ndarray:
    values = _vector(packed, DIM * (DIM + 1) // 2, "packed Gram")
    out = np.zeros((DIM, DIM))
    indices = np.tril_indices(DIM)
    out[indices] = values
    out[(indices[1], indices[0])] = values
    return out


def common_diagonal_mixture(x: Any, means: Any, variance: Any,
                            weights: Any) -> dict[str, Any]:
    """Exact two-Gaussian kernel algebra, including negative rank-one term.

    The generic dimension is useful for an independent one-dimensional fixture.
    No probability or covariance clipping/repair is performed.
    """
    x = np.asarray(x, dtype=np.float64)
    means = np.asarray(means, dtype=np.float64)
    variance = np.asarray(variance, dtype=np.float64)
    weights = np.asarray(weights, dtype=np.float64)
    if (x.ndim != 1 or means.shape != (2, x.size) or variance.shape != x.shape
            or weights.shape != (2,) or not np.all(np.isfinite(x))
            or not np.all(np.isfinite(means)) or not np.all(np.isfinite(variance))
            or not np.all(variance > 0.) or not np.all(weights > 0.)
            or not np.all(np.isfinite(weights)) or float(weights.sum()) != 1.):
        raise ValueError("invalid two-component common-diagonal mixture")
    precision = 1.0 / variance
    differences = x[None, :] - means
    log_components = (np.log(weights) - .5 * np.sum(differences * differences * precision, axis=1)
                      - .5 * np.sum(np.log(variance)) - .5 * x.size * math.log(2. * math.pi))
    log_kernel = float(np.logaddexp(log_components[0], log_components[1]))
    responsibilities = np.exp(log_components - log_kernel)
    component_gradient = differences * precision
    delta_gradient = component_gradient[1] - component_gradient[0]
    gradient = component_gradient[0] + responsibilities[1] * delta_gradient
    rank_subtraction = responsibilities[0] * responsibilities[1] * np.outer(delta_gradient, delta_gradient)
    hessian = np.diag(precision) - rank_subtraction
    if not (math.isfinite(log_kernel) and np.all(np.isfinite(gradient))
            and np.all(np.isfinite(hessian))):
        raise FloatingPointError("nonfinite mixture calculation")
    return {"cost": -log_kernel, "gradient": gradient, "hessian": hessian,
            "responsibilities": responsibilities, "log_components": log_components,
            "rank_subtraction": rank_subtraction}


def prior_cost_gradient_hessian(x: Any) -> dict[str, Any]:
    """Negative log *unconditioned kernel mixture*, not normalized support law."""
    x = _vector(x, DIM, "x")
    return common_diagonal_mixture(x, KERNEL_MEANS, KERNEL_VARIANCE, [.5, .5])


def public_prior() -> dict[str, Any]:
    return {
        "chart": list(COORDINATES), "base_measure": "Lebesgue dx in original entering x chart",
        "public_unsplit_mean": PUBLIC_MEAN.tolist(), "public_unsplit_sd": PUBLIC_SD.tolist(),
        "kernel_means": KERNEL_MEANS.tolist(), "kernel_sd": KERNEL_SD.tolist(),
        "weights": [.5, .5], "entering_lower": ENTERING_LOWER.tolist(),
        "entering_upper": ENTERING_UPPER.tolist(),
        "source": "src/scm_hypothesis.c:public_belief,split_component",
        "supported_law": "1_D(x) * sum_j 0.5*N(x;mu_j,P) / Z_D",
        "normalizer": "Z_D common to both arms, omitted only from MAP/cost contrasts",
        "separate_component_conditioning": False,
    }


@dataclass(frozen=True)
class Support:
    charge_min_Ah: float
    charge_max_Ah: float

    def __post_init__(self) -> None:
        lo = _finite_float(self.charge_min_Ah, "charge_min_Ah")
        hi = _finite_float(self.charge_max_Ah, "charge_max_Ah")
        if not lo <= 0. <= hi:
            raise ValueError("charge extrema must include entering zero")
        object.__setattr__(self, "charge_min_Ah", lo)
        object.__setattr__(self, "charge_max_Ah", hi)

    def path(self, x: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Slacks >=0, their full x Jacobian, and two x Hessians."""
        x = _vector(x, DIM, "x")
        Q = math.exp(float(x[Q_INDEX]))
        # Match the unchanged model's charge/exp(logQ) order at active bounds.
        discharge = self.charge_max_Ah / Q
        charge = -self.charge_min_Ah / Q
        slacks = np.array([x[Z_INDEX] - discharge, 1. - x[Z_INDEX] - charge])
        jacobian = np.zeros((2, DIM))
        jacobian[:, Q_INDEX] = [discharge, charge]
        jacobian[:, Z_INDEX] = [1., -1.]
        hessians = np.zeros((2, DIM, DIM))
        hessians[:, Q_INDEX, Q_INDEX] = [-discharge, -charge]
        return slacks, jacobian, hessians

    def diagnostics(self, x: Any) -> dict[str, Any]:
        x = _vector(x, DIM, "x")
        path, _, _ = self.path(x)
        lower = x - ENTERING_LOWER
        upper = ENTERING_UPPER - x
        slacks = np.concatenate((lower / PUBLIC_SD, upper / PUBLIC_SD, path / PUBLIC_SD[Z_INDEX]))
        gamma64 = (64. * EPS) / (1. - 64. * EPS)
        box_scales = np.maximum(1., np.maximum(np.abs(x), np.maximum(np.abs(ENTERING_LOWER), np.abs(ENTERING_UPPER))))
        path_scales = np.array([
            max(1., abs(float(x[Z_INDEX])), abs(self.charge_max_Ah / math.exp(float(x[Q_INDEX])))),
            max(1., abs(float(x[Z_INDEX])), abs(self.charge_min_Ah / math.exp(float(x[Q_INDEX])))),
        ])
        allowances = np.concatenate((gamma64 * box_scales, gamma64 * box_scales, gamma64 * path_scales))
        raw = np.concatenate((lower, upper, path))
        names = [f"lower:{name}" for name in COORDINATES] + [f"upper:{name}" for name in COORDINATES] + ["SOC_path_lower", "SOC_path_upper"]
        return {
            "strictly_feasible": bool(np.all(raw >= 0.)),
            "within_declared_arithmetic_allowance": bool(np.all(raw >= -allowances)),
            "arithmetic_allowance_semantics": "floating arithmetic diagnostic only; never repair a negative slack or admit an invalid model input",
            "raw_slacks": raw.tolist(), "scaled_slacks": slacks.tolist(),
            "arithmetic_allowances": allowances.tolist(), "names": names,
            "minimum_scaled_slack": float(np.min(slacks)),
            "maximum_scaled_violation": max(0., -float(np.min(slacks))),
            "active_threshold_scaled": math.sqrt(EPS),
            "active_names": [name for name, slack in zip(names, slacks) if slack <= math.sqrt(EPS)],
            "negative_slack_names": [name for name, slack in zip(names, raw) if slack < 0.],
            "charge_min_Ah": self.charge_min_Ah, "charge_max_Ah": self.charge_max_Ah,
        }


def support_constraints(x: Any, charge_min_Ah: float, charge_max_Ah: float) -> dict[str, Any]:
    return Support(charge_min_Ah, charge_max_Ah).diagnostics(x)


@dataclass(frozen=True)
class QuadraticBlock:
    anchor: np.ndarray
    cost: float
    gradient: np.ndarray
    gram: np.ndarray
    name: str = "likelihood_block"

    def __post_init__(self) -> None:
        anchor = _vector(self.anchor, DIM, "anchor")
        gradient = _vector(self.gradient, DIM, "gradient")
        gram = np.asarray(self.gram, dtype=np.float64).copy()
        if gram.shape == (136,):
            gram = unpack_lower(gram)
        if gram.shape != (DIM, DIM) or not np.all(np.isfinite(gram)) or not np.array_equal(gram, gram.T):
            raise ValueError("Gram must be finite and exactly symmetric, or lower packed")
        for value in (anchor, gradient, gram):
            value.setflags(write=False)
        object.__setattr__(self, "anchor", anchor)
        object.__setattr__(self, "gradient", gradient)
        object.__setattr__(self, "gram", gram)
        object.__setattr__(self, "cost", _finite_float(self.cost, "cost"))

    @classmethod
    def from_evaluator(cls, payload: dict[str, Any], name: str = "likelihood_block") -> "QuadraticBlock":
        return cls(payload["x"], payload["cost"], payload["gradient"], payload["gram"], name)

    def at(self, x: Any) -> tuple[float, np.ndarray, np.ndarray]:
        dx = _vector(x, DIM, "x") - self.anchor
        gx = self.gram @ dx
        cost = math.fsum([self.cost, float(self.gradient @ dx), .5 * float(dx @ gx)])
        return cost, self.gradient + gx, self.gram


def legacy_to_x(theta: Any, alpha: Any) -> np.ndarray:
    theta = _vector(theta, 7, "legacy theta")
    alpha = _vector(alpha, 9, "legacy alpha")
    if alpha[4] <= 0.:
        raise ValueError("legacy warm start needs H>0 to identify h0=u0/H")
    x = np.empty(DIM)
    x[:5] = theta[:5]
    x[5] = theta[6]
    x[6:11] = alpha[:5]
    x[11] = theta[5]
    x[12:15] = alpha[5:8]
    x[15] = alpha[8] / alpha[4]
    return x


def x_to_legacy(x: Any) -> tuple[np.ndarray, np.ndarray]:
    x = _vector(x, DIM, "x")
    return x[[0, 1, 2, 3, 4, 11, 5]], np.array([*x[6:11], *x[12:15], x[10] * x[15]])


def numerical_policy() -> dict[str, Any]:
    """JSON-serializable policy for the parent executable contract."""
    return {
        "schema": "mumble_replacement_math_policy_v1",
        "versions": {"numpy": PINNED_NUMPY, "scipy": PINNED_SCIPY},
        "solver": "scipy.optimize.minimize(method='trust-constr')",
        "primary_documentation": "https://docs.scipy.org/doc/scipy-1.17.0/reference/optimize.minimize-trustconstr.html",
        "derivatives": "Analytic full objective gradient/Hessian and two SOC constraint Jacobians/Hessians; no finite differences in solves",
        "coordinate_map": "x=common_warm_start + diag(public_unsplit_SD)*u; same origin/scales for both arms; x density base measure unchanged",
        "objective_scale": "sqrt(max(1, ||D*G_old*D||_inf, ||D*G_new*D||_inf)); fixed before both solves",
        "objective_offset": "Drop each quadratic's constant value at the common warm start from its optimizer objective only; preserve it in every reported cost",
        "constraint_scale": "SOC path slacks divided by public unsplit SOC SD; box constraints in u",
        "max_iterations_per_solve": MAX_ITERATIONS,
        "max_actual_combined_objective_gradient_evaluations_per_solve": MAX_COMBINED_EVALUATIONS,
        "evaluation_accounting": "Every actual objective/gradient kernel evaluation, any Hessian-triggered evaluation, and one forced final verification consume the same cap; final slot reserved. Cached Hessians and callback logging do not evaluate an objective. Raw SciPy nfev/njev/nhev also reported.",
        "starts_per_arm": 1, "solves": 2, "retries": 0,
        "gtol": GTOL, "xtol": XTOL, "barrier_tol": BASE_TOL,
        "initial_tr_radius": 1., "initial_constr_penalty": 1.,
        "initial_barrier_parameter": BASE_TOL,
        "initial_barrier_tolerance": GTOL,
        "stopping_rationale": "gtol equals the independently checked numerical KKT tolerance; initial barrier is1/64 of that tolerance because SciPy can report gtol success before its barrier complementarity is small",
        "factorization_method": "QRFactorization", "sparse_jacobian": False,
        "keep_feasible": True,
        "independent_KKT_tolerance": KKT_TOL,
        "KKT_checks": "Relative scaled stationarity, absolute scaled complementarity and dual violation <=KKT tolerance; strict raw feasibility and optimizer success additionally required for converged status",
        "feasibility_arithmetic": "Compute SOC using charge/exp(logQ), matching model order. Report gamma(64)*max(1,operand magnitudes) allowances separately; raw negative slacks are never clipped or accepted for model evaluation",
        "linear_algebra": "No eigenvalue clipping, pseudoinverse covariance, covariance repair or curvature inversion; unmodified spectra reported diagnostically. trust-constr QR may fall back to SVD for constrained optimization; all emitted warnings are recorded and this does not define a posterior covariance.",
        "curvature_interpretation": "Local surrogate and prior curvature only; no calibrated intervals, supported moments or posterior probabilities",
        "thread_policy": "Supervisor sets single-thread BLAS environment before importing numpy/scipy; this module never changes process-global thread settings",
    }


def build_pair_policy(old: QuadraticBlock, new: QuadraticBlock) -> dict[str, Any]:
    norms = [float(np.linalg.norm(PUBLIC_SD[:, None] * block.gram * PUBLIC_SD[None, :], ord=np.inf)) for block in (old, new)]
    scale = math.sqrt(max(1., *norms))
    if not math.isfinite(scale):
        raise FloatingPointError("nonfinite common objective scale")
    policy = numerical_policy()
    policy.update({"objective_scale_value": scale, "scaled_Gram_infinity_norms": norms,
                   "coordinate_SD": PUBLIC_SD.tolist()})
    policy["policy_sha256"] = hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return policy


def curvature_diagnostics(block: QuadraticBlock, x: Any,
                          prior: dict[str, Any] | None = None) -> dict[str, Any]:
    # Solvers pass their counted final evaluation; reporting adds no hidden call.
    if prior is None:
        prior = prior_cost_gradient_hessian(x)
    lower = block.gram + np.diag(KERNEL_PRECISION) - .25 * np.outer(RANK_VECTOR, RANK_VECTOR)
    actual = block.gram + prior["hessian"]
    lower_scaled = PUBLIC_SD[:, None] * lower * PUBLIC_SD[None, :]
    actual_scaled = PUBLIC_SD[:, None] * actual * PUBLIC_SD[None, :]
    lower_eigenvalues = np.linalg.eigvalsh(lower_scaled)
    actual_eigenvalues = np.linalg.eigvalsh(actual_scaled)
    return {
        "prior_hessian_lower_packed": pack_lower(prior["hessian"]),
        "objective_hessian_lower_packed": pack_lower(actual),
        "analytic_global_lower_formula": "G + P^-1 - (1/4)*d*d^T, d=P^-1*(mu1-mu0)",
        "global_lower_scaled_eigenvalues": lower_eigenvalues.tolist(),
        "local_objective_scaled_eigenvalues": actual_eigenvalues.tolist(),
        "global_lower_numerically_positive": bool(lower_eigenvalues[0] > 0.),
        "interpretation": "Analytic lower matrix is global; computed eigenvalues are floating diagnostics, not rigorous interval certificates. No eigenvalues are altered or inverted.",
    }


class EvaluationBudgetExceeded(RuntimeError):
    pass


class _Objective:
    def __init__(self, block: QuadraticBlock, warm: np.ndarray, scale: float,
                 limit: int = MAX_COMBINED_EVALUATIONS) -> None:
        self.block, self.warm, self.scale, self.limit = block, warm, scale, limit
        self.warm_cost, self.warm_gradient, _ = block.at(warm)
        self.calls = 0
        self.hessian_requests = 0
        self.hessian_cache_misses = 0
        self.last_u = None
        self.last = None

    def evaluate(self, u: np.ndarray, final: bool = False) -> dict[str, Any]:
        if self.calls >= self.limit - (0 if final else 1):
            raise EvaluationBudgetExceeded("combined objective/gradient cap; final verification slot reserved")
        self.calls += 1
        dx = PUBLIC_SD * u
        x = self.warm + dx
        prior = prior_cost_gradient_hessian(x)
        q_difference = math.fsum([float(self.warm_gradient @ dx), .5 * float(dx @ self.block.gram @ dx)])
        q_gradient = self.warm_gradient + self.block.gram @ dx
        gradient_x = q_gradient + prior["gradient"]
        hessian_x = self.block.gram + prior["hessian"]
        variable_cost = (q_difference + prior["cost"]) / self.scale
        result = {
            "x": x, "prior": prior, "quadratic_cost": self.warm_cost + q_difference,
            "variable_scaled_cost": variable_cost,
            "gradient_x": gradient_x,
            "gradient_u_scaled": PUBLIC_SD * gradient_x / self.scale,
            "hessian_u_scaled": PUBLIC_SD[:, None] * hessian_x * PUBLIC_SD[None, :] / self.scale,
        }
        if not (math.isfinite(variable_cost) and np.all(np.isfinite(gradient_x))
                and np.all(np.isfinite(hessian_x))):
            raise FloatingPointError("nonfinite surrogate objective")
        self.last_u, self.last = np.array(u, copy=True), result
        return result

    def fun(self, u: np.ndarray) -> tuple[float, np.ndarray]:
        result = self.evaluate(u)
        return result["variable_scaled_cost"], result["gradient_u_scaled"]

    def hess(self, u: np.ndarray) -> np.ndarray:
        self.hessian_requests += 1
        if self.last_u is None or not np.array_equal(u, self.last_u):
            self.hessian_cache_misses += 1
            self.evaluate(u)
        return self.last["hessian_u_scaled"]


def _KKT(final: dict[str, Any], warm: np.ndarray, u: np.ndarray,
         support: Support, scale: float, multipliers: Any) -> dict[str, Any]:
    if multipliers is None or len(multipliers) != 2:
        return {"available": False, "passed": False, "reason": "solver multipliers unavailable"}
    path_v = _vector(multipliers[0], 2, "path multipliers")
    box_v = _vector(multipliers[1], DIM, "bound multipliers")
    slacks, jac, _ = support.path(final["x"])
    path_scaled = slacks / PUBLIC_SD[Z_INDEX]
    jac_u = jac * PUBLIC_SD[None, :] / PUBLIC_SD[Z_INDEX]
    lower_u = (ENTERING_LOWER - warm) / PUBLIC_SD
    upper_u = (ENTERING_UPPER - warm) / PUBLIC_SD
    lower_lambda = np.maximum(-box_v, 0.)
    upper_lambda = np.maximum(box_v, 0.)
    path_lambda = -path_v
    constraint_force = jac_u.T @ path_v + box_v
    stationarity = final["gradient_u_scaled"] + constraint_force
    stationarity_scale = max(1., float(np.linalg.norm(final["gradient_u_scaled"], ord=np.inf)), float(np.linalg.norm(constraint_force, ord=np.inf)))
    relative = float(np.linalg.norm(stationarity, ord=np.inf)) / stationarity_scale
    complements = np.concatenate((path_lambda * path_scaled, lower_lambda * (u - lower_u), upper_lambda * (upper_u - u)))
    complementarity = float(np.max(np.abs(complements)))
    dual_violation = max(0., -float(np.min(path_lambda)))
    natural_stationarity_x = stationarity * scale / PUBLIC_SD
    return {
        "available": True,
        "passed": bool(relative <= KKT_TOL and complementarity <= KKT_TOL and dual_violation <= KKT_TOL),
        "tolerance": KKT_TOL,
        "stationarity_u_scaled": stationarity.tolist(),
        "stationarity_u_scaled_infinity_norm": float(np.max(np.abs(stationarity))),
        "stationarity_normalization": stationarity_scale,
        "stationarity_relative": relative,
        "stationarity_x_natural_NLL": natural_stationarity_x.tolist(),
        "complementarity_scaled_max_abs": complementarity,
        "complementarity_natural_NLL_max_abs": complementarity * scale,
        "dual_violation_scaled": dual_violation,
        "path_signed_multipliers_scaled": path_v.tolist(),
        "box_signed_multipliers_scaled": box_v.tolist(),
        "path_signed_multipliers_natural": (path_v * scale / PUBLIC_SD[Z_INDEX]).tolist(),
        "box_signed_multipliers_natural": (box_v * scale / PUBLIC_SD).tolist(),
        "sign_convention": "g>=0 has signed v<=0; stationarity=gradient+J^T*v. Bound positive/negative parts are dual decomposition, not covariance or probability clipping.",
    }


def _solve_one(block: QuadraticBlock, warm: np.ndarray, support: Support,
               policy: dict[str, Any], *, iteration_limit: int = MAX_ITERATIONS,
               evaluation_limit: int = MAX_COMBINED_EVALUATIONS) -> dict[str, Any]:
    """Private override arguments exist only for fabricated budget qualification."""
    scale = policy["objective_scale_value"]
    objective = _Objective(block, warm, scale, evaluation_limit)
    lower_u = (ENTERING_LOWER - warm) / PUBLIC_SD
    upper_u = (ENTERING_UPPER - warm) / PUBLIC_SD
    constraint_calls = {"value": 0, "jacobian": 0, "hessian": 0}

    def constraint_value(u: np.ndarray) -> np.ndarray:
        constraint_calls["value"] += 1
        return support.path(warm + PUBLIC_SD * u)[0] / PUBLIC_SD[Z_INDEX]

    def constraint_jacobian(u: np.ndarray) -> np.ndarray:
        constraint_calls["jacobian"] += 1
        return support.path(warm + PUBLIC_SD * u)[1] * PUBLIC_SD[None, :] / PUBLIC_SD[Z_INDEX]

    def constraint_hessian(u: np.ndarray, v: np.ndarray) -> np.ndarray:
        constraint_calls["hessian"] += 1
        hessians = support.path(warm + PUBLIC_SD * u)[2]
        hessian = np.einsum("k,kij->ij", v, hessians)
        return PUBLIC_SD[:, None] * hessian * PUBLIC_SD[None, :] / PUBLIC_SD[Z_INDEX]

    trace = []
    last_accepted_u = np.zeros(DIM)
    last_state = None

    def callback(u: np.ndarray, state: Any) -> bool:
        nonlocal last_accepted_u, last_state
        last_accepted_u, last_state = np.array(u, copy=True), state
        trace.append({"iteration": int(state.nit), "objective_evaluations": objective.calls,
                      "variable_scaled_cost": float(state.fun), "optimality": float(state.optimality),
                      "constraint_violation": float(state.constr_violation), "trust_radius": float(state.tr_radius),
                      "barrier_parameter": float(state.barrier_parameter)})
        return False

    options = {key: policy[key] for key in (
        "gtol", "xtol", "barrier_tol", "initial_tr_radius", "initial_constr_penalty",
        "initial_barrier_parameter", "initial_barrier_tolerance", "factorization_method", "sparse_jacobian")}
    options.update({"maxiter": iteration_limit, "verbose": 0})
    constraint = NonlinearConstraint(constraint_value, [0., 0.], [np.inf, np.inf],
                                    jac=constraint_jacobian, hess=constraint_hessian, keep_feasible=True)
    budget_hit = False
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            result = minimize(objective.fun, np.zeros(DIM), method="trust-constr", jac=True,
                              hess=objective.hess, bounds=Bounds(lower_u, upper_u, keep_feasible=True),
                              constraints=[constraint], callback=callback, options=options)
            candidate_u = result.x
        except EvaluationBudgetExceeded:
            budget_hit = True
            result = last_state
            candidate_u = last_accepted_u
    final = objective.evaluate(candidate_u, final=True)
    feasibility = support.diagnostics(final["x"])
    multipliers = getattr(result, "v", None) if result is not None else None
    kkt = _KKT(final, warm, candidate_u, support, scale, multipliers)
    raw_success = bool(getattr(result, "success", False)) and not budget_hit
    if raw_success and feasibility["strictly_feasible"] and kkt["passed"]:
        status = "converged"
    elif feasibility["strictly_feasible"]:
        status = "unresolved"
    else:
        status = "infeasible_candidate"
    raw_keys = ("status", "success", "message", "nit", "nfev", "njev", "nhev", "cg_niter",
                "cg_stop_cond", "optimality", "constr_violation", "tr_radius", "barrier_parameter",
                "barrier_tolerance", "constr_penalty", "method")
    raw = {}
    if result is not None:
        for key in raw_keys:
            if hasattr(result, key):
                value = getattr(result, key)
                raw[key] = value.item() if isinstance(value, np.generic) else value
    if budget_hit:
        raw.update({"success": False, "external_stop": "combined_evaluation_budget",
                    "message": "Evaluation budget reached; last accepted iterate preserved, final verification counted"})
    if objective.calls > evaluation_limit or int(raw.get("nit", 0)) > iteration_limit:
        raise AssertionError("internal solver accounting exceeded budget")
    prior = final["prior"]
    return {
        "name": block.name, "status": status, "candidate_x": final["x"].tolist(),
        "warm_start_x": warm.tolist(), "optimizer": raw,
        "evaluation_counts": {"combined_objective_gradient": objective.calls,
                              "final_verification": 1, "Hessian_requests": objective.hessian_requests,
                              "Hessian_cache_misses": objective.hessian_cache_misses,
                              "constraint_calls": constraint_calls, "iterations": int(raw.get("nit", 0)),
                              "model_calls": 0, "observation_reads": 0},
        "budget_hit": budget_hit, "iteration_limit": iteration_limit, "evaluation_limit": evaluation_limit,
        "quadratic_cost": final["quadratic_cost"], "prior_kernel_cost": prior["cost"],
        "common_objective_without_support_normalizer": final["quadratic_cost"] + prior["cost"],
        "variable_scaled_optimizer_cost": final["variable_scaled_cost"],
        "omitted_quadratic_constant": objective.warm_cost,
        "prior_responsibilities": prior["responsibilities"].tolist(),
        "gradient_x": final["gradient_x"].tolist(), "feasibility": feasibility, "KKT": kkt,
        "curvature": curvature_diagnostics(block, final["x"], prior),
        "trace": trace, "warnings": [str(item.message) for item in caught],
        "uncertainty_interpretation": "No covariance/interval inferred from these local surrogate curvature diagnostics",
    }


def solve_pair(old: QuadraticBlock, new: QuadraticBlock, warm_start: Any,
               charge_min_Ah: float, charge_max_Ah: float) -> dict[str, Any]:
    """Exactly two solves after complete common-input validation; no retry."""
    if np.__version__ != PINNED_NUMPY or scipy.__version__ != PINNED_SCIPY:
        raise RuntimeError("numerical dependency version differs from frozen policy")
    warm = _vector(warm_start, DIM, "warm_start")
    support = Support(charge_min_Ah, charge_max_Ah)
    if not support.diagnostics(warm)["strictly_feasible"]:
        raise ValueError("common warm start outside exact support; no clipping or replacement")
    policy = build_pair_policy(old, new)
    before = warm.tobytes()
    frozen = _solve_one(old, warm, support, policy)
    replacement = _solve_one(new, warm, support, policy)
    if warm.tobytes() != before:
        raise AssertionError("common warm start mutated")
    return {"schema": "mumble_replacement_surrogate_pair_v1", "policy": policy,
            "prior": public_prior(), "frozen": frozen, "replacement": replacement,
            "status": "converged" if frozen["status"] == replacement["status"] == "converged" else "unresolved",
            "solves": 2, "starts_per_arm": 1, "retries": 0,
            "model_calls": 0, "observation_reads": 0,
            "evidence_ownership": "Arms are alternatives: new likelihood block replaces old; neither arm includes the other or a recursive posterior"}


def prior_box_oscillation_bound() -> dict[str, Any]:
    farthest = np.maximum(np.abs(ENTERING_LOWER[None, :] - KERNEL_MEANS),
                          np.abs(ENTERING_UPPER[None, :] - KERNEL_MEANS))
    maxima = .5 * np.sum(farthest * farthest / KERNEL_VARIANCE[None, :], axis=1)
    bound = -float(np.logaddexp(-maxima[0], -maxima[1]) - math.log(2.))
    return {"component_box_maximum_Mahalanobis_half": maxima.tolist(),
            "prior_log_density_oscillation_upper_bound": bound,
            "formula": "-log(0.5*exp(-M0)+0.5*exp(-M1)); D subset entering box",
            "limitation": "Algebraic bound evaluated in binary64; no optimizer, support normalizer or global constrained-target exclusion"}


def saved_candidate_prior_costs(candidates: dict[str, Any]) -> dict[str, Any]:
    if len(candidates) > 3:
        raise ValueError("at most three predeclared saved-candidate prior evaluations")
    rows = {}
    for name, x in candidates.items():
        prior = prior_cost_gradient_hessian(x)
        rows[name] = {"prior_kernel_cost": prior["cost"],
                      "responsibilities": prior["responsibilities"].tolist()}
    return {"candidates": rows, "evaluations": len(rows), "model_calls": 0,
            "support_normalizer_included": False, "bound": prior_box_oscillation_bound()}
