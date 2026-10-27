#!/usr/bin/env python3
"""Finite stdlib-only qualification of supervisor accounting and arithmetic.

All records, matrices and attempt roots are fabricated.  Process launch is
forbidden except for Python call stubs; neither numerical-stack imports nor
canonical evidence are needed.  The exclusive receipt binds tested sources.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, redirect_stdout
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import resource
import struct
import subprocess
import sys
import tempfile
import time
import traceback
from types import SimpleNamespace
from unittest.mock import patch


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Checks:
    def __init__(self):
        self.rows = []

    def check(self, name, passed, detail=None):
        self.rows.append({"name": name, "pass": bool(passed), "detail": detail})

    def rejected(self, name, function):
        try:
            function()
        except Exception as error:
            self.check(name, True, {"type": type(error).__name__, "message": str(error)})
        else:
            self.check(name, False, "unexpectedly accepted")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fabricated_geometry():
    x = [-3., -1., 1., 5., 6., math.log(.0625), .1, .15, .2, .25,
         .03125, .5, .01, .02, -.01, -.375]
    lower, upper = [-10.] * 16, [10.] * 16
    lower[5], upper[5] = -4., -2.
    lower[6:11], upper[6:11] = [0.] * 5, [1., 1., 1., 1., .1]
    lower[11:16], upper[11:16] = [.2, -.08, -.08, -.08, -1.], [.95, .08, .08, .08, 1.]
    prior = {"entering_lower": lower, "entering_upper": upper}
    prefix = {"prefix_records": 0, "charge_min_Ah": 0., "charge_max_Ah": 0.,
              "charge_Ah": 0., "elapsed_physical_s": 0.}
    return x, prior, prefix


def fake_args(base, sup, label):
    root = base / label
    (root / sup.EXP).mkdir(parents=True)
    return SimpleNamespace(root=str(root), evidence_root=str(root / "fabricated_evidence"),
                           source_revision="f" * 40,
                           executable_receipt=sup.EXP + "/unused_executable_receipt.json",
                           output_dir=sup.EXP + "/attempt001")


def fixture_resources(exit_code=1, violations=None):
    return {"child_launched": True, "pid": -1, "exit_code": exit_code,
            "peak_RSS_bytes": 4096, "CPU_total_s": 0., "wall_s_through_wait4": 0.,
            "resource_violations": violations or [], "output_truncated": False,
            "fabricated_stub": True}


def prefix_and_parser_checks(sup, base, checks):
    records = [(0, .5, .25, 3.6), (1, 0., -.5, 3.61),
               (2, 2., -.125, 3.59), (3, .25, .5, 3.62)]
    data = b"".join(struct.pack("<Qddd", *row) for row in records)
    path = base / "fabricated_prefix.bin"
    path.write_bytes(data + b"malformed suffix deliberately outside selected prefix")
    result = sup.scan_prefix(path, 4, sha(data))
    half_charge = .125 / 3600.
    expected = {"charge_Ah": 0., "charge_min_Ah": -half_charge,
                "charge_max_Ah": half_charge, "elapsed_physical_s": 2.75}
    checks.check("prefix_hash_and_exact_length", result["prefix_sha256"] == sha(data)
                 and result["prefix_bytes"] == 128 and result["extra_records_read"] == 0)
    checks.check("prefix_integrals_and_both_extrema_include_zero",
                 all(struct.pack("<d", result[key]) == struct.pack("<d", value) for key, value in expected.items()),
                 {"actual": {key: result[key] for key in expected}, "expected": expected})
    checks.check("prefix_preserves_zero_dt_and_last_observation", result["max_abs_current_A"] == .5
                 and result["last_record"] == {"index": 3, "dt_s": .25, "current_A": .5, "observed_voltage_V": 3.62})
    zero = sup.scan_prefix(path, 0, sha(b""))
    checks.check("empty_prefix_has_empty_hash_and_zero_integrals", zero["prefix_records"] == 0
                 and zero["last_record"] is None and zero["charge_min_Ah"] == zero["charge_max_Ah"] == 0.)
    checks.rejected("prefix_wrong_hash_rejected", lambda: sup.scan_prefix(path, 4, "0" * 64))
    cases = {
        "wrong_index": struct.pack("<Qddd", 1, .5, .25, 3.6),
        "negative_dt": struct.pack("<Qddd", 0, -.5, .25, 3.6),
        "nonfinite_current": struct.pack("<Qddd", 0, .5, float("nan"), 3.6),
        "truncated": data[:31],
    }
    for name, fixture in cases.items():
        bad = base / f"fabricated_{name}.bin"
        bad.write_bytes(fixture)
        checks.rejected(f"prefix_{name}_rejected", lambda bad=bad: sup.scan_prefix(bad, 1))
    for name, text in (("duplicate", '{"a":1,"a":2}'), ("nan", '{"a":NaN}'),
                       ("infinity", '{"a":Infinity}'), ("overflow_exponent", '{"a":1e999}'),
                       ("trailing", '{} {}')):
        checks.rejected(f"strict_JSON_{name}_rejected", lambda text=text: sup.strict_json(text))
    checks.rejected("boolean_not_admitted_as_number", lambda: sup.number(True, "fabricated boolean"))
    return {"prefix": result, "fixture_prefix_sha256": sha(data), "fixture_records": records}


def support_and_gram_checks(sup, base, checks):
    x, prior, prefix = fabricated_geometry()
    checks.check("interior_support_admitted", sup.support(x, prior, prefix)["strictly_interior"])
    box_bad = x.copy()
    box_bad[15] = math.nextafter(1., math.inf)
    bad_box = sup.support(box_bad, prior, prefix)
    checks.check("one_ULP_negative_box_slack_rejected", not bad_box["strictly_feasible"]
                 and bad_box["minimum_raw_slack"] < 0. and not bad_box["arithmetic_allowance_used_for_admission"])
    boundary_prefix = {**prefix, "charge_min_Ah": -.03125, "charge_max_Ah": .03125}
    boundary = sup.support(x, prior, boundary_prefix)
    checks.check("exact_SOC_path_boundary_admitted_without_interior_claim",
                 boundary["strictly_feasible"] and not boundary["strictly_interior"])
    path_bad = x.copy()
    path_bad[11] = math.nextafter(.5, 0.)
    bad_path = sup.support(path_bad, prior, boundary_prefix)
    checks.check("one_ULP_negative_SOC_path_slack_rejected", not bad_path["strictly_feasible"]
                 and bad_path["minimum_SOC"] < 0.)
    run = sup.Run(fake_args(base, sup, "support_guard"))
    run.prior, run.prefix = prior, boundary_prefix
    with patch.object(run, "child", side_effect=AssertionError("support failure must precede launch")) as child:
        checks.rejected("negative_support_blocks_model_launch", lambda: run.evaluate("bad", path_bad, Path("unused")))
        checks.check("negative_support_caused_zero_child_calls", child.call_count == 0)

    # Independent dense construction: legacy J is 16x16; B supplies full off-diagonal correlations.
    B = [[(float(i + 1) if i == j else 0.) + (((i + 2) * (j + 3)) % 7 - 3) / 8.
          for j in range(16)] for i in range(16)]
    raw = [[math.fsum(B[k][i] * B[k][j] for k in range(16)) for j in range(16)] for i in range(16)]
    scales = [2. ** (i % 5 - 2) for i in range(16)]
    saved = {"coordinate_scales": scales,
             "joint_normal": [raw[i][j] * scales[i] * scales[j] for i in range(16) for j in range(16)]}
    M = [[0.] * 16 for _ in range(16)]
    for i in range(5):
        M[i][i] = 1.
    M[5][11], M[6][5] = 1., 1.
    for i in range(5):
        M[7 + i][6 + i] = 1.
    for i in range(3):
        M[12 + i][12 + i] = 1.
    M[15][10], M[15][15] = x[15], x[10]
    expected = [math.fsum(M[r][i] * raw[r][c] * M[c][j]
                         for r in range(16) for c in range(16)) for i in range(16) for j in range(i + 1)]
    actual, abs_scales = sup.mapped_legacy_gram(saved, x)
    errors = [abs(a - b) for a, b in zip(actual, expected)]
    checks.check("dense_legacy_Gram_scale_removal_and_full_chain", max(errors) == 0.,
                 {"entries": len(errors), "maximum_absolute_error": max(errors)})
    index = lambda i, j: i * (i + 1) // 2 + j
    analytic_HH = raw[11][11] + 2. * x[15] * raw[11][15] + x[15] ** 2 * raw[15][15]
    analytic_hH = x[10] * raw[15][11] + x[10] * x[15] * raw[15][15]
    checks.check("H_h_product_cross_terms_retained", actual[index(10, 10)] == analytic_HH
                 and actual[index(15, 10)] == analytic_hH
                 and actual[index(15, 15)] == x[10] ** 2 * raw[15][15])
    checks.check("absolute_reference_scales_bound_signed_terms", all(s >= abs(v) for s, v in zip(abs_scales, actual)))
    theta, alpha = sup.x_to_legacy(x)
    checks.check("legacy_point_roundtrip", sup.legacy_to_x(theta, alpha) == x)
    bad_saved = {**saved, "coordinate_scales": [0.] + scales[1:]}
    checks.rejected("nonpositive_legacy_scale_rejected", lambda: sup.mapped_legacy_gram(bad_saved, x))
    return {"dense_Gram_entries": 136, "maximum_mapping_error": max(errors),
            "analytic_HH": analytic_HH, "analytic_hH": analytic_hH,
            "negative_box_slack": bad_box["minimum_raw_slack"], "negative_path_slack": bad_path["minimum_SOC"]}


def comparison_and_review_checks(sup, checks):
    def audit(cost):
        return {"cost": cost, "absolute_summand_scales": {"cost": abs(cost)}}
    cases = [
        ("positive", 1000., 900., -2., -3., "accepted_feasible_point_improvement"),
        ("negative", 900., 1000., -3., -2., "retained_worse_replacement"),
        ("unresolved", 1000., math.nextafter(1000., 0.), -2., -2., "retained_unresolved_cost_difference"),
        ("common_prior_changes_ranking", 10., 11., 3., 0., "accepted_feasible_point_improvement"),
    ]
    decisions = {}
    for label, lf, lr, pf, pr, expected in cases:
        row = sup.compare_candidates(audit(lf), audit(lr), pf, pr, 32)
        checks.check(f"computed_cost_{label}", row["decision"] == expected and row["voltage_threshold"] is None
                     and not row["truth_used"] and not row["MAP_or_optimum_claim"], row)
        decisions[label] = row
    identities = {path: {"sha256": sha(path.encode())} for path in sup.REQUIRED_SOURCES}
    executable = {"source_identities": identities}
    review = {"status": "passed", "canonical_invocations_before_review": 0,
              "plan_sha256": sup.PLAN_SHA256,
              "reviewed_source_sha256": {path: row["sha256"] for path, row in identities.items() if path != sup.REVIEW}}
    sup.validate_review(review, executable)
    checks.check("matching_immutable_review_admitted", True)
    checks.rejected("different_review_plan_rejected", lambda: sup.validate_review({**review, "plan_sha256": "0" * 64}, executable))
    changed = {**review, "reviewed_source_sha256": dict(review["reviewed_source_sha256"])}
    changed["reviewed_source_sha256"][sup.REQUIRED_SOURCES[0]] = "0" * 64
    checks.rejected("different_review_source_rejected", lambda: sup.validate_review(changed, executable))
    missing = {**review, "reviewed_source_sha256": dict(review["reviewed_source_sha256"])}
    missing["reviewed_source_sha256"].pop(sup.REQUIRED_SOURCES[0])
    checks.rejected("missing_review_source_rejected", lambda: sup.validate_review(missing, executable))
    return decisions


def closure_checks(sup, base, checks):
    summaries = {}
    for name, overflow in (("preflight_failure", False), ("output_cap_failure", True)):
        run = sup.Run(fake_args(base, sup, name))
        def failing_preflight(self):
            self.stage = "fabricated_preflight"
            if overflow:
                (self.output / "fabricated_oversized_child_output.bin").write_bytes(b"x" * (sup.LIMITS["closed_output_bytes_max"] + 1))
            raise sup.common.ProbeError("fabricated preflight failure")
        with patch.object(sup.Run, "preflight", failing_preflight), \
             patch.object(sup.Run, "child", side_effect=AssertionError("preflight failure must not launch")) as child:
            result = run.execute()
            checks.check(f"{name}:zero_child_calls", child.call_count == 0)
        receipt = sup.strict_json((run.output / "receipt.json").read_bytes())
        recorded = sup.strict_json((run.output / "result.json").read_bytes())
        actual_bytes = sum(p.stat().st_size for p in run.output.rglob("*") if p.is_file())
        checks.check(f"{name}:failure_receipts_retained", result["status"] == recorded["status"] == receipt["status"] == "failed"
                     and (run.output / "started.json").is_file() and receipt["counts"]["model_passes_started"] == 0
                     and receipt["counts"]["solver_invocations_reserved"] == 0)
        checks.check(f"{name}:closed_byte_count_exact", receipt["closed_output_bytes_including_receipt"] == actual_bytes,
                     {"reported": receipt["closed_output_bytes_including_receipt"], "actual": actual_bytes})
        if overflow:
            checks.check("output_cap_failure:bounded_emergency_closure", receipt["failure_only_emergency_closure"]
                         and not receipt["ordinary_output_cap_passed"]
                         and actual_bytes > sup.LIMITS["closed_output_bytes_max"]
                         and (run.output / "receipt.json").stat().st_size < 262144)
        before = {p.name: sha(p.read_bytes()) for p in run.output.iterdir() if p.is_file()}
        with patch.object(sup.Run, "preflight", side_effect=AssertionError("existing output must block preflight")) as preflight:
            checks.rejected(f"{name}:existing_attempt_rejected", run.execute)
            checks.check(f"{name}:no_overwrite_or_new_preflight", preflight.call_count == 0
                         and before == {p.name: sha(p.read_bytes()) for p in run.output.iterdir() if p.is_file()})
        summaries[name] = {"counts": receipt["counts"], "errors": recorded["errors"],
                           "actual_closed_bytes": actual_bytes,
                           "failure_only_emergency_closure": receipt["failure_only_emergency_closure"]}
    return summaries


def partial_child_checks(sup, base, checks):
    x, prior, prefix = fabricated_geometry()
    args = fake_args(base, sup, "partial_worker_failure")
    run = sup.Run(args)
    evaluated = []
    child_stubs = []

    def preflight(self):
        self.stage = "fabricated_preflight"
        self.plan = {"inputs": {"source_id": "fabricated_source"}}
        self.prefix, self.prior, self.saved_free = prefix, prior, {}
        self.old_x, self.new_x = x.copy(), x.copy()
        self.old_file, self.new_file = self.x_file("old.txt", x), self.x_file("new.txt", x)
        self.python = Path(sys.executable)

    def evaluate(self, name, candidate, path):
        evaluated.append(name)
        return {}

    def failed_worker(command, output, bounds):
        child_stubs.append("worker")
        (output / "raw_probe.json").write_text('{"status":"failed"}\n')
        (output / "probe.stderr").write_text("fabricated worker failure\n")
        solves = run.output / "solves"
        solves.mkdir()
        for name in ("frozen.started.json", "frozen.result.json", "replacement.started.json", "replacement.exception.json"):
            (solves / name).write_text(json.dumps({"fabricated": True, "name": name}))
        return fixture_resources()

    with patch.object(sup.Run, "preflight", preflight), patch.object(sup.Run, "evaluate", evaluate), \
         patch.object(sup, "parity_check", return_value={"passed": True}), \
         patch.object(sup.common, "supervise", failed_worker):
        result = run.execute()
    receipt = sup.strict_json((run.output / "receipt.json").read_bytes())
    markers = sup.strict_json((run.output / "solver_markers.json").read_bytes())
    checks.check("partial_worker:started_and_saved_counts_survive", result["status"] == "failed"
                 and receipt["counts"]["solver_invocations_reserved"] == 2
                 and receipt["counts"]["solver_started_markers"] == 2
                 and receipt["counts"]["solver_results_saved"] == 1)
    checks.check("partial_worker:no_post_failure_audits_or_retry", evaluated == ["old_anchor", "replacement_anchor"]
                 and child_stubs == ["worker"] and receipt["counts"]["retries"] == 0)
    checks.check("partial_worker:unknown_progress_explicit_and_first_result_preserved",
                 "Unknown" in markers["uncompleted_started_progress"]
                 and markers["per_solve"]["replacement"] == {"started": True, "completed": False, "exception": True}
                 and "solves/frozen.result.json" in receipt["files"])

    model_rows = {}
    for name, recover_count in (("model_launch_exception", False), ("partial_model_count", True)):
        other = sup.Run(fake_args(base, sup, name))
        other.output.mkdir()
        other.prefix = {"prefix_records": 3}
        def model_stub(command, output, bounds):
            if not recover_count:
                raise RuntimeError("fabricated supervise exception after reserved model invocation")
            (output / "raw_probe.json").write_text('{"status":"failed","model_step_calls":2}\n')
            (output / "probe.stderr").write_text("fabricated partial model\n")
            return fixture_resources()
        with patch.object(sup.common, "supervise", model_stub):
            checks.rejected(f"{name}:failure_stops_child", lambda: other.child("model", ["fabricated_no_exec"], "model"))
        checks.check(f"{name}:attempt_accounting", other.counts["model_passes_started"] == 1
                     and other.counts["model_passes_completed"] == 0
                     and other.counts["model_steps_reported"] == (2 if recover_count else 0)
                     and other.counts["model_step_count_complete"] is recover_count, dict(other.counts))
        model_rows[name] = dict(other.counts)
    return {"partial_worker_counts": receipt["counts"], "worker_markers": markers,
            "stub_evaluation_order": evaluated, "model_failure_counts": model_rows,
            "real_model_calls": 0, "real_optimizer_calls": 0}


def outer_check(outer, sup, base, checks):
    root = base / "outer_resource_veto"
    attempt = root / sup.EXP / "attempt001"
    attempt.mkdir(parents=True)
    revision = "e" * 40
    (attempt / "receipt.json").write_text(json.dumps({"status": "completed", "canonical_inference_closed": True,
                                                    "source_revision": revision}))
    (attempt / "result.json").write_text(json.dumps({"status": "completed", "source_revision": revision}))
    calls = []
    def observed_failure(command, output, bounds):
        calls.append("outer_process_stub")
        (output / "raw_probe.json").write_text('{"status":"completed"}\n')
        (output / "probe.stderr").write_text("")
        return fixture_resources(0, ["probe_CPU_limit"])
    argv = ["fabricated_outer", "--root", str(root), "--evidence-root", str(root / "unused"),
            "--source-revision", revision]
    captured = io.StringIO()
    with patch.object(sys, "argv", argv), patch.object(outer.common, "supervise", observed_failure), redirect_stdout(captured):
        code = outer.main()
    receipt = sup.strict_json((root / sup.EXP / "execution_process/receipt.json").read_bytes())
    checks.check("outer_resource_failure_vetoes_inner_completed_result", code == 1 and receipt["status"] == "failed"
                 and calls == ["outer_process_stub"] and receipt["process"]["resource_violations"] == ["probe_CPU_limit"])
    checks.check("outer_veto_adds_no_inference", receipt["model_calls"] == receipt["optimizer_calls"] == receipt["truth_reads"] == 0
                 and receipt["retries"] == 0)
    return {"exit_code": code, "status": receipt["status"], "errors": receipt["errors"],
            "resource_violations": receipt["process"]["resource_violations"], "real_child_processes": 0}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output = args.output.open("x", encoding="utf-8")
    start_wall, start_cpu = time.monotonic(), time.process_time()
    checks = Checks()
    paths = [root / "tools/run_retained_likelihood_replacement.py",
             root / "tools/execute_retained_likelihood_replacement_once.py",
             root / "tools/run_conditional_belief_probe.py", Path(__file__).resolve(),
             root / "experiments/retained_likelihood_replacement_001/replacement_math.py",
             root / "experiments/retained_likelihood_replacement_001/solve_worker.py"]
    identities = {str(path.relative_to(root)): sha(path.read_bytes()) for path in paths}
    report = {"schema": "mumble_retained_supervisor_qualification_v1", "status": "running",
              "source_sha256": identities, "scope": "Fabricated stdlib-only fixtures and stubbed child calls",
              "canonical_evidence_reads": 0, "real_model_calls": 0, "real_optimizer_calls": 0,
              "real_child_processes": 0}
    try:
        sys.path.insert(0, str(root / "tools"))
        sup = load_module("retained_supervisor_qualification_subject", paths[0])
        outer = load_module("retained_outer_qualification_subject", paths[1])
        forbidden = lambda *a, **k: (_ for _ in ()).throw(AssertionError("real child/git call forbidden in qualification"))
        with ExitStack() as stack, tempfile.TemporaryDirectory(prefix="mumble_supervisor_fabricated_") as directory:
            stack.enter_context(patch("os.fork", forbidden))
            stack.enter_context(patch.object(subprocess, "Popen", forbidden))
            stack.enter_context(patch.object(sup.common, "git_bytes", forbidden))
            stack.enter_context(patch.object(sup.common, "supervise", forbidden))
            base = Path(directory)
            report["prefix_and_parser"] = prefix_and_parser_checks(sup, base, checks)
            report["support_and_mapping"] = support_and_gram_checks(sup, base, checks)
            report["cost_decisions"] = comparison_and_review_checks(sup, checks)
            report["failure_closure"] = closure_checks(sup, base, checks)
            report["partial_children"] = partial_child_checks(sup, base, checks)
            report["outer_veto"] = outer_check(outer, sup, base, checks)
        forbidden_imports = [name for name in sys.modules if name == "numpy" or name.startswith("numpy.")
                             or name == "scipy" or name.startswith("scipy.")
                             or name in ("replacement_math", "solve_worker")]
        checks.check("no_numerical_stack_or_optimizer_import", not forbidden_imports, forbidden_imports)
        checks.check("tested_sources_unchanged", identities == {str(path.relative_to(root)): sha(path.read_bytes()) for path in paths})
        report["status"] = "pass" if all(row["pass"] for row in checks.rows) else "failed_checks"
    except Exception as error:
        report["status"] = "failed_exception"
        report["exception"] = {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}
    report["checks"] = checks.rows
    report["check_count"] = len(checks.rows)
    report["failed_count"] = sum(not row["pass"] for row in checks.rows)
    report["resources"] = {"wall_s_before_final_encoding": time.monotonic() - start_wall,
                           "CPU_s_before_final_encoding": time.process_time() - start_cpu,
                           "own_peak_RSS_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024}
    json.dump(report, output, indent=2, allow_nan=False)
    output.write("\n")
    output.close()
    print(json.dumps({"status": report["status"], "checks": report["check_count"],
                      "failed": report["failed_count"], "output": str(args.output),
                      "sha256": sha(args.output.read_bytes()), "source_sha256": identities}, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
