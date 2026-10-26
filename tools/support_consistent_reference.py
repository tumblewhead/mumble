#!/usr/bin/env python3
"""Qualify the frozen single-h-bound affine reference using fabricated inputs.

No battery transition, learner, canonical checkpoint, observation or truth is read.
The independent oracle conditions on h BEFORE voltage and integrates only h.
The output file is reserved exclusively, including for unsuccessful attempts.
"""

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import resource
import signal
import stat
import sys
import time


PLAN = "plans/support_consistent_conditional_001.json"
PLAN_SHA256 = "6dc336a03686716f8bbc1fe225b5f80eb0d495781ebfc25ce42366d905fd74a8"
PUBLIC_SOURCE = "src/scm_hypothesis.c"
PUBLIC_SHA256 = "779f4854cabf434db70b71a47b098fe15b1b54d54b5c440df2c2393a2c1fecb5"
MATH = "experiments/support_consistent_conditional_001/mathematics.json"
OWN_SOURCE = "tools/support_consistent_reference.py"
D, Q, Z, H = 16, 5, 11, 15
LOWER, UPPER = -1.0, 1.0
EPS = sys.float_info.epsilon
GAMMA = 16384 * EPS / (1 - 16384 * EPS)
QUAD_EPS = 64 * EPS
LOG_2PI = math.log(2 * math.pi)
COUNTS = {"affine_kernel_products": 0, "oracle_integrals": 0,
          "quadrature_calls": 0, "quadrature_function_evaluations": 0}
QUADRATURE = []


class ReferenceError(RuntimeError):
    pass


class InvalidSupport(ReferenceError):
    pass


class InvalidKernel(ReferenceError):
    pass


def require(condition, message, error=ReferenceError):
    if not condition:
        raise error(message)


def interrupt_budget(signum, frame):
    raise ReferenceError("Resource signal " + str(signum))


def digest(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    hasher, count = hashlib.sha256(), 0
    with os.fdopen(fd, "rb") as stream:
        require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "Nonregular input: " + str(path))
        while chunk := stream.read(65536):
            hasher.update(chunk)
            count += len(chunk)
    return {"sha256": hasher.hexdigest(), "bytes": count}


def rss_bytes():
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * (1 if sys.platform == "darwin" else 1024)


def norm(value):
    return float(np.linalg.norm(np.asarray(value, dtype=float).reshape(-1)))


class Checks:
    def __init__(self):
        self.records = []

    def equal(self, name, actual, reference, quadrature_error=0.0):
        a, b = np.asarray(actual, dtype=float), np.asarray(reference, dtype=float)
        require(a.shape == b.shape, "Comparison shape mismatch: " + name)
        finite = bool(np.isfinite(a).all() and np.isfinite(b).all() and math.isfinite(quadrature_error))
        discrepancy = float(np.max(np.abs(a - b))) if finite and a.size else (0.0 if finite else math.inf)
        ref_norm = norm(b) if finite else math.inf
        allowance = GAMMA * max(1.0, ref_norm) + 16 * quadrature_error
        passed = finite and quadrature_error >= 0 and discrepancy <= allowance
        item = {"name": name, "passed": bool(passed), "kind": "numerical_reconstruction",
                "max_absolute_discrepancy": discrepancy, "reference_norm": ref_norm,
                "reported_quadrature_error_norm": quadrature_error, "allowance": allowance,
                "shape": list(a.shape)}
        if not passed and finite and a.size:
            index = np.unravel_index(int(np.argmax(np.abs(a - b))), a.shape)
            item.update(index=list(index), actual=float(a[index]), reference=float(b[index]))
        self.records.append(item)
        return passed

    def condition(self, name, passed, details=None):
        self.records.append({"name": name, "passed": bool(passed), "kind": "logical_or_exact",
                             "details": details})
        return bool(passed)

    def psd(self, name, covariance):
        minimum = float(np.linalg.eigvalsh(covariance)[0])
        allowance = GAMMA * max(1.0, norm(covariance))
        self.condition(name, minimum >= -allowance,
                       {"minimum_eigenvalue": minimum, "roundoff_allowance": allowance,
                        "covariance_modified": False})

    def summary(self):
        numeric = [r for r in self.records if r["kind"] == "numerical_reconstruction"]
        return {"count": len(self.records), "passed": all(r["passed"] for r in self.records),
                "failed_count": sum(not r["passed"] for r in self.records),
                "maximum_raw_absolute_discrepancy": max((r["max_absolute_discrepancy"] for r in numeric), default=0),
                "records": self.records}


@dataclass(frozen=True)
class Kernel:
    mean: object
    covariance: object

    @staticmethod
    def create(mean, covariance):
        m, k = np.array(mean, dtype=float, copy=True), np.array(covariance, dtype=float, copy=True)
        m.setflags(write=False)
        k.setflags(write=False)
        return Kernel(m, k)

    def record(self):
        return {"mean": self.mean, "covariance": self.covariance}

    def bytes(self):
        return self.mean.tobytes() + self.covariance.tobytes()


