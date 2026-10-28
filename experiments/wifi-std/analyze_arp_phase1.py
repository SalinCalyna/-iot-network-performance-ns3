#!/usr/bin/env python3
"""ARP study step 2: size of the ARP artifact in the Phase I (802.11b) residual loss.

    python3 -I -B experiments/wifi-std/analyze_arp_phase1.py

Inputs (read-only): results/wifi-std/arp-phase1-off, results/wifi-std/arp-phase1-on (iot-network-wifi-std-arp.cc),
  frozen references analysis/final-report-data/static_n50_diagnostic.csv (Static N=50, 12 runs) and
  analysis/bottleneck-characterisation/data/probe_aggregate.csv (OLSR N=75/100, 16 kbps, seed 20).
Definitions (identical to static_n50_diagnostic.csv): loss = txPkts - rxPkts (FlowMonitor);
  attributable = mac_queue + max_retry + ip_drop_{no_route,ttl,route_error,other}; residual = loss - attributable.
  New: arp = total_arp_l3_drops + total_arp_cache_drops; arp_share_of_residual = arp / residual;
  residual_after_arp = residual - arp.
Each ARP drop ends that packet's life at that hop, so it is disjoint from the MAC/IP drop counters. For Static and
  OLSR all ARP-resolved packets are data (routing control is broadcast), so arp counts lost data packets.
Checks (stop conditions): every run has provenance exit 0 and empty stderr; no NA/nan/inf/empty in the used
  numeric columns; b-off reproduces the frozen reference values of every compared column.
Output: results/wifi-std/arp-phase1-analysis/{phase1_arp.csv, REPORT.txt}
"""
import csv
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
W = ROOT / "results/wifi-std"
OUT = W / "arp-phase1-analysis"
DIAG = ROOT / "analysis/final-report-data/static_n50_diagnostic.csv"
PROBE = ROOT / "analysis/bottleneck-characterisation/data/probe_aggregate.csv"
DROPS = ["total_mac_queue_drops", "total_max_retry_drops", "total_ip_drop_no_route", "total_ip_drop_ttl",
         "total_ip_drop_route_error", "total_ip_drop_other"]
CELLS = ([("static", 50, r, s) for r in (16, 12, 8, 4) for s in (20, 25, 30)]
         + [("olsr", n, 16, 20) for n in (75, 100)])


def one(path):
    with open(path, newline="") as f:
        return next(csv.DictReader(f))


def num(v, where):
    try:
        x = float(v)
    except (TypeError, ValueError):
        sys.exit(f"STOP: non-numeric value {v!r} in {where}")
    if math.isnan(x) or math.isinf(x):
        sys.exit(f"STOP: NA value {v!r} in {where}")
    return x


def load(arm, p, n, r, s):
    d = W / f"arp-phase1-{arm}" / f"b-{arm}_{p}_{n}_rate{r}_seed{s}"
    pv = json.loads((d / "provenance.json").read_text())
    if pv["exit_code"] != 0 or pv["stderr_bytes"] or pv.get("timed_out"):
        sys.exit(f"STOP: {d.name} exit {pv['exit_code']} stderr {pv['stderr_bytes']}")
    a, e = one(d / "probe_aggregate.csv"), one(d / "wifistd_ext.csv")
    g = lambda row, k: num(row[k], f"{d.name}:{k}")
    tx, rx = g(a, "txPkts"), g(a, "rxPkts")
    att = sum(g(a, k) for k in DROPS)
    arp = g(e, "total_arp_l3_drops") + g(e, "total_arp_cache_drops")
    loss = tx - rx
    res = loss - att
    return dict(arm=arm, protocol=p, nodes=n, rate_kbps=r, seed=s, tx=tx, rx=rx, pdr=g(a, "pdr"),
                app_pdr=g(e, "app_pdr"), throughput_kbps=g(a, "throughputKbps"), gw_airtime=g(a, "gw_airtime_busy_frac"),
                loss=loss, mac_queue=g(a, "total_mac_queue_drops"), max_retry=g(a, "total_max_retry_drops"),
                attributable=att, residual=res, arp_l3=g(e, "total_arp_l3_drops"),
                arp_cache=g(e, "total_arp_cache_drops"), arp=arp,
                arp_pct_of_residual=(100 * arp / res if res > 0 else float("nan")),
                arp_pct_of_loss=(100 * arp / loss if loss > 0 else float("nan")),
                residual_after_arp=res - arp, wall_min=pv["wall_sec"] / 60, _agg=a)


