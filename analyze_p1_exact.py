#!/usr/bin/env python3
import sys
import os
import re
from collections import defaultdict

print("==================================================")
print("     Phase 1 (0ms-25ms) Broadcast EXACT Analysis  ")
print("==================================================")

log_file = "run.log"
if len(sys.argv) > 1:
    log_file = sys.argv[1]

if not os.path.exists(log_file):
    print(f"Error: {log_file} not found. Please run the simulation first.")
    print("Example: ./ns3 run scratch/lr-wpan-swarm > run.log")
    sys.exit(1)

top_neighbors = defaultdict(list)
p1_attempts = defaultdict(list) # drone -> list of attempt times
p1_aborts = defaultdict(list)   # drone -> list of abort times
p1_success_tx = {}              # drone -> time of successful TX in Epoch 1
p1_rx = set()                   # (receiver, sender)
global_metrics = {}

current_drone_report = None

with open(log_file, "r") as f:
    for line in f:
        # 1. Parse Top Neighbors (Ground Truth within 50m)
        if "Metrics Report" in line:
            m = re.search(r'Drone\s+(\d+)\s+Metrics', line)
            if m:
                current_drone_report = int(m.group(1))
        elif current_drone_report is not None and "Drone" in line and "(" in line:
            m = re.search(r'Drone\s+(\d+)\s*\(\s*(\d+)m\)', line)
            if m:
                target = int(m.group(1))
                dist = int(m.group(2))
                top_neighbors[current_drone_report].append((target, dist))
        elif "GLOBAL NETWORK METRICS" in line:
            current_drone_report = None

        # 2. Parse Global Metrics Summary
        if "Phase 1 TX Attempts" in line:
            m = re.search(r':\s*(\d+)', line)
            if m: global_metrics["p1_attempts"] = int(m.group(1))
        elif "Phase 1 TX Aborts" in line:
            m = re.search(r':\s*(\d+)', line)
            if m: global_metrics["p1_aborts"] = int(m.group(1))
        elif "Phase 1 TX Success" in line:
            m = re.search(r':\s*(\d+)', line)
            if m: global_metrics["p1_success"] = int(m.group(1))
        elif "Phase 1 RX Success" in line:
            m = re.search(r':\s*(\d+)', line)
            if m: global_metrics["p1_rx_total"] = int(m.group(1))
        elif "Discovery Message Reception Ratio" in line:
            m = re.search(r':\s*([\d\.]+)%', line)
            if m: global_metrics["disc_ratio"] = float(m.group(1))

        # 3. Parse Epoch 1 Events (0ms to 26ms)
        time_m = re.search(r'Time:\s*([\d\.]+)ms', line)
        if time_m:
            time_ms = float(time_m.group(1))
            if time_ms <= 26.0:
                if "[P1_ATTEMPT]" in line:
                    d_m = re.search(r'Drone:\s*(\d+)', line)
                    if d_m: p1_attempts[int(d_m.group(1))].append(time_ms)
                elif "[P1_ABORT]" in line:
                    d_m = re.search(r'Drone:\s*(\d+)', line)
                    if d_m: p1_aborts[int(d_m.group(1))].append(time_ms)
                elif "[P1_SUCCESS]" in line:
                    d_m = re.search(r'Drone:\s*(\d+)', line)
                    if d_m: p1_success_tx[int(d_m.group(1))] = time_ms
                elif "[P1_RX]" in line:
                    r_m = re.search(r'Receiver:\s*(\d+)', line)
                    s_m = re.search(r'Sender:\s*(\d+)', line)
                    if r_m and s_m:
                        p1_rx.add((int(r_m.group(1)), int(s_m.group(1))))

# Link-by-Link Exact Breakdown for Epoch 1
total_target_links = 0
p1_success_links = 0
fail_sender_abort = 0
fail_rx_deafness = 0
fail_air_collision = 0
fail_fading_loss = 0

PACKET_DURATION_MS = 0.8 # ~21 bytes at 250kbps + preamble/headers

