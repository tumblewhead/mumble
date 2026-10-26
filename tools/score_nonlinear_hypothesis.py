#!/usr/bin/env python3
"""Score closed two-component outputs; no inference or tuning is performed.

Truth is imported only after both scheduled inference processes have ended and
the frozen source/plan/output hashes validate. The capacity time hypothesis is
assessed on the predeclared2100s trace without an early capacity deadline.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path

from run_nonlinear_hypothesis import ROOT, PLAN, sha, strict_json, git

NAMES = ["log_tau1", "log_tau2", "log_tau3", "log_gamma_plus", "log_gamma_minus",
         "log_Q_Ah", "R0", "R1", "R2", "R3", "H", "current_z", "current_v1",
         "current_v2", "current_v3", "current_h"]
SCALES = [1.] * 6 + [.2] * 4 + [.03, .1, .03, .03, .03, 1.]


def write_new(path: Path, result) -> None:
    with path.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")


def attainment(rows: list[dict], metric: str, threshold: float) -> dict:
    passed = [r[metric] is not None and abs(r[metric]) <= threshold for r in rows]
    first = next((r["time_s"] for r, p in zip(rows, passed) if p), None)
    retained = None
    for row, passes in zip(reversed(rows), reversed(passed)):
        if not passes:
            break
        retained = row["time_s"]
    return {"first_observed_hit_s": first, "from_which_all_later_saved_queries_pass_s": retained,
            "passed_queries": sum(passed), "queries": len(rows),
            "scope": "Available points on the saved grid through this finite endpoint; not continuous-time convergence or uncertainty qualification."}


def measure(view: dict, truth: dict, gates: dict) -> dict:
    soc = 100 * (view["current_soc"] - truth["z0"]) if view["point_available"] else None
    q = 100 * (view["capacity_Ah"] / truth["Q_Ah"] - 1) if view["capacity_available"] else None
    soc_hard = soc is not None and abs(soc) <= gates["hard_SOC_error_pp"]
    q_hard = q is not None and abs(q) <= gates["hard_capacity_error_percent"]
    q_halfwidth = None
    if view["local_ranges_available"] and view["capacity_Ah"] > 0:
        q_halfwidth = 100 * max(view["capacity_Ah"] - view["capacity_local_lower_Ah"],
                               view["capacity_local_upper_Ah"] - view["capacity_Ah"]) / view["capacity_Ah"]
    return {"SOC_error_pp": soc, "capacity_error_percent": q, "SOC_hard": soc_hard,
            "capacity_hard": q_hard, "SOC_preferred": soc is not None and abs(soc) <= gates["preferred_SOC_error_pp"],
            "capacity_preferred": q is not None and abs(q) <= gates["preferred_capacity_error_percent"],
            "capacity_Ah": view["capacity_Ah"] if view["capacity_available"] else None,
            "current_SOC": view["current_soc"] if view["point_available"] else None,
            "capacity_local_2SD_halfwidth_percent_of_estimate": q_halfwidth,
            "capacity_local_interval_covers_truth": bool(view["local_ranges_available"] and
                view["capacity_local_lower_Ah"] <= truth["Q_Ah"] <= view["capacity_local_upper_Ah"]),
            "SOC_local_interval_covers_truth": bool(view["local_ranges_available"] and
                view["soc_local_lower"] <= truth["z0"] <= view["soc_local_upper"]),
            "soc_local_status": view["soc_status"], "capacity_local_status": view["capacity_status"],
            "soc_local_provisional_hard_breach": view["soc_status"] == "provisional" and not soc_hard,
            "capacity_local_provisional_hard_breach": view["capacity_status"] == "provisional" and not q_hard,
            "evidence_next_index": view["evidence_next_index"], "flags": view["flags"]}


def status_counts(rows: list[dict]) -> dict:
    return {"SOC_unavailable_queries": sum(r["SOC_error_pp"] is None for r in rows),
            "capacity_unavailable_queries": sum(r["capacity_error_percent"] is None for r in rows),
            "SOC_local_provisional_hard_breaches": sum(r["soc_local_provisional_hard_breach"] for r in rows),
            "capacity_local_provisional_hard_breaches": sum(r["capacity_local_provisional_hard_breach"] for r in rows)}


def trend(rows: list[dict]) -> dict:
    at = {r["next_index"]: r for r in rows}
    q = {n: at[n]["capacity_error_percent"] if n in at else None for n in (31500, 63000, 73500)}
    def reduction(a, b):
        return abs(q[a]) - abs(q[b]) if q[a] is not None and q[b] is not None else None
    return {"capacity_error_percent_at_900_1800_2100s": [q[n] for n in (31500, 63000, 73500)],
            "absolute_error_reduction_900_to_1800_percent_points": reduction(31500, 63000),
            "absolute_error_reduction_1800_to_2100_percent_points": reduction(63000, 73500),
            "interpretation": "Positive reduction means smaller absolute scored error. The900-to1800 segment includes later varied/informative input;1800-to2100 is the prescribed weak tail. Neither is an asymptotic convergence proof."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--figure", type=Path, required=True)
    args = parser.parse_args()
    primary, output, figure = (p.resolve() for p in (args.primary, args.output, args.figure))
    if any(p.exists() for p in (output, figure, figure.with_suffix(".svg"))):
        parser.error("Preserve first scores/figures; output exists")
    receipt_path = primary / "receipt.json"
    receipt = strict_json(receipt_path.read_text())
    if receipt.get("schema") != "mumble_nonlinear_hypothesis_receipt_v1" or \
            not receipt.get("inference_completed") or not receipt.get("finished_utc") or len(receipt["processes"]) != 2:
        parser.error("Both inference attempts must finish before truth scoring")
    if receipt["plan_sha256"] != sha(PLAN):
        parser.error("Plan differs from pre-inference snapshot")
    for name in ("tools/score_nonlinear_hypothesis.py", "tools/run_nonlinear_hypothesis.py", "tools/generate_cases.py"):
        if receipt["source_sha256"].get(name) != sha(ROOT / name):
            parser.error("Frozen scoring source differs: " + name)
    all_events = {}
    for process in receipt["processes"]:
        path = primary / process["stdout_jsonl"]
        if sha(path) != process["stdout_sha256"]:
            parser.error("Inference output changed: " + str(path))
        all_events[process["arm"]] = [strict_json(line) for line in path.read_text().splitlines() if line]

    # Bind truth to the committed snapshot without reading it in inference.
    manifest = ROOT / "data/manifest.json"
    if git("hash-object", str(manifest)) != receipt["truth_manifest_git_blob"]:
        parser.error("Truth manifest differs from the frozen source tree")
    # This is the first truth-bearing import/parse in this program.
    import numpy as np
    from generate_cases import advance_truth
    cache = ROOT / "build/matplotlib"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plan = strict_json(PLAN.read_text())
    gates = plan["assessment"]
    truth_case = next(c for c in strict_json(manifest.read_text())["cases"] if c["case_id"] == plan["case"]["id"])
    data_path = ROOT / plan["case"]["path"]
    if sha(data_path) != plan["case"]["sha256"] or sha(data_path) != truth_case["sha256"]:
        raise ValueError("Frozen observations changed")
    data = np.loadtxt(data_path, delimiter=",", skiprows=1)
    truth = truth_case["truth"]
    requested = sorted({q["next_index"] for events in all_events.values() for q in events if q.get("event") == "query"})
    truth_at = {n: advance_truth(data[:n, 1], data[:n, 2], truth) for n in requested}
    selected = {int(t * 35) for t in plan["execution"]["selected_query_times_s"]}
    result = {"schema": "mumble_nonlinear_hypothesis_scores_v1", "source_revision": receipt["source_revision"],
        "inference_finished_utc": receipt["finished_utc"], "scoring_started_utc": datetime.now(timezone.utc).isoformat(),
        "primary_receipt_sha256": sha(receipt_path), "plan_sha256": sha(PLAN),
        "source_sha256": {p: sha(ROOT / p) for p in ("tools/score_nonlinear_hypothesis.py",
            "tools/run_nonlinear_hypothesis.py", "tools/generate_cases.py", "data/manifest.json")},
        "truth_used_only_after_inference": True, "estimator_calls": 0, "optimizer_calls": 0,
        "capacity_startup_deadline": None, "case_id": plan["case"]["id"], "thresholds": gates,
        "query_scope": "1s grid through10s, then10s grid plus declared endpoints; samples themselves remain35Hz with original intervals.",
        "uncertainty_scope": "Local moment ranges and hulls are diagnostics. Empirical hits/misses on one correlated trace do not validate coverage.",
        "arms": {}, "full_vectors": [], "functional_passed": receipt["functional_passed"],
        "numerical_health_passed": receipt["numerical_health_passed"],
        "owned_resource_gate_passed": receipt["owned_resource_gate_passed"],
        "complete_target_qualified": False, "candidate_promoted": False}
    for name, events in all_events.items():
        queries = [q for q in events if q.get("event") == "query"]
        rows, component_rows = [], [[], []]
        for query in queries:
            n = query["next_index"]
            actual = truth_at[n]
            row = {"next_index": n, "time_s": query["aggregate"]["elapsed_s"],
                   **measure(query["aggregate"], actual, gates), "log_weights": query["log_weights"],
                   "all_component_local_hull": query["all_component_hull"],
                   "bank_evidence_next_index": query["bank_evidence_next_index"]}
            comps = []
            for j in range(2):
                c = {"next_index": n, "time_s": row["time_s"], **measure(query["components"][j], actual, gates)}
                component_rows[j].append(c)
                comps.append(c)
            q_errors = [abs(c["capacity_error_percent"]) for c in comps if c["capacity_error_percent"] is not None]
            row["oracle_best_component_capacity_abs_error_percent_scoring_only"] = min(q_errors) if q_errors else None
            row["any_component_capacity_hard_scoring_only"] = any(c["capacity_hard"] for c in comps)
            rows.append(row)
            if n in selected:
                true_x = [*map(math.log, actual["tau"]), math.log(actual["gamma_plus"]),
                          math.log(actual["gamma_minus"]), math.log(actual["Q_Ah"]),
                          actual["R0"], *actual["R"], actual["H"], actual["z0"], *actual["v0"], actual["h0"]]
                for selector, view in [("aggregate", query["aggregate"]), ("component0", query["components"][0]),
                                       ("component1", query["components"][1])]:
                    error = [(v - t) / scale for v, t, scale in zip(view["mean"], true_x, SCALES)]
                    result["full_vectors"].append({"arm": name, "view": selector, "next_index": n,
                        "time_s": row["time_s"], "coordinate_names": NAMES, "mean": view["mean"],
                        "truth_current_chart_scoring_only": true_x, "coordinate_sd": view["coordinate_sd"],
                        "engineering_scales": SCALES, "scaled_current_vector_RMS": math.sqrt(sum(x*x for x in error)/16),
                        "point_available": bool(view["point_available"]), "capacity_available": bool(view["capacity_available"])})
        aggregate_times = {f"{metric}_{quality}": attainment(rows, field, gates[key]) for metric, field, hard, preferred in (
            ("SOC", "SOC_error_pp", "hard_SOC_error_pp", "preferred_SOC_error_pp"),
            ("capacity", "capacity_error_percent", "hard_capacity_error_percent", "preferred_capacity_error_percent"))
            for quality, key in (("hard", hard), ("preferred", preferred))}
        at = {r["next_index"]: r for r in rows}
        result["arms"][name] = {"queries": rows, "selected_checkpoints": [r for r in rows if r["next_index"] in selected],
            "observed_attainment": aggregate_times, "aggregate_qualification_audit": status_counts(rows),
            "capacity_learning": trend(rows),
            "SOC_usefulness_gate": all(n in at and at[n]["SOC_hard"] for n in (31500, 63000, 73500)),
            "capacity_hard_at_1800_and_2100": all(n in at and at[n]["capacity_hard"] for n in (63000, 73500)),
            "components": [{"component": j, "queries": crows, "qualification_audit": status_counts(crows),
                            "capacity_learning": trend(crows)} for j, crows in enumerate(component_rows)]}
    old_path = ROOT / "experiments/bounded_online_002/scores.json"
    old = next(c for c in strict_json(old_path.read_text())["cases"] if c["case_id"] == plan["case"]["id"])
    result["frozen_predecessor"] = {"path": str(old_path.relative_to(ROOT)), "sha256": sha(old_path), "rerun": False,
        "selected_control": [{"next_index": v["next_index"], "SOC_error_pp": v["current_SOC_error_pp"],
            "capacity_error_percent": v["positive_parameter_relative_error_percent"]["Q_Ah"]}
            for v in old["selected_full_vectors"] if v["arm"] == "control" and v["next_index"] in (31500, 63000, 73500)]}
    result["decision_inputs"] = {"functional": receipt["functional_passed"], "numerical": receipt["numerical_health_passed"],
        "owned_resources": receipt["owned_resource_gate_passed"],
        "split_SOC_useful": result["arms"]["public_logQ_split"]["SOC_usefulness_gate"],
        "split_capacity_hard_late": result["arms"]["public_logQ_split"]["capacity_hard_at_1800_and_2100"],
        "capacity_no_startup_deadline": True,
        "scope": "Mechanism decision must consider paired arms, component alternatives, weights and later learning/retention. This finite result cannot establish eventual convergence or validated coverage."}

    fig, axes = plt.subplots(2, 2, figsize=(12.8, 8.2), sharex=True, constrained_layout=True)
    colors = {"coincident_control": "#496780", "public_logQ_split": "#c45c26"}
    labels = {"coincident_control": "Coincident control", "public_logQ_split": "Public capacity split"}
    for name, arm in result["arms"].items():
        rows = arm["queries"]; t = [r["time_s"]/60 for r in rows]
        def values(key): return [r[key] if r[key] is not None else float("nan") for r in rows]
        axes[0, 0].plot(t, values("capacity_error_percent"), label=labels[name], color=colors[name], linewidth=1.8)
        axes[0, 1].plot(t, values("SOC_error_pp"), label=labels[name], color=colors[name], linewidth=1.8)
        axes[1, 0].plot(t, values("capacity_local_2SD_halfwidth_percent_of_estimate"), color=colors[name], linewidth=1.8)
    split = result["arms"]["public_logQ_split"]
    for j, color in ((0, "#267b72"), (1, "#985aa7")):
        rows = split["components"][j]["queries"]
        axes[1, 1].plot([r["time_s"]/60 for r in rows],
            [r["capacity_error_percent"] if r["capacity_error_percent"] is not None else float("nan") for r in rows],
            label=f"Split component {j}", color=color, linewidth=1.5)
    rows = split["queries"]
    axes[1, 1].plot([r["time_s"]/60 for r in rows],
        [r["capacity_error_percent"] if r["capacity_error_percent"] is not None else float("nan") for r in rows],
        label="Weighted aggregate", color=colors["public_logQ_split"], linewidth=2)
    for axis, hard in ((axes[0, 0], 5), (axes[0, 1], 10), (axes[1, 1], 5)):
        axis.axhspan(-hard, hard, color="#418051", alpha=.09)
        axis.axhline(0, color="#64748b", linewidth=.6)
        axis.axhline(hard, color="#418051", linewidth=.8, linestyle="--")
        axis.axhline(-hard, color="#418051", linewidth=.8, linestyle="--")
    axes[1, 0].set_yscale("log")
    axes[0, 0].set(title="Capacity point error — no startup deadline", ylabel="Relative error (%)")
    axes[0, 1].set(title="Current SOC point error", ylabel="Error (percentage points)")
    axes[1, 0].set(title="Local capacity precision — not validated coverage", ylabel="Largest two-SD halfwidth (%)", xlabel="Elapsed time (minutes)")
    axes[1, 1].set(title="Retained capacity alternatives", ylabel="Relative error (%)", xlabel="Elapsed time (minutes)")
    for axis in axes.flat:
        axis.axvline(15, color="#64748b", linestyle=":", linewidth=.8)
        axis.axvspan(30, 35, color="#64748b", alpha=.08)
        axis.grid(alpha=.18)
        axis.set_xlim(0, 35)
    axes[0, 0].legend(fontsize=8); axes[1, 1].legend(fontsize=8)
    fig.suptitle("mumble: one chronological Cell B comparison\n15 min diagnostic; 30–35 min weak tail; truth used only after inference", fontsize=13)
    figure.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(figure, dpi=160); fig.savefig(figure.with_suffix(".svg")); plt.close(fig)
    result["figures"] = {str(p.relative_to(ROOT)): sha(p) for p in (figure, figure.with_suffix(".svg"))}
    result["scoring_finished_utc"] = datetime.now(timezone.utc).isoformat()
    write_new(output, result)
    print(json.dumps({"output": str(output), "arms": {name: {"capacity_learning": arm["capacity_learning"],
        "SOC_attainment": arm["observed_attainment"]["SOC_hard"], "SOC_usefulness_gate": arm["SOC_usefulness_gate"],
        "capacity_hard_late": arm["capacity_hard_at_1800_and_2100"]} for name, arm in result["arms"].items()}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
