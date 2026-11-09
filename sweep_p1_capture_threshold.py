#!/usr/bin/env python3
"""
Phase 1 Capture / Demodulation Threshold Sensitivity Sweep
Investigates the impact of SINR Capture Demodulation Threshold on Phase 1 PRR:
- Sweep Range: -5.0 dB (Original 802.15.4 DSSS demodulation), -3.0 dB, 0.0 dB, +3.0 dB (Original PHY Margin), +6.0 dB (Strict BLE 5.4 C/I)
- Swarm Scale: 150 UAVs in 200m x 200m x 80m
- Phase 1 Duration: 10.0 ms (100 µs Micro-Slot Sidelink S-SPS)
- Evaluates: P1 PRR (%), Physical Capture Events, and Exact Drop Breakdown
"""

import subprocess
import os
import sys
import re
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

print("==========================================================================================")
print("🎯 PHASE 1 CAPTURE THRESHOLD SENSITIVITY BENCHMARK (-5.0 dB to +6.0 dB) 🎯")
print("==========================================================================================")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
NS3_DIR = os.path.expanduser("~/ns-3-dev")
if not os.path.exists(NS3_DIR):
    NS3_DIR = PROJECT_DIR

# Sync latest files to ns-3 directory if needed
files_to_sync = ["scratch/lr-wpan-swarm.cc", "src/lr-wpan/model/lr-wpan-phy.cc"]
for rel_path in files_to_sync:
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

num_nodes = int(sys.argv[1]) if len(sys.argv) > 1 else 150
p1_duration = 10.0
p1_slot_us = 100.0
sim_time = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0

# Thresholds to test: covers original -5dB, 0dB, original PHY 3dB, and strict 6dB
thresholds = [-5.0, -3.0, 0.0, 3.0, 6.0]

print(f"• UAV Swarm Scale        : {num_nodes} UAVs")
print(f"• Phase 1 Broadcast Win  : {p1_duration:.1f} ms ({p1_slot_us:.0f} µs Micro-Slot, 98 slots)")
print(f"• Thresholds to Test     : {thresholds} dB")
print(f"• Airspace Dimensions    : 200m x 200m x 80m")
print(f"• Simulation Time        : {sim_time:.1f} s")
print("------------------------------------------------------------------------------------------\n")

results = []

