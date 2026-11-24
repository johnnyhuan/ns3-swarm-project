#!/usr/bin/env python3
"""
Re-tune CSMA (P1), SSA (P1) and P2 for the nRF54L15 DK conditions
(QFN48: max TX power +7 dBm, BLE 2M sensitivity -94 dBm).

Method (one-factor-at-a-time around the current best, repeated):
  - each pass sweeps every parameter of a method while all others stay at the current best
    ("center"); all sweeps of a pass run in parallel
  - a parameter moves to a new value only if that value beats the center by >= MIN_GAIN points
    (averaged over the tuning seeds); otherwise it stays (guards against seed noise)
  - P2 slots (24 x 400 us) and data channels (10) are fixed (user's resource budget)
  - resource parameters (TX power, beacon copies, extra listening) use the
    knee rule instead: the cheapest value within MIN_GAIN of the best, since more resources always
    help a little and the plain maximum would always win
  - pass 2 repeats the sweeps around the new center, which catches interactions
  - CSMA and SSA are tuned first (objective: P1 PRR); P2 is then tuned on top of the new SSA
    (objective: P2 PRR)
  - tuning seeds (101, 102) are NOT the seeds of the final comparison (1..5), so the final
    numbers are not measured on the seeds the parameters were picked on

Results: results/tune_runs_<simtime>s.csv (every run, also the cache to resume), tune_summary.txt.

Usage:
    python3 run_tune.py                    # all stages, pushes results
    python3 run_tune.py --stages p1 --no-push
"""
import argparse
import csv
import os
import re
import shutil
import statistics
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

ap = argparse.ArgumentParser()
ap.add_argument("--stages", nargs="+", default=["p1", "p2"], choices=["p1", "p2"])
ap.add_argument("--seeds", type=int, nargs="+", default=[101, 102])
ap.add_argument("--passes", type=int, default=2)
ap.add_argument("--simtime", type=float, default=10.0)
ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
ap.add_argument("--no-push", action="store_true")
a = ap.parse_args()
MIN_GAIN = 0.2

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
NS3_DIR = os.path.expanduser(os.environ.get("NS3_DIR", "~/ns-3-dev"))
if not os.path.exists(os.path.join(NS3_DIR, "ns3")):
    sys.exit(f"ns-3 not found at {NS3_DIR} (set NS3_DIR)")
for rel in ["scratch/lr-wpan-swarm.cc",
            "src/lr-wpan/model/lr-wpan-phy.cc", "src/lr-wpan/model/lr-wpan-phy.h",
            "src/lr-wpan/model/lr-wpan-csmaca.cc", "src/lr-wpan/model/lr-wpan-csmaca.h",
            "src/lr-wpan/model/lr-wpan-mac.cc", "src/lr-wpan/model/lr-wpan-mac.h"]:
    s, d = os.path.join(PROJECT_DIR, rel), os.path.join(NS3_DIR, rel)
    if os.path.exists(s) and os.path.abspath(s) != os.path.abspath(d):
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copy(s, d)

COMMON = (f"--numNodes=100 --simTime={a.simtime} --nodeSpeed=10.0 --spaceSize=200 --spaceZ=80 "
          f"--p1Duration=10 --preambleLockDb=6 --autoPush=false --rxSensitivityDbm=-94")

# Each parameter: (name, list of values, start value, function value -> flags)
# Resource parameters (cost grows along the value list: energy, air time, cycle length, spectrum)
# use the knee rule: the cheapest value within MIN_GAIN of the best. Without it the search always
# takes the maximum (more power / slots / channels always helps a little).
COST_PARAMS = {"P1 power (dBm)", "beacon copies per cycle", "P2 power (dBm)", "extra neighbours listened"}
def f1(flag):
    return lambda v: f"--{flag}={v}"


