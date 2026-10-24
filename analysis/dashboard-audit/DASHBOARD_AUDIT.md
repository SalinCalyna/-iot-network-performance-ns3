# Dashboard audit (Phase 1, before changes) — 2026-10-25

Scope: `site/index.html`, `site/*.js`, `site/dashboard.css`, `site/data/*.json`, at commit `f77073c80` (the
live dashboard). Read-only: nothing was changed during this audit. Tools added for it:
`experiments/dashboard/audit_final_research_json.py` and `experiments/dashboard/browser_check.mjs`.

## 1. Authoritative data per research phase

| Phase | Dashboard data | Authoritative source | Check | Result |
|---|---|---|---|---|
| V3 baseline (IEEE 802.11b, 1,782 runs) | `final_research.json` → `baseline` | `analysis/final-report-data/v3_core_results.csv` | field by field | all match (delay and jitter stored in ms, CSV in s) |
| V3 95 % CI layer | `v3ext-stats.json` | `results/v3-ext/*.csv` via `experiments/build_v3_site_stats.py` | `--check` rebuild | up to date |
| V4 matched (594 rows) and Tier-1 screen (66 runs) | `v4_matched`, `v4_tier1` | `v4_results.csv` | field by field | all match |
| Bottleneck characterisation (176 runs) | `bottleneck`, `hopbin` | `bottleneck_results.csv`, `T_probe_hopbin_by_cell.csv` | field by field | all match |
| Retry-exhaustion validation (36 runs) | `retry` | `retry_results.csv` | field by field | all match |
| Offered-rate intervention (72 runs) | `ratesweep` | `rate_sweep_results.csv` | field by field | all match |
| Static/N = 50 negative control (12 runs) | `diagnostic` | `static_n50_diagnostic.csv` | field by field | all match |
| Wi-Fi 6 Risk-Aware Routing (208 runs) and AODV diagnostic (2 runs) | `wifi6-risk.json` | Wi-Fi 6 analysis outputs (sha256-listed) | `verify_site_wifi6.py` | 12/12 checks passed |
| BA topology (Phase 8) | — | none (proposed, not run) | — | no data, correctly so |

`final_research.json`: **850/850 values match** the package. 70 distinct numbers are typed directly into
`index.html` outside the Wi-Fi 6 sections, and all 70 are found in the authoritative sources. The only one not
found verbatim, "−7.6 pp" for Static/N = 50, is −7.61 pp in `rate_sweep_results.csv`, correctly rounded.

## 2. Factual errors (claims that contradict the authoritative CSV data)

| # | Where | Displayed claim | Authoritative data | Origin |
|---|---|---|---|---|
| F1 | Retry section: key finding and insight card | MAC-queue overflow "dominates loss in 10 of the 12 measured cells" | `retry_results.csv`: queue share > retry share in **7 / 12** cells (all six high-traffic cells, plus OLSR N = 100 medium); the CSV's own `interpretation` column agrees | `FINAL_REPORT_DATA_PACKAGE.md` line 93 ("10/12") |
| F2 | Bottleneck section (operating-region row, list, text) | MAC-queue drops "1.2–2.4× over-represented at hop ≤ 1", stated in the package for "all 16 cells" | `bottleneck_results.csv` `macq_concentration_ratio`: **1.38–2.39 in 11 cells**; **below 1** in OLSR N = 30 high (0.67) and OLSR N = 50 medium (0.37); **no MAC-queue drops** in 3 medium-traffic cells | package line 42 / 92 (also copied into README Finding 3) |
| F3 | Findings section 02, bottleneck text | "gateway airtime reaching 0.86–0.89 at N ≥ 75 under high traffic" (protocol not stated) | true for **OLSR** (0.8638, 0.8893). Static at N = 75/100 high is 0.62–0.66 | package line 92 (also README Finding 3) |

## 3. Definition / clarity issues (numbers correct, meaning unclear)

| # | Where | Issue |
|---|---|---|
| C1 | Intervention callout | "+25.5 % throughput at 12 kbps" (OLSR N = 100) is the mean of per-seed changes (+43.8, +23.3, +9.5 %). The change in the seed-mean throughput, as in `rate_sweep_results.csv`, is **+24.34 %**. The definition is not stated |
| C2 | Network Health panel | Status labels use dashboard-defined thresholds. Only the airtime thresholds are disclosed, PDR / MAC-queue thresholds and bar scaling are not, and Throughput is always labelled "normal" |
| C3 | "Risk Summary" section | Uses "High Risk / Low Risk" for *performance* classification of the 802.11b baseline. The Wi-Fi 6 study uses "risk" for HIGH_RISK relay *nodes*. The section names only the BA study as unrelated |
| C4 | CI caption on all V3 charts | Always says "n = 11 seeds, df = 10", although some points have n = 10 (one seed excluded, disclosed only in a note and the tooltip) |
| C5 | V3 line charts | Node counts 10, 20, 30, 50, 75, 100 are drawn at equal spacing, which distorts the slope between 50, 75 and 100 |
| C6 | All SVG charts | No axis titles. Units appear only in panel subtitles and tooltips |
| C7 | Protocol colours | 802.11b SVG charts use OLSR = blue, Static = green, AODV = orange. The Wi-Fi 6 figures use Static = blue, Risk-Aware = orange, OLSR = green, AODV = red. The same protocol has different colours in different sections |
| C8 | V4 vs Wi-Fi 6 | No statement that the Wi-Fi 6 Risk-Aware gain comes from a risk-weighted Dijkstra with oracle risk knowledge, not from the V4 sigmoid mechanism (closed, negative) |

