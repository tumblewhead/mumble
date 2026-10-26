#!/usr/bin/env python3
"""Plot completed state-conditioned sensitivity evidence without running physics.

Heatmap peaks come from results.json, which uses the complete diagnostic grid.
Curves come only from the saved, thinned profiles.npz display views. This module
does not import the analysis/model implementation or assimilate observations.
"""
from __future__ import annotations

import argparse
from copy import copy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import textwrap

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
COORDINATES = [
    "log_tau1", "log_tau2", "log_tau3", "log_gamma_plus", "log_gamma_minus",
    "log_Q_Ah", "R0", "R1", "R2", "R3", "H", "current_z",
    "current_v1", "current_v2", "current_v3", "current_h",
]
ROW_LABELS = [
    r"$\tau_1$", r"$\tau_2$", r"$\tau_3$", r"$\gamma_+$", r"$\gamma_-$",
    r"$Q$", r"$R_0$", r"$R_1$", r"$R_2$", r"$R_3$", r"$H$",
    r"Entering SOC $z$", r"Entering $v_1$", r"Entering $v_2$",
    r"Entering $v_3$", r"Entering $h$",
]
PROFILE_KEYS = (
    "indices", "time_s", "joint_error_V", "sum_isolated_errors_V",
    "linear_joint_error_V",
)
FINAL_INDEX = 73500
FINAL_TIME_S = 2100
RATE_HZ = 35


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def strict_json(path: Path):
    def reject(value):
        raise ValueError("Nonfinite JSON token in " + str(path) + ": " + value)
    return json.loads(path.read_text(), parse_constant=reject)


def require(condition, message: str) -> None:
    if not condition:
        raise ValueError(message)


def shown_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def protocol_name(protocol: dict) -> str:
    return str(protocol.get("label") or protocol.get("name") or
               protocol["id"].replace("_", " "))


def protocol_seconds(protocol: dict) -> float:
    return sum(segment["samples"] for segment in protocol["segments"]) / RATE_HZ


def protocol_current_note(protocol: dict) -> str:
    currents = [segment["current_A"] * 1000 for segment in protocol["segments"]]
    if len(currents) <= 3:
        return " → ".join(f"{value:+g}" for value in currents) + " mA"
    return f"{len(currents)} dwells; {min(currents):+g} to {max(currents):+g} mA"


def nonnegative_peak(row: dict, field: str) -> float:
    value = row[field]["peak_abs"]
    require(isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value >= 0,
            "Invalid stored peak: " + row["coordinate"] + ": " + field)
    return float(value)


