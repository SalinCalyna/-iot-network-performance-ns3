#!/usr/bin/env python3
"""
Retry-exhaustion measurement -- analysis. READ-ONLY.
Consumes:
  data-retry/probe_aggregate.csv
  data-retry/pernode/probe_<proto>_<n>_<traffic>_seed<s>.csv
Writes only NEW artifacts under analysis/bottleneck-characterisation/:
  T_retry_aggregate_by_cell.csv
  T_retry_hopbin_by_cell.csv
  T_retry_concentration.csv
  T_retry_correlations.csv
  T_retry_attribution.csv
No existing file (incl. the §10 dataset / T_probe_* tables) is modified.
"""
import csv, glob, json, math, os, statistics as st
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
AGG  = os.path.join(BASE, "data-retry", "probe_aggregate.csv")
PN   = os.path.join(BASE, "data-retry", "pernode")
OUT  = BASE

def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return math.nan

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
           "total_max_retry_drops","total_ip_drop_no_route","total_ip_drop_ttl",
           "total_ip_drop_route_error","total_ip_drop_queue","total_ip_drop_other",
           "gw_airtime_busy_frac","ring1_airtime_busy_frac_mean","rest_airtime_busy_frac_mean",
           "ring1_node_count","txPkts","rxPkts"]

def summ(vals):
    vals = [v for v in vals if not math.isnan(v)]
    if not vals:
        return dict(n=0, mean=math.nan, sd=math.nan)
    return dict(n=len(vals), mean=st.fmean(vals), sd=(st.pstdev(vals) if len(vals) > 1 else 0.0))

agg_cell_summary = {}
for k, rows in sorted(agg_by_cell.items()):
    d = {"protocol": k[0], "nodes": k[1], "trafficLevel": k[2], "n_seeds": len(rows)}
    for col in AGG_NUM:
        s = summ([fnum(r[col]) for r in rows])
        d[col + "_mean"] = s["mean"]
        d[col + "_sd"]   = s["sd"]
    # packet loss + attribution (per-run then averaged, not averaged-then-subtracted)
    lost = [fnum(r["txPkts"]) - fnum(r["rxPkts"]) for r in rows]
    macq = [fnum(r["total_mac_queue_drops"]) for r in rows]
    retry = [fnum(r["total_max_retry_drops"]) for r in rows]
    noroute = [fnum(r["total_ip_drop_no_route"]) for r in rows]
    ttl = [fnum(r["total_ip_drop_ttl"]) for r in rows]
    rte = [fnum(r["total_ip_drop_route_error"]) for r in rows]
    other = [fnum(r["total_ip_drop_other"]) for r in rows]
    retry_frac = [ (retry[i]/lost[i]) if lost[i] else math.nan for i in range(len(rows)) ]
    macq_frac  = [ (macq[i]/lost[i]) if lost[i] else math.nan for i in range(len(rows)) ]
    acct = [ (macq[i]+retry[i]+noroute[i]+ttl[i]+rte[i]+other[i])/lost[i] if lost[i] else math.nan
             for i in range(len(rows)) ]
    d["lost_mean"] = st.fmean(lost)
    d["retry_frac_of_loss_mean"] = st.fmean([x for x in retry_frac if not math.isnan(x)])
    d["macq_frac_of_loss_mean"]  = st.fmean([x for x in macq_frac if not math.isnan(x)])
    d["accounted_frac_of_loss_mean"] = st.fmean([x for x in acct if not math.isnan(x)])
    agg_cell_summary[k] = d

def hopbin(h):
    if h < 0:  return "unreach"
    if h == 0: return "gw"
    if h == 1: return "hop1"
    if h == 2: return "hop2"
    if h == 3: return "hop3"
    return "hop4+"
BIN_ORDER = ["gw","hop1","hop2","hop3","hop4+","unreach"]

pernode_files = sorted(glob.glob(os.path.join(PN, "probe_*.csv")))
hopbin_acc   = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
hopbin_count = defaultdict(lambda: defaultdict(list))
conc_acc     = defaultdict(list)
corr_acc     = defaultdict(lambda: defaultdict(list))

PN_NUM = ["airtime_busy_frac","airtime_ccabusy_s","phy_rx_drops","mac_queue_drops",
          "max_retry_drops","ip_drop_no_route","ip_drop_route_error",
          "app_pkts_originated","l3_unicast_forwarded","dist_to_gw_m"]

def parse_name(path):
    b = os.path.basename(path)[len("probe_"):-len(".csv")]
    proto, n, traffic, seedtok = b.split("_")
    return proto, int(n), traffic, int(seedtok[len("seed"):])

