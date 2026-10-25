#!/usr/bin/env python3
"""Score completed M1 inference; never invoked by the inference runner.

Reads truth only after the immutable primary receipt says every process has
finished. No optimization, parameter correction or inference output rewrite.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--figure", type=Path, required=True)
    args = parser.parse_args()
    primary, output, figure = (p.resolve() for p in (args.primary, args.output, args.figure))
    if output.exists() or figure.exists() or figure.with_suffix(".svg").exists():
        parser.error("Scoring outputs exist; preserve them and choose a new destination")
    receipt_path = primary / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    if not receipt.get("inference_completed") or not receipt.get("finished_utc"):
        parser.error("All inference must finish before truth scoring")

    # Truth-bearing modules/data are deliberately loaded only past this gate.
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from generate_cases import advance_truth, simulate
    from validate import assess_result, json_safe

    manifest_path = ROOT / "data/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    truths = {case["case_id"]: case for case in manifest["cases"]}
    gate = receipt["acceptance"]["usefulness"]
    scores = {
        "schema": "mumble_trajectory_integration_scores_v1",
        "scoring_started_utc": datetime.now(timezone.utc).isoformat(),
        "inference_finished_utc": receipt["finished_utc"],
        "source_revision": receipt["source_revision"],
        "primary_receipt_sha256": sha(receipt_path),
        "scorer_sha256": sha(Path(__file__)),
        "scoring_dependencies_sha256": {name: sha(ROOT / name) for name in
            ("tools/validate.py", "tools/generate_cases.py", "data/manifest.json")},
        "truth_scope": "Post-inference scoring only. Cold entering truth is shifted only for independent scoring.",
        "functional_passed": receipt["functional_passed"],
        "usefulness_thresholds": gate,
        "cases": [],
        "uncertainty_scope": "Reported ranges are local likelihood diagnostics. Observed truth errors are not validated coverage.",
        "query_metrics_scope": "Deduplicated sparse scheduled queries; not a bound on every intervening sample.",
    }
    fig, axes = plt.subplots(3, 2, figsize=(12.8, 10.5), sharex=True, constrained_layout=True)
    colors = {"control": "#17639b", "warm": "#42a58a", "cold": "#cb6231"}
    raw_hashes = {}
    for column, case in enumerate(receipt["cases"]):
        case_id = case["case_id"]
        truth_record = truths[case_id]
        csv = manifest_path.parent / truth_record["csv"]
        if sha(csv) != truth_record["sha256"]:
            raise ValueError(f"Input changed: {case_id}")
        data = np.loadtxt(csv, delimiter=",", skiprows=1)
        dt, current, measured = data[:, 1], data[:, 2], data[:, 3]
        physical_time = np.cumsum(dt)
        truth = truth_record["truth"]
        _, true_soc, _ = simulate(dt, current, truth, states=True)
        events = {arm: [] for arm in ("control", "warm", "cold")}
        for process in case["processes"]:
            path = primary / process["stdout_jsonl"]
            raw_hashes[process["stdout_jsonl"]] = sha(path)
            if sha(path) != process["stdout_sha256"]:
                raise ValueError(f"Inference output changed: {path.name}")
            events[process["kind"]].extend(json.loads(line) for line in path.read_text().splitlines() if line)
        scored_case = {"case_id": case_id, "functional_passed": case["functional_passed"],
            "truth_capacity_Ah": truth["Q_Ah"], "fits": [], "arms": {}, "benchmarks": []}
        for arm, records in events.items():
            queries = {r["next_index"]: r for r in records if r["event"] == "query"}
            trajectory = []
            for n, record in sorted(queries.items()):
                state = record["state"]
                actual_soc = float(true_soc[n - 1]) if n else truth["z0"]
                valid_soc = bool(state["point_available"])
                valid_q = bool(state["capacity_available"])
                trajectory.append({"next_index": n, "time_s": state["elapsed_s"],
                    "SOC_error_pp": 100 * (state["current_soc"] - actual_soc) if valid_soc else None,
                    "capacity_error_percent": 100 * (state["capacity_Ah"] / truth["Q_Ah"] - 1) if valid_q else None,
                    "evidence_age_s": float(state["elapsed_s"] - (physical_time[state["evidence_next_index"] - 1]
                        if state["evidence_next_index"] else 0)),
                    "state": state, "assessment": record["assessment"]})
            for record in (r for r in records if r["event"] == "fit"):
                n, begin = record["next_index"], record["epoch_begin"]
                fit = record["fit"]
                if fit is None:
                    scored_case["fits"].append({"arm": arm, "next_index": n,
                        "returncode": record["returncode"], "score": None})
                    continue
                entering_truth = advance_truth(dt[:begin], current[:begin], truth)
                independent = assess_result(fit, entering_truth, dt[begin:n], current[begin:n], measured[begin:n], receipt["execution"]["sigma"])
                query = queries[n]
                scored_case["fits"].append({"arm": arm, "next_index": n, "epoch_begin": begin,
                    "time_s": float(physical_time[n - 1]), "returncode": record["returncode"],
                    "optimizer_status": fit["status"], "termination_reason": fit["termination_reason"],
                    "iterations": fit["iterations"], "evaluations": fit["evaluations"],
                    "elapsed_cpu_s": fit["elapsed_cpu_s"], "independent_score": independent,
                    "assessment": query["assessment"], "resources": query["resources"]})
            required = gate["cold_recovery_checkpoints_samples"] if arm == "cold" else gate["uninterrupted_and_warm_checkpoints_samples"]
            by_position = {r["next_index"]: r for r in trajectory}
            for n in required:
                r = by_position.get(n)
                soc_error, q_error = (r["SOC_error_pp"], r["capacity_error_percent"]) if r else (None, None)
                soc_pass = soc_error is not None and abs(soc_error) < gate["current_SOC_abs_error_pp_lt"]
                q_pass = q_error is not None and abs(q_error) < gate["capacity_abs_relative_error_percent_lt"]
                scored_case["benchmarks"].append({"arm": arm, "next_index": n,
                    "time_s": r["time_s"] if r else None, "SOC_error_pp": soc_error,
                    "capacity_error_percent": q_error, "SOC_passed": soc_pass,
                    "capacity_passed": q_pass, "passed": soc_pass and q_pass,
                    "optimizer_status": r["state"]["optimizer_status"] if r else None,
                    "SOC_status": r["assessment"]["current_soc"]["status"] if r and r["assessment"] else "unknown",
                    "capacity_status": r["assessment"]["capacity_Ah"]["status"] if r and r["assessment"] else "unknown"})
            available = [r for r in trajectory if r["SOC_error_pp"] is not None]
            available_q = [r for r in trajectory if r["capacity_error_percent"] is not None]
            fitted = [r for r in scored_case["fits"] if r["arm"] == arm]
            jointly_useful = [r["SOC_error_pp"] is not None and r["capacity_error_percent"] is not None
                and abs(r["SOC_error_pp"]) < gate["current_SOC_abs_error_pp_lt"]
                and abs(r["capacity_error_percent"]) < gate["capacity_abs_relative_error_percent_lt"]
                for r in trajectory]
            first_useful = next((r["time_s"] for r, useful in zip(trajectory, jointly_useful) if useful), None)
            sustained_useful = None
            for r, useful in reversed(list(zip(trajectory, jointly_useful))):
                if not useful:
                    break
                sustained_useful = r["time_s"]
            scored_case["arms"][arm] = {
                "query_count": len(trajectory), "SOC_available_query_count": len(available),
                "capacity_available_query_count": len(available_q),
                "first_SOC_available_s": available[0]["time_s"] if available else None,
                "first_both_accuracy_benchmarks_s_at_queries": first_useful,
                "sustained_both_accuracy_benchmarks_from_s_at_queries": sustained_useful,
                "both_accuracy_benchmarks_query_count": sum(jointly_useful),
                "max_abs_SOC_error_pp_at_queries": max((abs(r["SOC_error_pp"]) for r in available), default=None),
                "max_abs_capacity_error_percent_at_queries": max((abs(r["capacity_error_percent"]) for r in available_q), default=None),
                "max_evidence_age_s_at_queries": max((r["evidence_age_s"] for r in available), default=None),
                "SOC_status_counts": dict(Counter(r["assessment"]["current_soc"]["status"] if r["assessment"] else "unknown" for r in trajectory)),
                "capacity_status_counts": dict(Counter(r["assessment"]["capacity_Ah"]["status"] if r["assessment"] else "unknown" for r in trajectory)),
                "fit_count": len(fitted), "fit_CPU_s": sum(r.get("elapsed_cpu_s", 0) for r in fitted),
                "nonconverged_fit_count": sum(r.get("optimizer_status", -1) != 0 for r in fitted),
                "peak_requested_session_owned_bytes": max((r["resources"]["peak_owned_bytes"] for r in queries.values()), default=0),
                "peak_requested_session_plus_successful_fit_bytes": max((r["resources"]["peak_fit_owned_bytes"] for r in queries.values()), default=0),
            }
            times = [r["time_s"] / 60 for r in trajectory]
            style = {"color": colors[arm], "label": arm, "linewidth": 1.7,
                "linestyle": "--" if arm == "warm" else "-", "alpha": .9}
            axes[0, column].plot(times, [np.nan if r["SOC_error_pp"] is None else r["SOC_error_pp"] for r in trajectory], **style)
            axes[1, column].plot(times, [np.nan if r["capacity_error_percent"] is None else r["capacity_error_percent"] for r in trajectory], **style)
        scored_case["usefulness_passed"] = all(r["passed"] for r in scored_case["benchmarks"])
        scored_case["control_and_warm_usefulness_passed"] = all(r["passed"] for r in scored_case["benchmarks"] if r["arm"] != "cold")
        scored_case["cold_usefulness_passed"] = all(r["passed"] for r in scored_case["benchmarks"] if r["arm"] == "cold")
        scores["cases"].append(scored_case)
        reset_s = float(physical_time[receipt["execution"]["cold_reset_sample"] - 1])
        axes[0, column].set_title(case_id.split("_35hz")[0].replace("_", " ").title())
        for row, threshold in ((0, gate["current_SOC_abs_error_pp_lt"]), (1, gate["capacity_abs_relative_error_percent_lt"])):
            axis = axes[row, column]
            axis.axhspan(-threshold, threshold, color="#dbe8ef", alpha=.65, zorder=-1)
            axis.axhline(0, color="#646d78", linewidth=.7)
            axis.axvline(reset_s / 60, color=colors["cold"], linestyle=":", linewidth=1.1)
            axis.set_yscale("symlog", linthresh=.5)
            axis.grid(alpha=.2)
        axes[2, column].plot(physical_time / 60, current * 1000, color="#4c5666", linewidth=1)
        axes[2, column].set_xlabel("Actual elapsed time (minutes)")
        axes[2, column].grid(alpha=.2)
    axes[0, 0].set_ylabel("Current SOC error (percentage points)\nSymmetric log scale outside ±0.5")
    axes[1, 0].set_ylabel("Capacity error (%)\nSymmetric log scale outside ±0.5")
    axes[2, 0].set_ylabel("Measured current (mA)")
    axes[0, 0].legend(loc="best")
    fig.suptitle("M1: two-cell lifecycle — uninterrupted, warm restart, and cold reset\n"
                 "Shading: predeclared ±0.5 benchmarks; dotted line: cold reset; gaps: unavailable estimates", fontsize=12)
    figure.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(figure, dpi=160)
    fig.savefig(figure.with_suffix(".svg"))
    plt.close(fig)
    scores["primary_output_sha256"] = raw_hashes
    scores["usefulness_passed"] = all(case["usefulness_passed"] for case in scores["cases"])
    scores["control_and_warm_usefulness_passed"] = all(case["control_and_warm_usefulness_passed"] for case in scores["cases"])
    scores["cold_usefulness_passed"] = all(case["cold_usefulness_passed"] for case in scores["cases"])
    scores["figure_sha256"] = {p.name: sha(p) for p in (figure, figure.with_suffix(".svg"))}
    scores["scoring_finished_utc"] = datetime.now(timezone.utc).isoformat()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(json_safe(scores), indent=2, allow_nan=False) + "\n")
    print(json.dumps({"functional_passed": scores["functional_passed"], "usefulness_passed": scores["usefulness_passed"],
        "control_and_warm_usefulness_passed": scores["control_and_warm_usefulness_passed"],
        "cold_usefulness_passed": scores["cold_usefulness_passed"], "scores": str(output), "figure": str(figure)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
