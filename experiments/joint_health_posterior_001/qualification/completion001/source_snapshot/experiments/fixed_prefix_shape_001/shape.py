#!/usr/bin/env python3
"""Host-only fixed-prefix geometry and analysis. No estimator or model execution.

The CLI requires a separately qualified commit-only capture and binds its saved
pointer-free bank checkpoint. A point vector plus scalar cost is not a capture.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

DIM = 16
PREFIX = 252_000
NODE_COUNT = 545
BASE = "af4524c40b33cb80de230a4afc8878793a9f1860"
OBS_SHA = "cdbf064028753eb1abf6f33ba2512853ecb58e21493791a269a4b5956545849f"
TRACE_SHA = "b2f9194092392f9001d1cef417db881c1d9b8ff9759ee6731d78a08600b1f46c"
PRIOR_SHA = "500e9f20893d66570607d268cb1e5e6eccf37c8078127ff345cbcce92a73c2a9"
BUDGET_NLL = 0.1
MAX_HALVINGS = 16
WHITENING_TOL = 1e-6
U = np.finfo(np.float64).eps / 2


class ContractError(ValueError):
    """A missing/invalid prerequisite; never an automatic retry request."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def array(value: Any, shape: tuple[int, ...], name: str) -> np.ndarray:
    a = np.asarray(value, dtype=np.float64)
    require(a.shape == shape, f"{name}: expected shape {shape}, got {a.shape}")
    require(bool(np.isfinite(a).all()), f"{name}: nonfinite value")
    return a


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load(path: Path) -> dict[str, Any]:
    def reject(value: str) -> None:
        raise ContractError(f"nonstandard JSON constant: {value}")
    value = json.loads(path.read_text(), parse_constant=reject)
    require(isinstance(value, dict), "JSON document must be an object")
    return value


def save_new(path: Path, value: dict[str, Any]) -> None:
    # Serialize before opening, so a serialization failure cannot truncate a file.
    data = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    with path.open("x", encoding="utf-8") as f:
        f.write(data)


def unpack_metric(packed: Any) -> np.ndarray:
    p = array(packed, (136,), "packed metric")
    m = np.zeros((DIM, DIM))
    k = 0
    for i in range(DIM):
        for j in range(i + 1):
            m[i, j] = m[j, i] = p[k]
            k += 1
    return m


def directions() -> list[tuple[str, int, int | None, np.ndarray]]:
    eye = np.eye(DIM)
    result = [(f"axis_{i:02d}", i, None, eye[i]) for i in range(DIM)]
    for i in range(DIM):
        for j in range(i + 1, DIM):
            result.append((f"pair_{i:02d}_{j:02d}", i, j,
                           (eye[i] + eye[j]) / math.sqrt(2.0)))
    return result


def common_support(x: np.ndarray, lower: np.ndarray, upper: np.ndarray,
                   cmin: float, cmax: float) -> bool:
    if not np.isfinite(x).all() or np.any(x < lower) or np.any(x > upper):
        return False
    with np.errstate(over="ignore", under="ignore", invalid="ignore", divide="ignore"):
        q = np.exp(x[:, 5])
        zlo = x[:, 11] - cmax / q
        zhi = x[:, 11] - cmin / q
    return bool(np.all(np.isfinite(q) & (q > 0) & np.isfinite(zlo) &
                       np.isfinite(zhi) & (zlo >= 0) & (zhi <= 1)))


