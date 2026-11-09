#!/usr/bin/env python3
"""
Generate 3 simple, minimalist scenario diagrams illustrating the 60.9% Preamble Collision causes:
1. Scenario 1: Hidden Terminal (Classic spatial blindness)
2. Scenario 2: Near-Far Asymmetry (Collateral drop by close strong sender)
3. Scenario 3: Equal-Power Deadlock (Cluster overlap with <6dB difference)
Plus a combined 3-in-1 panel.
"""

import os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.patches import Circle, FancyArrowPatch, Arc

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

cjk_font_path = "/System/Library/Fonts/STHeiti Medium.ttc"
if not os.path.exists(cjk_font_path):
    cjk_font_path = "/System/Library/Fonts/Supplemental/Songti.ttc"
prop_bold = fm.FontProperties(fname=cjk_font_path, weight='bold')
prop_norm = fm.FontProperties(fname=cjk_font_path, weight='normal')

# Common styling
COLOR_RX = "#0f172a"      # Slate 900
COLOR_TX = "#2563eb"      # Blue 600
COLOR_PASS = "#16a34a"    # Green 600
COLOR_DROP = "#dc2626"    # Red 600
COLOR_BLIND = "#9333ea"   # Purple 600

# ==============================================================================
# Diagram 1: Scenario 1 - Hidden Terminal
# ==============================================================================
def draw_scenario_1():
    fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
    ax.set_xlim(-50, 50)
    ax.set_ylim(-30, 30)
    ax.set_aspect('equal')
    ax.axis('off')
    fig.patch.set_facecolor('#ffffff')
    ax.set_facecolor('#ffffff')

    # Positions
    pos_A = (-32, 0)
    pos_C = (0, 0)
    pos_B = (35, 0)

    # 70m CCA Blindness Arc / Line on top
    ax.annotate(
        '', xy=pos_B, xytext=pos_A,
        arrowprops=dict(arrowstyle='<->', color=COLOR_BLIND, lw=2, linestyle='--',
                        connectionstyle="arc3,rad=-0.4")
    )
    ax.text(1.5, 23, "70m (距離太遠，互在 CCA 盲區，聽不到對方)", ha='center', va='center',
            fontsize=10.5, fontweight='bold', color=COLOR_BLIND, fontproperties=prop_bold)

    # Signal path A -> C (Arrives 1st, Success)
    ax.annotate(
        '', xy=(-4, 0), xytext=(-26, 0),
        arrowprops=dict(arrowstyle='->', color=COLOR_PASS, lw=3.5, mutation_scale=20)
    )
    ax.text(-15, -4.5, "25m\n先到達 (t = 0µs)\n(成功鎖定)", ha='center', va='top',
            fontsize=10, fontweight='bold', color=COLOR_PASS, fontproperties=prop_bold)

    # Signal path B -> C (Arrives 2nd, Collision)
    ax.annotate(
        '', xy=(4, 0), xytext=(29, 0),
        arrowprops=dict(arrowstyle='->', color=COLOR_DROP, lw=3.5, linestyle=':', mutation_scale=20)
    )
    ax.text(17, -4.5, "39m\n晚 30µs 到達\n(接收端忙線拒收)", ha='center', va='top',
            fontsize=10, fontweight='bold', color=COLOR_DROP, fontproperties=prop_bold)

    # Nodes
    # Drone A
    ax.add_patch(Circle(pos_A, 5.5, fc='#dbeafe', ec=COLOR_TX, lw=2.2, zorder=4))
    ax.text(pos_A[0], pos_A[1], "發射 A\n(UAV 19)", ha='center', va='center',
            fontsize=9.5, fontweight='bold', color=COLOR_TX, fontproperties=prop_bold)

    # Receiver C
    ax.add_patch(Circle(pos_C, 6.0, fc='#f1f5f9', ec=COLOR_RX, lw=2.5, zorder=4))
    ax.text(pos_C[0], pos_C[1], "接收端\n(UAV 33)", ha='center', va='center',
            fontsize=10, fontweight='bold', color=COLOR_RX, fontproperties=prop_bold)

    # Drone B
    ax.add_patch(Circle(pos_B, 5.5, fc='#fee2e2', ec=COLOR_DROP, lw=2.2, zorder=4))
    ax.text(pos_B[0], pos_B[1], "發射 B\n(UAV 72)", ha='center', va='center',
            fontsize=9.5, fontweight='bold', color=COLOR_DROP, fontproperties=prop_bold)

    ax.set_title("情境一：經典隱藏節點 (Hidden Terminal)", fontsize=13, fontweight='bold', pad=15, fontproperties=prop_bold)
    plt.tight_layout()
    path = os.path.join(PROJECT_DIR, "scenario1_hidden_terminal.png")
    plt.savefig(path, bbox_inches='tight')
    plt.close()
    print(f"✅ Generated {path}")

