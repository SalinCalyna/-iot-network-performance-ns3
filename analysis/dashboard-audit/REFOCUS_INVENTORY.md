# Dashboard refocus — keep / remove / merge inventory (2026-10-25, before changes)

Baseline: live dashboard at commit `74213abe1` — 27 sections, about 8,500 words, 22 SVG charts, 8 Wi-Fi 6 figures.
Goal: show only completed, validated research in five areas, with Wi-Fi 6 Risk-Aware Routing as the highlight.

Removals apply to the **public dashboard page only**. Every research file stays in Git unchanged: simulator
sources, raw and derived datasets (including the now-unused `site/data/*.json` and `research.db`), reproducibility
scripts, and historical documentation (`docs/research-history.md`, `docs/v1-v4-methodology-results.md`).

## New structure (5 areas)

1. **V3 Baseline** — IEEE 802.11b network performance
2. **Bottleneck Analysis & Traffic-Rate Intervention** — retry evidence merged in; Static control merged in
3. **V4 Sigmoid Routing** — valid negative result
4. **Wi-Fi 6 Risk-Aware Routing** — visual highlight: N = 30 inferential, N = 100 descriptive, exposure, cost, short
   AODV secondary finding
5. **Conclusions, Limitations & Reproducibility**

## Sections

| Current section | Decision | Where its essential content goes |
|---|---|---|
| `view-overview` (hero, status rows, coverage chips, scope cards, flowchart, legend badges, KPI cards, story rail) | **Merge** | New compact overview: title, one-paragraph summary, five area cards with each area's key validated result, verified run counts. Status rows, scope cards, flowchart, legend badges and story rail are removed (duplicated) |
| `view-glance` (phase table, findings, limitations) | **Merge** | Phase/run-count table → overview (completed phases only). Findings and limitations → area 5 (no duplicate) |
| Network Health panel | **Remove** | Dashboard heuristic, not a research result; its evidence (OLSR N = 100 high) is in the Bottleneck charts |
| `view-risk-summary` (Performance Health Check) | **Remove** | Dashboard heuristic classification, not a research result |
| `view-realworld` (Phuket map, scenario) | **Remove** | Conceptual context, not measured |
| `view-bridge` | **Remove** | Conceptual |
| `view-research-questions` | **Merge** | The five answered questions become the five area cards. RQ6 (answered by Wi-Fi 6) is area 4. RQ7 (sigmoid routing under risk, unanswered) moves to the scope note in area 5 |
| `view-topology` (Experimental Design: network animation, pipeline architecture, IoT diagram, parameter space) | **Merge** | A compact experimental-setup table in area 1. Animation, architecture diagram and long explanations are removed |
| `view-baseline` | **Merge** | Area 1 header |
| `view-performance` | **Keep (reduced)** | Area 1: PDR, throughput and delay vs N (95 % CI) and PDR by traffic level, with a short CI and undefined-run note |
| `view-bottleneck` | **Keep (reduced)** | Area 2: gateway airtime chart, MAC-queue-by-hop chart, short evidence list. The operating-region console and OEI grid are removed (they duplicate the list) |
| `view-retry` | **Merge** | Area 2: retry vs queue comparison chart plus the 12-cell table (the evidence for "7 / 12") |
| `view-intervention` | **Keep (reduced)** | Area 2: PDR-vs-rate chart (OLSR N = 75, N = 100, Static N = 50), airtime chart with N selector, ΔPDR value |
| `view-static-control` | **Merge** | Area 2: Static N = 50 line in the PDR-vs-rate chart, plus a short statement with the residual-loss range. The 12-row diagnostic table is removed; it is linked in the CSV |
| `view-reproducibility` | **Merge** | Area 5 reproducibility panel |
| `view-risk-experiment` (BA topology proposal) | **Remove** | Unexecuted proposal. Area 5 states once that a BA variant was designed but **not executed** |
| `view-routing` (V4) | **Keep (reduced)** | Area 3: matched-condition chart (594 runs) and the Tier-1 activation table (66 runs). The Tier-1 bar chart duplicates the table and is removed, as are the long mechanism text and history notes |
| `view-w6-overview` | **Keep** | Area 4 header: KPIs, key finding, statistical approach, compact design, V4 distinction. The T-W1 parameter table is linked instead of shown |
| `view-w6-results` | **Keep** | Selector table, F-W1, F-W2 |
| `view-w6-paired` | **Keep** | Paired table, F-W3 |
| `view-w6-cost` | **Keep (reduced)** | Hop table and F-W4. F-W8 (delay CDF) is removed |
| `view-w6-aodv` | **Merge** | Concise secondary-finding card in area 4 (measured numbers, hypothesis label, scope). Tables T-W6a–c and figures F-W5–F-W7 are linked in the repository |
| `view-w6-validity` | **Merge** | T-W7 limitations table → area 5. Block Ack tables (T-W2) and load calibration (T-W3) are removed; one line each, with links |
| `view-data-explorer` (SQL explorer, V3 statistics explorer) | **Remove** | Data stays in the repository (`research.db`, `v3ext-stats.json`, `results/v3-ext/`). The link remains |
| `view-conclusions` | **Keep (rewritten)** | Area 5: findings (deduplicated), limitations, reproducibility, scope |
| `view-roadmap` | **Remove** | Future / proposed items. The single scope line in area 5 replaces it |

