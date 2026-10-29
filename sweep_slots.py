#!/usr/bin/env python3
import subprocess
import os
import re
import sys

# Parameters (Default 75 UAVs, 10 m/s RWP flight speed, matching Phase 1 baseline)
num_nodes = int(sys.argv[1]) if len(sys.argv) > 1 else 75
node_speed = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0

print("==========================================================================================")
print(f"🚀 Starting Phase 2 Data Slots Sweep: 5 to 20 Slots (Every Integer Step: 1)")
print(f"   Swarm Scale: {num_nodes} UAVs | Flight Speed: {node_speed} m/s (3D RWP)")
print(f"   Fixed Setup: P1 Power = 0 dBm, P2 Power = -2 dBm, Channels = 6, AvoidDist = 50m")
print(f"   Observation: Trade-off between Beacon Reliability (PRR) vs. Freshness (Mean AoI)")
print("==========================================================================================\n")

# Path configuration
NS3_DIR = os.path.expanduser("~/ns-3-dev")
PROJECT_DIR = os.path.expanduser("~/ns3-swarm-project")

# 1. Sync updated code to ns-3-dev
try:
    print(f"=> Syncing {PROJECT_DIR}/scratch/lr-wpan-swarm.cc to {NS3_DIR}/scratch/...")
    subprocess.run(["cp", os.path.join(PROJECT_DIR, "scratch/lr-wpan-swarm.cc"), os.path.join(NS3_DIR, "scratch/")], check=True)
except Exception as e:
    print(f"Error copying file: {e}")
    sys.exit(1)

# Slots: Exactly 5 to 20 without skipping any integer
slots = list(range(5, 21)) # [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
results = []

for idx, s in enumerate(slots, start=1):
    # Cycle time formula: P1 (25ms) + GAP (1ms) + s * (2.5ms)
    cycle_ms = 25.0 + 1.0 + (s * 2.5)
    print(f"⚡ [{idx:2d}/{len(slots)}] Running Phase 2 Slots = {s:2d} (Cycle Time: {cycle_ms:4.1f} ms)...", end="", flush=True)
    
    cmd = [
        "./ns3", "run",
        f"scratch/lr-wpan-swarm --p2TxPower=-2 --p1TxPower=0 --p1AvoidDist=50 "
        f"--numChannels=6 --numSlots={s} --numNodes={num_nodes} --nodeSpeed={node_speed}"
    ]
    
    process = subprocess.Popen(
        cmd,
        cwd=NS3_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True
    )
    
    disc_ratio = 0.0
    bcn_ratio = 0.0
    avg_iat = 0.0
    max_iat = 0.0
    mean_aoi = 0.0
    max_aoi = 0.0
    tx_deafness = 0.0
    rx_deafness = 0.0
    collision = 0.0
    
    raw_lines = []
    for line in process.stdout:
        raw_lines.append(line)
        if "Discovery Message Reception Ratio" in line:
            m = re.search(r':\s+(\d+\.\d+)%', line)
            if m: disc_ratio = float(m.group(1))
        elif "Beacon Packet Reception Ratio" in line:
            m = re.search(r':\s+(\d+\.\d+)%', line)
            if m: bcn_ratio = float(m.group(1))
        elif "Avg Discovery Msg IAT" in line:
            m = re.search(r':\s+(\d+\.\d+)\s+ms', line)
            if m: avg_iat = float(m.group(1))
        elif "Max Discovery Msg IAT" in line:
            m = re.search(r':\s+(\d+\.\d+)\s+ms', line)
            if m: max_iat = float(m.group(1))
        elif "Mean Beacon Packet AoI" in line:
            m = re.search(r':\s+(\d+\.\d+)\s+ms', line)
            if m: mean_aoi = float(m.group(1))
        elif "Max Beacon Packet AoI" in line:
            m = re.search(r':\s+(\d+\.\d+)\s+ms', line)
            if m: max_aoi = float(m.group(1))
        elif "TX Deafness (Same slot as TX)" in line:
            m = re.search(r'\((\d+\.\d+)%\)', line)
            if m: tx_deafness = float(m.group(1))
        elif "RX Deafness (Slot conflict)" in line:
            m = re.search(r'\((\d+\.\d+)%\)', line)
            if m: rx_deafness = float(m.group(1))
        elif "Resource Collision (Same S+C)" in line:
            m = re.search(r'\((\d+\.\d+)%\)', line)
            if m: collision = float(m.group(1))
            
    process.wait()
    
    if bcn_ratio == 0.0 and process.returncode != 0:
        print(f"\n❌ Error in simulation run with Slots = {s}:")
        print("".join(raw_lines[-20:]))
    else:
        print(f" => Beacon PRR: {bcn_ratio:4.1f}% | AoI: {mean_aoi:5.1f}ms | Coll: {collision:4.1f}% | RX-Deaf: {rx_deafness:4.1f}%")
        
    results.append({
        "slots": s,
        "cycle_ms": cycle_ms,
        "disc_ratio": disc_ratio,
        "bcn_ratio": bcn_ratio,
        "avg_iat": avg_iat,
        "max_iat": max_iat,
        "mean_aoi": mean_aoi,
        "max_aoi": max_aoi,
        "tx_deafness": tx_deafness,
        "rx_deafness": rx_deafness,
        "collision": collision
    })

