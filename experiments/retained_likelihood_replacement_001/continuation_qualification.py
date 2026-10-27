#!/usr/bin/env python3
"""Fabricated control-flow checks; no canonical evidence or numerical imports."""
import argparse
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import resource
import sys
import tempfile
import time
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import continue_retained_likelihood_replacement as continuation
import execute_retained_likelihood_continuation_once as outer


def main():
    output = ROOT / continuation.EXP / "qualification/continuation_checks.json"
    assert not output.exists(), "Qualification output already exists; no overwrite"
    start, cpu = time.monotonic(), time.process_time()
    paths = ["tools/continue_retained_likelihood_replacement.py", "tools/execute_retained_likelihood_continuation_once.py",
             "tools/run_retained_likelihood_replacement.py", continuation.EXP + "/continuation_qualification.py"]
    hashes = {path: continuation.identity(ROOT / path) for path in paths}
    checks, cases = [], {}

    def check(name, condition, detail=None):
        checks.append({"name": name, "passed": bool(condition), "detail": detail})
        if not condition:
            raise AssertionError(name)

    with tempfile.TemporaryDirectory(prefix="mumble_continuation_fabricated_") as temp:
        base = Path(temp)
        directory = base / "manifest"
        directory.mkdir()
        (directory / "sample.txt").write_text("fabricated closed content\n")
        files = {"sample.txt": continuation.identity(directory / "sample.txt")}
        receipt = {"files": files, "closed_output_bytes_including_receipt": 0}
        for _ in range(8):
            data = (json.dumps(receipt, indent=2) + "\n").encode()
            total = len(data) + files["sample.txt"]["bytes"]
            if receipt["closed_output_bytes_including_receipt"] == total:
                break
            receipt["closed_output_bytes_including_receipt"] = total
        (directory / "receipt.json").write_bytes(data)
        check("closed_manifest_exact", continuation.closed_manifest(directory, receipt) == total)
        (directory / "sample.txt").write_text("mutated\n")
        try:
            continuation.closed_manifest(directory, receipt)
        except continuation.original.common.ProbeError:
            check("closed_manifest_mutation_rejected", True)
        else:
            check("closed_manifest_mutation_rejected", False)

        source = base / "anchor.json"
        source.write_bytes(b'{"fabricated_anchor":true,"value":1.25}\n')
        target = base / "copy.json"
        target.write_bytes(source.read_bytes())
        check("anchor_copy_exact_identity", continuation.identity(target) == continuation.identity(source))
        check("source_anchor_preserved", source.read_bytes() == b'{"fabricated_anchor":true,"value":1.25}\n')

        prior_counts = {"supervisor_invocations": 1, "model_passes_started": 2, "model_passes_completed": 2,
                        "model_steps_reported": 504000, "model_step_count_complete": True,
                        "solver_invocations_reserved": 0, "solver_started_markers": 0, "solver_results_saved": 0}
        for case, fail_first_audit in (("complete", False), ("audit_failure", True)):
            root = base / case
            (root / continuation.EXP).mkdir(parents=True)
            args = argparse.Namespace(root=str(root), evidence_root=str(root / "fabricated_evidence"),
                source_revision="0" * 40, executable_receipt="fabricated", output_dir=continuation.EXP + "/continuation001")
            calls = []

            class FakeContinuation(continuation.Continuation):
                def preflight(self):
                    calls.append("reuse_two_closed_anchors")
                    self.original_attempt = {"status": "failed", "counts": dict(prior_counts), "fabricated": True}
                    self.previous_resources = {"CPU_total_s": 1., "wall_s_through_wait4": 1.5}
                    self.plan = {"inputs": {"source_id": "fabricated_source"}}
                    self.prefix = {"prefix_records": 252000}
                    self.passes.extend({"id": label, "reused": True, "fabricated": True}
                                       for label in ("old_anchor", "replacement_anchor"))

                def solve(self):
                    calls.append("one_worker_two_solves")
                    (self.output / "solves").mkdir()
                    self.write("solves/prior.json", {"fabricated": True})
                    self.counts.update(solver_invocations_reserved=2, solver_started_markers=2, solver_results_saved=2)
                    row = {"candidate_x": [0.] * 16, "prior_kernel_cost": 0., "status": "unresolved"}
                    return {"frozen": dict(row), "replacement": dict(row), "status": "unresolved", "policy": {"policy_sha256": "fixture"}}

                def evaluate(self, name, x, path):
                    calls.append(name)
                    self.counts["model_passes_started"] += 1
                    if fail_first_audit:
                        self.counts["model_step_count_complete"] = False
                        raise RuntimeError("fabricated first audit failure")
                    self.counts["model_passes_completed"] += 1
                    self.counts["model_steps_reported"] += 252000
                    payload = {"cost": 10. if name == "frozen_audit" else 1.,
                               "absolute_summand_scales": {"cost": 10. if name == "frozen_audit" else 1.}}
                    self.payloads[name] = payload
                    self.passes.append({"id": name, "reused": False, "fabricated": True})
                    return payload

            run = FakeContinuation(args)
            check(case + ":unknown_original_counts_not_complete", not run.cumulative_counts()["model_step_count_complete"])
            result = run.execute()
            receipt = continuation.read_json((run.output / "receipt.json").read_bytes())
            saved = continuation.read_json((run.output / "result.json").read_bytes())
            check(case + ":closed_manifest", continuation.closed_manifest(run.output, receipt) > 0)
            check(case + ":original_status_preserved", saved["original_attempt"]["status"] == "failed")
            check(case + ":two_saved_blocks_not_reexecuted", calls[:2] == ["reuse_two_closed_anchors", "one_worker_two_solves"])
            check(case + ":exactly_two_reserved_solves", receipt["cumulative_counts"]["solver_invocations_reserved"] == 2)
            if fail_first_audit:
                check("failed_audit:remaining_audit_not_started", calls == ["reuse_two_closed_anchors", "one_worker_two_solves", "frozen_audit"])
                check("failed_audit:failed_receipt", result["status"] == receipt["status"] == "failed")
                check("failed_audit:unknown_steps_preserved", not receipt["cumulative_counts"]["model_step_count_complete"])
                check("failed_audit:earlier_solver_output_preserved", (run.output / "solves/prior.json").is_file())
            else:
                check("complete:only_two_remaining_audits", calls == ["reuse_two_closed_anchors", "one_worker_two_solves", "frozen_audit", "replacement_audit"])
                check("complete:local_and_cumulative_calls", receipt["counts"]["model_passes_completed"] == 2
                      and receipt["cumulative_counts"]["model_passes_completed"] == 4
                      and receipt["cumulative_counts"]["model_steps_reported"] == 1008000)
                check("complete:unresolved_feasible_improvement_retains_status", saved["transaction"]["decision"] == "accepted_feasible_point_improvement"
                      and all(row["solver_status"] == "unresolved" for row in saved["candidates"].values()))
                before_hash = continuation.identity(run.output / "receipt.json")
                try:
                    run.execute()
                except FileExistsError:
                    check("exclusive_continuation_no_overwrite", before_hash == continuation.identity(run.output / "receipt.json"))
                else:
                    check("exclusive_continuation_no_overwrite", False)
            cases[case] = {"calls": calls, "status": result["status"], "counts": receipt["counts"],
                           "cumulative_counts": receipt["cumulative_counts"]}

        root = base / "cap_check"
        (root / continuation.EXP).mkdir(parents=True)
        args = argparse.Namespace(root=str(root), evidence_root="unused", source_revision="0" * 40,
                                  executable_receipt="unused", output_dir=continuation.EXP + "/continuation001")
        run = continuation.Continuation(args)
        run.counts["model_passes_started"] = 2
        with patch.object(continuation.original.Run, "child", side_effect=AssertionError("third model child forbidden")) as child_guard:
            try:
                run.child("third_audit", ["never"], "model")
            except continuation.original.common.ProbeError:
                check("third_new_model_pass_rejected_before_launch", child_guard.call_count == 0)
            else:
                check("third_new_model_pass_rejected_before_launch", False)
        run.previous_resources = {"CPU_total_s": 2., "wall_s_through_wait4": 3.}
        u = run.usage()
        check("cumulative_CPU_includes_original", u["CPU_total_s"] == u["current_invocation_CPU_total_s"] + 2.)
        check("cumulative_active_wall_includes_original", u["wall_s_through_snapshot"] == u["current_invocation_wall_s_through_snapshot"] + 3.)

        # Outer observer veto: a current process individually within the loose
        # stub receipt still exceeds the cumulative budget with its predecessor.
        root = base / "outer_veto"
        old_dir = root / continuation.EXP / "execution_process"
        old_dir.mkdir(parents=True)
        old = {"status": "failed", "process": {"exit_code": 1, "resource_violations": [], "output_truncated": False,
                "CPU_total_s": 29.9, "wall_s_through_wait4": 1., "peak_RSS_bytes": 1000}}
        (old_dir / "receipt.json").write_text(json.dumps(old))
        inner_dir = root / continuation.EXP / "continuation001"
        inner_dir.mkdir()
        cumulative_counts = {"model_passes_started": 4, "model_passes_completed": 4, "model_steps_reported": 1008000,
            "solver_invocations_reserved": 2, "solver_started_markers": 2, "solver_results_saved": 2,
            "repeated_anchor_passes": 0, "truth_reads": 0}
        (inner_dir / "receipt.json").write_text(json.dumps({"status": "completed", "canonical_inference_closed": True,
            "source_revision": "0" * 40, "cumulative_counts": cumulative_counts}))
        (inner_dir / "result.json").write_text(json.dumps({"status": "completed", "source_revision": "0" * 40}))
        def stub(command, output, bounds):
            (output / "raw_probe.json").write_text('{"status":"completed","fabricated":true}\n')
            (output / "probe.stderr").write_text("")
            return {"exit_code": 0, "resource_violations": [], "output_truncated": False,
                    "CPU_total_s": .2, "wall_s_through_wait4": .2, "peak_RSS_bytes": 1000}
        with patch.object(outer.common, "supervise", side_effect=stub) as guard, \
             patch.object(sys, "argv", ["outer", "--root", str(root), "--evidence-root", str(root), "--source-revision", "0" * 40]), \
             redirect_stdout(io.StringIO()):
            exit_code = outer.main()
        outer_receipt = continuation.read_json((root / continuation.EXP / "continuation_process/receipt.json").read_bytes())
        check("outer_cumulative_CPU_veto", exit_code == 1 and outer_receipt["status"] == "failed"
              and "Cumulative original plus continuation process budget exceeded" in outer_receipt["errors"])
        check("outer_exactly_one_stub_launch", guard.call_count == 1)
        all_bytes = sum(p.stat().st_size for d in ("attempt001", "execution_process", "continuation001", "continuation_process")
                        for p in (root / continuation.EXP / d).rglob("*") if p.is_file())
        check("outer_combined_closed_byte_count_exact", all_bytes == outer_receipt["all_closed_output_bytes_including_outer_receipt"])
        cases["outer_veto"] = outer_receipt

    check("source_files_unchanged", hashes == {path: continuation.identity(ROOT / path) for path in paths})
    report = {"schema": "mumble_saved_block_continuation_qualification_v1", "status": "passed",
        "sources": hashes, "checks": checks, "check_count": len(checks), "failed_count": 0,
        "cases": cases, "real_child_calls": 0, "real_model_calls": 0, "real_optimizer_calls": 0,
        "canonical_evidence_reads": 0, "truth_reads": 0, "numeric_stack_imports": 0,
        "resources": {"wall_s": time.monotonic() - start, "CPU_s": time.process_time() - cpu,
                      "peak_own_RSS_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024}}
    continuation.original.common.write_new_json(output, report, 131072)
    print(json.dumps({"status": "passed", "checks": len(checks), "receipt": str(output), "identity": continuation.identity(output)}))


if __name__ == "__main__":
    main()
