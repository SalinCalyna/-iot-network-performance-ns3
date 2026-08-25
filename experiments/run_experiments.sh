#!/usr/bin/env bash
#
# Runs the full (routing protocol x network size) experiment matrix for the
# "Analysis of IoT Network Performance Using NS-3" V2 study, and writes
# results/<protocol>_<nSensors>.csv (one row appended per --posSeed trial).
#
# Every run shares identical parameters except --protocol, --nSensors and
# --posSeed, so the only things that vary between rows are exactly the
# variables the experiment is designed to study.
#
# Usage: ./experiments/run_experiments.sh [nSeeds]
#   nSeeds  number of independent topology draws per scenario (default: 5)

set -euo pipefail
cd "$(dirname "$0")/.."

NSEEDS="${1:-5}"
PROTOCOLS=(aodv olsr static)
SIZES=(10 20 30 50)

BIN="./build/scratch/ns3-dev-iot-network-default"
if [[ ! -x "$BIN" ]]; then
    echo "Binary not found at $BIN -- run: ./ns3 build scratch_iot-network" >&2
    exit 1
fi

rm -rf results
mkdir -p results/logs

total=$(( ${#PROTOCOLS[@]} * ${#SIZES[@]} * NSEEDS ))
count=0

for n in "${SIZES[@]}"; do
    for p in "${PROTOCOLS[@]}"; do
        for ((seed = 1; seed <= NSEEDS; seed++)); do
            count=$((count + 1))
            echo "[$count/$total] protocol=$p nSensors=$n posSeed=$seed"
            "$BIN" \
                --protocol="$p" \
                --nSensors="$n" \
                --posSeed="$seed" \
                --simTime=100 \
                --appStart=30 \
                --areaSize=250 \
                --txPowerDbm=20 \
                --txRange=90 \
                --packetSize=512 \
                --dataRate=8kbps \
                --outDir=results \
                > "results/logs/${p}_${n}_seed${seed}.log" 2>&1
        done
    done
done

echo "Done. Results in ./results/*.csv (per-run logs in ./results/*.log)"
