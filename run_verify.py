#!/usr/bin/env python3
"""
P2 verification suite: is a 'received' packet really received?

  1. Known-answer tests: a few UAVs at fixed positions with forced P2 cells. Each link has an
     answer that can be worked out by hand (range edge, 6 dB lock rule, half duplex, channel
     isolation, two-copy rescue). PASS only if every link behaves exactly as expected.
  2. Independent cross-check (verify_crosscheck.py) of every reception in a normal 100-UAV run
     (and of every test): sender really sent, receiver on the right channel and not sending,
     SINR >= 6 dB recomputed from positions, evaluation consistent with the receptions.
  3. Payload check: each 50-byte P2 packet carries sender ID, cycle, sequence and CRC-32; the
     receiver only counts packets that check out for the current cycle; 0 may be rejected
     (when it was added, the 10 s 100-UAV PRR stayed exactly the same, 95.9 % at seed 1).
  4. Timeline: one UAV, one cycle, slot by slot, for a hand check.

Usage:
    python3 run_verify.py              # all, pushes results
    python3 run_verify.py --no-push
"""
import argparse
import math
import os
import re
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

# Official P1 (SSA tuned) + P2 settings
P1 = ("--p1Duration=10 --preambleLockDb=6 --autoPush=false --enableP1Ssa=true --p1SlotUs=150 --p1TxPower=7 "
      "--p1SenseDecay=0.7 --p1ReselInitMin=2 --p1ReselInitMax=5 --p1ReselMin=30 --p1ReselMax=90 --p1PoolFrac=0.25")
P2 = "--p1AvoidDist=50 --numSlots=24 --numChannels=10 --dataSlotUs=400 --slotGuardBandUs=30 --p2ExtraRx=3"
SWARM = "--nodeSpeed=10.0 --spaceSize=200 --spaceZ=80"


def pr(p_tx, d):
    return p_tx - 46.6777 - 30 * math.log10(d)


# Known-answer tests. Node ids follow the order of --positions. Channel index c -> radio channel 12+c.
# expect: (sender, receiver, 'always' | 'never', why). 'always' = received in every cycle the receiver
# listened to that sender; 'never' = received in no cycle (and the receiver did listen / sender did send).
TESTS = [
    dict(name="T1 range edge, +3 dBm at 45 m", power=3, copies=1,
         pos="0,0,10;45,0,10", cells="",
         expect=[(1, 0, "always", f"RX {pr(3, 45):.1f} dBm >= -94 dBm (SINR {pr(3, 45) + 100:.1f} dB over -100 dBm noise)"),
                 (0, 1, "always", "same, other direction")]),
    dict(name="T2 range edge, +2 dBm at 45 m", power=2, copies=1,
         pos="0,0,10;45,0,10", cells="",
         expect=[(1, 0, "never", f"RX {pr(2, 45):.1f} dBm < -94 dBm (SINR {pr(2, 45) + 100:.1f} dB < 6 dB)"),
                 (0, 1, "never", "same, other direction")]),
    dict(name="T3 same cell, interferer 1.5x farther", power=4, copies=1,
         pos="0,0,10;10,0,10;-15,0,10", cells="1:5:0;2:5:0;0:10:3",
         expect=[(1, 0, "never", f"wanted 10 m vs interferer 15 m: {30 * math.log10(1.5):.2f} dB < 6 dB")]),
    dict(name="T4 same cell, interferer 2x farther", power=4, copies=1,
         pos="0,0,10;10,0,10;-20,0,10", cells="1:5:0;2:5:0;0:10:3",
         expect=[(1, 0, "always", f"wanted 10 m vs interferer 20 m: {30 * math.log10(2):.2f} dB > 6 dB"),
                 (2, 0, "never", "the weaker one in the same cell can never lock")]),
    dict(name="T5 half duplex: both send in the same slot", power=4, copies=1,
         pos="0,0,10;10,0,10", cells="0:5:0;1:5:1",
         expect=[(0, 1, "never", "receiver is transmitting in that slot"),
                 (1, 0, "never", "receiver is transmitting in that slot")]),
    dict(name="T6 control: different slots", power=4, copies=1,
         pos="0,0,10;10,0,10", cells="0:5:0;1:9:1",
         expect=[(0, 1, "always", "10 m, no interference"), (1, 0, "always", "10 m, no interference")]),
    dict(name="T7 same slot, different channels", power=4, copies=1,
         pos="0,0,10;30,0,10;14,0,10;16,0,10", cells="0:5:0;1:5:1;2:10:2;3:12:3",
         expect=[(0, 2, "always", "B is on another channel: no interference"),
                 (1, 3, "always", "A is on another channel: no interference")]),
    dict(name="T8 same slot, same channel (control for T7)", power=4, copies=1,
         pos="0,0,10;30,0,10;14,0,10;16,0,10", cells="0:5:0;1:5:0;2:10:2;3:12:3",
         expect=[(0, 2, "never", f"14 m vs 16 m: {30 * math.log10(16 / 14):.2f} dB < 6 dB"),
                 (1, 3, "never", f"14 m vs 16 m: {30 * math.log10(16 / 14):.2f} dB < 6 dB")]),
    dict(name="T9 two copies: 1st copy collides, 2nd is clean", power=4, copies=2,
         pos="0,0,10;10,0,10;-15,0,10", cells="1:5:0:15:2;2:5:0:20:4;0:10:3:18:5",
         expect=[(1, 0, "always", "copy in slot 5 collides (5.28 dB), copy in slot 15 is clean")],
         slot_expect=(1, 0, 15)),
]

