# AODV diagnostic, N = 100, 8 kbps, k = 0, seed 20 (2026-10-24)
Runner `experiments/wifi6-risk/run_aodv_diag.py`; validated risk-v2 binary d909f6de / source 33b350ab, unchanged.
Both runs set NS_LOG="AodvRoutingProtocol=level_logic|prefix_time|prefix_node"; the log (21.2 M / 21.7 M lines) was
not stored. It was piped through `aodv_log_counter.py`, which writes only counts to `aodv_log_counts.json`.
- bafix0/: argv of n100-8k-v2-20261024T165009 aodv_k0_rate8_seed20 + --baSsnFix=0
- bafix1/: identical argv (fix on). Every output file is byte-identical to the original run except the wall-clock
  timestamp in probe_aggregate.csv, so logging did not alter the simulation.
Checks (analyze_pilot_n30.py, per sub-batch): 13/13 passed each. With the fix off the simulator writes no
ba_ssn_fix.csv; the analyzer accepts that file being absent only when argv contains --baSsnFix=0.
Single seed: these are observations for seed 20, not estimates.

## Fix off vs fix on (seed 20)
| metric | fix off | fix on |
|---|---|---|
| nominal = sink PDR % | 53.21 | 55.13 |
| gateway airtime | 0.691 | 0.697 |
| broadcast (group) data frames | 208,899 | 202,494 |
| unicast data PSDUs (HE_SU) | 1,393,752 | 1,380,871 |
| BAR PSDUs | 177,748 | 183,074 |
| MPDUs expired (lifetime) | 162,246 | 157,691 |
| retry-limit drops | 1,926 | 1,929 |
| no-route drops | 815 | 829 |
| delay p50 / p95 / p99 ms | 219 / 729 / 1,111 | 215 / 700 / 969 |
| packets > 10 s (max) | 3 (48.0 s) | 0 (9.8 s) |
| AODV link-failure events | 163,075 | 161,253 |
| RERR sent with precursors / without | 118,194 / 105,382 | 117,736 / 106,366 |
| RERR receptions | 1,247,226 | 1,237,296 |
| RREQ originations (to gateway / other) | 5,458 (2,283 / 3,175) | 5,350 (2,254 / 3,096) |
| RREQ receptions | 3,550,283 | 3,462,743 |
| gratuitous RREPs by intermediate nodes | 108,482 | 106,664 |
| Hellos sent | 5,857 | 5,371 |
From existing traces (n100-8k batch, k = 0, seeds 20-22), AODV vs OLSR: 52-58 vs 7-11 path changes per source
per minute; 82-99 vs 14-19 distinct paths per source; 84-358 vs 0-12 packets on looping paths; 49.8-55.1 % of AODV's
lost packets were lost before any relay forwarded them (path = source + relays that forwarded). Per-source
PDR (sources at 1 / 2 hops of the 90 m graph): AODV 68.8-78.6 % / 42.9-47.8 %, OLSR 99.9 % / 99.4-99.5 %.
[Corrected 2026-10-24: an earlier note in the N = 100 README grouped packets by relay_hops, which for lost packets
counts only the relays reached.]

## Confirmed observations
1. The Block Ack modification is not the cause. With the fix off, PDR is 1.9 pp lower, airtime, control traffic
   and BARs are unchanged, and the long tail returns (3 packets > 10 s). The 177k BARs come from standard ns-3
   BlockAck recovery, not from the fix.
2. MAC data load alone is not the cause. OLSR carries the same application traffic at N = 100 with airtime 0.40
   and 99.6 % PDR. AODV at N = 30, 64 kbps (2.4x the total offered load, airtime 0.55, same synchronized CBR)
   delivers 99.95 % with 9.9k broadcast frames.
3. ns-3 AODV treats every dropped unicast MPDU as a link failure, whatever the drop reason (queue-lifetime expiry
   included): aodv-routing-protocol.cc:784-791 (DroppedMpdu -> NotifyTxError, reason ignored) and
   aodv-neighbor.cc:167-179 (neighbour closed -> Purge -> SendRerrWhenBreaksLinkToNextHop).
4. AODV control activity is driven by route maintenance: about 161k link failures and 118k RERRs to active
   precursors (1.24M receptions). RREQ originations are only about 20 per second network-wide (5.4k), but each
   flood is received about 650 times (3.5M receptions), so in receptions the (re-)discovery floods are the largest
   control component, followed by RERRs; plus 107k gratuitous RREPs. [Wording corrected 2026-10-24: the earlier
   "dominated by route maintenance" understated the channel cost of RREQ floods.]
5. Link failures run at 229/s before data starts (0-30 s; Hello-loss expiry only, with no routes and no
   precursors). They jump to 572-579/s within the first 10 s of traffic, then stay flat to 300 s. The collapse is
   immediate and sustained; it does not escalate over the run.
6. Synchronized CBR is associated with discovery. 39.9 % of RREQ originations fall in the first 32 ms of the
   512 ms CBR cycle (uniform would be 6.25 %), as do 11.8 % of link failures and 11.2 % of gratuitous RREPs. At
   30.512 s every sensor sends its first RREQ at the same instant.

## Likely root cause (inference; not isolated by a controlled change)
A self-sustaining AODV route-maintenance loop at N = 100. A unicast MPDU dropped for any reason, mostly queue-
lifetime expiry under contention, is read as a link break. That triggers a RERR (about 10 receptions each),
invalidates the routes, and starts rediscovery: a network-wide RREQ flood, gratuitous RREPs and new BA agreements
to new next hops. This raises airtime to 0.69, which causes more expiry and more breaks. Synchronized CBR
concentrates discoveries and contention at the send instant, and density (about 650 receptions per flood)
multiplies their cost. The loop does not form at N = 30 or with OLSR, which has no reactive link-failure
signalling.

## Remaining uncertainty
- Breaks after 30 s are not split between MAC-drop and Hello-expiry causes ("Close link" lines were not counted
  separately). The share of expired MPDUs that are unicast vs broadcast is unknown. The per-node correlation of
  MAC drops with link failures is r = 0.55.
- The contributions of synchronized CBR and of the 500 ms MAC queue lifetime are not isolated. The simulator has
  no option to desynchronize CBR, and changing MaxDelay or AODV timers would change the methodology.
- One seed only for fix off.