# Summary Table
print("\n" + "="*122)
print(f"           🏆 EXPERIMENT RESULTS: PHASE 2 DATA SLOTS SWEEP (5 to 20 Slots) [{num_nodes} Drones] 🏆")
print("="*122)
print(f"{'Slots':<6} | {'Cycle (ms)':<10} | {'Beacon PRR (%)':<15} | {'Mean AoI (ms)':<14} | {'Max AoI (ms)':<13} | {'Collisions (%)':<15} | {'RX Deaf (%)':<12} | {'TX Deaf (%)':<12} | {'Disc MRR (%)':<12}")
print("-" * 122)

best_slot_prr = None
max_prr = -1.0
best_slot_aoi = None
min_aoi = 99999.0

for r in results:
    if r['bcn_ratio'] > max_prr:
        max_prr = r['bcn_ratio']
        best_slot_prr = r['slots']
    if r['mean_aoi'] > 0 and r['mean_aoi'] < min_aoi:
        min_aoi = r['mean_aoi']
        best_slot_aoi = r['slots']
        
    print(f"{r['slots']:<6d} | {r['cycle_ms']:>8.1f}ms | {r['bcn_ratio']:>13.1f}% | {r['mean_aoi']:>12.1f}ms | {r['max_aoi']:>11.1f}ms | {r['collision']:>13.1f}% | {r['rx_deafness']:>10.1f}% | {r['tx_deafness']:>10.1f}% | {r['disc_ratio']:>10.1f}%")

print("="*122)
print(f"📌 Key Highlights:")
print(f"   • Highest Beacon PRR : {max_prr:.1f}% achieved at {best_slot_prr} Slots")
print(f"   • Lowest Mean AoI    : {min_aoi:.1f} ms achieved at {best_slot_aoi} Slots")
print("="*122)

# Save text summary
result_file = os.path.join(PROJECT_DIR, "exp_p2_slot_results.txt")
with open(result_file, "w") as f:
    f.write(f"# Phase 2 Data Slots Sweep (5 to 20 Slots) - {num_nodes} UAVs, Speed: {node_speed} m/s\n")
    f.write("Slots,CycleMs,BeaconPRR,MeanAoI_ms,MaxAoI_ms,CollisionPct,RxDeafPct,TxDeafPct,DiscoveryMRR\n")
    for r in results:
        f.write(f"{r['slots']},{r['cycle_ms']:.1f},{r['bcn_ratio']:.2f},{r['mean_aoi']:.1f},{r['max_aoi']:.1f},{r['collision']:.2f},{r['rx_deafness']:.2f},{r['tx_deafness']:.2f},{r['disc_ratio']:.2f}\n")
print(f"\n✅ Results saved to {result_file}")

