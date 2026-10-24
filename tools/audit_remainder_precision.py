#!/usr/bin/env python3
"""Diagnose frozen norm-audit failures using an independent long-double model.

This audit never rewrites the original receipt, gates, C core or probe. It
selects only the failed prediction-norm checks from that receipt and repeats
those saved candidates. A diagnostic pass does not change an original failure
or qualify ordinary C arithmetic as a validated mathematical enclosure.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools/remainder_precision_audit.c"
DEFAULT_RECEIPT = ROOT / "experiments/bounded_event_002/receipt/receipt.json"


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def original_anchor(path: Path) -> tuple[int, float, str, list[list[float]]]:
    tokens = path.read_text().split()
    modes, sigma, identity = int(tokens[0]), float(tokens[1]), tokens[2]
    if modes != 3:
        raise ValueError("This independent diagnostic is explicitly a 3RC model")
    cursor = 3
    groups = []
    for length in (7, 9, 16):
        groups.append([float(x) for x in tokens[cursor:cursor+length]])
        cursor += length
    if any(len(g) != n for g, n in zip(groups, (7, 9, 16), strict=True)):
        raise ValueError("Incomplete original anchor")
    return modes, sigma, identity, groups


def make_input(anchor_path: Path, candidates: list[dict], identity: str) -> str:
    modes, sigma, source_id, groups = original_anchor(anchor_path)
    if source_id != identity:
        raise ValueError("Original anchor/data identity mismatch")
    lines = [f"{modes} {sigma:.17g}"]
    lines.extend(" ".join(format(x, ".17g") for x in group) for group in groups)
    lines.append(str(len(candidates)))
    for candidate in candidates:
        delta = candidate["delta_scaled"]
        if len(delta) != 16:
            raise ValueError("Unexpected candidate dimension")
        lines.append(" ".join(format(x, ".17g") for x in delta))
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    receipt_path, out = args.receipt.resolve(), args.output_dir.resolve()
    if out.exists():
        parser.error("Output directory exists; use a new diagnostic path")
    original_hash = sha(receipt_path)
    original = json.loads(receipt_path.read_text())
    failures = [c for c in original["checks"] if not c["passed"]]
    selected = [c for c in failures if c["name"].endswith("/prediction_bound")]
    if len(failures) != 18 or len(selected) != 18:
        raise ValueError("Expected exactly the 18 frozen prediction-norm failures; refuse to silently change audit scope")
    if any(c["numerical_audit_tolerance"] != 1e-10 for c in selected):
        raise ValueError("Original numerical allowance differs from the declared unchanged 1e-10")
    data = ROOT / "data" / f"{original['case_id']}.csv"
    data_hash = sha(data)
    if data_hash != original["data_sha256"]:
        raise ValueError("Observation source differs from the frozen failed run")
    source_matches = {name: sha(ROOT / name) == digest for name, digest in original["source_sha256"].items()}
    if not all(source_matches.values()):
        raise ValueError("Original B002 source changed; restore or separately document before this frozen diagnosis")
    helper_hashes = {relative(SOURCE): sha(SOURCE), relative(Path(__file__)): sha(Path(__file__))}
    grouped: dict[tuple[str, str], list[dict]] = {}
    for failure in selected:
        run_name, checkpoint, candidate_name, _ = failure["name"].split("/")
        grouped.setdefault((run_name, checkpoint), []).append({"failure": failure, "candidate_name": candidate_name})
    if set(grouped) != {("informative_900", "final"), ("carry_1800_to_2100", "split")}:
        raise ValueError("Unexpected checkpoint grouping for the frozen diagnosis")
    out.mkdir(parents=True)
    metadata = {
        "schema": "mumble_remainder_precision_diagnostic_v1",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "diagnostic_source_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "platform": platform.platform(), "python": platform.python_version(),
        "original_receipt": relative(receipt_path), "original_receipt_sha256": original_hash,
        "original_source_revision": original["source_revision"],
        "original_source_sha256": original["source_sha256"],
        "original_source_files_match": source_matches,
        "original_result": {"passed": sum(c["passed"] for c in original["checks"]),
                            "total": len(original["checks"]), "failed": len(failures),
                            "all_preregistered_checks_passed": original["all_preregistered_checks_passed"],
                            "unchanged_by_this_diagnostic": True},
        "data_sha256": data_hash, "helper_sha256": helper_hashes,
        "scope": "Only 18 frozen failing candidates at two checkpoints; no fit, truth access, threshold change or bound recomputation",
        "input_semantics": "Original JSON/config numbers parsed as double, serialized with round-trip precision, then converted to long double before parameter addition and all model arithmetic",
        "numerical_norm_allowance": 1e-10, "arithmetic_validated": False,
        "original_machine_enclosure_validated": False, "truth_used": False,
        "new_nonlinear_fits": 0, "runs": [], "diagnostic_rows": [], "operational_failures": [],
    }
    compiler = shlex.split(os.environ.get("CC", "cc"))
    version = subprocess.run(compiler + ["--version"], cwd=ROOT, text=True, capture_output=True, check=True)
    flags = ["-std=c99", "-O3", "-Wall", "-Wextra", "-Wpedantic", "-fno-fast-math"]
    with tempfile.TemporaryDirectory(prefix="mumble_precision_audit_") as temporary:
        executable = Path(temporary) / "remainder_precision_audit"
        command = compiler + flags + [str(SOURCE), "-lm", "-o", str(executable)]
        compiled = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        metadata["compiler"] = {"version_command": compiler + ["--version"],
                                "version_stdout": version.stdout, "command": command,
                                "flags": flags, "returncode": compiled.returncode,
                                "stdout": compiled.stdout, "stderr": compiled.stderr}
        if compiled.returncode:
            metadata["operational_failures"].append({"kind": "compile", "returncode": compiled.returncode})
        else:
            metadata["executable_sha256"] = sha(executable)
            for (run_name, checkpoint_name), entries in grouped.items():
                run = next(r for r in original["runs"] if r["name"] == run_name)
                saved_path = receipt_path.parent / run["file"]
                if sha(saved_path) != run["result_sha256"]:
                    raise ValueError("Frozen probe result hash mismatch")
                saved = json.loads(saved_path.read_text())
                checkpoint = next(c for c in saved["checkpoints"] if c["label"] == checkpoint_name)
                candidates = [next(c for c in checkpoint["candidates"] if c["probe_name"] == e["candidate_name"]) for e in entries]
                anchor_path = receipt_path.parent / f"{run_name}_anchor.txt"
                if sha(anchor_path) != run["config_sha256"]:
                    raise ValueError("Frozen configuration hash mismatch")
                stem = f"{run_name}_{checkpoint_name}"
                private_input = out / f"{stem}_input.txt"
                private_input.write_text(make_input(anchor_path, candidates, data_hash))
                invocation = [str(executable), str(data), str(private_input), str(checkpoint["samples"])]
                begin = time.perf_counter()
                try:
                    process = subprocess.run(invocation, cwd=ROOT, capture_output=True, text=True, timeout=60)
                except subprocess.TimeoutExpired as error:
                    stdout = error.stdout.decode(errors="replace") if isinstance(error.stdout, bytes) else error.stdout or ""
                    stderr = error.stderr.decode(errors="replace") if isinstance(error.stderr, bytes) else error.stderr or ""
                    (out / f"{stem}.failed_stdout.txt").write_text(stdout)
                    (out / f"{stem}.stderr.txt").write_text(stderr)
                    metadata["operational_failures"].append({"kind": "timeout", "run": stem})
                    break
                (out / f"{stem}.stderr.txt").write_text(process.stderr)
                if process.returncode:
                    (out / f"{stem}.failed_stdout.txt").write_text(process.stdout)
                    metadata["operational_failures"].append({"kind": "probe_exit", "run": stem, "returncode": process.returncode})
                    break
                try:
                    result = json.loads(process.stdout)
                    if result["samples"] != checkpoint["samples"] or result["candidate_count"] != len(entries):
                        raise ValueError("Precision probe count mismatch")
                except (ValueError, KeyError, TypeError) as error:
                    (out / f"{stem}.failed_stdout.txt").write_text(process.stdout)
                    metadata["operational_failures"].append({"kind": "probe_JSON", "run": stem, "error": str(error)})
                    break
                # Preserve original long-double decimal output before Python's
                # summary conversion to its ordinary floating-point numbers.
                raw_output = out / f"{stem}.json"
                raw_output.write_text(process.stdout)
                metadata["runs"].append({"run": run_name, "checkpoint": checkpoint_name,
                    "samples": checkpoint["samples"], "source_probe": relative(saved_path),
                    "source_probe_sha256": sha(saved_path), "source_config": relative(anchor_path),
                    "source_config_sha256": sha(anchor_path), "input": private_input.name,
                    "input_sha256": sha(private_input), "output": raw_output.name,
                    "output_sha256": sha(raw_output), "command": invocation,
                    "candidate_vectors_sha256": hashlib.sha256(json.dumps(
                        [{"name": c["probe_name"], "delta_scaled": c["delta_scaled"]} for c in candidates],
                        sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest(),
                    "process_wall_s": time.perf_counter()-begin,
                    "LDBL_MANT_DIG": result["LDBL_MANT_DIG"], "DBL_MANT_DIG": result["DBL_MANT_DIG"],
                    "long_double_bytes": result["long_double_bytes"], "LDBL_EPSILON": result["LDBL_EPSILON"]})
                for entry, prior, high in zip(entries, candidates, result["candidates"], strict=True):
                    failure = entry["failure"]
                    norm = high["actual_whitened_remainder_norm"]
                    bound = failure["E_bound"]
                    allowance = failure["numerical_audit_tolerance"]
                    metadata["diagnostic_rows"].append({
                        "original_check": failure["name"], "original_check_passed": False,
                        "original_double_replay_norm": failure["actual_norm"],
                        "original_E_bound": bound, "unchanged_numerical_norm_allowance": allowance,
                        "higher_precision_replay_norm": norm,
                        "higher_precision_within_original_bound_plus_allowance": norm is not None and norm <= bound + allowance,
                        "replay_norm_reduction_factor": failure["actual_norm"] / norm if norm else None,
                        "higher_precision_signed_NLL_difference": high["nonlinear_minus_affine_NLL"],
                        "original_B_bound": prior["remainder"]["B_bound"],
                        "original_delta_scaled": prior["delta_scaled"],
                        "arithmetic_validated": False})
                print(json.dumps({"diagnosed": stem, "candidates": len(entries),
                                  "LDBL_MANT_DIG": result["LDBL_MANT_DIG"]}), flush=True)
    metadata["original_receipt_unchanged"] = sha(receipt_path) == original_hash
    metadata["observations_unchanged"] = sha(data) == data_hash
    metadata["helper_sources_unchanged"] = helper_hashes == {relative(SOURCE): sha(SOURCE), relative(Path(__file__)): sha(Path(__file__))}
    metadata["original_sources_unchanged"] = all(sha(ROOT / name) == digest for name, digest in original["source_sha256"].items())
    metadata["diagnostic_inputs_unchanged"] = all(
        sha(ROOT / r["source_probe"]) == r["source_probe_sha256"] and
        sha(ROOT / r["source_config"]) == r["source_config_sha256"] and
        sha(out / r["input"]) == r["input_sha256"] for r in metadata["runs"])
    metadata["diagnostic_complete"] = len(metadata["diagnostic_rows"]) == 18 and not metadata["operational_failures"]
    metadata["higher_precision_rows_within_original_allowance"] = sum(r["higher_precision_within_original_bound_plus_allowance"] for r in metadata["diagnostic_rows"])
    metadata["interpretation"] = [
        "The frozen original campaign result remains 654/672, with 18 failed numerical norm checks.",
        "Lower errors under higher precision support an arithmetic-floor diagnosis; they do not convert original failures into passes.",
        "Long double/libm is still not validated outward-rounded arithmetic. Its own residual floor may exceed a very small analytical quadratic bound.",
        "No analytical coefficient, 0.1-NLL budget, original 1e-10 norm allowance or 1e-8 NLL allowance was changed.",
    ]
    metadata["finished_utc"] = datetime.now(timezone.utc).isoformat()
    save(out / "receipt.json", metadata)
    okay = (metadata["diagnostic_complete"] and metadata["original_receipt_unchanged"] and
            metadata["observations_unchanged"] and metadata["helper_sources_unchanged"] and
            metadata["original_sources_unchanged"] and metadata["diagnostic_inputs_unchanged"])
    print(json.dumps({"diagnostic_complete": metadata["diagnostic_complete"],
                      "higher_precision_rows_within_original_allowance": metadata["higher_precision_rows_within_original_allowance"],
                      "original_passed": metadata["original_result"]["passed"],
                      "original_total": metadata["original_result"]["total"], "arithmetic_validated": False}), flush=True)
    return 0 if okay else 1


if __name__ == "__main__":
    raise SystemExit(main())
