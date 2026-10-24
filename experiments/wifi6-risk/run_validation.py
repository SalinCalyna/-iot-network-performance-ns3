#!/usr/bin/env python3
"""Small deterministic validation of scratch/iot-network-wifi6-risk.cc (risk-v1). Runs nothing large.

    python3 -I -B experiments/wifi6-risk/run_validation.py [--jobs=6]
    python3 -I -B experiments/wifi6-risk/run_validation.py --version=v2 --compareTo=<v1 validation dir>
      risk-v2: regression/passivity runs use --baSsnFix=0; risk scenarios use the fix (default on) and get T10.
    python3 -I -B experiments/wifi6-risk/run_validation.py --version=v3 --compareTo=<v2 validation dir>
      risk-v3: regression/passivity runs use --baSsnFix=0 --baReestFix=0; risk scenarios use both fixes and get
      T10 and T11; S_ax_<proto>_k2_reest0 (--baReestFix=0) must equal the v2 run byte for byte.
    python3 -I -B experiments/wifi6-risk/run_validation.py --version=v4 --compareTo=<v3 validation dir>
      risk-v4 (experimental): regression/passivity runs use all three Block Ack fixes off; risk scenarios use
      --baAddbaBar (default on) and get T10 and T12; S_ax_<proto>_k2_addba0 (--baAddbaBar=0) must equal v3.

Output: results/wifi6-risk/validation-<timestamp>/ (new directory; nothing existing is overwritten):
  runs/<id>/ (simulator outputs + provenance.json), checks.csv, SUMMARY.txt. Exit 0 only if every check passes.

Groups
  R  regression: the parent binary (iot-network-wifi-std-arp) and the new binary with --riskStudy=0 re-run 4
     stored runs; all original outputs must be byte-identical to the stored files (timestamp column excepted).
     This also checks that the rebuilt ns-3 libraries reproduce the stored results.
  P  passivity: the same 4 runs with --riskStudy=1 --numHighRisk=0: original outputs still byte-identical.
  S  risk scenarios (802.11ax Tier A, ARP pre-populated, N=30, seed 20, 16 kbps, 100 s, --perPacketTrace=1):
     static / riskaware / olsr / aodv x numHighRisk 0..3; a repeat run; one run with LOW_RISK p=0.1;
     802.11b static and riskaware with 3 high-risk nodes.
Checks T1-T9 are listed in experiments/wifi6-risk/README.md.
"""
import csv
import hashlib
import importlib.util
import json
import math
import os
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("risk_ref", HERE / "risk_ref.py")
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)

NEW_BIN = ROOT / "build/scratch/ns3-dev-iot-network-wifi6-risk-default"
ARP_BIN = ROOT / "build/scratch/ns3-dev-iot-network-wifi-std-arp-default"
NEW_SRC = ROOT / "scratch/iot-network-wifi6-risk.cc"
STORED = {   # stored run directory -> its argv (from provenance.json, minus --outDir)
    "b_static_30": ROOT / "results/wifi-std/arp-regression/b_static_30_high_seed20",
    "b_aodv_30": ROOT / "results/wifi-std/arp-regression/b_aodv_30_high_seed20",
    "bon_olsr_50": ROOT / "results/wifi-std/arp-b-on-os/b-on_olsr_50_rate16_seed20",
    "axon_static_50": ROOT / "results/wifi-std/arp-smoke-ax-on/ax-on_static_50_rate16_seed20",
}
S_BASE = ["--nSensors=30", "--trafficLevel=high", "--offeredRateKbps=16", "--seed=20", "--arpPrepopulate=1",
          "--simTime=100", "--riskStudy=1", "--perPacketTrace=1"]
P_HIGH, BETA, N_S = 0.5, 10.0, 30


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def rows(p):
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


# ------------------------------------------------------------------ std::mt19937 + libc++ uniform_real
class MT19937:
    def __init__(self, seed):
        self.mt = [0] * 624
        self.i = 624
        self.mt[0] = seed & 0xFFFFFFFF
        for k in range(1, 624):
            self.mt[k] = (1812433253 * (self.mt[k - 1] ^ (self.mt[k - 1] >> 30)) + k) & 0xFFFFFFFF

    def __call__(self):
        if self.i >= 624:
            for k in range(624):
                y = (self.mt[k] & 0x80000000) | (self.mt[(k + 1) % 624] & 0x7FFFFFFF)
                self.mt[k] = self.mt[(k + 397) % 624] ^ (y >> 1) ^ (0x9908B0DF if y & 1 else 0)
            self.i = 0
        y = self.mt[self.i]
        self.i += 1
        y ^= y >> 11
        y ^= (y << 7) & 0x9D2C5680
        y ^= (y << 15) & 0xEFC60000
        return y ^ (y >> 18)