CSMA = dict(fixed="--enableP1Ssa=false", objective="P1", params=[
    ("P1 power (dBm)", [2, 3, 4, 5, 6, 7], 4, f1("p1TxPower")),
    ("CCA threshold (dBm)", [-98, -96, -94, -92, -90, -88], -94, f1("p1CcaThresholdDbm")),
    ("extra CCA attempts", [0, 1, 2, 3], 1, f1("p1MaxBackoffs")),
    ("min backoff exponent", [0, 1, 2], 0, f1("p1MinBE")),
    ("retry window (ms)", ["0.02-0.1", "0.05-0.2", "0.1-0.5", "0.2-1.0"], "0.05-0.2",
     lambda v: f"--p1RetryMinMs={v.split('-')[0]} --p1RetryMaxMs={v.split('-')[1]}"),
    ("beacon copies per cycle", [1, 2], 1, f1("p1Copies")),
])
SSA = dict(fixed="--enableP1Ssa=true", objective="P1", params=[
    ("P1 power (dBm)", [3, 4, 5, 6, 7], 7, f1("p1TxPower")),
    ("slot length (us)", [140, 150, 170, 200], 150, f1("p1SlotUs")),
    ("candidate pool", [0.1, 0.15, 0.25, 0.35, 0.5], 0.25, f1("p1PoolFrac")),
    ("RSSI memory decay", [0.3, 0.5, 0.6, 0.7, 0.8, 0.9], 0.7, f1("p1SenseDecay")),
    ("reselection counter (cycles)", ["10-30", "20-60", "30-90", "50-150", "100-300"], "30-90",
     lambda v: f"--p1ReselMin={v.split('-')[0]} --p1ReselMax={v.split('-')[1]}"),
    ("first-pick counter (cycles)", ["off", "1-3", "2-5", "5-10"], "2-5",
     lambda v: "--p1ReselInitMin=-1 --p1ReselInitMax=-1" if v == "off"
     else f"--p1ReselInitMin={v.split('-')[0]} --p1ReselInitMax={v.split('-')[1]}"),
])
# P2 slots (24 x 400 us) and data channels (10) are a fixed resource budget chosen by the user
P2 = dict(fixed="--dataSlotUs=400 --slotGuardBandUs=30 --p2Copies=2 --p2SmartPick=true --numSlots=24 --numChannels=10",
          objective="P2", params=[
    ("P2 power (dBm)", [2, 3, 4, 5, 6, 7], 4, f1("p2TxPower")),
    ("extra neighbours listened", [1, 2, 3, 4, 5], 3, f1("p2ExtraRx")),
    ("slot-avoid distance (m)", [40, 45, 50, 55, 60, 70], 50, f1("p1AvoidDist")),
])


def flags_of(method, center):
    return " ".join([method["fixed"]] + [fn(center[name]) for name, _, _, fn in method["params"]])


def default_center(method):
    return {name: start for name, _, start, _ in method["params"]}


# ---------------- run cache ----------------
CSV_PATH = os.path.join(PROJECT_DIR, "results", f"tune_runs_{a.simtime:g}s.csv")
os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
cache = {}
if os.path.exists(CSV_PATH):
    with open(CSV_PATH, newline="") as f:
        for r in csv.DictReader(f):
            cache[(r["flags"], int(r["seed"]))] = (float(r["P1"]), float(r["P2"]))

