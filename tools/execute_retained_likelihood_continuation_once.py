#!/usr/bin/env python3
"""One outer observer for the separately frozen saved-block continuation."""
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
    output = root / EXP / "continuation_process"
    output.mkdir(exist_ok=False)
    old_path = root / EXP / "execution_process/receipt.json"
    old_identity = common.digest(old_path)
    old = common.strict_json(old_path.read_bytes())
    common.require(old["status"] == "failed" and old["process"]["exit_code"] == 1
                   and not old["process"]["resource_violations"] and not old["process"]["output_truncated"],
                   "Original closure is not eligible for the separately reviewed continuation")
    previous = old["process"]
    cpu_remaining = 30. - previous["CPU_total_s"]
    wall_remaining = 60. - previous["wall_s_through_wait4"]
    common.require(cpu_remaining > 0. and wall_remaining > 0., "No cumulative execution budget remains")
    source = Path(__file__).resolve()
    source_before = common.digest(source)
    command = [str(Path(sys.executable).resolve()), "-B", str(root / "tools/continue_retained_likelihood_replacement.py"),
               "--root", str(root), "--evidence-root", str(Path(args.evidence_root).resolve()),
               "--source-revision", args.source_revision]
    limits = {"probe_CPU_s_max": cpu_remaining, "probe_wall_s_max": wall_remaining,
              "probe_address_space_bytes_max": 1073741824, "probe_peak_RSS_bytes_max": 134217728,
              "probe_output_bytes_max": 524288, "supervisor_peak_RSS_bytes_max": 134217728}
    common.write_new_json(output / "started.json", {"schema": "mumble_retained_continuation_outer_start_v1",
        "utc": datetime.now(timezone.utc).isoformat(), "command": command, "source": source_before,
        "original_outer_receipt": {"path": str(old_path.relative_to(root)), **old_identity},
        "continuation_invocations": 1, "further_retries": 0, "remaining_limits": limits}, 65536)
    started = time.monotonic()
    process = common.supervise(command, output, limits)
    process["RSS_method"] = "wait4 high-water statistic for the continuation supervisor/descendants; not summed simultaneous memory"
    process["CPU_method"] = "Exact wait4 CPU includes continuation supervisor and its waited descendants/bookkeeping"
    (output / "raw_probe.json").rename(output / "stdout.json")
    (output / "probe.stderr").rename(output / "stderr.txt")
    errors = []
    if process["exit_code"] != 0 or process["resource_violations"] or process["output_truncated"]:
        errors.append("Continuation supervisor exit or whole-process resource check failed")
    if common.digest(source) != source_before or common.digest(old_path) != old_identity:
        errors.append("Outer observer source or original receipt changed")
    cumulative = {"CPU_total_s": previous["CPU_total_s"] + process["CPU_total_s"],
                  "active_process_wall_s": previous["wall_s_through_wait4"] + process["wall_s_through_wait4"],
                  "maximum_wait4_peak_RSS_bytes": max(previous["peak_RSS_bytes"], process["peak_RSS_bytes"]),
                  "canonical_supervisor_invocations": 2, "repeated_anchor_passes": 0,
                  "CPU_total_s_max": 30, "active_process_wall_s_max": 60, "peak_RSS_bytes_max": 134217728}
    if cumulative["CPU_total_s"] > 30 or cumulative["active_process_wall_s"] > 60 or cumulative["maximum_wait4_peak_RSS_bytes"] > 134217728:
        errors.append("Cumulative original plus continuation process budget exceeded")
    inner_path = root / EXP / "continuation001/receipt.json"
    result_path = root / EXP / "continuation001/result.json"
    inner_identity = result_identity = None
    try:
        inner_identity, result_identity = common.digest(inner_path), common.digest(result_path)
        inner, result = common.strict_json(inner_path.read_bytes()), common.strict_json(result_path.read_bytes())
        if inner["status"] != "completed" or result["status"] != "completed" or not inner["canonical_inference_closed"]:
            errors.append("Continuation inner inference did not complete")
        if inner["source_revision"] != args.source_revision or result["source_revision"] != args.source_revision:
            errors.append("Continuation source revision differs")
        expected = {"model_passes_started": 4, "model_passes_completed": 4, "model_steps_reported": 1008000,
                    "solver_invocations_reserved": 2, "solver_started_markers": 2, "solver_results_saved": 2,
                    "repeated_anchor_passes": 0, "truth_reads": 0}
        if any(inner["cumulative_counts"].get(k) != v for k, v in expected.items()):
            errors.append("Cumulative inference count differs from the unused-work contract")
    except Exception as error:
        errors.append(type(error).__name__ + ": " + str(error))
    directories = {name: root / EXP / name for name in ("attempt001", "execution_process", "continuation001", "continuation_process")}
    byte_counts = {name: sum(p.stat().st_size for p in directory.rglob("*") if p.is_file())
                   for name, directory in directories.items()}
    receipt = {"schema": "mumble_retained_continuation_outer_receipt_v1", "status": "completed" if not errors else "failed",
        "errors": errors, "source_revision": args.source_revision, "continuation_process_finished": True,
        "continuation_invocations": 1, "further_retries": 0, "truth_reads": 0, "model_calls": 0, "optimizer_calls": 0,
        "source": source_before, "process": process, "cumulative_resources": cumulative,
        "original_outer_receipt": {"path": str(old_path.relative_to(root)), **old_identity},
        "inner_receipt": inner_identity, "inner_result": result_identity,
        "stdout": common.digest(output / "stdout.json"), "stderr": common.digest(output / "stderr.txt"),
        "directory_bytes_before_outer_receipt": byte_counts,
        "all_closed_output_bytes_including_outer_receipt": 0, "all_closed_output_bytes_max": 2097152,
        "outer_bookkeeping_wall_s_before_receipt": time.monotonic() - started,
        "outer_own_peak_RSS_bytes": common.own_peak_bytes(),
        "scope": "Sum of two whole-supervisor wait4 CPU/active wall observations; excludes intervening source work. Original parity failure remains failed. No model call is repeated, no truth is read, and failed cumulative closure vetoes reporting."}
    for _ in range(12):
        total = sum(byte_counts.values()) + len((json.dumps(receipt, indent=2, allow_nan=False) + "\n").encode())
        if total > 2097152 and "Cumulative output byte cap exceeded" not in errors:
            errors.append("Cumulative output byte cap exceeded"); receipt["status"] = "failed"
        if receipt["all_closed_output_bytes_including_outer_receipt"] == total:
            break
        receipt["all_closed_output_bytes_including_outer_receipt"] = total
    common.write_new_json(output / "receipt.json", receipt, 65536)
    print(json.dumps({"status": receipt["status"], "receipt": str(output / "receipt.json"),
                      "process": process, "cumulative_resources": cumulative, "errors": errors}, allow_nan=False))
    return 0 if receipt["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
