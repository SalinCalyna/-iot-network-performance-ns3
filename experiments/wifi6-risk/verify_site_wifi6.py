#!/usr/bin/env python3
"""Verify the Wi-Fi 6 dashboard sections against the validated sources (read-only).

    python3 -I -B experiments/wifi6-risk/verify_site_wifi6.py <site dir> <rendered DOM html> <base index.html>

Checks
  V1 every source file listed in data/wifi6-risk.json still has the recorded sha256
  V2 JSON numeric blocks equal the analysis CSVs (stats_by_config.csv, paired_riskaware_vs_static.csv)
  V3 JSON report tables equal the T-W*.csv files cell for cell
  V4 every rendered table cell of the raw-table panels equals the JSON table cell
  V5 every number in the rendered Wi-Fi 6 text (outside raw tables) is traceable: it equals a JSON value at the
     displayed precision, or a number in the static section text that appears in TABLES.md / FIGURES.md
  V6 no p-value or significance wording is rendered for N = 100
  V7 existing dashboard: the base index.html with the inserted Wi-Fi 6 block, nav group, chip, story node and
     script tag removed is identical to the original; dashboard.css only appended
  V8 every in-page anchor (href="#...") and data-target resolves; every local src/href file exists
"""
import csv
import hashlib
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ok_all = True


