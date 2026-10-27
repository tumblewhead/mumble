#!/usr/bin/env python3
"""Presentation display derivatives of the closed, preserved scored CSV.

No observations, original truth, model, prior, optimizer or interval computation.
The failed reporting receipt is explicit: its numerical export and six figures
closed before an unrelated categorical-axis formatting error. This script does
not change that receipt or rerun its reporting pipeline.
"""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, MaxNLocator

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments/live_anchor_integration_001"
RECEIPT_SHA = "cf525bcf13d85365254b48b458f6fe93b5b730cc9d7c6e641c43f916efa63b0d"
CSV_SHA = "f1bdf31d27132cd9f95760fd98e9eb6721fc7208fc396f74370be3fde6ad259a"
DISPLAY = [("τ₁", "s", 1), ("τ₂", "s", 1), ("τ₃", "s", 1),
           ("γ₊", "Ah⁻¹", 1), ("γ₋", "Ah⁻¹", 1), ("Capacity", "mAh", 1000),
           ("R₀", "mΩ", 1000), ("R₁", "mΩ", 1000), ("R₂", "mΩ", 1000),
           ("R₃", "mΩ", 1000), ("H", "mV", 1000), ("Entering SOC", "%", 100),
           ("Entering v₁", "mV", 1000), ("Entering v₂", "mV", 1000),
           ("Entering v₃", "mV", 1000), ("Entering h", "1", 1)]


