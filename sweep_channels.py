#!/usr/bin/env python3
import subprocess
import os
import re
import sys

# Parameters (Default 75 UAVs, 10 m/s RWP flight speed, matching baseline)
num_nodes = int(sys.argv[1]) if len(sys.argv) > 1 else 75
node_speed = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0

print("==========================================================================================")
print(f"🚀 Starting Phase 2 Channel Count Sweep: 2 to 10 Channels (Every Integer Step: 1)")
print(f"   Swarm Scale: {num_nodes} UAVs | Flight Speed: {node_speed} m/s (3D RWP)")
print(f"   Fixed Setup: P1 Power = 0 dBm, P2 Power = -2 dBm, Slots = 10 (Cycle = 51.0 ms), AvoidDist = 50m")
print(f"   Observation: Trade-off between Frequency Diversity (PRR) vs. Freshness (Mean AoI)")
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

# Channels: Exactly 2 to 10 without skipping any integer
channels = list(range(2, 11))  # [2, 3, 4, 5, 6, 7, 8, 9, 10]
results = []

for idx, c in enumerate(channels, start=1):
    print(f"⚡ [{idx:2d}/{len(channels)}] Running Phase 2 Channels = {c:2d}...", end="", flush=True)
    
    cmd = [
        "./ns3", "run",
        f"scratch/lr-wpan-swarm --p2TxPower=-2 --p1TxPower=0 --p1AvoidDist=50 "
        f"--numSlots=10 --numChannels={c} --numNodes={num_nodes} --nodeSpeed={node_speed}"
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
        print(f"\n❌ Error in simulation run with Channels = {c}:")
        print("".join(raw_lines[-20:]))
    else:
        print(f" => Beacon PRR: {bcn_ratio:4.1f}% | AoI: {mean_aoi:5.1f}ms")
        
    results.append({
        "channel": c,
        "disc_ratio": disc_ratio,
        "bcn_ratio": bcn_ratio,
        "mean_aoi": mean_aoi,
        "max_aoi": max_aoi,
        "tx_deafness": tx_deafness,
        "rx_deafness": rx_deafness,
        "collision": collision
    })

# Summary Table
print("\n" + "="*80)
print(f"       🏆 EXPERIMENT RESULTS: PHASE 2 CHANNELS SWEEP (2 to 10) [{num_nodes} Drones] 🏆")
print("="*80)
print(f"{'Channels':<12} | {'Beacon PRR (%)':<18} | {'Mean AoI (ms)':<16} | {'Max AoI (ms)':<14}")
print("-" * 80)
for r in results:
    c_str = f"{r['channel']}"
    if r['channel'] == 6:
        c_str += " (基線)"
    print(f"{c_str:<12} | {r['bcn_ratio']:>16.1f}% | {r['mean_aoi']:>14.1f} ms | {r['max_aoi']:>12.1f} ms")
print("="*80)

# Save result to text file
result_file = os.path.join(PROJECT_DIR, "exp_p2_channel_results.txt")
with open(result_file, "w") as f:
    f.write("Channels,Beacon_PRR_pct,Mean_AoI_ms,Max_AoI_ms,Collisions_pct,RX_Deafness_pct,TX_Deafness_pct\n")
    for r in results:
        f.write(f"{r['channel']},{r['bcn_ratio']:.2f},{r['mean_aoi']:.1f},{r['max_aoi']:.1f},{r['collision']:.2f},{r['rx_deafness']:.2f},{r['tx_deafness']:.2f}\n")
print(f"\n✅ Results saved to {result_file}")

# Generate publication-quality twin y-axis plot (identical visual style to P1 duration/power sweeps)
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'sans-serif']
    plt.rcParams['axes.unicode_minus'] = False
    
    ch_vals = [r['channel'] for r in results]
    bcn_vals = [r['bcn_ratio'] for r in results]
    aoi_vals = [r['mean_aoi'] for r in results]
    
    fig, ax1 = plt.subplots(figsize=(9.0, 5.5), dpi=300)
    
    # Left Axis: Beacon PRR (%)
    line1 = ax1.plot(ch_vals, bcn_vals, marker='o', markersize=8, color="#d62728", linewidth=2.5, label='Beacon Packet PRR (Phase 2)')
    
    for c, bv in zip(ch_vals, bcn_vals):
        ax1.text(c, bv + 1.2, f"{bv:.1f}%", ha='center', va='bottom', fontsize=8.5, fontweight='bold', color="#d62728")
        
    ax1.set_xlabel('Phase 2 Data Channels (Available Frequencies)', fontsize=11, fontweight='bold', labelpad=8)
    ax1.set_ylabel('Beacon PRR (%)', fontsize=11, fontweight='bold', color="#d62728")
    ax1.tick_params(axis='y', labelcolor="#d62728")
    ax1.set_xticks(ch_vals)
    max_bcn = max(bcn_vals) if bcn_vals else 50.0
    ax1.set_ylim(0, max(max_bcn * 1.35, 40.0))
    ax1.grid(True, linestyle='--', alpha=0.5)
    
    # Right Axis: Mean Beacon AoI (ms)
    ax2 = ax1.twinx()
    line2 = ax2.plot(ch_vals, aoi_vals, marker='^', markersize=8, color="#2ca02c", linewidth=2.2, linestyle='--', label='Mean Beacon AoI (Phase 2)')
    
    for c, aoi in zip(ch_vals, aoi_vals):
        ax2.text(c, aoi + 2.0, f"{aoi:.1f}ms", ha='center', va='bottom', fontsize=8.5, fontweight='bold', color="#2ca02c")
        
    ax2.set_ylabel('Mean Beacon AoI (ms)', fontsize=11, fontweight='bold', color="#2ca02c")
    ax2.tick_params(axis='y', labelcolor="#2ca02c")
    min_aoi = min(aoi_vals) if aoi_vals else 50.0
    max_aoi = max(aoi_vals) if aoi_vals else 200.0
    ax2.set_ylim(max(0.0, min_aoi * 0.7), max_aoi * 1.35)
    
    # Combine legends into upper left or center right
    lines = line1 + line2
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc='upper left', frameon=True, framealpha=0.9, fontsize=9.5)
    
    ax1.set_title(f'Phase 2 Channel Allocation vs. Beacon PRR & AoI ({num_nodes} UAVs, {node_speed} m/s)\n'
                  f'[Fixed: P1 = 0 dBm (25ms), P2 = -2 dBm, Slots = 10, AvoidDist = 50m]',
                  fontsize=12.0, fontweight='bold', pad=12)

    plot_path = os.path.join(PROJECT_DIR, "exp_p2_channel_plot.png")
    fig.tight_layout()
    fig.savefig(plot_path, bbox_inches='tight')
    plt.close(fig)
    print(f"📊 Auto-generated publication plot: {plot_path}")
except Exception as e:
    print(f"(Plotting skipped or failed: {e})")

print("\n==========================================================================")
print("👉 Sweep completed! You can push results to GitHub via:")
print("   git add sweep_channels.py exp_p2_channel_results.txt exp_p2_channel_plot.png")
print("   git commit -m 'data: Phase 2 channel sweep results (2 to 10)'")
print("   git push origin main")
print("==========================================================================")
