#!/usr/bin/env python3
"""Seed-paired statistics for a risk-v2 N = 30 batch (input: <batch>/analysis/pilot_runs.csv written by
analyze_pilot_n30.py). Read-only. No third-party packages.

    python3 -I -B experiments/wifi6-risk/analyze_paired_stats.py <batch dir> [--rate=8] [--descriptive]

--descriptive (used for n = 3 batches): no hypothesis tests are written; the paired CSV and STATS.txt give the
per-seed differences, mean, SD and the t-based 95 % interval as a descriptive range only.

Writes <batch>/analysis/:
  stats_by_config.csv   per (protocol, k): n, mean, SD, 95 % CI of the mean (Student t, df = n - 1)
  paired_riskaware_vs_static.csv
                        per (k, metric): differences riskaware - static on the same seed (same positions,
                        traffic and high-risk set), mean, SD, 95 % CI, Cohen's d_z, paired t-test (two-sided),
                        exact Wilcoxon signed-rank test (two-sided; zero differences dropped, average ranks for
                        ties, exact null by enumerating all sign patterns), exact sign-flip permutation test on the
                        mean difference (all 2^n patterns), and Holm-adjusted Wilcoxon p over the primary family
                        (exposure and nominal PDR, k = 1..3: 6 tests).
  STATS.txt             readable summary
Notes: with n = 10 the smallest two-sided exact Wilcoxon p is 2/1024 = 0.00195. Delay metrics are computed over
delivered packets only, so a protocol that loses long-path packets can show lower delay (survivorship).
"""
import csv
import itertools
import math
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

METRICS = ("pdr_nominal_pct", "sink_pdr_pct", "sink_thr_kbps", "delay_p50_ms", "delay_p95_ms", "delay_p99_ms",
           "mean_hops_delivered", "exposure_rate_pct", "risk_dropped_pkts", "other_lost_pkts", "gw_airtime")
PRIMARY = ("exposure_rate_pct", "pdr_nominal_pct")


# ---------------------------------------------------------------- Student t (regularized incomplete beta)
def _betacf(a, b, x):
    tiny, qab, qap, qam = 1e-300, a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        de = d * c
        h *= de
        if abs(de - 1.0) < 1e-15:
            break
    return h


