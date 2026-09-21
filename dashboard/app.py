#!/usr/bin/env python3
"""
Local read-only results dashboard for the ns-3 IoT Network V2 study.

This app never writes to, modifies, or deletes anything under results/. It
only reads *.csv files at startup-of-request time (via load_all_csv(), called
fresh on every API call so newly added CSVs are picked up automatically) and
serves aggregated/raw views of that data plus a methodology summary whose
values are read from experiments/run_experiments.sh and scratch/iot-network.cc
as they exist on disk -- nothing here is a hardcoded experiment result.

Run with:
    python3 dashboard/app.py
Then open:
    http://127.0.0.1:5000
"""

import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_from_directory

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
RESULTS_DIR = PROJECT_ROOT / "results"

# Loads dashboard/.env if present (see .env.example). Never commit .env --
# it's excluded via dashboard/.gitignore. GOOGLE_MAPS_API_KEY is read from
# the environment only; nothing is ever hardcoded here.
load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)

# The column set every V2 result CSV is expected to have (see
# scratch/iot-network.cc's CSV-writing block). A file missing any of these
# is skipped (reported via /api/meta's "problems" list) rather than crashing
# the dashboard or being silently guessed at.
EXPECTED_COLUMNS = {
    "RoutingProtocol",
    "NumberOfNodes",
    "PosSeed",
    "PacketsSent",
    "PacketsReceived",
    "PacketLoss",
    "PDR",
    "ThroughputKbps",
    "AverageDelaySec",
}


def load_all_csv():
    """Reads every *.csv currently under results/ and concatenates them.

    Runs fresh on every call (no caching) so files added or removed between
    requests are picked up without restarting the server. Returns
    (dataframe, problems) where problems lists any file that didn't match
    the expected V2 CSV structure and was therefore skipped.
    """
    frames = []
    problems = []
    for path in sorted(RESULTS_DIR.glob("*.csv")):
        try:
            df = pd.read_csv(path)
        except Exception as exc:  # noqa: BLE001 - report, don't crash
            problems.append(f"{path.name}: could not be read ({exc})")
            continue
        missing = EXPECTED_COLUMNS - set(df.columns)
        if missing:
            problems.append(f"{path.name}: missing expected columns {sorted(missing)}")
            continue
        df["__source_file"] = path.name
        frames.append(df)

    if not frames:
        return pd.DataFrame(columns=sorted(EXPECTED_COLUMNS) + ["__source_file"]), problems

    combined = pd.concat(frames, ignore_index=True)
    return combined, problems


# Some per-run metrics are UNDEFINED -- not zero -- for a run in which no data
# packet was received: average delay and jitter are (sum over received
# packets) / (received packets), and the approximate hop count is
# 1 + timesForwarded / received. With PacketsReceived == 0 the simulator writes
# the placeholder 0.0 into the CSV (scratch/iot-network-v3-ext.cc: the
# `totalRx > 0 ? ... : 0.0` guards). That 0 is not a measurement, so it must not
# enter a mean/SD/CI. The raw CSVs and research.db keep the stored 0 untouched;
# the exclusion happens here, at aggregation time, per metric, and the valid n
# is always reported next to the total. PDR, throughput and packet loss are
# genuinely 0 for such a run and are never excluded.
#
# Hop count is exempt when HopCountMethod == "exact" (Static routing): that value
# is computed from the fixed route tree, independent of deliveries, so it stays
# defined even when nothing was received.
_UNDEFINED_WHEN_NO_RX = ("AverageDelaySec", "AverageJitterSec", "AverageHopCount")


def _undefined_mask(df, col):
    """Boolean Series, True where metric `col` is undefined for that run."""
    no_rx = pd.to_numeric(df["PacketsReceived"], errors="coerce") == 0
    if col in ("AverageDelaySec", "AverageJitterSec"):
        return no_rx
    if col == "AverageHopCount" and "HopCountMethod" in df.columns:
        return no_rx & (df["HopCountMethod"] != "exact")
    return pd.Series(False, index=df.index)


def _valid_values(df, col):
    """The DEFINED observations of `col` as floats. A metric that can never be
    undefined (PDR, throughput, loss, ...) is returned untouched -- exactly the
    pre-existing computation, with no mask built."""
    if col not in _UNDEFINED_WHEN_NO_RX:
        return df[col].astype(float)
    return df.loc[~_undefined_mask(df, col), col].astype(float)


