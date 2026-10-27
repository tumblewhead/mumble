#!/usr/bin/env python3
"""Build the frozen finite C probe and preserve command/compiler/source identity.

Compilation only. This program never launches a scientific executable.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import resource
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
EXP = Path("experiments/compact_nonlinear_history_001")

def identity(p):
    b = Path(p).read_bytes()
    return {"bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-id", choices=("build", "build002"), default="build002")
    args = parser.parse_args()
    start = time.monotonic()
    output = ROOT / EXP / args.build_id
    output.mkdir(exist_ok=False)
    cc = str(Path(shutil.which("cc")).resolve())
    flags = ["-std=c99", "-O3", "-Wall", "-Wextra", "-Wpedantic", "-Werror", "-fno-fast-math", "-ffp-contract=off", "-fstack-usage",
             "-I", "include", "-I", str(EXP)]
    sources = [str(EXP / "probe.c"), str(EXP / "compact_history.c"), "src/scm_model.c"]
    commands = []
    objects = []
    for source in sources:
        obj = str(EXP / args.build_id / (Path(source).stem + ".o"))
        command = [cc, *flags, "-c", source, "-o", obj]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        commands.append({"command": command, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
        if result.returncode:
            break
        objects.append(obj)
    binary = EXP / args.build_id / "probe.bin"
    if len(objects) == len(sources):
        command = [cc, "-o", str(binary), *objects, "-lm"]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        commands.append({"command": command, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
    success = len(commands) == 4 and all(c["returncode"] == 0 for c in commands)
    text_files = {}
    for p in sorted(output.glob("*.su")):
        text_files[p.name] = {**identity(p), "contents": p.read_text()}
    symbols = subprocess.run(["nm", "-u", str(output / "compact_history.o")], capture_output=True, text=True, check=False) if (output / "compact_history.o").exists() else None
    own = resource.getrusage(resource.RUSAGE_SELF)
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    receipt = {
        "schema": "mumble_compact_nonlinear_history_build_v1", "status": "passed" if success else "failed",
        "source_identities": {s: identity(ROOT / s) for s in [*sources, "include/scm_model.h", str(EXP / "compact_history.h"), str(EXP / "build.py")]},
        "compiler": {"path": cc, **identity(cc), "version": subprocess.check_output([cc, "--version"], text=True).splitlines()[0]},
        "flags": flags, "commands": commands,
        "binary": {"path": str(binary), **identity(ROOT / binary)} if success else None,
        "stack_usage": text_files,
        "candidate_undefined_symbols": symbols.stdout.splitlines() if symbols else [],
        "limitations": "Host compiler ABI/static stack estimates; external libm, ISR and caller paths are not target high-water measurements. No executable/model invocation occurs in this build.",
        "counts": {"compile_commands": len(objects), "scientific_invocations": 0, "model_steps": 0, "prior_evaluations": 0, "truth_reads": 0},
        "resources": {"CPU_self_s": own.ru_utime + own.ru_stime, "CPU_children_s": children.ru_utime + children.ru_stime,
                      "wall_s": time.monotonic() - start, "peak_RSS_self_bytes": own.ru_maxrss * 1024,
                      "peak_RSS_waited_children_bytes": children.ru_maxrss * 1024},
    }
    receipt_path = ROOT / EXP / (args.build_id + "_receipt.json")
    with receipt_path.open("x") as f:
        json.dump(receipt, f, sort_keys=True, indent=2, allow_nan=False);f.write("\n")
    print(json.dumps({"status": receipt["status"], "binary": receipt["binary"], "receipt": identity(receipt_path),
                      "compile_stderr": [c["stderr"] for c in commands if c["stderr"]]}))
    if not success:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
