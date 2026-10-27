#!/usr/bin/env python3
"""One fabricated build/run. No observations, model, prior, or optimizer import.

The frozen JSON plan supplies identities and the finite fixture names. Decimal
vertex enumeration is independent of the C edge-segment implementation.
"""
import argparse
import copy
import ctypes as C
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

N = 16
P = 136
A16 = C.c_double * N


class Workspace(C.Structure):
    _fields_ = [("packed", C.c_double * P), ("gradient", A16),
                ("point", A16), ("majorizer", A16), ("direction", A16)]


class Input(C.Structure):
    _fields_ = [(n, C.POINTER(C.c_double)) for n in ("anchor", "sd", "lower", "upper")]
    _fields_ += [("charge_min_Ah", C.c_double), ("charge_max_Ah", C.c_double)]


DOUBLE_RESULTS = ["original_slope", "original_slope_allowance", "tangent_model_decrease",
                  "tangent_model_allowance", "diagonal_model_decrease", "diagonal_model_allowance",
                  "min_support_slack", "min_step_slack", "min_polygon_slack", "minimum_majorizer"]
COUNTERS = ["edges_considered", "plane_tests", "candidates_considered", "selected_candidate",
            "cholesky_entries", "cholesky_products", "dot_products", "quadratic_products"]


class Result(C.Structure):
    _fields_ = [(n, C.c_double) for n in DOUBLE_RESULTS]
    _fields_ += [("status", C.c_int32), ("reason", C.c_int32)]
    _fields_ += [(n, C.c_uint32) for n in COUNTERS]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clean(value):
    if isinstance(value, float) and not math.isfinite(value):
        return repr(value)
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    return value


def base():
    return dict(anchor=[0.] * 11 + [.5] + [0.] * 4, sd=[.25] * N,
                lower=[-4.] * 11 + [0.] + [-4.] * 3 + [-1.],
                upper=[4.] * 11 + [1.] + [4.] * 3 + [1.],
                gradient=[0.] * N, metric=[[4. if i == j else 0. for j in range(N)] for i in range(N)],
                charge_min=0., charge_max=0.)


def fixtures():
    out = []
    a = base();a["gradient"][0] = .08;a["gradient"][5] = .04;a["gradient"][11] = -.08
    a["metric"][0][5] = a["metric"][5][0] = 1.
    a["metric"][0][11] = a["metric"][11][0] = .5
    a.update(charge_min=-.125, charge_max=.125)
    out.append(("dense_interior", a, 0, 0))
    a = base();a["anchor"][15] = -1.;a["gradient"][15] = .8;a["gradient"][0] = .2
    out.append(("active_h_other_descent", a, 0, 0))
    for name, z, cm, cp, gz in (("lower_soc_face", .75, 0., .25, .5),
                               ("upper_soc_face", .25, -.25, 0., -.5)):
        a = base();a["sd"][5] = a["sd"][11] = 1.;a["anchor"][11] = z
        a["metric"][5][5] = a["metric"][11][11] = 1.
        a["gradient"][5] = 1.0625;a["gradient"][11] = gz
        a.update(charge_min=cm, charge_max=cp)
        out.append((name, a, 0, 0))
    out.append(("zero_gradient", base(), 1, 1))
    a = base();a["sd"][5] = 1.;a["metric"][5][5] = 1.;a["gradient"][5] = -8.
    out.append(("reciprocal_log_trust", a, 0, 0))
    a = base();a["lower"][5] = a["upper"][5] = 0.
    a["lower"][11] = a["upper"][11] = .5;a["gradient"][0] = .2
    out.append(("fixed_qz_parallel", a, 0, 0))
    a = base();a["gradient"][2] = float("nan")
    out.append(("nonfinite_input_unchanged", a, -2, None))
    a = base();a["metric"][0][0] = a["metric"][1][1] = 1.
    a["metric"][0][1] = a["metric"][1][0] = 2.;a["gradient"][0] = .2
    out.append(("indefinite_metric", a, -4, 5))
    a = base();a["metric"] = [[0.] * N for _ in range(N)]
    out.append(("zero_metric", a, -4, 5))
    a = base();a["sd"][0] = 2.;a["metric"][0][0] = sys.float_info.max
    out.append(("nonfinite_scaled_metric", a, -2, 4))
    a = base();a["alias_anchor"] = True
    out.append(("input_alias_unchanged", a, -5, None))
    a = base();a["anchor"][5] = float.fromhex("0x1.193ea7aad030bp+0")
    a["anchor"][11] = float.fromhex("0x1.5555555555554p-2")
    a["charge_max"] = 1.;a["gradient"][0] = .2
    out.append(("reciprocal_anchor_rounding", a, 1, 2))
    a = base();a["anchor"][15] = -2.
    out.append(("invalid_support_unchanged", a, -3, None))
    return out


