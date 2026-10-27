#!/usr/bin/env python3
"""Postclosure saved-trace reporting; never run a model, prior, or optimizer.

The parent must supply the independently pinned whole-process receipt SHA256.
Truth is inaccessible until the completed-run and original/copy capture gates
pass.  Importing this file performs no reporting or numerical evaluation.
"""
from __future__ import annotations

import argparse
import ast
import csv
import gzip
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import platform
import resource
import signal
import struct
import sys
import time
import zlib

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
EXP = "experiments/live_anchor_integration_001"
PLAN = EXP + "/reporting_plan.json"
RUNNER = "tools/run_live_anchor_integration.py"
SELF = "tools/report_live_anchor_integration.py"
SCHEMA = "mumble_live_anchor_reporting_v1"
STOP = {0: "none", 1: "round_limit", 2: "direction_unresolved",
        3: "no_admitted_trial", 4: "metric_unresolved", 5: "query_unavailable",
        6: "counter_limit", 7: "rounding_unresolved"}
N = 31501
WORK_KEYS = ("model_steps", "qr_rows", "query_evaluations", "prior_evaluations",
             "proposal_rounds", "accepted_steps")
DISPLAY = [("τ₁", "s", 1.), ("τ₂", "s", 1.), ("τ₃", "s", 1.),
           ("γ₊", "Ah⁻¹", 1.), ("γ₋", "Ah⁻¹", 1.), ("Capacity Q", "mAh", 1000.),
           ("R₀", "mΩ", 1000.), ("R₁", "mΩ", 1000.), ("R₂", "mΩ", 1000.),
           ("R₃", "mΩ", 1000.), ("H", "mV", 1000.), ("Entering SOC z₀", "%", 100.),
           ("Entering v₁", "mV", 1000.), ("Entering v₂", "mV", 1000.),
           ("Entering v₃", "mV", 1000.), ("Entering h₀", "1", 1.)]
CURRENT_DISPLAY = [("Current SOC", "%", 100.), ("Current v₁", "mV", 1000.),
                   ("Current v₂", "mV", 1000.), ("Current v₃", "mV", 1000.),
                   ("Current h", "1", 1.)]


def require(value, message):
    if not value:
        raise ValueError(message)


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "Duplicate JSON key: " + key)
        result[key] = value
    return result


def strict_json(data):
    def bad(value):
        raise ValueError("Nonfinite JSON constant: " + value)
    return json.loads(data, object_pairs_hook=pairs, parse_constant=bad)


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def identity(path):
    digest, size = hashlib.sha256(), 0
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
            size += len(block)
    return {"bytes": size, "sha256": digest.hexdigest()}


def fsync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_json(path, value):
    with Path(path).open("xb") as stream:
        stream.write(encode(value))
        stream.flush()
        os.fsync(stream.fileno())
    fsync_directory(Path(path).parent)


