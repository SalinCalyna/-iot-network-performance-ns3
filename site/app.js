// Main dashboard wiring: navigation, filters, and section rendering.
// All numbers rendered here come from data/final_research.json, which is a direct
// extract of analysis/final-report-data/*.csv (see that package for the source of truth).

const COLORS = { olsr: "var(--olsr)", static: "var(--static)", aodv: "var(--aodv)", v4: "var(--v4)" };
let DATA = null;
// Derived statistical layer (data/v3ext-stats.json, built by experiments/build_v3_site_stats.py from the raw
// results/v3-ext/*.csv). final_research.json / research.db are read as before and never modified. If the file
// cannot be loaded the charts fall back to means only -- a confidence interval is never invented.
let STATS = null;
const UNDEFINED_METRICS = ["delay", "jitter", "hop"];   // undefined when PacketsReceived == 0 (hop: unless exact method)
function nodeBlock(p, n, mk) {
  const m = STATS && STATS.marginalNodes.find(r => r.protocol === p && r.nodes === n);
  return m ? m.metrics[mk] : null;
}
// Baseline value for (protocol, N, field). Delay / Jitter / Hop Count come from the exclusion-aware statistics layer
// (frozen final_research.json still averages the simulator's placeholder 0 of an undefined run into them);
// every other field is the frozen value, unchanged.
function bval(p, n, field) {
  const blk = UNDEFINED_METRICS.includes(field) ? nodeBlock(p, n, field) : null;
  if (blk && blk.mean != null) return blk.mean;
  const row = DATA.baseline[p].find(d => d.n === n);
  return row ? row[field] : undefined;
}

