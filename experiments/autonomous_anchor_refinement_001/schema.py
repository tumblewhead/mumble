"""Shared, standard-library identities and closure schema for one finite run."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import stat

EXP = "experiments/autonomous_anchor_refinement_001"
PLAN = "plans/autonomous_anchor_refinement_001.json"
VERSION = "mumble_autonomous_anchor_v1"
PREFIX = 252000
MAX_PROPOSALS = 16
MAX_MODEL_PASSES = 33
MAX_MODEL_STEPS = PREFIX * MAX_MODEL_PASSES
FRACTIONS = (1., .5, .25, .125, .0625, .03125, .015625, .0078125)
LIMITS = {
    "CPU_total_s_max": 60, "wall_total_s_max": 90,
    "child_RSS_bytes_max": 134217728, "supervisor_RSS_bytes_max": 134217728,
    "child_address_space_bytes_max": 1073741824,
    "child_stdout_stderr_bytes_max": 524288,
    "closed_output_bytes_max": 8388608,
}
THREAD_ENV = {name: "1" for name in (
    "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
)}
CAPTURE_ROLES = {"stdout": "raw_probe.json", "stderr": "probe.stderr"}
ATTEMPT_ROLES = {"result": "result.json", "receipt": "receipt.json"}
OUTER_ROLES = {**CAPTURE_ROLES, "reservation": "reservation.json", "receipt": "receipt.json"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "Duplicate JSON key: " + key)
        result[key] = value
    return result


def _constant(value):
    raise ValueError("Nonfinite JSON constant: " + value)


def _float(value):
    result = float(value)
    require(math.isfinite(result), "Nonfinite JSON exponent")
    return result


def strict_json(data):
    return json.loads(data, object_pairs_hook=_pairs, parse_constant=_constant, parse_float=_float)


def read_json(path):
    return strict_json(Path(path).read_bytes())


def identity(path):
    path = Path(path)
    checksum = hashlib.sha256()
    size = 0
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "Not a regular file: " + str(path))
        while chunk := stream.read(1024 * 1024):
            checksum.update(chunk)
            size += len(chunk)
    return {"bytes": size, "sha256": checksum.hexdigest()}


def safe(root, relative):
    root, relative = Path(root).resolve(), Path(relative)
    require(not relative.is_absolute() and ".." not in relative.parts, "Unsafe relative path")
    path = root / relative
    require(not path.is_symlink(), "Symlink path is not admitted")
    path = path.resolve()
    require(path.is_relative_to(root), "Path escapes its declared root")
    return path


def fsync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def reserve_directory(path):
    path = Path(path)
    path.mkdir(exist_ok=False)
    fsync_directory(path.parent)


def encode_json(value):
    return (json.dumps(value, indent=2, allow_nan=False) + "\n").encode()


def write_json(path, value, max_bytes=1048576):
    path = Path(path)
    data = encode_json(value)
    require(len(data) <= max_bytes, "JSON exceeds its byte cap: " + str(path))
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    fsync_directory(path.parent)
    return identity(path)


def manifest(directory):
    directory = Path(directory)
    result = {}
    for path in sorted(directory.rglob("*")):
        require(not path.is_symlink(), "Symlink in output directory")
        if path.is_file():
            result[str(path.relative_to(directory))] = identity(path)
    return result


def bind(path, expected, bindings, label):
    path = Path(path).resolve()
    actual = identity(path)
    require(actual == {key: expected[key] for key in ("bytes", "sha256")}, "Identity changed: " + label)
    record = {"path": str(path), "label": label, **actual}
    previous = bindings.get(str(path))
    require(previous is None or previous == record, "Conflicting identity binding: " + label)
    bindings[str(path)] = record
    return record


def rehash_bindings(bindings):
    rows = bindings.values() if isinstance(bindings, dict) else bindings
    for row in rows:
        require(identity(row["path"]) == {key: row[key] for key in ("bytes", "sha256")},
                "Bound file changed: " + row["path"])


def close_receipt(directory, receipt):
    """Preserve failed closure even when a success cap has already been breached."""
    directory = Path(directory)
    files = manifest(directory)
    require("receipt.json" not in files, "Receipt already exists")
    receipt["files"] = files
    receipt["closed_output_bytes_including_receipt"] = 0
    for _ in range(16):
        total = sum(row["bytes"] for row in files.values()) + len(encode_json(receipt))
        if total == receipt["closed_output_bytes_including_receipt"]:
            break
        receipt["closed_output_bytes_including_receipt"] = total
    else:
        raise ValueError("Receipt size accounting did not stabilize")
    return write_json(directory / "receipt.json", receipt, 2097152)


def validate_manifest(directory, receipt):
    actual = manifest(directory)
    require("receipt.json" in actual, "Missing closed receipt")
    received = actual.pop("receipt.json")
    require(actual == receipt["files"], "Closed file manifest differs")
    require(sum(row["bytes"] for row in actual.values()) + received["bytes"] ==
            receipt["closed_output_bytes_including_receipt"], "Closed byte total differs")
    return received


def validate_activity(attempt, receipt, result):
    """Reconstruct activity from retained children, not completeness flags alone."""
    attempt = Path(attempt)
    counts = receipt["counts"]
    require(counts == result["counts"], "Result and receipt counts differ")
    totals = {"model": 0, "steps": 0, "propose": 0, "prior": 0, "assess": 0,
              "prior_reserved": 0, "prior_completed": 0, "solver_started": 0,
              "solver_completed": 0, "combined": 0}
    seen = set()
    for sequence, child in enumerate(receipt["children"], 1):
        require(child["sequence"] == sequence and child["directory"] not in seen,
                "Missing or duplicate child reservation sequence")
        seen.add(child["directory"])
        directory = safe(attempt, child["directory"])
        reservation = read_json(safe(attempt, child["reservation"]))
        action = child["action"]
        require(action in ("model", "prior", "propose", "assess") and
                reservation["action"] == action and reservation["sequence"] == sequence and
                reservation["roles"] == CAPTURE_ROLES and reservation["retry"] is False,
                "Child reservation identity mismatch")
        process = read_json(directory / "resources.json")
        require(process == child["resources"] and process["child_launched"] is True and
                process["exit_code"] == 0 and process["resource_violations"] == [] and
                process["output_truncated"] is False and child["activity_complete"] is True,
                "Incomplete child/process accounting")
        counter = {"model": "model_passes_reserved", "propose": "proposal_calls_reserved",
                   "prior": "prior_actions_reserved", "assess": "assess_actions_reserved"}[action]
        require(reservation["counts_after_reservation"][counter] == reservation["counts_before"][counter] + 1,
                "Missing durable before/after call reservation")
        for filename, expected in reservation["request_files"].items():
            require(identity(safe(directory, filename)) == expected, "Reserved child input changed")
        totals[action] += 1
        if action == "model":
            payload = read_json(directory / CAPTURE_ROLES["stdout"])
            require(payload["schema"] == "mumble_retained_likelihood_stream_evaluator_v1" and
                    payload["status"] == "ok" and payload["prefix_requested"] == PREFIX and
                    all(payload[key] == PREFIX for key in (
                        "records_read", "records_accumulated", "model_step_calls", "model_predict_calls")) and
                    payload["input_bytes_read"] == 32 * PREFIX and payload["model_init_calls"] == 1,
                    "Completed model pass has incomplete counters")
            require(child["model_steps_reported"] == PREFIX, "Parent/model counter mismatch")
            totals["steps"] += payload["model_step_calls"]
            continue
        path = directory / "output/result.json"
        worker = read_json(path)
        require(worker["schema"] == "mumble_autonomous_anchor_worker_result_v1" and
                worker["status"] == "completed" and worker["action"] == action,
                "Missing completed worker result")
        activity = worker["counts"]
        require(activity == child["worker_counts"] and activity["optimizer_evaluation_count_complete"] is True,
                "Worker activity remains unknown")
        prior_expected = 0 if action == "propose" else 1
        require(activity["prior_evaluations"] == activity["prior_evaluations_completed"] == prior_expected,
                "Unexpected external prior evaluation")
        starts = activity["optimizer_calls_started"]
        require(type(starts) is int and starts in (0, 1) and starts == activity["optimizer_calls_completed"],
                "Incomplete optimizer call")
        require(action == "propose" or starts == 0, "Optimizer call in a nonproposal action")
        require((directory / "output/solve_started.json").is_file() == bool(starts),
                "Missing optimizer start marker")
        evaluations = activity["combined_evaluations"]
        require(type(evaluations) is int and 0 <= evaluations <= (256 if action == "propose" else 0),
                "Per-proposal combined evaluation cap")
        totals["prior_reserved"] += activity["prior_evaluations"]
        totals["prior_completed"] += activity["prior_evaluations_completed"]
        totals["solver_started"] += starts
        totals["solver_completed"] += activity["optimizer_calls_completed"]
        totals["combined"] += evaluations
    require(1 <= totals["model"] <= MAX_MODEL_PASSES and totals["steps"] <= MAX_MODEL_STEPS and
            totals["prior"] == 1 and totals["assess"] == totals["model"] - 1 and
            totals["prior_reserved"] == totals["prior_completed"] == totals["model"] and
            0 <= totals["propose"] <= MAX_PROPOSALS and totals["combined"] <= 4096,
            "Canonical point/prior/proposal accounting or cap failed")
    exact = {
        "model_passes_reserved": totals["model"], "model_passes_launched": totals["model"],
        "model_passes_completed": totals["model"], "model_steps_reported": totals["steps"],
        "proposal_calls_reserved": totals["propose"], "proposal_actions_completed": totals["propose"],
        "prior_actions_reserved": totals["prior"], "assess_actions_reserved": totals["assess"],
        "external_prior_evaluations_reserved": totals["prior"] + totals["assess"],
        "external_prior_evaluations_started_reported": totals["prior_reserved"],
        "external_prior_evaluations_completed": totals["prior_completed"],
        "optimizer_calls_started": totals["solver_started"], "optimizer_calls_completed": totals["solver_completed"],
        "proposal_combined_evaluations_reported": totals["combined"],
    }
    require(all(counts[key] == value for key, value in exact.items()), "Reported counts differ from retained child evidence")
    require(counts["model_step_count_complete"] is True and counts["worker_activity_complete"] is True and
            receipt["unresolved_model_reservations"] == [] and receipt["unresolved_worker_reservations"] == [],
            "Closure has unresolved reservations")
    require(counts["supervisor_invocations"] == 1 and all(counts[key] == 0 for key in (
        "truth_reads", "historical_candidate_reads", "learner_calls", "source_generations",
        "original_fitter_calls", "retries")), "Forbidden canonical activity")
    require(result["initial"] is not None and result["final"] is not None and
            result["initial"]["generation"] == 0 and
            result["final"]["generation"] == counts["accepted_steps"] == len(result["generation_records"]) - 1,
            "Accepted-generation accounting differs")
    initial = read_json(attempt / "public_initialization.json")
    require(result["initial"]["x"] == initial["x"], "Run did not start at its fixed public initialization")
    return totals


def validate_closed_run(root, attempt=None, outer=None):
    """Read-only reporting gate; contains no numerical, prior or truth access."""
    root = Path(root).resolve()
    attempt = Path(attempt) if attempt is not None else safe(root, EXP + "/attempt001")
    outer = Path(outer) if outer is not None else safe(root, EXP + "/execution_process")
    receipt = read_json(attempt / "receipt.json")
    result = read_json(attempt / "result.json")
    observer = read_json(outer / "receipt.json")
    for payload, kind in ((receipt, "run_receipt"), (result, "result"), (observer, "outer_receipt")):
        require(payload["schema"] == VERSION and payload["kind"] == kind and
                payload["status"] == "completed", "No successful versioned closure: " + kind)
    require(receipt["canonical_inference_closed"] is True and observer["canonical_process_finished"] is True,
            "Inference is not closed")
    require(result["source_revision"] == receipt["source_revision"] == observer["source_revision"] and
            result["plan_sha256"] == receipt["plan_sha256"] == observer["plan_sha256"],
            "Closure source/plan mismatch")
    inner_id = validate_manifest(attempt, receipt)
    validate_manifest(outer, observer)
    require(inner_id == observer["inner_receipt"] and identity(attempt / "result.json") == observer["inner_result"],
            "Outer closure binds different inner outputs")
    require(observer["roles"] == OUTER_ROLES and receipt["roles"] == ATTEMPT_ROLES,
            "Shared closure role schema differs")
    validate_activity(attempt, receipt, result)
    process = observer["process"]
    require(observer["canonical_supervisor_invocations"] == 1 and observer["retries"] == 0 and
            process["child_launched"] is True and process["exit_code"] == 0 and
            process["resource_violations"] == [] and process["output_truncated"] is False,
            "Whole-process closure failed")
    require(process["CPU_total_s"] <= LIMITS["CPU_total_s_max"] and
            process["wall_s_through_wait4"] <= LIMITS["wall_total_s_max"] and
            process["peak_RSS_bytes"] <= LIMITS["child_RSS_bytes_max"] and
            observer["outer_own_peak_RSS_bytes"] <= LIMITS["supervisor_RSS_bytes_max"],
            "Whole-process resource cap failed")
    closed_bytes = receipt["closed_output_bytes_including_receipt"] + observer["closed_output_bytes_including_receipt"]
    require(observer["all_closed_output_bytes"] == closed_bytes and
            closed_bytes <= LIMITS["closed_output_bytes_max"], "Whole-run closed output cap failed")
    rehash_bindings(receipt["source_bindings"])
    rehash_bindings(receipt["input_bindings"])
    rehash_bindings(receipt["generated_bindings"])
    rehash_bindings(observer["source_bindings"])
    return {"result": result, "receipt": receipt, "outer_receipt": observer}
