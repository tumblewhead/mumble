#!/usr/bin/env python3
"""Saved-output-only underflow diagnostic for one preserved parity failure.

No work is performed on import.  No model, optimizer, archive or truth reader
exists here.  The original gate/result remains immutable.  This diagnostic is
eligible only for its sole observed direct (v10, log_gamma_minus) mismatch.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from decimal import Decimal, localcontext, ROUND_CEILING
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import resource
import struct
import sys
import time


U = Fraction(1, 2 ** 53)
ETA = Fraction(1, 2 ** 1074)
HALF_ETA = ETA / 2
ONE = Fraction(1)
PREFIX = 252000
PAIR = 82
ROW = 12
COL = 4
DIAGONAL = 14
SCALES = [1., 1., 1., 1., 1., .1, 1., .2, .2, .2, .2, .03, .03, .03, .03, .03]
INPUTS = {
    "saved_free": "experiments/historical_likelihood_control_001/attempt002/free/stdout.json",
    "evaluator": "experiments/retained_likelihood_replacement_001/attempt001/replacement_anchor/stdout.json",
    "original_parity": "experiments/retained_likelihood_replacement_001/attempt001/historical_parity.json",
}
SOURCE_HASHES = {
    "src/scm_estimator.c": "28846f09c4edde6f3ae1e92cc174a5e6fa082a7a83e5f27824f3ff021a5e6bb5",
    "src/scm_model.c": "05d7ddd5ec2736875b809c3f8cdd48910804d10873043bc366e314e3b5cb4646",
    "experiments/retained_likelihood_replacement_001/stream_evaluator.c": "29cfafde5b13b6039401181755266b92220bcee91a0f0bfe819e9123ee7a5942",
    "tools/run_retained_likelihood_replacement.py": "aaaa652008e03476768e273fa048e8567a9e9b932a43c6716d12b41aca5e1986",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value, name):
    require(type(value) in (int, float) and math.isfinite(value), "Expected finite number: " + name)
    return float(value)


def vector(values, count, name):
    require(isinstance(values, list) and len(values) == count, "Wrong shape: " + name)
    return [number(value, name) for value in values]


def gamma(k):
    require(type(k) is int and 0 <= k and k * U < 1, "Invalid gamma count")
    return k * U / (1 - k * U)


def gamma_float(k):
    ku = k * 2. ** -53
    return ku / (1. - ku)


def exact(value):
    return Fraction.from_float(number(value, "binary64 operand"))


def decimal_upper(value):
    with localcontext() as context:
        context.prec = 100
        context.rounding = ROUND_CEILING
        return str(Decimal(value.numerator) / Decimal(value.denominator))


def float_upper(value):
    require(value >= 0, "Negative upper bound")
    result = float(value)
    require(math.isfinite(result), "Nonfinite upper bound")
    if Fraction.from_float(result) < value:
        result = math.nextafter(result, math.inf)
    require(math.isfinite(result) and Fraction.from_float(result) >= value, "Outward float conversion failed")
    return result


def sqrt_upper(value):
    require(value >= 0, "Negative squared norm")
    if value == 0:
        return Fraction(0)
    with localcontext() as context:
        context.prec = 100
        context.rounding = ROUND_CEILING
        operand = Decimal(value.numerator) / Decimal(value.denominator)
        # Decimal.sqrt is correctly rounded. One next_plus covers either its
        # last-bit direction; the exact square check is the admission rule.
        root = context.sqrt(operand).next_plus(context)
        bound = Fraction(root)
    require(bound * bound >= value, "Outward square-root verification failed")
    return bound


def preprocessing_coefficients(sigma, scale):
    sigma, scale = exact(sigma), exact(scale)
    require(sigma > 0 and scale > 0, "Nonpositive sigma/coordinate scale")
    tmax = (1 + U) ** 2 / (1 - U)
    rho = tmax - 1
    E = HALF_ETA * (tmax + (1 + U) / (sigma * scale) + 1 / scale)
    return rho, E


def allowance(n, sigma, scale, diagonal, absolute_cross, reference, old_allowance):
    """Complete computed-Gram bound for a direct scaled/unit-scale pair.

    All algebra is exact rational arithmetic except an outward decimal square
    root whose exact rational square is checked.  eta/2 never becomes float0.
    """
    require(type(n) is int and 1 <= n <= PREFIX, "Unsupported sample count")
    D, S, R = exact(diagonal), exact(absolute_cross), abs(exact(reference))
    old = exact(old_allowance)
    require(D >= 0 and S >= 0 and old >= 0, "Negative saved accumulation quantity")
    scale_f = exact(scale)
    g = gamma(n)
    beta = U + (1 + U) * g * g
    Gamma = gamma(8 * n + 128)
    require(beta < 1 and beta <= Gamma < 1, "Inherited diagonal relative bound insufficient")
    rho, E = preprocessing_coefficients(sigma, scale)
    lam = g + U * (1 + g)
    A = rho + U * (2 + rho)
    C = A + lam * (1 + U) * (1 + rho)
    K = (beta + C / (1 - U)) / (1 - beta)
    require(K <= Gamma, "Inherited cross-product relative budget insufficient")
    sum_squared_upper = (D / (1 - Gamma) + n * HALF_ETA) / (1 - U)
    L1 = sqrt_upper(n * sum_squared_upper)
    jacobian_loss = (1 + U) * (1 + lam) * E * L1
    gram_product_loss = n * HALF_ETA * (1 + (1 + lam) / scale_f + C / (1 - U))
    final_unscaling_loss = HALF_ETA
    B = jacobian_loss + gram_product_loss + final_unscaling_loss
    rounding_recovery = max(Fraction(0), Gamma * (S + R) - old)
    total = old + B + rounding_recovery
    return {"total": total, "underflow": B, "rounding_recovery": rounding_recovery,
            "jacobian_loss": jacobian_loss, "gram_product_loss": gram_product_loss,
            "final_unscaling_loss": final_unscaling_loss, "Gamma": Gamma, "beta": beta,
            "rho": rho, "E": E, "lambda": lam, "A": A, "C": C, "K": K,
            "sum_squared_upper": sum_squared_upper, "L1_upper": L1}


def mapped_reference(saved, x):
    flat = vector(saved["joint_normal"], 256, "legacy Gram")
    scales = vector(saved["coordinate_scales"], 16, "legacy scales")
    require(scales == SCALES, "Public legacy coordinate scales differ")
    require(all(flat[16 * r + c] == flat[16 * c + r] for r in range(16) for c in range(16)),
            "Legacy full matrix is not symmetric")
    columns = [[] for _ in range(16)]
    for row, column in enumerate((0, 1, 2, 3, 4, 11, 5, 6, 7, 8, 9, 10, 12, 13, 14)):
        columns[column].append((row, 1.))
    columns[10].append((15, x[15]))
    columns[15].append((15, x[10]))
    result, absolute = [], []
    for i in range(16):
        for j in range(i + 1):
            terms = [di * dj * (flat[16 * r + c] / scales[r] / scales[c])
                     for r, di in columns[i] for c, dj in columns[j]]
            result.append(math.fsum(terms))
            absolute.append(math.fsum(abs(value) for value in terms))
    return result, absolute


def original_comparison(saved, evaluator):
    x = vector(evaluator["x"], 16, "entering x")
    reference, reference_abs = mapped_reference(saved, x)
    observed = vector(evaluator["gram"], 136, "evaluator Gram")
    absolute = vector(evaluator["absolute_summand_scales"]["gram"], 136, "absolute Gram scales")
    factor = gamma_float(8 * PREFIX + 128)
    rows = []
    for i, (a, b, r) in enumerate(zip(observed, reference, reference_abs)):
        bound = factor * (absolute[i] + r)
        error = abs(a - b)
        rows.append({"packed_index": i, "actual": a, "reference": b, "absolute_error": error,
                     "allowance": bound, "passed": error <= bound})
    return rows


def derivation():
    return {
        "arithmetic": "Binary64 round to nearest, ties to even, gradual underflow, no overflow; u=2^-53, eta=2^-1074. Multiplication/division obey |fl(z)-z|<=u*|z|+eta/2. Add/subtract of binary64 inputs is exact whenever its exact result is subnormal (eta lattice).",
        "source_pair": "Direct v10/log_gamma_minus only. Legacy X=fl(fl(v*s)/sigma), new a=fl(v/sigma), s=0.03. Counterpart y is the identical scale1 gamma-minus computation; same theta/alpha, model, observations and derivative convention are required.",
        "preprocessing": "With b=legacy_X/s in exact reals, |a-b|<=rho*|a|+E; rho=(1+u)^2/(1-u)-1; E=eta/2*((1+u)^2/(1-u)+(1+u)/(sigma*s)+1/s).",
        "compensated_sum": "Neumaier selects the larger-magnitude input, so its two-term residual is error-free under the stated arithmetic. For exact input absolute sum Q, the stored correction accumulation plus final addition gives error<=beta*Q, beta=u+(1+u)*gamma(N)^2. We verify beta<=Gamma=gamma(8N+128).",
        "diagonal": "For computed q_k=fl(y_k^2)>=0, sum q_k<=D/(1-Gamma). Product rounding gives sum y_k^2<=[D/(1-Gamma)+N*eta/2]/(1-u). Cauchy-Schwarz gives L1=sum|y_k|<=sqrt(N*that upper bound).",
        "full_relative_coefficient": "g=gamma(N); lambda=g+u*(1+g); A=rho+u*(2+rho); C=A+lambda*(1+u)*(1+rho); K=(beta+C/(1-u))/(1-beta). We verify K<=Gamma exactly, covering preprocessing, product, new compensated sum, old naive sum and final legacy division relative errors.",
        "additive_underflow": "B=(1+u)*(1+lambda)*E*L1 + N*eta/2*(1+(1+lambda)/s+C/(1-u)) + eta/2. These are preprocessing loss, new/legacy Gram-product loss with accumulation amplification, and final legacy unscaling loss.",
        "allowance_rounding": "Add max(0,Gamma*(saved_abs_cross+abs(reference))-original_float_allowance), recovering downward rounding of the former allowance. This alone is insufficient; B is essential.",
        "scope": "Conditional certificate for comparing computed arithmetic of this one direct pair, with the common raw stream and source conventions assumed/bound by the caller. It does not certify the model/libm/derivative recurrence against exact physics or certify statistical uncertainty. No voltage or observed-error floor.",
        "source_anchors": ["src/scm_estimator.c:inner,system_matrix", "src/scm_model.c:scm_model_step,scm_model_predict",
                           "stream_evaluator.c:map_jacobian,accumulate,neumaier", "run_retained_likelihood_replacement.py:parity_check"],
    }


def diagnose(saved_free_payload, evaluator_payload, original_parity_payload):
    report = {"schema": "mumble_underflow_parity_diagnostic_v1", "status": "ineligible",
              "eligible": False, "original_gate_passed": original_parity_payload.get("passed"),
              "corrected_gate_passed": False, "original_attempt_reclassified": False,
              "additive_underflow_bound": None, "derivation": derivation(),
              "counts": {"model_calls": 0, "optimizer_calls": 0, "archive_reads": 0, "truth_reads": 0}}
    try:
        f, a, original = saved_free_payload, evaluator_payload, original_parity_payload
        require(f["method"] == "full" and f["modes"] == 3 and f["status"] == 0
                and f["samples"] == PREFIX and f["joint_normal_dimension"] == 16, "Historical reference identity differs")
        require(f["joint_normal_semantics"] == "Scaled likelihood Jacobian Gram matrix before damping and Schur reduction; not a posterior"
                and f["joint_normal_coordinates"] == "Scaled theta followed by scaled alpha; packed row-major", "Legacy matrix convention differs")
        require(a["schema"] == "mumble_retained_likelihood_stream_evaluator_v1" and a["status"] == "ok"
                and a["dimension"] == 16 and a["prefix_requested"] == a["records_accumulated"] == PREFIX,
                "Saved evaluator identity differs")
        require(number(a["sigma_V"], "sigma") == number(f["sigma_V"], "legacy sigma") == .001, "Sigma differs")
        x = vector(a["x"], 16, "entering x")
        theta = [*x[:5], x[11], x[5]]
        alpha = [*x[6:11], *x[12:15], x[10] * x[15]]
        require(all(struct.pack("<d", v) == struct.pack("<d", w) for v, w in
                    zip(theta + alpha, vector(f["theta"], 7, "theta") + vector(f["alpha"], 9, "alpha"))),
                "Counterpart computation is not bound to bit-identical theta/alpha")
        rows = original_comparison(f, a)
        require(original["Gram"] == rows, "Preserved comparator rows differ from saved source reconstruction")
        require(original["passed"] is False and original["cost"]["passed"] is True
                and original["endpoint_SOC"]["passed"] is True, "Original non-Gram gate did not pass")
        failures = [row["packed_index"] for row in rows if not row["passed"]]
        require(failures == [PAIR], "Additional or different original parity failures remain fatal")
        row = rows[PAIR]
        require(row["reference"] == 0. and 0. < abs(row["actual"]) < sys.float_info.min,
                "Not the fixed zero-reference/subnormal direct-pair case")
        scales = a["absolute_summand_scales"]["gram"]
        require(number(scales[PAIR], "cross absolute scale") >= abs(row["actual"]), "Absolute cross scale is inconsistent")
        require(number(a["gram"][DIAGONAL], "counterpart diagonal") >= 0.
                and a["gram"][DIAGONAL] == scales[DIAGONAL], "Counterpart diagonal is not its nonnegative compensated sum")
        require(sys.float_info.radix == 2 and sys.float_info.mant_dig == 53
                and Fraction.from_float(math.ulp(0.)) == ETA and math.ulp(0.) / .001 > 0.,
                "Scalar host does not exhibit required binary64 gradual underflow")
        values = allowance(PREFIX, .001, SCALES[12], a["gram"][DIAGONAL], scales[PAIR],
                           row["reference"], row["allowance"])
        error = abs(exact(row["actual"]) - exact(row["reference"]))
        passed = error <= values["total"]
        report.update(status="corrected_diagnostic_pass" if passed else "corrected_diagnostic_fail",
                      eligible=True, corrected_gate_passed=passed,
                      original_failed_indices=failures, original_passed_Gram_entries=135,
                      selected_pair={"packed_index": PAIR, "row": ROW, "column": COL,
                                     "coordinates": ["v10", "log_gamma_minus"], **row},
                      additive_underflow_bound={
                          "float_upper": float_upper(values["underflow"]),
                          "decimal_upper": decimal_upper(values["underflow"]),
                          "jacobian_preprocessing_loss_decimal_upper": decimal_upper(values["jacobian_loss"]),
                          "Gram_product_loss_decimal_upper": decimal_upper(values["gram_product_loss"]),
                          "final_unscaling_loss_decimal_upper": decimal_upper(values["final_unscaling_loss"]),
                          "old_allowance_rounding_recovery_decimal_upper": decimal_upper(values["rounding_recovery"]),
                      },
                      corrected_total_allowance={"float_upper": float_upper(values["total"]),
                                                 "decimal_upper": decimal_upper(values["total"])},
                      normal_budget_check={"K_decimal_upper": decimal_upper(values["K"]),
                                           "Gamma_decimal_upper": decimal_upper(values["Gamma"]),
                                           "beta_decimal_upper": decimal_upper(values["beta"]),
                                           "K_le_Gamma_exact": values["K"] <= values["Gamma"],
                                           "beta_le_Gamma_exact": values["beta"] <= values["Gamma"]},
                      diagonal_norm_bound={"saved_gamma_diagonal": a["gram"][DIAGONAL],
                                           "sum_squared_upper": decimal_upper(values["sum_squared_upper"]),
                                           "L1_upper": decimal_upper(values["L1_upper"])},
                      comparison="Exact rational error versus exact rational allowance using an outward square-root bound; float outputs are rounded upward",
                      preserved_disposition="Original attempt remains failed. This is a separate saved-output diagnostic, not authorization to resume or a retrospective gate rewrite.")
    except (ValueError, KeyError, TypeError, OverflowError) as error:
        report["ineligibility"] = {"type": type(error).__name__, "reason": str(error)}
    return report


def _neumaier(values):
    total = correction = 0.
    for value in values:
        updated = total + value
        error = (total - updated) + value if abs(total) >= abs(value) else (value - updated) + total
        correction += error
        total = updated
    return total + correction


def _fabricated_payloads():
    theta = [-3., -1., 1., 5., 6., .5, math.log(.0625)]
    alpha = [.1, .2, .3, .4, .03125, 0., 0., 0., .0078125]
    x = theta[:5] + [theta[6]] + alpha[:5] + [theta[5]] + alpha[5:8] + [.25]
    G = [0.] * 256
    G[16 * 4 + 4] = float(PREFIX)
    saved = {"method": "full", "modes": 3, "status": 0, "samples": PREFIX,
             "sigma_V": .001, "joint_normal_dimension": 16,
             "joint_normal_semantics": "Scaled likelihood Jacobian Gram matrix before damping and Schur reduction; not a posterior",
             "joint_normal_coordinates": "Scaled theta followed by scaled alpha; packed row-major",
             "coordinate_scales": SCALES.copy(), "theta": theta, "alpha": alpha, "joint_normal": G}
    gram, _ = mapped_reference(saved, x)
    gram[PAIR] = PREFIX * (-math.ulp(0.) / .001)
    a = {"schema": "mumble_retained_likelihood_stream_evaluator_v1", "status": "ok", "dimension": 16,
         "prefix_requested": PREFIX, "records_accumulated": PREFIX, "sigma_V": .001,
         "x": x, "gram": gram, "absolute_summand_scales": {"gram": [abs(v) for v in gram]}}
    p = {"passed": False, "cost": {"passed": True}, "endpoint_SOC": {"passed": True},
         "Gram": original_comparison(saved, a)}
    return saved, a, p


def qualify():
    checks, witnesses = [], {}
    def check(name, value, detail=None):
        checks.append({"name": name, "pass": bool(value), "detail": detail})
    eta = math.ulp(0.)
    check("minimum_subnormal_and_half_underflow", exact(eta) == ETA and eta * .5 == 0.)
    check("ties_to_even_subnormal_rounding", eta * 1.5 == 2. * eta)
    check("scale_before_whitening_loses_saved_type_of_tail", (-eta * .03) / .001 == 0.
          and -eta / .001 == -1000. * eta)
    rho, E = preprocessing_coefficients(.001, .03)
    values = [eta, 2. * eta, 17. * eta, 1000. * eta, sys.float_info.min / 64.,
              sys.float_info.min, 1e-100, .125, 1., 1e300]
    for index, v in enumerate(values + [-v for v in values]):
        new = exact(v / .001)
        old = exact((v * .03) / .001) / exact(.03)
        check(f"preprocessing_bound_{index}", abs(new - old) <= rho * abs(new) + E)
    sequences = [
        ([eta] * 9, [1.] * 9),
        ([-eta, 2. * eta, -3. * eta, 17. * eta], [1., -2., 3., -.5]),
        ([sys.float_info.min / 64., -sys.float_info.min / 32.], [2., 1.]),
        ([.125, -.25, .5, -.0625], [2., -.5, .25, 4.]),
    ]
    for index, (raw, counterpart) in enumerate(sequences):
        a = [v / .001 for v in raw]
        b_scaled = [(v * .03) / .001 for v in raw]
        new_terms = [v * y for v, y in zip(a, counterpart)]
        old_terms = [v * y for v, y in zip(b_scaled, counterpart)]
        observed = _neumaier(new_terms)
        old_sum = 0.
        for value in old_terms:
            old_sum += value
        reference = old_sum / .03
        absolute = _neumaier([abs(value) for value in new_terms])
        D = _neumaier([value * value for value in counterpart])
        old_bound = gamma_float(8 * len(raw) + 128) * (absolute + abs(reference))
        bound = allowance(len(raw), .001, .03, D, absolute, reference, old_bound)
        check(f"full_Gram_arithmetic_bound_{index}", abs(exact(observed) - exact(reference)) <= bound["total"],
              {"new": observed, "legacy": reference, "old_allowance": old_bound,
               "corrected_allowance_upper": float_upper(bound["total"])})
    tiny = math.sqrt(eta) / 4.
    counterpart = [tiny] * 7
    D = _neumaier([v * v for v in counterpart])
    bound = allowance(7, .001, .03, D, 0., 0., 0.)
    exact_norm2 = sum((exact(v) ** 2 for v in counterpart), Fraction(0))
    check("zero_recorded_diagonal_still_bounds_squared_term_underflow", D == 0. and exact_norm2 > 0.
          and bound["sum_squared_upper"] >= exact_norm2)
    check("outward_L1_bound_verified_by_exact_square", bound["L1_upper"] >= sum((abs(exact(v)) for v in counterpart), Fraction(0)))
    check("outward_float_conversion_never_zeros_positive_allowance", float_upper(HALF_ETA) == eta)
    saved, a, p = _fabricated_payloads()
    positive = diagnose(saved, a, p)
    check("fabricated_selected_failure_corrected_without_reclassifying_original", positive["eligible"]
          and positive["corrected_gate_passed"] and positive["original_gate_passed"] is False
          and positive["original_attempt_reclassified"] is False)
    larger = deepcopy(a)
    larger["gram"][PAIR] = -sys.float_info.min / 2.
    larger["absolute_summand_scales"]["gram"][PAIR] = abs(larger["gram"][PAIR])
    larger_p = {**p, "Gram": original_comparison(saved, larger)}
    negative = diagnose(saved, larger, larger_p)
    check("not_every_subnormal_discrepancy_is_accepted", negative["eligible"] and not negative["corrected_gate_passed"])
    extra = deepcopy(a)
    extra["gram"][0] = extra["absolute_summand_scales"]["gram"][0] = 1.
    extra_p = {**p, "Gram": original_comparison(saved, extra)}
    check("additional_failure_remains_fatal", not diagnose(saved, extra, extra_p)["eligible"])
    bad_scale = deepcopy(saved)
    bad_scale["coordinate_scales"][12] = .04
    check("changed_legacy_scale_rejected", not diagnose(bad_scale, a, p)["eligible"])
    bad_alpha = deepcopy(saved)
    bad_alpha["alpha"][4] = math.nextafter(bad_alpha["alpha"][4], math.inf)
    check("nonidentical_counterpart_anchor_rejected", not diagnose(bad_alpha, a, p)["eligible"])
    check("other_original_gate_failure_remains_fatal", not diagnose(saved, a, {**p, "cost": {"passed": False}})["eligible"])
    witnesses.update(selected_case=positive, larger_subnormal_rejected=negative)
    return {"schema": "mumble_underflow_parity_qualification_v1",
            "status": "pass" if all(row["pass"] for row in checks) else "failed",
            "checks": checks, "check_count": len(checks), "failed_count": sum(not row["pass"] for row in checks),
            "witnesses": witnesses, "derivation": derivation(),
            "counts": {"model_calls": 0, "optimizer_calls": 0, "canonical_data_reads": 0, "truth_reads": 0}}


def strict_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    def constant(value):
        raise ValueError("Nonfinite JSON constant: " + value)
    return json.loads(data, object_pairs_hook=pairs, parse_constant=constant,
                      parse_float=lambda text: number(float(text), "JSON exponent"))


def write_new(path, value):
    data = (json.dumps(value, indent=2, allow_nan=False) + "\n").encode()
    require(len(data) <= 512 * 1024, "Diagnostic output cap exceeded")
    with path.open("xb") as stream:
        stream.write(data)
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    q = sub.add_parser("qualify")
    q.add_argument("--output", required=True, type=Path)
    d = sub.add_parser("diagnose")
    d.add_argument("--root", required=True, type=Path)
    d.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    started, cpu = time.monotonic(), time.process_time()
    own = Path(__file__).resolve()
    source_identity = {"path": str(own), "sha256": hashlib.sha256(own.read_bytes()).hexdigest()}
    if args.command == "qualify":
        result = qualify()
        result["source"] = source_identity
        result["resources"] = {"wall_s_before_encoding": time.monotonic() - started,
                               "CPU_s_before_encoding": time.process_time() - cpu,
                               "own_peak_RSS_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024}
        identity = write_new(args.output, result)
        print(json.dumps({"status": result["status"], "checks": result["check_count"],
                          "failed": result["failed_count"], "output": identity}))
        return 0 if result["status"] == "pass" else 1
    root = args.root.resolve()
    args.output_dir.mkdir(exist_ok=False)
    source_bindings = {}
    for relative, expected in SOURCE_HASHES.items():
        data = (root / relative).read_bytes()
        require(hashlib.sha256(data).hexdigest() == expected, "Unchanged source differs: " + relative)
        source_bindings[relative] = {"sha256": expected, "bytes": len(data)}
    payloads, input_bindings, originals = {}, {}, {}
    for key, relative in INPUTS.items():
        data = (root / relative).read_bytes()
        require(len(data) <= 1024 * 1024, "Saved JSON exceeds input cap")
        originals[relative] = data
        payloads[key] = strict_json(data)
        input_bindings[relative] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    result = diagnose(payloads["saved_free"], payloads["evaluator"], payloads["original_parity"])
    for relative, data in originals.items():
        require((root / relative).read_bytes() == data, "Saved input changed")
    result_identity = write_new(args.output_dir / "diagnostic.json", result)
    receipt = {"schema": "mumble_underflow_parity_saved_receipt_v1", "status": result["status"],
               "source": source_identity, "unchanged_source_bindings": source_bindings,
               "input_bindings": input_bindings, "diagnostic": result_identity,
               "original_gate_passed": result["original_gate_passed"], "corrected_gate_passed": result["corrected_gate_passed"],
               "original_attempt_reclassified": False, "original_artifacts_modified": False,
               "counts": result["counts"], "resources": {"wall_s_before_encoding": time.monotonic() - started,
                   "CPU_s_before_encoding": time.process_time() - cpu,
                   "own_peak_RSS_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024}}
    identity = write_new(args.output_dir / "receipt.json", receipt)
    print(json.dumps({"status": result["status"], "eligible": result["eligible"],
                      "original_gate_passed": result["original_gate_passed"],
                      "corrected_gate_passed": result["corrected_gate_passed"], "receipt": identity}))
    return 0 if result["corrected_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
