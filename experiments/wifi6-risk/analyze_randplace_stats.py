#!/usr/bin/env python3
"""Draw-paired statistics for the risk-v2 N = 100 random-placement batch (input: pilot_runs.csv written by
analyze_randplace.py). Read-only on the runs and on every existing analysis. No third-party packages.

    python3 -I -B experiments/wifi6-risk/analyze_randplace_stats.py <pilot_runs.csv> --out=<dir>
        [--subtree8=<pilot_runs.csv>] [--subtree32=<pilot_runs.csv>]

Unit of analysis: a draw = (topology seed, placement seed), 3 x 4 = 12 per rate. Within a draw Static, Risk-Aware
and OLSR share positions, traffic schedule (P5) and the preregistered high-risk set (P2), so protocol differences
are paired per draw. Draws are nested in 3 topologies (4 placements each), so they are not fully independent.

Statistics (helpers reused from analyze_paired_stats.py, unchanged):
  - per (protocol, rate): mean, SD, 95 % t interval over the 12 draws; share of draws with zero exposure (H4)
  - paired differences A - B per draw: mean, SD, 95 % t interval (df = 11), exact sign-flip permutation p over the
    12 draws (4096 patterns), exact Wilcoxon p, the 3 per-topology mean differences, and a topology-level 95 % t
    interval (n = 3, df = 2) as the cluster-conservative range
  - Holm adjustment of the sign-flip p over the primary family: exposure and nominal PDR x 3 comparisons x 2 rates
Classification (fixed here, before reading the results):
  supported    primary metric; Holm sign-flip p < 0.05, draw-level 95 % interval excludes 0, and the per-topology
               mean differences have the same sign in all 3 topologies
  consistent   secondary metric meeting the same three criteria without Holm (exploratory)
  descriptive  everything else, every delay metric (computed over delivered packets only: survivorship), and every
               test where all differences are 0 (reported as identical)
  Scope: inference is over random placements within these 3 topologies. At topology level n = 3, so no claim
  generalises to other topologies; the topology-level interval is reported for that reason.
Writes <out>/: stats_by_protocol.csv, paired_differences.csv, conditional_on_tree.csv, k0_cost.csv,
subtree_compare.csv (when --subtree* are given), STATS.txt
"""
import csv
import importlib.util
import math
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("analyze_paired_stats", HERE / "analyze_paired_stats.py")
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)

PROTOS = ("static", "riskaware", "olsr")
RATES = (8, 32)
METRICS = ("exposure_rate_pct", "pdr_nominal_pct", "sink_pdr_pct", "risk_dropped_pkts", "other_lost_pkts",
           "sink_thr_kbps", "delay_p50_ms", "delay_p95_ms", "delay_p99_ms", "mean_hops_delivered", "gw_airtime",
           "mpdu_retry_drop", "mpdu_expired", "no_route_drops", "unsent_at_source")
PRIMARY = ("exposure_rate_pct", "pdr_nominal_pct")
PAIRS = (("static", "olsr"), ("riskaware", "static"), ("riskaware", "olsr"))


def rows(p):
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


def write(path, rs):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rs[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rs)


def paired(diff, topo):
    """diff: per-draw differences; topo: topology seed of each draw."""
    mean, sd, lo, hi = S.ci95(diff)
    tm = defaultdict(list)
    for t, x in zip(topo, diff):
        tm[t].append(x)
    tmeans = [st.mean(tm[t]) for t in sorted(tm)]
    _, _, tlo, thi = S.ci95(tmeans)
    pw, nnz, _ = S.wilcoxon_exact(diff)
    return dict(diff_mean=mean, diff_sd=sd, diff_ci95_lo=lo, diff_ci95_hi=hi,
                draws_A_higher=sum(x > 0 for x in diff), draws_equal=sum(x == 0 for x in diff),
                draws_A_lower=sum(x < 0 for x in diff), p_signflip_exact=S.signflip_exact(diff),
                p_wilcoxon_exact=pw, wilcoxon_n_nonzero=nnz,
                topo_means=" ".join(f"{t}:{m:+.4g}" for t, m in zip(sorted(tm), tmeans)),
                topo_same_sign=int(all(m > 0 for m in tmeans) or all(m < 0 for m in tmeans)),
                topo_ci95_lo=tlo, topo_ci95_hi=thi)


