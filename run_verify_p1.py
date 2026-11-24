#!/usr/bin/env python3
"""
P1 verification suite: is a discovered neighbour really discovered?

  1. Known-answer tests (SSA, fixed positions, forced P1 slots, +8 dBm): range edge, the 6 dB lock
     rule inside one slot, half duplex, adjacent slots. PASS only if every link behaves exactly
     as worked out by hand in every cycle.
  2. Independent cross-check (verify_crosscheck.P1Model) of every counted beacon reception in a
     100-UAV run, for tuned SSA and tuned CSMA: the packet ID belongs to a beacon that sender
     really sent in this cycle, not cut, receiver not transmitting, SINR >= 6 dB recomputed from
     positions and every overlapping beacon, evaluation consistent with the receptions.
     The 4-byte beacon has no room for an extra CRC, so the cycle/sender identity is checked
     through the packet ID in the logs instead (same purpose as the P2 payload check).

Usage:
    python3 run_verify_p1.py              # pushes results
    python3 run_verify_p1.py --no-push
"""
import argparse
import math
import os
import shutil
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import verify_crosscheck as vc

ap = argparse.ArgumentParser()
ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
ap.add_argument("--no-push", action="store_true")
a = ap.parse_args()

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
NS3_DIR = os.path.expanduser(os.environ.get("NS3_DIR", "~/ns-3-dev"))
if not os.path.exists(os.path.join(NS3_DIR, "ns3")):
    sys.exit(f"ns-3 not found at {NS3_DIR} (set NS3_DIR)")
for rel in ["scratch/lr-wpan-swarm.cc",
            "src/lr-wpan/model/lr-wpan-phy.cc", "src/lr-wpan/model/lr-wpan-phy.h",
            "src/lr-wpan/model/lr-wpan-csmaca.cc", "src/lr-wpan/model/lr-wpan-csmaca.h",
            "src/lr-wpan/model/lr-wpan-mac.cc", "src/lr-wpan/model/lr-wpan-mac.h"]:
    s, d = os.path.join(PROJECT_DIR, rel), os.path.join(NS3_DIR, rel)
    if os.path.exists(s) and os.path.abspath(s) != os.path.abspath(d):
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copy(s, d)

COMMON = "--p1Duration=10 --preambleLockDb=6 --autoPush=false"
SSA = ("--enableP1Ssa=true --p1SlotUs=150 --p1TxPower=8 --p1SenseDecay=0.7 --p1ReselInitMin=2 --p1ReselInitMax=5 "
       "--p1ReselMin=30 --p1ReselMax=90 --p1PoolFrac=0.25")
CSMA = ("--enableP1Ssa=false --p1TxPower=4 --p1CcaThresholdDbm=-94 --p1MinBE=0 --p1MaxBackoffs=1 "
        "--p1RetryMinMs=0.05 --p1RetryMaxMs=0.2")
P2 = "--p1AvoidDist=50 --numSlots=24 --numChannels=10 --dataSlotUs=400 --slotGuardBandUs=30 --p2ExtraRx=3 --p2TxPower=4"
SWARM = "--numNodes=100 --nodeSpeed=10.0 --spaceSize=200 --spaceZ=80 --rngRun=1"


def pr(p, d):
    return p - 46.6777 - 30 * math.log10(d)


# expect: (sender, receiver, 'always' | 'never', why)
TESTS = [
    dict(name="T1 range edge: 70 m at +8 dBm", pos="0,0,10;70,0,10", slots="0:10;1:40",
         expect=[(1, 0, "always", f"RX {pr(8, 70):.2f} dBm >= -95 dBm"), (0, 1, "always", "other direction")]),
    dict(name="T2 range edge: 80 m at +8 dBm", pos="0,0,10;80,0,10", slots="0:10;1:40",
         expect=[(1, 0, "never", f"RX {pr(8, 80):.2f} dBm < -95 dBm"), (0, 1, "never", "other direction")]),
    dict(name="T3 same slot, interferer 1.5x farther", pos="0,0,10;10,0,10;-15,0,10", slots="0:30;1:5;2:5",
         expect=[(1, 0, "never", f"10 m vs 15 m: {30 * math.log10(1.5):.2f} dB < 6 dB"),
                 (2, 0, "never", "weaker one")]),
    dict(name="T4 same slot, interferer 2x farther", pos="0,0,10;10,0,10;-20,0,10", slots="0:30;1:5;2:5",
         expect=[(1, 0, "always", f"10 m vs 20 m: {30 * math.log10(2):.2f} dB > 6 dB"),
                 (2, 0, "never", "weaker one can never lock")]),
    dict(name="T5 half duplex: both in the same slot", pos="0,0,10;10,0,10", slots="0:5;1:5",
         expect=[(0, 1, "never", "receiver is transmitting"), (1, 0, "never", "receiver is transmitting")]),
    dict(name="T6 adjacent slots (5 and 6) do not overlap", pos="0,0,10;10,0,10", slots="0:5;1:6",
         expect=[(0, 1, "always", "slot 5 TX ends at 136 us, slot 6 TX starts at 190 us"),
                 (1, 0, "always", "radio is back in RX 40 us after its own beacon")]),
]

