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
function renderTopology() {
  const svg = document.getElementById("topology-svg");
  const sensors = [
    { x: 60, y: 60 }, { x: 180, y: 50 }, { x: 300, y: 65 }, { x: 420, y: 55 },
    { x: 540, y: 70 }, { x: 300, y: 150 },
  ];
  const gateway = { x: 320, y: 250 };
  const edges = [[0, 1], [1, 2], [2, 3], [3, 4], [2, 5], [5, 6]];
  const all = [...sensors, gateway];

  let lines = "";
  edges.forEach(([a, b], i) => {
    const p1 = all[a], p2 = all[b];
    if (!p1 || !p2) return;
    lines += `<line class="topo-line" x1="${p1.x}" y1="${p1.y}" x2="${p2.x}" y2="${p2.y}"
      stroke="#3b82f6" stroke-width="2" stroke-opacity="0.55" style="animation-delay:${i * 0.15}s" />`;
  });
  let nodes = "";
  sensors.forEach((p, i) => {
    nodes += `<circle cx="${p.x}" cy="${p.y}" r="10" fill="#0a0e18" stroke="#22d3ee" stroke-width="2" />
      <text x="${p.x}" y="${p.y + 24}" fill="#8b93a7" font-size="11" text-anchor="middle">Sensor ${i + 1}</text>`;
  });
  nodes += `<circle cx="${gateway.x}" cy="${gateway.y}" r="16" fill="#3b82f6" stroke="#93c5fd" stroke-width="2" />
    <text x="${gateway.x}" y="${gateway.y + 32}" fill="#e7ebf5" font-size="12" font-weight="700" text-anchor="middle">Gateway / Sink</text>`;

  svg.innerHTML = `<style>.topo-line{stroke-dasharray:8;animation:dash 1.6s linear infinite;}
    @keyframes dash{to{stroke-dashoffset:-32;}}</style>${lines}${nodes}`;
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

(async function init() {
  attachFilters();
  attachSorting("summary-table", sortState.summary, renderSummaryTable);
  setupNav();
  renderTopology();

  await Promise.all([loadMeta(), loadMethodology(), loadFullSummary()]);
  await refreshPerformance();
  await refreshTrials();
  await loadFileList();
})();
