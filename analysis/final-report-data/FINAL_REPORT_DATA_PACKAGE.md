# FINAL REPORT DATA PACKAGE

**Type: read-only data extraction and synthesis.** No simulation run, no dataset modified, no source/runner touched. All figures below are either copied verbatim from existing approved derived tables, or freshly computed from frozen raw datasets using only mean/SD/percentage-change arithmetic (no new statistical testing, no outlier removal).

---

## Files in this package (`analysis/final-report-data/`)

| File | Contents |
|---|---|
| `final_metrics.csv` | Master cross-stage metrics table (74 rows: V3 pooled, §10, retry, rate-sweep, Static/N=50 diagnostic) |
| `v3_core_results.csv` | V3 protocol comparison by node count (pooled traffic/mobility, official Seed 20-30) |
| `v4_results.csv` | V4-matched (pooled), V4-sensitivity (27 configs), V4-Tier-1 activation (6 configs) |
| `bottleneck_results.csv` | §10 evidence: airtime, queue drops, PHY drops, concentration ratios by protocol/N/traffic |
| `retry_results.csv` | Retry-exhaustion validation: loss attribution by protocol/N/traffic |
| `rate_sweep_results.csv` | 72-run offered-rate sweep: full stats + deltas vs. 16kbps baseline |
| `static_n50_diagnostic.csv` | 12-run residual-loss accounting (mutually-exclusive counters) |
| `figure_data.csv` | Clean plotting data for 7 candidate thesis figures (long format) |
| `thesis_evidence_map.csv` | The 7 frozen findings mapped to research question, evidence, interpretation, limitation |
| `REPORT_DATA_DICTIONARY.md` | Metric-by-metric definitions, units, caveats (AODV denominator, OLSR overhead gap, PHY-drops≠loss, etc.) |
| `final_number_check.csv` | Cross-file consistency check; documents 2 apparent "conflicts" that are correctly-labeled different poolings, not errors |

---

## AUTHORITATIVE NUMBERS FOR THESIS

Use these exact values consistently across Abstract, Chapters 3-5, Conclusion, and slides. Each is sourced to its file above.

### V3 baseline (PDR, pooled over traffic × mobility, official Seed 20-30, n=99 per cell)

| Protocol | N=10 | N=100 |
|---|---:|---:|
| OLSR | **69.48%** | **29.78%** |
| Static | **46.69%** | **17.20%** |
| AODV | **76.73%** | **4.00%** (carries the FlowMonitor denominator caveat) |

*(Source: `v3_core_results.csv`)*

### Bottleneck characterisation (§10)

- Gateway airtime at **N=75/high traffic: 0.8638**; at **N=100/high traffic: 0.8893** — the empirical near-saturation reference band used throughout this research (~0.85+), not a universal theoretical threshold.
- MAC-queue-drop concentration at hop≤1: **1.2–2.4× over-represented** relative to node population share, across all 16 (protocol×N×traffic) cells.
- Retry-exhaustion contribution to loss: **mean ≈6%** (range 1.5–18.0% across 12 cells), MAC-queue overflow larger in **10 of 12 cells**.

*(Source: `bottleneck_results.csv`, `retry_results.csv`)*

### Offered-rate intervention

- **OLSR N=75**: PDR **+14.7 percentage points** (26.28% → 40.95%) at 4kbps vs. 16kbps baseline, monotonic in 6/6 individual seed-series.
- **OLSR N=100**: PDR **+25.2 percentage points** (14.53% → 39.74%) at 4kbps vs. 16kbps baseline, monotonic in 6/6 individual seed-series.
- Corroborating throughput evidence: **OLSR N=100 delivered throughput rises** at reduced rate (+25.5% at 12kbps, +6.2% at 8kbps, despite less being offered) — the clean congestion-relief signature, not just proportionally-less-in-less-out.

*(Source: `rate_sweep_results.csv`)*

### Static/N=50 diagnostic

- Residual (unattributed) loss: **64.65%–99.57% across all 12 runs**, **≥92% in 10 of 12 runs**. State both figures in the thesis: *"typically ≥92% of loss unattributed, full range 65–99.6% across all 12 diagnostic runs."*
- 12-run conclusion: congestion (airtime, MAC-queue drops) was measurably relieved by rate reduction, but the relieved mechanisms accounted for at most ~35% (typically ~16% or less) of Static/N=50's total loss even at the congested baseline — explaining, without inventing, why PDR did not improve.

*(Source: `static_n50_diagnostic.csv`)*

### V4

