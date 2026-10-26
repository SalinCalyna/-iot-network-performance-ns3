#!/usr/bin/env python3
"""risk-v2, N = 100 saturated risk study (approved 2026-10-25): 72 new runs =
static / riskaware / olsr x numHighRisk 0-3 x 16 and 32 kbps per source x seeds 20-22. AODV is excluded.
The 36 validated 8 kbps runs of the same protocols (n100-8k-v2-20261024T165009) are reused in place
(reuse_manifest.json) as the light-load reference; they are never re-run.

    caffeinate -i python3 -I -B experiments/wifi6-risk/run_n100_sat.py [--jobs=6] [--batch=<batch dir to resume>]

Phases, without stopping between them unless a gate fails:
  1. subset: seed 20, 32 kbps, 3 protocols x k = 0 and 3 (6 runs)
  2. subset gate: every run exit 0 with empty stderr, all output files present, risk key_missing = 0, finite
     metrics; analyze_pilot_n30.py on the whole batch (new + reused runs) with 0 failed checks
  3. full: the remaining 66 runs
  4. final gate: the same checks on all 72 new runs, then analyze_paired_stats.py --descriptive per rate
     (outputs copied to analysis/rate<r>/, since that script writes fixed file names)
A failed gate or a run with exit != 0 is critical: no new run is started, running ones finish, the batch is kept and
the runner exits 1. There are no automatic retries (the simulation is deterministic).

Same simulator, fixed arguments and risk parameters as run_n100_8k.py (run_pilot_n30.py BASE with --nSensors=100);
only --offeredRateKbps differs. Resume: a run whose provenance.json shows exit 0 is skipped; a run directory without
provenance.json (interrupted) is moved to <batch>/interrupted/ before it is re-run. Nothing is deleted.
Records: batch.json (configuration), status.jsonl (one event per line: start/end/gate/concurrency/stop),
per run provenance.json (argv, exit, wall, binary and source sha256) and outputs_sha256.json (every output file).
Concurrency: at most --jobs; fewer when macOS reports memory pressure (warn: 4, critical: 2) or a CPU speed limit
below 80 % (thermal), and no new run when less than 1.5 GB of disk is free (stop).
"""
import csv
import hashlib
import importlib.util
import json
import math
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("run_pilot_n30", HERE / "run_pilot_n30.py")
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)
P.BASE = [a if a != "--nSensors=30" else "--nSensors=100" for a in P.BASE]
assert "--nSensors=100" in P.BASE
ROOT = P.ROOT
PROTOS, KS, RATES, SEEDS = ("olsr", "static", "riskaware"), (0, 1, 2, 3), (16, 32), (20, 21, 22)
REF_BATCH = ROOT / "results/wifi6-risk/n100-8k-v2-20261024T165009"
SUBSET = [(p, k, 20, 32) for p in PROTOS for k in (0, 3)]
OUT_FILES = ("probe_aggregate.csv", "risk_summary.csv", "risk_nodes.csv", "routes_planned.csv", "path_summary.csv",
             "packet_paths.csv", "risk_drops.csv", "wifi_readback.csv", "wifi_txvector_counts.csv", "wifistd_ext.csv",
             "ba_ssn_fix.csv")
MIN_FREE_START, MIN_FREE_RUN = 5 * 1024 ** 3, int(1.5 * 1024 ** 3)
LOCK = threading.Lock()


