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

from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, render_template, request, send_from_directory

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
RESULTS_DIR = PROJECT_ROOT / "results"

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
    df, _ = load_all_csv()
    df = apply_filters(
        df, request.args.get("protocol"), request.args.get("nodes"), request.args.get("trial")
    )
    if df.empty:
        return jsonify([])

    out = []
    for (protocol, nodes), g in df.groupby(["RoutingProtocol", "NumberOfNodes"]):

        def mean_std(col):
            mean = float(g[col].mean())
            std = float(g[col].std(ddof=1)) if len(g) > 1 else 0.0
            if pd.isna(std):
                std = 0.0
            return mean, std

        pdr_mean, pdr_std = mean_std("PDR")
        thr_mean, thr_std = mean_std("ThroughputKbps")
        delay_mean, delay_std = mean_std("AverageDelaySec")
        loss_mean, loss_std = mean_std("PacketLoss")

        out.append(
            {
                "protocol": protocol,
                "nodes": int(nodes),
                "trials": int(len(g)),
                "pdrMean": pdr_mean,
                "pdrStd": pdr_std,
                "throughputMean": thr_mean,
                "throughputStd": thr_std,
                "delayMean": delay_mean,
                "delayStd": delay_std,
                "lossMean": loss_mean,
                "lossStd": loss_std,
            }
        )

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
        series = df[col]
        stats[col] = {
            "mean": float(series.mean()),
            "std": float(series.std(ddof=1)) if len(series) > 1 else 0.0,
            "min": float(series.min()),
            "max": float(series.max()),
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
