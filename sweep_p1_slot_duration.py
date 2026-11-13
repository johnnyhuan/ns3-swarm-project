#!/usr/bin/env python3
"""
Phase 1 SSA Slot Duration Sweep Benchmark
Evaluates physical limits: How short can a slot be?
Sweeps p1SlotUs from 150us to 1000us.
"""

import subprocess
import os
import sys
import re
from datetime import datetime

print("=========================================================================")
print("🔬 PHASE 1 SSA SLOT DURATION SWEEP: MINIMUM SLOT LIMIT ANALYSIS 🔬")
print("=========================================================================")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
NS3_DIR = os.path.expanduser("~/ns-3-dev")
if not os.path.exists(NS3_DIR):
    NS3_DIR = PROJECT_DIR

# 1. Sync updated files to NS3_DIR
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

num_nodes = int(sys.argv[1]) if len(sys.argv) > 1 else 75
sim_time = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
p1_duration = float(sys.argv[3]) if len(sys.argv) > 3 else 10.0
space_size = float(sys.argv[4]) if len(sys.argv) > 4 else 200.0
space_z = float(sys.argv[5]) if len(sys.argv) > 5 else 80.0

# Slot durations to test in microseconds
# Dense high-resolution sweep between 70us and 105us to find the exact optimum / physical limit
slot_durations = [70.0, 75.0, 77.5, 80.0, 82.5, 85.0, 87.5, 90.0, 92.5, 95.0, 97.5, 100.0, 105.0]

print(f"• Swarm Scale         : {num_nodes} UAVs in {space_size:.0f}m x {space_size:.0f}m x {space_z:.0f}m")
print(f"• Phase 1 Window      : {p1_duration} ms")
print(f"• Simulation Duration : {sim_time} s per point")
print(f"• Slot Sweep Range    : {slot_durations} µs")
print("-------------------------------------------------------------------------\n")

