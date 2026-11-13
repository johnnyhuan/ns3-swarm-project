#!/usr/bin/env python3
"""
Phase 1 robustness of the tuned CSMA and tuned SSA settings.

  A) clock-sync error: every node's P1 timing is off by U(-E, +E) us, redrawn each cycle
  B) density: 50 / 100 / 150 / 200 UAVs in the same 200 x 200 x 80 m airspace

simTime 10 s, seeds 1-3 by default; runs in parallel; results pushed to GitHub main.

Usage:
    python3 run_p1_robustness.py
    python3 run_p1_robustness.py --seeds 1 2 3 4 5 --jobs 4
    NS3_DIR=~/ns-3-local python3 run_p1_robustness.py --no-push
"""
import argparse
import os
import re
import shutil
import statistics
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

ap = argparse.ArgumentParser()
ap.add_argument("--simtime", type=float, default=10.0)
ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
ap.add_argument("--sync", type=float, nargs="+", default=[0, 10, 20, 30, 40, 60])
ap.add_argument("--nodes", type=int, nargs="+", default=[50, 100, 150, 200])
ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
ap.add_argument("--no-push", action="store_true")
a = ap.parse_args()

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
NS3_DIR = os.path.expanduser(os.environ.get("NS3_DIR", "~/ns-3-dev"))
if not os.path.exists(os.path.join(NS3_DIR, "ns3")):
    sys.exit(f"ns-3 not found at {NS3_DIR} (set NS3_DIR)")

SYNC = ["scratch/lr-wpan-swarm.cc",
        "src/lr-wpan/model/lr-wpan-phy.cc", "src/lr-wpan/model/lr-wpan-phy.h",
        "src/lr-wpan/model/lr-wpan-csmaca.cc", "src/lr-wpan/model/lr-wpan-csmaca.h",
        "src/lr-wpan/model/lr-wpan-mac.cc", "src/lr-wpan/model/lr-wpan-mac.h"]
for rel in SYNC:
    src_f, dst_f = os.path.join(PROJECT_DIR, rel), os.path.join(NS3_DIR, rel)
    if os.path.exists(src_f) and os.path.abspath(src_f) != os.path.abspath(dst_f):
        os.makedirs(os.path.dirname(dst_f), exist_ok=True)
        shutil.copy(src_f, dst_f)

BASE = (f"--simTime={a.simtime} --p1Duration=10 --preambleLockDb=6 --p2TxPower=-2 "
        f"--nodeSpeed=10.0 --numSlots=13 --dataSlotUs=750 --p2Duration=9.75 --numChannels=6 "
        f"--spaceSize=200 --spaceZ=80 --autoPush=false")
CSMA = ("--enableP1Ssa=false --p1TxPower=4 --p1CcaThresholdDbm=-94 "
        "--p1MinBE=0 --p1MaxBackoffs=1 --p1RetryMinMs=0.05 --p1RetryMaxMs=0.2")
SSA = ("--enableP1Ssa=true --p1SlotUs=150 --p1TxPower=8 --p1SenseDecay=0.7 "
      "--p1ReselInitMin=2 --p1ReselInitMax=5 --p1ReselMin=30 --p1ReselMax=90 --p1PoolFrac=0.25")

# config key -> flags (deduplicated across the two experiments)
configs = {}
def cfg(method, n, e):
    key = f"{method}_n{n}_e{e:g}"
    configs[key] = f"{CSMA if method == 'csma' else SSA} --numNodes={n} --p1SyncErrUs={e:g}"
    return key

syncA = {("SSA", e): cfg("ssa", 100, e) for e in a.sync}
syncA.update({("CSMA", e): cfg("csma", 100, e) for e in (0, max(a.sync))})
densB = {(m, n): cfg(m.lower(), n, 0) for m in ("CSMA", "SSA") for n in a.nodes}

