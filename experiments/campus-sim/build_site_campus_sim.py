#!/usr/bin/env python3
"""Build the dashboard data for "PSU Phuket Campus Simulation Results" (read-only on results/ and analysis/).

    python3 -I -B experiments/campus-sim/build_site_campus_sim.py <batch dir> <site dir>

Writes <site>/data/campus-sim.json from the campus matrix batch:
  nodes      node map (dashboard id, application, local metres, lat/lon, OSM source) from analysis/campus-sim/inputs
  links      the 90 m link model (reconstructed from the positions file; must reproduce every run's degree)
  runs       seed 1 of every (protocol, placement, rate): high-risk set, installed tree (Static / Risk-Aware, from
             routes_planned.csv), observed link usage and each source's 3 most-used paths (path_summary.csv), per-source
             sent / delivered / risk-dropped, packets forwarded per node, run metrics (pilot_runs.csv)
  stats      by_protocol, paired, per_placement, k0_baseline from <batch>/analysis/stats/ (analyze_campus_stats.py)
Cross-checks (any failure stops the build): CHECKS.txt has 0 failed; every run's pernode coordinates equal the
positions file within 0.001 m; the link model reproduces the simulator's degree for every node; the installed tree of
every Static / Risk-Aware run equals the reference model (risk_ref.py) tree for its risk set; every by_protocol mean
is recomputed from pilot_runs.csv. Source files are listed with sha256.
"""
import csv
import hashlib
import importlib.util
import json
import math
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("risk_ref", ROOT / "experiments/wifi6-risk/risk_ref.py")
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)
SRC = {}


