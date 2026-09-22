#!/usr/bin/env python3
"""Derived statistics layer for the public dashboard (site/).

READ-ONLY over the official V3 raw results:

    results/v3-ext/*.csv   (only Seed 20-30, Duration 300 -> 1,782 runs, 162 cells)

and writes ONE new derived file:

    site/data/v3ext-stats.json

It never modifies results/*.csv, site/data/research.db or
site/data/final_research.json, and it never runs a simulation.

Statistics (no other method is used):
  * per condition (cell) and per chart point: mean, sample SD (ddof=1),
    standard error SD/sqrt(n), two-sided Student-t 95% CI half-width
    t(0.975, df=n-1) * SD / sqrt(n).  n=11 -> df=10, t=2.228.
  * the t table is identical to dashboard/app.py::_T_TABLE_95 (3 dp).
  * the 11 seeds (20-30) are treated as statistical replications.

Undefined observations (excluded at THIS aggregation layer only):
  a run with PacketsReceived == 0 has no defined
    - AverageDelaySec, AverageJitterSec
    - AverageHopCount, unless HopCountMethod == "exact" (Static routing)
  The simulator stores a placeholder 0.0 for them; that 0 is not a measurement.
  PDR, throughput and packet loss are genuinely 0 for such a run and are kept.
  Each metric uses its own valid n (df = n_valid - 1, its own t).  Nothing is
  imputed and no undefined value is ever converted to zero.

Chart-point ("marginal") statistics average, for each seed, that seed's runs
across the cells the point spans (one number per seed) and take the CI across
the per-seed numbers -- never from cell means or pooled runs.  A seed with an
undefined run for a metric is excluded whole for that metric, so every
remaining per-seed value averages the same cells.

Usage:  python3 experiments/build_v3_site_stats.py          (writes the JSON)
        python3 experiments/build_v3_site_stats.py --check  (verify the committed JSON is current)
"""
import csv
import glob
import json
import math
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_GLOB = os.path.join(ROOT, "results", "v3-ext", "*.csv")
OUT_PATH = os.path.join(ROOT, "site", "data", "v3ext-stats.json")

SEEDS = list(range(20, 31))
DURATION = 300.0
PROTOCOLS = ["aodv", "olsr", "static"]
NODES = [10, 20, 30, 50, 75, 100]
TRAFFIC = ["low", "medium", "high"]
MOBILITY = ["static", "low", "medium"]

# Identical to dashboard/app.py::_T_TABLE_95 (two-sided 95%, df 1-30, 3 dp).
T_TABLE_95 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
    6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
    11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
    16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
    21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
    26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
}

# key -> (csv column, scale to display unit, unit label)
METRICS = {
    "pdr": ("PDR", 1.0, "%"),
    "throughput": ("ThroughputKbps", 1.0, "kbps"),
    "delay": ("AverageDelaySec", 1000.0, "ms"),
    "jitter": ("AverageJitterSec", 1000.0, "ms"),
    "loss": ("PacketLoss", 1.0, "packets"),
    "routing_overhead": ("RoutingOverheadPackets", 1.0, "packets"),
    "hop": ("AverageHopCount", 1.0, "hops"),
    "path_changes": ("PathChanges", 1.0, "changes"),
    "link_util_avg": ("AverageLinkUtilization", 1.0, "fraction"),
    "link_util_max": ("MaximumLinkUtilization", 1.0, "fraction"),
}
UNDEFINED_WHEN_NO_RX = ("delay", "jitter", "hop")


def t_critical(n):
    if n < 2:
        return None
    df = n - 1
    if df in T_TABLE_95:
        return T_TABLE_95[df]
    if df > 30:
        return 1.96
    return T_TABLE_95[min(T_TABLE_95, key=lambda k: abs(k - df))]


def is_undefined(row, key):
    """True when metric `key` of this run is undefined (not a measurement)."""
    if key not in UNDEFINED_WHEN_NO_RX or row["_rx"] != 0:
        return False
    if key == "hop" and row["HopCountMethod"] == "exact":
        return False
    return True


def describe(values):
    """(n, mean, sd, se, ci95, df, t) over the given valid observations."""
    n = len(values)
    if n == 0:
        return dict(n=0, mean=None, sd=None, se=None, ci95=None, df=None, t=None)
    mean = statistics.fmean(values)
    sd = statistics.stdev(values) if n > 1 else 0.0
    se = sd / math.sqrt(n)
    t = t_critical(n)
    ci = t * se if (t is not None and n > 1) else None
    return dict(n=n, mean=mean, sd=sd, se=se, ci95=ci, df=(n - 1 if n > 1 else None), t=t)


