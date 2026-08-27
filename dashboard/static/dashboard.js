// IoT Network Performance Lab -- front end.
// All numeric data comes from /api/* (backed by pandas reading results/*.csv
// on every request) -- nothing here is a hardcoded experiment result.

Chart.defaults.color = "#8b93a7";
Chart.defaults.borderColor = "rgba(255,255,255,0.08)";
Chart.defaults.font.family = "-apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif";

const PROTOCOL_COLORS = { aodv: "#3b82f6", olsr: "#f59e0b", static: "#22d3ee" };
const PROTOCOL_LABELS = { aodv: "AODV", olsr: "OLSR", static: "Static" };

const METRICS = {
  pdr: {
    title: "Packet Delivery Ratio (PDR)",
    axisLabel: "PDR (%)",
    meanKey: "pdrMean", stdKey: "pdrStd", rowKey: "pdr",
    unit: "%", decimals: 2, scale: 1, underInvestigation: true,
    note: "AODV's PacketsSent denominator was found to scale with topology/network size in a way OLSR's and Static's do not (V2.7.1 validation report). AODV PDR here is provisional, not a settled comparison.",
  },
  throughput: {
    title: "Throughput",
    axisLabel: "Throughput (kbps)",
    meanKey: "throughputMean", stdKey: "throughputStd", rowKey: "throughputKbps",
    unit: "kbps", decimals: 2, scale: 1, underInvestigation: false,
    note: "Received IP-layer bytes divided by the 70 s active traffic window (30 s-100 s). Not affected by the PacketsSent caveat.",
  },
  delay: {
    title: "End-to-End Delay",
    axisLabel: "Delay (ms)",
    meanKey: "delayMean", stdKey: "delayStd", rowKey: "delaySec",
    unit: "ms", decimals: 2, scale: 1000, underInvestigation: false,
    note: "Packet-count-weighted average end-to-end delay across all received packets (FlowMonitor delaySum / received packets).",
  },
  loss: {
    title: "Packet Loss",
    axisLabel: "Packet loss (packets)",
    meanKey: "lossMean", stdKey: "lossStd", rowKey: "packetLoss",
    unit: "pkts", decimals: 1, scale: 1, underInvestigation: false,
    note: "PacketsSent - PacketsReceived. For AODV specifically this inherits the PacketsSent caveat -- see Validity section.",
  },
};

const state = { protocol: "all", nodes: "all", trial: "all", metric: "pdr" };
const sortState = { summary: { key: "nodes", dir: 1 }, raw: { key: "trial", dir: 1 } };

let lastSummary = [];       // filtered by global state, drives Performance chart + table
let fullSummary = [];       // unfiltered (all 12 rows), drives Protocols + Scaling sections
let lastRawFile = null;

let mainChart = null;
const scaleCharts = {};
const miniCharts = {};

function qs(params) {
  const p = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => p.set(k, v));
  return p.toString();
}
function fmt(value, decimals) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return Number(value).toFixed(decimals);
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
async function loadMeta() {
  const res = await fetch("/api/meta");
  const meta = await res.json();

  document.getElementById("stat-scenarios").textContent = meta.totalScenarios;
  document.getElementById("stat-trials").textContent = meta.totalTrials;
  document.getElementById("stat-protocols").textContent = meta.protocols.length;
  document.getElementById("stat-sizes").textContent = meta.networkSizes.length;
  document.getElementById("hero-scenarios").textContent = meta.totalScenarios;
  document.getElementById("hero-trials").textContent = meta.totalTrials;
  document.getElementById("hero-sizes").textContent = meta.networkSizes.length;
  document.getElementById("status-csv-count").textContent = meta.csvFilesDetected.length;

  if (meta.problems && meta.problems.length) {
    const panel = document.getElementById("problems-panel");
    const list = document.getElementById("problems-list");
    list.innerHTML = "";
    meta.problems.forEach((msg) => {
      const li = document.createElement("li");
      li.textContent = msg;
      list.appendChild(li);
    });
    panel.style.display = "block";
  }
}

