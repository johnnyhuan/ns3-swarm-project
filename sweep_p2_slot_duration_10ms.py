#!/usr/bin/env python3
"""
Phase 2 (10ms Window) Slot Duration Optimization Benchmark:
Evaluates Phase 2 Data Delivery PRR and Detailed Physical Failure Root Causes across different slot durations:
- Phase 1: Fixed 10.0 ms CSMA-CA Broadcast (with +6.0 dB Capture ENABLED)
- Phase 2: Fixed 10.0 ms Window (Slot Durations: 400µs, 500µs, 625µs, 750µs, 800µs, 1000µs, 1250µs, 1500µs, 2000µs, 2500µs)
- Phase 2 Capture: DISABLED (Pure physical collision, no capture rescues)
- Swarm Scale: 100 UAVs in 200m x 200m x 80m 3D airspace
- Physical Layer: Bluetooth 5.4 LE 2M PHY (2 Mbps, 244µs transmission air time)
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
print("⏱️  PHASE 2 (10ms WINDOW) SLOT DURATION OPTIMIZATION SWEEP (100 UAVs, BLE 2M PHY) ⏱️")
print("==========================================================================================")

num_nodes = int(sys.argv[1]) if len(sys.argv) > 1 else 100
sim_time = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
num_channels = int(sys.argv[3]) if len(sys.argv) > 3 else 6
p1_duration = 10.0
p2_duration = 10.0
space_size = 200.0
space_z = 80.0
capture_thresh_db = 6.0

# Slot durations to test (microseconds)
# Covering: 400us (25 slots), 500us (20 slots), 625us (16 slots - BLE standard), 
# 750us (13 slots), 800us (12 slots), 1000us (10 slots), 1250us (8 slots), 
# 1500us (6 slots), 2000us (5 slots), 2500us (4 slots)
slot_durations_us = [400.0, 500.0, 625.0, 750.0, 800.0, 1000.0, 1250.0, 1500.0, 2000.0, 2500.0]

print(f"• UAV Swarm Scale        : {num_nodes} UAVs in {space_size:.0f}m x {space_size:.0f}m x {space_z:.0f}m")
print(f"• Phase 1 Broadcast Win  : {p1_duration:.1f} ms (CSMA-CA, Capture ENABLED: +{capture_thresh_db:.1f} dB)")
print(f"• Phase 2 Data Window    : {p2_duration:.1f} ms ({num_channels} data channels)")
print(f"• Phase 2 Capture Event  : DISABLED (Pure Collision, No Capture Rescues)")
print(f"• Slot Sweep Range (µs)  : {slot_durations_us} µs ({len(slot_durations_us)} points)")
print(f"• Simulation Time        : {sim_time:.1f} s per evaluation point")
print("------------------------------------------------------------------------------------------\n")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
NS3_DIR = os.path.expanduser("~/ns-3-dev")
if not os.path.exists(NS3_DIR):
    NS3_DIR = PROJECT_DIR

# Sync updated files to NS3_DIR
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

def run_single_slot(slot_us):
    # Clean previous reports
    for fname in ["p1_ground_truth_report.txt", "p2_ground_truth_report.txt", "run.log"]:
        fpath = os.path.join(NS3_DIR, fname)
        if os.path.exists(fpath):
            try: os.remove(fpath)
            except Exception: pass

    cmd = [
        "./ns3", "run",
        f"scratch/lr-wpan-swarm --numNodes={num_nodes} --p1Duration={p1_duration} "
        f"--p2Duration={p2_duration} --dataSlotUs={slot_us} --numChannels={num_channels} "
        f"--simTime={sim_time} --spaceSize={space_size} --spaceZ={space_z} "
        f"--p1TxPower=0 --p2TxPower=-2 --p1CcaThresholdDbm=-96.58 --nodeSpeed=10.0 "
        f"--enableP1Ssa=false --enablePhyCapture=true --enableP2Capture=false "
        f"--p1CaptureThresholdDb={capture_thresh_db} --phyCaptureMarginDb={capture_thresh_db} --autoPush=false"
    ]

    try:
        proc = subprocess.run(cmd, cwd=NS3_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=300)
        stdout_output = proc.stdout
        if proc.returncode != 0:
            print(f"\n❌ [NS3 ERROR] Command returned exit code {proc.returncode} at slot = {slot_us} µs:")
            lines = stdout_output.strip().split("\n")
            print("\n".join(lines[-25:]))
    except subprocess.TimeoutExpired:
        print(f"TIMEOUT at slot = {slot_us} µs!")
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
    return parse_p2_metrics(p1_text, p2_text, combined_out, slot_us)

def parse_p2_metrics(p1_text, p2_text, stdout_text, slot_us):
    slots_count = max(1, int(p2_duration * 1000.0 / slot_us))
    total_cells = slots_count * num_channels

    data = {
        "slot_us": slot_us,
        "num_slots": slots_count,
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

for s_us in slot_durations_us:
    slots_cnt = max(1, int(p2_duration * 1000.0 / s_us))
    cells = slots_cnt * num_channels
    print(f"▶️ Testing Slot Duration = {s_us:>6.1f} µs ({slots_cnt:>2} slots, {cells:>3} cells) ... ", end="", flush=True)
    res = run_single_slot(s_us)
    if res is not None:
        print(f"P2 PRR: {res['p2_prr']:>5.1f}% ({res['p2_success']:,}) | Cutoff: {res['slot_cutoff']:>4} | RX Deaf: {res['rx_deafness']:>4} | Coll: {res['collisions']:>3}")
        results.append(res)
    else:
        print("ERROR / TIMEOUT")

# Output Summary Table
print("\n" + "=" * 125)
print("📊 PHASE 2 (10ms WINDOW) SLOT DURATION OPTIMIZATION SUMMARY (100 UAVs, BLE 2M PHY, P2 Capture OFF) 📊")
print("=" * 125)
print(f"| {'Slot Duration':^14} | {'Slots':^7} | {'Cells':^7} | {'P1 PRR':^9} | {'P2 Data PRR':^15} | {'P1 Miss':^10} | {'RX Deafness':^13} | {'Collisions':^12} |")
print("|" + "-" * 16 + "|" + "-" * 9 + "|" + "-" * 9 + "|" + "-" * 11 + "|" + "-" * 17 + "|" + "-" * 12 + "|" + "-" * 15 + "|" + "-" * 14 + "|")

best_idx = 0
best_prr = 0.0

for i, r in enumerate(results):
    if r["p2_prr"] > best_prr:
        best_prr = r["p2_prr"]
        best_idx = i

    dur_str = f"{r['slot_us']:.0f} µs"
    if r['slot_us'] == 625.0: dur_str += " (BLE)"
    slots_str = f"{r['num_slots']}"
    cells_str = f"{r['total_cells']}"
    p1_str = f"{r['p1_prr']:.1f}%"
    p2_str = f"{r['p2_prr']:.1f}% ({r['p2_success']:,})"
    p1_miss_str = f"{r['p1_miss']:,}"
    rx_deaf_str = f"{r['rx_deafness']:,}"
    coll_str = f"{r['collisions']:,}"
    print(f"| {dur_str:^14} | {slots_str:^7} | {cells_str:^7} | {p1_str:^9} | {p2_str:^15} | {p1_miss_str:^10} | {rx_deaf_str:^13} | {coll_str:^12} |")

print("=" * 125)
print(f"🏆 Optimal Operating Point: Slot Duration = {results[best_idx]['slot_us']:.0f} µs ({results[best_idx]['num_slots']} slots, {results[best_idx]['total_cells']} cells) with P2 PRR = {best_prr:.1f}%\n")

# Save CSV and TXT reports
csv_path = os.path.join(PROJECT_DIR, "exp_p2_slot_sweep_results.csv")
txt_path = os.path.join(PROJECT_DIR, "exp_p2_slot_sweep_report.txt")

with open(csv_path, "w", encoding="utf-8") as f:
    f.write("Slot_Duration_us,Num_Slots,Total_Cells,P1_PRR,P2_Links,P2_Success,P2_PRR,P1_Miss,TX_Deafness,RX_Deafness,Channel_Mismatch,Collisions,Low_SINR,Payload_Drop,Slot_Cutoff,P2_Captures\n")
    for r in results:
        f.write(f"{r['slot_us']:.1f},{r['num_slots']},{r['total_cells']},{r['p1_prr']:.2f},{r['p2_links']},{r['p2_success']},{r['p2_prr']:.2f},{r['p1_miss']},{r['tx_deafness']},{r['rx_deafness']},{r['ch_mismatch']},{r['collisions']},{r['low_sinr']},{r['payload_drop']},{r.get('slot_cutoff', 0)},{r['p2_captures']}\n")

with open(txt_path, "w", encoding="utf-8") as f:
    f.write(f"# Phase 2 (10ms Window) Slot Duration Optimization Benchmark\n")
    f.write(f"- Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write(f"- Swarm Scale: {num_nodes} UAVs in 200m x 200m x 80m\n")
    f.write(f"- PHY Standard: Bluetooth 5.4 LE 2M PHY (2 Mbps, 244 µs air time)\n")
    f.write(f"- Phase 1: Fixed 10.0 ms CSMA-CA with Capture (+6.0 dB)\n")
    f.write(f"- Phase 2: Fixed 10.0 ms Data Phase, 6 Channels, Capture DISABLED\n\n")
    f.write(f"| Slot Duration | Slots in 10ms | Total Cells (6 Ch) | P1 PRR | P2 Data PRR | P1 Discovery Miss | RX Deafness Conflict | Preamble Collisions |\n")
    f.write(f"| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
    for r in results:
        dur_note = f"{r['slot_us']:.0f} µs" + (" (BLE Baseband Slot)" if r['slot_us'] == 625.0 else "")
        f.write(f"| {dur_note} | {r['num_slots']} | {r['total_cells']} | {r['p1_prr']:.1f}% | {r['p2_prr']:.1f}% ({r['p2_success']}) | {r['p1_miss']} | {r['rx_deafness']} | {r['collisions']} |\n")
    f.write(f"\n- Optimal Slot: {results[best_idx]['slot_us']:.0f} µs ({results[best_idx]['num_slots']} slots, {results[best_idx]['total_cells']} cells) achieving {best_prr:.1f}% P2 PRR\n")

print(f"✅ Saved results to:\n  - {csv_path}\n  - {txt_path}")

# ==============================================================================
# Plot 1: PRR vs Slot Duration (Clean Academic Curve)
# ==============================================================================
slot_vals = [r["slot_us"] for r in results]
p2_prrs = [r["p2_prr"] for r in results]
cells_list = [r["total_cells"] for r in results]

plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['font.size'] = 11

fig, ax = plt.subplots(figsize=(10.5, 6), dpi=300)
ax.plot(slot_vals, p2_prrs, marker='s', markersize=8.5, linewidth=2.5, color='#1f77b4', label='Phase 2 Data PRR (%) [Capture OFF]')

for i, s in enumerate(slot_vals):
    lbl = f"{p2_prrs[i]:.1f}%\n({results[i]['num_slots']} slots)"
    offset_y = 12 if i % 2 == 0 else -22
    color_txt = '#d62728' if i == best_idx else '#1f77b4'
    ax.annotate(lbl, (s, p2_prrs[i]), textcoords="offset points", xytext=(0, offset_y),
                ha='center', fontsize=9.5, fontweight='bold', color=color_txt)

# Highlight BLE 625 µs slot
if 625.0 in slot_vals:
    idx_625 = slot_vals.index(625.0)
    ax.scatter([625.0], [p2_prrs[idx_625]], color='#e6550d', s=160, zorder=5, marker='*', label='Bluetooth Baseband Slot (625 µs)')

ax.set_title('Phase 2 Data Delivery Ratio vs Slot Duration\n(10ms Window, 6 Channels, 100 UAVs, BLE 5.4 2M PHY, Capture OFF)', fontsize=13, fontweight='bold', pad=14)
ax.set_xlabel('Phase 2 Slot Duration (µs)', fontsize=11, fontweight='bold')
ax.set_ylabel('Top-5 Neighbor Data Delivery PRR (%)', fontsize=11, fontweight='bold')
ax.set_xticks(slot_vals)
ax.set_xticklabels([f"{int(s)}" for s in slot_vals], rotation=25)
ax.set_ylim(min(p2_prrs) - 6, max(p2_prrs) + 6)
ax.grid(True, linestyle='--', alpha=0.55)
ax.legend(loc='lower left', fontsize=11, framealpha=0.95)

plt.tight_layout()
fig1_path = os.path.join(PROJECT_DIR, "p2_slot_sweep_prr.png")
plt.savefig(fig1_path)
plt.close()
print(f"✅ Saved PRR curve to {fig1_path}")

# ==============================================================================
# Plot 2: Failure Category Breakdown (Dual Panel)
# ==============================================================================
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 10), dpi=300, sharex=True)

# Panel a: PRR and Total Cells
ax1.plot(slot_vals, p2_prrs, marker='s', markersize=7.5, linewidth=2.2, color='#1f77b4', label='Phase 2 Delivery PRR (%)')
ax1.set_ylabel('Delivery PRR (%)', fontsize=11, fontweight='bold', color='#1f77b4')
ax1.tick_params(axis='y', labelcolor='#1f77b4')
ax1.set_ylim(min(p2_prrs) - 5, max(p2_prrs) + 5)
ax1.grid(True, linestyle='--', alpha=0.55)
ax1.set_title('(a) Phase 2 Delivery PRR & Available Resource Cells', fontsize=12, fontweight='bold')

ax1_twin = ax1.twinx()
ax1_twin.plot(slot_vals, cells_list, marker='o', markersize=6.5, linewidth=2.0, color='#2ca02c', linestyle=':', label='Total Resource Cells (Slots x 6 Ch)')
ax1_twin.set_ylabel('Available Cells (Slots x 6 Channels)', fontsize=11, fontweight='bold', color='#2ca02c')
ax1_twin.tick_params(axis='y', labelcolor='#2ca02c')

lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax1_twin.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labels1 + labels2, loc='center right', fontsize=10.5, framealpha=0.95)

# Panel b: Drop Causes
p1_miss_list = [r["p1_miss"] for r in results]
rx_deaf_list = [r["rx_deafness"] for r in results]
coll_list = [r["collisions"] for r in results]
ch_mismatch_list = [r["ch_mismatch"] for r in results]

ax2.plot(slot_vals, rx_deaf_list, marker='^', markersize=7, linewidth=2.0, color='#e6550d', label='RX Deafness (Slot Conflict)')
ax2.plot(slot_vals, coll_list, marker='x', markersize=7.5, linewidth=2.0, color='#d62728', label='Preamble Collisions (Same Slot & Ch)')
ax2.plot(slot_vals, ch_mismatch_list, marker='d', markersize=6.5, linewidth=1.8, color='#756bb1', label='Channel Mismatch')
ax2.plot(slot_vals, p1_miss_list, marker='o', markersize=6.0, linewidth=1.8, color='#8c564b', linestyle='--', label='P1 Discovery Miss (Constant ~2.7k)')

ax2.set_title('(b) Physical Failure Root Cause Decomposition (No Capture)', fontsize=12, fontweight='bold')
ax2.set_xlabel('Phase 2 Slot Duration (µs)', fontsize=11, fontweight='bold')
ax2.set_ylabel('Dropped Link Counts', fontsize=11, fontweight='bold')
ax2.set_xticks(slot_vals)
ax2.set_xticklabels([f"{int(s)}" for s in slot_vals], rotation=25)
ax2.grid(True, linestyle='--', alpha=0.55)
ax2.legend(loc='upper right', fontsize=10, framealpha=0.95)

plt.tight_layout()
fig2_path = os.path.join(PROJECT_DIR, "p2_slot_sweep_breakdown.png")
plt.savefig(fig2_path)
plt.close()
print(f"✅ Saved breakdown dashboard to {fig2_path}")

if "--no-push" not in sys.argv:
    print("\n🚀 Pushing results and plots to GitHub main...")
    try:
        subprocess.run(
            "git add exp_p2_slot_sweep* p2_slot_sweep* && git commit -m 'data: upload Phase 2 10ms slot duration sweep results and plots' && git push origin main",
            shell=True,
            cwd=PROJECT_DIR,
            check=False
        )
        print("✅ Git push completed!")
    except Exception as e:
        print(f"⚠️ Git push notice: {e}")

print("🎉 Phase 2 slot sweep script completed successfully!")
