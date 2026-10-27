#!/usr/bin/env python3
"""One public-start, bounded autonomous-anchor experiment; no retry or history seed."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import math
import os
from pathlib import Path
import resource
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
EXP = "experiments/autonomous_anchor_refinement_001"
PLAN_SHA256 = "3f493d1067ea40798c8c91d5a0820fa89cef888d8d082774df2230679835be2b"
BASE = "ef4efee174c946c76a18a1b6a974900a8bbe41b2"
OLD = "experiments/retained_likelihood_replacement_001"
PINNED_HELPERS = {
    "tools/run_conditional_belief_probe.py": "411c483c25a2578ef99feea1476ef8482ecb14c65ca0f7958c9e65f9b9f0d82a",
    "tools/run_retained_likelihood_replacement.py": "aaaa652008e03476768e273fa048e8567a9e9b932a43c6716d12b41aca5e1986",
}
for _relative, _expected in PINNED_HELPERS.items():
    if hashlib.sha256((ROOT / _relative).read_bytes()).hexdigest() != _expected:
        raise ValueError("Qualified source helper changed: " + _relative)
import run_conditional_belief_probe as common
import run_retained_likelihood_replacement as helpers

_spec = importlib.util.spec_from_file_location("autonomous_anchor_schema", ROOT / EXP / "schema.py")
if _spec is None or _spec.loader is None:
    raise ValueError("Cannot load the shared closure schema")
schema = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(schema)
require = schema.require
CONFIG = EXP + "/qualification/math.json"
REVIEW = EXP + "/independent_review.json"
REQUIRED_SOURCES = (
    schema.PLAN, EXP + "/schema.py", "tools/run_autonomous_anchor_refinement.py",
    "tools/execute_autonomous_anchor_once.py", EXP + "/proposal_worker.py",
    EXP + "/anchor_math.py", CONFIG, REVIEW, EXP + "/reporting.py", EXP + "/DESIGN.md",
    EXP + "/orchestration_qualification.py", EXP + "/qualification/orchestration.json",
    *PINNED_HELPERS, OLD + "/stream_evaluator.c", OLD + "/replacement_math.py",
    "src/scm_model.c", "include/scm_model.h", "src/scm_hypothesis.c",
)


def vector(value, name):
    return helpers.vector(value, 16, name)


def load_prior(value, x):
    require(isinstance(value, dict) and value["schema"] == "mumble_autonomous_anchor_prior_v1" and
            value["x"] == x and value["prior_evaluations"] == 1 and
            value["support_normalizer_included"] is False and
            value["reference_math_sha256"] == "870583ec263f4bf4e69b80aa9fc06402336deb606aeaa88533389ddce715261b",
            "Prior identity or supported-kernel semantics differ")
    helpers.number(value["cost"], "prior cost")
    vector(value["gradient"], "prior gradient")
    helpers.vector(value["hessian_lower"], 136, "prior Hessian")
    helpers.vector(value["responsibilities"], 2, "prior responsibilities")
    return value


def new_counts():
    return {
        "supervisor_invocations": 1,
        "model_passes_reserved": 0, "model_passes_launched": 0, "model_passes_completed": 0,
        "model_steps_reported": 0, "model_step_count_complete": True,
        "proposal_calls_reserved": 0, "proposal_actions_completed": 0,
        "prior_actions_reserved": 0, "assess_actions_reserved": 0,
        "external_prior_evaluations_reserved": 0, "external_prior_evaluations_started_reported": 0,
        "external_prior_evaluations_completed": 0,
        "optimizer_calls_started": 0, "optimizer_calls_completed": 0,
        "proposal_combined_evaluations_reported": 0, "worker_activity_complete": True,
        "accepted_steps": 0, "rejected_trials": 0, "infeasible_trials": 0,
        "truth_reads": 0, "historical_candidate_reads": 0, "learner_calls": 0,
        "source_generations": 0, "original_fitter_calls": 0, "retries": 0,
    }


class Run:
    def __init__(self, args):
        self.args = args
        self.root = Path(args.root).resolve()
        self.output = Path(args.output_dir)
        if not self.output.is_absolute():
            self.output = self.root / self.output
        self.output = self.output.resolve()
        self.start = time.monotonic()
        self.stage = "reserve_attempt"
        self.counts = new_counts()
        self.sources, self.inputs, self.generated = {}, {}, {}
        self.children, self.proposal_records, self.trial_records, self.generation_records = [], [], [], []
        self.outstanding_models, self.outstanding_workers = set(), set()
        self.initial = self.active = None
        self.call_serial = 0
        self.supervise = common.supervise

    def relative(self, path):
        return str(Path(path).relative_to(self.output))

    def file_record(self, path):
        return {"path": self.relative(path), **schema.identity(path)}

    def bind(self, records, path, expected=None):
        path = Path(path).resolve()
        return schema.bind(path, expected or schema.identity(path), records, str(path))

    def write(self, relative, value, emergency=False):
        path = self.output / relative
        used = sum(row["bytes"] for row in schema.manifest(self.output).values())
        maximum = 2097152 if emergency else schema.LIMITS["closed_output_bytes_max"] - used
        schema.write_json(path, value, maximum)
        return path

    def usage(self):
        own = resource.getrusage(resource.RUSAGE_SELF)
        children = resource.getrusage(resource.RUSAGE_CHILDREN)
        return {
            "CPU_self_s": own.ru_utime + own.ru_stime,
            "CPU_waited_children_s": children.ru_utime + children.ru_stime,
            "CPU_total_s": own.ru_utime + own.ru_stime + children.ru_utime + children.ru_stime,
            "wall_s": time.monotonic() - self.start,
            "supervisor_peak_RSS_bytes": common.own_peak_bytes(),
        }

    def check_budget(self):
        usage = self.usage()
        require(usage["CPU_total_s"] <= schema.LIMITS["CPU_total_s_max"], "Cumulative CPU cap")
        require(usage["wall_s"] <= schema.LIMITS["wall_total_s_max"], "Cumulative wall cap")
        require(usage["supervisor_peak_RSS_bytes"] <= schema.LIMITS["supervisor_RSS_bytes_max"], "Supervisor RSS cap")
        require(sum(row["bytes"] for row in schema.manifest(self.output).values()) <=
                schema.LIMITS["closed_output_bytes_max"] - 262144, "Runtime output cap or closure reserve exhausted")
        return usage

    def recheck(self):
        for bindings in (self.sources, self.inputs, self.generated):
            schema.rehash_bindings(bindings)
        return self.check_budget()

    def preflight(self):
        self.stage = "preflight"
        require(self.root == ROOT and self.output == self.root / EXP / "attempt001", "Wrong canonical source or attempt location")
        require(len(self.args.source_revision) == 40 and all(c in "0123456789abcdef" for c in self.args.source_revision),
                "A full published source revision is required")
        plan_path = self.root / schema.PLAN
        require(schema.identity(plan_path)["sha256"] == PLAN_SHA256, "Frozen contract changed")
        self.plan = schema.read_json(plan_path)
        require(self.plan["schema"] == "mumble_autonomous_anchor_refinement_contract_v1" and
                self.plan["status"] == "frozen_before_canonical_inference" and self.plan["base_revision"] == BASE,
                "Unexpected contract")
        limits = self.plan["limits"]
        expected_limits = {
            "proposal_rounds_max": 16, "full_prefix_model_passes_max": 33, "model_steps_max": 8316000,
            "proposal_iterations_max": 100, "proposal_combined_objective_gradient_evaluations_max": 256,
            "total_proposal_combined_objective_gradient_evaluations_max": 4096,
            "external_exact_prior_evaluations_max": 33, "CPU_s_max": 60,
            "active_process_wall_s_max": 90, "process_peak_RSS_bytes_max": 134217728,
            "process_address_space_bytes_max": 1073741824,
            "per_child_combined_stdout_stderr_bytes_max": 524288,
            "all_closed_runtime_outputs_bytes_max": 8388608,
        }
        require(all(limits[key] == value for key, value in expected_limits.items()), "Frozen caps differ")
        require(self.plan["trial_policy"]["fractions"] == list(schema.FRACTIONS) and
                self.plan["trial_policy"]["Armijo_c1"] == .25, "Frozen trial policy differs")
        os.environ.update(schema.THREAD_ENV)
        os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
        receipt_path = Path(self.args.executable_receipt)
        if not receipt_path.is_absolute():
            receipt_path = self.root / receipt_path
        self.bind(self.inputs, receipt_path)
        executable = schema.read_json(receipt_path)
        require(executable["schema"] == "mumble_autonomous_anchor_executable_receipt_v1" and
                executable["status"] == "qualified_before_canonical_invocation" and
                executable["source_revision"] == self.args.source_revision and
                executable["plan_sha256"] == PLAN_SHA256 and executable["qualification"]["passed"] is True,
                "Unqualified or mismatched executable receipt")
        identities = executable["source_identities"]
        require(set(REQUIRED_SOURCES) <= set(identities), "Executable receipt omits required source")
        for relative, expected in identities.items():
            require(not any(marker in relative for marker in (
                "/historical_likelihood_control_001/", "/attempt001/", "/attempt002/",
                "/continuation001/", "/reporting001/", "/reporting_attempt", "/summary.json", "/truth.bin")),
                "Nonpublic inference source binding: " + relative)
            path = schema.safe(self.root, relative)
            self.bind(self.sources, path, expected)
            committed = common.git_bytes(self.root, self.args.source_revision, relative)
            require(len(committed) == expected["bytes"] and hashlib.sha256(committed).hexdigest() == expected["sha256"],
                    "Published source differs: " + relative)
            self.check_budget()
        review = schema.read_json(self.root / REVIEW)
        require(review["status"] in ("passed", "pass") and review["plan_sha256"] == PLAN_SHA256,
                "Independent implementation review did not pass")
        reviewed = review.get("source_sha256", review.get("reviewed_source_sha256", {}))
        require(all(reviewed.get(relative) == identities[relative]["sha256"] for relative in identities if relative != REVIEW),
                "Implementation review source binding differs")
        self.binary = schema.safe(self.root, executable["binary"]["path"])
        self.bind(self.sources, self.binary, executable["binary"])
        reference = self.plan["unchanged_reference"]
        require(str(self.binary.relative_to(self.root)) == reference["evaluator_binary"] and
                schema.identity(self.binary) == {"bytes": reference["evaluator_binary_bytes"], "sha256": reference["evaluator_binary_sha256"]},
                "Evaluator differs from unchanged qualified binary")
        require(os.access(self.binary, os.X_OK), "Evaluator is not executable")
        self.python = Path(sys.executable).resolve()
        require(str(self.python) == executable["python"]["path"] and sys.version == executable["python"]["version"],
                "Qualified Python runtime differs")
        self.bind(self.sources, self.python, executable["python"])
        config = schema.read_json(self.root / CONFIG)
        require(config["schema"] == "mumble_autonomous_anchor_math_qualification_v1" and config["status"] == "passed",
                "Mathematical qualification has not passed")
        self.policy = config["configuration"]["policy"]
        self.prior_config = config["configuration"]["public_prior"]
        self.public_x = vector(self.prior_config["public_unsplit_mean"], "public initialization")
        evidence_root = Path(self.args.evidence_root).resolve()
        require(not self.output.is_relative_to(evidence_root), "Output overlaps evidence")
        declared = self.plan["input"]
        self.observations = schema.safe(evidence_root, declared["member"])
        self.bind(self.inputs, self.observations, {"bytes": declared["archive_bytes"], "sha256": declared["archive_sha256"]})
        require(declared["prefix_records"] == schema.PREFIX and declared["prefix_bytes"] == schema.PREFIX * 32,
                "Prefix scope differs")
        self.prefix = helpers.scan_prefix(self.observations, schema.PREFIX, declared["prefix_sha256"])
        self.prefix_geometry = {"records": schema.PREFIX, "charge_min_Ah": self.prefix["charge_min_Ah"],
                                "charge_max_Ah": self.prefix["charge_max_Ah"]}
        self.write("prefix_input.json", self.prefix)
        feasible = helpers.support(self.public_x, self.prior_config, self.prefix)
        require(feasible["strictly_feasible"], "Fixed public mean is infeasible; no substitute seed")
        self.write("public_initialization.json", {"x": self.public_x, "support": feasible,
                   "origin": "Fixed public unsplit mean", "alternate_seeds": 0,
                   "historical_candidate_reads": 0, "truth_reads": 0})
        self.write("configuration.json", {"policy": self.policy, "public_prior": self.prior_config})
        self.recheck()

    def child(self, kind, prepare):
        self.stage = kind
        self.recheck()
        self.call_serial += 1
        name = "calls/call%03d_%s" % (self.call_serial, kind)
        out = self.output / name
        schema.reserve_directory(out)
        command = prepare(out)
        before = dict(self.counts)
        if kind == "model":
            require(self.counts["model_passes_reserved"] < schema.MAX_MODEL_PASSES, "Model-pass cap")
            self.counts["model_passes_reserved"] += 1
            self.counts["model_step_count_complete"] = False
            self.outstanding_models.add(name)
        else:
            key = {"propose": "proposal_calls_reserved", "prior": "prior_actions_reserved", "assess": "assess_actions_reserved"}[kind]
            if kind == "propose":
                require(self.counts[key] < schema.MAX_PROPOSALS, "Proposal cap")
            if kind == "prior":
                require(self.counts[key] == 0, "Only the initial standalone prior action is allowed")
            self.counts[key] += 1
            if kind in ("prior", "assess"):
                self.counts["external_prior_evaluations_reserved"] += 1
            require(self.counts["prior_actions_reserved"] + self.counts["assess_actions_reserved"] <= schema.MAX_MODEL_PASSES,
                    "External prior action cap")
            self.counts["worker_activity_complete"] = False
            self.outstanding_workers.add(name)
        usage = self.check_budget()
        bounds = {"probe_CPU_s_max": schema.LIMITS["CPU_total_s_max"] - usage["CPU_total_s"],
                  "probe_wall_s_max": schema.LIMITS["wall_total_s_max"] - usage["wall_s"],
                  "probe_address_space_bytes_max": schema.LIMITS["child_address_space_bytes_max"],
                  "probe_peak_RSS_bytes_max": schema.LIMITS["child_RSS_bytes_max"],
                  "probe_output_bytes_max": schema.LIMITS["child_stdout_stderr_bytes_max"],
                  "supervisor_peak_RSS_bytes_max": schema.LIMITS["supervisor_RSS_bytes_max"]}
        require(bounds["probe_CPU_s_max"] > 0. and bounds["probe_wall_s_max"] > 0., "No remaining process budget")
        reservation = {"schema": schema.VERSION, "kind": "child_reservation", "action": kind,
                       "sequence": self.call_serial, "command": command, "bounds": bounds,
                       "counts_before": before, "counts_after_reservation": dict(self.counts),
                       "source_bindings": list(self.sources.values()), "input_bindings": list(self.inputs.values()),
                       "request_files": schema.manifest(out), "roles": schema.CAPTURE_ROLES,
                       "utc": datetime.now(timezone.utc).isoformat(), "retry": False}
        self.write(name + "/reservation.json", reservation)
        row = {"sequence": self.call_serial, "action": kind, "directory": name,
               "reservation": name + "/reservation.json", "resources": None, "activity_complete": False}
        self.children.append(row)
        # The reservation and its directory entry are durable before this call.
        resources = self.supervise(command, out, bounds)
        row["resources"] = resources
        self.write(name + "/resources.json", resources)
        if kind == "model":
            if resources["child_launched"]:
                self.counts["model_passes_launched"] += 1
            try:
                payload = schema.read_json(out / schema.CAPTURE_ROLES["stdout"])
                steps = payload["model_step_calls"]
                require(type(steps) is int and 0 <= steps <= schema.PREFIX, "Invalid partial model count")
                self.counts["model_steps_reported"] += steps
                row["model_steps_reported"] = steps
                row["activity_complete"] = True
                self.outstanding_models.remove(name)
                self.counts["model_step_count_complete"] = not self.outstanding_models
            except Exception as error:
                row["activity_error"] = type(error).__name__ + ": " + str(error)
        else:
            try:
                result_path = out / "output/result.json"
                result = schema.read_json(result_path)
                require(result["schema"] == "mumble_autonomous_anchor_worker_result_v1" and result["action"] == kind,
                        "Unexpected worker result envelope")
                counts = result["counts"]
                for key in ("prior_evaluations", "prior_evaluations_completed", "optimizer_calls_started", "optimizer_calls_completed"):
                    require(type(counts[key]) is int and 0 <= counts[key] <= 1, "Invalid worker count: " + key)
                require(counts["prior_evaluations_completed"] <= counts["prior_evaluations"] and
                        counts["optimizer_calls_completed"] <= counts["optimizer_calls_started"], "Worker completion exceeds starts")
                if kind == "propose":
                    require(counts["prior_evaluations"] == 0, "Proposal reevaluated the cached prior")
                else:
                    require(counts["optimizer_calls_started"] == 0, "Nonproposal action entered optimizer")
                require((out / "output/solve_started.json").exists() == bool(counts["optimizer_calls_started"]),
                        "Optimizer start marker/count mismatch")
                self.counts["external_prior_evaluations_started_reported"] += counts["prior_evaluations"]
                self.counts["external_prior_evaluations_completed"] += counts["prior_evaluations_completed"]
                self.counts["optimizer_calls_started"] += counts["optimizer_calls_started"]
                self.counts["optimizer_calls_completed"] += counts["optimizer_calls_completed"]
                evaluations = counts["combined_evaluations"]
                if counts["optimizer_evaluation_count_complete"] is True:
                    require(type(evaluations) is int and 0 <= evaluations <= (256 if kind == "propose" else 0),
                            "Worker combined-evaluation cap")
                    self.counts["proposal_combined_evaluations_reported"] += evaluations
                else:
                    require(evaluations is None, "Incomplete optimizer count must remain null")
                row["worker_counts"] = counts
                row["worker_result"] = self.file_record(result_path)
                if result["status"] == "completed":
                    require(counts["optimizer_evaluation_count_complete"] is True and
                            counts["optimizer_calls_started"] == counts["optimizer_calls_completed"],
                            "Completed action has unknown optimizer work")
                    require(counts["prior_evaluations"] == counts["prior_evaluations_completed"] == (0 if kind == "propose" else 1),
                            "Completed action violates the cached-prior evaluation budget")
                    row["activity_complete"] = True
                    self.outstanding_workers.remove(name)
                    if kind == "propose":
                        self.counts["proposal_actions_completed"] += 1
                    self.counts["worker_activity_complete"] = not self.outstanding_workers
                require(self.counts["external_prior_evaluations_reserved"] <= 33 and
                        self.counts["proposal_combined_evaluations_reported"] <= 4096, "Cumulative algebra/solve cap")
            except Exception as error:
                row["activity_error"] = type(error).__name__ + ": " + str(error)
        self.write(name + "/completion.json", row)
        self.recheck()
        require(resources["exit_code"] == 0 and resources["resource_violations"] == [] and
                resources["output_truncated"] is False, "Child exit/resource failure: " + kind)
        require(row["activity_complete"], "Incomplete child activity: " + kind)
        return out

    def evaluate(self, x):
        x = vector(x, "model entering vector")
        feasible = helpers.support(x, self.prior_config, self.prefix)
        require(feasible["strictly_feasible"], "Raw-infeasible candidate before model invocation")

        def prepare(out):
            path = out / "x.txt"
            data = (" ".join(format(value, ".17g") for value in x) + "\n").encode("ascii")
            with path.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            schema.fsync_directory(out)
            require([float(token) for token in data.decode().split()] == x, "Entering vector did not round-trip")
            self.bind(self.generated, path)
            return [str(self.binary), "--x", str(path), "--sigma", "0.001", "--observations",
                    str(self.observations), "--prefix", str(schema.PREFIX)]

        out = self.child("model", prepare)
        path = out / schema.CAPTURE_ROLES["stdout"]
        payload = schema.read_json(path)
        validation = helpers.validate_evaluator(payload, x, self.prefix)
        self.write(self.relative(out / "validation.json"), validation)
        self.bind(self.generated, path)
        self.counts["model_passes_completed"] += 1
        return {"payload": payload, "path": path}

    def worker(self, action, **fields):
        request = {"schema": "mumble_autonomous_anchor_worker_request_v1", "action": action,
                   "policy": self.policy, **fields}

        def prepare(out):
            path = out / "request.json"
            self.write(self.relative(path), request)
            self.bind(self.generated, path)
            return [str(self.python), "-B", str(self.root / EXP / "proposal_worker.py"),
                    "--input", str(path), "--output-dir", str(out / "output")]

        out = self.child(action, prepare)
        wrapper = schema.read_json(out / schema.CAPTURE_ROLES["stdout"])
        path = out / "output/result.json"
        result = schema.read_json(path)
        require(wrapper["status"] == result["status"] == "completed" and wrapper["action"] == action and
                wrapper["counts"] == result["counts"] and wrapper["payload_path"] == "result.json",
                "Worker stdout/result mismatch")
        self.bind(self.generated, path)
        return result["payload"], path, result["counts"]

    def point(self, evaluated, prior, prior_path, pointer):
        payload = evaluated["payload"]
        load_prior(prior, payload["x"])
        return {"block": payload, "block_path": evaluated["path"], "prior": prior,
                "prior_path": prior_path, "prior_pointer": pointer}

    def install(self, point, generation):
        payload, prior = point["block"], point["prior"]
        record = {
            "schema": schema.VERSION, "kind": "accepted_generation", "generation": generation,
            "x": payload["x"], "endpoint_x": payload["endpoint_x"], "endpoint_state": payload["endpoint_state"],
            "likelihood_cost": payload["cost"], "prior_kernel_cost": prior["cost"],
            "computed_common_objective": math.fsum([payload["cost"], prior["cost"]]),
            "evaluator": self.file_record(point["block_path"]),
            "prior": {**self.file_record(point["prior_path"]), "json_pointer": point["prior_pointer"]},
            "ownership": {"source_id": self.plan["input"]["source_id"], "source_interval": [0, schema.PREFIX],
                          "cursor": schema.PREFIX, "prior_copies": 1, "active_likelihood_blocks": 1},
            "retired_generation": generation - 1 if generation else None,
            "retired_block_added_as_evidence": False,
        }
        name = "generations/generation%03d.json" % generation
        record["generation_record"] = name
        self.write(name, record)
        # Only after the complete new generation record is durable does the
        # in-memory owner advance. The old record and raw block remain immutable.
        self.active = point
        point["record"] = record
        self.generation_records.append(name)
        if generation:
            self.counts["accepted_steps"] += 1
        return point

    def refine(self):
        initial = self.evaluate(self.public_x)
        payload, prior_path, _ = self.worker("prior", x=self.public_x)
        active = self.install(self.point(initial, payload["prior"], prior_path, "/payload/prior"), 0)
        self.initial = active
        for round_index in range(1, schema.MAX_PROPOSALS + 1):
            if self.counts["model_passes_reserved"] >= schema.MAX_MODEL_PASSES:
                return "model_pass_budget_exhausted"
            payload, proposal_path, counts = self.worker("propose", block=active["block"], prior=active["prior"],
                                                         prefix=self.prefix_geometry)
            proposal = payload["proposal"]
            candidate = vector(proposal["candidate_x"], "proposal candidate")
            require(proposal["anchor_x"] == active["block"]["x"], "Proposal anchor is not the active accepted point")
            record_name = "proposals/round%03d.json" % round_index
            self.write(record_name, {"schema": schema.VERSION, "kind": "proposal_record", "round": round_index,
                       "generation": active["record"]["generation"], "active_evaluator": active["record"]["evaluator"],
                       "worker_result": self.file_record(proposal_path), "counts": counts,
                       "status": proposal["status"], "direction_admitted": proposal["direction_admitted"]})
            self.proposal_records.append(record_name)
            require(proposal["status"] != "metric_not_positive_definite", "Unmodified proposal metric is not positive definite")
            require(type(proposal["direction_admitted"]) is bool, "Invalid direction admission flag")
            if not proposal["direction_admitted"]:
                return "no_admissible_direction"
            require(proposal["resolved_descent"] is True and proposal["resolved_model_decrease"] is True and
                    proposal["step_box_feasible"] is True and
                    helpers.support(candidate, self.prior_config, self.prefix)["strictly_feasible"],
                    "Admitted proposal violates its own direction/support guards")
            scaled_step = [(b - a) / d for a, b, d in zip(active["block"]["x"], candidate,
                           self.prior_config["public_unsplit_sd"])]
            require(all(math.isfinite(u) and 1. + u >= 0. and 1. - u >= 0. for u in scaled_step),
                    "Admitted direction exceeds the one-public-SD step box")
            admitted = False
            for fraction_index, alpha in enumerate(schema.FRACTIONS):
                if self.counts["model_passes_reserved"] >= schema.MAX_MODEL_PASSES:
                    return "model_pass_budget_exhausted"
                anchor = active["block"]["x"]
                x = list(candidate) if alpha == 1. else [a + alpha * (b - a) for a, b in zip(anchor, candidate)]
                feasible = helpers.support(x, self.prior_config, self.prefix)
                name = "trials/round%03d_fraction%02d.json" % (round_index, fraction_index)
                trial = {"schema": schema.VERSION, "kind": "trial_record", "round": round_index,
                         "fraction_index": fraction_index, "alpha": alpha, "x": x,
                         "generation_before": active["record"]["generation"], "support": feasible,
                         "proposal_record": record_name, "accepted": False, "model_called": False}
                if not feasible["strictly_feasible"]:
                    self.counts["infeasible_trials"] += 1
                    trial["status"] = "rejected_raw_infeasible_without_model_call"
                    self.write(name, trial)
                    self.trial_records.append(name)
                    continue
                evaluated = self.evaluate(x)
                trial["model_called"] = True
                trial["evaluator"] = self.file_record(evaluated["path"])
                payload, assess_path, _ = self.worker("assess", current_block=active["block"],
                    current_prior=active["prior"], trial_block=evaluated["payload"], proposal=proposal,
                    alpha=alpha, prefix=self.prefix_geometry)
                assessment = payload["assessment"]
                load_prior(assessment["trial_prior"], x)
                require(type(assessment["accepted"]) is bool, "Invalid trial acceptance flag")
                trial["assessment"] = self.file_record(assess_path)
                trial["status"] = assessment["status"]
                trial["accepted"] = assessment["accepted"]
                if assessment["accepted"]:
                    point = self.point(evaluated, assessment["trial_prior"], assess_path, "/payload/assessment/trial_prior")
                    active = self.install(point, active["record"]["generation"] + 1)
                    trial["generation_after"] = active["record"]["generation"]
                    trial["installed_generation"] = active["record"]["generation_record"]
                    admitted = True
                else:
                    self.counts["rejected_trials"] += 1
                    trial["generation_after"] = active["record"]["generation"]
                self.write(name, trial)
                self.trial_records.append(name)
                if admitted:
                    break
            if not admitted:
                return "all_trial_fractions_rejected"
        return "proposal_round_budget_exhausted"

    def run(self):
        schema.reserve_directory(self.output)
        for name in ("calls", "generations", "proposals", "trials"):
            schema.reserve_directory(self.output / name)
        errors, stop = [], None
        try:
            self.write("reservation.json", {"schema": schema.VERSION, "kind": "run_reservation",
                       "source_revision": self.args.source_revision, "plan_sha256": PLAN_SHA256,
                       "command": [sys.executable, *sys.argv], "counts": dict(self.counts),
                       "canonical_invocations": 1, "retries": 0})
            self.preflight()
            stop = self.refine()
            self.recheck()
            require(self.counts["proposal_calls_reserved"] == self.counts["proposal_actions_completed"] and
                    self.counts["model_passes_completed"] == self.counts["model_passes_reserved"] >= 1 and
                    self.counts["external_prior_evaluations_completed"] == self.counts["model_passes_completed"],
                    "Completed sequence has incomplete point/proposal/prior accounting")
        except Exception as error:
            errors.append({"stage": self.stage, "type": type(error).__name__, "message": str(error)})
        for name, bindings in (("source", self.sources), ("input", self.inputs), ("generated", self.generated)):
            try:
                schema.rehash_bindings(bindings)
            except Exception as error:
                errors.append({"stage": "posthash_" + name, "type": type(error).__name__, "message": str(error)})
        if self.outstanding_models or self.outstanding_workers:
            errors.append({"stage": "closure", "type": "IncompleteActivity", "message": "Reserved child activity remains unknown"})
        result = {"schema": schema.VERSION, "kind": "result", "status": "failed" if errors else "completed",
                  "source_revision": self.args.source_revision, "plan_sha256": PLAN_SHA256,
                  "stop_reason": stop if not errors else "numerical_input_or_resource_failure",
                  "counts": dict(self.counts), "initial": self.initial.get("record") if self.initial else None,
                  "final": self.active.get("record") if self.active else None,
                  "proposal_records": self.proposal_records, "trial_records": self.trial_records,
                  "generation_records": self.generation_records, "errors": errors,
                  "coverage_validated": False, "candidate_promoted": False}
        self.write("result.json", result, emergency=bool(errors))
        receipt = {"schema": schema.VERSION, "kind": "run_receipt", "status": result["status"],
                   "source_revision": self.args.source_revision, "plan_sha256": PLAN_SHA256,
                   "canonical_inference_closed": True, "roles": schema.ATTEMPT_ROLES,
                   "counts": dict(self.counts), "errors": errors,
                   "source_bindings": list(self.sources.values()), "input_bindings": list(self.inputs.values()),
                   "generated_bindings": list(self.generated.values()), "children": self.children,
                   "resources_before_receipt": self.usage(), "limits": schema.LIMITS,
                   "unresolved_model_reservations": sorted(self.outstanding_models),
                   "unresolved_worker_reservations": sorted(self.outstanding_workers),
                   "reserved_model_step_upper_bound": self.counts["model_passes_reserved"] * schema.PREFIX,
                   "scope": "All child processes waited. Whole-process outer wait4, including final closure, controls success. No inference retry or post-close model/prior/truth work."}
        schema.close_receipt(self.output, receipt)
        print(schema.encode_json({"schema": schema.VERSION, "status": result["status"], "stop_reason": result["stop_reason"],
              "counts": self.counts, "result": self.file_record(self.output / "result.json"),
              "receipt": self.file_record(self.output / "receipt.json")}).decode(), end="")
        return 0 if not errors else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--executable-receipt", default=EXP + "/executable_receipt.json")
    parser.add_argument("--output-dir", default=EXP + "/attempt001")
    args = parser.parse_args()
    try:
        return Run(args).run()
    except Exception as error:
        print(schema.encode_json({"schema": schema.VERSION, "status": "failed_before_closed_receipt",
              "exception": {"type": type(error).__name__, "message": str(error)}, "retries": 0}).decode(), end="")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
