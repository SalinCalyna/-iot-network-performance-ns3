#!/usr/bin/env python3
"""Matched statistics for the PSU Phuket campus matrix (input: pilot_runs.csv written by analyze_campus.py).
Read-only. No third-party packages; statistical helpers reused unchanged from experiments/wifi6-risk/analyze_paired_stats.py.

    python3 -I -B experiments/campus-sim/analyze_campus_stats.py <batch dir> [--out=<dir>]

Design: one fixed campus topology (83 sensors + gateway). A draw = (risk placement, seed); placements with k = 3 are
subtree (simulator rule, worst case for Static) and u101..u104 (uniform hash rule); seeds 1-3 are independent
replications (ns-3 random streams and risk-drop hash). Within a draw Static, Risk-Aware and OLSR share the topology,
traffic schedule (P5), risk set (P2) and every risk-drop decision, so protocol differences are paired per draw.
The k = 0 runs (no risk) are reported descriptively per protocol (3 seeds).
Statistics per rate, k = 3 (15 draws): per-protocol mean, SD, 95 % t interval; paired A - B per draw with 95 % t
interval (df = 14), exact sign-flip permutation p (2^15 patterns), exact Wilcoxon p, per-placement mean differences
and a placement-level 95 % t interval (n = 5, df = 4) as the cluster-conservative range. Holm adjustment of the
sign-flip p over the primary family: nominal PDR and exposure x 3 comparisons x 2 rates (12 tests).
Classification (fixed before the matrix finished):
  supported    primary metric, Holm p < 0.05, draw-level interval excludes 0, same sign in all 5 placements
  consistent   secondary metric meeting the same three criteria without Holm (exploratory)
  descriptive  everything else and every delay / hop metric (delivered packets only: survivorship)
  identical    all 15 differences are 0
Scope: one proposed campus layout, open-space radio model without buildings, uncalibrated. Results describe this
simulation, not campus performance, and do not generalise to other layouts.
Writes <out>/ (default <batch>/analysis/stats/): by_protocol.csv, paired.csv, per_placement.csv, k0_baseline.csv, STATS.txt
"""
import csv
import importlib.util
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("aps", HERE.parent / "wifi6-risk/analyze_paired_stats.py")
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)

PROTOS = ("static", "riskaware", "olsr")
LABEL = {"static": "Static", "riskaware": "Risk-Aware", "olsr": "OLSR"}
PAIRS = (("riskaware", "static"), ("riskaware", "olsr"), ("static", "olsr"))
METRICS = ("pdr_nominal_pct", "exposure_rate_pct", "sink_thr_kbps", "lost_pkts", "risk_dropped_pkts", "other_lost_pkts",
           "delay_p50_ms", "delay_p95_ms", "delay_p99_ms", "mean_hops_delivered", "gw_airtime", "mpdu_retry_drop",
           "mpdu_expired", "no_route_drops")
PRIMARY = ("pdr_nominal_pct", "exposure_rate_pct")


def write(path, rs):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rs[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rs)


