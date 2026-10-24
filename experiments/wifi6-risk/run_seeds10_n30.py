#!/usr/bin/env python3
"""risk-v2, N = 30, 8 kbps, 10 seeds (20-29) x static / aodv / olsr / riskaware x numHighRisk 0-3 = 160 configs.

    python3 -I -B experiments/wifi6-risk/run_seeds10_n30.py [--jobs=6] [--batch=<existing batch dir to resume>]

Seeds 20-22 are NOT re-run: the 48 matching runs of results/wifi6-risk/pilot-n30-v2-20261024T054949 are reused
when, for every one, provenance shows exit 0, empty stderr, the validated risk-v2 binary and source hashes, and an
argv identical (except --outDir) to the one this script would use. They are listed in <batch>/reuse_manifest.json
(path, argv, hashes); nothing is copied or moved. Seeds 23-29 (112 runs) are run into
results/wifi6-risk/seeds10-n30-8k-v2-<time>/runs/. Settings are those of run_pilot_n30.py (same BASE arguments).
A run directory without provenance.json (interrupted) is moved to <batch>/interrupted/ before it is re-run.
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

ROOT = P.ROOT
REUSE = ROOT / "results/wifi6-risk/pilot-n30-v2-20261024T054949"
RATE, NEW_SEEDS, OLD_SEEDS = 8, tuple(range(23, 30)), (20, 21, 22)


def main():
    opts = dict(a.split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
    jobs = int(opts.get("--jobs", 6))
    if P.sha(P.BIN) != P.EXPECT_BIN or P.sha(P.SRC) != P.EXPECT_SRC:
        sys.exit("STOP: risk-v2 binary or source differs from the validated version")
    if shutil.disk_usage(ROOT).free < 1024 ** 3:
        sys.exit("STOP: less than 1 GB free")
    # reuse check
    manifest = []
    for s in OLD_SEEDS:
        for p in P.PROTOS:
            for k in P.KS:
                d = REUSE / "runs" / P.rid(p, k, s, RATE)
                pv = json.loads((d / "provenance.json").read_text())
                want = [str(P.BIN)] + P.args(p, k, s, RATE)
                ok = (pv["exit_code"] == 0 and pv["stderr_bytes"] == 0 and pv["binary_sha256"] == P.EXPECT_BIN
                      and pv["source_sha256"] == P.EXPECT_SRC and pv["argv"][:-1] == want
                      and pv["argv"][-1].startswith("--outDir="))
                if not ok:
                    sys.exit(f"STOP: cannot reuse {d} (provenance does not match)")
                manifest.append(dict(run_id=d.name, path=str(d.relative_to(ROOT)), argv=pv["argv"],
                                     binary_sha256=pv["binary_sha256"], source_sha256=pv["source_sha256"]))
    if "--batch" in opts:
        out = Path(opts["--batch"]).resolve()
    else:
        out = ROOT / "results/wifi6-risk" / time.strftime("seeds10-n30-8k-v2-%Y%m%dT%H%M%S")
        out.mkdir(parents=True)
        (out / "batch.json").write_text(json.dumps(dict(
            binary=str(P.BIN), binary_sha256=P.EXPECT_BIN, source=str(P.SRC), source_sha256=P.EXPECT_SRC,
            base_args=P.BASE, protocols=P.PROTOS, num_high_risk=P.KS, rate_kbps=RATE, new_seeds=NEW_SEEDS,
            reused_seeds=OLD_SEEDS, reused_from=str(REUSE.relative_to(ROOT)), simTime_s=300, appStart_s=30,
            created=time.strftime("%Y-%m-%dT%H:%M:%S%z")), indent=1))
    (out / "reuse_manifest.json").write_text(json.dumps(manifest, indent=1))
    pending = []
    for s in NEW_SEEDS:
        for p in P.PROTOS:
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
    print(f"reused {len(manifest)} runs; {len(pending)} runs to do in {out}", flush=True)
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        list(ex.map(lambda c: P.run(P.rid(*c), P.args(*c), out), pending))
    print(f"output: {out}")


if __name__ == "__main__":
    main()