def finite_tree(value):
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {k: finite_tree(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [finite_tree(v) for v in value]
    return value


def load_verified_module(path, expected, name):
    require(identity(path) == expected, "Module source identity differs: " + str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_binding(rows, root, relative):
    target = (root / relative).resolve()
    found = [r for r in rows if Path(r["path"]).resolve() == target]
    require(len(found) == 1, "Missing/ambiguous pre-inference binding: " + relative)
    expected = {k: found[0][k] for k in ("bytes", "sha256")}
    require(identity(target) == expected, "Pre-inference source changed: " + relative)
    return expected


class Report:
    def __init__(self, args):
        self.args = args
        self.root, self.evidence = Path(args.root).resolve(), Path(args.evidence_root).resolve()
        self.output = Path(args.output_dir).resolve()
        require(self.root == ROOT, "Reporter source root differs")
        require(self.output == self.root / EXP / "reporting001", "Unexpected reporting destination")
        require(not self.output.exists(), "Reporting destination already exists; no overwrite or retry")
        self.output.mkdir()
        fsync_directory(self.output.parent)
        self.started, self.cpu_started = time.monotonic(), time.process_time()
        self.errors, self.inputs, self.stage = [], {}, "reservation"
        self.counts = {k: 0 for k in ("reporting_invocations", "saved_snapshot_decodes",
            "truth_literal_evaluations", "scalar_truth_record_reads", "journal_header_reads",
            "journal_record_reads", "closed_form_reference_evaluations", "truth_file_hash_passes",
            "truth_data_stream_opens", "observation_archive_opens", "model_calls", "prior_calls",
            "optimizer_calls", "source_generation_calls", "RNG_draws", "interval_calculations")}
        self.counts["reporting_invocations"] = 1
        self.plan = strict_json((self.root / PLAN).read_bytes())
        require(self.plan["schema"] == "mumble_live_anchor_reporting_plan_v1", "Reporting plan schema differs")
        require(self.plan["limits"] == {"CPU_s": 120, "RSS_bytes": 536870912,
            "closed_output_bytes": 100663296, "reporting_invocations": 1, "wall_s": 180}, "Reporting limits differ")
        self.gate, self.summary = None, None
        self.np, self.plt = None, None
        write_json(self.output / "reservation.json", {"schema": SCHEMA, "invocations": 1,
            "parent_outer_sha256": args.outer_sha256, "reporter": identity(Path(__file__)),
            "plan": identity(self.root / PLAN), "truth_read_before_closure": False})

    def remember(self, path, expected=None, truth=False):
        path = Path(path).resolve()
        if truth:
            self.counts["truth_file_hash_passes"] += 1
        actual = identity(path)
        if expected is not None:
            require(actual == expected, "Input identity differs: " + str(path))
        row = {"path": str(path), **actual, "truth_content": truth}
        require(str(path) not in self.inputs or self.inputs[str(path)] == row, "Conflicting input identity")
        self.inputs[str(path)] = row
        return actual

    def check_resources(self):
        now = self.resources()
        limits = self.plan["limits"]
        require(now["CPU_s"] <= limits["CPU_s"], "Reporting CPU cap exceeded")
        require(now["wall_s"] <= limits["wall_s"], "Reporting wall cap exceeded")
        require(now["own_peak_RSS_bytes"] <= limits["RSS_bytes"], "Reporting RSS cap exceeded")
        size = sum(p.stat().st_size for p in self.output.rglob("*") if p.is_file())
        require(size <= limits["closed_output_bytes"], "Reporting output cap exceeded")

    def resources(self):
        return {"CPU_s": time.process_time() - self.cpu_started,
                "wall_s": time.monotonic() - self.started,
                "own_peak_RSS_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) *
                    (1 if sys.platform == "darwin" else 1024)}

    def close_gate(self):
        self.stage = "completed_inference_and_capture_gate"
        outer_path = self.root / EXP / "execution_process/receipt.json"
        outer_id = self.remember(outer_path)
        require(outer_id["sha256"] == self.args.outer_sha256, "Parent-pinned outer receipt differs")
        outer = strict_json(outer_path.read_bytes())
        expected = source_binding(outer["source_bindings"], self.root, RUNNER)
        run = load_verified_module(self.root / RUNNER, expected, "postclosure_live_runner")
        self.gate = run.validate_closed_run(self.root, outer_id, read_observations=False)
        require(self.gate["observations_reopened"] is False, "Reporting reopened observations")
        for relative in (SELF, PLAN):
            self.remember(self.root / relative,
                source_binding(self.gate["inner"]["source_bindings"], self.root, relative))
        for relative, sha in self.plan["source_metadata_sha256"].items():
            actual = self.remember(self.root / relative)
            require(actual["sha256"] == sha, "Reporting source metadata differs: " + relative)
        self.remember(self.root / RUNNER, expected)
        for name in ("receipt.json", "result.json"):
            self.remember(self.root / EXP / "attempt001" / name)
        raw = run.common.load_capture().load_verified(self.gate["trace_directory"], self.gate["trace_commit_identity"])
        require(run.scan_trace(raw, self.gate["source_id"]) == self.gate["result"]["trace"],
                "Saved trace reduction differs from closed result")
        self.trace_id = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        self.run = run
        return raw

    def arrays(self, raw):
        self.stage = "saved_trace_decode"
        import numpy as np
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        self.np, self.plt = np, plt
        self.environment = {"python": sys.version, "platform": platform.platform(),
            "numpy": np.__version__, "matplotlib": matplotlib.__version__, "backend": matplotlib.get_backend()}
        self.x, self.current = np.empty((N, 16)), np.empty((N, 5))
        self.index = np.empty(N, dtype=np.int64)
        self.time_s, self.source_time = np.empty(N), np.empty(N)
        self.costs, self.slacks = np.empty((N, 3)), np.empty((N, 2))
        self.flags = np.empty((N, 5), dtype=np.int64)
        self.work = np.empty((N, 6), dtype=np.int64)
        k = 0
        for line in io.BytesIO(raw):
            row = strict_json(line)
            if row["kind"] not in ("initial", "block"):
                continue
            require(k < N, "Too many saved snapshots")
            self.index[k] = row["next_index"]
            self.x[k] = row["x"]
            endpoint = row["endpoint"]
            self.current[k] = [endpoint["SOC"], *endpoint["v_V"], endpoint["h"]]
            self.time_s[k], self.source_time[k] = row["elapsed_s"], row["source_elapsed_s"]
            self.costs[k] = [row["likelihood_cost"], row["prior_cost"], row["total_cost"]]
            self.slacks[k] = [endpoint["min_support_slack"], endpoint["min_endpoint_slack"]]
            self.flags[k] = [row["flags"], row["search_stop_reason"],
                -1 if row["last_fraction"] is None else row["last_fraction"],
                row["accepted_steps_in_block"], row["phase_and_flags"]]
            self.work[k] = [row["counts"][key] for key in WORK_KEYS]
            k += 1
        require(k == N and np.array_equal(self.index, np.arange(N) * 16), "Saved block grid differs")
        require(all(np.isfinite(a).all() for a in (self.x, self.current, self.time_s,
                    self.source_time, self.costs, self.slacks)), "Nonfinite saved trace")
        self.counts["saved_snapshot_decodes"] = k
        self.physical = self.x.copy()
        # Scalar libm transform matches the original-coordinate definition.
        for j in range(6):
            self.physical[:, j] = [math.exp(float(v)) for v in self.x[:, j]]
        require(np.isfinite(self.physical).all(), "Nonfinite physical parameter transform")

    def resolve_evidence(self, relative, optional=False):
        for base in (self.evidence, self.root):
            candidate = base / relative
            if candidate.is_file():
                return candidate
        if optional:
            return None
        raise FileNotFoundError("Required restored reporting evidence is absent: " + relative)

    def truth(self):
        self.stage = "postclosure_reference_decode"
        require(self.gate is not None and self.gate["outer"]["status"] == "completed", "Truth gate absent")
        np = self.np
        static = self.plan["static_truth"]
        source = (self.root / static["source"]).read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(source)).encode() + b"\0" + source).hexdigest()
        require(blob == static["git_blob_sha1"], "Static truth source Git blob differs")
        tree = ast.parse(source)
        assignments = [node.value for node in tree.body if isinstance(node, ast.Assign) and
            any(isinstance(target, ast.Name) and target.id == "CELLS" for target in node.targets)]
        require(len(assignments) == 1 and isinstance(assignments[0], ast.Dict), "Literal cell table differs")
        table = assignments[0]
        selected = [value for key, value in zip(table.keys, table.values)
                    if isinstance(key, ast.Constant) and key.value == "cell_b"]
        require(len(selected) == 1, "Selected cell literal missing/ambiguous")
        self.counts["truth_literal_evaluations"] += 1
        p = ast.literal_eval(selected[0])
        self.static_truth = np.asarray([*p["tau"], p["gamma_plus"], p["gamma_minus"], p["Q_Ah"],
             p["R0"], *p["R"], p["H"], p["z0"], *p["v0"], p["h0"]], dtype=float)
        require(self.static_truth.shape == (16,) and np.isfinite(self.static_truth).all(), "Invalid static references")
        self.reference = np.full((N, 5), np.nan)
        self.reference[0] = [p["z0"], *p["v0"], p["h0"]]
        self.q_truth = np.full(N, float(p["Q_Ah"]))
        scalar = self.plan["scalar_truth"]
        truth_path = self.resolve_evidence(scalar["path"])
        self.remember(truth_path, {k: scalar[k] for k in ("bytes", "sha256")}, truth=True)
        record = struct.Struct("<Qddd")
        self.counts["truth_data_stream_opens"] += 1
        with truth_path.open("rb") as stream:
            for k in range(1, N):
                n = int(self.index[k])
                stream.seek(record.size * (n - 1))
                data = stream.read(record.size)
                self.counts["scalar_truth_record_reads"] += 1
                require(len(data) == record.size, "Truncated scalar truth record")
                index, q, z, clean_v = record.unpack(data)
                require(index == n and all(math.isfinite(v) for v in (q, z, clean_v)), "Truth record index/value differs")
                require(struct.pack("<d", q) == struct.pack("<d", p["Q_Ah"]) and 0 <= z <= 1,
                        "Static capacity/scalar truth support mismatch")
                self.q_truth[k], self.reference[k, 0] = q, z
        require(self.counts["scalar_truth_record_reads"] == scalar["maximum_direct_record_reads"], "Scalar truth read cap/count differs")
        self.dense_truth(p)

    def dense_truth(self, p):
        spec = self.plan["optional_dense_current_truth"]
        path = self.resolve_evidence(spec["path"], optional=True)
        self.current_truth_status = {"SOC": "all_saved_points_from_scalar_truth",
            "v1_v2_v3_h": "initial_only_local_journal_unavailable", "journal_used": False,
            "reference_model": "original physical source, not redefined for decoded input"}
        if path is None:
            return
        self.remember(path, {k: spec[k] for k in ("bytes", "sha256")}, truth=True)
        manifest_path = self.resolve_evidence(spec["manifest_path"])
        self.remember(manifest_path, {"bytes": spec["manifest_bytes"], "sha256": spec["manifest_sha256"]})
        manifest = strict_json(manifest_path.read_bytes())
        require(manifest["cell"] == "cell_b" and manifest["fixture"] is False and
            manifest["rate_Hz"] == 35 and manifest["dt_s"] == 1. / 35., "Original source manifest differs")
        source_id = hashlib.sha256(json.dumps(manifest, sort_keys=True,
            separators=(",", ":"), allow_nan=False).encode()).digest()
        header, payload, check = struct.Struct("<8sIIQQ32s"), struct.Struct("<QII6d8d16s16sII32s"), struct.Struct("<II")
        def checked(data, size):
            require(len(data) == size + 8, "Truncated journal record")
            checksum, reserved = check.unpack(data[size:])
            require(reserved == 0 and checksum == zlib.crc32(data[:size]), "Journal CRC/reserved differs")
            return data[:size]
        self.counts["truth_data_stream_opens"] += 1
        with path.open("rb") as stream:
            self.counts["journal_header_reads"] += 1
            magic, version, record_bytes, begin, count, sid = header.unpack(checked(stream.read(72), 64))
            require((magic, version, record_bytes, begin, count, sid) ==
                (b"SCMSRC01", 1, 208, 0, 504001, source_id), "Journal header/source identity differs")
            for k, index in enumerate(self.index):
                stream.seek(72 + (int(index) - begin) * 208)
                fields = payload.unpack(checked(stream.read(208), 200))
                self.counts["journal_record_reads"] += 1
                n, event_index, within = fields[:3]
                require(n == int(index), "Journal record chronology differs")
                z, v, h = fields[3], list(fields[4:7]), fields[7]
                self.counts["closed_form_reference_evaluations"] += 1
                if within:
                    require(event_index < len(manifest["events"]), "Journal event index differs")
                    event = manifest["events"][event_index]
                    require(n == event["start_index"] + within, "Journal within-event chronology differs")
                    current, elapsed = event["current_A"], within * (1. / 35.)
                    z = z - current * elapsed / (3600. * p["Q_Ah"])
                    v = [r * current + (old - r * current) * math.exp(-elapsed / tau)
                         for r, tau, old in zip(p["R"], p["tau"], v)]
                    if current != 0:
                        target = 1. if current > 0 else -1.
                        gamma = p["gamma_plus"] if current > 0 else p["gamma_minus"]
                        h = target + (h - target) * math.exp(-gamma * abs(current) * elapsed / 3600.)
                require(all(math.isfinite(a) for a in [z, *v, h]) and 0 <= z <= 1 and -1 <= h <= 1,
                        "Journal reference is invalid")
                require(struct.pack("<d", z) == struct.pack("<d", float(self.reference[k, 0])),
                        "Closed-form journal SOC differs from indexed scalar truth")
                self.reference[k] = [z, *v, h]
        require(self.counts["journal_record_reads"] == spec["maximum_direct_record_reads"] and
                self.counts["closed_form_reference_evaluations"] == spec["maximum_closed_form_reference_evaluations"],
                "Optional reporting reference cap/count differs")
        self.current_truth_status.update(v1_v2_v3_h="all_saved_points_from_local_journal_closed_form", journal_used=True)

    def at(self, k):
        return {"next_index": int(self.index[k]), "source_elapsed_s": float(self.source_time[k]),
                "decoded_elapsed_s": float(self.time_s[k])}

    def stats(self, estimates, references, relative=False):
        np = self.np
        ref = np.broadcast_to(references, estimates.shape)
        error = 100. * (estimates / ref - 1.) if relative else estimates - ref
        good = np.isfinite(error)
        chosen = np.flatnonzero(good & (self.index > 0))
        result = {"reference_count_all": int(good.sum()), "reference_count_postinitial": int(len(chosen)),
            "initial_error": float(error[0]) if good[0] else None,
            "final_error": float(error[-1]) if good[-1] else None,
            "initial_estimate": float(estimates[0]), "final_estimate": float(estimates[-1]),
            "initial_reference": float(ref[0]) if math.isfinite(ref[0]) else None,
            "final_reference": float(ref[-1]) if math.isfinite(ref[-1]) else None,
            "exactly_unchanged_adjacent_estimate_count": int(np.count_nonzero(estimates[1:] == estimates[:-1])),
            "postinitial": None, "unchanged_count_is_not_convergence": True}
        if len(chosen):
            e = error[chosen]
            lo, hi, absolute = int(chosen[np.argmin(e)]), int(chosen[np.argmax(e)]), int(chosen[np.argmax(np.abs(e))])
            result["postinitial"] = {"minimum_signed": {"value": float(error[lo]), **self.at(lo)},
                "maximum_signed": {"value": float(error[hi]), **self.at(hi)},
                "maximum_absolute": {"value": float(abs(error[absolute])), "signed": float(error[absolute]), **self.at(absolute)},
                "mean_absolute": math.fsum(abs(float(v)) for v in e) / len(e),
                "RMS": math.sqrt(math.fsum(float(v) ** 2 for v in e) / len(e))}
        return result

    def target(self, error, threshold):
        np = self.np
        mask = np.isfinite(error) & (np.abs(error) <= threshold)
        hits = np.flatnonzero(mask & (self.index > 0))
        failures = np.flatnonzero(~mask & (self.index > 0))
        tail = (int(failures[-1]) + 1) if len(failures) else 1
        return {"inclusive_limit": threshold, "initial_prior_passes": bool(mask[0]),
                "postinitial_pass_count": int(mask[1:].sum()), "postinitial_points": N - 1,
                "final_passes": bool(mask[-1]), "first_saved_hit": self.at(int(hits[0])) if len(hits) else None,
                "first_all_remaining_saved_points_pass": self.at(tail) if tail < N else None,
                "interpretation": "Finite saved-grid screen only; no between-snapshot or eventual-convergence assertion."}

    def summarize(self):
        self.stage = "saved_data_statistics"
        np = self.np
        original = []
        for j, spec in enumerate(self.plan["original_quantities"]):
            row = {**spec, "native_error": self.stats(self.physical[:, j], self.static_truth[j])}
            if j <= 10 and self.static_truth[j] > 0:
                row["relative_percent_error"] = self.stats(self.physical[:, j], self.static_truth[j], relative=True)
            original.append(row)
        current = [{**spec, "native_error": self.stats(self.current[:, j], self.reference[:, j])}
                    for j, spec in enumerate(self.plan["current_quantities"])]
        q_error = 100. * (self.physical[:, 5] / self.q_truth - 1.)
        z_error = 100. * (self.current[:, 0] - self.reference[:, 0])
        targets = self.plan["point_error_requirements"]
        screens = {"Q_absolute_relative_percent": {name: self.target(q_error, limit)
                    for name, limit in targets["Q_absolute_relative_percent"].items()},
                   "current_SOC_absolute_pp": {name: self.target(z_error, limit)
                    for name, limit in targets["current_SOC_absolute_pp"].items()}}
        stop_counts = {str(key): {"name": name, "postinitial_count": int(np.count_nonzero(self.flags[1:, 1] == key))}
                       for key, name in STOP.items()}
        self.summary = {"schema": SCHEMA, "status": "completed", "inference_status": "completed",
            "source_revision": self.gate["source_revision"], "source_id": self.gate["source_id"],
            "snapshot_count": N, "grid": "0,16,...,504000; no interpolation", "initial_prior_reported_separately": True,
            "time": {"axis": "saved original source elapsed time", "final_source_s": float(self.source_time[-1]),
                "final_decoded_s": float(self.time_s[-1]),
                "max_abs_decoded_minus_source_s": float(np.max(np.abs(self.time_s - self.source_time)))},
            "original_quantities": original, "current_quantities": current, "current_reference_availability": self.current_truth_status,
            "targets": screens, "final_capacity_error_percent": float(q_error[-1]),
            "final_current_SOC_error_pp": float(z_error[-1]),
            "initial": {"physical_parameters": self.physical[0].tolist(), "current_state": self.current[0].tolist(),
                "current_truth": [None if not math.isfinite(v) else float(v) for v in self.reference[0]], **self.at(0)},
            "final": {"physical_parameters": self.physical[-1].tolist(), "current_state": self.current[-1].tolist(),
                "current_truth": [None if not math.isfinite(v) else float(v) for v in self.reference[-1]], **self.at(N-1)},
            "static_reference": self.static_truth.tolist(), "search": {"stop_reason_counts": stop_counts,
                "accepted_blocks": int(self.flags[1:, 3].sum()), "blocks_without_accepted_step": int((self.flags[1:, 3] == 0).sum()),
                "final_work_counts": dict(zip(WORK_KEYS, map(int, self.work[-1]))),
                "flags_histogram": {str(int(v)): int((self.flags[:, 0] == v).sum()) for v in np.unique(self.flags[:, 0])},
                "phase_flags_histogram": {str(int(v)): int((self.flags[:, 4] == v).sum()) for v in np.unique(self.flags[:, 4])}},
            "interpretation": self.plan["interpretation"], "coverage_validated": False, "candidate_promoted": False,
            "model_audits": "Separate frozen three-candidate audit; not invoked or inferred by this reporter.",
            "closure": {"outer": identity(self.root / EXP / "execution_process/receipt.json"),
                "inner": identity(self.root / EXP / "attempt001/receipt.json"),
                "result": identity(self.root / EXP / "attempt001/result.json"),
                "trace": self.trace_id, "trace_commit_identity": self.gate["trace_commit_identity"],
                "both_capture_copies_verified": True, "observations_reopened": False},
            "reporting_activity": dict(self.counts), "environment": self.environment}

    def write_trajectory(self):
        self.stage = "all_snapshot_export"
        names = [x["name"] for x in self.plan["original_quantities"]]
        current_names = [x["name"] for x in self.plan["current_quantities"]]
        headings = ["next_index", "source_elapsed_s", "decoded_elapsed_s"]
        headings += ["entering_x_" + str(j) for j in range(16)]
        for name in names + current_names:
            headings += [name + "_estimate", name + "_truth", name + "_signed_error"]
        headings += ["likelihood_cost", "prior_cost", "total_cost", "min_support_slack", "min_endpoint_slack",
                     "flags", "search_stop_reason", "last_fraction", "accepted_steps_in_block", "phase_and_flags"]
        headings += list(WORK_KEYS)
        with (self.output / "trajectory.csv.gz").open("xb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=6) as zipped:
                with io.TextIOWrapper(zipped, encoding="utf-8", newline="") as stream:
                    writer = csv.writer(stream, lineterminator="\n")
                    writer.writerow(headings)
                    for k in range(N):
                        row = [int(self.index[k]), float(self.source_time[k]), float(self.time_s[k]), *map(float, self.x[k])]
                        for j in range(16):
                            a, b = float(self.physical[k, j]), float(self.static_truth[j])
                            row += [a, b, a-b]
                        for j in range(5):
                            a, b = float(self.current[k, j]), float(self.reference[k, j])
                            row += [a, b if math.isfinite(b) else "", a-b if math.isfinite(b) else ""]
                        row += list(map(float, self.costs[k])) + list(map(float, self.slacks[k]))
                        row += list(map(int, self.flags[k])) + list(map(int, self.work[k]))
                        writer.writerow(row)
            raw.flush()
            os.fsync(raw.fileno())

    def figures(self):
        self.stage = "saved_trace_figures"
        plt, np = self.plt, self.np
        plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
            "axes.spines.right": False, "axes.grid": True, "grid.alpha": .20,
            "path.simplify": False, "svg.fonttype": "none", "savefig.facecolor": "white"})
        blue, orange = "#1665A7", "#C65D12"
        x = self.source_time / 60.
        self.figures_meta = []
        def save(fig, stem, title, dpi=220, early=False):
            fig.suptitle(title, fontsize=17, y=.995)
            fig.text(.01, .006, "Public initialization · all saved block endpoints · " +
                ("fixed first 120 seconds" if early else "full four-hour source timeline") +
                " · point estimates; no calibrated intervals", fontsize=9, color="#444444")
            fig.tight_layout(rect=(0, .027, 1, .945))
            fig.savefig(self.output / (stem + ".png"), dpi=dpi)
            fig.savefig(self.output / (stem + ".svg"))
            self.figures_meta.append({"stem": stem, "PNG_dpi": dpi, "snapshots_supplied":
                int(np.count_nonzero(self.source_time <= 120.)) if early else N,
                "smoothing": False, "time_axis": "saved source elapsed time", "fixed_early_window": early})
            plt.close(fig)
            self.check_resources()
        def setup(ax, label="Source elapsed time (min)", early=False):
            ax.set_xlabel(label)
            ax.set_xlim((0., 120.) if early else (0., 240.))
            ax.ticklabel_format(axis="y", style="plain", useOffset=False)
        for stem, coordinates, shape, size, title in (
            ("all16_parameters", range(16), (4, 4), (17, 13), "All 16 original entering quantities"),
            ("parameters_01_08", range(8), (2, 4), (17, 8), "Parameters 1–8: time constants, rates, capacity and resistance"),
            ("parameters_09_16", range(8, 16), (2, 4), (17, 8), "Parameters 9–16: remaining resistance and entering states")):
            fig, axes = plt.subplots(*shape, figsize=size, squeeze=False)
            for ax, j in zip(axes.flat, coordinates):
                name, unit, scale = DISPLAY[j]
                ax.plot(x, self.physical[:, j] * scale, color=blue, linewidth=1.15, label="Estimate")
                ax.axhline(self.static_truth[j] * scale, color=orange, linestyle="--", linewidth=1.25, label="Source reference")
                ax.plot(x[0], self.physical[0, j] * scale, "o", color=blue, markersize=3)
                ax.set_title(f"{j+1}. {name}", fontsize=11)
                ax.set_ylabel(unit)
                setup(ax)
            axes.flat[0].legend(fontsize=8, loc="best")
            save(fig, stem, title, dpi=250 if stem == "all16_parameters" else 220)
        fig, axes = plt.subplots(5, 1, figsize=(14, 14))
        for j, ax in enumerate(axes):
            name, unit, scale = CURRENT_DISPLAY[j]
            ax.plot(x, self.current[:, j] * scale, color=blue, linewidth=1.15, label="Estimate")
            known = np.isfinite(self.reference[:, j])
            if int(known.sum()) == N:
                ax.plot(x, self.reference[:, j] * scale, color=orange, linestyle="--", linewidth=1.25, label="Source reference")
            else:
                ax.plot(x[known], self.reference[known, j] * scale, "D", color=orange, markersize=4, label="Initial source reference")
                ax.text(.99, .93, "Later reference unavailable: local journal absent", ha="right", va="top", transform=ax.transAxes, fontsize=9)
            ax.set_title(name, loc="left"); ax.set_ylabel(unit); setup(ax)
            ax.legend(fontsize=8, loc="best")
        save(fig, "current_states", "Current physical state estimates and available source references")
        for early, stem in ((False, "capacity_SOC_overview"), (True, "early_capacity_SOC")):
            fig, axes = plt.subplots(2, 2, figsize=(15, 9))
            mask = self.source_time <= 120. if early else np.ones(N, dtype=bool)
            xx = self.source_time[mask] if early else x
            q, z = self.physical[mask, 5], self.current[mask, 0]
            qt, zt = self.q_truth[mask], self.reference[mask, 0]
            for ax, estimate, reference, title, unit, scale in (
                (axes[0, 0], q, qt, "Capacity", "mAh", 1000.),
                (axes[0, 1], z, zt, "Current SOC", "%", 100.)):
                ax.plot(xx, estimate*scale, color=blue, linewidth=1.3, label="Estimate")
                ax.plot(xx, reference*scale, color=orange, linewidth=1.3, linestyle="--", label="Source reference")
                ax.set_title(title); ax.set_ylabel(unit); ax.legend(fontsize=9)
            for ax, errors, label, limits in (
                (axes[1, 0], 100.*(q/qt-1.), "Capacity error (%)", self.plan["point_error_requirements"]["Q_absolute_relative_percent"]),
                (axes[1, 1], 100.*(z-zt), "SOC error (percentage points)", self.plan["point_error_requirements"]["current_SOC_absolute_pp"])):
                ax.plot(xx, errors, color=blue, linewidth=1.2, label="Signed point error")
                ax.axhline(0, color="#666666", linewidth=.6)
                for name, color, style in (("preferred", "#27804E", "--"), ("hard", "#A54C45", ":")):
                    for sign in (-1, 1):
                        ax.axhline(sign*limits[name], color=color, linestyle=style, linewidth=.9,
                                   label=f"Existing {name} ±{limits[name]:g}" if sign > 0 else None)
                ax.set_title(label); ax.set_ylabel(label); ax.legend(fontsize=8)
            for ax in axes.flat:
                setup(ax, "Source elapsed time (s)" if early else "Source elapsed time (min)", early)
            save(fig, stem, "Capacity and SOC: " + ("predeclared first two minutes" if early else "full saved trajectory"), early=early)
        fig, axes = plt.subplots(2, 1, figsize=(15, 8))
        axes[0].plot(x, self.work[:, 5], color=blue, linewidth=1.2)
        axes[0].set_ylabel("Cumulative accepted steps")
        axes[0].set_title("Saved acceptance count; a plateau is not a convergence test", loc="left")
        axes[1].plot(x, self.flags[:, 1], ".", color=blue, markersize=1.7)
        axes[1].set_yticks(list(STOP), [str(k)+": "+v.replace("_", " ") for k, v in STOP.items()], fontsize=8)
        axes[1].set_ylabel("Per-block stop reason")
        for ax in axes: setup(ax)
        save(fig, "optimization_trace", "Finite per-block search behavior")

    def finish(self):
        self.stage = "unchanged_input_and_output_closure"
        for row in self.inputs.values():
            if row["truth_content"]:
                self.counts["truth_file_hash_passes"] += 1
            require(identity(row["path"]) == {k: row[k] for k in ("bytes", "sha256")}, "Reporting input changed")
        # Revalidate immutable metadata and both capture copies, still skipping observations.
        self.run.validate_closed_run(self.root, self.summary["closure"]["outer"], read_observations=False)
        self.check_resources()
        self.summary["reporting_activity"] = dict(self.counts)
        self.summary["figures"] = self.figures_meta
        self.summary["inputs"] = list(self.inputs.values())
        self.summary["output_data"] = {p.name: identity(p) for p in sorted(self.output.iterdir()) if p.is_file() and p.name != "reservation.json"}
        self.summary["resources_before_summary_encoding"] = self.resources()
        write_json(self.output / "summary.json", self.summary)

    def receipt(self):
        if self.plt is not None:
            self.plt.close("all")
        try:
            self.check_resources()
        except Exception as error:
            self.errors.append({"stage": "final_resource_check", "type": type(error).__name__, "message": str(error)[:2048]})
        files = {p.relative_to(self.output).as_posix(): identity(p) for p in sorted(self.output.rglob("*")) if p.is_file()}
        receipt = {"schema": SCHEMA, "status": "failed" if self.errors else "completed", "stage": self.stage,
            "inference_status": None if self.gate is None else self.gate["outer"]["status"],
            "reporting_activity": self.counts, "errors": self.errors, "inputs": list(self.inputs.values()),
            "resources_before_final_encoding": self.resources(), "limits": self.plan["limits"],
            "resources_scope": "Own process through final receipt assembly; final encode/write/print latency excluded.",
            "files": files, "closed_output_bytes_including_receipt": 0,
            "model_prior_optimizer_calls": 0, "candidate_changed": False, "coverage_validated": False}
        base = sum(v["bytes"] for v in files.values())
        for _ in range(8):
            size = base + len(encode(finite_tree(receipt)))
            if receipt["closed_output_bytes_including_receipt"] == size:
                break
            receipt["closed_output_bytes_including_receipt"] = size
        require(receipt["closed_output_bytes_including_receipt"] == base + len(encode(finite_tree(receipt))), "Receipt byte accounting did not stabilize")
        if receipt["closed_output_bytes_including_receipt"] > self.plan["limits"]["closed_output_bytes"]:
            receipt["status"] = "failed"
            receipt["errors"].append({"stage": "receipt_closure", "type": "OutputCap", "message": "Closed reporting output exceeds frozen cap"})
            receipt["failure_only_emergency_closure"] = True
            for _ in range(8):
                receipt["closed_output_bytes_including_receipt"] = base + len(encode(finite_tree(receipt)))
        write_json(self.output / "reporting_receipt.json", finite_tree(receipt))
        print(json.dumps({"schema": SCHEMA, "status": receipt["status"],
            "receipt": identity(self.output / "reporting_receipt.json"),
            "summary": identity(self.output / "summary.json") if (self.output / "summary.json").exists() else None,
            "activity": self.counts}, sort_keys=True, allow_nan=False))
        return 0 if receipt["status"] == "completed" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--outer-sha256", required=True)
    args = parser.parse_args()
    require(len(args.outer_sha256) == 64 and all(c in "0123456789abcdef" for c in args.outer_sha256), "Invalid parent receipt SHA256")
    report = Report(args)
    def timeout(signum, frame):
        raise TimeoutError("Reporting wall cap reached")
    signal.signal(signal.SIGALRM, timeout)
    signal.setitimer(signal.ITIMER_REAL, report.plan["limits"]["wall_s"])
    try:
        raw = report.close_gate()
        report.arrays(raw)
        del raw
        report.check_resources()
        report.truth()
        report.summarize()
        report.write_trajectory()
        report.figures()
        report.finish()
    except Exception as error:
        report.errors.append({"stage": report.stage, "type": type(error).__name__, "message": str(error)[:4096]})
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    return report.receipt()


if __name__ == "__main__":
    raise SystemExit(main())
