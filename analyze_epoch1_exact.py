#!/usr/bin/env python3
import sys
import re
from collections import defaultdict

print("==================================================")
print("      Epoch 1 (0ms-51ms) EXACT Data Analysis      ")
print("==================================================")

log_file = "run.log"

top_5 = defaultdict(list)
p1_rx = set() # (Receiver, Sender)
p2_attempt = {} # Sender -> (Slot, Channel)
p2_rx = set() # (Receiver, Sender)

current_drone_report = None

try:
    with open(log_file, "r") as f:
        for line in f:
            # Parse Top 5 topology at the end of the log
            if "Metrics Report" in line:
                match = re.search(r'Drone\s+(\d+)\s+Metrics', line)
                if match:
                    current_drone_report = int(match.group(1))
            elif line.startswith("Drone ") and current_drone_report is not None:
                match = re.search(r'Drone\s+(\d+)\s*\(', line)
                if match:
                    target = int(match.group(1))
                    top_5[current_drone_report].append(target)
            elif "---" in line or "Target (Dist)" in line:
                pass
            else:
                if current_drone_report is not None and not line.strip():
                    # End of report block
                    current_drone_report = None
            
            # Parse Time events
            time_match = re.search(r'Time:\s*([\d\.]+)ms', line)
            if time_match:
                time_ms = float(time_match.group(1))
                if time_ms <= 60.0:
                    if "[P1_RX]" in line:
                        r_match = re.search(r'Receiver:\s*(\d+)', line)
                        s_match = re.search(r'Sender:\s*(\d+)', line)
                        if r_match and s_match:
                            p1_rx.add((int(r_match.group(1)), int(s_match.group(1))))
                            
                    elif "[P2_ATTEMPT]" in line:
                        d_match = re.search(r'Drone:\s*(\d+)', line)
                        s_match = re.search(r'Slot:\s*(\d+)', line)
                        c_match = re.search(r'Channel:\s*(\d+)', line)
                        if d_match and s_match and c_match:
                            p2_attempt[int(d_match.group(1))] = (int(s_match.group(1)), int(c_match.group(1)))
                            
                    elif "[P2_RX]" in line:
                        r_match = re.search(r'Receiver:\s*(\d+)', line)
                        s_match = re.search(r'Sender:\s*(\d+)', line)
                        if r_match and s_match:
                            p2_rx.add((int(r_match.group(1)), int(s_match.group(1))))

except FileNotFoundError:
    print(f"Error: {log_file} not found. Please run the simulation first.")
    sys.exit(1)

# Analysis Counters
total_expected_links = 0
success = 0
p1_miss = 0
rx_deafness = 0
slot_conflict = 0
p2_abort = 0
physical_collision = 0
fading_loss = 0

for b, targets in top_5.items():
    for a in targets:
        total_expected_links += 1
        
        if (b, a) in p2_rx:
            success += 1
            continue
            
        if (b, a) not in p1_rx:
            p1_miss += 1
            continue
            
        if a not in p2_attempt:
            p2_abort += 1
            continue
            
        slot_a, chan_a = p2_attempt[a]
        
        # Did B transmit?
        if b in p2_attempt:
            slot_b, chan_b = p2_attempt[b]
            if slot_b == slot_a:
                rx_deafness += 1
                continue
                
        # Did B drop A because of a closer neighbor choosing the same slot?
        # Closer neighbors are those appearing BEFORE 'a' in 'targets'
        closer_neighbors = targets[:targets.index(a)]
        conflict = False
        for c in closer_neighbors:
            if (b, c) in p1_rx and c in p2_attempt:
                slot_c, _ = p2_attempt[c]
                if slot_c == slot_a:
                    conflict = True
                    break
        if conflict:
            slot_conflict += 1
            continue
            
        # B should have listened to A's slot/channel. Was there interference?
        interferers = [x for x, (s, c) in p2_attempt.items() if x != a and s == slot_a and c == chan_a]
        if len(interferers) > 0:
            physical_collision += 1
            continue
            
        # Otherwise, generic fading/distance loss
        fading_loss += 1

print(f"Total Theoretical Top-5 Links to satisfy in Epoch 1: {total_expected_links}")
print(f"✅ Successful Receptions (Phase 2): {success} ({(success/total_expected_links)*100:.1f}%)")
print("--------------------------------------------------")
print("❌ FAILURE REASONS (EXACT NUMBERS FROM LOG):")
print(f"  1. Phase 1 Miss (Receiver didn't hear Sender in P1): {p1_miss}")
print(f"  2. RX Deafness (Receiver transmitted in Sender's slot): {rx_deafness}")
print(f"  3. Slot Conflict (Closer neighbor took the same slot): {slot_conflict}")
print(f"  4. Physical Collision (Someone else used same Slot+Channel): {physical_collision}")
print(f"  5. Phase 2 Abort (Sender failed to TX in P2): {p2_abort}")
print(f"  6. Fading / SINR Loss (Signal too weak or random noise): {fading_loss}")
print("==================================================")
