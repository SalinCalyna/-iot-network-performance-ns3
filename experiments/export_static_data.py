#!/usr/bin/env python3
"""
Exports the real V2.7 results (results/*.csv) to static JSON files for the
GitHub Pages version of the dashboard, which has no Flask backend to query.

This produces exactly the same data the Flask app's /api/* endpoints serve
at request time -- nothing here is invented or approximated. Run this
whenever results/*.csv changes and the public site needs to reflect it.

Usage:
    python3 experiments/export_static_data.py [results_dir] [out_dir]
    (defaults: results_dir=results, out_dir=site/data)

This script never writes to results/*.csv or results/logs/* -- read-only
on the real experiment data.
"""

import csv
import glob
import json
import os
import statistics
import sys

EXPECTED_COLUMNS = {
    "RoutingProtocol", "NumberOfNodes", "PosSeed", "PacketsSent",
    "PacketsReceived", "PacketLoss", "PDR", "ThroughputKbps", "AverageDelaySec",
}


def load_all_rows(results_dir):
    rows = []
    csv_files = sorted(
        p for p in glob.glob(os.path.join(results_dir, "*.csv"))
        if os.path.basename(p) != "statistics.csv"
    )
    for path in csv_files:
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            if not EXPECTED_COLUMNS.issubset(set(reader.fieldnames or [])):
                continue
            for r in reader:
                rows.append(
                    {
                        "protocol": r["RoutingProtocol"].strip().lower(),
                        "nodes": int(r["NumberOfNodes"]),
                        "trial": int(r["PosSeed"]),
                        "packetsSent": int(r["PacketsSent"]),
                        "packetsReceived": int(r["PacketsReceived"]),
                        "packetLoss": int(r["PacketLoss"]),
                        "pdr": float(r["PDR"]),
                        "throughputKbps": float(r["ThroughputKbps"]),
                        "delaySec": float(r["AverageDelaySec"]),
                        "sourceFile": os.path.basename(path),
                    }
                )
    return rows, [os.path.basename(p) for p in csv_files]


