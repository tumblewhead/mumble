#!/usr/bin/env python3
"""Plot already closed finite-set comparisons; no scientific evaluations."""
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "experiments/compact_nonlinear_history_001"
SOURCE = EXP / "reporting001/summary.json"
EXPECTED = "0586282d02fc5508fef87b1585f7ed055cb542a87fbb39d779d4372719f74e5f"

def identity(p):
    b = p.read_bytes()
    return {"bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}

def main():
    assert identity(SOURCE)["sha256"] == EXPECTED
    s = json.loads(SOURCE.read_bytes())
    rows = []
    for arm_index in (1, 0):
        for checkpoint in s["checkpoints"]:
            arm = checkpoint["arms"][arm_index]
            row = {"arm": arm["arm"], "time_s": checkpoint["nominal_time_s"]}
            for mode in ("affine", "quartic"):
                group = arm["fidelity"][mode]["groups"]["local_41_excluding_public"]
                assert group["available_count"] == 41 and group["complete_declared_set"]
                row[mode] = group["error_oscillation_available"]
            rows.append(row)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 12,
                         "axes.spines.top": False, "axes.spines.right": False})
    fig, ax = plt.subplots(figsize=(11.6, 6.8))
    fig.subplots_adjust(left=.12, right=.98, bottom=.25, top=.81)
    x = np.array([0., 1., 2.6, 3.6]);width = .30
    colors = {"affine": "#94a3b8", "quartic": "#087f8c"}
    for mode, offset, label in (("affine", -width/2, "Affine residual approximation"),
                                ("quartic", width/2, "Second-order residual approximation")):
        values = [r[mode] for r in rows]
        bars = ax.bar(x + offset, values, width, color=colors[mode], label=label, zorder=3)
        for bar, value in zip(bars, values):
            label_text = f"{value:.6f}" if value < .001 else f"{value:.5f}" if value < 1 else f"{value:,.0f}"
            ax.text(bar.get_x()+bar.get_width()/2, value*1.40, label_text,
                    ha="center", va="bottom", fontsize=10, fontweight="bold", color="#163343")
    ax.set_yscale("log");ax.set_ylim(1e-5, 1e6)
    ax.set_yticks([1e-5,1e-3,1e-1,10,1000,100000]);ax.grid(axis="y",alpha=.25,zorder=0)
    ax.set_ylabel("Range of likelihood approximation error\n(log-likelihood units; logarithmic axis)")
    ax.set_xticks(x, ["7,200 s", "8,400 s", "7,200 s", "8,400 s"])
    ax.text(.5,-.16,"Saved autonomous anchor",transform=ax.get_xaxis_transform(),ha="center",fontweight="bold",fontsize=13)
    ax.text(3.1,-.16,"Fixed public starting anchor",transform=ax.get_xaxis_transform(),ha="center",fontweight="bold",fontsize=13)
    ax.axvline(1.8,color="#cbd5e1",lw=1.1)
    fig.suptitle("Compression accuracy depends strongly on the anchor",x=.12,y=.97,ha="left",fontsize=19,fontweight="bold",color="#163343")
    fig.text(.12,.91,"The same 41 joint parameter points around saved generation 7; smaller is better.",fontsize=12,color="#475569")
    ax.legend(loc="upper left",bbox_to_anchor=(0.,1.07),frameon=False,fontsize=10,ncol=2)
    fig.text(.12,.085,"Error range = maximum minus minimum of (compact cost − exact cost) over the declared points.",fontsize=10,color="#475569")
    fig.text(.12,.047,"Finite diagnostic only: no interval-coverage claim. The saved-anchor chart is also inaccurate at the distant public starting point.",fontsize=9.6,color="#475569")
    paths=[EXP/"history_fidelity.png",EXP/"history_fidelity.svg"]
    for p in paths:
        if p.exists():raise FileExistsError(p)
        fig.savefig(p,dpi=170,facecolor="white",metadata={"Creator":"mumble compact nonlinear history saved-output plot"} if p.suffix==".svg" else None)
    plt.close(fig)
    receipt={"schema":"mumble_compact_history_plot_v1","status":"completed",
             "source_summary":{"path":str(SOURCE.relative_to(ROOT)),**identity(SOURCE)},
             "script":{"path":str(Path(__file__).relative_to(ROOT)),**identity(Path(__file__))},
             "data":rows,"outputs":{str(p.relative_to(ROOT)):identity(p) for p in paths},
             "matplotlib":matplotlib.__version__,"model_calls":0,"prior_evaluations":0,"truth_reads":0,
             "interpretation":"Finite available41-node error oscillation, not a posterior interval or continuous-domain guarantee."}
    with (EXP/"plot_receipt.json").open("x") as f:json.dump(receipt,f,sort_keys=True,indent=2);f.write("\n")
    print(json.dumps({"status":"completed","outputs":receipt["outputs"]}))

if __name__ == "__main__":
    main()
