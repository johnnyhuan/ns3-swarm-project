#!/usr/bin/env python3
"""
Generate a Publication/Presentation-Grade 16:9 Slide with CJK Font:
Root Cause Analysis of 60.9% Preamble Collisions in BLE 5.4 2M Swarm CSMA-CA.
"""

import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.patches import FancyBboxPatch

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# Setup CJK font
cjk_font_path = "/System/Library/Fonts/STHeiti Medium.ttc"
if not os.path.exists(cjk_font_path):
    cjk_font_path = "/System/Library/Fonts/Supplemental/Songti.ttc"
prop_bold = fm.FontProperties(fname=cjk_font_path, weight='bold')
prop_norm = fm.FontProperties(fname=cjk_font_path, weight='normal')

# 16:9 widescreen canvas
fig = plt.figure(figsize=(16, 9), dpi=300)
ax = fig.add_subplot(111)
ax.set_xlim(0, 16)
ax.set_ylim(0, 9)
ax.axis('off')

fig.patch.set_facecolor('#f8fafc')
ax.set_facecolor('#f8fafc')

# -------------------------------------------------------------------------
# Top Header Section
# -------------------------------------------------------------------------
badge = FancyBboxPatch((0.8, 8.12), 4.2, 0.42, boxstyle="round,pad=0.08", fc='#fee2e2', ec='#ef4444', lw=1.2)
ax.add_patch(badge)
ax.text(2.9, 8.33, '實體層最大死因剖析 (佔總失敗 60.9%)', ha='center', va='center',
        fontsize=11, fontweight='bold', color='#b91c1c', fontproperties=prop_bold)

ax.text(0.8, 7.62, '為什麼 60.9% 的封包失敗都是「前導碼碰撞 (Preamble Collision)」？',
        fontsize=21, fontweight='bold', color='#0f172a', fontproperties=prop_bold)
ax.text(0.8, 7.18, 'BLE 5.4 2M PHY 無協調 CSMA-CA 廣播 | 100 台 UAV 蜂群 | 1,860 / 3,052 條失敗連線實測根因',
        fontsize=12, fontweight='bold', color='#64748b', fontproperties=prop_bold)

# -------------------------------------------------------------------------
# Mechanism Banner: The Physical Lock-In Principle
# -------------------------------------------------------------------------
mech_box = FancyBboxPatch((0.8, 5.82), 14.4, 1.10, boxstyle="round,pad=0.2", fc='#ffffff', ec='#cbd5e1', lw=1.5)
ax.add_patch(mech_box)

ax.text(1.1, 6.58, '【天線前導碼硬體鎖定機制 (Hardware Preamble Lock-in & Lock-out)】',
        fontsize=12.5, fontweight='bold', color='#1e293b', fontproperties=prop_bold)
mech_desc = (
    "1. 鎖定狀態：接收端一旦偵測到任一封包前導碼 (Prx > -96 dBm)，硬體狀態立刻切入 BUSY_RX 解調鎖定。\n"
    "2. 拒收機制：在此 244 µs 空中時間內，後續到達的任何封包天線一律無法同步，直接被拒收判定為碰撞 (Drop)。\n"
    "3. 唯一生還條件：後到者的訊號必須比第一台高出 +6.0 dB 以上 (天線功率捕獲 Power Capture)，否則全部陣亡！"
)
ax.text(1.1, 6.05, mech_desc, fontsize=10.2, color='#334155', linespacing=1.35, fontproperties=prop_norm)

# -------------------------------------------------------------------------
# Three Concrete Real-World Scenarios (Cards)
# -------------------------------------------------------------------------
card_y = 1.88
card_h = 3.75
card_w = 4.55
gap = 0.38
start_x = 0.8

