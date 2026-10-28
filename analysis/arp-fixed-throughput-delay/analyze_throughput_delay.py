#!/usr/bin/env python3
"""G1: throughput and delay of AODV, OLSR and Static in the ARP-fixed, static-mobility 802.11b dataset (306 runs).

    myenv/bin/python -I -B analysis/arp-fixed-throughput-delay/analyze_throughput_delay.py

Read-only. Inputs: results/wifi-std/{arp-a2-on, arp-a1-on, arp-b-on-os}/b-on_*/{provenance.json, probe_aggregate.csv,
wifistd_ext.csv}, written by scratch/iot-network-wifi-std-arp.cc (--standard=80211b --arpPrepopulate=1).

Metric definitions (iot-network-wifi-std-arp.cc lines 543-570; FlowMonitor, gateway-bound flows only):
  throughputKbps = sum(rxBytes) * 8 / (270 s * 1000). rxBytes are IP packet bytes: 540 B per packet
                   (512 B payload + 8 B UDP + 20 B IP), checked per run below.
  goodput_kbps   = rxPkts * 512 * 8 / (270 s * 1000), i.e. payload only, in the same units as the offered rate.
  sched_delivery = 100 * rxPkts / scheduled sends. Scheduled sends = the Static (= AODV) FlowMonitor sent count for
                   the same N, rate and seed, checked identical below. Unlike PDR, this ratio does not depend on how
                   many packets OLSR sources managed to hand to the IP layer.
  delay_ms       = 1000 * sum(delaySum) / sum(rxPkts): packet-weighted mean one-way delay over delivered packets,
                   from the source IP send to gateway delivery. The simulator writes 0 when rxPkts = 0; such runs
                   would be treated as missing (none exist; checked).
Statistics: per-cell mean, SD, min, max; 95 % CI = t(0.975, n-1) * SD / sqrt(n). Paired protocol differences per
  seed (same node positions). n = 11 at high traffic; n = 3 at low and medium traffic, which is descriptive only.
  No significance tests are run.
Stops (exit 1) on any provenance, coverage, duplicate, unit or schedule check failure.
Outputs (this directory): runs.csv, cells.csv, paired.csv, INPUTS.sha256, REPORT.md,
  fig_g1_throughput.png, fig_g1_delay.png, fig_g1_delay_vs_delivery.png
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
DIRS = ("arp-a2-on", "arp-a1-on", "arp-b-on-os")
PROTOS, NS, TRAFFIC = ("aodv", "olsr", "static"), (10, 20, 30, 50, 75, 100), ("low", "medium", "high")
RATE = {"low": 4, "medium": 8, "high": 16}
LABEL = {"4": "low", "8": "medium", "16": "high"}
SEEDS = {"low": (20, 25, 30), "medium": (20, 25, 30), "high": tuple(range(20, 31))}
BIN_SHA, SRC_SHA = "9f74bd9ce2c6", "4923685a52f9"
WINDOW_S, PAYLOAD_B, IP_PKT_B = 270.0, 512, 540
T975 = {2: 4.303, 10: 2.228}
PAIRS = (("static", "olsr"), ("static", "aodv"), ("olsr", "aodv"))
METRICS = ("throughput_kbps", "goodput_kbps", "sched_delivery_pct", "pdr_pct", "delay_ms", "hop_count")


def stop(msg):
    sys.exit(f"STOP: {msg}")


def arg(argv, key):
    hit = [a.split("=", 1)[1] for a in argv if a.startswith(f"--{key}=")]
    return hit[0] if hit else None


def one_row(path):
    with open(path, newline="") as fh:
        rows = list(csv.DictReader(fh))
    if len(rows) != 1:
        stop(f"{path} has {len(rows)} data rows")
    return rows[0]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_runs():
    runs, inputs = {}, []
    for d in DIRS:
        for rd in sorted((W / d).glob("b-on_*")):
            prov = json.loads((rd / "provenance.json").read_text())
            agg, ext = one_row(rd / "probe_aggregate.csv"), one_row(rd / "wifistd_ext.csv")
            argv = prov["argv"]
            checks = {
                "exit 0": prov["exit_code"] == 0,
                "empty stderr": prov["stderr_bytes"] == 0,
                "binary": prov["binary_sha256"].startswith(BIN_SHA),
                "source": prov["source_sha256"].startswith(SRC_SHA),
                "802.11b": arg(argv, "standard") == "80211b",
                "flag argv": arg(argv, "arpPrepopulate") == "1",
                "flag output": ext["arp_prepopulate"] == "1",
                "0 ARP drops": int(ext["total_arp_l3_drops"]) + int(ext["total_arp_cache_drops"]) == 0,
                "no mobility arg": arg(argv, "mobility") is None,
            }
            bad = [k for k, ok in checks.items() if not ok]
            if bad:
                stop(f"{rd.relative_to(ROOT)} fails {bad}")
            rate = arg(argv, "offeredRateKbps")
            traffic = LABEL[rate] if rate else arg(argv, "trafficLevel")
            if traffic != "medium" and rate is None:
                stop(f"{rd.name}: no offered rate")
            key = (arg(argv, "protocol"), int(arg(argv, "nSensors")), traffic, int(arg(argv, "seed")))
            rec = dict(tx=int(agg["txPkts"]), rx=int(agg["rxPkts"]), pdr=float(agg["pdr"]),
                       thr=float(agg["throughputKbps"]), delay_s=float(agg["avgDelaySec"]),
                       hop=float(ext["avg_hop_count_v3"]), hop_method=ext["hop_count_method"],
                       argv=tuple(argv[1:-1]), src=str(rd.relative_to(ROOT)))
            inputs += [rd / "probe_aggregate.csv", rd / "wifistd_ext.csv", rd / "provenance.json"]
            if key in runs:
                old = runs[key]
                if (old["tx"], old["rx"], old["thr"], old["delay_s"], old["argv"]) != \
                        (rec["tx"], rec["rx"], rec["thr"], rec["delay_s"], rec["argv"]):
                    stop(f"duplicate {key} differs between {old['src']} and {rec['src']}")
                continue
            runs[key] = rec
    expected = {(p, n, t, s) for p in PROTOS for n in NS for t in TRAFFIC for s in SEEDS[t]}
    if set(runs) != expected:
        stop(f"coverage: missing {sorted(expected - set(runs))[:5]}, extra {sorted(set(runs) - expected)[:5]}")
    return runs, inputs


def derive(runs):
    sched = {}
    for (p, n, t, s), r in runs.items():
        if p == "olsr":
            continue
        if sched.setdefault((n, t, s), r["tx"]) != r["tx"]:
            stop(f"AODV and Static sent counts differ at N={n} {t} seed {s}")
    rows = []
    for (p, n, t, s), r in sorted(runs.items()):
        if r["rx"] == 0:
            stop(f"zero reception at {(p, n, t, s)}: delay sentinel would need handling")
        if abs(r["thr"] * WINDOW_S * 1000 / 8 - r["rx"] * IP_PKT_B) > 0.01 * r["rx"] + 1:
            stop(f"{(p, n, t, s)}: throughput does not equal 540 B per received packet")
        if abs(100 * r["rx"] / r["tx"] - r["pdr"]) > 1e-3:
            stop(f"{(p, n, t, s)}: PDR does not recompute")
        rows.append(dict(protocol=p, N=n, traffic=t, rate_kbps=RATE[t], seed=s, tx=r["tx"], rx=r["rx"],
                         scheduled=sched[(n, t, s)],
                         throughput_kbps=r["thr"],
                         goodput_kbps=r["rx"] * PAYLOAD_B * 8 / (WINDOW_S * 1000),
                         sched_delivery_pct=100 * r["rx"] / sched[(n, t, s)],
                         pdr_pct=r["pdr"], delay_ms=1000 * r["delay_s"], hop_count=r["hop"],
                         hop_method=r["hop_method"], source=r["src"]))
    return rows


def summary(vals):
    n = len(vals)
    m, sd = st.mean(vals), st.stdev(vals)
    hw = T975[n - 1] * sd / math.sqrt(n)
    return dict(n=n, mean=m, sd=sd, min=min(vals), max=max(vals), ci_lo=m - hw, ci_hi=m + hw)


def cells_table(rows):
    out = []
    for t in TRAFFIC:
        for n in NS:
            for p in PROTOS:
                sel = [r for r in rows if (r["protocol"], r["N"], r["traffic"]) == (p, n, t)]
                rec = dict(traffic=t, rate_kbps=RATE[t], N=n, protocol=p,
                           offered_payload_kbps=n * RATE[t], evidence="CI" if len(sel) == 11 else "descriptive")
                for mname in METRICS:
                    s = summary([r[mname] for r in sel])
                    for k, v in s.items():
                        rec[f"{mname}_{k}" if k != "n" else "n"] = v
                out.append(rec)
    return out


def paired_table(rows):
    idx = {(r["protocol"], r["N"], r["traffic"], r["seed"]): r for r in rows}
    out = []
    for t in TRAFFIC:
        for n in NS:
            for a, b in PAIRS:
                for mname in ("goodput_kbps", "delay_ms"):
                    d = [idx[(a, n, t, s)][mname] - idx[(b, n, t, s)][mname] for s in SEEDS[t]]
                    s = summary(d)
                    out.append(dict(traffic=t, N=n, contrast=f"{a}-{b}", metric=mname, n=s["n"],
                                    mean_diff=s["mean"], sd_diff=s["sd"], min_diff=s["min"], max_diff=s["max"],
                                    ci_lo=s["ci_lo"], ci_hi=s["ci_hi"],
                                    seeds_positive=sum(x > 0 for x in d), seeds_negative=sum(x < 0 for x in d),
                                    ci_excludes_zero=(s["ci_lo"] > 0 or s["ci_hi"] < 0) if s["n"] == 11 else "n/a",
                                    evidence="CI" if s["n"] == 11 else "descriptive"))
    return out


def write_csv(path, rows):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        for r in rows:
            w.writerow({k: (f"{v:.6g}" if isinstance(v, float) else v) for k, v in r.items()})


def figures(cells):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available: figures skipped")
        return []
    color = {"aodv": "#2a78d6", "olsr": "#eb6834", "static": "#1baf7a"}   # validated categorical slots 1-3
    marker = {"aodv": "o", "olsr": "s", "static": "^"}
    name = {"aodv": "AODV", "olsr": "OLSR", "static": "Static"}
    ink, muted, grid = "#1f1f1e", "#6b6a64", "#e6e5e0"
    plt.rcParams.update({"font.size": 9, "axes.edgecolor": muted, "axes.labelcolor": ink, "xtick.color": muted,
                         "ytick.color": muted, "axes.spines.top": False, "axes.spines.right": False})
    made = []

    def panel_fig(metric, ylabel, fname, title, offered_line=False):
        fig, axes = plt.subplots(1, 3, figsize=(10, 3.4), sharey=False)
        for ax, t in zip(axes, TRAFFIC):
            ends = sorted(((c[f"{metric}_mean"], c["protocol"]) for c in cells
                           if c["traffic"] == t and c["N"] == NS[-1]))
            sep = 0.06 * max(c[f"{metric}_mean"] for c in cells if c["traffic"] == t)
            label_y = {}
            for y, p in ends:                       # push end labels apart so they never overlap
                prev = max(label_y.values(), default=-math.inf)
                label_y[p] = max(y, prev + sep)
            for p in PROTOS:
                sel = [c for c in cells if c["traffic"] == t and c["protocol"] == p]
                xs = [c["N"] for c in sel]
                ys = [c[f"{metric}_mean"] for c in sel]
                if t == "high":
                    lo = [c[f"{metric}_mean"] - c[f"{metric}_ci_lo"] for c in sel]
                    hi = [c[f"{metric}_ci_hi"] - c[f"{metric}_mean"] for c in sel]
                else:
                    lo = [c[f"{metric}_mean"] - c[f"{metric}_min"] for c in sel]
                    hi = [c[f"{metric}_max"] - c[f"{metric}_mean"] for c in sel]
                ax.errorbar(xs, ys, yerr=[lo, hi], color=color[p], marker=marker[p], markersize=5, linewidth=2,
                            capsize=2, elinewidth=1, label=name[p])
                ax.annotate(name[p], (xs[-1], label_y[p]), xytext=(4, 0), textcoords="offset points",
                            color=ink, fontsize=8, va="center", annotation_clip=False)
            if offered_line:
                ax.plot(NS, [n * RATE[t] for n in NS], color=muted, linewidth=1, linestyle="--")
                ax.annotate("offered", (NS[2], NS[2] * RATE[t]), xytext=(2, 4), textcoords="offset points",
                            color=muted, fontsize=7)
            bars = "95 % CI, 11 seeds" if t == "high" else "min–max, 3 seeds"
            ax.set_title(f"{t} ({RATE[t]} kbit/s per sensor) · bars: {bars}", fontsize=8.5, color=ink)
            ax.set_xlabel("sensors N")
            ax.set_xticks(NS)
            ax.set_xlim(0, 115)
            ax.grid(axis="y", color=grid, linewidth=0.6)
            ax.set_ylim(bottom=0)
        axes[0].set_ylabel(ylabel)
        axes[0].legend(frameon=False, fontsize=8, loc="upper left")
        fig.suptitle(title, fontsize=10, color=ink, x=0.01, ha="left")
        fig.tight_layout()
        fig.savefig(OUT / fname, dpi=200)
        plt.close(fig)
        made.append(fname)

    panel_fig("goodput_kbps", "goodput, kbit/s (payload)", "fig_g1_throughput.png",
              "Delivered payload throughput at the gateway, ARP-fixed 802.11b, static nodes", offered_line=True)
    panel_fig("delay_ms", "mean one-way delay, ms (delivered packets)", "fig_g1_delay.png",
              "Mean delay of delivered packets, ARP-fixed 802.11b, static nodes")

    fig, axes = plt.subplots(1, 3, figsize=(10, 3.4), sharey=True)
    for ax, t in zip(axes, TRAFFIC):
        for p in PROTOS:
            sel = [c for c in cells if c["traffic"] == t and c["protocol"] == p]
            ax.scatter([c["sched_delivery_pct_mean"] for c in sel], [c["delay_ms_mean"] for c in sel],
                       color=color[p], marker=marker[p], s=36, edgecolors="white", linewidths=1.5, label=name[p])
            for c in sel:
                ax.annotate(str(c["N"]), (c["sched_delivery_pct_mean"], c["delay_ms_mean"]), xytext=(3, 2),
                            textcoords="offset points", fontsize=6.5, color=muted)
        ax.set_title(f"{t} ({RATE[t]} kbit/s) · labels = N", fontsize=8.5, color=ink)
        ax.set_xlabel("delivered / scheduled packets, %")
        ax.set_xlim(0, 100)
        ax.grid(color=grid, linewidth=0.6)
    axes[0].set_ylabel("mean delay, ms")
    axes[0].legend(frameon=False, fontsize=8, loc="upper right")
    fig.suptitle("Delay is measured on delivered packets only: compare it alongside delivery", fontsize=10,
                 color=ink, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(OUT / "fig_g1_delay_vs_delivery.png", dpi=200)
    plt.close(fig)
    made.append("fig_g1_delay_vs_delivery.png")
    return made


def report(rows, cells, paired, figs):
    c = {(x["protocol"], x["N"], x["traffic"]): x for x in cells}
    pr = {(x["contrast"], x["N"], x["traffic"], x["metric"]): x for x in paired}
    L = ["# G1: ARP-fixed throughput and delay (generated by analyze_throughput_delay.py)", "",
         f"Runs: {len(rows)} unique (306 expected); all provenance, coverage, duplicate, unit and schedule checks passed.",
         "Throughput below is payload goodput (kbit/s), comparable with the offered rate; the simulator's "
         "throughputKbps equals goodput x 540/512 in every run.", "",
         "## Goodput, mean per cell (kbit/s); offered payload = N x rate", "",
         "| traffic | N | offered | AODV | OLSR | Static | highest |", "|---|---|---|---|---|---|---|"]
    for t in TRAFFIC:
        for n in NS:
            v = {p: c[(p, n, t)]["goodput_kbps_mean"] for p in PROTOS}
            L.append(f"| {t} | {n} | {n * RATE[t]} | " + " | ".join(f"{v[p]:.1f}" for p in PROTOS)
                     + f" | {max(v, key=v.get)} |")
    L += ["", "## Mean delay of delivered packets, per cell (ms)", "",
          "| traffic | N | AODV | OLSR | Static | lowest |", "|---|---|---|---|---|---|"]
    for t in TRAFFIC:
        for n in NS:
            v = {p: c[(p, n, t)]["delay_ms_mean"] for p in PROTOS}
            L.append(f"| {t} | {n} | " + " | ".join(f"{v[p]:.1f}" for p in PROTOS) + f" | {min(v, key=v.get)} |")
    L += ["", "## High traffic (11 seeds): paired differences with 95 % CI", "",
          "| N | contrast | goodput diff kbit/s [CI] | seeds +/- | delay diff ms [CI] | seeds +/- |",
          "|---|---|---|---|---|---|"]
    for n in NS:
        for a, b in PAIRS:
            g, d = pr[(f"{a}-{b}", n, "high", "goodput_kbps")], pr[(f"{a}-{b}", n, "high", "delay_ms")]
            L.append(f"| {n} | {a}-{b} | {g['mean_diff']:+.1f} [{g['ci_lo']:+.1f}, {g['ci_hi']:+.1f}] | "
                     f"{g['seeds_positive']}/{g['seeds_negative']} | {d['mean_diff']:+.1f} [{d['ci_lo']:+.1f}, "
                     f"{d['ci_hi']:+.1f}] | {d['seeds_positive']}/{d['seeds_negative']} |")
    L += ["", "Low and medium traffic have 3 seeds per cell: see paired.csv (descriptive only, no CI claimed).",
          "", "Figures: " + (", ".join(figs) if figs else "none (matplotlib unavailable)")]
    (OUT / "REPORT.md").write_text("\n".join(L) + "\n")


def main():
    runs, inputs = load_runs()
    rows = derive(runs)
    cells = cells_table(rows)
    paired = paired_table(rows)
    write_csv(OUT / "runs.csv", rows)
    write_csv(OUT / "cells.csv", cells)
    write_csv(OUT / "paired.csv", paired)
    (OUT / "INPUTS.sha256").write_text("".join(f"{sha256(p)}  {p.relative_to(ROOT)}\n" for p in sorted(set(inputs))))
    figs = figures(cells)
    report(rows, cells, paired, figs)
    print(f"OK: {len(rows)} runs, {len(cells)} cells, {len(paired)} paired rows, {len(set(inputs))} inputs hashed, "
          f"figures: {figs}")


if __name__ == "__main__":
    main()
