# Wi-Fi 6 risk study — report outputs inventory (2026-10-24)

Generator: `experiments/wifi6-risk/make_report_outputs.py`. Run with `myenv/bin/python -I -B …`; it needs matplotlib
3.10.8 and numpy 2.4.4 from the project venv `myenv`. It reads 350 validated input files; their sha256 hashes are
in `inventory.json`. No simulation was run and no result file was modified. Two generations produced
byte-identical tables.

## Completed outputs
| Item | File(s) | Data | n |
|---|---|---|---|
| T-W1 parameters | tables/T-W1_parameters.csv | batch.json + read-back of all 9,808 devices in 208 runs | — |
| T-W2 Block Ack | tables/T-W2a–d_*.csv | diag-delay-20261021, v4-tail-check, diag-tail README, validation batches | 1 seed (a); 3 seeds (b) |
| T-W3 load calibration | tables/T-W3_load_calibration.csv | lowload-smoke-v2, pilot-n30-v2 | 3 seeds per row |
| T-W4 N = 30 main (inferential) | tables/T-W4a/b_*.csv | seeds10-n30-8k-v2 | 10 seeds |
| T-W5 N = 100 main (descriptive) | tables/T-W5a/b_*.csv | n100-8k-v2 | 3 seeds |
| T-W6 AODV at N = 100 | tables/T-W6a–c_*.csv | n100-8k-v2, aodv-diag-n100 | 3 seeds (a); 1 seed (b) |
| T-W7 limitations | tables/T-W7_limitations.csv | batch READMEs | — |
| F-W1–F-W8 | figures/*.pdf, *.png; captions in FIGURES.md | as above | as stated in each caption |
| Formatted tables | TABLES.md | — | — |
| Results & Discussion draft | N100_AODV_SECTION.md | — | — |
| Plan updated | analysis/thesis-writing-plan/TABLE_FIGURE_PLAN.csv (+15 rows: T-W1–T-W7, F-W1–F-W8) | — | — |

F-W8 is included because the per-packet traces support it (delivered packets only).

## Corrections made during preparation (all propagated to the READMEs and N100_AODV_SECTION.md)
1. "Lost packets never crossed the first link" is now "lost before being forwarded by any relay", 49.8–55.1 %.
   For a lost packet, `path` holds the source plus the relays that forwarded it.
2. "0-relay sources only 54.7 % PDR" is withdrawn: it grouped lost packets by the number of relays they reached.
   It is replaced by per-source PDR by 90 m-graph hop: AODV 68.8–78.6 % (1 hop) and 42.9–47.8 % (≥ 2 hops);
   OLSR 99.9 % and 99.4–99.5 %.
3. AODV PDR per 30 s window is now 39.7–65.8 % over seeds 20–22 (previously 44–64 %, from seeds 20–21 only).
4. "AODV control traffic dominated by route maintenance rather than discovery" is reworded. The triggers are
   link failures and RERRs (118k sent, 1.24M receptions), but by receptions the RREQ floods are the largest
   component (5.4k originations, 3.46M receptions).
5. Exact Wilcoxon p is now printed to 3 significant digits (0.00195, not 0.0020). Secondary metrics are marked
   "unadjusted".

## Inconsistencies and points needing a footnote (data unchanged)
1. **Denominators in older batches.**
   - The low-load smoke CSV computes PDR from app-tx. At 16 kbps seed 20, 18 packets were never sent. T-W3 uses
     the full schedule (105,400) as the denominator, so it reports 94.97 ± 3.18 % instead of the earlier
     94.97 ± 3.17 %.
   - The saturated v2/v3/v4 tail runs also count app-tx, so T-W2b shows no PDR.
2. **T-W2a, fix off vs on (k = 2, seed 20, 100 s).** The fix-off run delivered 6,939 packets vs 6,843 with the fix.
   FlowMonitor PDR shows the opposite order (83.37 vs 83.55 %) because it counts packets delayed > 10 s as lost.
   The fix changes the event sequence, so the two runs follow different trajectories. With one seed the count
   difference is not interpretable; the tail metrics (max delay 65.3 s vs 0.1 s) are the evidence.
3. **Hop cost differs between N = 30 and N = 100 (F-W4).**
   - N = 30: Risk-Aware's all-sent path length does grow, from 1.64 to 1.75 links at k = 3. The delivered-hop
     difference of +0.25 against Static is about +0.11 real lengthening plus survivorship.
   - N = 100: there is no real lengthening (1.613 links at every k).
   - My earlier progress report described the N = 30 cost as "+0.07 to +0.25 hops". That figure is for
     delivered packets and needs this qualifier (it does not appear in any README).
4. **N = 30 Static and Risk-Aware k = 0 PDR is 99.66 ± 1.05 %, not 100 %.** Seed 28 has one source isolated in
   the 90 m disk graph (527 packets).
5. **Risk-Aware exposure at N = 30.** Its exposure is 0 in every run except seed 21 at k = 2 and k = 3
   (3.33 %, mean 0.33 %). In that seed, source 11 has no safe path.
6. **AODV exposure is not comparable.** At N = 100, AODV's exposure of 1.1–3.4 % sits on a 57 % PDR baseline,
   so it can't be compared with the other protocols.
7. **F-W8 knee.** AODV's delay CDF has a knee near 500 ms, which coincides with the MAC queue lifetime
   (`wifi-mac-queue.cc:42-44`, not overridden). This is an observation; it was not tested.

## Missing data (cannot be filled without new runs or approvals)
1. The AODV Block Ack sensitivity check covers seed 20 only.
2. There is no controlled test of the AODV feedback hypothesis. Desynchronized CBR needs a simulator change;
   MaxDelay or Hello sensitivity would change the methodology.
3. Link failures after traffic starts are not split between Hello expiry and MAC drops ("Close link" lines were
   not counted). The unicast vs broadcast share of expired MPDUs is unknown.
4. The N = 100 subtree design was also run at saturated load (16 and 32 kbps, 3 seeds; validated), but those
   results are not yet part of the reported findings, so the congestion trade-off of risk avoidance is not covered
   by them.
5. Only 3 seeds exist at N = 100, so it supports no inferential statistics.
6. The thesis chapter outlines (`CHAPTER_3/4/5_OUTLINE.md`) and `CLAIM_TO_EVIDENCE_MAP.csv` cover only the
   802.11b phases. The Wi-Fi 6 study is in TABLE_FIGURE_PLAN.csv but not yet in those files.

## Not done (by instruction)
No simulation, no simulator change, no commit or push, and no N = 100 saturated-load experiment.
