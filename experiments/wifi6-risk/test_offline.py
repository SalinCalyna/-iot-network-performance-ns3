#!/usr/bin/env python3
"""Offline tests of the risk-v1 reference model (no simulator, no build).

    python3 -I -B experiments/wifi6-risk/test_offline.py

They check the rules the simulator must follow on synthetic and v3-style random topologies. They test the
Python reference only; experiments/wifi6-risk/run_validation.py compares the simulator against it.
"""
import importlib.util
import math
import random
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("risk_ref", Path(__file__).with_name("risk_ref.py"))
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)

FAILS, PASSES = [], 0


def check(name, cond, detail=""):
    global PASSES
    if cond:
        PASSES += 1
    else:
        FAILS.append(f"{name}: {detail}")


def v3_positions(n, seed, area=250.0):
    """Not the C++ mt19937 stream: only a realistic random layout for property tests."""
    rng = random.Random(seed)
    return [(rng.uniform(0, area), rng.uniform(0, area)) for _ in range(n)] + [(area / 2, area / 2)]


def main():
    # 1. hash: range, determinism, independence of the key fields
    us = [R.risk_uniform(1, node, src, seq) for node in range(5) for src in range(5) for seq in range(200)]
    check("hash range", all(0.0 <= u < 1.0 for u in us))
    check("hash deterministic", R.risk_uniform(7, 3, 4, 5) == R.risk_uniform(7, 3, 4, 5))
    check("hash key sensitive", len({R.risk_uniform(1, 2, 3, s) for s in range(1000)}) == 1000)
    frac = sum(u < 0.5 for u in us) / len(us)
    lo, hi = R.wilson(sum(u < 0.5 for u in us), len(us))
    check("hash ~ uniform", lo <= 0.5 <= hi, f"frac {frac}")

    # 2. hand-made graph: gateway 6; two routes from 0: 0-1-6 (short) and 0-2-3-6
    #    adjacency by explicit coordinates on a line/ladder with range 1.0
    pos = [(0, 0), (1, 0), (0, 1), (1, 1), (3, 3), (4, 3), (2, 0.5)]
    #  hand adjacency instead of geometry
    adj = [[1, 2], [0, 6], [0, 3], [2, 6], [5], [4], [1, 3]]
    gw = 6
    hop, parent = R.bfs_tree(adj, gw)
    check("bfs hops", hop[:4] == [2, 1, 2, 1] and hop[4] == -1, hop)
    tau0 = [0.0] * 7
    d, rp = R.risk_tree(adj, gw, tau0, 10.0)
    check("dijkstra == bfs without risk", rp[:4] == parent[:4], (rp, parent))
    tau = [0.0] * 7
    tau[1] = -math.log1p(-0.5)
    d, rp = R.risk_tree(adj, gw, tau, 10.0)
    check("riskaware avoids high relay", R.path_of(rp, 0, gw) == [2, 3, 6], R.path_of(rp, 0, gw))
    check("riskaware cost", abs(d[0] - 3.0) < 1e-12, d[0])
    d, rp = R.risk_tree(adj, gw, tau, 0.0)
    check("beta=0 equals hop count", R.path_of(rp, 0, gw) == [1, 6])
    safe = R.safe_reach(adj, gw, {1})
    check("safe path exists for 0", safe[0])
    safe = R.safe_reach(adj, gw, {1, 3})
    check("no safe path for 0 when 1 and 3 high", not safe[0])
    check("high source still reaches", safe[1])
    check("unreachable stays unreachable", not safe[4])

    # 3. random v3-style topologies: properties over many seeds and N
    for n in (10, 20, 30, 50, 75, 100):
        for seed in range(20, 31):
            pos = v3_positions(n, seed)
            for rule in ("subtree", "degree", "random"):
                ms = [R.model(pos, n, rule=rule, k=k) for k in range(4)]
                m0 = ms[0]
                if len(m0["rank"]) < 3:
                    continue
                # nested, deterministic, relays only, gateway never
                sets = [sorted(m["high"]) for m in ms]
                check("nested", all(set(sets[k]) <= set(sets[k + 1]) for k in range(3)), (n, seed, rule, sets))
                check("sizes", [len(s) for s in sets] == [0, 1, 2, 3], (n, seed, rule))
                check("relays only", all(m0["hop"][h] >= 1 and m0["desc"][h] >= 1 for h in sets[3]))
                check("gateway never", n not in sets[3])
                check("deterministic", R.model(pos, n, rule=rule, k=3)["high"] == ms[3]["high"])
                # k=0: riskaware tree identical to BFS tree
                check("k0 tree == bfs", m0["ra_parent"][:n] == m0["parent"][:n], (n, seed, rule))
                for m in ms:
                    gw = m["gw"]
                    for s in range(n):
                        pb = R.path_of(m["parent"], s, gw)
                        pr = R.path_of(m["ra_parent"], s, gw)
                        reach = m["hop"][s] >= 1
                        check("connectivity same", bool(pb) == reach and bool(pr) == reach, (n, seed, s))
                        if not reach:
                            continue
                        cb = R.path_cost(pb, m["tau"], 10.0, gw)
                        cr = R.path_cost(pr, m["tau"], 10.0, gw)
                        check("riskaware optimal", cr <= cb + 1e-9 and abs(cr - m["ra_dist"][s]) < 1e-9,
                              (n, seed, s, cr, cb))
                        check("loop free", len(set(pr)) == len(pr))
                        hb = sum(v in m["high"] for v in pb if v != gw)
                        hr = sum(v in m["high"] for v in pr if v != gw)
                        if hb == 0:
                            check("unexposed unchanged cost", abs(cr - cb) < 1e-9, (n, seed, s))
                        if hr > 0 and m["safe"][s]:
                            # risky path kept only if every safe path is longer by more than the penalty
                            check("keeps risk only if detour too long", cr <= cb + 1e-9)
    print(f"offline tests: {PASSES} passed, {len(FAILS)} failed")
    for f in FAILS[:20]:
        print("  FAIL", f)
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
