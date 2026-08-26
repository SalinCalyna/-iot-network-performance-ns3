#!/usr/bin/env python3
"""
Parameterized experiment runner for the V3 expanded-experiment-matrix study
(scratch/iot-network-v3-ext.cc).

Per the 2026-08 advisor direction, V3 keeps V2's topology-generation method
unchanged and instead widens the experiment matrix along:

    nodes x traffic x mobility x routing x seed

writing one CSV row per run to results/v3-ext/. This script never touches
results/*.csv (V2's own output), results/v28-sigmoid-pilot/, or results/v3/
(scratch/iot-network-v3.cc's own output, a separate Barabasi-Albert /
risk-aware-routing research track with an incompatible schema) -- those are
untouched reference tracks. "v3-ext" (not "v3") is deliberate: "results/v3"
was already claimed by iot-network-v3.cc before this script existed -- see
docs/v3-experiment-framework.md's "Three tracks" table.

"sigmoid" is deliberately NOT in ROUTING_PROTOCOLS: it is not implemented in
iot-network-v3-ext.cc (the binary refuses to run and exits 1 rather than
fabricate a result -- see the source file's header comment and
docs/v3-experiment-framework.md). Passing --routing sigmoid on the command
line will therefore make every combination fail fast, which is intentional:
it makes the gap visible instead of silently skipping it.

Seeds -- two distinct, deliberately separated policies (see
docs/v3-experiment-framework.md's "Seeds" subsection for the full
rationale):

    - Validation / Smoke Test: --seeds 1 (what has actually been run so
      far -- the framework smoke test and the six-node-size sweep).
    - Official V3 experiment: --seeds 20-30 (seed values 20 through 30
      inclusive, 11 seeds -- advisor-specified 2026-08-26; NOT the same as
      "20 or 30 total seeds starting at seed 1"). Not yet run.

Usage examples:

    # Official V3 experiment matrix (WARNING: 1,782 runs at full size --
    # see docs/v3-experiment-framework.md for the wall-clock estimate
    # before running this; NOT run by this pass):
    python3 experiments/run_v3_experiments.py \\
        --nodes 10 20 30 50 75 100 \\
        --traffic low medium high \\
        --mobility static low medium \\
        --routing aodv olsr static \\
        --seeds 20-30 \\
        --duration 300

    # Validation / Smoke Test (what this project has actually run so far --
    # NOT the official multi-seed experiment):
    python3 experiments/run_v3_experiments.py \\
        --nodes 10 --traffic medium --mobility static low medium \\
        --routing aodv olsr static --seeds 1 --duration 60 --app-start 10
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BIN = PROJECT_ROOT / "build" / "scratch" / "ns3-dev-iot-network-v3-ext-default"
RESULTS_DIR = PROJECT_ROOT / "results" / "v3-ext"
LOG_DIR = RESULTS_DIR / "logs"

ALL_NODES = [10, 20, 30, 50, 75, 100]
ALL_TRAFFIC = ["low", "medium", "high"]
ALL_MOBILITY = ["static", "low", "medium"]
ALL_ROUTING = ["aodv", "olsr", "static"]  # "sigmoid" intentionally excluded -- see module docstring


def parse_seeds(spec):
    """'1-25' -> [1..25]; '1,3,5' -> [1,3,5]; also accepts a mix via commas."""
    seeds = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-")
            seeds.extend(range(int(lo), int(hi) + 1))
        elif part:
            seeds.append(int(part))
    return seeds


def build_arg_parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--nodes", type=int, nargs="+", default=[10], choices=ALL_NODES)
    p.add_argument("--traffic", nargs="+", default=["medium"], choices=ALL_TRAFFIC)
    p.add_argument("--mobility", nargs="+", default=["static"], choices=ALL_MOBILITY)
    p.add_argument("--routing", nargs="+", default=["aodv", "olsr", "static"])
    p.add_argument("--seeds", default="1", help="e.g. '1' (validation/smoke-test default) "
                   "or '20-30' (Official V3 experiment range, seed values 20-30 inclusive) "
                   "or '1,2,3'")
    p.add_argument("--duration", type=float, default=300.0, help="simTime in seconds (300-600 recommended)")
    p.add_argument("--app-start", type=float, default=30.0)
    p.add_argument("--area-size", type=float, default=250.0)
    p.add_argument("--tx-power-dbm", type=float, default=20.0)
    p.add_argument("--tx-range", type=float, default=90.0)
    p.add_argument("--packet-size", type=int, default=512)
    p.add_argument("--dry-run", action="store_true", help="print the planned run matrix and exit")
    return p


def main():
    args = build_arg_parser().parse_args()
    seeds = parse_seeds(args.seeds)

    unknown_routing = set(args.routing) - set(ALL_ROUTING) - {"sigmoid"}
    if unknown_routing:
        sys.exit(f"Unknown --routing value(s): {sorted(unknown_routing)}")

    combos = [
        (n, traffic, mobility, routing, seed)
        for n in args.nodes
        for traffic in args.traffic
        for mobility in args.mobility
        for routing in args.routing
        for seed in seeds
    ]

    print(f"Planned runs: {len(combos)}  (nodes={args.nodes} x traffic={args.traffic} x "
          f"mobility={args.mobility} x routing={args.routing} x seeds={seeds})")
    est_minutes = len(combos) * args.duration / 60.0 / 60.0  # rough: real time << sim time, this is an upper bound
    print(f"Duration per run: {args.duration}s (sim time). This is NOT wall-clock time -- "
          f"ns-3 typically runs much faster than real time for this scenario, but the full "
          f"matrix is still a lot of runs; time a handful yourself before committing to the "
          f"full set.")

    if args.dry_run:
        for combo in combos:
            print("  ", combo)
        return

    if not BIN.exists():
        sys.exit(f"Binary not found at {BIN} -- run: ./ns3 build iot-network-v3-ext")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    skipped_sigmoid = 0
    failed = []
    t0 = time.time()
    for i, (n, traffic, mobility, routing, seed) in enumerate(combos, 1):
        tag = f"{routing}_{n}_{traffic}_{mobility}_seed{seed}"
        print(f"[{i}/{len(combos)}] {tag}", flush=True)

        if routing == "sigmoid":
            print("  -> skipped: sigmoid is not implemented in iot-network-v3-ext "
                  "(see docs/v3-experiment-framework.md)")
            skipped_sigmoid += 1
            continue

        cmd = [
            str(BIN),
            f"--protocol={routing}",
            f"--nSensors={n}",
            f"--trafficLevel={traffic}",
            f"--mobilityMode={mobility}",
            f"--seed={seed}",
            f"--simTime={args.duration}",
            f"--appStart={args.app_start}",
            f"--areaSize={args.area_size}",
            f"--txPowerDbm={args.tx_power_dbm}",
            f"--txRange={args.tx_range}",
            f"--packetSize={args.packet_size}",
            f"--outDir={RESULTS_DIR}",
        ]
        log_path = LOG_DIR / f"{tag}.log"
        with open(log_path, "w") as log_file:
            result = subprocess.run(cmd, stdout=log_file, stderr=subprocess.STDOUT)
        if result.returncode != 0:
            print(f"  -> FAILED (exit {result.returncode}), see {log_path}")
            failed.append(tag)

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.1f}s wall-clock. "
          f"{len(combos) - skipped_sigmoid - len(failed)} succeeded, "
          f"{skipped_sigmoid} skipped (sigmoid not implemented), {len(failed)} failed.")
    if failed:
        print("Failed runs:")
        for tag in failed:
            print(f"  {tag}  (log: {LOG_DIR / (tag + '.log')})")
        sys.exit(1)


if __name__ == "__main__":
    main()