## 4. Stale content (written before the Wi-Fi 6 study was completed)

- Hero subtitle: "(proposed) risk-aware routing strategies". Status strip: "Next → BA Risky-Node Study";
  "Research Status" card has no Wi-Fi 6 entry. Sidebar footer: "802.11b Multi-hop Mesh · … Phase 8 Proposed".
- Research Questions: RQ6 "Planned", although the Wi-Fi 6 study answers it on the 802.11ax mesh (k = 0 vs 1–3).
  RQ7 (sigmoid routing under risk) remains unanswered, and the page should say the Wi-Fi 6 study does not answer it.
- Experimental Design: "explicit per-node low/high-risk states … has not yet been run". This is still true for BA,
  but such states have since been run on the wireless mesh.
- V4 section: "The active next research direction is the BA Risky Nodes phase".
- Findings: "Exactly five findings"; no Wi-Fi 6 finding; "05 — NEXT PHASE" points to BA only.
- Roadmap: no Wi-Fi 6 entry (completed) and no N = 100 saturated experiment (not run).

## 5. Claims verified as correct (semantic, not only numeric)

- NO_ROUTE / ROUTE_ERROR < 2 % of loss in every cell: maximum 1.57 % (OLSR N = 100 high).
- Rate intervention monotonic in every seed: 6/6 OLSR seed series at N = 75 and N = 100 rise at each rate step.
- Static/N = 50 flat to negative: all 9 per-seed changes vs 16 kbps are negative.
- Retry averages: mean retry share 6.0 %, mean queue share 17.15 % (unweighted over 12 cells, labelled "Avg.").
- Wi-Fi 6, N = 30, k = 3:
  - PDR +23.18 pp, 95 % CI [+19.81, +26.54];
  - exposure −46.33 pp, 95 % CI [−53.21, −39.46];
  - exact Wilcoxon p = 0.00195, Holm-adjusted p = 0.0117;
  - N = 100 has no p-values.

## 6. Usability and accessibility (`browser_check.mjs`, before)

| Check | 1440 px | 768 px | 390 px |
|---|---|---|---|
| Console errors / exceptions / failed requests | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| Horizontal overflow | 0 px | 0 px | **235 px** (Performance table, V4 table) |
| Broken images / unresolved anchors | 0 / 0 | 0 / 0 | 0 / 0 |
| Text below 11 px (rendered) | 597 nodes | 440 | 669 |
| Charts without accessible name | 22/22 | 22/22 | 22/22 |
| axe WCAG 2 A/AA violations | color-contrast 84 · link-in-text-block 8 · select-name 7 · aria-command-name 7 (map markers) · scrollable-region-focusable 5 · label 1 | similar | similar (scrollable-region 14) |

**U1 (visual defect, live):** `.hero` uses a CSS `mask-image` meant to fade its decorative grid background. The
mask applies to the whole element, so the overview KPI cards (1,782 / 594 / 176 / 681/681) and the story rail render
nearly transparent (see `before` screenshots).

