#!/bin/sh
# ARP study steps 1-2. Re-running resumes (run_resumable.py skips completed runs). Stops at the first failure.
cd "$(dirname "$0")/../.." || exit 1
P="python3 -I -B"
echo "== chain start $(date '+%F %T %z')"
caffeinate -i $P experiments/wifi-std/run_resumable.py arp-regression || { echo "STOP: arp-regression batch failed"; exit 1; }
$P experiments/wifi-std/compare_arp_regression.py > results/wifi-std/arp-regression_compare.txt 2>&1
rc=$?; tail -15 results/wifi-std/arp-regression_compare.txt
[ $rc -eq 0 ] || { echo "STOP: regression mismatch"; exit 1; }
$P experiments/wifi-std/check_frozen.py || { echo "STOP: frozen files touched"; exit 1; }
caffeinate -i $P experiments/wifi-std/run_resumable.py arp-phase1-off arp-phase1-on || { echo "STOP: phase1 batch failed"; exit 1; }
$P experiments/wifi-std/check_frozen.py || { echo "STOP: frozen files touched"; exit 1; }
echo "== chain done $(date '+%F %T %z')"
