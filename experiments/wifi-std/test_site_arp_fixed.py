#!/usr/bin/env python3
"""Tests for site/data/arp-fixed.json (read-only; stdlib only).

    python3 -I -B experiments/wifi-std/test_site_arp_fixed.py

T1 rebuild: build_site_arp_fixed.py (which itself cross-checks every value against the raw run files) reproduces
   site/data/arp-fixed.json byte for byte.
T2 isolation: no original-configuration (ARP-affected) dataset is a source, no key names an "off"/"frozen" value,
   and every listed source still has the recorded sha256.
T3 traceability: every number in the JSON equals the value in its source CSV (rounded to 4 decimals).
T4 interval policy: a CI is present exactly for 11-seed cells; 3-seed cells have ci = null and min <= mean <= max.
T5 claims: the published values of claims C01, C04, C06, C08-C10, C12 (condition-level part), C13 and C14
   (publication/CLAIMS.csv) are recomputed from the JSON alone and must match.
"""
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
J = ROOT / "site/data/arp-fixed.json"
fails = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))
    if not ok:
        fails.append(name)


def rows(p):
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


r4 = lambda x: None if x in (None, "", "nan", "NA") else round(float(x), 4)
d = json.loads(J.read_text())

# T1
with tempfile.TemporaryDirectory() as tmp:
    r = subprocess.run([sys.executable, "-I", "-B", str(ROOT / "experiments/wifi-std/build_site_arp_fixed.py"), tmp],
                       capture_output=True, text=True)
    same = r.returncode == 0 and (Path(tmp) / "data/arp-fixed.json").read_bytes() == J.read_bytes()
    check("T1 rebuild byte-identical (with raw cross-checks)", same, (r.stdout or r.stderr).strip()[-120:])

# T2
srcs = [s["path"] for s in d["meta"]["sources"]]
bad_src = [s for s in srcs if any(x in s for x in ("final-report-data", "v3-ext", "bottleneck-characterisation", "v4-"))]
keys = set()


def walk(o):
    if isinstance(o, dict):
        for k, v in o.items():
            keys.add(k)
            walk(v)
    elif isinstance(o, list):
        for v in o:
            walk(v)


walk(d)
bad_keys = sorted(k for k in keys if any(x in k.lower() for x in ("_off", "frozen", "original")))
hash_bad = [s["path"] for s in d["meta"]["sources"] if hashlib.sha256((ROOT / s["path"]).read_bytes()).hexdigest() != s["sha256"]]
check("T2 no ARP-affected source or field; source hashes current", not bad_src and not bad_keys and not hash_bad,
      f"sources {len(srcs)}; bad sources {bad_src}; bad keys {bad_keys}; changed {hash_bad}")

# T3
CH4, TD = ROOT / "analysis/chapter4-tables-figures", ROOT / "analysis/arp-fixed-throughput-delay"
t43 = {(r["traffic"], int(r["N"]), r["protocol"]): r for r in rows(CH4 / "t43_cells.csv")}
cells = {(r["traffic"], int(r["N"]), r["protocol"]): r for r in rows(TD / "cells.csv")}
t44 = {(r["protocol"], int(r["N"]), r["traffic"]): r for r in rows(CH4 / "t44_bottleneck.csv")}
t45 = {(r["protocol"], int(r["N"]), int(r["rate_kbps"])): r for r in rows(CH4 / "t45_ratesweep.csv")}
rk = {(r["traffic"], int(r["N"])): r for r in rows(CH4 / "t43a_ranking.csv")}
n_cmp, miss = 0, []


def eq(label, a, b):
    global n_cmp
    n_cmp += 1
    if a != b:
        miss.append((label, a, b))


for t, prot in d["pdr"].items():
    for p, pts in prot.items():
        for pt in pts:
            r = t43[(t, pt["n"], p)]
            eq(f"pdr {t} {p} {pt['n']}", (pt["mean"], pt["min"], pt["max"], pt["ci"]),
               (r4(r["pdr_on"]), r4(r["pdr_on_min"]), r4(r["pdr_on_max"]), r4(r["pdr_on_ci"]) if pt["seeds"] == 11 else None))
for metric, col in (("goodput", "goodput_kbps"), ("delay", "delay_ms")):
    for t, prot in d[metric].items():
        for p, pts in prot.items():
            for pt in pts:
                c = cells[(t, pt["n"], p)]
                eq(f"{metric} {t} {p} {pt['n']}", (pt["mean"], pt["min"], pt["max"], pt["ci"]),
                   (r4(c[f"{col}_mean"]), r4(c[f"{col}_min"]), r4(c[f"{col}_max"]),
                    r4(float(c[f"{col}_ci_hi"]) - float(c[f"{col}_mean"])) if pt["seeds"] == 11 else None))
