#!/usr/bin/env python3
"""Authorized one-role publication repair from the intact independent RAW role.

Original package files and receipts remain untouched, including the damaged
gzip and the failed postclosure review. No scientific values are decoded.
"""
from __future__ import annotations

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
RUNNER_SHA = "e9dccc8fec9720e39a4c82551637adc9f5dbacf8cee4743a6d49b0f34e889d6f"
PACKAGER = "tools/package_live_anchor_trace.py"
PACKAGER_SHA = "caf05f388206d340e180504b73b632df0f0cc7c114d69e750d6d3e3bd50de097"
OUTER = {"bytes": 5999, "sha256": "338acf3c491baab5691239c2115f83a750d9422682d72ebb87f51db919452d08"}
RAW = {"bytes": 33494823, "sha256": "b2f9194092392f9001d1cef417db881c1d9b8ff9759ee6731d78a08600b1f46c"}
GZIP = {"bytes": 8568513, "sha256": "1916a1a42aa2027000a75bcb445f1959861e58c21dc991988b2f5bf57c2c3a1c"}
SCHEMA = "mumble_live_anchor_publication_recovery_v1"


def stat_record(path):
    s = path.stat()
    return {"bytes": s.st_size, "device": s.st_dev, "inode": s.st_ino,
            "nlink": s.st_nlink, "mtime_ns": s.st_mtime_ns, "ctime_ns": s.st_ctime_ns}


def matching_open_writers(paths):
    """A bounded-time observation of matching descriptors, not a causal proof."""
    wanted = {str(Path(p).resolve()) for p in paths}
    matches, inaccessible = [], 0
    for process in Path("/proc").iterdir():
        if not process.name.isdigit():
            continue
        try:
            descriptors = list((process / "fd").iterdir())
        except (PermissionError, FileNotFoundError, ProcessLookupError):
            inaccessible += 1
            continue
        for descriptor in descriptors:
            try:
                target = os.readlink(descriptor)
                if target not in wanted:
                    continue
                info = (process / "fdinfo" / descriptor.name).read_text()
                flags = next(int(line.split()[1], 8) for line in info.splitlines() if line.startswith("flags:"))
                if flags & os.O_ACCMODE in (os.O_WRONLY, os.O_RDWR):
                    matches.append({"pid": int(process.name), "fd": int(descriptor.name),
                                    "path": target, "flags_octal": oct(flags)})
            except (PermissionError, FileNotFoundError, ProcessLookupError):
                inaccessible += 1
    return {"matching_open_write_descriptors": matches, "inaccessible_or_disappeared_entries": inaccessible,
            "limit": "Point-in-time descriptor observation only; no attribution or guarantee against past/future writers."}


