#!/bin/sh
# ARP study step 3: waits for chain_arp_steps12.sh to finish OK, then the ax-on smoke (20 runs, OLSR N=100 64/128/256
# first, no timeout, stop on failure) and AODV N=100 (4 runs, 3600 s timeout each, continue). Re-run to resume.
cd "$(dirname "$0")/../.." || exit 1
L=results/wifi-std/arp-chain12_console.log
until grep -q "chain done\|STOP" "$L"; do sleep 30; done
grep -q "STOP" "$L" && { echo "STOP: steps 1-2 stopped, step 3 not started"; exit 1; }
P="python3 -I -B"
echo "== step 3 start $(date '+%F %T %z')"
caffeinate -i $P experiments/wifi-std/run_resumable.py arp-smoke-ax-on || { echo "STOP: smoke batch failed"; exit 1; }
caffeinate -i $P experiments/wifi-std/run_resumable.py arp-smoke-ax-on-aodv100 --timeout=3600 --no-stop || { echo "STOP: aodv100 batch error"; exit 1; }
$P experiments/wifi-std/check_frozen.py || { echo "STOP: frozen files touched"; exit 1; }
echo "== step 3 done $(date '+%F %T %z')"
