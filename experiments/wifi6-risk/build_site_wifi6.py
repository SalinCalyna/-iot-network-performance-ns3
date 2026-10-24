#!/usr/bin/env python3
"""Build the dashboard data for the Wi-Fi 6 risk study (read-only on results/ and analysis/).

    python3 -I -B experiments/wifi6-risk/build_site_wifi6.py <site dir>

Writes <site>/data/wifi6-risk.json and copies the validated figures to <site>/images/wifi6/. Every number in the
JSON is read from:
  results/wifi6-risk/{seeds10-n30-8k-v2-20261024T160515,n100-8k-v2-20261024T165009}/analysis/
      stats_by_config.csv, paired_riskaware_vs_static.csv   (numeric means, SD, t intervals, tests)
  analysis/wifi6-risk-writeup/tables/T-W*.csv                (formatted report tables, shown verbatim)
  analysis/wifi6-risk-writeup/FIGURES.md                     (captions)
The numeric means/SD/intervals are cross-checked against the formatted T-W4/T-W5 tables (same rounding) before
anything is written; any mismatch stops the build. Source files and their sha256 are listed in the JSON.
"""
import csv
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
W = ROOT / "analysis/wifi6-risk-writeup"
B = {30: ROOT / "results/wifi6-risk/seeds10-n30-8k-v2-20261024T160515",
     100: ROOT / "results/wifi6-risk/n100-8k-v2-20261024T165009"}
METRICS = [("pdr_nominal_pct", "Nominal PDR", "%", 2), ("exposure_rate_pct", "Risk exposure", "%", 2),
           ("sink_thr_kbps", "Throughput", "kbps", 1), ("delay_p50_ms", "Delay p50", "ms", 1),
           ("delay_p95_ms", "Delay p95", "ms", 1), ("delay_p99_ms", "Delay p99", "ms", 1),
           ("mean_hops_delivered", "Hop count, delivered", "links", 3), ("gw_airtime", "Gateway airtime", "fraction", 3)]
PROTOS = ("static", "riskaware", "olsr", "aodv")
LABEL = {"static": "Static", "riskaware": "Risk-Aware", "olsr": "OLSR", "aodv": "AODV"}
SRC = {}


