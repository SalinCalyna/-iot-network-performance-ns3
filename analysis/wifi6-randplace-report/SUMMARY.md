# N = 100 uniform random risk placement: results summary

Date: 2026-10-26. Batch: `results/wifi6-risk/n100-randplace-v2-20261026T032146` (72 new runs + 18 reused k = 0 runs).
Design and hypotheses were fixed before the run in `analysis/wifi6-n100-sat-report/PROPOSAL_random_placement.md` (revision 2).

## 1. Provenance and integrity

| item | value |
|---|---|
| simulator source | `scratch/iot-network-wifi6-risk-v2.cc`, sha256 `33b350ab…` (unchanged) |
| simulator binary | `build/scratch/ns3-dev-iot-network-wifi6-risk-v2-default`, sha256 `d909f6de…` (unchanged) |
| ns-3 libraries | 35/35 match `analysis/wifi6-n100-sat-report/SIMULATOR_LIBS.sha256` |
| earlier N = 100 dataset | 2,024/2,024 files match `DATASET_MANIFEST.sha256` |
| runner gates | subset 6 runs: 328 passed, 0 failed; final 90 runs: 1,197 passed, 0 failed (P0–P6, R1–R3) |
| analysis re-run | `analyze_out/` is byte-identical to the runner's `<batch>/analysis/` (CHECKS.txt, checks.csv, pilot_runs.csv, pilot_by_config.csv) |
| raw data | 1,229 raw batch files hashed before the analysis (`RAW_BEFORE.sha256`) and unchanged after it |

Grid: Static, Risk-Aware, OLSR × k = 3 × {8, 32} kbps × topology seeds {20, 21, 22} × placement seeds {101–104}.
A *draw* = (topology seed, placement seed): 12 per rate. Within a draw the three protocols share positions, traffic
schedule (P5) and the preregistered high-risk set (P2), so comparisons are paired per draw.

## 2. Statistical approach

- Per (protocol, rate): mean and 95 % t interval over 12 draws.
- Paired differences per draw: 95 % t interval (df = 11), exact sign-flip permutation test (4,096 patterns), exact
  Wilcoxon, per-topology mean differences, and a topology-level 95 % t interval (n = 3, df = 2).
- Holm adjustment over the primary family (exposure and nominal PDR × 3 comparisons × 2 rates).
- **Supported** = primary metric, Holm p < 0.05, draw-level interval excludes 0, and the same sign in all 3 topologies.
  **Consistent** = a secondary metric that meets the same criteria without Holm (exploratory). Everything else is **descriptive**.
  All delay metrics are descriptive because they are computed over delivered packets only (survivorship).
  These rules are written in the script header and were not changed after the results were seen.
- **Scope:** draws are nested in 3 topologies. Inference covers random placement within these topologies. With 3
  topologies, generalisation to other topologies is not established. Where the topology-level interval also
  excludes 0, this is noted.

## 3. Results (mean [95 % interval] over 12 draws)

| rate | protocol | exposure % (zero-exposure draws) | nominal PDR % | p95 delay ms | gateway airtime |
|---|---|---|---|---|---|
| 8 | Static | 1.83 [0.12, 3.54] (7/12, max 7) | 99.05 [98.2, 99.9] | 162 | 0.223 |
| 8 | Risk-Aware | 0 (12/12) | 99.95 [99.9, 100] | 162 | 0.224 |
| 8 | OLSR | 1.15 [0.92, 1.39] (0/12, max 1.76) | 99.02 [98.9, 99.2] | 281 | 0.397 |
| 32 | Static | 1.83 [0.12, 3.54] (7/12, max 7) | 71.99 [70.4, 73.6] | 493 | 0.754 |
| 32 | Risk-Aware | 0 (12/12) | 72.18 [70.4, 73.9] | 493 | 0.753 |
| 32 | OLSR | 2.29 [1.41, 3.16] (0/12, max 5.43) | 58.79 [57.7, 59.9] | 519 | 0.770 |

### Statistically supported (primary, Holm-adjusted)
1. **Risk-Aware has lower exposure than OLSR**: −1.15 pp [−1.39, −0.92] at 8 kbps and −2.29 pp [−3.16, −1.42] at 32 kbps.
   This holds in 12/12 draws (Holm p = 0.006), and the topology-level interval also excludes 0.
2. **Risk-Aware has higher nominal PDR than OLSR**: +0.94 pp [+0.79, +1.08] at 8 kbps and +13.4 pp [+10.7, +16.1] at 32 kbps.
   This holds in 12/12 draws (Holm p = 0.006), and the topology-level interval also excludes 0.
3. **Static has higher nominal PDR than OLSR at 32 kbps**: +13.2 pp [+10.6, +15.8], 12/12 draws (Holm p = 0.006), and the topology-level interval also excludes 0.

### Consistent (secondary, exploratory)
- Gateway congestion is lower with Static and Risk-Aware than with OLSR. At 8 kbps gateway airtime is 0.17 lower
  (0.22 vs 0.40). At 32 kbps it is 0.016 lower, with all three near saturation (≈ 0.75–0.77). MAC retry-limit drops
  are about 590 (8 kbps) and 1,135 (32 kbps) fewer per run than OLSR. Both hold in 12/12 draws.
- Risk-Aware has fewer risk drops than OLSR: 12/12 draws at both rates.

