# risk-v1: Low/High-risk relay nodes and risk-aware routing in the Wi-Fi mesh

> **Current status (2026-10-25):** the study is complete and validated. The adopted simulator is
> **risk-v2** (`scratch/iot-network-wifi6-risk-v2.cc`, source sha256 `33b350ab…`; see "Version for
> the research pilot" below). Results: N = 30 (seeds 20–29, 160 runs) and N = 100 (seeds 20–22,
> 48 runs). The status lines directly below are the original 2026-10-21 risk-v1 notes, kept as
> history. Reproduction guide: `docs/wifi6-risk-reproducibility.md`.

Status (2026-10-21): **source written and syntax-checked, not built, not run.** The build is blocked: the disk
has about 0.2 GB free and the ns-3 library rebuild that a CMake reconfigure started on 2026-10-21 stopped
half-way. No simulation result exists for this program yet.

## Files
| File | Role |
|---|---|
| `scratch/iot-network-wifi6-risk.cc` | new simulator (copy of `iot-network-wifi-std-uid.cc` + `--riskStudy`) |
| `experiments/wifi6-risk/risk_ref.py` | independent Python reference: disk graph, BFS, relay ranking, risk-aware Dijkstra, safe paths, drop hash |
| `experiments/wifi6-risk/test_offline.py` | offline property tests of the reference (no simulator) |
| `experiments/wifi6-risk/run_validation.py` | small deterministic simulator validation, checks T0–T9 |

No existing source, result or baseline is modified. `iot-network-wifi-std-arp.cc` (the active simulator,
802.11b and 802.11ax with the ARP fix), `iot-network-v3-ext.cc` (frozen V3/V4) and all results stay as they are.

## Lineage
`iot-network-bottleneck-probe.cc` → `iot-network-wifi-std.cc` (standard selectable) →
`iot-network-wifi-std-arp.cc` (ARP fix) → `iot-network-wifi-std-uid.cc` (per-packet accounting, unbuilt) →
`iot-network-wifi6-risk.cc` (this). With `--riskStudy=0` the new program connects, installs and writes nothing
new, so its outputs must equal the parent's for the same arguments (test T1).

## Model (assumptions pending advisor approval)
- **States.** Every sensor is `LOW_RISK` or `HIGH_RISK`; the gateway is never risky. State → risk score `r`:
  `--lowRiskDropProb` (default 0), `--highRiskDropProb` (default 0.5). `r` is the probability that the node
  loses a transit application data packet. A node's own packets, control, ARP and broadcast frames are never
  affected.
- **Assignment** (`--numHighRisk` 0–3). Candidates are reachable sensors that relay for at least one other
  sensor in the BFS tree on the 90 m disk graph. Rules (`--riskSelect`):
  - `subtree` (default): most BFS descendants, then degree, then lower id;
  - `degree`: degree, then descendants, then id;
  - `random`: SplitMix64 hash of `--riskSelectSeed`, then id;
  - `ids`: `--highRiskIds=a,b,c`.

  The sets are nested across k. They depend only on positions, so they are the same under every protocol.
- **Risk drop.** `RiskDropFilter` is an `Ipv4RoutingProtocol` at list priority 1000, installed only on nodes
  with `r > 0`. It drops a packet iff `U < r`, where `U = SplitMix64-hash(--riskDropSeed, node, src, seq)` and
  `(src, seq)` is the application packet number. The same packet at the same node gets the same decision under
  every protocol, and no ns-3 random stream is used.
- **Routing.** `aodv`, `olsr` and `static` are unchanged. `--protocol=riskaware` is new: an offline Dijkstra
  tree toward the gateway in which entering transit node v costs `1 + riskBeta·(−ln(1 − r_v))`
  (`--riskBeta`, default 10). It is installed as static host routes. Ties reproduce the BFS tree, so with no
  risk it equals `static`. Routing knows the states perfectly, which makes its benefit an upper bound.
- **Mobility:** static only (inherited); offline routes would not follow moving nodes.

## Outputs (`--riskStudy=1`)
| File | Contents |
|---|---|
| `risk_nodes.csv` | per node: hop, degree, BFS descendants, candidate rank, state, risk score, eligible / dropped / passed transit packets |
| `routes_planned.csv` | per source: installed path, hops, risk cost and high-risk transits, plus the BFS and riskaware paths and a safe-path flag |
| `path_summary.csv` | observed paths per source with packet fates |
| `packet_paths.csv` | one row per data packet; only with `--perPacketTrace=1` |
| `risk_drops.csv` | every risk drop (node, src, seq, uid, time, U) |
| `risk_summary.csv` | run-level PDR, risk loss share, exposure rate, high-risk transits per packet, sources exposed / avoided / unavoidable, mean installed cost and hops, path-following check |
| `wifi_readback.csv` | standard, band, channel, width, HE configuration and GI, data/control mode and A-MPDU/A-MSDU limits, read back from every device |
| `wifi_txvector_counts.csv` | transmitted PSDUs counted by frame class × preamble × modulation × mode × width × GI |

## Tests
`python3 -I -B experiments/wifi6-risk/test_offline.py`: reference-model properties. Ran on 2026-10-21:
143,908 checks passed, 0 failed.

`python3 -I -B experiments/wifi6-risk/run_validation.py` (after the build): 4 regression runs × 3 binaries/modes
plus 20 risk runs (N = 30, seed 20, 100 s). It writes `results/wifi6-risk/validation-<time>/`.

