#!/usr/bin/env python3
import subprocess
import os
import sys
import csv
from collections import defaultdict

print("=========================================================================")
print("🔬 PHASE 1 EXACT PHYSICAL LAYER GROUND TRUTH RUNNER & ANALYZER 🔬")
print("=========================================================================")

# Configuration parameters
num_nodes = int(sys.argv[1]) if len(sys.argv) > 1 else 75
node_speed = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
p1_duration = float(sys.argv[3]) if len(sys.argv) > 3 else 25.0
p1_power = int(sys.argv[4]) if len(sys.argv) > 4 else 0
enable_sidelink = (sys.argv[5].lower() in ["true", "1", "yes"]) if len(sys.argv) > 5 else True
p1_slot_us = float(sys.argv[6]) if len(sys.argv) > 6 else 800.0
sim_time = float(sys.argv[7]) if len(sys.argv) > 7 else 10.0

print(f"• Swarm Scale    : {num_nodes} UAVs")
print(f"• Flight Speed   : {node_speed} m/s (3D Random Waypoint)")
print(f"• Phase 1 Window : {p1_duration} ms")
print(f"• Phase 1 Power  : {p1_power:+d} dBm")
print(f"• Sim Duration   : {sim_time:.1f} s (Steady-State convergence evaluated on last 2.0s)")
print(f"• P1 Mechanism   : {'Sidelink Semi-Persistent Scheduling (S-SPS + CSMA)' if enable_sidelink else 'Legacy Continuous Random Delay'}")
if enable_sidelink:
    total_slots = int(max(1, (p1_duration * 1000.0 - 2000.0) / p1_slot_us))
    print(f"• P1 Slot Size   : {p1_slot_us:.0f} µs ({total_slots} slots available)")
print("-------------------------------------------------------------------------\n")

# Detect paths
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
NS3_DIR = os.path.expanduser("~/ns-3-dev")

if not os.path.exists(NS3_DIR):
    NS3_DIR = PROJECT_DIR

# 1. Sync updated lr-wpan-swarm.cc to NS3_DIR
src_cc = os.path.join(PROJECT_DIR, "scratch/lr-wpan-swarm.cc")
dst_cc = os.path.join(NS3_DIR, "scratch/lr-wpan-swarm.cc")

if os.path.abspath(src_cc) != os.path.abspath(dst_cc):
    try:
        print(f"=> Syncing {src_cc} to {dst_cc}...")
        subprocess.run(["cp", src_cc, dst_cc], check=True)
    except Exception as e:
        print(f"Error syncing code: {e}")
        sys.exit(1)

# 2. Run simulation
sidelink_flag = f"--enableP1Sidelink=true --p1SlotUs={p1_slot_us}" if enable_sidelink else "--enableP1Sidelink=false"
cmd = [
    "./ns3", "run",
    f"scratch/lr-wpan-swarm --numNodes={num_nodes} --nodeSpeed={node_speed} "
    f"--p1Duration={p1_duration} --p1TxPower={p1_power} --p2TxPower=-2 --simTime={sim_time} {sidelink_flag}"
]

print(f"=> Executing in {NS3_DIR}:\n   {' '.join(cmd)}\n")
print("========================== SIMULATION LOGS ==============================")

process = subprocess.Popen(
    cmd,
    cwd=NS3_DIR,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    universal_newlines=True
)

for line in process.stdout:
    print(line, end="")

process.wait()
print("=========================================================================\n")

# 3. Copy output artifacts back to PROJECT_DIR if run in separate NS3_DIR
for fname in ["p1_exact_drop_reasons.csv", "p1_ground_truth_report.txt"]:
    src_f = os.path.join(NS3_DIR, fname)
    dst_f = os.path.join(PROJECT_DIR, fname)
    if os.path.exists(src_f) and os.path.abspath(src_f) != os.path.abspath(dst_f):
        subprocess.run(["cp", src_f, dst_f])

