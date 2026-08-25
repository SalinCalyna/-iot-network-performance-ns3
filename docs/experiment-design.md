# Experiment Design — V3 Sigmoid Extension

## Topology justification

15 nodes: 1 Gateway (Node 0), 1 Server (Node 1), 13 sensor/relay nodes (Nodes 2-14) in three
spatial clusters at increasing distance from the Gateway (near ~70 m, middle ~150 m from Gateway,
far ~230 m from Gateway), rather than a uniform-random field (V2.7's approach) or a straight chain.
This gives, by construction rather than chance:

- Short intra-cluster hops (dense local connectivity within each cluster).
- Genuine multi-hop paths from the far cluster to the Gateway (not achievable in a single hop).
- Multiple candidate relay nodes within each cluster, so more than one physical path can exist
  between a given sensor and the Gateway — the actual chosen path depends on the routing
  protocol/metric, which is the point of the comparison.
- A deliberate slight offset in the middle cluster's position (not perfectly collinear with the
  near and far clusters) so boundary nodes have more than one geometrically plausible route,
  rather than a single forced chain.

Node roles are fixed and never renumbered: Node IDs 0-14 always mean the same thing across every
protocol, seed, and traffic condition, exactly as V2.7 already guarantees for its own node
numbering.

## Traffic conditions

| Label | Data rate per sensor | Total offered load (13 sensors) |
|---|---|---|
| Low | 4 kbps | 52 kbps |
| Medium | 8 kbps | 104 kbps |
| High | 16 kbps | 208 kbps |

Medium (8 kbps) matches V2.7's existing baseline rate, so the two studies share a reference point.
`--trafficCondition` is a label only; `--dataRate` is the parameter that actually controls the
simulation, and the experiment runner is responsible for keeping the two consistent.

## Protocols

| CLI value | Description |
|---|---|
| `aodv` | Unmodified ns-3 AODV (reactive) |
| `olsr` | Unmodified ns-3 OLSR (proactive) |
| `static` | Same BFS shortest-hop-count baseline as V2.7 |
| `sigmoid` | New: Dijkstra over a sigmoid-weighted composite edge cost — see `sigmoid-metric.md` |

## Sigmoid parameters to sweep

k = 0.1, 0.2, 0.3 (as specified), x0 = 0.5 (midpoint of the normalized [0,1] input range) by
default. See `sigmoid-metric.md` for why this k range sits in the sigmoid's near-linear regime
given how the inputs are normalized, and what that implies for interpreting the k sweep.

## Experiment matrix

**Validation (already run, this pass):** 15 nodes x 4 protocols x 1 traffic condition (medium) x
1 seed = 4 runs. Confirmed: builds, runs, produces non-degenerate CSV rows for all four
protocols, no crashes, no unreachable-sensor warnings.

**Full matrix (not yet run — requires explicit approval):** 15 nodes x 4 protocols
(aodv/olsr/static/sigmoid, with sigmoid run once per k value) x 3 traffic conditions x 5 seeds.
That is 3 non-sigmoid protocols x 3 traffic x 5 seeds = 45 runs, plus sigmoid x 3 k-values x 3
traffic x 5 seeds = 45 runs, for 90 total new runs. This does not touch, overwrite, or mix with
V2.7's existing 60 runs.

## CSV output

New directory, new naming scheme, never colliding with V2.7:

```
results/v3/<protocol>_15_<traffic>.csv
```

Columns: `protocol,seed,nodes,traffic_condition,data_rate,packets_sent,packets_received,
packet_loss,pdr,throughput_kbps,delay_sec,jitter_sec,hop_count,hop_count_method,
routing_overhead_packets,unreachable_sensors,sigmoid_k,sigmoid_x0,sigmoid_w_link_quality,
sigmoid_w_load` — the last four are blank (not zero) for non-sigmoid rows, since they are not
applicable rather than zero-valued.

## What is explicitly deferred, pending your review

- The full 90-run matrix (gated on you approving the design, and on the routing-overhead
  measurement gap in `methodology.md` being either fixed or explicitly accepted as a known
  limitation for this round of experiments).
- Dashboard integration of V3 results (Topology/Real-World Map/Sigmoid Analysis pages) — building
  UI against a 4-row validation dataset risks presenting a placeholder as if it were a real result;
  this should follow, not precede, the full matrix.
- `git commit`/`push` — not done in this pass.
