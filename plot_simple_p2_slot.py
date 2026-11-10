#!/usr/bin/env python3
"""
Simple & Clean Plot Generator for Phase 2 Slot Duration Optimization:
- No peak star marker (*)
- No slot count parentheticals like "(13 slots)"
- Simple, publication/slide-ready aesthetic
"""

import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
ARTIFACT_DIR = "/Users/hbxuan/.gemini/antigravity/brain/580f4ce3-fbf9-4506-9bc7-86b7ef48b448"

# Data from simulation
slot_durations = [400, 500, 625, 750, 800, 1000, 1250, 1500, 2000, 2500]
p2_prr = [0.0, 0.0, 0.0, 83.2, 81.5, 81.2, 77.5, 68.6, 60.9, 50.6]

plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['font.size'] = 11

# ==============================================================================
# 1. Clean Simple Plot (All 10 Points, Equidistant Ticks for Clean Spacing)
# ==============================================================================
fig, ax = plt.subplots(figsize=(10, 5.8), dpi=300)

# Single clean line and uniform solid markers
x_indices = list(range(len(slot_durations)))
ax.plot(x_indices, p2_prr, marker='o', markersize=7.5, linewidth=2.4, color='#1f77b4', label='Phase 2 Delivery PRR (%)')

# Clean annotations: strictly percentages only (NO slots, NO stars, NO peak text)
for i, (s, p) in enumerate(zip(slot_durations, p2_prr)):
    if p > 0:
        offset_y = 10
        ax.annotate(f"{p:.1f}%", (i, p), textcoords="offset points", xytext=(0, offset_y),
                    ha='center', fontsize=10, fontweight='bold', color='#1f77b4')
    else:
        ax.annotate(f"{p:.1f}%", (i, p), textcoords="offset points", xytext=(0, 8),
                    ha='center', fontsize=9, color='#7f7f7f')

ax.set_title('Phase 2 Data PRR vs. Slot Duration (10ms Window)', fontsize=13, fontweight='bold', pad=14)
ax.set_xlabel('Slot Duration (µs)', fontsize=11.5, fontweight='bold')
ax.set_ylabel('Delivery PRR (%)', fontsize=11.5, fontweight='bold')
ax.set_xticks(x_indices)
ax.set_xticklabels([f"{s}" for s in slot_durations], fontsize=10.5)
ax.set_ylim(-3, 95)
ax.grid(True, linestyle='--', alpha=0.5)
ax.legend(loc='lower left', fontsize=10.5, framealpha=0.95)

plt.tight_layout()

# Save to workspace and artifact directory
out_path_1 = os.path.join(PROJECT_DIR, "p2_slot_sweep_prr.png")
plt.savefig(out_path_1)
if os.path.exists(ARTIFACT_DIR):
    plt.savefig(os.path.join(ARTIFACT_DIR, "p2_slot_sweep_prr.png"))
plt.close()
print(f"✅ Saved clean simple plot to {out_path_1}")

# ==============================================================================
# 2. Focused Operational Plot (750µs ~ 2500µs, Clean & Simple)
# ==============================================================================
op_slots = [750, 800, 1000, 1250, 1500, 2000, 2500]
op_prr = [83.2, 81.5, 81.2, 77.5, 68.6, 60.9, 50.6]
op_indices = list(range(len(op_slots)))

fig, ax2 = plt.subplots(figsize=(9, 5.5), dpi=300)
ax2.plot(op_indices, op_prr, marker='o', markersize=7.5, linewidth=2.4, color='#1f77b4', label='Phase 2 Delivery PRR (%)')

for i, (s, p) in enumerate(zip(op_slots, op_prr)):
    ax2.annotate(f"{p:.1f}%", (i, p), textcoords="offset points", xytext=(0, 10),
                 ha='center', fontsize=10, fontweight='bold', color='#1f77b4')

ax2.set_title('Phase 2 Data PRR vs. Slot Duration (Operational Range: 750µs ~ 2500µs)', fontsize=12.5, fontweight='bold', pad=14)
ax2.set_xlabel('Slot Duration (µs)', fontsize=11.5, fontweight='bold')
ax2.set_ylabel('Delivery PRR (%)', fontsize=11.5, fontweight='bold')
ax2.set_xticks(op_indices)
ax2.set_xticklabels([f"{s}" for s in op_slots], fontsize=10.5)
ax2.set_ylim(40, 92)
ax2.grid(True, linestyle='--', alpha=0.5)
ax2.legend(loc='lower left', fontsize=10.5, framealpha=0.95)

plt.tight_layout()
out_path_2 = os.path.join(PROJECT_DIR, "p2_slot_sweep_prr_operational.png")
plt.savefig(out_path_2)
if os.path.exists(ARTIFACT_DIR):
    plt.savefig(os.path.join(ARTIFACT_DIR, "p2_slot_sweep_prr_operational.png"))
plt.close()
print(f"✅ Saved focused operational plot to {out_path_2}")
