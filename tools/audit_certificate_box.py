#!/usr/bin/env python3
"""Source-frozen small exact-reference audit for one fixed uncertain RC mode.

Synthetic R/tau and SOC0/Q appear only inside generation/scoring. The provider
receives the public continuous box and observations. The frozen SCM_FULL core
is a separate broader-support comparison under an exact public unit transform.
"""
from __future__ import annotations

import argparse
import ctypes as ct
import datetime as dt
from fractions import Fraction as F
from functools import lru_cache
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import tempfile
import time

import audit_certificate as fixed
from audit_stable import (Attenuation, Charge, Interval, Mask, Checks, ceil, floor,
                          exp_minus_enclosure, finite_json, git, rational, run, sha)
from audit_certificate import (Capacity, SOC, Knot, Sample, Result, clone, ocv_exact,
                               exact_query, evidence_measure, describe, main_sequence)

ROOT = Path(__file__).resolve().parents[1]
PLAN = "experiments/indefinite_stability_004/plan.json"
Z, K, GRID = 65536, 126000000, 1 << 128
D, U32, VOLTAGE_LIMIT = 1 << 32, (1 << 32)-1, 8000000000


class Mode(ct.Structure):
    _fields_ = [("r_lower_mOhm", ct.c_uint32), ("r_upper_mOhm", ct.c_uint32),
                ("tau_lower_ticks", ct.c_uint32), ("tau_upper_ticks", ct.c_uint32)]


class Config(ct.Structure):
    _fields_ = [("cells", ct.c_uint32), ("ocv_knots", ct.c_uint32),
                ("initial_soc_lower", ct.c_int32), ("initial_soc_upper", ct.c_int32),
                ("current_limit_uA", ct.c_int32), ("r0_mOhm", ct.c_uint32),
                ("mode", Mode * 3), ("initial_rc", Interval * 3),
                ("capacity", Capacity * 64), ("ocv", Knot * 17)]


class Bank(ct.Structure):
    _fields_ = [("config", ct.POINTER(Config)), ("charge", Charge),
                ("evidence", Mask), ("rc", Interval * 3), ("initial_soc", SOC * 64)]


class Workspace(ct.Structure):
    _fields_ = [("staged", Bank)]


ABI_SOURCE = r"""
#include "scm_certificate_box.h"
#include <stddef.h>
size_t audit_size_config(void) { return sizeof(scm_certificate_box_config); }
size_t audit_size_bank(void) { return sizeof(scm_certificate_box_bank); }
size_t audit_size_workspace(void) { return sizeof(scm_certificate_box_workspace); }
size_t audit_size_sample(void) { return sizeof(scm_certificate_box_sample); }
size_t audit_size_result(void) { return sizeof(scm_certificate_box_result); }
size_t audit_offset_config_ocv(void) { return offsetof(scm_certificate_box_config,ocv); }
size_t audit_offset_bank_initial_soc(void) { return offsetof(scm_certificate_box_bank,initial_soc); }
size_t audit_offset_result_mask(void) { return offsetof(scm_certificate_box_result,active_mask); }
"""


class API:
    def __init__(self, path: Path):
        self.lib = ct.CDLL(str(path))
        signatures = {
            "config_validate": [ct.POINTER(Config)],
            "init": [ct.POINTER(Bank), ct.POINTER(Config)],
            "push": [ct.POINTER(Bank), ct.POINTER(Sample), ct.POINTER(Workspace)],
            "query": [ct.POINTER(Bank), ct.POINTER(Result)],
            "attenuation": [ct.c_uint32, ct.c_uint32, ct.c_uint32, ct.POINTER(Attenuation)],
            "interval_step": [ct.POINTER(Interval), ct.POINTER(Attenuation), ct.c_int32, ct.c_int32],
        }
        for name, args in signatures.items():
            fn = getattr(self.lib, "scm_certificate_box_" + name)
            fn.argtypes, fn.restype = args, ct.c_int
            setattr(self, name, fn)
        self.fixed_attenuation = self.lib.scm_stable_attenuation_ratio
        self.fixed_attenuation.argtypes = [ct.c_uint32, ct.c_uint32, ct.POINTER(Attenuation)]
        self.fixed_attenuation.restype = ct.c_int
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


