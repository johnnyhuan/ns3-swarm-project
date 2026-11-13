#!/usr/bin/env python3
"""
Line charts for the Phase 1 report: SSA (Sensing-based Slotted Access) vs CSMA.

Reads the per-seed ground-truth reports already in the repo:
  p1_final_<mode>_seed<N>.txt      (run_p1_final_compare.py, 10 s, 5 seeds)
  p1_robust_<cfg>_seed<N>.txt      (run_p1_robustness.py, 10 s, 3 seeds)
and writes PNGs to figures/.

Usage: python3 plot_p1_report.py
"""
import glob
import os
import re
import statistics

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "figures")
os.makedirs(OUT, exist_ok=True)

# Palette: categorical slots 1-2 (validated: CVD dE 24.7, normal dE 33.6, >= 3:1 on surface)
SSA = "#2a78d6"      # blue  - proposed method
CSMA = "#eb6834"     # orange - baseline
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e4e3de"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.size": 12, "axes.titlesize": 14, "axes.titleweight": "bold", "axes.labelsize": 12,
    "axes.edgecolor": GRID, "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": INK2, "ytick.color": INK2, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.8, "axes.axisbelow": True, "legend.frameon": False,
    "lines.linewidth": 2.0, "lines.markersize": 8,
})
for side in ("top", "right"):
    plt.rcParams[f"axes.spines.{side}"] = False

BRACKETS = ["0-10m", "10-20m", "20-30m", "30-40m", "40-50m"]


def read(path):
    return open(path, encoding="utf-8", errors="ignore").read()


def prr(text):
    return float(re.search(r"Successfully Received \(Delivered\)\s*:\s*\d+\s*\(([\d.]+)%\)", text).group(1))


def brackets(text):
    out = []
    for b in BRACKETS:
        m = re.search(rf"^\s*{b}\s*\|\s*(\d+)\s*\|\s*(\d+)", text, re.M)
        out.append(100.0 * int(m.group(2)) / int(m.group(1)))
    return out


def seeds(pattern):
    files = sorted(glob.glob(os.path.join(HERE, pattern)))
    if not files:
        raise SystemExit(f"no files for {pattern}")
    return [read(f) for f in files]


def mean_sd(vals):
    return statistics.mean(vals), (statistics.stdev(vals) if len(vals) > 1 else 0.0)


def finish(ax, fig, name, note):
    fig.text(0.01, 0.01, note, fontsize=9, color=INK2, ha="left", va="bottom")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    path = os.path.join(OUT, name)
    fig.savefig(path, dpi=200)
    plt.close(fig)
    print("saved", path)


# ---------------------------------------------------------------- 1) PRR vs distance
modes = [("SSA (tuned)", "ssa_tuned", SSA, "-", "o", True),
         ("SSA (default)", "ssa_default", SSA, "--", "o", False),
         ("CSMA (tuned)", "csma_tuned", CSMA, "-", "s", True),
         ("CSMA (default)", "csma_default", CSMA, "--", "s", False)]
fig, ax = plt.subplots(figsize=(8, 5))
x = list(range(len(BRACKETS)))
for label, tag, color, ls, mk, filled in modes:
    runs = [brackets(t) for t in seeds(f"p1_final_{tag}_seed*.txt")]
    ys = [statistics.mean(r[i] for r in runs) for i in x]
    ax.plot(x, ys, ls=ls, color=color, marker=mk, label=label,
            markerfacecolor=color if filled else SURFACE, markeredgewidth=2)
    if filled:
        ax.annotate(f"{ys[-1]:.1f}%", (x[-1], ys[-1]), xytext=(8, 0), textcoords="offset points",
                    va="center", color=INK, fontsize=11)
