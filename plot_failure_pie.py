#!/usr/bin/env python3
"""
Publication-Quality Donut/Pie Chart with Text Cleanly Placed Beside Wedges.
NO arrows, NO bounding boxes, NO legend box.
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
    "Preamble Collision (Hidden Terminals)\n1,860 (60.9%)",
    "CSMA Abort (CCA Channel Busy)\n517 (16.9%)",
    "Half-Duplex Deafness (Busy TX)\n472 (15.5%)",
    "Low Demodulation SINR (< +6.0 dB)\n195 (6.4%)",
    "Payload Corruption (Interference)\n8 (0.3%)"
]
counts = [1860, 517, 472, 195, 8]
total_drops = sum(counts)
pcts = [c / total_drops * 100 for c in counts]

colors = ['#e6550d', '#756bb1', '#3182bd', '#2ca02c', '#8c564b']

plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['font.size'] = 11

fig, ax = plt.subplots(figsize=(11, 7.5), dpi=300)

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

# Direct text placed neatly beside each wedge (NO arrows, NO boxes)
# Coordinates tuned for visual balance around the pie
text_positions = [
    # (x, y, ha, va)
    (-1.18, -0.75, 'right', 'center'),   # Collision (bottom-left)
    (1.15, -0.10, 'left', 'center'),     # Abort (right)
    (1.10, 0.90, 'left', 'center'),      # Deafness (top-right)
    (0.05, 1.22, 'center', 'bottom'),    # Low SINR (top)
    (-1.15, 0.85, 'right', 'center')     # Corruption (top-left)
]

for i, (x, y, ha, va) in enumerate(text_positions):
    ax.text(
        x, y,
        labels[i],
        fontsize=11,
        fontweight='bold',
        color=colors[i],
        ha=ha,
        va=va,
        linespacing=1.35
    )

ax.set_title(
    "CSMA-CA Broadcast Packet Failure Root Causes\n(BLE 5.4 2M PHY, 100 UAVs, 10ms Window, PRR: 87.1%)",
    fontsize=14,
    fontweight='bold',
    pad=26
)

ax.set_xlim(-2.4, 2.4)
ax.set_ylim(-1.5, 1.6)
ax.axis('off')

plt.tight_layout()

out_path = os.path.join(PROJECT_DIR, "csma_failure_pie_chart.png")
plt.savefig(out_path, bbox_inches='tight')
plt.close()

print(f"✅ Clean text-beside pie chart saved to: {out_path}")
