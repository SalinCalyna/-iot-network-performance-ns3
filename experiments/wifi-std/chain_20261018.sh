#!/bin/sh
# 2026-10-18 chain (user-approved): (a) the 5 interrupted ax-on smoke runs, (b) Phase I rate sweep on 802.11b with
# --arpPrepopulate=1 (72 runs, same conditions/seeds as the original), (c) b-on OLSR + Static x N 50/75/100 x 16 kbps
# x seeds 20-30 (66 runs). No AODV, no ax-on matrix. Re-run to resume.
cd "$(dirname "$0")/../.." || exit 1
P="python3 -I -B"
echo "== chain start $(date '+%F %T %z')"
caffeinate -i $P experiments/wifi-std/run_resumable.py arp-smoke-ax-on arp-ratesweep-on arp-b-on-os || { echo "STOP: batch failed"; exit 1; }
$P experiments/wifi-std/check_frozen.py || { echo "STOP: frozen files touched"; exit 1; }
echo "== chain done $(date '+%F %T %z')"