print(f"NS3_DIR = {NS3_DIR}")
print("▶ Building ...", flush=True)
b = subprocess.run(["./ns3", "build", "scratch/lr-wpan-swarm"], cwd=NS3_DIR,
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
if b.returncode != 0:
    print(b.stdout[-4000:])
    sys.exit("✗ build failed")

run_root = os.path.join(NS3_DIR, "p1_robust_runs")
shutil.rmtree(run_root, ignore_errors=True)


def run_one(job):
    key, seed = job
    d = os.path.join(run_root, f"{key}_seed{seed}")
    os.makedirs(d, exist_ok=True)
    p = subprocess.run(["./ns3", "run", "--no-build", "--cwd", d,
                        f"scratch/lr-wpan-swarm {BASE} {configs[key]} --rngRun={seed}"],
                       cwd=NS3_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    rpt = os.path.join(d, "p1_ground_truth_report.txt")
    if p.returncode != 0 or not os.path.exists(rpt):
        return job, None, p.stdout[-3000:]
    return job, open(rpt, encoding="utf-8", errors="ignore").read(), ""


def parse(text):
    r = {}
    m = re.search(r"Successfully Received \(Delivered\)\s*:\s*(\d+)\s*\(([\d.]+)%\)", text)
    r["PRR"] = float(m.group(2)) if m else float("nan")
    m = re.search(r"Mean 50m Neighbors per UAV \(Density\):\s*([\d.]+)", text)
    r["NBR"] = float(m.group(1)) if m else float("nan")
    for k, pat in [("COLL", "PREAMBLE_COLLISION_BUSY_RX"), ("LOWSINR", "PREAMBLE_LOW_SINR"),
                   ("ABORT", "SENDER_CSMA_ABORT"), ("CUT", "SLOT_BOUNDARY_CUTOFF")]:
        m = re.search(rf"\b{pat}\s*:\s*(\d+)", text)
        r[k] = int(m.group(1)) if m else 0
    m = re.search(r"Total Expected P1 Neighbor Links.*?:\s*(\d+)", text)
    r["LINKS"] = int(m.group(1)) if m else 0
    return r


jobs = [(k, s) for k in configs for s in a.seeds]
print(f"▶ {len(jobs)} runs, {a.jobs} in parallel ...", flush=True)
res = {k: {} for k in configs}
saved = []
# biggest (slowest) runs first
jobs.sort(key=lambda j: -int(re.search(r"_n(\d+)_", j[0]).group(1)))
with ThreadPoolExecutor(max_workers=a.jobs) as ex:
    for (key, seed), text, err in ex.map(run_one, jobs):
        if text is None:
            print(err)
            sys.exit(f"✗ {key} seed {seed} failed")
        res[key][seed] = parse(text)
        fname = f"p1_robust_{key}_seed{seed}.txt"
        with open(os.path.join(PROJECT_DIR, fname), "w", encoding="utf-8") as f:
            f.write(text)
        saved.append(fname)
        print(f"   {key:22s} seed {seed}: {res[key][seed]['PRR']:.2f}%", flush=True)


def m(key, f="PRR"):
    return statistics.mean(res[key][s][f] for s in a.seeds)


def sd(key):
    v = [res[key][s]["PRR"] for s in a.seeds]
    return statistics.stdev(v) if len(v) > 1 else 0.0


L = [f"P1 robustness | simTime {a.simtime}s | seeds {a.seeds} | tuned CSMA vs tuned SSA", "=" * 78]
L.append("A) Clock-sync error, 100 UAVs (P1 PRR %, mean +- stdev over seeds)")
L.append(f"{'sync error':>12s}{'SSA':>18s}{'CSMA':>18s}{'SSA collisions':>15s}{'SSA low SINR':>13s}")
for e in a.sync:
    k = syncA[("SSA", e)]
    sl = f"{m(k):6.2f} +- {sd(k):4.2f}"
    ck = syncA.get(("CSMA", e))
    cs = f"{m(ck):6.2f} +- {sd(ck):4.2f}" if ck else "-"
    L.append(f"{'+-' + format(e, 'g') + ' us':>12s}{sl:>18s}{cs:>18s}{m(k, 'COLL'):>15.0f}{m(k, 'LOWSINR'):>13.0f}")
L.append("")
L.append("B) Density, perfect sync (P1 PRR %, mean +- stdev over seeds)")
L.append(f"{'UAVs':>6s}{'50m nbrs':>10s}{'SSA':>18s}{'CSMA':>18s}{'gap':>8s}{'CSMA aborts':>13s}")
for n in a.nodes:
    ks, kc = densB[("SSA", n)], densB[("CSMA", n)]
    L.append(f"{n:>6d}{m(ks, 'NBR'):>10.1f}{(format(m(ks), '6.2f') + ' +- ' + format(sd(ks), '4.2f')):>18s}"
             f"{(format(m(kc), '6.2f') + ' +- ' + format(sd(kc), '4.2f')):>18s}{m(ks) - m(kc):>8.2f}{m(kc, 'ABORT'):>13.0f}")
L.append("")
L.append("Slot-end force cutoffs (SSA, all runs): " +
         str(sum(res[k][s]["CUT"] for k in configs if k.startswith("ssa_") for s in a.seeds)))
L.append("=" * 78)
L.append(f"CSMA tuned: {CSMA}")
L.append(f"SSA tuned  : {SSA}")
summary = "\n".join(L) + "\n"
print("\n" + summary)
with open(os.path.join(PROJECT_DIR, "p1_robustness_summary.txt"), "w", encoding="utf-8") as f:
    f.write(summary)

if a.no_push:
    sys.exit(0)
files = ["p1_robustness_summary.txt"] + sorted(saved)
try:
    subprocess.run(["git", "pull", "--rebase", "--autostash", "origin", "main"], cwd=PROJECT_DIR, check=True)
    subprocess.run(["git", "add", "-f"] + files, cwd=PROJECT_DIR, check=True)
    subprocess.run(["git", "commit", "-m", f"data: P1 robustness (sync error, density; {a.simtime}s, seeds {a.seeds})"],
                   cwd=PROJECT_DIR, check=True)
    subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=PROJECT_DIR, check=True)
    print("✓ Results pushed to GitHub")
except subprocess.CalledProcessError as e:
    print(f"⚠ Git upload failed ({e}); results are still saved locally in {PROJECT_DIR}")
