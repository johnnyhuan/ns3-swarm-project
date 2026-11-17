#!/usr/bin/env python3
"""
Line charts of the P2 density sweep (run_p2_density.py) -> figures/p2/.
Reads p2_density_summary.txt (P1 PRR) and the per-run reports p2_density_p2_n<N>_seed1.txt.
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

CHOSEN = 100   # reference swarm size
xs, prr, fails = [], [], {}
KEYS = [("PREAMBLE_LOW_SINR", "Low SINR (co-channel interference)", ORANGE),
        ("PREAMBLE_COLLISION_BUSY_RX", "Preamble collision", YELLOW),
        ("P1_DISCOVERY_MISS", "P1 discovery miss", BLUE),
        ("RX_DEAFNESS_SLOT_CONFLICT", "Two wanted neighbours in one slot", AQUA)]
for c in range(1, 501):
    f = os.path.join(HERE, f"p2_density_p2_n{c}_seed1.txt")
    if not os.path.exists(f):
        continue
    t = open(f, encoding="utf-8", errors="ignore").read()
    links = int(re.search(r"Total Expected P2 Neighbor Links.*?:\s*(\d+)", t).group(1))
    xs.append(c)
    prr.append(float(re.search(r"Successfully Received \(Delivered\)\s*:\s*\d+\s*\(([\d.]+)%\)", t).group(1)))
    for k, _, _ in KEYS:
        fails.setdefault(k, []).append(100.0 * int(re.search(rf"\b{k}\s*:\s*(\d+)", t).group(1)) / links)

note = ("P1 = SSA tuned, 200 x 200 x 80 m, 10 s, seed 1. P2: 24 slots x 400 us, 10 channels, +4 dBm, no CCA, listen to 5 + 3 neighbours. "
        "PRR = share of each UAV's 5 nearest neighbours (<= 50 m) whose P2 packet was really received.")

# Fig 1: P2 PRR vs channel count
fig, ax = plt.subplots(figsize=(9, 5.2))
summ = open(os.path.join(HERE, "p2_density_summary.txt"), encoding="utf-8").read()
hdr = [int(v) for v in re.findall(r"(\d+) UAVs", summ.split("\n")[2])]
p1row = [float(v) for v in re.search(r"P1 PRR \(%\)\s+(.*)", summ).group(1).split()]
p1 = dict(zip(hdr, p1row))
ax.plot(xs, [p1[x] for x in xs], color=ORANGE, marker="s", label="P1 discovery (SSA)")
ax.plot(xs, prr, color=BLUE, marker="o", label="P2 data")
ax.legend(loc="lower left")
ax.axvline(CHOSEN, color=INK2, ls=":", lw=1.2)
i = xs.index(CHOSEN)

ax.set_xticks(xs)
ax.set_xlabel("Number of UAVs in 200 x 200 x 80 m")
ax.set_ylabel("PRR (%)")
ax.set_ylim(min(85, min(prr) - 2), 100)
for x, v in zip(xs, prr):
    ax.annotate(f"{v:.1f}", (x, v), xytext=(0, -16), textcoords="offset points", ha="center", color=BLUE, fontsize=10)
ax.set_title("P1 and P2 delivery vs. swarm density")
fig.text(0.01, 0.01, note, fontsize=9, color=INK2, wrap=True)
fig.tight_layout(rect=(0, 0.07, 1, 1))
fig.savefig(os.path.join(OUT, "p2_density_prr.png"), dpi=160)

# Fig 2: failure breakdown vs channel count
fig, ax = plt.subplots(figsize=(9, 5.2))
for k, label, color in KEYS:
    pts = [(x, v) for x, v in zip(xs, fails[k]) if v > 0]   # 0 cannot be drawn on a log axis
    ax.plot([p[0] for p in pts], [p[1] for p in pts], color=color, marker="o", label=label)
ax.axvline(CHOSEN, color=INK2, ls=":", lw=1.2)
ax.set_xticks(xs)
ax.set_xlabel("Number of UAVs in 200 x 200 x 80 m")
ax.set_ylabel("Lost links (% of all links)")
ax.set_yscale("log")
ax.set_yticks([0.1, 0.3, 1, 3, 10, 30, 100])
ax.set_yticklabels(["0.1", "0.3", "1", "3", "10", "30", "100"])
ax.set_title("Why P2 packets are lost (by swarm density)")
ax.legend(loc="upper right", fontsize=10)
fig.text(0.01, 0.01, "Same box, more UAVs: more neighbours inside 50 m compete for the 24 slots x 10 channels, "
         "and the same cell is reused closer by.",
         fontsize=9, color=INK2, wrap=True)
fig.tight_layout(rect=(0, 0.07, 1, 1))
fig.savefig(os.path.join(OUT, "p2_density_failures.png"), dpi=160)
print("saved figures/p2/p2_density_prr.png, figures/p2/p2_density_failures.png")