scenarios = [
    {
        "title": "情境一：經典隱藏節點盲區",
        "subtitle": "距離 > 50m，彼此互在 CCA 死角",
        "tag": "CCA 盲區同時發射",
        "color": "#ea580c",
        "bg_color": "#fff7ed",
        "border_color": "#fdba74",
        "points": [
            "真實物理配置：",
            "  • UAV 72 與 UAV 19 相距 70m。",
            "  • 彼此訊號弱於 -96.58 dBm，無法互聽。",
            "實際發生過程：",
            "  1. 兩台同時偵測通道「閒置」，一同發射。",
            "  2. 中央 UAV 33 先收到 UAV 19 前導碼並鎖定。",
            "  3. UAV 72 的封包晚 30µs 到達 UAV 33。",
            "  4. UAV 33 處於忙碌，直接拒收 UAV 72！"
        ]
    },
    {
        "title": "情境二：近遠功率懸殊的附帶傷害",
        "subtitle": "強者觸發捕獲，遠處正常封包遭殃",
        "tag": "強弱排擠連帶犧牲",
        "color": "#7c3aed",
        "bg_color": "#faf5ff",
        "border_color": "#d8b4fe",
        "points": [
            "真實物理配置：",
            "  • 接收端 R 附近 8m 有近鄰 N，38m 有目標 S。",
            "  • 目標 S 封包 (-93 dBm) 本可正常解調。",
            "實際發生過程：",
            "  1. 近鄰 N 剛好發射，極強訊號 (-74 dBm) 覆蓋。",
            "  2. 接收端 R 觸發 Power Capture 成功收到 N。",
            "  3. 但目標 S 因無法超越近鄰 +6 dB，硬體",
            "     無法分身解調第二台，目標 S 慘遭吞沒。"
        ]
    },
    {
        "title": "情境三：均質同儕重疊無強者",
        "subtitle": "群內距離相近 (30~40m)，訊號差 < 6dB",
        "tag": "無功率優勢集體死鎖",
        "color": "#0284c7",
        "bg_color": "#f0f9ff",
        "border_color": "#bae6fd",
        "points": [
            "真實物理配置：",
            "  • 接收端周圍 3~4 台無人機在 32m~42m。",
            "  • 接收功率皆在 -91 ~ -95 dBm 之間。",
            "實際發生過程：",
            "  1. 各自隨機退避後，在同一微秒於空中重疊。",
            "  2. 彼此功率差不到 4 dB（未達 +6.0 dB 門檻）。",
            "  3. 天線只能鎖定第一奈秒到的 1 台。",
            "  4. 後續重疊的 2~3 台全部陣亡 (全部 Drop)。"
        ]
    }
]

for idx, sc in enumerate(scenarios):
    cx = start_x + idx * (card_w + gap)
    card = FancyBboxPatch((cx, card_y), card_w, card_h, boxstyle="round,pad=0.2",
                          fc=sc["bg_color"], ec=sc["border_color"], lw=1.8)
    ax.add_patch(card)
    
    # Card Header
    ax.text(cx + 0.25, card_y + card_h - 0.45, sc["title"], fontsize=12, fontweight='bold',
            color=sc["color"], fontproperties=prop_bold)
    ax.text(cx + 0.25, card_y + card_h - 0.75, sc["subtitle"], fontsize=9.5, fontweight='bold',
            color='#475569', fontproperties=prop_bold)
    
    # Tag
    tag_patch = FancyBboxPatch((cx + card_w - 1.8, card_y + card_h - 0.65), 1.6, 0.35,
                               boxstyle="round,pad=0.08", fc=sc["color"], ec='none')
    ax.add_patch(tag_patch)
    ax.text(cx + card_w - 1.0, card_y + card_h - 0.48, sc["tag"],
            ha='center', va='center', fontsize=8.5, fontweight='bold', color='#ffffff', fontproperties=prop_bold)
    
    # Divider line
    ax.plot([cx + 0.25, cx + card_w - 0.25], [card_y + card_h - 0.95, card_y + card_h - 0.95],
            color=sc["border_color"], lw=1.2)
    
    # Bullet points
    y_text = card_y + card_h - 1.25
    for pt in sc["points"]:
        if pt.endswith("："):
            ax.text(cx + 0.25, y_text, pt, fontsize=9.5, fontweight='bold', color='#1e293b', fontproperties=prop_bold)
            y_text -= 0.28
        else:
            ax.text(cx + 0.3, y_text, pt, fontsize=9.0, color='#334155', fontproperties=prop_norm)
            y_text -= 0.24

# -------------------------------------------------------------------------
# Bottom Takeaway Summary Banner
# -------------------------------------------------------------------------
bot_box = FancyBboxPatch((0.8, 0.50), 14.4, 1.15, boxstyle="round,pad=0.2", fc='#0f172a', ec='none')
ax.add_patch(bot_box)

ax.text(1.1, 1.32, '【關鍵結論與架構瓶頸 (Why Tuning Backoff Cannot Fix This)】',
        fontsize=12, fontweight='bold', color='#38bdf8', fontproperties=prop_bold)
takeaway_text = (
    "• 通道物理容量受限：100 台無人機廣播需 24.4 ms 純發射時間，10 ms 視窗意味著 244% 的通道超載率 (Load G = 2.44)。\n"
    "• 85.6% 碰撞發生在距離 >= 30m：彼此互在 CCA 死角，純調退避參數或發射功率無法消除隱藏節點盲區。\n"
    "• 解法唯一方向：唯有藉由「時槽化協調 (Slotted Allocation)」或「視窗擴增至 15~20ms (使 G 降至 1.2)」，才能突破 95% PRR！"
)
ax.text(1.1, 0.76, takeaway_text, fontsize=9.6, color='#cbd5e1', linespacing=1.35, fontproperties=prop_norm)

plt.tight_layout()

slide_path = os.path.join(PROJECT_DIR, "slide_preamble_collision_examples.png")
plt.savefig(slide_path, dpi=300, bbox_inches='tight')
plt.close()

print(f"✅ Presentation slide successfully generated at: {slide_path}")
