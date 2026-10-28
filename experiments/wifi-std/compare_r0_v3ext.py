#!/usr/bin/env python3
"""R0: flag-off regression of scratch/iot-network-wifi-std-arp.cc against results/v3-ext (static mobility).

    python3 -I -B experiments/wifi-std/compare_r0_v3ext.py              # results/wifi-std/arp-r0-off (15 runs)
    python3 -I -B experiments/wifi-std/compare_r0_v3ext.py --preview    # existing arp-phase1-off runs (16 / 4 kbps)

Every v3-ext column in compare_regression.V3_MAP is compared as text (the same mapping regression2 passed with);
the columns in V3_NOT_COMPARED are not compared, for the reasons listed there.
Traffic 'low' has no label in the new program: it is run as --trafficLevel=high --offeredRateKbps=4. For those runs
the TrafficLevel column is taken from the run id ('low'), and the program's own label/rate are checked separately
(trafficLevel == high, offered_rate_kbps == 4); DataRate ('4kbps') is compared from the program output as usual.
Excluded from the regression criterion (user decision 2026-10-18, see results/wifi-std/arp-r0-off/README.md):
PathChanges and UnreachableSensors differ by reporting definition, not by simulation. They are still printed
(as 'excluded, differs') but never cause a FAIL, and must not be used from -arp.cc in any analysis.
Exit 0 only if every compared value is identical and every expected file and row exists.
"""
import csv
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
W = ROOT / "results/wifi-std"
V3 = ROOT / "results/v3-ext"
spec = importlib.util.spec_from_file_location("cr", ROOT / "experiments/wifi-std/compare_regression.py")
cr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cr)
EXCLUDED = {
    "PathChanges": "-arp.cc samples routes for AODV only (iot-network-wifi-std-arp.cc:532-533); v3-ext samples "
                   "every protocol (iot-network-v3-ext.cc:505-513)",
    "UnreachableSensors": "-arp.cc counts BFS-unreachable sensors for every protocol (iot-network-wifi-std-arp.cc:"
                          "435-437); v3-ext counts them for static only (iot-network-v3-ext.cc:1190-1245)",
}


def rows(p):
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


def compare(rd, proto, n, traffic, seed, fails):
    pv = json.loads((rd / "provenance.json").read_text())
    if pv["exit_code"] != 0 or pv["stderr_bytes"] or pv.get("timed_out") or "--arpPrepopulate=1" in pv["argv"]:
        fails.append(f"{rd.name}: exit {pv['exit_code']} stderr {pv['stderr_bytes']} or flag on")
        return 0, 0
    f = V3 / f"{proto}_{n}_{traffic}_static.csv"
    ref = [r for r in rows(f) if r["Seed"] == str(seed)]
    if len(ref) != 1:
        fails.append(f"{f.name}: {len(ref)} rows for seed {seed}")
        return 0, 0
    agg, ext = rows(rd / "probe_aggregate.csv")[0], rows(rd / "wifistd_ext.csv")[0]
    uncovered = [c for c in ref[0] if c not in cr.V3_MAP and c not in cr.V3_NOT_COMPARED]
    fails += [f"{f.name}: column {c} neither compared nor listed" for c in uncovered]
    bad = 0
    for col, (src, key) in cr.V3_MAP.items():
        if col == "TrafficLevel" and traffic == "low":
            got = "low"
            if agg["trafficLevel"] != "high" or agg["offered_rate_kbps"] != "4":
                fails.append(f"{rd.name}: low run has trafficLevel={agg['trafficLevel']} "
                             f"offered_rate_kbps={agg['offered_rate_kbps']}")
                bad += 1
        else:
            got = (agg[key] if src == "agg" else ext[key] if src == "ext" else key if src == "const"
                   else key(agg, ext))
        if col in EXCLUDED:
            if got != ref[0][col]:
                print(f"    excluded, differs: {col} v3-ext {ref[0][col]!r} new {got!r}")
            continue
        if got != ref[0][col]:
            fails.append(f"{rd.name}: {col} v3-ext {ref[0][col]!r} new {got!r}")
            bad += 1
    k = len(cr.V3_MAP) - len(EXCLUDED)
    print(f"  {rd.name} vs {f.name} seed {seed}: {k} values, {bad} differ")
    return k, bad


def main():
    fails, vals, diffs = [], 0, 0
    if "--preview" in sys.argv:
        d, lab = W / "arp-phase1-off", {"16": "high", "4": "low"}
        runs = []
        for rd in sorted(d.iterdir()):
            m = re.fullmatch(r"b-off_(\w+?)_(\d+)_rate(\d+)_seed(\d+)", rd.name)
            if m and m[3] in lab:
                runs.append((rd, m[1], int(m[2]), lab[m[3]], int(m[4])))
    else:
        d = W / "arp-r0-off"
        b = json.loads((d / "batch.json").read_text())
        runs = []
        for rid in b["run_ids"]:
            m = re.fullmatch(r"b-off_(\w+?)_(\d+)_(low|medium|high)_seed(\d+)", rid)
            if not (d / rid / "provenance.json").exists():
                fails.append(f"{rid}: not complete")
                continue
            runs.append((d / rid, m[1], int(m[2]), m[3], int(m[4])))
    for r in runs:
        v, x = compare(*r, fails)
        vals, diffs = vals + v, diffs + x
    print("== excluded from the regression criterion (not used from -arp.cc in any analysis)")
    for c, why in EXCLUDED.items():
        print(f"  {c}: {why}")
    print("== v3-ext columns not compared")
    for c, why in cr.V3_NOT_COMPARED.items():
        print(f"  {c}: {why}")
    print(f"\nRESULT: runs {len(runs)}, values compared {vals}, differing values {diffs}, FAIL items {len(fails)}")
    for x in fails:
        print("  FAIL", x)
    print("R0", "PASS" if not fails and runs else "FAIL")
    return 0 if not fails and runs else 1


if __name__ == "__main__":
    sys.exit(main())