def rows(p):
    p = Path(p)
    SRC[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


def raw_table(name):
    p = W / "tables" / f"{name}.csv"
    SRC[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    with open(p, newline="") as f:
        r = list(csv.reader(f))
    return dict(header=r[0], rows=r[1:])


def fmt(m, sd, lo, hi, nd):
    return f"{m:.{nd}f} ± {sd:.{nd}f} [{lo:.{nd}f}, {hi:.{nd}f}]"


def main():
    site = Path(sys.argv[1]).resolve()
    assert (site / "index.html").exists(), site
    out = dict(generated_by="experiments/wifi6-risk/build_site_wifi6.py (ns-3-dev, branch exp/wifi6-arp)",
               metrics=[dict(key=k, label=l, unit=u, digits=d) for k, l, u, d in METRICS],
               protocols=[dict(key=p, label=LABEL[p]) for p in PROTOS], batches={})
    for n, b in B.items():
        st = rows(b / "analysis/stats_by_config.csv")
        pr = rows(b / "analysis/paired_riskaware_vs_static.csv")
        tw = raw_table("T-W4a_by_protocol" if n == 30 else "T-W5a_by_protocol")
        seeds = sorted({int(s) for r in st for s in r["seeds"].split()})
        cfg = []
        for r in st:
            d = dict(protocol=r["protocol"], k=int(r["k"]), n=int(r["n"]))
            for k, _, _, nd in METRICS:
                d[k] = [float(r[f"{k}_{x}"]) for x in ("mean", "sd", "ci95_lo", "ci95_hi")]
            cfg.append(d)
            # cross-check against the formatted report table (protocol, k)
            trow = next(x for x in tw["rows"] if x[0] == LABEL[d["protocol"]] and int(x[1]) == d["k"])
            for i, (k, _, _, nd) in enumerate(METRICS):
                assert trow[3 + i] == fmt(*d[k], nd), (n, d["protocol"], d["k"], k, trow[3 + i], fmt(*d[k], nd))
        paired = []
        for r in pr:
            if r["metric"] not in [m[0] for m in METRICS] or int(r["k"]) == 0:
                continue
            x = dict(k=int(r["k"]), metric=r["metric"], n_pairs=int(r["n_pairs"]),
                     static_mean=float(r["static_mean"]), riskaware_mean=float(r["riskaware_mean"]),
                     diff=[float(r["diff_mean"]), float(r["diff_sd"]), float(r["diff_ci95_lo"]), float(r["diff_ci95_hi"])],
                     higher=int(r["pairs_riskaware_higher"]), equal=int(r["pairs_equal"]), lower=int(r["pairs_riskaware_lower"]))
            if n == 30:
                x.update(p_wilcoxon=float(r["p_wilcoxon_exact"]), cohen_dz=float(r["cohen_dz"]),
                         p_holm=float(r["p_wilcoxon_holm"]) if r["p_wilcoxon_holm"] != "" else None)
            else:
                assert "p_wilcoxon_exact" not in r     # descriptive file: no tests exist
                x["per_seed"] = r["per_seed_diff"]
            paired.append(x)
        runs = rows(b / "analysis/pilot_runs.csv")
        den = dict(runs=len(runs), max_unsent_at_source=max(int(r["unsent_at_source"]) for r in runs),
                   max_abs_sink_minus_nominal_pp=max(abs(float(r["sink_pdr_pct"]) - float(r["pdr_nominal_pct"])) for r in runs),
                   max_sink_minus_flowmonitor_pkts=max(int(r["sink_minus_fm"]) for r in runs))
        out["batches"][str(n)] = dict(n_sensors=n, seeds=seeds, n_seeds=len(seeds), inferential=(n == 30),
                                      batch=b.name, configs=cfg, paired=paired, denominators=den)
    for name in ("T-W1_parameters", "T-W2a_ba_defect_n30", "T-W2b_residual_tail_n100_64k", "T-W2c_tail_mechanisms",
                 "T-W2d_validation", "T-W3_load_calibration", "T-W6a_aodv_vs_olsr_n100", "T-W6b_aodv_diagnostic_seed20",
                 "T-W6c_aodv_findings_status", "T-W7_limitations"):
        out.setdefault("tables", {})[name] = raw_table(name)
    cap = (W / "FIGURES.md").read_text()
    SRC["analysis/wifi6-risk-writeup/FIGURES.md"] = hashlib.sha256(cap.encode()).hexdigest()
    figs = {}
    for m in re.finditer(r"^## (F-W\S+)\n(.+?)\n\n\*Source:\* (.+?)\n", cap, re.M | re.S):
        figs[m.group(1)] = dict(caption=m.group(2).strip(), source=m.group(3).strip(), src=f"images/wifi6/{m.group(1)}.png")
    assert len(figs) == 8, list(figs)
    out["figures"] = figs
    (site / "images/wifi6").mkdir(parents=True, exist_ok=True)
    for name in figs:
        src = W / "figures" / f"{name}.png"
        SRC[str(src.relative_to(ROOT))] = hashlib.sha256(src.read_bytes()).hexdigest()
        shutil.copyfile(src, site / "images/wifi6" / f"{name}.png")
    inv = json.loads((W / "inventory.json").read_text())
    SRC["analysis/wifi6-risk-writeup/inventory.json"] = hashlib.sha256((W / "inventory.json").read_bytes()).hexdigest()
    out["hop_check"] = inv["hop_check"]          # mean links: delivered vs all sent, per k (seed means)
    out["sources"] = dict(sorted(SRC.items()))
    (site / "data/wifi6-risk.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"wrote {site / 'data/wifi6-risk.json'}: {len(out['batches'])} batches, {len(out['tables'])} tables, "
          f"{len(figs)} figures, {len(SRC)} source files; cross-check vs T-W4/T-W5 passed")


if __name__ == "__main__":
    main()