def build_summary(rows):
    groups = {}
    for r in rows:
        groups.setdefault((r["protocol"], r["nodes"]), []).append(r)

    out = []
    for (protocol, nodes), trials in sorted(groups.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        def mean_std(key):
            values = [t[key] for t in trials]
            mean = statistics.mean(values)
            std = statistics.stdev(values) if len(values) > 1 else 0.0
            return mean, std

        pdr_mean, pdr_std = mean_std("pdr")
        thr_mean, thr_std = mean_std("throughputKbps")
        delay_mean, delay_std = mean_std("delaySec")
        loss_mean, loss_std = mean_std("packetLoss")

        out.append(
            {
                "protocol": protocol,
                "nodes": nodes,
                "trials": len(trials),
                "pdrMean": pdr_mean, "pdrStd": pdr_std,
                "throughputMean": thr_mean, "throughputStd": thr_std,
                "delayMean": delay_mean, "delayStd": delay_std,
                "lossMean": loss_mean, "lossStd": loss_std,
            }
        )
    return out


def build_meta(rows, csv_files):
    protocols = sorted({r["protocol"] for r in rows})
    node_sizes = sorted({r["nodes"] for r in rows})
    trials = sorted({r["trial"] for r in rows})
    scenario_count = len({(r["protocol"], r["nodes"]) for r in rows})
    return {
        "totalScenarios": scenario_count,
        "totalTrials": len(rows),
        "protocols": protocols,
        "networkSizes": node_sizes,
        "trials": trials,
        "csvFilesDetected": csv_files,
        "problems": [],
        "resultsDir": "results",
        "note": "Exported once at build time from the real results/*.csv files -- this is a static snapshot, not a live query.",
    }


METHODOLOGY = {
    "simulator": "ns-3 (ns-3.47-dev)",
    "simulationFile": "scratch/iot-network.cc",
    "network": (
        "Multi-hop IEEE 802.11b ad-hoc IoT mesh: AdhocWifiMac, "
        "ConstantRateWifiManager @ DsssRate1Mbps, "
        "LogDistancePropagationLossModel (exponent=3.0, referenceLoss=40dB)"
    ),
    "gatewayNote": (
        "Gateway and Server are merged into a single node (hosts the sink "
        "application), positioned at the centre of the field."
    ),
    "protocols": [
        "AODV (reactive)",
        "OLSR (proactive)",
        "Static (BFS shortest-hop routes over an assumed 90 m disk "
        "connectivity model, installed as fixed Ipv4StaticRouting host routes)",
    ],
    "networkSizes": [10, 20, 30, 50],
    "trialsPerScenario": "5 independent topology seeds (--posSeed 1-5)",
    "areaSize": "250 m x 250 m square deployment area (fixed across all sizes and protocols)",
    "txPowerDbm": 20.0,
    "txRangeNote": "90 m nominal disk range, used only for computing Static routes",
    "packetSize": "512 bytes",
    "trafficPerSource": "8 kbps continuous UDP CBR per sensor (OnTime=1, OffTime=0)",
    "totalSimTime": "100 s (--simTime=100)",
    "applicationStart": "30 s (--appStart=30)",
    "activeTrafficWindow": (
        "70 s (from 30 s to 100 s) -- this is the window throughput is normalized "
        "over, not the total 100 s simulation time"
    ),
    "source": "Values read from experiments/run_experiments.sh and scratch/iot-network.cc.",
}


def load_sigmoid_validation_rows(pilot_dir):
    """V2.8 is a superseded, informal pilot (scratch/iot-network-v28-sigmoid-pilot.cc,
    formerly iot-network-v3.cc before the advisor-assigned V3 study took over that
    name): only 4 rows exist (1 seed x {aodv,olsr,static,sigmoid}, medium traffic,
    15 nodes). This is a smoke-test validation run, NOT a statistical comparison --
    n=1 per protocol. Kept in its own JSON so it can never be silently merged into
    the V2.7 12-scenario/5-trial dataset the rest of the dashboard relies on, and
    kept separate from the real V3 (Barabasi-Albert / risk-aware routing) dataset.
    """
    rows = []
    if not os.path.isdir(pilot_dir):
        return rows
    for path in sorted(glob.glob(os.path.join(pilot_dir, "*.csv"))):
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for r in reader:
                rows.append(
                    {
                        "protocol": r["protocol"].strip().lower(),
                        "seed": int(r["seed"]),
                        "nodes": int(r["nodes"]),
                        "trafficCondition": r["traffic_condition"],
                        "dataRate": r["data_rate"],
                        "packetsSent": int(r["packets_sent"]),
                        "packetsReceived": int(r["packets_received"]),
                        "packetLoss": int(r["packet_loss"]),
                        "pdr": float(r["pdr"]),
                        "throughputKbps": float(r["throughput_kbps"]),
                        "delaySec": float(r["delay_sec"]),
                        "jitterSec": float(r["jitter_sec"]),
                        "hopCount": float(r["hop_count"]),
                        "hopCountMethod": r["hop_count_method"],
                        "routingOverheadPackets": int(r["routing_overhead_packets"]),
                        "unreachableSensors": int(r["unreachable_sensors"]),
                        "sigmoidK": float(r["sigmoid_k"]) if r["sigmoid_k"] else None,
                        "sigmoidX0": float(r["sigmoid_x0"]) if r["sigmoid_x0"] else None,
                        "sigmoidWLinkQuality": float(r["sigmoid_w_link_quality"]) if r["sigmoid_w_link_quality"] else None,
                        "sigmoidWLoad": float(r["sigmoid_w_load"]) if r["sigmoid_w_load"] else None,
                        "sourceFile": os.path.basename(path),
                    }
                )
    return rows


SIGMOID_META = {
    "status": "SUPERSEDED -- V2.8 pilot, VALIDATION ONLY, not a statistical comparison",
    "note": (
        "scratch/iot-network-v28-sigmoid-pilot.cc (renamed from iot-network-v3.cc; "
        "'V3' now names the advisor-assigned Barabasi-Albert / risk-aware routing "
        "study -- see site/data/v3-summary.json) added a 4th routing mode "
        "(sigmoid-weighted Dijkstra) to a separate 15-node topology, as an "
        "early-stage, informal research direction built before that assignment. "
        "Only a single 4-run smoke test has been executed (1 seed, medium traffic, "
        "one run per protocol) to confirm the code compiles, runs, and produces "
        "sane output -- the full experiment matrix has not been run and never will "
        "be, this pilot is superseded. These 4 rows must not be read as evidence "
        "that sigmoid routing outperforms AODV/OLSR/Static; with n=1 per protocol "
        "there is no variance estimate and no statistical basis for that claim."
    ),
    "equation": "S(x) = 1 / (1 + exp(-k * (x - x0)))",
    "proxies": [
        "link_quality = distance / txRange (geometric proxy for link reliability)",
        "load = node_degree / max_degree (proxy for relative node congestion)",
    ],
    "docsSource": "docs/sigmoid-metric.md, docs/methodology.md, docs/experiment-design.md (all describe the superseded V2.8 pilot)",
}


# ======================================================================
# V3 Phase 1 -- expanded experiment matrix (results/v3-ext/*.csv), the
# topology-preserving track (scratch/iot-network-v3-ext.cc). This is a
# DIFFERENT dataset from results/v3/ (Barabasi-Albert/risk-aware-routing,
# exported above as sigmoid.json) and from results/v28-sigmoid-pilot/ --
# see docs/v3-experiment-framework.md. Mirrors dashboard/app.py's
# /api/v3ext/* endpoints so the static site shows the same numbers the
# Flask dashboard does, just exported at build time instead of queried live.
# ======================================================================
V3EXT_EXPECTED_COLUMNS = {
    "RoutingProtocol", "NumberOfNodes", "TrafficLevel", "MobilityMode",
    "Seed", "Duration", "PacketsSent", "PacketsReceived", "PacketLoss", "PDR",
    "ThroughputKbps", "AverageDelaySec", "AverageJitterSec",
    "RoutingOverheadPackets", "AverageHopCount", "HopCountMethod",
    "PathChanges", "AverageLinkUtilization", "MaximumLinkUtilization",
    "UnreachableSensors",
}


def load_v3ext_rows(v3ext_dir):
    rows = []
    csv_files = sorted(
        p for p in glob.glob(os.path.join(v3ext_dir, "*.csv"))
    ) if os.path.isdir(v3ext_dir) else []
    used_files = []
    for path in csv_files:
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            if not V3EXT_EXPECTED_COLUMNS.issubset(set(reader.fieldnames or [])):
                continue
            used_files.append(os.path.basename(path))
            for r in reader:
                rows.append(
                    {
                        "protocol": r["RoutingProtocol"].strip().lower(),
                        "nodes": int(r["NumberOfNodes"]),
                        "traffic": r["TrafficLevel"].strip().lower(),
                        "mobility": r["MobilityMode"].strip().lower(),
                        "seed": int(r["Seed"]),
                        "duration": float(r["Duration"]),
                        "packetsSent": int(r["PacketsSent"]),
                        "packetsReceived": int(r["PacketsReceived"]),
                        "packetLoss": int(r["PacketLoss"]),
                        "pdr": float(r["PDR"]),
                        "throughputKbps": float(r["ThroughputKbps"]),
                        "delaySec": float(r["AverageDelaySec"]),
                        "jitterSec": float(r["AverageJitterSec"]),
                        "routingOverheadPackets": int(r["RoutingOverheadPackets"]),
                        "hopCount": float(r["AverageHopCount"]),
                        "hopCountMethod": r["HopCountMethod"],
                        "pathChanges": int(r["PathChanges"]),
                        "avgLinkUtilization": float(r["AverageLinkUtilization"]),
                        "maxLinkUtilization": float(r["MaximumLinkUtilization"]),
                        "unreachableSensors": int(r["UnreachableSensors"]),
                        "sourceFile": os.path.basename(path),
                    }
                )
    return rows, used_files


V3EXT_METRIC_KEYS = [
    ("pdr", "pdr"), ("throughputKbps", "throughput"), ("delaySec", "delay"),
    ("jitterSec", "jitter"), ("packetLoss", "packetLoss"),
    ("routingOverheadPackets", "routingOverhead"), ("hopCount", "hopCount"),
    ("pathChanges", "pathChanges"), ("avgLinkUtilization", "avgLinkUtil"),
    ("maxLinkUtilization", "maxLinkUtil"),
]


def build_v3ext_summary(rows):
    """Groups by (protocol, nodes, traffic, mobility, duration) -- duration
    is part of the key, same reasoning as dashboard/app.py's
    /api/v3ext/summary: aodv_10_medium_static.csv mixes 30s/40s smoke-test
    rows with the real 300s validation row, and grouping without duration
    would silently blend them into one misleading mean."""
    groups = {}
    for r in rows:
        key = (r["protocol"], r["nodes"], r["traffic"], r["mobility"], r["duration"])
        groups.setdefault(key, []).append(r)

    out = []
    for (protocol, nodes, traffic, mobility, duration), g in groups.items():
        n = len(g)
        row = {
            "protocol": protocol, "nodes": nodes, "traffic": traffic,
            "mobility": mobility, "duration": duration, "n": n,
            "hopCountMethod": g[0]["hopCountMethod"],
        }
        for src_key, out_key in V3EXT_METRIC_KEYS:
            values = [x[src_key] for x in g]
            mean = statistics.mean(values)
            std = statistics.stdev(values) if n > 1 else 0.0
            row[f"{out_key}Mean"] = mean
            row[f"{out_key}Std"] = std
        out.append(row)
    out.sort(key=lambda r: (r["nodes"], r["protocol"], r["traffic"], r["mobility"], r["duration"]))
    return out


def build_v3ext_meta(rows, csv_files):
    if not rows:
        return {
            "totalRows": 0, "protocols": [], "networkSizes": [], "trafficLevels": [],
            "mobilityModes": [], "seeds": [], "durations": [], "csvFilesDetected": csv_files,
            "resultsDir": "results/v3-ext",
        }
    return {
        "totalRows": len(rows),
        "protocols": sorted({r["protocol"] for r in rows}),
        "networkSizes": sorted({r["nodes"] for r in rows}),
        "trafficLevels": sorted({r["traffic"] for r in rows}),
        "mobilityModes": sorted({r["mobility"] for r in rows}),
        "seeds": sorted({r["seed"] for r in rows}),
        "durations": sorted({r["duration"] for r in rows}),
        "csvFilesDetected": csv_files,
        "resultsDir": "results/v3-ext",
        "note": (
            "Exported once at build time from the real results/v3-ext/*.csv files -- "
            "a static snapshot, not a live query. Validation (Seed 1) and the Official "
            "V3 experiment (Seeds 20-30, 11 seeds inclusive) are distinct -- see "
            "docs/v3-experiment-framework.md's Seeds subsection. As of this export, "
            "only Seed 1 validation data exists on disk; Seeds 20-30 have not been run."
        ),
    }


def main():
    results_dir = sys.argv[1] if len(sys.argv) > 1 else "results"
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "site/data"
    pilot_dir = os.path.join(results_dir, "v28-sigmoid-pilot")
    v3ext_dir = os.path.join(results_dir, "v3-ext")

    rows, csv_files = load_all_rows(results_dir)
    if not rows:
        print(f"No valid CSV rows found under {results_dir}/", file=sys.stderr)
        sys.exit(1)

    summary = build_summary(rows)
    meta = build_meta(rows, csv_files)
    sigmoid_rows = load_sigmoid_validation_rows(pilot_dir)
    v3ext_rows, v3ext_csv_files = load_v3ext_rows(v3ext_dir)
    v3ext_summary = build_v3ext_summary(v3ext_rows)
    v3ext_meta = build_v3ext_meta(v3ext_rows, v3ext_csv_files)

    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "rows.json"), "w") as f:
        json.dump(rows, f, indent=2)
    with open(os.path.join(out_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    with open(os.path.join(out_dir, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    with open(os.path.join(out_dir, "methodology.json"), "w") as f:
        json.dump(METHODOLOGY, f, indent=2)
    with open(os.path.join(out_dir, "sigmoid.json"), "w") as f:
        json.dump({"meta": SIGMOID_META, "rows": sigmoid_rows}, f, indent=2)
    with open(os.path.join(out_dir, "v3ext-rows.json"), "w") as f:
        json.dump(v3ext_rows, f, indent=2)
    with open(os.path.join(out_dir, "v3ext-summary.json"), "w") as f:
        json.dump(v3ext_summary, f, indent=2)
    with open(os.path.join(out_dir, "v3ext-meta.json"), "w") as f:
        json.dump(v3ext_meta, f, indent=2)

    print(f"Exported {len(rows)} rows, {len(summary)} summary groups -> {out_dir}/")
    print(f"  rows.json, summary.json, meta.json, methodology.json")
    print(f"Exported {len(sigmoid_rows)} V3 sigmoid validation rows -> {out_dir}/sigmoid.json")
    print(f"Exported {len(v3ext_rows)} V3 Phase 1 rows, {len(v3ext_summary)} summary groups -> "
          f"{out_dir}/v3ext-rows.json, v3ext-summary.json, v3ext-meta.json")


if __name__ == "__main__":
    main()
