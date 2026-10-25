#!/usr/bin/env python3
"""One frozen-anchor compact-vs-original replay, without fits or truth access."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "experiments/compact_bounded_001/plan.json"
SOURCES = (
    "Makefile", "src/scm_model.c", "include/scm_model.h", "src/scm_evidence.c",
    "include/scm_evidence.h", "src/scm_remainder.c", "include/scm_remainder.h",
    "src/scm_assess.c", "include/scm_assess.h", "include/scm_estimator.h",
    "src/scm_compact_evidence.c", "include/scm_compact_evidence.h",
    "src/scm_compact_remainder.c", "include/scm_compact_remainder.h",
    "src/scm_compact_assess.c", "include/scm_compact_assess.h",
    "tests/test_compact.c", "tests/test_compact_assess.c", "tools/compact_compare.h",
    "tools/compact_probe.c", "tools/run_compact.py", "tools/measure_compact_memory.py",
    "experiments/compact_bounded_001/plan.json",
)


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def git(*arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=ROOT, text=True).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--binary", type=Path, default=ROOT / "build/scm_compact_probe")
    args = parser.parse_args()
    out, binary = args.output_dir.resolve(), args.binary.resolve()
    if out.exists():
        parser.error("Output already exists; preserve the first receipt and choose a new path")
    plan = json.loads(PLAN.read_text())
    primary = plan["primary"]
    if primary["runs"] != 1 or primary["new_nonlinear_fits"] != 0 or primary["truth_access"]:
        raise ValueError("Runner supports one no-fit, no-truth comparison only")
    # Numerical source, tests, runner and frozen gates must be reviewable in the
    # source commit before the one primary replay is attempted.
    git("ls-files", "--error-unmatch", *SOURCES)
    if git("status", "--porcelain", "--", *SOURCES):
        raise ValueError("Commit the implementation and acceptance plan before primary replay")
    checkpoints = primary["checkpoints_samples"]
    if len(checkpoints) != 2 or checkpoints[-1] != primary["end_samples"]:
        raise ValueError("Expected the declared split/final checkpoint pair")
    data, anchor = ROOT / primary["data"], ROOT / primary["anchor"]
    data_hash, anchor_hash, binary_hash = sha(data), sha(anchor), sha(binary)
    if anchor.read_text().split()[2] != data_hash:
        raise ValueError("Anchor identity does not match the selected observation file")
    sources_before = {name: sha(ROOT / name) for name in SOURCES}
    out.mkdir(parents=True)
    copied_anchor = out / "anchor.txt"
    copied_anchor.write_bytes(anchor.read_bytes())
    command_tail = [str(data), str(copied_anchor), str(primary["end_samples"]),
                    str(checkpoints[0]), str(primary["max_event_samples"])]
    receipt = {
        "schema": "mumble_compact_receipt_v1", "started_utc": datetime.now(timezone.utc).isoformat(),
        "source_revision": git("rev-parse", "HEAD"), "branch": git("branch", "--show-current"),
        "source_sha256": sources_before, "plan_sha256": sha(PLAN),
        "data": primary["data"], "data_sha256": data_hash,
        "anchor": primary["anchor"], "anchor_sha256": anchor_hash,
        "binary_sha256": binary_hash, "platform": platform.platform(), "python": platform.python_version(),
        "command": [str(binary), *command_tail], "new_nonlinear_fits": 0, "truth_access": False,
        "anchor_scope": primary["anchor_scope"], "acceptance": plan["acceptance"],
        "limits": plan["limits"], "operational_failures": [],
    }
    begin = time.perf_counter()
    stdout, stderr, returncode = "", "", None
    with tempfile.TemporaryDirectory(prefix="mumble_compact_primary_") as temporary:
        executable = Path(temporary) / "probe"
        executable.write_bytes(binary.read_bytes())
        executable.chmod(0o700)
        if sha(executable) != binary_hash:
            raise RuntimeError("Binary changed while taking the run snapshot")
        try:
            process = subprocess.run([str(executable), *command_tail], cwd=ROOT,
                                     capture_output=True, text=True, timeout=60)
            stdout, stderr, returncode = process.stdout, process.stderr, process.returncode
        except subprocess.TimeoutExpired as error:
            stdout = error.stdout.decode(errors="replace") if isinstance(error.stdout, bytes) else error.stdout or ""
            stderr = error.stderr.decode(errors="replace") if isinstance(error.stderr, bytes) else error.stderr or ""
            receipt["operational_failures"].append({"kind": "timeout", "seconds": 60})
        except OSError as error:
            receipt["operational_failures"].append({"kind": "launch", "error": str(error)})
    receipt["process_wall_s"] = time.perf_counter() - begin
    receipt["returncode"] = returncode
    (out / "stdout.txt").write_text(stdout)
    (out / "stderr.txt").write_text(stderr)
    passed = False
    try:
        result = json.loads(stdout)
        if result["source_id"] != data_hash or result["end_samples"] != primary["end_samples"]:
            raise ValueError("Output input identity/count differs")
        if [c["samples"] for c in result["checkpoints"]] != checkpoints:
            raise ValueError("Checkpoint sample counts differ")
        save(out / "comparison.json", result)
        receipt["comparison_sha256"] = sha(out / "comparison.json")
        receipt["summary"] = {
            "exact_comparison": result["exact_comparison"],
            "diagnostic_comparison": result["diagnostic_comparison"],
            "owned_objects_bytes": result["owned_objects_bytes"],
            "checkpoints": [{"samples": c["samples"], "rank": c["numerical_rank"],
                             "local_curvature_diagnostic": c["local_curvature_diagnostic"]}
                            for c in result["checkpoints"]],
        }
        passed = returncode == 0 and result["all_checks_passed"] is True
    except (ValueError, TypeError, KeyError) as error:
        receipt["operational_failures"].append({"kind": "invalid_result", "error": str(error)})
    receipt["integrity"] = {
        "source_unchanged": sources_before == {name: sha(ROOT / name) for name in SOURCES},
        "binary_unchanged": binary_hash == sha(binary), "data_unchanged": data_hash == sha(data),
        "anchor_unchanged": anchor_hash == sha(anchor) == sha(copied_anchor),
    }
    receipt["all_checks_passed"] = passed and all(receipt["integrity"].values()) and not receipt["operational_failures"]
    receipt["finished_utc"] = datetime.now(timezone.utc).isoformat()
    save(out / "receipt.json", receipt)
    print(json.dumps({"receipt": str(out / "receipt.json"), "all_checks_passed": receipt["all_checks_passed"],
                      "wall_s": receipt["process_wall_s"], "returncode": returncode}))
    return 0 if receipt["all_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
