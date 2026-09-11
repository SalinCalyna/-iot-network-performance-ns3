// Main dashboard wiring: navigation, filters, and section rendering.
// All numbers rendered here come from data/final_research.json, which is a direct
// extract of analysis/final-report-data/*.csv (see that package for the source of truth).

const COLORS = { olsr: "var(--olsr)", static: "var(--static)", aodv: "var(--aodv)", v4: "var(--v4)" };
let DATA = null;

// ---------------------------------------------------------------- navigation
function initNav() {
  const links = document.querySelectorAll(".navlink");
  const sections = [...document.querySelectorAll("section.view")];
  links.forEach(l => l.addEventListener("click", () => {
    document.getElementById(l.dataset.target).scrollIntoView({ behavior: "smooth", block: "start" });
    closeDrawer();
  }));
  const spy = new IntersectionObserver(entries => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        links.forEach(l => l.classList.toggle("active", l.dataset.target === e.target.id));
      }
    });
  }, { rootMargin: "-15% 0px -70% 0px" });
  sections.forEach(s => spy.observe(s));

  document.getElementById("menu-btn").addEventListener("click", () => {
    document.getElementById("sidebar").classList.add("open");
    document.getElementById("scrim").classList.add("show");
  });
  document.getElementById("scrim").addEventListener("click", closeDrawer);
}
function closeDrawer() {
  document.getElementById("sidebar").classList.remove("open");
  document.getElementById("scrim").classList.remove("show");
}

// ---------------------------------------------------------------- pill filter helper
function pillGroup(container, options, activeIdx, onChange) {
  container.innerHTML = "";
  options.forEach((opt, i) => {
    const b = document.createElement("button");
    b.className = "pill" + (i === activeIdx ? " active" : "");
    b.textContent = opt;
    b.addEventListener("click", () => {
      [...container.children].forEach(c => c.classList.remove("active"));
      b.classList.add("active");
      onChange(i);
    });
    container.appendChild(b);
  });
}

// ---------------------------------------------------------------- 1. hero KPIs
function renderHero() {
  const s = DATA.stats;
  document.getElementById("kpi-v3").textContent = s.v3_runs.toLocaleString();
  document.getElementById("kpi-v4").textContent = s.v4_matched.toLocaleString();
  document.getElementById("kpi-bottleneck").textContent = s.bottleneck_runs.toLocaleString();
  document.getElementById("kpi-repro").textContent = `${s.repro_pass}/${s.repro_total - s.repro_na}`;
}

// ---------------------------------------------------------------- 2. network health
function statusFromAirtime(v) { return v >= 0.85 ? "critical" : v >= 0.6 ? "congested" : v >= 0.35 ? "degraded" : "normal"; }
function statusFromPdr(v) { return v >= 45 ? "normal" : v >= 30 ? "degraded" : v >= 15 ? "congested" : "critical"; }
function renderHealth() {
  const el = document.getElementById("health-panel");
  el.innerHTML = "";
  // representative near-saturated condition: OLSR N=100 high (the frozen worst-measured case)
  const cell = DATA.bottleneck["olsr-high"].find(d => d.n === 100);
  healthBar(el, "PDR", cell.pdr, cell.pdr.toFixed(1) + "%", statusFromPdr);
  healthBar(el, "Throughput", Math.min(cell.throughput / 5, 100), cell.throughput.toFixed(0) + " kbps", () => "normal");
  healthBar(el, "Gateway Airtime", cell.gw_airtime * 100, (cell.gw_airtime * 100).toFixed(0) + "%", v => statusFromAirtime(v / 100));
  healthBar(el, "MAC Queue Drops", Math.min(cell.macq / 500, 100), cell.macq.toFixed(0), v => v > 60 ? "critical" : v > 25 ? "congested" : "normal");
  document.getElementById("health-note").textContent =
    `Representative near-saturated condition: OLSR, N=100, high traffic (§10 bottleneck characterisation, 11 seeds). Thresholds: gateway airtime ≥85% = critical, ≥60% = congested, ≥35% = degraded, else normal.`;
}

// ---------------------------------------------------------------- 3. topology (main Network Topology section)
let topoState = { n: 75, protocol: "olsr", traffic: "high", mobility: "static", seed: 20 };
let topoAnim = { path: [], step: 0, timer: null, playing: false };

