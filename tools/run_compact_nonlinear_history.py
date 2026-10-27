#!/usr/bin/env python3
"""One finite compact-history invocation; no Python scientific computation.

The primary C process closes before either optional exact-audit child starts.
Every child stdout is preserved by the separately qualified capture transaction.
An intact duplicate never converts a changed original into a successful run.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import resource
import selectors
import signal
import stat
import struct
import subprocess
import sys
import time


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
EXP = "experiments/compact_nonlinear_history_001"
PLAN = "plans/compact_nonlinear_history_001.json"
PLAN_SHA256 = "bb5384b268e2b2c4cde0dd45aa7bf14dff768bb93a281c5636c05d6ba76fd7cf"
SCHEMA = "mumble_compact_nonlinear_history_run_v1"
PRIMARY_SCHEMA = "mumble_compact_nonlinear_history_primary_v1"
AUDIT_SCHEMA = "mumble_compact_nonlinear_history_audit_v1"
CAPTURE_PATH = ROOT / "tools/capture_preservation.py"
CAPTURE_SHA256 = "14f1ec0c73a816ffa0c441b6a5af465115e98080d1948d452f41a28ea30e5207"
CAPTURE_RECEIPT = "experiments/capture_preservation_001/attempt001/receipt.json"
CAPTURE_RECEIPT_SHA256 = "ee57549314b080a2c4b3d9e1a38d3ac144a7ce964d7090c9ae87a05dc1231a2b"
SOURCE_ID = "f0bd54ce53f1944d4f17070b6380dc8317ae895f2fd1628198a1c5408a67f79c"
ARCHIVE_MEMBER = "experiments/continuous_learning_validation_001/implementation/primary/B_continuous/source/observations.bin"
ARCHIVE_IDENTITY = {"bytes": 16128000, "sha256": "cdbf064028753eb1abf6f33ba2512853ecb58e21493791a269a4b5956545849f"}
PRIMARY_RECORDS = 294000
PRIMARY_PREFIX_SHA256 = "b8a1f6956cfe3a23ef6ffe74eaae765aad9bea02664ebdb6817690e1d1f777ba"
CHECKPOINTS = (252000, 294000)
ARMS = ("public_origin", "autonomous_origin")
MODEL_STEP_CAP = 14028000
LIMITS = {"CPU_s": 90., "wall_s": 120., "RSS_bytes": 134217728,
          "AS_bytes": 1073741824, "output_bytes": 8388608,
          "child_capture_bytes": 2097152, "proposal_rounds": 64, "trial_evaluations": 512,
          "query_evaluations": 1024, "prior_evaluations": 1024}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "Duplicate JSON key: " + key)
        result[key] = value
    return result


def _number_token(text):
    value = float(text)
    require(math.isfinite(value), "Nonfinite JSON number")
    return value


def _constant(text):
    raise ValueError("Nonfinite JSON constant: " + text)


def strict_json(data):
    return json.loads(data, object_pairs_hook=_pairs, parse_float=_number_token, parse_constant=_constant)


def read_json(path):
    return strict_json(Path(path).read_bytes())


def encode_json(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def identity(path):
    digest, count = hashlib.sha256(), 0
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as handle:
        require(stat.S_ISREG(os.fstat(handle.fileno()).st_mode), "Expected regular file: " + str(path))
        while block := handle.read(1048576):
            count += len(block)
            digest.update(block)
    return {"bytes": count, "sha256": digest.hexdigest()}


def fsync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def reserve_directory(path):
    Path(path).mkdir(exist_ok=False)
    fsync_directory(Path(path).parent)


def write_bytes(path, data):
    with Path(path).open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    fsync_directory(Path(path).parent)
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def write_json(path, value, maximum=2097152):
    data = encode_json(value)
    require(len(data) <= maximum, "JSON output cap: " + str(path))
    return write_bytes(path, data)


def safe(root, relative):
    relative = Path(relative)
    require(not relative.is_absolute() and ".." not in relative.parts, "Unsafe relative path")
    root = Path(root).resolve()
    path = root / relative
    require(not path.is_symlink(), "Symlink is not an admitted role")
    resolved = path.resolve()
    require(resolved.is_relative_to(root), "Role escapes its root")
    return resolved


def manifest(directory):
    rows = {}
    for path in sorted(Path(directory).rglob("*")):
        require(not path.is_symlink(), "Symlink in closed output")
        if path.is_file():
            rows[path.relative_to(directory).as_posix()] = identity(path)
    return rows


def bind(rows, path, expected, label):
    path = Path(path).resolve()
    expected = {"bytes": expected["bytes"], "sha256": expected["sha256"]}
    require(identity(path) == expected, "Bound identity differs: " + label)
    row = {"path": str(path), "label": label, **expected}
    previous = rows.get(str(path))
    require(previous is None or previous == row, "Conflicting binding: " + label)
    rows[str(path)] = row
    return row


def rehash(rows):
    for row in rows.values() if isinstance(rows, dict) else rows:
        require(identity(row["path"]) == {"bytes": row["bytes"], "sha256": row["sha256"]},
                "Bound file changed: " + row["path"])


def own_peak_bytes():
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * (1 if sys.platform == "darwin" else 1024)


def load_capture():
    require(identity(CAPTURE_PATH)["sha256"] == CAPTURE_SHA256, "Qualified capture source differs")
    specification = importlib.util.spec_from_file_location("compact_history_capture", CAPTURE_PATH)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def stop_group(pid):
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def supervise_capture(command, transaction, bounds):
    """Exact wait4 plus qualified, independently duplicated stdout capture.

    Callers reserve work and fsync launch metadata before entering this function.
    A committed capture is raw evidence only; exit/resource status remains an
    independent gate. Neither this function nor the capture module parses JSON.
    """
    started = time.monotonic()
    writer = transaction.open_original()
    stderr_file = (transaction.directory / "probe.stderr").open("xb")
    stdout_read, stdout_write = os.pipe()
    stderr_read, stderr_write = os.pipe()
    pid = os.fork()
    if pid == 0:
        try:
            os.setsid()
            os.dup2(stdout_write, 1)
            os.dup2(stderr_write, 2)
            for descriptor in (stdout_read, stdout_write, stderr_read, stderr_write):
                if descriptor not in (1, 2):
                    os.close(descriptor)
            cpu = max(1, math.ceil(bounds["CPU_s"]))
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
            resource.setrlimit(resource.RLIMIT_AS, (bounds["AS_bytes"],) * 2)
            resource.setrlimit(resource.RLIMIT_FSIZE, (bounds["capture_bytes"],) * 2)
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            os.execve(command[0], command, os.environ.copy())
        except BaseException as error:
            os.write(2, ("Child exec/setup failed: " + repr(error) + "\n").encode()[:4096])
            os._exit(127)
    os.close(stdout_write)
    os.close(stderr_write)
    selector = selectors.DefaultSelector()
    for descriptor, role in ((stdout_read, "stdout"), (stderr_read, "stderr")):
        os.set_blocking(descriptor, False)
        selector.register(descriptor, selectors.EVENT_READ, role)
    observed = {"stdout": 0, "stderr": 0}
    written = {"stdout": 0, "stderr": 0}
    violations, capture_errors = [], []
    status = usage = reaped_wall = None
    killed = False

    def violate(reason):
        nonlocal killed
        if reason not in violations:
            violations.append(reason)
        if not killed:
            stop_group(pid)
            killed = True

    try:
        while selector.get_map() or usage is None:
            elapsed = time.monotonic() - started
            if elapsed > bounds["wall_s"]:
                violate("child_wall_limit")
            if own_peak_bytes() > bounds["RSS_bytes"]:
                violate("supervisor_RSS_limit")
            if usage is None:
                waited, child_status, child_usage = os.wait4(pid, os.WNOHANG)
                if waited:
                    status, usage = child_status, child_usage
                    reaped_wall = time.monotonic() - started
            for key, _ in selector.select(0.02):
                try:
                    chunk = os.read(key.fd, 65536)
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(key.fd)
                    os.close(key.fd)
                    continue
                role = key.data
                observed[role] += len(chunk)
                remaining = bounds["capture_bytes"] - sum(written.values())
                kept = chunk[:max(0, remaining)]
                if role == "stdout":
                    writer.write(kept)
                else:
                    stderr_file.write(kept)
                written[role] += len(kept)
                if len(kept) != len(chunk):
                    violate("combined_stdout_stderr_limit")
            if killed and usage is not None and elapsed > bounds["wall_s"] + 1.:
                break
    except BaseException as error:
        violate("supervisor_exception:" + type(error).__name__ + ":" + str(error))
    finally:
        if usage is None:
            stop_group(pid)
            _, status, usage = os.wait4(pid, 0)
            reaped_wall = time.monotonic() - started
        for key in list(selector.get_map().values()):
            selector.unregister(key.fd)
            os.close(key.fd)
        selector.close()
        try:
            writer.close()
        except Exception as error:
            capture_errors.append({"stage": "writer_close", "type": type(error).__name__, "message": str(error)})
        stderr_file.flush()
        os.fsync(stderr_file.fileno())
        stderr_file.close()
        fsync_directory(transaction.directory)
    written["stdout"] = writer.bytes
    cpu_s = usage.ru_utime + usage.ru_stime
    rss = int(usage.ru_maxrss) * (1 if sys.platform == "darwin" else 1024)
    if cpu_s > bounds["CPU_s"]:
        violations.append("child_CPU_limit")
    if rss > bounds["RSS_bytes"]:
        violations.append("child_RSS_limit")
    if reaped_wall > bounds["wall_s"] and "child_wall_limit" not in violations:
        violations.append("child_wall_limit")
    commit_identity = None
    try:
        commit_identity = transaction.commit()
    except Exception as error:
        capture_errors.append({"stage": "capture_commit", "type": type(error).__name__, "message": str(error)})
    return {"child_launched": True, "pid": pid, "command": command,
            "exit_code": os.waitstatus_to_exitcode(status), "CPU_user_s": usage.ru_utime,
            "CPU_system_s": usage.ru_stime, "CPU_total_s": cpu_s,
            "wall_s_through_wait4": reaped_wall, "peak_RSS_bytes": rss,
            "RSS_method": "Exact wait4 high-water for this PID and waited descendants; not summed concurrent memory",
            "stdout_stderr_bytes_written": written, "stdout_stderr_bytes_observed": observed,
            "output_truncated": observed != written, "bounds": bounds, "resource_violations": violations,
            "capture_commit_identity": commit_identity, "capture_errors": capture_errors,
            "capture_closed_before_dependent_read": commit_identity is not None}


def valid_process(process):
    require(process["child_launched"] is True and process["exit_code"] == 0 and
            not process["resource_violations"] and process["output_truncated"] is False and
            not process["capture_errors"] and process["capture_commit_identity"] is not None,
            "Child exit/resource/capture failure")


def nonnegative_int(value, label):
    require(type(value) is int and value >= 0, "Invalid integer: " + label)
    return value


def vector(value, label):
    require(isinstance(value, list) and len(value) == 16, "Wrong 16D vector: " + label)
    require(all(type(v) in (float, int) and math.isfinite(v) for v in value), "Nonfinite vector: " + label)
    return value


def same_vector(left, right):
    return all(struct.pack("<d", a) == struct.pack("<d", b) for a, b in zip(left, right))


def finite_number(value, label):
    require(type(value) in (float, int) and math.isfinite(value), "Invalid finite value: " + label)
    return value


def validate_exact_points(points, count, prefix, expected_vectors=None):
    require(isinstance(points, list) and len(points) == count, "Exact-point inventory differs")
    steps = 0
    for index, point in enumerate(points):
        require(point["index"] == index, "Exact-point order differs")
        x = vector(point["x"], "exact entering point")
        if expected_vectors is not None:
            require(same_vector(x, expected_vectors[index]), "Exact point differs from declared input")
        attempted = nonnegative_int(point["model_steps"], "exact model attempts")
        accumulated = nonnegative_int(point["records_accumulated"], "exact accumulated records")
        require(accumulated <= attempted <= prefix, "Exact-point work exceeds prefix")
        steps += attempted
        if point["status"] == "available":
            require(point["status_code"] == 0 and attempted == accumulated == prefix and
                    point["first_unavailable_index"] is None, "Available exact point is incomplete")
            require(finite_number(point["cost"], "exact cost") >= 0., "Negative exact cost")
            vector(point["endpoint_x"], "exact endpoint")
        else:
            require(point["status"] == "unavailable" and point["status_code"] != 0 and
                    point["cost"] is None and point["endpoint_x"] is None and
                    type(point["first_unavailable_index"]) is int and
                    0 <= point["first_unavailable_index"] < prefix,
                    "Unavailable exact point was omitted or assigned a cost")
    return steps


def validate_primary(payload, expected_vectors=None):
    checkpoints = payload["checkpoints"]
    require([c["next_index"] for c in checkpoints] == list(CHECKPOINTS), "Checkpoint scope differs")
    trials = proposals = 0
    for checkpoint in checkpoints:
        require(checkpoint["complete"] is True and [a["arm"] for a in checkpoint["arms"]] == list(ARMS),
                "Checkpoint completion/arm order differs")
        prefix = checkpoint["next_index"]
        validate_exact_points(checkpoint["oracle"]["points"], 42, prefix, expected_vectors)
        for arm in checkpoint["arms"]:
            vector(arm["candidate_x"], "primary candidate")
            require(arm["refine_status"] in (0, 1) and arm["report_status"] == arm["endpoint_status"] == 0,
                    "Unsuccessful candidate/refinement result")
            require(arm["counts"]["model_steps"] == arm["counts"]["qr_rows"] == prefix,
                    "Candidate did not ingest exactly one row per record")
            for stage in ("before", "after"):
                for key in ("likelihood_cost", "prior_cost", "total_cost", "cost_absolute_scale"):
                    finite_number(arm[stage][key], "compact " + stage + " " + key)
            require([point["index"] for point in arm["fixed_points"]] == list(range(42)),
                    "Fixed diagnostic nodes were omitted or reordered")
            for point in arm["fixed_points"]:
                for mode in ("affine", "quartic"):
                    if point[mode]["status_code"] == 0:
                        finite_number(point[mode]["cost"], "compact fixed-node cost")
                    else:
                        require(point[mode]["cost"] is None, "Unavailable compact node has a cost")
            events = arm["trace"]
            require(len(events) <= 16 * 9, "Trace exceeds frozen refinement extent")
            proposals += sum(event["event"] == "proposal" for event in events)
            trials += sum(event["event"] == "trial" for event in events)
            require(all(event["event"] in ("proposal", "trial") for event in events), "Unexpected trace event")
    counts = payload["counts"]
    last = checkpoints[-1]
    candidate = sum(arm["counts"]["model_steps"] for arm in last["arms"])
    oracle = sum(point["model_steps"] for point in last["oracle"]["points"])
    require(candidate == counts["candidate_model_steps"] == 2 * PRIMARY_RECORDS and
            oracle == counts["oracle_model_steps"] and candidate + oracle == counts["model_steps"],
            "Primary model counter decomposition differs")
    require(trials == counts["trial_evaluations"] and proposals <= counts["proposal_rounds"],
            "Trace/work counter decomposition differs")
    for key in ("query_evaluations", "prior_evaluations", "proposal_rounds", "accepted_steps"):
        require(sum(arm["counts"][key] for arm in last["arms"]) == counts[key], "Bank counter sum differs: " + key)


def summarize_fidelity(primary, audits):
    """Saved scalar comparisons only; no prior, sketch query, model or optimizer."""
    comparisons = []
    for checkpoint, audit in zip(primary["checkpoints"], audits):
        arms = []
        for arm_index, (arm, exact_candidate) in enumerate(zip(checkpoint["arms"], audit["points"])):
            modes = {}
            for mode in ("affine", "quartic"):
                rows, errors = [], []
                origin = None
                for approximate, exact in zip(arm["fixed_points"], checkpoint["oracle"]["points"]):
                    available = approximate[mode]["status_code"] == 0 and exact["status"] == "available"
                    error = math.fsum([approximate[mode]["cost"], -exact["cost"]]) if available else None
                    rows.append({"index": exact["index"], "oracle_status": exact["status"],
                                 "compact_status_code": approximate[mode]["status_code"],
                                 "exact_cost": exact["cost"], "compact_cost": approximate[mode]["cost"],
                                 "compact_minus_exact": error})
                    if available:
                        errors.append(error)
                    if exact["index"] == arm_index:
                        origin = error
                for row in rows:
                    row["centered_error_at_origin"] = (math.fsum([row["compact_minus_exact"], -origin])
                                                         if origin is not None and row["compact_minus_exact"] is not None else None)
                modes[mode] = {"reference_index": arm_index, "offset_at_origin": origin,
                               "available_points": len(errors), "points": rows,
                               "error_min": min(errors) if errors else None,
                               "error_max": max(errors) if errors else None,
                               "error_oscillation": math.fsum([max(errors), -min(errors)]) if errors else None}
            require(exact_candidate["status"] == "available", "Selected candidate lacks an exact audit")
            arms.append({"arm": arm["arm"], "candidate_x": arm["candidate_x"],
                         "Q_Ah": math.exp(arm["candidate_x"][5]),
                         "refine_status": arm["refine_status"], "refinement_stop": arm["refinement_stop"],
                         "before": arm["before"], "after": arm["after"], "compact_endpoint": arm["endpoint"],
                         "exact_audit_cost": exact_candidate["cost"], "exact_audit_endpoint_x": exact_candidate["endpoint_x"],
                         "compact_minus_exact_likelihood_cost": math.fsum([arm["after"]["likelihood_cost"], -exact_candidate["cost"]]),
                         "audit_likelihood_plus_cached_prior": math.fsum([exact_candidate["cost"], arm["after"]["prior_cost"]]),
                         "fixed_node_fidelity": modes})
        comparisons.append({"next_index": checkpoint["next_index"], "arms": arms})
    return {"checkpoints": comparisons, "model_calls": 0, "prior_evaluations": 0,
            "oracle_feedback_to_acceptance": False,
            "interpretation": "Finite saved-node cost/relative-log-likelihood diagnostics only; no continuous-domain, calibrated coverage or exact nonlinear convergence claim."}


def git_bytes(root, revision, relative):
    result = subprocess.run(["git", "-C", str(root), "show", revision + ":" + relative],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=10)
    require(result.returncode == 0, "Published source file unavailable: " + relative)
    return result.stdout


def verify_source_revision(root, revision, sources):
    require(len(revision) == 40 and all(c in "0123456789abcdef" for c in revision), "Invalid source revision")
    for relative, expected in sources.items():
        data = git_bytes(root, revision, relative)
        require({"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()} == expected,
                "Source revision does not bind " + relative)


def scan_prefix(path):
    """Input-only validation/integrals; no model, fitting or prior evaluation."""
    digest = hashlib.sha256()
    elapsed = charge = minimum = maximum = max_current = 0.
    checkpoints = []
    with Path(path).open("rb") as handle:
        for index in range(PRIMARY_RECORDS):
            raw = handle.read(32)
            require(len(raw) == 32, "Short primary observation prefix")
            observed_index, dt, current, voltage = struct.unpack("<Qddd", raw)
            require(observed_index == index and all(math.isfinite(v) for v in (dt, current, voltage)) and
                    0. <= dt <= 1. and abs(current) <= .25,
                    "Invalid ordered observation record")
            digest.update(raw)
            elapsed += dt
            charge += current * dt / 3600.
            minimum, maximum = min(minimum, charge), max(maximum, charge)
            max_current = max(max_current, abs(current))
            require(all(math.isfinite(v) for v in (elapsed, charge)), "Nonfinite input integral")
            if index + 1 in CHECKPOINTS:
                checkpoints.append({"next_index": index + 1, "prefix_bytes": 32 * (index + 1),
                                    "prefix_sha256": digest.copy().hexdigest(), "elapsed_s": elapsed,
                                    "charge_Ah": charge, "charge_min_Ah": minimum, "charge_max_Ah": maximum})
    return {"records": PRIMARY_RECORDS, "bytes": PRIMARY_RECORDS * 32, "sha256": digest.hexdigest(),
            "checkpoints": checkpoints, "maximum_abs_current_A": max_current,
            "model_calls": 0, "prior_evaluations": 0, "scan_passes": 1}


def close_receipt(directory, receipt, maximum):
    files = manifest(directory)
    receipt["files"] = files
    receipt["closed_output_bytes_including_receipt"] = 0
    for _ in range(24):
        value = sum(row["bytes"] for row in files.values()) + len(encode_json(receipt))
        if value == receipt["closed_output_bytes_including_receipt"]:
            break
        receipt["closed_output_bytes_including_receipt"] = value
    else:
        raise ValueError("Receipt size did not stabilize")
    if value > maximum:
        receipt["status"] = "failed"
        receipt["errors"].append({"stage": "closure", "type": "ResourceFailure", "message": "Closed output cap"})
        for _ in range(24):
            value = sum(row["bytes"] for row in files.values()) + len(encode_json(receipt))
            if value == receipt["closed_output_bytes_including_receipt"]:
                break
            receipt["closed_output_bytes_including_receipt"] = value
    write_json(Path(directory) / "receipt.json", receipt)
    return receipt


def validate_manifest(directory, receipt):
    actual = manifest(directory)
    own = actual.pop("receipt.json")
    require(actual == receipt["files"], "Closed manifest differs")
    require(sum(row["bytes"] for row in actual.values()) + own["bytes"] ==
            receipt["closed_output_bytes_including_receipt"], "Closed byte total differs")


def validate_closed_attempt(directory, receipt, result):
    """Reconstruct successful scope from committed child evidence, without models."""
    require(receipt["schema"] == result["schema"] == SCHEMA and
            receipt["status"] == result["status"] == "completed" and
            receipt["canonical_inference_closed"] is True and receipt["errors"] == result["errors"] == [],
            "Attempt is not a complete successful closure")
    validate_manifest(directory, receipt)
    rehash(receipt["source_bindings"])
    rehash(receipt["input_bindings"])
    rehash(receipt["generated_bindings"])
    counts = receipt["counts"]
    require(counts == result["counts"] and counts["canonical_invocations"] == 1 and counts["retries"] == 0,
            "Result/receipt invocation counts differ")
    for prefix in ("primary", "audits"):
        expected = 1 if prefix == "primary" else 2
        require(counts[prefix + "_reserved"] == counts[prefix + "_launched"] ==
                counts[prefix + "_completed"] == expected, "Incomplete child sequence")
    require(counts["model_steps_reserved_upper_bound"] == MODEL_STEP_CAP and
            counts["model_step_count_complete"] is True and counts["worker_counts_complete"] is True and
            counts["child_launch_count_complete"] is True,
            "Incomplete work accounting")
    for key in ("truth_reads", "historical_summary_reads", "old_learner_calls", "original_fitter_calls", "source_generations"):
        require(counts[key] == 0, "Forbidden scientific activity")
    children = receipt["children"]
    require([(row["mode"], row["prefix_records"]) for row in children] ==
            [("primary", PRIMARY_RECORDS), ("audit", CHECKPOINTS[0]), ("audit", CHECKPOINTS[1])],
            "Child role/order differs")
    capture = load_capture()
    totals = {"model_steps": 0, "prior_evaluations": 0, "proposal_rounds": 0,
              "trial_evaluations": 0, "query_evaluations": 0}
    payloads = []
    actual_capture_bindings = []
    for child in children:
        require(child["launched"] is True and child["counts_reported_complete"] is True,
                "Child activity is not complete")
        process = child["process"]
        valid_process(process)
        location = Path(child["directory"])
        require(location.is_relative_to(directory) and location.parent == Path(directory) / "calls",
                "Capture escaped this attempt")
        expected_commit = process["capture_commit_identity"]
        require(child["payload"] == {"capture_directory": str(location), "commit_identity": expected_commit},
                "Child payload capture binding differs")
        payload = strict_json(capture.load_verified(location, expected_commit))
        require(payload["status"] == "completed" and payload["source_id"] == SOURCE_ID and
                payload["prefix_records"] == child["prefix_records"] and
                payload["counts"] == child["reported_counts"] and payload["counts"]["counts_complete"] is True,
                "Committed payload scope/counts differ")
        require(payload["counts"]["records_read"] == child["prefix_records"] and
                payload["counts"]["input_bytes_read"] == child["prefix_records"] * 32,
                "Input extent differs")
        require(payload["counts"]["model_steps"] <= child["maximum_model_steps"], "Child model-step cap")
        for key in totals:
            totals[key] += nonnegative_int(payload["counts"][key], key)
        actual_capture_bindings.append({"directory": str(location), "identity": expected_commit})
        payloads.append(payload)
    require(actual_capture_bindings == receipt["capture_bindings"], "Capture closure inventory differs")
    for key, total in totals.items():
        require(counts[key + "_reported"] == total, "Child counter sum differs: " + key)
        maximum = MODEL_STEP_CAP if key == "model_steps" else LIMITS[key]
        require(total <= maximum, "Cumulative work cap: " + key)
    primary = payloads[0]
    require(primary["schema"] == PRIMARY_SCHEMA and
            [row["next_index"] for row in primary["checkpoints"]] == list(CHECKPOINTS), "Primary scope differs")
    validate_primary(primary)
    for checkpoint, audit in zip(primary["checkpoints"], payloads[1:]):
        require([arm["arm"] for arm in checkpoint["arms"]] == list(ARMS) and audit["schema"] == AUDIT_SCHEMA,
                "Arm or audit role differs")
        require(audit["counts"]["model_steps"] == 2 * checkpoint["next_index"] and len(audit["points"]) == 2,
                "Audit model scope differs")
        require(validate_exact_points(audit["points"], 2, checkpoint["next_index"]) == audit["counts"]["model_steps"],
                "Audit point/model counter sum differs")
        for arm, audited in zip(checkpoint["arms"], audit["points"]):
            require(same_vector(vector(arm["candidate_x"], "closed candidate"), vector(audited["x"], "closed audit")),
                    "Post-primary audit changed the internally selected point")
        require(all(audit["counts"][key] == 0 for key in
                    ("prior_evaluations", "proposal_rounds", "trial_evaluations", "query_evaluations")),
                "Audit fed additional inference work")
    require(result["audit_feedback_to_primary"] is False, "Audit fed back to inference")


class Run:
    def __init__(self, args):
        self.args = args
        self.root = Path(args.root).resolve()
        self.output = self.root / EXP / "attempt001"
        self.start = time.monotonic()
        self.capture = load_capture()
        self.sources, self.inputs, self.generated = {}, {}, {}
        self.children, self.captures = [], []
        self.stage, self.primary, self.audits = "reservation", None, []
        self.comparison = None
        self.plan_identity = None
        self.counts = {"canonical_invocations": 1, "primary_reserved": 0, "primary_launched": 0,
                       "primary_completed": 0, "audits_reserved": 0, "audits_launched": 0,
                       "audits_completed": 0, "model_steps_reserved_upper_bound": 0,
                       "model_steps_reported": 0, "model_step_count_complete": True,
                       "prior_evaluations_reported": 0, "proposal_rounds_reported": 0,
                       "trial_evaluations_reported": 0, "query_evaluations_reported": 0,
                       "worker_counts_complete": True, "child_launch_count_complete": True,
                       "truth_reads": 0, "historical_summary_reads": 0, "old_learner_calls": 0,
                       "original_fitter_calls": 0, "source_generations": 0, "retries": 0}

    def usage(self):
        own = resource.getrusage(resource.RUSAGE_SELF)
        children = resource.getrusage(resource.RUSAGE_CHILDREN)
        return {"CPU_self_s": own.ru_utime + own.ru_stime,
                "CPU_waited_children_s": children.ru_utime + children.ru_stime,
                "CPU_total_s": own.ru_utime + own.ru_stime + children.ru_utime + children.ru_stime,
                "wall_s": time.monotonic() - self.start, "supervisor_peak_RSS_bytes": own_peak_bytes()}

    def write(self, name, value):
        path = self.output / name
        identity_row = write_json(path, value)
        self.generated[str(path)] = {"path": str(path), "label": name, **identity_row}
        return path

    def recheck(self):
        rehash(self.sources)
        rehash(self.inputs)
        rehash(self.generated)
        for row in self.captures:
            self.capture.load_verified(row["directory"], row["identity"])
        used = self.usage()
        require(used["CPU_total_s"] <= LIMITS["CPU_s"] and used["wall_s"] <= LIMITS["wall_s"],
                "Cumulative CPU/wall cap")
        require(used["supervisor_peak_RSS_bytes"] <= LIMITS["RSS_bytes"], "Supervisor RSS cap")
        require(sum(row["bytes"] for row in manifest(self.output).values()) <= LIMITS["output_bytes"] - 262144,
                "Runtime output cap/closure reserve")
        return used

    def preflight(self):
        self.stage = "preflight"
        require(self.root == ROOT, "Wrong source root")
        executable_path = safe(self.root, self.args.executable_receipt)
        executable = read_json(executable_path)
        require(executable["schema"] == "mumble_compact_nonlinear_history_executable_receipt_v1" and
                executable["status"] == "qualified_before_canonical_invocation" and
                executable["source_revision"] == self.args.source_revision and
                executable["qualification"]["passed"] is True, "Executable is not qualified/bound")
        bind(self.inputs, executable_path, identity(executable_path), "executable_receipt")
        self.plan_identity = identity(self.root / PLAN)
        require(self.plan_identity["sha256"] == executable["plan_sha256"] == PLAN_SHA256, "Plan receipt mismatch")
        self.plan = read_json(self.root / PLAN)
        require(self.plan["schema"] == "mumble_compact_nonlinear_history_contract_v1" and
                self.plan["status"] == "frozen_before_canonical_inference", "Contract is not frozen")
        declared = self.plan["input"]
        require(declared["source_id"] == SOURCE_ID and declared["evidence_member"] == ARCHIVE_MEMBER and
                {"bytes": declared["full_bytes"], "sha256": declared["full_sha256"]} == ARCHIVE_IDENTITY and
                declared["prefix_records"] == PRIMARY_RECORDS and declared["prefix_bytes"] == 32 * PRIMARY_RECORDS and
                declared["prefix_sha256"] == PRIMARY_PREFIX_SHA256 and declared["checkpoints"] == list(CHECKPOINTS),
                "Contract input extent differs")
        required_limits = {"canonical_invocations_max": 1, "scientific_children_max": 3,
                           "primary_children_max": 1, "audit_children_max": 2,
                           "model_steps_max": MODEL_STEP_CAP, "proposal_rounds_max": LIMITS["proposal_rounds"],
                           "trial_evaluations_max": LIMITS["trial_evaluations"],
                           "query_evaluations_max": LIMITS["query_evaluations"],
                           "prior_evaluations_max": LIMITS["prior_evaluations"],
                           "CPU_total_s_max": LIMITS["CPU_s"], "wall_total_s_max": LIMITS["wall_s"],
                           "RSS_bytes_max": LIMITS["RSS_bytes"], "address_space_bytes_max": LIMITS["AS_bytes"],
                           "child_capture_bytes_max": LIMITS["child_capture_bytes"],
                           "closed_output_bytes_max": LIMITS["output_bytes"], "retries_max": 0}
        require(all(self.plan["limits"][key] == value for key, value in required_limits.items()),
                "Frozen resource/work policy differs")
        sources = executable["source_identities"]
        required = {PLAN, "tools/run_compact_nonlinear_history.py", "tools/execute_compact_history_once.py",
                    "tools/capture_preservation.py", CAPTURE_RECEIPT, EXP + "/probe.c",
                    EXP + "/compact_history.c", EXP + "/compact_history.h", "src/scm_model.c", "include/scm_model.h",
                    EXP + "/prepare_queries.py", EXP + "/build.py", executable["build_receipt"]["path"],
                    EXP + "/qualification/supervisor.json", EXP + "/qualification/supervisor_fixture.py",
                    EXP + "/qualification/supervisor_plan.json", EXP + "/qualification/supervisor_source_freeze.json",
                    declared["prepared_points"], declared["preparation_receipt"],
                    executable["independent_review"]["path"]}
        require(required <= set(sources), "Missing required published source identities")
        for relative, expected in sources.items():
            require(not any(part in relative for part in ("/summary.json", "/truth", "historical_likelihood_control_001/attempt")),
                    "Unexpected historical summary/truth source binding")
            bind(self.sources, safe(self.root, relative), expected, relative)
        verify_source_revision(self.root, self.args.source_revision, sources)
        require(identity(self.root / CAPTURE_RECEIPT)["sha256"] == CAPTURE_RECEIPT_SHA256,
                "Capture qualification differs")
        require(read_json(self.root / CAPTURE_RECEIPT)["status"] == "passed", "Capture is not qualified")
        integration = read_json(self.root / EXP / "qualification/supervisor.json")
        require(integration["schema"] == "mumble_compact_history_supervisor_qualification_v1" and
                integration["status"] == "passed" and
                integration["counts"]["real_fabricated_children_completed"] == 1 and
                integration["counts"]["child_activity_complete"] is True, "Capture integration is not qualified")
        for relative in ("tools/run_compact_nonlinear_history.py", "tools/execute_compact_history_once.py",
                         "tools/capture_preservation.py"):
            require({key: integration["sources"][relative][key] for key in ("bytes", "sha256")} == sources[relative],
                    "Integration qualification source differs: " + relative)
        review = executable["independent_review"]
        review_path = safe(self.root, review["path"])
        bind(self.sources, review_path, review, review["path"])
        require(read_json(review_path)["status"] in ("passed", "pass"), "Source review has not passed")
        self.binary = safe(self.root, executable["binary"]["path"])
        bind(self.sources, self.binary, executable["binary"], executable["binary"]["path"])
        require(os.access(self.binary, os.X_OK), "Qualified binary is not executable")
        selected_build = executable["build_receipt"]
        require(selected_build["path"].startswith(EXP + "/build") and selected_build["path"].endswith("_receipt.json"),
                "Unexpected build receipt role")
        build_path = safe(self.root, selected_build["path"])
        bind(self.sources, build_path, selected_build, selected_build["path"])
        build = read_json(build_path)
        require(build["schema"] == "mumble_compact_nonlinear_history_build_v1" and
                build["status"] == "passed" and build["binary"] == executable["binary"], "Build/binary receipt mismatch")
        require(all(relative in sources and sources[relative] == expected
                    for relative, expected in build["source_identities"].items()), "Build-source binding mismatch")
        self.python = Path(sys.executable).resolve()
        require(executable["python"]["path"] == str(self.python) and executable["python"]["version"] == sys.version,
                "Python runtime mismatch")
        bind(self.sources, self.python, executable["python"], "python")
        self.observations = safe(Path(self.args.evidence_root), ARCHIVE_MEMBER)
        bind(self.inputs, self.observations, ARCHIVE_IDENTITY, "observation_archive")
        # Root supplies only the declared prepared diagnostic/warm-start nodes.
        self.points = safe(self.root, declared["prepared_points"])
        preparation_path = safe(self.root, declared["preparation_receipt"])
        bind(self.inputs, preparation_path, sources[declared["preparation_receipt"]], "preparation_receipt")
        prepared = read_json(preparation_path)
        require(prepared["schema"] == "mumble_compact_nonlinear_history_preparation_v1" and
                prepared["status"] == "completed" and prepared["source_id"] == SOURCE_ID and
                prepared["plan"] == {"path": PLAN, **self.plan_identity}, "Prepared-input provenance differs")
        query_record = prepared["queries"]
        require(query_record["path"] == declared["prepared_points"] and
                query_record["rows"] == 42 and query_record["columns"] == 16, "Prepared query extent differs")
        bind(self.inputs, self.points, query_record, "prepared_points")
        expected_preparation_inputs = {declared["public_configuration"]: declared["public_configuration_sha256"],
                                       declared["warm_generation"]: declared["warm_generation_sha256"],
                                       declared["warm_evaluator"]: declared["warm_evaluator_sha256"]}
        require(set(prepared["inputs"]) == set(expected_preparation_inputs), "Unexpected preparation input")
        for relative, expected in prepared["inputs"].items():
            require(expected["sha256"] == expected_preparation_inputs[relative], "Preparation input differs from contract")
            bind(self.inputs, safe(self.root, relative), expected, "preparation_input_hash_only:" + relative)
            data = git_bytes(self.root, self.plan["base_revision"], relative)
            require({"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()} == expected,
                    "Preparation input is not the frozen published base member")
        preparation_source = prepared["preparation_source"]
        require(preparation_source["path"] in sources, "Unbound preparation implementation")
        bind(self.sources, safe(self.root, preparation_source["path"]), preparation_source, preparation_source["path"])
        rows = [[float(v) for v in line.split()] for line in self.points.read_text().splitlines()]
        require(len(rows) == len(prepared["nodes"]) == 42, "Prepared query row count differs")
        for index, (point, node) in enumerate(zip(rows, prepared["nodes"])):
            require(node["index"] == index and same_vector(vector(point, "prepared row"), vector(node["x"], "prepared node")),
                    "Prepared text/node binary64 values differ")
        self.prepared_vectors = rows
        prefix = scan_prefix(self.observations)
        require(prefix["sha256"] == PRIMARY_PREFIX_SHA256, "Primary prefix hash differs")
        self.write("prefix_input.json", prefix)
        self.recheck()

    def child(self, name, mode, prefix, points, point_vectors=None):
        self.stage = mode
        usage = self.recheck()
        before = dict(self.counts)
        maximum_steps = 44 * prefix if mode == "primary" else 2 * prefix
        key = "primary" if mode == "primary" else "audits"
        require(self.counts[key + "_reserved"] < (1 if mode == "primary" else 2), "Child invocation cap")
        self.counts[key + "_reserved"] += 1
        self.counts["model_steps_reserved_upper_bound"] += maximum_steps
        require(self.counts["model_steps_reserved_upper_bound"] <= MODEL_STEP_CAP, "Reserved model-step cap")
        self.counts["model_step_count_complete"] = False
        self.counts["worker_counts_complete"] = False
        self.counts["child_launch_count_complete"] = False
        directory = self.output / "calls" / name
        current_bytes = sum(row["bytes"] for row in manifest(self.output).values())
        capture_cap = min(LIMITS["child_capture_bytes"], (LIMITS["output_bytes"] - current_bytes - 524288) // 2)
        require(capture_cap > 0, "No capture/duplicate/closure budget remains")
        bounds = {"CPU_s": LIMITS["CPU_s"] - usage["CPU_total_s"],
                  "wall_s": LIMITS["wall_s"] - usage["wall_s"], "RSS_bytes": LIMITS["RSS_bytes"],
                  "AS_bytes": LIMITS["AS_bytes"], "capture_bytes": capture_cap}
        require(bounds["CPU_s"] > 0. and bounds["wall_s"] > 0., "No process budget remains")
        command = [str(self.binary), "--mode", mode, "--observations", str(self.observations),
                   "--prefix", str(prefix), "--points", str(points), "--source-id", SOURCE_ID]
        transaction = self.capture.CaptureTransaction.reserve(
            directory, max_bytes=capture_cap,
            context={"schema": SCHEMA, "kind": "child_capture", "mode": mode,
                     "source_revision": self.args.source_revision, "plan_sha256": self.plan_identity["sha256"]})
        reservation = {"schema": SCHEMA, "mode": mode, "prefix_records": prefix,
                       "command": command, "maximum_model_steps": maximum_steps,
                       "counts_before": before, "counts_after_reservation": dict(self.counts),
                       "source_bindings": list(self.sources.values()), "input_bindings": list(self.inputs.values()),
                       "point_file": {"path": str(points), **identity(points)}, "bounds": bounds,
                       "utc": datetime.now(timezone.utc).isoformat(), "retries": 0}
        self.write("calls/" + name + "/launch.json", reservation)
        row = {"name": name, "mode": mode, "prefix_records": prefix,
               "maximum_model_steps": maximum_steps, "directory": str(directory),
               "launched": None, "counts_reported_complete": False, "process": None, "payload": None}
        self.children.append(row)
        process = supervise_capture(command, transaction, bounds)
        row["process"] = process
        row["launched"] = process["child_launched"]
        self.counts["child_launch_count_complete"] = all(row["launched"] is not None for row in self.children)
        if process["child_launched"]:
            self.counts[key + "_launched"] += 1
        self.write("calls/" + name + "/resources.json", process)
        if process["capture_commit_identity"] is not None:
            binding = {"directory": str(directory), "identity": process["capture_commit_identity"]}
            self.captures.append(binding)
            try:
                payload = strict_json(self.capture.load_verified(directory, binding["identity"]))
                row["payload"] = {"capture_directory": str(directory), "commit_identity": binding["identity"]}
                reported = payload["counts"]
                steps = nonnegative_int(reported["model_steps"], "model steps")
                require(steps <= maximum_steps, "Child model-step cap")
                complete = reported["counts_complete"] is True
                self.counts["model_steps_reported"] += steps
                for source_key, destination in (("prior_evaluations", "prior_evaluations_reported"),
                                                ("proposal_rounds", "proposal_rounds_reported"),
                                                ("trial_evaluations", "trial_evaluations_reported"),
                                                ("query_evaluations", "query_evaluations_reported")):
                    self.counts[destination] += nonnegative_int(reported[source_key], source_key)
                row["reported_counts"] = reported
                row["counts_reported_complete"] = complete
                self.counts["model_step_count_complete"] = all(r["counts_reported_complete"] for r in self.children)
                self.counts["worker_counts_complete"] = self.counts["model_step_count_complete"]
            except Exception as error:
                row["parse_or_count_error"] = {"type": type(error).__name__, "message": str(error)}
                raise
        else:
            raise ValueError("No committed child stdout; progress remains unknown")
        valid_process(process)
        expected_schema = PRIMARY_SCHEMA if mode == "primary" else AUDIT_SCHEMA
        require(payload["schema"] == expected_schema and payload["status"] == "completed" and
                payload["source_id"] == SOURCE_ID and payload["prefix_records"] == prefix,
                "Child payload identity/status/scope mismatch")
        require(row["counts_reported_complete"] and reported["records_read"] == prefix and
                reported["input_bytes_read"] == 32 * prefix, "Incomplete input/worker activity")
        require(all(reported[key] == 0 for key in ("truth_reads", "source_generations", "learner_calls", "original_fitter_calls")),
                "Forbidden child scientific activity")
        require(all(self.counts[key + "_reported"] <= LIMITS[key] for key in
                    ("proposal_rounds", "trial_evaluations", "query_evaluations", "prior_evaluations")),
                "Refinement/query/prior work cap")
        if mode == "primary":
            validate_primary(payload, self.prepared_vectors)
        else:
            require(steps == 2 * prefix and len(payload["points"]) == 2, "Exact audit scope differs")
            require(validate_exact_points(payload["points"], 2, prefix, point_vectors) == steps and
                    reported["candidate_model_steps"] == 0 and reported["oracle_model_steps"] == steps,
                    "Audit point/model work decomposition differs")
            require(all(same_vector(vector(row["x"], "audit point"), expected)
                        for row, expected in zip(payload["points"], point_vectors)), "Audit vector changed")
            require(reported["prior_evaluations"] == reported["proposal_rounds"] ==
                    reported["trial_evaluations"] == reported["query_evaluations"] == 0,
                    "Audit performed inference/prior work")
        self.counts[key + "_completed"] += 1
        self.write("calls/" + name + "/completion.json",
                   {"schema": SCHEMA, "status": "completed", "capture_commit_identity": binding["identity"],
                    "reported_counts": reported, "counts_after": dict(self.counts),
                    "scientific_role": "primary" if mode == "primary" else "post_primary_audit_only"})
        self.recheck()
        return payload, row["payload"]

    def run(self):
        reserve_directory(self.output)
        reserve_directory(self.output / "calls")
        self.write("reservation.json", {"schema": SCHEMA, "kind": "run_reservation",
                   "source_revision": self.args.source_revision, "counts": dict(self.counts),
                   "limits": LIMITS, "model_step_cap": MODEL_STEP_CAP, "retries": 0})
        errors = []
        try:
            self.preflight()
            primary, reference = self.child("primary", "primary", PRIMARY_RECORDS, self.points)
            retained_proposals = sum(event["event"] == "proposal" for checkpoint in primary["checkpoints"]
                                     for arm in checkpoint["arms"] for event in arm["trace"])
            self.primary = {"capture": reference, "counts": primary["counts"], "storage": primary["storage"],
                            "proposal_trace_events": retained_proposals,
                            "proposal_rounds_without_callback": primary["counts"]["proposal_rounds"] - retained_proposals,
                            "trace_note": "Some finite early direction stops return after reserving/counting the round but before its callback."}
            self.write("primary_closed.json", {"schema": SCHEMA, "canonical_primary_closed": True,
                       "capture": reference, "counts": dict(self.counts), "audit_feedback_to_primary": False})
            for checkpoint in primary["checkpoints"]:
                index = checkpoint["next_index"]
                vectors = [arm["candidate_x"] for arm in checkpoint["arms"]]
                raw = ("\n".join(" ".join(format(float(v), ".17g") for v in point) for point in vectors) + "\n").encode()
                reconstructed = [float(v) for v in raw.split()]
                require(all(same_vector(reconstructed[16 * i:16 * (i + 1)], point)
                            for i, point in enumerate(vectors)), "Audit serialization changed a candidate")
                points = self.output / ("audit_points_" + str(index) + ".txt")
                expected = write_bytes(points, raw)
                self.generated[str(points)] = {"path": str(points), "label": points.name, **expected}
                audit, audit_reference = self.child("audit" + str(index), "audit", index, points, vectors)
                self.audits.append({"next_index": index, "capture": audit_reference,
                                    "counts": audit["counts"], "arms": list(ARMS),
                                    "candidate_x": vectors, "points": audit["points"],
                                    "audit_only_never_fed_to_acceptance": True})
            require(self.counts["primary_completed"] == 1 and self.counts["audits_completed"] == 2 and
                    self.counts["model_step_count_complete"], "Required child sequence incomplete")
            self.stage = "saved_output_reduction"
            self.comparison = summarize_fidelity(primary, self.audits)
            self.write("comparison.json", self.comparison)
            self.recheck()
        except Exception as error:
            errors.append({"stage": self.stage, "type": type(error).__name__, "message": str(error)})
        for name, rows in (("sources", self.sources), ("inputs", self.inputs), ("generated", self.generated)):
            try:
                rehash(rows)
            except Exception as error:
                errors.append({"stage": "posthash_" + name, "type": type(error).__name__, "message": str(error)})
        for row in self.captures:
            try:
                self.capture.load_verified(row["directory"], row["identity"])
            except Exception as error:
                errors.append({"stage": "capture_integrity", "type": type(error).__name__, "message": str(error)})
        result = {"schema": SCHEMA, "kind": "result", "status": "failed" if errors else "completed",
                  "source_revision": self.args.source_revision,
                  "plan_sha256": None if self.plan_identity is None else self.plan_identity["sha256"],
                  "counts": self.counts, "primary": self.primary, "audits": self.audits,
                  "comparison_path": "comparison.json" if self.comparison is not None else None,
                  "errors": errors, "audit_feedback_to_primary": False,
                  "coverage_validated": False, "candidate_promoted": False}
        self.write("result.json", result)
        receipt = {"schema": SCHEMA, "kind": "receipt", "status": result["status"],
                   "canonical_inference_closed": True, "source_revision": self.args.source_revision,
                   "plan_sha256": result["plan_sha256"], "counts": self.counts,
                   "source_bindings": list(self.sources.values()), "input_bindings": list(self.inputs.values()),
                   "generated_bindings": list(self.generated.values()), "children": self.children,
                   "capture_bindings": self.captures, "resources_before_receipt": self.usage(),
                   "errors": list(errors), "truth_reads": 0,
                   "resource_scope": "Inner snapshot; whole canonical process/children/closure is measured by the outer wait4 receipt."}
        close_receipt(self.output, receipt, LIMITS["output_bytes"])
        print(encode_json({"schema": SCHEMA, "status": receipt["status"], "counts": self.counts,
                           "result": identity(self.output / "result.json"),
                           "receipt": identity(self.output / "receipt.json")}).decode(), end="")
        return 0 if receipt["status"] == "completed" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--executable-receipt", default=EXP + "/executable_receipt.json")
    return Run(parser.parse_args()).run()


if __name__ == "__main__":
    raise SystemExit(main())