def load_evidence(primary: Path):
    """Validate provenance and array shape; do not recompute model metrics."""
    receipt_path = primary / "receipt.json"
    receipt = strict_json(receipt_path)
    require(receipt.get("schema") == "mumble_parameter_sensitivity_receipt_v1",
            "Unexpected sensitivity receipt schema")
    require(receipt.get("completed") is True and bool(receipt.get("finished_utc")),
            "Sensitivity analysis must be completed before plotting")
    require(receipt.get("all_domains_passed") is True,
            "Completed analysis must report valid prediction domains")
    artifacts = receipt.get("artifacts_sha256", {})
    require("results.json" in artifacts and "profiles.npz" in artifacts,
            "Receipt must bind results.json and profiles.npz")
    for name, expected in artifacts.items():
        candidate = (primary / name).resolve()
        try:
            candidate.relative_to(primary)
        except ValueError as error:
            raise ValueError("Artifact path leaves input directory: " + name) from error
        require(candidate.is_file() and sha(candidate) == expected,
                "Sensitivity artifact hash mismatch: " + name)
    own_name = "tools/plot_parameter_sensitivity.py"
    own_hash = sha(Path(__file__).resolve())
    frozen_plot_hash = receipt.get("source_sha256", {}).get(own_name)
    if frozen_plot_hash is not None:
        require(frozen_plot_hash == own_hash, "Plotter differs from frozen analysis source")
    results = strict_json(primary / "results.json")
    require(results.get("schema") == "mumble_parameter_sensitivity_results_v1",
            "Unexpected sensitivity results schema")
    require(results.get("source_revision") == receipt.get("source_revision")
            and bool(receipt.get("source_revision")), "Result source revision mismatch")
    require(results.get("coordinate_names") == COORDINATES,
            "Unexpected coordinate order")
    require(len(results.get("reference_unit", [])) == len(COORDINATES),
            "Missing coordinate reference-unit declarations")
    anchors = results.get("anchors", [])
    require(bool(anchors) and anchors[-1].get("anchor_index") == FINAL_INDEX,
            "Profiles must refer to the final 2100 s anchor")
    anchor = anchors[-1]
    require(anchor.get("anchor_time_s") == FINAL_TIME_S
            and sum(a.get("anchor_index") == FINAL_INDEX for a in anchors) == 1,
            "Expected one final anchor at sample 73500 / 2100 s")
    protocols = results.get("protocols", [])
    require(len(protocols) == 6, "Expected six frozen diagnostic protocols")
    ids = [protocol["id"] for protocol in protocols]
    require(all(isinstance(name, str) and name for name in ids) and len(set(ids)) == 6,
            "Protocol IDs must be six distinct nonempty strings")
    for protocol in protocols:
        segments = protocol.get("segments", [])
        require(bool(segments), "Empty protocol: " + protocol["id"])
        for segment in segments:
            count = segment["samples"]
            current = segment["current_A"]
            require(isinstance(count, int) and not isinstance(count, bool) and count > 0
                    and isinstance(current, (int, float)) and not isinstance(current, bool)
                    and math.isfinite(current), "Invalid declared protocol dwell")
    records = anchor.get("protocol_results", [])
    require(len(records) == 6 and {r["protocol"] for r in records} == set(ids),
            "Final anchor protocol results do not match the declared protocols")
    by_protocol = {record["protocol"]: record for record in records}
    sensitivity = np.empty((16, 6))
    impact = np.empty((16, 6))
    profiles = {}
    with np.load(primary / "profiles.npz", allow_pickle=False) as stored:
        for column, protocol in enumerate(protocols):
            name = protocol["id"]
            record = by_protocol[name]
            rows = record["coordinates"]
            require([row["coordinate"] for row in rows] == COORDINATES,
                    "Coordinate order mismatch in protocol " + name)
            sensitivity[:, column] = [nonnegative_peak(row, "unit_sensitivity_at_estimate_mV") for row in rows]
            impact[:, column] = [nonnegative_peak(row, "isolated_actual_error_mV") for row in rows]
            expected_samples = sum(s["samples"] for s in protocol["segments"])
            require(record["samples"] == expected_samples,
                    "Result duration differs from protocol " + name)
            profile = {key: np.asarray(stored[name + "__" + key]) for key in PROFILE_KEYS}
            time_s = profile["time_s"]
            indices = profile["indices"]
            require(time_s.ndim == 1 and len(time_s) >= 2
                    and all(array.shape == time_s.shape and np.all(np.isfinite(array))
                            for array in profile.values()),
                    "Invalid display-profile shape or values: " + name)
            require(np.issubdtype(indices.dtype, np.integer) and indices[0] == 0
                    and indices[-1] == expected_samples and np.all(np.diff(indices) > 0)
                    and np.all(np.diff(time_s) > 0)
                    and np.allclose(time_s, indices / RATE_HZ, rtol=0, atol=1e-9),
                    "Display profile does not match the declared sample grid: " + name)
            profiles[name] = profile
    return receipt, results, anchor, protocols, by_protocol, profiles, sensitivity, impact, {
        "receipt_sha256": sha(receipt_path), "artifacts_sha256": artifacts,
        "plotter_sha256": own_hash, "plotter_frozen_by_receipt": frozen_plot_hash is not None,
    }


