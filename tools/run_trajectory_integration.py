#!/usr/bin/env python3
"""One frozen M1 two-cell lifecycle run. C owns inference; truth is never loaded.

Complete checkpoints are temporary host artifacts. Their sizes, SHA256 values,
commands and comparison outcomes remain in the receipt; committed inputs and
sources reproduce them. Existing outputs are never overwritten or retuned.
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
import selectors
import subprocess
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "experiments/trajectory_integration_001/plan.json"
SOURCES = (
    "Makefile", "src/scm_model.c", "src/scm_estimator.c", "src/scm_assess.c", "src/scm_features.c",
    "include/scm_model.h", "include/scm_estimator.h", "include/scm_assess.h", "include/scm_features.h",
    "src/scm_session.c", "include/scm_session.h",
    "src/scm_session_checkpoint.c", "include/scm_session_checkpoint.h",
    "tests/test_session.c", "tests/test_session_checkpoint.c",
    "tools/session_probe.c", "tools/run_trajectory_integration.py",
    "experiments/trajectory_integration_001/plan.json",
)
TIMING_FIELDS = {"elapsed_cpu_s", "basis_seconds"}
PROCESS_TIMEOUT_S = 1200
LOCK = threading.Lock()


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def git(*arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=ROOT, text=True).strip()


def progress(value: dict) -> None:
    with LOCK:
        print(json.dumps(value, allow_nan=False), flush=True)


def strict_json(line: bytes) -> dict:
    def invalid_constant(value: str) -> None:
        raise ValueError(f"Nonstandard JSON constant: {value}")
    result = json.loads(line, parse_constant=invalid_constant)
    if not isinstance(result, dict) or not isinstance(result.get("event"), str):
        raise ValueError("Expected one object with an event name")
    return result


def validate_plan(plan: dict) -> None:
    expected = {
        "fit_sample_counts": [350, 31500, 63000, 73500],
        "checkpoint_sample_counts": [420, 31500, 42000, 64750, 73500],
        "warm_segment_ends": [420, 42000, 64750, 73500],
        "cold_reset_sample": 31500, "query_stride_samples": 350,
        "fit_budget_total": 20, "starts": 3, "max_iterations": 120,
        "sigma": 0.001, "modes": 3, "max_history_samples": 73500,
        "control_fits_per_cell": 4, "warm_fits_per_cell": 4,
        "cold_new_fits_per_cell": 2,
    }
    if plan["schema"] != "mumble_trajectory_integration_plan_v1":
        raise ValueError("Unknown primary plan schema")
    for key, value in expected.items():
        if plan["execution"].get(key) != value:
            raise ValueError(f"M1 driver does not implement plan execution.{key}")
    cases = plan["cases"]
    if len(cases) != 2 or len({c["case_id"] for c in cases}) != 2:
        raise ValueError("Exactly two distinct frozen cells are required")
    for case in cases:
        if case["samples"] != 73500 or len(case["sha256"]) != 64:
            raise ValueError("Unexpected case size or identity")
        if Path(case["case_id"]).name != case["case_id"]:
            raise ValueError("Case identifiers must be filenames")
        if sha(ROOT / case["path"]) != case["sha256"]:
            raise ValueError(f"Input hash differs for {case['case_id']}")
    if plan["execution"]["case_workers"] not in (1, 2):
        raise ValueError("This primary permits one or two case workers")
    if plan["acceptance"]["query_atol"] != 1e-12 or plan["acceptance"]["query_rtol"] != 1e-10:
        raise ValueError("Unexpected comparison tolerances")


class Budget:
    def __init__(self, limit: int):
        self.limit, self.calls = limit, 0
        self.lock = threading.Lock()

    def observed_call(self) -> int:
        with self.lock:
            self.calls += 1
            if self.calls > self.limit:
                raise ValueError("Global primary fit budget exceeded")
            return self.calls


def run_process(command: list[str], out: Path, case_id: str, name: str,
                kind: str, start: int, end: int, expected_fits: list[int],
                expected_saves: list[int], budget: Budget) -> tuple[dict, list[dict]]:
    """Persist every byte, with a real timeout even while a fit emits no output."""
    stem = f"{case_id}__{name}"
    stdout_path, stderr_path = out / f"{stem}.jsonl", out / f"{stem}.stderr.txt"
    record = {
        "name": name, "kind": kind, "start_index": start, "end_index": end,
        "command": command, "stdout_jsonl": stdout_path.name, "stderr": stderr_path.name,
        "timeout_s": PROCESS_TIMEOUT_S, "returncode": None,
        "operational_failures": [], "checkpoint_records": [],
    }
    events: list[dict] = []
    pending = b""
    started = time.monotonic()
    process = None
    progress({"event": "process_begin", "case_id": case_id, "name": name,
              "start_index": start, "end_index": end, "expected_fit_calls": len(expected_fits)})

    def accept(line: bytes) -> None:
        event = strict_json(line)
        events.append(event)
        if event["event"] == "fit_begin":
            calls = budget.observed_call()
            progress({"case_id": case_id, "process": name, "primary_fit_calls_seen": calls, **event})
        elif event["event"] == "fit":
            result = event.get("fit") or {}
            progress({"event": "fit_complete", "case_id": case_id, "process": name,
                      "next_index": event["next_index"], "returncode": event["returncode"],
                      "optimizer_status": result.get("status"), "elapsed_cpu_s": result.get("elapsed_cpu_s")})

    with stdout_path.open("wb") as raw, stderr_path.open("wb") as errors:
        try:
            process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=errors)
            assert process.stdout is not None
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while selector.get_map():
                    if time.monotonic() - started > PROCESS_TIMEOUT_S:
                        raise TimeoutError(f"Process exceeded {PROCESS_TIMEOUT_S}s")
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
                                accept(line)
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
                    remainder = process.stdout.read()
                    if remainder:
                        raw.write(remainder)
        finally:
            if process is not None and process.stdout is not None:
                process.stdout.close()
    record["process_wall_s"] = time.monotonic() - started
    record["stdout_sha256"], record["stderr_sha256"] = sha(stdout_path), sha(stderr_path)
    record["stdout_bytes"], record["stderr_bytes"] = stdout_path.stat().st_size, stderr_path.stat().st_size
    begins = [e for e in events if e["event"] == "fit_begin"]
    fits = [e for e in events if e["event"] == "fit"]
    runs = [e for e in events if e["event"] == "run"]
    completes = [e for e in events if e["event"] == "complete"]
    checkpoints = [e for e in events if e["event"] == "checkpoint"]
    record["actual_fit_calls"] = len(begins)
    record["fit_positions"] = [e["next_index"] for e in begins]
    record["validations"] = {
        "successful_exit": record["returncode"] == 0,
        "run_identity": len(runs) == 1 and runs[0]["start_index"] == start and runs[0]["end_index"] == end,
        "fit_schedule": record["fit_positions"] == expected_fits,
        "fit_completions": [e["next_index"] for e in fits] == expected_fits and all(e["returncode"] == 0 for e in fits),
        "completion": len(completes) == 1 and completes[0]["next_index"] == end and completes[0]["actual_fit_calls"] == len(begins),
        "checkpoint_schedule": [e["next_index"] for e in checkpoints] == expected_saves,
        "no_error_events": not any(e["event"] == "error" for e in events),
    }
    for checkpoint in checkpoints:
        path = Path(checkpoint["path"])
        try:
            record["checkpoint_records"].append({
                "next_index": checkpoint["next_index"], "epoch_begin": checkpoint["epoch_begin"],
                "path_during_run": str(path), "bytes": path.stat().st_size, "sha256": sha(path),
            })
        except OSError as error:
            record["operational_failures"].append({"kind": "checkpoint_read", "error": str(error)})
    record["passed"] = all(record["validations"].values()) and not record["operational_failures"]
    save(out / f"{stem}.process.json", record)
    progress({"event": "process_complete", "case_id": case_id, "name": name,
              "passed": record["passed"], "returncode": record["returncode"],
              "actual_fit_calls": record["actual_fit_calls"], "process_wall_s": record["process_wall_s"]})
    return record, events


def compare_values(expected: object, actual: object, atol: float, rtol: float,
                   path: str = "", *, exact: bool = False) -> tuple[int, float, list[str]]:
    """Discrete fields are exact. Tolerance applies only to JSON float values."""
    count, maximum, failures = 0, 0.0, []
    if isinstance(expected, dict) and isinstance(actual, dict):
        if expected.keys() != actual.keys():
            return 1, 0.0, [path + ": keys differ"]
        for key in expected:
            n, delta, failed = compare_values(expected[key], actual[key], atol, rtol, f"{path}.{key}", exact=exact)
            count += n
            maximum = max(maximum, delta)
            failures.extend(failed)
    elif isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            return 1, 0.0, [path + ": lengths differ"]
        for index, (left, right) in enumerate(zip(expected, actual)):
            n, delta, failed = compare_values(left, right, atol, rtol, f"{path}[{index}]", exact=exact)
            count += n
            maximum = max(maximum, delta)
            failures.extend(failed)
    else:
        count = 1
        if isinstance(expected, float) or isinstance(actual, float):
            if isinstance(expected, (int, float)) and not isinstance(expected, bool) and isinstance(actual, (int, float)) and not isinstance(actual, bool):
                maximum = abs(expected - actual)
                same = math.isfinite(expected) and math.isfinite(actual) and (expected == actual if exact else maximum <= atol + rtol * max(abs(expected), abs(actual)))
            else:
                same = False
        else:
            same = type(expected) is type(actual) and expected == actual
        if not same:
            failures.append(path)
    return count, maximum, failures


def compare_records(control: list[dict], warm: list[dict], event_type: str,
                    fields: list[str], atol: float, rtol: float, *, exact: bool = False) -> dict:
    by_position = {e["next_index"]: e for e in control if e["event"] == event_type}
    selected = [e for e in warm if e["event"] == event_type]
    count, maximum, failures = 0, 0.0, []
    positions = {e["next_index"] for e in selected}
    if positions != set(by_position):
        failures.append("Position sets differ")
    for event in selected:
        position = event["next_index"]
        if position not in by_position:
            failures.append(f"Missing control position {position}")
            continue
        left = {key: by_position[position][key] for key in fields}
        right = {key: event[key] for key in fields}
        if event_type == "fit":
            left["fit"] = {k: v for k, v in left["fit"].items() if k not in TIMING_FIELDS}
            right["fit"] = {k: v for k, v in right["fit"].items() if k not in TIMING_FIELDS}
        n, delta, failed = compare_values(left, right, atol, rtol, f"{event_type}@{position}", exact=exact)
        count += n
        maximum = max(maximum, delta)
        failures.extend(failed)
    return {"passed": not failures, "compared_records": len(selected), "compared_scalar_fields": count,
            "maximum_absolute_difference": maximum, "failure_count": len(failures), "first_failures": failures[:20]}


def run_case(case: dict, plan: dict, executable: Path, temporary: Path,
             out: Path, budget: Budget) -> dict:
    execution, acceptance = plan["execution"], plan["acceptance"]
    case_id = case["case_id"]
    case_temp = temporary / case_id
    case_temp.mkdir()
    result = {"case_id": case_id, "data": case["path"], "data_sha256": case["sha256"],
              "processes": [], "operational_failures": [], "functional_passed": False}
    schedule = execution["fit_sample_counts"]
    saves = execution["checkpoint_sample_counts"]

    def launch(name: str, kind: str, start: int, end: int,
               restore: Path | None = None, cold: bool = False) -> tuple[dict, list[dict]]:
        expected_fits = [n for n in schedule if start < n <= end]
        expected_saves = [n for n in saves if start < n <= end] if kind != "cold" else []
        prefix = case_temp / name
        command = [str(executable), "--data", str(ROOT / case["path"]), "--source", case["sha256"],
                   "--end", str(end), "--checkpoint-prefix", str(prefix),
                   "--save-at", ",".join(map(str, expected_saves)),
                   "--query-stride", str(execution["query_stride_samples"]), "--fit-budget", str(len(expected_fits))]
        if restore is not None:
            command += ["--restore", str(restore)]
        if cold:
            command += ["--cold-reset"]
        record, events = run_process(command, out, case_id, name, kind, start, end,
                                     expected_fits, expected_saves, budget)
        result["processes"].append(record)
        if not record["passed"]:
            raise ValueError(f"Process {name} failed; dependent segments not started")
        runs = [e for e in events if e["event"] == "run"]
        if runs[0]["source_id"] != case["sha256"]:
            raise ValueError(f"Process {name} source identity mismatch")
        declared = {key: execution[key] for key in ("modes", "starts", "max_iterations", "max_history_samples", "sigma", "query_stride_samples")}
        declared.update(restored=restore is not None, cold_reset=cold,
                        fit_budget=len(expected_fits), truth_input=False, prior_factor_added=False)
        if any(runs[0].get(key) != value for key, value in declared.items()):
            raise ValueError(f"Process {name} configuration differs from the frozen plan")
        queries = [e["next_index"] for e in events if e["event"] == "query"]
        stride = execution["query_stride_samples"]
        expected_queries = sorted({start, end, *expected_fits, *expected_saves,
                                   *range((start // stride + 1) * stride, end + 1, stride)})
        if queries != expected_queries:
            raise ValueError(f"Process {name} query positions differ from the frozen policy")
        return record, events

    try:
        control, control_events = launch("control", "control", 0, case["samples"])
        warm_records, warm_events = [], []
        start, restore = 0, None
        for index, end in enumerate(execution["warm_segment_ends"]):
            name = f"warm_{index + 1}"
            record, events = launch(name, "warm", start, end, restore)
            warm_records.append(record)
            warm_events.extend(events)
            restore = case_temp / f"{name}-{end}.bin"
            start = end
        cold_start = execution["cold_reset_sample"]
        _, cold_events = launch("cold", "cold", cold_start, case["samples"],
                                case_temp / f"control-{cold_start}.bin", cold=True)
        warm_checkpoints = {c["next_index"]: c for p in warm_records for c in p["checkpoint_records"]}
        checkpoint_comparison = []
        for control_checkpoint in control["checkpoint_records"]:
            n = control_checkpoint["next_index"]
            warm_checkpoint = warm_checkpoints.get(n)
            checkpoint_comparison.append({"next_index": n, "control": control_checkpoint,
                "warm": warm_checkpoint, "passed": warm_checkpoint is not None and
                (control_checkpoint["bytes"], control_checkpoint["sha256"]) == (warm_checkpoint["bytes"], warm_checkpoint["sha256"])})
        atol, rtol = acceptance["query_atol"], acceptance["query_rtol"]
        result["comparisons"] = {
            "checkpoints": checkpoint_comparison,
            "queries": compare_records(control_events, warm_events, "query", ["state", "assessment"], atol, rtol),
            "fits": compare_records(control_events, warm_events, "fit", ["returncode", "epoch_begin", "fit"], atol, rtol),
            "resources": compare_records(control_events, warm_events, "query", ["resources"], 0, 0, exact=True),
            "excluded_fields": {"fit": sorted(TIMING_FIELDS), "query": ["event", "reason"]},
        }
        first_queries = [e for e in cold_events if e["event"] == "query"]
        first = first_queries[0] if first_queries else None
        result["cold_reset_check"] = {
            "passed": first is not None and first["reason"] == "cold_reset" and
                first["next_index"] == cold_start and first["epoch_begin"] == cold_start and
                first["state"]["point_available"] == 0 and first["state"]["capacity_available"] == 0 and
                first["state"]["history_samples"] == 0 and first["state"]["cold_resets"] == 1 and first["assessment"] is None,
            "immediate_query": first,
        }
        result["actual_fit_calls"] = sum(p["actual_fit_calls"] for p in result["processes"])
        result["functional_passed"] = all(c["passed"] for c in checkpoint_comparison) and all(
            result["comparisons"][kind]["passed"] for kind in ("queries", "fits", "resources")) and result["cold_reset_check"]["passed"] and result["actual_fit_calls"] == 10
    except Exception as error:
        result["operational_failures"].append({"kind": type(error).__name__, "error": str(error)})
        result["actual_fit_calls"] = sum(p["actual_fit_calls"] for p in result["processes"])
    save(out / f"{case_id}__case.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--binary", type=Path, default=ROOT / "build/scm_session_probe")
    args = parser.parse_args()
    out, binary = args.output_dir.resolve(), args.binary.resolve()
    if out.exists():
        parser.error("Output already exists; preserve the first run and choose a new path")
    plan = json.loads(PLAN.read_text())
    validate_plan(plan)
    git("ls-files", "--error-unmatch", *SOURCES)
    if git("status", "--porcelain", "--", *SOURCES):
        raise ValueError("Commit clean numerical sources, tests, runner and frozen plan before primary inference")
    source_hashes = {name: sha(ROOT / name) for name in SOURCES}
    binary_hash = sha(binary)
    out.mkdir(parents=True)
    receipt = {
        "schema": "mumble_trajectory_integration_receipt_v1",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "source_revision": git("rev-parse", "HEAD"), "branch": git("branch", "--show-current"),
        "source_sha256": source_hashes, "plan": str(PLAN.relative_to(ROOT)), "plan_sha256": sha(PLAN),
        "binary": str(binary.relative_to(ROOT)) if binary.is_relative_to(ROOT) else str(binary),
        "binary_sha256": binary_hash, "platform": platform.platform(), "python": platform.python_version(),
        "execution": plan["execution"], "acceptance": plan["acceptance"],
        "truth_access": False, "prior_factor_added": False, "inference_completed": False,
        "functional_passed": False, "usefulness": "not_scored_here; separate scoring only after all C inference",
        "checkpoint_artifacts": "Temporary complete journals; SHA256/size retained, source/data/commands reproduce them",
        "timing_scope": "Host fit CPU and subprocess wall; not M23 latency or energy",
        "memory_scope": "Requested C ownership and solver work, plus checkpoint size; not complete RSS, allocator or target stack",
        "cases": [], "operational_failures": [],
    }
    save(out / "receipt.json", receipt)
    budget = Budget(plan["execution"]["fit_budget_total"])
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="mumble_m1_primary_") as directory:
            temporary = Path(directory)
            executable = temporary / "scm_session_probe"
            executable.write_bytes(binary.read_bytes())
            executable.chmod(0o700)
            if sha(executable) != binary_hash:
                raise ValueError("Executable changed while snapshotting")
            with ThreadPoolExecutor(max_workers=plan["execution"]["case_workers"]) as workers:
                futures = [workers.submit(run_case, case, plan, executable, temporary, out, budget) for case in plan["cases"]]
                for future in as_completed(futures):
                    receipt["cases"].append(future.result())
                    receipt["actual_fit_calls_total"] = budget.calls
                    save(out / "receipt.json", receipt)
            receipt["binary_snapshot_unchanged"] = sha(executable) == binary_hash
        receipt["inference_completed"] = True
    except Exception as error:
        receipt["operational_failures"].append({"kind": type(error).__name__, "error": str(error)})
    receipt["cases"].sort(key=lambda case: case["case_id"])
    receipt["actual_fit_calls_total"] = budget.calls
    receipt["process_wall_s"] = time.monotonic() - started
    receipt["integrity"] = {
        "source_unchanged": source_hashes == {name: sha(ROOT / name) for name in SOURCES},
        "source_revision_unchanged": receipt["source_revision"] == git("rev-parse", "HEAD"),
        "binary_unchanged": binary_hash == sha(binary),
        "data_unchanged": all(sha(ROOT / case["path"]) == case["sha256"] for case in plan["cases"]),
        "binary_snapshot_unchanged": receipt.get("binary_snapshot_unchanged", False),
    }
    receipt["fit_budget_passed"] = budget.calls <= budget.limit
    receipt["functional_passed"] = receipt["inference_completed"] and len(receipt["cases"]) == 2 and all(
        case["functional_passed"] for case in receipt["cases"]) and all(receipt["integrity"].values()) and budget.calls == budget.limit and not receipt["operational_failures"]
    receipt["finished_utc"] = datetime.now(timezone.utc).isoformat()
    save(out / "receipt.json", receipt)
    progress({"event": "primary_complete", "receipt": str(out / "receipt.json"),
              "functional_passed": receipt["functional_passed"], "actual_fit_calls_total": budget.calls,
              "inference_completed": receipt["inference_completed"], "process_wall_s": receipt["process_wall_s"]})
    return 0 if receipt["functional_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
