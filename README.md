# Analysis of Gateway-Centric IoT Wireless Mesh Networks Using NS-3

Identifying congestion bottlenecks and evaluating traffic-rate mitigation in multi-hop IoT
wireless networks, using the [ns-3](https://www.nsnam.org/) network simulator.

**Status:** Phases 1–7 (below) are complete and **frozen** — independently verified reproducible
(51/51 validation runs, 681/681 applicable metric comparisons). **A Wi-Fi 6 (802.11ax)
Risk-Aware Routing study was completed and validated in 2026-10** (208 runs; see
[Wi-Fi 6 Risk-Aware Routing](#wi-fi-6-risk-aware-routing-completed-2026-10) below). **A separate
Phase 8 opened 2026-10** per advisor direction (BA topology / risky-node routing) — this is a
proposed experimental design only; nothing has been executed yet. See
[Advisor feedback (2026-10)](#advisor-feedback-2026-10--ba-topologyrisky-node-routing) below and
[`docs/v1-v4-methodology-results.md`](docs/v1-v4-methodology-results.md) for the full,
verification-labelled status of every track.

| | |
|---|---|
| Simulation | NS-3 |
| Network | Multi-hop 802.11b ad-hoc IoT mesh (Phases 1–7); 802.11ax (Wi-Fi 6) ad-hoc mesh (risk study) |
| Protocols | AODV / OLSR / Static / V4 Sigmoid-Based Adaptive Routing (investigation); Risk-Aware routing (Wi-Fi 6 study) |
| Official V3 baseline | 1,782 runs |
| Reproducibility | 51/51 validation runs PASS |
| Dashboard | [GitHub Pages — /site/index.html](https://salincalyna.github.io/-iot-network-performance-ns3/site/index.html) |

### Research status

| Track | Network | Status | Evidence |
|---|---|---|---|
| Phases 1–7: V3 baseline → V4 → bottleneck → retry → rate intervention → Static diagnostic → reproducibility | IEEE 802.11b mesh | **Frozen** — reproducible (51/51 runs) | [`analysis/final-report-data/`](analysis/final-report-data/) |
| Wi-Fi 6 Risk-Aware Routing (low/high-risk relay states, k = 0–3) | IEEE 802.11ax mesh | **Completed and validated** (2026-10) — N = 30 (10 seeds, inferential), N = 100 (3 seeds, descriptive) | [section below](#wi-fi-6-risk-aware-routing-completed-2026-10); [dashboard](https://salincalyna.github.io/-iot-network-performance-ns3/site/index.html#view-w6-overview) |
| N = 100 saturated-load risk experiment | IEEE 802.11ax mesh | **Not run** (pending approval) | — |
| Phase 8: BA topology / risky-node routing | Barabasi-Albert graph | **Proposed — not yet executed** (opened 2026-10) | [Advisor feedback](#advisor-feedback-2026-10--ba-topologyrisky-node-routing) |

## Researcher

| | |
|---|---|
| Researcher | Salinthip Keereerat |
| Student ID | 6630613037 |
| Institution | College of Computing, Prince of Songkla University, Phuket Campus |
| Advisor | Komsan Kanjanasit |
| Co-Advisors | Wisarut Chantara, Kullawat Chaowanawatee |
| GitHub | [@SalinCalyna](https://github.com/SalinCalyna) |
| Repository | https://github.com/SalinCalyna/-iot-network-performance-ns3 |

## Research question

> What is the main cause of packet loss in a multi-hop IoT network as network size and traffic
> load increase, and can the identified bottleneck be mitigated by reducing offered traffic rate?

## Objective

To analyze and identify the factors affecting performance and packet loss in a multi-hop IoT
network using NS-3, and to evaluate whether appropriate traffic management can mitigate
congestion and improve network reliability.

## Conclusion

> The study identifies gateway and first-hop congestion as the dominant measurable bottleneck
> under near-saturated conditions and demonstrates that reducing offered traffic rate can
> effectively mitigate this bottleneck and improve PDR in OLSR networks at high node densities.
> However, the effectiveness of the intervention is protocol- and load-dependent, and a portion
> of packet loss remains unattributed by the current instrumentation.

## Key findings

**1. Network scale and traffic load.** Performance degrades as node count and traffic load
increase, consistently across AODV, OLSR, and Static routing (V3 official baseline, 1,782 runs).

**2. V4 routing investigation.** Sigmoid-based adaptive routing changed routing behaviour under
selected conditions — up to 100% of seeds re-routed relative to Static's shortest-path tree at
the strongest tested configuration — but routing activation did not produce a statistically
credible performance improvement over Static. This is a valid negative result, not a failed
implementation: the mechanism runs, computes, and measurably alters routes; it simply does not
move delivery performance under the tested conditions.

**3. Main measurable bottleneck.** Gateway and first-hop congestion becomes the dominant
measurable bottleneck under near-saturated conditions (176-run bottleneck characterisation).
Gateway airtime reaches approximately 0.86–0.89 at high node counts under high traffic, and
MAC-layer queue drops are 1.2–2.4× over-represented in the first-hop neighbourhood. Routing
failures (NO_ROUTE / ROUTE_ERROR) are negligible in every tested condition.

**4. Retry exhaustion.** MAC-layer retry exhaustion exists and is directly measured (36-run
validation), but it is not the dominant mechanism — it accounts for a mean of roughly 6% of loss
and is concentrated farther from the gateway, the opposite spatial pattern from MAC-queue
overflow.

**5. Traffic-rate intervention.** Reducing offered traffic rate (16 → 12 → 8 → 4 kbps) improves
OLSR PDR at N=75 and N=100 (72-run offered-rate sweep). At the deepest reduction tested:
- **N=75: approximately +14.7 percentage points**
- **N=100: approximately +25.2 percentage points**

At N=100, delivered throughput actually *rises* at a reduced offered rate — the signature of
recovering from congestion collapse rather than simply delivering less because less was sent.

**6. Static routing.** Static routing at N=50 does not show the same improvement from
offered-rate reduction (12-run diagnostic) — PDR is flat to negative across all tested rates and
seeds. This is not evidence of a broken protocol: the mechanisms the intervention relieves
(airtime, MAC-queue overflow) were never the dominant source of loss for this specific condition.

**7. Remaining limitation.** A portion of packet loss remains unattributed by the current
instrumentation — for the Static/N=50 diagnostic, residual (unattributed) loss ranges
64.65%–99.57% across the 12 tested runs (typically ≥92%), while currently attributed mechanisms
account for only about 0.4–35.4%. This is reported as an instrumentation limitation, not a claim
about a specific unmeasured physical cause.

## Important caveats

- **AODV:** AODV's PDR and packet-loss figures are affected by a known ns-3 FlowMonitor
  `PacketsSent`-denominator artifact tied to AODV's route discovery/repair behaviour. They should
  be read as indicative and directionally robust, not exact cross-protocol comparisons. Throughput
  and qualitative trends are unaffected.
- **OLSR:** `RoutingOverheadPackets` reads 0 for OLSR in the V3 dataset. This is a
  metric-coverage limitation in that measurement (its classifier is scoped to AODV's control
  ports), **not** evidence that OLSR generates zero control traffic.
- **Static routing:** some sensors were unreachable at low node counts in the V3 baseline (a
  sparse-topology / placement effect, not a routing-failure mechanism); this was not observed as
  material in the bottleneck/intervention experiments. The large unattributed-loss gap at
  Static/N=50 (see Finding 7) is a separate, later finding specific to that condition.
- **V4:** a valid negative result — the mechanism activates and changes routing behaviour, it
  does not improve delivery performance under the tested conditions. This is not a failed
  implementation.

## Wi-Fi 6 Risk-Aware Routing (completed 2026-10)

A follow-on study on an IEEE 802.11ax (Wi-Fi 6) version of the gateway-centric mesh, adding
explicit low-risk / high-risk relay states. It is **separate from the frozen 802.11b research
above** (different PHY/MAC, different simulator) and **separate from the proposed Phase 8 BA
study** (different topology). Live results:
[dashboard → Wi-Fi 6 Risk-Aware Routing](https://salincalyna.github.io/-iot-network-performance-ns3/site/index.html#view-w6-overview).

**Objectives**
1. Measure how 0–3 high-risk relay nodes affect delivery and risk exposure under Static, OLSR and
   AODV routing.
2. Test whether risk-aware route selection reduces exposure and loss, and at what cost in delay,
   path length and airtime.
3. Check whether the result holds when the network grows from 30 to 100 sensors.

**Methodology (summary)**
- **Network:** 802.11ax, 2.4 GHz channel 1, 20 MHz, HE MCS 0, A-MPDU/A-MSDU off, ARP
  pre-populated.
- **Topology:** 250 m × 250 m area with the gateway at the centre; static, seeded positions.
- **Traffic:** 512 B UDP CBR at 8 kbps per sensor, with all sensors sending at the same instants
  (synchronized, inherited from the V3 design). simTime is 300 s and traffic starts at 30 s.
- **Risk model:** each sensor is LOW_RISK (drop probability 0) or HIGH_RISK (0.5 for every transit
  data packet). The k = 0–3 high-risk relays are the top-k relays of Static's BFS tree (most
  descendants). Risk drops are deterministic hashes, so the same packet gets the same decision
  under every protocol.
- **Protocols:** Static (BFS shortest path on a 90 m disk graph), Risk-Aware (Dijkstra where entering
  a transit node costs 1 + 10·(−ln(1 − r)), on the same graph, with oracle knowledge of risk), and
  OLSR and AODV with unmodified ns-3 defaults.
- **Matched design:** within a seed, positions, traffic and the high-risk set are identical for
  every protocol.
- **Simulator:** `iot-network-wifi6-risk-v2`. It includes one fix for a confirmed ns-3 Block Ack
  defect: an ADDBA SSN mismatch left packets held for up to 65.3 s at N = 30, 16 kbps (seed 20,
  100 s run).
- **Runs and checks:** N = 30, seeds 20–29 (160 runs, 1,830/1,830 checks passed); N = 100, seeds
  20–22 (48 runs, 549/549 checks passed).
- **Metric:** all main comparisons use **nominal PDR** (delivered ÷ scheduled packets). In all 208
  runs no scheduled packet went unsent, so nominal PDR equals sink-based PDR.

**Major findings**

N = 30 (10 seeds; inferential), Risk-Aware − Static on the same seed:

| k | Static PDR | Risk-Aware PDR | Δ PDR [95 % CI] | Δ exposure [95 % CI] | Pairs favouring Risk-Aware |
|---|---|---|---|---|---|
| 1 | 89.21 % | 99.67 % | +10.45 pp [+8.20, +12.71] | −21.00 pp [−25.64, −16.36] | 10/10 |
| 2 | 81.50 % | 99.50 % | +18.00 pp [+14.99, +21.00] | −36.00 pp [−42.13, −29.86] | 10/10 |
| 3 | 76.32 % | 99.50 % | +23.18 pp [+19.81, +26.54] | −46.33 pp [−53.21, −39.46] | 10/10 |

Exact Wilcoxon signed-rank p = 0.00195 for each of these six primary tests; Holm-adjusted
p = 0.0117. With n = 10, 0.00195 is the smallest attainable exact p.

- **Cost at N = 30.** p95 delay is +4.1 to +9.1 ms higher than Static at k = 1–3, and gateway
  airtime +0.005 to +0.013. Part of the delivered-packet difference is survivorship, because
  Static loses the relayed packets that cross risky nodes. Over *all sent* packets, Risk-Aware
  paths really do lengthen, from 1.64 to 1.75 links at k = 3.
- **N = 100 (3 seeds; descriptive only — no significance claimed).**
  - Risk-Aware − Static, same seed: nominal PDR +9.15 / +15.74 / +19.70 pp and exposure
    −18.33 / −31.33 / −39.33 pp at k = 1 / 2 / 3. The direction is the same in 3/3 seeds.
  - Every exposed source had a safe alternative, so Risk-Aware exposure is 0 in every run.
  - All-sent path length is unchanged at 1.613 links for every k, so the delay and hop
    differences versus Static are survivorship. Against its own k = 0 run, Risk-Aware's
    p50/p95/p99 delay stays within −1.1 to +2.5 ms.
- **AODV at N = 100 (secondary finding).**
  - AODV delivered 56.60 ± 1.76 % against OLSR's 99.62 ± 0.04 % (k = 0, 3 seeds). The level is
    nearly the same at every k, so the risk model is not the cause; at N = 30 (k = 0, 10 seeds)
    AODV delivers 99.99 %.
  - A diagnostic on seed 20 excluded the Block Ack fix as the cause: with it switched off, PDR
    was 53.21 % against 55.13 % with it on, and airtime was unchanged.
  - Confirmed in the ns-3 source: AODV treats every dropped unicast MPDU, including queue-lifetime
    expiry, as a link failure.
  - The suspected mechanism is a self-reinforcing loop: MAC queue expiry → link failure → RERR
    and route rediscovery → more airtime → more expiry. This is a **hypothesis**; it was not
    isolated experimentally.
  - AODV results are reported as measured; AODV was not tuned.

**Limitations**
- **Selection bias:** high-risk relays are chosen from Static's tree, which is Static's worst
  case.
- **Oracle risk:** Risk-Aware knows each node's risk exactly and the risk is static, so its
  benefit is an upper bound.
- **Different link models:** Static and Risk-Aware route on a 90 m disk graph, while OLSR and AODV
  discover links over the real radio range.
- **Synchronized CBR traffic:** all sensors send at the same instants.
- **Light load:** per-run gateway airtime 0.04–0.08 at N = 30 and 0.19–0.44 at N = 100,
  excluding AODV.
  The N = 100 saturated-load experiment has not been run.
- **Three seeds at N = 100:** these results are descriptive only.
- **Residual Block Ack tail:** under saturation only, 13–37 per 100k delivered packets are delayed
  more than 10 s. In the main experiments no Static, Risk-Aware or OLSR packet exceeded 10 s;
  one AODV packet did (N = 100).
- **Delay survivorship:** delay is measured over delivered packets only.
- **AODV mechanism:** the causal chain is not isolated, the Block Ack check covers one seed, and
  the MAC queue lifetime (500 ms) was not varied.

**Reproducibility status:** the validated tables, figures and per-run analysis are kept in the
researcher's working repository. The dashboard data file (`site/data/wifi6-risk.json`) lists every
source file it was built from, with its sha256. The Wi-Fi 6 simulator source and raw run outputs
are **not yet part of this public repository**.

## Advisor feedback (2026-10) — BA topology/risky-node routing

Komsan Kanjanasit requested, in 2026-10 feedback, that the frozen research above (Phases 1–7) be
followed by a new investigation on the Barabasi-Albert (BA) topology / risk-aware routing study:

1. Explain why and how the routing mechanism works.
2. Add explicit low-risk and high-risk node states.
3. Assign 1–3 high-risk nodes and study routing behaviour.
4. Prepare a methodology and results report for V1–V4 before proceeding further.

**Status: proposed design only — no code change, no simulation run, no existing data touched.**
(Requests 2 and 3, explicit low/high-risk node states with 1–3 high-risk nodes, have since been
implemented and measured on the *wireless mesh* in the
[Wi-Fi 6 Risk-Aware Routing](#wi-fi-6-risk-aware-routing-completed-2026-10) study. The BA-topology
version described here is still unrun.)
The full audit and design (topology/algorithm as it exists today, the proposed low/high-risk
node-state model and its supporting references, exactly how — and when it would *not* — affect
route selection, the matched 0/1/2/3-high-risk-node experiment matrix, a 12-run pilot, and the
required logging additions) is in
[`docs/v1-v4-methodology-results.md`](docs/v1-v4-methodology-results.md). **Important scope note
on the filename:** `scratch/iot-network-v3.cc` in *this* repository is still the legacy 15-node
sigmoid pilot (see "Early V3 sigmoid prototype" below) — the 26-node Barabasi-Albert risk-aware
simulator this new phase targets is a separate, same-named program that exists only as an
uncommitted file in the researcher's local working environment and is **not yet part of this
repository**. The two must not be confused; this is exactly the kind of V3-vs-V3 mislabeling this
audit was asked to guard against.

## Reproducibility

The frozen research was independently re-executed using a 51-run validation matrix covering the
V3 baseline (AODV/OLSR/Static), the bottleneck condition, the rate intervention, and the Static
negative control. All 51 runs completed successfully. Of 687 metric comparisons, 681 applicable
comparisons passed exactly, with no failed comparisons and no numerical drift. Six comparisons
were not applicable because `MaxRetryDrops` was not available in the original §10 dataset (that
instrumentation was added in a later phase). Based on this validation, the frozen research
results are considered reproducible from the current source code and configuration.

Full detail: [`analysis/final-reproducibility-check/FINAL_REPRODUCIBILITY_CHECK.md`](analysis/final-reproducibility-check/FINAL_REPRODUCIBILITY_CHECK.md).

## Data source of truth

All reported research values are based on the frozen **Final Report Data Package** at
[`analysis/final-report-data/`](analysis/final-report-data/):

| File | Contents |
|---|---|
| `final_metrics.csv` | Master cross-stage metrics table |
| `v3_core_results.csv` | V3 baseline, by protocol × node count |
| `v4_results.csv` | V4 matched / sensitivity / Tier-1 activation results |
| `bottleneck_results.csv` | Gateway/first-hop congestion evidence (§10) |
| `retry_results.csv` | Retry-exhaustion validation results |
| `rate_sweep_results.csv` | Offered-rate intervention results, with deltas vs. the 16 kbps baseline |
| `static_n50_diagnostic.csv` | Static/N=50 residual-loss accounting, all 12 runs |
| `figure_data.csv` | Clean plotting data for the core figures |
| `thesis_evidence_map.csv` | The seven findings mapped to research question, evidence, and limitation |
| `REPORT_DATA_DICTIONARY.md` | Metric definitions, units, and caveats |
| `final_number_check.csv` | Cross-file numerical consistency check |
| `FINAL_REPORT_DATA_PACKAGE.md` | Package summary and authoritative numbers |

## Research history

The project progressed through seven phases before being frozen: V3 baseline → V4 sigmoid-routing
investigation → bottleneck characterisation → retry-exhaustion validation → offered-rate
intervention → Static/N=50 diagnostic → final reproducibility validation. Earlier project
iterations (V1/V2.7) and their results are preserved for context, not as current findings — see
[`docs/research-history.md`](docs/research-history.md), which also now documents the proposed
Phase 8 (BA risky-node study). For the advisor's own "V1–V4" framing specifically, cross-walked to
these phases and labelled Implemented / Experiment completed / Proposed / Not yet verified, see
[`docs/v1-v4-methodology-results.md`](docs/v1-v4-methodology-results.md).

## Final research source code

- **`scratch/iot-network-v3-ext.cc`** — the official V3 baseline simulator (AODV / OLSR / Static,
  the full node-count/traffic/mobility matrix).
- **`scratch/iot-network-bottleneck-probe.cc`** — the instrumented research simulator used for
  bottleneck characterisation, retry-exhaustion validation, the offered-rate intervention, and the
  Static/N=50 diagnostic. It replicates the V3 topology/PHY/MAC/traffic configuration exactly and
  adds per-node instrumentation (airtime, MAC-queue drops, PHY RX drops, retry-exhaustion drops,
  hop distance).

`scratch/iot-network.cc`, `scratch/iot-network-v3.cc`, and `scratch/scratch-simulator.cc` are
**legacy/historical implementations** from earlier project iterations (V1/V2.7 and an early V3
sigmoid prototype) — kept for reference and reproducibility of the project's history, not part of
the current frozen research. See `docs/research-history.md`.

## Repository contents

```
scratch/
  iot-network-v3-ext.cc          Final: V3 official baseline simulator (AODV/OLSR/Static)
  iot-network-bottleneck-probe.cc Final: instrumented simulator (bottleneck/retry/rate-sweep/diagnostic)
  iot-network.cc                 Legacy (V2.7)
  iot-network-v3.cc               Legacy (early V3 sigmoid prototype)
  scratch-simulator.cc            Legacy (V1)
results/
  v3-ext/                        Official V3 baseline results (1,782 rows, Seed 20-30)
  v4-matched/, v4-sensitivity/   V4 sigmoid-routing results
  *.csv, logs/, plots/, v3/      Legacy (V2.7) results, kept for history
analysis/
  final-report-data/             Authoritative frozen results package (source of truth)
  final-reproducibility-check/   51-run reproducibility validation
  bottleneck-characterisation/   Raw §10 / retry-exhaustion / rate-sweep run outputs
  update8-tier1-activation/      V4 activation-screen raw data
  final-github-release/          This release's audit trail
docs/
  research-history.md             V1 -> V2 -> V3 -> V4 -> bottleneck -> intervention -> frozen
                                  -> Phase 8 BA risky-node (proposed, 2026-10)
  v1-v4-methodology-results.md    Advisor's "V1-V4" framing, cross-walked to real tracks/files,
                                  each item labelled Implemented/Completed/Proposed/Not verified
  methodology.md, experiment-design.md, sigmoid-metric.md, v3-experiment-framework.md
                                  Design rationale (historical + V3 framework)
dashboard/
  app.py                         Local-only Flask dashboard (legacy V2.7 result browser;
                                 not used by the public GitHub Pages site)
site/
  index.html, static/, data/     Public GitHub Pages dashboard -- presents the frozen final
                                 research (see Public dashboard below)
  wifi6.js, data/wifi6-risk.json, images/wifi6/
                                 Wi-Fi 6 Risk-Aware Routing sections (data file lists its
                                 validated sources with sha256)
.github/workflows/
  deploy-pages.yml                Runs on every push to main (see Public dashboard below)
```

## Public dashboard (GitHub Pages)

https://salincalyna.github.io/-iot-network-performance-ns3/site/index.html

A static HTML/CSS/JS site (no backend) built from `analysis/final-report-data/figure_data.csv`
and the other frozen package files. GitHub Pages serves the `main` branch, so the dashboard
lives under `/site/` (the site root shows this README). `.github/workflows/deploy-pages.yml` also
runs on every push to `main`. It presents: Overview, Baseline Performance, V4 Routing
Investigation, Bottleneck, Retry Exhaustion, Offered-Rate Intervention, Static Control,
Reproducibility, and Conclusions & Limitations. Earlier (V2.7/V3-prototype) results are shown
separately under a "Research History" section, clearly labelled as historical and not mixed into
the final-research charts.

A separate sidebar group, **Wi-Fi 6 Risk-Aware Routing — Measured**, adds six sections:
- Risk Study Overview;
- Results (N = 30 / N = 100);
- Paired Risk-Aware vs Static;
- Cost of Avoidance;
- AODV Diagnostic;
- Validity & Limitations.

N = 30 is shown with 95 % confidence intervals and exact tests. N = 100 is descriptive only, with
no p-values.

`dashboard/app.py` is a separate, local-only Flask tool that browses the legacy V2.7
`results/*.csv` files directly; it is not the public dashboard and is not part of the frozen
final research.

## Reproducing the simulation

Both final simulators are ns-3 scratch programs; they need a working ns-3 checkout to build and
run:

```bash
# from the root of a working ns-3 checkout
cp scratch/iot-network-v3-ext.cc scratch/iot-network-bottleneck-probe.cc <ns-3-checkout>/scratch/
cd <ns-3-checkout>
./ns3 build iot-network-v3-ext iot-network-bottleneck-probe
```

See `analysis/final-reproducibility-check/config_fingerprint.txt` for the exact parameter
fingerprint (topology, PHY/MAC, traffic, timing, seed handling) confirmed reproducible against
this repository's frozen results, and `analysis/final-report-data/REPORT_DATA_DICTIONARY.md` for
every command-line flag and metric definition. The `results/` and `analysis/` directories in this
repository already contain the CSVs produced by the frozen research — you do not need to rerun
anything to inspect the data.

## Legacy: earlier project material

The sections below describe earlier (pre-freeze) project iterations, kept for history. They are
**not** the current research — see Key Findings above for the frozen results.

<details>
<summary>V2.7 baseline (legacy)</summary>

12 scenarios (3 protocols × 4 network sizes: 10/20/30/50 nodes), 5 independent topology seeds per
scenario, 60 total simulation runs. Network: multi-hop IEEE 802.11b ad-hoc mesh (`AdhocWifiMac`,
`ConstantRateWifiManager @ DsssRate1Mbps`, `LogDistancePropagationLossModel` exponent=3.0,
referenceLoss=40dB); gateway/sink/server merged into a single node at the field centre; 250×250 m
deployment area, 20 dBm tx power; 8 kbps continuous UDP CBR per sensor, 512 B packets; 100 s total
simulation time, traffic active 30–100 s.

A validation pass on the V2.7 results found the same AODV `PacketsSent`-denominator behaviour
later confirmed and documented in the frozen research's AODV caveat above.
</details>

<details>
<summary>Early V3 sigmoid prototype (legacy, superseded by V4)</summary>

`scratch/iot-network-v3.cc` was an early, separate exploration: a 15-node clustered topology with
a 4th routing mode computing Dijkstra shortest paths over sigmoid-weighted edge costs. Only a
4-run smoke test was ever executed (not a statistical study). This line of investigation was
superseded by the V4 Sigmoid-Based Adaptive Routing study on the official V3 topology (see Key
Findings, Finding 2), which is the frozen, authoritative result for adaptive routing in this
project. Design rationale for the prototype remains in `docs/sigmoid-metric.md`,
`docs/methodology.md`, and `docs/experiment-design.md` for historical reference.

**Filename collision, flagged 2026-10:** a *different* program, also named `iot-network-v3.cc`,
was later written for the new Phase 8 BA/risky-node study (see "Advisor feedback (2026-10)"
above) — a 26-node Barabasi-Albert topology with degree-based structural risk, unrelated to this
15-node pilot. That program is not in this repository yet (local, uncommitted). Do not assume any
result or description here applies to it.
</details>
