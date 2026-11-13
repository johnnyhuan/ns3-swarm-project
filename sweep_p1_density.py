#!/usr/bin/env python3
import subprocess
import os
import sys
import csv
import re
from collections import defaultdict

print("=========================================================================")
print("🔬 SWARM DENSITY & TOPOLOGY SWEEP BENCHMARK (75 UAVs, P1 = 10ms) 🔬")
print("=========================================================================")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
NS3_DIR = os.path.expanduser("~/ns-3-dev")
if not os.path.exists(NS3_DIR):
    NS3_DIR = PROJECT_DIR

# Sync updated files to NS3_DIR if running across separate folders
sync_files = [
    "scratch/lr-wpan-swarm.cc",
    "src/lr-wpan/model/lr-wpan-phy.cc",
    "src/lr-wpan/model/lr-wpan-phy.h",
    "src/lr-wpan/model/lr-wpan-constants.h",
    "src/lr-wpan/model/lr-wpan-csmaca.cc"
]
for rel_path in sync_files:
    src_f = os.path.join(PROJECT_DIR, rel_path)
    dst_f = os.path.join(NS3_DIR, rel_path)
    if os.path.exists(src_f) and os.path.abspath(src_f) != os.path.abspath(dst_f):
        try:
            print(f"=> Syncing {src_f} to {dst_f}...")
            os.makedirs(os.path.dirname(dst_f), exist_ok=True)
            subprocess.run(["cp", src_f, dst_f], check=True)
        except Exception as e:
            print(f"Error syncing {rel_path}: {e}")
            sys.exit(1)

num_nodes = int(sys.argv[1]) if len(sys.argv) > 1 else 75
node_speed = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
p1_duration = float(sys.argv[3]) if len(sys.argv) > 3 else 10.0
sim_time = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0

# Airspace topologies to test:
# (spaceSize, spaceZ, Label)
spaces = [
    (300.0, 100.0, "300x300x100m (Original Sparse Baseline, ~3.0 neighbors)"),
    (230.0, 100.0, "230x230x100m (Theoretical Mean = 5.0 neighbors)"),
    (220.0, 80.0,  "220x220x80m  (Balanced ~6.4 neighbors, 71% >=5 neighbors)"),
    (200.0, 80.0,  "200x200x80m  (Saturated ~7.6 neighbors, 81% >=5 neighbors)"),
    (180.0, 70.0,  "180x180x70m  (Dense Saturated ~10.0 neighbors, 92% >=5 neighbors)")
]

results = []

