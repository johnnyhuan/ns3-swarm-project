#!/usr/bin/env python3
import sys
import re

print("==================================================")
print("      Phase 2: Epoch 1 (0ms-51ms) Deep Analysis   ")
print("==================================================")

log_file = "run.log"

attempts = {} # drone_id -> {"slot": s, "channel": c}
receives = {} # receiver -> set of senders it successfully received from

try:
    with open(log_file, "r") as f:
        for line in f:
            if "Time:" in line:
                # Extract time to ensure we are in Epoch 1 (0 to 60ms is safe)
                match = re.search(r'Time:\s*([\d\.]+)ms', line)
                if match:
                    time_ms = float(match.group(1))
                    if time_ms > 60.0:
                        break # Stop parsing after Epoch 1
                    
                    if "[P2_ATTEMPT]" in line:
                        d_match = re.search(r'Drone:\s*(\d+)', line)
                        s_match = re.search(r'Slot:\s*(\d+)', line)
                        c_match = re.search(r'Channel:\s*(\d+)', line)
                        if d_match and s_match and c_match:
                            drone = int(d_match.group(1))
                            slot = int(s_match.group(1))
                            channel = int(c_match.group(1))
                            attempts[drone] = {"slot": slot, "channel": channel}
                            
                    elif "[P2_RX]" in line:
                        r_match = re.search(r'Receiver:\s*(\d+)', line)
                        s_match = re.search(r'Sender:\s*(\d+)', line)
                        if r_match and s_match:
                            receiver = int(r_match.group(1))
                            sender = int(s_match.group(1))
                            if receiver not in receives:
                                receives[receiver] = set()
                            receives[receiver].add(sender)

except FileNotFoundError:
    print(f"Error: {log_file} not found. Please run the simulation first.")
    sys.exit(1)

# Analysis Phase
grid = {} # slot -> channel -> list of sender drones
for drone, data in attempts.items():
    slot = data["slot"]
    channel = data["channel"]
    if slot not in grid:
        grid[slot] = {}
    if channel not in grid[slot]:
        grid[slot][channel] = []
    grid[slot][channel].append(drone)

# 1. Total Transmitters
total_tx = len(attempts)
print(f"Total Drones Transmitting in Epoch 1: {total_tx}")

# 2. Identify Collisions
collisions = []
for slot, channels in grid.items():
    for channel, senders in channels.items():
        if len(senders) > 1:
            collisions.append((slot, channel, senders))

print(f"\n[1] Direct Resource Collisions: {len(collisions)} occurrences")
for slot, channel, senders in collisions:
    print(f"    - Slot {slot}, Channel {channel} was shared by: {senders}")

# 3. Analyze potential RX Deafness for each attempt
deafness_pairs = 0
for slot, channels in grid.items():
    senders_in_slot = []
    for c, s_list in channels.items():
        senders_in_slot.extend(s_list)
    
    # If there are >1 senders in the same slot, they are all deaf to each other!
    if len(senders_in_slot) > 1:
        # Number of deaf pairs = N * (N-1)
        n = len(senders_in_slot)
        deafness_pairs += n * (n - 1)

print(f"\n[2] RX Deafness (Half-Duplex) Impact:")
print(f"    - Found {deafness_pairs} potential pairwise interactions blocked because both drones transmitted in the same Slot.")

# 4. Actual successful receptions
total_rx = sum(len(senders) for senders in receives.values())
print(f"\n[3] Total Successful P2 Receptions in Epoch 1: {total_rx}")
print(f"    - This represents roughly {total_rx}/250 ({(total_rx/250)*100:.1f}%) of the theoretical Top-5 topology limit.")

# 5. Let's trace specific lost packets.
tx_success_count = {d: 0 for d in attempts.keys()}
for r, senders in receives.items():
    for s in senders:
        if s in tx_success_count:
            tx_success_count[s] += 1

failed_tx = [d for d, count in tx_success_count.items() if count <= 1]
print(f"\n[4] Drones whose transmissions were received by 1 or 0 neighbors: {len(failed_tx)} drones")
for d in failed_tx[:10]: # Print top 10
    slot = attempts[d]['slot']
    channel = attempts[d]['channel']
    shared_with = grid[slot][channel]
    collision_str = f"Collided with {shared_with}" if len(shared_with) > 1 else "No direct collision"
    print(f"    - Drone {d} (Slot {slot}, Ch {channel}): Received by {tx_success_count[d]} drones. ({collision_str})")
if len(failed_tx) > 10:
    print(f"    - ... and {len(failed_tx)-10} more.")

print("\n==================================================")