def load_official():
    files = sorted(glob.glob(CSV_GLOB))
    if not files:
        sys.exit("ERROR: no CSV files found at %s" % CSV_GLOB)
    rows, seen = [], set()
    for path in files:
        with open(path, newline="") as fh:
            for r in csv.DictReader(fh):
                seed, dur = int(r["Seed"]), float(r["Duration"])
                if seed not in SEEDS or dur != DURATION:
                    continue  # legacy / smoke rows stay on disk, outside the official baseline
                r["_seed"], r["_nodes"] = seed, int(r["NumberOfNodes"])
                r["_rx"] = int(r["PacketsReceived"])
                key = (r["RoutingProtocol"], r["_nodes"], r["TrafficLevel"], r["MobilityMode"], seed)
                if key in seen:
                    sys.exit("ERROR: duplicate official run %r" % (key,))
                seen.add(key)
                for mk, (col, _scale, _u) in METRICS.items():
                    r["_" + mk] = float(r[col])
                rows.append(r)
    expected = len(PROTOCOLS) * len(NODES) * len(TRAFFIC) * len(MOBILITY) * len(SEEDS)
    if len(rows) != expected:
        sys.exit("ERROR: expected %d official runs, found %d - refusing to write statistics" % (expected, len(rows)))
    return files, rows


def metric_block(valid_values, n_total, scale):
    d = describe([v * scale for v in valid_values])
    excluded = n_total - d["n"]
    return {
        "mean": d["mean"], "sd": d["sd"], "se": d["se"], "ci95": d["ci95"],
        "n": d["n"], "nTotal": n_total, "excluded": excluded, "df": d["df"], "t": d["t"],
    }


