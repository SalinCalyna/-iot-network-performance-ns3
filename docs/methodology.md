# Methodology

**Analysis of an IoT Network Performance Using NS-3**
Salinthip Keereerat (6630613037), College of Computing, Prince of Songkla University, Phuket Campus
Advisor: Komsan Kanjanasit — Co-advisors: Wisarut Chantara, Kullawat Chaowanawatee

This document covers the V3 sigmoid-metric extension. The V2.7 baseline (10/20/30/50-node
uniform-random topology, AODV/OLSR/Static, 60 runs) is unchanged and documented in the
dashboard's own Methodology tab — this file does not restate it.

## Pipeline

```
Topology (15 nodes, 3 clusters)
        v
802.11b ad-hoc wireless mesh
        v
Routing protocol: AODV | OLSR | Static | Sigmoid
        v
IoT traffic (per-sensor UDP CBR, low/medium/high rate)
        v
FlowMonitor
        v
CSV (results/v3/<protocol>_15_<traffic>.csv)
        v
Python analysis (experiments/analyze_results.py or a v3-specific script)
        v
Graphs / dashboard
```

## Simulator and files

- Simulator: ns-3 (ns-3.47-dev), as used throughout this project.
- V3 simulation source: `scratch/iot-network-v3.cc` — a **separate** program from
  `scratch/iot-network.cc` (V2.7). V2.7 is untouched; the exact binary that produced the 60
  existing `results/*.csv` rows remains reproducible.

## Node roles (never renumbered)

| Node | Role |
|---|---|
| 0 | Gateway/Sink — the only node bridging the wireless mesh and the wired backhaul |
| 1 | Server — reached only via a wired point-to-point link from the Gateway |
| 2-14 | 13 IoT sensor/relay nodes, in 3 spatial clusters at increasing distance from the Gateway |

### Why the Gateway and Server are on separate links, not both in the wireless mesh

An earlier design (proposed for "V2.8") considered giving the Gateway and Server their own
addresses within the same wireless routing domain. That was rejected: for a sensor to route
traffic all the way to an external Server subnet, the routing protocol has to advertise
reachability to that subnet, and ns-3's AODV and OLSR implementations do this differently. OLSR
supports HNA (Host and Network Association) for exactly this; ns-3's AODV implementation does
not. Comparing AODV against OLSR under a setup where only one of them can actually reach the
Server would not be a fair, controlled comparison — it would test which optional protocol feature
exists more than routing-metric behavior.

**Resolution:** the wireless routing comparison is scoped to the sensor-to-Gateway hop only,
exactly the same measurement boundary V2.7 already uses. The Gateway-to-Server hop is a separate,
always-on wired backhaul link (10 Mbps, 2 ms), with a small periodic relay application making it
functionally real (not just a cosmetic node), but its performance is **not** part of the routing
metrics recorded in the CSV. This keeps the four routing modes on genuinely equal footing.

## Application-layer packet counting

Packets Sent, Packets Received, Packet Loss, and PDR are all counted from ns-3 FlowMonitor's
per-flow statistics (`FlowMonitor::GetFlowStats()`), filtered to flows destined for the Gateway's
mesh address on UDP port 9 (the sensor application's destination port) — i.e., at the transport/
application boundary, not from PHY or MAC-layer frame counters. This matches how V2.7's metrics
were already computed and keeps the two studies comparable in method.

**Known limitation carried over from V2.7 (see the V2.7.1 validation report):** ns-3's FlowMonitor
counts a locally-originated packet via the `SendOutgoing` trace, and AODV's route-discovery queue
was found to cause AODV's `PacketsSent` to scale with topology/network size in a way OLSR's and
Static's do not. This has not been fixed here and applies equally to V3's AODV runs. PDR
comparisons involving AODV should be read with that caveat.

## FlowMonitor

`FlowMonitorHelper::InstallAll()` is used, same as V2.7. In addition to the delay/throughput/PDR
fields already used in V2.7, V3 also reads:

- `FlowStats::jitterSum` — real, existing ns-3 field, aggregated the same way as delay.
- `FlowStats::timesForwarded` — used as an **approximate** hop-count proxy for AODV/OLSR (see
  below); not used for Static/Sigmoid, which have an exact, directly-computed hop count instead.

FlowMonitor XML export was not enabled for the validation runs (kept identical in scope to V2.7,
which also does not serialize XML) — see Future Work if per-flow/per-drop-reason XML data is
wanted for the full experiment matrix.

## Hop count

| Protocol | Method | Column value |
|---|---|---|
| Static, Sigmoid | Exact — the path length from the same offline graph computation that installs the routes | `hop_count_method = exact` |
| AODV, OLSR | Approximate — `1 + (timesForwarded / receivedPackets)`, averaged over received packets | `hop_count_method = approx_timesForwarded` |

The CSV always records which method was used for a given row; the two are not directly comparable
without accounting for that.

## Routing overhead — a real measurement limitation found during validation

Routing overhead is intended to capture routing-protocol control traffic: AODV's RREQ/RREP/RERR
(UDP port 654) and OLSR's HELLO/TC (UDP port 698). FlowMonitor tracks all IP traffic including
these, and V3 classifies flows on those two ports separately from sensor data traffic.

**During the validation run, OLSR reported exactly 0 overhead packets and AODV reported a
non-zero but almost certainly incomplete count.** Reading ns-3's FlowMonitor source
(`src/flow-monitor/model/ipv4-flow-probe.cc`) confirms the cause: the `SendOutgoing` trace that
FlowMonitor uses to count transmitted packets explicitly skips non-unicast destinations
(`if (!m_ipv4->IsUnicast(...)) return;`). OLSR's HELLO and TC messages, and AODV's RREQ, are sent
as broadcasts — FlowMonitor never sees them at all. AODV's small non-zero count in the validation
run most likely reflects only its unicast RREP/RERR traffic, not the (typically much larger) RREQ
flood.

**This means the current `routing_overhead_packets` column undercounts OLSR overhead severely and
AODV overhead partially, and should not yet be presented as a real cross-protocol overhead
comparison.** Static and Sigmoid genuinely have zero *runtime* control overhead by construction
(no protocol messages are exchanged after route installation), so their zero is correct — the
problem is specifically that AODV's and OLSR's true values are not being captured. Fixing this
properly would require hooking a different trace source (e.g. `WifiMac`-level or
`AodvHelper`/`OlsrHelper` transmission traces rather than FlowMonitor's IP-layer `SendOutgoing`),
which has not been implemented and needs a design decision before it's used for the full
experiment matrix — see the accompanying report for a specific ask on this.