def log(out, **ev):
    ev["time"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with LOCK, open(out / "status.jsonl", "a") as f:
        f.write(json.dumps(ev) + "\n")
    print(json.dumps(ev), flush=True)


def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def hash_outputs(d):
    files = sorted(x for x in d.rglob("*") if x.is_file() and x.name != "outputs_sha256.json")
    m = {str(x.relative_to(d)): dict(bytes=x.stat().st_size, sha256=sha_file(x)) for x in files}
    (d / "outputs_sha256.json").write_text(json.dumps(m, indent=1))


def pressure():
    """(memory pressure level 1/2/4, CPU speed limit %) from macOS; (1, 100) if unavailable."""
    try:
        lvl = int(subprocess.run(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"], capture_output=True,
                                 text=True, timeout=10).stdout.strip() or 1)
    except Exception:
        lvl = 1
    lim = 100
    try:
        for line in subprocess.run(["pmset", "-g", "therm"], capture_output=True, text=True, timeout=10).stdout.splitlines():
            if "CPU_Speed_Limit" in line:
                lim = int(line.split("=")[1])
    except Exception:
        pass
    return lvl, lim


def allowed(jobs):
    lvl, lim = pressure()
    a = jobs
    if lvl >= 4:
        a = min(a, 2)
    elif lvl >= 2:
        a = min(a, 4)
    if lim < 80:
        a = max(1, min(a, jobs - 2))
    return a, lvl, lim


def one_run(c, out, state):
    name = P.rid(*c)
    log(out, event="start", run=name)
    prov = P.run(name, P.args(*c), out)
    d = out / "runs" / name
    hash_outputs(d)
    log(out, event="end", run=name, exit_code=prov["exit_code"], stderr_bytes=prov["stderr_bytes"],
        wall_sec=prov["wall_sec"])
    if prov["exit_code"] != 0 or prov["stderr_bytes"] != 0:
        state["critical"] = f"run {name}: exit {prov['exit_code']}, stderr {prov['stderr_bytes']} B"


def execute(todo, out, jobs, phase):
    pending = []
    for c in todo:
        d = out / "runs" / P.rid(*c)
        if d.exists():
            pv = d / "provenance.json"
            if pv.exists() and json.loads(pv.read_text())["exit_code"] == 0:
                continue
            if pv.exists():   # a completed failed run: kept, never overwritten
                sys.exit(f"STOP: {d.name} has a failed provenance.json; inspect before resuming")
            dst = out / "interrupted" / time.strftime(f"{d.name}-%Y%m%dT%H%M%S")
            dst.parent.mkdir(exist_ok=True)
            shutil.move(str(d), str(dst))
            log(out, event="moved_interrupted", run=d.name, to=str(dst.relative_to(ROOT)))
        pending.append(c)
    pending.sort(key=lambda c: (-c[3], PROTOS.index(c[0])))   # 32 kbps and OLSR (slowest) first
    log(out, event="phase_start", phase=phase, runs=len(pending))
    state, threads, last = {}, [], None
    while pending or any(t.is_alive() for t in threads):
        threads = [t for t in threads if t.is_alive()]
        if pending and not state.get("critical"):
            a, lvl, lim = allowed(jobs)
            if (a, lvl, lim) != last:
                log(out, event="concurrency", allowed=a, memory_pressure_level=lvl, cpu_speed_limit=lim)
                last = (a, lvl, lim)
            if shutil.disk_usage(ROOT).free < MIN_FREE_RUN:
                state["critical"] = f"disk free {shutil.disk_usage(ROOT).free / 1024 ** 3:.2f} GB < 1.5 GB"
            elif len(threads) < a:
                c = pending.pop(0)
                t = threading.Thread(target=one_run, args=(c, out, state))
                t.start()
                threads.append(t)
                time.sleep(2)
                continue
        if state.get("critical") and pending:
            log(out, event="stop_launching", reason=state["critical"], not_started=len(pending))
            pending = []
        time.sleep(10)
    log(out, event="phase_end", phase=phase, critical=state.get("critical"))
    return state.get("critical")


def gate(out, configs, name):
    """Integrity checks on the given new runs, then analyze_pilot_n30.py on the whole batch. Returns error or None."""
    errs = []
    for c in configs:
        d = out / "runs" / P.rid(*c)
        pv = json.loads((d / "provenance.json").read_text())
        if pv["exit_code"] != 0 or pv["stderr_bytes"] != 0 or pv["binary_sha256"] != P.EXPECT_BIN \
                or pv["source_sha256"] != P.EXPECT_SRC:
            errs.append(f"{d.name}: provenance {pv['exit_code']} {pv['stderr_bytes']}")
        miss = [f for f in OUT_FILES if not (d / f).exists()]
        if miss:
            errs.append(f"{d.name}: missing {miss}")
            continue
        with open(d / "risk_summary.csv", newline="") as f:
            s = list(csv.DictReader(f))[0]
        if int(s["key_missing"]) != 0:
            errs.append(f"{d.name}: key_missing {s['key_missing']}")
        if int(s["app_tx_pkts"]) <= 0 or int(s["delivered_unique"]) <= 0:
            errs.append(f"{d.name}: app_tx {s['app_tx_pkts']} delivered {s['delivered_unique']}")
        for k2 in ("exposure_rate_pct", "mean_hops_delivered"):
            if not math.isfinite(float(s[k2])):
                errs.append(f"{d.name}: {k2} = {s[k2]}")
    r = subprocess.run([sys.executable, "-I", "-B", str(HERE / "analyze_pilot_n30.py"), str(out)],
                       cwd=ROOT, capture_output=True, text=True)
    (out / "analysis").mkdir(exist_ok=True)
    (out / "analysis" / f"analyze_{name}.log").write_text(r.stdout + r.stderr)
    first = (out / "analysis" / "CHECKS.txt").read_text().splitlines()[0] if (out / "analysis" / "CHECKS.txt").exists() else ""
    if r.returncode != 0 or " 0 failed" not in first:
        errs.append(f"analyze_pilot_n30: rc {r.returncode}; {first}")
    log(out, event="gate", gate=name, runs=len(configs), checks=first, errors=errs[:20])
    return "; ".join(errs[:5]) if errs else None


def reuse_manifest(out):
    m = []
    for s in SEEDS:
        for p in PROTOS:
            for k in KS:
                d = REF_BATCH / "runs" / P.rid(p, k, s, 8)
                pv = json.loads((d / "provenance.json").read_text())
                if pv["exit_code"] != 0 or pv["binary_sha256"] != P.EXPECT_BIN:
                    sys.exit(f"STOP: reference run {d.name} is not a validated run")
                m.append(dict(run_id=d.name, path=str(d.relative_to(ROOT)), argv=pv["argv"],
                              provenance_sha256=sha_file(d / "provenance.json"),
                              packet_paths_sha256=sha_file(d / "packet_paths.csv")))
    (out / "reuse_manifest.json").write_text(json.dumps(m, indent=1))
    return len(m)


def main():
    opts = dict(a.split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
    jobs = min(6, int(opts.get("--jobs", 6)))
    if P.sha(P.BIN) != P.EXPECT_BIN or P.sha(P.SRC) != P.EXPECT_SRC:
        sys.exit("STOP: risk-v2 binary or source differs from the validated version")
    free = shutil.disk_usage(ROOT).free
    if free < MIN_FREE_START:
        sys.exit(f"STOP: {free / 1024 ** 3:.2f} GB free, at least 5 GB required")
    if "--batch" in opts:
        out = Path(opts["--batch"]).resolve()
        log(out, event="resume", free_gb=round(free / 1024 ** 3, 2))
    else:
        out = ROOT / "results/wifi6-risk" / time.strftime("n100-sat-v2-%Y%m%dT%H%M%S")
        out.mkdir(parents=True)
        (out / "batch.json").write_text(json.dumps(dict(
            binary=str(P.BIN), binary_sha256=P.EXPECT_BIN, source=str(P.SRC), source_sha256=P.EXPECT_SRC,
            base_args=P.BASE, n_sensors=100, protocols=PROTOS, num_high_risk=KS, rates_kbps=RATES, seeds=SEEDS,
            subset=SUBSET, reused_reference=str(REF_BATCH.relative_to(ROOT)), reused_rate_kbps=8,
            simTime_s=300, appStart_s=30, max_jobs=jobs, created=time.strftime("%Y-%m-%dT%H:%M:%S%z")), indent=1))
        n = reuse_manifest(out)
        log(out, event="created", batch=str(out.relative_to(ROOT)), reused=n, free_gb=round(free / 1024 ** 3, 2))
    t0 = time.time()
    full = [(p, k, s, r) for r in RATES for s in SEEDS for p in PROTOS for k in KS]
    assert len(full) == 72 and all(c in full for c in SUBSET)
    err = execute(SUBSET, out, jobs, "subset") or gate(out, SUBSET, "subset")
    if err:
        log(out, event="STOPPED", phase="subset", reason=err, elapsed_min=round((time.time() - t0) / 60, 1))
        sys.exit(1)
    err = execute([c for c in full if c not in SUBSET], out, jobs, "full") or gate(out, full, "final")
    if err:
        log(out, event="STOPPED", phase="full", reason=err, elapsed_min=round((time.time() - t0) / 60, 1))
        sys.exit(1)
    for r in RATES:
        res = subprocess.run([sys.executable, "-I", "-B", str(HERE / "analyze_paired_stats.py"), str(out),
                              f"--rate={r}", "--descriptive"], cwd=ROOT, capture_output=True, text=True)
        dst = out / "analysis" / f"rate{r}"
        dst.mkdir(exist_ok=True)
        (dst / "analyze_paired_stats.log").write_text(res.stdout + res.stderr)
        for f in ("stats_by_config.csv", "paired_riskaware_vs_static.csv", "STATS.txt"):
            if (out / "analysis" / f).exists():
                shutil.copy2(out / "analysis" / f, dst / f)
        log(out, event="paired_stats", rate=r, rc=res.returncode)
    log(out, event="DONE", elapsed_min=round((time.time() - t0) / 60, 1))


if __name__ == "__main__":
    main()
