#!/usr/bin/env python3
"""Small independent physical-model/Jacobian checks for offline sensitivity.

Uses public constructed coordinates only. It imports no saved estimates, input
trace, synthetic truth manifest, estimator, optimizer, or scoring program.
First execution failures remain in an append-only attempts list in the JSON
design receipt; an implementation fix requires a separately recorded attempt.
"""
from __future__ import annotations

import argparse
import copy
import ctypes
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import traceback

import numpy as np

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECEIPT = ROOT / "experiments/parameter_sensitivity_001/development/independent_check_design.json"
RATE = 35
DT = 1.0 / RATE
PHYSICAL_ATOL = 1e-10
JACOBIAN_ATOL = 1e-7
JACOBIAN_RTOL = 1e-6
FD_STEP = 2e-6
COORDINATES = ["log_tau1", "log_tau2", "log_tau3", "log_gamma_plus",
               "log_gamma_minus", "log_Q_Ah", "R0", "R1", "R2", "R3",
               "H", "initial_z", "initial_v1", "initial_v2", "initial_v3", "initial_h"]


def public_vector(kind: str) -> np.ndarray:
    if kind == "interior":
        return np.r_[np.log([.04, .4, 4., 180., 260., .08]),
                     [.15, .12, .19, .28, .025, .62, .003, -.002, .004, -.2]]
    if kind == "separated_time_scales":
        return np.r_[np.log([.006, .31, 9., 80., 450., .075]),
                     [.08, .03, .17, .41, .02, .37, -.004, .006, -.002, .35]]
    raise ValueError(kind)


PROTOCOLS = {
    "rest": [{"current_A": 0., "samples": 35}],
    "discharge": [{"current_A": .04, "samples": 70}],
    "charge": [{"current_A": -.05, "samples": 70}],
    "mixed": [{"current_A": 0., "samples": 7},
              {"current_A": .06, "samples": 21},
              {"current_A": -.035, "samples": 35},
              {"current_A": 0., "samples": 14},
              {"current_A": .015, "samples": 11}],
}


class Physical(ctypes.Structure):
    _fields_ = [("modes", ctypes.c_int), ("R0", ctypes.c_double),
                ("R", ctypes.c_double * 3), ("tau", ctypes.c_double * 3),
                ("H", ctypes.c_double), ("gamma_plus", ctypes.c_double),
                ("gamma_minus", ctypes.c_double), ("Q", ctypes.c_double)]


class State(ctypes.Structure):
    _fields_ = [("z", ctypes.c_double), ("v", ctypes.c_double * 3),
                ("h", ctypes.c_double)]


def production_stepper(library: Path):
    library_handle = ctypes.CDLL(str(library))
    step = library_handle.scm_physical_step
    step.argtypes = [ctypes.POINTER(Physical), ctypes.POINTER(State),
                     ctypes.c_void_p, ctypes.c_double, ctypes.c_double,
                     ctypes.POINTER(ctypes.c_double)]
    step.restype = ctypes.c_int
    return library_handle, step


def production_trajectory(step, x: np.ndarray, segments: list[dict]) -> dict:
    p = Physical(3, x[6], (ctypes.c_double * 3)(*x[7:10]),
                 (ctypes.c_double * 3)(*np.exp(x[:3])), x[10],
                 math.exp(x[3]), math.exp(x[4]), math.exp(x[5]))
    state = State(x[11], (ctypes.c_double * 3)(*x[12:15]), x[15])
    current = np.r_[segments[0]["current_A"],
                    np.concatenate([np.full(s["samples"], s["current_A"]) for s in segments])]
    result = {"time_s": np.arange(len(current)) * DT, "current_A": current,
              "voltage_V": np.empty(len(current)), "z": np.empty(len(current)),
              "v": np.empty((len(current), 3)), "h": np.empty(len(current))}
    voltage = ctypes.c_double()
    for i, amps in enumerate(current):
        code = step(ctypes.byref(p), ctypes.byref(state), None,
                    0. if i == 0 else DT, float(amps), ctypes.byref(voltage))
        if code:
            raise RuntimeError(f"Production physical step failed at sample {i}: {code}")
        result["voltage_V"][i] = voltage.value
        result["z"][i] = state.z
        result["v"][i] = state.v
        result["h"][i] = state.h
    return result