def rd(p):
    p = Path(p)
    SRC[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


def main():
    b, site = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
    errs = []
    batch = json.loads((b / "batch.json").read_text())
    N = batch["n_sensors"]
    checks = (b / "analysis/CHECKS.txt").read_text().splitlines()[0]
    if not checks.endswith(" 0 failed"):
        errs.append("CHECKS: " + checks)
    pos = [(float(r["x"]), float(r["y"])) for r in rd(ROOT / batch["positions_file"])]
    nmap = rd(ROOT / "analysis/campus-sim/inputs/node_map_gw627751851.csv")
    topo = json.loads((ROOT / batch["topology_check"]).read_text())
    runs_csv = {r["run"]: r for r in rd(b / "analysis/pilot_runs.csv")}
    adj = [[j for j in range(N + 1) if j != i and math.dist(pos[i], pos[j]) <= 90.0] for i in range(N + 1)]
    pre = json.loads((b / "preregistration.json").read_text())["sets"]
    out_runs, wall = [], defaultdict(list)
    for d in sorted((b / "runs").iterdir()):
        pv = json.loads((d / "provenance.json").read_text())
        p, k, pl, r, s = d.name.split("_")
        k, rate, seed = int(k[1:]), int(r[4:]), int(s[4:])
        wall[(p, rate)].append(pv["wall_sec"])
        pn = rd(next((d / "pernode").glob("*.csv")))
        if any(abs(float(x["x"]) - pos[i][0]) > 1e-3 or abs(float(x["y"]) - pos[i][1]) > 1e-3 for i, x in enumerate(pn)):
            errs.append(f"{d.name}: coordinates differ from the positions file")
        rn = {int(x["node_id"]): x for x in rd(d / "risk_nodes.csv")}
        if any(len(adj[i]) != int(rn[i]["degree"]) for i in range(N + 1)):
            errs.append(f"{d.name}: link model does not reproduce degree")
        if seed != 1:
            SRC.pop(str((next((d / "pernode").glob("*.csv"))).relative_to(ROOT)), None)
            SRC.pop(str((d / "risk_nodes.csv").relative_to(ROOT)), None)
            continue
        high = [i for _, i in sorted((int(rn[i]["high_risk_rank"]), i) for i in range(N) if rn[i]["risk_state"] == "HIGH_RISK")]
        m = R.model(pos, N, k=k, p_high=0.5, p_low=0.0, beta=10.0) if pl in ("none", "subtree") else \
            R.model(pos, N, rule="ids", ids=pre[pl]["high_order"][:k], k=k, p_high=0.5, p_low=0.0, beta=10.0)
        if sorted(m["high"]) != sorted(high):
            errs.append(f"{d.name}: high-risk set differs from the reference model")
        tree = None
        if p in ("static", "riskaware"):
            tree = [-1] * (N + 1)
            for x in rd(d / "routes_planned.csv"):
                path = [int(v) for v in x["installed_path"].split(">")] if x["installed_path"] else []
                if len(path) > 1:
                    tree[int(x["src"])] = path[1]
            ref = m["parent"] if p == "static" else m["ra_parent"]
            if tree[:N] != [ref[i] if ref[i] is not None else -1 for i in range(N)]:
                errs.append(f"{d.name}: installed tree differs from the reference model")
        uses, src, paths = defaultdict(int), [[0, 0, 0] for _ in range(N)], defaultdict(list)
        for x in rd(d / "path_summary.csv"):
            path, pk = [int(v) for v in x["path"].split(">")], int(x["packets"])
            for a, c in zip(path, path[1:]):
                uses[(a, c)] += pk
            i = int(x["src"])
            src[i][0] += pk
            src[i][1] += int(x["delivered"])
            src[i][2] += int(x["risk_dropped"])
            paths[i].append([pk, int(x["delivered"]), path])
        met = runs_csv[d.name]
        out_runs.append(dict(id=d.name, protocol=p, k=k, place=pl, rate=rate, seed=seed, high=high, tree=tree,
                             uses=sorted([a, c, v] for (a, c), v in uses.items()), src=src,
                             paths=[sorted(paths[i], key=lambda z: (-z[0], z[2]))[:3] for i in range(N)], n_paths=[len(paths[i]) for i in range(N)],
                             fwd=[int(x["l3_unicast_forwarded"]) for x in pn],
                             metrics={c: round(float(met[c]), 4) for c in ("pdr_nominal_pct", "exposure_rate_pct", "sink_thr_kbps", "lost_pkts",
                                                                           "delay_p50_ms", "delay_p95_ms", "mean_hops_delivered", "gw_airtime", "mpdu_retry_drop")}))
    sd = b / "analysis/stats"
    by = rd(sd / "by_protocol.csv")
    k3 = [r for r in runs_csv.values() if r["k"] == "3"]
    for x in by:
        v = [float(r["pdr_nominal_pct"]) for r in k3 if r["protocol"] == x["protocol"] and r["rate_kbps"] == x["rate_kbps"]]
        if abs(st.mean(v) - float(x["pdr_nominal_pct_mean"])) > 1e-9:
            errs.append(f"by_protocol {x['rate_kbps']} {x['protocol']}: mean not reproduced")
    if errs:
        sys.exit("STOP: " + "; ".join(errs[:20]))
    # "nan" (exact Wilcoxon p when all 15 differences are 0, class identical) and "" -> null
    fl = lambda v: None if v in ("", "nan") else float(v)
    num = lambda r: {k: (v if k in ("protocol", "A", "B", "metric", "place", "class", "placement_means", "per_draw", "high_risk_ids") else fl(v)) for k, v in r.items()}
    out = dict(
        generated_by="experiments/campus-sim/build_site_campus_sim.py", batch=str(b.relative_to(ROOT)), checks=checks,
        design=dict(n_sensors=N, protocols=batch["protocols"], seeds=batch["seeds"], rates=[8, 32], placements=["none", "subtree"] + [f"u{P}" for P in batch["uniform_placements"]],
                    uniform_sets={k: v["high_order"] for k, v in pre.items()}, simulator=batch["simulator"], source_sha256=batch["source_sha256"],
                    binary_sha256=batch["binary_sha256"], positions_sha256=batch["positions_sha256"], libraries_manifest=batch["libraries_manifest"],
                    runs=len(runs_csv), base_args=batch["base_args"]),
        runtime=dict(total_run_hours=round(sum(sum(v) for v in wall.values()) / 3600, 2),
                     mean_wall_min={f"{p}_{r}": round(st.mean(v) / 60, 1) for (p, r), v in sorted(wall.items())}),
        topology=dict(links=[[i, j] for i in range(N + 1) for j in adj[i] if i < j], max_hop=topo["link_model_90m"]["max_hop"],
                      mean_degree=topo["link_model_90m"]["mean_degree"], links_crossing_osm_building=topo["link_model_90m"]["links_crossing_osm_building"],
                      hop=[int(x) for x in [rn[i]["hop_to_gw"] for i in range(N + 1)]]),
        nodes=[dict(id=int(x["node_id"]), role=x["role"], app=x["application"], xy=[float(x["x_m"]), float(x["y_m"])], ll=[float(x["lat"]), float(x["lon"])], src=x["source"]) for x in nmap],
        runs=out_runs,
        stats=dict(by_protocol=[num(x) for x in by], paired=[num(x) for x in rd(sd / "paired.csv")],
                   per_placement=[num(x) for x in rd(sd / "per_placement.csv")], k0_baseline=[num(x) for x in rd(sd / "k0_baseline.csv")]),
        sources=SRC)
    (site / "data").mkdir(parents=True, exist_ok=True)
    (site / "data/campus-sim.json").write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n")
    print(f"wrote campus-sim.json: {len(out_runs)} map runs, {len(runs_csv)} runs in stats, {len(SRC)} sources; all cross-checks passed")


if __name__ == "__main__":
    main()