function renderTopoSection() {
  const nOpts = [10, 20, 30, 50, 75, 100];
  const pOpts = ["aodv", "olsr", "static", "sigmoid"];
  const tOpts = ["low", "medium", "high"];
  const mOpts = ["static", "low", "medium"];
  const sOpts = [20, 25, 30];
  pillGroup(document.getElementById("topo-n"), nOpts.map(String), nOpts.indexOf(topoState.n), i => { topoState.n = nOpts[i]; resetTraversal(); drawTopo(); });
  pillGroup(document.getElementById("topo-p"), pOpts.map(s => s.toUpperCase()), pOpts.indexOf(topoState.protocol), i => { topoState.protocol = pOpts[i]; resetTraversal(); drawTopo(); });
  pillGroup(document.getElementById("topo-t"), tOpts.map(s => s[0].toUpperCase() + s.slice(1)), tOpts.indexOf(topoState.traffic), i => { topoState.traffic = tOpts[i]; resetTraversal(); drawTopo(); });
  const topoM = document.getElementById("topo-m");
  if (topoM) pillGroup(topoM, mOpts.map(s => s[0].toUpperCase() + s.slice(1)), mOpts.indexOf(topoState.mobility), i => { topoState.mobility = mOpts[i]; resetTraversal(); drawTopo(); });
  const topoS = document.getElementById("topo-s");
  if (topoS) pillGroup(topoS, sOpts.map(String), sOpts.indexOf(topoState.seed), i => { topoState.seed = sOpts[i]; resetTraversal(); drawTopo(); });

  const playBtn = document.getElementById("topo-play");
  const pauseBtn = document.getElementById("topo-pause");
  const resetBtn = document.getElementById("topo-reset");
  const stepBtn = document.getElementById("topo-step");
  if (playBtn) playBtn.addEventListener("click", playTraversal);
  if (pauseBtn) pauseBtn.addEventListener("click", pauseTraversal);
  if (resetBtn) resetBtn.addEventListener("click", () => { resetTraversal(); drawTopo(); });
  if (stepBtn) stepBtn.addEventListener("click", stepTraversal);

  drawTopo();
}

function resetTraversal() {
  pauseTraversal();
  topoAnim.step = 0;
}

// Returns a measured-result summary for the closest available exact/pooled match, or null
// if no measured result exists for this configuration. Never invents values.
function lookupMeasured(protocol, n, traffic, mobility) {
  if (mobility === "static" && (protocol === "olsr" || protocol === "static")) {
    const cell = (DATA.bottleneck[protocol + "-" + traffic] || []).find(d => d.n === n);
    if (cell) return { source: "§10 bottleneck study (exact match, 11 seeds)", pdr: cell.pdr, throughput: cell.throughput, gw_airtime: cell.gw_airtime, macq: cell.macq };
  }
  if (protocol === "aodv" || protocol === "olsr" || protocol === "static") {
    const arr = DATA.baseline[protocol];
    const cell = arr && arr.find(d => d.n === n);
    if (cell) return { source: "V3 baseline (pooled across traffic & mobility, 99 seeds) — not this exact condition", pdr: cell.pdr, throughput: cell.throughput, delay: cell.delay, pooled: true };
  }
  return null;
}