def betainc(a, b, x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lb = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    if x < (a + 1) / (a + b + 2):
        return math.exp(lb) * _betacf(a, b, x) / a
    return 1.0 - math.exp(lb) * _betacf(b, a, 1 - x) / b


def t_two_sided_p(t, df):
    return betainc(df / 2.0, 0.5, df / (df + t * t))


def t_quantile(q, df):   # q in (0.5, 1)
    lo, hi = 0.0, 1000.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if 1 - t_two_sided_p(mid, df) / 2 < q:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def ci95(xs):
    n = len(xs)
    m = st.mean(xs)
    if n < 2:
        return m, float("nan"), float("nan"), float("nan")
    sd = st.stdev(xs)
    h = t_quantile(0.975, n - 1) * sd / math.sqrt(n)
    return m, sd, m - h, m + h


def wilcoxon_exact(d):
    nz = [x for x in d if x != 0]
    n = len(nz)
    if n == 0:
        return float("nan"), 0, 0.0
    order = sorted(range(n), key=lambda i: abs(nz[i]))
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs(nz[order[j + 1]]) == abs(nz[order[i]]):
            j += 1
        for t in range(i, j + 1):
            ranks[order[t]] = (i + j) / 2 + 1
        i = j + 1
    wplus = sum(r for r, x in zip(ranks, nz) if x > 0)
    total = sum(ranks)
    dev = abs(wplus - total / 2)
    cnt = 0
    for signs in itertools.product((0, 1), repeat=n):
        w = sum(r for r, s in zip(ranks, signs) if s)
        if abs(w - total / 2) >= dev - 1e-9:
            cnt += 1
    return cnt / 2 ** n, n, wplus


def signflip_exact(d):
    n = len(d)
    obs = abs(sum(d))
    cnt = sum(1 for signs in itertools.product((1, -1), repeat=n)
              if abs(sum(s * x for s, x in zip(signs, d))) >= obs - 1e-9)
    return cnt / 2 ** n


def holm(ps):
    idx = sorted(range(len(ps)), key=lambda i: ps[i])
    adj, run = [0.0] * len(ps), 0.0
    for r, i in enumerate(idx):
        run = max(run, min(1.0, (len(ps) - r) * ps[i]))
        adj[i] = run
    return adj


def main():
    b = Path(sys.argv[1])
    rate = int(dict(a.split("=", 1) for a in sys.argv[2:] if "=" in a).get("--rate", 8))
    descriptive = "--descriptive" in sys.argv[2:]
    an = b / "analysis"
    with open(an / "pilot_runs.csv", newline="") as f:
        R = [r for r in csv.DictReader(f) if int(r["rate_kbps"]) == rate]
    by = defaultdict(dict)
    for r in R:
        by[(r["protocol"], int(r["k"]))][int(r["seed"])] = r
    lines = [f"{b.name}: rate {rate} kbps, {len(R)} runs"]
    rows = []
    for (p, k) in sorted(by, key=lambda x: (("static", "riskaware", "aodv", "olsr").index(x[0]), x[1])):
        d = by[(p, k)]
        row = dict(protocol=p, k=k, n=len(d), seeds=" ".join(map(str, sorted(d))))
        for m in METRICS:
            mean, sd, lo, hi = ci95([float(d[s][m]) for s in sorted(d)])
            row.update({f"{m}_mean": mean, f"{m}_sd": sd, f"{m}_ci95_lo": lo, f"{m}_ci95_hi": hi})
        rows.append(row)
    with open(an / "stats_by_config.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    pr = []
    for k in (0, 1, 2, 3):
        s_, r_ = by[("static", k)], by[("riskaware", k)]
        seeds = sorted(set(s_) & set(r_))
        for m in METRICS:
            diff = [float(r_[s][m]) - float(s_[s][m]) for s in seeds]
            mean, sd, lo, hi = ci95(diff)
            if sd and sd > 0:
                t = mean / (sd / math.sqrt(len(diff)))
                pt = t_two_sided_p(t, len(diff) - 1)
                dz = mean / sd
            else:
                t, pt, dz = float("nan"), (1.0 if mean == 0 else 0.0), float("nan")
            pw, nnz, wplus = wilcoxon_exact(diff)
            pr.append(dict(k=k, metric=m, n_pairs=len(diff), seeds=" ".join(map(str, seeds)),
                           static_mean=st.mean(float(s_[s][m]) for s in seeds),
                           riskaware_mean=st.mean(float(r_[s][m]) for s in seeds),
                           diff_mean=mean, diff_sd=sd, diff_ci95_lo=lo, diff_ci95_hi=hi, cohen_dz=dz,
                           pairs_riskaware_higher=sum(x > 0 for x in diff), pairs_equal=sum(x == 0 for x in diff),
                           pairs_riskaware_lower=sum(x < 0 for x in diff), t_stat=t, p_paired_t=pt,
                           p_wilcoxon_exact=pw, wilcoxon_n_nonzero=nnz, wilcoxon_w_plus=wplus,
                           p_signflip_exact=signflip_exact(diff), p_wilcoxon_holm="",
                           per_seed_diff=" ".join(f"{s}:{x:+.6g}" for s, x in zip(seeds, diff))))
    fam = [i for i, x in enumerate(pr) if x["metric"] in PRIMARY and x["k"] in (1, 2, 3)]
    for i, a in zip(fam, holm([pr[i]["p_wilcoxon_exact"] for i in fam])):
        pr[i]["p_wilcoxon_holm"] = a
    if descriptive:
        tests = ("t_stat", "p_paired_t", "p_wilcoxon_exact", "wilcoxon_n_nonzero", "wilcoxon_w_plus",
                 "p_signflip_exact", "p_wilcoxon_holm", "cohen_dz")
        pr = [{c: v for c, v in x.items() if c not in tests} for x in pr]
        lines[0] += " (descriptive only: no hypothesis tests; 95 % t interval shown as a descriptive range)"
    with open(an / "paired_riskaware_vs_static.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(pr[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(pr)
    for x in pr:
        if x["k"] == 0 and x["metric"] not in PRIMARY:
            continue
        if descriptive:
            lines.append(f"k={x['k']} {x['metric']:20s} static {x['static_mean']:.4g} riskaware {x['riskaware_mean']:.4g} "
                         f"diff {x['diff_mean']:+.4g} SD {x['diff_sd']:.3g} "
                         f"[{x['diff_ci95_lo']:+.4g}, {x['diff_ci95_hi']:+.4g}] "
                         f"higher/equal/lower {x['pairs_riskaware_higher']}/{x['pairs_equal']}/{x['pairs_riskaware_lower']} "
                         f"per seed {x['per_seed_diff']}")
            continue
        lines.append(f"k={x['k']} {x['metric']:20s} static {x['static_mean']:.4g} riskaware {x['riskaware_mean']:.4g} "
                     f"diff {x['diff_mean']:+.4g} [{x['diff_ci95_lo']:+.4g}, {x['diff_ci95_hi']:+.4g}] "
                     f"higher/equal/lower {x['pairs_riskaware_higher']}/{x['pairs_equal']}/{x['pairs_riskaware_lower']} "
                     f"t p={x['p_paired_t']:.3g} Wilcoxon p={x['p_wilcoxon_exact']:.3g}"
                     + (f" (Holm {x['p_wilcoxon_holm']:.3g})" if x["p_wilcoxon_holm"] != "" else "")
                     + f" sign-flip p={x['p_signflip_exact']:.3g}")
    (an / "STATS.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
