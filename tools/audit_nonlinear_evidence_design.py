#!/usr/bin/env python3
"""Audit frozen summaries and public design arithmetic; never run inference.

Only saved query/scoring JSON, summaries and source text are read. The prescribed
event schedule and OCV expression are decoded with a restricted AST reader;
the truth-bearing generator module is never imported or executed. No raw CSV is
read and no per-sample model trajectory is generated. An output path must not
already exist, so prior receipts cannot be overwritten.
"""
from __future__ import annotations

import argparse
import ast
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
CASE = "cell_b_35hz_s202610240"
TIMES = (10, 60, 120, 220, 400, 450, 460, 600, 900, 1200, 1800, 2100)


class Inputs:
    def __init__(self, root: Path):
        self.root = root
        self.hashes: dict[str, str] = {}

    def text(self, path: str) -> str:
        content = (self.root / path).read_bytes()
        self.hashes[path] = hashlib.sha256(content).hexdigest()
        return content.decode("utf-8")

    def json(self, path: str):
        return json.loads(self.text(path))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def public_expression(node: ast.AST, names: dict):
    """Decode the public profile and OCV expression without eval or imports."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float)):
        return node.value
    if isinstance(node, ast.Name) and node.id in names:
        return names[node.id]
    if isinstance(node, (ast.List, ast.Tuple)):
        result = [public_expression(x, names) for x in node.elts]
        return tuple(result) if isinstance(node, ast.Tuple) else result
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        result = public_expression(node.operand, names)
        return -result if isinstance(node.op, ast.USub) else result
    if isinstance(node, ast.BinOp):
        left, right = public_expression(node.left, names), public_expression(node.right, names)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
    if isinstance(node, ast.JoinedStr):
        return "".join(str(public_expression(x, names)) for x in node.values)
    if isinstance(node, ast.FormattedValue):
        require(node.conversion == -1, "Unsupported profile label conversion")
        spec = public_expression(node.format_spec, names) if node.format_spec else ""
        return format(public_expression(node.value, names), spec)
    if isinstance(node, ast.Call) and not node.keywords:
        args = [public_expression(x, names) for x in node.args]
        if isinstance(node.func, ast.Name) and node.func.id == "Fraction":
            return Fraction(*args)
        if (isinstance(node.func, ast.Attribute) and node.func.attr == "tanh"
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "np"):
            return math.tanh(*args)
    raise ValueError("Unsupported public expression: " + ast.dump(node))


def prescribed_profile(module: ast.Module) -> tuple[int, list[dict], ast.AST]:
    rate_nodes = [n.value for n in module.body if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == "RATE_HZ" for t in n.targets)]
    require(len(rate_nodes) == 1, "Missing unique public sample rate")
    rate = public_expression(rate_nodes[0], {})
    require(isinstance(rate, int) and rate == 35, "This receipt is for the frozen 35 Hz profile")
    profile = next(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == "profile")
    blocks: list[tuple] = []

    def read_statements(statements: list[ast.stmt], names: dict) -> None:
        for node in statements:
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                continue  # Public function docstring.
            if isinstance(node, ast.Assign):
                require(len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                        and node.targets[0].id == "blocks", "Unexpected profile assignment")
                require(not blocks, "Repeated profile initialization")
                blocks.extend(public_expression(node.value, names))
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                call = node.value
                require(isinstance(call.func, ast.Attribute) and call.func.attr == "extend"
                        and isinstance(call.func.value, ast.Name) and call.func.value.id == "blocks"
                        and len(call.args) == 1 and not call.keywords, "Unexpected profile call")
                blocks.extend(public_expression(call.args[0], names))
            elif isinstance(node, ast.For):
                require(isinstance(node.target, ast.Name) and isinstance(node.iter, ast.Call)
                        and isinstance(node.iter.func, ast.Name) and node.iter.func.id == "range"
                        and not node.iter.keywords and not node.orelse, "Unexpected profile loop")
                args = [public_expression(a, names) for a in node.iter.args]
                values = range(*args)
                require(len(values) <= 1000, "Profile event loop exceeds audit scope")
                for value in values:
                    read_statements(node.body, dict(names, **{node.target.id: value}))
            elif isinstance(node, ast.Assert):
                continue  # Independently check duration and grid alignment below.
            elif isinstance(node, ast.Return):
                require(isinstance(node.value, ast.Name) and node.value.id == "blocks",
                        "Unexpected profile return")
            else:
                raise ValueError("Unsupported profile statement: " + ast.dump(node))

    read_statements(profile.body, {})
    time, events = Fraction(0), []
    for current, duration, label in blocks:
        require(isinstance(duration, Fraction) and duration > 0, "Invalid exact event duration")
        count = duration * rate
        require(count.denominator == 1, "Event does not align with the public sample grid")
        events.append({"label": label, "start_s": time, "end_s": time + duration,
                       "current_A": current, "duration_s": duration, "count": int(count)})
        time += duration
    require(time == 2100, "Unexpected prescribed profile duration")
    ocv = next(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == "ocv")
    returns = [n.value for n in ocv.body if isinstance(n, ast.Return)]
    require(len(returns) == 1, "Missing unique public OCV expression")
    return rate, events, returns[0]


def source_contract(online: str, header: str, model: str) -> tuple[list[float], list[float], dict]:
    compact = "".join(online.split())
    for text in ("k=current>0?3:4;", "q=exp(old->mean[k])*(fabs(current)/3600.)*dt;",
                 "next->mean[15]=a*old->mean[15]+om*sign;",
                 "*voltage=u-s->mean[6]*current-s->mean[12]-s->mean[13]-s->mean[14]-s->mean[10]*s->mean[15];"):
        require(text in compact, "Physical equation changed; review this audit before reuse")
    for text in ("SCM_ONLINE_DIM 16", "SCM_ONLINE_LOG_Q=5", "SCM_ONLINE_HYST=15"):
        require(text in header, "Online coordinate contract changed")
    model_compact = "".join(model.split())
    require("q=tanh(8*(z-.5));" in model_compact and "*value=3+1.15*z+.08*q;" in model_compact,
            "Illustrative model OCV changed")
    bounds = []
    for name in ("lower", "upper"):
        match = re.search(r"static\s+const\s+double\s+" + name + r"\[D\]\s*=\s*\{([^}]+)\}", online)
        require(match is not None, "Missing public support array")
        values = [float(x.strip()) for x in match.group(1).split(",") if x.strip()]
        require(len(values) == 16, "Unexpected public support dimension")
        bounds.append(values)
    prior = re.search(r"static\s+void\s+public_belief\([^)]*\)\s*\{(.*?)\n\}", online, re.S)
    require(prior is not None, "Missing public belief function")
    body = prior.group(1)
    mean = re.search(r"s->mean\[5\]\s*=\s*([-+0-9.eE]+)\s*;", body)
    root12 = re.search(r"root12\s*=\s*([-+0-9.eE]+)\s*;", body)
    require(mean is not None and root12 is not None, "Public logQ prior changed")
    require("s->factor[AT(i,i)]=width/root12;" in "".join(body.split()),
            "Public scale construction changed")
    return bounds[0], bounds[1], {"logQ_mean": float(mean.group(1)), "root12": float(root12.group(1))}


def public_split(lower: list[float], upper: list[float], prior: dict) -> dict:
    """This section depends only on public source constants, never scored truth."""
    mu = prior["logQ_mean"]
    sigma = (upper[5] - lower[5]) / prior["root12"]
    alpha, beta = math.sqrt(2 / math.pi), math.sqrt(1 - 2 / math.pi)
    component_sd = sigma * beta
    components = [{"weight": 0.5, "logQ_mean": mu + sign * alpha * sigma,
                   "logQ_SD": component_sd} for sign in (-1, 1)]
    for component in components:
        require(lower[5] <= component["logQ_mean"] <= upper[5],
                "Public split mean lies outside the inherited mean domain")
        component["physical_point_Q_Ah"] = math.exp(component["logQ_mean"])
    reconstructed_mu = sum(c["weight"] * c["logQ_mean"] for c in components)
    reconstructed_var = sum(c["weight"] * (c["logQ_SD"] ** 2
                            + (c["logQ_mean"] - reconstructed_mu) ** 2) for c in components)
    return {"scope": "Design arithmetic only; one fixed public placement, not inference or a search.",
            "truth_used": False, "public_logQ_mean": mu, "public_logQ_SD": sigma,
            "public_logQ_mean_domain": [lower[5], upper[5]], "alpha": alpha, "beta_SD": beta,
            "components": components, "means_inside_public_domain": True,
            "reconstructed_logQ_mean": reconstructed_mu,
            "reconstructed_logQ_variance": reconstructed_var,
            "mean_difference_from_original": reconstructed_mu - mu,
            "variance_difference_from_original": reconstructed_var - sigma ** 2,
            "density_limit": "Two Gaussian components match these logQ moments; they do not reproduce the original Gaussian density or supply hard support. exp(logQ_mean) is a physical point, not the component mean of Q."}


def build(root: Path, source_revision: str) -> dict:
    inputs = Inputs(root)
    online = inputs.text("src/scm_online.c")
    header = inputs.text("include/scm_online.h")
    model = inputs.text("src/scm_model.c")
    lower, upper, prior = source_contract(online, header, model)
    split = public_split(lower, upper, prior)  # Evaluated before loading any scoring truth.
    rate, events, ocv_expression = prescribed_profile(ast.parse(inputs.text("tools/generate_cases.py")))
    summary = inputs.json("experiments/bounded_online_002/summary.json")
    scores = inputs.json("experiments/bounded_online_002/scores.json")
    case = next(x for x in scores["cases"] if x["case_id"] == CASE)
    vectors = {x["next_index"]: x for x in case["selected_full_vectors"] if x["arm"] == "control"}
    truth_Q = math.exp(vectors[73500]["truth_current_chart"][5])
    wanted = {t * rate for t in TIMES}
    queries = {}
    query_count = 0
    path = "experiments/bounded_online_002/primary/" + CASE + "__control.jsonl"
    for line in inputs.text(path).splitlines():
        record = json.loads(line)
        if record.get("event") == "query":
            query_count += 1
            if record["next_index"] in wanted:
                require(record["next_index"] not in queries, "Duplicate selected saved query")
                queries[record["next_index"]] = record["state"]
    require(set(queries) == wanted, "Missing selected saved query")
    timing = []
    for time in TIMES:
        state = queries[time * rate]
        q = state["capacity_Ah"]
        timing.append({"nominal_time_s": time, "saved_elapsed_s": state["elapsed_s"],
                       "next_index": time * rate, "capacity_Ah": q,
                       "capacity_error_percent_scoring_only": 100 * (q / truth_Q - 1),
                       "local_2SD_max_halfwidth_percent_of_estimate": 100 * max(
                           q - state["capacity_local_lower_Ah"], state["capacity_local_upper_Ah"] - q) / q,
                       "capacity_status": state["capacity_status"], "logQ_SD": state["coordinate_sd"][5],
                       "SOC": state["mean"][11], "H_V": state["mean"][10], "h": state["mean"][15],
                       "gamma_plus": math.exp(state["mean"][3]),
                       "gamma_minus": math.exp(state["mean"][4]),
                       "limited_gain_count": state["limited_gain_count"],
                       "last_limited_mask": state["last_limited_mask"],
                       "innovation_EWMA": state["innovation_ewma"]})
    decompositions = []
    for index in (350, 31500, 63000, 73500):
        vector = vectors[index]
        mean, truth = vector["mean"], vector["truth_current_chart"]
        time = Fraction(index, rate)
        event = next(e for e in events if e["start_s"] < time <= e["end_s"])
        current = event["current_A"]
        ocv_est = public_expression(ocv_expression, {"z": mean[11]})
        ocv_true = public_expression(ocv_expression, {"z": truth[11]})
        terms = {"OCV": 1000 * (ocv_est - ocv_true),
                 "ohmic": -1000 * current * (mean[6] - truth[6]),
                 "RC": -1000 * (sum(mean[12:15]) - sum(truth[12:15])),
                 "hysteresis": -1000 * (mean[10] * mean[15] - truth[10] * truth[15])}
        decompositions.append({"next_index": index, "nominal_time_s": float(time),
                               "current_A": current, "voltage_difference_mV": terms,
                               "total_voltage_difference_mV": sum(terms.values()),
                               "estimated_H_SOC_h": [mean[10], mean[11], mean[15]],
                               "scored_true_H_SOC_h": [truth[10], truth[11], truth[15]],
                               "local_H_SOC_h_SD": [vector["coordinate_sd"][i] for i in (10, 11, 15)]})
    last_positive = len(events) - 1
    while last_positive >= 0 and events[last_positive]["current_A"] > 0:
        last_positive -= 1
    tail = events[last_positive + 1:]
    require(tail and tail[0]["start_s"] == 1500 and tail[-1]["end_s"] == 2100,
            "Expected frozen positive tail changed")
    gamma_min = math.exp(lower[3])
    require(lower[15] == -1 and upper[15] == 1, "Hysteresis support changed")
    reachability = []
    for endpoint in (1800, 2100):
        charge = Fraction(0)
        for event in tail:
            duration = max(Fraction(0), min(Fraction(endpoint), event["end_s"]) - event["start_s"])
            charge += Fraction(str(event["current_A"])) * duration / 3600
        bound = 1 + (lower[15] - 1) * math.exp(-gamma_min * float(charge))
        saved = queries[endpoint * rate]["mean"][15]
        reachability.append({"nominal_time_s": endpoint, "positive_charge_Ah_exact_prescription": str(charge),
                             "positive_charge_Ah": float(charge), "analytic_lower_evaluated_double": bound,
                             "saved_h": saved, "violation_below_lower": bound - saved,
                             "outside_analytic_hull_at_ordinary_precision": saved < bound})
    m1 = inputs.json("experiments/trajectory_integration_001/summary.json")
    m1_case = next(x for x in m1["cases"] if x["case_id"] == CASE)
    m1_audit = inputs.json("experiments/m1_belief_audit_001/summary.json")
    m1_audit_case = next(x for x in m1_audit["cases"] if x["case_id"] == CASE)
    m1_rows = []
    for benchmark in m1_case["selected_benchmarks"]:
        if benchmark["arm"] == "control":
            audit = next(x for x in m1_audit_case["fit_summaries"]
                         if x["arm"] == "control" and x["next_index"] == benchmark["next_index"])
            m1_rows.append({"next_index": benchmark["next_index"], "time_s": benchmark["time_s"],
                            "capacity_error_percent": benchmark["capacity_error_percent"],
                            "SOC_error_pp": benchmark["SOC_error_pp"],
                            "hysteresis_state_error": audit["current_state_errors"]["hysteresis_state_error"],
                            "optimizer_status": benchmark["optimizer_status"],
                            "capacity_status": benchmark["capacity_status"]})
    return {"schema": "mumble_nonlinear_evidence_design_audit_v1", "source_revision": source_revision,
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "evidence_input_sha256": inputs.hashes,
            "actions": {"inference_runs": 0, "optimizer_calls": 0, "trace_replays": 0,
                        "raw_voltage_trace_reads": 0, "raw_data_generation": 0,
                        "public_generator_module_imports": 0},
            "public_split_design_no_truth": split,
            "post_inference_evidence": {
                "case": CASE, "arm": "control", "saved_query_count": query_count,
                "truth_capacity_Ah_scoring_only": truth_Q,
                "frozen_source_revision": summary["source_revision"],
                "rejected_corrections": case["arms"]["control"]["final_counters"]["rejected_voltage_count"],
                "all_zero_selected_gains": case["arms"]["control"]["final_counters"]["zero_gain_count"],
                "capacity_timing": timing, "endpoint_voltage_decompositions": decompositions,
                "M1_existing_reference_comparison": m1_rows},
            "input_only_reachability": {
                "truth_used_in_bound": False, "entering_h_support": [lower[15], upper[15]],
                "gamma_plus_lower_log_from_source": lower[3], "gamma_plus_lower_evaluated_double": gamma_min,
                "positive_tail": [{"label": e["label"], "start_s": float(e["start_s"]),
                                   "end_s": float(e["end_s"]), "current_A": e["current_A"]} for e in tail],
                "formula": "h(t) >= 1 + (h_lower - 1) exp(-gamma_plus_lower * positive_charge_Ah)",
                "rows": reachability,
                "arithmetic_scope": "Analytic real-arithmetic inequality evaluated with ordinary Python double/libm; no outward-rounded C certificate.",
                "input_scope": "Prescribed exact event durations and decimal current levels from public profile source; no new raw-CSV compliance check or per-sample replay."},
            "assumptions_and_limits": [
                "Frozen saved queries and scoring vectors have the provenance declared by their existing receipts; this audit hashes them but does not rerun scoring.",
                "The frozen primary consumed the prescribed profile with the established actual-interval semantics. The analytic bound uses that prescription, not a fresh raw-input audit.",
                "Static matched model, fixed gamma within inherited supports, h in [-1,1], illustrative known OCV and no process noise are the inherited premises.",
                "Endpoint compensation is a measurement-equation evaluation at four saved vectors, not a model trajectory or inverse fit.",
                "Scoring truth appears only in the retrospective evidence section. Public split placement and the reachability bound do not use it.",
                "The reachability violation identifies physical-history inconsistency; it does not establish a unique bias mechanism, calibrated coverage or sufficient capacity remedy.",
                "The broad public h hull alone does not exclude the full wrong SOC/Q/h compensation family.",
                "The two-component prior is one fixed public design. Matching initial logQ moments does not validate filtering accuracy or preserve the complete original prior density.",
                "All previous scores, statuses and failures remain unchanged. No new primary is performed or authorized by this audit."]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-revision", required=True, help="Frozen source commit for this one audit execution")
    parser.add_argument("--output", type=Path, help="New JSON path; stdout if omitted")
    args = parser.parse_args()
    require(re.fullmatch(r"[0-9a-f]{40}", args.source_revision) is not None, "Use a full 40-character commit ID")
    if args.output is not None:
        require(not args.output.exists(), "Refusing to overwrite existing audit output")
    result = build(ROOT, args.source_revision)
    rendered = json.dumps(result, allow_nan=False, separators=(",", ":")) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write(rendered)


if __name__ == "__main__":
    main()
