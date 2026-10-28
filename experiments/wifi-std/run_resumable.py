#!/usr/bin/env python3
"""Resumable runner for scratch/iot-network-wifi-std.cc. Same run lists and argv as run_wifi_std.py (imported, not
edited); adds resume after an interruption, per-run timeout, and caffeinate.

    python3 -I -B experiments/wifi-std/run_resumable.py p1 p2 p3            # smoke resume passes, in order
    python3 -I -B experiments/wifi-std/run_resumable.py matrix-ax:128 matrix-b-aodv [--jobs=6] [--timeout=SEC]

Batches:
  p1  OLSR N=100 rate 64/128/256           -> results/wifi-std/smoke-resume-p1/   stop on failure
  p2  Static, all 8 smoke cells            -> results/wifi-std/smoke-resume-p2/   stop on failure
  p3  AODV N=100, 4 rates, 3600 s timeout  -> results/wifi-std/smoke-resume-p3/   timeout recorded, continue
  arp-regression | arp-phase1-off | arp-phase1-on | arp-smoke-ax-on | arp-smoke-ax-on-aodv100 | arp-ratesweep-on | arp-ratesweep-off | arp-b-on-os | arp-r0-off | arp-a2-on | arp-a1-on | arp-b1-on | arp-matrix-ax-on:<sat> | arp-matrix-b-on
      ARP study on scratch/iot-network-wifi-std-arp.cc -> results/wifi-std/<name>[-<sat>]/ (see arp_runs)
  <mode>[:<extra>]  any run_wifi_std.py mode -> results/wifi-std/<mode>/ (stop on failure unless --no-stop)
Batches named on one command line run one after another; a stop-on-failure batch that fails ends the chain.

Resume rules (re-running the same command after an interruption):
  * batch.json (written at first start) fixes the run list, source and binary SHA-256; a resume with a different
    source/binary/run list is refused. A batch directory without batch.json (e.g. made by run_smoke_resume.py) is
    adopted only if every provenance.json in it has the same source and binary hash.
  * a run directory WITH provenance.json is complete and is skipped (whatever its exit code; a recorded failure
    in a stop-on-failure batch ends the batch, it is not re-run).
  * a run directory WITHOUT provenance.json is incomplete: if a live process is using it (its --outDir appears in
    `ps`), the runner refuses to start; otherwise the directory is moved, unchanged, to
    results/wifi-std/incomplete/<batch>/<run_id>__moved-<timestamp>/ and logged in incomplete/MOVED.log.
    Nothing is deleted.
  * a lock file (<batch>/.runner.lock with the PID) refuses a second live runner on the same batch.
--park only moves incomplete run directories aside (reason in MOVED.log from --reason=...) and runs nothing.
Unless already running under it, the runner re-executes itself under `caffeinate -i`.
Console output is also appended to results/wifi-std/<batch dir name>_console.log.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("run_wifi_std", HERE / "run_wifi_std.py")
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)

SMOKE_SRC, SMOKE_BIN = "e715ccfa22af01ca", "ef5c54925b77b97e"   # hashes of the interrupted smoke batch
PASSES = {
    "p1": dict(ids=[f"ax_olsr_100_rate{r}_seed20" for r in (64, 128, 256)], timeout=None, stop=True),
    "p2": dict(ids=[f"ax_static_{n}_rate{r}_seed20" for n in (50, 100) for r in (16, 64, 128, 256)],
               timeout=None, stop=True),
    "p3": dict(ids=[f"ax_aodv_100_rate{r}_seed20" for r in (16, 64, 128, 256)], timeout=3600, stop=False),
}
INCOMPLETE = R.OUT / "incomplete"

# ARP study (2026-10-16): new source with --arpPrepopulate and ARP drop counters; the original is never edited.
ARP_SRC = "scratch/iot-network-wifi-std-arp.cc"
ARP_BIN = "build/scratch/ns3-dev-iot-network-wifi-std-arp-default"
ON = ["--arpPrepopulate=1"]


def arp_runs(name, extra):
    """Run lists of the ARP study. Ids carry the arm (b-off / b-on / ax-on) so arms never share a directory."""
    def mk(arm, std, p, n, rate, seed):
        r = R.run(f"{arm}_{p}_{n}_rate{rate}_seed{seed}", std, p, n, rate, seed)
        r["args"] += ON if arm.endswith("-on") else []
        return r

    def v3(p, n, traffic, seed, on):
        """v3-ext traffic labels: the id always carries the label; low = --trafficLevel=high --offeredRateKbps=4."""
        arm = "b-on" if on else "b-off"
        if traffic == "medium":
            r = R.run(f"{arm}_{p}_{n}_medium_seed{seed}", "80211b", p, n, None, seed)
            r["args"] = [a.replace("--trafficLevel=high", "--trafficLevel=medium") for a in r["args"]]
        else:
            r = R.run(f"{arm}_{p}_{n}_{traffic}_seed{seed}", "80211b", p, n, {"low": 4, "high": 16}[traffic], seed)
        r["args"] += ON if on else []
        return r
    if name == "arp-regression":            # regression2 run list, flag off, new binary
        return [dict(r, args=list(r["args"])) for r in R.runs_for("regression2", None)]
    if name in ("arp-phase1-off", "arp-phase1-on"):
        arm = "b-off" if name.endswith("off") else "b-on"
        return ([mk(arm, "80211b", "static", 50, r, s) for r in (16, 12, 8, 4) for s in (20, 25, 30)]
                + [mk(arm, "80211b", "olsr", n, 16, 20) for n in (75, 100)])
    if name == "arp-smoke-ax-on":           # 20 runs: OLSR N=100 64/128/256 first (saturation rule), then the rest
        first = [("olsr", 100, r) for r in (64, 128, 256)]
        rest = [(p, n, r) for p in ("olsr", "static", "aodv") for n in (50, 100) for r in (16, 64, 128, 256)
                if (p, n, r) not in first and not (p == "aodv" and n == 100)]
        return [mk("ax-on", "80211ax", p, n, r, 20) for p, n, r in first + rest]
    if name == "arp-smoke-ax-on-aodv100":   # 4 runs, run with --timeout=3600 --no-stop
        return [mk("ax-on", "80211ax", "aodv", 100, r, 20) for r in (16, 64, 128, 256)]
    if name in ("arp-ratesweep-on", "arp-ratesweep-off"):   # Phase I rate sweep: same 72 conditions/seeds
        arm = "b-on" if name.endswith("-on") else "b-off"
        return [mk(arm, "80211b", p, n, r, s) for p in ("static", "olsr") for n in (50, 75, 100)
                for r in (16, 12, 8, 4) for s in (20, 25, 30)]
    if name == "arp-matrix-ax-on":
        sat = int(extra)
        return [mk("ax-on", "80211ax", p, n, r, s) for p in ("aodv", "olsr", "static") for n in (50, 75, 100)
                for r in (16, sat) for s in R.SEEDS]
    if name == "arp-b-on-os":               # 66 runs: b-on OLSR + Static x N 50/75/100 x 16 kbps x seeds 20-30 (no AODV)
        return [mk("b-on", "80211b", p, n, 16, s) for p in ("olsr", "static") for n in (50, 75, 100)
                for s in R.SEEDS]
    if name == "arp-r0-off":                # 15 runs: flag-off regression vs results/v3-ext (compare_r0_v3ext.py)
        return ([v3(p, n, "high", 20, False) for p in ("aodv", "olsr", "static") for n in (10, 20, 50)]
                + [v3(p, 50, t, 20, False) for p in ("aodv", "olsr", "static") for t in ("low", "medium")])
    if name == "arp-a2-on":                 # 162 runs: 3 protocols x N 10-100 x low/medium/high x seeds 20/25/30
        return [v3(p, n, t, s, True) for p in ("aodv", "olsr", "static") for n in (10, 20, 30, 50, 75, 100)
                for t in ("low", "medium", "high") for s in (20, 25, 30)]
    if name == "arp-a1-on":                 # 96 runs: high x seeds 20-30, minus runs already in arp-a2-on (seeds
        #  20/25/30) and arp-b-on-os (OLSR/Static N 50/75/100, identical argv; 18/18 shared runs byte-identical)
        return [v3(p, n, "high", s, True) for p in ("aodv", "olsr", "static") for n in (10, 20, 30, 50, 75, 100)
                for s in R.SEEDS if s not in (20, 25, 30) and not (p != "aodv" and n >= 50)]
    if name == "arp-b1-on":                 # 64 runs: Table 4 (OLSR/Static x N=30 high + N 30-100 medium x 11 seeds =
        #  110) minus the 46 already in arp-a2-on / arp-a1-on with identical argv (N=30 high; medium seeds 20/25/30)
        return [v3(p, n, "medium", s, True) for p in ("olsr", "static") for n in (30, 50, 75, 100)
                for s in R.SEEDS if s not in (20, 25, 30)]
    if name == "arp-matrix-b-on":
        return [mk("b-on", "80211b", p, n, 16, s) for p in ("aodv", "olsr", "static") for n in (50, 75, 100)
                for s in R.SEEDS]
    return None


def batch_spec(name, timeout, no_stop):
    mode, _, extra = name.partition(":")
    ar = arp_runs(mode, extra)
    if ar is not None:
        return dict(name=name, dir=R.OUT / (mode + (f"-{extra}" if extra else "")), runs=ar, timeout=timeout,
                    stop=not no_stop, expect=None, src=ARP_SRC, bin=ARP_BIN)
    if name in PASSES:
        p = PASSES[name]
        smoke = {r["id"]: r for r in R.runs_for("smoke", None)}
        return dict(name=name, dir=R.OUT / f"smoke-resume-{name}", runs=[smoke[i] for i in p["ids"]],
                    timeout=p["timeout"], stop=p["stop"], expect=(SMOKE_SRC, SMOKE_BIN), src=R.SRC, bin=R.BIN)
    return dict(name=name, dir=R.OUT / mode, runs=R.runs_for(mode, extra or None), timeout=timeout,
                stop=not no_stop, expect=None, src=R.SRC, bin=R.BIN)


def live_outdirs():
    ps = subprocess.run(["ps", "-axww", "-o", "command="], capture_output=True, text=True).stdout
    return [line for line in ps.splitlines() if "--outDir=" in line]


def pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def log_to(path):
    f = open(path, "a")

    def say(msg):
        print(msg, flush=True)
        f.write(msg + "\n")
        f.flush()
    return say


def run_batch(b, jobs, park=False, reason="no provenance.json (run interrupted)"):
    d = b["dir"]
    say = log_to(R.OUT / f"{d.name}_console.log")
    head, branch = R.git("rev-parse", "HEAD"), R.git("rev-parse", "--abbrev-ref", "HEAD")
    src_sha, bin_sha = R.sha256(b['src']), R.sha256(b['bin'])
    ids = [r["id"] for r in b["runs"]]
    if b["expect"] and not (src_sha.startswith(b["expect"][0]) and bin_sha.startswith(b["expect"][1])):
        sys.exit(f"{b['name']}: source/binary {src_sha[:16]}/{bin_sha[:16]} differ from the smoke batch")

    d.mkdir(parents=False, exist_ok=True)
    lock = d / ".runner.lock"
    if lock.exists():
        old = int(lock.read_text().split()[0] or 0)
        if old and pid_alive(old):
            sys.exit(f"{b['name']}: another runner (pid {old}) holds {lock}")
    lock.write_text(f"{os.getpid()} {time.strftime('%Y-%m-%dT%H:%M:%S%z')}\n")

    meta_p = d / "batch.json"
    meta = dict(batch=b["name"], run_ids=ids, source=b['src'], source_sha256=src_sha, binary=b['bin'],
                binary_sha256=bin_sha, timeout_sec=b["timeout"], stop_on_failure=b["stop"])
    if meta_p.exists():
        old = json.loads(meta_p.read_text())
        for k in ("run_ids", "source_sha256", "binary_sha256", "timeout_sec", "stop_on_failure"):
            if old[k] != meta[k]:
                sys.exit(f"{b['name']}: resume refused, {k} differs from {meta_p}")
    else:
        for pv in d.glob("*/provenance.json"):
            p = json.loads(pv.read_text())
            if (p["source_sha256"], p["binary_sha256"]) != (src_sha, bin_sha) or p["run_id"] not in ids:
                sys.exit(f"{b['name']}: cannot adopt {d}: {pv} has another source/binary or run id")
        meta.update(created=time.strftime("%Y-%m-%dT%H:%M:%S%z"), git_head=head, git_branch=branch,
                    adopted_existing=any(d.iterdir()))
        meta_p.write_text(json.dumps(meta, indent=1))

    stray = [x.name for x in d.iterdir() if x.is_dir() and x.name not in ids]
    if stray:
        sys.exit(f"{b['name']}: unexpected directories in {d}: {stray}")

    todo, recorded_fail = [], []
    live = live_outdirs()
    for r in b["runs"]:
        rd = d / r["id"]
        if (rd / "provenance.json").exists():
            p = json.loads((rd / "provenance.json").read_text())
            if p.get("timed_out") or p["exit_code"] != 0 or p["stderr_bytes"]:
                recorded_fail.append(r["id"])
            continue
        if rd.exists():
            rel = f"--outDir={rd.relative_to(R.ROOT)}"
            if any(rel in line for line in live):
                sys.exit(f"{b['name']}: {r['id']} is incomplete but a live process uses it; not touching it")
            stamp = time.strftime("%Y%m%dT%H%M%S")
            dst = INCOMPLETE / d.name / f"{r['id']}__moved-{stamp}"
            dst.parent.mkdir(parents=True, exist_ok=True)
            contents = sorted(f"{x.name}:{x.stat().st_size}" for x in rd.rglob("*") if x.is_file())
            shutil.move(str(rd), str(dst))
            with open(INCOMPLETE / "MOVED.log", "a") as f:
                f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')}\t{rd.relative_to(R.ROOT)}\t->\t"
                        f"{dst.relative_to(R.ROOT)}\t{reason}\tfiles={contents}\n")
            say(f"{b['name']}: moved incomplete {r['id']} -> {dst.relative_to(R.ROOT)}")
        todo.append(r)
    if park:
        lock.unlink(missing_ok=True)
        say(f"{b['name']}: --park: incomplete runs moved aside, nothing run ({len(todo)} not complete)")
        return True
    if recorded_fail and b["stop"]:
        sys.exit(f"{b['name']}: STOP, failed runs already recorded: {recorded_fail}")

    say(f"{b['name']}: {len(ids)} runs, {len(ids) - len(todo)} already complete, {len(todo)} to run, {jobs} parallel, "
        f"timeout {b['timeout']}; HEAD {head} ({branch}); source {src_sha[:16]}; binary {bin_sha[:16]}; "
        f"started {time.strftime('%Y-%m-%dT%H:%M:%S%z')}")
    stop = {"flag": False}

    def one(run_):
        if stop["flag"]:
            return run_["id"], None, 0.0, "", False
        rd = d / run_["id"]
        rd.mkdir(exist_ok=False)
        argv = [str(R.ROOT / b['bin'])] + run_["args"] + [f"--outDir={rd.relative_to(R.ROOT)}"]
        t0, timed_out = time.time(), False
        with open(rd / "stdout.log", "x") as so, open(rd / "stderr.log", "x") as se:
            try:
                rc = subprocess.run(argv, cwd=R.ROOT, stdout=so, stderr=se, timeout=b["timeout"]).returncode
            except subprocess.TimeoutExpired:
                rc, timed_out = None, True
        wall = time.time() - t0
        err = (rd / "stderr.log").read_text()
        prov = dict(run_id=run_["id"], argv=argv, cwd=str(R.ROOT), git_head=head, git_branch=branch, source=b['src'],
                    source_sha256=src_sha, binary=b['bin'], binary_sha256=bin_sha, exit_code=rc,
                    wall_sec=round(wall, 1), stderr_bytes=len(err), timeout_sec=b["timeout"], timed_out=timed_out,
                    finished=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
        with open(rd / "provenance.json", "x") as f:
            json.dump(prov, f, indent=1)
        if b["stop"] and (timed_out or rc != 0 or err):
            stop["flag"] = True
        return run_["id"], rc, wall, err, timed_out

    done, failed = 0, []
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        for fu in as_completed([ex.submit(one, r) for r in todo]):
            rid, rc, wall, err, to = fu.result()
            done += 1
            if rc is None and not to:
                continue
            status = "TIMEOUT" if to else f"exit {rc}"
            say(f"[{done}/{len(todo)}] {rid}: {status}, {wall:.1f} s, stderr {len(err)} B")
            if to or rc != 0 or err:
                failed.append((rid, status, err[-1500:]))
    lock.unlink(missing_ok=True)
    if R.sha256(b['src']) != src_sha or R.sha256(b['bin']) != bin_sha:
        sys.exit("source or binary changed during the batch")
    say(f"{b['name']}: finished {time.strftime('%Y-%m-%dT%H:%M:%S%z')}; problems {failed if failed else 'none'}")
    return not (failed and b["stop"])


def main():
    if os.environ.get("WIFISTD_CAFFEINATED") != "1":
        env = dict(os.environ, WIFISTD_CAFFEINATED="1")
        os.execvpe("caffeinate", ["caffeinate", "-i", sys.executable, "-I", "-B", __file__, *sys.argv[1:]], env)
    opts = {a.split("=")[0]: (a.split("=", 1)[1] if "=" in a else "1") for a in sys.argv[1:] if a.startswith("--")}
    names = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not names:
        sys.exit(__doc__)
    jobs = int(opts.get("--jobs", 6))
    timeout = int(opts["--timeout"]) if "--timeout" in opts else None
    for n in names:
        if not run_batch(batch_spec(n, timeout, "--no-stop" in opts), jobs, park="--park" in opts,
                         reason=opts.get("--reason", "no provenance.json (run interrupted)")):
            sys.exit(f"{n}: STOP, later batches not started")


if __name__ == "__main__":
    main()