def _mean_sd_ci95(values):
    """(n, mean, sd, ci95, df, t) over the valid observations only. n<2 has no CI
    (never fabricated as 0); n==0 has no mean either."""
    n = int(len(values))
    if n == 0:
        return n, None, None, None, None, None
    mean = float(values.mean())
    std = float(values.std(ddof=1)) if n > 1 else 0.0
    if pd.isna(std):
        std = 0.0
    tcrit = _t_critical_95(n)
    ci95 = (tcrit * std / (n ** 0.5)) if (tcrit is not None and n > 1) else None
    return n, mean, std, ci95, (n - 1 if n > 1 else None), tcrit


def apply_filters(df, protocol, nodes, trial):
    if protocol and protocol != "all":
        df = df[df["RoutingProtocol"].str.lower() == protocol.lower()]
    if nodes and nodes != "all":
        df = df[df["NumberOfNodes"] == int(nodes)]
    if trial and trial != "all":
        df = df[df["PosSeed"] == int(trial)]
    return df


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/config")
def api_config():
    """Non-secret runtime config for the frontend. The Google Maps key (if
    set) is read from the environment/`.env` only -- never hardcoded, never
    committed. `mapsConfigured` lets the frontend show a graceful message
    instead of a blank map when it's missing."""
    key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    return jsonify(
        {
            "mapsConfigured": bool(key),
            "googleMapsApiKey": key,
            "defaultCenter": {"lat": 7.8917, "lng": 98.3897},  # PSU Phuket Campus (approximate)
            "defaultCenterLabel": "Prince of Songkla University, Phuket Campus",
        }
    )


@app.route("/api/validate")
def api_validate():
    """Runs the same anomaly checks used in the V2.7.1 validation report
    (PDR>100%, negative values, rx>tx, loss != sent-received) live against
    whatever is currently in results/*.csv, so the dashboard never silently
    assumes the data is clean."""
    df, _ = load_all_csv()
    issues = []
    for _, r in df.iterrows():
        tag = f"{r['RoutingProtocol']}/{r['NumberOfNodes']}n/seed{r['PosSeed']}"
        tx, rx, loss, pdr = r["PacketsSent"], r["PacketsReceived"], r["PacketLoss"], r["PDR"]
        if pdr > 100.0 or pdr < 0.0:
            issues.append(f"{tag}: PDR out of range ({pdr})")
        if rx > tx:
            issues.append(f"{tag}: received packets ({rx}) exceed sent packets ({tx})")
        if loss != tx - rx:
            issues.append(f"{tag}: PacketLoss ({loss}) != Sent-Received ({tx - rx})")
        if tx < 0 or rx < 0 or loss < 0:
            issues.append(f"{tag}: negative packet count")
    return jsonify({"rowsChecked": int(df.shape[0]), "issues": issues, "valid": len(issues) == 0})


@app.route("/api/meta")
def api_meta():
    df, problems = load_all_csv()
    csv_files = sorted(p.name for p in RESULTS_DIR.glob("*.csv"))

    if df.empty:
        return jsonify(
            {
                "totalScenarios": 0,
                "totalTrials": 0,
                "protocols": [],
                "networkSizes": [],
                "trials": [],
                "csvFilesDetected": csv_files,
                "problems": problems,
                "resultsDir": str(RESULTS_DIR),
            }
        )

    scenario_count = df.drop_duplicates(["RoutingProtocol", "NumberOfNodes"]).shape[0]
    return jsonify(
        {
            "totalScenarios": int(scenario_count),
            "totalTrials": int(df.shape[0]),
            "protocols": sorted(df["RoutingProtocol"].unique().tolist()),
            "networkSizes": sorted(int(n) for n in df["NumberOfNodes"].unique().tolist()),
            "trials": sorted(int(t) for t in df["PosSeed"].unique().tolist()),
            "csvFilesDetected": csv_files,
            "problems": problems,
            "resultsDir": str(RESULTS_DIR),
        }
    )


@app.route("/api/rows")
def api_rows():
    df, _ = load_all_csv()
    df = apply_filters(
        df, request.args.get("protocol"), request.args.get("nodes"), request.args.get("trial")
    )
    if df.empty:
        return jsonify([])

    view = df.rename(
        columns={
            "RoutingProtocol": "protocol",
            "NumberOfNodes": "nodes",
            "PosSeed": "trial",
            "PacketsSent": "packetsSent",
            "PacketsReceived": "packetsReceived",
            "PacketLoss": "packetLoss",
            "PDR": "pdr",
            "ThroughputKbps": "throughputKbps",
            "AverageDelaySec": "delaySec",
        }
    )[
        [
            "protocol",
            "nodes",
            "trial",
            "packetsSent",
            "packetsReceived",
            "packetLoss",
            "pdr",
            "throughputKbps",
            "delaySec",
        ]
    ]
    view = view.sort_values(["nodes", "protocol", "trial"])
    return jsonify(view.to_dict(orient="records"))


