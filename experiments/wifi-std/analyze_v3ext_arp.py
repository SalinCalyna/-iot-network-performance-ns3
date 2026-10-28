#!/usr/bin/env python3
"""ARP effect on the Table 4-2 baseline (static mobility only): v3-ext (ARP fix off) vs iot-network-wifi-std-arp.cc
--standard=80211b --arpPrepopulate=1 (on).

    python3 -I -B experiments/wifi-std/analyze_v3ext_arp.py

off: results/v3-ext/<p>_<N>_<traffic>_static.csv, seeds 20-30 (R0: -arp.cc flag off reproduces these exactly,
     results/wifi-std/arp-r0-off/README.md)
on : low/medium -> results/wifi-std/arp-a2-on (seeds 20/25/30)
     high       -> arp-a2-on (20/25/30) + arp-a1-on (other seeds) + arp-b-on-os (OLSR/Static N 50/75/100, other
                   seeds; identical argv, checked here; the A2/b-on-os overlap is checked byte-identical)
Traffic labels: low = 4 kbps (run as --trafficLevel=high --offeredRateKbps=4, always labelled low), medium = 8, high = 16.
Only PDR and ThroughputKbps are used (PathChanges and UnreachableSensors from -arp.cc are never used).
95% CI = t(0.975, n-1) * sd / sqrt(n). dPDR = on - off, paired by seed (same positions per seed), with paired CI.
Output: results/wifi-std/v3ext-arp-analysis/{cells.csv, pooled.csv, ranking.csv, REPORT.txt}
"""
import csv
import json
import math
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
W, V3 = ROOT / "results/wifi-std", ROOT / "results/v3-ext"
OUT = W / "v3ext-arp-analysis"
PROTOS, NS, TRAFFIC = ("aodv", "olsr", "static"), (10, 20, 30, 50, 75, 100), ("low", "medium", "high")
RATE = {"low": "4", "medium": "8", "high": "16"}
S3, S11 = (20, 25, 30), tuple(range(20, 31))
T975 = {2: 4.303, 8: 2.306, 10: 2.228}


def num(v, where):
    try:
        x = float(v)
    except (TypeError, ValueError):
        sys.exit(f"STOP: non-numeric {v!r} in {where}")
    if math.isnan(x) or math.isinf(x):
        sys.exit(f"STOP: NA in {where}")
    return x


def rows(p):
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


def ci(xs):
    return T975[len(xs) - 1] * st.stdev(xs) / math.sqrt(len(xs))


def on_dir(p, n, t, s):
    if t != "high" or s in S3:
        return W / "arp-a2-on" / f"b-on_{p}_{n}_{t}_seed{s}"
    if p != "aodv" and n >= 50:
        return W / "arp-b-on-os" / f"b-on_{p}_{n}_rate16_seed{s}"
    return W / "arp-a1-on" / f"b-on_{p}_{n}_high_seed{s}"


def load_on(p, n, t, s):
    d = on_dir(p, n, t, s)
    pv = json.loads((d / "provenance.json").read_text())
    if pv["exit_code"] != 0 or pv["stderr_bytes"] or pv.get("timed_out"):
        sys.exit(f"STOP: {d.name} exit {pv['exit_code']} stderr {pv['stderr_bytes']}")
    want = ["--standard=80211b", f"--protocol={p}", f"--nSensors={n}",
            "--trafficLevel=" + ("medium" if t == "medium" else "high"), f"--seed={s}"]
    want += ([] if t == "medium" else [f"--offeredRateKbps={RATE[t]}"]) + ["--arpPrepopulate=1"]
    if pv["argv"][1:-1] != want:
        sys.exit(f"STOP: {d} argv {pv['argv'][1:-1]} != {want}")
    a = rows(d / "probe_aggregate.csv")[0]
    e = rows(d / "wifistd_ext.csv")[0]
    if a["offered_rate_kbps"] != RATE[t] or e["arp_prepopulate"] != "1":
        sys.exit(f"STOP: {d.name} rate {a['offered_rate_kbps']} arp_prepopulate {e['arp_prepopulate']}")
    arp = num(e["total_arp_l3_drops"], d.name) + num(e["total_arp_cache_drops"], d.name)
    return dict(pdr=num(a["pdr"], d.name), thr=num(a["throughputKbps"], d.name), arp=arp,
                air=num(a["gw_airtime_busy_frac"], d.name), wall=pv["wall_sec"])


