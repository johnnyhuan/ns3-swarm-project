#!/usr/bin/env python3
"""
Density sweep of SSA final + P2 final: 50..500 UAVs (step 50) in the same 200 x 200 x 80 m box,
5 s each, seed 1. Builds ns-3 once, then runs the swarm sizes in parallel (largest first) through
run_final.py --exps ssa_only. Chart: plot_density_final.py --simtime 5.

Usage:
    python3 run_density_ssa.py                     # pushes results
    python3 run_density_ssa.py --parallel 5 --no-push
"""
import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

ap = argparse.ArgumentParser()
ap.add_argument("--nodes", type=int, nargs="+", default=list(range(50, 501, 50)))
ap.add_argument("--simtime", type=float, default=5.0)
ap.add_argument("--parallel", type=int, default=6)
ap.add_argument("--no-push", action="store_true")
a = ap.parse_args()
HERE = os.path.dirname(os.path.abspath(__file__))
NS3_DIR = os.path.expanduser(os.environ.get("NS3_DIR", "~/ns-3-dev"))

# copy sources and build once (the parallel runs then use --skip-build)
import shutil
for rel in ["scratch/lr-wpan-swarm.cc", "src/lr-wpan/model/lr-wpan-phy.cc", "src/lr-wpan/model/lr-wpan-phy.h",
            "src/lr-wpan/model/lr-wpan-csmaca.cc", "src/lr-wpan/model/lr-wpan-csmaca.h",
            "src/lr-wpan/model/lr-wpan-mac.cc", "src/lr-wpan/model/lr-wpan-mac.h"]:
    if os.path.abspath(os.path.join(HERE, rel)) != os.path.abspath(os.path.join(NS3_DIR, rel)):
        shutil.copy(os.path.join(HERE, rel), os.path.join(NS3_DIR, rel))
b = subprocess.run(["./ns3", "build", "scratch/lr-wpan-swarm"], cwd=NS3_DIR, stdout=subprocess.PIPE,
                   stderr=subprocess.STDOUT, text=True)
if b.returncode != 0:
    print(b.stdout[-3000:])
    sys.exit("build failed")


def one(n):
    p = subprocess.run([sys.executable, "run_final.py", "--exps", "ssa_only", "--nodes", str(n),
                        "--simtime", str(a.simtime), "--no-push", "--jobs", "1", "--skip-build"],
                       cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return n, p.returncode, p.stdout.strip().splitlines()[-2:]


with ThreadPoolExecutor(max_workers=a.parallel) as ex:
    for n, rc, tail in ex.map(one, sorted(a.nodes, reverse=True)):
        print(f"{n:4d} UAVs: {'ok' if rc == 0 else 'FAILED'}  {' | '.join(tail)}", flush=True)

# plot (the ns-3 venv python may lack matplotlib: fall back to the system python)
for py in (sys.executable, "/usr/bin/python3"):
    if subprocess.run([py, "plot_density_final.py", "--simtime", f"{a.simtime:g}"], cwd=HERE).returncode == 0:
        break
if not a.no_push:
    t = f"_t{a.simtime:g}" if a.simtime != 10 else ""
    files = [f"results/final_ssa_only_v2{'' if n == 100 else f'_n{n}'}{t}.csv" for n in a.nodes] + \
            [f"results/final_runs_top7_gap200_v2{'' if n == 100 else f'_n{n}'}{t}.csv" for n in a.nodes] + \
            [f"figures/final/density_ssa_v2{t}.png", "run_density_ssa.py", "run_final.py", "plot_density_final.py"]
    files = [f for f in files if os.path.exists(os.path.join(HERE, f))]
    try:
        subprocess.run(["git", "pull", "--rebase", "--autostash", "origin", "main"], cwd=HERE, check=True)
        subprocess.run(["git", "add", "-f"] + files, cwd=HERE, check=True)
        subprocess.run(["git", "commit", "-m", f"data: SSA final density sweep {min(a.nodes)}-{max(a.nodes)} UAVs ({a.simtime:g} s, seed 1)"],
                       cwd=HERE, check=True)
        subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=HERE, check=True)
        print("✓ Results pushed to GitHub")
    except subprocess.CalledProcessError as e:
        print(f"⚠ Git upload failed ({e})")
