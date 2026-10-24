# risk-v2, N = 100, 8 kbps, 3 seeds (2026-10-24)
48 configurations = static / riskaware / aodv / olsr x numHighRisk 0-3 x seeds 20-22, all run here (nothing
reused). Runner `experiments/wifi6-risk/run_n100_8k.py` (run_pilot_n30.py settings with --nSensors=100; binary
d909f6de, source 33b350ab); checks/metrics `analyze_pilot_n30.py` (analysis/CHECKS.txt: 549 passed, 0 failed);
descriptive paired summary `analyze_paired_stats.py --rate=8 --descriptive` (analysis/STATS.txt,
paired_riskaware_vs_static.csv, stats_by_config.csv). 1,256 run-minutes, 6 jobs; output 168 MB.

n = 3 seeds: mean, SD and the Student-t 95 % interval of the mean are reported as DESCRIPTIVE ranges only. No
hypothesis tests are reported (the smallest attainable exact two-sided Wilcoxon p with 3 pairs is 0.25) and no
statistical significance is claimed.

Determinism: olsr_k0 seeds 20-22 are byte-identical to lowload-smoke-v2-20261024T041410/runs/olsr_100_rate8_seed*
in all 14 compared output files except the wall-clock `timestamp` column of probe_aggregate.csv (the new argv adds
only the explicit risk parameters, which equal the defaults).

Integrity: unsent_at_source 0 in all 48 runs (nominal PDR = sink PDR); duplicates 0; sink - FlowMonitor rx <= 1;
static/riskaware 0 packets > 1 s; OLSR 36 packets > 1 s, 0 > 10 s; AODV 3,066 > 1 s, 1 > 10 s (max 20.7 s).

Main results (mean +/- SD over seeds 20-22)
| k | Static PDR % | Risk-Aware PDR % | OLSR PDR % | AODV PDR % | Static exposure % | RA exposure % |
|---|---|---|---|---|---|---|
| 0 | 99.95 +/- 0.01 | 99.95 +/- 0.01 | 99.62 +/- 0.04 | 56.60 +/- 1.76 | 0 | 0 |
| 1 | 90.81 +/- 2.71 | 99.96 +/- 0.03 | 99.34 +/- 0.47 | 58.08 +/- 1.87 | 18.33 +/- 5.51 | 0 |
| 2 | 84.22 +/- 3.66 | 99.96 +/- 0.01 | 98.64 +/- 1.03 | 57.29 +/- 3.77 | 31.33 +/- 7.37 | 0 |
| 3 | 80.25 +/- 2.97 | 99.96 +/- 0.00 | 98.86 +/- 0.63 | 57.43 +/- 3.96 | 39.33 +/- 6.03 | 0 |
Risk-Aware - Static, same seed: nominal PDR +9.15 / +15.74 / +19.70 pp (k = 1/2/3; 3/3 seeds higher each);
exposure -18.33 / -31.33 / -39.33 pp (3/3 lower). Every exposed static source had a safe alternative
(srcs_unavoidable = 0 in all 9 runs), so Risk-Aware exposure is 0 in every run.
Path cost: over ALL sent packets the relay-hop count of Risk-Aware k = 3 equals Static's (0.6698 vs 0.6700,
0.4899 vs 0.4899, 0.6799 vs 0.6799 for seeds 20/21/22): equal-length safe detours exist at this density. The
+0.04 / +0.07 / +0.09 delivered-hop and +6 to +23 ms p50-p99 differences vs Static at the same k are therefore
survivorship (Static loses its relayed packets). Against the k = 0 baseline Risk-Aware k = 1-3 is within
-1.1 to +2.5 ms (p50/p95/p99 means) and -0.001 to +0.003 gateway airtime.

AODV collapse at N = 100 (finding; cause NOT confirmed)
AODV delivers 55-61 % at every k (k = 0 included, so it is not caused by the risk model), whereas at N = 30,
8 kbps it delivers 99.99 % (k = 0, 10 seeds). Facts (aodv_k0 seed 20 vs olsr_k0 seed 20): gateway airtime 0.69 vs
0.40; group-addressed data frames 202,494 vs 20,147; unicast data PSDUs 1,380,871 vs 494,777; BAR PSDUs 183,074 vs
1,272; MPDUs expired (lifetime) 157,691 vs 0, spread over all nodes (hop 1: 56,769 over 33 nodes, hop 2: 100,448
over 67 nodes); no-route drops 829. Loss is sustained (39.7-65.8 % PDR in every 30 s window, seeds 20-22) and hits sources one hop
from the gateway too (AODV 68.8-78.6 % vs OLSR 99.9 %, 90 m-graph hop; corrected 2026-10-24: the earlier
"0-relay 54.7 %" grouped lost packets by relays reached and is withdrawn). A few packets traverse 14-63 relays (transient routing loops). Hypothesis: AODV route-discovery
broadcast traffic plus synchronized CBR saturates the shared channel at N = 100; not tested. A contribution of the
risk-v2 Block Ack modification cannot be excluded (ba_fix_events 1,692 vs OLSR 586). AODV comparisons at N = 100
should be reported with this caveat or after a targeted diagnosis.
Update 2026-10-24: diagnosed in ../aodv-diag-n100-20261024T204129/README.md. The Block Ack fix is excluded
(fix off: 53.2 % PDR vs 55.1 %). The likely cause is an AODV route-maintenance loop: every MAC drop is read as a
link break, which triggers RERR and rediscovery and adds airtime; synchronized CBR is associated with it.

Disclosed limitations (as the N = 30 batch, plus)
1. Risk selection bias: HIGH_RISK relays are the top-k of the static 90 m BFS tree (subtree rule).
2. Oracle knowledge: Risk-Aware knows every node's risk exactly; upper bound.
3. Static/Risk-Aware use the 90 m disk graph; OLSR/AODV use the real radio range (OLSR 1.39-1.40 delivered hops,
   AODV 1.72-1.74, Static/RA 1.52-1.61).
4. Synchronized CBR traffic (V3 design).
5. risk-v2 Block Ack modification; residual tail documented at saturation (not reached here: airtime <= 0.44
   except AODV).
6. Delay over delivered packets only (survivorship, see above).
7. 8 kbps is light load for Static/RA/OLSR (gateway airtime per run 0.186-0.443; configuration means 0.194-0.400); only 3 seeds.
