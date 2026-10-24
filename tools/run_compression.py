#!/usr/bin/env python3
"""Six bounded final-prefix compression comparisons; C performs all fitting.

The explicit initialization and feature construction use fixed nominal values.
Physical truth is passed only to validate.assess_result after each C fit.
The binary is privately snapshotted once so concurrent CLI rebuilds cannot
change methods between cases. Every failure is retained in the result record.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile
import time

import numpy as np

from validate import assess_result as score_result, json_safe

ROOT = Path(__file__).resolve().parents[1]
NOMINAL_THETA = [math.log(.07), math.log(.7), math.log(7.),
                 math.log(150.), math.log(300.), .68, math.log(.06)]
METHODS = ("full", "tangent", "hybrid")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(json_safe(obj), indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def summarize(records: list[dict]) -> list[dict]:
    rows = []
    full = {r["case_id"]: r for r in records if r["method"] == "full" and r.get("scores")}
    for record in records:
        row = {key: record.get(key) for key in ("case_id", "cell", "method", "returncode", "process_wall_s")}
        fit, score = record.get("result", {}), record.get("scores", {})
        for key in ("status", "termination_reason", "samples", "features", "blocks", "basis_bytes", "payload_bytes",
                    "workspace_bytes", "data_bytes", "retained_bytes", "setup_peak_bytes", "elapsed_cpu_s",
                    "basis_seconds", "basis_max_orthogonality", "max_discarded_column_norm"):
            row[key] = fit.get(key)
        for key in ("voltage_rmse_mV", "capacity_relative_error_percent", "current_SOC_error_pp",
                    "soc_trajectory_rmse_pp", "objective_full_independent", "objective_abs_discrepancy"):
            row[key] = score.get(key)
        if fit:
            row["voltage_payload_reduction_percent"] = 100. * (1. - fit["features"] / fit["samples"])
            row["fit_plus_basis_cpu_s"] = fit["elapsed_cpu_s"] + fit["basis_seconds"]
        reference = full.get(record["case_id"])
        if score and reference:
            fs = reference["scores"]
            row["capacity_difference_from_full_percent"] = 100. * (score["physical_parameters"]["Q_Ah"] / fs["physical_parameters"]["Q_Ah"] - 1.)
            row["current_SOC_difference_from_full_pp"] = 100. * (score["current_SOC_estimate"] - fs["current_SOC_estimate"])
            row["excess_full_objective"] = score["objective_full_independent"] - fs["objective_full_independent"]
        rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "results/compression_results.json")
    parser.add_argument("--timeout", type=float, default=300.)
    args = parser.parse_args()
    benchmark = ROOT / "build/scm_estimator_benchmark"
    selected_binary = args.binary or (benchmark if benchmark.is_file() else ROOT / "build/scm_estimator")
    manifest = json.loads((ROOT / "data/manifest.json").read_text())
    cases = []
    for cell in ("cell_a", "cell_b"):
        candidates = [c for c in manifest["cases"] if c["cell"] == cell]
        case = min(candidates, key=lambda c: c["seed"])
        if case["n_samples"] != 73500 or case["duration_s"] != 2100.:
            raise ValueError("This bounded comparison requires exactly the final 2100 s/73500 sample prefix")
        cases.append(case)
    source_paths = ("src/scm_estimator.c", "src/scm_features.c", "include/scm_features.h",
                    "src/scm_model.c", "include/scm_model.h", "tools/validate.py", "tools/run_compression.py")
    document = {
        "schema": "scm_compression_supplement_35hz_v1", "started_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Bounded supplemental six-fit final-prefix comparison; the main chronological campaign uses full retained history.",
        "sampling_Hz": 35, "duration_s": 2100, "starts": 3, "max_iterations": 120,
        "nominal_initial_theta": NOMINAL_THETA,
        "initial_policy": "Same explicit fixed nominal initialization for every case/method, plus identical C nominal restarts. No warm start from a future/full fit.",
        "truth_policy": "Truth is used only by existing independent validate.assess_result after C estimation, never for initialization, bases, centering, or fitting.",
        "binary_source_path": str(selected_binary),
        "source_inspection_sha256": {p: sha256(ROOT / p) for p in source_paths},
        "source_inspection_note": "Hashes identify inspected source and scoring files; the retained executable hash independently identifies the actual program run.",
        "representation": {
            "scope": "Disjoint event-local blocks split on any current or dt change; one global candidate/state path is propagated across all blocks without resets.",
            "tangent": "One fixed nominal nonlinear anchor; block basis contains a constant direction, all linear-amplitude design columns, and outer sensitivities at fixed nominal amplitudes.",
            "hybrid": "Five fixed prior nonlinear anchors; same columns at every anchor plus each anchor's predicted-voltage difference from anchor0.",
            "center": "Anchor0 voltage prediction from the observed input history and fixed nominal parameters; independent of observed voltages and true parameters.",
            "basis_orthogonalization": "Two-pass modified Gram-Schmidt; relative threshold1e-9, absolute threshold1e-11; explicit basis arrays retained.",
            "nominal_alpha_3RC": [.12, .2, .2, .2, .025, 0., 0., 0., .005],
            "conditional_information_property": "In exact arithmetic without column truncation, orthonormal projection preserves all Gaussian likelihood ratios among means in the retained affine span under known common iid covariance. Including anchor mean differences and every anchor design matrix extends this to the union of the retained nonlinear-anchor affine-amplitude families. Tangent columns preserve first-order changes at the nominal amplitude vectors.",
            "numerical_qualification": "Current QR discards directions at stated tolerances, so exact-span statements require their residual/error allowance; orthogonality and maximum discarded-column norm are reported.",
            "nonlinear_limit": "No guarantee for arbitrary nonlinear parameter points, later basis relocation, unknown covariance, unmodelled dynamics, or source revisions. Similar point fits do not establish global identification or future-equivalent history compression.",
            "memory_limit": "The program still retains original samples, explicit per-block bases, a centering vector, and derivative workspace. Observation-payload compression is not complete estimator memory compression or a bounded-memory encoder.",
            "execution_limit": "Each candidate still replays all raw input samples. This comparison is batch final-prefix estimation, not proof of online basis maintenance at35Hz or Cortex-M23 feasibility.",
        },
        "timing_scope": "C elapsed_cpu_s measures fitting; basis_seconds measures basis construction. Their sum is reported. Process wall also includes input parsing and JSON output and may reflect host contention; no MCU latency/energy inference.",
        "memory_scope": "C-reported requested allocations, not RSS, allocator overhead or stack high-water.",
        "records": [], "summary_rows": [],
    }
    with tempfile.TemporaryDirectory(prefix="scm_compression_binary_") as directory:
        private = Path(directory) / "scm_estimator"
        first = selected_binary.read_bytes()
        second = selected_binary.read_bytes()
        if first != second:
            raise RuntimeError("Executable changed while taking the snapshot; rerun after build completes")
        private.write_bytes(first); private.chmod(0o700)
        expected_hash = hashlib.sha256(first).hexdigest()
        document["executable_sha256"] = expected_hash
        document["private_binary_snapshot"] = True
        save(args.output, document)
        for case in cases:
            data_path = ROOT / "data" / case["csv"]
            if sha256(data_path) != case["sha256"]:
                raise ValueError("Input hash mismatch")
            trace = np.loadtxt(data_path, delimiter=",", skiprows=1)
            if trace.shape != (73500, 4) or not np.isfinite(trace).all():
                raise ValueError("Invalid final-prefix data matrix")
            if not np.array_equal(trace[:, 0], np.arange(len(trace))):
                raise ValueError("Invalid sample index sequence")
            event_count = 1 + int(np.count_nonzero((trace[1:, 1] != trace[:-1, 1]) | (trace[1:, 2] != trace[:-1, 2])))
            for method in METHODS:
                record = {"case_id": case["case_id"], "cell": case["cell"], "seed": case["seed"],
                          "method": method, "data_sha256": case["sha256"], "observed_event_blocks": event_count,
                          "nominal_initial_theta": NOMINAL_THETA}
                command = [str(private), "--data", str(data_path), "--case", case["case_id"],
                           "--method", method, "--modes", "3", "--starts", "3", "--max-iter", "120",
                           "--sigma", ".001", "--prefix", "73500", "--initial",
                           ",".join(format(x, ".17g") for x in NOMINAL_THETA)]
                record["command"] = command
                begin = time.perf_counter()
                try:
                    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=args.timeout)
                    record.update(returncode=completed.returncode, stderr=completed.stderr, process_wall_s=time.perf_counter()-begin)
                    if completed.returncode != 0:
                        record["stdout"] = completed.stdout
                    else:
                        fit = json.loads(completed.stdout)
                        if fit["samples"] != 73500 or fit["method"] != method or fit["case_id"] != case["case_id"]:
                            raise ValueError("Estimator output identity mismatch")
                        record["result"] = fit
                        record["scores"] = score_result(fit, case["truth"], trace[:, 1], trace[:, 2], trace[:, 3])
                except (OSError, subprocess.TimeoutExpired, ValueError, KeyError) as exc:
                    record.setdefault("returncode", None)
                    record.update(error=repr(exc), process_wall_s=time.perf_counter()-begin)
                document["records"].append(record)
                document["summary_rows"] = summarize(document["records"])
                save(args.output, document)
                print(json.dumps(json_safe(document["summary_rows"][-1]), allow_nan=False), flush=True)
        document["private_executable_unchanged"] = sha256(private) == expected_hash
    document["finished_utc"] = datetime.now(timezone.utc).isoformat()
    document["operational_failures"] = sum(r.get("returncode") != 0 or "error" in r for r in document["records"])
    document["nonconverged_selected_fits"] = sum(r.get("result", {}).get("status", 1) != 0 for r in document["records"])
    save(args.output, document)


if __name__ == "__main__":
    main()
