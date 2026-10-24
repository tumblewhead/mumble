#!/usr/bin/env python3
"""Compile unchanged production C with tiny, constructed stability witnesses.

An all-reproduced result confirms counterexamples; it is not qualification.
The output path must be new. No long campaign, truth data, or inference occurs.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
PLAN = "experiments/indefinite_stability_001/plan.json"
FROZEN = [
    "src/scm_model.c", "src/scm_evidence.c", "src/scm_remainder.c",
    "include/scm_model.h", "include/scm_evidence.h", "include/scm_remainder.h",
]
SOURCES = FROZEN + ["tools/stability_witness.c", "tools/run_stability_witnesses.py", PLAN]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_hashes() -> dict[str, str]:
    return {name: sha((ROOT / name).read_bytes()) for name in SOURCES}


def command(args: list[str], timeout: int = 30) -> dict:
    start = time.monotonic()
    try:
        p = subprocess.run(args, cwd=ROOT, text=True, capture_output=True,
                           check=False, timeout=timeout)
        return {"command": args, "returncode": p.returncode,
                "stdout": p.stdout, "stderr": p.stderr,
                "elapsed_seconds": time.monotonic() - start, "timeout": False}
    except subprocess.TimeoutExpired as exc:
        def decoded(value):
            return value.decode(errors="replace") if isinstance(value, bytes) else value or ""
        return {"command": args, "returncode": None,
                "stdout": decoded(exc.stdout), "stderr": decoded(exc.stderr),
                "elapsed_seconds": time.monotonic() - start, "timeout": True}


def git_text(*args: str) -> str:
    p = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=True)
    return p.stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    if output.exists():
        raise FileExistsError(f"Refusing existing result: {output}")
    plan = json.loads((ROOT / PLAN).read_text())
    before = source_hashes()
    compiler = shlex.split(os.environ.get("CC", "cc"))
    if not compiler or shutil.which(compiler[0]) is None:
        raise RuntimeError("C compiler not found")
    compiler[0] = str(Path(shutil.which(compiler[0])).resolve())
    flags = plan["machine_contract"]["compiler_flags"]
    base_hashes = {}
    for name in FROZEN:
        p = subprocess.run(["git", "show", f"{plan['base_revision']}:{name}"],
                           cwd=ROOT, capture_output=True, check=True)
        base_hashes[name] = sha(p.stdout)
    committed_sources = {}
    for name in SOURCES:
        p = subprocess.run(["git", "show", f"HEAD:{name}"],
                           cwd=ROOT, capture_output=True, check=False)
        committed_sources[name] = p.returncode == 0 and sha(p.stdout) == before[name]
    receipt = {
        "schema": "mumble_indefinite_stability_witness_receipt_v1",
        "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "interpretation": "Reproducing the mechanisms is counterexample evidence, not indefinite-stability qualification.",
        "source_revision": git_text("rev-parse", "HEAD"),
        "work_branch": git_text("branch", "--show-current"),
        "plan": PLAN,
        "plan_and_sources_match_commit_before_run": committed_sources,
        "source_sha256_before": before,
        "frozen_source_sha256_at_base": base_hashes,
        "platform": {"system": platform.system(), "machine": platform.machine(),
                     "release": platform.release(), "python": platform.python_version(),
                     "libc": list(platform.libc_ver())},
        "compiler_version": command(compiler + ["--version"]),
        "scope": {"endurance_run": False, "synthetic_truth_used": False,
                  "constructed_api_states_are_replayed_histories": False,
                  "deployed_subsystem_memory_claim": False},
    }
    with tempfile.TemporaryDirectory(prefix="mumble-stability-witness-") as temp:
        binary = Path(temp) / "stability_witness"
        compile_args = compiler + flags + ["-Iinclude", "tools/stability_witness.c",
            "src/scm_model.c", "src/scm_evidence.c", "src/scm_remainder.c", "-lm", "-o", str(binary)]
        receipt["compile"] = command(compile_args)
        if receipt["compile"]["returncode"] == 0:
            receipt["binary_sha256"] = sha(binary.read_bytes())
            execution = command([str(binary)])
            receipt["execution"] = execution
            try:
                def reject_nonfinite(value: str):
                    raise ValueError(f"Nonfinite JSON constant: {value}")
                receipt["witnesses"] = json.loads(execution["stdout"], parse_constant=reject_nonfinite)
            except (ValueError, json.JSONDecodeError) as exc:
                receipt["parse_error"] = str(exc)
    after = source_hashes()
    receipt["source_sha256_after"] = after
    receipt["sources_unchanged_during_run"] = before == after
    receipt["production_sources_match_frozen_base"] = all(before[n] == base_hashes[n] for n in FROZEN)
    witness_pass = receipt.get("witnesses", {}).get("all_expected_mechanisms_reproduced", False)
    success = (receipt["sources_unchanged_during_run"] and receipt["production_sources_match_frozen_base"]
               and all(committed_sources.values()) and receipt["compile"]["returncode"] == 0
               and receipt.get("execution", {}).get("returncode") == 0 and witness_pass)
    receipt["counterexample_experiment_completed_as_planned"] = success
    receipt["indefinite_stability_proved"] = False
    receipt["finished_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"receipt": str(output), "counterexamples_reproduced": witness_pass,
                      "completed_as_planned": success, "indefinite_stability_proved": False}))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
