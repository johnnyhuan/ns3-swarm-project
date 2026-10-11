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

# Color Palette (Modern Academic)
PRIMARY_BLUE = "#1f77b4"
ACCENT_RED = "#d62728"
ACCENT_GREEN = "#2ca02c"
ACCENT_ORANGE = "#ff7f0e"
ACCENT_PURPLE = "#9467bd"
DARK_GRAY = "#333333"

# ==========================================
# 1. Experiment 1: Phase 2 TX Power Sweep
# ==========================================
def plot_exp1():
    powers = [-15, -12, -9, -6, -4, -2, 0]
    ratios = [0.0, 0.0, 38.7, 38.4, 40.3, 41.0, 38.6]

    fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
    
    # Line and points
    ax.plot(powers, ratios, marker='o', markersize=8, color=PRIMARY_BLUE, linewidth=2.5, label='Beacon Reception Ratio (%)')
    
    # Highlight optimal point
    opt_idx = 5 # -2 dBm
    ax.scatter([powers[opt_idx]], [ratios[opt_idx]], color=ACCENT_RED, s=160, zorder=5, label='最佳參數 (-2 dBm, 41.0%)')
    
    # Annotate optimal point
    ax.annotate('黃金平衡點: -2 dBm\n最高接收率: 41.0%\n(覆蓋 50m 且干擾最小)',
                xy=(powers[opt_idx], ratios[opt_idx]),
                xytext=(powers[opt_idx] - 4.5, ratios[opt_idx] - 12),
                arrowprops=dict(facecolor=ACCENT_RED, edgecolor=ACCENT_RED, shrink=0.08, width=1.8, headwidth=7),
                fontsize=10, fontweight='bold', color=ACCENT_RED,
                bbox=dict(boxstyle="round,pad=0.4", fc="#ffebee", ec=ACCENT_RED, lw=1))
    
    # Annotate low power failure zone
    ax.axvspan(-16, -10.5, color='#e0e0e0', alpha=0.4, label='訊號不足解碼失敗區 (0%)')
    ax.text(-13.5, 15, '低於靈敏度\n(-90 dBm)\n無法解碼', ha='center', va='center', fontsize=9, color='#666666', style='italic')

    # Annotate high power interference
    ax.annotate('功率過大造成\n全網同頻干擾增加',
                xy=(0, 38.6), xytext=(-1.5, 28),
                arrowprops=dict(facecolor=DARK_GRAY, arrowstyle="->", lw=1.2),
                fontsize=9, color=DARK_GRAY)

    ax.set_title('實驗一：Phase 2 傳輸功率與業務封包接收率關係圖\n(Phase 2 TX Power Sweep)', fontsize=13, fontweight='bold', pad=12)
    ax.set_xlabel('Phase 2 發射功率 (Phase 2 TX Power, dBm)', fontsize=11, fontweight='bold')
    ax.set_ylabel('Beacon Packet Reception Ratio (%)', fontsize=11, fontweight='bold')
    ax.set_ylim(-2, 50)
    ax.set_xlim(-16, 1)
    ax.grid(True, linestyle='--', alpha=0.6)
    ax.legend(loc='upper left', frameon=True, framealpha=0.9)

    out_name = "exp1_p2_tx_power.png"
    p_ws = os.path.join(WORKSPACE_DIR, out_name)
    p_art = os.path.join(ARTIFACT_DIR, out_name)
    fig.savefig(p_ws, bbox_inches='tight')
    fig.savefig(p_art, bbox_inches='tight')
    plt.close(fig)
    print(f"Generated {out_name}")

