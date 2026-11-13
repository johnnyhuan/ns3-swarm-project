#!/usr/bin/env python3
"""
Fine-grained Phase 1 parameter sweeps for the report charts (one factor at a time
around the tuned settings). Results are appended to CSV files, so an interrupted
sweep can simply be restarted (finished runs are skipped).

  results/p1_sweeps.csv         exp,line,x,seed,prr,coll,lowsinr,cutoffs,late,links
  results/p1_distance_bins.csv  exp,line,seed,bin_lo_m,total,success   (2 m bins)

Run folders are deleted after parsing (a 10 s run writes ~25 MB of per-link CSV).

Usage:
    NS3_DIR=~/ns-3-local python3 run_p1_param_sweeps.py                  # all experiments
    NS3_DIR=~/ns-3-local python3 run_p1_param_sweeps.py --exp pool decay # some of them
"""
import argparse
import csv
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

ap = argparse.ArgumentParser()
ap.add_argument("--exp", nargs="+", default=None)
ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
ap.add_argument("--simtime", type=float, default=10.0)
ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
a = ap.parse_args()

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
NS3_DIR = os.path.expanduser(os.environ.get("NS3_DIR", "~/ns-3-dev"))
if not os.path.exists(os.path.join(NS3_DIR, "ns3")):
    sys.exit(f"ns-3 not found at {NS3_DIR} (set NS3_DIR)")
RES = os.path.join(PROJECT_DIR, "results")
os.makedirs(RES, exist_ok=True)
SWEEP_CSV = os.path.join(RES, "p1_sweeps.csv")
DIST_CSV = os.path.join(RES, "p1_distance_bins.csv")

for rel in ["scratch/lr-wpan-swarm.cc",
            "src/lr-wpan/model/lr-wpan-phy.cc", "src/lr-wpan/model/lr-wpan-phy.h",
            "src/lr-wpan/model/lr-wpan-csmaca.cc", "src/lr-wpan/model/lr-wpan-csmaca.h",
            "src/lr-wpan/model/lr-wpan-mac.cc", "src/lr-wpan/model/lr-wpan-mac.h"]:
    s, d = os.path.join(PROJECT_DIR, rel), os.path.join(NS3_DIR, rel)
    if os.path.exists(s) and os.path.abspath(s) != os.path.abspath(d):
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copy(s, d)

BASE = (f"--simTime={a.simtime} --p1Duration=10 --preambleLockDb=6 --p2TxPower=-2 --nodeSpeed=10.0 "
        f"--numSlots=13 --dataSlotUs=750 --p2Duration=9.75 --numChannels=6 --spaceSize=200 --spaceZ=80 "
        f"--autoPush=false")


def ssa(**kw):
    p = dict(numNodes=100, p1SlotUs=150, p1TxPower=8, p1SenseDecay=0.7, p1ReselInitMin=2, p1ReselInitMax=5,
             p1ReselMin=30, p1ReselMax=90, p1PoolFrac=0.25, p1SyncErrUs=0)
    p.update(kw)
    return "--enableP1Ssa=true " + " ".join(f"--{k}={v:g}" if isinstance(v, float) else f"--{k}={v}"
                                             for k, v in p.items())


def csma(**kw):
    p = dict(numNodes=100, p1TxPower=4, p1CcaThresholdDbm=-94, p1MinBE=0, p1MaxBackoffs=1,
             p1RetryMinMs=0.05, p1RetryMaxMs=0.2, p1SyncErrUs=0)
    p.update(kw)
    return "--enableP1Ssa=false " + " ".join(f"--{k}={v:g}" if isinstance(v, float) else f"--{k}={v}"
                                              for k, v in p.items())


def frange(lo, hi, step):
    n = int(round((hi - lo) / step))
    return [round(lo + i * step, 4) for i in range(n + 1)]


# exp -> list of (line, x, flags)
EXPS = {
    "pool": [("SSA", x, ssa(p1PoolFrac=x)) for x in [0.05, 0.10, 0.15, 0.25, 0.35, 0.45, 0.60]],
    "decay": [("SSA", x, ssa(p1SenseDecay=x)) for x in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]],
    "counter": ([("two-stage (first 2-5)", n, ssa(p1ReselMin=n, p1ReselMax=3 * n))
                 for n in [1, 2, 5, 10, 20, 30, 50, 100]] +
                [("single-stage", n, ssa(p1ReselMin=n, p1ReselMax=3 * n, p1ReselInitMin=-1, p1ReselInitMax=-1))
                 for n in [1, 2, 5, 10, 20, 30, 50, 100]]),
    "slot": ([("perfect sync", x, ssa(p1SlotUs=x)) for x in [130, 140, 150, 170, 200, 250, 300]] +
             [("sync error +-20 us", x, ssa(p1SlotUs=x, p1SyncErrUs=20)) for x in [130, 140, 150, 170, 200, 250, 300]]),
    "sync": ([("SSA", x, ssa(p1SyncErrUs=x)) for x in range(0, 61, 5)] +
             [("CSMA", x, csma(p1SyncErrUs=x)) for x in (0, 30, 60)]),
    "density": ([("SSA", n, ssa(numNodes=n)) for n in range(25, 251, 25)] +
                [("CSMA", n, csma(numNodes=n)) for n in range(25, 251, 25)]),
    "distance": [("SSA tuned", 0, ssa()),
                 ("SSA default", 0, "--enableP1Ssa=true --numNodes=100 --p1SlotUs=150 --p1TxPower=4 "
                                    "--p1SenseDecay=0.8 --p1ReselMin=5 --p1ReselMax=15 --p1PoolFrac=0.25"),
                 ("CSMA tuned", 0, csma()),
                 ("CSMA default", 0, "--enableP1Ssa=false --numNodes=100 --p1TxPower=4 --p1CcaThresholdDbm=-97")],
}
DIST_SEEDS = [1, 2, 3, 4, 5]
exps = a.exp or list(EXPS)

