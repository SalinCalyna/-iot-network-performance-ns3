#!/usr/bin/env python3
"""End-to-end verification of the public dashboard (read-only on data).

    python3 -I -B experiments/dashboard/verify_dashboard.py <rendered DOM html> <browser_check out dir> [base ref]

base ref (default github/main): the previously published site, used to check that its numbers are preserved.
Checks
  D1 final_research.json = frozen package (audit_final_research_json.py)
  D2 v3ext-stats.json is current (build_v3_site_stats.py --check)
  D3 wifi6-risk.json and the Wi-Fi 6 figures rebuild byte-identical from the committed package (build_site_wifi6.py)
  D4 every number in the page outside the data-driven Wi-Fi 6 tables is traceable to an authoritative source
  D5 every number of the previously published page is still present, except the audited corrections
  D6 corrected claims are gone (audit F1-F3, stale wording)
  D7 required Wi-Fi 6 values are displayed (N = 30, k = 3 paired differences and 95 % CIs)
  D8 no p-value or significance wording is attached to an N = 100 statement
  D9 browser QA: no console errors, failed requests, broken images, unresolved anchors, overflow at any width,
     unnamed charts or axe WCAG 2 A/AA violations
  D10 structural preservation vs the published page: every element id, section, data-target, external link and
      h2/h3 heading still exists (headings may change only through the explicit RENAMES map)
  Also writes <qa dir>/changed_sentences.txt: every sentence of the published page's visible text that is no longer
  present verbatim, for manual review of wording changes (not machine-judged).
"""
import glob
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ok_all = True


def check(name, ok, detail=""):
    global ok_all
    ok_all &= bool(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


def run(cmd):
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip().splitlines()[-1:] or [""]


def visible_text(h):
    h = re.sub(r"<(script|style|svg|head)[^>]*>.*?</\1>", " ", h, flags=re.S)
    h = re.sub(r'\s(href|src|style|class|id|viewBox|d|transform|data-[a-z-]+|width|height|x|y|r|cx|cy|alt|aria-[a-z]+|role|tabindex|for|rel|target|title|type)="[^"]*"', "", h)
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h)))


norm = lambda t: t.replace(",", "").rstrip(".")
nums = lambda t: {norm(x) for x in re.findall(r"\d[\d,]*\.?\d*", t)}


