#!/usr/bin/env python3
"""Run the one frozen two-arm chronological comparison. Never load truth.

Existing output directories are refused. Each process's first stdout/stderr
and complete checkpoints remain in the receipt directory, including failures.
The source and prerequisite hashes must match the committed pre-run snapshot.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "experiments/nonlinear_hypothesis_001/plan.json"
QUALIFICATION = ROOT / "experiments/nonlinear_hypothesis_001/development/qualification.json"
ALGORITHM = "two_component_public_logQ_predictive_joseph_v1"
SOURCES = (
    "Makefile", "include/scm_model.h", "src/scm_model.c", "include/scm_online.h",
    "include/scm_hypothesis.h", "src/scm_hypothesis.c",
    "include/scm_hypothesis_checkpoint.h", "src/scm_hypothesis_checkpoint.c",
    "tools/hypothesis_probe.c", "tests/test_hypothesis.c",
    "tests/test_hypothesis_checkpoint.c", "tools/run_nonlinear_hypothesis.py",
    "tools/score_nonlinear_hypothesis.py", "tools/generate_cases.py",
    "plans/estimation_targets_001.json", "plans/capacity_learning_horizon_001.json",
    "plans/nonlinear_evidence_design_001.json", "experiments/nonlinear_hypothesis_001/plan.json",
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def strict_json(text: str):
    def invalid(value):
        raise ValueError("Nonfinite JSON constant: " + value)
    return json.loads(text, parse_constant=invalid)


def save(path: Path, value) -> None:
    # Only the current new run's receipt is updated; frozen old directories
    # cannot be opened by this program because main refuses their existence.
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def validate_plan(plan: dict) -> None:
    assert plan["schema"] == "mumble_nonlinear_hypothesis_plan_v1"
    case, execution = plan["case"], plan["execution"]
    assert case["samples"] == 73500 and case["start_index"] == 0
    assert execution["expected_processes"] == 2
    assert execution["expected_input_deliveries"] == 147000
    assert execution["checkpoint_samples"] == [31500, 63000, 73500]
    assert execution["query_stride_samples"] == 350
    assert execution["early_query_stride_samples"] == 35
    assert execution["early_query_through_sample"] == 350
    assert execution["case_workers"] == 1 and execution["primary_repetitions"] == 1
    assert [(a["name"], a["mode"]) for a in plan["arms"]] == [
        ("coincident_control", "coincident"), ("public_logQ_split", "split")]
    assert sha(ROOT / case["path"]) == case["sha256"]
    assert plan["assessment"]["capacity_startup_deadline"] is None


def expected_schedule(plan: dict) -> list[int]:
    end = plan["case"]["samples"]
    execution = plan["execution"]
    return sorted({0, end, *execution["checkpoint_samples"],
                   *range(350, end + 1, 350), *range(35, 351, 35)})


def validate_output(events: list[dict], plan: dict, arm: dict, code: int) -> dict:
    case = plan["case"]
    runs = [x for x in events if x.get("event") == "run"]
    queries = [x for x in events if x.get("event") == "query"]
    complete = [x for x in events if x.get("event") == "complete"]
    checkpoints = [x for x in events if x.get("event") == "checkpoint"]
    expected = {"schema": "mumble_hypothesis_jsonl_v1", "model_version": 1,
                "algorithm": ALGORITHM, "mode": arm["mode"], "source_id": case["sha256"],
                "start_index": 0, "end_index": 73500, "dimension": 16, "components": 2,
                "restored": False, "cold_reset": False, "query_stride_samples": 350,
                "sigma_V": .001, "max_dt_s": 1., "max_abs_current_A": .25,
                "checkpoint_bytes": 3004, "batch_optimizer_calls": 0,
                "truth_input": False, "raw_history_retained": False}
    checks = {
        "successful_exit": code == 0,
        "identity": len(runs) == 1 and all(runs[0].get(k) == v for k, v in expected.items()),
        "query_schedule": [q["next_index"] for q in queries] == expected_schedule(plan),
        "completion": len(complete) == 1 and complete[0].get("input_deliveries") == 73500
                      and complete[0].get("next_index") == 73500,
        "checkpoint_schedule": [q["next_index"] for q in checkpoints] == plan["execution"]["checkpoint_samples"],
        "no_error_or_fit_events": not any(e.get("event") in ("error", "fit", "fit_begin") for e in events),
        "chronology_and_common_counts": bool(queries),
        "weights_normalized": bool(queries),
        "honest_qualification_metadata": bool(queries),
        "coincident_components_identical": True,
    }
    for q in queries:
        n, aggregate, components = q["next_index"], q["aggregate"], q["components"]
        checks["chronology_and_common_counts"] &= len(components) == 2 and all(
            x["next_index"] == n and x["prediction_count"] == n and x["voltage_count"] == n
            and x["missing_voltage_count"] == 0 for x in [aggregate, *components])
        logs = q["log_weights"]
        checks["weights_normalized"] &= len(logs) == 2 and all(
            isinstance(x, (int, float)) and math.isfinite(x) for x in logs)
        if checks["weights_normalized"]:
            checks["weights_normalized"] &= abs(sum(math.exp(x) for x in logs) - 1) <= 1e-12
        checks["honest_qualification_metadata"] &= q.get("application_SOC_Q_accuracy") == "unresolved" \
            and q.get("coverage") == "unvalidated" and q.get("hard_support") == "not_provided"
        if arm["mode"] == "coincident":
            fields = ("mean", "coordinate_sd", "evidence_next_index", "point_available",
                      "capacity_available", "local_ranges_available", "rejected_voltage_count",
                      "limited_gain_count", "zero_gain_count")
            checks["coincident_components_identical"] &= all(
                components[0].get(key) == components[1].get(key) for key in fields) and logs[0] == logs[1]
    resources = queries[-1]["resources"] if queries else None
    resource_passed = bool(resources) and all(q["resources"] == resources for q in queries) \
        and resources["owned_subtotal_bytes"] <= 7152 and resources["checkpoint_bytes"] == 3004
    final = queries[-1] if queries else None
    numerical = bool(final) and checks["completion"] and all(
        q["aggregate"]["rejected_voltage_count"] == 0
        and (q["aggregate"]["flags"] & (2 | 4 | 16)) == 0 for q in queries)
    return {"checks": checks, "functional_passed": all(checks.values()),
            "owned_resource_gate_passed": bool(resource_passed), "resources": resources,
            "numerical_health_passed": bool(numerical),
            "query_count": len(queries),
            "input_deliveries": complete[0]["input_deliveries"] if len(complete) == 1 else
                max((q["next_index"] for q in queries), default=0),
            "final_counters": {k: final["aggregate"][k] for k in
                ("next_index", "prediction_count", "voltage_count", "missing_voltage_count", "rejected_voltage_count")}
                if final else None,
            "rejected_events": [e for e in events if e.get("event") == "voltage_rejected"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--binary", type=Path, default=ROOT / "build/scm_hypothesis_probe")
    args = parser.parse_args()
    out, binary = args.output.resolve(), args.binary.resolve()
    if out.exists():
        parser.error("Preserve first results; output directory already exists")
    plan = strict_json(PLAN.read_text())
    validate_plan(plan)
    source_revision = git("rev-parse", "HEAD")
    for path in SOURCES:
        frozen = subprocess.check_output(["git", "show", source_revision + ":" + path], cwd=ROOT)
        if (ROOT / path).read_bytes() != frozen:
            raise ValueError("Uncommitted experiment source: " + path)
    qualification = strict_json(QUALIFICATION.read_text())
    if not qualification.get("ready_for_primary"):
        raise ValueError("Targeted prerequisites have not passed")
    for path, digest in qualification["implementation_sha256"].items():
        if sha(ROOT / path) != digest:
            raise ValueError("Implementation differs from qualified source: " + path)
    if sha(binary) != qualification["probe_binary_sha256"]:
        raise ValueError("Probe binary differs from prerequisite receipt")
    out.mkdir(parents=True)
    (out / "checkpoints").mkdir()
    receipt = {"schema": "mumble_nonlinear_hypothesis_receipt_v1",
               "source_revision": source_revision, "source_tree": git("rev-parse", "HEAD^{tree}"),
               "source_sha256": {p: sha(ROOT / p) for p in SOURCES},
               "truth_manifest_git_blob": git("rev-parse", source_revision + ":data/manifest.json"),
               "plan_sha256": sha(PLAN), "qualification_sha256": sha(QUALIFICATION),
               "binary_sha256": sha(binary), "binary": str(binary),
               "platform": platform.platform(), "python": platform.python_version(),
               "started_utc": datetime.now(timezone.utc).isoformat(), "inference_completed": False,
               "case": plan["case"], "processes": [], "truth_loaded_by_runner": False,
               "batch_optimizer_calls": 0, "original_study_reruns": 0,
               "capacity_deadline_amendment": "plans/capacity_learning_horizon_001.json",
               "target_memory_or_timing_qualified": False}
    save(out / "receipt.json", receipt)
    for arm in plan["arms"]:
        stem = arm["name"]
        stdout, stderr = out / (stem + ".jsonl"), out / (stem + ".stderr.txt")
        command = [str(binary), "--mode", arm["mode"], "--data", str(ROOT / plan["case"]["path"]),
                   "--source", plan["case"]["sha256"], "--end", "73500",
                   "--checkpoint-prefix", str(out / "checkpoints" / stem),
                   "--save-at", "31500,63000,73500", "--query-stride", "350"]
        print(json.dumps({"event": "arm_start", "arm": stem, "samples": 73500}), flush=True)
        start = time.monotonic()
        error = None
        with stdout.open("wb") as output, stderr.open("wb") as errors:
            try:
                result = subprocess.run(command, cwd=ROOT, stdout=output, stderr=errors,
                                        timeout=plan["execution"]["process_timeout_s"])
                code = result.returncode
            except (OSError, subprocess.TimeoutExpired) as failure:
                code, error = -1, str(failure)
        process = {"arm": stem, "mode": arm["mode"], "command": command,
                   "returncode": code, "execution_error": error, "wall_seconds": time.monotonic() - start,
                   "stdout_jsonl": stdout.name, "stderr": stderr.name,
                   "stdout_sha256": sha(stdout), "stderr_sha256": sha(stderr),
                   "stdout_bytes": stdout.stat().st_size, "checkpoint_records": []}
        try:
            events = [strict_json(line) for line in stdout.read_text().splitlines() if line]
            process.update(validate_output(events, plan, arm, code))
        except (ValueError, KeyError, TypeError, OverflowError) as failure:
            process.update({"parse_or_validation_error": str(failure), "functional_passed": False,
                            "numerical_health_passed": False, "owned_resource_gate_passed": False})
        for n in plan["execution"]["checkpoint_samples"]:
            path = out / "checkpoints" / f"{stem}-{n}.bin"
            if path.exists():
                process["checkpoint_records"].append({"next_index": n, "path": str(path.relative_to(out)),
                    "bytes": path.stat().st_size, "sha256": sha(path)})
                if path.stat().st_size != 3004:
                    process["functional_passed"] = False
        process["checkpoint_files_complete"] = [r["next_index"] for r in process["checkpoint_records"]] == \
            plan["execution"]["checkpoint_samples"]
        process["functional_passed"] &= process["checkpoint_files_complete"]
        receipt["processes"].append(process)
        save(out / "receipt.json", receipt)
        print(json.dumps({"event": "arm_complete", "arm": stem, "returncode": code,
            "functional_passed": process["functional_passed"],
            "numerical_health_passed": process["numerical_health_passed"],
            "wall_seconds": process["wall_seconds"]}), flush=True)
    receipt.update({"inference_completed": True, "finished_utc": datetime.now(timezone.utc).isoformat(),
        "input_deliveries": sum(p.get("input_deliveries", 0) for p in receipt["processes"]),
        "functional_passed": all(p["functional_passed"] for p in receipt["processes"]),
        "numerical_health_passed": all(p["numerical_health_passed"] for p in receipt["processes"]),
        "owned_resource_gate_passed": all(p["owned_resource_gate_passed"] for p in receipt["processes"])})
    save(out / "receipt.json", receipt)
    print(json.dumps({k: receipt[k] for k in ("inference_completed", "input_deliveries",
        "functional_passed", "numerical_health_passed", "owned_resource_gate_passed")}), flush=True)
    return 0 if all(receipt[k] for k in ("functional_passed", "numerical_health_passed", "owned_resource_gate_passed")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
