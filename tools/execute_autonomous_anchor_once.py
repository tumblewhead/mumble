#!/usr/bin/env python3
"""Exclusive whole-process observer for one autonomous-anchor invocation."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
EXP = "experiments/autonomous_anchor_refinement_001"
_common_path = ROOT / "tools/run_conditional_belief_probe.py"
if hashlib.sha256(_common_path.read_bytes()).hexdigest() != "411c483c25a2578ef99feea1476ef8482ecb14c65ca0f7958c9e65f9b9f0d82a":
    raise ValueError("Qualified process supervisor changed")
import run_conditional_belief_probe as common

_spec = importlib.util.spec_from_file_location("autonomous_anchor_outer_schema", ROOT / EXP / "schema.py")
if _spec is None or _spec.loader is None:
    raise ValueError("Cannot load shared closure schema")
schema = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(schema)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--executable-receipt", default=EXP + "/executable_receipt.json")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    schema.require(root == ROOT, "Wrong source root")
    output = root / EXP / "execution_process"
    schema.reserve_directory(output)
    started = time.monotonic()
    sources = {}
    for path in (Path(__file__).resolve(), root / EXP / "schema.py", _common_path):
        schema.bind(path, schema.identity(path), sources, str(path))
    plan_identity = schema.identity(root / schema.PLAN)
    command = [str(Path(sys.executable).resolve()), "-B", str(root / "tools/run_autonomous_anchor_refinement.py"),
               "--root", str(root), "--evidence-root", str(Path(args.evidence_root).resolve()),
               "--source-revision", args.source_revision, "--executable-receipt", args.executable_receipt]
    bounds = {"probe_CPU_s_max": schema.LIMITS["CPU_total_s_max"],
              "probe_wall_s_max": schema.LIMITS["wall_total_s_max"],
              "probe_address_space_bytes_max": schema.LIMITS["child_address_space_bytes_max"],
              "probe_peak_RSS_bytes_max": schema.LIMITS["child_RSS_bytes_max"],
              "probe_output_bytes_max": schema.LIMITS["child_stdout_stderr_bytes_max"],
              "supervisor_peak_RSS_bytes_max": schema.LIMITS["supervisor_RSS_bytes_max"]}
    schema.write_json(output / "reservation.json", {
        "schema": schema.VERSION, "kind": "outer_reservation", "command": command,
        "source_revision": args.source_revision, "plan_sha256": plan_identity["sha256"],
        "source_bindings": list(sources.values()), "limits": bounds, "roles": schema.OUTER_ROLES,
        "canonical_supervisor_invocations_before": 0, "canonical_supervisor_invocations_after_reservation": 1,
        "utc": datetime.now(timezone.utc).isoformat(), "retries": 0,
    })
    process = None
    errors = []
    inner_identity = result_identity = None
    inner_bytes = None
    try:
        process = common.supervise(command, output, bounds)
        process["CPU_method"] = "Exact wait4 CPU for canonical supervisor including its waited descendants and final closure"
        process["RSS_method"] = "wait4 high-water statistic for canonical supervisor/descendants; not summed concurrent memory"
        schema.write_json(output / "resources.json", process)
        schema.require(process["child_launched"] is True and process["exit_code"] == 0 and
                       process["resource_violations"] == [] and process["output_truncated"] is False,
                       "Canonical process exit/resource failure")
        attempt = root / EXP / "attempt001"
        inner_identity = schema.identity(attempt / "receipt.json")
        result_identity = schema.identity(attempt / "result.json")
        inner = schema.read_json(attempt / "receipt.json")
        result = schema.read_json(attempt / "result.json")
        schema.require(inner["schema"] == result["schema"] == schema.VERSION and
                       inner["status"] == result["status"] == "completed" and
                       inner["canonical_inference_closed"] is True and
                       inner["source_revision"] == result["source_revision"] == args.source_revision and
                       inner["plan_sha256"] == result["plan_sha256"] == plan_identity["sha256"],
                       "Inner inference lacks a successful matching closure")
        schema.validate_manifest(attempt, inner)
        schema.validate_activity(attempt, inner, result)
        inner_bytes = inner["closed_output_bytes_including_receipt"]
        schema.rehash_bindings(inner["source_bindings"])
        schema.rehash_bindings(inner["input_bindings"])
        schema.rehash_bindings(inner["generated_bindings"])
        stdout = schema.read_json(output / schema.CAPTURE_ROLES["stdout"])
        schema.require(stdout["status"] == "completed" and stdout["counts"] == inner["counts"] and
                       stdout["stop_reason"] == result["stop_reason"], "Supervisor stdout/receipt mismatch")
    except Exception as error:
        errors.append({"type": type(error).__name__, "message": str(error)})
    try:
        schema.rehash_bindings(sources)
        schema.require(schema.identity(root / schema.PLAN) == plan_identity, "Contract changed during execution")
        schema.require(common.own_peak_bytes() <= schema.LIMITS["supervisor_RSS_bytes_max"], "Outer observer RSS cap")
    except Exception as error:
        errors.append({"type": type(error).__name__, "message": str(error)})
    attempt = root / EXP / "attempt001"
    if inner_bytes is None:
        inner_bytes = sum(row["bytes"] for row in schema.manifest(attempt).values()) if attempt.exists() else 0
    for filename, target in (("receipt.json", "inner_receipt"), ("result.json", "inner_result")):
        path = attempt / filename
        if path.exists():
            if target == "inner_receipt":
                inner_identity = schema.identity(path)
            else:
                result_identity = schema.identity(path)
    files = schema.manifest(output)
    receipt = {
        "schema": schema.VERSION, "kind": "outer_receipt", "status": "failed" if errors else "completed",
        "source_revision": args.source_revision, "plan_sha256": plan_identity["sha256"],
        "canonical_process_finished": process is not None,
        "canonical_supervisor_invocations": 1, "retries": 0, "roles": schema.OUTER_ROLES,
        "source_bindings": list(sources.values()), "process": process, "errors": errors,
        "inner_receipt": inner_identity, "inner_result": result_identity, "inner_closed_bytes": inner_bytes,
        "files": files, "closed_output_bytes_including_receipt": 0, "all_closed_output_bytes": 0,
        "all_closed_output_bytes_max": schema.LIMITS["closed_output_bytes_max"],
        "outer_own_peak_RSS_bytes": common.own_peak_bytes(),
        "outer_bookkeeping_wall_s_before_receipt": time.monotonic() - started,
        "truth_reads": 0, "model_calls": 0, "optimizer_calls": 0,
        "scope": "One complete canonical-supervisor wait4 observation, including waited descendants and inner result/receipt closure. Outer observer bookkeeping is separately reported. Raw capture names remain unchanged. Failed closure vetoes reporting; no retry.",
    }
    for _ in range(24):
        own_bytes = sum(row["bytes"] for row in files.values()) + len(schema.encode_json(receipt))
        combined = inner_bytes + own_bytes
        if combined > schema.LIMITS["closed_output_bytes_max"] and not any(row["message"] == "Whole-run output cap" for row in errors):
            errors.append({"type": "ResourceFailure", "message": "Whole-run output cap"})
            receipt["status"] = "failed"
        if receipt["closed_output_bytes_including_receipt"] == own_bytes and receipt["all_closed_output_bytes"] == combined:
            break
        receipt["closed_output_bytes_including_receipt"] = own_bytes
        receipt["all_closed_output_bytes"] = combined
    else:
        raise ValueError("Outer receipt size accounting did not stabilize")
    schema.write_json(output / "receipt.json", receipt, 2097152)
    print(schema.encode_json({"schema": schema.VERSION, "status": receipt["status"],
          "receipt": {"path": str(output / "receipt.json"), **schema.identity(output / "receipt.json")},
          "process": process, "all_closed_output_bytes": receipt["all_closed_output_bytes"],
          "errors": errors}).decode(), end="")
    return 0 if receipt["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
