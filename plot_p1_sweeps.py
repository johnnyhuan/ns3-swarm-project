#!/usr/bin/env python3
"""
Fine-grained line charts of the Phase 1 sweeps (run_p1_param_sweeps.py) -> figures/sweeps/.

Each line is the mean over seeds; the shaded band is +-1 standard deviation.
The value used by the tuned SSA setting is marked with a vertical dotted line.
"""
import csv
import os
import statistics
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
OUT = os.path.join(HERE, "figures", "sweeps")
os.makedirs(OUT, exist_ok=True)

# validated categorical slots 1-4 (adjacent CVD dE >= 9, see dataviz palette)
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

rows = list(csv.DictReader(open(os.path.join(RES, "p1_sweeps.csv"))))
data = defaultdict(lambda: defaultdict(list))   # (exp, line) -> x -> [prr]
extra = defaultdict(lambda: defaultdict(list))  # (exp, line, field) -> x -> [v]
for r in rows:
    if r["exp"] == "slot" and float(r["x"]) < 136:
        continue   # beacon (40 us turnaround + 96 us on air = 136 us) does not fit: every beacon is cut
    k = (r["exp"], r["line"])
    data[k][float(r["x"])].append(float(r["prr"]))
    for fld in ("coll", "lowsinr", "cutoffs"):
        extra[(r["exp"], r["line"], fld)][float(r["x"])].append(float(r[fld]))


def stats(d):
    xs = sorted(d)
    m = [statistics.mean(d[x]) for x in xs]
    s = [statistics.stdev(d[x]) if len(d[x]) > 1 else 0.0 for x in xs]
    return xs, m, s


def line(ax, exp, name, color, label=None, marker="o", ls="-", end_label=True):
    if (exp, name) not in data:
        return None
    xs, m, s = stats(data[(exp, name)])
    ax.fill_between(xs, [a - b for a, b in zip(m, s)], [a + b for a, b in zip(m, s)], color=color, alpha=0.15, lw=0)
    ax.plot(xs, m, color=color, marker=marker, ls=ls, label=label or name)
    if end_label:
        ax.annotate(f"{m[-1]:.1f}%", (xs[-1], m[-1]), xytext=(6, 0), textcoords="offset points",
                    va="center", fontsize=10, color=INK)
    return xs, m


def mark(ax, x, text):
    ax.axvline(x, color=INK2, ls=":", lw=1.2)
    ax.annotate(text, (x, ax.get_ylim()[1]), xytext=(4, -14), textcoords="offset points", fontsize=10, color=INK2)


def finish(fig, name, note):
    import textwrap
    lines = textwrap.wrap(note, 110)
    fig.text(0.01, 0.01, "\n".join(lines), fontsize=9, color=INK2, ha="left", va="bottom")
    fig.tight_layout(rect=(0, 0.035 * len(lines) + 0.01, 1, 1))
    fig.savefig(os.path.join(OUT, name), dpi=200)
    plt.close(fig)
    print("saved", name)


NOTE = "100 UAVs, 200×200×80 m, 10 m/s, BLE 5.4 LE 2M model, 10 s, mean ± 1 std of 3 seeds"
TUNED = "others at tuned SSA: 150 µs slots, +8 dBm, decay 0.7, pool 25 %, counter 2–5 → 30–90"

# 1) candidate pool
if ("pool", "SSA") in data:
    fig, ax = plt.subplots(figsize=(8, 5))
    xs, m = line(ax, "pool", "SSA", BLUE, "SSA")
    ax.set_xticks(xs, [f"{int(round(x * 100))}" for x in xs])
    ax.set_xlabel("Candidate pool: lowest-energy slots considered at reselection (%)")
    ax.set_ylabel("Phase 1 discovery PRR (%)")
    ax.set_ylim(min(m) - 2, 100.5)
    mark(ax, 0.25, "used: 25 %")
    ax.set_title("SSA: candidate pool size")
    finish(fig, "s1_pool.png", f"{NOTE}; {TUNED}")

# 2) reselection counter (two-stage vs single-stage)
if ("counter", "two-stage (first 2-5)") in data:
    fig, ax = plt.subplots(figsize=(8.5, 5))
    xs, m1 = line(ax, "counter", "two-stage (first 2-5)", BLUE, "two-stage: first counter 2–5, then N–3N")
    _, m2 = line(ax, "counter", "single-stage", ORANGE, "single-stage: always N–3N", marker="s", ls="--")
    ax.set_xscale("log")
    ax.set_xticks(xs, [f"{int(x)}–{int(3 * x)}" for x in xs], rotation=45, ha="right")
    ax.minorticks_off()
    ax.set_xlabel("Reselection counter range N–3N (cycles, 1 cycle = 20.75 ms)")
    ax.set_ylabel("Phase 1 discovery PRR (%)")
    ax.set_ylim(min(m1 + m2) - 2, 100.5)
    mark(ax, 30, "used: 30–90")
    ax.set_title("SSA: how long a node keeps its slot")
    ax.legend(loc="lower center")
    finish(fig, "s2_counter.png", f"{NOTE}; {TUNED}")

# 3) decay
if ("decay", "SSA") in data:
    fig, ax = plt.subplots(figsize=(8, 5))
    xs, m = line(ax, "decay", "SSA", BLUE, "SSA")
    ax.set_xticks(xs)
    ax.set_xlabel("Per-cycle decay of sensed slot energy (1.0 = all cycles weigh the same)")
    ax.set_ylabel("Phase 1 discovery PRR (%)")
    ax.set_ylim(min(m) - 2, 100.5)
    mark(ax, 0.7, "used: 0.7")
    ax.set_title("SSA: weight of older sensing samples")
    finish(fig, "s3_decay.png", f"{NOTE}; {TUNED}")