csv_path = os.path.join(PROJECT_DIR, "p1_exact_drop_reasons.csv")
if not os.path.exists(csv_path):
    print(f"❌ Error: {csv_path} not found. Did the simulation finish correctly?")
    sys.exit(1)

# 4. Parse Ground Truth CSV & Generate Visualizations
print(f"=> Parsing exact link records from {csv_path}...")

cycle_ms = p1_duration + 1.0 + 10 * 2.5 # ~51 ms
steady_start_sec = max(0.0, sim_time - 2.0)
steady_start_epoch = int(steady_start_sec * 1000.0 / cycle_ms) + 1

total_links = 0
success_links = 0
fail_reasons = defaultdict(int)
dist_brackets = ["0-10m", "10-20m", "20-30m", "30-40m", "40-50m"]
bracket_counts = {b: defaultdict(int) for b in dist_brackets}

steady_total = 0
steady_success = 0
steady_fails = defaultdict(int)
steady_bracket_counts = {b: defaultdict(int) for b in dist_brackets}

with open(csv_path, "r") as f:
    reader = csv.DictReader(f)
    for row in reader:
        total_links += 1
        epoch = int(row["Epoch"])
        status = row["Status"]
        reason = row["ExactReason"]
        dist = float(row["Distance_m"])
        
        # Determine bracket
        if dist < 10.0: b_idx = "0-10m"
        elif dist < 20.0: b_idx = "10-20m"
        elif dist < 30.0: b_idx = "20-30m"
        elif dist < 40.0: b_idx = "30-40m"
        else: b_idx = "40-50m"

        bracket_counts[b_idx]["TOTAL"] += 1
        
        if status == "SUCCESS":
            success_links += 1
            bracket_counts[b_idx]["SUCCESS"] += 1
        else:
            fail_reasons[reason] += 1
            bracket_counts[b_idx][reason] += 1

        # Steady-state window (Last 2.0s)
        if epoch >= steady_start_epoch:
            steady_total += 1
            steady_bracket_counts[b_idx]["TOTAL"] += 1
            if status == "SUCCESS":
                steady_success += 1
                steady_bracket_counts[b_idx]["SUCCESS"] += 1
            else:
                steady_fails[reason] += 1
                steady_bracket_counts[b_idx][reason] += 1

total_fails = total_links - success_links
steady_total_fails = steady_total - steady_success

print(f"\n=========================================================================")
print(f"📊 FULL SIMULATION SUMMARY ({sim_time:.1f}s Total, 0 ~ {sim_time:.1f}s):")
print(f"• Total Target Links (50m Top-K) : {total_links:,}")
print(f"• Successfully Delivered         : {success_links:,} ({(success_links/total_links)*100:.1f}%)")
print(f"• Dropped / Failed Links         : {total_fails:,} ({(total_fails/total_links)*100:.1f}%)")

if steady_total > 0:
    print(f"\n🎯 STEADY-STATE CONVERGED SUMMARY (Last 2.0s: {steady_start_sec:.1f}s ~ {sim_time:.1f}s | Epoch {steady_start_epoch}+):")
    print(f"• Steady-State Target Links      : {steady_total:,}")
    print(f"• Successfully Delivered         : {steady_success:,} ({(steady_success/steady_total)*100:.1f}%)")
    print(f"• Dropped / Failed Links         : {steady_total_fails:,} ({(steady_total_fails/steady_total)*100:.1f}%)")

labels_map = {
    "PREAMBLE_COLLISION_BUSY_RX": "Preamble Collision (BUSY_RX)",
    "PREAMBLE_LOW_SINR": "Preamble Low SINR (<= -5dB)",
    "RX_DEAFNESS_BUSY_TX": "Receiver Deafness (BUSY_TX)",
    "SENDER_CSMA_ABORT": "Sender CSMA Abort",
    "RADIO_TURNAROUND_BUSY": "Radio Turnaround / Transient Busy",
    "PAYLOAD_INTERFERENCE_CORRUPTION": "Payload Interference (PER Error)"
}

