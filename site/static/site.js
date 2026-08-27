// IoT Network Performance Lab -- STATIC (GitHub Pages) front end.
// This is the no-backend counterpart to dashboard/static/dashboard.js.
// Every number comes from ./data/*.json, which is a build-time export of
// the real results/*.csv files (see experiments/export_static_data.py) --
// nothing here is invented, and this file makes no network calls other
// than fetching those local JSON files and the local plot images.

Chart.defaults.color = "#8b93a7";
Chart.defaults.borderColor = "rgba(255,255,255,0.08)";
Chart.defaults.font.family = "-apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif";

const PROTOCOL_COLORS = { aodv: "#3b82f6", olsr: "#f59e0b", static: "#22d3ee" };
const PROTOCOL_LABELS = { aodv: "AODV", olsr: "OLSR", static: "Static" };

const METRICS = {
  pdr: { title: "Packet Delivery Ratio (PDR)", axisLabel: "PDR (%)", meanKey: "pdrMean", stdKey: "pdrStd", rowKey: "pdr", unit: "%", decimals: 2, scale: 1, underInvestigation: true,
    note: "AODV's PacketsSent denominator was found to scale with topology/network size in a way OLSR's and Static's do not (V2.7.1 validation report). AODV PDR here is provisional, not a settled comparison." },
  throughput: { title: "Throughput", axisLabel: "Throughput (kbps)", meanKey: "throughputMean", stdKey: "throughputStd", rowKey: "throughputKbps", unit: "kbps", decimals: 2, scale: 1, underInvestigation: false,
    note: "Received IP-layer bytes divided by the 70 s active traffic window (30 s-100 s). Not affected by the PacketsSent caveat." },
  delay: { title: "End-to-End Delay", axisLabel: "Delay (ms)", meanKey: "delayMean", stdKey: "delayStd", rowKey: "delaySec", unit: "ms", decimals: 2, scale: 1000, underInvestigation: false,
    note: "Packet-count-weighted average end-to-end delay across all received packets (FlowMonitor delaySum / received packets)." },
  loss: { title: "Packet Loss", axisLabel: "Packet loss (packets)", meanKey: "lossMean", stdKey: "lossStd", rowKey: "packetLoss", unit: "pkts", decimals: 1, scale: 1, underInvestigation: false,
    note: "PacketsSent - PacketsReceived. For AODV specifically this inherits the PacketsSent caveat -- see Validity section." },
};

const state = { protocol: "all", nodes: "all", trial: "all", metric: "pdr" };
const sortState = { summary: { key: "nodes", dir: 1 } };

let ALL_ROWS = [];
let ALL_SUMMARY = [];
let META = null;
let lastSummary = [];
let fullSummary = [];
let mainChart = null;
const scaleCharts = {};
const miniCharts = {};

function fmt(value, decimals) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return Number(value).toFixed(decimals);
}

// ---- Local "API" -- filters the pre-loaded JSON exactly like the Flask endpoints do ----
function localSummary({ protocol = "all", nodes = "all", trial = "all" } = {}) {
  let rows = ALL_ROWS;
  if (protocol !== "all") rows = rows.filter((r) => r.protocol === protocol);
  if (nodes !== "all") rows = rows.filter((r) => r.nodes === Number(nodes));
  if (trial !== "all") rows = rows.filter((r) => r.trial === Number(trial));
  if (protocol === "all" && nodes === "all" && trial === "all") return ALL_SUMMARY;

  const groups = {};
  rows.forEach((r) => { const k = r.protocol + "|" + r.nodes; (groups[k] = groups[k] || []).push(r); });
  const mean = (a) => a.reduce((s, v) => s + v, 0) / a.length;
  const std = (a) => { if (a.length < 2) return 0; const m = mean(a); return Math.sqrt(a.reduce((s, v) => s + (v - m) ** 2, 0) / (a.length - 1)); };
  return Object.values(groups).map((g) => ({
    protocol: g[0].protocol, nodes: g[0].nodes, trials: g.length,
    pdrMean: mean(g.map((r) => r.pdr)), pdrStd: std(g.map((r) => r.pdr)),
    throughputMean: mean(g.map((r) => r.throughputKbps)), throughputStd: std(g.map((r) => r.throughputKbps)),
    delayMean: mean(g.map((r) => r.delaySec)), delayStd: std(g.map((r) => r.delaySec)),
    lossMean: mean(g.map((r) => r.packetLoss)), lossStd: std(g.map((r) => r.packetLoss)),
  })).sort((a, b) => a.nodes - b.nodes || a.protocol.localeCompare(b.protocol));
}
function localRows({ protocol = "all", nodes = "all", trial = "all" } = {}) {
  let rows = ALL_ROWS;
  if (protocol !== "all") rows = rows.filter((r) => r.protocol === protocol);
  if (nodes !== "all") rows = rows.filter((r) => r.nodes === Number(nodes));
  if (trial !== "all") rows = rows.filter((r) => r.trial === Number(trial));
  return rows;
}

// ---- Chart.js error-bar plugin (no external plugin dependency) ----
const errorBarsPlugin = {
  id: "errorBars",
  afterDatasetsDraw(c) {
    const { ctx } = c;
    c.data.datasets.forEach((dataset, datasetIndex) => {
      if (!dataset.errorBars) return;
      const meta = c.getDatasetMeta(datasetIndex);
      const yScale = c.scales.y;
      meta.data.forEach((bar, index) => {
        const err = dataset.errorBars[index];
        const value = dataset.data[index];
        if (err == null || value == null) return;
        const x = bar.x;
        const yTop = yScale.getPixelForValue(value + err);
        const yBottom = yScale.getPixelForValue(Math.max(value - err, yScale.min));
        ctx.save();
        ctx.strokeStyle = "rgba(231,235,245,0.85)";
        ctx.lineWidth = 1.4;
        ctx.beginPath();
        ctx.moveTo(x, yTop); ctx.lineTo(x, yBottom);
        ctx.moveTo(x - 5, yTop); ctx.lineTo(x + 5, yTop);
        ctx.moveTo(x - 5, yBottom); ctx.lineTo(x + 5, yBottom);
        ctx.stroke();
        ctx.restore();
      });
    });
  },
};
Chart.register(errorBarsPlugin);

