#!/usr/bin/env python3
"""
UAV Swarm Phase 1 Cycle Duration Sweep Benchmark: 3GPP Sidelink S-SPS (100µs Slot) vs CSMA-CA
Fixed Swarm Scale: 150 UAVs
Phase 1 Window Duration Sweep: 3.0 ms to 15.0 ms (Every 1 ms integer step)

Evaluates:
- Phase 1 Mini-Beacon Delivery PRR (%)
- Gain Δ PRR (%) (Sidelink S-SPS vs CSMA-CA)
- Detailed Failure Breakdown (RX Deafness, Preamble Collisions, CSMA Aborts, Low SINR)
- Sidelink Power Capture Rescues
- Phase 2 Data Delivery PRR (%)
- Mean Beacon AoI (Age of Information, ms) & Latency Trade-off
"""

import subprocess
import os
import sys
import re
import csv
from datetime import datetime

print("==========================================================================================")
print("⏱️  PHASE 1 DURATION SWEEP BENCHMARK: 3GPP SIDELINK S-SPS (100µs) vs CSMA-CA  ⏱️")
print("==========================================================================================")

# Command-line configurable parameters
num_nodes = int(sys.argv[1]) if len(sys.argv) > 1 else 150
p1_slot_us = float(sys.argv[2]) if len(sys.argv) > 2 else 100.0
sim_time = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
space_size = float(sys.argv[4]) if len(sys.argv) > 4 else 200.0
space_z = float(sys.argv[5]) if len(sys.argv) > 5 else 80.0

# Phase 1 Durations: 3ms to 15ms every ms, sequential without jumping
durations = [3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0]

print(f"• Fixed Swarm Scale      : {num_nodes} UAVs")
print(f"• Phase 1 Duration Sweep : {durations} ms (13 evaluation points, 1ms step)")
print(f"• Sidelink Slot Width    : {p1_slot_us} µs")
print(f"• Airspace Dimensions    : {space_size:.0f}m x {space_size:.0f}m x {space_z:.0f}m")
print(f"• Simulation Time        : {sim_time} s per run")
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

def run_simulation(dur_ms, enable_sidelink):
    # Clean old report files before run
    for fname in ["p1_ground_truth_report.txt", "p2_ground_truth_report.txt", "run.log", "metrics.txt"]:
        fpath = os.path.join(NS3_DIR, fname)
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
            except Exception:
                pass
    
    sidelink_flag = f"--enableP1Sidelink=true --p1SlotUs={p1_slot_us}" if enable_sidelink else "--enableP1Sidelink=false"
    cmd = [
        "./ns3", "run",
        f"scratch/lr-wpan-swarm --numNodes={num_nodes} --p1Duration={dur_ms} "
        f"--simTime={sim_time} --spaceSize={space_size} --spaceZ={space_z} "
        f"--p1TxPower=0 --p2TxPower=-2 --p1CcaThresholdDbm=-96.58 --nodeSpeed=10.0 "
        f"{sidelink_flag} --autoPush=false"
    ]
    
    try:
        proc = subprocess.run(cmd, cwd=NS3_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=300)
        out = proc.stdout
    except subprocess.TimeoutExpired:
        print(f"\n⚠️ Command timed out after 300s!")
        return None

    # Read generated reports
    p1_rpt = os.path.join(NS3_DIR, "p1_ground_truth_report.txt")
    p1_text = ""
    if os.path.exists(p1_rpt):
        with open(p1_rpt, "r", encoding="utf-8", errors="ignore") as f:
            p1_text = f.read()

    p2_rpt = os.path.join(NS3_DIR, "p2_ground_truth_report.txt")
    p2_text = ""
    if os.path.exists(p2_rpt):
        with open(p2_rpt, "r", encoding="utf-8", errors="ignore") as f:
            p2_text = f.read()

    metrics_rpt = os.path.join(NS3_DIR, "metrics.txt")
    metrics_text = ""
    if os.path.exists(metrics_rpt):
        with open(metrics_rpt, "r", encoding="utf-8", errors="ignore") as f:
            metrics_text = f.read()

    combined_stdout = out + "\n" + metrics_text
    return parse_metrics(p1_text, p2_text, combined_stdout, dur_ms)

