#!/usr/bin/env python3
"""
Research analysis pipeline for the "Analysis of IoT Network Performance
Using NS-3" V2.7 dataset.

    NS-3 C++ simulation -> CSV -> (this script) -> statistics + graphs -> dashboard

This script never runs NS-3 and never writes to results/*.csv or
results/logs/* -- it only reads them. Its own outputs go to
results/statistics.csv and results/plots/*.png + results/plots/*.svg
(one PNG for fast preview/dashboard display, one SVG for publication use,
per detected metric).

Validation is strict: if the CSV structure or values don't match what the
V2.7 experiment design expects (required columns, protocol names, node
counts, PDR range, received<=sent, no duplicate trials), this script STOPS
and reports the problem instead of silently continuing with graphs/
statistics built on data that might be corrupted.

Metrics are auto-detected, not hard-coded to a fixed list: the four V2.7
metrics (PDR, throughput, packet loss, delay) are always present in the
current dataset, but if a CSV also has extra columns (e.g. jitter or hop
count, as V3's schema does), those are picked up automatically and plotted
too -- and, symmetrically, nothing is fabricated for a column that isn't
there.

Usage:
    python3 experiments/analyze_results.py [results_dir]

Exit codes: 0 on success, 1 on a validation failure or missing data.
"""

import csv
import glob
import os
import statistics
import sys

# Required for every row -- validation fails if any of these are missing.
# This is exactly the V2.7 schema; it is not relaxed just because a CSV
# happens to have extra columns too.
EXPECTED_COLUMNS = {
    "RoutingProtocol", "NumberOfNodes", "PosSeed", "PacketsSent",
    "PacketsReceived", "PacketLoss", "PDR", "ThroughputKbps", "AverageDelaySec",
}
EXPECTED_PROTOCOLS = {"aodv", "olsr", "static"}
EXPECTED_NODE_SIZES = {10, 20, 30, 50}

# Column name -> (metric key, human-readable axis label). This is the full
# set of metric columns this script knows how to plot; which of them
# actually get graphed for a given dataset is decided at runtime by
# intersecting this against whatever columns the loaded CSVs actually have
# (see detect_available_metrics()) -- nothing here is assumed present.
KNOWN_METRIC_COLUMNS = [
    ("PDR", "pdr", "PDR (%)"),
    ("ThroughputKbps", "throughput", "Throughput (kbps)"),
    ("PacketLoss", "packet_loss", "Packet Loss (packets)"),
    ("AverageDelaySec", "delay", "End-to-End Delay (s)"),
    ("AverageJitterSec", "jitter", "Jitter (s)"),
    ("JitterSec", "jitter", "Jitter (s)"),
    ("HopCount", "hop_count", "Hop Count"),
    ("RoutingOverheadPackets", "routing_overhead", "Routing Overhead (packets)"),
]


def detect_available_metrics(fieldnames):
    """Which of KNOWN_METRIC_COLUMNS are actually present in this CSV's
    header. Never assumes a metric exists -- if a column isn't there, that
    metric is simply not analyzed or plotted for this dataset."""
    present = set(fieldnames)
    seen_keys = set()
    metrics = []
    for col, key, label in KNOWN_METRIC_COLUMNS:
        if col in present and key not in seen_keys:
            metrics.append((col, key, label))
            seen_keys.add(key)
    return metrics


# ---------------------------------------------------------------- discovery
def discover_csv_files(results_dir):
    """Experiment result CSVs only -- excludes this script's own output
    (statistics.csv), which lives in the same directory but is not an
    input trial."""
    all_csv = glob.glob(os.path.join(results_dir, "*.csv"))
    return sorted(p for p in all_csv if os.path.basename(p) != "statistics.csv")


# ---------------------------------------------------------------- loading
def load_rows(csv_files):
    """Reads every row from every CSV, tagging each with its source file.
    Does not validate here -- that happens in validate_rows() so all
    problems can be reported together, not just the first one found.
    Also returns the union of every fieldname seen across all files, so the
    caller can auto-detect which optional metrics are actually available."""
    rows = []
    all_fieldnames = set()
    for path in csv_files:
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                rows.append({"__file": path, "__error": "empty file / no header"})
                continue
            missing = EXPECTED_COLUMNS - set(reader.fieldnames)
            if missing:
                rows.append({"__file": path, "__error": f"missing columns {sorted(missing)}"})
                continue
            all_fieldnames.update(reader.fieldnames)
            for r in reader:
                r["__file"] = os.path.basename(path)
                rows.append(r)
    return rows, all_fieldnames