def main():
    source = ROOT / RUNNER
    if hashlib.sha256(source.read_bytes()).hexdigest() != RUNNER_SHA:
        raise ValueError("Reviewed primary closure source differs")
    spec = importlib.util.spec_from_file_location("package_recovery_closed_runner", source)
    run = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run)
    common, capture = run.common, run.common.load_capture()
    output = ROOT / EXP / "publication_recovery001"
    common.reserve_directory(output)
    started, cpu_started = time.monotonic(), time.process_time()
    self_path = Path(__file__).resolve()
    self_identity = run.identity(self_path)
    sources, inputs, errors, facts = {}, {}, [], {}
    run.write_json(output / "reservation.json", {"schema": SCHEMA,
        "invocations": 1, "independent_raw_recompressions_max": 1,
        "source": {"path": str(self_path), **self_identity}, "outer_receipt": OUTER,
        "raw_expected": RAW, "gzip_expected": GZIP,
        "caps": {"CPU_s": 60, "wall_s": 90, "RSS_bytes": 134217728, "closed_output_bytes": 20971520},
        "model_prior_optimizer_truth_calls": 0, "trace_value_decodes": 0,
        "preservation": "Keep original damaged gzip, all original receipts and failed review unchanged."})

    def resources():
        return {"CPU_s": time.process_time() - cpu_started, "wall_s": time.monotonic() - started,
                "peak_RSS_bytes": common.own_peak_bytes()}

    def limits():
        u = resources()
        common.require(u["CPU_s"] <= 60 and u["wall_s"] <= 90 and u["peak_RSS_bytes"] <= 134217728,
                       "Publication repair resource cap")

    try:
        closed = run.validate_closed_run(ROOT, OUTER, read_observations=False)
        common.bind(sources, self_path, self_identity, "recovery_source")
        common.bind(sources, source, run.identity(source), "primary_validator")
        packager = ROOT / PACKAGER
        common.require(run.identity(packager)["sha256"] == PACKAGER_SHA, "Original packager source changed")
        common.bind(sources, packager, run.identity(packager), "original_packager")
        common.bind(inputs, ROOT / EXP / "publication001/receipt.json",
            {"bytes": 4883, "sha256": "dcc6a97b8dd7926f268bab99370be3d17ed1274cc87abad9aecd5fd9c6e2373a"}, "original_packaging_receipt")
        common.bind(inputs, ROOT / EXP / "review/execution_receipt_review.json",
            {"bytes": 31906, "sha256": "5536fadb285fdee26cc1a6ec318c98a9445fd9a49126304d693ea84f1c508a83"}, "preserved_failed_review")
        trace_dir = Path(closed["trace_directory"])
        commit_path = trace_dir / capture.COMMIT
        common.bind(inputs, commit_path, closed["trace_commit_identity"], "primary_capture_commit")
        commit = run.read_json(commit_path)
        raw_paths = {}
        for role in ("original", "object"):
            raw_paths[role] = common.safe(trace_dir, commit[role]["path"])
            common.require({k: commit[role][k] for k in RAW} == RAW, "Raw role contract differs")
            common.bind(inputs, raw_paths[role], RAW, "raw_" + role)
        intact = ROOT / EXP / "publication001/trace_original.jsonl.gz"
        damaged = ROOT / EXP / "publication001/trace_independent_copy.jsonl.gz"
        common.bind(inputs, intact, GZIP, "intact_original_role_gzip")
        damaged_identity = run.identity(damaged)
        common.require(damaged_identity != GZIP, "Damaged gzip unexpectedly changed again before recovery")
        common.bind(inputs, damaged, damaged_identity, "damaged_independent_role_gzip")
        damaged_stat = stat_record(damaged)
        before_writers = matching_open_writers([*raw_paths.values(), intact, damaged])
        common.require(not before_writers["matching_open_write_descriptors"], "Observed live writer for protected role")
        prefix_matches = False
        if damaged_identity["bytes"] <= GZIP["bytes"]:
            prefix_matches = True
            with damaged.open("rb") as a, intact.open("rb") as b:
                while part := a.read(1048576):
                    if part != b.read(len(part)):
                        prefix_matches = False
                        break
        facts.update(source_revision=closed["source_revision"], capture_commit_identity=closed["trace_commit_identity"],
            damaged_observation={"path": str(damaged), **damaged_identity, "stat": damaged_stat,
                                 "exact_prefix_of_intact_gzip": prefix_matches},
            open_writer_observation_before=before_writers,
            source_inspection="Original script opens each gzip once with xb, closes and fsyncs it, verifies decompression, then has no later write-open to either gzip. No cause is established by source inspection or descriptor snapshots.",
            cause="unattributed")
        run.write_json(output / "before.json", {"schema": SCHEMA, "facts": facts,
            "source_bindings": list(sources.values()), "input_bindings": list(inputs.values())})
        target = output / "trace_independent_copy.jsonl.gz"
        compressed_input_digest, read_bytes = hashlib.sha256(), 0
        with raw_paths["object"].open("rb") as original, target.open("xb") as target_handle:
            with gzip.GzipFile(filename="", mode="wb", compresslevel=6, fileobj=target_handle, mtime=0) as compressor:
                while chunk := original.read(1048576):
                    read_bytes += len(chunk)
                    common.require(read_bytes <= RAW["bytes"], "Independent raw input grew")
                    compressed_input_digest.update(chunk)
                    compressor.write(chunk)
                    limits()
            target_handle.flush()
            os.fsync(target_handle.fileno())
        common.fsync_directory(output)
        common.require({"bytes": read_bytes, "sha256": compressed_input_digest.hexdigest()} == RAW,
                       "Recompression source bytes differ")
        compressed_identity = run.identity(target)
        common.require(compressed_identity == GZIP, "Recovered gzip differs from originally closed identity")
        digest, length = hashlib.sha256(), 0
        with gzip.open(target, "rb") as decompressor:
            while chunk := decompressor.read(1048576):
                length += len(chunk)
                common.require(length <= RAW["bytes"], "Recovered decompression exceeded raw extent")
                digest.update(chunk)
                limits()
        decompressed_identity = {"bytes": length, "sha256": digest.hexdigest()}
        common.require(decompressed_identity == RAW, "Recovered gzip decompression differs")
        common.rehash(sources)
        common.rehash(inputs)
        run.validate_closed_run(ROOT, OUTER, read_observations=False)
        common.require(stat_record(damaged) == damaged_stat, "Damaged gzip metadata changed during recovery")
        after_writers = matching_open_writers([*raw_paths.values(), intact, damaged, target])
        common.require(not after_writers["matching_open_write_descriptors"], "Observed writer after repair")
        facts.update(recovered_path=target.relative_to(ROOT).as_posix(), recovered_identity=compressed_identity,
            decompressed_identity=decompressed_identity, recompression_source=str(raw_paths["object"]),
            independent_raw_recompressions=1, open_writer_observation_after=after_writers)
        limits()
    except Exception as error:
        errors.append({"type": type(error).__name__, "message": str(error)[:2048]})
    files = run.manifest(output)
    receipt = {"schema": SCHEMA, "status": "failed" if errors else "completed", "invocations": 1,
        "source": {"path": str(self_path), **self_identity}, "outer_receipt": OUTER,
        "source_bindings": list(sources.values()), "input_bindings": list(inputs.values()),
        "facts": facts, "resources_before_final_receipt": resources(), "files": files,
        "closed_output_bytes_including_receipt": 0, "errors": errors,
        "trace_value_decodes": 0, "model_prior_optimizer_truth_calls": 0,
        "original_canonical_status_changed": False, "original_packaging_integrity_status": "failed_postclosure",
        "cause": "unattributed", "preserved_failed_review": True}
    for _ in range(24):
        length = sum(row["bytes"] for row in files.values()) + len(run.encode_json(receipt))
        if length > 20971520 and not any(row["message"] == "Repair closed output cap" for row in errors):
            errors.append({"type": "ResourceFailure", "message": "Repair closed output cap"})
            receipt["status"] = "failed"
        if receipt["closed_output_bytes_including_receipt"] == length:
            break
        receipt["closed_output_bytes_including_receipt"] = length
    else:
        raise ValueError("Recovery receipt byte accounting did not stabilize")
    run.write_json(output / "receipt.json", receipt)
    if receipt["status"] == "completed":
        selection = {"schema": "mumble_live_anchor_publication_selection_v1", "status": "selected_after_explicit_recovery",
            "outer_receipt": OUTER, "capture_commit_identity": facts["capture_commit_identity"],
            "original_packaging_receipt": {"path": EXP + "/publication001/receipt.json", **run.identity(ROOT / EXP / "publication001/receipt.json")},
            "original_packaging_integrity_status": "failed_postclosure",
            "preserved_damaged_artifact": facts["damaged_observation"],
            "recovery_receipt": {"path": (output / "receipt.json").relative_to(ROOT).as_posix(), **run.identity(output / "receipt.json")},
            "roles": [{"role": "original", "gzip_path": EXP + "/publication001/trace_original.jsonl.gz", "gzip_identity": GZIP, "raw_identity": RAW},
                      {"role": "independent_object", "gzip_path": facts["recovered_path"], "gzip_identity": GZIP, "raw_identity": RAW,
                       "source": "One recompression of the still-verified independent raw capture; not a relabelled original gzip."}],
            "restoration": "Create both raw roles separately in a new restoration directory, verify RAW identities and independent inodes, then validate original capture metadata. Do not overwrite an existing capture or change canonical scientific status.",
            "cause": "unattributed", "model_prior_optimizer_truth_calls": 0}
        run.write_json(ROOT / EXP / "publication_selection.json", selection)
    print(run.encode_json({"schema": SCHEMA, "status": receipt["status"],
        "receipt": {"path": str(output / "receipt.json"), **run.identity(output / "receipt.json")},
        "facts": facts, "errors": errors}).decode(), end="")
    return 0 if receipt["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
