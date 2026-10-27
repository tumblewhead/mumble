#!/usr/bin/env python3
"""One frozen retained-likelihood transaction; no learner, fitter or retry.

The parent uses only the standard library. The separately supervised worker
imports the qualified numerical stack after single-thread environment setup.
All observation model calls occur in at most four separately recorded C passes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import resource
import struct
import sys
import time
import traceback

sys.dont_write_bytecode = True
import run_conditional_belief_probe as common

EXP = "experiments/retained_likelihood_replacement_001"
PLAN = "plans/retained_likelihood_replacement_execution_001.json"
PLAN_SHA256 = "ad51d651ee68b1a19c1685f8486faa6c55e6d7ad21950fcfc2be42dc23aca3a1"
BASE = "f632c268f69ad10f856f761f5542c35d4d4c96fd"
FREE = "experiments/historical_likelihood_control_001/attempt002/free/stdout.json"
CONFIG = EXP + "/qualification/worker_configuration.json"
REVIEW = EXP + "/implementation_review.json"
REQUIRED_SOURCES = (
    PLAN, "tools/run_retained_likelihood_replacement.py",
    "tools/execute_retained_likelihood_replacement_once.py",
    "tools/run_conditional_belief_probe.py", EXP + "/stream_evaluator.c",
    EXP + "/replacement_math.py", EXP + "/solve_worker.py", CONFIG,
    EXP + "/evaluator_qualification.py", EXP + "/math_qualification.py",
    EXP + "/supervisor_qualification.py",
    EXP + "/qualification/evaluator_run001/receipt.json",
    EXP + "/qualification/evaluator_summary.json",
    EXP + "/qualification/math_attempt004.json",
    EXP + "/qualification/math_policy.json",
    EXP + "/qualification/worker_checks.json",
    EXP + "/qualification/supervisor_checks.json", REVIEW,
    "src/scm_model.c", "include/scm_model.h", "src/scm_hypothesis.c",
)
UNCHANGED_SOURCES = ("tools/run_conditional_belief_probe.py", "src/scm_model.c",
                     "include/scm_model.h", "src/scm_hypothesis.c")
EVALUATOR_SCHEMA = "mumble_retained_likelihood_stream_evaluator_v1"
COORDINATES = ["logtau1", "logtau2", "logtau3", "loggamma_plus", "loggamma_minus",
               "logQ", "R0", "R1", "R2", "R3", "H", "z", "v1", "v2", "v3", "h"]
GRAM_LAYOUT = "lower-packed-row-major: i*(i+1)/2+j for j<=i"
LIMITS = {"CPU_total_s_max": 30, "wall_total_s_max": 60,
          "child_RSS_bytes_max": 134217728, "supervisor_RSS_bytes_max": 134217728,
          "child_address_space_bytes_max": 1073741824,
          "child_stdout_stderr_bytes_max": 524288, "closed_output_bytes_max": 2097152}
THREAD_ENV = {key: "1" for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
                                     "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")}
require = common.require
digest = common.digest


def sha(data):
    return hashlib.sha256(data).hexdigest()


def finite_float(text):
    value = float(text)
    require(math.isfinite(value), "Nonfinite JSON exponent")
    return value


def strict_json(data):
    return json.loads(data, object_pairs_hook=common.unique_object,
                      parse_constant=common.reject_constant, parse_float=finite_float)


def number(value, name):
    require(type(value) in (int, float) and math.isfinite(value), "Expected finite number: " + name)
    return float(value)


def vector(values, length, name):
    require(isinstance(values, list) and len(values) == length, "Wrong shape: " + name)
    return [number(value, name) for value in values]


def gamma(k):
    ku = k * 2. ** -53
    require(0. <= ku < 1., "Invalid accumulation bound")
    return ku / (1. - ku)


def directory_manifest(directory):
    result = {}
    for path in sorted(directory.rglob("*")):
        require(not path.is_symlink(), "Unexpected symlink in output")
        if path.is_file():
            result[str(path.relative_to(directory))] = digest(path)
    return result


def scan_prefix(path, count, expected_sha=None):
    """Input-only sequential scan; no source generation, model or truth read."""
    require(type(count) is int and 0 <= count <= 252000, "Invalid prefix count")
    checksum = hashlib.sha256()
    charge = elapsed = low = high = max_current = 0.
    last = None
    with path.open("rb") as stream:
        for index in range(count):
            record = stream.read(32)
            require(len(record) == 32, "Short observation prefix")
            checksum.update(record)
            saved_index, dt, current, voltage = struct.unpack("<Qddd", record)
            require(saved_index == index, "Observation order/index mismatch")
            require(all(math.isfinite(item) for item in (dt, current, voltage)) and dt >= 0.,
                    "Invalid observation record")
            charge += current * dt / 3600.
            elapsed += dt
            require(math.isfinite(charge) and math.isfinite(elapsed), "Nonfinite prefix integral")
            low, high = min(low, charge), max(high, charge)
            max_current = max(max_current, abs(current))
            last = {"index": saved_index, "dt_s": dt, "current_A": current, "observed_voltage_V": voltage}
    actual = checksum.hexdigest()
    require(expected_sha is None or actual == expected_sha, "Original prefix hash mismatch")
    return {"prefix_records": count, "prefix_bytes": 32 * count, "prefix_sha256": actual,
            "charge_Ah": charge, "charge_min_Ah": low, "charge_max_Ah": high,
            "charge_extrema_include_initial_zero": True, "elapsed_physical_s": elapsed,
            "max_abs_current_A": max_current, "last_record": last,
            "model_calls": 0, "truth_reads": 0, "extra_records_read": 0}


def support(x, prior, prefix):
    x = vector(x, 16, "entering x")
    lower, upper = prior["entering_lower"], prior["entering_upper"]
    slacks = [x[i] - lower[i] for i in range(16)] + [upper[i] - x[i] for i in range(16)]
    capacity = math.exp(x[5])
    min_soc = x[11] - prefix["charge_max_Ah"] / capacity
    max_soc = x[11] - prefix["charge_min_Ah"] / capacity
    slacks.extend((min_soc, 1. - max_soc))
    require(all(math.isfinite(item) for item in slacks), "Nonfinite support calculation")
    return {"strictly_feasible": all(item >= 0. for item in slacks),
            "strictly_interior": all(item > 0. for item in slacks),
            "raw_slacks": slacks, "minimum_raw_slack": min(slacks),
            "minimum_SOC": min_soc, "maximum_SOC": max_soc,
            "arithmetic_allowance_used_for_admission": False}


def legacy_to_x(theta, alpha):
    theta, alpha = vector(theta, 7, "theta"), vector(alpha, 9, "alpha")
    require(alpha[4] > 0., "H must be positive for the supplied legacy anchor")
    return theta[:5] + [theta[6]] + alpha[:5] + [theta[5]] + alpha[5:8] + [alpha[8] / alpha[4]]


def x_to_legacy(x):
    return [x[i] for i in (0, 1, 2, 3, 4, 11, 5)], x[6:11] + x[12:15] + [x[10] * x[15]]


def mapped_legacy_gram(saved, x):
    """Remove legacy scales, then apply the full local H*h chain M'GM."""
    flat = vector(saved["joint_normal"], 256, "legacy full Gram")
    scales = vector(saved["coordinate_scales"], 16, "legacy scales")
    require(all(value > 0. for value in scales), "Nonpositive legacy scale")
    # columns[j] are the nonzero (legacy row, derivative) pairs for x_j.
    columns = [[] for _ in range(16)]
    for row, column in enumerate((0, 1, 2, 3, 4, 11, 5, 6, 7, 8, 9, 10, 12, 13, 14)):
        columns[column].append((row, 1.))
    columns[10].append((15, x[15]))
    columns[15].append((15, x[10]))
    mapped, abs_reference = [], []
    for i in range(16):
        for j in range(i + 1):
            terms = [di * dj * (flat[16 * r + c] / scales[r] / scales[c])
                     for r, di in columns[i] for c, dj in columns[j]]
            mapped.append(math.fsum(terms))
            abs_reference.append(math.fsum(abs(value) for value in terms))
    return mapped, abs_reference