def positions(seed, n, area=250.0):
    """Sensor positions as scratch/iot-network-wifi-std-arp.cc:326-330 draws them (x then y), gateway last."""
    g = MT19937(seed)

    def coord():
        s = float(g())
        s += float(g()) * 4294967296.0
        return area * (s / 18446744073709551616.0)
    out = []
    for _ in range(n):
        x = coord()
        y = coord()
        out.append((x, y))
    return out + [(area / 2.0, area / 2.0)]


# ------------------------------------------------------------------ running
def run(binary, args, outdir, timeout=7200):
    outdir.mkdir(parents=True, exist_ok=False)
    argv = [str(binary)] + args + [f"--outDir={outdir.relative_to(ROOT)}"]
    t0 = time.time()
    with open(outdir / "stdout.log", "x") as so, open(outdir / "stderr.log", "x") as se:
        rc = subprocess.run(argv, cwd=ROOT, stdout=so, stderr=se, timeout=timeout).returncode
    prov = dict(argv=argv, exit_code=rc, wall_sec=round(time.time() - t0, 1),
                stderr_bytes=(outdir / "stderr.log").stat().st_size, binary_sha256=sha(binary))
    (outdir / "provenance.json").write_text(json.dumps(prov, indent=1))
    return prov


class Checks:
    def __init__(self):
        self.rows = []

    def add(self, test, subject, ok, detail=""):
        self.rows.append(dict(test=test, subject=subject, passed=int(bool(ok)), detail=str(detail)[:400]))


def original_files(d):
    fs = ["probe_aggregate.csv", "wifistd_ext.csv", "stdout.log"]
    fs += [str(p.relative_to(d)) for p in sorted((d / "pernode").glob("*.csv"))]
    fs += [str(p.relative_to(d)) for p in sorted((d / "pernode_ext").glob("*.csv"))]
    return fs


def same_outputs(ref, new):
    bad = []
    for f in original_files(ref):
        a, b = ref / f, new / f
        if not b.exists():
            bad.append(f"{f} missing")
            continue
        if f == "probe_aggregate.csv":
            strip = lambda p: [line.split(",", 1)[1] for line in p.read_text().splitlines()]
            if strip(a) != strip(b):
                bad.append(f)
        elif a.read_bytes() != b.read_bytes():
            bad.append(f)
    return bad


