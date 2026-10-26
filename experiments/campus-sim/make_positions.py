#!/usr/bin/env python3
"""PSU Phuket campus study: build and verify the ns-3 positions file from the dashboard's proposed deployment.

    python3 -I -B experiments/campus-sim/make_positions.py [--gateway=<OSM way id>]

Input: analysis/campus-sim/inputs/campus.json (= site/data/campus/campus.json of commit 66b422f4e, the deployed
Smart Campus dashboard; built from the frozen OSM snapshot by build_site_campus.py).
Node set exactly as the dashboard's "Proposed smart-campus deployment" with all four applications: every proposed
sensor except one placed at the gateway building's own centroid, in the dashboard's order (sensor ids are the
dashboard ids), then the gateway. Coordinates are the dashboard's local metric frame (x east, y north, metres from
the campus polygon's vertex mean, equirectangular); nothing is moved, rounded further or added.
Writes analysis/campus-sim/inputs/:
  positions_gw<id>.csv   node_id,x,y  (simulator input; gateway = last row)
  node_map_gw<id>.csv    node_id, role, application, x, y, lat, lon, OSM source of the point
  topology_check_gw<id>.json  counts, pairwise-distance summary, connected components and gateway reachability
                         under the 90 m link model (and at 116.6 m, the longest hop observed in the validated runs),
                         hop and degree distributions, and the share of 90 m links whose straight segment crosses an
                         OSM building footprint (descriptive: the radio model has no buildings)
Stops if a coordinate converts back to lat/lon more than 0.02 m from the dashboard's lat/lon (the two
roundings in campus.json allow at most 0.015 m), if two nodes coincide,
or if any sensor cannot reach the gateway under the 90 m model.
"""
import csv
import hashlib
import json
import math
import sys
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IN = ROOT / "analysis/campus-sim/inputs"
TX, TX_OBS = 90.0, 116.6


def seg_cross(p, q, a, b):
    d = lambda u, v, w: (v[0] - u[0]) * (w[1] - u[1]) - (v[1] - u[1]) * (w[0] - u[0])
    d1, d2, d3, d4 = d(a, b, p), d(a, b, q), d(p, q, a), d(p, q, b)
    return (d1 > 0) != (d2 > 0) and (d3 > 0) != (d4 > 0)


def inside(pt, poly):
    c = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > pt[1]) != (y2 > pt[1]) and pt[0] < (x2 - x1) * (pt[1] - y1) / (y2 - y1) + x1:
            c = not c
    return c


def bfs(adj, gw):
    hop = [-1] * len(adj)
    hop[gw] = 0
    q = deque([gw])
    while q:
        u = q.popleft()
        for v in adj[u]:
            if hop[v] < 0:
                hop[v] = hop[u] + 1
                q.append(v)
    return hop


def components(adj):
    seen, comps = [False] * len(adj), []
    for s in range(len(adj)):
        if not seen[s]:
            comp, q = [], [s]
            seen[s] = True
            while q:
                u = q.pop()
                comp.append(u)
                for v in adj[u]:
                    if not seen[v]:
                        seen[v] = True
                        q.append(v)
            comps.append(sorted(comp))
    return comps


