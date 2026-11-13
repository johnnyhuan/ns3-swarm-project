#!/usr/bin/env python3
"""
Phase 1 tuning charts: SSA (Sensing-based Slotted Access) and CSMA.

  figures/tuning/p0_ssa_improvement_stages.png   - SSA/CSMA PRR after each design step
  figures/tuning/t01 ... t10                      - one chart per tuning sweep

Data: p1_tuning_runs.csv (config, seed, P1 PRR) - local sweeps, 100 UAVs, 3 seeds each.
Every run: 200x200x80 m, 10 m/s, P1 = 10 ms, BLE 5.4 LE 2M model.

Usage: python3 plot_p1_tuning.py
"""
import csv
import textwrap
import os
import statistics
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "figures", "tuning")
os.makedirs(OUT, exist_ok=True)

# Categorical palette slots 1-3 (validated together: all checks pass on the light surface)
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
SSA_C, CSMA_C = BLUE, ORANGE
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3de"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.size": 12, "axes.titlesize": 14, "axes.titleweight": "bold", "axes.labelsize": 12,
    "axes.edgecolor": GRID, "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": INK2, "ytick.color": INK2, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.8, "axes.axisbelow": True, "legend.frameon": False,
    "lines.linewidth": 2.0, "lines.markersize": 8,
    "axes.spines.top": False, "axes.spines.right": False, "axes.xmargin": 0.08,
})

runs = defaultdict(list)
with open(os.path.join(HERE, "p1_tuning_runs.csv")) as fh:
    for r in csv.DictReader(fh):
        runs[r["config"]].append(float(r["p1_prr_pct"]))


def ms(cfg):
    v = runs[cfg]
    return statistics.mean(v), (statistics.stdev(v) if len(v) > 1 else 0.0)


def save(fig, name, note):
    wrapped = textwrap.fill(note, width=int(fig.get_figwidth() * 14))
    lines_n = wrapped.count("\n") + 1
    fig.text(0.01, 0.01, wrapped, fontsize=9, color=INK2, ha="left", va="bottom")
    fig.tight_layout(rect=(0, 0.02 + 0.03 * lines_n, 1, 1))
    p = os.path.join(OUT, name)
    fig.savefig(p, dpi=200)
    plt.close(fig)
    print("saved", p)


def line(ax, xs, cfgs, color, label, marker="o", ls="-", labels="best", off=(9, 5)):
    """Mean +- std line; direct-label the best point (or all / none)."""
    m = [ms(c)[0] for c in cfgs]
    s = [ms(c)[1] for c in cfgs]
    ax.errorbar(xs, m, yerr=s, color=color, marker=marker, ls=ls, capsize=4, elinewidth=1.2, label=label)
    if isinstance(labels, (list, tuple)):
        idx = labels
    else:
        idx = range(len(m)) if labels == "all" else ([max(range(len(m)), key=lambda i: m[i])] if labels == "best" else [])
    for i in idx:
        ax.annotate(f"{m[i]:.1f}", (xs[i], m[i]), xytext=off, textcoords="offset points",
                    ha="left", va="bottom" if off[1] >= 0 else "top", color=INK, fontsize=10)
    return m


def mark_chosen(ax, x, text="chosen", top=False):
    ax.axvline(x, color=INK2, lw=1, ls=":")
    if top:
        ax.annotate(text, (x, ax.get_ylim()[1]), xytext=(-4, -14), textcoords="offset points", color=INK2,
                    fontsize=10, ha="right")
    else:
        ax.annotate(text, (x, ax.get_ylim()[0]), xytext=(4, 6), textcoords="offset points", color=INK2, fontsize=10)


S3 = "3 s simulation"
S10 = "10 s simulation"
COMMON = "100 UAVs, 200×200×80 m, 10 m/s, mean ± 1 std of 3 seeds"

# ------------------------------------------------------------------ P0: improvement stages
stages = ["Start\n0 dBm,\n300 µs slots", "① +4 dBm,\n160 µs slots", "② No CCA,\n150 µs, RSSI\nsensing",
          "③ Decay 0.8", "④ Timing\nbug fixes", "⑤ Tuned\n(+8 dBm, decay 0.7,\ncounter 2–5→30–90)"]