for path in pernode_files:
    proto, n, traffic, seed = parse_name(path)
    cell = (proto, n, traffic)
    nodes = []
    with open(path) as fh:
        for r in csv.DictReader(fh):
            rec = {kk: fnum(r[kk]) for kk in PN_NUM}
            rec["is_gateway"] = int(r["is_gateway"])
            rec["hop"] = int(float(r["hop_to_gw"]))
            rec["bin"] = hopbin(rec["hop"])
            nodes.append(rec)

    binc = defaultdict(int)
    for rec in nodes:
        b = rec["bin"]
        binc[b] += 1
        for kk in PN_NUM:
            hopbin_acc[cell][b][kk].append(rec[kk])
    for b in BIN_ORDER:
        hopbin_count[cell][b].append(binc.get(b, 0))

    sensors = [rec for rec in nodes if rec["is_gateway"] == 0]
    tot_nodes = len(sensors)
    le1 = [rec for rec in sensors if 0 <= rec["hop"] <= 1]
    def frac(sel, kk, sensors=sensors):
        tot = sum(rec[kk] for rec in sensors)
        return (sum(rec[kk] for rec in sel) / tot) if tot > 0 else math.nan
    conc_acc[cell].append((
        (len(le1) / tot_nodes) if tot_nodes else math.nan,
        frac(le1, "max_retry_drops"),
        frac(le1, "phy_rx_drops"),
        frac(le1, "mac_queue_drops"),
    ))

    for rec in sensors:
        corr_acc[cell]["retry_vs_hop"].append((rec["hop"], rec["max_retry_drops"]))
        corr_acc[cell]["retry_vs_dist"].append((rec["dist_to_gw_m"], rec["max_retry_drops"]))
        corr_acc[cell]["retry_vs_airtime"].append((rec["airtime_busy_frac"], rec["max_retry_drops"]))
        corr_acc[cell]["retry_vs_macq"].append((rec["mac_queue_drops"], rec["max_retry_drops"]))
        corr_acc[cell]["retry_vs_phyrx"].append((rec["phy_rx_drops"], rec["max_retry_drops"]))

def pearson(pairs):
    pairs = [(x, y) for x, y in pairs if not (math.isnan(x) or math.isnan(y))]
    if len(pairs) < 3:
        return math.nan, len(pairs)
    xs = [p[0] for p in pairs]; ys = [p[1] for p in pairs]
    mx = st.fmean(xs); my = st.fmean(ys)
    sx = math.sqrt(sum((x-mx)**2 for x in xs)); sy = math.sqrt(sum((y-my)**2 for y in ys))
    if sx == 0 or sy == 0:
        return math.nan, len(pairs)
    cov = sum((x-mx)*(y-my) for x, y in pairs)
    return cov/(sx*sy), len(pairs)

hopbin_summary = {}
for cell, bins in hopbin_acc.items():
    hopbin_summary[cell] = {}
    for b in BIN_ORDER:
        if b not in bins: continue
        node_cnt = summ([float(x) for x in hopbin_count[cell][b]])
        rec = {"n_nodes_per_seed_mean": node_cnt["mean"]}
        for kk in ["airtime_busy_frac","max_retry_drops","phy_rx_drops","mac_queue_drops",
                   "l3_unicast_forwarded","dist_to_gw_m"]:
            s = summ(bins[b][kk])
            rec[kk + "_node_mean"] = s["mean"]
            rec[kk + "_bin_total_mean"] = (s["mean"] * node_cnt["mean"]) if not math.isnan(s["mean"]) else math.nan
        hopbin_summary[cell][b] = rec

conc_summary = {}
for cell, lst in conc_acc.items():
    fn = summ([t[0] for t in lst]); fr = summ([t[1] for t in lst])
    fp = summ([t[2] for t in lst]); fm = summ([t[3] for t in lst])
    conc_summary[cell] = {
        "frac_nodes_hop_le1_mean": fn["mean"],
        "frac_retry_hop_le1_mean": fr["mean"],
        "frac_phyrx_hop_le1_mean": fp["mean"],
        "frac_macq_hop_le1_mean":  fm["mean"],
        "retry_conc_ratio": (fr["mean"]/fn["mean"]) if fn["mean"] else math.nan,
        "phyrx_conc_ratio": (fp["mean"]/fn["mean"]) if fn["mean"] else math.nan,
        "macq_conc_ratio":  (fm["mean"]/fn["mean"]) if fn["mean"] else math.nan,
    }

corr_summary = {}
for cell, d in corr_acc.items():
    corr_summary[cell] = {}
    for kk, pairs in d.items():
        r, nn = pearson(pairs)
        corr_summary[cell][kk] = {"r": r, "n": nn}

def w_csv(path, header, rows):
    with open(path, "w", newline="") as fh:
        wr = csv.writer(fh); wr.writerow(header); wr.writerows(rows)