def main():
    opts = dict(a.split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
    jobs = int(opts.get("--jobs", 6))
    global NEW_BIN, NEW_SRC
    version = opts.get("--version", "v1")
    reg_extra = []
    if version == "v2":
        NEW_BIN = ROOT / "build/scratch/ns3-dev-iot-network-wifi6-risk-v2-default"
        NEW_SRC = ROOT / "scratch/iot-network-wifi6-risk-v2.cc"
        reg_extra = ["--baSsnFix=0"]
    if version == "v3":
        NEW_BIN = ROOT / "build/scratch/ns3-dev-iot-network-wifi6-risk-v3-default"
        NEW_SRC = ROOT / "scratch/iot-network-wifi6-risk-v3.cc"
        reg_extra = ["--baSsnFix=0", "--baReestFix=0"]
    if version == "v4":
        NEW_BIN = ROOT / "build/scratch/ns3-dev-iot-network-wifi6-risk-v4-default"
        NEW_SRC = ROOT / "scratch/iot-network-wifi6-risk-v4.cc"
        reg_extra = ["--baSsnFix=0", "--baReestFix=0", "--baAddbaBar=0"]
    compare_to = Path(opts["--compareTo"]) if "--compareTo" in opts else None
    free = shutil.disk_usage(ROOT).free
    if free < 2 * 1024 ** 3:
        sys.exit(f"STOP: only {free / 1024 ** 2:.0f} MB free; need >= 2 GB")
    for b in (NEW_BIN, ARP_BIN):
        if not b.exists():
            sys.exit(f"STOP: binary missing: {b}")
    out = ROOT / "results/wifi6-risk" / time.strftime(f"validation-{version}-%Y%m%dT%H%M%S")
    out.mkdir(parents=True, exist_ok=False)
    C = Checks()
    (out / "provenance.json").write_text(json.dumps(dict(
        version=version, compare_to=str(compare_to), new_source=str(NEW_SRC), new_source_sha256=sha(NEW_SRC), new_binary_sha256=sha(NEW_BIN), arp_binary_sha256=sha(ARP_BIN),
        started=time.strftime("%Y-%m-%dT%H:%M:%S%z")), indent=1))

    jobsl = []
    for name, ref in STORED.items():
        args = [a for a in json.loads((ref / "provenance.json").read_text())["argv"][1:] if not a.startswith("--outDir")]
        jobsl += [(f"R_arp_{name}", ARP_BIN, args), (f"R_new_{name}", NEW_BIN, args + ["--riskStudy=0"] + reg_extra),
                  (f"P_new_{name}", NEW_BIN, args + ["--riskStudy=1", "--numHighRisk=0"] + reg_extra)]
    S = {}
    for proto in ("static", "riskaware", "olsr", "aodv"):
        for k in range(4):
            S[f"S_ax_{proto}_k{k}"] = ["--standard=80211ax", f"--protocol={proto}", f"--numHighRisk={k}"] + S_BASE
    S["S_ax_riskaware_k3_repeat"] = S["S_ax_riskaware_k3"]
    S["S_ax_riskaware_k1_low0.1"] = ["--standard=80211ax", "--protocol=riskaware", "--numHighRisk=1",
                                     "--lowRiskDropProb=0.1"] + S_BASE
    for proto in ("static", "riskaware", "olsr", "aodv"):   # FlowMonitor twins: only MaxPerHopDelay differs
        for k in range(4):
            S[f"F_ax_{proto}_k{k}"] = S[f"S_ax_{proto}_k{k}"] + ["--ns3::FlowMonitor::MaxPerHopDelay=1000s"]
    for proto in ("static", "riskaware"):
        S[f"S_b_{proto}_k3"] = ["--standard=80211b", f"--protocol={proto}", "--numHighRisk=3"] + S_BASE
    REEST0 = {}
    if version == "v3":   # --baReestFix=0 twins: must equal the risk-v2 validation runs
        for proto in ("olsr", "aodv"):
            REEST0[f"S_ax_{proto}_k2_reest0"] = (f"S_ax_{proto}_k2", S[f"S_ax_{proto}_k2"] + ["--baReestFix=0"])
    jobsl += [(k, NEW_BIN, v) for k, v in S.items()]
    if version == "v4":   # --baAddbaBar=0 twins: must equal the risk-v3 validation runs
        for proto in ("olsr", "aodv"):
            REEST0[f"S_ax_{proto}_k2_addba0"] = (f"S_ax_{proto}_k2", S[f"S_ax_{proto}_k2"] + ["--baAddbaBar=0"])
    jobsl += [(k, NEW_BIN, v[1]) for k, v in REEST0.items()]

    with ThreadPoolExecutor(max_workers=jobs) as ex:
        provs = dict(zip([j[0] for j in jobsl], ex.map(lambda j: run(j[1], j[2], out / "runs" / j[0]), jobsl)))
    for k, p in provs.items():
        C.add("T0 run", k, p["exit_code"] == 0 and p["stderr_bytes"] == 0,
              f"exit {p['exit_code']} stderr {p['stderr_bytes']} B wall {p['wall_sec']} s")

    # T1 regression / T2 passivity
    for name, ref in STORED.items():
        for tag, test in (("R_arp", "T1 regression (parent binary, rebuilt libs)"), ("R_new", "T1 regression (riskStudy=0)"),
                          ("P_new", "T2 passivity (riskStudy=1, 0 high-risk)")):
            d = out / "runs" / f"{tag}_{name}"
            bad = same_outputs(ref, d)
            C.add(test, f"{tag}_{name}", not bad, bad or "all original outputs identical")
        extra = [p.name for p in (out / "runs" / f"R_new_{name}").iterdir()
                 if p.name in ("risk_summary.csv", "risk_nodes.csv", "routes_planned.csv")]
        C.add("T1 no new outputs with riskStudy=0", name, not extra, extra)

    pos = positions(20, N_S)
    pn = rows(next((out / "runs" / "S_ax_static_k0" / "pernode").glob("*.csv")))
    dmax = max(max(abs(float(r["x"]) - pos[int(r["node_id"])][0]), abs(float(r["y"]) - pos[int(r["node_id"])][1]))
               for r in pn)
    C.add("T8 reference positions reproduce simulator", "seed 20 N 30", dmax < 1e-3, f"max |diff| {dmax:.2e} m")

    ids_by_k = {}
    for name in S:
        d = out / "runs" / name
        if provs[name]["exit_code"] != 0:
            continue
        args = S[name]
        k = int(next(a for a in args if a.startswith("--numHighRisk=")).split("=")[1])
        proto = next(a for a in args if a.startswith("--protocol=")).split("=")[1]
        p_low = float(next((a.split("=")[1] for a in args if a.startswith("--lowRiskDropProb=")), 0.0))
        m = R.model(pos, N_S, k=k, p_high=P_HIGH, p_low=p_low, beta=BETA)
        gw = m["gw"]
        rn = {int(r["node_id"]): r for r in rows(d / "risk_nodes.csv")}
        rs = rows(d / "risk_summary.csv")[0]
        rp = {int(r["src"]): r for r in rows(d / "routes_planned.csv")}
        # T3 assignment
        sim_high = sorted(i for i, r in rn.items() if r["risk_state"] == "HIGH_RISK")
        C.add("T3 high-risk ids match reference", name, sim_high == sorted(m["high"]), (sim_high, sorted(m["high"])))
        C.add("T3 count", name, len(sim_high) == k, len(sim_high))
        C.add("T3 gateway never risky", name, rn[gw]["risk_state"] == "LOW_RISK" and float(rn[gw]["risk_score"]) == 0)
        C.add("T3 hop/degree/descendants match reference", name,
              all(int(rn[i]["hop_to_gw"]) == m["hop"][i] and int(rn[i]["degree"]) == m["degree"][i]
                  and int(rn[i]["bfs_descendants"]) == m["desc"][i] for i in range(gw + 1)))
        C.add("T3 risk scores", name, all(abs(float(rn[i]["risk_score"]) - m["p"][i]) < 1e-15 for i in range(gw + 1)))
        ids_by_k.setdefault(k, set()).add(tuple(sim_high))
        # T4 path selection / T5 connectivity
        tree = m["parent"] if proto != "riskaware" else m["ra_parent"]
        for s in range(N_S):
            r = rp[s]
            pb = R.path_of(m["parent"], s, gw)
            pr = R.path_of(m["ra_parent"], s, gw)
            fmt = lambda p: ">".join(map(str, [s] + p)) if p else "NA"
            ok = r["bfs_path"] == fmt(pb) and r["riskaware_path"] == fmt(pr)
            if pr:
                ok &= abs(float(r["riskaware_risk_cost"]) - m["ra_dist"][s]) < 1e-9
                ok &= abs(float(r["bfs_risk_cost"]) - R.path_cost(pb, m["tau"], BETA, gw)) < 1e-9
            C.add("T4 planned paths and costs match reference", f"{name} src {s}", ok,
                  (r["bfs_path"], fmt(pb), r["riskaware_path"], fmt(pr)))
            C.add("T5 reachability matches BFS", f"{name} src {s}", int(r["reachable"]) == int(m["hop"][s] >= 1))
            C.add("T4 safe path flag", f"{name} src {s}", int(r["safe_path_exists"]) == int(m["safe"][s]))
            if proto in ("static", "riskaware") and m["hop"][s] >= 1:
                C.add("T5 installed path = protocol tree", f"{name} src {s}", r["installed_path"] == fmt(R.path_of(tree, s, gw)))
        if proto == "riskaware" and k == 0 and p_low == 0:
            C.add("T4 riskaware k=0 tree == static BFS tree", name, all(m["ra_parent"][s] == m["parent"][s] for s in range(N_S)))
        # T6 risk drops
        drops = rows(d / "risk_drops.csv")
        bad = [x for x in drops if m["p"][int(x["node_id"])] <= 0
               or abs(R.risk_uniform(1, int(x["node_id"]), int(x["src"]), int(x["seq"])) - float(x["u"])) > 0
               or not float(x["u"]) < m["p"][int(x["node_id"])]]
        C.add("T6 every drop at a p>0 node and reproduced by the reference hash", name, not bad, bad[:3])
        C.add("T6 no drop of a node's own packet", name, all(int(x["node_id"]) != int(x["src"]) for x in drops))
        C.add("T6 key_missing = 0", name, rs["key_missing"] == "0", rs["key_missing"])
        # a node's own packets reach RouteInput only through AODV's loopback deferral; they are never dropped
        C.add("T6 own-source packets seen by the filter only under AODV (loopback)", name,
              proto == "aodv" or rs["eligible_local_source"] == "0", rs["eligible_local_source"])
        for i, r in rn.items():
            e, dr = int(r["eligible_transit_pkts"]), int(r["risk_dropped"])
            if m["p"][i] > 0 and e >= 30:
                lo, hi = R.wilson(dr, e)
                C.add("T6 empirical drop rate in 99.9% Wilson interval", f"{name} node {i}", lo <= m["p"][i] <= hi,
                      f"{dr}/{e} p={m['p'][i]}")
            if m["p"][i] == 0:
                C.add("T6 no drops where p=0", f"{name} node {i}", dr == 0 and e == 0, (dr, e))
        C.add("T6 drop log = per-node counters", name, len(drops) == sum(int(r["risk_dropped"]) for r in rn.values()))
        # T7 metric consistency
        ext = rows(d / "wifistd_ext.csv")[0]
        agg = rows(d / "probe_aggregate.csv")[0]
        pp = rows(d / "packet_paths.csv")
        summ = rows(d / "path_summary.csv")
        C.add("T7 path records = app tx", name, int(rs["path_records"]) == int(ext["app_tx_pkts"]) == len(pp),
              (rs["path_records"], ext["app_tx_pkts"], len(pp)))
        C.add("T7 delivered + duplicates = sink rx", name,
              int(rs["delivered_unique"]) + int(rs["duplicates"]) == int(rs["sink_rx_counter"]) == int(ext["app_rx_pkts"]))
        fm1000 = "--ns3::FlowMonitor::MaxPerHopDelay=1000s" in args
        if fm1000:
            C.add("T7 FlowMonitor rx = unique sink deliveries (MaxPerHopDelay 1000 s)", name,
                  rs["delivered_unique"] == agg["rxPkts"], (rs["delivered_unique"], agg["rxPkts"]))
        else:
            C.add("T7 FlowMonitor rx <= unique sink deliveries (default 10 s per-hop loss timer)", name,
                  int(agg["rxPkts"]) <= int(rs["delivered_unique"]), (agg["rxPkts"], rs["delivered_unique"]))
        tx, rx = int(agg["txPkts"]), int(agg["rxPkts"])
        C.add("T7 PDR = 100 rx/tx (FlowMonitor)", name, abs(float(agg["pdr"]) - 100.0 * rx / tx) < 1e-3 * max(1, float(agg["pdr"])))
        C.add("T7 app PDR = 100 delivered/app tx", name,
              abs(float(rs["pdr_app_pct"]) - 100.0 * int(rs["delivered_unique"]) / int(rs["app_tx_pkts"])) < 1e-3)
        C.add("T7 throughput = rx * 540 B * 8 / 70 s", name,
              abs(float(agg["throughputKbps"]) - rx * 540 * 8 / 70.0 / 1000.0) < 1e-3 * max(1, float(agg["throughputKbps"])),
              (agg["throughputKbps"], rx * 540 * 8 / 70.0 / 1000.0))
        dl = [float(x["delay_s"]) for x in pp if x["fate"] == "delivered"]
        if fm1000 and dl:
            C.add("T7 FlowMonitor mean delay = mean of per-packet delays (1 us)", name,
                  abs(float(agg["avgDelaySec"]) - sum(dl) / len(dl)) < 1e-6, (agg["avgDelaySec"], sum(dl) / len(dl)))
        C.add("T7 per-packet delay >= 0 and rx within the run", name,
              all(0 <= float(x["delay_s"]) and float(x["rx_time_s"]) <= 100.0 for x in pp if x["fate"] == "delivered"))
        C.add("T7 path_summary totals", name,
              sum(int(x["packets"]) for x in summ) == len(pp)
              and sum(int(x["delivered"]) for x in summ) == int(rs["delivered_unique"])
              and sum(int(x["risk_dropped"]) for x in summ) == int(rs["risk_dropped_pkts"]))
        fate = Counter(x["fate"] for x in pp)
        C.add("T7 fates partition the packets", name,
              fate["delivered"] == int(rs["delivered_unique"]) and fate["risk_drop"] == int(rs["risk_dropped_pkts"])
              and fate["lost_other"] == int(rs["lost_other_pkts"]), dict(fate))
        exp = sum(1 for x in pp if int(x["high_risk_transits"]) > 0)
        C.add("T7 exposure recomputed from packet paths", name, exp == int(rs["exposed_pkts"]), (exp, rs["exposed_pkts"]))
        hi_tr = sum(sum(1 for v in x["path"].split(">")[1:] if int(v) != gw and int(v) in m["high"]) for x in pp)
        C.add("T7 high-risk transits recomputed from path strings", name, hi_tr == sum(int(x["high_risk_transits"]) for x in pp))
        if proto in ("static", "riskaware"):
            C.add("T7 every delivered packet followed the installed path", name,
                  rs["delivered_following_installed_path"] == rs["delivered_checked_against_installed"],
                  (rs["delivered_following_installed_path"], rs["delivered_checked_against_installed"]))
        # T9 Wi-Fi read-back / TXVECTOR
        wr = rows(d / "wifi_readback.csv")
        tv = rows(d / "wifi_txvector_counts.csv")
        if "--standard=80211ax" in args:
            C.add("T9 HE settings read back on every device", name, all(
                r["standard"] == "802.11ax" and r["band"] == "2.4GHz" and r["channel_number"] == "1"
                and float(r["channel_width_mhz"]) == 20 and r["he_configuration"] == "1" and r["he_guard_interval_ns"] == "800"
                and r["data_mode"] == "HeMcs0" and r["control_mode"] == "ErpOfdmRate6Mbps"
                and r["be_max_ampdu_bytes"] == "0" and r["be_max_amsdu_bytes"] == "0" for r in wr), wr[0])
            uni = [r for r in tv if r["frame_class"] == "data_unicast"]
            C.add("T9 unicast data PSDUs are HE SU, HeMcs0, 20 MHz, GI 800 ns", name, uni and all(
                r["preamble"] == "HE_SU" and r["modulation_class"] == "HE" and r["mode"] == "HeMcs0"
                and float(r["channel_width_mhz"]) == 20 and r["guard_interval_ns"] == "800" for r in uni), uni)
            grp = [r for r in tv if r["frame_class"] == "data_group"]
            C.add("T9 group data frames use ERP-OFDM 6 Mbps (NonUnicastMode)", name,
                  all(r["mode"] == "ErpOfdmRate6Mbps" for r in grp), grp)
            dsss = [r for r in tv if r["modulation_class"] == "DSSS"]
            C.add("T9 only management action frames and their ACKs use DSSS 1 Mbps (2.4 GHz basic rate)", name,
                  all(r["frame_type"] in ("MGT_ACTION", "CTL_ACK") and r["mode"] == "DsssRate1Mbps" for r in dsss), dsss)
            acks = [r for r in tv if r["frame_type"] == "CTL_ACK"]
            C.add("T9 ACKs use ERP-OFDM 6 Mbps or DSSS 1 Mbps only", name,
                  all(r["mode"] in ("ErpOfdmRate6Mbps", "DsssRate1Mbps") for r in acks), acks)
            C.add("T9 no HE PPDU other than unicast data", name,
                  all(r["frame_class"] == "data_unicast" for r in tv if r["modulation_class"] == "HE"))
        else:
            C.add("T9 802.11b settings read back", name, all(
                r["standard"] == "802.11b" and r["he_configuration"] == "0" and r["data_mode"] == "DsssRate1Mbps"
                for r in wr), wr[0])
            C.add("T9 all PSDUs DSSS 1 Mbps", name, all(r["mode"] == "DsssRate1Mbps" for r in tv), tv)

    # T3 nesting and protocol independence; T8 matching across routing modes
    for k, sets in ids_by_k.items():
        C.add("T3 same high-risk ids under every protocol/standard", f"k={k}", len(sets) == 1, sets)
    sets = {k: set(next(iter(v))) for k, v in ids_by_k.items() if len(v) == 1}
    C.add("T3 nested k=1 in k=2 in k=3", "S", all(sets.get(k, set()) <= sets.get(k + 1, set()) for k in range(3)), sets)
    ax = [n for n in S if n.startswith(("S_ax_", "F_ax_")) and provs[n]["exit_code"] == 0]
    for proto in ("static", "riskaware", "olsr", "aodv"):
        for k in range(4):
            a, b = out / "runs" / f"S_ax_{proto}_k{k}", out / "runs" / f"F_ax_{proto}_k{k}"
            same = all((a / f).read_bytes() == (b / f).read_bytes() for f in
                       ("packet_paths.csv", "path_summary.csv", "risk_drops.csv", "risk_nodes.csv", "routes_planned.csv",
                        "wifi_txvector_counts.csv"))   # risk_summary/wifistd_ext/stdout carry FlowMonitor rx
            C.add("T8 FlowMonitor timer does not change the simulation (twin identical)", f"{proto} k{k}", same)

    def sched(name):
        pp = rows(out / "runs" / name / "packet_paths.csv")
        by = defaultdict(list)
        for x in pp:
            by[int(x["src"])].append(x["tx_time_s"])
        return {s: (len(v), v[0], v[-1]) for s, v in by.items()}

    def posfile(name):
        return [(r["node_id"], r["x"], r["y"]) for r in rows(next((out / "runs" / name / "pernode").glob("*.csv")))]
    ref_s, ref_p = sched(ax[0]), posfile(ax[0])
    for name in ax[1:]:
        C.add("T8 identical positions across runs", name, posfile(name) == ref_p)
        C.add("T8 identical per-source send schedule (count, first, last)", name, sched(name) == ref_s)
    if all(provs.get(n, {}).get("exit_code") == 0 for n in ("S_ax_static_k0", "S_ax_riskaware_k0")):
        a, b = out / "runs" / "S_ax_static_k0", out / "runs" / "S_ax_riskaware_k0"
        num = lambda d: [line.split(",")[2:] for line in (d / "probe_aggregate.csv").read_text().splitlines()[1:]]
        C.add("T8 riskaware k=0 == static (all aggregate metrics)", "ax k0", num(a) == num(b))
        C.add("T8 riskaware k=0 == static (packet paths)", "ax k0",
              (a / "packet_paths.csv").read_bytes() == (b / "packet_paths.csv").read_bytes())
    a, b = out / "runs" / "S_ax_riskaware_k3", out / "runs" / "S_ax_riskaware_k3_repeat"
    same = all((a / f).read_bytes() == (b / f).read_bytes() for f in
               ("risk_summary.csv", "risk_nodes.csv", "routes_planned.csv", "packet_paths.csv", "risk_drops.csv",
                "wifistd_ext.csv", "stdout.log"))
    C.add("T8 repeat run byte-identical (determinism)", "riskaware k3", same)
    # same logical packet, same node -> same decision across protocols
    dec = defaultdict(set)
    for name in ax:
        for x in rows(out / "runs" / name / "risk_drops.csv"):
            dec[(x["node_id"], x["src"], x["seq"])].add(x["u"])
    C.add("T6 identical decision value for a (node, src, seq) across protocols", "S", all(len(v) == 1 for v in dec.values()))

    # T10 (risk-v2): Block Ack SSN fix
    if version in ("v2", "v3", "v4"):
        for name in S:
            d = out / "runs" / name
            if provs[name]["exit_code"] != 0:
                continue
            pp = rows(d / "packet_paths.csv")
            agg = rows(d / "probe_aggregate.csv")[0]
            rs = rows(d / "risk_summary.csv")[0]
            dl = [float(x["delay_s"]) for x in pp if x["fate"] == "delivered"]
            C.add("T10 no delivered packet delayed > 1 s", name, max(dl) < 1.0, f"max {max(dl):.3f} s")
            C.add("T10 FlowMonitor rx = sink with the default 10 s timer", name,
                  "--ns3::FlowMonitor::MaxPerHopDelay=1000s" in S[name] or agg["rxPkts"] == rs["delivered_unique"],
                  (agg["rxPkts"], rs["delivered_unique"]))
            if "--standard=80211ax" in S[name]:
                fix = rows(d / "ba_ssn_fix.csv")
                bar = sum(int(r["psdus"]) for r in rows(d / "wifi_txvector_counts.csv") if r["frame_type"] == "CTL_BACKREQ")
                if version != "v4":
                    C.add("T10 a BlockAckReq was transmitted for every SSN-mismatch event", name, bar >= len(fix), (len(fix), bar))
                C.add("T10 fix only corrects mismatches (originator start != advertised SSN)", name,
                      all(r["advertised_ssn"] != r["originator_start"] for r in fix))
                if version == "v2" and compare_to and not fix and (compare_to / "runs" / name).exists():
                    C.add("T10 runs where the fix never triggers equal risk-v1", name,
                          (compare_to / "runs" / name / "packet_paths.csv").read_bytes() == (d / "packet_paths.csv").read_bytes())
            else:
                C.add("T10 802.11b: no fix file (non-QoS)", name, not (d / "ba_ssn_fix.csv").exists())

    # T11 (risk-v3): Block Ack re-establishment fix
    if version == "v3":
        for name in S:
            d = out / "runs" / name
            if provs[name]["exit_code"] != 0:
                continue
            if "--standard=80211ax" in S[name]:
                fix = rows(d / "ba_ssn_fix.csv")
                re_ = rows(d / "ba_reest_fix.csv") if (d / "ba_reest_fix.csv").exists() else None
                C.add("T11 ba_reest_fix.csv written (802.11ax)", name, re_ is not None)
                if re_ is None:
                    continue
                nbar = sum(r["bar_scheduled"] == "1" for r in re_)
                bar = sum(int(r["psdus"]) for r in rows(d / "wifi_txvector_counts.csv") if r["frame_type"] == "CTL_BACKREQ")
                C.add("T11 a BlockAckReq was transmitted for every SSN-mismatch and re-establishment event", name,
                      bar >= len(fix) + nbar, (len(fix), nbar, bar))
                C.add("T11 BAR scheduled iff originator start != advertised SSN", name,
                      all((r["bar_scheduled"] == "1") == (r["advertised_ssn"] != "-1" and r["advertised_ssn"] != r["start_after"])
                          for r in re_))
                if compare_to and nbar == 0 and (compare_to / "runs" / name).exists():
                    C.add("T11 runs where the re-establishment fix sends no BAR equal risk-v2", name,
                          (compare_to / "runs" / name / "packet_paths.csv").read_bytes() == (d / "packet_paths.csv").read_bytes())
            else:
                C.add("T11 802.11b: no re-establishment file (non-QoS)", name, not (d / "ba_reest_fix.csv").exists())
        for name, (v2name, args) in REEST0.items():
            d = out / "runs" / name
            if not compare_to or not (compare_to / "runs" / v2name).exists():
                C.add("T11 --baReestFix=0 equals risk-v2 (all outputs)", name, False, "BLOCKED: no --compareTo v2 run")
                continue
            bad = same_outputs(compare_to / "runs" / v2name, d)
            C.add("T11 --baReestFix=0 equals risk-v2 (all outputs)", name, not bad, bad or "identical")
            C.add("T11 --baReestFix=0 writes no ba_reest_fix.csv", name, not (d / "ba_reest_fix.csv").exists())

    # T12 (risk-v4): one BlockAckReq per ADDBA Response
    if version == "v4":
        for name in S:
            d = out / "runs" / name
            if provs[name]["exit_code"] != 0:
                continue
            if "--standard=80211ax" in S[name]:
                ab = rows(d / "ba_addba_bar.csv") if (d / "ba_addba_bar.csv").exists() else None
                C.add("T12 ba_addba_bar.csv written (802.11ax)", name, ab is not None)
                if ab is None:
                    continue
                nbar = sum(r["bar_scheduled"] == "1" for r in ab)
                bar = sum(int(r["psdus"]) for r in rows(d / "wifi_txvector_counts.csv") if r["frame_type"] == "CTL_BACKREQ")
                C.add("T12 a BlockAckReq was transmitted for every scheduled ADDBA-Response BAR", name, bar >= nbar, (nbar, bar))
                C.add("T12 BAR scheduled iff the agreement is established at check time", name,
                      all((r["bar_scheduled"] == "1") == (r["originator_start"] != "-1") for r in ab))
                C.add("T12 v2/v3 triggers send no BAR (log only)", name,
                      all(r["bar_scheduled"] == "0" for r in rows(d / "ba_ssn_fix.csv"))
                      and all(r["bar_scheduled"] == "0" for r in rows(d / "ba_reest_fix.csv")))
                C.add("T12 one ADDBA-Response record per (node, recipient, tid, time)", name,
                      len({(r["time_s"], r["node_id"], r["recipient"], r["tid"]) for r in ab}) == len(ab))
            else:
                C.add("T12 802.11b: no ba_addba_bar.csv (non-QoS)", name, not (d / "ba_addba_bar.csv").exists())
        for name, (v3name, args) in REEST0.items():
            d = out / "runs" / name
            if not compare_to or not (compare_to / "runs" / v3name).exists():
                C.add("T12 --baAddbaBar=0 equals risk-v3 (all outputs)", name, False, "BLOCKED: no --compareTo v3 run")
                continue
            bad = same_outputs(compare_to / "runs" / v3name, d)
            C.add("T12 --baAddbaBar=0 equals risk-v3 (all outputs)", name, not bad, bad or "identical")
            C.add("T12 --baAddbaBar=0 writes no ba_addba_bar.csv", name, not (d / "ba_addba_bar.csv").exists())

    with open(out / "checks.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["test", "subject", "passed", "detail"])
        w.writeheader()
        w.writerows(C.rows)
    by = defaultdict(lambda: [0, 0])
    for r in C.rows:
        by[r["test"]][0 if r["passed"] else 1] += 1
    lines = [f"validation {out.name}: {sum(v[0] for v in by.values())} passed, {sum(v[1] for v in by.values())} failed"]
    lines += [f"  {'PASS' if v[1] == 0 else 'FAIL'}  {t}: {v[0]} passed, {v[1]} failed" for t, v in sorted(by.items())]
    lines += ["", "failures (first 40):"] + [f"  {r['test']} | {r['subject']} | {r['detail']}" for r in C.rows if not r["passed"]][:40]
    (out / "SUMMARY.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0 if all(v[1] == 0 for v in by.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
