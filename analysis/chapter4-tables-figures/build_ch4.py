#!/usr/bin/env python3
"""Tables and figures for Chapter 4 (§4.2-4.5, 4.7), recomputed from raw run outputs and cross-checked against the
existing analyses. Read-only on all inputs.

    myenv/bin/python -I -B analysis/chapter4-tables-figures/build_ch4.py

Inputs
  ARP-fixed (flag on): results/wifi-std/{arp-a2-on, arp-a1-on, arp-b-on-os, arp-b1-on, arp-ratesweep-on,
                       arp-phase1-on}/b-on_*/{provenance.json, probe_aggregate.csv, wifistd_ext.csv}
  Diagnostic flag off: results/wifi-std/arp-phase1-off/b-off_*
  Frozen originals:    results/v3-ext/*_static.csv (Stage 1, seeds 20-30 only);
                       analysis/bottleneck-characterisation/data/probe_aggregate.csv (Stage 3);
                       analysis/bottleneck-characterisation/data-ratesweep/probe_aggregate.csv (Stage 5);
                       analysis/final-reproducibility-check/{run_manifest.csv, reproducibility_comparison.csv}
Cross-checks (stop on mismatch): results/wifi-std/v3ext-arp-analysis/cells.csv, pooled.csv;
  table4-arp-analysis/table4_on_vs_off.csv; arp-ratesweep-analysis/cells_vs_frozen.csv.
Conventions: PDR = 100 rx/tx (FlowMonitor); 95 % CI = t(0.975, n-1) SD / sqrt(n), reported only for n = 11;
  3-seed cells are descriptive (min-max shown). Pooled tables (3 traffic levels x 3 seeds) report means only,
  because the 9 runs share 3 topologies and are not independent.
Outputs (this directory): t41_diagnostic.csv, t42_pooled_pdr.csv, t43_cells.csv, t43a_ranking.csv,
  t44_bottleneck.csv, t45_ratesweep.csv, t47_reproducibility.csv, CROSSCHECK.txt, INPUTS.sha256,
  fig_4_pdr.png, fig_4_airtime.png, fig_4_ratesweep.png
"""
import csv
import hashlib
import json
import math
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
W = ROOT / "results/wifi-std"
ON_DIRS = ("arp-a2-on", "arp-a1-on", "arp-b-on-os", "arp-b1-on", "arp-ratesweep-on", "arp-phase1-on")
PROTOS, NS, TRAFFIC = ("aodv", "olsr", "static"), (10, 20, 30, 50, 75, 100), ("low", "medium", "high")
RATE = {"low": 4, "medium": 8, "high": 16}
S3, S11 = (20, 25, 30), tuple(range(20, 31))
T975 = {2: 4.303, 8: 2.306, 10: 2.228}
IPDROPS = ("total_ip_drop_no_route", "total_ip_drop_ttl", "total_ip_drop_route_error", "total_ip_drop_other")
INPUTS = set()
CHECK = []


def stop(msg):
    sys.exit(f"STOP: {msg}")


def rows_of(path):
    INPUTS.add(path)
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def one(path):
    r = rows_of(path)
    if len(r) != 1:
        stop(f"{path}: {len(r)} rows")
    return r[0]


def arg(argv, key):
    hit = [a.split("=", 1)[1] for a in argv if a.startswith(f"--{key}=")]
    return hit[0] if hit else None


def ci(vals):
    n = len(vals)
    if n < 2 or n - 1 not in T975:
        return float("nan")
    return T975[n - 1] * st.stdev(vals) / math.sqrt(n)


def run_record(rd, flag):
    INPUTS.add(rd / "provenance.json")
    prov = json.loads((rd / "provenance.json").read_text())
    a, e = one(rd / "probe_aggregate.csv"), one(rd / "wifistd_ext.csv")
    argv = prov["argv"]
    ok = (prov["exit_code"] == 0 and prov["stderr_bytes"] == 0 and prov["binary_sha256"].startswith("9f74bd9ce2c6")
          and arg(argv, "standard") == "80211b" and e["arp_prepopulate"] == flag
          and (arg(argv, "arpPrepopulate") == "1") == (flag == "1") and arg(argv, "mobility") is None)
    if not ok:
        stop(f"provenance/flag check failed: {rd.relative_to(ROOT)}")
    rate = float(arg(argv, "offeredRateKbps") or 8)
    key = (arg(argv, "protocol"), int(arg(argv, "nSensors")), int(rate), int(arg(argv, "seed")))
    tx, rx = int(a["txPkts"]), int(a["rxPkts"])
    rec = dict(tx=tx, rx=rx, pdr=100 * rx / tx, gw=float(a["gw_airtime_busy_frac"]),
               ring1=float(a["ring1_airtime_busy_frac_mean"]), mq=int(a["total_mac_queue_drops"]),
               rt=int(a["total_max_retry_drops"]), ip=sum(int(a[c]) for c in IPDROPS),
               arp=int(e["total_arp_l3_drops"]) + int(e["total_arp_cache_drops"]), dir=rd)
    if abs(rec["pdr"] - float(a["pdr"])) > 1e-3:
        stop(f"PDR recompute {rd}")
    return key, rec


