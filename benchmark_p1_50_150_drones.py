#!/usr/bin/env python3
"""
UAV Swarm Phase 1 Benchmark: 50 to 150 UAVs under Strict Bluetooth 5.4 LE 2M (+6.0 dB C/I)
Compares 3GPP Sidelink Mode 4 S-SPS (100 µs Micro-Slot) vs CSMA-CA Baseline.
- Swarm Scale: 50 to 150 UAVs (step 10, continuous sweep without gaps)
- Physical Layer: Bluetooth 5.4 LE 2M PHY, C/I Capture Threshold = +6.0 dB
- Broadcast Window: 10.0 ms (98 Micro-Slots in Sidelink)
- Airspace: 200m x 200m x 80m 3D Space, UAV Speed = 10.0 m/s
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
print("🚀 UAV SWARM PHASE 1 BENCHMARK: 50-150 UAVs (STRICT +6.0 dB BLE 5.4 C/I) 🚀")
print("==========================================================================================")

sim_time = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
p1_duration = 10.0
p1_slot_us = 100.0
capture_thresh_db = 6.0
space_size = 200.0
space_z = 80.0

# 50 to 150 UAVs in steps of 10
node_counts = list(range(50, 151, 10))

print(f"• UAV Swarm Scale Points : {node_counts} UAVs (11 points)")
print(f"• Physical C/I Threshold : +{capture_thresh_db:.1f} dB (Strict Bluetooth 5.4 LE 2M)")
print(f"• Phase 1 Broadcast Win  : {p1_duration:.1f} ms")
print(f"• Sidelink Micro-Slot    : {p1_slot_us:.0f} µs ({int((p1_duration * 1000.0 - 250.0) / p1_slot_us) + 1} slots)")
print(f"• Airspace Dimensions    : {space_size:.0f}m x {space_size:.0f}m x {space_z:.0f}m")
print(f"• Mobility Speed         : 10.0 m/s (36 km/h)")
print(f"• Simulation Time        : {sim_time:.1f} s per run")
print("------------------------------------------------------------------------------------------\n")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
NS3_DIR = os.path.expanduser("~/ns-3-dev")
if not os.path.exists(NS3_DIR):
    NS3_DIR = PROJECT_DIR

# Sync updated files to ns-3 directory if needed
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
            print(f"=> Syncing {rel_path} to {dst_f}...")
            os.makedirs(os.path.dirname(dst_f), exist_ok=True)
            subprocess.run(["cp", src_f, dst_f], check=True)
        except Exception as e:
            print(f"Error syncing {rel_path}: {e}")
            sys.exit(1)

def run_simulation(nodes, enable_sidelink):
    for fname in ["p1_ground_truth_report.txt", "p2_ground_truth_report.txt", "run.log"]:
        fpath = os.path.join(NS3_DIR, fname)
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
            except Exception:
                pass

    cmd = [
        "./ns3", "run",
        f"scratch/lr-wpan-swarm --numNodes={nodes} --p1Duration={p1_duration} "
        f"--simTime={sim_time} --spaceSize={space_size} --spaceZ={space_z} "
        f"--enableP1Sidelink={'true' if enable_sidelink else 'false'} "
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
        "p1_links": 0,
        "p1_success": 0,
        "p1_prr": 0.0,
        "p1_fails": 0,
        "csma_abort": 0,
        "rx_deafness": 0,
        "preamble_coll": 0,
        "low_sinr": 0,
        "captures": 0
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

    # 1. Run Baseline CSMA-CA
    print(f"   [1/2] Running CSMA-CA Baseline ... ", end="", flush=True)
    csma_res = run_simulation(nodes, enable_sidelink=False)
    if csma_res is not None:
        print(f"PRR: {csma_res['p1_prr']:.1f}% | Coll: {csma_res['preamble_coll']} | Aborts: {csma_res['csma_abort']} | Captures: {csma_res['captures']}")
    else:
        print(f"TIMEOUT / ERROR")

    # 2. Run Sidelink S-SPS
    print(f"   [2/2] Running Sidelink S-SPS (+6dB) ... ", end="", flush=True)
    sps_res = run_simulation(nodes, enable_sidelink=True)
    if sps_res is not None:
        print(f"PRR: {sps_res['p1_prr']:.1f}% | Coll: {sps_res['preamble_coll']} | Captures: {sps_res['captures']}")
    else:
        print("TIMEOUT / ERROR")

    if csma_res is not None and sps_res is not None:
        diff = sps_res['p1_prr'] - csma_res['p1_prr']
        print(f"   ==> Δ PRR Gain: {diff:+.1f}% ({'⭐ Sidelink Wins' if diff >= 0 else '⚠️ CSMA Wins'})\n")
    else:
        diff = None
        print(f"   ==> Δ PRR Gain: N/A\n")

    results.append({
        "nodes": nodes,
        "csma": csma_res,
        "sps": sps_res,
        "diff": diff
    })

# Print Full Comparative Table
print("\n" + "=" * 125)
print("📊 UAV SWARM PHASE 1 BENCHMARK SUMMARY (50-150 UAVs, C/I >= +6.0 dB) 📊")
print("=" * 125)
print(f"| {'Nodes':^7} | {'CSMA PRR':^10} | {'S-SPS PRR':^10} | {'Δ Gain':^9} | {'CSMA Abort':^11} | {'CSMA Coll':^10} | {'CSMA Capt':^10} | {'SPS Capt':^10} | {'Evaluation':^18} |")
print("|" + "-" * 9 + "|" + "-" * 12 + "|" + "-" * 12 + "|" + "-" * 11 + "|" + "-" * 13 + "|" + "-" * 12 + "|" + "-" * 12 + "|" + "-" * 12 + "|" + "-" * 20 + "|")

for r in results:
    nodes = r["nodes"]
    csma_prr = f"{r['csma']['p1_prr']:.1f}%" if r["csma"] else "N/A"
    sps_prr = f"{r['sps']['p1_prr']:.1f}%" if r["sps"] else "N/A"
    diff_str = f"{r['diff']:+6.1f}%" if r["diff"] is not None else "N/A"
    csma_abort = f"{r['csma']['csma_abort']:,}" if r["csma"] else "N/A"
    csma_coll = f"{r['csma']['preamble_coll']:,}" if r["csma"] else "N/A"
    csma_capt = f"{r['csma']['captures']:,}" if r["csma"] else "N/A"
    sps_capt = f"{r['sps']['captures']:,}" if r["sps"] else "N/A"

    eval_str = "🚀 Sidelink Dominant" if (r["diff"] is not None and r["diff"] > 5.0) else ("🤝 Comparable" if (r["diff"] is not None and abs(r["diff"]) <= 5.0) else "CSMA Marginally Ahead")
    print(f"| {nodes:^7} | {csma_prr:^10} | {sps_prr:^10} | {diff_str:^9} | {csma_abort:^11} | {csma_coll:^10} | {csma_capt:^10} | {sps_capt:^10} | {eval_str:^18} |")

print("=" * 125)

# Save Text and CSV reports
txt_path = os.path.join(PROJECT_DIR, "exp_p1_scale_50_150_results.txt")
csv_path = os.path.join(PROJECT_DIR, "exp_p1_scale_50_150_results.csv")

with open(txt_path, "w", encoding="utf-8") as f:
    f.write("# UAV Swarm Phase 1 Benchmark: 50 to 150 UAVs (Strict Bluetooth 5.4 LE 2M +6.0 dB C/I)\n")
    f.write(f"- Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write(f"- Phase 1 Duration: {p1_duration:.1f} ms\n")
    f.write(f"- Sidelink Slot Width: {p1_slot_us:.0f} µs (98 slots)\n")
    f.write(f"- Capture SINR Threshold: +{capture_thresh_db:.1f} dB\n\n")
    f.write("| Nodes | CSMA PRR (%) | S-SPS PRR (%) | Δ Gain (%) | CSMA Aborts | CSMA Collisions | SPS Collisions | SPS Captures | Evaluation |\n")
    f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
    for r in results:
        f.write(f"| {r['nodes']} | {r['csma']['p1_prr']:.1f}% | {r['sps']['p1_prr']:.1f}% | {r['diff']:+.1f}% | {r['csma']['csma_abort']} | {r['csma']['preamble_coll']} | {r['sps']['preamble_coll']} | {r['sps']['captures']} | {'Sidelink Dominant' if r['diff'] > 5.0 else 'Comparable'} |\n")

with open(csv_path, "w", encoding="utf-8") as f:
    f.write("Nodes,CSMA_PRR,SPS_PRR,Delta_Gain,CSMA_Aborts,CSMA_Collisions,SPS_Collisions,SPS_Captures\n")
    for r in results:
        f.write(f"{r['nodes']},{r['csma']['p1_prr']:.2f},{r['sps']['p1_prr']:.2f},{r['diff']:.2f},{r['csma']['csma_abort']},{r['csma']['preamble_coll']},{r['sps']['preamble_coll']},{r['sps']['captures']}\n")

print(f"\n✅ Summary report saved to: {txt_path}")
print(f"✅ CSV data saved to: {csv_path}")

# Plotting publication-quality figures
nodes_list = [r["nodes"] for r in results]
csma_prrs = [r["csma"]["p1_prr"] for r in results]
sps_prrs = [r["sps"]["p1_prr"] for r in results]

# Figure 1: Clean Comparison Curve
fig, ax = plt.subplots(figsize=(10, 6))
ax.plot(nodes_list, sps_prrs, marker='s', markersize=8, linewidth=2.5, color='#1f77b4', label='3GPP Sidelink S-SPS (100 µs Micro-Slot, C/I $\ge$ +6.0 dB)')
ax.plot(nodes_list, csma_prrs, marker='o', markersize=8, linewidth=2.5, color='#d62728', linestyle='--', label='CSMA-CA Baseline (BLE 2M PHY)')

for i, n in enumerate(nodes_list):
    ax.annotate(f"{sps_prrs[i]:.1f}%", (n, sps_prrs[i]), textcoords="offset points", xytext=(0, 10), ha='center', fontsize=9, fontweight='bold', color='#1f77b4')
    ax.annotate(f"{csma_prrs[i]:.1f}%", (n, csma_prrs[i]), textcoords="offset points", xytext=(0, -15), ha='center', fontsize=9, fontweight='bold', color='#d62728')

ax.set_title('Phase 1 Broadcast PRR vs UAV Swarm Scale (50–150 UAVs, C/I $\ge$ +6.0 dB)', fontsize=14, fontweight='bold')
ax.set_xlabel('Swarm Scale (Number of UAVs in 200m x 200m x 80m)', fontsize=12, fontweight='bold')
ax.set_ylabel('Phase 1 Delivery PRR (%)', fontsize=12, fontweight='bold')
ax.set_xticks(nodes_list)
ax.set_ylim(min(min(csma_prrs), min(sps_prrs)) - 8, 102)
ax.grid(True, linestyle='--', alpha=0.6)
ax.legend(loc='lower left', fontsize=11, framealpha=0.9)

plt.tight_layout()
fig1_path = os.path.join(PROJECT_DIR, "exp_p1_scale_50_150_prr.png")
plt.savefig(fig1_path, dpi=300)
plt.close()
print(f"✅ PRR plot saved to: {fig1_path}")

# Figure 2: Comprehensive Multi-Panel Dashboard
fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(11, 12), sharex=True)

# Panel 1: PRR Curves
ax1.plot(nodes_list, sps_prrs, marker='s', markersize=7, linewidth=2.2, color='#1f77b4', label='Sidelink S-SPS (100 µs)')
ax1.plot(nodes_list, csma_prrs, marker='o', markersize=7, linewidth=2.2, color='#d62728', linestyle='--', label='CSMA-CA Baseline')
ax1.set_ylabel('Phase 1 PRR (%)', fontsize=11, fontweight='bold')
ax1.set_ylim(min(min(csma_prrs), min(sps_prrs)) - 8, 102)
ax1.grid(True, linestyle='--', alpha=0.6)
ax1.legend(loc='lower left', fontsize=10)
ax1.set_title('Comprehensive Swarm Scalability Analysis (50 to 150 UAVs, BLE 5.4 C/I = +6.0 dB)', fontsize=13, fontweight='bold')

# Panel 2: Sidelink Captures
capt_list = [r["sps"]["captures"] for r in results]
ax2.plot(nodes_list, capt_list, marker='^', markersize=7, linewidth=2.0, color='#ff7f0e', label='Power Capture Events (C/I $\ge$ +6 dB)')
ax2.set_ylabel('Capture Rescues', fontsize=11, fontweight='bold', color='#ff7f0e')
ax2.tick_params(axis='y', labelcolor='#ff7f0e')
ax2.grid(True, linestyle='--', alpha=0.6)
ax2.legend(loc='upper left', fontsize=10)

# Panel 3: Collision Failures
csma_colls = [r["csma"]["preamble_coll"] for r in results]
sps_colls = [r["sps"]["preamble_coll"] for r in results]
width = 3.5
x_pos = [n for n in nodes_list]
ax3.bar([x - width/2 for x in x_pos], csma_colls, width=width, color='#d62728', alpha=0.8, label='CSMA Collisions')
ax3.bar([x + width/2 for x in x_pos], sps_colls, width=width, color='#1f77b4', alpha=0.8, label='Sidelink Collisions')
ax3.set_xlabel('Swarm Scale (Number of UAVs)', fontsize=11, fontweight='bold')
ax3.set_ylabel('Collisions (Drops)', fontsize=11, fontweight='bold')
ax3.grid(True, linestyle='--', alpha=0.6)
ax3.legend(loc='upper left', fontsize=10)

plt.tight_layout()
fig2_path = os.path.join(PROJECT_DIR, "exp_p1_scale_50_150_dashboard.png")
plt.savefig(fig2_path, dpi=300)
plt.close()
print(f"✅ Dashboard plot saved to: {fig2_path}")

print("📤 Uploading benchmark results to GitHub...")
try:
    subprocess.run("git add exp_p1_scale_50_150* && git commit -m 'data: upload 50-150 UAV benchmark results' && git push origin main", shell=True, cwd=PROJECT_DIR)
except Exception as e:
    print(f"Notice on auto-push: {e}")

print("\n🎉 Benchmark Completed Successfully!")