def validate_kernel(kernel):
    m, k = kernel.mean, kernel.covariance
    require(m.shape == (D,) and k.shape == (D, D), "Kernel dimensions", InvalidKernel)
    require(np.isfinite(m).all() and np.isfinite(k).all(), "Nonfinite kernel", InvalidKernel)
    require(np.array_equal(k, k.T), "Asymmetric kernel", InvalidKernel)
    require(k[H, H] >= 0, "Negative h variance", InvalidKernel)
    if k[H, H] == 0:
        require(np.count_nonzero(k[H, :]) == 0 and np.count_nonzero(k[:, H]) == 0,
                "Zero h variance with nonzero cross row", InvalidKernel)
    eigen_min = float(np.linalg.eigvalsh(k)[0])
    require(eigen_min >= -GAMMA * max(1.0, norm(k)), "Indefinite kernel", InvalidKernel)
    return eigen_min


def log_interval_mass(alpha, beta):
    require(alpha < beta, "Empty standardized interval", InvalidSupport)
    if beta <= 0:
        lo, hi = float(special.log_ndtr(alpha)), float(special.log_ndtr(beta))
        value = hi + math.log(-math.expm1(lo - hi))
    elif alpha >= 0:
        hi, lo = float(special.log_ndtr(-alpha)), float(special.log_ndtr(-beta))
        value = hi + math.log(-math.expm1(lo - hi))
    else:
        mass = float(special.ndtr(beta) - special.ndtr(alpha))
        require(mass > 0, "Unresolved positive support mass", InvalidSupport)
        value = math.log(mass)
    require(math.isfinite(value), "Nonfinite support log mass", InvalidSupport)
    return value


def supported_moments(kernel):
    eigen_min = validate_kernel(kernel)
    m, k = kernel.mean, kernel.covariance
    variance = float(k[H, H])
    if variance == 0:
        require(LOWER <= m[H] <= UPPER, "Zero-mass deterministic h prior", InvalidSupport)
        return {"mean": m.copy(), "covariance": k.copy(), "log_support_mass": 0.0,
                "scalar_h_mean": float(m[H]), "scalar_h_variance": 0.0,
                "singular_h": True, "kernel_minimum_eigenvalue": eigen_min}
    sd = math.sqrt(variance)
    alpha, beta = (LOWER - m[H]) / sd, (UPPER - m[H]) / sd
    log_mass = log_interval_mass(alpha, beta)
    ratio_a = math.exp(-0.5 * alpha * alpha - 0.5 * LOG_2PI - log_mass)
    ratio_b = math.exp(-0.5 * beta * beta - 0.5 * LOG_2PI - log_mass)
    shift = ratio_a - ratio_b
    h_mean = float(m[H] + sd * shift)
    h_variance = variance * (1 + alpha * ratio_a - beta * ratio_b - shift * shift)
    require(math.isfinite(h_variance) and h_variance > 0, "Nonpositive finite-interval h variance")
    require(LOWER < h_mean < UPPER, "Supported mean not strictly interior")
    direction = k[:, H] / variance
    mean = m + direction * (h_mean - m[H])
    covariance = k + np.outer(direction, direction) * (h_variance - variance)
    require(np.isfinite(mean).all() and np.isfinite(covariance).all(), "Nonfinite supported moments")
    return {"mean": mean, "covariance": covariance, "log_support_mass": log_mass,
            "scalar_h_mean": h_mean, "scalar_h_variance": h_variance,
            "alpha": alpha, "beta": beta, "singular_h": False,
            "kernel_minimum_eigenvalue": eigen_min}


def observation(J, c, R, y):
    return {"J": np.asarray(J, dtype=float), "c": float(c), "R": float(R), "y": float(y)}


def observation_arrays(observations):
    A = np.stack([o["J"] for o in observations])
    c = np.array([o["c"] for o in observations])
    noise = np.array([o["R"] for o in observations])
    y = np.array([o["y"] for o in observations])
    require(A.shape == (len(observations), D) and np.isfinite(A).all()
            and np.isfinite(c).all() and np.isfinite(noise).all() and np.isfinite(y).all()
            and np.all(noise > 0), "Invalid affine observation")
    return A, c, noise, y


def gaussian_log_density(residual, cholesky):
    whitened = np.linalg.solve(cholesky, residual)
    return float(-0.5 * (len(residual) * LOG_2PI + 2 * np.log(np.diag(cholesky)).sum()
                        + whitened @ whitened))


