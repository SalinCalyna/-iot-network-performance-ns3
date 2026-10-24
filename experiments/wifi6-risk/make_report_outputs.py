#!/usr/bin/env python3
"""Wi-Fi 6 risk study: report tables T-W1..T-W7 and figures F-W1..F-W8 from existing validated results only.
Read-only on results/; no simulation is run. Needs matplotlib + numpy (project venv):

    myenv/bin/python -I -B experiments/wifi6-risk/make_report_outputs.py

Writes analysis/wifi6-risk-writeup/:
  tables/T-W*.csv          machine-readable tables
  TABLES.md                all tables, formatted, with sources, sample sizes and caveats
  figures/F-W*.pdf / .png  figures (PDF vector, PNG 300 dpi)
  FIGURES.md               captions (sources, n, interval definition, caveats)
  inventory.json           input files used (sha256) and output files
Statistics: N = 30 (seeds 20-29, n = 10) uses the inferential results already computed by analyze_paired_stats.py
(paired t CI, exact Wilcoxon, Holm over the primary family). N = 100 (seeds 20-22, n = 3) is descriptive only: the
Student-t 95 % interval of the mean is shown as a descriptive range and no p-value is reported.
"""
import csv
import hashlib
import importlib.util
import json
import math
import statistics as st
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RES = ROOT / "results/wifi6-risk"
OUT = ROOT / "analysis/wifi6-risk-writeup"
TAB, FIG = OUT / "tables", OUT / "figures"
B30 = RES / "seeds10-n30-8k-v2-20261024T160515"
B100 = RES / "n100-8k-v2-20261024T165009"
PILOT = RES / "pilot-n30-v2-20261024T054949"
SMOKE = RES / "lowload-smoke-v2-20261024T041410"
DIAG = RES / "aodv-diag-n100-20261024T204129"
DELAY = RES / "diag-delay-20261021"
V4CMP = RES / "v4-tail-check-20261023T222251/compare_v2_v3_v4.csv"
PROTOS = ("static", "riskaware", "olsr", "aodv")
LABEL = {"static": "Static", "riskaware": "Risk-Aware", "olsr": "OLSR", "aodv": "AODV"}
COLOR = {"static": "#4C72B0", "riskaware": "#DD8452", "olsr": "#55A868", "aodv": "#C44E52"}
MARK = {"static": "o", "riskaware": "s", "olsr": "^", "aodv": "D"}
USED = {}

spec = importlib.util.spec_from_file_location("aps", HERE / "analyze_paired_stats.py")
APS = importlib.util.module_from_spec(spec)
spec.loader.exec_module(APS)

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.titlesize": 9.5, "axes.labelsize": 9,
                     "legend.fontsize": 8, "figure.constrained_layout.use": True, "xtick.labelsize": 8.5, "ytick.labelsize": 8.5, "axes.spines.top": False,
                     "axes.spines.right": False, "savefig.bbox": "tight", "pdf.fonttype": 42})


def use(p):
    p = Path(p)
    if p not in USED:
        USED[p] = hashlib.sha256(p.read_bytes()).hexdigest()
    return p


def rows(p):
    with open(use(p), newline="") as f:
        return list(csv.DictReader(f))


def runs_of(b):
    return {(r["protocol"], int(r["k"]), int(r["seed"])): r for r in rows(b / "analysis/pilot_runs.csv")}


def run_dir(b, name):
    d = b / "runs" / name
    if d.exists():
        return d
    for m in json.loads(use(b / "reuse_manifest.json").read_text()):
        if m["run_id"] == name:
            return ROOT / m["path"]
    raise FileNotFoundError(name)


def ci(xs):
    m, sd, lo, hi = APS.ci95(xs)
    return m, sd, lo, hi


def f(x, nd=2):
    return "" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.{nd}f}"


def pm(xs, nd=2):
    m, sd, lo, hi = ci(xs)
    return f"{m:.{nd}f} ± {sd:.{nd}f} [{lo:.{nd}f}, {hi:.{nd}f}]"


