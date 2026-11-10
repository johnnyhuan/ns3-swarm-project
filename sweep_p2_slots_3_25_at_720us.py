#!/usr/bin/env python3
"""
Phase 2 Slot Count Scaling Benchmark (3 ~ 25 Slots @ 720µs Fixed Slot Duration):
Explores the scaling capacity and saturation of Phase 2 slot allocation:
- Slot Duration: Fixed at 720.0 µs (Physical safety margin: +98µs over 622µs hard limit)
- Tested Slot Counts: 3 to 25 slots (range(3, 26), 23 continuous evaluation points)
- Phase 2 Duration: Dynamically scaled from 2.16 ms to 18.00 ms (s * 0.72 ms)
- Available Cells (6 Channels): 18 cells (3 slots) to 150 cells (25 slots)
- Phase 1: Fixed 10.0 ms CSMA-CA Broadcast with Capture (+6.0 dB margin)
- Phase 2: Capture DISABLED (pure physical interference / zero capture rescues)
- Swarm Scale: 100 UAVs in 200m x 200m x 80m 3D airspace
- Physical Layer: Bluetooth 5.4 LE 2M PHY (2 Mbps, 404µs packet air time)
"""

import subprocess
import os
import sys
import re
import csv
from datetime import datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

print("==========================================================================================")
print("🔬 PHASE 2 SLOT COUNT SCALING BENCHMARK (3 ~ 25 Slots @ 720µs, 100 UAVs, BLE 2M PHY) 🔬")
print("==========================================================================================")

num_nodes = int(sys.argv[1]) if len(sys.argv) > 1 else 100
sim_time = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
num_channels = int(sys.argv[3]) if len(sys.argv) > 3 else 6
slot_us = float(sys.argv[4]) if len(sys.argv) > 4 else 720.0
p1_duration = 10.0
space_size = 200.0
space_z = 80.0
capture_thresh_db = 6.0

# 3 to 25 slots inclusive
slots_range = list(range(3, 26))

print(f"• UAV Swarm Scale        : {num_nodes} UAVs in {space_size:.0f}m x {space_size:.0f}m x {space_z:.0f}m")
print(f"• Phase 1 Broadcast Win  : {p1_duration:.1f} ms (CSMA-CA, Capture ENABLED: +{capture_thresh_db:.1f} dB)")
print(f"• Slot Duration (Fixed)  : {slot_us:.1f} µs (Bluetooth 5.4 LE 2M PHY, 50µs Guard Band)")
print(f"• Slot Counts Evaluated  : {slots_range[0]} ~ {slots_range[-1]} slots ({len(slots_range)} points)")
print(f"• Phase 2 Duration Range : {slots_range[0] * slot_us / 1000.0:.2f} ms ~ {slots_range[-1] * slot_us / 1000.0:.2f} ms")
print(f"• Total Cell Range (6 Ch): {slots_range[0] * num_channels} cells ~ {slots_range[-1] * num_channels} cells")
print(f"• Simulation Time        : {sim_time:.1f} s per evaluation point")
print("------------------------------------------------------------------------------------------\n")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
NS3_DIR = os.path.expanduser("~/ns-3-dev")
if not os.path.exists(NS3_DIR):
    NS3_DIR = PROJECT_DIR

# Sync updated files to NS3_DIR if running from standard ns-3 folder
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
            os.makedirs(os.path.dirname(dst_f), exist_ok=True)
            subprocess.run(["cp", src_f, dst_f], check=True)
        except Exception:
            pass

