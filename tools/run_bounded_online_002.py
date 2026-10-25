#!/usr/bin/env python3
"""One frozen two-cell boundary-aware bounded-online lifecycle run; no truth or optimizer.

Complete fixed-size checkpoints are temporary host artifacts. Preserve their
hashes/sizes and every first subprocess output. Never overwrite an old run.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import selectors
import subprocess
import tempfile
import time

# Pure host hash/JSON/parity utilities; this module does not execute M1.
from run_trajectory_integration import sha, git, progress, strict_json, compare_values

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "experiments/bounded_online_002/plan.json"
SOURCES = (
    "Makefile", "include/scm_model.h", "src/scm_model.c",
    "include/scm_online.h", "src/scm_online.c",
    "include/scm_online_checkpoint.h", "src/scm_online_checkpoint.c",
    "tests/test_online.c", "tests/test_online_checkpoint.c",
    "tools/online_probe.c", "tools/run_bounded_online_002.py", "tools/score_bounded_online_002.py",
    "tools/run_trajectory_integration.py", "plans/estimation_targets_001.json",
    "experiments/bounded_online_002/plan.json",
)
PROCESS_TIMEOUT_S = 1200
CHECKPOINT_BYTES = 2456
MODEL_VERSION = 2
ALGORITHM_ID = "componentwise_feasible_gain_joseph_lower_v2"


def save(path: Path, value: object) -> None:
    """Publish complete JSON atomically; raw process stdout remains streaming."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def validate_plan(plan: dict) -> None:
    if plan["schema"] != "mumble_bounded_online_plan_v2":
        raise ValueError("Unknown bounded-online plan schema")
    expected = {"checkpoint_sample_counts": [420, 31500, 42000, 64750, 73500],
        "warm_segment_ends": [420, 42000, 64750, 73500], "cold_reset_sample": 31500,
        "query_stride_samples": 350, "expected_processes": 12,
        "expected_input_deliveries": 378000, "new_batch_optimizer_calls": 0}
    for key, value in expected.items():
        if plan["execution"].get(key) != value:
            raise ValueError(f"Driver does not implement execution.{key}")
    domain = plan["candidate"]["input_domain"]
    if any(domain[key] != value for key, value in
           (("dt_s_min", 0), ("dt_s_max", 1), ("abs_current_A_max", .25), ("sigma_V", .001), ("modes", 3))):
        raise ValueError("Driver public input configuration differs from plan")
    if plan["acceptance"]["core_owned_bytes_max"] != 8192:
        raise ValueError("Unexpected fixed core storage gate")
    if plan["candidate"]["model_version"] != MODEL_VERSION or \
            plan["candidate"]["checkpoint"]["version"] != 2 or \
            plan["candidate"]["checkpoint"]["expected_bytes"] != CHECKPOINT_BYTES:
        raise ValueError("Unexpected model/checkpoint identity")
    if plan["acceptance"]["primary_rejected_voltage_updates_max"] != 0:
        raise ValueError("This primary requires zero rejected voltage corrections")
    cases = plan["cases"]
    if len(cases) != 2 or len({c["case_id"] for c in cases}) != 2:
        raise ValueError("Exactly two distinct cells required")
    for case in cases:
        if case["samples"] != 73500 or Path(case["case_id"]).name != case["case_id"]:
            raise ValueError("Unexpected case size or unsafe identifier")
        if sha(ROOT / case["path"]) != case["sha256"]:
            raise ValueError("Frozen input hash changed")
    if plan["execution"]["case_workers"] not in (1, 2):
        raise ValueError("Only one or two independent cell workers are supported")


