#!/usr/bin/env python3
"""Report verified partial evidence while preserving the failed canonical run."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path
import resource
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
EXP = "experiments/autonomous_anchor_refinement_001"
PLAN = "plans/autonomous_anchor_failure_reporting_001.json"
PLAN_SHA = "027d86cad6ddea0ad2917bb0cce25d1e7b87b4fd4bc5adec4eb932085e1c2b03"


def require(value, message):
    if not value:
        raise ValueError(message)


def identity(path):
    data = Path(path).read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def read(path):
    return json.loads(Path(path).read_bytes())


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    started, cpu_started = time.monotonic(), time.process_time()
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    resource.setrlimit(resource.RLIMIT_AS, (268435456, 268435456))
    resource.setrlimit(resource.RLIMIT_FSIZE, (2097152, 2097152))
    area = ROOT / EXP
    require(identity(ROOT / PLAN)["sha256"] == PLAN_SHA, "Reporting contract changed")
    plan = read(ROOT / PLAN)
    review_path = area / "pre_failure_reporting_review.json"
    review = read(review_path)
    require(review["status"] == "passed" and review["accepted_prefix_verified"] is True,
            "Partial evidence has not passed independent review")
    for relative in (PLAN, EXP + "/failure_reporting.py", EXP + "/reporting.py", EXP + "/schema.py"):
        require(review["source_sha256"][relative] == identity(ROOT / relative)["sha256"],
                "Failure reporting review does not bind current source: " + relative)
    for relative, expected in plan["pinned_inputs"].items():
        require(identity(ROOT / relative) == expected, "Frozen failure input changed: " + relative)
    # The original helpers are standard-library functions, with no inference on import.
    helper = load("autonomous_anchor_partial_reporting_helpers", area / "reporting.py")
    schema, executable = helper.load_schema(ROOT)
    output = area / "failure_reporting001"
    schema.reserve_directory(output)
    bindings = {}
    activity = {"model_calls": 0, "optimizer_calls": 0, "prior_function_evaluations": 0,
                "observation_numeric_decodes": 0, "raw_truth_file_opens": 0,
                "previous_summary_numeric_reads": 0, "saved_truth_records_reused": 0,
                "inference_outputs_modified": 0, "canonical_retries": 0}
    failure = summary_id = None
    gate_passed = False

    def bind(path, expected=None):
        return helper.register(schema, path, bindings, expected)

    def budget():
        require(time.monotonic() - started <= 10, "Reporting wall cap")
        require(time.process_time() - cpu_started <= 5, "Reporting CPU cap")
        require(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024 <= 67108864,
                "Reporting RSS cap")

    schema.write_json(output / "reservation.json", {
        "schema": "mumble_anchor_failed_run_report_v1", "command": [sys.executable, *sys.argv],
        "contract": bind(ROOT / PLAN), "reporter": bind(Path(__file__)),
        "pre_reporting_review": bind(review_path), "limits": plan["limits"],
        "canonical_run_status": "failed", "inference_retry": False,
    })
    try:
        for relative, expected in plan["pinned_inputs"].items():
            bind(ROOT / relative, expected)
        attempt, outer_dir = area / "attempt001", area / "execution_process"
        result, run, outer = (read(attempt / "result.json"), read(attempt / "receipt.json"),
                              read(outer_dir / "receipt.json"))
        require(result["status"] == run["status"] == outer["status"] == "failed",
                "Canonical failure must remain unchanged")
        require(run["canonical_inference_closed"] is True and outer["canonical_process_finished"] is True,
                "Original process has not closed")
        require(outer["process"]["exit_code"] == 1 and outer["process"]["resource_violations"] == [],
                "Unexpected outer failure")
        require(all(obj["source_revision"] == plan["source_revision"] and
                    obj["plan_sha256"] == plan["original_plan_sha256"] for obj in (result, run, outer)),
                "Canonical source or original contract differs")
        require(outer["inner_receipt"] == identity(attempt / "receipt.json") and
                outer["inner_result"] == identity(attempt / "result.json"), "Outer closure identity differs")
        for directory, receipt in ((attempt, run), (outer_dir, outer)):
            schema.validate_manifest(directory, receipt)
            for relative, expected in schema.manifest(directory).items():
                bind(schema.safe(directory, relative), expected)
        for collection in (run["source_bindings"], run["input_bindings"], outer["source_bindings"]):
            for row in collection:
                bind(row["path"], row)
        damaged = plan["known_failure"]
        damaged_path = (attempt / damaged["relative_path"]).resolve()
        mismatches = []
        for row in run["generated_bindings"]:
            actual = identity(row["path"])
            expected = {key: row[key] for key in ("bytes", "sha256")}
            if actual != expected:
                require(Path(row["path"]).resolve() == damaged_path and expected == damaged["expected"] and
                        actual == damaged["actual"], "Unexpected original generated-file mismatch")
                mismatches.append({"path": damaged["relative_path"], "expected": expected, "actual": actual})
            else:
                bind(row["path"], expected)
        require(len(mismatches) == 1, "Expected exactly the recorded capture-loss failure")
        recovery = area / damaged["separate_recovery"]
        recovery_id = bind(recovery, damaged["expected"])
        require(read(recovery) == read(attempt / "calls/call028_assess/request.json")["trial_block"],
                "Recovered bytes and retained decoded audit differ")
        diagnostic_id = bind(area / "failure_diagnostic.json")
        require(result["counts"] == run["counts"] and result["counts"]["accepted_steps"] == 7,
                "Recorded partial activity differs")
        require(result["counts"]["rejected_trials"] == 2 and len(result["trial_records"]) == 9,
                "Unrecorded final assessment must not become an installed trial")
        ownership = {"source_id": "f0bd54ce53f1944d4f17070b6380dc8317ae895f2fd1628198a1c5408a67f79c",
                     "source_interval": [0, 252000], "cursor": 252000, "prior_copies": 1,
                     "active_likelihood_blocks": 1}
        generations = []
        for index, relative in enumerate(result["generation_records"]):
            state = read(schema.safe(attempt, relative))
            require(state["generation"] == index and state["ownership"] == ownership and
                    state["retired_block_added_as_evidence"] is False, "Accepted ownership differs")
            point = helper.state_report(schema, attempt, state, bindings)
            if generations:
                require(point["computed_common_objective"] < generations[-1]["computed_common_objective"],
                        "Accepted objective is not strictly decreasing")
            generations.append(point)
        require(len(generations) == 8 and result["initial"] == read(attempt / result["generation_records"][0]) and
                result["final"] == read(attempt / result["generation_records"][-1]), "Partial endpoint differs")
        require(generations[0]["x"] == read(attempt / "public_initialization.json")["x"],
                "Public initialization changed")
        trials = []
        for relative in result["trial_records"]:
            trial = read(attempt / relative)
            assessment = read(attempt / trial["assessment"]["path"])["payload"]["assessment"]
            require(trial["accepted"] == assessment["accepted"], "Recorded acceptance differs")
            require(assessment["accepted"] == (assessment["Armijo_margin_before_combination_guard"] >
                                              assessment["Armijo_combination_allowance"]),
                    "Saved Armijo decision differs")
            trials.append({"path": relative, "round": trial["round"], "alpha": trial["alpha"],
                           "accepted": trial["accepted"], "assessment": assessment})
        require(sum(row["accepted"] for row in trials) == 7, "Accepted trial count differs")
        proposals = []
        for relative in result["proposal_records"]:
            item = read(attempt / relative)
            proposal = read(attempt / item["worker_result"]["path"])["payload"]["proposal"]
            proposals.append({"path": relative, "round": item["round"],
                              "inner_solver_status": proposal["inner_solver_status"],
                              "KKT": proposal["KKT"], "counts": item["counts"]})
        pending = read(attempt / "calls/call030_assess/output/result.json")["payload"]["assessment"]
        require(pending["accepted"] is False and pending["alpha"] == .25,
                "Unexpected unrecorded assessment")
        for path, expected in bindings.items():
            require(identity(path) == expected, "Partial reporting input changed: " + path)
        budget()
        gate_passed = True

        # First permitted historical/reference/truth access, after the explicit failed-run gate.
        reference_spec = plan["reference_after_gate"]
        reference_path = ROOT / reference_spec["path"]
        require(str(reference_path.resolve()) not in bindings, "Historical reference was an inference input")
        reference_id = bind(reference_path, reference_spec)
        activity["previous_summary_numeric_reads"] += 1
        previous = read(reference_path)
        require(previous["status"] == "completed" and previous["all_bound_inputs_unchanged"] is True,
                "Preceding saved report is not valid")
        truth = previous["truth"]
        require(truth["next_index"] == 252000 and truth["decoded_records"] == 1,
                "Wrong saved endpoint truth")
        activity["saved_truth_records_reused"] += 1
        reference = previous["arms"]["replacement"]
        for point in generations:
            point["point_errors"] = helper.point_errors(point, truth)
        initial, final = generations[0], generations[-1]
        summary = {
            "schema": "mumble_anchor_failed_run_report_v1", "status": "completed_partial_failure_analysis",
            "inference_status": "failed", "partial_evidence": True,
            "source_revision": result["source_revision"], "inference_plan_sha256": result["plan_sha256"],
            "failure_reporting_plan_sha256": PLAN_SHA, "inference_stop_reason": result["stop_reason"],
            "inference_errors": result["errors"], "inference_counts": result["counts"],
            "original_integrity_failure": mismatches, "separate_byte_exact_recovery": recovery_id,
            "failure_diagnostic": diagnostic_id, "capture_loss_cause": "Unattributed",
            "initial": initial, "final_accepted": final, "accepted_generations": generations,
            "accepted_replacements": 7,
            "computed_initial_minus_final_common_objective": math.fsum((initial["computed_common_objective"], -final["computed_common_objective"])),
            "recorded_trials": trials, "proposals": proposals,
            "unrecorded_last_assessment": {"worker_result": "calls/call030_assess/output/result.json",
                                          "assessment": pending, "installed": False,
                                          "included_in_parent_trial_count": False},
            "post_run_reference": {"summary": reference_id, "Q_Ah": reference["endpoint_Q_Ah"],
                "endpoint_SOC": reference["endpoint_SOC"],
                "computed_common_objective": reference["computed_common_objective_without_support_normalizer"],
                "computed_final_minus_reference_objective": math.fsum((final["computed_common_objective"], -reference["computed_common_objective_without_support_normalizer"])),
                "scope": "Saved supplied-anchor feasible point, opened only after partial-evidence review; not an optimum or initialization."},
            "truth": {"capacity_Ah": truth["capacity_Ah"], "SOC": truth["SOC"],
                "next_index": truth["next_index"], "record_sha256": truth["record_sha256"],
                "original_source_sha256": truth["source_sha256"], "provenance": reference_id,
                "timing": "Saved truth reused only after independent accepted-prefix review and failed-manifest checks; no raw truth file opened."},
            "resources": {"CPU_total_s": outer["process"]["CPU_total_s"],
                "active_process_wall_s": outer["process"]["wall_s_through_wait4"],
                "maximum_wait4_peak_RSS_bytes": outer["process"]["peak_RSS_bytes"],
                "closed_runtime_output_bytes": outer["all_closed_output_bytes"],
                "scope": "Original failed invocation including waited descendants; reporting/recovery separate."},
            "storage": {"C_fixed_workspace_bytes": 10680, "C_main_frame_bytes": 11072,
                "workspace_inside_main_frame": True, "external_prefix_bytes": 8064000,
                "complete_M23_resources_qualified": False},
            "limitations": ["Original finite invocation remains failed; capture recovery does not change its stop or status.",
                "Seven accepted steps are verified partial evidence, not a completed refinement or nonlinear stationarity certificate.",
                "Inner quadratic KKT status and nonlinear convergence are separate.",
                "No posterior intervals, calibrated coverage, global MAP or firmware qualification."],
            "coverage_validated": False, "candidate_promoted": False, "reporting_activity": activity,
        }
        for path, expected in bindings.items():
            require(identity(path) == expected, "Input changed during partial reporting: " + path)
        budget()
        summary["all_reporting_inputs_unchanged"] = True
        summary_id = schema.write_json(output / "summary.json", summary, 1572864)
    except Exception as error:
        failure = {"type": type(error).__name__, "message": str(error)}
    changed = [path for path, expected in bindings.items() if identity(path) != expected]
    receipt = {"schema": "mumble_anchor_failed_run_report_v1",
        "status": "completed" if failure is None and not changed else "failed",
        "inference_status": "failed", "failed_manifest_and_accepted_prefix_validated_before_reference": gate_passed,
        "completed_inference_closure_validated": False, "exception": failure,
        "activity": activity, "inputs": bindings, "changed_inputs": changed, "summary": summary_id,
        "resources_before_receipt": {"wall_s": time.monotonic() - started,
            "CPU_s": time.process_time() - cpu_started,
            "own_peak_RSS_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024},
        "scope": "Separate post-failure reporting; no modification or retry of the original inference."}
    schema.close_receipt(output, receipt)
    require(receipt["closed_output_bytes_including_receipt"] <= 2097152, "Reporting output cap")
    print(json.dumps({"status": receipt["status"], "inference_status": "failed", "activity": activity,
                      "exception": failure, "output": str(output)}))
    return 0 if receipt["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