b = subprocess.run(["./ns3", "build", "scratch/lr-wpan-swarm"], cwd=NS3_DIR,
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
if b.returncode != 0:
    print(b.stdout[-3000:])
    sys.exit("build failed")
run_root = os.path.join(NS3_DIR, "tune_runs")
os.makedirs(run_root, exist_ok=True)


def prr(text):
    m = re.search(r"Successfully Received \(Delivered\)\s*:\s*\d+\s*\(([\d.]+)%\)", text)
    return float(m.group(1)) if m else float("nan")


def run_one(job):
    flags, seed = job
    tag = f"r{abs(hash((flags, seed))) % 10**10}"
    d = os.path.join(run_root, tag)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    p = subprocess.run(["./ns3", "run", "--no-build", "--cwd", d,
                        f"scratch/lr-wpan-swarm {COMMON} {flags} --rngRun={seed}"],
                       cwd=NS3_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        t1 = open(os.path.join(d, "p1_ground_truth_report.txt"), errors="ignore").read()
        t2 = open(os.path.join(d, "p2_ground_truth_report.txt"), errors="ignore").read()
        res = (prr(t1), prr(t2))
    except OSError:
        res = (float("nan"), float("nan"))
    shutil.rmtree(d, ignore_errors=True)
    return job, res, p.returncode


def run_batch(jobs):
    todo = sorted({j for j in jobs if j not in cache})
    if not todo:
        return
    print(f"   ▶ {len(todo)} runs ({len(jobs) - len(todo)} cached), {a.jobs} in parallel", flush=True)
    new = not os.path.exists(CSV_PATH)
    with open(CSV_PATH, "a", newline="") as f, ThreadPoolExecutor(max_workers=a.jobs) as ex:
        w = csv.writer(f)
        if new:
            w.writerow(["flags", "seed", "P1", "P2"])
        for (flags, seed), res, rc in ex.map(run_one, todo):
            cache[(flags, seed)] = res
            w.writerow([flags, seed, res[0], res[1]])
            f.flush()
            if rc != 0 or res[0] != res[0]:
                print(f"     ✗ failed: {flags} seed {seed}", flush=True)


def score(flags, objective):
    vals = [cache[(flags, s)][0 if objective == "P1" else 1] for s in a.seeds]
    vals = [v for v in vals if v == v]
    return statistics.mean(vals) if vals else float("-inf")


report = [f"Re-tuning for nRF54L15 DK (QFN48): TX <= +7 dBm, sensitivity -94 dBm | 100 UAVs, {a.simtime} s, "
          f"tuning seeds {a.seeds} | move only if >= {MIN_GAIN} pt better; resource parameters: cheapest value "
          f"within {MIN_GAIN} pt of the best | * = center", "=" * 100]


def tune(label, method, extra_fixed=""):
    """Jacobi-style one-factor sweeps around the center, `passes` times."""
    center = default_center(method)
    m = dict(method, fixed=(method["fixed"] + " " + extra_fixed).strip())
    obj = m["objective"]
    history = []
    for p in range(1, a.passes + 1):
        jobs = []
        sweeps = {}
        for name, values, _, _ in m["params"]:
            sweeps[name] = []
            for v in values:
                c = dict(center, **{name: v})
                fl = flags_of(m, c)
                sweeps[name].append((v, fl))
                jobs += [(fl, s) for s in a.seeds]
        print(f"▶ {label} pass {p}", flush=True)
        run_batch(jobs)
        base = score(flags_of(m, center), obj)
        new_center = dict(center)
        lines = [f"{label} pass {p}: center {obj} PRR {base:.2f}%"]
        for name, vals in sweeps.items():
            scored = [(v, score(fl, obj)) for v, fl in vals]
            best_v, best_s = max(scored, key=lambda x: x[1])
            if name in COST_PARAMS:
                # knee rule: cheapest value within MIN_GAIN of the best
                knee_v = next(v for v, sc in scored if sc >= best_s - MIN_GAIN)
                move = knee_v != center[name]
                if move:
                    new_center[name] = knee_v
            else:
                move = best_s - base >= MIN_GAIN and best_v != center[name]
                if move:
                    new_center[name] = best_v
            lines.append(f"  {name:30s} " + "  ".join(
                f"{v}:{s:.2f}{'*' if v == center[name] else ''}" for v, s in scored)
                + f"   -> {new_center[name]}{'  (moved)' if move else ''}{'  [knee rule]' if name in COST_PARAMS else ''}")
        # check the combined center (several moves at once may interact)
        if new_center != center:
            fl = flags_of(m, new_center)
            run_batch([(fl, s) for s in a.seeds])
            comb = score(fl, obj)
            lines.append(f"  combined new center: {comb:.2f}% (was {base:.2f}%)")
            if comb < base:
                # fall back: keep only the single best move
                best_single = max(((n, score(flags_of(m, dict(center, **{n: new_center[n]})), obj))
                                   for n in new_center if new_center[n] != center[n]), key=lambda x: x[1])
                new_center = dict(center, **{best_single[0]: new_center[best_single[0]]})
                lines.append(f"  combined was worse -> keep only the best single move: {best_single[0]}")
        history += lines
        print("\n".join(lines), flush=True)
        if new_center == center:
            history.append(f"  converged after pass {p}")
            break
        center = new_center
    final = score(flags_of(m, center), obj)
    start = score(flags_of(m, default_center(method)), obj)
    history.append(f"{label} FINAL: {start:.2f}% (old setting) -> {final:.2f}% (tuned) on tuning seeds")
    history.append(f"  flags: {flags_of(m, center)}")
    report.extend(history + [""])
    return center, flags_of(m, center)


best = {}
# P2 as it runs while P1 is tuned (same string as the cached runs)
P2_FOR_P1 = ("--dataSlotUs=400 --slotGuardBandUs=30 --p2Copies=2 --p2SmartPick=true --p2TxPower=4 "
             "--numSlots=24 --numChannels=10 --p2ExtraRx=3 --p1AvoidDist=50")
if "p1" in a.stages:
    # P1 methods are tuned with the current P2 in place (so the cycle is identical); run both in one pool
    best["CSMA"] = tune("CSMA", CSMA, extra_fixed=P2_FOR_P1)
    best["SSA"] = tune("SSA", SSA, extra_fixed=P2_FOR_P1)
if "p2" in a.stages:
    if "SSA" in best:
        ssa_flags = flags_of(SSA, best["SSA"][0])
    else:
        ssa_flags = flags_of(SSA, default_center(SSA))
    best["P2"] = tune("P2", P2, extra_fixed=ssa_flags)

summary = "\n".join(report) + "\n"
print("\n" + summary)
with open(os.path.join(PROJECT_DIR, "tune_summary.txt"), "w", encoding="utf-8") as f:
    f.write(summary)
shutil.rmtree(run_root, ignore_errors=True)

if a.no_push:
    sys.exit(0)
try:
    subprocess.run(["git", "pull", "--rebase", "--autostash", "origin", "main"], cwd=PROJECT_DIR, check=True)
    subprocess.run(["git", "add", "-f", "tune_summary.txt", os.path.relpath(CSV_PATH, PROJECT_DIR), "run_tune.py"], cwd=PROJECT_DIR, check=True)
    subprocess.run(["git", "commit", "-m", f"data: re-tune {' '.join(a.stages)} for +7 dBm / -94 dBm (seeds {a.seeds})"],
                   cwd=PROJECT_DIR, check=True)
    subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=PROJECT_DIR, check=True)
    print("✓ Results pushed to GitHub")
except subprocess.CalledProcessError as e:
    print(f"⚠ Git upload failed ({e}); results are still saved locally in {PROJECT_DIR}")