ssa_v = [58.7, 83.3, 87.5, 91.3, 91.7, 97.2]
csma_v = [75.3, 84.0, 83.6, 83.6, 83.8, 82.1]
fig, ax = plt.subplots(figsize=(10, 5.6))
x = list(range(len(stages)))
ax.plot(x, ssa_v, color=SSA_C, marker="o", label="SSA")
ax.plot(x, csma_v, color=CSMA_C, marker="s", ls="--", label="CSMA")
for i, v in enumerate(ssa_v):
    ax.annotate(f"{v:.1f}%", (i, v), xytext=(0, -20 if i == 1 else 10), textcoords="offset points",
                ha="center", fontsize=10, color=INK)
for i in (0, len(x) - 1):
    ax.annotate(f"{csma_v[i]:.1f}%", (i, csma_v[i]), xytext=(0, -18), textcoords="offset points",
                ha="center", fontsize=10, color=INK)
ax.set_xticks(x, stages, fontsize=10)
ax.set_ylabel("Phase 1 discovery PRR (%)")
ax.set_ylim(50, 102)
ax.set_title("SSA improvement step by step")
ax.legend(loc="lower right")
save(fig, "p0_ssa_improvement_stages.png",
     "100 UAVs. Start–④: 3 s runs (start/① seed 1 only, ②–④ 3 seeds); ⑤: final run, 10 s, 5 seeds. "
     "CSMA shown at the same time point (tuned in ⑤).")

# ------------------------------------------------------------------ T1: CSMA CCA threshold
fig, ax = plt.subplots(figsize=(8, 5))
xs = [-100, -97, -94, -91, -88, -85]
line(ax, xs, [f"cca{-v}" for v in xs], CSMA_C, "CSMA", marker="s")
a = ms("aloha")[0]
ax.axhline(a, color=INK2, ls="--", lw=1.5, label=f"No CCA at all (ALOHA): {a:.1f}")
ax.set_xticks(xs)
ax.set_xlabel("CCA threshold (dBm, RSSI incl. noise)")
ax.set_ylabel("Phase 1 discovery PRR (%)")
ax.set_ylim(75, 88)
mark_chosen(ax, -94, "final: −94 (≈ −97 at 3 s, slightly better at 10 s)")
ax.set_title("CSMA: CCA threshold")
ax.legend(loc="upper right")
save(fig, "t01_csma_cca_threshold.png", f"{COMMON}, {S3}, +4 dBm, single CCA, retry 0.1–0.5 ms")

# ------------------------------------------------------------------ T2: CSMA retry delay
fig, ax = plt.subplots(figsize=(8, 5))
cfgs = ["r0.05-0.2", "cca97", "r0.2-1", "r0.5-2", "r1-4"]
xs = [0.125, 0.3, 0.6, 1.25, 2.5]
line(ax, xs, cfgs, CSMA_C, "CSMA", marker="s", labels="all")
ax.set_xscale("log")
ax.set_xticks(xs, ["0.05–0.2", "0.1–0.5", "0.2–1", "0.5–2", "1–4"])
ax.minorticks_off()
ax.set_xlabel("Random retry delay after a busy CCA (ms)")
ax.set_ylabel("Phase 1 discovery PRR (%)")
ax.set_ylim(72, 88)
mark_chosen(ax, 0.125, "chosen")
ax.set_title("CSMA: retry delay after channel-access failure")
ax.legend(loc="upper right")
save(fig, "t02_csma_retry_delay.png", f"{COMMON}, {S3}, +4 dBm, CCA −97 dBm, single CCA")

# ------------------------------------------------------------------ T3: CSMA backoff
fig, ax = plt.subplots(figsize=(8, 5))
line(ax, [0, 1, 3], ["cca97", "be0b1", "be0b3"], CSMA_C, "MinBE = 0", marker="s")
line(ax, [1, 3], ["be1b1", "be1b3"], BLUE, "MinBE = 1", marker="o", ls="--", labels="none")
m3, s3 = ms("be3b0")
ax.errorbar([0], [m3], yerr=[s3], color=AQUA, marker="^", ls="none", capsize=4, label="MinBE = 3")
ax.set_xticks([0, 1, 2, 3])
ax.set_xlabel("Extra CCA attempts before giving up (MaxBackoffs)")
ax.set_ylabel("Phase 1 discovery PRR (%)")
ax.set_ylim(76, 88)
mark_chosen(ax, 1, "chosen: MinBE 0, 1 extra")
ax.set_title("CSMA: random backoff (unit 60 µs)")
ax.legend(loc="upper right")
save(fig, "t03_csma_backoff.png", f"{COMMON}, {S3}, +4 dBm, CCA −97 dBm, retry 0.1–0.5 ms")