# 4) slot width / slot count
if ("slot", "perfect sync") in data:
    fig, ax = plt.subplots(figsize=(8.5, 5.4))
    xs, m1 = line(ax, "slot", "perfect sync", BLUE, "perfect sync")
    r2 = line(ax, "slot", "sync error +-20 us", AQUA, "sync error ±20 µs", marker="s", ls="--")
    lo = min(m1 + (r2[1] if r2 else []))
    ax.set_ylim(lo - 2, 100.5)
    ax.set_xticks(xs)
    ax.set_xlabel("Slot width (µs)")
    ax.set_ylabel("Phase 1 discovery PRR (%)")
    top = ax.secondary_xaxis("top")
    top.set_xticks(xs, [str(int((10000 - 40) // x)) for x in xs])
    top.set_xlabel("Slots per 10 ms Phase 1", color=INK2)
    top.tick_params(colors=INK2)
    mark(ax, 150, "used: 150 µs (66 slots)")
    ax.axvspan(xs[0] - 5, 156, color=INK2, alpha=0.06, lw=0)
    ax.set_title("SSA: slot width vs. number of slots")
    ax.legend(loc="lower left")
    finish(fig, "s4_slot.png", "100 UAVs, 10 s, 3 seeds; slot = 40 µs turnaround + 96 µs beacon + guard (grey: guard < 20 µs; 130 µs does not fit)")

# 5) sync error
if ("sync", "SSA") in data:
    fig, ax = plt.subplots(figsize=(8, 5))
    xs, m = line(ax, "sync", "SSA", BLUE, "SSA (tuned)")
    if ("sync", "CSMA") in data:
        cx, cm, _ = stats(data[("sync", "CSMA")])
        ax.axhline(statistics.mean(cm), color=ORANGE, ls="--", label="CSMA (tuned, needs no sync)")
    ax.axvspan(0, 14, color=BLUE, alpha=0.07, lw=0)
    ax.set_xticks(xs[::2], [f"±{int(x)}" for x in xs[::2]])
    ax.set_xlabel("Per-node clock synchronization error (µs)")
    ax.set_ylabel("Phase 1 discovery PRR (%)")
    ax.set_ylim(75, 100.5)
    ax.text(1, 76, "within slot guard (14 µs)", fontsize=10, color=INK2)
    ax.set_title("SSA: sensitivity to clock synchronization error")
    ax.legend(loc="upper right")
    finish(fig, "s5_sync_error.png", f"{NOTE}; error redrawn per node per cycle")

# 6) density
if ("density", "SSA") in data:
    fig, ax = plt.subplots(figsize=(8, 5))
    xs, ms = line(ax, "density", "SSA", BLUE, "SSA (tuned)")
    _, mc = line(ax, "density", "CSMA", ORANGE, "CSMA (tuned)", marker="s")
    ax.set_xticks(xs)
    ax.set_xlabel("Number of UAVs in the 200×200×80 m airspace")
    ax.set_ylabel("Phase 1 discovery PRR (%)")
    ax.set_ylim(min(mc) - 3, 100.5)
    ax.set_title("Discovery reliability vs. swarm density")
    ax.legend(loc="lower left")
    finish(fig, "s6_density.png", "200×200×80 m, 10 m/s, perfect sync, BLE 5.4 LE 2M model, 10 s, mean ± 1 std of 3 seeds")

# 7) distance (2 m bins)
dpath = os.path.join(RES, "p1_distance_bins.csv")
if os.path.exists(dpath):
    agg = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: [0, 0])))  # line -> seed -> bin -> [tot,suc]
    for r in csv.DictReader(open(dpath)):
        t = agg[r["line"]][r["seed"]][int(r["bin_lo_m"])]
        t[0] += int(r["total"])
        t[1] += int(r["success"])
if os.path.exists(dpath) and agg:
    fig, ax = plt.subplots(figsize=(8.5, 5))
    for name, color, ls, mk in [("SSA tuned", BLUE, "-", "o"), ("SSA default", BLUE, "--", "o"),
                                ("CSMA tuned", ORANGE, "-", "s"), ("CSMA default", ORANGE, "--", "s")]:
        if name not in agg:
            continue
        bins = sorted({b for sd in agg[name].values() for b in sd})
        xs, m, s = [], [], []
        for b in bins:
            vals = [100.0 * sd[b][1] / sd[b][0] for sd in agg[name].values() if sd[b][0] >= 20]
            if vals:
                xs.append(b + 1)
                m.append(statistics.mean(vals))
                s.append(statistics.stdev(vals) if len(vals) > 1 else 0.0)
        ax.fill_between(xs, [a - c for a, c in zip(m, s)], [a + c for a, c in zip(m, s)], color=color, alpha=0.12, lw=0)
        filled = "tuned" in name
        ax.plot(xs, m, color=color, ls=ls, marker=mk, label=name.replace(" tuned", " (tuned)").replace(" default", " (default)"),
                markerfacecolor=color if filled else SURFACE, markeredgewidth=1.5)
        if filled:
            ax.annotate(f"{m[-1]:.1f}%", (xs[-1], m[-1]), xytext=(6, 0), textcoords="offset points", va="center", fontsize=10)
    ax.set_xticks(range(0, 51, 5))
    ax.set_xlim(0, 53)
    ax.set_xlabel("Distance to neighbor (m, 2 m bins)")
    ax.set_ylabel("Phase 1 discovery PRR (%)")
    ax.set_ylim(40, 101)
    ax.set_title("Discovery reliability vs. distance")
    ax.legend(loc="lower left", ncol=2)
    finish(fig, "s7_distance.png", "100 UAVs, 200×200×80 m, 10 m/s, BLE 5.4 LE 2M model, 10 s, mean ± 1 std of 5 seeds")
