#!/usr/bin/env python3
"""
Phase 2 Data Delivery Benchmark for 150 UAV Swarm
- Baseline Phase 1: 3GPP Sidelink Mode 4 S-SPS (10ms window, 100 µs slot width)
- Phase 2 Total Duration: 10.0 ms
- Evaluates Phase 2 Data Delivery Success Rate (PRR), Ground Truth Drop Breakdown, Power Capture Events, and AoI.
- Compares:
  1. dataSlotUs = 625 µs (16 slots in 10ms - maximum 2D capacity for 2 Mbps PHY)
  2. dataSlotUs = 1000 µs (10 slots in 10ms - 1.0 ms integer slot standard)
"""

import subprocess
import os
import sys
import re

print("==========================================================================================")
print("🎯  PHASE 2 DATA DELIVERY BENCHMARK (150 UAVs, Phase 1 = 10ms, Phase 2 = 10ms)  🎯")
print("==========================================================================================")

num_nodes = int(sys.argv[1]) if len(sys.argv) > 1 else 150
sim_time = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
space_size = float(sys.argv[3]) if len(sys.argv) > 3 else 200.0
space_z = float(sys.argv[4]) if len(sys.argv) > 4 else 80.0

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
            os.makedirs(os.path.dirname(dst_f), exist_ok=True)
            subprocess.run(["cp", src_f, dst_f], check=True)
        except Exception as e:
            print(f"Error syncing {rel_path}: {e}")
            sys.exit(1)

def run_test(slot_us, p2_dur_ms=10.0):
    num_slots = int(p2_dur_ms * 1000.0 / slot_us)
    guard_us = slot_us - 436.0 - 40.0
    print(f"\n▶️ Running Phase 2 Test: Slot = {slot_us:.0f} µs ({num_slots} slots in {p2_dur_ms:.1f}ms, Guard Band = {guard_us:.0f} µs)...")

    # Clean old report files before run
    for fname in ["p1_ground_truth_report.txt", "p2_ground_truth_report.txt", "run.log", "metrics.txt"]:
        fpath = os.path.join(NS3_DIR, fname)
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
            except Exception:
                pass

    cmd = [
        "./ns3", "run",
        f"scratch/lr-wpan-swarm --numNodes={num_nodes} --p1Duration=10.0 --p1SlotUs=100.0 "
        f"--enableP1Sidelink=true --p2Duration={p2_dur_ms} --dataSlotUs={slot_us} "
        f"--simTime={sim_time} --spaceSize={space_size} --spaceZ={space_z} "
        f"--p1TxPower=0 --p2TxPower=-2 --nodeSpeed=10.0 --autoPush=false"
    ]

    proc = subprocess.run(cmd, cwd=NS3_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=300)
    out = proc.stdout

    # Read generated p2 report
    p2_rpt = os.path.join(NS3_DIR, "p2_ground_truth_report.txt")
    p2_text = ""
    if os.path.exists(p2_rpt):
        with open(p2_rpt, "r", encoding="utf-8", errors="ignore") as f:
            p2_text = f.read()

    # Read p1 report
    p1_rpt = os.path.join(NS3_DIR, "p1_ground_truth_report.txt")
    p1_text = ""
    if os.path.exists(p1_rpt):
        with open(p1_rpt, "r", encoding="utf-8", errors="ignore") as f:
            p1_text = f.read()

    # Read metrics.txt
    metrics_rpt = os.path.join(NS3_DIR, "metrics.txt")
    metrics_text = ""
    if os.path.exists(metrics_rpt):
        with open(metrics_rpt, "r", encoding="utf-8", errors="ignore") as f:
            metrics_text = f.read()

    data = parse_results(p1_text, p2_text, out + "\n" + metrics_text)
    data["slot_us"] = slot_us
    data["num_slots"] = num_slots
    data["guard_us"] = guard_us
    data["p2_dur_ms"] = p2_dur_ms
    return data

