#!/usr/bin/env python3
"""Exclusive whole-process observer; no model, optimizer, prior or truth API."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import resource
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
EXP = "experiments/live_anchor_integration_001"


def pairs(items):
    result = {}
    for key, value in items:
        if key in result: raise ValueError("Duplicate receipt key")
        result[key] = value
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--executable-receipt", default=EXP + "/executable_receipt.json")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if root != ROOT: raise ValueError("Wrong source root")
    relative = Path(args.executable_receipt)
    if relative.is_absolute() or ".." in relative.parts: raise ValueError("Unsafe executable receipt")
    executable_path = root / relative
    executable = json.loads(executable_path.read_bytes(), object_pairs_hook=pairs)
    if executable["schema"] != "mumble_live_anchor_integration_executable_receipt_v1" or \
       executable["status"] != "qualified_before_canonical_invocation" or \
       executable["source_revision"] != args.source_revision:
        raise ValueError("Executable receipt does not bind the requested source")
    for name in ("tools/run_live_anchor_integration.py", "tools/execute_live_anchor_integration_once.py"):
        data = (root / name).read_bytes()
        if {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()} != executable["source_identities"][name]:
            raise ValueError("Unbound observer/runner source")
    spec = importlib.util.spec_from_file_location("live_anchor_runner", root / "tools/run_live_anchor_integration.py")
    run = importlib.util.module_from_spec(spec); spec.loader.exec_module(run)
    common, capture = run.common, run.common.load_capture()
    started = time.monotonic()
    own_start = resource.getrusage(resource.RUSAGE_SELF)
    plan_identity = run.identity(root / run.PLAN)
    common.require(plan_identity["sha256"] == executable["host_plan_sha256"], "Outer host-plan binding differs")
    run.validate_plan(run.read_json(root / run.PLAN))
    output = root / EXP / "execution_process"
    transaction = capture.CaptureTransaction.reserve(output, max_bytes=run.LIMITS["outer_capture_bytes"],
        context={"schema": run.SCHEMA, "role": "outer_capture", "source_revision": args.source_revision,
                 "host_plan": plan_identity, "canonical_supervisor_invocations": 1, "retries": 0})
    sources = {}
    for name in ("tools/run_live_anchor_integration.py", "tools/execute_live_anchor_integration_once.py",
                 run.COMMON, run.CAPTURE, run.PLAN):
        common.bind(sources, root / name, executable["source_identities"][name], name)
    common.bind(sources, executable_path, run.identity(executable_path), "executable_receipt")
    command = [str(Path(sys.executable).resolve()), "-B", str(root / "tools/run_live_anchor_integration.py"),
               "--root", str(root), "--evidence-root", str(Path(args.evidence_root).resolve()),
               "--source-revision", args.source_revision, "--executable-receipt", args.executable_receipt]
    # The helper couples inherited RLIMIT_FSIZE and its combined-stream bound.
    #64 MiB is required for the inner raw trace. The outer transaction itself
    # enforces256 KiB stdout; combined outer stdout/stderr is checked on close.
    bounds = {key: run.LIMITS[key] for key in ("CPU_s", "wall_s", "RSS_bytes", "AS_bytes", "capture_bytes")}
    run.write_json(output / "launch.json", {"schema": run.SCHEMA, "command": command,
        "source_revision": args.source_revision, "host_plan": plan_identity,
        "source_bindings": list(sources.values()), "bounds": bounds,
        "outer_capture_stdout_limit_bytes": run.LIMITS["outer_capture_bytes"],
        "outer_combined_postclosure_limit_bytes": run.LIMITS["outer_capture_bytes"],
        "canonical_supervisor_invocations": 1, "retries": 0})
    process, inner_identity, result_identity = None, None, None
    errors = []
    attempt = root / EXP / "attempt001"
    try:
        process = common.supervise_capture(command, transaction, bounds)
        process["CPU_scope"] = "Exact wait4 of canonical supervisor including its waited child and final inner closure"
        run.write_json(output / "resources.json", process)
        common.valid_process(process)
        common.require(sum(process["stdout_stderr_bytes_written"].values()) <= run.LIMITS["outer_capture_bytes"],
                       "Outer combined stdout/stderr closure limit")
        stdout = common.strict_json(capture.load_verified(output, process["capture_commit_identity"]))
        inner = run.read_json(attempt / "receipt.json")
        result = run.read_json(attempt / "result.json")
        inner_identity = run.identity(attempt / "receipt.json")
        result_identity = run.identity(attempt / "result.json")
        common.require(inner["status"] == result["status"] == stdout["status"] == "completed" and
                       inner["source_revision"] == result["source_revision"] == args.source_revision and
                       inner["host_plan"] == result["host_plan"] == plan_identity,
                       "Inner source/plan/status closure differs")
        run.validate_closed_attempt(attempt, inner, result)
        common.require(stdout["schema"] == run.SCHEMA and stdout["counts"] == inner["counts"] and
                       stdout["receipt"] == inner_identity and stdout["result"] == result_identity,
                       "Canonical stdout does not bind closed inner files")
    except Exception as error:
        errors.append({"type": type(error).__name__, "message": str(error)[:2048]})
    try:
        common.rehash(sources)
        common.require(run.identity(root / run.PLAN) == plan_identity, "Plan changed")
        if process and process["capture_commit_identity"]:
            capture.load_verified(output, process["capture_commit_identity"])
        common.require(common.own_peak_bytes() <= run.LIMITS["RSS_bytes"], "Outer RSS limit")
        if process:
            common.require(sum(process["stdout_stderr_bytes_written"].values()) <= run.LIMITS["outer_capture_bytes"],
                           "Outer combined stdout/stderr closure limit")
    except Exception as error:
        errors.append({"type": type(error).__name__, "message": str(error)[:2048]})
    own_now = resource.getrusage(resource.RUSAGE_SELF)
    own_cpu = own_now.ru_utime + own_now.ru_stime - own_start.ru_utime - own_start.ru_stime
    total_cpu = own_cpu + (process["CPU_total_s"] if process else 0.)
    wall = time.monotonic() - started
    if total_cpu > run.LIMITS["CPU_s"] or wall > run.LIMITS["wall_s"]:
        errors.append({"type": "ResourceFailure", "message": "Whole-run CPU/wall including outer bookkeeping"})
    inner_files = run.manifest(attempt) if attempt.exists() else {}
    inner_bytes = sum(x["bytes"] for x in inner_files.values())
    inner_identity, result_identity = inner_files.get("receipt.json"), inner_files.get("result.json")
    files = run.manifest(output)
    receipt = {"schema": run.SCHEMA, "kind": "outer_receipt", "status": "failed" if errors else "completed",
        "source_revision": args.source_revision, "host_plan": plan_identity,
        "canonical_process_finished": process is not None, "canonical_supervisor_invocations": 1, "retries": 0,
        "process": process, "errors": errors, "source_bindings": list(sources.values()),
        "inner_receipt": inner_identity, "inner_result": result_identity, "inner_closed_bytes": inner_bytes,
        "files": files, "closed_output_bytes_including_receipt": 0, "all_closed_output_bytes": 0,
        "all_closed_output_bytes_max": run.LIMITS["output_bytes"],
        "outer_CPU_s_before_receipt": own_cpu, "CPU_total_including_outer_before_receipt_s": total_cpu,
        "outer_own_peak_RSS_bytes": common.own_peak_bytes(), "wall_total_before_receipt_s": wall,
        "outer_output_limit_scope": "Live outer stdout256 KiB; inherited file/combined helper bound64 MiB; combined outer stdout/stderr256 KiB verified at closure.",
        "model_calls": 0, "prior_evaluations": 0, "truth_reads": 0,
        "scope": "Complete inner process tree is measured by exact wait4; outer metadata bookkeeping is reported separately through the pre-receipt snapshot. Both original and independent captures remain required; failed status is never retried or silently repaired."}
    for _ in range(24):
        own = sum(x["bytes"] for x in files.values()) + len(run.encode_json(receipt))
        combined = inner_bytes + own
        if combined > run.LIMITS["output_bytes"] and not any(x["message"] == "Whole-run closed output cap" for x in errors):
            errors.append({"type": "ResourceFailure", "message": "Whole-run closed output cap"})
            receipt["status"] = "failed"
        if receipt["closed_output_bytes_including_receipt"] == own and receipt["all_closed_output_bytes"] == combined:
            break
        receipt["closed_output_bytes_including_receipt"] = own
        receipt["all_closed_output_bytes"] = combined
    else:
        raise ValueError("Outer receipt byte accounting did not stabilize")
    run.write_json(output / "receipt.json", receipt)
    print(run.encode_json({"schema": run.SCHEMA, "status": receipt["status"],
          "receipt": {"path": str(output / "receipt.json"), **run.identity(output / "receipt.json")},
          "process": process, "all_closed_output_bytes": receipt["all_closed_output_bytes"],
          "errors": errors}).decode(), end="")
    return 0 if receipt["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
