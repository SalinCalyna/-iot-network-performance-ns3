# V1–V4 Methodology & Results — Advisor's Framing, Cross-Walked to Real Tracks

This document answers Komsan Kanjanasit's 2026-10 request directly: a methodology-and-results
report for "V1–V4," using his own labels, before any further BA/risky-node work proceeds. No file
in this repository is literally named `iot-network-v1.cc` — the mapping below is this report's
own convention, checked against each simulator's own header comment and git metadata, not assumed
from older docs. Every item below carries one of four labels:

- **Implemented** — the simulator code exists and is complete.
- **Experiment completed** — runs were actually executed and the output data exists on disk.
- **Proposed** — a design, not yet implemented or run.
- **Not yet verified** — implemented, but no execution evidence exists; results must not be
  assumed or invented.

## Track map

| Advisor's label | Actual track | Simulator file | Status |
|---|---|---|---|
| V1 | "V2"/"V2.7" baseline | `scratch/iot-network.cc` | Implemented, Experiment completed (60 runs) |
| V2 | "V2.8"-style sigmoid pilot | `scratch/iot-network-v3.cc` on **this branch** (`main`) | Implemented, Experiment completed (4-run smoke test only) |
| V3 | BA topology / risk-aware routing (paper reproduction) | `scratch/iot-network-v3.cc`, a **different, same-named program** that exists only locally/uncommitted (see note below) | Implemented (uncommitted), **Not yet verified** — zero runs |
| V3 Phase 1 | Official extended baseline | `scratch/iot-network-v3-ext.cc` | Implemented, Experiment completed (1,782 official runs) |
| V4 | Sigmoid-adaptive routing | `scratch/iot-network-v3-ext.cc`, `--protocol=v4` | Implemented, Experiment completed (957 runs), **closed** |

**Branch/filename note:** `iot-network-v3.cc` means two different programs depending on where you
look. On this repository's `main` branch it is the legacy 15-node sigmoid pilot (what the
researcher's local working environment calls "V2.8"). A separate 26-node Barabasi-Albert
risk-aware program of the same name was written later for the advisor's BA/risky-node request —
it is **not committed to this repository on any branch**; it exists only as a local, uncommitted
file in the researcher's working environment. Do not treat results, descriptions, or data from one
as applying to the other.

## V1 — Baseline

**File:** `scratch/iot-network.cc`. **Status: Implemented, Experiment completed.**

Uniform-random sensor placement, gateway at field centre, 802.11b shared ad-hoc channel (1 Mbps
DSSS, log-distance path loss). AODV, OLSR, and Static (BFS shortest-hop) routing. 10/20/30/50
nodes × 3 protocols × 5 seeds = 60 runs, all complete (`results/*.csv`, `results/statistics.csv`).
PDR falls as node count grows for every protocol (e.g. AODV 70.5%→27.2%, OLSR 49.6%→20.0%, Static
53.5%→23.6% from N=10 to N=50) — the fixed reference point every later track is checked against.

## V2 — Sigmoid pilot

**File (this branch):** `scratch/iot-network-v3.cc` (15-node pilot). **Status: Implemented,
Experiment completed as a smoke test only (n=1 seed) — not a statistical result.**

Fixed 15-node, 3-cluster topology; adds a 4th "Sigmoid" routing mode (offline Dijkstra over two
geometry-derived proxies — link quality and topological load). Explicitly documented as
"inspired by, not a reproduction of" the cited ECTI-CON 2025 paper (never read; fetch blocked).
Only a 4-run validation (one seed, medium traffic, all 4 protocols) was ever executed; the planned
90-run full matrix was never run. Single-seed result: Sigmoid PDR 60.1% vs. AODV 42.6% / OLSR
47.4% / Static 38.5% — **not statistically meaningful with n=1**.

## V3 — BA topology / risk-aware routing

**File:** a 26-node Barabasi-Albert program also named `iot-network-v3.cc`, **not in this
repository** (local/uncommitted only). **Status: Implemented (uncommitted), Not yet verified.**

Reproduces the topology/evaluation methodology of Thaenchaikun & Kanjanasit, "Performance
Analysis of Sigmoid-Enhanced OSPF for Risk-Aware Adaptive Routing in Secure Networks," Network
(MDPI) 2026. 26-node BA scale-free graph (m=2), 10 core + 16 host nodes, wired point-to-point
links. Structural risk is **continuous and degree-based**: `R_i = d_i/max(d_k)`,
`R_ij = max(d_i,d_j)/max(d_k)` — there is **no discrete per-node risk state** in this code today.
Three routing-cost variants (`standard`, `linear`, `sigmoid`) share one Dijkstra implementation,
run once per destination (26 runs), installed offline as fixed routes before traffic starts.
**Zero runs have ever been executed** — the designated output directory does not exist on disk.
This directly explains the advisor's "risky nodes not showing / routing doesn't match before"
feedback: there is no output to show, and the existing risk model has no node-level state to
display.