for key, pts in d["bottleneck"].items():
    p, t = key.split("-")
    for pt in pts:
        r = t44[(p, pt["n"], t)]
        eq(f"bottleneck {key} {pt['n']}", (pt["gw_airtime"], pt["gw_airtime_ci"], pt["ring1_airtime"], pt["mac_frame_drop_events"],
                                           pt["hop1_concentration"], pt["pdr"]),
           (r4(r["gw_air_on"]), r4(r["gw_air_on_ci"]), r4(r["ring1_on"]), r4(r["macq_events_on"]), r4(r["hop1_conc_ratio_on"]), r4(r["pdr_on"])))
for key, pts in d["ratesweep"].items():
    p, n = key.split("-")
    for pt in pts:
        r = t45[(p, int(n), pt["rate"])]
        eq(f"rate {key} {pt['rate']}", (pt["pdr"], pt["pdr_min"], pt["pdr_max"], pt["change_vs16_pp"], pt["gw_airtime"]),
           (r4(r["pdr_on"]), r4(r["pdr_on_min"]), r4(r["pdr_on_max"]), r4(r["change_vs16_on_pp"]), r4(r["gw_air_on"])))
for x in d["ranking"]:
    r = rk[(x["traffic"], x["n"])]
    eq(f"ranking {x['traffic']} {x['n']}", (x["leader"], x["margin_pp"]), (r["leader_on"], r4(r["margin_over_second_pp"])))
check("T3 every JSON value equals its source CSV value", not miss, f"{n_cmp} records compared; {len(miss)} differ {miss[:2]}")

# T4
pts = [pt for m in ("pdr", "goodput", "delay") for prot in d[m].values() for ps in prot.values() for pt in ps]
bad = [pt for pt in pts if (pt["seeds"] == 11) != (pt["ci"] is not None) or not pt["min"] <= pt["mean"] <= pt["max"]]
check("T4 CI only for 11-seed cells; 3-seed cells descriptive", not bad, f"{len(pts)} cells; {len(bad)} violate")

# T5
claims = {c["id"]: c["published_value"] for c in rows(ROOT / "publication/CLAIMS.csv")}
got = {}
m = d["meta"]["runs"]
got["C01"] = f"{m['protocol_comparison']}/{m['bottleneck']}/{m['rate_sweep']}"
P = ("aodv", "olsr", "static")
lead = lambda metric, t, i: max(P, key=lambda p: d[metric][t][p][i]["mean"])
got["C04"] = f"{sum(1 for t in d['pdr'] for i in range(1, 6) if lead('pdr', t, i) == lead('goodput', t, i) == 'static')}/15"
n10 = [sorted((d["pdr"][t][p][0]["mean"] for p in P), reverse=True) for t in d["pdr"]]
got["C06"] = f"{max(a[0] - a[1] for a in n10):.1f}"
pl = [x["mean"] for x in d["goodput"]["high"]["static"][2:]]
got["C08"] = f"{min(pl):.0f}–{max(pl):.0f}"
air = [x["gw_airtime"] for v in d["bottleneck"].values() for x in v if x["n"] >= 75]
got["C09"] = f"{min(air):.2f}–{max(air):.2f}"
hc = [x["hop1_concentration"] for v in d["bottleneck"].values() for x in v if x["hop1_concentration"] is not None and x["hop1_concentration"] > 1.5]
got["C10"] = f"{len(hc)}/16 {min(hc):.2f}–{max(hc):.2f}"
up = sum(x["pdr"] > v[0]["pdr"] for v in d["ratesweep"].values() for x in v[1:])
got["C12"] = f"{up}/18"   # condition-level part only; the seed-level part (54/54) needs per-seed data and is checked by publication/verify_published_claims.py
o50 = {x["rate"]: x["pdr"] for x in d["ratesweep"]["olsr-50"]}
got["C13"] = f"{o50[8]:.1f} {o50[4]:.1f}"
got["C14"] = f"{sum(1 for t in d['delay'] for i in range(6) if min(P, key=lambda p: d['delay'][t][p][i]['mean']) == 'static')}/18"
expect = dict(claims, C12=claims["C12"].split()[0])
diff = {k: (v, expect[k]) for k, v in got.items() if v != expect[k]}
check("T5 published claims recomputed from the JSON", not diff, f"{len(got)} claims; differ {diff}")
print("RESULT:", "all tests passed" if not fails else f"{len(fails)} failed: {fails}")
sys.exit(1 if fails else 0)