## Charts (22 → 10) and figures (8 → 4)

| Kept | Removed (reason) |
|---|---|
| `chart-pdr`, `chart-throughput`, `chart-delay` (lines, 95 % CI) | `chart-pdr-compare`, `chart-throughput-compare`, `chart-delay-compare`, `chart-loss-compare` (bars duplicate the lines) |
| `chart-traffic-load` | `chart-loss` (mirror of PDR), `chart-jitter`, `chart-hopcount-v3`, `chart-routing-overhead` (OLSR coverage gap), `chart-path-changes`, `chart-mlu` (secondary) |
| `chart-gw-airtime`, `chart-hop-macq`, `chart-retry-vs-macq` | `chart-int-pdr` (duplicates the PDR-vs-rate lines) |
| `chart-static-control` (now the PDR-vs-rate chart), `chart-int-airtime` | `chart-v4-tier1-pdr` (duplicates the Tier-1 table) |
| `chart-v4-matched-pdr` | — |
| Figures F-W1, F-W2, F-W3, F-W4 | F-W5, F-W6, F-W7 (AODV detail), F-W8 (delay CDF); kept in `analysis/wifi6-risk-writeup/figures/` |

## Claims checked for loss of supporting evidence

| Claim kept on the page | Evidence after the change |
|---|---|
| Performance degrades with N for all protocols | PDR, throughput and delay charts (kept) |
| OLSR gateway airtime 0.86–0.89 at N ≥ 75, high traffic | gateway-airtime chart (kept) |
| MAC-queue drops 1.4–2.4× over-represented at hop ≤ 1 in 11 of 16 cells | hop-bin chart (kept) plus link to `bottleneck_results.csv` |
| NO_ROUTE / ROUTE_ERROR < 2 % of loss | text only, before and after; link to `bottleneck_results.csv` |
| Retry ≈ 6 % vs queue ≈ 17.1 % (means); queue larger in 7 / 12 cells | retry chart **and** the 12-cell table (kept, because the table is the evidence for 7 / 12) |
| Rate cut 16 → 4 kbps: OLSR +14.7 pp (N = 75), +25.2 pp (N = 100) | PDR-vs-rate chart (kept) |
| Static N = 50 does not improve (−7.6 pp); residual loss 64.65–99.57 % | Static line in the same chart; residual range stated with a link to `static_n50_diagnostic.csv` (the table is removed) |
| V4 re-routed up to 11/11 seeds, no credible PDR gain | Tier-1 table (activation and PDR, kept) and matched chart (kept) |
| Wi-Fi 6 N = 30 k = 3: +23.18 pp [+19.81, +26.54], −46.33 pp [−53.21, −39.46], p = 0.00195, Holm 0.0117 | paired table, selector table, F-W1–F-W3 (kept) |
| Wi-Fi 6 N = 100: same direction 3/3, descriptive | paired table (N = 100 view), F-W1, F-W3 (kept) |
| Routing cost: real lengthening 1.64 → 1.75 links (N = 30), none at N = 100 | hop table and F-W4 (kept) |
| AODV N = 100: 56.60 % vs OLSR 99.62 % | selector table (AODV and OLSR rows at N = 100, kept) |
| Block Ack fix excluded as the AODV cause (53.21 % vs 55.13 %, seed 20) | stated numbers plus link to T-W6b in `analysis/wifi6-risk-writeup/TABLES.md` (the table is removed from the page) |
| 802.11b reproducible: 51/51 runs, 681/681 comparisons | stated, with link to `FINAL_REPRODUCIBILITY_CHECK.md` |

No kept claim loses its evidence entirely. Where a table leaves the page, the claim keeps its exact numbers and a
direct link to the authoritative file.

## Scientific content review (after the first preview)

All 155 changed or removed sentences from `verify_dashboard.py` were reviewed against the original page and the
authoritative sources (`analysis/final-report-data/`, `analysis/wifi6-risk-writeup/TABLES.md`). 45 required
qualifiers were checked for in the rendered page text. Three changes were made, wording only, with no numbers changed:

| Issue found | Change |
|---|---|
| The V4 limitation "the two-pass offline design measures load under baseline routing, never under the mechanism's own routing" had been dropped | Restored in the V4 callout |
| The finding "p95 delay cost +4.1 to +9.1 ms" did not say what it was compared against; the cost section's "about 2 ms" is Risk-Aware k = 3 vs its own k = 0 | Now reads "versus Static", with the survivorship note (delay is over delivered packets). Source: TABLES.md paired rows, delay p95, k = 1–3 |
| The overview Wi-Fi 6 card showed the N = 30 result without its qualifications | Added "10/10 pairs; an upper bound (oracle risk knowledge). N = 100 descriptive only." |

Dropped deliberately, because the content they qualified is no longer on the page: the MLU, hop-count, jitter and
routing-overhead chart caveats. The OLSR overhead limitation is still in area 5. Also dropped: the label "Decision B",
the "no Tier-2 / no further tuning" status lines (the V4 negative result itself is kept), and the AODV logging
byte-identity note (linked in T-W6).
