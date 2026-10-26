# PSU Phuket campus-specific ns-3 simulation: methodology, validation and results

Date: 2026-10-26. Batch: `results/campus-sim/campus-matrix-20261026T161440` (108 runs), preceded by the pilot
`results/campus-sim/campus-pilot-20261026T160720` (6 runs). Raw per-run outputs stay outside Git; every file is listed
with sha256 in `RAW_OUTPUTS.sha256`.

## 1. Evidence categories

| # | Category | Status in this study |
|---|---|---|
| 1 | Proposed campus deployment | Input. Sensor sites from the deployed Smart Campus dashboard (`site/data/campus/campus.json` at commit 66b422f4e), derived from a frozen OpenStreetMap snapshot. Conceptual, not installed. |
| 2 | Campus-specific ns-3 results | **This report.** Simulated on the proposed layout; uncalibrated. |
| 3 | Validated generic mesh results | Not changed. The random 250 m field studies (N = 30 / N = 100, uniform placement) are separate and remain as published. |
| 4 | Real campus measurements | **None.** No sensor is installed; no RSSI, loss or traffic was measured on campus. |

Nothing in this report is a measurement of campus performance, and no result is calibrated.

## 2. Inputs

- `inputs/campus.json`: byte copy of the dashboard data (sha256 `b44e7d9b…`, recorded in `inputs/topology_check_gw627751851.json`).
- `inputs/positions_gw627751851.csv` (sha256 `5e898bcd70cb7931694934913db8d4f46f97e69a6900a7e3d8c054a8aa051cae`),
  made by `experiments/campus-sim/make_positions.py`: the dashboard's 83 proposed sensors (27 environmental,
  21 traffic, 7 flood, 28 lighting) in dashboard order, plus the gateway at the centroid of the administration
  building (OSM way 627751851) as node 83. Coordinates are the dashboard's local metric frame, unchanged
  (round trip to the dashboard lat/lon ≤ 0.02 m, i.e. rounding only). No node was moved or added.
- `inputs/node_map_gw627751851.csv`: node id ↔ application, lat/lon and OSM source of each site.
- `inputs/topology_check_gw627751851.json`: under the 90 m link model, 284 links, one component, all sensors reach the
  gateway, max 7 hops, mean degree 6.76, gateway degree 10, minimum pairwise distance 30.11 m. 170 of 284 links
  (60 %) cross an OSM building footprint (descriptive; the radio model has no buildings).

## 3. Simulator

- `scratch/iot-network-wifi6-campus.cc` (sha256 `7c2d52276e6b9a42f5996c66ba0890ff16557924ea8fb0c40f8907c3822c56ee`)
  = the validated `scratch/iot-network-wifi6-risk-v2.cc` (sha256 `33b350ab…`, unchanged) plus one option,
  `--positionsFile` (header `node_id,x,y`, N + 1 rows in order, gateway last; the simulator aborts on a bad header,
  count, order or non-finite value).
- Without `--positionsFile` its output was byte-identical to a validated risk-v2 run; four malformed files aborted as
  intended; with the campus file every node used the exact coordinates (gate P7, below).
- Binary `build/scratch/ns3-dev-iot-network-wifi6-campus-default`, sha256 `96fe6f3a…`; ns-3 libraries listed in
  `SIMULATOR_LIBS_CAMPUS.sha256`.
- **Library rebuild.** Building the campus program re-ran CMake and recompiled all 35 ns-3 libraries, so their hashes no
  longer equal the frozen `analysis/wifi6-n100-sat-report/SIMULATOR_LIBS.sha256` (that file was not edited; the
  original libraries are in the iCloud backup `wifi6-risk-backup-20261025T225734`). Re-running three validated N = 30
  configurations with the rebuilt libraries reproduced all 39 output files byte for byte (except the wall-clock column
  of `probe_aggregate.csv`), so the rebuilt libraries are functionally equivalent for this simulator.
- Radio and traffic as in the validated study: 802.11ax HE MCS0, 2.4 GHz, 20 MHz, 20 dBm, log-distance path loss
  (exponent 3, 40 dB at 1 m), open space, 512-byte UDP CBR from every sensor to the gateway, 30–300 s, ARP pre-populated.
  Base arguments are in `matrix/batch.json`.

## 4. Design (fixed before the matrix ran)

- Protocols: Static (BFS tree), Risk-Aware (risk-weighted Dijkstra, oracle risk knowledge), OLSR.
- Risk: k = 0 (none) or k = 3 high-risk relays, transit-only drop probability 0.5, decided by a SplitMix64 hash of
  (riskDropSeed, node, src, seq), so all protocols of one draw face identical drop decisions.