def load_off(p, n, t):
    f = V3 / f"{p}_{n}_{t}_static.csv"
    by = {}
    for r in rows(f):
        s = int(r["Seed"])
        if s in S11:
            if s in by:
                sys.exit(f"STOP: duplicate seed {s} in {f.name}")
            if r["TrafficLevel"] != t or r["DataRate"] != RATE[t] + "kbps" or r["MobilityMode"] != "static":
                sys.exit(f"STOP: {f.name} seed {s} labels {r['TrafficLevel']}/{r['DataRate']}/{r['MobilityMode']}")
            by[s] = dict(pdr=num(r["PDR"], f.name), thr=num(r["ThroughputKbps"], f.name))
    if set(by) != set(S11):
        sys.exit(f"STOP: {f.name} seeds {sorted(by)}")
    return by


def overlap_check():
    """A2 high seeds 20/25/30 vs arp-b-on-os (same argv): outputs must be identical."""
    bad = 0
    for p in ("olsr", "static"):
        for n in (50, 75, 100):
            for s in S3:
                a, b = W / "arp-a2-on" / f"b-on_{p}_{n}_high_seed{s}", W / "arp-b-on-os" / f"b-on_{p}_{n}_rate16_seed{s}"
                for f in ("stdout.log", "wifistd_ext.csv"):
                    bad += (a / f).read_bytes() != (b / f).read_bytes()
                strip = lambda p_: [r.split(",", 1)[1] for r in p_.read_text().splitlines()]
                bad += strip(a / "probe_aggregate.csv") != strip(b / "probe_aggregate.csv")
    if bad:
        sys.exit(f"STOP: A2/b-on-os overlap differs in {bad} files")
    return 18


