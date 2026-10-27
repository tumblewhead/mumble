#!/usr/bin/env python3
"""One frozen, bounded fabricated qualification of the rolling integration.

The C shared library is qualification-only.  Its pass-through wrappers count
kernel attempts and save bounded query records; the canonical engine is never
linked to this host instrumentation.  No archived observations are opened.
"""
import argparse
from contextlib import contextmanager
import ctypes as C
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import resource
import shutil
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
EXP = HERE.parent
PLAN = HERE / "independent_plan.json"
N = 16
D3 = C.c_double * 3
D16 = C.c_double * 16
D37 = C.c_double * 37
ID = C.c_ubyte * 32
SIGMA = .001


class Sample(C.Structure):
    _fields_ = [(k, C.c_double) for k in ("dt", "current", "voltage")]


class Model(C.Structure):
    _fields_ = [("modes", C.c_int), ("theta", C.c_double * 7),
                ("tau", D3), ("gamma", C.c_double * 2),
                ("Q", C.c_double), ("z0", C.c_double),
                ("charge_Ah", C.c_double), ("elapsed", C.c_double),
                ("f", D3), ("a", D3), ("df", D3), ("da", D3),
                ("hb", C.c_double), ("ha", C.c_double),
                ("dhb", C.c_double * 2), ("dha", C.c_double * 2)]


class Jet(C.Structure):
    _fields_ = [("model", Model)] + [(k, D3) for k in ("ddf", "dda", "ddhb", "ddha")]


class Bank(C.Structure):
    _fields_ = [("upper", C.c_double * 703), ("jet", Jet),
                ("origin", D16), ("estimate", D16), ("source_id", ID),
                ("next_index", C.c_uint64), ("charge_min_Ah", C.c_double),
                ("charge_max_Ah", C.c_double)]
    _fields_ += [(k, C.c_uint64) for k in
                 ("model_steps", "qr_rows", "query_evaluations", "prior_evaluations",
                  "proposal_rounds", "accepted_steps")]
    _fields_ += [("available", C.c_uint32), ("last_error", C.c_int32)]


class Codes(C.Structure):
    _fields_ = [(k, C.c_uint16) for k in ("voltage", "current", "temperature")]


class Raw(C.Structure):
    _fields_ = [("interval_ticks", C.c_uint64), ("codes", Codes)]


class Affine(C.Structure):
    _fields_ = [("offset", C.c_double), ("units_per_code", C.c_double)]


class Calibration(C.Structure):
    _fields_ = [(k, Affine) for k in ("voltage_V", "current_A", "temperature_C")]
    _fields_ += [("seconds_per_tick", C.c_double)]


class Reading(C.Structure):
    _fields_ = [(k, C.c_double) for k in ("dt_s", "voltage_V", "current_A", "temperature_C")]


class QueryState(C.Structure):
    _fields_ = [(k, D3) for k in ("f", "a", "df", "da")]
    _fields_ += [("hb", C.c_double), ("ha", C.c_double),
                 ("dhb", C.c_double * 2), ("dha", C.c_double * 2),
                 ("charge_Ah", C.c_double), ("inverse_Q", C.c_double),
                 ("tau", D3), ("gamma", C.c_double * 2),
                 ("z", C.c_double), ("slope", C.c_double), ("mu", C.c_double)]


class QueryWorkspace(C.Structure):
    _fields_ = [("packed", C.c_double * 136), ("gradient", D16),
                ("point", D16), ("state", QueryState), ("decoded", Reading)]


class ProposalWorkspace(C.Structure):
    _fields_ = [("packed", C.c_double * 136)] + [(k, D16) for k in
                 ("gradient", "point", "majorizer", "direction")]


class MergeWorkspace(C.Structure):
    _fields_ = [("prospective", Jet), ("row", D37),
                ("decoded", Reading), ("model_sample", Sample)]


class Workspace(C.Union):
    _fields_ = [("query", QueryWorkspace), ("proposal", ProposalWorkspace),
                ("merge", MergeWorkspace)]


class Endpoint(C.Structure):
    _fields_ = [("SOC", C.c_double), ("v", D3), ("h", C.c_double),
                ("min_support_slack", C.c_double), ("min_endpoint_slack", C.c_double)]


class Step(C.Structure):
    _fields_ = [(k, C.c_double) for k in
                ("slope", "slope_allowance", "model_decrease", "model_allowance",
                 "cost_decrease", "cost_allowance", "armijo_required",
                 "combine_allowance", "alpha")]


class Detail(C.Union):
    _fields_ = [("endpoint", Endpoint), ("step", Step)]


class EvidenceResult(C.Structure):
    _fields_ = [(k, C.c_double) for k in
                ("likelihood_cost", "prior_cost", "total_cost", "cost_absolute_scale")]
    _fields_ += [("flags", C.c_uint32), ("stop_reason", C.c_uint32),
                 ("detail", Detail), ("round", C.c_uint32), ("fraction", C.c_uint32)]


class Result(C.Union):
    _fields_ = [("evidence", EvidenceResult), ("raw", C.c_double * 15)]


class Core(C.Structure):
    _fields_ = [("bank", Bank), ("workspace", Workspace), ("result", Result)]


class Inputs(C.Structure):
    _fields_ = [("retained", Raw * 16), ("ingress", Raw * 8),
                ("next_ingress_sequence", C.c_uint64)]
    _fields_ += [(k, C.c_uint32) for k in
                 ("ingress_head", "ingress_count", "block_count", "phase_and_flags")]


class Context(C.Structure):
    _fields_ = [("core", Core), ("inputs", Inputs), ("calibration", Calibration),
                ("auxiliary_reserved", C.c_double * 16)]


class HostObservation(C.Structure):
    _fields_ = [("index", C.c_uint64)] + [(k, C.c_double) for k in
                 ("dt_s", "current_A", "voltage_V")]


class HostError(C.Structure):
    _fields_ = [(k, C.c_double) for k in ("dt_s", "current_A", "voltage_V")]
    _fields_ += [("half_ties", C.c_uint32), ("rails", C.c_uint32)]


def identity(path):
    path = Path(path)
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def clean(value):
    if isinstance(value, float) and not math.isfinite(value):
        return repr(value)
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [clean(v) for v in value]
    return value