def main():
    opts = dict(a.split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
    raw = (IN / "campus.json").read_bytes()
    C = json.loads(raw)
    gid = int(opts.get("--gateway", C["proposed"]["default_gateway"]))
    g = next(x for x in C["proposed"]["gateways"] if x["id"] == gid)
    sensors = [s for s in C["proposed"]["sensors"] if f"OSM way {gid}" not in s["src"]]   # as campus.js
    f = C["frame"]
    pos = [s["xy"] for s in sensors] + [g["xy"]]
    lls = [s["ll"] for s in sensors] + [g["ll"]]
    n, gw = len(pos), len(pos) - 1
    errs = []
    for i, (p, ll) in enumerate(zip(pos, lls)):   # metric -> lat/lon round trip against the dashboard's own values
        lat, lon = f["lat0"] + p[1] / f["m_per_deg_lat"], f["lon0"] + p[0] / f["m_per_deg_lon"]
        e = math.hypot((lat - ll[0]) * f["m_per_deg_lat"], (lon - ll[1]) * f["m_per_deg_lon"])
        if e > 0.02:   # dashboard rounding: xy to 0.01 m (<= 0.0071 m) + lat/lon to 1e-7 deg (<= 0.0078 m)
            errs.append(f"node {i}: frame round trip {e:.3f} m")
    D = [[math.dist(pos[i], pos[j]) for j in range(n)] for i in range(n)]
    dmin = min(D[i][j] for i in range(n) for j in range(i + 1, n))
    if dmin <= 0:
        errs.append("coincident nodes")
    adj = [[j for j in range(n) if j != i and D[i][j] <= TX] for i in range(n)]
    adj_obs = [[j for j in range(n) if j != i and D[i][j] <= TX_OBS] for i in range(n)]
    hop, hop_obs = bfs(adj, gw), bfs(adj_obs, gw)
    if any(h < 0 for h in hop[:gw]):
        errs.append(f"unreachable under 90 m: {[i for i in range(gw) if hop[i] < 0]}")
    bld = [[(( ll[1] - f["lon0"]) * f["m_per_deg_lon"], (ll[0] - f["lat0"]) * f["m_per_deg_lat"]) for ll in b["ring"]] for b in C["buildings"]]
    links = [(i, j) for i in range(n) for j in adj[i] if i < j]
    crossing = sum(1 for i, j in links if any(any(seg_cross(pos[i], pos[j], r[k], r[k + 1]) for k in range(len(r) - 1)) for r in bld))
    in_bld = [i for i in range(gw) if any(inside(pos[i], r) for r in bld)]
    if errs:
        sys.exit("STOP: " + "; ".join(errs))
    tag = f"gw{gid}"
    with open(IN / f"positions_{tag}.csv", "w", newline="") as fh:
        fh.write("node_id,x,y\n")
        for i, p in enumerate(pos):
            fh.write(f"{i},{p[0]},{p[1]}\n")
    with open(IN / f"node_map_{tag}.csv", "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["node_id", "role", "application", "x_m", "y_m", "lat", "lon", "source"])
        for i, s in enumerate(sensors):
            w.writerow([i, "sensor", s["app"], s["xy"][0], s["xy"][1], s["ll"][0], s["ll"][1], s["src"]])
        w.writerow([gw, "gateway", "", g["xy"][0], g["xy"][1], g["ll"][0], g["ll"][1], f"centroid of OSM way {gid} ({g['name']})"])
    hist = lambda xs: {str(k): xs.count(k) for k in sorted(set(xs))}
    apps = {}
    for s in sensors:
        apps[s["app"]] = apps.get(s["app"], 0) + 1
    chk = dict(input=dict(file="analysis/campus-sim/inputs/campus.json", sha256=hashlib.sha256(raw).hexdigest(),
                          source="site/data/campus/campus.json at commit 66b422f4e"),
               gateway=dict(osm_way=gid, name=g["name"], xy=g["xy"], ll=g["ll"]),
               n_sensors=gw, applications=apps, frame=f,
               extent_m=dict(x=[min(p[0] for p in pos), max(p[0] for p in pos)], y=[min(p[1] for p in pos), max(p[1] for p in pos)]),
               min_pairwise_distance_m=round(dmin, 3), frame_round_trip_max_error_m="<= 0.02 (rounding of the dashboard values)",
               link_model_90m=dict(links=len(links), components=len(components(adj)), unreachable=[i for i in range(gw) if hop[i] < 0],
                                   max_hop=max(hop), hop_histogram=hist(hop[:gw]), mean_degree=round(sum(map(len, adj)) / n, 2),
                                   gateway_degree=len(adj[gw]), links_crossing_osm_building=crossing),
               at_116_6m=dict(components=len(components(adj_obs)), max_hop=max(hop_obs), mean_degree=round(sum(map(len, adj_obs)) / n, 2)),
               sensors_inside_osm_building_footprint=in_bld)
    (IN / f"topology_check_{tag}.json").write_text(json.dumps(chk, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({k: chk[k] for k in ("n_sensors", "applications", "min_pairwise_distance_m", "link_model_90m", "at_116_6m")}, ensure_ascii=False))
    print("positions sha256:", hashlib.sha256((IN / f"positions_{tag}.csv").read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
