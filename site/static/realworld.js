// "Real-World IoT Application Simulation" -- a conceptual smart-campus
// visualization connecting the NS-3 study to an illustrative real-world
// scenario. Node roles, positions, links, and routing-behaviour animations
// are illustrative only -- NOT derived from packet-level simulation traces.
// The only real data used anywhere in this file comes from /api/summary
// (the same endpoint the rest of the dashboard uses), for the metric cards.

const RW_GATEWAY = { x: 450, y: 260 };

// path: the fixed illustrative route from this sensor to the gateway,
// expressed as a sequence of node ids ('GW' = gateway). Hop count varies
// 1-4 by design, mirroring the multi-hop theme of the NS-3 study.
const RW_NODES = [
  { id: 0, x: 100, y: 80, role: "Temperature", icon: "\u{1F321}", zone: "Academic Building", path: [0, 1, 2, "GW"] },
  { id: 1, x: 200, y: 120, role: "Air Quality", icon: "\u{1F4A8}", zone: "Academic Building", path: [1, 2, "GW"] },
  { id: 2, x: 390, y: 250, role: "PM2.5", icon: "\u{1FAA7}", zone: "Central Plaza", path: [2, "GW"] },
  { id: 3, x: 680, y: 80, role: "Smart Lighting", icon: "\u{1F4A1}", zone: "Library", path: [3, 6, 2, "GW"] },
  { id: 4, x: 100, y: 440, role: "Parking (Lot A)", icon: "\u{1F17F}", zone: "Parking Lot A", path: [4, 8, 9, 12, "GW"] },
  { id: 5, x: 520, y: 250, role: "Water Monitoring", icon: "\u{1F4A7}", zone: "Central Plaza", path: [5, "GW"] },
  { id: 6, x: 450, y: 50, role: "Security Camera", icon: "\u{1F4F9}", zone: "Main Gate", path: [6, 2, "GW"] },
  { id: 7, x: 700, y: 260, role: "Emergency Detection", icon: "\u{1F6A8}", zone: "Residence Hall", path: [7, 14, 10, 5, "GW"] },
  { id: 8, x: 100, y: 260, role: "Environmental (Humidity)", icon: "\u{1F32B}", zone: "Green Park", path: [8, 9, 12, "GW"] },
  { id: 9, x: 180, y: 320, role: "Green Area / Soil Moisture", icon: "\u{1F331}", zone: "Green Park", path: [9, 12, "GW"] },
  { id: 10, x: 600, y: 340, role: "Smart Lighting (Zone B)", icon: "\u{1F4A1}", zone: "Walkway B", path: [10, 5, "GW"] },
  { id: 11, x: 780, y: 440, role: "Parking (Lot B)", icon: "\u{1F17F}", zone: "Parking Lot B", path: [11, 10, 5, "GW"] },
  { id: 12, x: 450, y: 320, role: "Noise Monitoring", icon: "\u{1F50A}", zone: "Central Plaza", path: [12, "GW"] },
  { id: 13, x: 780, y: 120, role: "Waste Bin Level", icon: "\u{1F5D1}", zone: "Library", path: [13, 3, 6, 2, "GW"] },
  { id: 14, x: 780, y: 320, role: "Energy Metering", icon: "⚡", zone: "Residence Hall", path: [14, 10, 5, "GW"] },
];

const RW_EDGES = [
  [0, 1], [1, 2], [2, "GW"], [3, 6], [13, 3], [6, 2], [8, 9], [9, 12],
  [12, "GW"], [4, 8], [7, 14], [14, 10], [10, 5], [5, "GW"], [11, 10],
];

const RW_ZONES = [
  { x: 30, y: 20, w: 250, h: 150, label: "Academic Building" },
  { x: 620, y: 20, w: 250, h: 150, label: "Library" },
  { x: 30, y: 200, w: 240, h: 170, label: "Green Park" },
  { x: 640, y: 200, w: 240, h: 170, label: "Residence Hall" },
  { x: 30, y: 390, w: 240, h: 120, label: "Parking Lot A" },
  { x: 640, y: 390, w: 240, h: 120, label: "Parking Lot B" },
];