def save(path, value):
    data = (json.dumps(clean(value), sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    with Path(path).open("xb") as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())
    fd = os.open(Path(path).parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def clone(value):
    return type(value).from_buffer_copy(bytes(value))


def calibration():
    # Fabricated exact-binary coefficients, not the canonical producer map.
    return Calibration(Affine(1.5, 1. / 1024.), Affine(-.25, 1. / 8192.),
                       Affine(0., 1. / 32.), 1. / 1024.)


def source_id():
    return ID(*((3 * i + 1) % 256 for i in range(32)))


def raw_at(index, kind="normal"):
    ticks = (64, 128, 96, 160, 0, 48, 80, 144, 112, 32, 192, 64, 128, 96, 160, 80)
    currents = (2560, 2816, 2048, 1280, 2304, 1792, 2560, 2048,
                1024, 3072, 1792, 2560, 2304, 1280, 2048, 2816)
    voltages = (2350, 2348, 2355, 2362, 2358, 2353, 2349, 2357,
                2364, 2345, 2360, 2352, 2351, 2363, 2356, 2347)
    i = index % 16
    return Raw(ticks[i], Codes(2600 if kind == "active_h" else voltages[i],
                              2048 if kind in ("zero", "active_h") else currents[i], 800))


def samples(start=0, count=16, kind="normal"):
    cal = calibration()
    return [(raw_at(i, kind).interval_ticks * cal.seconds_per_tick,
             cal.current_A.offset + cal.current_A.units_per_code * raw_at(i, kind).codes.current,
             cal.voltage_V.offset + cal.voltage_V.units_per_code * raw_at(i, kind).codes.voltage)
            for i in range(start, start + count)]


def jet_values(jet):
    result = {k: list(getattr(jet.model, k)) for k in ("f", "a", "df", "da", "dhb", "dha")}
    result.update({k: list(getattr(jet, k)) for k in ("ddf", "dda", "ddhb", "ddha")})
    result.update({k: getattr(jet.model, k) for k in ("hb", "ha", "charge_Ah", "elapsed")})
    return result


def evidence_identity(ctx):
    b = ctx.core.bank
    return {"factor_sha256": hashlib.sha256(bytes(b.upper)).hexdigest(),
            "jet_sha256": hashlib.sha256(bytes(b.jet)).hexdigest(),
            "origin": list(b.origin), "next_index": b.next_index, "qr_rows": b.qr_rows,
            "source_id": bytes(b.source_id).hex(),
            "charge_min_Ah": b.charge_min_Ah, "charge_max_Ah": b.charge_max_Ah,
            "inputs_sha256": hashlib.sha256(bytes(ctx.inputs)).hexdigest()}


def result_values(ctx):
    r = ctx.core.result.evidence
    return {"likelihood_cost": r.likelihood_cost, "prior_cost": r.prior_cost,
            "total_cost": r.total_cost, "flags": r.flags,
            "gradient": list(ctx.core.workspace.query.gradient),
            "GN": list(ctx.core.workspace.query.packed),
            "point": list(ctx.core.workspace.query.point),
            "endpoint": {"SOC": r.detail.endpoint.SOC, "v": list(r.detail.endpoint.v),
                         "h": r.detail.endpoint.h}}


def bind(lib):
    P = C.POINTER
    signatures = {
        "re_init": ([P(Context), P(C.c_ubyte), P(Calibration)], C.c_int),
        "re_offer": ([P(Context), P(C.c_ubyte), C.c_uint64, P(Raw)], C.c_int),
        "re_admit": ([P(Context)], C.c_int),
        "re_invalidate": ([P(Context), C.c_int], C.c_int),
        "re_commit": ([P(Context)], C.c_int),
        "re_refine": ([P(Context), C.c_uint], C.c_int),
        "re_process": ([P(Context), C.c_uint], C.c_int),
        "iq_query": ([P(Context), C.c_int, C.c_int], C.c_int),
        "iq_size": ([C.c_uint], C.c_size_t), "iq_offset": ([C.c_uint], C.c_size_t),
        "iq_activity": ([C.c_uint], C.c_uint64),
        "iq_read_query": ([C.c_uint, P(C.c_double), P(C.c_double), P(C.c_uint64), P(C.c_int)], C.c_int),
        "rm_init_jet": ([P(Jet), P(C.c_double)], C.c_int),
        "rm_transport": ([P(Jet), P(C.c_double), P(C.c_double), P(Jet)], C.c_int),
        "rm_query_init": ([P(QueryState), P(Jet), P(C.c_double), P(C.c_double)], C.c_int),
        "iq_query_step": ([P(QueryState), P(C.c_double), P(Reading)], C.c_int),
        "rm_query_derivative": ([P(QueryState), P(C.c_double), P(Reading), C.c_uint], C.c_double),
        "iq_merge_step": ([P(Jet), P(C.c_double), P(Sample), C.c_double, P(C.c_double)], C.c_int),
        "hp_decode_record": ([P(C.c_ubyte), P(HostObservation)], C.c_int),
        "hp_encode": ([C.c_uint64, P(HostObservation), P(Raw), P(HostError)], C.c_int),
    }
    for name, (args, returns) in signatures.items():
        fn = getattr(lib, name); fn.argtypes = args; fn.restype = returns


class Qualification:
    def __init__(self, lib, oracle, plan):
        self.lib, self.oracle, self.plan = lib, oracle, plan
        self.cases, self.current = [], None
        self.refinements = 0
        self.host_calls = 0

    @contextmanager
    def case(self, name):
        self.current = {"name": name, "status": "running", "checks": [], "observations": {}}
        self.cases.append(self.current)
        try:
            yield
        except Exception:
            self.current["status"] = "failed"
            raise
        else:
            self.current["status"] = "passed"

    def check(self, name, condition, **detail):
        item = {"check": name, "passed": bool(condition), **detail}
        self.current["checks"].append(item)
        if not condition:
            raise AssertionError(self.current["name"] + ": " + name)

    def close(self, name, actual, expected, absolute, relative=0.):
        bound = absolute + relative * max(abs(actual), abs(expected))
        self.check(name, math.isfinite(actual) and math.isfinite(expected)
                   and abs(actual - expected) <= bound,
                   actual=actual, expected=expected, allowance=bound)

    def new_context(self, kind=None):
        ctx, sid, cal = Context(), source_id(), calibration()
        self.check("public_init", self.lib.re_init(C.byref(ctx), sid, C.byref(cal)) == 0)
        if kind is not None:
            self.fill(ctx, 0, 16, kind)
        return ctx

    def fill(self, ctx, start, count, kind="normal"):
        sid = source_id()
        for index in range(start, start + count):
            raw = raw_at(index, kind)
            self.check("offer_%d" % index, self.lib.re_offer(C.byref(ctx), sid, index, C.byref(raw)) == 0)
            self.check("admit_%d" % index, self.lib.re_admit(C.byref(ctx)) == 0)
        self.check("chronology_invariant", ctx.core.bank.next_index + ctx.inputs.block_count
                   + ctx.inputs.ingress_count == ctx.inputs.next_ingress_sequence)

    def query(self, ctx, point, derivatives=1, prior=0):
        ctx.core.workspace.query.point[:] = point
        self.check("query_success", self.lib.iq_query(C.byref(ctx), derivatives, prior) == 0)
        return result_values(ctx)

    def compare_joint(self, got, cost, gram, prefix, extra_cost=0., extra_gradient=None,
                      extra_gram=None):
        sd = self.oracle.PUBLIC_SD
        self.close(prefix + "_cost", got["likelihood_cost"], cost.v + extra_cost,
                   2e-8, 2e-11)
        for i in range(16):
            expected = cost.g[i] + (0. if extra_gradient is None else extra_gradient[i])
            self.close(prefix + "_gradient_%d" % i, got["gradient"][i] * sd[i],
                       expected * sd[i], 2e-7, 2e-10)
            for j in range(i + 1):
                expected = gram[i * 16 + j] + (0. if extra_gram is None else extra_gram[i * 16 + j])
                self.close(prefix + "_GN_%d_%d" % (i, j), got["GN"][i * (i + 1) // 2 + j] * sd[i] * sd[j],
                           expected * sd[i] * sd[j], 2e-7, 2e-10)

    def kernel_rows(self, boundary, origin, point, stream):
        state, x, old = QueryState(), D16(*point), D16(*origin)
        self.check("kernel_query_init", self.lib.rm_query_init(C.byref(state), C.byref(boundary), old, x) == 0)
        rows = []
        for k, (dt, current, voltage) in enumerate(stream):
            reading = Reading(dt, voltage, current, 25.)
            self.check("kernel_query_step_%d" % k, self.lib.iq_query_step(C.byref(state), x, C.byref(reading)) == 0)
            rows.append({"voltage": state.mu, "SOC": state.z,
                         "J": [self.lib.rm_query_derivative(C.byref(state), x, C.byref(reading), i) for i in range(16)]})
        return rows

    def compare_rows(self, rows, expected, name):
        for k, (got, reference) in enumerate(zip(rows, expected["rows"])):
            self.close(name + "_voltage_%d" % k, got["voltage"], reference["voltage"].v, 3e-12)
            self.close(name + "_SOC_%d" % k, got["SOC"], reference["SOC"].v, 3e-14)
            for i in range(16):
                self.close(name + "_J_%d_%d" % (k, i), got["J"][i] * self.oracle.PUBLIC_SD[i],
                           reference["voltage"].g[i] * self.oracle.PUBLIC_SD[i], 3e-11, 3e-11)

    def finite_differences(self, point, stream, rows, boundary=None, origin=None):
        # A fixed five-point derivative rule in public-SD units. Its numerical
        # allowance is a fabricated smooth-fixture check, never a noise gate.
        h = 2. ** -12
        for i in range(16):
            values = []
            for multiplier in (-2., -1., 1., 2.):
                x = list(point); x[i] += multiplier * h * self.oracle.PUBLIC_SD[i]
                values.append(self.oracle.block_scalar(x, stream, SIGMA, origin, boundary)["voltage"])
            for k, row in enumerate(rows):
                derivative = (values[0][k] - 8. * values[1][k]
                              + 8. * values[2][k] - values[3][k]) / (12. * h)
                self.close("five_point_J_%d_%d" % (k, i), derivative,
                           row["J"][i] * self.oracle.PUBLIC_SD[i], 3e-8)

    def trace(self, start):
        output = []
        for index in range(start, self.lib.iq_activity(3)):
            point, costs, counts, labels = D16(), D3(), (C.c_uint64 * 2)(), (C.c_int * 3)()
            self.check("query_record_%d" % index, self.lib.iq_read_query(index, point, costs, counts, labels) == 0)
            output.append({"point": list(point), "total_cost": costs[0], "likelihood_cost": costs[1],
                           "prior_cost": costs[2], "cursor": counts[0], "rows": counts[1],
                           "status": labels[0], "derivatives": labels[1], "include_prior": labels[2]})
        return output

    def run(self):
        mean, sd = list(self.oracle.PUBLIC_MEAN), self.oracle.PUBLIC_SD
        stream = samples()
        with self.case("initial_public_prior_once"):
            empty = self.new_context()
            self.check("public_origin", list(empty.core.bank.origin) == mean)
            self.check("public_estimate", list(empty.core.bank.estimate) == mean)
            self.check("empty_evidence", empty.core.bank.next_index == 0
                       and empty.core.bank.qr_rows == 0 and not any(empty.core.bank.upper))
            before = evidence_identity(empty)
            without = self.query(empty, mean, 1, 0)
            self.check("empty_likelihood_zero", without["likelihood_cost"] == 0.
                       and not any(without["gradient"]) and not any(without["GN"]))
            prior, precision = self.oracle.public_prior_ad(mean)
            pcount = empty.core.bank.prior_evaluations
            with_prior = self.query(empty, mean, 1, 1)
            self.check("one_prior_evaluation", empty.core.bank.prior_evaluations == pcount + 1)
            self.close("common_prior_cost", with_prior["total_cost"], prior.v, 3e-12)
            for i in range(16):
                self.close("prior_gradient_%d" % i, with_prior["gradient"][i] * sd[i],
                           prior.g[i] * sd[i], 3e-11)
                for j in range(i + 1):
                    self.close("kernel_majorizer_%d_%d" % (i, j),
                               with_prior["GN"][i * (i + 1) // 2 + j],
                               precision[i] if i == j else 0., 3e-12, 3e-13)
            self.check("query_did_not_own_evidence", evidence_identity(empty) == before)
            self.current["observations"] = {"prior_cost": prior.v, "point": mean}

        with self.case("public_block_full_joint_AD"):
            public = self.new_context("normal")
            self.check("raw_not_assimilated", public.inputs.block_count == 16
                       and public.core.bank.next_index == public.core.bank.qr_rows == 0)
            public_result = self.query(public, mean, 1, 0)
            public_ad = self.oracle.block_ad(mean, stream, SIGMA)
            self.compare_joint(public_result, public_ad["cost"], public_ad["GN"], "public")
            public_rows = self.kernel_rows(public.core.bank.jet, mean, mean, stream)
            self.compare_rows(public_rows, public_ad, "public")
            prior_count = public.core.bank.prior_evaluations
            combined = self.query(public, mean, 1, 1)
            self.check("prior_once_after_block", public.core.bank.prior_evaluations == prior_count + 1)
            self.close("prior_cost_added_once", combined["total_cost"] - public_result["total_cost"], prior.v, 3e-8)
            for i in range(16):
                self.close("joint_prior_gradient_once_%d" % i,
                           (combined["gradient"][i] - public_result["gradient"][i]) * sd[i],
                           prior.g[i] * sd[i], 3e-8)
            self.current["observations"] = {"likelihood": public_result, "kernel_rows": public_rows}

        with self.case("public_all16_five_point_derivatives"):
            self.finite_differences(mean, stream, public_rows)

        with self.case("transported_boundary_and_full_joint_block"):
            transported = clone(public)
            self.check("prefix_commit", self.lib.re_commit(C.byref(transported)) == 0)
            boundary = clone(transported.core.bank.jet)
            boundary_dict = jet_values(boundary)
            old_factor = list(transported.core.bank.upper)
            shifts = (.05, -.04, .03, .05, -.035, .025, .01, -.01,
                      .012, -.008, .025, -.02, .005, -.004, .003, -.05)
            point = [mean[i] + shifts[i] * sd[i] for i in range(16)]
            moved = Jet()
            self.check("transport", self.lib.rm_transport(C.byref(boundary), D16(*mean),
                       D16(*point), C.byref(moved)) == 0)
            bf, ba, bhb, bha = self.oracle.translated_boundary_ad(point, mean, boundary_dict)
            for i in range(3):
                for name, reference in (("f", bf[i]), ("a", ba[i])):
                    self.close("transport_%s_%d" % (name, i), getattr(moved.model, name)[i], reference.v, 3e-14)
                    self.close("transport_d%s_%d" % (name, i), getattr(moved.model, "d" + name)[i], reference.g[i], 3e-14)
                    self.close("transport_dd%s_%d" % (name, i), getattr(moved, "dd" + name)[i], reference.h[i * 16 + i], 3e-14)
            for name, reference in (("hb", bhb), ("ha", bha)):
                self.close("transport_" + name, getattr(moved.model, name), reference.v, 3e-14)
                for i in range(2):
                    self.close("transport_d%s_%d" % (name, i), getattr(moved.model, "d" + name)[i], reference.g[3 + i], 3e-14)
                for k, (i, j) in enumerate(((3, 3), (3, 4), (4, 4))):
                    self.close("transport_dd%s_%d" % (name, k), getattr(moved, "dd" + name)[k], reference.h[i * 16 + j], 3e-14)
            self.check("transport_charge_time_unchanged", moved.model.charge_Ah == boundary.model.charge_Ah
                       and moved.model.elapsed == boundary.model.elapsed)
            self.fill(transported, 16, 16)
            suffix = samples(16)
            transported_result = self.query(transported, point, 1, 0)
            transported_ad = self.oracle.block_ad(point, suffix, SIGMA, mean, boundary_dict)
            old_cost, old_gn = self.oracle.factor_ad(point, mean, old_factor)
            self.compare_joint(transported_result, transported_ad["cost"], transported_ad["GN"],
                               "transported", old_cost.v, old_cost.g, old_gn)
            transported_rows = self.kernel_rows(boundary, mean, point, suffix)
            self.compare_rows(transported_rows, transported_ad, "transported")
            model_point = D16(*point)
            jet = clone(moved)
            merge_rows = []
            for k, ((dt, current, observed), expected) in enumerate(zip(suffix, transported_ad["rows"])):
                row = D37(); sample = Sample(dt, current, observed)
                self.check("transported_merge_step_%d" % k,
                           self.lib.iq_merge_step(C.byref(jet), model_point, C.byref(sample), SIGMA, row) == 0)
                expected_row = self.oracle.expected_merge_row(expected["voltage"], observed, SIGMA)
                for i in range(37):
                    self.close("signed_row_%d_%d" % (k, i), row[i], expected_row[i], 3e-9, 3e-10)
                pairs = {tuple(sorted(pair)) for pair in self.oracle.PAIRS}
                for i in range(16):
                    for j in range(i + 1):
                        if tuple(sorted((i, j))) not in pairs:
                            self.close("unlisted_Hessian_%d_%d_%d" % (k, i, j),
                                       expected["voltage"].h[i * 16 + j] * sd[i] * sd[j], 0., 3e-12)
                merge_rows.append(list(row))
            self.current["observations"] = {"point": point, "old_origin": mean,
                "boundary": boundary_dict, "transported_boundary": jet_values(moved),
                "joint_result": transported_result, "kernel_rows": transported_rows,
                "signed_merge_rows": merge_rows}

        with self.case("transported_all16_five_point_derivatives"):
            self.finite_differences(point, suffix, transported_rows, boundary_dict, mean)

        with self.case("zero_current_capacity_likelihood_flat"):
            zero = self.new_context("zero")
            zero_ad = self.oracle.block_ad(mean, samples(kind="zero"), SIGMA)
            outputs = []
            for direction in (-.2, 0., .2):
                x = list(mean); x[5] += direction * sd[5]
                outputs.append(self.query(zero, x, 1, 0))
            self.check("exact_Q_flat_likelihood", all(o["likelihood_cost"] == outputs[0]["likelihood_cost"] for o in outputs))
            for k, output in enumerate(outputs):
                self.check("zero_Q_gradient_%d" % k, output["gradient"][5] == 0.)
                self.check("zero_Q_GN_row_%d" % k, all(output["GN"][max(i, 5) * (max(i, 5) + 1) // 2 + min(i, 5)] == 0. for i in range(16)))
            self.check("independent_zero_Q", zero_ad["cost"].g[5] == 0.
                       and all(zero_ad["GN"][5 * 16 + i] == 0. for i in range(16)))
            self.current["observations"] = {"logQ_values": [o["point"][5] for o in outputs],
                                            "likelihood_cost": outputs[0]["likelihood_cost"]}

        with self.case("local_quadratic_first_merge_equivalence"):
            merged = clone(public)
            before = self.query(merged, mean, 1, 0)
            prior_count = merged.core.bank.prior_evaluations
            self.check("commit", self.lib.re_commit(C.byref(merged)) == 0)
            after = self.query(merged, mean, 1, 0)
            self.check("exact_record_ownership", merged.core.bank.next_index == merged.core.bank.qr_rows == 16
                       and merged.inputs.block_count == 0 and merged.inputs.next_ingress_sequence == 16)
            self.check("merge_does_not_add_prior", merged.core.bank.prior_evaluations == prior_count)
            self.close("merge_cost", after["likelihood_cost"], before["likelihood_cost"], 3e-8, 3e-11)
            for i in range(16):
                self.close("merge_gradient_%d" % i, after["gradient"][i] * sd[i], before["gradient"][i] * sd[i], 3e-7, 3e-10)
                for j in range(i + 1):
                    k = i * (i + 1) // 2 + j
                    self.close("merge_GN_%d_%d" % (i, j), after["GN"][k] * sd[i] * sd[j], before["GN"][k] * sd[i] * sd[j], 3e-7, 3e-10)
            self.current["observations"] = {"before": before, "after": after, "cursor": 16, "rows": 16}

        with self.case("two_block_single_count_transition"):
            second = clone(merged)
            self.fill(second, 16, 16)
            second.core.bank.estimate[:] = point  # Explicit host-only fabricated accepted point.
            before = self.query(second, point, 1, 0)
            prior_count = second.core.bank.prior_evaluations
            self.check("second_commit", self.lib.re_commit(C.byref(second)) == 0)
            after = self.query(second, point, 1, 0)
            self.check("two_block_ownership", second.core.bank.next_index == second.core.bank.qr_rows == 32
                       and second.inputs.block_count == 0 and second.inputs.next_ingress_sequence == 32)
            self.check("origin_moves_only_to_chosen_point", list(second.core.bank.origin) == point)
            self.check("history_and_boundary_unverified_flags", second.inputs.phase_and_flags & 256
                       and second.inputs.phase_and_flags & 512)
            self.check("second_merge_no_prior", second.core.bank.prior_evaluations == prior_count)
            self.close("transition_cost", after["likelihood_cost"], before["likelihood_cost"], 3e-8, 3e-11)
            for i in range(16):
                self.close("transition_gradient_%d" % i, after["gradient"][i] * sd[i], before["gradient"][i] * sd[i], 3e-7, 3e-10)
                for j in range(i + 1):
                    k = i * (i + 1) // 2 + j
                    self.close("transition_GN_%d_%d" % (i, j), after["GN"][k] * sd[i] * sd[j], before["GN"][k] * sd[i] * sd[j], 3e-7, 3e-10)
            self.current["observations"] = {"before": before, "after": after, "cursor": 32, "rows": 32}

        with self.case("query_refinement_preserves_committed_evidence"):
            refined = clone(public)
            before_evidence = evidence_identity(refined)
            before_point = list(refined.core.bank.estimate)
            before_prior = refined.core.bank.prior_evaluations
            before_accept = refined.core.bank.accepted_steps
            start = self.lib.iq_activity(3)
            self.refinements += 1
            status = self.lib.re_refine(C.byref(refined), 1)
            self.check("finite_refinement_status", status in (0, 1))
            self.check("committed_evidence_unchanged", evidence_identity(refined) == before_evidence)
            trace = self.trace(start)
            valid_costs = [z for z in trace if z["status"] == 0 and z["derivatives"] == 0]
            if refined.core.bank.accepted_steps > before_accept:
                self.check("accepted_point_was_evaluated", any(list(refined.core.bank.estimate) == z["point"] for z in valid_costs))
                self.check("accepted_objective_decreased", any(list(refined.core.bank.estimate) == z["point"]
                           and z["total_cost"] < trace[0]["total_cost"] for z in valid_costs))
            else:
                self.check("no_unevaluated_installation", list(refined.core.bank.estimate) == before_point)
            self.check("one_prior_per_successful_query", refined.core.bank.prior_evaluations - before_prior
                       == sum(z["status"] == 0 and z["include_prior"] == 1 for z in trace))
            self.current["observations"] = {"status": status, "accepted_steps": refined.core.bank.accepted_steps - before_accept,
                "before_point": before_point, "after_point": list(refined.core.bank.estimate), "queries": trace}

        with self.case("cost_only_proposal_endpoint_preservation"):
            cost_only = clone(public)
            for i in range(136):
                cost_only.core.workspace.query.packed[i] = .5 + i / 1024.
            cost_only.core.workspace.query.packed[:16] = point
            cost_only.core.workspace.query.gradient[:] = [-.25 - i / 512. for i in range(16)]
            packed_before = bytes(cost_only.core.workspace.query.packed)
            gradient_before = bytes(cost_only.core.workspace.query.gradient)
            evidence_before = evidence_identity(cost_only)
            self.query(cost_only, point, 0, 1)
            self.check("entire_packed_preserved", bytes(cost_only.core.workspace.query.packed) == packed_before)
            self.check("entire_gradient_preserved", bytes(cost_only.core.workspace.query.gradient) == gradient_before)
            self.check("endpoint_preserved", list(cost_only.core.workspace.query.packed[:16]) == point)
            self.check("cost_query_ownership_unchanged", evidence_identity(cost_only) == evidence_before)
            cost_only.core.workspace.query.point[15] = 2.
            self.check("invalid_trial_rejected", self.lib.iq_query(C.byref(cost_only), 0, 1) < 0)
            self.check("rejected_trial_preserves_packed", bytes(cost_only.core.workspace.query.packed) == packed_before)
            self.check("rejected_trial_preserves_gradient", bytes(cost_only.core.workspace.query.gradient) == gradient_before)
            self.check("rejected_trial_ownership_unchanged", evidence_identity(cost_only) == evidence_before)

        with self.case("active_h_supported_refinement"):
            active = self.new_context("active_h")
            active.core.bank.estimate[15] = -1.  # Explicit host-only boundary fixture.
            before_evidence = evidence_identity(active)
            start = self.lib.iq_activity(3)
            self.refinements += 1
            status = self.lib.re_refine(C.byref(active), 1)
            self.check("active_bound_finite_status", status in (0, 1))
            self.check("active_bound_has_accepted_descent", active.core.bank.accepted_steps == 1)
            self.check("h_bound_not_relaxed", active.core.bank.estimate[15] == -1.)
            self.check("other_coordinate_moves", any(active.core.bank.estimate[i] != mean[i] for i in range(15)))
            self.check("active_refine_ownership_unchanged", evidence_identity(active) == before_evidence)
            trace = self.trace(start)
            self.check("active_point_was_evaluated", any(z["status"] == 0 and z["derivatives"] == 0
                       and z["point"] == list(active.core.bank.estimate) for z in trace))
            self.current["observations"] = {"status": status, "point": list(active.core.bank.estimate), "queries": trace}

        with self.case("source_order_atomicity"):
            guarded = self.new_context()
            sid, wrong, raw = source_id(), source_id(), raw_at(0)
            wrong[31] ^= 1
            for label, supplied, index in (("source", wrong, 0), ("skipped", sid, 1)):
                before = bytes(guarded)
                self.check(label + "_rejected", self.lib.re_offer(C.byref(guarded), supplied, index, C.byref(raw)) < 0)
                self.check(label + "_atomic", bytes(guarded) == before)
            self.check("one_offer", self.lib.re_offer(C.byref(guarded), sid, 0, C.byref(raw)) == 0)
            before = bytes(guarded)
            self.check("duplicate_rejected", self.lib.re_offer(C.byref(guarded), sid, 0, C.byref(raw)) < 0)
            self.check("duplicate_atomic", bytes(guarded) == before)
            alias_id = C.cast(C.byref(guarded, Core.bank.offset + Bank.source_id.offset), C.POINTER(C.c_ubyte))
            self.check("source_alias_rejected", self.lib.re_offer(C.byref(guarded), alias_id, 1, C.byref(raw)) < 0)
            self.check("alias_atomic", bytes(guarded) == before)

        with self.case("ingress_wrap_full_and_counter_exhaustion"):
            queued = self.new_context(); sid = source_id()
            for block in range(3):
                for index in range(block * 8, block * 8 + 8):
                    raw = raw_at(index)
                    self.check("queue_offer_%d" % index, self.lib.re_offer(C.byref(queued), sid, index, C.byref(raw)) == 0)
                if block < 2:
                    self.check("queue_admit_%d" % block, self.lib.re_admit(C.byref(queued)) == 0)
            before = bytes(queued); raw = raw_at(24)
            self.check("ingress_full_rejected", self.lib.re_offer(C.byref(queued), sid, 24, C.byref(raw)) < 0)
            self.check("ingress_full_atomic", bytes(queued) == before)
            self.check("blocked_admit_no_loss", self.lib.re_admit(C.byref(queued)) == 0 and bytes(queued) == before)
            self.check("retained_prefix_exact", all(bytes(queued.inputs.retained[i]) == bytes(raw_at(i)) for i in range(16)))
            self.check("commit_prefix_with_ingress", self.lib.re_commit(C.byref(queued)) == 0)
            self.check("admit_suffix", self.lib.re_admit(C.byref(queued)) == 0)
            self.check("suffix_owned_once", queued.core.bank.next_index == queued.core.bank.qr_rows == 16
                       and queued.inputs.block_count == 8 and queued.inputs.ingress_count == 0
                       and queued.inputs.next_ingress_sequence == 24)
            self.check("suffix_order_exact", all(bytes(queued.inputs.retained[i]) == bytes(raw_at(16 + i)) for i in range(8)))
            exhausted = self.new_context(); exhausted.core.bank.next_index = (1 << 64) - 1
            exhausted.inputs.next_ingress_sequence = (1 << 64) - 1
            before = bytes(exhausted)
            self.check("cursor_exhaustion_rejected", self.lib.re_offer(C.byref(exhausted), sid, (1 << 64) - 1, C.byref(raw)) < 0)
            self.check("cursor_never_wraps", bytes(exhausted) == before)

        with self.case("invalid_inputs_transport_and_host_producer"):
            invalid = Context(); C.memset(C.byref(invalid), 0x35, C.sizeof(invalid))
            bad_cal = calibration(); bad_cal.seconds_per_tick = 0.; sid = source_id()
            before = bytes(invalid)
            self.check("invalid_init_rejected", self.lib.re_init(C.byref(invalid), sid, C.byref(bad_cal)) < 0)
            self.check("invalid_init_atomic", bytes(invalid) == before)
            valid = self.new_context()
            for label, raw in (("code", Raw(1, Codes(4096, 2048, 800))),
                               ("duration", Raw(2048, Codes(2350, 2048, 800)))):
                before = bytes(valid)
                self.check(label + "_domain_rejected", self.lib.re_offer(C.byref(valid), sid, 0, C.byref(raw)) < 0)
                self.check(label + "_domain_atomic", bytes(valid) == before)
            bad_point = list(mean); bad_point[15] = 2.; out_jet = Jet()
            before, original = bytes(out_jet), bytes(valid.core.bank.jet)
            self.check("invalid_transport_rejected", self.lib.rm_transport(C.byref(valid.core.bank.jet), D16(*mean), D16(*bad_point), C.byref(out_jet)) < 0)
            self.check("transport_prevalidation_atomic", bytes(out_jet) == before and bytes(valid.core.bank.jet) == original)
            self.host_fixtures()

        with self.case("internal_QR_fault_latches_unavailable"):
            fault = self.new_context(); self.fill(fault, 0, 1)
            # Host-only finite hostile factor: at its origin all quadratic
            # features vanish, while the first QR rotation propagates a huge
            # off-diagonal into the next huge diagonal and overflows.
            fault.core.bank.upper[1] = sys.float_info.max
            fault.core.bank.upper[37] = sys.float_info.max
            before_factor = bytes(fault.core.bank.upper)
            raw_before = bytes(fault.inputs.retained)
            status = self.lib.re_commit(C.byref(fault))
            self.check("real_internal_failure", status < 0)
            self.check("unavailability_latched", fault.core.bank.available == 0
                       and fault.inputs.phase_and_flags & 15 == 3)
            self.check("no_false_rollback", bytes(fault.core.bank.upper) != before_factor)
            self.check("no_partial_ownership_published", fault.core.bank.next_index == fault.core.bank.qr_rows == 0
                       and fault.inputs.block_count == 1 and bytes(fault.inputs.retained) == raw_before)
            before = bytes(fault)
            self.check("unavailable_query_rejected", self.lib.iq_query(C.byref(fault), 0, 0) < 0)
            self.check("unavailable_commit_rejected", self.lib.re_commit(C.byref(fault)) < 0)
            self.check("unavailable_offer_rejected", self.lib.re_offer(C.byref(fault), source_id(), 1, C.byref(raw_at(1))) < 0)
            self.check("unavailable_state_stable", bytes(fault) == before)
            self.current["observations"] = {"status": status, "last_error": fault.core.bank.last_error,
                "available": fault.core.bank.available, "phase_flags": fault.inputs.phase_and_flags}

        with self.case("phase_layout_no_heap_and_own_stack"):
            types = (Model, Jet, Bank, QueryState, Workspace, Result, Core, Inputs,
                     Calibration, Context, Raw, Reading, EvidenceResult, ProposalWorkspace)
            expected = (280, 376, 6368, 224, 1600, 120, 8088, 408, 56, 8680, 16, 32, 120, 1600)
            for k, (kind, count) in enumerate(zip(types, expected)):
                self.check("layout_%s" % kind.__name__, C.sizeof(kind) == self.lib.iq_size(k) == count)
            self.check("input_result_sample_layout", self.lib.iq_size(14) == 48
                       and self.lib.iq_size(15) == 120 and self.lib.iq_size(16) == 24)
            offsets = (Context.core.offset, Context.inputs.offset, Context.calibration.offset,
                       Context.auxiliary_reserved.offset, Core.bank.offset, Core.workspace.offset,
                       Core.result.offset, QueryWorkspace.packed.offset, QueryWorkspace.gradient.offset,
                       QueryWorkspace.point.offset, QueryWorkspace.state.offset, QueryWorkspace.decoded.offset)
            for k, expected_offset in enumerate(offsets):
                self.check("offset_%d" % k, self.lib.iq_offset(k) == expected_offset)
            self.check("no_wrapper_budget_rejection", self.lib.iq_activity(2) == 0)
            self.check("model_step_budget", self.lib.iq_activity(0) + self.lib.iq_activity(1) <= 4096)
            self.check("merge_budget", self.lib.iq_activity(1) <= 256)
            self.check("query_budget", self.lib.iq_activity(3) <= 128)
            self.check("refinement_budget", self.refinements == 2)
            self.check("host_producer_budget", self.host_calls == 8)
            self.check("independent_trajectory_budgets", self.oracle.ACTIVITY["scalar_trajectories"] == 128
                       and self.oracle.ACTIVITY["AD_trajectories"] <= 8)
            self.current["observations"] = {"sizeof": dict(zip((x.__name__ for x in types), expected)),
                "planned_total": C.sizeof(Context) + 768 + 768,
                "candidate_single_bank": True, "reference_arrays_host_only": True}

    def host_fixtures(self):
        blob = (C.c_ubyte * 32).from_buffer_copy(struct.pack("<Qddd", 7, .125, -.0625, 3.75))
        observation = HostObservation()
        self.host_calls += 1
        self.check("host_decode", self.lib.hp_decode_record(blob, C.byref(observation)) == 0)
        self.check("host_decode_exact", (observation.index, observation.dt_s, observation.current_A, observation.voltage_V)
                   == (7, .125, -.0625, 3.75))
        high = 1.5 + 4095. / 1024.
        cases = [("low", HostObservation(2, 0., 0., 1.5), 2, True),
                 ("high", HostObservation(2, 1., 0., high), 2, True),
                 ("tie_and_time", HostObservation(2, 1. / 128., 0., 1.5 + 1000.5 / 1024.), 2, True),
                 ("below_span", HostObservation(2, .125, 0., 1.5 - 2. ** -20), 2, False),
                 ("above_span", HostObservation(2, .125, 0., high + 2. ** -20), 2, False),
                 ("nonfinite", HostObservation(2, .125, float("nan"), 3.75), 2, False),
                 ("order", HostObservation(3, .125, 0., 3.75), 2, False)]
        for label, observation, index, success in cases:
            raw, error = Raw(), HostError()
            C.memset(C.byref(raw), 0x25, C.sizeof(raw)); C.memset(C.byref(error), 0x35, C.sizeof(error))
            before_raw, before_error = bytes(raw), bytes(error)
            self.host_calls += 1
            status = self.lib.hp_encode(index, C.byref(observation), C.byref(raw), C.byref(error))
            self.check("host_" + label + "_status", (status == 0) == success)
            if success:
                self.check("host_" + label + "_temperature", raw.codes.temperature == 1040)
                self.check("host_" + label + "_time_error", abs(error.dt_s) <= .5 / 7000000. + 8. * sys.float_info.epsilon)
                if label == "low":
                    self.check("low_rail_preserved", raw.codes.voltage == 0 and raw.interval_ticks == 0 and error.rails & 1)
                elif label == "high":
                    self.check("high_rail_preserved", raw.codes.voltage == 4095 and raw.interval_ticks == 7000000 and error.rails & 16)
                else:
                    self.check("half_voltage_tie_up", raw.codes.voltage == 1001 and error.half_ties & 1)
                    self.check("actual_time_quantized", raw.interval_ticks in (54687, 54688))
            else:
                self.check("host_" + label + "_atomic", bytes(raw) == before_raw and bytes(error) == before_error)


def project_stack(source_paths, stack_paths):
    """Conservative source call paths using no-inline emitted host frames.

    Each static helper resolves within its own translation unit. External
    library calls and the qualification wrappers are deliberately separate
    from the candidate project frame bound.
    """
    definitions, public, frames, external = {}, {}, {}, set()
    for path in source_paths:
        if path.name == "independent_bridge.c":
            continue
        text = path.read_text()
        text = re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"', ' ', text, flags=re.S)
        pattern = re.compile(r'(?m)^(static\s+)?(?:unsigned\s+)?(?:int|double|void|size_t|uint64_t|uint32_t)\s+'
                             r'([A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{')
        for match in pattern.finditer(text):
            level, position = 1, match.end()
            while level and position < len(text):
                level += (text[position] == '{') - (text[position] == '}')
                position += 1
            name = match.group(2)
            key = path.name + ':' + name
            calls = set(re.findall(r'\b([A-Za-z_]\w*)\s*\(', text[match.end():position - 1]))
            definitions[key] = {"file": path.name, "name": name, "calls": calls}
            if not match.group(1):
                public[name] = key
    raw_frames = []
    for path in stack_paths:
        for line in path.read_text().splitlines():
            fields = line.split('\t')
            if len(fields) != 3:
                raise ValueError("Unexpected stack record: " + line)
            location, amount, kind = fields
            parts = location.rsplit(':', 3)
            filename, function = Path(parts[0]).name, parts[-1].split('.')[0]
            if filename == 'rolling_engine.c' and function == 'iq_real_engine_query':
                function = 're_query'
            key = filename + ':' + function
            frames[key] = max(frames.get(key, 0), int(amount))
            raw_frames.append({"source": filename, "function": function, "bytes": int(amount), "kind": kind})
            if kind != 'static':
                raise ValueError("Dynamic/unbounded own frame: " + line)
    graph = {}
    ignored = {'if', 'for', 'while', 'switch', 'sizeof', 'return', 'isfinite', 'isnan'}
    for key, definition in definitions.items():
        children = []
        for call in definition['calls'] - ignored:
            local = definition['file'] + ':' + call
            target = local if local in definitions else public.get(call)
            if target:
                children.append(target)
            else:
                external.add(call)
        graph[key] = sorted(children)
    memo = {}
    def path_to(key, ancestors=()):
        if key in ancestors:
            raise ValueError("Recursive project call path: " + str(ancestors + (key,)))
        if key not in frames:
            raise ValueError("Missing emitted frame for reachable project function: " + key)
        if key in memo:
            return memo[key]
        tails = [path_to(child, ancestors + (key,)) for child in graph.get(key, [])]
        amount, nodes = max(tails, default=(0, []), key=lambda value: value[0])
        memo[key] = (frames[key] + amount, [key] + nodes)
        return memo[key]
    roots = {name: path_to(public[name]) for name in
             ('re_init', 're_offer', 're_admit', 're_query', 're_refine', 're_commit', 're_process')}
    maximum = max(value[0] for value in roots.values())
    return {"maximum_project_path_bytes": maximum,
            "paths": {name: {"bytes": value[0], "functions": value[1]} for name, value in roots.items()},
            "emitted_frames": raw_frames, "source_call_graph": graph,
            "external_calls_not_in_project_frame_sum": sorted(external),
            "scope": "No-inline/no-sibling-call host frames summed conservatively along project source paths. Qualification wrappers and Python reference memory are outside candidate storage. Libm/libc, hardware ISR/runtime and caller frames remain in the separate unmeasured reserve; no target measurement."}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output-dir', required=True)
    args = ap.parse_args()
    plan = json.loads(PLAN.read_text())
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=False, exist_ok=False)
    started = time.monotonic()
    own_before = resource.getrusage(resource.RUSAGE_SELF)
    compiler = Path(shutil.which('cc')).resolve()
    python = Path(sys.executable).resolve()
    source_bindings = {name: identity(ROOT / name) for name in plan['source_sha256']}
    if any(value['sha256'] != plan['source_sha256'][name] for name, value in source_bindings.items()):
        raise ValueError('Frozen source mismatch before any compilation')
    plan_identity = identity(PLAN)
    compiler_identity, python_identity = identity(compiler), identity(python)
    save(output / 'source_freeze.json', {'schema': 'rolling_independent_source_freeze_v1',
         'plan': plan_identity, 'sources': source_bindings,
         'compiler': {'path': str(compiler), **compiler_identity},
         'python': {'path': str(python), 'version': sys.version, **python_identity},
         'scientific_invocations_before_freeze': 0})
    receipt = {'schema': 'rolling_independent_qualification_v1', 'status': 'failed',
        'plan': plan_identity, 'source_freeze': identity(output / 'source_freeze.json'),
        'source_bindings': source_bindings, 'build_invocations': 0,
        'qualification_invocations': 1, 'retries': 0, 'cases': [], 'errors': [],
        'canonical_observation_reads': 0, 'truth_reads': 0, 'archive_model_calls': 0,
        'original_learner_calls': 0, 'original_optimizer_calls': 0}
    qualification, oracle, lib = None, None, None
    try:
        library = output / 'rolling_qualification.so'
        engine_path = EXP / 'rolling_engine.c'
        engine_text = engine_path.read_text()
        definition = 'int re_query(re_context *c,int derivatives,int include_prior)'
        if engine_text.count(definition) != 1:
            raise ValueError('Expected exactly one frozen re_query definition for observation interposition')
        observed_text = engine_text.replace(definition, 'int iq_real_engine_query(re_context *c,int derivatives,int include_prior)', 1)
        generated = output / 'rolling_engine_instrumented.c'
        with generated.open('x') as out:
            out.write('#line 1 ' + json.dumps(str(engine_path)) + '\n' + observed_text)
        receipt['query_instrumentation'] = {
            'original_source': identity(engine_path), 'generated_source': identity(generated),
            'replacement_count': 1, 'old_definition': definition,
            'new_definition': 'int iq_real_engine_query(re_context *c,int derivatives,int include_prior)',
            'meaning': 'Only the definition symbol is renamed; unchanged internal re_query calls bind the host recorder, which forwards unchanged arguments. The numerical body and canonical source are unchanged. This avoids assumptions about same-translation-unit linker wrapping.'}
        command = [str(compiler), *plan['compiler_flags'], '-I' + str(ROOT / 'include'), '-I' + str(EXP)]
        command += [str(generated if (ROOT / name) == engine_path else ROOT / name) for name in plan['build_sources']]
        command += ['-Wl,--wrap=rm_query_step', '-Wl,--wrap=rm_merge_step',
                    '-lm', '-o', str(library)]
        save(output / 'build_launch.json', {'argv': command, 'build_number': 1})
        receipt['build_invocations'] = 1
        before_child = resource.getrusage(resource.RUSAGE_CHILDREN)
        build_start = time.monotonic()
        build = subprocess.run(command, cwd=output, capture_output=True, timeout=30, check=False)
        after_child = resource.getrusage(resource.RUSAGE_CHILDREN)
        (output / 'build.stdout').write_bytes(build.stdout)
        (output / 'build.stderr').write_bytes(build.stderr)
        receipt['build'] = {'argv': command, 'exit_code': build.returncode,
            'wall_s': time.monotonic() - build_start,
            'waited_children_CPU_s': after_child.ru_utime + after_child.ru_stime
                - before_child.ru_utime - before_child.ru_stime,
            'cumulative_children_peak_RSS_bytes': after_child.ru_maxrss * 1024,
            'scope': 'One compiler subprocess; CPU difference includes its waited descendants. RSS is the host cumulative-child high-water value, not candidate SRAM.',
            'stdout': identity(output / 'build.stdout'), 'stderr': identity(output / 'build.stderr')}
        if build.returncode:
            raise RuntimeError('Single qualification build failed')
        receipt['library'] = identity(library)
        stack_files = sorted(output.glob('*.su'))
        receipt['stack'] = project_stack([ROOT / x for x in plan['build_sources']], stack_files)
        source_text = '\n'.join((ROOT / x).read_text() for x in plan['candidate_sources'])
        if re.search(r'\b(?:malloc|calloc|realloc|free|alloca|sbrk)\s*\(', source_text):
            raise RuntimeError('Candidate source contains forbidden heap allocation call')
        receipt['candidate_heap_call_scan'] = 'no forbidden allocation calls in the bound candidate source set'
        spec = importlib.util.spec_from_file_location('rolling_independent_oracle', HERE / 'independent_oracle.py')
        oracle = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(oracle)
        lib = C.CDLL(str(library)); bind(lib)
        for i, kind in enumerate((Model, Jet, Bank, QueryState, Workspace, Result, Core, Inputs,
                                 Calibration, Context, Raw, Reading, EvidenceResult, ProposalWorkspace)):
            if C.sizeof(kind) != lib.iq_size(i):
                raise RuntimeError('ctypes ABI mismatch before engine/kernel execution: ' + kind.__name__)
        own_path = receipt['stack']['maximum_project_path_bytes']
        complete = C.sizeof(Context) + max(plan['project_stack_reservation'], own_path) + plan['runtime_IRQ_caller_reservation']
        receipt['memory'] = {'objects_bytes': C.sizeof(Context), 'project_path_bytes': own_path,
            'project_stack_reservation_bytes': plan['project_stack_reservation'],
            'runtime_IRQ_caller_reservation_bytes': plan['runtime_IRQ_caller_reservation'],
            'complete_host_object_and_project_path_with_runtime_reservation_bytes': complete,
            'target_measured': False, 'runtime_reservation_measured': False,
            'host_instrumentation_and_oracle_arrays_are_candidate_owned': False}
        if complete > plan['SRAM_limit']:
            raise RuntimeError('Compiled project call-path budget fails before numerical fixtures')
        save(output / 'fixture_launch.json', {'fixture_names': plan['cases'],
             'single_invocation': 1, 'model_step_limit': 4096, 'merge_step_limit': 256,
             'query_limit': 128, 'library': receipt['library']})
        qualification = Qualification(lib, oracle, plan)
        qualification.run()
        if [case['name'] for case in qualification.cases] != plan['cases']:
            raise RuntimeError('Finite case inventory differs from frozen plan')
        qualification.current['status'] = 'running'
        qualification.check('complete_observed_project_path_budget', complete <= plan['SRAM_limit'],
                            objects=C.sizeof(Context), project_path=own_path,
                            stack_reserved=max(plan['project_stack_reservation'], own_path),
                            runtime_reservation=plan['runtime_IRQ_caller_reservation'], total=complete)
        qualification.current['status'] = 'passed'
        receipt['status'] = 'passed'
    except Exception as error:
        if qualification is not None and qualification.current is not None:
            qualification.current['status'] = 'failed'
        receipt['errors'].append({'type': type(error).__name__, 'detail': str(error)})
    finally:
        if qualification is not None:
            receipt['cases'] = qualification.cases
            receipt['assertions'] = sum(len(case['checks']) for case in qualification.cases)
            receipt['refinement_invocations'] = qualification.refinements
            receipt['pure_host_producer_calls'] = qualification.host_calls
        if oracle is not None:
            receipt['independent_reference_activity'] = oracle.ACTIVITY
        if lib is not None:
            receipt['C_activity'] = {'query_model_step_attempts': lib.iq_activity(0),
                'merge_model_step_attempts': lib.iq_activity(1), 'budget_rejections': lib.iq_activity(2),
                'query_attempts': lib.iq_activity(3)}
        receipt['sources_unchanged'] = all(identity(ROOT / name) == value for name, value in source_bindings.items())
        receipt['plan_unchanged'] = identity(PLAN) == plan_identity
        receipt['compiler_python_unchanged'] = identity(compiler) == compiler_identity and identity(python) == python_identity
        if not (receipt['sources_unchanged'] and receipt['plan_unchanged'] and receipt['compiler_python_unchanged']):
            receipt['status'] = 'failed'; receipt['errors'].append({'detail': 'A frozen input changed'})
        own_after = resource.getrusage(resource.RUSAGE_SELF)
        receipt['resources_before_final_receipt'] = {
            'wall_s': time.monotonic() - started,
            'own_CPU_s': own_after.ru_utime + own_after.ru_stime - own_before.ru_utime - own_before.ru_stime,
            'own_peak_RSS_bytes': own_after.ru_maxrss * 1024,
            'scope': 'Python process including in-process qualification C kernels, measured from main entry before final receipt serialization. Compiler child resources are separate. No Cortex-M23 timing claim.'}
        resource_row = receipt['resources_before_final_receipt']
        if (resource_row['wall_s'] > plan['whole_limits']['wall_s']
                or resource_row['own_CPU_s'] > plan['whole_limits']['own_CPU_s']
                or resource_row['own_peak_RSS_bytes'] > plan['whole_limits']['own_RSS_bytes']):
            receipt['status'] = 'failed'; receipt['errors'].append({'detail': 'Frozen host qualification resource limit exceeded'})
        receipt['files'] = {p.relative_to(output).as_posix(): identity(p)
                            for p in sorted(output.rglob('*')) if p.is_file()}
        closed = sum(value['bytes'] for value in receipt['files'].values())
        receipt['closed_output_bytes_including_receipt'] = closed
        for _ in range(12):
            size = closed + len((json.dumps(clean(receipt), sort_keys=True, indent=2, allow_nan=False) + '\n').encode())
            if size == receipt['closed_output_bytes_including_receipt']:
                break
            receipt['closed_output_bytes_including_receipt'] = size
        if size > plan['whole_limits']['closed_output_bytes']:
            receipt['status'] = 'failed'; receipt['errors'].append({'detail': 'Frozen output limit exceeded'})
            for _ in range(12):
                size = closed + len((json.dumps(clean(receipt), sort_keys=True, indent=2, allow_nan=False) + '\n').encode())
                if size == receipt['closed_output_bytes_including_receipt']:
                    break
                receipt['closed_output_bytes_including_receipt'] = size
        save(output / 'receipt.json', receipt)
    print(json.dumps({'status': receipt['status'], 'receipt': str(output / 'receipt.json'),
                      'identity': identity(output / 'receipt.json'), 'assertions': receipt.get('assertions'),
                      'C_activity': receipt.get('C_activity'), 'errors': receipt['errors']}))
    return 0 if receipt['status'] == 'passed' else 1


if __name__ == "__main__":
    raise SystemExit(main())
