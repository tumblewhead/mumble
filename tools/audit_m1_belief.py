#!/usr/bin/env python3
"""Supplement the completed M1 run with full-vector errors and product tiers.

No optimizer, inference replay, parameter correction, or frozen-file rewrite.
Truth is loaded only after the primary receipt confirms inference completion.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POSITIVE_NAMES = ["R0", "R1", "R2", "R3", "tau1", "tau2", "tau3",
                  "H", "gamma_plus", "gamma_minus", "Q_Ah"]
PHYSICAL_NAMES = POSITIVE_NAMES + ["z0", "v10", "v20", "v30", "h0"]
CHART_NAMES = ["log_tau1", "log_tau2", "log_tau3", "log_gamma_plus",
               "log_gamma_minus", "z0", "log_Q_Ah", "R0", "R1", "R2",
               "R3", "H", "v10", "v20", "v30", "u0=H*h0"]
LIMITS = {"hard": {"capacity_percent": 5.0, "SOC_pp": 10.0},
          "preferred": {"capacity_percent": 0.5, "SOC_pp": 0.5}}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def physical_values(p: dict) -> dict:
    result = {k: p[k] for k in ("R0", "H", "gamma_plus", "gamma_minus", "Q_Ah", "z0", "h0")}
    for i in range(3):
        result[f"R{i+1}"] = p["R"][i]
        result[f"tau{i+1}"] = p["tau"][i]
        result[f"v{i+1}0"] = p["v0"][i]
    return result


def tier(soc_error_pp: float | None, capacity_error_percent: float | None) -> str:
    if soc_error_pp is None or capacity_error_percent is None:
        return "unknown"
    for key, bounds in (("preferred", LIMITS["preferred"]), ("hard", LIMITS["hard"])):
        if abs(soc_error_pp) <= bounds["SOC_pp"] and abs(capacity_error_percent) <= bounds["capacity_percent"]:
            return "within_" + key
    return "over_hard"


def progress_summary(points: list[dict], category: str) -> dict:
    allowed = {"within_preferred"} if category == "preferred" else {"within_preferred", "within_hard"}
    good = [p["tier"] in allowed for p in points]
    first = next((p["time_s"] for p, ok in zip(points, good) if ok), None)
    sustained = None
    for point, ok in reversed(list(zip(points, good))):
        if not ok:
            break
        sustained = point["time_s"]
    return {"first_s": first, "sustained_from_s": sustained, "queries_within": sum(good)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary", type=Path, default=ROOT / "experiments/trajectory_integration_001/primary")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "experiments/m1_belief_audit_001")
    args = parser.parse_args()
    primary, output = args.primary.resolve(), args.output_dir.resolve()
    if output.exists():
        parser.error("Supplement output already exists; preserve it and choose another destination")
    receipt_path = primary / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    if not receipt.get("inference_completed") or not receipt.get("finished_utc"):
        parser.error("All M1 inference must finish before this truth-bearing audit")

    # These are scoring/diagnostic functions only. No fitting module is called.
    import numpy as np
    from assess import assess_result as local_assessment
    from generate_cases import advance_truth, physical_to_vectors, vectors_to_physical

    manifest_path = ROOT / "data/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    truths = {r["case_id"]: r for r in manifest["cases"]}
    source_paths = [receipt_path, manifest_path, ROOT / "tools/generate_cases.py",
                    ROOT / "tools/assess.py", ROOT / "experiments/trajectory_integration_001/scores.json"]
    before = {str(p.relative_to(ROOT)): sha(p) for p in source_paths}
    checks, failures, records, cases, benchmark_rows = 0, [], [], [], []

    def check(condition: bool, label: str) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            failures.append(label)

    for case in receipt["cases"]:
        case_id = case["case_id"]
        truth_record = truths[case_id]
        csv = manifest_path.parent / truth_record["csv"]
        check(sha(csv) == case["data_sha256"] == truth_record["sha256"], case_id + ": input identity")
        before[str(csv.relative_to(ROOT))] = sha(csv)
        data = np.loadtxt(csv, delimiter=",", skiprows=1)
        dt, current = data[:, 1], data[:, 2]
        truth = truth_record["truth"]
        charge = np.cumsum(current * dt / 3600.0)
        time_s = np.cumsum(dt)
        true_soc = truth["z0"] - charge / truth["Q_Ah"]
        arms = {key: [] for key in ("control", "warm", "cold")}
        for process in case["processes"]:
            path = primary / process["stdout_jsonl"]
            before[str(path.relative_to(ROOT))] = sha(path)
            check(sha(path) == process["stdout_sha256"], case_id + ": raw output identity")
            arms[process["kind"]].extend(json.loads(line) for line in path.read_text().splitlines() if line)
        case_summary = {"case_id": case_id, "arms": {}, "fit_summaries": []}
        for arm, events in arms.items():
            queries = {e["next_index"]: e for e in events if e["event"] == "query"}
            points = []
            for n, query in sorted(queries.items()):
                state = query["state"]
                actual_soc = float(true_soc[n - 1]) if n else truth["z0"]
                soc_error = 100 * (state["current_soc"] - actual_soc) if state["point_available"] else None
                q_error = 100 * (state["capacity_Ah"] / truth["Q_Ah"] - 1) if state["capacity_available"] else None
                points.append({"next_index": n, "time_s": state["elapsed_s"], "SOC_error_pp": soc_error,
                    "capacity_error_percent": q_error, "tier": tier(soc_error, q_error),
                    "SOC_status": query["assessment"]["current_soc"]["status"] if query["assessment"] else "unknown",
                    "capacity_status": query["assessment"]["capacity_Ah"]["status"] if query["assessment"] else "unknown"})
            required = receipt["acceptance"]["usefulness"]["cold_recovery_checkpoints_samples" if arm == "cold"
                else "uninterrupted_and_warm_checkpoints_samples"]
            by_n = {p["next_index"]: p for p in points}
            for n in required:
                point = by_n[n]
                benchmark_rows.append({"case_id": case_id, "arm": arm, **point,
                    "SOC_within_hard": point["SOC_error_pp"] is not None and abs(point["SOC_error_pp"]) <= LIMITS["hard"]["SOC_pp"],
                    "capacity_within_hard": point["capacity_error_percent"] is not None and abs(point["capacity_error_percent"]) <= LIMITS["hard"]["capacity_percent"]})
            case_summary["arms"][arm] = {"query_count": len(points), "tier_counts": dict(Counter(p["tier"] for p in points)),
                "hard": progress_summary(points, "hard"), "preferred": progress_summary(points, "preferred"),
                "maximum_available_SOC_abs_error_pp": max((abs(p["SOC_error_pp"]) for p in points if p["SOC_error_pp"] is not None), default=None),
                "maximum_available_capacity_abs_error_percent": max((abs(p["capacity_error_percent"]) for p in points if p["capacity_error_percent"] is not None), default=None),
                "SOC_status_counts": dict(Counter(p["SOC_status"] for p in points)),
                "capacity_status_counts": dict(Counter(p["capacity_status"] for p in points))}
            if arm == "warm":
                continue
            for event in (e for e in events if e["event"] == "fit"):
                n, epoch_begin, fit = event["next_index"], event["epoch_begin"], event["fit"]
                check(fit is not None and event["returncode"] == 0, case_id + ": completed fit")
                if fit is None:
                    continue
                estimated = vectors_to_physical(fit["theta"], fit["alpha"])
                entering_truth = advance_truth(dt[:epoch_begin], current[:epoch_begin], truth)
                true_theta, true_alpha = physical_to_vectors(entering_truth)
                values = np.r_[fit["theta"], fit["alpha"]]
                actual = np.r_[true_theta, true_alpha]
                scales = np.asarray(fit["coordinate_scales"], float)
                scaled_error = (values - actual) / scales
                check(values.shape == actual.shape == scales.shape == (16,), case_id + ": vector dimensions")
                check(bool(np.all(np.isfinite(scaled_error)) and np.all(scales > 0)), case_id + ": finite scaled error")
                local = local_assessment(fit)
                query = queries[n]
                check(local["numerical_rank"] == query["assessment"]["numerical_rank"], case_id + ": local rank parity")
                check(local["parameters"]["current_soc"]["status"] == query["assessment"]["current_soc"]["status"], case_id + ": SOC qualification parity")
                check(local["parameters"]["Q_Ah"]["status"] == query["assessment"]["capacity_Ah"]["status"], case_id + ": capacity qualification parity")
                estimated_values, actual_values = physical_values(estimated), physical_values(entering_truth)
                physical = {}
                for key in PHYSICAL_NAMES:
                    estimate, target = estimated_values[key], actual_values[key]
                    diagnostic = local["parameters"][key]
                    if key in POSITIVE_NAMES:
                        error, units = 100 * (estimate / target - 1), "relative percent"
                    elif key == "z0":
                        error, units = 100 * (estimate - target), "percentage points"
                    elif key.startswith("v"):
                        error, units = 1000 * (estimate - target), "mV"
                    else:
                        error, units = estimate - target, "absolute dimensionless"
                        if diagnostic["point"] is None:
                            estimate, error = None, None
                    physical[key] = {"estimate": estimate, "truth": target, "signed_error": error,
                        "error_units": units, "status": diagnostic["status"],
                        "range_kind": diagnostic["range_kind"], "range": diagnostic["local_range"],
                        "range_units": diagnostic["units"], "null_projection": diagnostic["null_projection"]}
                estimated_now = advance_truth(dt[epoch_begin:n], current[epoch_begin:n], estimated)
                actual_now = advance_truth(dt[:n], current[:n], truth)
                current_errors = {"SOC_error_pp": 100 * (estimated_now["z0"] - actual_now["z0"]),
                    "RC_voltage_error_mV": [1000 * (a - b) for a, b in zip(estimated_now["v0"], actual_now["v0"])],
                    "hysteresis_state_error": estimated_now["h0"] - actual_now["h0"]}
                check(abs(current_errors["SOC_error_pp"] - by_n[n]["SOC_error_pp"]) < 1e-8,
                      case_id + ": independent current SOC parity")
                order = np.argsort(np.abs(scaled_error))[::-1]
                positive_order = sorted(POSITIVE_NAMES, key=lambda k: abs(physical[k]["signed_error"]), reverse=True)
                record = {"case_id": case_id, "arm": arm, "next_index": n, "epoch_begin": epoch_begin,
                    "time_s": float(time_s[n - 1]), "optimizer_status": fit["status"],
                    "termination_reason": fit["termination_reason"], "numerical_rank": local["numerical_rank"],
                    "physical_parameters_and_entering_states": physical,
                    "physical_status_counts": dict(Counter(v["status"] for v in physical.values())),
                    "current_state_errors": current_errors,
                    "coordinate_scaled_error": {"names": CHART_NAMES, "scales": scales.tolist(),
                        "signed_components": scaled_error.tolist(), "RMS": float(np.sqrt(np.mean(scaled_error ** 2))),
                        "L2_norm": float(np.linalg.norm(scaled_error)), "max_abs": float(np.max(np.abs(scaled_error))),
                        "largest_components": [{"name": CHART_NAMES[i], "signed_scaled_error": float(scaled_error[i])} for i in order[:3]]},
                    "largest_positive_parameter_errors": [{"name": key, "relative_error_percent": physical[key]["signed_error"]} for key in positive_order[:3]],
                    "product_tier_at_fit": by_n[n]["tier"]}
                records.append(record)
                case_summary["fit_summaries"].append({k: record[k] for k in
                    ("arm", "next_index", "time_s", "optimizer_status", "numerical_rank", "physical_status_counts",
                     "current_state_errors", "largest_positive_parameter_errors", "product_tier_at_fit")})
                case_summary["fit_summaries"][-1]["coordinate_scaled_RMS"] = record["coordinate_scaled_error"]["RMS"]
                case_summary["fit_summaries"][-1]["coordinate_scaled_max_abs"] = record["coordinate_scaled_error"]["max_abs"]
        cases.append(case_summary)

    for name, digest in before.items():
        check(sha(ROOT / name) == digest, "frozen input unchanged: " + name)
    summary = {
        "schema": "mumble_m1_belief_audit_v1", "created_utc": datetime.now(timezone.utc).isoformat(),
        "primary_source_revision": receipt["source_revision"], "published_M1_revision": "8acc87b1e8eb1b92acd7f0f9c1b643d1cfb79658",
        "inference_completed_utc": receipt["finished_utc"], "new_optimizer_calls": 0, "primary_reruns": 0,
        "original_M1_usefulness_passed": False, "frozen_M1_result_unchanged": True,
        "product_thresholds": LIMITS,
        "threshold_semantics": "User-supplied point-error requirements. SOC percent means absolute percentage points of SOC. Hard limits use <=; preferred thresholds mark diminishing returns. These are acceptance requirements, not estimator-certified error bounds or coverage.",
        "physical_vector": {"names": PHYSICAL_NAMES, "dimension": 16,
            "scope": "11 static parameters plus entering SOC, three entering RC voltages and entering hysteresis state for the fitted epoch. Current hidden-state errors are separately reconstructed at each endpoint.",
            "error_units": "Positive parameters: relative percent; z0: percentage points; entering RC voltages: mV; h0: absolute dimensionless. No raw mixed-unit total is reported."},
        "aggregate_definition": {"chart": CHART_NAMES, "formula": "e_i=(estimated_x_i-truth_x_i)/fit.coordinate_scales_i; RMS=sqrt(sum(e_i^2)/16); L2=sqrt(sum(e_i^2)); max=max(abs(e_i))",
            "scope": "Dimensionless error under the reference's declared engineering coordinate scales. Log coordinates for tau/gamma/Q; z0 linear; alpha contains R/H/entering voltages/u0=H*h0. This score is scale-dependent, not a percentage, posterior distance or coverage statistic.",
            "uncertainty": "Existing offline local assessor recomputed from the frozen joint Gram, without truth. Original diagnostic precision thresholds remain unchanged. Numerical rank and provisional ranges are not global identifiability or validated coverage."},
        "cases": cases, "revised_declared_benchmarks": benchmark_rows,
        "revised_benchmark_totals": {"count": len(benchmark_rows),
            "SOC_within_hard": sum(r["SOC_within_hard"] for r in benchmark_rows),
            "capacity_within_hard": sum(r["capacity_within_hard"] for r in benchmark_rows),
            "both_within_hard": sum(r["tier"] in ("within_hard", "within_preferred") for r in benchmark_rows),
            "both_within_preferred": sum(r["tier"] == "within_preferred" for r in benchmark_rows)},
        "query_scope": "Sparse saved nominal10-second queries plus lifecycle events, deduplicated by sample position. First/sustained times and maxima are sampled metrics, not all-sample bounds.",
        "validation": {"checks": checks, "failures": failures, "passed": not failures},
        "input_sha256": before, "script_sha256": sha(Path(__file__)),
        "records": "experiments/m1_belief_audit_001/records.json",
    }
    output.mkdir(parents=True)
    (output / "records.json").write_text(json.dumps(records, indent=2, allow_nan=False) + "\n")
    summary["records_sha256"] = sha(output / "records.json")
    (output / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"passed": not failures, "checks": checks, "failures": failures,
        "fit_records": len(records), "new_optimizer_calls": 0,
        "revised_benchmark_totals": summary["revised_benchmark_totals"]}))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
