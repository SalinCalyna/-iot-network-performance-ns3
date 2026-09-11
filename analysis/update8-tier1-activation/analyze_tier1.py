#!/usr/bin/env python3
"""
UPDATE #8 TIER-1 V4 ACTIVATION SCREEN -- integrity audit + route-tree activation check
+ 8-metric comparison vs Static. READ-ONLY on all pre-existing datasets.

Inputs:
  analysis/update8-tier1-activation/data/v4_50_medium_static.csv   (66 new Tier-1 rows -- this screen)
  results/v3-ext/static_50_medium_static.csv  (seeds 20-30, Static baseline, LOCKED -- read only)
  results/v4-sensitivity/v4_50_medium_static.csv  (297 Stage-1 rows, LOCKED -- read only, context)
"""
import sys, math, json
from pathlib import Path
from math import comb
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path("/Users/pinpuk/ns-3-dev")
T1 = ROOT / "analysis/update8-tier1-activation/data/v4_50_medium_static.csv"
STAT = ROOT / "results/v3-ext/static_50_medium_static.csv"
SENS = ROOT / "results/v4-sensitivity/v4_50_medium_static.csv"
OUT = ROOT / "analysis/update8-tier1-activation"
PLOTS = OUT / "plots"; PLOTS.mkdir(parents=True, exist_ok=True)

SEEDS = list(range(20, 31))
X0L = [0.02, 0.05, 0.50]
X0R = [0.50, 0.80]
METRICS = {
    "PDR": ("PDR", "%", "higher"), "Throughput": ("ThroughputKbps", "kbps", "higher"),
    "Delay": ("AverageDelaySec", "s", "lower"), "Jitter": ("AverageJitterSec", "s", "lower"),
    "PacketLoss": ("PacketLoss", "pkts", "lower"), "HopCount": ("AverageHopCount", "hops", "context"),
    "AvgLinkUtil": ("AverageLinkUtilization", "ratio", "context"),
    "MaxLinkUtil": ("MaximumLinkUtilization", "ratio", "context"),
}
MCOLS = [c for c, _, _ in METRICS.values()]
PARAMS = ["SigmoidKRisk", "SigmoidX0Risk", "SigmoidKLoad", "SigmoidX0Load", "WeightRisk", "WeightLoad"]

t1 = pd.read_csv(T1)
st = pd.read_csv(STAT); st = st[st.Seed.between(20, 30)].copy()

rep = {}
def R(k, v): rep[k] = v; print(f"{k}: {v}")

# ---------------------------------------------------------------- 1. INTEGRITY AUDIT
print("=" * 78); print("INTEGRITY AUDIT"); print("=" * 78)
R("expected_runs", 6 * 11)
R("actual_rows", int(len(t1)))
R("log_files", len(list((OUT / "data" / "logs").glob("*.log"))))
R("output_csv_files", [p.name for p in (OUT / "data").glob("*.csv")])
R("routing_protocol", sorted(t1.RoutingProtocol.str.lower().unique()))
R("node_counts", sorted(int(x) for x in t1.NumberOfNodes.unique()))
R("traffic", sorted(t1.TrafficLevel.str.lower().unique()))
R("mobility", sorted(t1.MobilityMode.str.lower().unique()))
R("durations", sorted(float(x) for x in t1.Duration.unique()))
R("seeds", sorted(int(x) for x in t1.Seed.unique()))
R("k_R_values", sorted(t1.SigmoidKRisk.unique()))
R("k_L_values", sorted(t1.SigmoidKLoad.unique()))
R("w_R_values", sorted(t1.WeightRisk.unique()))
R("x0_R_values", sorted(t1.SigmoidX0Risk.unique()))
R("x0_L_values", sorted(t1.SigmoidX0Load.unique()))
R("hopcount_method", sorted(t1.HopCountMethod.unique()))
R("pathchanges_unique", sorted(int(x) for x in t1.PathChanges.unique()))
cfg = t1.groupby(PARAMS).size()
R("n_param_configs", int(len(cfg)))
R("rows_per_config_min_max", (int(cfg.min()), int(cfg.max())))
R("duplicate (config,seed) rows", int(t1.duplicated(subset=PARAMS + ["Seed"]).sum()))
naninf = int((~np.isfinite(t1[MCOLS].to_numpy(float))).sum())
R("NaN_or_Inf_in_metrics", naninf)
negs = {c: int((t1[c] < 0).sum()) for c in MCOLS if (t1[c] < 0).any()}
R("impossible_negatives", negs or "none")
# param bound checks
bad = []
for _, r in t1.iterrows():
    if not (r.SigmoidKRisk > 0 and r.SigmoidKLoad > 0): bad.append("k>0")
    if not (0 < r.SigmoidX0Risk < 1 and 0 < r.SigmoidX0Load < 1): bad.append("0<x0<1")
    if abs(r.WeightRisk + r.WeightLoad - 1) > 1e-9: bad.append("wR+wL=1")