def parity_check(saved, payload, x, count):
    expected, reference_abs = mapped_legacy_gram(saved, x)
    gram, gram_abs = payload["gram"], payload["absolute_summand_scales"]["gram"]
    factor = gamma(8 * count + 128)
    rows = []
    for index, (a, b, scale) in enumerate(zip(gram, expected, reference_abs)):
        allowance = factor * (gram_abs[index] + scale)
        error = abs(a - b)
        rows.append({"packed_index": index, "actual": a, "reference": b,
                     "absolute_error": error, "allowance": allowance, "passed": error <= allowance})
    original_cost = number(saved["objective_full"], "saved free cost")
    cost_allowance = factor * (abs(original_cost) + abs(payload["cost"]) + payload["absolute_summand_scales"]["cost"])
    cost_error = abs(payload["cost"] - original_cost)
    saved_soc = saved["theta"][5] - saved["charge_Ah"] / math.exp(saved["theta"][6])
    soc_error = abs(payload["endpoint_x"][11] - saved_soc)
    soc_allowance = gamma(64) * max(1., abs(saved["theta"][5]), abs(saved["charge_Ah"] / math.exp(saved["theta"][6])))
    return {"passed": all(row["passed"] for row in rows) and cost_error <= cost_allowance and soc_error <= soc_allowance,
            "cost": {"actual": payload["cost"], "reference": original_cost, "absolute_error": cost_error,
                     "allowance": cost_allowance, "passed": cost_error <= cost_allowance},
            "endpoint_SOC": {"actual": payload["endpoint_x"][11], "reference": saved_soc,
                             "absolute_error": soc_error, "allowance": soc_allowance, "passed": soc_error <= soc_allowance},
            "Gram": rows, "Gram_entries": 136,
            "scope": "Computed source-reconstruction check; not a rigorous real-model error certificate",
            "gradient_parity": "Unavailable: original fit did not save the corresponding full gradient"}


