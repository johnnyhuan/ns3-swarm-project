#!/usr/bin/env python3
"""
3GPP Sidelink S-SPS Benchmark: Physical Capture Effect (Capture Enabled vs Capture Disabled)
Evaluates 3GPP Sidelink Mode 4 S-SPS with and without Power Capture Effect across 50 to 150 UAVs.
- Swarm Scale: 50 to 150 UAVs (step 10, or single scale like 100 UAVs)
- Physical Layer: Bluetooth 5.4 LE 2M, C/I Capture Threshold = +6.0 dB
- Evaluates: PRR Gain from Capture, Collision Reduction, and Exact Capture Rescues
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
print("🚀 SIDELINK S-SPS BENCHMARK: CAPTURE ENABLED (+6dB) vs CAPTURE DISABLED 🚀")
print("==========================================================================================")

# Configurable arguments
if len(sys.argv) > 1 and sys.argv[1].isdigit():
    node_counts = [int(sys.argv[1])]
    sim_time = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
else:
    node_counts = list(range(50, 151, 10))
    sim_time = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0

p1_duration = 10.0
p1_slot_us = 250.0
capture_margin_db = 6.0
space_size = 200.0
space_z = 80.0

print(f"• UAV Swarm Scale Points : {node_counts} UAVs")
print(f"• Phase 1 Broadcast Win  : {p1_duration:.1f} ms (98 Micro-Slots of 100 µs)")
print(f"• Capture Margin (if on) : +{capture_margin_db:.1f} dB (Strict BLE 5.4 LE 2M C/I)")
print(f"• Airspace Dimensions    : {space_size:.0f}m x {space_size:.0f}m x {space_z:.0f}m")
print(f"• Mobility Speed         : 10.0 m/s (36 km/h)")
print(f"• Simulation Time        : {sim_time:.1f} s per point")
print("------------------------------------------------------------------------------------------\n")

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
            print(f"=> Syncing {rel_path} to {dst_f}...")
            os.makedirs(os.path.dirname(dst_f), exist_ok=True)
            subprocess.run(["cp", src_f, dst_f], check=True)
        except Exception as e:
            print(f"Error syncing {rel_path}: {e}")
            sys.exit(1)

def run_sidelink(nodes, enable_capture):
    for fname in ["p1_ground_truth_report.txt", "p2_ground_truth_report.txt", "run.log"]:
        fpath = os.path.join(NS3_DIR, fname)
        if os.path.exists(fpath):
            try: os.remove(fpath)
            except Exception: pass

    cmd = [
        "./ns3", "run",
        f"scratch/lr-wpan-swarm --numNodes={nodes} --p1Duration={p1_duration} "
        f"--simTime={sim_time} --spaceSize={space_size} --spaceZ={space_z} "
        f"--enableP1Sidelink=true --p1SlotUs={p1_slot_us} "
        f"--enablePhyCapture={'true' if enable_capture else 'false'} "
        f"--p1CaptureThresholdDb={capture_margin_db} "
        f"--phyCaptureMarginDb={capture_margin_db} --autoPush=false"
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
        "links": 0, "succ": 0, "prr": 0.0, "fail": 0,
        "rx_deafness": 0, "preamble_coll": 0, "low_sinr": 0, "captures": 0
    }

    src = p1_text if p1_text else stdout_text

    m = re.search(r"Total Expected P1 Neighbor Links.*:\s*(\d+)", src)
    if m: data["links"] = int(m.group(1))

    m = re.search(r"Successfully Received \(Delivered\)\s*:\s*(\d+)\s*\(([\d\.]+)%\)", src)
    if m:
        data["succ"] = int(m.group(1))
        data["prr"] = float(m.group(2))

    m = re.search(r"Failed Link Receptions \(Dropped/Missed\)\s*:\s*(\d+)", src)
    if m: data["fail"] = int(m.group(1))

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

    # 1. Sidelink With Capture (+6 dB)
    print(f"   [1/2] Sidelink S-SPS With Capture (+6.0 dB) ... ", end="", flush=True)
    with_cap = run_sidelink(nodes, enable_capture=True)
    if with_cap is not None:
        print(f"PRR: {with_cap['prr']:.1f}% | Coll: {with_cap['preamble_coll']} | Captures: {with_cap['captures']}")
    else:
        print("TIMEOUT / ERROR")

    # 2. Sidelink Without Capture
    print(f"   [2/2] Sidelink S-SPS Without Capture (Disabled) ... ", end="", flush=True)
    no_cap = run_sidelink(nodes, enable_capture=False)
    if no_cap is not None:
        print(f"PRR: {no_cap['prr']:.1f}% | Coll: {no_cap['preamble_coll']} | Captures: {no_cap['captures']}")
    else:
        print("TIMEOUT / ERROR")

    if with_cap is not None and no_cap is not None:
        diff = with_cap['prr'] - no_cap['prr']
        print(f"   ==> Δ Capture Gain: {diff:+.1f}% ({'⭐ Capture Critical' if diff > 5.0 else '⚖️ Moderate Gain'})\n")
    else:
        diff = None
        print(f"   ==> Δ Capture Gain: N/A\n")

    results.append({
        "nodes": nodes,
        "with_cap": with_cap,
        "no_cap": no_cap,
        "diff": diff
    })

# Print Full Comparative Table
print("\n" + "=" * 120)
print("📊 SIDELINK S-SPS BENCHMARK: CAPTURE (+6dB) vs NO CAPTURE SUMMARY 📊")
print("=" * 120)
print(f"| {'Nodes':^7} | {'With Capture':^14} | {'No Capture':^14} | {'Δ Gain':^10} | {'With Coll':^11} | {'No Coll':^11} | {'Captures':^12} | {'Capture Importance':^20} |")
print("|" + "-" * 9 + "|" + "-" * 16 + "|" + "-" * 16 + "|" + "-" * 12 + "|" + "-" * 13 + "|" + "-" * 13 + "|" + "-" * 14 + "|" + "-" * 22 + "|")

for r in results:
    nodes = r["nodes"]
    with_prr = f"{r['with_cap']['p1_prr']:.1f}%" if r["with_cap"] else "N/A"
    no_prr = f"{r['no_cap']['p1_prr']:.1f}%" if r["no_cap"] else "N/A"
    diff_str = f"{r['diff']:+6.1f}%" if r["diff"] is not None else "N/A"
    with_coll = f"{r['with_cap']['preamble_coll']:,}" if r["with_cap"] else "N/A"
    no_coll = f"{r['no_cap']['preamble_coll']:,}" if r["no_cap"] else "N/A"
    capt_cnt = f"{r['with_cap']['captures']:,}" if r["with_cap"] else "N/A"

    importance = "🔥 Essential (+15%+)" if (r["diff"] is not None and r["diff"] > 15.0) else ("🚀 Major Gain (+5~15%)" if (r["diff"] is not None and r["diff"] > 5.0) else "Moderate")
    print(f"| {nodes:^7} | {with_prr:^14} | {no_prr:^14} | {diff_str:^10} | {with_coll:^11} | {no_coll:^11} | {capt_cnt:^12} | {importance:^20} |")

print("=" * 120)

# Save Reports
txt_path = os.path.join(PROJECT_DIR, "exp_sidelink_capture_comparison_results.txt")
csv_path = os.path.join(PROJECT_DIR, "exp_sidelink_capture_comparison_results.csv")

with open(txt_path, "w", encoding="utf-8") as f:
    f.write("# 3GPP Sidelink S-SPS Benchmark: Capture Enabled (+6dB) vs Capture Disabled\n")
    f.write(f"- Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write(f"- Phase 1 Duration: {p1_duration:.1f} ms\n")
    f.write(f"- Micro-Slot: {p1_slot_us:.0f} µs (98 slots)\n")
    f.write(f"- Capture Margin: +{capture_margin_db:.1f} dB\n\n")
    f.write("| Nodes | With Capture PRR | No Capture PRR | Delta Gain | With Collisions | No Collisions | Captures | Importance |\n")
    f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
    for r in results:
        f.write(f"| {r['nodes']} | {r['with_cap']['p1_prr']:.1f}% | {r['no_cap']['p1_prr']:.1f}% | {r['diff']:+.1f}% | {r['with_cap']['preamble_coll']} | {r['no_cap']['preamble_coll']} | {r['with_cap']['captures']} | {'Essential' if r['diff'] > 15.0 else 'Major'} |\n")

with open(csv_path, "w", encoding="utf-8") as f:
    f.write("Nodes,With_Capture_PRR,No_Capture_PRR,Delta_Gain,With_Collisions,No_Collisions,Captures\n")
    for r in results:
        f.write(f"{r['nodes']},{r['with_cap']['p1_prr']:.2f},{r['no_cap']['p1_prr']:.2f},{r['diff']:.2f},{r['with_cap']['preamble_coll']},{r['no_cap']['preamble_coll']},{r['with_cap']['captures']}\n")

print(f"\n✅ Summary report saved to: {txt_path}")
print(f"✅ CSV data saved to: {csv_path}")

# Plotting figures
nodes_list = [r["nodes"] for r in results]
with_prrs = [r["with_cap"]["p1_prr"] for r in results]
no_prrs = [r["no_cap"]["p1_prr"] for r in results]

# Figure 1: PRR Comparison Curve
fig, ax = plt.subplots(figsize=(10, 6))
ax.plot(nodes_list, with_prrs, marker='s', markersize=8, linewidth=2.5, color='#1f77b4', label='Sidelink S-SPS (Capture Enabled, +6.0 dB)')
ax.plot(nodes_list, no_prrs, marker='x', markersize=8, linewidth=2.5, color='#d62728', linestyle='--', label='Sidelink S-SPS (No Capture / Disabled)')

for i, n in enumerate(nodes_list):
    ax.annotate(f"{with_prrs[i]:.1f}%", (n, with_prrs[i]), textcoords="offset points", xytext=(0, 10), ha='center', fontsize=9, fontweight='bold', color='#1f77b4')
    ax.annotate(f"{no_prrs[i]:.1f}%", (n, no_prrs[i]), textcoords="offset points", xytext=(0, -15), ha='center', fontsize=9, fontweight='bold', color='#d62728')

ax.set_title('Sidelink S-SPS PRR: Capture Enabled (+6dB) vs Capture Disabled (50–150 UAVs)', fontsize=14, fontweight='bold')
ax.set_xlabel('Swarm Scale (Number of UAVs in 200m x 200m x 80m)', fontsize=12, fontweight='bold')
ax.set_ylabel('Phase 1 Delivery PRR (%)', fontsize=12, fontweight='bold')
ax.set_xticks(nodes_list)
ax.set_ylim(min(min(with_prrs), min(no_prrs)) - 8, 102)
ax.grid(True, linestyle='--', alpha=0.6)
ax.legend(loc='lower left', fontsize=11, framealpha=0.9)

plt.tight_layout()
fig1_path = os.path.join(PROJECT_DIR, "exp_sidelink_capture_comparison_prr.png")
plt.savefig(fig1_path, dpi=300)
plt.close()
print(f"✅ PRR plot saved to: {fig1_path}")

# Figure 2: Dashboard
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 9), sharex=True)

# Top: PRR
ax1.plot(nodes_list, with_prrs, marker='s', markersize=7, linewidth=2.2, color='#1f77b4', label='Capture Enabled (+6dB)')
ax1.plot(nodes_list, no_prrs, marker='x', markersize=7, linewidth=2.2, color='#d62728', linestyle='--', label='Capture Disabled')
ax1.set_ylabel('Phase 1 PRR (%)', fontsize=11, fontweight='bold')
ax1.set_ylim(min(min(with_prrs), min(no_prrs)) - 8, 102)
ax1.grid(True, linestyle='--', alpha=0.6)
ax1.legend(loc='lower left', fontsize=10)
ax1.set_title('Sidelink S-SPS Sensitivity to Physical Power Capture Effect', fontsize=13, fontweight='bold')

# Bottom: Captures & Collision Delta
ax2_r = ax2.twinx()
width = 3.5
x_pos = [n for n in nodes_list]
capt_list = [r["with_cap"]["captures"] for r in results]
diff_prrs = [r["diff"] for r in results]

b1 = ax2.bar(x_pos, diff_prrs, width=width, color='#2ca02c', alpha=0.75, label='Δ PRR Gain from Capture (%)')
l1 = ax2_r.plot(x_pos, capt_list, marker='^', markersize=7, color='#ff7f0e', linewidth=2.0, label='Capture Events Count')

ax2.set_xlabel('Swarm Scale (Number of UAVs)', fontsize=11, fontweight='bold')
ax2.set_ylabel('Capture Gain Δ PRR (%)', fontsize=11, fontweight='bold', color='#2ca02c')
ax2_r.set_ylabel('Total Capture Events', fontsize=11, fontweight='bold', color='#ff7f0e')
ax2.grid(True, linestyle='--', alpha=0.6)

plt.tight_layout()
fig2_path = os.path.join(PROJECT_DIR, "exp_sidelink_capture_comparison_dashboard.png")
plt.savefig(fig2_path, dpi=300)
plt.close()
print(f"✅ Dashboard plot saved to: {fig2_path}")

print("📤 Auto-uploading results to GitHub...")
try:
    subprocess.run("git add exp_sidelink_capture_comparison* && git commit -m 'data: upload Sidelink capture comparison benchmark results' && git push origin main", shell=True, cwd=PROJECT_DIR)
except Exception as e:
    print(f"Notice on auto-push: {e}")

print("\n🎉 Sidelink Capture Comparison Benchmark Completed Successfully!")