def geometry(a):
    x, s = a["anchor"], a["sd"]
    q0 = math.exp(-x[5]);qs = q0 * s[5]
    lo = max(a["lower"][5], x[5] - s[5]);hi = min(a["upper"][5], x[5] + s[5])
    qlo = (math.exp(-hi) - q0) / qs;qhi = (math.exp(-lo) - q0) / qs
    zlo = max(-1., (a["lower"][11] - x[11]) / s[11])
    zhi = min(1., (a["upper"][11] - x[11]) / s[11])
    return [(-1., 0., -qlo), (1., 0., qhi), (0., -1., -zlo), (0., 1., zhi),
            (a["charge_max"] * qs, -s[11], x[11] - a["charge_max"] * q0),
            (-a["charge_min"] * qs, s[11], 1. - x[11] + a["charge_min"] * q0)]


def polygon_reference(a, m):
    """80-digit unconstrained, line-normal, and pair-vertex enumeration."""
    with localcontext() as ctx:
        ctx.prec = 80
        D = Decimal.from_float
        planes = [(D(x), D(y), D(z)) for x, y, z in geometry(a)]
        mx, my = D(m[5]), D(m[11])
        hx = D(-a["sd"][5] * a["gradient"][5]);hy = D(a["sd"][11] * a["gradient"][11])
        tx, ty = -hx / mx, -hy / my
        cand = [(Decimal(0), Decimal(0)), (tx, ty)]
        for aa, bb, cc in planes:
            den = aa * aa / mx + bb * bb / my
            if den:
                lam = (aa * tx + bb * ty - cc) / den
                cand.append((tx - lam * aa / mx, ty - lam * bb / my))
        for i, (aa, bb, cc) in enumerate(planes):
            for dd, ee, ff in planes[:i]:
                det = aa * ee - bb * dd
                if det:
                    cand.append(((cc * ee - bb * ff) / det, (aa * ff - cc * dd) / det))
        # Decimal division can leave an ~1e-79 residual; this bound is an
        # oracle arithmetic allowance only, never estimator feasibility.
        tol = Decimal("1e-70")
        cand = [(x, y) for x, y in cand if all(aa * x + bb * y <= cc + tol for aa, bb, cc in planes)]
        vals = [(hx * x + hy * y + (mx * x * x + my * y * y) / 2, x, y) for x, y in cand]
        best = min(vals)
        return [float(v) for v in best], len(cand)


def exact_diagnostics(a, w):
    F = Fraction.from_float
    J = [(-s if i == 5 else s) for i, s in enumerate(a["sd"])]
    A = [[a["metric"][i][j] * (J[i] * J[j]) for j in range(N)] for i in range(N)]
    t = [F(v) for v in w.direction]
    h = [F(J[i] * a["gradient"][i]) for i in range(N)]
    original = -sum(F(a["gradient"][i]) * (F(w.point[i]) - F(a["anchor"][i])) for i in range(N))
    linear = sum(h[i] * t[i] for i in range(N))
    quad = sum(F(A[i][j]) * t[i] * t[j] for i in range(N) for j in range(N))
    diag = sum(F(w.majorizer[i]) * t[i] * t[i] for i in range(N))
    return A, original, -(linear + quad / 2), -(linear + diag / 2)


