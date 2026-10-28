#!/bin/sh
# 2026-10-18 A2 -> A1 (user-approved after R0 PASS with PathChanges/UnreachableSensors excluded, see
# results/wifi-std/arp-r0-off/README.md). 802.11b, --arpPrepopulate=1, static mobility; 4 kbps runs are labelled low.
# Re-run to resume.
cd "$(dirname "$0")/../.." || exit 1
P="python3 -I -B"
echo "== chain start $(date '+%F %T %z')"
$P experiments/wifi-std/compare_r0_v3ext.py > /dev/null || { echo "STOP: R0 not PASS"; exit 1; }
caffeinate -i $P experiments/wifi-std/run_resumable.py arp-a2-on arp-a1-on || { echo "STOP: batch failed"; exit 1; }
$P experiments/wifi-std/check_frozen.py || { echo "STOP: frozen files touched"; exit 1; }
echo "== chain done $(date '+%F %T %z')"
