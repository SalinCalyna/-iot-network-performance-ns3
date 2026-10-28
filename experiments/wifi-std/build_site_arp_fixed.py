#!/usr/bin/env python3
"""Build the dashboard data for the ARP-fixed IEEE 802.11b results (read-only on results/ and analysis/).

    python3 -I -B experiments/wifi-std/build_site_arp_fixed.py <site dir>

Writes <site>/data/arp-fixed.json. Every value is copied from the verified ARP-fixed analysis outputs:
  analysis/chapter4-tables-figures/t43_cells.csv, t43a_ranking.csv, t44_bottleneck.csv, t45_ratesweep.csv
  analysis/arp-fixed-throughput-delay/cells.csv
  publication/CLAIMS.csv
Only the ARP-fixed ("_on") columns are used. The original-configuration ("_off") columns are never read into the
output, so no ARP-affected value can reach this file. Confidence intervals are published only for cells with 11
seeds (high traffic); 3-seed cells carry the seed minimum and maximum instead, and ci = null.

Before anything is written, every published cell value is recomputed independently from the raw run files
(results/wifi-std/arp-*-on*/*/probe_aggregate.csv, pernode/*.csv). Any mismatch stops the build. The source files
and their sha256 are listed in the JSON. The output is deterministic (sorted keys, fixed rounding).
"""
import csv
import glob
import hashlib
import json
import math
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CH4 = ROOT / "analysis/chapter4-tables-figures"
TD = ROOT / "analysis/arp-fixed-throughput-delay"
SOURCES = [CH4 / "t43_cells.csv", CH4 / "t43a_ranking.csv", CH4 / "t44_bottleneck.csv", CH4 / "t45_ratesweep.csv",
           TD / "cells.csv", ROOT / "publication/CLAIMS.csv", CH4 / "INPUTS.sha256", TD / "INPUTS.sha256"]
PROTOS = ("aodv", "olsr", "static")
NS = (10, 20, 30, 50, 75, 100)
TRAFFIC = {"low": 4, "medium": 8, "high": 16}
SEEDS = {4: (20, 25, 30), 8: (20, 25, 30), 16: tuple(range(20, 31))}
T975 = {2: 4.302653, 10: 2.228139}
R = 4   # decimals kept in the JSON (the analysis CSVs carry 4)


def stop(msg):
    sys.exit("STOP: " + msg)


def rows(p):
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


def r4(x):
    return None if x is None else round(float(x), R)


def close(a, b, tol=6e-4):
    return abs(float(a) - float(b)) <= tol


# ---------------------------------------------------------------- independent recomputation from raw runs
def raw_runs():
    out = {}
    for d in ("arp-a2-on", "arp-a1-on", "arp-b-on-os", "arp-b1-on", "arp-ratesweep-on"):
        for p in sorted(glob.glob(str(ROOT / f"results/wifi-std/{d}/*/probe_aggregate.csv"))):
            a = rows(p)[0]
            prov = json.loads(Path(p).with_name("provenance.json").read_text())
            if "--arpPrepopulate=1" not in prov["argv"] or prov["exit_code"] != 0:
                stop(f"{p}: not a clean ARP-fixed run")
            k = (d == "arp-ratesweep-on", a["protocol"], int(a["nodes"]), int(float(a["offered_rate_kbps"])), int(a["seed"]))
            out.setdefault(k, (a, Path(p).parent))
    return out


RAW = raw_runs()
S1 = {k[1:]: v for k, v in RAW.items() if not k[0] and k[1:] in
      {(p, n, rt, s) for p in PROTOS for n in NS for rt in SEEDS for s in SEEDS[rt]}}
RS = {k[1:]: v for k, v in RAW.items() if k[0]}
if len(S1) != 306 or len(RS) != 72:
    stop(f"raw coverage {len(S1)} / {len(RS)} (expected 306 / 72)")
pdr = lambda a: 100 * int(a["rxPkts"]) / int(a["txPkts"])
gp = lambda a: int(a["rxPkts"]) * 512 * 8 / 270 / 1000
dl = lambda a: 1000 * float(a["avgDelaySec"])


def stats(xs):
    m = st.mean(xs)
    ci = T975[len(xs) - 1] * st.stdev(xs) / math.sqrt(len(xs)) if len(xs) == 11 else None
    return m, ci, min(xs), max(xs)


# ---------------------------------------------------------------- read verified analysis outputs
t43 = {(r["traffic"], int(r["N"]), r["protocol"]): r for r in rows(CH4 / "t43_cells.csv")}
cells = {(r["traffic"], int(r["N"]), r["protocol"]): r for r in rows(TD / "cells.csv")}
rank = {(r["traffic"], int(r["N"])): r for r in rows(CH4 / "t43a_ranking.csv")}
t44 = {(r["protocol"], int(r["N"]), r["traffic"]): r for r in rows(CH4 / "t44_bottleneck.csv")}
t45 = {(r["protocol"], int(r["N"]), int(r["rate_kbps"])): r for r in rows(CH4 / "t45_ratesweep.csv")}