| Test | Checks |
|---|---|
| T0 | every run exits 0 with empty stderr |
| T1 | regression: parent binary and new binary with `--riskStudy=0` reproduce 4 stored runs byte for byte; no new files |
| T2 | passivity: `--riskStudy=1` with 0 high-risk nodes leaves all original outputs identical |
| T3 | risk assignment equals the reference; correct count; nested; same under every protocol and standard; gateway never risky |
| T4 | BFS and riskaware paths and costs equal the reference (1e-9); safe-path flags; riskaware with k = 0 equals the BFS tree |
| T5 | reachability equals BFS; installed path equals the protocol's tree |
| T6 | each drop is at a node with r > 0, is reproduced by the reference hash, is never the node's own packet, and gets the same U across protocols; per-node rate lies in the 99.9% Wilson interval; no drops where r = 0 |
| T7 | path records = app tx; delivered + duplicates = sink rx (FlowMonitor rx reported); fates partition the packets; exposure recomputed; every delivered static/riskaware packet followed the installed path |
| T8 | identical positions and per-source send schedules across all runs; positions equal the reference mt19937 replica; riskaware k = 0 equals static; a repeat run is byte-identical |
| T9 | 802.11ax: every device reads back 802.11ax, 2.4 GHz channel 1, 20 MHz, HE configuration, GI 800 ns, HeMcs0, ERP-OFDM 6 Mbps control, A-MPDU/A-MSDU 0; unicast data PSDUs HE_SU/HE/HeMcs0; 802.11b: DSSS 1 Mbps |

## Before running
1. Free at least 5 GB of disk space.
2. `cmake --build cmake-cache -j 7 --target scratch_iot-network-wifi6-risk scratch_iot-network-wifi-std-arp` (finishes the interrupted library rebuild).
3. `python3 -I -B experiments/wifi6-risk/run_validation.py`.

## risk-v2 (2026-10-21): Block Ack SSN fix
`scratch/iot-network-wifi6-risk-v2.cc` = risk-v1 + `--baSsnFix` (default true; `--baSsnFix=0` is byte-identical to
risk-v1). Investigation: `results/wifi6-risk/diag-delay-20261021/` (diagnostic program
`scratch/iot-network-wifi6-risk-diag.cc`, read-only timeline; it leaves every output byte-identical).

**Root cause (confirmed by trace and ns-3 source):**
- ns-3 sets up Block Ack for every VHT/HE pair (`ht-frame-exchange-manager.cc:131-136`).
- The ADDBA Request advertises SSN 0.
- MPDU 0 is discarded at the retry limit while the handshake is in NO_REPLY state.
- `QosTxop::GotAddBaResponse` (`qos-txop.cc:700-707`) then starts the originator window at 1, but the recipient
  window stays at 0, and no BlockAckReq is sent.
- The recipient therefore holds every later MPDU until SN 256 (the HE buffer size) arrives: about 65 s at 3.9 pkt/s.

**Fix:** when an originator agreement is established with a start different from the advertised SSN, send a
BlockAckReq through the public API (`PrepareBlockAckRequest` + `ScheduleBar`). Every fix event is logged in
`ba_ssn_fix.csv`.

**Validation** `results/wifi6-risk/validation-v2-20261021T181501/`: 6,206 checks passed, 0 failed (T0–T10).

## risk-v3 (2026-10-22): Block Ack re-establishment fix (partial)
`scratch/iot-network-wifi6-risk-v3.cc` = risk-v2 + `--baReestFix` (default true; `--baReestFix=0` is byte-identical to
risk-v2). On every received ADDBA Response for an agreement that is already ESTABLISHED it checks, 1 ms later,
whether the originator's start differs from the advertised SSN and, if so, sends a BAR (`ba_reest_fix.csv`).
Hooking MonitorSnifferRx makes ns-3 build one Packet per A-MPDU subframe, so packet UIDs are relabelled (all
other outputs identical when no BAR is sent).

Validation `results/wifi6-risk/validation-v3-20261022T133856/` (`run_validation.py --version=v3`): 6,322 passed,
2 failed (UID relabelling only; `check_t11_uid_relabel.py` passes). Saturation check `run_v3_tail_check.py` →
`results/wifi6-risk/v3-tail-check-20261022T133856/` (`analyze_v3_tail_check.py`): the confirmed v2 case is fixed,
but 22–36 packets per run are still delayed > 10 s. Diagnosis of all cases: `results/wifi6-risk/diag-tail-20261022/README.md`.
**Not for experiments yet**: two further mechanisms (stale ADDBA Response; BAR deferred until data is queued) are open.

## risk-v4 (2026-10-23, EXPERIMENTAL, not adopted)
`scratch/iot-network-wifi6-risk-v4.cc` = risk-v3 + `--baAddbaBar`: one BAR after every received ADDBA Response.
Validation `validation-v4-20261023T222251` 6,354/0; matched N=100 comparison in
`results/wifi6-risk/diag-tail-20261022/README.md`. It did not reduce the > 10 s tail consistently against risk-v2
(2 of 3 seeds), so it is kept only as a diagnostic record.

## Version for the research pilot: risk-v2
risk-v2 fixes one confirmed, deterministic ns-3 defect (65 s delays at N = 30, T10 validated) with one BAR per
mismatch event. Known limitation at saturation (N = 100, ≥ 64 kbps): 0.013–0.037 % of delivered packets are held
> 10 s in a Block Ack reorder buffer (diag-tail-20261022 cases A–D; ns-3 has no recipient reorder timeout and
defers a failed BAR until data is queued). Report sink-based PDR and delay percentiles (p50/p95/p99); report max
delay only with this caveat; FlowMonitor rx undercounts by up to 45 packets per run (≤ 0.04 %). Delayed packets are
not filtered and MaxPerHopDelay is left at its default.
