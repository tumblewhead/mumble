#!/usr/bin/env python3
"""Report the closed compact-history experiment from verified saved captures.

No observation, truth, historical-summary, model, prior-function or optimizer
access. The caller pins the completed outer receipt; it pins the inner closure,
which pins each capture commit. Surviving duplicate captures never substitute
for a lost original. This module has no execution on import.
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
import stat
import struct
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
EXP = "experiments/compact_nonlinear_history_001"
RUN_SCHEMA = "mumble_compact_nonlinear_history_run_v1"
SOURCE_ID = "f0bd54ce53f1944d4f17070b6380dc8317ae895f2fd1628198a1c5408a67f79c"
CAPTURE_SHA = "14f1ec0c73a816ffa0c441b6a5af465115e98080d1948d452f41a28ea30e5207"
PREFIXES = (252000, 294000)
ARMS = ("public_origin", "autonomous_origin")
GROUPS = {
    "all_42": list(range(42)),
    "local_41_excluding_public": list(range(1, 42)),
    "whitened_32_plus_a7": [1] + list(range(2, 34)),
    "target_8_plus_a7": [1] + list(range(34, 42)),
    "logQ_4_plus_a7": [1] + list(range(34, 38)),
    "SOC_4_plus_a7": [1] + list(range(38, 42)),
}
STOP = {0: "none", 1: "round_limit", 2: "no_resolved_direction", 3: "no_accepted_trial",
        4: "metric_not_positive_definite", 5: "endpoint_approximation_unavailable", 6: "counter_limit"}
REPORT_LIMITS = {"wall_s": 30., "CPU_s": 30., "RSS_bytes": 134217728,
                 "output_bytes": 2097152}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "Duplicate JSON key: " + key)
        result[key] = value
    return result


def parse(data):
    def bad(token):
        raise ValueError("Nonfinite JSON token: " + token)
    value = json.loads(data, object_pairs_hook=pairs, parse_constant=bad)
    def walk(item):
        if isinstance(item, float):
            require(math.isfinite(item), "Overflowed JSON number")
        elif isinstance(item, list):
            for child in item: walk(child)
        elif isinstance(item, dict):
            for child in item.values(): walk(child)
    walk(value)
    return value


def encode(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def ident(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def identity_part(value):
    return {"bytes": value["bytes"], "sha256": value["sha256"]}


def same_vector(a, b):
    return len(a) == len(b) == 16 and all(struct.pack("<d", x) == struct.pack("<d", y)
                                           for x, y in zip(a, b))


def process_valid(process):
    require(process["child_launched"] is True and process["exit_code"] == 0 and
            process["resource_violations"] == [] and process["capture_errors"] == [] and
            process["output_truncated"] is False and process["capture_commit_identity"] is not None,
            "Unsuccessful process/capture closure")


class Report:
    def __init__(self, root, output, outer_sha):
        self.root, self.output, self.outer_sha = root, output, outer_sha
        self.started, self.cpu_started = time.monotonic(), time.process_time()
        self.inputs, self.captures = {}, []
        self.capture = None
        self.activity = {"model_calls": 0, "prior_function_evaluations": 0, "optimizer_calls": 0,
                         "observation_file_opens": 0, "observation_decodes": 0, "truth_reads": 0,
                         "historical_summary_reads": 0, "learner_calls": 0, "candidate_updates": 0,
                         "capture_verified_reads": 0}

    def read(self, path, expected=None, maximum=8388608):
        path = Path(path).absolute()
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_size <= maximum, "Invalid input role/size")
            blocks, count = [], 0
            while block := os.read(fd, 65536):
                count += len(block)
                require(count <= maximum, "Reporting input grew beyond limit")
                blocks.append(block)
            after = os.fstat(fd)
            current = path.lstat()
            signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            require(signature(before) == signature(after) == signature(current), "Reporting input changed during read")
        finally:
            os.close(fd)
        data = b"".join(blocks)
        got = ident(data)
        if expected is not None:
            require(got == identity_part(expected), "Reporting input identity differs: " + str(path))
        previous = self.inputs.get(str(path))
        require(previous is None or previous == got, "Reporting input changed between reads")
        self.inputs[str(path)] = got
        return data

    def read_json(self, path, expected=None):
        return parse(self.read(path, expected))

    def manifest(self, directory, receipt):
        actual = {}
        for path in sorted(directory.rglob("*")):
            require(not path.is_symlink(), "Symlink in closed inference output")
            if path.is_file() and path.name != "receipt.json":
                actual[path.relative_to(directory).as_posix()] = ident(self.read(path))
            elif path.is_file() and path != directory / "receipt.json":
                actual[path.relative_to(directory).as_posix()] = ident(self.read(path))
        require(actual == receipt["files"], "Closed inference file inventory differs")
        own = self.inputs[str((directory / "receipt.json").absolute())]
        require(sum(item["bytes"] for item in actual.values()) + own["bytes"] ==
                receipt["closed_output_bytes_including_receipt"], "Closed inference byte total differs")

    def verified_capture(self, directory, expected):
        data = self.capture.load_verified(directory, expected)
        self.activity["capture_verified_reads"] += 1
        self.captures.append({"directory": str(directory), "commit_identity": expected,
                              "payload": ident(data)})
        return parse(data)

    def load(self):
        outer_dir, attempt = self.root / EXP / "execution_process", self.root / EXP / "attempt001"
        outer_data = self.read(outer_dir / "receipt.json")
        require(ident(outer_data)["sha256"] == self.outer_sha, "Parent-pinned outer receipt differs")
        outer = parse(outer_data)
        require(outer["schema"] == RUN_SCHEMA and outer["status"] == "completed" and
                outer["canonical_process_finished"] is True and outer["canonical_supervisor_invocations"] == 1 and
                outer["retries"] == 0 and outer["errors"] == [], "Outer inference is not successfully closed")
        process_valid(outer["process"])
        inner = self.read_json(attempt / "receipt.json", outer["inner_receipt"])
        result = self.read_json(attempt / "result.json", outer["inner_result"])
        for value in (inner, result):
            require(value["schema"] == RUN_SCHEMA and value["status"] == "completed" and
                    value["source_revision"] == outer["source_revision"] and
                    value["plan_sha256"] == outer["plan_sha256"] and value["errors"] == [],
                    "Inner closure identity/status differs")
        require(inner["canonical_inference_closed"] is True and inner["counts"] == result["counts"] and
                result["audit_feedback_to_primary"] is False and result["coverage_validated"] is False and
                result["candidate_promoted"] is False, "Inner scientific scope differs")
        self.manifest(attempt, inner)
        self.manifest(outer_dir, outer)
        require(inner["closed_output_bytes_including_receipt"] == outer["inner_closed_bytes"] and
                outer["inner_closed_bytes"] + outer["closed_output_bytes_including_receipt"] ==
                outer["all_closed_output_bytes"] <= outer["all_closed_output_bytes_max"],
                "Whole inference output closure differs")
        source_rows = {row["path"]: row for row in inner["source_bindings"]}
        for relative in ("tools/capture_preservation.py", "tools/run_compact_nonlinear_history.py",
                         "tools/execute_compact_history_once.py", EXP + "/compact_history.c",
                         EXP + "/compact_history.h", EXP + "/probe.c", EXP + "/reporting.py",
                         "src/scm_model.c", "include/scm_model.h"):
            path = self.root / relative
            require(str(path) in source_rows, "Reporter/source not pinned before inference: " + relative)
            data = self.read(path, source_rows[str(path)])
            if relative == "tools/capture_preservation.py":
                require(ident(data)["sha256"] == CAPTURE_SHA, "Unqualified capture implementation")
        specification = importlib.util.spec_from_file_location("compact_report_capture", self.root / "tools/capture_preservation.py")
        self.capture = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(self.capture)
        outer_stdout = self.verified_capture(outer_dir, outer["process"]["capture_commit_identity"])
        require(outer_stdout["status"] == "completed" and outer_stdout["counts"] == inner["counts"] and
                outer_stdout["receipt"] == outer["inner_receipt"] and outer_stdout["result"] == outer["inner_result"],
                "Outer captured inner closure differs")
        counts = inner["counts"]
        require(counts["canonical_invocations"] == 1 and counts["retries"] == 0 and
                all(counts[key] is True for key in ("model_step_count_complete", "worker_counts_complete", "child_launch_count_complete")),
                "Incomplete inference work accounting")
        for role, expected in (("primary", 1), ("audits", 2)):
            require(all(counts[role + suffix] == expected for suffix in ("_reserved", "_launched", "_completed")),
                    "Incomplete scientific child sequence")
        for key in ("truth_reads", "historical_summary_reads", "old_learner_calls", "original_fitter_calls", "source_generations"):
            require(counts[key] == 0, "Inference scope violation: " + key)
        children = inner["children"]
        require([(c["mode"], c["prefix_records"]) for c in children] ==
                [("primary", 294000), ("audit", 252000), ("audit", 294000)], "Scientific role order differs")
        payloads, capture_bindings = [], []
        totals = {key: 0 for key in ("model_steps", "prior_evaluations", "query_evaluations", "proposal_rounds", "trial_evaluations")}
        for child, name in zip(children, ("primary", "audit252000", "audit294000")):
            directory = attempt / "calls" / name
            require(Path(child["directory"]) == directory and directory.resolve() == directory,
                    "Unexpected capture path")
            require(child["launched"] is True and child["counts_reported_complete"] is True, "Incomplete child")
            process_valid(child["process"])
            commit = child["process"]["capture_commit_identity"]
            require(child["payload"] == {"capture_directory": str(directory), "commit_identity": commit},
                    "Parent-pinned child capture differs")
            payload = self.verified_capture(directory, commit)
            require(payload["status"] == "completed" and payload["source_id"] == SOURCE_ID and
                    payload["prefix_records"] == child["prefix_records"] and
                    payload["counts"] == child["reported_counts"] and payload["counts"]["counts_complete"] is True,
                    "Committed payload differs from parent accounting")
            for key in totals: totals[key] += payload["counts"][key]
            payloads.append(payload)
            capture_bindings.append({"directory": str(directory), "identity": commit})
        require(capture_bindings == inner["capture_bindings"], "Capture inventory differs")
        require(all(totals[key] == counts[key + "_reported"] for key in totals), "Cumulative scientific counts differ")
        prepared_path = self.root / EXP / "prepared/receipt.json"
        require(str(prepared_path) in source_rows, "Prepared labels lack a pre-inference binding")
        prepared = self.read_json(prepared_path, source_rows[str(prepared_path)])
        require(prepared["status"] == "completed" and len(prepared["nodes"]) == 42, "Prepared labels unavailable")
        return outer, inner, result, payloads, prepared

    def resources(self):
        usage = resource.getrusage(resource.RUSAGE_SELF)
        return {"wall_s_before_final_encoding": time.monotonic() - self.started,
                "CPU_self_s": time.process_time() - self.cpu_started,
                "peak_RSS_bytes": usage.ru_maxrss * (1 if sys.platform == "darwin" else 1024)}

    def recheck(self):
        for path, expected in list(self.inputs.items()):
            require(ident(self.read(path, expected)) == expected, "Reporting input changed")
        for row in self.captures:
            require(ident(self.capture.load_verified(row["directory"], row["commit_identity"])) == row["payload"],
                    "Committed original/duplicate changed during reporting")
            self.activity["capture_verified_reads"] += 1
        resources = self.resources()
        require(resources["wall_s_before_final_encoding"] <= REPORT_LIMITS["wall_s"] and
                resources["CPU_self_s"] <= REPORT_LIMITS["CPU_s"] and
                resources["peak_RSS_bytes"] <= REPORT_LIMITS["RSS_bytes"], "Reporting resource cap")


def finite_error(approximate, exact):
    if approximate["status_code"] != 0 or exact["status"] != "available":
        return None
    return math.fsum([approximate["cost"], -exact["cost"]])


def mode_fidelity(arm, oracle, mode, origin):
    rows = []
    for i, (approximate, exact) in enumerate(zip(arm["fixed_points"], oracle)):
        require(approximate["index"] == exact["index"] == i, "Fixed node order differs")
        error = finite_error(approximate[mode], exact)
        row = {"index": i, "exact_status": exact["status"], "exact_status_code": exact["status_code"],
               "first_unavailable_index": exact["first_unavailable_index"],
               "compact_status_code": approximate[mode]["status_code"], "exact_cost": exact["cost"],
               "compact_cost": approximate[mode]["cost"], "compact_minus_exact": error}
        for name, reference in (("relative_to_bank_origin", origin), ("relative_to_a7", 1)):
            ref = finite_error(arm["fixed_points"][reference][mode], oracle[reference])
            row[name] = None if error is None or ref is None else math.fsum([
                approximate[mode]["cost"], -exact["cost"],
                -arm["fixed_points"][reference][mode]["cost"], oracle[reference]["cost"]])
        rows.append(row)
    groups = {}
    for name, indices in GROUPS.items():
        available = [i for i in indices if rows[i]["compact_minus_exact"] is not None]
        errors = [rows[i]["compact_minus_exact"] for i in available]
        centered = [abs(rows[i]["relative_to_a7"]) for i in available if rows[i]["relative_to_a7"] is not None]
        groups[name] = {"indices": indices, "complete_declared_set": len(available) == len(indices),
                        "available_count": len(available), "unavailable_indices": [i for i in indices if i not in available],
                        "error_min_available": min(errors) if errors else None,
                        "error_max_available": max(errors) if errors else None,
                        "error_oscillation_available": math.fsum([max(errors), -min(errors)]) if errors else None,
                        "maximum_abs_a7_centered_error_available": max(centered) if centered else None}
    return {"bank_origin_index": origin, "offset_at_bank_origin": rows[origin]["compact_minus_exact"],
            "offset_at_a7": rows[1]["compact_minus_exact"], "points": rows, "groups": groups}


def summarize(outer, inner, result, payloads, prepared):
    primary, *audits = payloads
    require(primary["schema"] == "mumble_compact_nonlinear_history_primary_v1" and
            [p["next_index"] for p in primary["checkpoints"]] == list(PREFIXES), "Primary schema/checkpoints differ")
    nodes = prepared["nodes"]
    initial_priors = [a["before"]["prior_cost"] for a in primary["checkpoints"][0]["arms"]]
    comparisons, previous_counts = [], [{}, {}]
    for checkpoint, audit in zip(primary["checkpoints"], audits):
        prefix = checkpoint["next_index"]
        require(checkpoint["complete"] is True and audit["schema"] == "mumble_compact_nonlinear_history_audit_v1" and
                audit["prefix_records"] == prefix and len(audit["points"]) == 2 and
                [a["arm"] for a in checkpoint["arms"]] == list(ARMS), "Audit/checkpoint extent differs")
        oracle = checkpoint["oracle"]["points"]
        require(len(oracle) == len(nodes) == 42 and
                all(same_vector(node["x"], exact["x"]) for node, exact in zip(nodes, oracle)),
                "Prepared/exact node values differ")
        arms = []
        for a, (arm, audited) in enumerate(zip(checkpoint["arms"], audit["points"])):
            require(audited["status"] == "available" and same_vector(arm["candidate_x"], audited["x"]) and
                    audited["records_accumulated"] == prefix and audited["model_steps"] == prefix,
                    "Independent audit did not evaluate the selected candidate")
            x, exact_endpoint = arm["candidate_x"], audited["endpoint_x"]
            exact_objective = math.fsum([audited["cost"], arm["after"]["prior_cost"]])
            origin = oracle[a]
            origin_objective = (math.fsum([origin["cost"], initial_priors[a]])
                                if origin["status"] == "available" else None)
            incremental = {key: value - previous_counts[a].get(key, 0) for key, value in arm["counts"].items()}
            require(all(v >= 0 for v in incremental.values()), "Bank counters moved backward")
            previous_counts[a] = dict(arm["counts"])
            accepted = [e for e in arm["trace"] if e["event"] == "trial" and e["flags"] & 16]
            require(len(accepted) == incremental["accepted_steps"], "Accepted trace/counter count differs")
            modes = {mode: mode_fidelity(arm, oracle, mode, a) for mode in ("affine", "quartic")}
            arms.append({"arm": arm["arm"], "candidate_x": x, "Q_Ah": math.exp(x[5]),
                         "endpoint_SOC": exact_endpoint[11], "endpoint_SOC_percent": 100. * exact_endpoint[11],
                         "refinement_status": arm["refine_status"], "stop_reason_code": arm["refinement_stop"],
                         "stop_reason": STOP.get(arm["refinement_stop"], "unknown"),
                         "before": arm["before"], "after": arm["after"], "counts_cumulative": arm["counts"],
                         "counts_since_previous_checkpoint": incremental,
                         "trace": {"proposal_events": sum(e["event"] == "proposal" for e in arm["trace"]),
                                   "trial_attempts": sum(e["event"] == "trial" for e in arm["trace"]),
                                   "cost_evaluated_trials": sum(e["event"] == "trial" and e["cost_available"] for e in arm["trace"]),
                                   "accepted_steps": len(accepted), "accepted_fractions": [e["step"]["alpha"] for e in accepted]},
                         "candidate_comparison": {
                             "exact_likelihood_cost": audited["cost"], "cached_candidate_prior_cost": arm["after"]["prior_cost"],
                             "exact_likelihood_plus_cached_prior": exact_objective,
                             "compact_minus_exact_likelihood": math.fsum([arm["after"]["likelihood_cost"], -audited["cost"]]),
                             "represented_objective_decrease_this_checkpoint": math.fsum([arm["before"]["total_cost"], -arm["after"]["total_cost"]]),
                             "initial_origin_exact_likelihood": origin["cost"],
                             "initial_origin_cached_prior_from_first_checkpoint": initial_priors[a],
                             "initial_origin_exact_objective": origin_objective,
                             "exact_objective_decrease_from_initial_origin": None if origin_objective is None else math.fsum([origin_objective, -exact_objective])},
                         "endpoint_comparison": {
                             "represented": arm["endpoint"], "exact_model_x": exact_endpoint,
                             "represented_minus_exact_SOC": math.fsum([arm["endpoint"]["SOC"], -exact_endpoint[11]]),
                             "represented_minus_exact_SOC_pp": 100. * math.fsum([arm["endpoint"]["SOC"], -exact_endpoint[11]]),
                             "represented_minus_exact_v_V": [math.fsum([v, -exact_endpoint[12+i]]) for i, v in enumerate(arm["endpoint"]["v"])],
                             "represented_minus_exact_h": math.fsum([arm["endpoint"]["h"], -exact_endpoint[15]])},
                         "fidelity": modes})
        comparisons.append({"next_index": prefix, "nominal_time_s": prefix / 35., "arms": arms})
    return {"schema": "mumble_compact_nonlinear_history_report_v1", "status": "completed_saved_output_analysis",
            "use_requires_completed_reporting_receipt": True, "inference_status": "completed",
            "source_revision": inner["source_revision"], "plan_sha256": inner["plan_sha256"],
            "source_id": SOURCE_ID, "groups": GROUPS, "nodes": nodes, "checkpoints": comparisons,
            "inference_counts": inner["counts"], "storage": primary["storage"],
            "inference_resources": {"whole_canonical_process": outer["process"],
                                    "outer_own_peak_RSS_bytes": outer["outer_own_peak_RSS_bytes"],
                                    "outer_bookkeeping_wall_s_before_receipt": outer["outer_bookkeeping_wall_s_before_receipt"],
                                    "all_closed_output_bytes": outer["all_closed_output_bytes"]},
            "interpretation": {
                "error": "e(x)=computed compact likelihood cost minus computed exact-model likelihood cost; priors cancel at each matched point.",
                "offset": "A parameter-independent offset does not alter normalized odds. Both bank-origin and common-a7 offsets/centered errors are retained.",
                "oscillation": "max(e)-min(e) bounds absolute log-odds distortion only between available nodes in the declared finite set. Unavailable nodes remain explicit; no probability mass is discarded or renormalized.",
                "nodes": "These are coupled metric directions and curvature-predicted target paths, not nonlinear profiles, posterior samples or credible-interval endpoints.",
                "candidate": "Exact candidate audits occurred after primary inference closed and never changed acceptance. Cached kernel-prior constants are reused algebraically, with no prior-function evaluation.",
                "memory": "One candidate replaces the old learner. Host two-arm/oracle/trace storage is counted separately; target stack, IRQ/libm, ADC and checkpoint drivers remain unmeasured planning obligations.",
                "old_anchor_run": "The previous autonomous-anchor invocation remains failed; its independently verified generation7 is the declared warm representation origin, not a successful old-run closure."},
            "no_coverage_or_promotion_claim": True, "decision_thresholds_added": 0}


def fsync_directory(directory):
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try: os.fsync(fd)
    finally: os.close(fd)


def write(path, value):
    data = encode(value)
    with path.open("xb") as handle:
        handle.write(data); handle.flush(); os.fsync(handle.fileno())
    fsync_directory(path.parent)
    return ident(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--outer-sha256", required=True)
    parser.add_argument("--output-dir", default=EXP + "/reporting001")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    require(root == ROOT, "Wrong repository root")
    require(len(args.outer_sha256) == 64 and all(c in "0123456789abcdef" for c in args.outer_sha256), "Invalid outer pin")
    output = Path(args.output_dir)
    if not output.is_absolute(): output = root / output
    output = output.absolute()
    require(output.parent.resolve() == root / EXP and not output.exists(), "Reporting destination must be new under this experiment")
    output.mkdir(exist_ok=False); fsync_directory(output.parent)
    report = Report(root, output, args.outer_sha256)
    own = ident(Path(__file__).read_bytes())
    write(output / "reservation.json", {"schema": "mumble_compact_nonlinear_history_reporting_receipt_v1",
          "status": "reserved", "source": {"path": EXP + "/reporting.py", **own},
          "parent_pinned_outer_sha256": args.outer_sha256, "limits": REPORT_LIMITS})
    errors, outputs, summary = [], {}, None
    try:
        loaded = report.load()
        summary = summarize(*loaded)
        report.recheck()
        data = encode(summary)
        require(len(data) <= REPORT_LIMITS["output_bytes"] - 262144, "Summary output cap")
        outputs["summary.json"] = write(output / "summary.json", summary)
        report.recheck()
    except Exception as error:
        errors.append({"type": type(error).__name__, "message": str(error)})
    receipt = {"schema": "mumble_compact_nonlinear_history_reporting_receipt_v1",
               "status": "failed" if errors else "completed", "parent_pinned_outer_sha256": args.outer_sha256,
               "source": {"path": EXP + "/reporting.py", **own}, "errors": errors,
               "activity": report.activity, "inputs": report.inputs, "capture_bindings": report.captures,
               "all_reporting_inputs_unchanged": not errors, "resources": report.resources(),
               "limits": REPORT_LIMITS, "outputs": outputs, "closed_output_bytes_including_receipt": 0,
               "inference_artifacts_modified": False, "new_scientific_execution": False}
    existing = sum(p.stat().st_size for p in output.iterdir() if p.is_file())
    for _ in range(24):
        size = existing + len(encode(receipt))
        if size > REPORT_LIMITS["output_bytes"] and receipt["status"] != "failed":
            receipt["status"] = "failed"
            receipt["errors"].append({"type": "ResourceFailure", "message": "Reporting output cap"})
            receipt["all_reporting_inputs_unchanged"] = False
        if size == receipt["closed_output_bytes_including_receipt"]: break
        receipt["closed_output_bytes_including_receipt"] = size
    else:
        raise ValueError("Reporting receipt size did not stabilize")
    receipt_id = write(output / "reporting_receipt.json", receipt)
    print(json.dumps({"status": receipt["status"], "output_directory": str(output),
                      "summary": outputs.get("summary.json"), "receipt": receipt_id,
                      "activity": report.activity, "errors": errors}, allow_nan=False))
    return 0 if receipt["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
