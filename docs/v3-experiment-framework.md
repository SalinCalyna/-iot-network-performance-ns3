# V3 Expanded Experiment Framework (topology-preserving track)

## Why this file exists, and how it relates to the other V3 documents

As of 2026-08 the advisor gave a specific instruction for V3: **keep using
V2's own topology-generation method** (uniform-random sensor placement in a
square field, one gateway at the centre -- see `scratch/iot-network.cc`),
and first widen the experiment conditions and metric set. Adaptive/Sigmoid
routing is a *later* phase, not this one.

### Correction (2026-08-26): there are three prior/parallel tracks, not two

An earlier version of this document said there were two tracks ("Track A"
and "Track B") and described "Track A" as a fixed 15-node clustered
topology with a working sigmoid mode, attributing it to
`scratch/iot-network-v3.cc`. **That attribution was wrong**, found and
corrected while inspecting the actual current file contents (not just the
docs) during this pass. The real picture, reading each `.cc` file's own
header comment directly:

| # | Name used in code | Simulator | Topology | Sigmoid? | Output |
|---|---|---|---|---|---|
| 1 | V2 / "V2.7" (baseline, unchanged) | `scratch/iot-network.cc` | uniform-random, 10/20/30/50 nodes | no | `results/*.csv` |
| 2 | "V2.8 pilot" (informal, pre-dates an official V3 assignment) | `scratch/iot-network-v28-sigmoid-pilot.cc` | fixed 15-node, 3-cluster Gateway/Server/sensor | yes, geometry-proxy Dijkstra | `results/v28-sigmoid-pilot/*.csv` |
| 3 | "V3" (a *previous* official advisor assignment, since superseded by the direction this document implements) | `scratch/iot-network-v3.cc` | 26-node Barabasi-Albert scale-free graph, wired point-to-point links (10 core routers + 16 hosts) | yes, reproducing a specific paper's "Sigmoid-Enhanced OSPF" | `results/v3/*.csv` (topology_nodes.csv, performance_summary.csv, etc.) |
| 4 | **This document's track** ("V3 Phase 1" in the advisor's and student's current usage) | `scratch/iot-network-v3-ext.cc` | **V2's own uniform-random method**, 10-100 nodes | **not implemented** (refuses to run) | `results/v3-ext/*.csv` |

