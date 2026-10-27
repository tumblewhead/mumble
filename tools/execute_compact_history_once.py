#!/usr/bin/env python3
"""Exclusive outer observer for the complete compact-history process tree."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
EXP = "experiments/compact_nonlinear_history_001"


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate executable-receipt key")
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
    if root != ROOT:
        raise ValueError("Wrong canonical source root")
    relative = Path(args.executable_receipt)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Unsafe executable-receipt path")
    executable_path = root / relative
    executable = json.loads(executable_path.read_bytes(), object_pairs_hook=_pairs)
    if executable["schema"] != "mumble_compact_nonlinear_history_executable_receipt_v1" or \
       executable["status"] != "qualified_before_canonical_invocation" or \
       executable["source_revision"] != args.source_revision:
        raise ValueError("Executable receipt does not authorize this source")
    # Bind the imported runner and this observer before loading any helper.
    for name in ("tools/run_compact_nonlinear_history.py", "tools/execute_compact_history_once.py"):
        data = (root / name).read_bytes()
        expected = executable["source_identities"][name]
        if {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()} != expected:
            raise ValueError("Outer/imported source differs: " + name)
    specification = importlib.util.spec_from_file_location("compact_history_supervisor", root / "tools/run_compact_nonlinear_history.py")
    run = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(run)
    capture = run.load_capture()
    output = root / EXP / "execution_process"
    started = time.monotonic()
    plan_identity = run.identity(root / run.PLAN)
    run.require(plan_identity["sha256"] == executable["plan_sha256"], "Outer plan binding differs")
    transaction = capture.CaptureTransaction.reserve(
        output, max_bytes=run.LIMITS["child_capture_bytes"],
        context={"schema": run.SCHEMA, "kind": "outer_capture",
                 "source_revision": args.source_revision, "plan_sha256": plan_identity["sha256"],
                 "canonical_supervisor_invocations_before": 0,
                 "canonical_supervisor_invocations_after_reservation": 1, "retries": 0})
    sources = {}
    for name in ("tools/run_compact_nonlinear_history.py", "tools/execute_compact_history_once.py", "tools/capture_preservation.py"):
        run.bind(sources, root / name, executable["source_identities"][name], name)
    run.bind(sources, executable_path, run.identity(executable_path), "executable_receipt")
    command = [str(Path(sys.executable).resolve()), "-B", str(root / "tools/run_compact_nonlinear_history.py"),
               "--root", str(root), "--evidence-root", str(Path(args.evidence_root).resolve()),
               "--source-revision", args.source_revision, "--executable-receipt", args.executable_receipt]
    bounds = {"CPU_s": run.LIMITS["CPU_s"], "wall_s": run.LIMITS["wall_s"],
              "RSS_bytes": run.LIMITS["RSS_bytes"], "AS_bytes": run.LIMITS["AS_bytes"],
              "capture_bytes": run.LIMITS["child_capture_bytes"]}
    run.write_json(output / "launch.json",
                   {"schema": run.SCHEMA, "kind": "outer_launch", "command": command,
                    "source_revision": args.source_revision, "plan_sha256": plan_identity["sha256"],
                    "source_bindings": list(sources.values()), "bounds": bounds,
                    "canonical_supervisor_invocations": 1, "retries": 0})
    process, inner_identity, result_identity = None, None, None
    errors = []
    attempt = root / EXP / "attempt001"
    try:
        process = run.supervise_capture(command, transaction, bounds)
        process["CPU_scope"] = "Exact wait4 of canonical supervisor, including its waited children and final inner closure"
        run.write_json(output / "resources.json", process)
        run.valid_process(process)
        stdout = run.strict_json(capture.load_verified(output, process["capture_commit_identity"]))
        inner = run.read_json(attempt / "receipt.json")
        result = run.read_json(attempt / "result.json")
        inner_identity = run.identity(attempt / "receipt.json")
        result_identity = run.identity(attempt / "result.json")
        run.require(inner["status"] == result["status"] == stdout["status"] == "completed" and
                    inner["schema"] == result["schema"] == stdout["schema"] == run.SCHEMA and
                    inner["canonical_inference_closed"] is True and
                    inner["source_revision"] == result["source_revision"] == args.source_revision and
                    inner["plan_sha256"] == result["plan_sha256"] == plan_identity["sha256"],
                    "Inner canonical sequence lacks a successful matching closure")
        run.validate_closed_attempt(attempt, inner, result)
        run.require(stdout["counts"] == inner["counts"] and stdout["receipt"] == inner_identity and
                    stdout["result"] == result_identity, "Canonical stdout binding differs")
    except Exception as error:
        errors.append({"type": type(error).__name__, "message": str(error)})
    try:
        run.rehash(sources)
        run.require(run.identity(root / run.PLAN) == plan_identity, "Plan changed during canonical process")
        run.require(run.own_peak_bytes() <= run.LIMITS["RSS_bytes"], "Outer observer RSS cap")
        if process is not None and process["capture_commit_identity"] is not None:
            capture.load_verified(output, process["capture_commit_identity"])
    except Exception as error:
        errors.append({"type": type(error).__name__, "message": str(error)})
    inner_files = run.manifest(attempt) if attempt.exists() else {}
    inner_bytes = sum(row["bytes"] for row in inner_files.values())
    inner_identity = inner_files.get("receipt.json")
    result_identity = inner_files.get("result.json")
    files = run.manifest(output)
    receipt = {"schema": run.SCHEMA, "kind": "outer_receipt", "status": "failed" if errors else "completed",
               "source_revision": args.source_revision, "plan_sha256": plan_identity["sha256"],
               "canonical_process_finished": process is not None,
               "canonical_supervisor_invocations": 1, "retries": 0, "source_bindings": list(sources.values()),
               "process": process, "errors": errors, "inner_receipt": inner_identity,
               "inner_result": result_identity, "inner_closed_bytes": inner_bytes, "files": files,
               "closed_output_bytes_including_receipt": 0, "all_closed_output_bytes": 0,
               "all_closed_output_bytes_max": run.LIMITS["output_bytes"],
               "outer_own_peak_RSS_bytes": run.own_peak_bytes(),
               "outer_bookkeeping_wall_s_before_receipt": time.monotonic() - started,
               "model_calls": 0, "prior_evaluations": 0, "truth_reads": 0,
               "scope": "One exact wait4 for the complete canonical supervisor/children/inner closure. Outer bookkeeping reported separately. Both original and independent capture remain required; failed closure never retries or silently recovers."}
    for _ in range(24):
        own = sum(row["bytes"] for row in files.values()) + len(run.encode_json(receipt))
        combined = inner_bytes + own
        if combined > run.LIMITS["output_bytes"] and not any(row["message"] == "Whole-run output cap" for row in errors):
            errors.append({"type": "ResourceFailure", "message": "Whole-run output cap"})
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
