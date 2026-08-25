# Sigmoid-Based Routing Metric

Inspired by (not a reproduction of) Thaenchaikun, Kanjanasit & Chantara, "Enhancement of Network
Performance Using Sigmoid-Based Metrics on a Routing Protocol", ECTI-CON 2025,
DOI 10.1109/ECTI-CON64996.2025.11100445. **That paper has not been read** by whoever wrote this
code — there was no way to fetch it in this environment. Everything below is independently derived
from the general idea of a sigmoid-transformed composite routing cost, not a reproduction of that
paper's specific method, and should not be cited as if it reproduces that paper's results.

## Integration mechanism — why a 4th static mode, not a modified AODV/OLSR

ns-3's AODV and OLSR route selection is implemented entirely inside `src/aodv/` and `src/olsr/`
with no pluggable cost-metric hook. Modifying that core code to inject a custom metric was ruled
out as both a violation of "do not modify ns-3 core source" and a real risk to the two protocols'
already-validated behavior.

**What was built instead:** "Sigmoid" is a fourth routing mode with the same architecture as
"Static" — a graph computed offline, in `iot-network-v3.cc`, from node positions, with the result
installed as fixed `Ipv4StaticRouting` host routes. The only difference from "Static" is that edges
are weighted by the sigmoid composite cost below and the shortest-**cost** path is found with
Dijkstra instead of unweighted BFS. This means the sigmoid formula genuinely determines which path
a sensor's traffic takes — it is not a value computed only for a dashboard chart.

## The honest limitation this creates

Because routes are computed once, before any traffic starts (same timing as Static), the metric's
inputs cannot be true live-measured delay/jitter/loss — nothing has been transmitted yet at
route-computation time. The inputs used are **geometry-derived proxies**, not runtime
measurements. This is materially different from, and weaker than, a live-adaptive routing metric
that reacts to real observed conditions. What is implemented here is best described as
**offline sigmoid-weighted route selection**, not reactive adaptive routing. A genuinely adaptive
version would need per-hop, in-protocol cost updates — the kind of change to AODV/OLSR core that
was explicitly ruled out above.

## Inputs — two, not four, and why

The reference formula you specified uses four inputs (delay, jitter, loss, load). Implementing
four *independent* pre-simulation proxies is not honestly possible here: with no traffic yet sent,
the only information available per candidate edge is its geometry (distance, and the node degree
of its endpoints). Deriving four "different" numbers from that same geometric information would
not add genuine independent information — it would just be the same underlying signal, relabeled
four times to match the reference formula's variable count. That would misrepresent the metric's
actual information content.

Instead, two genuinely distinct, independently-justified proxies are used:

| Proxy | Formula | Justification |
|---|---|---|
| **Link quality** | `distance / txRange`, in [0,1] | Distance-to-range-edge is the standard proxy for expected link quality in a log-distance path-loss model (this project's own PHY model); higher value = weaker expected signal, plausibly correlated with higher delay/jitter/loss risk from the same underlying physical cause. |
| **Load** | `avg(degree(i), degree(j)) / maxDegree`, in [0,1] | A topological property, independent of the link-quality proxy; a node with many neighbors within range is a more likely contention/congestion point if chosen as a relay. |

## Normalization, weights, output range

Both proxies are already normalized to [0,1] by construction (a ratio of distances / a ratio of
degrees), so no separate normalization step is needed. Each is passed through the sigmoid
independently, then combined:

```
S(x)   = 1 / (1 + exp(-k * (x - x0)))
cost   = w_linkQuality * S(linkQuality) + w_load * S(load)
```

Default weights: `w_linkQuality = w_load = 0.5` (configurable via `--sigmoidWLinkQuality` /
`--sigmoidWLoad`, expected to sum to 1). Since each `S(x)` is in (0,1) and the weights sum to 1,
`cost` is also in (0,1). **Lower cost is better** — both proxies represent "badness" (higher
distance ratio / higher relative load = worse), and Dijkstra minimizes total path cost, so it
naturally prefers paths avoiding high-distance-ratio, high-degree relay hops.

## k and x0

x0 defaults to 0.5 — the midpoint of the [0,1] input range both proxies already live in, so the
inflection point sits centered on the data rather than at an arbitrary offset.

k = 0.1, 0.2, 0.3 as specified. **A real, computed observation worth stating plainly rather than
glossing over:** at this input scale (x confined to [0,1]) and x0 = 0.5, these k values keep the
sigmoid almost entirely in its near-linear regime, not its characteristic steep S-curve:

| k | S(0) | S(0.5) | S(1) | Total range |
|---|---|---|---|---|
| 0.1 | 0.4875 | 0.5000 | 0.5125 | 0.025 |
| 0.2 | 0.4750 | 0.5000 | 0.5250 | 0.050 |
| 0.3 | 0.4626 | 0.5000 | 0.5374 | 0.075 |
| *(for comparison)* 10 | 0.0067 | 0.5000 | 0.9933 | 0.987 |

At k = 0.1-0.3, S(x) barely moves off 0.5 across the *entire* possible input range — the
transformed cost is only weakly sensitive to the underlying proxy value, so route selection in
this k range will look close to a flat/uniform cost (paths will differ mainly through the load
term breaking ties, since both proxies get compressed toward ~0.5 similarly). This is not a bug —
it is exactly what the requested k values produce given inputs normalized to [0,1] — but it means
the experiment as specified is unlikely to show the sigmoid's most characteristic "smooth-but-
decisive" transition behavior. Reaching that regime at this input scale would need k roughly in
the 5-20 range (see the comparison row above). **This experiment will run exactly the requested
k = 0.1/0.2/0.3 sweep as specified** — but if the research question is specifically about the
sigmoid's characteristic steep-transition behavior, a wider k sweep including larger values would
be needed to actually observe it; that's a design choice for you to make, not something decided
here.

## Route-selection mechanism, concretely

1. Build the same disk-connectivity adjacency graph as "Static" (edge if distance <= `--txRange`).
2. Compute each node's degree and the graph's max degree.
3. For every edge, compute `cost` as above.
4. Run Dijkstra from the Gateway over these costs (not BFS over hop count).
5. Install the resulting minimum-cost path as a static host route per sensor, exactly the same
   mechanism "Static" already uses (`Ipv4StaticRouting::AddHostRouteTo`).

## What the validation run actually showed (one seed, one traffic condition — not a result)

A single validation run (seed 1, medium traffic, k=0.2, x0=0.5, equal weights) produced a
non-degenerate CSV row with PDR/throughput/delay/jitter/hop-count all in plausible ranges, and no
crash or unreachable-sensor warning. **This is a confirmation that the code runs correctly, not a
finding about whether Sigmoid performs better or worse than AODV/OLSR/Static.** One seed is not a
statistically meaningful comparison — see V2.7.1's own validation report for exactly this point
made about single-seed topology draws. No performance claim should be made until the full,
multi-seed experiment matrix has run.