def run_process(command: list[str], out: Path, case_id: str, name: str, kind: str,
                start: int, end: int, saves: list[int], plan: dict) -> tuple[dict, list[dict]]:
    stem = f"{case_id}__{name}"
    stdout, stderr = out / f"{stem}.jsonl", out / f"{stem}.stderr.txt"
    record = {"name": name, "kind": kind, "start_index": start, "end_index": end,
        "command": command, "stdout_jsonl": stdout.name, "stderr": stderr.name,
        "returncode": None, "timeout_s": PROCESS_TIMEOUT_S, "operational_failures": [],
        "checkpoint_records": []}
    process, pending, events = None, b"", []
    began = time.monotonic()
    progress({"event": "process_begin", "case_id": case_id, "name": name,
        "start_index": start, "end_index": end, "expected_deliveries": end - start})
    with stdout.open("wb") as raw, stderr.open("wb") as errors:
        try:
            process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=errors)
            assert process.stdout is not None
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while selector.get_map():
                    if time.monotonic() - began > PROCESS_TIMEOUT_S:
                        raise TimeoutError("Online process exceeded timeout")
                    for key, _ in selector.select(timeout=1.0):
                        data = os.read(key.fileobj.fileno(), 65536)
                        if not data:
                            selector.unregister(key.fileobj)
                            continue
                        raw.write(data)
                        raw.flush()
                        pending += data
                        while b"\n" in pending:
                            line, pending = pending.split(b"\n", 1)
                            if line:
                                events.append(strict_json(line))
                if pending:
                    raise ValueError("Truncated final JSONL record")
            record["returncode"] = process.wait(timeout=5)
        except (OSError, ValueError, TimeoutError, subprocess.TimeoutExpired) as error:
            record["operational_failures"].append({"kind": type(error).__name__, "error": str(error)})
            if process is not None:
                if process.poll() is None:
                    process.kill()
                record["returncode"] = process.wait()
                if process.stdout is not None:
                    raw.write(process.stdout.read())
        finally:
            if process is not None and process.stdout is not None:
                process.stdout.close()
    record["process_wall_s"] = time.monotonic() - began
    record["stdout_sha256"], record["stderr_sha256"] = sha(stdout), sha(stderr)
    record["stdout_bytes"], record["stderr_bytes"] = stdout.stat().st_size, stderr.stat().st_size
    runs = [e for e in events if e["event"] == "run"]
    queries = [e for e in events if e["event"] == "query"]
    completes = [e for e in events if e["event"] == "complete"]
    checkpoints = [e for e in events if e["event"] == "checkpoint"]
    expected_queries = sorted({start, end, *saves, *range(
        (start // plan["execution"]["query_stride_samples"] + 1) * plan["execution"]["query_stride_samples"],
        end + 1, plan["execution"]["query_stride_samples"])})
    case = next(c for c in plan["cases"] if c["case_id"] == case_id)
    expected_run = {"schema": "mumble_online_jsonl_v2", "model_version": MODEL_VERSION,
        "algorithm": ALGORITHM_ID, "source_id": case["sha256"], "start_index": start, "end_index": end,
        "restored": start != 0, "cold_reset": kind == "cold", "dimension": 16,
        "query_stride_samples": plan["execution"]["query_stride_samples"], "sigma_V": .001,
        "max_dt_s": 1.0, "max_abs_current_A": .25, "checkpoint_bytes": CHECKPOINT_BYTES,
        "batch_optimizer_calls": 0, "truth_input": False, "raw_history_retained": False}
    record["input_deliveries"] = completes[0]["input_deliveries"] if len(completes) == 1 else max(
        (e.get("next_index", start) - start for e in events), default=0)
    record["delivery_count_scope"] = "Complete-event accepted updates; on failure, consumed input position inferred from last event"
    record["validations"] = {
        "successful_exit": record["returncode"] == 0,
        "run_identity_and_config": len(runs) == 1 and all(runs[0].get(k) == v for k, v in expected_run.items()),
        "query_schedule": [e["next_index"] for e in queries] == expected_queries,
        "completion": len(completes) == 1 and completes[0]["next_index"] == end and
            completes[0]["input_deliveries"] == end - start and completes[0]["batch_optimizer_calls"] == 0,
        "checkpoint_schedule": [e["next_index"] for e in checkpoints] == saves,
        "no_error_events": not any(e["event"] == "error" for e in events),
        "no_batch_fit_events": not any(e["event"] in ("fit", "fit_begin") for e in events),
        "query_ledger": bool(queries) and all(e["state"]["next_index"] == e["next_index"] and
            e["state"]["prediction_count"] == e["next_index"] for e in queries),
    }
    resource_rows = [e["resources"] for e in queries]
    record["resources"] = resource_rows[-1] if resource_rows else None
    record["resource_passed"] = bool(resource_rows) and all(r == resource_rows[0] for r in resource_rows) and \
        resource_rows[0]["core_owned_bytes"] <= plan["acceptance"]["core_owned_bytes_max"]
    record["numerical_health"] = {
        "rejected_voltage_count_start": queries[0]["state"]["rejected_voltage_count"] if queries else None,
        "rejected_voltage_count_end": queries[-1]["state"]["rejected_voltage_count"] if queries else None,
        "rejected_voltage_updates_max": plan["acceptance"]["primary_rejected_voltage_updates_max"],
        "scope": "Cumulative counters survive warm/cold restart; primary permits zero rejected corrections."
    }
    record["numerical_health_passed"] = bool(queries) and record["validations"]["completion"] and \
        record["validations"]["successful_exit"] and all(
            e["state"]["rejected_voltage_count"] <= plan["acceptance"]["primary_rejected_voltage_updates_max"] and
            (e["state"]["flags"] & (2 | 4 | 16)) == 0 for e in queries)
    for checkpoint in checkpoints:
        path = Path(checkpoint["path"])
        try:
            size = path.stat().st_size
            record["checkpoint_records"].append({"next_index": checkpoint["next_index"],
                "epoch_begin": checkpoint["epoch_begin"], "path_during_run": str(path),
                "bytes": size, "sha256": sha(path)})
            if size != CHECKPOINT_BYTES or checkpoint.get("bytes") != CHECKPOINT_BYTES:
                raise ValueError("Checkpoint violates fixed-size format")
        except (OSError, ValueError) as error:
            record["operational_failures"].append({"kind": "checkpoint", "error": str(error)})
    record["passed"] = all(record["validations"].values()) and not record["operational_failures"]
    save(out / f"{stem}.process.json", record)
    progress({"event": "process_complete", "case_id": case_id, "name": name,
        "passed": record["passed"], "resource_passed": record["resource_passed"],
        "numerical_health_passed": record["numerical_health_passed"],
        "input_deliveries": record["input_deliveries"], "process_wall_s": record["process_wall_s"]})
    return record, events


def compare_queries(control: list[dict], warm: list[dict]) -> dict:
    by_n = {e["next_index"]: e for e in control if e["event"] == "query"}
    selected = [e for e in warm if e["event"] == "query"]
    errors, count, maximum = [], 0, 0.0
    if {e["next_index"] for e in selected} != set(by_n):
        errors.append("Query position sets differ")
    for event in selected:
        n = event["next_index"]
        if n not in by_n:
            errors.append(f"Missing control position {n}")
            continue
        left = {key: by_n[n][key] for key in ("state", "resources")}
        right = {key: event[key] for key in ("state", "resources")}
        checked, delta, failed = compare_values(left, right, 0, 0, f"query@{n}", exact=True)
        count += checked
        maximum = max(maximum, delta)
        errors.extend(failed)
    return {"passed": not errors, "compared_records": len(selected), "compared_scalar_fields": count,
        "maximum_absolute_difference": maximum, "failure_count": len(errors), "first_failures": errors[:20]}


def run_case(case: dict, plan: dict, executable: Path, temporary: Path, out: Path) -> dict:
    case_id, execution = case["case_id"], plan["execution"]
    directory = temporary / case_id
    directory.mkdir()
    result = {"case_id": case_id, "data": case["path"], "data_sha256": case["sha256"],
        "processes": [], "operational_failures": [], "functional_passed": False, "resource_passed": False,
        "numerical_health_passed": False}

    def launch(name: str, kind: str, start: int, end: int, restore: Path | None = None) -> tuple[dict, list[dict]]:
        saves = [n for n in execution["checkpoint_sample_counts"] if start < n <= end] if kind != "cold" else []
        command = [str(executable), "--data", str(ROOT / case["path"]), "--source", case["sha256"],
            "--end", str(end), "--checkpoint-prefix", str(directory / name), "--save-at", ",".join(map(str, saves)),
            "--query-stride", str(execution["query_stride_samples"])]
        if restore is not None:
            command += ["--restore", str(restore)]
        if kind == "cold":
            command += ["--cold-reset"]
        process, events = run_process(command, out, case_id, name, kind, start, end, saves, plan)
        result["processes"].append(process)
        if not process["passed"]:
            raise ValueError(f"Process {name} failed; dependent continuations not started")
        return process, events

    try:
        control, control_events = launch("control", "control", 0, case["samples"])
        warm_records, warm_events, start, restore = [], [], 0, None
        for index, end in enumerate(execution["warm_segment_ends"]):
            name = f"warm_{index+1}"
            process, events = launch(name, "warm", start, end, restore)
            warm_records.append(process)
            warm_events.extend(events)
            restore = directory / f"{name}-{end}.bin"
            start = end
        cold_start = execution["cold_reset_sample"]
        _, cold_events = launch("cold", "cold", cold_start, case["samples"], directory / f"control-{cold_start}.bin")
        warm_checkpoints = {c["next_index"]: c for p in warm_records for c in p["checkpoint_records"]}
        comparisons = []
        for checkpoint in control["checkpoint_records"]:
            warm = warm_checkpoints.get(checkpoint["next_index"])
            comparisons.append({"next_index": checkpoint["next_index"], "control": checkpoint, "warm": warm,
                "passed": warm is not None and (checkpoint["bytes"], checkpoint["sha256"]) == (warm["bytes"], warm["sha256"])})
        result["comparisons"] = {"checkpoints": comparisons, "queries": compare_queries(control_events, warm_events),
            "excluded_fields": ["query event/reason", "process wall time"]}
        first = next((e for e in cold_events if e["event"] == "query"), None)
        result["cold_reset_check"] = {"immediate_query": first, "passed": first is not None and
            first["reason"] == "cold_reset" and first["next_index"] == cold_start and first["epoch_begin"] == cold_start and
            first["state"]["point_available"] == 0 and first["state"]["capacity_available"] == 0 and
            first["state"]["local_ranges_available"] == 0 and first["state"]["cold_resets"] == 1}
        result["functional_passed"] = all(r["passed"] for r in comparisons) and result["comparisons"]["queries"]["passed"] and result["cold_reset_check"]["passed"]
        result["resource_passed"] = all(p["resource_passed"] for p in result["processes"])
        result["numerical_health_passed"] = all(p["numerical_health_passed"] for p in result["processes"])
    except Exception as error:
        result["operational_failures"].append({"kind": type(error).__name__, "error": str(error)})
    result["input_deliveries"] = sum(p["input_deliveries"] for p in result["processes"])
    save(out / f"{case_id}__case.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--binary", type=Path, default=ROOT / "build/scm_online_probe")
    args = parser.parse_args()
    out, binary = args.output_dir.resolve(), args.binary.resolve()
    if out.exists():
        parser.error("Output exists; preserve the first run and choose another path")
    plan = json.loads(PLAN.read_text())
    validate_plan(plan)
    git("ls-files", "--error-unmatch", *SOURCES)
    if git("status", "--porcelain", "--", *SOURCES):
        raise ValueError("Commit clean source/tests/runner/plan before primary inference")
    hashes = {name: sha(ROOT / name) for name in SOURCES}
    binary_hash = sha(binary)
    out.mkdir(parents=True)
    receipt = {"schema": "mumble_bounded_online_receipt_v2", "model_version": MODEL_VERSION,
        "algorithm": ALGORITHM_ID, "started_utc": datetime.now(timezone.utc).isoformat(),
        "source_revision": git("rev-parse", "HEAD"), "branch": git("branch", "--show-current"),
        "source_sha256": hashes, "plan": str(PLAN.relative_to(ROOT)), "plan_sha256": sha(PLAN),
        "binary_sha256": binary_hash, "binary": str(binary), "platform": platform.platform(),
        "python": platform.python_version(), "execution": plan["execution"], "acceptance": plan["acceptance"],
        "truth_access": False, "batch_optimizer_calls": 0, "inference_completed": False,
        "functional_passed": False, "resource_passed": False, "numerical_health_passed": False,
        "cases": [], "operational_failures": [],
        "usefulness": "Separate post-inference scoring; never used for inference or tuning",
        "checkpoint_artifacts": "Temporary complete fixed state files; hashes/sizes and commands preserved",
        "memory_scope": "Fixed core state/workspace/query and enumerated host buffers; stack and libc/FILE/runtime extra",
        "timing_scope": "Host process wall time, including input parsing/output/checkpoints; not isolated kernel or M23 timing"}
    save(out / "receipt.json", receipt)
    began = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="mumble_online_002_primary_") as directory:
            temporary = Path(directory)
            executable = temporary / "scm_online_probe"
            executable.write_bytes(binary.read_bytes())
            executable.chmod(0o700)
            if sha(executable) != binary_hash:
                raise ValueError("Binary changed while snapshotting")
            with ThreadPoolExecutor(max_workers=plan["execution"]["case_workers"]) as workers:
                futures = [workers.submit(run_case, case, plan, executable, temporary, out) for case in plan["cases"]]
                for future in as_completed(futures):
                    receipt["cases"].append(future.result())
                    save(out / "receipt.json", receipt)
            receipt["binary_snapshot_unchanged"] = sha(executable) == binary_hash
        receipt["inference_completed"] = True
    except Exception as error:
        receipt["operational_failures"].append({"kind": type(error).__name__, "error": str(error)})
    receipt["cases"].sort(key=lambda c: c["case_id"])
    receipt["input_deliveries"] = sum(c["input_deliveries"] for c in receipt["cases"])
    receipt["processes_completed"] = sum(len(c["processes"]) for c in receipt["cases"])
    receipt["process_wall_s"] = time.monotonic() - began
    receipt["integrity"] = {"source_unchanged": hashes == {name: sha(ROOT / name) for name in SOURCES},
        "source_revision_unchanged": receipt["source_revision"] == git("rev-parse", "HEAD"),
        "binary_unchanged": binary_hash == sha(binary),
        "data_unchanged": all(sha(ROOT / c["path"]) == c["sha256"] for c in plan["cases"]),
        "binary_snapshot_unchanged": receipt.get("binary_snapshot_unchanged", False)}
    receipt["functional_passed"] = receipt["inference_completed"] and len(receipt["cases"]) == 2 and \
        all(c["functional_passed"] for c in receipt["cases"]) and all(receipt["integrity"].values()) and \
        receipt["input_deliveries"] == plan["execution"]["expected_input_deliveries"] and \
        receipt["processes_completed"] == plan["execution"]["expected_processes"] and not receipt["operational_failures"]
    receipt["resource_passed"] = len(receipt["cases"]) == 2 and all(c["resource_passed"] for c in receipt["cases"])
    receipt["numerical_health_passed"] = len(receipt["cases"]) == 2 and all(c["numerical_health_passed"] for c in receipt["cases"])
    receipt["finished_utc"] = datetime.now(timezone.utc).isoformat()
    save(out / "receipt.json", receipt)
    progress({"event": "primary_complete", "receipt": str(out / "receipt.json"),
        "functional_passed": receipt["functional_passed"], "resource_passed": receipt["resource_passed"],
        "numerical_health_passed": receipt["numerical_health_passed"],
        "input_deliveries": receipt["input_deliveries"], "processes_completed": receipt["processes_completed"],
        "process_wall_s": receipt["process_wall_s"]})
    return 0 if receipt["functional_passed"] and receipt["resource_passed"] and receipt["numerical_health_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