for thresh in thresholds:
    print(f"▶️ Testing SINR Capture Threshold: {thresh:+.1f} dB ...", end="", flush=True)

    # Clean old report files
    for fname in ["p1_ground_truth_report.txt", "p2_ground_truth_report.txt", "run.log", "metrics.txt"]:
        fpath = os.path.join(NS3_DIR, fname)
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
            except Exception:
                pass

    cmd = [
        "./ns3", "run",
        f"scratch/lr-wpan-swarm --numNodes={num_nodes} --p1Duration={p1_duration} "
        f"--p2Duration=10.0 --dataSlotUs=1000.0 --numChannels=6 "
        f"--simTime={sim_time} --spaceSize=200.0 --spaceZ=80.0 "
        f"--p1TxPower=0 --p2TxPower=-2 --p1CcaThresholdDbm=-96.58 --nodeSpeed=10.0 "
        f"--enableP1Sidelink=true --p1SlotUs={p1_slot_us} "
        f"--p1CaptureThresholdDb={thresh} --autoPush=false"
    ]

    try:
        proc = subprocess.run(cmd, cwd=NS3_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=300)
        out = proc.stdout
    except subprocess.TimeoutExpired:
        print(" ⚠️ Timed out after 300s!")
        continue

    # Read P1 ground truth report
    p1_path = os.path.join(NS3_DIR, "p1_ground_truth_report.txt")
    p1_text = ""
    if os.path.exists(p1_path):
        with open(p1_path, "r", encoding="utf-8") as f:
            p1_text = f.read()

    # Parse metrics
    m_p1_links = re.search(r"Total Expected P1 Neighbor Links.*:\s*(\d+)", p1_text)
    m_p1_succ = re.search(r"1\.\s+SUCCESS.*:\s*(\d+)\s*\(([\d\.]+)%\)", p1_text)
    m_p1_fail = re.search(r"TOTAL DROPPED / MISSED LINKS.*:\s*(\d+)\s*\(([\d\.]+)%\)", p1_text)
    m_p1_capt = re.search(r"Total Power Capture Events Triggered\s*:\s*(\d+)", p1_text)
    m_p1_low_sinr = re.search(r"PREAMBLE_LOW_SINR.*:\s*(\d+)", p1_text)
    m_p1_coll = re.search(r"PREAMBLE_COLLISION_BUSY_RX.*:\s*(\d+)", p1_text)
    m_p1_deaf = re.search(r"RX_DEAFNESS_BUSY_TX.*:\s*(\d+)", p1_text)

    links = int(m_p1_links.group(1)) if m_p1_links else 0
    succ = int(m_p1_succ.group(1)) if m_p1_succ else 0
    prr = float(m_p1_succ.group(2)) if m_p1_succ else 0.0
    capt = int(m_p1_capt.group(1)) if m_p1_capt else 0
    low_sinr = int(m_p1_low_sinr.group(1)) if m_p1_low_sinr else 0
    coll = int(m_p1_coll.group(1)) if m_p1_coll else 0
    deaf = int(m_p1_deaf.group(1)) if m_p1_deaf else 0

    note = ""
    if thresh == -5.0:
        note = "Original IEEE 802.15.4 DSSS demodulation floor"
    elif thresh == 0.0:
        note = "Equal Power (0 dB) boundary"
    elif thresh == 3.0:
        note = "Original ns-3 PHY Capture Margin (+3.0 dB)"
    elif thresh == 6.0:
        note = "Strict Bluetooth 5.4 LE 2M C/I (+6.0 dB)"

    results.append({
        "threshold": thresh,
        "links": links,
        "succ": succ,
        "prr": prr,
        "capt": capt,
        "low_sinr": low_sinr,
        "coll": coll,
        "deaf": deaf,
        "note": note
    })

    print(f" => P1 PRR: {prr:.1f}%, Capture Events: {capt:,}, Low SINR Drops: {low_sinr:,}")

# Print Table
print("\n" + "=" * 105)
print("📊 PHASE 1 CAPTURE / DEMODULATION THRESHOLD EXPERIMENT SUMMARY TABLE 📊")
print("=" * 105)
print(f"| {'Threshold (dB)':^14} | {'P1 PRR (%)':^12} | {'Delivered':^11} | {'Captures':^12} | {'Low SINR Drops':^16} | {'Description / Physical Meaning':^30} |")
print("|" + "-" * 16 + "|" + "-" * 14 + "|" + "-" * 13 + "|" + "-" * 14 + "|" + "-" * 18 + "|" + "-" * 32 + "|")
for r in results:
    print(f"| {r['threshold']:>+12.1f} dB | {r['prr']:>10.1f}% | {r['succ']:>11,} | {r['capt']:>12,} | {r['low_sinr']:>16,} | {r['note']:<30} |")
print("=" * 105)

# Save text summary
summary_path = os.path.join(PROJECT_DIR, "exp_p1_capture_threshold_results.txt")
with open(summary_path, "w", encoding="utf-8") as f:
    f.write("# Phase 1 Capture / Demodulation Threshold Sensitivity Benchmark\n")
    f.write(f"- Swarm Scale: {num_nodes} UAVs in 200m x 200m x 80m\n")
    f.write(f"- Phase 1 Window: {p1_duration:.1f} ms ({p1_slot_us:.0f} µs Micro-Slot, 98 slots)\n\n")
    f.write(f"| Threshold (dB) | P1 PRR (%) | Delivered | Captures | Low SINR Drops | Physical Meaning |\n")
    f.write(f"| :--- | :--- | :--- | :--- | :--- | :--- |\n")
    for r in results:
        f.write(f"| {r['threshold']:+.1f} dB | {r['prr']:.1f}% | {r['succ']} | {r['capt']} | {r['low_sinr']} | {r['note']} |\n")