const RW_PROTOCOL_LABELS = { aodv: "AODV", olsr: "OLSR", static: "Static" };

function rwNodePos(id) {
  if (id === "GW") return RW_GATEWAY;
  return RW_NODES.find((n) => n.id === id);
}

const rwState = { protocol: "aodv", source: 7 };
let rwWatchTimer = null;

function renderCampusStage() {
  const svg = document.getElementById("rw-topology-svg");
  let markup = "";

  RW_ZONES.forEach((z) => {
    markup += `<rect x="${z.x}" y="${z.y}" width="${z.w}" height="${z.h}" rx="10"
      fill="rgba(255,255,255,0.02)" stroke="rgba(255,255,255,0.07)" stroke-width="1"/>
      <text class="rw-zone-label" x="${z.x + 10}" y="${z.y + 18}">${z.label}</text>`;
  });

  RW_EDGES.forEach(([a, b]) => {
    const p1 = rwNodePos(a), p2 = rwNodePos(b);
    markup += `<line class="rw-edge" x1="${p1.x}" y1="${p1.y}" x2="${p2.x}" y2="${p2.y}"/>`;
    markup += `<line class="rw-route-flood" data-flood-edge="${a}-${b}" x1="${p1.x}" y1="${p1.y}" x2="${p2.x}" y2="${p2.y}"/>`;
  });

  RW_NODES.forEach((n) => {
    markup += `<g class="rw-node-pulse" data-node="${n.id}">
      <circle cx="${n.x}" cy="${n.y}" r="15" fill="#0a0e18" stroke="#3b82f6" stroke-width="1.6"/>
      <text class="rw-node-glyph" x="${n.x}" y="${n.y + 5}" text-anchor="middle">${n.icon}</text>
      <text class="rw-node-label" x="${n.x}" y="${n.y + 28}" text-anchor="middle">Node ${n.id}</text>
      <text class="rw-node-role" x="${n.x}" y="${n.y + 39}" text-anchor="middle">${n.role}</text>
    </g>`;
  });

  markup += `<g class="rw-gateway-pulse" data-node="GW">
    <circle cx="${RW_GATEWAY.x}" cy="${RW_GATEWAY.y}" r="22" fill="#132038" stroke="#22d3ee" stroke-width="2.2"/>
    <text x="${RW_GATEWAY.x}" y="${RW_GATEWAY.y + 6}" text-anchor="middle" font-size="18">\u{1F5A5}</text>
    <text class="rw-node-label" x="${RW_GATEWAY.x}" y="${RW_GATEWAY.y + 40}" text-anchor="middle" font-weight="700">Gateway / Server</text>
  </g>`;

  svg.innerHTML = markup;

  const select = document.getElementById("rw-source");
  select.innerHTML = "";
  RW_NODES.forEach((n) => {
    const opt = document.createElement("option");
    opt.value = n.id;
    opt.textContent = `Node ${n.id} — ${n.role}`;
    if (n.id === rwState.source) opt.selected = true;
    select.appendChild(opt);
  });
}

function rwPathD(sourceId) {
  const node = RW_NODES.find((n) => n.id === sourceId);
  return node.path.map((id) => rwNodePos(id)).map((p, i) => `${i === 0 ? "M" : "L"}${p.x},${p.y}`).join(" ");
}

function rwFloodEdgesForSource(sourceId) {
  // Every edge incident to any node on the source's own path -- an
  // illustrative stand-in for an AODV route-request flood, not a real
  // broadcast simulation.
  const node = RW_NODES.find((n) => n.id === sourceId);
  const onPath = new Set(node.path);
  return RW_EDGES.filter(([a, b]) => onPath.has(a) || onPath.has(b));
}

function rwClearRoute() {
  const svg = document.getElementById("rw-topology-svg");
  const old = svg.querySelector("#rw-route-path");
  if (old) old.remove();
  const oldPacket = svg.querySelector("#rw-packet");
  if (oldPacket) oldPacket.remove();
  svg.querySelectorAll(".rw-route-flood.active").forEach((el) => el.classList.remove("active"));
}

