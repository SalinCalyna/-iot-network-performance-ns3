#!/usr/bin/env python3
"""Verify every published 802.11b claim against the raw result files (stdlib only, read-only).

Run from the repository root of the PUBLIC tree after the package has been copied in:
    python3 publication/verify_published_claims.py
Checks:
  M  the package manifest (publication/MANIFEST.sha256) matches the files on disk;
  I  every input listed in the analyses' INPUTS.sha256 exists with the recorded hash;
  K  each claim in publication/CLAIMS.csv is recomputed from raw outputs and compared;
  R  every number in the README's ARP-fixed 802.11b section is backed by a claim.
Exit status 0 only if everything passes.
"""
import csv
import glob
import hashlib
import json
import math
import os
import re
import statistics as st
import sys
from collections import defaultdict

ROOT = os.getcwd()
FAIL = []


def ok(cid, cond, msg):
    print(f"{'PASS' if cond else 'FAIL'}  {cid:4} {msg}")
    if not cond:
        FAIL.append(cid)


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


# ---------------------------------------------------------------- M, I
man = [l.split("  ", 1) for l in open("publication/MANIFEST.sha256").read().splitlines()]
bad = [p for h, p in man if not os.path.exists(p) or sha(p) != h]
ok("M1", not bad, f"package manifest: {len(man)} files, {len(bad)} missing or changed {bad[:2]}")
for m in ("analysis/chapter4-tables-figures/INPUTS.sha256", "analysis/arp-fixed-throughput-delay/INPUTS.sha256"):
    rows = [l.split("  ", 1) for l in open(m).read().splitlines() if l.strip()]
    badi = [p for h, p in rows if not os.path.exists(p) or sha(p) != h]
    ok("I" + m.split("/")[1][:2], not badi, f"{m}: {len(rows)} inputs, {len(badi)} missing or changed {badi[:2]}")

# ---------------------------------------------------------------- load raw data
T975 = {2: 4.302653, 10: 2.228139}
mean = lambda xs: sum(xs) / len(xs)
ci = lambda xs: T975[len(xs) - 1] * st.stdev(xs) / math.sqrt(len(xs))
runs = {}
flag_on = 0
flag_bad = 0
for d in ("arp-a2-on", "arp-a1-on", "arp-b-on-os", "arp-b1-on", "arp-ratesweep-on", "arp-phase1-on"):
    for p in glob.glob(f"results/wifi-std/{d}/*/provenance.json"):
        rd = os.path.dirname(p)
        pv = json.load(open(p))
        a = next(csv.DictReader(open(f"{rd}/probe_aggregate.csv")))
        e = next(csv.DictReader(open(f"{rd}/wifistd_ext.csv")))
        flag_on += 1
        if not (pv["exit_code"] == 0 and "--arpPrepopulate=1" in pv["argv"] and e["arp_prepopulate"] == "1"
                and int(e["total_arp_l3_drops"]) + int(e["total_arp_cache_drops"]) == 0):
            flag_bad += 1
        runs.setdefault(d, {})[(a["protocol"], int(a["nodes"]), int(float(a["offered_rate_kbps"])), int(a["seed"]))] = (a, e, rd)
S1 = {}
for d in ("arp-a2-on", "arp-a1-on", "arp-b-on-os"):
    for k, v in runs[d].items():
        S1.setdefault(k, v)
B = {}
for d in ("arp-a2-on", "arp-a1-on", "arp-b-on-os", "arp-b1-on"):
    for k, v in runs[d].items():
        if k[0] in ("olsr", "static") and k[1] in (30, 50, 75, 100) and k[2] in (8, 16):
            B.setdefault(k, v)
RS = runs["arp-ratesweep-on"]
SEEDS = {4: [20, 25, 30], 8: [20, 25, 30], 16: list(range(20, 31))}
pdr = lambda a: 100 * int(a["rxPkts"]) / int(a["txPkts"])
gp = lambda a: int(a["rxPkts"]) * 512 * 8 / 270 / 1000
cell = lambda p, n, rt, f: mean([f(S1[(p, n, rt, s)][0]) for s in SEEDS[rt]])