async function loadMethodology() {
  const res = await fetch("/api/methodology");
  const m = await res.json();
  const grid = document.getElementById("methodology-grid");
  const rows = [
    ["Simulator", m.simulator],
    ["Simulation file", m.simulationFile],
    ["Network", m.network],
    ["Gateway / Server", m.gatewayNote],
    ["Routing protocols", m.protocols.join(" | ")],
    ["Network sizes", m.networkSizes.join(", ") + " nodes"],
    ["Trials", m.trialsPerScenario],
    ["Deployment area", m.areaSize],
    ["Tx power", m.txPowerDbm + " dBm"],
    ["Static route range", m.txRangeNote],
    ["Packet size", m.packetSize],
    ["Traffic per source", m.trafficPerSource],
    ["Total simulation time", m.totalSimTime],
    ["Application start", m.applicationStart],
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
async function refreshPerformance() {
  const params = { protocol: state.protocol, nodes: state.nodes, trial: state.trial };
  const res = await fetch("/api/summary?" + qs(params));
  lastSummary = await res.json();
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
    const key = proto.toLowerCase();
    return {
      label: PROTOCOL_LABELS[key] + (metric.underInvestigation && key === "aodv" ? " (under investigation)" : ""),
      data, errorBars,
      backgroundColor: PROTOCOL_COLORS[key] || "#999",
      borderRadius: 4,
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
        tooltip: {
          callbacks: {
            label(item) {
              const ds = item.dataset;
              const err = ds.errorBars ? ds.errorBars[item.dataIndex] : null;
              const base = `${ds.label}: ${fmt(item.raw, metric.decimals)} ${metric.unit}`;
              return err != null ? `${base} (SD ${fmt(err, metric.decimals)})` : base;
            },
          },
        },
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
      <td>${PROTOCOL_LABELS[r.protocol.toLowerCase()] || r.protocol}</td>
      <td>${r.nodes}</td>
      <td>${r.trials}</td>
      <td>${fmt(r.pdrMean, 2)} &plusmn; ${fmt(r.pdrStd, 2)}</td>
      <td>${fmt(r.throughputMean, 2)} &plusmn; ${fmt(r.throughputStd, 2)}</td>
      <td>${fmt(r.delayMean * 1000, 2)} &plusmn; ${fmt(r.delayStd * 1000, 2)}</td>
      <td>${fmt(r.lossMean, 1)} &plusmn; ${fmt(r.lossStd, 1)}</td>
    `;
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

// ---------------- Generated research graphs (analyze_results.py output) ----------------
// Captions are derived automatically from the filename (metric_vs_nodes.png)
// rather than a hardcoded per-file list, so a newly detected metric (e.g.
// jitter, if a future CSV schema includes it) gets a sensible caption
// without needing a code change here.
function graphCaptionFromFilename(name) {
  const key = name.replace(/\.(png|svg)$/, "").replace(/_vs_nodes$/, "");
  const words = key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  return `${words} vs Network Size`;
}

async function loadResearchGraphs() {
  const res = await fetch("/api/graphs");
  const data = await res.json();
  const grid = document.getElementById("research-graphs-grid");
  const note = document.getElementById("research-graphs-note");

  if (!data.graphs.length) {
    grid.innerHTML = "";
    note.innerHTML = "No generated plots found yet. Run <code>./experiments/run_and_analyze.sh</code> to create them.";
    return;
  }

  const svgSet = new Set(data.svgGraphs || []);
  grid.innerHTML = data.graphs
    .map((name) => {
      const svgName = name.replace(/\.png$/, ".svg");
      const svgLink = svgSet.has(svgName)
        ? ` &middot; <a href="/results/plots/${encodeURIComponent(svgName)}" download>SVG</a>`
        : "";
      return `
      <div class="research-graph-item">
        <img src="/results/plots/${encodeURIComponent(name)}" alt="${graphCaptionFromFilename(name)}" loading="lazy">
        <div class="research-graph-caption">${graphCaptionFromFilename(name)}${svgLink}</div>
      </div>
    `;
    })
    .join("");

  const when = data.generatedAt ? new Date(data.generatedAt * 1000).toLocaleString() : "unknown";
  note.innerHTML = data.statisticsAvailable
    ? `Generated ${when}. Full statistics: <a href="/download/statistics.csv">statistics.csv</a>.`
    : "statistics.csv not found -- graphs may be out of date.";
}

// ---------------- Protocols + Scaling (use full, unfiltered summary) ----------------
async function loadFullSummary() {
  const res = await fetch("/api/summary?" + qs({ protocol: "all", nodes: "all", trial: "all" }));
  fullSummary = await res.json();
  renderProtocolCards();
  renderScalingCharts();
}

function renderProtocolCards() {
  ["aodv", "olsr", "static"].forEach((key) => {
    const rows = fullSummary.filter((r) => r.protocol.toLowerCase() === key);
    if (!rows.length) return;
    const avg = (field) => rows.reduce((s, r) => s + r[field], 0) / rows.length;
    const box = document.getElementById(`protocol-metrics-${key}`);
    box.innerHTML = `
      <div><span class="metric-label">Avg PDR</span><span class="metric-value">${fmt(avg("pdrMean"), 1)}%</span></div>
      <div><span class="metric-label">Avg Throughput</span><span class="metric-value">${fmt(avg("throughputMean"), 1)} kbps</span></div>
      <div><span class="metric-label">Avg Delay</span><span class="metric-value">${fmt(avg("delayMean") * 1000, 1)} ms</span></div>
      <div><span class="metric-label">Avg Loss</span><span class="metric-value">${fmt(avg("lossMean"), 0)} pkts</span></div>
    `;

    const nodeSizes = rows.map((r) => r.nodes).sort((a, b) => a - b);
    const byNode = {}; rows.forEach((r) => { byNode[r.nodes] = r; });
    const ctx = document.getElementById(`mini-chart-${key}`).getContext("2d");
    if (miniCharts[key]) miniCharts[key].destroy();
    miniCharts[key] = new Chart(ctx, {
      type: "line",
      data: {
        labels: nodeSizes,
        datasets: [{
          data: nodeSizes.map((n) => byNode[n].pdrMean),
          borderColor: PROTOCOL_COLORS[key], backgroundColor: PROTOCOL_COLORS[key],
          tension: 0.3, pointRadius: 3, fill: false,
        }],
      },
      options: {
        responsive: true, animation: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (i) => `PDR: ${fmt(i.raw, 1)}%` } } },
        scales: {
          y: { display: true, beginAtZero: true, ticks: { display: false }, grid: { display: false } },
          x: { display: true, ticks: { color: "#8b93a7", font: { size: 10 } }, grid: { display: false } },
        },
      },
    });
  });
}

function renderScalingCharts() {
  const nodeSizes = [...new Set(fullSummary.map((r) => r.nodes))].sort((a, b) => a - b);
  const protocols = ["aodv", "olsr", "static"];

  Object.entries(METRICS).forEach(([metricKey, metric]) => {
    const canvasId = `scale-${metricKey}`;
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const datasets = protocols.map((key) => {
      const rows = fullSummary.filter((r) => r.protocol.toLowerCase() === key);
      const byNode = {}; rows.forEach((r) => { byNode[r.nodes] = r; });
      return {
        label: PROTOCOL_LABELS[key],
        data: nodeSizes.map((n) => (byNode[n] ? byNode[n][metric.meanKey] * metric.scale : null)),
        borderColor: PROTOCOL_COLORS[key], backgroundColor: PROTOCOL_COLORS[key],
        tension: 0.3, pointRadius: 3, fill: false,
      };
    });
    if (scaleCharts[metricKey]) scaleCharts[metricKey].destroy();
    scaleCharts[metricKey] = new Chart(canvas.getContext("2d"), {
      type: "line",
      data: { labels: nodeSizes.map((n) => n + " nodes"), datasets },
      options: {
        responsive: true, animation: false,
        plugins: { legend: { position: "bottom", labels: { color: "#8b93a7", boxWidth: 10, font: { size: 11 } } } },
        scales: {
          y: { beginAtZero: true, title: { display: true, text: metric.axisLabel, font: { size: 11 } }, grid: { color: "rgba(255,255,255,0.06)" } },
          x: { grid: { display: false } },
        },
      },
    });
  });
}

// ---------------- Trial Analysis ----------------
async function refreshTrials() {
  const protocol = document.getElementById("trial-protocol").value;
  const nodes = document.getElementById("trial-nodes").value;
  const res = await fetch("/api/rows?" + qs({ protocol, nodes, trial: "all" }));
  const rows = await res.json();

  const tbody = document.getElementById("trial-tbody");
  tbody.innerHTML = "";
  rows.sort((a, b) => a.trial - b.trial).forEach((r) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>Trial ${r.trial}</td>
      <td>${fmt(r.pdr, 2)}</td>
      <td>${fmt(r.throughputKbps, 2)}</td>
      <td>${fmt(r.delaySec * 1000, 2)}</td>
      <td>${r.packetLoss}</td>
    `;
    tbody.appendChild(tr);
  });

  renderStatsTable(
    "trial-stats",
    rows,
    [
      { key: "pdr", label: "PDR (%)", decimals: 2 },
      { key: "throughputKbps", label: "Throughput (kbps)", decimals: 2 },
      { key: "delaySec", label: "Delay (ms)", decimals: 2, scale: 1000 },
      { key: "packetLoss", label: "Packet loss (pkts)", decimals: 1 },
    ]
  );
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
  let html = `<table class="table-card glass" style="width:100%;"><thead><tr>
    <th>Metric</th><th>Mean</th><th>Std dev</th><th>Min</th><th>Max</th>
  </tr></thead><tbody>`;
  fields.forEach((f) => {
    const scale = f.scale || 1;
    const values = rows.map((r) => r[f.key] * scale);
    const s = computeStats(values);
    html += `<tr>
      <td>${f.label}</td>
      <td>${fmt(s.mean, f.decimals)}</td>
      <td>${fmt(s.std, f.decimals)}</td>
      <td>${fmt(s.min, f.decimals)}</td>
      <td>${fmt(s.max, f.decimals)}</td>
    </tr>`;
  });
  html += "</tbody></table>";
  container.innerHTML = html;
}

// ---------------- Raw Data Explorer ----------------
async function loadFileList() {
  const res = await fetch("/api/files");
  const files = await res.json();
  const select = document.getElementById("file-select");
  select.innerHTML = "";
  files.forEach((f) => {
    const opt = document.createElement("option");
    opt.value = f.filename;
    opt.textContent = f.error ? `${f.filename} (error)` : `${f.filename} -- ${PROTOCOL_LABELS[(f.protocol || "").toLowerCase()] || f.protocol}, ${f.nodes} nodes, ${f.trialCount} trials`;
    select.appendChild(opt);
  });
  if (files.length) await loadFileDetail(files[0].filename);
}

async function loadFileDetail(filename) {
  lastRawFile = filename;
  document.getElementById("download-link").href = "/download/" + encodeURIComponent(filename);
  const res = await fetch("/api/file/" + encodeURIComponent(filename));
  const data = await res.json();

  const metaBox = document.getElementById("file-meta");
  if (data.error) {
    metaBox.innerHTML = `<div class="stat-chip glass"><div class="kpi-value">!</div><div class="kpi-label">${data.error}</div></div>`;
  } else {
    const first = data.rows[0] || {};
    metaBox.innerHTML = `
      <div class="stat-chip glass"><div class="kpi-value">${first.RoutingProtocol ?? "-"}</div><div class="kpi-label">Protocol</div></div>
      <div class="stat-chip glass"><div class="kpi-value">${first.NumberOfNodes ?? "-"}</div><div class="kpi-label">Nodes</div></div>
      <div class="stat-chip glass"><div class="kpi-value">${data.rows.length}</div><div class="kpi-label">Trials in file</div></div>
      <div class="stat-chip glass"><div class="kpi-value">${data.columns.length}</div><div class="kpi-label">Columns</div></div>
    `;
  }

  const tbody = document.getElementById("raw-tbody");
  tbody.innerHTML = "";
  (data.rows || []).forEach((r) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${r.RoutingProtocol}</td><td>${r.NumberOfNodes}</td><td>${r.PosSeed}</td>
      <td>${r.PacketsSent}</td><td>${r.PacketsReceived}</td><td>${r.PacketLoss}</td>
      <td>${fmt(r.PDR, 2)}</td><td>${fmt(r.ThroughputKbps, 2)}</td><td>${fmt(r.AverageDelaySec, 4)}</td>
    `;
    tbody.appendChild(tr);
  });

  if (data.stats) {
    renderStatsTable(
      "raw-stats",
      (data.rows || []).map((r) => ({ pdr: r.PDR, throughputKbps: r.ThroughputKbps, delaySec: r.AverageDelaySec, packetLoss: r.PacketLoss })),
      [
        { key: "pdr", label: "PDR (%)", decimals: 2 },
        { key: "throughputKbps", label: "Throughput (kbps)", decimals: 2 },
        { key: "delaySec", label: "Delay (ms)", decimals: 2, scale: 1000 },
        { key: "packetLoss", label: "Packet loss (pkts)", decimals: 1 },
      ]
    );
  }
}

// ---------------- Topology (conceptual, static -- no invented coordinates) ----------------
// ---------------- Interactive topology (TopologyEngine, static/topology.js) ----------------
async function bootstrapTopology() {
  const metaRes = await fetch("/api/meta");
  const meta = await metaRes.json();
  TopologyEngine.init({
    meta: { networkSizes: meta.networkSizes, protocols: meta.protocols, trials: meta.trials },
    getRow: async (protocol, nodes, seed) => {
      const res = await fetch("/api/rows?" + qs({ protocol, nodes, trial: seed }));
      const rows = await res.json();
      return rows[0] || null;
    },
  });
}

// ---------------- Nav / scrollspy / mobile menu ----------------
function setupNav() {
  const links = document.querySelectorAll(".nav-link");
  const sections = [...links].map((l) => document.getElementById(l.dataset.section)).filter(Boolean);

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          links.forEach((l) => l.classList.toggle("active", l.dataset.section === entry.target.id));
        }
      });
    },
    { rootMargin: "-40% 0px -55% 0px" }
  );
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

// ---------------- V3 Phase 1: expanded matrix (results/v3-ext/, /api/v3ext/*) ----------------
// Separate dataset from V2's results/*.csv and from results/v3/ (a different
// study, Barabasi-Albert/risk-aware routing) and results/v28-sigmoid-pilot/
// (below) -- see docs/v3-experiment-framework.md.
const V3EXT_METRICS = {
  pdr: { title: "Packet Delivery Ratio (PDR)", axisLabel: "PDR (%)", key: "pdr", unit: "%", decimals: 2, scale: 1 },
  throughput: { title: "Throughput", axisLabel: "Throughput (kbps)", key: "throughput", unit: "kbps", decimals: 2, scale: 1 },
  delay: { title: "End-to-End Delay", axisLabel: "Delay (ms)", key: "delay", unit: "ms", decimals: 2, scale: 1000 },
  jitter: { title: "Jitter", axisLabel: "Jitter (ms)", key: "jitter", unit: "ms", decimals: 2, scale: 1000 },
  packetLoss: { title: "Packet Loss", axisLabel: "Packet loss (packets)", key: "packetLoss", unit: "pkts", decimals: 1, scale: 1 },
  routingOverhead: { title: "Routing Overhead (best-effort -- undercounts broadcast control traffic)", axisLabel: "Overhead (packets)", key: "routingOverhead", unit: "pkts", decimals: 1, scale: 1 },
  hopCount: { title: "Hop Count", axisLabel: "Hop count", key: "hopCount", unit: "hops", decimals: 2, scale: 1 },
  pathChanges: { title: "Path Changes", axisLabel: "Path changes", key: "pathChanges", unit: "", decimals: 1, scale: 1 },
  avgLinkUtil: { title: "Average Link Utilization", axisLabel: "Utilization (fraction)", key: "avgLinkUtil", unit: "", decimals: 4, scale: 1 },
  maxLinkUtil: { title: "Maximum Link Utilization (MLU)", axisLabel: "Utilization (fraction)", key: "maxLinkUtil", unit: "", decimals: 4, scale: 1 },
};

const v3extState = { nodes: "all", traffic: "all", mobility: "all", routing: "all", duration: "all", metric: "pdr" };
const v3extSort = { key: "nodes", dir: 1 };
let v3extSummary = [];
let v3extChart = null;

async function loadV3extMeta() {
  const res = await fetch("/api/v3ext/meta");
  const meta = await res.json();
  const fill = (id, values) => {
    const sel = document.getElementById(id);
    sel.innerHTML = `<option value="all">All</option>` + values.map((v) => `<option value="${v}">${v}</option>`).join("");
  };
  fill("v3ext-filter-nodes", meta.networkSizes);
  fill("v3ext-filter-traffic", meta.trafficLevels);
  fill("v3ext-filter-mobility", meta.mobilityModes);
  fill("v3ext-filter-duration", meta.durations);
  const routingSel = document.getElementById("v3ext-filter-routing");
  routingSel.innerHTML = `<option value="all">All (compare protocols)</option>` +
    meta.protocols.map((p) => `<option value="${p}">${PROTOCOL_LABELS[p] || p}</option>`).join("");
  return meta;
}

async function refreshV3ext() {
  const res = await fetch("/api/v3ext/summary?" + qs({
    nodes: v3extState.nodes, traffic: v3extState.traffic, mobility: v3extState.mobility,
    routing: v3extState.routing, duration: v3extState.duration,
  }));
  v3extSummary = await res.json();
  renderV3extChart();
  renderV3extTable();
  renderV3extKpis();
  renderV3extSecondaryMetrics();
}

function renderV3extChart() {
  const metric = V3EXT_METRICS[v3extState.metric];
  document.getElementById("v3ext-chart-title").textContent = metric.title + " vs. Network Size";
  document.getElementById("v3ext-chart-note").textContent =
    "Each point is the mean across whatever seeds are present for that (protocol, node count) cell under the current filters -- if multiple traffic/mobility cells match, the point averages across them too (the table below always lists every cell separately). Error bars are a 95% CI (Student's t) shown only for a single, unambiguous cell with n≥2 seeds.";

  const nodeSizes = [...new Set(v3extSummary.map((r) => r.nodes))].sort((a, b) => a - b);
  const protocols = [...new Set(v3extSummary.map((r) => r.protocol))].sort();

  const datasets = protocols.map((proto) => {
    const byNode = {};
    v3extSummary.filter((r) => r.protocol === proto).forEach((r) => {
      (byNode[r.nodes] = byNode[r.nodes] || []).push(r);
    });
    const data = nodeSizes.map((n) => {
      const cells = byNode[n];
      if (!cells) return null;
      const vals = cells.map((c) => c[`${metric.key}Mean`] * metric.scale);
      return vals.reduce((a, b) => a + b, 0) / vals.length;
    });
    const errorBars = nodeSizes.map((n) => {
      const cells = byNode[n];
      if (!cells || cells.length !== 1 || cells[0].n < 2) return null;
      const ci = cells[0][`${metric.key}Ci95`];
      return ci != null ? ci * metric.scale : null;
    });
    const key = proto.toLowerCase();
    return {
      label: PROTOCOL_LABELS[key] || proto,
      data, errorBars,
      borderColor: PROTOCOL_COLORS[key] || "#999",
      backgroundColor: (PROTOCOL_COLORS[key] || "#999") + "33",
      tension: 0.25,
      pointRadius: 4,
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
        tooltip: {
          callbacks: {
            label(item) {
              const ds = item.dataset;
              const err = ds.errorBars ? ds.errorBars[item.dataIndex] : null;
              const base = `${ds.label}: ${fmt(item.raw, metric.decimals)} ${metric.unit}`;
              return err != null ? `${base} (95% CI ±${fmt(err, metric.decimals)})` : base;
            },
          },
        },
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
  const ciTag = (mean, ci95, n, decimals) =>
    n < 2 || ci95 == null ? `${fmt(mean, decimals)} (n=${n})` : `${fmt(mean, decimals)} &plusmn; ${fmt(ci95, decimals)} (n=${n})`;
  data.forEach((r) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${PROTOCOL_LABELS[r.protocol.toLowerCase()] || r.protocol}</td>
      <td>${r.nodes}</td>
      <td>${r.traffic}</td>
      <td>${r.mobility}</td>
      <td>${r.duration}</td>
      <td>${r.n}</td>
      <td>${ciTag(r.pdrMean, r.pdrCi95, r.n, 2)}</td>
      <td>${ciTag(r.throughputMean, r.throughputCi95, r.n, 2)}</td>
      <td>${ciTag(r.delayMean * 1000, r.delayCi95 != null ? r.delayCi95 * 1000 : null, r.n, 2)}</td>
      <td>${ciTag(r.jitterMean * 1000, r.jitterCi95 != null ? r.jitterCi95 * 1000 : null, r.n, 2)}</td>
      <td>${ciTag(r.packetLossMean, r.packetLossCi95, r.n, 1)}</td>
      <td>${ciTag(r.routingOverheadMean, r.routingOverheadCi95, r.n, 1)}</td>
      <td>${fmt(r.hopCountMean, 2)} (${r.hopCountMethod})</td>
      <td>${ciTag(r.pathChangesMean, r.pathChangesCi95, r.n, 1)}</td>
      <td>${ciTag(r.avgLinkUtilMean, r.avgLinkUtilCi95, r.n, 4)}</td>
      <td>${ciTag(r.maxLinkUtilMean, r.maxLinkUtilCi95, r.n, 4)}</td>
    `;
    tbody.appendChild(tr);
  });
  updateSortIndicators("v3ext-summary-table", v3extSort);
}