# ------------------------------------------------------------------ T4: TX power (both)
fig, ax = plt.subplots(figsize=(8, 5))
line(ax, [2, 4, 6, 8], ["cs_tx2_c97", "cs_best_tx4", "cs_tx6_c97", "cs_best_tx8"], CSMA_C, "CSMA (tuned backoff)",
     marker="s", labels="all")
line(ax, [4, 8], ["sl_tx4", "sl_tx8"], SSA_C, "SSA (decay 0.8, counter 5–15)", labels="all")
ax.set_xticks([2, 4, 6, 8])
ax.set_xlabel("Phase 1 TX power (dBm)")
ax.set_ylabel("Phase 1 discovery PRR (%)")
ax.set_ylim(78, 96)
ax.set_title("TX power: helps SSA, not CSMA")
ax.legend(loc="center right")
save(fig, "t04_tx_power.png", f"{COMMON}, {S3}, CSMA: CCA −97 dBm; SSA: 150 µs slots")

# ------------------------------------------------------------------ T5: CSMA copies
fig, ax = plt.subplots(figsize=(8, 5))
line(ax, [1, 2, 3], ["cs_best_tx4", "cs_k2_tx4", "cs_k3_tx4"], CSMA_C, "CSMA, +4 dBm", marker="s", labels="all")
line(ax, [1, 2], ["cs_best_tx8", "cs_k2_tx8"], BLUE, "CSMA, +8 dBm", marker="o", ls="--", labels="none")
ax.set_xticks([1, 2, 3])
ax.set_xlabel("Beacon transmissions per cycle")
ax.set_ylabel("Phase 1 discovery PRR (%)")
ax.set_ylim(68, 88)
ax.set_title("CSMA: sending the beacon several times")
ax.legend(loc="lower left")
save(fig, "t05_csma_copies.png", f"{COMMON}, {S3}, CCA −97 dBm, MinBE 0 + 1 extra CCA, retry 0.05–0.2 ms")

# ------------------------------------------------------------------ T6: SSA slot width (early version)
fig, ax = plt.subplots(figsize=(8, 5))
xs, ys = [160, 200, 300], [83.3, 79.4, 69.5]
ax.plot(xs, ys, color=SSA_C, marker="o", label="SSA (early version)")
for xv, yv in zip(xs, ys):
    ax.annotate(f"{yv:.1f}", (xv, yv), xytext=(0, 10), textcoords="offset points", ha="center", fontsize=10)
ax.axhline(84.0, color=CSMA_C, ls="--", label="CSMA (same run): 84.0")
ax.set_xticks([160, 200, 250, 300])
ax.set_xlabel("Slot width (µs)   [slots in 10 ms: 160 µs → 62, 200 µs → 50, 300 µs → 33]")
ax.set_ylabel("Phase 1 discovery PRR (%)")
ax.set_ylim(65, 90)
ax.set_title("SSA: slot width (more, shorter slots)")
ax.legend(loc="lower left")
save(fig, "t06_ssa_slot_width.png",
     "100 UAVs, 3 s, seed 1 only, +4 dBm, early SSA (still with CCA, packet-count sensing); "
     "150 µs became possible after CCA was removed")

# ------------------------------------------------------------------ T7: SSA decay
fig, ax = plt.subplots(figsize=(8, 5))
line(ax, [0.6, 0.7, 0.8, 0.9], ["sl_d06", "sl_d07", "sl_tx8", "sl_d09"], SSA_C, f"counter 5–15, {S3}", labels="all")
line(ax, [0.6, 0.7, 0.8], ["L_i25_r50_150_d06", "L_i25_r50_150_d07", "L_i25_r50_150_d08"], AQUA,
     f"counter 2–5→50–150, {S10}", marker="^", ls="--", labels="all")
