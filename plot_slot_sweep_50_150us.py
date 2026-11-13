#!/usr/bin/env python3
"""
Generate publication-quality plot for Phase 1 SSA Slot Duration Sweep
Focused specifically on the 50 µs to 150 µs sweep region, with dual-panel full spectrum view.
"""

import matplotlib.pyplot as plt
import numpy as np
import os

# Complete collected data points from previous sweeps
data = [
    # slot_us, slots_avail, prr, deafness, coll, captures, note
    (10.0,  976,  0.0,   0,   0,     0, "Physical Limit"),
    (20.0,  488,  0.0,   0,   0,     0, "Physical Limit"),
    (30.0,  326,  0.0,   0,   0,     0, "Physical Limit"),
    (50.0,  196,  0.0,   0,   0,     0, "Physical Limit"),
    (70.0,  140,  0.0,   0,   0,     0, "Sub-75µs Boundary"),
    (75.0,  131,  0.0,   0,   0,     0, "Sub-75µs Boundary"),
    (77.5,  126,  0.0,   0,   0,     0, "Sub-85µs Boundary"),
    (80.0,  122,  0.0,   0,   0,     0, "Sub-85µs Boundary"),
    (82.5,  119,  0.0,   0,   0,     0, "Sub-85µs Boundary"),
    (85.0,  115,  0.0,   0,   0,     0, "Cliff Threshold"),
    (87.5,  112, 92.4, 168, 458, 47454, "Minimum Viable Slot"),
    (90.0,  109, 92.3, 169, 449, 48458, "SSA Active"),
    (92.5,  106, 93.4, 151, 358, 48623, "Peak Spatial Reuse"),
    (95.0,  103, 92.3, 181, 412, 46695, "SSA Active"),
    (97.5,  101, 92.2, 176, 396, 45206, "SSA Active"),
    (100.0,  98, 93.2, 157, 372, 46339, "Selected Standard (100µs)"),
    (105.0,  93, 93.1, 137, 380, 44769, "Micro-Slot Plateau"),
    (125.0,  79, 91.5, 191, 394, 29208, "Medium Micro-Slot"),
    (150.0,  66, 88.4, 251, 558, 34595, "Slot Contention Rise"),
    (200.0,  49, 85.2, 319, 778, 29800, "Coarse Slot"),
    (250.0,  40, 80.1, 435, 976, 13393, "High Collision Baseline")
]

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# -------------------------------------------------------------------------
# Figure 1: Focused 50 µs to 150 µs Zoomed Plot (Exactly what user remembered)
# -------------------------------------------------------------------------
sub_data = [d for d in data if 50.0 <= d[0] <= 150.0]
x_sub = [d[0] for d in sub_data]
y_sub_prr = [d[2] for d in sub_data]
y_sub_slots = [d[1] for d in sub_data]

fig, ax1 = plt.subplots(figsize=(11, 6.5))

color_prr = '#2980b9'
ax1.set_xlabel('Phase 1 SSA Slot Duration (µs)', fontsize=12, fontweight='bold')
ax1.set_ylabel('Phase 1 Delivery PRR (%)', color=color_prr, fontsize=12, fontweight='bold')
line1 = ax1.plot(x_sub, y_sub_prr, color=color_prr, marker='o', linewidth=2.5, markersize=8, label='Phase 1 PRR (%)')
ax1.tick_params(axis='y', labelcolor=color_prr)
ax1.set_ylim([-5, 105])
ax1.grid(True, linestyle='--', alpha=0.5)

# Highlight cliff transition region [85us, 87.5us]
ax1.axvspan(50, 85, color='#e74c3c', alpha=0.12, label='Inviable Region (< 87.5 µs, PRR = 0%)')
ax1.axvline(x=87.5, color='#c0392b', linestyle='--', linewidth=2, label='Physical Boundary Threshold (87.5 µs)')

# Highlight chosen 100 us standard
ax1.scatter([100.0], [93.2], color='#e67e22', s=180, zorder=5, edgecolor='black', linewidth=1.5)
ax1.annotate('Selected Standard (100 µs)\nPRR: 93.2% (98 Slots)', 
             xy=(100.0, 93.2), xytext=(108, 80),
             arrowprops=dict(facecolor='#e67e22', shrink=0.08, width=2, headwidth=8),
             fontsize=11, fontweight='bold', color='#d35400',
             bbox=dict(boxstyle="round,pad=0.4", fc="#fef9e7", ec="#e67e22", lw=1.5))

# Annotate the steep cliff at 87.5 us
ax1.annotate('Sharp Step Transition\n(85µs: 0% → 87.5µs: 92.4%)', 
             xy=(87.5, 45), xytext=(55, 45),
             arrowprops=dict(facecolor='#c0392b', shrink=0.08, width=1.8, headwidth=7),
             fontsize=10, fontweight='bold', color='#c0392b',
             bbox=dict(boxstyle="round,pad=0.3", fc="#fdf2e9", ec="#c0392b", lw=1))