def load_on():
    on = {}
    for d in ON_DIRS:
        for rd in sorted((W / d).glob("b-on_*")):
            k, r = run_record(rd, "1")
            if r["arp"] != 0:
                stop(f"ARP drops in flag-on run {rd}")
            if k in on:
                o = on[k]
                if (o["tx"], o["rx"], o["mq"], o["rt"], o["gw"]) != (r["tx"], r["rx"], r["mq"], r["rt"], r["gw"]):
                    stop(f"inconsistent duplicate {k}")
                continue
            on[k] = r
    return on


def conc(rd):
    pn = list((rd / "pernode").glob("*.csv"))
    if len(pn) != 1:
        stop(f"pernode files in {rd}")
    sens = [r for r in rows_of(pn[0]) if r["is_gateway"] == "0"]
    le1 = [r for r in sens if 0 <= int(float(r["hop_to_gw"])) <= 1]
    tot = sum(int(r["mac_queue_drops"]) for r in sens)
    return len(le1) / len(sens), (sum(int(r["mac_queue_drops"]) for r in le1) / tot if tot else None)


def check(label, ours, ref, tol):
    diff = abs(ours - ref)
    CHECK.append(f"{'OK ' if diff <= tol else 'BAD'} {label}: ours {ours:.4f} ref {ref:.4f} |diff| {diff:.4g} (tol {tol})")
    if diff > tol:
        stop(f"cross-check failed: {label}")