// ---------------- Meta / Methodology ----------------
function applyMeta(meta) {
  document.getElementById("stat-scenarios").textContent = meta.totalScenarios;
  document.getElementById("stat-trials").textContent = meta.totalTrials;
  document.getElementById("stat-protocols").textContent = meta.protocols.length;
  document.getElementById("stat-sizes").textContent = meta.networkSizes.length;
  document.getElementById("hero-scenarios").textContent = meta.totalScenarios;
  document.getElementById("hero-trials").textContent = meta.totalTrials;
  document.getElementById("hero-sizes").textContent = meta.networkSizes.length;
  document.getElementById("status-csv-count").textContent = meta.csvFilesDetected.length;
}
function applyMethodology(m) {
  const grid = document.getElementById("methodology-grid");
  const rows = [
    ["Simulator", m.simulator], ["Simulation file", m.simulationFile], ["Network", m.network],
    ["Gateway / Server", m.gatewayNote], ["Routing protocols", m.protocols.join(" | ")],
    ["Network sizes", m.networkSizes.join(", ") + " nodes"], ["Trials", m.trialsPerScenario],
    ["Deployment area", m.areaSize], ["Tx power", m.txPowerDbm + " dBm"], ["Static route range", m.txRangeNote],
    ["Packet size", m.packetSize], ["Traffic per source", m.trafficPerSource],
    ["Total simulation time", m.totalSimTime], ["Application start", m.applicationStart],
    ["Active traffic window", m.activeTrafficWindow],
  ];
  grid.innerHTML = "";
  rows.forEach(([term, def]) => {
    const dt = document.createElement("dt"); dt.textContent = term;
    const dd = document.createElement("dd"); dd.textContent = def;
    grid.appendChild(dt); grid.appendChild(dd);
  });
}

// ---------------- Performance section ----------------
function refreshPerformance() {
  lastSummary = localSummary(state);
  renderMainChart();
  renderSummaryTable();
}

function renderMainChart() {
  const metric = METRICS[state.metric];
  document.getElementById("chart-title").textContent = metric.title;
  document.getElementById("chart-note").textContent = metric.note;
  document.getElementById("chart-status-tag").style.display = metric.underInvestigation ? "inline-block" : "none";
  document.getElementById("chart-status-ok").style.display = metric.underInvestigation ? "none" : "inline-block";

  const nodeSizes = [...new Set(lastSummary.map((r) => r.nodes))].sort((a, b) => a - b);
  const protocols = [...new Set(lastSummary.map((r) => r.protocol))].sort();

  const datasets = protocols.map((proto) => {
    const byNode = {};
    lastSummary.filter((r) => r.protocol === proto).forEach((r) => { byNode[r.nodes] = r; });
    const data = nodeSizes.map((n) => (byNode[n] ? byNode[n][metric.meanKey] * metric.scale : null));
    const errorBars = nodeSizes.map((n) => (byNode[n] ? byNode[n][metric.stdKey] * metric.scale : null));
    return {
      label: PROTOCOL_LABELS[proto] + (metric.underInvestigation && proto === "aodv" ? " (under investigation)" : ""),
      data, errorBars, backgroundColor: PROTOCOL_COLORS[proto] || "#999", borderRadius: 4,
    };
  });

  const ctx = document.getElementById("main-chart").getContext("2d");
  if (mainChart) mainChart.destroy();
  mainChart = new Chart(ctx, {
    type: "bar",
    data: { labels: nodeSizes.map((n) => n + " nodes"), datasets },
    options: {
      responsive: true, animation: false,
      plugins: {
        legend: { position: "top", labels: { color: "#dbe2f0" } },
        tooltip: { callbacks: { label(item) {
          const ds = item.dataset;
          const err = ds.errorBars ? ds.errorBars[item.dataIndex] : null;
          const base = `${ds.label}: ${fmt(item.raw, metric.decimals)} ${metric.unit}`;
          return err != null ? `${base} (SD ${fmt(err, metric.decimals)})` : base;
        } } },
      },
      scales: {
        y: { beginAtZero: true, title: { display: true, text: metric.axisLabel }, grid: { color: "rgba(255,255,255,0.06)" } },
        x: { title: { display: true, text: "Network size" }, grid: { display: false } },
      },
    },
  });
}

