#!/usr/bin/env python3
import csv
import os
from collections import defaultdict
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
csv_path = os.path.join(PROJECT_DIR, "p1_exact_drop_reasons.csv")

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

plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'Helvetica']
plt.rcParams['axes.unicode_minus'] = False

# Mapping in original order
labels_map = {
    "RX_DEAFNESS_BUSY_TX": "Receiver Deafness (BUSY_TX)",
    "PREAMBLE_COLLISION_BUSY_RX": "Preamble Collision (BUSY_RX)",
    "PAYLOAD_INTERFERENCE_CORRUPTION": "Payload Interference (PER Error)",
    "SENDER_CSMA_ABORT": "Sender CSMA Abort",
    "PREAMBLE_LOW_SINR": "Preamble Low SINR (<= -5dB)",
    "OUT_OF_RANGE_OR_FADING": "Radio Turnaround / Transient Busy"
}

colors_map = {
    "RX_DEAFNESS_BUSY_TX": "#e74c3c",                # Coral Red
    "PREAMBLE_COLLISION_BUSY_RX": "#e67e22",         # Orange
    "PAYLOAD_INTERFERENCE_CORRUPTION": "#9b59b6",    # Purple
    "SENDER_CSMA_ABORT": "#3498db",                  # Sky Blue
    "PREAMBLE_LOW_SINR": "#f1c40f",                  # Yellow
    "OUT_OF_RANGE_OR_FADING": "#95a5a6"              # Gray
}

plot_labels = []
plot_sizes = []
plot_colors = []

for r_key, r_name in labels_map.items():
    cnt = fail_reasons.get(r_key, 0)
    if cnt > 0:
        pct = (cnt / total_fails) * 100.0 if total_fails > 0 else 0
        plot_labels.append(f"{r_name}\n({cnt} links, {pct:.1f}%)")
        plot_sizes.append(cnt)
        plot_colors.append(colors_map[r_key])

# 1. ORIGINAL STYLE DONUT CHART
fig, ax = plt.subplots(figsize=(10, 8), subplot_kw=dict(aspect="equal"))
wedges, texts = ax.pie(
    plot_sizes,
    labels=plot_labels,
    colors=plot_colors,
    startangle=140,
    wedgeprops=dict(width=0.4, edgecolor='white', linewidth=2),
    textprops=dict(fontsize=11)
)

ax.set_title(f"Phase 1 Exact Physical Failure Breakdown [75 UAVs, 50m Top-5 Links]\n"
             f"Total Links: {total_links:,} | Success: {success_links:,} ({(success_links/total_links)*100:.1f}%) | "
             f"Failed: {total_fails:,} ({(total_fails/total_links)*100:.1f}%)",
             fontsize=13, fontweight='bold', pad=20)

donut_path = os.path.join(PROJECT_DIR, "p1_ground_truth_donut.png")
plt.tight_layout()
plt.savefig(donut_path, dpi=300)
plt.close()
print(f"✅ Re-generated original-style donut chart: {donut_path}")

# 2. STACKED BAR CHART
fig, ax = plt.subplots(figsize=(11, 6.5))
x = range(len(dist_brackets))

categories = [
    ("RX_DEAFNESS_BUSY_TX", "Receiver Deafness", colors_map["RX_DEAFNESS_BUSY_TX"]),
    ("PREAMBLE_COLLISION_BUSY_RX", "Preamble Collision", colors_map["PREAMBLE_COLLISION_BUSY_RX"]),
    ("PAYLOAD_INTERFERENCE_CORRUPTION", "Payload Interference", colors_map["PAYLOAD_INTERFERENCE_CORRUPTION"]),
    ("SENDER_CSMA_ABORT", "Sender CSMA Abort", colors_map["SENDER_CSMA_ABORT"]),
    ("PREAMBLE_LOW_SINR", "Preamble Low SINR", colors_map["PREAMBLE_LOW_SINR"]),
    ("OUT_OF_RANGE_OR_FADING", "Radio Turnaround / Transient Busy", colors_map["OUT_OF_RANGE_OR_FADING"])
]

bottoms = [0] * len(dist_brackets)
for cat_key, cat_name, cat_color in categories:
    vals = [bracket_counts[b][cat_key] for b in dist_brackets]
    if sum(vals) > 0:
        ax.bar(x, vals, bottom=bottoms, label=f"{cat_name} (Total: {sum(vals)})", color=cat_color, width=0.55, edgecolor='black', linewidth=0.6)
        bottoms = [bottoms[i] + vals[i] for i in range(len(dist_brackets))]

ax.set_xticks(x)
ax.set_xticklabels(dist_brackets, fontsize=11, fontweight='bold')
ax.set_xlabel("Inter-UAV Distance Bracket", fontsize=12, fontweight='bold', labelpad=10)
ax.set_ylabel("Number of Failed Link Receptions", fontsize=12, fontweight='bold')
ax.set_title("Phase 1 Physical Drop Causes vs. Spatial Distance (Ground Truth)", fontsize=13, fontweight='bold', pad=15)
ax.legend(loc="upper right", frameon=True, fontsize=10, edgecolor='#bdc3c7')
ax.grid(axis='y', linestyle='--', alpha=0.5)

dist_path = os.path.join(PROJECT_DIR, "p1_ground_truth_distance.png")
plt.tight_layout()
plt.savefig(dist_path, dpi=300)
plt.close()
print(f"✅ Re-generated distance chart: {dist_path}")
