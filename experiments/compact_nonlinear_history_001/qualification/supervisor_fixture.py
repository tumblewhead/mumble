"""Exactly one real fabricated child through the new capture/wait4 integration."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import sys
import time


ROOT = Path(__file__).resolve().parents[3]
AREA = ROOT / "experiments/compact_nonlinear_history_001/qualification"
PLAN = AREA / "supervisor_plan.json"
FREEZE = AREA / "supervisor_source_freeze.json"
OUTPUT = AREA / "supervisor_attempt001"
RECEIPT = AREA / "supervisor.json"
CHILD_CODE = """import json, sys
value = {"schema":"mumble_compact_capture_fixture_v1","status":"completed","payload":"x"*8192,"model_calls":0,"prior_evaluations":0}
sys.stdout.write(json.dumps(value,sort_keys=True,separators=(",",":"))+"\\n")
sys.stdout.flush()
sys.stderr.write("fabricated capture fixture\\n")
sys.stderr.flush()
"""


def identity(path):
    data = Path(path).read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    started = time.monotonic()
    plan, freeze = json.loads(PLAN.read_text()), json.loads(FREEZE.read_text())
    check(freeze["status"] == "frozen_before_single_integration_child", "Source freeze status differs")
    check(not OUTPUT.exists() and not RECEIPT.exists(), "Single integration control already reserved")
    for record in freeze["sources"].values():
        check(identity(record["path"]) == {"bytes": record["bytes"], "sha256": record["sha256"]},
              "Frozen integration source differs")
    check(plan["cases"] == plan["real_fabricated_children"] == 1, "Integration scope differs")
    specification = importlib.util.spec_from_file_location("compact_fixture_supervisor", ROOT / "tools/run_compact_nonlinear_history.py")
    run = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(run)
    capture = run.load_capture()
    cap = plan["qualification_limits"]
    resource.setrlimit(resource.RLIMIT_AS, (cap["AS_bytes"],) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (cap["CPU_total_s"], cap["CPU_total_s"] + 1))
    transaction = capture.CaptureTransaction.reserve(
        OUTPUT, max_bytes=plan["child_limits"]["capture_bytes"],
        context={"qualification_only": True, "real_fabricated_children_reserved": 1,
                 "plan": {"path": str(PLAN), **identity(PLAN)},
                 "source_freeze": {"path": str(FREEZE), **identity(FREEZE)}})
    command = [str(Path(sys.executable).resolve()), "-I", "-B", "-c", CHILD_CODE]
    run.write_json(OUTPUT / "launch.json", {"command": command, "bounds": plan["child_limits"],
                   "real_fabricated_children_before": 0, "real_fabricated_children_after_reservation": 1,
                   "sources": freeze["sources"]})
    process, failure, commit = None, None, None
    try:
        process = run.supervise_capture(command, transaction, plan["child_limits"])
        run.write_json(OUTPUT / "resources.json", process)
        run.valid_process(process)
        commit = process["capture_commit_identity"]
        check(commit is not None and (OUTPUT / "commit.json").is_file(), "Dependent read preceded commit")
        raw = capture.load_verified(OUTPUT, commit)
        payload = run.strict_json(raw)
        check(payload == {"schema": "mumble_compact_capture_fixture_v1", "status": "completed",
                          "payload": "x" * 8192, "model_calls": 0, "prior_evaluations": 0},
              "Fabricated committed JSON differs")
        check(process["stdout_stderr_bytes_observed"] == process["stdout_stderr_bytes_written"] ==
              {"stdout": len(raw), "stderr": len(b"fabricated capture fixture\n")}, "Capture byte counts differ")
        check((OUTPUT / "probe.stderr").read_bytes() == b"fabricated capture fixture\n", "Stderr capture differs")
        metadata = json.loads((OUTPUT / "commit.json").read_text())
        original = (OUTPUT / "raw_probe.json").stat()
        duplicate = (OUTPUT / metadata["object"]["path"]).stat()
        check((original.st_dev, original.st_ino) != (duplicate.st_dev, duplicate.st_ino), "Capture inode is shared")
        for record in freeze["sources"].values():
            check(identity(record["path"]) == {"bytes": record["bytes"], "sha256": record["sha256"]},
                  "Integration source changed")
    except BaseException as error:
        failure = {"type": type(error).__name__, "message": str(error)}
    own, children = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    resources = {"CPU_self_s": own.ru_utime + own.ru_stime,
                 "CPU_children_s": children.ru_utime + children.ru_stime,
                 "CPU_total_s": own.ru_utime + own.ru_stime + children.ru_utime + children.ru_stime,
                 "wall_s_before_receipt": time.monotonic() - started,
                 "supervisor_peak_RSS_bytes": run.own_peak_bytes()}
    if not (resources["CPU_total_s"] <= cap["CPU_total_s"] and resources["wall_s_before_receipt"] <= cap["wall_s"] and
            resources["supervisor_peak_RSS_bytes"] <= cap["RSS_bytes"]):
        failure = failure or {"type": "ResourceFailure", "message": "Integration qualification cap"}
    files = run.manifest(OUTPUT)
    receipt = {"schema": "mumble_compact_history_supervisor_qualification_v1",
               "status": "passed" if failure is None else "failed", "failure": failure,
               "sources": freeze["sources"], "source_freeze": {"path": str(FREEZE), **identity(FREEZE)},
               "command": command, "process": process, "capture_commit_identity": commit,
               "resources_before_receipt": resources, "files": files, "closed_output_bytes_including_receipt": 0,
               "counts": {"qualification_invocations": 1, "real_fabricated_children_reserved": 1,
                          "real_fabricated_children_completed": int(process is not None),
                          "child_activity_complete": process is not None, "stub_children": 0,
                          "canonical_invocations": 0, "scientific_binary_invocations": 0,
                          "model_calls": 0, "optimizer_calls": 0, "prior_evaluations": 0,
                          "observation_reads": 0, "truth_reads": 0, "old_capture_changes": 0},
               "limitations": "One real capture/wait4 integration control; scientific orchestration/schema policy reviewed statically. Parent resources sampled before final receipt; exact child wait4 includes full child lifetime. No power-loss/hostile-writer guarantee or historical-loss attribution."}
    for _ in range(12):
        size = sum(row["bytes"] for row in files.values()) + len(run.encode_json(receipt))
        if size == receipt["closed_output_bytes_including_receipt"]:
            break
        receipt["closed_output_bytes_including_receipt"] = size
    check(size <= cap["closed_output_bytes"], "Final integration output cap")
    run.write_json(RECEIPT, receipt)
    print(json.dumps({"status": receipt["status"], "receipt": str(RECEIPT), **identity(RECEIPT),
                      "counts": receipt["counts"], "resources_before_receipt": resources}))
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
