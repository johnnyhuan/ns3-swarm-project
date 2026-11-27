#!/usr/bin/env python3
"""SSA one-parameter sweeps (run_final.py --exps sweep_decay / sweep_counter) -> figures/final/<exp>_v2<suffix>.png
usage: python3 plot_sweep.py <sweep_decay|sweep_counter> [nodes] [simtime]"""
import csv
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "figures", "final")
os.makedirs(OUT, exist_ok=True)
BLUE, AQUA = "#2a78d6", "#1baf7a"
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3de"
plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.size": 11, "axes.titlesize": 12, "axes.titleweight": "bold", "axes.edgecolor": GRID,
    "axes.labelcolor": INK, "text.color": INK, "xtick.color": INK2, "ytick.color": INK2,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "legend.frameon": False, "lines.linewidth": 2.2, "lines.markersize": 7,
    "axes.spines.top": False, "axes.spines.right": False,
})
EXP = sys.argv[1]
NODES = int(sys.argv[2]) if len(sys.argv) > 2 else 100
SIMT = float(sys.argv[3]) if len(sys.argv) > 3 else 10.0
CFG = {
    "sweep_decay": dict(title="SSA RSSI-memory decay sweep", final="decay 0.6",
                        xlabel="RSSI memory decay per cycle (dotted = final 0.6)",
                        note="Decay: each cycle old RSSI history is multiplied by it (small = forgets fast; "
                             "1.0 = no decay, history halved at reselection). Reselection 20-60."),
    "sweep_counter": dict(title="SSA reselection counter sweep", final="20-60",
                          xlabel="reselection counter range in cycles (dotted = final 20-60; 1 cycle = 19.8 ms)",
                          note="Counter: a UAV keeps its P1 slot for a random number of cycles in this range, then re-picks "
                               "(no short first-pick counter). Decay 0.6."),
}[EXP]
SUFFIX = ("" if NODES == 100 else f"_n{NODES}") + ("" if SIMT == 10 else f"_t{SIMT:g}")
rows = list(csv.DictReader(open(os.path.join(HERE, "results", f"final_{EXP}_v2{SUFFIX}.csv"))))
labels = [r["label"].replace("decay ", "") for r in rows]
xs = list(range(len(rows)))
FX = [r["label"] for r in rows].index(CFG["final"])
dens = sum(float(r["DENS_mean"]) for r in rows) / len(rows)
PANELS = [("Success rate (%)", "P1", "P2"), ("Mean AoI: time average (ms)", "AoI1_mean", "AoI2_mean"),
          ("Peak AoI p99 (ms)", "AoI1_p99", "AoI2_p99"), ("Peak AoI max (ms)", "AoI1_max", "AoI2_max")]
fig, axes = plt.subplots(2, 2, figsize=(15, 9.6))
for ax, (title, k1, k2) in zip(axes.flat, PANELS):
    for k, color, mk, name in ((k1, BLUE, "o", "P1 (discovery)"), (k2, AQUA, "s", "P2 (state packets)")):
        ys = [float(r[f"{k}_mean"]) for r in rows]
        ax.plot(xs, ys, color=color, marker=mk, label=name)
        for x, y in zip(xs, ys):
            ax.annotate(f"{y:.1f}" if y < 100 else f"{y:.0f}", (x, y), xytext=(0, 8 if k == k1 else -15),
                        textcoords="offset points", ha="center", fontsize=8.5, color=INK)
    ax.axvline(FX, color=INK2, ls=":", lw=1.2)
    ax.set_title(title, loc="left")
    ax.set_xlabel(CFG["xlabel"])
    ax.set_xticks(xs)
    ax.set_xticklabels(labels)
    if k1 == "P1":
        lo = min(float(r[f"{k}_mean"]) for r in rows for k in (k1, k2))
        ax.set_ylim(max(0, 5 * int(lo // 5) - 5), 100)
    else:
        ax.set_ylim(0, None)
h, l = axes.flat[0].get_legend_handles_labels()
fig.legend(h, l, loc="upper right", bbox_to_anchor=(0.99, 0.995), ncol=2, fontsize=10.5)
fig.suptitle(f"{CFG['title']} (everything else final) | {NODES} UAVs, density {dens:.1f} UAVs within 50 m",
             fontsize=14, fontweight="bold", x=0.01, ha="left")
fig.text(0.01, 0.005, f"200 x 200 x 80 m, 10 m/s random waypoint, {SIMT:g} s, seed 1. SSA: 150 us slots, pool 25 %, +7 dBm, "
         "P2 final. " + CFG["note"] + " Success = 7 nearest neighbours (<= 50 m) received per cycle. "
         "Mean AoI = time average; p99 / max = peak AoI.", fontsize=9, color=INK2, wrap=True)
fig.tight_layout(rect=(0, 0.04, 1, 0.96))
name = f"{EXP}_v2{SUFFIX}.png"
fig.savefig(os.path.join(OUT, name), dpi=150)
print("saved figures/final/" + name)