### Proposed: explicit low-risk / high-risk node state — **Proposed, not implemented**

Neither cited paper defines a discrete per-node risk label; this is a new modeling extension.
Proposed: `RiskState(i) ∈ {low, high}`, settable via a new `--highRiskNodes=<ids>` flag, combined
as `R_i' = max(R_i, 1[RiskState(i)=high])` — a pure superset of today's formula (0 flagged nodes
reproduces current behavior exactly; no new tunable weight is introduced).

### How risk state would affect routing — explicit, not assumed

- `standard` mode: **zero effect, always** (flat per-hop cost; required negative control).
- `linear`/`sigmoid` modes: a flagged node raises the Dijkstra cost of every edge touching it; a
  route reroutes around it **only if** a cheaper alternate path exists. Many of the 16 "host"
  (leaf) nodes have no alternate path at all, so flagging them can do nothing — this is expected,
  not a bug. High-degree "core" nodes are more likely to show an observable reroute.

### Matched experiment design — **Proposed, not run**

Fixed `--baSeed` per matched set; deterministic node selection (top-k by degree, ties by node ID,
so each count's flagged set is a subset of the next). Full matrix per seed: 3 `routingMode` values
× {0,1,2,3} high-risk nodes = 12 runs. `standard` is a required negative control at every count.
Eventual official run (pending pilot approval): seeds 20–30 (11 seeds, matching V3 Phase 1's
convention) — **not proposed to run yet**.

### Pilot — **Proposed, not run**

Step 0 (no simulator): verify the top-3 degree-ranked nodes at the candidate seed actually have a
viable alternate path, before writing any code. Step 1: 1 seed × 1 traffic level × 3 modes × 4
risk-counts = 12 runs, with three explicit pass/fail checks (code wiring works; `standard` shows
zero route changes; `linear`/`sigmoid` shows ≥1 route change). The full 11-seed matrix should not
run until all three checks pass.

### Metrics & logging — **Proposed, not implemented**

New: routes-changed count, risk-exposure rate (fraction of flows still touching a high-risk node),
hop-count inflation (%). None of these are computable from today's schema (routes are installed,
never recorded as sequences). Required additions: `risk_state` column in `node_risk.csv`; new
`routing_table.csv` and `route_changes.csv`; 5 new columns in `performance_summary.csv`. All
additive — nothing in the current schema is renamed or removed.

### Output isolation

Designated directory `results/v3/` does not exist yet, and is already isolated from V3 Phase 1
(`results/v3-ext/`) and V4 (`results/v4-matched/`, `results/v4-sensitivity/`) — no collision risk.

## V3 Phase 1 — Official extended baseline

**File:** `scratch/iot-network-v3-ext.cc`. **Status: Implemented, Experiment completed.**

V1's own topology method (uniform-random, gateway-centred), widened to 10–100 nodes, 3 traffic
levels, 3 mobility modes. Official run: seeds 20–30 (11 seeds), 300 s, 162 configurations = 1,782
runs, dataset-verified (no NaNs, no duplicate identities, PDR∈[0,100] in every row). Pooled
results (594 runs/protocol): PDR — AODV 37.2±28.2%, OLSR 48.1±17.2%, Static 28.6±14.8%; throughput
— AODV 85.8±56.1, OLSR 169.7±101.2, Static 109.5±95.6 kbps. OLSR delivers most consistently at
higher link-utilisation cost; Static has the lowest delay/jitter but lowest mean PDR; AODV
collapses at scale. The 75/100-node PDR collapse was confirmed (via Static's own connectivity
counter) to be channel congestion, not a topology defect.

## V4 — Sigmoid-adaptive routing

**File:** `scratch/iot-network-v3-ext.cc`, `--protocol=v4`. **Status: Implemented, Experiment
completed (957 runs), closed — Decision B.**

Edge cost = weighted sum of sigmoid-transformed RiskScore (degree-based) and LoadScore (measured,
two-pass: pass 1 measures baseline load, pass 2 installs the adaptive-cost tree). Evaluated across
297 Stage-1 sensitivity runs, 594 Stage-2 matched-comparison runs, 66 Tier-1 activation-screen
runs. **Finding:** the mechanism mechanically works — it changes route trees under the right
parameters (up to 100% of seeds re-routed in the most active configuration, mean hop count
+27.9%) — but **no activated configuration improved PDR, throughput, delay, jitter, or packet
loss over Static** with a credible effect (n=11/config). Attributed to a structural mismatch:
RiskScore reflects node geometry, not where traffic concentrates (the gateway's one-hop
neighbourhood, regardless of degree). **Closed: mechanism demonstrably works, no performance
benefit demonstrated; no further-tier experiment judged scientifically justified.**

## Safety confirmation for this report

No source file was modified, no simulation was run, and no existing data or report was overwritten
to produce this document. Section V3's status (zero runs) and the BA risky-node design were
re-verified directly against source/git/filesystem state on 2026-10-11, not assumed from prior
documentation.