def parse_metrics(p1_text, p2_text, stdout_text, dur_ms):
    cycle_ms = dur_ms + 1.0 + (10 * 2.5) # Phase 1 + 1ms gap + 10 data slots * 2.5ms = dur_ms + 26ms
    data = {
        "dur_ms": dur_ms,
        "cycle_ms": cycle_ms,
        "p1_links": 0,
        "p1_success": 0,
        "p1_prr": 0.0,
        "p1_fails": 0,
        "csma_abort": 0,
        "rx_deafness": 0,
        "preamble_coll": 0,
        "low_sinr": 0,
        "captures": 0,
        "p2_prr": 0.0,
        "mean_aoi": 0.0,
        "avg_iat": 0.0
    }
    
    src_p1 = p1_text if p1_text else stdout_text
    
    m = re.search(r"Total Expected P1 Neighbor Links.*:\s*(\d+)", src_p1)
    if m: data["p1_links"] = int(m.group(1))
    
    m = re.search(r"Successfully Received \(Delivered\)\s*:\s*(\d+)\s*\(([\d\.]+)%\)", src_p1)
    if m:
        data["p1_success"] = int(m.group(1))
        data["p1_prr"] = float(m.group(2))
        
    m = re.search(r"Failed Link Receptions \(Dropped/Missed\)\s*:\s*(\d+)", src_p1)
    if m: data["p1_fails"] = int(m.group(1))
    
    m = re.search(r"SENDER_CSMA_ABORT\s*:\s*(\d+)", src_p1)
    if m: data["csma_abort"] = int(m.group(1))

    m = re.search(r"RX_DEAFNESS_BUSY_TX\s*:\s*(\d+)", src_p1)
    if m: data["rx_deafness"] = int(m.group(1))

    m = re.search(r"PREAMBLE_COLLISION_BUSY_RX\s*:\s*(\d+)", src_p1)
    if m: data["preamble_coll"] = int(m.group(1))

    m = re.search(r"PREAMBLE_LOW_SINR\s*:\s*(\d+)", src_p1)
    if m: data["low_sinr"] = int(m.group(1))

    m = re.search(r"Total Power Capture Events Triggered\s*:\s*(\d+)", src_p1)
    if m: data["captures"] = int(m.group(1))

    if p2_text:
        m2 = re.search(r"Successfully Received \(Delivered\)\s*:\s*(\d+)\s*\(([\d\.]+)%\)", p2_text)
        if m2: data["p2_prr"] = float(m2.group(2))

    m_aoi = re.search(r"Mean Beacon Packet AoI \(Top-K\)\s*:\s*([\d\.]+)\s*ms", stdout_text)
    if m_aoi: data["mean_aoi"] = float(m_aoi.group(1))

    m_iat = re.search(r"Avg Discovery Msg IAT \(Top-K\)\s*:\s*([\d\.]+)\s*ms", stdout_text)
    if m_iat: data["avg_iat"] = float(m_iat.group(1))

    return data

results = []