### Not supported or descriptive only
- **H2 (primary): Static vs OLSR exposure.** +0.68 pp [−1.09, +2.45] at 8 kbps and −0.45 pp [−2.18, +1.28] at 32 kbps.
  No difference is detected. The 37 pp gap seen under subtree placement does not appear, and the interval rules out
  differences larger than about 2.5 pp. The preregistered ±1 pp prediction can be neither confirmed nor rejected at this precision.
- **Static vs OLSR PDR at 8 kbps:** +0.03 pp [−0.84, +0.91]. No difference detected.
- **Risk-Aware vs Static:** the two are identical in the 7 draws where no risky node lies on the BFS tree, so the test
  rests on 5 non-zero draws. The smallest possible sign-flip p is then 0.0625, so this comparison cannot reach
  significance by design. Descriptively, in the 5 on-tree draws Risk-Aware removes all exposure (−4.4 pp, range
  −7.0 to −1.0) and gains +2.17 pp PDR at 8 kbps (range +0.47 to +3.45) but only +0.46 pp at 32 kbps (range −0.96 to
  +1.49). This is consistent with **H1** (a gain that is smaller at 32 kbps), but n = 5.
- **H4 (concentration):** Static exposure is zero in 7/12 draws and reaches up to 7 % in the rest. OLSR exposure is
  non-zero in 12/12 draws but small (≤ 1.76 % at 8 kbps, ≤ 5.43 % at 32 kbps). The pattern matches H4 (descriptive).
- **Delay:** OLSR's p95 delay is about 120 ms higher at 8 kbps and about 26 ms higher at 32 kbps in 12/12 draws.
  Descriptive only (survivorship).
- **Cost of risk vs k = 0:** k = 3 lowers nominal PDR by 0.90 pp (Static), 0.01 pp (Risk-Aware) and 0.61 pp (OLSR)
  at 8 kbps, and by 0.17, +0.03 and 0.80 pp at 32 kbps (`stats/k0_cost.csv`).
- **Subtree vs uniform placement** (same seeds, k = 3): Static exposure goes from 39.3 % to 1.83 % and Static PDR at
  8 kbps from 80.3 % to 99.05 %. OLSR changes little (1.5 → 1.15 % at 8 kbps; 4.9 → 2.3 % at 32 kbps). The earlier
  large Static penalty was a property of the subtree placement, which puts risk on Static's backbone.

**Interpretation:** under protocol-independent placement, Static and OLSR are about equally exposed. Risk-Aware's
exposure advantage is significant against OLSR in every draw, but against Static it appears only when a risky node
sits on the static tree. The large PDR advantage of tree routing (Static and Risk-Aware) over OLSR at 32 kbps comes
from congestion (gateway airtime, MAC retries), not from risk.

Not done (listed in the proposal): an independent recomputation (`verify_n100_sat.py`-style) of this batch, and the
comparison of trace-predicted with measured exposure.

## 4. Reproduce

```sh
cd ~/ns-3-dev
B=results/wifi6-risk/n100-randplace-v2-20261026T032146
python3 -I -B experiments/wifi6-risk/analyze_randplace.py $B --out=analysis/wifi6-randplace-report/analyze_out
python3 -I -B experiments/wifi6-risk/analyze_randplace_stats.py analysis/wifi6-randplace-report/analyze_out/pilot_runs.csv \
  --out=analysis/wifi6-randplace-report/stats \
  --subtree8=results/wifi6-risk/n100-8k-v2-20261024T165009/analysis/pilot_runs.csv \
  --subtree32=results/wifi6-risk/n100-sat-v2-20261025T112146/analysis/pilot_runs.csv
```
Python 3.14.3, standard library only. Script sha256 values: analyze_randplace.py `4a2f8a14…`,
analyze_randplace_stats.py `5d10a2c0…`, analyze_paired_stats.py `4534ec87…` (helpers, unchanged),
run_n100_randplace.py `eaabecf7…`, risk_ref.py `a50d67ce…`, run_validation.py `e8597cfb…`.

Outputs: `analyze_out/` (checks and per-run metrics) and `stats/` (stats_by_protocol.csv, paired_differences.csv,
conditional_on_tree.csv, k0_cost.csv, subtree_compare.csv, STATS.txt).

## 5. Backup plan for the new batch (not yet written)

The existing iCloud backup `ns3-backups/wifi6-risk-backup-20261025T225734/` predates this batch. iCloud has
**446 MB** of quota left, and a full repeat of `backup_wifi6_risk.py` (≈ 0.75 GB tar.gz, since it re-archives all of
`results/wifi6-risk`) would not fit. Proposed **incremental** backup:

- Contents (1,246 files plus 3 scripts): the new batch, its console log, this report folder,
  `run_n100_randplace.py`, `analyze_randplace.py` and `analyze_randplace_stats.py`. The 18 reused k = 0 runs and the
  simulator are already in the 2026-10-25 backup (the k = 0 runs are covered by DATASET_MANIFEST, verified today).
- Measured size: **163 MiB** tar.gz (0.59 GiB raw). Local disk needed: about 0.17 GiB while iCloud uploads.
  iCloud quota left afterwards: about 280 MB.
- Steps (same procedure as `backup_wifi6_risk.py`): pre-check hashes → FILES.sha256 → `x:gz` archive, never
  overwriting → re-read every member and compare hashes → archive sha256. Destination
  `iCloud Drive/ns3-backups/wifi6-risk-randplace-<timestamp>/`.
- This needs either a `--roots`/incremental option in `backup_wifi6_risk.py` or a small separate script. Neither is
  written yet; both wait for approval.
