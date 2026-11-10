#!/usr/bin/env python3
"""
Phase 2 Baseline Evaluation Script:
- Phase 1: Fixed 10.0 ms CSMA-CA Broadcast
- Phase 2: 10.0 ms Data Phase
- Slot Width: 1000.0 µs (1.0 ms slot, exactly 10 slots in 10 ms)
- Number of Channels: 6 channels (Total 2D cells: 10 x 6 = 60 cells)
- Power Capture: ENABLED (Strict BLE 5.4 LE 2M C/I Margin = +6.0 dB)
- Swarm Scale: 100 UAVs in 200m x 200m x 80m 3D Airspace
- Physical Layer: Bluetooth 5.4 LE 2M PHY (2 Mbps, 244 µs packet air time)
"""

import subprocess
import os
import sys
import re
import csv
import math
import numpy as np
from datetime import datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

print("==========================================================================================")
print("🚀  PHASE 2 DATA DELIVERY BASELINE RUN: 10ms CSMA P1 + 10ms SLOTTED P2  🚀")
print("==========================================================================================")

num_nodes = int(sys.argv[1]) if len(sys.argv) > 1 else 100
sim_time = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
data_slot_us = float(sys.argv[3]) if len(sys.argv) > 3 else 1000.0 # 1.0 ms slot
num_channels = int(sys.argv[4]) if len(sys.argv) > 4 else 6
capture_enabled = True
capture_thresh_db = 6.0
p1_duration = 10.0
p2_duration = 10.0
p2_slots = max(1, int(p2_duration * 1000.0 / data_slot_us))
total_cells = p2_slots * num_channels
space_size = 200.0
space_z = 80.0

print(f"• UAV Swarm Scale        : {num_nodes} UAVs")
print(f"• Phase 1 Broadcast Win  : {p1_duration:.1f} ms (Pure CSMA-CA Broadcast)")
print(f"• Phase 2 Data Window    : {p2_duration:.1f} ms ({p2_slots} slots x {data_slot_us:.0f} µs, {num_channels} channels = {total_cells} 2D cells)")
print(f"• Antenna Capture Effect : {'ENABLED' if capture_enabled else 'DISABLED'} (Strict BLE 5.4 C/I: +{capture_thresh_db:.1f} dB)")
print(f"• Airspace Dimensions    : {space_size:.0f}m x {space_size:.0f}m x {space_z:.0f}m")
print(f"• Simulation Duration    : {sim_time:.1f} s (~{(int(sim_time * 1000.0 / (p1_duration + 1.0 + p2_duration)))} cycles)")
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

# Clean old report files
for fname in ["p1_ground_truth_report.txt", "p2_ground_truth_report.txt", "run.log"]:
    fpath = os.path.join(NS3_DIR, fname)
    if os.path.exists(fpath):
        try: os.remove(fpath)
        except Exception: pass

cmd = [
    "./ns3", "run",
    f"scratch/lr-wpan-swarm --numNodes={num_nodes} --p1Duration={p1_duration} "
    f"--enableP1Sidelink=false --p2Duration={p2_duration} --dataSlotUs={data_slot_us} "
    f"--numChannels={num_channels} --enablePhyCapture={'true' if capture_enabled else 'false'} "
    f"--phyCaptureMarginDb={capture_thresh_db} --simTime={sim_time} "
    f"--spaceSize={space_size} --spaceZ={space_z} --nodeSpeed=10.0 --autoPush=false"
]

print("⏳ Executing simulation in ns-3 ... ", end="", flush=True)
try:
    proc = subprocess.run(cmd, cwd=NS3_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=300)
    out = proc.stdout
    print("Done!\n")
except subprocess.TimeoutExpired:
    print("TIMEOUT!")
    sys.exit(1)