@app.route("/api/summary")
def api_summary():
    """Groups V2 baseline rows by (protocol, nodes) and reports mean/std/95%
    CI across the PosSeed trials present for that cell (5 per cell in this
    track, not the V3-ext 20-30 seed range -- see api_v3ext_summary). Same
    Student's-t method as V3-ext (_t_critical_95), just a different n."""
    df, _ = load_all_csv()
    df = apply_filters(
        df, request.args.get("protocol"), request.args.get("nodes"), request.args.get("trial")
    )
    if df.empty:
        return jsonify([])

    out = []
    for (protocol, nodes), g in df.groupby(["RoutingProtocol", "NumberOfNodes"]):
        n = int(len(g))
        row = {"protocol": protocol, "nodes": int(nodes), "trials": n}
        # Each metric on its own valid observations. Only delay is undefined
        # for a no-packets-received trial (V2 has no jitter/hop columns); PDR,
        # throughput and loss keep every trial (n stays = trials).
        for col, key in (
            ("PDR", "pdr"),
            ("ThroughputKbps", "throughput"),
            ("AverageDelaySec", "delay"),
            ("PacketLoss", "loss"),
        ):
            valid = _valid_values(g, col)
            n_valid, mean, std, ci95, df_, tcrit = _mean_sd_ci95(valid)
            row[f"{key}Mean"] = mean
            row[f"{key}Std"] = std
            row[f"{key}Ci95"] = ci95
            row[f"{key}N"] = n_valid
            row[f"{key}Excluded"] = n - n_valid
            row[f"{key}Df"] = df_
            row[f"{key}TCritical"] = tcrit
        out.append(row)

    out.sort(key=lambda r: (r["nodes"], r["protocol"]))
    return jsonify(out)


@app.route("/api/files")
def api_files():
    """Lists each CSV under results/ with metadata for the Raw Data Explorer.
    Protocol/nodes are read from the file's own data columns, not guessed
    from the filename, so this stays correct even if naming conventions
    change."""
    out = []
    for path in sorted(RESULTS_DIR.glob("*.csv")):
        try:
            df = pd.read_csv(path)
        except Exception as exc:  # noqa: BLE001
            out.append({"filename": path.name, "error": str(exc)})
            continue
        missing = EXPECTED_COLUMNS - set(df.columns)
        entry = {
            "filename": path.name,
            "rowCount": int(df.shape[0]),
            "columns": list(df.columns),
        }
        if missing:
            entry["error"] = f"missing expected columns {sorted(missing)}"
        else:
            entry["protocol"] = (
                df["RoutingProtocol"].iloc[0] if not df.empty else None
            )
            entry["nodes"] = int(df["NumberOfNodes"].iloc[0]) if not df.empty else None
            entry["trialCount"] = int(df["PosSeed"].nunique()) if not df.empty else 0
        out.append(entry)
    return jsonify(out)


@app.route("/api/file/<path:filename>")
def api_file_detail(filename):
    """Raw rows + summary stats for one CSV, for the Raw Data Explorer."""
    safe_name = Path(filename).name  # strip any directory components
    path = RESULTS_DIR / safe_name
    if not safe_name.endswith(".csv") or not path.is_file():
        return jsonify({"error": "file not found"}), 404
    try:
        df = pd.read_csv(path)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 400

    missing = EXPECTED_COLUMNS - set(df.columns)
    result = {"filename": safe_name, "columns": list(df.columns), "rows": df.to_dict(orient="records")}
    if missing:
        result["error"] = f"missing expected columns {sorted(missing)}"
        return jsonify(result)

    numeric_cols = ["PacketsSent", "PacketsReceived", "PacketLoss", "PDR", "ThroughputKbps", "AverageDelaySec"]
    stats = {}
    for col in numeric_cols:
        # Undefined observations (delay of a no-packets-received trial) are left
        # out of that metric's statistics; `n` says how many were used.
        series = df.loc[~_undefined_mask(df, col), col]
        if series.empty:
            stats[col] = {"mean": None, "std": None, "min": None, "max": None, "n": 0}
            continue
        stats[col] = {
            "mean": float(series.mean()),
            "std": float(series.std(ddof=1)) if len(series) > 1 else 0.0,
            "min": float(series.min()),
            "max": float(series.max()),
            "n": int(len(series)),
        }
        if pd.isna(stats[col]["std"]):
            stats[col]["std"] = 0.0
    result["stats"] = stats
    return jsonify(result)