V = {}  # claim id -> recomputed value (string as published)
V["C01"] = f"{len(S1)}/{len(B)}/{len(RS)}"
V["C02"] = f"{flag_on - flag_bad}/{flag_on}"
# ARP diagnostic
offr = {}
for p in glob.glob("results/wifi-std/arp-phase1-off/*/probe_aggregate.csv"):
    a = next(csv.DictReader(open(p)))
    e = next(csv.DictReader(open(p.replace("probe_aggregate", "wifistd_ext"))))
    offr[(a["protocol"], int(a["nodes"]), int(float(a["offered_rate_kbps"])), int(a["seed"]))] = (a, e)
cnt = lambda a: sum(int(a[k]) for k in ("total_mac_queue_drops", "total_max_retry_drops", "total_ip_drop_no_route", "total_ip_drop_ttl",
                                       "total_ip_drop_route_error", "total_ip_drop_queue", "total_ip_drop_other"))
rat = [100 * (int(e["total_arp_l3_drops"]) + int(e["total_arp_cache_drops"])) / (int(a["txPkts"]) - int(a["rxPkts"]) - cnt(a))
       for k, (a, e) in offr.items() if k[0] == "static"]
V["C03"] = f"{min(rat):.1f}–{max(rat):.1f}"
lead = {}
for rt in (4, 8, 16):
    for n in (10, 20, 30, 50, 75, 100):
        m = {p: cell(p, n, rt, pdr) for p in ("aodv", "olsr", "static")}
        g = {p: cell(p, n, rt, gp) for p in ("aodv", "olsr", "static")}
        lead[(rt, n)] = (max(m, key=m.get), max(g, key=g.get), m)
V["C04"] = f"{sum(1 for (rt, n), v in lead.items() if n >= 20 and v[0] == v[1] == 'static')}/15"
excl = 0
for n in (10, 20, 30, 50, 75, 100):
    for o in ("olsr", "aodv"):
        d = [gp(S1[("static", n, 16, s)][0]) - gp(S1[(o, n, 16, s)][0]) for s in range(20, 31)]
        excl += (mean(d) - ci(d)) * (mean(d) + ci(d)) > 0
V["C05"] = f"{excl}/12"
n10 = [max(v[2].values()) - sorted(v[2].values())[-2] for (rt, n), v in lead.items() if n == 10]
V["C06"] = f"{max(n10):.1f}"
sched = {p: mean([100 * int(S1[(p, 10, 16, s)][0]["rxPkts"]) / int(S1[("static", 10, 16, s)][0]["txPkts"]) for s in range(20, 31)]) for p in ("aodv", "olsr")}
V["C07"] = f"{'aodv' if sched['aodv'] > sched['olsr'] else 'olsr'} {abs(sched['aodv'] - sched['olsr']):.2f}"
plat = [mean([gp(S1[("static", n, 16, s)][0]) for s in range(20, 31)]) for n in (30, 50, 75, 100)]
V["C08"] = f"{min(plat):.0f}–{max(plat):.0f}"
gw = {}
conc = {}
for (p, n, rt, s), (a, e, rd) in B.items():
    gw.setdefault((p, n, rt), []).append(float(a["gw_airtime_busy_frac"]))
    pn = list(csv.DictReader(open(glob.glob(f"{rd}/pernode/*.csv")[0])))
    sens = [x for x in pn if x["is_gateway"] == "0"]
    le1 = [x for x in sens if 0 <= int(float(x["hop_to_gw"])) <= 1]
    mq = sum(int(x["mac_queue_drops"]) for x in sens)
    conc.setdefault((p, n, rt), []).append((len(le1) / len(sens), sum(int(x["mac_queue_drops"]) for x in le1) / mq if mq else None))
