#!/usr/bin/env python3
"""
Side-by-Side Performance Comparison Runner
Version A: Continuous Random Delay + CSMA-CA (Baseline)
Version B: 3GPP Sidelink Mode 4 Sensing-Based Semi-Persistent Scheduling (S-SPS, No CSMA)
"""

import subprocess
import os
import sys
import re
from datetime import datetime

print("==========================================================================")
print("⚔️  PHASE 1 ARCHITECTURE COMPARISON: SIDELINK S-SPS vs CSMA-CA  ⚔️")
print("==========================================================================")

# Command-line arguments
p1_duration = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0
sim_time = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
p1_slot_us = float(sys.argv[3]) if len(sys.argv) > 3 else 100.0
num_nodes = int(sys.argv[4]) if len(sys.argv) > 4 else 75
space_size = float(sys.argv[5]) if len(sys.argv) > 5 else 200.0
space_z = float(sys.argv[6]) if len(sys.argv) > 6 else 80.0

print(f"• Swarm Scale         : {num_nodes} UAVs")
print(f"• Airspace Volume     : {space_size:.0f}m x {space_size:.0f}m x {space_z:.0f}m")
print(f"• Phase 1 Window      : {p1_duration} ms")
print(f"• Sidelink Slot Width : {p1_slot_us} µs ({int((p1_duration * 1000.0 - 250.0) / p1_slot_us) + 1} slots)")
print(f"• Simulation Duration : {sim_time} s")
print("--------------------------------------------------------------------------\n")

# Detect paths
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
NS3_DIR = os.path.expanduser("~/ns-3-dev")
if not os.path.exists(NS3_DIR):
    NS3_DIR = PROJECT_DIR

# 1. Sync updated files to NS3_DIR if running from external repo
sync_files = [
    "scratch/lr-wpan-swarm.cc",
    "src/lr-wpan/model/lr-wpan-phy.cc",
    "src/lr-wpan/model/lr-wpan-phy.h",
    "src/lr-wpan/model/lr-wpan-constants.h",
    "src/lr-wpan/model/lr-wpan-csmaca.cc"
]
for rel_path in sync_files:
    src_f = os.path.join(PROJECT_DIR, rel_path)
    dst_f = os.path.join(NS3_DIR, rel_path)
    if os.path.exists(src_f) and os.path.abspath(src_f) != os.path.abspath(dst_f):
        try:
            print(f"=> Syncing {rel_path} to {dst_f}...")
            os.makedirs(os.path.dirname(dst_f), exist_ok=True)
            subprocess.run(["cp", src_f, dst_f], check=True)
        except Exception as e:
            print(f"Error syncing {rel_path}: {e}")
            sys.exit(1)

