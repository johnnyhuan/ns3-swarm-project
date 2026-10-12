#!/usr/bin/env python3
import subprocess
import os
import re
import sys

print("=========================================================")
print("🚀 Starting Swarm Density & Space Size Sweep (150m - 400m)")
print("=========================================================")

# Testing smaller spaces (higher densities) and baseline
spaces = [150, 200, 250, 300, 400]
results = []

# Path to the real ns-3-dev directory
NS3_DIR = os.path.expanduser("~/ns-3-dev")
PROJECT_DIR = os.path.expanduser("~/ns3-swarm-project")

# 1. Copy the latest code to ns-3-dev
try:
    print(f"=> Copying {PROJECT_DIR}/scratch/lr-wpan-swarm.cc to {NS3_DIR}/scratch/")
    subprocess.run(["cp", os.path.join(PROJECT_DIR, "scratch/lr-wpan-swarm.cc"), os.path.join(NS3_DIR, "scratch/")], check=True)
except Exception as e:
    print(f"Error copying file: {e}")
    sys.exit(1)

for s in spaces:
    # Scale Z proportionally: e.g. 150m space -> 50m height, 300m space -> 100m height
    z = round(min(100.0, s / 3.0), 1) if s < 300 else 100.0
    print(f"\n⚡ Running simulation with Space Size = {s}m x {s}m x {z}m...")
    cmd = ["./ns3", "run", f"scratch/lr-wpan-swarm --p2TxPower=-2 --p1TxPower=0 --p1AvoidDist=50 --numChannels=6 --spaceSize={s} --spaceZ={z}"]
    
    process = subprocess.Popen(
        cmd,
        cwd=NS3_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True
    )
    
    bcn_ratio = 0.0
    disc_ratio = 0.0
    srf = 0.0
    match_ratio = 0.0
    collision_ratio = 0.0
    rx_deaf_ratio = 0.0
    tx_deaf_ratio = 0.0
    
    raw_lines = []
    for line in process.stdout:
        raw_lines.append(line)
        if "Resource Collision (Same S+C):" in line:
            m = re.search(r'\((\d+\.\d+)%\)', line)
            if m: collision_ratio = float(m.group(1))
        elif "RX Deafness (Slot conflict)" in line:
            m = re.search(r'\((\d+\.\d+)%\)', line)
            if m: rx_deaf_ratio = float(m.group(1))
        elif "TX Deafness (Same slot as TX):" in line:
            m = re.search(r'\((\d+\.\d+)%\)', line)
            if m: tx_deaf_ratio = float(m.group(1))
        elif "Spatial Reuse Factor (SRF)" in line:
            m = re.search(r':\s+(\d+\.\d+)', line)
            if m: srf = float(m.group(1))
        elif "Discovery Message Reception Ratio" in line:
            m = re.search(r':\s+(\d+\.\d+)%', line)
            if m: disc_ratio = float(m.group(1))
        elif "Beacon Packet Reception Ratio" in line:
            m = re.search(r':\s+(\d+\.\d+)%', line)
            if m: bcn_ratio = float(m.group(1))
        elif "Monitor Member List Match Ratio" in line:
            m = re.search(r':\s+(\d+\.\d+)%', line)
            if m: match_ratio = float(m.group(1))
                
    process.wait()
    
    if bcn_ratio == 0.0 and process.returncode != 0:
        print("====== ERROR OUTPUT ======")
        print("".join(raw_lines[-20:]))
        print("==========================")
        
    print(f"   => Space {s}m: Beacon PRR = {bcn_ratio}% | SRF = {srf} | Collisions = {collision_ratio}% | RX Deafness = {rx_deaf_ratio}% | Disc PRR = {disc_ratio}%")
    results.append({
        "space": s,
        "z": z,
        "bcn_ratio": bcn_ratio,
        "disc_ratio": disc_ratio,
        "srf": srf,
        "match_ratio": match_ratio,
        "collision": collision_ratio,
        "rx_deafness": rx_deaf_ratio,
        "tx_deafness": tx_deaf_ratio
    })

print("\n" + "="*95)
print("             🏆 SPACE SIZE & SWARM DENSITY SWEEP RESULTS 🏆")
print("="*95)
print(f"{'Space (m)':<12} | {'Beacon PRR (%)':<16} | {'SRF (pkts/slot)':<18} | {'Collisions (%)':<16} | {'Disc PRR (%)':<14}")
print("-" * 95)
for r in results:
    print(f"{r['space']:<12} | {r['bcn_ratio']:<16.1f} | {r['srf']:<18.2f} | {r['collision']:<16.1f} | {r['disc_ratio']:<14.1f}")
print("="*95)