def run_single_slot_count(num_slots):
    p2_duration_ms = num_slots * slot_us / 1000.0

    for fname in ["p1_ground_truth_report.txt", "p2_ground_truth_report.txt", "run.log"]:
        fpath = os.path.join(NS3_DIR, fname)
        if os.path.exists(fpath):
            try: os.remove(fpath)
            except Exception: pass

    cmd = [
        "./ns3", "run",
        f"scratch/lr-wpan-swarm --numNodes={num_nodes} --p1Duration={p1_duration} "
        f"--numSlots={num_slots} --p2Duration={p2_duration_ms:.4f} --dataSlotUs={slot_us} "
        f"--numChannels={num_channels} --simTime={sim_time} --spaceSize={space_size} --spaceZ={space_z} "
        f"--p1TxPower=0 --p2TxPower=-2 --p1CcaThresholdDbm=-96.58 --nodeSpeed=10.0 "
        f"--enableP1Sidelink=false --enablePhyCapture=true --enableP2Capture=false "
        f"--p1CaptureThresholdDb={capture_thresh_db} --phyCaptureMarginDb={capture_thresh_db} --autoPush=false"
    ]

    try:
        proc = subprocess.run(cmd, cwd=NS3_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=300)
        stdout_output = proc.stdout
        if proc.returncode != 0:
            print(f"\n❌ [NS3 ERROR] Command returned exit code {proc.returncode} at slots = {num_slots}:")
            lines = stdout_output.strip().split("\n")
            print("\n".join(lines[-25:]))
    except subprocess.TimeoutExpired:
        print(f"TIMEOUT at slots = {num_slots}!")
        return None

    p1_report = os.path.join(NS3_DIR, "p1_ground_truth_report.txt")
    p2_report = os.path.join(NS3_DIR, "p2_ground_truth_report.txt")

    p1_text = ""
    p2_text = ""
    if os.path.exists(p1_report):
        with open(p1_report, "r", encoding="utf-8", errors="ignore") as f:
            p1_text = f.read()
    if os.path.exists(p2_report):
        with open(p2_report, "r", encoding="utf-8", errors="ignore") as f:
            p2_text = f.read()

    combined_out = stdout_output + "\n" + p1_text + "\n" + p2_text
    return parse_p2_metrics(p1_text, p2_text, combined_out, num_slots, p2_duration_ms)

def parse_p2_metrics(p1_text, p2_text, stdout_text, num_slots, p2_duration_ms):
    total_cells = num_slots * num_channels
    cycle_ms = p1_duration + 1.0 + p2_duration_ms

    data = {
        "num_slots": num_slots,
        "slot_us": slot_us,
        "p2_duration_ms": p2_duration_ms,
        "cycle_ms": cycle_ms,
        "total_cells": total_cells,
        "p1_prr": 0.0,
        "p2_links": 0,
        "p2_success": 0,
        "p2_prr": 0.0,
        "p2_fails": 0,
        "p1_miss": 0,
        "tx_deafness": 0,
        "rx_deafness": 0,
        "ch_mismatch": 0,
        "csma_abort": 0,
        "collisions": 0,
        "low_sinr": 0,
        "payload_drop": 0,
        "slot_cutoff": 0,
        "p2_captures": 0
    }

    # Parse P1 PRR
    m = re.search(r"Successfully Received \(Delivered\)\s*:\s*\d+\s*\(([\d\.]+)%\)", p1_text)
    if m: data["p1_prr"] = float(m.group(1))

    # Parse P2 Delivered
    src = p2_text if p2_text else stdout_text
    m = re.search(r"Total Expected P2 Neighbor Links.*:\s*(\d+)", src)
    if m: data["p2_links"] = int(m.group(1))

    m = re.search(r"Successfully Received \(Delivered\)\s*:\s*(\d+)\s*\(([\d\.]+)%\)", src)
    if m:
        data["p2_success"] = int(m.group(1))
        data["p2_prr"] = float(m.group(2))

    m = re.search(r"Failed Link Receptions \(Dropped/Missed\)\s*:\s*(\d+)", src)
    if m: data["p2_fails"] = int(m.group(1))

    m = re.search(r"P1_DISCOVERY_MISS\s*:\s*(\d+)", src)
    if m: data["p1_miss"] = int(m.group(1))

    m = re.search(r"TX_DEAFNESS_SAME_SLOT\s*:\s*(\d+)", src)
    if m: data["tx_deafness"] = int(m.group(1))

    m = re.search(r"RX_DEAFNESS_SLOT_CONFLICT\s*:\s*(\d+)", src)
    if m: data["rx_deafness"] = int(m.group(1))

    m = re.search(r"RECEIVER_CHANNEL_MISMATCH\s*:\s*(\d+)", src)
    if m: data["ch_mismatch"] = int(m.group(1))

    m = re.search(r"PREAMBLE_COLLISION_BUSY_RX\s*:\s*(\d+)", src)
    if m: data["collisions"] = int(m.group(1))

    m = re.search(r"PREAMBLE_LOW_SINR\s*:\s*(\d+)", src)
    if m: data["low_sinr"] = int(m.group(1))

    m = re.search(r"PAYLOAD_INTERFERENCE_DROP\s*:\s*(\d+)", src)
    if m: data["payload_drop"] = int(m.group(1))

    m = re.search(r"SLOT_BOUNDARY_CUTOFF\s*:\s*(\d+)", src)
    if m: data["slot_cutoff"] = int(m.group(1))

    m = re.search(r"Total Power Capture Events Triggered\s*:\s*(\d+)", src)
    if m: data["p2_captures"] = int(m.group(1))

    return data

