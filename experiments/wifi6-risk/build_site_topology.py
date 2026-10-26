#!/usr/bin/env python3
"""Build the dashboard topology data for the Wi-Fi 6 risk study (read-only on results/).

    python3 -I -B experiments/wifi6-risk/build_site_topology.py <site dir>

Writes <site>/data/topology/index.json and one file per topology (N, seed). Everything shown is read from the
validated runs' own outputs; nothing is simulated or estimated:
  pernode/probe_*.csv     node coordinates x, y (as printed by the simulator), packets forwarded, gateway airtime
  risk_nodes.csv          hop, degree, risk state and score, transit packets eligible / risk-dropped per node
  routes_planned.csv      per source: installed path, BFS path, Risk-Aware path and their route costs
  path_summary.csv        per source and observed path: packets, delivered, risk-dropped, lost otherwise (link usage,
                          per-source totals and each source's three most-used paths are kept)
  <batch>/analysis/pilot_runs.csv   run metrics (nominal PDR, exposure, p95 delay, gateway airtime)
The only reconstruction is the 90 m link model (the simulator's --txRange disk graph used by Static and
Risk-Aware), computed from the printed coordinates. The build stops unless, for every run: (1) the coordinates
equal those of every other run of the same (N, seed); (2) every node's link count equals the simulator's degree;
(3) BFS and the Risk-Aware Dijkstra re-implemented from the source reproduce routes_planned.csv for every source;
(4) every route cost equals hops + beta * sum of tau over transit nodes; (5) the batch's CHECKS.txt has 0 failed.
"""
import csv
import hashlib
import heapq
import json
import math
import sys
from collections import defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "results/wifi6-risk"
# validated batches whose results appear on the dashboard or in the reports; the 64 kbps pilot runs are excluded
BATCHES = {"seeds10-n30-8k-v2-20261024T160515": "N = 30, subtree placement, 8 kbps (10 seeds)",
           "n100-8k-v2-20261024T165009": "N = 100, subtree placement, 8 kbps",
           "n100-sat-v2-20261025T112146": "N = 100, subtree placement, 16 / 32 kbps (saturated study)",
           "n100-randplace-v2-20261026T032146": "N = 100, uniform random placement, 8 / 32 kbps"}
METRICS = ("pdr_nominal_pct", "exposure_rate_pct", "delay_p95_ms", "gw_airtime", "risk_dropped_pkts", "mean_hops_delivered")
TX_RANGE = 90.0


def rows(p):
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


def arg(argv, k):
    return next(a.split("=", 1)[1] for a in argv if a.startswith(f"--{k}="))


def nodes_of(path):
    return [int(x) for x in path.split(">")] if path else []


