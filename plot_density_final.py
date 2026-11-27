#!/usr/bin/env python3
"""
SSA final + P2 final vs swarm density -> figures/final/density_ssa.png
x = measured mean number of UAVs within 50 m of a UAV (not the swarm size).
Collects the SSA-final row of every swarm size that has been run:
  results/final_ssa_only_n<N>.csv, results/final_compare_n<N>.csv, results/final_buildup_ssa.csv (100 UAVs)
"""
import csv
import glob
import os
import re

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
import argparse
ap = argparse.ArgumentParser()
ap.add_argument("--simtime", type=float, default=10.0)
SIMT = ap.parse_args().simtime
TSUF = "" if SIMT == 10 else f"_t{SIMT:g}"
KNOWN_DENS = {100: 20.2}   # 100-UAV runs predate the density column (measured 20.2, seed 1)


def read(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


pts = {}
# current model only (v2: radio off in idle P2 slots, time-average + peak AoI, 65 P1 slots)
for f in glob.glob(os.path.join(HERE, "results", f"final_ssa_only_v2*{TSUF}.csv")):
    base = os.path.basename(f)
    if TSUF == "" and "_t" in base.replace("final_", ""):
        continue
    m = re.search(r"_n(\d+)", base)
    n = int(m.group(1)) if m else 100
    for r in read(f):
        if r["label"].startswith("SSA"):
            pts[n] = r


def val(r, k):
    return float(r[f"{k}_mean"])


data = []
for n, r in pts.items():
    d = val(r, "DENS") if r.get("DENS_mean") not in (None, "", "nan") else KNOWN_DENS.get(n, float("nan"))
    data.append((d, r))
data.sort(key=lambda t: t[0])
xs = [d for d, _ in data]

PANELS = [("Success rate (%)", "P1", "P2", "%"), ("Mean AoI: time average (ms)", "AoI1_mean", "AoI2_mean", "ms"),
          ("Peak AoI p99 (ms): 99 % of updates arrive within", "AoI1_p99", "AoI2_p99", "ms"),
          ("Peak AoI max (ms): longest time without an update", "AoI1_max", "AoI2_max", "ms")]
fig, axes = plt.subplots(2, 2, figsize=(15, 9.6))
for ax, (title, k1, k2, unit) in zip(axes.flat, PANELS):
    for k, color, mk, name in ((k1, BLUE, "o", "P1 (discovery)"), (k2, AQUA, "s", "P2 (state packets)")):
        ys = [val(r, k) for _, r in data]
        ax.plot(xs, ys, color=color, marker=mk, label=name)
        for x, y in zip(xs, ys):
            ax.annotate(f"{y:.1f}" if (unit == "%" or y < 100) else f"{y:.0f}", (x, y),
                        xytext=(0, 8 if k == k1 else -15), textcoords="offset points",
                        ha="center", fontsize=8.5, color=INK)
    ax.set_title(title, loc="left")
    ax.set_xlabel("density: mean number of UAVs within 50 m of a UAV")
    if unit == "%":
        lo = min(min(val(r, k1), val(r, k2)) for _, r in data)
        ax.set_ylim(max(0, 5 * int(lo // 5) - 5), 100)
    else:
        ax.set_ylim(0, None)
h, l = axes.flat[0].get_legend_handles_labels()
fig.legend(h, l, loc="upper right", bbox_to_anchor=(0.99, 0.995), ncol=2, fontsize=10.5)
fig.suptitle("SSA + P2 (final design) vs swarm density", fontsize=15, fontweight="bold", x=0.01, ha="left")
fig.text(0.01, 0.005, f"200 x 200 x 80 m, 10 m/s random waypoint, {SIMT:g} s, seed 1; density changed by the number of UAVs. "
         "nRF54L15 DK (QFN48): TX <= +7 dBm, BLE 2M sensitivity -94 dBm. Success = each UAV's 7 nearest neighbours "
         "(<= 50 m) really received per cycle. Mean AoI = time average of the age of the newest packet held from them; "
         "peak AoI = age just before each new packet arrives.", fontsize=9, color=INK2, wrap=True)
fig.tight_layout(rect=(0, 0.04, 1, 0.96))
fig.savefig(os.path.join(OUT, f"density_ssa_v2{TSUF}.png"), dpi=150)
print(f"saved figures/final/density_ssa_v2{TSUF}.png  points:", ", ".join(f"{d:.1f}" for d in xs))
