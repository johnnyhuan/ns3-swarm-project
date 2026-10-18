#!/usr/bin/env python3
import subprocess
import os
import re
import sys

print("=========================================================")
print("🚀 Starting Experiment: Slot Count Sweep (5 - 20 Slots)")
print("=========================================================")

slots = list(range(5, 21)) # [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
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

for s in slots:
    print(f"\n⚡ Running simulation with Phase 2 Data Slots = {s}...")
    cmd = ["./ns3", "run", f"scratch/lr-wpan-swarm --p2TxPower=-2 --p1TxPower=0 --p1AvoidDist=50 --numChannels=6 --numSlots={s}"]
    
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
    mean_aoi = 0.0
    
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
        elif "Mean Beacon Packet AoI" in line:
            m = re.search(r':\s+(\d+\.\d+)\s+ms', line)
            if m: mean_aoi = float(m.group(1))
                
    process.wait()
    
    if bcn_ratio == 0.0 and process.returncode != 0:
        print("====== ERROR OUTPUT ======")
        print("".join(raw_lines[-20:]))
        print("==========================")
        
    print(f"   => Slot {s:2d}: Beacon PRR = {bcn_ratio:4.1f}% | SRF = {srf:4.2f} | Collisions = {collision_ratio:4.1f}% | RX Deafness = {rx_deaf_ratio:4.1f}% | Mean AoI = {mean_aoi:5.1f} ms")
    results.append({
        "slot": s,
        "bcn_ratio": bcn_ratio,
        "disc_ratio": disc_ratio,
        "srf": srf,
        "match_ratio": match_ratio,
        "collision": collision_ratio,
        "rx_deafness": rx_deaf_ratio,
        "tx_deafness": tx_deaf_ratio,
        "mean_aoi": mean_aoi
    })

print("\n" + "="*95)
print("              🏆 EXPERIMENT: SLOT COUNT SWEEP RESULTS (5 - 20) 🏆")
print("="*95)
print(f"{'Slots':<8} | {'Beacon PRR (%)':<15} | {'SRF (pkts/slot)':<16} | {'Collisions (%)':<15} | {'RX Deafness (%)':<16} | {'Mean AoI (ms)':<14}")
print("-" * 95)
best_s = None
best_ratio = -1.0
for r in results:
    if r['bcn_ratio'] > best_ratio:
        best_ratio = r['bcn_ratio']
        best_s = r['slot']
    print(f"{r['slot']:<8} | {r['bcn_ratio']:>13.1f}% | {r['srf']:>15.2f} | {r['collision']:>13.1f}% | {r['rx_deafness']:>14.1f}% | {r['mean_aoi']:>12.1f} ms")
print("="*95)
print(f"🎉 Best Configuration: {best_s} Slots with {best_ratio:.1f}% Beacon Reception Ratio!")
print("="*95)

# Save result to a quick text summary
with open(os.path.join(PROJECT_DIR, "exp_slot_results.txt"), "w") as f:
    f.write("Slot,BeaconPRR,SRF,Collision,RXDeafness,MeanAoI\n")
    for r in results:
        f.write(f"{r['slot']},{r['bcn_ratio']},{r['srf']},{r['collision']},{r['rx_deafness']},{r['mean_aoi']}\n")

print("\n✅ Sweep completed! Results saved to exp_slot_results.txt.")