# ==============================================================================
# Diagram 2: Scenario 2 - Near-Far Disparity
# ==============================================================================
def draw_scenario_2():
    fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
    ax.set_xlim(-50, 30)
    ax.set_ylim(-30, 30)
    ax.set_aspect('equal')
    ax.axis('off')
    fig.patch.set_facecolor('#ffffff')
    ax.set_facecolor('#ffffff')

    # Positions
    pos_S = (-38, 0)
    pos_R = (0, 0)
    pos_N = (16, 0)

    # Near node N -> R (Very strong, 8m equivalent scaled)
    ax.annotate(
        '', xy=(4.5, 0), xytext=(11.5, 0),
        arrowprops=dict(arrowstyle='->', color=COLOR_PASS, lw=4.5, mutation_scale=22)
    )
    ax.text(10, 8, "8m (超近)\nPrx = -74 dBm\n(觸發功率捕獲成功)", ha='center', va='bottom',
            fontsize=10, fontweight='bold', color=COLOR_PASS, fontproperties=prop_bold)

    # Far node S -> R (38m, decodable in silence, but swallowed)
    ax.annotate(
        '', xy=(-5, 0), xytext=(-32, 0),
        arrowprops=dict(arrowstyle='->', color=COLOR_DROP, lw=2.5, linestyle=':', mutation_scale=20)
    )
    ax.text(-19, -4.5, "38m (原本可正常解調)\nPrx = -93 dBm\n(弱 19dB，被近鄰覆蓋拒收)",
            ha='center', va='top', fontsize=10, fontweight='bold', color=COLOR_DROP, fontproperties=prop_bold)

    # Nodes
    # Far Sender S
    ax.add_patch(Circle(pos_S, 5.5, fc='#fee2e2', ec=COLOR_DROP, lw=2.2, zorder=4))
    ax.text(pos_S[0], pos_S[1], "目標發射\n(遠處 S)", ha='center', va='center',
            fontsize=9.5, fontweight='bold', color=COLOR_DROP, fontproperties=prop_bold)

    # Receiver R
    ax.add_patch(Circle(pos_R, 6.0, fc='#f1f5f9', ec=COLOR_RX, lw=2.5, zorder=4))
    ax.text(pos_R[0], pos_R[1], "接收端\n(UAV R)", ha='center', va='center',
            fontsize=10, fontweight='bold', color=COLOR_RX, fontproperties=prop_bold)

    # Near Peer N
    ax.add_patch(Circle(pos_N, 5.5, fc='#dcfce7', ec=COLOR_PASS, lw=2.2, zorder=4))
    ax.text(pos_N[0], pos_N[1], "近鄰無人機\n(近處 N)", ha='center', va='center',
            fontsize=9.5, fontweight='bold', color=COLOR_PASS, fontproperties=prop_bold)

    ax.set_title("情境二：近遠功率懸殊的附帶傷害 (Near-Far Disparity)", fontsize=13, fontweight='bold', pad=15, fontproperties=prop_bold)
    plt.tight_layout()
    path = os.path.join(PROJECT_DIR, "scenario2_near_far.png")
    plt.savefig(path, bbox_inches='tight')
    plt.close()
    print(f"✅ Generated {path}")