@app.route("/download/<path:filename>")
def download_file(filename):
    """Serves an existing results CSV byte-for-byte, unmodified, for
    download. Restricted to *.csv files that actually live in results/ --
    no path traversal, no other file types."""
    safe_name = Path(filename).name
    path = RESULTS_DIR / safe_name
    if not safe_name.endswith(".csv") or not path.is_file():
        return jsonify({"error": "file not found"}), 404
    return send_from_directory(RESULTS_DIR, safe_name, as_attachment=True)


@app.route("/api/graphs")
def api_graphs():
    """Lists the research plots generated by experiments/analyze_results.py
    (results/plots/*.png + *.svg) and whether results/statistics.csv
    exists, so the dashboard never hardcodes filenames. This is read fresh
    on every call -- re-running the analysis pipeline and reloading the
    dashboard page is all that's needed to pick up new plots, no caching.
    Empty/false if the pipeline hasn't been run yet -- this endpoint does
    not generate anything itself."""
    plots_dir = RESULTS_DIR / "plots"
    png_files = sorted(p.name for p in plots_dir.glob("*.png")) if plots_dir.is_dir() else []
    svg_files = sorted(p.name for p in plots_dir.glob("*.svg")) if plots_dir.is_dir() else []
    stats_path = RESULTS_DIR / "statistics.csv"
    return jsonify(
        {
            "graphs": png_files,
            "svgGraphs": svg_files,
            "statisticsAvailable": stats_path.is_file(),
            "generatedAt": stats_path.stat().st_mtime if stats_path.is_file() else None,
        }
    )


@app.route("/results/plots/<path:filename>")
def serve_plot(filename):
    """Serves a generated plot (PNG or SVG). Read-only, restricted to
    results/plots/."""
    safe_name = Path(filename).name
    plots_dir = RESULTS_DIR / "plots"
    path = plots_dir / safe_name
    if not (safe_name.endswith(".png") or safe_name.endswith(".svg")) or not path.is_file():
        return jsonify({"error": "plot not found -- run experiments/run_and_analyze.sh"}), 404
    return send_from_directory(plots_dir, safe_name)


# ======================================================================
# V3 Phase 1 -- expanded experiment matrix, V2 topology preserved
# (scratch/iot-network-v3-ext.cc -> results/v3-ext/*.csv). This is a
# DIFFERENT dataset from results/v3/ (scratch/iot-network-v3.cc, the
# Barabasi-Albert / risk-aware-routing study) and from
# results/v28-sigmoid-pilot/ (the earlier informal sigmoid exploration) --
# see docs/v3-experiment-framework.md's "Three tracks" table. Read-only,
# same as every other section: nothing here is fabricated or hardcoded.
# ======================================================================
V3EXT_DIR = RESULTS_DIR / "v3-ext"

V3EXT_EXPECTED_COLUMNS = {
    "RoutingProtocol",
    "NumberOfNodes",
    "TrafficLevel",
    "DataRate",
    "MobilityMode",
    "MobilitySpeed",
    "Seed",
    "Duration",
    "PacketsSent",
    "PacketsReceived",
    "PacketLoss",
    "PDR",
    "ThroughputKbps",
    "AverageDelaySec",
    "AverageJitterSec",
    "RoutingOverheadPackets",
    "AverageHopCount",
    "HopCountMethod",
    "PathChanges",
    "AverageLinkUtilization",
    "MaximumLinkUtilization",
    "UnreachableSensors",
}

# Two-sided 97.5th-percentile Student's t critical values, indexed by degrees
# of freedom (df = n_seeds - 1). No scipy dependency is used elsewhere in
# this project (see experiments/requirements.txt), so this small textbook
# table stands in for scipy.stats.t.ppf for the df range this study
# actually uses (a handful of seeds up to ~30); df > 30 falls back to the
# normal approximation (1.96), which is standard practice at that sample size.
_T_TABLE_95 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
    6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
    11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
    16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
    21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
    26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
}


def _t_critical_95(n):
    """95% two-sided critical value for n samples (df = n-1). n<2 has no
    defined confidence interval (returns None -- never fabricated as 0)."""
    if n < 2:
        return None
    df = n - 1
    if df in _T_TABLE_95:
        return _T_TABLE_95[df]
    if df > 30:
        return 1.96
    # df not in the table and <=30 shouldn't happen (table is dense 1-30),
    # but fall back to the nearest tabulated df rather than guessing.
    return _T_TABLE_95[min(_T_TABLE_95.keys(), key=lambda k: abs(k - df))]


