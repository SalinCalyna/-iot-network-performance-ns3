#!/usr/bin/env python3
"""risk-v2, N = 100, 8 kbps per source, seeds 20-22 x static / aodv / olsr / riskaware x numHighRisk 0-3 (48 runs).

    python3 -I -B experiments/wifi6-risk/run_n100_8k.py [--jobs=6] [--batch=<existing batch dir to resume>]

Same fixed settings and approved risk parameters as run_pilot_n30.py (its BASE arguments with --nSensors=100).
No earlier run has an identical argv (the low-load smoke OLSR k=0 runs used implicit risk defaults and another
argument order), so nothing is reused; those three runs are compared byte for byte afterwards as a determinism check.
Output: results/wifi6-risk/n100-8k-v2-<time>/runs/. A run directory without provenance.json (interrupted) is moved
to <batch>/interrupted/ before it is re-run.
"""
import importlib.util
import json
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("run_pilot_n30", HERE / "run_pilot_n30.py")
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)
P.BASE = [a if a != "--nSensors=30" else "--nSensors=100" for a in P.BASE]
assert "--nSensors=100" in P.BASE
ROOT, RATE, SEEDS = P.ROOT, 8, (20, 21, 22)


def main():
    opts = dict(a.split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
    jobs = int(opts.get("--jobs", 6))
    if P.sha(P.BIN) != P.EXPECT_BIN or P.sha(P.SRC) != P.EXPECT_SRC:
        sys.exit("STOP: risk-v2 binary or source differs from the validated version")
    if shutil.disk_usage(ROOT).free < 1024 ** 3:
        sys.exit("STOP: less than 1 GB free")
    if "--batch" in opts:
        out = Path(opts["--batch"]).resolve()
    else:
        out = ROOT / "results/wifi6-risk" / time.strftime("n100-8k-v2-%Y%m%dT%H%M%S")
        out.mkdir(parents=True)
        (out / "batch.json").write_text(json.dumps(dict(
            binary=str(P.BIN), binary_sha256=P.EXPECT_BIN, source=str(P.SRC), source_sha256=P.EXPECT_SRC,
            base_args=P.BASE, n_sensors=100, protocols=P.PROTOS, num_high_risk=P.KS, rate_kbps=RATE, seeds=SEEDS,
            simTime_s=300, appStart_s=30, created=time.strftime("%Y-%m-%dT%H:%M:%S%z")), indent=1))
    pending = []
    for s in SEEDS:
        for p in ("olsr", "aodv", "static", "riskaware"):   # slower protocols first
            for k in P.KS:
                d = out / "runs" / P.rid(p, k, s, RATE)
                if d.exists():
                    pv = d / "provenance.json"
                    if pv.exists() and json.loads(pv.read_text())["exit_code"] == 0:
                        continue
                    dst = out / "interrupted" / time.strftime(f"{d.name}-%Y%m%dT%H%M%S")
                    dst.parent.mkdir(exist_ok=True)
                    shutil.move(str(d), str(dst))
                pending.append((p, k, s, RATE))
    print(f"{len(pending)} runs to do in {out}", flush=True)
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        list(ex.map(lambda c: P.run(P.rid(*c), P.args(*c), out), pending))
    print(f"output: {out}")


if __name__ == "__main__":
    main()
