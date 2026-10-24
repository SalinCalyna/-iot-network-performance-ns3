#!/usr/bin/env python3
"""Checks and metrics for a risk-v2 N = 30 pilot batch (run_pilot_n30.py). Read-only on the runs.

    python3 -I -B experiments/wifi6-risk/analyze_pilot_n30.py <batch dir>

Works on whatever runs exist (subset or full); runs listed in <batch>/reuse_manifest.json are included. Writes into <batch>/analysis/:
  checks.csv, CHECKS.txt   per-run and cross-run checks (P0-P8 below)
  pilot_runs.csv           one row per run (sink-based metrics)
  pilot_by_config.csv      mean, SD, min, max over the seeds present, per (rate, protocol, k)
Checks
  P0 exit 0, empty stderr, all output files, binary = validated risk-v2
  P1 accounting: path records = app tx; fates partition; delivered + duplicates = sink rx; FlowMonitor rx <= sink
  P2 high-risk set = reference model (positions from the mt19937 replica, subtree rule); identical across
     protocols and loads for the same (seed, k); k = 0 -> no high-risk node
  P3 every risk drop: at a HIGH_RISK node, not the node's own packet, U reproduced by the reference hash, U < r
  P4 static / riskaware: every delivered packet followed the installed path; installed path = reference tree
     (BFS for static, risk-aware Dijkstra for riskaware); riskaware k = 0 packet paths = static k = 0
  P5 matching: for every run with the same (seed, rate), each source's first send time is identical and its send
     count is <= the nominal count. OnOffApplication fires its Tx trace only when Socket::Send succeeds
     (onoff-application.cc SendPacket); a send that fails because the source has no route (OLSR before its table
     holds the gateway) is retried at the next slot and never counted. nominal_offered = 30 x the scheduled sends per
     source (the maximum count seen for that (seed, rate), which must be the same for every source) and
     pdr_nominal_pct = delivered / nominal_offered are reported next to the app-tx PDR.
  P6 802.11ax: unicast data PSDUs only HE_SU / HeMcs0
Metrics: sink PDR = delivered_unique / app tx; throughput = delivered x 540 B x 8 / 270 s; delay percentiles are
nearest-rank over delivered packets; exposure = share of sent packets whose observed path crossed a HIGH_RISK
relay (risk_summary.csv). n = 3 seeds: descriptive only.
"""
import csv
import importlib.util
import json
import math
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("risk_ref", HERE / "risk_ref.py")
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)
spec2 = importlib.util.spec_from_file_location("run_validation", HERE / "run_validation.py")
V = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(V)

EXPECT_BIN = "d909f6de6233dfad80700b37beb71d4a62c2cd38f223b6acc70cbb40f1bb2407"
N = 30
FILES = ("probe_aggregate.csv", "risk_summary.csv", "risk_nodes.csv", "routes_planned.csv", "path_summary.csv",
         "packet_paths.csv", "risk_drops.csv", "wifi_readback.csv", "wifi_txvector_counts.csv", "wifistd_ext.csv",
         "ba_ssn_fix.csv")


def rows(p):
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


def pct(xs, q):
    return xs[max(0, math.ceil(q * len(xs)) - 1)] if xs else float("nan")


def fmt(path):
    return ">".join(map(str, path))


class Checks:
    def __init__(self):
        self.rows = []

    def add(self, test, subject, ok, detail=""):
        self.rows.append(dict(test=test, subject=subject, passed=int(bool(ok)), detail=str(detail)[:300]))


def parse(name):
    p, k, r, s = name.split("_")
    return p, int(k[1:]), int(r[4:]), int(s[4:])


