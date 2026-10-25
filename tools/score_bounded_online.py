#!/usr/bin/env python3
"""Post-inference scoring for the frozen bounded online candidate.

No estimator or optimizer is invoked. Truth is loaded only after the complete
primary receipt is closed. Initial/current state coordinates are kept distinct.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAMES = ["log_tau1", "log_tau2", "log_tau3", "log_gamma_plus", "log_gamma_minus",
         "log_Q_Ah", "R0", "R1", "R2", "R3", "H", "current_z",
         "current_v1", "current_v2", "current_v3", "current_h"]
SCALES = [1.] * 6 + [.2] * 4 + [.03, .1, .03, .03, .03, 1.]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def status_name(value: object) -> str:
    return {0: "unknown", 1: "unexcited", 2: "unresolved", 3: "provisional"}.get(value, str(value))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--figure", type=Path, required=True)
    args = parser.parse_args()
    primary, output, figure = (p.resolve() for p in (args.primary, args.output, args.figure))
    if output.exists() or figure.exists() or figure.with_suffix(".svg").exists():
        parser.error("Preserve existing results; choose a new output")
    receipt_path = primary / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    if not receipt.get("inference_completed") or not receipt.get("finished_utc"):
        parser.error("All inference must finish before truth scoring")

    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from generate_cases import advance_truth
    from validate import json_safe

    manifest_path = ROOT / "data/manifest.json"
    truth_cases = {c["case_id"]: c for c in json.loads(manifest_path.read_text())["cases"]}
    plan_path = ROOT / "experiments/bounded_online_001/plan.json"
    plan = json.loads(plan_path.read_text())
    gates = plan["acceptance"]["point_accuracy"]
    hard_soc, hard_q = gates["hard_current_SOC_abs_error_pp_le"], gates["hard_capacity_abs_relative_percent_le"]
    pref_soc, pref_q = gates["preferred_current_SOC_pp_le"], gates["preferred_capacity_percent_le"]
    result = {"schema": "mumble_bounded_online_scores_v1", "source_revision": receipt["source_revision"],
        "scoring_started_utc": datetime.now(timezone.utc).isoformat(), "inference_finished_utc": receipt["finished_utc"],
        "primary_receipt_sha256": sha(receipt_path), "plan_sha256": sha(plan_path),
        "scorer_sha256": sha(Path(__file__)), "dependencies_sha256": {name: sha(ROOT / name) for name in
            ("tools/generate_cases.py", "tools/validate.py", "data/manifest.json", "plans/estimation_targets_001.json")},
        "functional_passed": receipt["functional_passed"], "thresholds": gates,
        "metric_semantics": {"SOC": "absolute percentage-point error", "capacity": "absolute relative percent error",
            "scaled_current_vector_RMS": "RMS of16 coordinate errors divided by declared engineering scales; not percent or posterior distance.",
            "coordinates": NAMES, "scales": SCALES,
            "uncertainty": "Prior-conditioned local Gaussian approximation; interval hits/misses here do not establish coverage.",
            "query_scope": "Deduplicated saved queries at nominal10s plus lifecycle events, not every intervening sample."},
        "cases": [], "raw_sha256": {}, "new_optimizer_calls": 0}
    fig, axes = plt.subplots(3, 2, figsize=(13, 10.5), sharex=True, constrained_layout=True)
    colors = {"control": "#17639b", "warm": "#42a58a", "cold": "#cb6231"}
    failures = []
    for column, case in enumerate(receipt["cases"]):
        case_id = case["case_id"]
        truth_record = truth_cases[case_id]
        data_path = manifest_path.parent / truth_record["csv"]
        if sha(data_path) != truth_record["sha256"]:
            raise ValueError("Input changed: " + case_id)
        data = np.loadtxt(data_path, delimiter=",", skiprows=1)
        dt, current = data[:, 1], data[:, 2]
        physical_time = np.cumsum(dt)
        truth = truth_record["truth"]
        arms = {name: [] for name in ("control", "warm", "cold")}
        for process in case["processes"]:
            path = primary / process["stdout_jsonl"]
            if sha(path) != process["stdout_sha256"]:
                raise ValueError("Raw output changed: " + path.name)
            result["raw_sha256"][process["stdout_jsonl"]] = sha(path)
            arms[process["kind"]].extend(json.loads(line) for line in path.read_text().splitlines() if line)
        truth_at = {}
        scored_case = {"case_id": case_id, "functional_passed": case["functional_passed"],
            "arms": {}, "benchmarks": [], "selected_full_vectors": []}
        for arm, records in arms.items():
            queries = {r["next_index"]: r for r in records if r["event"] == "query"}
            trajectory = []
            for n, record in sorted(queries.items()):
                state = record["state"]
                if n not in truth_at:
                    truth_at[n] = advance_truth(dt[:n], current[:n], truth)
                t = truth_at[n]
                x = np.asarray(state["mean"], float)
                true_x = np.r_[np.log(t["tau"]), np.log([t["gamma_plus"], t["gamma_minus"], t["Q_Ah"]]),
                               t["R0"], t["R"], t["H"], t["z0"], t["v0"], t["h0"]]
                soc_error = float(100 * (state["current_soc"] - t["z0"])) if state["point_available"] else None
                q_error = float(100 * (state["capacity_Ah"] / t["Q_Ah"] - 1)) if state["capacity_available"] else None
                soc_hard = soc_error is not None and abs(soc_error) <= hard_soc
                q_hard = q_error is not None and abs(q_error) <= hard_q
                preferred = soc_error is not None and q_error is not None and abs(soc_error) <= pref_soc and abs(q_error) <= pref_q
                soc_status, q_status = status_name(state["soc_status"]), status_name(state["capacity_status"])
                point = {"next_index": n, "time_s": state["elapsed_s"], "SOC_error_pp": soc_error,
                    "capacity_error_percent": q_error, "soc_hard": soc_hard, "capacity_hard": q_hard,
                    "hard": soc_hard and q_hard, "preferred": preferred, "soc_status": soc_status,
                    "capacity_status": q_status, "state": state}
                trajectory.append(point)
                if n in (350, 31500, 63000, 73500) and arm != "warm":
                    pos_est = np.r_[x[6:10], np.exp(x[:3]), x[10], np.exp(x[3:6])]
                    pos_true = np.r_[t["R0"], t["R"], t["tau"], t["H"], t["gamma_plus"], t["gamma_minus"], t["Q_Ah"]]
                    scored_case["selected_full_vectors"].append({"arm": arm, "next_index": n,
                        "epoch_begin": record["epoch_begin"], "time_s": state["elapsed_s"],
                        "point_available": state["point_available"], "capacity_available": state["capacity_available"],
                        "mean": x.tolist(), "truth_current_chart": true_x.tolist(), "coordinate_sd": state["coordinate_sd"],
                        "scaled_current_vector_RMS": float(np.sqrt(np.mean(((x - true_x) / SCALES) ** 2))),
                        "positive_parameter_relative_error_percent": dict(zip(
                            ["R0", "R1", "R2", "R3", "tau1", "tau2", "tau3", "H", "gamma_plus", "gamma_minus", "Q_Ah"],
                            (100 * (pos_est / pos_true - 1)).tolist())),
                        "current_SOC_error_pp": soc_error,
                        "current_RC_error_mV": (1000 * (x[12:15] - true_x[12:15])).tolist(),
                        "current_hysteresis_error": float(x[15] - true_x[15]),
                        "soc_status": soc_status, "capacity_status": q_status})
            required = gates["cold_samples"] if arm == "cold" else gates["control_and_warm_samples"]
            by_position = {p["next_index"]: p for p in trajectory}
            for n in required:
                p = by_position.get(n)
                row = {"arm": arm, "next_index": n, "present": p is not None,
                       "hard_passed": bool(p and p["hard"]), "preferred_passed": bool(p and p["preferred"])}
                if p:
                    row.update({key: p[key] for key in ("time_s", "SOC_error_pp", "capacity_error_percent", "soc_status", "capacity_status")})
                scored_case["benchmarks"].append(row)
            first_s, sustained_s = {}, {}
            for tier in ("hard", "preferred"):
                first_s[tier] = next((p["time_s"] for p in trajectory if p[tier]), None)
                sustained_s[tier] = None
                for p in reversed(trajectory):
                    if not p[tier]:
                        break
                    sustained_s[tier] = p["time_s"]
            misleading_soc = [p for p in trajectory if p["soc_status"] == "provisional" and p["SOC_error_pp"] is not None and not p["soc_hard"]]
            misleading_q = [p for p in trajectory if p["capacity_status"] == "provisional" and p["capacity_error_percent"] is not None and not p["capacity_hard"]]
            final = trajectory[-1]["state"] if trajectory else {}
            scored_case["arms"][arm] = {"query_count": len(trajectory), "first_both_s": first_s,
                "sustained_both_from_s": sustained_s, "within_hard_queries": sum(p["hard"] for p in trajectory),
                "within_preferred_queries": sum(p["preferred"] for p in trajectory),
                "SOC_status_counts": dict(Counter(p["soc_status"] for p in trajectory)),
                "capacity_status_counts": dict(Counter(p["capacity_status"] for p in trajectory)),
                "max_abs_SOC_error_pp_at_queries": max((abs(p["SOC_error_pp"]) for p in trajectory if p["SOC_error_pp"] is not None), default=None),
                "max_abs_capacity_error_percent_at_queries": max((abs(p["capacity_error_percent"]) for p in trajectory if p["capacity_error_percent"] is not None), default=None),
                "provisional_SOC_hard_error_breaches": len(misleading_soc),
                "provisional_capacity_hard_error_breaches": len(misleading_q),
                "first_provisional_hard_breach": {"SOC": misleading_soc[0]["time_s"] if misleading_soc else None,
                    "capacity": misleading_q[0]["time_s"] if misleading_q else None},
                "final_counters": {key: final.get(key) for key in ("prediction_count", "voltage_count", "rejected_voltage_count",
                    "limited_gain_count", "zero_gain_count", "missing_voltage_count", "cold_resets", "minimum_gain_scale")}}
            if misleading_soc or misleading_q:
                failures.append({"case_id": case_id, "arm": arm, "kind": "provisional_point_exceeds_hard_error",
                    "SOC_queries": len(misleading_soc), "capacity_queries": len(misleading_q)})
            times = [p["time_s"] / 60 for p in trajectory]
            style = {"color": colors[arm], "label": arm, "linewidth": 1.5, "linestyle": "--" if arm == "warm" else "-"}
            for row, key in ((0, "SOC_error_pp"), (1, "capacity_error_percent")):
                axes[row, column].plot(times, [np.nan if p[key] is None else p[key] for p in trajectory], **style)
        scored_case["hard_accuracy_passed"] = all(b["hard_passed"] for b in scored_case["benchmarks"])
        scored_case["preferred_accuracy_passed"] = all(b["preferred_passed"] for b in scored_case["benchmarks"])
        result["cases"].append(scored_case)
        axes[0, column].set_title(case_id.split("_35hz")[0].replace("_", " ").title())
        for row, hard, pref in ((0, hard_soc, pref_soc), (1, hard_q, pref_q)):
            axis = axes[row, column]
            axis.axhspan(-pref, pref, color="#dceaf2", zorder=-1)
            for sign in (-1, 1):
                axis.axhline(sign * hard, color="#b0413e", linestyle=":", linewidth=1)
            axis.axhline(0, color="#747c85", linewidth=.6)
            axis.axvline(15, color=colors["cold"], linestyle=":", linewidth=1)
            axis.set_yscale("symlog", linthresh=.5)
            axis.grid(alpha=.2)
        axes[2, column].plot(physical_time / 60, current * 1000, color="#4c5666", linewidth=1)
        axes[2, column].grid(alpha=.2)
        axes[2, column].set_xlabel("Actual elapsed time (minutes)")
    axes[0, 0].set_ylabel("Current SOC error (percentage points)")
    axes[1, 0].set_ylabel("Capacity error (%)")
    axes[2, 0].set_ylabel("Current (mA)")
    axes[0, 0].legend(loc="best")
    fig.suptitle("First bounded online learner: frozen two-cell falsification\n"
                 "Blue band: preferred ±0.5; red lines: hard limits; orange vertical: cold reset", fontsize=12)
    figure.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(figure, dpi=160)
    fig.savefig(figure.with_suffix(".svg"))
    plt.close(fig)
    result["hard_accuracy_passed"] = all(c["hard_accuracy_passed"] for c in result["cases"]) and len(result["cases"]) == 2
    result["preferred_accuracy_passed"] = all(c["preferred_accuracy_passed"] for c in result["cases"]) and len(result["cases"]) == 2
    result["provisional_hard_error_audit_passed"] = not failures
    result["provisional_hard_error_failures"] = failures
    result["figure_sha256"] = {p.name: sha(p) for p in (figure, figure.with_suffix(".svg"))}
    result["scoring_finished_utc"] = datetime.now(timezone.utc).isoformat()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(json_safe(result), indent=2, allow_nan=False) + "\n")
    print(json.dumps({key: result[key] for key in ("functional_passed", "hard_accuracy_passed",
        "preferred_accuracy_passed", "provisional_hard_error_audit_passed")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
