#!/usr/bin/env python3
"""risk-v2, N = 100 random risk-placement study (PROPOSED, not yet approved): 72 new runs =
static / riskaware / olsr x numHighRisk 3 x 8 and 32 kbps x topology seeds 20-22 x placement seeds 101-104.
The k = 0 runs do not depend on placement; the 18 validated ones (8 kbps: n100-8k-v2-20261024T165009, 32 kbps:
n100-sat-v2-20261025T112146) are reused in place (reuse_manifest.json) and never re-run.

    python3 -I -B experiments/wifi6-risk/run_n100_randplace.py --dry-run=<dir>      # no simulation
    caffeinate -i python3 -I -B experiments/wifi6-risk/run_n100_randplace.py [--jobs=6] [--placement=uniform|relay]
                                                                             [--batch=<batch dir to resume>]

Placement (fixed before any run, written to preregistration.json with the reference model's high-risk sets):
  uniform (default): the k sensors 0..N-1 with the smallest SplitMix64(SplitMix64(SplitMix64(P) ^ seed) ^ id), seed =
           topology seed; protocol-independent.
  relay: the simulator's --riskSelect=random rule (relays of the static 90 m BFS tree only).
Both are passed to the simulator as --riskSelect=ids --highRiskIds=<ids in rank order>, so the risk set is explicit
in every argv; every other argument equals run_n100_sat.py (run_pilot_n30.py BASE with --nSensors=100).

Phases (as run_n100_sat.py): subset (seed 20, placement 101, 3 protocols x 8 and 32 kbps: 6 runs) -> subset gate ->
the remaining 66 runs -> final gate. Gates: every run exit 0 with empty stderr, all output files, risk key_missing
= 0, finite metrics, then analyze_randplace.py on the whole batch (new + reused) with 0 failed checks.
A failed gate or a run with exit != 0 is critical: no new run is started, running ones finish, the batch is kept and
the runner exits 1. No automatic retries (deterministic simulation). Before starting and before each phase the
binary, the source and the 35 linked ns-3 libraries must match their validated sha256
(analysis/wifi6-n100-sat-report/SIMULATOR_LIBS.sha256).
One runner per batch (runner.lock with the owner's pid); no start while any risk-v2 simulator process is running.
On resume, preregistration.json must equal the reference model's sets, the scripts must equal the sha256 recorded in
batch.json, and the reused runs must match reuse_manifest.json.
Resume: a run whose provenance.json shows exit 0 is skipped; a run directory without provenance.json (interrupted) is
moved to <batch>/interrupted/; a run with a failed provenance.json stops the runner. Nothing is deleted.
"""
import importlib.util
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name, f):
    spec = importlib.util.spec_from_file_location(name, HERE / f)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


S = load("run_n100_sat", "run_n100_sat.py")    # P (run_pilot_n30 with N = 100), logging, execution, hashing
R = load("risk_ref", "risk_ref.py")
V = load("run_validation", "run_validation.py")
P, ROOT = S.P, S.ROOT
N = 100
PROTOS, K, RATES, SEEDS, PLACES = ("olsr", "static", "riskaware"), 3, (8, 32), (20, 21, 22), (101, 102, 103, 104)
REF = {8: ROOT / "results/wifi6-risk/n100-8k-v2-20261024T165009",
       32: ROOT / "results/wifi6-risk/n100-sat-v2-20261025T112146"}
LIBS = ROOT / "analysis/wifi6-n100-sat-report/SIMULATOR_LIBS.sha256"
SUBSET = [(p, K, 20, r, 101) for p in PROTOS for r in RATES]


def rid(p, k, s, r, pl):
    return f"{p}_k{k}_rate{r}_seed{s}_place{pl}"


def args(p, k, s, r, pl, ids):
    base = [a for a in P.BASE if not a.startswith("--riskSelect=")]
    return base + ["--riskSelect=ids", "--highRiskIds=" + ",".join(map(str, ids[:k])),
                   f"--protocol={p}", f"--numHighRisk={k}", f"--offeredRateKbps={r}", f"--seed={s}"]


SCRIPTS = ("run_n100_randplace.py", "analyze_randplace.py", "run_n100_sat.py", "run_pilot_n30.py", "risk_ref.py",
           "run_validation.py", "analyze_pilot_n30.py")


def script_hashes():
    return {f: S.sha_file(HERE / f) for f in SCRIPTS}


def take_lock(out):
    """One runner per batch: <batch>/runner.lock holds the owner's pid; a lock whose pid is gone is taken over."""
    lock = out / "runner.lock"
    if lock.exists():
        pid = int(lock.read_text().split()[0])
        if subprocess.run(["kill", "-0", str(pid)], capture_output=True).returncode == 0:
            sys.exit(f"STOP: runner pid {pid} already owns {out}")
    lock.write_text(f"{__import__('os').getpid()} {time.strftime('%Y-%m-%dT%H:%M:%S%z')}\n")