ax.set_xticks(x, ["0–10", "10–20", "20–30", "30–40", "40–50"])
ax.set_xlabel("Distance to neighbor (m)")
ax.set_ylabel("Phase 1 discovery PRR (%)")
ax.set_ylim(50, 101)
ax.set_xlim(-0.2, len(x) - 0.55)
ax.set_title("Discovery reliability vs. distance")
ax.legend(loc="lower left", ncol=2)
finish(ax, fig, "fig1_prr_vs_distance.png",
       "100 UAVs, 200×200×80 m, 10 m/s, BLE 5.4 LE 2M PHY model, 10 s, mean of 5 seeds")

# ---------------------------------------------------------------- 2) PRR vs density
fig, ax = plt.subplots(figsize=(8, 5))
nodes = [50, 100, 150, 200]
series = {}
for label, key, color, mk in [("SSA (tuned)", "ssa", SSA, "o"), ("CSMA (tuned)", "csma", CSMA, "s")]:
    ms = [mean_sd([prr(t) for t in seeds(f"p1_robust_{key}_n{n}_e0_seed*.txt")]) for n in nodes]
    series[key] = [m for m, _ in ms]
    ax.errorbar(nodes, [m for m, _ in ms], yerr=[s for _, s in ms], color=color, marker=mk,
                capsize=4, elinewidth=1.2, label=label)
    ax.annotate(f"{ms[-1][0]:.1f}%", (nodes[-1], ms[-1][0]), xytext=(10, 0), textcoords="offset points",
                va="center", color=INK, fontsize=11)
for n, a, b in zip(nodes, series["ssa"], series["csma"]):
    ax.annotate(f"+{a - b:.1f}", (n, (a + b) / 2), ha="center", va="center", color=INK2, fontsize=10)
ax.set_xticks(nodes)
ax.set_xlim(40, 222)
ax.set_xlabel("Number of UAVs in the airspace")
ax.set_ylabel("Phase 1 discovery PRR (%)")
ax.set_ylim(70, 101)
ax.set_title("Discovery reliability vs. swarm density")
ax.legend(loc="lower left")
finish(ax, fig, "fig2_prr_vs_density.png",
       "200×200×80 m, 10 m/s, perfect sync, 10 s, mean ± 1 std of 3 seeds; grey numbers = SSA − CSMA (pp)")

# ---------------------------------------------------------------- 3) PRR vs sync error
fig, ax = plt.subplots(figsize=(8, 5))
errs = [0, 10, 20, 30, 40, 60]
ms = [mean_sd([prr(t) for t in seeds(f"p1_robust_ssa_n100_e{e}_seed*.txt")]) for e in errs]
ax.axvspan(0, 14, color=SSA, alpha=0.07, lw=0)
ax.text(1, 75.6, "within slot guard (14 µs)", color=INK2, fontsize=10)
ax.errorbar(errs, [m for m, _ in ms], yerr=[s for _, s in ms], color=SSA, marker="o",
            capsize=4, elinewidth=1.2, label="SSA (tuned)")
csma_vals = [prr(t) for e in (0, 60) for t in seeds(f"p1_robust_csma_n100_e{e}_seed*.txt")]
cm = statistics.mean(csma_vals)
ax.axhline(cm, color=CSMA, ls="--", label="CSMA (tuned, needs no sync)")
for e, (m, _) in zip(errs, ms):
    if e in (0, 20, 40, 60):
        ax.annotate(f"{m:.1f}%", (e, m), xytext=(6, 8), textcoords="offset points", color=INK, fontsize=10)
ax.set_xticks(errs, [f"±{e}" for e in errs])
ax.set_xlabel("Per-node clock synchronization error (µs)")
ax.set_ylabel("Phase 1 discovery PRR (%)")
ax.set_ylim(75, 101)
ax.set_xlim(-3, 63)
ax.set_title("Sensitivity of SSA to clock synchronization error")
ax.legend(loc="upper right")
finish(ax, fig, "fig3_prr_vs_sync_error.png",
       "100 UAVs, 150 µs slots, error redrawn per node per cycle, 10 s, mean ± 1 std of 3 seeds")