def closed_product(prior, observations):
    # This support validation deliberately precedes every likelihood operation.
    before = supported_moments(prior)
    A, c, noise, y = observation_arrays(observations)
    COUNTS["affine_kernel_products"] += 1
    cross = prior.covariance @ A.T
    S = np.diag(noise) + A @ cross
    chol = np.linalg.cholesky(S)
    residual = y - c - A @ prior.mean
    log_gaussian = gaussian_log_density(residual, chol)
    if np.count_nonzero(cross) == 0:
        posterior = Kernel.create(prior.mean, prior.covariance)
    else:
        whitened = np.linalg.solve(chol, cross.T)
        gain_residual = np.linalg.solve(chol.T, np.linalg.solve(chol, residual))
        posterior = Kernel.create(prior.mean + cross @ gain_residual,
                                  prior.covariance - whitened.T @ whitened)
    after = supported_moments(posterior)
    log_evidence = log_gaussian + after["log_support_mass"] - before["log_support_mass"]
    return {"prior_kernel": prior, "posterior_kernel": posterior, "prior_supported": before,
            "posterior_supported": after, "log_gaussian_evidence": log_gaussian,
            "log_evidence": log_evidence, "log_normalizer_ratio": after["log_support_mass"] - before["log_support_mass"],
            "innovation": residual, "innovation_covariance": S}


def integrate_scalar(name, function):
    result = integrate.quad(function, LOWER, UPPER, epsabs=QUAD_EPS,
                            epsrel=QUAD_EPS, limit=200, full_output=1)
    value, error, info = result[:3]
    row = {"name": name, "value": float(value), "reported_error": float(error),
           "function_evaluations": int(info["neval"]), "subintervals": int(info["last"])}
    if len(result) != 3:
        row["failure"] = str(result[3])
    QUADRATURE.append(row)
    COUNTS["quadrature_calls"] += 1
    COUNTS["quadrature_function_evaluations"] += int(info["neval"])
    require(len(result) == 3 and math.isfinite(value) and math.isfinite(error) and error >= 0,
            "Quadrature failed: " + name)
    return float(value), float(error)


def finite_interval_peak(log_density, stationary):
    # A numerical scaling point only; no distribution or quadrature point is clipped.
    candidates = [LOWER, UPPER]
    if LOWER < stationary < UPPER:
        candidates.append(float(stationary))
    point = max(candidates, key=log_density)
    return point, float(log_density(point))


def conditioned_h_oracle(prior, observations, label):
    """Independent order: X|h first, voltage second, integrate h last.

    Full 16D mean/covariance follow from the affine conditional mean and constant
    conditional covariance. Only three scalar posterior integrals are needed.
    The posterior joint Gaussian kernel is never formed by this oracle.
    """
    validate_kernel(prior)
    m, k = prior.mean, prior.covariance
    v = float(k[H, H])
    require(v > 0, "Integral oracle requires positive h variance")
    A, c, noise, y = observation_arrays(observations)
    COUNTS["oracle_integrals"] += 1
    direction = k[:, H] / v
    retained = [i for i in range(D) if i != H]
    conditional = np.zeros((D, D))
    u = k[retained, H]
    conditional[np.ix_(retained, retained)] = k[np.ix_(retained, retained)] - np.outer(u, u) / v
    # h is exactly fixed GIVEN h; its zero conditional row is an identity,
    # not a zeroing of the physical posterior h variance.
    cross = conditional @ A.T
    T = np.diag(noise) + A @ cross
    chol = np.linalg.cholesky(T)
    whitened = np.linalg.solve(chol, cross.T)
    conditional_after = conditional - whitened.T @ whitened
    gain = np.linalg.solve(chol.T, np.linalg.solve(chol, cross.T)).T
    slope_y = A @ direction
    offset_y = c + A @ (m - direction * m[H])
    inverse_slope = np.linalg.solve(chol.T, np.linalg.solve(chol, slope_y))
    inverse_residual = np.linalg.solve(chol.T, np.linalg.solve(chol, y - offset_y))
    stationary = (m[H] / v + slope_y @ inverse_residual) / (1 / v + slope_y @ inverse_slope)

    def prior_log(h):
        return -0.5 * (LOG_2PI + math.log(v) + (h - m[H]) ** 2 / v)

    def weight_log(h):
        return prior_log(h) + gaussian_log_density(y - offset_y - slope_y * h, chol)

    _, prior_shift = finite_interval_peak(prior_log, float(m[H]))
    prior_integral, prior_error = integrate_scalar(label + ".prior_mass_scaled", lambda h: math.exp(prior_log(h) - prior_shift))
    require(prior_integral > 0, "Nonpositive integrated prior mass")
    log_prior_mass = prior_shift + math.log(prior_integral)
    anchor, shift = finite_interval_peak(weight_log, float(stationary))

    def weight(h):
        return math.exp(weight_log(h) - shift)

    i0, e0 = integrate_scalar(label + ".posterior_mass_scaled", weight)
    i1, e1 = integrate_scalar(label + ".posterior_centered_first_scaled", lambda h: (h - anchor) * weight(h))
    i2, e2 = integrate_scalar(label + ".posterior_centered_second_scaled", lambda h: (h - anchor) ** 2 * weight(h))
    require(i0 > 0, "Nonpositive integrated posterior mass")
    displacement, second = i1 / i0, i2 / i0
    h_variance = second - displacement * displacement
    require(h_variance > 0, "Nonpositive integrated h variance")
    # First-order propagation of quad's reported errors, not a certified enclosure.
    displacement_error = (e1 + abs(displacement) * e0) / i0
    variance_error = (e2 + abs(second) * e0) / i0 + 2 * abs(displacement) * displacement_error
    at_anchor = m + direction * (anchor - m[H])
    mean_anchor = at_anchor + gain @ (y - c - A @ at_anchor)
    slope_after = direction - gain @ slope_y
    mean = mean_anchor + slope_after * displacement
    covariance = conditional_after + np.outer(slope_after, slope_after) * h_variance
    return {"mean": mean, "covariance": covariance,
            "log_evidence": shift + math.log(i0) - log_prior_mass,
            "log_prior_support_mass": log_prior_mass,
            "scalar_h_mean": anchor + displacement, "scalar_h_variance": h_variance,
            "mean_reported_error": np.abs(slope_after) * displacement_error,
            "covariance_reported_error": np.abs(np.outer(slope_after, slope_after)) * variance_error,
            "log_evidence_reported_error": e0 / i0 + prior_error / prior_integral,
            "log_prior_mass_reported_error": prior_error / prior_integral,
            "conditional_covariance_before_voltage": conditional,
            "conditional_covariance_after_voltage": conditional_after,
            "posterior_log_weight_shift": shift, "integration_anchor": anchor,
            "error_semantics": "Quad-reported estimates propagated through ratios; no formal enclosure."}


