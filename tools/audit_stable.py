#!/usr/bin/env python3
"""Independent exact-reference audit of the isolated integer proof kernels.

The rational exponential oracle uses a positive series for exp(q) and a
geometric tail, then inversion. It does not reuse the C alternating polynomial
or range reduction. All primary inputs and scopes are specified in plan.json.
Finite testing corroborates lemma/code correspondence; it is not an all-time
proof, a battery-certificate producer, or target qualification.
"""
from __future__ import annotations

import argparse
import ctypes as ct
import datetime as dt
from fractions import Fraction as F
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import re
import shlex
import shutil
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
PLAN = "experiments/indefinite_stability_002/plan.json"
D = 1 << 32
U32 = D - 1
I32_MIN, I32_MAX = -(1 << 31), (1 << 31) - 1
I64_MIN, I64_MAX = -(1 << 63), (1 << 63) - 1
STATE_MAX = 1 << 30
ABI_SOURCE = r"""
#include "scm_stable.h"
#include <stddef.h>
size_t audit_size_charge(void) { return sizeof(scm_stable_charge); }
size_t audit_size_mask(void) { return sizeof(scm_stable_mask); }
size_t audit_size_attenuation(void) { return sizeof(scm_stable_attenuation); }
size_t audit_size_interval(void) { return sizeof(scm_stable_interval); }
"""


class Charge(ct.Structure):
    _fields_ = [("value", ct.c_int64), ("lower", ct.c_int64), ("upper", ct.c_int64)]


class Mask(ct.Structure):
    _fields_ = [("domain", ct.c_uint64), ("active", ct.c_uint64)]


class Attenuation(ct.Structure):
    _fields_ = [("lower", ct.c_uint64), ("upper", ct.c_uint64)]


class Interval(ct.Structure):
    _fields_ = [("lower", ct.c_int32), ("upper", ct.c_int32), ("bound", ct.c_int32)]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def run(args: list[str], timeout: int = 30) -> dict:
    start = time.monotonic()
    try:
        p = subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                           check=False, timeout=timeout)
        return {"command": args, "returncode": p.returncode, "stdout": p.stdout,
                "stderr": p.stderr, "timeout": False,
                "seconds": time.monotonic() - start}
    except subprocess.TimeoutExpired as exc:
        def decode(v):
            return v.decode(errors="replace") if isinstance(v, bytes) else v or ""
        return {"command": args, "returncode": None, "stdout": decode(exc.stdout),
                "stderr": decode(exc.stderr), "timeout": True,
                "seconds": time.monotonic() - start}


def floor(x: F) -> int:
    return x.numerator // x.denominator