hdr = ["protocol","nodes","trafficLevel","n_seeds","pdr_mean","pdr_sd","throughputKbps_mean",
       "avgDelaySec_mean","lost_mean","total_max_retry_drops_mean","total_mac_queue_drops_mean",
       "total_phy_rx_drops_mean","total_ip_drop_no_route_mean","gw_airtime_busy_frac_mean",
       "ring1_airtime_busy_frac_mean_mean","retry_frac_of_loss_mean","macq_frac_of_loss_mean",
       "accounted_frac_of_loss_mean"]
rows = []
for k in sorted(agg_cell_summary):
    d = agg_cell_summary[k]
    rows.append([d["protocol"], d["nodes"], d["trafficLevel"], d["n_seeds"],
                 f'{d["pdr_mean"]:.3f}', f'{d["pdr_sd"]:.3f}', f'{d["throughputKbps_mean"]:.3f}',
                 f'{d["avgDelaySec_mean"]:.5f}', f'{d["lost_mean"]:.1f}',
                 f'{d["total_max_retry_drops_mean"]:.1f}', f'{d["total_mac_queue_drops_mean"]:.1f}',
                 f'{d["total_phy_rx_drops_mean"]:.0f}', f'{d["total_ip_drop_no_route_mean"]:.1f}',
                 f'{d["gw_airtime_busy_frac_mean"]:.4f}', f'{d["ring1_airtime_busy_frac_mean_mean"]:.4f}',
                 f'{d["retry_frac_of_loss_mean"]*100:.2f}', f'{d["macq_frac_of_loss_mean"]*100:.2f}',
                 f'{d["accounted_frac_of_loss_mean"]*100:.2f}'])
w_csv(os.path.join(OUT, "T_retry_aggregate_by_cell.csv"), hdr, rows)

hdr = ["protocol","nodes","trafficLevel","hop_bin","n_nodes_per_seed_mean",
       "airtime_busy_frac_node_mean","max_retry_drops_node_mean","max_retry_drops_bin_total_mean",
       "phy_rx_drops_node_mean","mac_queue_drops_node_mean","l3_unicast_forwarded_node_mean",
       "dist_to_gw_m_node_mean"]
rows = []
for k in sorted(hopbin_summary):
    for b in BIN_ORDER:
        if b not in hopbin_summary[k]: continue
        r = hopbin_summary[k][b]
        rows.append([k[0], k[1], k[2], b, f'{r["n_nodes_per_seed_mean"]:.2f}',
                     f'{r["airtime_busy_frac_node_mean"]:.4f}',
                     f'{r["max_retry_drops_node_mean"]:.2f}', f'{r["max_retry_drops_bin_total_mean"]:.1f}',
                     f'{r["phy_rx_drops_node_mean"]:.0f}', f'{r["mac_queue_drops_node_mean"]:.2f}',
                     f'{r["l3_unicast_forwarded_node_mean"]:.1f}', f'{r["dist_to_gw_m_node_mean"]:.1f}'])
w_csv(os.path.join(OUT, "T_retry_hopbin_by_cell.csv"), hdr, rows)

hdr = ["protocol","nodes","trafficLevel","frac_nodes_hop_le1","frac_retry_hop_le1",
       "frac_phyrx_hop_le1","frac_macq_hop_le1","retry_conc_ratio","phyrx_conc_ratio","macq_conc_ratio"]
rows = []
for k in sorted(conc_summary):
    d = conc_summary[k]
    rows.append([k[0], k[1], k[2], f'{d["frac_nodes_hop_le1_mean"]:.3f}',
                 f'{d["frac_retry_hop_le1_mean"]:.3f}', f'{d["frac_phyrx_hop_le1_mean"]:.3f}',
                 f'{d["frac_macq_hop_le1_mean"]:.3f}', f'{d["retry_conc_ratio"]:.3f}',
                 f'{d["phyrx_conc_ratio"]:.3f}', f'{d["macq_conc_ratio"]:.3f}'])
w_csv(os.path.join(OUT, "T_retry_concentration.csv"), hdr, rows)

hdr = ["protocol","nodes","trafficLevel","relation","pearson_r","n_nodes_pooled"]
rows = []
for k in sorted(corr_summary):
    for kk, v in corr_summary[k].items():
        rows.append([k[0], k[1], k[2], kk, f'{v["r"]:.3f}', v["n"]])
w_csv(os.path.join(OUT, "T_retry_correlations.csv"), hdr, rows)

print(f"agg rows={len(agg_rows)}  pernode files={len(pernode_files)}  cells={len(agg_by_cell)}")
print("wrote: T_retry_aggregate_by_cell.csv, T_retry_hopbin_by_cell.csv, T_retry_concentration.csv, T_retry_correlations.csv")
