#!/usr/bin/env python3
"""Exact-reference finite audit of the conditional integer battery provider.

The compiled provider receives public configuration and observations only.
Synthetic truth belongs to this generator/scorer, never inference or starts.
The unchanged retained-history C estimator is a separate comparison path.
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
import re
import shlex
import shutil
import subprocess
import tempfile
import time

from audit_stable import (Attenuation, Charge, Interval, Mask, Checks, ceil, floor,
                          exp_minus_enclosure, finite_json, git, rational, run, sha)

ROOT = Path(__file__).resolve().parents[1]
PLAN = "experiments/indefinite_stability_003/plan.json"
Z, K, GRID = 65536, 126000000, 1 << 128
U32, VOLTAGE_LIMIT = (1 << 32) - 1, 8000000000


class Capacity(ct.Structure):
    _fields_ = [("lower_uAh", ct.c_uint32), ("upper_uAh", ct.c_uint32)]


class SOC(ct.Structure):
    _fields_ = [("lower", ct.c_int32), ("upper", ct.c_int32)]


class Knot(ct.Structure):
    _fields_ = [("soc", ct.c_int32), ("voltage_nV", ct.c_int64)]


class Config(ct.Structure):
    _fields_ = [("cells", ct.c_uint32), ("ocv_knots", ct.c_uint32),
                ("initial_soc_lower", ct.c_int32), ("initial_soc_upper", ct.c_int32),
                ("current_limit_uA", ct.c_int32), ("r0_mOhm", ct.c_uint32),
                ("r_mOhm", ct.c_uint32 * 3), ("tau_ticks", ct.c_uint32 * 3),
                ("initial_rc", Interval * 3), ("capacity", Capacity * 64),
                ("ocv", Knot * 17)]


class Bank(ct.Structure):
    _fields_ = [("config", ct.POINTER(Config)), ("charge", Charge),
                ("evidence", Mask), ("rc", Interval * 3), ("initial_soc", SOC * 64)]


class Workspace(ct.Structure):
    _fields_ = [("staged", Bank)]


class Sample(ct.Structure):
    _fields_ = [("current_uA", ct.c_int32), ("ticks", ct.c_uint32),
                ("voltage_lower_nV", ct.c_int64), ("voltage_upper_nV", ct.c_int64)]


class Result(ct.Structure):
    _fields_ = [("soc_lower", ct.c_int32), ("soc_upper", ct.c_int32),
                ("capacity_lower_uAh", ct.c_uint32), ("capacity_upper_uAh", ct.c_uint32),
                ("active_mask", ct.c_uint64), ("active_cells", ct.c_uint32),
                ("has_support", ct.c_int)]


ABI_SOURCE = r"""
#include "scm_certificate.h"
#include <stddef.h>
size_t audit_size_config(void) { return sizeof(scm_certificate_config); }
size_t audit_size_bank(void) { return sizeof(scm_certificate_bank); }
size_t audit_size_workspace(void) { return sizeof(scm_certificate_workspace); }
size_t audit_size_sample(void) { return sizeof(scm_certificate_sample); }
size_t audit_size_result(void) { return sizeof(scm_certificate_result); }
size_t audit_offset_config_ocv(void) { return offsetof(scm_certificate_config,ocv); }
size_t audit_offset_bank_initial_soc(void) { return offsetof(scm_certificate_bank,initial_soc); }
size_t audit_offset_result_mask(void) { return offsetof(scm_certificate_result,active_mask); }
"""


class API:
    def __init__(self, path: Path):
        self.lib = ct.CDLL(str(path))
        signatures = {
            "config_validate": [ct.POINTER(Config)],
            "init": [ct.POINTER(Bank), ct.POINTER(Config)],
            "push": [ct.POINTER(Bank), ct.POINTER(Sample), ct.POINTER(Workspace)],
            "query": [ct.POINTER(Bank), ct.POINTER(Result)],
        }
        for name, args in signatures.items():
            fn = getattr(self.lib, "scm_certificate_" + name)
            fn.argtypes, fn.restype = args, ct.c_int
            setattr(self, name, fn)
        self.attenuation = self.lib.scm_stable_attenuation_ratio
        self.attenuation.argtypes = [ct.c_uint32, ct.c_uint32, ct.POINTER(Attenuation)]
        self.attenuation.restype = ct.c_int
        self.sizes = {}
        for name, cls in (("config", Config), ("bank", Bank), ("workspace", Workspace),
                          ("sample", Sample), ("result", Result)):
            fn = getattr(self.lib, "audit_size_" + name)
            fn.argtypes, fn.restype = [], ct.c_size_t
            actual = fn()
            if actual != ct.sizeof(cls):
                raise RuntimeError("ctypes ABI size mismatch: " + name)
            self.sizes[name] = actual
        for name, expected in (("config_ocv", Config.ocv.offset),
                               ("bank_initial_soc", Bank.initial_soc.offset),
                               ("result_mask", Result.active_mask.offset)):
            fn = getattr(self.lib, "audit_offset_" + name)
            fn.argtypes, fn.restype = [], ct.c_size_t
            if fn() != expected:
                raise RuntimeError("ctypes ABI offset mismatch: " + name)

    def fresh(self, config: Config):
        bank, workspace = Bank(), Workspace()
        status = self.init(ct.byref(bank), ct.byref(config))
        if status != 0:
            raise RuntimeError(f"Initialization failed: {status}")
        return bank, workspace

    def read(self, bank: Bank):
        result = Result()
        status = self.query(ct.byref(bank), ct.byref(result))
        return status, result


def clone(value):
    return type(value).from_buffer_copy(bytes(value))


def public_config(plan: dict) -> Config:
    p = plan["public_configuration"]
    c = Config()
    c.cells = p["capacity_cells"]
    c.ocv_knots = len(p["OCV_nodes_SOCgrid_nV"])
    c.initial_soc_lower, c.initial_soc_upper = p["initial_SOC_grid_bounds"]
    c.current_limit_uA, c.r0_mOhm = p["current_limit_microA"], p["R0_milliohm"]
    for j in range(3):
        c.r_mOhm[j], c.tau_ticks[j] = p["Ri_milliohm"][j], p["tau_ticks"][j]
        c.initial_rc[j] = Interval(p["initial_RC_nV"][j], p["initial_RC_nV"][j], p["RC_bound_nV"])
    lo, hi = p["capacity_domain_microAh"]
    for j in range(c.cells):
        c.capacity[j] = Capacity(lo + (hi-lo)*j//c.cells, lo + (hi-lo)*(j+1)//c.cells)
    for j, (z, v) in enumerate(p["OCV_nodes_SOCgrid_nV"]):
        c.ocv[j] = Knot(z, v)
    return c


def ocv_exact(config: Config, soc: F) -> F:
    x = soc * Z
    if x < 0 or x > Z:
        raise ValueError("Independent truth left the declared SOC domain")
    for j in range(1, config.ocv_knots):
        left, right = config.ocv[j-1], config.ocv[j]
        if x <= right.soc:
            return F(left.voltage_nV) + (x-left.soc)*F(right.voltage_nV-left.voltage_nV,
                                                        right.soc-left.soc)
    raise AssertionError("OCV interval not found")


@lru_cache(maxsize=None)
def oracle_coefficient(ticks: int, tau: int):
    lo, hi, _, _ = exp_minus_enclosure(F(ticks, tau))
    return floor(lo*GRID), ceil(hi*GRID)


class TruthOracle:
    """Generator/scorer state; never passed to the compiled provider."""
    def __init__(self, config: Config, z0: F, capacity: F, initial_rc=None):
        self.config, self.z0, self.capacity = config, z0, capacity
        self.charge, self.elapsed_ticks = 0, 0
        initial = initial_rc if initial_rc is not None else [
            F(r.lower+r.upper, 2) for r in config.initial_rc]
        self.rc = [(floor(F(v)*GRID), ceil(F(v)*GRID)) for v in initial]

    def advance(self, current: int, ticks: int):
        self.charge += current*ticks
        self.elapsed_ticks += ticks
        soc = self.z0-F(self.charge, K*self.capacity)
        for j in range(3):
            al, au = oracle_coefficient(ticks, self.config.tau_ticks[j])
            xl, xu = self.rc[j]
            target = current*self.config.r_mOhm[j]*GRID
            corners = [a*x+(GRID-a)*target for a in (al, au) for x in (xl, xu)]
            self.rc[j] = (min(corners)//GRID, -((-max(corners))//GRID))
        voltage = ocv_exact(self.config, soc)-current*self.config.r0_mOhm
        lo = voltage-sum(F(r[1], GRID) for r in self.rc)
        hi = voltage-sum(F(r[0], GRID) for r in self.rc)
        return soc, lo, hi


def exact_query(config: Config, bank: Bank):
    bounds = []
    qlo, qhi = None, None
    for j in range(config.cells):
        if not bank.evidence.active & (1 << j):
            continue
        cell, z = config.capacity[j], bank.initial_soc[j]
        values = [F(s)-F(bank.charge.value*Z, K*q)
                  for s in (z.lower, z.upper) for q in (cell.lower_uAh, cell.upper_uAh)]
        lo, hi = max(0, floor(min(values))), min(Z, ceil(max(values)))
        if lo > hi:
            raise AssertionError("An active cell has empty independent current-SOC hull")
        bounds.append((lo, hi))
        qlo = cell.lower_uAh if qlo is None else min(qlo, cell.lower_uAh)
        qhi = cell.upper_uAh if qhi is None else max(qhi, cell.upper_uAh)
    if not bounds:
        return None
    return min(x[0] for x in bounds), max(x[1] for x in bounds), qlo, qhi


def evidence_measure(config: Config, bank: Bank) -> int:
    return sum(bank.initial_soc[j].upper-bank.initial_soc[j].lower
               for j in range(config.cells) if bank.evidence.active & (1 << j))


def describe(config: Config, bank: Bank, result: Result):
    active = [j for j in range(config.cells) if result.active_mask & (1 << j)]
    return {
        "charge_code_ticks": str(bank.charge.value),
        "active_mask": f"0x{result.active_mask:016x}", "active_cells": result.active_cells,
        "has_support": bool(result.has_support),
        "current_SOC_grid": [result.soc_lower, result.soc_upper] if result.has_support else None,
        "current_SOC": [result.soc_lower/Z, result.soc_upper/Z] if result.has_support else None,
        "current_SOC_width_grid": result.soc_upper-result.soc_lower if result.has_support else None,
        "capacity_microAh": [result.capacity_lower_uAh, result.capacity_upper_uAh] if result.has_support else None,
        "capacity_width_microAh": result.capacity_upper_uAh-result.capacity_lower_uAh if result.has_support else None,
        "sum_active_SOC0_widths_grid": evidence_measure(config, bank),
        "retained_SOC0_by_active_bin": [[j, bank.initial_soc[j].lower, bank.initial_soc[j].upper] for j in active],
        "interpretation": "Outer support ranges; no point-estimate accuracy or confidence-coverage claim."}


def exercise_trace(api: API, config: Config, z0: F, capacity: F, sequence,
                   checkpoints=None, initial_rc=None, noise=True):
    checks = Checks()
    bank, workspace = api.fresh(config)
    oracle = TruthOracle(config, z0, capacity, initial_rc)
    truth_bins = [j for j in range(config.cells)
                  if config.capacity[j].lower_uAh <= capacity <= config.capacity[j].upper_uAh]
    checks.check("truth_inside_declared_cover", bool(truth_bins) and
                 config.initial_soc_lower <= z0*Z <= config.initial_soc_upper)
    prior_status, prior_result = api.read(bank)
    checks.check("initial_query_valid", prior_status == 0)
    records, observations = [], []
    max_rc_width = [0, 0, 0]
    minimum_margin = None
    for k, (current, ticks) in enumerate(sequence):
        old_mask = bank.evidence.active
        old_soc = [(x.lower, x.upper) for x in bank.initial_soc]
        old_query = clone(prior_result)
        soc, vlo, vhi = oracle.advance(current, ticks)
        center = floor((vlo+vhi)/2+F(1, 2))
        perturb = (((k*48271+17) % 1801)-900)*1000 if noise else 0
        center += perturb
        obs = Sample(current, ticks, center-1000000, center+1000000)
        margin = min(vlo-obs.voltage_lower_nV, obs.voltage_upper_nV-vhi)
        minimum_margin = margin if minimum_margin is None else min(minimum_margin, margin)
        checks.check("generated_voltage_interval_contains_exact_model", margin >= 0, {"sample": k})
        pushed = api.push(ct.byref(bank), ct.byref(obs), ct.byref(workspace))
        before_query = bytes(bank)
        queried, result = api.read(bank)
        checks.check("valid_supported_transition", pushed == queried == 0 and result.has_support == 1,
                     {"sample": k, "push": pushed, "query": queried})
        checks.check("query_is_read_only", bytes(bank) == before_query, {"sample": k})
        checks.check("exact_charge", bank.charge.value == oracle.charge, {"sample": k})
        checks.check("independent_RC_containment", all(
            bank.rc[j].lower*GRID <= oracle.rc[j][0] <= oracle.rc[j][1] <= bank.rc[j].upper*GRID
            for j in range(3)), {"sample": k})
        for j in range(3):
            max_rc_width[j] = max(max_rc_width[j], bank.rc[j].upper-bank.rc[j].lower)
        checks.check("mask_monotone", bank.evidence.active & ~old_mask == 0, {"sample": k})
        monotone = True
        for j in range(config.cells):
            new = bank.initial_soc[j]
            if bank.evidence.active & (1 << j):
                monotone &= old_soc[j][0] <= new.lower <= new.upper <= old_soc[j][1]
            else:
                monotone &= (new.lower, new.upper) == old_soc[j]
        checks.check("retained_intervals_monotone_inactive_frozen", monotone, {"sample": k})
        checks.check("every_truth_intersecting_bin_survives", all(
            bank.evidence.active & (1 << j) for j in truth_bins), {"sample": k, "bins": truth_bins})
        checks.check("retained_SOC0_contains_truth", all(
            bank.initial_soc[j].lower <= z0*Z <= bank.initial_soc[j].upper for j in truth_bins),
            {"sample": k})
        checks.check("current_SOC_query_contains_truth", result.has_support and
                     result.soc_lower <= soc*Z <= result.soc_upper, {"sample": k})
        checks.check("capacity_query_contains_truth", result.has_support and
                     result.capacity_lower_uAh <= capacity <= result.capacity_upper_uAh, {"sample": k})
        expected = exact_query(config, bank)
        checks.check("query_matches_independent_rational_hull", expected ==
                     (result.soc_lower, result.soc_upper, result.capacity_lower_uAh, result.capacity_upper_uAh)
                     and result.active_cells == bank.evidence.active.bit_count(), {"sample": k})
        if current == 0:
            checks.check("zero_current_query_nonwidening", result.soc_lower >= old_query.soc_lower and
                         result.soc_upper <= old_query.soc_upper and
                         result.capacity_lower_uAh >= old_query.capacity_lower_uAh and
                         result.capacity_upper_uAh <= old_query.capacity_upper_uAh, {"sample": k})
        if ticks == 0:
            checks.check("zero_time_charge_identity", bank.charge.value == oracle.charge, {"sample": k})
        observations.append((ticks, current, center, obs.voltage_lower_nV, obs.voltage_upper_nV))
        if checkpoints and k+1 in checkpoints:
            record = describe(config, bank, result)
            record.update({"samples": k+1, "stage": checkpoints[k+1],
                           "elapsed_s": oracle.elapsed_ticks/35000,
                           "scorer_only_true_current_SOC": float(soc),
                           "scorer_only_true_capacity_microAh": float(capacity)})
            records.append(record)
        prior_result = result
    digest_input = "".join(f"{t} {i} {v} {lo} {hi}\n" for t, i, v, lo, hi in observations)
    return {**checks.result(), "samples": len(observations), "checkpoints": records,
            "truth_bins": truth_bins, "max_observed_RC_width_nV": max_rc_width,
            "minimum_measurement_containment_margin_nV": rational(minimum_margin) if minimum_margin is not None else None,
            "observations_sha256": sha(digest_input.encode())}, observations, bank


def main_sequence(plan):
    sequence, checkpoints = [], {}
    pattern = plan["public_configuration"]["actual_tick_pattern"]
    for phase in plan["main_stimulus"]:
        for _ in range(phase["samples"]):
            sequence.append((phase["current_microA"], pattern[len(sequence) % len(pattern)]))
        checkpoints[len(sequence)] = phase["name"]
    return sequence, checkpoints


def audit_usefulness(main: dict):
    c = Checks()
    rows = main["checkpoints"]
    c.check("four_phase_checkpoints", len(rows) == 4)
    if len(rows) == 4:
        c.check("zero_charge_capacity_unresolved", rows[0]["capacity_microAh"] == [30000, 100000]
                and rows[0]["active_cells"] == 64)
        for previous, new in ((rows[0], rows[1]), (rows[2], rows[3])):
            c.check("informative_capacity_strictly_narrows",
                    new["capacity_width_microAh"] < previous["capacity_width_microAh"],
                    {"stage": new["stage"], "before": previous["capacity_width_microAh"],
                     "after": new["capacity_width_microAh"]})
            c.check("informative_retained_evidence_strictly_narrows",
                    new["sum_active_SOC0_widths_grid"] < previous["sum_active_SOC0_widths_grid"],
                    {"stage": new["stage"], "before": previous["sum_active_SOC0_widths_grid"],
                     "after": new["sum_active_SOC0_widths_grid"]})
        c.check("quiet_phase_target_nonwidening",
                rows[2]["capacity_width_microAh"] <= rows[1]["capacity_width_microAh"] and
                rows[2]["current_SOC_width_grid"] <= rows[1]["current_SOC_width_grid"])
    return {**c.result(), "precision_threshold_selected": False,
            "scope": "Predeclared strict narrowing and retention gates; actual finite-grid widths remain explicit."}


def audit_inherited_width(api: API, config: Config, plan: dict, main: dict):
    checks = Checks(); modes = []; d = 1 << 32
    ticks = plan["public_configuration"]["actual_tick_pattern"]
    for j in range(3):
        rows = []
        for t in ticks:
            coefficient = Attenuation()
            status = api.attenuation(t, config.tau_ticks[j], ct.byref(coefficient))
            checks.check("enumerated_coefficient_valid", status == 0 and
                         0 <= coefficient.lower <= coefficient.upper <= d)
            rows.append({"ticks": t, "lower": coefficient.lower, "upper": coefficient.upper})
        active = [r for r in rows if r["ticks"] > 0]
        h = max(r["upper"]-r["lower"] for r in active)
        g = min(d-r["upper"] for r in active)
        checks.check("strict_active_contraction_gap", g > 0, {"mode": j})
        w0 = config.initial_rc[j].upper-config.initial_rc[j].lower
        bound = min(F(2*config.initial_rc[j].bound), max(F(w0),
                    F(2*config.initial_rc[j].bound*h+2*d, g))) if g > 0 else None
        observed = main["max_observed_RC_width_nV"][j]
        checks.check("observed_width_within_inherited_bound", bound is not None and observed <= bound,
                     {"mode": j, "observed": observed})
        modes.append({"mode": j, "tau_ticks": config.tau_ticks[j],
                      "tau_seconds": config.tau_ticks[j]/35000, "state_bound_nV": config.initial_rc[j].bound,
                      "coefficient_enumeration": rows, "h": h, "g": g,
                      "all_time_width_bound_nV": rational(bound) if bound is not None else None,
                      "all_time_width_bound_nV_approx": float(bound) if bound is not None else None,
                      "max_observed_width_nV": observed})
    return {**checks.result(), "modes": modes,
            "premise": "Every future active interval uses a positive tick count from the declared pattern and the same fixed RC model/domain; arbitrary exact zero-time identities may intervene. Current remains within the configuration limit.",
            "proof_source": "proofs/indefinite_stability_002/lemmas.json:L4",
            "method": "Finite enumeration certifies g and h over the admitted ratio alphabet; L4 gives all-prefix width. This is not extrapolation from the finite trace.",
            "unit": "One RC state grid unit is exactly1nV under the represented model; sensor/model error and physical validation remain separate."}


def simple_config(base: Config, nodes, prior=(0, Z), cells=None):
    c = clone(base)
    c.initial_soc_lower, c.initial_soc_upper = prior
    c.r0_mOhm = 0
    for j in range(3):
        c.r_mOhm[j] = 0
        c.initial_rc[j] = Interval(0, 0, 0)
    c.ocv_knots = len(nodes)
    for j, (z, v) in enumerate(nodes):
        c.ocv[j] = Knot(z, v)
    if cells is not None:
        c.cells = len(cells)
        for j, (lo, hi) in enumerate(cells):
            c.capacity[j] = Capacity(lo, hi)
    return c


def audit_canaries(api: API, base: Config, main_bank: Bank, plan):
    c = Checks()
    details = {}
    # Boundary truth must retain both adjacent closed cells, not one selected bit.
    seq, _ = main_sequence(plan)
    boundary, _, _ = exercise_trace(api, base, F(53, 100), F(65000), seq[:600])
    c.check("shared_capacity_boundary", boundary["passed"] and boundary["truth_bins"] == [31, 32], boundary)
    details["boundary"] = boundary
    signs, _, sign_bank = exercise_trace(api, base, F(1, 2), F(65000),
                                         [(50000, 1000), (-50000, 1001), (50000, 1), (0, 0)], noise=False)
    c.check("positive_negative_return_zero_charge", signs["passed"] and sign_bank.charge.value == 0, signs)
    details["signed_charge"] = signs
    # The truth initial RC state is an endpoint/midpoint of the declared box.
    uncertain = clone(base)
    for j in range(3):
        uncertain.initial_rc[j].lower, uncertain.initial_rc[j].upper = -10000, 10000
    rc_box, _, _ = exercise_trace(api, uncertain, F(1, 2), F(64700),
                                  [(20000 if j % 2 else -20000, 999+j % 3) for j in range(12)],
                                  initial_rc=[-10000, 10000, 0])
    c.check("uncertain_initial_RC_box", rc_box["passed"], rc_box)
    details["initial_RC_box"] = rc_box
    # Inclusive knots and a complete interior plateau have exact known preimages.
    plateau = simple_config(base, [(0, 3000000000), (16384, 3400000000),
                                   (49152, 3400000000), (Z, 4000000000)])
    plateau_rows = []
    for voltage, expected in ((3000000000, (0, 0)), (3400000000, (16384, 49152)),
                              (4000000000, (Z, Z))):
        b, w = api.fresh(plateau)
        o = Sample(0, 0, voltage, voltage)
        push = api.push(ct.byref(b), ct.byref(o), ct.byref(w)); query, result = api.read(b)
        c.check("inclusive_OCV_knot_or_plateau", push == query == 0 and
                (result.soc_lower, result.soc_upper) == expected and result.active_cells == 64)
        plateau_rows.append({"voltage_nV": voltage, "expected_SOC_grid": list(expected),
                             "actual_SOC_grid": [result.soc_lower, result.soc_upper]})
    details["plateau_and_knots"] = plateau_rows
    # Full-range constant OCV is intentionally uninformative about SOC and Q.
    flat = simple_config(base, [(0, 3500000000), (Z, 3500000000)])
    b, w = api.fresh(flat); before = bytes(b)
    o = Sample(0, 0, 3500000000, 3500000000)
    pushed = api.push(ct.byref(b), ct.byref(o), ct.byref(w)); _, r = api.read(b)
    c.check("flat_OCV_reports_unresolved", pushed == 0 and r.soc_lower == 0 and r.soc_upper == Z
            and r.capacity_lower_uAh == 30000 and r.capacity_upper_uAh == 100000)
    # A point charge can leave some SOC0 values outside the physical domain
    # without justifying exclusion of the whole capacity cell.
    small_soc = simple_config(base, [(0, 3000000000), (Z, 4000000000)], prior=(0, 655))
    b, w = api.fresh(small_soc)
    o = Sample(10000, 35000, -VOLTAGE_LIMIT, VOLTAGE_LIMIT)
    pushed = api.push(ct.byref(b), ct.byref(o), ct.byref(w)); queried, r = api.read(b)
    c.check("partial_SOC_domain_is_clipped_not_whole_cell_rejected", pushed == queried == 0 and
            r.active_cells == 64 and r.soc_lower == 0 and exact_query(small_soc, b) ==
            (r.soc_lower, r.soc_upper, r.capacity_lower_uAh, r.capacity_upper_uAh))
    o = Sample(200000, 2100000, -VOLTAGE_LIMIT, VOLTAGE_LIMIT)
    pushed = api.push(ct.byref(b), ct.byref(o), ct.byref(w)); queried, r = api.read(b)
    c.check("entire_SOC_domain_exit_is_inconsistent", pushed == queried == 1 and not r.has_support)
    # Extreme legal capacity endpoint exercises the full positive uint32 denominator.
    extreme = simple_config(base, [(0, 3000000000), (Z, 4000000000)],
                            cells=[(U32, U32)])
    ex, _, _ = exercise_trace(api, extreme, F(1, 2), F(U32),
                             [(1, U32), (-1, U32), (0, 0)], noise=False)
    c.check("maximum_capacity_and_tick_encoding", ex["passed"], ex)
    details["extreme_encoding"] = ex
    # Whole-transaction failure must preserve charge, RC state, masks and strips.
    b, w = api.fresh(base)
    invalid = [Sample(base.current_limit_uA+1, 1000, 3000000000, 4000000000),
               Sample(0, 1000, 5, 4), Sample(0, 1000, -VOLTAGE_LIMIT-1, 0),
               Sample(0, 1000, 0, VOLTAGE_LIMIT+1),
               Sample(base.current_limit_uA, U32, 3000000000, 4000000000)]
    statuses = []
    for o in invalid:
        before = bytes(b)
        status = api.push(ct.byref(b), ct.byref(o), ct.byref(w))
        c.check("invalid_full_transaction_atomic", status < 0 and bytes(b) == before)
        statuses.append(status)
    details["invalid_transition_statuses"] = statuses
    # Config errors and an invalid query cannot overwrite their destination.
    bad = clone(base); bad.tau_ticks[1] = 0
    before = bytes(b)
    c.check("invalid_config_init_atomic", api.init(ct.byref(b), ct.byref(bad)) < 0 and bytes(b) == before)
    bad_bank = clone(b); bad_bank.evidence.domain = 0
    output = Result(); ct.memset(ct.byref(output), 0x5A, ct.sizeof(output)); before = bytes(output)
    c.check("invalid_query_output_atomic", api.query(ct.byref(bad_bank), ct.byref(output)) < 0 and bytes(output) == before)
    alias = Workspace(); api.init(ct.byref(alias.staged), ct.byref(base)); before = bytes(alias.staged)
    o = Sample(0, 0, -VOLTAGE_LIMIT, VOLTAGE_LIMIT)
    c.check("explicit_workspace_alias_rejected", api.push(ct.byref(alias.staged), ct.byref(o), ct.byref(alias)) < 0 and bytes(alias.staged) == before)
    # Valid contradiction commits physical propagation and remains inconsistent.
    b, w = api.fresh(base); o = Sample(10000, 1000, -VOLTAGE_LIMIT, -VOLTAGE_LIMIT)
    status = api.push(ct.byref(b), ct.byref(o), ct.byref(w)); qstatus, result = api.read(b)
    c.check("contradiction_commits_and_reports_no_support", status == qstatus == 1 and
            b.charge.value == 10000000 and not result.has_support and b.evidence.active == 0)
    before_rc = [(r.lower, r.upper) for r in b.rc]
    o = Sample(0, 1000, -VOLTAGE_LIMIT, VOLTAGE_LIMIT)
    status = api.push(ct.byref(b), ct.byref(o), ct.byref(w)); qstatus, result = api.read(b)
    c.check("inconsistency_is_sticky_with_carried_dynamics", status == qstatus == 1 and
            b.evidence.active == 0 and b.charge.value == 10000000 and
            [(r.lower, r.upper) for r in b.rc] != before_rc)
    # Preserve already-learned evidence under deliberately uninformative rest.
    b, w = clone(main_bank), Workspace()
    old_mask = b.evidence.active; old_soc = bytes(b.initial_soc); old_charge = b.charge.value
    old_rc = bytes(b.rc); _, old_result = api.read(b)
    for _ in range(32):
        o = Sample(0, 1000, -VOLTAGE_LIMIT, VOLTAGE_LIMIT)
        status = api.push(ct.byref(b), ct.byref(o), ct.byref(w)); qs, new_result = api.read(b)
        c.check("uninformative_quiet_preserves_persistent_evidence", status == qs == 0 and
                b.evidence.active == old_mask and bytes(b.initial_soc) == old_soc and
                b.charge.value == old_charge and bytes(new_result) == bytes(old_result))
    c.check("uninformative_rest_still_relaxes_RC", bytes(b.rc) != old_rc)
    details["uninformative_rest_updates"] = 32
    return {**c.result(), "cases": details,
            "constructed_state_scope": "Invalid-query and alias guards use explicit API boundary objects; no physical-history reachability assertion."}


def reference_inputs(config: Config, observations, temporary: Path):
    model_lines = [f"35000 {Z} 3 {config.ocv_knots}",
                   " ".join(str(x) for x in [config.r0_mOhm, *config.r_mOhm]),
                   " ".join(str(x) for x in config.tau_ticks),
                   " ".join(str(x.lower) for x in config.initial_rc)]
    model_lines += [f"{config.ocv[j].soc} {config.ocv[j].voltage_nV}" for j in range(config.ocv_knots)]
    model_text = "\n".join(model_lines)+"\n"
    data_text = str(len(observations))+"\n"+"".join(f"{t} {i} {v}\n" for t, i, v, _, _ in observations)
    model, data = temporary/"public_model.txt", temporary/"observations.txt"
    model.write_text(model_text); data.write_text(data_text)
    return model, data, {"public_model_sha256": sha(model_text.encode()),
                         "reference_observations_sha256": sha(data_text.encode()),
                         "truth_columns_or_parameters_present": False}


def compare_reference(plan: dict, config: Config, observations, main: dict, temp: Path):
    model, data, hashes = reference_inputs(config, observations, temp)
    command = [str(temp/"provider_reference_probe"), str(model), str(data)] + [
        str(x) for x in plan["retained_history_comparison"]["prefix_samples"]]
    execution = run(command, timeout=60)
    result = {"command": execution, "input_hashes": hashes, "completed": False}
    if execution["returncode"] == 0:
        output = json.loads(execution["stdout"])
        result["output"] = output
        by_n = {r["samples"]: r for r in main["checkpoints"]}
        comparisons = []
        truth = plan["generator_and_scorer_only"]
        for fit in output.get("fits", []):
            cp = by_n[fit["samples"]]
            if fit["return_code"] != 0:
                continue
            q = fit["capacity_Ah"]*1e6
            comparisons.append({"samples": fit["samples"], "stage": cp["stage"],
                "numerically_converged": fit["status"] == 0,
                "current_SOC_point": fit["current_SOC"], "capacity_point_microAh": q,
                "scorer_only_current_SOC_error_pp": 100*(fit["current_SOC"]-cp["scorer_only_true_current_SOC"]),
                "scorer_only_capacity_error_percent": 100*(q/truth["capacity_microAh"]-1),
                "reference_point_in_certificate_SOC_hull": cp["current_SOC"][0] <= fit["current_SOC"] <= cp["current_SOC"][1],
                "reference_point_in_certificate_capacity_hull": cp["capacity_microAh"][0] <= q <= cp["capacity_microAh"][1]})
        result["comparisons"] = comparisons
        result["completed"] = output.get("completed", False) and len(comparisons) == 4
    result["interpretation"] = "Same observations/known model, separately interpreted Gaussian objective and hard outer intervals. Local solver convergence, truth error, precision and coverage are distinct."
    return result


def memory_report(api: API, temp: Path, commands):
    frames = []
    for component in ("certificate", "stable"):
        for line in (temp/(component+".su")).read_text().splitlines():
            fields = line.split("\t")
            if len(fields) == 3:
                frames.append({"component": component, "function": fields[0].rsplit(":", 1)[-1],
                               "bytes": int(fields[1]), "kind": fields[2]})
    undefined = {name: commands[name+"_undefined"]["stdout"] for name in ("certificate", "stable")}
    imports = "\n".join(undefined.values())
    heap = re.findall(r"\b(?:malloc|calloc|realloc|free)\b", imports)
    math = re.findall(r"\b(?:exp|expm1|log|sqrt|pow|tanh|sin|cos)\b", imports)
    stack_sum = sum(f["bytes"] for f in frames)
    return {"host_object_bytes": api.sizes, "simultaneous_config_bank_workspace_sample_result_bytes": sum(api.sizes.values()),
            "compiler_stack_frames": frames, "largest_reported_core_frame_bytes": max(f["bytes"] for f in frames),
            "conservative_sum_all_reported_core_frames_bytes": stack_sum,
            "objects_plus_loose_own_stack_subtotal_bytes": sum(api.sizes.values())+stack_sum,
            "stack_scope": "Loose sum of all nonrecursive own-source frames, including initialization and all branches; not measured stack high-water. External runtime/interrupt/caller stack is not qualified.",
            "undefined_symbols": undefined, "heap_imports": heap, "libm_imports": math,
            "object_sections": {name: commands[name+"_sections"]["stdout"] for name in ("certificate", "stable")},
            "complete_backing_configuration_included": True,
            "scope": "The implemented provider's complete public configuration, live state, staged transaction workspace, input, output and conservative own-source stack subtotal. Acquisition, persistence, delivery protocol and target compiler/runtime remain separate.",
            "Cortex_M23_qualified": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--development", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve() if args.output.is_absolute() else (ROOT/args.output).resolve()
    if output.exists():
        raise FileExistsError(f"Refusing existing receipt: {output}")
    if args.development and (output == ROOT or ROOT in output.parents):
        raise ValueError("Development receipts must be outside the repository")
    plan = json.loads((ROOT/PLAN).read_text())
    before = {p: sha((ROOT/p).read_bytes()) for p in plan["sources"]}
    head = git("rev-parse", "HEAD").decode().strip()
    committed = {}
    for p in before:
        snapshot = subprocess.run(["git", "show", head+":"+p], cwd=ROOT, capture_output=True, check=False)
        committed[p] = snapshot.returncode == 0 and sha(snapshot.stdout) == before[p]
    if not args.development and not all(committed.values()):
        raise RuntimeError("Primary source/plan must match a committed source revision before execution")
    frozen_source = git("ls-tree", "-r", "--name-only", plan["base_revision"], "--", "src", "include").decode().splitlines()
    frozen_matches = {p: sha((ROOT/p).read_bytes()) == sha(git("show", plan["base_revision"]+":"+p)) for p in frozen_source}
    frozen_paths = ["data", "results", "experiments/bounded_event_001", "experiments/bounded_event_002",
                    "experiments/indefinite_stability_001", "experiments/indefinite_stability_002",
                    "proofs/indefinite_stability_001", "proofs/indefinite_stability_002"]
    changed = git("diff", "--name-only", plan["base_revision"], "--", *frozen_paths).decode().splitlines()
    compiler = shlex.split(os.environ.get("CC", "cc"))
    if not compiler or not shutil.which(compiler[0]):
        raise RuntimeError("C compiler not found")
    compiler[0] = str(Path(shutil.which(compiler[0])).resolve())
    flags = plan["compiler_flags"]
    receipt = {"schema": "mumble_battery_certificate_audit_receipt_v1",
        "mode": "development" if args.development else "primary",
        "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_revision": head, "branch": git("branch", "--show-current").decode().strip(),
        "plan": PLAN, "source_sha256_before": before,
        "sources_match_commit_before_run": committed,
        "old_numerical_source_matches_base": frozen_matches, "old_evidence_changed": changed,
        "platform": {"system": platform.system(), "machine": platform.machine(),
                     "release": platform.release(), "python": platform.python_version(), "libc": list(platform.libc_ver())},
        "compiler_version": run(compiler+["--version"]), "commands": {}, "audits": {},
        "nonclaims": plan["nonclaims"], "development_checks_preceded_primary_freeze": True}
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="mumble-certificate-audit-") as directory:
        temp = Path(directory); (temp/"abi.c").write_text(ABI_SOURCE)
        core = ["src/scm_stable.c", "src/scm_certificate.c"]
        cmd = receipt["commands"]
        cmd["provider_shared_compile"] = run(compiler+flags+["-Iinclude", "-shared", "-fPIC", *core, str(temp/"abi.c"), "-o", str(temp/"provider.so")])
        cmd["provider_unit_compile"] = run(compiler+flags+["-Iinclude", *core, "tests/test_certificate.c", "-o", str(temp/"test_certificate")])
        cmd["reference_compile"] = run(compiler+flags+["-Iinclude", "src/scm_model.c", "src/scm_features.c", "src/scm_estimator.c", "tools/provider_reference_probe.c", "-lm", "-o", str(temp/"provider_reference_probe")])
        for name in ("certificate", "stable"):
            cmd[name+"_core_compile"] = run(compiler+flags+["-Iinclude", "-fstack-usage", "-c", "src/scm_"+name+".c", "-o", str(temp/(name+".o"))])
        compiled = all(v["returncode"] == 0 for v in cmd.values())
        if compiled:
            receipt["binary_sha256"] = {name: sha((temp/name).read_bytes()) for name in
                ("provider.so", "test_certificate", "provider_reference_probe", "certificate.o", "stable.o")}
            cmd["provider_unit_run"] = run([str(temp/"test_certificate")])
            for name in ("certificate", "stable"):
                cmd[name+"_undefined"] = run(["nm", "-u", str(temp/(name+".o"))])
                cmd[name+"_sections"] = run(["size", "-A", str(temp/(name+".o"))])
            try:
                api = API(temp/"provider.so"); config = public_config(plan)
                sequence, checkpoints = main_sequence(plan)
                truth = plan["generator_and_scorer_only"]
                primary, observations, bank = exercise_trace(api, config, F(*truth["initial_SOC"]),
                    F(truth["capacity_microAh"]), sequence, checkpoints)
                receipt["audits"]["chronological_main"] = primary
                receipt["audits"]["conditional_usefulness"] = audit_usefulness(primary)
                receipt["audits"]["inherited_RC_width"] = audit_inherited_width(api, config, plan, primary)
                receipt["audits"]["boundary_canaries"] = audit_canaries(api, config, bank, plan)
                receipt["retained_history_reference"] = compare_reference(plan, config, observations, primary, temp)
                receipt["memory"] = memory_report(api, temp, cmd)
            except Exception as exc:
                receipt["audit_exception"] = repr(exc)
    after = {p: sha((ROOT/p).read_bytes()) for p in plan["sources"]}
    receipt["source_sha256_after"] = after
    receipt["sources_unchanged_during_run"] = before == after
    receipt["audit_seconds"] = time.monotonic()-start
    soundness = compiled and receipt["commands"].get("provider_unit_run", {}).get("returncode") == 0 and all(
        receipt["audits"].get(name, {}).get("passed", False) for name in ("chronological_main", "boundary_canaries", "inherited_RC_width"))
    useful = receipt["audits"].get("conditional_usefulness", {}).get("passed", False)
    reference_ok = receipt.get("retained_history_reference", {}).get("completed", False)
    memory_ok = "memory" in receipt and not receipt["memory"]["heap_imports"] and not receipt["memory"]["libm_imports"]
    top_checks = sum(a["checks"] for a in receipt["audits"].values())
    nested_checks = sum(case.get("checks", 0) for case in
        receipt["audits"].get("boundary_canaries", {}).get("cases", {}).values()
        if isinstance(case, dict))
    receipt["assertion_counts"] = {
        "top_level": top_checks, "nested_trace_checks": nested_checks,
        "total_including_nested_and_their_summary_gates": top_checks+nested_checks,
        "scope": "The top-level boundary checks include summary gates over nested traces. Counts are finite correspondence evidence, not a lifetime quantifier."}
    success = soundness and useful and reference_ok and memory_ok and before == after and all(frozen_matches.values()) and not changed and (args.development or all(committed.values()))
    receipt.update({"sampled_provider_soundness_checks_passed": soundness,
                    "conditional_usefulness_gates_passed": useful,
                    "reference_comparison_completed": reference_ok,
                    "experiment_completed_as_planned": success,
                    "full_battery_estimator_indefinite_stability_proved": False,
                    "finished_utc": dt.datetime.now(dt.timezone.utc).isoformat()})
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        stream.write(finite_json(receipt))
    print(json.dumps({"receipt": str(output), "mode": receipt["mode"], "soundness_checks": soundness,
                      "usefulness_gates": useful, "reference_completed": reference_ok,
                      "completed_as_planned": success, "audit_seconds": receipt["audit_seconds"]}))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