def public_config(plan: dict) -> Config:
    p = plan["public_configuration"]
    c = Config()
    c.cells, c.ocv_knots = p["capacity_cells"], len(p["OCV_nodes_SOCgrid_nV"])
    c.initial_soc_lower, c.initial_soc_upper = p["initial_SOC_grid_bounds"]
    c.current_limit_uA, c.r0_mOhm = p["current_limit_microA"], p["R0_milliohm"]
    for j in range(3):
        c.mode[j] = Mode(*p["R_milliohm_boxes"][j], *p["tau_tick_boxes"][j])
        c.initial_rc[j] = Interval(p["initial_RC_nV"][j], p["initial_RC_nV"][j], p["RC_bound_nV"])
    lo, hi = p["capacity_domain_microAh"]
    for j in range(c.cells):
        c.capacity[j] = Capacity(lo+(hi-lo)*j//c.cells, lo+(hi-lo)*(j+1)//c.cells)
    for j, (z, v) in enumerate(p["OCV_nodes_SOCgrid_nV"]):
        c.ocv[j] = Knot(z, v)
    return c


@lru_cache(maxsize=None)
def oracle_coefficient(ticks: int, tau: F):
    lo, hi, _, _ = exp_minus_enclosure(F(ticks)/tau)
    return floor(lo*GRID), ceil(hi*GRID)


class TruthOracle:
    """Generator/scorer state; real R/tau are fixed for this entire trace."""
    def __init__(self, config: Config, z0: F, capacity: F, initial_rc=None, parameters=None):
        self.config, self.z0, self.capacity = config, z0, capacity
        self.charge, self.elapsed_ticks = 0, 0
        self.parameters = [(F(m.r_lower_mOhm+m.r_upper_mOhm, 2),
                            F(m.tau_lower_ticks+m.tau_upper_ticks, 2)) for m in config.mode]
        for j, pair in (parameters or {}).items():
            self.parameters[j] = (F(pair[0]), F(pair[1]))
        for j, (r, tau) in enumerate(self.parameters):
            m = config.mode[j]
            if not (m.r_lower_mOhm <= r <= m.r_upper_mOhm and
                    m.tau_lower_ticks <= tau <= m.tau_upper_ticks):
                raise ValueError("Scorer parameter outside public box")
        initial = initial_rc if initial_rc is not None else [F(r.lower+r.upper, 2) for r in config.initial_rc]
        self.rc = [(floor(F(v)*GRID), ceil(F(v)*GRID)) for v in initial]

    def advance(self, current: int, ticks: int):
        self.charge += current*ticks
        self.elapsed_ticks += ticks
        soc = self.z0-F(self.charge, K*self.capacity)
        for j, (r, tau) in enumerate(self.parameters):
            al, au = oracle_coefficient(ticks, tau)
            xl, xu = self.rc[j]
            target = current*r*GRID
            corners = [F(a*x+(GRID-a)*target, GRID) for a in (al, au) for x in (xl, xu)]
            self.rc[j] = (floor(min(corners)), ceil(max(corners)))
        voltage = ocv_exact(self.config, soc)-current*self.config.r0_mOhm
        lo = voltage-sum(F(r[1], GRID) for r in self.rc)
        hi = voltage-sum(F(r[0], GRID) for r in self.rc)
        return soc, lo, hi


def exercise_trace(api: API, config: Config, z0: F, capacity: F, sequence,
                   checkpoints=None, initial_rc=None, noise=True, parameters=None):
    checks = Checks()
    bank, workspace = api.fresh(config)
    oracle = TruthOracle(config, z0, capacity, initial_rc, parameters)
    truth_bins = [j for j in range(config.cells)
                  if config.capacity[j].lower_uAh <= capacity <= config.capacity[j].upper_uAh]
    checks.check("truth_inside_declared_cover", bool(truth_bins) and
                 config.initial_soc_lower <= z0*Z <= config.initial_soc_upper)
    prior_status, prior_result = api.read(bank)
    checks.check("initial_query_valid", prior_status == 0)
    records, observations = [], []
    max_rc_width = [r.upper-r.lower for r in config.initial_rc]
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
                           "scorer_only_true_capacity_microAh": float(capacity),
                           "RC_intervals_nV": [[r.lower, r.upper] for r in bank.rc]})
            records.append(record)
        prior_result = result
    digest_input = "".join(f"{t} {i} {v} {lo} {hi}\n" for t, i, v, lo, hi in observations)
    return {**checks.result(), "samples": len(observations), "checkpoints": records,
            "truth_bins": truth_bins, "max_observed_RC_width_nV": max_rc_width,
            "minimum_measurement_containment_margin_nV": rational(minimum_margin) if minimum_margin is not None else None,
            "observations_sha256": sha(digest_input.encode()),
            "scorer_only_fixed_R_tau": [[rational(r), rational(t)] for r, t in oracle.parameters]}, observations, bank


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
        c.check("quiet_phase_target_and_evidence_nonwidening",
                rows[2]["capacity_width_microAh"] <= rows[1]["capacity_width_microAh"] and
                rows[2]["current_SOC_width_grid"] <= rows[1]["current_SOC_width_grid"] and
                rows[2]["sum_active_SOC0_widths_grid"] <= rows[1]["sum_active_SOC0_widths_grid"])
    return {**c.result(), "precision_threshold_selected": False,
            "scope": "Predeclared strict narrowing and retention gates; actual finite-grid widths remain explicit."}


def simple_config(base: Config, nodes, prior=(0, Z), cells=None):
    c = clone(base)
    c.initial_soc_lower, c.initial_soc_upper = prior
    c.r0_mOhm = 0
    for j in range(3):
        c.mode[j].r_lower_mOhm = c.mode[j].r_upper_mOhm = 0
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
    bad = clone(base); bad.mode[1].tau_lower_ticks = 0
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


