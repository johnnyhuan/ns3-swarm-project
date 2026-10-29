#!/usr/bin/env python3
import subprocess
import os
import re
import sys
import math

# Parameters (Default 75 UAVs, 10 m/s RWP flight speed, matching baseline)
num_nodes = int(sys.argv[1]) if len(sys.argv) > 1 else 75
node_speed = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0

print("==========================================================================================")
print(f"🚀 Starting Experiment: Phase 2 Spatial Defense Design & RSSI Sensitivity Sweep")
print(f"   Swarm Scale: {num_nodes} UAVs | Flight Speed: {node_speed} m/s (3D RWP)")
print(f"   Comparison : (A) No Defense (僅避同格) vs. (B) Defense RSSI Sweep (-106 to -90 dBm)")
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

def run_simulation(enable_defense, avoid_rssi=None):
    if not enable_defense:
        cmd_args = "--enableDefense=false"
    else:
        cmd_args = f"--enableDefense=true --p1AvoidRssi={avoid_rssi}"
        
    cmd = [
        "./ns3", "run",
        f"scratch/lr-wpan-swarm {cmd_args} --p2TxPower=-2 --p1TxPower=0 "
        f"--numChannels=6 --numSlots=10 --numNodes={num_nodes} --nodeSpeed={node_speed}"
    ]
    
    process = subprocess.Popen(
        cmd,
        cwd=NS3_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True
    )
    
    bcn_ratio = 0.0
    mean_aoi = 0.0
    max_aoi = 0.0
    tx_deafness = 0.0
    rx_deafness = 0.0
    collision = 0.0
    
    raw_lines = []
    for line in process.stdout:
        raw_lines.append(line)
        if "Beacon Packet Reception Ratio" in line:
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
        print(f"\n❌ Error in simulation:")
        print("".join(raw_lines[-20:]))
        
    return {
        "bcn_ratio": bcn_ratio,
        "mean_aoi": mean_aoi,
        "max_aoi": max_aoi,
        "tx_deafness": tx_deafness,
        "rx_deafness": rx_deafness,
        "collision": collision
    }

# ---------------------------------------------------------
# Phase 1: Run Baseline (Without Defense Design)
# ---------------------------------------------------------
print("⚡ [1/18] Running Baseline: WITHOUT Defense Design (只要聽到，就不跟他選同一格)...", end="", flush=True)
no_defense_res = run_simulation(enable_defense=False)
print(f" => Beacon PRR: {no_defense_res['bcn_ratio']:4.1f}% | AoI: {no_defense_res['mean_aoi']:5.1f}ms | RX-Deaf: {no_defense_res['rx_deafness']:4.1f}% | TX-Deaf: {no_defense_res['tx_deafness']:4.1f}%\n")

# ---------------------------------------------------------
# Phase 2: Sweep Defense RSSI Threshold from -106 to -90 dBm
# ---------------------------------------------------------
rssi_list = list(range(-106, -89)) # [-106, -105, ..., -90] (17 integer steps)
sweep_results = []

for idx, r in enumerate(rssi_list, start=2):
    equiv_dist = 10.0 ** ((-46.6777 - r) / 30.0)
    print(f"⚡ [{idx:2d}/18] Running Defense Threshold = {r:4d} dBm (~{equiv_dist:4.1f}m)...", end="", flush=True)
    res = run_simulation(enable_defense=True, avoid_rssi=r)
    res["rssi"] = r
    res["equiv_dist"] = equiv_dist
    sweep_results.append(res)
    print(f" => Beacon PRR: {res['bcn_ratio']:4.1f}% | AoI: {res['mean_aoi']:5.1f}ms | RX-Deaf: {res['rx_deafness']:4.1f}% | TX-Deaf: {res['tx_deafness']:4.1f}%")

# ---------------------------------------------------------
# Display Summary Tables
# ---------------------------------------------------------
opt_baseline = next((x for x in sweep_results if x["rssi"] == -98), sweep_results[0])