def main():
    b = Path(sys.argv[1])
    opts = dict(a.split("=", 1) for a in sys.argv[2:] if a.startswith("--") and "=" in a)
    out = Path(opts.get("--out", b / "analysis/stats"))
    out.mkdir(parents=True, exist_ok=True)
    with open(b / "analysis/pilot_runs.csv", newline="") as f:
        R = list(csv.DictReader(f))
    runs = {(r["protocol"], int(r["rate_kbps"]), r["place"], int(r["seed"])): r for r in R}
    rates = sorted({int(r["rate_kbps"]) for r in R})
    draws = sorted({(r["place"], int(r["seed"])) for r in R if r["k"] == "3"})
    places = sorted({p for p, _ in draws}, key=lambda p: (p != "subtree", p))
    k0seeds = sorted({int(r["seed"]) for r in R if r["k"] == "0"})
    for rate in rates:
        for p in PROTOS:
            for d in draws:
                assert (p, rate, *d) in runs, f"missing run {p} {rate} {d}"
    lines = [f"{b.name}: {len(R)} runs; {len(draws)} matched k = 3 draws per rate ({len(places)} placements x "
             f"{len(draws) // max(1, len(places))} seeds); k = 0 baseline over seeds {k0seeds}", ""]
    bp, pr, pp, kb = [], [], [], []
    for rate in rates:
        for p in PROTOS:
            row = dict(rate_kbps=rate, protocol=p, n_draws=len(draws))
            for m in METRICS:
                mean, sd, lo, hi = S.ci95([float(runs[(p, rate, *d)][m]) for d in draws])
                row.update({f"{m}_mean": mean, f"{m}_sd": sd, f"{m}_ci95_lo": lo, f"{m}_ci95_hi": hi})
            ex = [float(runs[(p, rate, *d)]["exposure_rate_pct"]) for d in draws]
            row["zero_exposure_draws"] = sum(x == 0 for x in ex)
            bp.append(row)
            k0 = [runs[(p, rate, "none", s)] for s in k0seeds if (p, rate, "none", s) in runs]
            if k0:
                kb.append(dict(rate_kbps=rate, protocol=p, n_seeds=len(k0), **{f"{m}_mean": st.mean(float(x[m]) for x in k0) for m in METRICS},
                               **{f"{m}_min": min(float(x[m]) for x in k0) for m in ("pdr_nominal_pct", "delay_p95_ms", "gw_airtime")},
                               **{f"{m}_max": max(float(x[m]) for x in k0) for m in ("pdr_nominal_pct", "delay_p95_ms", "gw_airtime")}))
            for pl in places:
                v = [runs[(p, rate, pl, s)] for q, s in draws if q == pl]
                pp.append(dict(rate_kbps=rate, protocol=p, place=pl, n_seeds=len(v), high_risk_ids=v[0]["high_risk_ids"],
                               **{f"{m}_mean": st.mean(float(x[m]) for x in v) for m in ("pdr_nominal_pct", "exposure_rate_pct", "delay_p95_ms", "mean_hops_delivered", "gw_airtime")}))
        for a, c in PAIRS:
            for m in METRICS:
                diff = [float(runs[(a, rate, *d)][m]) - float(runs[(c, rate, *d)][m]) for d in draws]
                mean, sd, lo, hi = S.ci95(diff)
                by = defaultdict(list)
                for (pl, _), x in zip(draws, diff):
                    by[pl].append(x)
                pm = [st.mean(by[pl]) for pl in places]
                _, _, plo, phi = S.ci95(pm)
                pw, nnz, _ = S.wilcoxon_exact(diff)
                pr.append(dict(rate_kbps=rate, A=a, B=c, metric=m, primary=int(m in PRIMARY), n_draws=len(diff),
                               A_mean=st.mean(float(runs[(a, rate, *d)][m]) for d in draws), B_mean=st.mean(float(runs[(c, rate, *d)][m]) for d in draws),
                               diff_mean=mean, diff_sd=sd, diff_ci95_lo=lo, diff_ci95_hi=hi,
                               draws_A_higher=sum(x > 0 for x in diff), draws_equal=sum(x == 0 for x in diff), draws_A_lower=sum(x < 0 for x in diff),
                               p_signflip_exact=S.signflip_exact(diff), p_wilcoxon_exact=pw, wilcoxon_n_nonzero=nnz,
                               placement_means=" ".join(f"{pl}:{x:+.4g}" for pl, x in zip(places, pm)),
                               placement_same_sign=int(all(x > 0 for x in pm) or all(x < 0 for x in pm)),
                               placement_ci95_lo=plo, placement_ci95_hi=phi, p_signflip_holm="",
                               per_draw=" ".join(f"{pl}/{s}:{x:+.4g}" for (pl, s), x in zip(draws, diff))))
    fam = [i for i, x in enumerate(pr) if x["primary"] and x["draws_equal"] < x["n_draws"]]
    for i, adj in zip(fam, S.holm([pr[i]["p_signflip_exact"] for i in fam])):
        pr[i]["p_signflip_holm"] = adj
    for x in pr:
        crit = (x["diff_ci95_lo"] > 0 or x["diff_ci95_hi"] < 0) and x["placement_same_sign"] == 1
        if x["draws_equal"] == x["n_draws"]:
            x["class"] = "identical"
        elif x["metric"].startswith("delay") or x["metric"] == "mean_hops_delivered":
            x["class"] = "descriptive"
        elif x["primary"]:
            x["class"] = "supported" if crit and x["p_signflip_holm"] < 0.05 else "descriptive"
        else:
            x["class"] = "consistent" if crit and x["p_signflip_exact"] < 0.05 else "descriptive"
    write(out / "by_protocol.csv", bp)
    write(out / "paired.csv", pr)
    write(out / "per_placement.csv", pp)
    if kb:
        write(out / "k0_baseline.csv", kb)
    g = lambda r, m, d: f"{r[m + '_mean']:.{d}f} [{r[m + '_ci95_lo']:.{d}f}, {r[m + '_ci95_hi']:.{d}f}]"
    for rate in rates:
        lines.append(f"== {rate} kbps, k = 3: mean [95 % t interval] over {len(draws)} draws")
        for r in (x for x in bp if x["rate_kbps"] == rate):
            lines.append(f"  {LABEL[r['protocol']]:10s} PDR {g(r, 'pdr_nominal_pct', 2)} | exposure {g(r, 'exposure_rate_pct', 2)} (zero in {r['zero_exposure_draws']}) | "
                         f"thr {g(r, 'sink_thr_kbps', 1)} kbps | p95 {g(r, 'delay_p95_ms', 0)} ms | hops {g(r, 'mean_hops_delivered', 2)} | gw {g(r, 'gw_airtime', 3)}")
        for r in (x for x in kb if x["rate_kbps"] == rate):
            lines.append(f"  k = 0  {LABEL[r['protocol']]:10s} PDR {r['pdr_nominal_pct_mean']:.2f} (range {r['pdr_nominal_pct_min']:.2f}-{r['pdr_nominal_pct_max']:.2f}) | p95 {r['delay_p95_ms_mean']:.0f} ms | gw {r['gw_airtime_mean']:.3f}")
    lines += ["", "== paired A - B (draw-level 95 % interval; placement-level interval, n = 5; sign-flip p; Holm for primary)"]
    for x in pr:
        if x["metric"] in ("pdr_nominal_pct", "exposure_rate_pct", "sink_thr_kbps", "delay_p95_ms", "mean_hops_delivered", "gw_airtime", "mpdu_retry_drop"):
            h = f"{x['p_signflip_holm']:.3g}" if x["p_signflip_holm"] != "" else "-"
            lines.append(f"  {x['rate_kbps']:>2} kbps {LABEL[x['A']]:>10s}-{LABEL[x['B']]:<10s} {x['metric']:20s} {x['diff_mean']:+10.4g} "
                         f"[{x['diff_ci95_lo']:+.4g}, {x['diff_ci95_hi']:+.4g}] plc [{x['placement_ci95_lo']:+.4g}, {x['placement_ci95_hi']:+.4g}] "
                         f"A>B {x['draws_A_higher']} = {x['draws_equal']} A<B {x['draws_A_lower']} p={x['p_signflip_exact']:.3g} holm={h} -> {x['class']}")
    lines += ["", "== per placement (mean over seeds): PDR % / exposure %"]
    for rate in rates:
        for pl in places:
            v = {x["protocol"]: x for x in pp if x["rate_kbps"] == rate and x["place"] == pl}
            lines.append(f"  {rate:>2} kbps {pl:8s} high [{v['static']['high_risk_ids']}]  " + "  ".join(
                f"{LABEL[p]} {v[p]['pdr_nominal_pct_mean']:.2f} / {v[p]['exposure_rate_pct_mean']:.2f}" for p in PROTOS))
    (out / "STATS.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
