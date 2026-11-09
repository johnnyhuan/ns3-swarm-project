#!/usr/bin/env python3
"""
Phase 1 (10ms Window) Slot Count Sweep: Finding the Optimal Slot Granularity
Evaluates Sidelink S-SPS performance across different slot counts (from 20 to 115 slots)
against CSMA-CA Baseline under 100 UAVs in 200m x 200m x 80m airspace.
Physical Layer: Bluetooth 5.4 LE 2M (+6.0 dB C/I Capture Threshold).
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
print("🔬 PHASE 1 (10ms WINDOW): OPTIMAL SLOT COUNT SWEEP AT 100 UAVs 🔬")
print("==========================================================================================")

sim_time = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
num_nodes = 100
p1_duration = 10.0
capture_thresh_db = 6.0
space_size = 200.0
space_z = 80.0

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
NS3_DIR = os.path.expanduser("~/ns-3-dev")
if not os.path.exists(NS3_DIR):
    NS3_DIR = PROJECT_DIR

# Sync updated files to NS3_DIR
sync_files = [
    "scratch/lr-wpan-swarm.cc",
    "src/lr-wpan/model/lr-wpan-phy.cc"
]
for rel_path in sync_files:
    src_f = os.path.join(PROJECT_DIR, rel_path)
    dst_f = os.path.join(NS3_DIR, rel_path)
    if os.path.exists(src_f) and os.path.abspath(src_f) != os.path.abspath(dst_f):
        try:
            os.makedirs(os.path.dirname(dst_f), exist_ok=True)
            subprocess.run(["cp", src_f, dst_f], check=True)
        except Exception:
            pass

# Slot width list to sweep (microseconds)
# Deep low-duration sweep: 100 µs down to 10 µs (98 slots up to 976 slots)
slot_configs = [
    (100.0, "98 slots (100 µs)"),
    (90.0,  "109 slots (90 µs)"),
    (85.0,  "115 slots (85 µs)"),
    (80.0,  "122 slots (80 µs)"),
    (75.0,  "131 slots (75 µs)"),
    (70.0,  "140 slots (70 µs)"),
    (65.0,  "151 slots (65 µs)"),
    (60.0,  "163 slots (60 µs)"),
    (50.0,  "196 slots (50 µs)"),
    (40.0,  "244 slots (40 µs)"),
    (30.0,  "326 slots (30 µs)"),
    (20.0,  "488 slots (20 µs)"),
    (10.0,  "976 slots (10 µs)")
]

def run_simulation(enable_sidelink, slot_us=100.0):
    for fname in ["p1_ground_truth_report.txt", "p2_ground_truth_report.txt", "run.log"]:
        fpath = os.path.join(NS3_DIR, fname)
        if os.path.exists(fpath):
            try: os.remove(fpath)
            except Exception: pass

    cmd = [
        "./ns3", "run",
        f"scratch/lr-wpan-swarm --numNodes={num_nodes} --p1Duration={p1_duration} "
        f"--simTime={sim_time} --spaceSize={space_size} --spaceZ={space_z} "
        f"--enableP1Sidelink={'true' if enable_sidelink else 'false'} "
        f"--p1SlotUs={slot_us} --p1CaptureThresholdDb={capture_thresh_db} "
        f"--phyCaptureMarginDb={capture_thresh_db} --autoPush=false"
    ]

    proc = subprocess.run(cmd, cwd=NS3_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=300)
    out = proc.stdout

    p1_rpt = os.path.join(NS3_DIR, "p1_ground_truth_report.txt")
    p1_text = ""
    if os.path.exists(p1_rpt):
        with open(p1_rpt, "r", encoding="utf-8", errors="ignore") as f:
            p1_text = f.read()

    return parse_report(p1_text if p1_text else out)

def parse_report(text):
    data = {
        "links": 0, "succ": 0, "prr": 0.0, "fail": 0,
        "csma_abort": 0, "rx_deafness": 0, "preamble_coll": 0,
        "low_sinr": 0, "captures": 0
    }
    m = re.search(r"Total Expected P1 Neighbor Links.*:\s*(\d+)", text)
    if m: data["links"] = int(m.group(1))

    m = re.search(r"Successfully Received \(Delivered\)\s*:\s*(\d+)\s*\(([\d\.]+)%\)", text)
    if m:
        data["succ"] = int(m.group(1))
        data["prr"] = float(m.group(2))

    m = re.search(r"Failed Link Receptions \(Dropped/Missed\)\s*:\s*(\d+)", text)
    if m: data["fail"] = int(m.group(1))

    m = re.search(r"SENDER_CSMA_ABORT\s*:\s*(\d+)", text)
    if m: data["csma_abort"] = int(m.group(1))

    m = re.search(r"RX_DEAFNESS_BUSY_TX\s*:\s*(\d+)", text)
    if m: data["rx_deafness"] = int(m.group(1))

    m = re.search(r"PREAMBLE_COLLISION_BUSY_RX\s*:\s*(\d+)", text)
    if m: data["preamble_coll"] = int(m.group(1))

    m = re.search(r"PREAMBLE_LOW_SINR\s*:\s*(\d+)", text)
    if m: data["low_sinr"] = int(m.group(1))

    m = re.search(r"Total Power Capture Events Triggered\s*:\s*(\d+)", text)
    if m: data["captures"] = int(m.group(1))

    return data

print("\n[Step 1/2] Running CSMA-CA Baseline (Continuous Random Backoff, No Slots)...")
csma_res = run_simulation(enable_sidelink=False)
print(f"  ==> CSMA-CA PRR: {csma_res['prr']:.1f}% ({csma_res['succ']}/{csma_res['links']}) | Aborts: {csma_res['csma_abort']} | Coll: {csma_res['preamble_coll']} | Captures: {csma_res['captures']}")

print("\n[Step 2/2] Sweeping Sidelink Slot Counts in 10ms Window (100 µs down to 10 µs)...")
sidelink_results = []
for slot_us, label in slot_configs:
    slots_cnt = max(1, int((p1_duration * 1000.0 - 250.0) / slot_us) + 1)
    density = num_nodes / slots_cnt
    print(f"  ▶️ Testing {label} (Slot {slot_us:.1f} µs, ~{density:.2f} UAVs/slot) ...", end="", flush=True)
    res = run_simulation(enable_sidelink=True, slot_us=slot_us)
    res["slot_us"] = slot_us
    res["slots_cnt"] = slots_cnt
    res["density"] = density
    sidelink_results.append(res)
    print(f" ==> PRR: {res['prr']:.1f}% | Deaf: {res['rx_deafness']} | Coll: {res['preamble_coll']} | Captures: {res['captures']}")

# Print Comparison Table
print("\n" + "=" * 115)
print(f"📊 PHASE 1 (10ms) SLOT COUNT SWEEP SUMMARY (100 UAVs, C/I >= +6.0 dB) 📊")
print("=" * 115)
print(f"{'Slot Width':<12} | {'Slots':<6} | {'UAVs/Slot':<10} | {'Sidelink PRR':<14} | {'CSMA Baseline':<14} | {'Δ vs CSMA':<12} | {'Deafness':<9} | {'Collisions':<11} | {'Captures':<9}")
print("-" * 115)

best_idx = 0
best_prr = -1.0
for i, r in enumerate(sidelink_results):
    if r['prr'] > best_prr:
        best_prr = r['prr']
        best_idx = i
    delta = r['prr'] - csma_res['prr']
    print(f"{r['slot_us']:<12.1f} | {r['slots_cnt']:<6} | {r['density']:<10.2f} | {r['prr']:<13.1f}% | {csma_res['prr']:<13.1f}% | {delta:+11.1f}% | {r['rx_deafness']:<9} | {r['preamble_coll']:<11} | {r['captures']:<9}")

best_slot = sidelink_results[best_idx]
print("=" * 115)
print(f"🏆 BEST SIDELINK CONFIGURATION IN 10ms: {best_slot['slots_cnt']} Slots (Slot Width {best_slot['slot_us']:.1f} µs) with PRR = {best_slot['prr']:.1f}%\n")

# Save Text Report
report_path = os.path.join(PROJECT_DIR, "exp_10ms_slot_sweep_results.txt")
with open(report_path, "w", encoding="utf-8") as f:
    f.write("# Phase 1 (10ms Window) Optimal Slot Count Sweep Analysis\n")
    f.write(f"- Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write(f"- Swarm Scale: 100 UAVs in 200m x 200m x 80m\n")
    f.write(f"- Broadcast Window: 10.0 ms\n")
    f.write(f"- Physical C/I Capture Threshold: +6.0 dB (Strict BLE 5.4 LE 2M)\n")
    f.write(f"- CSMA-CA Baseline PRR: {csma_res['prr']:.1f}%\n\n")
    f.write("| Slot Width (µs) | Total Slots | UAVs/Slot | Sidelink PRR (%) | CSMA PRR (%) | Δ Gain (%) | RX Deafness | Preamble Collisions | Power Captures |\n")
    f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
    for r in sidelink_results:
        delta = r['prr'] - csma_res['prr']
        f.write(f"| {r['slot_us']:.1f} | {r['slots_cnt']} | {r['density']:.2f} | {r['prr']:.1f}% | {csma_res['prr']:.1f}% | {delta:+.1f}% | {r['rx_deafness']} | {r['preamble_coll']} | {r['captures']} |\n")

print(f"📄 Detailed text report saved to: {report_path}")

# Plotting Charts
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

slots_x = [r['slots_cnt'] for r in sidelink_results]
prrs_y = [r['prr'] for r in sidelink_results]

# Panel 1: PRR vs Slot Count
ax1.plot(slots_x, prrs_y, 'o-', color='#1f77b4', linewidth=2.5, markersize=8, label='Sidelink S-SPS (+6dB)')
ax1.axhline(y=csma_res['prr'], color='#d62728', linestyle='--', linewidth=2.0, label=f"CSMA-CA Baseline ({csma_res['prr']:.1f}%)")
ax1.scatter([best_slot['slots_cnt']], [best_slot['prr']], color='#2ca02c', s=160, zorder=5, label=f"Optimal: {best_slot['slots_cnt']} Slots ({best_slot['prr']:.1f}%)")

ax1.set_xlabel('Number of Slots in 10ms Window', fontsize=12, fontweight='bold')
ax1.set_ylabel('Phase 1 Delivery PRR (%)', fontsize=12, fontweight='bold')
ax1.set_title('Phase 1 Delivery PRR vs Slot Count (100 UAVs, 10ms)', fontsize=13, fontweight='bold')
ax1.set_ylim(50, 100)
ax1.grid(True, linestyle='--', alpha=0.6)
ax1.legend(loc='lower right', fontsize=11)

for r in sidelink_results:
    ax1.annotate(f"{r['prr']:.1f}%", (r['slots_cnt'], r['prr']), textcoords="offset points", xytext=(0, 8), ha='center', fontsize=9, fontweight='bold')

# Panel 2: Physical Collision and Capture Dynamics
deafness_y = [r['rx_deafness'] for r in sidelink_results]
coll_y = [r['preamble_coll'] for r in sidelink_results]
capt_y = [r['captures'] for r in sidelink_results]

ax2.plot(slots_x, coll_y, 's--', color='#ff7f0e', linewidth=2, label='Collisions (Preamble Collision)')
ax2.plot(slots_x, capt_y, '^-', color='#2ca02c', linewidth=2, label='Power Capture Rescues')
ax2.plot(slots_x, deafness_y, 'd:', color='#9467bd', linewidth=2, label='Half-Duplex Deafness (TX Deaf)')

ax2.set_xlabel('Number of Slots in 10ms Window', fontsize=12, fontweight='bold')
ax2.set_ylabel('Event Count', fontsize=12, fontweight='bold')
ax2.set_title('Collision, Capture & Deafness vs Slot Count', fontsize=13, fontweight='bold')
ax2.grid(True, linestyle='--', alpha=0.6)
ax2.legend(loc='upper right', fontsize=10)

plt.tight_layout()
fig_path = os.path.join(PROJECT_DIR, "exp_10ms_slot_sweep_dashboard.png")
plt.savefig(fig_path, dpi=300)
plt.close()
print(f"📊 Dashboard plot saved to: {fig_path}")

# Auto commit and push
print("\n📤 Uploading slot sweep results to GitHub...")
try:
    subprocess.run("git add exp_10ms_slot_sweep* && git commit -m 'data: upload 10ms optimal slot sweep results' && git push origin main", shell=True, cwd=PROJECT_DIR)
except Exception as e:
    print(f"Notice on git push: {e}")

print("🎉 Slot Sweep Benchmark Completed Successfully!")
