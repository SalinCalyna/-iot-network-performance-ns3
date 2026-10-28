#!/bin/sh
# Phase I rate sweep (802.11b, 72 conditions x {on, off}) on iot-network-wifi-std-arp.cc. Starts when the 20-run
# ax-on smoke batch has finished (runs alongside the 4-run AODV N=100 batch, --jobs=4). Re-run to resume.
cd "$(dirname "$0")/../.." || exit 1
L=results/wifi-std/arp-chain3_console.log
until grep -q "arp-smoke-ax-on: finished\|STOP" "$L"; do sleep 30; done
grep -q "STOP" "$L" && { echo "STOP: step 3 stopped, rate sweep not started"; exit 1; }
P="python3 -I -B"
echo "== rate sweep start $(date '+%F %T %z')"
caffeinate -i $P experiments/wifi-std/run_resumable.py arp-ratesweep-on arp-ratesweep-off --jobs=4 || { echo "STOP: rate sweep failed"; exit 1; }
$P experiments/wifi-std/check_frozen.py || { echo "STOP: frozen files touched"; exit 1; }
echo "== rate sweep done $(date '+%F %T %z')"
