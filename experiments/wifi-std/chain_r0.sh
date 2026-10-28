#!/bin/sh
# 2026-10-18 R0 (user-approved chain R0 -> A2 -> A1). The flag-off preview (compare_r0_v3ext.py --preview) already
# showed OLSR PathChanges != v3-ext, so only R0 is run here and the chain stops after the R0 comparison.
cd "$(dirname "$0")/../.." || exit 1
P="python3 -I -B"
echo "== R0 start $(date '+%F %T %z')"
caffeinate -i $P experiments/wifi-std/run_resumable.py arp-r0-off || { echo "STOP: batch failed"; exit 1; }
$P experiments/wifi-std/compare_r0_v3ext.py > results/wifi-std/arp-r0-off_compare.txt 2>&1; echo "compare exit $?"
$P experiments/wifi-std/check_frozen.py || { echo "STOP: frozen files touched"; exit 1; }
echo "== R0 done $(date '+%F %T %z')"