def compare_oracle(checks, label, result, oracle):
    after = result["posterior_supported"]
    checks.equal(label + ".full_mean", after["mean"], oracle["mean"], norm(oracle["mean_reported_error"]))
    checks.equal(label + ".full_covariance", after["covariance"], oracle["covariance"], norm(oracle["covariance_reported_error"]))
    checks.equal(label + ".log_evidence", result["log_evidence"], oracle["log_evidence"], oracle["log_evidence_reported_error"])
    checks.equal(label + ".prior_log_normalizer", result["prior_supported"]["log_support_mass"],
                 oracle["log_prior_support_mass"], oracle["log_prior_mass_reported_error"])
    checks.psd(label + ".supported_covariance_PSD", after["covariance"])
    checks.psd(label + ".truncation_downdate_PSD", result["posterior_kernel"].covariance - after["covariance"])


def fixture(plan, name):
    p = plan["qualification"][name]
    m, k = np.zeros(D), np.eye(D) * 0.01
    m[Q], m[Z], m[H] = math.log(0.06), 0.5, float(p["h_mean"])
    k[H, H] = float(p["h_variance"])
    if name == "interior":
        k[Z, Z], k[Q, Q] = p["z_variance"], p["q_variance"]
    else:
        k[Z, Z] = 0.1 ** 2 * k[H, H] + 0.0004
        k[Q, Q] = 0.3 ** 2 * k[H, H] + 0.0009
        k[Z, H] = k[H, Z] = 0.1 * k[H, H]
        k[Q, H] = k[H, Q] = -0.3 * k[H, H]
        k[Z, Q] = k[Q, Z] = -0.03 * k[H, H]
    j = np.zeros(D)
    j[Z], j[H] = p["J_z"], p["J_h"]
    return Kernel.create(m, k), observation(j, p["c"], p["R"], p["y"])