function drawTopo() {
  const n = topoState.n, protocol = topoState.protocol, traffic = topoState.traffic, mobility = topoState.mobility, seed = topoState.seed;
  const key = protocol + "-" + n + "-" + traffic;
  const real = (mobility === "static" && seed === 20) ? DATA.topology_real[key] : null;
  const container = document.getElementById("topo-canvas");
  const noteEl = document.getElementById("topo-note");
  let nodes, congestionLevel = 0, source;
  if (real) {
    nodes = real; source = "real";
    const bnKey = protocol + "-" + traffic;
    const bnCell = (DATA.bottleneck[bnKey] || []).find(d => d.n === n);
    congestionLevel = bnCell ? bnCell.gw_airtime : 0;
  } else {
    nodes = generateTopology(n, seed); source = "generated";
    const bnCell = (DATA.bottleneck["olsr-" + (traffic === "low" ? "medium" : traffic)] || [])[0];
    congestionLevel = bnCell ? bnCell.gw_airtime * 0.4 : 0.2;
  }
  topoAnim.path = buildHopPath(nodes);
  if (topoAnim.step > topoAnim.path.length - 1) topoAnim.step = 0;

  renderTopology(container, nodes, {
    congestionLevel: congestionLevel,
    highlightPath: topoAnim.path,
    markerStep: (topoAnim.playing || topoAnim.step > 0) ? topoAnim.step : -1
  });

  if (source === "real") {
    noteEl.innerHTML = "<strong>Captured topology</strong> — actual node positions and hop distances from the frozen bottleneck-characterisation run (" + protocol.toUpperCase() + ", N=" + n + ", " + traffic + " traffic, static mobility, seed 20). Gateway airtime in this condition: <strong>" + (congestionLevel * 100).toFixed(0) + "%</strong>.";
  } else if (protocol === "sigmoid") {
    noteEl.innerHTML = "<strong>Conceptual / Simulation Topology View</strong> — Sigmoid routing is the proposed V3 research direction (see Adaptive Routing) and has not been evaluated on this topology yet. This diagram uses the simulator's real placement algorithm for illustration only; no Sigmoid routing data exists for any configuration.";
  } else {
    noteEl.innerHTML = "<strong>Conceptual / Simulation Topology View</strong> — no per-node capture exists for " + protocol.toUpperCase() + " / N=" + n + " / " + traffic + " traffic / " + mobility + " mobility / seed " + seed + " in the frozen instrumentation (captured data covers OLSR/Static only, N∈{30,50,75,100}, static mobility, seed 20). This diagram uses the same placement algorithm as the simulator (uniform-random, seeded, 250×250m field, gateway at centre, 90m range) for illustration; it is not a captured run for this exact condition.";
  }

  // "Current View" configuration summary
  const cv = document.getElementById("topo-current-view");
  if (cv) {
    cv.innerHTML = '<div class="health-row"><div class="health-label">N</div><div style="flex:1;font-weight:700">' + n + '</div></div>'
      + '<div class="health-row"><div class="health-label">Routing</div><div style="flex:1;font-weight:700">' + protocol.toUpperCase() + '</div></div>'
      + '<div class="health-row"><div class="health-label">Traffic</div><div style="flex:1;font-weight:700">' + (traffic[0].toUpperCase() + traffic.slice(1)) + '</div></div>'
      + '<div class="health-row"><div class="health-label">Mobility</div><div style="flex:1;font-weight:700">' + (mobility[0].toUpperCase() + mobility.slice(1)) + '</div></div>'
      + '<div class="health-row"><div class="health-label">Seed</div><div style="flex:1;font-weight:700">' + seed + '</div></div>';
  }

  // measured-results card, shown only if a real match exists (never fabricated)
  const mc = document.getElementById("topo-measured-card");
  if (mc) {
    const measured = lookupMeasured(protocol, n, traffic, mobility);
    if (measured) {
      mc.innerHTML = '<div class="panel-sub" style="margin-bottom:8px">' + measured.source + '</div>'
        + '<div class="health-row"><div class="health-label">PDR</div><div style="flex:1;font-weight:700">' + measured.pdr.toFixed(2) + '%</div></div>'
        + (measured.throughput != null ? '<div class="health-row"><div class="health-label">Throughput</div><div style="flex:1;font-weight:700">' + measured.throughput.toFixed(1) + ' kbps</div></div>' : "")
        + (measured.gw_airtime != null ? '<div class="health-row"><div class="health-label">Gateway airtime</div><div style="flex:1;font-weight:700">' + (measured.gw_airtime * 100).toFixed(0) + '%</div></div>' : "");
    } else {
      mc.innerHTML = '<div class="panel-sub">No measured result exists for this exact configuration in the frozen research (this is expected for Sigmoid routing — see Adaptive Routing section).</div>';
    }
  }
}

// ---------------------------------------------------------------- route traversal animation
// Illustrative route traversal only -- highlights the same hop-chain edges already drawn
// in the topology, using the nearest-neighbour heuristic. This is NOT a packet-level replay.
function renderTraversalFrame() {
  const container = document.getElementById("topo-canvas");
  const n = topoState.n, protocol = topoState.protocol, traffic = topoState.traffic, mobility = topoState.mobility, seed = topoState.seed;
  const real = (mobility === "static" && seed === 20) ? DATA.topology_real[protocol + "-" + n + "-" + traffic] : null;
  const nodes = real || generateTopology(n, seed);
  renderTopology(container, nodes, { congestionLevel: 0.5, highlightPath: topoAnim.path, markerStep: topoAnim.step });
  const caption = document.getElementById("topo-traversal-caption");
  if (caption) {
    const atEnd = topoAnim.step >= topoAnim.path.length - 1;
    caption.textContent = atEnd
      ? "Illustrative route traversal — reached the gateway."
      : "Illustrative route traversal — hop " + (Math.floor(topoAnim.step) + 1) + " of " + (topoAnim.path.length - 1) + ".";
  }
}
function playTraversal() {
  if (!topoAnim.path.length) drawTopo();
  if (topoAnim.playing) return;
  topoAnim.playing = true;
  topoAnim.timer = setInterval(function () {
    topoAnim.step += 1;
    if (topoAnim.step >= topoAnim.path.length - 1) { topoAnim.step = topoAnim.path.length - 1; pauseTraversal(); }
    renderTraversalFrame();
  }, 900);
}
function pauseTraversal() {
  topoAnim.playing = false;
  if (topoAnim.timer) { clearInterval(topoAnim.timer); topoAnim.timer = null; }
}
function stepTraversal() {
  pauseTraversal();
  if (!topoAnim.path.length) drawTopo();
  topoAnim.step = Math.min(topoAnim.step + 1, Math.max(topoAnim.path.length - 1, 0));
  renderTraversalFrame();
}

