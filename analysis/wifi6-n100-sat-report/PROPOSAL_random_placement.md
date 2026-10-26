# Proposal (revision 2): N = 100 protocol-independent random risk placement, 72 runs — FOR REVIEW, NOT STARTED

Revision 2 (2026-10-25) replaces the first draft's relay-restricted design (random among relays of the static BFS
tree). The bias analysis below showed that design still favours OLSR by construction.

## 1. Selection bias in the placement designs
The k = 0 validated runs show which nodes actually relay traffic (a node counts as a relay if it carries ≥ 1 % of a run's packets).

| topology seed | Static relays (8 kbps) | OLSR relays (8 / 32 kbps) | shared Static ∩ OLSR (8 kbps) | OLSR transits via Static relays (8 kbps) |
|---|---|---|---|---|
| 20 | 9 | 16 / 34 | 4 | 15 % |
| 21 | 7 | 3 / 38 | 0 | 10 % |
| 22 | 14 | 15 / 36 | 3 | 18 % |

Expected exposure per design was estimated from the k = 0 packet paths (k = 3, 400 draws per seed; this ignores re-routing).

| design | candidates | Static exposure | OLSR exposure (8 / 32 kbps) | P(Static exposure = 0) | bias |
|---|---|---|---|---|---|
| subtree (done) | top BFS subtrees | 39 % (measured) | 1.5 / 4.9 % (measured) | 0 | worst case for Static; risk sits on Static's backbone |
| A: random among static-BFS relays | 7–14 | 14–22 % | 1.3–2.4 / 4.3–7.1 % | 0 | candidates are Static's relays by definition, so OLSR is favoured |
| C: random among the union of relays of all protocols | 41–51 | 3.2–3.7 % | 1.3–2.5 / 3.8–4.4 % | 0.38–0.60 | depends on observed routes; tilted toward OLSR's large relay set at 32 kbps |
| **B: uniform over all 100 sensors** | 100 | 1.7–1.9 % | 0.9–1.3 / 2.0–2.2 % | 0.64–0.79 | none by construction: placement uses only node id and seeds, never routes |

Remaining biases and properties of B:
- **Low exposure, concentrated in few draws.** In most draws no risky node lies on Static's tree (P = 0.64–0.79). This is a property being measured (Static concentrates traffic on a few relays; OLSR spreads it), not a defect. It does call for more placement draws per topology and makes k = 1 uninformative (Static exposure is zero in 87–94 % of draws).
- **Risk-Aware usually matches Static.** Risk-Aware equals Static whenever no risky node is on the BFS tree. Its benefit is already measured in the subtree study; here it is reported conditionally (draws with and without a risky node on the tree).
- **Same perfect-knowledge and transit-only drop assumptions** as the main study. Gateway never risky.
- **Precision.** From 12 draws per (protocol, rate), the 95 % range of the mean Static − OLSR exposure difference is about ±2.5 pp (SD per draw about 4 pp). That resolves whether the 37-pp gap seen under subtree placement disappears, but not differences of about 1 pp. A larger k does not improve this ratio (k = 10: SD 7–8 pp).

**Recommendation: design B.** It is the only design in which no protocol's routing determines the risk set, so it is the only one that supports a fair cross-protocol exposure comparison (H2). Designs A and C each tilt the result toward one protocol.

## 2. Hypotheses (fixed before any run)
- **H2 (primary):** under protocol-independent placement, the mean exposure of Static and OLSR differs by much less than the 37 pp seen under subtree placement. The trace-based prediction is |Δ| ≤ about 1 pp.
- **H4:** Static's exposure is concentrated: it is zero in most draws and large in a few. OLSR's is diffuse: small but non-zero in almost all draws.
- **H1 (secondary, conditional):** in draws where a risky node lies on the BFS tree, Risk-Aware has 0 exposure and a PDR gain over Static at 8 kbps that is smaller at 32 kbps.

## 3. Configuration
- **Simulator:** unchanged risk-v2 binary (`d909f6de…`), source (`33b350ab…`) and the 35 linked ns-3 libraries (`SIMULATOR_LIBS.sha256`).
- **Arguments:** all identical to the saturated study except `--riskSelect=ids --highRiskIds=<a,b,c>`. The risk set is explicit in every argv.
- **Placement rule:** the k sensors with the smallest `SplitMix64(SplitMix64(SplitMix64(P) ^ topology_seed) ^ id)`. P ∈ {101, 102, 103, 104} are pre-registered placement seeds, independent of topology seeds 20–22.
- **Grid:** Static, Risk-Aware, OLSR × k = 3 × {8, 32} kbps × topology seeds {20, 21, 22} × P {101–104} = **72 runs**.
- **Reuse:** k = 0 baseline = 18 validated runs (8 kbps from `n100-8k-v2-20261024T165009`, 32 kbps from `n100-sat-v2-20261025T112146`), reused in place.
- **Pre-registered sets** (dry run, `preregistration.json`; reference model):

| seed | P = 101 | P = 102 | P = 103 | P = 104 |
|---|---|---|---|---|
| 20 | 38, 46, 31 | 47, 20, 93 | 49, 94, 46 | 77, 34, 54 |
| 21 | 51, 18, 2 | 87, 26, 77 | 9, 92, 24 | 41, 47, 14 |
| 22 | 95, 94, 21 | 50, 30, 20 | 33, 70, 18 | 45, 53, 35 |

Five of the 12 sets contain a node of the static BFS tree (47; 9; 21; 30; 18, relaying for 1–7 sensors).

## 4. Scripts (new files; the simulator and validated scripts are unchanged)
**`experiments/wifi6-risk/run_n100_randplace.py`** reuses `run_n100_sat.py`'s execution engine.
- Placement modes: `--placement=uniform` (default) or `relay` (design A).
- `--dry-run=<dir>` writes the plan without simulating.
- Safeguards:
  - binary, source and 35-library sha256 checked at start, before the full phase and at each gate
  - ≥ 5 GB free to start; no new run below 1.5 GB
  - at most 6 jobs, reduced under memory pressure or a CPU speed limit
  - `preregistration.json` written before the first run
  - resumable; interrupted runs are moved, never deleted; a failed run is never overwritten; no automatic retries
  - per-run provenance and output sha256
  - critical stop on any failed check
- 6-run gate: seed 20, P = 101, 3 protocols × 8 and 32 kbps.

**`experiments/wifi6-risk/analyze_randplace.py`** is a copy of `analyze_pilot_n30.py` with placement-aware run ids, reference sets and keys, plus `--out`.
- New checks:
  - R1: Static routes equal the k = 0 Static routes.
  - R2: Risk-Aware has no exposure when no source is unavoidable.
  - R3: key_missing = 0, and the simulator echoes the preregistered ids in order.
- Tests run so far (no simulation):
  - Regression on the validated saturated batch: identical P0–P6 results (1,263 checks) and identical `pilot_runs.csv`; R1–R3 add 171 passing checks.
  - Fault injection: a wrong risk set fails P2 and P3; a run not in ids mode fails R3; a missing k = 0 reference fails R1.

## 5. Validation criteria
- **Gate (6 runs) and final (72 + 18 reused):** 0 failed for P0–P6 and R1–R3.
- **After the final gate:** independent recomputation (`verify_n100_sat.py`-style) and a checksum manifest.
- **Stop rules** as in the saturated study.
- **Note:** the ids selection path has not been used in any earlier validated run. The gate is its first execution, and P2, P3 and R3 test it directly.

## 6. Runtime and resources
- **Job time:** about 1,800 job-minutes (mean wall per run: OLSR 30 / 51 min, Risk-Aware 10 / 27 min, Static 7 / 24 min at 8 / 32 kbps).
- **Wall time:** about 5 h at 6 jobs, or 7.5–8 h at 4 jobs (memory pressure held the last batch at 4 most of the time). The gate takes about 75 min.
- **Disk:** about 0.65 GB. The start requires ≥ 5 GB free; about 5.3 GB is free now, so free about 3 GB first.

## 7. Analysis plan (descriptive)
- Per (protocol, rate): mean, SD and distribution over 12 draws of exposure, risk drops, PDR, throughput, delay p50/p95/p99, hops, gateway airtime and MAC drops. Also the share of draws with zero exposure (H4).
- Paired Static − OLSR and Risk-Aware − Static per draw.
- Conditional on "a risky node on the BFS tree" (H1).
- Comparison with the subtree study at the same (seed, rate) and k = 3.
- Comparison of the trace-based predicted exposure with the measured exposure.
