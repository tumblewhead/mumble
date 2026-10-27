#!/usr/bin/env python3
"""Finite fabricated child callbacks for the complete parent lifecycle.

No numerical module, model binary, archive, historical result or truth is used.
Returned likelihood/prior/solver values and resource records are explicit stubs;
this checks orchestration, persistence, counting and closure, not their algebra.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import resource
import sys
import tempfile
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
spec = importlib.util.spec_from_file_location("autonomous_parent_fixture", ROOT / "tools/run_autonomous_anchor_refinement.py")
parent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parent)
s = parent.schema


def prior(x):
    return {"schema": "mumble_autonomous_anchor_prior_v1", "x": list(x), "cost": 0.,
            "gradient": [0.] * 16, "hessian_lower": [0.] * 136, "responsibilities": [.5, .5],
            "reference_math_sha256": "870583ec263f4bf4e69b80aa9fc06402336deb606aeaa88533389ddce715261b",
            "support_normalizer_included": False, "prior_evaluations": 1}


class FabricatedRun(parent.Run):
    def __init__(self, directory, mode):
        args = argparse.Namespace(root=str(ROOT), output_dir=str(directory), source_revision="0" * 40,
                                  evidence_root="unused", executable_receipt="unused")
        super().__init__(args)
        self.mode = mode
        self.supervise = self.stub_child
        self.stub_calls = []
        self.next_proposal = 0
        self.accepted_trial_block = None
        self.reused_block_observed = False
        self.reservation_checks = 0

    def preflight(self):
        self.plan = {"input": {"source_id": "fabricated_orchestration_only"}}
        self.public_x = [0.] * 16
        self.public_x[11] = .5
        self.prior_config = {"public_unsplit_mean": self.public_x, "public_unsplit_sd": [1.] * 16,
                             "entering_lower": [-10.] * 16, "entering_upper": [10.] * 16}
        self.policy = {"fixture": True}
        self.prefix = {"prefix_records": s.PREFIX, "charge_Ah": 0., "charge_min_Ah": 0.,
                       "charge_max_Ah": 0., "elapsed_physical_s": 0.,
                       "last_record": {"index": s.PREFIX - 1, "dt_s": 0., "current_A": 0., "observed_voltage_V": 0.}}
        self.prefix_geometry = {"records": s.PREFIX, "charge_min_Ah": 0., "charge_max_Ah": 0.}
        self.binary = Path("/fabricated/nonexistent_model_never_executed")
        self.observations = Path("/fabricated/nonexistent_archive_never_opened")
        self.python = Path(sys.executable).resolve()
        self.write("public_initialization.json", {"x": self.public_x, "fixture": True})
        self.write("prefix_input.json", self.prefix)

    def model_payload(self, x):
        cost = 100. - self.counts["model_passes_reserved"]
        physical = list(x)
        physical[:6] = [1.] * 6
        return {
            "schema": parent.helpers.EVALUATOR_SCHEMA, "status": "ok", "dimension": 16,
            "coordinate_names": parent.helpers.COORDINATES, "sigma_V": .001,
            "gram_layout": parent.helpers.GRAM_LAYOUT, "x": x, "cost": cost,
            "gradient": [0.] * 16, "gram": [0.] * 136,
            "endpoint_x": list(x), "endpoint_state": physical,
            "endpoint_derivative": [0.] * 256, "endpoint_physical_derivative": [0.] * 256,
            "absolute_summand_scales": {"cost": cost, "gradient": [0.] * 16, "gram": [0.] * 136},
            "prefix_requested": s.PREFIX, "records_read": s.PREFIX, "records_accumulated": s.PREFIX,
            "input_bytes_read": 32 * s.PREFIX, "model_init_calls": 1,
            "model_step_calls": s.PREFIX, "model_predict_calls": s.PREFIX,
            "source_generations": 0, "learner_ingests": 0, "fit_calls": 0, "truth_reads": 0,
            "charge_extrema_include_initial_zero": True, "charge_Ah": 0., "charge_min_Ah": 0.,
            "charge_max_Ah": 0., "elapsed_physical_s": 0., "last_record": self.prefix["last_record"],
            "storage": {"workspace_sizeof_bytes": 10680}, "fabricated": True,
        }

    def stub_child(self, command, out, bounds):
        reservation = s.read_json(out / "reservation.json")
        action = reservation["action"]
        assert reservation["command"] == command
        assert reservation["counts_after_reservation"] == self.counts
        counter = {"model": "model_passes_reserved", "propose": "proposal_calls_reserved",
                   "prior": "prior_actions_reserved", "assess": "assess_actions_reserved"}[action]
        assert reservation["counts_after_reservation"][counter] == reservation["counts_before"][counter] + 1
        self.reservation_checks += 1
        self.stub_calls.append(action)
        code = 0
        if action == "model":
            x = [float(value) for value in (out / "x.txt").read_text().split()]
            payload = self.model_payload(x)
            if self.counts["model_passes_reserved"] == 2 and self.mode in ("partial_model", "unknown_model"):
                code = 1
                payload = {"schema": parent.helpers.EVALUATOR_SCHEMA, "status": "error", "model_step_calls": 5}
                raw = b"" if self.mode == "unknown_model" else s.encode_json(payload)
            else:
                raw = s.encode_json(payload)
        else:
            request = s.read_json(out / "request.json")
            assert request["action"] == action and request["schema"] == "mumble_autonomous_anchor_worker_request_v1"
            worker_out = out / "output"
            s.reserve_directory(worker_out)
            counts = {"prior_evaluations": 0, "prior_evaluations_completed": 0,
                      "optimizer_calls_started": 0, "optimizer_calls_completed": 0,
                      "combined_evaluations": 0, "optimizer_evaluation_count_complete": True}
            if action == "prior":
                payload = {"prior": prior(request["x"])}
                counts["prior_evaluations"] = counts["prior_evaluations_completed"] = 1
            elif action == "propose":
                self.next_proposal += 1
                block = request["block"]
                if self.next_proposal == 2 and self.accepted_trial_block is not None:
                    self.reused_block_observed = block == self.accepted_trial_block
                x = list(block["x"])
                x[0] += .125
                admitted = not (self.mode in ("full_reject_half_accept", "accepted_reuse", "no_direction") and
                                (self.next_proposal >= 2 or self.mode == "no_direction"))
                payload = {"proposal": {"candidate_x": x, "anchor_x": block["x"],
                           "direction_admitted": admitted, "resolved_descent": admitted,
                           "resolved_model_decrease": admitted, "step_box_feasible": True,
                           "status": "direction_admitted" if admitted else "unresolved_no_admissible_direction"}}
                if self.mode == "metric_failure":
                    payload["proposal"].update(status="metric_not_positive_definite", direction_admitted=False)
                else:
                    counts.update(optimizer_calls_started=1, optimizer_calls_completed=1, combined_evaluations=3)
                    s.write_json(worker_out / "solve_started.json", {"fixture": True, "before_fake_optimizer": True})
                if self.mode == "partial_proposal":
                    code = 1
                    counts.update(optimizer_calls_completed=0, combined_evaluations=None, optimizer_evaluation_count_complete=False)
                    payload = None
            else:
                alpha = request["alpha"]
                accepted = (self.mode in ("accepted_reuse", "round_cap") or
                            (self.mode == "full_reject_half_accept" and alpha == .5) or
                            (self.mode == "pass_cap" and alpha == s.FRACTIONS[-1]))
                if accepted:
                    self.accepted_trial_block = request["trial_block"]
                payload = {"assessment": {"accepted": accepted, "trial_prior": prior(request["trial_block"]["x"]),
                           "status": "accepted" if accepted else "rejected"}}
                counts["prior_evaluations"] = counts["prior_evaluations_completed"] = 1
            result = {"schema": "mumble_autonomous_anchor_worker_result_v1", "status": "failed" if code else "completed",
                      "action": action, "payload": payload, "counts": counts, "fabricated": True}
            if action == "prior" and self.mode == "unknown_prior":
                code, raw = 1, b""
            else:
                s.write_json(worker_out / "result.json", result)
                raw = s.encode_json({"schema": result["schema"], "status": result["status"], "action": action,
                                     "payload_path": "result.json", "counts": counts})
        for name, data in ((s.CAPTURE_ROLES["stdout"], raw), (s.CAPTURE_ROLES["stderr"], b"")):
            with (out / name).open("xb") as stream:
                stream.write(data)
        return {"child_launched": True, "pid": 0, "command": command, "exit_code": code,
                "wall_s_through_wait4": .001, "CPU_user_s": .001, "CPU_system_s": 0., "CPU_total_s": .001,
                "peak_RSS_bytes": 1048576, "resource_violations": [], "output_truncated": False,
                "limits": bounds, "fabricated_resource_record_no_process_launched": True,
                "stdout_stderr_bytes_written": {"stdout": len(raw), "stderr": 0},
                "stdout_stderr_bytes_observed": {"stdout": len(raw), "stderr": 0}}


def main():
    output = ROOT / parent.EXP / "qualification/orchestration.json"
    if output.exists():
        raise ValueError("Qualification already recorded; no overwrite")
    started = time.monotonic()
    records = []
    source_paths = [Path(__file__).resolve(), ROOT / "tools/run_autonomous_anchor_refinement.py",
                    ROOT / "tools/execute_autonomous_anchor_once.py", ROOT / parent.EXP / "schema.py"]
    before = {str(path.relative_to(ROOT)): s.identity(path) for path in source_paths}
    with tempfile.TemporaryDirectory(prefix="mumble_autonomous_orchestration_") as temporary:
        temporary = Path(temporary)
        expected = {
            "full_reject_half_accept": ("completed", "no_admissible_direction", 3, 2, 1),
            "accepted_reuse": ("completed", "no_admissible_direction", 2, 2, 1),
            "all_reject": ("completed", "all_trial_fractions_rejected", 9, 1, 0),
            "no_direction": ("completed", "no_admissible_direction", 1, 1, 0),
            "pass_cap": ("completed", "model_pass_budget_exhausted", 33, 4, 4),
            "round_cap": ("completed", "proposal_round_budget_exhausted", 17, 16, 16),
            "metric_failure": ("failed", "numerical_input_or_resource_failure", 1, 1, 0),
            "partial_model": ("failed", "numerical_input_or_resource_failure", 2, 1, 0),
            "unknown_model": ("failed", "numerical_input_or_resource_failure", 2, 1, 0),
            "partial_proposal": ("failed", "numerical_input_or_resource_failure", 1, 1, 0),
            "unknown_prior": ("failed", "numerical_input_or_resource_failure", 1, 0, 0),
        }
        for mode, want in expected.items():
            run = FabricatedRun(temporary / mode, mode)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = run.run()
            result = s.read_json(run.output / "result.json")
            receipt = s.read_json(run.output / "receipt.json")
            s.validate_manifest(run.output, receipt)
            actual = (result["status"], result["stop_reason"], run.counts["model_passes_reserved"],
                      run.counts["proposal_calls_reserved"], run.counts["accepted_steps"])
            assert actual == want, (mode, actual, want)
            assert code == (0 if want[0] == "completed" else 1)
            assert run.reservation_checks == len(run.children) == len(run.stub_calls)
            assert all((run.output / row["directory"] / "raw_probe.json").exists() and
                       (run.output / row["directory"] / "probe.stderr").exists() for row in run.children)
            if want[0] == "completed":
                reconstructed = s.validate_activity(run.output, receipt, result)
                assert reconstructed["prior_completed"] == reconstructed["model"]
            if mode in ("full_reject_half_accept", "accepted_reuse"):
                assert run.reused_block_observed
            if mode == "full_reject_half_accept":
                assert [s.read_json(run.output / path)["alpha"] for path in run.trial_records] == [1., .5]
            if mode == "partial_model":
                assert run.counts["model_steps_reported"] == s.PREFIX + 5 and run.counts["model_step_count_complete"]
                assert run.stub_calls[-1] == "model"
            if mode == "unknown_model":
                assert run.counts["model_steps_reported"] == s.PREFIX and not run.counts["model_step_count_complete"]
                assert len(receipt["unresolved_model_reservations"]) == 1
            if mode == "partial_proposal":
                assert not run.counts["worker_activity_complete"] and run.counts["optimizer_calls_started"] == 1
                assert run.counts["optimizer_calls_completed"] == 0 and len(receipt["unresolved_worker_reservations"]) == 1
            if mode == "unknown_prior":
                assert run.counts["external_prior_evaluations_reserved"] == run.counts["prior_actions_reserved"] == 1
                assert run.counts["external_prior_evaluations_started_reported"] == run.counts["external_prior_evaluations_completed"] == 0
                assert not run.counts["worker_activity_complete"] and len(receipt["unresolved_worker_reservations"]) == 1
            records.append({"case": mode, "passed": True, "status": result["status"],
                            "stop_reason": result["stop_reason"], "counts": result["counts"],
                            "durable_reservations_observed_before_callback": run.reservation_checks,
                            "accepted_audit_reuse_observed": run.reused_block_observed,
                            "closure_manifest_verified": True,
                            "raw_payload_path_relative_to_worker_output_exercised": True})
        run = FabricatedRun(temporary / "resource_cap", "all_reject")
        s.reserve_directory(run.output)
        s.reserve_directory(run.output / "calls")
        run.usage = lambda: {"CPU_total_s": 61., "wall_s": 0., "supervisor_peak_RSS_bytes": 1}
        try:
            run.child("model", lambda _: ["must_not_launch"])
        except ValueError as error:
            assert str(error) == "Cumulative CPU cap"
        else:
            raise AssertionError("Cumulative cap did not stop launch")
        assert run.stub_calls == [] and run.counts["model_passes_reserved"] == 0
        records.append({"case": "cumulative_CPU_cap_prevents_reservation_and_launch", "passed": True})
    after = {str(path.relative_to(ROOT)): s.identity(path) for path in source_paths}
    assert before == after
    assert "numpy" not in sys.modules and "scipy" not in sys.modules
    receipt = {
        "schema": "mumble_autonomous_anchor_orchestration_qualification_v1", "status": "passed",
        "command": [sys.executable, *sys.argv], "source_identities": before,
        "cases": records, "case_count": len(records), "sources_unchanged": before == after,
        "activity": {"canonical_model_calls": 0, "actual_model_calls": 0, "actual_optimizer_calls": 0,
                     "actual_prior_evaluations": 0, "canonical_observation_reads": 0,
                     "historical_candidate_reads": 0, "truth_reads": 0, "child_processes_launched": 0},
        "resources": {"wall_s_before_receipt": time.monotonic() - started,
                      "own_peak_RSS_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024},
        "limitations": "All scientific payloads, per-child counts and child resources are fabricated callbacks. This qualifies parent control flow, persistence, counter reconstruction and failure retention, not model/numerical accuracy. The existing wait4 supervisor is reused unchanged. Temporary case files are reproducible from this exact source; only this qualification receipt is retained.",
    }
    s.write_json(output, receipt, 1048576)
    print(json.dumps({"status": "passed", "case_count": len(records), "receipt": {"path": str(output), **s.identity(output)},
                      "activity": receipt["activity"]}))


if __name__ == "__main__":
    main()