- Placements for k = 3: `subtree` (the simulator's rule: on Static's tree, the worst case for Static) and four uniform
  sets drawn by hash, preregistered in `matrix/preregistration.json`: u101 [16, 44, 25], u102 [42, 35, 76],
  u103 [39, 53, 55], u104 [19, 5, 47].
- Rates 8 and 32 kbps per sensor; seeds 1–3 with `--riskDropSeed = --seed`.
- 3 protocols × (1 + 5 placements) × 2 rates × 3 seeds = 108 runs. Per rate, k = 3 gives 15 matched draws
  (5 placements × 3 seeds).
- Statistics (`experiments/campus-sim/analyze_campus_stats.py`): per-draw paired differences with a 95 % t interval
  (df = 14), exact sign-flip permutation p (2^15 patterns), exact Wilcoxon p, a placement-level 95 % t interval
  (n = 5, df = 4) as the cluster-conservative range, and Holm adjustment over the 12 primary tests (nominal PDR and
  exposure × 3 comparisons × 2 rates). Classes: *supported* (primary, Holm p < 0.05, draw-level interval excludes 0,
  same sign in all 5 placements); *consistent* (secondary metric, same criteria without Holm; exploratory);
  *descriptive* (everything else, and all delay and hop metrics, which cover delivered packets only); *identical*
  (all 15 differences 0).

## 5. Validation

### 5.1 Pilot
6 runs (k = 0 and subtree k = 3, 8 kbps, seed 1, three protocols): 88 checks passed, 0 failed.

### 5.2 Matrix gate, first pass: failed (checker defect)
`matrix/gate1_failed/CHECKS.txt`: 1502 passed, **40 failed**, all in P3 "risk drops valid", exactly the 40
Static/OLSR k = 3 runs with seeds 2 and 3.

Cause: `analyze_campus.py` had been adapted from the randplace analyzer, where every run used `riskDropSeed = 1`, and
recomputed the reference hash with seed 1. The campus runner passes `--riskDropSeed = <seed>`, so for seeds 2 and 3
the checker compared against the wrong reference. The simulation outputs were not at fault.

Fix: P3 now takes the hash seed from the run's `risk_summary.csv` (`risk_drop_seed`) and also requires it to equal
`--riskDropSeed` in the run's recorded argv. No simulation was re-run; no raw output was changed. The first-pass
analysis directory was kept as `analysis-gate1-failed/` inside the batch.

### 5.3 Matrix gate, second pass: passed
`matrix/analyze_out/CHECKS.txt`: **108 runs; 1542 passed, 0 failed** (the same 1502 checks plus the 40 corrected).

