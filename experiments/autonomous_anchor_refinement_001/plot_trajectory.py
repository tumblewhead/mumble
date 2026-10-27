#!/usr/bin/env python3
"""Plot saved partial-report values; no new inference or truth-file access."""
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import LogLocator

area = Path(__file__).resolve().parent
source = area / "failure_reporting001/summary.json"
raw = source.read_bytes()
summary = json.loads(raw)
assert summary["status"] == "completed_partial_failure_analysis"
assert summary["inference_status"] == "failed" and summary["partial_evidence"] is True
points = summary["accepted_generations"]
x = [p["generation"] for p in points]
values = [[p["computed_common_objective"] for p in points],
          [p["Q_Ah"] * 1000 for p in points],
          [p["endpoint_SOC"] * 100 for p in points]]
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                     "axes.spines.top": False, "axes.spines.right": False,
                     "svg.fonttype": "none", "savefig.facecolor": "white"})
fig, axes = plt.subplots(1, 3, figsize=(13.8, 4.7))
fig.subplots_adjust(left=.067, right=.985, bottom=.18, top=.71, wspace=.32)
fig.suptitle("An anchor obtained from public initialization", x=.067, y=.96,
             ha="left", fontsize=18, fontweight="bold", color="#173b49")
fig.text(.067, .87, "Verified partial result: seven accepted steps. The canonical run then failed an output-integrity check.",
         ha="left", color="#555555", fontsize=11)
for ax, data, title, ylabel in zip(axes, values,
        ["Audited common objective", "Capacity", "Endpoint state of charge"],
        ["Negative log kernel (log scale)", "Capacity (mAh)", "SOC (%)"]):
    ax.plot(x, data, color="#176b87", marker="o", linewidth=2, markersize=5)
    ax.set_title(title, loc="left", fontweight="bold", pad=12)
    ax.set_xlabel("Accepted generation (0 = public start)", labelpad=10)
    ax.set_ylabel(ylabel)
    ax.set_xticks(x)
    ax.grid(axis="y", alpha=.2)
    ax.set_xlim(-.2, 7.4)
axes[0].set_yscale("log")
axes[0].yaxis.set_major_locator(LogLocator(base=10, numticks=6))
axes[0].annotate("4.068 billion", (x[0], values[0][0]), xytext=(8, -2),
                 textcoords="offset points", va="top", fontsize=9)
axes[0].annotate("126,413.1341", (7, values[0][-1]), xytext=(-2, 15),
                 textcoords="offset points", ha="right", fontsize=9)
for ax, truth in zip(axes[1:], [summary["truth"]["capacity_Ah"] * 1000,
                              summary["truth"]["SOC"] * 100]):
    ax.axhline(truth, color="#b36625", linestyle="--", linewidth=1.3,
               label="Saved truth, used only after run")
    ax.legend(loc="lower right", frameon=False, fontsize=8)
axes[1].annotate(f"{values[1][-1]:.6f} mAh", (7, values[1][-1]), xytext=(-2, 13),
                 textcoords="offset points", ha="right", fontsize=9)
axes[2].annotate(f"{values[2][-1]:.6f}%", (7, values[2][-1]), xytext=(-2, 13),
                 textcoords="offset points", ha="right", fontsize=9)
fig.text(.067, .035, "Points describe retained accepted generations; this figure supplies no uncertainty intervals or convergence claim.",
         fontsize=9, color="#555555")
outputs = [area / "anchor_trajectory.png", area / "anchor_trajectory.svg"]
assert not any(p.exists() for p in outputs), "Figure outputs already exist"
for destination in outputs:
    fig.savefig(destination, dpi=170)
plt.close(fig)
assert source.read_bytes() == raw
receipt = {"schema": "mumble_anchor_trajectory_plot_v1",
           "input": {"path": str(source), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()},
           "outputs": {p.name: {"bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in outputs},
           "activity": {"model_calls": 0, "optimizer_calls": 0, "prior_calls": 0, "raw_truth_opens": 0},
           "source_unchanged": True, "inference_status": "failed", "partial_evidence": True}
with (area / "plot_receipt.json").open("x") as stream:
    json.dump(receipt, stream, indent=2)
    stream.write("\n")
print(json.dumps(receipt))
