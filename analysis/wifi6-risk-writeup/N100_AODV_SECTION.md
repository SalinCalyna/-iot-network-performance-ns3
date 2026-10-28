# Wi-Fi 6 risk study — N = 100 scalability: AODV degradation (Results & Discussion subsection)

Draft for the final research report, 2026-10-24. Every number below comes from validated, unmodified runs:
- `results/wifi6-risk/n100-8k-v2-20261024T165009/`: 48 runs, 549/549 checks passed.
- `results/wifi6-risk/aodv-diag-n100-20261024T204129/`: 2 runs, 13/13 checks passed each.
- N = 30 references: `seeds10-n30-8k-v2-20261024T160515/` and `pilot-n30-v2-20261024T054949/`.

AODV results are reported as measured. No AODV parameter was tuned and no run was replaced. With n = 3 seeds,
values are mean ± SD and are descriptive; no statistical significance is claimed.

---

## 4.x.y Routing-protocol behaviour at N = 100: AODV degradation

**Observed performance.** At N = 100 sensors and 8 kbps per source (800 kbps nominal offered load), AODV
delivered 56.60 ± 1.76 % of the nominal traffic with no high-risk nodes (k = 0; seeds 20–22, range
55.13–58.55 %). OLSR delivered 99.62 ± 0.04 % under identical topology, traffic and PHY/MAC settings (Table
4.x.a). The AODV deficit is essentially independent of the number of high-risk relays: 56.60–58.08 % for
k = 0–3, against 98.64–99.62 % for OLSR. The risk model is therefore not its cause. The same AODV
implementation and settings delivered 99.99 ± 0.02 % at N = 30 and 8 kbps (k = 0, 10 seeds). It also delivered
99.76–99.95 % at N = 30 and 64 kbps (3 seeds), a 2.4-fold higher total offered load (1,920 kbps) with
gateway airtime of 0.51–0.58. The degradation is therefore specific to the larger network, not to the
offered data rate.

**Channel and MAC indicators.** AODV occupied the gateway's channel for 0.690 ± 0.008 of the time, compared
with 0.400 ± 0.038 for OLSR. Relative to OLSR in the same seed, AODV transmitted:
- 9.9–11.4 times as many group-addressed (broadcast) frames: 202–220 k vs 19–21 k;
- 2.8–3.2 times as many unicast data PSDUs: 1.25–1.42 M vs 0.40–0.49 M;
- 129–164 times as many BlockAckRequests: 145–183 k vs 1.0–1.3 k.

Between 135,658 and 165,918 MPDUs per run were discarded after exceeding the MAC queue lifetime (OLSR: 0).
In seed 20 these expiries were spread across all hop distances rather than concentrated at the gateway. Routing-layer
"no route" drops were small (675–829 per run against 21.8–23.6 k lost packets). Loss was sustained over the
whole run, with 39.7–65.8 % delivery in every 30 s window (seeds 20–22). Between 49.8 and 55.1 % of AODV's lost packets were
lost before any relay forwarded them. Sources one hop from the gateway in the 90 m graph were also affected:
AODV 68.8–78.6 % delivery against 99.9 % for OLSR (two-hop sources: 42.9–47.8 % against 99.4–99.5 %). Delay over delivered packets was higher for AODV:

| Delay | AODV | OLSR |
|---|---|---|
| p50 | 206 ± 16 ms | 144 ± 21 ms |
| p95 | 675 ± 51 ms | 285 ± 35 ms |
| p99 | 973 ± 23 ms | 329 ± 43 ms |

Route stability differed markedly between the two protocols:

| Route stability | AODV | OLSR |
|---|---|---|
| Path changes per source per minute | 51.8–57.5 | 6.9–11.2 |
| Distinct paths per source | 82–99 | 14–19 |
| Packets on looping paths per run | 84–358 (0.16–0.68 % of sent) | 0–12 |

