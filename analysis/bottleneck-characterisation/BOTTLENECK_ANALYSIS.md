# BOTTLENECK CHARACTERISATION — read-only analysis of existing V3/V4 data

**Type:** read-only analysis. No simulation was run; no source, dataset, dashboard, or
checksum was modified; no new statistical testing on the 66-run Tier-1 set; no commit/push.
Inputs: `results/v3-ext/*.csv` (V3 Official, 1,782 rows, seeds 20–30, 300 s),
`results/v4-sensitivity/*.csv` (297), `results/v4-matched/*.csv` (594),
`analysis/update8-tier1-activation/data/v4_50_medium_static.csv` (66). All read-only.

**Research question:** are the observed PDR ceiling and the degradation at higher node
counts / traffic levels primarily caused by **network contention / saturation**, rather
than by **reachability failure** or **poor route selection**?

**Hypothesis H1:** *the dominant performance bottleneck is contention/saturation near the
sink, rather than reachability or poor path selection.*

**Metric available for a per-run picture only.** The CSVs hold per-run aggregates (PDR,
throughput, delay, jitter, packet loss, routing overhead, mean hop count, path changes,
Avg/Max link-utilisation proxy, unreachable-sensor count). There are **no node positions,
no per-node or per-link statistics, no MAC/airtime counters, no queue-drop counts**. Any
statement about *where* loss occurs is therefore structural inference, not measurement.

---

## 1. Executive finding

The existing data supports the **"congestion/contention, not reachability, not
route-selection quality"** part of H1 strongly, and the **"specifically near the sink /
in the gateway's 1-hop ring"** part only as a plausible structural inference that the
available metrics cannot confirm.

- **Reachability is not the cause at scale.** `UnreachableSensors = 0` in every one of the
  50-, 75-, and 100-node conditions (all protocols, all traffic, all mobility). Non-zero
  unreachable counts occur only at 10 nodes (mean ≈ 0.9, i.e. ~9 % of sensors) and 20
  nodes (mean ≈ 0.2) — a sparse-topology effect in the opposite regime from where the
  ceiling/degradation question lives.
- **Route selection is not the lever.** Substantial route-tree restructuring (V4 Tier-1
  `x0_R = 0.80, x0_L = 0.50`: +27.9 % mean hop count, changed in all 11 seeds) leaves PDR
  statistically unchanged. Three different routing approaches at the matched 50 / medium /
  static condition — OLSR (37.9 %), Static (36.4 %), V4 (34.8 %) — all sit within ~3 points
  despite completely different route trees and route-maintenance strategies. Stage-2
  confirmed V4 ≡ Static on 7/8 metrics across all 594 matched conditions.
- **The signature of a capacity limit is present.** Delivered throughput **rises to a peak
  and then declines** as offered load grows (OLSR at high traffic: 118 → 194 → 267 → **360
  (50 nodes)** → 330 → 247 kbps over 10→100 nodes), and the **delivered fraction**
  (throughput ÷ offered) craters (OLSR high traffic: 73.5 % → 15.4 %; medium: 69.6 % →
  34.1 %). Peak delivered throughput anywhere is ≈ 430–470 kbps ≈ **43–47 % of the nominal
  1 Mbps DSSS PHY**, and it does not increase however much more is offered. Delay and jitter
  rise monotonically with node count and traffic for every protocol.

**Decision: H1 PARTIALLY SUPPORTED** (§9).

---

## 2. Evidence FOR H1