ax.set_xticks([0.6, 0.7, 0.8, 0.9])
ax.set_xlabel("Per-cycle decay of sensed slot energy (lower = forget faster)")
ax.set_ylabel("Phase 1 discovery PRR (%)")
ax.set_ylim(88, 100)
mark_chosen(ax, 0.7)
ax.set_title("SSA: sensing memory (decay)")
ax.legend(loc="lower left")
save(fig, "t07_ssa_decay.png", f"{COMMON}, +8 dBm, 150 µs slots, pool 25 %")

# ------------------------------------------------------------------ T8: SSA pool fraction
fig, ax = plt.subplots(figsize=(8, 5))
line(ax, [10, 15, 25, 40], ["sl_pool10", "sl_pool15", "sl_tx8", "sl_pool40"], SSA_C,
     f"decay 0.8, counter 5–15, {S3}", labels="all")
line(ax, [15, 25, 35], ["M_r20_60_p15", "L_i25_r20_60_d07", "M_r20_60_p35"], AQUA,
     f"decay 0.7, counter 2–5→20–60, {S10}", marker="^", ls="--", labels="all")
ax.set_xticks([10, 15, 25, 35, 40])
ax.set_xlabel("Candidate pool: lowest-energy slots considered at reselection (%)")
ax.set_ylabel("Phase 1 discovery PRR (%)")
ax.set_ylim(86, 100)
mark_chosen(ax, 25)
ax.set_title("SSA: candidate pool size")
ax.legend(loc="lower right")
save(fig, "t08_ssa_pool.png", f"{COMMON}, +8 dBm, 150 µs slots")

# ------------------------------------------------------------------ T9: SSA reselection counter
fig, ax = plt.subplots(figsize=(9, 5.2))
line(ax, [3.5, 10, 20, 40], ["sl_r2_5", "sl_tx8", "sl_r10_30", "sl_r20_60_d08"], SSA_C,
     f"decay 0.8, blind first pick, {S3}", labels=[0, 1, 2, 3], off=(9, -8))
line(ax, [20, 30, 40, 60, 100, 200, 1500],
     ["M_r10_30", "M_r15_45", "L_i25_r20_60_d07", "M_r30_90", "L_i25_r50_150_d07", "L_i25_r100_300_d07", "L_i25_r1000"],
     AQUA, f"decay 0.7, first counter 2–5, {S10}", marker="^", ls="--", labels=[3, 5, 6])
ax.set_xscale("log")
ax.set_xticks([3.5, 10, 20, 40, 60, 100, 200, 1500],
              ["2–5", "5–15", "10–30", "20–60", "30–90", "50–150", "100–300", "1000–2000\n(≈ never)"], fontsize=10)
ax.minorticks_off()
ax.set_xlabel("Reselection counter range (cycles; 1 cycle = 20.75 ms)")
ax.set_ylabel("Phase 1 discovery PRR (%)")
ax.set_ylim(76, 100)
mark_chosen(ax, 60, "chosen: 30–90", top=True)
ax.set_title("SSA: how long a node keeps its slot")
ax.legend(loc="lower left", fontsize=10)
save(fig, "t09_ssa_reselection_counter.png", f"{COMMON}, +8 dBm, 150 µs slots, pool 25 %")

# ------------------------------------------------------------------ T10: SSA first counter
fig, ax = plt.subplots(figsize=(8, 5))
line(ax, [0, 1, 2], ["L_sl_r50_150_d07", "L_i13_r50_150_d07", "L_i25_r50_150_d07"], SSA_C,
     "counter 50–150 after the first pick", labels="all")
ax.set_xticks([0, 1, 2], ["same as later\n(50–150)", "1–3", "2–5"])
ax.set_xlabel("Counter after the blind first slot pick (cycles)")
ax.set_ylabel("Phase 1 discovery PRR (%)")
ax.set_ylim(90, 100)
ax.set_xlim(-0.4, 2.4)
ax.set_title("SSA: counter right after the first (blind) slot pick")
ax.legend(loc="lower right")
save(fig, "t10_ssa_first_counter.png", f"{COMMON}, {S10}, +8 dBm, 150 µs slots, decay 0.7, pool 25 %. "
     "Means differ by less than 1 std; 2–5 was kept because it halves the seed-to-seed spread.")
