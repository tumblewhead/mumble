#!/usr/bin/env python3
"""Record B002 host storage/compiler stack accounting without MCU claims.

The supplied remainder probe must match its sibling campaign receipt.
Stack objects are rebuilt with the Makefile's current compiler/flags.
No estimator campaign is rerun, and an existing output is never overwritten.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import platform
from pathlib import Path
import shlex
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / "build/scm_remainder_probe"
STACK_DIR = ROOT / "build/remainder-stack"
SOURCES = (
    "Makefile", "tools/remainder_probe.c", "src/scm_remainder.c",
    "include/scm_remainder.h", "src/scm_evidence.c",
    "include/scm_evidence.h", "src/scm_model.c", "include/scm_model.h",
    "src/scm_assess.c", "include/scm_assess.h", "include/scm_estimator.h",
)
PROBE_OBJECTS = (
    "input_config", "online_bank", "online_work", "snapshot",
    "diagnostic_fit", "diagnostic_assessment", "diagnostic_work",
    "diagnostic_options", "gradient", "local_step", "target_gradient",
    "input_candidates", "direct_normal", "direct_gradient", "audit_jacobian",
    "candidate_theta", "candidate_alpha", "audit_anchor", "audit_candidate",
    "audit_anchor_row", "audit_candidate_row", "audit_theta_jac", "csv_line",
    "source_hex", "candidate_count",
    "remainder_bank", "remainder_work", "remainder_query",
    "candidate_names", "candidate_classes", "candidate_available",
    "candidate_scales", "input_candidate_count", "audit_alpha_precise",
    "nll_budget", "checkpoint_anchor_cost",
)


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                          check=check)


def relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def provenance(probe_path: Path, source_hashes: dict[str, str]) -> dict:
    sibling = probe_path.parent / "receipt.json"
    result = {"probe_result": relative(probe_path), "probe_sha256": sha(probe_path),
              "binary": relative(BINARY), "binary_sha256": sha(BINARY)}
    if not sibling.exists():
        raise ValueError("A matching companion receipt.json is required")
    receipt = json.loads(sibling.read_text())
    if receipt.get("binary_sha256") != result["binary_sha256"]:
        raise ValueError("Probe companion receipt does not match current probe binary")
    mismatched = [name for name, digest in source_hashes.items()
                  if receipt.get("source_sha256", {}).get(name) != digest]
    if mismatched:
        raise ValueError(f"Probe receipt/source mismatch: {mismatched}")
    matching = [r for r in receipt.get("runs", []) if r.get("file") == probe_path.name]
    if len(matching) != 1 or matching[0].get("result_sha256") != result["probe_sha256"]:
        raise ValueError("Probe result hash is absent or mismatched in companion receipt")
    result.update({"verification": "binary_source_and_result_match_companion_receipt",
                   "companion_receipt": relative(sibling), "companion_sha256": sha(sibling),
                   "campaign_source_revision": receipt.get("source_revision")})
    return result


def compile_stack() -> dict:
    command = ["make", "--no-print-directory", "-B", "remainder-stack"]
    completed = run(command)
    recipes = []
    versions = {}
    for line in completed.stdout.splitlines():
        if "-fstack-usage" not in line:
            continue
        tokens = shlex.split(line)
        if "-c" not in tokens or "-o" not in tokens:
            continue
        first_option = next((i for i, token in enumerate(tokens) if token.startswith("-")), len(tokens))
        compiler = tokens[:first_option]
        key = shlex.join(compiler)
        if key not in versions:
            version_command = compiler + ["--version"]
            version = run(version_command, check=False)
            versions[key] = {"command": version_command, "returncode": version.returncode,
                             "stdout": version.stdout.strip(), "stderr": version.stderr.strip()}
        recipes.append({"argv": tokens, "source": tokens[tokens.index("-c") + 1],
                        "object": tokens[tokens.index("-o") + 1], "compiler": compiler,
                        "flags_before_source": tokens[first_option:tokens.index("-c")]})
    if len(recipes) != 5:
        raise ValueError("Expected five recorded stack compilation commands")
    return {"command": command, "recipes": recipes, "compiler_versions": versions,
            "stdout": completed.stdout, "stderr": completed.stderr,
            "meaning": "Fresh host compilation; does not rerun fitting or the probe"}


def stack_frames() -> tuple[list[dict], dict[tuple[str, str], dict]]:
    files = []
    by_name = {}
    for path in sorted(STACK_DIR.glob("*.su")):
        frames = []
        for line in path.read_text().splitlines():
            fields = line.split("\t")
            if len(fields) != 3:
                raise ValueError(f"Unrecognized .su line in {path}: {line}")
            location, count, qualifier = fields
            source, lineno, column, function = location.rsplit(":", 3)
            frame = {"function": function, "source": source, "line": int(lineno),
                     "column": int(column), "frame_bytes": int(count), "qualifier": qualifier}
            frames.append(frame)
            # GCC may append .constprop/.isra suffixes to local functions.
            base = function.split(".", 1)[0]
            key = (source, base)
            if key not in by_name or by_name[key]["frame_bytes"] < frame["frame_bytes"]:
                by_name[key] = frame
        object_path = path.with_suffix(".o")
        files.append({"path": relative(path), "sha256": sha(path), "frames": frames,
                      "object_sha256": sha(object_path) if object_path.exists() else None})
    if len(files) != 5:
        raise ValueError("Expected five .su files in build/remainder-stack")
    return files, by_name


def paths(frames: dict[tuple[str, str], dict]) -> list[dict]:
    # Source qualification keeps local names such as bounded distinct. Calls
    # are sequential branches, not one artificial sum of every helper frame.
    evidence = lambda name: ("src/scm_evidence.c", name)
    remainder = lambda name: ("src/scm_remainder.c", name)
    model = lambda name: ("src/scm_model.c", name)
    assess = lambda name: ("src/scm_assess.c", name)
    probe = lambda name: ("tools/remainder_probe.c", name)
    paired = [remainder("scm_remainder_evidence_push")]
    advance = paired + [remainder("advance")]
    query = [remainder("scm_remainder_query")]
    emit = [probe("main"), probe("emit_checkpoint")]
    definitions = {
        "evidence_initialization_model": [evidence("scm_evidence_init"), model("scm_model_init")],
        "evidence_initialization_support": [evidence("scm_evidence_init"), evidence("parameters_valid"), evidence("bounded")],
        "remainder_initialization_support": [remainder("scm_remainder_init"), remainder("config_valid"), remainder("bounded")],
        "remainder_initialization_box": [remainder("scm_remainder_init"), remainder("exponential_box")],
        "remainder_initialization_pair": [remainder("scm_remainder_init"), remainder("pair")],
        "paired_binding": paired + [remainder("matched"), remainder("same_config"), model("scm_model_ntheta")],
        "paired_advance_first_extremum": advance + [remainder("max_first"), remainder("q_exp")],
        "paired_advance_second_extremum": advance + [remainder("max_second"), remainder("second_exp")],
        "paired_advance_range": advance + [remainder("range_step")],
        "paired_advance_coefficient": advance + [remainder("add_bound")],
        "paired_evidence_model_OCV": paired + [evidence("scm_evidence_push"), model("scm_model_step"), model("scm_ocv_eval")],
        "paired_evidence_prediction": paired + [evidence("scm_evidence_push"), model("scm_model_predict")],
        "paired_evidence_event_merge_QR": paired + [evidence("scm_evidence_push"), evidence("seal_staged"), evidence("merge"), evidence("qr_row"), evidence("scm_evidence_packed_index")],
        "paired_evidence_residual_monitor": paired + [evidence("scm_evidence_push"), evidence("seal_staged"), evidence("scm_evidence_factor_rms_sigma"), evidence("scm_evidence_packed_index")],
        "independent_remainder_audit_push": [remainder("scm_remainder_push"), remainder("advance"), remainder("max_second"), remainder("second_exp")],
        "query_binding": query + [remainder("matched"), remainder("same_config"), model("scm_model_ntheta")],
        "query_guard_support": query + [evidence("scm_evidence_check_candidate"), evidence("parameters_valid"), evidence("bounded")],
        "query_guard_OCV": query + [evidence("scm_evidence_check_candidate"), model("scm_ocv_eval")],
        "query_factor_cost": query + [evidence("scm_evidence_factor_cost"), evidence("scm_evidence_packed_index")],
        "seal_event_merge_QR": [evidence("scm_evidence_seal"), evidence("seal_staged"), evidence("merge"), evidence("qr_row"), evidence("scm_evidence_packed_index")],
        "snapshot_merge_QR": [evidence("scm_evidence_snapshot"), evidence("merge"), evidence("qr_row"), evidence("scm_evidence_packed_index")],
        "factor_normal": [evidence("scm_evidence_factor_normal"), evidence("scm_evidence_packed_index")],
        "assessment_diagnose": [assess("scm_assess"), assess("diagnose")],
        "probe_candidate_model": emit + [probe("emit_candidate"), model("scm_model_step"), model("scm_ocv_eval")],
        "probe_candidate_query_guard": emit + [probe("emit_candidate")] + query + [evidence("scm_evidence_check_candidate"), model("scm_ocv_eval")],
        "probe_candidate_query_cost": emit + [probe("emit_candidate")] + query + [evidence("scm_evidence_factor_cost"), evidence("scm_evidence_packed_index")],
        "probe_moment_audit": emit + [probe("audit_moments"), model("scm_model_step"), model("scm_ocv_eval")],
        "probe_candidate_generation": emit + [probe("make_candidates"), probe("add_candidate")],
        "probe_region_bound": emit + [probe("region_json")],
        "probe_assessment": emit + [assess("scm_assess"), assess("diagnose")],
        "probe_evidence_initialization": [probe("main"), probe("read_anchor"), evidence("scm_evidence_init"), model("scm_model_init")],
        "probe_remainder_initialization_support": [probe("main"), probe("read_anchor"), remainder("scm_remainder_init"), remainder("config_valid"), remainder("bounded")],
        "probe_remainder_initialization_box": [probe("main"), probe("read_anchor"), remainder("scm_remainder_init"), remainder("exponential_box")],
        "probe_paired_ingestion_model": [probe("main")] + paired + [evidence("scm_evidence_push"), model("scm_model_step"), model("scm_ocv_eval")],
        "probe_paired_ingestion_bound": [probe("main")] + advance + [remainder("max_second"), remainder("second_exp")],
        "probe_paired_ingestion_QR": [probe("main")] + paired + [evidence("scm_evidence_push"), evidence("seal_staged"), evidence("merge"), evidence("qr_row"), evidence("scm_evidence_packed_index")],
        "probe_read_csv": [probe("main"), probe("read_sample"), probe("space")],
        "probe_snapshot": emit + [evidence("scm_evidence_snapshot"), evidence("merge"), evidence("qr_row"), evidence("scm_evidence_packed_index")],
    }
    answer = []
    for name, chain in definitions.items():
        components = []
        for source, function in chain:
            f = frames.get((source, function))
            components.append({"source": source, "function": function,
                               "frame_bytes": f["frame_bytes"] if f else 0,
                               "status": "separate_reported_frame_added_conservatively" if f else "not_separately_reported_assumed_inlined_in_caller"})
        answer.append({"name": name, "components": components,
                       "project_frame_sum_bytes": sum(c["frame_bytes"] for c in components),
                       "external_library_stack_bytes": None})
    return answer


def linker_accounting(expected_probe_bytes: int) -> dict:
    result = {"binary_sha256": sha(BINARY), "runtime_peak_or_target_SRAM": False}
    if shutil.which("size"):
        command = ["size", str(BINARY)]
        s = run(command)
        columns = s.stdout.splitlines()[-1].split()
        text_bytes, data_bytes, bss_bytes = map(int, columns[:3])
        result.update({"size_command": command, "size_stdout": s.stdout,
                       "BSD_text_bytes_including_readonly_content": text_bytes,
                       "BSD_data_bytes": data_bytes, "BSD_bss_bytes": bss_bytes,
                       "data_plus_bss_bytes": data_bytes + bss_bytes,
                       "data_plus_bss_minus_probe_sizeof_sum_bytes": data_bytes + bss_bytes - expected_probe_bytes})
        sections = run(["size", "-A", str(BINARY)])
        result["section_table_stdout"] = sections.stdout
    else:
        result["size_status"] = "tool_unavailable"
    if shutil.which("nm"):
        command = ["nm", "-S", "--size-sort", "--radix=d", str(BINARY)]
        n = run(command)
        symbols = []
        own = []
        for line in n.stdout.splitlines():
            fields = line.split()
            if len(fields) == 4 and fields[0].isdigit() and fields[1].isdigit():
                address, count, kind, name = fields
                if kind in "bBdDsSgG":
                    record = {"name": name, "type": kind, "bytes": int(count), "address": int(address)}
                    symbols.append(record)
                    if name in PROBE_OBJECTS:
                        own.append(record)
        missing = sorted(set(PROBE_OBJECTS) - {s["name"] for s in own})
        own_bytes = sum(s["bytes"] for s in own)
        if missing or own_bytes != expected_probe_bytes:
            raise ValueError(f"nm/probe static accounting mismatch: missing={missing}, nm={own_bytes}, sizeof={expected_probe_bytes}")
        result.update({"nm_command": command, "probe_named_static_objects": own,
                       "probe_named_static_bytes": own_bytes,
                       "other_named_host_static_objects": [s for s in symbols if s["name"] not in PROBE_OBJECTS],
                       "nm_matches_probe_sizeof_sum": True})
    else:
        result["nm_status"] = "tool_unavailable"
    result["interpretation"] = (
        "Linker section sizes include padding and host startup/static objects. Text includes readonly content. "
        "These host ELF sections are not an MCU flash/SRAM budget, process RSS, dynamic-loader allocation or runtime peak."
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe-result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    probe_path = args.probe_result.resolve()
    probe = json.loads(probe_path.read_text())
    if probe.get("schema") != "mumble_remainder_probe_v1":
        raise ValueError("Expected a B002 remainder probe result")
    memory = probe["memory"]
    source_hashes = {name: sha(ROOT / name) for name in SOURCES}
    origin = provenance(probe_path, source_hashes)
    binary_hash = sha(BINARY)
    compilation = compile_stack()
    files, frames = stack_frames()
    call_paths = paths(frames)
    path_bytes = {p["name"]: p["project_frame_sum_bytes"] for p in call_paths}
    if binary_hash != sha(BINARY) or any(sha(ROOT / p) != h for p, h in source_hashes.items()):
        raise ValueError("Source or probe binary changed during accounting")
    bank = memory["bank_bytes"]
    update = memory["update_workspace_bytes"]
    snapshot_bytes = memory["snapshot_output_bytes"]
    diagnostic = memory["diagnostic_objects_bytes"]
    vectors = memory["local_vector_arrays_bytes"]
    config = memory["config_bytes"]
    remainder_bank = memory["remainder_bank_bytes"]
    remainder_work = memory["remainder_workspace_bytes"]
    query_result = memory["remainder_query_result_bytes"]
    double_bytes = memory["factor_numeric_payload_bytes"] // 153
    incoming_sample = 3 * double_bytes
    evidence_ingestion = bank + update
    ingestion = evidence_ingestion + remainder_bank + remainder_work
    if ingestion != memory["paired_ingestion_objects_bytes"]:
        raise ValueError("Paired ingestion sizeof components do not match probe total")
    if remainder_bank + remainder_work + query_result != memory["remainder_incremental_objects_bytes"]:
        raise ValueError("Remainder incremental sizeof components do not match probe total")
    with_query = ingestion + query_result
    with_snapshot = with_query + snapshot_bytes
    simultaneous = with_snapshot + diagnostic + vectors
    budget = 10 * 1024
    total_static = memory["probe_static_objects_sum_bytes"]
    linker = linker_accounting(total_static)
    receipt = {
        "schema": "mumble_remainder_memory_accounting_v1",
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_revision": run(["git", "rev-parse", "HEAD"]).stdout.strip(),
        "worktree_status_before_output": run(["git", "status", "--porcelain"]).stdout,
        "platform": platform.platform(), "machine": platform.machine(),
        "pointer_bits": 64 if sys.maxsize > 2**32 else 32,
        "source_sha256": source_hashes,
        "accounting_helper_sha256": sha(Path(__file__)),
        "probe_provenance": origin,
        "compilation": compilation,
        "exact_probe_sizeof_breakdown": memory,
        "object_totals": {
            "evidence_bank_bytes": bank,
            "evidence_update_workspace_bytes": update,
            "evidence_bank_plus_update_workspace_bytes": evidence_ingestion,
            "remainder_bank_bytes": remainder_bank,
            "remainder_transaction_workspace_bytes": remainder_work,
            "remainder_query_result_bytes": query_result,
            "paired_ingestion_banks_plus_transaction_workspaces_bytes": ingestion,
            "incoming_sample_bytes": incoming_sample,
            "incoming_sample_basis": "scm_sample is three doubles; host double size inferred from 153-double factor payload",
            "paired_ingestion_plus_incoming_sample_bytes": ingestion + incoming_sample,
            "paired_ingestion_query_result_plus_incoming_sample_bytes": with_query + incoming_sample,
            "paired_ingestion_query_result_plus_snapshot_bytes": with_snapshot,
            "simultaneous_ingestion_query_snapshot_diagnostics_vectors_bytes": simultaneous,
            "same_with_separate_retained_input_config_bytes": simultaneous + config,
            "same_with_input_config_and_incoming_sample_bytes": simultaneous + config + incoming_sample,
            "whole_host_probe_static_sizeof_sum_bytes": total_static,
            "design_goal_bytes": budget,
            "paired_ingestion_objects_fit_10KiB_before_external_costs": ingestion + incoming_sample <= budget,
            "implemented_simultaneous_diagnostic_objects_exceed_10KiB": simultaneous > budget,
            "model_state_and_model_row": "Already embedded in bank/update workspace; not added again",
            "transactional_copy": "Evidence workspace contains a staged evidence bank; remainder workspace contains a staged remainder bank. Both are counted. Paired update stages remainder, calls atomic evidence push, then commits remainder; no third bank copy is credited or hidden.",
            "query_snapshot": "The remainder query directly uses the matched evidence history/event factors and allocates no new snapshot. The implemented probe nevertheless retains its original snapshot for diagnostics, so that object remains fully counted.",
            "paired_ancestry_binding": "Remainder state includes an evidence-object pointer and sticky paired-ancestry flag; both are counted by sizeof. Shallow-copy/rebinding continuation is unsupported.",
            "workspace_aliasing_or_union": "Not implemented. No hypothetical phase reuse subtracted from actual totals",
        },
        "stack_files": files,
        "project_call_path_estimates": call_paths,
        "partial_live_bounds": {
            "paired_ingestion_objects_sample_plus_paired_project_stack_bytes": ingestion + incoming_sample + max(value for name, value in path_bytes.items() if name.startswith("paired_")),
            "paired_ingestion_query_objects_plus_query_project_stack_bytes": with_query + max(value for name, value in path_bytes.items() if name.startswith("query_")),
            "simultaneous_diagnostic_objects_plus_project_assessment_stack_bytes": simultaneous + path_bytes["assessment_diagnose"],
            "whole_probe_sizeof_static_plus_largest_listed_project_path_bytes": total_static + max(path_bytes.values()),
            "whole_probe_linker_static_plus_largest_listed_project_path_bytes": linker.get("data_plus_bss_bytes", 0) + max(path_bytes.values()) if "data_plus_bss_bytes" in linker else None,
            "qualification": "Partial accounting with known project frames; external frames and runtime allocation remain additional, so these are not complete runtime peak measurements",
        },
        "stack_interpretation": [
            "Compiler .su frames are tied to the recorded host compiler and flags.",
            "Listed paths conservatively add emitted frames even where calls may be inlined; inlined-only functions have no additional frame beyond caller accounting.",
            "Dynamic,bounded qualifiers are retained. No function reported dynamic,unbounded is silently accepted as bounded.",
            "Call paths are source-derived estimates, not measured stack high-water marks or an exhaustive external-library call graph.",
            "Local helpers are keyed by source file and function to avoid combining unrelated same-named functions. Maximum emitted constprop/isra frame per source/function is used conservatively.",
            "Paired-update remainder advancement and evidence advancement execute sequentially; their descendant frames are separate paths, not incorrectly summed as simultaneous callees.",
        ],
        "host_linker": linker,
        "external_or_unmeasured_costs": [
            "Compiler/ABI-dependent caller frames, interrupt context, task stack and scheduling overhead.",
            "libm calls (hypot, exp, expm1, tanh, log and others) and libc/stdio frames and buffers.",
            "FILE objects, dynamic loader, allocator bookkeeping and host runtime allocations.",
            "Acquisition buffering, communications, persistent-checkpoint buffers and other application state.",
            "External curve storage is zero in this run. B002 supports only the smooth illustrative OCV and explicitly rejects measured PWL tables; future curve/table storage and validated derivative enclosures are additional work.",
            "Target instruction/text size, soft-float implementation, MCU stack, latency, flash and energy.",
        ],
        "claims": {"history_independent_core_object_sizes": True,
                   "no_core_heap_or_retained_raw_trace": True,
                   "remainder_formula_real_arithmetic_analytic": True,
                   "floating_point_outward_rounding_validated": False,
                   "mathematical_envelope_implies_firmware_qualification": False,
                   "complete_10KiB_estimator_demonstrated": False,
                   "Cortex_M23_qualified": False,
                   "MCU_runtime_peak_measured": False},
    }
    unbounded = [f for file in files for f in file["frames"]
                 if "dynamic" in f["qualifier"].split(",") and "bounded" not in f["qualifier"].split(",")]
    receipt["unbounded_project_frames"] = unbounded
    if unbounded:
        receipt["claims"]["project_stack_bounded_by_report"] = False
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"output": relative(output), "sha256": sha(output),
                      "paired_ingestion_objects_bytes": ingestion,
                      "simultaneous_diagnostic_objects_bytes": simultaneous,
                      "Cortex_M23_qualified": False}, allow_nan=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f"memory accounting failed: {error}", file=sys.stderr)
        raise SystemExit(1)
