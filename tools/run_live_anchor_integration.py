#!/usr/bin/env python3
"""One public-start run. Only metadata/hash/trace reduction occurs in Python.

The qualified capture/wait4 implementation is imported unchanged; no older
experiment preflight, model, prior, optimizer or saved candidate is invoked.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import resource
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
EXP = "experiments/live_anchor_integration_001"
PLAN = EXP + "/host_run_plan.json"
SCHEMA = "mumble_live_anchor_integration_run_v1"
TRACE_SCHEMA = "mumble_live_anchor_trace_v1"
COMMON = "tools/run_compact_nonlinear_history.py"
COMMON_SHA256 = "b4a128b2c3547795fadc9e60406365c3784d0ba733367bfa1372fdbfbe3e7498"
CAPTURE = "tools/capture_preservation.py"
CAPTURE_SHA256 = "14f1ec0c73a816ffa0c441b6a5af465115e98080d1948d452f41a28ea30e5207"
CAPTURE_QUAL = "experiments/capture_preservation_001/attempt001/receipt.json"
CAPTURE_QUAL_SHA256 = "ee57549314b080a2c4b3d9e1a38d3ac144a7ce964d7090c9ae87a05dc1231a2b"
COMMON_QUAL = "experiments/compact_nonlinear_history_001/qualification/supervisor.json"
COMMON_QUAL_SHA256 = "c98856188a12e99928f88c4401ddb4112e42fabf1ef1714a383a53375186c758"
ARCHIVE = "experiments/continuous_learning_validation_001/implementation/primary/B_continuous/source/observations.bin"
ARCHIVE_ID = {"bytes": 16128000, "sha256": "cdbf064028753eb1abf6f33ba2512853ecb58e21493791a269a4b5956545849f"}
CHECKPOINTS = (252000, 294000, 504000)
WORK = {"model_steps": 6048000, "qr_rows": 504000, "query_evaluations": 346501,
        "prior_evaluations": 315001, "proposal_rounds": 31500, "accepted_steps": 31500}
LIMITS = {"CPU_s": 600., "wall_s": 900., "RSS_bytes": 268435456,
          "AS_bytes": 1073741824, "capture_bytes": 67108864,
          "outer_capture_bytes": 262144, "output_bytes": 150994944}
PUBLIC_MEAN = [-3.0484125313829042, -.7458274383888583, 1.90333124488516,
               5.0106352940962555, 5.703782474656201, -2.8134107167600364,
               .1, .1, .1, .1, .024, .68, 0., 0., 0., 0.]
LINKED_C = {EXP + "/" + x for x in ("host_probe.c", "host_input.c", "rolling_engine.c",
                                     "rolling_model.c", "public_contract.c")}
LINKED_C |= {"experiments/live_anchor_bootstrap_001/" + x for x in
             ("adc12.c", "support_step.c", "history_translation.c")}
LINKED_C.add("src/scm_model.c")
HEADERS = {EXP + "/" + x for x in ("host_input.h", "rolling_engine.h", "rolling_model.h")}
HEADERS |= {"experiments/live_anchor_bootstrap_001/" + x for x in
            ("adc12.h", "support_step.h", "history_translation.h", "live_layout.h")}
HEADERS |= {"experiments/compact_nonlinear_history_001/compact_history.h", "include/scm_model.h"}
MODEL_CONTRACT_SOURCES = (LINKED_C - {EXP + "/host_probe.c"}) | HEADERS


def load_common():
    path = ROOT / COMMON
    if hashlib.sha256(path.read_bytes()).hexdigest() != COMMON_SHA256:
        raise ValueError("Qualified supervision source differs")
    spec = importlib.util.spec_from_file_location("live_anchor_qualified_common", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


common = load_common()
require = common.require
identity = common.identity
read_json = common.read_json
write_json = common.write_json
encode_json = common.encode_json
manifest = common.manifest
safe = common.safe


def source_manifest(root, plan):
    """No Git/binary/runner/receipt reference: the source ID is not circular."""
    return {"schema": "mumble_live_anchor_source_manifest_v1",
            "archive": {k: plan["input"][k] for k in ("member", "bytes", "sha256", "records", "format")},
            "study_fixture": plan["study_fixture"], "likelihood": plan["likelihood"],
            "algorithm": plan["algorithm"],
            "model_contract_sources": {p: identity(Path(root) / p) for p in sorted(MODEL_CONTRACT_SOURCES)}}


def source_manifest_id(value):
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(data).hexdigest()


def validate_plan(plan):
    require(plan["schema"] == "mumble_live_anchor_host_run_plan_v1", "Wrong host plan schema")
    inp, execution, algorithm = plan["input"], plan["execution"], plan["algorithm"]
    require(inp["member"] == ARCHIVE and inp["records"] == 504000 and
            {k: inp[k] for k in ("bytes", "sha256")} == ARCHIVE_ID, "Input identity differs")
    require(algorithm["retained_records"] == 16 and algorithm["ingress_records"] == 8 and
            algorithm["rounds_per_full_block"] == 1 and algorithm["blocks"] == 31500 and
            algorithm["fractions_max_per_round"] == 8, "Algorithm work policy differs")
    expected_work = {"query_evaluations": 346501, "prior_evaluations": 315001,
                     "attempted_model_steps": 6048000, "qr_rows": 504000,
                     "proposal_rounds": 31500, "fraction_attempts": 252000}
    require(algorithm["work_caps"] == expected_work, "Work caps differ")
    expected = {"canonical_invocations": 1, "retries": 0, "CPU_s": 600, "wall_s": 900,
                "host_RSS_bytes": 268435456, "AS_bytes": 1073741824,
                "combined_child_stdout_stderr_bytes": 67108864,
                "outer_stdout_stderr_bytes": 262144, "closed_runtime_output_bytes": 150994944}
    require(all(execution[k] == v for k, v in expected.items()), "Resource/invocation policy differs")
    fixture = plan["study_fixture"]
    require(fixture["voltage_V"]["offset"] == 1.5 and fixture["voltage_V"]["units_per_code"] == 1/1024 and
            fixture["current_A"]["offset"] == -.256 and fixture["current_A"]["units_per_code"] == .000125 and
            fixture["temperature_C"]["offset"] == -40. and fixture["temperature_C"]["units_per_code"] == .0625 and
            fixture["temperature_C"]["synthetic_value"] == 25. and fixture["seconds_per_tick"] == 1/7000000,
            "Fixture calibration differs")
    require(plan["likelihood"]["sigma_V"] == .001 and
            plan["likelihood"]["quantization_variance_inflation"] is False and
            plan["likelihood"]["coverage_claim"] is False, "Likelihood policy differs")


def finite(value, label):
    require(type(value) in (float, int) and math.isfinite(value), "Invalid finite " + label)


def counts(value, previous=None):
    require(set(value) == set(WORK), "Counter schema differs")
    for key, maximum in WORK.items():
        require(type(value[key]) is int and 0 <= value[key] <= maximum, "Work cap/type: " + key)
        if previous is not None:
            require(value[key] >= previous[key], "Counter regressed: " + key)
    require(value["accepted_steps"] <= value["proposal_rounds"] and
            value["prior_evaluations"] <= value["query_evaluations"], "Counter ownership differs")


def scan_trace(data, expected_source_id):
    """One bounded saved-data pass, retaining only initial/final/fixed checkpoints."""
    result = {"header": None, "initial": None, "final_snapshot": None, "terminal": None,
              "snapshots": 0, "block_rows": 0, "checkpoint_snapshots": [],
              "line_count": 0, "parse_complete": False, "errors": []}
    previous_index = -16
    previous_counts = None
    offset = 0
    try:
        for line_number, line in enumerate(io.BytesIO(data), 1):
            require(len(line) <= 4096 and line.endswith(b"\n"), "Oversize/incomplete trace line")
            row = common.strict_json(line)
            require(row["schema"] == TRACE_SCHEMA, "Trace schema differs")
            require(result["terminal"] is None, "Data follows terminal record")
            kind = row["kind"]
            if line_number == 1:
                require(kind == "header" and row["source_id"] == expected_source_id and
                        row["records_requested"] == 504000 and row["block_records"] == 16 and
                        row["rounds_per_block"] == 1 and row["candidate_context_bytes"] == 8680 and
                        row["sigma_V"] == .001 and row["coverage_validated"] is False,
                        "Trace header contract differs")
                result["header"] = row
            elif kind in ("initial", "block"):
                require(row["next_index"] == previous_index + 16, "Snapshot chronology differs")
                require((kind == "initial") == (row["next_index"] == 0), "Initial/block role differs")
                common.vector(row["x"], "entering point")
                if kind == "initial":
                    require(common.same_vector(row["x"], PUBLIC_MEAN), "Initialization is not the public mean")
                    require(row["counts"] == {"model_steps": 0, "qr_rows": 0, "query_evaluations": 1,
                                               "prior_evaluations": 1, "proposal_rounds": 0, "accepted_steps": 0},
                            "Initial query/counter policy differs")
                    result["initial"] = row
                endpoint = row["endpoint"]
                require(len(endpoint["v_V"]) == 3, "Endpoint dimension differs")
                for value in [endpoint["SOC"], endpoint["h"], *endpoint["v_V"],
                              endpoint["min_support_slack"], endpoint["min_endpoint_slack"],
                              row["elapsed_s"], row["source_elapsed_s"], row["likelihood_cost"],
                              row["prior_cost"], row["total_cost"]]:
                    finite(value, "trace value")
                require(row["available"] is True and 0 <= endpoint["SOC"] <= 1 and
                        -1 <= endpoint["h"] <= 1, "Unavailable/domain-invalid snapshot")
                require(type(row["search_stop_reason"]) is int and 0 <= row["search_stop_reason"] <= 7 and
                        (row["last_fraction"] is None or type(row["last_fraction"]) is int and
                         0 <= row["last_fraction"] <= 7), "Search diagnostic differs")
                counts(row["counts"], previous_counts)
                require(row["counts"]["qr_rows"] == row["next_index"] and
                        row["counts"]["model_steps"] >= row["next_index"], "Evidence/step count differs")
                old_accepted = 0 if previous_counts is None else previous_counts["accepted_steps"]
                require(row["accepted_steps_in_block"] == row["counts"]["accepted_steps"] - old_accepted and
                        row["accepted_steps_in_block"] in (0, 1), "Accepted-step delta differs")
                if previous_counts is not None:
                    require(row["counts"]["proposal_rounds"] - previous_counts["proposal_rounds"] <= 1,
                            "More than one proposal round in a block")
                    require(row["elapsed_s"] >= result["final_snapshot"]["elapsed_s"] and
                            row["source_elapsed_s"] >= result["final_snapshot"]["source_elapsed_s"],
                            "Time regressed")
                previous_index, previous_counts = row["next_index"], row["counts"]
                result["final_snapshot"] = row
                result["snapshots"] += 1
                result["block_rows"] += kind == "block"
                if row["next_index"] in CHECKPOINTS:
                    result["checkpoint_snapshots"].append({"next_index": row["next_index"],
                        "line": line_number, "byte_offset": offset, "bytes": len(line),
                        "sha256": hashlib.sha256(line).hexdigest(), "snapshot": row})
            elif kind == "terminal":
                require(row["status"] in ("completed", "failed") and row["counts_complete"] is True,
                        "Invalid terminal status/count scope")
                counts(row["counts"], previous_counts)
                require(all(row[k] == 0 for k in ("truth_reads", "historical_candidate_reads", "original_fitter_calls", "source_generations", "retries")),
                        "Forbidden activity reported")
                require(row["snapshots"] == result["snapshots"] and
                        row["last_snapshot_index"] == max(0, previous_index), "Terminal snapshot count differs")
                if row["status"] == "completed":
                    require(all(row[k] == 504000 for k in ("records_read", "records_encoded", "records_offered",
                        "records_admitted", "committed_next_index")) and row["blocks_committed"] == 31500 and
                        result["snapshots"] == 31501 and result["block_rows"] == 31500 and
                        row["counts"] == previous_counts and row["candidate_context_bytes"] == 8680,
                        "Completed stream extent/counters differ")
                    require([r["next_index"] for r in result["checkpoint_snapshots"]] == list(CHECKPOINTS),
                            "Completed checkpoint inventory differs")
                result["terminal"] = row
            else:
                raise ValueError("Unexpected trace role: " + str(kind))
            result["line_count"] = line_number
            offset += len(line)
        require(result["header"] is not None and result["terminal"] is not None, "Trace lacks closure")
        result["parse_complete"] = True
    except Exception as error:
        result["errors"].append({"type": type(error).__name__, "message": str(error)[:2048], "byte_offset": offset})
    return result


def validate_closed_attempt(directory, receipt, result, read_observations=True):
    require(receipt["schema"] == result["schema"] == SCHEMA and receipt["canonical_inference_closed"] is True,
            "Inner receipt/result schema or closure differs")
    require(receipt["status"] == result["status"] == "completed", "Canonical inference did not complete")
    actual = manifest(directory)
    require({p: v for p, v in actual.items() if p != "receipt.json"} == receipt["files"], "Closed manifest differs")
    require(sum(v["bytes"] for v in actual.values()) == receipt["closed_bytes_including_receipt"], "Closed byte count differs")
    require(receipt["counts"] == result["counts"] and receipt["counts"]["producer_children_launched"] == 1 and
            receipt["counts"]["producer_children_reaped"] == 1 and receipt["counts"]["worker_counts_complete"] is True,
            "Child/count closure differs")
    common.rehash(receipt["source_bindings"])
    # Reporting may revalidate metadata while keeping the closed archive unopened.
    common.rehash([row for row in receipt["input_bindings"]
                   if read_observations or row["label"] != "observation_archive"])
    capture = common.load_capture()
    capture.load_verified(Path(directory) / "producer", receipt["process"]["capture_commit_identity"])
    require(result["trace"]["parse_complete"] and result["trace"]["terminal"]["status"] == "completed",
            "Trace did not complete")


def validate_closed_run(root, expected_outer_identity, read_observations=False):
    """Postclosure metadata/capture gate; default never reopens observations.

    The caller must pin this module's source before importing it and pin the
    outer receipt independently. This gate accepts completed runs only; failed
    traces stay failed and need an explicit separately reviewed reporting scope.
    """
    root = Path(root).resolve()
    require(root == ROOT, "Closed source root differs")
    outer_dir, attempt = root / EXP / "execution_process", root / EXP / "attempt001"
    require(identity(outer_dir / "receipt.json") == {k: expected_outer_identity[k] for k in ("bytes", "sha256")},
            "Parent-pinned outer receipt differs")
    outer = read_json(outer_dir / "receipt.json")
    require(outer["schema"] == SCHEMA and outer["kind"] == "outer_receipt" and
            outer["status"] == "completed" and outer["canonical_process_finished"] is True and
            outer["canonical_supervisor_invocations"] == 1 and outer["retries"] == 0 and not outer["errors"],
            "Whole canonical process lacks successful closure")
    common.valid_process(outer["process"])
    require(sum(outer["process"]["stdout_stderr_bytes_written"].values()) <= LIMITS["outer_capture_bytes"],
            "Closed outer output cap differs")
    require(outer["CPU_total_including_outer_before_receipt_s"] <= LIMITS["CPU_s"] and
            outer["wall_total_before_receipt_s"] <= LIMITS["wall_s"] and
            outer["outer_own_peak_RSS_bytes"] <= LIMITS["RSS_bytes"], "Closed outer resource cap differs")
    actual_outer = manifest(outer_dir)
    require({p: x for p, x in actual_outer.items() if p != "receipt.json"} == outer["files"],
            "Closed outer manifest differs")
    require(sum(x["bytes"] for x in actual_outer.values()) == outer["closed_output_bytes_including_receipt"],
            "Closed outer byte count differs")
    require(identity(attempt / "receipt.json") == outer["inner_receipt"] and
            identity(attempt / "result.json") == outer["inner_result"], "Outer/inner identity chain differs")
    inner, result = read_json(attempt / "receipt.json"), read_json(attempt / "result.json")
    require(outer["source_revision"] == inner["source_revision"] == result["source_revision"] and
            outer["host_plan"] == inner["host_plan"] == result["host_plan"], "Closure source/plan chain differs")
    validate_closed_attempt(attempt, inner, result, read_observations=read_observations)
    require(outer["inner_closed_bytes"] == inner["closed_bytes_including_receipt"] and
            outer["all_closed_output_bytes"] == outer["inner_closed_bytes"] + outer["closed_output_bytes_including_receipt"] and
            outer["all_closed_output_bytes"] <= outer["all_closed_output_bytes_max"] == LIMITS["output_bytes"],
            "Whole canonical closed bytes differ")
    common.rehash(outer["source_bindings"])
    capture = common.load_capture()
    stdout = common.strict_json(capture.load_verified(outer_dir, outer["process"]["capture_commit_identity"]))
    require(stdout["schema"] == SCHEMA and stdout["status"] == "completed" and
            stdout["receipt"] == outer["inner_receipt"] and stdout["result"] == outer["inner_result"] and
            stdout["counts"] == inner["counts"], "Whole-process stdout binding differs")
    return {"outer": outer, "inner": inner, "result": result,
            "trace_directory": str(attempt / "producer"),
            "trace_commit_identity": inner["process"]["capture_commit_identity"],
            "source_revision": inner["source_revision"], "source_id": inner["source_id"],
            "observations_reopened": bool(read_observations)}


class Run:
    def __init__(self, args):
        self.args, self.start = args, time.monotonic()
        self.root = Path(args.root).resolve()
        self.output = self.root / EXP / "attempt001"
        self.sources, self.inputs = {}, {}
        self.plan_identity, self.executable, self.source_id = None, None, None
        self.process, self.trace = None, None
        self.errors, self.stage = [], "reservation"
        self.counts = {"canonical_invocations": 1, "producer_children_reserved": 0,
                       "producer_children_launched": 0, "producer_children_reaped": 0,
                       "child_launch_count_complete": True, "worker_counts_complete": True,
                       "model_steps_reserved_upper_bound": 0, "model_steps_reported": 0,
                       "query_evaluations_reported": 0, "prior_evaluations_reported": 0,
                       "proposal_rounds_reported": 0, "qr_rows_reported": 0,
                       "truth_reads": 0, "historical_candidate_reads": 0, "retries": 0}

    def usage(self):
        own, children = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
        return {"CPU_self_s": own.ru_utime + own.ru_stime,
                "CPU_waited_children_s": children.ru_utime + children.ru_stime,
                "CPU_total_s": own.ru_utime + own.ru_stime + children.ru_utime + children.ru_stime,
                "wall_s": time.monotonic() - self.start, "supervisor_peak_RSS_bytes": common.own_peak_bytes(),
                "scope": "Before final inner receipt; whole-process outer wait4 is authoritative for final resources."}

    def preflight(self):
        self.stage = "preflight"
        require(self.root == ROOT, "Unexpected source root")
        executable_path = safe(self.root, self.args.executable_receipt)
        exe = read_json(executable_path)
        require(exe["schema"] == "mumble_live_anchor_integration_executable_receipt_v1" and
                exe["status"] == "qualified_before_canonical_invocation" and
                exe["source_revision"] == self.args.source_revision and exe["qualification"]["passed"] is True,
                "Executable receipt is not qualified/bound")
        common.bind(self.inputs, executable_path, identity(executable_path), "executable_receipt")
        self.executable = exe
        self.plan_identity = identity(self.root / PLAN)
        require(self.plan_identity["sha256"] == exe["host_plan_sha256"], "Host plan binding differs")
        plan = read_json(self.root / PLAN); validate_plan(plan)
        required = LINKED_C | HEADERS | {PLAN, EXP + "/host_audit_plan.json", COMMON, COMMON_QUAL,
            CAPTURE, CAPTURE_QUAL, "tools/run_live_anchor_integration.py", "tools/execute_live_anchor_integration_once.py",
            exe["binary"]["path"], exe["build_receipt"]["path"], exe["qualification"]["receipt"]["path"],
            exe["independent_review"]["path"]}
        source_ids = exe["source_identities"]
        require(required <= set(source_ids), "Missing required published source identity")
        for relative, expected in source_ids.items():
            require(not any(x in relative for x in ("/truth", "/summary.json", "historical_likelihood_control_001/attempt",
                                                     "autonomous_anchor_refinement_001/attempt", "retained_likelihood_replacement_001/continuation")),
                    "Historical candidate/summary/truth is not an inference source")
            common.bind(self.sources, safe(self.root, relative), expected, relative)
        common.verify_source_revision(self.root, self.args.source_revision, source_ids)
        for path, expected_sha in ((COMMON, COMMON_SHA256), (CAPTURE, CAPTURE_SHA256),
                                   (COMMON_QUAL, COMMON_QUAL_SHA256), (CAPTURE_QUAL, CAPTURE_QUAL_SHA256)):
            require(source_ids[path]["sha256"] == expected_sha, "Qualified helper identity differs: " + path)
        for path in (COMMON_QUAL, CAPTURE_QUAL):
            require(read_json(self.root / path)["status"] == "passed", "Prerequisite qualification failed")
        for role in (exe["qualification"]["receipt"], exe["independent_review"]):
            common.bind(self.sources, safe(self.root, role["path"]), role, role["path"])
            require(read_json(self.root / role["path"])["status"] in ("passed", "pass"), "Qualification/review gate pending")
        build_role = exe["build_receipt"]
        common.bind(self.sources, safe(self.root, build_role["path"]), build_role, build_role["path"])
        build = read_json(self.root / build_role["path"])
        require(build["status"] == "passed" and build["binary"] == exe["binary"], "Build/binary mismatch")
        require(all(source_ids.get(p) == expected for p, expected in build["source_identities"].items()),
                "Build source differs from executable source")
        linked = {str(Path(p).resolve().relative_to(self.root)) if Path(p).is_absolute() else p
                  for p in build["compile_command"] if p.endswith(".c")}
        require(linked == LINKED_C, "Canonical binary links an unexpected C implementation")
        require("-fno-fast-math" in build["compile_command"] and "-ffp-contract=off" in build["compile_command"],
                "Floating arithmetic policy differs")
        self.binary = safe(self.root, exe["binary"]["path"])
        common.bind(self.sources, self.binary, exe["binary"], exe["binary"]["path"])
        require(os.access(self.binary, os.X_OK), "Canonical binary is not executable")
        runtime = Path(sys.executable).resolve()
        require(exe["python"]["path"] == str(runtime) and exe["python"]["version"] == sys.version,
                "Python runtime differs")
        common.bind(self.sources, runtime, exe["python"], "python")
        expected_manifest = source_manifest(self.root, plan)
        require(exe["source_manifest"] == expected_manifest and
                exe["source_id"] == source_manifest_id(expected_manifest), "Source/config identity differs")
        self.source_id = exe["source_id"]
        write_json(self.output / "source_manifest.json", expected_manifest)
        self.observations = safe(Path(self.args.evidence_root), ARCHIVE)
        common.bind(self.inputs, self.observations, ARCHIVE_ID, "observation_archive")

    def execute(self):
        self.stage = "producer_reservation"
        self.counts.update(producer_children_reserved=1, model_steps_reserved_upper_bound=WORK["model_steps"],
                           worker_counts_complete=False)
        command = [str(self.binary), "--observations", str(self.observations), "--records", "504000",
                   "--source-id", self.source_id, "--rounds-per-block", "1"]
        used = self.usage()
        bounds = {"CPU_s": LIMITS["CPU_s"] - used["CPU_total_s"],
                  "wall_s": LIMITS["wall_s"] - used["wall_s"],
                  "RSS_bytes": LIMITS["RSS_bytes"], "AS_bytes": LIMITS["AS_bytes"],
                  "capture_bytes": LIMITS["capture_bytes"]}
        require(bounds["CPU_s"] > 0 and bounds["wall_s"] > 0, "No canonical budget remains")
        capture = common.load_capture()
        transaction = capture.CaptureTransaction.reserve(self.output / "producer", max_bytes=LIMITS["capture_bytes"],
            context={"schema": SCHEMA, "source_revision": self.args.source_revision,
                     "source_id": self.source_id, "host_plan": self.plan_identity,
                     "work_reserved": dict(self.counts), "retries": 0})
        write_json(self.output / "launch.json", {"schema": SCHEMA, "command": command, "bounds": bounds,
            "counts_reserved_before_launch": dict(self.counts), "source_bindings": list(self.sources.values()),
            "input_bindings": list(self.inputs.values())})
        self.stage = "producer_supervision"
        self.counts["producer_children_launched"] = None
        self.counts["child_launch_count_complete"] = False
        self.process = common.supervise_capture(command, transaction, bounds)
        self.counts["producer_children_launched"] = int(self.process["child_launched"])
        self.counts["producer_children_reaped"] = int(self.process["child_launched"])
        self.counts["child_launch_count_complete"] = True
        write_json(self.output / "resources.json", self.process)
        self.stage = "closed_trace_validation"
        if self.process["capture_commit_identity"] is not None:
            payload = capture.load_verified(transaction.directory, self.process["capture_commit_identity"])
            self.trace = scan_trace(payload, self.source_id)
            del payload
            terminal = self.trace["terminal"]
            if terminal is not None and self.trace["parse_complete"]:
                self.counts["worker_counts_complete"] = True
                for reported, raw in (("model_steps_reported", "model_steps"),
                                      ("query_evaluations_reported", "query_evaluations"),
                                      ("prior_evaluations_reported", "prior_evaluations"),
                                      ("proposal_rounds_reported", "proposal_rounds"), ("qr_rows_reported", "qr_rows")):
                    self.counts[reported] = terminal["counts"][raw]
            else:
                for key in list(self.counts):
                    if key.endswith("_reported"): self.counts[key] = None
        common.valid_process(self.process)
        require(self.trace is not None and self.trace["parse_complete"] and
                self.trace["terminal"]["status"] == "completed", "Canonical trace lacks a successful closure")

    def close(self):
        try:
            common.rehash(self.sources); common.rehash(self.inputs)
            if self.process and self.process["capture_commit_identity"]:
                common.load_capture().load_verified(self.output / "producer", self.process["capture_commit_identity"])
            used = self.usage()
            require(used["CPU_total_s"] <= LIMITS["CPU_s"] and used["wall_s"] <= LIMITS["wall_s"] and
                    used["supervisor_peak_RSS_bytes"] <= LIMITS["RSS_bytes"], "Inner total resource cap")
        except Exception as error:
            self.errors.append({"stage": "closure", "type": type(error).__name__, "message": str(error)[:2048]})
        if self.counts["producer_children_reserved"] and not self.counts["worker_counts_complete"]:
            for key in list(self.counts):
                if key.endswith("_reported"): self.counts[key] = None
        result = {"schema": SCHEMA, "status": "failed" if self.errors else "completed",
                  "source_revision": self.args.source_revision, "host_plan": self.plan_identity,
                  "source_id": self.source_id, "counts": dict(self.counts), "trace": self.trace,
                  "process": self.process, "errors": self.errors, "truth_reads": 0,
                  "history_fidelity_verified": False, "coverage_validated": False, "candidate_promoted": False}
        write_json(self.output / "result.json", result)
        files = manifest(self.output)
        receipt = {"schema": SCHEMA, "status": result["status"], "canonical_inference_closed": True,
                   "source_revision": self.args.source_revision, "host_plan": self.plan_identity,
                   "source_id": self.source_id, "source_bindings": list(self.sources.values()),
                   "input_bindings": list(self.inputs.values()), "counts": dict(self.counts),
                   "process": self.process, "resources_before_final_receipt": self.usage(),
                   "files": files, "closed_bytes_including_receipt": 0, "errors": self.errors,
                   "truth_reads": 0, "scope": "Candidate process finished or never launched. Failed status is retained; outer wait4 seals whole-process resources."}
        for _ in range(24):
            total_bytes = sum(x["bytes"] for x in files.values()) + len(encode_json(receipt))
            require(total_bytes <= LIMITS["output_bytes"] - 1048576, "Inner output/closure reserve exceeded")
            if total_bytes == receipt["closed_bytes_including_receipt"]: break
            receipt["closed_bytes_including_receipt"] = total_bytes
        else:
            raise ValueError("Inner receipt byte accounting did not stabilize")
        write_json(self.output / "receipt.json", receipt)
        stdout = {"schema": SCHEMA, "status": receipt["status"], "counts": dict(self.counts),
                  "receipt": identity(self.output / "receipt.json"), "result": identity(self.output / "result.json")}
        print(encode_json(stdout).decode(), end="")
        return 0 if receipt["status"] == "completed" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--evidence-root")
    parser.add_argument("--source-revision")
    parser.add_argument("--executable-receipt", default=EXP + "/executable_receipt.json")
    parser.add_argument("--describe-source", action="store_true")
    args = parser.parse_args()
    if args.describe_source:
        plan = read_json(Path(args.root) / PLAN); validate_plan(plan)
        value = source_manifest(Path(args.root), plan)
        print(encode_json({"source_manifest": value, "source_id": source_manifest_id(value)}).decode(), end="")
        return 0
    require(args.evidence_root and args.source_revision, "Canonical run requires explicit input root/revision")
    run = Run(args)
    common.reserve_directory(run.output)
    write_json(run.output / "reservation.json", {"schema": SCHEMA, "canonical_invocations": 1,
               "retries": 0, "source_revision": args.source_revision, "counts_before": dict(run.counts)})
    try:
        run.preflight(); run.execute()
    except Exception as error:
        run.errors.append({"stage": run.stage, "type": type(error).__name__, "message": str(error)[:2048]})
    return run.close()


if __name__ == "__main__":
    raise SystemExit(main())
