#!/usr/bin/env python3
"""
CSMA-CA CCA (Clear Channel Assessment) Sensitivity Fine-Tuning Experiment (100 UAVs)
Sweeps CCA Energy Detection Threshold from Conservative (-102 dBm) to Aggressive (-76 dBm).
Investigates the trade-off: Channel Access Aborts vs Preamble Collisions.
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
print("🎛️ CSMA-CA CCA ENERGY DETECTION SENSITIVITY FINE-TUNING (100 UAVs) 🎛️")
print("==========================================================================================")

sim_time = float(sys.argv[1]) if len(sys.argv) > 1 else 1.5
num_nodes = 100
p1_duration = 10.0
capture_thresh_db = 6.0
space_size = 200.0
space_z = 80.0

# CCA Energy Detection Threshold sweep (dBm)
# From conservative (high sensitivity, frequent aborts) to aggressive (low sensitivity, high spatial reuse)
cca_thresholds = [-102.0, -98.0, -96.58, -92.0, -88.0, -84.0, -80.0, -76.0]

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
NS3_DIR = os.path.expanduser("~/ns-3-dev")
if not os.path.exists(NS3_DIR):
    NS3_DIR = PROJECT_DIR

# Sync updated files
for rel_path in ["scratch/lr-wpan-swarm.cc", "src/lr-wpan/model/lr-wpan-phy.cc", "src/lr-wpan/model/lr-wpan-phy.h"]:
    src_f = os.path.join(PROJECT_DIR, rel_path)
    dst_f = os.path.join(NS3_DIR, rel_path)
    if os.path.exists(src_f) and os.path.abspath(src_f) != os.path.abspath(dst_f):
        try:
            os.makedirs(os.path.dirname(dst_f), exist_ok=True)
            subprocess.run(["cp", src_f, dst_f], check=True)
        except Exception:
            pass

def run_simulation(cca_thresh):
    for fname in ["p1_ground_truth_report.txt", "p2_ground_truth_report.txt", "run.log"]:
        fpath = os.path.join(NS3_DIR, fname)
        if os.path.exists(fpath):
            try: os.remove(fpath)
            except Exception: pass

    cmd = [
        "./ns3", "run",
        f"scratch/lr-wpan-swarm --numNodes={num_nodes} --p1Duration={p1_duration} "
        f"--simTime={sim_time} --spaceSize={space_size} --spaceZ={space_z} "
        f"--enableP1Ssa=false --p1CcaThresholdDbm={cca_thresh} "
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
        "captures": 0
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

for thresh in cca_thresholds:
    # Estimate sensing radius (assuming 0 dBm TX power): d = 10^((0 - 46.68 - thresh) / 30)
    sensing_radius = 10.0 ** ((-46.6777 - thresh) / 30.0)
    label = f"{thresh:.1f} dBm" + (" (Default)" if abs(thresh - (-96.58)) < 0.1 else "")
    print(f"▶️ Testing CCA Threshold = {label:<20} (Sensing Radius: ~{sensing_radius:4.1f}m)... ", end="", flush=True)
    
    res = run_simulation(thresh)
    if res is not None:
        print(f"PRR: {res['prr']:.1f}% | Abort: {res['csma_abort']:4d} | Coll: {res['preamble_coll']:4d} | Captures: {res['captures']:5d}")
    else:
        print("ERROR")
    results.append({"thresh": thresh, "radius": sensing_radius, "res": res})

# Print Comparative Summary
print("\n" + "=" * 122)
print("📊 CSMA-CA CCA SENSITIVITY TUNING SUMMARY (100 UAVs, C/I >= +6.0 dB) 📊")
print("=" * 122)
print(f"| {'CCA Thresh (dBm)':^18} | {'Sensing Radius':^16} | {'PRR (%)':^9} | {'CSMA Abort':^12} | {'Collisions':^12} | {'Deafness':^10} | {'Captures':^11} |")
print("|" + "-" * 20 + "|" + "-" * 18 + "|" + "-" * 11 + "|" + "-" * 14 + "|" + "-" * 14 + "|" + "-" * 12 + "|" + "-" * 13 + "|")

for r in results:
    th = r["thresh"]
    rad = f"~{r['radius']:.1f} m"
    res = r["res"]
    if res:
        prr_str = f"{res['prr']:.1f}%"
        abort_str = f"{res['csma_abort']:,}"
        coll_str = f"{res['preamble_coll']:,}"
        deaf_str = f"{res['rx_deafness']:,}"
        capt_str = f"{res['captures']:,}"
    else:
        prr_str = abort_str = coll_str = deaf_str = capt_str = "N/A"

    th_label = f"{th:.2f} dBm" + (" (Std)" if abs(th - (-96.58)) < 0.1 else "")
    print(f"| {th_label:^18} | {rad:^16} | {prr_str:^9} | {abort_str:^12} | {coll_str:^12} | {deaf_str:^10} | {capt_str:^11} |")

print("=" * 122)

# Save Text and CSV Reports
txt_path = os.path.join(PROJECT_DIR, "exp_csma_cca_results.txt")
csv_path = os.path.join(PROJECT_DIR, "exp_csma_cca_results.csv")

with open(txt_path, "w", encoding="utf-8") as f:
    f.write("# CSMA-CA Clear Channel Assessment (CCA) Sensitivity Fine-Tuning (100 UAVs)\n")
    f.write(f"- Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write(f"- Scale: 100 UAVs in 200m x 200m x 80m | Window: 10.0 ms | Strict BLE 5.4 C/I: +6.0 dB\n\n")
    f.write("| CCA Thresh (dBm) | Sensing Radius (m) | PRR (%) | CSMA Aborts | Collisions | Deafness | Captures |\n")
    f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
    for r in results:
        res = r["res"]
        if res:
            f.write(f"| {r['thresh']:.2f} | {r['radius']:.1f} | {res['prr']:.1f}% | {res['csma_abort']} | {res['preamble_coll']} | {res['rx_deafness']} | {res['captures']} |\n")

with open(csv_path, "w", encoding="utf-8") as f:
    f.write("CCA_Thresh_dBm,Sensing_Radius_m,PRR,CSMA_Aborts,Collisions,Deafness,Low_SINR,Captures\n")
    for r in results:
        res = r["res"]
        if res:
            f.write(f"{r['thresh']:.2f},{r['radius']:.1f},{res['prr']:.2f},{res['csma_abort']},{res['preamble_coll']},{res['rx_deafness']},{res['low_sinr']},{res['captures']}\n")

# Plot Publication-Quality Figures
try:
    th_vals = [r["thresh"] for r in results if r["res"]]
    prr_vals = [r["res"]["prr"] for r in results if r["res"]]
    abort_vals = [r["res"]["csma_abort"] for r in results if r["res"]]
    coll_vals = [r["res"]["preamble_coll"] for r in results if r["res"]]
    deaf_vals = [r["res"]["rx_deafness"] for r in results if r["res"]]
    capt_vals = [r["res"]["captures"] for r in results if r["res"]]

    best_idx = prr_vals.index(max(prr_vals))

    # Figure 1: PRR curve vs CCA Threshold
    fig, ax = plt.subplots(figsize=(9.5, 5.5), dpi=300)
    ax.plot(th_vals, prr_vals, marker='o', markersize=8, linewidth=2.5, color='#1f77b4', label='CSMA-CA Delivery PRR (%)')
    ax.plot(th_vals[best_idx], prr_vals[best_idx], marker='*', markersize=16, color='#ff7f0e',
            label=f'Optimal Sensitivity: {th_vals[best_idx]:.1f} dBm ({prr_vals[best_idx]:.1f}%)')

    for th, prr in zip(th_vals, prr_vals):
        ax.annotate(f"{prr:.1f}%", (th, prr), textcoords="offset points", xytext=(0, 9), ha='center', fontsize=9.5, fontweight='bold', color='#333333')

    ax.set_title('CSMA-CA Delivery PRR vs CCA Energy Detection Threshold (100 UAVs)', fontsize=13, fontweight='bold', pad=12)
    ax.set_xlabel('CCA Energy Detection Threshold (dBm) [Conservative $\\leftarrow$ Sensitive $\\rightarrow$ Aggressive]', fontsize=11, fontweight='bold')
    ax.set_ylabel('Top-5 Neighbor Delivery PRR (%)', fontsize=11, fontweight='bold')
    ax.set_xticks(th_vals)
    ax.set_xticklabels([f"{t:.1f}" for t in th_vals])
    ax.set_ylim(min(prr_vals) - 6, 100)
    ax.grid(True, linestyle='--', alpha=0.55)
    ax.legend(loc='lower left', fontsize=10.5, framealpha=0.95)
    plt.tight_layout()
    fig1_path = os.path.join(PROJECT_DIR, "exp_csma_cca_prr.png")
    plt.savefig(fig1_path)
    plt.close()
    print(f"✅ PRR plot saved to: {fig1_path}")

    # Figure 2: Trade-off Dashboard (Aborts vs Collisions)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.8), dpi=300)

    # Panel A: Delivery PRR
    ax1.plot(th_vals, prr_vals, marker='o', markersize=8, linewidth=2.4, color='#1f77b4', label='CSMA-CA PRR')
    ax1.axvline(x=th_vals[best_idx], color='#2ca02c', linestyle=':', linewidth=2, label=f'Best Threshold ({th_vals[best_idx]:.1f} dBm)')
    ax1.set_title('(a) Delivery PRR vs CCA Sensitivity', fontsize=12, fontweight='bold')
    ax1.set_xlabel('CCA Threshold (dBm)', fontsize=11, fontweight='bold')
    ax1.set_ylabel('Delivery PRR (%)', fontsize=11, fontweight='bold')
    ax1.set_xticks(th_vals)
    ax1.grid(True, linestyle='--', alpha=0.55)
    ax1.legend(loc='lower left', fontsize=10)

    # Panel B: The Fundamental Trade-off (Aborts decrease vs Collisions increase)
    width = 1.6
    ax2.bar([t - width/2 for t in th_vals], abort_vals, width=width, color='#d62728', alpha=0.85, label='CSMA Aborts (Channel Busy)')
    ax2.bar([t + width/2 for t in th_vals], coll_vals, width=width, color='#9467bd', alpha=0.85, label='Preamble Collisions (Hidden Nodes)')
    ax2.set_title('(b) Trade-off: Channel Aborts vs Preamble Collisions', fontsize=12, fontweight='bold')
    ax2.set_xlabel('CCA Threshold (dBm) [Conservative $\\leftarrow \\rightarrow$ Aggressive]', fontsize=11, fontweight='bold')
    ax2.set_ylabel('Number of Link Drops', fontsize=11, fontweight='bold')
    ax2.set_xticks(th_vals)
    ax2.grid(True, linestyle='--', alpha=0.55)
    ax2.legend(loc='upper right', fontsize=10)

    plt.tight_layout()
    fig2_path = os.path.join(PROJECT_DIR, "exp_csma_cca_dashboard.png")
    plt.savefig(fig2_path)
    plt.close()
    print(f"✅ Trade-off Dashboard plot saved to: {fig2_path}")

except Exception as e:
    print(f"Notice on plotting: {e}")

print("\n🎉 CSMA-CA CCA Sensitivity Experiment Ready!")
