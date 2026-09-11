#!/bin/zsh
# Reproducibility validation -- 51 runs total. READ-ONLY w.r.t. all frozen datasets.
# Writes ONLY under analysis/final-reproducibility-check/. No source/runner modified.
set -u
cd /Users/pinpuk/ns-3-dev
V3BIN=build/scratch/ns3-dev-iot-network-v3-ext-default
PROBEBIN=build/scratch/ns3-dev-iot-network-bottleneck-probe-default
BASE=/Users/pinpuk/ns-3-dev/analysis/final-reproducibility-check
LOGD=$BASE/logs
MASTER=$BASE/run_master.log
i=0; total=51; fail=0
echo "==== REPRO VALIDATION START $(date '+%F %T')  total=$total ====" | tee -a "$MASTER"

# ---- Case A: V3 baseline, 3 protocols x N{10,50,100} x medium x static x seeds{20,25,30} = 27 ----
OUT_A=$BASE/data
mkdir -p "$OUT_A"
for pr in aodv olsr static; do for n in 10 50 100; do for s in 20 25 30; do
  i=$((i+1))
  tag="caseA_${pr}_n${n}_medium_seed${s}"
  echo "[$i/$total] $tag $(date '+%T')" | tee -a "$MASTER"
  "$V3BIN" --protocol=$pr --nSensors=$n --trafficLevel=medium --mobilityMode=static --seed=$s \
    --outDir=$OUT_A > "$LOGD/$tag.log" 2>&1
  rc=$?
  [ $rc -ne 0 ] && { echo "  -> FAILED rc=$rc" | tee -a "$MASTER"; fail=$((fail+1)); }
done; done; done

# ---- Case B: bottleneck validation, OLSR, N{75,100}, high, seeds{20,25,30} = 6 ----
OUT_B=$BASE/data-caseB
mkdir -p "$OUT_B/pernode"
for n in 75 100; do for s in 20 25 30; do
  i=$((i+1))
  tag="caseB_olsr_n${n}_high_seed${s}"
  echo "[$i/$total] $tag $(date '+%T')" | tee -a "$MASTER"
  "$PROBEBIN" --protocol=olsr --nSensors=$n --trafficLevel=high --seed=$s \
    --outDir=$OUT_B > "$LOGD/$tag.log" 2>&1
  rc=$?
  [ $rc -ne 0 ] && { echo "  -> FAILED rc=$rc" | tee -a "$MASTER"; fail=$((fail+1)); }
done; done

# ---- Case C: rate-intervention validation, OLSR, N{75,100}, rate{16,4}, seeds{20,25,30} = 12 ----
# separate outDir per rate to avoid the known pernode-filename-collision bug from the original rate sweep
for r in 16 4; do
  OUT_C=$BASE/data-caseC-rate${r}
  mkdir -p "$OUT_C/pernode"
  for n in 75 100; do for s in 20 25 30; do
    i=$((i+1))
    tag="caseC_olsr_n${n}_rate${r}_seed${s}"
    echo "[$i/$total] $tag $(date '+%T')" | tee -a "$MASTER"
    "$PROBEBIN" --protocol=olsr --nSensors=$n --trafficLevel=high --offeredRateKbps=$r --seed=$s \
      --outDir=$OUT_C > "$LOGD/$tag.log" 2>&1
    rc=$?
    [ $rc -ne 0 ] && { echo "  -> FAILED rc=$rc" | tee -a "$MASTER"; fail=$((fail+1)); }
  done; done
done

# ---- Case D: Static negative-control, N=50, rate{16,4}, seeds{20,25,30} = 6 ----
for r in 16 4; do
  OUT_D=$BASE/data-caseD-rate${r}
  mkdir -p "$OUT_D/pernode"
  for s in 20 25 30; do
    i=$((i+1))
    tag="caseD_static_n50_rate${r}_seed${s}"
    echo "[$i/$total] $tag $(date '+%T')" | tee -a "$MASTER"
    "$PROBEBIN" --protocol=static --nSensors=50 --trafficLevel=high --offeredRateKbps=$r --seed=$s \
      --outDir=$OUT_D > "$LOGD/$tag.log" 2>&1
    rc=$?
    [ $rc -ne 0 ] && { echo "  -> FAILED rc=$rc" | tee -a "$MASTER"; fail=$((fail+1)); }
  done
done

echo "==== REPRO VALIDATION DONE $(date '+%F %T')  runs=$i  failed=$fail ====" | tee -a "$MASTER"