**Diagnostic run.** A two-run diagnostic was performed on seed 20 (k = 0). Both runs recorded AODV event counts
from the ns-3 log without changing the simulation; the fix-on run reproduced the original outputs byte for byte.
The diagnostic showed that AODV control activity is driven by link-failure handling. Route discoveries are
comparatively rare but expensive: each RREQ flood is received about 650 times, so in receptions the
(re-)discovery floods are the largest control component, followed by RERRs (Table 4.x.b):
- 161,253 link-failure events;
- 117,736 Route Errors (RERR) sent to active precursors, received 1.24 M times;
- 5,350 RREQ originations, each received about 650 times (3.46 M receptions in total);
- 106,664 gratuitous RREPs from intermediate nodes;
- 5,371 Hello messages.

Link failures occurred at 229 s⁻¹ before data traffic began. They rose to 572 s⁻¹ within the first 10 s
of traffic and stayed at that level until the end of the run. RREQ originations clustered at the
synchronized send instants: 39.9 % fell in the first 32 ms of the 512 ms CBR period, against 6.25 % if
uniform. Disabling the risk-v2 Block Ack modification (`--baSsnFix=0`) left the collapse unchanged:

| Fix off vs fix on (seed 20) | Fix off | Fix on |
|---|---|---|
| PDR | 53.21 % | 55.13 % |
| Gateway airtime | 0.691 | 0.697 |
| BlockAckRequests | 177.7 k | 183.1 k |
| Link failures | 163.1 k | 161.3 k |

**Interpretation.** The results support the following observations:
1. **(O1)** The degradation is not caused by the risk model, the Block Ack modification, or the data load
   alone.
2. **(O2)** It coincides with frequent link-failure events, very large RERR and RREQ-flood traffic, and unstable
   routes.
3. **(O3)** In ns-3's AODV, every dropped unicast MPDU is treated as a link failure, irrespective of the drop
   reason. This includes MPDUs discarded because they exceeded the queue lifetime.

Observation O3 is a property of the implementation (`aodv-routing-protocol.cc`, `NotifyTxError`;
`aodv-neighbor.cc`, `ProcessTxError`). It suggests, but does not establish, a self-reinforcing
routing-repair loop:
1. Contention delays a queued frame beyond its lifetime.
2. AODV interprets the discard as a broken link and invalidates the routes through that neighbour.
3. It sends RERRs, and the affected sources start new network-wide RREQ floods.
4. The additional control traffic and the retransmissions to new next hops raise channel occupancy, which
   causes further expiries.

Synchronized CBR plausibly strengthens the loop because every source needs a route at the same instant. Node
density multiplies the cost of each flood. Neither feature is present to the same degree at N = 30. OLSR,
which maintains routes proactively and does not react to individual MAC drops, does not show the effect. We
regard this mechanism as the most likely explanation, but it is a hypothesis. The contributions of its
individual elements (synchronized traffic, queue lifetime and Hello-based neighbour expiry) were not isolated
by controlled experiments (Table 4.x.c).

**Implications for the comparison.** Under these conditions AODV is not a competitive baseline at N = 100.
Differences between Risk-Aware or Static routing and AODV at N = 100 mainly reflect this AODV-specific
scaling behaviour, not risk avoidance. Comparisons of risk exposure and delivery at N = 100 should therefore
use Static (matched) and OLSR as the reference protocols, with AODV reported for completeness. The finding
concerns the ns-3 AODV implementation under synchronized periodic traffic in a dense 802.11ax ad-hoc network.
It should not be generalized to AODV as a protocol without further experiments.

---

