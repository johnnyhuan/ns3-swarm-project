#!/usr/bin/env python3
import subprocess
import os
import sys
import csv
import re
from collections import defaultdict

print("=========================================================================")
print("🔬 PHASE 1 BROADCAST WINDOW DURATION SWEEP BENCHMARK (5ms ~ 10ms) 🔬")
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
sim_time = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0

# 5ms to 10ms range (plus 12ms as upper reference)
durations = [5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 12.0]

results = []

for dur in durations:
    cycle_ms = dur + 1.0 + 25.0 # Phase 1 + 1ms gap + 10 slots * 2.5ms = dur + 26ms
    print(f"\n-------------------------------------------------------------------------")
    print(f"▶️ Testing Phase 1 Duration = {dur:.1f} ms (Cycle = {cycle_ms:.1f} ms) across {sim_time:.1f}s...")
    print(f"-------------------------------------------------------------------------")

    cmd = [
        "./ns3", "run",
        f"scratch/lr-wpan-swarm --numNodes={num_nodes} --nodeSpeed={node_speed} "
        f"--p1Duration={dur} --p1TxPower=0 --p2TxPower=-2 --simTime={sim_time} "
        f"--enableP1Sidelink=false"
    ]

    proc = subprocess.Popen(cmd, cwd=NS3_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    for line in proc.stdout:
        if "[P1_RX]" not in line and "[P1_ATTEMPT]" not in line and "[P2_" not in line and "Distance: " not in line:
            print(line, end="")
    proc.wait()

    # Move csv and metrics output
    src_csv = os.path.join(NS3_DIR, "p1_exact_drop_reasons.csv")
    dst_csv = os.path.join(PROJECT_DIR, f"p1_exact_drop_{dur:.0f}ms.csv")
    if os.path.exists(src_csv):
        subprocess.run(["cp", src_csv, dst_csv])

    src_metrics = os.path.join(NS3_DIR, "metrics.txt")
    dst_metrics = os.path.join(PROJECT_DIR, f"metrics_{dur:.0f}ms.txt")
    if os.path.exists(src_metrics):
        subprocess.run(["cp", src_metrics, dst_metrics])

    if not os.path.exists(dst_csv):
        print(f"❌ 錯誤: 未找到輸出 CSV {dst_csv}")
        continue

    # Parse CSV for Physical drop reasons
    total_links = 0
    success_links = 0
    fails = defaultdict(int)

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
    avg_iat = 0.0
    if os.path.exists(dst_metrics):
        with open(dst_metrics, "r") as mf:
            content = mf.read()
            m_bcn = re.search(r"Beacon Packet Reception Ratio\s*:\s*([\d\.]+)%", content)
            if m_bcn:
                p2_bcn_prr = float(m_bcn.group(1))
            m_aoi = re.search(r"Mean Beacon Packet AoI \(Top-K\)\s*:\s*([\d\.]+)\s*ms", content)
            if m_aoi:
                mean_aoi = float(m_aoi.group(1))
            m_iat = re.search(r"Avg Discovery Msg IAT \(Top-K\)\s*:\s*([\d\.]+)\s*ms", content)
            if m_iat:
                avg_iat = float(m_iat.group(1))

    results.append({
        "dur": dur,
        "cycle_ms": cycle_ms,
        "total_links": total_links,
        "success": success_links,
        "prr": succ_pct,
        "coll_pct": coll_pct,
        "abort_pct": abort_pct,
        "deaf_pct": deaf_pct,
        "low_sinr_pct": low_sinr_pct,
        "p2_prr": p2_bcn_prr,
        "mean_aoi": mean_aoi,
        "avg_iat": avg_iat
    })

# Format Final Sweep Table
lines = []
lines.append("\n========================================================================================================")
lines.append("       🎯 PHASE 1 BROADCAST 視窗長度掃描實驗總結 (5ms ~ 12ms, 2 Mbps BLE 5.4, 75 UAVs) 🎯")
lines.append("========================================================================================================")
lines.append(f"{'P1 視窗':<8s} | {'週期':<8s} | {'P1 成功率':<11s} | {'空中碰撞':<10s} | {'退讓放棄':<9s} | {'耳聾':<8s} | {'P2 成功率':<11s} | {'平均 AoI':<11s}")
lines.append("--------------------------------------------------------------------------------------------------------")

best_score = -1.0
best_dur = 5.0

for r in results:
    dur_str = f"{r['dur']:.0f} ms"
    cycle_str = f"{r['cycle_ms']:.1f} ms"
    prr_str = f"{r['prr']:.1f}%"
    coll_str = f"{r['coll_pct']:.1f}%"
    abort_str = f"{r['abort_pct']:.1f}%"
    deaf_str = f"{r['deaf_pct']:.1f}%"
    p2_str = f"{r['p2_prr']:.1f}%"
    aoi_str = f"{r['mean_aoi']:.1f} ms"

    # Trade-off score: high PRR + low AoI
    score = r["prr"] * 0.7 + (100.0 - min(100.0, r["mean_aoi"])) * 0.3
    if score > best_score:
        best_score = score
        best_dur = r["dur"]

    lines.append(f"{dur_str:<8s} | {cycle_str:<8s} | {prr_str:<11s} | {coll_str:<10s} | {abort_str:<9s} | {deaf_str:<8s} | {p2_str:<11s} | {aoi_str:<11s}")

lines.append("========================================================================================================")
lines.append(f"\n💡 綜合評估最佳甜蜜點 (Sweet Spot)：推薦 Phase 1 視窗 = {best_dur:.0f} ms")
lines.append("--------------------------------------------------------------------------------------------------------\n")

output_str = "\n".join(lines)
print(output_str)

with open(os.path.join(PROJECT_DIR, "p1_duration_sweep_summary.txt"), "w") as f:
    f.write(output_str)

# Also save CSV for plotting if needed
with open(os.path.join(PROJECT_DIR, "p1_duration_sweep.csv"), "w") as f:
    writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
    writer.writeheader()
    writer.writerows(results)
