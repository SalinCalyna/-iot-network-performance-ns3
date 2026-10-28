#!/usr/bin/env python3
"""ARP study: Phase I offered-rate sweep (802.11b) with the ARP fix off vs on.

    python3 -I -B experiments/wifi-std/analyze_arp_ratesweep.py

Inputs (read-only): results/wifi-std/arp-ratesweep-{off,on}/ (iot-network-wifi-std-arp.cc; 72 runs each, same
  conditions and seeds as analysis/bottleneck-characterisation/run_ratesweep_batch.sh), frozen
  analysis/bottleneck-characterisation/data-ratesweep/probe_aggregate.csv (reproduction check of the off arm).
Per cell (protocol, N, rate kbps per sensor), 3 seeds (20, 25, 30): mean and SD of FlowMonitor PDR %, throughput kbps,
  gateway airtime (0-1), MAC-queue drops (packets/run; NB counts every MPDU incl. routing control and ARP frames),
  retry drops (packets/run), ARP drops (packets/run); delta vs 16 kbps (pp / %); per-seed monotonicity of PDR over
  16 -> 12 -> 8 -> 4 kbps; MAC-queue concentration ratio at hop <= 1 (Phase I definition: per seed, share of sensor
  MAC-queue drops at hop <= 1 and share of sensors at hop <= 1; ratio of the seed means; seeds without drops are left
  out of the drop-share mean and counted).
Stop checks: provenance exit 0 / empty stderr; no NA in used columns; the off arm must equal the frozen aggregate
  (every column except timestamp).
Output: results/wifi-std/arp-ratesweep-analysis/{cells.csv, REPORT.txt}
"""
import csv
import glob
import json
import math
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
W = ROOT / "results/wifi-std"
OUT = W / "arp-ratesweep-analysis"
FROZEN = ROOT / "analysis/bottleneck-characterisation/data-ratesweep/probe_aggregate.csv"
PROTOS, NS, RATES, SEEDS = ("olsr", "static"), (50, 75, 100), (16, 12, 8, 4), (20, 25, 30)


def one(p):
    with open(p, newline="") as f:
        return next(csv.DictReader(f))


def f(v, where):
    try:
        x = float(v)
    except (TypeError, ValueError):
        sys.exit(f"STOP: non-numeric {v!r} in {where}")
    if math.isnan(x) or math.isinf(x):
        sys.exit(f"STOP: NA {v!r} in {where}")
    return x


def load(arm, p, n, r, s):
    d = W / f"arp-ratesweep-{arm}" / f"b-{arm}_{p}_{n}_rate{r}_seed{s}"
    pv = json.loads((d / "provenance.json").read_text())
    if pv["exit_code"] != 0 or pv["stderr_bytes"] or pv.get("timed_out"):
        sys.exit(f"STOP: {d.name} exit {pv['exit_code']} stderr {pv['stderr_bytes']}")
    a, e = one(d / "probe_aggregate.csv"), one(d / "wifistd_ext.csv")
    with open(glob.glob(str(d / "pernode/*.csv"))[0], newline="") as fh:
        pn = [x for x in csv.DictReader(fh) if x["is_gateway"] == "0"]
    hop1 = [x for x in pn if 0 <= int(x["hop_to_gw"]) <= 1]
    mq_all = sum(f(x["mac_queue_drops"], d.name) for x in pn)
    mq_h1 = sum(f(x["mac_queue_drops"], d.name) for x in hop1)
    g = lambda row, k: f(row[k], f"{d.name}:{k}")
    return dict(agg=a, pdr=g(a, "pdr"), thr=g(a, "throughputKbps"), air=g(a, "gw_airtime_busy_frac"),
                macq=g(a, "total_mac_queue_drops"), retry=g(a, "total_max_retry_drops"),
                arp=g(e, "total_arp_l3_drops") + g(e, "total_arp_cache_drops"),
                share_drop=(mq_h1 / mq_all if mq_all > 0 else None), share_sens=len(hop1) / len(pn),
                wall=pv["wall_sec"])


def ms(v):
    return (st.mean(v), st.stdev(v) if len(v) > 1 else float("nan"))


