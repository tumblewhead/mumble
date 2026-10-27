#!/usr/bin/env python3
"""Close whole-process resources around exactly one canonical supervisor call.

This outer observer performs no model, optimizer, observation or truth work.
Its exclusive output reservation is separate from the immutable inner attempt.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
import run_conditional_belief_probe as common

EXP = "experiments/retained_likelihood_replacement_001"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--source-revision", required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    output = root / EXP / "execution_process"
    output.mkdir(exist_ok=False)
    source = Path(__file__).resolve()
    source_before = common.digest(source)
    command = [str(Path(sys.executable).resolve()), "-B", str(root / "tools/run_retained_likelihood_replacement.py"),
               "--root", str(root), "--evidence-root", str(Path(args.evidence_root).resolve()),
               "--source-revision", args.source_revision]
    limits = {"probe_CPU_s_max": 30, "probe_wall_s_max": 60,
              "probe_address_space_bytes_max": 1073741824,
              "probe_peak_RSS_bytes_max": 134217728, "probe_output_bytes_max": 524288,
              "supervisor_peak_RSS_bytes_max": 134217728}
    common.write_new_json(output / "started.json", {"schema": "mumble_retained_replacement_outer_start_v1",
        "utc": datetime.now(timezone.utc).isoformat(), "command": command, "source": source_before,
        "canonical_supervisor_invocations": 1, "retries": 0, "limits": limits}, 65536)
    started = time.monotonic()
    process = common.supervise(command, output, limits)
    process["RSS_method"] = "wait4 high-water RSS for the canonical supervisor/descendant accounting; not summed simultaneous process-tree memory"
    process["CPU_method"] = "wait4 CPU for the canonical supervisor including its waited descendants and git bookkeeping"
    (output / "raw_probe.json").rename(output / "stdout.json")
    (output / "probe.stderr").rename(output / "stderr.txt")
    source_after = common.digest(source)
    errors = []
    if process["exit_code"] != 0 or process["resource_violations"] or process["output_truncated"]:
        errors.append("Canonical supervisor exit or whole-process resource check failed")
    if source_before != source_after:
        errors.append("Outer observer source changed")
    inner_path = root / EXP / "attempt001/receipt.json"
    result_path = root / EXP / "attempt001/result.json"
    inner_identity = result_identity = None
    try:
        inner_identity, result_identity = common.digest(inner_path), common.digest(result_path)
        inner = common.strict_json(inner_path.read_bytes())
        result = common.strict_json(result_path.read_bytes())
        if inner["status"] != "completed" or result["status"] != "completed" or not inner["canonical_inference_closed"]:
            errors.append("Inner inference did not complete successfully")
        if inner["source_revision"] != args.source_revision or result["source_revision"] != args.source_revision:
            errors.append("Inner source revision differs")
    except Exception as error:
        errors.append(type(error).__name__ + ": " + str(error))
    attempt_bytes = sum(path.stat().st_size for path in (root / EXP / "attempt001").rglob("*") if path.is_file())
    observer_bytes_before_receipt = sum(path.stat().st_size for path in output.iterdir() if path.is_file())
    receipt = {"schema": "mumble_retained_replacement_outer_receipt_v1",
        "status": "completed" if not errors else "failed", "errors": errors,
        "source_revision": args.source_revision, "canonical_supervisor_invocations": 1,
        "canonical_process_finished": True, "retries": 0, "truth_reads": 0,
        "model_calls": 0, "optimizer_calls": 0, "source": source_after,
        "process": process, "inner_receipt": inner_identity, "inner_result": result_identity,
        "stdout": common.digest(output / "stdout.json"), "stderr": common.digest(output / "stderr.txt"),
        "attempt_closed_bytes": attempt_bytes,
        "observer_closed_bytes_before_receipt": observer_bytes_before_receipt,
        "canonical_closed_output_bytes_including_outer_receipt": 0,
        "canonical_closed_output_bytes_max": 2097152,
        "outer_bookkeeping_wall_s_before_receipt": time.monotonic() - started,
        "outer_own_peak_RSS_bytes": common.own_peak_bytes(),
        "scope": "Exact wait4 CPU includes the canonical supervisor and its waited descendants. Child wall includes internal result/receipt close and exit. This outer observation adds no inference. A failed outer receipt vetoes result validity and post-inference truth reporting."}
    for _ in range(12):
        encoded_size = len((json.dumps(receipt, indent=2, allow_nan=False) + "\n").encode())
        total = attempt_bytes + observer_bytes_before_receipt + encoded_size
        if total > 2097152 and "Combined canonical/observer output cap exceeded" not in errors:
            errors.append("Combined canonical/observer output cap exceeded")
            receipt["status"] = "failed"
        if receipt["canonical_closed_output_bytes_including_outer_receipt"] == total:
            break
        receipt["canonical_closed_output_bytes_including_outer_receipt"] = total
    common.write_new_json(output / "receipt.json", receipt, 65536)
    print(json.dumps({"status": receipt["status"], "receipt": str(output / "receipt.json"),
                      "process": process, "errors": errors}, allow_nan=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
