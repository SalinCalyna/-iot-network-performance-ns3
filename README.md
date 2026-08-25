# Analysis of IoT Network Performance Using NS-3

Research project analyzing routing-protocol performance (AODV, OLSR, Static
Routing) in a multi-hop 802.11b ad-hoc IoT wireless mesh, using the
[ns-3](https://www.nsnam.org/) network simulator.

**Current baseline: V2.7** — 12 scenarios (3 protocols x 4 network sizes:
10/20/30/50 nodes), 5 independent topology seeds per scenario, 60 total
simulation runs. A separate, in-progress **V3 sigmoid-routing extension**
(4 validation runs only, not a full study) is also included — see
[Sigmoid research direction](#sigmoid-routing-research-direction-v3) below.

**Public dashboard:** https://salincalyna.github.io/-iot-network-performance-ns3/
(static build of the same dashboard, auto-deployed from `site/` via GitHub
Actions on every push to `main`)

## Researcher

| | |
|---|---|
| Researcher | Salinthip Keereerat |
| Student ID | 6630613037 |
| Institution | College of Computing, Prince of Songkla University, Phuket Campus |
| Advisor | Komsan Kanjanasit |
| Co-Advisors | Wisarut Chantara, Kullawat Chaowanawatee |
| GitHub | [@SalinCalyna](https://github.com/SalinCalyna) |
| Repository | https://github.com/SalinCalyna/-iot-network-performance-ns3 |

## Objective

Compare how a reactive protocol (AODV), a proactive protocol (OLSR), and a
fixed baseline (custom static routing) perform as a multi-hop wireless IoT
sensor network scales from 10 to 50 nodes, using Packet Delivery Ratio,
Throughput, End-to-End Delay, and Packet Loss measured directly from ns-3's
FlowMonitor.

## Repository contents

```
scratch/
  iot-network.cc          V2.7 simulation: multi-hop 802.11b ad-hoc IoT mesh,
                           AODV / OLSR / Static routing, FlowMonitor metrics
  iot-network-v3.cc        V3 (in-progress): 15-node clustered topology, adds a
                           4th "sigmoid" routing mode -- validation-only, see below
  scratch-simulator.cc     Earlier (V1) implementation, kept for reference
experiments/
  run_experiments.sh       Runs the full 12-scenario x 5-seed V2.7 matrix
  run_and_analyze.sh       Wrapper: analyze-only by default, --run re-runs first
  analyze_results.py       Auto-detects available metrics, writes results/statistics.csv
                            and PNG+SVG plots to results/plots/
  export_static_data.py    Exports results/*.csv (and results/v3/*.csv) to
                            site/data/*.json for the GitHub Pages build
  requirements.txt         Python dependencies
results/
  *.csv                    V2.7 experiment results (12 files, 60 rows total)
  logs/                    Per-run console logs
  plots/                   Generated PNG + SVG plots (from analyze_results.py)
  v3/                      V3 sigmoid validation results (4 rows only)
docs/
  methodology.md, experiment-design.md, sigmoid-metric.md
                           Design rationale for the V3 sigmoid extension
dashboard/
  app.py                   Flask backend -- reads results/*.csv live via pandas.
                           Local-only; not used by the public GitHub Pages site.
  templates/, static/      Dashboard frontend (dark research-dashboard UI,
                           Chart.js visualizations, interactive topology,
                           methodology & validity panels)
site/
  index.html, static/      Static (no-backend) build of the same dashboard,
                           deployed to GitHub Pages
  data/*.json               Build-time export of results/*.csv (see
                           export_static_data.py) -- the static site's only
                           data source, regenerated whenever results change
  results/                 Copies of results/*.csv and results/plots/* served
                           directly by the static site
.github/workflows/
  deploy-pages.yml          GitHub Actions workflow: deploys site/ to GitHub
                           Pages on every push to main
```

## Reproducing the simulation

`scratch/iot-network.cc` is an ns-3 scratch program; it needs a working
ns-3 checkout (developed against ns-3.47-dev) to build and run:

```bash
# from the root of a working ns-3 checkout
cp scratch/iot-network.cc  <ns-3-checkout>/scratch/
cp -r experiments           <ns-3-checkout>/
cd <ns-3-checkout>
./ns3 build scratch_iot-network
./experiments/run_experiments.sh        # runs the full 60-run V2.7 matrix
```

The `results/` directory in this repository already contains the CSVs and
logs produced by that matrix — you do not need to rerun it to inspect the
data.

## Regenerating graphs and statistics

```bash
cd <ns-3-checkout>
python3 -m venv venv && source venv/bin/activate   # optional but recommended
pip install -r experiments/requirements.txt
./experiments/run_and_analyze.sh          # analyze-only: reads existing results/*.csv
./experiments/run_and_analyze.sh --run    # re-runs the full matrix first, then analyzes
```

This writes `results/statistics.csv` (mean/std/min/max/count per
protocol x network size) and PNG + SVG plots to `results/plots/`. The
dashboard's "Generated Research Graphs" panel and the public GitHub Pages
site both read this same output — nothing is regenerated at deploy time.

## Running the dashboard locally (Flask)

```bash
python3 -m venv venv && source venv/bin/activate   # optional but recommended
pip install -r requirements.txt
python3 dashboard/app.py
```
Then open http://127.0.0.1:5000. The dashboard reads `results/*.csv`
directly (via pandas) on every request — nothing is hardcoded, and adding a
new CSV that follows the existing column structure is picked up
automatically.

## Public dashboard (GitHub Pages, static)

https://salincalyna.github.io/-iot-network-performance-ns3/

This is a static HTML/CSS/JS build of the same dashboard, since GitHub Pages
cannot run a Flask backend. It reads pre-exported JSON under `site/data/`
instead of querying `/api/*` live. To update it after new results:

```bash
python3 experiments/export_static_data.py results site/data
cp results/*.csv site/results/csv/
cp results/plots/* site/results/plots/
git add site/ results/ && git commit -m "Update results and regenerate static site data" && git push
```
GitHub Actions (`.github/workflows/deploy-pages.yml`) then redeploys
`site/` to Pages automatically. Two features are Flask-only and are not
available on the public static site: live re-validation of malformed CSVs
(`/api/validate`) and on-the-fly `/api/graphs` discovery of newly-added plot
files — the static site always reflects the JSON/assets present at the last
export.

## Methodology summary (V2.7 baseline)

- Network: multi-hop IEEE 802.11b ad-hoc mesh (`AdhocWifiMac`,
  `ConstantRateWifiManager @ DsssRate1Mbps`, `LogDistancePropagationLossModel`
  exponent=3.0, referenceLoss=40dB)
- Gateway/Sink/Server merged into a single node at the field centre
- Deployment area: 250 x 250 m, tx power 20 dBm
- Traffic: 8 kbps continuous UDP CBR per sensor, 512 B packets
- Simulation time: 100 s total, application traffic active from 30 s-100 s
  (70 s active window)
- Static routing: BFS shortest-hop routes over an assumed 90 m disk
  connectivity model, installed as real `Ipv4StaticRouting` host routes (not
  `Ipv4GlobalRoutingHelper`, which was found to treat the shared wifi channel
  as all-nodes-one-hop and defeats multi-hop routing)

## Known limitation (V2.7.1 validation finding)

A validation pass on the V2.7 results found that AODV's `PacketsSent` count,
as measured by ns-3's FlowMonitor, is not constant across topology seeds the
way OLSR's and Static's counts are — it appears to scale with topology
conditions in a way that suggests FlowMonitor is counting some AODV
route-repair/requeue events as new "sent" packets. **AODV PDR figures should
therefore be treated as provisional, not a final confirmed comparison
against OLSR/Static**, until this is resolved (most likely by counting
offered packets at the application layer instead of via FlowMonitor's IP-layer
trace). Throughput and delay are unaffected by this issue. This is reflected
in the dashboard's Validity section.

## Sigmoid routing research direction (V3)

`scratch/iot-network-v3.cc` is a **separate**, in-progress extension: a
15-node clustered topology with a wired Gateway/Server backhaul and a 4th
routing mode ("sigmoid") that computes Dijkstra shortest paths over
sigmoid-weighted edge costs,

```
S(x) = 1 / (1 + exp(-k * (x - x0)))
```

applied to two geometrically-justified proxies: link quality
(`distance / txRange`) and load (`node_degree / max_degree`). Full
derivation and the analysis showing k = 0.1/0.2/0.3 sit in the sigmoid's
near-linear regime for x in [0,1] are in `docs/sigmoid-metric.md`,
`docs/methodology.md`, and `docs/experiment-design.md`.

**Only a 4-run smoke test has been executed** (1 seed, medium traffic, one
run per protocol) to confirm the sigmoid mode compiles, runs, and produces
sane output — the full experiment matrix has **not** been run. The
dashboard's Sigmoid (V3) section shows these 4 rows for transparency, but
they carry no variance estimate and are not a statistical comparison against
AODV/OLSR/Static. Extending this to a full matrix, and resolving a known
FlowMonitor routing-overhead measurement gap for OLSR (broadcast HELLO/TC
traffic isn't captured by the `SendOutgoing` trace), is future work.
