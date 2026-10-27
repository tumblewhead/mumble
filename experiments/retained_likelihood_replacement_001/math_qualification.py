#!/usr/bin/env python3
"""Finite, fabricated-only qualification of replacement_math.py.

No canonical vectors, observations, truth, model, or optimizer result files are
read.  Four known KKT optima plus two stop-budget cases are evaluated once.  The
output is exclusive and preserves any failure; it is never overwritten.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import resource
import sys
import time
import traceback

START_WALL = time.monotonic()
START_CPU = time.process_time()

import numpy as np
import scipy
import replacement_math as rm


class Checks:
    def __init__(self) -> None:
        self.rows = []

    def condition(self, name, value, detail=None):
        self.rows.append({"name": name, "pass": bool(value), "detail": detail})

    def close(self, name, actual, expected, tolerance):
        actual, expected = np.asarray(actual), np.asarray(expected)
        error = float(np.max(np.abs(actual - expected)))
        self.condition(name, math.isfinite(error) and error <= tolerance,
                       {"max_abs_error": error, "tolerance": tolerance})


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_matrix(small, large):
    i = np.arange(rm.DIM)[:, None]
    j = np.arange(rm.DIM)[None, :]
    # Fixed full, non-diagonal construction: no random or result-selected seed.
    basis = np.cos((i + .5) * (j + .25)) + np.eye(rm.DIM)
    orthogonal, _ = np.linalg.qr(basis)
    eigenvalues = np.geomspace(small, large, rm.DIM)
    matrix = (orthogonal * eigenvalues[None, :]) @ orthogonal.T
    matrix = .5 * (matrix + matrix.T)  # define the fabricated symmetric input
    return matrix / np.outer(rm.PUBLIC_SD, rm.PUBLIC_SD)


def known_block(name, target, gram, desired_gradient_x=None):
    prior = rm.prior_cost_gradient_hessian(target)
    desired = np.zeros(rm.DIM) if desired_gradient_x is None else desired_gradient_x
    return rm.QuadraticBlock(target, 1000., desired - prior["gradient"], gram, name)


def algebra_checks(checks):
    independent = rm.common_diagonal_mixture([0.], [[-1.], [1.]], [.25], [.5, .5])
    checks.close("negative_responsibility_Hessian", independent["hessian"], [[-12.]], 128. * rm.EPS)
    checks.close("symmetric_mixture_zero_gradient", independent["gradient"], [0.], 128. * rm.EPS)
    checks.condition("actual_public_prior_is_not_globally_convex",
                     rm.prior_cost_gradient_hessian(rm.PUBLIC_MEAN)["hessian"][5, 5] < 0.)

    # Independent cosh form of the equal-weight/common-variance split density.
    for index, displacement in enumerate((0., -.9, .7)):
        x = rm.PUBLIC_MEAN + .13 * rm.PUBLIC_SD * np.sin(np.arange(rm.DIM) + .3)
        x[5] = rm.PUBLIC_MEAN[5] + displacement * rm.PUBLIC_SD[5]
        mean = .5 * (rm.KERNEL_MEANS[0] + rm.KERNEL_MEANS[1])
        offset = .5 * (rm.KERNEL_MEANS[1, 5] - rm.KERNEL_MEANS[0, 5])
        variance = rm.KERNEL_VARIANCE
        u = offset * (x[5] - mean[5]) / variance[5]
        log_cosh = abs(float(u)) + math.log1p(math.exp(-2. * abs(float(u)))) - math.log(2.)
        expected_cost = (.5 * np.sum((x - mean) ** 2 / variance)
                         + .5 * np.sum(np.log(2. * math.pi * variance))
                         + .5 * offset * offset / variance[5] - log_cosh)
        expected_gradient = (x - mean) / variance
        expected_gradient[5] -= offset / variance[5] * math.tanh(float(u))
        expected_hessian = np.diag(1. / variance)
        expected_hessian[5, 5] -= (offset / variance[5]) ** 2 * (1. - math.tanh(float(u)) ** 2)
        observed = rm.prior_cost_gradient_hessian(x)
        checks.close(f"prior_cosh_cost_{index}", observed["cost"], expected_cost,
                     1024. * rm.EPS * max(1., abs(float(expected_cost))))
        checks.close(f"prior_cosh_gradient_{index}", observed["gradient"], expected_gradient,
                     1024. * rm.EPS * max(1., float(np.max(np.abs(expected_gradient)))))
        checks.close(f"prior_cosh_Hessian_{index}", observed["hessian"], expected_hessian,
                     1024. * rm.EPS * max(1., float(np.max(np.abs(expected_hessian)))))

    x = rm.PUBLIC_MEAN + .11 * rm.PUBLIC_SD * np.cos(np.arange(rm.DIM))
    direction_u = np.sin(np.arange(rm.DIM) + .7)
    direction_x = rm.PUBLIC_SD * direction_u
    h = rm.EPS ** (1. / 3.)
    plus = rm.prior_cost_gradient_hessian(x + h * direction_x)
    minus = rm.prior_cost_gradient_hessian(x - h * direction_x)
    center = rm.prior_cost_gradient_hessian(x)
    expected_first = float(center["gradient"] @ direction_x)
    checks.close("prior_directional_gradient", (plus["cost"] - minus["cost"]) / (2. * h),
                 expected_first, 512. * rm.EPS ** (2. / 3.) * max(1., abs(expected_first)))
    expected_second = rm.PUBLIC_SD * (center["hessian"] @ direction_x)
    checks.close("prior_directional_Hessian", rm.PUBLIC_SD * (plus["gradient"] - minus["gradient"]) / (2. * h),
                 expected_second, 512. * rm.EPS ** (2. / 3.) * max(1., float(np.max(np.abs(expected_second)))))

    support = rm.Support(-.006, .024)
    c, jac, hessians = support.path(x)
    cp, jp, _ = support.path(x + h * direction_x)
    cm, jm, _ = support.path(x - h * direction_x)
    checks.close("path_constraint_directional_Jacobian", (cp - cm) / (2. * h), jac @ direction_x,
                 512. * rm.EPS ** (2. / 3.))
    checks.close("path_constraint_directional_Hessians", (jp - jm) * rm.PUBLIC_SD / (2. * h),
                 np.einsum("kij,j->ki", hessians, direction_x) * rm.PUBLIC_SD,
                 512. * rm.EPS ** (2. / 3.))
    checks.condition("charge_extrema_preserve_zero", support.charge_min_Ah <= 0. <= support.charge_max_Ah)
    try:
        rm.Support(.001, .01)
    except ValueError:
        rejected = True
    else:
        rejected = False
    checks.condition("reject_charge_extrema_excluding_zero", rejected)
    invalid = x.copy()
    invalid[15] = 1. + math.sqrt(rm.EPS)
    before = invalid.copy()
    invalid_diagnostic = support.diagnostics(invalid)
    checks.condition("invalid_support_is_reported_without_clipping", not invalid_diagnostic["strictly_feasible"]
                     and np.array_equal(before, invalid))

    theta, alpha = rm.x_to_legacy(x)
    checks.close("entering_legacy_roundtrip", rm.legacy_to_x(theta, alpha), x, 16. * rm.EPS)
    # The u0 product is part of the map; its derivative has BOTH H and h0 terms.
    _, alpha_plus = rm.x_to_legacy(x + h * direction_x)
    _, alpha_minus = rm.x_to_legacy(x - h * direction_x)
    checks.close("u0_product_chain", (alpha_plus[8] - alpha_minus[8]) / (2. * h),
                 x[15] * direction_x[10] + x[10] * direction_x[15], 512. * rm.EPS ** (2. / 3.))
    alpha[4] = 0.
    try:
        rm.legacy_to_x(theta, alpha)
    except ValueError:
        rejected = True
    else:
        rejected = False
    checks.condition("reject_nonidentified_H_zero_inverse_map", rejected)

    gram = make_matrix(10., 300.)
    packed = rm.pack_lower(gram)
    checks.close("packed_lower_preserves_all_correlations", rm.unpack_lower(packed), gram, 0.)
    a = x.copy()
    g = np.cos(np.arange(rm.DIM)) / rm.PUBLIC_SD
    block = rm.QuadraticBlock(a, 7., g, gram)
    delta = .02 * direction_x
    cost, gradient, Hessian = block.at(a + delta)
    checks.close("full_quadratic_value", cost, 7. + g @ delta + .5 * delta @ gram @ delta, 1024. * rm.EPS)
    checks.close("full_quadratic_gradient", gradient, g + gram @ delta,
                 1024. * rm.EPS * max(1., float(np.max(np.abs(gradient)))))
    checks.close("full_quadratic_Hessian", Hessian, gram, 0.)
    bound = rm.prior_box_oscillation_bound()
    checks.condition("prior_oscillation_bound_finite_nonnegative",
                     math.isfinite(bound["prior_log_density_oscillation_upper_bound"])
                     and bound["prior_log_density_oscillation_upper_bound"] >= 0.)
    return {"negative_Hessian_witness": {"gradient": independent["gradient"].tolist(),
                                          "Hessian": independent["hessian"].tolist()},
            "public_prior": rm.public_prior(), "prior_box_bound": bound,
            "directional_step": h, "directional_tolerance_factor": 512. * rm.EPS ** (2. / 3.)}


def solver_checks(checks):
    warm = rm.PUBLIC_MEAN.copy()
    first_target = warm + .1 * rm.PUBLIC_SD * np.cos(np.arange(rm.DIM) + .4)
    second_target = warm + .12 * rm.PUBLIC_SD * np.sin(np.arange(rm.DIM) + 2.)
    first = known_block("dense_interior", first_target, make_matrix(10., 300.))
    second = known_block("dense_ill_conditioned_interior", second_target, make_matrix(10., 1e6))
    pair_a = rm.solve_pair(first, second, warm, -.003, .015)

    box_target = warm.copy()
    box_target[10], box_target[15] = 0., 1.
    box_target[11] = .7
    box_gradient = np.zeros(rm.DIM)
    box_gradient[10], box_gradient[15] = 4. / rm.PUBLIC_SD[10], -3. / rm.PUBLIC_SD[15]
    box = known_block("H_lower_and_h_upper_active", box_target, make_matrix(10., 300.), box_gradient)
    path_support = rm.Support(-.006, .024)
    path_target = warm.copy()
    path_target[11] = path_support.charge_max_Ah / math.exp(float(path_target[5]))
    path_gradient = 4. * path_support.path(path_target)[1][0] / rm.PUBLIC_SD[11]
    path = known_block("SOC_path_lower_active", path_target, make_matrix(10., 300.), path_gradient)
    pair_b = rm.solve_pair(box, path, warm, -.006, .024)

    target_rows = []
    coordinate_tolerance = 256. * math.sqrt(rm.EPS)
    for pair, targets in ((pair_a, (first_target, second_target)), (pair_b, (box_target, path_target))):
        checks.condition(f"{pair['frozen']['name']}:exactly_two_solves", pair["solves"] == 2
                         and pair["starts_per_arm"] == 1 and pair["retries"] == 0)
        checks.condition(f"{pair['frozen']['name']}:common_warm_and_scale",
                         pair["frozen"]["warm_start_x"] == pair["replacement"]["warm_start_x"]
                         and pair["policy"]["coordinate_SD"] == rm.PUBLIC_SD.tolist())
        for key, target in zip(("frozen", "replacement"), targets):
            row = pair[key]
            error = (np.array(row["candidate_x"]) - target) / rm.PUBLIC_SD
            checks.close(f"{row['name']}:known_optimum_scaled_coordinates", error, np.zeros(rm.DIM), coordinate_tolerance)
            expected_converged = (bool(row["optimizer"].get("success", False))
                                  and row["feasibility"]["strictly_feasible"] and row["KKT"]["passed"])
            checks.condition(f"{row['name']}:honest_status_from_raw_success_support_and_KKT",
                             (row["status"] == "converged") == expected_converged,
                             {"status": row["status"], "raw_status": row["optimizer"].get("status"),
                              "KKT": {name: row["KKT"].get(name) for name in ("stationarity_relative", "complementarity_scaled_max_abs", "dual_violation_scaled")}})
            if row["name"] in ("dense_interior", "H_lower_and_h_upper_active"):
                checks.condition(f"{row['name']}:required_convergence", row["status"] == "converged")
            checks.condition(f"{row['name']}:strictly_feasible", row["feasibility"]["strictly_feasible"])
            checks.condition(f"{row['name']}:bounded_counts", row["evaluation_counts"]["iterations"] <= 100
                             and row["evaluation_counts"]["combined_objective_gradient"] <= 1024
                             and row["evaluation_counts"]["final_verification"] == 1)
            checks.condition(f"{row['name']}:positive_analytic_lower_diagnostic",
                             row["curvature"]["global_lower_numerically_positive"])
            target_rows.append({"name": row["name"], "known_target_x": target.tolist(),
                                "maximum_scaled_coordinate_error": float(np.max(np.abs(error))),
                                "coordinate_tolerance": coordinate_tolerance})

    policy = rm.build_pair_policy(first, second)
    support = rm.Support(-.003, .015)
    iteration_stop = rm._solve_one(first, warm, support, policy, iteration_limit=1)
    budget_stop = rm._solve_one(first, warm, support, policy, evaluation_limit=1)
    checks.condition("iteration_limit_is_unresolved_not_success", iteration_stop["status"] == "unresolved"
                     and iteration_stop["evaluation_counts"]["iterations"] == 1
                     and not iteration_stop["optimizer"].get("success", False))
    checks.condition("evaluation_limit_preserves_finite_warm_and_receipt", budget_stop["status"] == "unresolved"
                     and budget_stop["budget_hit"] and budget_stop["evaluation_counts"]["combined_objective_gradient"] == 1
                     and budget_stop["candidate_x"] == warm.tolist())
    invalid_warm = warm.copy()
    invalid_warm[15] = 2.
    try:
        rm.solve_pair(first, second, invalid_warm, -.003, .015)
    except ValueError:
        rejected = True
    else:
        rejected = False
    checks.condition("reject_invalid_common_warm_before_solvers", rejected)
    checks.condition("caller_warm_unchanged", np.array_equal(warm, rm.PUBLIC_MEAN))
    unresolved = [pair[key]["name"] for pair in (pair_a, pair_b)
                  for key in ("frozen", "replacement") if pair[key]["status"] != "converged"]
    return {"pair_a": pair_a, "pair_b": pair_b, "known_targets": target_rows,
            "iteration_stop": iteration_stop, "evaluation_budget_stop": budget_stop,
            "optimizer_invocations": 6, "canonical_optimizer_invocations": 0,
            "model_calls": 0, "observation_reads": 0,
            "solver_limitations": {"unresolved_fixture_names": unresolved,
                                   "semantics": "Passing qualification establishes known-point accuracy and correct convergence/limit reporting; it does not establish universal optimizer convergence. Hard-case unresolved flags are preserved, not relaxed into success."},
            "budgets": "Four qualification solves at normal100/1024 limits plus one1-iteration case and one1-evaluation case; no retries"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not args.output.parent.is_dir():
        args.output.parent.mkdir(parents=True, exist_ok=True)
    stream = args.output.open("x", encoding="utf-8")
    checks = Checks()
    module_path = Path(rm.__file__).resolve()
    own_path = Path(__file__).resolve()
    root = own_path.parents[2]
    source_paths = [module_path, own_path, root / "plans/retained_likelihood_replacement_001.json",
                    root / "src/scm_hypothesis.c"]
    hashes = {str(path.relative_to(root)): digest(path) for path in source_paths}
    report = {"schema": "mumble_replacement_math_qualification_v1", "status": "running",
              "policy": rm.numerical_policy(), "source_hashes": hashes,
              "scope": "Fabricated algebra and six bounded synthetic solver invocations only",
              "environment": {"python": sys.version, "platform": platform.platform(),
                              "numpy": np.__version__, "scipy": scipy.__version__}}
    try:
        checks.condition("pinned_dependencies", np.__version__ == rm.PINNED_NUMPY and scipy.__version__ == rm.PINNED_SCIPY)
        report["algebra"] = algebra_checks(checks)
        report["solvers"] = solver_checks(checks)
        checks.condition("input_source_hashes_unchanged", hashes == {str(path.relative_to(root)): digest(path) for path in source_paths})
        report["status"] = "pass" if all(row["pass"] for row in checks.rows) else "failed_checks"
    except Exception as error:
        report["status"] = "failed_exception"
        report["exception"] = {"type": type(error).__name__, "message": str(error),
                               "traceback": traceback.format_exc()}
    finally:
        report["checks"] = checks.rows
        report["check_count"] = len(checks.rows)
        report["failed_count"] = sum(not row["pass"] for row in checks.rows)
        report["resources"] = {"wall_s_from_before_numerical_imports": time.monotonic() - START_WALL,
                               "CPU_s_from_before_numerical_imports": time.process_time() - START_CPU,
                               "own_peak_RSS_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
                               "final_encoding_excluded_from_time": True}
        # Nonfinite diagnostics must not conceal a failing receipt.
        def finite_json(value):
            if isinstance(value, float) and not math.isfinite(value):
                return repr(value)
            if isinstance(value, dict):
                return {str(key): finite_json(item) for key, item in value.items()}
            if isinstance(value, (list, tuple)):
                return [finite_json(item) for item in value]
            return value
        encoded = json.dumps(finite_json(report), indent=2, allow_nan=False) + "\n"
        if len(encoded.encode()) > 512 * 1024:
            report = {"schema": report["schema"], "status": "failed_output_budget",
                      "source_hashes": hashes, "check_count": report["check_count"],
                      "failed_count": report["failed_count"], "full_encoded_bytes": len(encoded.encode())}
            encoded = json.dumps(report, indent=2, allow_nan=False) + "\n"
        stream.write(encoded)
        stream.close()
    print(json.dumps({"status": report["status"], "output": str(args.output),
                      "checks": report["check_count"], "failed": report["failed_count"],
                      "bytes": args.output.stat().st_size, "sha256": digest(args.output)}))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
