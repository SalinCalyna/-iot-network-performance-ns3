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
    meanKey: "pdrMean", stdKey: "pdrStd", ciKey: "pdrCi95", nKey: "pdrN", rowKey: "pdr",
    unit: "%", decimals: 2, scale: 1, underInvestigation: true,
    note: "AODV's PacketsSent denominator was found to scale with topology/network size in a way OLSR's and Static's do not (V2.7.1 validation report). AODV PDR here is provisional, not a settled comparison.",
  },
  throughput: {
    title: "Throughput",
    axisLabel: "Throughput (kbps)",
    meanKey: "throughputMean", stdKey: "throughputStd", ciKey: "throughputCi95", nKey: "throughputN", rowKey: "throughputKbps",
    unit: "kbps", decimals: 2, scale: 1, underInvestigation: false,
    note: "Received IP-layer bytes divided by the 70 s active traffic window (30 s-100 s). Not affected by the PacketsSent caveat.",
  },
  delay: {
    title: "End-to-End Delay",
    axisLabel: "Delay (ms)",
    meanKey: "delayMean", stdKey: "delayStd", ciKey: "delayCi95", nKey: "delayN", rowKey: "delaySec",
    unit: "ms", decimals: 2, scale: 1000, underInvestigation: false,
    note: "Packet-count-weighted average end-to-end delay across all received packets (FlowMonitor delaySum / received packets).",
  },
  loss: {
    title: "Packet Loss",
    axisLabel: "Packet loss (packets)",
    meanKey: "lossMean", stdKey: "lossStd", ciKey: "lossCi95", nKey: "lossN", rowKey: "packetLoss",
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
        // Display-only clamp: dataset.errorBarLowerBound is the metric's
        // physical lower bound (see PHYSICAL_LOWER_BOUND); the CI half-width
        // `err` itself is never altered.
        const lowerBound = dataset.errorBarLowerBound != null ? dataset.errorBarLowerBound : -Infinity;
        const yTop = yScale.getPixelForValue(value + err);
        const yBottom = yScale.getPixelForValue(Math.max(value - err, lowerBound, yScale.min));
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

// ---------------- Statistical-analysis helpers (shared by every chart) ----------------
// Single source of truth for the confidence level used dashboard-wide. All
// *Ci95 fields come pre-computed from the backend (Student's t, computed
// from the seed-level rows -- see app.py's _t_critical_95 / api_summary /
// api_v3ext_summary), always at this level; changing it here only relabels
// the charts/tooltips and does NOT change what the backend computed, so it
// is not exposed as a live UI control.
const CONFIDENCE_LEVEL = 0.95;
const CI_LABEL = `${Math.round(CONFIDENCE_LEVEL * 100)}% CI`;

function hexToRgba(hex, alpha) {
  const h = hex.replace("#", "");
  const r = parseInt(h.substring(0, 2), 16);
  const g = parseInt(h.substring(2, 4), 16);
  const b = parseInt(h.substring(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

// Builds the two hidden helper datasets (lower bound, upper bound-with-fill)
// that Chart.js's built-in filler renders as a shaded band between them.
// Must be pushed as an ADJACENT pair into `datasets` (lower immediately
// before upper) -- fill:'-1' means "fill to the previous dataset in this
// chart's dataset array". The visible mean line is a separate dataset the
// caller pushes on top (later in the array = drawn last = never obscured
// by the band), matching the requirement that the band stay visually
// subtle underneath the line.
// `lowerBound` (optional) is the metric's physical lower bound. It is applied
// ONLY to the drawn band's lower edge: the CI half-width in `ciArr` and the
// unclamped statistical lower limit (kept on the helper dataset as `rawLower`)
// are never modified.
function ciBandDatasetPair(meanArr, ciArr, colorHex, bandAlpha = 0.18, lowerBound = null) {
  const rawLower = meanArr.map((v, i) => (v == null || ciArr[i] == null ? null : v - ciArr[i]));
  const lower = rawLower.map((v) => (v == null ? null : displayLowerLimit(v, lowerBound)));
  const upper = meanArr.map((v, i) => (v == null || ciArr[i] == null ? null : v + ciArr[i]));
  const shared = {
    isCiHelper: true,
    pointRadius: 0,
    pointHoverRadius: 0,
    borderWidth: 0,
    tension: 0.25,
    spanGaps: false,
  };
  return [
    { ...shared, data: lower, rawLower, fill: false, backgroundColor: "transparent" },
    { ...shared, data: upper, fill: "-1", backgroundColor: hexToRgba(colorHex, bandAlpha) },
  ];
}

// Physical lower bounds, applied to the DISPLAYED lower CI limit only.
// Every metric charted here is a count, a ratio/fraction, a rate, or a time
// -- non-negative by construction -- so 0 is an objectively valid floor for
// each. A metric absent from this map gets no clamp. The mean, the SD/SE/CI
// and the raw observations are never clamped; a t-interval can still cross 0
// for a skewed, low-mean metric (e.g. PathChanges) and that is shown truthfully
// in the tooltip rather than hidden.
const PHYSICAL_LOWER_BOUND = {
  pdr: 0, throughput: 0, delay: 0, jitter: 0,
  loss: 0, packetLoss: 0, routingOverhead: 0,
  hopCount: 0, pathChanges: 0, avgLinkUtil: 0, maxLinkUtil: 0,
};
function physicalLowerBound(metricKey) {
  return Object.prototype.hasOwnProperty.call(PHYSICAL_LOWER_BOUND, metricKey)
    ? PHYSICAL_LOWER_BOUND[metricKey]
    : null;
}
function displayLowerLimit(rawLower, lowerBound) {
  return lowerBound != null ? Math.max(lowerBound, rawLower) : rawLower;
}

// Largest (value + CI half-width) across bar datasets, +5% headroom, used as the
// y-axis suggestedMax so an upper error-bar cap is never clipped by the plot
// area. Layout only -- no value or interval is altered.
function yMaxIncludingCi(datasets) {
  let max = 0;
  datasets.forEach((ds) => ds.data.forEach((v, i) => {
    if (v == null) return;
    const e = ds.errorBars ? ds.errorBars[i] : null;
    max = Math.max(max, v + (e != null ? e : 0));
  }));
  return max > 0 ? max * 1.05 : undefined;
}

// Multi-line tooltip body shared by every bar/line chart: "Mean: x unit",
// "95% CI: lower-upper unit" (or an explicit no-CI reason), "n = N".
// `lowerBound` (optional): when the raw lower limit falls below the metric's
// physical floor, the displayed limit is clamped to it and the raw value is
// still disclosed on its own line.
//
// Metric-specific sample size: `n` is the number of VALID observations for this
// metric; `opts.nTotal` (when given) is the number of seeds/runs the condition
// has. When n < nTotal the exclusion is spelled out -- n is never shown as the
// total. opts.unitWord ("run" | "seed") and opts.reason word the exclusion.
function validNText(n, nTotal, { eq = " = ", unitWord = "run", reason = "undefined: no packets received" } = {}) {
  if (nTotal == null || n == null || n >= nTotal) return `n${eq}${n}`;
  const k = nTotal - n;
  return `n${eq}${n} of ${nTotal}; ${k} ${unitWord}${k === 1 ? "" : "s"} excluded (${reason})`;
}

function ciTooltipLines(label, meanVal, ciVal, n, unit, decimals, lowerBound = null, opts = {}) {
  const lines = [];
  if (label) lines.push(label);
  if (meanVal == null) {
    // No valid observation at all: say so; never print a 0 or NaN as a mean.
    lines.push("Mean: n/a (no valid observations)");
    if (n != null) lines.push(validNText(n, opts.nTotal, opts));
    return lines;
  }
  lines.push(`Mean: ${fmt(meanVal, decimals)} ${unit}`.trim());
  if (n == null || n < 2) {
    lines.push(`${CI_LABEL}: n/a (n=${n ?? 0} seed${n === 1 ? "" : "s"})`);
  } else if (ciVal == null) {
    lines.push(`${CI_LABEL}: n/a`);
  } else {
    const rawLower = meanVal - ciVal;
    const shownLower = displayLowerLimit(rawLower, lowerBound);
    lines.push(`${CI_LABEL}: ${fmt(shownLower, decimals)}–${fmt(meanVal + ciVal, decimals)} ${unit}`.trim());
    if (shownLower !== rawLower) {
      lines.push(`(raw lower limit ${fmt(rawLower, decimals)}; shown clamped at ${lowerBound})`);
    }
  }
  if (n != null) lines.push(validNText(n, opts.nTotal, opts));
  return lines;
}

// null-safe scaling / averaging: a missing (null) statistic must stay missing --
// JavaScript would otherwise coerce null * 1000 to 0 and average it in as a value.
const scaleOrNull = (v, s) => (v == null ? null : v * s);
function meanOfDefined(values) {
  const ok = values.filter((v) => v != null);
  return ok.length ? ok.reduce((a, b) => a + b, 0) / ok.length : null;
}

// Excludes the hidden band-helper datasets from the legend and from
// tooltips, so only the real mean line/bar ever shows up in either.
const ciAwareLegend = { labels: { filter: (item, data) => !data.datasets[item.datasetIndex]?.isCiHelper } };
function ciAwareTooltipFilter(item) {
  return !item.dataset.isCiHelper;
}

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
    const data = nodeSizes.map((n) => (byNode[n] ? scaleOrNull(byNode[n][metric.meanKey], metric.scale) : null));
    const errorBars = nodeSizes.map((n) => (byNode[n] && byNode[n][metric.ciKey] != null ? byNode[n][metric.ciKey] * metric.scale : null));
    // Metric-specific valid n (delay can be below `trials` when a trial received
    // no packets and its delay is undefined) and the trial total, for the tooltip.
    const trials = nodeSizes.map((n) => (byNode[n] ? (byNode[n][metric.nKey] ?? byNode[n].trials) : null));
    const trialTotals = nodeSizes.map((n) => (byNode[n] ? byNode[n].trials : null));
    const key = proto.toLowerCase();
    return {
      label: PROTOCOL_LABELS[key] + (metric.underInvestigation && key === "aodv" ? " (under investigation)" : ""),
      data, errorBars, trials, trialTotals,
      errorBarLowerBound: physicalLowerBound(state.metric),
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
              const n = ds.trials ? ds.trials[item.dataIndex] : null;
              return ciTooltipLines(ds.label, item.raw, err, n, metric.unit, metric.decimals, ds.errorBarLowerBound, { nTotal: ds.trialTotals ? ds.trialTotals[item.dataIndex] : null });
            },
          },
        },
      },
      scales: {
        // suggestedMax keeps the upper CI whisker inside the plot area (the
        // axis would otherwise autoscale to the bar heights alone and clip it).
        y: { beginAtZero: true, suggestedMax: yMaxIncludingCi(datasets), title: { display: true, text: metric.axisLabel }, grid: { color: "rgba(255,255,255,0.06)" } },
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
      <td title="SD ${fmt(r.pdrStd, 2)}">${fmt(r.pdrMean, 2)} &plusmn; ${fmt(r.pdrCi95, 2)} (95% CI, n=${r.trials})</td>
      <td title="SD ${fmt(r.throughputStd, 2)}">${fmt(r.throughputMean, 2)} &plusmn; ${fmt(r.throughputCi95, 2)}</td>
      <td title="SD ${fmt(scaleOrNull(r.delayStd, 1000), 2)}">${r.delayMean == null ? "n/a (no valid observations)" : `${fmt(r.delayMean * 1000, 2)} &plusmn; ${fmt(scaleOrNull(r.delayCi95, 1000), 2)}`}${(r.delayN ?? r.trials) < r.trials ? ` <span class="small-note-inline">(${validNText(r.delayN, r.trials, { eq: "=" })})</span>` : ""}</td>
      <td title="SD ${fmt(r.lossStd, 1)}">${fmt(r.lossMean, 1)} &plusmn; ${fmt(r.lossCi95, 1)}</td>
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
    const avg = (field) => meanOfDefined(rows.map((r) => r[field]));
    const box = document.getElementById(`protocol-metrics-${key}`);
    box.innerHTML = `
      <div><span class="metric-label">Avg PDR</span><span class="metric-value">${fmt(avg("pdrMean"), 1)}%</span></div>
      <div><span class="metric-label">Avg Throughput</span><span class="metric-value">${fmt(avg("throughputMean"), 1)} kbps</span></div>
      <div><span class="metric-label">Avg Delay</span><span class="metric-value">${fmt(scaleOrNull(avg("delayMean"), 1000), 1)} ms</span></div>
      <div><span class="metric-label">Avg Loss</span><span class="metric-value">${fmt(avg("lossMean"), 0)} pkts</span></div>
    `;

    const nodeSizes = rows.map((r) => r.nodes).sort((a, b) => a - b);
    const byNode = {}; rows.forEach((r) => { byNode[r.nodes] = r; });
    const pdrMeans = nodeSizes.map((n) => byNode[n].pdrMean);
    const pdrCis = nodeSizes.map((n) => byNode[n].pdrCi95);
    const pdrTrials = nodeSizes.map((n) => byNode[n].trials);
    const ctx = document.getElementById(`mini-chart-${key}`).getContext("2d");
    if (miniCharts[key]) miniCharts[key].destroy();
    miniCharts[key] = new Chart(ctx, {
      type: "line",
      data: {
        labels: nodeSizes,
        datasets: [
          ...ciBandDatasetPair(pdrMeans, pdrCis, PROTOCOL_COLORS[key], 0.22, physicalLowerBound("pdr")),
          {
            data: pdrMeans, trials: pdrTrials, ci: pdrCis,
            borderColor: PROTOCOL_COLORS[key], backgroundColor: PROTOCOL_COLORS[key],
            tension: 0.3, pointRadius: 3, fill: false,
          },
        ],
      },
      options: {
        responsive: true, animation: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            filter: ciAwareTooltipFilter,
            callbacks: { label: (i) => ciTooltipLines(null, i.raw, i.dataset.ci[i.dataIndex], i.dataset.trials[i.dataIndex], "%", 1, physicalLowerBound("pdr")) },
          },
        },
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
    const datasets = [];
    protocols.forEach((key) => {
      const rows = fullSummary.filter((r) => r.protocol.toLowerCase() === key);
      const byNode = {}; rows.forEach((r) => { byNode[r.nodes] = r; });
      const meanArr = nodeSizes.map((n) => (byNode[n] ? scaleOrNull(byNode[n][metric.meanKey], metric.scale) : null));
      const ciArr = nodeSizes.map((n) => (byNode[n] && byNode[n][metric.ciKey] != null ? byNode[n][metric.ciKey] * metric.scale : null));
      const trialsArr = nodeSizes.map((n) => (byNode[n] ? (byNode[n][metric.nKey] ?? byNode[n].trials) : null));
      const trialTotalsArr = nodeSizes.map((n) => (byNode[n] ? byNode[n].trials : null));
      datasets.push(...ciBandDatasetPair(meanArr, ciArr, PROTOCOL_COLORS[key], 0.18, physicalLowerBound(metricKey)));
      datasets.push({
        label: PROTOCOL_LABELS[key],
        data: meanArr, ci: ciArr, trials: trialsArr, trialTotals: trialTotalsArr,
        borderColor: PROTOCOL_COLORS[key], backgroundColor: PROTOCOL_COLORS[key],
        tension: 0.3, pointRadius: 3, fill: false,
      });
    });
    if (scaleCharts[metricKey]) scaleCharts[metricKey].destroy();
    scaleCharts[metricKey] = new Chart(canvas.getContext("2d"), {
      type: "line",
      data: { labels: nodeSizes.map((n) => n + " nodes"), datasets },
      options: {
        responsive: true, animation: false,
        plugins: {
          legend: { position: "bottom", labels: { color: "#8b93a7", boxWidth: 10, font: { size: 11 }, filter: ciAwareLegend.labels.filter } },
          tooltip: {
            filter: ciAwareTooltipFilter,
            callbacks: {
              label: (item) => ciTooltipLines(item.dataset.label, item.raw, item.dataset.ci[item.dataIndex], item.dataset.trials[item.dataIndex], metric.unit, metric.decimals, physicalLowerBound(metricKey), { nTotal: item.dataset.trialTotals[item.dataIndex] }),
            },
          },
        },
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
      <td>${r.packetsReceived === 0 ? `<span title="No packets received: delay is undefined (the raw CSV stores 0 as a placeholder); excluded from delay statistics." style="text-decoration:underline dotted;">undefined</span>` : fmt(r.delaySec * 1000, 2)}</td>
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
      { key: "delaySec", label: "Delay (ms)", decimals: 2, scale: 1000, validWhen: (r) => r.packetsReceived > 0 },
      { key: "packetLoss", label: "Packet loss (pkts)", decimals: 1 },
    ]
  );
}

function computeStats(values) {
  const n = values.length;
  if (n === 0) return { mean: null, std: null, min: null, max: null };
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
    // f.validWhen (optional) marks the rows where this metric is DEFINED; the
    // others (e.g. delay of a trial that received no packets) are left out of
    // this metric's statistics and the exclusion is shown, not hidden.
    const validRows = f.validWhen ? rows.filter(f.validWhen) : rows;
    const values = validRows.map((r) => r[f.key] * scale);
    const s = computeStats(values);
    const nNote = validRows.length < rows.length
      ? ` <span class="small-note-inline">(${validNText(validRows.length, rows.length, { eq: "=", unitWord: "trial" })})</span>`
      : "";
    html += `<tr>
      <td>${f.label}${nNote}</td>
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
      <td>${fmt(r.PDR, 2)}</td><td>${fmt(r.ThroughputKbps, 2)}</td><td>${r.PacketsReceived === 0 ? `<span title="No packets received: delay is undefined (the raw CSV stores 0 as a placeholder)." style="text-decoration:underline dotted;">undefined</span>` : fmt(r.AverageDelaySec, 4)}</td>
    `;
    tbody.appendChild(tr);
  });

  if (data.stats) {
    renderStatsTable(
      "raw-stats",
      (data.rows || []).map((r) => ({ pdr: r.PDR, throughputKbps: r.ThroughputKbps, delaySec: r.AverageDelaySec, packetLoss: r.PacketLoss, packetsReceived: r.PacketsReceived })),
      [
        { key: "pdr", label: "PDR (%)", decimals: 2 },
        { key: "throughputKbps", label: "Throughput (kbps)", decimals: 2 },
        { key: "delaySec", label: "Delay (ms)", decimals: 2, scale: 1000, validWhen: (r) => r.packetsReceived > 0 },
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

// seedRange: "official" (Seed 20-30 only -- the default and what n=11 cells
// come from), "all" (include legacy/smoke rows), or "legacy" (only those).
const v3extState = { nodes: "all", traffic: "all", mobility: "all", routing: "all", duration: "all", seedRange: "official", metric: "pdr" };
const V3EXT_SEEDRANGE_LABELS = {
  official: "Official (Seeds 20–30), n=11 per official cell",
  all: "All runs (official + legacy/smoke)",
  legacy: "Legacy / Smoke only (non-official seeds)",
};
const v3extSort = { key: "nodes", dir: 1 };
let v3extSummary = [];
let v3extMarginal = [];   // per-seed marginal CI rows (/api/v3ext/marginal) -- drives the line-chart band
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
  const query = qs({
    nodes: v3extState.nodes, traffic: v3extState.traffic, mobility: v3extState.mobility,
    routing: v3extState.routing, duration: v3extState.duration, seedRange: v3extState.seedRange,
  });
  // Same filters for both: the summary gives per-cell rows (table, mean line),
  // the marginal gives the seed-level CI for the chart's own (protocol, nodes) grouping.
  const [summaryRes, marginalRes] = await Promise.all([
    fetch("/api/v3ext/summary?" + query),
    fetch("/api/v3ext/marginal?" + query),
  ]);
  v3extSummary = await summaryRes.json();
  v3extMarginal = await marginalRes.json();
  const readout = document.getElementById("v3ext-seedrange-readout");
  if (readout) readout.textContent = V3EXT_SEEDRANGE_LABELS[v3extState.seedRange] || v3extState.seedRange;
  renderV3extChart();
  renderV3extTable();
  renderV3extKpis();
  renderV3extSecondaryMetrics();
}

function renderV3extChart() {
  const metric = V3EXT_METRICS[v3extState.metric];
  document.getElementById("v3ext-chart-title").textContent = metric.title + " vs. Network Size";
  document.getElementById("v3ext-chart-note").textContent =
    "Each point is the mean across whatever seeds are present for that (protocol, node count) cell under the current filters -- if multiple traffic/mobility cells match, the point averages across them too (the table below always lists every cell separately). The shaded band is a 95% CI (two-sided Student's t, df = n−1 = 10 for the 11 official seeds). For a point that averages several traffic/mobility cells, each seed's value is first averaged across those cells (one value per seed) and the CI is taken across the 11 per-seed values -- never from the cell means themselves. Delay, Jitter and Hop Count are undefined for a run in which no packet was received; such runs (or, for a multi-cell point, their whole seed) are excluded from those three metrics only, and the tooltip then reads \"n = 10 of 11 ...\" with df = n−1 = 9. Hover a point for n, the CI limits and how many cells were averaged.";

  const nodeSizes = [...new Set(v3extSummary.map((r) => r.nodes))].sort((a, b) => a - b);
  const protocols = [...new Set(v3extSummary.map((r) => r.protocol))].sort();
  const lowerBound = physicalLowerBound(metric.key);

  const datasets = [];
  protocols.forEach((proto) => {
    const byNode = {};
    v3extSummary.filter((r) => r.protocol === proto).forEach((r) => {
      (byNode[r.nodes] = byNode[r.nodes] || []).push(r);
    });
    // Seed-level marginal for this (protocol, nodes) point, when unambiguous:
    // exactly one duration in scope and a balanced design (every seed carries
    // the same cells). Its statistics are computed per metric on the VALID
    // seeds only (see /api/v3ext/marginal), so `<key>N` may be below the
    // design's seed count when a metric is undefined for some seed. Otherwise
    // (legacy 'all' views with mixed durations / unbalanced seeds) there is no
    // valid seed-level CI and the point stays band-less rather than fabricated.
    const marginalFor = (n) => {
      const rows = v3extMarginal.filter((m) => m.protocol === proto && m.nodes === n);
      return rows.length === 1 && rows[0].balanced ? rows[0] : null;
    };
    const validN = (m) => (m ? m[`${metric.key}N`] : null);
    // Mean line. For an unaffected point this is the same number as before (the
    // mean of the matching cell means == the mean of the per-seed values). Where
    // a seed-level point exists it is the mean of that point's valid per-seed
    // observations, so the band is centred on the plotted line even when a seed
    // was excluded for this metric. Fallback (no seed-level point): the mean of
    // the cell means that ARE defined -- a missing mean is never turned into 0.
    const data = nodeSizes.map((n) => {
      const m = marginalFor(n);
      if (m && m[`${metric.key}Mean`] != null) return m[`${metric.key}Mean`] * metric.scale;
      const cells = byNode[n];
      if (!cells) return null;
      const avg = meanOfDefined(cells.map((c) => c[`${metric.key}Mean`]));
      return avg == null ? null : avg * metric.scale;
    });
    const ciArr = nodeSizes.map((n) => {
      const m = marginalFor(n);
      if (!m || !(validN(m) >= 2)) return null;
      return scaleOrNull(m[`${metric.key}Ci95`], metric.scale);
    });
    const nArr = nodeSizes.map((n) => {
      const m = marginalFor(n);
      if (m) return validN(m);
      const cells = byNode[n];
      return cells && cells.length === 1 ? (cells[0][`${metric.key}N`] ?? cells[0].n) : null;
    });
    const nTotalArr = nodeSizes.map((n) => {
      const m = marginalFor(n);
      if (m) return m.n;
      const cells = byNode[n];
      return cells && cells.length === 1 ? cells[0].n : null;
    });
    const cellsArr = nodeSizes.map((n) => {
      const m = marginalFor(n);
      return m ? m.cells : null;
    });
    const key = proto.toLowerCase();
    datasets.push(...ciBandDatasetPair(data, ciArr, PROTOCOL_COLORS[key] || "#999", 0.18, lowerBound));
    datasets.push({
      label: PROTOCOL_LABELS[key] || proto,
      data, ci: ciArr, n: nArr, nTotal: nTotalArr, cells: cellsArr,
      borderColor: PROTOCOL_COLORS[key] || "#999",
      backgroundColor: PROTOCOL_COLORS[key] || "#999",
      tension: 0.25,
      pointRadius: 4,
      fill: false,
    });
  });

  const ctx = document.getElementById("v3ext-chart").getContext("2d");
  if (v3extChart) v3extChart.destroy();
  v3extChart = new Chart(ctx, {
    type: "line",
    data: { labels: nodeSizes.map((n) => n + " nodes"), datasets },
    options: {
      responsive: true, animation: false,
      plugins: {
        legend: { position: "top", labels: { color: "#dbe2f0", filter: ciAwareLegend.labels.filter } },
        tooltip: {
          filter: ciAwareTooltipFilter,
          callbacks: {
            label(item) {
              const ds = item.dataset;
              const cells = ds.cells ? ds.cells[item.dataIndex] : null;
              // A seed-level point averages several cells, so an excluded unit is a whole seed
              // (any of its runs undefined); for a single cell it is one run.
              const exclOpts = {
                nTotal: ds.nTotal ? ds.nTotal[item.dataIndex] : null,
                unitWord: cells > 1 ? "seed" : "run",
                reason: cells > 1 ? "undefined: no packets received in at least one of its runs" : "undefined: no packets received",
              };
              const lines = ciTooltipLines(ds.label, item.raw, ds.ci[item.dataIndex], ds.n[item.dataIndex], metric.unit, metric.decimals, lowerBound, exclOpts);
              if (cells > 1) lines.push(`seed-level average of ${cells} traffic × mobility cells`);
              return lines;
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
  // n is the metric's own VALID sample size; nTotal the cell's seed count. When
  // they differ the exclusion is written out ("n=10 of 11; 1 run excluded ...").
  const ciTag = (mean, ci95, n, decimals, nTotal) => {
    const ntext = validNText(n, nTotal, { eq: "=" });
    if (mean == null) return `n/a (no valid observations; ${ntext})`;
    return n < 2 || ci95 == null
      ? `${fmt(mean, decimals)} (${ntext})`
      : `${fmt(mean, decimals)} &plusmn; ${fmt(ci95, decimals)} (${ntext})`;
  };
  const nOf = (r, key) => r[`${key}N`] ?? r.n;
  data.forEach((r) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${PROTOCOL_LABELS[r.protocol.toLowerCase()] || r.protocol}</td>
      <td>${r.nodes}</td>
      <td>${r.traffic}</td>
      <td>${r.mobility}</td>
      <td>${r.duration}</td>
      <td>${r.n}</td>
      <td>${ciTag(r.pdrMean, r.pdrCi95, nOf(r, "pdr"), 2, r.n)}</td>
      <td>${ciTag(r.throughputMean, r.throughputCi95, nOf(r, "throughput"), 2, r.n)}</td>
      <td>${ciTag(scaleOrNull(r.delayMean, 1000), scaleOrNull(r.delayCi95, 1000), nOf(r, "delay"), 2, r.n)}</td>
      <td>${ciTag(scaleOrNull(r.jitterMean, 1000), scaleOrNull(r.jitterCi95, 1000), nOf(r, "jitter"), 2, r.n)}</td>
      <td>${ciTag(r.packetLossMean, r.packetLossCi95, nOf(r, "packetLoss"), 1, r.n)}</td>
      <td>${ciTag(r.routingOverheadMean, r.routingOverheadCi95, nOf(r, "routingOverhead"), 1, r.n)}</td>
      <td>${fmt(r.hopCountMean, 2)} (${r.hopCountMethod}${nOf(r, "hopCount") < r.n ? "; " + validNText(nOf(r, "hopCount"), r.n, { eq: "=" }) : ""})</td>
      <td>${ciTag(r.pathChangesMean, r.pathChangesCi95, nOf(r, "pathChanges"), 1, r.n)}</td>
      <td>${ciTag(r.avgLinkUtilMean, r.avgLinkUtilCi95, nOf(r, "avgLinkUtil"), 4, r.n)}</td>
      <td>${ciTag(r.maxLinkUtilMean, r.maxLinkUtilCi95, nOf(r, "maxLinkUtil"), 4, r.n)}</td>
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
  document.getElementById("v3ext-filter-seedrange").addEventListener("change", (e) => { v3extState.seedRange = e.target.value; onFilterChange(); });
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
  // meanOfDefined: a cell with no valid observation for a metric (null mean) is
  // skipped, never averaged in as 0.
  const avg = (key) => meanOfDefined(v3extSummary.map((r) => r[key]));
  els.throughput.textContent = fmt(avg("throughputMean"), 2);
  els.pdr.textContent = fmt(avg("pdrMean"), 2);
  els.delay.textContent = fmt(scaleOrNull(avg("delayMean"), 1000), 2);
  els.jitter.textContent = fmt(scaleOrNull(avg("jitterMean"), 1000), 2);
  const n = v3extSummary.reduce((s, r) => s + r.n, 0);
  // Delay / Jitter are undefined for a run with no packets received and are left
  // out of those two cards' cell means; say how many runs that is.
  const excluded = v3extSummary.reduce((s, r) => s + Math.max(r.delayExcluded || 0, r.jitterExcluded || 0), 0);
  const exclNote = excluded > 0
    ? ` Delay/Jitter exclude ${excluded} run${excluded === 1 ? "" : "s"} with no packets received (undefined, not 0).`
    : "";
  document.getElementById("v3ext-kpi-note").textContent =
    (v3extSummary.length === 1
      ? `Single matching cell -- n=${v3extSummary[0].n} seed(s).`
      : `Averaged across ${v3extSummary.length} matching cells (${n} seed-runs total). Narrow the filters above for an exact single-condition reading.`) + exclNote;
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
  // Comparison mode always compares protocols on the official dataset only.
  const res = await fetch("/api/v3ext/summary?" + qs({
    nodes: v3cmpState.nodes, traffic: v3cmpState.traffic, mobility: v3cmpState.mobility,
    routing: "all", duration: v3cmpState.duration, seedRange: "official",
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

  // Metric-specific valid n (`<key>N`) -- for Delay/Jitter/Hop Count it can be below
  // the cell's seed count `n` (runs with no packets received are undefined and
  // excluded). The error bar is the 95% CI computed from exactly those valid runs.
  const validN = (r) => (r ? (r[`${metric.key}N`] ?? r.n) : null);
  const data = V3CMP_PROTOCOLS.map((p) => (byProto[p] ? scaleOrNull(byProto[p][`${metric.key}Mean`], metric.scale) : null));
  const errorBars = V3CMP_PROTOCOLS.map((p) => {
    const r = byProto[p];
    if (!r || !(validN(r) >= 2)) return null;
    return scaleOrNull(r[`${metric.key}Ci95`], metric.scale);
  });
  const nArr = V3CMP_PROTOCOLS.map((p) => validN(byProto[p]));
  const nTotalArr = V3CMP_PROTOCOLS.map((p) => (byProto[p] ? byProto[p].n : null));

  const ctx = canvas.getContext("2d");
  if (v3cmpChart) v3cmpChart.destroy();
  v3cmpChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: V3CMP_PROTOCOLS.map((p) => PROTOCOL_LABELS[p] || p),
      datasets: [{
        label: metric.title,
        data, errorBars, n: nArr, nTotal: nTotalArr,
        // errorBars are 95% CI half-widths (t-based, from the 11 seeds of each
        // protocol's own cell) -- not SD. The bound only limits the drawn lower cap.
        errorBarLowerBound: physicalLowerBound(metric.key),
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
              if (item.raw == null) return `${item.label}: no data`;
              const ds = item.dataset;
              return ciTooltipLines(null, item.raw, ds.errorBars[item.dataIndex], ds.n[item.dataIndex], metric.unit, metric.decimals, ds.errorBarLowerBound, { nTotal: ds.nTotal[item.dataIndex] });
            },
          },
        },
      },
      scales: {
        y: { beginAtZero: true, suggestedMax: yMaxIncludingCi([{ data, errorBars }]), title: { display: true, text: metric.axisLabel }, grid: { color: "rgba(255,255,255,0.06)" } },
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
    routing: v3extState.routing, duration: v3extState.duration, seedRange: v3extState.seedRange,
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
  // A run with no packets received has Delay / Jitter / (approximate) Hop Count
  // UNDEFINED; the simulator stored the placeholder 0 in the CSV. The stored
  // value is unchanged -- the table just doesn't present it as a measurement.
  const undefinedCell = (title) => `<span title="${title}" style="text-decoration:underline dotted;">undefined</span>`;
  const UNDEF_TITLE = "No packets received: this metric is undefined. The raw CSV stores 0 as a placeholder; it is excluded from this metric's statistics.";
  data.forEach((r) => {
    const noRx = r.packetsReceived === 0;
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${r.nodes}</td>
      <td>${r.traffic}</td>
      <td>${r.mobility}</td>
      <td>${PROTOCOL_LABELS[r.protocol.toLowerCase()] || r.protocol}</td>
      <td>${r.seed}</td>
      <td>${r.duration}</td>
      <td>${fmt(r.throughputKbps, 2)}</td>
      <td>${noRx ? undefinedCell(UNDEF_TITLE) : fmt(r.delaySec * 1000, 2)}</td>
      <td>${noRx ? undefinedCell(UNDEF_TITLE) : fmt(r.jitterSec * 1000, 2)}</td>
      <td>${fmt(r.pdr, 2)}</td>
      <td>${r.packetLoss}</td>
      <td>${r.routingOverheadPackets}</td>
      <td>${noRx && r.hopCountMethod !== "exact" ? undefinedCell(UNDEF_TITLE) : fmt(r.hopCount, 2)} (${r.hopCountMethod})</td>
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
