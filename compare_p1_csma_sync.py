#!/usr/bin/env python3
import subprocess
import os
import sys
import csv
from collections import defaultdict

print("=========================================================================")
print("🔬 PHASE 1 CSMA SYNC BENCHMARK SUITE: BASELINE vs 100m vs 50m SYNC 🔬")
print("=========================================================================")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
NS3_DIR = os.path.expanduser("~/ns-3-dev")
if not os.path.exists(NS3_DIR):
    NS3_DIR = PROJECT_DIR

# Sync scratch/lr-wpan-swarm.cc and modified BLE 5.4 PHY files to NS3_DIR if needed
sync_files = [
    "scratch/lr-wpan-swarm.cc",
    "src/lr-wpan/model/lr-wpan-phy.cc",
    "src/lr-wpan/model/lr-wpan-constants.h"
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

num_nodes = int(sys.argv[1]) if len(sys.argv) > 1 else 75
node_speed = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
sim_time = float(sys.argv[3]) if len(sys.argv) > 3 else 10.0

cases = [
    {
        "id": "baseline",
        "name": "原版基準 (Baseline)",
        "desc": "廣播 100m / CSMA 46.1m (脫節)",
        "p1_power": 0,
        "cca_thresh": -96.58
    },
    {
        "id": "sync_100m",
        "name": "方案一 (100m 同步)",
        "desc": "廣播 100m / CSMA 100m (全面同步)",
        "p1_power": 0,
        "cca_thresh": -106.58
    },
    {
        "id": "sync_50m",
        "name": "方案二 (50m 同步)",
        "desc": "廣播 50m / CSMA 50m (聚焦同步)",
        "p1_power": -9,
        "cca_thresh": -106.58
    }
]

results = []

for idx, c in enumerate(cases, 1):
    print(f"\n=========================================================================")
    print(f"🚀 [{idx}/3] 正在執行: {c['name']} - {c['desc']}")
    print(f"   參數: P1 Power = {c['p1_power']:+d} dBm, CCA 門檻 = {c['cca_thresh']:.2f} dBm, SimTime = {sim_time}s")
    print(f"=========================================================================")

    cmd = [
        "./ns3", "run",
        f"scratch/lr-wpan-swarm --numNodes={num_nodes} --nodeSpeed={node_speed} "
        f"--p1Duration=25.0 --p1TxPower={c['p1_power']} --p2TxPower=-2 --simTime={sim_time} "
        f"--enableP1Sidelink=false --p1CcaThresholdDbm={c['cca_thresh']}"
    ]

    print(f"=> Executing in {NS3_DIR}:\n   {' '.join(cmd)}\n")

    proc = subprocess.Popen(cmd, cwd=NS3_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    for line in proc.stdout:
        # Filter noisy logs, print key steps
        if "[P1_RX]" not in line and "[P1_ATTEMPT]" not in line and "[P2_" not in line and "Distance: " not in line:
            print(line, end="")
    proc.wait()

    # Move csv output
    src_csv = os.path.join(NS3_DIR, "p1_exact_drop_reasons.csv")
    dst_csv = os.path.join(PROJECT_DIR, f"p1_exact_drop_{c['id']}.csv")
    if os.path.exists(src_csv):
        subprocess.run(["cp", src_csv, dst_csv])
    
    if not os.path.exists(dst_csv):
        print(f"❌ 錯誤: 未找到輸出 CSV {dst_csv}")
        continue

    # Parse results
    total_links = 0
    success_links = 0
    fails = defaultdict(int)

    cycle_ms = 51.0
    steady_start_epoch = int((sim_time - 2.0) * 1000.0 / cycle_ms) + 1 if sim_time >= 4.0 else 0
    steady_total = 0
    steady_success = 0
    steady_fails = defaultdict(int)

    with open(dst_csv, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_links += 1
            epoch = int(row["Epoch"])
            status = row["Status"]
            reason = row["ExactReason"]

            if status == "SUCCESS":
                success_links += 1
            else:
                fails[reason] += 1

            if epoch >= steady_start_epoch:
                steady_total += 1
                if status == "SUCCESS":
                    steady_success += 1
                else:
                    steady_fails[reason] += 1

    succ_pct = (success_links / total_links * 100.0) if total_links > 0 else 0
    steady_succ_pct = (steady_success / steady_total * 100.0) if steady_total > 0 else 0

    results.append({
        "case": c,
        "total": total_links,
        "success": success_links,
        "succ_pct": succ_pct,
        "steady_total": steady_total,
        "steady_success": steady_success,
        "steady_succ_pct": steady_succ_pct,
        "fails": fails,
        "steady_fails": steady_fails
    })

# Format Final Comparison Table
summary_lines = []
summary_lines.append("\n========================================================================================================")
summary_lines.append("                📊 PHASE 1 CSMA 距離同步實驗：三大架構核心指標對照總結 📊")
summary_lines.append("========================================================================================================")
summary_lines.append(f"{'指標項目':<30s} | {'原版基準 (Baseline)':<22s} | {'方案一 (100m 同步)':<22s} | {'方案二 (50m 同步)':<22s}")
summary_lines.append("--------------------------------------------------------------------------------------------------------")

def fmt_val(idx, field, is_pct=False, is_fail_key=None):
    if idx >= len(results):
        return "N/A"
    res = results[idx]
    if is_fail_key:
        cnt = res["fails"].get(is_fail_key, 0)
        tot = res["total"]
        pct = (cnt / tot * 100.0) if tot > 0 else 0
        return f"{cnt:,d} ({pct:.1f}%)"
    if field == "succ_pct":
        return f"{res['success']:,d} ({res['succ_pct']:.1f}%)"
    if field == "steady_succ_pct":
        return f"{res['steady_success']:,d} ({res['steady_succ_pct']:.1f}%)"
    return str(res.get(field, "N/A"))

summary_lines.append(f"{'P1 發射功率 (TX Power)':<30s} | {'0 dBm (~100m)':<22s} | {'0 dBm (~100m)':<22s} | {'-9 dBm (~50m)':<22s}")
summary_lines.append(f"{'CSMA 能量偵聽門檻 (CCA)':<30s} | {'-96.58 dBm (46.1m)':<22s} | {'-106.58 dBm (100m)':<22s} | {'-106.58 dBm (50m)':<22s}")
summary_lines.append(f"{'空間感知匹配狀態':<30s} | {'嚴重脫節 (盲區 54m)':<22s} | {'全面同步 (100m:100m)':<22s} | {'聚焦同步 (50m:50m)':<22s}")
summary_lines.append("--------------------------------------------------------------------------------------------------------")
summary_lines.append(f"{'總目標通訊鏈路 (50m Top-5)':<30s} | {fmt_val(0, 'total'):<22s} | {fmt_val(1, 'total'):<22s} | {fmt_val(2, 'total'):<22s}")
summary_lines.append(f"{'0~10s 全程平均成功率 (PRR)':<30s} | {fmt_val(0, 'succ_pct'):<22s} | {fmt_val(1, 'succ_pct'):<22s} | {fmt_val(2, 'succ_pct'):<22s}")
summary_lines.append(f"{'8~10s 穩定態成功率 (PRR)':<30s} | {fmt_val(0, 'steady_succ_pct'):<22s} | {fmt_val(1, 'steady_succ_pct'):<22s} | {fmt_val(2, 'steady_succ_pct'):<22s}")
summary_lines.append("--------------------------------------------------------------------------------------------------------")
summary_lines.append("【失敗物理根因分析 (佔總目標鏈路比例)】:")
summary_lines.append(f"{'  • 空中碰撞 (PREAMBLE_COLLISION)':<30s} | {fmt_val(0, None, is_fail_key='PREAMBLE_COLLISION_BUSY_RX'):<22s} | {fmt_val(1, None, is_fail_key='PREAMBLE_COLLISION_BUSY_RX'):<22s} | {fmt_val(2, None, is_fail_key='PREAMBLE_COLLISION_BUSY_RX'):<22s}")
summary_lines.append(f"{'  • 退讓放棄 (CSMA_ABORT)':<30s} | {fmt_val(0, None, is_fail_key='SENDER_CSMA_ABORT'):<22s} | {fmt_val(1, None, is_fail_key='SENDER_CSMA_ABORT'):<22s} | {fmt_val(2, None, is_fail_key='SENDER_CSMA_ABORT'):<22s}")
summary_lines.append(f"{'  • 發射耳聾 (RX_DEAFNESS)':<30s} | {fmt_val(0, None, is_fail_key='RX_DEAFNESS_BUSY_TX'):<22s} | {fmt_val(1, None, is_fail_key='RX_DEAFNESS_BUSY_TX'):<22s} | {fmt_val(2, None, is_fail_key='RX_DEAFNESS_BUSY_TX'):<22s}")
summary_lines.append(f"{'  • 低訊噪比 (LOW_SINR)':<30s} | {fmt_val(0, None, is_fail_key='PREAMBLE_LOW_SINR'):<22s} | {fmt_val(1, None, is_fail_key='PREAMBLE_LOW_SINR'):<22s} | {fmt_val(2, None, is_fail_key='PREAMBLE_LOW_SINR'):<22s}")
summary_lines.append("========================================================================================================\n")

summary_text = "\n".join(summary_lines)
print(summary_text)

# Save text report
report_path = os.path.join(PROJECT_DIR, "p1_csma_sync_comparison.txt")
with open(report_path, "w") as f:
    f.write(summary_text)
print(f"📄 對照總結報告已儲存至: {report_path}")

# Plot comparison chart
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    labels = [c["name"] for c in cases]
    succ_rates = [r["succ_pct"] for r in results]
    coll_rates = [(r["fails"].get("PREAMBLE_COLLISION_BUSY_RX", 0) / r["total"] * 100.0) if r["total"] > 0 else 0 for r in results]
    abort_rates = [(r["fails"].get("SENDER_CSMA_ABORT", 0) / r["total"] * 100.0) if r["total"] > 0 else 0 for r in results]

    x = np.arange(len(labels))
    width = 0.25

    fig, ax = plt.subplots(figsize=(10, 6))
    r1 = ax.bar(x - width, succ_rates, width, label='P1 成功率 (PRR)', color='#2ecc71')
    r2 = ax.bar(x, coll_rates, width, label='空中碰撞率 (Collision)', color='#e67e22')
    r3 = ax.bar(x + width, abort_rates, width, label='退讓放棄率 (CSMA Abort)', color='#3498db')

    ax.set_ylabel('百分比 (%)', fontsize=12)
    ax.set_title('Phase 1 CSMA 距離同步架構對照 (75 UAVs, 3D RWP 10m/s)', fontsize=14, fontweight='bold', pad=15)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=11)
    ax.legend(fontsize=11)
    ax.grid(axis='y', linestyle='--', alpha=0.5)

    for rects in [r1, r2, r3]:
        for rect in rects:
            h = rect.get_height()
            ax.annotate(f'{h:.1f}%',
                        xy=(rect.get_x() + rect.get_width() / 2, h),
                        xytext=(0, 3),  # 3 points vertical offset
                        textcoords="offset points",
                        ha='center', va='bottom', fontsize=10, fontweight='bold')

    plt.tight_layout()
    plot_path = os.path.join(PROJECT_DIR, "p1_csma_sync_comparison.png")
    plt.savefig(plot_path, dpi=300)
    plt.close()
    print(f"📈 對照視覺化圖表已儲存至: {plot_path}")
except Exception as e:
    print(f"繪圖跳過: {e}")