def write(name, rows):
    with open(OUT / name, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        for r in rows:
            w.writerow({k: (f"{v:.4f}" if isinstance(v, float) else v) for k, v in r.items()})


def main():
    on = load_on()
    # ---------- frozen Stage 1 ----------
    fz = {}
    for f in sorted((ROOT / "results/v3-ext").glob("*_static.csv")):
        for r in rows_of(f):
            if 20 <= int(r["Seed"]) <= 30:
                fz[(r["RoutingProtocol"], int(r["NumberOfNodes"]), RATE[r["TrafficLevel"]], int(r["Seed"]))] = \
                    100 * int(r["PacketsReceived"]) / int(r["PacketsSent"])
    seeds = {"low": S3, "medium": S3, "high": S11}

    # ---------- Table 4.1: paired diagnostic ----------
    t41 = []
    off_dirs = {}
    for rd in sorted((W / "arp-phase1-off").glob("b-off_*")):
        k, r = run_record(rd, "0")
        off_dirs[k] = r
    if len(off_dirs) != 14:
        stop("phase1-off count")
    for k in sorted(off_dirs, key=lambda x: (x[0] != "static", x[1], -x[2], x[3])):
        f, n = off_dirs[k], on[k]
        loss_f, loss_n = f["tx"] - f["rx"], n["tx"] - n["rx"]
        res_f = loss_f - (f["mq"] + f["rt"] + f["ip"])
        res_n = loss_n - (n["mq"] + n["rt"] + n["ip"])
        t41.append(dict(protocol=k[0], N=k[1], rate_kbps=k[2], seed=k[3], pdr_off=f["pdr"], pdr_on=n["pdr"],
                        loss_off=loss_f, arp_off=f["arp"], residual_off=res_f, arp_pct_of_residual=100 * f["arp"] / res_f,
                        residual_minus_arp_off=res_f - f["arp"], loss_on=loss_n, arp_on=n["arp"], residual_on=res_n))
    write("t41_diagnostic.csv", t41)
    st50 = [r for r in t41 if r["protocol"] == "static"]
    CHECK.append(f"INFO T4.1 Static N=50: ARP/residual {min(r['arp_pct_of_residual'] for r in st50):.1f}-"
                 f"{max(r['arp_pct_of_residual'] for r in st50):.1f} %; residual-ARP {min(r['residual_minus_arp_off'] for r in st50)}"
                 f" to {max(r['residual_minus_arp_off'] for r in st50)}; residual on {min(r['residual_on'] for r in st50)} to "
                 f"{max(r['residual_on'] for r in st50)}; PDR off {min(r['pdr_off'] for r in st50):.1f}-"
                 f"{max(r['pdr_off'] for r in st50):.1f}, on {min(r['pdr_on'] for r in st50):.1f}-{max(r['pdr_on'] for r in st50):.1f}")

    # ---------- Table 4.2: pooled PDR (means only) ----------
    pooled_ref = {(r["protocol"], int(r["N"])): r for r in rows_of(W / "v3ext-arp-analysis/pooled.csv")}
    t42 = []
    for p in PROTOS:
        for n in NS:
            ks = [(p, n, RATE[t], s) for t in TRAFFIC for s in S3]
            off_m, on_m = st.mean(fz[k] for k in ks), st.mean(on[k]["pdr"] for k in ks)
            check(f"T4.2 {p} N={n} PDR off", off_m, float(pooled_ref[(p, n)]["pdr_off"]), 0.01)
            check(f"T4.2 {p} N={n} PDR on", on_m, float(pooled_ref[(p, n)]["pdr_on"]), 0.01)
            t42.append(dict(protocol=p, N=n, n_runs=len(ks), pdr_off=off_m, pdr_on=on_m, change_pp=on_m - off_m))
    write("t42_pooled_pdr.csv", t42)

    # ---------- Table 4.3: per-cell PDR, paired change; ranking ----------
    cells_ref = {(r["protocol"], int(r["N"]), r["traffic"]): r for r in rows_of(W / "v3ext-arp-analysis/cells.csv")}
    t43, rank = [], []
    for t in TRAFFIC:
        for n in NS:
            means_on, means_off = {}, {}
            for p in PROTOS:
                ks = [(p, n, RATE[t], s) for s in seeds[t]]
                d = [on[k]["pdr"] - fz[k] for k in ks]
                pon, poff = [on[k]["pdr"] for k in ks], [fz[k] for k in ks]
                means_on[p], means_off[p] = st.mean(pon), st.mean(poff)
                ref = cells_ref[(p, n, t)]
                check(f"T4.3 {p} N={n} {t} PDR on", means_on[p], float(ref["pdr_on"]), 0.01)
                check(f"T4.3 {p} N={n} {t} dPDR", st.mean(d), float(ref["dpdr"]), 0.01)
                t43.append(dict(traffic=t, N=n, protocol=p, n_seeds=len(ks), pdr_off=means_off[p], pdr_on=means_on[p],
                                pdr_on_ci=ci(pon), pdr_on_min=min(pon), pdr_on_max=max(pon),
                                change_pp=st.mean(d), change_ci=ci(d), seeds_up=sum(x > 0 for x in d)))
            lead_on, lead_off = max(means_on, key=means_on.get), max(means_off, key=means_off.get)
            second = sorted(means_on.values())[-2]
            rank.append(dict(traffic=t, N=n, n_seeds=len(seeds[t]), leader_off=lead_off, leader_on=lead_on,
                             leader_on_pdr=means_on[lead_on], margin_over_second_pp=means_on[lead_on] - second))
    write("t43_cells.csv", t43)
    write("t43a_ranking.csv", rank)

    # ---------- Table 4.4: bottleneck ----------
    fb = {(r["protocol"], int(r["nodes"]), {"medium": 8, "high": 16}[r["trafficLevel"]], int(r["seed"])): r
          for r in rows_of(ROOT / "analysis/bottleneck-characterisation/data/probe_aggregate.csv")}
    if len(fb) != 176:
        stop("frozen bottleneck count")
    t4ref = {(r["protocol"], int(r["N"]), r["traffic"]): r for r in rows_of(W / "table4-arp-analysis/table4_on_vs_off.csv")}
    t44 = []
    for p in ("olsr", "static"):
        for n in (30, 50, 75, 100):
            for t, rate in (("medium", 8), ("high", 16)):
                ks = [(p, n, rate, s) for s in S11]
                if any(k not in on for k in ks):
                    stop(f"bottleneck coverage {p} {n} {t}")
                gw = [on[k]["gw"] for k in ks]
                fr = [conc(on[k]["dir"]) for k in ks]
                withd = [x[1] for x in fr if x[1] is not None]
                cratio = st.mean(withd) / st.mean(x[0] for x in fr) if withd else float("nan")
                row = dict(protocol=p, N=n, traffic=t, n_seeds=11,
                           pdr_off=st.mean(100 * int(fb[k]["rxPkts"]) / int(fb[k]["txPkts"]) for k in ks),
                           pdr_on=st.mean(on[k]["pdr"] for k in ks),
                           gw_air_off=st.mean(float(fb[k]["gw_airtime_busy_frac"]) for k in ks),
                           gw_air_on=st.mean(gw), gw_air_on_ci=ci(gw),
                           ring1_on=st.mean(on[k]["ring1"] for k in ks),
                           macq_events_off=st.mean(int(fb[k]["total_mac_queue_drops"]) for k in ks),
                           macq_events_on=st.mean(on[k]["mq"] for k in ks),
                           hop1_conc_ratio_on=cratio, seeds_with_macq_on=len(withd))
                ref = t4ref[(p, n, t)]
                check(f"T4.4 {p} N={n} {t} gw on", row["gw_air_on"], float(ref["gw_air_on"]), 0.0005)
                check(f"T4.4 {p} N={n} {t} macq on", row["macq_events_on"], float(ref["macq_on"]), 0.5)
                check(f"T4.4 {p} N={n} {t} pdr on", row["pdr_on"], float(ref["pdr_on"]), 0.01)
                if not math.isnan(cratio):
                    check(f"T4.4 {p} N={n} {t} conc", cratio, float(ref["conc_on"]), 0.005)
                t44.append(row)
    write("t44_bottleneck.csv", t44)

    # ---------- Table 4.5: rate sweep ----------
    fr_ = {(r["protocol"], int(r["nodes"]), int(float(r["offered_rate_kbps"])), int(r["seed"])): r
           for r in rows_of(ROOT / "analysis/bottleneck-characterisation/data-ratesweep/probe_aggregate.csv")}
    if len(fr_) != 72:
        stop("frozen rate-sweep count")
    rsref = {(r["protocol"], int(r["N"]), int(r["rate_kbps"])): r for r in rows_of(W / "arp-ratesweep-analysis/cells_vs_frozen.csv")}
    t45 = []
    for p in ("olsr", "static"):
        for n in (50, 75, 100):
            base_on = {s: on[(p, n, 16, s)]["pdr"] for s in S3}
            base_off = {s: 100 * int(fr_[(p, n, 16, s)]["rxPkts"]) / int(fr_[(p, n, 16, s)]["txPkts"]) for s in S3}
            means = {}
            for rate in (16, 12, 8, 4):
                pon = {s: on[(p, n, rate, s)]["pdr"] for s in S3}
                poff = {s: 100 * int(fr_[(p, n, rate, s)]["rxPkts"]) / int(fr_[(p, n, rate, s)]["txPkts"]) for s in S3}
                means[rate] = st.mean(pon.values())
                row = dict(protocol=p, N=n, rate_kbps=rate, n_seeds=3, pdr_off=st.mean(poff.values()),
                           pdr_on=means[rate], pdr_on_min=min(pon.values()), pdr_on_max=max(pon.values()),
                           change_vs16_off_pp=st.mean(poff[s] - base_off[s] for s in S3),
                           change_vs16_on_pp=st.mean(pon[s] - base_on[s] for s in S3),
                           seeds_above_16_on=sum(pon[s] > base_on[s] for s in S3) if rate != 16 else "",
                           gw_air_on=st.mean(on[(p, n, rate, s)]["gw"] for s in S3),
                           macq_events_on=st.mean(on[(p, n, rate, s)]["mq"] for s in S3))
                ref = rsref[(p, n, rate)]
                check(f"T4.5 {p} N={n} {rate} pdr on", row["pdr_on"], float(ref["pdr_on_pct"]), 0.01)
                check(f"T4.5 {p} N={n} {rate} dPDR on", row["change_vs16_on_pp"], float(ref["dpdr_vs16_on_pp"]), 0.01)
                check(f"T4.5 {p} N={n} {rate} dPDR off", row["change_vs16_off_pp"], float(ref["dpdr_vs16_off_pp"]), 0.01)
                t45.append(row)
            mono = means[12] <= means[8] <= means[4]
            for r in t45[-4:]:
                r["monotonic_cell_mean_on"] = mono
    write("t45_ratesweep.csv", t45)

    # ---------- Table 4.7: reproducibility ----------
    man = rows_of(ROOT / "analysis/final-reproducibility-check/run_manifest.csv")
    comp = rows_of(ROOT / "analysis/final-reproducibility-check/reproducibility_comparison.csv")
    t47 = []
    for case in ("A", "B", "C", "D"):
        mr = [r for r in man if r["case"] == case]
        cr = [r for r in comp if r["dataset"].endswith(f"Case{case}") or f"-Case{case}" in r["dataset"]]
        t47.append(dict(case=case, reruns=len(mr), runs_ok=sum(r["status"] == "OK" for r in mr), comparisons=len(cr),
                        passed=sum(r["status"] == "PASS" for r in cr),
                        pass_nonzero_diff=sum(r["status"] == "PASS" and float(r["absolute_difference"] or 0) != 0 for r in cr),
                        not_applicable=sum(r["status"] == "NOT_APPLICABLE" for r in cr),
                        failed=sum(r["status"] not in ("PASS", "NOT_APPLICABLE") for r in cr)))
    if sum(r["comparisons"] for r in t47) != 687 or sum(r["reruns"] for r in t47) != 51:
        stop("reproducibility totals")
    write("t47_reproducibility.csv", t47)

    figures(t43, t44, t45)
    (OUT / "CROSSCHECK.txt").write_text("\n".join(CHECK) + "\n")
    (OUT / "INPUTS.sha256").write_text("".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(ROOT)}\n"
                                               for p in sorted(INPUTS)))
    bad = [c for c in CHECK if c.startswith("BAD")]
    print(f"OK: {len(on)} distinct flag-on runs; {sum(c.startswith('OK') for c in CHECK)} cross-checks passed, "
          f"{len(bad)} failed; {len(INPUTS)} inputs hashed")


