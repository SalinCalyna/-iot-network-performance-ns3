# FINAL REPRODUCIBILITY CHECK

**Type: read-only-after-analysis validation.** New simulations run only into the new, isolated
`analysis/final-reproducibility-check/` directory. No existing dataset, source file, runner
script, or the frozen `analysis/final-report-data/` package was modified.

## 1. Status
**PASS**

## 2. Exact number of runs attempted
51 (Case A: 27, Case B: 6, Case C: 12, Case D: 6)

## 3. Successful runs
51 / 51

## 4. Failed runs
0 (confirmed via `run_master.log`: `runs=51 failed=0`, and 0 error/crash signatures across all 51 per-run logs in `logs/`)

## 5. Configuration fingerprint
See `config_fingerprint.txt`. Direct source inspection of `scratch/iot-network-v3-ext.cc` and
`scratch/iot-network-bottleneck-probe.cc` confirmed identical topology (areaSize=250m, gateway at
field centre, txRange=90m nominal disk, `std::mt19937(seed)` placement RNG), identical PHY/MAC
(802.11b, ConstantRateWifiManager @ DsssRate1Mbps, LogDistance exponent=3.0/refDist=1.0/refLoss=40,
AdhocWifiMac, txPower=20dBm), identical traffic mapping (low/medium/high = 4/8/16 kbps, 512B
packets, always-on CBR), identical timing (simTime=300s, appStart=30s), and identical seed
handling (`RngSeedManager::SetSeed(seed)`, `SetRun(1)`). Both binaries were rebuilt this session;
`cmake` reported no stale targets for either, confirming the binaries already matched current
source with zero drift. **NO CONFIGURATION MISMATCH FOUND.**

## 6. Dataset/reference versions used
`analysis/final-report-data/` (the frozen package) for context; direct comparisons were made
against the underlying frozen raw datasets it was built from: `results/v3-ext/*.csv` (Case A),
`analysis/bottleneck-characterisation/data/probe_aggregate.csv` (Case B, §10), and
`analysis/bottleneck-characterisation/data-ratesweep/probe_aggregate.csv` (Cases C and D).

## 7. Metric comparison summary
687 individual metric comparisons across all 51 reruns (`reproducibility_comparison.csv`):

| Status | Count |
|---|---:|
| PASS | 681 |
| PASS_MINOR_DRIFT | 0 |
| FAIL | 0 |
| NOT_APPLICABLE | 6 (MaxRetryDrops requested for Case B, which uses the original §10 dataset — that instrumentation did not exist yet when §10 was run; correctly excluded, not a failure) |

**Every single applicable comparison (681/681) was an exact match** — integer counters (TxPackets,
RxPackets, PacketLoss, MAC-queue drops, PHY RX drops, MaxRetryDrops, routing overhead,
unreachable sensors) matched with **zero absolute difference**, and floating-point metrics (PDR,
throughput, delay, jitter, airtime, hop count, link utilization) matched to well under the 0.01%
relative-difference tolerance in every case (in practice, bit-identical on direct inspection).

## 8. Largest discrepancies
**None found.** The largest relative difference across all 681 applicable comparisons was
effectively 0% (only the wall-clock `Timestamp` field, which is expected to differ and was not
compared as a metric). This is consistent with the fully deterministic design of both simulators
(seeded Mersenne-Twister placement RNG + `RngSeedManager`, no external randomness sources) and the
fact that neither binary was recompiled with any source change since the original frozen runs.

## 9. Research-finding validation
See `research_finding_reproducibility.csv`. All 6 rechecked findings (F1, F3, F4, F5, F6, F7)
**preserved their direction** in the rerun; F2 (V4) was correctly marked **NOT RECHECKED** per
instructions, since no approved V4 configuration could be executed within this validation's scope
without risking an unauthorized configuration choice.

## 10. Any unexplained mismatch
None.

## 11. Whether the frozen thesis conclusions remain valid
**Yes, fully.** Every rechecked finding reproduced in both magnitude and direction; the six
Case-B/C/D conditions reproduced bit-identically at the per-seed level.

## 12. Whether another rerun is actually necessary
**No.** The validation matrix (51 runs, spanning all three protocols, three representative node
counts, the near-saturation bottleneck condition, the rate intervention, and the Static negative
control) found perfect reproducibility with no drift requiring further investigation.

---

## FINAL DECISION GATE

### A — REPRODUCIBLE

- **Can the thesis proceed to writing?** YES.
- **Must any frozen number be replaced?** NO — every frozen number checked in this validation reproduced exactly.
- **Is another simulation necessary?** NO.