function rwStartRoute() {
  rwClearRoute();
  const svg = document.getElementById("rw-topology-svg");
  const caption = document.getElementById("rw-caption");
  const d = rwPathD(rwState.source);
  const protoClass = `rw-route-${rwState.protocol}`;

  const drawPathAndPacket = () => {
    const ns = "http://www.w3.org/2000/svg";
    const path = document.createElementNS(ns, "path");
    path.setAttribute("id", "rw-route-path");
    path.setAttribute("class", protoClass);
    path.setAttribute("d", d);
    svg.appendChild(path);

    const packet = document.createElementNS(ns, "circle");
    packet.setAttribute("id", "rw-packet");
    packet.setAttribute("r", "6");
    packet.setAttribute("fill", "#e7ebf5");
    const anim = document.createElementNS(ns, "animateMotion");
    anim.setAttribute("dur", "2.4s");
    anim.setAttribute("repeatCount", "indefinite");
    const mpath = document.createElementNS(ns, "mpath");
    mpath.setAttributeNS("http://www.w3.org/1999/xlink", "href", "#rw-route-path");
    anim.appendChild(mpath);
    packet.appendChild(anim);
    svg.appendChild(packet);
  };

  if (rwState.protocol === "aodv") {
    caption.textContent = `AODV: discovering a route from Node ${rwState.source} to the gateway (route request flooding)…`;
    const floodEdges = rwFloodEdgesForSource(rwState.source);
    floodEdges.forEach(([a, b], i) => {
      setTimeout(() => {
        const el = svg.querySelector(`[data-flood-edge="${a}-${b}"]`);
        if (el) el.classList.add("active");
      }, i * 90);
    });
    setTimeout(() => {
      svg.querySelectorAll(".rw-route-flood.active").forEach((el) => el.classList.remove("active"));
      drawPathAndPacket();
      caption.textContent = `AODV: route established — data now flows Node ${rwState.source} → Gateway (reactive, on-demand).`;
    }, floodEdges.length * 90 + 500);
  } else if (rwState.protocol === "olsr") {
    caption.textContent = `OLSR: routes are already maintained proactively across the mesh — forwarding starts immediately.`;
    RW_EDGES.forEach(([a, b]) => {
      const el = svg.querySelector(`[data-flood-edge="${a}-${b}"]`);
      if (el) el.classList.add("active");
    });
    drawPathAndPacket();
  } else {
    caption.textContent = `Static: a fixed, pre-computed route is used — it never changes, regardless of live conditions.`;
    drawPathAndPacket();
  }
}

function rwPauseRoute() {
  const svg = document.getElementById("rw-topology-svg");
  if (svg.animationsPaused && svg.animationsPaused()) svg.unpauseAnimations();
  else svg.pauseAnimations();
}

function rwResetRoute() {
  const svg = document.getElementById("rw-topology-svg");
  svg.setCurrentTime(0);
  svg.unpauseAnimations();
}

// Pluggable so the static (GitHub Pages) build can supply summary rows from
// pre-loaded local JSON instead of a live Flask endpoint -- see site/static/site.js.
window.rwFetchSummary =
  window.rwFetchSummary ||
  (async (protocol) => {
    const res = await fetch("/api/summary?" + new URLSearchParams({ protocol, nodes: "all", trial: "all" }));
    return res.json();
  });

async function rwRefreshMetrics() {
  const rows = await window.rwFetchSummary(rwState.protocol);
  const box = document.getElementById("rw-metrics");
  if (!rows.length) { box.innerHTML = "<p class='chart-note'>No V2.7 data for this protocol.</p>"; return; }
  const avg = (key) => rows.reduce((s, r) => s + r[key], 0) / rows.length;
  box.innerHTML = `
    <div class="kpi-card glass"><div class="kpi-value">${avg("pdrMean").toFixed(1)}%</div><div class="kpi-label">PDR (mean)</div></div>
    <div class="kpi-card glass"><div class="kpi-value">${avg("throughputMean").toFixed(1)}</div><div class="kpi-label">Throughput (kbps)</div></div>
    <div class="kpi-card glass"><div class="kpi-value">${(avg("delayMean") * 1000).toFixed(1)}</div><div class="kpi-label">Delay (ms)</div></div>
    <div class="kpi-card glass"><div class="kpi-value">${avg("lossMean").toFixed(0)}</div><div class="kpi-label">Packet loss (pkts)</div></div>
  `;
}

