#!/usr/bin/env python3
import subprocess
import os
import re
import sys

print("🚀 Starting Phase 2 TX Power Parameter Sweep...")

powers = [-15, -12, -9, -6, -4, -2, 0]
results = []

# Path to the real ns-3-dev directory
NS3_DIR = os.path.expanduser("~/ns-3-dev")

# 1. Copy the latest code to ns-3-dev
try:
    print("=> Copying scratch/lr-wpan-swarm.cc to ns-3-dev/scratch/")
    subprocess.run(["cp", "scratch/lr-wpan-swarm.cc", os.path.join(NS3_DIR, "scratch/")], check=True)
except Exception as e:
    print(f"Error copying file: {e}")
    sys.exit(1)

for p in powers:
    print(f"\n⚡ Running simulation with Phase 2 TX Power = {p} dBm...")
    cmd = ["./ns3", "run", f"scratch/lr-wpan-swarm --p2TxPower={p}"]
    
    # Run the simulation
    process = subprocess.Popen(
        cmd,
        cwd=NS3_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True
    )
    
    bcn_ratio = 0.0
    collision_ratio = 0.0
    rx_deaf_ratio = 0.0
    
    # We parse the output live to extract the metrics
    for line in process.stdout:
        if "Resource Collision (Same S+C):" in line:
            match = re.search(r'\((\d+\.\d+)%\)', line)
            if match:
                collision_ratio = float(match.group(1))
        elif "RX Deafness" in line:
            match = re.search(r'\((\d+\.\d+)%\)', line)
            if match:
                rx_deaf_ratio = float(match.group(1))
        elif "Beacon Packet Reception Ratio" in line:
            match = re.search(r':\s+(\d+\.\d+)%', line)
            if match:
                bcn_ratio = float(match.group(1))
                
    process.wait()
    
    print(f"   => Reception Ratio: {bcn_ratio}% (Collisions: {collision_ratio}%, RX Deafness: {rx_deaf_ratio}%)")
    results.append((p, bcn_ratio, collision_ratio, rx_deaf_ratio))

print("\n" + "="*55)
print("             🏆 PARAMETER SWEEP RESULTS 🏆")
print("="*55)
print(f"{'TX Power (dBm)':<16} | {'Reception Ratio':<17} | {'Resource Collision':<19}")
print("-" * 55)
best_p = None
best_ratio = -1.0
for p, ratio, col, rx in results:
    if ratio > best_ratio:
        best_ratio = ratio
        best_p = p
    print(f"{p:>14}   |   {ratio:>13}%  | {col:>16}%")
print("="*55)
print(f"🎉 Best Configuration: Phase 2 TX Power = {best_p} dBm with {best_ratio}% Reception Ratio!")
print("="*55)