def main():
    OUT.mkdir(exist_ok=True)
    with open(FROZEN, newline="") as fh:
        frozen = {(r["protocol"], int(r["nodes"]), int(float(r["offered_rate_kbps"])), int(r["seed"])): r
                  for r in csv.DictReader(fh)}
    R = {(arm, p, n, r, s): load(arm, p, n, r, s) for arm in ("off", "on") for p in PROTOS for n in NS
         for r in RATES for s in SEEDS}
    mism = []
    for (arm, p, n, r, s), x in R.items():
        if arm == "off":
            ref = frozen[(p, n, r, s)]
            for k in ref:
                if k != "timestamp" and ref[k] != x["agg"].get(k):
                    mism.append(f"{p} N={n} {r}kbps s{s} {k}: frozen {ref[k]} vs off {x['agg'].get(k)}")
    rows, lines = [], []
    for p in PROTOS:
        for n in NS:
            base = {arm: ms([R[(arm, p, n, 16, s)]["pdr"] for s in SEEDS])[0] for arm in ("off", "on")}
            base_thr = {arm: ms([R[(arm, p, n, 16, s)]["thr"] for s in SEEDS])[0] for arm in ("off", "on")}
            for arm in ("off", "on"):
                mono = sum(all(R[(arm, p, n, a, s)]["pdr"] <= R[(arm, p, n, b, s)]["pdr"]
                               for a, b in zip(RATES, RATES[1:])) for s in SEEDS)
                for r in RATES:
                    xs = [R[(arm, p, n, r, s)] for s in SEEDS]
                    pdr, thr, air = ms([x["pdr"] for x in xs]), ms([x["thr"] for x in xs]), ms([x["air"] for x in xs])
                    sd = [x["share_drop"] for x in xs if x["share_drop"] is not None]
                    ratio = (st.mean(sd) / st.mean([x["share_sens"] for x in xs])) if sd else float("nan")
                    row = dict(protocol=p, N=n, rate_kbps=r, arm=arm, n_seeds=len(xs),
                               pdr_mean_pct=round(pdr[0], 2), pdr_sd_pp=round(pdr[1], 2),
                               delta_pdr_vs16_pp=round(pdr[0] - base[arm], 2),
                               thr_mean_kbps=round(thr[0], 1), thr_sd_kbps=round(thr[1], 1),
                               thr_change_vs16_pct=round(100 * (thr[0] / base_thr[arm] - 1), 1),
                               gw_airtime_mean=round(air[0], 4), gw_airtime_sd=round(air[1], 4),
                               macq_drops_mean_pkts=round(st.mean(x["macq"] for x in xs), 1),
                               retry_drops_mean_pkts=round(st.mean(x["retry"] for x in xs), 1),
                               arp_drops_mean_pkts=round(st.mean(x["arp"] for x in xs), 1),
                               macq_hop1_conc_ratio=round(ratio, 2), seeds_with_macq_drops=len(sd),
                               pdr_monotonic_seeds=f"{mono}/3", wall_mean_min=round(st.mean(x["wall"] for x in xs) / 60, 1))
                    rows.append(row)
    with open(OUT / "cells.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    rep = ["ARP study -- Phase I rate sweep, 802.11b, ARP fix off vs on (3 seeds per cell: 20, 25, 30)", "",
           f"Off arm vs frozen data-ratesweep: {'all 72 runs identical (every column except timestamp)' if not mism else f'{len(mism)} MISMATCHES'}"]
    rep += [f"  {m}" for m in mism[:20]]
    rep.append("")
    rep.append("proto  N   rate | PDR % off / on (dPDR vs16 pp off / on) | thr kbps off / on | gw air off / on | "
               "macQ pkts off / on | ARP pkts off | conc. ratio off / on | monotonic off / on")
    by = {(r["protocol"], r["N"], r["rate_kbps"], r["arm"]): r for r in rows}
    for p in PROTOS:
        for n in NS:
            for r in RATES:
                a, b = by[(p, n, r, "off")], by[(p, n, r, "on")]
                rep.append(f"{p:6s} {n:3d} {r:3d}  | {a['pdr_mean_pct']:6.2f} / {b['pdr_mean_pct']:6.2f} "
                           f"({a['delta_pdr_vs16_pp']:+6.2f} / {b['delta_pdr_vs16_pp']:+6.2f}) | "
                           f"{a['thr_mean_kbps']:6.1f} / {b['thr_mean_kbps']:6.1f} | {a['gw_airtime_mean']:.3f} / "
                           f"{b['gw_airtime_mean']:.3f} | {a['macq_drops_mean_pkts']:8.0f} / {b['macq_drops_mean_pkts']:8.0f} | "
                           f"{a['arp_drops_mean_pkts']:7.0f} | {a['macq_hop1_conc_ratio']:.2f} / {b['macq_hop1_conc_ratio']:.2f} | "
                           f"{a['pdr_monotonic_seeds']} / {b['pdr_monotonic_seeds']}")
    (OUT / "REPORT.txt").write_text("\n".join(rep) + "\n")
    print("\n".join(rep))
    sys.exit(1 if mism else 0)


if __name__ == "__main__":
    main()