| Check | Result |
|---|---|
| P0 exit 0, empty stderr, all files present, binary hash | 108 / 108 |
| P1 packet accounting (path records = app tx, fates partition, delivered + duplicates = sink rx, FlowMonitor ≤ sink) | 108 / 108 each |
| P2 high-risk set = reference model; hop and degree = reference; same set across protocols and rates | 108, 108, 18 / 18 |
| P3 every risk drop valid (run's own seed) | 108 / 108 |
| P4 Static / Risk-Aware delivered packets followed the installed path; installed path = reference tree; Risk-Aware k = 0 paths = Static k = 0 | 72, 72, 6 / 6 |
| P5 identical first-send times, one send count per source, sends ≤ nominal | 6, 6, 108 |
| P6 unicast data sent as HE_SU HeMcs0 | 108 / 108 |
| P7 simulator coordinates = positions file | 108 / 108 |
| R1 Static routes = k = 0 Static routes | 30 / 30 |
| R2 Risk-Aware no exposure without unavoidable sources | 36 / 36 |
| R3 risk_summary key_missing = 0, preregistered ids | 108 / 108 |

The metrics table `pilot_runs.csv` is byte-identical between the two passes (the fix changed only the check).
Re-checking the pilot with the corrected checker: 88 passed, 0 failed.

### 5.4 Independent recheck of risk drops
`experiments/campus-sim/verify_risk_drops.py` (separate code path from the gate): matrix 108 runs, 368,420 drops,
0 violations (`matrix/VERIFY_RISK_DROPS.txt`); pilot 6 runs, 16,629 drops, 0 violations. Every run's argv, run id and
`risk_summary.csv` agree on the seed; no k = 0 run has a drop.

### 5.5 Determinism (pilot vs matrix)
The 6 pilot configurations were run again inside the matrix. All 14 simulator output files per run have identical
sha256, the metric rows are identical, and provenance differs only in `--outDir` and the timing fields
(`matrix/DETERMINISM_PILOT_VS_MATRIX.txt`).

### 5.6 Dashboard build cross-checks
`experiments/campus-sim/build_site_campus_sim.py` stops on any failure: CHECKS has 0 failed; every run's coordinates
equal the positions file within 0.001 m; the reconstructed 90 m link model reproduces the simulator's degree for every
node in every run; each Static / Risk-Aware installed tree equals the reference model; every by-protocol mean is
recomputed from the run table. All passed.

## 6. Results (k = 3, mean [95 % t interval] over 15 matched draws)

| Rate | Protocol | Nominal PDR (%) | Exposure (%) | p95 delay (ms) | Hops (delivered) | Gateway airtime |
|---|---|---|---|---|---|---|
| 8 kbps | Static | 92.13 [85.50, 98.76] | 13.73 [2.74, 24.73] | 126 | 3.11 | 0.153 |
| 8 kbps | Risk-Aware | 99.99 [99.99, 100.00] | 0.00 (15/15 draws zero) | 133 | 3.20 | 0.162 |
| 8 kbps | OLSR | 97.32 [95.94, 98.70] | 5.17 [2.46, 7.88] | 185 | 2.45 | 0.205 |
| 32 kbps | Static | 90.16 [84.16, 96.17] | 13.73 [2.74, 24.72] | 384 | 3.10 | 0.610 |
| 32 kbps | Risk-Aware | 96.05 [95.53, 96.58] | 0.00 (15/15 draws zero) | 485 | 3.17 | 0.638 |
| 32 kbps | OLSR | 67.05 [66.18, 67.92] | 7.09 [4.27, 9.92] | 681 | 2.55 | 0.627 |

No risk (k = 0, 3 seeds): 8 kbps Static = Risk-Aware 100.00 %, OLSR 99.92 %; 32 kbps Static = Risk-Aware 95.33 %,
OLSR 68.02 %.

### Primary comparisons (A − B; draw-level 95 % interval; placement-level interval; Holm p)

| Rate | Comparison | Nominal PDR (pp) | Class | Exposure (pp) | Class |
|---|---|---|---|---|---|
| 8 | Risk-Aware − Static | +7.86 [+1.23, +14.49]; plc [−8.19, +23.92]; 15/15; 7.3e-4 | supported | −13.73 [−24.73, −2.74]; plc [−40.36, +12.89]; 15/15; 7.3e-4 | supported |
| 8 | Risk-Aware − OLSR | +2.67 [+1.29, +4.06]; plc [−0.60, +5.95]; 15/15; 7.3e-4 | supported | −5.17 [−7.88, −2.46]; plc [−11.60, +1.26]; 15/15; 7.3e-4 | supported |
| 8 | Static − OLSR | −5.19 [−10.53, +0.15]; 4 vs 11; 0.11 | descriptive | +8.57 [+0.08, +17.06]; 11 vs 4; 0.11 | descriptive |
| 32 | Risk-Aware − Static | +5.89 [−0.55, +12.33]; 9 vs 6; 0.11 | descriptive | −13.73 [−24.72, −2.74]; plc [−40.35, +12.89]; 15/15; 7.3e-4 | supported |
| 32 | Risk-Aware − OLSR | +29.00 [+27.64, +30.36]; plc [+25.78, +32.22]; 15/15; 7.3e-4 | supported | −7.09 [−9.92, −4.27]; plc [−13.90, −0.29]; 15/15; 7.3e-4 | supported |
| 32 | Static − OLSR | +23.11 [+17.85, +28.37]; plc [+10.39, +35.83]; 15/15; 7.3e-4 | supported | +6.64 [−1.81, +15.09]; 9 vs 6; 0.20 | descriptive |

Full tables: `matrix/stats/` (`paired.csv` includes every secondary metric and the per-draw differences).

### Per placement (mean of 3 seeds, 8 kbps): PDR % / exposure %

| Placement | High-risk | Static | Risk-Aware | OLSR |
|---|---|---|---|---|
| subtree | 1, 2, 4 | 69.13 / 51.81 | 100.00 / 0.00 | 92.68 / 14.29 |
| u101 | 16, 25, 44 | 98.18 / 3.61 | 99.99 / 0.00 | 98.97 / 1.89 |
| u102 | 35, 42, 76 | 95.77 / 8.43 | 99.99 / 0.00 | 98.90 / 2.11 |
| u103 | 39, 53, 55 | 99.40 / 1.20 | 100.00 / 0.00 | 97.89 / 4.08 |
| u104 | 5, 19, 47 | 98.18 / 3.61 | 100.00 / 0.00 | 98.16 / 3.48 |

At 32 kbps the uniform placements give Static 94.60–95.90 %, Risk-Aware 94.85–96.34 % and OLSR 66.53–68.41 % PDR.

## 7. Interpretation (within this simulation only)

1. **Risk-Aware had zero exposure in all 30 k = 3 draws** (both rates), as the oracle-knowledge design implies on a
   connected topology. The differences from Static and OLSR are supported by the pre-set criteria.
2. **The size of the Risk-Aware − Static difference depends on the placement.** Most of it comes from the subtree
   placement (Static exposure 51.8 %, PDR 69 %); with uniform placements Static exposure was 1.2–8.4 % and its PDR
   95.8–99.4 % at 8 kbps. The placement-level intervals (n = 5) for Risk-Aware − Static include 0. The mean over the
   5 placements is therefore not a property of the campus; it depends on the placement mix chosen.
3. **At 32 kbps Risk-Aware and Static PDR are close in the uniform placements** (sign varies by placement); the overall
   difference is descriptive.
4. **OLSR at 32 kbps lost about a third of packets with or without risk** (67.05 % with k = 3, 68.02 % with k = 0),
   while Static and Risk-Aware stayed near 95–96 %. This is a load effect in this model (OLSR also had about 80 and
   135 more MAC retry drops per run than the other protocols at 8 and 32 kbps). Its mechanism was not investigated here.
5. **OLSR's delivered packets used fewer hops** (2.45–2.55 vs 3.1–3.2) and its p95 delay was higher. Hop and delay
   metrics cover delivered packets only and are descriptive. OLSR can use links longer than 90 m; the 90 m disk is only
   the Static/Risk-Aware link model.
6. The campus layout is deeper than the generic fields (up to 7 hops under the 90 m model vs 2–3).

## 8. Limitations

- **Not calibrated.** No campus RSSI, loss or traffic data exist. The open-space log-distance model is the one used in
  the validated generic study.
- **No buildings.** 60 % of the 90 m links cross a building footprint; walls are not modelled, so link quality is likely
  optimistic. OSM gives footprints for 33 buildings but heights for only 6 and no materials; ns-3 buildings are
  axis-aligned boxes, so footprints could not be represented faithfully.
- **One layout, one gateway site.** Seeds vary only ns-3 random streams and the risk-drop hash; results do not
  generalise to other layouts, gateway sites or densities.
- **Placement-dependent effects.** Five placements (one deliberately adversarial for Static) are not a random sample of
  campus risk; the aggregate effect sizes depend on that choice.
- **Stress traffic.** Constant 512-byte UDP at 8 or 32 kbps per sensor is far above typical sensing traffic.
- **Risk model assumptions** as in the generic study: oracle risk knowledge for Risk-Aware, transit-only drops with
  p = 0.5, gateway never risky, flat terrain, static nodes.
- **Libraries rebuilt** (section 3); shown to be functionally equivalent on three validated configurations, not on
  every validated configuration.

## 9. Runtime and disk

- Matrix: 2026-10-26 16:14–21:31 (+07:00), 6 parallel jobs on an 8-CPU Mac; 24.81 run-hours in total.
  Mean wall time per run (min): Static 3.2 (8 kbps) / 19.5 (32 kbps); Risk-Aware 3.3 / 24.6; OLSR 6.4 / 25.7.
- Disk: matrix batch 820 MB, pilot 18 MB. Free space after the run: about 9.7 GiB.

## 10. Reproduce

```
python3 -I -B experiments/campus-sim/make_positions.py
python3 -I -B experiments/campus-sim/run_campus.py --phase=pilot
python3 -I -B experiments/campus-sim/run_campus.py --phase=matrix --jobs=6
python3 -I -B experiments/campus-sim/analyze_campus.py <batch>
python3 -I -B experiments/campus-sim/verify_risk_drops.py <batch>
python3 -I -B experiments/campus-sim/analyze_campus_stats.py <batch>
python3 -I -B experiments/campus-sim/build_site_campus_sim.py <batch> <site dir>
```

The runner checks the source, binary and positions hashes before launching and refuses to start below 2.0 GiB free.
