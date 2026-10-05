#!/usr/bin/env python3
import subprocess
import re

# We test Phase 1 Avoid Distance from 0m to 100m.
avoid_dists = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
fixed_p1_power = 0
fixed_p2_power = -2

print("🚀 Starting RX Deafness Defense Parameter Sweep (Avoid Distance 0m - 100m)...")
print(f"=> Using fixed Phase 1 TX Power = {fixed_p1_power} dBm (100m range)")
print(f"=> Using fixed Phase 2 TX Power = {fixed_p2_power} dBm (50m range)\n")

# Copy the file
subprocess.run("cp ~/ns3-swarm-project/scratch/lr-wpan-swarm.cc ~/ns-3-dev/scratch/", shell=True, check=True)

for d in avoid_dists:
    dist_str = f"{d}m" if d > 0 else "0m (Disabled)"
    print(f"⚡ Running simulation with RX Deafness Defense Distance = {dist_str}...")
    
    cmd = f'cd ~/ns-3-dev && ./ns3 run "scratch/lr-wpan-swarm --p2TxPower={fixed_p2_power} --p1TxPower={fixed_p1_power} --p1AvoidDist={d}"'
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    
    beacon_ratio = "N/A"
    collision_ratio = "N/A"
    rx_deafness_ratio = "N/A"
    
    raw_output = []
    for line in process.stdout:
        raw_output.append(line)
        if "Resource Collision (Same S+C):" in line:
            match = re.search(r'\(([\d.]+)%\)', line)
            if match:
                collision_ratio = match.group(1) + "%"
        if "RX Deafness (Slot conflict)" in line:
            match = re.search(r'\(([\d.]+)%\)', line)
            if match:
                rx_deafness_ratio = match.group(1) + "%"
        if "Beacon Packet Reception Ratio" in line:
            match = re.search(r':\s*([\d.]+)%', line)
            if match:
                beacon_ratio = match.group(1) + "%"
                
    process.wait()
    if beacon_ratio == "N/A":
        print("====== RAW OUTPUT ======")
        print("".join(raw_output))
        print("========================")
    print(f"   => Reception Ratio: {beacon_ratio} (Collisions: {collision_ratio}, RX Deafness: {rx_deafness_ratio})\n")

print("✅ Avoid Distance sweep completed!")
