#!/usr/bin/env python3
import subprocess
import os
import re
import sys

# Parameters
num_nodes = int(sys.argv[1]) if len(sys.argv) > 1 else 75
node_speed = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0

print("=========================================================================")
print(f"🚀 Starting Phase 1 TX Power Sweep (-5 dBm to +5 dBm, Step: 1 dBm)")
print(f"   Swarm Scale: {num_nodes} UAVs | Flight Speed: {node_speed} m/s (3D RWP)")
print(f"   Observation: Dual-Line Comparison (Discovery MRR vs. Beacon PRR) + AoI")
print("=========================================================================\n")

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

# Power levels: -5 dBm to +5 dBm (11 points, step 1 dBm)
# Theoretical coverage d = 100 * 10^(P / 30) meters
power_levels = list(range(-5, 6)) # [-5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5]
fixed_p2_power = -2

results = []

for idx, p in enumerate(power_levels, start=1):
    est_range = 100.0 * (10.0 ** (p / 30.0))
    range_desc = f"{est_range:4.1f}m"
    if p == 0:
        range_desc += " (基線)"
    elif p == -5:
        range_desc += " (~68m)"
    elif p == 5:
        range_desc += " (~147m)"

    print(f"⚡ [{idx}/{len(power_levels)}] Running P1 Power = {p:+2d} dBm (Estimated Range: {range_desc})...")
    
    cmd = [
        "./ns3", "run",
        f"scratch/lr-wpan-swarm --p2TxPower={fixed_p2_power} --p1TxPower={p} "
        f"--p1AvoidDist=50 --numChannels=6 --numSlots=10 "
        f"--numNodes={num_nodes} --nodeSpeed={node_speed}"
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
    mean_aoi = 0.0
    
    raw_lines = []
    for line in process.stdout:
        raw_lines.append(line)
        if "Discovery Message Reception Ratio" in line:
            m = re.search(r'Discovery Message Reception Ratio\s*:\s*([\d.]+)%', line)
            if m: disc_ratio = float(m.group(1))
        elif "Beacon Packet Reception Ratio" in line:
            m = re.search(r'Beacon Packet Reception Ratio\s*:\s*([\d.]+)%', line)
            if m: bcn_ratio = float(m.group(1))
        elif "Avg Discovery Msg IAT (Top-K)" in line:
            m = re.search(r'Avg Discovery Msg IAT \(Top-K\)\s*:\s*([\d.]+)', line)
            if m: avg_iat = float(m.group(1))
        elif "Mean Beacon Packet AoI (Top-K)" in line:
            m = re.search(r'Mean Beacon Packet AoI \(Top-K\)\s*:\s*([\d.]+)', line)
            if m: mean_aoi = float(m.group(1))

    process.wait()
    
    if disc_ratio == 0.0 and bcn_ratio == 0.0 and process.returncode != 0:
        print("====== ERROR OUTPUT ======")
        print("".join(raw_lines[-20:]))
        print("==========================")
        
    print(f"   => P1 Power {p:+2d} dBm: Discovery MRR = {disc_ratio:5.1f}% | Beacon PRR = {bcn_ratio:5.1f}% | Mean AoI = {mean_aoi:5.1f} ms")
    
    results.append({
        "power": p,
        "range_m": est_range,
        "disc_ratio": disc_ratio,
        "bcn_ratio": bcn_ratio,
        "avg_iat": avg_iat,
        "mean_aoi": mean_aoi
    })

# Format and display summary table
print("\n" + "="*96)
print(f"       🏆 EXPERIMENT RESULTS: PHASE 1 TX POWER SWEEP (-5 to +5 dBm) [{num_nodes} Drones] 🏆")
print("="*96)
print(f"{'P1 Power (dBm)':<16} | {'Est. Range (m)':<16} | {'Discovery MRR (%)':<19} | {'Beacon PRR (%)':<16} | {'Mean AoI (ms)':<14}")
print("-" * 96)
for r in results:
    p_str = f"{r['power']:+d} dBm"
    rng_str = f"{r['range_m']:.1f} m"
    if r['power'] == 0:
        p_str += " (基線)"
    print(f"{p_str:>13}    | {rng_str:>13}   | {r['disc_ratio']:>17.1f}% | {r['bcn_ratio']:>14.1f}% | {r['mean_aoi']:>12.1f} ms")
print("="*96)

# Save result to text file
result_file = os.path.join(PROJECT_DIR, "exp_p1_power_results.txt")
with open(result_file, "w") as f:
    f.write("Power_dBm,Est_Range_m,Discovery_MRR_pct,Beacon_PRR_pct,Avg_IAT_ms,Mean_AoI_ms\n")
    for r in results:
        f.write(f"{r['power']},{r['range_m']:.1f},{r['disc_ratio']:.2f},{r['bcn_ratio']:.2f},{r['avg_iat']:.1f},{r['mean_aoi']:.1f}\n")
print(f"\n✅ Results saved to {result_file}")

# Generate publication-quality plot
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'sans-serif']
    plt.rcParams['axes.unicode_minus'] = False
    
    p_vals = [r['power'] for r in results]
    disc_vals = [r['disc_ratio'] for r in results]
    bcn_vals = [r['bcn_ratio'] for r in results]
    aoi_vals = [r['mean_aoi'] for r in results]
    
    fig, ax1 = plt.subplots(figsize=(9.0, 5.5), dpi=300)
    
    # Left Axis: Reception Ratios (%)
    line1 = ax1.plot(p_vals, disc_vals, marker='s', markersize=8, color="#1f77b4", linewidth=2.5, label='Discovery Message RR (Phase 1)')
    line2 = ax1.plot(p_vals, bcn_vals, marker='o', markersize=8, color="#d62728", linewidth=2.5, label='Beacon Packet PRR (Phase 2)')
    
    for p, dv, bv in zip(p_vals, disc_vals, bcn_vals):
        ax1.text(p, dv + 1.8, f"{dv:.1f}%", ha='center', va='bottom', fontsize=8.5, fontweight='bold', color="#1f77b4")
        ax1.text(p, bv - 2.8, f"{bv:.1f}%", ha='center', va='top', fontsize=8.5, fontweight='bold', color="#d62728")
        
    ax1.set_title(f'Phase 1 TX Power vs. Reception Ratios & Beacon AoI ({num_nodes} Drones, {node_speed} m/s)', fontsize=12.5, fontweight='bold', pad=12)
    ax1.set_xlabel('Phase 1 TX Power (dBm)', fontsize=11, fontweight='bold')
    ax1.set_ylabel('Reception Ratio (%)', fontsize=11, fontweight='bold', color="#333333")
    ax1.set_xticks(p_vals)
    ax1.set_xticklabels([f"{p:+d}" for p in p_vals])
    ax1.set_ylim(0, 100)
    ax1.grid(True, linestyle='--', alpha=0.5)

    # Right Axis: Mean Beacon AoI (ms)
    ax2 = ax1.twinx()
    line3 = ax2.plot(p_vals, aoi_vals, marker='^', markersize=8, color="#2ca02c", linewidth=2.2, linestyle='--', label='Mean Beacon AoI (Phase 2)')
    
    for p, aoi in zip(p_vals, aoi_vals):
        ax2.text(p, aoi + 2.0, f"{aoi:.1f}ms", ha='center', va='bottom', fontsize=8.5, fontweight='bold', color="#2ca02c")
        
    ax2.set_ylabel('Mean Beacon AoI (ms)', fontsize=11, fontweight='bold', color="#2ca02c")
    ax2.tick_params(axis='y', labelcolor="#2ca02c")
    
    min_aoi = min(aoi_vals) if aoi_vals else 100.0
    max_aoi = max(aoi_vals) if aoi_vals else 200.0
    ax2.set_ylim(max(0.0, min_aoi * 0.7), max_aoi * 1.35)

    # Combine legends into lower right (clean without point annotation)
    lines = line1 + line2 + line3
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc='lower right', frameon=True, framealpha=0.9, fontsize=9.5)
    
    plot_path = os.path.join(PROJECT_DIR, "exp_p1_power_plot.png")
    fig.savefig(plot_path, bbox_inches='tight')
    plt.close(fig)
    print(f"📊 Auto-generated publication plot: {plot_path}")
except Exception as e:
    print(f"(Plotting skipped or failed: {e})")