done = set()
if os.path.exists(SWEEP_CSV):
    with open(SWEEP_CSV) as f:
        for r in csv.DictReader(f):
            done.add((r["exp"], r["line"], float(r["x"]), int(r["seed"])))
else:
    with open(SWEEP_CSV, "w", newline="") as f:
        csv.writer(f).writerow(["exp", "line", "x", "seed", "prr", "coll", "lowsinr", "cutoffs", "late", "links"])
if not os.path.exists(DIST_CSV):
    with open(DIST_CSV, "w", newline="") as f:
        csv.writer(f).writerow(["exp", "line", "seed", "bin_lo_m", "total", "success"])

jobs = []
for e in exps:
    for line, x, flags in EXPS[e]:
        for s in (DIST_SEEDS if e == "distance" else a.seeds):
            if (e, line, float(x), s) not in done:
                jobs.append((e, line, x, s, flags))
nodes_of = lambda j: int(re.search(r"--numNodes=(\d+)", j[4]).group(1))
jobs.sort(key=lambda j: -nodes_of(j))   # slowest first
print(f"NS3_DIR={NS3_DIR}  {len(jobs)} runs to do ({len(done)} already done), {a.jobs} parallel", flush=True)
if not jobs:
    sys.exit(0)

b = subprocess.run(["./ns3", "build", "scratch/lr-wpan-swarm"], cwd=NS3_DIR,
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
if b.returncode != 0:
    print(b.stdout[-3000:])
    sys.exit("build failed")

root = os.path.join(NS3_DIR, "p1_sweep_runs")
os.makedirs(root, exist_ok=True)


def num(pat, text, cast=int, default=0):
    m = re.search(pat, text)
    return cast(m.group(1)) if m else default


def run(job):
    e, line, x, s, flags = job
    d = os.path.join(root, re.sub(r"[^A-Za-z0-9.]+", "_", f"{e}_{line}_{x}_s{s}"))
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    p = subprocess.run(["./ns3", "run", "--no-build", "--cwd", d, f"scratch/lr-wpan-swarm {BASE} {flags} --rngRun={s}"],
                       cwd=NS3_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    rpt = os.path.join(d, "p1_ground_truth_report.txt")
    if p.returncode != 0 or not os.path.exists(rpt):
        tail = p.stdout[-1500:]
        shutil.rmtree(d, ignore_errors=True)
        return job, None, None, tail
    t = open(rpt, encoding="utf-8", errors="ignore").read()
    row = [e, line, x, s,
           num(r"Successfully Received \(Delivered\)\s*:\s*\d+\s*\(([\d.]+)%\)", t, float, float("nan")),
           num(r"\bPREAMBLE_COLLISION_BUSY_RX\s*:\s*(\d+)", t), num(r"\bPREAMBLE_LOW_SINR\s*:\s*(\d+)", t),
           num(r"P1 Slot Boundary Force Cutoffs\s*:\s*(\d+)", t), num(r"P1 Beacons Not Started Within Slot\s*:\s*(\d+)", t),
           num(r"Total Expected P1 Neighbor Links.*?:\s*(\d+)", t)]
    bins = None
    if e == "distance":
        tot, suc = [0] * 25, [0] * 25
        with open(os.path.join(d, "p1_exact_drop_reasons.csv")) as f:
            for r in csv.DictReader(f):
                k = min(24, int(float(r["Distance_m"]) // 2))
                tot[k] += 1
                suc[k] += r["Status"] == "SUCCESS"
        bins = [[e, line, s, 2 * k, tot[k], suc[k]] for k in range(25)]
    shutil.rmtree(d, ignore_errors=True)
    return job, row, bins, ""


fails = 0
with ThreadPoolExecutor(max_workers=a.jobs) as ex:
    for i, (job, row, bins, err) in enumerate(ex.map(run, jobs), 1):
        if row is None:
            fails += 1
            print(f"✗ {job[0]} {job[1]} x={job[2]} seed {job[3]} failed\n{err}", flush=True)
            continue
        with open(SWEEP_CSV, "a", newline="") as f:
            csv.writer(f).writerow(row)
        if bins:
            with open(DIST_CSV, "a", newline="") as f:
                csv.writer(f).writerows(bins)
        print(f"[{i}/{len(jobs)}] {job[0]:8s} {job[1]:24s} x={job[2]:<6g} seed {job[3]}: {row[4]:.2f}%", flush=True)
print(f"done, {fails} failed")
