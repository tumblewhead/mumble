#!/usr/bin/env python3
"""Measure compact host object lifetimes and compiler frames; no target claim."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SHARED_FUNCTIONS = {
    "scm_model": {"scm_model_ntheta", "scm_model_nalpha", "scm_model_init", "scm_ocv_validate", "scm_ocv_eval"},
    "scm_evidence": {"scm_evidence_packed_index", "scm_evidence_factor_cost", "scm_evidence_factor_rms_sigma"},
    "scm_assess": {"scm_assess_options_default"},
}
# Reviewed against this revision's source and objdump -dr output, including
# emitted calls after compiler inlining. Re-review after source/compiler changes.
CALLPATHS = {
    "initialization": [
        [("scm_compact_remainder", "scm_compact_remainder_init"), ("scm_model", "scm_model_ntheta")],
        [("scm_compact_evidence", "scm_compact_evidence_init"), ("scm_model", "scm_model_init")],
        [("scm_compact_evidence", "scm_compact_evidence_init"), ("scm_compact_evidence", "parameters_valid"), ("scm_model", "scm_model_ntheta")],
    ],
    "paired_ingestion": [
        [("scm_compact_remainder", "scm_compact_remainder_evidence_push"), ("scm_compact_evidence", "scm_compact_evidence_push"), ("scm_compact_evidence", "stage_seal"), ("scm_compact_evidence", "qr_row"), ("scm_evidence", "scm_evidence_packed_index")],
        [("scm_compact_remainder", "scm_compact_remainder_evidence_push"), ("scm_compact_remainder", "advance"), ("scm_compact_remainder", "max_first")],
        [("scm_compact_remainder", "scm_compact_remainder_evidence_push"), ("scm_compact_remainder", "advance"), ("scm_compact_remainder", "max_second")],
    ],
    "focused_target_query": [
        [("scm_compact_assess", "scm_compact_assess"), ("scm_compact_evidence", "scm_compact_evidence_snapshot_into"), ("scm_compact_evidence", "qr_row"), ("scm_evidence", "scm_evidence_packed_index")],
        [("scm_compact_assess", "scm_compact_assess"), ("scm_compact_assess", "diagnose")],
    ],
    "remainder_query": [
        [("scm_compact_remainder", "scm_compact_remainder_query"), ("scm_compact_evidence", "scm_compact_evidence_check_candidate"), ("scm_compact_evidence", "parameters_valid"), ("scm_model", "scm_model_ntheta")],
        [("scm_compact_remainder", "scm_compact_remainder_query"), ("scm_evidence", "scm_evidence_factor_cost"), ("scm_evidence", "scm_evidence_packed_index")],
    ],
}


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def command(*args: str) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=ROOT / "build/scm_compact_probe")
    parser.add_argument("--stack-dir", type=Path, default=ROOT / "build/compact-stack")
    parser.add_argument("--probe-result", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    binary, stack_dir, out = args.binary.resolve(), args.stack_dir.resolve(), args.output.resolve()
    if out.exists():
        parser.error("Output exists; preserve prior accounting and select a new path")
    sizes = json.loads(command(str(binary), "--sizes"))
    if args.probe_result:
        comparison = json.loads(args.probe_result.read_text())
        if comparison["owned_objects_bytes"] != sizes["complete_owned_objects"]:
            raise ValueError("Replay aggregate size differs from current binary")
    frames, stack_hashes, selected = [], {}, []
    required = {"scm_compact_evidence", "scm_compact_remainder", "scm_compact_assess", *SHARED_FUNCTIONS}
    for stem in sorted(required):
        path = stack_dir / f"{stem}.su"
        stack_hashes[path.name] = sha(path)
        for line in path.read_text().splitlines():
            location, amount, qualifier = line.split("\t")
            function = location.rsplit(":", 1)[-1]
            entry = {"object": stem, "function": function, "bytes": int(amount), "qualifier": qualifier, "location": location}
            frames.append(entry)
            if stem.startswith("scm_compact_") or function in SHARED_FUNCTIONS.get(stem, set()):
                selected.append(entry)
    sections = {}
    for line in command("size", "-A", str(binary)).splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[0].startswith("."):
            sections[fields[0]] = int(fields[1])
    symbols = []
    for line in command("nm", "--size-sort", "-S", str(binary)).splitlines():
        fields = line.split()
        if len(fields) == 4 and fields[2] in ("b", "B", "d", "D"):
            symbols.append({"name": fields[3], "bytes": int(fields[1], 16), "type": fields[2]})
    compact_symbol = next(s for s in symbols if s["name"] == "compact")
    if compact_symbol["bytes"] != sizes["complete_owned_objects"]:
        raise ValueError("Actual owned aggregate symbol does not match sizeof")
    persistent = sizes["config"] + sizes["compact_evidence"] + sizes["compact_remainder"]
    auxiliaries = sizes["sample"] + sizes["remainder_result"] + sizes["caller_delta"]
    baseline = sum(sizes[n] for n in ("reference_evidence", "reference_evidence_workspace", "reference_remainder", "reference_remainder_workspace"))
    ingestion = persistent + sizes["ingest_phase"]
    all_owned = sizes["complete_owned_objects"]
    frame_index = {(f["object"], f["function"]): f for f in frames}
    callpaths = {}
    for phase, paths in CALLPATHS.items():
        reviewed = []
        for path in paths:
            entries = [frame_index[node] for node in path]
            reviewed.append({"frames": entries, "bytes": sum(f["bytes"] for f in entries)})
        maximum = max(p["bytes"] for p in reviewed)
        callpaths[phase] = {"reviewed_paths": reviewed, "maximum_own_source_bytes": maximum,
                            "objects_plus_own_source_bytes": all_owned + maximum}
    result = {
        "schema": "mumble_compact_memory_v1", "source_revision": command("git", "rev-parse", "HEAD").strip(),
        "platform": platform.platform(), "compiler": command("cc", "--version").splitlines()[0],
        "compile_flags": "make compact-stack default: -Iinclude -std=c99 -O3 -Wall -Wextra -Wpedantic -fstack-usage",
        "binary_sha256": sha(binary), "sizeof_bytes": sizes,
        "lifetimes": {
            "owned_immutable_RAM_configuration": sizes["config"],
            "persistent_configuration_and_banks": persistent,
            "ingestion_phase_scratch": sizes["ingest_phase"],
            "query_phase_workspace_report_options": sizes["query_phase"],
            "actual_serialized_phase_union": sizes["serialized_phase_union"],
            "sample_remainder_result_caller_delta": auxiliaries,
            "aggregate_padding": all_owned - persistent - sizes["serialized_phase_union"] - auxiliaries,
            "complete_owned_objects": all_owned,
            "ordinary_ingestion_objects": ingestion,
            "query_objects_before_input_result_delta": persistent + sizes["query_phase"],
            "old_paired_ingestion_objects": baseline,
            "paired_ingestion_reduction_bytes": baseline - ingestion,
            "paired_ingestion_reduction_percent": 100.0 * (baseline - ingestion) / baseline,
            "remaining_before_stack_external_to_10240B": 10240 - all_owned,
            "phase_contract": "Ingestion and target diagnostics cannot overlap. Query report/options/eigenvalues live inside the phase union and must be consumed or copied before the next ingest; copied output costs extra RAM.",
            "included": "One RAM config, both live QR factors, carried model/metadata, full remainder state/audit fields, actual largest phase union, one sample, one remainder result, one16-double trial vector.",
            "backing_OCV_bytes": 0,
            "OCV_scope": "This paired remainder model uses the built-in illustrative OCV. A PWL evidence-only caller must separately account for immutable OCV arrays.",
        },
        "stack": {
            "records": frames, "file_sha256": stack_hashes,
            "selected_compact_and_shared_records": selected,
            "largest_selected_frame_bytes": max(f["bytes"] for f in selected),
            "loose_sum_selected_frames_bytes": sum(f["bytes"] for f in selected),
            "objects_plus_loose_sum_bytes": all_owned + sum(f["bytes"] for f in selected),
            "reviewed_phase_callpaths": callpaths,
            "largest_reviewed_callpath_bytes": max(p["maximum_own_source_bytes"] for p in callpaths.values()),
            "objects_plus_largest_reviewed_callpath_bytes": all_owned + max(p["maximum_own_source_bytes"] for p in callpaths.values()),
            "callpath_review": "Independent source/.su/objdump -dr review of the current host objects. Competing paths shown; sequential frames are not added together. Tail calls conservatively included. Re-review if source, flags or compiler changes. This remains own-source estimation, not full worst-case runtime measurement.",
            "scope": "Compiler-reported own-source frames, including init. The sum includes mutually exclusive APIs and is deliberately loose, not the measured simultaneous stack. Shared helpers are selected by compact-path reachability. Inlined locals belong to their caller frame. dynamic,bounded records retain the compiler's maximum label.",
            "unmeasured": "libm/libc, external callers, interrupts, runtime and target compiler/ABI stack; no complete worst-case stack proof.",
        },
        "host_comparison_harness": {
            "ELF_sections_bytes": sections,
            "ELF_data_plus_bss_bytes": sections.get(".data", 0) + sections.get(".bss", 0),
            "named_writable_symbols": symbols,
            "scope": "Includes original reference, old diagnostics, CSV/candidate arrays and host runtime symbols; do not mislabel the whole comparison executable as the compact subsystem.",
        },
        "remaining_costs": [
            "Known-input acquisition backlog while target query is running and any output retained across ingestion",
            "Exactly-once delivery ledger beyond the bank/source/index API and complete checkpoint/recovery staging",
            "Autonomous nonlinear solver state/workspace, if selected later",
            "Library/caller/interrupt/runtime stack and actual Cortex-M23 code generation",
            "Flash/NVM and immutable configuration placement require a target-specific separate account",
        ],
        "target_qualified": False, "full_firmware_memory_qualified": False,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": str(out), "owned_bytes": all_owned, "ingestion_bytes": ingestion,
                      "loose_own_stack_bytes": result["stack"]["loose_sum_selected_frames_bytes"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
