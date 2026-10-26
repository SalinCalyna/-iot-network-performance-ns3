#!/usr/bin/env python3
"""Build the dashboard data for the N = 100 uniform random risk-placement study (read-only on results/ and analysis/).

    python3 -I -B experiments/wifi6-risk/build_site_randplace.py <site dir>

Writes <site>/data/wifi6-randplace.json. Every number is read from:
  analysis/wifi6-randplace-report/analyze_out/pilot_runs.csv, CHECKS.txt   (analyze_randplace.py, per-run metrics)
  analysis/wifi6-randplace-report/stats/*.csv                             (analyze_randplace_stats.py)
  results/wifi6-risk/n100-randplace-v2-20261026T032146/{batch,preregistration}.json
Cross-checks before anything is written (any mismatch stops the build): every per-protocol mean and every paired mean
difference in stats/ is recomputed from pilot_runs.csv; the 12 draws, the on-tree set and the 72 + 18 run counts match
the design. Source files and their sha256 are listed in the JSON.
"""
import csv
import hashlib
import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REP = ROOT / "analysis/wifi6-randplace-report"
BATCH = ROOT / "results/wifi6-risk/n100-randplace-v2-20261026T032146"
PROTOS = ("static", "riskaware", "olsr")
LABEL = {"static": "Static", "riskaware": "Risk-Aware", "olsr": "OLSR"}
RATES = (8, 32)
METRICS = [("exposure_rate_pct", "Risk exposure", "%", 2), ("pdr_nominal_pct", "Nominal PDR", "%", 2),
           ("delay_p50_ms", "Delay p50", "ms", 1), ("delay_p95_ms", "Delay p95", "ms", 1),
           ("gw_airtime", "Gateway airtime", "fraction", 3), ("mpdu_retry_drop", "MAC retry-limit drops", "MPDUs", 0),
           ("risk_dropped_pkts", "Risk drops", "pkts", 0), ("sink_thr_kbps", "Throughput", "kbps", 1)]
SRC = {}