for dur in durations:
    sps_slots = int((dur * 1000.0 - 250.0) / p1_slot_us) + 1
    cycle_time = dur + 26.0
    print(f"▶️ Testing Phase 1 Duration: {dur:.1f} ms (Cycle: {cycle_time:.1f} ms, S-SPS Slots: {sps_slots} in {dur:.0f}ms)...")
    
    # 1. Run Baseline CSMA-CA
    print(f"   [1/2] Running CSMA-CA Baseline ... ", end="", flush=True)
    csma_res = run_simulation(dur, enable_sidelink=False)
    if csma_res is not None:
        print(f"PRR: {csma_res['p1_prr']:.1f}% | Deafness: {csma_res['rx_deafness']} | Coll: {csma_res['preamble_coll']} | Aborts: {csma_res['csma_abort']} | AoI: {csma_res['mean_aoi']:.1f}ms")
    else:
        print(f"TIMEOUT / ERROR")

    # 2. Run Sidelink S-SPS (100 µs Micro-Slot)
    print(f"   [2/2] Running Sidelink S-SPS (100µs) ... ", end="", flush=True)
    sps_res = run_simulation(dur, enable_sidelink=True)
    if sps_res is not None:
        print(f"PRR: {sps_res['p1_prr']:.1f}% | Deafness: {sps_res['rx_deafness']} | Coll: {sps_res['preamble_coll']} | Captures: {sps_res['captures']} | AoI: {sps_res['mean_aoi']:.1f}ms")
    else:
        print("TIMEOUT / ERROR")

    if csma_res is not None and sps_res is not None:
        prr_diff = sps_res['p1_prr'] - csma_res['p1_prr']
        print(f"   ==> Δ PRR: {prr_diff:+.1f}% ({'⭐ Sidelink Wins' if prr_diff >= 0 else '⚠️ CSMA Wins'})\n")
    else:
        prr_diff = None
        print(f"   ==> Δ PRR: N/A\n")

    results.append({
        "dur": dur,
        "cycle": cycle_time,
        "sps_slots": sps_slots,
        "csma": csma_res,
        "sps": sps_res,
        "diff": prr_diff
    })

# Print Full Comparative Table
print("\n" + "=" * 125)
print(f"📊 UAV SWARM PHASE 1 DURATION SWEEP: SIDELINK S-SPS (100µs) vs CSMA-CA (150 UAVs, 3ms - 15ms)")
print("=" * 125)
print(f"{'P1 Dur':<8} | {'Cycle':<8} | {'Slots':<6} | {'CSMA PRR':<10} | {'S-SPS PRR':<10} | {'Δ Gain':<9} | {'CSMA Coll':<10} | {'SPS Coll':<10} | {'CSMA Abort':<11} | {'SPS Capt':<9} | {'CSMA AoI':<9} | {'SPS AoI':<9} | {'Advantage'}")
print("-" * 125)

for r in results:
    sps_p1 = f"{r['sps']['p1_prr']:.1f}%" if r['sps'] else "ERR"
    sps_coll = str(r['sps']['preamble_coll']) if r['sps'] else "-"
    sps_capt = str(r['sps']['captures']) if r['sps'] else "-"
    sps_aoi = f"{r['sps']['mean_aoi']:.1f}ms" if r['sps'] else "-"

    if r['csma'] is not None:
        csma_p1 = f"{r['csma']['p1_prr']:.1f}%"
        csma_coll = str(r['csma']['preamble_coll'])
        csma_abort = str(r['csma']['csma_abort'])
        csma_aoi = f"{r['csma']['mean_aoi']:.1f}ms"
        diff_str = f"{r['diff']:+.1f}%" if r['diff'] is not None else "N/A"
        adv = "🚀 Sidelink Dominant" if (r['diff'] is not None and r['diff'] > 3.0) else ("🤝 Comparable" if (r['diff'] is not None and abs(r['diff']) <= 3.0) else "CSMA Ahead")
    else:
        csma_p1 = "N/A"
        csma_coll = "N/A"
        csma_abort = "N/A"
        csma_aoi = "N/A"
        diff_str = "N/A"
        adv = "CSMA Timeout / Error"

    print(f"{r['dur']:<4.0f} ms  | {r['cycle']:<5.1f} ms | {r['sps_slots']:<6} | {csma_p1:<10} | {sps_p1:<10} | {diff_str:<9} | {csma_coll:<10} | {sps_coll:<10} | {csma_abort:<11} | {sps_capt:<9} | {csma_aoi:<9} | {sps_aoi:<9} | {adv}")

print("=" * 125)