def audit_box_helpers(api: API, base: Config, plan: dict):
    checks = Checks(); coefficients = []; steps = []; invalid = []
    attenuation_cases = [(0, 1, U32), (1, 1, U32), (U32, 1, U32),
                         (32, 1, 2), (33, 1, U32), (U32, U32, U32)]
    attenuation_cases += [(t, 945000, 1155000) for t in (0, *plan["public_configuration"]["actual_tick_pattern"])]
    for ticks, tl, tu in attenuation_cases:
        a = Attenuation(); status = api.attenuation(ticks, tl, tu, ct.byref(a))
        low, _, _, _ = exp_minus_enclosure(F(ticks, tl))
        _, high, _, _ = exp_minus_enclosure(F(ticks, tu))
        checks.check("continuous_tau_endpoint_attenuation_encloses_oracle",
                     status == 0 and F(a.lower, D) <= low <= high <= F(a.upper, D),
                     {"ticks": ticks, "tau": [tl, tu]})
        if ticks == 0:
            checks.check("zero_time_box_attenuation_is_exact_identity", a.lower == a.upper == D)
        coefficients.append({"ticks": ticks, "tau_ticks": [tl, tu], "coefficient": [a.lower, a.upper]})
    for ticks, tl, tu in ((1, 0, 1), (0, 2, 1), (0, 0, 0)):
        a = Attenuation(17, 19); before = bytes(a)
        status = api.attenuation(ticks, tl, tu, ct.byref(a))
        checks.check("invalid_attenuation_output_atomic", status < 0 and bytes(a) == before)
        invalid.append({"helper": "attenuation", "input": [ticks, tl, tu], "status": status})
    state_cases = [(-37, 51, 100, 0, D, -91, 83),
                   (-37, 51, 100, D, D, -91, 83),
                   (-100, 100, 100, 1, D-1, -100, 100),
                   (13, 13, 100, 12345678, 4123456789, -12, -3),
                   (-(1 << 30), 1 << 30, 1 << 30, 0, D, -(1 << 30), 1 << 30)]
    for lo, hi, bound, al, au, fl, fu in state_cases:
        state, a = Interval(lo, hi, bound), Attenuation(al, au)
        before = bytes(state)
        corners = [F(aa*x+(D-aa)*f, D) for aa in (al, au)
                   for x in (lo, hi) for f in (fl, fu)]
        expected = (floor(min(corners)), ceil(max(corners)))
        status = api.interval_step(ct.byref(state), ct.byref(a), fl, fu)
        checks.check("eight_corner_exact_rational_hull", status == 0 and
                     (state.lower, state.upper) == expected,
                     {"state": [lo, hi], "attenuation": [al, au], "forcing": [fl, fu]})
        recurrence = F(au*(hi-lo)+(D-al)*(fu-fl)+2*bound*(au-al), D)+2
        checks.check("one_step_width_recurrence", state.upper-state.lower <= recurrence)
        if al == au == D:
            checks.check("valid_identity_preserves_complete_RC_bytes", bytes(state) == before)
        steps.append({"state": [lo, hi, bound], "coefficient": [al, au], "forcing": [fl, fu],
                      "actual": [state.lower, state.upper], "exact_rational_hull": list(expected)})
    for al, au, fl, fu in ((D, D, 5, 4), (D, D, -101, 0),
                          (D, D, 0, 101), (D+1, D+1, 0, 0), (2, 1, 0, 0)):
        state, a = Interval(-20, 30, 100), Attenuation(al, au)
        before = bytes(state); status = api.interval_step(ct.byref(state), ct.byref(a), fl, fu)
        checks.check("invalid_forcing_or_coefficient_rejected_before_identity",
                     status < 0 and bytes(state) == before)
        invalid.append({"helper": "interval_step", "input": [al, au, fl, fu], "status": status})
    # Explicit signed forcing ordering: multiplication reverses R endpoints at I<0.
    for current in (-200000, -1, 0, 1, 200000):
        fl, fu = sorted((current*54, current*66))
        for r in (F(54), F(241, 4), F(66)):
            checks.check("signed_R_forcing_contains_real_parameter", fl <= current*r <= fu)
    mutations = [
        ("reversed_R", lambda c: setattr(c.mode[2], "r_lower_mOhm", 67)),
        ("reversed_tau", lambda c: setattr(c.mode[2], "tau_lower_ticks", 1155001)),
        ("zero_tau", lambda c: setattr(c.mode[2], "tau_lower_ticks", 0)),
        ("R_exceeds_encoding", lambda c: setattr(c.mode[2], "r_upper_mOhm", 1001)),
        ("forcing_exceeds_state_domain", lambda c: setattr(c.mode[2], "r_upper_mOhm", 84)),
        ("second_uncertain_R", lambda c: setattr(c.mode[0], "r_upper_mOhm", 31)),
        ("second_uncertain_tau", lambda c: setattr(c.mode[1], "tau_upper_ticks", 17501)),
    ]
    bank, _ = api.fresh(base)
    for label, mutate in mutations:
        bad = clone(base); mutate(bad); before = bytes(bank)
        validate = api.config_validate(ct.byref(bad))
        status = api.init(ct.byref(bank), ct.byref(bad))
        checks.check("invalid_box_config_rejects_complete_init_atomically",
                     validate < 0 and status < 0 and bytes(bank) == before, {"case": label})
        invalid.append({"configuration": label, "validate": validate, "init": status})
    # One parameter alone may be uncertain, and a wholly degenerate box is legal.
    for label, vary_r, vary_tau in (("R_only", True, False), ("tau_only", False, True),
                                   ("degenerate", False, False)):
        candidate = clone(base)
        if not vary_r:
            candidate.mode[2].r_lower_mOhm = candidate.mode[2].r_upper_mOhm = 60
        if not vary_tau:
            candidate.mode[2].tau_lower_ticks = candidate.mode[2].tau_upper_ticks = 1050000
        checks.check("admitted_single_or_degenerate_box", api.config_validate(ct.byref(candidate)) == 0,
                     {"case": label})
    fractional = plan["small_fractional_case"]
    sequence = [(fractional["current_recipe_microA"][k % len(fractional["current_recipe_microA"])],
                 fractional["tick_recipe"][k % len(fractional["tick_recipe"])])
                for k in range(fractional["samples"])]
    trace, _, _ = exercise_trace(api, base, F(53, 100), F(64700), sequence,
        parameters={2: (F(*fractional["actual_R_mOhm"]), F(*fractional["actual_tau_ticks"]))})
    checks.check("fractional_real_R_tau_trace", trace["passed"])
    return {**checks.result(), "attenuation_cases": coefficients, "interval_cases": steps,
            "invalid_cases": invalid, "fractional_trace": trace,
            "scope": "Constructed helper boundaries and one continuous-parameter truth; fixed parameters persist through the entire trace."}


def bank_numerical(bank, config):
    return (bank.charge.value, bank.charge.lower, bank.charge.upper,
            bank.evidence.domain, bank.evidence.active,
            tuple((r.lower, r.upper, r.bound) for r in bank.rc),
            tuple((bank.initial_soc[j].lower, bank.initial_soc[j].upper) for j in range(config.cells)))


def result_numerical(result):
    return (result.soc_lower, result.soc_upper, result.capacity_lower_uAh,
            result.capacity_upper_uAh, result.active_mask, result.active_cells, result.has_support)


def degenerate_config(base: Config, plan: dict):
    c = clone(base); p = plan["public_configuration"]
    for j in range(3):
        c.mode[j] = Mode(p["Ri_milliohm"][j], p["Ri_milliohm"][j],
                         p["tau_ticks"][j], p["tau_ticks"][j])
    return c