function attachV3extFilters() {
  const onFilterChange = () => { refreshV3ext(); refreshV3extRaw(); };
  document.getElementById("v3ext-filter-nodes").addEventListener("change", (e) => { v3extState.nodes = e.target.value; onFilterChange(); });
  document.getElementById("v3ext-filter-traffic").addEventListener("change", (e) => { v3extState.traffic = e.target.value; onFilterChange(); });
  document.getElementById("v3ext-filter-mobility").addEventListener("change", (e) => { v3extState.mobility = e.target.value; onFilterChange(); });
  document.getElementById("v3ext-filter-routing").addEventListener("change", (e) => { v3extState.routing = e.target.value; onFilterChange(); });
  document.getElementById("v3ext-filter-duration").addEventListener("change", (e) => { v3extState.duration = e.target.value; onFilterChange(); });
  document.querySelectorAll("#v3ext-metric-tabs .tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#v3ext-metric-tabs .tab").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      v3extState.metric = btn.dataset.metric;
      renderV3extChart();
    });
  });
}

// KPI summary cards -- averaged across whatever v3extSummary rows match the
// current filters (a narrow-enough filter selects exactly one row, so the
// "average" is just that row's own values). Empty selection shows "--", per
// row, never a fabricated 0.
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

// Network Metrics + Link Performance tiles -- same averaging rule as the KPI
// cards above (average of whatever v3extSummary rows currently match the
// filters), just for the secondary metrics moved out of the main chart to
// keep it readable.
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