# ==============================================================================
# Diagram 3: Scenario 3 - Equal-Power Cluster Deadlock
# ==============================================================================
def draw_scenario_3():
    fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
    ax.set_xlim(-25, 45)
    ax.set_ylim(-35, 35)
    ax.set_aspect('equal')
    ax.axis('off')
    fig.patch.set_facecolor('#ffffff')
    ax.set_facecolor('#ffffff')

    # Receiver at (0, 0)
    pos_R = (0, 0)

    # 3 peers at similar distances (~35m)
    r_dist = 34
    ang1 = np.deg2rad(40)
    ang2 = np.deg2rad(0)
    ang3 = np.deg2rad(-40)

    pos_P1 = (r_dist * np.cos(ang1), r_dist * np.sin(ang1))
    pos_P2 = (r_dist * np.cos(ang2), r_dist * np.sin(ang2))
    pos_P3 = (r_dist * np.cos(ang3), r_dist * np.sin(ang3))

    # Signal 1 (P1 -> R): Arrives at t0 (1st arrival -> locked)
    ax.annotate(
        '', xy=(3.5*np.cos(ang1), 3.5*np.sin(ang1)),
        xytext=(pos_P1[0] - 5*np.cos(ang1), pos_P1[1] - 5*np.sin(ang1)),
        arrowprops=dict(arrowstyle='->', color=COLOR_PASS, lw=3.5, mutation_scale=20)
    )
    ax.text(12, 19, "先到 1 奈秒 (Prx = -92 dBm)\n(天線鎖定成功)", fontsize=9.5,
            fontweight='bold', color=COLOR_PASS, fontproperties=prop_bold)

    # Signal 2 (P2 -> R): Overlaps at t0 + 15us (Drop)
    ax.annotate(
        '', xy=(4.5, 0), xytext=(pos_P2[0] - 5.5, 0),
        arrowprops=dict(arrowstyle='->', color=COLOR_DROP, lw=2.5, linestyle=':', mutation_scale=20)
    )
    ax.text(13, -3.5, "晚 15µs 到 (Prx = -91 dBm)\n(功率差只有 1dB < 6dB，無法捕獲丟棄)",
            fontsize=9.0, fontweight='bold', color=COLOR_DROP, fontproperties=prop_bold)

    # Signal 3 (P3 -> R): Overlaps at t0 + 30us (Drop)
    ax.annotate(
        '', xy=(3.5*np.cos(ang3), 3.5*np.sin(ang3)),
        xytext=(pos_P3[0] - 5*np.cos(ang3), pos_P3[1] - 5*np.sin(ang3)),
        arrowprops=dict(arrowstyle='->', color=COLOR_DROP, lw=2.5, linestyle=':', mutation_scale=20)
    )
    ax.text(12, -23, "晚 30µs 到 (Prx = -93 dBm)\n(差 1dB，未達 +6dB 門檻丟棄)", fontsize=9.0,
            fontweight='bold', color=COLOR_DROP, fontproperties=prop_bold)

    # Nodes
    # Receiver
    ax.add_patch(Circle(pos_R, 5.5, fc='#f1f5f9', ec=COLOR_RX, lw=2.5, zorder=4))
    ax.text(pos_R[0], pos_R[1], "接收端\n(UAV R)", ha='center', va='center',
            fontsize=9.5, fontweight='bold', color=COLOR_RX, fontproperties=prop_bold)

    # P1 (Success)
    ax.add_patch(Circle(pos_P1, 5.0, fc='#dcfce7', ec=COLOR_PASS, lw=2.2, zorder=4))
    ax.text(pos_P1[0], pos_P1[1], "無人機 1\n(36m)", ha='center', va='center',
            fontsize=8.5, fontweight='bold', color=COLOR_PASS, fontproperties=prop_bold)

    # P2 (Drop)
    ax.add_patch(Circle(pos_P2, 5.0, fc='#fee2e2', ec=COLOR_DROP, lw=2.2, zorder=4))
    ax.text(pos_P2[0], pos_P2[1], "無人機 2\n(35m)", ha='center', va='center',
            fontsize=8.5, fontweight='bold', color=COLOR_DROP, fontproperties=prop_bold)

    # P3 (Drop)
    ax.add_patch(Circle(pos_P3, 5.0, fc='#fee2e2', ec=COLOR_DROP, lw=2.2, zorder=4))
    ax.text(pos_P3[0], pos_P3[1], "無人機 3\n(37m)", ha='center', va='center',
            fontsize=8.5, fontweight='bold', color=COLOR_DROP, fontproperties=prop_bold)

    ax.set_title("情境三：均質同儕重疊無強者 (Equal-Power Deadlock)", fontsize=13, fontweight='bold', pad=15, fontproperties=prop_bold)
    plt.tight_layout()
    path = os.path.join(PROJECT_DIR, "scenario3_equal_cluster.png")
    plt.savefig(path, bbox_inches='tight')
    plt.close()
    print(f"✅ Generated {path}")