def audit_degenerate_control(api: API, old_api: fixed.API, base: Config, plan: dict,
                             observations, checkpoints):
    checks = Checks(); nominal = degenerate_config(base, plan); old_config = fixed.public_config(plan)
    bank, work = api.fresh(nominal); boxed, boxed_work = api.fresh(base)
    old, old_work = old_api.fresh(old_config); records = []; coefficient_rows = []
    for t in (0, *plan["public_configuration"]["actual_tick_pattern"]):
        for j in range(3):
            a, b = Attenuation(), Attenuation(); m = base.mode[j]; n = nominal.mode[j]
            sa = api.attenuation(t, m.tau_lower_ticks, m.tau_upper_ticks, ct.byref(a))
            sb = api.attenuation(t, n.tau_lower_ticks, n.tau_upper_ticks, ct.byref(b))
            checks.check("public_alphabet_nominal_coefficient_contained",
                         sa == sb == 0 and a.lower <= b.lower <= b.upper <= a.upper,
                         {"mode": j, "ticks": t})
            coefficient_rows.append({"mode": j, "ticks": t, "box": [a.lower, a.upper],
                                     "nominal": [b.lower, b.upper]})
    max_width = [0, 0, 0]
    for k, (ticks, current, center, lower, upper) in enumerate(observations):
        sample = Sample(current, ticks, lower, upper)
        s = api.push(ct.byref(bank), ct.byref(sample), ct.byref(work))
        bs = api.push(ct.byref(boxed), ct.byref(sample), ct.byref(boxed_work))
        os = old_api.push(ct.byref(old), ct.byref(sample), ct.byref(old_work))
        qs, result = api.read(bank); bqs, br = api.read(boxed); oqs, old_result = old_api.read(old)
        checks.check("degenerate_matches_frozen003_status_and_all_numerical_fields",
                     s == os == qs == oqs == 0 and bank_numerical(bank, nominal) == bank_numerical(old, old_config)
                     and result_numerical(result) == result_numerical(old_result), {"sample": k})
        checks.check("adding_uncertainty_contains_nominal_RC_and_evidence",
                     bs == bqs == 0 and bank.evidence.active & ~boxed.evidence.active == 0
                     and all(boxed.rc[j].lower <= bank.rc[j].lower <= bank.rc[j].upper <= boxed.rc[j].upper
                             for j in range(3))
                     and all(not (bank.evidence.active & (1 << j)) or
                             boxed.initial_soc[j].lower <= bank.initial_soc[j].lower <=
                             bank.initial_soc[j].upper <= boxed.initial_soc[j].upper for j in range(base.cells)),
                     {"sample": k})
        checks.check("adding_uncertainty_contains_nominal_target_hulls",
                     br.soc_lower <= result.soc_lower <= result.soc_upper <= br.soc_upper and
                     br.capacity_lower_uAh <= result.capacity_lower_uAh <=
                     result.capacity_upper_uAh <= br.capacity_upper_uAh, {"sample": k})
        for j in range(3):
            max_width[j] = max(max_width[j], bank.rc[j].upper-bank.rc[j].lower)
        if k+1 in checkpoints:
            record = describe(nominal, bank, result)
            record.update({"samples": k+1, "stage": checkpoints[k+1],
                           "RC_intervals_nV": [[r.lower, r.upper] for r in bank.rc]})
            records.append(record)
    return {**checks.result(), "samples": len(observations), "checkpoints": records,
            "coefficient_containment_enumeration": coefficient_rows,
            "max_observed_RC_width_nV": max_width,
            "observations_policy": "Exactly the main public midpoint observations; frozen003 source is compiled without rerunning its historical campaign.",
            "numerical_equivalence_scope": "Every status and named numerical field; config pointers, object padding and implementation metadata are excluded.",
            "nesting_scope": "Certified for this tick alphabet and these midpoint observations. Generic numerical attenuation nesting is not assumed."}


def audit_width(api: API, config: Config, plan: dict, traces: list[dict], degenerate: dict):
    checks = Checks(); modes = []
    ticks = plan["width_analysis"]["future_tick_alphabet"]
    currents = plan["width_analysis"]["future_current_alphabet_microA"]
    for j in range(3):
        m = config.mode[j]; rows = []; model_spans = []; arithmetic_excess = []
        for t in ticks:
            a = Attenuation()
            status = api.attenuation(t, m.tau_lower_ticks, m.tau_upper_ticks, ct.byref(a))
            lo_l, lo_u, _, _ = exp_minus_enclosure(F(t, m.tau_lower_ticks))
            hi_l, hi_u, _, _ = exp_minus_enclosure(F(t, m.tau_upper_ticks))
            checks.check("width_coefficient_oracle_enclosure", status == 0 and
                         F(a.lower, D) <= lo_l <= hi_u <= F(a.upper, D))
            if m.tau_lower_ticks == m.tau_upper_ticks:
                physical_lo = physical_hi = F(0)
            else:
                physical_lo, physical_hi = hi_l-lo_u, hi_u-lo_l
            excess = (F(a.upper, D)-hi_l)+(lo_u-F(a.lower, D))
            model_spans.append(physical_hi*D); arithmetic_excess.append(excess*D)
            rows.append({"ticks": t, "lower": a.lower, "upper": a.upper,
                         "physical_coefficient_span_lower": rational(physical_lo),
                         "physical_coefficient_span_upper": rational(physical_hi),
                         "kernel_endpoint_excess_upper": rational(excess)})
        g = min(D-r["upper"] for r in rows); h = max(r["upper"]-r["lower"] for r in rows)
        b = max(D-r["lower"] for r in rows)
        fmax = max(abs(i)*(m.r_upper_mOhm-m.r_lower_mOhm) for i in currents)
        checks.check("strict_future_alphabet_contraction_gap", g > 0, {"mode": j})
        bound = config.initial_rc[j].bound; w0 = config.initial_rc[j].upper-config.initial_rc[j].lower
        numerator = b*fmax+2*bound*h+2*D
        stationary = F(numerator, g) if g > 0 else None
        full = min(F(2*bound), max(F(w0), stationary)) if stationary is not None else None
        observed = [trace["max_observed_RC_width_nV"][j] for trace in traces]
        checks.check("every_full_phase_case_observed_width_within_theorem",
                     full is not None and all(w <= full for w in observed), {"mode": j, "observed": observed})
        model_h, arithmetic_h = max(model_spans), max(arithmetic_excess)
        checks.check("coefficient_span_decomposition_bounds_h", F(h) <= model_h+arithmetic_h)
        contributions = None if g <= 0 else {
            "forcing_interval_stationary_nV": rational(F(b*fmax, g)),
            "combined_coefficient_span_stationary_nV": rational(F(2*bound*h, g)),
            "integer_endpoint_rounding_stationary_nV": rational(F(2*D, g)),
            "physical_tau_span_stationary_upper_nV": rational(2*bound*model_h/g),
            "kernel_attenuation_overenclosure_stationary_upper_nV": rational(2*bound*arithmetic_h/g),
            "scope": "The first three sum exactly to the unsaturated stationary bound. Separate physical/endpoint maxima conservatively bound the combined coefficient contribution; their maxima need not share one tick."}
        modes.append({"mode": j, "R_mOhm_box": [m.r_lower_mOhm, m.r_upper_mOhm],
                      "tau_ticks_box": [m.tau_lower_ticks, m.tau_upper_ticks],
                      "B_nV": bound, "W0_nV": w0, "coefficient_enumeration": rows,
                      "g": g, "h": h, "b": b, "Fmax_nV": fmax,
                      "exact_stationary_numerator": str(numerator),
                      "all_time_width_bound_nV": rational(full) if full is not None else None,
                      "all_time_width_bound_nV_approx": float(full) if full is not None else None,
                      "unsaturated_stationary_bound_nV": rational(stationary) if stationary is not None else None,
                      "contribution_decomposition": contributions, "observed_widths_by_full_case_nV": observed,
                      "degenerate_main_max_observed_width_nV": degenerate["max_observed_RC_width_nV"][j]})
    return {**checks.result(), "modes": modes, "future_tick_alphabet": ticks,
            "future_current_alphabet_microA": currents,
            "current_extension": "Endpoint |I| bound covers every admitted represented current between the extreme alphabet values.",
            "proof_source": "proofs/indefinite_stability_004/lemmas.json",
            "method": "Exact finite coefficient enumeration establishes theorem premises; the written induction supplies all-prefix scope. This is not extrapolation from observed widths.",
            "warning_on_interpretation": "Nondegenerate width contains model ambiguity and discarded correlations as well as integer/kernel rounding; it is not numerical error alone."}


