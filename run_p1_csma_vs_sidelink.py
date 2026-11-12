#!/usr/bin/env python3
"""
Phase 1: CSMA-CA vs Sidelink-style S-SPS (BLE 5.4 LE 2M model), averaged over several seeds.

Sidelink: no CCA, RSSI-based slot sensing, slot width(s) given by --slots.
Every (mode, seed) runs on the same topology for that seed; results are averaged
and pushed to GitHub main.

Usage:
    python3 run_p1_csma_vs_sidelink.py                       # 100 UAVs, 3 s, +4 dBm, CCA -97, SL 150 us x decay 1.0/0.8, seeds 1 2 3
    python3 run_p1_csma_vs_sidelink.py --slots 150 160 --seeds 1 2 3 4 5
"""
import argparse
import os
import re
import shutil
import statistics
import subprocess
import sys

ap = argparse.ArgumentParser()
ap.add_argument("--nodes", type=int, default=100)
ap.add_argument("--simtime", type=float, default=3.0)
ap.add_argument("--txpower", type=float, default=4.0)
ap.add_argument("--cca", type=float, default=-97.0)
ap.add_argument("--slots", type=float, nargs="+", default=[150.0])
ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
ap.add_argument("--decays", type=float, nargs="+", default=[1.0, 0.8],
                help="Sidelink per-cycle sensing decay values (1.0 = equal weights)")
ap.add_argument("--no-csma", action="store_true", help="skip the CSMA baseline")
a = ap.parse_args()

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
NS3_DIR = os.path.expanduser("~/ns-3-dev")
if not os.path.exists(NS3_DIR):
    NS3_DIR = PROJECT_DIR

for rel_path in ["scratch/lr-wpan-swarm.cc",
                 "src/lr-wpan/model/lr-wpan-phy.cc",
                 "src/lr-wpan/model/lr-wpan-phy.h",
                 "src/lr-wpan/model/lr-wpan-csmaca.cc",
                 "src/lr-wpan/model/lr-wpan-csmaca.h"]:
    src_f = os.path.join(PROJECT_DIR, rel_path)
    dst_f = os.path.join(NS3_DIR, rel_path)
    if os.path.exists(src_f) and os.path.abspath(src_f) != os.path.abspath(dst_f):
        os.makedirs(os.path.dirname(dst_f), exist_ok=True)
        shutil.copy(src_f, dst_f)

REASONS = ["SUCCESS", "SENDER_CSMA_ABORT", "RX_DEAFNESS_BUSY_TX",
           "PREAMBLE_COLLISION_BUSY_RX", "PREAMBLE_LOW_SINR",
           "RADIO_TURNAROUND_BUSY", "PAYLOAD_INTERFERENCE_CORRUPTION", "SLOT_BOUNDARY_CUTOFF"]
BRACKETS = ["0-10m", "10-20m", "20-30m", "30-40m", "40-50m"]

MODES = ([] if a.no_csma else [("CSMA", "csma", "--enableP1Sidelink=false")]) + [
    (f"SL{s:g} d{d:g}", f"sidelink_{s:g}us_decay{d:g}",
     f"--enableP1Sidelink=true --p1SlotUs={s} --p1SenseDecay={d}")
    for s in a.slots for d in a.decays
]
cfg = (f"{a.nodes} UAVs | simTime {a.simtime}s | P1 TX {a.txpower:g} dBm | CCA {a.cca:g} dBm | "
       f"lock 6 dB | seeds {a.seeds}")

print(f"NS3_DIR = {NS3_DIR}")
print(f"P1 CSMA vs Sidelink | {cfg}\n")


def parse(text):
    row = {}
    m = re.search(r"Total Expected P1 Neighbor Links.*?:\s*(\d+)", text)
    row["TOTAL"] = int(m.group(1)) if m else 0
    m = re.search(r"Successfully Received \(Delivered\)\s*:\s*(\d+)\s*\(([\d.]+)%\)", text)
    row["SUCCESS"], row["PRR"] = (int(m.group(1)), float(m.group(2))) if m else (0, float("nan"))
    for r in REASONS[1:]:
        m = re.search(rf"\b{r}\s*:\s*(\d+)", text)
        row[r] = int(m.group(1)) if m else 0
    m = re.search(r"P1 Slot Boundary Force Cutoffs\s*:\s*(\d+)", text)
    row["CUTOFFS"] = int(m.group(1)) if m else 0
    m = re.search(r"P1 Beacons Not Started Within Slot\s*:\s*(\d+)", text)
    row["LATE"] = int(m.group(1)) if m else 0
    for b in BRACKETS:
        m = re.search(rf"^\s*{b}\s*\|\s*(\d+)\s*\|\s*(\d+)", text, re.M)
        row[b] = (100.0 * int(m.group(2)) / int(m.group(1))) if m and int(m.group(1)) else float("nan")
    return row


