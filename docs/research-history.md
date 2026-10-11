# Research History

This document traces the project's progression from its first prototype through the frozen
Phases 1–7 research, and now into the proposed Phase 8, so that earlier code and results remain
understandable without being confused with current or newer findings. See the main
[README](../README.md) for the current, authoritative status of every phase.

## V1 — `scratch-simulator.cc`

Earliest implementation. Kept for reference only; not used in any reported result.

## V2 / V2.7 — `scratch/iot-network.cc`

First complete study: 3 protocols (AODV, OLSR, Static) × 4 network sizes (10/20/30/50 nodes) × 5
seeds = 60 runs, on a multi-hop 802.11b ad-hoc mesh. Established the basic simulation environment
(topology generation, FlowMonitor-based metrics, static-routing BFS construction) that all later
phases build on. Identified the AODV FlowMonitor `PacketsSent`-denominator behaviour later
reconfirmed in the frozen research (see the README's AODV caveat).

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

## Phase 2 — V4 Sigmoid-Based Adaptive Routing

An adaptive route-cost mechanism (a risk/load sigmoid cost function with six tunable parameters)
was implemented on the V3 topology and evaluated across three datasets: a matched comparison
against Static (594 runs), a 27-configuration sensitivity sweep (297 runs), and a 6-configuration
activation screen (66 runs, `analysis/update8-tier1-activation/`). Result: the mechanism activates
and measurably restructures routes, but does not produce a statistically credible delivery
improvement over Static — a valid negative result that closed the "better path selection" line of
investigation.

## Phase 3 — Bottleneck Characterisation — `scratch/iot-network-bottleneck-probe.cc`

Since neither node/traffic scaling (Phase 1) nor better routing (Phase 2) explained the
degradation, a new instrumented simulator was built to measure *where* the loss occurs: per-node
airtime, MAC-queue drops, PHY RX drops, and hop distance. 176 runs (OLSR/Static × 4 node counts ×
2 traffic levels × 11 seeds) localised the dominant measurable bottleneck to the gateway and
first-hop neighbourhood under near-saturated conditions.

## Phase 4 — Retry-Exhaustion Validation

Added a direct measurement of MAC-layer retry exhaustion (36 runs) to test whether it was the
mechanism behind the airtime/queue signature. Result: retry exhaustion is real and measurable, but
secondary to MAC-queue overflow, and spatially concentrated in the opposite location (farther from
the gateway).

## Phase 5 — Offered-Rate Intervention

Tested whether reducing offered traffic rate (16/12/8/4 kbps) relieves the identified bottleneck
(72 runs: OLSR/Static × N=50/75/100 × 4 rates × 3 seeds). Result: PDR improves substantially and
consistently for OLSR at N=75 and N=100 (the near-saturated conditions), with the clearest single
piece of evidence being that N=100 delivered throughput actually *rises* at a reduced offered
rate.

## Phase 6 — Static/N=50 Diagnostic

Static routing at N=50 did not show the same improvement in Phase 5. A focused 12-run diagnostic
found that congestion was genuinely relieved (airtime and MAC-queue drops fell as expected), but
the relieved mechanisms were never the dominant source of loss for this specific condition —
explaining the null result without inventing a cause for the large residual (unattributed) loss.

## Phase 7 — Final Reproducibility Validation

A 51-run validation matrix independently re-executed representative conditions from every prior
phase and compared 687 metrics against the frozen datasets: 681 applicable comparisons passed
exactly, 0 failed, 0 numerical drift. This confirmed the frozen results are reproducible from the
current source code and configuration, closing Phases 1–7 of the research.

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

## Summary

```
V1 -> V2/V2.7 -> early V3 sigmoid prototype -> V3 Official Baseline -> V4 Sigmoid Adaptive Routing
   -> Bottleneck Characterisation -> Retry-Exhaustion Validation -> Offered-Rate Intervention
   -> Static/N=50 Diagnostic -> Final Reproducibility Validation (FROZEN, Phases 1-7)
   -> BA Topology / Risky-Node Routing (Phase 8, PROPOSED 2026-10, not yet executed)
```
