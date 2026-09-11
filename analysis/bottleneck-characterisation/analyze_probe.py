#!/usr/bin/env python3
"""
Section 10 - Instrumented Bottleneck Probe: loss-localisation analysis.
READ-ONLY. Consumes:
  data/probe_aggregate.csv            (one row per run)
  data/pernode/probe_<proto>_<n>_<traffic>_seed<s>.csv  (one row per node)
Writes only NEW artifacts under analysis/bottleneck-characterisation/:
  T_probe_aggregate_by_cell.csv
  T_probe_hopbin_by_cell.csv
  T_probe_concentration.csv
  T_probe_correlations.csv
  PROBE_ANALYSIS_DATA.json
No existing file is modified.
"""
import csv, glob, json, math, os, statistics as st
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
AGG  = os.path.join(BASE, "data", "probe_aggregate.csv")
PN   = os.path.join(BASE, "data", "pernode")
OUT  = BASE

def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return math.nan

# ----------------------------------------------------------------------------
# 1. Load aggregate rows
# ----------------------------------------------------------------------------
agg_rows = []
with open(AGG) as fh:
    for r in csv.DictReader(fh):
        agg_rows.append(r)

def cell_key(r):
    return (r["protocol"], int(r["nodes"]), r["trafficLevel"])

agg_by_cell = defaultdict(list)
for r in agg_rows:
    agg_by_cell[cell_key(r)].append(r)

AGG_NUM = ["pdr","throughputKbps","avgDelaySec","avgJitterSec","unreachableSensors",
           "routingOverheadPkts","total_phy_rx_drops","total_mac_queue_drops",
           "total_ip_drop_no_route","total_ip_drop_ttl","total_ip_drop_route_error",
           "total_ip_drop_queue","total_ip_drop_other","gw_airtime_busy_frac",
           "ring1_airtime_busy_frac_mean","rest_airtime_busy_frac_mean","ring1_node_count",
           "txPkts","rxPkts"]

def summ(vals):
    vals = [v for v in vals if not math.isnan(v)]
    if not vals:
        return dict(n=0, mean=math.nan, sd=math.nan, med=math.nan, mn=math.nan, mx=math.nan)
    return dict(n=len(vals), mean=st.fmean(vals),
                sd=(st.pstdev(vals) if len(vals) > 1 else 0.0),
                med=st.median(vals), mn=min(vals), mx=max(vals))

agg_cell_summary = {}
for k, rows in sorted(agg_by_cell.items()):
    d = {"protocol": k[0], "nodes": k[1], "trafficLevel": k[2], "n_seeds": len(rows)}
    for col in AGG_NUM:
        s = summ([fnum(r[col]) for r in rows])
        d[col + "_mean"] = s["mean"]
        d[col + "_sd"]   = s["sd"]
    # derived: delivered fraction (== pdr/100), nominal PHY headroom
    d["delivered_frac_mean"] = d["pdr_mean"] / 100.0
    agg_cell_summary[k] = d

# ----------------------------------------------------------------------------
# 2. Per-node: bin by hop distance, accumulate per cell across seeds
# ----------------------------------------------------------------------------
def hopbin(h):
    if h < 0:      return "unreach"
    if h == 0:     return "gw"
    if h == 1:     return "hop1"
    if h == 2:     return "hop2"
    if h == 3:     return "hop3"
    return "hop4+"

BIN_ORDER = ["gw","hop1","hop2","hop3","hop4+","unreach"]

# per cell: list over seeds of per-bin dict of metric-lists (node-level)
pernode_files = sorted(glob.glob(os.path.join(PN, "probe_*.csv")))

# accumulators
hopbin_acc   = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))  # cell -> bin -> metric -> [node values pooled over all seeds]
hopbin_count = defaultdict(lambda: defaultdict(list))                        # cell -> bin -> [node-count per seed]
# concentration: per seed, fraction of total drops in hop<=1 vs fraction of nodes in hop<=1
conc_acc     = defaultdict(list)   # cell -> [ (frac_nodes_le1, frac_phyrx_le1, frac_macq_le1, frac_fwd_le1) per seed ]
# correlations pooled at node level per cell
corr_acc     = defaultdict(lambda: defaultdict(list))  # cell -> key -> [(x,y)]

PN_NUM = ["airtime_busy_frac","airtime_tx_s","airtime_rx_s","airtime_ccabusy_s",
          "phy_rx_drops","mac_queue_drops","ip_drop_no_route","ip_drop_ttl",
          "ip_drop_route_error","ip_drop_queue","ip_drop_other",
          "app_pkts_originated","l3_unicast_forwarded","dist_to_gw_m"]

