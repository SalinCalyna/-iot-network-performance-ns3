# risk-v2, N = 30, 8 kbps, 10 seeds (2026-10-24)
160 configurations = static / riskaware / aodv / olsr x numHighRisk 0-3 x seeds 20-29. Seeds 23-29 (112 runs) run
here; seeds 20-22 (48 runs) reused in place from pilot-n30-v2-20261024T054949 after an exact provenance match
(`reuse_manifest.json`: argv, binary d909f6de, source 33b350ab, exit 0, empty stderr). Runner
`experiments/wifi6-risk/run_seeds10_n30.py`; checks/metrics `analyze_pilot_n30.py` (analysis/CHECKS.txt:
1,830 passed, 0 failed); paired statistics `analyze_paired_stats.py` (analysis/STATS.txt,
paired_riskaware_vs_static.csv, stats_by_config.csv). Output 118 MB.

Disclosed limitations
1. Risk selection bias: HIGH_RISK relays are the top-k of the static 90 m BFS tree (subtree rule), i.e. where
   Static routes most traffic. Risk-Aware vs Static is matched; comparisons with OLSR/AODV favour them less than
   Static only because of this choice.
2. Oracle knowledge: riskaware knows every node's risk exactly and the risk never changes: upper bound.
3. Static/riskaware use the 90 m disk graph; the radio reaches further (OLSR/AODV 1.3-1.4 hops vs 1.5-1.75). In
   seed 28 source 26 is isolated in the 90 m graph: static and riskaware lose all its 527 packets (-3.33 pp PDR for
   that seed); OLSR/AODV deliver them.
4. Synchronized CBR: all sources send at the same instant every 0.512 s (V3 design); absolute delays include this.
5. risk-v2 Block Ack limitation (saturation only): here 0 packets > 10 s, max delay 3.94 s, sink = FlowMonitor rx.
6. Delay is over delivered packets only: Static drops long relayed paths, which lowers its delay (survivorship).
7. 8 kbps is very light load (gateway airtime 0.04-0.08): no congestion trade-off is tested.