def validate_evaluator(payload, x, prefix):
    count = prefix["prefix_records"]
    expected = {"schema": EVALUATOR_SCHEMA, "status": "ok", "dimension": 16,
                "coordinate_names": COORDINATES, "sigma_V": .001, "gram_layout": GRAM_LAYOUT,
                "x": x, "prefix_requested": count, "records_read": count,
                "records_accumulated": count, "input_bytes_read": 32 * count,
                "model_init_calls": 1, "model_step_calls": count, "model_predict_calls": count,
                "source_generations": 0, "learner_ingests": 0, "fit_calls": 0, "truth_reads": 0,
                "charge_extrema_include_initial_zero": True}
    for key, value in expected.items():
        require(payload.get(key) == value, "Evaluator field mismatch: " + key)
    for key in ("charge_Ah", "charge_min_Ah", "charge_max_Ah", "elapsed_physical_s"):
        require(struct.pack("<d", number(payload[key], key)) == struct.pack("<d", prefix[key]),
                "Input-scan/evaluator bitwise integral mismatch: " + key)
    for key, length in (("gradient", 16), ("gram", 136), ("endpoint_x", 16), ("endpoint_state", 16),
                        ("endpoint_derivative", 256), ("endpoint_physical_derivative", 256)):
        vector(payload[key], length, key)
    require(number(payload["cost"], "cost") >= 0., "Negative likelihood cost")
    scales = payload["absolute_summand_scales"]
    require(number(scales["cost"], "cost accumulation scale") >= 0., "Negative accumulation scale")
    for key, size in (("gradient", 16), ("gram", 136)):
        require(all(value >= 0. for value in vector(scales[key], size, key)), "Negative absolute summand scale")
    if count:
        for key, value in prefix["last_record"].items():
            require(payload["last_record"][key] == value, "Final observation mismatch")
    return {"passed": True, "records": count, "model_steps": count,
            "cost": payload["cost"], "endpoint_Q_Ah": payload["endpoint_state"][5],
            "endpoint_SOC": payload["endpoint_state"][11], "fixed_workspace_bytes": payload["storage"]["workspace_sizeof_bytes"]}


def compare_candidates(frozen_audit, replacement_audit, prior_frozen, prior_replacement, count):
    lf, lr = frozen_audit["cost"], replacement_audit["cost"]
    pf, pr = number(prior_frozen, "frozen prior cost"), number(prior_replacement, "replacement prior cost")
    accumulation = gamma(8 * count + 64) * (frozen_audit["absolute_summand_scales"]["cost"]
                                               + replacement_audit["absolute_summand_scales"]["cost"])
    combination = gamma(8) * math.fsum([abs(lf), abs(lr), abs(pf), abs(pr)])
    allowance = accumulation + combination
    delta = math.fsum([lf, pf, -lr, -pr])
    decision = ("accepted_feasible_point_improvement" if delta > allowance else
                "retained_worse_replacement" if delta < -allowance else "retained_unresolved_cost_difference")
    return {"F_frozen": math.fsum([lf, pf]), "F_replacement": math.fsum([lr, pr]),
            "delta_frozen_minus_replacement": delta, "arithmetic_resolution_allowance": allowance,
            "computed_summand_accumulation_allowance": accumulation,
            "four_term_combination_allowance": combination, "decision": decision,
            "common_support_normalizer": "Omitted, cancels in this contrast",
            "scope": "Computed costs and fixed reported prior values; no real-model/libm/prior-evaluation certificate",
            "voltage_threshold": None, "truth_used": False, "MAP_or_optimum_claim": False}


def solver_markers(directory):
    rows = {}
    for name in ("frozen", "replacement"):
        rows[name] = {key: (directory / f"{name}.{suffix}.json").is_file()
                      for key, suffix in (("started", "started"), ("completed", "result"), ("exception", "exception"))}
    return {"per_solve": rows, "started_count": sum(row["started"] for row in rows.values()),
            "completed_count": sum(row["completed"] for row in rows.values()),
            "uncompleted_started_progress": "Unknown; never infer zero evaluations or retry"}


def validate_review(review, executable):
    require(review.get("status") == "passed" and review.get("canonical_invocations_before_review") == 0,
            "Implementation review did not pass before execution")
    require(review.get("plan_sha256") == PLAN_SHA256, "Review covers a different execution contract")
    reviewed = review.get("reviewed_source_sha256", {})
    for rel in REQUIRED_SOURCES:
        if rel != REVIEW:
            require(reviewed.get(rel) == executable["source_identities"][rel]["sha256"],
                    "Review covers a different or missing source: " + rel)