# ---------------------------------------------------------------- validation
def validate_rows(rows):
    """Returns a list of problem strings. Empty list = data is clean.
    Does not repair anything -- every problem found here is reported
    verbatim to the caller, which stops rather than plotting on top of it."""
    problems = []
    seen_trials = {}

    for r in rows:
        if "__error" in r:
            problems.append(f"{r['__file']}: {r['__error']}")
            continue

        f = r["__file"]
        protocol_raw = r["RoutingProtocol"]
        protocol = protocol_raw.strip().lower()
        if protocol not in EXPECTED_PROTOCOLS:
            problems.append(f"{f}: unexpected protocol name '{protocol_raw}' (expected one of {sorted(EXPECTED_PROTOCOLS)})")

        try:
            nodes = int(r["NumberOfNodes"])
        except (ValueError, TypeError):
            problems.append(f"{f}: NumberOfNodes is not a valid integer ('{r['NumberOfNodes']}')")
            continue
        if nodes not in EXPECTED_NODE_SIZES:
            problems.append(
                f"{f}: unexpected network size {nodes} nodes (expected one of {sorted(EXPECTED_NODE_SIZES)}) "
                f"-- a 15-node (or any non-V2.7) result must not be mixed into this dataset"
            )

        try:
            seed = int(r["PosSeed"])
            tx = int(r["PacketsSent"])
            rx = int(r["PacketsReceived"])
            loss = int(r["PacketLoss"])
            pdr = float(r["PDR"])
            throughput = float(r["ThroughputKbps"])
            delay = float(r["AverageDelaySec"])
        except (ValueError, TypeError) as exc:
            problems.append(f"{f}: non-numeric value in a numeric column ({exc})")
            continue

        key = (protocol, nodes, seed)
        if key in seen_trials:
            problems.append(f"{f}: duplicate trial protocol={protocol} nodes={nodes} seed={seed} (already seen in {seen_trials[key]})")
        else:
            seen_trials[key] = f

        if tx < 0 or rx < 0 or loss < 0:
            problems.append(f"{f}: negative packet count (sent={tx}, received={rx}, loss={loss})")
        if rx > tx:
            problems.append(f"{f}: received packets ({rx}) exceed sent packets ({tx})")
        if pdr < 0 or pdr > 100:
            problems.append(f"{f}: PDR out of range ({pdr})")
        if loss != tx - rx:
            problems.append(f"{f}: PacketLoss ({loss}) != Sent-Received ({tx - rx})")
        if throughput == 0 and rx > 0:
            problems.append(f"{f}: zero throughput despite {rx} packets received (inconsistent)")

    return problems


def clean_rows(rows, metric_columns):
    """Rows with numeric protocol/nodes/seed plus every detected metric
    column, for use only after validate_rows() has confirmed there are no
    problems. metric_columns is the list from detect_available_metrics()."""
    out = []
    for r in rows:
        if "__error" in r:
            continue
        cleaned = {
            "protocol": r["RoutingProtocol"].strip().lower(),
            "nodes": int(r["NumberOfNodes"]),
            "seed": int(r["PosSeed"]),
        }
        for col, _key, _label in metric_columns:
            try:
                cleaned[col] = float(r[col])
            except (KeyError, ValueError, TypeError):
                # Column present in some files but not this row/file --
                # skip it for this row rather than fabricating a value.
                continue
        out.append(cleaned)
    return out