def run_simulation(enable_sidelink, slot_us):
    mode_name = f"Sidelink S-SPS (Slot={slot_us}us, No CSMA)" if enable_sidelink else "Continuous Delay + CSMA-CA (Baseline)"
    print(f"\n🚀 Running: {mode_name} ...")

    # Clean old report files before run
    for fname in ["p1_ground_truth_report.txt", "p2_ground_truth_report.txt", "run.log"]:
        fpath = os.path.join(NS3_DIR, fname)
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
            except Exception:
                pass
    
    sidelink_flag = f"--enableP1Sidelink=true --p1SlotUs={slot_us}" if enable_sidelink else "--enableP1Sidelink=false"
    cmd = [
        "./ns3", "run",
        f"scratch/lr-wpan-swarm --numNodes={num_nodes} --p1Duration={p1_duration} "
        f"--simTime={sim_time} --spaceSize={space_size} --spaceZ={space_z} "
        f"--p1TxPower=0 --p2TxPower=-2 --p1CcaThresholdDbm=-96.58 --nodeSpeed=10.0 "
        f"{sidelink_flag} --autoPush=false"
    ]
    
    proc = subprocess.run(cmd, cwd=NS3_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    out = proc.stdout

    if proc.returncode != 0:
        print(f"\n❌ Execution failed (exit code {proc.returncode})!")
        print(out)
        sys.exit(1)

    # Read generated p1 report
    p1_rpt = os.path.join(NS3_DIR, "p1_ground_truth_report.txt")
    p1_text = ""
    if os.path.exists(p1_rpt):
        with open(p1_rpt, "r", encoding="utf-8", errors="ignore") as f:
            p1_text = f.read()

    # Read generated p2 report
    p2_rpt = os.path.join(NS3_DIR, "p2_ground_truth_report.txt")
    p2_text = ""
    if os.path.exists(p2_rpt):
        with open(p2_rpt, "r", encoding="utf-8", errors="ignore") as f:
            p2_text = f.read()

    # Read run.log
    run_log = os.path.join(NS3_DIR, "run.log")
    log_text = ""
    if os.path.exists(run_log):
        with open(run_log, "r", encoding="utf-8", errors="ignore") as f:
            log_text = f.read()

    combined_stdout = out + "\n" + log_text
    return parse_metrics(p1_text, p2_text, combined_stdout)

def parse_metrics(p1_text, p2_text, stdout_text):
    data = {
        "p1_links": 0,
        "p1_success": 0,
        "p1_prr": 0.0,
        "p1_fails": 0,
        "csma_abort": 0,
        "rx_deafness": 0,
        "preamble_coll": 0,
        "low_sinr": 0,
        "turnaround": 0,
        "payload_drop": 0,
        "captures": 0,
        "steady_links": 0,
        "steady_success": 0,
        "steady_prr": 0.0,
        "p2_prr": 0.0,
        "mean_iat": 0.0,
        "mean_aoi": 0.0
    }
    
    # Priority: Parse Phase 1 metrics from p1_text
    src_p1 = p1_text if p1_text else stdout_text
    
    m = re.search(r"Total Expected P1 Neighbor Links.*:\s*(\d+)", src_p1)
    if m: data["p1_links"] = int(m.group(1))
    
    m = re.search(r"Successfully Received \(Delivered\)\s*:\s*(\d+)\s*\(([\d\.]+)%\)", src_p1)
    if m:
        data["p1_success"] = int(m.group(1))
        data["p1_prr"] = float(m.group(2))
        
    m = re.search(r"Failed Link Receptions \(Dropped/Missed\)\s*:\s*(\d+)", src_p1)
    if m: data["p1_fails"] = int(m.group(1))
    
    m = re.search(r"SENDER_CSMA_ABORT\s*:\s*(\d+)", src_p1)
    if m: data["csma_abort"] = int(m.group(1))

    m = re.search(r"RX_DEAFNESS_BUSY_TX\s*:\s*(\d+)", src_p1)
    if m: data["rx_deafness"] = int(m.group(1))

    m = re.search(r"PREAMBLE_COLLISION_BUSY_RX\s*:\s*(\d+)", src_p1)
    if m: data["preamble_coll"] = int(m.group(1))

    m = re.search(r"PREAMBLE_LOW_SINR\s*:\s*(\d+)", src_p1)
    if m: data["low_sinr"] = int(m.group(1))

    m = re.search(r"RADIO_TURNAROUND_BUSY\s*:\s*(\d+)", src_p1)
    if m: data["turnaround"] = int(m.group(1))

    m = re.search(r"PAYLOAD_INTERFERENCE_CORRUPTION\s*:\s*(\d+)", src_p1)
    if m: data["payload_drop"] = int(m.group(1))

    m = re.search(r"Total Power Capture Events Triggered\s*:\s*(\d+)", src_p1)
    if m: data["captures"] = int(m.group(1))

    # Parse Steady-State Phase 1 metrics
    m = re.search(r"Steady-State P1 Target Links.*:\s*(\d+)", src_p1)
    if m:
        data["steady_links"] = int(m.group(1))
        m_succ = re.search(r"Steady-State P1 Target Links[\s\S]*?Successfully Received \(Delivered\)\s*:\s*(\d+)\s*\(([\d\.]+)%\)", src_p1)
        if m_succ:
            data["steady_success"] = int(m_succ.group(1))
            data["steady_prr"] = float(m_succ.group(2))

    # Priority: Parse Phase 2 metrics from p2_text
    src_p2 = p2_text if p2_text else stdout_text
    m = re.search(r"Successfully Received \(Delivered\)\s*:\s*(\d+)\s*\(([\d\.]+)%\)", src_p2)
    if m:
        data["p2_prr"] = float(m.group(2))

    # Parse IAT & AoI from stdout/run.log
    m = re.search(r"Avg Discovery Msg IAT \(Top-K\)\s*:\s*([\d\.]+)\s*ms", stdout_text)
    if m: data["mean_iat"] = float(m.group(1))

    m = re.search(r"Mean Beacon Packet AoI \(Top-K\)\s*:\s*([\d\.]+)\s*ms", stdout_text)
    if m: data["mean_aoi"] = float(m.group(1))

    return data

# Run both versions
res_csma = run_simulation(enable_sidelink=False, slot_us=p1_slot_us)
res_sidelink = run_simulation(enable_sidelink=True, slot_us=p1_slot_us)

# Print Comparison Table
print("\n" + "=" * 92)
print("📊 HEAD-TO-HEAD RESULTS: CONTINUOUS CSMA-CA vs 3GPP SIDELINK S-SPS (No CSMA)")
print("=" * 92)
header = f"{'Metric / Feature':<38} | {'CSMA-CA (Baseline)':<22} | {'Sidelink S-SPS':<22} | {'Diff / Impact':<12}"
print(header)
print("-" * 92)

def fmt_row(name, val_a, val_b, is_pct=False, invert_better=False):
    s_a = f"{val_a:.1f}%" if is_pct else str(val_a)
    s_b = f"{val_b:.1f}%" if is_pct else str(val_b)
    diff = val_b - val_a
    diff_s = f"{diff:+.1f}%" if is_pct else f"{diff:+d}"
    
    if abs(diff) < 1e-4:
        tag = "="
    elif (diff > 0 and not invert_better) or (diff < 0 and invert_better):
        tag = "🏆"
    else:
        tag = ""
    return f"{name:<38} | {s_a:<22} | {s_b:<22} | {diff_s:<7} {tag}"

print(fmt_row("Phase 1 Delivery PRR (Overall)", res_csma["p1_prr"], res_sidelink["p1_prr"], is_pct=True))
if res_csma["steady_links"] > 0 or res_sidelink["steady_links"] > 0:
    print(fmt_row("Phase 1 Steady-State PRR (Last 2s)", res_csma["steady_prr"], res_sidelink["steady_prr"], is_pct=True))
print(fmt_row("Delivered Links", res_csma["p1_success"], res_sidelink["p1_success"]))
print(fmt_row("Total Failed Links", res_csma["p1_fails"], res_sidelink["p1_fails"], invert_better=True))
print("-" * 92)
print("Physical & MAC Root Cause Breakdown:")
print(fmt_row("  • CSMA Aborts (Channel Busy)", res_csma["csma_abort"], res_sidelink["csma_abort"], invert_better=True))
print(fmt_row("  • RX Deafness (Half-Duplex)", res_csma["rx_deafness"], res_sidelink["rx_deafness"], invert_better=True))
print(fmt_row("  • Preamble Busy RX Collisions", res_csma["preamble_coll"], res_sidelink["preamble_coll"], invert_better=True))
print(fmt_row("  • Preamble Low SINR Drops", res_csma["low_sinr"], res_sidelink["low_sinr"], invert_better=True))
print(fmt_row("  • Transceiver Turnaround Busy", res_csma["turnaround"], res_sidelink["turnaround"], invert_better=True))
print(fmt_row("  • Payload Interference Drops", res_csma["payload_drop"], res_sidelink["payload_drop"], invert_better=True))
print("-" * 92)
print("Physical Layer Capture Effect & System Metrics:")
print(fmt_row("  • Power Capture Events Rescued", res_csma["captures"], res_sidelink["captures"]))
if res_csma["p2_prr"] > 0 or res_sidelink["p2_prr"] > 0:
    print(fmt_row("Phase 2 P2P Delivery PRR", res_csma["p2_prr"], res_sidelink["p2_prr"], is_pct=True))
if res_csma["mean_iat"] > 0 or res_sidelink["mean_iat"] > 0:
    print(f"{'Phase 1 Mean Discovery IAT':<38} | {res_csma['mean_iat']:<22.2f} ms | {res_sidelink['mean_iat']:<22.2f} ms | {res_sidelink['mean_iat'] - res_csma['mean_iat']:+6.2f} ms")
if res_csma["mean_aoi"] > 0 or res_sidelink["mean_aoi"] > 0:
    print(f"{'Phase 2 Mean Age of Info (AoI)':<38} | {res_csma['mean_aoi']:<22.2f} ms | {res_sidelink['mean_aoi']:<22.2f} ms | {res_sidelink['mean_aoi'] - res_csma['mean_aoi']:+6.2f} ms")
print("=" * 92)

# Generate Markdown Report
md_report_path = os.path.join(PROJECT_DIR, "SIDELINK_VS_CSMA_COMPARISON.md")
with open(md_report_path, "w", encoding="utf-8") as f:
    f.write(f"# Phase 1 Architecture Comparison: Sidelink S-SPS vs CSMA-CA\n\n")
    f.write(f"- **Generated At**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write(f"- **Swarm Setup**: {num_nodes} UAVs in {space_size:.0f}m x {space_size:.0f}m x {space_z:.0f}m\n")
    f.write(f"- **Phase 1 Duration**: {p1_duration} ms | **Slot Width**: {p1_slot_us} µs\n\n")
    f.write(f"| Metric / Root Cause | CSMA-CA (Baseline) | 3GPP Sidelink S-SPS | Difference |\n")
    f.write(f"| :--- | :--- | :--- | :--- |\n")
    f.write(f"| **Phase 1 PRR (Overall 0~{sim_time:.0f}s)** | **{res_csma['p1_prr']:.1f}%** | **{res_sidelink['p1_prr']:.1f}%** | **{res_sidelink['p1_prr'] - res_csma['p1_prr']:+.1f}%** |\n")
    if res_csma["steady_links"] > 0 or res_sidelink["steady_links"] > 0:
        f.write(f"| **Phase 1 Steady-State PRR (Last 2s)** | **{res_csma['steady_prr']:.1f}%** | **{res_sidelink['steady_prr']:.1f}%** | **{res_sidelink['steady_prr'] - res_csma['steady_prr']:+.1f}%** |\n")
    f.write(f"| Delivered Links | {res_csma['p1_success']} | {res_sidelink['p1_success']} | {res_sidelink['p1_success'] - res_csma['p1_success']:+d} |\n")
    f.write(f"| Total Dropped Links | {res_csma['p1_fails']} | {res_sidelink['p1_fails']} | {res_sidelink['p1_fails'] - res_csma['p1_fails']:+d} |\n")
    f.write(f"| CSMA Aborts | {res_csma['csma_abort']} | {res_sidelink['csma_abort']} | {res_sidelink['csma_abort'] - res_csma['csma_abort']:+d} |\n")
    f.write(f"| RX Deafness (Half-Duplex) | {res_csma['rx_deafness']} | {res_sidelink['rx_deafness']} | {res_sidelink['rx_deafness'] - res_csma['rx_deafness']:+d} |\n")
    f.write(f"| Preamble Collisions | {res_csma['preamble_coll']} | {res_sidelink['preamble_coll']} | {res_sidelink['preamble_coll'] - res_csma['preamble_coll']:+d} |\n")
    f.write(f"| Preamble Low SINR Drops | {res_csma['low_sinr']} | {res_sidelink['low_sinr']} | {res_sidelink['low_sinr'] - res_csma['low_sinr']:+d} |\n")
    f.write(f"| Turnaround Busy Drops | {res_csma['turnaround']} | {res_sidelink['turnaround']} | {res_sidelink['turnaround'] - res_csma['turnaround']:+d} |\n")
    f.write(f"| Payload Interference Drops | {res_csma['payload_drop']} | {res_sidelink['payload_drop']} | {res_sidelink['payload_drop'] - res_csma['payload_drop']:+d} |\n")
    f.write(f"| Power Capture Rescued Packets | {res_csma['captures']} | {res_sidelink['captures']} | {res_sidelink['captures'] - res_csma['captures']:+d} |\n")
    f.write(f"| Phase 2 PRR | {res_csma['p2_prr']:.1f}% | {res_sidelink['p2_prr']:.1f}% | {res_sidelink['p2_prr'] - res_csma['p2_prr']:+.1f}% |\n")
    f.write(f"| Phase 1 Mean IAT | {res_csma['mean_iat']:.2f} ms | {res_sidelink['mean_iat']:.2f} ms | {res_sidelink['mean_iat'] - res_csma['mean_iat']:+.2f} ms |\n")
    f.write(f"| Phase 2 Mean AoI | {res_csma['mean_aoi']:.2f} ms | {res_sidelink['mean_aoi']:.2f} ms | {res_sidelink['mean_aoi'] - res_csma['mean_aoi']:+.2f} ms |\n")

print(f"\n✅ Summary report saved to {md_report_path}")
