#!/usr/bin/env python3
"""
Phase 2 (Data Delivery) Pilot Run:
- Phase 1: Fixed 10.0 ms CSMA-CA Broadcast with Capture ENABLED (+6.0 dB BLE 5.4 C/I)
- Phase 2: 10.0 ms Data Delivery, Data Slot = 1000.0 µs (10 slots), 6 Channels, Capture DISABLED (No Capture Event)
- Swarm Scale: 100 UAVs in 200m x 200m x 80m
"""

import subprocess
import os
import sys
import re
from datetime import datetime

print("==========================================================================================")
print("🚀  PHASE 2 DATA DELIVERY PILOT BENCHMARK (100 UAVs, BLE 5.4 2M PHY)  🚀")
print("==========================================================================================")

sim_time = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
num_nodes = int(sys.argv[2]) if len(sys.argv) > 2 else 100
data_slot_us = float(sys.argv[3]) if len(sys.argv) > 3 else 1000.0  # 1000 µs (10 slots in 10ms)
num_channels = int(sys.argv[4]) if len(sys.argv) > 4 else 6
p1_duration = 10.0
p2_duration = 10.0
space_size = 200.0
space_z = 80.0

p2_slots = max(1, int(p2_duration * 1000.0 / data_slot_us))
total_cells = p2_slots * num_channels
cycle_ms = p1_duration + 1.0 + p2_duration

print(f"• UAV Swarm Scale        : {num_nodes} UAVs in {space_size:.0f}m x {space_size:.0f}m x {space_z:.0f}m")
print(f"• Phase 1 Broadcast Win  : {p1_duration:.1f} ms (CSMA-CA Contention, Capture ENABLED: +6.0 dB)")
print(f"• Phase 2 Data Window    : {p2_duration:.1f} ms ({p2_slots} slots x {data_slot_us:.0f} µs, {num_channels} channels = {total_cells} cells)")
print(f"• Phase 2 Capture Event  : DISABLED (Pure Collision / No Capture Rescue)")
print(f"• Total Cycle Duration   : {cycle_ms:.1f} ms (P1: {p1_duration:.0f}ms + Gap: 1ms + P2: {p2_duration:.0f}ms)")
print(f"• Simulation Time        : {sim_time:.1f} s")
print("------------------------------------------------------------------------------------------\n")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
NS3_DIR = os.path.expanduser("~/ns-3-dev")
if not os.path.exists(NS3_DIR):
    NS3_DIR = PROJECT_DIR

# Sync updated files to NS3_DIR if running across separate folders
sync_files = [
    "scratch/lr-wpan-swarm.cc",
    "src/lr-wpan/model/lr-wpan-phy.cc",
    "src/lr-wpan/model/lr-wpan-phy.h"
]
for rel_path in sync_files:
    src_f = os.path.join(PROJECT_DIR, rel_path)
    dst_f = os.path.join(NS3_DIR, rel_path)
    if os.path.exists(src_f) and os.path.abspath(src_f) != os.path.abspath(dst_f):
        try:
            print(f"=> Syncing {rel_path} to {dst_f}...")
            os.makedirs(os.path.dirname(dst_f), exist_ok=True)
            subprocess.run(["cp", src_f, dst_f], check=True)
        except Exception as e:
            print(f"Error syncing {rel_path}: {e}")
            sys.exit(1)

# Clean previous report files
for fname in ["p1_ground_truth_report.txt", "p2_ground_truth_report.txt", "run.log", "p1_exact_drop_reasons.csv", "p2_exact_drop_reasons.csv"]:
    fpath = os.path.join(NS3_DIR, fname)
    if os.path.exists(fpath):
        try: os.remove(fpath)
        except Exception: pass

print(f"▶️ Executing ns-3 simulation (P1 CSMA 10ms with capture + P2 Slotted 10ms NO capture) ...", flush=True)

cmd = [
    "./ns3", "run",
    f"scratch/lr-wpan-swarm --numNodes={num_nodes} --p1Duration={p1_duration} "
    f"--p2Duration={p2_duration} --dataSlotUs={data_slot_us} --numChannels={num_channels} "
    f"--simTime={sim_time} --spaceSize={space_size} --spaceZ={space_z} "
    f"--p1TxPower=0 --p2TxPower=-2 --p1CcaThresholdDbm=-96.58 --nodeSpeed=10.0 "
    f"--enableP1Ssa=false --enablePhyCapture=true --enableP2Capture=false "
    f"--p1CaptureThresholdDb=6.0 --phyCaptureMarginDb=6.0 --autoPush=false"
]

try:
    proc = subprocess.run(cmd, cwd=NS3_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=300)
    stdout_output = proc.stdout
except subprocess.TimeoutExpired:
    print(f"\n⚠️ Command timed out after 300s!")
    sys.exit(1)

# Print and capture Phase 1 and Phase 2 reports
p1_report = os.path.join(NS3_DIR, "p1_ground_truth_report.txt")
p2_report = os.path.join(NS3_DIR, "p2_ground_truth_report.txt")

p1_content = ""
p2_content = ""

if os.path.exists(p1_report):
    with open(p1_report, "r", encoding="utf-8", errors="ignore") as f:
        p1_content = f.read()

if os.path.exists(p2_report):
    with open(p2_report, "r", encoding="utf-8", errors="ignore") as f:
        p2_content = f.read()

print(p1_content)
print(p2_content)

# Save combined pilot report
out_rpt = os.path.join(PROJECT_DIR, "p2_pilot_test_report.txt")
with open(out_rpt, "w", encoding="utf-8") as f:
    f.write(f"# Phase 2 Data Delivery Pilot Test Report\n")
    f.write(f"- Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write(f"- Configuration: P1 CSMA 10ms (Capture ON), P2 10ms (Slot {data_slot_us:.0f}µs, 6 Chs, Capture OFF)\n")
    f.write(f"- Nodes: {num_nodes} UAVs\n\n")
    f.write("=== PHASE 1 REPORT ===\n")
    f.write(p1_content)
    f.write("\n=== PHASE 2 REPORT ===\n")
    f.write(p2_content)

print(f"✅ Combined test report saved to {out_rpt}")

if "--no-push" not in sys.argv:
    print("\n🚀 Pushing results and reports to GitHub main...")
    try:
        subprocess.run(
            "git add p2_pilot_test_report.txt p1_ground_truth_report.txt p2_ground_truth_report.txt p1_exact_drop_reasons.csv p2_exact_drop_reasons.csv && git commit -m 'data: upload P2 pilot test results (10ms, slot 1000us, P2 capture OFF)' && git push origin main",
            shell=True,
            cwd=PROJECT_DIR,
            check=False
        )
        print("✅ Git push completed!")
    except Exception as e:
        print(f"⚠️ Git push notice: {e}")

print("🎉 Pilot test finished!")