// ---------------- V3 Phase 1: Comparison Mode (AODV vs OLSR vs Static) ----------------
// Always locks node count / traffic / mobility / duration so protocols are
// only ever compared under identical conditions -- never mismatched ones.
const v3cmpState = { nodes: null, traffic: "medium", mobility: "static", duration: "300", metric: "pdr" };
let v3cmpChart = null;
const V3CMP_PROTOCOLS = ["aodv", "olsr", "static"];

async function loadV3cmpMeta(meta) {
  const fill = (id, values, selected) => {
    const sel = document.getElementById(id);
    sel.innerHTML = values.map((v) => `<option value="${v}">${v}</option>`).join("");
    if (selected != null && values.map(String).includes(String(selected))) sel.value = String(selected);
  };
  fill("v3cmp-filter-nodes", meta.networkSizes, meta.networkSizes.includes(50) ? 50 : meta.networkSizes[0]);
  fill("v3cmp-filter-traffic", meta.trafficLevels, meta.trafficLevels.includes("medium") ? "medium" : meta.trafficLevels[0]);
  fill("v3cmp-filter-mobility", meta.mobilityModes, meta.mobilityModes.includes("static") ? "static" : meta.mobilityModes[0]);
  fill("v3cmp-filter-duration", meta.durations, meta.durations.map(String).includes("300") ? 300 : meta.durations[0]);
  v3cmpState.nodes = document.getElementById("v3cmp-filter-nodes").value;
  v3cmpState.traffic = document.getElementById("v3cmp-filter-traffic").value;
  v3cmpState.mobility = document.getElementById("v3cmp-filter-mobility").value;
  v3cmpState.duration = document.getElementById("v3cmp-filter-duration").value;
}