# ---------------------------------------------------------------- statistics
def compute_statistics(rows, metric_columns):
    """One row per (protocol, nodes, metric) in tidy/long format --
    matches the requested protocol/nodes/trials/mean/std columns, plus
    min/max/metric for completeness and reproducibility. Only metrics
    actually present in the data (metric_columns) are computed."""
    groups = {}
    for r in rows:
        groups.setdefault((r["protocol"], r["nodes"]), []).append(r)

    stats_rows = []
    for (protocol, nodes), trials in sorted(groups.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        for csv_col, _metric_key, _label in metric_columns:
            values = [t[csv_col] for t in trials if csv_col in t]
            if not values:
                continue
            mean = statistics.mean(values)
            std = statistics.stdev(values) if len(values) > 1 else 0.0
            stats_rows.append(
                {
                    "protocol": protocol,
                    "nodes": nodes,
                    "metric": csv_col,
                    "trials": len(values),
                    "mean": mean,
                    "std": std,
                    "min": min(values),
                    "max": max(values),
                }
            )
    return stats_rows


def write_statistics_csv(stats_rows, out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["protocol", "nodes", "metric", "trials", "mean", "std", "min", "max"])
        writer.writeheader()
        for row in stats_rows:
            writer.writerow(row)


# ---------------------------------------------------------------- graphs
GRAPH_TITLES = {
    "pdr": "Packet Delivery Ratio vs Network Size",
    "throughput": "Throughput vs Network Size",
    "packet_loss": "Packet Loss vs Network Size",
    "delay": "End-to-End Delay vs Network Size",
    "jitter": "Jitter vs Network Size",
    "hop_count": "Hop Count vs Network Size",
    "routing_overhead": "Routing Overhead vs Network Size",
}


def generate_graphs(stats_rows, metric_columns, out_dir):
    """Renders one grouped-bar-with-error-bars figure per detected metric,
    saved as both PNG (fast preview, dashboard display) and SVG (vector,
    publication-quality) -- only for metrics actually present in the data."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    os.makedirs(out_dir, exist_ok=True)
    protocol_labels = {"aodv": "AODV", "olsr": "OLSR", "static": "Static", "sigmoid": "Sigmoid"}
    colors = {"aodv": "#3b82f6", "olsr": "#f59e0b", "static": "#0891b2", "sigmoid": "#8b5cf6"}

    by_metric = {}
    for row in stats_rows:
        by_metric.setdefault(row["metric"], []).append(row)

    generated = []
    for csv_col, metric_key, ylabel in metric_columns:
        rows = by_metric.get(csv_col, [])
        node_sizes = sorted({r["nodes"] for r in rows})
        protocols = sorted({r["protocol"] for r in rows})
        if not node_sizes or not protocols:
            continue

        fig, ax = plt.subplots(figsize=(8, 5))
        width = 0.8 / max(len(protocols), 1)
        x = range(len(node_sizes))
        for i, protocol in enumerate(protocols):
            by_nodes = {r["nodes"]: r for r in rows if r["protocol"] == protocol}
            means = [by_nodes[n]["mean"] if n in by_nodes else 0 for n in node_sizes]
            stds = [by_nodes[n]["std"] if n in by_nodes else 0 for n in node_sizes]
            offsets = [xi + (i - (len(protocols) - 1) / 2.0) * width for xi in x]
            ax.bar(offsets, means, width=width, yerr=stds, capsize=4,
                   label=protocol_labels.get(protocol, protocol.title()),
                   color=colors.get(protocol, "#999999"))

        ax.set_xticks(list(x))
        ax.set_xticklabels([f"{n} nodes" for n in node_sizes])
        ax.set_xlabel("Number of Nodes")
        ax.set_ylabel(ylabel)
        ax.set_title(GRAPH_TITLES.get(metric_key, f"{ylabel} vs Network Size"))
        ax.legend()
        ax.grid(axis="y", alpha=0.3)
        fig.tight_layout()

        base_name = f"{metric_key}_vs_nodes"
        for ext in ("png", "svg"):
            out_path = os.path.join(out_dir, f"{base_name}.{ext}")
            fig.savefig(out_path, dpi=150 if ext == "png" else None)
            generated.append(out_path)
        plt.close(fig)

    return generated


# ---------------------------------------------------------------- console report
def print_report(csv_files, rows, stats_rows, metric_columns, graph_paths, statistics_path):
    protocols = sorted({r["protocol"] for r in rows})
    node_sizes = sorted({r["nodes"] for r in rows})
    all_known_keys = {key for _col, key, _label in KNOWN_METRIC_COLUMNS}
    detected_keys = {key for _col, key, _label in metric_columns}
    skipped_keys = sorted(all_known_keys - detected_keys)

    print("=" * 40)
    print("IoT Network Research Analysis")
    print("=" * 40)
    print()
    print("Dataset:")
    print(f"  {os.path.basename(os.path.normpath(sys.argv[1] if len(sys.argv) > 1 else 'results'))}")
    print()
    print("Protocols:")
    print("  " + " / ".join(p.upper() if p != "static" else "Static" for p in protocols))
    print()
    print("Network sizes:")
    print("  " + " / ".join(str(n) for n in node_sizes))
    print()
    print("Trials:")
    print(f"  {len(rows)}")
    print()
    print("-" * 40)
    print("Analyzing CSV files...")
    print(f"  {len(csv_files)} CSV files found")
    print(f"  {len(rows)} trials detected")
    print("  Data validation passed")
    print()
    print("-" * 40)
    print("Detecting available metrics...")
    print("  " + ", ".join(key for _col, key, _label in metric_columns))
    if skipped_keys:
        print(f"  (not present in this dataset, skipped: {', '.join(skipped_keys)})")
    print()
    print("-" * 40)
    print("Generating statistics...")
    print("  Mean")
    print("  Standard deviation")
    print(f"  -> {statistics_path}")
    print()
    print("-" * 40)
    print("Generating graphs (PNG + SVG)...")
    for path in graph_paths:
        print(f"  -> {path}")
    print()
    print("-" * 40)
    print("Analysis completed successfully.")
    print("=" * 40)
    print()
    print("V2.7 Limitation:")
    print("  AODV packet-count accounting requires further validation before")
    print("  making definitive cross-protocol PDR comparisons.")


def main():
    results_dir = sys.argv[1] if len(sys.argv) > 1 else "results"

    csv_files = discover_csv_files(results_dir)
    if not csv_files:
        print(f"No CSV files found under {results_dir}/", file=sys.stderr)
        sys.exit(1)

    raw_rows, fieldnames = load_rows(csv_files)
    problems = validate_rows(raw_rows)
    if problems:
        print("Data validation FAILED -- refusing to generate statistics or graphs.", file=sys.stderr)
        print(f"({len(problems)} problem(s) found)", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        sys.exit(1)

    metric_columns = detect_available_metrics(fieldnames)
    rows = clean_rows(raw_rows, metric_columns)
    stats_rows = compute_statistics(rows, metric_columns)

    statistics_path = os.path.join(results_dir, "statistics.csv")
    write_statistics_csv(stats_rows, statistics_path)

    plots_dir = os.path.join(results_dir, "plots")
    graph_paths = generate_graphs(stats_rows, metric_columns, plots_dir)

    print_report(csv_files, rows, stats_rows, metric_columns, graph_paths, statistics_path)


if __name__ == "__main__":
    main()