function renderSummaryTable() {
  const data = sortRows(lastSummary, sortState.summary);
  const tbody = document.getElementById("summary-tbody");
  tbody.innerHTML = "";
  data.forEach((r) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${PROTOCOL_LABELS[r.protocol] || r.protocol}</td><td>${r.nodes}</td><td>${r.trials}</td>
      <td>${fmt(r.pdrMean, 2)} &plusmn; ${fmt(r.pdrStd, 2)}</td>
      <td>${fmt(r.throughputMean, 2)} &plusmn; ${fmt(r.throughputStd, 2)}</td>
      <td>${fmt(r.delayMean * 1000, 2)} &plusmn; ${fmt(r.delayStd * 1000, 2)}</td>
      <td>${fmt(r.lossMean, 1)} &plusmn; ${fmt(r.lossStd, 1)}</td>`;
    tbody.appendChild(tr);
  });
  updateSortIndicators("summary-table", sortState.summary);
}

function sortRows(rows, sortSpec) {
  const copy = [...rows];
  copy.sort((a, b) => {
    const av = a[sortSpec.key], bv = b[sortSpec.key];
    if (typeof av === "string") return av.localeCompare(bv) * sortSpec.dir;
    return (av - bv) * sortSpec.dir;
  });
  return copy;
}
function updateSortIndicators(tableId, sortSpec) {
  document.querySelectorAll(`#${tableId} thead th`).forEach((th) => {
    th.classList.remove("sort-asc", "sort-desc");
    if (th.dataset.sort === sortSpec.key) th.classList.add(sortSpec.dir === 1 ? "sort-asc" : "sort-desc");
  });
}
function attachSorting(tableId, sortSpec, renderFn) {
  document.querySelectorAll(`#${tableId} thead th`).forEach((th) => {
    if (!th.dataset.sort) return;
    th.addEventListener("click", () => {
      if (sortSpec.key === th.dataset.sort) sortSpec.dir *= -1;
      else { sortSpec.key = th.dataset.sort; sortSpec.dir = 1; }
      renderFn();
    });
  });
}

// ---------------- Generated research graphs (pre-generated PNG/SVG files) ----------------
function graphCaptionFromFilename(name) {
  const key = name.replace(/\.(png|svg)$/, "").replace(/_vs_nodes$/, "");
  const words = key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  return `${words} vs Network Size`;
}
const KNOWN_GRAPHS = ["pdr_vs_nodes", "throughput_vs_nodes", "packet_loss_vs_nodes", "delay_vs_nodes", "jitter_vs_nodes"];
async function loadResearchGraphs() {
  const grid = document.getElementById("research-graphs-grid");
  const note = document.getElementById("research-graphs-note");
  const found = [];
  for (const base of KNOWN_GRAPHS) {
    const name = base + ".png";
    // HEAD-less existence check via Image load; jitter is only included if analyze_results.py
    // actually detected a jitter column in the source CSVs and generated the file.
    // eslint-disable-next-line no-await-in-loop
    const exists = await new Promise((resolve) => {
      const img = new Image();
      img.onload = () => resolve(true);
      img.onerror = () => resolve(false);
      img.src = `results/plots/${name}`;
    });
    if (exists) found.push(name);
  }
  if (!found.length) {
    grid.innerHTML = "";
    note.innerHTML = "No generated plots found in this export.";
    return;
  }
  grid.innerHTML = found.map((name) => {
    const svgName = name.replace(/\.png$/, ".svg");
    return `<div class="research-graph-item">
      <img src="results/plots/${name}" alt="${graphCaptionFromFilename(name)}" loading="lazy">
      <div class="research-graph-caption">${graphCaptionFromFilename(name)} &middot; <a href="results/plots/${svgName}" download>SVG</a></div>
    </div>`;
  }).join("");
  note.innerHTML = `Static export &mdash; full statistics: <a href="results/csv/statistics.csv" download>statistics.csv</a> (if included) or browse <a href="results/csv/">results/csv/</a>.`;
}

// ---------------- Protocols + Scaling ----------------
function loadFullSummary() {
  fullSummary = localSummary({ protocol: "all", nodes: "all", trial: "all" });
  renderProtocolCards();
  renderScalingCharts();
}

function renderProtocolCards() {
  ["aodv", "olsr", "static"].forEach((key) => {
    const rows = fullSummary.filter((r) => r.protocol === key);
    if (!rows.length) return;
    const avg = (field) => rows.reduce((s, r) => s + r[field], 0) / rows.length;
    const box = document.getElementById(`protocol-metrics-${key}`);
    box.innerHTML = `
      <div><span class="metric-label">Avg PDR</span><span class="metric-value">${fmt(avg("pdrMean"), 1)}%</span></div>
      <div><span class="metric-label">Avg Throughput</span><span class="metric-value">${fmt(avg("throughputMean"), 1)} kbps</span></div>
      <div><span class="metric-label">Avg Delay</span><span class="metric-value">${fmt(avg("delayMean") * 1000, 1)} ms</span></div>
      <div><span class="metric-label">Avg Loss</span><span class="metric-value">${fmt(avg("lossMean"), 0)} pkts</span></div>`;

    const nodeSizes = rows.map((r) => r.nodes).sort((a, b) => a - b);
    const byNode = {}; rows.forEach((r) => { byNode[r.nodes] = r; });
    const ctx = document.getElementById(`mini-chart-${key}`).getContext("2d");
    if (miniCharts[key]) miniCharts[key].destroy();
    miniCharts[key] = new Chart(ctx, {
      type: "line",
      data: { labels: nodeSizes, datasets: [{ data: nodeSizes.map((n) => byNode[n].pdrMean), borderColor: PROTOCOL_COLORS[key], backgroundColor: PROTOCOL_COLORS[key], tension: 0.3, pointRadius: 3, fill: false }] },
      options: {
        responsive: true, animation: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (i) => `PDR: ${fmt(i.raw, 1)}%` } } },
        scales: { y: { display: true, beginAtZero: true, ticks: { display: false }, grid: { display: false } }, x: { display: true, ticks: { color: "#8b93a7", font: { size: 10 } }, grid: { display: false } } },
      },
    });
  });
}

