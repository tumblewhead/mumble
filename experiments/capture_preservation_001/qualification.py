"""One bounded, real-child qualification of the future capture transaction.

All payloads are fabricated bytes. Injected faults touch only this new attempt.
No model, optimizer, prior, observation, truth or historical-result code is used.
"""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import selectors
import signal
import sys
import time


ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT = ROOT / "experiments/capture_preservation_001"
PLAN = EXPERIMENT / "plan.json"
PLAN_SHA256 = "2b4cbb1bdad7f37a4440586a53266f2706208e1e648de10b6e3423aee7a54e0d"
MODULE = ROOT / "tools/capture_preservation.py"
FREEZE = EXPERIMENT / "source_freeze.json"
CHILD_CODE = """import os, sys
n = int(sys.argv[1])
data = bytes((i * 37 + 11) % 256 for i in range(n))
while data:
    data = data[os.write(1, data):]
"""


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def digest(path):
    data = Path(path).read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def fsync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_json(path, value):
    data = json_bytes(value)
    with Path(path).open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    fsync_directory(Path(path).parent)


def manifest(directory):
    result = {}
    for path in sorted(directory.rglob("*")):
        require(not path.is_symlink(), "Qualification output symlink")
        if path.is_file():
            result[path.relative_to(directory).as_posix()] = digest(path)
    return result


def fabricated_bytes(count):
    return bytes((i * 37 + 11) % 256 for i in range(count))


def reject(function, classes):
    try:
        function()
    except classes as error:
        return {"type": type(error).__name__, "message": str(error)}
    raise AssertionError("Expected rejection did not occur")


