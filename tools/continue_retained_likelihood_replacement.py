#!/usr/bin/env python3
"""Complete only the unused work after the preserved subnormal parity stop.

The original invocation, its sources and failed result remain immutable.
This separately frozen adaptation reuses two closed anchor blocks and permits
only the two original surrogate solves and two remaining model audit passes.
"""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import sys
import traceback

sys.dont_write_bytecode = True
import run_retained_likelihood_replacement as original

EXP = original.EXP
PLAN = "plans/retained_likelihood_replacement_continuation_001.json"
PLAN_SHA256 = "1fe5ac901630be7472794df9dc24783f84f16a95008864875ae7afda09e007fa"
REVIEW = EXP + "/continuation_review.json"
NEW_SOURCES = (PLAN, "tools/continue_retained_likelihood_replacement.py",
    "tools/execute_retained_likelihood_continuation_once.py", EXP + "/underflow_parity.py",
    EXP + "/qualification/underflow_parity_checks.json", EXP + "/continuation_qualification.py",
    EXP + "/qualification/continuation_checks.json", EXP + "/reporting_continuation.py",
    EXP + "/reporting.py", "src/scm_estimator.c", EXP + "/independent_parity_failure_review.json", REVIEW)
require = original.require
identity = original.digest
read_json = original.strict_json


def closed_manifest(directory, receipt):
    actual = original.directory_manifest(directory)
    require("receipt.json" in actual, "Original receipt absent")
    del actual["receipt.json"]
    require(actual == receipt["files"], "Original closed manifest changed")
    total = sum(row["bytes"] for row in actual.values()) + identity(directory / "receipt.json")["bytes"]
    require(total == receipt["closed_output_bytes_including_receipt"], "Original closed byte count differs")
    return total


