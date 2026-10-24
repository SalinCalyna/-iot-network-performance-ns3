"""Independent Python reference for scratch/iot-network-wifi6-risk.cc (risk-v1).

Written separately from the C++ (not generated from it) so that the validation tests can compare the
simulator's risk assignment, routing trees, path costs and drop decisions against a second implementation.
Inputs are node positions (sensors 0..N-1, gateway N) exactly as the simulator writes them to pernode/*.csv.
"""
import math
from collections import deque
import heapq

MASK = (1 << 64) - 1


def splitmix64(x):
    x = (x + 0x9E3779B97F4A7C15) & MASK
    x = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & MASK
    x = ((x ^ (x >> 27)) * 0x94D049BB133111EB) & MASK
    return x ^ (x >> 31)


def risk_uniform(seed, node, src, seq):
    h = splitmix64(splitmix64(splitmix64(splitmix64(seed) ^ node) ^ src) ^ seq)
    return (h >> 11) * (1.0 / 9007199254740992.0)


def disk_graph(pos, tx_range):
    """pos: list of (x, y) for all nodes (sensors then gateway). Adjacency lists in ascending order."""
    n = len(pos)
    adj = [[] for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if math.hypot(pos[i][0] - pos[j][0], pos[i][1] - pos[j][1]) <= tx_range:
                adj[i].append(j)
                adj[j].append(i)
    return adj


def bfs_tree(adj, gw):
    n = len(adj)
    hop, parent = [-1] * n, [-1] * n
    hop[gw] = 0
    q = deque([gw])
    while q:
        u = q.popleft()
        for v in adj[u]:
            if hop[v] < 0:
                hop[v], parent[v] = hop[u] + 1, u
                q.append(v)
    return hop, parent


def descendants(parent, n_sensors, gw):
    d = [0] * len(parent)
    for i in range(n_sensors):
        a = parent[i]
        while a >= 0 and a != gw:
            d[a] += 1
            a = parent[a]
    return d


def ranking(rule, n_sensors, hop, desc, degree, select_seed=1, ids=None):
    if rule == "ids":
        return list(ids)
    cand = [i for i in range(n_sensors) if hop[i] >= 1 and desc[i] >= 1]
    if rule == "subtree":
        key = lambda i: (-desc[i], -degree[i], 0, i)
    elif rule == "degree":
        key = lambda i: (-degree[i], -desc[i], 0, i)
    elif rule == "random":
        key = lambda i: (0, 0, splitmix64(splitmix64(select_seed) ^ i), i)
    else:
        raise ValueError(rule)
    return sorted(cand, key=key)


def risk_tree(adj, gw, tau, beta):
    """Dijkstra from the gateway; entering transit v costs 1 + beta*tau[v]; ties by order of assignment."""
    n = len(adj)
    dist, parent, done = [math.inf] * n, [-1] * n, [False] * n
    order = 0
    dist[gw] = 0.0
    pq = [(0.0, order, gw)]
    order += 1
    while pq:
        d, _, v = heapq.heappop(pq)
        if done[v]:
            continue
        done[v] = True
        w = 1.0 + beta * (0.0 if v == gw else tau[v])
        for u in adj[v]:
            if done[u]:
                continue
            nd = d + w
            if nd < dist[u]:
                dist[u], parent[u] = nd, v
                heapq.heappush(pq, (nd, order, u))
                order += 1
    return dist, parent


def path_of(parent, s, gw):
    p, a, guard = [], parent[s], 0
    while a >= 0 and guard <= len(parent):
        p.append(a)
        if a == gw:
            break
        a = parent[a]
        guard += 1
    return p if p and p[-1] == gw else []


def path_cost(path, tau, beta, gw):
    return sum(1.0 + beta * (0.0 if v == gw else tau[v]) for v in path)


def safe_reach(adj, gw, high):
    """Nodes that can reach the gateway without a HIGH_RISK node as a relay (a HIGH source may send)."""
    seen = [False] * len(adj)
    seen[gw] = True
    q = deque([gw])
    while q:
        v = q.popleft()
        if v != gw and v in high:
            continue
        for u in adj[v]:
            if not seen[u]:
                seen[u] = True
                q.append(u)
    return seen


def wilson(k, n, z=3.2905):   # 99.9 % two-sided
    if n == 0:
        return (0.0, 1.0)
    ph = k / n
    den = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / den
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    return (c - h, c + h)


def model(pos, n_sensors, tx_range=90.0, rule="subtree", k=0, p_high=0.5, p_low=0.0, beta=10.0, select_seed=1,
          ids=None):
    gw = n_sensors
    adj = disk_graph(pos, tx_range)
    hop, parent = bfs_tree(adj, gw)
    desc = descendants(parent, n_sensors, gw)
    degree = [len(a) for a in adj]
    rank = ranking(rule, n_sensors, hop, desc, degree, select_seed, ids)
    high = set(rank[:k])
    p = [p_low] * n_sensors + [0.0]
    for h in high:
        p[h] = p_high
    tau = [-math.log1p(-x) for x in p]
    dist, ra_parent = risk_tree(adj, gw, tau, beta)
    return dict(gw=gw, adj=adj, hop=hop, parent=parent, desc=desc, degree=degree, rank=rank, high=high, p=p,
                tau=tau, ra_dist=dist, ra_parent=ra_parent, safe=safe_reach(adj, gw, high))