gm = {k: mean(v) for k, v in gw.items()}
V["C09"] = f"{min(v for k, v in gm.items() if k[1] >= 75):.2f}–{max(v for k, v in gm.items() if k[1] >= 75):.2f}"
cr = {}
for k, v in conc.items():
    fm = [b for a, b in v if b is not None]
    if fm:
        cr[k] = mean(fm) / mean([a for a, b in v])
hi = [x for x in cr.values() if x > 1.5]
V["C10"] = f"{len(hi)}/16 {min(hi):.2f}–{max(hi):.2f}"
exc = []
seen = set()
for d in ("arp-a2-on", "arp-a1-on", "arp-b-on-os", "arp-b1-on", "arp-ratesweep-on", "arp-phase1-on"):
    for k, (a, e, rd) in runs[d].items():
        if k[0] == "static" and k not in seen:
            seen.add(k)
            exc.append(cnt(a) - (int(a["txPkts"]) - int(a["rxPkts"])) > 0)
V["C11"] = f"{sum(exc)}/{len(exc)}"
up = sum(pdr(RS[(p, n, rt, s)][0]) > pdr(RS[(p, n, 16, s)][0]) for p in ("olsr", "static") for n in (50, 75, 100) for rt in (4, 8, 12) for s in (20, 25, 30))
cells_up = sum(mean([pdr(RS[(p, n, rt, s)][0]) for s in (20, 25, 30)]) > mean([pdr(RS[(p, n, 16, s)][0]) for s in (20, 25, 30)])
               for p in ("olsr", "static") for n in (50, 75, 100) for rt in (4, 8, 12))
V["C12"] = f"{cells_up}/18 {up}/54"
V["C13"] = f"{mean([pdr(RS[('olsr', 50, 8, s)][0]) for s in (20, 25, 30)]):.1f} {mean([pdr(RS[('olsr', 50, 4, s)][0]) for s in (20, 25, 30)]):.1f}"
dl = sum(1 for rt in (4, 8, 16) for n in (10, 20, 30, 50, 75, 100)
         if min(("aodv", "olsr", "static"), key=lambda p: cell(p, n, rt, lambda a: float(a["avgDelaySec"]))) == "static")
V["C14"] = f"{dl}/18"
# V4 (original configuration, public data)
v3 = {}
for p in glob.glob("results/v3-ext/static_*_*_*.csv"):
    for r in csv.DictReader(open(p)):
        if 20 <= int(r["Seed"]) <= 30:
            v3[(int(r["NumberOfNodes"]), r["TrafficLevel"], r["MobilityMode"], int(r["Seed"]))] = r
dd = [float(r["PDR"]) - float(v3[(int(r["NumberOfNodes"]), r["TrafficLevel"], r["MobilityMode"], int(r["Seed"]))]["PDR"])
      for p in glob.glob("results/v4-matched/*.csv") for r in csv.DictReader(open(p))]
h = 1.96 * st.stdev(dd) / math.sqrt(len(dd))
V["C15"] = f"{mean(dd):+.2f} [{mean(dd) - h:+.2f}, {mean(dd) + h:+.2f}] n={len(dd)}"
rc = list(csv.DictReader(open("analysis/final-reproducibility-check/reproducibility_comparison.csv")))
V["C16"] = f"{sum(r['status'] == 'PASS' for r in rc)}/{sum(r['status'] in ('PASS', 'FAIL') for r in rc)}"

sent = {}
for p in glob.glob("results/v3-ext/*_*_*_*.csv"):
    m = re.match(r".*/(aodv|olsr|static)_(\d+)_(low|medium|high)_(static|low|medium)\.csv$", p)
    if m:
        for r in csv.DictReader(open(p)):
            if 20 <= int(r["Seed"]) <= 30:
                sent[(m.group(1), int(m.group(2)), m.group(3), m.group(4), int(r["Seed"]))] = int(r["PacketsSent"])