// ---------------------------------------------------------------- 4. performance charts
let perfProtocols = { aodv: true, olsr: true, static: true };
function renderPerformance() {
  const toggles = document.getElementById("perf-protocol-toggle");
  toggles.innerHTML = "";
  Object.keys(perfProtocols).forEach(p => {
    const b = document.createElement("button");
    b.className = "pill" + (perfProtocols[p] ? " active" : "");
    b.textContent = p.toUpperCase();
    b.style.color = perfProtocols[p] ? "#fff" : "";
    b.addEventListener("click", () => { perfProtocols[p] = !perfProtocols[p]; drawPerfCharts(); renderPerformance(); });
    toggles.appendChild(b);
  });
  drawPerfCharts();
}
function activeSeries(metric, scale) {
  const out = {};
  Object.keys(perfProtocols).forEach(p => {
    if (!perfProtocols[p]) return;
    out[p] = DATA.baseline[p].map(d => ({ x: d.n, y: scale ? d[metric] * scale : d[metric] }));
  });
  return out;
}
function drawPerfCharts() {
  legendOnce("perf-legend");
  lineChart(document.getElementById("chart-pdr"), activeSeries("pdr"), { colors: COLORS, unit: "%", yfmt: 0 });
  lineChart(document.getElementById("chart-throughput"), activeSeries("throughput"), { colors: COLORS, unit: " kbps", yfmt: 0 });
  lineChart(document.getElementById("chart-delay"), activeSeries("delay"), { colors: COLORS, unit: " ms", yfmt: 0 });
  lineChart(document.getElementById("chart-loss"), activeSeries("loss"), { colors: COLORS, unit: " pkts", yfmt: 0 });
}
function legendOnce(id) {
  const c = document.getElementById(id); c.innerHTML = "";
  legend(c, [["AODV", "var(--aodv)"], ["OLSR", "var(--olsr)"], ["Static", "var(--static)"]]);
}

// ---------------------------------------------------------------- 5. traffic load
function renderTrafficLoad() {
  const c = document.getElementById("chart-traffic-load");
  legendOnce("traffic-legend");
  const levels = ["low", "medium", "high"];
  const series = {};
  ["aodv", "olsr", "static"].forEach(p => { series[p] = levels.map(l => ({ x: l.toUpperCase(), y: DATA.traffic_level[p][l] })); });
  groupedBar(c, series, { colors: COLORS, unit: "%", yfmt: 0, xlabel: x => x });
}

// ---------------------------------------------------------------- 6. bottleneck
function renderBottleneck() {
  const c1 = document.getElementById("chart-gw-airtime");
  legend(document.getElementById("bn-legend"), [["OLSR / high", "var(--olsr)"], ["Static / high", "var(--static)"]]);
  groupedBar(c1, {
    olsr: DATA.bottleneck["olsr-high"].map(d => ({ x: d.n, y: d.gw_airtime })),
    static: DATA.bottleneck["static-high"].map(d => ({ x: d.n, y: d.gw_airtime }))
  }, { colors: COLORS, yfmt: 2, xlabel: x => `N=${x}` });
}

// ---------------------------------------------------------------- 7. hop-based MAC queue chart
let hopState = { protocol: "olsr", n: 100, traffic: "high" };
function renderHopChart() {
  pillGroup(document.getElementById("hop-n"), [30, 50, 75, 100].map(String), [30, 50, 75, 100].indexOf(hopState.n), i => { hopState.n = [30, 50, 75, 100][i]; drawHop(); });
  pillGroup(document.getElementById("hop-p"), ["OLSR", "Static"], hopState.protocol === "olsr" ? 0 : 1, i => { hopState.protocol = i === 0 ? "olsr" : "static"; drawHop(); });
  drawHop();
}
function drawHop() {
  const key = `${hopState.protocol}-${hopState.n}-${hopState.traffic}`;
  const bins = (DATA.hopbin[key] || []).filter(b => b.bin !== "unreach");
  const c = document.getElementById("chart-hop-macq");
  groupedBar(c, { macq: bins.map(b => ({ x: b.bin, y: b.macq })) },
    { colors: { macq: "var(--warn)" }, yfmt: 1, xlabel: x => x === "gw" ? "Gateway" : x.toUpperCase() });
}

