#!/usr/bin/env python3
"""ARP study: Phase I rate sweep (802.11b), ARP fix ON (new runs) vs the frozen original (= ARP fix off).

    python3 -I -B experiments/wifi-std/analyze_arp_ratesweep_vs_frozen.py

Used instead of analyze_arp_ratesweep.py because the off arm was not re-run (2026-10-18 instruction: flag-on only).
The off arm is the frozen data; arp-phase1-off showed iot-network-wifi-std-arp.cc with the flag off reproduces it
exactly (14 runs, every compared value identical).

Inputs (read-only):
  on : results/wifi-std/arp-ratesweep-on/ (72 runs, seeds 20/25/30)
  off: analysis/bottleneck-characterisation/data-ratesweep/probe_aggregate.csv (72 rows)
       per-node (MAC-queue drop by hop) for off exists only at 16 kbps (data/pernode, the §10 probe, identical
       aggregate) and 4 kbps (data-ratesweep/pernode, overwritten by the last rate run); 12 and 8 kbps -> n/a.
Concentration ratio (Phase I Eq. 3-8): mean over seeds of (share of sensor MAC-queue drops at hop <= 1) divided by
  mean share of sensors at hop <= 1; seeds without MAC-queue drops are left out of the drop-share mean and counted.
NB MAC-queue drops count every MPDU, including routing control and ARP frames.
Output: results/wifi-std/arp-ratesweep-analysis/{cells_vs_frozen.csv, REPORT_vs_frozen.txt}
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
BC = ROOT / "analysis/bottleneck-characterisation"
PROTOS, NS, RATES, SEEDS = ("olsr", "static"), (50, 75, 100), (16, 12, 8, 4), (20, 25, 30)


def num(v, where):
    try:
        x = float(v)
    except (TypeError, ValueError):
        sys.exit(f"STOP: non-numeric {v!r} in {where}")
    if math.isnan(x) or math.isinf(x):
        sys.exit(f"STOP: NA {v!r} in {where}")
    return x


def hop_shares(pernode_csv, where):
    with open(pernode_csv, newline="") as fh:
        rows = list(csv.DictReader(fh))
    pn = [x for x in rows if x["is_gateway"] == "0"]
    mq_total = sum(num(x["mac_queue_drops"], where) for x in rows)   # incl. gateway, = aggregate total
    hop1 = [x for x in pn if 0 <= int(x["hop_to_gw"]) <= 1]
    mq_all = sum(num(x["mac_queue_drops"], where) for x in pn)
    mq_h1 = sum(num(x["mac_queue_drops"], where) for x in hop1)
    return (mq_h1 / mq_all if mq_all > 0 else None), len(hop1) / len(pn), mq_total


def load_on(p, n, r, s):
    d = W / "arp-ratesweep-on" / f"b-on_{p}_{n}_rate{r}_seed{s}"
    pv = json.loads((d / "provenance.json").read_text())
    if pv["exit_code"] != 0 or pv["stderr_bytes"] or pv.get("timed_out"):
        sys.exit(f"STOP: {d.name} exit {pv['exit_code']} stderr {pv['stderr_bytes']}")
    with open(d / "probe_aggregate.csv", newline="") as fh:
        a = next(csv.DictReader(fh))
    with open(d / "wifistd_ext.csv", newline="") as fh:
        e = next(csv.DictReader(fh))
    sd, ss, mq_pn = hop_shares(glob.glob(str(d / "pernode/*.csv"))[0], d.name)
    g = lambda row, k: num(row[k], f"{d.name}:{k}")
    return dict(pdr=g(a, "pdr"), thr=g(a, "throughputKbps"), air=g(a, "gw_airtime_busy_frac"),
                macq=g(a, "total_mac_queue_drops"), retry=g(a, "total_max_retry_drops"),
                arp=g(e, "total_arp_l3_drops") + g(e, "total_arp_cache_drops"), share_drop=sd, share_sens=ss,
                wall=pv["wall_sec"])


def main():
    OUT.mkdir(exist_ok=True)
    with open(BC / "data-ratesweep/probe_aggregate.csv", newline="") as fh:
        frozen = {(r["protocol"], int(r["nodes"]), int(float(r["offered_rate_kbps"])), int(r["seed"])): r
                  for r in csv.DictReader(fh)}
    off = {}
    for (p, n, r, s), a in frozen.items():
        w = f"frozen {p} {n} {r} s{s}"
        x = dict(pdr=num(a["pdr"], w), thr=num(a["throughputKbps"], w), air=num(a["gw_airtime_busy_frac"], w),
                 macq=num(a["total_mac_queue_drops"], w), retry=num(a["total_max_retry_drops"], w), arp=None,
                 share_drop=None, share_sens=None, hop_ok=False)
        pn = {16: BC / f"data/pernode/probe_{p}_{n}_high_seed{s}.csv",
              4: BC / f"data-ratesweep/pernode/probe_{p}_{n}_high_seed{s}.csv"}.get(r)
        if pn is not None:
            sd, ss, mq_pn = hop_shares(pn, w)
            if abs(mq_pn - x["macq"]) > 0.5:   # per-node file must belong to this exact run
                sys.exit(f"STOP: {pn.name} MAC-queue sum {mq_pn} != aggregate {x['macq']} ({w})")
            x.update(share_drop=sd, share_sens=ss, hop_ok=True)
        off[(p, n, r, s)] = x
    on = {(p, n, r, s): load_on(p, n, r, s) for p in PROTOS for n in NS for r in RATES for s in SEEDS}
    for x in on.values():
        x["hop_ok"] = True

    def cell(arm, p, n, r):
        xs = [arm[(p, n, r, s)] for s in SEEDS]
        m = lambda k: st.mean(x[k] for x in xs)
        sdv = lambda k: st.stdev(x[k] for x in xs)
        ratio, nd = float("nan"), 0
        if all(x["hop_ok"] for x in xs):
            sd = [x["share_drop"] for x in xs if x["share_drop"] is not None]
            nd = len(sd)
            if sd:
                ratio = st.mean(sd) / st.mean(x["share_sens"] for x in xs)
        return dict(pdr=m("pdr"), pdr_sd=sdv("pdr"), thr=m("thr"), air=m("air"), air_sd=sdv("air"),
                    macq=m("macq"), retry=m("retry"),
                    arp=(m("arp") if xs[0]["arp"] is not None else float("nan")), ratio=ratio, nd=nd,
                    hop=all(x["hop_ok"] for x in xs),
                    mono=sum(all(arm[(p, n, a, s)]["pdr"] <= arm[(p, n, b, s)]["pdr"]
                                 for a, b in zip(RATES, RATES[1:])) for s in SEEDS),
                    wall=(m("wall") / 60 if "wall" in xs[0] else float("nan")))

    rows, rep = [], ["Phase I rate sweep, 802.11b: frozen original (ARP fix off) vs re-run with --arpPrepopulate=1 (on)",
                     "3 seeds per cell (20, 25, 30); rate = offered rate in kbps per sensor; dPDR in pp vs 16 kbps of the same arm",
                     "MAC-queue drops in packets per run (every MPDU, incl. control/ARP); conc. = MAC-queue drop concentration at hop<=1",
                     "(off per-node data exists only at 16 and 4 kbps)", "",
                     "proto  N   rate | PDR % off / on   | dPDR pp off / on  | thr kbps off / on | gw air off / on | "
                     "macQ off / on   | ARP on | conc. off / on (seeds w/ drops) | monotonic off / on | wall on min"]
    for p in PROTOS:
        for n in NS:
            b_off, b_on = cell(off, p, n, 16), cell(on, p, n, 16)
            for r in RATES:
                a, b = cell(off, p, n, r), cell(on, p, n, r)
                da, db = a["pdr"] - b_off["pdr"], b["pdr"] - b_on["pdr"]
                rows.append(dict(protocol=p, N=n, rate_kbps=r, n_seeds=3,
                                 pdr_off_pct=round(a["pdr"], 2), pdr_on_pct=round(b["pdr"], 2),
                                 pdr_sd_off_pp=round(a["pdr_sd"], 2), pdr_sd_on_pp=round(b["pdr_sd"], 2),
                                 dpdr_vs16_off_pp=round(da, 2), dpdr_vs16_on_pp=round(db, 2),
                                 on_minus_off_pp=round(b["pdr"] - a["pdr"], 2),
                                 thr_off_kbps=round(a["thr"], 1), thr_on_kbps=round(b["thr"], 1),
                                 thr_change_vs16_off_pct=round(100 * (a["thr"] / b_off["thr"] - 1), 1),
                                 thr_change_vs16_on_pct=round(100 * (b["thr"] / b_on["thr"] - 1), 1),
                                 gw_air_off=round(a["air"], 4), gw_air_on=round(b["air"], 4),
                                 macq_off_pkts=round(a["macq"], 1), macq_on_pkts=round(b["macq"], 1),
                                 retry_off_pkts=round(a["retry"], 1), retry_on_pkts=round(b["retry"], 1),
                                 arp_on_pkts=round(b["arp"], 1),
                                 conc_off=(round(a["ratio"], 2) if a["hop"] else ""), conc_on=round(b["ratio"], 2),
                                 seeds_macq_off=(a["nd"] if a["hop"] else ""), seeds_macq_on=b["nd"],
                                 monotonic_off=f"{a['mono']}/3", monotonic_on=f"{b['mono']}/3",
                                 wall_on_min=round(b["wall"], 1)))
                co = f"{a['ratio']:.2f}({a['nd']})" if a["hop"] else "n/a"
                rep.append(f"{p:6s} {n:3d} {r:3d}  | {a['pdr']:6.2f} / {b['pdr']:6.2f} | {da:+6.2f} / {db:+6.2f} | "
                           f"{a['thr']:6.1f} / {b['thr']:6.1f} | {a['air']:.3f} / {b['air']:.3f} | "
                           f"{a['macq']:7.0f} / {b['macq']:7.0f} | {b['arp']:6.0f} | {co:>9s} / {b['ratio']:.2f}({b['nd']}) | "
                           f"{a['mono']}/3 / {b['mono']}/3 | {b['wall']:.1f}")
    with open(OUT / "cells_vs_frozen.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (OUT / "REPORT_vs_frozen.txt").write_text("\n".join(rep) + "\n")
    print("\n".join(rep))


if __name__ == "__main__":
    main()