b = subprocess.run(["./ns3", "build", "scratch/lr-wpan-swarm"], cwd=NS3_DIR,
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
if b.returncode != 0:
    print(b.stdout[-3000:])
    sys.exit("build failed")
run_root = os.path.join(NS3_DIR, "verify_p1_runs")
shutil.rmtree(run_root, ignore_errors=True)


def run(tag, flags):
    d = os.path.join(run_root, tag)
    os.makedirs(d)
    p = subprocess.run(["./ns3", "run", "--no-build", "--cwd", d, f"scratch/lr-wpan-swarm {flags}"],
                       cwd=NS3_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return tag, d, p.returncode, p.stdout[-2000:]


jobs = [("swarm_ssa_3s", f"--simTime=3 {SWARM} {COMMON} {SSA} {P2} --verifyLog=true"),
        ("swarm_csma_3s", f"--simTime=3 {SWARM} {COMMON} {CSMA} {P2} --verifyLog=true")]
for i, t in enumerate(TESTS):
    jobs.append((f"test{i + 1}", f"--simTime=2 {COMMON} {SSA} {P2} --verifyLog=true --positions={t['pos']} --forceP1Slots={t['slots']}"))

print(f"▶ {len(jobs)} runs, {a.jobs} in parallel ...", flush=True)
done = {}
with ThreadPoolExecutor(max_workers=a.jobs) as ex:
    for tag, d, rc, out in ex.map(lambda j: run(*j), jobs):
        if rc != 0:
            print(out)
            sys.exit(f"✗ {tag} crashed")
        done[tag] = d
        print(f"   {tag} done", flush=True)

lines = ["P1 verification suite (SSA tuned: 150 us x 66 slots, +8 dBm; CSMA tuned: +4 dBm, CCA -94 dBm)", "=" * 100]
all_ok = True
lines.append("1. KNOWN-ANSWER TESTS (SSA, fixed positions, forced P1 slots, +8 dBm, 2 s each)")
for i, t in enumerate(TESTS):
    m = vc.P1Model(done[f"test{i + 1}"], 8.0)
    epochs = {r["epoch"] for r in m.tx}
    sent = defaultdict(set)
    for r in m.tx:
        if not r["cut"]:
            sent[r["sender"]].add(r["epoch"])
    got = defaultdict(set)
    for r in m.rx:
        got[(r["tx"], r["rx"])].add(r["epoch"])
    lines.append(f"  {t['name']}  (positions {t['pos']}; P1 slots {t['slots']})")
    ok_t = True
    for s, r, exp, why in t["expect"]:
        n = len(epochs)
        if exp == "always":
            ok = len(sent[s]) >= 0.9 * n and sent[s] <= got[(s, r)]
        else:
            ok = len(got[(s, r)]) == 0 and len(sent[s]) >= 0.9 * n
        ok_t &= ok
        lines.append(f"     UAV {s} -> UAV {r}: expect {exp:6s} -> {'PASS' if ok else 'FAIL'}  "
                     f"(received {len(got[(s, r)])} / sent {len(sent[s])} / cycles {n})  [{why}]")
    nv = sum(len(v) for v in m.check()["violations"].values())
    ok_t &= nv == 0
    lines.append(f"     cross-check violations: {nv}")
    all_ok &= ok_t

lines.append("")
lines.append("2. INDEPENDENT CROSS-CHECK OF EVERY BEACON RECEPTION (100 UAVs, 3 s, seed 1)")
for tag, p in (("swarm_ssa_3s", 8.0), ("swarm_csma_3s", 4.0)):
    res = vc.P1Model(done[tag], p).check()
    nv = sum(len(v) for v in res["violations"].values())
    all_ok &= nv == 0
    lines.append(f"  {tag}: {'PASS' if nv == 0 else 'FAIL'} ({nv} violations)")
    lines.append("    " + vc.report_p1(res).replace("\n", "\n    "))
lines.append("")
lines.append("OVERALL: " + ("ALL PASS" if all_ok else "SOME CHECKS FAILED"))
summary = "\n".join(lines) + "\n"
print("\n" + summary)
with open(os.path.join(PROJECT_DIR, "verify_p1_summary.txt"), "w", encoding="utf-8") as f:
    f.write(summary)
shutil.rmtree(run_root, ignore_errors=True)

if a.no_push:
    sys.exit(0 if all_ok else 1)
files = ["verify_p1_summary.txt", "run_verify_p1.py", "verify_crosscheck.py", "scratch/lr-wpan-swarm.cc"]
try:
    subprocess.run(["git", "pull", "--rebase", "--autostash", "origin", "main"], cwd=PROJECT_DIR, check=True)
    subprocess.run(["git", "add", "-f"] + files, cwd=PROJECT_DIR, check=True)
    subprocess.run(["git", "commit", "-m", f"verify: P1 verification suite ({'all pass' if all_ok else 'FAILURES'})"],
                   cwd=PROJECT_DIR, check=True)
    subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=PROJECT_DIR, check=True)
    print("✓ Results pushed to GitHub")
except subprocess.CalledProcessError as e:
    print(f"⚠ Git upload failed ({e}); results are still saved locally in {PROJECT_DIR}")