print("\n" + "="*95)
print(f"       🏆 COMPARISON: WITHOUT DEFENSE vs. WITH PROPOSED DEFENSE (-98 dBm) [{num_nodes} UAVs] 🏆")
print("="*95)
print(f"{'Mechanism':<35} | {'Beacon PRR':<12} | {'Mean AoI':<12} | {'RX Deafness':<13} | {'TX Deafness':<12}")
print("-" * 95)
print(f"{'Without Defense (僅避同格 S+C)':<35} | {no_defense_res['bcn_ratio']:>10.1f}% | {no_defense_res['mean_aoi']:>9.1f} ms | {no_defense_res['rx_deafness']:>11.1f}% | {no_defense_res['tx_deafness']:>10.1f}%")
print(f"{'With Defense (防禦門檻 -98dBm / 50m)':<35} | {opt_baseline['bcn_ratio']:>10.1f}% | {opt_baseline['mean_aoi']:>9.1f} ms | {opt_baseline['rx_deafness']:>11.1f}% | {opt_baseline['tx_deafness']:>10.1f}%")
diff_prr = opt_baseline['bcn_ratio'] - no_defense_res['bcn_ratio']
gain_times = opt_baseline['bcn_ratio'] / max(0.1, no_defense_res['bcn_ratio'])
print("="*95)
print(f"🎉 防禦設計效益：Beacon PRR 提升 +{diff_prr:.1f}% (效能提升約 {gain_times:.1f} 倍)，大幅抑制耳聾衝突！\n")

print("="*105)
print(f"       🏆 DEFENSE RSSI THRESHOLD SWEEP (-106 to -90 dBm) [{num_nodes} UAVs, 10 m/s] 🏆")
print("="*105)
print(f"{'RSSI Threshold':<16} | {'Equiv Dist':<12} | {'Beacon PRR (%)':<16} | {'Mean AoI (ms)':<15} | {'RX Deaf (%)':<13} | {'TX Deaf (%)':<13} | {'Collision (%)':<13}")
print("-" * 105)
for r in sweep_results:
    rssi_str = f"{r['rssi']} dBm"
    if r['rssi'] == -98:
        rssi_str += " (原50m)"
    print(f"{rssi_str:<16} | {r['equiv_dist']:>9.1f} m | {r['bcn_ratio']:>14.1f}% | {r['mean_aoi']:>13.1f} ms | {r['rx_deafness']:>11.1f}% | {r['tx_deafness']:>11.1f}% | {r['collision']:>11.1f}%")
print("="*105)

# Save results to text file
result_file = os.path.join(PROJECT_DIR, "exp_p2_defense_results.txt")
with open(result_file, "w") as f:
    f.write("# Baseline Without Defense\n")
    f.write(f"NO_DEFENSE,{no_defense_res['bcn_ratio']:.2f},{no_defense_res['mean_aoi']:.1f},{no_defense_res['rx_deafness']:.2f},{no_defense_res['tx_deafness']:.2f},{no_defense_res['collision']:.2f}\n\n")
    f.write("# Defense RSSI Threshold Sweep\n")
    f.write("RSSI_dBm,EquivDist_m,Beacon_PRR_pct,Mean_AoI_ms,RX_Deafness_pct,TX_Deafness_pct,Collision_pct\n")
    for r in sweep_results:
        f.write(f"{r['rssi']},{r['equiv_dist']:.1f},{r['bcn_ratio']:.2f},{r['mean_aoi']:.1f},{r['rx_deafness']:.2f},{r['tx_deafness']:.2f},{r['collision']:.2f}\n")
print(f"\n✅ Results saved to {result_file}")