class Run:
    def __init__(self, args):
        self.start = time.monotonic()
        self.args, self.root = args, Path(args.root).resolve()
        self.output = common.argument_path(self.root, Path(args.output_dir))
        self.sources, self.inputs, self.generated = {}, {}, {}
        self.children, self.passes, self.payloads = [], [], {}
        self.outstanding_model_counts = set()
        self.plan = self.prior = self.prefix = self.saved_free = None
        self.stage, self.worker_launched = "reserve_output_directory", False
        self.counts = {"supervisor_invocations": 1, "model_passes_started": 0,
                       "model_passes_completed": 0, "model_steps_reported": 0,
                       "model_step_count_complete": True, "solver_invocations_reserved": 0,
                       "solver_started_markers": 0, "solver_results_saved": 0,
                       "learner_calls": 0, "fitter_calls": 0, "truth_reads": 0, "retries": 0}

    def usage(self):
        own = resource.getrusage(resource.RUSAGE_SELF)
        children = resource.getrusage(resource.RUSAGE_CHILDREN)
        return {"wall_s_through_snapshot": time.monotonic() - self.start,
                "CPU_self_s": own.ru_utime + own.ru_stime,
                "CPU_all_waited_children_s": children.ru_utime + children.ru_stime,
                "CPU_total_s": own.ru_utime + own.ru_stime + children.ru_utime + children.ru_stime,
                "supervisor_peak_RSS_bytes": common.own_peak_bytes(),
                "maximum_exact_child_peak_RSS_bytes": max((row["resources"]["peak_RSS_bytes"] for row in self.children), default=0),
                "CPU_scope": "RUSAGE_SELF plus every waited child, including git bookkeeping",
                "RSS_scope": "Supervisor and exact wait4 per execution child; concurrent children maximum one"}

    def check_budget(self):
        value = self.usage()
        for key in ("CPU_total_s", "supervisor_peak_RSS_bytes"):
            limit_key = "CPU_total_s_max" if key == "CPU_total_s" else "supervisor_RSS_bytes_max"
            require(value[key] <= LIMITS[limit_key], "Global resource limit: " + key)
        require(value["wall_s_through_snapshot"] <= LIMITS["wall_total_s_max"], "Global wall limit")
        total = sum(row["bytes"] for row in directory_manifest(self.output).values())
        require(total <= LIMITS["closed_output_bytes_max"], "Closed-output byte cap exceeded")
        return value

    def write(self, name, value, emergency_closure=False):
        path = self.output / name
        require(path.parent.is_dir(), "Output parent not reserved")
        used = sum(row["bytes"] for row in directory_manifest(self.output).values())
        # A cap failure cannot erase its own receipt. This bounded exception is
        # only for failed final closure; success still requires the total cap.
        limit = 524288 if emergency_closure else LIMITS["closed_output_bytes_max"] - used
        common.write_new_json(path, value, limit)
        return path

    def bind(self, records, path, expected=None, label=None):
        return common.bind_file(records, path, expected, label)

    def recheck(self):
        for records in (self.sources, self.inputs, self.generated):
            for saved in tuple(records.values()):
                self.bind(records, Path(saved["path"]), saved, saved["label"])
        self.check_budget()

    def x_file(self, name, x):
        path = self.output / name
        data = (" ".join(format(value, ".17g") for value in vector(x, 16, name)) + "\n").encode("ascii")
        with path.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        self.bind(self.generated, path, label=name)
        return path

    def preflight(self):
        self.stage = "preflight"
        require(re.fullmatch(r"[0-9a-f]{40}", self.args.source_revision) is not None, "Source revision must be a full commit ID")
        require(Path(__file__).resolve() == self.root / "tools/run_retained_likelihood_replacement.py", "Wrong supervisor location")
        require(Path(common.__file__).resolve() == self.root / "tools/run_conditional_belief_probe.py", "Wrong common supervisor import")
        plan_path = common.beneath(self.root, PLAN)
        self.bind(self.sources, plan_path, {"sha256": PLAN_SHA256}, PLAN)
        self.plan = strict_json(plan_path.read_bytes())
        require(self.plan["schema"] == "mumble_retained_likelihood_replacement_execution_contract_v1"
                and self.plan["status"] == "frozen_before_canonical_invocation" and self.plan["base_revision"] == BASE,
                "Unexpected frozen contract")
        for key, value in LIMITS.items():
            require(self.plan["resources"][key] == value, "Resource contract differs")
        require(self.plan["resources"]["thread_policy"] == THREAD_ENV, "Thread contract differs")
        os.environ.update(THREAD_ENV)
        os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
        receipt_path = common.argument_path(self.root, Path(self.args.executable_receipt))
        self.bind(self.inputs, receipt_path, label="executable receipt")
        executable = strict_json(receipt_path.read_bytes())
        require(executable["schema"] == "mumble_retained_replacement_executable_receipt_v1"
                and executable["status"] == "qualified_before_canonical_invocation", "Unqualified executable receipt")
        require(executable["source_revision"] == self.args.source_revision and executable["plan_sha256"] == PLAN_SHA256,
                "Executable source/plan identity mismatch")
        for rel in REQUIRED_SOURCES:
            path = common.beneath(self.root, rel)
            expected = executable["source_identities"][rel]
            self.bind(self.sources, path, expected, rel)
            committed = common.git_bytes(self.root, self.args.source_revision, rel)
            require(sha(committed) == expected["sha256"] and len(committed) == expected["bytes"], "Source commit mismatch: " + rel)
            if rel in UNCHANGED_SOURCES:
                require(common.git_bytes(self.root, BASE, rel) == committed, "Production/shared source changed: " + rel)
            self.check_budget()
        review = strict_json((self.root / REVIEW).read_bytes())
        validate_review(review, executable)
        for rel, expected in self.plan["inputs"]["metadata_identities"].items():
            path = common.beneath(self.root, rel)
            self.bind(self.inputs, path, expected, rel)
            require(sha(common.git_bytes(self.root, BASE, rel)) == expected["sha256"], "Historical metadata base mismatch")
        self.binary = common.beneath(self.root, executable["binary"]["path"])
        self.bind(self.sources, self.binary, executable["binary"], "qualified evaluator binary")
        require(os.access(self.binary, os.X_OK), "Evaluator is not executable")
        self.python = Path(sys.executable).resolve()
        require(str(self.python) == executable["python"]["path"] and sys.version == executable["python"]["version"],
                "Python runtime identity differs")
        self.bind(self.sources, self.python, executable["python"], "qualified Python executable")
        config = strict_json((self.root / CONFIG).read_bytes())
        require(config["schema"] == "mumble_surrogate_worker_configuration_v1", "Unexpected configuration export")
        require(config["numerical_policy"] == self.plan["solver_policy"], "Frozen solver policy/export differs")
        require(config["math_source_sha256"] == executable["source_identities"][EXP + "/replacement_math.py"]["sha256"],
                "Math configuration source differs")
        require(config["worker_source_sha256"] == executable["source_identities"][EXP + "/solve_worker.py"]["sha256"],
                "Worker configuration source differs")
        self.prior = config["prior"]
        evidence_root = Path(self.args.evidence_root).resolve()
        require(not self.output.is_relative_to(evidence_root), "Output overlaps immutable evidence")
        self.observations = common.beneath(evidence_root, self.plan["inputs"]["observation_member"])
        self.bind(self.inputs, self.observations, {"sha256": self.plan["inputs"]["observation_sha256"],
                                                 "bytes": self.plan["inputs"]["observation_bytes"]}, "original observations")
        self.prefix = scan_prefix(self.observations, self.plan["inputs"]["prefix_records"], self.plan["inputs"]["prefix_sha256"])
        require(self.prefix["prefix_bytes"] == self.plan["inputs"]["prefix_bytes"], "Prefix length mismatch")
        self.write("prefix_input.json", self.prefix)
        saved = strict_json((self.root / FREE).read_bytes())
        for key, value in {"case_id": "historical_likelihood_control_001/free", "method": "full", "modes": 3,
                           "sigma_V": .001, "samples": self.prefix["prefix_records"], "status": 0,
                           "fixed_mask": 0, "fixed_alpha_mask": 0, "joint_normal_dimension": 16}.items():
            require(saved[key] == value, "Unexpected historical free fit: " + key)
        self.saved_free = saved
        old = vector(self.prior["public_unsplit_mean"], 16, "public old anchor")
        new = legacy_to_x(saved["theta"], saved["alpha"])
        t_back, a_back = x_to_legacy(new)
        roundtrip_errors = [abs(a - b) for a, b in zip(t_back + a_back, saved["theta"] + saved["alpha"])]
        roundtrip_allowances = [gamma(64) * max(1., abs(a), abs(b)) for a, b in zip(t_back + a_back, saved["theta"] + saved["alpha"])]
        require(all(a <= b for a, b in zip(roundtrip_errors, roundtrip_allowances)), "Legacy anchor round-trip mismatch")
        anchors = {"old": {"x": old, "origin": "fixed public unsplit mean"},
                   "replacement": {"x": new, "origin": "supplied saved pure-likelihood free fit"},
                   "common_warm_start_x": new, "roundtrip_absolute_errors": roundtrip_errors,
                   "roundtrip_allowances": roundtrip_allowances, "truth_used": False,
                   "old_anchor_is_actual_recursive_history": False, "autonomous_anchor_selection": False}
        for name in ("old", "replacement"):
            anchors[name]["support"] = support(anchors[name]["x"], self.prior, self.prefix)
            require(anchors[name]["support"]["strictly_feasible"], "Anchor outside strict common support")
        self.write("anchors.json", anchors)
        self.old_x, self.new_x = old, new
        self.old_file = self.x_file("old_anchor_x.txt", old)
        self.new_file = self.x_file("replacement_anchor_x.txt", new)
        self.recheck()

    def child(self, name, command, kind):
        self.stage = name
        self.recheck()
        out = self.output / name
        out.mkdir(exist_ok=False)
        usage = self.check_budget()
        bounds = {"probe_CPU_s_max": LIMITS["CPU_total_s_max"] - usage["CPU_total_s"],
                  "probe_wall_s_max": LIMITS["wall_total_s_max"] - usage["wall_s_through_snapshot"],
                  "probe_address_space_bytes_max": LIMITS["child_address_space_bytes_max"],
                  "probe_peak_RSS_bytes_max": LIMITS["child_RSS_bytes_max"],
                  "probe_output_bytes_max": LIMITS["child_stdout_stderr_bytes_max"],
                  "supervisor_peak_RSS_bytes_max": LIMITS["supervisor_RSS_bytes_max"]}
        require(bounds["probe_CPU_s_max"] > 0. and bounds["probe_wall_s_max"] > 0., "No remaining child budget")
        self.write(name + "/launch.json", {"kind": kind, "command": command, "bounds": bounds,
                                            "utc": datetime.now(timezone.utc).isoformat(), "retry": False})
        if kind == "model":
            require(self.counts["model_passes_started"] < 4, "Model-pass budget exhausted")
            self.counts["model_passes_started"] += 1
            self.outstanding_model_counts.add(name)
            self.counts["model_step_count_complete"] = False
        else:
            require(not self.worker_launched, "Only one worker launch is permitted")
            self.worker_launched = True
            self.counts["solver_invocations_reserved"] = 2
        resources = common.supervise(command, out, bounds)
        (out / "raw_probe.json").rename(out / "stdout.json")
        (out / "probe.stderr").rename(out / "stderr.txt")
        row = {"id": name, "kind": kind, "resources": resources}
        self.children.append(row)
        self.write(name + "/resources.json", resources)
        if kind == "model":
            try:
                raw = strict_json((out / "stdout.json").read_bytes())
                steps = raw.get("model_step_calls")
                require(type(steps) is int and 0 <= steps <= self.prefix["prefix_records"], "Invalid attempted model-step count")
                self.counts["model_steps_reported"] += steps
                self.outstanding_model_counts.remove(name)
                self.counts["model_step_count_complete"] = not self.outstanding_model_counts
            except Exception:
                self.counts["model_step_count_complete"] = False
        else:
            marker = solver_markers(self.output / "solves")
            self.counts["solver_started_markers"] = marker["started_count"]
            self.counts["solver_results_saved"] = marker["completed_count"]
            self.write("solver_markers.json", marker)
        self.recheck()
        require(resources["exit_code"] == 0 and not resources["resource_violations"] and not resources["output_truncated"],
                "Child failed or exceeded a resource bound: " + name)
        return out

    def evaluate(self, name, x, path):
        feasible = support(x, self.prior, self.prefix)
        require(feasible["strictly_feasible"], "Candidate outside support before model call")
        out = self.child(name, [str(self.binary), "--x", str(path), "--sigma", "0.001",
                                "--observations", str(self.observations), "--prefix", str(self.prefix["prefix_records"])], "model")
        payload = strict_json((out / "stdout.json").read_bytes())
        validation = validate_evaluator(payload, x, self.prefix)
        self.write(name + "/validation.json", validation)
        self.bind(self.generated, out / "stdout.json", label=name + " evaluator output")
        self.payloads[name] = payload
        self.passes.append({"id": name, "path": str((out / "stdout.json").relative_to(self.output)), "validation": validation})
        self.counts["model_passes_completed"] += 1
        return payload

    def solve(self):
        out = self.child("solver_process", [str(self.python), "-B", str(self.root / EXP / "solve_worker.py"),
                "--old-block", str(self.output / "old_anchor/stdout.json"),
                "--new-block", str(self.output / "replacement_anchor/stdout.json"),
                "--warm", str(self.new_file), "--charge-min", format(self.prefix["charge_min_Ah"], ".17g"),
                "--charge-max", format(self.prefix["charge_max_Ah"], ".17g"),
                "--output-dir", str(self.output / "solves")], "surrogate_worker")
        stdout = strict_json((out / "stdout.json").read_bytes())
        require(stdout["status"] == "completed", "Worker completion receipt absent")
        pair_path = self.output / "solves/pair.json"
        pair = strict_json(pair_path.read_bytes())
        require(pair["schema"] == "mumble_replacement_surrogate_pair_v1" and pair["solves"] == 2
                and pair["starts_per_arm"] == 1 and pair["retries"] == 0
                and pair["model_calls"] == 0 and pair["observation_reads"] == 0, "Worker pair accounting mismatch")
        require(self.counts["solver_started_markers"] == self.counts["solver_results_saved"] == 2, "Incomplete per-solve markers")
        require(pair["prior"] == self.prior, "Prior changed between arms")
        policy = pair["policy"]
        for key, value in self.plan["solver_policy"].items():
            require(policy[key] == value, "Solver policy changed: " + key)
        hashed_policy = {k: v for k, v in policy.items() if k != "policy_sha256"}
        require(sha(json.dumps(hashed_policy, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()) == policy["policy_sha256"],
                "Pair policy hash mismatch")
        require(policy["coordinate_SD"] == self.prior["public_unsplit_sd"], "Coordinate scaling changed")
        for name in ("frozen", "replacement"):
            row = pair[name]
            require(row == strict_json((self.output / f"solves/{name}.result.json").read_bytes()), "Pair/result mismatch")
            require(row["name"] == name and row["warm_start_x"] == self.new_x, "Different common start")
            require(row["status"] in ("converged", "unresolved"), "Invalid candidate status for audit")
            feasible = support(row["candidate_x"], self.prior, self.prefix)
            require(feasible["strictly_feasible"] and row["feasibility"]["strictly_feasible"], "Infeasible surrogate candidate")
            counts = row["evaluation_counts"]
            require(type(counts["combined_objective_gradient"]) is int and 1 <= counts["combined_objective_gradient"] <= 1024
                    and type(counts["iterations"]) is int and 0 <= counts["iterations"] <= 100
                    and counts["final_verification"] == 1 and counts["model_calls"] == counts["observation_reads"] == 0,
                    "Solver call budget or accounting mismatch")
            converged = bool(row["optimizer"]["success"] and row["KKT"]["passed"])
            require((row["status"] == "converged") == converged, "Solver success bypasses independent KKT")
            number(row["prior_kernel_cost"], "prior cost")
        for path in (self.output / "solves").iterdir():
            if path.is_file():
                self.bind(self.generated, path, label="closed solver output " + path.name)
        self.recheck()
        return pair

    def execute(self):
        require(self.output == self.root / EXP / "attempt001", "Only the one canonical attempt001 destination is admitted")
        require(self.output.parent.is_dir(), "Experiment directory is absent")
        self.output.mkdir(exist_ok=False)
        result = {"schema": "mumble_retained_likelihood_replacement_result_v1", "status": "failed",
                  "source_revision": self.args.source_revision, "plan_sha256": PLAN_SHA256,
                  "passes": self.passes, "candidates": {}, "errors": [],
                  "coverage_validated": False, "candidate_promoted": False, "truth_reads": 0}
        try:
            self.write("started.json", {"schema": "mumble_retained_replacement_started_v1",
                "utc": datetime.now(timezone.utc).isoformat(), "argv": vars(self.args), "pid": os.getpid(),
                "supervisor_source": digest(Path(__file__)), "maximum_model_passes": 4,
                "maximum_surrogate_solves": 2, "retries": 0, "truth_reads": 0})
            self.preflight()
            result.update(source_id=self.plan["inputs"]["source_id"], prefix_records=self.prefix["prefix_records"],
                          input_summary="prefix_input.json", anchors="anchors.json")
            self.evaluate("old_anchor", self.old_x, self.old_file)
            replacement = self.evaluate("replacement_anchor", self.new_x, self.new_file)
            parity = parity_check(self.saved_free, replacement, self.new_x, self.prefix["prefix_records"])
            self.write("historical_parity.json", parity)
            require(parity["passed"], "Historical free-fit reconstruction parity failed")
            pair = self.solve()
            result["solver"] = {"output_dir": "solves", "pair_path": "solves/pair.json", "status": pair["status"],
                                "started_count": 2, "completed_count": 2, "policy_sha256": pair["policy"]["policy_sha256"]}
            for name in ("frozen", "replacement"):
                row = pair[name]
                result["candidates"][name] = {"x": row["candidate_x"], "solver_path": f"solves/{name}.result.json",
                    "audit_path": f"{name}_audit/stdout.json", "prior_kernel_cost": row["prior_kernel_cost"],
                    "solver_status": row["status"]}
                path = self.x_file(name + "_candidate_x.txt", row["candidate_x"])
                self.evaluate(name + "_audit", row["candidate_x"], path)
            comparison = compare_candidates(self.payloads["frozen_audit"], self.payloads["replacement_audit"],
                pair["frozen"]["prior_kernel_cost"], pair["replacement"]["prior_kernel_cost"], self.prefix["prefix_records"])
            self.recheck()
            accepted = comparison["decision"] == "accepted_feasible_point_improvement"
            prior_identity = digest(self.output / "solves/prior.json")
            ownership = {"source_id": self.plan["inputs"]["source_id"], "observation_indices": [0, self.prefix["prefix_records"]],
                         "interval_convention": "half-open", "cursor": self.prefix["prefix_records"],
                         "prior": prior_identity, "prior_copies": 1, "active_likelihood_blocks": 1}
            before = {**ownership, "generation": 0, "block": "old_anchor/stdout.json", "candidate": "frozen"}
            after = {**ownership, "generation": int(accepted),
                     "block": "replacement_anchor/stdout.json" if accepted else before["block"],
                     "candidate": "replacement" if accepted else "frozen"}
            result.update(status="completed", comparison=comparison,
                transaction={"decision": comparison["decision"], "accepted": accepted, "before": before, "after": after,
                             "old_block_archived": accepted, "prior_unchanged": True, "cursor_unchanged": True,
                             "posterior_multiplied_into_replayed_evidence": False,
                             "scope": "Host prototype transaction; no production estimator promotion"})
        except Exception as error:
            result["errors"].append({"stage": self.stage, "exception_type": type(error).__name__,
                                     "message": str(error), "traceback": traceback.format_exc()})
        result["counts"] = dict(self.counts)
        # All inferential children have ended before closure or reporting exists.
        self.stage = "close_receipt"
        try:
            self.check_budget()
        except Exception as error:
            result["status"] = "failed"
            result["errors"].append({"stage": self.stage, "message": str(error)})
            if "transaction" in result:
                result["transaction"]["accepted"] = False
                result["transaction"]["decision"] = "retained_resource_failure"
                result["transaction"]["after"] = result["transaction"]["before"]
                result["transaction"]["old_block_archived"] = False
        # Reserve enough closure space before reporting success. If a child
        # already exceeded the total cap, retain its bytes and a failed record.
        ordinary_bytes = sum(row["bytes"] for row in directory_manifest(self.output).values())
        if ordinary_bytes + 262144 > LIMITS["closed_output_bytes_max"]:
            result["status"] = "failed"
            result["errors"].append({"stage": self.stage, "message": "Insufficient ordinary output budget for bounded closure",
                                     "ordinary_bytes": ordinary_bytes, "closure_reservation_bytes": 262144})
            if "transaction" in result:
                result["transaction"]["accepted"] = False
                result["transaction"]["decision"] = "retained_resource_failure"
                result["transaction"]["after"] = result["transaction"]["before"]
                result["transaction"]["old_block_archived"] = False
        self.write("result.json", result, emergency_closure=result["status"] != "completed")
        files = directory_manifest(self.output)
        receipt = {"schema": "mumble_retained_likelihood_replacement_receipt_v1", "status": result["status"],
                   "canonical_inference_closed": True, "source_revision": self.args.source_revision,
                   "plan_sha256": PLAN_SHA256, "counts": self.counts, "truth_reads": 0,
                   "source_bindings": list(self.sources.values()), "input_bindings": list(self.inputs.values()),
                   "generated_input_and_solver_bindings": list(self.generated.values()),
                   "children": self.children, "files": files, "resources": self.usage(), "limits": LIMITS,
                   "closed_output_bytes_including_receipt": 0, "retries": 0,
                   "failure_only_emergency_closure": result["status"] != "completed",
                   "ordinary_output_cap_passed": ordinary_bytes <= LIMITS["closed_output_bytes_max"],
                   "closure": "Every inference child waited; manifests include all closed attempt files except this self-referential receipt. Resource snapshot follows manifest creation; final JSON encoding/fsync excluded from the internal time snapshot. No further inference or truth read by this process."}
        # Fix the receipt-size count without writing or replacing any prior file.
        others = sum(row["bytes"] for row in files.values())
        for _ in range(8):
            encoded = (json.dumps(receipt, indent=2, allow_nan=False) + "\n").encode()
            total = others + len(encoded)
            if receipt["closed_output_bytes_including_receipt"] == total:
                break
            receipt["closed_output_bytes_including_receipt"] = total
        require(result["status"] != "completed" or total <= LIMITS["closed_output_bytes_max"],
                "Successful receipt exceeds closed-output cap")
        self.write("receipt.json", receipt, emergency_closure=result["status"] != "completed")
        return {"status": result["status"], "result_path": str(self.output / "result.json"),
                "receipt_path": str(self.output / "receipt.json"), "counts": self.counts,
                "resources_after_internal_receipt_close": self.usage(),
                "decision": result.get("transaction", {}).get("decision"), "errors": result["errors"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--executable-receipt", default=EXP + "/executable_receipt.json")
    parser.add_argument("--output-dir", default=EXP + "/attempt001")
    args = parser.parse_args()
    try:
        result = Run(args).execute()
    except Exception as error:
        result = {"status": "failed_before_receipt", "exception_type": type(error).__name__, "message": str(error),
                  "no_retry": True}
    print(json.dumps(result, allow_nan=False))
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