# ==============================================================================
# Diagram 4: 3-in-1 Combined Panel (For convenient single slide insertion)
# ==============================================================================
def draw_combined():
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(18, 5.6), dpi=300)
    fig.patch.set_facecolor('#ffffff')

    # Panel 1: Hidden Terminal
    ax1.set_xlim(-48, 48)
    ax1.set_ylim(-28, 28)
    ax1.set_aspect('equal')
    ax1.axis('off')
    pos_A = (-30, 0); pos_C = (0, 0); pos_B = (32, 0)
    ax1.annotate('', xy=pos_B, xytext=pos_A,
                 arrowprops=dict(arrowstyle='<->', color=COLOR_BLIND, lw=2, linestyle='--', connectionstyle="arc3,rad=-0.4"))
    ax1.text(1, 21, "70m (CCA 死角，互不知情)", ha='center', va='center', fontsize=9.5, fontweight='bold', color=COLOR_BLIND, fontproperties=prop_bold)
    ax1.annotate('', xy=(-4, 0), xytext=(-24, 0), arrowprops=dict(arrowstyle='->', color=COLOR_PASS, lw=3, mutation_scale=18))
    ax1.text(-14, -4.5, "25m (先到達)\n(成功鎖定)", ha='center', va='top', fontsize=9.0, fontweight='bold', color=COLOR_PASS, fontproperties=prop_bold)
    ax1.annotate('', xy=(4, 0), xytext=(26, 0), arrowprops=dict(arrowstyle='->', color=COLOR_DROP, lw=3, linestyle=':', mutation_scale=18))
    ax1.text(15, -4.5, "39m (晚 30µs)\n(忙線拒收)", ha='center', va='top', fontsize=9.0, fontweight='bold', color=COLOR_DROP, fontproperties=prop_bold)
    ax1.add_patch(Circle(pos_A, 5.0, fc='#dbeafe', ec=COLOR_TX, lw=2, zorder=4))
    ax1.text(pos_A[0], pos_A[1], "發射 A", ha='center', va='center', fontsize=9, fontweight='bold', color=COLOR_TX, fontproperties=prop_bold)
    ax1.add_patch(Circle(pos_C, 5.5, fc='#f1f5f9', ec=COLOR_RX, lw=2.2, zorder=4))
    ax1.text(pos_C[0], pos_C[1], "接收 C", ha='center', va='center', fontsize=9, fontweight='bold', color=COLOR_RX, fontproperties=prop_bold)
    ax1.add_patch(Circle(pos_B, 5.0, fc='#fee2e2', ec=COLOR_DROP, lw=2, zorder=4))
    ax1.text(pos_B[0], pos_B[1], "發射 B", ha='center', va='center', fontsize=9, fontweight='bold', color=COLOR_DROP, fontproperties=prop_bold)
    ax1.set_title("(a) 情境一：經典隱藏節點盲區", fontsize=11.5, fontweight='bold', pad=12, fontproperties=prop_bold)

    # Panel 2: Near-Far Disparity
    ax2.set_xlim(-46, 28)
    ax2.set_ylim(-28, 28)
    ax2.set_aspect('equal')
    ax2.axis('off')
    pos_S = (-34, 0); pos_R = (0, 0); pos_N = (14, 0)
    ax2.annotate('', xy=(4.5, 0), xytext=(10, 0), arrowprops=dict(arrowstyle='->', color=COLOR_PASS, lw=4, mutation_scale=20))
    ax2.text(9, 7.5, "8m (超近，-74dBm)\n(捕獲成功)", ha='center', va='bottom', fontsize=8.5, fontweight='bold', color=COLOR_PASS, fontproperties=prop_bold)
    ax2.annotate('', xy=(-4.5, 0), xytext=(-28, 0), arrowprops=dict(arrowstyle='->', color=COLOR_DROP, lw=2.2, linestyle=':', mutation_scale=18))
    ax2.text(-16, -4.5, "38m (弱 19dB，-93dBm)\n(被近鄰鎖定覆蓋)", ha='center', va='top', fontsize=8.5, fontweight='bold', color=COLOR_DROP, fontproperties=prop_bold)
    ax2.add_patch(Circle(pos_S, 5.0, fc='#fee2e2', ec=COLOR_DROP, lw=2, zorder=4))
    ax2.text(pos_S[0], pos_S[1], "目標 S", ha='center', va='center', fontsize=9, fontweight='bold', color=COLOR_DROP, fontproperties=prop_bold)
    ax2.add_patch(Circle(pos_R, 5.5, fc='#f1f5f9', ec=COLOR_RX, lw=2.2, zorder=4))
    ax2.text(pos_R[0], pos_R[1], "接收 R", ha='center', va='center', fontsize=9, fontweight='bold', color=COLOR_RX, fontproperties=prop_bold)
    ax2.add_patch(Circle(pos_N, 5.0, fc='#dcfce7', ec=COLOR_PASS, lw=2, zorder=4))
    ax2.text(pos_N[0], pos_N[1], "近鄰 N", ha='center', va='center', fontsize=9, fontweight='bold', color=COLOR_PASS, fontproperties=prop_bold)
    ax2.set_title("(b) 情境二：近遠功率排擠傷害", fontsize=11.5, fontweight='bold', pad=12, fontproperties=prop_bold)

    # Panel 3: Equal-Power Deadlock
    ax3.set_xlim(-20, 42)
    ax3.set_ylim(-30, 30)
    ax3.set_aspect('equal')
    ax3.axis('off')
    r_dist = 30
    ang1 = np.deg2rad(40); ang2 = np.deg2rad(0); ang3 = np.deg2rad(-40)
    pos_P1 = (r_dist * np.cos(ang1), r_dist * np.sin(ang1))
    pos_P2 = (r_dist * np.cos(ang2), r_dist * np.sin(ang2))
    pos_P3 = (r_dist * np.cos(ang3), r_dist * np.sin(ang3))
    ax3.annotate('', xy=(3.5*np.cos(ang1), 3.5*np.sin(ang1)), xytext=(pos_P1[0]-4.5*np.cos(ang1), pos_P1[1]-4.5*np.sin(ang1)),
                 arrowprops=dict(arrowstyle='->', color=COLOR_PASS, lw=3, mutation_scale=18))
    ax3.text(10, 16, "先到 1 奈秒 (-92dBm)\n(鎖定)", fontsize=8.5, fontweight='bold', color=COLOR_PASS, fontproperties=prop_bold)
    ax3.annotate('', xy=(4.5, 0), xytext=(pos_P2[0]-5, 0),
                 arrowprops=dict(arrowstyle='->', color=COLOR_DROP, lw=2.2, linestyle=':', mutation_scale=18))
    ax3.text(11, -3.5, "晚 15µs (-91dBm)\n(差 1dB 陣亡)", fontsize=8.0, fontweight='bold', color=COLOR_DROP, fontproperties=prop_bold)
    ax3.annotate('', xy=(3.5*np.cos(ang3), 3.5*np.sin(ang3)), xytext=(pos_P3[0]-4.5*np.cos(ang3), pos_P3[1]-4.5*np.sin(ang3)),
                 arrowprops=dict(arrowstyle='->', color=COLOR_DROP, lw=2.2, linestyle=':', mutation_scale=18))
    ax3.text(10, -20, "晚 30µs (-93dBm)\n(差 1dB 陣亡)", fontsize=8.0, fontweight='bold', color=COLOR_DROP, fontproperties=prop_bold)
    ax3.add_patch(Circle((0, 0), 5.0, fc='#f1f5f9', ec=COLOR_RX, lw=2.2, zorder=4))
    ax3.text(0, 0, "接收 R", ha='center', va='center', fontsize=9, fontweight='bold', color=COLOR_RX, fontproperties=prop_bold)
    ax3.add_patch(Circle(pos_P1, 4.5, fc='#dcfce7', ec=COLOR_PASS, lw=2, zorder=4))
    ax3.text(pos_P1[0], pos_P1[1], "UAV 1", ha='center', va='center', fontsize=8, fontweight='bold', color=COLOR_PASS, fontproperties=prop_bold)
    ax3.add_patch(Circle(pos_P2, 4.5, fc='#fee2e2', ec=COLOR_DROP, lw=2, zorder=4))
    ax3.text(pos_P2[0], pos_P2[1], "UAV 2", ha='center', va='center', fontsize=8, fontweight='bold', color=COLOR_DROP, fontproperties=prop_bold)
    ax3.add_patch(Circle(pos_P3, 4.5, fc='#fee2e2', ec=COLOR_DROP, lw=2, zorder=4))
    ax3.text(pos_P3[0], pos_P3[1], "UAV 3", ha='center', va='center', fontsize=8, fontweight='bold', color=COLOR_DROP, fontproperties=prop_bold)
    ax3.set_title("(c) 情境三：均質重疊無強者", fontsize=11.5, fontweight='bold', pad=12, fontproperties=prop_bold)

    plt.tight_layout()
    path = os.path.join(PROJECT_DIR, "scenarios_all_three_panels.png")
    plt.savefig(path, bbox_inches='tight')
    plt.close()
    print(f"✅ Generated {path}")

if __name__ == "__main__":
    draw_scenario_1()
    draw_scenario_2()
    draw_scenario_3()
    draw_combined()