def main():
    src = Path(sys.argv[1])
    opts = dict(a.split("=", 1) for a in sys.argv[2:] if a.startswith("--") and "=" in a)
    out = Path(opts["--out"])
    out.mkdir(parents=True, exist_ok=True)
    R = rows(src)
    k3 = {(r["protocol"], int(r["rate_kbps"]), int(r["seed"]), int(r["place"])): r
          for r in R if r["k"] == "3" and r["place"] != "subtree"}
    k0 = {(r["protocol"], int(r["rate_kbps"]), int(r["seed"])): r for r in R if r["k"] == "0"}
    draws = sorted({(s, p) for (_, _, s, p) in k3})
    assert len(draws) == 12 and len(k3) == 72, (len(draws), len(k3))
    # a risky node lies on the static BFS tree iff some static source's installed path crosses it
    on_tree = {(s, p) for (s, p) in draws if int(k3[("static", 8, s, p)]["srcs_exposed_installed"]) > 0}
    assert on_tree == {(s, p) for (s, p) in draws if int(k3[("static", 32, s, p)]["srcs_exposed_installed"]) > 0}
    lines = [f"{src}: 72 runs at k = 3 (12 draws x 3 protocols x 2 rates) + {len(k0)} reused k = 0 runs",
             f"draws with a risky node on the static BFS tree: {len(on_tree)} of 12 "
             f"({' '.join(f'{s}/{p}' for s, p in sorted(on_tree))})", ""]

    # per protocol
    sp = []
    for rate in RATES:
        for p in PROTOS:
            row = dict(rate_kbps=rate, protocol=p, n_draws=12)
            for m in METRICS:
                mean, sd, lo, hi = S.ci95([float(k3[(p, rate, s, q)][m]) for s, q in draws])
                row.update({f"{m}_mean": mean, f"{m}_sd": sd, f"{m}_ci95_lo": lo, f"{m}_ci95_hi": hi})
            ex = [float(k3[(p, rate, s, q)]["exposure_rate_pct"]) for s, q in draws]
            row["draws_zero_exposure"] = sum(x == 0 for x in ex)
            row["exposure_max"] = max(ex)
            sp.append(row)
    write(out / "stats_by_protocol.csv", sp)

    # paired
    pr = []
    for rate in RATES:
        for a, b in PAIRS:
            for m in METRICS:
                diff = [float(k3[(a, rate, s, q)][m]) - float(k3[(b, rate, s, q)][m]) for s, q in draws]
                row = dict(rate_kbps=rate, A=a, B=b, metric=m, n_draws=12, primary=int(m in PRIMARY),
                           A_mean=st.mean(float(k3[(a, rate, s, q)][m]) for s, q in draws),
                           B_mean=st.mean(float(k3[(b, rate, s, q)][m]) for s, q in draws))
                row.update(paired(diff, [s for s, _ in draws]))
                row["p_signflip_holm"] = ""
                row["per_draw_diff"] = " ".join(f"{s}/{q}:{x:+.4g}" for (s, q), x in zip(draws, diff))
                pr.append(row)
    fam = [i for i, x in enumerate(pr) if x["primary"] and x["draws_equal"] < 12]
    for i, adj in zip(fam, S.holm([pr[i]["p_signflip_exact"] for i in fam])):
        pr[i]["p_signflip_holm"] = adj
    for x in pr:
        crit = x["diff_ci95_lo"] > 0 or x["diff_ci95_hi"] < 0
        crit = crit and x["topo_same_sign"] == 1
        if x["draws_equal"] == 12:
            x["class"] = "identical"
        elif x["metric"].startswith("delay"):
            x["class"] = "descriptive"
        elif x["primary"]:
            x["class"] = "supported" if crit and x["p_signflip_holm"] < 0.05 else "descriptive"
        else:
            x["class"] = "consistent" if crit and x["p_signflip_exact"] < 0.05 else "descriptive"
    write(out / "paired_differences.csv", pr)

    # conditional on a risky node on the BFS tree (H1); n = 5 / 7: descriptive only
    cd = []
    for rate in RATES:
        for cond, ds in (("on_tree", sorted(on_tree)), ("off_tree", [d for d in draws if d not in on_tree])):
            for a, b in PAIRS:
                for m in ("exposure_rate_pct", "pdr_nominal_pct", "risk_dropped_pkts", "delay_p95_ms"):
                    diff = [float(k3[(a, rate, s, q)][m]) - float(k3[(b, rate, s, q)][m]) for s, q in ds]
                    mean, sd, lo, hi = S.ci95(diff)
                    cd.append(dict(rate_kbps=rate, condition=cond, n_draws=len(ds), A=a, B=b, metric=m,
                                   diff_mean=mean, diff_sd=sd, diff_min=min(diff), diff_max=max(diff),
                                   draws_A_higher=sum(x > 0 for x in diff), draws_A_lower=sum(x < 0 for x in diff)))
    write(out / "conditional_on_tree.csv", cd)

    # cost of k = 3 relative to the k = 0 run of the same (protocol, rate, topology)
    kc = []
    for rate in RATES:
        for p in PROTOS:
            for m in ("pdr_nominal_pct", "delay_p95_ms", "gw_airtime"):
                diff = [float(k3[(p, rate, s, q)][m]) - float(k0[(p, rate, s)][m]) for s, q in draws]
                mean, sd, lo, hi = S.ci95(diff)
                kc.append(dict(rate_kbps=rate, protocol=p, metric=m, k0_mean=st.mean(float(k0[(p, rate, s)][m]) for s in (20, 21, 22)),
                               k3_mean=st.mean(float(k3[(p, rate, s, q)][m]) for s, q in draws),
                               diff_mean=mean, diff_sd=sd, diff_min=min(diff), diff_max=max(diff)))
    write(out / "k0_cost.csv", kc)

    # subtree placement (earlier validated batches) at the same seeds, k = 3
    sc = []
    for rate in RATES:
        f = opts.get(f"--subtree{rate}")
        if not f:
            continue
        st_rows = {(r["protocol"], int(r["seed"])): r for r in rows(f)
                   if r["k"] == "3" and int(r["rate_kbps"]) == rate and r.get("place", "subtree") == "subtree"
                   and r["protocol"] in PROTOS and int(r["seed"]) in (20, 21, 22)}
        for p in PROTOS:
            seeds = sorted(s for (pp, s) in st_rows if pp == p)
            for m in ("exposure_rate_pct", "pdr_nominal_pct"):
                sc.append(dict(rate_kbps=rate, protocol=p, metric=m, subtree_seeds=" ".join(map(str, seeds)),
                               subtree_mean=st.mean(float(st_rows[(p, s)][m]) for s in seeds) if seeds else "",
                               uniform_mean=st.mean(float(k3[(p, rate, s, q)][m]) for s, q in draws if s in seeds) if seeds else ""))
    if sc:
        write(out / "subtree_compare.csv", sc)

    # readable summary
    def g(r, m):
        return f"{r[m + '_mean']:.3g} [{r[m + '_ci95_lo']:.3g}, {r[m + '_ci95_hi']:.3g}]"
    for rate in RATES:
        lines.append(f"== {rate} kbps: mean [95 % t interval] over 12 draws")
        for r in (x for x in sp if x["rate_kbps"] == rate):
            lines.append(f"  {r['protocol']:9s} exposure % {g(r, 'exposure_rate_pct')} (zero in {r['draws_zero_exposure']}/12, max {r['exposure_max']:.3g})"
                         f" | nominal PDR % {g(r, 'pdr_nominal_pct')} | p95 delay ms {g(r, 'delay_p95_ms')}"
                         f" | gw airtime {g(r, 'gw_airtime')}")
    lines.append("")
    lines.append("== paired differences A - B (draw-level 95 % interval; topology-level interval, n = 3; sign-flip p; Holm for primary)")
    for x in pr:
        if x["metric"] in ("exposure_rate_pct", "pdr_nominal_pct", "risk_dropped_pkts", "delay_p95_ms", "gw_airtime", "mpdu_retry_drop"):
            h = f"{x['p_signflip_holm']:.3g}" if x["p_signflip_holm"] != "" else "-"
            lines.append(f"  {x['rate_kbps']:>2} kbps {x['A']:>9s}-{x['B']:<9s} {x['metric']:18s} {x['diff_mean']:+9.4g} "
                         f"[{x['diff_ci95_lo']:+.4g}, {x['diff_ci95_hi']:+.4g}] topo [{x['topo_ci95_lo']:+.4g}, {x['topo_ci95_hi']:+.4g}] "
                         f"({x['topo_means']}) A>B {x['draws_A_higher']} =:{x['draws_equal']} A<B {x['draws_A_lower']} "
                         f"p={x['p_signflip_exact']:.3g} holm={h} -> {x['class']}")
    lines.append("")
    lines.append("== conditional (descriptive): mean difference, on-tree draws vs off-tree draws")
    for x in cd:
        if x["metric"] in ("exposure_rate_pct", "pdr_nominal_pct"):
            lines.append(f"  {x['rate_kbps']:>2} kbps {x['condition']:8s} n={x['n_draws']} {x['A']:>9s}-{x['B']:<9s} {x['metric']:18s} "
                         f"{x['diff_mean']:+.4g} (range {x['diff_min']:+.4g} .. {x['diff_max']:+.4g})")
    if sc:
        lines.append("")
        lines.append("== subtree vs uniform placement, k = 3, same seeds (descriptive)")
        for x in sc:
            lines.append(f"  {x['rate_kbps']:>2} kbps {x['protocol']:9s} {x['metric']:18s} subtree {x['subtree_mean']:.4g} -> uniform {x['uniform_mean']:.4g}")
    (out / "STATS.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