def parse_name(path):
    b = os.path.basename(path)[len("probe_"):-len(".csv")]
    # <proto>_<n>_<traffic>_seed<s>
    proto, n, traffic, seedtok = b.split("_")
    return proto, int(n), traffic, int(seedtok[len("seed"):])

for path in pernode_files:
    proto, n, traffic, seed = parse_name(path)
    cell = (proto, n, traffic)
    nodes = []
    with open(path) as fh:
        for r in csv.DictReader(fh):
            rec = {kk: fnum(r[kk]) for kk in PN_NUM}
            rec["node_id"]    = int(r["node_id"])
            rec["is_gateway"] = int(r["is_gateway"])
            rec["hop"]        = int(float(r["hop_to_gw"]))
            rec["bin"]        = hopbin(rec["hop"])
            nodes.append(rec)

    # per-bin accumulation (node-level pooled)
    binc = defaultdict(int)
    for rec in nodes:
        b = rec["bin"]
        binc[b] += 1
        for kk in PN_NUM:
            hopbin_acc[cell][b][kk].append(rec[kk])
    for b in BIN_ORDER:
        hopbin_count[cell][b].append(binc.get(b, 0))

    # concentration (exclude gateway itself from "nodes" denominator? keep sensors+relays; gateway is sink)
    sensors = [rec for rec in nodes if rec["is_gateway"] == 0]
    tot_nodes = len(sensors)
    le1 = [rec for rec in sensors if 0 <= rec["hop"] <= 1]
    def frac(sel, kk):
        tot = sum(rec[kk] for rec in sensors)
        return (sum(rec[kk] for rec in le1) / tot) if tot > 0 else math.nan
    conc_acc[cell].append((
        (len(le1) / tot_nodes) if tot_nodes else math.nan,
        frac(le1, "phy_rx_drops"),
        frac(le1, "mac_queue_drops"),
        frac(le1, "l3_unicast_forwarded"),
        frac(le1, "airtime_ccabusy_s"),
    ))

    # correlations at node level (sensors only)
    for rec in sensors:
        corr_acc[cell]["phyrx_vs_dist"].append((rec["dist_to_gw_m"], rec["phy_rx_drops"]))
        corr_acc[cell]["phyrx_vs_hop"].append((rec["hop"], rec["phy_rx_drops"]))
        corr_acc[cell]["macq_vs_hop"].append((rec["hop"], rec["mac_queue_drops"]))
        corr_acc[cell]["airtime_vs_hop"].append((rec["hop"], rec["airtime_busy_frac"]))
        corr_acc[cell]["fwd_vs_hop"].append((rec["hop"], rec["l3_unicast_forwarded"]))
        corr_acc[cell]["airtime_vs_dist"].append((rec["dist_to_gw_m"], rec["airtime_busy_frac"]))

def pearson(pairs):
    pairs = [(x, y) for x, y in pairs if not (math.isnan(x) or math.isnan(y))]
    if len(pairs) < 3:
        return math.nan, len(pairs)
    xs = [p[0] for p in pairs]; ys = [p[1] for p in pairs]
    mx = st.fmean(xs); my = st.fmean(ys)
    sx = math.sqrt(sum((x-mx)**2 for x in xs))
    sy = math.sqrt(sum((y-my)**2 for y in ys))
    if sx == 0 or sy == 0:
        return math.nan, len(pairs)
    cov = sum((x-mx)*(y-my) for x, y in pairs)
    return cov/(sx*sy), len(pairs)

# ----------------------------------------------------------------------------
# 3. Build hop-bin summary table per cell
# ----------------------------------------------------------------------------
hopbin_summary = {}   # cell -> bin -> dict
for cell, bins in hopbin_acc.items():
    hopbin_summary[cell] = {}
    for b in BIN_ORDER:
        if b not in bins:
            continue
        node_cnt = summ([float(x) for x in hopbin_count[cell][b]])
        rec = {"n_nodes_per_seed_mean": node_cnt["mean"]}
        for kk in ["airtime_busy_frac","airtime_ccabusy_s","phy_rx_drops",
                   "mac_queue_drops","l3_unicast_forwarded","app_pkts_originated",
                   "ip_drop_no_route","ip_drop_route_error","dist_to_gw_m"]:
            s = summ(bins[b][kk])
            rec[kk + "_node_mean"] = s["mean"]
            rec[kk + "_node_sd"]   = s["sd"]
            # per-seed total contributed by this bin = node_mean * nodes_in_bin, summed then / seeds
            rec[kk + "_bin_total_mean"] = (s["mean"] * node_cnt["mean"]) if not math.isnan(s["mean"]) else math.nan
        hopbin_summary[cell][b] = rec