def make_design(anchor: Any, metric: Any, public_sd: Any, lower: Any, upper: Any,
                charge_min: float, charge_max: float, charge: float) -> dict[str, Any]:
    """Freeze a complete mixed-direction stencil using represented geometry only.

    G is the existing GN-plus-prior-kernel metric, NOT a posterior covariance or
    the exact mixture Hessian. Whitening merely chooses coupled test locations.
    The support-only halving schedule is fixed here, before reference queries.
    """
    x0 = array(anchor, (DIM,), "anchor")
    g = array(metric, (DIM, DIM), "metric")
    sd = array(public_sd, (DIM,), "public_sd")
    lo, hi = array(lower, (DIM,), "lower"), array(upper, (DIM,), "upper")
    require(bool(np.array_equal(g, g.T)), "metric is not exactly symmetric")
    require(bool(np.all(sd > 0) and np.all(lo < hi)), "invalid scales or bounds")
    require(all(math.isfinite(c) for c in (charge_min, charge_max, charge)), "nonfinite charge")
    require(charge_min <= min(0.0, charge) and charge_max >= max(0.0, charge),
            "charge extrema do not include initial and endpoint charge")
    require(common_support(x0[None, :], lo, hi, charge_min, charge_max),
            "anchor is outside common entering-box/SOC support")
    scaled = g * np.outer(sd, sd)
    require(bool(np.isfinite(scaled).all()), "scaled metric overflow")
    try:
        chol = np.linalg.cholesky(scaled)
        b = np.linalg.solve(chol.T, np.eye(DIM))
    except np.linalg.LinAlgError as exc:
        raise ContractError("metric factorization failed; no jitter or eigenvalue clipping") from exc
    require(bool(np.isfinite(b).all()), "nonfinite whitening basis")
    residual = float(np.linalg.norm(b.T @ scaled @ b - np.eye(DIM), ord=np.inf))
    require(math.isfinite(residual) and residual <= WHITENING_TOL,
            "whitening resolution unresolved; do not repair the metric")
    basis = sd[:, None] * b
    dirs = directions()
    chosen = None
    for halvings in range(MAX_HALVINGS + 1):
        radius = math.ldexp(1.0, -halvings)
        nodes = [{"id": "anchor", "level": -1, "direction": None,
                  "sign": 0, "x": x0.tolist()}]
        for level, h in enumerate((radius, radius / 2)):
            for label, i, j, vector in dirs:
                for sign in (-1, 1):
                    x = x0 + sign * h * (basis @ vector)
                    nodes.append({"id": f"r{level}_{label}_{'p' if sign > 0 else 'm'}",
                                  "level": level, "direction": label,
                                  "i": i, "j": j, "sign": sign, "x": x.tolist()})
        xx = np.asarray([n["x"] for n in nodes])
        if common_support(xx, lo, hi, charge_min, charge_max):
            chosen = (halvings, radius, nodes, xx)
            break
    require(chosen is not None, "symmetric stencil not supported after fixed 16 halvings")
    halvings, radius, nodes, xx = chosen
    require(len(nodes) == NODE_COUNT, "internal stencil count mismatch")
    require(np.unique(xx, axis=0).shape[0] == NODE_COUNT,
            "represented points collide at binary64 resolution")
    q0 = math.exp(float(x0[5]))
    soc0 = float(x0[11]) - charge / q0
    for node in nodes:
        q = math.exp(node["x"][5])
        node["Q_relative_anchor_percent"] = 100 * math.expm1(node["x"][5] - float(x0[5]))
        node["current_SOC_relative_anchor_pp"] = 100 * (node["x"][11] - charge / q - soc0)
    return {"schema": "mumble_fixed_prefix_nodes_v1", "prefix": PREFIX,
            "base_revision": BASE, "node_count": NODE_COUNT,
            "dimension": DIM, "nodes": nodes, "radii": [radius, radius / 2],
            "support_only_halvings": halvings, "whitening_residual_inf": residual,
            "basis_original_x_units": basis.tolist(), "anchor": x0.tolist(),
            "metric_role": "node_design_only_GN_plus_kernel_precision_not_covariance",
            "common_support": "original_entering_box_and_all_prefix_SOC_charge_extrema",
            "support_checks_exclude": "approximate_boundary_endpoint_and_model_numerics",
            "truth_used": False, "reference_queries_before_freeze": 0,
            "budget_NLL": BUDGET_NLL}


def validate_capture(capture: dict[str, Any], snapshot: Path) -> None:
    require(capture.get("schema") == "mumble_fixed_prefix_capture_v1", "capture schema")
    require(capture.get("prefix") == PREFIX and capture.get("base_revision") == BASE,
            "capture prefix/source mismatch")
    require(capture.get("observations_sha256") == OBS_SHA, "observation identity mismatch")
    require(capture.get("trace_sha256") == TRACE_SHA, "original trace identity mismatch")
    r = capture.get("reconstruction", {})
    for key, expected in {"method": "commit_only", "optimizer_calls": 0,
                          "truth_reads": 0, "records": PREFIX, "blocks": PREFIX // 16,
                          "checked_snapshots": PREFIX // 16 + 1,
                          "parity": "bitwise"}.items():
        require(r.get(key) == expected, f"reconstruction prerequisite: {key}")
    require(capture.get("snapshot_scope") == "pointer_free_host_ABI_bank_inputs_calibration",
            "snapshot must exclude live pointer/workspace unions")
    require(snapshot.is_file() and snapshot.stat().st_size > 0, "saved bank snapshot missing")
    require(snapshot.stat().st_size == capture.get("snapshot_bytes"), "snapshot size mismatch")
    require(file_sha(snapshot) == capture.get("snapshot_sha256"), "snapshot hash mismatch")


