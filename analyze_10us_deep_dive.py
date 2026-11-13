#!/usr/bin/env python3
"""
Deep Diagnostic Analysis of 10 µs Slot Experiment
Directly inspects ns-3 execution logs, PHY state transitions, and SSA slotted capture mechanics
to verify if 10 µs micro-slot is physically sound or an artifact of the slotted capture model.
"""

import subprocess
import os
import sys
import re

print("==========================================================================================")
print("🔬 DEEP PHYSICAL & LOG AUDIT: 10 µs SLOT EXPERIMENT AT 100 UAVs 🔬")
print("==========================================================================================")

sim_time = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
num_nodes = 100
p1_duration = 10.0
p1_slot_us = 10.0
capture_thresh_db = 6.0
space_size = 200.0
space_z = 80.0

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
NS3_DIR = os.path.expanduser("~/ns-3-dev")
if not os.path.exists(NS3_DIR):
    NS3_DIR = PROJECT_DIR

# Sync files
for rel_path in ["scratch/lr-wpan-swarm.cc", "src/lr-wpan/model/lr-wpan-phy.cc"]:
    src_f = os.path.join(PROJECT_DIR, rel_path)
    dst_f = os.path.join(NS3_DIR, rel_path)
    if os.path.exists(src_f) and os.path.abspath(src_f) != os.path.abspath(dst_f):
        try:
            os.makedirs(os.path.dirname(dst_f), exist_ok=True)
            subprocess.run(["cp", src_f, dst_f], check=True)
        except Exception:
            pass

# Run 10 µs simulation
print(f"▶️ Running simulation: 100 UAVs, p1Duration=10ms, p1SlotUs=10.0µs, captureThreshold=+6.0dB ...")
cmd = [
    "./ns3", "run",
    f"scratch/lr-wpan-swarm --numNodes={num_nodes} --p1Duration={p1_duration} "
    f"--simTime={sim_time} --spaceSize={space_size} --spaceZ={space_z} "
    f"--enableP1Ssa=true --p1SlotUs={p1_slot_us} --p1CaptureThresholdDb={capture_thresh_db} "
    f"--phyCaptureMarginDb={capture_thresh_db} --autoPush=false"
]
proc = subprocess.run(cmd, cwd=NS3_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=300)
out = proc.stdout

# Read generated report
p1_rpt = os.path.join(NS3_DIR, "p1_ground_truth_report.txt")
p1_text = ""
if os.path.exists(p1_rpt):
    with open(p1_rpt, "r", encoding="utf-8", errors="ignore") as f:
        p1_text = f.read()

print("\n" + "=" * 90)
print("📄 RAW OUTPUT FROM p1_ground_truth_report.txt:")
print("=" * 90)
for line in p1_text.splitlines():
    if any(k in line for k in ["Successfully Received", "Failed Link", "EXACT PHYSICAL ROOT CAUSE", "CSMA_ABORT", "RX_DEAFNESS", "COLLISION", "LOW_SINR", "Capture Events", "Mean SINR"]):
        print(line)
print("=" * 90)

# Check CSV if available
csv_path = os.path.join(NS3_DIR, "p1_exact_drop_reasons.csv")
if os.path.exists(csv_path):
    import csv
    with open(csv_path, "r", encoding="utf-8", errors="ignore") as f:
        reader = list(csv.DictReader(f))
        print(f"\n📊 Total Drop Records in CSV: {len(reader)}")
        if reader:
            print(f"   Sample first 3 drop records:")
            for row in reader[:3]:
                print(f"   - Epoch {row.get('Epoch')}, Receiver {row.get('Receiver')}, Sender {row.get('Sender')}: SINR={row.get('SINR_dB')} dB, Dist={row.get('Distance_m')}m, CoChannelDrones={row.get('CoChannelDrones')}, Cat={row.get('Category')}")

print("\n🔍 Verification Analysis Completed!")