R("param_bound_violations", len(bad))
# the 6 expected configs present?
got = {(round(a,3), round(b,3)) for a, b in zip(t1.SigmoidX0Load, t1.SigmoidX0Risk)}
want = {(round(a,3), round(b,3)) for a in X0L for b in X0R}
R("expected_6_configs_present", got == want)
R("missing_configs", sorted(want - got))
R("unexpected_configs", sorted(got - want))
# LOCKED datasets untouched
R("V3_official_rows", int(sum(1 for _ in open('/dev/null')) or 0))  # placeholder; real check in shell
INTEGRITY_OK = (len(t1) == 66 and len(cfg) == 6 and (cfg == 11).all() and naninf == 0
                and not negs and not bad and got == want
                and sorted(t1.Seed.unique()) == SEEDS
                and rep["hopcount_method"] == ["exact"])
R("INTEGRITY_OK", bool(INTEGRITY_OK))
if not INTEGRITY_OK:
    (OUT / "integrity_report.json").write_text(json.dumps(rep, indent=2, default=str))
    print("INTEGRITY FAILED -- stopping."); sys.exit(1)

# ---------------------------------------------------------------- 2. ROUTE-TREE ACTIVATION CHECK
print("\n" + "=" * 78); print("ROUTE-TREE ACTIVATION CHECK (pre-registered: >=30% of 11 seeds change tree)"); print("=" * 78)
st_hop = st.set_index("Seed")["AverageHopCount"].to_dict()
st_m = {m: st.set_index("Seed")[METRICS[m][0]].to_dict() for m in METRICS}

def sign_p(nbetter, n):
    if n == 0: return float("nan")
    k = min(nbetter, n - nbetter)
    return min(1.0, 2.0 * sum(comb(n, i) for i in range(0, k + 1)) / 2 ** n)

rows = []
for (x0r, x0l), g in t1.groupby(["SigmoidX0Risk", "SigmoidX0Load"]):
    g = g.set_index("Seed")
    hop_v4 = np.array([g.loc[s, "AverageHopCount"] for s in SEEDS], float)
    hop_st = np.array([st_hop[s] for s in SEEDS], float)
    hopdiff = hop_v4 - hop_st
    n_changed = int(np.sum(np.abs(hopdiff) > 1e-9))
    rec = dict(x0_R=x0r, x0_L=x0l, k_R=10, k_L=10, w_R=0.5, n_seeds=11,
               seeds_tree_differs_from_static=n_changed,
               route_change_pct=100.0 * n_changed / 11,
               ACTIVATED=bool(n_changed / 11 >= 0.30),
               mean_hop_v4=float(hop_v4.mean()), mean_hop_static=float(hop_st.mean()),
               mean_hop_diff=float(hopdiff.mean()), max_abs_hop_diff=float(np.abs(hopdiff).max()),
               median_abs_hop_diff=float(np.median(np.abs(hopdiff))))
    for m, (col, unit, direction) in METRICS.items():
        v4v = np.array([g.loc[s, col] for s in SEEDS], float)
        bv = np.array([st_m[m][s] for s in SEEDS], float)
        d = v4v - bv
        rec[f"{m}_v4_mean"] = float(v4v.mean()); rec[f"{m}_v4_sd"] = float(v4v.std(ddof=1))
        rec[f"{m}_v4_median"] = float(np.median(v4v)); rec[f"{m}_v4_min"] = float(v4v.min()); rec[f"{m}_v4_max"] = float(v4v.max())
        rec[f"{m}_static_mean"] = float(bv.mean())
        rec[f"{m}_mean_diff"] = float(d.mean()); rec[f"{m}_median_diff"] = float(np.median(d))
        rec[f"{m}_pct_vs_static"] = float("nan") if bv.mean() == 0 else float(d.mean() / abs(bv.mean()) * 100)
        nb = int(np.sum((v4v > bv) if direction == "higher" else (v4v < bv))) if direction != "context" else int(np.sum(v4v > bv))
        rec[f"{m}_seeds_v4_'better'"] = nb
        rec[f"{m}_sign_test_p"] = sign_p(nb, 11) if direction != "context" else float("nan")
        rec[f"{m}_cohens_d"] = float(d.mean() / d.std(ddof=1)) if d.std(ddof=1) else float("nan")
    rows.append(rec)
T = pd.DataFrame(rows).sort_values(["x0_R", "x0_L"]).reset_index(drop=True)
T.to_csv(OUT / "T_tier1_activation_and_perf.csv", index=False)

print(T[["x0_R", "x0_L", "seeds_tree_differs_from_static", "route_change_pct", "ACTIVATED",
         "mean_hop_v4", "mean_hop_static", "mean_hop_diff", "max_abs_hop_diff"]].round(4).to_string(index=False))