| # | Observation | Value / detail | Why it supports H1 |
|---|---|---|---|
| F1 | `UnreachableSensors = 0` at every 50/75/100-node condition | 0 of 1,782 rows at N ≥ 50; non-zero only at N = 10 (mean 0.94) and N = 20 (mean 0.21) | Degradation at scale is **not** a reachability / disconnection failure — every sensor has a topological path to the gateway |
| F2 | Delivered **throughput peaks then declines** as offered load rises | OLSR, high traffic: 118 → 194 → 267 → **360 (peak, 50 nodes)** → 330 → 247 kbps (10→100 nodes) | Adding offered load *reduces* delivered load — the defining signature of a **saturated shared medium / congestion collapse** |
| F3 | **Delivered fraction** (throughput ÷ offered) falls monotonically with offered load | OLSR: node count 74 → 44 % (low), 70 → 34 % (medium), 74 → 15 % (high); traffic 49 → 33 % (pooled). Static: 48 → 15 % (low), 49 → 21 % (medium) | A smaller share of offered traffic gets through as you offer more → the network is **capacity-limited**, not merely "more packets to lose" |
| F4 | Delivered-throughput ceiling ≈ 43–47 % of nominal PHY | max ThroughputKbps: OLSR 429.6, Static 467.9 (nominal 1000) | Consistent with the **effective CSMA/CA aggregation capacity** of a shared 802.11 DSSS 1 Mbps channel under many contending senders (typically 40–60 % of nominal, less with more senders / hidden terminals) |
| F5 | Massive route restructuring does not move PDR | V4 Tier-1 `x0_R=0.8, x0_L=0.5`: +27.9 % hop count, 11/11 seeds re-routed, PDR +3.5 % (sign-test p = 1.0, negative at the median). Config with 0 % route change: PDR −4.1 % (execution noise). Route change and PDR are **decoupled** | If path quality were the constraint, changing the paths this much would move PDR. It does not → **path selection is not the bottleneck** |
| F6 | Three routing approaches converge on the same PDR ceiling | 50 / medium / static, seeds 20–30: OLSR 37.9 %, Static 36.4 %, V4 34.8 % (all `PathChanges` ≈ 0–572, wildly different trees) | The ceiling is a property of the **scenario**, not of any protocol's route selection |
| F7 | Delay and jitter rise monotonically with node count and traffic for every protocol | Static delay 0.032 → 0.160 s (10→100 nodes); OLSR delay 0.041 → 0.369 s; jitter tracks | Queueing / contention accumulates as offered load grows |
| F8 | AODV's much lower PDR correlates with its control-plane load on the shared medium | 50 / medium / static: AODV PDR 20.2 % with **216,552** routing-overhead packets and `PathChanges` ≈ 1732; OLSR/Static PDR ≈ 37 % with ~0–572 | A within-scenario demonstration that **adding traffic near the aggregation region degrades delivery** — AODV congests its own sink neighbourhood with RREQ/RREP/RERR |
| F9 | Shallow topology funnels all traffic through the gateway's neighbourhood | Gateway at field centre; radio range 90 m in a 250 m field → 40.7 % of the area (≈ 20 sensors at N = 50, ≈ 41 at N = 100) is within 1 hop of the gateway. Observed mean hop count 1.2–1.6 (all protocols) | 100 % of application traffic must be received by the gateway over one shared medium, via a 1-hop ring whose links are all in mutual carrier-sense range — a **mandatory aggregation funnel** |

---

## 3. Evidence AGAINST H1 (and confounds / limits)

| # | Observation | Why it is a caveat |
|---|---|---|
| A1 | **No direct measurement of the sink region.** No node positions, no per-node/per-link stats, no MAC airtime, no queue-drop counts in any dataset | The "loss concentrates in the gateway's 1-hop ring" claim is **structural inference** (geometry + range + hop count), not something the data measures. It cannot be distinguished from **distributed relay congestion** in the inner field |
| A2 | The Link-Utilisation proxy, taken at face value, would **understate** congestion | `MaximumLinkUtilization` stays ≈ 0.05 while aggregate delivered throughput rises 46 → 172 kbps (Static, 10→100 nodes). The proxy is *delivered bytes ÷ nominal PHY* **per neighbour pair**; it excludes retries, backoff, ACKs, headers, and other nodes' airtime, and per-link load spreads as N grows. So a MaxLU of 0.05 is **not** evidence of an un-congested channel — the saturation case rests on F2–F4 (throughput), not on the LU proxy |
| A3 | Static's PDR is **flat-to-slightly-up** with traffic (26 → 30 → 30 % low→medium→high, pooled) | A simple "more offered load → proportionally more sink loss" model predicts Static PDR should *fall* with traffic. It does not. Possible reasons: Static is already at a loss floor at low traffic (its low-traffic PDR is only 26 %, far below OLSR's 52 %), or Static's loss is dominated by a **route-staleness / placement effect** that is load-independent. This weakens a *pure* load-driven sink-saturation story for Static specifically |
| A4 | AODV's collapse is **partly its own protocol overhead** | So "all routing approaches degrade" is cleanest for OLSR and Static; AODV degrades for a **compounded** reason (aggregation contention *plus* self-inflicted control traffic). AODV is still consistent with H1 (F8) but is not a clean independent replicate |
| A5 | Small-N figures carry a **reachability artefact** | At N = 10, ~9 % of sensors are unreachable in a typical run, so 10-node PDR is not a pure congestion/route comparison. (Does not affect the N ≥ 50 conclusion, where UnreachableSensors = 0.) |
| A6 | The mechanism of loss (MAC contention drop vs interface-queue overflow vs collision) is **not identified** | Both are "congestion, not path quality," but "sink-side MAC contention" vs "relay queue overflow" implies different interventions and is unresolved by aggregate PDR / delay |