results = []

for s in slots_range:
    p2_dur = s * slot_us / 1000.0
    cells = s * num_channels
    print(f"▶️ Testing Slots = {s:>2} ({p2_dur:>5.2f} ms, {cells:>3} cells) ... ", end="", flush=True)
    res = run_single_slot_count(s)
    if res is not None:
        print(f"P2 PRR: {res['p2_prr']:>5.1f}% ({res['p2_success']:,}) | Cutoff: {res['slot_cutoff']:>4} | RX Deaf: {res['rx_deafness']:>4} | Coll: {res['collisions']:>3}")
        results.append(res)
    else:
        print("ERROR / TIMEOUT")

# Summary Table
print("\n" + "=" * 135)
print("📊 PHASE 2 SLOT COUNT SCALING BENCHMARK SUMMARY (3 ~ 25 Slots @ 720µs, 6 Channels) 📊")
print("=" * 135)
print(f"| {'Slots':^7} | {'P2 Dur':^10} | {'Cells':^7} | {'Cycle Time':^12} | {'P1 PRR':^9} | {'P2 Data PRR':^15} | {'Cutoff':^8} | {'RX Deafness':^13} | {'Collisions':^12} |")
print("|" + "-" * 9 + "|" + "-" * 12 + "|" + "-" * 9 + "|" + "-" * 14 + "|" + "-" * 11 + "|" + "-" * 17 + "|" + "-" * 10 + "|" + "-" * 15 + "|" + "-" * 14 + "|")

best_idx = 0
best_prr = 0.0

for i, r in enumerate(results):
    if r["p2_prr"] > best_prr:
        best_prr = r["p2_prr"]
        best_idx = i

    slots_str = f"{r['num_slots']}"
    dur_str = f"{r['p2_duration_ms']:.2f} ms"
    cells_str = f"{r['total_cells']}"
    cycle_str = f"{r['cycle_ms']:.2f} ms"
    p1_str = f"{r['p1_prr']:.1f}%"
    p2_str = f"{r['p2_prr']:.1f}% ({r['p2_success']:,})"
    cutoff_str = f"{r['slot_cutoff']:,}"
    rx_deaf_str = f"{r['rx_deafness']:,}"
    coll_str = f"{r['collisions']:,}"
    print(f"| {slots_str:^7} | {dur_str:^10} | {cells_str:^7} | {cycle_str:^12} | {p1_str:^9} | {p2_str:^15} | {cutoff_str:^8} | {rx_deaf_str:^13} | {coll_str:^12} |")

print("=" * 135)
print(f"🏆 Optimal Configuration: {results[best_idx]['num_slots']} Slots ({results[best_idx]['p2_duration_ms']:.2f} ms, {results[best_idx]['total_cells']} cells) achieving P2 PRR = {best_prr:.1f}%\n")

# Save CSV and TXT
csv_path = os.path.join(PROJECT_DIR, "exp_p2_slots_3_25_results.csv")
txt_path = os.path.join(PROJECT_DIR, "exp_p2_slots_3_25_report.txt")

with open(csv_path, "w", encoding="utf-8") as f:
    f.write("Num_Slots,Slot_Duration_us,P2_Duration_ms,Cycle_ms,Total_Cells,P1_PRR,P2_Links,P2_Success,P2_PRR,P1_Miss,TX_Deafness,RX_Deafness,Channel_Mismatch,Collisions,Low_SINR,Payload_Drop,Slot_Cutoff,P2_Captures\n")
    for r in results:
        f.write(f"{r['num_slots']},{r['slot_us']:.1f},{r['p2_duration_ms']:.4f},{r['cycle_ms']:.4f},{r['total_cells']},{r['p1_prr']:.2f},{r['p2_links']},{r['p2_success']},{r['p2_prr']:.2f},{r['p1_miss']},{r['tx_deafness']},{r['rx_deafness']},{r['ch_mismatch']},{r['collisions']},{r['low_sinr']},{r['payload_drop']},{r['slot_cutoff']},{r['p2_captures']}\n")

