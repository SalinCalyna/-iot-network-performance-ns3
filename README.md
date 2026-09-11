# Analysis of IoT Network Performance Using NS-3

Identifying congestion bottlenecks and evaluating traffic-rate mitigation in multi-hop IoT
wireless networks, using the [ns-3](https://www.nsnam.org/) network simulator.

**Status:** Research Complete — the research described below is **frozen**.

| | |
|---|---|
| Simulation | NS-3 |
| Network | Multi-hop 802.11b ad-hoc IoT mesh |
| Protocols | AODV / OLSR / Static / V4 Sigmoid-Based Adaptive Routing (investigation) |
| Official V3 baseline | 1,782 runs |
| Reproducibility | 51/51 validation runs PASS |
| Research status | **FROZEN** |
| Dashboard | [GitHub Pages](https://salincalyna.github.io/-iot-network-performance-ns3/) |

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
[`docs/research-history.md`](docs/research-history.md).

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
  methodology.md, experiment-design.md, sigmoid-metric.md, v3-experiment-framework.md
                                  Design rationale (historical + V3 framework)
dashboard/
  app.py                         Local-only Flask dashboard (legacy V2.7 result browser;
                                 not used by the public GitHub Pages site)
site/
  index.html, static/, data/     Public GitHub Pages dashboard -- presents the frozen final
                                 research (see Public dashboard below)
.github/workflows/
  deploy-pages.yml                Deploys site/ to GitHub Pages on every push to main
```

## Public dashboard (GitHub Pages)

https://salincalyna.github.io/-iot-network-performance-ns3/

A static HTML/CSS/JS site (no backend) built from `analysis/final-report-data/figure_data.csv`
and the other frozen package files, deployed automatically by GitHub Actions on every push to
`main`. It presents: Overview, Baseline Performance, V4 Routing Investigation, Bottleneck,
Retry Exhaustion, Offered-Rate Intervention, Static Control, Reproducibility, and Conclusions &
Limitations. Earlier (V2.7/V3-prototype) results are shown separately under a "Research History"
section, clearly labelled as historical and not mixed into the final-research charts.

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
</details>
