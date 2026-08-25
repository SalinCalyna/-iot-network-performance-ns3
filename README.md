# Analysis of IoT Network Performance Using NS-3

Research project analyzing routing-protocol performance (AODV, OLSR, Static
Routing) in a multi-hop 802.11b ad-hoc IoT wireless mesh, using the
[ns-3](https://www.nsnam.org/) network simulator.

**Current version: V2.7 (baseline)** — 12 scenarios (3 protocols x 4 network
sizes: 10/20/30/50 nodes), 5 independent topology seeds per scenario, 60
total simulation runs.

## Researcher

| | |
|---|---|
| Researcher | Salinthip Keereerat |
| Student ID | 6630613037 |
| Institution | College of Computing, Prince of Songkla University, Phuket Campus |
| Advisor | Komsan Kanjanasit |
| Co-Advisors | Wisarut Chantara, Kullawat Chaowanawatee |
| GitHub | [@SalinCalyna](https://github.com/SalinCalyna) |

## Repository contents

```
scratch/
  iot-network.cc         V2.7 simulation: multi-hop 802.11b ad-hoc IoT mesh,
                          AODV / OLSR / Static routing, FlowMonitor metrics
  scratch-simulator.cc   Earlier (V1) implementation, kept for reference
experiments/
  run_experiments.sh     Runs the full 12-scenario x 5-seed experiment matrix
  analyze_results.py     Aggregates results/*.csv into a mean +/- SD summary
results/
  *.csv                  V2.7 experiment results (12 files, 60 rows total)
  logs/                  Per-run console logs (60 files)
dashboard/
  app.py                 Flask backend -- reads results/*.csv live via pandas
  templates/, static/    Dashboard frontend (dark research-dashboard UI,
                          Chart.js visualizations, methodology & validity
                          panels)
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
python3 experiments/analyze_results.py  # prints the summary table
```

The `results/` directory in this repository already contains the CSVs and
logs produced by that matrix -- you do not need to rerun it to inspect the
data.

## Running the dashboard

```bash
python3 -m venv venv && source venv/bin/activate   # optional but recommended
pip install -r requirements.txt
python3 dashboard/app.py
```
Then open http://127.0.0.1:5000. The dashboard reads `results/*.csv`
directly (via pandas) on every request -- nothing is hardcoded, and adding a
new CSV that follows the existing column structure is picked up
automatically.

## Methodology summary

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
  `Ipv4GlobalRoutingHelper`)

## Known limitation (V2.7.1 validation finding)

A validation pass on the V2.7 results found that AODV's `PacketsSent` count,
as measured by ns-3's FlowMonitor, is not constant across topology seeds the
way OLSR's and Static's counts are -- it appears to scale with topology
conditions in a way that suggests FlowMonitor is counting some AODV
route-repair/requeue events as new "sent" packets. **AODV PDR figures should
therefore be treated as provisional, not a final confirmed comparison
against OLSR/Static**, until this is resolved (most likely by counting
offered packets at the application layer instead of via FlowMonitor's IP-layer
trace). Throughput and delay are unaffected by this issue. This is reflected
in the dashboard's Validity section.