def identity(path):
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def main():
    output = EXP / "presentation"
    output.mkdir(exist_ok=False)
    report = EXP / "reporting001"
    receipt_path = report / "reporting_receipt.json"
    assert identity(receipt_path)["sha256"] == RECEIPT_SHA
    receipt = json.loads(receipt_path.read_text())
    assert receipt["status"] == "failed" and receipt["inference_status"] == "completed"
    source = report / "trajectory.csv.gz"
    assert identity(source) == receipt["files"]["trajectory.csv.gz"]
    assert identity(source)["sha256"] == CSV_SHA
    plan_path = EXP / "reporting_plan.json"
    plan = json.loads(plan_path.read_text())
    names = [row["name"] for row in plan["original_quantities"]]
    t = np.empty(31501)
    estimates, references = np.empty((31501, 16)), np.empty((31501, 16))
    soc, soc_reference = np.empty(31501), np.empty(31501)
    with gzip.open(source, "rt", newline="") as stream:
        for k, row in enumerate(csv.DictReader(stream)):
            assert k < len(t) and int(row["next_index"]) == 16 * k
            t[k] = float(row["source_elapsed_s"]) / 3600
            for j, name in enumerate(names):
                estimates[k, j] = float(row[name + "_estimate"])
                references[k, j] = float(row[name + "_truth"])
            soc[k] = float(row["current_SOC_estimate"])
            soc_reference[k] = float(row["current_SOC_truth"])
    assert k + 1 == 31501 and t[0] == 0 and t[-1] == 4
    assert np.isfinite(estimates).all() and np.isfinite(references).all()
    assert np.array_equal(references, np.broadcast_to(references[0], references.shape))
    q_error = 100 * (estimates[:, 5] / references[:, 5] - 1)
    z_error = 100 * (soc - soc_reference)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 14,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.edgecolor": "#B9C6CF", "axes.labelcolor": "#334155",
        "xtick.color": "#475569", "ytick.color": "#475569",
        "grid.color": "#D7E0E5", "grid.alpha": .6, "axes.grid": True,
        "path.simplify": False, "svg.fonttype": "none", "savefig.facecolor": "white"})
    blue, gold = "#126E8A", "#B86B16"
    formatter = FuncFormatter(lambda value, _: f"{value:.3g}")
    files = []

    def save(fig, name):
        for suffix in ("png", "svg"):
            path = output / (name + "." + suffix)
            fig.savefig(path, dpi=160, facecolor="white")
            files.append({"path": path.relative_to(ROOT).as_posix(), **identity(path)})
        plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(16, 4.7))
    for ax, error, title, hard, unit in (
        (axes[0], q_error, "Capacity error", 5., "%"),
        (axes[1], z_error, "Current SOC error", 10., "percentage points")):
        ax.axhspan(-.5, .5, color="#D9EFE8", zorder=0, label="Preferred ±0.5")
        ax.axhline(0, color="#62727E", linewidth=.8)
        for sign in (-1, 1):
            ax.axhline(sign * hard, color="#AD6A52", linewidth=1, linestyle=(0, (2, 3)),
                       label=f"Hard limit ±{hard:g}" if sign == 1 else None)
        ax.plot(t, error, color=blue, linewidth=1.65, label="Saved point error")
        ax.plot(t[0], error[0], marker="o", markersize=5, markerfacecolor="white", color=blue)
        ax.set_title(title, loc="left", fontsize=19, fontweight="bold", color="#173044", pad=14)
        ax.set_ylabel(unit, fontsize=14)
        ax.set_xlabel("Elapsed time (hours)", fontsize=14)
        ax.set_xlim(0, 4)
        ax.set_xticks(range(5))
        ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
        ax.yaxis.set_major_formatter(formatter)
        ax.legend(loc="upper right", fontsize=11, frameon=False)
    fig.subplots_adjust(left=.062, right=.985, bottom=.19, top=.88, wspace=.22)
    save(fig, "slide_capacity_SOC_errors")

    for stem, coordinates in (("slide_parameters_01_08", range(8)),
                              ("slide_parameters_09_16", range(8, 16))):
        fig, axes = plt.subplots(2, 4, figsize=(16, 7.05))
        for ax, j in zip(axes.flat, coordinates):
            label, unit, scale = DISPLAY[j]
            ax.plot(t, estimates[:, j] * scale, color=blue, linewidth=1.4)
            ax.axhline(references[0, j] * scale, color=gold, linewidth=1.4, linestyle=(0, (4, 3)))
            ax.plot(t[0], estimates[0, j] * scale, marker="o", markersize=3.5,
                    markerfacecolor="white", color=blue)
            ax.set_title(f"{j+1}. {label} ({unit})", loc="left", fontsize=13.5,
                         fontweight="bold", color="#173044", pad=10)
            ax.set_xlim(0, 4)
            ax.set_xticks(range(5))
            ax.set_xlabel("Hours", fontsize=12)
            ax.tick_params(labelsize=11.5)
            ax.yaxis.set_major_locator(MaxNLocator(nbins=4))
            ax.yaxis.set_major_formatter(formatter)
        fig.subplots_adjust(left=.052, right=.99, bottom=.09, top=.945, hspace=.55, wspace=.36)
        save(fig, stem)

    metadata = {"schema": "rolling_update_display_derivatives_v1", "status": "completed",
        "purpose": "Slide-readable styles using every saved scored point; numerical sources unchanged.",
        "csv": {"path": source.relative_to(ROOT).as_posix(), **identity(source)},
        "reporting_receipt": {"path": receipt_path.relative_to(ROOT).as_posix(), **identity(receipt_path)},
        "original_reporting_status": "failed categorical-axis formatting; retained CSV and six figures intact",
        "reporting_plan": identity(plan_path), "script": identity(Path(__file__)),
        "points_per_trace": len(t), "time_hours": [float(t[0]), float(t[-1])],
        "smoothing": False, "data_clipping": False, "thresholds": plan["point_error_requirements"],
        "final": {"Q_mAh": float(1000 * estimates[-1, 5]),
                  "Q_relative_error_percent": float(q_error[-1]),
                  "current_SOC_percent": float(100 * soc[-1]),
                  "current_SOC_error_pp": float(z_error[-1])},
        "files": files, "new_raw_truth_reads": 0, "observation_reads": 0,
        "model_prior_optimizer_interval_calls": 0, "no_convergence_or_coverage_claim": True}
    (output / "display_sources.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps({"status": "completed", "files": files, "final": metadata["final"]}))


if __name__ == "__main__":
    main()
