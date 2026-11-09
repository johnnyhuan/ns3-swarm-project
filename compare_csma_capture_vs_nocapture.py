#!/usr/bin/env python3
"""
CSMA-CA Capture Effect Benchmark: With Capture vs Without Capture (50 to 150 UAVs)
Specifically investigates the impact of Physical Layer RF Capture Effect on CSMA-CA.
- Condition 1: CSMA-CA With Capture (enableCapture=true, CaptureMargin=6.0 dB)
- Condition 2: CSMA-CA Without Capture (enableCapture=false, Pure Collision Model)
- Swarm Scale: 50 to 150 UAVs (step 10, 11 continuous points)
- Phase 1 Window: 10.0 ms
- Evaluates: PRR (%), Collisions, Aborts, Capture Rescues, and Capture Gain
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
print("🚀 CSMA-CA CAPTURE EFFECT BENCHMARK: WITH CAPTURE vs WITHOUT CAPTURE (50-150 UAVs) 🚀")
print("==========================================================================================")

sim_time = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
p1_duration = 10.0
capture_margin_db = 6.0
space_size = 200.0
space_z = 80.0

# 50 to 150 UAVs in increments of 10
node_counts = list(range(50, 151, 10))

print(f"• Evaluated Scheme       : CSMA-CA Baseline (Continuous Random Delay + CCA)")
print(f"• UAV Swarm Scale Points : {node_counts} UAVs (11 points)")
print(f"• Phase 1 Broadcast Win  : {p1_duration:.1f} ms")
print(f"• Capture Margin (When ON: +{capture_margin_db:.1f} dB (Strict BLE 5.4 C/I)")
print(f"• Airspace Dimensions    : {space_size:.0f}m x {space_size:.0f}m x {space_z:.0f}m")
print(f"• Simulation Time        : {sim_time:.1f} s per run")
print("------------------------------------------------------------------------------------------\n")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
NS3_DIR = os.path.expanduser("~/ns-3-dev")
if not os.path.exists(NS3_DIR):
    NS3_DIR = PROJECT_DIR

# Sync latest files to ns-3 directory
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

def run_simulation(nodes, enable_capture):
    for fname in ["p1_ground_truth_report.txt", "p2_ground_truth_report.txt", "run.log"]:
        fpath = os.path.join(NS3_DIR, fname)
        if os.path.exists(fpath):
            try: os.remove(fpath)
            except Exception: pass

    cmd = [
        "./ns3", "run",
        f"scratch/lr-wpan-swarm --numNodes={nodes} --p1Duration={p1_duration} "
        f"--simTime={sim_time} --spaceSize={space_size} --spaceZ={space_z} "
        f"--enableP1Sidelink=false --enableCapture={'true' if enable_capture else 'false'} "
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
        "links": 0, "succ": 0, "prr": 0.0, "p1_prr": 0.0, "fail": 0,
        "csma_abort": 0, "rx_deafness": 0, "preamble_coll": 0,
        "low_sinr": 0, "captures": 0
    }

    src = p1_text if p1_text else stdout_text

    m = re.search(r"Total Expected P1 Neighbor Links.*:\s*(\d+)", src)
    if m: data["links"] = int(m.group(1))

    m = re.search(r"Successfully Received \(Delivered\)\s*:\s*(\d+)\s*\(([\d\.]+)%\)", src)
    if m:
        data["succ"] = int(m.group(1))
        data["prr"] = float(m.group(2))
        data["p1_prr"] = float(m.group(2))

    m = re.search(r"Failed Link Receptions \(Dropped/Missed\)\s*:\s*(\d+)", src)
    if m: data["fail"] = int(m.group(1))

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

    # 1. CSMA-CA With Capture
    print(f"   [1/2] CSMA-CA With Capture (ON)    ... ", end="", flush=True)
    with_res = run_simulation(nodes, enable_capture=True)
    if with_res is not None:
        print(f"PRR: {with_res['p1_prr']:.1f}% | Coll: {with_res['preamble_coll']} | Aborts: {with_res['csma_abort']} | Captures: {with_res['captures']}")
    else:
        print(f"TIMEOUT / ERROR")

    # 2. CSMA-CA Without Capture
    print(f"   [2/2] CSMA-CA Without Capture (OFF) ... ", end="", flush=True)
    no_res = run_simulation(nodes, enable_capture=False)
    if no_res is not None:
        print(f"PRR: {no_res['p1_prr']:.1f}% | Coll: {no_res['preamble_coll']} | Aborts: {no_res['csma_abort']} | Captures: {no_res['captures']}")
    else:
        print("TIMEOUT / ERROR")

    if with_res is not None and no_res is not None:
        diff = with_res['p1_prr'] - no_res['p1_prr']
        print(f"   ==> Δ Capture Gain: {diff:+.2f}% PRR (Capture Benefit: {with_res['captures']} rescues)\n")
    else:
        diff = None
        print(f"   ==> Δ Capture Gain: N/A\n")

    results.append({
        "nodes": nodes,
        "with_cap": with_res,
        "no_cap": no_res,
        "diff": diff
    })

# Print Full Comparative Table
print("\n" + "=" * 125)
print("📊 CSMA-CA CAPTURE EFFECT BENCHMARK SUMMARY (50-150 UAVs: WITH CAPTURE vs WITHOUT CAPTURE) 📊")
print("=" * 125)
print(f"| {'Nodes':^7} | {'With Cap PRR':^14} | {'No Cap PRR':^14} | {'Δ Gain':^10} | {'With Coll':^11} | {'No Coll':^11} | {'Captures':^12} | {'Aborts':^10} | {'Capture Impact':^20} |")
print("|" + "-" * 9 + "|" + "-" * 16 + "|" + "-" * 16 + "|" + "-" * 12 + "|" + "-" * 13 + "|" + "-" * 13 + "|" + "-" * 14 + "|" + "-" * 12 + "|" + "-" * 22 + "|")

for r in results:
    nodes = r["nodes"]
    with_prr = f"{r['with_cap']['p1_prr']:.1f}%" if r["with_cap"] else "N/A"
    no_prr = f"{r['no_cap']['p1_prr']:.1f}%" if r["no_cap"] else "N/A"
    diff_str = f"{r['diff']:+6.2f}%" if r["diff"] is not None else "N/A"
    with_coll = f"{r['with_cap']['preamble_coll']:,}" if r["with_cap"] else "N/A"
    no_coll = f"{r['no_cap']['preamble_coll']:,}" if r["no_cap"] else "N/A"
    cap_count = f"{r['with_cap']['captures']:,}" if r["with_cap"] else "N/A"
    aborts = f"{r['with_cap']['csma_abort']:,}" if r["with_cap"] else "N/A"

    impact = "⚡ Significant Gain" if (r["diff"] is not None and r["diff"] > 1.0) else ("🔍 Minor Benefit" if (r["diff"] is not None and r["diff"] > 0) else "Neutral")
    print(f"| {nodes:^7} | {with_prr:^14} | {no_prr:^14} | {diff_str:^10} | {with_coll:^11} | {no_coll:^11} | {cap_count:^12} | {aborts:^10} | {impact:^20} |")

print("=" * 125)

# Save Text and CSV reports
txt_path = os.path.join(PROJECT_DIR, "exp_csma_capture_vs_nocapture_results.txt")
csv_path = os.path.join(PROJECT_DIR, "exp_csma_capture_vs_nocapture_results.csv")

with open(txt_path, "w", encoding="utf-8") as f:
    f.write("# CSMA-CA Capture Effect Benchmark: With Capture vs Without Capture (50 to 150 UAVs)\n")
    f.write(f"- Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write(f"- Phase 1 Duration: {p1_duration:.1f} ms\n")
    f.write(f"- Capture Margin: +{capture_margin_db:.1f} dB\n\n")
    f.write("| Nodes | With Capture PRR (%) | Without Capture PRR (%) | Δ Gain (%) | With Collisions | No Collisions | Captures | Aborts |\n")
    f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
    for r in results:
        f.write(f"| {r['nodes']} | {r['with_cap']['p1_prr']:.1f}% | {r['no_cap']['p1_prr']:.1f}% | {r['diff']:+.2f}% | {r['with_cap']['preamble_coll']} | {r['no_cap']['preamble_coll']} | {r['with_cap']['captures']} | {r['with_cap']['csma_abort']} |\n")

with open(csv_path, "w", encoding="utf-8") as f:
    f.write("Nodes,With_Capture_PRR,No_Capture_PRR,Delta_Gain,With_Collisions,No_Collisions,Captures,Aborts\n")
    for r in results:
        f.write(f"{r['nodes']},{r['with_cap']['p1_prr']:.2f},{r['no_cap']['p1_prr']:.2f},{r['diff']:.2f},{r['with_cap']['preamble_coll']},{r['no_cap']['preamble_coll']},{r['with_cap']['captures']},{r['with_cap']['csma_abort']}\n")

print(f"\n✅ Summary report saved to: {txt_path}")
print(f"✅ CSV data saved to: {csv_path}")

# Plotting publication-quality figures
nodes_list = [r["nodes"] for r in results]
with_prrs = [r["with_cap"]["p1_prr"] for r in results]
no_prrs = [r["no_cap"]["p1_prr"] for r in results]

# Figure 1: Clean Comparison Curve
fig, ax = plt.subplots(figsize=(10, 6))
ax.plot(nodes_list, with_prrs, marker='o', markersize=8, linewidth=2.5, color='#2ca02c', label='CSMA-CA (With Capture Event, Margin = 6.0 dB)')
ax.plot(nodes_list, no_prrs, marker='x', markersize=8, linewidth=2.5, color='#d62728', linestyle='--', label='CSMA-CA (Without Capture Event, Pure Collision)')

for i, n in enumerate(nodes_list):
    ax.annotate(f"{with_prrs[i]:.1f}%", (n, with_prrs[i]), textcoords="offset points", xytext=(0, 10), ha='center', fontsize=9, fontweight='bold', color='#2ca02c')
    ax.annotate(f"{no_prrs[i]:.1f}%", (n, no_prrs[i]), textcoords="offset points", xytext=(0, -15), ha='center', fontsize=9, fontweight='bold', color='#d62728')

ax.set_title('CSMA-CA Reception PRR: With Capture vs Without Capture (50–150 UAVs)', fontsize=14, fontweight='bold')
ax.set_xlabel('Swarm Scale (Number of UAVs in 200m x 200m x 80m)', fontsize=12, fontweight='bold')
ax.set_ylabel('Phase 1 Delivery PRR (%)', fontsize=12, fontweight='bold')
ax.set_xticks(nodes_list)
ax.set_ylim(min(min(with_prrs), min(no_prrs)) - 8, 102)
ax.grid(True, linestyle='--', alpha=0.6)
ax.legend(loc='lower left', fontsize=11, framealpha=0.9)

plt.tight_layout()
fig1_path = os.path.join(PROJECT_DIR, "exp_csma_capture_vs_nocapture_prr.png")
plt.savefig(fig1_path, dpi=300)
plt.close()
print(f"✅ PRR plot saved to: {fig1_path}")

# Figure 2: Comprehensive Multi-Panel Dashboard
fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(11, 12), sharex=True)

# Panel 1: PRR Curves
ax1.plot(nodes_list, with_prrs, marker='o', markersize=7, linewidth=2.2, color='#2ca02c', label='CSMA With Capture (6 dB)')
ax1.plot(nodes_list, no_prrs, marker='x', markersize=7, linewidth=2.2, color='#d62728', linestyle='--', label='CSMA Without Capture')
ax1.set_ylabel('Phase 1 PRR (%)', fontsize=11, fontweight='bold')
ax1.set_ylim(min(min(with_prrs), min(no_prrs)) - 8, 102)
ax1.grid(True, linestyle='--', alpha=0.6)
ax1.legend(loc='lower left', fontsize=10)
ax1.set_title('CSMA-CA Capture Effect In-Depth Analysis (50 to 150 UAVs)', fontsize=13, fontweight='bold')

# Panel 2: Collisions Comparison Bar Chart
with_colls = [r["with_cap"]["preamble_coll"] for r in results]
no_colls = [r["no_cap"]["preamble_coll"] for r in results]
width = 3.5
x_pos = [n for n in nodes_list]
ax2.bar([x - width/2 for x in x_pos], no_colls, width=width, color='#d62728', alpha=0.8, label='Without Capture Collisions (Higher Drops)')
ax2.bar([x + width/2 for x in x_pos], with_colls, width=width, color='#2ca02c', alpha=0.8, label='With Capture Collisions (Rescued by Capture)')
ax2.set_ylabel('Collision Drops', fontsize=11, fontweight='bold')
ax2.grid(True, linestyle='--', alpha=0.6)
ax2.legend(loc='upper left', fontsize=10)

# Panel 3: Captures Rescues
capt_list = [r["with_cap"]["captures"] for r in results]
ax3.plot(nodes_list, capt_list, marker='^', markersize=7, linewidth=2.0, color='#ff7f0e', label='Capture Rescues in CSMA (C/I $\ge$ 6.0 dB)')
ax3.set_xlabel('Swarm Scale (Number of UAVs)', fontsize=11, fontweight='bold')
ax3.set_ylabel('Capture Rescues', fontsize=11, fontweight='bold', color='#ff7f0e')
ax3.tick_params(axis='y', labelcolor='#ff7f0e')
ax3.grid(True, linestyle='--', alpha=0.6)
ax3.legend(loc='upper left', fontsize=10)

plt.tight_layout()
fig2_path = os.path.join(PROJECT_DIR, "exp_csma_capture_vs_nocapture_dashboard.png")
plt.savefig(fig2_path, dpi=300)
plt.close()
print(f"✅ Dashboard plot saved to: {fig2_path}")

print("📤 Uploading benchmark results to GitHub...")
try:
    subprocess.run("git add exp_csma_capture_vs_nocapture* && git commit -m 'data: upload CSMA capture vs nocapture benchmark results' && git push origin main", shell=True, cwd=PROJECT_DIR)
except Exception as e:
    print(f"Notice on auto-push: {e}")

print("\n🎉 CSMA Capture vs No-Capture Benchmark Completed Successfully!")