def check_case(lib, name, a, expected, reason):
    checks = []
    def check(label, condition):
        checks.append({"check": label, "passed": bool(condition)})
    arrays = [A16(*a[k]) for k in ("anchor", "sd", "lower", "upper")]
    inp = Input(*arrays, a["charge_min"], a["charge_max"])
    w = Workspace()
    for i in range(N):
        w.gradient[i] = a["gradient"][i]
        w.point[i] = a["anchor"][i] if a.get("alias_anchor") else 123.
        w.majorizer[i] = w.direction[i] = 123.
        for j in range(i + 1):
            w.packed[i * (i + 1) // 2 + j] = a["metric"][i][j]
    if a.get("alias_anchor"):
        inp.anchor = C.cast(C.byref(w, Workspace.point.offset), C.POINTER(C.c_double))
    r = Result();C.memset(C.byref(r), 0xA5, C.sizeof(r))
    before_w, before_r = bytes(w), bytes(r)
    before_arrays = [bytes(x) for x in arrays]
    status = lib.ss_propose(C.byref(inp), C.byref(w), C.byref(r))
    check("expected_status", status == expected)
    if reason is not None:
        check("expected_reason", r.reason == reason)
        check("returned_status_matches_result", r.status == status)
    check("read_only_arrays_unchanged", before_arrays == [bytes(x) for x in arrays])
    if reason is None:
        check("prevalidation_workspace_unchanged", bytes(w) == before_w)
        check("prevalidation_result_unchanged", bytes(r) == before_r)
        return dict(name=name, input=clean(a), status=status, checks=checks,
                    workspace_before_sha256=hashlib.sha256(before_w).hexdigest(),
                    workspace_after_sha256=hashlib.sha256(bytes(w)).hexdigest())
    check("gradient_unchanged", list(w.gradient) == a["gradient"])
    check("finite_fixed_edge_work", r.edges_considered <= 6 and r.plane_tests <= 90 and r.candidates_considered <= 8)
    check("finite_fixed_matrix_work", r.cholesky_entries <= 136 and r.cholesky_products <= 680
          and r.dot_products <= 32 and r.quadratic_products <= 272)
    data = dict(name=name, input=a, status=status, result={k: getattr(r, k) for k in DOUBLE_RESULTS + ["status", "reason"] + COUNTERS},
                point=list(w.point), direction=list(w.direction), majorizer=list(w.majorizer), checks=checks)
    if status >= 0 and reason != 2:
        A, so, sm, sd = exact_diagnostics(a, w)
        for i in range(N):
            check("row_majorizer_%02d" % i, Fraction.from_float(w.majorizer[i]) >= sum(Fraction.from_float(abs(v)) for v in A[i]))
        for label, exact, got, limit in (("original_slope", so, r.original_slope, r.original_slope_allowance),
                                        ("tangent_model", sm, r.tangent_model_decrease, r.tangent_model_allowance),
                                        ("diagonal_model", sd, r.diagonal_model_decrease, r.diagonal_model_allowance)):
            check(label + "_exact_operand_allowance", abs(Fraction.from_float(got) - exact) <= Fraction.from_float(limit))
        oracle, feasible_count = polygon_reference(a, list(w.majorizer))
        hx = -a["sd"][5] * a["gradient"][5];hy = a["sd"][11] * a["gradient"][11]
        x, y = w.direction[5], w.direction[11]
        observed = hx * x + hy * y + .5 * ((w.majorizer[5] * x) * x + (w.majorizer[11] * y) * y)
        tol = 512 * sys.float_info.epsilon * max(1., abs(observed), abs(oracle[0]))
        check("independent_polygon_cost", abs(observed - oracle[0]) <= tol)
        check("independent_polygon_point", max(abs(x - oracle[1]), abs(y - oracle[2])) <= 2048 * sys.float_info.epsilon * max(1., abs(x), abs(y)))
        data["polygon_oracle"] = dict(cost=oracle[0], t5=oracle[1], t11=oracle[2], feasible_candidates=feasible_count, cost_tolerance=tol)
        check("complete_cholesky_work", r.cholesky_entries == 136 and r.cholesky_products == 680)
        maximum = 0.
        for i in range(N):
            for j in range(N):
                restored = math.fsum(w.packed[i*(i+1)//2+k] * w.packed[j*(j+1)//2+k] for k in range(min(i, j)+1))
                maximum = max(maximum, abs(restored - A[i][j]))
        check("unmodified_scaled_cholesky", maximum <= 128 * sys.float_info.epsilon * max(1., max(abs(v) for row in A for v in row)))
        data["cholesky_max_error"] = maximum
    if status == 0:
        check("strict_original_support", r.min_support_slack >= 0. and r.min_step_slack >= 0.)
        check("resolved_original_descent", r.original_slope > r.original_slope_allowance)
        check("resolved_both_model_decreases", r.tangent_model_decrease > r.tangent_model_allowance and r.diagonal_model_decrease > r.diagonal_model_allowance)
    if name == "dense_interior":
        check("reciprocal_cross_term_sign", A[0][5] < 0. and A[0][11] > 0.)
    if name == "active_h_other_descent":
        check("active_h_preserved_other_axis_moves", w.point[15] == -1. and w.point[0] < 0.)
    if name in ("lower_soc_face", "upper_soc_face"):
        check("coupled_Q_SOC_both_move", w.point[5] != a["anchor"][5] and w.point[11] != a["anchor"][11])
        check("known_coupled_solution", abs(w.point[5] + math.log(2.)) <= 128 * sys.float_info.epsilon and w.point[11] == .5)
    if name == "reciprocal_log_trust":
        check("original_log_trust_preserved", abs(w.point[5]) <= 1. and abs(w.direction[5] - (math.exp(-1.) - 1.)) < 128 * sys.float_info.epsilon)
    if name == "zero_gradient":
        check("zero_gradient_exact_anchor", list(w.point) == a["anchor"])
    if name == "reciprocal_anchor_rounding":
        check("rounding_rejection_not_clipping", status == 1 and r.reason == 2 and r.original_slope == 0.)
    return data


def stack_account(files):
    frames = {}
    for p in files:
        for line in p.read_text().splitlines():
            fields = line.split("\t")
            if len(fields) >= 3:
                name = fields[0].split(":")[-1].split(".")[0]
                frames[name] = max(frames.get(name, 0), int(fields[1]))
                if fields[2] != "static":
                    raise RuntimeError("non-static own stack: " + line)
    graph = {"ss_propose": ["validate", "geometry", "scaled_metric", "select_point", "diagnostics", "cholesky", "original_support", "finish"],
             "validate": ["overlaps", "original_support"], "scaled_metric": ["ix", "add_up"],
             "select_point": ["feasible", "edge_point", "pair_cost"], "feasible": ["plane"],
             "edge_point": ["plane"], "diagnostics": ["ix", "sum_add", "value", "add_up", "up", "allowance"],
             "cholesky": ["ix"], "allowance": ["up", "add_up"], "add_up": ["up"]}
    def total(n):
        children = graph.get(n, [])
        return frames.get(n, 0) + max((total(c) for c in children), default=0)
    return dict(frames_bytes=frames, maximum_reviewed_own_call_path_bytes=total("ss_propose"),
                excludes="libm, libc, caller-owned input view, platform ISR/runtime; no target measurement",
                call_graph=graph)


def main():
    ap = argparse.ArgumentParser();ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()
    here = Path(__file__).resolve().parent;root = here.parent
    plan_path = here / "support_plan.json"
    plan = json.loads(plan_path.read_text())
    own_paths = [root / "support_step.c", root / "support_step.h", Path(__file__).resolve()]
    for path in own_paths:
        if digest(path) != plan["source_sha256"][path.name]:
            raise RuntimeError("frozen source identity mismatch: " + path.name)
    cases = fixtures()
    if [x[0] for x in cases] != plan["fixtures"]:
        raise RuntimeError("fixture inventory mismatch")
    out = Path(args.output_dir).resolve();out.mkdir(parents=False, exist_ok=False)
    started = time.perf_counter();cpu = time.process_time()
    receipt = dict(schema="mumble_support_step_qualification_v1", status="failed", plan_sha256=digest(plan_path),
                   source_sha256=plan["source_sha256"], canonical_observation_reads=0, model_calls=0,
                   prior_calls=0, archived_optimizer_calls=0, truth_reads=0, build_invocations=0, primitive_calls=0,
                   fixture_count=len(cases), cases=[], errors=[])
    try:
        cmd = ["cc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-fno-fast-math",
               "-ffp-contract=off", "-fno-inline", "-fno-optimize-sibling-calls", "-fstack-usage", "-fPIC", "-shared",
               str(root / "support_step.c"), "-lm", "-o", str(out / "support_step.so")]
        receipt["build_invocations"] = 1;receipt["build_command"] = cmd
        build = subprocess.run(cmd, cwd=out, capture_output=True, text=True, timeout=30, check=False)
        (out / "build.stdout").write_text(build.stdout);(out / "build.stderr").write_text(build.stderr)
        receipt["build_exit_code"] = build.returncode
        if build.returncode:
            raise RuntimeError("single qualification build failed")
        lib = C.CDLL(str(out / "support_step.so"))
        lib.ss_propose.argtypes = [C.POINTER(Input), C.POINTER(Workspace), C.POINTER(Result)]
        lib.ss_propose.restype = C.c_int
        for n in ("workspace", "input", "result"):
            getattr(lib, "ss_" + n + "_bytes").restype = C.c_size_t
        sizes = dict(workspace=lib.ss_workspace_bytes(), input=lib.ss_input_bytes(), result=lib.ss_result_bytes())
        receipt["sizes_bytes"] = sizes
        if sizes != dict(workspace=1600, input=48, result=120):
            raise RuntimeError("layout mismatch")
        for fixture in cases:
            receipt["primitive_calls"] += 1
            receipt["cases"].append(check_case(lib, *fixture))
        receipt["stack"] = stack_account(sorted(out.glob("*.su")))
        if not receipt["stack"]["frames_bytes"]:
            raise RuntimeError("missing stack receipt")
        if receipt["stack"]["maximum_reviewed_own_call_path_bytes"] > plan["own_stack_cap_bytes"]:
            raise RuntimeError("own stack cap exceeded")
        failures = [(case["name"], c["check"]) for case in receipt["cases"] for c in case["checks"] if not c["passed"]]
        receipt["assertions"] = sum(len(case["checks"]) for case in receipt["cases"])
        receipt["failed_assertions"] = failures
        if failures:
            raise RuntimeError("fabricated assertions failed")
        receipt["status"] = "passed"
    except Exception as exc:
        receipt["errors"].append(type(exc).__name__ + ": " + str(exc))
    finally:
        receipt["wall_s"] = time.perf_counter() - started
        receipt["python_cpu_s"] = time.process_time() - cpu
        receipt["own_max_RSS_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        receipt["child_max_RSS_bytes"] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss * 1024
        receipt["inputs_unchanged"] = all(digest(p) == plan["source_sha256"][p.name] for p in own_paths)
        if not receipt["inputs_unchanged"]:
            receipt["status"] = "failed";receipt["errors"].append("qualification source changed")
        receipt["output_files"] = [{"path": p.name, "bytes": p.stat().st_size, "sha256": digest(p)} for p in sorted(out.iterdir()) if p.is_file()]
        payload = json.dumps(clean(receipt), indent=2, sort_keys=True, allow_nan=False) + "\n"
        path = out / "receipt.json"
        with path.open("x") as f:
            f.write(payload);f.flush();os.fsync(f.fileno())
    print(json.dumps(dict(status=receipt["status"], receipt=str(path), sha256=digest(path),
                          primitive_calls=receipt["primitive_calls"], assertions=receipt.get("assertions"), errors=receipt["errors"])))
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