def figures(t43, t44, t45):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    color = {"aodv": "#2a78d6", "olsr": "#eb6834", "static": "#1baf7a"}   # validated categorical slots 1-3
    marker = {"aodv": "o", "olsr": "s", "static": "^"}
    name = {"aodv": "AODV", "olsr": "OLSR", "static": "Static"}
    ink, muted, grid = "#1f1f1e", "#6b6a64", "#e6e5e0"
    plt.rcParams.update({"font.size": 9, "axes.edgecolor": muted, "axes.labelcolor": ink, "xtick.color": muted,
                         "ytick.color": muted, "axes.spines.top": False, "axes.spines.right": False})

    def end_labels(ax, ends, sep, x):
        y_used = []
        for y, p in sorted(ends):
            y = max([y] + [u + sep for u in y_used[-1:]])
            y_used.append(y)
            ax.annotate(name[p], (x, y), xytext=(4, 0), textcoords="offset points", color=ink, fontsize=8,
                        va="center", annotation_clip=False)

    # Figure 4.1: PDR vs N, ARP-fixed (solid) with original configuration (dashed, faded)
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.4), sharey=True)
    for ax, t in zip(axes, TRAFFIC):
        ends = []
        for p in PROTOS:
            sel = [r for r in t43 if r["traffic"] == t and r["protocol"] == p]
            xs = [r["N"] for r in sel]
            ys = [r["pdr_on"] for r in sel]
            if t == "high":
                err = [[r["pdr_on_ci"] for r in sel], [r["pdr_on_ci"] for r in sel]]
            else:
                err = [[r["pdr_on"] - r["pdr_on_min"] for r in sel], [r["pdr_on_max"] - r["pdr_on"] for r in sel]]
            ax.plot(xs, [r["pdr_off"] for r in sel], color=color[p], linewidth=1, linestyle="--", alpha=0.45)
            ax.errorbar(xs, ys, yerr=err, color=color[p], marker=marker[p], markersize=5, linewidth=2, capsize=2,
                        elinewidth=1, label=f"{name[p]} (ARP-fixed)")
            ends.append((ys[-1], p))
        end_labels(ax, ends, 6, NS[-1])
        bars = "95 % CI, 11 seeds" if t == "high" else "min–max, 3 seeds"
        ax.set_title(f"{t} ({RATE[t]} kbit/s) · bars: {bars}", fontsize=8.5, color=ink)
        ax.set_xlabel("sensors N")
        ax.set_xticks(NS)
        ax.set_xlim(0, 115)
        ax.set_ylim(0, 100)
        ax.grid(axis="y", color=grid, linewidth=0.6)
    axes[0].set_ylabel("PDR, %")
    axes[0].plot([], [], color=muted, linestyle="--", linewidth=1, label="original configuration (dashed)")
    axes[0].legend(frameon=False, fontsize=7.5, loc="lower left")
    fig.suptitle("Packet delivery ratio, ARP-fixed 802.11b, static nodes (solid) vs original configuration (dashed)",
                 fontsize=10, color=ink, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(OUT / "fig_4_pdr.png", dpi=200)
    plt.close(fig)

    # Figure 4.2: gateway airtime vs N
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.4), sharey=True)
    for ax, t in zip(axes, ("medium", "high")):
        ends = []
        for p in ("olsr", "static"):
            sel = [r for r in t44 if r["traffic"] == t and r["protocol"] == p]
            xs = [r["N"] for r in sel]
            ax.plot(xs, [r["gw_air_off"] for r in sel], color=color[p], linewidth=1, linestyle="--", alpha=0.45)
            ax.errorbar(xs, [r["gw_air_on"] for r in sel], yerr=[r["gw_air_on_ci"] for r in sel], color=color[p],
                        marker=marker[p], markersize=5, linewidth=2, capsize=2, elinewidth=1,
                        label=f"{name[p]} (ARP-fixed)")
            ends.append((sel[-1]["gw_air_on"], p))
        end_labels(ax, ends, 0.05, 100)
        ax.set_title(f"{t} ({RATE[t]} kbit/s) · bars: 95 % CI, 11 seeds", fontsize=8.5, color=ink)
        ax.set_xlabel("sensors N")
        ax.set_xticks((30, 50, 75, 100))
        ax.set_xlim(20, 112)
        ax.set_ylim(0, 1)
        ax.grid(axis="y", color=grid, linewidth=0.6)
    axes[0].set_ylabel("gateway airtime (busy fraction)")
    axes[0].plot([], [], color=muted, linestyle="--", linewidth=1, label="original configuration (dashed)")
    axes[0].legend(frameon=False, fontsize=7.5, loc="lower right")
    fig.suptitle("Gateway radio busy fraction (TX + RX + CCA-busy)", fontsize=10, color=ink, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(OUT / "fig_4_airtime.png", dpi=200)
    plt.close(fig)

    # Figure 4.3: rate sweep PDR vs offered rate
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.4), sharey=True)
    for ax, n in zip(axes, (50, 75, 100)):
        ends = []
        for p in ("olsr", "static"):
            sel = sorted([r for r in t45 if r["N"] == n and r["protocol"] == p], key=lambda r: r["rate_kbps"])
            xs = [r["rate_kbps"] for r in sel]
            ax.plot(xs, [r["pdr_off"] for r in sel], color=color[p], linewidth=1, linestyle="--", alpha=0.45)
            ax.errorbar(xs, [r["pdr_on"] for r in sel],
                        yerr=[[r["pdr_on"] - r["pdr_on_min"] for r in sel], [r["pdr_on_max"] - r["pdr_on"] for r in sel]],
                        color=color[p], marker=marker[p], markersize=5, linewidth=2, capsize=2, elinewidth=1,
                        label=f"{name[p]} (ARP-fixed)")
            ends.append((sel[-1]["pdr_on"], p))
        end_labels(ax, ends, 6, 16)
        ax.set_title(f"N = {n} · bars: min–max, 3 seeds", fontsize=8.5, color=ink)
        ax.set_xlabel("offered rate per sensor, kbit/s")
        ax.set_xticks((4, 8, 12, 16))
        ax.set_xlim(2, 19)
        ax.set_ylim(0, 100)
        ax.grid(axis="y", color=grid, linewidth=0.6)
    axes[0].set_ylabel("PDR, %")
    axes[0].plot([], [], color=muted, linestyle="--", linewidth=1, label="original configuration (dashed)")
    axes[0].legend(frameon=False, fontsize=7.5, loc="lower left")
    fig.suptitle("Offered-rate sweep: PDR vs offered rate (descriptive, 3 seeds per point)", fontsize=10, color=ink,
                 x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(OUT / "fig_4_ratesweep.png", dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    main()