def main():
    OUT.mkdir(exist_ok=True)
    with open(DIAG, newline="") as f:
        diag = {(int(r["rate_kbps"]), int(r["seed"])): r for r in csv.DictReader(f)}
    with open(PROBE, newline="") as f:
        probe = {(r["protocol"], int(r["nodes"]), int(r["seed"])): r for r in csv.DictReader(f)
                 if r["trafficLevel"] == "high"}
    rows, lines, mism = [], [], []
    for p, n, r, s in CELLS:
        off, on = load("off", p, n, r, s), load("on", p, n, r, s)
        # reproduction of the frozen Phase I values (flag off must equal the original program)
        if p == "static":
            ref = diag[(r, s)]
            pairs = [("txPkts", "txPkts"), ("rxPkts", "rxPkts"), ("PDR", "pdr"), ("mac_queue_drops", "total_mac_queue_drops"),
                     ("max_retry_drops", "total_max_retry_drops"), ("ip_drop_no_route", "total_ip_drop_no_route")]
            for rk, ak in pairs:
                if abs(float(ref[rk]) - float(off["_agg"][ak])) > 1e-3:
                    mism.append(f"static 50 {r} {s} {rk}: frozen {ref[rk]} vs b-off {off['_agg'][ak]}")
            if abs(float(ref["residual_loss"]) - off["residual"]) > 0.5:
                mism.append(f"static 50 {r} {s} residual: frozen {ref['residual_loss']} vs {off['residual']}")
        else:
            ref = probe[(p, n, s)]
            for k in ref:
                if k != "timestamp" and ref[k] != off["_agg"].get(k):
                    mism.append(f"{p} {n} {r} {s} {k}: frozen {ref[k]} vs b-off {off['_agg'].get(k)}")
        for x in (off, on):
            x.pop("_agg")
            rows.append(x)
        lines.append(f"{p:6s} N={n:3d} {r:2d}kbps s{s}: PDR off {off['pdr']:6.2f} -> on {on['pdr']:6.2f} "
                     f"(d {on['pdr'] - off['pdr']:+6.2f} pp) | off: residual {off['residual']:6.0f} "
                     f"({100 * off['residual'] / off['loss']:5.1f}% of loss), ARP {off['arp']:6.0f} = "
                     f"{off['arp_pct_of_residual']:5.1f}% of residual, residual-ARP {off['residual_after_arp']:6.0f} | "
                     f"on: ARP {on['arp']:.0f}, residual {on['residual']:.0f}")
    keys = [k for k in rows[0]]
    with open(OUT / "phase1_arp.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    st = [x for x in rows if x["arm"] == "off" and x["protocol"] == "static"]
    shares = [x["arp_pct_of_residual"] for x in st]
    rep = ["ARP study step 2 -- Phase I (802.11b) residual loss vs ARP drops", "",
           f"Reproduction of frozen Phase I values by b-off: {'all compared values identical' if not mism else 'MISMATCH'}"]
    rep += [f"  {m}" for m in mism]
    rep += ["", *lines, "",
            f"Static N=50 (12 runs), b-off: ARP share of residual min {min(shares):.1f}% / median "
            f"{sorted(shares)[len(shares) // 2]:.1f}% / max {max(shares):.1f}%",
            f"  residual left after ARP: min {min(x['residual_after_arp'] for x in st):.0f} / max "
            f"{max(x['residual_after_arp'] for x in st):.0f} packets"]
    (OUT / "REPORT.txt").write_text("\n".join(rep) + "\n")
    print("\n".join(rep))
    sys.exit(1 if mism else 0)


if __name__ == "__main__":
    main()