- **V4 activated**: Tier-1 Config 6 (x0_R=0.80, x0_L=0.50) — **11/11 seeds (100%) re-route** relative to Static's shortest-path tree, mean hop count **+27.9%** (1.578 → 2.018).
- **V4 did not improve target performance**: same config's PDR change is **+3.5%** but **not statistically credible** (sign-test p=1.0, Cohen's d=+0.15, negative at the median), while delay **worsens +21.6%** and MaxLinkUtil **worsens +42.8%**. This is the single strongest-activation configuration in the entire V4 research chain.

*(Source: `v4_results.csv`, copied from the existing approved `T_tier1_activation_and_perf.csv`)*

---

## Data-hygiene notes (preserved, not corrected)

- **V3 legacy rows**: 19 rows at non-standard seeds (1, 2, 99) exist in 11 raw `results/v3-ext/*.csv` files. The official analysis (`analyze_v3_official.py`) already filters to `Seed.between(20,30)` with its own integrity check — **no effect on any published V3 conclusion.** Any new direct use of the raw files must apply the same filter.
- **Rate-sweep per-node collision**: per-node CSV filenames encoded `trafficLevel` (held constant) but not the swept offered rate, so 3 of 4 rate levels' per-node files were overwritten. **Aggregate results (used for every rate-sweep and diagnostic conclusion) remain fully valid.** 12kbps per-node data is unavailable; do not perform new spatial analysis using those files; this was not rerun or repaired.

---

## FINAL REPORT

### 1. Status
**READY WITH CAVEATS**

### 2. Datasets used
V3 baseline (1782 official rows), V4 matched (594) + sensitivity (297) + Tier-1 (66), §10 bottleneck probe (176), retry-exhaustion validation (36), offered-rate sweep (72), Static/N=50 diagnostic (12-run subset of the rate sweep). All frozen, all read-only.

### 3. Files created
`final_metrics.csv`, `v3_core_results.csv`, `v4_results.csv`, `bottleneck_results.csv`, `retry_results.csv`, `rate_sweep_results.csv`, `static_n50_diagnostic.csv`, `figure_data.csv`, `thesis_evidence_map.csv`, `REPORT_DATA_DICTIONARY.md`, `final_number_check.csv`, `FINAL_REPORT_DATA_PACKAGE.md` — all new, all under `analysis/final-report-data/`.

### 4. Authoritative findings (with key quantitative evidence)
1. Performance degrades with N/load — OLSR PDR 69.5%→29.8% (N=10→100).
2. V4 activation ≠ improvement — 100% activation, +27.9% hop count, PDR change not significant (p=1.0).
3. Gateway/1-hop congestion dominant under near-saturation — airtime 0.86–0.89 at N≥75/high, MAC-queue 1.2–2.4× concentrated at hop≤1.
4. Retry exhaustion present, not dominant — mean ≈6% of loss, queue overflow larger in 10/12 cells.
5. Rate reduction improves OLSR PDR at N=75/100 — +14.7pp and +25.2pp respectively, monotonic across seeds.
6. Static/N=50 does not respond — PDR flat-to-negative in all 3 seeds; low CV (1.9–10.4%) rules out noise.
7. Residual loss remains unexplained — 65–99.6% (typically ≥92%) unattributed across all 12 diagnostic runs.

### 5. Important caveats
AODV FlowMonitor denominator artifact; V3's `RoutingOverheadPackets`=0 for OLSR is a metric-coverage gap, not zero control traffic; PHY RX-drop volume ≠ permanent loss; retry exhaustion measured but secondary; not every terminal packet fate is captured; the rate intervention is a fixed-rate sweep, not adaptive control; results are specific to this ns-3 topology/configuration; 19 legacy-seed V3 rows (no conclusion impact); rate-sweep per-node rate-ambiguity (aggregate unaffected).

### 6. Number conflicts
**NO** genuine conflicts found. **One clarification documented** (`final_number_check.csv`): the pooled V4-matched PDR figures (all traffic/mobility) differ from the previously-published single-condition N=50/medium/static figures (OLSR 37.9%/Static 36.4%/V4 34.8%) — both are correct, independently re-verified bit-for-bit against raw data this session, and are simply different, now clearly-labeled poolings.

### 7. Research integrity
No simulation rerun. No new experiment. No dataset modified. No source modified. No runner modified. No topology modified.

### 8. Report readiness
**Can the thesis Results/Discussion chapters now be written from this package without reopening the research?**

**YES.** All seven frozen findings have quantitative evidence, source files, and stated limitations in this package. The two "smallest missing items" that remain (residual-loss mechanism identity; rate-sweep pernode data at 12kbps) are explicitly out of scope by design — they are documented as open limitations for the thesis's Future Work section, not blockers for writing Results/Discussion from the frozen evidence base.