print(f"\n✅ Summary report saved to: {summary_path}")

# Plot figures if results exist
if results:
    xs = [r['threshold'] for r in results]
    prrs = [r['prr'] for r in results]
    capts = [r['capt'] for r in results]
    low_sinrs = [r['low_sinr'] for r in results]

    # Figure 1: Focused PRR Curve
    fig, ax1 = plt.subplots(figsize=(9, 5.5))
    ax1.plot(xs, prrs, marker='o', linewidth=2.5, markersize=8, color='#1f77b4', label='Phase 1 PRR (%)')
    ax1.set_xlabel('SINR Capture Demodulation Threshold (dB)', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Phase 1 Delivery PRR (%)', fontsize=12, fontweight='bold', color='#1f77b4')
    ax1.tick_params(axis='y', labelcolor='#1f77b4')
    ax1.set_ylim(min(prrs) - 5, max(prrs) + 5)
    ax1.grid(True, linestyle='--', alpha=0.6)

    # Annotations
    for r in results:
        ax1.annotate(f"{r['prr']:.1f}%", (r['threshold'], r['prr']),
                     textcoords="offset points", xytext=(0, 10), ha='center',
                     fontsize=10, fontweight='bold', color='#1f77b4')

    ax1.set_title(f'Phase 1 PRR vs SINR Capture Threshold (150 UAVs, 10ms Window)', fontsize=14, fontweight='bold')
    plt.tight_layout()
    prr_fig_path = os.path.join(PROJECT_DIR, "exp_p1_capture_threshold_prr.png")
    plt.savefig(prr_fig_path, dpi=300)
    plt.close()
    print(f"✅ PRR plot saved to: {prr_fig_path}")

    # Figure 2: Dual-Panel Dashboard
    fig, (ax_top, ax_bot) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

    # Top: PRR and Captures
    ax_top.plot(xs, prrs, marker='s', linewidth=2.5, color='#2ca02c', label='P1 PRR (%)')
    ax_top.set_ylabel('Phase 1 PRR (%)', fontsize=11, fontweight='bold', color='#2ca02c')
    ax_top.tick_params(axis='y', labelcolor='#2ca02c')
    ax_top.grid(True, linestyle='--', alpha=0.6)
    ax_top.set_title('Impact of SINR Capture Demodulation Threshold on Swarm Reception (150 UAVs)', fontsize=13, fontweight='bold')

    ax_top_r = ax_top.twinx()
    ax_top_r.plot(xs, capts, marker='^', linewidth=2.0, linestyle='--', color='#ff7f0e', label='Capture Events')
    ax_top_r.set_ylabel('Power Capture Events', fontsize=11, fontweight='bold', color='#ff7f0e')
    ax_top_r.tick_params(axis='y', labelcolor='#ff7f0e')

    # Bottom: Drops
    ax_bot.bar(xs, low_sinrs, width=0.8, color='#d62728', alpha=0.75, label='Low SINR Rejections')
    ax_bot.set_xlabel('SINR Capture Threshold (dB)', fontsize=11, fontweight='bold')
    ax_bot.set_ylabel('Rejected Links (Drops)', fontsize=11, fontweight='bold', color='#d62728')
    ax_bot.grid(True, linestyle='--', alpha=0.6)
    ax_bot.legend(loc='upper left')

    plt.tight_layout()
    dash_fig_path = os.path.join(PROJECT_DIR, "exp_p1_capture_threshold_dashboard.png")
    plt.savefig(dash_fig_path, dpi=300)
    plt.close()
    print(f"✅ Dashboard plot saved to: {dash_fig_path}")

print("📤 Pushing benchmark results and plots to GitHub...")
try:
    subprocess.run("git add exp_p1_capture_threshold* && git commit -m 'data: update P1 capture threshold benchmark results and plots' && git push origin main", shell=True, cwd=PROJECT_DIR)
except Exception as e:
    print(f"Notice on auto-push: {e}")

print("\n🎉 Benchmark Completed Successfully!")