async function refreshV3cmp() {
  const res = await fetch("/api/v3ext/summary?" + qs({
    nodes: v3cmpState.nodes, traffic: v3cmpState.traffic, mobility: v3cmpState.mobility,
    routing: "all", duration: v3cmpState.duration,
  }));
  const rows = await res.json();
  renderV3cmpChart(rows);
}

function renderV3cmpChart(rows) {
  const metric = V3EXT_METRICS[v3cmpState.metric];
  const byProto = {};
  rows.forEach((r) => { byProto[r.protocol.toLowerCase()] = r; });
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
  const errorBars = V3CMP_PROTOCOLS.map((p) => {
    const r = byProto[p];
    if (!r || r.n < 2) return null;
    const ci = r[`${metric.key}Ci95`];
    return ci != null ? ci * metric.scale : null;
  });

  const ctx = canvas.getContext("2d");
  if (v3cmpChart) v3cmpChart.destroy();
  v3cmpChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: V3CMP_PROTOCOLS.map((p) => PROTOCOL_LABELS[p] || p),
      datasets: [{
        label: metric.title,
        data, errorBars,
        backgroundColor: V3CMP_PROTOCOLS.map((p) => (PROTOCOL_COLORS[p] || "#999") + "cc"),
        borderColor: V3CMP_PROTOCOLS.map((p) => PROTOCOL_COLORS[p] || "#999"),
        borderWidth: 1,
      }],
    },
    options: {
      responsive: true, animation: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label(item) {
              const err = item.dataset.errorBars ? item.dataset.errorBars[item.dataIndex] : null;
              if (item.raw == null) return `${item.label}: no data`;
              const base = `${fmt(item.raw, metric.decimals)} ${metric.unit}`;
              return err != null ? `${base} (95% CI ±${fmt(err, metric.decimals)})` : base;
            },
          },
        },
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
    document.getElementById(`v3cmp-filter-${key}`).addEventListener("change", (e) => {
      v3cmpState[key] = e.target.value;
      refreshV3cmp();
    });
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

