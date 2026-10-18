#!/usr/bin/env python3
import subprocess
import os
import re
import sys

num_nodes = int(sys.argv[1]) if len(sys.argv) > 1 else 100

print("=========================================================")
print(f"🚀 Starting Experiment: UAV Flight Speed Sweep (0 - 25 m/s) [{num_nodes} Drones]")
print("=========================================================")

speeds = [0, 5, 10, 15, 20, 25] # 0 = Static Hover, 10 = 36 km/h, 25 = 90 km/h
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

for v in speeds:
    speed_desc = f"{v} m/s ({v*3.6:.0f} km/h)" if v > 0 else "0 m/s (Static Hover)"
    print(f"\n⚡ Running simulation with UAV Speed = {speed_desc} (Nodes = {num_nodes})...")
    cmd = ["./ns3", "run", f"scratch/lr-wpan-swarm --p2TxPower=-2 --p1TxPower=0 --p1AvoidDist=50 --numChannels=6 --numSlots=10 --numNodes={num_nodes} --nodeSpeed={v}"]
    
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
        
    print(f"   => Speed {v:2d} m/s: Beacon PRR = {bcn_ratio:4.1f}% | Disc MRR = {disc_ratio:4.1f}% | SRF = {srf:4.2f} | Collisions = {collision_ratio:4.1f}% | Mean AoI = {mean_aoi:5.1f} ms")
    results.append({
        "speed": v,
        "speed_kmh": v * 3.6,
        "bcn_ratio": bcn_ratio,
        "disc_ratio": disc_ratio,
        "srf": srf,
        "match_ratio": match_ratio,
        "collision": collision_ratio,
        "rx_deafness": rx_deaf_ratio,
        "mean_aoi": mean_aoi
    })

print("\n" + "="*95)
print(f"             🏆 EXPERIMENT: UAV FLIGHT SPEED SWEEP RESULTS [{num_nodes} Drones] 🏆")
print("="*95)
print(f"{'Speed (m/s)':<12} | {'Speed (km/h)':<12} | {'Beacon PRR':<12} | {'Disc MRR':<12} | {'SRF (pkts/slot)':<16} | {'Mean AoI':<12}")
print("-" * 95)
for r in results:
    print(f"{r['speed']:>4} m/s     | {r['speed_kmh']:>6.1f} km/h   | {r['bcn_ratio']:>10.1f}% | {r['disc_ratio']:>10.1f}% | {r['srf']:>15.2f} | {r['mean_aoi']:>9.1f} ms")
print("="*95)

# Save result to a quick text summary
with open(os.path.join(PROJECT_DIR, "exp_speed_results.txt"), "w") as f:
    f.write("Speed_ms,Speed_kmh,BeaconPRR,DiscMRR,SRF,Collision,RXDeafness,MeanAoI\n")
    for r in results:
        f.write(f"{r['speed']},{r['speed_kmh']},{r['bcn_ratio']},{r['disc_ratio']},{r['srf']},{r['collision']},{r['rx_deafness']},{r['mean_aoi']}\n")

print("\n✅ Speed sweep completed! Results saved to exp_speed_results.txt.")