def single_dwell_reference(x: np.ndarray, current: float, count: int) -> dict:
    """Direct independent formulas; no root propagator/Jacobian helper calls."""
    time = np.arange(count + 1) * DT
    tau, gp, gm, capacity = np.exp(x[:3]), math.exp(x[3]), math.exp(x[4]), math.exp(x[5])
    e = np.exp(-time[:, None] / tau)
    v = current * x[7:10] + (x[12:15] - current * x[7:10]) * e
    delta_soc = current * time / (3600. * capacity)
    z = x[11] - delta_soc
    sign = 1. if current > 0 else -1.
    gamma = gp if current > 0 else gm
    q = gamma * abs(current) * time / 3600.
    eh = np.exp(-q)
    h = np.full(count + 1, x[15]) if current == 0 else sign + (x[15] - sign) * eh
    t = np.tanh(8. * (z - .5))
    slope = 1.15 + .64 * (1. - t*t)
    voltage = 3. + 1.15*z + .08*t - current*x[6] - v.sum(axis=1) - x[10]*h
    jz, jv = np.zeros((count + 1, 16)), np.zeros((count + 1, 16))
    jz[:, 5], jz[:, 11] = delta_soc, 1.
    jv[:, :3] = -(x[12:15] - current*x[7:10]) * e * (time[:, None] / tau)
    if current != 0:
        jv[:, 3 if current > 0 else 4] = -x[10] * q * eh * (sign - x[15])
    jv[:, 5], jv[:, 6] = slope*delta_soc, -current
    jv[:, 7:10] = -current * (1. - e)
    jv[:, 10], jv[:, 11] = -h, slope
    jv[:, 12:15], jv[:, 15] = -e, -x[10]*eh
    return {"time_s": time, "current_A": np.full(count + 1, current),
            "voltage_V": voltage, "z": z, "v": v, "h": h,
            "voltage_jacobian": jv, "soc_jacobian": jz}


class Checks:
    def __init__(self):
        self.assertions = 0
        self.failures = []
        self.comparisons = []

    def require(self, condition, label: str):
        self.assertions += 1
        if not condition:
            self.failures.append({"check": label})

    def compare(self, got, expected, label: str, atol=PHYSICAL_ATOL, rtol=0.):
        got, expected = np.asarray(got), np.asarray(expected)
        self.assertions += 1
        if got.shape != expected.shape:
            self.failures.append({"check": label, "shape": list(got.shape),
                                  "expected_shape": list(expected.shape)})
            return
        finite = np.isfinite(got) & np.isfinite(expected)
        error = np.abs(got - expected)
        tolerance = atol + rtol*np.abs(expected)
        failed = (~finite) | (error > tolerance)
        record = {"check": label, "entries": int(error.size),
                  "failed_entries": int(failed.sum()), "absolute_tolerance": atol,
                  "relative_tolerance": rtol}
        if np.all(finite):
            record["max_absolute_error"] = float(error.max(initial=0.))
            record["max_tolerance_ratio"] = float((error/tolerance).max(initial=0.))
            meaningful = np.abs(expected) >= 1e-6
            record["max_relative_error_where_reference_abs_ge_1e_6"] = float(
                (error[meaningful]/np.abs(expected[meaningful])).max(initial=0.))
            if got.ndim == 2 and got.shape[1] == 16:
                record["per_coordinate_max_absolute_error"] = error.max(axis=0).tolist()
        if np.any(failed):
            location = tuple(int(k) for k in np.argwhere(failed)[0])
            self.failures.append({"check": label, "first_failed_index": list(location),
                                  "actual": float(got[location]) if np.isfinite(got[location]) else str(got[location]),
                                  "expected": float(expected[location]) if np.isfinite(expected[location]) else str(expected[location])})
        self.comparisons.append(record)


def finite_difference(module, x, segments):
    total = 1 + sum(s["samples"] for s in segments)
    jv, jz = np.empty((total, 16)), np.empty((total, 16))
    for i in range(16):
        epsilon = FD_STEP * max(1., abs(x[i]))
        plus, minus = x.copy(), x.copy()
        plus[i] += epsilon
        minus[i] -= epsilon
        a, b = module.propagate(plus, segments), module.propagate(minus, segments)
        jv[:, i] = (a["voltage_V"] - b["voltage_V"]) / (2.*epsilon)
        jz[:, i] = (a["z"] - b["z"]) / (2.*epsilon)
    return jv, jz


