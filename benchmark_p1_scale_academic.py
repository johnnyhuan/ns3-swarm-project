#!/usr/bin/env python3
"""
UAV Swarm Phase 1 Scalability Benchmark (50 to 150 UAVs)
Compares Proposed Autonomous Slotted MAC (Proposed Scheme) vs CSMA-CA Baseline (BLE 2M PHY).
- Physical Layer: BLE 5.4 2M PHY, C/I Capture Threshold = +6.0 dB
- Swarm Scale: 50 to 150 UAVs (Step 10)
- Airspace: 200m x 200m x 80m 3D Space, UAV Speed = 10.0 m/s
- Academic terminology: Zero mention of cellular terminology.
"""

import subprocess
import os
import sys
import re
from datetime import datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

print("==========================================================================================")
print("🚀 UAV SWARM SCALABILITY BENCHMARK: 50-150 UAVs (PROPOSED SCHEME VS CSMA) 🚀")
print("==========================================================================================")

sim_time = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
p1_duration = 10.0
p1_slot_us = 300.0
capture_thresh_db = 6.0
space_size = 200.0
space_z = 80.0

node_counts = list(range(50, 151, 10))

print(f"• UAV Swarm Scale Points : {node_counts} UAVs (11 scale points)")
print(f"• Physical C/I Threshold : +{capture_thresh_db:.1f} dB (Strict BLE 5.4 Standard)")
print(f"• Broadcast Time Window  : {p1_duration:.1f} ms")
print(f"• Slot Duration          : {p1_slot_us:.0f} µs ({int(p1_duration * 1000.0 / p1_slot_us)} slots)")
print(f"• Airspace Dimensions    : {space_size:.0f}m x {space_size:.0f}m x {space_z:.0f}m")
print(f"• UAV Mobility Speed     : 10.0 m/s")
print(f"• Sim Duration per Run   : {sim_time:.1f} s")
print("------------------------------------------------------------------------------------------\n")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
NS3_DIR = os.path.expanduser("~/ns-3-dev")
if not os.path.exists(NS3_DIR):
    NS3_DIR = PROJECT_DIR

for rel_path in ["scratch/lr-wpan-swarm.cc", "src/lr-wpan/model/lr-wpan-phy.cc", "src/lr-wpan/model/lr-wpan-phy.h"]:
    src_f = os.path.join(PROJECT_DIR, rel_path)
    dst_f = os.path.join(NS3_DIR, rel_path)
    if os.path.exists(src_f) and os.path.abspath(src_f) != os.path.abspath(dst_f):
        try:
            os.makedirs(os.path.dirname(dst_f), exist_ok=True)
            subprocess.run(["cp", src_f, dst_f], check=True)
        except Exception:
            pass

def run_simulation(nodes, enable_proposed):
    for fname in ["p1_ground_truth_report.txt", "p2_ground_truth_report.txt", "run.log"]:
        fpath = os.path.join(NS3_DIR, fname)
        if os.path.exists(fpath):
            try: os.remove(fpath)
            except Exception: pass

    cmd = [
        "./ns3", "run",
        f"scratch/lr-wpan-swarm --numNodes={nodes} --p1Duration={p1_duration} "
        f"--simTime={sim_time} --spaceSize={space_size} --spaceZ={space_z} "
        f"--enableP1Ssa={'true' if enable_proposed else 'false'} "
        f"--p1SlotUs={p1_slot_us} --p1CaptureThresholdDb={capture_thresh_db} "
        f"--phyCaptureMarginDb={capture_thresh_db} --autoPush=false"
    ]

    try:
        proc = subprocess.run(cmd, cwd=NS3_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=300)
        out = proc.stdout
    except subprocess.TimeoutExpired:
        print(f"\n⚠️ Command timed out after 300s!")
        return None

    p1_rpt = os.path.join(NS3_DIR, "p1_ground_truth_report.txt")
    p1_text = ""
    if os.path.exists(p1_rpt):
        with open(p1_rpt, "r", encoding="utf-8", errors="ignore") as f:
            p1_text = f.read()

    combined_stdout = out + "\n" + p1_text
    return parse_metrics(p1_text, combined_stdout)

def parse_metrics(p1_text, stdout_text):
    data = {
        "p1_links": 0, "p1_success": 0, "p1_prr": 0.0, "p1_fails": 0,
        "csma_abort": 0, "rx_deafness": 0, "preamble_coll": 0, "low_sinr": 0, "captures": 0
    }
    src = p1_text if p1_text else stdout_text

    m = re.search(r"Total Expected P1 Neighbor Links.*:\s*(\d+)", src)
    if m: data["p1_links"] = int(m.group(1))

    m = re.search(r"Successfully Received \(Delivered\)\s*:\s*(\d+)\s*\(([\d\.]+)%\)", src)
    if m:
        data["p1_success"] = int(m.group(1))
        data["p1_prr"] = float(m.group(2))

    m = re.search(r"Failed Link Receptions \(Dropped/Missed\)\s*:\s*(\d+)", src)
    if m: data["p1_fails"] = int(m.group(1))

    m = re.search(r"SENDER_CSMA_ABORT\s*:\s*(\d+)", src)
    if m: data["csma_abort"] = int(m.group(1))

    m = re.search(r"RX_DEAFNESS_BUSY_TX\s*:\s*(\d+)", src)
    if m: data["rx_deafness"] = int(m.group(1))

    m = re.search(r"PREAMBLE_COLLISION_BUSY_RX\s*:\s*(\d+)", src)
    if m: data["preamble_coll"] = int(m.group(1))

    m = re.search(r"PREAMBLE_LOW_SINR\s*:\s*(\d+)", src)
    if m: data["low_sinr"] = int(m.group(1))

    m = re.search(r"Total Power Capture Events Triggered\s*:\s*(\d+)", src)
    if m: data["captures"] = int(m.group(1))

    return data

