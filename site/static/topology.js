// Interactive Network Topology engine -- shared, unchanged, between the
// local Flask dashboard and the public GitHub Pages static site. The only
// difference between the two deployments is how real per-scenario rows are
// fetched (see the two bootstrap calls at the bottom of each site's HTML);
// everything else here is identical.
//
// Positions/links are an illustrative, deterministic layout sized to the
// REAL selected experiment's node count (10/20/30/50 -- never invented).
// V2.7 stores no per-run coordinates, so every per-node field in the
// inspector says so honestly rather than fabricating a value.

const TopologyEngine = (function () {
  const GATEWAY = { x: 450, y: 500 };
  const RING_RADII = [90, 170, 250];
  const RING_ANGLE_START = 190;
  const RING_ANGLE_SPAN = 160;
  const PROTOCOL_LABELS = { aodv: "AODV", olsr: "OLSR", static: "Static" };

  let layout = { nodes: [], edges: [], ringNodeIds: [[], [], []] };
  let zoomBox = { x: 0, y: 0, w: 900, h: 560 };
  const BASE_BOX = { x: 0, y: 0, w: 900, h: 560 };

  let getRow = async () => null; // (protocol, nodes, seed) -> real row or null
  let meta = { networkSizes: [10, 20, 30, 50], protocols: ["aodv", "olsr", "static"], trials: [1, 2, 3, 4, 5] };
  let state = { nodes: 10, protocol: "aodv", seed: 1 };

  function deg2rad(d) { return (d * Math.PI) / 180; }
  function fmt(v, d) { return v === null || v === undefined || Number.isNaN(v) ? "-" : Number(v).toFixed(d); }

  function buildLayout(n) {
    const ringCounts = [];
    let remaining = n;
    for (let r = 0; r < RING_RADII.length; r++) {
      const isLast = r === RING_RADII.length - 1;
      const c = isLast ? remaining : Math.ceil(n / RING_RADII.length);
      ringCounts.push(Math.min(c, remaining));
      remaining -= ringCounts[r];
    }
    const nodes = [];
    let id = 0;
    const ringNodeIds = [[], [], []];
    for (let r = 0; r < RING_RADII.length; r++) {
      const count = ringCounts[r];
      for (let k = 0; k < count; k++) {
        const deg = RING_ANGLE_START + (RING_ANGLE_SPAN * (k + 0.5)) / Math.max(count, 1);
        const rad = deg2rad(deg);
        const x = GATEWAY.x + RING_RADII[r] * Math.cos(rad);
        const y = GATEWAY.y + RING_RADII[r] * Math.sin(rad);
        nodes.push({ id, x, y, ring: r });
        ringNodeIds[r].push(id);
        id++;
      }
    }
    const edges = [];
    for (let r = 0; r < RING_RADII.length; r++) {
      const ids = ringNodeIds[r];
      for (let k = 0; k < ids.length - 1; k++) edges.push([ids[k], ids[k + 1]]);
      if (r === 0) {
        ids.forEach((nid) => edges.push([nid, "GW"]));
      } else {
        const prevIds = ringNodeIds[r - 1];
        ids.forEach((nid, k) => { if (prevIds.length) edges.push([nid, prevIds[k % prevIds.length]]); });
      }
    }
    return { nodes, edges, ringNodeIds };
  }

  function nodePos(id) { return id === "GW" ? GATEWAY : layout.nodes.find((n) => n.id === id); }
  function edgeLength(a, b) { const p1 = nodePos(a), p2 = nodePos(b); return Math.hypot(p1.x - p2.x, p1.y - p2.y); }

  function traceToGateway(startId) {
    const path = [startId];
    let cur = startId;
    let ring = layout.nodes.find((n) => n.id === cur).ring;
    while (ring > 0) {
      const prevIds = layout.ringNodeIds[ring - 1];
      const idxInRing = layout.ringNodeIds[ring].indexOf(cur);
      const next = prevIds[idxInRing % prevIds.length];
      path.push(next);
      cur = next;
      ring -= 1;
    }
    path.push("GW");
    return path;
  }
  function conceptualRoute() {
    const ring = layout.ringNodeIds[2].length ? 2 : layout.ringNodeIds[1].length ? 1 : 0;
    return traceToGateway(layout.ringNodeIds[ring][0]);
  }

  function svgMarkup() {
    let markup = `<g data-layer="basemap">
      <rect x="20" y="20" width="860" height="520" rx="16" fill="rgba(255,255,255,0.015)" stroke="rgba(255,255,255,0.05)"/>
      <text x="36" y="42" fill="#8b93a7" font-size="11" letter-spacing="0.03em">ILLUSTRATIVE SIMULATION FIELD</text>
    </g>`;

    const edgesMarkup = layout.edges.map(([a, b]) => {
      const p1 = nodePos(a), p2 = nodePos(b);
      const len = edgeLength(a, b);
      return `<line class="topo-edge" data-a="${a}" data-b="${b}" data-len="${len.toFixed(1)}"
        x1="${p1.x}" y1="${p1.y}" x2="${p2.x}" y2="${p2.y}"
        stroke="rgba(255,255,255,0.14)" stroke-width="1.6"/>`;
    }).join("");
    markup += `<g data-layer="links">${edgesMarkup}</g>`;

    markup += `<g data-layer="range" style="display:none;">
      ${layout.nodes.map((n) => `<circle class="range-circle" data-node="${n.id}" cx="${n.x}" cy="${n.y}" r="0" fill="none" stroke="rgba(34,211,238,0.35)" stroke-dasharray="4 4"/>`).join("")}
    </g>`;

    const nodesMarkup = layout.nodes.map((n) => `<g class="topo-node" data-node="${n.id}" tabindex="0">
      <circle cx="${n.x}" cy="${n.y}" r="13" fill="#0a0e18" stroke="#3b82f6" stroke-width="1.6"/>
      <text x="${n.x}" y="${n.y + 4}" text-anchor="middle" font-size="10" fill="#e7ebf5">${n.id}</text>
    </g>`).join("");
    markup += `<g data-layer="nodes">${nodesMarkup}</g>`;

    markup += `<g data-layer="gateway">
      <circle cx="${GATEWAY.x}" cy="${GATEWAY.y}" r="20" fill="#132038" stroke="#22d3ee" stroke-width="2.2"/>
      <text x="${GATEWAY.x}" y="${GATEWAY.y + 5}" text-anchor="middle" font-size="16">\u{1F5A5}</text>
      <text x="${GATEWAY.x}" y="${GATEWAY.y + 34}" text-anchor="middle" font-size="10" font-weight="700" fill="#e7ebf5">Gateway / Sink</text>
    </g>`;
    return markup;
  }

  function render() {
    const svg = document.getElementById("topo-svg");
    if (!svg) return;
    layout = buildLayout(state.nodes);
    svg.innerHTML = svgMarkup();
    svg.querySelectorAll(".topo-node").forEach((el) => {
      el.addEventListener("click", () => selectNode(Number(el.dataset.node)));
    });
    applyLayerVisibility();
    const slider = document.getElementById("topo-range-slider");
    if (slider) applyRangeVisualization(Number(slider.value));
    clearRouteAnim();
    document.getElementById("topo-experiment-readout").textContent =
      `${state.nodes} nodes, ${PROTOCOL_LABELS[state.protocol]}, seed ${state.seed}`;
    resetNodeInspector();
    refreshResultPanel();
  }

  function selectNode(id) {
    document.querySelectorAll(".topo-node").forEach((el) => el.classList.toggle("active", Number(el.dataset.node) === id));
    const na = '<span class="na">N/A — Not recorded in V2.7</span>';
    document.getElementById("topo-node-inspector").innerHTML = `
      <h3>Node Inspector &mdash; Node ${id}</h3>
      <dl class="inspector-fields">
        <dt>Status</dt><dd>${na}</dd>
        <dt>Protocol</dt><dd>${PROTOCOL_LABELS[state.protocol]} <span class="small-note-inline">(selected experiment)</span></dd>
        <dt>Seed</dt><dd>${state.seed} <span class="small-note-inline">(selected experiment)</span></dd>
        <dt>Network size</dt><dd>${state.nodes} nodes <span class="small-note-inline">(selected experiment)</span></dd>
        <dt>Neighbors</dt><dd>${na}</dd>
        <dt>Position</dt><dd>${na} <span class="small-note-inline">(illustrative marker only)</span></dd>
        <dt>Route to Gateway</dt><dd>${na}</dd>
        <dt>Hop Count</dt><dd>${na}</dd>
        <dt>Packets / PDR</dt><dd>${na} <span class="small-note-inline">(only aggregate totals recorded — see Experiment Result)</span></dd>
      </dl>
    `;
  }
  function resetNodeInspector() {
    document.getElementById("topo-node-inspector").innerHTML =
      `<h3>Node Inspector</h3><p class="chart-note">Click a node to inspect it.</p>`;
  }

  async function refreshResultPanel() {
    const row = await getRow(state.protocol, state.nodes, state.seed);
    const box = document.getElementById("topo-result-panel");
    if (!row) {
      box.innerHTML = `<h3>Experiment Result</h3><p class="chart-note">No matching V2.7 run for this combination.</p>`;
      return;
    }
    box.innerHTML = `
      <h3>Experiment Result <span class="badge badge-actual">ACTUAL DATA</span></h3>
      <dl class="inspector-fields">
        <dt>Protocol</dt><dd>${PROTOCOL_LABELS[row.protocol] || row.protocol}</dd>
        <dt>Nodes</dt><dd>${row.nodes}</dd>
        <dt>Seed</dt><dd>${row.trial}</dd>
        <dt>PDR</dt><dd>${fmt(row.pdr, 2)} %</dd>
        <dt>Throughput</dt><dd>${fmt(row.throughputKbps, 2)} kbps</dd>
        <dt>Packet Loss</dt><dd>${row.packetLoss} packets</dd>
        <dt>Average Delay</dt><dd>${fmt(row.delaySec, 4)} s</dd>
      </dl>
      <p class="data-source-note"><strong>Source:</strong> <code>${row.sourceFile || (row.protocol + "_" + row.nodes + ".csv")}</code></p>
    `;
    document.getElementById("topo-topology-panel").innerHTML = `
      <dl class="inspector-fields">
        <dt>Total Nodes</dt><dd>${row.nodes}</dd>
        <dt>Connected Nodes</dt><dd><span class="na">N/A</span></dd>
        <dt>Unreachable Nodes</dt><dd><span class="na">N/A</span></dd>
        <dt>Links</dt><dd><span class="na">N/A</span></dd>
        <dt>Average Hop Count</dt><dd><span class="na">N/A</span></dd>
      </dl>
      <p class="small-note">Per-node connectivity is not recorded in V2.7's result CSVs (aggregate metrics only) — these fields cannot be calculated without re-instrumenting the simulation.</p>
    `;
  }

  function applyLayerVisibility() {
    const svg = document.getElementById("topo-svg");
    ["basemap", "nodes", "links", "gateway", "range"].forEach((layerKey) => {
      const cb = document.getElementById(`topo-layer-${layerKey}`);
      const group = svg.querySelector(`[data-layer="${layerKey}"]`);
      if (cb && group) group.style.display = cb.checked ? "" : "none";
    });
  }

  function applyRangeVisualization(rangeM) {
    const svg = document.getElementById("topo-svg");
    if (!svg) return;
    const pxPerM = RING_RADII[0] / 60;
    const rangePx = rangeM * pxPerM;
    svg.querySelectorAll(".range-circle").forEach((c) => c.setAttribute("r", rangePx));
    svg.querySelectorAll(".topo-edge").forEach((el) => {
      el.classList.toggle("out-of-range", Number(el.dataset.len) > rangePx);
    });
  }

  function attachPanZoom() {
    const svg = document.getElementById("topo-svg");
    if (!svg) return;
    zoomBox = { ...BASE_BOX };
    let dragging = false, last = null;
    svg.addEventListener("mousedown", (e) => { dragging = true; last = { x: e.clientX, y: e.clientY }; });
    window.addEventListener("mouseup", () => { dragging = false; last = null; });
    window.addEventListener("mousemove", (e) => {
      if (!dragging || !last) return;
      const scale = zoomBox.w / svg.clientWidth;
      zoomBox.x -= (e.clientX - last.x) * scale;
      zoomBox.y -= (e.clientY - last.y) * scale;
      last = { x: e.clientX, y: e.clientY };
      updateViewBox();
    });
    svg.addEventListener("wheel", (e) => { e.preventDefault(); zoom(e.deltaY < 0 ? 0.9 : 1.1); }, { passive: false });
    document.getElementById("topo-zoom-in").addEventListener("click", () => zoom(0.85));
    document.getElementById("topo-zoom-out").addEventListener("click", () => zoom(1.18));
    document.getElementById("topo-zoom-reset").addEventListener("click", () => { zoomBox = { ...BASE_BOX }; updateViewBox(); });
  }
  function zoom(factor) {
    const cx = zoomBox.x + zoomBox.w / 2, cy = zoomBox.y + zoomBox.h / 2;
    zoomBox.w = Math.min(BASE_BOX.w * 2.5, Math.max(BASE_BOX.w * 0.35, zoomBox.w * factor));
    zoomBox.h = Math.min(BASE_BOX.h * 2.5, Math.max(BASE_BOX.h * 0.35, zoomBox.h * factor));
    zoomBox.x = cx - zoomBox.w / 2;
    zoomBox.y = cy - zoomBox.h / 2;
    updateViewBox();
  }
  function updateViewBox() {
    document.getElementById("topo-svg").setAttribute("viewBox", `${zoomBox.x} ${zoomBox.y} ${zoomBox.w} ${zoomBox.h}`);
  }

  function clearRouteAnim() {
    const svg = document.getElementById("topo-svg");
    const old = svg.querySelector("#topo-route-path");
    if (old) old.remove();
    const oldPacket = svg.querySelector("#topo-packet");
    if (oldPacket) oldPacket.remove();
  }
  function startAnim() {
    clearRouteAnim();
    const svg = document.getElementById("topo-svg");
    const route = conceptualRoute();
    const d = route.map((id) => nodePos(id)).map((p, i) => `${i === 0 ? "M" : "L"}${p.x},${p.y}`).join(" ");
    const ns = "http://www.w3.org/2000/svg";
    const path = document.createElementNS(ns, "path");
    path.setAttribute("id", "topo-route-path");
    path.setAttribute("d", d);
    path.setAttribute("stroke", "#3b82f6"); path.setAttribute("stroke-width", "2.4"); path.setAttribute("fill", "none");
    svg.appendChild(path);
    const packet = document.createElementNS(ns, "circle");
    packet.setAttribute("id", "topo-packet"); packet.setAttribute("r", "6"); packet.setAttribute("fill", "#e7ebf5");
    const anim = document.createElementNS(ns, "animateMotion");
    anim.setAttribute("dur", "2.6s"); anim.setAttribute("repeatCount", "indefinite");
    const mpath = document.createElementNS(ns, "mpath");
    mpath.setAttributeNS("http://www.w3.org/1999/xlink", "href", "#topo-route-path");
    anim.appendChild(mpath); packet.appendChild(anim);
    svg.appendChild(packet);
  }
  function pauseAnim() {
    const svg = document.getElementById("topo-svg");
    if (svg.animationsPaused && svg.animationsPaused()) svg.unpauseAnimations();
    else svg.pauseAnimations();
  }
  function resetAnim() {
    const svg = document.getElementById("topo-svg");
    svg.setCurrentTime(0);
    svg.unpauseAnimations();
  }

  function populateSelectors() {
    const nodesSel = document.getElementById("topo-sel-nodes");
    const protoSel = document.getElementById("topo-sel-protocol");
    const seedSel = document.getElementById("topo-sel-seed");
    nodesSel.innerHTML = meta.networkSizes.map((n) => `<option value="${n}">${n} nodes</option>`).join("");
    protoSel.innerHTML = meta.protocols.map((p) => `<option value="${p}">${PROTOCOL_LABELS[p] || p}</option>`).join("");
    seedSel.innerHTML = meta.trials.map((s) => `<option value="${s}">Seed ${s}</option>`).join("");
    nodesSel.value = state.nodes; protoSel.value = state.protocol; seedSel.value = state.seed;

    const onChange = () => {
      state.nodes = Number(nodesSel.value);
      state.protocol = protoSel.value;
      state.seed = Number(seedSel.value);
      render();
    };
    nodesSel.addEventListener("change", onChange);
    protoSel.addEventListener("change", onChange);
    seedSel.addEventListener("change", onChange);
  }

  function init(options) {
    getRow = options.getRow;
    meta = options.meta || meta;
    state.nodes = meta.networkSizes[0] || 10;
    state.protocol = meta.protocols[0] || "aodv";
    state.seed = meta.trials[0] || 1;

    populateSelectors();
    render();
    attachPanZoom();

    document.querySelectorAll('#topo-layers-panel input[type="checkbox"]').forEach((cb) => {
      cb.addEventListener("change", applyLayerVisibility);
    });
    const slider = document.getElementById("topo-range-slider");
    slider.addEventListener("input", (e) => {
      document.getElementById("topo-range-value").textContent = e.target.value + " m";
      applyRangeVisualization(Number(e.target.value));
    });
    document.getElementById("topo-play").addEventListener("click", startAnim);
    document.getElementById("topo-pause").addEventListener("click", pauseAnim);
    document.getElementById("topo-reset").addEventListener("click", resetAnim);
  }

  return { init };
})();
