#!/usr/bin/env python3
"""risk-v2 pilot at N = 30 (approved scope, 2026-10-24): 96 runs =
protocols static / aodv / olsr / riskaware x numHighRisk 0..3 x seeds 20, 21, 22 x 8 and 64 kbps per source.

    python3 -I -B experiments/wifi6-risk/run_pilot_n30.py --phase=subset [--jobs=6]
    python3 -I -B experiments/wifi6-risk/run_pilot_n30.py --phase=full --batch=<batch dir> [--jobs=6]

--phase=subset creates results/wifi6-risk/pilot-n30-v2-<time>/ and runs the representative subset (seed 20,
both loads, all 4 protocols, k = 0 and 3: 16 runs). --phase=full runs the remaining runs of the same batch; a run
whose provenance.json shows exit 0 is skipped, and a run directory without provenance.json (interrupted) is moved to
<batch>/interrupted/ before it is re-run. Nothing is deleted.

Fixed settings (as the validated risk-v2 smoke batches): risk-v2 binary, --standard=80211ax (Tier A: 2.4 GHz ch 1,
20 MHz, HeMcs0, GI 800 ns, A-MPDU/A-MSDU off), --trafficLevel=high with --offeredRateKbps, --arpPrepopulate=1,
simTime 300 s and appStart 30 s (program defaults), 512 B UDP CBR to the gateway, static positions (seeded,
250 m x 250 m, gateway at the centre), 90 m disk graph for static/riskaware, --riskStudy=1, --perPacketTrace=1,
--baSsnFix on (default). Approved risk parameters, passed explicitly (equal to the defaults): HIGH_RISK r = 0.5,
LOW_RISK r = 0, beta = 10, selection rule subtree, risk-drop seed 1.
Matching: positions depend only on the seed; the high-risk set depends only on positions, k and the rule, so it is
the same for every protocol and load; every source's send schedule depends only on the rate.
"""
import hashlib
import json
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / "build/scratch/ns3-dev-iot-network-wifi6-risk-v2-default"
SRC = ROOT / "scratch/iot-network-wifi6-risk-v2.cc"
EXPECT_BIN = "d909f6de6233dfad80700b37beb71d4a62c2cd38f223b6acc70cbb40f1bb2407"
EXPECT_SRC = "33b350ab5f790d7347fbd81b3b010a1d455af73ebd0a28ce187eca7e0633311b"
PROTOS, KS, SEEDS, RATES = ("static", "aodv", "olsr", "riskaware"), (0, 1, 2, 3), (20, 21, 22), (8, 64)
BASE = ["--standard=80211ax", "--nSensors=30", "--trafficLevel=high", "--arpPrepopulate=1", "--riskStudy=1",
        "--perPacketTrace=1", "--highRiskDropProb=0.5", "--lowRiskDropProb=0", "--riskBeta=10",
        "--riskSelect=subtree", "--riskDropSeed=1"]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def rid(p, k, s, r):
    return f"{p}_k{k}_rate{r}_seed{s}"


def args(p, k, s, r):
    return BASE + [f"--protocol={p}", f"--numHighRisk={k}", f"--offeredRateKbps={r}", f"--seed={s}"]


def run(name, a, out):
    d = out / "runs" / name
    d.mkdir(parents=True, exist_ok=False)
    argv = [str(BIN)] + a + [f"--outDir={d.relative_to(ROOT)}"]
    t0 = time.time()
    with open(d / "stdout.log", "x") as so, open(d / "stderr.log", "x") as se:
        rc = subprocess.run(argv, cwd=ROOT, stdout=so, stderr=se).returncode
    prov = dict(run_id=name, argv=argv, exit_code=rc, wall_sec=round(time.time() - t0, 1),
                stderr_bytes=(d / "stderr.log").stat().st_size, binary_sha256=sha(BIN), source_sha256=sha(SRC),
                finished=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    (d / "provenance.json").write_text(json.dumps(prov, indent=1))
    print(f"{name}: exit {rc}, stderr {prov['stderr_bytes']} B, {prov['wall_sec']} s", flush=True)
    return prov


def main():
    opts = dict(a.split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
    jobs, phase = int(opts.get("--jobs", 6)), opts.get("--phase")
    if sha(BIN) != EXPECT_BIN or sha(SRC) != EXPECT_SRC:
        sys.exit("STOP: risk-v2 binary or source differs from the validated version")
    if shutil.disk_usage(ROOT).free < 1024 ** 3:
        sys.exit("STOP: less than 1 GB free")
    full = [(p, k, s, r) for r in RATES for s in SEEDS for p in PROTOS for k in KS]
    if phase == "subset":
        out = ROOT / "results/wifi6-risk" / time.strftime("pilot-n30-v2-%Y%m%dT%H%M%S")
        out.mkdir(parents=True)
        (out / "batch.json").write_text(json.dumps(dict(
            binary=str(BIN), binary_sha256=EXPECT_BIN, source=str(SRC), source_sha256=EXPECT_SRC, base_args=BASE,
            protocols=PROTOS, num_high_risk=KS, seeds=SEEDS, rates_kbps=RATES, simTime_s=300, appStart_s=30,
            created=time.strftime("%Y-%m-%dT%H:%M:%S%z")), indent=1))
        todo = [c for c in full if c[2] == 20 and c[1] in (0, 3)]
    elif phase == "full":
        out = Path(opts["--batch"]).resolve()
        todo = full
    else:
        sys.exit("--phase=subset | full")
    pending = []
    for c in todo:
        d = out / "runs" / rid(*c)
        if d.exists():
            pv = d / "provenance.json"
            if pv.exists() and json.loads(pv.read_text())["exit_code"] == 0:
                continue
            dst = out / "interrupted" / time.strftime(f"{d.name}-%Y%m%dT%H%M%S")
            dst.parent.mkdir(exist_ok=True)
            shutil.move(str(d), str(dst))
            print(f"moved incomplete {d.name} -> {dst}", flush=True)
        pending.append(c)
    print(f"{phase}: {len(pending)} runs to do in {out}", flush=True)
    # longest first: 64 kbps runs take longer
    pending.sort(key=lambda c: -c[3])
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        list(ex.map(lambda c: run(rid(*c), args(*c), out), pending))
    print(f"output: {out}")


if __name__ == "__main__":
    main()
