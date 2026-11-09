#!/usr/bin/env python3
"""
Clean, publication-quality donut/pie chart of CSMA-CA broadcast packet failure root causes.
Physical Layer: BLE 5.4 2M PHY, 100 UAVs, 10ms window duration.
"""

import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# Data for 10ms Phase 1 CSMA-CA Broadcast (BLE 5.4 2M PHY, 100 UAVs)
# Total links = 23,674, Delivered = 20,622 (87.1%), Dropped = 3,052 (12.9%)
categories = [
    'Preamble Collision (Hidden Terminals)',
    'CSMA Abort (CCA Channel Busy)',
    'Half-Duplex Deafness (Busy TX)',
    'Low Demodulation SINR (< +6.0 dB)',
    'Payload Interference Corruption'
]
counts = [1860, 517, 472, 195, 8]
total_drops = sum(counts)

colors = ['#e6550d', '#756bb1', '#3182bd', '#31a354', '#969696']
explode = (0.04, 0.02, 0.02, 0.02, 0.02)

plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['font.size'] = 11

fig, ax = plt.subplots(figsize=(9, 7.2), dpi=300)

wedges, texts, autotexts = ax.pie(
    counts,
    explode=explode,
    labels=None,
    autopct=lambda pct: f"{pct:.1f}%\n({int(round(pct * total_drops / 100)):,})" if pct > 2.0 else "",
    pctdistance=0.75,
    startangle=140,
    colors=colors,
    wedgeprops=dict(width=0.42, edgecolor='white', linewidth=2.5)
)

for autotext in autotexts:
    autotext.set_color('white')
    autotext.set_fontsize(10)
    autotext.set_fontweight('bold')

# Center text in donut
ax.text(0, 0.08, 'Total Failures', ha='center', va='center', fontsize=12, fontweight='bold', color='#555555')
ax.text(0, -0.08, f'{total_drops:,}', ha='center', va='center', fontsize=18, fontweight='bold', color='#111111')
ax.text(0, -0.22, '(12.9% of links)', ha='center', va='center', fontsize=10.5, color='#777777')

# Legend with clean counts and percentages
legend_labels = [
    f"{cat}: {cnt:,} ({cnt/total_drops*100:.1f}%)"
    for cat, cnt in zip(categories, counts)
]
ax.legend(
    wedges, legend_labels,
    title="Failure Root Causes (Total Drops: 3,052)",
    title_fontsize=11.5,
    loc="center left",
    bbox_to_anchor=(0.88, 0.5),
    fontsize=10.5,
    frameon=True,
    facecolor='#fdfdfd',
    edgecolor='#dddddd'
)

ax.set_title(
    "CSMA-CA Packet Failure Root Causes (BLE 5.4 2M PHY)\n100 UAV Swarm, 10ms Window (PRR: 87.1%)",
    fontsize=13.5,
    fontweight='bold',
    pad=18
)

plt.tight_layout()

out_path = os.path.join(PROJECT_DIR, "csma_failure_pie_chart.png")
plt.savefig(out_path, bbox_inches='tight')
plt.close()

print(f"✅ Clean failure pie chart saved to: {out_path}")
