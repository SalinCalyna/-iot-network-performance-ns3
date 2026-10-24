# risk-v2 pilot, N = 30 (2026-10-24)
96 runs: static / riskaware / aodv / olsr x numHighRisk 0-3 x seeds 20-22 x 8 and 64 kbps per source.
802.11ax Tier A, static positions, 300 s (apps 30-300 s), ARP pre-populated, approved risk parameters
(HIGH_RISK r = 0.5, LOW_RISK r = 0, beta = 10, subtree rule, risk-drop seed 1), risk-v2 binary d909f6de.
Runner `experiments/wifi6-risk/run_pilot_n30.py` (subset of 16 first, then the other 80); checks and metrics
`experiments/wifi6-risk/analyze_pilot_n30.py` → `analysis/` (CHECKS.txt: 1,086 passed, 0 failed;
pilot_runs.csv; pilot_by_config.csv). All 96 runs exit 0, empty stderr; wall clock 05:52-06:32 (6 jobs).

Findings and limitations (details in the 2026-10-24 report):
- Load: 8 kbps gateway airtime 0.05-0.07; 64 kbps 0.40-0.57. 64 kbps is moderate load at N = 30, NOT saturated.
- OnOff counts only successful socket sends; OLSR at 64 kbps seed 21 missed 19-31 sends per run (no route at the
  source). pdr_nominal_pct uses the scheduled sends (126,540 at 64 kbps, 15,810 at 8 kbps).
- High-risk relays are ranked on the static 90 m BFS tree (subtree rule), so the risk set is chosen where Static
  routes most traffic; OLSR/AODV use longer radio links (1.3-1.4 hops vs 1.69 for static) and cross these relays less.
- riskaware has perfect, static risk knowledge: its result is an upper bound.
- Synchronized CBR: every source sends at the same instant each interval (inherited from the V3 design).
- Block Ack limitation of risk-v2: no packet > 10 s in any of the 96 runs (max 6.13 s), sink = FlowMonitor rx in all.