checked = 0


def agree(label, published, recomputed, tol=6e-4, rel=0.0):
    """Absolute tolerance for values; CI half-widths also get a relative tolerance of 1e-4, because the
    throughput-delay analysis used t(0.975, 10) = 2.228 (3 decimals) where this check uses 2.228139."""
    global checked
    if published is None and recomputed is None:
        return
    if (published is None) != (recomputed is None) or not close(published, recomputed, tol + rel * abs(float(recomputed))):
        stop(f"{label}: analysis output {published} != raw recomputation {recomputed}")
    checked += 1


def series_block(metric):
    out = {}
    for t, rt in TRAFFIC.items():
        out[t] = {}
        for p in PROTOS:
            pts = []
            for n in NS:
                xs = [{"pdr": pdr, "goodput": gp, "delay": dl}[metric](S1[(p, n, rt, s)][0]) for s in SEEDS[rt]]
                m, ci, lo, hi = stats(xs)
                if metric == "pdr":
                    r = t43[(t, n, p)]
                    pub = dict(mean=float(r["pdr_on"]), ci=float(r["pdr_on_ci"]) if len(xs) == 11 else None,
                               min=float(r["pdr_on_min"]), max=float(r["pdr_on_max"]), n=int(r["n_seeds"]))
                    agree(f"pdr {t} {n} {p} = cells.csv", float(cells[(t, n, p)]["pdr_pct_mean"]), pub["mean"])
                else:
                    c = cells[(t, n, p)]
                    col = {"goodput": "goodput_kbps", "delay": "delay_ms"}[metric]
                    pub = dict(mean=float(c[f"{col}_mean"]),
                               ci=(float(c[f"{col}_ci_hi"]) - float(c[f"{col}_mean"])) if len(xs) == 11 else None,
                               min=float(c[f"{col}_min"]), max=float(c[f"{col}_max"]), n=int(c["n"]))
                for key, val in (("mean", m), ("ci", ci), ("min", lo), ("max", hi)):
                    agree(f"{metric} {t} N={n} {p} {key}", pub[key], val, 6e-4 if metric == "pdr" else 2e-3,
                          1e-4 if key == "ci" else 0.0)
                if pub["n"] != len(xs):
                    stop(f"{metric} {t} {n} {p}: n {pub['n']} != {len(xs)}")
                pt = {"n": n, "mean": r4(pub["mean"]), "ci": r4(pub["ci"]), "min": r4(pub["min"]), "max": r4(pub["max"]),
                      "seeds": pub["n"]}
                if metric == "goodput":
                    pt["offered"] = float(cells[(t, n, p)]["offered_payload_kbps"])
                pts.append(pt)
            out[t][p] = pts
    return out


data = {"pdr": series_block("pdr"), "goodput": series_block("goodput"), "delay": series_block("delay")}

# ranking (leader per condition, ARP-fixed only)
data["ranking"] = []
for t in TRAFFIC:
    for n in NS:
        r = rank[(t, n)]
        m = {p: data["pdr"][t][p][NS.index(n)]["mean"] for p in PROTOS}
        if max(m, key=m.get) != r["leader_on"]:
            stop(f"ranking {t} {n}: leader {r['leader_on']} vs recomputed {max(m, key=m.get)}")
        data["ranking"].append({"traffic": t, "n": n, "leader": r["leader_on"], "margin_pp": r4(r["margin_over_second_pp"]),
                                "seeds": int(r["n_seeds"])})

# bottleneck (OLSR / Static x N 30-100 x medium / high, 11 seeds)
B = {}
for (rs_, p, n, rt, s), v in RAW.items():
    if not rs_ and p in ("olsr", "static") and n in (30, 50, 75, 100) and rt in (8, 16):
        B.setdefault((p, n, rt, s), v)
if len(B) != 176:
    stop(f"bottleneck coverage {len(B)}")
