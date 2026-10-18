#!/usr/bin/env python3
import subprocess
import os
import re
import sys

print("=========================================================")
print("🚀 Starting Experiment: Channel Count Sweep (0 - 10 Ch)")
print("=========================================================")

channels = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
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

for c in channels:
    print(f"\n⚡ Running simulation with Phase 2 Data Channels = {c}...")
    cmd = ["./ns3", "run", f"scratch/lr-wpan-swarm --p2TxPower=-2 --p1TxPower=0 --p1AvoidDist=50 --numChannels={c}"]
    
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
        
    print(f"   => Channel {c}: Beacon PRR = {bcn_ratio}% | SRF = {srf} | Collisions = {collision_ratio}% | RX Deafness = {rx_deaf_ratio}%")
    results.append({
        "channel": c,
        "bcn_ratio": bcn_ratio,
        "disc_ratio": disc_ratio,
        "srf": srf,
        "match_ratio": match_ratio,
        "collision": collision_ratio,
        "rx_deafness": rx_deaf_ratio,
        "tx_deafness": tx_deaf_ratio
    })

print("\n" + "="*85)
print("             🏆 EXPERIMENT: CHANNEL COUNT SWEEP RESULTS (0 - 10) 🏆")
print("="*85)
print(f"{'Channels':<10} | {'Beacon PRR (%)':<16} | {'SRF (pkts/slot)':<18} | {'Collisions (%)':<16} | {'RX Deafness (%)':<16}")
print("-" * 85)
best_c = None
best_ratio = -1.0
for r in results:
    if r['bcn_ratio'] > best_ratio:
        best_ratio = r['bcn_ratio']
        best_c = r['channel']
    print(f"{r['channel']:<10} | {r['bcn_ratio']:>14.1f}% | {r['srf']:>16.2f} | {r['collision']:>14.1f}% | {r['rx_deafness']:>14.1f}%")
print("="*85)
print(f"🎉 Best Configuration: {best_c} Channels with {best_ratio:.1f}% Beacon Reception Ratio!")
print("="*85)

# Save result to a quick text summary
with open(os.path.join(PROJECT_DIR, "exp3_channel_results.txt"), "w") as f:
    f.write("Channel,BeaconPRR,SRF,Collision,RXDeafness\n")
    for r in results:
        f.write(f"{r['channel']},{r['bcn_ratio']},{r['srf']},{r['collision']},{r['rx_deafness']}\n")

print("\n✅ Sweep completed! Results saved to exp3_channel_results.txt.")
