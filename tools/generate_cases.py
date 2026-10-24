#!/usr/bin/env python3
"""Fresh 35 Hz SCM C research campaign; truth never enters estimator input.

At 25 C, voltage is measured at the END of each constant-current interval.
Positive current discharges. This is a synthetic laboratory history, not a
hardware pulse recommendation. All event boundaries align exactly with the
35 Hz sample grid; exact rational durations define the prescribed input.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from fractions import Fraction
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RATE_HZ = 35
SIGMA_V = 0.001
SEEDS = [202610240, 202610241, 202610242]
CHECKPOINTS_S = [10, 40, 220, 400, 600, 900, 1200, 1500, 1800, 2100]
CELLS = {
    "cell_a": {"R0": .12, "R": [.18, .22, .28], "tau": [.05, .5, 5.],
               "H": .025, "gamma_plus": 220., "gamma_minus": 370.,
               "Q_Ah": .060, "z0": .80, "v0": [.003, -.002, .004], "h0": -.45},
    "cell_b": {"R0": .16, "R": [.22, .27, .33], "tau": [.075, .65, 7.5],
               "H": .030, "gamma_plus": 330., "gamma_minus": 500.,
               "Q_Ah": .0647, "z0": .78, "v0": [-.002, .004, .006], "h0": .35},
}


def profile():
    """(current A, exact duration s, semantic label), chronological order."""
    blocks = [(0., Fraction(10), "initial_rest")]
    for k in range(30):
        blocks.extend([(.030, Fraction(2, 7), f"pulse_{k:02d}_low"),
                       (.075, Fraction(1, 7), f"pulse_{k:02d}_high"),
                       (0., Fraction(4, 7), f"pulse_{k:02d}_rest")])
    blocks.extend([
        (.030, Fraction(60), "same_sign_low"),
        (.075, Fraction(60), "same_sign_high"),
        (0., Fraction(60), "rest_after_pair"),
        (.060, Fraction(140), "discharge_before_reversal"),
        (0., Fraction(40), "rest_before_reversal"),
        (-.045, Fraction(240), "first_reversal"),
        (.060, Fraction(180), "return_high"),
        (.045, Fraction(120), "return_medium"),
        (.075, Fraction(120), "discharge_high"),
        (0., Fraction(60), "middle_rest"),
        (.025, Fraction(180), "discharge_low"),
        (-.030, Fraction(140), "second_reversal"),
        (0., Fraction(60), "late_rest"),
        (.060, Fraction(300), "late_discharge"),
        (.003, Fraction(300), "weak_tail"),
    ])
    assert sum((x[1] for x in blocks), Fraction()) == 2100
    return blocks


def samples():
    dt, current, events = [], [], []
    index = 0
    time = Fraction()
    for I, duration, label in profile():
        count_exact = duration * RATE_HZ
        if count_exact.denominator != 1:
            raise ValueError("Input boundary does not align with sample grid")
        count = int(count_exact)
        events.append({"label": label, "start_index": index, "count": count,
                       "start_s": float(time), "end_s": float(time + duration),
                       "current_A": I, "duration_fraction_s": str(duration)})
        dt.extend([1. / RATE_HZ] * count)
        current.extend([I] * count)
        index += count
        time += duration
    return np.asarray(dt), np.asarray(current), events


def ocv(z):
    z = np.asarray(z)
    return 3. + 1.15 * z + .08 * np.tanh(8. * (z - .5))


def simulate(dt, current, p, *, states=False, check_domain=True):
    """Independent vector evaluation at elapsed time within complete dwells.

    This does not call the C model or reproduce its sample-by-sample recurrence.
    Its shape supports any finite number of Foster modes.
    """
    dt, current = np.asarray(dt, float), np.asarray(current, float)
    if dt.ndim != 1 or current.shape != dt.shape or np.any(dt <= 0):
        raise ValueError("Positive one-dimensional intervals required")
    R, tau, v = (np.asarray(p[key], float).copy() for key in ("R", "tau", "v0"))
    if not (len(R) == len(tau) == len(v)) or np.any(tau <= 0) or p["Q_Ah"] <= 0:
        raise ValueError("Invalid Foster dimensions, time constants, or capacity")
    voltage, soc, hyst = (np.empty_like(current) for _ in range(3))
    z, h = float(p["z0"]), float(p["h0"])
    if not len(current):
        return (voltage, soc, hyst) if states else voltage
    starts = np.r_[0, 1 + np.flatnonzero(current[1:] != current[:-1])]
    stops = np.r_[starts[1:], len(current)]
    for a, b in zip(starts, stops):
        I = current[a]
        t = np.cumsum(dt[a:b])
        zz = z - I * t / (3600. * p["Q_Ah"])
        vv = R[:, None] * I + (v - R * I)[:, None] * np.exp(-t[None, :] / tau[:, None])
        if I == 0:
            hh = np.full_like(t, h)
        else:
            target = 1. if I > 0 else -1.
            gamma = p["gamma_plus"] if I > 0 else p["gamma_minus"]
            hh = target + (h - target) * np.exp(-gamma * abs(I) * t / 3600.)
        soc[a:b], hyst[a:b] = zz, hh
        voltage[a:b] = ocv(zz) - p["R0"] * I - np.sum(vv, axis=0) - p["H"] * hh
        z, h, v = float(zz[-1]), float(hh[-1]), vv[:, -1]
    if check_domain and np.any((soc < 0) | (soc > 1)):
        raise ValueError("SOC leaves known OCV domain")
    return (voltage, soc, hyst) if states else voltage


def physical_to_vectors(p):
    return (np.r_[np.log(p["tau"]), np.log(p["gamma_plus"]),
                  np.log(p["gamma_minus"]), p["z0"], np.log(p["Q_Ah"])],
            np.r_[p["R0"], p["R"], p["H"], p["v0"], p["H"] * p["h0"]])


def advance_truth(dt, current, truth):
    """Shift synthetic entering-state truth for scoring a later window only.

    The returned states must never initialize or constrain the estimator.
    Physical parameters and capacity remain unchanged in this campaign.
    """
    p = copy.deepcopy(truth)
    dt, current = np.asarray(dt, float), np.asarray(current, float)
    if not len(dt):
        return p
    v = np.asarray(p["v0"], float)
    R, tau = np.asarray(p["R"]), np.asarray(p["tau"])
    z, h = p["z0"], p["h0"]
    starts = np.r_[0, 1 + np.flatnonzero(current[1:] != current[:-1])]
    stops = np.r_[starts[1:], len(current)]
    for a, b in zip(starts, stops):
        I, duration = float(current[a]), float(dt[a:b].sum())
        e = np.exp(-duration / tau)
        v = R*I + (v-R*I)*e
        z -= I*duration/(3600*p["Q_Ah"])
        if I != 0:
            target = 1. if I > 0 else -1.
            gamma = p["gamma_plus"] if I > 0 else p["gamma_minus"]
            h = target + (h-target)*np.exp(-gamma*abs(I)*duration/3600)
    p.update(z0=float(z), h0=float(h), v0=v.tolist())
    return p


def vectors_to_physical(theta, alpha, n_modes=None):
    theta, alpha = np.asarray(theta, float), np.asarray(alpha, float)
    n = len(theta) - 4 if n_modes is None else n_modes
    if len(theta) != n + 4 or len(alpha) != 2*n + 3:
        raise ValueError("Incompatible parameter vector lengths")
    H, u0 = float(alpha[1+n]), float(alpha[2+2*n])
    return {"R0": float(alpha[0]), "R": alpha[1:1+n].tolist(),
            "tau": np.exp(theta[:n]).tolist(), "H": H,
            "gamma_plus": float(np.exp(theta[n])), "gamma_minus": float(np.exp(theta[n+1])),
            "z0": float(theta[n+2]), "Q_Ah": float(np.exp(theta[n+3])),
            "v0": alpha[2+n:2+2*n].tolist(), "h0": u0 / H if H != 0 else 0.}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "data")
    parser.add_argument("--seeds", type=int, choices=(1, 2, 3), default=3)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    dt, current, events = samples()
    cases = []
    for cell_index, (cell, truth) in enumerate(CELLS.items()):
        clean, soc, hyst = simulate(dt, current, truth, states=True)
        for seed in SEEDS[:args.seeds]:
            stream_seed = seed + 1000 * cell_index
            noise = np.random.default_rng(stream_seed).normal(0., SIGMA_V, len(dt))
            cid = f"{cell}_35hz_s{seed}"
            path = args.output / f"{cid}.csv"
            np.savetxt(path, np.c_[np.arange(len(dt)), dt, current, clean+noise],
                       delimiter=",", header="sample_index,dt_s,current_A,voltage_V",
                       comments="", fmt=["%d", "%.17g", "%.17g", "%.17g"])
            prefix = []
            for seconds in CHECKPOINTS_S:
                n = seconds * RATE_HZ
                prefix.append({"time_s": seconds, "samples": n,
                               "true_current_SOC": float(soc[n-1]),
                               "true_current_h": float(hyst[n-1]),
                               "negative_current_observed": bool(np.any(current[:n] < 0)),
                               "transferred_charge_Ah": float(dt[:n] @ current[:n] / 3600.)})
            cases.append({"case_id": cid, "csv": path.name, "cell": cell,
                          "history": "conditional_learning_35hz", "seed": seed,
                          "stream_seed": stream_seed, "model_match": True,
                          "truth": truth, "n_modes": len(truth["R"]), "n_samples": len(dt),
                          "duration_s": 2100., "net_charge_Ah": float(dt @ current / 3600.),
                          "soc_min": float(soc.min()), "soc_max": float(soc.max()),
                          "soc_final": float(soc[-1]), "prefixes": prefix, "sha256": sha256(path)})
            cases[-1]["weak_tail_truth_start"] = advance_truth(
                dt[:1800*RATE_HZ], current[:1800*RATE_HZ], truth)
            cases[-1]["weak_tail_truth_usage"] = "Scoring only; never an estimator initial state or prior"
    manifest = {
        "schema": "scm_c_cases_v2_35hz_fresh", "generator": "tools/generate_cases.py",
        "sampling_Hz": RATE_HZ, "temperature_C": 25., "sigma_V": SIGMA_V,
        "ocv_kind": "illustrative_known_curve_not_user_measurements",
        "ocv_formula": "3+1.15*z+0.08*tanh(8*(z-0.5))",
        "sample_semantics": "Point voltage at END of constant-current interval; sample i ends at (i+1)/35 s",
        "noise_scope": "iid 1mV per reading at35Hz only; no cross-rate performance inference",
        "checkpoints_s": CHECKPOINTS_S,
        "first_negative_current_onset_s": 400., "first_negative_sample_index": 14000,
        "first_negative_observation_time_s": 400. + 1./35,
        "weak_tail_start_s": 1800., "weak_tail_end_s": 2100.,
        "events": events, "case_count": len(cases), "cases": cases,
        "recovery_notice": "Fresh generated campaign after prior workspace loss; no old raw results reused"
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False)+"\n")
    print(json.dumps({"manifest": str(args.output / "manifest.json"), "cases": len(cases),
                      "samples_per_case": len(dt), "sampling_Hz": RATE_HZ,
                      "first_negative_current_onset_s": 400.,
                      "net_charge_Ah": manifest["cases"][0]["net_charge_Ah"],
                      "SOC_drop_pp": {c["cell"]: 100*(c["truth"]["z0"]-c["soc_final"])
                                      for c in cases if c["seed"] == SEEDS[0]}}))


if __name__ == "__main__":
    main()
