#!/usr/bin/env python3
"""One separately authorized, postclosure three-point reference transaction.

The live candidate is never changed. This adapter compiles the already frozen
reference source once, then evaluates only the three predeclared saved points.
"""
from __future__ import annotations

import argparse
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
EXP = "experiments/live_anchor_integration_001"
SELF = "tools/run_live_anchor_exact_audits.py"
RUNNER = "tools/run_live_anchor_integration.py"
RUNNER_SHA256 = "e9dccc8fec9720e39a4c82551637adc9f5dbacf8cee4743a6d49b0f34e889d6f"
PLAN = EXP + "/host_audit_plan.json"
PLAN_SHA256 = "b144122a05d67038b533ca44b3b971f961f32a22b9efa907a64a6dd8dc74cad3"
AUDIT_C = EXP + "/host_exact_audit.c"
AUDIT_C_SHA256 = "5288e16efa087025602cdf0c4e6bbe3b1043c6820047ce4dfb409467293d4a83"
SCHEMA = "mumble_live_anchor_postclosure_audits_v1"
CHECKPOINTS = (252000, 294000, 504000)
CAPS = {"CPU_s": 30, "wall_s": 60, "RSS_bytes": 134217728,
        "AS_bytes": 536870912, "capture_bytes_per_child": 1048576,
        "closed_output_bytes": 8388608}
LINKED_C = (AUDIT_C, EXP + "/host_input.c", EXP + "/public_contract.c",
            "experiments/live_anchor_bootstrap_001/adc12.c", "src/scm_model.c")
HEADERS = (EXP + "/host_input.h", "experiments/live_anchor_bootstrap_001/adc12.h",
           "experiments/compact_nonlinear_history_001/compact_history.h", "include/scm_model.h")


