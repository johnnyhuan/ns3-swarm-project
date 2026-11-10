import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

# Set font and style
plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['font.size'] = 11

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6), dpi=300)

# Data for operational points
slots = [750, 1000, 1250, 1500, 2000, 2500]
num_slots = [13, 10, 8, 6, 5, 4]
total_cells = [78, 60, 48, 36, 30, 24]
prr = [61.0, 81.2, 77.5, 68.6, 60.9, 50.6]
rx_deafness = [272, 918, 1511, 3021, 3887, 5079]
collisions = [123, 192, 284, 409, 379, 425]

# -------------------------------------------------------------
# Panel 1: PRR vs Slot Duration with Physical Boundary Shading
# -------------------------------------------------------------
ax1.axvspan(350, 724, color='#fee0d2', alpha=0.6, label='Physically Invalid Zone (< 724 µs)\n(Transmission Overrun & Truncation)')
ax1.axvline(724, color='#de2d26', linestyle='--', linewidth=1.8, label='Physical Lower Bound (724 µs)\n[CCA 128µs + Turnaround 192µs + Air 404µs]')

ax1.plot(slots, prr, marker='s', markersize=8, linewidth=2.5, color='#1f77b4', label='Phase 2 Data PRR (%) [No Capture]')

# Mark optimal point
ax1.scatter([1000], [81.2], color='#d62728', s=180, zorder=6, marker='*', label='Optimal Point: 1000 µs (PRR 81.2%)')

# Annotate points
for s, p, ns, tc in zip(slots, prr, num_slots, total_cells):
    color = '#d62728' if s == 1000 else '#1f77b4'
    weight = 'bold' if s == 1000 else 'normal'
    offset_y = 10 if s != 750 else -18
    ax1.annotate(f"{p:.1f}%\n({ns} slots / {tc} cells)", 
                 (s, p), textcoords="offset points", xytext=(0, offset_y),
                 ha='center', fontsize=9.5, fontweight=weight, color=color)

ax1.set_title('(a) Phase 2 Data PRR vs Slot Duration (10ms Window)', fontsize=12, fontweight='bold', pad=12)
ax1.set_xlabel('Phase 2 Slot Duration (µs)', fontsize=11, fontweight='bold')
ax1.set_ylabel('Top-5 Neighbor Data PRR (%)', fontsize=11, fontweight='bold')
ax1.set_xlim(350, 2650)
ax1.set_ylim(40, 92)
ax1.set_xticks([400, 500, 625, 724, 750, 1000, 1250, 1500, 2000, 2500])
ax1.set_xticklabels(['400\n(N/A)', '500\n(N/A)', '625\n(N/A)', '724\n(Limit)', '750', '1000\n★', '1250', '1500', '2000', '2500'], fontsize=9)
ax1.grid(True, linestyle='--', alpha=0.5)
ax1.legend(loc='lower left', fontsize=9, framealpha=0.95)

# -------------------------------------------------------------
# Panel 2: The Tradeoff: Available Cells vs RX Deafness Surge
# -------------------------------------------------------------
ax2_twin = ax2.twinx()

line1 = ax2.plot(slots, total_cells, marker='o', markersize=7, linewidth=2.2, color='#2ca02c', label='Available Resource Cells (Slots × 6 Ch)')
line2 = ax2_twin.plot(slots, rx_deafness, marker='^', markersize=7, linewidth=2.2, color='#e6550d', label='RX Deafness (Slot Conflict Drops)')

ax2.set_title('(b) Mechanism: Cell Scarcity Drives RX Deafness Surge', fontsize=12, fontweight='bold', pad=12)
ax2.set_xlabel('Phase 2 Slot Duration (µs)', fontsize=11, fontweight='bold')
ax2.set_ylabel('Total Available Resource Cells', fontsize=11, fontweight='bold', color='#2ca02c')
ax2_twin.set_ylabel('RX Deafness Link Drops', fontsize=11, fontweight='bold', color='#e6550d')

ax2.tick_params(axis='y', labelcolor='#2ca02c')
ax2_twin.tick_params(axis='y', labelcolor='#e6550d')
ax2.set_xticks(slots)
ax2.set_xticklabels([f"{s} µs" for s in slots], fontsize=9.5)
ax2.grid(True, linestyle='--', alpha=0.5)

# Combine legends
lines = line1 + line2
labels = [l.get_label() for l in lines]
ax2.legend(lines, labels, loc='center right', fontsize=9.5, framealpha=0.95)

plt.tight_layout()
plt.savefig('/Users/hbxuan/Downloads/ns-3-dev-master-src/p2_10ms_slot_optimization_curve.png')
plt.savefig('/Users/hbxuan/.gemini/antigravity/brain/580f4ce3-fbf9-4506-9bc7-86b7ef48b448/p2_10ms_slot_optimization_curve.png')
print("✅ Saved optimized dual-panel chart!")