// ---------------- V3 Phase 1: Raw Data table (per-run rows, /api/v3ext/rows) ----------------
const v3extRawSort = { key: "nodes", dir: 1 };
let v3extRawRows = [];

async function refreshV3extRaw() {
  const res = await fetch("/api/v3ext/rows?" + qs({
    nodes: v3extState.nodes, traffic: v3extState.traffic, mobility: v3extState.mobility,
    routing: v3extState.routing, duration: v3extState.duration,
  }));
  v3extRawRows = await res.json();
  renderV3extRawTable();
}

function renderV3extRawTable() {
  const data = sortRows(v3extRawRows, v3extRawSort);
  const tbody = document.getElementById("v3ext-raw-tbody");
  tbody.innerHTML = "";
  if (!data.length) {
    tbody.innerHTML = `<tr><td colspan="16" class="empty-state">No data available for this configuration.</td></tr>`;
    updateSortIndicators("v3ext-raw-table", v3extRawSort);
    return;
  }
  data.forEach((r) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${r.nodes}</td>
      <td>${r.traffic}</td>
      <td>${r.mobility}</td>
      <td>${PROTOCOL_LABELS[r.protocol.toLowerCase()] || r.protocol}</td>
      <td>${r.seed}</td>
      <td>${r.duration}</td>
      <td>${fmt(r.throughputKbps, 2)}</td>
      <td>${fmt(r.delaySec * 1000, 2)}</td>
      <td>${fmt(r.jitterSec * 1000, 2)}</td>
      <td>${fmt(r.pdr, 2)}</td>
      <td>${r.packetLoss}</td>
      <td>${r.routingOverheadPackets}</td>
      <td>${fmt(r.hopCount, 2)} (${r.hopCountMethod})</td>
      <td>${r.pathChanges}</td>
      <td>${fmt(r.avgLinkUtilization, 4)}</td>
      <td>${fmt(r.maxLinkUtilization, 4)}</td>
    `;
    tbody.appendChild(tr);
  });
  updateSortIndicators("v3ext-raw-table", v3extRawSort);
}

// Sigmoid is deliberately not implemented for this track -- mark it in the
// routing filter rather than silently omitting it, so it reads as "pending
// Phase 3", not "forgotten".
function markSigmoidPending() {
  const hint = document.getElementById("v3ext-sigmoid-hint");
  if (hint) hint.textContent = "Sigmoid: not yet implemented / pending Phase 3 -- no rows exist for it yet.";
}

async function bootstrapV3ext() {
  const meta = await loadV3extMeta();
  markSigmoidPending();
  attachV3extFilters();
  attachSorting("v3ext-summary-table", v3extSort, renderV3extTable);
  attachSorting("v3ext-raw-table", v3extRawSort, renderV3extRawTable);
  await refreshV3ext();
  await refreshV3extRaw();

  if (meta.networkSizes && meta.networkSizes.length) {
    await loadV3cmpMeta(meta);
    attachV3cmpFilters();
    await refreshV3cmp();
  }
}

async function loadSigmoid() {
  const res = await fetch("/api/sigmoid");
  const data = await res.json();
  renderSigmoidSection(data);
}

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
  if (!rows.length) {
    card.style.display = "none";
    return;
  }
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

(async function init() {
  attachFilters();
  attachSorting("summary-table", sortState.summary, renderSummaryTable);
  setupNav();

  await Promise.all([loadMeta(), loadMethodology(), loadFullSummary(), loadResearchGraphs(), bootstrapTopology(), loadSigmoid(), bootstrapV3ext()]);
  await refreshPerformance();
  await refreshTrials();
  await loadFileList();
})();
