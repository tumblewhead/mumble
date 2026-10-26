#!/usr/bin/env python3
"""Readable display derivative of the completed sensitivity heatmap only.

The frozen original plotter validates input evidence. This wrapper changes
labels and colour normalization, never physics, metrics, or source artifacts.
"""
from __future__ import annotations

import argparse
from copy import copy
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import plot_parameter_sensitivity as base


COLOUR_FLOOR_MV = .001
LABELS = {
    "rest_300s": "Rest\n0 mA\n300 s",
    "weak_300s": "Weak load\n+3 mA\n300 s",
    "load_step_130s": "Load step\n0/+60/0 mA\n10/60/60 s",
    "charge_600s": "Charge\n−30 mA\n600 s",
    "reversal_600s": "Reversal\n+60/−30 mA\n300/300 s",
    "discharge_1800s": "Discharge\n+60 mA\n1800 s",
}
EXPECTED_SEGMENTS = {
    "rest_300s": [(0., 10500)],
    "weak_300s": [(.003, 10500)],
    "load_step_130s": [(0., 350), (.06, 2100), (0., 2100)],
    "charge_600s": [(-.03, 21000)],
    "reversal_600s": [(.06, 10500), (-.03, 10500)],
    "discharge_1800s": [(.06, 63000)],
}