results = []

for nodes in node_counts:
    print(f"▶️ Testing Swarm Scale: {nodes} UAVs...")

    print(f"   [1/2] Running CSMA/CA Baseline ... ", end="", flush=True)
    csma_res = run_simulation(nodes, enable_proposed=False)
    if csma_res is not None:
        print(f"PRR: {csma_res['p1_prr']:.1f}% | Coll: {csma_res['preamble_coll']} | Aborts: {csma_res['csma_abort']}")
    else:
        print(f"ERROR")

    print(f"   [2/2] Running Proposed Autonomous Slotted MAC ... ", end="", flush=True)
    prop_res = run_simulation(nodes, enable_proposed=True)
    if prop_res is not None:
        print(f"PRR: {prop_res['p1_prr']:.1f}% | Coll: {prop_res['preamble_coll']} | Captures: {prop_res['captures']}")
    else:
        print("ERROR")

    diff = (prop_res['p1_prr'] - csma_res['p1_prr']) if (csma_res and prop_res) else None
    results.append({"nodes": nodes, "csma": csma_res, "prop": prop_res, "diff": diff})

# Output Summary Table
print("\n" + "=" * 115)
print("📊 UAV SWARM SCALE BENCHMARK SUMMARY (50-150 UAVs, C/I >= +6.0 dB) 📊")
print("=" * 115)
print(f"| {'Nodes':^7} | {'CSMA PRR':^10} | {'Proposed PRR':^12} | {'Δ Gain':^9} | {'CSMA Abort':^11} | {'CSMA Coll':^10} | {'Proposed Capt':^13} |")
print("|" + "-" * 9 + "|" + "-" * 12 + "|" + "-" * 14 + "|" + "-" * 11 + "|" + "-" * 13 + "|" + "-" * 12 + "|" + "-" * 15 + "|")

for r in results:
    nodes = r["nodes"]
    csma_prr = f"{r['csma']['p1_prr']:.1f}%" if r["csma"] else "N/A"
    prop_prr = f"{r['prop']['p1_prr']:.1f}%" if r["prop"] else "N/A"
    diff_str = f"{r['diff']:+6.1f}%" if r["diff"] is not None else "N/A"
    csma_abort = f"{r['csma']['csma_abort']:,}" if r["csma"] else "N/A"
    csma_coll = f"{r['csma']['preamble_coll']:,}" if r["csma"] else "N/A"
    prop_capt = f"{r['prop']['captures']:,}" if r["prop"] else "N/A"
    print(f"| {nodes:^7} | {csma_prr:^10} | {prop_prr:^12} | {diff_str:^9} | {csma_abort:^11} | {csma_coll:^10} | {prop_capt:^13} |")

print("=" * 115)

# Save Reports & Figures
txt_path = os.path.join(PROJECT_DIR, "academic_uav_scale_results.txt")
csv_path = os.path.join(PROJECT_DIR, "academic_uav_scale_results.csv")

with open(txt_path, "w", encoding="utf-8") as f:
    f.write("# UAV Swarm Phase 1 Benchmark: 50 to 150 UAVs\n")
    f.write(f"- Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write(f"- Window: {p1_duration:.1f} ms | Slot Width: {p1_slot_us:.0f} µs | Capture Threshold: +{capture_thresh_db:.1f} dB\n\n")
    f.write("| Nodes | CSMA PRR (%) | Proposed PRR (%) | Δ Gain (%) | CSMA Aborts | Proposed Captures |\n")
    f.write("| :--- | :--- | :--- | :--- | :--- | :--- |\n")
    for r in results:
        f.write(f"| {r['nodes']} | {r['csma']['p1_prr']:.1f}% | {r['prop']['p1_prr']:.1f}% | {r['diff']:+.1f}% | {r['csma']['csma_abort']} | {r['prop']['captures']} |\n")

with open(csv_path, "w", encoding="utf-8") as f:
    f.write("Nodes,CSMA_PRR,Proposed_PRR,Delta_Gain,CSMA_Aborts,CSMA_Collisions,Proposed_Collisions,Proposed_Captures\n")
    for r in results:
        f.write(f"{r['nodes']},{r['csma']['p1_prr']:.2f},{r['prop']['p1_prr']:.2f},{r['diff']:.2f},{r['csma']['csma_abort']},{r['csma']['preamble_coll']},{r['prop']['preamble_coll']},{r['prop']['captures']}\n")

# Re-plot Figures
subprocess.run(["python3", os.path.join(PROJECT_DIR, "plot_academic_50_150.py")], check=True)
print("🎉 Benchmark complete! Plots saved to academic_uav_scale_prr.png and academic_uav_scale_dashboard.png")
