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

// ---------------------------------------------------------------- 2b. risk summary
// Classification method (documented in the UI callout too):
//  - PDR and Gateway Airtime reuse the existing statusFromPdr/statusFromAirtime
//    thresholds already used by the Network Health panel above.
//  - Throughput/Delay/Packet Loss/Routing Overhead/Path Changes have no predefined
//    threshold in the research methodology, so each is classified relative to its
//    own median across the full measured Without-Risk baseline (all protocols x
//    all node counts) -- a transparent, data-derived relative comparison, not an
//    invented cutoff.
let riskMedians = null;
let riskState = { protocol: "olsr", n: 100 };

function median(arr) {
  const s = [...arr].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}
function computeRiskMedians() {
  const fields = ["throughput", "delay", "loss", "routing_overhead", "path_changes"];
  const all = {}; fields.forEach(f => all[f] = []);
  ["aodv", "olsr", "static"].forEach(p => {
    DATA.baseline[p].forEach(d => fields.forEach(f => all[f].push(bval(p, d.n, f))));
  });
  riskMedians = {};
  fields.forEach(f => riskMedians[f] = median(all[f]));
}

function riskItemHtml(item) {
  const cls = item.level === "HIGH" ? "risk-high" : "risk-low";
  const levelText = item.level === "HIGH" ? "High — " : "Low Risk — ";
  return `<div class="risk-item ${cls}">
    <div class="ri-icon"><span class="ri-dot"></span></div>
    <div class="ri-body">
      <div class="ri-name">${item.label}</div>
      <div class="ri-value">${item.valueText}</div>
      <div class="ri-why">${levelText}${item.why}</div>
    </div>
  </div>`;
}

function renderRiskSummary() {
  if (!riskMedians) computeRiskMedians();
  const pOpts = ["aodv", "olsr", "static"];
  const nOpts = [10, 20, 30, 50, 75, 100];
  pillGroup(document.getElementById("risk-protocol"), pOpts.map(s => s.toUpperCase()), pOpts.indexOf(riskState.protocol),
    i => { riskState.protocol = pOpts[i]; drawRiskSummary(); });
  pillGroup(document.getElementById("risk-n"), nOpts.map(String), nOpts.indexOf(riskState.n),
    i => { riskState.n = nOpts[i]; drawRiskSummary(); });
  drawRiskSummary();
}

