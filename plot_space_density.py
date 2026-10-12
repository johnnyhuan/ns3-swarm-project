#!/usr/bin/env python3
import os
import shutil
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

# Set font family for clear rendering with fallback
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'STHeiti', 'Songti SC', 'DejaVu Sans', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.autolayout'] = True
plt.rcParams['font.size'] = 11

WORKSPACE_DIR = "/Users/hbxuan/Downloads/ns-3-dev-master-src"
ARTIFACT_DIR = "/Users/hbxuan/.gemini/antigravity/brain/0c02aa46-03da-4a6c-a3c2-222629c65ccf"

# Data from simulation
spaces = [150, 200, 250, 300, 400]
bcn_ratios = [21.0, 22.3, 29.3, 41.0, 49.0]
srfs = [9.31, 8.19, 8.04, 6.58, 4.55]
collisions = [8.4, 7.1, 4.0, 3.5, 2.2]
disc_ratios = [72.4, 69.8, 71.2, 79.3, 84.5]

# Color Palette (Modern Academic)
PRIMARY_BLUE = "#1f77b4"
ACCENT_RED = "#d62728"
ACCENT_GREEN = "#2ca02c"
ACCENT_ORANGE = "#ff7f0e"
ACCENT_PURPLE = "#9467bd"
DARK_GRAY = "#333333"

def plot_space_density():
    fig, ax1 = plt.subplots(figsize=(9, 5.5), dpi=300)

    # Left Axis: Reception Ratios
    line1 = ax1.plot(spaces, bcn_ratios, marker='o', markersize=9, color=PRIMARY_BLUE, linewidth=2.8, label='Beacon Packet PRR (%)')
    line2 = ax1.plot(spaces, disc_ratios, marker='s', markersize=8, color=ACCENT_GREEN, linewidth=2.2, linestyle='--', label='Discovery Message PRR (%)')
    
    # Highlight baseline (300m)
    ax1.scatter([300], [41.0], color=ACCENT_RED, s=180, zorder=6, label='標準基準點 (300m, 41.0%)')
    
    # Annotate 150m (Ultra-dense)
    ax1.annotate('超高密度塞車區 (21.0%)\n• CSMA 退避逾時嚴重\n• 50台搶10時槽 (避讓崩潰)\n• 碰撞率高達 8.4%',
                 xy=(150, 21.0), xytext=(155, 30.0),
                 arrowprops=dict(facecolor=ACCENT_RED, edgecolor=ACCENT_RED, shrink=0.08, width=1.5, headwidth=6),
                 fontsize=9, fontweight='bold', color=ACCENT_RED,
                 bbox=dict(boxstyle="round,pad=0.35", fc="#ffebee", ec=ACCENT_RED, lw=1))

    # Annotate 300m (Standard Baseline)
    ax1.annotate('標準黃金平衡 (41.0%)\n高密度戰術編隊防撞\n空間復用與衝突最佳折衷',
                 xy=(300, 41.0), xytext=(240, 48.0),
                 arrowprops=dict(facecolor=PRIMARY_BLUE, edgecolor=PRIMARY_BLUE, shrink=0.08, width=1.5, headwidth=6),
                 fontsize=9, fontweight='bold', color=PRIMARY_BLUE,
                 bbox=dict(boxstyle="round,pad=0.35", fc="#e8f4fd", ec=PRIMARY_BLUE, lw=1))

    # Annotate 400m (Sparse)
    ax1.annotate('廣域稀疏空域 (49.0%)\n節點距離拉大\n空間碰撞大幅降至 2.2%',
                 xy=(400, 49.0), xytext=(330, 58.0),
                 arrowprops=dict(facecolor=ACCENT_GREEN, edgecolor=ACCENT_GREEN, shrink=0.08, width=1.5, headwidth=6),
                 fontsize=9, fontweight='bold', color="#1b5e20",
                 bbox=dict(boxstyle="round,pad=0.35", fc="#e8f5e9", ec=ACCENT_GREEN, lw=1))

    # Data value labels
    for s, b, d in zip(spaces, bcn_ratios, disc_ratios):
        ax1.text(s, b - 2.5, f"{b:.1f}%", ha='center', va='top', fontsize=9.5, fontweight='bold', color=PRIMARY_BLUE)
        ax1.text(s, d + 1.2, f"{d:.1f}%", ha='center', va='bottom', fontsize=8.5, color=ACCENT_GREEN)

    # Right Axis: Collision Ratio & SRF
    ax2 = ax1.twinx()
    line3 = ax2.plot(spaces, collisions, marker='^', markersize=8, color=ACCENT_ORANGE, linewidth=2.0, linestyle='-.', label='Collision Ratio (%)')
    ax2.set_ylabel('封包碰撞率 Collisions (%)', fontsize=11, fontweight='bold', color=ACCENT_ORANGE)
    ax2.tick_params(axis='y', labelcolor=ACCENT_ORANGE)
    ax2.set_ylim(0, 15)

    for s, c in zip(spaces, collisions):
        ax2.text(s, c + 0.4, f"{c:.1f}%", ha='center', va='bottom', fontsize=8.5, color=ACCENT_ORANGE, fontweight='bold')

    ax1.set_title('群落密度與空間擴展性分析：空域邊長與封包接收率/碰撞率關係圖\n(Swarm Spatial Density & Scalability Sweep)', fontsize=13, fontweight='bold', pad=12)
    ax1.set_xlabel('3D 空域邊長 (Space Size, m)', fontsize=11, fontweight='bold')
    ax1.set_ylabel('封包接收率 Reception Ratio (%)', fontsize=11, fontweight='bold', color=PRIMARY_BLUE)
    ax1.tick_params(axis='y', labelcolor=PRIMARY_BLUE)
    ax1.set_ylim(10, 95)
    ax1.set_xlim(130, 420)
    ax1.set_xticks(spaces)
    ax1.grid(True, linestyle='--', alpha=0.5)

    # Combine legends
    lines = line1 + line2 + [ax1.collections[0]] + line3
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc='upper left', frameon=True, framealpha=0.9, fontsize=9.5)

    out_name = "exp5_space_density_sweep.png"
    p_ws = os.path.join(WORKSPACE_DIR, out_name)
    p_art = os.path.join(ARTIFACT_DIR, out_name)
    plt.savefig(p_ws, dpi=300)
    plt.close()
    shutil.copy2(p_ws, p_art)
    print(f"✅ Generated {p_ws} and copied to {p_art}")

if __name__ == "__main__":
    plot_space_density()
