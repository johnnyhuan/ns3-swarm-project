#!/usr/bin/env python3
"""
CSMA-CA Phase 1 Broadcast Duration Sweep: 3.0 ms to 20.0 ms (Continuous 1 ms step, 18 points)
Evaluates BLE 5.4 2M PHY CSMA-CA Delivery PRR and Detailed Physical Failure Root Causes:
- Swarm Scale: 100 UAVs in 200m x 200m x 80m
- Duration Points: 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20 ms
- Physical Layer: Bluetooth 5.4 LE 2M PHY (2 Mbps, 244 us air time), Strict C/I = +6.0 dB
- Tracks: Delivery PRR, Collisions, Aborts, Half-Duplex Deafness, Low SINR, Power Captures
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
print("⏱️  CSMA-CA BROADCAST DURATION SWEEP: 3.0 ms ~ 20.0 ms (CONTINUOUS 1 ms STEP) ⏱️")
print("==========================================================================================")

num_nodes = int(sys.argv[1]) if len(sys.argv) > 1 else 100
sim_time = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
space_size = 200.0
space_z = 80.0
capture_thresh_db = 6.0

# 3ms to 20ms, every single integer without skipping any number
durations = [float(d) for d in range(3, 21)]

print(f"• Target Swarm Scale    : {num_nodes} UAVs")
print(f"• Airspace Dimensions   : {space_size:.0f}m x {space_size:.0f}m x {space_z:.0f}m")
print(f"• Duration Sweep Range  : {durations} ms (18 points)")
print(f"• Simulation Duration   : {sim_time:.1f} s per evaluation point")
print(f"• Physical Threshold    : +{capture_thresh_db:.1f} dB (Strict BLE 5.4 C/I)")
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

def run_simulation(p1_dur):
    for fname in ["p1_ground_truth_report.txt", "p2_ground_truth_report.txt", "run.log"]:
        fpath = os.path.join(NS3_DIR, fname)
        if os.path.exists(fpath):
            try: os.remove(fpath)
            except Exception: pass

    cmd = [
        "./ns3", "run",
        f"scratch/lr-wpan-swarm --numNodes={num_nodes} --p1Duration={p1_dur} "
        f"--simTime={sim_time} --spaceSize={space_size} --spaceZ={space_z} "
        f"--enableP1Sidelink=false --p1CaptureThresholdDb={capture_thresh_db} "
        f"--phyCaptureMarginDb={capture_thresh_db} --autoPush=false"
    ]

    try:
        proc = subprocess.run(cmd, cwd=NS3_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=300)
        out = proc.stdout
    except subprocess.TimeoutExpired:
        print(f"TIMEOUT at {p1_dur}ms!")
        return None

    p1_rpt = os.path.join(NS3_DIR, "p1_ground_truth_report.txt")
    p1_text = ""
    if os.path.exists(p1_rpt):
        with open(p1_rpt, "r", encoding="utf-8", errors="ignore") as f:
            p1_text = f.read()

    combined_stdout = out + "\n" + p1_text
    return parse_metrics(p1_text, combined_stdout, p1_dur)

def parse_metrics(p1_text, stdout_text, p1_dur):
    data = {
        "p1_dur_ms": p1_dur,
        "traffic_load_G": (num_nodes * 0.244) / p1_dur,
        "links": 0, "success": 0, "prr": 0.0, "fails": 0,
        "csma_abort": 0, "rx_deafness": 0, "preamble_coll": 0, "low_sinr": 0, "captures": 0
    }
    src = p1_text if p1_text else stdout_text

    m = re.search(r"Total Expected P1 Neighbor Links.*:\s*(\d+)", src)
    if m: data["links"] = int(m.group(1))

    m = re.search(r"Successfully Received \(Delivered\)\s*:\s*(\d+)\s*\(([\d\.]+)%\)", src)
    if m:
        data["success"] = int(m.group(1))
        data["prr"] = float(m.group(2))

    m = re.search(r"Failed Link Receptions \(Dropped/Missed\)\s*:\s*(\d+)", src)
    if m: data["fails"] = int(m.group(1))

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

for d in durations:
    print(f"▶️ Testing Duration = {d:>4.1f} ms (Load G = {(num_nodes * 0.244) / d:4.2f}) ... ", end="", flush=True)
    res = run_simulation(d)
    if res is not None:
        print(f"PRR: {res['prr']:>5.1f}% | Coll: {res['preamble_coll']:>5} | Aborts: {res['csma_abort']:>5} | Deafness: {res['rx_deafness']:>4} | Captures: {res['captures']:>5}")
        results.append(res)
    else:
        print("ERROR / TIMEOUT")

# Output Summary Table
print("\n" + "=" * 115)
print("📊 CSMA-CA DURATION SWEEP BENCHMARK SUMMARY (3ms ~ 20ms, 100 UAVs, C/I >= +6.0 dB) 📊")
print("=" * 115)
print(f"| {'Duration':^10} | {'Load G':^8} | {'Delivery PRR':^14} | {'Collisions':^12} | {'CSMA Aborts':^13} | {'RX Deafness':^13} | {'Captures':^10} |")
print("|" + "-" * 12 + "|" + "-" * 10 + "|" + "-" * 16 + "|" + "-" * 14 + "|" + "-" * 15 + "|" + "-" * 15 + "|" + "-" * 12 + "|")

for r in results:
    dur_str = f"{r['p1_dur_ms']:.1f} ms"
    load_str = f"{r['traffic_load_G']:.2f}"
    prr_str = f"{r['prr']:.1f}% ({r['success']:,})"
    coll_str = f"{r['preamble_coll']:,}"
    abort_str = f"{r['csma_abort']:,}"
    deaf_str = f"{r['rx_deafness']:,}"
    capt_str = f"{r['captures']:,}"
    print(f"| {dur_str:^10} | {load_str:^8} | {prr_str:^14} | {coll_str:^12} | {abort_str:^13} | {deaf_str:^13} | {capt_str:^10} |")

print("=" * 115)

# Save CSV and TXT reports
csv_path = os.path.join(PROJECT_DIR, "exp_csma_duration_3_20ms_results.csv")
txt_path = os.path.join(PROJECT_DIR, "exp_csma_duration_3_20ms_report.txt")

with open(csv_path, "w", encoding="utf-8") as f:
    f.write("Duration_ms,Traffic_Load_G,Links,Success,PRR,Collisions,Aborts,RX_Deafness,Low_SINR,Captures\n")
    for r in results:
        f.write(f"{r['p1_dur_ms']:.1f},{r['traffic_load_G']:.3f},{r['links']},{r['success']},{r['prr']:.2f},{r['preamble_coll']},{r['csma_abort']},{r['rx_deafness']},{r['low_sinr']},{r['captures']}\n")

with open(txt_path, "w", encoding="utf-8") as f:
    f.write(f"# CSMA-CA Phase 1 Duration Sweep Benchmark (3.0 ms ~ 20.0 ms)\n")
    f.write(f"- Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write(f"- Scale: {num_nodes} UAVs in 200m x 200m x 80m\n")
    f.write(f"- PHY Standard: BLE 5.4 2M, Capture Margin = +6.0 dB\n\n")
    f.write("| Duration | Load G | Delivery PRR | Collisions | CSMA Aborts | RX Deafness | Captures |\n")
    f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
    for r in results:
        f.write(f"| {r['p1_dur_ms']:.1f} ms | {r['traffic_load_G']:.2f} | {r['prr']:.1f}% | {r['preamble_coll']} | {r['csma_abort']} | {r['rx_deafness']} | {r['captures']} |\n")

print(f"\n✅ Results saved to:\n  - {csv_path}\n  - {txt_path}")

# Plotting Publication-Quality Figures
dur_list = [r["p1_dur_ms"] for r in results]
prr_list = [r["prr"] for r in results]
coll_list = [r["preamble_coll"] for r in results]
abort_list = [r["csma_abort"] for r in results]
deaf_list = [r["rx_deafness"] for r in results]
capt_list = [r["captures"] for r in results]

# Figure 1: PRR vs Duration
fig, ax = plt.subplots(figsize=(10, 6), dpi=300)
ax.plot(dur_list, prr_list, marker='o', markersize=8, linewidth=2.5, color='#d62728', label='CSMA-CA (BLE 5.4 2M PHY)')

for i, d in enumerate(dur_list):
    offset_y = 10 if i % 2 == 0 else -16
    ax.annotate(f"{prr_list[i]:.1f}%", (d, prr_list[i]), textcoords="offset points", xytext=(0, offset_y),
                ha='center', fontsize=9, fontweight='bold', color='#d62728')

ax.set_title('CSMA-CA Packet Delivery Ratio vs Broadcast Window Duration (BLE 5.4 2M PHY, 100 UAVs)', fontsize=13, fontweight='bold', pad=12)
ax.set_xlabel('Phase 1 Broadcast Window Duration (ms, 1ms Step)', fontsize=11, fontweight='bold')
ax.set_ylabel('Top-5 Neighbor Delivery PRR (%)', fontsize=11, fontweight='bold')
ax.set_xticks(dur_list)
ax.set_ylim(min(prr_list) - 5, 100)
ax.grid(True, linestyle='--', alpha=0.55)
ax.legend(loc='lower right', fontsize=11, framealpha=0.95)

plt.tight_layout()
fig1_path = os.path.join(PROJECT_DIR, "csma_duration_3_20ms_prr.png")
plt.savefig(fig1_path)
plt.close()
print(f"✅ PRR Curve saved to {fig1_path}")

# Figure 2: Multi-Panel Failure Root Cause Analysis
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 10), dpi=300, sharex=True)

# Panel 1: PRR and Traffic Load G
ax1.plot(dur_list, prr_list, marker='o', markersize=7, linewidth=2.2, color='#d62728', label='Delivery PRR (%)')
ax1.set_ylabel('Delivery PRR (%)', fontsize=11, fontweight='bold', color='#d62728')
ax1.tick_params(axis='y', labelcolor='#d62728')
ax1.set_ylim(35, 100)
ax1.grid(True, linestyle='--', alpha=0.55)
ax1.set_title('(a) Packet Delivery Ratio & Traffic Load G', fontsize=12, fontweight='bold')

ax1_twin = ax1.twinx()
load_list = [r["traffic_load_G"] for r in results]
ax1_twin.plot(dur_list, load_list, marker='s', markersize=6, linewidth=2.0, color='#1f77b4', linestyle=':', label='Normalized Traffic Load G')
ax1_twin.set_ylabel('Normalized Channel Load G', fontsize=11, fontweight='bold', color='#1f77b4')
ax1_twin.tick_params(axis='y', labelcolor='#1f77b4')

# Panel 2: Drop Category Decomposition
ax2.plot(dur_list, coll_list, marker='^', markersize=7, linewidth=2.0, color='#ff7f0e', label='Preamble Collisions (Hidden Nodes)')
ax2.plot(dur_list, abort_list, marker='x', markersize=7, linewidth=2.0, color='#9467bd', label='CSMA Sender Aborts (CCA Busy)')
ax2.plot(dur_list, deaf_list, marker='d', markersize=6, linewidth=1.8, color='#8c564b', label='Half-Duplex RX Deafness')
ax2.set_title('(b) Failure Category Decomposition (Drops)', fontsize=12, fontweight='bold')
ax2.set_xlabel('Phase 1 Broadcast Window Duration (ms)', fontsize=11, fontweight='bold')
ax2.set_ylabel('Dropped Link Counts', fontsize=11, fontweight='bold')
ax2.set_xticks(dur_list)
ax2.grid(True, linestyle='--', alpha=0.55)
ax2.legend(loc='upper right', fontsize=10, framealpha=0.95)

plt.tight_layout()
fig2_path = os.path.join(PROJECT_DIR, "csma_duration_3_20ms_breakdown.png")
plt.savefig(fig2_path)
plt.close()
print(f"✅ Failure Breakdown Dashboard saved to {fig2_path}")

if "--no-push" not in sys.argv:
    print("\n🚀 Pushing experiment results and plots to GitHub main...")
    try:
        subprocess.run(
            "git add exp_csma_duration_3_20ms* csma_duration_3_20ms* && git commit -m 'data: upload 3ms to 20ms CSMA duration sweep results and plots' && git push origin main",
            shell=True,
            cwd=PROJECT_DIR,
            check=False
        )
        print("✅ Git push completed!")
    except Exception as e:
        print(f"⚠️ Git push notice: {e}")

print("🎉 Experiment script completed successfully!")
