#!/usr/bin/env python3
"""
Charts of the P2 one-vs-two-copies test (run_p2_copies.py) -> figures/p2/.
Reads the per-run reports p2_copies_p2_n<N>_copies<C>_seed1.txt in the repo root.
"""
import os
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "figures", "p2")
os.makedirs(OUT, exist_ok=True)

BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3de"
plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.size": 12, "axes.titlesize": 14, "axes.titleweight": "bold", "axes.labelsize": 12,
    "axes.edgecolor": GRID, "axes.labelcolor": INK, "text.color": INK, "xtick.color": INK2,
    "ytick.color": INK2, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.axisbelow": True, "legend.frameon": False, "lines.linewidth": 2.0, "lines.markersize": 6,
    "axes.spines.top": False, "axes.spines.right": False,
})

KEYS = [("P1_DISCOVERY_MISS", "P1 discovery miss", BLUE),
        ("PREAMBLE_LOW_SINR", "Low SINR (co-channel interference)", ORANGE),
        ("PREAMBLE_COLLISION_BUSY_RX", "Preamble collision", YELLOW),
        ("RX_DEAFNESS_SLOT_CONFLICT", "Two wanted neighbours in one slot", AQUA)]


def load(n, c):
    f = os.path.join(HERE, f"p2_copies_p2_n{n}_copies{c}_seed1.txt")
    if not os.path.exists(f):
        return None
    t = open(f, encoding="utf-8", errors="ignore").read()
    links = int(re.search(r"Total Expected P2 Neighbor Links.*?:\s*(\d+)", t).group(1))
    row = {"PRR": float(re.search(r"Successfully Received \(Delivered\)\s*:\s*\d+\s*\(([\d.]+)%\)", t).group(1))}
    for k, _, _ in KEYS:
        m = re.search(rf"\b{k}\s*:\s*(\d+)", t)
        row[k] = 100.0 * (int(m.group(1)) if m else 0) / links
    row["OTHER"] = 100.0 - row["PRR"] - sum(row[k] for k, _, _ in KEYS)
    return row


ns = [n for n in (50, 75, 100, 125, 150, 175, 200) if load(n, 1) and load(n, 2)]
d = {(n, c): load(n, c) for n in ns for c in (1, 2)}
note = ("P1 = SSA tuned, 10 s, seed 1. P2: 24 slots x 400 us, 10 channels, +4 dBm, no CCA, listen to 5 + 3 neighbours, "
        "50 m slot avoidance. 2 copies = two non-adjacent cells per cycle, both advertised in the P1 beacon.")

# Fig 1: P2 PRR, 1 vs 2 copies
fig, ax = plt.subplots(figsize=(9, 5.2))
for c, color, label in ((1, BLUE, "1 copy per cycle"), (2, ORANGE, "2 copies per cycle")):
    ys = [d[(n, c)]["PRR"] for n in ns]
    ax.plot(ns, ys, color=color, marker="o", label=label)
    for x, y in zip(ns, ys):
        ax.annotate(f"{y:.1f}", (x, y), xytext=(0, 8 if c == 2 else -16), textcoords="offset points",
                    ha="center", color=INK2, fontsize=10)
ax.set_xticks(ns)
ax.set_xlabel("Number of UAVs (200 x 200 x 80 m)")
ax.set_ylabel("P2 PRR (%)")
lo = min(d[k]["PRR"] for k in d)
ax.set_ylim(max(0, int(lo) - 4), 100)
ax.set_title("P2 delivery: one vs. two copies per cycle")
ax.legend(loc="lower left")
fig.text(0.01, 0.01, note, fontsize=9, color=INK2, wrap=True)
fig.tight_layout(rect=(0, 0.07, 1, 1))
fig.savefig(os.path.join(OUT, "p2_copies_prr.png"), dpi=160)

# Fig 2: loss causes, grouped bars (1 copy | 2 copies) per density
fig, ax = plt.subplots(figsize=(9, 5.2))
w = 0.38
xs = range(len(ns))
for i, n in enumerate(ns):
    for j, c in enumerate((1, 2)):
        x = i + (j - 0.5) * w
        bottom = 0.0
        for k, label, color in KEYS:
            v = d[(n, c)][k]
            ax.bar(x, v, w * 0.92, bottom=bottom, color=color, label=label if (i == 0 and j == 0) else None,
                   edgecolor=SURFACE, linewidth=0.8)
            bottom += v
        ax.annotate(f"{c}x", (x, bottom), xytext=(0, 3), textcoords="offset points", ha="center",
                    color=INK2, fontsize=10)
ax.set_xticks(list(xs))
ax.set_xticklabels([f"{n} UAVs" for n in ns])
ax.set_ylabel("Lost links (% of all links)")
ax.set_title("Why P2 packets are lost (1x = one copy, 2x = two copies)")
ax.legend(loc="upper left", fontsize=10)
fig.text(0.01, 0.01, "With 2 copies, loss reasons are judged on the later copy (a link is lost only if both copies fail).",
         fontsize=9, color=INK2, wrap=True)
fig.tight_layout(rect=(0, 0.05, 1, 1))
fig.savefig(os.path.join(OUT, "p2_copies_failures.png"), dpi=160)
print("saved figures/p2/p2_copies_prr.png, figures/p2/p2_copies_failures.png")