def run_point(slot_us):
    # Clean old report files
    for fname in ["p1_ground_truth_report.txt", "p2_ground_truth_report.txt", "run.log"]:
        fpath = os.path.join(NS3_DIR, fname)
        if os.path.exists(fpath):
            try: os.remove(fpath)
            except Exception: pass

    cmd = [
        "./ns3", "run",
        f"scratch/lr-wpan-swarm --numNodes={num_nodes} --p1Duration={p1_duration} "
        f"--simTime={sim_time} --spaceSize={space_size} --spaceZ={space_z} "
        f"--enableP1Ssa=true --p1SlotUs={slot_us} --autoPush=false"
    ]
    proc = subprocess.run(cmd, cwd=NS3_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    out = proc.stdout

    p1_rpt = os.path.join(NS3_DIR, "p1_ground_truth_report.txt")
    p1_text = ""
    if os.path.exists(p1_rpt):
        with open(p1_rpt, "r", encoding="utf-8", errors="ignore") as f:
            p1_text = f.read()

    run_log = os.path.join(NS3_DIR, "run.log")
    log_text = ""
    if os.path.exists(run_log):
        with open(run_log, "r", encoding="utf-8", errors="ignore") as f:
            log_text = f.read()

    combined = p1_text + "\n" + out + "\n" + log_text

    if not p1_text or proc.returncode != 0:
        print(f"\n[NS3 DIAGNOSTIC for {slot_us:.1f}µs] ExitCode: {proc.returncode}")
        err_lines = [l for l in out.splitlines() if any(k in l.lower() for k in ["assert", "error", "fault", "abort", "terminate", "msg"])]
        if err_lines:
            print("  ==> " + "\n  ==> ".join(err_lines[-5:]))
        elif out:
            print("  ==> " + "\n  ==> ".join(out.splitlines()[-5:]))

    slots_avail = int((p1_duration * 1000.0 - 250.0) / slot_us) + 1
    density = num_nodes / max(1, slots_avail)

    data = {
        "slot_us": slot_us,
        "slots_avail": slots_avail,
        "density": density,
        "prr": 0.0,
        "delivered": 0,
        "fails": 0,
        "rx_deafness": 0,
        "preamble_coll": 0,
        "low_sinr": 0,
        "captures": 0,
        "p2_prr": 0.0,
        "mean_aoi": 0.0
    }

    m = re.search(r"Successfully Received \(Delivered\)\s*:\s*(\d+)\s*\(([\d\.]+)%\)", p1_text)
    if m:
        data["delivered"] = int(m.group(1))
        data["prr"] = float(m.group(2))

    m = re.search(r"Failed Link Receptions \(Dropped/Missed\)\s*:\s*(\d+)", p1_text)
    if m: data["fails"] = int(m.group(1))

    m = re.search(r"RX_DEAFNESS_BUSY_TX\s*:\s*(\d+)", p1_text)
    if m: data["rx_deafness"] = int(m.group(1))

    m = re.search(r"PREAMBLE_COLLISION_BUSY_RX\s*:\s*(\d+)", p1_text)
    if m: data["preamble_coll"] = int(m.group(1))

    m = re.search(r"PREAMBLE_LOW_SINR\s*:\s*(\d+)", p1_text)
    if m: data["low_sinr"] = int(m.group(1))

    m = re.search(r"Total Power Capture Events Triggered\s*:\s*(\d+)", p1_text)
    if m: data["captures"] = int(m.group(1))

    p2_rpt = os.path.join(NS3_DIR, "p2_ground_truth_report.txt")
    if os.path.exists(p2_rpt):
        with open(p2_rpt, "r", encoding="utf-8", errors="ignore") as f:
            p2_text = f.read()
            m2 = re.search(r"Successfully Received \(Delivered\)\s*:\s*(\d+)\s*\(([\d\.]+)%\)", p2_text)
            if m2: data["p2_prr"] = float(m2.group(2))

    m_aoi = re.search(r"Mean Beacon Packet AoI \(Top-K\)\s*:\s*([\d\.]+)\s*ms", combined)
    if m_aoi: data["mean_aoi"] = float(m_aoi.group(1))

    return data

results = []
for s_us in slot_durations:
    slots_cnt = int((p1_duration * 1000.0 - 250.0) / s_us) + 1
    print(f"▶️ Testing Slot Duration = {s_us:.1f} µs ({slots_cnt} slots, ~{num_nodes/slots_cnt:.2f} UAVs/slot) ...", end="", flush=True)
    res = run_point(s_us)
    results.append(res)
    print(f"  ==> PRR: {res['prr']:.1f}% | Deafness: {res['rx_deafness']} | Coll: {res['preamble_coll']} | Captures: {res['captures']}")

print("\n" + "=" * 105)
print("📊 SSA SLOT DURATION SWEEP: HIGH-RESOLUTION 75µs - 105µs BOUNDARY ANALYSIS")
print("=" * 105)
print(f"{'Slot (µs)':<10} | {'Slots':<6} | {'UAVs/Slot':<10} | {'P1 PRR':<10} | {'Deafness':<10} | {'Collision':<10} | {'Low SINR':<10} | {'Captures':<10} | {'Physical State / Phenomenon':<22}")
print("-" * 105)

for r in results:
    if r['slot_us'] < 75.0:
        phys_note = "⚡ Sub-75µs Boundary"
    elif r['slot_us'] <= 85.0:
        phys_note = "🚀 Optimal Micro-Slot Region"
    elif r['slot_us'] <= 100.0:
        phys_note = "🔥 Peak SSA Spatial Reuse"
    else:
        phys_note = "✅ Baseline Micro-Slot"
    
    print(f"{r['slot_us']:<10.1f} | {r['slots_avail']:<6} | {r['density']:<10.2f} | {r['prr']:<9.1f}% | {r['rx_deafness']:<10} | {r['preamble_coll']:<10} | {r['low_sinr']:<10} | {r['captures']:<10} | {phys_note:<22}")
print("=" * 105)

# Save text report
summary_path = os.path.join(PROJECT_DIR, "exp_slot_sweep_results.txt")
with open(summary_path, "w", encoding="utf-8") as f:
    f.write("# Phase 1 SSA Slot Duration Sweep Summary (High-Resolution 70µs - 105µs)\n")
    f.write(f"- Swarm Scale: {num_nodes} UAVs in {space_size}m x {space_size}m x {space_z}m\n")
    f.write(f"- Phase 1 Duration: {p1_duration} ms\n")
    f.write(f"- Packet Airtime Limit: 244 µs (192µs Header + 52µs Payload @ 2 Mbps)\n\n")
    f.write("| Slot (µs) | Slots Available | UAVs/Slot | P1 PRR (%) | RX Deafness | Preamble Coll | Low SINR | Captures | Physical Phenomenon |\n")
    f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
    for r in results:
        if r['slot_us'] < 75.0: note = "Sub-75µs Boundary"
        elif r['slot_us'] <= 85.0: note = "Optimal Micro-Slot Region"
        elif r['slot_us'] <= 100.0: note = "Peak SSA Spatial Reuse"
        else: note = "Baseline Micro-Slot"
        f.write(f"| {r['slot_us']:.1f} | {r['slots_avail']} | {r['density']:.2f} | {r['prr']:.1f}% | {r['rx_deafness']} | {r['preamble_coll']} | {r['low_sinr']} | {r['captures']} | {note} |\n")

print(f"\n📄 Results saved to: {summary_path}")

# Optional Plot Generation
try:
    import matplotlib.pyplot as plt
    x_slots = [r['slot_us'] for r in results]
    y_prr = [r['prr'] for r in results]
    y_slots = [r['slots_avail'] for r in results]

    fig, ax1 = plt.subplots(figsize=(10, 6))

    color = '#2980b9'
    ax1.set_xlabel('Slot Duration (µs)', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Phase 1 Delivery PRR (%)', color=color, fontsize=12, fontweight='bold')
    line1 = ax1.plot(x_slots, y_prr, color=color, marker='o', linewidth=2.5, markersize=8, label='Phase 1 PRR (%)')
    ax1.tick_params(axis='y', labelcolor=color)
    ax1.grid(True, linestyle='--', alpha=0.5)

    # Highlight 244us physical airtime line
    ax1.axvline(x=244.0, color='#e74c3c', linestyle=':', linewidth=2, label='Physical Packet Airtime Limit (244 µs)')

    ax2 = ax1.twinx()
    color = '#27ae60'
    ax2.set_ylabel('Available Slots (in 10ms window)', color=color, fontsize=12, fontweight='bold')
    line2 = ax2.plot(x_slots, y_slots, color=color, marker='s', linestyle='--', linewidth=2, markersize=7, label='Available Slots')
    ax2.tick_params(axis='y', labelcolor=color)

    lines = line1 + line2 + [plt.Line2D([0], [0], color='#e74c3c', linestyle=':', linewidth=2)]
    labels = [l.get_label() for l in lines]
    labels[-1] = 'Physical Airtime Limit (244 µs)'
    ax1.legend(lines, labels, loc='center right', frameon=True)

    plt.title(f'SSA: Slot Duration Sweep & Minimum Slot Physical Bound\n(75 UAVs, 10ms Window, 2 Mbps PHY)', fontsize=13, fontweight='bold')
    plot_path = os.path.join(PROJECT_DIR, "exp_slot_sweep_prr.png")
    plt.savefig(plot_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"📈 Plot saved to: {plot_path}")
except Exception as e:
    print(f"Note: matplotlib plot skipped ({e})")