function renderScalingCharts() {
  const nodeSizes = [...new Set(fullSummary.map((r) => r.nodes))].sort((a, b) => a - b);
  const protocols = ["aodv", "olsr", "static"];
  Object.entries(METRICS).forEach(([metricKey, metric]) => {
    const canvas = document.getElementById(`scale-${metricKey}`);
    if (!canvas) return;
    const datasets = protocols.map((key) => {
      const rows = fullSummary.filter((r) => r.protocol === key);
      const byNode = {}; rows.forEach((r) => { byNode[r.nodes] = r; });
      return { label: PROTOCOL_LABELS[key], data: nodeSizes.map((n) => (byNode[n] ? byNode[n][metric.meanKey] * metric.scale : null)), borderColor: PROTOCOL_COLORS[key], backgroundColor: PROTOCOL_COLORS[key], tension: 0.3, pointRadius: 3, fill: false };
    });
    if (scaleCharts[metricKey]) scaleCharts[metricKey].destroy();
    scaleCharts[metricKey] = new Chart(canvas.getContext("2d"), {
      type: "line",
      data: { labels: nodeSizes.map((n) => n + " nodes"), datasets },
      options: {
        responsive: true, animation: false,
        plugins: { legend: { position: "bottom", labels: { color: "#8b93a7", boxWidth: 10, font: { size: 11 } } } },
        scales: { y: { beginAtZero: true, title: { display: true, text: metric.axisLabel, font: { size: 11 } }, grid: { color: "rgba(255,255,255,0.06)" } }, x: { grid: { display: false } } },
      },
    });
  });
}

// ---------------- Trial Analysis ----------------
function refreshTrials() {
  const protocol = document.getElementById("trial-protocol").value;
  const nodes = document.getElementById("trial-nodes").value;
  const rows = localRows({ protocol, nodes, trial: "all" });

  const tbody = document.getElementById("trial-tbody");
  tbody.innerHTML = "";
  [...rows].sort((a, b) => a.trial - b.trial).forEach((r) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>Trial ${r.trial}</td><td>${fmt(r.pdr, 2)}</td><td>${fmt(r.throughputKbps, 2)}</td><td>${fmt(r.delaySec * 1000, 2)}</td><td>${r.packetLoss}</td>`;
    tbody.appendChild(tr);
  });

  renderStatsTable("trial-stats", rows, [
    { key: "pdr", label: "PDR (%)", decimals: 2 },
    { key: "throughputKbps", label: "Throughput (kbps)", decimals: 2 },
    { key: "delaySec", label: "Delay (ms)", decimals: 2, scale: 1000 },
    { key: "packetLoss", label: "Packet loss (pkts)", decimals: 1 },
  ]);
}

function computeStats(values) {
  const n = values.length;
  const mean = values.reduce((a, b) => a + b, 0) / n;
  const variance = n > 1 ? values.reduce((s, v) => s + (v - mean) ** 2, 0) / (n - 1) : 0;
  return { mean, std: Math.sqrt(variance), min: Math.min(...values), max: Math.max(...values) };
}
function renderStatsTable(containerId, rows, fields) {
  const container = document.getElementById(containerId);
  if (!rows.length) { container.innerHTML = "<p class='chart-note'>No data for this selection.</p>"; return; }
  let html = `<table class="table-card glass" style="width:100%;"><thead><tr><th>Metric</th><th>Mean</th><th>Std dev</th><th>Min</th><th>Max</th></tr></thead><tbody>`;
  fields.forEach((f) => {
    const scale = f.scale || 1;
    const values = rows.map((r) => r[f.key] * scale);
    const s = computeStats(values);
    html += `<tr><td>${f.label}</td><td>${fmt(s.mean, f.decimals)}</td><td>${fmt(s.std, f.decimals)}</td><td>${fmt(s.min, f.decimals)}</td><td>${fmt(s.max, f.decimals)}</td></tr>`;
  });
  html += "</tbody></table>";
  container.innerHTML = html;
}

// ---------------- Raw Data Explorer ----------------
function loadFileList() {
  const select = document.getElementById("file-select");
  select.innerHTML = "";
  META.csvFilesDetected.forEach((filename) => {
    const [protocol, nodesExt] = filename.replace(".csv", "").split("_");
    const nodes = Number(nodesExt);
    const rows = ALL_ROWS.filter((r) => r.sourceFile === filename);
    const opt = document.createElement("option");
    opt.value = filename;
    opt.textContent = `${filename} -- ${PROTOCOL_LABELS[protocol] || protocol}, ${nodes} nodes, ${rows.length} trials`;
    select.appendChild(opt);
  });
  if (META.csvFilesDetected.length) loadFileDetail(META.csvFilesDetected[0]);
}

function loadFileDetail(filename) {
  document.getElementById("download-link").href = `results/csv/${encodeURIComponent(filename)}`;
  const rows = ALL_ROWS.filter((r) => r.sourceFile === filename);

  const metaBox = document.getElementById("file-meta");
  const first = rows[0] || {};
  metaBox.innerHTML = `
    <div class="stat-chip glass"><div class="kpi-value">${PROTOCOL_LABELS[first.protocol] ?? "-"}</div><div class="kpi-label">Protocol</div></div>
    <div class="stat-chip glass"><div class="kpi-value">${first.nodes ?? "-"}</div><div class="kpi-label">Nodes</div></div>
    <div class="stat-chip glass"><div class="kpi-value">${rows.length}</div><div class="kpi-label">Trials in file</div></div>
    <div class="stat-chip glass"><div class="kpi-value">9</div><div class="kpi-label">Columns</div></div>`;

  const tbody = document.getElementById("raw-tbody");
  tbody.innerHTML = "";
  rows.forEach((r) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${PROTOCOL_LABELS[r.protocol]}</td><td>${r.nodes}</td><td>${r.trial}</td>
      <td>${r.packetsSent}</td><td>${r.packetsReceived}</td><td>${r.packetLoss}</td>
      <td>${fmt(r.pdr, 2)}</td><td>${fmt(r.throughputKbps, 2)}</td><td>${fmt(r.delaySec, 4)}</td>`;
    tbody.appendChild(tr);
  });

  renderStatsTable("raw-stats", rows, [
    { key: "pdr", label: "PDR (%)", decimals: 2 },
    { key: "throughputKbps", label: "Throughput (kbps)", decimals: 2 },
    { key: "delaySec", label: "Delay (ms)", decimals: 2, scale: 1000 },
    { key: "packetLoss", label: "Packet loss (pkts)", decimals: 1 },
  ]);
}