def check(name, ok, detail=""):
    global ok_all
    ok_all &= bool(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


def rows(p):
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


def main():
    site, dom_p, base_p = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    J = json.loads((site / "data/wifi6-risk.json").read_text())
    dom = dom_p.read_text()
    # V1
    bad = [p for p, h in J["sources"].items() if hashlib.sha256((ROOT / p).read_bytes()).hexdigest() != h]
    check("V1 source sha256 unchanged", not bad, f"{len(J['sources'])} files" + (f"; changed {bad}" if bad else ""))
    # V2
    nbad, ncheck = [], 0
    for n, b in J["batches"].items():
        bd = ROOT / "results/wifi6-risk" / b["batch"] / "analysis"
        st = {(r["protocol"], int(r["k"])): r for r in rows(bd / "stats_by_config.csv")}
        for c in b["configs"]:
            for m in J["metrics"]:
                ref = [float(st[(c["protocol"], c["k"])][f"{m['key']}_{x}"]) for x in ("mean", "sd", "ci95_lo", "ci95_hi")]
                ncheck += 1
                if c[m["key"]] != ref:
                    nbad.append((n, c["protocol"], c["k"], m["key"]))
        pr = {(int(r["k"]), r["metric"]): r for r in rows(bd / "paired_riskaware_vs_static.csv")}
        for x in b["paired"]:
            r = pr[(x["k"], x["metric"])]
            ncheck += 1
            ref = [float(r[k]) for k in ("diff_mean", "diff_sd", "diff_ci95_lo", "diff_ci95_hi")]
            if x["diff"] != ref or x["higher"] != int(r["pairs_riskaware_higher"]):
                nbad.append((n, x["k"], x["metric"]))
            if b["inferential"] and x["p_wilcoxon"] != float(r["p_wilcoxon_exact"]):
                nbad.append((n, x["k"], x["metric"], "p"))
    check("V2 JSON numbers = analysis CSVs", not nbad, f"{ncheck} blocks" + (f"; mismatches {nbad[:5]}" if nbad else ""))
    # V3
    tbad = []
    for name, t in J["tables"].items():
        with open(ROOT / "analysis/wifi6-risk-writeup/tables" / f"{name}.csv", newline="") as f:
            r = list(csv.reader(f))
        if [t["header"]] + t["rows"] != r:
            tbad.append(name)
    check("V3 JSON tables = T-W*.csv", not tbad, f"{len(J['tables'])} tables" + (f"; differ {tbad}" if tbad else ""))
    # V4
    tid = {"w6-t-params": "T-W1_parameters", "w6-t-aodv-a": "T-W6a_aodv_vs_olsr_n100", "w6-t-aodv-b": "T-W6b_aodv_diagnostic_seed20",
           "w6-t-aodv-c": "T-W6c_aodv_findings_status", "w6-t-ba-a": "T-W2a_ba_defect_n30", "w6-t-ba-b": "T-W2b_residual_tail_n100_64k",
           "w6-t-ba-c": "T-W2c_tail_mechanisms", "w6-t-ba-d": "T-W2d_validation", "w6-t-load": "T-W3_load_calibration",
           "w6-t-lim": "T-W7_limitations"}
    cbad, ncell = [], 0
    for el, name in tid.items():
        m = re.search(r'id="%s"[^>]*>(.*?)</table>' % el, dom, re.S)
        body = m.group(1).split("<tbody>")[1]
        got = [[html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
               for tr in re.findall(r"<tr>(.*?)</tr>", body, re.S)]
        t = J["tables"][name]
        want = [[r[i] for i in range(len(r))] if el != "w6-t-lim" else r[:3] for r in t["rows"]]
        ncell += sum(len(r) for r in got)
        if got != [[c.strip() for c in r] for r in want]:
            cbad.append(el)
    check("V4 rendered raw tables = JSON tables", not cbad, f"{ncell} cells" + (f"; differ {cbad}" if cbad else ""))
    # V5: traceability of every number in rendered Wi-Fi 6 text outside the raw tables
    start, end = dom.index('id="view-w6-overview"'), dom.index('id="view-data-explorer"')
    sec = dom[start:end]
    for el in tid:
        sec = re.sub(r'(id="%s"[^>]*>).*?(</table>)' % el, r"\1\2", sec, flags=re.S)
    sec = re.sub(r"<figcaption>.*?</figcaption>", "", sec, flags=re.S)   # captions verbatim from FIGURES.md (checked below)
    sec = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", sec, flags=re.S)
    sec = re.sub(r'(href|src|id|class|data-[a-z]+|style|alt)="[^"]*"', "", sec)
    text = html.unescape(re.sub(r"<[^>]+>", " ", sec))
    vals = set()

    def add(x):
        for d in range(0, 5):
            vals.add(f"{abs(x):.{d}f}")
        vals.add(f"{abs(x):.3g}")
    for b in J["batches"].values():
        for s in b["seeds"]:
            vals.add(str(s))
        vals.update({str(b["n_seeds"]), str(b["n_sensors"])})
        for k_, v in b["denominators"].items():
            add(float(v))
        for c in b["configs"]:
            for m in J["metrics"]:
                for v in c[m["key"]]:
                    add(v)
        for x in b["paired"]:
            for v in x["diff"] + [x["static_mean"], x["riskaware_mean"], x.get("p_wilcoxon") or 0, x.get("p_holm") or 0,
                                  x.get("cohen_dz") or 0, x["higher"], x["equal"], x["lower"], x["n_pairs"], x["k"]]:
                add(float(v))
            for t in x.get("per_seed", "").split():
                add(float(t.split(":")[1]))
    for h in J["hop_check"]:
        for v in h["delivered"] + h["all_sent"]:
            add(v)
    for t in J["tables"].values():
        for r in t["rows"]:
            for c in r:
                for tok in re.findall(r"\d[\d,]*\.?\d*", c):
                    vals.add(tok.replace(",", ""))
    vals.add(str(sum(b["denominators"]["runs"] for b in J["batches"].values())))
    docs = "".join((ROOT / "analysis/wifi6-risk-writeup" / f).read_text() for f in ("TABLES.md", "FIGURES.md", "N100_AODV_SECTION.md"))
    docnums = {t.replace(",", "") for t in re.findall(r"\d[\d,]*\.?\d*", docs)}
    toks = [t.replace(",", "") for t in re.findall(r"\d[\d,]*\.?\d*", text)]
    untraced = sorted({t for t in toks if t.rstrip(".") not in vals and t.rstrip(".") not in docnums})
    check("V5 every rendered number traceable to JSON / validated docs", not untraced,
          f"{len(toks)} numeric tokens" + (f"; untraced {untraced}" if untraced else ""))
    caps = re.findall(r"<figcaption><strong>(F-W\d)\.</strong> (.*?) <span", dom[start:end], re.S)
    capbad = [c for c, t in caps if html.unescape(t).strip() not in [f["caption"] for f in J["figures"].values()]]
    check("V5b figure captions = FIGURES.md", len(caps) == 8 and not capbad, f"{len(caps)} captions")
    # V6
    m = re.search(r'id="w6-pair-table"[^>]*>(.*?)</table>', dom, re.S)
    ptxt = m.group(1)
    check("V6 default paired view is N = 30 with tests", "Wilcoxon p" in ptxt)
    n100 = [x for x in J["batches"]["100"]["paired"] if any(k in x for k in ("p_wilcoxon", "p_holm", "cohen_dz"))]
    sig = re.findall(r"N = 100[^.]*?(significan|p =)", text)
    check("V6 no test statistics stored or rendered for N = 100", not n100 and not sig and not J["batches"]["100"]["inferential"])
    # V7
    cur = (site / "index.html").read_text()
    base = base_p.read_text()
    stripped = cur
    s0, s1 = stripped.index("      <!-- ============================================================ WI-FI 6 RISK-AWARE ROUTING"), \
        stripped.index('      <section class="view" id="view-data-explorer">')
    stripped = stripped[:s0] + stripped[s1:]
    stripped = re.sub(r'    <div class="navgroup phase-measured">\n      <div class="glabel">Wi-Fi 6 Risk-Aware Routing — Measured</div>.*?</div>\n\n', "", stripped, flags=re.S)
    stripped = stripped.replace('\n        <span class="chip ok">● WI-FI 6 RISK STUDY MEASURED</span>', "")
    stripped = stripped.replace('\n          <a href="#view-w6-overview" class="story-node done"><span class="story-num">8</span>Wi-Fi 6 Risk-Aware Routing (Measured)</a>', "")
    stripped = stripped.replace('\n<script src="wifi6.js"></script>', "")
    check("V7 existing index.html content unchanged (only insertions)", stripped == base)
    css_base = (base_p.parent / "dashboard.css").read_text()
    check("V7 dashboard.css only appended", (site / "dashboard.css").read_text().startswith(css_base))
    # V8
    ids = set(re.findall(r'\bid="([^"]+)"', dom))
    hrefs = set(re.findall(r'href="#([^"]+)"', cur)) | set(re.findall(r'data-target="([^"]+)"', cur))
    missing = sorted(h for h in hrefs if h not in ids)
    check("V8 in-page anchors and nav targets resolve", not missing, f"{len(hrefs)} targets" + (f"; missing {missing}" if missing else ""))
    local = set(re.findall(r'(?:src|href)="((?!https?:|#|data:|mailto:)[^"]+)"', dom))
    lmiss = sorted(p for p in local if not (site / p.split("?")[0]).exists())
    check("V8 local files referenced by the page exist", not lmiss, f"{len(local)} files" + (f"; missing {lmiss}" if lmiss else ""))
    print("ALL PASS" if ok_all else "FAILURES")
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