print("\n-- 8-metric summary vs Static (mean; % vs Static; sign-test p; Cohen's d) --")
for _, r in T.iterrows():
    print(f"\n  config x0_R={r.x0_R} x0_L={r.x0_L}  (route change {r.route_change_pct:.1f}%, ACTIVATED={r.ACTIVATED})")
    for m in METRICS:
        d = METRICS[m][2]
        print(f"    {m:12s} V4={r[f'{m}_v4_mean']:10.4f}  Static={r[f'{m}_static_mean']:10.4f}  "
              f"pct={r[f'{m}_pct_vs_static']:+7.2f}%  seeds_better={r[f'{m}_seeds_v4_' + chr(39) + 'better' + chr(39)]}/11  "
              f"p={r[f'{m}_sign_test_p']:.3f}  d={r[f'{m}_cohens_d']:+.2f}  [{d}]")

any_activated = bool(T["ACTIVATED"].any())
R2 = {}
R2["ANY_CONFIG_ACTIVATED (>=30% seeds)"] = any_activated
R2["activated_configs"] = T[T.ACTIVATED][["x0_R", "x0_L", "route_change_pct"]].to_dict("records")
R2["max_route_change_pct"] = float(T["route_change_pct"].max())
R2["config_with_max_activity"] = T.sort_values("route_change_pct", ascending=False).iloc[0][["x0_R", "x0_L", "route_change_pct", "seeds_tree_differs_from_static"]].to_dict()
print("\n" + json.dumps(R2, indent=2, default=str))

# ---------------------------------------------------------------- 3. CONTEXT vs Stage-1 (k<=5, x0=0.5) -- read only
sens = pd.read_csv(SENS)
sens_x005 = sens[(sens.SigmoidX0Risk == 0.5) & (sens.SigmoidX0Load == 0.5)]
R("stage1_configs_x0=0.5_all_k", int(sens_x005.groupby(PARAMS).ngroups))
# stage-1 route activity (already known from Update #7): recompute quickly
s1_changed = 0
for key, g in sens_x005.groupby(PARAMS):
    g = g.set_index("Seed")
    ch = sum(1 for s in SEEDS if abs(g.loc[s, "AverageHopCount"] - st_hop[s]) > 1e-9)
    s1_changed += ch
R("stage1_total_route_changing_runs (x0=0.5, k in {0.5,2,5}, all w)", int(s1_changed))
R("tier1_total_route_changing_runs (x0 recentred, k=10)", int(T["seeds_tree_differs_from_static"].sum()))

# ---------------------------------------------------------------- figures
COL = {"static": "#2ca02c", "v4": "#9467bd"}
# route-change % by config
fig, ax = plt.subplots(figsize=(8, 4.5))
lab = [f"x0_R={r.x0_R}\nx0_L={r.x0_L}" for _, r in T.iterrows()]
bars = ax.bar(range(len(T)), T["route_change_pct"], color=["#d62728" if a else "#7f7f7f" for a in T["ACTIVATED"]])
ax.axhline(30, c="k", ls="--", label="pre-registered activation threshold (30%)")
ax.set_xticks(range(len(T))); ax.set_xticklabels(lab, fontsize=8)
ax.set_ylabel("% of 11 seeds where V4 tree != Static tree (exact hop)")
ax.set_title("Tier-1: routing activity by re-centred config (k_R=k_L=10, w_R=0.5)")
ax.legend(); fig.tight_layout(); fig.savefig(PLOTS / "fig1_route_change_by_config.png", dpi=130); plt.close(fig)

# PDR & Delay by config vs Static
for label in ["PDR", "Throughput", "Delay", "PacketLoss"]:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(range(len(T)), T[f"{label}_v4_mean"], yerr=T[f"{label}_v4_sd"], capsize=3, color="slateblue")
    ax.axhline(T[f"{label}_static_mean"].iloc[0], c="green", ls="--", lw=2,
               label=f"Static mean = {T[f'{label}_static_mean'].iloc[0]:.3g}")
    ax.set_xticks(range(len(T))); ax.set_xticklabels(lab, fontsize=8)
    ax.set_ylabel(f"{label} ({METRICS[label][1]})")
    ax.set_title(f"Tier-1: {label} by re-centred config (mean +/- SD, 11 seeds) vs Static")
    ax.legend(); fig.tight_layout(); fig.savefig(PLOTS / f"fig_{label}_by_config.png", dpi=130); plt.close(fig)

rep.update(R2)
(OUT / "integrity_and_digest.json").write_text(json.dumps(rep, indent=2, default=str))
print("\nArtifacts:")
for p in sorted(OUT.rglob("*")):
    if p.is_file() and "data/logs" not in str(p):
        print("  ", p.relative_to(ROOT))
print("\nDONE")