def check_hashes():
    errs = []
    if P.sha(P.BIN) != P.EXPECT_BIN or P.sha(P.SRC) != P.EXPECT_SRC:
        errs.append("risk-v2 binary or source differs from the validated version")
    for line in LIBS.read_text().splitlines():
        h, f = line.split(maxsplit=1)
        if S.sha_file(ROOT / f) != h:
            errs.append(f"library changed: {f}")
    return errs


def preregister(placement):
    """Ranking per (topology seed, placement seed) and the reference model's high-risk set for k = K."""
    out = {}
    for s in SEEDS:
        pos = V.positions(s, N)
        base = R.model(pos, N, k=0)
        for pl in PLACES:
            if placement == "uniform":
                # topology seed mixed in so that each (topology, placement) pair gets its own draw
                rank = sorted(range(N), key=lambda i: (R.splitmix64(R.splitmix64(R.splitmix64(pl) ^ s) ^ i), i))
            else:
                rank = R.ranking("random", N, base["hop"], base["desc"], base["degree"], select_seed=pl)
            m = R.model(pos, N, rule="ids", ids=rank[:K], k=K)
            out[f"{s}:{pl}"] = dict(ranking=rank[:10], high=sorted(m["high"]), high_order=rank[:K],
                                    bfs_descendants={str(i): base["desc"][i] for i in rank[:K]},
                                    hop={str(i): base["hop"][i] for i in rank[:K]},
                                    on_static_tree=[i for i in rank[:K] if base["desc"][i] >= 1])
    return out


def reuse_manifest(out):
    m = []
    for r in RATES:
        for s in SEEDS:
            for p in PROTOS:
                d = REF[r] / "runs" / P.rid(p, 0, s, r)
                pv = json.loads((d / "provenance.json").read_text())
                if pv["exit_code"] != 0 or pv["binary_sha256"] != P.EXPECT_BIN:
                    sys.exit(f"STOP: reference run {d.name} is not a validated run")
                m.append(dict(run_id=d.name, path=str(d.relative_to(ROOT)), argv=pv["argv"],
                              provenance_sha256=S.sha_file(d / "provenance.json"),
                              packet_paths_sha256=S.sha_file(d / "packet_paths.csv")))
    (out / "reuse_manifest.json").write_text(json.dumps(m, indent=1))
    return len(m)


