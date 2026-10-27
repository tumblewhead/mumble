#!/usr/bin/env python3
"""One finite fabricated qualification, reusing the repository capture protocol."""
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
from capture_preservation import CaptureTransaction, load_verified  # noqa: E402


def identity(path):
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def save(path, value):
    with path.open("x") as out:
        json.dump(value, out, sort_keys=True, separators=(",", ":"))
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def child(command, destination):
    start = time.monotonic()
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    timed_out = False
    try:
        p = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=30)
        code, stdout, stderr = p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired as error:
        timed_out = True
        code, stdout, stderr = None, error.stdout or b"", error.stderr or b""
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    result = {"command": command, "returncode": code, "timed_out": timed_out,
              "wall_seconds": time.monotonic()-start,
              "CPU_seconds": (after.ru_utime+after.ru_stime)-(before.ru_utime+before.ru_stime),
              "host_cumulative_children_peak_RSS_bytes": after.ru_maxrss*1024,
              "stdout_bytes": len(stdout), "stderr_bytes": len(stderr),
              "output_cap_stage": "post_child_collection", "live_output_bound": False,
              "within_post_capture_cap": len(stdout)+len(stderr) <= 1048576,
              "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
              "stderr_sha256": hashlib.sha256(stderr).hexdigest()}
    destination.with_suffix(".stdout").write_bytes(stdout)
    destination.with_suffix(".stderr").write_bytes(stderr)
    save(destination.with_suffix(".json"), result)
    return result, stdout


def main():
    attempt = HERE / "translation_attempt001"
    attempt.mkdir(exist_ok=False)
    paths = [Path(__file__), HERE / "translation_test.c", HERE / "translation_plan.json",
             HERE.parent / "history_translation.c", HERE.parent / "history_translation.h",
             HERE.parent / "live_layout.h", HERE.parent / "support_step.h", HERE.parent / "adc12.h",
             ROOT / "experiments/compact_nonlinear_history_001/compact_history.h",
             ROOT / "include/scm_model.h", ROOT / "tools/capture_preservation.py"]
    frozen = {str(p.relative_to(ROOT)): identity(p) for p in paths}
    compiler = Path(shutil.which("cc")).resolve()
    python = Path(sys.executable).resolve()
    compiler_identity, python_identity = identity(compiler), identity(python)
    save(attempt / "source_freeze.json", {"schema": "translation_source_freeze_v1", "sources": frozen,
         "compiler_driver": {"path": str(compiler), **compiler_identity},
         "python": {"path": str(python), **python_identity},
         "git_base": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()})
    binary = attempt / "translation_test"
    command = [str(compiler), "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
               "-fno-fast-math", "-fstack-usage", "-Iinclude",
               str((HERE.parent / "history_translation.c").relative_to(ROOT)),
               str((HERE / "translation_test.c").relative_to(ROOT)), "-lm", "-o", str(binary)]
    receipt = {"schema": "translation_qualification_receipt_v1", "source_freeze": identity(attempt / "source_freeze.json"),
               "build_invocations": 0, "test_invocations": 0, "retries": 0,
               "canonical_stream_invocations": 0, "model_calls": 0, "observation_reads": 0,
               "prior_calls": 0, "truth_reads": 0,
               "status": "reserved", "target_measured": False, "integrated_estimator": False}
    try:
        save(attempt / "build_launch.json", {"command": command, "build_invocation": 1})
        receipt["build_invocations"] = 1
        build, _ = child(command, attempt / "build")
        receipt["build"] = build
        receipt["status"] = "build_failed"
        if build["returncode"] == 0 and build["within_post_capture_cap"]:
            tx = CaptureTransaction.reserve(attempt / "capture", max_bytes=1048576,
                 context={"task": "fabricated polynomial translation and static layout", "source_freeze": receipt["source_freeze"]})
            writer = tx.open_original()
            receipt["binary"] = identity(binary)
            save(attempt / "test_launch.json", {"binary": receipt["binary"], "test_invocation": 1})
            receipt["test_invocations"] = 1
            try:
                run, payload = child([str(binary)], attempt / "run")
                receipt["run"] = run
                writer.write(payload)
            finally:
                writer.close()
            commit = tx.commit()
            save(attempt / "capture_commit.json", commit)
            receipt["capture_commit"] = commit
            receipt["status"] = "test_failed"
            if run["returncode"] == 0 and run["within_post_capture_cap"]:
                result = json.loads(load_verified(attempt / "capture", commit))
                valid = result["passed"] and result["cases"] == 8 and result["evaluation_points"] == 255 and result["assertions"] <= 100000
                receipt["result"] = result
                receipt["status"] = "passed" if valid else "result_contract_failed"
    except Exception as error:
        receipt["status"] = "closure_failed"
        receipt["failure"] = {"type": type(error).__name__, "detail": str(error)}
    finally:
        try:
            receipt["sources_unchanged"] = all(identity(p) == frozen[str(p.relative_to(ROOT))] for p in paths)
            receipt["toolchain_driver_unchanged"] = identity(compiler) == compiler_identity and identity(python) == python_identity
        except Exception as error:
            receipt["sources_unchanged"] = False
            receipt["source_check_failure"] = {"type": type(error).__name__, "detail": str(error)}
        receipt["stack_files"] = {p.name: identity(p) for p in sorted(attempt.glob("*.su"))}
        if not receipt["sources_unchanged"] or not receipt.get("toolchain_driver_unchanged", False):
            receipt["status"] = "source_changed"
        save(attempt / "receipt.json", receipt)
    print(json.dumps({"status": receipt["status"], "receipt": str((attempt / "receipt.json").relative_to(ROOT)),
                      "test_invocations": receipt["test_invocations"], "result": receipt.get("result")}))
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