ax2 = ax1.twinx()
color_slots = '#27ae60'
ax2.set_ylabel('Available Slots in 10ms Window', color=color_slots, fontsize=12, fontweight='bold')
line2 = ax2.plot(x_sub, y_sub_slots, color=color_slots, marker='s', linestyle=':', linewidth=2, markersize=7, label='Available Slots (Capacity)')
ax2.tick_params(axis='y', labelcolor=color_slots)
ax2.set_ylim([40, 210])

# Combine legends
lines = line1 + line2
labels = [l.get_label() for l in lines]
ax1.legend(lines, labels, loc='center right', frameon=True, fontsize=10)

plt.title('Phase 1 SSA Micro-Slot Duration Sweep (50 µs to 150 µs)\nDiscovery of Minimum Physical Slot Boundary & 100 µs Standard Selection', fontsize=13, fontweight='bold')
plt.tight_layout()

focused_path = os.path.join(PROJECT_DIR, "exp_slot_sweep_50_150us.png")
plt.savefig(focused_path, dpi=300, bbox_inches='tight')
plt.close()
print(f"✅ Saved focused plot (50-150µs): {focused_path}")

# -------------------------------------------------------------------------
# Figure 2: Dual-Panel Comprehensive Dashboard (Full 10-250µs + 50-150µs Zoom)
# -------------------------------------------------------------------------
fig, (ax_full, ax_zoom) = plt.subplots(1, 2, figsize=(16, 6))

# Panel 1: Full Spectrum (10 µs to 250 µs)
x_full = [d[0] for d in data]
y_full_prr = [d[2] for d in data]

ax_full.plot(x_full, y_full_prr, marker='o', color='#2980b9', linewidth=2.5, markersize=7, label='Delivery PRR (%)')
ax_full.axvspan(10, 85, color='#e74c3c', alpha=0.15, label='Zero-PRR Dead Zone (< 87.5 µs)')
ax_full.axvspan(87.5, 125, color='#2ecc71', alpha=0.15, label='Optimal Micro-Slot Zone (91-93%)')
ax_full.axvline(x=100.0, color='#e67e22', linestyle='--', linewidth=2, label='Adopted Standard (100 µs)')
ax_full.scatter([100.0], [93.2], color='#e67e22', s=140, zorder=5, edgecolor='black')

ax_full.set_title('(a) Full Spectrum Sweep (10 µs to 250 µs)', fontsize=12, fontweight='bold')
ax_full.set_xlabel('Slot Duration (µs)', fontsize=11, fontweight='bold')
ax_full.set_ylabel('Phase 1 Delivery PRR (%)', fontsize=11, fontweight='bold')
ax_full.set_ylim([-5, 105])
ax_full.grid(True, linestyle='--', alpha=0.5)
ax_full.legend(loc='lower right', fontsize=9)

# Panel 2: Zoomed Transition Zone (50 µs to 150 µs)
ax_zoom.plot(x_sub, y_sub_prr, marker='o', color='#2980b9', linewidth=2.5, markersize=7, label='Delivery PRR (%)')
ax_zoom.axvspan(50, 85, color='#e74c3c', alpha=0.15)
ax_zoom.axvspan(87.5, 125, color='#2ecc71', alpha=0.15)
ax_zoom.axvline(x=87.5, color='#c0392b', linestyle='--', linewidth=2, label='Physical Bound (87.5 µs)')
ax_zoom.scatter([100.0], [93.2], color='#e67e22', s=160, zorder=5, edgecolor='black')

ax_zoom.annotate('Chosen 100 µs\n(PRR: 93.2%)', 
                 xy=(100.0, 93.2), xytext=(112, 75),
                 arrowprops=dict(facecolor='#e67e22', shrink=0.08, width=1.5, headwidth=6),
                 fontsize=10, fontweight='bold', color='#d35400',
                 bbox=dict(boxstyle="round,pad=0.3", fc="#fef9e7", ec="#e67e22", lw=1.2))

ax_zoom.set_title('(b) Zoomed Critical Region (50 µs to 150 µs)', fontsize=12, fontweight='bold')
ax_zoom.set_xlabel('Slot Duration (µs)', fontsize=11, fontweight='bold')
ax_zoom.set_ylabel('Phase 1 Delivery PRR (%)', fontsize=11, fontweight='bold')
ax_zoom.set_xlim([45, 155])
ax_zoom.set_ylim([-5, 105])
ax_zoom.grid(True, linestyle='--', alpha=0.5)
ax_zoom.legend(loc='lower right', fontsize=9)

plt.suptitle('SSA: Slot Duration Sweep & Selection Rationale (75 UAVs, 10ms Window)', fontsize=14, fontweight='bold', y=0.98)
plt.tight_layout()

dual_path = os.path.join(PROJECT_DIR, "exp_slot_sweep_dual_panel.png")
plt.savefig(dual_path, dpi=300, bbox_inches='tight')
plt.close()
print(f"✅ Saved dual-panel plot: {dual_path}")