// ---------------- Interactive topology ----------------
function bootstrapTopology() {
  TopologyEngine.init({
    meta: { networkSizes: META.networkSizes, protocols: META.protocols, trials: META.trials },
    getRow: async (protocol, nodes, seed) => localRows({ protocol, nodes, trial: seed })[0] || null,
  });
}

// ---------------- Nav / scrollspy / mobile menu ----------------
function setupNav() {
  const links = document.querySelectorAll(".nav-link");
  const sections = [...links].map((l) => document.getElementById(l.dataset.section)).filter(Boolean);
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => { if (entry.isIntersecting) links.forEach((l) => l.classList.toggle("active", l.dataset.section === entry.target.id)); });
  }, { rootMargin: "-40% 0px -55% 0px" });
  sections.forEach((s) => observer.observe(s));
  const sidebar = document.getElementById("sidebar");
  document.getElementById("menu-toggle").addEventListener("click", () => sidebar.classList.toggle("open"));
  links.forEach((l) => l.addEventListener("click", () => sidebar.classList.remove("open")));
}

// ---------------- Filters wiring ----------------
function attachFilters() {
  document.getElementById("filter-protocol").addEventListener("change", (e) => { state.protocol = e.target.value; refreshPerformance(); });
  document.getElementById("filter-nodes").addEventListener("change", (e) => { state.nodes = e.target.value; refreshPerformance(); });
  document.getElementById("filter-trial").addEventListener("change", (e) => { state.trial = e.target.value; refreshPerformance(); });
  document.querySelectorAll("#metric-tabs .tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#metric-tabs .tab").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.metric = btn.dataset.metric;
      renderMainChart();
    });
  });
  document.querySelectorAll("[data-jump]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.getElementById("filter-protocol").value = btn.dataset.protocol;
      state.protocol = btn.dataset.protocol;
      refreshPerformance();
      document.getElementById(btn.dataset.jump).scrollIntoView({ behavior: "smooth" });
    });
  });
  document.getElementById("trial-protocol").addEventListener("change", refreshTrials);
  document.getElementById("trial-nodes").addEventListener("change", refreshTrials);
  document.getElementById("file-select").addEventListener("change", (e) => loadFileDetail(e.target.value));
}

// Real-World section (realworld.js) fetches "/api/summary" on Flask; on the
// static site it must read the same locally-loaded rows instead. realworld.js
// calls this once on DOMContentLoaded (before our own JSON fetches may have
// resolved), so it awaits `dataReadyPromise` rather than reading ALL_ROWS directly.
let resolveDataReady;
const dataReadyPromise = new Promise((resolve) => { resolveDataReady = resolve; });
window.rwFetchSummary = async (protocol) => {
  await dataReadyPromise;
  return localSummary({ protocol, nodes: "all", trial: "all" });
};