// ---------------------------------------------------------------- navigation
function initNav() {
  const links = document.querySelectorAll(".navlink");
  const sections = [...document.querySelectorAll("section.view")];
  const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  links.forEach(l => l.addEventListener("click", ev => {
    const t = document.getElementById(l.dataset.target);
    if (!t) return;
    ev.preventDefault();
    t.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
    history.replaceState(null, "", "#" + l.dataset.target);   // shareable section links
    closeDrawer();
  }));
  const setActive = id => links.forEach(l => {
    const on = l.dataset.target === id;
    l.classList.toggle("active", on);
    if (on) l.setAttribute("aria-current", "true"); else l.removeAttribute("aria-current");
  });
  const spy = new IntersectionObserver(entries => {
    entries.forEach(e => { if (e.isIntersecting) setActive(e.target.id); });
  }, { rootMargin: "-15% 0px -70% 0px" });
  sections.forEach(s => spy.observe(s));

  const btn = document.getElementById("menu-btn");
  btn.setAttribute("aria-controls", "sidebar"); btn.setAttribute("aria-expanded", "false");
  btn.setAttribute("aria-label", "Open section navigation");
  btn.addEventListener("click", () => {
    document.getElementById("sidebar").classList.add("open");
    document.getElementById("scrim").classList.add("show");
    btn.setAttribute("aria-expanded", "true");
  });
  document.getElementById("scrim").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", e => { if (e.key === "Escape") closeDrawer(); });
}
function closeDrawer() {
  document.getElementById("sidebar").classList.remove("open");
  document.getElementById("scrim").classList.remove("show");
  const btn = document.getElementById("menu-btn");
  if (btn) btn.setAttribute("aria-expanded", "false");
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
function renderHero() {   // run counts in the overview cards, from final_research.json "stats"
  const s = DATA.stats, set = (id, v) => { const e = document.getElementById(id); if (e) e.textContent = v; };
  set("kpi-v3", s.v3_runs.toLocaleString());
  set("kpi-bottleneck", s.bottleneck_runs.toLocaleString());
  set("kpi-repro", `${s.repro_pass}/${s.repro_total - s.repro_na}`);
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
// OLSR RoutingOverhead is stored as 0 because of a documented instrumentation-coverage limitation (see the chart's own note),
// so a "0 ± 0" interval would falsely suggest a precisely measured zero -- no CI is drawn for it.
const noCi = (p, metric) => metric === "routing_overhead" && p === "olsr";
function activeSeries(metric, scale) {
  const out = {};
  Object.keys(perfProtocols).forEach(p => {
    if (!perfProtocols[p]) return;
    out[p] = DATA.baseline[p].map(d => {
      const blk = nodeBlock(p, d.n, metric);
      if (!blk || blk.mean == null) return { x: d.n, y: scale ? d[metric] * scale : d[metric] };   // no statistics available: plain point
      const k = scale || 1;
      const pt = { x: d.n, y: blk.mean * k, n: blk.n, nTotal: blk.nTotal };
      if (blk.ci95 != null && !noCi(p, metric)) pt.ci = blk.ci95 * k;
      return pt;
    });
  });
  return out;
}
// Per-chart disclosure of any chart point whose metric is undefined for some seed(s).
function undefinedNoteFor(metric) {
  if (!STATS || !UNDEFINED_METRICS.includes(metric)) return "";
  const parts = [];
  STATS.marginalNodes.forEach(m => {
    const b = m.metrics[metric];
    if (b.excluded > 0 && perfProtocols[m.protocol]) {
      parts.push(`${m.protocol.toUpperCase()} @ N=${m.nodes}: n = ${b.n} of ${b.nTotal} seeds &mdash; seed ${b.excludedSeeds.join(", ")} excluded (undefined: no packets were received in at least one of its runs; df = ${b.df}, t = ${b.t}).`);
    }
  });
  return parts.join("<br>");
}
const PERF_CHARTS = [   // ytitle = axis title with unit; line charts use a proportional node-count axis (xNumeric)
  ["chart-pdr", "line", "pdr", null, { unit: "%", yfmt: 0, ytitle: "PDR (%)" }],
  ["chart-throughput", "line", "throughput", null, { unit: " kbps", yfmt: 0, ytitle: "Throughput (kbps)" }],
  ["chart-delay", "line", "delay", null, { unit: " ms", yfmt: 0, ytitle: "Mean delay (ms)" }],
];
function drawPerfCharts() {
  legendOnce("perf-legend");
  PERF_CHARTS.forEach(([id, kind, metric, scale, o]) => {
    const c = document.getElementById(id);
    const series = activeSeries(metric, scale);
    if (kind === "line") lineChart(c, series, { colors: COLORS, xNumeric: true, xtitle: "Number of sensor nodes (N)", ...o });
    else groupedBar(c, series, { colors: COLORS, xtitle: "Number of sensor nodes (N)", ...o, xlabel: x => `N=${x}` });
    if (STATS) {
      let extra = undefinedNoteFor(metric);
      if (metric === "routing_overhead" && perfProtocols.olsr) extra += (extra ? "<br>" : "") + "OLSR: stored 0 reflects a documented instrumentation-coverage limitation &mdash; no interval is drawn for it.";
      ciCaption(c, kind === "line" ? "band" : "bar", extra);
    }
  });
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
  ["aodv", "olsr", "static"].forEach(p => {
    series[p] = levels.map(l => {
      const m = STATS && STATS.marginalTraffic.find(r => r.protocol === p && r.traffic === l);
      const b = m && m.metrics.pdr;
      return b && b.mean != null ? { x: l.toUpperCase(), y: b.mean, ci: b.ci95 == null ? undefined : b.ci95, n: b.n, nTotal: b.nTotal }
                                 : { x: l.toUpperCase(), y: DATA.traffic_level[p][l] };
    });
  });
  groupedBar(c, series, { colors: COLORS, unit: "%", yfmt: 0, xlabel: x => x, ytitle: "PDR (%)", xtitle: "Traffic level" });
  if (STATS) ciCaption(c, "bar", "Each bar: every seed&rsquo;s mean PDR over the 18 conditions (6 node counts &times; 3 mobility modes); the CI is taken across those 11 per-seed values.");
}

// ---------------------------------------------------------------- 6. bottleneck
function renderBottleneck() {
  const c1 = document.getElementById("chart-gw-airtime");
  legend(document.getElementById("bn-legend"), [["OLSR / high", "var(--olsr)"], ["Static / high", "var(--static)"]]);
  groupedBar(c1, {
    olsr: DATA.bottleneck["olsr-high"].map(d => ({ x: d.n, y: d.gw_airtime * 100 })),
    static: DATA.bottleneck["static-high"].map(d => ({ x: d.n, y: d.gw_airtime * 100 }))
  }, { colors: COLORS, unit: "%", yfmt: 0, xlabel: x => `N=${x}`, ytitle: "Gateway airtime (% busy)", xtitle: "Number of sensor nodes (N), high traffic" });
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
    { colors: { macq: "var(--warn)" }, yfmt: 1, xlabel: x => x === "gw" ? "Gateway" : x.toUpperCase(),
      ytitle: "MAC-queue drops per node (mean)", xtitle: "Hop distance from gateway",
      title: `Mean MAC-queue drops per node by hop distance, ${hopState.protocol.toUpperCase()} N=${hopState.n}, ${hopState.traffic} traffic` });
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
function renderV4() {   // Tier-1 activation screen: table only (the bar chart duplicated it)
  const tbody = document.getElementById("v4-table-body"); tbody.innerHTML = "";
  DATA.v4_tier1.forEach(r => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${r.condition}</td><td>${r.route_change_pct}</td><td>${r.activated}</td>
      <td class="num">${r.pdr_v4.toFixed(2)}%</td><td class="num">${r.pdr_static.toFixed(2)}%</td>`;
    tbody.appendChild(tr);
  });
}

// ---------------------------------------------------------------- 9b. V4 matched-condition comparison
function renderV4Matched() {
  legend(document.getElementById("v4-matched-legend"), [["V4 (Sigmoid-weighted)", "var(--v4)"], ["Static", "var(--static)"]]);
  groupedBar(document.getElementById("chart-v4-matched-pdr"), {
    v4: DATA.v4_matched.map(d => ({ x: d.n, y: d.pdr_v4 })),
    static: DATA.v4_matched.map(d => ({ x: d.n, y: d.pdr_static }))
  }, { colors: { v4: "var(--v4)", static: "var(--static)" }, unit: "%", yfmt: 0, xlabel: x => `N=${x}`, ytitle: "PDR (%)", xtitle: "Number of sensor nodes (N)" });
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
  lineChart(document.getElementById("chart-int-airtime"), { air: rows.map(d => ({ x: d.rate + "k", y: d.gw_airtime * 100 })) }, { colors: { air: "var(--warn)" }, unit: "%", yfmt: 0, ytitle: "Gateway airtime (% busy)", xtitle: "Offered rate per sensor (kbps, 3 seeds)" });
  const delta = rows[rows.length - 1].delta_pdr_pp;
  document.getElementById("int-delta").textContent = `${delta > 0 ? "+" : ""}${delta.toFixed(1)} pp`;
  document.getElementById("int-delta-label").textContent = `PDR change, N=${intN}, 16→4 kbps`;
}

// ---------------------------------------------------------------- 11. static control
function renderStaticControl() {
  legend(document.getElementById("sc-legend"), [["OLSR N=75", "var(--olsr)"], ["OLSR N=100", "var(--olsr-2)"], ["Static N=50", "var(--static)"]]);
  lineChart(document.getElementById("chart-static-control"), {
    "OLSR N=75": DATA.ratesweep["olsr-75"].map(d => ({ x: d.rate + "k", y: d.pdr })),
    "OLSR N=100": DATA.ratesweep["olsr-100"].map(d => ({ x: d.rate + "k", y: d.pdr })),
    "Static N=50": DATA.ratesweep["static-50"].map(d => ({ x: d.rate + "k", y: d.pdr }))
  }, { colors: { "OLSR N=75": "var(--olsr)", "OLSR N=100": "var(--olsr-2)", "Static N=50": "var(--static)" }, unit: "%", yfmt: 0, ytitle: "PDR (%)", xtitle: "Offered rate per sensor (kbps, 3 seeds)" });

}

// ---------------------------------------------------------------- init
async function main() {
  DATA = await fetch("data/final_research.json").then(r => r.json());
  try { STATS = await fetch("data/v3ext-stats.json").then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }); } catch (e) { STATS = null; console.warn("v3ext-stats.json unavailable:", e); }
  renderHero();
  renderPerformance();
  renderTrafficLoad();
  renderBottleneck();
  renderHopChart();
  renderRetry();
  renderIntervention();
  renderStaticControl();
  renderV4();
  renderV4Matched();
  initNav();
}
document.addEventListener("DOMContentLoaded", main);
