#!/usr/bin/env python3
"""Bounded fabricated qualification; never opens an archived observation file.

The independent reference carries physical states and their tangents directly,
whereas stream_evaluator.c uses the unchanged basis/feature model. A second
reference calls unchanged scm_physical_step through ctypes. Every input trace
is fabricated here and every evaluator receives only newly created fixtures.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import signal
import struct
import subprocess
import sys
import time

D = 16
SIGMA = 0.001
U = 2.0 ** -53
BASE = Path(__file__).resolve().parents[2]
AREA = Path(__file__).resolve().parent
SCHEMA = "mumble_retained_likelihood_evaluator_qualification_v1"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def strict_json(path: Path) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def constant(value):
        raise ValueError(f"Nonfinite JSON token: {value}")

    value = json.loads(path.read_text(), object_pairs_hook=pairs, parse_constant=constant)
    if not isinstance(value, dict):
        raise ValueError("Expected one JSON object")
    return value


def launch(argv: list[str], directory: Path, label: str, cwd: Path) -> dict:
    stdout_path = directory / f"{label}.stdout"
    stderr_path = directory / f"{label}.stderr"

    def limits():
        resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
        resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024,) * 2)

    begin = time.monotonic()
    timed_out = False
    with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
        process = subprocess.Popen(
            argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
            start_new_session=True, preexec_fn=limits,
        )
        while True:
            pid, status, usage = os.wait4(process.pid, os.WNOHANG)
            if pid:
                break
            if time.monotonic() - begin > 15:
                timed_out = True
                os.killpg(process.pid, signal.SIGKILL)
                _, status, usage = os.wait4(process.pid, 0)
                break
            time.sleep(0.005)
        process.returncode = os.waitstatus_to_exitcode(status)
    result = {
        "command": argv, "cwd": str(cwd), "exit_code": process.returncode,
        "wall_s": time.monotonic() - begin, "CPU_user_s": usage.ru_utime,
        "CPU_system_s": usage.ru_stime, "peak_RSS_bytes": usage.ru_maxrss * 1024,
        "resource_measurement": "os.wait4 for this exact child PID; build commands may include compiler descendants",
        "timed_out": timed_out,
        "stdout": str(stdout_path.relative_to(directory)),
        "stdout_sha256": digest(stdout_path), "stdout_bytes": stdout_path.stat().st_size,
        "stderr": str(stderr_path.relative_to(directory)),
        "stderr_sha256": digest(stderr_path), "stderr_bytes": stderr_path.stat().st_size,
    }
    write_json(directory / f"{label}.resources.json", result)
    return result


class Physical(ctypes.Structure):
    _fields_ = [
        ("modes", ctypes.c_int), ("R0", ctypes.c_double),
        ("R", ctypes.c_double * 3), ("tau", ctypes.c_double * 3),
        ("H", ctypes.c_double), ("gamma_plus", ctypes.c_double),
        ("gamma_minus", ctypes.c_double), ("Q", ctypes.c_double),
    ]


class PhysicalState(ctypes.Structure):
    _fields_ = [("z", ctypes.c_double), ("v", ctypes.c_double * 3), ("h", ctypes.c_double)]


class PhysicalReference:
    def __init__(self, path: Path):
        self.library = ctypes.CDLL(str(path))
        self.step = self.library.scm_physical_step
        self.step.argtypes = [
            ctypes.POINTER(Physical), ctypes.POINTER(PhysicalState), ctypes.c_void_p,
            ctypes.c_double, ctypes.c_double, ctypes.POINTER(ctypes.c_double),
        ]
        self.step.restype = ctypes.c_int
        self.calls = 0

    def trace(self, x: list[float], rows: list[tuple[float, float]]):
        physical = Physical(
            3, x[6], (ctypes.c_double * 3)(*x[7:10]),
            (ctypes.c_double * 3)(*(math.exp(v) for v in x[:3])),
            x[10], math.exp(x[3]), math.exp(x[4]), math.exp(x[5]),
        )
        state = PhysicalState(x[11], (ctypes.c_double * 3)(*x[12:15]), x[15])
        prediction = ctypes.c_double()
        voltage = []
        for dt, current in rows:
            status = self.step(ctypes.byref(physical), ctypes.byref(state), None,
                               dt, current, ctypes.byref(prediction))
            self.calls += 1
            if status != 0:
                raise AssertionError(f"Fabricated physical fixture failed: {status}")
            voltage.append(prediction.value)
        return voltage, list(x[:11]) + [state.z, *state.v, state.h]


def direct_tangent(x: list[float], rows: list[tuple[float, float]]) -> dict:
    """Direct physical recurrence and analytic tangent, independent of features."""
    z, v, h = x[11], list(x[12:15]), x[15]
    dz = [float(k == 11) for k in range(D)]
    dv = [[float(k == 12 + i) for k in range(D)] for i in range(3)]
    dh = [float(k == 15) for k in range(D)]
    voltage, jacobians = [], []
    Q = math.exp(x[5])
    charge = elapsed = 0.0
    charge_min = charge_max = 0.0
    for dt, current in rows:
        charge += current * dt / 3600
        charge_min, charge_max = min(charge_min, charge), max(charge_max, charge)
        elapsed += dt
        z -= current * dt / (3600 * Q)
        dz[5] += current * dt / (3600 * Q)
        for i in range(3):
            q = dt / math.exp(x[i])
            e, om = math.exp(-q), -math.expm1(-q)
            old = v[i]
            dv[i] = [e * value for value in dv[i]]
            dv[i][i] += q * e * (old - x[7 + i] * current)
            dv[i][7 + i] += om * current
            v[i] = e * old + om * x[7 + i] * current
        if dt != 0 and current != 0:
            index = 3 if current > 0 else 4
            sign = 1 if current > 0 else -1
            q = math.exp(x[index]) * (abs(current) / 3600) * dt
            e, om = math.exp(-q), -math.expm1(-q)
            old = h
            dh = [e * value for value in dh]
            dh[index] += -q * e * (old - sign)
            h = e * old + om * sign
        t = math.tanh(8 * (z - 0.5))
        slope = 1.15 + 0.64 * (1 - t * t)
        prediction = 3 + 1.15 * z + 0.08 * t
        for vi in v:
            prediction -= vi
        prediction -= x[6] * current + x[10] * h
        gradient = [
            slope * dz[k] - sum(dv[i][k] for i in range(3)) - x[10] * dh[k]
            for k in range(D)
        ]
        gradient[6] -= current
        gradient[10] -= h
        voltage.append(prediction)
        jacobians.append(gradient)
    endpoint = list(x[:11]) + [z, *v, h]
    derivative = [[float(i == j) for j in range(D)] for i in range(11)] + [dz] + dv + [dh]
    return {"voltage": voltage, "jacobians": jacobians, "endpoint": endpoint,
            "derivative": derivative, "charge": charge, "charge_min": charge_min,
            "charge_max": charge_max, "elapsed": elapsed}


class Checks:
    def __init__(self):
        self.items = []
        self.assertions = 0

    def require(self, condition: bool, message: str):
        self.assertions += 1
        if not condition:
            raise AssertionError(message)

    def compare(self, name, actual, expected, tolerances):
        self.require(len(actual) == len(expected) == len(tolerances), name + " dimensions")
        errors = [abs(a - b) for a, b in zip(actual, expected)]
        for index, (a, b, error, tolerance) in enumerate(zip(actual, expected, errors, tolerances)):
            self.require(math.isfinite(a) and math.isfinite(b) and error <= tolerance,
                         f"{name}[{index}]: {a!r} != {b!r}, error {error!r} > {tolerance!r}")
        self.items.append({
            "name": name, "status": "pass", "scalar_comparisons": len(actual),
            "maximum_absolute_error": max(errors, default=0),
            "maximum_error_over_tolerance": max(
                (e / t if t else 0 for e, t in zip(errors, tolerances)), default=0),
        })


def scalar_roundoff(reference: float, n: int, scale: float = 1.0) -> float:
    # Frozen engineering reconstruction tolerance, not a full-model certificate.
    return 256 * U * (n + 1) * max(1.0, abs(reference), abs(scale))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=AREA / "qualification/evaluator_run001")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    checks = Checks()
    children = []
    evaluator_counts = {"invocations": 0, "model_init_calls": 0, "model_step_calls": 0,
                        "model_predict_calls": 0, "records_accumulated": 0}
    source_paths = [
        Path(__file__).resolve(), AREA / "stream_evaluator.c", BASE / "src/scm_model.c",
        BASE / "include/scm_model.h", BASE / "src/scm_hypothesis.c",
        BASE / "plans/retained_likelihood_replacement_001.json",
    ]
    source_before = {str(p.relative_to(BASE)): digest(p) for p in source_paths}
    reference = None
    failure = None
    receipt = {
        "schema": SCHEMA, "status": "running", "source_sha256": source_before,
        "qualification_source": str(Path(__file__).resolve().relative_to(BASE)),
        "scope": "Only code literals and fabricated files created below this exclusive output directory; no archived observation, truth, checkpoint or original fitter access.",
        "arithmetic_policy": {
            "binary64_unit_roundoff": U,
            "reconstruction_tolerance": "256*u*(N+1)*max(1,|reference|,local_scale); cost/gradient/Gram tolerances propagate the separately allowed prediction and Jacobian errors into their summands.",
            "finite_difference": "Five-point central derivative with h=2e-5*max(1,|x_k|); tolerance is 256*u*(N+1)*max(1,|function|)/h + h^4*max(1,|derivative|).",
            "limitations": "These fixed fabricated reconstruction tolerances exercise code and mapping. They are not global libm/trajectory error bounds, statistical thresholds or coverage calibration.",
        },
    }
    write_json(output / "reservation.json", {
        "schema": SCHEMA, "source_sha256": source_before,
        "command": sys.argv, "canonical_runs_authorized": False,
    })
    try:
        compiler = os.environ.get("CC", "cc")
        flags = ["-std=c99", "-O2", "-Wall", "-Wextra", "-Wpedantic", "-Werror",
                 "-fno-fast-math", "-ffp-contract=off"]
        binary, library = output / "stream_evaluator.bin", output / "original_model.so"
        commands = [
            ("compiler_version", [compiler, "--version"]),
            ("build_evaluator", [
                compiler, *flags, "-fstack-usage", "-I", str(BASE / "include"),
                str(AREA / "stream_evaluator.c"), str(BASE / "src/scm_model.c"),
                "-lm", "-o", str(binary),
            ]),
            ("build_physical_reference", [
                compiler, *flags, "-shared", "-fPIC", "-I", str(BASE / "include"),
                str(BASE / "src/scm_model.c"), "-lm", "-o", str(library),
            ]),
        ]
        for label, command in commands:
            child = launch(command, output, label, output)
            children.append(child)
            checks.require(child["exit_code"] == 0 and not child["timed_out"], f"{label} failed")
        reference = PhysicalReference(library)
        x = [
            math.log(.05), math.log(.5), math.log(5), math.log(140), math.log(260),
            math.log(.065), .12, .18, .24, .16, .03, .62, .012, -.006, .009, .35,
        ]
        common_rows = [
            (.02, .06), (.13, -.04), (0., .09), (.7, 0.), (1.2, .03),
            (.08, -.07), (0., 0.), (.4, .02), (3., -.05),
        ]
        cases = [
            ("mixed_current", x, common_rows),
            ("zero_dt", x, [(0., .07)]),
            ("zero_current", x, [(0., 0.), (.03, 0.), (.7, 0.), (2., 0.)]),
            ("zero_samples", x, []),
            ("zero_H_chain", x[:10] + [0.] + x[11:], common_rows),
            ("buffer_boundary", x, [(.01, (-.04, 0., .06)[i % 3]) for i in range(129)]),
        ]
        records_by_name, x_files = {}, {}

        def invoke(label, x_path, observation_path, prefix, expected_error=None, extra=None):
            argv = [
                str(binary), "--x", str(x_path), "--sigma", "0.001",
                "--observations", str(observation_path), "--prefix", str(prefix),
                *(extra or []),
            ]
            child = launch(argv, output, label, output)
            children.append(child)
            payload = strict_json(output / child["stdout"])
            checks.require(payload["schema"] == "mumble_retained_likelihood_stream_evaluator_v1", label + " schema")
            checks.require(not child["timed_out"], label + " deadline")
            checks.require(child["stdout_bytes"] + child["stderr_bytes"] <= 128 * 1024, label + " output bound")
            checks.require(
                payload["source_generations"] == payload["learner_ingests"] ==
                payload["fit_calls"] == payload["truth_reads"] == 0, label + " forbidden calls",
            )
            if expected_error is None:
                checks.require(child["exit_code"] == 0 and payload["status"] == "ok", label + " success")
                checks.require(payload["records_read"] == payload["records_accumulated"] == prefix, label + " records")
                checks.require(payload["input_bytes_read"] == prefix * 32, label + " exact extent")
                checks.require(
                    payload["model_init_calls"] == 1 and
                    payload["model_step_calls"] == payload["model_predict_calls"] == prefix,
                    label + " API counters",
                )
            else:
                checks.require(
                    child["exit_code"] != 0 and payload["status"] == "error" and
                    payload["error"] == expected_error, label + " expected rejection",
                )
                checks.items.append({
                    "name": label, "status": "pass", "expected_error": expected_error,
                    "records_accumulated": payload["records_accumulated"],
                    "model_step_calls": payload["model_step_calls"],
                })
            evaluator_counts["invocations"] += 1
            for key in evaluator_counts:
                if key != "invocations":
                    evaluator_counts[key] += payload[key]
            return payload

        results = {}
        for name, entering, rows in cases:
            voltage, physical_endpoint = reference.trace(entering, rows)
            observed = [v + (i % 5 - 2) * .00031 for i, v in enumerate(voltage)]
            data = b"".join(
                struct.pack("<Qddd", i, dt, current, v)
                for i, ((dt, current), v) in enumerate(zip(rows, observed))
            )
            observation_path = output / f"{name}.observations.bin"
            x_path = output / f"{name}.x.txt"
            observation_path.write_bytes(data)
            x_path.write_text("\n".join(format(v, ".17g") for v in entering) + "\n")
            records_by_name[name], x_files[name] = (observation_path, data), x_path
            result = invoke(name, x_path, observation_path, len(rows))
            results[name] = result
            direct = direct_tangent(entering, rows)
            n = len(rows)
            checks.compare(name + "/physical_vs_direct_endpoint", physical_endpoint, direct["endpoint"],
                           [scalar_roundoff(v, n) for v in direct["endpoint"]])
            checks.compare(name + "/endpoint", result["endpoint_x"], direct["endpoint"],
                           [scalar_roundoff(v, n) for v in direct["endpoint"]])
            endpoint_jacobian = [value for row in direct["derivative"] for value in row]
            checks.compare(name + "/endpoint_derivative", result["endpoint_derivative"], endpoint_jacobian,
                           [scalar_roundoff(v, n) for v in endpoint_jacobian])
            physical_values = [math.exp(v) if i < 6 else v for i, v in enumerate(direct["endpoint"])]
            physical_jacobian = [
                (math.exp(entering[i]) if i < 6 else 1.) * endpoint_jacobian[i * D + j]
                for i in range(D) for j in range(D)
            ]
            checks.compare(name + "/physical_endpoint", result["endpoint_state"], physical_values,
                           [scalar_roundoff(v, n) for v in physical_values])
            checks.compare(name + "/physical_endpoint_derivative", result["endpoint_physical_derivative"], physical_jacobian,
                           [scalar_roundoff(v, n) for v in physical_jacobian])
            checks.compare(
                name + "/charge_time",
                [result[k] for k in ("charge_Ah", "charge_min_Ah", "charge_max_Ah", "elapsed_physical_s")],
                [direct[k] for k in ("charge", "charge_min", "charge_max", "elapsed")], [0.] * 4,
            )
            residuals = [(v - y) / SIGMA for v, y in zip(direct["voltage"], observed)]
            whitened = [[j / SIGMA for j in row] for row in direct["jacobians"]]
            dr = [scalar_roundoff(v, n) / SIGMA for v in direct["voltage"]]
            dj = [[scalar_roundoff(j, n) / SIGMA for j in row] for row in direct["jacobians"]]
            costs = [.5 * r * r for r in residuals]
            cost = math.fsum(costs)
            cost_tolerance = (
                math.fsum(abs(r) * d + .5 * d * d for r, d in zip(residuals, dr)) +
                scalar_roundoff(cost, n)
            )
            checks.compare(name + "/cost", [result["cost"]], [cost], [cost_tolerance])
            expected_g, expected_G, absolute_g, absolute_G, gt, Gt = [], [], [], [], [], []
            for i in range(D):
                terms = [r * row[i] for r, row in zip(residuals, whitened)]
                expected_g.append(math.fsum(terms))
                absolute_g.append(math.fsum(abs(v) for v in terms))
                gt.append(
                    math.fsum(
                        abs(r) * dji[i] + abs(row[i]) * dri + dri * dji[i]
                        for r, row, dri, dji in zip(residuals, whitened, dr, dj)
                    ) + scalar_roundoff(absolute_g[-1], n)
                )
                for j in range(i + 1):
                    terms = [row[i] * row[j] for row in whitened]
                    expected_G.append(math.fsum(terms))
                    absolute_G.append(math.fsum(abs(v) for v in terms))
                    Gt.append(
                        math.fsum(
                            abs(row[i]) * dji[j] + abs(row[j]) * dji[i] + dji[i] * dji[j]
                            for row, dji in zip(whitened, dj)
                        ) + scalar_roundoff(absolute_G[-1], n)
                    )
            checks.compare(name + "/gradient", result["gradient"], expected_g, gt)
            checks.compare(name + "/Gram", result["gram"], expected_G, Gt)
            checks.compare(name + "/absolute_gradient_terms", result["absolute_summand_scales"]["gradient"], absolute_g, gt)
            checks.compare(name + "/absolute_Gram_terms", result["absolute_summand_scales"]["gram"], absolute_G, Gt)
            checks.compare(name + "/absolute_cost_terms", [result["absolute_summand_scales"]["cost"]], [cost], [cost_tolerance])
            checks.require(result["charge_extrema_include_initial_zero"] is True, name + " initial charge included")
            checks.require(
                result["storage"]["read_buffer_bytes"] == 4096 and
                result["storage"]["observation_sized_arrays"] == 0, name + " fixed storage",
            )
            if rows:
                checks.compare(name + "/last_prediction", [result["last_record"]["predicted_voltage_V"]],
                               [voltage[-1]], [scalar_roundoff(voltage[-1], n)])
                checks.compare(name + "/last_J", result["last_record"]["whitened_prediction_jacobian"], whitened[-1], dj[-1])
            else:
                checks.require(result["last_record"] is None, "zero samples has no observation")
                checks.require(result["cost"] == 0 and all(v == 0 for v in result["gradient"] + result["gram"]),
                               "zero samples has zero information")
                checks.require(result["endpoint_x"] == entering, "zero samples has identity state")

        # Five-point differences use the separate direct physical C API.
        central = results["mixed_current"]
        fd_voltage, fd_tolerance_voltage, fd_tolerance_endpoint = [], [], []
        finite_difference_rows = [[0.] * D for _ in range(D)]
        h_values = []
        for k in range(D):
            step = 2e-5 * max(1., abs(x[k]))
            h_values.append(step)
            samples = {}
            for multiple in (-2, -1, 1, 2):
                xx = list(x)
                xx[k] += multiple * step
                samples[multiple] = reference.trace(xx, common_rows)
            derivative_v = math.fsum((
                -samples[2][0][-1], 8 * samples[1][0][-1],
                -8 * samples[-1][0][-1], samples[-2][0][-1],
            )) / (12 * step)
            fd_voltage.append(derivative_v / SIGMA)
            fd_tolerance_voltage.append((
                scalar_roundoff(central["last_record"]["predicted_voltage_V"], len(common_rows)) / step +
                step ** 4 * max(1., abs(derivative_v))
            ) / SIGMA)
            for row in range(D):
                derivative = math.fsum((
                    -samples[2][1][row], 8 * samples[1][1][row],
                    -8 * samples[-1][1][row], samples[-2][1][row],
                )) / (12 * step)
                finite_difference_rows[row][k] = derivative
                fd_tolerance_endpoint.append(
                    scalar_roundoff(central["endpoint_x"][row], len(common_rows)) / step +
                    step ** 4 * max(1., abs(derivative))
                )
        checks.compare("physical_five_point_last_voltage_derivative",
                       central["last_record"]["whitened_prediction_jacobian"], fd_voltage, fd_tolerance_voltage)
        fd_endpoint = [finite_difference_rows[i][j] for i in range(D) for j in range(D)]
        # Tolerances were appended column-major.
        fd_tolerance_endpoint = [fd_tolerance_endpoint[j * D + i] for i in range(D) for j in range(D)]
        checks.compare("physical_five_point_endpoint_derivative",
                       central["endpoint_derivative"], fd_endpoint, fd_tolerance_endpoint)
        receipt["finite_difference_steps"] = h_values

        zero_dt = results["zero_dt"]
        j = zero_dt["last_record"]["whitened_prediction_jacobian"]
        checks.require(j[10] == -x[15] / SIGMA and j[15] == -x[10] / SIGMA, "H*h exact zero-dt chain")
        checks.require(all(j[k] == 0 for k in (0, 1, 2, 3, 4, 5, 7, 8, 9)), "zero-dt unexcited derivatives")
        checks.require(results["zero_H_chain"]["last_record"]["whitened_prediction_jacobian"][15] == 0.,
                       "zero H removes voltage derivative with respect to h0")
        checks.require(results["zero_H_chain"]["last_record"]["whitened_prediction_jacobian"][10] != 0.,
                       "zero H retains derivative with respect to H")
        checks.items.append({"name": "analytic_H_times_h_and_zero_dt_controls", "status": "pass"})

        valid_x = x_files["mixed_current"]
        valid_file, valid_data = records_by_name["mixed_current"]
        malformed = [
            ("truncated_record", valid_data[:-1], 9, "truncated_prefix"),
            ("wrong_first_index", struct.pack("<Q", 1) + valid_data[8:], 9, "unordered_record_index"),
            ("duplicate_index", valid_data[:32] + struct.pack("<Q", 0) + valid_data[40:], 9, "unordered_record_index"),
            ("nonfinite_dt", struct.pack("<Qddd", 0, float("nan"), .01, 3.7), 1, "nonfinite_record"),
            ("nonfinite_current", struct.pack("<Qddd", 0, .01, float("inf"), 3.7), 1, "nonfinite_record"),
            ("nonfinite_voltage", struct.pack("<Qddd", 0, .01, .01, float("inf")), 1, "nonfinite_record"),
            ("negative_dt", struct.pack("<Qddd", 0, -.01, .01, 3.7), 1, "negative_dt"),
            ("SOC_domain_exit", struct.pack("<Qddd", 0, 10000., .1, 3.7), 1, "model_step_failed"),
            ("finite_record_cost_overflow", struct.pack("<Qddd", 0, 0., 0., -1e308), 1, "nonfinite_cost_accumulation"),
        ]
        for label, data, prefix, expected_error in malformed:
            path = output / f"{label}.observations.bin"
            path.write_bytes(data)
            invoke(label, valid_x, path, prefix, expected_error)
        for label, text, expected_error in [
            ("x_extra_value", valid_x.read_text() + "0\n", "invalid_x_file"),
            ("x_nonfinite", "nan\n" + "\n".join(str(v) for v in x[1:]), "invalid_x_file"),
            ("x_missing_value", "\n".join(str(v) for v in x[:-1]), "invalid_x_file"),
            ("x_outside_entering_support", "\n".join(str(v) for v in x[:11] + [.1] + x[12:]), "entering_support_or_init_failed"),
        ]:
            path = output / f"{label}.x.txt"
            path.write_text(text)
            rejected = invoke(label, path, valid_file, 9, expected_error)
            checks.require(rejected["model_step_calls"] == 0, label + " no model step")
        invoke("prefix_over_cap", valid_x, valid_file, 252001, "invalid_prefix")
        invoke("duplicate_sigma_option", valid_x, valid_file, 9, "unknown_or_repeated_option", ["--sigma", "0.002"])
        suffix = output / "unread_suffix.observations.bin"
        suffix.write_bytes(valid_data[:32] + b"bad suffix that is not a record")
        suffix_result = invoke("exact_prefix_ignores_suffix", valid_x, suffix, 1)
        checks.require(suffix_result["input_bytes_read"] == 32, "No read beyond prefix")
        checks.items.append({"name": "exact_prefix_ignores_suffix", "status": "pass", "input_bytes_read": 32})
        receipt["binary_sha256"] = digest(binary)
        receipt["binary_bytes"] = binary.stat().st_size
        receipt["physical_reference_library_sha256"] = digest(library)
        receipt["compiler_version"] = (output / "compiler_version.stdout").read_text().strip()
        receipt["storage"] = results["mixed_current"]["storage"]
    except Exception as error:
        failure = {"type": type(error).__name__, "message": str(error)}
    source_after = {str(p.relative_to(BASE)): digest(p) for p in source_paths}
    receipt.update({
        "status": "pass" if failure is None and source_before == source_after else "fail",
        "failure": failure, "checks": checks.items, "assertions_executed": checks.assertions,
        "check_groups_completed": len(checks.items), "children": children,
        "evaluator_counts_on_fabricated_inputs": evaluator_counts,
        "direct_physical_reference_calls_on_fabricated_inputs": reference.calls if reference else 0,
        "canonical_observation_reads": 0, "canonical_model_passes": 0, "canonical_truth_reads": 0,
        "original_fitter_invocations": 0, "learner_invocations": 0,
        "source_sha256_after": source_after, "sources_unchanged": source_before == source_after,
        "supervisor_own_peak_RSS_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        "wall_s_before_receipt": time.monotonic() - started,
        "environment": {"python": sys.version, "platform": sys.platform, "uname": list(os.uname())},
        "limitations": [
            "Fabricated qualification only; source/binary require independent review and publication before canonical use.",
            "No production or canonical archive file was opened for model evaluation or truth scoring.",
            "The sizeof accounting is not complete target SRAM and evaluator peak RSS is a host measurement.",
            "No likelihood optimum, calibrated uncertainty, global numerical guarantee or firmware readiness is established.",
        ],
    })
    receipt["artifacts_before_receipt"] = {
        str(p.relative_to(output)): {"bytes": p.stat().st_size, "sha256": digest(p)}
        for p in sorted(output.rglob("*")) if p.is_file()
    }
    write_json(output / "receipt.json", receipt)
    print(json.dumps({
        "status": receipt["status"], "receipt": str(output / "receipt.json"),
        "assertions": checks.assertions, "check_groups": len(checks.items),
        "failure": failure, "canonical_model_passes": 0,
    }, allow_nan=False))
    return 0 if receipt["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
