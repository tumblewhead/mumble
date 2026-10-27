#!/usr/bin/env python3
"""One frozen, fabricated ADC transport/calibration qualification; no model imports."""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import resource
import shutil
import signal
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[3]
QUAL = ROOT / "experiments/live_anchor_bootstrap_001/qualification"
PLAN = QUAL / "adc12_plan.json"
FREEZE = QUAL / "adc12_source_freeze.json"
ATTEMPT = QUAL / "adc12_attempt001"


def identity(path):
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Expected regular non-symlink file: {path}")
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            h.update(block)
    return {"bytes": path.stat().st_size, "sha256": h.hexdigest()}


def strict_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate key: {key}")
            result[key] = value
        return result
    def reject(value):
        raise ValueError(f"Nonfinite JSON constant: {value}")
    return json.loads(Path(path).read_text(), object_pairs_hook=pairs, parse_constant=reject)


def encode(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_new(path, value):
    data = value if isinstance(value, bytes) else encode(value)
    with Path(path).open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    fsync_dir(Path(path).parent)


def bindings():
    plan = strict_json(PLAN)
    compiler = Path(shutil.which("cc") or "").resolve(strict=True)
    python = Path(sys.executable).resolve(strict=True)
    source_paths = [PLAN.relative_to(ROOT).as_posix(), *plan["sources"]]
    return {
        "schema": "mumble_adc12_source_freeze_v1",
        "status": "frozen_before_compile_and_test",
        "base_revision": plan["base_revision"],
        "sources": {name: identity(ROOT / name) for name in source_paths},
        "compiler": {"path": str(compiler), **identity(compiler)},
        "python": {"path": str(python), "version": sys.version, **identity(python)},
        "platform": platform.platform(),
        "activity": {"compile_invocations": 0, "test_invocations": 0,
                     "model_calls": 0, "prior_calls": 0, "optimizer_calls": 0,
                     "observation_reads": 0, "truth_reads": 0},
    }


def verify_bindings(frozen):
    for name, expected in frozen["sources"].items():
        if identity(ROOT / name) != expected:
            raise ValueError(f"Source changed: {name}")
    for role in ("compiler", "python"):
        expected = frozen[role]
        if identity(expected["path"]) != {k: expected[k] for k in ("bytes", "sha256")}:
            raise ValueError(f"Executable changed: {role}")


def child(name, argv, caps, counters):
    directory = ATTEMPT / name
    directory.mkdir()
    fsync_dir(ATTEMPT)
    reservation = {
        "schema": "mumble_adc12_child_reservation_v1", "role": name,
        "argv": argv, "caps": caps, "child_launched": False,
        "expected_prior_counts": dict(counters),
    }
    write_new(directory / "reservation.json", reservation)
    counters[f"{name}_reserved"] += 1
    stdout = directory / "stdout.txt"
    stderr = directory / "stderr.txt"
    started = time.monotonic()
    timed_out = False
    status = None
    usage = None

    def limits():
        resource.setrlimit(resource.RLIMIT_CPU, (caps["CPU_s"], caps["CPU_s"]))
        resource.setrlimit(resource.RLIMIT_AS, (caps["AS_bytes"], caps["AS_bytes"]))
        resource.setrlimit(resource.RLIMIT_FSIZE, (caps["file_bytes"], caps["file_bytes"]))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    with stdout.open("xb") as out, stderr.open("xb") as err:
        process = subprocess.Popen(argv, cwd=ROOT, stdout=out, stderr=err,
                                   stdin=subprocess.DEVNULL, preexec_fn=limits,
                                   start_new_session=True, close_fds=True)
        counters[f"{name}_launched"] += 1
        while True:
            pid, status, usage = os.wait4(process.pid, os.WNOHANG)
            if pid:
                break
            if time.monotonic() - started > caps["wall_s"]:
                timed_out = True
                os.killpg(process.pid, signal.SIGKILL)
                _, status, usage = os.wait4(process.pid, 0)
                break
            time.sleep(0.005)
        process.returncode = os.waitstatus_to_exitcode(status)
        out.flush(); os.fsync(out.fileno())
        err.flush(); os.fsync(err.fileno())
    elapsed = time.monotonic() - started
    counters[f"{name}_completed"] += 1
    output_bindings = {}
    for path in (stdout, stderr):
        pinned = identity(path)
        data = path.read_bytes()
        if len(data) != pinned["bytes"] or hashlib.sha256(data).hexdigest() != pinned["sha256"]:
            raise ValueError(f"Capture changed during read: {path}")
        duplicate = path.with_suffix(".exactcopy")
        write_new(duplicate, data)
        if identity(path) != pinned or identity(duplicate) != pinned:
            raise ValueError(f"Capture preservation mismatch: {path}")
        output_bindings[path.name] = pinned
    result = {
        "schema": "mumble_adc12_child_resources_v1", "role": name, "argv": argv,
        "exit_code": process.returncode, "timed_out": timed_out,
        "CPU_user_s": usage.ru_utime, "CPU_system_s": usage.ru_stime,
        "CPU_total_s": usage.ru_utime + usage.ru_stime,
        "wall_s": elapsed, "peak_RSS_bytes": usage.ru_maxrss * 1024,
        "accounting_scope": "Exact os.wait4 for this child; compiler usage includes its waited compiler/linker descendants. Host Linux RSS, not target SRAM.",
        "outputs": output_bindings,
        "caps": caps,
    }
    violations = []
    if timed_out or elapsed > caps["wall_s"]: violations.append("wall")
    if result["CPU_total_s"] > caps["CPU_s"]: violations.append("CPU")
    if result["peak_RSS_bytes"] > caps["RSS_bytes"]: violations.append("RSS")
    if any(row["bytes"] > caps["file_bytes"] for row in output_bindings.values()):
        violations.append("output")
    result["resource_violations"] = violations
    write_new(directory / "resources.json", result)
    return result


def stack_records():
    rows = []
    for path in sorted(ATTEMPT.glob("*.su")):
        for line in path.read_text().splitlines():
            fields = line.split("\t")
            if len(fields) != 3:
                raise ValueError(f"Unexpected compiler stack row: {line}")
            rows.append({"file": path.name, "function": fields[0].rsplit(":", 1)[-1],
                         "frame_bytes": int(fields[1]), "kind": fields[2], "raw": line})
    if not rows:
        raise ValueError("No compiler stack records")
    return rows


def memory_ledger(sizes):
    queue = sizes["queue"]
    raw = sizes["raw_sample"]
    decoded = sizes["decoded_reading"]
    sequence = sizes["sequence_output"]
    calibration = sizes["calibration"]
    source = 32
    one_buffer = queue + raw + decoded + sequence
    all_ram = one_buffer + calibration + source
    return {
        "host_sizeof": sizes,
        "prior_ADC_queue_reservation_bytes": 448,
        "standalone_queue_difference_from_prior_reservation_bytes": 448 - queue,
        "one_serialized_raw_buffer_runtime_objects_bytes": one_buffer,
        "additional_immutable_calibration_bytes": calibration,
        "additional_immutable_push_source_identity_bytes": source,
        "one_raw_buffer_all_objects_in_RAM_bytes": all_ram,
        "separate_acquisition_and_decoded_raw_buffers_all_RAM_bytes": all_ram + raw,
        "optional_channel_codec_output_additional_bytes": sizes["optional_packed_channels"],
        "phase_rule": "A single externally serialized caller can reuse one raw buffer for push and take. A separately live acquisition buffer adds another raw_sample. Calibration/source may be const flash only if target placement is actually established.",
        "excluded_and_unmeasured": ["Stack/call-chain and library frames", "Caller/ISR/runtime storage and acquisition hardware state", "Synchronization or DMA buffers", "Target ABI and linker placement"],
        "integrated_bootstrap_layout": "Not this standalone FIFO. The separately proposed retained16 plus ingress8 plus64 metadata layout must be counted and qualified independently.",
        "claim": "Object ledger only; no complete ADC subsystem SRAM, physical ADC performance or Cortex-M23 qualification claim.",
    }


def run():
    ATTEMPT.mkdir()
    fsync_dir(QUAL)
    started = time.monotonic()
    before = resource.getrusage(resource.RUSAGE_SELF)
    counters = {f"{role}_{suffix}": 0 for role in ("compile", "test")
                for suffix in ("reserved", "launched", "completed")}
    receipt = {"schema": "mumble_adc12_transport_qualification_receipt_v1",
               "status": "failed", "counts": counters, "errors": [],
               "scientific_activity": {"model_calls": 0, "prior_calls": 0,
                   "optimizer_calls": 0, "learner_calls": 0,
                   "observation_reads": 0, "truth_reads": 0, "hardware_reads": 0,
                   "retries": 0}}
    resources = []
    plan = strict_json(PLAN)
    try:
        frozen = strict_json(FREEZE)
        verify_bindings(frozen)
        receipt["source_freeze"] = {"path": FREEZE.relative_to(ROOT).as_posix(), **identity(FREEZE)}
        receipt["sources_and_executables"] = frozen
        write_new(ATTEMPT / "reservation.json", {
            "schema": "mumble_adc12_qualification_reservation_v1",
            "source_freeze": receipt["source_freeze"], "plan": identity(PLAN),
            "compile_invocations_max": 1, "test_invocations_max": 1,
            "retries": 0, "counts_before": dict(counters),
        })
        binary = ATTEMPT / "adc12_test.bin"
        command = [frozen["compiler"]["path"], *plan["execution"]["compiler_flags"],
                   "experiments/live_anchor_bootstrap_001/adc12.c",
                   "experiments/live_anchor_bootstrap_001/qualification/adc12_test.c",
                   "-lm", "-o", str(binary)]
        resources.append(child("compile", command, plan["execution"]["compile_caps"], counters))
        if resources[-1]["exit_code"] != 0 or resources[-1]["resource_violations"]:
            raise ValueError("Compiler failed or exceeded a frozen limit")
        receipt["binary"] = {"path": binary.relative_to(ROOT).as_posix(), **identity(binary)}
        receipt["stack_records"] = stack_records()
        resources.append(child("test", [str(binary)], plan["execution"]["test_caps"], counters))
        if resources[-1]["exit_code"] != 0 or resources[-1]["resource_violations"]:
            raise ValueError("Fabricated test failed or exceeded a frozen limit")
        test = strict_json(ATTEMPT / "test/stdout.txt")
        if test["schema"] != "mumble_adc12_fabricated_test_v1" or test["status"] != "passed":
            raise ValueError("Test did not pass")
        if test["cases"] != 8 or test["failures"] != 0 or test["codec_vectors"] != 40:
            raise ValueError("Unexpected test scope")
        if [row["name"] for row in test["case_results"]] != [row["name"] for row in plan["cases"]]:
            raise ValueError("Case names differ from frozen plan")
        if any(test[key] != 0 for key in ("model_calls", "prior_calls", "optimizer_calls", "observation_reads", "truth_reads")):
            raise ValueError("Unexpected scientific activity")
        receipt["test_result"] = test
        receipt["memory"] = memory_ledger(test["sizeof"])
        receipt["stack_scope"] = "Host compiler per-function frames only, including its inlining decisions; not an additive whole-call-chain bound and not measured target stack."
        verify_bindings(frozen)
        if identity(FREEZE) != {key: receipt["source_freeze"][key] for key in ("bytes", "sha256")}:
            raise ValueError("Source-freeze identity changed")
        if identity(binary) != {key: receipt["binary"][key] for key in ("bytes", "sha256")}:
            raise ValueError("Test binary changed")
        receipt["inputs_unchanged"] = True
        receipt["status"] = "passed"
    except Exception as error:
        receipt["errors"].append({"type": type(error).__name__, "message": str(error)})
    after = resource.getrusage(resource.RUSAGE_SELF)
    own_cpu = after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime
    receipt["children"] = resources
    receipt["child_resource_accounting_complete"] = len(resources) == counters["compile_launched"] + counters["test_launched"]
    receipt["supervisor_resources_before_final_receipt"] = {
        "CPU_own_s": own_cpu, "CPU_with_completed_children_s": own_cpu + sum(r["CPU_total_s"] for r in resources),
        "wall_s": time.monotonic() - started, "peak_RSS_bytes": after.ru_maxrss * 1024,
        "scope": "Supervisor snapshot before final receipt; exact child wait4 rows above. Check child_resource_accounting_complete before treating the sum as all launched work. Final receipt serialization/close is not included in this snapshot.",
    }
    total = receipt["supervisor_resources_before_final_receipt"]
    caps = plan["execution"]["whole_caps"]
    for label, value, maximum in (
        ("whole CPU", total["CPU_with_completed_children_s"], caps["CPU_s"]),
        ("whole wall before receipt", total["wall_s"], caps["wall_s"]),
        ("parent RSS", total["peak_RSS_bytes"], caps["parent_RSS_bytes"]),
    ):
        if not math.isfinite(value) or value > maximum:
            receipt["status"] = "failed"; receipt["errors"].append({"limit": label, "value": value, "maximum": maximum})
    receipt["files"] = {p.relative_to(ATTEMPT).as_posix(): identity(p)
                        for p in sorted(ATTEMPT.rglob("*")) if p.is_file()}
    closed = sum(row["bytes"] for row in receipt["files"].values())
    receipt["closed_output_bytes_including_receipt"] = closed
    for _ in range(12):
        updated = closed + len(encode(receipt))
        if updated == receipt["closed_output_bytes_including_receipt"]:
            break
        receipt["closed_output_bytes_including_receipt"] = updated
    else:
        raise RuntimeError("Receipt byte-count fixed point failed")
    if updated > caps["closed_output_bytes"]:
        receipt["status"] = "failed"
        receipt["errors"].append({"limit": "closed output", "value": updated, "maximum": caps["closed_output_bytes"]})
        for _ in range(12):
            updated = closed + len(encode(receipt))
            if updated == receipt["closed_output_bytes_including_receipt"]: break
            receipt["closed_output_bytes_including_receipt"] = updated
    write_new(ATTEMPT / "receipt.json", receipt)
    print(json.dumps({"status": receipt["status"], "receipt": str(ATTEMPT / "receipt.json"),
                      "identity": identity(ATTEMPT / "receipt.json"), "counts": counters,
                      "errors": receipt["errors"]}, allow_nan=False))
    return 0 if receipt["status"] == "passed" else 1


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--freeze", action="store_true")
    group.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if args.freeze:
        write_new(FREEZE, bindings())
        print(json.dumps({"source_freeze": str(FREEZE), "identity": identity(FREEZE), "child_invocations": 0}))
        return 0
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
