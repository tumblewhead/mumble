#!/usr/bin/env python3
"""State-conditioned forward sensitivity analysis; never runs an estimator.

The coordinate order matches the frozen two-component learner. Exact physical
constant-current dwell solutions carry entering states and their derivatives.
All predictions are evaluated on the declared 35 Hz diagnostic sample grid.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "experiments/parameter_sensitivity_001/plan.json"
RATE = 35
NAMES = ["log_tau1", "log_tau2", "log_tau3", "log_gamma_plus", "log_gamma_minus",
         "log_Q_Ah", "R0", "R1", "R2", "R3", "H", "current_z",
         "current_v1", "current_v2", "current_v3", "current_h"]
LABELS = ["tau1", "tau2", "tau3", "gamma_plus", "gamma_minus", "Q",
          "R0", "R1", "R2", "R3", "H", "z", "v1", "v2", "v3", "h"]
UNITS = ["s", "s", "s", "1/Ah", "1/Ah", "Ah", "ohm", "ohm", "ohm",
         "ohm", "V", "fraction", "V", "V", "V", "dimensionless"]


def ocv(z):
    return 3.0 + 1.15 * z + 0.08 * np.tanh(8.0 * (z - 0.5))


def ocv_slope(z):
    q = np.tanh(8.0 * (z - 0.5))
    return 1.15 + 0.64 * (1.0 - q * q)


def propagate(x, segments, jacobian=False):
    """Return physical trajectory and optional exact first derivatives.

    x: log(tau[3]), log(gamma[2]), log(Q), R0, R[3], H, z, v[3], h.
    segments: current_A and positive integer samples at exactly 1/35 s.
    The first row is t=0 under the first segment's current (instant ohmic
    change); it has no interval weight. Remaining rows end each interval.
    No voltage updates or re-estimation occur. The initial-state sensitivities
    intentionally exclude each parameter's effect on pre-anchor history.
    """
    x = np.asarray(x, dtype=float)
    if x.shape != (16,) or not np.all(np.isfinite(x)) or not segments:
        raise ValueError("A finite 16-coordinate vector and nonempty protocol are required")
    if np.any(x[6:11] < 0) or not 0 <= x[11] <= 1 or not -1 <= x[15] <= 1:
        raise ValueError("Physical coordinate outside its domain")
    with np.errstate(over="raise", under="ignore", invalid="raise"):
        positive = np.exp(x[:6])
    if not np.all(np.isfinite(positive)) or np.any(positive <= 0):
        raise ValueError("Positive parameters must be finite and nonzero")
    counts = []
    for segment in segments:
        count, current = segment["samples"], segment["current_A"]
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            raise ValueError("Protocol counts must be positive integers")
        if not math.isfinite(current) or abs(current) > .25:
            raise ValueError("Protocol current exceeds the frozen model-input contract")
        counts.append(count)
    total = sum(counts)
    result = {"time_s": np.arange(total + 1, dtype=float) / RATE,
              "current_A": np.empty(total + 1), "voltage_V": np.empty(total + 1),
              "z": np.empty(total + 1), "v": np.empty((total + 1, 3)),
              "h": np.empty(total + 1)}
    if jacobian:
        result["voltage_jacobian"] = np.empty((total + 1, 16))
        result["soc_jacobian"] = np.empty((total + 1, 16))
    tau, gamma, capacity = positive[:3], positive[3:5], positive[5]
    resistance, amplitude = x[7:10], x[10]
    z, v, h = x[11], x[12:15].copy(), x[15]
    eye = np.eye(16)
    dz, dv, dh = eye[11].copy(), eye[12:15].copy(), eye[15].copy()
    current = float(segments[0]["current_A"])
    result["current_A"][0] = current
    result["z"][0], result["v"][0], result["h"][0] = z, v, h
    result["voltage_V"][0] = ocv(z) - x[6] * current - np.sum(v) - amplitude * h
    if jacobian:
        result["soc_jacobian"][0] = dz
        result["voltage_jacobian"][0] = (
            ocv_slope(z) * dz - current * eye[6] - np.sum(dv, axis=0)
            - h * eye[10] - amplitude * dh)
    start = 1
    for segment, count in zip(segments, counts):
        current = float(segment["current_A"])
        elapsed = np.arange(1, count + 1, dtype=float) / RATE
        charge_over_Q = current * elapsed / (3600.0 * capacity)
        zz = z - charge_over_Q
        q = elapsed[:, None] / tau
        decay = np.exp(-q)
        change = -np.expm1(-q)
        vv = decay * v + change * current * resistance
        if current == 0:
            hh = np.full(count, h)
            hdecay, hq, direction = np.ones(count), np.zeros(count), 0
        else:
            direction = 0 if current > 0 else 1
            target = 1.0 if current > 0 else -1.0
            hq = gamma[direction] * abs(current) * elapsed / 3600.0
            hdecay = np.exp(-hq)
            hh = hdecay * h + (-np.expm1(-hq)) * target
        if not np.all(np.isfinite(zz)) or np.any(zz < 0) or np.any(zz > 1):
            raise ValueError("SOC leaves the supplied OCV domain; no clipping")
        sl = slice(start, start + count)
        result["current_A"][sl] = current
        result["z"][sl], result["v"][sl], result["h"][sl] = zz, vv, hh
        result["voltage_V"][sl] = ocv(zz) - x[6] * current - np.sum(vv, axis=1) - amplitude * hh
        if jacobian:
            dzs = np.broadcast_to(dz, (count, 16)).copy()
            dzs[:, 5] += charge_over_Q
            dvs = decay[:, :, None] * dv[None, :, :]
            for mode in range(3):
                dvs[:, mode, 7 + mode] += change[:, mode] * current
                dvs[:, mode, mode] += (v[mode] - resistance[mode] * current) * decay[:, mode] * q[:, mode]
            dhs = hdecay[:, None] * dh[None, :]
            if current != 0:
                dhs[:, 3 + direction] += (target - h) * hdecay * hq
            result["soc_jacobian"][sl] = dzs
            result["voltage_jacobian"][sl] = (
                ocv_slope(zz)[:, None] * dzs - current * eye[6]
                - np.sum(dvs, axis=1) - hh[:, None] * eye[10] - amplitude * dhs)
            dz, dv, dh = dzs[-1].copy(), dvs[-1].copy(), dhs[-1].copy()
        z, v, h = float(zz[-1]), vv[-1].copy(), float(hh[-1])
        start += count
    if not all(np.all(np.isfinite(value)) for value in result.values()):
        raise ValueError("Nonfinite diagnostic output")
    return result


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def write_json(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def unit_scales(x):
    """Native-coordinate increment for the explicitly labeled reference unit."""
    return np.r_[np.full(6, .01), .01 * x[6:11], .01, .001, .001, .001, .01]


def physical(x):
    return np.r_[np.exp(x[:6]), x[6:]]


def curve_metrics(error, time_s, scale=1.0):
    values = np.asarray(error) * scale
    index = int(np.argmax(np.abs(values)))
    return {"peak_abs": float(abs(values[index])), "signed_at_peak": float(values[index]),
            "peak_index": index, "peak_time_s": float(time_s[index]),
            "RMS": float(np.sqrt(np.mean(values[1:] ** 2))),
            "initial": float(values[0]), "final": float(values[-1])}


def view_indices(segments):
    total = sum(x["samples"] for x in segments)
    indices = {0, total, *np.linspace(0, total, 401).astype(int).tolist()}
    start = 0
    for segment in segments:
        indices.update(range(start, start + min(350, segment["samples"]) + 1))
        indices.add(start + segment["samples"])
        start += segment["samples"]
    return np.array(sorted(indices), dtype=int)


def execute(plan, output):
    """One fixed post-inference audit; preserve its first output directory."""
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Output already exists; preserve the first sensitivity result")
    sources = plan["source_files"]
    revision = git("rev-parse", "HEAD")
    for path in sources:
        if (ROOT / path).read_bytes() != subprocess.check_output(["git", "show", revision + ":" + path], cwd=ROOT):
            raise ValueError("Uncommitted analysis source: " + path)
    evidence = ROOT / plan["saved_evidence"]["path"]
    if sha(evidence) != plan["saved_evidence"]["sha256"]:
        raise ValueError("Saved full vectors changed")
    qualification_path = ROOT / plan["qualification_path"]
    qualification = json.loads(qualification_path.read_text())
    if not qualification["passed"]:
        raise ValueError("Independent prerequisites did not pass")
    for path, digest in qualification["source_sha256"].items():
        if sha(ROOT / path) != digest:
            raise ValueError("Qualified source changed: " + path)
    saved = json.loads(evidence.read_text())
    selected = [v for v in saved["full_vectors"] if v["arm"] == "public_logQ_split"
                and v["view"] == "aggregate" and v["next_index"] in plan["anchor_samples"]]
    if [v["next_index"] for v in selected] != plan["anchor_samples"]:
        raise ValueError("Unexpected anchor ordering or count")
    output.mkdir(parents=True)
    started = time.monotonic()
    receipt = {"schema": "mumble_parameter_sensitivity_receipt_v1", "completed": False,
               "source_revision": revision, "source_tree": git("rev-parse", "HEAD^{tree}"),
               "source_sha256": {p: sha(ROOT / p) for p in sources},
               "plan_sha256": sha(PLAN_PATH), "qualification_sha256": sha(qualification_path),
               "saved_evidence_sha256": sha(evidence), "started_utc": datetime.now(timezone.utc).isoformat(),
               "platform": platform.platform(), "python": platform.python_version(), "numpy": np.__version__,
               "estimator_runs": 0, "optimizer_calls": 0, "completed_study_reruns": 0,
               "truth_use": "Saved scoring truth is used only as the post-inference error baseline.",
               "propagation_calls": 0, "diagnostic_interval_evaluations": 0}
    write_json(output / "started.json", receipt)
    results = {"schema": "mumble_parameter_sensitivity_results_v1", "source_revision": revision,
               "coordinate_names": NAMES, "labels": LABELS, "physical_units": UNITS,
               "reference_unit": ["1 percent fractional differential"] * 11 +
                 ["1 SOC percentage point", "1 mV", "1 mV", "1 mV", "0.01 dimensionless h"],
               "semantics": plan["semantics"], "anchors": [], "protocols": plan["protocols"]}
    profiles = {}

    def run(x, segments, jacobian=False):
        result = propagate(x, segments, jacobian)
        receipt["propagation_calls"] += 1
        receipt["diagnostic_interval_evaluations"] += sum(s["samples"] for s in segments)
        return result

    for vector in selected:
        estimate = np.asarray(vector["mean"], float)
        truth = np.asarray(vector["truth_current_chart_scoring_only"], float)
        error = estimate - truth
        actual_p, estimated_p = physical(truth), physical(estimate)
        record = {"anchor_index": vector["next_index"], "anchor_time_s": vector["next_index"] / RATE,
                  "native_estimate": estimate.tolist(), "native_truth_scoring_only": truth.tolist(),
                  "physical_estimate": estimated_p.tolist(), "physical_truth": actual_p.tolist(),
                  "physical_error": (estimated_p - actual_p).tolist(),
                  "protocol_results": []}
        for protocol in plan["protocols"]:
            segments = protocol["segments"]
            baseline, predicted = run(truth, segments, True), run(estimate, segments, True)
            t = baseline["time_s"]
            slope = ocv_slope(baseline["z"])
            isolated = np.empty((len(t), 16))
            repairs = np.empty_like(isolated)
            linear = baseline["voltage_jacobian"] * error
            linear_at_estimate = predicted["voltage_jacobian"] * error
            rows = []
            for j, name in enumerate(NAMES):
                single = truth.copy(); single[j] = estimate[j]
                injected = run(single, segments)
                fixed = estimate.copy(); fixed[j] = truth[j]
                repaired = run(fixed, segments)
                isolated[:, j] = injected["voltage_V"] - baseline["voltage_V"]
                repairs[:, j] = predicted["voltage_V"] - repaired["voltage_V"]
                rows.append({"coordinate": name, "label": LABELS[j],
                    "unit_sensitivity_at_truth_mV": curve_metrics(baseline["voltage_jacobian"][:, j] * unit_scales(truth)[j], t, 1000),
                    "unit_sensitivity_at_estimate_mV": curve_metrics(predicted["voltage_jacobian"][:, j] * unit_scales(estimate)[j], t, 1000),
                    "isolated_actual_error_mV": curve_metrics(isolated[:, j], t, 1000),
                    "isolated_error_OCV_equivalent_SOC_pp_proxy": curve_metrics(isolated[:, j] / slope, t, 100),
                    "isolated_actual_SOC_error_pp": curve_metrics(injected["z"] - baseline["z"], t, 100),
                    "one_coordinate_repair_effect_mV": curve_metrics(repairs[:, j], t, 1000),
                    "linearized_actual_error_at_truth_mV": curve_metrics(linear[:, j], t, 1000),
                    "linearized_actual_error_at_estimate_mV": curve_metrics(linear_at_estimate[:, j], t, 1000),
                    "linearization_residual_at_truth_mV": curve_metrics(isolated[:, j] - linear[:, j], t, 1000)})
            joint = predicted["voltage_V"] - baseline["voltage_V"]
            sum_single = np.sum(isolated, axis=1)
            sum_abs = np.sum(np.abs(isolated), axis=1)
            joint_rms = float(np.sqrt(np.mean(joint[1:] ** 2)))
            sum_abs_rms = float(np.sqrt(np.mean(sum_abs[1:] ** 2)))
            metrics = {"protocol": protocol["id"], "samples": len(t) - 1,
                "truth_SOC_range": [float(np.min(baseline["z"])), float(np.max(baseline["z"]))],
                "estimate_SOC_range": [float(np.min(predicted["z"])), float(np.max(predicted["z"]))],
                "coordinates": rows,
                "joint_voltage_error_mV": curve_metrics(joint, t, 1000),
                "joint_SOC_error_pp": curve_metrics(predicted["z"] - baseline["z"], t, 100),
                "joint_voltage_OCV_equivalent_SOC_pp_proxy": curve_metrics(joint / slope, t, 100),
                "sum_isolated_errors_mV": curve_metrics(sum_single, t, 1000),
                "sum_absolute_isolated_errors_mV_diagnostic_not_bound": curve_metrics(sum_abs, t, 1000),
                "nonlinear_interaction_mV": curve_metrics(joint - sum_single, t, 1000),
                "joint_first_order_at_truth_mV": curve_metrics(np.sum(linear, axis=1), t, 1000),
                "joint_linearization_residual_mV": curve_metrics(joint - np.sum(linear, axis=1), t, 1000),
                "joint_RMS_over_sum_absolute_isolated_RMS": joint_rms / sum_abs_rms if sum_abs_rms else None}
            record["protocol_results"].append(metrics)
            if vector["next_index"] == plan["anchor_samples"][-1]:
                keep = view_indices(segments)
                prefix = protocol["id"] + "__"
                for key, values in {"indices": keep, "time_s": t[keep], "current_A": baseline["current_A"][keep],
                    "truth_voltage_V": baseline["voltage_V"][keep], "estimated_voltage_V": predicted["voltage_V"][keep],
                    "joint_error_V": joint[keep], "isolated_errors_V": isolated[keep],
                    "repair_effects_V": repairs[keep], "sum_isolated_errors_V": sum_single[keep],
                    "sum_absolute_isolated_errors_V": sum_abs[keep], "linear_joint_error_V": np.sum(linear, axis=1)[keep]}.items():
                    profiles[prefix + key] = values
            print(json.dumps({"event": "protocol_complete", "anchor_s": record["anchor_time_s"],
                              "protocol": protocol["id"], "joint_peak_mV": metrics["joint_voltage_error_mV"]["peak_abs"]}), flush=True)
        results["anchors"].append(record)
    write_json(output / "results.json", results)
    np.savez_compressed(output / "profiles.npz", **profiles)
    receipt.update({"completed": True, "finished_utc": datetime.now(timezone.utc).isoformat(),
                    "wall_seconds": time.monotonic() - started,
                    "artifacts_sha256": {p.name: sha(p) for p in (output / "results.json", output / "profiles.npz")},
                    "all_domains_passed": True,
                    "profile_scope": "Plot views only: all35Hz samples used for metrics, first10s of each dwell retained densely plus401 evenly spaced indices; finalanchor only."})
    write_json(output / "receipt.json", receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = execute(json.loads(PLAN_PATH.read_text()), args.output)
    print(json.dumps({k: receipt[k] for k in ("completed", "propagation_calls", "diagnostic_interval_evaluations", "wall_seconds")}))


if __name__ == "__main__":
    main()
