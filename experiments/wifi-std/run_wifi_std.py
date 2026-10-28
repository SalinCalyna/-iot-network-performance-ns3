#!/usr/bin/env python3
"""Runner for scratch/iot-network-wifi-std.cc (Phase I bottleneck study on a selectable Wi-Fi standard).

    python3 -I -B experiments/wifi-std/run_wifi_std.py regression2          # 6 b OLSR/Static + 3 b AODV
    python3 -I -B experiments/wifi-std/run_wifi_std.py smoke                # ax: 3 protocols x N 50,100 x 16/64/128/256
    python3 -I -B experiments/wifi-std/run_wifi_std.py matrix-ax <satKbps>  # ax: 3 x 3 N x {16, sat} x 11 seeds
    python3 -I -B experiments/wifi-std/run_wifi_std.py matrix-b-aodv        # b: AODV x 3 N x 16 kbps x 11 seeds

Each run gets a fresh directory results/wifi-std/<mode>/<run_id>/ (refused if it exists) with
stdout/stderr logs and provenance.json (git HEAD/branch, source and binary SHA-256, exact argv,
wall time, exit code). The binary is run directly (no ./ns3, nothing is rebuilt). Runs execute in
parallel (--jobs, default 6); the batch stops scheduling new runs at the first non-zero exit or
non-empty stderr. Nothing outside results/wifi-std/ is written.
"""
import hashlib
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = "scratch/iot-network-wifi-std.cc"
BIN = "build/scratch/ns3-dev-iot-network-wifi-std-default"
OUT = ROOT / "results/wifi-std"
SEEDS = range(20, 31)


def run(rid, std, proto, n, rate=None, seed=20):
    a = [f"--standard={std}", f"--protocol={proto}", f"--nSensors={n}", "--trafficLevel=high", f"--seed={seed}"]
    if rate is not None:
        a.append(f"--offeredRateKbps={rate}")
    return dict(id=rid, args=a)


def runs_for(mode, extra):
    if mode == "regression2":
        return ([run(f"b_{p}_{n}_high_seed20", "80211b", p, n) for p in ("olsr", "static") for n in (30, 75, 100)]
                + [run(f"b_aodv_{n}_high_seed20", "80211b", "aodv", n) for n in (30, 75, 100)])
    if mode == "smoke":
        return [run(f"ax_{p}_{n}_rate{r}_seed20", "80211ax", p, n, r)
                for p in ("aodv", "olsr", "static") for n in (50, 100) for r in (16, 64, 128, 256)]
    if mode == "matrix-ax":
        sat = int(extra)
        return [run(f"ax_{p}_{n}_rate{r}_seed{s}", "80211ax", p, n, r, s)
                for p in ("aodv", "olsr", "static") for n in (50, 75, 100) for r in (16, sat) for s in SEEDS]
    if mode == "matrix-b-aodv":
        return [run(f"b_aodv_{n}_rate16_seed{s}", "80211b", "aodv", n, 16, s) for n in (50, 75, 100) for s in SEEDS]
    sys.exit(__doc__)


def sha256(p):
    return hashlib.sha256((ROOT / p).read_bytes()).hexdigest()


def git(*a):
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True,
                          env={"GIT_OPTIONAL_LOCKS": "0", "PATH": "/usr/bin:/bin:/opt/homebrew/bin"}).stdout.strip()


def main(mode, extra=None, jobs=6):
    runs = runs_for(mode, extra)
    head, branch = git("rev-parse", "HEAD"), git("rev-parse", "--abbrev-ref", "HEAD")
    src_sha, bin_sha = sha256(SRC), sha256(BIN)
    (OUT / mode).mkdir(parents=True, exist_ok=False)
    print(f"{mode}: {len(runs)} runs, {jobs} parallel; HEAD {head} ({branch}); source {src_sha[:16]}; "
          f"binary {bin_sha[:16]}", flush=True)
    stop = {"flag": False}

    def one(run_):
        if stop["flag"]:
            return run_["id"], None, 0.0, "skipped"
        d = OUT / mode / run_["id"]
        d.mkdir(exist_ok=False)
        argv = [str(ROOT / BIN)] + run_["args"] + [f"--outDir={d.relative_to(ROOT)}"]
        t0 = time.time()
        with open(d / "stdout.log", "x") as so, open(d / "stderr.log", "x") as se:
            rc = subprocess.run(argv, cwd=ROOT, stdout=so, stderr=se).returncode
        wall = time.time() - t0
        err = (d / "stderr.log").read_text()
        prov = dict(run_id=run_["id"], argv=argv, cwd=str(ROOT), git_head=head, git_branch=branch, source=SRC,
                    source_sha256=src_sha, binary=BIN, binary_sha256=bin_sha, exit_code=rc,
                    wall_sec=round(wall, 1), stderr_bytes=len(err), finished=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
        with open(d / "provenance.json", "x") as f:
            json.dump(prov, f, indent=1)
        if rc != 0 or err:
            stop["flag"] = True
        return run_["id"], rc, wall, err

    done = 0
    failed = []
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        futs = [ex.submit(one, r) for r in runs]
        for fu in as_completed(futs):
            rid, rc, wall, err = fu.result()
            done += 1
            if rc is None:
                continue
            print(f"[{done}/{len(runs)}] {rid}: exit {rc}, {wall:.1f} s, stderr {len(err)} B", flush=True)
            if rc != 0 or err:
                failed.append((rid, rc, err[-1500:]))
    if sha256(SRC) != src_sha or sha256(BIN) != bin_sha:
        sys.exit("source or binary changed during the batch")
    if failed:
        sys.exit(f"STOP: failed runs {failed}")
    print(f"{mode}: all {len(runs)} runs finished", flush=True)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--jobs=")]
    jobs = next((int(a.split("=")[1]) for a in sys.argv[1:] if a.startswith("--jobs=")), 6)
    if not args:
        sys.exit(__doc__)
    main(args[0], args[1] if len(args) > 1 else None, jobs)