## Table 4.x.a — N = 100, 8 kbps, k = 0: AODV vs OLSR (seeds 20–22, mean ± SD unless a range is given)
| Metric | AODV | OLSR |
|---|---|---|
| Nominal PDR (= sink PDR) % | 56.60 ± 1.76 | 99.62 ± 0.04 |
| PDR range over k = 0–3 (means) % | 56.60–58.08 | 98.64–99.62 |
| Sink throughput, kbps | 477.2 ± 14.8 | 840.0 ± 0.3 |
| Gateway airtime (fraction) | 0.690 ± 0.008 | 0.400 ± 0.038 |
| Delay p50 / p95 / p99, ms | 206 / 675 / 973 | 144 / 285 / 329 |
| Mean hops (delivered) | 1.73 ± 0.13 | 1.40 ± 0.08 |
| Broadcast frames per run | 202–220 k | 19–21 k |
| Unicast data PSDUs per run | 1.25–1.42 M | 0.40–0.49 M |
| BlockAckRequest PSDUs per run | 145–183 k | 1.0–1.3 k |
| MPDUs expired (queue lifetime) per run | 136–166 k | 0 |
| Retry-limit drops per run | 1.9–2.4 k | 0.6–0.7 k |
| IP no-route drops per run | 675–829 | 0 |
| Packets delayed > 1 s per run | 225–307 | 0 |
| Path changes per source per minute | 51.8–57.5 | 6.9–11.2 |
| Packets on looping paths per run | 84–358 | 0–12 |
| Lost packets not forwarded by any relay (% of lost) | 49.8–55.1 | — |
| PDR of sources 1 / 2 hops from gateway (90 m graph), % | 68.8–78.6 / 42.9–47.8 | 99.9 / 99.4–99.5 |
| Reference: N = 30, 8 kbps PDR % (10 seeds) | 99.99 ± 0.02 | 99.99 ± 0.00 |

## Table 4.x.b — AODV diagnostic, N = 100, 8 kbps, k = 0, seed 20 (single seed)
| Quantity | Block Ack fix off | Block Ack fix on (original) |
|---|---|---|
| Nominal PDR % | 53.21 | 55.13 |
| Gateway airtime | 0.691 | 0.697 |
| BlockAckRequest PSDUs | 177,748 | 183,074 |
| MPDUs expired | 162,246 | 157,691 |
| Packets > 10 s (max delay) | 3 (48.0 s) | 0 (9.8 s) |
| AODV link-failure events | 163,075 | 161,253 |
| — before traffic (0–30 s) | 6,865 (229 s⁻¹) | 6,865 (229 s⁻¹) |
| — during traffic (30–300 s) | 156,210 (579 s⁻¹) | 154,388 (572 s⁻¹) |
| RERR to active precursors / receptions | 118,194 / 1.25 M | 117,736 / 1.24 M |
| RREQ originations / receptions | 5,458 / 3.55 M | 5,350 / 3.46 M |
| Gratuitous RREPs | 108,482 | 106,664 |
| Hellos sent | 5,857 | 5,371 |
| RREQs in first 32 ms of 512 ms CBR cycle | — | 39.9 % (uniform: 6.25 %) |

## Table 4.x.c — Limitations of the N = 100 AODV finding
| # | Limitation | What is known | Effect on conclusions |
|---|---|---|---|
| L1 | Synchronized CBR traffic: all sources send at the same instant every 512 ms (inherited V3 design) | RREQs concentrate at send instants (39.9 % in the first 32 ms); AODV at N = 30 is unaffected under the same synchronization | Probably amplifies AODV's collapse; contribution not isolated (no desynchronization option without a simulator change) |
| L2 | MAC queue lifetime (ns-3 default, 500 ms) | 136–166 k expiries per AODV run, 0 for OLSR; in ns-3 AODV each unicast expiry is reported as a link failure | Couples congestion to route repair; sensitivity to the lifetime not tested (changing it would alter the approved configuration) |
| L3 | Hello-based link detection (AllowedHelloLoss × HelloInterval = 2 s) | 229 link failures s⁻¹ already before data traffic; the log does not separate Hello expiry from MAC-drop failures after traffic starts | Share of breaks attributable to each mechanism unknown; per-node correlation of MAC drops with link failures r = 0.55 |
| L4 | Block Ack sensitivity check on one seed | Fix off: 53.21 % vs 55.13 % PDR, airtime unchanged (seed 20) | Excludes the modification as the main cause for that seed; not a multi-seed estimate |
| L5 | Three seeds at N = 100 | AODV 55.13–58.55 %, OLSR 99.58–99.66 % at k = 0 | Descriptive only; no significance tests |
| L6 | Causal chain is inferred, not demonstrated | Observations O1–O3 are confirmed; the feedback loop is a hypothesis | Reported as the likely mechanism, not as an established cause |
| L7 | Implementation scope | ns-3 AODV, unmodified, 802.11ax Tier A ad-hoc, static nodes, 250 m × 250 m | Not generalizable to AODV implementations or deployments beyond these conditions |
| L8 | AODV parameters left at ns-3 defaults | No tuning was performed, by design | AODV results are a baseline for this configuration, not AODV's best attainable performance |