def audit_unit_transform(plan: dict):
    checks = Checks(); p = plan["public_configuration"]
    scale = F(plan["retained_history_comparison"]["public_unit_transform"]["scale"])
    count = 0
    for ticks in (0, *p["actual_tick_pattern"]):
        dt_physical = F(ticks, p["tick_frequency_Hz"]); dt_internal = dt_physical/scale
        for current in (-200000, -120000, 0, 200000):
            i_physical = F(current, 1000000); i_internal = scale*i_physical
            checks.check("unit_transform_charge_identity", i_internal*dt_internal == i_physical*dt_physical)
            for j in range(3):
                for r in p["R_milliohm_boxes"][j]:
                    for tau in p["tau_tick_boxes"][j]:
                        rp = F(r, 1000); tp = F(tau, p["tick_frequency_Hz"])
                        checks.check("unit_transform_attenuation_and_forcing_identity",
                                     dt_internal/(tp/scale) == dt_physical/tp and
                                     i_internal*(rp/scale) == i_physical*rp)
                        count += 1
    return {**checks.result(), "scale": int(scale), "parameter_endpoint_combinations": count,
            "consequence": "Equal charge, attenuation and forcing preserve RC trajectory, SOC and terminal voltage in real arithmetic with identical initial states and encoded OCV. The actual C/libm reference remains ordinary floating point; no bitwise identity is claimed."}


def reference_inputs(config: Config, observations, temporary: Path):
    model_lines = [f"35000 {Z} 3 {config.ocv_knots} 2 2", str(config.r0_mOhm)]
    model_lines += [f"{m.r_lower_mOhm} {m.r_upper_mOhm} {m.tau_lower_ticks} {m.tau_upper_ticks}" for m in config.mode]
    model_lines.append(" ".join(str(x.lower) for x in config.initial_rc))
    model_lines += [f"{config.ocv[j].soc} {config.ocv[j].voltage_nV}" for j in range(config.ocv_knots)]
    model_text = "\n".join(model_lines)+"\n"
    data_text = str(len(observations))+"\n"+"".join(f"{t} {i} {v}\n" for t, i, v, _, _ in observations)
    model, data = temporary/"public_box_model.txt", temporary/"observations.txt"
    model.write_text(model_text); data.write_text(data_text)
    return model, data, {"public_model_sha256": sha(model_text.encode()),
                         "reference_observations_sha256": sha(data_text.encode()),
                         "truth_columns_or_parameters_present": False,
                         "selected_parameter_input": "Public full box only; selected actual R/tau never supplied."}


def symmetric_eigenvalues(values):
    """Tiny ordinary-double Jacobi diagonalization for descriptive conditioning."""
    a = [[(values[4*i+j]+values[4*j+i])/2 for j in range(4)] for i in range(4)]
    for _ in range(128):
        i, j = max(((i, j) for i in range(4) for j in range(i+1, 4)), key=lambda x: abs(a[x[0]][x[1]]))
        if abs(a[i][j]) <= 1e-15*max(max(abs(a[k][k]) for k in range(4)), 1e-300):
            break
        angle = .5*math.atan2(2*a[i][j], a[j][j]-a[i][i])
        c, s = math.cos(angle), math.sin(angle)
        aii, ajj, aij = a[i][i], a[j][j], a[i][j]
        a[i][i] = c*c*aii-2*c*s*aij+s*s*ajj
        a[j][j] = s*s*aii+2*c*s*aij+c*c*ajj
        a[i][j] = a[j][i] = 0.
        for k in range(4):
            if k not in (i, j):
                x, y = a[k][i], a[k][j]
                a[k][i] = a[i][k] = c*x-s*y
                a[k][j] = a[j][k] = s*x+c*y
    return sorted(a[k][k] for k in range(4))


def local_conditioning(raw):
    eigenvalues = symmetric_eigenvalues(raw); largest = max(abs(x) for x in eigenvalues)
    threshold = 1e-12*largest
    rank = sum(x > threshold for x in eigenvalues)
    condition = eigenvalues[-1]/eigenvalues[0] if rank == 4 and eigenvalues[0] > 0 else None
    return {"symmetric_eigenvalues": eigenvalues, "relative_rank_threshold": 1e-12,
            "absolute_rank_threshold": threshold, "positive_rank": rank,
            "condition_number_if_full_positive_rank": condition,
            "singular_or_not_full_positive_rank": rank != 4,
            "scope": "Ordinary-double local raw Gram in scaled free coordinates [logtau,SOC0/.1,logQ,Rphysical/.4]. Conditions on fixed known parameters; no posterior, global identification, marginal precision or coverage inference."}


