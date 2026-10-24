#!/usr/bin/env python3
"""AODV diagnostic at N = 100, 8 kbps, k = 0, seed 20 (approved 2026-10-24). Validated risk-v2 binary, unchanged.

    python3 -I -B experiments/wifi6-risk/run_aodv_diag.py

Two runs, both with NS_LOG="AodvRoutingProtocol=level_logic|prefix_time|prefix_node"; the log is not stored, it is
piped through aodv_log_counter.py (counts only -> aodv_log_counts.json; non-log stderr lines -> stderr.log):
  bafix0/runs/aodv_k0_rate8_seed20   run_n100_8k.py argv + --baSsnFix=0 (Block Ack modification off)
  bafix1/runs/aodv_k0_rate8_seed20   argv identical to n100-8k-v2-20261024T165009/runs/aodv_k0_rate8_seed20
                                      (fix on). Its outputs are compared byte for byte with that run, which shows
                                      that logging did not change the simulation, and it supplies AODV control
                                      counts for the fix-on case.
Output: results/wifi6-risk/aodv-diag-n100-<time>/{bafix0,bafix1}/ (each with batch.json, n_sensors 100, so
analyze_pilot_n30.py can be run on it).
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("run_pilot_n30", HERE / "run_pilot_n30.py")
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)
P.BASE = [a if a != "--nSensors=30" else "--nSensors=100" for a in P.BASE]
ROOT = P.ROOT
NSLOG = "AodvRoutingProtocol=level_logic|prefix_time|prefix_node"
COUNTER = HERE / "aodv_log_counter.py"
GW, FIRST_SEND, PERIOD = "10.1.1.101", 30.512, 0.512


def run(sub, extra, out):
    d = out / sub / "runs" / P.rid("aodv", 0, 20, 8)
    d.mkdir(parents=True)
    argv = [str(P.BIN)] + P.args("aodv", 0, 20, 8) + extra + [f"--outDir={d.relative_to(ROOT)}"]
    t0 = time.time()
    with open(d / "stdout.log", "x") as so:
        sim = subprocess.Popen(argv, cwd=ROOT, stdout=so, stderr=subprocess.PIPE, env=dict(os.environ, NS_LOG=NSLOG))
        cnt = subprocess.Popen([sys.executable, "-I", "-B", str(COUNTER), str(d), GW, str(FIRST_SEND), str(PERIOD)],
                               stdin=sim.stderr)
        sim.stderr.close()
        rc = sim.wait()
        crc = cnt.wait()
    prov = dict(run_id=d.name, argv=argv, env_NS_LOG=NSLOG, exit_code=rc, counter_exit_code=crc,
                wall_sec=round(time.time() - t0, 1), stderr_bytes=(d / "stderr.log").stat().st_size,
                binary_sha256=P.sha(P.BIN), source_sha256=P.sha(P.SRC), counter_sha256=P.sha(COUNTER),
                finished=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    (d / "provenance.json").write_text(json.dumps(prov, indent=1))
    print(f"{sub}: exit {rc}, counter {crc}, stderr {prov['stderr_bytes']} B, {prov['wall_sec']} s", flush=True)


def main():
    if P.sha(P.BIN) != P.EXPECT_BIN or P.sha(P.SRC) != P.EXPECT_SRC:
        sys.exit("STOP: risk-v2 binary or source differs from the validated version")
    if shutil.disk_usage(ROOT).free < 1024 ** 3:
        sys.exit("STOP: less than 1 GB free")
    out = ROOT / "results/wifi6-risk" / time.strftime("aodv-diag-n100-%Y%m%dT%H%M%S")
    for sub, extra in (("bafix0", ["--baSsnFix=0"]), ("bafix1", [])):
        (out / sub).mkdir(parents=True)
        (out / sub / "batch.json").write_text(json.dumps(dict(
            binary=str(P.BIN), binary_sha256=P.EXPECT_BIN, source=str(P.SRC), source_sha256=P.EXPECT_SRC,
            base_args=P.BASE, extra_args=extra, n_sensors=100, protocols=["aodv"], num_high_risk=[0], rate_kbps=8,
            seeds=[20], env_NS_LOG=NSLOG, simTime_s=300, appStart_s=30,
            created=time.strftime("%Y-%m-%dT%H:%M:%S%z")), indent=1))
    with ThreadPoolExecutor(max_workers=2) as ex:
        list(ex.map(lambda c: run(c[0], c[1], out), (("bafix0", ["--baSsnFix=0"]), ("bafix1", []))))
    print(f"output: {out}")


if __name__ == "__main__":
    main()