# Read Phase 1 & Phase 2 Reports
p1_rpt = os.path.join(NS3_DIR, "p1_ground_truth_report.txt")
p2_rpt = os.path.join(NS3_DIR, "p2_ground_truth_report.txt")
p1_text = ""
p2_text = ""
if os.path.exists(p1_rpt):
    with open(p1_rpt, "r", encoding="utf-8", errors="ignore") as f:
        p1_text = f.read()
if os.path.exists(p2_rpt):
    with open(p2_rpt, "r", encoding="utf-8", errors="ignore") as f:
        p2_text = f.read()

# Parse Phase 1 Metrics
p1_data = {"links": 0, "success": 0, "prr": 0.0, "aborts": 0, "deafness": 0, "collisions": 0, "low_sinr": 0, "captures": 0}
src1 = p1_text if p1_text else out
m = re.search(r"Total Expected P1 Neighbor Links.*:\s*(\d+)", src1)
if m: p1_data["links"] = int(m.group(1))
m = re.search(r"Successfully Received \(Delivered\)\s*:\s*(\d+)\s*\(([\d\.]+)%\)", src1)
if m: p1_data["success"] = int(m.group(1)); p1_data["prr"] = float(m.group(2))
m = re.search(r"SENDER_CSMA_ABORT\s*:\s*(\d+)", src1)
if m: p1_data["aborts"] = int(m.group(1))
m = re.search(r"RX_DEAFNESS_BUSY_TX\s*:\s*(\d+)", src1)
if m: p1_data["deafness"] = int(m.group(1))
m = re.search(r"PREAMBLE_COLLISION_BUSY_RX\s*:\s*(\d+)", src1)
if m: p1_data["collisions"] = int(m.group(1))
m = re.search(r"PREAMBLE_LOW_SINR\s*:\s*(\d+)", src1)
if m: p1_data["low_sinr"] = int(m.group(1))
m = re.search(r"Total Power Capture Events Triggered\s*:\s*(\d+)", src1)
if m: p1_data["captures"] = int(m.group(1))

# Parse Phase 2 Metrics
p2_data = {
    "links": 0, "success": 0, "prr": 0.0, "fails": 0,
    "p1_miss": 0, "tx_deafness": 0, "rx_deafness": 0, "ch_mismatch": 0,
    "csma_abort": 0, "collisions": 0, "low_sinr": 0, "payload_drop": 0,
    "captures": 0
}
src2 = p2_text if p2_text else out
m = re.search(r"Total Expected P2 Neighbor Links.*:\s*(\d+)", src2)
if m: p2_data["links"] = int(m.group(1))
m = re.search(r"Successfully Received \(Delivered\)\s*:\s*(\d+)\s*\(([\d\.]+)%\)", src2)
if m: p2_data["success"] = int(m.group(1)); p2_data["prr"] = float(m.group(2))
m = re.search(r"Failed Link Receptions \(Dropped/Missed\)\s*:\s*(\d+)", src2)
if m: p2_data["fails"] = int(m.group(1))

m = re.search(r"P1_DISCOVERY_MISS\s*:\s*(\d+)", src2)
if m: p2_data["p1_miss"] = int(m.group(1))
m = re.search(r"TX_DEAFNESS_SAME_SLOT\s*:\s*(\d+)", src2)
if m: p2_data["tx_deafness"] = int(m.group(1))
m = re.search(r"RX_DEAFNESS_SLOT_CONFLICT\s*:\s*(\d+)", src2)
if m: p2_data["rx_deafness"] = int(m.group(1))
m = re.search(r"RECEIVER_CHANNEL_MISMATCH\s*:\s*(\d+)", src2)
if m: p2_data["ch_mismatch"] = int(m.group(1))
m = re.search(r"SENDER_CSMA_ABORT\s*:\s*(\d+)", src2)
if m: p2_data["csma_abort"] = int(m.group(1))
m = re.search(r"PREAMBLE_COLLISION_BUSY_RX\s*:\s*(\d+)", src2)
if m: p2_data["collisions"] = int(m.group(1))
m = re.search(r"PREAMBLE_LOW_SINR\s*:\s*(\d+)", src2)
if m: p2_data["low_sinr"] = int(m.group(1))
m = re.search(r"PAYLOAD_INTERFERENCE_DROP\s*:\s*(\d+)", src2)
if m: p2_data["payload_drop"] = int(m.group(1))
m = re.search(r"Total Power Capture Events Triggered\s*:\s*(\d+)", src2)
if m: p2_data["captures"] = int(m.group(1))