def build():
    files, rows = load_official()

    # ---- condition (cell) level: 162 cells x 11 seeds ------------------------------------
    by_cell = {}
    for r in rows:
        by_cell.setdefault((r["RoutingProtocol"], r["_nodes"], r["TrafficLevel"], r["MobilityMode"]), []).append(r)
    cells = []
    for proto in PROTOCOLS:
        for n in NODES:
            for tr in TRAFFIC:
                for mo in MOBILITY:
                    g = by_cell[(proto, n, tr, mo)]
                    assert sorted(r["_seed"] for r in g) == SEEDS, (proto, n, tr, mo)
                    cell = {"protocol": proto, "nodes": n, "traffic": tr, "mobility": mo,
                            "hopCountMethod": g[0]["HopCountMethod"], "metrics": {}}
                    for mk, (_c, scale, _u) in METRICS.items():
                        valid = [r["_" + mk] for r in g if not is_undefined(r, mk)]
                        cell["metrics"][mk] = metric_block(valid, len(g), scale)
                    cells.append(cell)

    # ---- chart-point level, seed-blocked -------------------------------------------------
    def seed_level(group_rows, seeds_expected_cells):
        """Return per-metric blocks for a set of runs spanning several cells."""
        per_seed_cells = {}
        for r in group_rows:
            per_seed_cells.setdefault(r["_seed"], []).append((r["RoutingProtocol"], r["_nodes"], r["TrafficLevel"], r["MobilityMode"]))
        cell_sets = {tuple(sorted(c)) for c in per_seed_cells.values()}
        balanced = len(cell_sets) == 1 and all(len(c) == len(set(c)) for c in per_seed_cells.values())
        assert balanced, "unbalanced chart point - refusing to fabricate an interval"
        assert len(next(iter(cell_sets))) == seeds_expected_cells
        out = {"nSeeds": len(per_seed_cells), "cells": seeds_expected_cells, "metrics": {}}
        for mk, (_c, scale, _u) in METRICS.items():
            bad = sorted({r["_seed"] for r in group_rows if is_undefined(r, mk)})
            per_seed = {}
            for r in group_rows:
                if r["_seed"] not in bad:
                    per_seed.setdefault(r["_seed"], []).append(r["_" + mk])
            values = [statistics.fmean(v) for _s, v in sorted(per_seed.items())]  # one value per valid seed
            blk = metric_block(values, len(per_seed_cells), scale)
            blk["excludedSeeds"] = bad
            out["metrics"][mk] = blk
        return out

    by_pn, by_pt = {}, {}
    for r in rows:
        by_pn.setdefault((r["RoutingProtocol"], r["_nodes"]), []).append(r)
        by_pt.setdefault((r["RoutingProtocol"], r["TrafficLevel"]), []).append(r)
    marginal_nodes = []      # one chart point per (protocol, node count): 9 cells = 3 traffic x 3 mobility
    for proto in PROTOCOLS:
        for n in NODES:
            marginal_nodes.append(dict(protocol=proto, nodes=n, **seed_level(by_pn[(proto, n)], len(TRAFFIC) * len(MOBILITY))))
    marginal_traffic = []    # one point per (protocol, traffic): 18 cells = 6 node counts x 3 mobility
    for proto in PROTOCOLS:
        for tr in TRAFFIC:
            marginal_traffic.append(dict(protocol=proto, traffic=tr, **seed_level(by_pt[(proto, tr)], len(NODES) * len(MOBILITY))))

    undefined_runs = []
    for r in rows:
        ex = [mk for mk in UNDEFINED_WHEN_NO_RX if is_undefined(r, mk)]
        if ex:
            undefined_runs.append({"protocol": r["RoutingProtocol"], "nodes": r["_nodes"], "traffic": r["TrafficLevel"],
                                   "mobility": r["MobilityMode"], "seed": r["_seed"], "packetsReceived": r["_rx"],
                                   "packetsSent": int(r["PacketsSent"]), "excludedMetrics": ex,
                                   "storedRawValue": {"delaySec": float(r["AverageDelaySec"]), "jitterSec": float(r["AverageJitterSec"]),
                                                      "hopCount": float(r["AverageHopCount"])}})
    return {
        "meta": {
            "purpose": "Derived statistical layer for the dashboard. Computed from results/v3-ext/*.csv; "
                       "final_research.json and research.db are NOT modified.",
            "generatedBy": "experiments/build_v3_site_stats.py",
            "source": {"csvDir": "results/v3-ext", "csvFiles": len(files), "officialRuns": len(rows),
                       "officialFilter": "Seed 20-30 inclusive AND Duration 300 s"},
            "design": {"protocols": PROTOCOLS, "nodes": NODES, "traffic": TRAFFIC, "mobility": MOBILITY,
                       "seeds": SEEDS, "replicationsPerCell": len(SEEDS), "cells": len(cells), "durationSec": int(DURATION)},
            "statistics": {"level": 0.95, "sided": "two-sided", "distribution": "Student t", "df": "n - 1",
                           "tTable": "dashboard/app.py::_T_TABLE_95 (3 dp)",
                           "ci": "mean +/- t(0.975, df) * SD / sqrt(n)", "sd": "sample SD (ddof = 1)", "se": "SD / sqrt(n)",
                           "t_n11": T_TABLE_95[10], "t_n10": T_TABLE_95[9]},
            "undefinedMetrics": {
                "rule": "PacketsReceived == 0 -> AverageDelaySec, AverageJitterSec and AverageHopCount (unless HopCountMethod == exact) are undefined",
                "alwaysDefined": ["pdr", "throughput", "loss", "routing_overhead", "path_changes", "link_util_avg", "link_util_max"],
                "excludedAt": "aggregation layer only; raw CSV / research.db / final_research.json keep the stored placeholder 0",
                "runs": undefined_runs,
            },
            "units": {k: v[2] for k, v in METRICS.items()},
            "marginalDefinition": {
                "nodes": "per (protocol, nodes): each seed's mean over its 9 traffic x mobility runs; CI across seeds",
                "traffic": "per (protocol, traffic): each seed's mean over its 18 node-count x mobility runs; CI across seeds",
                "undefinedHandling": "a seed with an undefined run for a metric is excluded whole for that metric",
            },
        },
        "cells": cells,
        "marginalNodes": marginal_nodes,
        "marginalTraffic": marginal_traffic,
    }


def main():
    doc = build()
    text = json.dumps(doc, indent=1, sort_keys=False, allow_nan=False) + "\n"
    if "--check" in sys.argv:
        current = open(OUT_PATH).read() if os.path.exists(OUT_PATH) else None
        print("v3ext-stats.json is up to date" if current == text else "v3ext-stats.json is STALE or missing")
        sys.exit(0 if current == text else 1)
    with open(OUT_PATH, "w") as fh:
        fh.write(text)
    print("wrote %s  (%d cells, %d undefined run(s) excluded from delay/jitter/hop only)" %
          (os.path.relpath(OUT_PATH, ROOT), len(doc["cells"]), len(doc["meta"]["undefinedMetrics"]["runs"])))


if __name__ == "__main__":
    main()
