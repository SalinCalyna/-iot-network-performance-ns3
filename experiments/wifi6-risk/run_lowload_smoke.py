#!/usr/bin/env python3
"""risk-v2 low-load smoke: 802.11ax, OLSR, N=100, 4/8/16 kbps per sensor, seeds 20/21/22 (9 runs).

    python3 -I -B experiments/wifi6-risk/run_lowload_smoke.py [--jobs=6]

Fixed settings (same as the parent's arp-smoke-ax-on batch, results/wifi-std/arp-smoke-ax-on): --standard=80211ax
(Tier A: 2.4 GHz ch 1, 20 MHz, HeMcs0, GI 800 ns, A-MPDU/A-MSDU off), --trafficLevel=high with --offeredRateKbps,
--arpPrepopulate=1, simTime 300 s, appStart 30 s, 512 B UDP CBR to the gateway, static positions, 90 m disk
graph; plus --riskStudy=1 --numHighRisk=0 (no risky node; path traces and Wi-Fi read-back only) and
--perPacketTrace=1. --baSsnFix is left at its default (on). Output: results/wifi6-risk/lowload-smoke-v2-<time>/.
"""
import csv
import hashlib
import json
import math
import statistics as st
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / "build/scratch/ns3-dev-iot-network-wifi6-risk-v2-default"
SRC = ROOT / "scratch/iot-network-wifi6-risk-v2.cc"
RATES, SEEDS = (4, 8, 16), (20, 21, 22)
BASE = ["--standard=80211ax", "--protocol=olsr", "--nSensors=100", "--trafficLevel=high", "--arpPrepopulate=1",
        "--riskStudy=1", "--numHighRisk=0", "--perPacketTrace=1"]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def run(rid, args, out):
    d = out / "runs" / rid
    d.mkdir(parents=True, exist_ok=False)
    argv = [str(BIN)] + args + [f"--outDir={d.relative_to(ROOT)}"]
    t0 = time.time()
    with open(d / "stdout.log", "x") as so, open(d / "stderr.log", "x") as se:
        rc = subprocess.run(argv, cwd=ROOT, stdout=so, stderr=se).returncode
    prov = dict(run_id=rid, argv=argv, exit_code=rc, wall_sec=round(time.time() - t0, 1),
                stderr_bytes=(d / "stderr.log").stat().st_size, binary_sha256=sha(BIN), source_sha256=sha(SRC),
                finished=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    (d / "provenance.json").write_text(json.dumps(prov, indent=1))
    return prov


def main():
    jobs = int(dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a).get("--jobs", 6))
    out = ROOT / "results/wifi6-risk" / time.strftime("lowload-smoke-v2-%Y%m%dT%H%M%S")
    out.mkdir(parents=True)
    (out / "batch.json").write_text(json.dumps(dict(binary=str(BIN), binary_sha256=sha(BIN), source=str(SRC),
                                                    source_sha256=sha(SRC), base_args=BASE, rates_kbps=RATES,
                                                    seeds=SEEDS, started=time.strftime("%Y-%m-%dT%H:%M:%S%z")), indent=1))
    todo = [(f"olsr_100_rate{r}_seed{s}", BASE + [f"--offeredRateKbps={r}", f"--seed={s}"]) for r in RATES for s in SEEDS]
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        provs = list(ex.map(lambda t: run(t[0], t[1], out), todo))
    for p in provs:
        print(f"{p['run_id']}: exit {p['exit_code']}, stderr {p['stderr_bytes']} B, {p['wall_sec']} s", flush=True)
    print(f"output: {out}")


if __name__ == "__main__":
    main()
