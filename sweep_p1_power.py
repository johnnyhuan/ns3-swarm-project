#!/usr/bin/env python3
import subprocess
import re

# We test Phase 1 TX Power from 0 dBm (100m) to 4 dBm (~158m).
power_levels = [0, 1, 2, 3, 4]
fixed_p2_power = -2

print("🚀 Starting Phase 1 TX Power Parameter Sweep (100m - ~150m)...")
print("=> Using fixed Phase 2 TX Power = -2 dBm (50m range)\n")

# Copy the file
subprocess.run("cp ~/ns3-swarm-project/scratch/lr-wpan-swarm.cc ~/ns-3-dev/scratch/", shell=True, check=True)

for p in power_levels:
    print(f"⚡ Running simulation with Phase 1 TX Power = {p} dBm...")
    
    cmd = f'cd ~/ns-3-dev && ./ns3 run "scratch/lr-wpan-swarm --p2TxPower={fixed_p2_power} --p1TxPower={p}"'
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

print("✅ Phase 1 Parameter sweep completed!")