b = subprocess.run(["./ns3", "build", "scratch/lr-wpan-swarm"], cwd=NS3_DIR,
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
if b.returncode != 0:
    print(b.stdout[-3000:])
    sys.exit("build failed")
run_root = os.path.join(NS3_DIR, "verify_runs")
shutil.rmtree(run_root, ignore_errors=True)


def run(tag, flags):
    d = os.path.join(run_root, tag)
    os.makedirs(d)
    p = subprocess.run(["./ns3", "run", "--no-build", "--cwd", d, f"scratch/lr-wpan-swarm {flags}"],
                       cwd=NS3_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return tag, d, p.returncode, p.stdout[-2000:]


jobs = []
for i, t in enumerate(TESTS):
    f = (f"--simTime=2 {P1} {P2} --p2TxPower={t['power']} --p2Copies={t['copies']} --verifyLog=true "
         f"--positions={t['pos']}" + (f" --forceCells={t['cells']}" if t["cells"] else ""))
    jobs.append((f"test{i + 1}", f))
jobs.append(("swarm_2copies_3s", f"--simTime=3 --numNodes=100 {SWARM} {P1} {P2} --p2TxPower=4 --verifyLog=true --rngRun=1"))
jobs.append(("swarm_1copy_3s", f"--simTime=3 --numNodes=100 {SWARM} {P1} {P2} --p2TxPower=4 --p2Copies=1 --verifyLog=true --rngRun=1"))
jobs.append(("swarm_2copies_10s", f"--simTime=10 --numNodes=100 {SWARM} {P1} {P2} --p2TxPower=4 --rngRun=1"))

print(f"▶ {len(jobs)} runs, {a.jobs} in parallel ...", flush=True)
done = {}
with ThreadPoolExecutor(max_workers=a.jobs) as ex:
    for tag, d, rc, out in ex.map(lambda j: run(*j), sorted(jobs, key=lambda j: "swarm" not in j[0])):
        if rc != 0:
            print(out)
            sys.exit(f"✗ {tag} crashed")
        done[tag] = d
        print(f"   {tag} done", flush=True)

lines = ["P2 verification suite (official P1 SSA + P2: 24 x 400 us, 10 ch, 5+3 RX, 2 copies + smart pick)", "=" * 100]
all_ok = True

# ---- 1. known-answer tests ----
lines.append("1. KNOWN-ANSWER TESTS (fixed positions, forced cells, 2 s each)")
for i, t in enumerate(TESTS):
    d = done[f"test{i + 1}"]
    m = vc.Model(d, t["power"])
    epochs = {r["epoch"] for r in m.tx}
    sent = defaultdict(set)
    for r in m.tx:
        if not r["cut"]:
            sent[r["sender"]].add(r["epoch"])
    listened = defaultdict(set)
    for (e, node), sch in m.sched.items():
        for slot, (act, ch, tgt) in sch.items():
            if act == "RX":
                listened[(tgt, node)].add(e)
    got = defaultdict(set)
    got_slots = defaultdict(set)
    for r in m.rx:
        if r["valid"]:
            got[(r["tx"], r["rx"])].add(r["epoch"])
            got_slots[(r["tx"], r["rx"])].add(r["slot"])
    lines.append(f"  {t['name']}  (positions {t['pos']}; cells {t['cells'] or 'free choice'}; {t['power']:+g} dBm; {t['copies']} copy)")
    test_ok = True
    for s, r, exp, why in t["expect"]:
        n_cyc = len(epochs)
        n_listen = len(listened[(s, r)])
        n_got = len(got[(s, r)])
        n_sent = len(sent[s])
        if exp == "always":
            ok = n_listen >= 0.8 * n_cyc and listened[(s, r)] <= got[(s, r)] | (listened[(s, r)] - sent[s])
            detail = f"received {n_got} / listened {n_listen} / cycles {n_cyc}"
        else:
            ok = n_got == 0 and n_sent >= 0.8 * n_cyc
            detail = f"received {n_got} / listened {n_listen} / sent {n_sent} / cycles {n_cyc}"
        test_ok &= ok
        lines.append(f"     UAV {s} -> UAV {r}: expect {exp:6s} -> {'PASS' if ok else 'FAIL'}  ({detail})  [{why}]")
    if "slot_expect" in t:
        s, r, slot = t["slot_expect"]
        ok = got_slots[(s, r)] == {slot}
        test_ok &= ok
        lines.append(f"     UAV {s} -> UAV {r}: received only in slot {slot} -> {'PASS' if ok else 'FAIL'} (slots {sorted(got_slots[(s, r)])})")
    res = m.check()
    nv = sum(len(v) for v in res["violations"].values())
    test_ok &= nv == 0
    lines.append(f"     cross-check violations: {nv}")
    all_ok &= test_ok

# ---- 2. independent cross-check on a swarm ----
lines.append("")
lines.append("2. INDEPENDENT CROSS-CHECK OF EVERY RECEPTION (100 UAVs, 3 s, seed 1)")
for tag in ("swarm_2copies_3s", "swarm_1copy_3s"):
    res = vc.Model(done[tag], 4.0).check()
    nv = sum(len(v) for v in res["violations"].values())
    all_ok &= nv == 0
    lines.append(f"  {tag}: {'PASS' if nv == 0 else 'FAIL'} ({nv} violations)")
    lines.append("    " + vc.report(res).replace("\n", "\n    "))

# ---- 3. payload check / regression ----
lines.append("")
lines.append("3. PAYLOAD CHECK (ID + cycle + sequence + CRC-32 in every P2 packet)")
for tag in ("swarm_2copies_10s", "swarm_2copies_3s", "swarm_1copy_3s"):
    t2 = open(os.path.join(done[tag], "p2_ground_truth_report.txt"), encoding="utf-8", errors="ignore").read()
    pc = re.search(r"P2 Payload Check.*?:\s*(\d+) / (\d+) / (\d+)", t2)
    prr = float(re.search(r"Successfully Received \(Delivered\)\s*:\s*\d+\s*\(([\d.]+)%\)", t2).group(1))
    ok = pc and int(pc.group(2)) == 0 and int(pc.group(3)) == 0
    all_ok &= bool(ok)
    lines.append(f"  {tag}: valid {pc.group(1)}, bad {pc.group(2)}, stale cycle {pc.group(3)}; P2 PRR {prr:.1f}%"
                 + f" -> {'PASS' if ok else 'FAIL'}")

# ---- 4. timeline ----
m = vc.Model(done["swarm_2copies_3s"], 4.0)
tl = m.timeline(0, 100)
with open(os.path.join(PROJECT_DIR, "verify_timeline_example.txt"), "w", encoding="utf-8") as f:
    f.write(tl)
lines.append("")
lines.append("4. TIMELINE for a hand check: verify_timeline_example.txt (UAV 0, cycle 100)")
lines.append("")
lines.append("OVERALL: " + ("ALL PASS" if all_ok else "SOME CHECKS FAILED"))
summary = "\n".join(lines) + "\n"
print("\n" + summary)
print(tl)
with open(os.path.join(PROJECT_DIR, "verify_summary.txt"), "w", encoding="utf-8") as f:
    f.write(summary)
shutil.rmtree(run_root, ignore_errors=True)

if a.no_push:
    sys.exit(0 if all_ok else 1)
files = ["verify_summary.txt", "verify_timeline_example.txt", "run_verify.py", "verify_crosscheck.py", "scratch/lr-wpan-swarm.cc"]
try:
    subprocess.run(["git", "pull", "--rebase", "--autostash", "origin", "main"], cwd=PROJECT_DIR, check=True)
    subprocess.run(["git", "add", "-f"] + files, cwd=PROJECT_DIR, check=True)
    subprocess.run(["git", "commit", "-m", f"verify: P2 verification suite ({'all pass' if all_ok else 'FAILURES'})"],
                   cwd=PROJECT_DIR, check=True)
    subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=PROJECT_DIR, check=True)
    print("✓ Results pushed to GitHub")
except subprocess.CalledProcessError as e:
    print(f"⚠ Git upload failed ({e}); results are still saved locally in {PROJECT_DIR}")