def load_runner():
    path = ROOT / RUNNER
    if hashlib.sha256(path.read_bytes()).hexdigest() != RUNNER_SHA256:
        raise ValueError("Reviewed canonical runner source differs")
    spec = importlib.util.spec_from_file_location("postclosure_live_anchor_runner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Audit:
    def __init__(self, args):
        self.args, self.started = args, time.monotonic()
        self.run = load_runner()
        self.common, self.capture = self.run.common, self.run.common.load_capture()
        self.root = Path(args.root).resolve()
        self.output = self.root / EXP / "postclosure_audit001"
        self.sources, self.inputs, self.records, self.errors = {}, {}, [], []
        self.closed, self.build, self.stage = None, None, "reservation"
        self.counts = {"dispatcher_invocations": 1, "builds_reserved": 0,
            "builds_completed": 0, "audit_passes_reserved": 0,
            "audit_passes_completed": 0, "model_steps_reserved_upper_bound": 0,
            "model_init_calls_reported": 0, "model_steps_reported": 0,
            "model_predict_calls_reported": 0, "model_counts_complete": True,
            "children_reserved": 0, "children_launched_reported": 0,
            "children_reaped_reported": 0, "child_activity_complete": True,
            "optimizer_calls": 0, "prior_calls": 0, "truth_reads": 0,
            "candidate_mutations": 0, "retries": 0}

    def require(self, condition, message):
        self.common.require(condition, message)

    def usage(self):
        own = resource.getrusage(resource.RUSAGE_SELF)
        children = resource.getrusage(resource.RUSAGE_CHILDREN)
        return {"CPU_self_s": own.ru_utime + own.ru_stime,
            "CPU_waited_children_s": children.ru_utime + children.ru_stime,
            "CPU_total_s": own.ru_utime + own.ru_stime + children.ru_utime + children.ru_stime,
            "wall_s": time.monotonic() - self.started,
            "supervisor_peak_RSS_bytes": self.common.own_peak_bytes(),
            "scope": "Dispatcher and waited compile/reference children through pre-final-receipt snapshot; exact wait4 retained per child."}

    def bind(self, collection, path, expected, label):
        return self.common.bind(collection, path, expected, label)

    def preflight(self):
        self.stage = "closed_candidate_and_frozen_reference"
        self.require(self.root == ROOT, "Unexpected source root")
        outer_identity = {"bytes": self.args.outer_receipt_bytes,
                          "sha256": self.args.outer_receipt_sha256}
        self.closed = self.run.validate_closed_run(self.root, outer_identity, read_observations=False)
        self.require(self.closed["source_revision"] == self.args.source_revision,
                     "Audit and candidate source revision differ")
        plan_identity = self.run.identity(self.root / PLAN)
        self.require(plan_identity["sha256"] == PLAN_SHA256, "Frozen audit plan differs")
        plan = self.run.read_json(self.root / PLAN)
        self.require(plan["schema"] == "mumble_live_anchor_postclosure_audit_plan_v1" and
                     plan["checkpoints"] == list(CHECKPOINTS) and plan["maximum_passes"] == 3 and
                     plan["maximum_exact_model_steps"] == 1050000 and plan["caps"] == CAPS and
                     plan["maximum_optimizer_calls"] == plan["maximum_prior_calls"] == 0,
                     "Frozen audit policy differs")
        self.require(self.run.identity(self.root / AUDIT_C)["sha256"] == AUDIT_C_SHA256,
                     "Frozen reference C source differs")
        source_names = (*LINKED_C, *HEADERS, PLAN, RUNNER, self.run.COMMON, self.run.CAPTURE)
        source_ids = {p: self.run.identity(self.root / p) for p in source_names}
        self.common.verify_source_revision(self.root, self.args.source_revision, source_ids)
        for relative, expected in source_ids.items():
            self.bind(self.sources, self.root / relative, expected, relative)
        self.bind(self.sources, self.root / SELF, self.run.identity(self.root / SELF), SELF)
        executable_rows = [r for r in self.closed["inner"]["input_bindings"]
                           if r["label"] == "executable_receipt"]
        self.require(len(executable_rows) == 1, "Canonical executable receipt is not unique")
        executable_path = Path(executable_rows[0]["path"])
        self.bind(self.inputs, executable_path, executable_rows[0], "canonical_executable_receipt")
        executable = self.run.read_json(executable_path)
        build_role = executable["build_receipt"]
        build_path = self.common.safe(self.root, build_role["path"])
        self.bind(self.inputs, build_path, build_role, "canonical_build_acceptance")
        canonical_build = self.run.read_json(build_path)
        self.compiler = Path(canonical_build["compile_command"][0]).resolve()
        self.require(self.compiler.is_absolute() and os.access(self.compiler, os.X_OK), "Compiler unavailable")
        self.bind(self.sources, self.compiler, self.run.identity(self.compiler), "compiler_driver")
        self.bind(self.sources, Path(sys.executable).resolve(),
                  self.run.identity(Path(sys.executable).resolve()), "python_runtime")
        for directory, name in (("execution_process", "receipt.json"),
                                ("attempt001", "receipt.json"), ("attempt001", "result.json")):
            path = self.root / EXP / directory / name
            self.bind(self.inputs, path, self.run.identity(path), directory + "/" + name)
        trace_dir = Path(self.closed["trace_directory"])
        commit_path = trace_dir / self.capture.COMMIT
        self.bind(self.inputs, commit_path, self.closed["trace_commit_identity"], "candidate_capture_commit")
        commit = self.run.read_json(commit_path)
        for role in ("original", "object", "reservation", "stream_closed"):
            row = commit[role]
            self.bind(self.inputs, trace_dir / row["path"], row, "candidate_capture_" + role)
        self.observations = self.common.safe(Path(self.args.evidence_root), self.run.ARCHIVE)
        self.bind(self.inputs, self.observations, self.run.ARCHIVE_ID, "observation_archive")
        self.checkpoints = {r["next_index"]: r for r in self.closed["result"]["trace"]["checkpoint_snapshots"]}
        self.require(set(self.checkpoints) <= set(CHECKPOINTS), "Unexpected checkpoint selection")
        self.run.write_json(self.output / "preflight.json", {"schema": SCHEMA,
            "source_revision": self.args.source_revision, "source_id": self.closed["source_id"],
            "outer_receipt": outer_identity, "audit_plan": plan_identity,
            "source_bindings": list(self.sources.values()), "input_bindings": list(self.inputs.values()),
            "checkpoint_indices": sorted(self.checkpoints), "counts": dict(self.counts)})

    def child(self, directory, command, reservation):
        used = self.usage()
        remaining_cpu, remaining_wall = CAPS["CPU_s"] - used["CPU_total_s"], CAPS["wall_s"] - used["wall_s"]
        self.require(remaining_cpu > 0 and remaining_wall > 0 and
                     used["supervisor_peak_RSS_bytes"] <= CAPS["RSS_bytes"], "Audit resource budget exhausted")
        bounds = {"CPU_s": remaining_cpu, "wall_s": remaining_wall,
                  "RSS_bytes": CAPS["RSS_bytes"], "AS_bytes": CAPS["AS_bytes"],
                  "capture_bytes": CAPS["capture_bytes_per_child"]}
        self.counts["children_reserved"] += 1
        transaction = self.capture.CaptureTransaction.reserve(directory,
            max_bytes=CAPS["capture_bytes_per_child"], context={"schema": SCHEMA, **reservation})
        self.run.write_json(directory / "launch.json", {"schema": SCHEMA, "command": command,
            "bounds": bounds, "reservation": reservation, "counts_before_launch": dict(self.counts),
            "source_bindings": list(self.sources.values()), "input_bindings": list(self.inputs.values())})
        try:
            process = self.common.supervise_capture(command, transaction, bounds)
        except BaseException:
            self.counts["child_activity_complete"] = False
            if reservation["kind"] == "reference":
                self.counts["model_counts_complete"] = False
            raise
        self.counts["children_launched_reported"] += int(process["child_launched"])
        self.counts["children_reaped_reported"] += int(process["child_launched"])
        self.run.write_json(directory / "resources.json", process)
        self.common.valid_process(process)
        payload = self.capture.load_verified(directory, process["capture_commit_identity"])
        return process, payload

    def compile(self):
        self.stage = "single_reference_build"
        self.counts["builds_reserved"] = 1
        directory = self.output / "build001"
        self.binary = directory / "host_exact_audit"
        command = [str(self.compiler), "-std=c99", "-O2", "-Wall", "-Wextra", "-Wpedantic", "-Werror",
            "-fno-fast-math", "-ffp-contract=off", "-I" + str(self.root / "include"),
            "-I" + str(self.root / EXP), *(str(self.root / p) for p in LINKED_C),
            "-lm", "-o", str(self.binary)]
        process, _ = self.child(directory, command, {"kind": "build", "build_invocations": 1,
                                                    "model_calls": 0, "prior_calls": 0})
        self.require(os.access(self.binary, os.X_OK), "Reference build has no executable output")
        binary_identity = self.run.identity(self.binary)
        self.bind(self.sources, self.binary, binary_identity, "compiled_reference_binary")
        self.counts["builds_completed"] = 1
        self.build = {"schema": SCHEMA, "kind": "build_receipt", "status": "passed",
            "compile_command": command, "binary": {"path": str(self.binary), **binary_identity},
            "source_revision": self.args.source_revision, "source_bindings": list(self.sources.values()),
            "process": process, "build_invocations": 1, "binary_executions": 0}
        self.run.write_json(directory / "receipt.json", self.build)

    def validate_payload(self, payload, checkpoint, point):
        self.require(payload["schema"] == "mumble_live_anchor_exact_audit_v1" and
            payload["status"] in ("available", "unavailable") and payload["source_id"] == self.closed["source_id"] and
            payload["prefix"] == checkpoint and self.common.same_vector(payload["x"], point) and
            payload["counts_complete"] is True and payload["sigma_V"] == .001,
            "Reference identity/status differs")
        self.require(all(payload[k] == 0 for k in ("optimizer_calls", "prior_calls", "truth_reads", "candidate_mutations")),
                     "Forbidden reference activity")
        for key in ("records_read", "records_accumulated", "model_steps", "model_predict_calls"):
            self.require(type(payload[key]) is int and 0 <= payload[key] <= checkpoint, "Reference count differs: " + key)
        self.require(type(payload["model_init_calls"]) is int and payload["model_init_calls"] in (0, 1) and
            payload["records_accumulated"] <= payload["model_predict_calls"] <= payload["model_steps"] <= payload["records_read"],
            "Reference chronology/count ownership differs")
        if payload["status"] == "available":
            self.require(all(payload[k] == checkpoint for k in
                ("records_read", "records_accumulated", "model_steps", "model_predict_calls")) and
                payload["model_init_calls"] == 1 and payload["stage"] == "complete" and payload["code"] == 0,
                "Available reference prefix is incomplete")
            self.run.finite(payload["likelihood_cost"], "reference cost")
            self.require(payload["likelihood_cost"] >= 0, "Negative reference cost")
            endpoint = payload["endpoint"]
            self.require(len(endpoint["v_V"]) == 3, "Reference endpoint dimension differs")
            for value in [endpoint["SOC"], *endpoint["v_V"], endpoint["h"], endpoint["elapsed_s"],
                          endpoint["charge_Ah"], endpoint["predicted_voltage_V"]]:
                self.run.finite(value, "reference endpoint")
        else:
            self.require(payload["likelihood_cost"] is None and payload["endpoint"] is None,
                         "Unavailable reference exposes a complete cost/endpoint")

    def evaluate(self, checkpoint):
        self.stage = "checkpoint_" + str(checkpoint)
        if checkpoint not in self.checkpoints:
            self.records.append({"next_index": checkpoint, "status": "missing_saved_checkpoint", "model_calls": 0})
            return
        selected = self.checkpoints[checkpoint]
        point = self.common.vector(selected["snapshot"]["x"], "saved candidate")
        trace_path = Path(self.closed["trace_directory"]) / self.capture.ORIGINAL
        with trace_path.open("rb") as handle:
            handle.seek(selected["byte_offset"])
            line = handle.read(selected["bytes"])
        self.require(len(line) == selected["bytes"] and hashlib.sha256(line).hexdigest() == selected["sha256"] and
                     self.common.strict_json(line) == selected["snapshot"], "Selected raw checkpoint differs")
        point_path = self.output / ("point_" + str(checkpoint) + ".txt")
        point_bytes = (" ".join(format(float(v), ".17g") for v in point) + "\n").encode()
        self.require(self.common.same_vector([float(s) for s in point_bytes.split()], point), "Point round trip differs")
        self.common.write_bytes(point_path, point_bytes)
        self.bind(self.inputs, point_path, self.run.identity(point_path), "saved_point_" + str(checkpoint))
        self.counts["audit_passes_reserved"] += 1
        self.counts["model_steps_reserved_upper_bound"] += checkpoint
        self.require(self.counts["audit_passes_reserved"] <= 3 and
                     self.counts["model_steps_reserved_upper_bound"] <= 1050000, "Frozen reference work cap")
        record = {"next_index": checkpoint, "status": "reserved", "x": point,
            "saved_checkpoint": {k: selected[k] for k in ("next_index", "line", "byte_offset", "bytes", "sha256")},
            "point_file": {"path": str(point_path), **self.run.identity(point_path)},
            "model_steps_reserved_upper_bound": checkpoint}
        self.records.append(record)
        directory = self.output / ("checkpoint_" + str(checkpoint))
        command = [str(self.binary), "--observations", str(self.observations), "--prefix", str(checkpoint),
                   "--point", str(point_path), "--source-id", self.closed["source_id"]]
        self.counts["model_counts_complete"] = False
        process, raw = self.child(directory, command, {"kind": "reference", **record})
        record["process"] = process
        payload = self.common.strict_json(raw)
        self.validate_payload(payload, checkpoint, point)
        record.update(status=payload["status"], payload=payload)
        for key in ("model_init_calls", "model_steps", "model_predict_calls"):
            self.counts[key + "_reported"] += payload[key]
        self.counts["audit_passes_completed"] += 1
        self.counts["model_counts_complete"] = True
        if payload["status"] == "available":
            snapshot = selected["snapshot"]
            record["comparison"] = {"represented_likelihood_cost": snapshot["likelihood_cost"],
                "exact_recurrence_likelihood_cost": payload["likelihood_cost"],
                "represented_minus_exact_cost": snapshot["likelihood_cost"] - payload["likelihood_cost"],
                "exact_minus_carried_endpoint": {
                    "SOC": payload["endpoint"]["SOC"] - snapshot["endpoint"]["SOC"],
                    "v_V": [a-b for a, b in zip(payload["endpoint"]["v_V"], snapshot["endpoint"]["v_V"])],
                    "h": payload["endpoint"]["h"] - snapshot["endpoint"]["h"]},
                "scope": "Computed same-decoded-input likelihood and endpoint at one saved point; no prior, optimization or global-fidelity/coverage inference."}
        self.run.write_json(directory / "result.json", record)

    def close(self):
        self.stage = "unchanged_inputs_and_audit_closure"
        try:
            self.common.rehash(self.sources)
            self.common.rehash(self.inputs)
            if self.closed:
                self.run.validate_closed_run(self.root,
                    {"bytes": self.args.outer_receipt_bytes, "sha256": self.args.outer_receipt_sha256},
                    read_observations=False)
            for row in self.records:
                if row.get("process"):
                    self.capture.load_verified(self.output / ("checkpoint_" + str(row["next_index"])),
                                               row["process"]["capture_commit_identity"])
            used = self.usage()
            self.require(used["CPU_total_s"] <= CAPS["CPU_s"] and used["wall_s"] <= CAPS["wall_s"] and
                         used["supervisor_peak_RSS_bytes"] <= CAPS["RSS_bytes"], "Postclosure audit resource cap")
        except Exception as error:
            self.errors.append({"stage": self.stage, "type": type(error).__name__, "message": str(error)[:2048]})
        status = "failed" if self.errors else "completed"
        result = {"schema": SCHEMA, "status": status, "source_revision": self.args.source_revision,
            "source_id": self.closed["source_id"] if self.closed else None,
            "audit_plan_sha256": PLAN_SHA256, "counts": dict(self.counts), "checkpoints": self.records,
            "build": self.build, "errors": self.errors, "candidate_status_unchanged": True,
            "coverage_validated": False, "candidate_promoted": False}
        self.run.write_json(self.output / "result.json", result)
        files = self.run.manifest(self.output)
        receipt = {"schema": SCHEMA, "status": status, "reference_transaction_closed": True,
            "source_revision": self.args.source_revision, "audit_plan_sha256": PLAN_SHA256,
            "source_bindings": list(self.sources.values()), "input_bindings": list(self.inputs.values()),
            "counts": dict(self.counts), "resources_before_final_receipt": self.usage(),
            "files": files, "closed_output_bytes_including_receipt": 0, "errors": self.errors,
            "original_candidate_status_unchanged": True, "truth_reads": 0,
            "partial_count_policy": "Reserved bounds remain durable; model_counts_complete=false means reported partial totals are lower bounds, never zero imputation."}
        for _ in range(24):
            size = sum(x["bytes"] for x in files.values()) + len(self.run.encode_json(receipt))
            if size > CAPS["closed_output_bytes"] and not any(x.get("message") == "Audit closed output cap" for x in self.errors):
                self.errors.append({"stage": "closure", "type": "ResourceFailure", "message": "Audit closed output cap"})
                receipt["status"] = "failed"
            if receipt["closed_output_bytes_including_receipt"] == size:
                break
            receipt["closed_output_bytes_including_receipt"] = size
        else:
            raise ValueError("Audit receipt byte accounting did not stabilize")
        self.run.write_json(self.output / "receipt.json", receipt)
        print(self.run.encode_json({"schema": SCHEMA, "status": receipt["status"],
            "receipt": {"path": str(self.output / "receipt.json"), **self.run.identity(self.output / "receipt.json")},
            "counts": self.counts, "errors": self.errors}).decode(), end="")
        return 0 if receipt["status"] == "completed" else 1

    def execute(self):
        self.common.reserve_directory(self.output)
        self.run.write_json(self.output / "reservation.json", {"schema": SCHEMA,
            "source_revision": self.args.source_revision, "audit_plan_sha256": PLAN_SHA256,
            "counts": dict(self.counts), "fixed_checkpoints": list(CHECKPOINTS), "caps": CAPS})
        try:
            self.preflight()
            self.compile()
            for checkpoint in CHECKPOINTS:
                self.evaluate(checkpoint)
        except Exception as error:
            self.errors.append({"stage": self.stage, "type": type(error).__name__, "message": str(error)[:2048]})
        return self.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--outer-receipt-sha256", required=True)
    parser.add_argument("--outer-receipt-bytes", type=int, required=True)
    return Audit(parser.parse_args()).execute()


if __name__ == "__main__":
    raise SystemExit(main())
