"""Conservative local likelihood diagnostics for the C research estimator.

This module does not produce a posterior, coverage certificate, or optimizer
update. A finite local interval is provisional. Nonlinear profiles and physical
ambiguity checks remain separate. No ground-truth values enter assessment.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np


def default_priors(modes: int, charge_Ah: float = 0.0) -> dict[str, list[float]]:
    """Outer supports matching this version of scm_theta_bounds/linear boxes.

    Current-SOC support uses only the bounds and net charge, so is conservative
    with respect to additional whole-path charge constraints.
    """
    if modes not in (1, 2, 3):
        raise ValueError("modes must be 1, 2 or 3")
    tau = ((.015, .15), (.15, 1.5), (1.5, 30.0)) if modes == 3 else ((.015, 30.0), (.8, 180.0))
    p = {f"tau{i+1}": list(tau[i]) for i in range(modes)}
    p.update({"gamma_plus": [5.0, 1200.0], "gamma_minus": [5.0, 1200.0],
              "z0": [.2, .95], "Q_Ah": [.03, .1], "H": [0.0, .1],
              "R0": [0.0, 1.0], "u0": [-.1, .1], "h0": [-1.0, 1.0]})
    for i in range(modes):
        p[f"R{i+1}"] = [0.0, 1.0]
        p[f"v{i+1}0"] = [-.08, .08]
    possibilities = [z - charge_Ah / q for z in p["z0"] for q in p["Q_Ah"]]
    p["current_soc"] = [max(0.0, min(possibilities)), min(1.0, max(possibilities))]
    return p


def assess_result(result: dict[str, Any], priors: dict[str, list[float]] | None = None,
                  relative_halfwidth: float = .10, soc_halfwidth: float = .05,
                  eigen_rtol: float = 1e-10, null_projection_tol: float = 1e-8,
                  sigma_multiplier: float = 2.0,
                  hysteresis_amplitude_floor_V: float = 1e-8) -> dict[str, Any]:
    """Assess raw scaled joint likelihood curvature without filling null space.

    Coordinate order is theta then alpha. C scales mean x=x_hat+scale*delta,
    and joint_normal is the Gram matrix in delta coordinates, before damping or
    Schur reduction. A target direction with >null_projection_tol of its squared
    normalized length in the numerical null space receives its full support.

    Raw finite intervals are NEVER clipped to bounds to make precision appear
    better. Bounds and optimizer termination are disclosed. A caller may supply
    narrower independently justified supports; truth must never be supplied.
    """
    n = int(result.get("modes", len(result["theta"]) - 4))
    nt, na = n + 4, 2 * n + 3
    dim = nt + na
    if n not in (1, 2, 3):
        raise ValueError("unsupported mode count")
    theta, alpha = np.asarray(result["theta"], dtype=float), np.asarray(result["alpha"], dtype=float)
    scales = np.asarray(result["coordinate_scales"], dtype=float)
    normal = np.asarray(result["joint_normal"], dtype=float)
    if theta.shape != (nt,) or alpha.shape != (na,) or scales.shape != (dim,):
        raise ValueError("coordinate dimensions disagree with mode count")
    if normal.size != dim * dim:
        raise ValueError("joint_normal must be active-dimension packed square matrix")
    normal = normal.reshape(dim, dim)
    if not (np.isfinite(theta).all() and np.isfinite(alpha).all()
            and np.isfinite(scales).all() and np.isfinite(normal).all()):
        raise ValueError("nonfinite coordinates, scales, or likelihood matrix")
    if np.any(scales <= 0):
        raise ValueError("coordinate scales must be positive")
    if not (relative_halfwidth > 0 and soc_halfwidth > 0 and 0 < eigen_rtol < 1
            and 0 < null_projection_tol < 1 and sigma_multiplier > 0):
        raise ValueError("invalid diagnostic thresholds")
    q = float(result.get("charge_Ah", 0.0))
    if not math.isfinite(q):
        raise ValueError("nonfinite charge_Ah")
    support = default_priors(n, q)
    if priors:
        for key, values in priors.items():
            if key not in support or len(values) != 2:
                raise ValueError(f"invalid support for {key}")
            lo, hi = map(float, values)
            if not math.isfinite(lo) or not math.isfinite(hi) or lo > hi:
                raise ValueError(f"invalid finite support for {key}")
            support[key] = [lo, hi]
    sym = (normal + normal.T) * .5
    eig, vectors = np.linalg.eigh(sym)
    largest = max(0.0, float(eig[-1]))
    cutoff = largest * eigen_rtol
    positive = eig > cutoff
    numerical_null = vectors[:, ~positive]
    negative_invalid = bool(np.any(eig < -max(cutoff, 1e-12)))
    asymmetry = float(np.max(np.abs(normal - normal.T))) / max(largest, 1.0)
    matrix_invalid = negative_invalid or asymmetry > 1e-8
    covariance = ((vectors[:, positive] / eig[positive]) @ vectors[:, positive].T
                  if np.any(positive) else np.zeros_like(sym))
    optimizer_ok = int(result.get("status", 1)) == 0
    active_bounds = int(result.get("active_linear_constraints", 0)) + int(result.get("active_outer_bounds", 0))
    unexcited = int(result.get("unexcited_theta_mask", 0))
    fixed_mask = int(result.get("fixed_mask", 0))
    fixed_alpha_mask = int(result.get("fixed_alpha_mask", 0))
    linked_chart = bool(result.get("has_current_soc", False) or result.get("fixed_current_soc") is not None)
    any_conditioning = bool(fixed_mask or fixed_alpha_mask or linked_chart)
    parameters: dict[str, dict[str, Any]] = {}

    def diagnose(name: str, point: float, gradient: np.ndarray, units: str,
                 threshold: str | None, log_coordinate: bool = False,
                 explicitly_unexcited: bool = False,
                 forced_reason: str | None = None) -> dict[str, Any]:
        point = float(point)
        norm2 = float(gradient @ gradient)
        null_fraction = (float(np.sum((numerical_null.T @ gradient) ** 2)) / norm2 if norm2 else 1.0)
        null_fraction = min(1.0, max(0.0, null_fraction))
        local = None
        standard_deviation = None
        half = None
        ratio = None
        passes: bool | None = None
        reasons: list[str] = []
        structural_null = null_fraction > null_projection_tol
        if linked_chart:
            reasons.append("This matrix uses a fixed-current-SOC derivative chart; unrestricted target intervals are not inferred from it.")
        elif forced_reason:
            reasons.append(forced_reason)
        elif matrix_invalid:
            reasons.append("Likelihood matrix is materially indefinite or asymmetric; local inversion is not trusted.")
        elif explicitly_unexcited:
            reasons.append("The retained history supplies no excitation for this direction; support is retained.")
        elif structural_null:
            reasons.append("Target has a component in the numerical likelihood null space; no pseudoinverse interval is reported.")
        else:
            variance = max(0.0, float(gradient @ covariance @ gradient))
            coordinate_sd = math.sqrt(variance)
            if log_coordinate:
                radius = sigma_multiplier * coordinate_sd
                try:
                    local = [point * math.exp(-radius), point * math.exp(radius)]
                except OverflowError:
                    local = None
                standard_deviation = point * coordinate_sd
            else:
                standard_deviation = coordinate_sd
                radius = sigma_multiplier * coordinate_sd
                local = [point - radius, point + radius]
            if local is None or not all(math.isfinite(v) for v in local):
                reasons.append("Local approximation has an unbounded numerical range; full support is retained.")
                local = None
            else:
                half = max(point - local[0], local[1] - point)
                ratio = half / abs(point) if point != 0 else None
                if threshold == "relative":
                    passes = ratio is not None and ratio <= relative_halfwidth
                elif threshold == "soc":
                    passes = half <= soc_halfwidth
                if passes is False:
                    reasons.append("Finite local range exceeds the declared precision threshold.")
                elif passes is True:
                    reasons.append("Local range passes the precision screen; nonlinear profile confirmation is still required.")
                else:
                    reasons.append("Finite local diagnostic; no precision threshold is declared for this nuisance coordinate.")
                if local[0] < support[name][0] or local[1] > support[name][1]:
                    reasons.append("Raw local range crosses supplied support; it has not been clipped to improve precision.")
        if not optimizer_ok:
            reasons.append("Optimizer did not report convergence; the point remains visible but its local interval is untrusted.")
        if active_bounds:
            reasons.append("Active constraints make this an interior Gaussian approximation at a constrained point; require a profile check.")
        if any_conditioning:
            reasons.append("Some coordinates were fixed in this fit; conditional optimization is not independent identification.")
        unavailable = bool(linked_chart or forced_reason or matrix_invalid or explicitly_unexcited or structural_null or local is None or not optimizer_ok)
        status = ("unexcited" if explicitly_unexcited and not matrix_invalid and not forced_reason and not linked_chart else
                  "unresolved" if unavailable or passes is False else "provisional")
        item = {
            "point": float(point), "units": units, "local_range": support[name][:] if unavailable else local,
            "range_kind": "prior_support" if unavailable else "untruncated_local_two_sigma",
            "prior_support": support[name][:], "status": status, "reason": " ".join(reasons),
            "passes_local_precision": bool(passes) if passes is not None and not unavailable else (False if unavailable else None),
            "eligible_for_profile_check": bool(not unavailable and passes is True),
            "null_projection": null_fraction, "local_standard_deviation": None if unavailable else standard_deviation,
            "local_halfwidth": None if unavailable else half, "relative_halfwidth": None if unavailable else ratio,
            "active_constraints_present": bool(active_bounds), "conditioned_fit": any_conditioning,
        }
        parameters[name] = item
        return item

    for i in range(n):
        g = np.zeros(dim);g[i] = scales[i]
        diagnose(f"tau{i+1}", math.exp(theta[i]), g, "s", "relative", True, bool(unexcited & (1 << i)))
    for key, index in (("gamma_plus", n), ("gamma_minus", n + 1), ("Q_Ah", n + 3)):
        g = np.zeros(dim);g[index] = scales[index]
        diagnose(key, math.exp(theta[index]), g, "1/Ah" if key.startswith("gamma") else "Ah", "relative", True,
                 bool(unexcited & (1 << index)))
    g = np.zeros(dim);g[n+2] = scales[n+2]
    diagnose("z0", theta[n+2], g, "SOC fraction", "soc", explicitly_unexcited=bool(unexcited & (1 << (n+2))))
    linear = [("R0", 0, "ohm", "relative")]
    linear += [(f"R{i+1}", 1+i, "ohm", "relative") for i in range(n)]
    linear += [("H", 1+n, "V", "relative")]
    linear += [(f"v{i+1}0", 2+n+i, "V", None) for i in range(n)]
    linear += [("u0", 2+2*n, "V", None)]
    for name, aindex, units, threshold in linear:
        index = nt + aindex;g = np.zeros(dim);g[index] = scales[index]
        no_signal = bool(sym[index, index] == 0.0)
        diagnose(name, alpha[aindex], g, units, threshold, explicitly_unexcited=no_signal)
    Q = math.exp(theta[n+3]);g = np.zeros(dim)
    g[n+2] = scales[n+2];g[n+3] = (q / Q) * scales[n+3]
    diagnose("current_soc", theta[n+2] - q/Q, g, "SOC fraction", "soc")
    H, u0 = float(alpha[1+n]), float(alpha[2+2*n])
    hpoint = u0/H if H > hysteresis_amplitude_floor_V else 0.0
    g = np.zeros(dim)
    hreason = None
    if H <= hysteresis_amplitude_floor_V:
        hreason = "Hysteresis amplitude is at or near zero, so h0 is not separately determined."
    elif parameters["H"]["range_kind"] == "untruncated_local_two_sigma" and parameters["H"]["local_range"][0] <= 0:
        hreason = "The local amplitude range reaches zero; division by H cannot give a supported h0 interval."
    else:
        g[nt+1+n] = -u0/(H*H) * scales[nt+1+n]
        g[nt+2+2*n] = scales[nt+2+2*n]/H
    diagnose("h0", hpoint, g, "dimensionless", None, forced_reason=hreason)
    if H <= hysteresis_amplitude_floor_V:
        parameters["h0"]["point"] = None
    return {
        "schema": "scm_local_assessment_v1", "diagnostic_only": True,
        "coverage_certificate": False, "modes": n, "joint_dimension": dim,
        "numerical_rank": int(np.count_nonzero(positive)), "eigenvalues": eig.tolist(),
        "eigen_cutoff": cutoff, "eigen_relative_cutoff": eigen_rtol,
        "null_projection_tolerance": null_projection_tol, "matrix_invalid": matrix_invalid,
        "matrix_relative_asymmetry": asymmetry, "sigma_multiplier": sigma_multiplier,
        "joint_matrix_chart": "fixed_current_soc_constrained" if linked_chart else "original_coordinates",
        "thresholds": {"relative_halfwidth": relative_halfwidth, "soc_halfwidth_fraction": soc_halfwidth},
        "optimizer_status": int(result.get("status", 1)), "termination_reason": result.get("termination_reason"),
        "projected_gradient": result.get("projected_gradient"), "active_constraints": active_bounds,
        "charge_Ah": q, "parameters": parameters,
        "method": "Undamped joint likelihood linearization; null directions retain support, positive eigendirections give provisional local ranges.",
        "caveats": ["No prior precision is inserted into the likelihood matrix.",
                    "Noise scaling is inherited from the C matrix; residual RMSE does not renormalize it.",
                    "Two-sigma local ranges are not nonlinear confidence or coverage certificates.",
                    "This is a reporting diagnostic, not natural-gradient estimation or an optimizer metric.",
                    "Carried learning tags must come from the runner's retained history; this function never fabricates age or interval shrinkage."],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    assessment = assess_result(json.loads(args.result.read_text()))
    text = json.dumps(assessment, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