---

## 4. Sink 1-hop-ring assessment

**Cannot be measured from the existing data.** The assessment is:

- **Structural argument (strong):** the gateway sits at the field centre with a 90 m range
  in a 250 m field. 40.7 % of the field area is within one hop of the gateway (≈ 20 sensors
  at N = 50, ≈ 41 at N = 100). The observed mean hop count (1.2–1.6 for every protocol at
  every node count ≥ 20) confirms a **shallow topology**: essentially all traffic reaches
  the gateway in 1–2 hops. Every packet in the network must therefore be *received by the
  gateway* over the single shared medium in its vicinity, and the ~59 % of sensors that are
  2+ hops out must additionally have their packets *relayed* by a 1-hop node — doubling the
  transmission count in that same carrier-sense domain. This is a mandatory funnel that no
  route choice within the field can bypass.
- **Consistency with the data (good):** the throughput plateau/collapse (F2), the
  capped ~430–470 kbps ceiling (F4), the route-insensitivity of PDR (F5–F6), and AODV's
  self-congestion (F8) are all exactly what an aggregation-medium saturation would produce.
- **Direct evidence (absent):** there is no per-node loss, no airtime, no position data to
  show that loss is *concentrated* at ≤ 1-hop nodes rather than spread across inner-field
  relays, and no way to confirm the channel near the gateway is actually near 100 % busy.

**Verdict on the 1-hop ring:** *plausible and consistent with every observation, but not
demonstrated.* The data supports "congestion at/around the aggregation point"; it does not
localise it to the 1-hop ring specifically, nor identify the loss mechanism.

---

## 5. Node-count effect

Pooled over traffic × mobility (99 runs/cell). `UnreachableSensors = 0` for all rows at
N ≥ 50.

| Nodes | Offered (kbps, medium) | OLSR PDR / deliv-frac | Static PDR / deliv-frac | AODV PDR / deliv-frac | OLSR delay | Static delay |
|---|---|---|---|---|---|---|
| 10 | 80 | 69.5 % / 72.5 % | 46.7 % / 49.7 % | 76.7 % / 81.7 % | 0.041 s | 0.032 s |
| 20 | 160 | 57.0 % / 60.0 % | 32.1 % / 34.4 % | 61.8 % / 65.1 % | 0.067 s | 0.053 s |
| 30 | 240 | 50.2 % / 53.8 % | 29.8 % / 32.5 % | 47.2 % / 46.3 % | 0.101 s | 0.074 s |
| 50 | 400 | 44.9 % / 46.1 % | 25.4 % / 28.0 % | 23.5 % / 20.9 % | 0.179 s | 0.105 s |
| 75 | 600 | 37.3 % / 34.5 % | 20.2 % / 21.9 % | 9.8 % / 8.4 % | 0.283 s | 0.130 s |
| 100 | 800 | 29.8 % / 24.8 % | 17.2 % / 18.4 % | 4.0 % / 3.3 % | 0.369 s | 0.160 s |

- Every protocol's **delivered fraction falls monotonically** as node count (and thus
  offered load, at fixed per-sensor rate) rises.
- **Delivered throughput** rises then flattens/declines: OLSR medium 55.7 → 273.1 kbps
  (flattening toward 100 nodes); Static medium 39.1 → 170.9 kbps (decelerating); AODV
  medium peaks at 30 nodes (129.6) then collapses to 31.0 at 100.
- Delay roughly quadruples (OLSR ×9, Static ×5) from 10 to 100 nodes — accumulating
  queueing.
- This is the profile of a **fixed-capacity aggregation channel** being offered ever more
  load, not of paths getting worse (mean hop count barely moves: Static 1.45 → 1.59).

## 6. Traffic-load effect