colors_map = {
    "PREAMBLE_COLLISION_BUSY_RX": "#e67e22",         # Orange
    "PREAMBLE_LOW_SINR": "#f1c40f",                  # Yellow
    "RX_DEAFNESS_BUSY_TX": "#e74c3c",                # Coral Red
    "SENDER_CSMA_ABORT": "#3498db",                  # Sky Blue
    "RADIO_TURNAROUND_BUSY": "#95a5a6",              # Gray
    "PAYLOAD_INTERFERENCE_CORRUPTION": "#9b59b6"     # Purple
}

plot_order = [
    "PREAMBLE_COLLISION_BUSY_RX",
    "PREAMBLE_LOW_SINR",
    "SENDER_CSMA_ABORT",
    "RADIO_TURNAROUND_BUSY",
    "RX_DEAFNESS_BUSY_TX",
    "PAYLOAD_INTERFERENCE_CORRUPTION"
]

if steady_total > 0:
    print("-------------------------------------------------------------------------")
    print("Steady-State Failure Causes Breakdown:")
    for r_key in plot_order:
        cnt = steady_fails.get(r_key, 0)
        pct = (cnt / steady_total_fails) * 100.0 if steady_total_fails > 0 else 0
        pct_tot = (cnt / steady_total) * 100.0 if steady_total > 0 else 0
        print(f"  • {labels_map[r_key]:32s}: {cnt:5,d} ({pct:5.1f}% of fails | {pct_tot:4.1f}% of all links)")