def main():
    global N
    b = Path(sys.argv[1])
    if (b / "batch.json").exists():   # N from the batch (default 30)
        N = int(json.loads((b / "batch.json").read_text()).get("n_sensors", N))
    an = b / "analysis"
    an.mkdir(exist_ok=True)
    C = Checks()
    runs = sorted(d for d in (b / "runs").iterdir() if (d / "provenance.json").exists())
    if (b / "reuse_manifest.json").exists():   # runs reused from another batch (run_seeds10_n30.py), read in place
        root = HERE.parents[1]
        runs = sorted(runs + [root / m["path"] for m in json.loads((b / "reuse_manifest.json").read_text())],
                      key=lambda d: d.name)
    models, pos_cache = {}, {}
    out, sched, high_sets, rapaths = [], defaultdict(dict), defaultdict(dict), {}
    for d in runs:
        name = d.name
        proto, k, rate, seed = parse(name)
        pv = json.loads((d / "provenance.json").read_text())
        bafix_off = "--baSsnFix=0" in pv["argv"]   # the simulator writes no ba_ssn_fix.csv with the fix off
        miss = [f for f in FILES if not (d / f).exists() and not (bafix_off and f == "ba_ssn_fix.csv")]
        C.add("P0 run ok", name, pv["exit_code"] == 0 and pv["stderr_bytes"] == 0 and not miss
              and pv["binary_sha256"] == EXPECT_BIN, (pv["exit_code"], pv["stderr_bytes"], miss))
        if pv["exit_code"] != 0 or miss:
            continue
        a, s, e = rows(d / "probe_aggregate.csv")[0], rows(d / "risk_summary.csv")[0], rows(d / "wifistd_ext.csv")[0]
        pp = rows(d / "packet_paths.csv")
        app_tx, sink = int(s["app_tx_pkts"]), int(s["delivered_unique"])
        fates = defaultdict(int)
        for x in pp:
            fates[x["fate"]] += 1
        # P1
        C.add("P1 path records = app tx", name, len(pp) == app_tx == int(s["path_records"]), (len(pp), app_tx))
        C.add("P1 fates partition", name, sum(fates.values()) == app_tx and fates["delivered"] == sink
              and fates["risk_drop"] == int(s["risk_dropped_pkts"]) and fates["lost_other"] == int(s["lost_other_pkts"]),
              dict(fates))
        C.add("P1 delivered + duplicates = sink rx", name, sink + int(s["duplicates"]) == int(s["sink_rx_counter"]))
        C.add("P1 FlowMonitor rx <= sink", name, int(a["rxPkts"]) <= sink, (a["rxPkts"], sink))
        # P2
        if seed not in pos_cache:
            pos_cache[seed] = V.positions(seed, N)
        if (seed, k) not in models:
            models[(seed, k)] = R.model(pos_cache[seed], N, k=k, p_high=0.5, p_low=0.0, beta=10.0)
        m = models[(seed, k)]
        rn = {int(r["node_id"]): r for r in rows(d / "risk_nodes.csv")}
        sim_high = sorted(i for i, r in rn.items() if r["risk_state"] == "HIGH_RISK")
        C.add("P2 high-risk set = reference", name, sim_high == sorted(m["high"]) and len(sim_high) == k,
              (sim_high, sorted(m["high"])))
        C.add("P2 hop/degree = reference", name, all(int(rn[i]["hop_to_gw"]) == m["hop"][i]
                                                      and int(rn[i]["degree"]) == m["degree"][i] for i in range(N + 1)))
        high_sets[(seed, k)][name] = tuple(sim_high)
        # P3
        dr = rows(d / "risk_drops.csv")
        bad = [x for x in dr if int(x["node_id"]) not in m["high"] or x["node_id"] == x["src"]
               or abs(float(x["u"]) - R.risk_uniform(1, int(x["node_id"]), int(x["src"]), int(x["seq"]))) > 1e-12
               or float(x["u"]) >= 0.5]
        C.add("P3 risk drops valid", name, not bad and (k > 0 or not dr), (len(dr), bad[:2]))
        # P4
        if proto in ("static", "riskaware"):
            C.add("P4 delivered packets followed the installed path", name,
                  s["delivered_following_installed_path"] == s["delivered_checked_against_installed"],
                  (s["delivered_following_installed_path"], s["delivered_checked_against_installed"]))
            tree = m["parent"] if proto == "static" else m["ra_parent"]
            rp = {int(r["src"]): r for r in rows(d / "routes_planned.csv")}
            C.add("P4 installed path = reference tree", name,
                  all(rp[i]["installed_path"] == fmt([i] + R.path_of(tree, i, m["gw"])) for i in range(N) if m["hop"][i] >= 1))
            if k == 0:
                rapaths[(proto, rate, seed)] = [(x["src"], x["seq"], x["fate"], x["path"]) for x in pp]
        # P5
        per = defaultdict(list)
        for x in pp:
            per[x["src"]].append(float(x["tx_time_s"]))
        sched[(seed, rate)][name] = {k2: (len(v), min(v), max(v)) for k2, v in per.items()}
        # P6
        tv = rows(d / "wifi_txvector_counts.csv")
        uni = [r for r in tv if r["frame_class"] == "data_unicast"]
        C.add("P6 unicast data HE_SU HeMcs0", name, uni and all(r["preamble"] == "HE_SU" and r["mode"] == "HeMcs0" for r in uni))
        # metrics
        dl = sorted(float(x["delay_s"]) for x in pp if x["fate"] == "delivered")
        bar = sum(int(r["psdus"]) for r in tv if r["frame_type"] == "CTL_BACKREQ")
        rd = int(s["risk_dropped_pkts"])
        out.append(dict(
            run=name, protocol=proto, k=k, rate_kbps=rate, seed=seed, wall_min=round(pv["wall_sec"] / 60, 1),
            high_risk_ids=" ".join(map(str, sim_high)), app_tx=app_tx, sink_delivered=sink,
            sink_pdr_pct=100 * sink / app_tx, sink_thr_kbps=sink * 540 * 8 / 270 / 1000, lost_pkts=app_tx - sink,
            risk_dropped_pkts=rd, other_lost_pkts=int(s["lost_other_pkts"]),
            risk_share_of_loss_pct=100 * rd / (app_tx - sink) if app_tx > sink else 0.0,
            delay_p50_ms=1000 * pct(dl, .5), delay_p95_ms=1000 * pct(dl, .95), delay_p99_ms=1000 * pct(dl, .99),
            delay_max_s=dl[-1] if dl else float("nan"), gt1s=sum(x > 1 for x in dl), gt10s=sum(x > 10 for x in dl),
            mean_hops_delivered=float(s["mean_hops_delivered"]), exposure_rate_pct=float(s["exposure_rate_pct"]),
            high_risk_transits_per_pkt=float(s["mean_high_risk_transits_per_pkt"]),
            srcs_exposed_installed=s["srcs_exposed_installed"], srcs_avoided_by_riskaware=s["srcs_avoided_by_riskaware"],
            srcs_unavoidable=s["srcs_unavoidable"], fm_rx=int(a["rxPkts"]), sink_minus_fm=sink - int(a["rxPkts"]),
            duplicates=int(s["duplicates"]), gw_airtime=float(a["gw_airtime_busy_frac"]),
            mpdu_expired=int(e["total_dropped_mpdu_expired_lifetime"]), mpdu_retry_drop=int(e["total_dropped_mpdu_retry_limit"]),
            no_route_drops=int(a["total_ip_drop_no_route"]), ba_fix_events=0 if bafix_off else len(rows(d / "ba_ssn_fix.csv")), bar_psdus=bar))
    # cross-run checks
    for key, v in high_sets.items():
        C.add("P2 same high-risk set across protocols and loads", f"seed {key[0]} k {key[1]}", len(set(v.values())) == 1,
              sorted(set(v.values())))
    nominal = {}
    for key, v in sched.items():
        mx = {src: max(x[src][0] for x in v.values() if src in x) for src in {s2 for x in v.values() for s2 in x}}
        nominal[key] = max(mx.values())
        C.add("P5 one scheduled send count for every source", f"seed {key[0]} rate {key[1]}",
              len(set(mx.values())) == 1 and len(mx) == N, sorted(set(mx.values())))
        first = {json.dumps({s2: t[1] for s2, t in x.items()}, sort_keys=True) for x in v.values()}
        C.add("P5 identical first-send times across runs", f"seed {key[0]} rate {key[1]}", len(first) == 1, len(first))
        for name, x in v.items():
            C.add("P5 send count <= nominal", name, len(x) == N and all(t[0] <= nominal[key] for t in x.values()))
    for r in out:
        nom = N * nominal[(r["seed"], r["rate_kbps"])]
        r["nominal_offered"] = nom
        r["unsent_at_source"] = nom - r["app_tx"]
        r["pdr_nominal_pct"] = 100 * r["sink_delivered"] / nom
    for (proto, rate, seed), v in rapaths.items():
        if proto == "riskaware" and ("static", rate, seed) in rapaths:
            C.add("P4 riskaware k=0 packet paths = static k=0", f"rate {rate} seed {seed}", v == rapaths[("static", rate, seed)])
    with open(an / "checks.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["test", "subject", "passed", "detail"], lineterminator="\n")
        w.writeheader()
        w.writerows(C.rows)
    by = defaultdict(lambda: [0, 0])
    for r in C.rows:
        by[r["test"]][0 if r["passed"] else 1] += 1
    lines = [f"{b.name}: {len(runs)} runs; checks {sum(v[0] for v in by.values())} passed, {sum(v[1] for v in by.values())} failed"]
    lines += [f"  {'PASS' if v[1] == 0 else 'FAIL'}  {t}: {v[0]} passed, {v[1]} failed" for t, v in sorted(by.items())]
    lines += [f"  FAIL {r['test']} | {r['subject']} | {r['detail']}" for r in C.rows if not r["passed"]][:40]
    (an / "CHECKS.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    if not out:
        return 1
    keys = list(out[0])
    with open(an / "pilot_runs.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    num = [k2 for k2 in keys if isinstance(out[0][k2], (int, float)) and k2 not in ("k", "rate_kbps", "seed")]
    agg = []
    for cfg in sorted({(x["rate_kbps"], x["protocol"], x["k"]) for x in out}):
        xs = [x for x in out if (x["rate_kbps"], x["protocol"], x["k"]) == cfg]
        row = dict(rate_kbps=cfg[0], protocol=cfg[1], k=cfg[2], n_seeds=len(xs), seeds=" ".join(str(x["seed"]) for x in xs))
        for k2 in num:
            v = [float(x[k2]) for x in xs]
            row[k2 + "_mean"], row[k2 + "_sd"] = st.mean(v), (st.stdev(v) if len(v) > 1 else 0.0)
            row[k2 + "_min"], row[k2 + "_max"] = min(v), max(v)
        agg.append(row)
    with open(an / "pilot_by_config.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(agg[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(agg)
    return 0 if all(v[1] == 0 for v in by.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