fro = max(100 * (1 - v / sent[("static",) + k[1:]]) for k, v in sent.items() if k[0] == "olsr")
fix = max(100 * (1 - int(a["txPkts"]) / int(S1[("static",) + k[1:]][0]["txPkts"])) for k, (a, e, rd) in S1.items() if k[0] == "olsr")
V["C17"] = f"{fro:.1f}/{fix:.1f}"
# Static at N = 10: sensors without a path on the 90 m disk model (no installed route). The count is a property of
# the topology, so it must be equal for the three protocols, and it must match the per-node hop data (hop_to_gw < 0).
un = lambda k: int(S1[k][0]["unreachableSensors"])
topo = all(len({un((p,) + k[1:]) for p in ("aodv", "olsr", "static")}) == 1 for k in S1 if k[0] == "static")
s10 = [(un(k), pdr(a), rd) for k, (a, e, rd) in S1.items() if k[0] == "static" and k[1] == 10]
hop_ok = all(x == sum(1 for r in csv.DictReader(open(glob.glob(f"{rd}/pernode/*.csv")[0]))
                      if r["is_gateway"] == "0" and int(float(r["hop_to_gw"])) < 0) for x, y, rd in s10)
mx, my = mean([x for x, y, rd in s10]), mean([y for x, y, rd in s10])
r10 = sum((x - mx) * (y - my) for x, y, rd in s10) / math.sqrt(sum((x - mx) ** 2 for x, y, rd in s10) * sum((y - my) ** 2 for x, y, rd in s10))
st10 = [cell("static", 10, rt, pdr) for rt in (4, 8, 16)]
dy10 = [cell(p, 10, rt, pdr) for p in ("aodv", "olsr") for rt in (4, 8, 16)]
u = {n: mean([un(("static", n, 16, s)) for s in range(20, 31)]) for n in (10, 20)}
h16 = sorted((un(("static", 10, 16, s)), pdr(S1[("static", 10, 16, s)][0])) for s in range(20, 31))   # fewest / most such sensors
V["C18"] = (f"{min(st10):.1f}–{max(st10):.1f} {min(dy10):.1f}–{max(dy10):.1f} {u[10]:.1f} {u[20]:.1f} "
            f"{max(un(k) for k in S1 if k[1] >= 50)} {r10:.2f} n={len(s10)} {h16[0][1]:.1f}/{h16[0][0]} {h16[-1][1]:.1f}/{h16[-1][0]}"
            if topo and hop_ok else f"inconsistent sensor counts (topology {topo}, per-node {hop_ok})")
claims = list(csv.DictReader(open("publication/CLAIMS.csv")))
for c in claims:
    got = V.get(c["id"])
    ok(c["id"], got == c["published_value"], f"{c['claim'][:70]} | published {c['published_value']} | recomputed {got}")
    for f in c["evidence_files"].split(";"):
        f = f.strip()
        if f and not glob.glob(f):
            ok(c["id"] + "f", False, f"evidence path missing: {f}")

# ---------------------------------------------------------------- R: numbers in the proposed README section are backed
txt = open("README.md", encoding="utf-8").read()
sec = txt[txt.index("### IEEE 802.11b study: ARP-fixed results"): txt.index("### Original IEEE 802.11b results")]
backed = " ".join(c["published_value"] + " " + c["also_backs"] for c in claims)
nums = set(re.findall(r"\d[\d,]*(?:\.\d+)?", re.sub(r"\]\([^)]*\)|`[^`]*`|802\.11\w*|N = \d+|k = \d|\b20\d\d-\d\d-\d\d\b|\b(?:January|February|March|April|May|June|July|August|September|October|November|December) 20\d\d\b|C\d\d", " ", sec)))
unb = sorted(n for n in nums if n.replace(",", "") not in backed.replace(",", ""))
ok("R1", not unb, f"numbers in the README ARP-fixed findings not backed by a claim: {unb}")
print("RESULT:", "all checks passed" if not FAIL else f"{len(FAIL)} failed: {FAIL}")
sys.exit(1 if FAIL else 0)
