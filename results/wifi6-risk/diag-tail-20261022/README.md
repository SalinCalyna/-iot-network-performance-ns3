# Residual long-delay tail at saturation (802.11ax, OLSR, N = 100, 64 kbps): diagnosis 2026-10-22

Programs (diagnostic only, never used for results):
- `scratch/iot-network-wifi6-risk-v2-diag.cc` = risk-v2 + read-only timeline (`--diagSrc`, `--diagNodes`)
- `scratch/iot-network-wifi6-risk-v3-diag.cc` = risk-v3 + the same timeline

Non-perturbation: `diag_src23/` (risk-v2-diag, full 300 s) reproduces every output of
`sat-smoke-v2-20261021T191711/runs/olsr_100_rate64_seed20` byte for byte (probe_aggregate timestamp excepted).
Truncated runs (`--simTime` < 300) reproduce the same events and UIDs up to their stop time (checked for the
traced packets: same uid, tx and rx times).

Every traced late packet was **received and acknowledged at the next hop**, then held in that hop's Block Ack
**reorder buffer**: the recipient's window waited for a sequence number that the originator no longer had, and no
BlockAckReq (BAR) reached the recipient for a long time. ns-3 recipients have no reorder-release timeout, so the
MPDU stays until a BAR arrives or a sequence number 256 higher arrives. Four ways this happens were found.

| # | Case (run, packet) | Held at | Hold | Mechanism | Evidence |
|---|---|---|---|---|---|
| A | v2 seed 20, src 23 seq 1756 (uid 504383) and 15 more | node 31 (link 23→31) | 157 s | retransmitted ADDBA Request processed as new → 2nd ADDBA Response → originator window jumps 1→2 silently; seq 1 then discarded as "old" → no BAR | `diag_src23/`, `diag_src23_t52/` (+ NS_LOG) |
| B | v3 seed 22, src 96 seq 69 (uid 399893) | node 69 (link 96→69) | 10.5 s | stale ADDBA Response: recipient answered an older ADDBA Request (SSN 0); originator matched it to its newer Request (SSN 4), so start = advertised SSN and the v2 check sent no BAR | `v3_s22_src96_t46/` (+ NS_LOG) |
| C | v3 seed 20, src 88 seq 62 (uid 338589) | gateway (link 88→100) | 12.5 s | BAR deferred: BlockAck to the BAR missed and no MPDU outstanding → ns-3 drops the BAR and puts the agreement on the "send BAR only if data queued" list; OLSR moved 88's route away from the gateway, so the BAR was resent only 12 s later | `v3_src88_t47/` |
| D | v3 seed 21, src 36 seq 98 (uid 600256) | node 35 (link 46→35) | 75.5 s | same as C (BAR SSN 14 failed at 37.04 s, resent at 112.37 s when 46 routed via 35 again) | `v3_s21_src36_t113/` |

## Case A in detail (link 23→31, times in s)
- 50.8920 23 sends ADDBA Request (mgmt seq 82, SSN 0); 50.8987 retry (mgmt seq 83, Retry=1).
- 50.8992 31 Acks; 50.8996 31 sends ADDBA Response; 50.9004 23 ESTABLISHED (start 0).
- 23 did not get the Ack of the Request, so it retransmits it (50.9071, 50.9388, Retry=1, mgmt seq 83).
- 50.9393 31 receives the duplicate. `HtFrameExchangeManager::ReceiveMpdu` calls `ReceiveMgtAction`
  **before** the MacRxMiddle duplicate filter (ht-frame-exchange-manager.cc:1938-1941), so `SendAddBaResponse`
  runs again and `CreateRecipientAgreement` replaces the agreement with SSN 0 (NS_LOG 50.939620).
- 50.9414 seq 0 delivered (recipient window → 1). seq 1 sent 3 times, never Acked.
- 50.9866 2nd ADDBA Response; 50.987388 `GotAddBaResponse` → `UpdateOriginatorAgreement(start = 2)`
  (NS_LOG); state already ESTABLISHED, so the AgreementState trace does not fire and the risk-v2 fix cannot see it.