data["bottleneck"] = {}
for p in ("olsr", "static"):
    for t, rt in (("medium", 8), ("high", 16)):
        pts = []
        for n in (30, 50, 75, 100):
            r = t44[(p, n, t)]
            runs = [B[(p, n, rt, s)] for s in range(20, 31)]
            gw = [float(a["gw_airtime_busy_frac"]) for a, _ in runs]
            m, ci, _, _ = stats(gw)
            agree(f"airtime {p} {n} {t}", r["gw_air_on"], m, 6e-5)
            agree(f"airtime ci {p} {n} {t}", r["gw_air_on_ci"], ci, 6e-5, 1e-4)
            agree(f"ring1 {p} {n} {t}", r["ring1_on"], st.mean(float(a["ring1_airtime_busy_frac_mean"]) for a, _ in runs), 6e-5)
            agree(f"macq {p} {n} {t}", r["macq_events_on"], st.mean(int(a["total_mac_queue_drops"]) for a, _ in runs), 6e-4)
            agree(f"pdr {p} {n} {t}", r["pdr_on"], st.mean(pdr(a) for a, _ in runs), 6e-4)
            parts = []
            for a, d in runs:
                pn = rows(glob.glob(str(d / "pernode/*.csv"))[0])
                sens = [x for x in pn if x["is_gateway"] == "0"]
                le1 = [x for x in sens if 0 <= int(float(x["hop_to_gw"])) <= 1]
                mq = sum(int(x["mac_queue_drops"]) for x in sens)
                parts.append((len(le1) / len(sens), sum(int(x["mac_queue_drops"]) for x in le1) / mq if mq else None))
            fm = [b for _, b in parts if b is not None]
            conc = st.mean(fm) / st.mean(a for a, _ in parts) if fm else None
            pub_conc = float(r["hop1_conc_ratio_on"]) if r["hop1_conc_ratio_on"] not in ("", "nan", "NA") else None
            agree(f"hop-1 concentration {p} {n} {t}", pub_conc, conc, 6e-4)
            pts.append({"n": n, "gw_airtime": r4(r["gw_air_on"]), "gw_airtime_ci": r4(r["gw_air_on_ci"]),
                        "ring1_airtime": r4(r["ring1_on"]), "mac_frame_drop_events": r4(r["macq_events_on"]),
                        "hop1_concentration": r4(pub_conc), "pdr": r4(r["pdr_on"]), "seeds": int(r["n_seeds"])})
        data["bottleneck"][f"{p}-{t}"] = pts

# offered-rate sweep (3 seeds, descriptive)
data["ratesweep"] = {}
for p in ("olsr", "static"):
    for n in (50, 75, 100):
        pts = []
        for rt in (16, 12, 8, 4):
            r = t45[(p, n, rt)]
            xs = [pdr(RS[(p, n, rt, s)][0]) for s in (20, 25, 30)]
            agree(f"rate pdr {p} {n} {rt}", r["pdr_on"], st.mean(xs))
            agree(f"rate pdr min {p} {n} {rt}", r["pdr_on_min"], min(xs))
            agree(f"rate pdr max {p} {n} {rt}", r["pdr_on_max"], max(xs))
            agree(f"rate airtime {p} {n} {rt}", r["gw_air_on"], st.mean(float(RS[(p, n, rt, s)][0]["gw_airtime_busy_frac"]) for s in (20, 25, 30)), 6e-5)
            pts.append({"rate": rt, "pdr": r4(r["pdr_on"]), "pdr_min": r4(r["pdr_on_min"]), "pdr_max": r4(r["pdr_on_max"]),
                        "change_vs16_pp": r4(r["change_vs16_on_pp"]), "gw_airtime": r4(r["gw_air_on"]), "seeds": int(r["n_seeds"])})
        data["ratesweep"][f"{p}-{n}"] = pts

# published claims (verbatim; recomputed by publication/verify_published_claims.py)
data["claims"] = [{"id": c["id"], "claim": c["claim"], "value": c["published_value"]} for c in rows(ROOT / "publication/CLAIMS.csv")]

data["meta"] = {
    "title": "IEEE 802.11b, ARP-fixed re-runs (ARP cache pre-populated)",
    "status": ("Primary 802.11b analysis of the thesis draft. The advisor approved this analysis structure "
               "(ARP-fixed runs primary, original runs secondary) in October 2026; the thesis itself remains "
               "under advisor review."),
    "configuration": "IEEE 802.11b DSSS 1 Mbit/s, 250 m field, central gateway, static sensors, --arpPrepopulate=1",
    "runs": {"protocol_comparison": len(S1), "bottleneck": len(B), "rate_sweep": len(RS)},
    "intervals": "95 % Student-t CI over 11 seeds (high traffic, bottleneck). 3-seed cells: seed min-max only, ci = null.",
    "excluded": "No original (ARP-affected) value is included. No mobility result exists for the ARP-fixed runs.",
    "generated_by": "experiments/wifi-std/build_site_arp_fixed.py",
    "raw_cross_checks": checked,
    "sources": [{"path": str(p.relative_to(ROOT)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in SOURCES],
}

out = Path(sys.argv[1]) / "data" / "arp-fixed.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
print(f"OK: {out} ({checked} values cross-checked against raw runs)")
