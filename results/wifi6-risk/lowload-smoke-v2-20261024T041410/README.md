# risk-v2 low-load smoke (2026-10-24)
802.11ax Tier A, OLSR, N = 100, 4/8/16 kbps per source, seeds 20/21/22, 300 s (apps 30-300 s), ARP pre-populated,
riskStudy=1 with 0 high-risk nodes, perPacketTrace=1, baSsnFix on (risk-v2 binary d909f6de, source 33b350ab).
Runner `experiments/wifi6-risk/run_lowload_smoke.py`; summary `experiments/wifi6-risk/analyze_lowload_smoke.py`
→ `lowload_runs.csv`, `lowload_by_rate.csv`. All 9 runs: exit 0, empty stderr.

| rate | sink PDR % (mean ± SD, min–max) | gw airtime | p50 / p95 / p99 delay ms | max delay s | MPDU expired | sink − FM rx |
|---|---|---|---|---|---|---|
| 4 | 99.56 ± 0.03 (99.52–99.58) | 0.21 ± 0.02 | 147 / 285 / 328 | 0.38–0.50 | 0 | 0 |
| 8 | 99.62 ± 0.04 (99.58–99.66) | 0.40 ± 0.04 | 144 / 285 / 329 | 0.40–0.48 | 0 | 0 |
| 16 | 94.97 ± 3.17 (91.53–97.77) | 0.67 ± 0.02 | 130 / 383 / 500 | 57.9–100.1 | 2,247–9,276 | 1–65 |

Non-saturated (gateway airtime < 0.5, no MAC-lifetime losses, PDR ≥ 99 %, no delay > 1 s, FlowMonitor rx = sink):
4 and 8 kbps. 16 kbps is in the congestion onset (lifetime losses, Block Ack tail of the risk-v2 limitation:
1–69 packets > 10 s). 

Observation: all 100 OnOff sources start at the same instant (appStart, no jitter; same as the frozen V3 design),
so 100 packets are offered in the same microsecond every 1.024 s at 4 kbps. Median delay of direct (0-relay) sources
is 99 ms at 4 kbps although gateway airtime is 0.21: the delay level at low load is set by this synchronized burst.
Not changed (traffic-model decision).

Block Ack limitation (risk-v2): see experiments/wifi6-risk/README.md, "Version for the research pilot".