# ==========================================
# 2. Experiment 2: Phase 1 TX Power Sweep
# ==========================================
def plot_exp2():
    powers = [0, 1, 2, 3, 4]
    ratios = [41.0, 34.5, 31.7, 31.5, 28.3]

    fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
    
    ax.plot(powers, ratios, marker='s', markersize=8, color=ACCENT_ORANGE, linewidth=2.5, label='Beacon Reception Ratio (%)')
    
    # Highlight optimal point
    ax.scatter([0], [41.0], color=ACCENT_GREEN, s=160, zorder=5, label='最佳參數 (0 dBm / ~100m, 41.0%)')
    
    # Annotation for optimal
    ax.annotate('最佳預警半徑 (0 dBm, ~100m)\nCSMA 順暢，衝突低',
                xy=(0, 41.0), xytext=(0.4, 43.5),
                arrowprops=dict(facecolor=ACCENT_GREEN, edgecolor=ACCENT_GREEN, shrink=0.08, width=1.8, headwidth=7),
                fontsize=10, fontweight='bold', color=ACCENT_GREEN,
                bbox=dict(boxstyle="round,pad=0.4", fc="#e8f5e9", ec=ACCENT_GREEN, lw=1))
    
    # Annotation for degradation
    ax.annotate('廣播功率加大反而暴跌！\n原因：50 台無人機擠在 Ch 11\n引發 CSMA 退避飢餓與風暴 (P1 Abort)',
                xy=(4, 28.3), xytext=(1.8, 24),
                arrowprops=dict(facecolor=ACCENT_RED, edgecolor=ACCENT_RED, shrink=0.08, width=1.8, headwidth=7),
                fontsize=9.5, fontweight='bold', color=ACCENT_RED,
                bbox=dict(boxstyle="round,pad=0.4", fc="#ffebee", ec=ACCENT_RED, lw=1))

    ax.set_title('實驗二：Phase 1 廣播功率對系統接收率的負面衝擊\n(Phase 1 TX Power Sweep & CSMA Storm)', fontsize=13, fontweight='bold', pad=12)
    ax.set_xlabel('Phase 1 發射功率 (Phase 1 TX Power, dBm)', fontsize=11, fontweight='bold')
    ax.set_ylabel('Beacon Packet Reception Ratio (%)', fontsize=11, fontweight='bold')
    ax.set_xticks(powers)
    ax.set_xticklabels(['0 dBm\n(~100m)', '1 dBm\n(~112m)', '2 dBm\n(~125m)', '3 dBm\n(~138m)', '4 dBm\n(~150m)'])
    ax.set_ylim(20, 50)
    ax.grid(True, linestyle='--', alpha=0.6)
    ax.legend(loc='lower left', frameon=True, framealpha=0.9)

    out_name = "exp2_p1_tx_power.png"
    p_ws = os.path.join(WORKSPACE_DIR, out_name)
    p_art = os.path.join(ARTIFACT_DIR, out_name)
    fig.savefig(p_ws, bbox_inches='tight')
    fig.savefig(p_art, bbox_inches='tight')
    plt.close(fig)
    print(f"Generated {out_name}")

# ==========================================
# 3. Experiment 3: Channel Count Sweep
# ==========================================
def plot_exp3():
    channels = ['6 頻道 (Ch 12-17)\n[標準 IEEE 802.15.4]', '10 頻道 (Ch 12-21)\n[頻率擴充嘗試]']
    ratios = [41.0, 31.8]

    fig, ax = plt.subplots(figsize=(7, 5), dpi=300)
    
    bars = ax.bar([0, 1], ratios, width=0.45, color=[PRIMARY_BLUE, ACCENT_PURPLE], edgecolor=DARK_GRAY, linewidth=1.5)
    
    # Bar value labels
    for bar in bars:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., h + 1.2, f'{h:.1f}%', ha='center', va='bottom', fontsize=12, fontweight='bold')

    # Annotation
    ax.text(0, 18, '[最佳配比] 41.0%\n10 Slots × 6 Channels (60格)\n發射/接收在同 Slot 機率均勻',
            ha='center', va='center', fontsize=9.5, color='white', fontweight='bold',
            bbox=dict(boxstyle="round,pad=0.5", fc=PRIMARY_BLUE, ec="none", alpha=0.9))

    ax.text(1, 14, '[嚴重警訊] 接收率暴跌 9.2%！\n原因：單網卡半雙工限制\n同 Slot 跨頻道無人監聽\n(Multi-Channel Deafness)',
            ha='center', va='center', fontsize=9.5, color='white', fontweight='bold',
            bbox=dict(boxstyle="round,pad=0.5", fc=ACCENT_PURPLE, ec="none", alpha=0.9))

    ax.set_title('實驗三：資料傳輸頻道數量對接收率的影響\n(Channel Expansion vs. Single-Radio Constraint)', fontsize=13, fontweight='bold', pad=12)
    ax.set_ylabel('Beacon Packet Reception Ratio (%)', fontsize=11, fontweight='bold')
    ax.set_xticks([0, 1])
    ax.set_xticklabels(channels, fontsize=10.5, fontweight='bold')
    ax.set_ylim(0, 52)
    ax.grid(axis='y', linestyle='--', alpha=0.6)

    out_name = "exp3_channel_count.png"
    p_ws = os.path.join(WORKSPACE_DIR, out_name)
    p_art = os.path.join(ARTIFACT_DIR, out_name)
    fig.savefig(p_ws, bbox_inches='tight')
    fig.savefig(p_art, bbox_inches='tight')
    plt.close(fig)
    print(f"Generated {out_name}")