def public_start_witness(root, checks):
    text = (root / PUBLIC_SOURCE).read_text()
    def bounds(name):
        found = re.search(r"static const double " + name + r"\[D\]=\{([^}]+)\};", text)
        require(found is not None, "Cannot locate public bounds")
        result = np.array([float(item.strip()) for item in found.group(1).split(",") if item.strip()])
        require(result.shape == (D,), "Public bounds dimensions")
        return result
    lo, hi = bounds("lower"), bounds("upper")
    body = re.search(r"static void public_belief\([^\n]+\)\n\{(.*?)\n\}", text, re.S).group(1)
    root12 = float(re.search(r"root12=([^;]+);", body).group(1))
    mean_H = float(re.search(r"s->mean\[10\]=([^;]+);", body).group(1))
    mean_q = float(re.search(r"s->mean\[5\]=([^;]+);", body).group(1))
    require("memset(s->mean,0," in body and "s->mean[15]=" not in body, "Public h mean initialization changed")
    split = re.search(r"const double alpha=([^,]+),beta=([^;]+);", text)
    alpha, beta = float(split.group(1)), float(split.group(2))
    variance_H, variance_h = ((hi[10] - lo[10]) / root12) ** 2, ((hi[H] - lo[H]) / root12) ** 2
    exact_product_variance = mean_H ** 2 * variance_h + variance_H * variance_h
    linear_product_variance = mean_H ** 2 * variance_h
    omitted = variance_H * variance_h
    # Evaluate the same positive degree-three axis rule on this polynomial ONLY.
    center = np.zeros(D)
    center[10] = mean_H
    diagonal = (hi - lo) / root12
    nodes = np.array([center + sign * 4 * diagonal[column] * np.eye(D)[column]
                      for column in range(D) for sign in (1, -1)])
    products = nodes[:, 10] * nodes[:, H]
    axis_mean = float(products.mean())
    axis_variance = float(((products - axis_mean) ** 2).mean())
    checks.equal("public_product.axis_degree3_variance", axis_variance, linear_product_variance)
    checks.equal("public_product.omitted_fourth_moment", exact_product_variance - axis_variance, omitted)
    checks.condition("public_product.omitted_term_positive", omitted > 0)
    unsplit_sd = (hi[Q] - lo[Q]) / root12
    split_variance = (beta * unsplit_sd) ** 2
    components = []
    for sign in (-1, 1):
        mu = mean_q + sign * alpha * unsplit_sd
        point_reciprocal = math.exp(-mu)
        exact_reciprocal_mean = math.exp(-mu + split_variance / 2)
        exact_reciprocal_variance = math.exp(-2 * mu + split_variance) * math.expm1(split_variance)
        axis_reciprocal_mean = point_reciprocal * (15 + math.cosh(4 * math.sqrt(split_variance))) / 16
        checks.equal("public_logQ.Jensen_ratio." + str(sign), exact_reciprocal_mean / point_reciprocal,
                     math.exp(split_variance / 2))
        checks.condition("public_logQ.strict_Jensen." + str(sign), exact_reciprocal_mean > point_reciprocal)
        components.append({"sign": sign, "kernel_mean_logQ": mu, "kernel_variance_logQ": split_variance,
                           "point_reciprocal_Q_Ah_inverse": point_reciprocal,
                           "exact_Gaussian_reciprocal_mean_Ah_inverse": exact_reciprocal_mean,
                           "exact_Gaussian_reciprocal_variance_Ah_inverse_squared": exact_reciprocal_variance,
                           "linearized_reciprocal_variance_Ah_inverse_squared": point_reciprocal ** 2 * split_variance,
                           "Jensen_mean_increment_Ah_inverse": exact_reciprocal_mean - point_reciprocal,
                           "degree3_axis_reciprocal_mean_Ah_inverse": axis_reciprocal_mean})
    checks.equal("public_split.total_mean", sum(c["kernel_mean_logQ"] for c in components) / 2, mean_q)
    mixture_variance = split_variance + (alpha * unsplit_sd) ** 2
    checks.equal("public_split.total_variance", mixture_variance, unsplit_sd ** 2)
    return {"source": PUBLIC_SOURCE, "anchors": ["public_belief", "split_component"],
            "H_mean": mean_H, "h_mean": 0, "H_variance": variance_H, "h_variance": variance_h,
            "exact_Gaussian_product_mean_V": 0, "exact_Gaussian_product_variance_V2": exact_product_variance,
            "linearized_product_variance_V2": linear_product_variance,
            "degree3_axis_product_variance_V2": axis_variance,
            "omitted_Var_H_times_Var_h_V2": omitted,
            "logQ_split_alpha": alpha, "logQ_split_beta": beta, "components": components,
            "limitations": "Moments of the public unbounded Gaussian laws, not bounded physical priors. Polynomial/reciprocal algebra only; no battery propagation or truth. The degree-three rule does not integrate general fourth moments exactly."}