def draw(plt, colors, sensitivity, impact, protocols):
    np = base.np
    maximum = float(max(sensitivity.max(), impact.max()))
    if maximum > COLOUR_FLOOR_MV:
        decade = 10 ** math.floor(math.log10(maximum))
        upper = math.ceil(maximum / decade) * decade
    else:
        upper = COLOUR_FLOOR_MV * 10
    normalization = colors.LogNorm(vmin=COLOUR_FLOOR_MV, vmax=upper, clip=True)
    palette = copy(plt.get_cmap("viridis"))
    palette.set_bad("#e5e7eb")
    fig = plt.figure(figsize=(18, 11.5))
    grid = fig.add_gridspec(1, 3, width_ratios=(1, 1, .04), left=.11, right=.94,
                           bottom=.255, top=.815, wspace=.14)
    axes = [fig.add_subplot(grid[0, 0])]
    axes.append(fig.add_subplot(grid[0, 1], sharey=axes[0]))
    colour_axis = fig.add_subplot(grid[0, 2])
    titles = ["Local sensitivity at ESTIMATED anchor\nDerivative × reference increment",
              "Known error, isolated one coordinate at a time\nEstimate substituted into scoring-truth baseline"]
    for axis, values, title in zip(axes, (sensitivity, impact), titles):
        display = np.ma.masked_where(values == 0, values)
        im = axis.imshow(display, norm=normalization, cmap=palette, interpolation="nearest", aspect="auto")
        axis.set_title(title, fontsize=12, pad=18)
        axis.set_xticks(np.arange(6))
        axis.set_xticklabels([LABELS[p["id"]] for p in protocols], fontsize=9.3, linespacing=1.45)
        axis.set_yticks(np.arange(16))
        axis.set_yticklabels(base.ROW_LABELS, fontsize=11)
        axis.set_xticks(np.arange(-.5, 6, 1), minor=True)
        axis.set_yticks(np.arange(-.5, 16, 1), minor=True)
        axis.grid(which="minor", color="white", linewidth=.6, alpha=.45)
        axis.tick_params(which="both", length=0, pad=8)
        for row in range(16):
            for column in range(6):
                value = float(values[row, column])
                if value == 0:
                    label, ink = "—", "#64748b"
                else:
                    red, green, blue, _ = palette(normalization(value))
                    brightness = .2126 * red + .7152 * green + .0722 * blue
                    label = f"{value:.2e}" if value < COLOUR_FLOOR_MV else f"{value:.3g}"
                    ink = "#111827" if brightness > .55 else "white"
                axis.text(column, row, label, ha="center", va="center", fontsize=9.1, color=ink)
    axes[1].tick_params(labelleft=False)
    ticks = [10. ** exponent for exponent in range(-3, math.floor(math.log10(upper)) + 1)]
    if not math.isclose(ticks[-1], upper):
        ticks.append(upper)
    colourbar = fig.colorbar(im, cax=colour_axis, ticks=ticks)
    colourbar.ax.set_yticklabels(["≤0.001"] + [f"{value:g}" for value in ticks[1:]])
    colourbar.ax.tick_params(labelsize=9)
    colourbar.set_label("Sampled peak |voltage change| (mV) · log colour scale", fontsize=10, labelpad=12)
    fig.suptitle("State-conditioned voltage sensitivity and isolated error impact", fontsize=18, y=.975)
    fig.text(.5, .927, "Saved split-aggregate anchor at 2100 s (35 min) · 16 coordinates × six diagnostic protocols",
             ha="center", fontsize=11, color="#334155")
    fig.text(.5, .17,
             "Slashes denote successive dwell currents and durations. Positive current discharges; negative current charges.\n"
             "Reference increments (left): 1% fractional differential for 11 parameters; 1 SOC percentage point for z; 1 mV for each v; 0.01 for h.",
             ha="center", va="top", fontsize=10, linespacing=1.6, color="#334155")
    fig.text(.5, .102,
             "Colour floor: 0.001 mV = 1 µV. Nonzero values below this floor share the lowest colour; "
             "their numerical values are unmodified and remain annotated.\n"
             "Grey dashes are exact zero. Annotations are rounded display values; all underlying metrics and first figures are preserved.",
             ha="center", va="top", fontsize=10, linespacing=1.6, color="#334155")
    fig.text(.5, .038,
             "Peaks use the full declared 35 Hz diagnostic grid, including the initial point. "
             "State-conditioned forward predictions; no pre-anchor history recomputation.\n"
             "Display-only revision: no model or estimator calls, voltage assimilation, uncertainty-coverage claim, or continuous-time bound.",
             ha="center", va="top", fontsize=9.8, linespacing=1.6, color="#475569")
    return fig, upper


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    primary, output = args.input.resolve(), args.output_dir.resolve()
    if output.exists():
        parser.error("Preserve existing display artifacts; output directory already exists")
    try:
        receipt, _, anchor, protocols, _, _, sensitivity, impact, identity = base.load_evidence(primary)
        base.require([p["id"] for p in protocols] == list(LABELS), "Unexpected protocol order for fixed display labels")
        for protocol in protocols:
            actual = [(segment["current_A"], segment["samples"]) for segment in protocol["segments"]]
            base.require(actual == EXPECTED_SEGMENTS[protocol["id"]], "Protocol differs from its explicit display label")
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.error(str(error))
    os.environ.setdefault("MPLCONFIGDIR", str(base.ROOT / "build" / "matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import colors

    output.mkdir(parents=True, exist_ok=False)
    with plt.rc_context({"font.family": "DejaVu Sans", "svg.fonttype": "none",
                         "axes.spines.top": False, "axes.spines.right": False}):
        figure, upper = draw(plt, colors, sensitivity, impact, protocols)
        artifacts = base.save_figure(figure, output, "voltage_sensitivity_and_error_heatmaps")
        plt.close(figure)
    display = {
        "schema": "mumble_parameter_sensitivity_display_revision_v1", "completed": True,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "input_directory": base.shown_path(primary), "analysis_source_revision": receipt["source_revision"],
        "input_receipt_sha256": identity["receipt_sha256"],
        "input_artifacts_sha256": identity["artifacts_sha256"],
        "base_plotter": {"path": "tools/plot_parameter_sensitivity.py", "sha256": identity["plotter_sha256"],
                         "frozen_by_analysis_receipt": identity["plotter_frozen_by_receipt"]},
        "display_tool": {"path": "tools/plot_parameter_sensitivity_heatmap.py", "sha256": base.sha(Path(__file__).resolve())},
        "anchor_index": anchor["anchor_index"], "anchor_time_s": anchor["anchor_time_s"],
        "column_labels": LABELS, "label_segments_verified_against_saved_protocols": True,
        "colour_mapping": {"scale": "logarithmic", "floor_mV": COLOUR_FLOOR_MV, "ceiling_mV": upper,
                           "clip_below_floor": True, "exact_zero_masked": True,
                           "raw_numerical_annotations_retained": True,
                           "nonzero_cells_below_floor": {"local_sensitivity": int(base.np.count_nonzero((sensitivity > 0) & (sensitivity < COLOUR_FLOOR_MV))),
                                                        "isolated_error": int(base.np.count_nonzero((impact > 0) & (impact < COLOUR_FLOOR_MV)))},
                           "floor_is_physical_or_statistical_bound": False},
        "preservation": {"original_figures_modified": False, "metrics_modified": False,
                         "analysis_model_or_estimator_modified": False, "primary_artifacts_modified": False},
        "scope": "Display-only derivative: shorter protocol labels and clipped colour normalization; original numeric peaks retained. State-conditioned forward predictions, without voltage assimilation or uncertainty-coverage claims.",
        "propagation_calls": 0, "model_calls": 0, "estimator_runs": 0, "optimizer_calls": 0,
        "matplotlib": matplotlib.__version__, "artifacts": artifacts,
    }
    with (output / "display_receipt.json").open("x") as stream:
        json.dump(display, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"completed": True, "display_receipt": base.shown_path(output / "display_receipt.json"),
                      "colour_floor_mV": COLOUR_FLOOR_MV, "colour_ceiling_mV": upper,
                      "below_floor": display["colour_mapping"]["nonzero_cells_below_floor"],
                      "artifacts": artifacts, "model_calls": 0, "estimator_runs": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