`docs/experiment-design.md`, `docs/methodology.md`, and
`docs/sigmoid-metric.md` describe track #2 (the file has since been renamed
to `iot-network-v28-sigmoid-pilot.cc`; those docs still say
`iot-network-v3.cc` in places, which is now stale). Track #3 is a
completely separate, later, paper-reproduction study (wired BA topology,
not wireless) that happened to also be called "V3" before the advisor's
latest pivot reassigned that name to the topology-preserving matrix
described here. **Track #3's code, at `scratch/iot-network-v3.cc`, is left
untouched** -- it is real, carefully-provenanced work (see its own header
comment for how the reference paper's parameters were sourced), just
answering a different question than the current instruction.

**A real bug was found and fixed because of this correction:** track #3
already writes to `results/v3/` (its header literally states this "cannot
collide with either" of the other two tracks -- true at the time it was
written, before this track existed). This document's simulator had
independently also defaulted to `results/v3/`, which would have caused two
incompatible CSV schemas to land in the same directory the first time
anyone ran the BA/risk-aware study. Fixed by moving this track's output
(and its runner's default) to **`results/v3-ext/`** instead, matching the
`iot-network-v3-ext.cc` filename. No actual data collision had occurred
yet (track #3 had not been run), so this was a latent-bug fix, not a data
recovery.

If the advisor's direction changes again, tracks #2 and #3 are still there,
untouched and still valid -- nothing about them was deleted or degraded to
build this track.

## What this track keeps identical to V2

Line-for-line the same as `scratch/iot-network.cc`:

- Node roles: N sensors (indices `0..N-1`) + 1 gateway (index `N`), gateway
  is also the sink/server.
- Topology generation: gateway at the field centre, sensors placed
  uniform-random in `[0, areaSize] x [0, areaSize]`, drawn from an
  independent `std::mt19937` seeded only by `--seed` -- never touched by
  ns-3's own RNG, so position never depends on `--protocol`.
- PHY/MAC: single shared 802.11b ad-hoc channel, 1 Mbps DSSS, log-distance
  path loss (exponent 3.0).
- Static routing: BFS shortest-hop tree over an assumed disk-connectivity
  graph (`--txRange`), installed as fixed `Ipv4StaticRouting` host routes.
- AODV/OLSR: unmodified ns-3 implementations via `Ipv4ListRoutingHelper`.
- Core metrics: packets sent/received, packet loss, PDR, throughput, delay
  -- same FlowMonitor-based computation as V2.

## What this track adds

### Network size
`--nSensors` supports up to 100.

### Traffic level (`--trafficLevel=low|medium|high`)
Maps to a per-sensor CBR data rate: low=4kbps, medium=8kbps, high=16kbps.
`medium` intentionally equals V2's existing baseline rate so the two
studies share a reference point.

### Mobility (`--mobilityMode=static|low|medium`)
- `static`: identical to V2 -- `ConstantPositionMobilityModel`.
- `low` / `medium`: sensors use `RandomWaypointMobilityModel` at a
  constant configured speed (`--mobilitySpeedLow`, default 1.0 m/s;
  `--mobilitySpeedMedium`, default 5.0 m/s), pausing 2s between waypoints,
  roaming within the same `[0, areaSize]^2` field. **The gateway never
  moves in any mode.**
- All modes start sensors at the *same* t=0 positions for a given `--seed`.
- Mobility is installed before the routing stack in every run, so the same
  `--seed` produces the same mobility trace across AODV/OLSR/Static.

### Routing (`--protocol=aodv|olsr|static`; `sigmoid` refuses to run)
Passing `--protocol=sigmoid` prints an explanatory message and exits with
status 1 -- **no CSV row is written and no result is fabricated.**
`experiments/run_v3_experiments.py` treats a `sigmoid` entry in `--routing`
the same way (skips it with a visible log line).

### Seeds (`--seed`)
Two distinct, deliberately separated seed policies exist for this track --
do not conflate them:

- **Validation / Smoke Test -- Seed 1 (and, for the framework smoke test
  only, Seed 2).** This is what has actually been run so far: the
  six-node-size sweep below and the framework smoke test both use `--seed=1`
  (or 1-2), specifically because a single seed is enough to confirm the
  simulator runs correctly end-to-end and to get a first read on the
  numbers -- it is **not** a statistically meaningful multi-seed result and
  must never be reported as one.
- **Official V3 experiment -- seed values 20 through 30, inclusive (11
  seeds: 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30).** Set by the advisor
  on 2026-08-26, superseding an earlier informal framing of this as "20 vs
  30 seeds" (i.e. a sample-size choice between running seeds 1-20 or
  1-30). The advisor's wording ("Seeds 20-30") is now interpreted literally
  as the inclusive seed-value range, giving a fixed n=11 per condition --
  **not** a choice between two different total-sample-size options. This
  range has **not been run yet** (see Explicitly deferred below).

`experiments/run_v3_experiments.py --seeds` accepts either form, e.g.
`--seeds 1` (validation) or `--seeds 20-30` (official); see that script's
module docstring for full invocation examples. The `--seeds` flag's own
CLI default remains `1`, deliberately -- so invoking the runner without an
explicit `--seeds` argument stays cheap (a single validation run) rather
than silently launching the 11-seed official range.

### Metrics -- verified, one by one (2026-08-26 inspection pass)

Every metric below was re-traced to its exact source line in
`scratch/iot-network-v3-ext.cc` and cross-checked against real simulation
output (not just read as a comment) during this pass, to confirm none of
them are placeholders, hardcoded, or randomly generated.

| Metric | CSV column | Traced to | Verified against real output? |
|---|---|---|---|
| Throughput | `ThroughputKbps` | FlowMonitor `rxBytes` / active-traffic-window | Yes -- nonzero in all 19 rows currently on disk |
| End-to-end delay | `AverageDelaySec` | FlowMonitor `delaySum / rxPackets` | Yes |
| Jitter | `AverageJitterSec` | FlowMonitor `jitterSum / rxPackets` | Yes -- nonzero, plausible magnitudes (ms range) |
| Packet loss | `PacketLoss` | `PacketsSent - PacketsReceived` | Yes -- re-derived independently in the CSV sanity pass below and matched exactly in every row |
| PDR | `PDR` | `100 * rxPackets / txPackets` | Yes -- confirmed in [0,100] in every row |
| Routing overhead | `RoutingOverheadPackets` | FlowMonitor flows on UDP port 654 (AODV) / 698 (OLSR) | Yes, but **known incomplete** -- see Known limitations |
| Hop count | `AverageHopCount` / `HopCountMethod` | exact BFS depth (Static) or `1 + timesForwarded/rxPackets` (AODV/OLSR) | Yes -- method column always present, static's hop counts sanity-checked against the same BFS tree used to install its routes |
| Path changes | `PathChanges` | periodic `Ipv4RoutingProtocol::RouteOutput` next-hop sampling every 5s | Yes -- **Static confirmed exactly 0 in every single run on disk** (correct by construction); AODV/OLSR show nonzero values that increase under mobility |
| Avg/Max link utilization | `AverageLinkUtilization` / `MaximumLinkUtilization` | WifiPhy `PhyTxBegin` trace, bytes per unicast (src,dst) MAC pair / (nominal PHY rate x duration) | Yes, but **explicitly a proxy, not a channel-busy measurement** -- see Known limitations |

No metric is computed from `rand()`/a random-variable draw independent of
the simulation state -- confirmed by grep (`rand(`, `srand(`, `TODO`,
`FIXME`, `placeholder`, `hardcod` all return zero matches in the source
file other than the intentionally-seeded, documented position/mobility
RNGs).

### CSV schema (`results/v3-ext/<protocol>_<nSensors>_<trafficLevel>_<mobilityMode>.csv`)

```
Timestamp,Version,RoutingProtocol,NumberOfNodes,TrafficLevel,DataRate,
MobilityMode,MobilitySpeed,Seed,Duration,PacketsSent,PacketsReceived,
PacketLoss,PDR,ThroughputKbps,AverageDelaySec,AverageJitterSec,
RoutingOverheadPackets,AverageHopCount,HopCountMethod,PathChanges,
AverageLinkUtilization,MaximumLinkUtilization,UnreachableSensors
```

One row is appended per run. **Important:** a given filename can therefore
accumulate runs made at *different* durations/appStart values over time
(e.g. an early short smoke test and a later real validation run both land
in the same file) -- this actually happened (see Known limitations) and is
handled by making Duration part of the dashboard's grouping key, not by
assuming a file only ever holds one experimental condition.

## Validation performed (2026-08-26)

**Everything in this section is Validation / Smoke Test data (Seed 1, or
Seed 1-2 for the framework smoke test) -- it is not the Official V3
experiment (Seed 20-30) defined above, and must not be presented as a
statistical result.**

### Framework smoke test (multiple small conditions)
Via `experiments/run_v3_experiments.py`: 10 sensors x {aodv, olsr, static}
x {static, low mobility} x {seed 1, 2}, medium traffic, 40s duration (12
runs); plus one 60s olsr/medium-mobility/high-traffic run; plus
`--protocol=sigmoid` invoked directly and via the runner (confirmed refuses
to run, writes no CSV row, no crash). All succeeded.

### Six-node-size validation sweep (the actual Task 3 request; Validation / Smoke Test, Seed 1 -- not the Official V3 experiment)
10/20/30/50/75/100 nodes, AODV, medium traffic, static mobility, seed 1,
**300s duration** (the real target duration, not a shortened smoke test).
Run via the same runner; wall-clock time was 897.7s (~15 min) for all 6
runs combined, no crashes, no empty files.

| Nodes | Tx | Rx | PDR | Throughput (kbps) | Avg hop count | Path changes |
|---:|---:|---:|---:|---:|---:|---:|
| 10 | 5,270 | 4,857 | 92.16% | 77.71 | 1.61 | 9 |
| 20 | 10,540 | 6,526 | 61.92% | 104.42 | 1.54 | 153 |
| 30 | 15,810 | 8,339 | 52.75% | 133.42 | 1.59 | 425 |
| 50 | 26,350 | 4,814 | 18.27% | 77.02 | 1.45 | 1,889 |
| 75 | 39,525 | 2,622 | 6.63% | 41.95 | 1.39 | 3,138 |
| 100 | 52,700 | 798 | 1.51% | 12.77 | 1.08 | 3,944 |

### Investigation: is the 75/100-node collapse a connectivity problem?

To answer Task 4's question directly, **Static routing was run at the same
75/100 node counts** (Static explicitly logs "N sensor(s) have no path to
the gateway" whenever true geometric BFS connectivity fails):

| Nodes | Static: unreachable sensors logged | Static PDR |
|---:|---:|---:|
| 50 | 0 (no "Note:" line printed) | 39.17% |
| 75 | 0 | 22.83% |
| 100 | 0 | 24.79% |

**Finding: it is not a connectivity/coverage problem.** Every sensor has a
geometric BFS path to the gateway at every size tested -- Static's own
"unreachable" counter is 0 throughout. Static's PDR still declines with
node count (39%->23%->25%) purely from **more nodes contending for the
same single 1 Mbps shared channel in the same fixed 250m field** (more
simultaneous transmissions -> more collisions), and AODV declines far more
sharply on top of that (18%->6.6%->1.5%) because of RREQ broadcast-storm
overhead compounding the same channel contention at high density. This is
a real, evidenced network-congestion phenomenon, not a bug in the
simulator or a topology-generation defect -- but it does mean `--areaSize`
and `--txRange` being fixed at V2's original 250m/90m values makes the
75/100-node conditions dominated by congestion rather than by whatever the
experiment is actually trying to compare. See Open questions below.

### CSV data-quality sanity pass (Task 14 checklist)
Ran automated checks across all 19 rows on disk in `results/v3-ext/`:
no empty files, no NaN values, PDR in [0,100] in every row, received <=
sent in every row, `PacketLoss == Sent - Received` in every row, MLU
always >= average link utilization and always <= 1.0, every row has
nonzero throughput. **One real issue found and fixed**, not a false
report of success:

- `aodv_10_medium_static.csv` contained 4 rows spanning 3 different
  `Duration` values (30s, 40s, 300s) for the same (protocol, nodes,
  traffic, mobility) combination, because early smoke-test runs and the
  real validation run both appended to the same file. Grouping by
  protocol/nodes/traffic/mobility alone (the dashboard's original
  implementation) would have silently averaged a 40s smoke-test row
  together with the real 300s validation row. **Fixed** by adding
  `Duration` to the dashboard's aggregation grouping key and exposing a
  Duration filter in the UI (see Dashboard section) -- confirmed via a
  live API call that the three durations now aggregate as three separate
  rows instead of one blended mean.

## Dashboard integration

Extended the existing `dashboard/app.py` / `dashboard/static/dashboard.js`
/ `dashboard/templates/index.html` (did not create a separate dashboard).
Backend endpoints (`/api/v3ext/meta`, `/api/v3ext/rows`,
`/api/v3ext/summary`) and the initial "Expanded Matrix (V3 Phase 1)" nav
section were built in an earlier pass on 2026-08-26; this second pass
(same day) added the pieces below on top of that, without rewriting any
of it.

### Backend (unchanged this pass)
- Read-only endpoints, same "read `*.csv` fresh on every request, never
  write, never cache" pattern as every other endpoint in `app.py`:
  `/api/v3ext/meta`, `/api/v3ext/rows` (per-run raw rows), `/api/v3ext/summary`
  (grouped mean/std/95% CI). 95% CI uses a small built-in Student's-t table
  (no scipy dependency, consistent with the rest of this project).
- `/api/v3ext/summary` groups by protocol/nodes/traffic/mobility/**duration**
  -- duration is part of the key, not just a display column, specifically
  because `aodv_10_medium_static.csv` has 30s/40s smoke-test rows mixed
  with the real 300s validation row; grouping without duration would
  silently blend them into one misleading mean.

### Frontend (this pass)
- New nav section **"Expanded Matrix (V3 Phase 1)"**, placed after
  Validity and before the (pre-existing, still-unbuilt) "BA Topology &
  Risk-Aware Routing (V3)" nav link -- that link still points at a section
  that doesn't exist (`id="v3-ba-routing"`); left as-is, out of scope for
  this track.
- Filters: node count, traffic level, mobility mode, routing protocol
  (default "all", to enable cross-protocol comparison), duration. The
  routing-protocol filter carries an inline hint marking Sigmoid as "not
  yet implemented / pending Phase 3" -- Sigmoid never appears as a
  selectable option (no rows exist for it), but its absence is now
  explained rather than silent.
- **Summary KPI cards** (Throughput, PDR, Delay, Jitter, Packet Loss,
  MLU) above the trend chart, averaged across whatever rows the current
  filters match; narrowing filters to one exact condition shows that
  condition's own values. Shows "No data" per card, never a fabricated 0,
  when no rows match.
- **Node-size trend chart** (pre-existing, relabeled): the metric-tab line
  chart plotted against network size (10/20/30/50/75/100) -- covers PDR,
  throughput, delay, jitter, packet loss, routing overhead, hop count,
  path changes, avg/max link utilization, one series per protocol, 95% CI
  error bars shown only for unambiguous n>=2 cells.
- **Aggregated results table** (pre-existing): mean/n/95% CI per
  (protocol, nodes, traffic, mobility, duration) cell, sortable.
- **New: Comparison Mode panel** -- a bar chart comparing AODV vs. OLSR vs.
  Static under one locked (node count, traffic, mobility, duration)
  combination, selected via its own compact filter row (defaults to
  50 nodes / medium / static / 300s where available). A protocol with no
  run recorded for the exact combination is omitted from the chart and
  named in a "No data available for this configuration: <protocol>" note
  underneath, instead of a fabricated zero-height bar.
- **New: 75/100-node warning callout**, always visible at the top of the
  section (not conditional on the current filter selection), with the
  advisor-review wording from the Task 8 instruction verbatim. Explicitly
  states these are real, unmodified results pending methodological review,
  not invalid ones.
- **New: Raw Data table** for `results/v3-ext/*.csv`, wired to the
  previously-unused `/api/v3ext/rows` endpoint -- one row per actual run
  on disk (19 rows currently), sortable by every column including Seed and
  Duration, so the 30s/40s debug rows in `aodv_10_medium_static.csv` are
  visible and distinguishable (via the Duration/Seed columns) rather than
  silently blended with the real Seed 1/Duration 300s validation row. The
  aggregated table and Comparison Mode never average across durations
  (see backend note above); this raw table is the one place all rows,
  debug included, are shown together, deliberately, with enough columns to
  tell them apart.

### Verification this pass
- `python3 -m py_compile dashboard/app.py` -- passes.
- `node --check dashboard/static/dashboard.js` -- passes (no Node.js
  project dependency implied; used only as a syntax checker).
- HTML tag-balance check (`<section>`/`<div>` open/close counts) on
  `templates/index.html` -- balanced.
- Started the dashboard locally (`python3 dashboard/app.py`, using a venv
  with `pandas`/`flask`/`python-dotenv` installed for this test since the
  system Python didn't have them) and exercised it with `curl` against a
  non-default port (macOS's AirPlay Receiver was already bound to the
  default port 5000 on this machine -- a local machine quirk, not an app
  bug; the shipped `app.py` is unchanged and still binds 5000 by default).
  Confirmed: `/api/v3ext/meta` lists all 6 node sizes (10/20/30/50/75/100);
  `/api/v3ext/summary` for AODV/medium/static/duration=300 returns exactly
  the 6 validated rows with correct values; `/api/v3ext/rows?nodes=10&duration=300`
  returns only the 1 real validation row, not the 3 debug rows also on
  disk for that file; a Comparison Mode query at 75 nodes correctly
  returns only `aodv` (confirming OLSR/Static would show as "no data" at
  that size, since they were never run there); the served HTML contains
  all new element IDs.
- **Not visually confirmed pixel-by-pixel in an actual browser** --
  in-session browser automation was declined for this session. The checks
  above (API responses, HTML structure, JS syntax) give reasonable
  confidence the page functions, but a human should still open
  `http://127.0.0.1:5000` once and eyeball the new KPI cards, warning
  banner, comparison chart, and raw table before using this for a
  presentation.

## Explicitly deferred (not done in this pass)

- **The full experiment matrix.** 6 node sizes x 3 traffic levels x 3
  mobility modes x 3 implemented protocols x 11 seeds (the Official V3
  seed range, seed values 20-30 inclusive -- see Seeds above) = **1,782
  runs** at 300-600s simulated time each. (Superseded estimate: this was
  previously written as "3,240-4,860 runs" under an earlier, now-corrected
  reading of "20-30 seeds" as a sample-size choice between 20 and 30 seeds
  starting at seed 1, rather than the fixed 11-value inclusive range the
  advisor actually specified.) Only prepared/estimated, not run (still not
  to be run yet). Based on the 6-run timing above (897.7s for 10-100 nodes
  combined, dominated by the larger sizes), a very rough linear
  extrapolation puts the full matrix in the range of many hours to low
  tens of hours of wall-clock time -- this needs a proper per-size timing
  measurement before committing to a schedule, and should wait for the
  Open Questions below to be resolved first (running the full matrix at
  values that turn out to need revision would waste most of that time).
- **Statistical aggregation across seeds** -- now implemented in the
  dashboard (mean/std/95% CI), but with only 1-2 seeds per condition on
  disk, these numbers are not yet meaningful; they will become so once
  real multi-seed data exists.
- **Adaptive / Sigmoid routing metric on this topology.** Explicitly the
  next phase, not this one, per Task 11.
- **Routing-overhead measurement fix** (MAC/protocol-level trace instead
  of FlowMonitor's IP-layer one, which misses broadcast RREQ/HELLO/TC) --
  flagged, not fixed, per Task 2's "otherwise keep the limitation
  documented" instruction.
- `git commit`/`push` -- not done in this pass.

## Known limitations

1. **Routing overhead undercounts AODV/OLSR control traffic.**
   FlowMonitor's `SendOutgoing` trace skips non-unicast destinations, and
   AODV's RREQ / OLSR's HELLO and TC are broadcast, so the true control
   overhead is higher than what's recorded (Static's true zero *is*
   correctly captured, since it has no runtime control traffic by
   construction). Fixing this needs a MAC- or protocol-level transmission
   trace instead of FlowMonitor's IP-layer one.
2. **`--areaSize`/`--txRange` fixed at V2's original 250m/90m regardless of
   node count.** Confirmed (see Investigation above) to make 75/100-node
   PDR dominated by channel congestion rather than by whatever routing
   comparison is intended. Needs an advisor decision before the full
   matrix runs at those sizes (see Open questions).
3. **MLU is an offered-load proxy, not a measured channel-busy fraction.**
   There is no dedicated "link" with reserved capacity on a shared
   random-access wireless channel the way there is on a wired link; this
   metric approximates it per unicast neighbour-pair from MAC-frame byte
   counts divided by nominal PHY bitrate x duration.
4. **95% CI in the dashboard uses a small built-in Student's-t table**
   (df 1-30, i.e. it supports sample sizes n=2 through n=31, falling back
   to the normal approximation beyond that), not scipy, since scipy is not
   a dependency anywhere else in this project. This df range is a
   statistics-table sizing choice, unrelated to and coincidentally
   overlapping with the Official V3 experiment's seed *values* (20-30,
   n=11) -- n=11 falls well inside the table's supported range regardless.
5. **A pre-existing dashboard nav link ("BA Topology & Risk-Aware Routing
   (V3)") points at a section that doesn't exist.** Found during this
   pass's dashboard inspection; not fixed, since it belongs to track #3,
   out of this pass's scope.

## Open questions for the advisor / before running the full matrix

1. Should `--areaSize` and/or `--txRange` scale with `--nSensors` (e.g. to
   keep average node degree, or offered load per unit area, roughly
   constant), or is a fixed 250m field deliberately part of "keep the same
   topology method," accepting that larger networks will be dominated by
   channel congestion rather than by routing-protocol differences? This is
   now backed by hard evidence (the Static-routing connectivity check
   above), not speculation -- 75/100-node results as currently configured
   mostly measure "how bad does congestion get," not "which protocol
   handles the same conditions better."
2. ~~How many seeds (20 vs 30)~~ **Resolved 2026-08-26: seed values 20-30
   inclusive (11 seeds) -- see Seeds above.** Still open: what duration
   (300s vs 600s) the real matrix should use.
3. Track #3 (`scratch/iot-network-v3.cc`, Barabasi-Albert/risk-aware
   routing) and track #2 (the V2.8 sigmoid pilot) -- keep both
   indefinitely as reference, or archive/remove once this track supersedes
   them for the thesis write-up?