print("=========================================================================\n")

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'Helvetica']
    plt.rcParams['axes.unicode_minus'] = False

    # Choose dataset for visualization (Steady-state if available, else total)
    plot_fails = steady_fails if steady_total > 0 else fail_reasons
    plot_total_fails = steady_total_fails if steady_total > 0 else total_fails
    plot_total = steady_total if steady_total > 0 else total_links
    plot_success = steady_success if steady_total > 0 else success_links
    plot_brackets = steady_bracket_counts if steady_total > 0 else bracket_counts
    time_label = f"Steady-State (Last 2.0s: {steady_start_sec:.1f}s~{sim_time:.1f}s)" if steady_total > 0 else f"Full {sim_time:.1f}s"

    plot_labels = []
    plot_sizes = []
    plot_colors = []

    for r_key in plot_order:
        cnt = plot_fails.get(r_key, 0)
        if cnt > 0:
            r_name = labels_map[r_key]
            pct = (cnt / plot_total_fails) * 100.0 if plot_total_fails > 0 else 0
            plot_labels.append(f"{r_name}\n({cnt:,} links, {pct:.1f}%)")
            plot_sizes.append(cnt)
            plot_colors.append(colors_map[r_key])

    fig, ax = plt.subplots(figsize=(10.5, 8.5), subplot_kw=dict(aspect="equal"))
    wedges, texts = ax.pie(
        plot_sizes,
        labels=plot_labels,
        colors=plot_colors,
        startangle=140,
        wedgeprops=dict(width=0.4, edgecolor='white', linewidth=2),
        textprops=dict(fontsize=11)
    )

    ax.set_title(f"Phase 1 Physical Failure Breakdown [{time_label}, 75 UAVs]\n"
                 f"Target Links: {plot_total:,} | Success: {plot_success:,} ({(plot_success/plot_total)*100:.1f}%) | "
                 f"Failed: {plot_total_fails:,} ({(plot_total_fails/plot_total)*100:.1f}%)",
                 fontsize=13, fontweight='bold', pad=20)

    donut_path = os.path.join(PROJECT_DIR, "p1_ground_truth_donut.png")
    plt.savefig(donut_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"📈 Donut chart saved to: {donut_path}")

    # 2. Stacked Bar Chart across Distance Brackets
    fig, ax = plt.subplots(figsize=(11, 6.5))
    x = range(len(dist_brackets))
    
    categories = [
        ("PREAMBLE_COLLISION_BUSY_RX", "Preamble Collision (BUSY_RX)", colors_map["PREAMBLE_COLLISION_BUSY_RX"]),
        ("PREAMBLE_LOW_SINR", "Preamble Low SINR", colors_map["PREAMBLE_LOW_SINR"]),
        ("RX_DEAFNESS_BUSY_TX", "Receiver Deafness (BUSY_TX)", colors_map["RX_DEAFNESS_BUSY_TX"]),
        ("SENDER_CSMA_ABORT", "Sender CSMA Abort", colors_map["SENDER_CSMA_ABORT"]),
        ("RADIO_TURNAROUND_BUSY", "Radio Turnaround Busy", colors_map["RADIO_TURNAROUND_BUSY"]),
        ("PAYLOAD_INTERFERENCE_CORRUPTION", "Payload Interference", colors_map["PAYLOAD_INTERFERENCE_CORRUPTION"])
    ]

    bottoms = [0] * len(dist_brackets)
    for cat_key, cat_name, cat_color in categories:
        vals = [plot_brackets[b][cat_key] for b in dist_brackets]
        if sum(vals) > 0:
            ax.bar(x, vals, bottom=bottoms, label=f"{cat_name} (Total: {sum(vals):,})", color=cat_color, width=0.55, edgecolor='black', linewidth=0.5)
            bottoms = [bottoms[i] + vals[i] for i in range(len(dist_brackets))]

    ax.set_xticks(x)
    ax.set_xticklabels(dist_brackets, fontsize=11, fontweight='bold')
    ax.set_xlabel("Distance Bracket between UAVs", fontsize=12, fontweight='bold', labelpad=10)
    ax.set_ylabel("Number of Failed Link Receptions", fontsize=12, fontweight='bold')
    ax.set_title(f"Phase 1 Failure Causes vs. Spatial Distance [{time_label}]", fontsize=13, fontweight='bold', pad=15)
    ax.legend(loc="upper right", frameon=True, fontsize=10, edgecolor='#bdc3c7')
    ax.grid(axis='y', linestyle='--', alpha=0.5)

    dist_path = os.path.join(PROJECT_DIR, "p1_ground_truth_distance.png")
    plt.savefig(dist_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"📈 Distance breakdown chart saved to: {dist_path}")
    ax.legend(loc="upper right", frameon=True, fontsize=10, edgecolor='#bdc3c7')
    ax.grid(axis='y', linestyle='--', alpha=0.5)

    dist_path = os.path.join(PROJECT_DIR, "p1_ground_truth_distance.png")
    plt.savefig(dist_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"📈 Distance breakdown chart saved to: {dist_path}")
    plt.close()
    print(f"📈 Distance breakdown chart saved to: {dist_path}")

except Exception as e:
    print(f"Note: Could not generate matplotlib plot: {e}")

print("\n=========================================================================")
print("✅ EXECUTION COMPLETE! All data files generated.")
print("=========================================================================")
print("Files ready for commit & push to GitHub:")
print("  • scratch/lr-wpan-swarm.cc")
print("  • p1_exact_drop_reasons.csv (Raw link-by-link data)")
print("  • p1_ground_truth_report.txt (Full numerical summary)")
print("  • p1_ground_truth_donut.png")
print("  • p1_ground_truth_distance.png")
print("-------------------------------------------------------------------------")
print("👉 You can now run:")
print("   git add scratch/lr-wpan-swarm.cc p1_exact_drop_reasons.csv p1_ground_truth_report.txt p1_ground_truth_donut.png p1_ground_truth_distance.png run_p1_exact_analysis.py")
print("   git commit -m 'data: exact Phase 1 physical ground truth results'")
print("   git push origin main")
print("=========================================================================\n")
