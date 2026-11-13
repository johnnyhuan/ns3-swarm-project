#!/usr/bin/env python3
"""
Phase 2 (Data Delivery) Single Run Test: 10 ms Phase 2 Duration
Baseline Configuration:
- Swarm Scale: 150 UAVs
- Phase 1 Architecture: SSA (Sensing-based Slotted Access) (100 µs Micro-Slot, 10 ms window)
- Phase 2 Window: 10.0 ms
- Phase 2 Slot Width: 1000 µs (1.0 ms) or 625 µs (Bluetooth Baseband slot)
- Physical Layer: 2 Mbps LE 2M PHY, 436 µs airtime, 40 µs fast turnaround
- Capture Margin: Strict +6.0 dB (Bluetooth 5.4 C/I)
- Evaluates: Phase 1 & Phase 2 Delivery PRR, Phase 2 Capture Events, Exact Physical Drop Reasons, AoI
"""

import subprocess
import os
import sys
import re

print("==========================================================================================")
print("🚀  PHASE 2 DATA DELIVERY TEST: 10 ms DURATION (150 UAVs, SSA BASELINE)  🚀")
print("==========================================================================================")

# Command-line configurable parameters
sim_time = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
num_nodes = int(sys.argv[2]) if len(sys.argv) > 2 else 150
data_slot_us = float(sys.argv[3]) if len(sys.argv) > 3 else 1000.0 # 1000 µs (10 slots) or 625 µs (16 slots)
num_channels = int(sys.argv[4]) if len(sys.argv) > 4 else 6
space_size = float(sys.argv[5]) if len(sys.argv) > 5 else 200.0
space_z = float(sys.argv[6]) if len(sys.argv) > 6 else 80.0
p1_capt_thresh = float(sys.argv[7]) if len(sys.argv) > 7 else -5.0 # -5.0 dB (802.15.4 standard), 3.0 dB, or 6.0 dB (BLE 5.4 C/I)

p1_duration = 10.0
p1_slot_us = 100.0
p2_duration = 10.0
p2_slots = max(1, int(p2_duration * 1000.0 / data_slot_us))
total_cells = p2_slots * num_channels
guard_us = data_slot_us - 436.0 - 40.0
cycle_ms = p1_duration + 1.0 + p2_duration

print(f"• UAV Swarm Scale        : {num_nodes} UAVs")
print(f"• Phase 1 Broadcast Win  : {p1_duration:.1f} ms (SSA, {p1_slot_us:.0f} µs slot, SINR Thresh: {p1_capt_thresh:+.1f} dB)")
print(f"• Phase 2 Data Window    : {p2_duration:.1f} ms ({p2_slots} slots x {data_slot_us:.0f} µs, {num_channels} channels = {total_cells} cells)")
print(f"• Data Packet Airtime    : 436 µs (@ 2 Mbps, 50B payload + headers) + 40 µs turnaround")
print(f"• Timing Guard Band      : {guard_us:.0f} µs")
print(f"• Total Cycle Duration   : {cycle_ms:.1f} ms (P1: {p1_duration:.0f}ms + Gap: 1ms + P2: {p2_duration:.0f}ms)")
print(f"• Airspace Dimensions    : {space_size:.0f}m x {space_size:.0f}m x {space_z:.0f}m")
print(f"• Simulation Time        : {sim_time:.1f} s")
print("------------------------------------------------------------------------------------------\n")

# Detect paths
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
NS3_DIR = os.path.expanduser("~/ns-3-dev")
if not os.path.exists(NS3_DIR):
    NS3_DIR = PROJECT_DIR