# Generate publication-quality 2-panel plot
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'sans-serif']
    plt.rcParams['axes.unicode_minus'] = False
    
    slot_vals = [r['slots'] for r in results]
    bcn_vals = [r['bcn_ratio'] for r in results]
    aoi_vals = [r['mean_aoi'] for r in results]
    coll_vals = [r['collision'] for r in results]
    rx_deaf_vals = [r['rx_deafness'] for r in results]
    tx_deaf_vals = [r['tx_deafness'] for r in results]
    cycle_vals = [r['cycle_ms'] for r in results]
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10.5, 9.0), dpi=300, sharex=True)
    
    # ---------------- PANEL 1: PRR vs AoI Trade-off ----------------
    line1 = ax1.plot(slot_vals, bcn_vals, marker='o', markersize=7.5, color="#d62728", linewidth=2.5, label='Phase 2 Beacon PRR (%)')
    
    for s, bv in zip(slot_vals, bcn_vals):
        ax1.text(s, bv + 1.2, f"{bv:.1f}%", ha='center', va='bottom', fontsize=8.0, fontweight='bold', color="#d62728")
        
    ax1.set_ylabel('Beacon PRR (%)', fontsize=11.5, fontweight='bold', color="#d62728")
    ax1.tick_params(axis='y', labelcolor="#d62728")
    ax1.set_ylim(0, max(bcn_vals) * 1.35 if bcn_vals else 100)
    ax1.grid(True, linestyle='--', alpha=0.5)
    
    ax1_twin = ax1.twinx()
    line2 = ax1_twin.plot(slot_vals, aoi_vals, marker='^', markersize=7.5, color="#2ca02c", linewidth=2.2, linestyle='--', label='Mean Beacon AoI (ms)')
    
    for s, aoi in zip(slot_vals, aoi_vals):
        ax1_twin.text(s, aoi + 2.0, f"{aoi:.1f}ms", ha='center', va='bottom', fontsize=8.0, fontweight='bold', color="#2ca02c")
        
    ax1_twin.set_ylabel('Mean Beacon AoI (ms)', fontsize=11.5, fontweight='bold', color="#2ca02c")
    ax1_twin.tick_params(axis='y', labelcolor="#2ca02c")
    min_aoi_val = min(aoi_vals) if aoi_vals else 50.0
    max_aoi_val = max(aoi_vals) if aoi_vals else 200.0
    ax1_twin.set_ylim(max(0, min_aoi_val * 0.7), max_aoi_val * 1.3)
    
    # Combine legend for Panel 1
    lines1 = line1 + line2
    labels1 = [l.get_label() for l in lines1]
    ax1.legend(lines1, labels1, loc='upper left', frameon=True, framealpha=0.9, fontsize=9.5)
    ax1.set_title(f'Phase 2 Data Slots Sweep (5 - 20 Slots): Reliability vs. Freshness Trade-off\n[{num_nodes} UAVs, Speed: {node_speed} m/s, Channels: 6, P2 Power: -2 dBm]',
                  fontsize=12.5, fontweight='bold', pad=12)

    # ---------------- PANEL 2: Contention & Deafness Breakdown ----------------
    ax2.plot(slot_vals, coll_vals, marker='s', markersize=7, color="#e67e22", linewidth=2.0, label='Resource Collision (Same Slot & Channel)')
    ax2.plot(slot_vals, rx_deaf_vals, marker='D', markersize=6.5, color="#3498db", linewidth=2.0, label='RX Deafness (Slot Conflict on Diff Channels)')
    ax2.plot(slot_vals, tx_deaf_vals, marker='v', markersize=7, color="#e74c3c", linewidth=2.0, linestyle=':', label='TX Deafness (Target in same slot as my TX)')
    
    for s, cv, rv in zip(slot_vals, coll_vals, rx_deaf_vals):
        ax2.text(s, cv + 0.8, f"{cv:.1f}%", ha='center', va='bottom', fontsize=7.5, color="#e67e22")
        ax2.text(s, rv - 1.2, f"{rv:.1f}%", ha='center', va='top', fontsize=7.5, color="#3498db")
        
    ax2.set_xlabel('Phase 2 Data Slots (Configurable per Cycle)', fontsize=11.5, fontweight='bold', labelpad=8)
    ax2.set_ylabel('Scheduling Conflict Ratio (%)', fontsize=11.5, fontweight='bold', color="#333333")
    ax2.set_xticks(slot_vals)
    ax2.set_xticklabels([f"{s}\n({c:.1f}ms)" for s, c in zip(slot_vals, cycle_vals)], fontsize=8.5)
    ax2.set_ylim(0, max(max(coll_vals), max(rx_deaf_vals), 30) * 1.35)
    ax2.grid(True, linestyle='--', alpha=0.5)
    ax2.legend(loc='upper right', frameon=True, framealpha=0.9, fontsize=9.5)
    ax2.set_title('Phase 2 Contention & Deafness Breakdown vs. Available Slots', fontsize=11.5, fontweight='bold', pad=10)

    plot_path = os.path.join(PROJECT_DIR, "exp_p2_slot_plot.png")
    fig.tight_layout()
    fig.savefig(plot_path, bbox_inches='tight')
    plt.close(fig)
    print(f"📊 Auto-generated publication plot: {plot_path}")
except Exception as e:
    print(f"(Plotting skipped or failed: {e})")

print("\n==========================================================================")
print("👉 Sweep completed! You can push results to GitHub via:")
print("   git add scratch/lr-wpan-swarm.cc sweep_slots.py exp_p2_slot_results.txt exp_p2_slot_plot.png")
print("   git commit -m 'data: Phase 2 slot sweep results (5 to 20)'")
print("   git push origin main")
print("==========================================================================")
