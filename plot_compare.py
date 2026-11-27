#!/usr/bin/env python3
"""
Three P1 methods side by side (P2 = final in all): CSMA final, CSMA final + idealized capture, SSA final.
Metrics on the x axis, one line per method. Success rates (%) and AoI (ms) need different scales, so
the figure has two panels: success rate (linear) and AoI (log, spans 9 ms .. 1.2 s).
Reads results/final_buildup_csma.csv and results/final_buildup_ssa.csv (run_final.py) -> figures/final/compare_methods.png
"""
import csv
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

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
    "legend.frameon": False, "lines.linewidth": 2.2, "lines.markersize": 8,
    "axes.spines.top": False, "axes.spines.right": False,
})
import sys
NODES = int(sys.argv[1]) if len(sys.argv) > 1 else 100   # usage: python3 plot_compare.py [nodes] [simtime]
SIMT = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
SUFFIX = ("" if NODES == 100 else f"_n{NODES}") + ("" if SIMT == 10 else f"_t{SIMT:g}")


def rows(path):
    with open(os.path.join(HERE, "results", path), newline="") as f:
        return list(csv.DictReader(f))


# model v2 (radio off in idle P2 slots, time-average + peak AoI, 65 P1 slots)
picked = rows(f"final_compare_v2{SUFFIX}.csv")   # order: CSMA, CSMA + capture, SSA
DENSITY = sum(float(r["DENS_mean"]) for r in picked) / len(picked)
methods = [
    ("CSMA (final)", picked[0], BLUE, "-", "o"),
    ("CSMA + capture (idealized, not possible on BLE chips)", picked[1], BLUE, "--", "o"),
    ("SSA (final)", picked[2], ORANGE, "-", "s"),
]
PRR = [("P1", "P1\nsuccess rate"), ("P2", "P2\nsuccess rate")]
AOI = [("AoI1_mean", "P1\nmean AoI"), ("AoI1_p99", "P1\np99 AoI"), ("AoI1_max", "P1\nmax AoI"),
       ("AoI2_mean", "P2\nmean AoI"), ("AoI2_p99", "P2\np99 AoI"), ("AoI2_max", "P2\nmax AoI")]

fig, (a1, a2) = plt.subplots(1, 2, figsize=(16, 7.2), gridspec_kw=dict(width_ratios=[1, 2.6]))
for name, r, color, ls, mk in methods:
    v = [float(r[f"{k}_mean"]) for k, _ in PRR]
    a1.plot(range(len(PRR)), v, color=color, ls=ls, marker=mk, label=name,
            markerfacecolor=SURFACE if ls == "--" else color, markeredgewidth=2)
    w = [float(r[f"{k}_mean"]) for k, _ in AOI]
    a2.plot(range(len(AOI)), w, color=color, ls=ls, marker=mk, label=name,
            markerfacecolor=SURFACE if ls == "--" else color, markeredgewidth=2)

# direct value labels: SSA on its own side of the CSMA line, CSMA on the other side, capture to the right
def label_all(ax, keys, fmtf):
    ref = {n: [float(r[f"{k}_mean"]) for k, _ in keys] for n, r, *_ in methods}
    c, s_ = ref["CSMA (final)"], ref["SSA (final)"]
    for name, vals in ref.items():
        for i, y in enumerate(vals):
            above = s_[i] >= c[i]
            if name == "SSA (final)":
                off, va = ((0, 9), "bottom") if above else ((0, -9), "top")
            elif name == "CSMA (final)":
                off, va = ((0, -9), "top") if above else ((0, 9), "bottom")
            else:
                off, va = (12, 0), "center"
            ax.annotate(fmtf(y), (i, y), xytext=off, textcoords="offset points", fontsize=9.5, color=INK,
                        ha="left" if off[0] else "center", va=va)


label_all(a1, PRR, lambda y: f"{y:.1f}")
label_all(a2, AOI, lambda y: f"{y:.0f}" if y >= 100 else f"{y:.1f}")

a1.set_xticks(range(len(PRR)))
a1.set_xticklabels([l for _, l in PRR])
a1.set_xlim(-0.4, len(PRR) - 0.6)
lo = min(float(r[f"{k}_mean"]) for _, r, *_ in methods for k, _ in PRR)
a1.set_ylim(max(0, 5 * int(lo // 5) - 5), 100)
a1.set_title("Success rate (%)  higher is better", loc="left")
a2.set_xticks(range(len(AOI)))
a2.set_xticklabels([l for _, l in AOI])
a2.set_yscale("log")
hi = max(float(r[f"{k}_mean"]) for _, r, *_ in methods for k, _ in AOI)
lo2 = min(float(r[f"{k}_mean"]) for _, r, *_ in methods for k, _ in AOI)
a2.set_ylim(lo2 / 2, hi * 2)
a2.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:g}"))
a2.set_title("Age of information (ms, log scale)  lower is better", loc="left")
h, l = a2.get_legend_handles_labels()
fig.legend(h, l, loc="upper right", bbox_to_anchor=(0.99, 0.995), ncol=3, fontsize=10.5)
fig.suptitle(f"P1 method comparison (P2 = final design) | {NODES} UAVs, on average {DENSITY:.1f} UAVs within 50 m of each UAV",
             fontsize=14, fontweight="bold", x=0.01, ha="left", y=0.93)
fig.text(0.01, 0.01, f"200 x 200 x 80 m, 10 m/s random waypoint, {SIMT:g} s, seed 1. nRF54L15 DK (QFN48): TX <= +7 dBm, "
         "BLE 2M sensitivity -94 dBm. Success = each UAV's 7 nearest neighbours (<= 50 m) really received per cycle; "
         "mean AoI = time average of the age of the newest packet held from them; p99 / max = peak AoI (age just before each new packet arrives).", fontsize=9, color=INK2, wrap=True)
fig.tight_layout(rect=(0, 0.05, 1, 0.9))
name = f"compare_methods_v2{SUFFIX}.png"
fig.savefig(os.path.join(OUT, name), dpi=150)
print("saved figures/final/" + name)