function rwSetProtocol(protocol) {
  rwState.protocol = protocol;
  document.querySelectorAll("#rw-protocol-tabs .tab").forEach((b) => b.classList.toggle("active", b.dataset.protocol === protocol));
  rwStartRoute();
  rwRefreshMetrics();
}

// ---------------- 60-second guided walkthrough ----------------
function rwWatchSimulation() {
  if (rwWatchTimer) clearInterval(rwWatchTimer);
  const caption = document.getElementById("rw-caption");
  const progressWrap = document.getElementById("rw-progress");
  const progressBar = document.getElementById("rw-progress-bar");
  progressWrap.style.display = "block";

  const phases = [
    { at: 0, text: "Welcome to a Smart Campus — 15 IoT sensors report conditions across the grounds to a central gateway.", action: () => rwClearRoute() },
    { at: 10, text: "IoT sensors continuously generate data: temperature, air quality, parking, lighting, security, and more.", action: () => rwPulseAllNodes() },
    { at: 20, text: `Data travels through multiple wireless hops — watch Node ${rwState.source}'s packet relay toward the gateway.`, action: () => rwStartRoute() },
    { at: 35, text: "Different routing protocols handle this differently: AODV discovers routes on demand, OLSR maintains them proactively, Static uses a fixed path.", action: () => rwCycleProtocols() },
    { at: 45, text: "The Gateway and Server receive and consolidate the incoming sensor data.", action: () => rwPulseGateway() },
    { at: 55, text: "Network performance can then be measured using PDR, Throughput, Delay, and Packet Loss — from the actual V2.7 NS-3 experiments below.", action: () => document.getElementById("rw-metrics").parentElement.scrollIntoView({ behavior: "smooth", block: "nearest" }) },
  ];
  let firedIndex = 0;
  const startTime = Date.now();

  rwWatchTimer = setInterval(() => {
    const elapsed = Date.now() - startTime;
    progressBar.style.width = Math.min(100, (elapsed / 60000) * 100) + "%";

    while (firedIndex < phases.length && elapsed >= phases[firedIndex].at * 1000) {
      caption.textContent = phases[firedIndex].text;
      phases[firedIndex].action();
      firedIndex++;
    }
    if (elapsed >= 60000) {
      clearInterval(rwWatchTimer);
      rwWatchTimer = null;
      setTimeout(() => { progressWrap.style.display = "none"; }, 800);
    }
  }, 200);
}

function rwPulseAllNodes() {
  const svg = document.getElementById("rw-topology-svg");
  RW_NODES.forEach((n, i) => {
    setTimeout(() => {
      const el = svg.querySelector(`.rw-node-pulse[data-node="${n.id}"]`);
      if (!el) return;
      el.classList.add("active");
      setTimeout(() => el.classList.remove("active"), 400);
    }, i * 60);
  });
}

function rwPulseGateway() {
  const svg = document.getElementById("rw-topology-svg");
  const el = svg.querySelector('.rw-gateway-pulse[data-node="GW"]');
  if (!el) return;
  el.classList.add("active");
  setTimeout(() => el.classList.remove("active"), 3000);
}

function rwCycleProtocols() {
  const order = ["aodv", "olsr", "static"];
  order.forEach((p, i) => {
    setTimeout(() => rwSetProtocol(p), i * 3000);
  });
}

function rwInit() {
  renderCampusStage();

  document.querySelectorAll("#rw-protocol-tabs .tab").forEach((btn) => {
    btn.addEventListener("click", () => rwSetProtocol(btn.dataset.protocol));
  });
  document.getElementById("rw-source").addEventListener("change", (e) => {
    rwState.source = Number(e.target.value);
    rwStartRoute();
  });
  document.getElementById("rw-start").addEventListener("click", () => rwStartRoute());
  document.getElementById("rw-pause").addEventListener("click", () => rwPauseRoute());
  document.getElementById("rw-reset").addEventListener("click", () => rwResetRoute());
  document.getElementById("rw-watch").addEventListener("click", () => rwWatchSimulation());

  rwRefreshMetrics();
}

document.addEventListener("DOMContentLoaded", rwInit);