with open(txt_path, "w", encoding="utf-8") as f:
    f.write(f"# Phase 2 Slot Count Scaling Benchmark (3 ~ 25 Slots @ 720µs Fixed)\n")
    f.write(f"- Benchmark Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write(f"- Swarm Scale: {num_nodes} UAVs in 200m x 200m x 80m 3D airspace\n")
    f.write(f"- PHY Standard: Bluetooth 5.4 LE 2M PHY (2 Mbps, 720.0µs slot, 50µs guard band)\n")
    f.write(f"- Phase 1: Fixed 10.0 ms CSMA-CA Broadcast with Capture (+6.0 dB margin)\n")
    f.write(f"- Phase 2: Variable Slot Allocation (3 ~ 25 Slots), 6 Channels, Capture DISABLED\n\n")
    f.write(f"| Slots | P2 Duration | Total Cells (6 Ch) | Cycle Time | P1 PRR | P2 Data PRR | Cutoff Drops | RX Deafness | Preamble Collisions |\n")
    f.write(f"| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |\n")
    for r in results:
        f.write(f"| {r['num_slots']} | {r['p2_duration_ms']:.2f} ms | {r['total_cells']} | {r['cycle_ms']:.2f} ms | {r['p1_prr']:.1f}% | {r['p2_prr']:.1f}% ({r['p2_success']:,}) | {r['slot_cutoff']} | {r['rx_deafness']:,} | {r['collisions']} |\n")
    f.write(f"\n- Optimal Slot Count: {results[best_idx]['num_slots']} slots ({results[best_idx]['p2_duration_ms']:.2f} ms, {results[best_idx]['total_cells']} cells) achieving {best_prr:.1f}% P2 PRR\n")

print(f"✅ Saved benchmark data to:\n  - {csv_path}\n  - {txt_path}")

# Plotting Curves
slot_nums = [r["num_slots"] for r in results]
p2_prrs = [r["p2_prr"] for r in results]
p1_prrs = [r["p1_prr"] for r in results]
rx_deafs = [r["rx_deafness"] for r in results]
p1_misses = [r["p1_miss"] for r in results]
collisions = [r["collisions"] for r in results]
cutoffs = [r["slot_cutoff"] for r in results]
p2_success = [r["p2_success"] for r in results]
p2_links = [r["p2_links"] for r in results]

plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['font.size'] = 11

# =========================================================================
# Plot 1: PRR Scaling Curve (P2 PRR vs Slot Count 3~25)
# =========================================================================
fig, ax1 = plt.subplots(figsize=(12, 6.5), dpi=300)

line1 = ax1.plot(slot_nums, p2_prrs, marker='s', markersize=8, linewidth=2.8, color='#1f77b4', label='Phase 2 Delivery PRR (%)')
line2 = ax1.plot(slot_nums, p1_prrs, marker='o', markersize=6, linewidth=1.8, color='#2ca02c', linestyle='--', label='Phase 1 Broadcast PRR (%) (Ceiling)')

# Annotate key data points cleanly (NO star, NO red highlight, uniform clean blue)
annot_slots = [3, 5, 8, 11, 14, 17, 20, 23, 25]
for s in annot_slots:
    if s in slot_nums:
        idx = slot_nums.index(s)
        ax1.annotate(f"{p2_prrs[idx]:.1f}%", (s, p2_prrs[idx]), textcoords="offset points", xytext=(0, 9),
                    ha='center', fontsize=9.5, fontweight='bold', color='#1f77b4')

ax1.set_title('Phase 2 Delivery PRR vs. Slot Count (3 ~ 25 Slots @ Fixed 720µs, 6 Channels)\n'
              '100 UAV Swarm, Bluetooth 5.4 LE 2M PHY, Phase 2 Capture DISABLED', fontsize=12.5, fontweight='bold', pad=14)
ax1.set_xlabel('Number of Phase 2 Slots (Slot Duration = 720 µs)', fontsize=11.5, fontweight='bold')
ax1.set_ylabel('Delivery PRR (%)', fontsize=11.5, fontweight='bold')
ax1.set_xticks(slot_nums)
ax1.set_xlim(2.4, 25.6)
ax1.set_ylim(20, 100)
ax1.grid(True, linestyle='--', alpha=0.5)

# Secondary top X-axis showing ONLY Phase 2 Duration (e.g. 2.16 ms, 5.76 ms) - NO cells
ax2 = ax1.twiny()
ax2.set_xlim(ax1.get_xlim())
tick_slots = [3, 5, 8, 11, 14, 17, 20, 23, 25]
ax2.set_xticks(tick_slots)
ax2.set_xticklabels([f"{s * slot_us / 1000.0:.2f} ms" for s in tick_slots], fontsize=10, fontweight='medium')
ax2.set_xlabel('Phase 2 Duration (ms)', fontsize=11, fontweight='bold', labelpad=8)

lines = line1 + line2
labels = [l.get_label() for l in lines]
ax1.legend(lines, labels, loc='lower right', fontsize=10.5, framealpha=0.95)

plt.tight_layout()
fig_path = os.path.join(PROJECT_DIR, "p2_slots_3_25_prr.png")
plt.savefig(fig_path)
plt.close()
print(f"✅ Saved PRR scaling curve to {fig_path}")

# =========================================================================
# Plot 2: Detailed Breakdown (Failure Evolution & Absolute Link Throughput)
# =========================================================================
fig, (ax_drop, ax_vol) = plt.subplots(1, 2, figsize=(16, 6), dpi=300)

# Panel A: Failure Cause Evolution
ax_drop.plot(slot_nums, rx_deafs, marker='^', markersize=7.5, linewidth=2.4, color='#e6550d', label='RX Deafness (Slot Conflict)')
ax_drop.plot(slot_nums, p1_misses, marker='d', markersize=6.5, linewidth=2.0, color='#756bb1', label='P1 Discovery Miss (Topology Miss)')
ax_drop.plot(slot_nums, collisions, marker='o', markersize=6.0, linewidth=1.8, color='#d62728', label='Co-channel Collisions')
ax_drop.plot(slot_nums, cutoffs, marker='x', markersize=7.0, linewidth=1.8, color='#3182bd', linestyle=':', label='Slot Boundary Cutoffs')

ax_drop.set_title('(a) Failure Mechanism Evolution Across Slot Counts', fontsize=12, fontweight='bold')
ax_drop.set_xlabel('Number of Phase 2 Slots', fontsize=11, fontweight='bold')
ax_drop.set_ylabel('Number of Dropped Link Packets', fontsize=11, fontweight='bold')
ax_drop.set_xticks(slot_nums)
ax_drop.set_xticklabels([str(s) for s in slot_nums], rotation=45, fontsize=9)
ax_drop.grid(True, linestyle='--', alpha=0.55)
ax_drop.legend(loc='upper right', fontsize=10, framealpha=0.95)

# Panel B: Absolute Link Delivery Capacity
ax_vol.bar(slot_nums, p2_success, width=0.65, color='#2ca02c', alpha=0.85, label='Successfully Delivered Packets')
fails = [r['p2_fails'] for r in results]
ax_vol.bar(slot_nums, fails, width=0.65, bottom=p2_success, color='#d62728', alpha=0.75, label='Dropped / Missed Packets')

ax_vol.set_title('(b) Phase 2 Absolute Communication Capacity', fontsize=12, fontweight='bold')
ax_vol.set_xlabel('Number of Phase 2 Slots', fontsize=11, fontweight='bold')
ax_vol.set_ylabel('Total Link Packet Volume', fontsize=11, fontweight='bold')
ax_vol.set_xticks(slot_nums)
ax_vol.set_xticklabels([str(s) for s in slot_nums], rotation=45, fontsize=9)
ax_vol.grid(True, linestyle='--', alpha=0.55, axis='y')
ax_vol.legend(loc='lower right', fontsize=10, framealpha=0.95)

plt.tight_layout()
breakdown_path = os.path.join(PROJECT_DIR, "p2_slots_3_25_breakdown.png")
plt.savefig(breakdown_path)
plt.close()
print(f"✅ Saved failure mechanism breakdown to {breakdown_path}")

# Auto Git Push
if "--no-push" not in sys.argv:
    print("\n🚀 Pushing results to GitHub main...")
    try:
        subprocess.run(
            "git add exp_p2_slots_3_25* p2_slots_3_25* && git commit -m 'data: upload Phase 2 slots 3-25 scaling sweep results and plots' && git push origin main",
            shell=True,
            cwd=PROJECT_DIR,
            check=False
        )
        print("✅ Git push completed!")
    except Exception as e:
        print(f"⚠️ Git push notice: {e}")

print("🎉 Slot count scaling benchmark script completed successfully!")
