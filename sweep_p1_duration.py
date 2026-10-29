#!/usr/bin/env python3
import subprocess
import os
import re
import sys

# Parameters
num_nodes = int(sys.argv[1]) if len(sys.argv) > 1 else 100
node_speed = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0

print("=========================================================================")
print(f"🚀 Starting Experiment: Phase 1 Duration Sweep (10ms - 40ms)")
print(f"   Swarm Scale: {num_nodes} Drones | Flight Speed: {node_speed} m/s (3D RWP)")
print(f"   Observation: Dual-Line Comparison (Discovery MRR vs. Beacon PRR)")
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

durations = [10, 15, 20, 25, 30, 35, 40]
results = []

for idx, dur in enumerate(durations, start=1):
    total_cycle = dur + 1.0 + (10 * 2.5) # dur + GAP(1ms) + 10 slots * 2.5ms = dur + 26ms
    print(f"⚡ [{idx}/{len(durations)}] Running P1 Duration = {dur:2d} ms (Frame Cycle = {total_cycle:4.1f} ms)...")
    
    cmd = [
        "./ns3", "run",
        f"scratch/lr-wpan-swarm --p1Duration={dur} --p2TxPower=-2 --p1TxPower=0 "
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
        
    print(f"   => P1 Duration {dur:2d}ms: Discovery MRR = {disc_ratio:5.1f}% | Beacon PRR = {bcn_ratio:5.1f}% | Mean AoI = {mean_aoi:5.1f} ms")
    
    results.append({
        "p1_dur": dur,
        "cycle_ms": total_cycle,
        "disc_ratio": disc_ratio,
        "bcn_ratio": bcn_ratio,
        "avg_iat": avg_iat,
        "mean_aoi": mean_aoi
    })

# Format and display summary table
print("\n" + "="*96)
print(f"       🏆 EXPERIMENT RESULTS: PHASE 1 DURATION SWEEP (10ms - 40ms) [{num_nodes} Drones] 🏆")
print("="*96)
print(f"{'P1 Duration (ms)':<18} | {'Epoch Cycle (ms)':<17} | {'Discovery MRR (%)':<19} | {'Beacon PRR (%)':<16} | {'Mean AoI (ms)':<14}")
print("-" * 96)
for r in results:
    dur_str = f"{r['p1_dur']} ms"
    cyc_str = f"{r['cycle_ms']:.1f} ms"
    if r['p1_dur'] == 25:
        dur_str += " (基線)"
    print(f"{dur_str:>15}    | {cyc_str:>14}   | {r['disc_ratio']:>17.1f}% | {r['bcn_ratio']:>14.1f}% | {r['mean_aoi']:>12.1f} ms")
print("="*96)

# Save result to text file
result_file = os.path.join(PROJECT_DIR, "exp_p1_duration_results.txt")
with open(result_file, "w") as f:
    f.write("P1_Duration_ms,Epoch_Cycle_ms,Discovery_MRR_pct,Beacon_PRR_pct,Avg_IAT_ms,Mean_AoI_ms\n")
    for r in results:
        f.write(f"{r['p1_dur']},{r['cycle_ms']:.1f},{r['disc_ratio']:.2f},{r['bcn_ratio']:.2f},{r['avg_iat']:.1f},{r['mean_aoi']:.1f}\n")
print(f"\n✅ Results saved to {result_file}")

# Try to plot automatically if matplotlib is available
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'sans-serif']
    plt.rcParams['axes.unicode_minus'] = False
    
    durs = [r['p1_dur'] for r in results]
    disc_vals = [r['disc_ratio'] for r in results]
    bcn_vals = [r['bcn_ratio'] for r in results]
    
    fig, ax = plt.subplots(figsize=(8.5, 5.2), dpi=300)
    
    line1 = ax.plot(durs, disc_vals, marker='s', markersize=8, color="#1f77b4", linewidth=2.5, label='Discovery Message RR (Phase 1)')
    line2 = ax.plot(durs, bcn_vals, marker='o', markersize=8, color="#d62728", linewidth=2.5, label='Beacon Packet PRR (Phase 2)')
    
    # Highlight 25ms baseline
    if 25 in durs:
        idx_25 = durs.index(25)
        ax.scatter([25], [disc_vals[idx_25]], color="#1f77b4", s=130, zorder=5)
        ax.scatter([25], [bcn_vals[idx_25]], color="#d62728", s=130, zorder=5)
        ax.annotate(f'Golden Balance (25ms)\nDisc: {disc_vals[idx_25]:.1f}%\nBcn: {bcn_vals[idx_25]:.1f}%',
                    xy=(25, bcn_vals[idx_25]), xytext=(27, bcn_vals[idx_25] - 12),
                    arrowprops=dict(facecolor='#d62728', shrink=0.08, width=1.5, headwidth=6),
                    fontsize=9.5, fontweight='bold', color="#d62728",
                    bbox=dict(boxstyle="round,pad=0.35", fc="#ffebee", ec="#d62728", lw=1))

    for d, dv, bv in zip(durs, disc_vals, bcn_vals):
        ax.text(d, dv + 1.8, f"{dv:.1f}%", ha='center', va='bottom', fontsize=9, fontweight='bold', color="#1f77b4")
        ax.text(d, bv - 2.5, f"{bv:.1f}%", ha='center', va='top', fontsize=9, fontweight='bold', color="#d62728")
        
    ax.set_title(f'Phase 1 Broadcast Duration vs. Reception Ratios ({num_nodes} Drones, {node_speed} m/s)', fontsize=13, fontweight='bold', pad=12)
    ax.set_xlabel('Phase 1 Duration (ms)', fontsize=11, fontweight='bold')
    ax.set_ylabel('Reception Ratio (%)', fontsize=11, fontweight='bold')
    ax.set_xticks(durs)
    ax.set_ylim(0, 100)
    ax.grid(True, linestyle='--', alpha=0.6)
    ax.legend(loc='center right', frameon=True, framealpha=0.9, fontsize=10)
    
    plot_path = os.path.join(PROJECT_DIR, "exp_p1_duration_plot.png")
    fig.savefig(plot_path, bbox_inches='tight')
    plt.close(fig)
    print(f"📊 Auto-generated publication plot: {plot_path}")
except Exception as e:
    print(f"(Plotting skipped or failed: {e})")