def finite_difference_matrices(design: dict[str, Any], delta: np.ndarray) -> list[dict[str, Any]]:
    result = []
    by = {n["id"]: k for k, n in enumerate(design["nodes"])}
    for level, h in enumerate(design["radii"]):
        gradient = np.zeros(DIM)
        hessian = np.zeros((DIM, DIM))
        curvatures = {}
        for label, i, j, _ in directions():
            minus = delta[by[f"r{level}_{label}_m"]]
            plus = delta[by[f"r{level}_{label}_p"]]
            require(math.isfinite(float(plus)) and math.isfinite(float(minus)),
                    "finite differences require every stencil value")
            curvatures[label] = (plus + minus) / (h * h)
            if j is None:
                gradient[i] = (plus - minus) / (2 * h)
                hessian[i, i] = curvatures[label]
        for label, i, j, _ in directions():
            if j is not None:
                hessian[i, j] = hessian[j, i] = curvatures[label] - 0.5 * (hessian[i, i] + hessian[j, j])
        result.append({"radius": h, "gradient_whitened": gradient.tolist(),
                       "symmetric_second_difference_matrix_whitened": hessian.tolist(),
                       "scope": "finite_stencil_estimate_not_exact_Hessian_or_covariance"})
    return result


def compare(design: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare centered NLL contrasts with supplied computed-cost allowances.

    Allowances must be registered by the evaluator; they do not cover physical
    model error, libm recurrence error, tails, normalization, or coverage.
    """
    require(design.get("schema") == "mumble_fixed_prefix_nodes_v1", "design schema")
    require(design.get("prefix") == PREFIX and design.get("node_count") == NODE_COUNT,
            "design prefix/count mismatch")
    require(len(rows) == NODE_COUNT and len(design["nodes"]) == NODE_COUNT,
            "all nodes must have a row, including explicit unavailable rows")
    rep = np.full(NODE_COUNT, np.nan)
    ref = np.full(NODE_COUNT, np.nan)
    ra, ea = np.zeros(NODE_COUNT), np.zeros(NODE_COUNT)
    valid = np.zeros(NODE_COUNT, dtype=bool)
    for k, (node, row) in enumerate(zip(design["nodes"], rows, strict=True)):
        require(row.get("id") == node["id"], "node ordering/identity mismatch")
        require(bool(np.array_equal(array(row.get("x"), (DIM,), "evaluated point"), node["x"])),
                "evaluated point differs from frozen node")
        status = row.get("status")
        require(status in ("available", "unavailable"), "missing explicit evaluation status")
        if status == "unavailable":
            require(isinstance(row.get("reason"), str) and bool(row["reason"]),
                    "unavailable row needs a reason")
            continue
        values = [row.get(key) for key in ("represented_likelihood_cost", "reference_likelihood_cost",
                  "represented_cost_allowance", "reference_cost_allowance")]
        v = array(values, (4,), "costs/allowances")
        require(bool(np.all(v >= 0)), "Gaussian likelihood costs and absolute allowances must be nonnegative")
        rep[k], ref[k], ra[k], ea[k] = v
        valid[k] = True
    require(bool(valid[0]), "anchor comparison is unavailable")
    dr, de = rep - rep[0], ref - ref[0]
    error = dr - de
    # Four differences, with a conservative six-operation gamma bound on
    # original cost magnitudes. Center is the same stored value, so exactly 0.
    gamma = 6 * U / (1 - 6 * U)
    with np.errstate(over="ignore", invalid="ignore"):
        allowance = ra + ra[0] + ea + ea[0] + gamma * (np.abs(rep) + abs(rep[0]) + np.abs(ref) + abs(ref[0]))
    dr[0] = de[0] = error[0] = allowance[0] = 0.0
    require(bool(np.isfinite(error[valid]).all() and np.isfinite(allowance[valid]).all()),
            "contrast/allowance overflow")
    lower, upper = error[valid] - allowance[valid], error[valid] + allowance[valid]
    oscillation = float(np.ptp(error[valid]))
    osc_lower = max(0.0, float(np.max(lower) - np.min(upper)))
    osc_upper = float(np.max(upper) - np.min(lower))
    complete = bool(valid.all())
    if osc_lower > BUDGET_NLL:
        decision = "repair_computed_shape_witness"
    elif complete and osc_upper <= BUDGET_NLL:
        decision = "keep_on_tested_points_only"
    else:
        decision = "unresolved"
    per_node = []
    for k, n in enumerate(design["nodes"]):
        per_node.append({"id": n["id"], "status": rows[k]["status"],
                         "centered_discrepancy_NLL": float(error[k]) if valid[k] else None,
                         "computed_arithmetic_allowance_NLL": float(allowance[k]) if valid[k] else None})
    result = {"schema": "mumble_fixed_prefix_analysis_v1", "prefix": PREFIX,
              "decision": decision, "complete_stencil": complete,
              "available_nodes": int(valid.sum()), "budget_NLL": BUDGET_NLL,
              "centered_error_oscillation_NLL": oscillation,
              "oscillation_computed_arithmetic_interval_NLL": [osc_lower, osc_upper],
              "anchor_represented_minus_reference_NLL": float(rep[0] - ref[0]),
              "per_node": per_node,
              "scope": "computed finite-node likelihood contrasts only; not continuous posterior/coverage",
              "no_claims": ["all_parameter_convergence", "exact_Hessian", "calibrated_intervals",
                            "global_or_tail_fidelity", "Cortex_M23_qualification"],
              "arithmetic_excludes": ["recurrence_and_libm_forward_error", "physical_model_error"],
              "common_prior": "identical original supported prior cancels from contrast discrepancy"}
    if complete:
        result["represented_second_differences"] = finite_difference_matrices(design, dr)
        result["reference_second_differences"] = finite_difference_matrices(design, de)
        result["discrepancy_second_differences"] = finite_difference_matrices(design, error)
    return result


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    d = sub.add_parser("design", help="freeze nodes after a qualified capture")
    d.add_argument("--capture", type=Path, required=True)
    d.add_argument("--snapshot", type=Path, required=True)
    d.add_argument("--output", type=Path, required=True)
    a = sub.add_parser("analyze", help="analyze one separately closed evaluation result")
    a.add_argument("--design", type=Path, required=True)
    a.add_argument("--evaluations", type=Path, required=True)
    a.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    try:
        if args.command == "design":
            c = load(args.capture)
            validate_capture(c, args.snapshot)
            out = make_design(c["anchor"], unpack_metric(c["metric_packed_lower"]),
                              c["public_sd"], c["lower"], c["upper"],
                              c["charge_min_Ah"], c["charge_max_Ah"], c["charge_Ah"])
            out["capture_sha256"] = file_sha(args.capture)
            out["snapshot_sha256"] = file_sha(args.snapshot)
            out["common_prior_source_sha256"] = PRIOR_SHA
        else:
            design, ev = load(args.design), load(args.evaluations)
            require(ev.get("schema") == "mumble_fixed_prefix_evaluations_v1", "evaluation schema")
            require(ev.get("design_sha256") == file_sha(args.design), "frozen design hash mismatch")
            require(ev.get("prefix") == PREFIX, "evaluation prefix mismatch")
            require(ev.get("common_prior_source_sha256") == PRIOR_SHA, "common prior source mismatch")
            require(ev.get("observations_sha256") == OBS_SHA, "evaluation input identity mismatch")
            require(ev.get("snapshot_sha256") == design.get("snapshot_sha256"), "evaluated bank identity mismatch")
            require(ev.get("closed") is True, "evaluation process not closed")
            out = compare(design, ev["rows"])
            out["design_sha256"] = file_sha(args.design)
            out["evaluations_sha256"] = file_sha(args.evaluations)
        save_new(args.output, out)
    except (ContractError, KeyError, OSError, ValueError, TypeError) as exc:
        p.exit(2, f"UNRESOLVED: {exc}\n")


if __name__ == "__main__":
    main()
