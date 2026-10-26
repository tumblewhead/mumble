#!/usr/bin/env python3
"""Plot only the completed, independently reduced historical control."""

import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/mumble-historical-matplotlib")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "summary.json"
summary = json.loads(SOURCE.read_text())
assert summary["coverage_validated"] is False
free = next(row for row in summary["fits"] if row["id"] == "free")
online = next(row for row in summary["online"]["entities"] if row["entity"] == "aggregate")
precision = summary["free_local_precision"]
truth = summary["truth"]

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 11,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.spines.left": False, "axes.edgecolor": "#c2cbd2",
    "axes.labelcolor": "#344554", "text.color": "#182b3a",
    "xtick.color": "#536675", "ytick.color": "#344554",
    "figure.facecolor": "white", "axes.facecolor": "white",
})
fig, axes = plt.subplots(2, 2, figsize=(11.8, 7.2),
                         gridspec_kw={"height_ratios": [1, 1]})
fig.subplots_adjust(left=.16, right=.97, top=.79, bottom=.21,
                    wspace=.37, hspace=.75)
fig.suptitle("Reevaluating history changes the center", x=.055, y=.97,
             ha="left", fontsize=21, fontweight="bold")
fig.text(.055, .905,
         "Same 252,000 observations at 7,200 seconds · errors relative to archived truth",
         fontsize=12, color="#536675")
colors = {"recursive": "#c86b39", "history": "#11677d"}

specs = [
    {"key": "Q_Ah", "field": "capacity_Ah", "truth": truth["capacity_Ah"],
     "scale": 1000., "label": "Capacity error (mAh)",
     "overall": (-.08, 1.39), "zoom": (-.010, .018)},
    {"key": "SOC", "field": "current_soc", "truth": truth["SOC"],
     "scale": 100., "label": "SOC error (percentage points)",
     "overall": (-.292, .018), "zoom": (-.0065, .0022)},
]

def draw(ax, spec, zoom):
    ax.axvline(0, color="#283c4b", linewidth=1.25, linestyle=(0, (4, 3)), zorder=1)
    ax.grid(axis="x", color="#e8edf0", linewidth=.8, zorder=0)
    rows = [("Historical refit", free, precision["local_two_SD_intervals"],
             0, colors["history"])]
    if not zoom:
        rows.insert(0, ("Saved recursive", online, online["local_two_SD_intervals"],
                        1, colors["recursive"]))
    for label, record, ranges, y, color in rows:
        center = (record[spec["field"]] - spec["truth"]) * spec["scale"]
        low, high = [(value-spec["truth"])*spec["scale"] for value in ranges[spec["key"]]]
        ax.errorbar(center, y, xerr=[[center-low], [high-center]], fmt="o",
                    color=color, ecolor=color, markersize=7, elinewidth=4,
                    capsize=7, capthick=1.5, zorder=4)
        if not zoom:
            alignment = "right" if center > sum(spec["overall"]) / 2 else "left"
            offset = -8 if alignment == "right" else 8
            ax.annotate(f"{center:+.6f}", (center, y), xytext=(offset, 16),
                        textcoords="offset points", ha=alignment, color=color, fontsize=10)
    ax.set_yticks([row[3] for row in rows], [row[0] for row in rows])
    ax.tick_params(axis="y", length=0, pad=10)
    ax.set_ylim((-.55, .55) if zoom else (-.45, 1.55))
    ax.set_xlim(spec["zoom"] if zoom else spec["overall"])
    ax.set_xlabel(spec["label"], labelpad=10)
    ax.ticklabel_format(axis="x", style="plain", useOffset=False)
    ax.xaxis.set_major_locator(MaxNLocator(5))
    ax.set_title("Historical refit: enlarged detail" if zoom else "Both estimates",
                 loc="left", fontsize=11, pad=17, fontweight="bold")
    if zoom:
        ax.text(0, .39, "truth", ha="center", va="bottom", fontsize=10,
                color="#283c4b", bbox={"facecolor": "white", "edgecolor": "none", "pad": 2})

for column, spec in enumerate(specs):
    draw(axes[0, column], spec, False)
    draw(axes[1, column], spec, True)
fig.text(.055, .055,
         "Bars: local ±2 SD (capacity transformed from log Q). These are local precision diagnostics.\n"
         "Truth is inside both refit bands at this one checkpoint; repeated-sampling coverage is unvalidated.",
         fontsize=10, color="#536675", linespacing=1.6)

output = HERE / "comparison.png"
fig.savefig(output, dpi=180, metadata={"Description": "Read-only plot of completed historical_likelihood_control_001"})
plt.close(fig)
receipt = {
    "schema": "mumble_historical_likelihood_figure_v1",
    "source": {"path": "summary.json", "sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest()},
    "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "output": {"path": output.name, "bytes": output.stat().st_size,
               "sha256": hashlib.sha256(output.read_bytes()).hexdigest()},
    "matplotlib_version": matplotlib.__version__,
    "new_model_or_fit_calls": 0,
    "inference_inputs_modified": False,
}
(HERE / "figure_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt))