def run_checks(module, step, checks: Checks) -> Checks:
    for kind in ("interior", "separated_time_scales"):
        for name, frozen_segments in PROTOCOLS.items():
            label = kind + "/" + name
            x, segments = public_vector(kind), copy.deepcopy(frozen_segments)
            original_x, original_segments = x.copy(), copy.deepcopy(segments)
            got = module.propagate(x, segments, jacobian=True)
            checks.require(np.array_equal(x, original_x) and segments == original_segments, label+"/inputs_unchanged")
            reference = production_trajectory(step, x, segments)
            for key in ("time_s", "current_A", "voltage_V", "z", "v", "h"):
                checks.compare(got[key], reference[key], label+"/production/"+key,
                               atol=1e-12 if key in ("time_s", "current_A") else PHYSICAL_ATOL)
            jv, jz = finite_difference(module, x, segments)
            checks.compare(got["voltage_jacobian"], jv, label+"/central_difference/voltage",
                           JACOBIAN_ATOL, JACOBIAN_RTOL)
            checks.compare(got["soc_jacobian"], jz, label+"/central_difference/SOC",
                           JACOBIAN_ATOL, JACOBIAN_RTOL)
            plain = module.propagate(x, segments)
            for key in ("time_s", "current_A", "voltage_V", "z", "v", "h"):
                checks.compare(plain[key], got[key], label+"/jacobian_flag_invariance/"+key)
            if len(segments) == 1:
                expected = single_dwell_reference(x, segments[0]["current_A"], segments[0]["samples"])
                for key in ("voltage_V", "z", "v", "h", "voltage_jacobian", "soc_jacobian"):
                    checks.compare(got[key], expected[key], label+"/closed_form/"+key)
            if name == "rest":
                checks.require(np.array_equal(got["h"], np.full(len(got["h"]), x[15])), label+"/h_unchanged_at_rest")
                checks.require(np.all(got["voltage_jacobian"][:, 3:6] == 0.), label+"/no_gamma_or_Q_information_at_rest")
    # Same physical dwell expressed as three pieces: no state/Jacobian restart.
    x = public_vector("interior")
    a = module.propagate(x, [{"current_A": .031, "samples": 39}], jacobian=True)
    b = module.propagate(x, [{"current_A": .031, "samples": n} for n in (13, 17, 9)], jacobian=True)
    for key in ("time_s", "current_A", "voltage_V", "z", "v", "h", "voltage_jacobian", "soc_jacobian"):
        checks.compare(a[key], b[key], "dwell_partition_invariance/"+key)
    # Unambiguous derivative directions at the first positive-duration sample.
    x[12:16] = 0.
    for current in (.04, -.04):
        got = module.propagate(x, [{"current_A": current, "samples": 35}], jacobian=True)
        sign, active, inactive = (1., 3, 4) if current > 0 else (-1., 4, 3)
        jac = got["voltage_jacobian"]
        checks.require(np.all(sign*jac[1, :3] > 0.), f"sign/{current}/tau")
        checks.require(sign*jac[1, active] < 0., f"sign/{current}/active_gamma")
        checks.require(np.all(jac[:, inactive] == 0.), f"sign/{current}/inactive_gamma")
        checks.require(sign*jac[1, 5] > 0. and sign*got["soc_jacobian"][1, 5] > 0., f"sign/{current}/capacity")
        checks.require(np.all(jac[0, 12:15] == -1.) and jac[0, 15] == -x[10], f"sign/{current}/entering_state_columns")
    # Domain errors must not silently extrapolate the known OCV chart.
    invalids = []
    for coordinate, value, label in [(0, float("nan"), "nonfinite"),
                                      (6, -.01, "negative_R0"), (10, -.01, "negative_H"),
                                      (11, -.01, "initial_SOC_outside"), (15, 1.01, "initial_h_outside")]:
        bad = public_vector("interior"); bad[coordinate] = value
        invalids.append((bad, [{"current_A": 0., "samples": 1}], label))
    bad = public_vector("interior"); bad[11] = 1e-8
    invalids.append((bad, [{"current_A": .2, "samples": 1}], "propagated_SOC_outside"))
    for bad, segments, label in invalids:
        try:
            module.propagate(bad, segments, jacobian=True)
        except ValueError:
            checks.require(True, "invalid/"+label)
        except Exception as exc:
            checks.require(False, "invalid/"+label+"/wrong_exception_"+type(exc).__name__)
        else:
            checks.require(False, "invalid/"+label+"/not_rejected")
    return checks


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", type=Path, default=ROOT/"tools/parameter_sensitivity.py")
    parser.add_argument("--library", type=Path, default=ROOT/"build/parameter_sensitivity/libscm_model.so")
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--qualification", type=Path,
                        default=ROOT/"experiments/parameter_sensitivity_001/development/qualification.json")
    args = parser.parse_args()
    if not args.module.is_file():
        parser.error("Root sensitivity module does not exist yet; no check attempt was run")
    receipt = json.loads(args.receipt.read_text())
    attempt = {"started_utc": datetime.now(timezone.utc).isoformat(),
               "source_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
               "source_sha256": {str(p.relative_to(ROOT)): digest(p) for p in
                   [Path(__file__).resolve(), args.module.resolve(), ROOT/"src/scm_model.c", ROOT/"include/scm_model.h"]},
               "command": [sys.executable, *sys.argv], "numpy_version": np.__version__,
               "fixture_count": 8, "saved_truth_or_estimates_read": False,
               "old_test_or_estimator_executions": 0}
    args.library.parent.mkdir(parents=True, exist_ok=True)
    command = ["cc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
               "-fPIC", "-shared", "-Iinclude", "src/scm_model.c", "-lm", "-o", str(args.library.resolve())]
    build = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    attempt["build"] = {"command": command, "returncode": build.returncode,
                        "stdout": build.stdout, "stderr": build.stderr}
    checks = Checks()
    try:
        if build.returncode:
            raise RuntimeError("Independent production shared-library build failed")
        attempt["production_library_sha256"] = digest(args.library)
        spec = importlib.util.spec_from_file_location("sensitivity_under_test", args.module)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        library_handle, step = production_stepper(args.library.resolve())
        checks = run_checks(module, step, checks)
        del library_handle
    except Exception:
        attempt["exception"] = traceback.format_exc()
    for path, before in attempt["source_sha256"].items():
        checks.require(digest(ROOT/path) == before, "source_unchanged_during_check/"+path)
    attempt.update({"finished_utc": datetime.now(timezone.utc).isoformat(),
                    "assertions": checks.assertions, "comparisons": checks.comparisons,
                    "failures": checks.failures,
                    "passed": not checks.failures and "exception" not in attempt})
    receipt.setdefault("attempts", []).append(attempt)
    receipt["status"] = "passed_before_primary" if attempt["passed"] else "failed_before_primary_preserved"
    receipt["latest_passed"] = attempt["passed"]
    args.receipt.write_text(json.dumps(receipt, indent=2, allow_nan=False)+"\n")
    qualification = {"schema": "mumble_parameter_sensitivity_qualification_v1",
                     "passed": attempt["passed"], "source_sha256": attempt["source_sha256"],
                     "source_revision": attempt["source_revision"],
                     "completed_utc": attempt["finished_utc"],
                     "independent_check_receipt": str(args.receipt.relative_to(ROOT)),
                     "independent_check_receipt_sha256": digest(args.receipt),
                     "attempts_preserved": len(receipt["attempts"]),
                     "assertions": checks.assertions,
                     "failures": checks.failures,
                     "production_library_sha256": attempt.get("production_library_sha256"),
                     "scope": "Finite public physical/Jacobian fixtures only; no saved Cell B vectors, estimator or primary diagnostic protocols."}
    args.qualification.write_text(json.dumps(qualification, indent=2, allow_nan=False)+"\n")
    maxima = {}
    for label in ("/production/", "/central_difference/", "/closed_form/"):
        maxima[label.strip("/")] = max((c.get("max_absolute_error", 0.) for c in checks.comparisons if label in c["check"]), default=None)
    print(json.dumps({"status": receipt["status"], "attempt": len(receipt["attempts"]),
                      "assertions": checks.assertions, "failures": checks.failures,
                      "exception": attempt.get("exception"), "max_absolute_errors": maxima,
                      "receipt": str(args.receipt)}, allow_nan=False))
    return 0 if attempt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
