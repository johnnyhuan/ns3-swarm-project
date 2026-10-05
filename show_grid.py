#!/usr/bin/env python3
import sys
import collections

if len(sys.argv) < 2:
    print("Usage: ./show_grid.py <run.log>")
    sys.exit(1)

log_file = sys.argv[1]

# epoch_id -> { slot -> { channel -> [drone_ids] } }
epochs = collections.defaultdict(lambda: collections.defaultdict(lambda: collections.defaultdict(list)))

with open(log_file, 'r') as f:
    for line in f:
        # [P2_ATTEMPT] Time: 76.5ms, Drone: 12, Slot: 3, Channel: 4
        if "[P2_ATTEMPT]" in line:
            parts = line.strip().split(',')
            time_str = parts[0].split('Time:')[1].replace('ms', '').strip()
            time_val = float(time_str)
            drone_str = parts[1].split('Drone:')[1].strip()
            drone_id = int(drone_str)
            slot_str = parts[2].split('Slot:')[1].strip()
            slot = int(slot_str)
            ch_str = parts[3].split('Channel:')[1].strip()
            ch = int(ch_str)
            
            # 51ms per epoch. Epoch 1 starts Phase 2 at ~25ms.
            epoch_id = int(time_val / 51.0) + 1
            
            epochs[epoch_id][slot][ch].append(drone_id)

# Print a few epochs
for target_epoch in [2, 3]:
    if target_epoch not in epochs:
        continue
    
    print(f"\n================ EPOCH {target_epoch} SLOT ALLOCATION (Global View) ================")
    print(f"{'Slot':<5} | " + " | ".join([f"Ch {c:<18}" for c in range(6)]))
    print("-" * 140)
    
    for s in range(10):
        row_str = f"{s:<5} | "
        for c in range(6):
            drones = epochs[target_epoch][s][c]
            if not drones:
                drones_str = "-"
            else:
                drones_str = ",".join(map(str, drones))
                if len(drones) > 1:
                    drones_str = f"[{drones_str}]" # visually group them
            row_str += f"{drones_str:<21} | "
        print(row_str)
    
    total_drones = sum(len(epochs[target_epoch][s][c]) for s in range(10) for c in range(6))
    print(f"Total Drones scheduled: {total_drones}/50")
    print("Note: [x,y,z] indicates multiple drones selected the exact same slot and channel globally.")
