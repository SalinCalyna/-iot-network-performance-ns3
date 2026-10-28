#!/usr/bin/env python3
"""Table 4 (bottleneck, §10 cells) with the ARP fix on vs the frozen original (off).

    python3 -I -B experiments/wifi-std/analyze_table4_arp.py

off: analysis/final-report-data/bottleneck_results.csv (frozen, 16 cells, 11 seeds)
on : iot-network-wifi-std-arp.cc --standard=80211b --arpPrepopulate=1, OLSR/Static x N 30/50/75/100 x medium/high x
     seeds 20-30: arp-a2-on (seeds 20/25/30), high N=30 -> arp-a1-on, high N>=50 -> arp-b-on-os, medium -> arp-b1-on.
Concentration ratio exactly as analysis/bottleneck-characterisation/analyze_probe.py (lines 128-205): per seed,
  share of sensor MAC-queue drops at hop<=1 and share of sensors at hop<=1; ratio = mean(drop share over seeds with
  drops) / mean(sensor share over all seeds). Seeds without MAC-queue drops are counted (n_seeds_macq).
NB MAC-queue drops count every MPDU, incl. routing control and ARP frames (same counter as the frozen data).
95% CI = t(0.975, 10) * sd / sqrt(11).
Output: results/wifi-std/table4-arp-analysis/{table4_on_vs_off.csv, REPORT.txt}
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
OUT = W / "table4-arp-analysis"
OFF = ROOT / "analysis/final-report-data/bottleneck_results.csv"
SEEDS, T = tuple(range(20, 31)), 2.228


def num(v, where):
    try:
        x = float(v)
    except (TypeError, ValueError):
        sys.exit(f"STOP: non-numeric {v!r} in {where}")
    if math.isnan(x) or math.isinf(x):
        sys.exit(f"STOP: NA in {where}")
    return x


def run_dir(p, n, t, s):
    if s in (20, 25, 30):
        return W / "arp-a2-on" / f"b-on_{p}_{n}_{t}_seed{s}"
    if t == "medium":
        return W / "arp-b1-on" / f"b-on_{p}_{n}_medium_seed{s}"
    if n == 30:
        return W / "arp-a1-on" / f"b-on_{p}_30_high_seed{s}"
    return W / "arp-b-on-os" / f"b-on_{p}_{n}_rate16_seed{s}"


def load(p, n, t, s):
    d = run_dir(p, n, t, s)
    pv = json.loads((d / "provenance.json").read_text())
    if pv["exit_code"] != 0 or pv["stderr_bytes"] or pv.get("timed_out") or "--arpPrepopulate=1" not in pv["argv"]:
        sys.exit(f"STOP: {d.name} exit {pv['exit_code']} stderr {pv['stderr_bytes']} or flag off")
    want = ["--standard=80211b", f"--protocol={p}", f"--nSensors={n}", f"--trafficLevel={t}", f"--seed={s}"]
    want += (["--offeredRateKbps=16"] if t == "high" else []) + ["--arpPrepopulate=1"]
    if pv["argv"][1:-1] != want:
        sys.exit(f"STOP: {d} argv {pv['argv'][1:-1]} != {want}")
    with open(d / "probe_aggregate.csv", newline="") as fh:
        a = next(csv.DictReader(fh))
    with open(d / "wifistd_ext.csv", newline="") as fh:
        e = next(csv.DictReader(fh))
    pn = glob.glob(str(d / "pernode/*.csv"))
    if len(pn) != 1:
        sys.exit(f"STOP: {d.name} pernode files {pn}")
    with open(pn[0], newline="") as fh:
        rows = list(csv.DictReader(fh))
    sens = [r for r in rows if r["is_gateway"] == "0"]
    le1 = [r for r in sens if 0 <= int(float(r["hop_to_gw"])) <= 1]
    mq_all = sum(num(r["mac_queue_drops"], d.name) for r in sens)
    mq_le1 = sum(num(r["mac_queue_drops"], d.name) for r in le1)
    mq_tot = sum(num(r["mac_queue_drops"], d.name) for r in rows)
    g = lambda k: num(a[k], f"{d.name}:{k}")
    if abs(mq_tot - g("total_mac_queue_drops")) > 0.5:
        sys.exit(f"STOP: {d.name} per-node MAC-queue sum {mq_tot} != aggregate {g('total_mac_queue_drops')}")
    return dict(pdr=g("pdr"), thr=g("throughputKbps"), gw=g("gw_airtime_busy_frac"),
                ring1=g("ring1_airtime_busy_frac_mean"), macq=g("total_mac_queue_drops"), phyrx=g("total_phy_rx_drops"),
                no_route=g("total_ip_drop_no_route"), route_err=g("total_ip_drop_route_error"),
                arp=num(e["total_arp_l3_drops"], d.name) + num(e["total_arp_cache_drops"], d.name),
                f_nodes=len(le1) / len(sens), f_macq=(mq_le1 / mq_all if mq_all > 0 else None))


def ci(xs):
    return T * st.stdev(xs) / math.sqrt(len(xs))


def main():
    OUT.mkdir(exist_ok=True)
    with open(OFF, newline="") as fh:
        off = {(r["protocol"], int(r["N"]), r["traffic"]): r for r in csv.DictReader(fh)}
    out, rep = [], ["Table 4 (bottleneck): frozen original (off) vs --arpPrepopulate=1 (on), 802.11b, static, "
                    "11 seeds (20-30) per cell",
                    "PDR %, thr kbps, airtime 0-1 (+-95% CI on), MAC-queue/PHY-RX drops pkts/run, conc. x "
                    "(seeds with MAC-queue drops)", ""]
    maxarp = 0.0
    for p in ("olsr", "static"):
        for n in (30, 50, 75, 100):
            for t in ("medium", "high"):
                xs = [load(p, n, t, s) for s in SEEDS]
                maxarp = max(maxarp, max(x["arp"] for x in xs))
                m = lambda k: st.mean(x[k] for x in xs)
                fm = [x["f_macq"] for x in xs if x["f_macq"] is not None]
                conc = (st.mean(fm) / m("f_nodes")) if fm else float("nan")
                o = off[(p, n, t)]
                if int(o["n_seeds"]) != 11:
                    sys.exit(f"STOP: frozen {p} {n} {t} n_seeds {o['n_seeds']}")
                row = dict(protocol=p, N=n, traffic=t, n_seeds=11,
                           pdr_off=float(o["PDR_mean"]), pdr_on=m("pdr"), pdr_on_ci=ci([x["pdr"] for x in xs]),
                           thr_off=float(o["throughput_kbps"]), thr_on=m("thr"),
                           gw_air_off=float(o["gw_airtime"]), gw_air_on=m("gw"), gw_air_on_ci=ci([x["gw"] for x in xs]),
                           ring1_air_off=float(o["ring1_airtime"]), ring1_air_on=m("ring1"),
                           macq_off=float(o["mac_queue_drops_mean"]), macq_on=m("macq"),
                           phyrx_off=float(o["phy_rx_drops_mean"]), phyrx_on=m("phyrx"),
                           no_route_off=float(o["NO_ROUTE_mean"]), no_route_on=m("no_route"),
                           route_err_off=float(o["ROUTE_ERROR_mean"]), route_err_on=m("route_err"),
                           frac_nodes_hop_le1=m("f_nodes"), frac_nodes_hop_le1_off=float(o["frac_nodes_hop_le1"]),
                           frac_macq_hop_le1_off=float(o["frac_macq_hop_le1"]),
                           frac_macq_hop_le1_on=(st.mean(fm) if fm else float("nan")),
                           conc_off=float(o["macq_concentration_ratio"]), conc_on=conc, n_seeds_macq_on=len(fm),
                           arp_on_max=max(x["arp"] for x in xs))
                out.append(row)
                rep.append(f"{p:6s} {n:3d} {t:6s} | PDR {row['pdr_off']:6.2f} -> {row['pdr_on']:6.2f}+-{row['pdr_on_ci']:4.2f}"
                           f" | thr {row['thr_off']:6.1f} -> {row['thr_on']:6.1f} | gw air {row['gw_air_off']:.3f} -> "
                           f"{row['gw_air_on']:.3f}+-{row['gw_air_on_ci']:.3f} | ring1 {row['ring1_air_off']:.3f} -> "
                           f"{row['ring1_air_on']:.3f} | macQ {row['macq_off']:7.0f} -> {row['macq_on']:7.0f} | "
                           f"conc {row['conc_off']:.2f} -> {row['conc_on']:.2f}({len(fm)}) | NO_ROUTE "
                           f"{row['no_route_off']:.0f} -> {row['no_route_on']:.0f}")
    rep.insert(2, f"hop<=1 sensor share check (on vs frozen) max |diff| = "
                  f"{max(abs(r['frac_nodes_hop_le1'] - r['frac_nodes_hop_le1_off']) for r in out):.4f}; "
                  f"max ARP drops on = {maxarp:.0f} pkts/run")
    with open(OUT / "table4_on_vs_off.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]), lineterminator="\n")
        w.writeheader()
        for r in out:
            w.writerow({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()})
    (OUT / "REPORT.txt").write_text("\n".join(rep) + "\n")
    print("\n".join(rep))


if __name__ == "__main__":
    main()