def main():
    dom_p, qa_dir = Path(sys.argv[1]), Path(sys.argv[2])
    base_ref = sys.argv[3] if len(sys.argv) > 3 else "github/main"
    dom = dom_p.read_text()
    # D1-D3
    rc, last = run([sys.executable, "-I", "-B", "experiments/dashboard/audit_final_research_json.py"])
    check("D1 final_research.json = frozen package", rc == 0, last[0])
    rc, last = run([sys.executable, "-I", "-B", "experiments/build_v3_site_stats.py", "--check"])
    check("D2 v3ext-stats.json current", rc == 0, last[0])
    tmp = Path(tempfile.mkdtemp()) / "site"
    shutil.copytree(ROOT / "site", tmp)
    rc, last = run([sys.executable, "-I", "-B", "experiments/wifi6-risk/build_site_wifi6.py", str(tmp)])
    same = rc == 0 and (tmp / "data/wifi6-risk.json").read_bytes() == (ROOT / "site/data/wifi6-risk.json").read_bytes() and all(
        (tmp / "images/wifi6" / f.name).read_bytes() == f.read_bytes() for f in (ROOT / "site/images/wifi6").glob("*.png"))
    check("D3 Wi-Fi 6 data and figures rebuild byte-identical", same, last[0][:90])
    # D4 traceability (data-driven Wi-Fi 6 tables are verified by verify_site_wifi6.py; their values come from D3)
    page = dom
    for tid in re.findall(r'<table class="data" id="(w6-[^"]+)"', page):
        page = re.sub(r'(id="%s"[^>]*>).*?(</table>)' % tid, r"\1\2", page, flags=re.S)
    page = re.sub(r"<figcaption>.*?</figcaption>", " ", page, flags=re.S)
    # the V3 statistics explorer and the SQL data explorer render database rows (checked by D1/D2), not prose
    for tid in ("v3s-table", "de-result", "risk-high-list", "risk-low-list", "risk-na-list", "health-panel", "health-note", "risk-context"):
        page = re.sub(r'(id="%s"[^>]*>).*?(</(?:table|div)>)' % tid, r"\1\2", page, count=1, flags=re.S)
    text = visible_text(page)
    src = ""
    for f in (glob.glob(str(ROOT / "analysis/final-report-data/*")) + glob.glob(str(ROOT / "analysis/bottleneck-characterisation/*.md"))
              + glob.glob(str(ROOT / "analysis/bottleneck-characterisation/T_*.csv")) + glob.glob(str(ROOT / "analysis/update8-tier1-activation/*.[mc][ds]*"))
              + glob.glob(str(ROOT / "analysis/final-reproducibility-check/*.[mt][dx]*")) + glob.glob(str(ROOT / "analysis/wifi6-risk-writeup/*.md"))
              + glob.glob(str(ROOT / "analysis/dashboard-audit/*.md")) + glob.glob(str(ROOT / "docs/*.md")) + [str(ROOT / "README.md")]
              + glob.glob(str(ROOT / "site/data/*.json"))):
        src += Path(f).read_text(errors="ignore")
    srcn = nums(src) | {x.rstrip("0").rstrip(".") for x in nums(src) if "." in x}
    page_n = [norm(x) for x in re.findall(r"\d[\d,]*\.?\d*", text)]
    exact_miss = sorted({x for x in page_n if x not in srcn and x.rstrip("0").rstrip(".") not in srcn})
    # values rendered by app.js / wifi6.js are source values formatted with toFixed(d); also allow the x100 / x1000
    # unit conversions used by the charts (fraction -> %, s -> ms). A token is traced when some source value rounds to it.
    vals = sorted({float(x) for x in srcn if x.replace(".", "", 1).isdigit()})
    import bisect
    def rounds_to(tok):
        d = len(tok.split(".")[1]) if "." in tok else 0
        t, h = float(tok), 0.5 * 10 ** -d + 1e-9
        for sc in (1, 100, 1000):
            lo, hi = (t - h) / sc, (t + h) / sc
            i = bisect.bisect_left(vals, lo)
            if i < len(vals) and vals[i] <= hi:
                return True
        return False
    untraced = [x for x in exact_miss if not rounds_to(x)]
    rounded = len(exact_miss) - len(untraced)
    check("D4 every displayed number traceable to authoritative sources", not untraced,
          f"{len(page_n)} numeric tokens ({rounded} as rounded data values)" + (f"; untraced {untraced}" if untraced else ""))
    # D5 preservation
    base = subprocess.run(["git", "show", f"{base_ref}:site/index.html"], cwd=ROOT, capture_output=True, text=True).stdout
    cur = (ROOT / "site/index.html").read_text()
    corrected = {"1.2"}   # audit F2: "1.2–2.4×" replaced by "1.4–2.4× in 11 of 16 cells"
    lost = sorted(nums(visible_text(base)) - nums(visible_text(cur)) - corrected)
    check("D5 numbers of the published page preserved (except audited corrections)", not lost,
          f"base {base_ref}" + (f"; missing {lost}" if lost else ""))
    # D6 corrected / stale claims
    gone = ["10 of the 12", "dominant in 10 / 12", "1.2–2.4", "Exactly five findings", "(proposed) risk-aware",
            "Next</span><span class=\"sc-val direction\">→ BA", "RQ6–RQ7 define the planned", ">High Risks<", ">Low Risks<"]
    still = [g for g in gone if g in cur]
    check("D6 audited errors and stale wording removed", not still, ", ".join(still))
    # D7 required values
    req = ["+23.18", "+19.81", "+26.54", "46.33", "−53.21", "−39.46", "0.00195", "0.0117"]
    vt = visible_text(dom)
    miss = [r for r in req if r not in vt]
    check("D7 N=30 k=3 paired results displayed", not miss, ", ".join(miss) or "PDR +23.18 [+19.81, +26.54]; exposure −46.33 [−53.21, −39.46]")
    # D8 N = 100 without p-values
    sents = re.split(r"(?<=[.;])\s+", vt)
    bad = [s for s in sents if re.search(r"N\s*=\s*100", s) and re.search(r"\bp\s*=|significan(t|ce)(?! is claimed| claimed)|statistically significant", s)
           and "no significance" not in s and "without a significance" not in s and "No significance" not in s]
    check("D8 no p-value / significance attached to N = 100", not bad, " | ".join(b[:120] for b in bad[:3]))
    # D9 browser QA
    reps = [json.loads(Path(f).read_text()) for f in sorted(glob.glob(str(qa_dir / "report-*.json")))]
    probs = []
    for r in reps:
        w = r["width"]
        for k in ("consoleMsgs", "exceptions", "logErrors", "httpErrors", "failed", "brokenImgs", "badAnchors", "badTargets", "overflow"):
            if r[k]: probs.append(f"{w}px {k}: {r[k][:2]}")
        if r["docWidth"] > r["viewport"]: probs.append(f"{w}px overflow {r['docWidth'] - r['viewport']}px")
        if r["chartsWithoutName"]: probs.append(f"{w}px unnamed charts {r['chartsWithoutName']}")
        if r.get("axe"): probs += [f"{w}px axe {v['id']}({v['nodes']})" for v in r["axe"]]
    check("D9 browser QA clean at " + "/".join(str(r["width"]) for r in reps) + " px", reps and not probs, "; ".join(probs[:6]))
    # D10 structure
    RENAMES = {"Risk Summary": "Performance Health Check", "High Risks": "Strained metrics", "Low Risks": "Within typical range"}
    ids = lambda h: set(re.findall(r'\bid="([^"]+)"', h))
    tg = lambda h: set(re.findall(r'data-target="([^"]+)"', h))
    ext = lambda h: set(re.findall(r'href="(https?://[^"]+)"', h))
    heads = lambda h: {html.unescape(re.sub(r"<[^>]+>", "", m)).strip() for m in re.findall(r"<h[23][^>]*>(.*?)</h[23]>", h, re.S)}
    miss = [f"id {i}" for i in sorted(ids(base) - ids(cur))] + [f"target {t}" for t in sorted(tg(base) - tg(cur))] \
        + [f"link {u}" for u in sorted(ext(base) - ext(cur))] \
        + [f"heading {h}" for h in sorted(heads(base) - heads(cur)) if RENAMES.get(h) not in heads(cur)]
    check("D10 structure of the published page preserved", not miss,
          f"{len(ids(base))} ids, {len(tg(base))} nav targets, {len(ext(base))} external links, {len(heads(base))} headings"
          + (f"; missing {miss[:8]}" if miss else ""))
    sent = lambda t: {x.strip() for x in re.split(r"(?<=[.!?])\s+", t) if len(x.strip()) > 25}
    changed = sorted(sent(visible_text(base)) - sent(visible_text(cur)))
    (qa_dir / "changed_sentences.txt").write_text("\n".join(changed) + "\n")
    print(f"  INFO  {len(changed)} sentences of the published page changed or removed -> {qa_dir / 'changed_sentences.txt'} (manual review)")
    print("ALL PASS" if ok_all else "FAILURES")
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