- 50.987388 seq 1 expires; `HandleDiscardedMpdu`: "Discarded an old frame" (NS_LOG) → no BAR.
- Recipient waits for seq 1. Link 23→31 is used only when OLSR picks 31: seq 2…29 (142–298 s) are Acked
  normally and buffered. 298.93 seq 29 expires → BAR SSN 30 → 299.355 31 releases all 26 buffered packets.

## Fix tried: risk-v3 (`--baReestFix`)
BAR when an ADDBA Response re-establishes an ESTABLISHED agreement at a start ≠ advertised SSN. It fixes A
(validated: `validation-v3-20261022T133856`, 6,322 passed; the 2 failures are packet-UID relabelling only, see
`check_t11_uid_relabel.txt`), but not B, C, D. Saturation re-run (`v3-tail-check-20261022T133856`):

| seed | v2 > 10 s | v3 > 10 s | v2 max (s) | v3 max (s) | v2 FM − sink | v3 FM − sink |
|---|---|---|---|---|---|---|
| 20 | 46 | 22 | 156.9 | 67.4 | −45 | −21 |
| 21 | 14 | 24 | 160.2 | 174.1 | −12 | −23 |
| 22 | 22 | 36 | 144.5 | 163.7 | −22 | −35 |

The fix changes the event sequence, so v3 runs follow different trajectories (PDR 25.5/26.9/28.2 % vs v2
29.8/25.4/30.1 %); with n = 3 that difference is not interpretable. `--baReestFix=0` reproduces risk-v2
byte for byte (seed 20 full run and the validation twins).

## Status
Root causes A–D are confirmed by trace and ns-3 source. A complete fix (B, C, D) is not implemented; it needs a
decision (see the 2026-10-22 report): C/D require changing when ns-3 retransmits a BAR.

## Experimental risk-v4 (2026-10-23): one BAR after every ADDBA Response (option a)
`scratch/iot-network-wifi6-risk-v4.cc` = risk-v3 + `--baAddbaBar` (default on; `--baAddbaBar=0` equals risk-v3:
validation twins and the 300 s seed-20 run byte-identical). v2/v3 triggers only log, so one Response → one BAR.
Validation `validation-v4-20261023T222251`: 6,354 passed, 0 failed. Matched runs `v4-tail-check-20261023T222251`
(`analyze_v4_compare.py` → `compare_v2_v3_v4*.csv`), seeds 20/21/22:

| metric | v2 | v3 | v4 |
|---|---|---|---|
| delayed > 10 s per 100k delivered | 37.1 / 13.2 / 17.6 | 21.0 / 21.6 / 31.1 | 14.6 / 17.1 / 16.1 |
| max delay (s) | 156.9 / 160.2 / 144.5 | 67.4 / 174.1 / 163.7 | 95.5 / 140.0 / 166.4 |
| p99 delay (ms) | 1124 / 1019 / 1041 | 1134 / 1005 / 1071 | 1047 / 1087 / 1042 |
| sink − FM rx (pkts) | 45 / 12 / 22 | 21 / 23 / 35 | 18 / 17 / 19 |
| sink PDR (%) | 29.80 / 25.45 / 30.06 | 25.46 / 26.92 / 28.25 | 29.68 / 25.47 / 29.64 |
| BAR PSDUs | 144,904 / 137,339 / 165,417 | 145,504 / 132,323 / 160,395 | 144,900 / 139,327 / 170,485 |

v4 schedules 2,749–2,952 extra BARs per run (≈ 2 % of BAR PSDUs, ≈ 0.16 s of estimated airtime per 300 s run).
It is lower than v3 in 3/3 seeds but lower than v2 in only 2/3 (seed 21: 17.1 vs 13.2 per 100k; max delay worse
in seed 22). Not a consistent improvement; the deferred-BAR mechanism (cases C/D) is untouched by design.
**Decision: v4 not adopted.** Pilot simulator: risk-v2 (see experiments/wifi6-risk/README.md), with the residual
tail documented as a limitation.