// ---------------------------------------------------------------- 8. retry
function renderRetry() {
  const tbody = document.getElementById("retry-table-body"); tbody.innerHTML = "";
  DATA.retry.forEach(r => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${r.protocol.toUpperCase()}</td><td class="num">${r.n}</td><td>${r.traffic}</td>
      <td class="num">${r.retry_pct.toFixed(2)}%</td><td class="num">${r.macq_pct.toFixed(2)}%</td>`;
    tbody.appendChild(tr);
  });
  const avg = arr => arr.reduce((a, b) => a + b, 0) / arr.length;
  twoBar(document.getElementById("chart-retry-vs-macq"),
    { label: "Retry exhaustion", value: avg(DATA.retry.map(r => r.retry_pct)), color: "var(--purple)" },
    { label: "MAC queue overflow", value: avg(DATA.retry.map(r => r.macq_pct)), color: "var(--warn)" },
    { unit: "%", yfmt: 1 });
}

// ---------------------------------------------------------------- 9. V4
function renderV4() {
  const tbody = document.getElementById("v4-table-body"); tbody.innerHTML = "";
  DATA.v4_tier1.forEach(r => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${r.condition}</td><td>${r.route_change_pct}</td><td>${r.activated}</td>
      <td class="num">${r.pdr_v4.toFixed(2)}%</td><td class="num">${r.pdr_static.toFixed(2)}%</td>`;
    tbody.appendChild(tr);
  });
}

// ---------------------------------------------------------------- 10. intervention
let intN = 100;
function renderIntervention() {
  pillGroup(document.getElementById("int-n"), [50, 75, 100].map(String), [50, 75, 100].indexOf(intN), i => { intN = [50, 75, 100][i]; drawIntervention(); });
  drawIntervention();
}
function drawIntervention() {
  const key = `olsr-${intN}`;
  const rows = DATA.ratesweep[key];
  legend(document.getElementById("int-legend"), [["PDR", "var(--olsr)"]]);
  lineChart(document.getElementById("chart-int-pdr"), { pdr: rows.map(d => ({ x: d.rate + "k", y: d.pdr })) }, { colors: { pdr: "var(--olsr)" }, unit: "%", yfmt: 0 });
  lineChart(document.getElementById("chart-int-airtime"), { air: rows.map(d => ({ x: d.rate + "k", y: d.gw_airtime })) }, { colors: { air: "var(--warn)" }, yfmt: 2 });
  const delta = rows[rows.length - 1].delta_pdr_pp;
  document.getElementById("int-delta").textContent = `${delta > 0 ? "+" : ""}${delta.toFixed(1)} pp`;
  document.getElementById("int-delta-label").textContent = `PDR change, N=${intN}, 16→4 kbps`;
}

// ---------------------------------------------------------------- 11. static control
function renderStaticControl() {
  legend(document.getElementById("sc-legend"), [["OLSR N=75", "var(--olsr)"], ["OLSR N=100", "#2f6fb0"], ["Static N=50", "var(--static)"]]);
  lineChart(document.getElementById("chart-static-control"), {
    "OLSR N=75": DATA.ratesweep["olsr-75"].map(d => ({ x: d.rate + "k", y: d.pdr })),
    "OLSR N=100": DATA.ratesweep["olsr-100"].map(d => ({ x: d.rate + "k", y: d.pdr })),
    "Static N=50": DATA.ratesweep["static-50"].map(d => ({ x: d.rate + "k", y: d.pdr }))
  }, { colors: { "OLSR N=75": "var(--olsr)", "OLSR N=100": "#2f6fb0", "Static N=50": "var(--static)" }, unit: "%", yfmt: 0 });

  const tbody = document.getElementById("diag-table-body"); tbody.innerHTML = "";
  DATA.diagnostic.forEach(r => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${r.rate} kbps</td><td class="num">${r.seed}</td><td class="num">${r.attributable_pct.toFixed(2)}%</td><td class="num">${r.residual_pct.toFixed(2)}%</td>`;
    tbody.appendChild(tr);
  });
}

// ---------------------------------------------------------------- init
async function main() {
  DATA = await fetch("data/final_research.json").then(r => r.json());
  renderHero();
  renderHealth();
  renderTopoSection();
  renderPerformance();
  renderTrafficLoad();
  renderBottleneck();
  renderHopChart();
  renderRetry();
  renderV4();
  renderIntervention();
  renderStaticControl();
  if (typeof initRealWorldSection === "function") initRealWorldSection(DATA);
  initNav();
}
document.addEventListener("DOMContentLoaded", main);
