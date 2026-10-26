#!/usr/bin/env python3
"""Read-only audit of the frozen continuous-study evidence.

This program never imports the learner, generator, or old scorer. It reads the
three exact archived files named by plans/weighting_output_diagnostic_001.json.
Truth is used only after reconstructing recorded output and score identities.
The plan fixes the scope, limits, and tolerances before this audit is executed.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import csv
import hashlib
import json
import math
import mmap
from pathlib import Path
import platform
import resource
import signal
import struct
import sys
import time


PLAN_PATH = "plans/weighting_output_diagnostic_001.json"
PLAN_SHA256 = "7ca80896fb0e56fb649fbbb34a4fbaf6b8b2771b1aa84f544b6d968a99025480"
BASE = "experiments/continuous_learning_validation_001/implementation/"
METRIC = struct.Struct("<Q7dQiI")
TRUTH = struct.Struct("<Qddd")
FAILURE_FLAGS = 2 | 4 | 8 | 16
ENTITY_NAMES = ("aggregate", "component0", "component1")


class AuditFailure(RuntimeError):
    """A preserved input, accounting, or resource failure; never retuned."""


def finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def json_safe(value):
    """Keep nonfinite failure diagnostics reportable with strict JSON."""
    if isinstance(value, float) and not math.isfinite(value):
        return repr(value)
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def weighted_magnitude(value, root_weight, log_root_weight):
    """The live query's subnormal-root fallback, applied to marginal terms."""
    magnitude = abs(value)
    if magnitude == 0:
        return 0.0
    if root_weight >= sys.float_info.min:
        return root_weight * magnitude
    return math.exp(math.log(magnitude) + log_root_weight)


def peak_rss_bytes():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value * 1024)


def strict_loads(text):
    def reject(value):
        raise AuditFailure("Nonstandard JSON numeric constant: " + value)
    return json.loads(text, parse_constant=reject)


def normalized_weights(logw):
    """Match the live query's normalized linear weights, retaining log odds."""
    a, b = map(math.exp, logw)
    total = a + b
    if not finite(total) or total <= 0:
        raise AuditFailure("Nonpositive/nonfinite weight normalization")
    return a / total, b / total


def log_normalization(logw):
    maximum = max(logw)
    return maximum + math.log(math.exp(logw[0] - maximum) +
                              math.exp(logw[1] - maximum))


def odds(logw):
    return logw[1] - logw[0]


def dominant(value):
    return 1 if value > 0 else 0 if value < 0 else None


def score_terms(components):
    r = [c["last_innovation_V"] for c in components]
    s = [c["last_innovation_variance_V2"] for c in components]
    if not all(finite(x) for x in r + s) or min(s) <= 0:
        raise AuditFailure("Nonfinite innovation or nonpositive innovation variance")
    nis = [r[j] * r[j] / s[j] for j in range(2)]
    ell = [-0.5 * math.log(s[j]) - 0.5 * nis[j] for j in range(2)]
    variance = 0.5 * math.log(s[0] / s[1])
    residual = 0.5 * (nis[0] - nis[1])
    return r, s, nis, ell, variance, residual


def midpoint_motion(before, after):
    p0, p1 = before["weight1"], after["weight1"]
    e0, e1 = before["component_SOC_errors_pp"], after["component_SOC_errors_pp"]
    midpoint = 0.5 * (p0 + p1)
    component = ((1 - midpoint) * (e1[0] - e0[0]) +
                 midpoint * (e1[1] - e0[1]))
    weight = (p1 - p0) * 0.5 * ((e0[1] - e0[0]) + (e1[1] - e1[0]))
    observed = after["aggregate_SOC_error_pp"] - before["aggregate_SOC_error_pp"]
    return {"observed_SOC_error_change_pp": observed,
            "component_error_motion_pp": component,
            "weight_motion_pp": weight,
            "reconstructed_change_pp": component + weight,
            "weight_motion_fraction_of_signed_change": weight / observed if observed else None,
            "identity": "(1-p_bar)*delta_e0+p_bar*delta_e1+delta_p*(gap_before+gap_after)/2",
            "scope": "Exact midpoint attribution of saved output-error motion; not a causal explanation of predictive preference."}


