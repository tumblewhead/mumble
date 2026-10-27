#!/usr/bin/env python3
"""Deterministically package both closed trace roles without decoding values."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import os
from pathlib import Path
import resource
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
EXP = "experiments/live_anchor_integration_001"
RUNNER = "tools/run_live_anchor_integration.py"
RUNNER_SHA256 = "e9dccc8fec9720e39a4c82551637adc9f5dbacf8cee4743a6d49b0f34e889d6f"
SCHEMA = "mumble_live_anchor_trace_publication_v1"
CAPS = {"input_bytes_per_role": 67108864, "compressed_bytes_per_role": 68157440,
        "CPU_s": 60, "wall_s": 90, "RSS_bytes": 134217728,
        "closed_output_bytes": 137363456}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outer-receipt-sha256", required=True)
    parser.add_argument("--outer-receipt-bytes", type=int, required=True)
    args = parser.parse_args()
    source = ROOT / RUNNER
    if hashlib.sha256(source.read_bytes()).hexdigest() != RUNNER_SHA256:
        raise ValueError("Reviewed closure validator differs")
    spec = importlib.util.spec_from_file_location("trace_packaging_closed_runner", source)
    run = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run)
    common = run.common
    output = ROOT / EXP / "publication001"
    common.reserve_directory(output)
    started, cpu_started = time.monotonic(), time.process_time()
    outer_identity = {"bytes": args.outer_receipt_bytes, "sha256": args.outer_receipt_sha256}
    self_path = Path(__file__).resolve()
    self_identity = run.identity(self_path)
    run.write_json(output / "reservation.json", {"schema": SCHEMA, "invocations": 1,
        "outer_receipt": outer_identity, "packaging_source": {"path": str(self_path), **self_identity},
        "caps": CAPS, "compression": {"format": "gzip", "level": 6, "mtime": 0, "filename": ""},
        "trace_value_decodes": 0, "model_prior_optimizer_truth_calls": 0})
    errors, roles, bindings = [], [], {}
    closed = None

    def resources():
        return {"CPU_s": time.process_time() - cpu_started,
                "wall_s": time.monotonic() - started,
                "peak_RSS_bytes": common.own_peak_bytes()}

    def check_resources():
        used = resources()
        common.require(all(used[k] <= CAPS[k] for k in ("CPU_s", "wall_s")) and
                       used["peak_RSS_bytes"] <= CAPS["RSS_bytes"], "Packaging resource cap")

    try:
        closed = run.validate_closed_run(ROOT, outer_identity, read_observations=False)
        capture = common.load_capture()
        trace_dir = Path(closed["trace_directory"])
        commit_path = trace_dir / capture.COMMIT
        common.bind(bindings, commit_path, closed["trace_commit_identity"], "capture_commit")
        commit = run.read_json(commit_path)
        for name in ("original", "object"):
            role = commit[name]
            original = common.safe(trace_dir, role["path"])
            expected = {k: role[k] for k in ("bytes", "sha256")}
            common.require(expected["bytes"] <= CAPS["input_bytes_per_role"], "Trace role is oversized")
            common.bind(bindings, original, expected, name)
            target = output / ("trace_" + ("original" if name == "original" else "independent_copy") + ".jsonl.gz")
            read_digest, read_bytes = hashlib.sha256(), 0
            with original.open("rb") as source_handle, target.open("xb") as compressed_handle:
                with gzip.GzipFile(filename="", mode="wb", compresslevel=6,
                                   fileobj=compressed_handle, mtime=0) as compressor:
                    while chunk := source_handle.read(1048576):
                        read_bytes += len(chunk)
                        common.require(read_bytes <= CAPS["input_bytes_per_role"], "Trace grew during packaging")
                        read_digest.update(chunk)
                        compressor.write(chunk)
                        common.require(compressed_handle.tell() <= CAPS["compressed_bytes_per_role"],
                                       "Compressed role cap")
                        check_resources()
                compressed_handle.flush()
                os.fsync(compressed_handle.fileno())
            common.fsync_directory(output)
            read_identity = {"bytes": read_bytes, "sha256": read_digest.hexdigest()}
            common.require(read_identity == expected, "Compression input identity differs")
            compressed_identity = run.identity(target)
            common.require(compressed_identity["bytes"] <= CAPS["compressed_bytes_per_role"], "Closed compressed role cap")
            decode_digest, decode_bytes = hashlib.sha256(), 0
            with gzip.open(target, "rb") as decompressor:
                while chunk := decompressor.read(1048576):
                    decode_bytes += len(chunk)
                    common.require(decode_bytes <= CAPS["input_bytes_per_role"], "Decompression extent cap")
                    decode_digest.update(chunk)
                    check_resources()
            decoded_identity = {"bytes": decode_bytes, "sha256": decode_digest.hexdigest()}
            common.require(decoded_identity == expected and run.identity(original) == expected,
                           "Decompressed/original identity differs")
            roles.append({"role": name, "original_path": str(original), "original_identity": expected,
                "compressed_path": target.relative_to(ROOT).as_posix(), "compressed_identity": compressed_identity,
                "decompressed_identity": decoded_identity, "raw_role_preserved_in_place": True,
                "publication_reconstruction": "Decompress this file to the exact original role path only in a new restoration location; never overwrite a present capture or silently change canonical status."})
        common.require(len(roles) == 2 and roles[0]["compressed_identity"] == roles[1]["compressed_identity"],
                       "Independent deterministic gzip outputs differ")
        common.rehash(bindings)
        run.validate_closed_run(ROOT, outer_identity, read_observations=False)
        common.require(run.identity(self_path) == self_identity, "Packaging source changed")
        check_resources()
    except Exception as error:
        errors.append({"type": type(error).__name__, "message": str(error)[:2048]})
    files = run.manifest(output)
    receipt = {"schema": SCHEMA, "status": "failed" if errors else "completed", "invocations": 1,
        "source_revision": closed["source_revision"] if closed else None, "outer_receipt": outer_identity,
        "packaging_source": {"path": str(self_path), **self_identity},
        "capture_commit_identity": closed["trace_commit_identity"] if closed else None,
        "source_bindings": list(bindings.values()), "roles": roles,
        "compression": {"format": "gzip", "level": 6, "mtime": 0, "filename": ""},
        "resources_before_final_receipt": resources(), "files": files,
        "closed_output_bytes_including_receipt": 0, "caps": CAPS, "errors": errors,
        "trace_value_decodes": 0, "observation_archive_opens": 0,
        "model_prior_optimizer_truth_calls": 0, "canonical_status_changed": False,
        "scope": "Lossless publication copies of both existing captured roles; raw roles and original closed manifests remain unchanged locally."}
    for _ in range(24):
        size = sum(r["bytes"] for r in files.values()) + len(run.encode_json(receipt))
        if size > CAPS["closed_output_bytes"] and not any(r["message"] == "Packaging closed output cap" for r in errors):
            errors.append({"type": "ResourceFailure", "message": "Packaging closed output cap"})
            receipt["status"] = "failed"
        if receipt["closed_output_bytes_including_receipt"] == size:
            break
        receipt["closed_output_bytes_including_receipt"] = size
    else:
        raise ValueError("Packaging receipt byte count did not stabilize")
    run.write_json(output / "receipt.json", receipt)
    print(run.encode_json({"schema": SCHEMA, "status": receipt["status"],
        "receipt": {"path": str(output / "receipt.json"), **run.identity(output / "receipt.json")},
        "roles": roles, "errors": errors}).decode(), end="")
    return 0 if receipt["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
