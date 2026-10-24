#!/usr/bin/env python3
"""Fresh 35 Hz growing-history research campaign; C performs all fitting.

At each checkpoint the entire observed prefix is replayed with the previous
theta as one starting point. Previous measurements are not turned into an
additional prior factor. Truth is used only by independent post-fit scoring.
This is a host replay reference, not bounded-memory streaming firmware.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shlex
import statistics
import subprocess
import tempfile
import threading
import time

import numpy as np
from assess import assess_result as qualify_result
from validate import assess_result as score_result

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RESULTS = ROOT / "results"
EXE = ROOT / "build" / "scm_estimator"
CHECKPOINTS = [10, 40, 220, 400, 600, 900, 1200, 1500, 1800, 2100]
STARTS = 3
MAX_ITER = 120
SIGMA = .001
LOCK = threading.Lock()


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_hashes():
    paths = list((ROOT / "src").glob("*.c")) + list((ROOT / "include").glob("*.h"))
    paths += [ROOT / "Makefile", ROOT / "tools" / "generate_cases.py",
              ROOT / "tools" / "validate.py", ROOT / "tools" / "assess.py", Path(__file__)]
    return {str(p.relative_to(ROOT)): sha256(p) for p in sorted(paths) if p.is_file()}


def capture(command):
    try:
        p = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=15)
        return p.stdout + p.stderr
    except (OSError, subprocess.TimeoutExpired) as exc:
        return repr(exc)


def metadata(workers, section):
    return {
        "schema": "scm_c_streaming_35hz_v1", "section": section,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "executable_sha256_before": sha256(EXE), "source_sha256_before": source_hashes(),
        "data_manifest_sha256": sha256(DATA / "manifest.json"),
        "platform": platform.platform(), "machine": platform.machine(),
        "python_version": platform.python_version(), "numpy_version": np.__version__,
        "compiler": capture(shlex.split(os.environ.get("CC", "cc")) + ["--version"]),
        "build_recipe": capture(["make", "-n", "-B", "all"]),
        "case_workers": workers,
        "timing_scope": "C CPU time is per fit; process wall includes startup/CSV/fit/output and may reflect concurrent-case or other host contention. No MCU latency or energy claim.",
        "memory_scope": "C-reported requested allocations; not process RSS, allocator overhead or stack high-water measurement.",
        "truth_policy": "Physical truth is supplied only to Python scoring after C fitting; never to C initial guesses, priors, objectives or state corrections.",
        "streaming_scope": "Chronological checkpoints with growing-history replay. Previous theta is initialization only; there is no extra previous-posterior factor and no double-counted observations.",
        "assessment_scope": "Undamped local likelihood diagnostics, not a posterior or nonlinear confidence-coverage certificate. Poor numerical statuses remain in the record.",
    }


def finish_metadata(meta):
    meta["finished_utc"] = datetime.now(timezone.utc).isoformat()
    meta["executable_sha256_after"] = sha256(EXE)
    meta["source_sha256_after"] = source_hashes()
    meta["executable_unchanged"] = meta["executable_sha256_before"] == meta["executable_sha256_after"]
    meta["source_unchanged"] = meta["source_sha256_before"] == meta["source_sha256_after"]


def json_safe(value):
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def write_json(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(json_safe(document), indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def load_trace(case):
    path = DATA / case["csv"]
    if sha256(path) != case["sha256"]:
        raise ValueError(f"Input CSV hash mismatch: {path.name}")
    a = np.loadtxt(path, delimiter=",", skiprows=1)
    if a.ndim != 2 or a.shape[1] != 4 or not np.isfinite(a).all():
        raise ValueError(f"Invalid input matrix: {path.name}")
    if not np.array_equal(a[:, 0], np.arange(len(a))) or np.any(a[:, 1] < 0):
        raise ValueError(f"Invalid indices or intervals: {path.name}")
    return a


def execute(case, trace, path, n, checkpoint_s, initial, expected_hash,
            *, truth=None, start_sample=0):
    record = {k: case[k] for k in ("case_id", "cell", "seed", "history", "model_match")}
    record.update(checkpoint_s=checkpoint_s, prefix_samples=n, start_sample=start_sample,
                  input_sha256=sha256(path), result=None)
    command = [str(EXE), "--data", str(path), "--case", case["case_id"],
               "--method", "full", "--modes", "3", "--starts", str(STARTS),
               "--max-iter", str(MAX_ITER), "--sigma", format(SIGMA, ".17g"),
               "--prefix", str(n)]
    if initial is not None:
        command += ["--initial", ",".join(format(v, ".17g") for v in initial)]
    record["command"] = command
    record["initial_source"] = "nominal_starts" if initial is None else "previous_prefix_theta_only"
    record["prior_factor_added"] = False
    if sha256(EXE) != expected_hash:
        record.update(returncode=None, error="Executable changed before fit; not executed")
        return record
    start = time.perf_counter()
    try:
        p = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=180)
        record.update(returncode=p.returncode, stderr=p.stderr, process_wall_s=time.perf_counter() - start)
    except (OSError, subprocess.TimeoutExpired) as exc:
        record.update(returncode=None, error=repr(exc), process_wall_s=time.perf_counter() - start)
        return record
    if p.returncode != 0:
        record["stdout"] = p.stdout
        return record
    try:
        result = json.loads(p.stdout)
        if result["samples"] != n or result["modes"] != 3 or result["case_id"] != case["case_id"]:
            raise ValueError("Result identity or dimensions disagree with request")
        record["result"] = result
        window = trace[:n]
        record["scores"] = score_result(result, case["truth"] if truth is None else truth,
                                         window[:, 1], window[:, 2], window[:, 3], sigma=SIGMA)
        record["assessment"] = qualify_result(result)
    except (ValueError, TypeError, KeyError, FloatingPointError) as exc:
        record["assessment_or_parse_error"] = repr(exc)
        record["stdout"] = p.stdout
    return record


def progress(record):
    result = record.get("result") or {}
    scores = record.get("scores") or {}
    print(json.dumps({"case": record["case_id"], "time_s": record["checkpoint_s"],
                      "returncode": record.get("returncode"), "status": result.get("status"),
                      "C_CPU_s": result.get("elapsed_cpu_s"),
                      "current_SOC_abs_error_pp": scores.get("current_SOC_abs_error_pp"),
                      "capacity_abs_relative_error_percent": scores.get("capacity_abs_relative_error_percent")}), flush=True)


def metric_value(record, metric):
    scores = record.get("scores")
    if scores is None:
        return None
    if metric == "current_soc":
        return scores["current_SOC_abs_error_pp"]
    return abs(scores["parameter_relative_errors_percent"][metric])


def convergence(records, cases):
    metrics = ["Q_Ah", "R0", "R1", "R2", "R3", "tau1", "tau2", "tau3",
               "gamma_plus", "gamma_minus", "H", "current_soc"]
    output = []
    for case in cases:
        rows = sorted([r for r in records if r["case_id"] == case["case_id"]], key=lambda r: r["checkpoint_s"])
        all_checkpoints_present = [r["checkpoint_s"] for r in rows] == CHECKPOINTS
        for metric in metrics:
            limits = [5., 1., .5] if metric == "current_soc" else [10., 5., .5]
            for limit in limits:
                selected = None
                values = [metric_value(r, metric) for r in rows]
                for j, value in enumerate(values if all_checkpoints_present else []):
                    if value is not None and all(v is not None and v < limit for v in values[j:]):
                        selected = j
                        break
                entry = {"case_id": case["case_id"], "metric": metric, "threshold": limit,
                         "threshold_units": "SOC percentage points" if metric == "current_soc" else "absolute relative percent",
                         "criterion": "First observed checkpoint strictly below threshold at this and all later valid requested checkpoints; no missing suffix checkpoints allowed. Not a future guarantee.",
                         "numerical_status_policy": "Numerical nonconvergence is retained; truth accuracy and self-qualification are separate."}
                if selected is None:
                    entry.update(status="unresolved_missing_results" if not all_checkpoints_present or any(v is None for v in values) else "right_censored_not_reached",
                                 time_s=None, censor_time_s=rows[-1]["checkpoint_s"] if rows else None)
                else:
                    entry.update(status="observed_suffix_below_threshold", time_s=rows[selected]["checkpoint_s"],
                                 remaining_checkpoints=len(rows)-selected,
                                 optimizer_status_at_crossing=rows[selected]["result"]["status"],
                                 assessment_at_crossing=rows[selected].get("assessment", {}).get("parameters", {}).get(metric))
                output.append(entry)
    return output


def summarize(records):
    valid = [r for r in records if r.get("result")]
    scored = [r for r in records if r.get("scores")]
    final = [r for r in scored if r["checkpoint_s"] == 2100]
    return {
        "attempted_fits": len(records), "valid_fit_results": len(valid), "scored_results": len(scored),
        "operational_failures": [{"case_id": r["case_id"], "checkpoint_s": r["checkpoint_s"], "returncode": r.get("returncode")} for r in records if not r.get("result")],
        "assessment_failures": [{"case_id": r["case_id"], "checkpoint_s": r["checkpoint_s"], "error": r.get("assessment_or_parse_error")} for r in records if r.get("assessment_or_parse_error")],
        "selected_status_counts": {str(s): sum(r["result"]["status"] == s for r in valid) for s in (0,1,2)},
        "final_point_metrics": {
            "cases": len(final),
            "max_capacity_abs_relative_error_percent": max((r["scores"]["capacity_abs_relative_error_percent"] for r in final), default=None),
            "max_current_SOC_abs_error_pp": max((r["scores"]["current_SOC_abs_error_pp"] for r in final), default=None),
            "max_voltage_RMSE_mV": max((r["scores"]["voltage_rmse_mV"] for r in final), default=None),
            "median_C_CPU_s": statistics.median([r["result"]["elapsed_cpu_s"] for r in final]) if final else None,
            "max_retained_bytes": max((r["result"]["retained_bytes"] for r in final), default=None),
        },
        "max_independent_objective_discrepancy": max((r["scores"]["objective_abs_discrepancy"] for r in scored), default=None),
    }


def run_campaign(manifest, workers):
    document = {"metadata": metadata(workers,"growing_history"),
                "campaign": {"sampling_Hz":35,"checkpoints_s":CHECKPOINTS,"modes":3,
                             "method":"full","starts":STARTS,"max_iterations":MAX_ITER,
                             "cases":len(manifest["cases"])}, "records":[]}
    path = RESULTS / "streaming_results.json"
    expected_hash = document["metadata"]["executable_sha256_before"]
    write_json(path,document)

    def one_case(case):
        trace=load_trace(case);previous=None;previous_time=None
        for seconds in CHECKPOINTS:
            n=round(seconds*35)
            if n>len(trace) or not math.isclose(float(np.sum(trace[:n,1])),seconds,abs_tol=1e-6):
                raise ValueError("Checkpoint sample count does not match physical time")
            record=execute(case,trace,DATA/case["csv"],n,seconds,previous,expected_hash)
            record["warm_start_previous_checkpoint_s"]=previous_time
            if record.get("result"):
                previous=record["result"]["theta"];previous_time=seconds
            with LOCK:
                document["records"].append(record)
                write_json(path,document)
                progress(record)
        return case["case_id"]

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(one_case,case):case["case_id"] for case in manifest["cases"]}
        for future in as_completed(futures):
            try:future.result()
            except Exception as exc:
                with LOCK:
                    document.setdefault("case_runner_errors",[]).append({"case_id":futures[future],"error":repr(exc)})
                    write_json(path,document)
    order={case["case_id"]:i for i,case in enumerate(manifest["cases"])}
    document["records"].sort(key=lambda r:(order[r["case_id"]],r["checkpoint_s"]))
    document["summary"]=summarize(document["records"])
    document["convergence"]=convergence(document["records"],manifest["cases"])
    finish_metadata(document["metadata"])
    write_json(path,document)
    return document


def run_tail(manifest,campaign):
    case=manifest["cases"][0];trace=load_trace(case);start=round(1800*35);tail=trace[start:].copy()
    tail[:,0]=np.arange(len(tail))
    if not np.all(tail[:,2]==.003):raise ValueError("Quiet-tail control is not constant3mA")
    document={"metadata":metadata(1,"tail_only_control"),
              "control":{"source_case_id":case["case_id"],"global_window_s":[1800,2100],
                         "start_sample":start,"samples":len(tail),"current_A":.003,
                         "semantics":"Same final300seconds of observations, reindexed into a separate inference window with unknown entering states. No earlier observations or previous estimate supplied.",
                         "truth_policy":"weak_tail_truth_start is used only for scoring the separate window."},"records":[]}
    with tempfile.TemporaryDirectory(prefix="scm_tail_control_") as folder:
        csv_path=Path(folder)/"tail.csv"
        np.savetxt(csv_path,tail,delimiter=",",header="sample_index,dt_s,current_A,voltage_V",comments="",fmt=["%d","%.17g","%.17g","%.17g"])
        record=execute(case,tail,csv_path,len(tail),2100,None,document["metadata"]["executable_sha256_before"],
                       truth=case["weak_tail_truth_start"],start_sample=start)
        record["window_start_index"]=start
        record["window_duration_s"]=300
        record["initial_source"]="nominal_starts_with_unknown_entering_states"
        document["records"].append(record)
        progress(record)
    reference=next((r for r in campaign["records"] if r["case_id"]==case["case_id"] and r["checkpoint_s"]==2100),None)
    if reference:
        document["full_history_reference"]={key:reference.get(key) for key in("case_id","checkpoint_s","result","scores","assessment")}
    document["summary"]=summarize(document["records"])
    finish_metadata(document["metadata"])
    write_json(RESULTS/"tail_only_result.json",document)
    return document


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers",type=int,default=3,choices=(1,2,3))
    parser.add_argument("--section",choices=("all","campaign","tail"),default="all")
    args=parser.parse_args()
    manifest=json.loads((DATA/"manifest.json").read_text())
    if manifest["sampling_Hz"]!=35 or manifest["checkpoints_s"]!=CHECKPOINTS:
        parser.error("Unexpected data sampling or checkpoint manifest")
    documents=[]
    if args.section in("all","campaign"):
        campaign=run_campaign(manifest,args.workers);documents.append(campaign)
    else:
        campaign=json.loads((RESULTS/"streaming_results.json").read_text())
        if campaign["metadata"]["executable_sha256_after"]!=sha256(EXE):
            parser.error("Stored campaign used a different executable")
    if args.section in("all","tail"):documents.append(run_tail(manifest,campaign))
    bad=any(d["summary"]["operational_failures"] or d["summary"]["assessment_failures"]
            or d.get("case_runner_errors") or not d["metadata"]["executable_unchanged"]
            or not d["metadata"]["source_unchanged"] for d in documents)
    print(json.dumps({"completed_sections":[d["metadata"]["section"] for d in documents],"all_checks_ok":not bad}),flush=True)
    return 1 if bad else 0


if __name__=="__main__":raise SystemExit(main())