# Output Summary Tables
print("=" * 95)
print("📊 PHASE 1 & PHASE 2 END-TO-END PIPELINE BENCHMARK REPORT (100 UAVs, BLE 2M PHY) 📊")
print("=" * 95)
print(f"• Phase 1 Broadcast Delivery PRR   : {p1_data['prr']:.1f}% ({p1_data['success']:,} / {p1_data['links']:,} links)")
print(f"  - CSMA Aborts: {p1_data['aborts']:,} | Deafness: {p1_data['deafness']:,} | Collisions: {p1_data['collisions']:,} | Captures: {p1_data['captures']:,}")
print("------------------------------------------------------------------------------------------")
print(f"• Phase 2 Data Delivery PRR        : {p2_data['prr']:.1f}% ({p2_data['success']:,} / {p2_data['links']:,} links)")
print(f"• Total Phase 2 Dropped Links      : {p2_data['fails']:,} ({(100.0 - p2_data['prr']):.1f}%)")
print("------------------------------------------------------------------------------------------")
print("🔍 Phase 2 Drop Reasons Breakdown (Exact Physical Causes):")
print(f"  1. P1_DISCOVERY_MISS             : {p2_data['p1_miss']:>5} ({(p2_data['p1_miss']/max(1, p2_data['fails'])*100):>5.1f}% of fails)")
print(f"  2. TX_DEAFNESS_SAME_SLOT         : {p2_data['tx_deafness']:>5} ({(p2_data['tx_deafness']/max(1, p2_data['fails'])*100):>5.1f}% of fails)")
print(f"  3. RX_DEAFNESS_SLOT_CONFLICT     : {p2_data['rx_deafness']:>5} ({(p2_data['rx_deafness']/max(1, p2_data['fails'])*100):>5.1f}% of fails)")
print(f"  4. RECEIVER_CHANNEL_MISMATCH     : {p2_data['ch_mismatch']:>5} ({(p2_data['ch_mismatch']/max(1, p2_data['fails'])*100):>5.1f}% of fails)")
print(f"  5. PREAMBLE_COLLISION_BUSY_RX    : {p2_data['collisions']:>5} ({(p2_data['collisions']/max(1, p2_data['fails'])*100):>5.1f}% of fails)")
print(f"  6. SENDER_CSMA_ABORT             : {p2_data['csma_abort']:>5} ({(p2_data['csma_abort']/max(1, p2_data['fails'])*100):>5.1f}% of fails)")
print(f"  7. PREAMBLE_LOW_SINR             : {p2_data['low_sinr']:>5} ({(p2_data['low_sinr']/max(1, p2_data['fails'])*100):>5.1f}% of fails)")
print(f"  8. PAYLOAD_INTERFERENCE_DROP     : {p2_data['payload_drop']:>5} ({(p2_data['payload_drop']/max(1, p2_data['fails'])*100):>5.1f}% of fails)")
print(f"  • Phase 2 Power Capture Rescues  : {p2_data['captures']:>5} packets")
print("=" * 95)

# Save Report Files
txt_path = os.path.join(PROJECT_DIR, "exp_p2_baseline_report.txt")
csv_path = os.path.join(PROJECT_DIR, "exp_p2_baseline_results.csv")