def write_csv(name, header, data):
    with open(TAB / f"{name}.csv", "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows(data)


def md_table(header, data):
    s = "| " + " | ".join(header) + " |\n|" + "---|" * len(header) + "\n"
    return s + "".join("| " + " | ".join(str(c) for c in r) + " |\n" for r in data)


def save(fig, name):
    fig.savefig(FIG / f"{name}.pdf", metadata={"CreationDate": None})   # deterministic PDF bytes
    fig.savefig(FIG / f"{name}.png", dpi=300)
    plt.close(fig)


MD, CAP, ISSUES = [], [], []


# ------------------------------------------------------------------ T-W1 parameters (verified against read-back)
def t_w1():
    b30 = json.loads(use(B30 / "batch.json").read_text())
    b100 = json.loads(use(B100 / "batch.json").read_text())
    rb_bad, nrb = [], 0
    for b, R in ((B30, runs_of(B30)), (B100, runs_of(B100))):
        for r in R.values():
            for x in rows(run_dir(b, r["run"]) / "wifi_readback.csv"):
                nrb += 1
                if (x["standard"], x["band"], x["channel_number"], x["channel_width_mhz"], x["he_guard_interval_ns"],
                        x["data_mode"], x["control_mode"], x["be_max_ampdu_bytes"], x["be_max_amsdu_bytes"]) != (
                        "802.11ax", "2.4GHz", "1", "20", "800", "HeMcs0", "ErpOfdmRate6Mbps", "0", "0"):
                    rb_bad.append((r["run"], x["node_id"]))
    assert not rb_bad, rb_bad[:3]
    base = b100["base_args"]
    data = [
        ("Simulator", "ns-3 scratch iot-network-wifi6-risk-v2 (risk-v2), unmodified for all results",
         f"binary sha256 {b100['binary_sha256'][:12]}…, source {b100['source_sha256'][:12]}…"),
        ("Wi-Fi standard", "IEEE 802.11ax (HE), ad-hoc MAC, Tier A", "--standard=80211ax; read-back"),
        ("Band / channel / width", "2.4 GHz, channel 1, 20 MHz", "read-back"),
        ("Data rate (unicast)", "ConstantRate HeMcs0, HE SU PPDU, GI 800 ns", "read-back; HE_SU/HeMcs0 checked (P6)"),
        ("Control / broadcast rate", "ERP-OFDM 6 Mbps", "read-back"),
        ("Aggregation", "A-MPDU and A-MSDU disabled (max 0 B); Block Ack agreements still set up by ns-3", "read-back"),
        ("Block Ack modification", "risk-v2 --baSsnFix=1: BlockAckReq when originator start ≠ advertised ADDBA SSN",
         "default on; see T-W2"),
        ("Tx power / propagation", "20 dBm; LogDistance, exponent 3.0, reference loss 40 dB at 1 m; constant speed", "source"),
        ("MAC queue lifetime", "ns-3 default (500 ms)", "not changed"),
        ("ARP", "pre-populated (--arpPrepopulate=1)", "base args"),
        ("Area / gateway", "250 m × 250 m, gateway at centre, sensors uniform random (seeded), static", "source"),
        ("Sensors N", "30 (seeds 20–29) and 100 (seeds 20–22)", "batch.json"),
        ("Traffic", "UDP CBR to gateway, 512 B payload, 8 kbps per sensor (one packet per 0.512 s); all sensors "
         "send at the same instants (synchronized, inherited V3 design)", "--trafficLevel=high --offeredRateKbps=8"),
        ("Timing", f"simTime {b100['simTime_s']} s, application start {b100['appStart_s']} s (270 s of traffic)",
         "batch.json"),
        ("Routing protocols", "Static (BFS tree on 90 m disk graph), Risk-Aware (risk-weighted Dijkstra on the same "
         "graph), OLSR and AODV (ns-3 defaults, unmodified)", "--protocol"),
        ("Risk model", "HIGH_RISK drop probability r = 0.5, LOW_RISK r = 0; k = 0–3 high-risk relays chosen by the "
         "subtree rule (most BFS descendants); risk-drop hash seed 1", "--highRiskDropProb=0.5 --lowRiskDropProb=0 "
         "--riskSelect=subtree --riskDropSeed=1"),
        ("Risk-Aware cost", "per transit node 1 + β·(−ln(1 − r)), β = 10; oracle knowledge of node risk", "--riskBeta=10"),
        ("Per-packet trace", "on (packet_paths.csv: path, fate, delay per packet)", "--perPacketTrace=1"),
        ("Throughput accounting", "delivered packets × 540 B (payload + UDP/IP headers) × 8 / 270 s", "analyze_pilot_n30.py"),
    ]
    assert "--nSensors=100" in base and "--highRiskDropProb=0.5" in base and "--riskBeta=10" in base
    assert b30["base_args"] == [a if a != "--nSensors=100" else "--nSensors=30" for a in base]
    write_csv("T-W1_parameters", ["parameter", "value", "source_or_check"], data)
    MD.append("## T-W1 — Simulation parameters (Wi-Fi 6 risk study)\n"
              f"All {len(runs_of(B30)) + len(runs_of(B100))} runs (N = 30: 160, N = 100: 48) share these settings; the "
              f"Wi-Fi read-back of every device in every run ({nrb:,} device rows) matches the listed PHY/MAC values.\n\n"
              + md_table(["Parameter", "Value", "Source / check"], data))


# ------------------------------------------------------------------ T-W2 Block Ack defect, fix and residual tail
def t_w2():
    a = []
    for k in (2, 3):
        for tag, lab in (("v2off", "fix off (= risk-v1)"), ("v2on", "fix on (risk-v2)")):
            pp = rows(DELAY / f"{tag}_k{k}/packet_paths.csv")
            d = sorted(float(x["delay_s"]) for x in pp if x["fate"] == "delivered")
            a.append((f"k = {k}", lab, len(d), f"{1000 * APS_pct(d, .99):.0f}", f"{d[-1]:.1f}", sum(x > 10 for x in d)))
    cmp_ = rows(V4CMP)
    b = []
    for r in cmp_:
        b.append((r["version"], r["seed"], r["sink_delivered"], r["gt10s"], f(float(r["gt10s_per_100k"]), 1),
                  f(float(r["delay_max_s"]), 1), f(float(r["delay_p99_ms"]), 0), r["sink_minus_fm"], r["bar_psdus"]))
    cases = [
        ("A", "duplicate ADDBA Request processed before the duplicate filter → 2nd ADDBA Response → originator window "
              "advanced silently; the missing SN is discarded as old, no BAR", "157 s", "fixed by risk-v3 (not adopted)"),
        ("B", "stale ADDBA Response matched to a newer Request", "10.5 s", "open"),
        ("C", "BlockAck to a BAR missed with no MPDU outstanding → BAR deferred until data is queued; OLSR moved the "
              "route away", "12.5 s", "open (needs a change to ns-3 BAR retransmission)"),
        ("D", "as C", "75.5 s", "open"),
    ]
    val = [("risk-v2", "validation-v2-20261021T181501", "6,206", "0", "adopted"),
           ("risk-v3", "validation-v3-20261022T133856", "6,322", "2 (packet-UID relabelling only)", "not adopted"),
           ("risk-v4", "validation-v4-20261023T222251", "6,354", "0", "not adopted (not consistently better)")]
    write_csv("T-W2a_ba_defect_n30", ["k", "variant", "delivered", "p99_ms", "max_delay_s", "gt10s"], a)
    write_csv("T-W2b_residual_tail_n100_64k", ["version", "seed", "sink_delivered", "gt10s", "gt10s_per_100k",
                                               "max_delay_s", "p99_ms", "sink_minus_fm", "bar_psdus"], b)
    write_csv("T-W2c_tail_mechanisms", ["case", "mechanism", "longest_hold", "status"], cases)
    write_csv("T-W2d_validation", ["version", "validation_batch", "checks_passed", "checks_failed", "decision"], val)
    MD.append("## T-W2 — Block Ack defect, risk-v2 fix and residual tail\n"
              "**(a) Defect and fix** — OLSR, N = 30, 16 kbps, seed 20, simTime 100 s (`diag-delay-20261021`; one seed, "
              "deterministic defect). With the fix off, MPDU 0 lost during the ADDBA handshake leaves the recipient "
              "window waiting until SN 256.\n\n"
              + md_table(["k", "Variant", "Delivered (pkts)", "p99 delay (ms)", "Max delay (s)", "Delayed > 10 s (pkts)"], a)
              + "\n**(b) Residual tail at saturation** — OLSR, N = 100, 64 kbps, k = 0, seeds 20–22, 300 s "
              "(`v4-tail-check-20261023T222251`). Saturated load is outside the main experiments; shown to bound the "
              "limitation. PDR is not shown because these earlier runs count app-tx (not nominal) offered packets.\n\n"
              + md_table(["Version", "Seed", "Delivered (pkts)", "> 10 s (pkts)", "> 10 s per 100k", "Max delay (s)",
                          "p99 (ms)", "Sink − FlowMonitor rx (pkts)", "BAR PSDUs"], b)
              + "\n**(c) Mechanisms of the residual tail** (confirmed by trace and ns-3 source; `diag-tail-20261022`)\n\n"
              + md_table(["Case", "Mechanism", "Longest hold", "Status"], cases)
              + "\n**(d) Validation of the simulator variants**\n\n"
              + md_table(["Version", "Validation batch", "Checks passed", "Failed", "Decision"], val))


def APS_pct(xs, q):
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else float("nan")


# ------------------------------------------------------------------ T-W3 load calibration
def t_w3():
    sm = rows(SMOKE / "lowload_runs.csv")
    by = defaultdict(list)
    for r in sm:
        by[int(r["rate_kbps"])].append(r)
    a = []
    for rate in sorted(by):
        R = by[rate]
        nominal = max(int(r["app_tx"]) for r in R)   # same schedule for all seeds; max = full schedule
        a.append((100, "OLSR", 0, rate, len(R), pm([100 * int(r["sink_delivered"]) / nominal for r in R]),
                  pm([float(r["gw_airtime"]) for r in R], 3), pm([float(r["delay_p99_ms"]) for r in R], 0),
                  sum(int(r["gt10s"]) for r in R), sum(nominal - int(r["app_tx"]) for r in R)))
        if any(int(r["app_tx"]) != nominal for r in R):
            ISSUES.append(f"T-W3: low-load smoke {rate} kbps: app_tx differs between seeds "
                          f"({sorted({r['app_tx'] for r in R})}); PDR in T-W3 uses the full schedule ({nominal}) as "
                          "nominal, whereas lowload_runs.csv reports app-tx-based sink PDR")
    P = rows(PILOT / "analysis/pilot_runs.csv")
    g = defaultdict(list)
    for r in P:
        if r["k"] == "0":
            g[(int(r["rate_kbps"]), r["protocol"])].append(r)
    for (rate, p) in sorted(g, key=lambda x: (x[0], PROTOS.index(x[1]))):
        R = g[(rate, p)]
        a.append((30, LABEL[p], 0, rate, len(R), pm([float(r["pdr_nominal_pct"]) for r in R]),
                  pm([float(r["gw_airtime"]) for r in R], 3), pm([float(r["delay_p99_ms"]) for r in R], 0),
                  sum(int(r["gt10s"]) for r in R), sum(int(r["unsent_at_source"]) for r in R)))
    h = ["N", "Protocol", "k", "Rate per sensor (kbps)", "n seeds", "Nominal PDR % mean ± SD [95% t]",
         "Gateway airtime mean ± SD [95% t]", "p99 delay (ms) mean ± SD [95% t]", "Delayed > 10 s (pkts, all seeds)",
         "Unsent at source (pkts, all seeds)"]
    write_csv("T-W3_load_calibration", h, a)
    MD.append("## T-W3 — Load calibration (why 8 kbps per sensor)\n"
              "N = 100: OLSR k = 0, seeds 20–22 (`lowload-smoke-v2-20261024T041410`); N = 30: k = 0, seeds 20–22 "
              "(`pilot-n30-v2-20261024T054949`). n = 3 per row: intervals are descriptive. 8 kbps is the highest tested "
              "N = 100 load with no packet > 10 s and gateway airtime ≈ 0.4; 16 kbps marks congestion onset.\n\n"
              + md_table(h, a))


# ------------------------------------------------------------------ T-W4 / T-W5 main results
METRICS = [("pdr_nominal_pct", "Nominal PDR (%)", 2), ("exposure_rate_pct", "Exposure (%)", 2),
           ("sink_thr_kbps", "Throughput (kbps)", 1), ("delay_p50_ms", "Delay p50 (ms)", 1),
           ("delay_p95_ms", "Delay p95 (ms)", 1), ("delay_p99_ms", "Delay p99 (ms)", 1),
           ("mean_hops_delivered", "Hops (delivered)", 3), ("gw_airtime", "Gateway airtime", 3)]


def main_table(b, name, n_expected, inferential):
    R = runs_of(b)
    seeds = sorted({s for (_, _, s) in R})
    assert len(seeds) == n_expected
    data = []
    for p in PROTOS:
        for k in range(4):
            row = [LABEL[p], k, len(seeds)]
            for m, _, nd in METRICS:
                row.append(pm([float(R[(p, k, s)][m]) for s in seeds], nd))
            data.append(row)
    h = ["Protocol", "k", "n seeds"] + [f"{lab} mean ± SD [95% t]" for _, lab, _ in METRICS]
    write_csv(f"{name}a_by_protocol", h, data)
    pr = {(int(x["k"]), x["metric"]): x for x in rows(b / "analysis/paired_riskaware_vs_static.csv")}
    pdata = []
    for k in (1, 2, 3):
        for m, lab, nd in METRICS:
            x = pr[(k, m)]
            # recompute from runs as a consistency check against the paired file
            d = [float(R[("riskaware", k, s)][m]) - float(R[("static", k, s)][m]) for s in seeds]
            mm, sd, lo, hi = ci(d)
            assert abs(mm - float(x["diff_mean"])) < 1e-9 and abs(sd - float(x["diff_sd"])) < 1e-9, (k, m)
            row = [k, lab, len(d), f"{float(x['static_mean']):.{nd}f}", f"{float(x['riskaware_mean']):.{nd}f}",
                   f"{mm:+.{nd}f}", f"{sd:.{nd}f}", f"[{lo:+.{nd}f}, {hi:+.{nd}f}]",
                   f"{x['pairs_riskaware_higher']}/{x['pairs_equal']}/{x['pairs_riskaware_lower']}"]
            if inferential:
                dz = x["cohen_dz"]
                row += [f"{float(dz):+.2f}" if dz not in ("", "nan") else "", f"{float(x['p_wilcoxon_exact']):.3g}",
                        f"{float(x['p_wilcoxon_holm']):.3g}" if x["p_wilcoxon_holm"] != "" else "— (secondary, unadjusted)"]
            else:
                row += [" ".join(f"{s}:{v:+.{nd}f}" for s, v in zip(seeds, d))]
            pdata.append(row)
    ph = ["k", "Metric", "n pairs", "Static mean", "Risk-Aware mean", "Diff (RA − S) mean", "Diff SD",
          "95% t interval of diff", "Pairs RA higher/equal/lower"]
    ph += ["Cohen d_z", "Exact Wilcoxon p", "Holm-adjusted p (primary)"] if inferential else ["Per-seed diff"]
    write_csv(f"{name}b_paired_ra_vs_static", ph, pdata)
    return h, data, ph, pdata, seeds


def t_w4_5():
    h, d, ph, pd, s = main_table(B30, "T-W4", 10, True)
    MD.append("## T-W4 — Main result, N = 30, 8 kbps, seeds 20–29 (n = 10; inferential)\n"
              "`seeds10-n30-8k-v2-20261024T160515` (160 runs, 1,830/1,830 checks). Intervals: Student-t 95 % CI of the "
              "mean (df = 9). Paired differences: same seed ⇒ same positions, traffic and high-risk set. Primary "
              "family (Holm, 6 tests): exposure and nominal PDR at k = 1–3. With n = 10 the smallest attainable exact "
              "two-sided Wilcoxon p is 0.00195. Delay and hops are over delivered packets (survivorship, see F-W4).\n\n"
              "**(a) By protocol and k**\n\n" + md_table(h, d)
              + "\n**(b) Paired Risk-Aware − Static**\n\n" + md_table(ph, pd))
    h, d, ph, pd, s = main_table(B100, "T-W5", 3, False)
    MD.append("## T-W5 — Main result, N = 100, 8 kbps, seeds 20–22 (n = 3; descriptive only)\n"
              "`n100-8k-v2-20261024T165009` (48 runs, 549/549 checks). Intervals: Student-t 95 % interval of the mean "
              "(df = 2), shown as a descriptive range; no hypothesis test is reported and no significance is claimed. "
              "AODV at N = 100 is affected by the route-maintenance behaviour in T-W6.\n\n"
              "**(a) By protocol and k**\n\n" + md_table(h, d)
              + "\n**(b) Paired Risk-Aware − Static (per-seed differences listed)**\n\n" + md_table(ph, pd))


# ------------------------------------------------------------------ T-W6 AODV at N = 100
def frames(d):
    tv = rows(d / "wifi_txvector_counts.csv")
    g = lambda c, t=None: sum(int(r["psdus"]) for r in tv if r["frame_class"] == c and (t is None or r["frame_type"] == t))
    return dict(broadcast=g("data_group"), unicast=g("data_unicast"), bar=g("ctl", "CTL_BACKREQ"),
                ba=g("ctl", "CTL_BACKRESP"), ack=g("ctl", "CTL_ACK"), mgmt=g("mgt"))


def path_stats(d):
    pp = rows(d / "packet_paths.csv")
    by = defaultdict(list)
    for r in pp:
        by[r["src"]].append(r)
    ch = 0
    for v in by.values():
        v.sort(key=lambda r: float(r["tx_time_s"]))
        ch += sum(a["path"] != b["path"] for a, b in zip(v, v[1:]))
    loops = sum(len(r["path"].split(">")) != len(set(r["path"].split(">"))) for r in pp)
    lost = [r for r in pp if r["fate"] != "delivered"]
    at_src = sum(len(r["path"].split(">")) == 1 for r in lost)
    win = defaultdict(lambda: [0, 0])
    for r in pp:
        w = int((float(r["tx_time_s"]) - 30) // 30)
        win[w][0] += 1
        win[w][1] += r["fate"] == "delivered"
    hop = {r["node_id"]: int(r["hop_to_gw"]) for r in rows(d / "risk_nodes.csv")}
    hg = defaultdict(lambda: [0, 0])
    for r in pp:
        hg[min(hop[r["src"]], 2)][0] += 1
        hg[min(hop[r["src"]], 2)][1] += r["fate"] == "delivered"
    return dict(pdr_hop1=100 * hg[1][1] / hg[1][0], pdr_hop2p=100 * hg[2][1] / hg[2][0],
                changes_per_src_min=ch / len(by) / 4.5, loops=loops, lost=len(lost), lost_at_src_pct=100 * at_src / len(lost)
                if lost else 0.0, win=[100 * b / a for _, (a, b) in sorted(win.items())], n=len(pp))


def t_w6():
    R = runs_of(B100)
    S = (20, 21, 22)
    m = {}
    for p in ("aodv", "olsr"):
        for s in S:
            d = B100 / "runs" / R[(p, 0, s)]["run"]
            m[(p, s)] = dict(frames(d), **path_stats(d), run=R[(p, 0, s)])
    rng = lambda p, key, fmt="{:,}": f"{fmt.format(min(m[(p, s)][key] for s in S))}–{fmt.format(max(m[(p, s)][key] for s in S))}"
    rr = lambda p, key, nd=2: pm([float(m[(p, s)]["run"][key]) for s in S], nd)
    pdr_k = {p: [st.mean(float(R[(p, k, s)]["pdr_nominal_pct"]) for s in S) for k in range(4)] for p in ("aodv", "olsr")}
    n30 = runs_of(B30)
    s30 = sorted({s for (_, _, s) in n30})
    a = [
        ("Nominal PDR (%), k = 0", rr("aodv", "pdr_nominal_pct"), rr("olsr", "pdr_nominal_pct")),
        ("Nominal PDR (%), means over k = 0–3", f"{min(pdr_k['aodv']):.2f}–{max(pdr_k['aodv']):.2f}",
         f"{min(pdr_k['olsr']):.2f}–{max(pdr_k['olsr']):.2f}"),
        ("Throughput (kbps)", rr("aodv", "sink_thr_kbps", 1), rr("olsr", "sink_thr_kbps", 1)),
        ("Gateway airtime", rr("aodv", "gw_airtime", 3), rr("olsr", "gw_airtime", 3)),
        ("Delay p50 (ms)", rr("aodv", "delay_p50_ms", 0), rr("olsr", "delay_p50_ms", 0)),
        ("Delay p95 (ms)", rr("aodv", "delay_p95_ms", 0), rr("olsr", "delay_p95_ms", 0)),
        ("Delay p99 (ms)", rr("aodv", "delay_p99_ms", 0), rr("olsr", "delay_p99_ms", 0)),
        ("Hops (delivered)", rr("aodv", "mean_hops_delivered", 2), rr("olsr", "mean_hops_delivered", 2)),
        ("Broadcast frames per run", rng("aodv", "broadcast"), rng("olsr", "broadcast")),
        ("Unicast data PSDUs per run", rng("aodv", "unicast"), rng("olsr", "unicast")),
        ("BlockAckRequest PSDUs per run", rng("aodv", "bar"), rng("olsr", "bar")),
        ("MPDUs expired (queue lifetime) per run", f"{min(int(m[('aodv', s)]['run']['mpdu_expired']) for s in S):,}–"
         f"{max(int(m[('aodv', s)]['run']['mpdu_expired']) for s in S):,}",
         f"{min(int(m[('olsr', s)]['run']['mpdu_expired']) for s in S):,}–{max(int(m[('olsr', s)]['run']['mpdu_expired']) for s in S):,}"),
        ("IP no-route drops per run", f"{min(int(m[('aodv', s)]['run']['no_route_drops']) for s in S)}–"
         f"{max(int(m[('aodv', s)]['run']['no_route_drops']) for s in S)}",
         f"{min(int(m[('olsr', s)]['run']['no_route_drops']) for s in S)}–{max(int(m[('olsr', s)]['run']['no_route_drops']) for s in S)}"),
        ("Path changes per source per minute", rng("aodv", "changes_per_src_min", "{:.1f}"), rng("olsr", "changes_per_src_min", "{:.1f}")),
        ("Packets on looping paths per run", rng("aodv", "loops"), rng("olsr", "loops")),
        ("Lost packets not forwarded by any relay (% of lost)", rng("aodv", "lost_at_src_pct", "{:.1f}"),
         rng("olsr", "lost_at_src_pct", "{:.1f}")),
        ("PDR of packets sent per 30 s window, min–max over windows and seeds (%)",
         f"{min(min(m[('aodv', s)]['win']) for s in S):.1f}–{max(max(m[('aodv', s)]['win']) for s in S):.1f}",
         f"{min(min(m[('olsr', s)]['win']) for s in S):.1f}–{max(max(m[('olsr', s)]['win']) for s in S):.1f}"),
        ("PDR of sources 1 hop from gateway (90 m graph, %)", rng("aodv", "pdr_hop1", "{:.1f}"), rng("olsr", "pdr_hop1", "{:.1f}")),
        ("PDR of sources ≥ 2 hops from gateway (90 m graph, %)", rng("aodv", "pdr_hop2p", "{:.1f}"), rng("olsr", "pdr_hop2p", "{:.1f}")),
        ("Reference: N = 30, 8 kbps, k = 0 nominal PDR (%), n = 10",
         pm([float(n30[("aodv", 0, s)]["pdr_nominal_pct"]) for s in s30]),
         pm([float(n30[("olsr", 0, s)]["pdr_nominal_pct"]) for s in s30])),
    ]
    write_csv("T-W6a_aodv_vs_olsr_n100", ["metric", "AODV", "OLSR"], a)
    J = {t: json.loads(use(DIAG / t / "runs/aodv_k0_rate8_seed20/aodv_log_counts.json").read_text()) for t in ("bafix0", "bafix1")}
    D = {t: rows(DIAG / t / "analysis/pilot_runs.csv")[0] for t in ("bafix0", "bafix1")}
    F = {t: frames(DIAG / t / "runs/aodv_k0_rate8_seed20") for t in J}
    orig = R[("aodv", 0, 20)]
    for key in ("sink_delivered", "gw_airtime", "mpdu_expired", "bar_psdus"):
        assert D["bafix1"][key] == orig[key], key   # logged fix-on rerun = original run

    def brk(t):
        v = J[t]["per_10s"]["SendRerrWhenBreaksLinkToNextHop"]
        pre = sum(v.get(str(x), 0) for x in (0, 10, 20))
        return pre, J[t]["totals"]["SendRerrWhenBreaksLinkToNextHop"] - pre
    ph = J["bafix1"]["phase_32ms"]["SendRequest"]
    b = []
    for lab, fn in [
        ("Nominal PDR (%)", lambda t: f"{float(D[t]['pdr_nominal_pct']):.2f}"),
        ("Gateway airtime", lambda t: f"{float(D[t]['gw_airtime']):.3f}"),
        ("Broadcast frames", lambda t: f"{F[t]['broadcast']:,}"),
        ("Unicast data PSDUs", lambda t: f"{F[t]['unicast']:,}"),
        ("BlockAckRequest PSDUs", lambda t: f"{int(D[t]['bar_psdus']):,}"),
        ("MPDUs expired", lambda t: f"{int(D[t]['mpdu_expired']):,}"),
        ("Packets > 10 s (max delay, s)", lambda t: f"{D[t]['gt10s']} ({float(D[t]['delay_max_s']):.1f})"),
        ("Block Ack fix events", lambda t: D[t]["ba_fix_events"]),
        ("AODV link-failure events", lambda t: f"{J[t]['totals']['SendRerrWhenBreaksLinkToNextHop']:,}"),
        ("— before traffic, 0–30 s (rate)", lambda t: f"{brk(t)[0]:,} ({brk(t)[0] / 30:.0f} s⁻¹)"),
        ("— during traffic, 30–300 s (rate)", lambda t: f"{brk(t)[1]:,} ({brk(t)[1] / 270:.0f} s⁻¹)"),
        ("RERR to active precursors", lambda t: f"{J[t]['totals']['rerr_broadcast'] + J[t]['totals']['rerr_unicast_one_precursor'] + J[t]['totals'].get('rerr_unicast', 0):,}"),
        ("RERR receptions", lambda t: f"{J[t]['totals']['RecvError']:,}"),
        ("RREQ originations (to gateway / other)", lambda t: f"{J[t]['totals']['SendRequest']:,} ({J[t]['rreq_by_dst']['gateway']:,} / {J[t]['rreq_by_dst']['other']:,})"),
        ("RREQ receptions (per origination)", lambda t: f"{J[t]['totals']['RecvRequest']:,} ({J[t]['totals']['RecvRequest'] / J[t]['totals']['SendRequest']:.0f})"),
        ("Gratuitous RREPs by intermediate nodes", lambda t: f"{J[t]['totals']['SendReplyByIntermediateNode']:,}"),
        ("Hellos sent", lambda t: f"{J[t]['totals']['SendHello']:,}"),
    ]:
        b.append((lab, fn("bafix0"), fn("bafix1")))
    b.append(("RREQ originations in first 32 ms of 512 ms CBR cycle (uniform 6.25 %)",
              f"{100 * J['bafix0']['phase_32ms']['SendRequest'].get('0', 0) / sum(J['bafix0']['phase_32ms']['SendRequest'].values()):.1f} %",
              f"{100 * ph.get('0', 0) / sum(ph.values()):.1f} %"))
    write_csv("T-W6b_aodv_diagnostic_seed20", ["quantity", "Block Ack fix off", "Block Ack fix on (original)"], b)
    c = [
        ("Confirmed", "AODV's deficit is present at k = 0 and nearly constant over k = 0–3 → not caused by the risk model", "T-W5a, T-W6a"),
        ("Confirmed", "Block Ack fix off: PDR 53.21 % vs 55.13 %, airtime and BARs unchanged → not caused by the Block Ack modification (seed 20 only)", "T-W6b"),
        ("Confirmed", "Same data traffic under OLSR: 99.6 % PDR, airtime 0.40; AODV at N = 30 is 99.99 % (8 kbps) and 99.76–99.95 % (64 kbps, 2.4× total load) → not data load alone", "T-W6a, T-W3"),
        ("Confirmed", "ns-3 AODV marks a neighbour broken on every dropped unicast MPDU regardless of drop reason (queue-lifetime expiry included)", "aodv-routing-protocol.cc:784-791; aodv-neighbor.cc:167-179"),
        ("Confirmed", "Control activity is driven by link failures (≈161k) and RERRs (≈118k, 1.24M receptions); RREQ originations are few (5.4k) but each flood is received ≈650 times (3.46M receptions), the largest control component by receptions", "T-W6b"),
        ("Confirmed", "Link failures 229 s⁻¹ before traffic, 572 s⁻¹ from the first 10 s of traffic, flat to 300 s", "T-W6b, F-W6"),
        ("Confirmed", "RREQ originations concentrate at synchronized send instants (39.9 % in first 32 ms)", "T-W6b, F-W6"),
        ("Hypothesis", "Self-reinforcing loop: contention → MPDU expiry → link failure → RERR + rediscovery → more airtime → more expiry", "not isolated experimentally"),
        ("Hypothesis", "Synchronized CBR and node density amplify the loop", "no desynchronization option; not tested"),
        ("Unknown", "Split of post-traffic link failures between MAC-drop and Hello-expiry causes; unicast vs broadcast share of expired MPDUs", "not logged separately"),
    ]
    write_csv("T-W6c_aodv_findings_status", ["status", "statement", "evidence"], c)
    MD.append("## T-W6 — AODV at N = 100 (secondary finding)\n"
              "**(a) AODV vs OLSR, N = 100, 8 kbps, k = 0, seeds 20–22** (mean ± SD [descriptive 95 % t] or range over "
              "seeds)\n\n" + md_table(["Metric", "AODV", "OLSR"], a)
              + "\n**(b) Diagnostic, seed 20 only** (`aodv-diag-n100-20261024T204129`; AODV event counts from the ns-3 "
              "log; the fix-on rerun is byte-identical to the original run)\n\n"
              + md_table(["Quantity", "Block Ack fix off", "Block Ack fix on (original)"], b)
              + "\n**(c) Status of each statement**\n\n" + md_table(["Status", "Statement", "Evidence"], c))
    return m


# ------------------------------------------------------------------ T-W7 limitations
def t_w7():
    # airtime ranges from the validated per-run tables (min-max over runs)
    r30, r100 = runs_of(B30).values(), runs_of(B100).values()
    rng = lambda xs: (min(xs), max(xs))
    air30 = rng([float(r["gw_airtime"]) for r in r30])
    air100 = rng([float(r["gw_airtime"]) for r in r100 if r["protocol"] != "aodv"])
    aodv100 = rng([float(r["gw_airtime"]) for r in r100 if r["protocol"] == "aodv"])
    L = [
        ("Risk-selection bias", "High-risk relays are the top-k of Static's BFS tree (subtree rule), where Static routes most traffic", "Static is the worst case; Risk-Aware vs Static is matched, but the gain over OLSR/AODV is not comparable to the gain over Static", "Design"),
        ("Oracle risk knowledge", "Risk-Aware knows every node's risk exactly; risk is static", "Risk-Aware results are an upper bound", "Design"),
        ("Different link models", "Static/Risk-Aware route on a 90 m disk graph; OLSR/AODV discover links over the real radio range", "OLSR/AODV use shorter paths (1.39–1.40 vs 1.52–1.61 hops at N = 100); N = 30 seed 28: one source isolated in the disk graph (527 packets lost by Static and Risk-Aware)", "Design"),
        ("Synchronized CBR", "All sensors send at the same instants every 512 ms (inherited V3 design)", "Absolute delays include synchronization; amplifies AODV contention (T-W6)", "Design"),
        ("Light load", f"8 kbps per sensor; per-run gateway airtime {air30[0]:.3f}–{air30[1]:.3f} (N = 30, all protocols) and "
         f"{air100[0]:.3f}–{air100[1]:.3f} (N = 100, Static / Risk-Aware / OLSR; AODV {aodv100[0]:.3f}–{aodv100[1]:.3f})",
         "No congestion trade-off of risk avoidance tested; saturated N = 100 experiment not performed", "Scope"),
        ("Seed counts", "N = 30: 10 seeds; N = 100: 3 seeds", "N = 100 is descriptive only; smallest exact Wilcoxon p = 0.00195 at n = 10", "Sample size"),
        ("Block Ack modification", "risk-v2 sends a BAR on ADDBA SSN mismatch; residual tail at saturation 13–37 per 100k delivered packets > 10 s", "Not reached in the main experiments (Static/RA 0 packets > 1 s; OLSR ≤ 36 > 1 s, 0 > 10 s at N = 100); max delay reported only with caveat", "Simulator"),
        ("Delay survivorship", "Delay and hops are over delivered packets; Static loses relayed packets at risky nodes", "Static's delay/hops look lower; at N = 100 Risk-Aware hops over all sent packets equal Static's (F-W4)", "Metric"),
        ("FlowMonitor undercount", "FlowMonitor rx < sink by ≤ 3 packets in main runs (≤ 45 at saturation)", "Sink-based PDR used throughout", "Metric"),
        ("Exposure definition", "Exposure = share of packets whose path crosses a high-risk node; drops are deterministic hashes", "Same packet gets the same risk decision under every protocol (fair matching), not a stochastic attack model", "Model"),
        ("AODV at N = 100", "Route-maintenance feedback suspected; causal chain not isolated; Block Ack check on one seed; Hello-expiry vs MAC-drop share unknown; AODV not tuned", "AODV at N = 100 is not a competitive baseline; compare Risk-Aware with Static and OLSR", "Protocol implementation"),
        ("MAC queue lifetime", "ns-3 default 500 ms, not varied", "Couples congestion to AODV link failure; sensitivity unknown", "Configuration"),
        ("Static topology", "No mobility; offline routes for Static/Risk-Aware", "Results do not cover route maintenance under mobility for Static/Risk-Aware", "Scope"),
    ]
    write_csv("T-W7_limitations", ["limitation", "description", "consequence", "category"], L)
    MD.append("## T-W7 — Consolidated limitations (Wi-Fi 6 risk study)\n\n"
              + md_table(["Limitation", "Description", "Consequence for conclusions", "Category"], L))


# ------------------------------------------------------------------ figures
def fig_vs_k(metric, ylabel, name, title):
    fig, axs = plt.subplots(1, 2, figsize=(7.2, 2.9), sharey=True)
    for ax, (b, n, tag) in zip(axs, ((B30, 10, "N = 30, seeds 20–29 (n = 10)"),
                                     (B100, 3, "N = 100, seeds 20–22 (n = 3, descriptive)"))):
        R = runs_of(b)
        seeds = sorted({s for (_, _, s) in R})
        for i, p in enumerate(PROTOS):
            x0 = [k + (i - 1.5) * 0.12 for k in range(4)]
            for k, x in zip(range(4), x0):
                v = [float(R[(p, k, s)][metric]) for s in seeds]
                ax.scatter([x] * len(v), v, s=6, color=COLOR[p], alpha=0.35, lw=0, zorder=2)
            ms = [ci([float(R[(p, k, s)][metric]) for s in seeds]) for k in range(4)]
            ax.errorbar(x0, [m[0] for m in ms], yerr=[[m[0] - m[2] for m in ms], [m[3] - m[0] for m in ms]],
                        color=COLOR[p], marker=MARK[p], ms=4, lw=1.1, capsize=2, label=LABEL[p], zorder=3)
        ax.set_title(tag)
        ax.set_xticks(range(4))
        ax.set_xlabel("High-risk relays k")
        ax.grid(axis="y", lw=0.4, alpha=0.5)
    axs[0].set_ylabel(ylabel)
    axs[0].legend(frameon=False, loc="best")
    save(fig, name)


def f_w3():
    fig, axs = plt.subplots(2, 2, figsize=(7.2, 5.0))
    for col, (b, tag) in enumerate(((B30, "N = 30 (n = 10 pairs)"), (B100, "N = 100 (n = 3 pairs, descriptive)"))):
        R = runs_of(b)
        seeds = sorted({s for (_, _, s) in R})
        for row, (m, lab) in enumerate((("pdr_nominal_pct", "Δ nominal PDR (pp)"), ("exposure_rate_pct", "Δ exposure (pp)"))):
            ax = axs[row][col]
            for k in (1, 2, 3):
                d = [float(R[("riskaware", k, s)][m]) - float(R[("static", k, s)][m]) for s in seeds]
                mm, sd, lo, hi = ci(d)
                jit = [k - 0.15 + 0.3 * i / max(1, len(d) - 1) for i in range(len(d))]
                ax.scatter(jit, d, s=10, color="0.45", lw=0, zorder=2)
                ax.errorbar([k + 0.25], [mm], yerr=[[mm - lo], [hi - mm]], color="#DD8452", marker="D", ms=5,
                            capsize=3, lw=1.3, zorder=3)
            ax.axhline(0, color="k", lw=0.6)
            ax.set_xticks((1, 2, 3))
            ax.set_xlim(0.5, 3.6)
            ax.set_ylabel(lab)
            ax.grid(axis="y", lw=0.4, alpha=0.5)
            if row == 0:
                ax.set_title(tag)
            else:
                ax.set_xlabel("High-risk relays k")
    save(fig, "F-W3_paired_differences")


def all_sent_hops(b, p, k, s):
    pp = rows(run_dir(b, runs_of(b)[(p, k, s)]["run"]) / "packet_paths.csv")
    return st.mean(int(x["relay_hops"]) for x in pp) + 1   # links = relays + 1


def f_w4():
    fig, axs = plt.subplots(2, 3, figsize=(7.4, 5.0))
    hopcheck = []
    for row, b in enumerate((B30, B100)):
        R = runs_of(b)
        seeds = sorted({s for (_, _, s) in R})
        nlab = f"N = {30 if b == B30 else 100} (n = {len(seeds)})"
        for col, (m, lab) in enumerate((("delay_p50_ms", "Delay p50 (ms)"), ("delay_p95_ms", "Delay p95 (ms)"))):
            ax = axs[row][col]
            for i, p in enumerate(("static", "riskaware")):
                ms = [ci([float(R[(p, k, s)][m]) for s in seeds]) for k in range(4)]
                x = [k + (i - 0.5) * 0.15 for k in range(4)]
                ax.errorbar(x, [q[0] for q in ms], yerr=[[q[0] - q[2] for q in ms], [q[3] - q[0] for q in ms]],
                            color=COLOR[p], marker=MARK[p], ms=4, capsize=2, lw=1.1, label=LABEL[p])
            if row == 0:
                ax.set_title(lab)
            if col == 0:
                ax.set_ylabel(f"{nlab}\n{lab}")
            ax.set_xticks(range(4))
            ax.grid(axis="y", lw=0.4, alpha=0.5)
        ax = axs[row][2]
        for i, p in enumerate(("static", "riskaware")):
            dl = [st.mean(float(R[(p, k, s)]["mean_hops_delivered"]) for s in seeds) for k in range(4)]
            al = [st.mean(all_sent_hops(b, p, k, s) for s in seeds) for k in range(4)]
            hopcheck.append((nlab, p, dl, al))
            ax.plot(range(4), dl, color=COLOR[p], marker=MARK[p], ms=4, lw=1.1, label=f"{LABEL[p]}, delivered")
            ax.plot(range(4), al, color=COLOR[p], marker=MARK[p], ms=4, lw=1.1, ls="--", mfc="white",
                    label=f"{LABEL[p]}, all sent")
        if row == 0:
            ax.set_title("Mean hops (links)")
        ax.set_xticks(range(4))
        ax.grid(axis="y", lw=0.4, alpha=0.5)
    for ax in axs[1]:
        ax.set_xlabel("High-risk relays k")
    axs[0][0].legend(frameon=False, fontsize=7.5)
    axs[0][2].legend(frameon=False, fontsize=6.5)
    save(fig, "F-W4_cost_delay_hops")
    return hopcheck


def f_w5(m):
    fig, ax = plt.subplots(figsize=(5.2, 2.8))
    for p in ("olsr", "aodv"):
        for j, s in enumerate((20, 21, 22)):
            w = m[(p, s)]["win"]
            ax.plot([30 + 30 * i + 15 for i in range(len(w))], w, color=COLOR[p], marker=MARK[p], ms=3, lw=1,
                    alpha=0.9, ls=("-", "--", ":")[j], label=f"{LABEL[p]} seed {s}")
    ax.set_xlabel("Send time (s), 30 s windows")
    ax.set_ylabel("PDR of packets sent in window (%)")
    ax.set_ylim(0, 102)
    ax.set_xlim(30, 300)
    ax.grid(lw=0.4, alpha=0.5)
    ax.legend(frameon=False, ncol=3, fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.22))
    ax.set_title("N = 100, 8 kbps, k = 0: delivery over time (seeds 20–22)")
    save(fig, "F-W5_aodv_olsr_pdr_time")


def f_w6():
    J = {t: json.loads((DIAG / t / "runs/aodv_k0_rate8_seed20/aodv_log_counts.json").read_text()) for t in ("bafix0", "bafix1")}
    fig, axs = plt.subplots(1, 2, figsize=(7.4, 2.8), gridspec_kw={"width_ratios": [1.5, 1]})
    ax = axs[0]
    for t, lab, ls in (("bafix1", "Block Ack fix on (original)", "-"), ("bafix0", "Block Ack fix off", "--")):
        v = J[t]["per_10s"]["SendRerrWhenBreaksLinkToNextHop"]
        ax.step([int(x) for x in range(0, 300, 10)], [v.get(str(x), 0) / 10 for x in range(0, 300, 10)], where="post",
                color="#C44E52" if t == "bafix1" else "0.3", ls=ls, lw=1.2, label=lab)
    ax.axvline(30, color="k", lw=0.7, ls=":")
    ax.text(31, ax.get_ylim()[1] * 0.08, "traffic starts (30 s)", fontsize=7.5)
    ax.set_xlabel("Simulation time (s)")
    ax.set_ylabel("AODV link failures (s⁻¹, 10 s bins)")
    ax.set_xlim(0, 300)
    ax.set_ylim(bottom=0)
    ax.legend(frameon=False, fontsize=7.5, loc="lower right")
    ax.set_title("Link-failure events, seed 20")
    ax = axs[1]
    ph = J["bafix1"]["phase_32ms"]
    for key, lab, c in (("SendRequest", "RREQ originations", "#C44E52"), ("SendRerrWhenBreaksLinkToNextHop", "Link failures", "0.4")):
        v = ph[key]
        tot = sum(v.values())
        ax.plot([32 * i + 16 for i in range(16)], [100 * v.get(str(i), 0) / tot for i in range(16)], marker="o", ms=3,
                lw=1.1, color=c, label=lab)
    ax.axhline(6.25, color="k", lw=0.7, ls=":", label="uniform (6.25 %)")
    ax.set_xlabel("Phase within 512 ms CBR cycle (ms)")
    ax.set_ylabel("Share of events (%)")
    ax.set_xlim(0, 512)
    ax.legend(frameon=False, fontsize=7.5)
    ax.set_title("Phase relative to synchronized sends, fix on")
    save(fig, "F-W6_aodv_link_failures_phase")


def f_w7(m):
    keys = (("broadcast", "Broadcast data"), ("unicast", "Unicast data"), ("ack", "ACK"), ("bar", "BlockAckReq"),
            ("ba", "BlockAck"), ("mgmt", "Mgmt action"))
    fig, ax = plt.subplots(figsize=(6.0, 2.8))
    for i, p in enumerate(("olsr", "aodv")):
        vals = [[m[(p, s)][k] for s in (20, 21, 22)] for k, _ in keys]
        x = [j + (i - 0.5) * 0.36 for j in range(len(keys))]
        ax.bar(x, [st.mean(v) for v in vals], width=0.34, color=COLOR[p], label=LABEL[p], alpha=0.85)
        for xx, v in zip(x, vals):
            ax.scatter([xx] * 3, v, s=7, color="k", zorder=3, lw=0)
    ax.set_yscale("log")
    ax.set_xticks(range(len(keys)))
    ax.set_xticklabels([lab for _, lab in keys])
    ax.set_ylabel("Transmitted PSDUs per run (log)")
    ax.legend(frameon=False)
    ax.grid(axis="y", lw=0.4, alpha=0.5, which="both")
    ax.set_title("N = 100, 8 kbps, k = 0: frames by type (bars = mean, dots = seeds 20–22)")
    save(fig, "F-W7_frame_composition")


def f_w8():
    R = runs_of(B100)
    fig, ax = plt.subplots(figsize=(5.0, 2.9))
    for p in PROTOS:
        d = []
        for s in (20, 21, 22):
            d += [1000 * float(x["delay_s"]) for x in rows(B100 / "runs" / R[(p, 0, s)]["run"] / "packet_paths.csv")
                  if x["fate"] == "delivered"]
        d.sort()
        n = len(d)
        step = max(1, n // 4000)
        xs = d[::step] + [d[-1]]
        ys = [100 * (i * step + 1) / n for i in range(len(xs) - 1)] + [100.0]
        ax.plot(xs, ys, color=COLOR[p], lw=1.3, label=f"{LABEL[p]} ({n:,} pkts)")
    ax.set_xscale("log")
    ax.set_xlabel("End-to-end delay of delivered packets (ms, log)")
    ax.set_ylabel("Cumulative share (%)")
    ax.grid(lw=0.4, alpha=0.5, which="both")
    ax.legend(frameon=False, fontsize=7.5)
    ax.set_title("N = 100, 8 kbps, k = 0, seeds 20–22 pooled")
    save(fig, "F-W8_delay_cdf_n100")


CAPTIONS = [
    ("F-W1_pdr_vs_k", "Nominal PDR versus the number of high-risk relays k (8 kbps per sensor). Left: N = 30, seeds "
     "20–29 (n = 10); right: N = 100, seeds 20–22 (n = 3). Markers: mean; error bars: Student-t 95 % interval of the "
     "mean (descriptive only for N = 100); faint dots: individual seeds. Nominal PDR = delivered / scheduled packets. "
     "The N = 30 Static/Risk-Aware k = 0 seed at 96.7 % is seed 28 (one source isolated in the 90 m disk graph). AODV "
     "at N = 100 is affected by the route-maintenance behaviour of F-W5–F-W7 at every k.",
     "seeds10-n30-8k-v2, n100-8k-v2 analysis/pilot_runs.csv"),
    ("F-W2_exposure_vs_k", "Exposure rate (share of sent packets whose path crossed at least one high-risk relay) "
     "versus k; layout and intervals as F-W1. High-risk relays are selected from Static's BFS tree (subtree rule), "
     "which maximises Static's exposure by design. Risk-Aware exposure is 0 except N = 30 seed 21 (source 11 has no "
     "safe path: 3.33 % in that seed at k = 2–3, mean over 10 seeds 0.33 %).", "as F-W1"),
    ("F-W3_paired_differences", "Paired Risk-Aware − Static differences on the same seed (same positions, traffic and "
     "high-risk set) for nominal PDR (top) and exposure (bottom). Grey: individual seeds; orange: mean with Student-t "
     "95 % interval. N = 30 (n = 10): all 10 pairs favour Risk-Aware at every k = 1–3; exact Wilcoxon p = 0.00195, "
     "Holm-adjusted 0.0117 over the six primary tests. N = 100 (n = 3): descriptive only, no test.",
     "paired_riskaware_vs_static.csv (both batches)"),
    ("F-W4_cost_delay_hops", "Cost of risk avoidance. Columns: delay p50 and p95 over delivered packets (mean ± "
     "Student-t 95 % interval of per-run percentiles) and mean path length in links (seed means). Solid: delivered "
     "packets; dashed, open markers: all sent packets (path planned/traversed). Static's falling delay and hops with k "
     "are survivorship: packets routed through risky relays are lost. At N = 100 Risk-Aware's all-sent path length "
     "equals Static's (1.613 links at every k, curves overlap), so its delay is unchanged from k = 0. At N = 30 "
     "Risk-Aware does lengthen paths (1.64 → 1.75 links at k = 3), and its p95 delay rises by about 2 ms over k = 0.",
     "pilot_runs.csv; runs/*/packet_paths.csv"),
    ("F-W5_aodv_olsr_pdr_time", "AODV and OLSR at N = 100, 8 kbps, k = 0: PDR of packets sent in each 30 s window, "
     "seeds 20–22. AODV delivers 39.7–65.8 % in every window, from the first window onward; OLSR delivers "
     "98.9–100 %.", "n100-8k-v2 runs/{aodv,olsr}_k0_*/packet_paths.csv"),
    ("F-W6_aodv_link_failures_phase", "AODV diagnostic, N = 100, 8 kbps, k = 0, seed 20 only. Left: AODV link-failure "
     "events (SendRerrWhenBreaksLinkToNextHop) per second in 10 s bins, with the Block Ack modification on (original "
     "run, byte-identical rerun) and off. Failures already occur before traffic (Hello expiry) and rise about 2.5× "
     "within 10 s of traffic start, then stay flat; the fix makes no visible difference. Right: phase of RREQ "
     "originations and link failures within the 512 ms synchronized CBR cycle (fix on); 39.9 % of RREQ originations "
     "fall in the first 32 ms. Counts are observations; the feedback loop that may link them is a hypothesis "
     "(T-W6c).", "aodv-diag-n100-20261024T204129/*/runs/*/aodv_log_counts.json"),
    ("F-W7_frame_composition", "Transmitted PSDUs by frame type at N = 100, 8 kbps, k = 0 (log scale; bars: mean of "
     "seeds 20–22; dots: seeds). AODV sends 9.9–11.4× OLSR's broadcast frames, 2.8–3.2× its unicast data PSDUs and "
     "129–164× its BlockAckRequests. Broadcast includes routing control (AODV RREQ/RERR/Hello; OLSR HELLO/TC).",
     "n100-8k-v2 runs/*/wifi_txvector_counts.csv"),
    ("F-W8_delay_cdf_n100", "Cumulative distribution of end-to-end delay of delivered packets, N = 100, 8 kbps, k = 0, "
     "seeds 20–22 pooled (packet counts in legend). Static and Risk-Aware coincide at k = 0. Delivered packets only: "
     "AODV's curve excludes its 43 % lost packets. The knee in AODV's curve near 500 ms coincides with the MAC queue "
     "lifetime (500 ms); this is an observation, not a tested cause.", "n100-8k-v2 runs/*_k0_*/packet_paths.csv"),
]


def write_captions():
    s = "# Wi-Fi 6 risk study — figure captions\n\nPDF (vector) and PNG (300 dpi) in `figures/`. Generated by " \
        "`experiments/wifi6-risk/make_report_outputs.py`.\n\n"
    for name, text, src in CAPTIONS:
        assert (FIG / f"{name}.pdf").exists(), name
        s += f"## {name}\n{text}\n\n*Source:* {src}\n\n"
    (OUT / "FIGURES.md").write_text(s)


def main():
    TAB.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)
    t_w1()
    t_w2()
    t_w3()
    t_w4_5()
    m = t_w6()
    t_w7()
    fig_vs_k("pdr_nominal_pct", "Nominal PDR (%)", "F-W1_pdr_vs_k", "Nominal PDR vs number of high-risk relays (8 kbps)")
    fig_vs_k("exposure_rate_pct", "Exposure rate (% of packets)", "F-W2_exposure_vs_k",
             "Share of packets routed through a high-risk relay (8 kbps)")
    f_w3()
    hop = f_w4()
    f_w5(m)
    f_w6()
    f_w7(m)
    f_w8()
    write_captions()
    (OUT / "TABLES.md").write_text("# Wi-Fi 6 risk study — report tables\n\nGenerated by "
                                   "`experiments/wifi6-risk/make_report_outputs.py` from validated results only. "
                                   "Mean ± SD [Student-t 95 % interval]; n stated per table.\n\n" + "\n".join(MD))
    inv = dict(inputs={str(p.relative_to(ROOT)): h for p, h in sorted(USED.items())},
               outputs=sorted(str(p.relative_to(ROOT)) for p in list(TAB.iterdir()) + list(FIG.iterdir())),
               hop_check=[dict(n=a, protocol=b, delivered=c, all_sent=d) for a, b, c, d in hop], issues=ISSUES)
    (OUT / "inventory.json").write_text(json.dumps(inv, indent=1))
    print(f"tables: {len(list(TAB.iterdir()))} files; figures: {len(list(FIG.iterdir()))} files; inputs: {len(USED)}")
    for a, b, c, d in hop:
        print(a, b, "delivered", [round(x, 3) for x in c], "all sent", [round(x, 3) for x in d])
    for i in ISSUES:
        print("ISSUE:", i)


if __name__ == "__main__":
    main()