Visible "undefined" text appears only in intended methodology wording ("undefined because no packets were
received"), not as a rendering defect. Navigation items are `<div>`s with click handlers: they can't be reached by
keyboard and are not real links.

## 7. Not changed by design

Frozen data files, the Final Report Data Package, simulator sources and raw results. The package-text
inconsistencies F1–F3 are reported here; the package itself is frozen and is not edited. The published README
repeats F2 and F3 and needs a separate correction.

## 8. After the redesign (Phase 4 results, same tools)

| Check | 1440 px | 768 px | 390 px |
|---|---|---|---|
| Console errors / exceptions / failed requests | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| Horizontal overflow | 0 px | 0 px | 0 px (was 235 px) |
| Broken images / unresolved anchors | 0 / 0 | 0 / 0 | 0 / 0 |
| Text below 11 px | 13 nodes (was 597) | 6 (was 440) | 17 (was 669) |
| Charts without accessible name | 0/22 (was 22/22) | 0/22 | 0/22 |
| axe WCAG 2 A/AA violations | **0** | **0** | **0** |

`experiments/dashboard/verify_dashboard.py` (D1–D9): all pass. Data integrity, traceability of all 1,282 displayed
numbers, preservation of every previously published number except the audited correction, removal of F1–F3 and stale
wording, the required Wi-Fi 6 values, no N = 100 significance claim, and clean browser QA.
`experiments/wifi6-risk/verify_site_wifi6.py`: V1–V6 and V8 pass. V7 ("existing sections unchanged since the Wi-Fi 6
insert") fails by design, because this redesign edits existing sections; D5/D6 replace it.

Remaining known limitations: chart tooltips are mouse/touch only (values are also in the tables and captions);
the decorative IoT diagram and some inline `<code>` render slightly below 11 px; the Research Phases table needs
horizontal scrolling at 390 px.

## 9. Corrections applied (before → after) and their authoritative sources

The frozen research documents are **not** modified: `analysis/final-report-data/` (including
`FINAL_REPORT_DATA_PACKAGE.md`, lines 42, 51, 92, 93), the published README and all data files keep their
original text and bytes. Only the dashboard's wording changes.

| # | Dashboard text before | Dashboard text after | Authoritative values |
|---|---|---|---|
| F1 | "MAC-queue overflow dominates loss in 10 of the 12 measured cells"; "dominant in 10 / 12 cells" | "the larger of the two in 7 of the 12 measured cells (all six high-traffic cells and OLSR N=100 medium); in the other five (medium-traffic, low-stress) cells retry exhaustion is the larger but still minor of the two" | `retry_results.csv`, columns `retry_pct_of_loss` and `macq_pct_of_loss` and the row-wise `interpretation` column: queue larger in OLSR 50/75/100 high, OLSR 100 medium, Static 50/75/100 high; retry larger in OLSR 50/75 medium and Static 50/75/100 medium |
| F2 | "MAC-queue drops 1.2–2.4× over-represented at hop ≤1" (package: "across all 16 cells") | "1.4–2.4× over-represented at hop ≤1 in 11 of 16 cells", with a note: ratio below 1 in OLSR N=30 high (0.668) and OLSR N=50 medium (0.373); no MAC-queue drops (nan) in OLSR N=30, Static N=30 and Static N=50 medium | `bottleneck_results.csv`, column `macq_concentration_ratio` (= `frac_macq_hop_le1` / `frac_nodes_hop_le1`; the same in `T_probe_concentration.csv` `macq_conc_ratio`): 1.380–2.391 in the remaining 11 cells |
| F3 | "gateway airtime reaches 0.86–0.89 at N≥75 under high traffic" (protocol not stated) | "OLSR gateway airtime reaches 0.86–0.89 at N≥75 under high traffic (Static 0.62–0.66)" | `bottleneck_results.csv` `gw_airtime`: OLSR 75 high 0.8638, OLSR 100 high 0.8893; Static 75 high 0.6219, Static 100 high 0.6559 |
| C1 | "+25.5% at 12 kbps" | "12 kbps: +24.3% in seed-mean throughput; +25.5% as the mean of the three per-seed changes" | `rate_sweep_results.csv` `pct_change_throughput_vs_16kbps` = +24.34 (OLSR N=100, 12 kbps); per-seed `analysis/bottleneck-characterisation/data-ratesweep/probe_aggregate.csv`: +43.81, +23.26, +9.52 % (mean 25.53) |

## 10. Regression coverage: V7 replaced by D5, D6 and D10

`verify_site_wifi6.py` V7 asserted that, apart from the inserted Wi-Fi 6 block, `index.html` was byte-identical to
the pre-Wi-Fi 6 page. This redesign intentionally edits existing sections, so V7 can no longer hold. Its intent,
"no historical content lost or altered without review", is now covered as follows:

| Original V7 guarantee | Replacement | Status |
|---|---|---|
| No number of the published page altered | D5: every number in the visible text of the published page (`github/main`) is still present, except the audited correction set {1.2} | automated |
| No claim silently changed | D6: the corrected / stale claims are absent. **Gap:** D6 only knows the listed claims | automated + list |
| No section, chart, link or heading removed | D10: every element id (169), nav target (23), external link (11) and h2/h3 heading (107) still exists; headings may change only through an explicit rename map (Risk Summary, High Risks, Low Risks) | automated |
| Wording unchanged | `changed_sentences.txt`: every sentence of the published page that is no longer present verbatim (31). All 31 were reviewed by hand and each is one of the documented changes (F1–F3, C1, stale status, renames, navigation, deploy wording, footer); three apparent changes are only the sentence splitter merging unchanged text with an adjacent edit | manual review |

**Remaining coverage gap:** the *meaning* of reworded prose is reviewed by hand, not judged by a script. A future
edit that keeps all numbers, ids, links and headings but changes a sentence's meaning would pass D5/D6/D10. It
would appear in `changed_sentences.txt`, which must therefore be reviewed on every dashboard change.