def compare_reference(plan: dict, config: Config, observations, main: dict, temp: Path):
    model, data, hashes = reference_inputs(config, observations, temp)
    command = [str(temp/"provider_box_reference_probe"), str(model), str(data)] + [
        str(x) for x in plan["retained_history_comparison"]["prefix_samples"]]
    execution = run(command, timeout=60)
    result = {"command": execution, "input_hashes": hashes, "completed": False,
              "support_difference": plan["retained_history_comparison"]["feasible_set_difference"],
              "unit_transform": plan["retained_history_comparison"]["public_unit_transform"]}
    if execution["returncode"] == 0:
        output = json.loads(execution["stdout"]); result["output"] = output
        by_n = {r["samples"]: r for r in main["checkpoints"]}; comparisons = []
        truth = plan["generator_and_scorer_only"]; actual = plan["full_phase_cases"][0]
        for fit in output.get("fits", []):
            cp = by_n[fit["samples"]]
            if fit["return_code"] != 0:
                continue
            q = fit["capacity_Ah"]*1e6
            fit["local_conditioning"] = local_conditioning(fit["conditional_raw_Gram_scaled_free4"])
            comparisons.append({"samples": fit["samples"], "stage": cp["stage"],
                "numerically_converged": fit["status"] == 0,
                "current_SOC_point": fit["current_SOC"], "capacity_point_microAh": q,
                "scorer_only_current_SOC_error_pp": 100*(fit["current_SOC"]-cp["scorer_only_true_current_SOC"]),
                "scorer_only_capacity_error_percent": 100*(q/truth["capacity_microAh"]-1),
                "scorer_only_selected_R_error_percent": 100*(fit["selected_physical_R_mOhm"]/float(F(*actual["actual_R_mOhm"]))-1),
                "scorer_only_selected_tau_error_percent": 100*(fit["selected_physical_tau_s"]/(float(F(*actual["actual_tau_ticks"]))/35000)-1),
                "reference_point_in_certificate_SOC_hull": cp["current_SOC"][0] <= fit["current_SOC"] <= cp["current_SOC"][1],
                "reference_point_in_certificate_capacity_hull": cp["capacity_microAh"][0] <= q <= cp["capacity_microAh"][1],
                "reference_R_point_in_declared_box": config.mode[2].r_lower_mOhm <= fit["selected_physical_R_mOhm"] <= config.mode[2].r_upper_mOhm,
                "reference_tau_point_in_declared_box": config.mode[2].tau_lower_ticks/35000 <= fit["selected_physical_tau_s"] <= config.mode[2].tau_upper_ticks/35000})
        result["comparisons"] = comparisons
        result["completed"] = output.get("completed", False) and len(comparisons) == 4
    result["interpretation"] = "Same observations and physically identical public model under scale2, but the frozen reference has broader R/tau support and a Gaussian objective. Point errors are scored only afterward. Numerical convergence, local curvature, outer hard-bound support and coverage remain distinct."
    return result


def precision_comparison(cases: dict, degenerate: dict):
    baseline = {r["samples"]: r for r in degenerate["checkpoints"]}; rows = []
    for name, trace in cases.items():
        for record in trace["checkpoints"]:
            old = baseline[record["samples"]]
            rows.append({"case": name, "samples": record["samples"], "stage": record["stage"],
                "capacity_width_microAh": record["capacity_width_microAh"],
                "degenerate_midpoint_capacity_width_microAh": old["capacity_width_microAh"],
                "capacity_width_ratio_to_degenerate_midpoint": record["capacity_width_microAh"]/old["capacity_width_microAh"] if old["capacity_width_microAh"] else None,
                "SOC_width_grid": record["current_SOC_width_grid"],
                "degenerate_midpoint_SOC_width_grid": old["current_SOC_width_grid"],
                "SOC_width_ratio_to_degenerate_midpoint": record["current_SOC_width_grid"]/old["current_SOC_width_grid"] if old["current_SOC_width_grid"] else None,
                "retained_SOC0_evidence_measure_grid": record["sum_active_SOC0_widths_grid"]})
    return {"rows": rows,
            "scope": "Midpoint ratios use identical observations. Corner ratios compare against the public midpoint control and include changed synthetic observations; they are descriptive and not paired isolates of uncertainty.",
            "threshold_selected_after_results": False}


def memory_report(api: API, temp: Path, commands, reference: dict):
    frames = []
    for component in ("certificate_box", "stable"):
        for line in (temp/(component+".su")).read_text().splitlines():
            fields = line.split("\t")
            if len(fields) == 3:
                frames.append({"component": component, "function": fields[0].rsplit(":", 1)[-1],
                               "bytes": int(fields[1]), "kind": fields[2]})
    undefined = {name: commands[name+"_undefined"]["stdout"] for name in ("certificate_box", "stable")}
    imports = "\n".join(undefined.values())
    heap = re.findall(r"\b(?:malloc|calloc|realloc|free)\b", imports)
    math_imports = re.findall(r"\b(?:exp|expm1|log|sqrt|pow|tanh|sin|cos)\b", imports)
    stack_sum = sum(f["bytes"] for f in frames)
    inspection_ok = all(commands[name+suffix]["returncode"] == 0
                        for name in ("certificate_box", "stable")
                        for suffix in ("_undefined", "_sections"))
    stack_ok = all(any(f["component"] == name for f in frames)
                   for name in ("certificate_box", "stable")) and all(
                       f["kind"] == "static" and f["bytes"] >= 0 for f in frames)
    ref_rows = []; output = reference.get("output", {})
    caller = sum(output.get(k, 0) for k in ("caller_input_sample_bytes", "caller_model_bytes",
                                          "caller_options_bytes", "caller_result_bytes"))
    for fit in output.get("fits", []):
        if fit.get("return_code") == 0:
            ref_rows.append({"samples": fit["samples"], "internal_retained_bytes": fit["retained_bytes"],
                             "internal_setup_peak_bytes": fit["setup_peak_bytes"],
                             "audit_driver_live_objects_and_full_trace_input_bytes": caller,
                             "internal_plus_driver_owned_subtotal_bytes": fit["retained_bytes"]+caller})
    return {"host_object_bytes": api.sizes,
            "object_inspection_commands_succeeded": inspection_ok,
            "nonempty_static_stack_reports_for_each_core_component": stack_ok,
            "simultaneous_config_bank_workspace_sample_result_bytes": sum(api.sizes.values()),
            "compiler_stack_frames": frames, "largest_reported_core_frame_bytes": max(f["bytes"] for f in frames),
            "conservative_sum_all_reported_core_frames_bytes": stack_sum,
            "objects_plus_loose_own_stack_subtotal_bytes": sum(api.sizes.values())+stack_sum,
            "stack_scope": "Loose sum of nonrecursive own-source frames including initialization and branches; not measured high-water. Runtime/caller/interrupt stack and target compiler remain unqualified.",
            "undefined_symbols": undefined, "heap_imports": heap, "libm_imports": math_imports,
            "object_sections": {name: commands[name+"_sections"]["stdout"] for name in ("certificate_box", "stable")},
            "complete_backing_configuration_included": True,
            "reference_allocation_comparison": ref_rows,
            "reference_scope": "Frozen solver-reported heap allocations plus explicit probe caller input/model/options/result objects. The probe retains the complete3675sample input buffer even at early fit prefixes. Excludes allocator overhead, complete reference stack/text, runtime and OS; not a complete firmware comparison.",
            "scope": "Provider includes complete configuration backing cells/OCV, bank, stagedworkspace, input/output, own-source stack and object sections/imports. Acquisition, persistence, delivery and complete firmware resources are not qualified.",
            "Cortex_M23_qualified": False, "complete_firmware_resources_qualified": False}