def load_v3ext_csv():
    """Same pattern as load_all_csv(), scoped to results/v3-ext/. Read fresh
    on every call; never caches, never writes."""
    frames = []
    problems = []
    if not V3EXT_DIR.is_dir():
        return pd.DataFrame(columns=sorted(V3EXT_EXPECTED_COLUMNS) + ["__source_file"]), problems
    for path in sorted(V3EXT_DIR.glob("*.csv")):
        try:
            df = pd.read_csv(path)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{path.name}: could not be read ({exc})")
            continue
        missing = V3EXT_EXPECTED_COLUMNS - set(df.columns)
        if missing:
            problems.append(f"{path.name}: missing expected columns {sorted(missing)}")
            continue
        df["__source_file"] = path.name
        frames.append(df)

    if not frames:
        return pd.DataFrame(columns=sorted(V3EXT_EXPECTED_COLUMNS) + ["__source_file"]), problems
    return pd.concat(frames, ignore_index=True), problems


def apply_v3ext_filters(df, nodes, traffic, mobility, routing, duration=None):
    if nodes and nodes != "all":
        df = df[df["NumberOfNodes"] == int(nodes)]
    if traffic and traffic != "all":
        df = df[df["TrafficLevel"].str.lower() == traffic.lower()]
    if mobility and mobility != "all":
        df = df[df["MobilityMode"].str.lower() == mobility.lower()]
    if routing and routing != "all":
        df = df[df["RoutingProtocol"].str.lower() == routing.lower()]
    if duration and duration != "all":
        df = df[df["Duration"] == float(duration)]
    return df


# Official V3 Baseline runs are defined strictly as Seed 20-30 inclusive
# (advisor-specified 2026-08-26 -- see docs/v3-experiment-framework.md and
# experiments/run_v3_experiments.py). Every other row in results/v3-ext/*.csv
# -- Seed 1/2 validation runs, Seed 99, and short-duration smoke tests -- is
# legacy/non-official data. It stays on disk untouched and remains reachable
# through the "all" and "legacy" seed ranges below, but the DEFAULT aggregation
# counts only Seed 20-30 so every official cell aggregates exactly its 11 seeds
# and nothing else (this is what fixed the six aodv/medium/static cells that
# otherwise picked up a stray Seed 1 run sharing Duration 300 s).
V3EXT_OFFICIAL_SEED_LOW = 20
V3EXT_OFFICIAL_SEED_HIGH = 30


def _v3ext_official_mask(df):
    seeds = pd.to_numeric(df["Seed"], errors="coerce")
    return seeds.between(V3EXT_OFFICIAL_SEED_LOW, V3EXT_OFFICIAL_SEED_HIGH)


def apply_v3ext_seed_range(df, seed_range):
    """seed_range: 'official' (default) keeps only Seed 20-30; 'legacy' keeps
    only rows outside that range; 'all' keeps everything. An unrecognised value
    falls back to 'official' -- the safe default -- rather than silently
    returning the full mixed set. Never mutates or drops the underlying CSVs;
    this is a per-request view filter only."""
    if df.empty or seed_range == "all":
        return df
    mask = _v3ext_official_mask(df)
    if seed_range == "legacy":
        return df[~mask]
    return df[mask]


@app.route("/api/v3ext/meta")
def api_v3ext_meta():
    df, problems = load_v3ext_csv()
    csv_files = sorted(p.name for p in V3EXT_DIR.glob("*.csv")) if V3EXT_DIR.is_dir() else []
    if df.empty:
        return jsonify(
            {
                "totalRows": 0,
                "protocols": [],
                "networkSizes": [],
                "trafficLevels": [],
                "mobilityModes": [],
                "seeds": [],
                "durations": [],
                "csvFilesDetected": csv_files,
                "problems": problems,
                "resultsDir": str(V3EXT_DIR),
            }
        )
    return jsonify(
        {
            "totalRows": int(df.shape[0]),
            "protocols": sorted(df["RoutingProtocol"].unique().tolist()),
            "networkSizes": sorted(int(n) for n in df["NumberOfNodes"].unique().tolist()),
            "trafficLevels": sorted(df["TrafficLevel"].unique().tolist()),
            "mobilityModes": sorted(df["MobilityMode"].unique().tolist()),
            "seeds": sorted(int(s) for s in df["Seed"].unique().tolist()),
            "durations": sorted(float(d) for d in df["Duration"].unique().tolist()),
            "csvFilesDetected": csv_files,
            "problems": problems,
            "resultsDir": str(V3EXT_DIR),
        }
    )