function renderSigmoidSection(data) {
  const { meta, rows } = data;
  document.getElementById("sigmoid-note").textContent = meta.note;
  document.getElementById("sigmoid-equation").textContent = meta.equation;
  const proxies = document.getElementById("sigmoid-proxies");
  proxies.innerHTML = "";
  meta.proxies.forEach((p) => {
    const li = document.createElement("li");
    li.textContent = p;
    proxies.appendChild(li);
  });

  const card = document.getElementById("sigmoid-table-card");
  if (!rows.length) { card.style.display = "none"; return; }
  card.style.display = "";
  const tbody = document.getElementById("sigmoid-tbody");
  tbody.innerHTML = "";
  rows.forEach((r) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${PROTOCOL_LABELS[r.protocol] || r.protocol}</td><td>${r.nodes}</td><td>${r.trafficCondition}</td>
      <td>${fmt(r.pdr, 2)}</td><td>${fmt(r.throughputKbps, 2)}</td><td>${fmt(r.delaySec * 1000, 2)}</td>
      <td>${fmt(r.jitterSec * 1000, 2)}</td><td>${fmt(r.hopCount, 2)}</td><td>${r.hopCountMethod}</td>
      <td>${r.routingOverheadPackets}</td>`;
    tbody.appendChild(tr);
  });
}

// ================================================================
// V3 Phase 1: expanded matrix (results/v3-ext/, static export at
// data/v3ext-*.json via experiments/export_static_data.py). Separate
// dataset from the V2.7 data above and from the Sigmoid pilot below --
// see docs/v3-experiment-framework.md's "Four tracks" table. Filters
// run entirely client-side against the pre-aggregated static JSON --
// no backend, same numbers the Flask dashboard's /api/v3ext/* endpoints
// serve live.
// ================================================================
const V3EXT_METRICS = {
  pdr: { title: "Packet Delivery Ratio (PDR)", axisLabel: "PDR (%)", key: "pdr", unit: "%", decimals: 2, scale: 1 },
  throughput: { title: "Throughput", axisLabel: "Throughput (kbps)", key: "throughput", unit: "kbps", decimals: 2, scale: 1 },
  delay: { title: "End-to-End Delay", axisLabel: "Delay (ms)", key: "delay", unit: "ms", decimals: 2, scale: 1000 },
  jitter: { title: "Jitter", axisLabel: "Jitter (ms)", key: "jitter", unit: "ms", decimals: 2, scale: 1000 },
};

let ALL_V3EXT_ROWS = [];
let ALL_V3EXT_SUMMARY = [];
let V3EXT_META = null;
const v3extState = { nodes: "all", traffic: "all", mobility: "all", routing: "all", duration: "all", metric: "pdr" };
const v3extSort = { key: "nodes", dir: 1 };
let v3extSummary = [];
let v3extChart = null;

function localV3extSummary({ nodes = "all", traffic = "all", mobility = "all", routing = "all", duration = "all" } = {}) {
  return ALL_V3EXT_SUMMARY.filter((r) =>
    (nodes === "all" || r.nodes === Number(nodes)) &&
    (traffic === "all" || r.traffic === traffic.toLowerCase()) &&
    (mobility === "all" || r.mobility === mobility.toLowerCase()) &&
    (routing === "all" || r.protocol === routing.toLowerCase()) &&
    (duration === "all" || r.duration === Number(duration))
  );
}
function localV3extRows({ nodes = "all", traffic = "all", mobility = "all", routing = "all", duration = "all" } = {}) {
  return ALL_V3EXT_ROWS.filter((r) =>
    (nodes === "all" || r.nodes === Number(nodes)) &&
    (traffic === "all" || r.traffic === traffic.toLowerCase()) &&
    (mobility === "all" || r.mobility === mobility.toLowerCase()) &&
    (routing === "all" || r.protocol === routing.toLowerCase()) &&
    (duration === "all" || r.duration === Number(duration))
  );
}

function loadV3extMeta() {
  const fill = (id, values) => {
    const sel = document.getElementById(id);
    sel.innerHTML = `<option value="all">All</option>` + values.map((v) => `<option value="${v}">${v}</option>`).join("");
  };
  fill("v3ext-filter-nodes", V3EXT_META.networkSizes);
  fill("v3ext-filter-traffic", V3EXT_META.trafficLevels);
  fill("v3ext-filter-mobility", V3EXT_META.mobilityModes);
  fill("v3ext-filter-duration", V3EXT_META.durations);
  const routingSel = document.getElementById("v3ext-filter-routing");
  routingSel.innerHTML = `<option value="all">All (compare protocols)</option>` +
    V3EXT_META.protocols.map((p) => `<option value="${p}">${PROTOCOL_LABELS[p] || p}</option>`).join("");
}

function refreshV3ext() {
  v3extSummary = localV3extSummary(v3extState);
  renderV3extChart();
  renderV3extTable();
  renderV3extKpis();
  renderV3extSecondaryMetrics();
  renderV3extRawTable();
}

function renderV3extChart() {
  const metric = V3EXT_METRICS[v3extState.metric];
  document.getElementById("v3ext-chart-title").textContent = metric.title + " vs. Network Size";
  document.getElementById("v3ext-chart-note").textContent =
    "Each point is the mean across whatever seeds are present for that (protocol, node count) cell under the current filters.";

  const nodeSizes = [...new Set(v3extSummary.map((r) => r.nodes))].sort((a, b) => a - b);
  const protocols = [...new Set(v3extSummary.map((r) => r.protocol))].sort();

  const datasets = protocols.map((proto) => {
    const byNode = {};
    v3extSummary.filter((r) => r.protocol === proto).forEach((r) => { (byNode[r.nodes] = byNode[r.nodes] || []).push(r); });
    const data = nodeSizes.map((n) => {
      const cells = byNode[n];
      if (!cells) return null;
      const vals = cells.map((c) => c[`${metric.key}Mean`] * metric.scale);
      return vals.reduce((a, b) => a + b, 0) / vals.length;
    });
    return {
      label: PROTOCOL_LABELS[proto] || proto, data,
      borderColor: PROTOCOL_COLORS[proto] || "#999",
      backgroundColor: (PROTOCOL_COLORS[proto] || "#999") + "33",
      tension: 0.25, pointRadius: 4,
    };
  });

  const ctx = document.getElementById("v3ext-chart").getContext("2d");
  if (v3extChart) v3extChart.destroy();
  v3extChart = new Chart(ctx, {
    type: "line",
    data: { labels: nodeSizes.map((n) => n + " nodes"), datasets },
    options: {
      responsive: true, animation: false,
      plugins: {
        legend: { position: "top", labels: { color: "#dbe2f0" } },
        tooltip: { callbacks: { label(item) { return `${item.dataset.label}: ${fmt(item.raw, metric.decimals)} ${metric.unit}`; } } },
      },
      scales: {
        y: { beginAtZero: true, title: { display: true, text: metric.axisLabel }, grid: { color: "rgba(255,255,255,0.06)" } },
        x: { title: { display: true, text: "Network size" }, grid: { display: false } },
      },
    },
  });
}

function renderV3extTable() {
  const data = sortRows(v3extSummary, v3extSort);
  const tbody = document.getElementById("v3ext-summary-tbody");
  tbody.innerHTML = "";
  if (!data.length) {
    tbody.innerHTML = `<tr><td colspan="16" class="empty-state">No data available for this configuration.</td></tr>`;
    updateSortIndicators("v3ext-summary-table", v3extSort);
    return;
  }
  data.forEach((r) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${PROTOCOL_LABELS[r.protocol] || r.protocol}</td><td>${r.nodes}</td><td>${r.traffic}</td><td>${r.mobility}</td>
      <td>${r.duration}</td><td>${r.n}</td>
      <td>${fmt(r.pdrMean, 2)} (n=${r.n})</td><td>${fmt(r.throughputMean, 2)}</td>
      <td>${fmt(r.delayMean * 1000, 2)}</td><td>${fmt(r.jitterMean * 1000, 2)}</td>
      <td>${fmt(r.packetLossMean, 1)}</td><td>${fmt(r.routingOverheadMean, 1)}</td>
      <td>${fmt(r.hopCountMean, 2)} (${r.hopCountMethod})</td><td>${fmt(r.pathChangesMean, 1)}</td>
      <td>${fmt(r.avgLinkUtilMean, 4)}</td><td>${fmt(r.maxLinkUtilMean, 4)}</td>
    `;
    tbody.appendChild(tr);
  });
  updateSortIndicators("v3ext-summary-table", v3extSort);
}