Pooled over node × mobility (198 runs/cell). Per-sensor rate: low 4 / medium 8 / high 16
kbps.

| Protocol | Traffic | Offered (kbps, pooled) | PDR | Delivered fraction | Max Link Util (proxy) | Delay |
|---|---|---|---|---|---|---|
| OLSR | low / medium / high | 190 / 380 / 760 | 52.5 % / 47.7 % / 44.2 % | 49.4 % / 42.9 % / 33.2 % | 0.019 / 0.031 / 0.046 | 0.173 / 0.165 / 0.182 s |
| Static | low / medium / high | 190 / 380 / 760 | 26.4 % / 29.5 % / 29.8 % | 21.4 % / 25.9 % / 24.9 % | 0.020 / 0.047 / 0.078 | 0.077 / 0.093 / 0.107 s |
| AODV | low / medium / high | 190 / 380 / 760 | 39.9 % / 38.2 % / 33.4 % | 25.2 % / 21.5 % / 16.8 % | 0.014 / 0.023 / 0.036 | 0.196 / 0.212 / 0.244 s |

- **OLSR and AODV:** higher traffic → lower delivered fraction (OLSR 49 → 33 %, AODV 25 →
  17 %). At 75–100 nodes the high-traffic case is where OLSR throughput actually *declines*
  (F2). This is congestion.
- **Static:** delivered fraction and PDR are roughly flat with traffic (a mild point
  *against* a pure load-saturation story for Static — caveat A3). Its Max Link Util proxy
  does climb with traffic (0.020 → 0.078), consistent with more offered load on the same
  links, but delivery does not fall in step.
- Higher traffic amplifies the node-count degradation for OLSR specifically (its 50→100
  delivered-fraction drop is −14 % at low traffic, −65 % at high) — the two stresses
  compound, as expected for a shared-capacity limit.

## 7. Implications for V4

- The V4 Closeout (Decision B) is **consistent with and explained by** this analysis. V4's
  route metric optimises *which multi-hop path* traffic takes. This analysis indicates that
  quantity has little leverage on delivery in this scenario — hence V4's activated
  configurations changed routes substantially and moved no metric credibly.