@app.route("/api/v3ext/rows")
def api_v3ext_rows():
    df, _ = load_v3ext_csv()
    df = apply_v3ext_filters(
        df,
        request.args.get("nodes"),
        request.args.get("traffic"),
        request.args.get("mobility"),
        request.args.get("routing"),
        request.args.get("duration"),
    )
    # Per-run rows honour the same seed-range view as the summary (default
    # 'official' = Seed 20-30). 'all' or 'legacy' surface the legacy/smoke
    # rows individually -- they are never removed from results/v3-ext/*.csv.
    df = apply_v3ext_seed_range(df, request.args.get("seedRange", "official"))
    if df.empty:
        return jsonify([])
    view = df.rename(
        columns={
            "RoutingProtocol": "protocol",
            "NumberOfNodes": "nodes",
            "TrafficLevel": "traffic",
            "DataRate": "dataRate",
            "MobilityMode": "mobility",
            "MobilitySpeed": "mobilitySpeed",
            "Seed": "seed",
            "Duration": "duration",
            "PacketsSent": "packetsSent",
            "PacketsReceived": "packetsReceived",
            "PacketLoss": "packetLoss",
            "PDR": "pdr",
            "ThroughputKbps": "throughputKbps",
            "AverageDelaySec": "delaySec",
            "AverageJitterSec": "jitterSec",
            "RoutingOverheadPackets": "routingOverheadPackets",
            "AverageHopCount": "hopCount",
            "HopCountMethod": "hopCountMethod",
            "PathChanges": "pathChanges",
            "AverageLinkUtilization": "avgLinkUtilization",
            "MaximumLinkUtilization": "maxLinkUtilization",
            "UnreachableSensors": "unreachableSensors",
        }
    )
    cols = [
        "protocol", "nodes", "traffic", "dataRate", "mobility", "mobilitySpeed", "seed",
        "duration", "packetsSent", "packetsReceived", "packetLoss", "pdr", "throughputKbps",
        "delaySec", "jitterSec", "routingOverheadPackets", "hopCount", "hopCountMethod",
        "pathChanges", "avgLinkUtilization", "maxLinkUtilization", "unreachableSensors",
    ]
    view = view[cols].sort_values(["nodes", "protocol", "traffic", "mobility", "seed"])
    return jsonify(view.to_dict(orient="records"))


# Metric column -> output key, used by /api/v3ext/summary. Mean/std/95% CI
# are computed for every one of these; nothing here is skipped or faked.
V3EXT_METRICS = [
    ("PDR", "pdr"),
    ("ThroughputKbps", "throughput"),
    ("AverageDelaySec", "delay"),
    ("AverageJitterSec", "jitter"),
    ("PacketLoss", "packetLoss"),
    ("RoutingOverheadPackets", "routingOverhead"),
    ("AverageHopCount", "hopCount"),
    ("PathChanges", "pathChanges"),
    ("AverageLinkUtilization", "avgLinkUtil"),
    ("MaximumLinkUtilization", "maxLinkUtil"),
]


@app.route("/api/v3ext/summary")
def api_v3ext_summary():
    """Groups filtered rows by (protocol, nodes, traffic, mobility, duration)
    and computes mean/std/95% CI across the seeds present for that group. n
    (seed count) is always reported alongside.

    The `seedRange` query param controls which seeds are in scope and
    defaults to 'official' -- Seed 20-30 only -- so every official cell
    aggregates exactly its 11 seeds. 'all' includes legacy/smoke rows;
    'legacy' isolates them. The underlying CSVs are never changed."""
    df, _ = load_v3ext_csv()
    df = apply_v3ext_filters(
        df,
        request.args.get("nodes"),
        request.args.get("traffic"),
        request.args.get("mobility"),
        request.args.get("routing"),
        request.args.get("duration"),
    )
    df = apply_v3ext_seed_range(df, request.args.get("seedRange", "official"))
    if df.empty:
        return jsonify([])

    out = []
    # Duration is part of the grouping key -- NOT just an incidental column --
    # because results/v3-ext/*.csv accumulates every run ever made against a
    # given (protocol, nodes, traffic, mobility) by appending (same convention
    # as V2), and this project has already run both short smoke-test durations
    # (e.g. 40s) and the real 300s validation duration against the same
    # scenario. Grouping without Duration would silently average a 40s
    # smoke-test row together with a 300s validation row into one misleading
    # "mean" -- confirmed as a real, found issue (aodv_10_medium_static.csv
    # contains rows at 30s, 40s, and 300s), not a hypothetical one.
    group_cols = ["RoutingProtocol", "NumberOfNodes", "TrafficLevel", "MobilityMode", "Duration"]
    for (protocol, nodes, traffic, mobility, duration), g in df.groupby(group_cols):
        n = int(len(g))
        row = {
            "protocol": protocol,
            "nodes": int(nodes),
            "traffic": traffic,
            "mobility": mobility,
            "duration": float(duration),
            "n": n,
            "hopCountMethod": g["HopCountMethod"].iloc[0] if not g.empty else None,
        }
        for col, key in V3EXT_METRICS:
            # Each metric on its own valid observations (see _undefined_mask):
            # n_valid, df = n_valid - 1 and t(0.975, df) are per metric. `n`
            # above stays the number of seeds in the cell; `<key>N` is how many
            # of them this metric could use, `<key>Excluded` the difference.
            series = _valid_values(g, col)
            n_valid, mean, std, ci95, df_, tcrit = _mean_sd_ci95(series)
            row[f"{key}Mean"] = mean
            row[f"{key}Std"] = std
            row[f"{key}Ci95"] = ci95
            row[f"{key}N"] = n_valid
            row[f"{key}Excluded"] = n - n_valid
            row[f"{key}Df"] = df_
            row[f"{key}TCritical"] = tcrit
        out.append(row)

    out.sort(key=lambda r: (r["nodes"], r["protocol"], r["traffic"], r["mobility"], r["duration"]))
    return jsonify(out)


