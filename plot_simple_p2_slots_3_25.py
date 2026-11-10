#!/usr/bin/env python3
"""
Simple & Clean Plot Generator for Phase 2 Slot Count Scaling (3 ~ 25 Slots @ 750µs):
- Data labels placed BELOW points to prevent overlap with Phase 1 baseline curve
- Main title (大標) and secondary top axis title (小標: Phase 2 Duration (ms)) properly padded
- Top axis tick labels show exact duration (e.g. 2.25 ms, 6.00 ms) with NO '(x cells)'
- No peak star marker (*)
- Clean, publication/slide-ready aesthetic
"""

import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
ARTIFACT_DIR = "/Users/hbxuan/.gemini/antigravity/brain/580f4ce3-fbf9-4506-9bc7-86b7ef48b448"

# Data from simulation
slot_nums = list(range(3, 26))
p2_durations_ms = [s * 0.75 for s in slot_nums]
p1_prrs = [85.7, 86.1, 86.2, 85.9, 85.8, 85.9, 86.1, 86.1, 86.4, 85.8, 86.0, 86.1, 86.2, 86.3, 86.4, 85.3, 85.7, 85.9, 85.9, 85.8, 86.2, 85.8, 86.1]
p2_prrs = [35.7, 49.3, 59.8, 67.0, 72.5, 75.6, 78.1, 79.6, 80.7, 81.1, 81.8, 82.1, 82.3, 82.7, 82.7, 82.2, 82.6, 82.7, 82.8, 83.0, 83.5, 83.0, 83.5]

plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['font.size'] = 11

fig, ax1 = plt.subplots(figsize=(11.5, 6.2), dpi=300)

# Plot P2 PRR (Main Curve) and P1 PRR (Baseline Reference)
line1 = ax1.plot(slot_nums, p2_prrs, marker='s', markersize=7.5, linewidth=2.5, color='#1f77b4', label='Phase 2 Delivery PRR (%)')
line2 = ax1.plot(slot_nums, p1_prrs, marker='o', markersize=5.5, linewidth=1.8, color='#2ca02c', linestyle='--', label='Phase 1 Broadcast PRR (%) (Discovery Baseline)')

# Annotate key data points BELOW the points (va='top', xytext=(0, -14)) to avoid colliding with P1
annot_slots = [3, 5, 8, 11, 14, 17, 20, 23, 25]
for s in annot_slots:
    idx = slot_nums.index(s)
    p = p2_prrs[idx]
    ax1.annotate(f"{p:.1f}%", (s, p), textcoords="offset points", xytext=(0, -14),
                 ha='center', va='top', fontsize=9.5, fontweight='bold', color='#1f77b4')

ax1.set_xlabel('Number of Phase 2 Slots (Slot Duration = 750 µs)', fontsize=11.5, fontweight='bold')
ax1.set_ylabel('Delivery PRR (%)', fontsize=11.5, fontweight='bold')
ax1.set_xticks(slot_nums)
ax1.set_xlim(2.4, 25.6)
ax1.set_ylim(20, 100)
ax1.grid(True, linestyle='--', alpha=0.5)

# Secondary top X-axis showing ONLY Phase 2 Duration (e.g. 2.25 ms, 6.00 ms) - NO '(x cells)'
ax2 = ax1.twiny()
ax2.set_xlim(ax1.get_xlim())
tick_slots = [3, 5, 8, 11, 14, 17, 20, 23, 25]
ax2.set_xticks(tick_slots)
ax2.set_xticklabels([f"{s * 0.75:.2f} ms" for s in tick_slots], fontsize=10, fontweight='medium')
ax2.set_xlabel('Phase 2 Duration (ms)', fontsize=11, fontweight='bold', labelpad=10)

# Main Title placed cleanly above ax2 with proper pad so it never collides with ax2 label
ax2.set_title('Phase 2 Delivery PRR vs. Slot Count (3 ~ 25 Slots @ Fixed 750µs, Zero Cutoff)\n'
              '100 UAV Swarm, Bluetooth 5.4 LE 2M PHY, P2 Capture DISABLED',
              fontsize=12.5, fontweight='bold', pad=18)

lines = line1 + line2
labels = [l.get_label() for l in lines]
ax1.legend(lines, labels, loc='lower right', fontsize=10.5, framealpha=0.95)

plt.tight_layout()

# Save image
out_path = os.path.join(PROJECT_DIR, "p2_slots_3_25_at_750us_prr.png")
plt.savefig(out_path)
if os.path.exists(ARTIFACT_DIR):
    plt.savefig(os.path.join(ARTIFACT_DIR, "p2_slots_3_25_at_750us_prr.png"))
plt.close()
print(f"✅ Saved clean 750us slot scaling plot to {out_path}")
