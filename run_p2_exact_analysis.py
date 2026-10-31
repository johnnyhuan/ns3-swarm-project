#!/usr/bin/env python3
import subprocess
import os
import sys
import csv
from collections import defaultdict

print("=========================================================================")
print("🔬 PHASE 2 EXACT PHYSICAL LAYER GROUND TRUTH RUNNER & ANALYZER 🔬")
print("=========================================================================")

# Configuration parameters (Default 75 UAVs, 10 m/s RWP, P1=0 dBm, P2=-2 dBm, 10 slots)
num_nodes = int(sys.argv[1]) if len(sys.argv) > 1 else 75
node_speed = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
p2_power = int(sys.argv[3]) if len(sys.argv) > 3 else -2
num_slots = int(sys.argv[4]) if len(sys.argv) > 4 else 10

print(f"• Swarm Scale    : {num_nodes} UAVs")
print(f"• Flight Speed   : {node_speed} m/s (3D Random Waypoint)")
print(f"• Phase 2 Power  : {p2_power:+d} dBm")
print(f"• Phase 2 Slots  : {num_slots} slots (2.5ms each)")
print(f"• Observation    : Exact link-by-link Ground Truth (Top-K within 50m)")
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
cmd = [
    "./ns3", "run",
    f"scratch/lr-wpan-swarm --numNodes={num_nodes} --nodeSpeed={node_speed} "
    f"--p1Duration=25 --p1TxPower=0 --p2TxPower={p2_power} --numSlots={num_slots} --numChannels=6 --p1AvoidDist=50"
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
for fname in ["p2_exact_drop_reasons.csv", "p2_ground_truth_report.txt"]:
    src_f = os.path.join(NS3_DIR, fname)
    dst_f = os.path.join(PROJECT_DIR, fname)
    if os.path.exists(src_f) and os.path.abspath(src_f) != os.path.abspath(dst_f):
        subprocess.run(["cp", src_f, dst_f])

csv_path = os.path.join(PROJECT_DIR, "p2_exact_drop_reasons.csv")
if not os.path.exists(csv_path):
    print(f"❌ Error: {csv_path} not found. Did the simulation finish correctly?")
    sys.exit(1)

# 4. Parse Ground Truth CSV & Generate Visualizations
print(f"=> Parsing Phase 2 exact link records from {csv_path}...")

total_links = 0
success_links = 0
fail_reasons = defaultdict(int)
dist_brackets = ["0-10m", "10-20m", "20-30m", "30-40m", "40-50m"]
bracket_counts = {b: defaultdict(int) for b in dist_brackets}

with open(csv_path, "r") as f:
    reader = csv.DictReader(f)
    for row in reader:
        total_links += 1
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

total_fails = total_links - success_links
print(f"\n📊 Summary Extracted:")
print(f"• Total Target Links (50m Top-K) : {total_links}")
print(f"• Successfully Delivered (PRR)   : {success_links} ({(success_links/total_links)*100:.1f}%)")
print(f"• Dropped / Failed Links         : {total_fails} ({(total_fails/total_links)*100:.1f}%)")

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'Helvetica']
    plt.rcParams['axes.unicode_minus'] = False

    # 1. Donut Chart for Failures (Exact Original Style with Direct Slice Labels)
    # Order structured so large slices insulate smaller slices, preventing text overlap
    labels_map = {
        "P1_DISCOVERY_MISS": "P1 Discovery Miss (Unscheduled)",
        "TX_DEAFNESS_SAME_SLOT": "TX Deafness (Same Slot as TX)",
        "RX_DEAFNESS_SLOT_CONFLICT": "RX Deafness (Slot Conflict)",
        "PAYLOAD_INTERFERENCE_DROP": "Payload Interference Corruption",
        "PREAMBLE_COLLISION_OR_LOW_SINR": "Preamble Collision / Low SINR",
        "RECEIVER_CHANNEL_MISMATCH": "Receiver Channel Mismatch",
        "RADIO_TURNAROUND_BUSY": "Radio Turnaround / Transient Busy",
        "SENDER_CSMA_ABORT": "Sender CSMA Abort"
    }

    colors_map = {
        "P1_DISCOVERY_MISS": "#9b59b6",                 # Purple (Phase 1 cascade)
        "TX_DEAFNESS_SAME_SLOT": "#e74c3c",             # Coral Red (Transmitting)
        "RX_DEAFNESS_SLOT_CONFLICT": "#3498db",         # Sky Blue (Listening to someone else)
        "PAYLOAD_INTERFERENCE_DROP": "#e67e22",         # Deep Orange (Mid-flight interference)
        "PREAMBLE_COLLISION_OR_LOW_SINR": "#f1c40f",    # Yellow (Preamble collision/weak)
        "RECEIVER_CHANNEL_MISMATCH": "#1abc9c",         # Teal (Channel mismatch)
        "RADIO_TURNAROUND_BUSY": "#95a5a6",             # Gray (Radio turnaround / transient)
        "SENDER_CSMA_ABORT": "#2ecc71"                  # Emerald Green (Sender CSMA abort)
    }

    plot_labels = []
    plot_sizes = []
    plot_colors = []

    for r_key, r_name in labels_map.items():
        cnt = fail_reasons.get(r_key, 0)
        if cnt > 0:
            pct = (cnt / total_fails) * 100.0 if total_fails > 0 else 0
            plot_labels.append(f"{r_name}\n({cnt:,} links, {pct:.1f}%)")
            plot_sizes.append(cnt)
            plot_colors.append(colors_map[r_key])

    fig, ax = plt.subplots(figsize=(10.5, 8.5), subplot_kw=dict(aspect="equal"))
    wedges, texts = ax.pie(
        plot_sizes,
        labels=plot_labels,
        colors=plot_colors,
        startangle=130,
        wedgeprops=dict(width=0.4, edgecolor='white', linewidth=2),
        textprops=dict(fontsize=10.5)
    )

    ax.set_title(f"Phase 2 Exact Physical Failure Breakdown [75 UAVs, 50m Top-5 Links]\n"
                 f"Total Links: {total_links:,} | Success: {success_links:,} ({(success_links/total_links)*100:.1f}%) | "
                 f"Failed: {total_fails:,} ({(total_fails/total_links)*100:.1f}%)",
                 fontsize=13, fontweight='bold', pad=20)

    donut_path = os.path.join(PROJECT_DIR, "p2_ground_truth_donut.png")
    plt.tight_layout()
    plt.savefig(donut_path, dpi=300)
    plt.close()
    print(f"📈 Phase 2 Donut chart saved to: {donut_path}")

    # 2. Stacked Bar Chart across Distance Brackets
    fig, ax = plt.subplots(figsize=(11, 6.5))
    x = range(len(dist_brackets))
    
    categories = [
        ("P1_DISCOVERY_MISS", "P1 Discovery Miss", colors_map["P1_DISCOVERY_MISS"]),
        ("TX_DEAFNESS_SAME_SLOT", "TX Deafness (Same Slot)", colors_map["TX_DEAFNESS_SAME_SLOT"]),
        ("RX_DEAFNESS_SLOT_CONFLICT", "RX Deafness (Slot Conflict)", colors_map["RX_DEAFNESS_SLOT_CONFLICT"]),
        ("PAYLOAD_INTERFERENCE_DROP", "Payload Interference", colors_map["PAYLOAD_INTERFERENCE_DROP"]),
        ("PREAMBLE_COLLISION_OR_LOW_SINR", "Preamble Collision / Low SINR", colors_map["PREAMBLE_COLLISION_OR_LOW_SINR"]),
        ("RECEIVER_CHANNEL_MISMATCH", "Channel Mismatch", colors_map["RECEIVER_CHANNEL_MISMATCH"]),
        ("RADIO_TURNAROUND_BUSY", "Radio Turnaround Busy", colors_map["RADIO_TURNAROUND_BUSY"]),
        ("SENDER_CSMA_ABORT", "Sender CSMA Abort", colors_map["SENDER_CSMA_ABORT"])
    ]

    bottoms = [0] * len(dist_brackets)
    for cat_key, cat_name, cat_color in categories:
        vals = [bracket_counts[b][cat_key] for b in dist_brackets]
        if sum(vals) > 0:
            ax.bar(x, vals, bottom=bottoms, label=f"{cat_name} (Total: {sum(vals):,})", color=cat_color, width=0.55, edgecolor='black', linewidth=0.5)
            bottoms = [bottoms[i] + vals[i] for i in range(len(dist_brackets))]

    ax.set_xticks(x)
    ax.set_xticklabels(dist_brackets, fontsize=11, fontweight='bold')
    ax.set_xlabel("Distance Bracket between UAVs", fontsize=12, fontweight='bold', labelpad=10)
    ax.set_ylabel("Number of Failed Link Receptions", fontsize=12, fontweight='bold')
    ax.set_title("Phase 2 Failure Causes vs. Spatial Distance (Ground Truth)", fontsize=13, fontweight='bold', pad=15)
    ax.legend(loc="upper right", frameon=True, fontsize=10, edgecolor='#bdc3c7')
    ax.grid(axis='y', linestyle='--', alpha=0.5)

    dist_path = os.path.join(PROJECT_DIR, "p2_ground_truth_distance.png")
    plt.tight_layout()
    plt.savefig(dist_path, dpi=300)
    plt.close()
    print(f"📈 Phase 2 Distance breakdown chart saved to: {dist_path}")

except Exception as e:
    print(f"Note: Could not generate matplotlib plot: {e}")

print("\n=========================================================================")
print("✅ EXECUTION COMPLETE! All Phase 2 Ground Truth files generated.")
print("=========================================================================")
print("Files ready for commit & push to GitHub:")
print("  • scratch/lr-wpan-swarm.cc")
print("  • p2_exact_drop_reasons.csv (Raw link-by-link data)")
print("  • p2_ground_truth_report.txt (Full numerical summary)")
print("  • p2_ground_truth_donut.png (Publication-quality Donut Chart)")
print("  • p2_ground_truth_distance.png (Distance Bracket Bar Chart)")
print("-------------------------------------------------------------------------")
print("👉 You can now run:")
print("   git add scratch/lr-wpan-swarm.cc p2_exact_drop_reasons.csv p2_ground_truth_report.txt p2_ground_truth_donut.png p2_ground_truth_distance.png run_p2_exact_analysis.py")
print("   git commit -m 'data: Phase 2 exact physical ground truth results'")
print("   git push origin main")
print("=========================================================================\n")