class Checks:
    def __init__(self):
        self.groups = {}
        self.mismatches = []

    def compare(self, group, actual, expected, atol, rtol=0.0, location=None):
        row = self.groups.setdefault(group, {"comparisons": 0, "max_abs_error": 0.0,
                                           "max_error_over_limit": 0.0,
                                           "at_max_abs_error": None})
        row["comparisons"] += 1
        valid = finite(actual) and finite(expected)
        error = abs(actual - expected) if valid else None
        limit = max(atol, rtol * max(abs(actual), abs(expected))) if valid else atol
        if valid and error >= row["max_abs_error"]:
            row["max_abs_error"] = error
            row["at_max_abs_error"] = location
        if valid:
            row["max_error_over_limit"] = max(row["max_error_over_limit"],
                                               error / limit if limit else (0 if error == 0 else math.inf))
        if not valid or error > limit:
            mismatch = {"check": group, "location": location, "actual": actual,
                        "expected": expected, "absolute_error": error,
                        "absolute_tolerance": atol, "relative_tolerance": rtol,
                        "effective_limit": limit}
            self.mismatches.append(mismatch)
            raise AuditFailure("Numeric mismatch: " + group + " at " + str(location))

    def require(self, condition, name, detail=None):
        if not condition:
            self.mismatches.append({"check": name, "detail": detail})
            raise AuditFailure(name + ": " + str(detail))


class Budget:
    def __init__(self, bounds, started):
        self.bounds = bounds
        self.started = started
        self.written = 0

    def check(self):
        if time.monotonic() - self.started > self.bounds["audit_wall_s_max"]:
            raise AuditFailure("Frozen wall-time limit exceeded")
        if peak_rss_bytes() > self.bounds["audit_peak_RSS_bytes_max"]:
            raise AuditFailure("Frozen own-process RSS limit exceeded")

    def add(self, count):
        # Reserve space for the mandatory success/failure receipt.
        if self.written + count > self.bounds["audit_output_bytes_max"] - 131072:
            raise AuditFailure("Derived-output limit would be exceeded")
        self.written += count


class CountedWriter:
    def __init__(self, file, budget):
        self.file, self.budget = file, budget

    def write(self, text):
        self.budget.add(len(text.encode("utf-8")))
        return self.file.write(text)


def digest_file(path, expected_bytes=None, git_blob=False):
    size = path.stat().st_size
    if expected_bytes is not None and size != expected_bytes:
        raise AuditFailure("Byte-count mismatch: " + str(path))
    sha256 = hashlib.sha256()
    sha1 = hashlib.sha1(("blob " + str(size) + "\0").encode()) if git_blob else None
    with path.open("rb") as source:
        while chunk := source.read(1 << 20):
            sha256.update(chunk)
            if sha1:
                sha1.update(chunk)
    result = {"bytes": size, "sha256": sha256.hexdigest()}
    if sha1:
        result["git_blob_sha1"] = sha1.hexdigest()
    return result