def heatmap_figure(plt, colors, protocols, sensitivity, impact):
    fig = plt.figure(figsize=(17.2, 11.2))
    grid = fig.add_gridspec(1, 3, width_ratios=(1, 1, .045), left=.105,
                           right=.94, bottom=.23, top=.82, wspace=.17)
    axes = [fig.add_subplot(grid[0, 0])]
    axes.append(fig.add_subplot(grid[0, 1], sharey=axes[0]))
    color_axis = fig.add_subplot(grid[0, 2])
    positive = np.r_[sensitivity[sensitivity > 0], impact[impact > 0]]
    low, high = (float(positive.min()), float(positive.max())) if len(positive) else (1e-6, 1.)
    if low == high:
        low, high = low / 10, high * 10
    normalization = colors.LogNorm(vmin=low, vmax=high)
    palette = copy(plt.get_cmap("viridis"))
    palette.set_bad("#e5e7eb")
    labels = [textwrap.fill(protocol_name(p), width=18) + f"\n{protocol_seconds(p):g} s"
              for p in protocols]
    titles = ["Local sensitivity at ESTIMATED anchor\nDerivative × declared reference increment",
              "Known estimation error, one coordinate at a time\nEstimate substituted into scoring-truth baseline"]
    for axis, values, title in zip(axes, (sensitivity, impact), titles):
        display = np.ma.masked_where(values == 0, values)
        im = axis.imshow(display, cmap=palette, norm=normalization, interpolation="nearest", aspect="auto")
        axis.set_title(title, fontsize=12, pad=18)
        axis.set_xticks(np.arange(6))
        axis.set_xticklabels(labels, fontsize=9, linespacing=1.3)
        axis.set_yticks(np.arange(16))
        axis.set_yticklabels(ROW_LABELS, fontsize=11)
        axis.set_xticks(np.arange(-.5, 6, 1), minor=True)
        axis.set_yticks(np.arange(-.5, 16, 1), minor=True)
        axis.grid(which="minor", color="white", linewidth=.6, alpha=.45)
        axis.tick_params(which="both", length=0, pad=7)
        for row in range(16):
            for column in range(6):
                value = float(values[row, column])
                if value == 0:
                    label, ink = "—", "#64748b"
                else:
                    red, green, blue, _ = palette(normalization(value))
                    brightness = .2126 * red + .7152 * green + .0722 * blue
                    label, ink = f"{value:.3g}", ("#111827" if brightness > .55 else "white")
                axis.text(column, row, label, ha="center", va="center", color=ink, fontsize=8.8)
    axes[1].tick_params(labelleft=False)
    colorbar = fig.colorbar(im, cax=color_axis)
    colorbar.set_label("Sampled peak |voltage change| (mV) · logarithmic colour", fontsize=10, labelpad=12)
    colorbar.ax.tick_params(labelsize=9)
    fig.suptitle("State-conditioned voltage sensitivity and isolated error impact", fontsize=18, y=.975)
    fig.text(.5, .925, "Saved split-aggregate anchor at 2100 s (35 min) · 16 coordinates × six diagnostic protocols",
             ha="center", fontsize=11, color="#334155")
    fig.text(.5, .125,
             "Left reference increments: 1% fractional differential for the 11 parameters; "
             "1 SOC percentage point for z; 1 mV for each v; 0.01 for h.\n"
             "Right: finite, known post-inference errors. Shared colour scale is in mV; grey dashes are exact zero; annotations are rounded.",
             ha="center", va="top", fontsize=10, linespacing=1.6, color="#334155")
    fig.text(.5, .048,
             "Peaks use the full declared 35 Hz diagnostic grid, including the initial point. "
             "Pre-anchor history is not recomputed.\n"
             "These are forward model diagnostics: no voltage assimilation, uncertainty coverage, or continuous-time bound is claimed.",
             ha="center", va="top", fontsize=10, linespacing=1.6, color="#475569")
    return fig


def joint_figure(plt, ticker, protocols, by_protocol, profiles):
    fig, axes = plt.subplots(2, 3, figsize=(17.2, 10.3))
    fig.subplots_adjust(left=.07, right=.975, bottom=.19, top=.81, wspace=.26, hspace=.48)
    styles = [
        ("joint_error_V", "Joint error: all estimated coordinates", "#124e78", "-", 2.2),
        ("sum_isolated_errors_V", "Sum of exact one-coordinate errors", "#c45a11", "--", 1.9),
        ("linear_joint_error_V", "First order: J at truth × native error", "#7e469e", ":", 2.1),
    ]
    for axis, protocol in zip(axes.flat, protocols):
        name = protocol["id"]
        profile = profiles[name]
        axis.axhline(0, color="#94a3b8", linewidth=.8)
        for field, label, colour, style, width in styles:
            axis.plot(profile["time_s"], 1000 * profile[field], label=label,
                      color=colour, linestyle=style, linewidth=width)
        title = textwrap.fill(protocol_name(protocol), width=34)
        axis.set_title(title + "\n" + protocol_current_note(protocol), fontsize=11, pad=10)
        axis.set_xlim(0, protocol_seconds(protocol))
        axis.xaxis.set_major_locator(ticker.MaxNLocator(5))
        axis.yaxis.set_major_locator(ticker.MaxNLocator(5))
        axis.tick_params(labelsize=9)
        axis.grid(alpha=.2)
        axis.set_xlabel("Time after saved anchor (s)", fontsize=10)
        axis.set_ylabel("Signed voltage error (mV)", fontsize=10)
        peak = by_protocol[name]["joint_voltage_error_mV"]["peak_abs"]
        require(isinstance(peak, (int, float)) and math.isfinite(peak) and peak >= 0,
                "Invalid stored joint peak: " + name)
        axis.text(.98, .04, f"Sampled joint |peak|: {peak:.3g} mV", transform=axis.transAxes,
                  ha="right", va="bottom", fontsize=8.5,
                  bbox={"facecolor": "white", "edgecolor": "none", "alpha": .85, "pad": 3})
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(.5, .91),
               ncol=3, frameon=False, fontsize=10, handlelength=3)
    fig.suptitle("Joint voltage error, isolated-error sum, and first-order prediction", fontsize=18, y=.98)
    fig.text(.5, .936, "Saved split-aggregate anchor at 2100 s · six state-conditioned future diagnostic protocols",
             ha="center", fontsize=11, color="#334155")
    fig.text(.5, .105,
             "Signed joint error = predicted voltage from the complete saved estimate − predicted voltage from scoring truth.\n"
             "One-coordinate errors replace one truth coordinate with its estimate; their sum is not an error bound. "
             "The first-order curve uses the truth-anchor Jacobian.",
             ha="center", va="top", fontsize=10, color="#334155", linespacing=1.6)
    fig.text(.5, .04,
             "Lines connect the supplied thinned display samples; peak labels use the full 35 Hz metric grid. "
             "Each panel has its own y scale.\n"
             "No voltage assimilation or parameter re-estimation occurs. These curves do not establish uncertainty coverage.",
             ha="center", va="top", fontsize=10, color="#475569", linespacing=1.6)
    return fig