# Save Text Summary Report
summary_path = os.path.join(PROJECT_DIR, "exp_p1_duration_comparison_results.txt")
with open(summary_path, "w", encoding="utf-8") as f:
    f.write(f"# UAV Swarm Phase 1 Cycle Duration Benchmark: Sidelink S-SPS vs CSMA-CA\n")
    f.write(f"- Swarm Scale         : {num_nodes} UAVs\n")
    f.write(f"- Phase 1 Range       : 3.0 ms to 15.0 ms (step 1.0 ms, 13 points)\n")
    f.write(f"- Airspace Dimensions : {space_size:.0f}m x {space_size:.0f}m x {space_z:.0f}m\n")
    f.write(f"- Sidelink Slot Width : {p1_slot_us} µs\n")
    f.write(f"- Simulation Duration : {sim_time} s per run\n\n")
    f.write(f"| P1 Duration (ms) | Cycle (ms) | S-SPS Slots | CSMA PRR (%) | Sidelink S-SPS PRR (%) | Δ Gain (%) | CSMA Collisions | SPS Collisions | CSMA Aborts | SPS Captures | CSMA AoI (ms) | SPS AoI (ms) | Evaluation |\n")
    f.write(f"| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
    for r in results:
        sps_p1 = f"{r['sps']['p1_prr']:.1f}%" if r['sps'] else "ERR"
        sps_coll = r['sps']['preamble_coll'] if r['sps'] else "-"
        sps_capt = r['sps']['captures'] if r['sps'] else "-"
        sps_aoi = f"{r['sps']['mean_aoi']:.1f}ms" if r['sps'] else "-"
        if r['csma'] is not None:
            csma_p1 = f"{r['csma']['p1_prr']:.1f}%"
            csma_coll = r['csma']['preamble_coll']
            csma_abort = r['csma']['csma_abort']
            csma_aoi = f"{r['csma']['mean_aoi']:.1f}ms"
            diff_str = f"{r['diff']:+.1f}%" if r['diff'] is not None else "N/A"
            adv = "Sidelink Dominant" if (r['diff'] is not None and r['diff'] > 3.0) else ("Comparable" if (r['diff'] is not None and abs(r['diff']) <= 3.0) else "CSMA Ahead")
            f.write(f"| {r['dur']:.0f} ms | {r['cycle']:.1f} ms | {r['sps_slots']} | {csma_p1} | {sps_p1} | {diff_str} | {csma_coll} | {sps_coll} | {csma_abort} | {sps_capt} | {csma_aoi} | {sps_aoi} | {adv} |\n")
        else:
            f.write(f"| {r['dur']:.0f} ms | {r['cycle']:.1f} ms | {r['sps_slots']} | N/A | {sps_p1} | N/A | N/A | {sps_coll} | N/A | {sps_capt} | N/A | {sps_aoi} | CSMA Failed |\n")

print(f"\n📄 Summary table saved to: {summary_path}")

# Save CSV for Raw Analysis
csv_path = os.path.join(PROJECT_DIR, "exp_p1_duration_comparison_results.csv")
with open(csv_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow([
        "p1_dur_ms", "cycle_ms", "sps_slots",
        "csma_prr", "sps_prr", "delta_gain",
        "csma_deafness", "sps_deafness",
        "csma_collisions", "sps_collisions",
        "csma_aborts", "sps_captures",
        "csma_p2_prr", "sps_p2_prr",
        "csma_aoi_ms", "sps_aoi_ms"
    ])
    for r in results:
        writer.writerow([
            r['dur'], r['cycle'], r['sps_slots'],
            r['csma']['p1_prr'] if r['csma'] else "",
            r['sps']['p1_prr'] if r['sps'] else "",
            r['diff'] if r['diff'] is not None else "",
            r['csma']['rx_deafness'] if r['csma'] else "",
            r['sps']['rx_deafness'] if r['sps'] else "",
            r['csma']['preamble_coll'] if r['csma'] else "",
            r['sps']['preamble_coll'] if r['sps'] else "",
            r['csma']['csma_abort'] if r['csma'] else "",
            r['sps']['captures'] if r['sps'] else "",
            r['csma']['p2_prr'] if r['csma'] else "",
            r['sps']['p2_prr'] if r['sps'] else "",
            r['csma']['mean_aoi'] if r['csma'] else "",
            r['sps']['mean_aoi'] if r['sps'] else ""
        ])

print(f"📊 Raw CSV saved to: {csv_path}")

# Generate Plots
try:
    import matplotlib.pyplot as plt
    x_dur = [r['dur'] for r in results]
    y_sps_prr = [r['sps']['p1_prr'] for r in results if r['sps'] is not None]
    x_csma_dur = [r['dur'] for r in results if r['csma'] is not None]
    y_csma_prr = [r['csma']['p1_prr'] for r in results if r['csma'] is not None]

    # Graph 1: PRR vs Phase 1 Duration
    plt.figure(figsize=(10, 6))
    plt.plot(x_dur, y_sps_prr, marker='o', linewidth=2.5, markersize=8, color='#2980b9', label='3GPP Sidelink S-SPS (100 µs Micro-Slot)')
    plt.plot(x_csma_dur, y_csma_prr, marker='s', linewidth=2.5, markersize=8, color='#e67e22', linestyle='--', label='Continuous Random Delay + CSMA-CA')
    
    plt.title(f'Phase 1 Mini-Beacon PRR vs Broadcast Window Duration\n({num_nodes} UAVs, Airspace: {space_size:.0f}m x {space_size:.0f}m x {space_z:.0f}m)', fontsize=13, fontweight='bold')
    plt.xlabel('Phase 1 Broadcast Window Duration (ms)', fontsize=12, fontweight='bold')
    plt.ylabel('Phase 1 Delivery PRR (%)', fontsize=12, fontweight='bold')
    plt.xticks(durations)
    plt.grid(True, linestyle='--', alpha=0.6)
    all_prrs = y_sps_prr + y_csma_prr
    if all_prrs:
        plt.ylim([min(all_prrs) - 5, 100])
    plt.legend(fontsize=10, loc='lower right')
    
    plot_prr_path = os.path.join(PROJECT_DIR, "exp_p1_duration_prr_comparison.png")
    plt.savefig(plot_prr_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"📈 PRR Plot saved to: {plot_prr_path}")

    # Graph 2: Failure Breakdown (Collisions, Deafness, Aborts)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

    # Severe Preamble Collisions
    ax1.plot(x_dur, [r['sps']['preamble_coll'] for r in results if r['sps']], marker='o', color='#2980b9', linewidth=2, label='S-SPS RX Collisions')
    ax1.plot(x_csma_dur, [r['csma']['preamble_coll'] for r in results if r['csma']], marker='s', color='#e67e22', linewidth=2, linestyle='--', label='CSMA RX Collisions')
    ax1.set_title('(a) Severe Preamble Collisions vs P1 Duration', fontweight='bold', fontsize=12)
    ax1.set_xlabel('Phase 1 Duration (ms)', fontweight='bold')
    ax1.set_ylabel('Severe RX Collisions', fontweight='bold')
    ax1.set_xticks(durations)
    ax1.grid(True, linestyle='--', alpha=0.6)
    ax1.legend(fontsize=10)

    # CSMA Aborts & Sidelink Captures
    ax2.plot(x_csma_dur, [r['csma']['csma_abort'] for r in results if r['csma']], marker='x', color='#c0392b', linewidth=2, linestyle=':', label='CSMA Channel Access Aborts')
    ax2.plot(x_dur, [r['sps']['captures'] for r in results if r['sps']], marker='^', color='#8e44ad', linewidth=2, label='S-SPS Power Captures (Rescued)')
    ax2.set_title('(b) CSMA Aborts vs S-SPS Captures', fontweight='bold', fontsize=12)
    ax2.set_xlabel('Phase 1 Duration (ms)', fontweight='bold')
    ax2.set_ylabel('Event Count', fontweight='bold')
    ax2.set_xticks(durations)
    ax2.grid(True, linestyle='--', alpha=0.6)
    ax2.legend(fontsize=10)

    plt.tight_layout()
    plot_fail_path = os.path.join(PROJECT_DIR, "exp_p1_duration_failures_comparison.png")
    plt.savefig(plot_fail_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"📈 Failure Breakdown Plot saved to: {plot_fail_path}")

    # Graph 3: Latency & AoI Trade-off
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

    # Phase 2 PRR
    ax1.plot(x_dur, [r['sps']['p2_prr'] for r in results if r['sps']], marker='o', color='#27ae60', linewidth=2, label='S-SPS Phase 2 Data PRR')
    ax1.plot(x_csma_dur, [r['csma']['p2_prr'] for r in results if r['csma']], marker='s', color='#d35400', linewidth=2, linestyle='--', label='CSMA Phase 2 Data PRR')
    ax1.set_title('(a) Phase 2 Data PRR vs P1 Duration', fontweight='bold', fontsize=12)
    ax1.set_xlabel('Phase 1 Duration (ms)', fontweight='bold')
    ax1.set_ylabel('Phase 2 Delivery PRR (%)', fontweight='bold')
    ax1.set_xticks(durations)
    ax1.grid(True, linestyle='--', alpha=0.6)
    ax1.legend(fontsize=10)

    # Mean AoI (Latency penalty of expanding cycle)
    ax2.plot(x_dur, [r['sps']['mean_aoi'] for r in results if r['sps']], marker='o', color='#2980b9', linewidth=2, label='S-SPS Mean AoI')
    ax2.plot(x_csma_dur, [r['csma']['mean_aoi'] for r in results if r['csma']], marker='s', color='#e67e22', linewidth=2, linestyle='--', label='CSMA Mean AoI')
    ax2.plot(x_dur, [r['cycle'] for r in results], color='#7f8c8d', linestyle='-.', label='Theoretical Cycle Time (ms)')
    ax2.set_title('(b) Age of Information (AoI) vs P1 Duration (Latency Cost)', fontweight='bold', fontsize=12)
    ax2.set_xlabel('Phase 1 Duration (ms)', fontweight='bold')
    ax2.set_ylabel('Mean Beacon AoI (ms)', fontweight='bold')
    ax2.set_xticks(durations)
    ax2.grid(True, linestyle='--', alpha=0.6)
    ax2.legend(fontsize=10)

    plt.tight_layout()
    plot_aoi_path = os.path.join(PROJECT_DIR, "exp_p1_duration_p2_aoi.png")
    plt.savefig(plot_aoi_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"📈 AoI & Latency Trade-off Plot saved to: {plot_aoi_path}")

    # Graph 4: Comprehensive 4-Panel Research Dashboard
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))

    # 1. PRR vs Duration
    axes[0, 0].plot(x_dur, y_sps_prr, marker='o', linewidth=2.5, markersize=7, color='#2980b9', label='3GPP Sidelink S-SPS (100 µs)')
    axes[0, 0].plot(x_csma_dur, y_csma_prr, marker='s', linewidth=2.5, markersize=7, color='#e67e22', linestyle='--', label='Continuous CSMA-CA')
    axes[0, 0].set_title('(a) Phase 1 Discovery PRR vs Duration (3-15ms, 150 UAVs)', fontsize=12, fontweight='bold')
    axes[0, 0].set_xlabel('Phase 1 Duration (ms)', fontweight='bold')
    axes[0, 0].set_ylabel('Delivery PRR (%)', fontweight='bold')
    axes[0, 0].set_xticks(durations)
    axes[0, 0].grid(True, linestyle='--', alpha=0.6)
    if all_prrs:
        axes[0, 0].set_ylim([min(all_prrs) - 5, 100])
    axes[0, 0].legend(fontsize=9)

    # 2. PRR Gain Δ (%)
    x_gain_labels = [f"{r['dur']:.0f}" for r in results]
    y_gains = [(r['diff'] if r['diff'] is not None else 0.0) for r in results]
    colors = ['#27ae60' if (r['diff'] is not None and r['diff'] >= 0) else '#c0392b' for r in results]
    axes[0, 1].bar(x_gain_labels, y_gains, color=colors, alpha=0.85, edgecolor='black')
    axes[0, 1].set_title('(b) Sidelink S-SPS PRR Advantage (Δ Gain %)', fontsize=12, fontweight='bold')
    axes[0, 1].set_xlabel('Phase 1 Duration (ms)', fontweight='bold')
    axes[0, 1].set_ylabel('PRR Gain over CSMA (%)', fontweight='bold')
    axes[0, 1].axhline(0, color='gray', linestyle='--')
    axes[0, 1].grid(True, linestyle='--', alpha=0.6)

    # 3. Collisions & Aborts
    axes[1, 0].plot(x_dur, [r['sps']['preamble_coll'] for r in results if r['sps']], marker='o', color='#2980b9', linewidth=2, label='S-SPS Collisions')
    axes[1, 0].plot(x_csma_dur, [r['csma']['preamble_coll'] for r in results if r['csma']], marker='s', color='#e67e22', linewidth=2, linestyle='--', label='CSMA Collisions')
    axes[1, 0].plot(x_csma_dur, [r['csma']['csma_abort'] for r in results if r['csma']], marker='x', color='#c0392b', linewidth=2, linestyle=':', label='CSMA Aborts')
    axes[1, 0].set_title('(c) Channel Contention Breakdown vs Duration', fontsize=12, fontweight='bold')
    axes[1, 0].set_xlabel('Phase 1 Duration (ms)', fontweight='bold')
    axes[1, 0].set_ylabel('Severe Incidents', fontweight='bold')
    axes[1, 0].set_xticks(durations)
    axes[1, 0].grid(True, linestyle='--', alpha=0.6)
    axes[1, 0].legend(fontsize=9)

    # 4. AoI Trade-off
    axes[1, 1].plot(x_dur, [r['sps']['mean_aoi'] for r in results if r['sps']], marker='o', color='#2980b9', linewidth=2, label='S-SPS AoI (ms)')
    axes[1, 1].plot(x_csma_dur, [r['csma']['mean_aoi'] for r in results if r['csma']], marker='s', color='#e67e22', linewidth=2, linestyle='--', label='CSMA AoI (ms)')
    axes[1, 1].plot(x_dur, [r['cycle'] for r in results], color='#7f8c8d', linestyle='-.', label='Cycle Time (ms)')
    axes[1, 1].set_title('(d) Age of Information & Cycle Latency Cost', fontsize=12, fontweight='bold')
    axes[1, 1].set_xlabel('Phase 1 Duration (ms)', fontweight='bold')
    axes[1, 1].set_ylabel('Latency (ms)', fontweight='bold')
    axes[1, 1].set_xticks(durations)
    axes[1, 1].grid(True, linestyle='--', alpha=0.6)
    axes[1, 1].legend(fontsize=9)

    plt.suptitle(f'UAV Swarm Discovery Window Duration Sweep (3ms to 15ms, 150 UAVs)\n3GPP Sidelink S-SPS (100µs Micro-Slot) vs Baseline CSMA-CA', fontsize=14, fontweight='bold', y=0.995)
    plt.tight_layout()
    dashboard_path = os.path.join(PROJECT_DIR, "exp_p1_duration_comprehensive_dashboard.png")
    plt.savefig(dashboard_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"📊 Comprehensive Dashboard saved to: {dashboard_path}")

except Exception as e:
    print(f"Note: matplotlib plotting skipped ({e})")

# Auto-push to git if requested or specified
if "--autoPush" in sys.argv:
    print("\n📤 Auto-pushing experiment results to GitHub...")
    subprocess.run("git add exp_p1_duration_* && git commit -m 'data: complete 150-UAV phase 1 duration benchmark 3ms to 15ms' && git push origin main", shell=True, cwd=PROJECT_DIR)

print("\n🎉 Benchmark experiment execution and data generation complete!")
