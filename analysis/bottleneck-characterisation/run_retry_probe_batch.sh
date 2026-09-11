#!/bin/zsh
# Retry-exhaustion measurement matrix -- MEASUREMENT ONLY, closes the §10 mechanism gap.
# Writes ONLY under analysis/bottleneck-characterisation/data-retry/ (NEW dir).
# The completed §10 raw dataset (data/) is never touched.
set -u
cd /Users/pinpuk/ns-3-dev
BIN=build/scratch/ns3-dev-iot-network-bottleneck-probe-default
OUT=/Users/pinpuk/ns-3-dev/analysis/bottleneck-characterisation/data-retry
LOGD=$OUT/runlogs
mkdir -p "$LOGD" "$OUT/pernode"
MASTER=$OUT/../batch_master_retry.log
PROTOS=(static olsr)
NODES=(50 75 100)
TRAFFIC=(medium high)
SEEDS=(20 25 30)
total=$(( ${#PROTOS[@]} * ${#NODES[@]} * ${#TRAFFIC[@]} * ${#SEEDS[@]} ))
i=0; fail=0
echo "==== RETRY PROBE BATCH START $(date '+%F %T')  total=$total ====" | tee -a "$MASTER"
for pr in $PROTOS; do for n in $NODES; do for tr in $TRAFFIC; do for s in $SEEDS; do
  i=$((i+1))
  tag="${pr}_${n}_${tr}_seed${s}"
  echo "[$i/$total] $tag $(date '+%T')" | tee -a "$MASTER"
  "$BIN" --protocol=$pr --nSensors=$n --trafficLevel=$tr --seed=$s --outDir=$OUT \
     > "$LOGD/$tag.log" 2>&1
  rc=$?
  [ $rc -ne 0 ] && { echo "  -> FAILED rc=$rc" | tee -a "$MASTER"; fail=$((fail+1)); }
done; done; done; done
echo "==== RETRY PROBE BATCH DONE $(date '+%F %T')  runs=$i  failed=$fail ====" | tee -a "$MASTER"