@app.route("/api/v3ext/marginal")
def api_v3ext_marginal():
    """Seed-level 95% CI for a line-chart point that spans several
    traffic x mobility cells.

    /api/v3ext/summary gives one CI per (protocol, nodes, traffic, mobility,
    duration) cell. A chart point that averages several such cells has no valid
    CI if it is built from those cell means (or from their pooled runs, which
    mixes between-condition variance into the spread). The valid seed-level
    observation for such a point is: for each seed, the mean of that seed's runs
    across the selected cells -- one number per seed. The CI is then the usual
    two-sided Student's t interval across those per-seed numbers:

        mean = average of the n seed values          (n = 11 official seeds)
        SE   = sample SD (ddof=1) / sqrt(n)
        CI95 = t(0.975, df = n-1) * SE                (df = 10, t = 2.228)

    Groups by (protocol, nodes, duration) -- the same grain the line chart
    plots. Only *balanced* groups get statistics: every seed must contribute
    exactly the same set of (traffic, mobility) cells, which is what makes the
    mean of the per-seed values equal the chart's mean-of-cell-means line. An
    unbalanced group (e.g. the legacy Seed 1/2/99 rows under seedRange=all)
    is returned with balanced=false and no statistics rather than a fabricated
    interval. Raw CIs are returned unclamped; any physical-bound clamping is a
    display-only concern handled by the front end.

    Undefined metrics (delay / jitter / approximate hop count of a run that
    received no packets -- see _undefined_mask) are handled per metric by
    complete-case exclusion of the affected seed: `<key>N` is the number of valid
    seeds, `<key>ExcludedSeeds` lists the dropped ones, `<key>Df` / `<key>TCritical`
    follow from n_valid. The row-level n/df/tCritical describe the design's seeds.
    Read-only.
    """
    df, _ = load_v3ext_csv()
    df = apply_v3ext_filters(
        df,
        request.args.get("nodes"),
        request.args.get("traffic"),
        request.args.get("mobility"),
        request.args.get("routing"),
        request.args.get("duration"),
    )
    df = apply_v3ext_seed_range(df, request.args.get("seedRange", "official"))
    if df.empty:
        return jsonify([])

    out = []
    for (protocol, nodes, duration), g in df.groupby(["RoutingProtocol", "NumberOfNodes", "Duration"]):
        cells_by_seed = {}
        for seed, traffic, mobility in zip(g["Seed"], g["TrafficLevel"], g["MobilityMode"]):
            cells_by_seed.setdefault(int(seed), []).append((traffic, mobility))
        cell_sets = {tuple(sorted(cells)) for cells in cells_by_seed.values()}
        # Balanced: one shared cell set, and no seed contributes a cell twice.
        balanced = len(cell_sets) == 1 and all(
            len(cells) == len(set(cells)) for cells in cells_by_seed.values()
        )
        n = len(cells_by_seed)
        row = {
            "protocol": protocol,
            "nodes": int(nodes),
            "duration": float(duration),
            "n": n,
            "df": n - 1 if n > 1 else None,
            "cells": len(next(iter(cell_sets))) if balanced else None,
            "balanced": bool(balanced),
            "tCritical": _t_critical_95(n),
        }
        if balanced:
            for col, key in V3EXT_METRICS:
                # Complete-case by seed, per metric: a seed in which ANY of the
                # averaged runs has this metric undefined (no packets received)
                # is left out of this metric entirely, so every remaining
                # per-seed value is an average over the same full set of cells
                # (the seed blocking is kept). Nothing is imputed and n is not
                # restored: n_valid, df = n_valid - 1 and t(0.975, df) are per
                # metric. Metrics with no undefined runs are unchanged.
                bad_seeds = (
                    sorted({int(s) for s in g.loc[_undefined_mask(g, col), "Seed"]})
                    if col in _UNDEFINED_WHEN_NO_RX
                    else []
                )
                gv = g[~g["Seed"].isin(bad_seeds)] if bad_seeds else g
                per_seed = gv.groupby("Seed")[col].mean().astype(float)  # one value per valid seed
                n_valid, mean, std, ci95, df_, tcrit = _mean_sd_ci95(per_seed)
                row[f"{key}Mean"] = mean
                row[f"{key}Std"] = std
                row[f"{key}Ci95"] = ci95
                row[f"{key}N"] = n_valid
                row[f"{key}Excluded"] = n - n_valid
                row[f"{key}ExcludedSeeds"] = bad_seeds
                row[f"{key}Df"] = df_
                row[f"{key}TCritical"] = tcrit
        out.append(row)

    out.sort(key=lambda r: (r["nodes"], r["protocol"], r["duration"]))
    return jsonify(out)