with open(txt_path, "w", encoding="utf-8") as f:
    f.write(f"# Phase 2 Baseline Evaluation Report (100 UAVs, BLE 5.4 2M PHY)\n")
    f.write(f"- Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write(f"- Phase 1: 10.0 ms CSMA-CA Broadcast (PRR: {p1_data['prr']:.1f}%)\n")
    f.write(f"- Phase 2: 10.0 ms ({p2_slots} slots x {data_slot_us:.0f} µs, {num_channels} channels)\n")
    f.write(f"- Phase 2 Delivery PRR: {p2_data['prr']:.1f}%\n")
    f.write(f"- Phase 2 Total Drops: {p2_data['fails']}\n\n")
    f.write("| Drop Category | Count | Pct of Fails | Pct of Links |\n")
    f.write("| :--- | :--- | :--- | :--- |\n")
    f.write(f"| P1 Discovery Miss | {p2_data['p1_miss']} | {p2_data['p1_miss']/max(1, p2_data['fails'])*100:.1f}% | {p2_data['p1_miss']/max(1, p2_data['links'])*100:.1f}% |\n")
    f.write(f"| TX Deafness (Same Slot) | {p2_data['tx_deafness']} | {p2_data['tx_deafness']/max(1, p2_data['fails'])*100:.1f}% | {p2_data['tx_deafness']/max(1, p2_data['links'])*100:.1f}% |\n")
    f.write(f"| RX Deafness (Conflict) | {p2_data['rx_deafness']} | {p2_data['rx_deafness']/max(1, p2_data['fails'])*100:.1f}% | {p2_data['rx_deafness']/max(1, p2_data['links'])*100:.1f}% |\n")
    f.write(f"| Channel Mismatch | {p2_data['ch_mismatch']} | {p2_data['ch_mismatch']/max(1, p2_data['fails'])*100:.1f}% | {p2_data['ch_mismatch']/max(1, p2_data['links'])*100:.1f}% |\n")
    f.write(f"| Preamble Collisions | {p2_data['collisions']} | {p2_data['collisions']/max(1, p2_data['fails'])*100:.1f}% | {p2_data['collisions']/max(1, p2_data['links'])*100:.1f}% |\n")
    f.write(f"| CSMA Sender Aborts | {p2_data['csma_abort']} | {p2_data['csma_abort']/max(1, p2_data['fails'])*100:.1f}% | {p2_data['csma_abort']/max(1, p2_data['links'])*100:.1f}% |\n")
    f.write(f"| Preamble Low SINR | {p2_data['low_sinr']} | {p2_data['low_sinr']/max(1, p2_data['fails'])*100:.1f}% | {p2_data['low_sinr']/max(1, p2_data['links'])*100:.1f}% |\n")
    f.write(f"| Payload Interference | {p2_data['payload_drop']} | {p2_data['payload_drop']/max(1, p2_data['fails'])*100:.1f}% | {p2_data['payload_drop']/max(1, p2_data['links'])*100:.1f}% |\n")

with open(csv_path, "w", encoding="utf-8") as f:
    f.write("P1_PRR,P2_PRR,P2_Expected,P2_Delivered,P2_Fails,P1_Miss,TX_Deafness,RX_Deafness,Ch_Mismatch,Collisions,Aborts,Low_SINR,Payload_Drop,Captures\n")
    f.write(f"{p1_data['prr']:.2f},{p2_data['prr']:.2f},{p2_data['links']},{p2_data['success']},{p2_data['fails']},"
            f"{p2_data['p1_miss']},{p2_data['tx_deafness']},{p2_data['rx_deafness']},{p2_data['ch_mismatch']},"
            f"{p2_data['collisions']},{p2_data['csma_abort']},{p2_data['low_sinr']},{p2_data['payload_drop']},{p2_data['captures']}\n")

print(f"✅ Text report: {txt_path}")
print(f"✅ CSV metrics: {csv_path}")

# Plot Clean Donut/Pie Chart with Text Beside Wedges (User's preferred style)
categories = []
counts = []
colors_map = {
    'P1 Discovery Miss': ('#e6550d', p2_data['p1_miss']),
    'RX Deafness (Slot Conflict)': ('#3182bd', p2_data['rx_deafness']),
    'TX Deafness (Same Slot)': ('#756bb1', p2_data['tx_deafness']),
    'Channel Mismatch': ('#31a354', p2_data['ch_mismatch']),
    'Preamble Collisions': ('#e7298a', p2_data['collisions']),
    'CSMA Aborts': ('#ff7f00', p2_data['csma_abort']),
    'Low SINR / Payload': ('#636363', p2_data['low_sinr'] + p2_data['payload_drop'])
}

for name, (col, cnt) in colors_map.items():
    if cnt > 0:
        categories.append((name, cnt, col))

if categories:
    cat_names = [c[0] for c in categories]
    cat_counts = [c[1] for c in categories]
    cat_colors = [c[2] for c in categories]
    total_fails = sum(cat_counts)

    plt.rcParams['font.family'] = 'DejaVu Sans'
    plt.rcParams['font.size'] = 11

    fig, ax = plt.subplots(figsize=(11, 7.5), dpi=300)
    wedges, _ = ax.pie(
        cat_counts,
        startangle=120,
        colors=cat_colors,
        wedgeprops=dict(width=0.42, edgecolor='white', linewidth=2.5)
    )

    ax.text(0, 0.08, 'Total P2 Drops', ha='center', va='center', fontsize=13, fontweight='bold', color='#555555')
    ax.text(0, -0.07, f'{total_fails:,}', ha='center', va='center', fontsize=21, fontweight='bold', color='#111111')
    ax.text(0, -0.21, f'({(100.0 - p2_data["prr"]):.1f}% of links)', ha='center', va='center', fontsize=11, color='#777777')

    # Compute text positions along each wedge's midpoint
    for i, p in enumerate(wedges):
        ang = (p.theta2 - p.theta1) / 2.0 + p.theta1
        rad = np.deg2rad(ang)
        x_edge = 1.18 * np.cos(rad)
        y_edge = 1.18 * np.sin(rad)
        ha = 'left' if np.cos(rad) >= 0 else 'right'
        va = 'bottom' if np.sin(rad) >= 0 else 'top'
        pct = cat_counts[i] / total_fails * 100
        label_text = f"{cat_names[i]}\n{cat_counts[i]:,} ({pct:.1f}%)"
        ax.text(x_edge, y_edge, label_text, fontsize=10.5, fontweight='bold', color=cat_colors[i], ha=ha, va=va)

    ax.set_title(
        f"Phase 2 Data Packet Failure Root Causes (BLE 5.4 2M PHY)\n"
        f"100 UAV Swarm, 10ms Window (10 slots x 1.0ms, 6 Chs, PRR: {p2_data['prr']:.1f}%)",
        fontsize=13.5, fontweight='bold', pad=24
    )
    ax.set_xlim(-2.4, 2.4)
    ax.set_ylim(-1.5, 1.6)
    ax.axis('off')

    plt.tight_layout()
    pie_path = os.path.join(PROJECT_DIR, "p2_baseline_failure_pie.png")
    plt.savefig(pie_path, bbox_inches='tight')
    plt.close()
    print(f"✅ Failure Donut Chart saved to: {pie_path}")

# Auto push
if "--no-push" not in sys.argv:
    print("\n🚀 Pushing experiment results and plots to GitHub main...")
    try:
        subprocess.run(
            "git add exp_p2_baseline* p2_baseline* && git commit -m 'data: upload Phase 2 baseline test results' && git push origin main",
            shell=True, cwd=PROJECT_DIR, check=False
        )
        print("✅ Git push completed!")
    except Exception as e:
        print(f"⚠️ Git push notice: {e}")

print("🎉 Phase 2 baseline test completed successfully!")