def parse_results(p1_text, p2_text, stdout_text):
    data = {
        "p1_prr": 0.0,
        "p2_prr": 0.0,
        "p2_links": 0,
        "p2_success": 0,
        "p2_fails": 0,
        "p1_miss": 0,
        "tx_deaf": 0,
        "rx_deaf": 0,
        "ch_mismatch": 0,
        "preamble_coll": 0,
        "low_sinr": 0,
        "payload_drop": 0,
        "captures": 0,
        "mean_aoi": 0.0,
        "max_aoi": 0.0,
        "avg_iat": 0.0
    }

    m = re.search(r"Successfully Received \(Delivered\)\s*:\s*\d+\s*\(([\d\.]+)%\)", p1_text)
    if m: data["p1_prr"] = float(m.group(1))

    m = re.search(r"Total Expected P2 Neighbor Links.*:\s*(\d+)", p2_text)
    if m: data["p2_links"] = int(m.group(1))

    m = re.search(r"Successfully Received \(Delivered\)\s*:\s*(\d+)\s*\(([\d\.]+)%\)", p2_text)
    if m:
        data["p2_success"] = int(m.group(1))
        data["p2_prr"] = float(m.group(2))

    m = re.search(r"Failed Link Receptions \(Dropped/Missed\)\s*:\s*(\d+)", p2_text)
    if m: data["p2_fails"] = int(m.group(1))

    m = re.search(r"P1_DISCOVERY_MISS\s*:\s*(\d+)", p2_text)
    if m: data["p1_miss"] = int(m.group(1))

    m = re.search(r"TX_DEAFNESS_SAME_SLOT\s*:\s*(\d+)", p2_text)
    if m: data["tx_deaf"] = int(m.group(1))

    m = re.search(r"RX_DEAFNESS_SLOT_CONFLICT\s*:\s*(\d+)", p2_text)
    if m: data["rx_deaf"] = int(m.group(1))

    m = re.search(r"RECEIVER_CHANNEL_MISMATCH\s*:\s*(\d+)", p2_text)
    if m: data["ch_mismatch"] = int(m.group(1))

    m = re.search(r"PREAMBLE_COLLISION_BUSY_RX\s*:\s*(\d+)", p2_text)
    if m: data["preamble_coll"] = int(m.group(1))

    m = re.search(r"PREAMBLE_LOW_SINR\s*:\s*(\d+)", p2_text)
    if m: data["low_sinr"] = int(m.group(1))

    m = re.search(r"PAYLOAD_INTERFERENCE_DROP\s*:\s*(\d+)", p2_text)
    if m: data["payload_drop"] = int(m.group(1))

    m = re.search(r"Total Power Capture Events Triggered\s*:\s*(\d+)", p2_text)
    if m: data["captures"] = int(m.group(1))

    m = re.search(r"Mean Beacon Packet AoI \(Top-K\)\s*:\s*([\d\.]+)\s*ms", stdout_text)
    if m: data["mean_aoi"] = float(m.group(1))

    m = re.search(r"Max Beacon Packet AoI \(Top-K\)\s*:\s*([\d\.]+)\s*ms", stdout_text)
    if m: data["max_aoi"] = float(m.group(1))

    m = re.search(r"Avg Discovery Msg IAT \(Top-K\)\s*:\s*([\d\.]+)\s*ms", stdout_text)
    if m: data["avg_iat"] = float(m.group(1))

    return data

# Test Configurations
test_slots = [625.0, 1000.0]
results = []

for s in test_slots:
    res = run_test(s, p2_dur_ms=10.0)
    results.append(res)
    print(f"   => P1 PRR: {res['p1_prr']:.1f}% | P2 Data PRR: {res['p2_prr']:.1f}% | Collisions: {res['preamble_coll']} | Captures: {res['captures']} | Mean AoI: {res['mean_aoi']:.1f}ms")

# Print Summary Table
print("\n" + "=" * 115)
print("📊  PHASE 2 DATA DELIVERY BENCHMARK SUMMARY (150 UAVs, P1=10ms, P2=10ms)")
print("=" * 115)
print(f"{'Slot (µs)':<10} | {'Slots':<6} | {'Guard (µs)':<11} | {'P1 PRR':<9} | {'P2 PRR':<9} | {'P1 Miss':<9} | {'RX Deaf':<9} | {'Collision':<10} | {'Captures':<9} | {'Mean AoI':<10}")
print("-" * 115)

for r in results:
    print(f"{r['slot_us']:<10.0f} | {r['num_slots']:<6} | {r['guard_us']:<11.0f} | {r['p1_prr']:<8.1f}% | {r['p2_prr']:<8.1f}% | {r['p1_miss']:<9} | {r['rx_deaf']:<9} | {r['preamble_coll']:<10} | {r['captures']:<9} | {r['mean_aoi']:<9.1f}ms")

print("=" * 115)

# Write Detailed Report
report_path = os.path.join(PROJECT_DIR, "p2_benchmark_150uav_report.txt")
with open(report_path, "w", encoding="utf-8") as f:
    f.write("# Phase 2 Data Delivery Benchmark Report (150 UAVs, P1=10ms, P2=10ms)\n\n")
    f.write(f"- Swarm Scale       : {num_nodes} UAVs\n")
    f.write(f"- Phase 1 Window    : 10.0 ms (Sidelink Mode 4 S-SPS, 100 µs micro-slot)\n")
    f.write(f"- Phase 2 Window    : 10.0 ms\n")
    f.write(f"- 2 Mbps Packet Air : 436 µs (50B payload + 11B MAC header + 12 symbols PPDU header)\n")
    f.write(f"- Fast Turnaround   : 40 µs (BLE 5.4 fast PLL turnaround)\n\n")
    f.write("| Slot (µs) | Slots | Guard Band | Phase 1 PRR | Phase 2 PRR | P1 Discovery Miss | RX Deafness | Preamble Collisions | Power Captures | Mean AoI (ms) |\n")
    f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
    for r in results:
        f.write(f"| {r['slot_us']:.0f} µs | {r['num_slots']} | {r['guard_us']:.0f} µs | {r['p1_prr']:.1f}% | {r['p2_prr']:.1f}% | {r['p1_miss']} | {r['rx_deaf']} | {r['preamble_coll']} | {r['captures']} | {r['mean_aoi']:.1f} ms |\n")

print(f"\n📄 Detailed report saved to: {report_path}")

if "--autoPush" in sys.argv:
    print("\n📤 Auto-pushing report to GitHub...")
    subprocess.run("git add p2_benchmark_150uav_report.txt && git commit -m 'data: add Phase 2 benchmark results for 150 UAVs (10ms window)' && git push origin main", shell=True, cwd=PROJECT_DIR)
