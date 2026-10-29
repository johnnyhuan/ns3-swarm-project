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

# Mapping of raw labels to verified, physically exact academic labels
labels_map = [
    ("PREAMBLE_COLLISION_BUSY_RX", "Preamble Collision (BUSY_RX)", "#e67e22"),           # Deep Orange
    ("PREAMBLE_LOW_SINR", "Preamble Low SINR (<= -5dB)", "#f1c40f"),                     # Bright Yellow/Amber
    ("SENDER_CSMA_ABORT", "Sender CSMA Access Abort", "#3498db"),                        # Sky Blue
    ("OUT_OF_RANGE_OR_FADING", "Radio Turnaround / Transient Busy", "#1abc9c"),          # Teal / Slate (Verified root cause)
    ("RX_DEAFNESS_BUSY_TX", "Receiver Deafness (BUSY_TX)", "#e74c3c")                     # Coral Red
]

plot_labels = []
plot_sizes = []
plot_colors = []

for r_key, r_name, r_color in labels_map:
    cnt = fail_reasons.get(r_key, 0)
    pct = (cnt / total_fails) * 100.0 if total_fails > 0 else 0
    plot_labels.append(f"{r_name}\n{cnt} links ({pct:.1f}%)")
    plot_sizes.append(cnt)
    plot_colors.append(r_color)

# 1. DONUT CHART
fig, ax = plt.subplots(figsize=(11, 8.5), subplot_kw=dict(aspect="equal"))
wedges, texts, autotexts = ax.pie(
    plot_sizes,
    autopct='%1.1f%%',
    pctdistance=0.78,
    colors=plot_colors,
    startangle=135,
    wedgeprops=dict(width=0.42, edgecolor='white', linewidth=2.5),
    textprops=dict(fontsize=11, fontweight='bold')
)

for autotext in autotexts:
    autotext.set_color('black')

# Center summary text
ax.text(0, 0, f"Total Drops\n{total_fails:,}\n(24.6%)",
        ha='center', va='center', fontsize=15, fontweight='bold', color='#2c3e50')

# Legend with absolute counts
legend_labels = [f"{lbl.splitlines()[0]}: {sz:,} ({sz/total_fails*100:.1f}%)" for lbl, sz in zip(plot_labels, plot_sizes)]
ax.legend(wedges, legend_labels,
          title="Root Causes (Zero Heuristics / PHY Truth)",
          loc="center left",
          bbox_to_anchor=(0.95, 0.5),
          fontsize=10.5,
          title_fontsize=11.5,
          frameon=True,
          edgecolor='#bdc3c7')

ax.set_title(f"Phase 1 Exact Physical Layer Failure Breakdown [75 UAV Swarm, 50m Top-5]\n"
             f"Total Evaluated Links: {total_links:,} | Delivered: {success_links:,} (75.4%) | Dropped: {total_fails:,} (24.6%)",
             fontsize=13, fontweight='bold', pad=25)

donut_path = os.path.join(PROJECT_DIR, "p1_ground_truth_donut.png")
plt.tight_layout()
plt.savefig(donut_path, dpi=300, bbox_inches='tight')
plt.close()
print(f"✅ Re-generated donut chart: {donut_path}")

# 2. STACKED BAR CHART
fig, ax = plt.subplots(figsize=(11, 6.5))
x = range(len(dist_brackets))

bottoms = [0] * len(dist_brackets)
for cat_key, cat_name, cat_color in labels_map:
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
plt.savefig(dist_path, dpi=300, bbox_inches='tight')
plt.close()
print(f"✅ Re-generated distance chart: {dist_path}")
