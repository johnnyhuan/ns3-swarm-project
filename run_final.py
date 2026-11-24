#!/usr/bin/env python3
"""
Final comparison runs (nRF54L15 DK conditions: TX <= +7 dBm, BLE 2M sensitivity -94 dBm).
100 UAVs, 200 x 200 x 80 m, 10 m/s, 10 s, seed 1 by default (--seeds 1 2 3 4 5 for more; tuning used seed 101).

Experiments (each = ordered list of steps; every step = full flag set):
  buildup_csma  P1 CSMA from default to final (+ idealized capture as a dashed reference)
  buildup_ssa   P1 SSA from the first version to final
  buildup_p2    P2 from the old design to final (P1 = SSA final)
P1 build-ups run with the final P2, so the cycle is identical everywhere.

Every run is cached in results/final_runs.csv (key = sorted flags + seed), so steps shared by
several experiments run once and an interrupted run resumes. Per-experiment tables go to
results/final_<experiment>.csv; charts come from plot_final.py.

Usage:
    python3 run_final.py                              # all build-ups, pushes results
    python3 run_final.py --exps buildup_csma --no-push
"""
import argparse
import csv
import os
import re
import shutil
import statistics
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

COMMON = ("--simTime=10 --numNodes={nodes} --nodeSpeed=10.0 --spaceSize=200 --spaceZ=80 "
          "--p1Duration=10 --preambleLockDb=6 --autoPush=false --rxSensitivityDbm=-94 --topK=7")
TOPK = 7   # each UAV must receive its 7 nearest neighbours within 50 m

# ---------------- final settings ----------------
P2_FINAL = dict(dataSlotUs=400, slotGuardBandUs=30, numSlots=24, numChannels=10, p2ExtraRx=3, p2TxPower=5,
                p1AvoidDist=50, p2Copies=2, p2SmartPick="true")
SSA_FINAL = dict(enableP1Ssa="true", p1SlotUs=150, p1TxPower=7, p1PoolFrac=0.25, p1SenseDecay=0.6,
                 p1ReselMin=20, p1ReselMax=60, p1ReselInitMin=-1, p1ReselInitMax=-1)
CSMA_FINAL = dict(enableP1Ssa="false", p1TxPower=5, p1CcaThresholdDbm=-94, p1MaxBackoffs=1, p1MinBE=0,
                  p1RetryMinMs=0.1, p1RetryMaxMs=0.5, p1Copies=1)

CSMA_DEFAULT = dict(CSMA_FINAL, p1TxPower=4, p1CcaThresholdDbm=-97, p1MaxBackoffs=0)
SSA_FIRST = dict(SSA_FINAL, p1SlotUs=300, p1TxPower=4, p1SenseDecay=1.0, p1ReselMin=5, p1ReselMax=15,
                 p1ReselInitMin=-1, p1ReselInitMax=-1)
P2_OLD = dict(P2_FINAL, dataSlotUs=750, slotGuardBandUs=50, numSlots=13, numChannels=6, p2ExtraRx=0,
              p2TxPower=4, p2Copies=1, p2SmartPick="false")


def chain(start, changes):
    """Cumulative steps: [(label, params)], each change applied on top of the previous step."""
    out, cur = [], dict(start)
    for label, delta in changes:
        cur = dict(cur, **delta)
        out.append((label, dict(cur)))
    return out


EXPERIMENTS = {
    "buildup_csma": dict(
        steps=[(lbl, dict(p, **P2_FINAL)) for lbl, p in chain(CSMA_DEFAULT, [
            ("CSMA default\n(+4 dBm,\nCCA -97 dBm)", {}),
            ("CCA threshold\n-97 -> -94 dBm", dict(p1CcaThresholdDbm=-94)),
            ("+1 extra CCA", dict(p1MaxBackoffs=1)),
            ("TX power\n+4 -> +5 dBm\n(= CSMA final)", dict(p1TxPower=5)),
        ])],
        reference=("CSMA final + idealized capture", dict(CSMA_FINAL, p1Capture="true", **P2_FINAL))),
    "buildup_ssa": dict(
        steps=[(lbl, dict(p, **P2_FINAL)) for lbl, p in chain(SSA_FIRST, [
            ("first SSA\n(300 us, +4 dBm,\nno decay, 5-15)", {}),
            ("slot\n300 -> 150 us", dict(p1SlotUs=150)),
            ("RSSI memory\ndecay 0.6", dict(p1SenseDecay=0.6)),
            ("TX power\n+4 -> +7 dBm", dict(p1TxPower=7)),
            ("reselection\n5-15 -> 20-60\n(= SSA final)", dict(p1ReselMin=20, p1ReselMax=60)),
        ])]),
    "buildup_p2": dict(
        steps=[(lbl, dict(p, **SSA_FINAL)) for lbl, p in chain(P2_OLD, [
            ("old P2\n(750 us x 13, 6 ch,\nno extra RX, 1 copy, +4)", {}),
            ("slots\n400 us x 24", dict(dataSlotUs=400, slotGuardBandUs=30, numSlots=24)),
            ("listen to\n3 extra", dict(p2ExtraRx=3)),
            ("6 -> 10\nchannels", dict(numChannels=10)),
            ("2 copies\nper packet", dict(p2Copies=2)),
            ("smart copy\nchoice", dict(p2SmartPick="true")),
            ("TX power\n+4 -> +5 dBm\n(= P2 final)", dict(p2TxPower=5)),
        ])]),
    # SSA reselection counter sweep, with and without the short first-pick counter (P2 = final)
    "sweep_resel": dict(
        steps=[(f"{lo}-{hi} | first pick {'2-5' if init else 'off'}",
                dict(SSA_FINAL, **P2_FINAL, p1ReselMin=lo, p1ReselMax=hi,
                     p1ReselInitMin=2 if init else -1, p1ReselInitMax=5 if init else -1))
               for init in (False, True)
               for lo, hi in ((3, 9), (5, 15), (10, 30), (15, 45), (20, 60), (30, 90), (50, 150))]),
}