function renderV3extKpis() {
  const els = {
    throughput: document.getElementById("v3ext-kpi-throughput"),
    pdr: document.getElementById("v3ext-kpi-pdr"),
    delay: document.getElementById("v3ext-kpi-delay"),
    jitter: document.getElementById("v3ext-kpi-jitter"),
  };
  if (!v3extSummary.length) {
    Object.values(els).forEach((el) => (el.textContent = "No data"));
    document.getElementById("v3ext-kpi-note").textContent = "No data available for this configuration.";
    return;
  }
  const avg = (key) => v3extSummary.reduce((s, r) => s + r[key], 0) / v3extSummary.length;
  els.throughput.textContent = fmt(avg("throughputMean"), 2);
  els.pdr.textContent = fmt(avg("pdrMean"), 2);
  els.delay.textContent = fmt(avg("delayMean") * 1000, 2);
  els.jitter.textContent = fmt(avg("jitterMean") * 1000, 2);
  const n = v3extSummary.reduce((s, r) => s + r.n, 0);
  document.getElementById("v3ext-kpi-note").textContent =
    v3extSummary.length === 1
      ? `Single matching cell -- n=${v3extSummary[0].n} seed(s).`
      : `Averaged across ${v3extSummary.length} matching cells (${n} seed-runs total). Narrow the filters above for an exact single-condition reading.`;
}

function renderV3extSecondaryMetrics() {
  const ids = ["v3ext-nm-loss", "v3ext-nm-overhead", "v3ext-nm-hopcount", "v3ext-nm-pathchanges", "v3ext-lp-avg", "v3ext-lp-max"];
  if (!v3extSummary.length) {
    ids.forEach((id) => { document.getElementById(id).textContent = "No data"; });
    return;
  }
  const avg = (key) => v3extSummary.reduce((s, r) => s + r[key], 0) / v3extSummary.length;
  document.getElementById("v3ext-nm-loss").textContent = fmt(avg("packetLossMean"), 1);
  document.getElementById("v3ext-nm-overhead").textContent = fmt(avg("routingOverheadMean"), 1);
  document.getElementById("v3ext-nm-hopcount").textContent = fmt(avg("hopCountMean"), 2);
  document.getElementById("v3ext-nm-pathchanges").textContent = fmt(avg("pathChangesMean"), 1);
  document.getElementById("v3ext-lp-avg").textContent = fmt(avg("avgLinkUtilMean") * 100, 3) + "%";
  document.getElementById("v3ext-lp-max").textContent = fmt(avg("maxLinkUtilMean") * 100, 3) + "%";
}

