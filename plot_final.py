#!/usr/bin/env python3
"""
Build-up charts from run_final.py -> figures/final/.
One figure per experiment: top row P1 (PRR, mean AoI, max AoI), bottom row P2 (same three).
Each bar is one cumulative design step; a dashed line marks a reference row (CSMA + idealized capture).
"""
import csv
import os

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
    "font.size": 11, "axes.titlesize": 12, "axes.titleweight": "bold", "axes.labelsize": 11,
    "axes.edgecolor": GRID, "axes.labelcolor": INK, "text.color": INK, "xtick.color": INK2,
    "ytick.color": INK2, "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.axisbelow": True, "legend.frameon": False,
    "axes.spines.top": False, "axes.spines.right": False,
})

TITLES = {
    "buildup_csma": "P1 CSMA: from default to final",
    "buildup_ssa": "P1 SSA: from the first version to final",
    "buildup_p2": "P2: from the old design to final (P1 = SSA final)",
}
PANELS = [("P1", "P1 PRR (%)", "%"), ("AoI1_mean", "P1 mean AoI (ms)", "ms"), ("AoI1_max", "P1 max & p99 AoI (ms)", "ms"),
          ("P2", "P2 PRR (%)", "%"), ("AoI2_mean", "P2 mean AoI (ms)", "ms"), ("AoI2_max", "P2 max & p99 AoI (ms)", "ms")]


def tint(hex_color, amount=0.55):
    """Lighter step of the same hue (blend toward the surface)."""
    h = hex_color.lstrip("#")
    c = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    sfc = [int(SURFACE[1:][i:i + 2], 16) for i in (0, 2, 4)]
    return "#" + "".join(f"{round(v + (sv - v) * amount):02x}" for v, sv in zip(c, sfc))
NOTE = ("100 UAVs, 200 x 200 x 80 m, 10 m/s, 10 s, seed 1. nRF54L15 DK (QFN48): TX <= +7 dBm, BLE 2M sensitivity -94 dBm. "
        "PRR = share of each UAV's 7 nearest neighbours (<= 50 m) really received per cycle. "
        "AoI = age of the newest packet held from each of those neighbours, sampled at the end of every cycle.")


def load(exp):
    path = os.path.join(HERE, "results", f"final_{exp}.csv")
    if not os.path.exists(path):
        return None
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def fmt(v, unit):
    if unit == "%":
        return f"{v:.1f}"
    return f"{v:.0f}" if v >= 100 else f"{v:.1f}"


for exp, title in TITLES.items():
    rows = load(exp)
    if not rows:
        continue
    steps = [r for r in rows if r["kind"] == "step"]
    refs = [r for r in rows if r["kind"] == "reference"]
    labels = [r["label"].replace(" | ", "\n") for r in steps]
    x = list(range(len(steps)))
    fig, axes = plt.subplots(2, 3, figsize=(max(15, 2.3 * len(steps) * 1.6), 9.6))
    for ax, (key, name, unit) in zip(axes.flat, PANELS):
        color = BLUE if key.startswith(("P1", "AoI1")) else AQUA
        vals = [float(r[f"{key}_mean"]) for r in steps]
        is_max = key.endswith("_max")
        ax.bar(x, vals, width=0.62, color=tint(color) if is_max else color, edgecolor=SURFACE, linewidth=2,
               label="max" if is_max else None)
        if is_max:
            p99 = [float(r[f"{key.replace('_max', '_p99')}_mean"]) for r in steps]
            ax.bar(x, p99, width=0.36, color=color, edgecolor=SURFACE, linewidth=2, label="p99")
            for xi, v in zip(x, p99):
                ax.annotate(fmt(v, unit), (xi, v), xytext=(0, 3), textcoords="offset points",
                            ha="center", va="bottom", fontsize=9, color=INK)
            ax.legend(loc="lower right", bbox_to_anchor=(1.0, 1.0), ncol=2, fontsize=9, borderaxespad=0.2)
        top = max(vals + [float(r[f"{key}_mean"]) for r in refs])
        for xi, v in zip(x, vals):
            ax.annotate(fmt(v, unit), (xi, v), xytext=(0, 3), textcoords="offset points",
                        ha="center", va="bottom", fontsize=9, color=INK)
        for r in refs:
            rv = float(r[f"{key}_mean"])
            ax.axhline(rv, color=INK2, ls="--", lw=1.4, label=f"{r['label']} (not possible on BLE chips)")
            txt = fmt(rv, unit)
            if is_max:
                txt += f"\n(p99 {fmt(float(r[key.replace('_max', '_p99') + '_mean']), unit)})"
            ax.annotate(txt, (1.0, rv), xycoords=("axes fraction", "data"), xytext=(2, 0),
                        textcoords="offset points", ha="left", va="center", fontsize=9, color=INK2)
        if unit == "%":
            lo = min(vals + [float(r[f"{key}_mean"]) for r in refs])
            ax.set_ylim(max(0, (int(lo) // 5) * 5 - 5), 100)
        else:
            ax.set_ylim(0, top * 1.18)
        ax.set_title(name, loc="left")
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=8.5)
    fig.suptitle(title, fontsize=15, fontweight="bold", x=0.01, ha="left")
    if refs:
        h, l = axes.flat[0].get_legend_handles_labels()
        fig.legend(h, l, loc="upper right", bbox_to_anchor=(0.99, 0.995), fontsize=10)
    fig.text(0.01, 0.005, NOTE, fontsize=8.5, color=INK2, wrap=True)
    fig.tight_layout(rect=(0, 0.045, 1, 0.97))
    out = os.path.join(OUT, f"{exp}.png")
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print("saved", os.path.relpath(out, HERE))
