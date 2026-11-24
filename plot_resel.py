#!/usr/bin/env python3
"""SSA reselection-counter sweep (run_final.py --exps sweep_resel) -> figures/final/sweep_resel.png"""
import csv
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "figures", "final")
os.makedirs(OUT, exist_ok=True)
BLUE, ORANGE = "#2a78d6", "#eb6834"
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3de"
plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.size": 11, "axes.titlesize": 12, "axes.titleweight": "bold", "axes.edgecolor": GRID,
    "axes.labelcolor": INK, "text.color": INK, "xtick.color": INK2, "ytick.color": INK2,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "legend.frameon": False, "lines.linewidth": 2.0, "lines.markersize": 6,
    "axes.spines.top": False, "axes.spines.right": False,
})

rows = list(csv.DictReader(open(os.path.join(HERE, "results", "final_sweep_resel.csv"))))
series = {}
for r in rows:
    counter, init = [s.strip() for s in r["label"].split("|")]
    series.setdefault(init, []).append((counter, r))
counters = [c for c, _ in series["first pick off"]]
x = list(range(len(counters)))
PANELS = [("P1", "P1 PRR (%)"), ("AoI1_mean", "P1 mean AoI (ms)"), ("AoI1_max", "P1 max AoI (ms)"),
          ("P2", "P2 PRR (%)"), ("AoI2_mean", "P2 mean AoI (ms)"), ("AoI2_max", "P2 max AoI (ms)")]
STYLE = {"first pick off": (BLUE, "o", "no short first counter"), "first pick 2-5": (ORANGE, "s", "first pick reselects after 2-5 cycles")}
CHOSEN = "20-60"

fig, axes = plt.subplots(2, 3, figsize=(16, 9))
for ax, (key, name) in zip(axes.flat, PANELS):
    for init, pts in series.items():
        color, marker, label = STYLE[init]
        ys = [float(r[f"{key}_mean"]) for _, r in pts]
        ax.plot(x, ys, color=color, marker=marker, label=label)
        if init == "first pick off":
            i = counters.index(CHOSEN)
            ax.annotate(f"{ys[i]:.1f}" if "P" == key[0] else f"{ys[i]:.0f}" if ys[i] >= 100 else f"{ys[i]:.1f}",
                        (i, ys[i]), xytext=(0, 9), textcoords="offset points", ha="center", fontsize=10, color=INK)
    ax.axvline(counters.index(CHOSEN), color=INK2, ls=":", lw=1.2)
    ax.set_xticks(x)
    ax.set_xticklabels(counters)
    ax.set_xlabel("reselection counter (cycles, uniform)")
    ax.set_title(name, loc="left")
    if key in ("P1", "P2"):
        ax.set_ylim(88, 100)
    else:
        ax.set_ylim(0, None)
h, l = axes.flat[0].get_legend_handles_labels()
fig.legend(h, l, loc="upper right", bbox_to_anchor=(0.99, 0.995), fontsize=10, ncol=2)
fig.suptitle("SSA: how long to keep a P1 slot (dotted line = proposed 20-60, no short first counter)", fontsize=15, fontweight="bold", x=0.01, ha="left")
fig.text(0.01, 0.005, "SSA final otherwise (150 us, +7 dBm, pool 25 %, decay 0.6), P2 final. 100 UAVs, 10 m/s, 10 s, seed 1. "
         "AoI sampled at the end of every cycle for each UAV's 5 nearest neighbours (<= 50 m).", fontsize=9, color=INK2)
fig.tight_layout(rect=(0, 0.03, 1, 0.95))
fig.savefig(os.path.join(OUT, "sweep_resel.png"), dpi=150)
print("saved figures/final/sweep_resel.png")
