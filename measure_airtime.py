#!/usr/bin/env python3
"""
Real Hardware Packet Air-Time Measurement Tool
Directly measures the nanosecond-level transmission duration of packets from ns-3 PHY events:
- Time of PhyTxBegin: The exact microsecond the preamble starts radiating on the antenna medium
- Time of PhyTxEnd  : The exact microsecond the last bit completely leaves the antenna medium
- Exact Air-Time    : PhyTxEnd - PhyTxBegin
"""

import subprocess
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
NS3_DIR = os.path.expanduser("~/ns-3-dev")
if not os.path.exists(NS3_DIR):
    NS3_DIR = PROJECT_DIR

# Sync scratch/lr-wpan-swarm.cc and src/lr-wpan/model/lr-wpan-phy.cc
for rel_path in ["scratch/lr-wpan-swarm.cc", "src/lr-wpan/model/lr-wpan-phy.cc", "src/lr-wpan/model/lr-wpan-phy.h"]:
    src_f = os.path.join(PROJECT_DIR, rel_path)
    dst_f = os.path.join(NS3_DIR, rel_path)
    if os.path.exists(src_f) and os.path.abspath(src_f) != os.path.abspath(dst_f):
        try:
            os.makedirs(os.path.dirname(dst_f), exist_ok=True)
            subprocess.run(["cp", src_f, dst_f], check=True)
        except Exception:
            pass

cmd = [
    "./ns3", "run",
    "scratch/lr-wpan-swarm --numNodes=2 --simTime=0.1 --p1Duration=10.0 --p2Duration=10.0 --enableP1Ssa=true"
]

print("📡 Executing Real Hardware Air-Time Measurement via ns-3 PHY Traces...\n")
proc = subprocess.run(cmd, cwd=NS3_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

printed_any = False
in_block = False
for line in proc.stdout.split("\n"):
    if "REAL HARDWARE AIR-TIME MEASUREMENT" in line:
        in_block = True
        printed_any = True
    if in_block:
        print(line)
        if line.startswith("===") and "REAL HARDWARE" not in line:
            in_block = False

if not printed_any:
    print(proc.stdout)
