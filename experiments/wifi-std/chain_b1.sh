#!/bin/sh
# 2026-10-18 B1 (user-approved): Table 4 cells OLSR/Static x N=30 high + N 30-100 medium x seeds 20-30, flag on.
# 64 new runs; the other 46 of the 110 are in arp-a2-on / arp-a1-on (identical argv). Re-run to resume.
cd "$(dirname "$0")/../.." || exit 1
P="python3 -I -B"
echo "== chain start $(date '+%F %T %z')"
caffeinate -i $P experiments/wifi-std/run_resumable.py arp-b1-on || { echo "STOP: batch failed"; exit 1; }
$P experiments/wifi-std/check_frozen.py || { echo "STOP: frozen files touched"; exit 1; }
echo "== chain done $(date '+%F %T %z')"