for s_xy, s_z, label in spaces:
    print(f"\n-------------------------------------------------------------------------")
    print(f"▶️ Testing Airspace = {s_xy:.0f}m x {s_xy:.0f}m x {s_z:.0f}m ({label}) across {sim_time:.1f}s...")
    print(f"-------------------------------------------------------------------------")

    cmd = [
        "./ns3", "run",
        f"scratch/lr-wpan-swarm --numNodes={num_nodes} --nodeSpeed={node_speed} "
        f"--p1Duration={p1_duration} --p1TxPower=0 --p2TxPower=-2 --simTime={sim_time} "
        f"--p1CcaThresholdDbm=-96.58 --spaceSize={s_xy} --spaceZ={s_z} --enableP1Ssa=false"
    ]

    process = subprocess.Popen(
        cmd,
        cwd=NS3_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True
    )

    for line in process.stdout:
        if "[P1_CAPTURE]" in line or "Discovery Message" in line or "Beacon Packet Reception" in line or "Total Power Capture" in line:
            print(f"  {line.strip()}")

    process.wait()

    # Copy files
    for fname in ["p1_exact_drop_reasons.csv", "p1_ground_truth_report.txt", "metrics.txt"]:
        src_f = os.path.join(NS3_DIR, fname)
        dst_f = os.path.join(PROJECT_DIR, fname)
        if os.path.exists(src_f) and os.path.abspath(src_f) != os.path.abspath(dst_f):
            subprocess.run(["cp", src_f, dst_f])

    dst_csv = os.path.join(PROJECT_DIR, "p1_exact_drop_reasons.csv")
    dst_report = os.path.join(PROJECT_DIR, "p1_ground_truth_report.txt")
    dst_metrics = os.path.join(PROJECT_DIR, "metrics.txt")

    # Parse Report for Density metrics
    mean_neighbors = 0.0
    pct_ge5 = 0.0
    total_captures = 0
    if os.path.exists(dst_report):
        with open(dst_report, "r") as rf:
            rcontent = rf.read()
            m_nb = re.search(r"Mean 50m Neighbors per UAV \(Density\)\s*:\s*([\d\.]+)", rcontent)
            if m_nb: mean_neighbors = float(m_nb.group(1))
            m_ge5 = re.search(r"UAVs with >= 5 Neighbors in 50m\s*:\s*([\d\.]+)%", rcontent)
            if m_ge5: pct_ge5 = float(m_ge5.group(1))
            m_cap = re.search(r"Total Power Capture Events Triggered\s*:\s*(\d+)", rcontent)
            if m_cap: total_captures = int(m_cap.group(1))

    # Parse CSV for Physical drop reasons
    total_links = 0
    success_links = 0
    fails = defaultdict(int)

    if os.path.exists(dst_csv):
        with open(dst_csv, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                total_links += 1
                status = row["Status"]
                reason = row["ExactReason"]
                if status == "SUCCESS":
                    success_links += 1
                else:
                    fails[reason] += 1

    succ_pct = (success_links / total_links * 100.0) if total_links > 0 else 0.0
    coll_pct = (fails["PREAMBLE_COLLISION_BUSY_RX"] / total_links * 100.0) if total_links > 0 else 0.0
    abort_pct = (fails["SENDER_CSMA_ABORT"] / total_links * 100.0) if total_links > 0 else 0.0
    deaf_pct = (fails["RX_DEAFNESS_BUSY_TX"] / total_links * 100.0) if total_links > 0 else 0.0
    low_sinr_pct = (fails["PREAMBLE_LOW_SINR"] / total_links * 100.0) if total_links > 0 else 0.0

    # Parse metrics.txt for P2 and AoI
    p2_bcn_prr = 0.0
    mean_aoi = 0.0
    if os.path.exists(dst_metrics):
        with open(dst_metrics, "r") as mf:
            content = mf.read()
            m_bcn = re.search(r"Beacon Packet Reception Ratio\s*:\s*([\d\.]+)%", content)
            if m_bcn: p2_bcn_prr = float(m_bcn.group(1))
            m_aoi = re.search(r"Mean Beacon Packet AoI \(Top-K\)\s*:\s*([\d\.]+)\s*ms", content)
            if m_aoi: mean_aoi = float(m_aoi.group(1))

    # Calculate average Top-5 evaluated per drone-epoch
    # Total drone-epochs = 75 * epochs
    avg_topk_eval = (total_links / (75.0 * 28.0)) if total_links > 0 else 0.0

    results.append({
        "space_xy": s_xy,
        "space_z": s_z,
        "label": label,
        "mean_neighbors": mean_neighbors,
        "pct_ge5": pct_ge5,
        "total_links": total_links,
        "avg_topk_eval": avg_topk_eval,
        "p1_prr": succ_pct,
        "coll_pct": coll_pct,
        "captures": total_captures,
        "p2_prr": p2_bcn_prr,
        "mean_aoi": mean_aoi
    })

# Format Final Sweep Table
lines = []
lines.append("\n================================================================================================================================")
lines.append("          🎯 SWARM DENSITY & TOPOLOGY SWEEP SUMMARY (75 UAVs, P1 = 10ms with 3dB Capture Effect) 🎯")
lines.append("================================================================================================================================")
lines.append(f"{'Airspace Size':<16} | {'Mean 50m Nbrs':<13} | {'UAVs >=5 Nbrs':<13} | {'Top-K Links':<11} | {'P1 PRR':<8} | {'Collision':<9} | {'Captures':<8} | {'P2 PRR':<8} | {'AoI':<7}")
lines.append("-" * 128)

for r in results:
    lines.append(
        f"{r['space_xy']:.0f}x{r['space_xy']:.0f}x{r['space_z']:.0f}m       | "
        f"{r['mean_neighbors']:>5.2f} UAVs    | "
        f"{r['pct_ge5']:>5.1f}%       | "
        f"{r['total_links']:>5d}       | "
        f"{r['p1_prr']:>5.1f}%  | "
        f"{r['coll_pct']:>5.1f}%    | "
        f"{r['captures']:>5d}    | "
        f"{r['p2_prr']:>5.1f}%  | "
        f"{r['mean_aoi']:>4.1f}ms"
    )

lines.append("================================================================================================================================\n")
summary_txt = "\n".join(lines)
print(summary_txt)

with open("p1_density_sweep_summary.txt", "w") as f:
    f.write(summary_txt)

with open("p1_density_sweep.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=[
        "space_xy", "space_z", "label", "mean_neighbors", "pct_ge5",
        "total_links", "avg_topk_eval", "p1_prr", "coll_pct", "captures", "p2_prr", "mean_aoi"
    ])
    writer.writeheader()
    writer.writerows(results)

print("✅ Density sweep summary saved to p1_density_sweep_summary.txt and p1_density_sweep.csv")