# ==========================================
# 4. Experiment 4: RX Deafness Distance Sweep
# ==========================================
def plot_exp4():
    dists = [0, 10, 20, 30, 40, 50]
    ratios = [5.2, 5.2, 5.2, 7.3, 9.0, 41.0]

    fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
    
    ax.plot(dists, ratios, marker='^', markersize=9, color=ACCENT_PURPLE, linewidth=2.5, label='Beacon Reception Ratio (%)')
    
    # Highlight optimal point
    ax.scatter([50], [41.0], color=ACCENT_RED, s=180, zorder=5, label='最佳防禦距離 (50m, 41.0%)')
    
    # Low defense region
    ax.axvspan(-2, 25, color='#ffebee', alpha=0.5, label='未防禦區 (耳聾慘烈 5.2%)')
    ax.text(10, 16, '未避讓近鄰時槽\n無人機嚴重耳聾\n接收率慘不忍睹', ha='center', va='center', fontsize=9, color=ACCENT_RED)

    # Dramatic leap annotation
    ax.annotate('垂直暴漲 +32%！\n完美覆蓋 50m 資料通訊半徑\n徹底消滅所有近距離耳聾 (RX Deafness)',
                xy=(50, 41.0), xytext=(22, 33),
                arrowprops=dict(facecolor=ACCENT_RED, edgecolor=ACCENT_RED, shrink=0.08, width=2, headwidth=8),
                fontsize=10, fontweight='bold', color=ACCENT_RED,
                bbox=dict(boxstyle="round,pad=0.5", fc="#fff3e0", ec=ACCENT_ORANGE, lw=1.2))

    ax.set_title('實驗四：耳聾防禦距離與封包接收率之關係\n(RX Deafness Avoid Distance Sweep)', fontsize=13, fontweight='bold', pad=12)
    ax.set_xlabel('耳聾防禦距離 (RX Deafness Avoid Distance, 公尺)', fontsize=11, fontweight='bold')
    ax.set_ylabel('Beacon Packet Reception Ratio (%)', fontsize=11, fontweight='bold')
    ax.set_xticks(dists)
    ax.set_xticklabels(['0m\n(關閉防禦)', '10m', '20m', '30m', '40m', '50m\n(全覆蓋)'])
    ax.set_ylim(0, 50)
    ax.set_xlim(-3, 55)
    ax.grid(True, linestyle='--', alpha=0.6)
    ax.legend(loc='upper left', frameon=True, framealpha=0.9)

    out_name = "exp4_rx_deafness_distance.png"
    p_ws = os.path.join(WORKSPACE_DIR, out_name)
    p_art = os.path.join(ARTIFACT_DIR, out_name)
    fig.savefig(p_ws, bbox_inches='tight')
    fig.savefig(p_art, bbox_inches='tight')
    plt.close(fig)
    print(f"Generated {out_name}")