def capture_child(tx, count, capture, limits):
    """Exact wait4 accounting; the tested writer receives real pipe bytes."""
    writer = tx.open_original()
    read_fd, write_fd = os.pipe()
    stderr_path = tx.directory / "child.stderr"
    error_fd = os.open(stderr_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    command = [sys.executable, "-I", "-B", "-c", CHILD_CODE, str(count)]
    write_json(tx.directory / "child_reservation.json",
               {"command": command, "reservation_before_launch": digest(tx.directory / capture.RESERVATION),
                "fabricated_payload_bytes": count, "child_sequence_scope": "one child in this case",
                "child_CPU_s_max": limits["child_CPU_s_max"],
                "child_wall_s_max": limits["child_wall_s_max"],
                "child_address_space_bytes_max": limits["child_address_space_bytes_max"]})
    start = time.monotonic()
    pid = os.fork()
    if pid == 0:
        try:
            os.setsid()
            resource.setrlimit(resource.RLIMIT_CPU, (limits["child_CPU_s_max"], limits["child_CPU_s_max"]))
            resource.setrlimit(resource.RLIMIT_AS, (limits["child_address_space_bytes_max"],) * 2)
            resource.setrlimit(resource.RLIMIT_FSIZE, (8192, 8192))
            os.dup2(write_fd, 1)
            os.dup2(error_fd, 2)
            os.close(read_fd)
            os.close(write_fd)
            os.close(error_fd)
            os.execv(sys.executable, command)
        except BaseException:
            os._exit(127)
    os.close(write_fd)
    os.set_blocking(read_fd, False)
    selector = selectors.DefaultSelector()
    selector.register(read_fd, selectors.EVENT_READ)
    observed, status, usage, output_error, killed = 0, None, None, None, False

    def kill():
        nonlocal killed
        if not killed:
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            killed = True

    try:
        while selector.get_map() or status is None:
            if time.monotonic() - start > limits["child_wall_s_max"]:
                kill()
                raise RuntimeError("Fabricated child wall cap exceeded")
            for key, _ in selector.select(0.01):
                try:
                    chunk = os.read(key.fd, 4096)
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(key.fd)
                    os.close(key.fd)
                    continue
                observed += len(chunk)
                if output_error is None:
                    try:
                        writer.write(chunk)
                    except capture.CaptureLimitError as error:
                        output_error = {"type": type(error).__name__, "message": str(error)}
                        kill()
            if status is None:
                waited, candidate_status, candidate_usage = os.wait4(pid, os.WNOHANG)
                if waited:
                    status, usage = candidate_status, candidate_usage
    finally:
        if status is None:
            kill()
            _, status, usage = os.wait4(pid, 0)
        for key in list(selector.get_map().values()):
            selector.unregister(key.fd)
            os.close(key.fd)
        selector.close()
        writer.close()
        os.fsync(error_fd)
        os.close(error_fd)
        fsync_directory(tx.directory)
    result = {"command": command, "child_launched": True,
              "exit_code": os.waitstatus_to_exitcode(status), "wall_s": time.monotonic() - start,
              "CPU_user_s": usage.ru_utime, "CPU_system_s": usage.ru_stime,
              "CPU_total_s": usage.ru_utime + usage.ru_stime,
              "peak_RSS_bytes": usage.ru_maxrss * 1024,
              "stdout_bytes_observed": observed, "stdout_bytes_written": writer.bytes,
              "stream_identity": writer.identity, "output_error": output_error,
              "killed_after_output_cap": killed, "stderr": digest(stderr_path),
              "resources_scope": "exact wait4 of this real fabricated child; no stub resources"}
    write_json(tx.directory / "child_resources.json", result)
    require(result["CPU_total_s"] <= limits["child_CPU_s_max"], "Child CPU cap")
    require(result["wall_s"] <= limits["child_wall_s_max"], "Child wall cap")
    require(result["peak_RSS_bytes"] <= limits["process_peak_RSS_bytes_max"], "Child RSS cap")
    require(result["stderr"]["bytes"] == 0, "Unexpected child stderr")
    return writer, result


def run_case(case, output, capture, limits, context):
    name = case["name"]
    tx = capture.CaptureTransaction.reserve(output / name, max_bytes=case["capture_cap"], context=context)
    events, faults = [], []
    if name == "duplicate_writers":
        events.append(reject(lambda: capture.CaptureTransaction.reserve(
            tx.directory, max_bytes=case["capture_cap"], context=context), (FileExistsError,)))
    writer, resources = capture_child(tx, case["payload_bytes"], capture, limits)
    expected = fabricated_bytes(case["payload_bytes"])
    retained = expected[:case["capture_cap"]]
    require(writer.identity == {"bytes": len(retained), "sha256": hashlib.sha256(retained).hexdigest()},
            "Streaming identity differs from fabricated stdout")
    require(resources["stdout_bytes_observed"] == len(expected), "Unexpected real child byte count")
    if name != "output_cap_exceeded":
        require(resources["exit_code"] == 0 and resources["output_error"] is None, "Fabricated child failed")
    else:
        require(resources["output_error"] is not None and writer.failure == "output_cap_exceeded",
                "Output cap was not detected")
    dummy_identity = {"bytes": 0, "sha256": hashlib.sha256(b"").hexdigest()}
    events.append(reject(lambda: capture.load_verified(tx.directory, dummy_identity),
                         (capture.CaptureIntegrityError,)))
    require(not (tx.directory / capture.COMMIT).exists(), "Premature commit record")
    if name == "original_truncated_before_commit":
        with (tx.directory / capture.ORIGINAL).open("wb") as handle:
            handle.flush()
            os.fsync(handle.fileno())
        faults.append("Explicit fixture truncation of original before commit")
        events.append(reject(tx.commit, (capture.CaptureIntegrityError,)))
        require(not (tx.directory / capture.COMMIT).exists(), "Failed commit was published")
        commit_identity = None
    elif name == "output_cap_exceeded":
        events.append(reject(tx.commit, (capture.CaptureStateError,)))
        require(not (tx.directory / capture.COMMIT).exists(), "Over-cap capture was committed")
        require(digest(tx.directory / capture.ORIGINAL) == writer.identity, "Partial bounded bytes not retained")
        commit_identity = None
    else:
        commit_identity = tx.commit()
        require(capture.load_verified(tx.directory, commit_identity) == expected, "Committed payload differs")
        record = json.loads((tx.directory / capture.COMMIT).read_text())
        original, duplicate = tx.directory / capture.ORIGINAL, tx.directory / record["object"]["path"]
        require(original.stat().st_ino != duplicate.stat().st_ino, "Copy is not an independent inode")
        if name == "duplicate_writers":
            unchanged = manifest(tx.directory)
            events.append(reject(tx.open_original, (capture.CaptureStateError,)))
            events.append(reject(tx.commit, (capture.CaptureStateError,)))
            require(manifest(tx.directory) == unchanged, "Duplicate API request changed committed evidence")
        elif name == "original_truncated_after_commit":
            with original.open("wb") as handle:
                handle.flush()
                os.fsync(handle.fileno())
            faults.append("Explicit fixture truncation of original after commit")
            events.append(reject(lambda: capture.load_verified(tx.directory, commit_identity),
                                 (capture.CaptureIntegrityError,)))
            require(duplicate.read_bytes() == expected, "Independent copy did not survive")
        elif name == "original_deleted_after_commit":
            original.unlink()
            fsync_directory(tx.directory)
            faults.append("Explicit fixture deletion of original after commit")
            events.append(reject(lambda: capture.load_verified(tx.directory, commit_identity),
                                 (capture.CaptureIntegrityError,)))
            require(duplicate.read_bytes() == expected, "Independent copy did not survive")
        elif name == "object_corrupted_after_commit":
            with duplicate.open("r+b") as handle:
                handle.write(bytes([expected[0] ^ 1]))
                handle.flush()
                os.fsync(handle.fileno())
            faults.append("Explicit fixture one-byte corruption of committed object")
            events.append(reject(lambda: capture.load_verified(tx.directory, commit_identity),
                                 (capture.CaptureIntegrityError,)))
            require(original.read_bytes() == expected, "Original did not survive")
    result = {"case": name, "status": "passed", "real_fabricated_children": 1,
              "resources": resources, "commit_identity": commit_identity,
              "expected_rejections": events, "injected_faults": faults,
              "scientific_status_changes": 0, "canonical_recovery_or_retry": False}
    write_json(tx.directory / "case.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(EXPERIMENT / "attempt001"))
    args = parser.parse_args()
    started = time.monotonic()
    output = Path(args.output_dir).absolute()
    require(output == EXPERIMENT / "attempt001", "One fixed qualification attempt only")
    plan = json.loads(PLAN.read_text())
    require(digest(PLAN)["sha256"] == PLAN_SHA256, "Frozen plan differs")
    frozen = json.loads(FREEZE.read_text())
    sources = {"plan": {"path": str(PLAN), **digest(PLAN)},
               "module": {"path": str(MODULE), **digest(MODULE)},
               "qualification": {"path": str(Path(__file__).resolve()), **digest(__file__)},
               "python": {"path": str(Path(sys.executable).resolve()), **digest(Path(sys.executable).resolve())}}
    require(frozen["schema"] == "mumble_capture_preservation_source_freeze_v1" and
            frozen["sources"] == sources, "Sources differ from pre-qualification freeze")
    limits = plan["limits"]
    cases = plan["fixed_cases"]
    require(len(cases) == limits["cases"] == limits["fabricated_children_max"] == 8,
            "Qualification extent differs")
    output.mkdir(mode=0o700, exist_ok=False)
    fsync_directory(output.parent)
    write_json(output / "reservation.json",
               {"schema": "mumble_capture_preservation_qualification_reservation_v1",
                "qualification_invocations": 1, "command": [sys.executable, *sys.argv],
                "sources": sources, "source_freeze": {"path": str(FREEZE), **digest(FREEZE)},
                "limits": limits, "case_names": [row["name"] for row in cases]})
    resource.setrlimit(resource.RLIMIT_AS, (limits["parent_address_space_bytes_max"],) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (limits["CPU_total_s_max"], limits["CPU_total_s_max"] + 1))

    def deadline(_signal, _frame):
        raise RuntimeError("Qualification process deadline exceeded")

    signal.signal(signal.SIGALRM, deadline)
    signal.signal(signal.SIGXCPU, deadline)
    signal.setitimer(signal.ITIMER_REAL, limits["wall_s_max"])
    results, failure = [], None
    try:
        specification = importlib.util.spec_from_file_location("qualified_capture_preservation", MODULE)
        capture = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(capture)
        context = {"qualification_only": True, "scientific_status": "not_a_scientific_invocation",
                   "source_sha256": sources["module"]["sha256"], "plan_sha256": PLAN_SHA256}
        for case in cases:
            results.append(run_case(case, output, capture, limits, context))
            own = resource.getrusage(resource.RUSAGE_SELF)
            children = resource.getrusage(resource.RUSAGE_CHILDREN)
            require(own.ru_utime + own.ru_stime + children.ru_utime + children.ru_stime <= limits["CPU_total_s_max"],
                    "Qualification cumulative CPU cap")
            require(time.monotonic() - started <= limits["wall_s_max"], "Qualification cumulative wall cap")
            require(own.ru_maxrss * 1024 <= limits["process_peak_RSS_bytes_max"], "Qualification RSS cap")
            require(sum(v["bytes"] for v in manifest(output).values()) < limits["closed_runtime_output_bytes_max"] - 32768,
                    "Qualification output closure reserve exhausted")
        for row in sources.values():
            require(digest(row["path"]) == {"bytes": row["bytes"], "sha256": row["sha256"]},
                    "Qualification source changed")
    except BaseException as error:
        failure = {"type": type(error).__name__, "message": str(error)}
    signal.setitimer(signal.ITIMER_REAL, 0)
    own = resource.getrusage(resource.RUSAGE_SELF)
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    files = manifest(output)
    launched = sum(1 for path in output.glob("*/child_resources.json"))
    child_reservations = sum(1 for path in output.glob("*/child_reservation.json"))
    receipt = {"schema": "mumble_capture_preservation_qualification_v1",
               "status": "passed" if failure is None and len(results) == 8 else "failed",
               "failure": failure, "sources": sources, "source_freeze": {"path": str(FREEZE), **digest(FREEZE)},
               "cases": results, "cases_completed": len(results), "cases_planned": 8,
               "counts": {"qualification_invocations": 1, "real_fabricated_child_reservations": child_reservations,
                          "real_fabricated_children_completed": launched,
                          "child_activity_complete": child_reservations == launched,
                          "stub_children": 0, "model_calls": 0, "optimizer_calls": 0,
                          "prior_evaluations": 0, "observation_reads": 0, "truth_reads": 0,
                          "historical_capture_changes": 0, "scientific_status_changes": 0},
               "resources": {"CPU_self_s": own.ru_utime + own.ru_stime,
                             "CPU_children_s": children.ru_utime + children.ru_stime,
                             "CPU_total_s": own.ru_utime + own.ru_stime + children.ru_utime + children.ru_stime,
                             "wall_s_before_receipt": time.monotonic() - started,
                             "supervisor_peak_RSS_bytes": own.ru_maxrss * 1024,
                             "maximum_child_wait4_peak_RSS_bytes": max(
                                 [row["resources"]["peak_RSS_bytes"] for row in results] or [0]),
                             "scope": "Parent rusage plus waited children through qualification closure, before final receipt serialization; each child has exact wait4 resources. Main wall excludes interpreter startup."},
               "limits": limits, "files": files, "closed_runtime_output_bytes": 0,
               "limitations": ["Finite fabricated qualification, not a reproduction of the original capture loss.",
                               "No power-loss, kernel/filesystem fault injection, cross-device replication or hostile-writer guarantee.",
                               "Independent inode copy and fsync are implemented; physical storage may still be shared.",
                               "Original loss remains an error even if the copy survives; no historical scientific status is changed.",
                               "Future inference must pin the commit identity and separately enforce its scientific/resource contract."]}
    for _ in range(10):
        closed_bytes = sum(row["bytes"] for row in files.values()) + len(json_bytes(receipt))
        if closed_bytes == receipt["closed_runtime_output_bytes"]:
            break
        receipt["closed_runtime_output_bytes"] = closed_bytes
    require(receipt["closed_runtime_output_bytes"] <= limits["closed_runtime_output_bytes_max"],
            "Final qualification output cap")
    write_json(output / "receipt.json", receipt)
    print(json.dumps({"status": receipt["status"], "cases_completed": len(results),
                      "real_fabricated_children_completed": launched,
                      "receipt": str(output / "receipt.json"), **digest(output / "receipt.json")}))
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
