#!/usr/bin/env python3
"""
Phase 2 basic BLE-style TDMA test. P1 is fixed to the tuned SSA setting.

P2 scheme (what a BLE 5.4 radio with raw/vendor radio access can do):
  - each UAV picks one (slot, channel) per cycle, avoiding the cells its P1 neighbours
    advertised, and announces it inside its P1 beacon (ID 9 bit + slot 8 bit + channel 4 bit)
  - in its slot it broadcasts one 50-byte state packet (61-byte frame, 280 us at LE 2M), no CCA
  - in other slots it tunes to the slot/channel of one of its 5 nearest neighbours (half duplex,
    one radio, one channel at a time); 40 us channel switch + 40 us RX->TX before TX
  - success = the packet of each of my Top-5 nearest neighbours within 50 m is really received

Configs (P2 window ~9.75 ms, 6 data channels):
  legacy slot   13 x 750 us  (old slot length)
  BLE slot      24 x 400 us  (80 us switch/turnaround + 280 us air + 40 us guard)

Usage:
    python3 run_p2_basic.py                 # seed 1, 10 s
    python3 run_p2_basic.py --seeds 1 2 3 --no-push
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
ap.add_argument("--seeds", type=int, nargs="+", default=[1])
ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
ap.add_argument("--no-push", action="store_true")
a = ap.parse_args()

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

# P1 fixed: tuned SSA
BASE = (f"--numNodes={a.nodes} --simTime={a.simtime} --p1Duration=10 --preambleLockDb=6 "
        f"--nodeSpeed=10.0 --spaceSize=200 --spaceZ=80 --autoPush=false "
        f"--enableP1Ssa=true --p1SlotUs=150 --p1TxPower=8 --p1SenseDecay=0.7 "
        f"--p1ReselInitMin=2 --p1ReselInitMax=5 --p1ReselMin=30 --p1ReselMax=90 --p1PoolFrac=0.25 "
        f"--numChannels=6 --p2Duration=9.75")

MODES = [
    ("750us x13 +8dBm", "p2_slot750_tx8", "--dataSlotUs=750 --slotGuardBandUs=50 --p2TxPower=8"),
    ("400us x24 +8dBm", "p2_slot400_tx8", "--dataSlotUs=400 --slotGuardBandUs=30 --p2TxPower=8"),
    ("400us x24 +4dBm", "p2_slot400_tx4", "--dataSlotUs=400 --slotGuardBandUs=30 --p2TxPower=4"),
]
REASONS = ["P1_DISCOVERY_MISS", "TX_DEAFNESS_SAME_SLOT", "RX_DEAFNESS_SLOT_CONFLICT",
           "RECEIVER_CHANNEL_MISMATCH", "PREAMBLE_COLLISION_BUSY_RX", "PREAMBLE_LOW_SINR",
           "PAYLOAD_INTERFERENCE_DROP", "SLOT_BOUNDARY_CUTOFF"]

b = subprocess.run(["./ns3", "build", "scratch/lr-wpan-swarm"], cwd=NS3_DIR,
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
if b.returncode != 0:
    print(b.stdout[-3000:])
    sys.exit("build failed")
run_root = os.path.join(NS3_DIR, "p2_basic_runs")


def run_one(job):
    label, tag, flags, seed = job
    d = os.path.join(run_root, f"{tag}_seed{seed}")
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    p = subprocess.run(["./ns3", "run", "--no-build", "--cwd", d,
                        f"scratch/lr-wpan-swarm {BASE} {flags} --rngRun={seed}"],
                       cwd=NS3_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    r1, r2 = os.path.join(d, "p1_ground_truth_report.txt"), os.path.join(d, "p2_ground_truth_report.txt")
    if p.returncode != 0 or not os.path.exists(r2):
        return job, None, None, p.stdout[-3000:]
    t1 = open(r1, encoding="utf-8", errors="ignore").read()
    t2 = open(r2, encoding="utf-8", errors="ignore").read()
    return job, t1, t2, ""


def prr(text):
    m = re.search(r"Successfully Received \(Delivered\)\s*:\s*\d+\s*\(([\d.]+)%\)", text)
    return float(m.group(1)) if m else float("nan")


def parse(t1, t2):
    row = {"P1": prr(t1), "P2": prr(t2)}
    for r in REASONS:
        m = re.search(rf"\b{r}\s*:\s*(\d+)", t2)
        row[r] = int(m.group(1)) if m else 0
    m = re.search(r"Total Expected P2 Neighbor Links.*?:\s*(\d+)", t2)
    row["LINKS"] = int(m.group(1)) if m else 0
    m = re.search(r"Total Slot Boundary Force Cutoffs\s*:\s*(\d+)", t2)
    row["CUTOFFS"] = int(m.group(1)) if m else 0
    return row


jobs = [(l, t, f, s) for (l, t, f) in MODES for s in a.seeds]
print(f"▶ {len(jobs)} runs, {a.jobs} in parallel, simTime {a.simtime} s ...", flush=True)
runs = {l: {} for (l, _, _) in MODES}
saved = []
with ThreadPoolExecutor(max_workers=a.jobs) as ex:
    for (label, tag, _, seed), t1, t2, err in ex.map(run_one, jobs):
        if t2 is None:
            print(err)
            sys.exit(f"✗ {label} seed {seed} failed")
        runs[label][seed] = parse(t1, t2)
        fname = f"p2_basic_{tag}_seed{seed}.txt"
        with open(os.path.join(PROJECT_DIR, fname), "w", encoding="utf-8") as f:
            f.write(t2)
        saved.append(fname)
        print(f"   {label:16s} seed {seed}: P1 {runs[label][seed]['P1']:.2f}%  P2 {runs[label][seed]['P2']:.2f}%",
              flush=True)

labels = [m[0] for m in MODES]
W = 18
mean = lambda l, k: statistics.mean(runs[l][s][k] for s in a.seeds)
pct = lambda l, k: 100.0 * mean(l, k) / max(1, mean(l, "LINKS"))
hdr = f"{'Metric (mean over seeds)':30s}" + "".join(f"{l:>{W}s}" for l in labels)
lines = [f"P2 basic BLE TDMA | P1 = SSA tuned | {a.nodes} UAVs | simTime {a.simtime}s | seeds {a.seeds}",
         "=" * len(hdr), hdr, "-" * len(hdr),
         f"{'P1 PRR (%)':30s}" + "".join(f"{mean(l, 'P1'):>{W}.2f}" for l in labels),
         f"{'P2 PRR (%)':30s}" + "".join(f"{mean(l, 'P2'):>{W}.2f}" for l in labels),
         "-" * len(hdr), "P2 failure share (% of all links):"]
for r in REASONS:
    lines.append(f"  {r:28s}" + "".join(f"{pct(l, r):>{W}.2f}" for l in labels))
lines.append(f"{'Slot-end force cutoffs':30s}" + "".join(f"{mean(l, 'CUTOFFS'):>{W}.0f}" for l in labels))
lines.append("=" * len(hdr))
lines.append("Settings:")
lines.append(f"  common: {BASE}")
for l, t, f in MODES:
    lines.append(f"  {l:16s}: {f}")
summary = "\n".join(lines) + "\n"
print("\n" + summary)
with open(os.path.join(PROJECT_DIR, "p2_basic_summary.txt"), "w", encoding="utf-8") as f:
    f.write(summary)
shutil.rmtree(run_root, ignore_errors=True)

if a.no_push:
    sys.exit(0)
files = ["p2_basic_summary.txt"] + sorted(saved)
try:
    subprocess.run(["git", "pull", "--rebase", "--autostash", "origin", "main"], cwd=PROJECT_DIR, check=True)
    subprocess.run(["git", "add", "-f"] + files, cwd=PROJECT_DIR, check=True)
    subprocess.run(["git", "commit", "-m", f"data: P2 basic BLE TDMA ({a.nodes} UAVs, {a.simtime}s, seeds {a.seeds})"],
                   cwd=PROJECT_DIR, check=True)
    subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=PROJECT_DIR, check=True)
    print("✓ Results pushed to GitHub")
except subprocess.CalledProcessError as e:
    print(f"⚠ Git upload failed ({e}); results are still saved locally in {PROJECT_DIR}")