def ceil(x: F) -> int:
    return -((-x.numerator) // x.denominator)


def rational(x: F) -> dict:
    return {"numerator": str(x.numerator), "denominator": str(x.denominator)}


def finite_json(data) -> str:
    return json.dumps(data, indent=2, allow_nan=False) + "\n"


class Checks:
    def __init__(self):
        self.total = 0
        self.failures = []

    def check(self, name: str, condition: bool, details=None):
        self.total += 1
        if not condition:
            self.failures.append({"name": name, "details": details})

    def result(self) -> dict:
        return {"checks": self.total, "failures": self.failures,
                "passed": not self.failures}


class API:
    def __init__(self, path: Path):
        self.lib = ct.CDLL(str(path))
        signatures = {
            "scm_stable_charge_init": [ct.POINTER(Charge), ct.c_int64, ct.c_int64, ct.c_int64],
            "scm_stable_charge_push": [ct.POINTER(Charge), ct.c_int32, ct.c_uint32],
            "scm_stable_mask_init": [ct.POINTER(Mask), ct.c_uint64],
            "scm_stable_mask_apply": [ct.POINTER(Mask), ct.c_uint64],
            "scm_stable_attenuation_ratio": [ct.c_uint32, ct.c_uint32, ct.POINTER(Attenuation)],
            "scm_stable_interval_init": [ct.POINTER(Interval), ct.c_int32, ct.c_int32, ct.c_int32],
            "scm_stable_interval_step": [ct.POINTER(Interval), ct.POINTER(Attenuation), ct.c_int32],
        }
        for name, args in signatures.items():
            fn = getattr(self.lib, name)
            fn.argtypes, fn.restype = args, ct.c_int
            setattr(self, name.removeprefix("scm_stable_"), fn)
        for name in ("charge", "mask", "attenuation", "interval"):
            fn = getattr(self.lib, "audit_size_" + name)
            fn.argtypes, fn.restype = [], ct.c_size_t

    def attenuation(self, num: int, den: int):
        a = Attenuation()
        status = self.attenuation_ratio(num, den, ct.byref(a))
        return status, a


@lru_cache(maxsize=None)
def exp_minus_enclosure(q: F):
    """Exact rational enclosure of exp(-q), independent of the C algorithm.

    S_n <= exp(q) <= S_n + t_(n+1)/(1-q/(n+2)), once q<n+2.
    Ratios of subsequent positive-series tail terms only decrease.
    Inverting positive endpoints encloses exp(-q).
    """
    if q == 0:
        return F(1), F(1), 0, "exact_zero"
    if q >= 32:
        return F(0), F(1, D), 0, "e_greater_than_two_tail"
    term = total = F(1)
    target = F(1, 1 << 160)
    for n in range(513):
        following = term * q / (n + 1)
        if q < n + 2:
            tail = following / (1 - q / (n + 2))
            low, high = 1 / (total + tail), 1 / total
            if high - low <= target:
                return low, high, n, "positive_series_and_geometric_tail"
        term = following
        total += term
    raise ArithmeticError("Independent exponential oracle exceeded 512 terms")


def exp_cases(plan: dict):
    cases = [(0, 1), (0, U32), (1, U32), (1, 1050), (1, 175),
             (1, 35), (1, 8), (1, 1), (31, 1), (32, 1), (33, 1),
             (U32, 1), (U32, U32), (U32, U32 - 1), (U32, 134217728)]
    for s in range(9):
        den = 1 << 20
        num = (1 << s) * den // 8
        cases.extend((num + d, den) for d in (-1, 0, 1))
    rng = random.Random(plan["seed"])
    for i in range(plan["audit"]["attenuation"]["random_ratios"]):
        if i % 3 == 0:
            pair = rng.randrange(U32 + 1), rng.randrange(1, U32 + 1)
        elif i % 3 == 1:
            den = rng.randrange(1, U32 // 32 + 1)
            pair = rng.randrange(0, 32 * den + 1), den
        else:
            pair = rng.randrange(1, 1001), rng.randrange(1 << 24, U32 + 1)
        cases.append(pair)
    return list(dict.fromkeys(cases))


def audit_exp(api: API, plan: dict) -> dict:
    c = Checks()
    rows = []
    for i, (num, den) in enumerate(exp_cases(plan)):
        status, a = api.attenuation(num, den)
        low, high, terms, method = exp_minus_enclosure(F(num, den))
        enclosed = F(a.lower, D) <= low and high <= F(a.upper, D)
        c.check("exponential_enclosure", status == 0 and
                0 <= a.lower <= a.upper <= D and enclosed,
                {"case": i, "num": num, "den": den,
                 "lower": a.lower, "upper": a.upper})
        rows.append({"num": num, "den": den, "lower": a.lower, "upper": a.upper,
                     "width_Q32_units": a.upper - a.lower, "status": status,
                     "oracle_last_term": terms, "oracle_method": method,
                     "oracle_Q128_lower": str(floor(low * (1 << 128))),
                     "oracle_Q128_upper": str(ceil(high * (1 << 128))),
                     "oracle_interval_contained": enclosed})
    old = Attenuation(11, 22)
    before = bytes(old)
    status = api.attenuation_ratio(1, 0, ct.byref(old))
    c.check("zero_denominator_atomic", status < 0 and bytes(old) == before)
    return {**c.result(), "cases": rows,
            "maximum_width_Q32_units": max(x["width_Q32_units"] for x in rows),
            "maximum_positive_series_last_term": max(x["oracle_last_term"] for x in rows),
            "oracle": "Exact rational positive exp(q) series plus geometric tail, inverted"}


def convex(a: F, x: F, target: F) -> F:
    return a * x + (1 - a) * target


def convex_enclosure(al: F, au: F, xl: F, xu: F, target: F):
    values = [convex(a, x, target) for a in (al, au) for x in (xl, xu)]
    return min(values), max(values)


def audit_state(api: API, plan: dict) -> dict:
    c = Checks()
    rng = random.Random(plan["seed"] + 1)
    cases = [(0, 0, 0, 0, 0, D),
             (10, -1, -1, 0, D // 2, D // 2),
             (10, 1, 1, 0, D // 2, D // 2),
             (STATE_MAX, -STATE_MAX, STATE_MAX, STATE_MAX, 0, D),
             (STATE_MAX, -STATE_MAX, -STATE_MAX, STATE_MAX, D - 1, D),
             (STATE_MAX, STATE_MAX, STATE_MAX, -STATE_MAX, 0, 1),
             (20, -7, 11, 20, D, D),
             (20, -7, 11, -9, 0, 0)]
    for _ in range(plan["audit"]["state"]["random_cases"]):
        bound = rng.choice([0, 1, 3, 10, 1 << 16, STATE_MAX])
        lower, upper = sorted([rng.randint(-bound, bound), rng.randint(-bound, bound)])
        target = rng.randint(-bound, bound)
        al, au = sorted([rng.randrange(D + 1), rng.randrange(D + 1)])
        cases.append((bound, lower, upper, target, al, au))
    for i, (bound, lower, upper, target, al, au) in enumerate(cases):
        s, a = Interval(), Attenuation(al, au)
        init = api.interval_init(ct.byref(s), lower, upper, bound)
        before = bytes(s)
        status = api.interval_step(ct.byref(s), ct.byref(a), target)
        lo, hi = convex_enclosure(F(al, D), F(au, D), F(lower), F(upper), F(target))
        c.check("state_rational_hull", init == 0 and status == 0 and
                s.lower == floor(lo) and s.upper == ceil(hi) and
                -bound <= s.lower <= s.upper <= bound, {"case": i})
        for na, nx in ((1, 3), (2, 1), (3, 2)):
            av = F(al, D) + F(na, 4) * F(au - al, D)
            xv = F(lower) + F(nx, 4) * (upper - lower)
            value = convex(av, xv, F(target))
            c.check("state_interior_enclosure", s.lower <= value <= s.upper, {"case": i})
        if al == au == D:
            c.check("state_exact_identity", bytes(s) == before, {"case": i})
    s = Interval(-1, 1, 10)
    for a, target in [(Attenuation(0, D + 1), 0),
                      (Attenuation(2, 1), 0), (Attenuation(0, D), 11)]:
        before = bytes(s)
        status = api.interval_step(ct.byref(s), ct.byref(a), target)
        c.check("state_invalid_atomic", status < 0 and bytes(s) == before)
    return {**c.result(), "case_count": len(cases),
            "oracle": "Exact Fraction bilinear extrema and independent interior points"}


def audit_charge(api: API, plan: dict) -> dict:
    c = Checks()
    critical = [
        (I64_MIN, I64_MAX, 0, I32_MIN, U32),
        (I64_MIN, I64_MAX, 0, I32_MAX, U32),
        (I64_MIN, I64_MAX, I64_MIN, -1, 1),
        (I64_MIN, I64_MAX, I64_MAX, 1, 1),
        (I64_MIN, I64_MAX, I64_MIN, I32_MIN, 0),
        (-100, 100, 0, 101, 1), (-100, 100, 0, -101, 1),
        (0, 0, 0, I32_MAX, 0)]
    rows = []
    for lower, upper, value, code, ticks in critical:
        s = Charge()
        init = api.charge_init(ct.byref(s), lower, upper, value)
        before = bytes(s)
        exact = value + code * ticks
        expected = -52 if not I64_MIN <= exact <= I64_MAX else (
            -51 if not lower <= exact <= upper else 0)
        status = api.charge_push(ct.byref(s), code, ticks)
        c.check("charge_critical_exact", init == 0 and status == expected and
                (s.value == exact if status == 0 else bytes(s) == before))
        rows.append({"initial": str(value), "code": code, "ticks": ticks,
                     "exact_candidate": str(exact), "status": status,
                     "value": str(s.value)})
    rng = random.Random(plan["seed"] + 2)
    s = Charge()
    api.charge_init(ct.byref(s), -(1 << 50), 1 << 50, 0)
    exact = 0
    accepted = rejected = 0
    for i in range(plan["audit"]["charge"]["random_transitions"]):
        code = rng.randint(I32_MIN, I32_MAX)
        ticks = rng.choice([0, 1, 999, 1000, 1001, U32])
        candidate = exact + code * ticks
        expected = -52 if not I64_MIN <= candidate <= I64_MAX else (
            -51 if not s.lower <= candidate <= s.upper else 0)
        before = bytes(s)
        status = api.charge_push(ct.byref(s), code, ticks)
        if status == 0:
            exact = candidate
            accepted += 1
        else:
            rejected += 1
        c.check("charge_integer_reference", status == expected and s.value == exact and
                (status == 0 or bytes(s) == before), {"step": i})
    api.charge_init(ct.byref(s), -91, 91, 0)
    for i in range(64):
        plus = api.charge_push(ct.byref(s), 7, 13)
        after_plus = s.value
        minus = api.charge_push(ct.byref(s), -7, 13)
        c.check("charge_exact_zero_net_cycle", plus == minus == 0 and
                after_plus == 91 and s.value == 0, {"cycle": i})
    return {**c.result(), "critical": rows,
            "random_accepted": accepted, "random_rejected": rejected,
            "zero_net_cycles": 64, "oracle": "Python unbounded integer product and prefix sum"}


def cells(mask: int):
    return {i for i in range(64) if mask & (1 << i)}


def audit_mask(api: API, plan: dict) -> dict:
    c = Checks()
    for initial in range(16):
        for allowed in range(16):
            s = Mask()
            api.mask_init(ct.byref(s), 15)
            api.mask_apply(ct.byref(s), initial)
            expected = cells(initial).intersection(cells(allowed))
            status = api.mask_apply(ct.byref(s), allowed)
            c.check("mask_set_intersection", cells(s.active) == expected and
                    status == (0 if expected else 1))
    s = Mask()
    api.mask_init(ct.byref(s), 255)
    timeline = [{"stage": "initial", "active": s.active}]
    for allowed in (63, 51):
        api.mask_apply(ct.byref(s), allowed)
    timeline.append({"stage": "informative", "active": s.active})
    before = bytes(s)
    for _ in range(plan["audit"]["mask"]["quiet_repetitions"]):
        api.mask_apply(ct.byref(s), 255)
        api.mask_apply(ct.byref(s), 51)
    c.check("mask_quiet_retention", bytes(s) == before)
    timeline.append({"stage": "quiet_and_duplicate", "active": s.active})
    api.mask_apply(ct.byref(s), 5)
    timeline.append({"stage": "renewed_refinement", "active": s.active})
    c.check("mask_demo_refines", s.active == 1)
    status = api.mask_apply(ct.byref(s), 0)
    again = api.mask_apply(ct.byref(s), 255)
    c.check("mask_empty_is_sticky_inconsistency", status == again == 1 and s.active == 0)
    api.mask_init(ct.byref(s), 15)
    before = bytes(s)
    status = api.mask_apply(ct.byref(s), 16)
    c.check("mask_invalid_atomic", status < 0 and bytes(s) == before)
    # Each singleton union covers theta=3/2, but they disagree on its cell.
    # This is a deliberately invalid producer premise, not a kernel defect.
    api.mask_init(ct.byref(s), 3)
    first = api.mask_apply(ct.byref(s), 1)
    second = api.mask_apply(ct.byref(s), 2)
    weak_premise_refuted = first == 0 and second == 1 and s.active == 0
    c.check("weak_union_cover_negative_control", weak_premise_refuted)
    return {**c.result(), "exhaustive_four_cell_pairs": 256, "timeline": timeline,
            "certificate_producer_soundness_claim": False,
            "weak_premise_negative_control": {
                "cells": [["0", "2"], ["1", "3"]], "true_parameter": "3/2",
                "certificates": [1, 2], "both_singleton_unions_cover_truth": True,
                "final_active": s.active, "final_status": second,
                "weak_union_cover_premise_refuted": weak_premise_refuted,
                "kernel_failure": False,
                "required_premise": "Retain every cell intersecting the exact compatible set."}}


def audit_stream(api: API, plan: dict) -> dict:
    cfg = plan["audit"]["nominal_stream"]
    checks = Checks()
    demos = []
    grid = 1 << cfg["reference_grid_bits"]
    for tau in cfg["tau_ticks"]:
        s = Interval()
        api.interval_init(ct.byref(s), 0, 0, cfg["state_bound"])
        exact_lower = exact_upper = F(0)
        maximum_width = 0
        largest_upper = 0
        largest_span = 0
        identities = 0
        checkpoints = []
        for i in range(cfg["steps_per_tau"]):
            ticks = cfg["actual_tick_pattern"][i % len(cfg["actual_tick_pattern"])]
            target = cfg["targets"][i % len(cfg["targets"])]
            status, a = api.attenuation(ticks, tau)
            alo, ahi, _, _ = exp_minus_enclosure(F(ticks, tau))
            reflo, refhi = convex_enclosure(alo, ahi, exact_lower, exact_upper, F(target))
            exact_lower = F(floor(reflo * grid), grid)
            exact_upper = F(ceil(refhi * grid), grid)
            before = bytes(s)
            pushed = api.interval_step(ct.byref(s), ct.byref(a), target)
            checks.check("chronological_reference_enclosure",
                         status == pushed == 0 and
                         s.lower <= exact_lower <= exact_upper <= s.upper,
                         {"tau_ticks": tau, "sample": i})
            if ticks == 0:
                identities += 1
                checks.check("zero_time_identity", bytes(s) == before)
            else:
                largest_upper = max(largest_upper, a.upper)
                largest_span = max(largest_span, a.upper - a.lower)
            maximum_width = max(maximum_width, s.upper - s.lower)
            if i in (0, cfg["steps_per_tau"] - 1):
                checkpoints.append({"sample": i, "lower": s.lower, "upper": s.upper,
                                    "reference_lower_approx": float(exact_lower),
                                    "reference_upper_approx": float(exact_upper)})
        gap = D - largest_upper
        width_bound = (F(2 * cfg["state_bound"] * largest_span + 2 * D, gap)
                       if gap > 0 else None)
        checks.check("conditional_width_bound_available", width_bound is not None,
                     {"tau_ticks": tau})
        if width_bound is not None:
            checks.check("observed_width_within_conditional_bound",
                         maximum_width <= width_bound, {"tau_ticks": tau})
        demos.append({
            "tau_ticks": tau, "tau_seconds_as_ratio": [tau, cfg["tick_frequency_Hz"]],
            "steps": cfg["steps_per_tau"], "zero_time_identity_updates": identities,
            "max_observed_width_state_units": maximum_width,
            "max_coefficient_upper": largest_upper, "max_coefficient_span_h": largest_span,
            "active_contraction_gap_g": gap,
            "conditional_uniform_width_bound": rational(width_bound) if width_bound else None,
            "conditional_uniform_width_bound_approx": float(width_bound) if width_bound else None,
            "checkpoints": checkpoints})
    return {**checks.result(), "illustrative_grid": cfg, "cases": demos,
            "physical_accuracy_claim": False,
            "reference": "Independent rational exponential enclosure; state oracle outward grid 2^-128"}


def memory_report(api: API, temp: Path, commands: dict) -> dict:
    sizes = {}
    for name, cls in [("charge", Charge), ("mask", Mask),
                      ("attenuation", Attenuation), ("interval", Interval)]:
        actual = getattr(api.lib, "audit_size_" + name)()
        if actual != ct.sizeof(cls):
            raise RuntimeError(f"ctypes ABI mismatch for {name}")
        sizes[name] = actual
    stack_text = (temp / "core.su").read_text() if (temp / "core.su").exists() else ""
    frames = []
    for line in stack_text.splitlines():
        fields = line.split("\t")
        if len(fields) == 3:
            frames.append({"function": fields[0].rsplit(":", 1)[-1],
                           "bytes": int(fields[1]), "kind": fields[2]})
    symbols = commands["undefined_symbols"].get("stdout", "")
    heap_calls = re.findall(r"\b(?:malloc|calloc|realloc|free)\b", symbols)
    return {
        "host_object_bytes": sizes, "one_of_each_object_subtotal_bytes": sum(sizes.values()),
        "compiler_stack_frames": frames,
        "largest_reported_core_frame_bytes": max((x["bytes"] for x in frames), default=0),
        "conservative_sum_all_reported_frames_bytes": sum(x["bytes"] for x in frames),
        "stack_aggregation_scope": "Sum of all reported nonrecursive core frames is a loose own-source upper subtotal, not runtime high-water or target ABI qualification.",
        "undefined_symbols": symbols, "heap_imports": heap_calls,
        "object_sections": commands["object_sections"].get("stdout", ""),
        "scope": "One instance per isolated primitive. Parameter-cell storage, certificate producer, acquisition, chronology/recovery, call runtime and full estimator are excluded.",
        "complete_subsystem_memory_claim": False, "Cortex_M23_qualified": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    if output.exists():
        raise FileExistsError(f"Refusing existing receipt: {output}")
    plan = json.loads((ROOT / PLAN).read_text())
    sources = plan["sources"]
    before = {p: sha((ROOT / p).read_bytes()) for p in sources}
    head = git("rev-parse", "HEAD").decode().strip()
    committed = {}
    for p in sources:
        proc = subprocess.run(["git", "show", f"{head}:{p}"], cwd=ROOT,
                              capture_output=True, check=False)
        committed[p] = proc.returncode == 0 and sha(proc.stdout) == before[p]
    frozen_files = git("ls-tree", "-r", "--name-only", plan["base_revision"],
                       "--", "src", "include").decode().splitlines()
    frozen_matches = {p: sha((ROOT / p).read_bytes()) ==
                      sha(git("show", plan["base_revision"] + ":" + p))
                      for p in frozen_files}
    frozen_paths = ["data", "results", "experiments/bounded_event_001",
                    "experiments/bounded_event_002", "experiments/indefinite_stability_001",
                    "proofs/indefinite_stability_001"]
    evidence_changes = git("diff", "--name-only", plan["base_revision"],
                           "--", *frozen_paths).decode().splitlines()
    compiler = shlex.split(os.environ.get("CC", "cc"))
    if not compiler or shutil.which(compiler[0]) is None:
        raise RuntimeError("C compiler not found")
    compiler[0] = str(Path(shutil.which(compiler[0])).resolve())
    flags = plan["compiler_flags"]
    receipt = {
        "schema": "mumble_stability_kernel_audit_receipt_v1",
        "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_revision": head, "branch": git("branch", "--show-current").decode().strip(),
        "plan": PLAN, "source_sha256_before": before,
        "plan_and_sources_match_commit_before_run": committed,
        "old_numerical_source_matches_base": frozen_matches,
        "old_evidence_changed": evidence_changes,
        "platform": {"system": platform.system(), "machine": platform.machine(),
                     "release": platform.release(), "python": platform.python_version(),
                     "libc": list(platform.libc_ver())},
        "compiler_version": run(compiler + ["--version"]),
        "nonclaims": plan["nonclaims"], "commands": {}, "audits": {}}
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="mumble-stable-audit-") as directory:
        temp = Path(directory)
        (temp / "abi.c").write_text(ABI_SOURCE)
        library = temp / "libstable.so"
        command = compiler + flags + ["-Iinclude", "-shared", "-fPIC",
            "src/scm_stable.c", str(temp / "abi.c"), "-o", str(library)]
        receipt["commands"]["shared_compile"] = run(command)
        receipt["commands"]["core_compile"] = run(compiler + flags + ["-Iinclude",
            "-fstack-usage", "-c", "src/scm_stable.c", "-o", str(temp / "core.o")])
        receipt["commands"]["unit_compile"] = run(compiler + flags + ["-Iinclude",
            "src/scm_stable.c", "tests/test_stable.c", "-o", str(temp / "test_stable")])
        compiled = all(receipt["commands"][k]["returncode"] == 0
                       for k in ("shared_compile", "core_compile", "unit_compile"))
        if compiled:
            receipt["binary_sha256"] = {"shared": sha(library.read_bytes()),
                                       "core_object": sha((temp / "core.o").read_bytes()),
                                       "unit": sha((temp / "test_stable").read_bytes())}
            receipt["commands"]["unit_run"] = run([str(temp / "test_stable")])
            receipt["commands"]["undefined_symbols"] = run(["nm", "-u", str(temp / "core.o")])
            receipt["commands"]["object_sections"] = run(["size", "-A", str(temp / "core.o")])
            api = API(library)
            for name, audit in [("attenuation", audit_exp), ("state", audit_state),
                                ("charge", audit_charge), ("mask", audit_mask),
                                ("nominal_stream", audit_stream)]:
                audit_start = time.monotonic()
                try:
                    receipt["audits"][name] = audit(api, plan)
                except Exception as exc:
                    receipt["audits"][name] = {"passed": False, "exception": repr(exc)}
                receipt["audits"][name]["seconds"] = time.monotonic() - audit_start
            try:
                receipt["memory"] = memory_report(api, temp, receipt["commands"])
            except Exception as exc:
                receipt["memory_error"] = repr(exc)
    after = {p: sha((ROOT / p).read_bytes()) for p in sources}
    receipt["source_sha256_after"] = after
    receipt["sources_unchanged_during_run"] = before == after
    receipt["audit_seconds"] = time.monotonic() - start
    numerical_pass = compiled and len(receipt["audits"]) == 5 and all(
        v["passed"] for v in receipt["audits"].values()) and (
        receipt["commands"].get("unit_run", {}).get("returncode") == 0)
    success = (numerical_pass and all(committed.values()) and before == after
               and all(frozen_matches.values()) and not evidence_changes
               and "memory" in receipt and not receipt["memory"]["heap_imports"])
    receipt["sampled_lemma_correspondence_checks_passed"] = numerical_pass
    receipt["experiment_completed_as_planned"] = success
    receipt["full_estimator_indefinite_stability_proved"] = False
    receipt["finished_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        stream.write(finite_json(receipt))
    print(json.dumps({"receipt": str(output), "sampled_checks_passed": numerical_pass,
                      "completed_as_planned": success,
                      "full_estimator_indefinite_stability_proved": False}))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
