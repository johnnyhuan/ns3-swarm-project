#!/usr/bin/env python3
"""
Publication-Quality Plotter for CSMA-CA Phase 1 Window Duration Sweep (3.0 ms ~ 20.0 ms)
Strictly adheres to:
- Physical Layer: Bluetooth 5.4 LE 2M PHY (2 Mbps, 244 us air time, strict C/I = +6.0 dB)
- Swarm Scale: 100 UAVs in 200m x 200m x 80m
- NO mention of IEEE 802.15.4.
"""

import os
import csv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
csv_path = os.path.join(PROJECT_DIR, "exp_csma_duration_3_20ms_results.csv")

if not os.path.exists(csv_path):
    print(f"Error: {csv_path} not found.")
    exit(1)

dur_list = []
load_list = []
prr_list = []
coll_list = []
abort_list = []
deaf_list = []
capt_list = []

with open(csv_path, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        dur_list.append(float(row["Duration_ms"]))
        load_list.append(float(row["Traffic_Load_G"]))
        prr_list.append(float(row["PRR"]))
        coll_list.append(int(row["Collisions"]))
        abort_list.append(int(row["Aborts"]))
        deaf_list.append(int(row["RX_Deafness"]))
        capt_list.append(int(row["Captures"]))

plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['font.size'] = 11

# ==============================================================================
# Figure 1: PRR vs Window Duration (BLE 5.4 2M PHY)
# ==============================================================================
fig, ax = plt.subplots(figsize=(10.5, 6), dpi=300)
ax.plot(dur_list, prr_list, marker='o', markersize=8, linewidth=2.5, color='#d62728', label='CSMA-CA (BLE 5.4 2M PHY)')

for i, d in enumerate(dur_list):
    offset_y = 10 if i % 2 == 0 else -16
    ax.annotate(f"{prr_list[i]:.1f}%", (d, prr_list[i]), textcoords="offset points", xytext=(0, offset_y),
                ha='center', fontsize=9.5, fontweight='bold', color='#d62728')

ax.set_title('CSMA-CA Packet Delivery Ratio vs Broadcast Window Duration\n(BLE 5.4 2M PHY, 100 UAVs, Continuous 3ms–20ms)', fontsize=13, fontweight='bold', pad=14)
ax.set_xlabel('Phase 1 Broadcast Window Duration (ms, 1 ms Step)', fontsize=11, fontweight='bold')
ax.set_ylabel('Top-5 Neighbor Delivery PRR (%)', fontsize=11, fontweight='bold')
ax.set_xticks(dur_list)
ax.set_ylim(min(prr_list) - 5, 100)
ax.grid(True, linestyle='--', alpha=0.55)
ax.legend(loc='lower right', fontsize=11.5, framealpha=0.95)

plt.tight_layout()
fig1_path = os.path.join(PROJECT_DIR, "csma_duration_3_20ms_prr.png")
plt.savefig(fig1_path)
plt.close()
print(f"✅ Generated {fig1_path}")

# ==============================================================================
# Figure 2: Comprehensive Multi-Panel Physical Breakdown
# ==============================================================================
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 10), dpi=300, sharex=True)

# Panel (a): Delivery PRR and Normalized Channel Load G
ax1.plot(dur_list, prr_list, marker='o', markersize=7.5, linewidth=2.4, color='#d62728', label='Delivery PRR (%)')
ax1.set_ylabel('Delivery PRR (%)', fontsize=11, fontweight='bold', color='#d62728')
ax1.tick_params(axis='y', labelcolor='#d62728')
ax1.set_ylim(35, 100)
ax1.grid(True, linestyle='--', alpha=0.55)
ax1.set_title('(a) Packet Delivery Ratio & Channel Traffic Overload Ratio G', fontsize=12, fontweight='bold')

ax1_twin = ax1.twinx()
ax1_twin.plot(dur_list, load_list, marker='s', markersize=6.5, linewidth=2.0, color='#1f77b4', linestyle=':', label='Traffic Overload Ratio G')
ax1_twin.set_ylabel('Channel Load G (Overload Multiple)', fontsize=11, fontweight='bold', color='#1f77b4')
ax1_twin.tick_params(axis='y', labelcolor='#1f77b4')

lines_1, labels_1 = ax1.get_legend_handles_labels()
lines_2, labels_2 = ax1_twin.get_legend_handles_labels()
ax1.legend(lines_1 + lines_2, labels_1 + labels_2, loc='center right', fontsize=10.5, framealpha=0.95)

# Panel (b): Drop Category Decomposition
ax2.plot(dur_list, coll_list, marker='^', markersize=7.5, linewidth=2.2, color='#ff7f0e', label='Preamble Collisions (Hidden Nodes)')
ax2.plot(dur_list, abort_list, marker='x', markersize=7.5, linewidth=2.2, color='#9467bd', label='CSMA Sender Aborts (CCA Channel Busy)')
ax2.plot(dur_list, deaf_list, marker='d', markersize=6.5, linewidth=2.0, color='#8c564b', label='Half-Duplex RX Deafness (Busy TX)')
ax2.plot(dur_list, capt_list, marker='*', markersize=8.5, linewidth=1.8, color='#2ca02c', linestyle='--', label='Power Capture Rescues (Rescued Packets)')
ax2.set_title('(b) Physical Failure Decomposition & Capture Rescues (BLE 5.4 2M PHY)', fontsize=12, fontweight='bold')
ax2.set_xlabel('Phase 1 Broadcast Window Duration (ms)', fontsize=11, fontweight='bold')
ax2.set_ylabel('Event / Link Counts', fontsize=11, fontweight='bold')
ax2.set_xticks(dur_list)
ax2.grid(True, linestyle='--', alpha=0.55)
ax2.legend(loc='upper right', fontsize=10, framealpha=0.95)

plt.tight_layout()
fig2_path = os.path.join(PROJECT_DIR, "csma_duration_3_20ms_breakdown.png")
plt.savefig(fig2_path)
plt.close()
print(f"✅ Generated {fig2_path}")