def save_figure(fig, output: Path, stem: str) -> dict:
    artifacts = {}
    for suffix in ("png", "svg"):
        path = output / (stem + "." + suffix)
        fig.savefig(path, dpi=180, facecolor="white")
        artifacts[path.name] = {"sha256": sha(path), "bytes": path.stat().st_size}
    return artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", dest="primary", type=Path, required=True,
                        help="Completed sensitivity primary directory")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="New directory for PNG/SVG figures and figures.json")
    args = parser.parse_args()
    primary, output = args.primary.resolve(), args.output_dir.resolve()
    if output.exists():
        parser.error("Preserve first figures; output directory already exists")
    try:
        receipt, results, anchor, protocols, by_protocol, profiles, sensitivity, impact, identity = load_evidence(primary)
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.error(str(error))
    os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "build" / "matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import colors, ticker

    output.mkdir(parents=True, exist_ok=False)
    artifacts = {}
    with plt.rc_context({"font.family": "DejaVu Sans", "svg.fonttype": "none",
                         "axes.spines.top": False, "axes.spines.right": False}):
        fig = heatmap_figure(plt, colors, protocols, sensitivity, impact)
        artifacts.update(save_figure(fig, output, "voltage_sensitivity_and_error_heatmaps"))
        plt.close(fig)
        fig = joint_figure(plt, ticker, protocols, by_protocol, profiles)
        artifacts.update(save_figure(fig, output, "joint_voltage_error_profiles"))
        plt.close(fig)
    manifest = {
        "schema": "mumble_parameter_sensitivity_figures_v1", "completed": True,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "input_directory": shown_path(primary), "source_revision": receipt["source_revision"],
        **identity, "numpy": np.__version__, "matplotlib": matplotlib.__version__,
        "anchor_index": anchor["anchor_index"], "anchor_time_s": anchor["anchor_time_s"],
        "coordinate_order": COORDINATES, "reference_units": results["reference_unit"],
        "protocol_order": [protocol["id"] for protocol in protocols],
        "heatmap_values": {
            "left": "Stored unit_sensitivity_at_estimate_mV.peak_abs; estimated anchor only",
            "right": "Stored isolated_actual_error_mV.peak_abs; known finite error at truth baseline",
            "scale": "Shared logarithmic mV colour scale; exact zeros masked; rounded annotations",
            "peak_scope": "Full declared 35 Hz sample grid including initial point; not peaks of the thinned plot views",
        },
        "profile_values": {
            "source": "Only supplied profiles.npz arrays, converted from V to mV",
            "curves": ["joint_error_V", "sum_isolated_errors_V", "linear_joint_error_V"],
            "first_order_anchor": "scoring truth",
            "sum_of_isolated_errors_is_bound": False,
            "sum_absolute_isolated_errors_plotted": False,
            "display_scope": receipt.get("profile_scope"),
        },
        "scope": "State-conditioned future model predictions from saved entering states. No pre-anchor history recomputation, voltage assimilation, estimator call, or uncertainty-coverage claim.",
        "physics_or_metric_recalculation": False, "propagation_calls": 0,
        "estimator_runs": 0, "optimizer_calls": 0, "completed_study_reruns": 0,
        "artifacts": artifacts,
    }
    with (output / "figures.json").open("x") as stream:
        json.dump(manifest, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"completed": True, "figures_json": shown_path(output / "figures.json"),
                      "artifacts": list(artifacts), "propagation_calls": 0, "estimator_runs": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
