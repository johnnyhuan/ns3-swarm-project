#!/usr/bin/env python3
"""
Phase 1 pure CSMA-CA test (BLE 5.4 receiver model, no post-lock re-sync).

Runs lr-wpan-swarm once per preamble lock threshold and prints the Phase 1
ground-truth breakdown side by side.

Usage:
    python3 run_p1_pure_csma.py [numNodes] [simTime] [lockDb ...]
    python3 run_p1_pure_csma.py                 # 100 nodes, 3.0 s, lock 6 dB and -5 dB
    python3 run_p1_pure_csma.py 100 3.0 6       # only 6 dB
"""
import os
import re
import shutil
import subprocess
import sys

num_nodes = int(sys.argv[1]) if len(sys.argv) > 1 else 100
sim_time = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
lock_values = [float(x) for x in sys.argv[3:]] or [6.0, -5.0]

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
NS3_DIR = os.path.expanduser("~/ns-3-dev")
if not os.path.exists(NS3_DIR):
    NS3_DIR = PROJECT_DIR

# Sync modified sources into the ns-3 tree (same as the sweep scripts)
for rel_path in ["scratch/lr-wpan-swarm.cc",
                 "src/lr-wpan/model/lr-wpan-phy.cc",
                 "src/lr-wpan/model/lr-wpan-phy.h",
                 "src/lr-wpan/model/lr-wpan-csmaca.cc"]:
    src_f = os.path.join(PROJECT_DIR, rel_path)
    dst_f = os.path.join(NS3_DIR, rel_path)
    if os.path.exists(src_f) and os.path.abspath(src_f) != os.path.abspath(dst_f):
        os.makedirs(os.path.dirname(dst_f), exist_ok=True)
        shutil.copy(src_f, dst_f)

REASONS = ["SUCCESS", "SENDER_CSMA_ABORT", "RX_DEAFNESS_BUSY_TX",
           "PREAMBLE_COLLISION_BUSY_RX", "PREAMBLE_LOW_SINR",
           "RADIO_TURNAROUND_BUSY", "PAYLOAD_INTERFERENCE_CORRUPTION"]

print(f"NS3_DIR = {NS3_DIR}")
print(f"P1 pure CSMA-CA | {num_nodes} UAVs | simTime {sim_time}s | lock thresholds {lock_values}\n")

results = {}
for lock in lock_values:
    report = os.path.join(NS3_DIR, "p1_ground_truth_report.txt")
    if os.path.exists(report):
        os.remove(report)

    args = (f"scratch/lr-wpan-swarm --numNodes={num_nodes} --simTime={sim_time} "
            f"--p1Duration=10 --enableP1Sidelink=false --preambleLockDb={lock} "
            f"--p1TxPower=0 --p2TxPower=-2 --p1CcaThresholdDbm=-96.58 --nodeSpeed=10.0 "
            f"--numSlots=13 --dataSlotUs=750 --p2Duration=9.75 --numChannels=6 "
            f"--spaceSize=200 --spaceZ=80 --rngRun=1 --autoPush=false")
    print(f"▶ Running preambleLockDb={lock} ...", flush=True)
    proc = subprocess.run(["./ns3", "run", args], cwd=NS3_DIR,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if proc.returncode != 0 or not os.path.exists(report):
        print(proc.stdout[-4000:])
        sys.exit(f"✗ Run failed for preambleLockDb={lock} (exit {proc.returncode})")

    text = open(report, encoding="utf-8", errors="ignore").read()
    saved = os.path.join(PROJECT_DIR, f"p1_report_lock{lock:g}dB.txt")
    shutil.copy(report, saved)

    row = {}
    m = re.search(r"Total Expected P1 Neighbor Links.*?:\s*(\d+)", text)
    row["TOTAL"] = int(m.group(1)) if m else 0
    m = re.search(r"Successfully Received \(Delivered\)\s*:\s*\d+\s*\(([\d.]+)%\)", text)
    row["PRR"] = float(m.group(1)) if m else float("nan")
    for r in REASONS[1:]:
        m = re.search(rf"\b{r}\s*:\s*(\d+)", text)
        row[r] = int(m.group(1)) if m else 0
    m = re.search(r"Successfully Received \(Delivered\)\s*:\s*(\d+)", text)
    row["SUCCESS"] = int(m.group(1)) if m else 0
    results[lock] = row
    print(f"  saved {saved}")

lines = []
lines.append(f"P1 pure CSMA-CA | {num_nodes} UAVs | simTime {sim_time}s | rngRun=1")
lines.append("=" * 78)
header = f"{'Metric':34s}" + "".join(f"{('lock ' + format(l, 'g') + ' dB'):>14s}" for l in lock_values)
lines.append(header)
lines.append("-" * len(header))
lines.append(f"{'Target links (Top-K in 50m)':34s}" + "".join(f"{results[l]['TOTAL']:>14d}" for l in lock_values))
lines.append(f"{'P1 PRR (%)':34s}" + "".join(f"{results[l]['PRR']:>14.2f}" for l in lock_values))
for r in REASONS:
    lines.append(f"{r:34s}" + "".join(f"{results[l][r]:>14d}" for l in lock_values))
lines.append("=" * 78)
summary = "\n".join(lines) + "\n"
print("\n" + summary)

summary_path = os.path.join(PROJECT_DIR, "p1_pure_csma_summary.txt")
with open(summary_path, "w", encoding="utf-8") as f:
    f.write(summary)

# Upload results to GitHub so they can be read back for analysis
result_files = ["p1_pure_csma_summary.txt"] + [f"p1_report_lock{l:g}dB.txt" for l in lock_values]
try:
    subprocess.run(["git", "pull", "--rebase", "--autostash", "origin", "main"], cwd=PROJECT_DIR, check=True)
    subprocess.run(["git", "add", "-f"] + result_files, cwd=PROJECT_DIR, check=True)
    msg = f"data: P1 pure CSMA results ({num_nodes} UAVs, {sim_time}s, lock {lock_values} dB)"
    subprocess.run(["git", "commit", "-m", msg], cwd=PROJECT_DIR, check=True)
    subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=PROJECT_DIR, check=True)
    print("✓ Results pushed to GitHub")
except subprocess.CalledProcessError as e:
    print(f"⚠ Git upload failed ({e}); results are still saved locally in {PROJECT_DIR}")