for receiver, targets in top_neighbors.items():
    for sender, dist in targets:
        total_target_links += 1

        # Check if receiver successfully heard sender in Phase 1
        if (receiver, sender) in p1_rx:
            p1_success_links += 1
            continue

        # Failure Root Cause Analysis:
        # Cause 1: Sender never successfully transmitted in Phase 1 (CSMA Aborted)
        if sender not in p1_success_tx:
            fail_sender_abort += 1
            continue

        sender_tx_time = p1_success_tx[sender]

        # Cause 2: Receiver Deafness (Receiver was transmitting when sender's packet arrived)
        if receiver in p1_success_tx:
            receiver_tx_time = p1_success_tx[receiver]
            if abs(receiver_tx_time - sender_tx_time) < PACKET_DURATION_MS:
                fail_rx_deafness += 1
                continue

        # Cause 3: Air Collision on Channel 11 (Another transmitter overlapped in time)
        collided = False
        for other_drone, other_tx_time in p1_success_tx.items():
            if other_drone != sender and other_drone != receiver:
                if abs(other_tx_time - sender_tx_time) < PACKET_DURATION_MS:
                    collided = True
                    break
        if collided:
            fail_air_collision += 1
            continue

        # Cause 4: Signal too weak or SINR background noise
        fail_fading_loss += 1

print("\n--------------------------------------------------")
print("1. 全網 1.0 秒全局 Phase 1 統計 (Global Summary):")
print("--------------------------------------------------")
if "p1_attempts" in global_metrics:
    print(f"• Phase 1 發射嘗試次數 (TX Attempts) : {global_metrics.get('p1_attempts', 0)}")
    print(f"• Phase 1 CSMA 忙線放棄 (TX Aborts)   : {global_metrics.get('p1_aborts', 0)}")
    print(f"• Phase 1 成功發射次數 (TX Success)  : {global_metrics.get('p1_success', 0)}")
    print(f"• 全網探索成功率 (Discovery Ratio)  : {global_metrics.get('disc_ratio', 0.0):.1f}%")
else:
    print("無法從 log 讀取全域統計，請確認 run.log 是否包含完整結算。")

print("\n--------------------------------------------------")
print(f"2. 第一週期 (Epoch 1: 0~25ms) 上帝視角連線死因分析:")
print("--------------------------------------------------")
if total_target_links > 0:
    success_rate = (p1_success_links / total_target_links) * 100
    fail_links = total_target_links - p1_success_links
    print(f"• 目標連線總數 (50m 內 Top-5 鄰居) : {total_target_links} 條")
    print(f"• ✅ 成功接收廣播 (P1 Success)      : {p1_success_links} 條 ({success_rate:.1f}%)")
    print(f"• ❌ 失敗漏聽廣播 (P1 Failed)       : {fail_links} 條 ({100-success_rate:.1f}%)")
    print("\n   [失敗原因逐筆剖析 (Failure Breakdown)]:")
    print(f"   ① 發射端 CSMA 退避失敗 (Sender Abort) : {fail_sender_abort:3d} 條 ({(fail_sender_abort/fail_links)*100 if fail_links else 0:5.1f}%)")
    print(f"   ② 空中同頻碰撞 (Air Collision on Ch11): {fail_air_collision:3d} 條 ({(fail_air_collision/fail_links)*100 if fail_links else 0:5.1f}%)")
    print(f"   ③ 接收端半雙工耳聾 (RX Deafness)      : {fail_rx_deafness:3d} 條 ({(fail_rx_deafness/fail_links)*100 if fail_links else 0:5.1f}%)")
    print(f"   ④ 訊號衰減與噪聲 (Fading/SINR Loss)   : {fail_fading_loss:3d} 條 ({(fail_fading_loss/fail_links)*100 if fail_links else 0:5.1f}%)")
else:
    print("未在 log 中找到目標連線，請確認模擬有正常執行完畢。")
print("==================================================\n")
