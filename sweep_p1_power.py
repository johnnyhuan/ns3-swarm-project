#!/usr/bin/env python3
import subprocess
import os
import re
import sys

num_nodes = int(sys.argv[1]) if len(sys.argv) > 1 else 100
node_speed = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0

print("=========================================================================")
print(f"🚀 Starting Phase 1 Coverage Strength Sweep (50m - 150m)")
print(f"   Scale: {num_nodes} UAVs | Speed: {node_speed} m/s (3D Random Waypoint)")
print(f"   Focus Metric: Phase 1 Receive Rate (Discovery Message Reception Ratio)")
print("=========================================================================\n")

# Path to the real ns-3-dev directory
NS3_DIR = os.path.expanduser("~/ns-3-dev")
PROJECT_DIR = os.path.expanduser("~/ns3-swarm-project")

# 1. Copy the latest code to ns-3-dev
try:
    print(f"=> Syncing {PROJECT_DIR}/scratch/lr-wpan-swarm.cc to {NS3_DIR}/scratch/...")
    subprocess.run(["cp", os.path.join(PROJECT_DIR, "scratch/lr-wpan-swarm.cc"), os.path.join(NS3_DIR, "scratch/")], check=True)
except Exception as e:
    print(f"Error copying file: {e}")
    sys.exit(1)

# Power levels and theoretical coverage distances:
# Based on Log-Distance model PL(d) = 46.6777 + 30.0 * log10(d)
# Baseline 0 dBm corresponds to 100m.
# Distance d = 100 * 10^(P / 30) meters.
# -9 dBm (~50.1m) to +5 dBm (~146.8m)
power_levels = [-9, -8, -7, -6, -5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5]
fixed_p2_power = -2

results = []

for idx, p in enumerate(power_levels, start=1):
    est_range = 100.0 * (10.0 ** (p / 30.0))
    range_desc = f"{est_range:4.1f}m"
    if p == 0:
        range_desc += " (基線)"
    elif p == -9:
        range_desc += " (~50m)"
    elif p == 5:
        range_desc += " (~150m)"

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
    
    p1_rec_rate = 0.0
    p1_attempts = 0
    p1_aborts = 0
    p1_success = 0
    p1_rx_total = 0
    avg_iat = 0.0
    max_iat = 0.0
    
    raw_lines = []
    for line in process.stdout:
        raw_lines.append(line)
        if "Discovery Message Reception Ratio:" in line:
            m = re.search(r'Discovery Message Reception Ratio:\s*([\d.]+)%', line)
            if m: p1_rec_rate = float(m.group(1))
        elif "Phase 1 TX Attempts" in line:
            m = re.search(r'Phase 1 TX Attempts\s*:\s*(\d+)', line)
            if m: p1_attempts = int(m.group(1))
        elif "Phase 1 TX Aborts (CSMA Busy)" in line:
            m = re.search(r'Phase 1 TX Aborts \(CSMA Busy\)\s*:\s*(\d+)', line)
            if m: p1_aborts = int(m.group(1))
        elif "Phase 1 TX Success (Sent)" in line:
            m = re.search(r'Phase 1 TX Success \(Sent\)\s*:\s*(\d+)', line)
            if m: p1_success = int(m.group(1))
        elif "Phase 1 RX Success (Total Rcvd)" in line:
            m = re.search(r'Phase 1 RX Success \(Total Rcvd\)\s*:\s*(\d+)', line)
            if m: p1_rx_total = int(m.group(1))
        elif "Avg Discovery Msg IAT (Top-K)" in line:
            m = re.search(r'Avg Discovery Msg IAT \(Top-K\)\s*:\s*([\d.]+)', line)
            if m: avg_iat = float(m.group(1))
        elif "Max Discovery Msg IAT (Top-K)" in line:
            m = re.search(r'Max Discovery Msg IAT \(Top-K\)\s*:\s*([\d.]+)', line)
            if m: max_iat = float(m.group(1))

    process.wait()
    
    abort_rate = (p1_aborts / p1_attempts * 100.0) if p1_attempts > 0 else 0.0
    
    if p1_rec_rate == 0.0 and process.returncode != 0:
        print("====== ERROR OUTPUT ======")
        print("".join(raw_lines[-20:]))
        print("==========================")
        
    print(f"   => P1 Receive Rate: {p1_rec_rate:5.1f}% | CSMA Abort Rate: {abort_rate:5.1f}% | Avg IAT: {avg_iat:5.1f} ms | RX Packets: {p1_rx_total}")
    
    results.append({
        "power": p,
        "range_m": est_range,
        "p1_rec_rate": p1_rec_rate,
        "abort_rate": abort_rate,
        "p1_attempts": p1_attempts,
        "p1_aborts": p1_aborts,
        "p1_success": p1_success,
        "p1_rx_total": p1_rx_total,
        "avg_iat": avg_iat,
        "max_iat": max_iat
    })

# Format and display final summary table
print("\n" + "="*96)
print(f"        🏆 EXPERIMENT RESULTS: PHASE 1 COVERAGE SWEEP (50m - 150m) [{num_nodes} Drones] 🏆")
print("="*96)
print(f"{'P1 Power (dBm)':<15} | {'Coverage (m)':<13} | {'P1 Receive Rate':<17} | {'CSMA Abort Rate':<17} | {'Avg IAT (ms)':<13} | {'Total RX Pkts':<12}")
print("-" * 96)
for r in results:
    p_str = f"{r['power']:+d} dBm"
    rng_str = f"{r['range_m']:.1f} m"
    print(f"{p_str:>12}    | {rng_str:>11}   | {r['p1_rec_rate']:>15.1f}% | {r['abort_rate']:>15.1f}% | {r['avg_iat']:>10.1f} ms | {r['p1_rx_total']:>12}")
print("="*96)

# Save result to file
result_file = os.path.join(PROJECT_DIR, "exp_p1_strength_results.txt")
with open(result_file, "w") as f:
    f.write("Power_dBm,Coverage_m,P1_Receive_Rate_pct,CSMA_Abort_Rate_pct,Attempts,Aborts,Sent,Total_RX,Avg_IAT_ms,Max_IAT_ms\n")
    for r in results:
        f.write(f"{r['power']},{r['range_m']:.1f},{r['p1_rec_rate']:.2f},{r['abort_rate']:.2f},{r['p1_attempts']},{r['p1_aborts']},{r['p1_success']},{r['p1_rx_total']},{r['avg_iat']:.1f},{r['max_iat']:.1f}\n")

print(f"\n✅ Phase 1 sweep completed! Detailed results saved to: {result_file}")
