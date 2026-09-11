#!/bin/zsh
# UPDATE #8 TIER-1 V4 ACTIVATION SCREEN -- approved scope, ANALYSIS-track.
# Calls the EXISTING, unmodified V4 binary directly (build/scratch/ns3-dev-iot-network-v3-ext-default)
# with the exact same shared parameters experiments/v4_sensitivity_study.py uses, varying ONLY
# x0_R, x0_L per the Tier-1 design. Writes ONLY under analysis/update8-tier1-activation/ .
# No source/runner/dashboard change. No results/ write. No git commit.
set -u
cd /Users/pinpuk/ns-3-dev
BIN=build/scratch/ns3-dev-iot-network-v3-ext-default
OUT=/Users/pinpuk/ns-3-dev/analysis/update8-tier1-activation/data
LOGD=$OUT/logs
MASTER=$OUT/../run_master.log
mkdir -p "$LOGD"

# Fixed (matched to Stage-1 sensitivity / V3 official)
NODES=50; TRAFFIC=medium; MOBIL=static; SIM=300; APPSTART=30; AREA=250; TXP=20; TXR=90; PKT=512
KR=10; KL=10; WR=0.5; WL=0.5
X0L_LEVELS=(0.02 0.05 0.50)
X0R_LEVELS=(0.50 0.80)
SEEDS=($(seq 20 30))

echo "==== TIER-1 SCREEN START $(date '+%Y-%m-%d %H:%M:%S') ====" | tee -a "$MASTER"
echo "x0_L in {${X0L_LEVELS[*]}}  x0_R in {${X0R_LEVELS[*]}}  k_R=k_L=$KR  w_R=$WR  seeds ${SEEDS[*]}" | tee -a "$MASTER"
i=0; total=$(( ${#X0L_LEVELS[@]} * ${#X0R_LEVELS[@]} * ${#SEEDS[@]} ))
fail=0
for x0l in $X0L_LEVELS; do
  for x0r in $X0R_LEVELS; do
    for s in $SEEDS; do
      i=$((i+1))
      tag="v4_50_medium_static_seed${s}_kR${KR}_x0R${x0r}_kL${KL}_x0L${x0l}_wR${WR}_wL${WL}"
      echo "[$i/$total] $tag" | tee -a "$MASTER"
      "$BIN" --protocol=v4 --nSensors=$NODES --trafficLevel=$TRAFFIC --mobilityMode=$MOBIL \
        --seed=$s --simTime=$SIM --appStart=$APPSTART --areaSize=$AREA --txPowerDbm=$TXP \
        --txRange=$TXR --packetSize=$PKT --outDir=$OUT \
        --v4KRisk=$KR --v4X0Risk=$x0r --v4KLoad=$KL --v4X0Load=$x0l --v4WRisk=$WR --v4WLoad=$WL \
        > "$LOGD/$tag.log" 2>&1
      rc=$?
      if [ $rc -ne 0 ]; then echo "  -> FAILED rc=$rc" | tee -a "$MASTER"; fail=$((fail+1)); fi
    done
  done
done
echo "==== TIER-1 SCREEN DONE $(date '+%Y-%m-%d %H:%M:%S')  runs=$i  failed=$fail ====" | tee -a "$MASTER"