---

## Remaining figures and tables for the final report (Wi-Fi 6 risk study)
The existing `analysis/thesis-writing-plan/TABLE_FIGURE_PLAN.csv` covers the 802.11b phases (Figures 1–7,
Tables 1–8) and has no entries for this study. "Data exists" means the source is already validated. No
item requires new simulation.

| ID | Type | Content | Source (validated) | Status |
|---|---|---|---|---|
| T-W1 | Table | Wi-Fi 6 simulation parameters (802.11ax Tier A, HeMcs0, 20 MHz, A-MPDU/A-MSDU off, ARP pre-populated, 300 s / 30 s, 512 B CBR, risk parameters r_high = 0.5, β = 10, subtree rule) | batch.json files, run_pilot_n30.py BASE | Data exists; to write |
| T-W2 | Table | Block Ack issue and risk-v2 fix: cases A–D, v2/v3/v4 > 10 s tails per 100 k packets | diag-tail-20261022/README.md, v3/v4 tail checks | Data exists; to write |
| T-W3 | Table | Load calibration (N = 100 OLSR 4/8/16 kbps; N = 30 8/64 kbps airtime) — justifies 8 kbps | lowload-smoke-v2, pilot-n30-v2 | Data exists; to write |
| T-W4 | Table | N = 30 main result, 10 seeds: PDR, exposure, delay, hops per protocol × k; paired Risk-Aware − Static with Wilcoxon / Holm | seeds10-n30-8k-v2 analysis/STATS.txt | Data exists; to write |
| T-W5 | Table | N = 100 main result, 3 seeds, descriptive: same columns, no tests | n100-8k-v2 analysis/stats_by_config.csv | Data exists; to write |
| T-W6 | Table | Tables 4.x.a–c above | this document | Drafted |
| T-W7 | Table | Consolidated limitations for the whole Wi-Fi 6 study (selection bias, oracle risk, 90 m disk graph vs radio range, synchronized CBR, Block Ack modification, survivorship, light load, seed counts, AODV L1–L8) | READMEs of the batches above | To consolidate |
| F-W1 | Figure | PDR vs k (0–3), four protocols, N = 30 (10 seeds) and N = 100 (3 seeds) panels, error bars = SD | stats_by_config.csv (both batches) | To plot |
| F-W2 | Figure | Exposure rate vs k, four protocols, both N | stats_by_config.csv | To plot |
| F-W3 | Figure | Paired Risk-Aware − Static differences per seed (PDR, exposure) vs k, both N | paired_riskaware_vs_static.csv | To plot |
| F-W4 | Figure | Cost of risk avoidance: delay p50/p95/p99 and hops, Risk-Aware vs Static k = 0; note survivorship | stats_by_config.csv; all-sent hop check (N = 100 README) | To plot |
| F-W5 | Figure | AODV vs OLSR at N = 100: per-30 s PDR time series (k = 0, 3 seeds) | runs/*/packet_paths.csv | To plot |
| F-W6 | Figure | AODV link failures per 10 s (fix on/off) with traffic start marked; RREQ phase histogram over the 512 ms cycle | aodv-diag .../aodv_log_counts.json | To plot |
| F-W7 | Figure | Frame-type composition AODV vs OLSR (broadcast, unicast, BAR, management) at N = 100 | runs/*/wifi_txvector_counts.csv | To plot |
| F-W8 | Figure (optional) | Delay CDF per protocol, N = 100, k = 0 | packet_paths.csv | To plot |

Also still to do in text: the methodology description of risk-v2 (Block Ack fix, risk model, selection rule),
and a statement that the N = 100 subtree design was also run at saturated load (16 and 32 kbps, 3 seeds;
validated) but is not yet part of the reported findings. Those results would add the congestion trade-off
currently listed as a limitation.
