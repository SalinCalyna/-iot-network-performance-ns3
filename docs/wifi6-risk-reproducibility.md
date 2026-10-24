# Wi-Fi 6 Risk-Aware Routing — reproducibility package

This package lets the published Wi-Fi 6 risk-study results be audited and partly regenerated. It
contains the exact validated simulator source, the experiment and analysis scripts, the batch
manifests, the per-batch analysis outputs, and the report tables and figures. The raw per-run
simulation outputs (8,783 files, 1.597 GB) are **not** in Git. They are listed file by file, with
size and sha256, in `results/wifi6-risk/RAW_MANIFEST.csv`. Results summary:
[README § Wi-Fi 6 Risk-Aware Routing](../README.md#wi-fi-6-risk-aware-routing-completed-2026-10);
live dashboard: https://salincalyna.github.io/-iot-network-performance-ns3/site/index.html

## Simulator

| Item | Value |
|---|---|
| Source | `scratch/iot-network-wifi6-risk-v2.cc` (committed unmodified) |
| Source sha256 | `33b350ab5f790d7347fbd81b3b010a1d455af73ebd0a28ce187eca7e0633311b` |
| Validated binary sha256 | `d909f6de6233dfad80700b37beb71d4a62c2cd38f223b6acc70cbb40f1bb2407` (`build/scratch/ns3-dev-iot-network-wifi6-risk-v2-default`) |
| ns-3 base | upstream ns-3-dev commit `0740177d4` (2026-03-10, "build: Add extra presets"); **no change to `src/` or `contrib/`** |
| ns-3 tooling patch | one line in the `ns3` wrapper: `cmake_presets[0]["environment"]` → `cmake_presets[0].get("environment", {})` (preset loading only; does not affect simulation) |
| Toolchain used | Apple clang 16.0.0, CMake 4.2.3, ns-3 `default` build profile, macOS 26.3.1 |

Build, from the root of an ns-3-dev checkout at the commit above:

```bash
cp scratch/iot-network-wifi6-risk-v2.cc <ns-3-dev>/scratch/
cd <ns-3-dev>
./ns3 configure --build-profile=default
./ns3 build iot-network-wifi6-risk-v2
```

The run scripts refuse to start (`STOP: risk-v2 binary or source differs from the validated
version`) unless both the source and binary sha256 match the validated values. A binary built
with another compiler or ns-3 revision gets a different hash. Re-simulating on another machine
therefore needs the same toolchain, or a deliberate, documented change to the `EXPECT_BIN` check
in `run_pilot_n30.py`. This package does not make that change.

## Package contents

| Path | Contents |
|---|---|
| `scratch/iot-network-wifi6-risk-v2.cc` | adopted simulator (risk-v2: risk model, Risk-Aware routing, per-packet traces, Block Ack SSN fix `--baSsnFix`) |
| `experiments/wifi6-risk/` | `risk_ref.py`, `test_offline.py` (reference model), `run_validation.py`, runners (`run_pilot_n30.py`, `run_seeds10_n30.py`, `run_n100_8k.py`, `run_lowload_smoke.py`, `run_aodv_diag.py`), analysis (`analyze_pilot_n30.py`, `analyze_paired_stats.py`, `analyze_lowload_smoke.py`, `aodv_log_counter.py`), report/dashboard (`make_report_outputs.py`, `build_site_wifi6.py`, `verify_site_wifi6.py`), `README.md` |
| `analysis/wifi6-risk-writeup/` | report tables T-W1–T-W7 (CSV + `TABLES.md`), figures F-W1–F-W8 (PDF + PNG, `FIGURES.md`), `N100_AODV_SECTION.md`, `INVENTORY.md`, `inventory.json` (input file hashes) |
| `results/wifi6-risk/seeds10-n30-8k-v2-20261024T160515/` | N = 30, 8 kbps, seeds 20–29: `batch.json`, `reuse_manifest.json`, `README.md`, `analysis/` (checks, per-run table, statistics) |
| `results/wifi6-risk/n100-8k-v2-20261024T165009/` | N = 100, 8 kbps, seeds 20–22: `batch.json`, `README.md`, `analysis/` |
| `results/wifi6-risk/pilot-n30-v2-20261024T054949/` | N = 30 pilot (8 and 64 kbps, seeds 20–22): manifest, README, analysis |
| `results/wifi6-risk/lowload-smoke-v2-20261024T041410/` | N = 100 OLSR load calibration (4/8/16 kbps): manifest, README, run tables |
| `results/wifi6-risk/aodv-diag-n100-20261024T204129/` | AODV diagnostic (Block Ack fix off/on, seed 20): README, manifests, analysis, AODV event counts and provenance |
| `results/wifi6-risk/diag-tail-20261022/README.md` | Block Ack residual-tail diagnosis (cases A–D) |
| `results/wifi6-risk/v4-tail-check-20261023T222251/` | `batch.json` and the v2/v3/v4 comparison CSVs (source of T-W2b) |
| `results/wifi6-risk/validation-v2-20261021T181501/` | risk-v2 validation summary, all 6,206 checks, provenance |
| `results/wifi6-risk/RAW_MANIFEST.csv` | every raw file kept outside Git: path, bytes, sha256 |

Manifest and provenance JSON files are committed verbatim. They contain the absolute paths of
the machine that ran the experiments (`/Users/pinpuk/ns-3-dev/...`); these paths are also present
in earlier committed records of this repository.

## What can be reproduced, and from what

| Level | Needs | Steps | Verified on 2026-10-25 |
|---|---|---|---|
| 1 — package only | Python 3 standard library | `python3 -I -B experiments/wifi6-risk/test_offline.py` | 143,908 checks passed |
| 1 | — | `analyze_paired_stats.py results/wifi6-risk/seeds10-n30-8k-v2-20261024T160515 --rate=8` and `… n100-8k-v2-20261024T165009 --rate=8 --descriptive` | `STATS.txt` and `stats_by_config.csv` byte-identical for both batches. N = 100 `paired_riskaware_vs_static.csv` byte-identical. N = 30 paired file: all 44 rows equal in every original column; the current script adds a `per_seed_diff` column written after that file was produced |
| 1 | — | `build_site_wifi6.py <site dir>` | `site/data/wifi6-risk.json` and all 8 figures byte-identical to the deployed dashboard |
| 1 | a rendered dashboard DOM | `verify_site_wifi6.py <site> <dom.html> <base index.html>` | 12/12 checks passed against the live dashboard |
| 2 — raw archive | raw outputs restored at the paths in `RAW_MANIFEST.csv` | `analyze_pilot_n30.py <batch>` (run-level checks); `make_report_outputs.py` (all tables/figures; also needs matplotlib 3.10.8, numpy 2.4.4) | both fail cleanly without the archive (`FileNotFoundError`). With the raw outputs in place, `make_report_outputs.py` regenerated byte-identical tables and figures twice (2026-10-25) |
| 3 — re-simulation | built simulator (see above) | runner scripts (`run_*.py`) | not re-run for this package (no new simulations); output determinism was checked during the study (byte-identical reruns) |

## External dependencies not included

- **`run_validation.py` regression tests (T1, T2, T10)** compare against the parent simulator
  `scratch/iot-network-wifi-std-arp.cc` and risk-v1 (`scratch/iot-network-wifi6-risk.cc`). Neither
  is part of this package, so the full validation cannot be re-run from it. Its recorded result
  (`validation-v2-20261021T181501`: 6,206 passed, 0 failed) is included. `analyze_pilot_n30.py`
  imports `run_validation.py` only for the position replica and needs no other simulator.
- **Not adopted, not included:** risk-v3 and risk-v4 (Block Ack variants), the diagnostic timeline
  simulators, and their scripts (`run_v3_tail_check.py`, `run_v4_tail_check.py`,
  `analyze_v3_tail_check.py`, `analyze_v4_compare.py`, `run_saturation_smoke.py`,
  `analyze_saturation_smoke.py`). Their recorded outputs used in the report (the v2/v3/v4
  comparison CSVs and the diagnosis README) are included as data. The raw runs are listed in
  `RAW_MANIFEST.csv`.

## Raw outputs: proposed archive (not uploaded)

- **Proposed location:** Zenodo, one versioned record with a DOI, linked from this repository and
  the thesis. Upload one `tar.zst` archive per batch directory of `results/wifi6-risk/` (largest
  about 0.5 GB before compression), together with `RAW_MANIFEST.csv`.
  - Integrity: after download, every file can be checked against its sha256.
  - Alternatives: GitHub Release assets (2 GB per file, no DOI) or the university's institutional
    repository.
- **Not chosen:** Git LFS, because the free quota is too small for 1.6 GB and the files never
  change.
- **Status:** nothing has been uploaded or published; this needs separate approval.