function drawRiskSummary() {
  const { protocol, n } = riskState;
  const baseRow = DATA.baseline[protocol].find(d => d.n === n);
  const cell = baseRow && { ...baseRow, delay: bval(protocol, n, "delay") };   // delay: exclusion-aware
  const highEl = document.getElementById("risk-high-list");
  const lowEl = document.getElementById("risk-low-list");
  const ctxEl = document.getElementById("risk-context");
  if (!cell) { // defensive only -- the full baseline grid always covers every protocol x N combination
    highEl.innerHTML = lowEl.innerHTML = '<p class="panel-sub" style="margin:0">No baseline data for this configuration.</p>';
    ctxEl.textContent = "";
    return;
  }

  const items = [];

  const pdrStatus = statusFromPdr(cell.pdr);
  items.push({ label: "PDR (Packet Delivery Ratio)", valueText: cell.pdr.toFixed(1) + "%",
    level: pdrStatus === "normal" ? "LOW" : "HIGH",
    why: pdrStatus === "normal" ? "reliable packet delivery" : "packet delivery is degraded relative to the healthy-network threshold" });

  items.push({ label: "Throughput", valueText: cell.throughput.toFixed(0) + " kbps",
    level: cell.throughput <= riskMedians.throughput ? "HIGH" : "LOW",
    why: cell.throughput <= riskMedians.throughput ? "delivered data rate is at or below the median across measured conditions" : "delivered data rate is above the median across measured conditions" });

  items.push({ label: "Average Delay", valueText: cell.delay.toFixed(0) + " ms",
    level: cell.delay >= riskMedians.delay ? "HIGH" : "LOW",
    why: cell.delay >= riskMedians.delay ? "may affect latency-sensitive IoT applications" : "latency is below the median across measured conditions" });

  items.push({ label: "Packet Loss", valueText: cell.loss.toFixed(0) + " pkts",
    level: cell.loss >= riskMedians.loss ? "HIGH" : "LOW",
    why: cell.loss >= riskMedians.loss ? "significant packet delivery degradation" : "packet loss is below the median across measured conditions" });

  if (protocol === "olsr") {
    items.push({ label: "Routing Overhead", valueText: cell.routing_overhead.toFixed(0) + " pkts", level: "LOW",
      why: "measured as 0 — known instrumentation coverage limitation, not confirmed zero overhead (see Performance Analysis)" });
  } else {
    items.push({ label: "Routing Overhead", valueText: cell.routing_overhead.toFixed(0) + " pkts",
      level: cell.routing_overhead >= riskMedians.routing_overhead ? "HIGH" : "LOW",
      why: cell.routing_overhead >= riskMedians.routing_overhead ? "control traffic is elevated relative to the median across measured conditions" : "relatively efficient routing overhead" });
  }

  if (protocol === "static") {
    items.push({ label: "Path Changes / Routing Stability", valueText: cell.path_changes.toFixed(1), level: "LOW",
      why: "0 by design — fixed shortest-path tree, routes never change (not a coverage gap)" });
  } else {
    items.push({ label: "Path Changes / Routing Stability", valueText: cell.path_changes.toFixed(1),
      level: cell.path_changes >= riskMedians.path_changes ? "HIGH" : "LOW",
      why: cell.path_changes >= riskMedians.path_changes ? "frequent route changes indicate routing instability" : "stable routing with few route changes" });
  }

  if (protocol === "olsr" || protocol === "static") {
    const bnCell = (DATA.bottleneck[protocol + "-high"] || []).find(d => d.n === n);
    if (bnCell) {
      const airStatus = statusFromAirtime(bnCell.gw_airtime);
      items.push({ label: "Gateway Airtime / Congestion", valueText: (bnCell.gw_airtime * 100).toFixed(0) + "% (high traffic)",
        level: airStatus === "normal" ? "LOW" : "HIGH",
        why: airStatus === "normal" ? "gateway channel is not congested" : "gateway channel congestion — primary measurable bottleneck mechanism" });
    }
  }

  const high = items.filter(it => it.level === "HIGH");
  const low = items.filter(it => it.level === "LOW");
  highEl.innerHTML = high.length ? high.map(riskItemHtml).join("")
    : '<p class="panel-sub" style="margin:0">No metrics currently flagged as high risk for this configuration.</p>';
  lowEl.innerHTML = low.length ? low.map(riskItemHtml).join("")
    : '<p class="panel-sub" style="margin:0">No metrics currently flagged as low risk for this configuration.</p>';
  const dBlk = nodeBlock(protocol, n, "delay");
  const dNote = dBlk && dBlk.excluded > 0 ? ` Average Delay uses n = ${dBlk.n} of ${dBlk.nTotal} seeds (${dBlk.excluded} seed excluded: undefined because no packets were received).` : "";
  ctxEl.textContent = `Showing: ${protocol.toUpperCase()}, N=${n} (Without-Risk baseline, pooled across traffic level and mobility mode).${dNote}`;
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
    if (cell) return { source: "V3 baseline (pooled across traffic & mobility: 99 runs = 11 seeds × 9 conditions) — not this exact condition", pdr: cell.pdr, throughput: cell.throughput, delay: bval(protocol, n, "delay"), pooled: true };
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

// ---------------------------------------------------------------- 3b. "How the network works" pipeline animation
// Illustrative only -- entirely separate from Route Traversal above (own state, own DOM ids,
// no shared variables). Positions two markers along the existing flow-node rows using their
// live DOM layout (getBoundingClientRect), not topology/coordinate data. Same play/pause/step/
// reset pattern as Route Traversal, but motion comes from a CSS transition on left/top rather
// than manual per-frame interpolation, since these are discrete flex boxes, not SVG coordinates.
let pipelineAnim = { step: 0, maxStep: 4, timer: null, playing: false, started: false };

function positionMarkerAlongRow(markerEl, nodeEls, progress) {
  if (!markerEl || !nodeEls.length) return;
  const n = nodeEls.length;
  const clamped = Math.max(0, Math.min(progress, 1)) * (n - 1);
  const i0 = Math.floor(clamped), i1 = Math.min(i0 + 1, n - 1), frac = clamped - i0;
  const containerRect = markerEl.parentElement.getBoundingClientRect();
  const r0 = nodeEls[i0].getBoundingClientRect(), r1 = nodeEls[i1].getBoundingClientRect();
  const x0 = r0.left + r0.width / 2 - containerRect.left, y0 = r0.top + r0.height / 2 - containerRect.top;
  const x1 = r1.left + r1.width / 2 - containerRect.left, y1 = r1.top + r1.height / 2 - containerRect.top;
  markerEl.style.left = (x0 + (x1 - x0) * frac) + "px";
  markerEl.style.top = (y0 + (y1 - y0) * frac) + "px";
}

function renderPipelineFrame() {
  const row1 = [...document.querySelectorAll("#flow-row-1 .flow-node")];
  const row2 = [...document.querySelectorAll("#flow-row-2 .flow-node")];
  const m1 = document.getElementById("flow-marker-1"), m2 = document.getElementById("flow-marker-2");
  const visible = pipelineAnim.started && (pipelineAnim.playing || pipelineAnim.step > 0);
  if (m1) m1.style.display = visible ? "block" : "none";
  if (m2) m2.style.display = visible ? "block" : "none";
  if (visible) {
    const progress = pipelineAnim.step / pipelineAnim.maxStep;
    positionMarkerAlongRow(m1, row1, progress);
    positionMarkerAlongRow(m2, row2, progress);
  }
  const caption = document.getElementById("pipeline-caption");
  if (caption) {
    if (!pipelineAnim.started) caption.textContent = "Press Play to begin.";
    else if (pipelineAnim.step >= pipelineAnim.maxStep) caption.textContent = "Illustrative animation — reached the sink / server.";
    else caption.textContent = "Illustrative animation — stage " + (pipelineAnim.step + 1) + " of " + (pipelineAnim.maxStep + 1) + ".";
  }
}
function playPipeline() {
  pipelineAnim.started = true;
  if (pipelineAnim.playing) return;
  pipelineAnim.playing = true;
  pipelineAnim.timer = setInterval(function () {
    pipelineAnim.step += 1;
    if (pipelineAnim.step >= pipelineAnim.maxStep) { pipelineAnim.step = pipelineAnim.maxStep; pausePipeline(); }
    renderPipelineFrame();
  }, 900);
  renderPipelineFrame();
}
function pausePipeline() {
  pipelineAnim.playing = false;
  if (pipelineAnim.timer) { clearInterval(pipelineAnim.timer); pipelineAnim.timer = null; }
}
function stepPipeline() {
  pausePipeline();
  pipelineAnim.started = true;
  pipelineAnim.step = Math.min(pipelineAnim.step + 1, pipelineAnim.maxStep);
  renderPipelineFrame();
}
function resetPipeline() {
  pausePipeline();
  pipelineAnim.step = 0;
  pipelineAnim.started = false;
  renderPipelineFrame();
}
function initPipelineAnimation() {
  const playBtn = document.getElementById("pipeline-play");
  const pauseBtn = document.getElementById("pipeline-pause");
  const stepBtn = document.getElementById("pipeline-step");
  const resetBtn = document.getElementById("pipeline-reset");
  if (playBtn) playBtn.addEventListener("click", playPipeline);
  if (pauseBtn) pauseBtn.addEventListener("click", pausePipeline);
  if (stepBtn) stepBtn.addEventListener("click", stepPipeline);
  if (resetBtn) resetBtn.addEventListener("click", resetPipeline);
  renderPipelineFrame();
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
const PERF_CHARTS = [
  ["chart-pdr", "line", "pdr", null, { unit: "%", yfmt: 0 }],
  ["chart-throughput", "line", "throughput", null, { unit: " kbps", yfmt: 0 }],
  ["chart-delay", "line", "delay", null, { unit: " ms", yfmt: 0 }],
  ["chart-loss", "line", "loss", null, { unit: " pkts", yfmt: 0 }],
  ["chart-jitter", "line", "jitter", null, { unit: " ms", yfmt: 1 }],
  ["chart-pdr-compare", "bar", "pdr", null, { unit: "%", yfmt: 0 }],
  ["chart-throughput-compare", "bar", "throughput", null, { unit: " kbps", yfmt: 0 }],
  ["chart-delay-compare", "bar", "delay", null, { unit: " ms", yfmt: 0 }],
  ["chart-loss-compare", "bar", "loss", null, { unit: " pkts", yfmt: 0 }],
  ["chart-routing-overhead", "bar", "routing_overhead", null, { unit: " pkts", yfmt: 0 }],
  ["chart-hopcount-v3", "line", "hop", null, { unit: " hops", yfmt: 2 }],
  ["chart-path-changes", "bar", "path_changes", null, { unit: "", yfmt: 0 }],
  ["chart-mlu", "bar", "link_util_max", 100, { unit: "%", yfmt: 1 }],
];
function drawPerfCharts() {
  legendOnce("perf-legend");
  PERF_CHARTS.forEach(([id, kind, metric, scale, o]) => {
    const c = document.getElementById(id);
    const series = activeSeries(metric, scale);
    if (kind === "line") lineChart(c, series, { colors: COLORS, ...o });
    else groupedBar(c, series, { colors: COLORS, ...o, xlabel: x => `N=${x}` });
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
  groupedBar(c, series, { colors: COLORS, unit: "%", yfmt: 0, xlabel: x => x });
  if (STATS) ciCaption(c, "bar", "Each bar: every seed&rsquo;s mean PDR over the 18 conditions (6 node counts &times; 3 mobility modes); the CI is taken across those 11 per-seed values.");
}

// ---------------------------------------------------------------- 6. bottleneck
function renderBottleneck() {
  const c1 = document.getElementById("chart-gw-airtime");
  legend(document.getElementById("bn-legend"), [["OLSR / high", "var(--olsr)"], ["Static / high", "var(--static)"]]);
  groupedBar(c1, {
    olsr: DATA.bottleneck["olsr-high"].map(d => ({ x: d.n, y: d.gw_airtime * 100 })),
    static: DATA.bottleneck["static-high"].map(d => ({ x: d.n, y: d.gw_airtime * 100 }))
  }, { colors: COLORS, unit: "%", yfmt: 0, xlabel: x => `N=${x}` });
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
  legend(document.getElementById("v4-tier1-legend"), [["V4 (Sigmoid-weighted)", "var(--v4)"], ["Static", "var(--static)"]]);
  groupedBar(document.getElementById("chart-v4-tier1-pdr"), {
    v4: DATA.v4_tier1.map((r, i) => ({ x: `Config${i + 1}`, y: r.pdr_v4 })),
    static: DATA.v4_tier1.map((r, i) => ({ x: `Config${i + 1}`, y: r.pdr_static }))
  }, { colors: { v4: "var(--v4)", static: "var(--static)" }, unit: "%", yfmt: 0, xlabel: x => x });

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
  }, { colors: { v4: "var(--v4)", static: "var(--static)" }, unit: "%", yfmt: 0, xlabel: x => `N=${x}` });
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
  lineChart(document.getElementById("chart-int-airtime"), { air: rows.map(d => ({ x: d.rate + "k", y: d.gw_airtime * 100 })) }, { colors: { air: "var(--warn)" }, unit: "%", yfmt: 0 });
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
  }, { colors: { "OLSR N=75": "var(--olsr)", "OLSR N=100": "var(--olsr-2)", "Static N=50": "var(--static)" }, unit: "%", yfmt: 0 });

  const tbody = document.getElementById("diag-table-body"); tbody.innerHTML = "";
  DATA.diagnostic.forEach(r => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${r.rate} kbps</td><td class="num">${r.seed}</td><td class="num">${r.attributable_pct.toFixed(2)}%</td><td class="num">${r.residual_pct.toFixed(2)}%</td>`;
    tbody.appendChild(tr);
  });
}

// ---------------------------------------------------------------- statistics layer: method note + undefined-metric detail
function renderStatMethod() {
  const set = (id, v) => { const e = document.getElementById(id); if (e) e.textContent = v; };
  if (!STATS) {
    const e = document.getElementById("sm-load-error");
    if (e) { e.style.display = "block"; e.textContent = "The statistics file data/v3ext-stats.json could not be loaded, so charts show means only. No confidence interval is drawn or estimated."; }
    return;
  }
  const d = STATS.meta.design, st = STATS.meta.statistics;
  set("sm-reps", `${d.replicationsPerCell} seeds (${d.seeds[0]}–${d.seeds[d.seeds.length - 1]})`);
  set("sm-df", String(d.replicationsPerCell - 1));
  set("sm-t", "≈ " + st.t_n11.toFixed(3));
  set("sm-cells", `${d.cells} / ${STATS.meta.source.officialRuns.toLocaleString()}`);
}
const UNDEF_ROWS = [["pdr", "PDR", "%", 2], ["throughput", "Throughput", " kbps", 2], ["loss", "Packet Loss", " pkts", 0],
                    ["delay", "Average Delay", " ms", 3], ["jitter", "Average Jitter", " ms", 3], ["hop", "Average Hop Count", " hops", 4]];
function renderUndefinedDetail() {
  const host = document.getElementById("undef-detail"); if (!host) return;
  if (!STATS) { host.innerHTML = ""; return; }
  const runs = STATS.meta.undefinedMetrics.runs;
  if (!runs.length) { host.innerHTML = '<p style="margin:8px 0 0">No run in the official baseline received zero packets, so no observation is excluded.</p>'; return; }
  host.innerHTML = runs.map(r => {
    const cell = STATS.cells.find(c => c.protocol === r.protocol && c.nodes === r.nodes && c.traffic === r.traffic && c.mobility === r.mobility);
    const rows = UNDEF_ROWS.map(([k, label, u, dp]) => {
      const b = cell.metrics[k], ex = b.excluded > 0;
      return `<tr><td>${label}</td><td>${ex ? `${b.n} of ${b.nTotal}` : b.n}</td><td>${b.df}</td><td>${b.mean.toFixed(dp)}${u}</td><td>&plusmn; ${b.ci95.toFixed(dp)}${u}</td><td>${ex ? "1 run excluded: undefined because no packets were received" : "all runs kept (real measurement)"}</td></tr>`;
    }).join("");
    const base = DATA.baseline[r.protocol].find(d => d.n === r.nodes);
    const fz = base ? `${base.delay.toFixed(2)} ms / ${base.jitter.toFixed(2)} ms / ${base.hop.toFixed(3)}` : "";
    const ex = ["delay", "jitter", "hop"].map(k => nodeBlock(r.protocol, r.nodes, k)).filter(Boolean);
    const ux = ex.length === 3 ? `${ex[0].mean.toFixed(2)} ms / ${ex[1].mean.toFixed(2)} ms / ${ex[2].mean.toFixed(3)}` : "";
    return `<div style="margin-top:10px"><strong>${r.protocol.toUpperCase()} &middot; ${r.nodes} nodes &middot; ${r.traffic} traffic &middot; ${r.mobility} mobility</strong> &mdash; seed ${r.seed} delivered ${r.packetsReceived} of ${r.packetsSent.toLocaleString()} packets. Its raw result is unchanged (stored delay / jitter / hop count = ${r.storedRawValue.delaySec}).
      <table><thead><tr><th>Metric</th><th>n</th><th>df</th><th>Mean</th><th>95% CI</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table>
      <p style="margin:8px 0 0;color:var(--text-dim)">In the ${r.protocol.toUpperCase()} @ N=${r.nodes} chart points (seed-level, 9 conditions) Delay, Jitter and Hop Count exclude seed ${r.seed} whole (n = 10 of 11, df = 9, t = 2.262). The frozen <code>final_research.json</code> summary averages the placeholder 0 into those points (Delay / Jitter / Hop = ${fz}); the charts use the exclusion-aware values ${ux}.</p></div>`;
  }).join("");
}

const V3S_DEC = { pdr: 2, throughput: 2, delay: 2, jitter: 2, loss: 1, routing_overhead: 1, hop: 4, path_changes: 2, link_util_avg: 5, link_util_max: 5 };
const V3S_LABEL = { pdr: "PDR", throughput: "Throughput", delay: "Average Delay", jitter: "Average Jitter", loss: "Packet Loss", routing_overhead: "Routing Overhead",
                    hop: "Average Hop Count", path_changes: "Path Changes", link_util_avg: "Avg Link Utilization", link_util_max: "Max Link Utilization" };
function initV3StatsExplorer() {
  const root = document.getElementById("v3stats-explorer"); if (!root) return;
  const note = document.getElementById("v3s-note");
  if (!STATS) { note.textContent = "Statistics unavailable: data/v3ext-stats.json could not be loaded."; return; }
  const $ = id => document.getElementById(id);
  const mSel = $("v3s-metric"), nSel = $("v3s-nodes");
  Object.keys(STATS.meta.units).forEach(k => { const o = document.createElement("option"); o.value = k; o.textContent = `${V3S_LABEL[k]} (${STATS.meta.units[k]})`; mSel.appendChild(o); });
  STATS.meta.design.nodes.forEach(n => { const o = document.createElement("option"); o.value = String(n); o.textContent = String(n); nSel.appendChild(o); });
  const draw = () => {
    const level = $("v3s-level").value, mk = mSel.value, pf = $("v3s-protocol").value, nf = nSel.value, tf = $("v3s-traffic").value, mf = $("v3s-mobility").value, onlyEx = $("v3s-only-excl").value === "yes";
    // Nodes filter applies to condition- and node-level rows, Traffic to condition- and traffic-level rows, Mobility to condition rows only.
    const visible = { nodes: level !== "traffic", traffic: level !== "nodes", mobility: level === "cells" };
    root.querySelectorAll(".filter-group[data-for]").forEach(g => { g.style.display = visible[g.dataset.for] ? "" : "none"; });
    let rows;
    if (level === "cells") rows = STATS.cells.map(c => ({ p: c.protocol, n: c.nodes, t: c.traffic, m: c.mobility, b: c.metrics[mk] }));
    else if (level === "nodes") rows = STATS.marginalNodes.map(r => ({ p: r.protocol, n: r.nodes, t: "all (9 conditions)", m: "", b: r.metrics[mk] }));
    else rows = STATS.marginalTraffic.map(r => ({ p: r.protocol, n: "all (18 conditions)", t: r.traffic, m: "", b: r.metrics[mk] }));
    rows = rows.filter(r => (pf === "all" || r.p === pf) && (nf === "all" || String(r.n) === nf || level === "traffic") && (tf === "all" || r.t === tf || level === "nodes") && (mf === "all" || r.m === mf || level !== "cells") && (!onlyEx || r.b.excluded > 0));
    const dp = V3S_DEC[mk], u = STATS.meta.units[mk] === "fraction" ? "" : " " + STATS.meta.units[mk];
    $("v3s-table").querySelector("thead").innerHTML = `<tr><th>Protocol</th><th>Nodes</th><th>Traffic</th><th>Mobility</th><th>n</th><th>Mean</th><th>SD</th><th>SE</th><th>95% CI (lower – upper)</th><th>df</th><th>t</th><th>Excluded</th></tr>`;
    $("v3s-table").querySelector("tbody").innerHTML = rows.map(r => {
      const b = r.b, ex = b.excluded > 0;
      const exTxt = ex ? (level === "cells" ? `${b.excluded} run excluded: undefined because no packets were received` : `seed ${b.excludedSeeds.join(", ")} excluded (undefined: no packets received in at least one of its runs)`) : "—";
      const ci = b.ci95 == null ? "n/a" : `${(b.mean - b.ci95).toFixed(dp)} – ${(b.mean + b.ci95).toFixed(dp)}`;
      return `<tr><td>${r.p.toUpperCase()}</td><td class="num">${r.n}</td><td>${r.t}</td><td>${r.m}</td><td class="num">${b.n}${ex ? ` of ${b.nTotal}` : ""}</td><td class="num">${b.mean.toFixed(dp)}</td><td class="num">${b.sd.toFixed(dp)}</td><td class="num">${b.se.toFixed(dp)}</td><td class="num">${ci}</td><td class="num">${b.df}</td><td class="num">${b.t}</td><td class="${ex ? "excl" : ""}">${exTxt}</td></tr>`;
    }).join("") || `<tr><td colspan="12" style="text-align:center;color:var(--text-faint)">No rows match the current filters.</td></tr>`;
    note.textContent = `${rows.length} row${rows.length === 1 ? "" : "s"} · values in${u || " fraction (0–1)"} · n = valid observations (of 11 seeds) · SD = sample SD (n−1) · SE = SD/√n · CI = mean ± t·SE with df = n−1 · the lower CI limit is shown raw (never clamped) in this table.`;
  };
  ["v3s-level", "v3s-metric", "v3s-protocol", "v3s-nodes", "v3s-traffic", "v3s-mobility", "v3s-only-excl"].forEach(id => $(id).addEventListener("change", draw));
  draw();
}

// ---------------------------------------------------------------- init
async function main() {
  DATA = await fetch("data/final_research.json").then(r => r.json());
  try { STATS = await fetch("data/v3ext-stats.json").then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }); } catch (e) { STATS = null; console.warn("v3ext-stats.json unavailable:", e); }
  renderStatMethod();
  renderUndefinedDetail();
  renderHero();
  renderHealth();
  computeRiskMedians();
  renderRiskSummary();
  renderTopoSection();
  initPipelineAnimation();
  renderPerformance();
  renderTrafficLoad();
  renderBottleneck();
  renderHopChart();
  renderRetry();
  renderV4();
  renderV4Matched();
  renderIntervention();
  renderStaticControl();
  if (typeof initRealWorldSection === "function") initRealWorldSection(DATA);
  if (typeof initDataExplorer === "function") initDataExplorer();
  initV3StatsExplorer();
  initNav();
}
document.addEventListener("DOMContentLoaded", main);