def read(p):
    p = Path(p)
    SRC[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return p.read_text()


def rows(p):
    return list(csv.DictReader(read(p).splitlines()))


def close(a, b, tol=1e-9):
    return abs(float(a) - float(b)) <= tol * max(1.0, abs(float(b)))


def main():
    site = Path(sys.argv[1])
    errs = []
    runs = rows(REP / "analyze_out/pilot_runs.csv")
    checks = read(REP / "analyze_out/CHECKS.txt").splitlines()[0]
    batch = json.loads(read(BATCH / "batch.json"))
    pre = json.loads(read(BATCH / "preregistration.json"))
    sp = rows(REP / "stats/stats_by_protocol.csv")
    pd = rows(REP / "stats/paired_differences.csv")
    cd = rows(REP / "stats/conditional_on_tree.csv")
    kc = rows(REP / "stats/k0_cost.csv")
    sc = rows(REP / "stats/subtree_compare.csv")

    k3 = {(r["protocol"], int(r["rate_kbps"]), int(r["seed"]), int(r["place"])): r
          for r in runs if r["k"] == "3" and r["place"] != "subtree"}
    k0 = [r for r in runs if r["k"] == "0"]
    draws = sorted({(s, p) for (_, _, s, p) in k3})
    if len(k3) != 72 or len(k0) != 18 or len(draws) != 12:
        errs.append(f"run counts: {len(k3)} k=3, {len(k0)} k=0, {len(draws)} draws")
    on_tree = {d for d in draws if int(k3[("static", 8, *d)]["srcs_exposed_installed"]) > 0}

    # cross-check stats/ against pilot_runs.csv
    for r in sp:
        for m, *_ in METRICS:
            v = [float(k3[(r["protocol"], int(r["rate_kbps"]), s, p)][m]) for s, p in draws]
            if not close(st.mean(v), r[m + "_mean"]) or not close(st.stdev(v), r[m + "_sd"]):
                errs.append(f"stats_by_protocol {r['rate_kbps']} {r['protocol']} {m}")
    for r in pd:
        a, b, rate, m = r["A"], r["B"], int(r["rate_kbps"]), r["metric"]
        d = [float(k3[(a, rate, s, p)][m]) - float(k3[(b, rate, s, p)][m]) for s, p in draws]
        if not close(st.mean(d), r["diff_mean"]) or sum(x == 0 for x in d) != int(r["draws_equal"]):
            errs.append(f"paired {rate} {a}-{b} {m}")
    # every metric of Risk-Aware equals Static's in the off-tree draws (identical runs)
    for s, p in draws:
        if (s, p) in on_tree:
            continue
        for rate in RATES:
            for m, *_ in METRICS:
                if float(k3[("riskaware", rate, s, p)][m]) != float(k3[("static", rate, s, p)][m]):
                    errs.append(f"off-tree draw {s}/{p} {rate} kbps {m}: Risk-Aware != Static")
    if len(on_tree) != 5:
        errs.append(f"on-tree draws: {len(on_tree)}")
    if "1197 passed, 0 failed" not in checks:
        errs.append("CHECKS.txt: " + checks)
    if errs:
        sys.exit("STOP: " + "; ".join(errs[:20]))

    f = lambda x: float(x)
    keep = [m for m, *_ in METRICS]
    out = dict(
        generated_by="experiments/wifi6-risk/build_site_randplace.py",
        batch=str(BATCH.relative_to(ROOT)), checks=checks,
        design=dict(n_sensors=batch["n_sensors"], k=batch["num_high_risk"], rates_kbps=batch["rates_kbps"],
                    topology_seeds=batch["seeds"], placement_seeds=batch["placement_seeds"], placement=pre["placement"],
                    sim_time_s=batch["simTime_s"], binary_sha256=batch["binary_sha256"], source_sha256=batch["source_sha256"],
                    new_runs=len(k3), reused_k0_runs=len(k0)),
        protocols=[dict(key=p, label=LABEL[p]) for p in PROTOS],
        metrics=[dict(key=m, label=l, unit=u, digits=d) for m, l, u, d in METRICS],
        draws=[dict(seed=s, place=p, high_risk_ids=k3[("static", 8, s, p)]["high_risk_ids"], on_tree=(s, p) in on_tree,
                    static_sources_exposed=int(k3[("static", 8, s, p)]["srcs_exposed_installed"]),
                    values={str(rate): {pr: {m: f(k3[(pr, rate, s, p)][m]) for m in keep} for pr in PROTOS} for rate in RATES})
               for s, p in draws],
        by_protocol=[dict(rate=int(r["rate_kbps"]), protocol=r["protocol"], n=int(r["n_draws"]),
                          zero_exposure_draws=int(r["draws_zero_exposure"]), exposure_max=f(r["exposure_max"]),
                          **{m: [f(r[m + "_mean"]), f(r[m + "_sd"]), f(r[m + "_ci95_lo"]), f(r[m + "_ci95_hi"])] for m in keep})
                     for r in sp],
        paired=[dict(rate=int(r["rate_kbps"]), A=r["A"], B=r["B"], metric=r["metric"], primary=r["primary"] == "1",
                     A_mean=f(r["A_mean"]), B_mean=f(r["B_mean"]),
                     diff=[f(r["diff_mean"]), f(r["diff_sd"]), f(r["diff_ci95_lo"]), f(r["diff_ci95_hi"])],
                     topo_ci=[f(r["topo_ci95_lo"]), f(r["topo_ci95_hi"])], topo_means=r["topo_means"],
                     higher=int(r["draws_A_higher"]), equal=int(r["draws_equal"]), lower=int(r["draws_A_lower"]),
                     p_signflip=f(r["p_signflip_exact"]), p_holm=f(r["p_signflip_holm"]) if r["p_signflip_holm"] else None,
                     cls=r["class"])
                for r in pd if r["metric"] in keep],
        conditional=[dict(rate=int(r["rate_kbps"]), condition=r["condition"], n=int(r["n_draws"]), A=r["A"], B=r["B"],
                          metric=r["metric"], mean=f(r["diff_mean"]), min=f(r["diff_min"]), max=f(r["diff_max"]),
                          higher=int(r["draws_A_higher"]), lower=int(r["draws_A_lower"])) for r in cd],
        k0_cost=[dict(rate=int(r["rate_kbps"]), protocol=r["protocol"], metric=r["metric"], k0=f(r["k0_mean"]),
                      k3=f(r["k3_mean"]), diff=f(r["diff_mean"])) for r in kc],
        subtree=[dict(rate=int(r["rate_kbps"]), protocol=r["protocol"], metric=r["metric"], subtree=f(r["subtree_mean"]),
                      uniform=f(r["uniform_mean"])) for r in sc],
        sources=SRC)
    (site / "data").mkdir(parents=True, exist_ok=True)
    (site / "data/wifi6-randplace.json").write_text(json.dumps(out, indent=1) + "\n")
    print(f"wrote {site / 'data/wifi6-randplace.json'}: {len(out['draws'])} draws, {len(out['paired'])} paired rows, "
          f"{len(SRC)} sources; cross-checks passed")


if __name__ == "__main__":
    main()
