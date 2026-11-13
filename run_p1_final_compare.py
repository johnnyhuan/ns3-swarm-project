#!/usr/bin/env python3
"""
Phase 1 final comparison: CSMA vs SSA, each at its default and at its tuned (best) setting.

All runs: 100 UAVs, 200x200x80 m, 10 m/s, P1 = 10 ms, BLE 5.4 LE 2M model, simTime 10 s.
Runs are executed in parallel (one working directory per run) and the results are
pushed to GitHub main.

Usage:
    python3 run_p1_final_compare.py                    # seeds 1-5, simTime 10 s
    python3 run_p1_final_compare.py --seeds 1 2 3 --simtime 10 --jobs 4
    python3 run_p1_final_compare.py --no-push          # local check, no git
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
ap.add_argument("--nodes", type=int, default=100)
ap.add_argument("--simtime", type=float, default=10.0)
ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4, 5])
ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
ap.add_argument("--no-push", action="store_true")
a = ap.parse_args()

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
NS3_DIR = os.environ.get("NS3_DIR", os.path.expanduser("~/ns-3-dev"))
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

BASE = (f"--numNodes={a.nodes} --simTime={a.simtime} --p1Duration=10 --preambleLockDb=6 "
        f"--p2TxPower=-2 --nodeSpeed=10.0 --numSlots=13 --dataSlotUs=750 --p2Duration=9.75 "
        f"--numChannels=6 --spaceSize=200 --spaceZ=80 --autoPush=false")

# name, tag, flags
MODES = [
    ("CSMA default", "csma_default",
     "--enableP1Ssa=false --p1TxPower=4 --p1CcaThresholdDbm=-97"),
    ("CSMA tuned", "csma_tuned",
     "--enableP1Ssa=false --p1TxPower=4 --p1CcaThresholdDbm=-94 "
     "--p1MinBE=0 --p1MaxBackoffs=1 --p1RetryMinMs=0.05 --p1RetryMaxMs=0.2"),
    ("SSA default", "ssa_default",
     "--enableP1Ssa=true --p1SlotUs=150 --p1TxPower=4 --p1SenseDecay=0.8 "
     "--p1ReselMin=5 --p1ReselMax=15 --p1PoolFrac=0.25"),
    ("SSA tuned", "ssa_tuned",
     "--enableP1Ssa=true --p1SlotUs=150 --p1TxPower=8 --p1SenseDecay=0.7 "
     "--p1ReselInitMin=2 --p1ReselInitMax=5 --p1ReselMin=30 --p1ReselMax=90 --p1PoolFrac=0.25"),
]

REASONS = ["SENDER_CSMA_ABORT", "RX_DEAFNESS_BUSY_TX", "PREAMBLE_COLLISION_BUSY_RX",
           "PREAMBLE_LOW_SINR", "PAYLOAD_INTERFERENCE_CORRUPTION", "SLOT_BOUNDARY_CUTOFF"]
BRACKETS = ["0-10m", "10-20m", "20-30m", "30-40m", "40-50m"]

print(f"NS3_DIR = {NS3_DIR}")
print("▶ Building ...", flush=True)
b = subprocess.run(["./ns3", "build", "scratch/lr-wpan-swarm"], cwd=NS3_DIR,
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
if b.returncode != 0:
    print(b.stdout[-4000:])
    sys.exit("✗ build failed")

run_root = os.path.join(NS3_DIR, "p1_final_runs")
shutil.rmtree(run_root, ignore_errors=True)


def run_one(job):
    label, tag, flags, seed = job
    d = os.path.join(run_root, f"{tag}_seed{seed}")
    os.makedirs(d, exist_ok=True)
    args = f"scratch/lr-wpan-swarm {BASE} {flags} --rngRun={seed}"
    p = subprocess.run(["./ns3", "run", "--no-build", "--cwd", d, args], cwd=NS3_DIR,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    rpt = os.path.join(d, "p1_ground_truth_report.txt")
    if p.returncode != 0 or not os.path.exists(rpt):
        return job, None, p.stdout[-3000:]
    return job, open(rpt, encoding="utf-8", errors="ignore").read(), ""


def parse(text):
    row = {}
    m = re.search(r"Successfully Received \(Delivered\)\s*:\s*(\d+)\s*\(([\d.]+)%\)", text)
    row["PRR"] = float(m.group(2)) if m else float("nan")
    for r in REASONS:
        m = re.search(rf"\b{r}\s*:\s*(\d+)", text)
        row[r] = int(m.group(1)) if m else 0
    for bk in BRACKETS:
        m = re.search(rf"^\s*{bk}\s*\|\s*(\d+)\s*\|\s*(\d+)", text, re.M)
        row[bk] = (100.0 * int(m.group(2)) / int(m.group(1))) if m and int(m.group(1)) else float("nan")
    m = re.search(r"P1 Slot Boundary Force Cutoffs\s*:\s*(\d+)", text)
    row["CUTOFFS"] = int(m.group(1)) if m else 0
    return row


jobs = [(l, t, f, s) for (l, t, f) in MODES for s in a.seeds]
print(f"▶ {len(jobs)} runs, {a.jobs} in parallel, simTime {a.simtime} s ...", flush=True)
runs = {l: {} for (l, _, _) in MODES}
saved = []
with ThreadPoolExecutor(max_workers=a.jobs) as ex:
    for (label, tag, _, seed), text, err in ex.map(run_one, jobs):
        if text is None:
            print(err)
            sys.exit(f"✗ {label} seed {seed} failed")
        runs[label][seed] = parse(text)
        fname = f"p1_final_{tag}_seed{seed}.txt"
        with open(os.path.join(PROJECT_DIR, fname), "w", encoding="utf-8") as f:
            f.write(text)
        saved.append(fname)
        print(f"   {label:14s} seed {seed}: {runs[label][seed]['PRR']:.2f}%", flush=True)

labels = [m[0] for m in MODES]
W = 15
mean = lambda l, k: statistics.mean(runs[l][s][k] for s in a.seeds)
sep = "=" * (34 + W * len(labels))
lines = [f"P1 final comparison | {a.nodes} UAVs | simTime {a.simtime}s | seeds {a.seeds}", sep]
hdr = f"{'Metric (mean over seeds)':34s}" + "".join(f"{l:>{W}s}" for l in labels)
lines += [hdr, "-" * len(hdr)]
lines.append(f"{'P1 PRR (%) mean':34s}" + "".join(f"{mean(l, 'PRR'):>{W}.2f}" for l in labels))
lines.append(f"{'P1 PRR (%) stdev':34s}" + "".join(
    f"{(statistics.stdev([runs[l][s]['PRR'] for s in a.seeds]) if len(a.seeds) > 1 else 0):>{W}.2f}" for l in labels))
lines.append(f"{'P1 PRR (%) min..max':34s}" + "".join(
    f"{(format(min(runs[l][s]['PRR'] for s in a.seeds), '.1f') + '..' + format(max(runs[l][s]['PRR'] for s in a.seeds), '.1f')):>{W}s}"
    for l in labels))
for r in REASONS:
    lines.append(f"{r:34s}" + "".join(f"{mean(l, r):>{W}.0f}" for l in labels))
lines.append(f"{'Slot-end force cutoffs':34s}" + "".join(f"{mean(l, 'CUTOFFS'):>{W}.1f}" for l in labels))
lines.append("-" * len(hdr))
for bk in BRACKETS:
    lines.append(f"{'PRR ' + bk + ' (%)':34s}" + "".join(f"{mean(l, bk):>{W}.1f}" for l in labels))
lines.append("-" * len(hdr))
for s in a.seeds:
    lines.append(f"{'PRR seed ' + str(s) + ' (%)':34s}" + "".join(f"{runs[l][s]['PRR']:>{W}.2f}" for l in labels))
lines.append(sep)
lines.append("Settings:")
for l, t, f in MODES:
    lines.append(f"  {l:14s}: {f}")
summary = "\n".join(lines) + "\n"
print("\n" + summary)

with open(os.path.join(PROJECT_DIR, "p1_final_compare_summary.txt"), "w", encoding="utf-8") as f:
    f.write(summary)

if a.no_push:
    sys.exit(0)
files = ["p1_final_compare_summary.txt"] + sorted(saved)
try:
    subprocess.run(["git", "pull", "--rebase", "--autostash", "origin", "main"], cwd=PROJECT_DIR, check=True)
    subprocess.run(["git", "add", "-f"] + files, cwd=PROJECT_DIR, check=True)
    subprocess.run(["git", "commit", "-m",
                    f"data: P1 final comparison ({a.nodes} UAVs, {a.simtime}s, seeds {a.seeds})"],
                   cwd=PROJECT_DIR, check=True)
    subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=PROJECT_DIR, check=True)
    print("✓ Results pushed to GitHub")
except subprocess.CalledProcessError as e:
    print(f"⚠ Git upload failed ({e}); results are still saved locally in {PROJECT_DIR}")