def run_qualification(root, plan, checks):
    families = {}
    for name in ("interior", "outward"):
        prior, obs = fixture(plan, name)
        before_bytes = prior.bytes()
        result = closed_product(prior, [obs])
        oracle = conditioned_h_oracle(prior, [obs], name)
        compare_oracle(checks, name, result, oracle)
        checks.condition(name + ".prior_unchanged", prior.bytes() == before_bytes)
        families[name] = {"observation": obs, "closed_form": result, "independent_oracle": oracle}
    interior = families["interior"]["closed_form"]
    obs = families["interior"]["observation"]
    p = plan["qualification"]["interior"]
    S = obs["R"] + obs["J"][Z] ** 2 * p["z_variance"]
    expected_z = p["z_mean"] + p["z_variance"] * obs["J"][Z] / S * (obs["y"] - obs["c"] - obs["J"][Z] * p["z_mean"])
    expected_z_variance = p["z_variance"] * obs["R"] / S
    checks.equal("interior.ordinary_z_mean", interior["posterior_supported"]["mean"][Z], expected_z)
    checks.equal("interior.ordinary_z_variance", interior["posterior_supported"]["covariance"][Z, Z], expected_z_variance)
    checks.equal("interior.unchanged_q_mean", interior["posterior_supported"]["mean"][Q], interior["prior_supported"]["mean"][Q])
    checks.equal("interior.unchanged_q_variance", interior["posterior_supported"]["covariance"][Q, Q], interior["prior_supported"]["covariance"][Q, Q])
    checks.equal("interior.unchanged_supported_h_mean", interior["posterior_supported"]["mean"][H], interior["prior_supported"]["mean"][H])
    checks.equal("interior.unchanged_supported_h_variance", interior["posterior_supported"]["covariance"][H, H], interior["prior_supported"]["covariance"][H, H])
    checks.condition("interior.support_ratio_exactly_one", interior["log_normalizer_ratio"] == 0.0)
    outward = families["outward"]["closed_form"]
    checks.condition("outward.kernel_exceeds_upper_bound", outward["posterior_kernel"].mean[H] > UPPER)
    checks.condition("outward.physical_mean_interior_positive_variance",
                     LOWER < outward["posterior_supported"]["mean"][H] < UPPER and outward["posterior_supported"]["covariance"][H, H] > 0)

    no_info = plan["qualification"]["zero_information"]
    zero_obs = observation(np.zeros(D), no_info["c"], no_info["R"], no_info["y"])
    current = outward["posterior_kernel"]
    initial_bytes = current.bytes()
    initial_supported = supported_moments(current)
    zero_records = []
    for repetition in range(no_info["repetitions"]):
        label = "zero_information." + str(repetition + 1)
        result = closed_product(current, [zero_obs])
        oracle = conditioned_h_oracle(current, [zero_obs], label)
        compare_oracle(checks, label, result, oracle)
        checks.condition(label + ".byte_identical_kernel", result["posterior_kernel"].bytes() == initial_bytes)
        checks.condition(label + ".byte_identical_physical_moments",
                         result["posterior_supported"]["mean"].tobytes() == initial_supported["mean"].tobytes()
                         and result["posterior_supported"]["covariance"].tobytes() == initial_supported["covariance"].tobytes())
        expected_log = -0.5 * (LOG_2PI + math.log(no_info["R"]) + (no_info["y"] - no_info["c"]) ** 2 / no_info["R"])
        checks.equal(label + ".constant_log_evidence", result["log_evidence"], expected_log)
        zero_records.append({"closed_form": result, "independent_oracle": oracle})
        current = result["posterior_kernel"]
    negative = supported_moments(Kernel.create(initial_supported["mean"], initial_supported["covariance"]))
    negative_mean_difference = norm(negative["mean"] - initial_supported["mean"])
    negative_covariance_difference = norm(negative["covariance"] - initial_supported["covariance"])
    checks.condition("zero_information.negative_control_changes_law",
                     negative_mean_difference > GAMMA * max(1.0, norm(initial_supported["mean"]))
                     and negative_covariance_difference > GAMMA * max(1.0, norm(initial_supported["covariance"])))
    families["zero_information"] = {"observation": zero_obs, "repetitions": zero_records,
                                     "moment_retruncation_negative_control": {"supported_moments": negative,
                                     "mean_difference_norm": negative_mean_difference,
                                     "covariance_difference_norm": negative_covariance_difference,
                                     "adopted": False}}

    branches = {}
    m, k = np.zeros(D), np.eye(D) * 0.01
    m[H], k[H, H] = 1, 0
    singular = Kernel.create(m, k)
    singular_before = supported_moments(singular)
    singular_after = closed_product(singular, [families["outward"]["observation"]])
    checks.condition("singular.valid_deterministic_h", singular_before["log_support_mass"] == 0
                     and singular_after["posterior_supported"]["mean"][H] == 1
                     and singular_after["posterior_supported"]["covariance"][H, H] == 0)
    rejections = []
    for name, invalid_mean, cross in (("outside", 1.01, 0), ("nonzero_cross_row", 1, 0.001)):
        bad_m, bad_k = m.copy(), k.copy()
        bad_m[H], bad_k[Z, H], bad_k[H, Z] = invalid_mean, cross, cross
        before_count = COUNTS["affine_kernel_products"]
        try:
            closed_product(Kernel.create(bad_m, bad_k), [families["outward"]["observation"]])
        except (InvalidSupport, InvalidKernel) as exc:
            caught = {"type": type(exc).__name__, "reason": str(exc)}
        else:
            caught = None
        checks.condition("singular.reject_" + name + "_before_voltage",
                         caught is not None and COUNTS["affine_kernel_products"] == before_count)
        rejections.append({"name": name, "failure": caught, "likelihood_operations": COUNTS["affine_kernel_products"] - before_count})
    branches["singular_h"] = {"valid_prior": singular_before, "valid_correction": singular_after,
                               "expected_rejections": rejections}

    prior, obs1 = fixture(plan, "outward")
    obs2 = observation(obs1["J"], obs1["c"], obs1["R"], 3.72)
    second = closed_product(outward["posterior_kernel"], [obs2])
    batch = closed_product(prior, [obs1, obs2])
    joint_oracle = conditioned_h_oracle(prior, [obs1, obs2], "two_observations")
    compare_oracle(checks, "two_observations.batch_oracle", batch, joint_oracle)
    checks.equal("two_observations.kernel_mean", second["posterior_kernel"].mean, batch["posterior_kernel"].mean)
    checks.equal("two_observations.kernel_covariance", second["posterior_kernel"].covariance, batch["posterior_kernel"].covariance)
    checks.equal("two_observations.supported_mean", second["posterior_supported"]["mean"], batch["posterior_supported"]["mean"])
    checks.equal("two_observations.supported_covariance", second["posterior_supported"]["covariance"], batch["posterior_supported"]["covariance"])
    checks.equal("two_observations.log_evidence", outward["log_evidence"] + second["log_evidence"], batch["log_evidence"])
    telescoping = outward["log_normalizer_ratio"] + second["log_normalizer_ratio"]
    checks.equal("two_observations.normalizer_telescope", telescoping,
                 second["posterior_supported"]["log_support_mass"] - outward["prior_supported"]["log_support_mass"])
    branches["two_observations"] = {"distinct_observation_ids": [0, 1], "second_observation": obs2,
                                    "sequential_second": second, "batch": batch, "joint_oracle": joint_oracle}

    m, k = np.zeros(D), np.eye(D) * 0.01
    m[H], k[H, H] = 1, 1
    j = np.zeros(D)
    j[H] = 1
    growth = closed_product(Kernel.create(m, k), [observation(j, 0, 1, -1)])
    growth_oracle = conditioned_h_oracle(growth["prior_kernel"], [observation(j, 0, 1, -1)], "variance_growth")
    compare_oracle(checks, "variance_growth", growth, growth_oracle)
    checks.condition("variance_growth.physical_posterior_exceeds_prior",
                     growth["posterior_supported"]["covariance"][H, H] > growth["prior_supported"]["covariance"][H, H])
    checks.condition("variance_growth.still_below_own_kernel",
                     growth["posterior_supported"]["covariance"][H, H] < growth["posterior_kernel"].covariance[H, H])
    branches["physical_variance_growth"] = {"closed_form": growth, "independent_oracle": growth_oracle}

    discrete = []
    for name, points, weights in (("A", [-1 / math.sqrt(2), 1 / math.sqrt(2)], [0.5, 0.5]),
                                 ("B", [-1, 0, 1], [0.25, 0.5, 0.25])):
        x, w = np.array(points), np.array(weights)
        log_terms = np.log(w) - 0.5 * (x / 0.1) ** 2 - math.log(0.1) - 0.5 * LOG_2PI
        log_evidence = float(special.logsumexp(log_terms))
        posterior = np.exp(log_terms - log_evidence)
        prior_mean, posterior_mean = float(w @ x), float(posterior @ x)
        discrete.append({"name": name, "points": x, "prior_weights": w,
                         "prior_mean": prior_mean, "prior_variance": float(w @ (x - prior_mean) ** 2),
                         "posterior_weights": posterior, "posterior_mean": posterior_mean,
                         "posterior_variance": float(posterior @ (x - posterior_mean) ** 2),
                         "log_evidence": log_evidence})
    checks.equal("moment_sufficiency.same_prior_mean", discrete[0]["prior_mean"], discrete[1]["prior_mean"])
    checks.equal("moment_sufficiency.same_prior_variance", discrete[0]["prior_variance"], discrete[1]["prior_variance"])
    checks.equal("moment_sufficiency.posterior_A", discrete[0]["posterior_variance"], 0.5)
    checks.equal("moment_sufficiency.posterior_B", discrete[1]["posterior_variance"], 1 / (math.exp(50) + 1))
    checks.condition("moment_sufficiency.different_posteriors", discrete[0]["posterior_variance"] > discrete[1]["posterior_variance"])
    branches["moment_sufficiency_counterexample"] = discrete
    branches["public_start_algebra"] = public_start_witness(root, checks)
    return {"families": families, "branches": branches}


