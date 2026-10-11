"""Runs the three scripts and writes results.txt beside them.  Usage: python -I run_all.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # needed under python -I
import task1_linear, task2_models, task345_predict

out = []
task1_linear.main(out)
out.append("")
task2_models.main(out)
out.append("")
task345_predict.main(out)
txt = "\n".join(out) + "\n"
open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "results.txt"), "w", newline="\n").write(txt)
print(txt)