def main():
    site = Path(sys.argv[1])
    out = site / "data/topology"
    out.mkdir(parents=True, exist_ok=True)
    errs, runs, checks, src_sha = [], [], {}, {}
    seen = set()
    for b, desc in BATCHES.items():
        bd = RES / b
        line = (bd / "analysis/CHECKS.txt").read_text().splitlines()[0]
        if not line.endswith(" 0 failed"):
            errs.append(f"{b}: {line}")
        checks[b] = dict(description=desc, checks=line)
        metrics = {r["run"]: r for r in rows(bd / "analysis/pilot_runs.csv")}
        src_sha[f"results/wifi6-risk/{b}/analysis/pilot_runs.csv"] = hashlib.sha256((bd / "analysis/pilot_runs.csv").read_bytes()).hexdigest()
        dirs = sorted(d for d in (bd / "runs").iterdir() if (d / "provenance.json").exists())
        if (bd / "reuse_manifest.json").exists():
            dirs += [ROOT / m["path"] for m in json.loads((bd / "reuse_manifest.json").read_text())]
        for d in dirs:
            if d.resolve() in seen:
                continue
            seen.add(d.resolve())
            runs.append((b, d, metrics.get(d.name)))
    topo = {}
    for b, d, met in runs:
        pv = json.loads((d / "provenance.json").read_text())
        argv = pv["argv"]
        N, seed, proto = int(arg(argv, "nSensors")), int(arg(argv, "seed")), arg(argv, "protocol")
        k, rate, beta = int(arg(argv, "numHighRisk")), int(float(arg(argv, "offeredRateKbps"))), float(arg(argv, "riskBeta"))
        place = "subtree" if arg(argv, "riskSelect") == "subtree" else d.name.split("_place")[1]
        if met is None:
            errs.append(f"{d.name}: no metrics row in {b}")
            continue
        gw, n = N, N + 1
        pn = rows(next((d / "pernode").glob("*.csv")))
        pos = [[float(r["x"]), float(r["y"])] for r in pn]
        t = topo.setdefault((N, seed), dict(N=N, seed=seed, pos=pos, runs=[]))
        if t["pos"] != pos:
            errs.append(f"{d.name}: coordinates differ from other runs of N={N} seed={seed}")
        adj = [[j for j in range(n) if j != i and math.dist(pos[i], pos[j]) <= TX_RANGE] for i in range(n)]
        rn = {int(r["node_id"]): r for r in rows(d / "risk_nodes.csv")}
        if any(len(adj[i]) != int(rn[i]["degree"]) for i in range(n)):
            errs.append(f"{d.name}: link model does not reproduce the simulator's degree")
        hop, bpar = [-1] * n, [-1] * n
        hop[gw] = 0
        q = deque([gw])
        while q:
            u = q.popleft()
            for v in adj[u]:
                if hop[v] < 0:
                    hop[v], bpar[v] = hop[u] + 1, u
                    q.append(v)
        r_ = [float(rn[i]["risk_score"]) for i in range(n)]
        tau = [0.0 if i == gw else -math.log1p(-r_[i]) for i in range(n)]
        dist, rpar, done, order = [math.inf] * n, [-1] * n, [False] * n, 1
        dist[gw] = 0.0
        pq = [(0.0, 0, gw)]
        while pq:
            dd, _, v = heapq.heappop(pq)
            if done[v]:
                continue
            done[v] = True
            w = 1.0 + beta * tau[v]
            for u in adj[v]:
                if not done[u] and dd + w < dist[u]:
                    dist[u], rpar[u] = dd + w, v
                    heapq.heappush(pq, (dd + w, order, u))
                    order += 1

        def walk(par, i):
            p = [i]
            while p[-1] != gw and par[p[-1]] >= 0:
                p.append(par[p[-1]])
            return p

        def cost(p):   # entering each node after the source costs 1 + beta * tau (tau_gateway = 0)
            return sum(1.0 + beta * tau[v] for v in p[1:])
        rp = {int(r["src"]): r for r in rows(d / "routes_planned.csv")}
        for i in range(N):
            r = rp[i]
            if r["reachable"] != "1":
                continue
            for col, par in (("bfs", bpar), ("riskaware", rpar)):
                p = walk(par, i)
                if r[f"{col}_path"] != ">".join(map(str, p)) or abs(float(r[f"{col}_risk_cost"]) - cost(p)) > 1e-4 * max(1, cost(p)):
                    errs.append(f"{d.name} src {i}: {col} path/cost not reproduced")
        if "bfs" not in t:
            t.update(bfs=bpar, hop=hop, degree=[len(a) for a in adj],
                     links=[[i, j] for i in range(n) for j in adj[i] if i < j])
        elif t["bfs"] != bpar:
            errs.append(f"{d.name}: BFS tree differs between runs of the same topology")
        uses, per_src, paths = defaultdict(int), [[0, 0, 0] for _ in range(N)], defaultdict(list)
        for r in rows(d / "path_summary.csv"):
            p, pk = nodes_of(r["path"]), int(r["packets"])
            for a, c in zip(p, p[1:]):
                uses[(a, c)] += pk
            s = int(r["src"])
            per_src[s][0] += pk
            per_src[s][1] += int(r["delivered"])
            per_src[s][2] += int(r["risk_dropped"])
            paths[s].append([pk, int(r["delivered"]), p])
        high = sorted((int(rn[i]["high_risk_rank"]), i) for i in range(N) if rn[i]["risk_state"] == "HIGH_RISK")
        installed = None
        if proto in ("static", "riskaware"):
            installed = [-1] * n
            for i in range(N):
                p = nodes_of(rp[i]["installed_path"]) if rp[i]["reachable"] == "1" else []
                if len(p) > 1:
                    installed[i] = p[1]
            if installed[:N] != (bpar if proto == "static" else rpar)[:N]:
                errs.append(f"{d.name}: installed routes differ from the {proto} tree")
        t["runs"].append(dict(
            id=d.name, batch=b, protocol=proto, k=k, rate=rate, place=place,
            high=[i for _, i in high], risk_p=float(arg(argv, "highRiskDropProb")), beta=beta,
            ra=rpar, cost_bfs=[round(cost(walk(bpar, i)), 4) if hop[i] > 0 else None for i in range(N)],
            cost_ra=[round(dist[i], 4) if math.isfinite(dist[i]) else None for i in range(N)],
            installed=installed is not None,
            uses=sorted([a, c, v] for (a, c), v in uses.items()), src=per_src,
            paths=[[[pk, dl, p] for pk, dl, p in sorted(paths[i], key=lambda x: (-x[0], x[2]))[:3]] for i in range(N)],
            n_paths=[len(paths[i]) for i in range(N)],
            fwd=[int(r["l3_unicast_forwarded"]) for r in pn], busy=[round(float(r["airtime_busy_frac"]), 4) for r in pn],
            elig=[int(rn[i]["eligible_transit_pkts"]) for i in range(N)], rdrop=[int(rn[i]["risk_dropped"]) for i in range(N)],
            metrics={m: round(float(met[m]), 4) for m in METRICS}))
    if errs:
        sys.exit("STOP: " + "; ".join(errs[:20]) + (f" (+{len(errs) - 20} more)" if len(errs) > 20 else ""))
    index = dict(generated_by="experiments/wifi6-risk/build_site_topology.py", tx_range_m=TX_RANGE, area_m=250.0,
                 batches=checks, sources=src_sha,
                 verification=f"{len(runs)} runs: coordinates identical within each topology; 90 m link model reproduces the "
                              f"simulator's degree for every node; BFS and Risk-Aware trees and route costs reproduce "
                              f"routes_planned.csv for every reachable source; all batch checks 0 failed",
                 topologies=[])
    for (N, seed), t in sorted(topo.items()):
        t["runs"].sort(key=lambda r: (r["place"] != "subtree", r["place"], r["rate"], r["k"], r["protocol"]))
        fn = f"n{N}_seed{seed}.json"
        (out / fn).write_text(json.dumps(t, separators=(",", ":")) + "\n")
        index["topologies"].append(dict(N=N, seed=seed, file=fn, runs=len(t["runs"]),
                                        options=sorted({(r["place"], r["rate"], r["k"], r["protocol"]) for r in t["runs"]})))
    (out / "index.json").write_text(json.dumps(index, indent=1) + "\n")
    print(f"wrote {out}: {len(topo)} topologies, {len(runs)} runs; all verifications passed")


if __name__ == "__main__":
    main()
