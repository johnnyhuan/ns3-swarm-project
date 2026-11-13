#!/usr/bin/env python3
"""
CSMA-CA Transmit Power Control (TPC) Deep Analysis for 100 UAVs
Investigates the impact of Phase 1 TX Power on PRR and Failure Categories:
- Sweep: -6 dBm to +6 dBm (Step: 2 dBm -> 7 points)
- Swarm Scale: 100 UAVs in 200m x 200m x 80m 3D Space
- Physical Layer: BLE 5.4 2M PHY, C/I Capture Threshold = +6.0 dB
- Evaluates: PRR (%), Preamble Collisions, CSMA Aborts, RX Deafness, Low SINR, Captures
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
print("⚡ CSMA-CA TRANSMIT POWER CONTROL (TPC) DEEP EXPERIMENT (100 UAVs) ⚡")
print("==========================================================================================")

sim_time = float(sys.argv[1]) if len(sys.argv) > 1 else 1.5
num_nodes = 100
p1_duration = 10.0
capture_thresh_db = 6.0
space_size = 200.0
space_z = 80.0

# TX Power levels from -6 dBm to +6 dBm
power_levels = [-6, -4, -2, 0, 2, 4, 6]

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
NS3_DIR = os.path.expanduser("~/ns-3-dev")
if not os.path.exists(NS3_DIR):
    NS3_DIR = PROJECT_DIR

# Sync updated files to ns-3 directory
for rel_path in ["scratch/lr-wpan-swarm.cc", "src/lr-wpan/model/lr-wpan-phy.cc", "src/lr-wpan/model/lr-wpan-phy.h"]:
    src_f = os.path.join(PROJECT_DIR, rel_path)
    dst_f = os.path.join(NS3_DIR, rel_path)
    if os.path.exists(src_f) and os.path.abspath(src_f) != os.path.abspath(dst_f):
        try:
            os.makedirs(os.path.dirname(dst_f), exist_ok=True)
            subprocess.run(["cp", src_f, dst_f], check=True)
        except Exception:
            pass

def run_simulation(tx_power):
    for fname in ["p1_ground_truth_report.txt", "p2_ground_truth_report.txt", "run.log"]:
        fpath = os.path.join(NS3_DIR, fname)
        if os.path.exists(fpath):
            try: os.remove(fpath)
            except Exception: pass

    cmd = [
        "./ns3", "run",
        f"scratch/lr-wpan-swarm --numNodes={num_nodes} --p1Duration={p1_duration} "
        f"--simTime={sim_time} --spaceSize={space_size} --spaceZ={space_z} "
        f"--enableP1Ssa=false --p1TxPower={tx_power} "
        f"--p1CaptureThresholdDb={capture_thresh_db} --phyCaptureMarginDb={capture_thresh_db} "
        f"--autoPush=false"
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
        "links": 0, "success": 0, "prr": 0.0, "fails": 0,
        "csma_abort": 0, "rx_deafness": 0, "preamble_coll": 0, "low_sinr": 0,
        "captures": 0, "mean_sinr_succ": 0.0, "mean_sinr_drop": 0.0
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

    m = re.search(r"Delivered Links Mean SINR\s*:\s*([\d\.\-]+)\s*dB", src)
    if m: data["mean_sinr_succ"] = float(m.group(1))

    m = re.search(r"Low SINR Dropped Links Mean SINR\s*:\s*([\d\.\-]+)\s*dB", src)
    if m: data["mean_sinr_drop"] = float(m.group(1))

    return data

results = []

for p in power_levels:
    est_range = 100.0 * (10.0 ** (p / 30.0))
    print(f"▶️ Testing CSMA Phase 1 TX Power = {p:+2d} dBm (Est. Nominal Range: {est_range:4.1f}m)... ", end="", flush=True)
    res = run_simulation(p)
    if res is not None:
        print(f"PRR: {res['prr']:.1f}% | Coll: {res['preamble_coll']} | Abort: {res['csma_abort']} | LowSINR: {res['low_sinr']} | Captures: {res['captures']}")
    else:
        print("ERROR")
    results.append({"power": p, "range": est_range, "res": res})

# Print Comparative Table
print("\n" + "=" * 118)
print("📊 CSMA-CA TRANSMIT POWER CONTROL (TPC) BENCHMARK SUMMARY (100 UAVs, C/I >= +6.0 dB) 📊")
print("=" * 118)
print(f"| {'Power (dBm)':^12} | {'Est Range':^11} | {'PRR (%)':^9} | {'Collisions':^12} | {'CSMA Abort':^12} | {'Deafness':^10} | {'Low SINR':^10} | {'Captures':^10} |")
print("|" + "-" * 14 + "|" + "-" * 13 + "|" + "-" * 11 + "|" + "-" * 14 + "|" + "-" * 14 + "|" + "-" * 12 + "|" + "-" * 12 + "|" + "-" * 12 + "|")

for r in results:
    p = r["power"]
    rng = f"{r['range']:.1f} m"
    res = r["res"]
    if res:
        prr_str = f"{res['prr']:.1f}%"
        coll_str = f"{res['preamble_coll']:,}"
        abort_str = f"{res['csma_abort']:,}"
        deaf_str = f"{res['rx_deafness']:,}"
        sinr_str = f"{res['low_sinr']:,}"
        capt_str = f"{res['captures']:,}"
    else:
        prr_str = coll_str = abort_str = deaf_str = sinr_str = capt_str = "N/A"

    p_label = f"{p:+2d} dBm" + (" (Base)" if p == 0 else "")
    print(f"| {p_label:^12} | {rng:^11} | {prr_str:^9} | {coll_str:^12} | {abort_str:^12} | {deaf_str:^12} | {sinr_str:^10} | {capt_str:^10} |")

print("=" * 118)

# Save Report Files
txt_path = os.path.join(PROJECT_DIR, "exp_csma_tpc_results.txt")
csv_path = os.path.join(PROJECT_DIR, "exp_csma_tpc_results.csv")

with open(txt_path, "w", encoding="utf-8") as f:
    f.write("# CSMA-CA Transmit Power Control (TPC) Benchmark Results (100 UAVs)\n")
    f.write(f"- Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write(f"- Scale: 100 UAVs in 200m x 200m x 80m | Window: 10.0 ms | Strict BLE 5.4 C/I: +6.0 dB\n\n")
    f.write("| Power (dBm) | Est Range (m) | PRR (%) | Collisions | Aborts | Deafness | Low SINR | Captures |\n")
    f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
    for r in results:
        res = r["res"]
        if res:
            f.write(f"| {r['power']:+d} | {r['range']:.1f} | {res['prr']:.1f}% | {res['preamble_coll']} | {res['csma_abort']} | {res['rx_deafness']} | {res['low_sinr']} | {res['captures']} |\n")

with open(csv_path, "w", encoding="utf-8") as f:
    f.write("Power_dBm,Est_Range_m,PRR,Collisions,Aborts,Deafness,Low_SINR,Captures\n")
    for r in results:
        res = r["res"]
        if res:
            f.write(f"{r['power']},{r['range']:.1f},{res['prr']:.2f},{res['preamble_coll']},{res['csma_abort']},{res['rx_deafness']},{res['low_sinr']},{res['captures']}\n")

# Plot Figures
try:
    p_vals = [r["power"] for r in results if r["res"]]
    prr_vals = [r["res"]["prr"] for r in results if r["res"]]
    coll_vals = [r["res"]["preamble_coll"] for r in results if r["res"]]
    abort_vals = [r["res"]["csma_abort"] for r in results if r["res"]]
    sinr_vals = [r["res"]["low_sinr"] for r in results if r["res"]]
    deaf_vals = [r["res"]["rx_deafness"] for r in results if r["res"]]
    capt_vals = [r["res"]["captures"] for r in results if r["res"]]

    # Figure 1: PRR curve vs TX Power
    fig, ax = plt.subplots(figsize=(9, 5.5), dpi=300)
    ax.plot(p_vals, prr_vals, marker='o', markersize=8, linewidth=2.5, color='#d62728', label='CSMA-CA Delivery PRR (%)')
    
    # Mark optimal point
    best_idx = prr_vals.index(max(prr_vals))
    ax.plot(p_vals[best_idx], prr_vals[best_idx], marker='*', markersize=16, color='#ff7f0e', label=f'Optimal TPC: {p_vals[best_idx]:+d} dBm ({prr_vals[best_idx]:.1f}%)')

    for p, prr in zip(p_vals, prr_vals):
        ax.annotate(f"{prr:.1f}%", (p, prr), textcoords="offset points", xytext=(0, 9), ha='center', fontsize=9.5, fontweight='bold', color='#333333')

    ax.set_title('CSMA-CA Delivery PRR vs Transmit Power (100 UAVs, 200m×200m×80m)', fontsize=13, fontweight='bold', pad=12)
    ax.set_xlabel('Phase 1 Transmit Power (dBm)', fontsize=11, fontweight='bold')
    ax.set_ylabel('Top-5 Neighbor Delivery PRR (%)', fontsize=11, fontweight='bold')
    ax.set_xticks(p_vals)
    ax.set_xticklabels([f"{p:+d}" for p in p_vals])
    ax.set_ylim(min(prr_vals) - 6, 100)
    ax.grid(True, linestyle='--', alpha=0.55)
    ax.legend(loc='lower left', fontsize=10.5, framealpha=0.95)
    plt.tight_layout()
    fig1_path = os.path.join(PROJECT_DIR, "exp_csma_tpc_prr.png")
    plt.savefig(fig1_path)
    plt.close()
    print(f"✅ PRR plot saved to: {fig1_path}")

    # Figure 2: Dual-Panel Failure Decomposition Dashboard
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.8), dpi=300)

    # Left: PRR curve
    ax1.plot(p_vals, prr_vals, marker='o', markersize=8, linewidth=2.4, color='#d62728', label='CSMA-CA Delivery PRR')
    ax1.axvline(x=p_vals[best_idx], color='#2ca02c', linestyle=':', linewidth=2, label=f'Best Power ({p_vals[best_idx]:+d} dBm)')
    ax1.set_title('(a) Packet Delivery Ratio vs TX Power', fontsize=12, fontweight='bold')
    ax1.set_xlabel('Transmit Power (dBm)', fontsize=11, fontweight='bold')
    ax1.set_ylabel('Delivery PRR (%)', fontsize=11, fontweight='bold')
    ax1.set_xticks(p_vals)
    ax1.grid(True, linestyle='--', alpha=0.55)
    ax1.legend(loc='lower left', fontsize=10)

    # Right: Grouped Failures (Collisions, Aborts, Low SINR)
    width = 0.45
    x = range(len(p_vals))
    ax2.bar([i - width/2 for i in x], coll_vals, width=width, color='#e377c2', alpha=0.85, label='Preamble Collisions (Hidden Nodes)')
    ax2.bar([i + width/2 for i in x], abort_vals, width=width, color='#17becf', alpha=0.85, label='CSMA Aborts (Channel Busy)')
    ax2.plot(x, sinr_vals, marker='s', markersize=7, color='#bcbd22', linewidth=2.0, label='Low SINR (< 6 dB)')
    ax2.set_title('(b) Failure Breakdown vs TX Power', fontsize=12, fontweight='bold')
    ax2.set_xlabel('Transmit Power (dBm)', fontsize=11, fontweight='bold')
    ax2.set_ylabel('Number of Link Drops', fontsize=11, fontweight='bold')
    ax2.set_xticks(x)
    ax2.set_xticklabels([f"{p:+d}" for p in p_vals])
    ax2.grid(True, linestyle='--', alpha=0.55)
    ax2.legend(loc='upper right', fontsize=9.5)

    plt.tight_layout()
    fig2_path = os.path.join(PROJECT_DIR, "exp_csma_tpc_dashboard.png")
    plt.savefig(fig2_path)
    plt.close()
    print(f"✅ Dashboard plot saved to: {fig2_path}")

except Exception as e:
    print(f"Notice on plotting: {e}")

print("\n🎉 CSMA-CA TPC Experiment Script Ready!")