class BinaryRows:
    def __init__(self, metrics, truth, checks):
        self.metrics, self.truth, self.checks = metrics, truth, checks
        checks.require(len(metrics) % METRIC.size == 0, "metric_extent")
        checks.require(len(truth) % TRUTH.size == 0, "truth_extent")
        self.count = len(metrics) // METRIC.size
        checks.require(self.count == len(truth) // TRUTH.size, "binary_record_count")

    def metric(self, n):
        self.checks.require(1 <= n <= self.count, "metric_index_range", n)
        values = METRIC.unpack_from(self.metrics, (n - 1) * METRIC.size)
        self.checks.require(values[0] == n, "metric_index_identity", {"requested": n, "stored": values[0]})
        self.checks.require(values[9] == 0 and not values[10] & FAILURE_FLAGS,
                            "valid_scalar_transaction", {"index": n, "code": values[9], "flags": values[10]})
        self.checks.require(values[8] & 3 == 3, "available_scalar_SOC_and_capacity", n)
        self.checks.require(all(finite(v) for v in values[1:8]), "finite_scalar_fields", n)
        self.checks.require(values[6] <= 0 and values[7] <= 0, "normalized_log_weight_sign", n)
        return values

    def actual_truth(self, n):
        self.checks.require(1 <= n <= self.count, "truth_index_range", n)
        values = TRUTH.unpack_from(self.truth, (n - 1) * TRUTH.size)
        self.checks.require(values[0] == n, "truth_index_identity", {"requested": n, "stored": values[0]})
        self.checks.require(all(finite(v) for v in values[1:]) and values[1] > 0,
                            "finite_truth_fields", n)
        return values


def interval_record(label, quantity, point, truth, limits, available, index):
    valid = bool(available and all(finite(x) for x in [point, truth] + list(limits)))
    if valid and limits[0] > limits[1]:
        raise AuditFailure("Reversed local interval")
    return {"entity": label, "quantity": quantity, "next_index": index,
            "available": valid, "point": point, "truth": truth, "interval": list(limits),
            "own_point_contained": limits[0] <= point <= limits[1] if valid else None,
            "truth_contained": limits[0] <= truth <= limits[1] if valid else None}


def count_interval(counts, record, checks):
    key = record["entity"] + "/" + record["quantity"]
    row = counts.setdefault(key, {"queries": 0, "available": 0,
                                 "own_point_contained": 0, "truth_contained": 0})
    row["queries"] += 1
    if record["available"]:
        row["available"] += 1
        row["own_point_contained"] += int(record["own_point_contained"])
        row["truth_contained"] += int(record["truth_contained"])
        checks.require(record["own_point_contained"], "own_point_inside_matching_interval", record)


def audit_endpoints(extraction, checks):
    records, counts = [], {}
    for arm, description in extraction["arms"].items():
        endpoint = description["endpoint"]
        entities = endpoint["entities"]
        checks.require(tuple(e["label"] for e in entities) == ENTITY_NAMES, "endpoint_entity_identity", arm)
        for entity in entities:
            available = entity["valid_for_useful_scoring"] and entity["local_ranges_available"]
            for quantity, point, truth, limits, availability in (
                ("SOC", entity["raw_SOC"], endpoint["truth_SOC"], entity["local_SOC_interval"], entity["point_available"]),
                ("Q_Ah", entity["raw_Q_Ah"], endpoint["truth_Q_Ah"], entity["local_Q_interval_Ah"], entity["capacity_available"])):
                row = interval_record(entity["label"], quantity, point, truth, limits,
                                      available and availability, endpoint["next_index"])
                row["arm"] = arm
                count_interval(counts, row, checks)
                records.append(row)
    checks.require(len(records) == 24, "endpoint_audit_count", len(records))
    return {"checks": len(records), "records": records, "counts": counts,
            "scope": "Four published endpoints, three matching entities, two quantities. Shared A suffixes are not independent replications."}


def verify_query(q, binaries, tolerance, checks, interval_counts):
    n = q["next_index"]
    components, aggregate = q["components"], q["aggregate"]
    checks.require(q["event"] == "query" and q["schema"] == "mumble_continuous_query_v1", "query_schema", n)
    checks.require(len(components) == 2 and [c["component"] for c in components] == [0, 1], "component_identity", n)
    checks.require(q["current_score_attempt"] and q["score_transaction_accepted"] and
                   q["last_rejection_stage_code"] == 0, "query_accepted_score", n)
    metric, truth = binaries.metric(n), binaries.actual_truth(n)
    entities = [aggregate] + components
    for label, entity in zip(ENTITY_NAMES, entities):
        checks.require(entity["next_index"] == n and not entity["flags"] & FAILURE_FLAGS,
                       "query_entity_index_and_validity", {"index": n, "entity": label})
        checks.require(len(entity["mean"]) == 16 and len(entity["coordinate_sd"]) == 16,
                       "query_coordinate_count", {"index": n, "entity": label})
        checks.require(all(finite(v) for v in entity["mean"] + entity["coordinate_sd"]) and
                       min(entity["coordinate_sd"]) >= 0, "finite_query_moments", n)
    checks.compare("query_elapsed", q["elapsed_s"], metric[1], tolerance["moment_abs"],
                   tolerance["moment_rel"], n)
    logw = q["log_weights"]
    checks.require(len(logw) == 2 and all(finite(v) and v <= 0 for v in logw), "query_log_weights", n)
    checks.compare("weight_log_normalization", log_normalization(logw), 0,
                   tolerance["query_old_weight_abs"], location=n)
    wa, wb = normalized_weights(logw)
    r, variances, nis, reconstructed_ell, variance_term, residual_term = score_terms(components)
    recorded_ell = q["pre_correction_log_likelihood"]
    checks.require(len(recorded_ell) == 2 and all(finite(x) for x in recorded_ell), "finite_recorded_scores", n)
    for j in range(2):
        checks.compare("predictive_score", recorded_ell[j], reconstructed_ell[j],
                       tolerance["log_score_abs"], location=[n, j])
    score_delta = recorded_ell[1] - recorded_ell[0]
    checks.compare("score_term_decomposition", variance_term + residual_term, score_delta,
                   tolerance["log_score_abs"], location=n)
    actual_increment, recurrence_error = None, None
    if n < binaries.count:
        following = binaries.metric(n + 1)
        for j in range(2):
            checks.compare("query_to_next_metric_old_weight", logw[j], following[6 + j],
                           tolerance["query_old_weight_abs"], location=[n, j])
        actual_increment = odds(following[6:8]) - odds(metric[6:8])
        recurrence_error = abs(actual_increment - score_delta)
        checks.compare("log_odds_recurrence", actual_increment, score_delta,
                       tolerance["log_odds_increment_abs"], location=n)
    total = math.exp(logw[0]) + math.exp(logw[1])
    log_roots = [0.5 * value - 0.5 * math.log(total) for value in logw]
    roots = [math.exp(value) for value in log_roots]
    for i in range(16):
        mean = wa * components[0]["mean"][i] + wb * components[1]["mean"][i]
        sd = math.hypot(weighted_magnitude(components[0]["coordinate_sd"][i], roots[0], log_roots[0]),
                        weighted_magnitude(components[0]["mean"][i] - mean, roots[0], log_roots[0]),
                        weighted_magnitude(components[1]["coordinate_sd"][i], roots[1], log_roots[1]),
                        weighted_magnitude(components[1]["mean"][i] - mean, roots[1], log_roots[1]))
        checks.compare("aggregate_mean", aggregate["mean"][i], mean,
                       tolerance["moment_abs"], tolerance["moment_rel"], [n, i])
        checks.compare("aggregate_sd", aggregate["coordinate_sd"][i], sd,
                       tolerance["moment_abs"], tolerance["moment_rel"], [n, i])
    all_limits = []
    for label, entity in zip(ENTITY_NAMES, entities):
        soc, logq = entity["mean"][11], entity["mean"][5]
        cap = math.exp(logq)
        expected = [soc - 2 * entity["coordinate_sd"][11], soc + 2 * entity["coordinate_sd"][11],
                    math.exp(logq - 2 * entity["coordinate_sd"][5]),
                    math.exp(logq + 2 * entity["coordinate_sd"][5])]
        checks.compare("raw_SOC_center", entity["raw_soc"], soc,
                       tolerance["moment_abs"], tolerance["moment_rel"], [n, label])
        checks.compare("raw_capacity_center", entity["raw_capacity_Ah"], cap,
                       tolerance["moment_abs"], tolerance["moment_rel"], [n, label])
        if entity["point_available"]:
            checks.compare("reported_SOC_center", entity["current_soc"], soc,
                           tolerance["moment_abs"], tolerance["moment_rel"], [n, label])
        if entity["capacity_available"]:
            checks.compare("reported_capacity_center", entity["capacity_Ah"], cap,
                           tolerance["moment_abs"], tolerance["moment_rel"], [n, label])
        actual = [entity[k] for k in ("soc_local_lower", "soc_local_upper",
                                     "capacity_local_lower_Ah", "capacity_local_upper_Ah")]
        if entity["local_ranges_available"]:
            for j in range(4):
                checks.compare("matching_local_interval", actual[j], expected[j],
                               tolerance["interval_abs"], tolerance["interval_rel"], [n, label, j])
        for quantity, point, actual_truth, limits, available in (
                ("SOC", soc, truth[2], actual[:2], entity["point_available"]),
                ("Q_Ah", cap, truth[1], actual[2:], entity["capacity_available"])):
            record = interval_record(label, quantity, point, actual_truth, limits,
                                     available and entity["local_ranges_available"], n)
            count_interval(interval_counts, record, checks)
        all_limits.append(expected)
    hull = [min(all_limits[1][0], all_limits[2][0]), max(all_limits[1][1], all_limits[2][1]),
            min(all_limits[1][2], all_limits[2][2]), max(all_limits[1][3], all_limits[2][3])]
    for i in range(4):
        checks.compare("all_component_hull", q["all_component_hull"][i], hull[i],
                       tolerance["interval_abs"], tolerance["interval_rel"], [n, i])
    if aggregate["prediction_available"]:
        prediction = wa * components[0]["predicted_voltage_V"] + wb * components[1]["predicted_voltage_V"]
        checks.compare("weighted_filtered_voltage", aggregate["predicted_voltage_V"], prediction,
                       tolerance["moment_abs"], tolerance["moment_rel"], n)
    checks.compare("query_scalar_SOC", aggregate["raw_soc"], metric[2],
                   tolerance["moment_abs"], tolerance["moment_rel"], n)
    checks.compare("query_scalar_capacity", aggregate["raw_capacity_Ah"], metric[3],
                   tolerance["moment_abs"], tolerance["moment_rel"], n)
    errors = [100 * (e["raw_soc"] - truth[2]) for e in entities]
    qerrors = [100 * (e["raw_capacity_Ah"] / truth[1] - 1) for e in entities]
    return {"next_index": n, "nominal_time_s": n / 35, "log_odds_post": odds(logw),
            "weight1": wb, "ell0": recorded_ell[0], "ell1": recorded_ell[1],
            "score_delta": score_delta, "variance_score_term": variance_term,
            "residual_score_term": residual_term, "stored_log_odds_increment": actual_increment,
            "recurrence_abs_error": recurrence_error,
            "innovation0_mV": 1000 * r[0], "innovation1_mV": 1000 * r[1],
            "innovation_sd0_mV": 1000 * math.sqrt(variances[0]),
            "innovation_sd1_mV": 1000 * math.sqrt(variances[1]),
            "NIS0": nis[0], "NIS1": nis[1],
            "aggregate_SOC_error_pp": errors[0], "component0_SOC_error_pp": errors[1],
            "component1_SOC_error_pp": errors[2], "aggregate_Q_error_percent": qerrors[0],
            "component0_Q_error_percent": qerrors[1], "component1_Q_error_percent": qerrors[2],
            "component0_limited_mask": components[0]["last_limited_mask"],
            "component1_limited_mask": components[1]["last_limited_mask"],
            "component0_blocked_mask": components[0]["last_blocked_mask"],
            "component1_blocked_mask": components[1]["last_blocked_mask"],
            "component0_gain_min": components[0]["last_gain_scale"],
            "component1_gain_min": components[1]["last_gain_scale"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-revision", help="Externally recorded frozen audit source commit; no subprocess is invoked.")
    args = parser.parse_args(argv)
    root, evidence_root, output = args.root.resolve(), args.evidence_root.resolve(), args.output_dir.resolve()
    if root == evidence_root:
        parser.error("Evidence must be restored to a separate root")
    if output.is_relative_to(evidence_root) or output.is_relative_to(root / (BASE + "primary")):
        parser.error("Derived output must be outside preserved primary evidence")
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    checks = Checks()
    result = {"schema": "mumble_weighting_output_audit_result_v1", "status": "failed",
              "source_revision": args.source_revision,
              "audit_source": {"path": "tools/audit_weighting_output.py", **digest_file(Path(__file__))},
              "plan": {"path": PLAN_PATH}, "input_identities": [],
              "execution": {"audit_processes": 1, "new_generator_runs": 0, "new_learner_runs": 0,
                            "new_optimizer_calls": 0, "old_scorer_runs": 0, "input_mutations": 0},
              "interpretation_limits": [
                  "Score-term summaries cover saved queries only, not all 35 Hz score increments.",
                  "Truth is used only for post-inference error and containment; no selection or tuning.",
                  "Local intervals and their descriptive truth inclusion do not establish coverage or hard support.",
                  "Output-motion decomposition does not identify a unique cause of predictive preference."],
              "failure_numeric_encoding": "Any nonfinite failure diagnostics are explicit repr strings; successful audited numeric values must be finite."}
    budget = None
    exit_code = 1
    original_handler = None
    try:
        plan_file = root / PLAN_PATH
        plan_identity = digest_file(plan_file)
        result["plan"].update(plan_identity)
        checks.require(plan_identity["sha256"] == PLAN_SHA256, "frozen_plan_sha256", plan_identity)
        plan = strict_loads(plan_file.read_text())
        bounds, tolerance = plan["resource_bounds"], plan["numerical_tolerances"]
        result["frozen_limits"] = bounds
        result["numerical_tolerances"] = tolerance
        result["comparison_rule"] = "abs(a-b) <= max(abs_tol, rel_tol*max(abs(a),abs(b)))"
        budget = Budget(bounds, started)
        def timeout(_signum, _frame):
            raise AuditFailure("Frozen audit wall-time alarm")
        original_handler = signal.signal(signal.SIGALRM, timeout)
        signal.setitimer(signal.ITIMER_REAL, bounds["audit_wall_s_max"])
        for path, expected in plan["inputs"]["identities"].items():
            actual = digest_file(root / path, expected["bytes"])
            result["input_identities"].append({"path": path, "origin": "repository", **actual})
            checks.require(actual["sha256"] == expected["sha256"], "source_or_extraction_identity", path)
            budget.check()
        index = strict_loads((root / (BASE + "evidence/index.json")).read_text())
        checks.require(index["archive_sha256"] == plan["inputs"]["archive_sha256"], "archive_index_identity")
        indexed = {entry["path"]: entry for entry in index["members"]}
        restored = {}
        for expected in plan["inputs"]["archive_members"]:
            path = expected["path"]
            checks.require(indexed.get(path) == expected, "frozen_member_index_identity", path)
            actual = digest_file(evidence_root / path, expected["bytes"], git_blob=True)
            result["input_identities"].append({"path": path, "origin": "restored_archive", **actual})
            checks.require(all(actual[k] == expected[k] for k in ("bytes", "sha256", "git_blob_sha1")),
                           "restored_member_identity", path)
            restored[Path(path).name] = evidence_root / path
            budget.check()
        checks.require(sum(x["bytes"] for x in plan["inputs"]["archive_members"]) <=
                       bounds["restore_selected_bytes_max"], "restored_byte_budget")
        extraction = strict_loads((root / (BASE + "reporting/observed_results.json")).read_text())
        result["endpoint_interval_audit"] = audit_endpoints(extraction, checks)
        scope = plan["scope"]
        lower, upper = scope["context_next_index_inclusive"]
        focus_lower, focus_upper = scope["focus_next_index_inclusive"]
        additional, witness_ids = set(scope["additional_query_indices"]), set(scope["saved_witness_indices"])
        witnesses, witness_details, interval_counts = {}, {}, {}
        sampled_scores = {"variance_score_term": [], "residual_score_term": [], "score_delta": [],
                          "NIS0": [], "NIS1": []}
        with ExitStack() as stack:
            mf = stack.enter_context(restored["metrics.bin"].open("rb"))
            tf = stack.enter_context(restored["truth.bin"].open("rb"))
            mm = stack.enter_context(mmap.mmap(mf.fileno(), 0, access=mmap.ACCESS_READ))
            tm = stack.enter_context(mmap.mmap(tf.fileno(), 0, access=mmap.ACCESS_READ))
            binaries = BinaryRows(mm, tm, checks)
            result["binary_record_count"] = binaries.count
            focus_file = stack.enter_context((output / "focus_odds.csv").open("x", newline="", encoding="utf-8"))
            focus_columns = ["next_index", "nominal_time_s", "logw0_pre", "logw1_pre", "logw0_post", "logw1_post",
                             "log_odds_pre", "log_odds_post", "log_odds_increment", "weight1_pre", "weight1_post",
                             "SOC_error_pp", "Q_error_percent", "availability_mask", "transaction_code", "flags"]
            focus_csv = csv.DictWriter(CountedWriter(focus_file, budget), fieldnames=focus_columns)
            focus_csv.writeheader()
            scan = {"first_next_index": lower, "last_next_index": upper, "records": 0,
                    "increment_sum": 0.0, "positive_increments": 0, "negative_increments": 0,
                    "zero_increments": 0, "max_absolute_increment": 0.0, "dominance_changes": [],
                    "pre_linear_underflow_counts": [0, 0], "focus_records": 0}
            increments = []
            for n in range(lower, upper + 1):
                before, after = binaries.metric(n), binaries.metric(n + 1)
                old, new = before[6:8], after[6:8]
                checks.compare("scalar_weight_log_normalization", log_normalization(old), 0,
                               tolerance["query_old_weight_abs"], location=n)
                increment = odds(new) - odds(old)
                checks.require(finite(increment), "finite_odds_increment", n)
                increments.append(increment)
                scan["records"] += 1
                scan["positive_increments" if increment > 0 else "negative_increments" if increment < 0 else "zero_increments"] += 1
                if abs(increment) > scan["max_absolute_increment"]:
                    scan["max_absolute_increment"] = abs(increment)
                    scan["at_max_absolute_increment"] = n
                for j in range(2):
                    scan["pre_linear_underflow_counts"][j] += int(math.exp(old[j]) == 0)
                if dominant(odds(old)) != dominant(odds(new)):
                    scan["dominance_changes"].append({"next_index": n, "nominal_time_s": n / 35,
                                                      "before": dominant(odds(old)), "after": dominant(odds(new)),
                                                      "log_odds_before": odds(old), "log_odds_after": odds(new)})
                if focus_lower <= n <= focus_upper:
                    truth = binaries.actual_truth(n)
                    focus_csv.writerow(dict(zip(focus_columns, [n, n / 35, *old, *new, odds(old), odds(new), increment,
                        normalized_weights(old)[1], normalized_weights(new)[1], 100 * (before[2] - truth[2]),
                        100 * (before[3] / truth[1] - 1), before[8], before[9], before[10]])))
                    scan["focus_records"] += 1
                if n % 128 == 0:
                    budget.check()
            scan["increment_sum"] = math.fsum(increments)
            scan["initial_pre_log_odds"] = odds(binaries.metric(lower)[6:8])
            scan["final_post_log_odds"] = odds(binaries.metric(upper + 1)[6:8])
            checks.compare("scalar_increment_telescoping", scan["increment_sum"],
                           scan["final_post_log_odds"] - scan["initial_pre_log_odds"],
                           tolerance["log_odds_increment_abs"], location=[lower, upper])
            result["context_scalar_scan"] = scan
            query_file = stack.enter_context((output / "query_diagnostics.csv").open("x", newline="", encoding="utf-8"))
            query_csv = None
            selected_count, read_count, previous_n = 0, 0, -1
            source_queries = stack.enter_context(restored["queries.jsonl"].open("r", encoding="utf-8"))
            for line in source_queries:
                q = strict_loads(line)
                n = q["next_index"]
                checks.require(n > previous_n, "strict_query_chronology", {"previous": previous_n, "current": n})
                previous_n = n
                read_count += 1
                if not (lower <= n <= upper or n in additional):
                    continue
                selected_count += 1
                checks.require(selected_count <= bounds["selected_full_queries_max"], "selected_query_budget")
                row = verify_query(q, binaries, tolerance, checks, interval_counts)
                if query_csv is None:
                    query_csv = csv.DictWriter(CountedWriter(query_file, budget), fieldnames=list(row))
                    query_csv.writeheader()
                query_csv.writerow(row)
                if lower <= n <= upper:
                    for key in sampled_scores:
                        sampled_scores[key].append(row[key])
                if n in witness_ids:
                    witnesses[n] = q
                    truth = binaries.actual_truth(n)
                    witness_details[n] = {**row, "truth_SOC": truth[2], "truth_Q_Ah": truth[1],
                        "component_SOC_errors_pp": [row["component0_SOC_error_pp"], row["component1_SOC_error_pp"]],
                        "all_component_hull": q["all_component_hull"],
                        "aggregate_SOC_interval": [q["aggregate"]["soc_local_lower"], q["aggregate"]["soc_local_upper"]],
                        "aggregate_Q_interval_Ah": [q["aggregate"]["capacity_local_lower_Ah"], q["aggregate"]["capacity_local_upper_Ah"]]}
                if selected_count % 32 == 0:
                    budget.check()
            checks.require(set(witnesses) == witness_ids, "saved_witness_completeness",
                           {"expected": sorted(witness_ids), "found": sorted(witnesses)})
            checks.require(additional <= set(witnesses), "additional_query_completeness")
            result["query_counts"] = {"read": read_count, "selected": selected_count,
                                      "recurrence_checked": checks.groups["log_odds_recurrence"]["comparisons"],
                                      "last_query_without_next_scalar_row": [binaries.count]}
            result["selected_query_interval_counts"] = interval_counts
            result["saved_witnesses"] = witness_details
            result["sampled_context_score_terms"] = {
                "scope": "Saved successful full queries in context only. These sums do not decompose all 35 Hz increments.",
                "statistics": {key: {"count": len(values), "sum": math.fsum(values),
                    "mean": math.fsum(values) / len(values), "minimum": min(values), "maximum": max(values)}
                    for key, values in sampled_scores.items()}}
            motion = midpoint_motion(witness_details[273385], witness_details[273420])
            checks.compare("midpoint_output_motion", motion["observed_SOC_error_change_pp"], motion["reconstructed_change_pp"],
                           tolerance["moment_abs"], tolerance["moment_rel"], [273385, 273420])
            result["SOC_error_motion_7811_to_7812"] = motion
            final_q = witnesses[504000]["aggregate"]
            final_t = binaries.actual_truth(504000)
            result["final_B_interval_units"] = {
                "Q_mAh": {"point": 1000 * final_q["capacity_Ah"], "truth": 1000 * final_t[1],
                    "signed_error": 1000 * (final_q["capacity_Ah"] - final_t[1]),
                    "local_interval": [1000 * final_q["capacity_local_lower_Ah"], 1000 * final_q["capacity_local_upper_Ah"]],
                    "full_width": 1000 * (final_q["capacity_local_upper_Ah"] - final_q["capacity_local_lower_Ah"])},
                "SOC_percentage_points": {"point": 100 * final_q["current_soc"], "truth": 100 * final_t[2],
                    "signed_error": 100 * (final_q["current_soc"] - final_t[2]),
                    "local_interval": [100 * final_q["soc_local_lower"], 100 * final_q["soc_local_upper"]],
                    "full_width": 100 * (final_q["soc_local_upper"] - final_q["soc_local_lower"])}}
            witness_file = stack.enter_context((output / "witness_queries.jsonl").open("x", encoding="utf-8"))
            writer = CountedWriter(witness_file, budget)
            for n in sorted(witnesses):
                writer.write(json.dumps(witnesses[n], separators=(",", ":"), allow_nan=False) + "\n")
        budget.check()
        result["status"] = "passed_accounting_and_saved_evidence_audit"
        exit_code = 0
    except Exception as error:
        result["failure"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        if original_handler is not None:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, original_handler)
        result["checks"] = checks.groups
        result["mismatches"] = checks.mismatches
        files = [{"path": p.name, **digest_file(p)} for p in sorted(output.iterdir()) if p.is_file()]
        result["outputs"] = files
        data_bytes = sum(p["bytes"] for p in files)
        result["resources"] = {"own_peak_RSS_bytes": peak_rss_bytes(),
            "RSS_source": "resource.getrusage(RUSAGE_SELF).ru_maxrss; Linux KiB converted to bytes",
            "wall_s": time.monotonic() - started, "derived_file_bytes_before_receipt": data_bytes,
            "output_bytes_including_receipt": data_bytes, "python_version": platform.python_version()}
        if budget:
            measured_resource_pass = (
                result["resources"]["own_peak_RSS_bytes"] <= budget.bounds["audit_peak_RSS_bytes_max"] and
                result["resources"]["wall_s"] <= budget.bounds["audit_wall_s_max"])
            result["resources"]["recorded_wall_and_own_RSS_within_frozen_limits"] = measured_resource_pass
            if not measured_resource_pass:
                result["status"] = "failed"
                result["failure"] = {"type": "AuditFailure", "message": "Final recorded own-resource limit exceeded"}
                exit_code = 1
        for _ in range(8):
            encoded = (json.dumps(json_safe(result), indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
            total = data_bytes + len(encoded)
            if total == result["resources"]["output_bytes_including_receipt"]:
                break
            result["resources"]["output_bytes_including_receipt"] = total
        if budget and total > budget.bounds["audit_output_bytes_max"]:
            result["status"] = "failed"
            result["failure"] = {"type": "AuditFailure", "message": "Total output limit exceeded"}
            exit_code = 1
            encoded = (json.dumps(json_safe(result), indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
        with (output / "result.json").open("xb") as target:
            target.write(encoded)
        print(json.dumps({"status": result["status"], "result": str(output / "result.json"),
                          "failure": result.get("failure"), "resources": result["resources"]}, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