# Sync updated files to NS3_DIR if running across separate folders
sync_files = [
    "scratch/lr-wpan-swarm.cc",
    "src/lr-wpan/model/lr-wpan-phy.cc",
    "src/lr-wpan/model/lr-wpan-phy.h",
    "src/lr-wpan/model/lr-wpan-constants.h",
    "src/lr-wpan/model/lr-wpan-csmaca.cc"
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

# Clean previous reports
for fname in ["p1_ground_truth_report.txt", "p2_ground_truth_report.txt", "run.log", "metrics.txt", "p1_exact_drop_reasons.csv", "p2_exact_drop_reasons.csv"]:
    fpath = os.path.join(NS3_DIR, fname)
    if os.path.exists(fpath):
        try:
            os.remove(fpath)
        except Exception:
            pass

print(f"▶️ Executing ns-3 simulation with Phase 2 = {p2_duration:.1f} ms, slot = {data_slot_us:.0f} µs ({p2_slots} slots) ...", flush=True)

cmd = [
    "./ns3", "run",
    f"scratch/lr-wpan-swarm --numNodes={num_nodes} --p1Duration={p1_duration} "
    f"--p2Duration={p2_duration} --dataSlotUs={data_slot_us} --numChannels={num_channels} "
    f"--simTime={sim_time} --spaceSize={space_size} --spaceZ={space_z} "
    f"--p1TxPower=0 --p2TxPower=-2 --p1CcaThresholdDbm=-96.58 --nodeSpeed=10.0 "
    f"--enableP1Ssa=true --p1SlotUs={p1_slot_us} --p1CaptureThresholdDb={p1_capt_thresh} --autoPush=false"
]

try:
    proc = subprocess.run(cmd, cwd=NS3_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=300)
    stdout_output = proc.stdout
except subprocess.TimeoutExpired:
    print(f"\n⚠️ Command timed out after 300s!")
    sys.exit(1)

if proc.returncode != 0:
    print(f"\n❌ Execution failed (exit code {proc.returncode})!")
    print(stdout_output)
    sys.exit(1)

# Read generated reports
p1_rpt_path = os.path.join(NS3_DIR, "p1_ground_truth_report.txt")
p1_text = ""
if os.path.exists(p1_rpt_path):
    with open(p1_rpt_path, "r", encoding="utf-8", errors="ignore") as f:
        p1_text = f.read()

p2_rpt_path = os.path.join(NS3_DIR, "p2_ground_truth_report.txt")
p2_text = ""
if os.path.exists(p2_rpt_path):
    with open(p2_rpt_path, "r", encoding="utf-8", errors="ignore") as f:
        p2_text = f.read()

metrics_path = os.path.join(NS3_DIR, "metrics.txt")
metrics_text = ""
if os.path.exists(metrics_path):
    with open(metrics_path, "r", encoding="utf-8", errors="ignore") as f:
        metrics_text = f.read()

# Copy CSVs to project directory
for csv_name in ["p1_exact_drop_reasons.csv", "p2_exact_drop_reasons.csv"]:
    src_csv = os.path.join(NS3_DIR, csv_name)
    dst_csv = os.path.join(PROJECT_DIR, csv_name)
    if os.path.exists(src_csv) and os.path.abspath(src_csv) != os.path.abspath(dst_csv):
        subprocess.run(["cp", src_csv, dst_csv])

# Print Phase 1 Summary
print("\n" + "=" * 90)
print("📊 1. PHASE 1 MINI-BEACON (DISCOVERY) SUMMARY")
print("=" * 90)
m_p1_links = re.search(r"Total Expected P1 Neighbor Links.*:\s*(\d+)", p1_text)
m_p1_succ = re.search(r"Successfully Received \(Delivered\)\s*:\s*(\d+)\s*\(([\d\.]+)%\)", p1_text)
m_p1_fail = re.search(r"Failed Link Receptions \(Dropped/Missed\)\s*:\s*(\d+)\s*\(([\d\.]+)%\)", p1_text)
m_p1_capt = re.search(r"Total Power Capture Events Triggered\s*:\s*(\d+)", p1_text)

if m_p1_succ:
    print(f"• Expected Target Links  : {m_p1_links.group(1) if m_p1_links else 'N/A'}")
    print(f"• Successfully Delivered : {m_p1_succ.group(1)} ({m_p1_succ.group(2)}% PRR)")
    print(f"• Dropped / Missed Links : {m_p1_fail.group(1) if m_p1_fail else '0'} ({m_p1_fail.group(2) if m_p1_fail else '0.0'}%)")
    print(f"• Phase 1 Capture Rescues: {m_p1_capt.group(1) if m_p1_capt else '0'} events (C/I >= +6.0 dB)")
else:
    print(p1_text[:500])

# Print Phase 2 Summary
print("\n" + "=" * 90)
print(f"📊 2. PHASE 2 DATA DELIVERY SUMMARY (Duration = {p2_duration:.1f} ms, {p2_slots} slots, {num_channels} chs = {total_cells} cells)")
print("=" * 90)

m_p2_links = re.search(r"Total Expected P2 Neighbor Links.*:\s*(\d+)", p2_text)
m_p2_succ = re.search(r"Successfully Received \(Delivered\)\s*:\s*(\d+)\s*\(([\d\.]+)%\)", p2_text)
m_p2_fail = re.search(r"Failed Link Receptions \(Dropped/Missed\)\s*:\s*(\d+)\s*\(([\d\.]+)%\)", p2_text)
m_p2_capt = re.search(r"Total Power Capture Events Triggered\s*:\s*(\d+)", p2_text)

p2_capt_count = int(m_p2_capt.group(1)) if m_p2_capt else 0

if m_p2_succ:
    print(f"• Expected Data Links    : {m_p2_links.group(1) if m_p2_links else 'N/A'}")
    print(f"• Successfully Delivered : {m_p2_succ.group(1)} (⭐ PRR: {m_p2_succ.group(2)}%)")
    print(f"• Dropped / Missed Links : {m_p2_fail.group(1) if m_p2_fail else '0'} ({m_p2_fail.group(2) if m_p2_fail else '0.0'}%)")
    
    # Explicitly highlight Phase 2 Capture Event status
    print(f"• Phase 2 Capture Events : {p2_capt_count} events triggered (Margin = +6.0 dB)")
    if p2_capt_count > 0:
        print(f"  👉 [Capture Status] : 💥 Yes! Phase 2 triggered {p2_capt_count} capture events, successfully preempting weaker co-channel packets!")
    else:
        print(f"  👉 [Capture Status] : ℹ️ Phase 2 triggered 0 capture events (slots were either scheduled without overlapping collisions or collided with insufficient SIR < 6 dB).")

    print("\n📋 EXACT PHYSICAL ROOT CAUSE BREAKDOWN:")
    print("-" * 90)
    for line in p2_text.splitlines():
        if ("%" in line and ":" in line and ("P2_" in line or "MISMATCH" in line or "DEAF" in line or "COLLISION" in line or "ABORT" in line or "SINR" in line or "DISCOVERY" in line)):
            print(line)
else:
    print(p2_text[:500])

# Print AoI and Latency
print("\n" + "=" * 90)
print("⏱️ 3. AGE OF INFORMATION (AoI) & LATENCY")
print("=" * 90)
m_mean_aoi = re.search(r"Mean Beacon Packet AoI \(Top-K\)\s*:\s*([\d\.]+)\s*ms", metrics_text)
m_max_aoi = re.search(r"Max Beacon Packet AoI \(Top-K\)\s*:\s*([\d\.]+)\s*ms", metrics_text)
m_avg_iat = re.search(r"Avg Discovery Msg IAT \(Top-K\)\s*:\s*([\d\.]+)\s*ms", metrics_text)

if m_mean_aoi:
    print(f"• Mean Beacon AoI (Top-K) : {m_mean_aoi.group(1)} ms")
    print(f"• Max Beacon AoI (Top-K)  : {m_max_aoi.group(1) if m_max_aoi else 'N/A'} ms")
    print(f"• Avg Discovery Msg IAT   : {m_avg_iat.group(1) if m_avg_iat else 'N/A'} ms")
    print(f"• Cycle Duration          : {cycle_ms:.1f} ms")
else:
    print(metrics_text)

# Save result summary file
summary_file = os.path.join(PROJECT_DIR, "p2_10ms_ground_truth_results.txt")
with open(summary_file, "w", encoding="utf-8") as f:
    f.write(f"# Phase 2 Data Delivery Single Test Report (10 ms Duration)\n")
    f.write(f"- Swarm Scale       : {num_nodes} UAVs\n")
    f.write(f"- Phase 1 Window    : {p1_duration:.1f} ms (SSA, {p1_slot_us:.0f} us slot)\n")
    f.write(f"- Phase 2 Window    : {p2_duration:.1f} ms ({p2_slots} slots x {data_slot_us:.0f} us, {num_channels} channels = {total_cells} cells)\n")
    f.write(f"- Cycle Time        : {cycle_ms:.1f} ms\n")
    f.write(f"- P1 PRR            : {m_p1_succ.group(2) if m_p1_succ else 'N/A'}%\n")
    f.write(f"- P2 PRR            : {m_p2_succ.group(2) if m_p2_succ else 'N/A'}%\n")
    f.write(f"- P2 Capture Events : {p2_capt_count} events\n")
    f.write(f"- Mean AoI          : {m_mean_aoi.group(1) if m_mean_aoi else 'N/A'} ms\n\n")
    f.write("## Phase 2 Ground Truth Report\n")
    f.write(p2_text)

print(f"\n📄 Complete test report saved to: {summary_file}")

# Auto push if requested
if "--autoPush" in sys.argv:
    print("📤 Auto-pushing test results to GitHub...")
    subprocess.run("git add p2_10ms_ground_truth_results.txt p1_exact_drop_reasons.csv p2_exact_drop_reasons.csv && git commit -m 'data: complete Phase 2 10ms baseline run report' && git push origin main", shell=True, cwd=PROJECT_DIR)

print("\n🎉 Phase 2 10ms single run execution completed successfully!")
