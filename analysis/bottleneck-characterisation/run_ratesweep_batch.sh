#!/bin/zsh
# Phase-1 offered-rate sweep -- MEASUREMENT ONLY. Approved matrix: 3 N x 2 protocols x 4 rates x 3 seeds = 72 runs.
# Writes ONLY under analysis/bottleneck-characterisation/data-ratesweep/ (NEW dir).
# Neither the §10 dataset (data/) nor the retry-exhaustion dataset (data-retry/) is touched.
set -u
cd /Users/pinpuk/ns-3-dev
BIN=build/scratch/ns3-dev-iot-network-bottleneck-probe-default
OUT=/Users/pinpuk/ns-3-dev/analysis/bottleneck-characterisation/data-ratesweep
LOGD=$OUT/runlogs
mkdir -p "$LOGD" "$OUT/pernode"
MASTER=$OUT/../batch_master_ratesweep.log
PROTOS=(static olsr)
NODES=(50 75 100)
RATES=(16 12 8 4)
SEEDS=(20 25 30)
total=$(( ${#PROTOS[@]} * ${#NODES[@]} * ${#RATES[@]} * ${#SEEDS[@]} ))
i=0; fail=0
echo "==== RATESWEEP BATCH START $(date '+%F %T')  total=$total ====" | tee -a "$MASTER"
for pr in $PROTOS; do for n in $NODES; do for r in $RATES; do for s in $SEEDS; do
  i=$((i+1))
  tag="${pr}_${n}_rate${r}_seed${s}"
  echo "[$i/$total] $tag $(date '+%T')" | tee -a "$MASTER"
  "$BIN" --protocol=$pr --nSensors=$n --trafficLevel=high --offeredRateKbps=$r --seed=$s --outDir=$OUT \
     > "$LOGD/$tag.log" 2>&1
  rc=$?
  [ $rc -ne 0 ] && { echo "  -> FAILED rc=$rc" | tee -a "$MASTER"; fail=$((fail+1)); }
done; done; done; done
echo "==== RATESWEEP BATCH DONE $(date '+%F %T')  runs=$i  failed=$fail ====" | tee -a "$MASTER"
