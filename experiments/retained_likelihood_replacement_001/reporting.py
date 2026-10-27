#!/usr/bin/env python3
"""Read-only reduction of one closed retained-likelihood replacement attempt.

No evaluator, battery model, learner or optimizer is reachable from this file.
Two explicitly counted post-inference prior algebra evaluations recover the
prior gradients needed to report the separately audited nonlinear gradients.
Inverse-curvature matrices are geometry diagnostics, never posterior moments
or confidence intervals. The full nonlinear likelihood Hessian is unavailable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import re
import struct
import sys
import time


DIM = 16
PREFIX = 252000
SCHEMA = "mumble_retained_likelihood_replacement_reporting_v1"
AREA = Path(__file__).resolve().parent
ROOT = AREA.parents[1]
TRUTH_MEMBER = (
    "experiments/continuous_learning_validation_001/implementation/primary/"
    "B_continuous/source/truth.bin"
)
TRUTH_BYTES = 16128000
TRUTH_SHA256 = "351b93c4157e80681eb5902f713750b6ab71d5c23a1b21a76cdbd8572861fc9f"
TRUTH_GIT_BLOB_SHA1 = "ed1672fc261e084f690cb3ae4bd63f58268a8163"
RESTORATION_MEMBER = "experiments/weighting_output_diagnostic_001/restoration.json"
RESTORATION_SHA256 = "2a8091607937df906cfd15b70c79aeabc55f6ce27867d83d9427ca3cd41844bb"
SOURCE_ID = "f0bd54ce53f1944d4f17070b6380dc8317ae895f2fd1628198a1c5408a67f79c"
SHAPE_LIMITATIONS = [
    "These are inverse-curvature shape matrices and transported local scales, not supported posterior moments or calibrated uncertainty.",
    "No centered interval, posterior probability or truth-in-interval coverage calculation is produced.",
    "A positive-definite matrix and an interior center do not establish a valid Gaussian approximation over the physical support.",
    "An unresolved candidate has no established stationary center. A nonstationary candidate has a nonzero local linear term. Neither is claimed to be the center of a posterior approximation.",
    "The audit Gauss-Newton-plus-prior matrix omits residual-weighted second derivatives of the nonlinear likelihood.",
    "No damping, eigenvalue alteration, pseudoinverse, rank cutoff or covariance inflation is applied.",
]


def strict_json(path: Path) -> dict:
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError(f"Duplicate JSON key: {key}")
            out[key] = value
        return out

    def constant(value):
        raise ValueError(f"Nonfinite JSON constant: {value}")

    def finite_float(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError(f"Overflowed JSON number: {value}")
        return parsed

    result = json.loads(path.read_text(), object_pairs_hook=pairs, parse_constant=constant,
                        parse_float=finite_float)
    if not isinstance(result, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return result


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def identity(path: Path) -> dict:
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": digest(path)}


def write_new_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def below(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    require(candidate.is_relative_to(root.resolve()), f"Path leaves root: {relative}")
    return candidate


def vector(np, values, count: int, name: str):
    result = np.asarray(values, dtype=np.float64)
    require(result.shape == (count,) and bool(np.all(np.isfinite(result))),
            f"{name}: expected {count} finite values")
    return result


def unpack(np, values, name: str):
    packed = vector(np, values, DIM * (DIM + 1) // 2, name)
    matrix = np.zeros((DIM, DIM), dtype=np.float64)
    indices = np.tril_indices(DIM)
    matrix[indices] = packed
    matrix[(indices[1], indices[0])] = packed
    return matrix


def full_matrix(np, values, name: str):
    return vector(np, values, DIM * DIM, name).reshape(DIM, DIM)


def prior_algebra(np, x, declared: dict) -> dict:
    """One post-inference evaluation of the frozen public kernel mixture.

    The operation order mirrors common_diagonal_mixture in the bound math
    source. The unknown common support normalizer is deliberately absent.
    """
    means = np.asarray(declared["kernel_means"], dtype=np.float64)
    sd = vector(np, declared["kernel_sd"], DIM, "prior kernel SD")
    weights = vector(np, declared["weights"], 2, "prior weights")
    require(means.shape == (2, DIM) and bool(np.all(np.isfinite(means))),
            "Invalid public prior means")
    require(bool(np.all(sd > 0.)) and bool(np.all(weights > 0.)) and
            float(weights.sum()) == 1., "Invalid prior scales or weights")
    variance = sd * sd
    precision = 1. / variance
    differences = x[None, :] - means
    logs = (
        np.log(weights) - .5 * np.sum(differences * differences * precision, axis=1)
        - .5 * np.sum(np.log(variance)) - .5 * DIM * math.log(2. * math.pi)
    )
    log_kernel = float(np.logaddexp(logs[0], logs[1]))
    responsibilities = np.exp(logs - log_kernel)
    component_gradient = differences * precision
    delta = component_gradient[1] - component_gradient[0]
    gradient = component_gradient[0] + responsibilities[1] * delta
    hessian = np.diag(precision) - responsibilities[0] * responsibilities[1] * np.outer(delta, delta)
    require(math.isfinite(log_kernel) and bool(np.all(np.isfinite(gradient))) and
            bool(np.all(np.isfinite(hessian))), "Nonfinite post-inference prior algebra")
    return {"cost": -log_kernel, "gradient": gradient, "hessian": hessian,
            "responsibilities": responsibilities}


def correlations(np, matrix):
    diagonal = np.diag(matrix)
    require(bool(np.all(diagonal >= 0.)), "Negative unmodified shape-matrix diagonal")
    scale = np.sqrt(diagonal)
    result = []
    for i in range(DIM):
        row = []
        for j in range(DIM):
            denominator = float(scale[i] * scale[j])
            row.append(float(matrix[i, j]) / denominator if denominator > 0. else None)
        result.append(row)
    return result


def local_shape(np, name: str, likelihood_gram, prior_hessian, scales, evaluator: dict,
                feasibility: dict, solver_status: str, kkt: dict, gradient_x) -> dict:
    """Invert only an unaltered PD interior matrix, then transport its full factor."""
    matrix = likelihood_gram + prior_hessian
    require(bool(np.array_equal(matrix, matrix.T)), name + ": matrix is asymmetric")
    scaled = matrix * np.outer(scales, scales)
    require(bool(np.all(np.isfinite(scaled))) and bool(np.array_equal(scaled, scaled.T)),
            name + ": scaled matrix is nonfinite or asymmetric")
    raw_slacks = np.asarray(feasibility["raw_slacks"], dtype=np.float64)
    require(raw_slacks.shape == (34,) and bool(np.all(np.isfinite(raw_slacks))),
            "Invalid saved support slacks")
    active = list(feasibility["active_names"])
    interior = bool(np.all(raw_slacks > 0.)) and not active
    output = {
        "name": name,
        "status": "diagnostics_only",
        "matrix_x_row_major": matrix.ravel().tolist(),
        "likelihood_Gram_x_row_major": likelihood_gram.ravel().tolist(),
        "prior_Hessian_x_row_major": prior_hessian.ravel().tolist(),
        "coordinate_scale": scales.tolist(),
        "scaled_matrix_definition": "diag(scale) * matrix_x * diag(scale); no objective-scale division",
        "gradient_x": gradient_x.tolist(),
        "gradient_x_infinity_norm": float(np.linalg.norm(gradient_x, ord=np.inf)),
        "scaled_gradient_infinity_norm": float(np.linalg.norm(scales * gradient_x, ord=np.inf)),
        "surrogate_solver_status": solver_status,
        "surrogate_KKT_passed": bool(kkt.get("passed", False)),
        "stationarity": (
            "Surrogate solver/KKT status applies only to the surrogate objective; "
            "audit nonlinear stationarity is not established by that result."
        ),
        "interior_for_unrestricted_shape": interior,
        "support_active_names": active,
        "support_raw_slacks": raw_slacks.tolist(),
        "support_active_threshold_scaled": feasibility["active_threshold_scaled"],
        "inverse_shape_available": False,
        "limitations": SHAPE_LIMITATIONS,
    }
    try:
        spectrum = np.linalg.eigvalsh(scaled)
    except np.linalg.LinAlgError as error:
        output.update(status="spectrum_unresolved", reason=str(error))
        return output
    require(bool(np.all(np.isfinite(spectrum))), name + ": nonfinite spectrum")
    output["scaled_eigenvalues"] = spectrum.tolist()
    output["scaled_matrix_positive_eigenvalues"] = bool(np.all(spectrum > 0.))
    condition = float(spectrum[-1] / spectrum[0]) if spectrum[0] > 0. else None
    output["scaled_condition_number_2"] = condition if condition is None or math.isfinite(condition) else None
    if not interior:
        output.update(status="unrestricted_shape_suppressed_active_support",
                      reason="A bound is active under the frozen support diagnostics or a raw slack is nonpositive.")
        return output
    if not bool(np.all(spectrum > 0.)):
        output.update(status="unrestricted_shape_suppressed_nonpositive_curvature",
                      reason="The unmodified matrix has a nonpositive computed eigenvalue.")
        return output
    try:
        factor = np.linalg.cholesky(scaled)
    except np.linalg.LinAlgError as error:
        output.update(status="unrestricted_shape_suppressed_Cholesky_failure", reason=str(error))
        return output
    inverse_lower = np.linalg.solve(factor, np.eye(DIM))
    inverse_x_factor = scales[:, None] * inverse_lower.T
    inverse_x = inverse_x_factor @ inverse_x_factor.T
    inverse_scaled = inverse_lower.T @ inverse_lower
    residual = scaled @ inverse_scaled - np.eye(DIM)
    denominator = float(np.linalg.norm(scaled, ord=np.inf) *
                        np.linalg.norm(inverse_scaled, ord=np.inf) + 1.)
    endpoint_map = full_matrix(np, evaluator["endpoint_derivative"], "endpoint chart map")
    physical_map = full_matrix(np, evaluator["endpoint_physical_derivative"], "endpoint physical map")
    endpoint_factor = endpoint_map @ inverse_x_factor
    physical_factor = physical_map @ inverse_x_factor
    endpoint_shape = endpoint_factor @ endpoint_factor.T
    physical_shape = physical_factor @ physical_factor.T
    for value in (inverse_x, endpoint_shape, physical_shape):
        require(bool(np.all(np.isfinite(value))), name + ": nonfinite inverse or transport")
    output.update({
        "status": "interior_positive_definite_local_shape",
        "inverse_shape_available": True,
        "shape_interpretation": (
            "Local inverse-curvature geometry at the returned point. This does not "
            "assert a stationary center, a posterior covariance, or calibrated uncertainty."
        ),
        "Cholesky_diagonal": np.diag(factor).tolist(),
        "Cholesky_reconstruction_relative_infinity_norm": float(
            np.linalg.norm(factor @ factor.T - scaled, ord=np.inf) /
            np.linalg.norm(scaled, ord=np.inf)
        ),
        "inverse_scaled_residual_infinity_norm": float(np.linalg.norm(residual, ord=np.inf)),
        "inverse_scaled_backward_error_infinity_norm": float(np.linalg.norm(residual, ord=np.inf)) / denominator,
        "inverse_curvature_x_row_major": inverse_x.ravel().tolist(),
        "inverse_curvature_x_correlations": correlations(np, inverse_x),
        "endpoint_chart_shape_row_major": endpoint_shape.ravel().tolist(),
        "endpoint_chart_correlations": correlations(np, endpoint_shape),
        "endpoint_physical_shape_row_major": physical_shape.ravel().tolist(),
        "endpoint_physical_correlations": correlations(np, physical_shape),
        "transport": "T * inverse(matrix_x) * T^T, computed by forward transport of its full Cholesky-derived factor; no inverse endpoint map",
    })
    scales_out = {
        "logQ": math.sqrt(float(inverse_x[5, 5])),
        "Q_Ah": math.sqrt(float(physical_shape[5, 5])),
        "entering_SOC": math.sqrt(float(inverse_x[11, 11])),
        "endpoint_SOC": math.sqrt(float(endpoint_shape[11, 11])),
    }
    output["target_shape_scales"] = scales_out
    output["twice_target_shape_scales"] = {key: 2. * value for key, value in scales_out.items()}
    return output


def validate_evaluator(np, payload: dict, expected_x) -> None:
    require(payload["schema"] == "mumble_retained_likelihood_stream_evaluator_v1" and
            payload["status"] == "ok", "Evaluator did not complete")
    require(payload["prefix_requested"] == payload["records_read"] ==
            payload["records_accumulated"] == payload["model_step_calls"] ==
            payload["model_predict_calls"] == PREFIX, "Evaluator scope/counter mismatch")
    require(payload["model_init_calls"] == 1 and payload["input_bytes_read"] == PREFIX * 32,
            "Evaluator init/byte extent mismatch")
    require(payload["sigma_V"] == .001 and all(
        payload[key] == 0 for key in ("source_generations", "learner_ingests", "fit_calls", "truth_reads")
    ), "Evaluator forbidden call or sigma mismatch")
    x = vector(np, payload["x"], DIM, "evaluator x")
    require(bool(np.array_equal(x, expected_x)), "Evaluator candidate mismatch")
    vector(np, payload["gradient"], DIM, "evaluator gradient")
    unpack(np, payload["gram"], "evaluator Gram")
    endpoint = vector(np, payload["endpoint_x"], DIM, "endpoint x")
    physical = vector(np, payload["endpoint_state"], DIM, "physical endpoint")
    full_matrix(np, payload["endpoint_derivative"], "endpoint map")
    full_matrix(np, payload["endpoint_physical_derivative"], "physical endpoint map")
    require(math.isfinite(payload["cost"]) and payload["cost"] >= 0., "Invalid likelihood cost")
    require(physical[5] == math.exp(float(x[5])) and
            endpoint[11] == float(x[11]) - payload["charge_Ah"] / math.exp(float(x[5])),
            "Endpoint Q/SOC mapping mismatch")


def summarize_arm(np, name: str, arm: dict, anchor: dict, audit: dict,
                  public_prior: dict, scales) -> dict:
    x = vector(np, arm["candidate_x"], DIM, "candidate")
    validate_evaluator(np, audit, x)
    prior = prior_algebra(np, x, public_prior)
    require(prior["cost"] == arm["prior_kernel_cost"],
            name + ": reconstructed prior cost differs from saved counted evaluation")
    saved_prior_hessian = unpack(np, arm["curvature"]["prior_hessian_lower_packed"], "saved prior Hessian")
    require(bool(np.array_equal(prior["hessian"], saved_prior_hessian)),
            name + ": reconstructed prior Hessian differs from saved counted evaluation")
    anchor_gram = unpack(np, anchor["gram"], "anchor Gram")
    audit_gram = unpack(np, audit["gram"], "audit Gram")
    surrogate_gradient = vector(np, arm["gradient_x"], DIM, "surrogate gradient")
    audit_gradient = vector(np, audit["gradient"], DIM, "audit likelihood gradient") + prior["gradient"]
    surrogate_matrix = anchor_gram + prior["hessian"]
    require(bool(np.array_equal(
        surrogate_matrix, unpack(np, arm["curvature"]["objective_hessian_lower_packed"], "saved surrogate Hessian")
    )), name + ": saved surrogate Hessian reconstruction mismatch")
    output = {
        "name": name, "candidate_x": x.tolist(),
        "entering_Q_Ah": math.exp(float(x[5])), "entering_SOC": float(x[11]),
        "endpoint_Q_Ah": audit["endpoint_state"][5], "endpoint_SOC": audit["endpoint_x"][11],
        "endpoint_x": audit["endpoint_x"], "endpoint_physical_state": audit["endpoint_state"],
        "computed_nonlinear_likelihood_cost": audit["cost"],
        "prior_kernel_cost": prior["cost"],
        "computed_common_objective_without_support_normalizer": audit["cost"] + prior["cost"],
        "surrogate_quadratic_cost": arm["quadratic_cost"],
        "surrogate_common_objective_without_support_normalizer": arm["common_objective_without_support_normalizer"],
        "surrogate_status": arm["status"], "optimizer": arm["optimizer"],
        "KKT": arm["KKT"], "feasibility": arm["feasibility"],
        "evaluation_counts": arm["evaluation_counts"], "warnings": arm["warnings"],
        "prior_gradient_x": prior["gradient"].tolist(),
        "prior_responsibilities": prior["responsibilities"].tolist(),
        "audited_nonlinear_common_gradient_x": audit_gradient.tolist(),
        "audited_nonlinear_common_scaled_gradient": (scales * audit_gradient).tolist(),
        "local_shapes": {},
    }
    output["local_shapes"]["surrogate_Hessian"] = local_shape(
        np, "surrogate Hessian = G_anchor + prior Hessian", anchor_gram, prior["hessian"],
        scales, audit, arm["feasibility"], arm["status"], arm["KKT"], surrogate_gradient,
    )
    output["local_shapes"]["audit_GN_plus_prior"] = local_shape(
        np, "audit Gauss-Newton-plus-prior matrix = G_candidate + prior Hessian",
        audit_gram, prior["hessian"], scales, audit, arm["feasibility"],
        arm["status"], arm["KKT"], audit_gradient,
    )
    return output


def read_verified_endpoint_truth(root: Path, truth_root: Path, inference_complete: bool) -> tuple[dict, dict]:
    """Called only after all complete inference receipts and raw results validate."""
    require(inference_complete, "Truth cannot be read before inference closure")
    metadata_path = below(root, RESTORATION_MEMBER)
    require(digest(metadata_path) == RESTORATION_SHA256, "Truth restoration metadata identity mismatch")
    metadata = strict_json(metadata_path)
    require(metadata["schema"] == "mumble_weighting_evidence_restoration_v1" and
            metadata["status"] == "verified_selected_members_restored", "Unverified truth restoration")
    matches = [item for item in metadata["selected_members_SHA256_and_Git_blob_verified"]
               if item["path"] == TRUTH_MEMBER]
    require(len(matches) == 1, "Truth member not uniquely bound")
    member = matches[0]
    require(member["bytes"] == TRUTH_BYTES and member["sha256"] == TRUTH_SHA256 and
            member["git_blob_sha1"] == TRUTH_GIT_BLOB_SHA1, "Truth archive member identity mismatch")
    path = below(truth_root, TRUTH_MEMBER)
    require(path.stat().st_size == TRUTH_BYTES, "Truth byte length mismatch")
    h256 = hashlib.sha256()
    hgit = hashlib.sha1(f"blob {TRUTH_BYTES}\0".encode("ascii"))
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            h256.update(block)
            hgit.update(block)
    require(h256.hexdigest() == TRUTH_SHA256 and hgit.hexdigest() == TRUTH_GIT_BLOB_SHA1,
            "Truth whole-member digest mismatch")
    with path.open("rb") as stream:
        stream.seek((PREFIX - 1) * 32)
        record = stream.read(32)
    require(len(record) == 32, "Incomplete endpoint truth record")
    next_index, Q, soc, unused_clean_voltage = struct.unpack("<Qddd", record)
    require(next_index == PREFIX and math.isfinite(Q) and Q > 0. and
            math.isfinite(soc) and 0. <= soc <= 1., "Invalid endpoint truth record")
    truth = {
        "next_index": next_index, "capacity_Ah": Q, "SOC": soc,
        "decoded_records": 1, "record_sha256": hashlib.sha256(record).hexdigest(),
        "source_path": str(path), "source_bytes": TRUTH_BYTES,
        "source_sha256": TRUTH_SHA256, "source_git_blob_sha1": TRUTH_GIT_BLOB_SHA1,
        "restoration_metadata_sha256": RESTORATION_SHA256,
        "timing": "Decoded only after the complete closed inference evidence was validated.",
        "clean_voltage_used": False,
    }
    return truth, {"path": str(path), "bytes": TRUTH_BYTES, "sha256": TRUTH_SHA256}


def bind_file(path: Path, expected: dict, bindings: dict) -> None:
    require(path.is_file(), f"Missing bound file: {path}")
    actual = identity(path)
    require(actual["sha256"] == expected["sha256"], f"File digest mismatch: {path}")
    if "bytes" in expected:
        require(actual["bytes"] == expected["bytes"], f"File length mismatch: {path}")
    key = str(path.resolve())
    require(key not in bindings or bindings[key] == actual, f"Conflicting file binding: {path}")
    bindings[key] = actual


def bind_declared_files(root: Path, declared, bindings: dict, name: str) -> None:
    """Explicit accepted receipt forms: named records or path-to-hash source maps."""
    if isinstance(declared, list):
        rows = [(None, item) for item in declared]
    else:
        require(isinstance(declared, dict), f"{name} must be a mapping or list")
        rows = list(declared.items())
    require(bool(rows), f"Empty {name}")
    for key, item in rows:
        if isinstance(item, str):
            require(isinstance(key, str), f"{name}: hash needs a path key")
            record = {"path": key, "sha256": item}
        else:
            require(isinstance(item, dict) and "sha256" in item, f"{name}: invalid identity record")
            record = dict(item)
            record.setdefault("path", key)
        require(isinstance(record["path"], str), f"{name}: missing file path")
        path = Path(record["path"])
        path = path.resolve() if path.is_absolute() else below(root, str(path))
        require(path.name != "truth.bin", "Canonical inference bindings unexpectedly contain truth")
        require(re.fullmatch(r"[0-9a-f]{64}", record["sha256"]) is not None, f"{name}: invalid SHA256")
        bind_file(path, record, bindings)


def load_closed_attempt(root: Path, attempt: Path, bindings: dict) -> dict:
    receipt_path = below(attempt, "receipt.json")
    receipt = strict_json(receipt_path)
    require(receipt["schema"] == "mumble_retained_likelihood_replacement_receipt_v1" and
            receipt["status"] == "completed" and receipt["canonical_inference_closed"] is True,
            "Canonical inference has no complete closed receipt")
    require(type(receipt["truth_reads"]) is int and receipt["truth_reads"] == 0,
            "Inference receipt reports truth access")
    bindings[str(receipt_path)] = identity(receipt_path)
    files = receipt["files"]
    require(isinstance(files, dict) and bool(files), "Missing closed attempt manifest")
    for relative, expected in files.items():
        require(relative != "receipt.json", "Receipt cannot self-hash in its closed file manifest")
        require(isinstance(expected, dict) and "sha256" in expected and "bytes" in expected,
                f"Invalid closed file record: {relative}")
        bind_file(below(attempt, relative), expected, bindings)
    actual_files = {str(path.relative_to(attempt)) for path in attempt.rglob("*") if path.is_file()}
    require(actual_files == set(files) | {"receipt.json"}, "Unmanifested or missing closed inference files")
    require(sum((attempt / path).stat().st_size for path in actual_files) ==
            receipt["closed_output_bytes_including_receipt"], "Closed output byte accounting mismatch")
    bind_declared_files(root, receipt["source_bindings"], bindings, "source bindings")
    bind_declared_files(root, receipt["input_bindings"], bindings, "input bindings")
    bind_declared_files(root, receipt["generated_input_and_solver_bindings"], bindings, "generated input bindings")
    paths = {
        "result": "result.json", "input_summary": "prefix_input.json", "anchors": "anchors.json",
        "old_anchor": "old_anchor/stdout.json", "replacement_anchor": "replacement_anchor/stdout.json",
        "frozen_audit": "frozen_audit/stdout.json", "replacement_audit": "replacement_audit/stdout.json",
        "pair": "solves/pair.json", "frozen_solution": "solves/frozen.result.json",
        "replacement_solution": "solves/replacement.result.json",
        "worker_result": "solves/worker_result.json",
    }
    for path in paths.values():
        require(path in files, f"Required result absent from closure manifest: {path}")
    values = {key: strict_json(below(attempt, relative)) for key, relative in paths.items()}
    result = values["result"]
    require(result["schema"] == "mumble_retained_likelihood_replacement_result_v1",
            "Unexpected result schema")
    require(result["status"] == "completed" and result["errors"] == [], "Inference result is incomplete or failed")
    require(result["source_id"] == SOURCE_ID and result["prefix_records"] == PREFIX,
            "Source or fixed-prefix mismatch")
    require(re.fullmatch(r"[0-9a-f]{40}", result["source_revision"]) is not None and
            re.fullmatch(r"[0-9a-f]{64}", result["plan_sha256"]) is not None,
            "Invalid source/plan identity")
    require(any(item["sha256"] == result["plan_sha256"] for item in bindings.values()),
            "Executed plan digest is not among the closed bound files")
    require(result["coverage_validated"] is False and result["candidate_promoted"] is False,
            "Unexpected inference promotion claim")
    require(result["counts"] == receipt["counts"], "Result/receipt call counts disagree")
    require(result["source_revision"] == receipt["source_revision"] and
            result["plan_sha256"] == receipt["plan_sha256"], "Result/receipt source identity mismatch")
    expected_counts = {
        "supervisor_invocations": 1, "model_passes_started": 4, "model_passes_completed": 4,
        "model_steps_reported": 4 * PREFIX, "model_step_count_complete": True,
        "solver_invocations_reserved": 2, "solver_started_markers": 2, "solver_results_saved": 2,
        "learner_calls": 0, "fitter_calls": 0, "truth_reads": 0, "retries": 0,
    }
    require(receipt["counts"] == expected_counts, "Closed canonical call budget mismatch")
    require(len(result["passes"]) == 4, "Expected the frozen four completed evaluator passes")
    resources, limits = receipt["resources"], receipt["limits"]
    require(resources["CPU_total_s"] <= limits["CPU_total_s_max"] and
            resources["wall_s_through_snapshot"] <= limits["wall_total_s_max"] and
            resources["supervisor_peak_RSS_bytes"] <= limits["supervisor_RSS_bytes_max"] and
            resources["maximum_exact_child_peak_RSS_bytes"] <= limits["child_RSS_bytes_max"] and
            receipt["closed_output_bytes_including_receipt"] <= limits["closed_output_bytes_max"],
            "Closed execution resource limit failed")
    require({child["id"] for child in receipt["children"]} ==
            {"old_anchor", "replacement_anchor", "solver_process", "frozen_audit", "replacement_audit"} and
            len(receipt["children"]) == 5, "Unexpected canonical child composition")
    for child in receipt["children"]:
        saved = strict_json(below(attempt, child["id"] + "/resources.json"))
        require(saved == child["resources"] and saved["exit_code"] == 0 and
                saved["resource_violations"] == [] and saved["output_truncated"] is False,
                "Child resource receipt failed or disagrees")
    pair, worker = values["pair"], values["worker_result"]
    require(pair["schema"] == "mumble_replacement_surrogate_pair_v1" and
            pair["solves"] == 2 and pair["starts_per_arm"] == 1 and pair["retries"] == 0 and
            pair["model_calls"] == pair["observation_reads"] == 0, "Invalid paired solver scope")
    require(worker["schema"] == "mumble_surrogate_worker_status_v1" and worker["status"] == "completed" and
            worker["exit_code"] == 0 and worker["truth_reads"] == 0 and
            worker["model_calls"] == worker["observation_reads"] == 0, "Solver worker is not complete")
    require(worker["counts"] == {"started_markers": 2, "solver_calls_entered": 2,
                                "solver_calls_returned": 2, "results_saved": 2},
            "Solver worker did not close exactly two reserved calls")
    for label in ("frozen", "replacement"):
        require(pair[label] == values[f"{label}_solution"], f"{label}: pair and saved solution disagree")
        candidate = result["candidates"][label]
        require(candidate["solver_path"] == paths[f"{label}_solution"] and
                candidate["audit_path"] == paths[f"{label}_audit"], f"{label}: result path mismatch")
        require(candidate["x"] == pair[label]["candidate_x"] and
                candidate["prior_kernel_cost"] == pair[label]["prior_kernel_cost"] and
                candidate["solver_status"] == pair[label]["status"], f"{label}: result fields disagree")
        require(pair[label]["feasibility"]["strictly_feasible"] is True,
                f"{label}: audited candidate was not strictly feasible")
    values.update(receipt=receipt, paths=paths)
    return values


def validate_comparison_and_transaction(closed: dict) -> dict:
    left, right = closed["frozen_audit"], closed["replacement_audit"]
    lf, lr = left["cost"], right["cost"]
    pf = closed["pair"]["frozen"]["prior_kernel_cost"]
    pr = closed["pair"]["replacement"]["prior_kernel_cost"]

    def gamma(k):
        ku = k * 2. ** -53
        return ku / (1. - ku)

    accumulation = gamma(8 * PREFIX + 64) * (
        left["absolute_summand_scales"]["cost"] + right["absolute_summand_scales"]["cost"]
    )
    combination = gamma(8) * math.fsum([abs(lf), abs(lr), abs(pf), abs(pr)])
    allowance = accumulation + combination
    difference = math.fsum([lf, pf, -lr, -pr])
    decision = (
        "accepted_feasible_point_improvement" if difference > allowance else
        "retained_worse_replacement" if difference < -allowance else
        "retained_unresolved_cost_difference"
    )
    expected = {
        "F_frozen": math.fsum([lf, pf]), "F_replacement": math.fsum([lr, pr]),
        "delta_frozen_minus_replacement": difference,
        "arithmetic_resolution_allowance": allowance,
        "computed_summand_accumulation_allowance": accumulation,
        "four_term_combination_allowance": combination, "decision": decision,
    }
    actual = closed["result"]["comparison"]
    require(all(actual[key] == value for key, value in expected.items()),
            "Frozen computed-objective comparison reconstruction failed")
    require(actual["truth_used"] is False and actual["MAP_or_optimum_claim"] is False and
            actual["voltage_threshold"] is None, "Unexpected comparison semantics")
    transaction = closed["result"]["transaction"]
    accepted = decision == "accepted_feasible_point_improvement"
    require(transaction["decision"] == decision and transaction["accepted"] is accepted and
            transaction["old_block_archived"] is accepted and
            transaction["prior_unchanged"] is True and transaction["cursor_unchanged"] is True and
            transaction["posterior_multiplied_into_replayed_evidence"] is False,
            "Transaction flags disagree with frozen decision/ownership")
    before, after = transaction["before"], transaction["after"]
    for row in (before, after):
        require(row["source_id"] == SOURCE_ID and row["observation_indices"] == [0, PREFIX] and
                row["cursor"] == PREFIX and row["prior_copies"] == 1 and
                row["active_likelihood_blocks"] == 1 and row["interval_convention"] == "half-open",
                "Likelihood/prior ownership or evidence cursor changed")
    require(before["prior"] == after["prior"] and before["generation"] == 0 and
            before["block"] == "old_anchor/stdout.json" and before["candidate"] == "frozen",
            "Invalid prior or old transaction state")
    require(after["generation"] == int(accepted) and
            after["block"] == ("replacement_anchor/stdout.json" if accepted else before["block"]) and
            after["candidate"] == ("replacement" if accepted else "frozen"),
            "Transaction did not atomically replace or retain the single block")
    return expected


def load_outer_closure(root: Path, attempt: Path, inner: dict, bindings: dict) -> dict:
    """Whole canonical process must have exited before reporting can see truth."""
    directory = below(root, "experiments/retained_likelihood_replacement_001/execution_process")
    receipt_path = below(directory, "receipt.json")
    outer = strict_json(receipt_path)
    require(outer["schema"] == "mumble_retained_replacement_outer_receipt_v1" and
            outer["status"] == "completed" and outer["canonical_process_finished"] is True and
            outer["canonical_supervisor_invocations"] == 1 and outer["retries"] == 0 and
            outer["errors"] == [], "Whole canonical process has no successful closed receipt")
    require(outer["truth_reads"] == outer["model_calls"] == outer["optimizer_calls"] == 0,
            "Outer observer performed forbidden inference or truth work")
    require(outer["source_revision"] == inner["result"]["source_revision"],
            "Outer and inner source revisions disagree")
    process = outer["process"]
    require(process["child_launched"] is True and process["exit_code"] == 0 and
            process["resource_violations"] == [] and process["output_truncated"] is False,
            "Whole canonical process failed or exceeded its resource limits")
    limits = inner["receipt"]["limits"]
    require(process["CPU_total_s"] <= limits["CPU_total_s_max"] and
            process["wall_s_through_wait4"] <= limits["wall_total_s_max"] and
            process["peak_RSS_bytes"] <= limits["child_RSS_bytes_max"] and
            outer["outer_own_peak_RSS_bytes"] <= limits["supervisor_RSS_bytes_max"],
            "Whole canonical process or outer observer exceeds a frozen limit")
    bind_file(attempt / "receipt.json", outer["inner_receipt"], bindings)
    bind_file(attempt / "result.json", outer["inner_result"], bindings)
    bind_file(directory / "stdout.json", outer["stdout"], bindings)
    bind_file(directory / "stderr.txt", outer["stderr"], bindings)
    bind_file(below(root, "tools/execute_retained_likelihood_replacement_once.py"), outer["source"], bindings)
    bindings[str(receipt_path)] = identity(receipt_path)
    started_path = directory / "started.json"
    started = strict_json(started_path)
    require(started["schema"] == "mumble_retained_replacement_outer_start_v1" and
            started["canonical_supervisor_invocations"] == 1 and started["retries"] == 0 and
            started["source"] == outer["source"] and started["command"] == process["command"],
            "Outer started/closed command or source identity mismatch")
    bindings[str(started_path)] = identity(started_path)
    actual_files = {str(path.relative_to(directory)) for path in directory.rglob("*") if path.is_file()}
    require(actual_files == {"started.json", "stdout.json", "stderr.txt", "receipt.json"},
            "Unexpected outer execution artifact set")
    root_stdout = strict_json(directory / "stdout.json")
    require(root_stdout["status"] == "completed" and root_stdout["errors"] == [] and
            root_stdout["counts"] == inner["result"]["counts"] and
            root_stdout["decision"] == inner["result"]["transaction"]["decision"],
            "Canonical supervisor stdout differs from its closed result")
    outer["closed_observer_output_bytes"] = sum((directory / path).stat().st_size for path in actual_files)
    require(outer["attempt_closed_bytes"] == inner["receipt"]["closed_output_bytes_including_receipt"] and
            outer["observer_closed_bytes_before_receipt"] ==
            outer["closed_observer_output_bytes"] - receipt_path.stat().st_size and
            outer["canonical_closed_output_bytes_including_outer_receipt"] ==
            outer["attempt_closed_bytes"] + outer["closed_observer_output_bytes"] and
            outer["canonical_closed_output_bytes_max"] == limits["closed_output_bytes_max"] == 2097152 and
            outer["canonical_closed_output_bytes_including_outer_receipt"] <=
            outer["canonical_closed_output_bytes_max"],
            "Combined attempt/outer closed-output accounting or cap failed")
    return outer


def endpoint_errors(point: dict, truth: dict) -> dict:
    q_error = point["endpoint_Q_Ah"] - truth["capacity_Ah"]
    soc_error = point["endpoint_SOC"] - truth["SOC"]
    return {"Q_error_Ah": q_error, "Q_error_percent": 100. * q_error / truth["capacity_Ah"],
            "SOC_error_fraction": soc_error, "SOC_error_percentage_points": 100. * soc_error,
            "scope": "One post-inference endpoint point-error comparison; no interval or coverage test"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--attempt-dir", type=Path, default=AREA / "attempt001")
    parser.add_argument("--truth-evidence-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=AREA)
    args = parser.parse_args()
    root, attempt, output = args.root.resolve(), args.attempt_dir.resolve(), args.output_dir.resolve()
    require(root.is_dir() and attempt.is_dir() and output.is_dir(), "Root, closed attempt and output directories must exist")
    require(not output.is_relative_to(attempt), "Reporting output must be outside the immutable attempt")
    names = ("summary.json", "reporting_receipt.json", "reporting_reservation.json")
    require(not any((output / name).exists() for name in names), "Reporting output already reserved; no overwrite or rerun")
    started = time.monotonic()
    source = Path(__file__).resolve()
    bindings = {str(source): identity(source)}
    activity = {
        "new_evaluator_invocations": 0, "new_battery_model_calls": 0, "new_optimizer_calls": 0,
        "new_learner_calls": 0, "new_source_generations": 0, "observation_numeric_decodes": 0,
        "post_inference_prior_algebra_evaluations": 0, "truth_records_decoded": 0,
    }
    write_new_json(output / "reporting_reservation.json", {
        "schema": SCHEMA, "command": [sys.executable, *sys.argv],
        "source": bindings[str(source)], "attempt": str(attempt),
        "purpose": "Read-only closed-result algebra and endpoint scoring; no inference retry.",
    })
    summary = None
    failure = None
    inference_closed = False
    try:
        closed = load_closed_attempt(root, attempt, bindings)
        outer = load_outer_closure(root, attempt, closed, bindings)
        inference_closed = True
        for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
            os.environ[key] = "1"
        import numpy as np
        pair = closed["pair"]
        require(np.__version__ == pair["policy"]["versions"]["numpy"], "Reporting NumPy differs from frozen solver policy")
        scales = vector(np, pair["policy"]["coordinate_SD"], DIM, "coordinate scales")
        require(bool(np.all(scales > 0.)) and
                bool(np.array_equal(scales, vector(np, pair["prior"]["public_unsplit_sd"], DIM, "public SD"))),
                "Common coordinate-scale mismatch")
        public = vector(np, pair["prior"]["public_unsplit_mean"], DIM, "public anchor")
        warm = vector(np, pair["frozen"]["warm_start_x"], DIM, "common warm")
        require(bool(np.array_equal(warm, vector(np, pair["replacement"]["warm_start_x"], DIM, "replacement warm"))),
                "The two solves did not share one warm start")
        validate_evaluator(np, closed["old_anchor"], public)
        validate_evaluator(np, closed["replacement_anchor"], warm)
        pass_names = ("old_anchor", "replacement_anchor", "frozen_audit", "replacement_audit")
        charge_time = {key: closed["old_anchor"][key] for key in
                       ("charge_Ah", "charge_min_Ah", "charge_max_Ah", "elapsed_physical_s")}
        require(all(all(closed[name][key] == value for key, value in charge_time.items())
                    for name in pass_names), "Evaluator passes have different input charge/time integrals")
        require(all(closed["input_summary"][key] == value for key, value in charge_time.items()) and
                closed["input_summary"]["prefix_records"] == PREFIX and
                closed["input_summary"]["prefix_bytes"] == 32 * PREFIX and
                closed["input_summary"]["prefix_sha256"] ==
                "a2219e78d29ddab4cfd1e02a7b6b520dc74fc0229e995b1aba0044bb240b269d",
                "Input-only prefix identity/integrals disagree")
        require(closed["anchors"]["old"]["x"] == public.tolist() and
                closed["anchors"]["replacement"]["x"] == warm.tolist() and
                closed["anchors"]["common_warm_start_x"] == warm.tolist() and
                closed["anchors"]["truth_used"] is False, "Anchor and common warm-start identity mismatch")
        arms = {}
        for label, anchor in (("frozen", "old_anchor"), ("replacement", "replacement_anchor")):
            activity["post_inference_prior_algebra_evaluations"] += 1
            arms[label] = summarize_arm(np, label, pair[label], closed[anchor],
                                        closed[f"{label}_audit"], pair["prior"], scales)
        require(activity["post_inference_prior_algebra_evaluations"] == 2, "Post-inference prior evaluation budget mismatch")
        reconstructed_comparison = validate_comparison_and_transaction(closed)
        difference = reconstructed_comparison["delta_frozen_minus_replacement"]
        summary = {
            "schema": SCHEMA, "status": "completed",
            "source_revision": closed["result"]["source_revision"],
            "plan_sha256": closed["result"]["plan_sha256"],
            "source_id": SOURCE_ID, "prefix_records": PREFIX, "charge_and_time": charge_time,
            "arms": arms, "transaction": closed["result"]["transaction"],
            "frozen_comparison": closed["result"]["comparison"],
            "comparison_independently_reconstructed": reconstructed_comparison,
            "computed_frozen_minus_replacement_common_objective": difference,
            "solver_pair_status": pair["status"], "solver_policy": pair["policy"],
            "prior": pair["prior"],
            "execution": {"counts": closed["receipt"]["counts"],
                          "resources": {
                              "whole_canonical_CPU_s": outer["process"]["CPU_total_s"],
                              "whole_canonical_wall_s_through_wait4": outer["process"]["wall_s_through_wait4"],
                              "whole_canonical_wait4_peak_RSS_bytes": outer["process"]["peak_RSS_bytes"],
                              "outer_observer_peak_RSS_bytes": outer["outer_own_peak_RSS_bytes"],
                              "maximum_exact_inference_child_peak_RSS_bytes": closed["receipt"]["resources"]["maximum_exact_child_peak_RSS_bytes"],
                              "inner_supervisor_peak_RSS_bytes": closed["receipt"]["resources"]["supervisor_peak_RSS_bytes"],
                              "whole_canonical_process_wait4": outer["process"],
                              "inner_pre_close_snapshot": closed["receipt"]["resources"],
                              "outer_scope": outer["scope"],
                              "RSS_interpretation": "Wait4 reports a high-water statistic; this is not a sum of concurrent process-tree memory.",
                              "closed_inference_attempt_bytes": closed["receipt"]["closed_output_bytes_including_receipt"],
                              "closed_outer_observer_output_bytes": outer["closed_observer_output_bytes"],
                              "combined_canonical_closed_output_bytes": outer["canonical_closed_output_bytes_including_outer_receipt"],
                              "combined_canonical_closed_output_bytes_max": outer["canonical_closed_output_bytes_max"],
                          },
                          "whole_canonical_process_finished": True,
                          "four_completed_model_passes": True,
                          "model_steps_from_raw_evaluators": sum(closed[name]["model_step_calls"] for name in pass_names),
                          "solver_calls_entered": closed["worker_result"]["counts"]["solver_calls_entered"]},
            "evidence_ownership": pair["evidence_ownership"],
            "local_shape_policy": SHAPE_LIMITATIONS,
            "coverage_validated": False, "candidate_promoted": False,
        }
        # This is the first access to the truth member in this program.
        truth, truth_binding = read_verified_endpoint_truth(root, args.truth_evidence_root.resolve(), inference_closed)
        activity["truth_records_decoded"] = truth["decoded_records"]
        bindings[truth_binding["path"]] = truth_binding
        restoration = below(root, RESTORATION_MEMBER)
        bindings[str(restoration)] = identity(restoration)
        summary["truth"] = truth
        for arm in arms.values():
            arm["endpoint_point_errors"] = endpoint_errors(arm, truth)
        after = {path: identity(Path(path)) for path in bindings}
        require(after == bindings, "A bound source, evidence or truth member changed during reporting")
        summary["reporting_activity"] = dict(activity)
        summary["inputs_unchanged"] = True
        summary["reporting_source"] = bindings[str(source)]
        write_new_json(output / "summary.json", summary)
    except Exception as error:
        failure = {"type": type(error).__name__, "message": str(error)}
    after = {path: identity(Path(path)) if Path(path).is_file() else None for path in bindings}
    if after != bindings and failure is None:
        failure = {"type": "InputMutation", "message": "A bound input changed before final reporting receipt closure"}
    receipt = {
        "schema": SCHEMA, "status": "completed" if failure is None else "failed",
        "exception": failure, "attempt": str(attempt),
        "canonical_inference_closed_before_reporting": inference_closed,
        "activity": activity, "before": bindings, "after": after,
        "all_bound_inputs_unchanged": after == bindings,
        "source": identity(source),
        "resources": {"wall_s_before_final_receipt": time.monotonic() - started,
                      "supervisor_own_peak_RSS_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
                      "resource_scope": "Read-only reporting process; no inference resource attribution"},
        "summary": identity(output / "summary.json") if (output / "summary.json").exists() else None,
        "limitations": SHAPE_LIMITATIONS,
    }
    write_new_json(output / "reporting_receipt.json", receipt)
    print(json.dumps({"status": receipt["status"], "summary": receipt["summary"], "exception": failure,
                      "new_model_or_optimizer_calls": 0}, allow_nan=False))
    return 0 if failure is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
