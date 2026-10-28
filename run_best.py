#!/usr/bin/env python3
import subprocess
import os
import sys

print("=========================================================================")
print("🚀 Running Optimal Configuration (Best Swarm Performance)")
print("=========================================================================\n")

NS3_DIR = os.path.expanduser("~/ns-3-dev")
PROJECT_DIR = os.path.expanduser("~/ns3-swarm-project")

# Sync latest lr-wpan-swarm.cc to ns-3-dev
try:
    print(f"=> Syncing {PROJECT_DIR}/scratch/lr-wpan-swarm.cc to {NS3_DIR}/scratch/...")
    subprocess.run(["cp", os.path.join(PROJECT_DIR, "scratch/lr-wpan-swarm.cc"), os.path.join(NS3_DIR, "scratch/")], check=True)
except Exception as e:
    print(f"Error copying file: {e}")
    sys.exit(1)

# Options:
# 1) Standard Baseline: 50 drones, 300m box, static hover -> ~41.0% Beacon PRR, ~80% Discovery PRR
# 2) High-Performance Wide Space: 50 drones, 400m box -> ~49.0% Beacon PRR, ~85% Discovery PRR
space_size = float(sys.argv[1]) if len(sys.argv) > 1 else 300.0
num_nodes = int(sys.argv[2]) if len(sys.argv) > 2 else 50
speed = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0

print(f"⚡ Launching simulation: Nodes={num_nodes}, Space={space_size}m, Speed={speed} m/s...")

cmd = [
    "./ns3", "run",
    f"scratch/lr-wpan-swarm --p2TxPower=-2 --p1TxPower=0 --p1AvoidDist=50 "
    f"--numChannels=6 --numSlots=10 --numNodes={num_nodes} --spaceSize={space_size} --nodeSpeed={speed}"
]

process = subprocess.Popen(
    cmd,
    cwd=NS3_DIR,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    universal_newlines=True
)

output_lines = []
capture = False
for line in process.stdout:
    output_lines.append(line)
    if "GLOBAL NETWORK METRICS" in line:
        capture = True
    if capture:
        print(line, end="")

process.wait()

if not capture:
    print("====== RAW OUTPUT ======")
    print("".join(output_lines[-30:]))
    print("========================")