# ----------------------------------------------------------------------------
# 4. Concentration + correlation summaries
# ----------------------------------------------------------------------------
conc_summary = {}
for cell, lst in conc_acc.items():
    fn  = summ([t[0] for t in lst])
    fp  = summ([t[1] for t in lst])
    fm  = summ([t[2] for t in lst])
    ff  = summ([t[3] for t in lst])
    fc  = summ([t[4] for t in lst])
    conc_summary[cell] = {
        "frac_nodes_hop_le1_mean": fn["mean"], "frac_nodes_hop_le1_sd": fn["sd"],
        "frac_phyrx_hop_le1_mean": fp["mean"], "frac_phyrx_hop_le1_sd": fp["sd"],
        "frac_macq_hop_le1_mean":  fm["mean"], "frac_macq_hop_le1_sd":  fm["sd"],
        "frac_fwd_hop_le1_mean":   ff["mean"], "frac_fwd_hop_le1_sd":   ff["sd"],
        "frac_ccabusy_hop_le1_mean": fc["mean"], "frac_ccabusy_hop_le1_sd": fc["sd"],
        # concentration ratio: >1 means over-represented at hop<=1
        "phyrx_conc_ratio": (fp["mean"]/fn["mean"]) if fn["mean"] else math.nan,
        "macq_conc_ratio":  (fm["mean"]/fn["mean"]) if fn["mean"] else math.nan,
        "fwd_conc_ratio":   (ff["mean"]/fn["mean"]) if fn["mean"] else math.nan,
    }

corr_summary = {}
for cell, d in corr_acc.items():
    corr_summary[cell] = {}
    for kk, pairs in d.items():
        r, nn = pearson(pairs)
        corr_summary[cell][kk] = {"r": r, "n": nn}

