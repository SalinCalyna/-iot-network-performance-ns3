#!/usr/bin/env python3
"""
Summarizes the IoT Network Performance V2 results produced by
run_experiments.sh into one mean+stddev table per (protocol, network size)
scenario.

Usage:
    python3 experiments/analyze_results.py [results_dir]
"""

import csv
import glob
import os
import statistics
import sys


def load_rows(results_dir):
    rows = []
    for path in sorted(glob.glob(os.path.join(results_dir, "*.csv"))):
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                rows.append(row)
    return rows


def summarize(rows):
    groups = {}
    for row in rows:
        key = (row["RoutingProtocol"], int(row["NumberOfNodes"]))
        groups.setdefault(key, []).append(row)

    summary = []
    for (protocol, n), trials in sorted(groups.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        pdrs = [float(t["PDR"]) for t in trials]
        thr = [float(t["ThroughputKbps"]) for t in trials]
        delay = [float(t["AverageDelaySec"]) for t in trials]
        loss = [int(t["PacketLoss"]) for t in trials]
        summary.append(
            {
                "protocol": protocol,
                "nSensors": n,
                "trials": len(trials),
                "pdrMean": statistics.mean(pdrs),
                "pdrStdev": statistics.stdev(pdrs) if len(pdrs) > 1 else 0.0,
                "throughputMean": statistics.mean(thr),
                "delayMean": statistics.mean(delay),
                "lossMean": statistics.mean(loss),
            }
        )
    return summary


def main():
    results_dir = sys.argv[1] if len(sys.argv) > 1 else "results"
    rows = load_rows(results_dir)
    if not rows:
        print(f"No CSV rows found under {results_dir}/")
        return

    summary = summarize(rows)

    header = f"{'Protocol':<8} {'N':>4} {'Trials':>6} {'PDR% (mean±sd)':>18} {'Throughput(kbps)':>18} {'Delay(s)':>10} {'Loss(pkts)':>11}"
    print(header)
    print("-" * len(header))
    for s in summary:
        print(
            f"{s['protocol']:<8} {s['nSensors']:>4} {s['trials']:>6} "
            f"{s['pdrMean']:>8.2f}±{s['pdrStdev']:<7.2f} "
            f"{s['throughputMean']:>18.2f} {s['delayMean']:>10.4f} {s['lossMean']:>11.1f}"
        )


if __name__ == "__main__":
    main()