def serializable(value):
    if isinstance(value, Kernel):
        return serializable(value.record())
    if isinstance(value, dict):
        return {str(k): serializable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serializable(v) for v in value]
    if hasattr(value, "tolist"):
        return serializable(value.tolist())
    if isinstance(value, float) and not math.isfinite(value):
        return {"nonfinite": repr(value)}
    return value


def encode_receipt(result):
    """Resolve the receipt's own decimal byte-count field with a finite bound."""
    for _ in range(5):
        encoded = (json.dumps(serializable(result), separators=(",", ":"), allow_nan=False) + "\n").encode()
        if result["resources"].get("output_bytes") == len(encoded):
            return encoded
        result["resources"]["output_bytes"] = len(encoded)
    raise ReferenceError("Receipt byte-count fixed point did not resolve")


def main():
    global np, scipy, special, integrate
    started, cpu_started = time.monotonic(), time.process_time()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    result = {"schema": "mumble_support_consistent_reference_result_v1", "status": "failed",
              "canonical_data_model_calls": 0, "learner_updates": 0, "source_generations": 0,
              "truth_inputs": 0, "production_source_changes": 0,
              "no_voltage_error_acceptance_cutoff": True,
              "intervals_qualified": False, "hardware_or_coverage_qualified": False}
    identities, checks = {}, None
    try:
        require(Path(__file__).resolve() == root / OWN_SOURCE, "Executing source is outside requested repository")
        for name in (OWN_SOURCE, PLAN, MATH, PUBLIC_SOURCE):
            identities[name] = digest(root / name)
        require(identities[PLAN]["sha256"] == PLAN_SHA256, "Frozen contract SHA256 differs")
        require(identities[PUBLIC_SOURCE]["sha256"] == PUBLIC_SHA256, "Frozen public source SHA256 differs")
        plan = json.loads((root / PLAN).read_text())
        require(plan["numerics"]["reconstruction_operation_budget"] == 16384
                and plan["numerics"]["integration_eps_multiplier"] == 64
                and plan["numerics"]["integration_limit"] == 200, "Frozen numerical settings differ")
        signal.signal(signal.SIGALRM, interrupt_budget)
        signal.signal(signal.SIGXCPU, interrupt_budget)
        signal.setitimer(signal.ITIMER_REAL, max(0.001, 60 - (time.monotonic() - started)))
        old_soft, old_hard = resource.getrlimit(resource.RLIMIT_CPU)
        hard = 31 if old_hard == resource.RLIM_INFINITY else min(old_hard, 31)
        resource.setrlimit(resource.RLIMIT_CPU, (min(30, hard), hard))
        for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
            os.environ[variable] = "1"
        import numpy as np
        import scipy
        from scipy import integrate, special
        result["environment"] = {"python": sys.version, "executable": sys.executable,
                                 "platform": platform.platform(), "numpy": np.__version__,
                                 "scipy": scipy.__version__, "BLAS_thread_limit_environment": 1}
        require(rss_bytes() <= plan["resources"]["reference_RSS_bytes_max"], "RSS exceeds limit after imports")
        checks = Checks()
        result.update(run_qualification(root, plan, checks))
        result["status"] = "passed" if checks.summary()["passed"] else "failed_checks"
    except Exception as exc:
        result["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        result["status"] = "failed"
    finally:
        # A final measured budget gate covers all computation and source checks;
        # the enclosing caller can additionally measure process-close latency.
        signal.setitimer(signal.ITIMER_REAL, 0)
        result["input_identities"] = identities
        after = {}
        try:
            for name, original in identities.items():
                after[name] = digest(root / name)
                if after[name] != original:
                    result["status"] = "failed_input_changed"
            result["input_identities_unchanged"] = after == identities
        except Exception as exc:
            result["status"] = "failed_input_recheck"
            result["input_recheck_error"] = str(exc)
        if checks is not None:
            result["checks"] = checks.summary()
        result["counts"] = COUNTS
        result["quadrature"] = QUADRATURE
        result["numerical_policy"] = {"machine_epsilon": EPS, "gamma_16384": GAMMA,
                                      "quadrature_epsabs": QUAD_EPS, "quadrature_epsrel": QUAD_EPS,
                                      "quadrature_limit": 200, "quad_error_multiplier": 16,
                                      "covariance_clipping": False, "probability_floors": False,
                                      "adaptive_scope_expansion": False,
                                      "error_estimates_are_formal_enclosures": False}
        result["resources"] = {"wall_s_before_final_encoding": time.monotonic() - started,
                               "CPU_s_since_main": time.process_time() - cpu_started,
                               "CPU_s_process_total": time.process_time(), "own_peak_RSS_bytes": rss_bytes(),
                               "scope": "Includes numerical-library imports, qualification and source rechecks; excludes final receipt write latency."}
        limits_pass = (result["resources"]["wall_s_before_final_encoding"] <= 60
                       and result["resources"]["CPU_s_process_total"] <= 30
                       and result["resources"]["own_peak_RSS_bytes"] <= 268435456)
        if not limits_pass:
            result["status"] = "failed_resources"
        result["resources"]["within_recorded_limits"] = limits_pass
        result["decision"] = {"reference": "go" if result["status"] == "passed" else "not_qualified",
                              "streaming_SOC_Q_remedy": "no_go",
                              "reason": "Exact single-h affine conditioning does not recover historical likelihood, full-box support or nonlinear prediction closure."}
        encoded = encode_receipt(result)
        if len(encoded) > 1048576:
            result = {"schema": result["schema"], "status": "failed_output_size",
                      "measured_output_bytes": len(encoded), "input_identities": identities,
                      "resources": result["resources"], "counts": COUNTS,
                      "decision": {"reference": "not_qualified", "streaming_SOC_Q_remedy": "no_go"}}
            encoded = encode_receipt(result)
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    print(json.dumps({"status": result["status"], "output": str(output),
                      "checks": result.get("checks", {}).get("count", 0), "bytes": len(encoded)}))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
