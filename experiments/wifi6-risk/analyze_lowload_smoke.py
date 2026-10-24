#!/usr/bin/env python3
"""Summarise a risk-v2 low-load smoke batch (run_lowload_smoke.py). Read-only.

    python3 -I -B experiments/wifi6-risk/analyze_lowload_smoke.py results/wifi6-risk/lowload-smoke-v2-<time>

Writes <batch>/lowload_runs.csv and <batch>/lowload_by_rate.csv (mean, SD, min, max over seeds) and prints them.
Sink-based: PDR = unique sink deliveries / application packets sent; throughput = deliveries x 540 B x 8 / 270 s
(UDP payload 512 B + 28 B IP/UDP headers, the same byte count as FlowMonitor; apps run 30-300 s). Delay
percentiles are nearest-rank over delivered packets (packet_paths.csv). FlowMonitor rx is reported for comparison
only. With n = 3 no statistical test is made.
"""
import csv
import json
import math
import statistics as st
import sys
from pathlib import Path


def rows(p):
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


def pct(xs, q):
    return xs[max(0, math.ceil(q * len(xs)) - 1)] if xs else float("nan")


def main():
    b = Path(sys.argv[1])
    out = []
    for d in sorted((b / "runs").iterdir()):
        pv = json.loads((d / "provenance.json").read_text())
        a, s, e = rows(d / "probe_aggregate.csv")[0], rows(d / "risk_summary.csv")[0], rows(d / "wifistd_ext.csv")[0]
        dl = sorted(float(x["delay_s"]) for x in rows(d / "packet_paths.csv") if x["fate"] == "delivered")
        bar = sum(int(r["psdus"]) for r in rows(d / "wifi_txvector_counts.csv") if r["frame_type"] == "CTL_BACKREQ")
        app_tx, sink, fm = int(s["app_tx_pkts"]), int(s["delivered_unique"]), int(a["rxPkts"])
        rate = int(float(a["offered_rate_kbps"]))
        out.append(dict(
            run=d.name, rate_kbps=rate, seed=int(a["seed"]), exit_code=pv["exit_code"], stderr_bytes=pv["stderr_bytes"],
            wall_min=round(pv["wall_sec"] / 60, 1), app_tx=app_tx, sink_delivered=sink, duplicates=int(s["duplicates"]),
            sink_pdr_pct=100 * sink / app_tx, sink_thr_kbps=sink * 540 * 8 / 270 / 1000,
            offered_agg_kbps=100 * rate * 540 / 512, delivered_over_offered=(sink * 540 * 8 / 270 / 1000) / (100 * rate * 540 / 512),
            lost_pkts=app_tx - sink, fm_tx=int(a["txPkts"]), fm_rx=fm, sink_minus_fm=sink - fm, fm_pdr_pct=float(a["pdr"]),
            delay_mean_ms=1000 * st.mean(dl), delay_p50_ms=1000 * pct(dl, .5), delay_p95_ms=1000 * pct(dl, .95),
            delay_p99_ms=1000 * pct(dl, .99), delay_max_s=dl[-1], gt1s=sum(x > 1 for x in dl), gt10s=sum(x > 10 for x in dl),
            gw_airtime=float(a["gw_airtime_busy_frac"]), ring1_airtime=float(a["ring1_airtime_busy_frac_mean"]),
            rest_airtime=float(a["rest_airtime_busy_frac_mean"]), mac_queue_drops=int(a["total_mac_queue_drops"]),
            mpdu_expired=int(e["total_dropped_mpdu_expired_lifetime"]), mpdu_retry_drop=int(e["total_dropped_mpdu_retry_limit"]),
            no_route_drops=int(a["total_ip_drop_no_route"]), mean_hops_delivered=float(s["mean_hops_delivered"]),
            ba_fix_events=len(rows(d / "ba_ssn_fix.csv")), bar_psdus=bar))
    keys = list(out[0])
    with open(b / "lowload_runs.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    num = [k for k in keys if k not in ("run", "rate_kbps", "seed")]
    agg = []
    for r in sorted({x["rate_kbps"] for x in out}):
        xs = [x for x in out if x["rate_kbps"] == r]
        row = dict(rate_kbps=r, n_seeds=len(xs))
        for k in num:
            v = [float(x[k]) for x in xs]
            row[k + "_mean"], row[k + "_sd"] = st.mean(v), (st.stdev(v) if len(v) > 1 else 0.0)
            row[k + "_min"], row[k + "_max"] = min(v), max(v)
        agg.append(row)
    with open(b / "lowload_by_rate.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(agg[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(agg)
    for k in num:
        print(f"{k:24s}", "  ".join(f"{x['rate_kbps']}/{x['seed']}={x[k]:.5g}" if isinstance(x[k], float) else f"{x['rate_kbps']}/{x['seed']}={x[k]}" for x in out))
    print()
    for a in agg:
        for k in num:
            print(f"rate {a['rate_kbps']:>3} {k:24s} mean {a[k+'_mean']:.5g} sd {a[k+'_sd']:.4g} min {a[k+'_min']:.5g} max {a[k+'_max']:.5g}")


if __name__ == "__main__":
    main()