SIGMOID_META = {
    "status": "SUPERSEDED -- V2.8 pilot, VALIDATION ONLY, not a statistical comparison",
    "note": (
        "scratch/iot-network-v28-sigmoid-pilot.cc (renamed from iot-network-v3.cc; "
        "'V3' now names the advisor-assigned Barabasi-Albert / risk-aware routing "
        "study -- see the V3 section below) added a 4th routing mode "
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


@app.route("/api/sigmoid")
def api_sigmoid():
    """V2.8 pilot sigmoid-routing validation data (results/v28-sigmoid-pilot/*.csv),
    kept in its own endpoint so it can never be silently merged into the V2.7
    dataset the rest of the dashboard relies on, or confused with the real V3
    (Barabasi-Albert / risk-aware routing) dataset served by /api/v3-summary.
    Returns an empty rows list -- not an error -- if the directory is empty."""
    v3_dir = RESULTS_DIR / "v28-sigmoid-pilot"
    rows = []
    if v3_dir.is_dir():
        for path in sorted(v3_dir.glob("*.csv")):
            df = pd.read_csv(path)
            for record in df.to_dict(orient="records"):
                rows.append(
                    {
                        "protocol": str(record["protocol"]).strip().lower(),
                        "seed": int(record["seed"]),
                        "nodes": int(record["nodes"]),
                        "trafficCondition": record["traffic_condition"],
                        "dataRate": record["data_rate"],
                        "packetsSent": int(record["packets_sent"]),
                        "packetsReceived": int(record["packets_received"]),
                        "packetLoss": int(record["packet_loss"]),
                        "pdr": float(record["pdr"]),
                        "throughputKbps": float(record["throughput_kbps"]),
                        "delaySec": float(record["delay_sec"]),
                        "jitterSec": float(record["jitter_sec"]),
                        "hopCount": float(record["hop_count"]),
                        "hopCountMethod": record["hop_count_method"],
                        "routingOverheadPackets": int(record["routing_overhead_packets"]),
                        "unreachableSensors": int(record["unreachable_sensors"]),
                        "sigmoidK": float(record["sigmoid_k"]) if pd.notna(record.get("sigmoid_k")) else None,
                        "sigmoidX0": float(record["sigmoid_x0"]) if pd.notna(record.get("sigmoid_x0")) else None,
                        "sigmoidWLinkQuality": float(record["sigmoid_w_link_quality"]) if pd.notna(record.get("sigmoid_w_link_quality")) else None,
                        "sigmoidWLoad": float(record["sigmoid_w_load"]) if pd.notna(record.get("sigmoid_w_load")) else None,
                        "sourceFile": path.name,
                    }
                )
    return jsonify({"meta": SIGMOID_META, "rows": rows})


@app.route("/api/methodology")
def api_methodology():
    # These values are read from experiments/run_experiments.sh and
    # scratch/iot-network.cc as they exist on disk (checked when this file
    # was written) -- they are not invented, and are independent of any
    # individual CSV's contents.
    return jsonify(
        {
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
    )


if __name__ == "__main__":
    print(f"Reading V2 results from: {RESULTS_DIR}")
    print("Starting dashboard at http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)