function renderV3extRawTable() {
  const data = sortRows(localV3extRows(v3extState), v3extSort);
  const tbody = document.getElementById("v3ext-raw-tbody");
  tbody.innerHTML = "";
  if (!data.length) {
    tbody.innerHTML = `<tr><td colspan="16" class="empty-state">No data available for this configuration.</td></tr>`;
    return;
  }
  data.forEach((r) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${r.nodes}</td><td>${r.traffic}</td><td>${r.mobility}</td><td>${PROTOCOL_LABELS[r.protocol] || r.protocol}</td>
      <td>${r.seed}</td><td>${r.duration}</td><td>${fmt(r.throughputKbps, 2)}</td><td>${fmt(r.delaySec * 1000, 2)}</td>
      <td>${fmt(r.jitterSec * 1000, 2)}</td><td>${fmt(r.pdr, 2)}</td><td>${r.packetLoss}</td>
      <td>${r.routingOverheadPackets}</td><td>${fmt(r.hopCount, 2)} (${r.hopCountMethod})</td><td>${r.pathChanges}</td>
      <td>${fmt(r.avgLinkUtilization, 4)}</td><td>${fmt(r.maxLinkUtilization, 4)}</td>
    `;
    tbody.appendChild(tr);
  });
}

function attachV3extFilters() {
  const onChange = () => refreshV3ext();
  document.getElementById("v3ext-filter-nodes").addEventListener("change", (e) => { v3extState.nodes = e.target.value; onChange(); });
  document.getElementById("v3ext-filter-traffic").addEventListener("change", (e) => { v3extState.traffic = e.target.value; onChange(); });
  document.getElementById("v3ext-filter-mobility").addEventListener("change", (e) => { v3extState.mobility = e.target.value; onChange(); });
  document.getElementById("v3ext-filter-routing").addEventListener("change", (e) => { v3extState.routing = e.target.value; onChange(); });
  document.getElementById("v3ext-filter-duration").addEventListener("change", (e) => { v3extState.duration = e.target.value; onChange(); });
  document.querySelectorAll("#v3ext-metric-tabs .tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#v3ext-metric-tabs .tab").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      v3extState.metric = btn.dataset.metric;
      renderV3extChart();
    });
  });
}

// ---------------- V3 Phase 1: Comparison Mode ----------------
const v3cmpState = { nodes: null, traffic: "medium", mobility: "static", duration: "300", metric: "pdr" };
let v3cmpChart = null;
const V3CMP_PROTOCOLS = ["aodv", "olsr", "static"];

function loadV3cmpMeta() {
  const fill = (id, values, selected) => {
    const sel = document.getElementById(id);
    sel.innerHTML = values.map((v) => `<option value="${v}">${v}</option>`).join("");
    if (selected != null && values.map(String).includes(String(selected))) sel.value = String(selected);
  };
  fill("v3cmp-filter-nodes", V3EXT_META.networkSizes, V3EXT_META.networkSizes.includes(50) ? 50 : V3EXT_META.networkSizes[0]);
  fill("v3cmp-filter-traffic", V3EXT_META.trafficLevels, V3EXT_META.trafficLevels.includes("medium") ? "medium" : V3EXT_META.trafficLevels[0]);
  fill("v3cmp-filter-mobility", V3EXT_META.mobilityModes, V3EXT_META.mobilityModes.includes("static") ? "static" : V3EXT_META.mobilityModes[0]);
  fill("v3cmp-filter-duration", V3EXT_META.durations, V3EXT_META.durations.map(String).includes("300") ? 300 : V3EXT_META.durations[0]);
  v3cmpState.nodes = document.getElementById("v3cmp-filter-nodes").value;
  v3cmpState.traffic = document.getElementById("v3cmp-filter-traffic").value;
  v3cmpState.mobility = document.getElementById("v3cmp-filter-mobility").value;
  v3cmpState.duration = document.getElementById("v3cmp-filter-duration").value;
}

function refreshV3cmp() {
  const rows = localV3extSummary({ nodes: v3cmpState.nodes, traffic: v3cmpState.traffic, mobility: v3cmpState.mobility, routing: "all", duration: v3cmpState.duration });
  renderV3cmpChart(rows);
}

function renderV3cmpChart(rows) {
  const metric = V3EXT_METRICS[v3cmpState.metric];
  const byProto = {};
  rows.forEach((r) => { byProto[r.protocol] = r; });
  const missing = V3CMP_PROTOCOLS.filter((p) => !byProto[p]);

  const canvas = document.getElementById("v3cmp-chart");
  const emptyEl = document.getElementById("v3cmp-empty");
  const missingNoteEl = document.getElementById("v3cmp-missing-note");

  if (rows.length === 0) {
    if (v3cmpChart) { v3cmpChart.destroy(); v3cmpChart = null; }
    canvas.style.display = "none";
    emptyEl.style.display = "block";
    missingNoteEl.textContent = "";
    return;
  }
  canvas.style.display = "block";
  emptyEl.style.display = "none";
  missingNoteEl.textContent = missing.length
    ? `No data available for this configuration: ${missing.map((p) => PROTOCOL_LABELS[p] || p).join(", ")}.`
    : "";

  const data = V3CMP_PROTOCOLS.map((p) => (byProto[p] ? byProto[p][`${metric.key}Mean`] * metric.scale : null));
  const ctx = canvas.getContext("2d");
  if (v3cmpChart) v3cmpChart.destroy();
  v3cmpChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: V3CMP_PROTOCOLS.map((p) => PROTOCOL_LABELS[p] || p),
      datasets: [{
        label: metric.title, data,
        backgroundColor: V3CMP_PROTOCOLS.map((p) => (PROTOCOL_COLORS[p] || "#999") + "cc"),
        borderColor: V3CMP_PROTOCOLS.map((p) => PROTOCOL_COLORS[p] || "#999"),
        borderWidth: 1,
      }],
    },
    options: {
      responsive: true, animation: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label(item) { return item.raw == null ? `${item.label}: no data` : `${fmt(item.raw, metric.decimals)} ${metric.unit}`; } } },
      },
      scales: {
        y: { beginAtZero: true, title: { display: true, text: metric.axisLabel }, grid: { color: "rgba(255,255,255,0.06)" } },
        x: { grid: { display: false } },
      },
    },
  });
}

function attachV3cmpFilters() {
  ["nodes", "traffic", "mobility", "duration"].forEach((key) => {
    document.getElementById(`v3cmp-filter-${key}`).addEventListener("change", (e) => { v3cmpState[key] = e.target.value; refreshV3cmp(); });
  });
  document.querySelectorAll("#v3cmp-metric-tabs .tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#v3cmp-metric-tabs .tab").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      v3cmpState.metric = btn.dataset.metric;
      refreshV3cmp();
    });
  });
}

function bootstrapV3ext() {
  loadV3extMeta();
  attachV3extFilters();
  attachSorting("v3ext-summary-table", v3extSort, renderV3extTable);
  attachSorting("v3ext-raw-table", v3extSort, renderV3extRawTable);
  refreshV3ext();
  if (V3EXT_META.networkSizes && V3EXT_META.networkSizes.length) {
    loadV3cmpMeta();
    attachV3cmpFilters();
    refreshV3cmp();
  }
}

(async function init() {
  const [rows, summary, meta, methodology, sigmoid, v3extRows, v3extSummaryData, v3extMeta] = await Promise.all([
    fetch("data/rows.json").then((r) => r.json()),
    fetch("data/summary.json").then((r) => r.json()),
    fetch("data/meta.json").then((r) => r.json()),
    fetch("data/methodology.json").then((r) => r.json()),
    fetch("data/sigmoid.json").then((r) => r.json()),
    fetch("data/v3ext-rows.json").then((r) => r.json()),
    fetch("data/v3ext-summary.json").then((r) => r.json()),
    fetch("data/v3ext-meta.json").then((r) => r.json()),
  ]);
  ALL_ROWS = rows; ALL_SUMMARY = summary; META = meta;
  ALL_V3EXT_ROWS = v3extRows; ALL_V3EXT_SUMMARY = v3extSummaryData; V3EXT_META = v3extMeta;
  resolveDataReady();

  attachFilters();
  attachSorting("summary-table", sortState.summary, renderSummaryTable);
  setupNav();
  applyMeta(META);
  applyMethodology(methodology);
  loadFullSummary();
  loadResearchGraphs();
  bootstrapTopology();
  renderSigmoidSection(sigmoid);
  refreshPerformance();
  refreshTrials();
  loadFileList();
  bootstrapV3ext();
})();
