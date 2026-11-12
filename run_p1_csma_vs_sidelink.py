#!/usr/bin/env python3
"""
Phase 1: pure CSMA-CA vs Sidelink-style S-SPS (BLE 5.4 receiver model, 6 dB lock, no re-sync).

Same topology (rngRun=1) for both MACs; prints the Phase 1 ground-truth breakdown
side by side and pushes the results to GitHub main.

Usage:
    python3 run_p1_csma_vs_sidelink.py [numNodes] [simTime] [p1SlotUs] [lockDb]
    python3 run_p1_csma_vs_sidelink.py                  # 100 nodes, 3.0 s, 300 us slots, 6 dB
"""
import os
import re
import shutil
import subprocess
import sys

num_nodes = int(sys.argv[1]) if len(sys.argv) > 1 else 100
sim_time = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
slot_us = float(sys.argv[3]) if len(sys.argv) > 3 else 300.0
lock_db = float(sys.argv[4]) if len(sys.argv) > 4 else 6.0

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
NS3_DIR = os.path.expanduser("~/ns-3-dev")
if not os.path.exists(NS3_DIR):
    NS3_DIR = PROJECT_DIR

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
BRACKETS = ["0-10m", "10-20m", "20-30m", "30-40m", "40-50m"]

MODES = [
    ("CSMA", "csma", "--enableP1Sidelink=false"),
    ("Sidelink", "sidelink", f"--enableP1Sidelink=true --p1SlotUs={slot_us}"),
]

print(f"NS3_DIR = {NS3_DIR}")
print(f"P1 CSMA vs Sidelink | {num_nodes} UAVs | simTime {sim_time}s | slot {slot_us} us | lock {lock_db} dB\n")

results = {}
for label, tag, flags in MODES:
    report = os.path.join(NS3_DIR, "p1_ground_truth_report.txt")
    if os.path.exists(report):
        os.remove(report)

    args = (f"scratch/lr-wpan-swarm --numNodes={num_nodes} --simTime={sim_time} "
            f"--p1Duration=10 {flags} --preambleLockDb={lock_db} "
            f"--p1TxPower=0 --p2TxPower=-2 --p1CcaThresholdDbm=-96.58 --nodeSpeed=10.0 "
            f"--numSlots=13 --dataSlotUs=750 --p2Duration=9.75 --numChannels=6 "
            f"--spaceSize=200 --spaceZ=80 --rngRun=1 --autoPush=false")
    print(f"▶ Running {label} ...", flush=True)
    proc = subprocess.run(["./ns3", "run", args], cwd=NS3_DIR,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if proc.returncode != 0 or not os.path.exists(report):
        print(proc.stdout[-4000:])
        sys.exit(f"✗ Run failed for {label} (exit {proc.returncode})")

    text = open(report, encoding="utf-8", errors="ignore").read()
    saved = os.path.join(PROJECT_DIR, f"p1_report_{tag}.txt")
    shutil.copy(report, saved)

    row = {}
    m = re.search(r"Total Expected P1 Neighbor Links.*?:\s*(\d+)", text)
    row["TOTAL"] = int(m.group(1)) if m else 0
    m = re.search(r"Successfully Received \(Delivered\)\s*:\s*(\d+)\s*\(([\d.]+)%\)", text)
    row["SUCCESS"], row["PRR"] = (int(m.group(1)), float(m.group(2))) if m else (0, float("nan"))
    for r in REASONS[1:]:
        m = re.search(rf"\b{r}\s*:\s*(\d+)", text)
        row[r] = int(m.group(1)) if m else 0
    for b in BRACKETS:
        m = re.search(rf"^\s*{b}\s*\|\s*(\d+)\s*\|\s*(\d+)", text, re.M)
        row[b] = (100.0 * int(m.group(2)) / int(m.group(1))) if m and int(m.group(1)) else float("nan")
    results[label] = row
    print(f"  saved {saved}")

labels = [m[0] for m in MODES]
lines = [f"P1 CSMA vs Sidelink | {num_nodes} UAVs | simTime {sim_time}s | slot {slot_us} us | "
         f"lock {lock_db} dB | rngRun=1", "=" * 72]
header = f"{'Metric':34s}" + "".join(f"{l:>16s}" for l in labels)
lines += [header, "-" * len(header)]
lines.append(f"{'Target links (Top-K in 50m)':34s}" + "".join(f"{results[l]['TOTAL']:>16d}" for l in labels))
lines.append(f"{'P1 PRR (%)':34s}" + "".join(f"{results[l]['PRR']:>16.2f}" for l in labels))
for r in REASONS:
    lines.append(f"{r:34s}" + "".join(f"{results[l][r]:>16d}" for l in labels))
lines.append("-" * len(header))
for b in BRACKETS:
    lines.append(f"{'PRR ' + b + ' (%)':34s}" + "".join(f"{results[l][b]:>16.1f}" for l in labels))
lines.append("=" * 72)
summary = "\n".join(lines) + "\n"
print("\n" + summary)

with open(os.path.join(PROJECT_DIR, "p1_csma_vs_sidelink_summary.txt"), "w", encoding="utf-8") as f:
    f.write(summary)

# Upload results to GitHub so they can be read back for analysis
result_files = ["p1_csma_vs_sidelink_summary.txt"] + [f"p1_report_{m[1]}.txt" for m in MODES]
try:
    subprocess.run(["git", "pull", "--rebase", "--autostash", "origin", "main"], cwd=PROJECT_DIR, check=True)
    subprocess.run(["git", "add", "-f"] + result_files, cwd=PROJECT_DIR, check=True)
    msg = f"data: P1 CSMA vs Sidelink ({num_nodes} UAVs, {sim_time}s, slot {slot_us}us, lock {lock_db}dB)"
    subprocess.run(["git", "commit", "-m", msg], cwd=PROJECT_DIR, check=True)
    subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=PROJECT_DIR, check=True)
    print("✓ Results pushed to GitHub")
except subprocess.CalledProcessError as e:
    print(f"⚠ Git upload failed ({e}); results are still saved locally in {PROJECT_DIR}")