runs = {}          # label -> list of rows (one per seed)
saved_files = []
for label, tag, flags in MODES:
    runs[label] = []
    for seed in a.seeds:
        report = os.path.join(NS3_DIR, "p1_ground_truth_report.txt")
        if os.path.exists(report):
            os.remove(report)
        args = (f"scratch/lr-wpan-swarm --numNodes={a.nodes} --simTime={a.simtime} "
                f"--p1Duration=10 {flags} --preambleLockDb=6 "
                f"--p1TxPower={a.txpower} --p2TxPower=-2 --p1CcaThresholdDbm={a.cca} --nodeSpeed=10.0 "
                f"--numSlots=13 --dataSlotUs=750 --p2Duration=9.75 --numChannels=6 "
                f"--spaceSize=200 --spaceZ=80 --rngRun={seed} --autoPush=false")
        print(f"▶ {label} seed {seed} ...", flush=True)
        proc = subprocess.run(["./ns3", "run", args], cwd=NS3_DIR,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if proc.returncode != 0 or not os.path.exists(report):
            print(proc.stdout[-4000:])
            sys.exit(f"✗ Run failed for {label} seed {seed} (exit {proc.returncode})")
        text = open(report, encoding="utf-8", errors="ignore").read()
        fname = f"p1_report_{tag}_seed{seed}.txt"
        shutil.copy(report, os.path.join(PROJECT_DIR, fname))
        saved_files.append(fname)
        row = parse(text)
        runs[label].append(row)
        print(f"   PRR {row['PRR']:.2f}%")

labels = [m[0] for m in MODES]
W = 16
sep = "=" * (34 + W * len(labels))
lines = [f"P1 CSMA vs Sidelink | {cfg}", sep]
header = f"{'Metric (mean over seeds)':34s}" + "".join(f"{l:>{W}s}" for l in labels)
lines += [header, "-" * len(header)]


def mean(label, key):
    return statistics.mean(r[key] for r in runs[label])


lines.append(f"{'P1 PRR (%) mean':34s}" + "".join(f"{mean(l, 'PRR'):>{W}.2f}" for l in labels))
lines.append(f"{'P1 PRR (%) min..max':34s}" + "".join(
    f"{(format(min(r['PRR'] for r in runs[l]), '.1f') + '..' + format(max(r['PRR'] for r in runs[l]), '.1f')):>{W}s}"
    for l in labels))
lines.append(f"{'Target links / seed':34s}" + "".join(f"{mean(l, 'TOTAL'):>{W}.0f}" for l in labels))
for r in REASONS:
    lines.append(f"{r:34s}" + "".join(f"{mean(l, r):>{W}.0f}" for l in labels))
lines.append(f"{'Slot-end force cutoffs (TX)':34s}" + "".join(f"{mean(l, 'CUTOFFS'):>{W}.1f}" for l in labels))
lines.append(f"{'Beacons not started in slot':34s}" + "".join(f"{mean(l, 'LATE'):>{W}.1f}" for l in labels))
lines.append("-" * len(header))
for b in BRACKETS:
    lines.append(f"{'PRR ' + b + ' (%)':34s}" + "".join(f"{mean(l, b):>{W}.1f}" for l in labels))
lines.append("-" * len(header))
for i, seed in enumerate(a.seeds):
    lines.append(f"{'PRR seed ' + str(seed) + ' (%)':34s}" + "".join(f"{runs[l][i]['PRR']:>{W}.2f}" for l in labels))
lines.append(sep)
summary = "\n".join(lines) + "\n"
print("\n" + summary)

with open(os.path.join(PROJECT_DIR, "p1_csma_vs_sidelink_summary.txt"), "w", encoding="utf-8") as f:
    f.write(summary)

# Upload results to GitHub so they can be read back for analysis
result_files = ["p1_csma_vs_sidelink_summary.txt"] + saved_files
try:
    subprocess.run(["git", "pull", "--rebase", "--autostash", "origin", "main"], cwd=PROJECT_DIR, check=True)
    subprocess.run(["git", "add", "-f"] + result_files, cwd=PROJECT_DIR, check=True)
    msg = f"data: P1 CSMA vs Sidelink ({cfg}, slots {a.slots}, decays {a.decays})"
    subprocess.run(["git", "commit", "-m", msg], cwd=PROJECT_DIR, check=True)
    subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=PROJECT_DIR, check=True)
    print("✓ Results pushed to GitHub")
except subprocess.CalledProcessError as e:
    print(f"⚠ Git upload failed ({e}); results are still saved locally in {PROJECT_DIR}")