- V4's own strongest evidence for a non-path-selection bottleneck: its `x0_R = 0.80,
  x0_L = 0.50` config re-routed every seed (+27.9 % hop count) and PDR did not respond
  (F5). V4 thus provided a *within-mechanism* demonstration of route-insensitivity, which
  this baseline analysis independently corroborates across AODV/OLSR/Static (F6).
- **Implication:** further work on the *routing metric* (measured-congestion input,
  min-max objective, reactive recomputation) is likely to be low-yield **unless** it can
  be shown that some routing degree of freedom (e.g. *spreading* the 1-hop aggregation load
  across more gateway neighbours, or admission/backpressure) actually has headroom. The
  additive per-edge cost family that V4 belongs to does not.

## 8. Remaining uncertainties

1. **Where does the loss occur?** Aggregate `PacketLoss = Sent − Received` does not
   localise loss. Sink-side MAC contention vs inner-field relay queue overflow vs collision
   losses are not separated.
2. **Is the channel near the gateway actually saturated?** The throughput plateau
   (F2–F4) strongly implies it, but no airtime / channel-busy measurement exists; the LU
   proxy cannot answer this (A2).
3. **Why is Static traffic-insensitive?** (A3) — loss floor already reached at low
   traffic, or a load-independent staleness/placement effect. Unresolved.
4. **Would spreading the 1-hop aggregation load help?** i.e. is there a routing degree of
   freedom (distribute relayed traffic across *more* distinct gateway-neighbour links) that
   the shortest-path family — including V4 — never exercises? Not testable from the data.
5. **Node-density confound.** `areaSize` (250 m) and `txRange` (90 m) are fixed across all
   node counts, so higher N also means higher density; "node count", "offered load", and
   "density" are not separable in this dataset.
6. **PHY rate is fixed at DSSS 1 Mbps.** Whether the ceiling is specific to this PHY (vs a
   higher-rate 802.11) is untested.

## 9. Decision

### **H1 PARTIALLY SUPPORTED.**

- **Supported (strongly):** the degradation at ≥ 50 nodes and under higher traffic is
  driven by **contention / saturation**, **not** by reachability failure
  (`UnreachableSensors = 0` throughout) and **not** by route-selection quality (large
  route-tree changes and three different routing approaches all leave PDR at the same
  ceiling). The throughput peak-then-decline (F2), the collapsing delivered fraction (F3),
  the ~43–47 %-of-nominal ceiling (F4), and monotonically rising delay/jitter (F7) are the
  standard signatures of a fixed-capacity aggregation medium being over-offered.
- **Not established:** that the limiting region is **specifically the sink's 1-hop ring**,
  or that the mechanism is **specifically MAC contention** (vs distributed relay queue
  overflow). These are plausible structural inferences (shallow central-gateway topology →
  mandatory aggregation funnel; F9) fully consistent with the data, but the existing
  metrics contain no node positions, per-node/per-link statistics, airtime counters, or
  queue-drop counts to confirm them.

The `INCONCLUSIVE` label is not appropriate — the core of H1 (congestion, not
reachability, not routing) is well supported. The `SUPPORTED` label overstates what the
data can localise. `PARTIALLY SUPPORTED` is the defensible reading.

## 10. Recommended next experiment (design only — DO NOT run)

**Instrumented bottleneck probe** — a **new** simulator file
(`scratch/iot-network-bottleneck-probe.cc`; the existing `iot-network-v3-ext.cc` is never
edited) that re-runs a **small, matched subset** of the existing conditions with per-node
instrumentation, to convert §9's "partially supported" into a definite answer.

- **Matrix:** OLSR + Static (the two clean routers) × nodes {30, 50, 75, 100} × traffic
  {medium, high} × mobility static × seeds 20–30 → **2 × 4 × 2 × 11 = 176 runs**. Matched to
  the V3 Official parameters (300 s, 250 m, 90 m range, 1 Mbps PHY, 512 B, appStart 30 s).
- **Added per-run outputs (CSV, alongside the existing metrics):**
  1. **Node positions** (so hop-distance-to-gateway can be computed for every node
     post-hoc).
  2. **Per-node MAC channel-busy fraction** (airtime), from `WifiPhy` state traces.
  3. **Per-node MAC-queue peak occupancy and drop count**, and **per-node PhyRxDrop /
     PhyTxDrop** counts.
  4. **Per-node received + forwarded byte counts** for gateway-bound traffic.
- **Pre-registered analysis / decision gate:**
  - Compute loss, airtime, and queue drops **binned by hop-distance-to-gateway** (0, 1,
    2, 3+). Is loss (and airtime) concentrated at distance ≤ 1?
  - Is airtime at the gateway and its 1-hop neighbours ≳ 70–80 % (channel effectively
    saturated)?
  - Is loss dominated by **MAC/PHY drops** (contention/collision) or **queue drops**
    (buffering)?
  - **If loss + airtime concentrate at ≤ 1 hop and airtime is near-saturated → H1
    SUPPORTED (sink MAC contention);** the routing line is effectively closed and
    **non-routing interventions** (multi-gateway / gateway placement, per-source
    rate/admission control near the sink, higher PHY rate, directional/PtP sink uplinks)
    become the research direction.
  - **If loss is distributed across relays / dominated by queue drops → H1 SUPPORTED
    (distributed relay congestion);** investigate a **min-max / backpressure** routing
    objective (RQ-B) before non-routing options.
  - **If loss does not concentrate and airtime is far from saturation → H1 NOT
    SUPPORTED;** re-examine the routing objective and the possibility of collision /
    hidden-terminal effects the aggregate metrics masked.

**This experiment is not run here and requires explicit approval.**

---

## Decision-gate outcome (per the task's mapping)

Because H1 is **partially supported** — with the "congestion, not path selection" core
supported and the "sink-side / 1-hop ring / MAC contention" specifics not measurable from
existing data:

- **Routing is likely the wrong lever** for improving delivery in this scenario (supported
  half of H1), so non-routing interventions should be on the table — **but** the
  location/mechanism must be pinned first.
- **The single missing measurement** is per-node loss / airtime / queue-drop data tagged by
  hop-distance-to-gateway (and node positions to compute it). The §10 instrumented probe is
  the minimum experiment that provides it.

**Recommendation: do the §10 instrumented probe next (on approval); do not pursue a new
routing metric or a non-routing intervention until it has localised the loss.**

**STOP.** Analysis only — nothing implemented or run.
