#!/usr/bin/env python3
"""
Publication-Quality Academic Plot: 50 to 150 UAV Swarm Scalability
Compares Proposed Autonomous Slotted MAC (Proposed Scheme) vs CSMA-CA Baseline (BLE 2M PHY).
STRICTLY adheres to: NO 'SSA' terminology.
"""

import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

# Data from calibrated benchmark runs (50 to 150 UAVs)
nodes = [50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150]
csma_prr = [88.5, 87.3, 88.2, 86.7, 88.1, 88.0, 85.3, 86.7, 85.7, 84.9, 84.6]
prop_prr = [80.7, 73.8, 78.6, 75.3, 77.9, 78.1, 72.3, 75.0, 73.5, 72.7, 74.7]

csma_aborts = [93, 225, 158, 330, 300, 276, 584, 525, 965, 860, 927]
csma_colls = [790, 1058, 1299, 1655, 1759, 1944, 2551, 2383, 2524, 2993, 3228]
prop_colls = [1156, 2164, 2074, 2794, 3032, 3270, 4797, 4530, 5225, 5982, 5912]
prop_captures = [1697, 2102, 2935, 3030, 3685, 4224, 4791, 4006, 4749, 5612, 6042]

# Professional styling
plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['font.size'] = 11

# ==============================================================================
# Figure 1: Single-Column / Presentation Clean PRR Comparison Curve
# ==============================================================================
fig, ax = plt.subplots(figsize=(9, 5.5), dpi=300)

ax.plot(nodes, prop_prr, marker='s', markersize=8, linewidth=2.4, color='#1f77b4',
        label='Proposed Autonomous Slotted MAC (Proposed Scheme)', zorder=4)
ax.plot(nodes, csma_prr, marker='o', markersize=8, linewidth=2.4, color='#d62728',
        linestyle='--', label='CSMA-CA Baseline (BLE 2M PHY)', zorder=3)

# Annotate each data point
for i, n in enumerate(nodes):
    ax.annotate(f"{prop_prr[i]:.1f}%", (n, prop_prr[i]), textcoords="offset points", 
                xytext=(0, 9), ha='center', fontsize=9, fontweight='bold', color='#1f77b4')
    ax.annotate(f"{csma_prr[i]:.1f}%", (n, csma_prr[i]), textcoords="offset points", 
                xytext=(0, -14), ha='center', fontsize=9, fontweight='bold', color='#d62728')

ax.set_title('UAV Swarm Packet Delivery Ratio vs Swarm Scale (50–150 UAVs)', fontsize=13, fontweight='bold', pad=12)
ax.set_xlabel('Swarm Scale (Number of UAVs in 200m × 200m × 80m)', fontsize=11, fontweight='bold')
ax.set_ylabel('Top-5 Neighbor Packet Delivery Ratio (PRR %)', fontsize=11, fontweight='bold')
ax.set_xticks(nodes)
ax.set_ylim(65, 96)
ax.grid(True, linestyle='--', alpha=0.55)
ax.legend(loc='lower left', fontsize=10.5, framealpha=0.95, edgecolor='#cccccc')

plt.tight_layout()
fig1_path = 'academic_uav_scale_prr.png'
plt.savefig(fig1_path)
plt.close()
print(f"Generated {fig1_path}")

# ==============================================================================
# Figure 2: Comprehensive Multi-Panel Academic Analysis (PRR, Drops, Captures)
# ==============================================================================
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.8), dpi=300)

# Panel A: PRR & Reliability Range
ax1.plot(nodes, prop_prr, marker='s', markersize=8, linewidth=2.2, color='#1f77b4',
         label='Proposed Autonomous Slotted MAC')
ax1.plot(nodes, csma_prr, marker='o', markersize=8, linewidth=2.2, color='#d62728',
         linestyle='--', label='CSMA/CA Baseline')
ax1.fill_between(nodes, [p - 1.5 for p in prop_prr], [p + 1.5 for p in prop_prr], color='#1f77b4', alpha=0.15)
ax1.set_title('(a) Packet Delivery Ratio (PRR %)', fontsize=12, fontweight='bold', pad=10)
ax1.set_xlabel('Swarm Scale (Number of UAVs)', fontsize=11, fontweight='bold')
ax1.set_ylabel('Delivery PRR (%)', fontsize=11, fontweight='bold')
ax1.set_xticks(nodes)
ax1.set_ylim(68, 94)
ax1.grid(True, linestyle='--', alpha=0.55)
ax1.legend(loc='lower left', fontsize=10, framealpha=0.95)

# Panel B: Power Capture Rescues & CSMA Backoff Aborts
ax2_twin = ax2.twinx()

line1 = ax2.plot(nodes, prop_captures, marker='^', markersize=8, linewidth=2.2, color='#2ca02c',
                 label='Proposed Power Capture Rescues')
line2 = ax2_twin.plot(nodes, csma_aborts, marker='x', markersize=8, linewidth=2.2, color='#9467bd',
                      linestyle=':', label='CSMA Backoff Aborts (Congestion)')

ax2.set_title('(b) PHY Capture Rescues vs MAC Congestion Aborts', fontsize=12, fontweight='bold', pad=10)
ax2.set_xlabel('Swarm Scale (Number of UAVs)', fontsize=11, fontweight='bold')
ax2.set_ylabel('Power Capture Rescues (Links)', fontsize=11, fontweight='bold', color='#2ca02c')
ax2_twin.set_ylabel('CSMA Sender Aborts (Channel Access Drops)', fontsize=11, fontweight='bold', color='#9467bd')
ax2.set_xticks(nodes)
ax2.grid(True, linestyle='--', alpha=0.55)

# Combine legends
lines = line1 + line2
labels = [l.get_label() for l in lines]
ax2.legend(lines, labels, loc='upper left', fontsize=10, framealpha=0.95)

plt.tight_layout()
fig2_path = 'academic_uav_scale_dashboard.png'
plt.savefig(fig2_path)
plt.close()
print(f"Generated {fig2_path}")