METRICS = ["P1", "P2", "AoI1_mean", "AoI1_p99", "AoI1_max", "AoI2_mean", "AoI2_p99", "AoI2_max",
           "AoI1_over100", "AoI1_over500", "AoI1_maxclose", "AoI2_over100", "AoI2_over500", "AoI2_maxclose"]
BUILDUPS = ["buildup_csma", "buildup_ssa", "buildup_p2"]
METRICS.append("DENS")   # mean number of UAVs within 50 m of a UAV (measured)

# the three P1 methods with the final P2, for one chart per swarm size
EXPERIMENTS["compare"] = dict(steps=[
    ("CSMA (final)", dict(CSMA_FINAL, **P2_FINAL)),
    ("CSMA + capture (idealized)", dict(CSMA_FINAL, p1Capture="true", **P2_FINAL)),
    ("SSA (final)", dict(SSA_FINAL, **P2_FINAL)),
])

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--exps", nargs="+", default=BUILDUPS, choices=list(EXPERIMENTS))
    ap.add_argument("--seeds", type=int, nargs="+", default=[1])
    ap.add_argument("--nodes", type=int, default=100, help="swarm size (same 200 x 200 x 80 m box)")
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

    def flags(params):
        return " ".join(f"--{k}={v}" for k, v in sorted(params.items()))

    COMMON = COMMON.format(nodes=a.nodes)
    SUFFIX = "" if a.nodes == 100 else f"_n{a.nodes}"
    CSV_PATH = os.path.join(PROJECT_DIR, "results", f"final_runs_top{TOPK}{SUFFIX}.csv")   # cache key = flags + seed
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    cache = {}
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, newline="") as f:
            for r in csv.DictReader(f):
                cache[(r["flags"], int(r["seed"]))] = {m: float(r.get(m) or "nan") for m in METRICS}
        # older cache files lack newer metric columns: rewrite with the current header
        with open(CSV_PATH, newline="") as f:
            header = next(csv.reader(f))
        if header != ["flags", "seed"] + METRICS:
            with open(CSV_PATH, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["flags", "seed"] + METRICS)
                for (fl, sd), v in cache.items():
                    w.writerow([fl, sd] + [v[m] for m in METRICS])

    b = subprocess.run(["./ns3", "build", "scratch/lr-wpan-swarm"], cwd=NS3_DIR,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if b.returncode != 0:
        print(b.stdout[-3000:])
        sys.exit("build failed")
    run_root = os.path.join(NS3_DIR, f"final_runs_n{a.nodes}_{os.getpid()}")   # private per invocation
    os.makedirs(run_root, exist_ok=True)

    def parse(t1, t2):
        def prr(t):
            m = re.search(r"Successfully Received \(Delivered\)\s*:\s*\d+\s*\(([\d.]+)%\)", t)
            return float(m.group(1)) if m else float("nan")

        def aoi(t, k):
            m = re.search(rf"AoI {k} at cycle end \(mean / p99 / max\)\s*:\s*([\d.]+) / ([\d.]+) / ([\d.]+)", t)
            return [float(x) for x in m.groups()] if m else [float("nan")] * 3
        def safety(t, k):
            m = re.search(rf"AoI {k} safety \(>100 ms % / >500 ms % / max <=20 m\)\s*:\s*([\d.]+) / ([\d.]+) / ([\d.]+)", t)
            return [float(x) for x in m.groups()] if m else [float("nan")] * 3
        a1, a2 = aoi(t2, "P1"), aoi(t2, "P2")
        s1, s2 = safety(t2, "P1"), safety(t2, "P2")
        md = re.search(r"Mean 50m Neighbors per UAV \(Density\)\s*:\s*([\d.]+)", t1)
        return dict(DENS=float(md.group(1)) if md else float("nan"),
                    P1=prr(t1), P2=prr(t2), AoI1_mean=a1[0], AoI1_p99=a1[1], AoI1_max=a1[2],
                    AoI2_mean=a2[0], AoI2_p99=a2[1], AoI2_max=a2[2],
                    AoI1_over100=s1[0], AoI1_over500=s1[1], AoI1_maxclose=s1[2],
                    AoI2_over100=s2[0], AoI2_over500=s2[1], AoI2_maxclose=s2[2])

    def run_one(job):
        fl, seed = job
        d = os.path.join(run_root, f"r{abs(hash(job)) % 10**10}")
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
        p = subprocess.run(["./ns3", "run", "--no-build", "--cwd", d,
                            f"scratch/lr-wpan-swarm {COMMON} {fl} --rngRun={seed}"],
                           cwd=NS3_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            res = parse(open(os.path.join(d, "p1_ground_truth_report.txt"), errors="ignore").read(),
                        open(os.path.join(d, "p2_ground_truth_report.txt"), errors="ignore").read())
        except OSError:
            res = None
        shutil.rmtree(d, ignore_errors=True)
        return job, res, p.stdout[-1500:]

    # collect all jobs
    plan = {}
    for e in a.exps:
        ex = EXPERIMENTS[e]
        rows = list(ex["steps"]) + ([ex["reference"]] if "reference" in ex else [])
        plan[e] = [(lbl, flags(p)) for lbl, p in rows]
    jobs = sorted({(fl, s) for e in plan for _, fl in plan[e] for s in a.seeds} - set(cache))
    print(f"▶ {len(jobs)} runs to do ({len(cache)} cached), {a.jobs} in parallel", flush=True)
    new = not os.path.exists(CSV_PATH)
    with open(CSV_PATH, "a", newline="") as f, ThreadPoolExecutor(max_workers=a.jobs) as ex:
        w = csv.writer(f)
        if new:
            w.writerow(["flags", "seed"] + METRICS)
        done_n = 0
        for (fl, seed), res, out in ex.map(run_one, jobs):
            done_n += 1
            if res is None:
                print(f"   ✗ failed seed {seed}: {fl}\n{out}", flush=True)
                continue
            cache[(fl, seed)] = res
            w.writerow([fl, seed] + [res[m] for m in METRICS])
            f.flush()
            print(f"   {done_n}/{len(jobs)} seed {seed}: P1 {res['P1']:.1f}%  P2 {res['P2']:.1f}%", flush=True)

    saved = []
    for e, rows in plan.items():
        path = os.path.join(PROJECT_DIR, "results", f"final_{e}{SUFFIX}.csv")
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["step", "label", "kind", "seeds"] + [f"{m}_{s}" for m in METRICS for s in ("mean", "std")] + ["flags"])
            nsteps = len(EXPERIMENTS[e]["steps"])
            for i, (lbl, fl) in enumerate(rows):
                vals = [cache[(fl, s)] for s in a.seeds if (fl, s) in cache]
                stats = []
                for m in METRICS:
                    xs = [v[m] for v in vals]
                    stats += [statistics.mean(xs), statistics.stdev(xs) if len(xs) > 1 else 0.0]
                w.writerow([i, lbl.replace("\n", " | "), "step" if i < nsteps else "reference", len(vals)]
                           + [f"{x:.3f}" for x in stats] + [fl])
        saved.append(os.path.relpath(path, PROJECT_DIR))
        print(f"✓ {path}")
    shutil.rmtree(run_root, ignore_errors=True)

    if a.no_push:
        sys.exit(0)
    try:
        subprocess.run(["git", "pull", "--rebase", "--autostash", "origin", "main"], cwd=PROJECT_DIR, check=True)
        subprocess.run(["git", "add", "-f", os.path.relpath(CSV_PATH, PROJECT_DIR), "run_final.py"] + saved, cwd=PROJECT_DIR, check=True)
        subprocess.run(["git", "commit", "-m", f"data: final {' '.join(a.exps)} (seeds {a.seeds})"], cwd=PROJECT_DIR, check=True)
        subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=PROJECT_DIR, check=True)
        print("✓ Results pushed to GitHub")
    except subprocess.CalledProcessError as e:
        print(f"⚠ Git upload failed ({e}); results are still saved locally in {PROJECT_DIR}")
