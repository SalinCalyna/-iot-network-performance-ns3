#!/usr/bin/env python3
"""PSU Phuket campus-specific ns-3 study: run a pilot or the bounded matrix with the campus simulator variant.

    caffeinate -i python3 -I -B experiments/campus-sim/run_campus.py --phase=pilot  [--jobs=4]
    caffeinate -i python3 -I -B experiments/campus-sim/run_campus.py --phase=matrix [--jobs=4] [--seeds=1,2,3]
    python3 -I -B experiments/campus-sim/run_campus.py --phase=... --dry-run      # plan only, runs nothing

Simulator: scratch/iot-network-wifi6-campus.cc (risk-v2 + --positionsFile), positions from
analysis/campus-sim/inputs/positions_gw627751851.csv (83 sensors of the dashboard's proposed deployment + gateway).
Every run uses the validated Wi-Fi 6 risk-study arguments (802.11ax HE MCS0, 2.4 GHz / 20 MHz, log-distance exponent 3,
512 B CBR, 300 s, traffic from 30 s, ARP pre-filled, p_high = 0.5, beta = 10) plus --positionsFile; only protocol,
k, risk placement, rate and seed vary. --riskDropSeed = --seed, so the protocols of one (placement, seed) share the
traffic schedule, the risk set and every risk-drop decision (matched), and seeds are independent replications.
Risk placements: none (k = 0); subtree (k = 3, simulator rule: relays with most BFS descendants, the worst case for
Static); u101..u104 (k = 3, the k sensors with the smallest SplitMix64(SplitMix64(P) ^ id), as on the dashboard).
  pilot : static / riskaware / olsr x {none, subtree} x 8 kbps x seed 1                          = 6 runs
  matrix: static / riskaware / olsr x {none, subtree, u101..u104} x {8, 32} kbps x seeds (default 1,2,3) = 108 runs
          (the pilot's 6 runs are reused if the batch is the pilot batch; otherwise a new batch is created)
Safeguards: source, binary, positions and campus-library hashes are checked before starting and the run stops on any
mismatch; one runner per batch (runner.lock); no start below 2.0 GiB free and no new run below 1.0 GiB; a run with
exit != 0 or non-empty stderr stops further launches; an interrupted run directory is moved to <batch>/interrupted/
(never deleted). Each run writes provenance.json and outputs_sha256.json. Gates run analyze_campus.py and require
0 failed checks.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SRC = ROOT / "scratch/iot-network-wifi6-campus.cc"
BIN = ROOT / "build/scratch/ns3-dev-iot-network-wifi6-campus-default"
POSF = ROOT / "analysis/campus-sim/inputs/positions_gw627751851.csv"
LIBS = ROOT / "analysis/campus-sim/SIMULATOR_LIBS_CAMPUS.sha256"
N = 83
BASE = ["--standard=80211ax", f"--nSensors={N}", "--trafficLevel=high", "--arpPrepopulate=1", "--riskStudy=1",
        "--perPacketTrace=1", "--highRiskDropProb=0.5", "--lowRiskDropProb=0", "--riskBeta=10"]
PROTOS = ("olsr", "riskaware", "static")
UNIFORM = (101, 102, 103, 104)
MIN_FREE_START, MIN_FREE_RUN = int(2.0 * 1024 ** 3), int(1.0 * 1024 ** 3)
LOCK = threading.Lock()


def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def sm64(x):
    M = (1 << 64) - 1
    x = (x + 0x9E3779B97F4A7C15) & M
    x = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & M
    x = ((x ^ (x >> 27)) * 0x94D049BB133111EB) & M
    return x ^ (x >> 31)


def uniform_ids(P, k=3):
    h0 = sm64(P)
    return [i for _, i in sorted((sm64(h0 ^ i), i) for i in range(N))][:k]


def rid(p, k, pl, r, s):
    return f"{p}_k{k}_{pl}_rate{r}_seed{s}"


def args(p, k, pl, r, s):
    a = BASE + [f"--positionsFile={POSF.relative_to(ROOT)}", f"--protocol={p}", f"--numHighRisk={k}",
                f"--offeredRateKbps={r}", f"--seed={s}", f"--riskDropSeed={s}"]
    if pl in ("none", "subtree"):
        a.append("--riskSelect=subtree")
    else:
        a += ["--riskSelect=ids", "--highRiskIds=" + ",".join(map(str, uniform_ids(int(pl[1:]), k)))]
    return a


def plan(phase, seeds):
    if phase == "pilot":
        return [(p, k, pl, 8, 1) for p in PROTOS for k, pl in ((0, "none"), (3, "subtree"))]
    places = [(0, "none"), (3, "subtree")] + [(3, f"u{P}") for P in UNIFORM]
    return [(p, k, pl, r, s) for s in seeds for r in (8, 32) for k, pl in places for p in PROTOS]


def log(out, **ev):
    ev["time"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with LOCK, open(out / "status.jsonl", "a") as f:
        f.write(json.dumps(ev) + "\n")
    print(json.dumps(ev), flush=True)


def check_hashes(expect):
    errs = []
    for key, path in (("source_sha256", SRC), ("binary_sha256", BIN), ("positions_sha256", POSF)):
        if sha_file(path) != expect[key]:
            errs.append(f"{path.name} changed")
    bad = [l.split()[1] for l in LIBS.read_text().splitlines() if sha_file(ROOT / l.split()[1]) != l.split()[0]]
    if bad:
        errs.append(f"{len(bad)} libraries differ from {LIBS.name}")
    return errs


def run(c, out, state):
    name = rid(*c)
    d = out / "runs" / name
    d.mkdir(parents=True, exist_ok=False)
    argv = [str(BIN)] + args(*c) + [f"--outDir={d.relative_to(ROOT)}"]
    log(out, event="start", run=name)
    t0 = time.time()
    with open(d / "stdout.log", "x") as so, open(d / "stderr.log", "x") as se:
        rc = subprocess.run(argv, cwd=ROOT, stdout=so, stderr=se).returncode
    prov = dict(run_id=name, argv=argv, exit_code=rc, wall_sec=round(time.time() - t0, 1),
                stderr_bytes=(d / "stderr.log").stat().st_size, binary_sha256=sha_file(BIN), source_sha256=sha_file(SRC),
                positions_sha256=sha_file(POSF), finished=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    (d / "provenance.json").write_text(json.dumps(prov, indent=1))
    files = sorted(x for x in d.rglob("*") if x.is_file())
    (d / "outputs_sha256.json").write_text(json.dumps({str(x.relative_to(d)): dict(bytes=x.stat().st_size, sha256=sha_file(x)) for x in files}, indent=1))
    log(out, event="end", run=name, exit_code=rc, stderr_bytes=prov["stderr_bytes"], wall_sec=prov["wall_sec"])
    if rc != 0 or prov["stderr_bytes"] != 0:
        state["critical"] = f"run {name}: exit {rc}, stderr {prov['stderr_bytes']} B"


def pressure():
    try:
        lvl = int(subprocess.run(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"], capture_output=True, text=True, timeout=10).stdout.strip() or 1)
    except Exception:
        lvl = 1
    return lvl


def execute(todo, out, jobs, phase):
    pending = []
    for c in todo:
        d = out / "runs" / rid(*c)
        if d.exists():
            pv = d / "provenance.json"
            if pv.exists() and json.loads(pv.read_text())["exit_code"] == 0:
                continue
            if pv.exists():
                sys.exit(f"STOP: {d.name} has a failed provenance.json; inspect before resuming")
            dst = out / "interrupted" / time.strftime(f"{d.name}-%Y%m%dT%H%M%S")
            dst.parent.mkdir(exist_ok=True)
            shutil.move(str(d), str(dst))
            log(out, event="moved_interrupted", run=d.name, to=str(dst.relative_to(ROOT)))
        pending.append(c)
    pending.sort(key=lambda c: (-c[3], PROTOS.index(c[0])))   # 32 kbps and OLSR (slowest) first
    log(out, event="phase_start", phase=phase, runs=len(pending))
    state, threads = {}, []
    while pending or any(t.is_alive() for t in threads):
        threads = [t for t in threads if t.is_alive()]
        if pending and not state.get("critical"):
            lvl = pressure()
            allowed = min(jobs, 2) if lvl >= 4 else min(jobs, 3) if lvl >= 2 else jobs
            free = shutil.disk_usage(ROOT).free
            if free < MIN_FREE_RUN:
                state["critical"] = f"disk free {free / 1024 ** 3:.2f} GiB < 1.0 GiB"
            elif len(threads) < allowed:
                t = threading.Thread(target=run, args=(pending.pop(0), out, state))
                t.start()
                threads.append(t)
                time.sleep(2)
                continue
        if state.get("critical") and pending:
            log(out, event="stop_launching", reason=state["critical"], not_started=len(pending))
            pending = []
        time.sleep(5)
    log(out, event="phase_end", phase=phase, critical=state.get("critical"))
    return state.get("critical")


def gate(out, name, expect):
    errs = check_hashes(expect)
    r = subprocess.run([sys.executable, "-I", "-B", str(HERE / "analyze_campus.py"), str(out)], cwd=ROOT, capture_output=True, text=True)
    (out / "analysis").mkdir(exist_ok=True)
    (out / "analysis" / f"analyze_{name}.log").write_text(r.stdout + r.stderr)
    first = (r.stdout.splitlines() or ["(no output)"])[0]
    if r.returncode != 0 or " 0 failed" not in first:
        errs.append(first)
    log(out, event="gate", gate=name, checks=first, errors=errs)
    return errs


def main():
    opts = dict(a.split("=", 1) if "=" in a else (a, "") for a in sys.argv[1:])
    phase = opts.get("--phase")
    assert phase in ("pilot", "matrix"), "--phase=pilot|matrix"
    jobs = max(1, min(6, int(opts.get("--jobs", 4))))
    seeds = [int(x) for x in opts.get("--seeds", "1,2,3").split(",")]
    expect = dict(source_sha256=sha_file(SRC), binary_sha256=sha_file(BIN), positions_sha256=sha_file(POSF))
    todo = plan(phase, seeds)
    if "--dry-run" in opts:
        for c in todo:
            print(rid(*c), " ".join(args(*c)))
        print(f"{len(todo)} runs; uniform sets: " + "; ".join(f"u{P}: {uniform_ids(P)}" for P in UNIFORM) +
              f"; free {shutil.disk_usage(ROOT).free / 1024 ** 3:.2f} GiB")
        return
    errs = check_hashes(expect)
    if errs:
        sys.exit("STOP: " + "; ".join(errs))
    free = shutil.disk_usage(ROOT).free
    if free < MIN_FREE_START:
        sys.exit(f"STOP: {free / 1024 ** 3:.2f} GiB free, at least 2.0 GiB required")
    out = Path(opts["--batch"]).resolve() if "--batch" in opts else ROOT / "results/campus-sim" / time.strftime(f"campus-{phase}-%Y%m%dT%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    lock = out / "runner.lock"
    if lock.exists() and Path(f"/proc/{lock.read_text().split()[0]}").exists():
        sys.exit("STOP: another runner holds this batch")
    try:
        os.kill(int(lock.read_text().split()[0]), 0) if lock.exists() else None
        if lock.exists():
            sys.exit("STOP: another runner holds this batch")
    except (ProcessLookupError, ValueError):
        pass
    lock.write_text(f"{os.getpid()} {time.strftime('%Y-%m-%dT%H:%M:%S%z')}\n")
    if not (out / "batch.json").exists():
        (out / "batch.json").write_text(json.dumps(dict(
            study="PSU Phuket campus-specific ns-3 study (proposed deployment; not calibrated to campus measurements)",
            phase=phase, simulator=str(SRC.relative_to(ROOT)), binary=str(BIN.relative_to(ROOT)), **expect,
            libraries_manifest=str(LIBS.relative_to(ROOT)), positions_file=str(POSF.relative_to(ROOT)),
            topology_check="analysis/campus-sim/inputs/topology_check_gw627751851.json", n_sensors=N, base_args=BASE,
            protocols=list(PROTOS), seeds=seeds if phase == "matrix" else [1], uniform_placements=list(UNIFORM),
            runs=len(todo), max_jobs=jobs, created=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            host=dict(os=subprocess.run(["sw_vers", "-productVersion"], capture_output=True, text=True).stdout.strip(),
                      cpus=os.cpu_count(), python=sys.version.split()[0])), indent=1))
        (out / "preregistration.json").write_text(json.dumps(dict(
            rule="uniform: k sensors with the smallest SplitMix64(SplitMix64(P) ^ id); subtree: simulator rule",
            sets={f"u{P}": dict(high_order=uniform_ids(P)) for P in UNIFORM}), indent=1))
    log(out, event="created_or_resumed", batch=str(out.relative_to(ROOT)), runs=len(todo), free_gib=round(free / 1024 ** 3, 2))
    try:
        err = execute(todo, out, jobs, phase) or (gate(out, phase, expect) or None)
        log(out, event="DONE" if not err else "STOPPED", error=err)
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
