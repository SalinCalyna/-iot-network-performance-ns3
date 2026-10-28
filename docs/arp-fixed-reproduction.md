# Reproducing the ARP-fixed IEEE 802.11b results

The ARP-fixed runs are the primary 802.11b evidence of the thesis *Analysis of Gateway-Centric IoT Wireless Mesh
Networks Using NS-3* (under advisor review). This guide rebuilds the simulator from upstream NS-3, re-runs any
recorded run, and regenerates the tables. **No fork of NS-3 and no project git history is needed.**

## 1. Simulator

| Item | Value |
|---|---|
| Source | `scratch/iot-network-wifi-std-arp.cc` (single file; NS-3 modules only), sha256 `4923685a52f9f8131caff2ecc45a806620c649bc621c82da…` (full hash in `publication/MANIFEST.sha256`) |
| NS-3 base | upstream `ns-3-dev` commit **`0740177d456a8e298a9db843ebb5e7d52ea103a5`** (`ns-3.47-21-g0740177d4`, 2026-03-10). The project made **no change to `src/`** |
| Build tool | one-line local fix in the top-level `ns3` script (`cmake_presets[0].get("environment", {})` instead of `["environment"]`), provided as [`docs/patches/ns3-preset-environment.patch`](patches/ns3-preset-environment.patch). It is needed only if your CMake presets lack an `environment` key; it does not affect simulation |
| Build profile | NS-3 `default`; Apple clang on macOS (Apple Silicon) |
| Recorded binary | every run's `provenance.json` records the binary sha256 (`9f74bd9c…`). A later rebuild has a different binary hash but reproduced a recorded run byte for byte (validation audit, 2026-10-28) |

```sh
git clone https://gitlab.com/nsnam/ns-3-dev.git && cd ns-3-dev
git checkout 0740177d456a8e298a9db843ebb5e7d52ea103a5
git apply <this repository>/docs/patches/ns3-preset-environment.patch   # only if ./ns3 fails on CMake presets
cp <this repository>/scratch/iot-network-wifi-std-arp.cc scratch/
./ns3 configure --build-profile=default && ./ns3 build scratch/iot-network-wifi-std-arp
```

## 2. Re-running a recorded run

Every run directory contains `provenance.json` with the exact command line (`argv`). To reproduce a run, replace
the binary path in `argv[0]` with your build and `--outDir` with a new directory. Example (ARP-fixed Static,
N = 20, 16 kbit/s, seed 20):

```sh
./build/scratch/ns3-dev-iot-network-wifi-std-arp-default --standard=80211b --protocol=static --nSensors=20 \
  --trafficLevel=high --seed=20 --offeredRateKbps=16 --arpPrepopulate=1 --outDir=/tmp/rerun
```

Compare `probe_aggregate.csv`, `wifistd_ext.csv` and the per-node files with
`results/wifi-std/arp-a2-on/b-on_static_20_high_seed20/`, ignoring the `timestamp` column.

Traffic levels: low = `--trafficLevel=high --offeredRateKbps=4`; medium = `--trafficLevel=medium` (8 kbit/s);
high = `--trafficLevel=high --offeredRateKbps=16`. Seeds 20–30 (high traffic) or 20, 25, 30 (low, medium, rate sweep).

Batches were run with `experiments/wifi-std/run_resumable.py` (batch names `arp-a2-on`, `arp-a1-on`, `arp-b-on-os`,
`arp-b1-on`, `arp-ratesweep-on`, `arp-phase1-on`, `arp-phase1-off`, `arp-r0-off`) through the `chain_*.sh` scripts.
`run_resumable.py` loads `experiments/wifi-std/run_wifi_std.py` at run time. The published `run_resumable.py` is
the version that defined and ran `arp-b1-on` (saved 2026-10-18 20:19; batch ran 20:20–20:48); it was not committed
in the original workspace before this publication.

## 3. Datasets

| Directory | Runs | Content |
|---|---|---|
| `results/wifi-std/arp-a2-on`, `arp-a1-on`, `arp-b-on-os` | 306 distinct (+18 identical duplicates) | AODV, OLSR, Static × N 10–100 × 3 loads, ARP pre-populated |
| + `arp-b1-on` | 176 bottleneck runs together with the above | OLSR, Static × N 30–100 × medium/high × 11 seeds |
| `arp-ratesweep-on` | 72 | OLSR, Static × N 50/75/100 × 4/8/12/16 kbit/s × seeds 20/25/30 |
| `arp-phase1-on`, `arp-phase1-off` | 14 + 14 | paired diagnostic, pre-population on/off |
| `arp-r0-off` | 15 | flag-off regression against the original Stage 1 outputs (0 differences; `README.md`) |

The original (frozen) datasets used for pairing (`results/v3-ext/`, `analysis/bottleneck-characterisation/`,
`analysis/final-report-data/`, `analysis/final-reproducibility-check/`) are already in this repository. They were
verified byte-identical to the files the analyses hashed.

## 4. Software dependencies

| Need | Version used | Notes |
|---|---|---|
| NS-3 | upstream commit `0740177d456a` | §1; its own build requirements (CMake, C++ compiler, Python 3) |
| C++ compiler | Apple clang 16.0.0 (present environment) | the version used for the original build was not recorded |
| Python | 3.14.3 (present environment) | analysis and verification scripts use the standard library only |
| matplotlib | 3.10.8 | only for the figures produced by the two analysis scripts (`requirements.txt` asks for ≥ 3.8) |

## 5. Regenerating the tables and checking the claims

```sh
python3 analysis/chapter4-tables-figures/build_ch4.py              # Tables 4.4-4.7, 4.11, 4.12, 4.17; Figures 4.1, 4.5, 4.6
python3 analysis/arp-fixed-throughput-delay/analyze_throughput_delay.py   # goodput and delay (Tables 4.8-4.10)
python3 publication/verify_published_claims.py                     # every number in the README 802.11b findings
python3 -I -B experiments/wifi-std/build_site_arp_fixed.py site      # dashboard data site/data/arp-fixed.json (cross-checked against raw runs)
python3 -I -B experiments/wifi-std/test_site_arp_fixed.py           # tests: rebuild, isolation, traceability, intervals, claims
```

Both analysis scripts stop on any provenance, coverage or consistency failure, and record the sha256 of every input
in `INPUTS.sha256`.

## 6. Known limits

- Static sensors only; no ARP-fixed mobility run exists.
- Low/medium traffic and the rate sweep have 3 seeds (descriptive).
- Delay is a mean over delivered packets.
- MAC frame-drop events are not lost packets.
- Static routes over a 90 m disk model. At N = 10 some sensors have no path on it, get no installed route and send
  directly to the gateway; Static's N = 10 PDR is associated with their number and should be interpreted with
  caution (claim C18).
- The exact build of the original (frozen) batches and the ~117 m two-node radio range are unverified.
- In `provenance.json` the original machine's repository root is replaced by the token `<NS3_ROOT>` (fields
  `argv[0]` and `cwd` only). The redaction is reversible; see `publication/PROVENANCE_PATHS.md`.