# ---------------------------------------------------------
# Generate Publication Plot
# ---------------------------------------------------------
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'sans-serif']
    plt.rcParams['axes.unicode_minus'] = False
    
    rssi_vals = [r['rssi'] for r in sweep_results]
    dist_vals = [r['equiv_dist'] for r in sweep_results]
    bcn_vals = [r['bcn_ratio'] for r in sweep_results]
    aoi_vals = [r['mean_aoi'] for r in sweep_results]
    
    fig, ax1 = plt.subplots(figsize=(10.5, 5.8), dpi=300)
    
    # Left Axis: Beacon PRR (%)
    line1 = ax1.plot(rssi_vals, bcn_vals, marker='o', markersize=8, color="#d62728", linewidth=2.5, label='Beacon PRR (With Defense)')
    
    for r, d, bv in zip(rssi_vals, dist_vals, bcn_vals):
        ax1.text(r, bv + 1.2, f"{bv:.1f}%", ha='center', va='bottom', fontsize=7.5, fontweight='bold', color="#d62728")
        
    # Baseline Without Defense Horizontal Line
    line_base = ax1.axhline(no_defense_res['bcn_ratio'], color="#7f8c8d", linestyle=":", linewidth=2.2,
                            label=f"Baseline: Without Defense ({no_defense_res['bcn_ratio']:.1f}%)")
    
    ax1.set_xlabel('Defense RSSI Threshold (dBm) & Equivalent Physical Range', fontsize=11, fontweight='bold', labelpad=8)
    ax1.set_ylabel('Beacon PRR (%)', fontsize=11, fontweight='bold', color="#d62728")
    ax1.tick_params(axis='y', labelcolor="#d62728")
    ax1.set_xticks(rssi_vals)
    ax1.set_xticklabels([f"{r}\n({d:.0f}m)" for r, d in zip(rssi_vals, dist_vals)], fontsize=8.0)
    max_bcn = max(max(bcn_vals), no_defense_res['bcn_ratio'], 35.0)
    ax1.set_ylim(0, max_bcn * 1.35)
    ax1.grid(True, linestyle='--', alpha=0.5)
    
    # Right Axis: Mean Beacon AoI (ms)
    ax2 = ax1.twinx()
    line2 = ax2.plot(rssi_vals, aoi_vals, marker='^', markersize=8, color="#2ca02c", linewidth=2.2, linestyle='--', label='Mean Beacon AoI (With Defense)')
    
    for r, aoi in zip(rssi_vals, aoi_vals):
        ax2.text(r, aoi + 2.0, f"{aoi:.1f}ms", ha='center', va='bottom', fontsize=7.5, fontweight='bold', color="#2ca02c")
        
    ax2.set_ylabel('Mean Beacon AoI (ms)', fontsize=11, fontweight='bold', color="#2ca02c")
    ax2.tick_params(axis='y', labelcolor="#2ca02c")
    min_aoi = min(aoi_vals) if aoi_vals else 50.0
    max_aoi = max(aoi_vals) if aoi_vals else 200.0
    ax2.set_ylim(max(0.0, min_aoi * 0.7), max_aoi * 1.35)
    
    # Combine legends into upper left
    lines = line1 + [line_base] + line2
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc='upper left', frameon=True, framealpha=0.9, fontsize=9.0)
    
    ax1.set_title(f'Phase 2 Spatial Defense Design & Sensitivity Sweep (-106 to -90 dBm)\n'
                  f'[{num_nodes} UAVs, Speed: {node_speed} m/s, Channels: 6, Slots: 10, Baseline: -98 dBm (50m)]',
                  fontsize=12.0, fontweight='bold', pad=12)

    plot_path = os.path.join(PROJECT_DIR, "exp_p2_defense_plot.png")
    fig.tight_layout()
    fig.savefig(plot_path, bbox_inches='tight')
    plt.close(fig)
    print(f"📊 Auto-generated publication plot: {plot_path}")
except Exception as e:
    print(f"(Plotting skipped or failed: {e})")

print("\n==========================================================================")
print("👉 Sweep completed! You can push results to GitHub via:")
print("   git add scratch/lr-wpan-swarm.cc sweep_p2_defense.py exp_p2_defense_results.txt exp_p2_defense_plot.png")
print("   git commit -m 'data: Phase 2 defense comparison and RSSI threshold sweep'")
print("   git push origin main")
print("==========================================================================")
