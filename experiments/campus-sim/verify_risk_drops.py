#!/usr/bin/env python3
"""Independent recheck of every risk drop in a campus batch (read-only; separate from the P3 gate of analyze_campus.py).

    python3 -I -B experiments/campus-sim/verify_risk_drops.py <batch dir>

For every run: the hash seed is taken from the run's argv (--riskDropSeed) and must equal the seed in the run id and
risk_summary.csv (seed, risk_drop_seed). Every row of risk_drops.csv must be at a HIGH_RISK node of risk_nodes.csv, not
the node's own packet, have U < 0.5, and U must equal the reference hash risk_ref.risk_uniform(seed, node, src, seq)
within 1e-12. k = 0 runs must have no drops. Exit status 1 on any violation.
"""
import csv
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("risk_ref", ROOT / "experiments/wifi6-risk/risk_ref.py")
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)


def main():
    b = Path(sys.argv[1])
    runs = drops = 0
    bad = []
    for d in sorted((b / "runs").iterdir()):
        argv = json.loads((d / "provenance.json").read_text())["argv"]
        seed = [int(a.split("=", 1)[1]) for a in argv if a.startswith("--riskDropSeed=")]
        s = next(csv.DictReader(open(d / "risk_summary.csv")))
        run_seed = int(d.name.split("seed")[1])
        if seed != [run_seed] or int(s["seed"]) != run_seed or int(s["risk_drop_seed"]) != run_seed:
            bad.append(f"{d.name}: seed mismatch argv {seed} summary {s['seed']}/{s['risk_drop_seed']}")
            continue
        high = {int(x["node_id"]) for x in csv.DictReader(open(d / "risk_nodes.csv")) if x["risk_state"] == "HIGH_RISK"}
        dr = list(csv.DictReader(open(d / "risk_drops.csv")))
        n = sum(1 for x in dr if int(x["node_id"]) not in high or x["node_id"] == x["src"] or float(x["u"]) >= 0.5
                or abs(float(x["u"]) - R.risk_uniform(run_seed, int(x["node_id"]), int(x["src"]), int(x["seq"]))) > 1e-12)
        if n:
            bad.append(f"{d.name}: {n} invalid drops")
        if "_k0_" in d.name and dr:
            bad.append(f"{d.name}: {len(dr)} drops with k = 0")
        runs += 1
        drops += len(dr)
    print(f"{b.name}: {runs} runs, {drops} risk drops rechecked with each run's own seed; violations: {len(bad)}")
    for x in bad[:20]:
        print("  " + x)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