def main():
    opts = dict(a.split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
    jobs = min(6, int(opts.get("--jobs", 6)))
    placement = opts.get("--placement", "uniform")
    assert placement in ("uniform", "relay")
    errs = check_hashes()
    if errs:
        sys.exit("STOP: " + "; ".join(errs))
    full = [(p, K, s, r, pl) for r in RATES for s in SEEDS for pl in PLACES for p in PROTOS]
    assert len(full) == 72 and len(set(full)) == 72 and all(c in full for c in SUBSET)
    if "--dry-run" in opts:   # write the plan, run nothing
        out = Path(opts["--dry-run"]).resolve()
        out.mkdir(parents=True, exist_ok=True)
        pre = preregister(placement)
        (out / "preregistration.json").write_text(json.dumps(dict(placement=placement, k=K, places=PLACES,
                                                                  sets=pre), indent=1))
        with open(out / "planned_argv.txt", "w") as f:
            for c in full:
                f.write(rid(*c) + "  " + " ".join(args(*c, pre[f"{c[2]}:{c[4]}"]["high_order"])) + "\n")
        print(f"dry run: {len(full)} runs planned, subset {len(SUBSET)}, hashes ok (binary, source, "
              f"{len(LIBS.read_text().splitlines())} libraries); free {shutil.disk_usage(ROOT).free / 1024 ** 3:.2f} GB; "
              f"wrote {out}")
        return
    busy = subprocess.run(["pgrep", "-f", P.BIN.name], capture_output=True, text=True).stdout.split()
    if busy:   # e.g. simulations orphaned by a killed runner: they would still write into run directories
        sys.exit(f"STOP: risk-v2 simulator processes already running: {busy}")
    free = shutil.disk_usage(ROOT).free
    if free < S.MIN_FREE_START:
        sys.exit(f"STOP: {free / 1024 ** 3:.2f} GB free, at least 5 GB required")
    if "--batch" in opts:
        out = Path(opts["--batch"]).resolve()
        take_lock(out)
        reg = json.loads((out / "preregistration.json").read_text())
        pre = reg["sets"]
        bj = json.loads((out / "batch.json").read_text())
        errs = []
        if json.loads(json.dumps(preregister(reg["placement"]))) != pre:
            errs.append("preregistration.json differs from the reference model")
        if bj.get("scripts_sha256") != script_hashes():
            errs.append("runner/analyzer/reference scripts changed since the batch was created")
        for m in json.loads((out / "reuse_manifest.json").read_text()):
            d = ROOT / m["path"]
            if S.sha_file(d / "provenance.json") != m["provenance_sha256"] or \
                    S.sha_file(d / "packet_paths.csv") != m["packet_paths_sha256"]:
                errs.append(f"reused run changed: {d.name}")
        if errs:
            sys.exit("STOP: " + "; ".join(errs))
        S.log(out, event="resume", free_gb=round(free / 1024 ** 3, 2))
    else:
        out = ROOT / "results/wifi6-risk" / time.strftime("n100-randplace-v2-%Y%m%dT%H%M%S")
        out.mkdir(parents=True)
        take_lock(out)
        pre = preregister(placement)
        (out / "preregistration.json").write_text(json.dumps(dict(placement=placement, k=K, places=PLACES,
                                                                  sets=pre), indent=1))
        (out / "batch.json").write_text(json.dumps(dict(
            binary=str(P.BIN), binary_sha256=P.EXPECT_BIN, source=str(P.SRC), source_sha256=P.EXPECT_SRC,
            libraries_sha256=str(LIBS.relative_to(ROOT)), base_args=P.BASE, n_sensors=N, protocols=PROTOS,
            num_high_risk=K, rates_kbps=RATES, seeds=SEEDS, placement=placement, placement_seeds=PLACES,
            subset=SUBSET, reused_k0={str(r): str(REF[r].relative_to(ROOT)) for r in RATES},
            simTime_s=300, appStart_s=30, max_jobs=jobs, scripts_sha256=script_hashes(), python=sys.version,
            created=time.strftime("%Y-%m-%dT%H:%M:%S%z")), indent=1))
        n = reuse_manifest(out)
        S.log(out, event="created", batch=str(out.relative_to(ROOT)), reused=n, free_gb=round(free / 1024 ** 3, 2))

    # run_n100_sat's execute()/gate() work on 4-tuples through P.rid / P.args; route them to the 5-tuple versions
    P.rid = rid
    P.args = lambda p, k, s, r, pl: args(p, k, s, r, pl, pre[f"{s}:{pl}"]["high_order"])
    S.PROTOS = PROTOS

    def gate(configs, name):
        errs = check_hashes()
        for c in configs:   # per-run integrity, as run_n100_sat.gate()
            d = out / "runs" / rid(*c)
            pv = json.loads((d / "provenance.json").read_text())
            if pv["exit_code"] != 0 or pv["stderr_bytes"] != 0 or pv["binary_sha256"] != P.EXPECT_BIN \
                    or pv["source_sha256"] != P.EXPECT_SRC:
                errs.append(f"{d.name}: provenance {pv['exit_code']} {pv['stderr_bytes']}")
            miss = [f for f in S.OUT_FILES if not (d / f).exists()]
            if miss:
                errs.append(f"{d.name}: missing {miss}")
                continue
            with open(d / "risk_summary.csv", newline="") as f:
                sm = list(S.csv.DictReader(f))[0]
            if int(sm["key_missing"]) != 0 or int(sm["app_tx_pkts"]) <= 0 or int(sm["delivered_unique"]) <= 0:
                errs.append(f"{d.name}: key_missing {sm['key_missing']} app_tx {sm['app_tx_pkts']}")
            for k2 in ("exposure_rate_pct", "mean_hops_delivered"):
                if not S.math.isfinite(float(sm[k2])):
                    errs.append(f"{d.name}: {k2} = {sm[k2]}")
        r = subprocess.run([sys.executable, "-I", "-B", str(HERE / "analyze_randplace.py"), str(out)],
                           cwd=ROOT, capture_output=True, text=True)
        (out / "analysis").mkdir(exist_ok=True)
        (out / "analysis" / f"analyze_{name}.log").write_text(r.stdout + r.stderr)
        chk = out / "analysis" / "CHECKS.txt"
        first = chk.read_text().splitlines()[0] if chk.exists() else ""
        if r.returncode != 0 or " 0 failed" not in first:
            errs.append(f"analyze_randplace: rc {r.returncode}; {first}")
        S.log(out, event="gate", gate=name, runs=len(configs), checks=first, errors=errs[:20])
        return "; ".join(errs[:5]) if errs else None

    t0 = time.time()
    err = S.execute(SUBSET, out, jobs, "subset") or gate(SUBSET, "subset")
    if err:
        S.log(out, event="STOPPED", phase="subset", reason=err, elapsed_min=round((time.time() - t0) / 60, 1))
        sys.exit(1)
    err = check_hashes()
    err = "; ".join(err) if err else (S.execute([c for c in full if c not in SUBSET], out, jobs, "full")
                                      or gate(full, "final"))
    if err:
        S.log(out, event="STOPPED", phase="full", reason=err, elapsed_min=round((time.time() - t0) / 60, 1))
        sys.exit(1)
    S.log(out, event="DONE", elapsed_min=round((time.time() - t0) / 60, 1))


if __name__ == "__main__":
    main()
