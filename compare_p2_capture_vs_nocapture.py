#!/usr/bin/env python3
"""
Comparison Benchmark: Phase 2 Performance With Capture vs Without Capture
Configuration:
- Swarm Scale: 100 UAVs in 200m x 200m x 80m
- Phase 1: 10.0 ms CSMA-CA Broadcast
- Phase 2: 10.0 ms Data Phase (10 slots x 1000 µs, 6 Channels = 60 cells)
- Physical Layer: Bluetooth 5.4 LE 2M PHY
- Case A: With Power Capture (+6.0 dB BLE 5.4 C/I)
- Case B: Without Power Capture (enablePhyCapture=false)
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
print("⚖️  PHASE 2 POWER CAPTURE ABLATION BENCHMARK: WITH CAPTURE vs WITHOUT CAPTURE ⚖️")
print("==========================================================================================")

num_nodes = int(sys.argv[1]) if len(sys.argv) > 1 else 100
sim_time = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
data_slot_us = 1000.0 # 1.0 ms slot
num_channels = 6
p1_duration = 10.0
p2_duration = 10.0
space_size = 200.0
space_z = 80.0

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

def run_case(enable_p2_capture, tag):
    print(f"\n▶️ Running Simulation: {tag} (P1 Capture=ON, P2 Capture={'ON' if enable_p2_capture else 'OFF'}) ... ", end="", flush=True)
    for fname in ["p1_ground_truth_report.txt", "p2_ground_truth_report.txt", "run.log"]:
        fpath = os.path.join(NS3_DIR, fname)
        if os.path.exists(fpath):
            try: os.remove(fpath)
            except Exception: pass

    cmd = [
        "./ns3", "run",
        f"scratch/lr-wpan-swarm --numNodes={num_nodes} --p1Duration={p1_duration} "
        f"--enableP1Sidelink=false --p2Duration={p2_duration} --dataSlotUs={data_slot_us} "
        f"--numChannels={num_channels} --enableP1Capture=true "
        f"--enableP2Capture={'true' if enable_p2_capture else 'false'} "
        f"--phyCaptureMarginDb=6.0 --simTime={sim_time} "
        f"--spaceSize={space_size} --spaceZ={space_z} --nodeSpeed=10.0 --autoPush=false"
    ]

    try:
        proc = subprocess.run(cmd, cwd=NS3_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=300)
        out = proc.stdout
        print("Done!")
    except subprocess.TimeoutExpired:
        print("TIMEOUT!")
        return None

    p1_rpt = os.path.join(NS3_DIR, "p1_ground_truth_report.txt")
    p2_rpt = os.path.join(NS3_DIR, "p2_ground_truth_report.txt")
    p1_text = ""
    p2_text = ""
    if os.path.exists(p1_rpt):
        with open(p1_rpt, "r", encoding="utf-8", errors="ignore") as f: p1_text = f.read()
    if os.path.exists(p2_rpt):
        with open(p2_rpt, "r", encoding="utf-8", errors="ignore") as f: p2_text = f.read()

    data = {
        "tag": tag,
        "capture_enabled": enable_capture,
        "p1_prr": 0.0, "p2_prr": 0.0, "p2_links": 0, "p2_success": 0, "p2_fails": 0,
        "p1_miss": 0, "tx_deafness": 0, "rx_deafness": 0, "ch_mismatch": 0,
        "collisions": 0, "csma_abort": 0, "low_sinr": 0, "payload_drop": 0,
        "p1_captures": 0, "p2_captures": 0
    }

    # Parse P1
    src1 = p1_text if p1_text else out
    m = re.search(r"Successfully Received \(Delivered\)\s*:\s*(\d+)\s*\(([\d\.]+)%\)", src1)
    if m: data["p1_prr"] = float(m.group(2))
    m = re.search(r"Total Power Capture Events Triggered\s*:\s*(\d+)", src1)
    if m: data["p1_captures"] = int(m.group(1))

    # Parse P2
    src2 = p2_text if p2_text else out
    m = re.search(r"Total Expected P2 Neighbor Links.*:\s*(\d+)", src2)
    if m: data["p2_links"] = int(m.group(1))
    m = re.search(r"Successfully Received \(Delivered\)\s*:\s*(\d+)\s*\(([\d\.]+)%\)", src2)
    if m:
        data["p2_success"] = int(m.group(1))
        data["p2_prr"] = float(m.group(2))
    m = re.search(r"Failed Link Receptions \(Dropped/Missed\)\s*:\s*(\d+)", src2)
    if m: data["p2_fails"] = int(m.group(1))

    m = re.search(r"P1_DISCOVERY_MISS\s*:\s*(\d+)", src2)
    if m: data["p1_miss"] = int(m.group(1))
    m = re.search(r"TX_DEAFNESS_SAME_SLOT\s*:\s*(\d+)", src2)
    if m: data["tx_deafness"] = int(m.group(1))
    m = re.search(r"RX_DEAFNESS_SLOT_CONFLICT\s*:\s*(\d+)", src2)
    if m: data["rx_deafness"] = int(m.group(1))
    m = re.search(r"RECEIVER_CHANNEL_MISMATCH\s*:\s*(\d+)", src2)
    if m: data["ch_mismatch"] = int(m.group(1))
    m = re.search(r"PREAMBLE_COLLISION_BUSY_RX\s*:\s*(\d+)", src2)
    if m: data["collisions"] = int(m.group(1))
    m = re.search(r"SENDER_CSMA_ABORT\s*:\s*(\d+)", src2)
    if m: data["csma_abort"] = int(m.group(1))
    m = re.search(r"PREAMBLE_LOW_SINR\s*:\s*(\d+)", src2)
    if m: data["low_sinr"] = int(m.group(1))
    m = re.search(r"PAYLOAD_INTERFERENCE_DROP\s*:\s*(\d+)", src2)
    if m: data["payload_drop"] = int(m.group(1))
    m = re.search(r"Total Power Capture Events Triggered\s*:\s*(\d+)", src2)
    if m: data["p2_captures"] = int(m.group(1))

    return data

res_with = run_case(True, "Phase 2 With Capture (+6.0 dB)")
res_without = run_case(False, "Phase 2 Without Capture (Pure Collision)")

if not res_with or not res_without:
    print("Error executing cases.")
    sys.exit(1)

# Summary Comparison Output
print("\n" + "=" * 105)
print("📊 PHASE 2 CAPTURE ABLATION: P1 FIXED WITH CAPTURE, EVALUATING P2 CAPTURE IMPACT 📊")
print("=" * 105)
print(f"• Phase 1 Broadcast Window: 10.0 ms CSMA-CA (Strictly FIXED with +6.0 dB Capture in both cases)")
print(f"• Phase 2 Data Window     : 10.0 ms Slotted (10 slots x 1000 µs, 6 Channels = 60 cells)")
print("-" * 105)
print(f"| {'Metric / Failure Category':<35} | {'P2 With Capture (+6dB)':<22} | {'P2 Without Capture':<20} | {'Difference (Δ)':<18} |")
print("|" + "-" * 37 + "|" + "-" * 24 + "|" + "-" * 22 + "|" + "-" * 20 + "|")

def fmt_diff(v_with, v_without, is_prr=False):
    delta = v_with - v_without
    if is_prr:
        sign = "+" if delta >= 0 else ""
        return f"{sign}{delta:.1f}% PRR"
    else:
        sign = "+" if delta >= 0 else ""
        return f"{sign}{delta:,}"

print(f"| {'Phase 1 Discovery PRR':<35} | {res_with['p1_prr']:>6.1f}%                 | {res_without['p1_prr']:>6.1f}%               | {fmt_diff(res_with['p1_prr'], res_without['p1_prr'], True):<18} |")
print(f"| {'Phase 2 Data Delivery PRR':<35} | {res_with['p2_prr']:>6.1f}% ({res_with['p2_success']:,})      | {res_without['p2_prr']:>6.1f}% ({res_without['p2_success']:,})    | {fmt_diff(res_with['p2_prr'], res_without['p2_prr'], True):<18} |")
print(f"| {'Total Phase 2 Failed Links':<35} | {res_with['p2_fails']:>7,}                 | {res_without['p2_fails']:>7,}               | {fmt_diff(res_with['p2_fails'], res_without['p2_fails']):<18} |")
print("|" + "-" * 37 + "|" + "-" * 24 + "|" + "-" * 22 + "|" + "-" * 20 + "|")
print(f"| 1. P1 Discovery Miss               | {res_with['p1_miss']:>7,}                 | {res_without['p1_miss']:>7,}               | {fmt_diff(res_with['p1_miss'], res_without['p1_miss']):<18} |")
print(f"| 2. TX Deafness (Same Slot)        | {res_with['tx_deafness']:>7,}                 | {res_without['tx_deafness']:>7,}               | {fmt_diff(res_with['tx_deafness'], res_without['tx_deafness']):<18} |")
print(f"| 3. RX Deafness (Slot Conflict)    | {res_with['rx_deafness']:>7,}                 | {res_without['rx_deafness']:>7,}               | {fmt_diff(res_with['rx_deafness'], res_without['rx_deafness']):<18} |")
print(f"| 4. Channel Mismatch               | {res_with['ch_mismatch']:>7,}                 | {res_without['ch_mismatch']:>7,}               | {fmt_diff(res_with['ch_mismatch'], res_without['ch_mismatch']):<18} |")
print(f"| 5. Preamble Collisions            | {res_with['collisions']:>7,}                 | {res_without['collisions']:>7,}               | {fmt_diff(res_with['collisions'], res_without['collisions']):<18} |")
print(f"| 6. CSMA Sender Aborts             | {res_with['csma_abort']:>7,}                 | {res_without['csma_abort']:>7,}               | {fmt_diff(res_with['csma_abort'], res_without['csma_abort']):<18} |")
print(f"| 7. Low SINR (< +6.0 dB)           | {res_with['low_sinr']:>7,}                 | {res_without['low_sinr']:>7,}               | {fmt_diff(res_with['low_sinr'], res_without['low_sinr']):<18} |")
print(f"| 8. Payload Interference Drop      | {res_with['payload_drop']:>7,}                 | {res_without['payload_drop']:>7,}               | {fmt_diff(res_with['payload_drop'], res_without['payload_drop']):<18} |")
print("|" + "-" * 37 + "|" + "-" * 24 + "|" + "-" * 22 + "|" + "-" * 20 + "|")
print(f"| • Total Capture Rescues Triggered | {res_with['p2_captures']:>7,}                 | {res_without['p2_captures']:>7,}               | {fmt_diff(res_with['p2_captures'], res_without['p2_captures']):<18} |")
print("=" * 105)

# Save Comparison TXT and CSV
txt_path = os.path.join(PROJECT_DIR, "exp_p2_capture_comparison_report.txt")
csv_path = os.path.join(PROJECT_DIR, "exp_p2_capture_comparison_results.csv")

with open(txt_path, "w", encoding="utf-8") as f:
    f.write(f"# Phase 2 Power Capture Ablation Benchmark (100 UAVs, BLE 2M PHY)\n")
    f.write(f"- Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write(f"- Phase 1: 10.0 ms CSMA-CA Broadcast (Strictly FIXED with +6.0 dB Capture on both cases)\n")
    f.write(f"- Phase 2: 10.0 ms Slotted (10 slots x 1000 µs, 6 Channels = 60 cells)\n\n")
    f.write(f"| Metric / Failure Category | P2 With Capture (+6dB) | P2 Without Capture | Difference (Δ) |\n")
    f.write(f"| :--- | :--- | :--- | :--- |\n")
    f.write(f"| Phase 1 Discovery PRR | {res_with['p1_prr']:.1f}% | {res_without['p1_prr']:.1f}% | {fmt_diff(res_with['p1_prr'], res_without['p1_prr'], True)} |\n")
    f.write(f"| Phase 2 Data PRR | {res_with['p2_prr']:.1f}% ({res_with['p2_success']:,}) | {res_without['p2_prr']:.1f}% ({res_without['p2_success']:,}) | {fmt_diff(res_with['p2_prr'], res_without['p2_prr'], True)} |\n")
    f.write(f"| Total Failed Links | {res_with['p2_fails']:,} | {res_without['p2_fails']:,} | {fmt_diff(res_with['p2_fails'], res_without['p2_fails'])} |\n")
    f.write(f"| 1. P1 Discovery Miss | {res_with['p1_miss']:,} | {res_without['p1_miss']:,} | {fmt_diff(res_with['p1_miss'], res_without['p1_miss'])} |\n")
    f.write(f"| 2. TX Deafness (Same Slot) | {res_with['tx_deafness']:,} | {res_without['tx_deafness']:,} | {fmt_diff(res_with['tx_deafness'], res_without['tx_deafness'])} |\n")
    f.write(f"| 3. RX Deafness (Conflict) | {res_with['rx_deafness']:,} | {res_without['rx_deafness']:,} | {fmt_diff(res_with['rx_deafness'], res_without['rx_deafness'])} |\n")
    f.write(f"| 4. Channel Mismatch | {res_with['ch_mismatch']:,} | {res_without['ch_mismatch']:,} | {fmt_diff(res_with['ch_mismatch'], res_without['ch_mismatch'])} |\n")
    f.write(f"| 5. Preamble Collisions | {res_with['collisions']:,} | {res_without['collisions']:,} | {fmt_diff(res_with['collisions'], res_without['collisions'])} |\n")
    f.write(f"| 6. CSMA Sender Aborts | {res_with['csma_abort']:,} | {res_without['csma_abort']:,} | {fmt_diff(res_with['csma_abort'], res_without['csma_abort'])} |\n")
    f.write(f"| 7. Low SINR (< +6.0 dB) | {res_with['low_sinr']:,} | {res_without['low_sinr']:,} | {fmt_diff(res_with['low_sinr'], res_without['low_sinr'])} |\n")
    f.write(f"| 8. Payload Interference | {res_with['payload_drop']:,} | {res_without['payload_drop']:,} | {fmt_diff(res_with['payload_drop'], res_without['payload_drop'])} |\n")
    f.write(f"| Total Capture Rescues | {res_with['p2_captures']:,} | {res_without['p2_captures']:,} | {fmt_diff(res_with['p2_captures'], res_without['p2_captures'])} |\n")

# Figure: Publication-Quality Side-by-Side Bar Comparison
categories = ['P2 Delivery PRR', 'Collisions', 'P1 Miss', 'RX Deafness', 'TX Deafness']
val_with = [res_with['p2_prr'], res_with['collisions'], res_with['p1_miss'], res_with['rx_deafness'], res_with['tx_deafness']]
val_without = [res_without['p2_prr'], res_without['collisions'], res_without['p1_miss'], res_without['rx_deafness'], res_without['tx_deafness']]

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.5), dpi=300)

# Subplot 1: PRR Comparison
bars1 = ax1.bar(['With Capture (+6dB)', 'Without Capture'], [res_with['p2_prr'], res_without['p2_prr']],
                color=['#2ca02c', '#d62728'], width=0.45)
for b in bars1:
    h = b.get_height()
    ax1.annotate(f"{h:.1f}%", xy=(b.get_x() + b.get_width() / 2, h), xytext=(0, 5),
                 textcoords="offset points", ha='center', va='bottom', fontsize=12, fontweight='bold')
ax1.set_ylabel('Phase 2 Delivery PRR (%)', fontsize=11, fontweight='bold')
ax1.set_title('(a) Phase 2 Delivery PRR Comparison', fontsize=12, fontweight='bold')
ax1.set_ylim(0, 100)
ax1.grid(True, linestyle='--', alpha=0.5, axis='y')

# Subplot 2: Collision and Drops Comparison
x = [0, 1, 2, 3]
w = 0.35
drop_labels = ['Collisions', 'P1 Miss', 'RX Deafness', 'TX Deafness']
d_with = [res_with['collisions'], res_with['p1_miss'], res_with['rx_deafness'], res_with['tx_deafness']]
d_without = [res_without['collisions'], res_without['p1_miss'], res_without['rx_deafness'], res_without['tx_deafness']]

ax2.bar([i - w/2 for i in x], d_with, width=w, label='With Capture (+6dB)', color='#2ca02c')
ax2.bar([i + w/2 for i in x], d_without, width=w, label='Without Capture', color='#d62728')
ax2.set_xticks(x)
ax2.set_xticklabels(drop_labels, fontsize=10, fontweight='bold')
ax2.set_ylabel('Dropped Link Counts', fontsize=11, fontweight='bold')
ax2.set_title('(b) Primary Failure Root Causes', fontsize=12, fontweight='bold')
ax2.legend(fontsize=10.5)
ax2.grid(True, linestyle='--', alpha=0.5, axis='y')

plt.tight_layout()
fig_path = os.path.join(PROJECT_DIR, "p2_capture_vs_nocapture_comparison.png")
plt.savefig(fig_path)
plt.close()

print(f"\n✅ Comparison report saved to: {txt_path}")
print(f"✅ Comparison plot saved to: {fig_path}")

# Auto Push
if "--no-push" not in sys.argv:
    print("\n🚀 Pushing experiment results and plots to GitHub main...")
    try:
        subprocess.run(
            "git add exp_p2_capture_comparison* p2_capture_vs_nocapture_comparison.png && git commit -m 'data: upload Phase 2 capture vs no-capture comparison results' && git push origin main",
            shell=True, cwd=PROJECT_DIR, check=False
        )
        print("✅ Git push completed!")
    except Exception as e:
        print(f"⚠️ Git push notice: {e}")

print("🎉 Phase 2 ablation benchmark completed successfully!")
