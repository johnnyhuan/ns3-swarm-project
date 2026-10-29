#!/usr/bin/env python3
# Alias to sweep_p2_power.py
import os
import sys

script_dir = os.path.dirname(os.path.abspath(__file__))
p2_script = os.path.join(script_dir, "sweep_p2_power.py")
os.execv(sys.executable, [sys.executable, p2_script] + sys.argv[1:])
