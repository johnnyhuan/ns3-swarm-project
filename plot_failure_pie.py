#!/usr/bin/env python3
"""
Publication-Quality Donut/Pie Chart with Direct Callout Labels Beside Wedges.
No separate legend box. Direct pointers from wedges to text labels.
Physical Layer: BLE 5.4 2M PHY, 100 UAVs, 10ms window duration.
"""

import os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# Data for 10ms Phase 1 CSMA-CA Broadcast (BLE 5.4 2M PHY, 100 UAVs)
# Total links = 23,674, Delivered = 20,622 (87.1%), Dropped = 3,052 (12.9%)
labels = [
    "Preamble Collision\n(Hidden Terminals)",
    "CSMA Abort\n(CCA Busy Limit)",
    "Half-Duplex Deafness\n(Busy Transmitting)",
    "Low Demodulation SINR\n(< +6.0 dB)",
    "Payload Corruption\n(Residual Noise)"
]
counts = [1860, 517, 472, 195, 8]
total_drops = sum(counts)
pcts = [c / total_drops * 100 for c in counts]

colors = ['#e6550d', '#756bb1', '#3182bd', '#2ca02c', '#8c564b']

plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['font.size'] = 11

fig, ax = plt.subplots(figsize=(11, 8), dpi=300)

# Create donut pie chart
wedges, _ = ax.pie(
    counts,
    startangle=105,
    colors=colors,
    wedgeprops=dict(width=0.42, edgecolor='white', linewidth=2.5)
)

# Center text in donut
ax.text(0, 0.08, 'Total Failures', ha='center', va='center', fontsize=13, fontweight='bold', color='#555555')
ax.text(0, -0.07, f'{total_drops:,}', ha='center', va='center', fontsize=21, fontweight='bold', color='#111111')
ax.text(0, -0.21, '(12.9% of links)', ha='center', va='center', fontsize=11, color='#777777')

# Direct callout labels beside the wedges with connector lines
# Explicitly configured positions for clean readability
text_coords = [
    # (x_text, y_text, ha, va, rad)
    (-1.35, -0.70, 'right', 'center', -0.1), # Collision (bottom-left)
    (1.42, -0.15, 'left', 'center', 0.1),    # Abort (right)
    (1.38, 0.95, 'left', 'center', 0.1),     # Deafness (top-right)
    (0.05, 1.38, 'center', 'bottom', 0.0),   # Low SINR (top)
    (-1.42, 0.95, 'right', 'center', 0.1)    # Corruption (top-left)
]

for i, p in enumerate(wedges):
    ang = (p.theta2 - p.theta1) / 2.0 + p.theta1
    ang_rad = np.deg2rad(ang)
    
    # Point on outer edge of wedge
    x_edge = np.cos(ang_rad)
    y_edge = np.sin(ang_rad)
    
    x_text, y_text, ha, va, rad = text_coords[i]
    label_text = f"{labels[i]}\n{counts[i]:,}  ({pcts[i]:.1f}%)"
    
    # Draw callout line and text box
    ax.annotate(
        label_text,
        xy=(x_edge, y_edge),
        xytext=(x_text, y_text),
        fontsize=10.5,
        fontweight='bold',
        color=colors[i],
        ha=ha,
        va=va,
        bbox=dict(boxstyle="round,pad=0.45", fc="#fdfdfd", ec=colors[i], lw=1.6, alpha=0.96),
        arrowprops=dict(
            arrowstyle="-|>",
            color=colors[i],
            lw=1.6,
            connectionstyle=f"arc3,rad={rad}"
        )
    )

ax.set_title(
    "CSMA-CA Broadcast Packet Failure Root Causes\n(BLE 5.4 2M PHY, 100 UAVs, 10ms Window, PRR: 87.1%)",
    fontsize=14,
    fontweight='bold',
    pad=26
)

ax.set_xlim(-2.3, 2.3)
ax.set_ylim(-1.6, 1.7)
ax.axis('off')

plt.tight_layout()

out_path = os.path.join(PROJECT_DIR, "csma_failure_pie_chart.png")
plt.savefig(out_path, bbox_inches='tight')
plt.close()

print(f"✅ Clean direct-callout pie chart saved to: {out_path}")
