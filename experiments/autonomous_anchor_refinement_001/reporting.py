#!/usr/bin/env python3
"""Report a closed anchor run using saved outputs only; no numerical imports."""
from __future__ import annotations

import argparse
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
PLAN = "plans/autonomous_anchor_refinement_001.json"
PLAN_SHA256 = "3f493d1067ea40798c8c91d5a0820fa89cef888d8d082774df2230679835be2b"
REFERENCE = "experiments/retained_likelihood_replacement_001/summary.json"
REFERENCE_ID = {"bytes": 426342, "sha256": "9f1686681584bfbfbdee8d47c6354f43aad90eff712b79c10f490682085ce067"}


def require(test, message):
    if not test:
        raise ValueError(message)


def basic_identity(path):
    data = Path(path).read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def load_schema(root):
    """Verify the shared closure source before importing its standard-library API."""
    executable = json.loads((root / EXP / "executable_receipt.json").read_bytes())
    require(executable["schema"] == "mumble_autonomous_anchor_executable_receipt_v1" and
            executable["status"] == "qualified_before_canonical_invocation", "Wrong executable receipt")
    path = root / EXP / "schema.py"
    expected = executable["source_identities"][EXP + "/schema.py"]
    require(basic_identity(path) == expected, "Shared closure schema changed")
    own_expected = executable["source_identities"][EXP + "/reporting.py"]
    require(basic_identity(Path(__file__)) == own_expected, "Reviewed reporting source changed")
    spec = importlib.util.spec_from_file_location("autonomous_anchor_reporting_schema", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, executable


def finite(value, label):
    require(type(value) in (int, float) and math.isfinite(value), "Nonfinite number: " + label)
    return float(value)


def pointer(value, location):
    require(location.startswith("/"), "Expected explicit JSON pointer")
    for part in location[1:].split("/"):
        value = value[part.replace("~1", "/").replace("~0", "~")]
    return value


def register(schema, path, bindings, expected=None):
    path = Path(path).resolve()
    actual = schema.identity(path)
    if expected is not None:
        require(actual == {k: expected[k] for k in ("bytes", "sha256")}, "Changed input: " + str(path))
    if str(path) in bindings:
        require(bindings[str(path)] == actual, "Conflicting input identity")
    bindings[str(path)] = actual
    return {"path": str(path), **actual}


def state_report(schema, attempt, state, bindings):
    audit_path = schema.safe(attempt, state["evaluator"]["path"])
    register(schema, audit_path, bindings, state["evaluator"])
    audit = schema.read_json(audit_path)
    prior_path = schema.safe(attempt, state["prior"]["path"])
    register(schema, prior_path, bindings, state["prior"])
    prior = pointer(schema.read_json(prior_path), state["prior"]["json_pointer"])
    require(prior["schema"] == "mumble_autonomous_anchor_prior_v1", "Wrong saved prior payload")
    require(audit["x"] == prior["x"] == state["x"], "Point, prior and model audit differ")
    require(len(state["x"]) == len(audit["gradient"]) == len(prior["gradient"]) == 16,
            "Saved joint dimension differs")
    require(audit["endpoint_x"] == state["endpoint_x"] and
            audit["endpoint_state"] == state["endpoint_state"], "Endpoint state mismatch")
    require(audit["cost"] == state["likelihood_cost"] and prior["cost"] == state["prior_kernel_cost"],
            "Saved cost mismatch")
    total = math.fsum((finite(audit["cost"], "likelihood"), finite(prior["cost"], "prior")))
    require(total == state["computed_common_objective"], "Common objective mismatch")
    gradient = [math.fsum((finite(a, "likelihood gradient"), finite(b, "prior gradient")))
                for a, b in zip(audit["gradient"], prior["gradient"])]
    Q = finite(state["endpoint_state"][5], "capacity")
    SOC = finite(state["endpoint_state"][11], "SOC")
    require(Q > 0. and 0. <= SOC <= 1., "Invalid saved endpoint")
    return {
        "generation": state["generation"], "x": state["x"],
        "Q_Ah": Q, "endpoint_SOC": SOC,
        "likelihood_cost": state["likelihood_cost"], "prior_kernel_cost": state["prior_kernel_cost"],
        "computed_common_objective": total,
        "saved_audit_plus_prior_gradient_x": gradient,
        "nonlinear_stationarity": "Not established. This is the sum of saved computed derivatives, not a new optimization or KKT certificate.",
        "evaluator": state["evaluator"], "prior": state["prior"], "ownership": state["ownership"],
    }


def point_errors(point, truth):
    q_error = math.fsum((point["Q_Ah"], -truth["capacity_Ah"]))
    z_error = math.fsum((point["endpoint_SOC"], -truth["SOC"]))
    return {"Q_error_Ah": q_error, "Q_error_percent": 100. * q_error / truth["capacity_Ah"],
            "SOC_error_fraction": z_error, "SOC_error_percentage_points": 100. * z_error,
            "scope": "One post-inference point comparison with a previously verified saved truth record; no interval/coverage test."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    schema, executable = load_schema(root)
    area = schema.safe(root, EXP)
    output = area / "reporting001"
    schema.reserve_directory(output)
    start_wall, start_cpu = time.monotonic(), time.process_time()
    bindings = {}
    activity = {"model_calls": 0, "optimizer_calls": 0, "prior_function_evaluations": 0,
                "observation_numeric_decodes": 0, "raw_truth_file_opens": 0,
                "previous_summary_numeric_reads": 0, "saved_truth_records_reused": 0,
                "inference_outputs_modified": 0}
    closure_validated = False
    failure = None
    summary_id = None
    schema.write_json(output / "reservation.json", {
        "schema": "mumble_autonomous_anchor_reporting_v1", "command": [sys.executable, *sys.argv],
        "reporter": register(schema, Path(__file__), bindings),
        "shared_schema": register(schema, area / "schema.py", bindings),
        "purpose": "Read-only post-closure reporting; only afterward reuse the pinned preceding summary as reference/truth provenance.",
    })
    try:
        plan_path = root / PLAN
        require(schema.identity(plan_path)["sha256"] == PLAN_SHA256, "Frozen plan changed")
        register(schema, plan_path, bindings)
        register(schema, area / "executable_receipt.json", bindings)
        closed = schema.validate_closed_run(root)
        result, run, outer = closed["result"], closed["receipt"], closed["outer_receipt"]
        require(result["source_revision"] == executable["source_revision"] and
                result["plan_sha256"] == PLAN_SHA256, "Closed inference has different source/plan")
        attempt = area / "attempt001"
        for directory in (attempt, area / "execution_process"):
            for relative, expected in schema.manifest(directory).items():
                register(schema, schema.safe(directory, relative), bindings, expected)
        for collection in (run["source_bindings"], run["input_bindings"], outer["source_bindings"]):
            rows = collection.values() if isinstance(collection, dict) else collection
            for row in rows:
                register(schema, row["path"], bindings, row)
        require(str((root / REFERENCE).resolve()) not in bindings,
                "Previous fitted summary was an inference input")
        initial = state_report(schema, attempt, result["initial"], bindings)
        final = state_report(schema, attempt, result["final"], bindings)
        expected_ownership = {"source_id": "f0bd54ce53f1944d4f17070b6380dc8317ae895f2fd1628198a1c5408a67f79c",
                              "source_interval": [0, 252000], "cursor": 252000,
                              "prior_copies": 1, "active_likelihood_blocks": 1}
        require(initial["ownership"] == final["ownership"] == expected_ownership,
                "Common prior/block/source ownership changed")
        require(initial["generation"] == 0 and
                final["generation"] == len(result["generation_records"]) - 1,
                "Generation count mismatch")
        records = {}
        for kind in ("proposal_records", "trial_records", "generation_records"):
            records[kind] = []
            for relative in result[kind]:
                path = schema.safe(attempt, relative)
                register(schema, path, bindings, run["files"][relative])
                records[kind].append({"path": relative, "record": schema.read_json(path)})
        closure_validated = True

        # This is the first possible access to fitted reference/truth values.
        activity["previous_summary_numeric_reads"] += 1
        reference_path = schema.safe(root, REFERENCE)
        reference_id = register(schema, reference_path, bindings, REFERENCE_ID)
        previous = schema.read_json(reference_path)
        require(previous["status"] == "completed" and previous["all_bound_inputs_unchanged"] is True,
                "Previous source-bound report was not completed")
        truth = previous["truth"]
        require(truth["next_index"] == 252000 and truth["decoded_records"] == 1 and
                finite(truth["capacity_Ah"], "saved truth capacity") > 0. and
                0. <= finite(truth["SOC"], "saved truth SOC") <= 1., "Wrong saved endpoint truth record")
        activity["saved_truth_records_reused"] += 1
        reference = previous["arms"]["replacement"]
        initial["point_errors"] = point_errors(initial, truth)
        final["point_errors"] = point_errors(final, truth)
        summary = {
            "schema": "mumble_autonomous_anchor_reporting_v1", "status": "completed",
            "source_revision": result["source_revision"], "plan_sha256": PLAN_SHA256,
            "inference_stop_reason": result["stop_reason"], "inference_counts": result["counts"],
            "initial": initial, "final": final,
            "computed_initial_minus_final_common_objective": math.fsum((initial["computed_common_objective"], -final["computed_common_objective"])),
            "accepted_replacements": final["generation"],
            "sequence": records,
            "post_run_reference": {
                "summary": reference_id,
                "kind": "Completed supplied-anchor feasible point under the same reference prior; not a nonlinear optimum or inference target.",
                "Q_Ah": reference["endpoint_Q_Ah"], "endpoint_SOC": reference["endpoint_SOC"],
                "computed_common_objective": reference["computed_common_objective_without_support_normalizer"],
                "computed_final_minus_reference_objective": math.fsum((final["computed_common_objective"], -reference["computed_common_objective_without_support_normalizer"])),
                "gap_scope": "Post-run computed point contrast only; no exclusion, optimization or accuracy claim follows from a nonzero gap.",
            },
            "truth": {"capacity_Ah": truth["capacity_Ah"], "SOC": truth["SOC"],
                      "next_index": truth["next_index"], "record_sha256": truth["record_sha256"],
                      "original_source_sha256": truth["source_sha256"],
                      "provenance": reference_id, "timing": "Reused only after validating all new inference closure and ownership records; no raw truth file opened."},
            "resources": {"CPU_total_s": outer["process"]["CPU_total_s"],
                          "active_process_wall_s": outer["process"]["wall_s_through_wait4"],
                          "maximum_wait4_peak_RSS_bytes": outer["process"]["peak_RSS_bytes"],
                          "outer_own_peak_RSS_bytes": outer["outer_own_peak_RSS_bytes"],
                          "closed_runtime_output_bytes": outer["all_closed_output_bytes"],
                          "scope": "Whole supervised invocation including waited descendants; wall excludes preparation/review/reporting. RSS is high-water, not summed concurrent tree memory."},
            "storage": {"C_fixed_workspace_bytes": 10680, "C_main_frame_bytes": 11072,
                        "workspace_inside_main_frame": True, "external_prefix_bytes": 8064000,
                        "complete_M23_resources_qualified": False},
            "limitations": [
                "Finite local nonlinear refinement from one public initialization, not global mode discovery or MAP qualification.",
                "Inner quadratic KKT checks do not establish nonlinear stationarity of any accepted point.",
                "The proposal metric majorizes prior curvature only; it is not a likelihood fidelity bound or posterior precision.",
                "The run supplies no calibrated intervals, posterior moments or coverage test.",
                "Fixed-history host refinement and external evidence storage are not an autonomous constant-memory streaming implementation.",
            ],
            "coverage_validated": False, "candidate_promoted": False,
            "reporting_activity": activity,
        }
        for path, expected in bindings.items():
            require(schema.identity(path) == expected, "Input changed during report: " + path)
        summary["all_bound_inputs_unchanged"] = True
        summary_id = schema.write_json(output / "summary.json", summary, 2097152)
    except Exception as error:
        failure = {"type": type(error).__name__, "message": str(error)}
    changed = [path for path, expected in bindings.items() if schema.identity(path) != expected]
    receipt = {
        "schema": "mumble_autonomous_anchor_reporting_v1", "status": "completed" if failure is None and not changed else "failed",
        "closure_validated_before_reference": closure_validated, "exception": failure,
        "activity": activity, "inputs": bindings, "changed_inputs": changed, "summary": summary_id,
        "resources_before_receipt": {"wall_s": time.monotonic() - start_wall, "CPU_s": time.process_time() - start_cpu,
                                     "own_peak_RSS_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
                                     "scope": "Reporting only; final receipt encoding/fsync excluded."},
    }
    schema.close_receipt(output, receipt)
    print(json.dumps({"status": receipt["status"], "output": str(output), "activity": activity, "exception": failure}))
    return 0 if receipt["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
