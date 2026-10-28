# Research History

This document traces the project's progression from its first prototype through the frozen
Phases 1–7 research, and now into the proposed Phase 8, so that earlier code and results remain
understandable without being confused with current or newer findings. See the main
[README](../README.md) for the current, authoritative status of every phase.

> **Status note (2026-10-28): ARP artifact.** After Phase 7, packet loss that the frozen 802.11b
> instrumentation could not attribute was traced to the Address Resolution Protocol (ARP). Every sensor
> starts sending at the same instant, the ARP requests collide, and packets waiting for address
> resolution are dropped without being counted. The frozen simulators do not pre-populate the ARP cache.
> The affected experiments were re-run, seed-matched, with the ARP cache pre-populated (306
> protocol-comparison, 176 bottleneck and 72 rate-sweep runs; static sensors only). This ARP-fixed
> analysis is the primary 802.11b analysis of the thesis draft (the advisor approved this analysis structure, with the original runs as secondary evidence, in October 2026; the thesis itself remains under advisor review). Phases 1–7 are kept below as they were written, for traceability; statements
> that the ARP-fixed analysis superseded or affects are marked **[superseded]** or **[ARP-affected]**.
> See the [ARP-fixed results](../README.md#ieee-80211b-study-arp-fixed-results-primary) and [`publication/CLAIMS.csv`](../publication/CLAIMS.csv).

## V1 — `scratch-simulator.cc`

Earliest implementation. Kept for reference only; not used in any reported result.

## V2 / V2.7 — `scratch/iot-network.cc`

First complete study: 3 protocols (AODV, OLSR, Static) × 4 network sizes (10/20/30/50 nodes) × 5
seeds = 60 runs, on a multi-hop 802.11b ad-hoc mesh. Established the basic simulation environment
(topology generation, FlowMonitor-based metrics, static-routing BFS construction) that all later
phases build on. Identified the AODV FlowMonitor `PacketsSent`-denominator behaviour later
reconfirmed in the frozen research (see the README's AODV caveat).
**[superseded]** The later V3 sent-count analysis (2026-10) found that the `PacketsSent` undercount
affects OLSR (a send that fails for lack of a route is not counted), not AODV.

## Early V3 sigmoid prototype — `scratch/iot-network-v3.cc`

A separate, early exploration of adaptive routing: a 15-node clustered topology with a 4th
routing mode computing shortest paths over sigmoid-weighted edge costs. Only a 4-run smoke test
was ever executed. This prototype was **superseded** by the V4 Sigmoid-Based Adaptive Routing
study (see below), which is the project's authoritative, statistically-evaluated adaptive-routing
result.

**Filename note (2026-10):** a different, later program is also named `iot-network-v3.cc` — a
26-node Barabasi-Albert topology with degree-based structural risk, written for the Phase 8
BA/risky-node study below. It is unrelated to this 15-node pilot and is not committed to this
repository yet. Do not treat the two as the same experiment.

## Phase 1 — V3 Official Baseline — `scratch/iot-network-v3-ext.cc`

The official, frozen baseline: AODV/OLSR/Static across 6 node counts (10–100), 3 traffic levels,
3 mobility modes, seeds 20–30 (11 seeds) — 1,782 official runs. Established that performance
degrades monotonically with node count and traffic load across all three protocols. This
simulator, not `iot-network.cc`, is the current baseline.
**[ARP-affected]** These runs include the uncounted ARP loss, which affected the protocols unequally.
With ARP fixed (static sensors), Static Routing has the highest delivery in every condition from N = 20
upward (15/15), so the frozen protocol ranking does not carry over. No ARP-fixed mobile run exists.

## Phase 2 — V4 Sigmoid-Based Adaptive Routing

An adaptive route-cost mechanism (a risk/load sigmoid cost function with six tunable parameters)
was implemented on the V3 topology and evaluated across three datasets: a matched comparison
against Static (594 runs), a 27-configuration sensitivity sweep (297 runs), and a 6-configuration
activation screen (66 runs, `analysis/update8-tier1-activation/`). Result: the mechanism activates
and measurably restructures routes, but does not produce a statistically credible delivery
improvement over Static — a valid negative result that closed the "better path selection" line of
investigation.

*Still valid as a result of the original configuration: V4 and Static share the same ARP behaviour, so
this comparison is internally matched. V4 was not re-run with ARP fixed.*

## Phase 3 — Bottleneck Characterisation — `scratch/iot-network-bottleneck-probe.cc`

Since neither node/traffic scaling (Phase 1) nor better routing (Phase 2) explained the
degradation, a new instrumented simulator was built to measure *where* the loss occurs: per-node
airtime, MAC-queue drops, PHY RX drops, and hop distance. 176 runs (OLSR/Static × 4 node counts ×
2 traffic levels × 11 seeds) localised the dominant measurable bottleneck to the gateway and
first-hop neighbourhood under near-saturated conditions.
*Consistent with the ARP-fixed re-runs:* with ARP fixed, gateway-region congestion persists (gateway
airtime 0.86–0.90 from N = 75 upward). MAC-queue drop counts are frame events, not lost packets.

## Phase 4 — Retry-Exhaustion Validation

Added a direct measurement of MAC-layer retry exhaustion (36 runs) to test whether it was the
mechanism behind the airtime/queue signature. Result: retry exhaustion is real and measurable, but
secondary to MAC-queue overflow, and spatially concentrated in the opposite location (farther from
the gateway).

**[superseded form]** "Secondary to MAC-queue overflow" compared shares of loss computed from MAC drop
counters. Those counters record frame events, and in the ARP-fixed Static runs they exceed the measured
packet loss in 141/143 runs, so they cannot be expressed as shares of loss. This measurement has no
ARP-fixed counterpart.

## Phase 5 — Offered-Rate Intervention

Tested whether reducing offered traffic rate (16/12/8/4 kbps) relieves the identified bottleneck
(72 runs: OLSR/Static × N=50/75/100 × 4 rates × 3 seeds). Result: PDR improves substantially and
consistently for OLSR at N=75 and N=100 (the near-saturated conditions), with the clearest single
piece of evidence being that N=100 delivered throughput actually *rises* at a reduced offered
rate.
**[ARP-affected]** With ARP fixed, every reduced rate improved PDR for both OLSR and Static in 18/18
conditions (3 seeds; descriptive).

## Phase 6 — Static/N=50 Diagnostic

Static routing at N=50 did not show the same improvement in Phase 5. A focused 12-run diagnostic
found that congestion was genuinely relieved (airtime and MAC-queue drops fell as expected), but
the relieved mechanisms were never the dominant source of loss for this specific condition —
explaining the null result without inventing a cause for the large residual (unattributed) loss.
**[superseded]** The residual loss was ARP drops: in these 12 runs, ARP drops equal 99.9–101.4 % of the
previously unattributed loss. With ARP fixed, Static N = 50 improves at every reduced rate.

## Phase 7 — Final Reproducibility Validation

A 51-run validation matrix independently re-executed representative conditions from every prior
phase and compared 687 metrics against the frozen datasets: 681 applicable comparisons passed
exactly, 0 failed, 0 numerical drift. This confirmed the frozen results are reproducible from the
current source code and configuration, closing Phases 1–7 of the research.
*Still valid:* this check concerns the reproducibility of the frozen outputs, which it confirms. It does
not address the ARP artifact.

## ARP artifact diagnosis and ARP-fixed re-runs (2026-10, after Phase 7)

A new simulator, `scratch/iot-network-wifi-std-arp.cc`, reproduces the frozen configuration (with the flag
off it reproduced the frozen outputs exactly in 29 regression runs) and adds `--arpPrepopulate`. A paired
diagnostic traced the Phase 6 residual to ARP drops, and the Phase 1, 3 and 5 experiments were re-run with
the ARP cache pre-populated (static sensors). This is the primary 802.11b analysis of the thesis draft (the advisor approved this analysis structure, with the original runs as secondary evidence, in October 2026; the thesis itself remains under advisor review). Details:
[`docs/arp-fixed-reproduction.md`](arp-fixed-reproduction.md).

## Phase 8 — BA Topology / Risky-Node Routing (proposed, opened 2026-10)

Per advisor direction (2026-10), a new phase on top of the frozen Phases 1–7: explicit low-risk /
high-risk per-node states on a Barabasi-Albert (BA) scale-free topology, studying how 0, 1, 2, and
3 high-risk nodes affect route selection and performance. **Status: proposed design only — no
code written for this phase, no simulation run, no data collected.** This reuses the filename
`scratch/iot-network-v3.cc` for a program distinct from the 15-node pilot above (see that
section's 2026-10 note); the BA program itself is not yet part of this repository.

Full audit of the existing BA-topology code (a related but different, already-written 26-node
risk-*scoring* simulator that has never been run), the proposed risk-state definition and its
references, how risk would and would not affect routing, the matched 0/1/2/3-node experiment
matrix, a 12-run pilot design, and the logging additions required: see
[`docs/v1-v4-methodology-results.md`](v1-v4-methodology-results.md), §BA topology / risky-node
routing.

## Wi-Fi 6 Risk-Aware Routing study (completed 2026-10)

A separate follow-on study, run on an IEEE 802.11ax (Wi-Fi 6) version of the gateway-centric
wireless mesh. It is distinct from the frozen 802.11b Phases 1–7 (different PHY/MAC, new
simulator `scratch/iot-network-wifi6-risk-v2.cc`) and from Phase 8 (no BA topology).
- **Risk model:** explicit LOW_RISK / HIGH_RISK relay states (drop probability 0 / 0.5 for transit
  data packets), with k = 0–3 high-risk relays.
- **Protocols:** Static, Risk-Aware (risk-weighted Dijkstra, oracle risk knowledge), OLSR and
  AODV; 8 kbps per sensor.
- **Simulator fix:** one confirmed ns-3 Block Ack defect is fixed in risk-v2. The alternative
  variants risk-v3 and risk-v4 were evaluated and not adopted.

Experiments completed:
- **Pilot:** N = 30, 96 runs.
- **Load calibration:** N = 100, OLSR, 9 runs.
- **Main N = 30 experiment:** seeds 20–29, 160 runs (inferential).
- **Main N = 100 experiment:** seeds 20–22, 48 runs (descriptive only).
- **AODV diagnostic:** 2 runs, seed 20.

Main result: at N = 30 and k = 3, Risk-Aware raised nominal PDR over Static by +23.18 pp
[95 % CI +19.81, +26.54] and cut exposure by 46.33 pp, in 10/10 matched pairs (Holm-adjusted
exact Wilcoxon p = 0.0117). At N = 100 the direction was the same in 3/3 seeds, reported
descriptively. Secondary finding: AODV degrades at N = 100 (56.60 % vs OLSR 99.62 %). The
suspected route-maintenance feedback loop is a hypothesis, not an isolated cause.

**Not run:** the N = 100 saturated-load risk experiment (pending approval).

Details: README § Wi-Fi 6 Risk-Aware Routing; reproduction guide
[`docs/wifi6-risk-reproducibility.md`](wifi6-risk-reproducibility.md); live dashboard
https://salincalyna.github.io/-iot-network-performance-ns3/site/index.html

## Summary

```
V1 -> V2/V2.7 -> early V3 sigmoid prototype -> V3 Official Baseline -> V4 Sigmoid Adaptive Routing
   -> Bottleneck Characterisation -> Retry-Exhaustion Validation -> Offered-Rate Intervention
   -> Static/N=50 Diagnostic -> Final Reproducibility Validation (FROZEN, Phases 1-7)
   -> ARP artifact diagnosis + ARP-fixed re-runs (2026-10; primary 802.11b analysis, structure
      approved by the advisor; supersedes Phase 4's share-of-loss form and the Phase 6 residual)
   -> BA Topology / Risky-Node Routing (Phase 8, PROPOSED 2026-10, not yet executed)

Separate track (802.11ax wireless mesh, not BA):
   Wi-Fi 6 Risk-Aware Routing (COMPLETED 2026-10: N=30 x 10 seeds, N=100 x 3 seeds)
   -> N=100 saturated-load risk experiment (NOT RUN, pending approval)
```