def frozen_inventory(base_revision: str):
    paths = ["src", "include", "tools", "data", "results", "experiments", "proofs",
             "reference_binaries", "provenance", "report"]
    tree = git("ls-tree", "-r", base_revision, "--", *paths).decode().splitlines()
    expected, matches, sha256 = {}, {}, {}
    for line in tree:
        metadata, path = line.split("\t", 1)
        mode, kind, object_id = metadata.split()
        if kind != "blob":
            raise RuntimeError("Unexpected frozen object: " + path)
        data = (ROOT/path).read_bytes()
        actual = hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
        expected[path] = object_id; matches[path] = actual == object_id; sha256[path] = sha(data)
    return {"base_revision": base_revision, "preserved_path_roots": paths,
            "base_git_blob_ids": expected, "matches_base_git_blob": matches, "sha256": sha256}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--development", action="store_true")
    parser.add_argument("--source-revision", help="Explicit root-provided frozen source SHA; required for primary")
    args = parser.parse_args()
    output = args.output.resolve() if args.output.is_absolute() else (ROOT/args.output).resolve()
    if output.exists():
        raise FileExistsError(f"Refusing existing receipt: {output}")
    if args.development and (output == ROOT or ROOT in output.parents):
        raise ValueError("Development receipts must be outside the repository")
    if not args.development and not args.source_revision:
        raise ValueError("Primary requires an explicit --source-revision frozen by the root coordinator")
    plan = json.loads((ROOT/PLAN).read_text())
    before = {p: sha((ROOT/p).read_bytes()) for p in plan["sources"]}
    head = git("rev-parse", "HEAD").decode().strip()
    source_revision = git("rev-parse", "--verify", args.source_revision or head).decode().strip()
    committed = {}
    for p in before:
        snapshot = subprocess.run(["git", "show", source_revision+":"+p], cwd=ROOT, capture_output=True, check=False)
        committed[p] = snapshot.returncode == 0 and sha(snapshot.stdout) == before[p]
    if not args.development and not all(committed.values()):
        raise RuntimeError("Primary source/plan/proofs must match the supplied committed source revision")
    frozen_before = frozen_inventory(plan["base_revision"])
    if not all(frozen_before["matches_base_git_blob"].values()):
        raise RuntimeError("A preserved pre004 source, tool, proof or evidence file differs from the base")
    compiler = shlex.split(os.environ.get("CC", "cc"))
    if not compiler or not shutil.which(compiler[0]):
        raise RuntimeError("C compiler not found")
    compiler[0] = str(Path(shutil.which(compiler[0])).resolve()); flags = plan["compiler_flags"]
    receipt = {"schema": "mumble_uncertain_RC_certificate_audit_receipt_v1",
        "mode": "development" if args.development else "primary",
        "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_revision": source_revision, "repository_HEAD_at_start": head,
        "branch": git("branch", "--show-current").decode().strip(),
        "plan": PLAN, "source_sha256_before": before, "sources_match_frozen_commit_before_run": committed,
        "preserved_files_before": frozen_before,
        "platform": {"system": platform.system(), "machine": platform.machine(),
                     "release": platform.release(), "python": platform.python_version(), "libc": list(platform.libc_ver())},
        "compiler_version": run(compiler+["--version"]), "commands": {}, "audits": {},
        "nonclaims": plan["nonclaims"], "design_decisions_before_development": plan["design_decisions_before_development"],
        "development_checks_preceded_primary_source_freeze": True}
    started = time.monotonic(); compiled = False
    with tempfile.TemporaryDirectory(prefix="mumble-certificate-box-audit-") as directory:
        temp = Path(directory)
        (temp/"abi.c").write_text(ABI_SOURCE); (temp/"fixed_abi.c").write_text(fixed.ABI_SOURCE)
        core = ["src/scm_stable.c", "src/scm_certificate_box.c"]; cmd = receipt["commands"]
        cmd["provider_shared_compile"] = run(compiler+flags+["-Iinclude", "-shared", "-fPIC", *core,
            str(temp/"abi.c"), "-o", str(temp/"provider_box.so")])
        cmd["fixed_control_shared_compile"] = run(compiler+flags+["-Iinclude", "-shared", "-fPIC",
            "src/scm_stable.c", "src/scm_certificate.c", str(temp/"fixed_abi.c"), "-o", str(temp/"provider_fixed.so")])
        cmd["provider_unit_compile"] = run(compiler+flags+["-Iinclude", *core, "src/scm_certificate.c",
            "tests/test_certificate_box.c", "-o", str(temp/"test_certificate_box")])
        cmd["reference_compile"] = run(compiler+flags+["-Iinclude", "src/scm_model.c", "src/scm_features.c",
            "src/scm_estimator.c", "tools/provider_box_reference_probe.c", "-lm", "-o", str(temp/"provider_box_reference_probe")])
        for name in ("certificate_box", "stable"):
            cmd[name+"_core_compile"] = run(compiler+flags+["-Iinclude", "-fstack-usage", "-c",
                "src/scm_"+name+".c", "-o", str(temp/(name+".o"))])
        compiled = all(v["returncode"] == 0 for v in cmd.values())
        if compiled:
            receipt["binary_sha256"] = {name: sha((temp/name).read_bytes()) for name in
                ("provider_box.so", "provider_fixed.so", "test_certificate_box", "provider_box_reference_probe", "certificate_box.o", "stable.o")}
            cmd["provider_unit_run"] = run([str(temp/"test_certificate_box")])
            for name in ("certificate_box", "stable"):
                cmd[name+"_undefined"] = run(["nm", "-u", str(temp/(name+".o"))])
                cmd[name+"_sections"] = run(["size", "-A", str(temp/(name+".o"))])
            try:
                api = API(temp/"provider_box.so"); old_api = fixed.API(temp/"provider_fixed.so")
                config = public_config(plan); sequence, checkpoints = main_sequence(plan)
                truth = plan["generator_and_scorer_only"]; cases = {}; useful = {}
                for case in plan["full_phase_cases"]:
                    result, observations, bank = exercise_trace(api, config, F(*truth["initial_SOC"]),
                        F(truth["capacity_microAh"]), sequence, checkpoints,
                        parameters={2: (F(*case["actual_R_mOhm"]), F(*case["actual_tau_ticks"]))})
                    cases[case["name"]] = result; useful[case["name"]] = audit_usefulness(result)
                    if case["name"] == "public_midpoint":
                        main_observations, main_bank = observations, bank
                receipt["full_phase_cases"] = cases
                receipt["usefulness_by_case"] = useful
                aggregate = Checks(); gates = Checks()
                for name, trace in cases.items():
                    aggregate.check("full_phase_trace_soundness", trace["passed"], {"case": name})
                    gates.check("unchanged_four_phase_usefulness_gates", useful[name]["passed"], {"case": name})
                receipt["audits"]["full_phase_soundness_summaries"] = aggregate.result()
                receipt["audits"]["conditional_usefulness_summaries"] = gates.result()
                receipt["audits"]["boundary_canaries"] = audit_canaries(api, config, main_bank, plan)
                receipt["audits"]["box_helpers_and_fractional_parameters"] = audit_box_helpers(api, config, plan)
                receipt["audits"]["degenerate_and_nested_control"] = audit_degenerate_control(api, old_api,
                    config, plan, main_observations, checkpoints)
                degenerate = receipt["audits"]["degenerate_and_nested_control"]
                receipt["audits"]["all_prefix_width_premises"] = audit_width(api, config, plan, list(cases.values()), degenerate)
                receipt["audits"]["public_reference_unit_transform"] = audit_unit_transform(plan)
                receipt["precision_comparison"] = precision_comparison(cases, degenerate)
                receipt["retained_history_reference"] = compare_reference(plan, config, main_observations,
                    cases["public_midpoint"], temp)
                receipt["memory"] = memory_report(api, temp, cmd, receipt["retained_history_reference"])
            except Exception as exc:
                receipt["audit_exception"] = {"type": type(exc).__name__, "message": str(exc)}
    after = {p: sha((ROOT/p).read_bytes()) for p in plan["sources"]}
    frozen_after = frozen_inventory(plan["base_revision"])
    receipt["source_sha256_after"] = after
    receipt["sources_unchanged_during_run"] = before == after
    receipt["preserved_files_after_sha256"] = frozen_after["sha256"]
    receipt["preserved_files_match_base_after"] = frozen_after["matches_base_git_blob"]
    receipt["preserved_files_unchanged_during_run"] = frozen_before["sha256"] == frozen_after["sha256"]
    receipt["audit_seconds"] = time.monotonic()-started
    soundness_keys = ("full_phase_soundness_summaries", "boundary_canaries", "box_helpers_and_fractional_parameters",
                      "degenerate_and_nested_control", "all_prefix_width_premises", "public_reference_unit_transform")
    soundness = compiled and receipt["commands"].get("provider_unit_run", {}).get("returncode") == 0 and all(
        receipt["audits"].get(name, {}).get("passed", False) for name in soundness_keys)
    useful = receipt["audits"].get("conditional_usefulness_summaries", {}).get("passed", False)
    reference_ok = receipt.get("retained_history_reference", {}).get("completed", False)
    memory_ok = "memory" in receipt and receipt["memory"]["object_inspection_commands_succeeded"] and receipt["memory"]["nonempty_static_stack_reports_for_each_core_component"] and not receipt["memory"]["heap_imports"] and not receipt["memory"]["libm_imports"]
    top_checks = sum(a["checks"] for a in receipt["audits"].values())
    nested_trace_checks = sum(c["checks"] for c in receipt.get("full_phase_cases", {}).values())
    nested_usefulness_checks = sum(c["checks"] for c in receipt.get("usefulness_by_case", {}).values())
    nested_canary_checks = sum(c.get("checks", 0) for c in receipt["audits"].get("boundary_canaries", {}).get("cases", {}).values() if isinstance(c, dict))
    nested_fractional_checks = receipt["audits"].get("box_helpers_and_fractional_parameters", {}).get("fractional_trace", {}).get("checks", 0)
    nested_total = nested_trace_checks+nested_usefulness_checks+nested_canary_checks+nested_fractional_checks
    top_failed = sum(len(a["failures"]) for a in receipt["audits"].values())
    nested_failed = sum(len(c["failures"]) for c in receipt.get("full_phase_cases", {}).values())
    nested_failed += sum(len(c["failures"]) for c in receipt.get("usefulness_by_case", {}).values())
    nested_failed += sum(len(c.get("failures", [])) for c in receipt["audits"].get("boundary_canaries", {}).get("cases", {}).values() if isinstance(c, dict))
    nested_failed += len(receipt["audits"].get("box_helpers_and_fractional_parameters", {}).get("fractional_trace", {}).get("failures", []))
    receipt["assertion_counts"] = {
        "top_level": top_checks, "top_level_failed": top_failed,
        "nested_full_phase_trace_checks": nested_trace_checks,
        "nested_usefulness_checks": nested_usefulness_checks, "nested_boundary_trace_checks": nested_canary_checks,
        "nested_fractional_trace_checks": nested_fractional_checks,
        "nested_total": nested_total, "nested_failed": nested_failed,
        "total_including_nested_and_summary_gates": top_checks+nested_total,
        "failed_including_nested_and_summary_gates": top_failed+nested_failed,
        "scope": "Top-level gates summarize nested trace/usefulness assertions and therefore overlap. Counts are finite correspondence evidence, not a lifetime quantifier."}
    preserved = all(frozen_after["matches_base_git_blob"].values()) and receipt["preserved_files_unchanged_during_run"]
    executed = compiled and "audit_exception" not in receipt and all(k in receipt["audits"] for k in soundness_keys) and reference_ok and memory_ok and before == after and preserved
    accepted = executed and soundness and useful and (args.development or all(committed.values()))
    receipt.update({"sampled_provider_soundness_checks_passed": soundness,
                    "conditional_usefulness_gates_passed": useful,
                    "reference_comparison_completed": reference_ok,
                    "experiment_executed_as_planned": executed,
                    "all_acceptance_gates_passed": accepted,
                    "full_battery_estimator_indefinite_stability_proved": False,
                    "finished_utc": dt.datetime.now(dt.timezone.utc).isoformat()})
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        stream.write(finite_json(receipt))
    print(json.dumps({"receipt": str(output), "mode": receipt["mode"], "soundness_checks": soundness,
                      "usefulness_gates": useful, "reference_completed": reference_ok,
                      "executed_as_planned": executed, "all_acceptance_gates_passed": accepted,
                      "audit_seconds": receipt["audit_seconds"]}))
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