class Continuation(original.Run):
    def __init__(self, args):
        super().__init__(args)
        self.previous_resources = None
        self.previous_output_bytes = 0
        self.original_attempt = None

    def usage(self):
        current = super().usage()
        previous = self.previous_resources or {}
        current["current_invocation_CPU_total_s"] = current["CPU_total_s"]
        current["current_invocation_wall_s_through_snapshot"] = current["wall_s_through_snapshot"]
        current["previous_whole_process_CPU_s"] = previous.get("CPU_total_s", 0.)
        current["previous_whole_process_wall_s"] = previous.get("wall_s_through_wait4", 0.)
        current["CPU_total_s"] += current["previous_whole_process_CPU_s"]
        current["wall_s_through_snapshot"] += current["previous_whole_process_wall_s"]
        current["scope"] = "Original plus current active process usage; source-review/publication gap excluded; final outer wait4 is authoritative"
        return current

    def check_budget(self):
        resources = super().check_budget()
        total = self.previous_output_bytes + sum(row["bytes"] for row in original.directory_manifest(self.output).values())
        require(total <= original.LIMITS["closed_output_bytes_max"], "Cumulative original plus continuation output cap")
        return resources

    def preflight(self):
        self.stage = "verify_preserved_failed_attempt_and_continuation_sources"
        plan_path = self.root / PLAN
        self.bind(self.sources, plan_path, {"sha256": PLAN_SHA256}, "continuation contract")
        plan = read_json(plan_path.read_bytes())
        require(plan["schema"] == "mumble_retained_likelihood_saved_block_continuation_contract_v1"
                and plan["status"] == "frozen_before_any_remaining_solver_or_model_call", "Wrong continuation contract")
        for rel, expected in plan["original_attempt"]["identities"].items():
            self.bind(self.inputs, self.root / rel, expected, "preserved " + rel)
        old_dir = self.root / EXP / "attempt001"
        old_result = read_json((old_dir / "result.json").read_bytes())
        old_receipt = read_json((old_dir / "receipt.json").read_bytes())
        outer_path = self.root / EXP / "execution_process/receipt.json"
        outer = read_json(outer_path.read_bytes())
        require(old_result["status"] == old_receipt["status"] == outer["status"] == "failed",
                "Original stop was not preserved")
        require(old_receipt["canonical_inference_closed"] and old_receipt["truth_reads"] == 0,
                "Original inference not closed without truth")
        require(len(old_result["errors"]) == 1 and old_result["errors"][0]["message"] ==
                "Historical free-fit reconstruction parity failed", "Unexpected original failure")
        counts = old_receipt["counts"]
        for key, value in {"supervisor_invocations": 1, "model_passes_started": 2, "model_passes_completed": 2,
                           "model_steps_reported": 504000, "model_step_count_complete": True,
                           "solver_invocations_reserved": 0, "solver_started_markers": 0,
                           "solver_results_saved": 0, "learner_calls": 0, "fitter_calls": 0,
                           "truth_reads": 0, "retries": 0}.items():
            require(counts[key] == value, "Original budget accounting differs: " + key)
        require(not (old_dir / "solves").exists(), "Original solver may have started")
        require(outer["process"]["exit_code"] == 1 and not outer["process"]["resource_violations"]
                and not outer["process"]["output_truncated"] and outer["canonical_process_finished"]
                and outer["canonical_supervisor_invocations"] == 1 and outer["retries"] == 0,
                "Original outer closure is not the diagnosed parity stop")
        require(outer["inner_receipt"] == identity(old_dir / "receipt.json")
                and outer["inner_result"] == identity(old_dir / "result.json"), "Original outer identities differ")
        closed_manifest(old_dir, old_receipt)
        for name in ("stdout", "stderr"):
            path = self.root / EXP / "execution_process" / (name + (".json" if name == "stdout" else ".txt"))
            self.bind(self.inputs, path, outer[name], "original outer " + name)
        for rel, expected in old_receipt["files"].items():
            self.bind(self.inputs, old_dir / rel, expected, "original closed output " + rel)
        for group in ("source_bindings", "input_bindings", "generated_input_and_solver_bindings"):
            for row in old_receipt[group]:
                self.bind(self.inputs, Path(row["path"]), row, "original binding " + row["label"])
        self.previous_output_bytes = sum(p.stat().st_size for d in (old_dir, outer_path.parent) for p in d.rglob("*") if p.is_file())
        require(self.previous_output_bytes == outer["canonical_closed_output_bytes_including_outer_receipt"],
                "Original combined output bytes differ")
        self.previous_resources = outer["process"]
        self.original_attempt = {"directory": str(old_dir.relative_to(self.root)),
            "result": {"path": str((old_dir / "result.json").relative_to(self.root)), **identity(old_dir / "result.json")},
            "receipt": {"path": str((old_dir / "receipt.json").relative_to(self.root)), **identity(old_dir / "receipt.json")},
            "parity": {"path": str((old_dir / "historical_parity.json").relative_to(self.root)), **identity(old_dir / "historical_parity.json")},
            "outer_receipt": {"path": str(outer_path.relative_to(self.root)), **identity(outer_path)},
            "counts": counts, "source_revision": old_result["source_revision"], "status": "failed",
            "original_failure_reclassified": False, "closed_output_bytes": self.previous_output_bytes}
        executable_path = original.common.argument_path(self.root, Path(self.args.executable_receipt))
        executable = read_json(executable_path.read_bytes())
        require(executable["continuation_plan_sha256"] == PLAN_SHA256, "Executable covers another continuation")
        for rel in NEW_SOURCES:
            expected = executable["continuation_source_identities"][rel]
            self.bind(self.sources, self.root / rel, expected, rel)
            require(original.sha(original.common.git_bytes(self.root, self.args.source_revision, rel)) == expected["sha256"],
                    "Continuation source commit differs: " + rel)
        review = read_json((self.root / REVIEW).read_bytes())
        require(review["status"] == "passed" and review["continuation_invocations_before_review"] == 0
                and review["continuation_plan_sha256"] == PLAN_SHA256, "Continuation review missing or stale")
        for rel in NEW_SOURCES:
            if rel != REVIEW:
                require(review["reviewed_source_sha256"][rel] == executable["continuation_source_identities"][rel]["sha256"],
                        "Continuation review source mismatch")
        # The original qualified preflight revalidates the scientific inputs and
        # fixed warm start; it performs an input-only scan, never a model pass.
        super().preflight()
        spec = importlib.util.spec_from_file_location("qualified_underflow_parity", self.root / EXP / "underflow_parity.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        original_parity = read_json((old_dir / "historical_parity.json").read_bytes())
        new_payload = read_json((old_dir / "replacement_anchor/stdout.json").read_bytes())
        diagnosis = module.diagnose(self.saved_free, new_payload, original_parity)
        self.write("underflow_diagnostic.json", diagnosis)
        require(diagnosis["corrected_gate_passed"] and not diagnosis["original_gate_passed"],
                "Qualified underflow diagnostic did not admit the saved blocks")
        reuse = []
        for label, x in (("old_anchor", self.old_x), ("replacement_anchor", self.new_x)):
            source = old_dir / label / "stdout.json"
            target_dir = self.output / label
            target_dir.mkdir(exist_ok=False)
            target = target_dir / "stdout.json"
            data = source.read_bytes()
            with target.open("xb") as stream:
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
            require(identity(target) == identity(source), "Copied anchor differs")
            payload = read_json(data)
            validation = original.validate_evaluator(payload, x, self.prefix)
            self.payloads[label] = payload
            self.bind(self.generated, target, identity(source), "reused anchor " + label)
            row = {"id": label, "path": label + "/stdout.json", "reused": True,
                   "origin": {"path": str(source.relative_to(self.root)), **identity(source)}, "validation": validation}
            self.passes.append(row); reuse.append(row)
        self.write("anchor_reuse.json", {"rows": reuse, "new_model_calls": 0,
            "semantics": "Exact copies of the two original closed blocks; alternatives owning the same prefix, not independent observations"})
        self.recheck()

    def child(self, name, command, kind):
        if kind == "model":
            require(self.counts["model_passes_started"] < 2, "Only two remaining audit passes are authorized")
        return super().child(name, command, kind)

    def cumulative_counts(self):
        original_counts = self.original_attempt["counts"] if self.original_attempt else {}
        return {"original_counts_verified": self.original_attempt is not None,
                "supervisor_invocations": 1 + original_counts.get("supervisor_invocations", 0),
                "model_passes_started": self.counts["model_passes_started"] + original_counts.get("model_passes_started", 0),
                "model_passes_completed": self.counts["model_passes_completed"] + original_counts.get("model_passes_completed", 0),
                "model_steps_reported": self.counts["model_steps_reported"] + original_counts.get("model_steps_reported", 0),
                "model_step_count_complete": self.original_attempt is not None and self.counts["model_step_count_complete"]
                                             and original_counts.get("model_step_count_complete", False),
                "solver_invocations_reserved": self.counts["solver_invocations_reserved"],
                "solver_started_markers": self.counts["solver_started_markers"],
                "solver_results_saved": self.counts["solver_results_saved"], "repeated_anchor_passes": 0,
                "learner_calls": 0, "fitter_calls": 0, "truth_reads": 0, "further_retries": 0}

    def execute(self):
        require(self.output == self.root / EXP / "continuation001", "Only the exclusive continuation001 destination is admitted")
        self.output.mkdir(exist_ok=False)
        result = {"schema": "mumble_retained_likelihood_replacement_result_v1", "status": "failed", "continuation": True,
                  "source_revision": self.args.source_revision, "plan_sha256": original.PLAN_SHA256,
                  "continuation_plan_sha256": PLAN_SHA256, "passes": self.passes, "candidates": {}, "errors": [],
                  "coverage_validated": False, "candidate_promoted": False, "truth_reads": 0}
        try:
            self.write("started.json", {"schema": "mumble_retained_replacement_continuation_started_v1",
                "utc": datetime.now(timezone.utc).isoformat(), "argv": vars(self.args), "pid": os.getpid(),
                "source": identity(Path(__file__)), "additional_model_passes_max": 2,
                "additional_surrogate_solves_max": 2, "further_retries": 0, "truth_reads": 0})
            self.preflight()
            result.update(source_id=self.plan["inputs"]["source_id"], prefix_records=self.prefix["prefix_records"],
                          input_summary="prefix_input.json", anchors="anchors.json", original_attempt=self.original_attempt)
            pair = self.solve()
            result["solver"] = {"output_dir": "solves", "pair_path": "solves/pair.json", "status": pair["status"],
                                "started_count": 2, "completed_count": 2, "policy_sha256": pair["policy"]["policy_sha256"]}
            for name in ("frozen", "replacement"):
                row = pair[name]
                result["candidates"][name] = {"x": row["candidate_x"], "solver_path": f"solves/{name}.result.json",
                    "audit_path": f"{name}_audit/stdout.json", "prior_kernel_cost": row["prior_kernel_cost"], "solver_status": row["status"]}
                x_path = self.x_file(name + "_candidate_x.txt", row["candidate_x"])
                self.evaluate(name + "_audit", row["candidate_x"], x_path)
            comparison = original.compare_candidates(self.payloads["frozen_audit"], self.payloads["replacement_audit"],
                pair["frozen"]["prior_kernel_cost"], pair["replacement"]["prior_kernel_cost"], self.prefix["prefix_records"])
            self.recheck()
            accepted = comparison["decision"] == "accepted_feasible_point_improvement"
            ownership = {"source_id": self.plan["inputs"]["source_id"], "observation_indices": [0, self.prefix["prefix_records"]],
                         "interval_convention": "half-open", "cursor": self.prefix["prefix_records"],
                         "prior": identity(self.output / "solves/prior.json"), "prior_copies": 1, "active_likelihood_blocks": 1}
            before = {**ownership, "generation": 0, "block": "old_anchor/stdout.json", "candidate": "frozen"}
            after = {**ownership, "generation": int(accepted), "block": "replacement_anchor/stdout.json" if accepted else before["block"],
                     "candidate": "replacement" if accepted else "frozen"}
            result.update(status="completed", comparison=comparison,
                transaction={"decision": comparison["decision"], "accepted": accepted, "before": before, "after": after,
                             "old_block_archived": accepted, "prior_unchanged": True, "cursor_unchanged": True,
                             "posterior_multiplied_into_replayed_evidence": False, "scope": "Host prototype transaction only"})
        except Exception as error:
            result["errors"].append({"stage": self.stage, "exception_type": type(error).__name__,
                                     "message": str(error), "traceback": traceback.format_exc()})
        result["counts"], result["cumulative_counts"] = dict(self.counts), self.cumulative_counts()
        result["original_attempt"] = self.original_attempt
        self.stage = "close_continuation"
        try:
            self.check_budget()
            require(self.previous_output_bytes + sum(v["bytes"] for v in original.directory_manifest(self.output).values()) + 262144
                    <= original.LIMITS["closed_output_bytes_max"], "Insufficient cumulative budget for bounded closure")
        except Exception as error:
            result["status"] = "failed"
            result["errors"].append({"stage": self.stage, "message": str(error)})
            if "transaction" in result:
                result["transaction"].update(accepted=False, decision="retained_resource_failure",
                    after=result["transaction"]["before"], old_block_archived=False)
        self.write("result.json", result, emergency_closure=result["status"] != "completed")
        files = original.directory_manifest(self.output)
        receipt = {"schema": "mumble_retained_likelihood_replacement_receipt_v1", "status": result["status"],
                   "continuation": True, "canonical_inference_closed": True, "source_revision": self.args.source_revision,
                   "plan_sha256": original.PLAN_SHA256, "continuation_plan_sha256": PLAN_SHA256,
                   "original_attempt": self.original_attempt, "counts": self.counts, "cumulative_counts": self.cumulative_counts(),
                   "truth_reads": 0, "source_bindings": list(self.sources.values()), "input_bindings": list(self.inputs.values()),
                   "generated_input_and_solver_bindings": list(self.generated.values()), "children": self.children,
                   "files": files, "resources": self.usage(), "limits": original.LIMITS,
                   "closed_output_bytes_including_receipt": 0, "previous_closed_output_bytes": self.previous_output_bytes,
                   "failure_only_emergency_closure": result["status"] != "completed", "further_retries": 0,
                   "closure": "All remaining inference children waited. Original failure remains preserved. Outer cumulative closure is authoritative before reporting."}
        other_bytes = sum(row["bytes"] for row in files.values())
        for _ in range(8):
            total = other_bytes + len((json.dumps(receipt, indent=2, allow_nan=False) + "\n").encode())
            if receipt["closed_output_bytes_including_receipt"] == total:
                break
            receipt["closed_output_bytes_including_receipt"] = total
        require(result["status"] != "completed" or total + self.previous_output_bytes <= original.LIMITS["closed_output_bytes_max"],
                "Successful cumulative closure exceeds output cap")
        self.write("receipt.json", receipt, emergency_closure=result["status"] != "completed")
        return {"status": result["status"], "decision": result.get("transaction", {}).get("decision"),
                "receipt": str(self.output / "receipt.json"), "counts": self.counts,
                "cumulative_counts": self.cumulative_counts(), "errors": result["errors"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--executable-receipt", default=EXP + "/continuation_executable_receipt.json")
    parser.add_argument("--output-dir", default=EXP + "/continuation001")
    args = parser.parse_args()
    try:
        result = Continuation(args).execute()
    except Exception as error:
        result = {"status": "failed_before_receipt", "exception_type": type(error).__name__, "message": str(error), "no_retry": True}
    print(json.dumps(result, allow_nan=False))
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