# ==========================================
# 5. Combined 4-in-1 Panel Chart
# ==========================================
def plot_combined():
    fig, axes = plt.subplots(2, 2, figsize=(14, 10), dpi=300)
    
    # Subplot 1
    ax1 = axes[0, 0]
    p1 = [-15, -12, -9, -6, -4, -2, 0]
    r1 = [0.0, 0.0, 38.7, 38.4, 40.3, 41.0, 38.6]
    ax1.plot(p1, r1, marker='o', color=PRIMARY_BLUE, lw=2.2, label='接收率 (%)')
    ax1.scatter([-2], [41.0], color=ACCENT_RED, s=120, zorder=5)
    ax1.set_title('(A) 實驗一：Phase 2 發射功率掃描', fontsize=12, fontweight='bold')
    ax1.set_xlabel('Phase 2 TX Power (dBm)', fontsize=10)
    ax1.set_ylabel('Reception Ratio (%)', fontsize=10)
    ax1.annotate('最佳點: -2 dBm (41.0%)', xy=(-2, 41.0), xytext=(-8, 30),
                 arrowprops=dict(facecolor=ACCENT_RED, arrowstyle="->", lw=1.5),
                 fontsize=9.5, fontweight='bold', color=ACCENT_RED)
    ax1.grid(True, linestyle='--', alpha=0.5)
    ax1.set_ylim(-2, 48)

    # Subplot 2
    ax2 = axes[0, 1]
    p2 = [0, 1, 2, 3, 4]
    r2 = [41.0, 34.5, 31.7, 31.5, 28.3]
    ax2.plot(p2, r2, marker='s', color=ACCENT_ORANGE, lw=2.2)
    ax2.scatter([0], [41.0], color=ACCENT_GREEN, s=120, zorder=5)
    ax2.set_title('(B) 實驗二：Phase 1 廣播發射功率掃描', fontsize=12, fontweight='bold')
    ax2.set_xlabel('Phase 1 TX Power (dBm)', fontsize=10)
    ax2.set_ylabel('Reception Ratio (%)', fontsize=10)
    ax2.annotate('最佳點: 0 dBm (41.0%)\n功率再大會引發 CSMA 塞車', xy=(0, 41.0), xytext=(0.8, 38),
                 arrowprops=dict(facecolor=ACCENT_GREEN, arrowstyle="->", lw=1.5),
                 fontsize=9.5, fontweight='bold', color=ACCENT_GREEN)
    ax2.set_xticks(p2)
    ax2.set_xticklabels(['0', '1', '2', '3', '4'])
    ax2.grid(True, linestyle='--', alpha=0.5)
    ax2.set_ylim(22, 48)

    # Subplot 3
    ax3 = axes[1, 0]
    bars = ax3.bar([0, 1], [41.0, 31.8], width=0.4, color=[PRIMARY_BLUE, ACCENT_PURPLE], edgecolor=DARK_GRAY)
    ax3.set_title('(C) 實驗三：Phase 2 資料頻道數對比', fontsize=12, fontweight='bold')
    ax3.set_ylabel('Reception Ratio (%)', fontsize=10)
    ax3.set_xticks([0, 1])
    ax3.set_xticklabels(['6 頻道 (最佳: 41.0%)', '10 頻道 (暴跌: 31.8%)'], fontsize=10, fontweight='bold')
    ax3.text(0, 42, '41.0%', ha='center', fontweight='bold', fontsize=11)
    ax3.text(1, 33, '31.8%', ha='center', fontweight='bold', fontsize=11)
    ax3.text(1, 15, '單天線多頻道\n耳聾衝突加劇', ha='center', fontsize=9, color='white',
             bbox=dict(boxstyle="round,pad=0.3", fc=ACCENT_PURPLE, ec="none"))
    ax3.grid(axis='y', linestyle='--', alpha=0.5)
    ax3.set_ylim(0, 50)

    # Subplot 4
    ax4 = axes[1, 1]
    p4 = [0, 10, 20, 30, 40, 50]
    r4 = [5.2, 5.2, 5.2, 7.3, 9.0, 41.0]
    ax4.plot(p4, r4, marker='^', color=ACCENT_PURPLE, lw=2.2)
    ax4.scatter([50], [41.0], color=ACCENT_RED, s=120, zorder=5)
    ax4.set_title('(D) 實驗四：耳聾防禦距離掃描', fontsize=12, fontweight='bold')
    ax4.set_xlabel('耳聾防禦距離 (公尺)', fontsize=10)
    ax4.set_ylabel('Reception Ratio (%)', fontsize=10)
    ax4.annotate('防禦 50m 垂直暴漲！\n(41.0%, 提升 >4.5倍)', xy=(50, 41.0), xytext=(15, 30),
                 arrowprops=dict(facecolor=ACCENT_RED, arrowstyle="->", lw=1.5),
                 fontsize=9.5, fontweight='bold', color=ACCENT_RED)
    ax4.grid(True, linestyle='--', alpha=0.5)
    ax4.set_ylim(0, 48)

    fig.suptitle('NS-3 LR-WPAN 高密度無人機通訊協定：四項核心參數實驗總覽', fontsize=15, fontweight='bold', y=0.995)
    
    out_name = "experiments_4in1_summary.png"
    p_ws = os.path.join(WORKSPACE_DIR, out_name)
    p_art = os.path.join(ARTIFACT_DIR, out_name)
    fig.savefig(p_ws, bbox_inches='tight')
    fig.savefig(p_art, bbox_inches='tight')
    plt.close(fig)
    print(f"Generated {out_name}")

if __name__ == '__main__':
    plot_exp1()
    plot_exp2()
    plot_exp3()
    plot_exp4()
    plot_combined()
    print("All charts successfully generated and saved to both workspace and artifact directories!")
