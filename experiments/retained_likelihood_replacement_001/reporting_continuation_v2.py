#!/usr/bin/env python3
"""Post-run reporting for the explicit saved-block continuation.

The original parity-rejected attempt remains failed and immutable. Its two
anchor outputs are reused by identity; only the continuation owns the two new
audit passes and two surrogate solves. This adapter imports the unchanged
reviewed numerical reporter and adds continuation-specific provenance gates.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import resource
import sys
import time


AREA = Path(__file__).resolve().parent
ROOT = AREA.parents[1]
EXP = "experiments/retained_likelihood_replacement_001"
SCHEMA = "mumble_retained_likelihood_continuation_reporting_v1"
CORE_SHA256 = "81dc98377d55a96e6a72373c5c7d3eea16a370d14eff89821ce49f56a7eadc26"
ORIGINAL_REVISION = "e8598bb546b83083c02de170304365fd78d36e41"
ORIGINAL_PLAN_SHA256 = "ad51d651ee68b1a19c1685f8486faa6c55e6d7ad21950fcfc2be42dc23aca3a1"
CONTINUATION_PLAN_SHA256 = "1fe5ac901630be7472794df9dc24783f84f16a95008864875ae7afda09e007fa"
ORIGINAL_IDENTITIES = {
    "attempt001/result.json": {
        "bytes": 2309, "sha256": "e338a6ce7a7617c44b4f6cdb6334d0dab7a4d4d35c1badeb703a012177aa9481",
    },
    "attempt001/receipt.json": {
        "bytes": 18307, "sha256": "aafc925349b1c6b73ff8554139612da630ef29f1990704b7fd430aa8915067c0",
    },
    "attempt001/historical_parity.json": {
        "bytes": 30994, "sha256": "a434abe32dc6c432144d71ea72d301992e540e3bf12f23d08ba0e362b5231334",
    },
    "attempt001/old_anchor/stdout.json": {
        "bytes": 12270, "sha256": "c7a898e9cfd66478d01efbf2f7062653984c3f07586f6e05fc5b9731524e14f8",
    },
    "attempt001/replacement_anchor/stdout.json": {
        "bytes": 12455, "sha256": "60620a8d5c128adaf11634919c6b7b54ebb571841cb5dfcd0e45c16798e5e878",
    },
    "execution_process/receipt.json": {
        "bytes": 3040, "sha256": "84e3e76986e6acefc4a36b9f69c5f98828d2527fb0dea32af6d69b07ec850d62",
    },
}


def load_core():
    path = Path(__file__).resolve().with_name("reporting.py")
    if hashlib.sha256(path.read_bytes()).hexdigest() != CORE_SHA256:
        raise ValueError("The original reviewed numerical reporter changed")
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("retained_replacement_reporting_core", path)
    if spec is None or spec.loader is None:
        raise ValueError("Cannot load the pinned numerical reporter")
    core = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(core)
    return core


def bind_manifest(core, directory: Path, receipt: dict, bindings: dict) -> None:
    files = receipt["files"]
    core.require(isinstance(files, dict) and bool(files), "Missing closed file manifest")
    for relative, expected in files.items():
        core.require(relative != "receipt.json" and isinstance(expected, dict) and
                     "sha256" in expected and "bytes" in expected, "Invalid closure file record")
        core.bind_file(core.below(directory, relative), expected, bindings)
    actual = {str(path.relative_to(directory)) for path in directory.rglob("*") if path.is_file()}
    core.require(actual == set(files) | {"receipt.json"}, "Closed output manifest is incomplete")
    core.require(sum((directory / relative).stat().st_size for relative in actual) ==
                 receipt["closed_output_bytes_including_receipt"], "Closed byte accounting differs")
    receipt_path = directory / "receipt.json"
    bindings[str(receipt_path)] = core.identity(receipt_path)


def bind_receipt_sources(core, root: Path, receipt: dict, bindings: dict) -> None:
    for key in ("source_bindings", "input_bindings", "generated_input_and_solver_bindings"):
        core.bind_declared_files(root, receipt[key], bindings, key)


def validate_original_attempt(core, root: Path, bindings: dict) -> dict:
    base = core.below(root, EXP)
    for relative, expected in ORIGINAL_IDENTITIES.items():
        core.bind_file(core.below(base, relative), expected, bindings)
    attempt = base / "attempt001"
    result = core.strict_json(attempt / "result.json")
    receipt = core.strict_json(attempt / "receipt.json")
    parity = core.strict_json(attempt / "historical_parity.json")
    expected_counts = {
        "supervisor_invocations": 1, "model_passes_started": 2, "model_passes_completed": 2,
        "model_steps_reported": 504000, "model_step_count_complete": True,
        "solver_invocations_reserved": 0, "solver_started_markers": 0, "solver_results_saved": 0,
        "learner_calls": 0, "fitter_calls": 0, "truth_reads": 0, "retries": 0,
    }
    core.require(result["schema"] == "mumble_retained_likelihood_replacement_result_v1" and
                 receipt["schema"] == "mumble_retained_likelihood_replacement_receipt_v1" and
                 result["status"] == receipt["status"] == "failed" and
                 receipt["canonical_inference_closed"] is True, "Original attempt lost its preserved failed status")
    core.require(result["source_revision"] == receipt["source_revision"] == ORIGINAL_REVISION and
                 result["plan_sha256"] == receipt["plan_sha256"] == ORIGINAL_PLAN_SHA256,
                 "Original source or frozen contract identity differs")
    core.require(result["source_id"] == core.SOURCE_ID and result["prefix_records"] == core.PREFIX and
                 result["counts"] == receipt["counts"] == expected_counts and receipt["truth_reads"] == 0,
                 "Original source/prefix/call scope differs")
    core.require(len(result["errors"]) == 1 and result["errors"][0]["stage"] == "replacement_anchor" and
                 result["errors"][0]["message"] == "Historical free-fit reconstruction parity failed",
                 "Original failure is not the explicitly admitted parity rejection")
    core.require(result["candidates"] == {} and len(result["passes"]) == 2 and
                 {row["id"] for row in result["passes"]} == {"old_anchor", "replacement_anchor"} and
                 result["coverage_validated"] is False and result["candidate_promoted"] is False,
                 "Original failed attempt unexpectedly contains solves or promotion")
    failed = [row for row in parity["Gram"] if not row["passed"]]
    core.require(parity["passed"] is False and parity["cost"]["passed"] is True and
                 parity["endpoint_SOC"]["passed"] is True and parity["Gram_entries"] == 136 and
                 len(failed) == 1 and failed[0]["packed_index"] == 82 and
                 failed[0]["reference"] == 0. and failed[0]["allowance"] == 0.,
                 "Original parity rejection no longer matches the frozen diagnosis")
    bind_manifest(core, attempt, receipt, bindings)
    bind_receipt_sources(core, root, receipt, bindings)
    outer_dir = base / "execution_process"
    outer = core.strict_json(outer_dir / "receipt.json")
    core.require(outer["schema"] == "mumble_retained_replacement_outer_receipt_v1" and
                 outer["status"] == "failed" and outer["canonical_process_finished"] is True and
                 outer["source_revision"] == ORIGINAL_REVISION and
                 outer["canonical_supervisor_invocations"] == 1 and outer["retries"] == 0 and
                 outer["truth_reads"] == outer["model_calls"] == outer["optimizer_calls"] == 0,
                 "Original outer process identity/activity differs")
    core.require(outer["errors"] == [
        "Canonical supervisor exit or whole-process resource check failed",
        "Inner inference did not complete successfully",
    ], "Original outer receipt has an additional failure")
    process = outer["process"]
    core.require(process["child_launched"] is True and process["exit_code"] == 1 and
                 process["resource_violations"] == [] and process["output_truncated"] is False,
                 "Original process did not fail solely through the preserved parity rejection")
    for name, expected in (("stdout.json", outer["stdout"]), ("stderr.txt", outer["stderr"])):
        core.bind_file(outer_dir / name, expected, bindings)
    core.bind_file(attempt / "receipt.json", outer["inner_receipt"], bindings)
    core.bind_file(attempt / "result.json", outer["inner_result"], bindings)
    core.bind_file(core.below(root, "tools/execute_retained_likelihood_replacement_once.py"), outer["source"], bindings)
    started_path = outer_dir / "started.json"
    started = core.strict_json(started_path)
    core.require(started["command"] == process["command"] and started["source"] == outer["source"] and
                 started["canonical_supervisor_invocations"] == 1 and started["retries"] == 0,
                 "Original outer started/closed evidence disagrees")
    bindings[str(started_path)] = core.identity(started_path)
    actual_files = {path.name for path in outer_dir.iterdir() if path.is_file()}
    core.require(actual_files == {"started.json", "stdout.json", "stderr.txt", "receipt.json"},
                 "Original outer artifact set differs")
    outer_bytes = sum((outer_dir / name).stat().st_size for name in actual_files)
    core.require(outer["attempt_closed_bytes"] == receipt["closed_output_bytes_including_receipt"] and
                 outer["observer_closed_bytes_before_receipt"] == outer_bytes - (outer_dir / "receipt.json").stat().st_size and
                 outer["canonical_closed_output_bytes_including_outer_receipt"] ==
                 receipt["closed_output_bytes_including_receipt"] + outer_bytes and
                 outer["canonical_closed_output_bytes_including_outer_receipt"] <= 2097152,
                 "Original closed output accounting differs")
    core.require(process["CPU_total_s"] <= 30. and process["wall_s_through_wait4"] <= 60. and
                 process["peak_RSS_bytes"] <= 134217728 and outer["outer_own_peak_RSS_bytes"] <= 134217728,
                 "Original resource use exceeds the cumulative contract before continuation")
    return {
        "attempt_path": attempt, "result": result, "receipt": receipt, "outer": outer,
        "parity": parity,
        "old_anchor": core.strict_json(attempt / "old_anchor/stdout.json"),
        "replacement_anchor": core.strict_json(attempt / "replacement_anchor/stdout.json"),
    }


def validate_original_reference(core, root: Path, reference: dict, original: dict, bindings: dict) -> None:
    core.require(reference["directory"] == EXP + "/attempt001" and
                 reference["source_revision"] == ORIGINAL_REVISION and reference["status"] == "failed" and
                 reference["original_failure_reclassified"] is False and
                 reference["counts"] == original["receipt"]["counts"] and
                 reference["closed_output_bytes"] ==
                 original["outer"]["canonical_closed_output_bytes_including_outer_receipt"],
                 "Continuation does not preserve the original failed attempt")
    paths = {"result": "attempt001/result.json", "receipt": "attempt001/receipt.json",
             "parity": "attempt001/historical_parity.json", "outer_receipt": "execution_process/receipt.json"}
    for key, relative in paths.items():
        row = reference[key]
        core.require(row["path"] == EXP + "/" + relative, "Wrong original-reference path")
        expected = ORIGINAL_IDENTITIES[relative]
        core.require(row["sha256"] == expected["sha256"] and row["bytes"] == expected["bytes"],
                     "Original-reference digest differs")
        core.bind_file(core.below(root, row["path"]), row, bindings)


def validate_closed_continuation(core, root: Path, directory: Path, original: dict, bindings: dict) -> dict:
    receipt = core.strict_json(directory / "receipt.json")
    core.require(receipt["schema"] == "mumble_retained_likelihood_replacement_receipt_v1" and
                 receipt["status"] == "completed" and receipt["continuation"] is True and
                 receipt["canonical_inference_closed"] is True and receipt["truth_reads"] == 0 and
                 receipt["failure_only_emergency_closure"] is False and receipt["further_retries"] == 0,
                 "Continuation has no successful ordinary closure")
    bind_manifest(core, directory, receipt, bindings)
    bind_receipt_sources(core, root, receipt, bindings)
    paths = {
        "result": "result.json", "input_summary": "prefix_input.json", "anchors": "anchors.json",
        "old_anchor": "old_anchor/stdout.json", "replacement_anchor": "replacement_anchor/stdout.json",
        "frozen_audit": "frozen_audit/stdout.json", "replacement_audit": "replacement_audit/stdout.json",
        "pair": "solves/pair.json", "frozen_solution": "solves/frozen.result.json",
        "replacement_solution": "solves/replacement.result.json", "worker_result": "solves/worker_result.json",
        "anchor_reuse": "anchor_reuse.json", "underflow_diagnostic": "underflow_diagnostic.json",
    }
    for path in paths.values():
        core.require(path in receipt["files"], "Required continuation output missing from manifest: " + path)
    values = {key: core.strict_json(directory / path) for key, path in paths.items()}
    result = values["result"]
    core.require(result["schema"] == "mumble_retained_likelihood_replacement_result_v1" and
                 result["status"] == "completed" and result["continuation"] is True and result["errors"] == [] and
                 result["truth_reads"] == 0 and result["coverage_validated"] is False and
                 result["candidate_promoted"] is False, "Continuation result failed or has an invalid claim")
    core.require(result["source_id"] == core.SOURCE_ID and result["prefix_records"] == core.PREFIX and
                 result["source_revision"] == receipt["source_revision"] and
                 core.re.fullmatch(r"[0-9a-f]{40}", result["source_revision"]) is not None and
                 result["plan_sha256"] == receipt["plan_sha256"] == ORIGINAL_PLAN_SHA256 and
                 result["continuation_plan_sha256"] == receipt["continuation_plan_sha256"] ==
                 CONTINUATION_PLAN_SHA256, "Continuation source/contract identity differs")
    core.require(any(value["sha256"] == CONTINUATION_PLAN_SHA256 for value in bindings.values()),
                 "Continuation contract is not bound")
    core.require(result["original_attempt"] == receipt["original_attempt"], "Original-reference copies disagree")
    validate_original_reference(core, root, result["original_attempt"], original, bindings)
    expected_current = {
        "supervisor_invocations": 1, "model_passes_started": 2, "model_passes_completed": 2,
        "model_steps_reported": 504000, "model_step_count_complete": True,
        "solver_invocations_reserved": 2, "solver_started_markers": 2, "solver_results_saved": 2,
        "learner_calls": 0, "fitter_calls": 0, "truth_reads": 0, "retries": 0,
    }
    expected_total = {
        "original_counts_verified": True,
        "supervisor_invocations": 2, "model_passes_started": 4, "model_passes_completed": 4,
        "model_steps_reported": 1008000, "model_step_count_complete": True,
        "solver_invocations_reserved": 2, "solver_started_markers": 2, "solver_results_saved": 2,
        "repeated_anchor_passes": 0, "learner_calls": 0, "fitter_calls": 0,
        "truth_reads": 0, "further_retries": 0,
    }
    core.require(result["counts"] == receipt["counts"] == expected_current and
                 result["cumulative_counts"] == receipt["cumulative_counts"] == expected_total,
                 "Current or cumulative inference accounting differs")
    core.require(receipt["previous_closed_output_bytes"] ==
                 original["outer"]["canonical_closed_output_bytes_including_outer_receipt"],
                 "Original bytes omitted or duplicated")
    core.require(len(result["passes"]) == 4, "Expected two reused blocks and two new audits")
    by_name = {row["id"]: row for row in result["passes"]}
    core.require(set(by_name) == {"old_anchor", "replacement_anchor", "frozen_audit", "replacement_audit"},
                 "Unexpected pass identity")
    for label in ("old_anchor", "replacement_anchor"):
        row = by_name[label]
        core.require(row["reused"] is True and row["path"] == paths[label] and
                     row["origin"]["path"] == EXP + "/attempt001/" + paths[label],
                     "Anchor was not explicitly reused from the original pass")
        expected = ORIGINAL_IDENTITIES["attempt001/" + paths[label]]
        core.require(row["origin"]["sha256"] == expected["sha256"] and
                     row["origin"]["bytes"] == expected["bytes"], "Anchor reuse identity differs")
        core.bind_file(directory / paths[label], expected, bindings)
        core.require(values[label] == original[label], "Copied anchor payload differs from original")
    for label in ("frozen_audit", "replacement_audit"):
        core.require(by_name[label].get("reused", False) is False and by_name[label]["path"] == paths[label],
                     "A new audit was mislabeled as a reused pass")
    core.require(values["anchor_reuse"]["new_model_calls"] == 0 and
                 values["anchor_reuse"]["rows"] == [by_name["old_anchor"], by_name["replacement_anchor"]],
                 "Anchor reuse receipt disagrees")
    diagnostic = values["underflow_diagnostic"]
    core.require(diagnostic["corrected_gate_passed"] is True and diagnostic["original_gate_passed"] is False,
                 "Qualified saved-output underflow gate failed or reclassified the original gate")
    pair, worker = values["pair"], values["worker_result"]
    core.require(pair["schema"] == "mumble_replacement_surrogate_pair_v1" and pair["solves"] == 2 and
                 pair["starts_per_arm"] == 1 and pair["retries"] == 0 and
                 pair["model_calls"] == pair["observation_reads"] == 0, "Solver scope differs")
    core.require(worker["schema"] == "mumble_surrogate_worker_status_v1" and worker["status"] == "completed" and
                 worker["exit_code"] == 0 and worker["truth_reads"] == 0 and
                 worker["model_calls"] == worker["observation_reads"] == 0 and
                 worker["counts"] == {"started_markers": 2, "solver_calls_entered": 2,
                                      "solver_calls_returned": 2, "results_saved": 2},
                 "Two surrogate solves were not completely closed")
    for label in ("frozen", "replacement"):
        core.require(pair[label] == values[label + "_solution"], "Pair and saved solution disagree")
        row = result["candidates"][label]
        core.require(row["solver_path"] == paths[label + "_solution"] and row["audit_path"] == paths[label + "_audit"] and
                     row["x"] == pair[label]["candidate_x"] and row["prior_kernel_cost"] == pair[label]["prior_kernel_cost"] and
                     row["solver_status"] == pair[label]["status"] and
                     pair[label]["feasibility"]["strictly_feasible"] is True,
                     "Audited candidate differs from its saved solution or is infeasible")
    core.require(len(receipt["children"]) == 3 and {row["id"] for row in receipt["children"]} ==
                 {"solver_process", "frozen_audit", "replacement_audit"}, "Unexpected additional execution child")
    for child in receipt["children"]:
        saved = core.strict_json(directory / child["id"] / "resources.json")
        core.require(saved == child["resources"] and saved["exit_code"] == 0 and
                     saved["resource_violations"] == [] and saved["output_truncated"] is False,
                     "A continuation child failed its resource gate")
    resources, limits = receipt["resources"], receipt["limits"]
    core.require(resources["CPU_total_s"] <= limits["CPU_total_s_max"] == 30 and
                 resources["wall_s_through_snapshot"] <= limits["wall_total_s_max"] == 60 and
                 resources["supervisor_peak_RSS_bytes"] <= limits["supervisor_RSS_bytes_max"] == 134217728 and
                 resources["maximum_exact_child_peak_RSS_bytes"] <= limits["child_RSS_bytes_max"] == 134217728,
                 "Inner cumulative resource snapshot failed")
    values.update(receipt=receipt, paths=paths)
    return values


def validate_continuation_outer(core, root: Path, directory: Path, closed: dict,
                                original: dict, bindings: dict) -> dict:
    out = core.below(root, EXP + "/continuation_process")
    path = out / "receipt.json"
    outer = core.strict_json(path)
    core.require(outer["schema"] == "mumble_retained_continuation_outer_receipt_v1" and
                 outer["status"] == "completed" and outer["errors"] == [] and
                 outer["continuation_process_finished"] is True and outer["continuation_invocations"] == 1 and
                 outer["further_retries"] == 0 and outer["truth_reads"] == outer["model_calls"] ==
                 outer["optimizer_calls"] == 0 and outer["source_revision"] == closed["result"]["source_revision"],
                 "Continuation outer process did not close successfully")
    process = outer["process"]
    core.require(process["child_launched"] is True and process["exit_code"] == 0 and
                 process["resource_violations"] == [] and process["output_truncated"] is False,
                 "Continuation whole-process exit/resource gate failed")
    core.bind_file(directory / "receipt.json", outer["inner_receipt"], bindings)
    core.bind_file(directory / "result.json", outer["inner_result"], bindings)
    core.bind_file(out / "stdout.json", outer["stdout"], bindings)
    core.bind_file(out / "stderr.txt", outer["stderr"], bindings)
    core.bind_file(core.below(root, "tools/execute_retained_likelihood_continuation_once.py"), outer["source"], bindings)
    old_ref = outer["original_outer_receipt"]
    core.require(old_ref["path"] == EXP + "/execution_process/receipt.json", "Wrong original outer path")
    core.bind_file(core.below(root, old_ref["path"]), old_ref, bindings)
    core.require(old_ref["sha256"] == ORIGINAL_IDENTITIES["execution_process/receipt.json"]["sha256"] and
                 old_ref["bytes"] == ORIGINAL_IDENTITIES["execution_process/receipt.json"]["bytes"],
                 "Wrong original outer identity")
    started_path = out / "started.json"
    started = core.strict_json(started_path)
    core.require(started["schema"] == "mumble_retained_continuation_outer_start_v1" and
                 started["continuation_invocations"] == 1 and started["further_retries"] == 0 and
                 started["original_outer_receipt"] == old_ref and started["source"] == outer["source"] and
                 started["command"] == process["command"], "Continuation outer start/close mismatch")
    bindings[str(started_path)] = core.identity(started_path)
    bindings[str(path)] = core.identity(path)
    previous = original["outer"]["process"]
    expected_cumulative = {
        "CPU_total_s": previous["CPU_total_s"] + process["CPU_total_s"],
        "active_process_wall_s": previous["wall_s_through_wait4"] + process["wall_s_through_wait4"],
        "maximum_wait4_peak_RSS_bytes": max(previous["peak_RSS_bytes"], process["peak_RSS_bytes"]),
        "canonical_supervisor_invocations": 2, "repeated_anchor_passes": 0,
        "CPU_total_s_max": 30, "active_process_wall_s_max": 60, "peak_RSS_bytes_max": 134217728,
    }
    core.require(outer["cumulative_resources"] == expected_cumulative and
                 expected_cumulative["CPU_total_s"] <= 30. and expected_cumulative["active_process_wall_s"] <= 60. and
                 expected_cumulative["maximum_wait4_peak_RSS_bytes"] <= 134217728 and
                 outer["outer_own_peak_RSS_bytes"] <= 134217728,
                 "Cumulative whole-process resource reconstruction or limit failed")
    core.require(started["remaining_limits"]["probe_CPU_s_max"] == 30. - previous["CPU_total_s"] and
                 started["remaining_limits"]["probe_wall_s_max"] == 60. - previous["wall_s_through_wait4"],
                 "Continuation reset its consumed execution budget")
    actual_outer = {p.name for p in out.iterdir() if p.is_file()}
    core.require(actual_outer == {"started.json", "stdout.json", "stderr.txt", "receipt.json"},
                 "Unexpected continuation outer artifact set")
    all_bytes = {}
    for name in ("attempt001", "execution_process", "continuation001", "continuation_process"):
        parent = core.below(root, EXP + "/" + name)
        all_bytes[name] = sum(p.stat().st_size for p in parent.rglob("*") if p.is_file())
    before_outer = dict(all_bytes)
    before_outer["continuation_process"] -= path.stat().st_size
    core.require(outer["directory_bytes_before_outer_receipt"] == before_outer and
                 outer["all_closed_output_bytes_including_outer_receipt"] == sum(all_bytes.values()) and
                 outer["all_closed_output_bytes_max"] == 2097152 and sum(all_bytes.values()) <= 2097152,
                 "All original-plus-continuation closed output byte accounting or cap failed")
    stdout = core.strict_json(out / "stdout.json")
    core.require(stdout["status"] == "completed" and stdout["errors"] == [] and
                 stdout["counts"] == closed["result"]["counts"] and
                 stdout["cumulative_counts"] == closed["result"]["cumulative_counts"] and
                 stdout["decision"] == closed["result"]["transaction"]["decision"],
                 "Continuation stdout disagrees with its closed result")
    outer["actual_closed_directory_bytes"] = all_bytes
    return outer


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--continuation-dir", type=Path, default=AREA / "continuation001")
    parser.add_argument("--truth-evidence-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=AREA)
    args = parser.parse_args()
    core = load_core()
    root, directory, output = args.root.resolve(), args.continuation_dir.resolve(), args.output_dir.resolve()
    core.require(root.is_dir() and directory.is_dir() and output.is_dir(),
                 "Repository, completed continuation and output directory must exist")
    core.require(directory == core.below(root, EXP + "/continuation001"),
                 "Only the separately frozen continuation001 may be reported")
    for immutable in ("attempt001", "execution_process", "continuation001", "continuation_process"):
        core.require(not output.is_relative_to(core.below(root, EXP + "/" + immutable)),
                     "Reporting cannot write into an immutable execution directory")
    names = ("summary.json", "reporting_receipt.json", "reporting_reservation.json")
    core.require(not any((output / name).exists() for name in names),
                 "Reporting already reserved; no overwrite or repeated truth decode")
    start = time.monotonic()
    source = Path(__file__).resolve()
    core_source = source.with_name("reporting.py")
    bindings = {str(source): core.identity(source), str(core_source): core.identity(core_source)}
    activity = {
        "new_evaluator_invocations": 0, "new_battery_model_calls": 0, "new_optimizer_calls": 0,
        "new_learner_calls": 0, "new_source_generations": 0, "observation_numeric_decodes": 0,
        "post_inference_prior_algebra_evaluations": 0, "truth_records_decoded": 0,
        "original_failure_reclassified": False,
    }
    core.write_new_json(output / "reporting_reservation.json", {
        "schema": SCHEMA, "command": [sys.executable, *sys.argv],
        "adapter_source": bindings[str(source)], "unchanged_core_source": bindings[str(core_source)],
        "continuation_directory": str(directory),
        "purpose": "Read-only reporting of the explicit continuation; preserve original failed attempt and exact saved blocks.",
    })
    failure = None
    cumulative_closed = False
    summary = None
    try:
        original = validate_original_attempt(core, root, bindings)
        closed = validate_closed_continuation(core, root, directory, original, bindings)
        outer = validate_continuation_outer(core, root, directory, closed, original, bindings)
        cumulative_closed = True
        for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
            os.environ[key] = "1"
        import numpy as np
        pair = closed["pair"]
        core.require(np.__version__ == pair["policy"]["versions"]["numpy"],
                     "Reporting NumPy differs from frozen solver policy")
        scales = core.vector(np, pair["policy"]["coordinate_SD"], 16, "coordinate scales")
        core.require(bool(np.all(scales > 0.)) and bool(np.array_equal(
            scales, core.vector(np, pair["prior"]["public_unsplit_sd"], 16, "public SD")
        )), "Common reporting coordinate scale differs")
        public = core.vector(np, pair["prior"]["public_unsplit_mean"], 16, "public old anchor")
        warm = core.vector(np, pair["frozen"]["warm_start_x"], 16, "common warm start")
        core.require(bool(np.array_equal(
            warm, core.vector(np, pair["replacement"]["warm_start_x"], 16, "replacement warm start")
        )), "The two solves did not share the fixed warm start")
        core.validate_evaluator(np, original["old_anchor"], public)
        core.validate_evaluator(np, original["replacement_anchor"], warm)
        core.validate_evaluator(np, closed["old_anchor"], public)
        core.validate_evaluator(np, closed["replacement_anchor"], warm)
        charge_time = {key: original["old_anchor"][key] for key in
                       ("charge_Ah", "charge_min_Ah", "charge_max_Ah", "elapsed_physical_s")}
        pass_names = ("old_anchor", "replacement_anchor", "frozen_audit", "replacement_audit")
        core.require(all(all(closed[name][key] == value for key, value in charge_time.items())
                         for name in pass_names), "Reused and new passes have different charge/time integrals")
        core.require(all(closed["input_summary"][key] == value for key, value in charge_time.items()) and
                     closed["input_summary"]["prefix_records"] == 252000 and
                     closed["input_summary"]["prefix_bytes"] == 8064000 and
                     closed["input_summary"]["prefix_sha256"] ==
                     "a2219e78d29ddab4cfd1e02a7b6b520dc74fc0229e995b1aba0044bb240b269d",
                     "Continuation prefix identity or integrals differ")
        core.require(closed["anchors"]["old"]["x"] == public.tolist() and
                     closed["anchors"]["replacement"]["x"] == warm.tolist() and
                     closed["anchors"]["common_warm_start_x"] == warm.tolist() and
                     closed["anchors"]["truth_used"] is False, "Fixed anchors changed")
        arms = {}
        for name, anchor in (("frozen", "old_anchor"), ("replacement", "replacement_anchor")):
            activity["post_inference_prior_algebra_evaluations"] += 1
            arms[name] = core.summarize_arm(
                np, name, pair[name], closed[anchor], closed[name + "_audit"], pair["prior"], scales,
            )
        core.require(activity["post_inference_prior_algebra_evaluations"] == 2,
                     "Post-inference prior algebra budget differs")
        comparison = core.validate_comparison_and_transaction(closed)
        summary = {
            "schema": SCHEMA, "status": "completed",
            "execution_mode": "explicit_saved_block_continuation_after_preserved_parity_failure",
            "source_revision": closed["result"]["source_revision"],
            "plan_sha256": ORIGINAL_PLAN_SHA256,
            "continuation_plan_sha256": CONTINUATION_PLAN_SHA256,
            "source_id": core.SOURCE_ID, "prefix_records": 252000, "charge_and_time": charge_time,
            "original_attempt": closed["result"]["original_attempt"],
            "original_failure": {
                "status": "failed", "source_revision": ORIGINAL_REVISION,
                "reclassified": False, "reason": original["result"]["errors"][0]["message"],
                "preserved_parity": original["parity"],
            },
            "saved_block_reuse": closed["anchor_reuse"],
            "separately_qualified_underflow_diagnostic": closed["underflow_diagnostic"],
            "arms": arms, "transaction": closed["result"]["transaction"],
            "frozen_comparison": closed["result"]["comparison"],
            "comparison_independently_reconstructed": comparison,
            "computed_frozen_minus_replacement_common_objective": comparison["delta_frozen_minus_replacement"],
            "solver_pair_status": pair["status"], "solver_policy": pair["policy"], "prior": pair["prior"],
            "execution": {
                "original_counts": original["receipt"]["counts"],
                "continuation_counts": closed["receipt"]["counts"],
                "cumulative_counts": closed["receipt"]["cumulative_counts"],
                "two_anchor_outputs_reused_by_identity": True, "repeated_anchor_model_passes": 0,
                "two_new_audit_passes": True,
                "unique_model_steps_from_raw_evaluators": sum(closed[name]["model_step_calls"] for name in pass_names),
                "solver_calls_entered": closed["worker_result"]["counts"]["solver_calls_entered"],
                "whole_continuation_process_finished": True,
                "resources": {
                    "cumulative_whole_process": outer["cumulative_resources"],
                    "original_whole_process_wait4": original["outer"]["process"],
                    "continuation_whole_process_wait4": outer["process"],
                    "original_inner_pre_close_snapshot": original["receipt"]["resources"],
                    "continuation_inner_pre_close_snapshot": closed["receipt"]["resources"],
                    "original_outer_observer_peak_RSS_bytes": original["outer"]["outer_own_peak_RSS_bytes"],
                    "continuation_outer_observer_peak_RSS_bytes": outer["outer_own_peak_RSS_bytes"],
                    "all_closed_directory_bytes": outer["actual_closed_directory_bytes"],
                    "all_closed_output_bytes": outer["all_closed_output_bytes_including_outer_receipt"],
                    "all_closed_output_bytes_max": outer["all_closed_output_bytes_max"],
                    "scope": outer["scope"],
                    "RSS_interpretation": "Per-process/high-water measurements, not summed concurrent process-tree memory.",
                },
            },
            "evidence_ownership": pair["evidence_ownership"],
            "local_shape_policy": core.SHAPE_LIMITATIONS,
            "coverage_validated": False, "candidate_promoted": False,
        }
        # No truth member has been opened before all original and continuation
        # identities, numerical outputs and cumulative outer gates pass.
        truth, truth_binding = core.read_verified_endpoint_truth(root, args.truth_evidence_root.resolve(), cumulative_closed)
        activity["truth_records_decoded"] = truth["decoded_records"]
        bindings[truth_binding["path"]] = truth_binding
        restoration = core.below(root, core.RESTORATION_MEMBER)
        bindings[str(restoration)] = core.identity(restoration)
        summary["truth"] = truth
        for arm in arms.values():
            arm["endpoint_point_errors"] = core.endpoint_errors(arm, truth)
        after = {path: core.identity(Path(path)) for path in bindings}
        core.require(after == bindings, "A bound original, continuation, source or truth file changed during reporting")
        summary["reporting_activity"] = dict(activity)
        summary["all_bound_inputs_unchanged"] = True
        summary["reporting_sources"] = {"adapter": bindings[str(source)], "unchanged_core": bindings[str(core_source)]}
        core.write_new_json(output / "summary.json", summary)
    except Exception as error:
        failure = {"type": type(error).__name__, "message": str(error)}
    after = {path: core.identity(Path(path)) if Path(path).is_file() else None for path in bindings}
    if after != bindings and failure is None:
        failure = {"type": "InputMutation", "message": "A bound input changed before reporting receipt closure"}
    receipt = {
        "schema": SCHEMA, "status": "completed" if failure is None else "failed",
        "exception": failure, "continuation_directory": str(directory),
        "original_attempt_status_preserved": "failed",
        "original_and_continuation_cumulative_closure_validated": cumulative_closed,
        "activity": activity, "before": bindings, "after": after,
        "all_bound_inputs_unchanged": after == bindings,
        "adapter_source": core.identity(source), "unchanged_core_source": core.identity(core_source),
        "resources": {"wall_s_before_final_receipt": time.monotonic() - start,
                      "supervisor_own_peak_RSS_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
                      "scope": "Post-inference read-only reporting; separate from canonical execution budgets"},
        "summary": core.identity(output / "summary.json") if (output / "summary.json").exists() else None,
        "limitations": core.SHAPE_LIMITATIONS,
    }
    core.write_new_json(output / "reporting_receipt.json", receipt)
    print(json.dumps({
        "status": receipt["status"], "summary": receipt["summary"], "exception": failure,
        "original_attempt_status": "failed", "new_model_or_optimizer_calls": 0,
    }, allow_nan=False))
    return 0 if failure is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
