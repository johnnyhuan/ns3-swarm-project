#!/usr/bin/env python3
"""
Line charts of the P2 avoid-distance sweep (run_p2_avoid.py) -> figures/p2/.
Reads the per-run reports p2_avoid_p2_avoid<D>_seed1.txt in the repo root.
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

CHOSEN = 50   # current avoid distance (m)
xs, prr, fails = [], [], {}
KEYS = [("PREAMBLE_LOW_SINR", "Low SINR (co-channel interference)", ORANGE),
        ("PREAMBLE_COLLISION_BUSY_RX", "Preamble collision", YELLOW),
        ("P1_DISCOVERY_MISS", "P1 discovery miss", BLUE),
        ("RX_DEAFNESS_SLOT_CONFLICT", "Two wanted neighbours in one slot", AQUA)]
for c in range(0, 201):
    f = os.path.join(HERE, f"p2_avoid_p2_avoid{c}_seed1.txt")
    if not os.path.exists(f):
        continue
    t = open(f, encoding="utf-8", errors="ignore").read()
    links = int(re.search(r"Total Expected P2 Neighbor Links.*?:\s*(\d+)", t).group(1))
    xs.append(c)
    prr.append(float(re.search(r"Successfully Received \(Delivered\)\s*:\s*\d+\s*\(([\d.]+)%\)", t).group(1)))
    for k, _, _ in KEYS:
        fails.setdefault(k, []).append(100.0 * int(re.search(rf"\b{k}\s*:\s*(\d+)", t).group(1)) / links)

note = ("P1 = SSA tuned, 100 UAVs, 10 s, seed 1. P2: 24 slots x 400 us, 10 channels, +4 dBm, no CCA, listen to 5 + 3 neighbours. "
        "PRR = share of each UAV's 5 nearest neighbours (<= 50 m) whose P2 packet was really received.")

# Fig 1: P2 PRR vs channel count
fig, ax = plt.subplots(figsize=(9, 5.2))
ax.plot(xs, prr, color=BLUE, marker="o")
ax.axvline(CHOSEN, color=INK2, ls=":", lw=1.2)
i = xs.index(CHOSEN)
ax.annotate(f"current: {CHOSEN} m, {prr[i]:.1f}%", (CHOSEN, prr[i]), xytext=(CHOSEN - 30, prr[i] - 4),
            arrowprops=dict(arrowstyle="-", color=INK2, lw=1), color=INK)
ax.annotate(f"{prr[-1]:.1f}%", (xs[-1], prr[-1]), xytext=(4, 6), textcoords="offset points", color=INK2, fontsize=11)
ax.annotate(f"{prr[0]:.1f}%", (xs[0], prr[0]), xytext=(6, -4), textcoords="offset points", color=INK2, fontsize=11)
ax.set_xticks(xs)
ax.set_xlabel("Avoid distance D (m): skip time slots of neighbours closer than D")
ax.set_ylabel("P2 PRR (%)")
ax.set_ylim(min(85, min(prr) - 2), 100)
ax.set_title("P2 delivery vs. slot-avoid distance")
fig.text(0.01, 0.01, note, fontsize=9, color=INK2, wrap=True)
fig.tight_layout(rect=(0, 0.07, 1, 1))
fig.savefig(os.path.join(OUT, "p2_avoid_prr.png"), dpi=160)

# Fig 2: failure breakdown vs channel count
fig, ax = plt.subplots(figsize=(9, 5.2))
for k, label, color in KEYS:
    pts = [(x, v) for x, v in zip(xs, fails[k]) if v > 0]   # 0 cannot be drawn on a log axis
    ax.plot([p[0] for p in pts], [p[1] for p in pts], color=color, marker="o", label=label)
ax.axvline(CHOSEN, color=INK2, ls=":", lw=1.2)
ax.set_xticks(xs)
ax.set_xlabel("Avoid distance D (m): skip time slots of neighbours closer than D")
ax.set_ylabel("Lost links (% of all links)")
ax.set_yscale("log")
ax.set_yticks([0.1, 0.3, 1, 3, 10, 30, 100])
ax.set_yticklabels(["0.1", "0.3", "1", "3", "10", "30", "100"])
ax.set_title("Why P2 packets are lost (by avoid distance)")
ax.legend(loc="upper right", fontsize=10)
fig.text(0.01, 0.01, "0 m = only avoid the exact cell a neighbour uses. Beacons are heard up to ~75 m, "
         "so 100 m = avoid the time slot of every neighbour that can be heard.",
         fontsize=9, color=INK2, wrap=True)
fig.tight_layout(rect=(0, 0.07, 1, 1))
fig.savefig(os.path.join(OUT, "p2_avoid_failures.png"), dpi=160)
print("saved figures/p2/p2_avoid_prr.png, figures/p2/p2_avoid_failures.png")