# ----------------------------------------------------------------------------
# 5. Emit CSVs
# ----------------------------------------------------------------------------
def w_csv(path, header, rows):
    with open(path, "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(header)
        wr.writerows(rows)

# 5a aggregate by cell
hdr = ["protocol","nodes","trafficLevel","n_seeds","pdr_mean","pdr_sd",
       "throughputKbps_mean","avgDelaySec_mean","avgJitterSec_mean",
       "unreachableSensors_mean","routingOverheadPkts_mean",
       "total_phy_rx_drops_mean","total_mac_queue_drops_mean",
       "total_ip_drop_no_route_mean","total_ip_drop_ttl_mean",
       "total_ip_drop_route_error_mean","total_ip_drop_other_mean",
       "gw_airtime_busy_frac_mean","ring1_airtime_busy_frac_mean_mean",
       "rest_airtime_busy_frac_mean_mean","ring1_node_count_mean",
       "txPkts_mean","rxPkts_mean"]
rows = []
for k in sorted(agg_cell_summary):
    d = agg_cell_summary[k]
    rows.append([d["protocol"], d["nodes"], d["trafficLevel"], d["n_seeds"],
                 f'{d["pdr_mean"]:.3f}', f'{d["pdr_sd"]:.3f}',
                 f'{d["throughputKbps_mean"]:.3f}', f'{d["avgDelaySec_mean"]:.5f}',
                 f'{d["avgJitterSec_mean"]:.5f}', f'{d["unreachableSensors_mean"]:.3f}',
                 f'{d["routingOverheadPkts_mean"]:.1f}',
                 f'{d["total_phy_rx_drops_mean"]:.0f}', f'{d["total_mac_queue_drops_mean"]:.1f}',
                 f'{d["total_ip_drop_no_route_mean"]:.1f}', f'{d["total_ip_drop_ttl_mean"]:.1f}',
                 f'{d["total_ip_drop_route_error_mean"]:.1f}', f'{d["total_ip_drop_other_mean"]:.1f}',
                 f'{d["gw_airtime_busy_frac_mean"]:.4f}',
                 f'{d["ring1_airtime_busy_frac_mean_mean"]:.4f}',
                 f'{d["rest_airtime_busy_frac_mean_mean"]:.4f}',
                 f'{d["ring1_node_count_mean"]:.1f}',
                 f'{d["txPkts_mean"]:.0f}', f'{d["rxPkts_mean"]:.0f}'])
w_csv(os.path.join(OUT, "T_probe_aggregate_by_cell.csv"), hdr, rows)

# 5b hop-bin by cell
hdr = ["protocol","nodes","trafficLevel","hop_bin","n_nodes_per_seed_mean",
       "airtime_busy_frac_node_mean","airtime_ccabusy_s_node_mean",
       "phy_rx_drops_node_mean","phy_rx_drops_bin_total_mean",
       "mac_queue_drops_node_mean","mac_queue_drops_bin_total_mean",
       "l3_unicast_forwarded_node_mean","app_pkts_originated_node_mean",
       "ip_drop_no_route_node_mean","ip_drop_route_error_node_mean",
       "dist_to_gw_m_node_mean"]
rows = []
for k in sorted(hopbin_summary):
    for b in BIN_ORDER:
        if b not in hopbin_summary[k]:
            continue
        r = hopbin_summary[k][b]
        rows.append([k[0], k[1], k[2], b,
                     f'{r["n_nodes_per_seed_mean"]:.2f}',
                     f'{r["airtime_busy_frac_node_mean"]:.4f}',
                     f'{r["airtime_ccabusy_s_node_mean"]:.3f}',
                     f'{r["phy_rx_drops_node_mean"]:.0f}',
                     f'{r["phy_rx_drops_bin_total_mean"]:.0f}',
                     f'{r["mac_queue_drops_node_mean"]:.2f}',
                     f'{r["mac_queue_drops_bin_total_mean"]:.1f}',
                     f'{r["l3_unicast_forwarded_node_mean"]:.1f}',
                     f'{r["app_pkts_originated_node_mean"]:.1f}',
                     f'{r["ip_drop_no_route_node_mean"]:.2f}',
                     f'{r["ip_drop_route_error_node_mean"]:.2f}',
                     f'{r["dist_to_gw_m_node_mean"]:.1f}'])
w_csv(os.path.join(OUT, "T_probe_hopbin_by_cell.csv"), hdr, rows)

# 5c concentration
hdr = ["protocol","nodes","trafficLevel","frac_nodes_hop_le1","frac_phyrx_hop_le1",
       "frac_macq_hop_le1","frac_fwd_hop_le1","frac_ccabusy_hop_le1",
       "phyrx_conc_ratio","macq_conc_ratio","fwd_conc_ratio"]
rows = []
for k in sorted(conc_summary):
    d = conc_summary[k]
    rows.append([k[0], k[1], k[2],
                 f'{d["frac_nodes_hop_le1_mean"]:.3f}',
                 f'{d["frac_phyrx_hop_le1_mean"]:.3f}',
                 f'{d["frac_macq_hop_le1_mean"]:.3f}',
                 f'{d["frac_fwd_hop_le1_mean"]:.3f}',
                 f'{d["frac_ccabusy_hop_le1_mean"]:.3f}',
                 f'{d["phyrx_conc_ratio"]:.3f}',
                 f'{d["macq_conc_ratio"]:.3f}',
                 f'{d["fwd_conc_ratio"]:.3f}'])
w_csv(os.path.join(OUT, "T_probe_concentration.csv"), hdr, rows)

# 5d correlations
hdr = ["protocol","nodes","trafficLevel","relation","pearson_r","n_nodes_pooled"]
rows = []
for k in sorted(corr_summary):
    for kk, v in corr_summary[k].items():
        rows.append([k[0], k[1], k[2], kk, f'{v["r"]:.3f}', v["n"]])
w_csv(os.path.join(OUT, "T_probe_correlations.csv"), hdr, rows)

# ----------------------------------------------------------------------------
# 6. JSON dump for the write-up
# ----------------------------------------------------------------------------
def keyify(d):
    return {f"{k[0]}_{k[1]}_{k[2]}": v for k, v in d.items()}

out = {
    "n_agg_rows": len(agg_rows),
    "n_pernode_files": len(pernode_files),
    "cells": sorted(f"{k[0]}_{k[1]}_{k[2]}" for k in agg_by_cell),
    "agg_cell_summary": keyify(agg_cell_summary),
    "hopbin_summary": keyify(hopbin_summary),
    "concentration": keyify(conc_summary),
    "correlations": keyify(corr_summary),
}
with open(os.path.join(OUT, "PROBE_ANALYSIS_DATA.json"), "w") as fh:
    json.dump(out, fh, indent=2, default=lambda o: None if (isinstance(o, float) and math.isnan(o)) else o)

print(f"agg rows={len(agg_rows)}  pernode files={len(pernode_files)}  cells={len(agg_by_cell)}")
print("wrote: T_probe_aggregate_by_cell.csv, T_probe_hopbin_by_cell.csv, "
      "T_probe_concentration.csv, T_probe_correlations.csv, PROBE_ANALYSIS_DATA.json")