def main():
    OUT.mkdir(exist_ok=True)
    nov = overlap_check()
    cells, rep, maxarp = [], [], 0.0
    data = {}
    for p in PROTOS:
        for n in NS:
            for t in TRAFFIC:
                seeds = S11 if t == "high" else S3
                off = load_off(p, n, t)
                on = {s: load_on(p, n, t, s) for s in seeds}
                maxarp = max(maxarp, max(x["arp"] for x in on.values()))
                data[(p, n, t)] = (off, on)
                po, pn = [off[s]["pdr"] for s in seeds], [on[s]["pdr"] for s in seeds]
                to, tn = [off[s]["thr"] for s in seeds], [on[s]["thr"] for s in seeds]
                d = [b - a for a, b in zip(po, pn)]
                po11 = [off[s]["pdr"] for s in S11]
                cells.append(dict(protocol=p, N=n, traffic=t, rate_kbps=RATE[t], n_seeds=len(seeds),
                                  pdr_off=st.mean(po), pdr_off_ci=ci(po), pdr_on=st.mean(pn), pdr_on_ci=ci(pn),
                                  dpdr=st.mean(d), dpdr_ci=ci(d),
                                  thr_off=st.mean(to), thr_off_ci=ci(to), thr_on=st.mean(tn), thr_on_ci=ci(tn),
                                  dthr=st.mean(tn) - st.mean(to),
                                  pdr_off_11seeds=st.mean(po11), pdr_off_11seeds_ci=ci(po11),
                                  gw_air_on=st.mean(x["air"] for x in on.values()),
                                  wall_on_min=st.mean(x["wall"] for x in on.values()) / 60,
                                  arp_on_max=max(x["arp"] for x in on.values())))
    pooled = []
    for p in PROTOS:
        for n in NS:
            po = [data[(p, n, t)][0][s]["pdr"] for t in TRAFFIC for s in S3]
            pn = [data[(p, n, t)][1][s]["pdr"] for t in TRAFFIC for s in S3]
            to = [data[(p, n, t)][0][s]["thr"] for t in TRAFFIC for s in S3]
            tn = [data[(p, n, t)][1][s]["thr"] for t in TRAFFIC for s in S3]
            d = [b - a for a, b in zip(po, pn)]
            pooled.append(dict(protocol=p, N=n, pooled="low+medium+high, static, seeds 20/25/30", n_runs=9,
                               pdr_off=st.mean(po), pdr_off_ci=ci(po), pdr_on=st.mean(pn), pdr_on_ci=ci(pn),
                               dpdr=st.mean(d), dpdr_ci=ci(d), thr_off=st.mean(to), thr_on=st.mean(tn)))
    rank = []
    keyed = {(c["protocol"], c["N"], c["traffic"]): c for c in cells}
    keyp = {(c["protocol"], c["N"]): c for c in pooled}
    for n in NS:
        for t in TRAFFIC + ("pooled",):
            get = (lambda p, arm: keyp[(p, n)][arm]) if t == "pooled" else (lambda p, arm: keyed[(p, n, t)][arm])
            ro = " > ".join(sorted(PROTOS, key=lambda p: -get(p, "pdr_off")))
            rn = " > ".join(sorted(PROTOS, key=lambda p: -get(p, "pdr_on")))
            # top-two separation: do the 95% CIs of first and second overlap? (pooled: CI over 9 runs)
            def sep(arm):
                o = sorted(PROTOS, key=lambda p: -get(p, arm))
                a, b = o[0], o[1]
                return (get(a, arm) - get(a, arm + "_ci")) > (get(b, arm) + get(b, arm + "_ci"))
            rank.append(dict(N=n, traffic=t, order_off=ro, order_on=rn, changed=ro != rn,
                             top_separated_off=sep("pdr_off"), top_separated_on=sep("pdr_on")))
    for name, tab in (("cells", cells), ("pooled", pooled), ("ranking", rank)):
        with open(OUT / f"{name}.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(tab[0]))
            w.writeheader()
            for r in tab:
                w.writerow({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()})
    rep.append(f"v3-ext (off) vs -arp.cc --arpPrepopulate=1 (on), 802.11b, static mobility. "
               f"A2/b-on-os overlap identical: {nov}/18 runs. max ARP drops on: {maxarp:.0f} pkts/run")
    rep.append("PDR %, thr kbps; +-95% CI; dPDR pp paired on-off; n seeds (high 11, low/medium 3)")
    for c in cells:
        rep.append(f"{c['protocol']:6s} {c['N']:3d} {c['traffic']:6s} n={c['n_seeds']:2d} | PDR off {c['pdr_off']:6.2f}"
                   f"+-{c['pdr_off_ci']:5.2f} on {c['pdr_on']:6.2f}+-{c['pdr_on_ci']:5.2f} d {c['dpdr']:+6.2f}"
                   f"+-{c['dpdr_ci']:5.2f} | thr off {c['thr_off']:6.1f}+-{c['thr_off_ci']:5.1f} on "
                   f"{c['thr_on']:6.1f}+-{c['thr_on_ci']:5.1f} | air on {c['gw_air_on']:.3f} | wall {c['wall_on_min']:.1f}")
    rep.append("\npooled (9 runs = 3 traffic x 3 seeds)")
    for c in pooled:
        rep.append(f"{c['protocol']:6s} {c['N']:3d} | PDR off {c['pdr_off']:6.2f}+-{c['pdr_off_ci']:5.2f} on "
                   f"{c['pdr_on']:6.2f}+-{c['pdr_on_ci']:5.2f} d {c['dpdr']:+6.2f}+-{c['dpdr_ci']:5.2f} | "
                   f"thr off {c['thr_off']:6.1f} on {c['thr_on']:6.1f}")
    rep.append("\nranking by mean PDR (sep = top-1 CI does not overlap top-2 CI)")
    for r in rank:
        rep.append(f"N={r['N']:3d} {r['traffic']:6s} off {r['order_off']:22s} sep={r['top_separated_off']!s:5s} | "
                   f"on {r['order_on']:22s} sep={r['top_separated_on']!s:5s} {'CHANGED' if r['changed'] else ''}")
    (OUT / "REPORT.txt").write_text("\n".join(rep) + "\n")
    print("\n".join(rep))


if __name__ == "__main__":
    main()
