// PSU Phuket smart-campus case study (proposed, not a deployment). Map data: data/campus/campus.json, built by
// experiments/wifi6-risk/build_site_campus.py from a frozen OpenStreetMap snapshot (© OpenStreetMap contributors,
// ODbL). Two modes: a conceptual deployment derived by a fixed rule from OSM features (links and trees computed here
// with the simulator's Static / Risk-Aware rules: an illustration, not a simulation), and the validated ns-3
// topologies (data/topology/*.json, measured coordinates and routes) placed at true scale on the map.
(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const TX = 90, BETA = 10, R_HIGH = 0.5, FIELD = 250;
  const APPS = {
    environmental: { label: "Environmental monitoring", color: "#0b5d53", rule: "centroid of each campus building", examples: "temperature, humidity, PM2.5, CO₂ at buildings" },
    traffic: { label: "Traffic monitoring", color: "#5b3aa8", rule: "junctions of campus roads", examples: "vehicle counts and parking occupancy at road junctions" },
    lighting: { label: "Smart lighting", color: "#a85f0f", rule: "every 70 m along roads and footways", examples: "street-light status, dimming and fault reports along roads and paths" },
    flood: { label: "Flood monitoring", color: "#0e6f9c", rule: "N / E / S / W edges of campus water bodies", examples: "water level and rainfall at ponds" }
  };
  const PROTO = { static: ["Static", "#4C72B0"], riskaware: ["Risk-Aware", "#DD8452"], olsr: ["OLSR", "#55A868"], aodv: ["AODV", "#C44E52"] };
  let C = null, RP = null, IDX = null, T = null, map = null, base = null, over = null;
  const tcache = {};
  const S = { mode: "proposed", gw: null, sel: null,
    p: { apps: new Set(Object.keys(APPS)), view: "both", links: true, k: 3, rule: "subtree", P: 101, manual: new Set() },
    v: { n: 100, seed: 20, place: "subtree", rate: 8, k: 3, proto: "riskaware", links: false, routes: true, traffic: false } };

  // ---------------------------------------------------------------- geometry
  const toXY = ll => [(ll[1] - C.frame.lon0) * C.frame.m_per_deg_lon, (ll[0] - C.frame.lat0) * C.frame.m_per_deg_lat];
  const toLL = xy => [C.frame.lat0 + xy[1] / C.frame.m_per_deg_lat, C.frame.lon0 + xy[0] / C.frame.m_per_deg_lon];
  function inside(pt, poly) {
    let c = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      const [x1, y1] = poly[i], [x2, y2] = poly[j];
      if ((y1 > pt[1]) !== (y2 > pt[1]) && pt[0] < (x2 - x1) * (pt[1] - y1) / (y2 - y1) + x1) c = !c;
    }
    return c;
  }
  const gwSite = () => C.proposed.gateways.find(g => g.id === S.gw);

  // ---------------------------------------------------------------- routing (the simulator's rules, lines 910-1056)
  function graph(P) {   // P: positions, gateway last; neighbours in ascending index order like the simulator
    const n = P.length, adj = Array.from({ length: n }, () => []);
    for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) if (Math.hypot(P[i][0] - P[j][0], P[i][1] - P[j][1]) <= TX) { adj[i].push(j); adj[j].push(i); }
    adj.forEach(a => a.sort((x, y) => x - y));
    const gw = n - 1, hop = Array(n).fill(-1), par = Array(n).fill(-1), q = [gw];
    hop[gw] = 0;
    for (let h = 0; h < q.length; h++) { const u = q[h]; for (const v of adj[u]) if (hop[v] < 0) { hop[v] = hop[u] + 1; par[v] = u; q.push(v); } }
    return { n, gw, adj, hop, par };
  }
  function riskAware(G, high) {
    const tau = Array(G.n).fill(0);
    high.forEach(i => { tau[i] = -Math.log1p(-R_HIGH); });
    const dist = Array(G.n).fill(Infinity), par = Array(G.n).fill(-1), done = Array(G.n).fill(false);
    let order = 0;
    const pq = [[0, order++, G.gw]];
    dist[G.gw] = 0;
    while (pq.length) {
      pq.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
      const [d, , v] = pq.shift();
      if (done[v]) continue;
      done[v] = true;
      const w = 1 + BETA * (v === G.gw ? 0 : tau[v]);
      for (const u of G.adj[v]) if (!done[u] && d + w < dist[u]) { dist[u] = d + w; par[u] = v; pq.push([dist[u], order++, u]); }
    }
    return { par, dist, tau };
  }
  function sm64(x) {   // SplitMix64 on BigInt, as in the simulator and run_n100_randplace.py
    const M = (1n << 64n) - 1n;
    x = (x + 0x9E3779B97F4A7C15n) & M;
    x = ((x ^ (x >> 30n)) * 0xBF58476D1CE4E5B9n) & M;
    x = ((x ^ (x >> 27n)) * 0x94D049BB133111EBn) & M;
    return x ^ (x >> 31n);
  }
  function pickRisky(G, nSensors) {
    const k = S.p.k;
    if (k === 0) return [];
    if (S.p.rule === "manual") return [...S.p.manual].filter(i => i < nSensors);
    if (S.p.rule === "uniform") {
      const h0 = sm64(BigInt(S.p.P));
      return [...Array(nSensors).keys()].map(i => [sm64(h0 ^ BigInt(i)), i]).sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : a[1] - b[1])).slice(0, k).map(x => x[1]);
    }
    const desc = Array(G.n).fill(0);   // subtree rule: most BFS descendants, then degree, then lower id
    for (let i = 0; i < nSensors; i++) for (let a = G.par[i]; a >= 0 && a !== G.gw; a = G.par[a]) desc[a]++;
    return [...Array(nSensors).keys()].filter(i => G.hop[i] >= 1 && desc[i] >= 1)
      .sort((a, b) => desc[b] - desc[a] || G.adj[b].length - G.adj[a].length || a - b).slice(0, k);
  }
  const walk = (par, i, gw) => { const p = [i]; while (p[p.length - 1] !== gw && par[p[p.length - 1]] >= 0 && p.length < 500) p.push(par[p[p.length - 1]]); return p; };

  // ---------------------------------------------------------------- controls
  function pills(container, options, active, onChange, multi) {
    container.innerHTML = "";
    options.forEach(([val, text]) => {
      const on = multi ? active.has(val) : val === active;
      const b = document.createElement("button");
      b.type = "button"; b.className = "pill" + (on ? " active" : ""); b.textContent = text;
      b.setAttribute("aria-pressed", on ? "true" : "false");
      b.addEventListener("click", () => onChange(val));
      container.appendChild(b);
    });
  }
  function group(label, id) { return `<div class="filter-group"><span class="fl">${label}</span><div id="${id}" class="pillrow"></div></div>`; }

  function renderControls() {
    pills($("cs-mode"), [["proposed", "Proposed smart-campus deployment"]].concat(IDX ? [["validated", "Validated ns-3 simulation topology"]] : []), S.mode, v => { S.mode = v; S.sel = null; render(); });
    const box = $("cs-controls");
    if (S.mode === "proposed") {
      box.innerHTML = group("Applications", "cs-apps-t") + group("Routing view", "cs-view") + group("High-risk relays k", "cs-k") + group("Risk placement", "cs-rule") +
        (S.p.rule === "uniform" ? group("Placement seed", "cs-P") : "") + group("Layers", "cs-pl");
      pills($("cs-apps-t"), Object.entries(APPS).map(([k, a]) => [k, a.label]), S.p.apps, v => { S.p.apps.has(v) && S.p.apps.size > 1 ? S.p.apps.delete(v) : S.p.apps.add(v); S.sel = null; S.p.manual.clear(); render(); }, true);
      pills($("cs-view"), [["both", "Static and Risk-Aware"], ["static", "Static"], ["riskaware", "Risk-Aware"]], S.p.view, v => { S.p.view = v; render(); });
      pills($("cs-k"), [0, 1, 2, 3].map(k => [k, String(k)]), S.p.k, v => { S.p.k = v; S.p.manual.clear(); render(); });
      pills($("cs-rule"), [["subtree", "Subtree rule (worst case for Static)"], ["uniform", "Uniform random"], ["manual", "Click sensors to mark"]], S.p.rule, v => { S.p.rule = v; S.p.manual.clear(); render(); });
      if (S.p.rule === "uniform") pills($("cs-P"), [101, 102, 103, 104].map(P => [P, `P${P}`]), S.p.P, v => { S.p.P = v; render(); });
      pills($("cs-pl"), [["links", "90 m link model"]], S.p.links ? "links" : null, () => { S.p.links = !S.p.links; render(); });
    } else {
      fixV();
      box.innerHTML = group("Network", "cs-n") + group("Topology seed", "cs-seed") + group("Risk placement", "cs-place") + group("Rate", "cs-rate") + group("k", "cs-vk") + group("Protocol", "cs-proto") + group("Layers", "cs-vl");
      pills($("cs-n"), [...new Set(IDX.topologies.map(t => t.N))].map(n => [n, `N = ${n}`]), S.v.n, v => { S.v.n = v; S.sel = null; loadT(); });
      pills($("cs-seed"), IDX.topologies.filter(t => t.N === S.v.n).map(t => [t.seed, String(t.seed)]), S.v.seed, v => { S.v.seed = v; S.sel = null; loadT(); });
      const o = vOpts();
      const places = [...new Set(o.map(x => x.place))].sort((a, b) => (a !== "subtree") - (b !== "subtree") || String(a).localeCompare(String(b)));
      pills($("cs-place"), places.map(p => [p, p === "subtree" ? "Subtree" : `Uniform P${p}`]), S.v.place, v => { S.v.place = v; render(); });
      const o1 = o.filter(x => x.place === S.v.place);
      pills($("cs-rate"), [...new Set(o1.map(x => x.rate))].sort((a, b) => a - b).map(r => [r, `${r} kbps`]), S.v.rate, v => { S.v.rate = v; render(); });
      const o2 = o1.filter(x => x.rate === S.v.rate);
      pills($("cs-vk"), [...new Set(o2.map(x => x.k))].sort().map(k => [k, String(k)]), S.v.k, v => { S.v.k = v; render(); });
      const o3 = o2.filter(x => x.k === S.v.k);
      pills($("cs-proto"), Object.keys(PROTO).filter(p => o3.some(x => x.protocol === p)).map(p => [p, PROTO[p][0]]), S.v.proto, v => { S.v.proto = v; render(); });
      const L = new Set(["links", "routes", "traffic"].filter(k => S.v[k]));
      pills($("cs-vl"), [["links", "90 m link model"], ["routes", "Installed routes"], ["traffic", "Observed traffic"]], L, v => { S.v[v] = !S.v[v]; render(); }, true);
    }
    renderLegend();
  }
  const vMeta = () => IDX.topologies.find(t => t.N === S.v.n && t.seed === S.v.seed);
  const vOpts = () => vMeta().options.map(o => ({ place: o[0], rate: o[1], k: o[2], protocol: o[3] }));
  function fixV() {
    const seeds = IDX.topologies.filter(t => t.N === S.v.n).map(t => t.seed);
    if (!seeds.includes(S.v.seed)) S.v.seed = seeds[0];
    let o = vOpts();
    const pick = (key, sk, pref) => { const v = [...new Set(o.map(x => x[key]))]; if (!v.includes(S.v[sk])) S.v[sk] = v.includes(pref) ? pref : v[0]; o = o.filter(x => x[key] === S.v[sk]); };
    pick("place", "place", "subtree"); pick("rate", "rate", 8); pick("k", "k", 3); pick("protocol", "proto", "riskaware");
  }

  function renderLegend() {
    const dot = (c, ring) => `<svg width="14" height="14" aria-hidden="true"><circle cx="7" cy="7" r="5" fill="${c}" stroke="${ring || "#fff"}" stroke-width="1.5"/></svg>`;
    const line = (c, dash, w) => `<svg width="24" height="10" aria-hidden="true"><line x1="1" y1="5" x2="23" y2="5" stroke="${c}" stroke-width="${w || 3}" ${dash ? `stroke-dasharray="${dash}"` : ""}/></svg>`;
    const sq = `<svg width="14" height="14" aria-hidden="true"><rect x="1" y="1" width="12" height="12" fill="#17202e"/></svg>`;
    let h = `<span class="item">${sq}Gateway</span><span class="item">${dot("#a3261b", "#a3261b")}High-risk relay</span>`;
    if (S.mode === "proposed") {
      h += Object.values(APPS).map(a => `<span class="item">${dot(a.color)}${a.label}</span>`).join("");
      h += `<span class="item">${line("#8592a3", "3 3", 1.2)}90 m link model <em>(conceptual)</em></span><span class="item">${line(PROTO.static[1])}Static tree <em>(computed illustration)</em></span><span class="item">${line(PROTO.riskaware[1])}Risk-Aware tree <em>(computed illustration)</em></span>`;
    } else {
      h += `<span class="item">${dot("#ffffff", "#3d4a5c")}Simulated sensor <em>(measured ns-3 position)</em></span><span class="item">${line("#123b84", "6 4", 2)}ns-3 field, 250 m × 250 m</span>` +
        `<span class="item">${line("#8592a3", "", 1)}90 m link model <em>(reconstructed)</em></span><span class="item">${line(PROTO[S.v.proto][1])}Installed route <em>(measured)</em></span><span class="item">${line(PROTO[S.v.proto][1] + "88", "", 5)}Observed traffic <em>(measured)</em></span>`;
    }
    $("cs-legend").innerHTML = h;
  }

  // ---------------------------------------------------------------- map
  function initMap() {
    map = L.map("cs-map", { scrollWheelZoom: false, zoomSnap: 0.25 });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors' }).addTo(map);
    base = L.layerGroup().addTo(map);
    over = L.layerGroup().addTo(map);
    L.polygon(C.campus.ring, { color: "#123b84", weight: 2, dashArray: "6 4", fill: false, interactive: false }).addTo(base);
    C.water.forEach(w => L.polygon(w.ring, { color: "#0e6f9c", weight: 1, fillColor: "#7cc3e6", fillOpacity: 0.45 }).bindTooltip(esc(w.name || "Water (OSM)")).addTo(base));
    C.roads.forEach(r => L.polyline(r.line, { color: r.kind === "footway" ? "#b8a98f" : "#9aa5b1", weight: r.kind === "footway" ? 1.5 : 3, opacity: 0.8, dashArray: r.kind === "footway" ? "3 3" : null, interactive: false }).addTo(base));
    C.buildings.forEach(b => L.polygon(b.ring, { color: "#6b7686", weight: 1, fillColor: "#c9ced6", fillOpacity: 0.55 })
      .bindTooltip(esc(b.name || b.name_th || "Building (unnamed in OSM)") + (b.name && b.name_th && b.name_th !== b.name ? ` · ${esc(b.name_th)}` : "")).addTo(base));
    map.fitBounds(L.polygon(C.campus.ring).getBounds(), { padding: [10, 10] });
    if (typeof ResizeObserver !== "undefined") new ResizeObserver(() => map.invalidateSize()).observe($("cs-map"));
  }
  function marker(ll, opt, tip, onClick) {
    const m = L.circleMarker(ll, Object.assign({ radius: 6, weight: 1.5, color: "#ffffff", fillOpacity: 1 }, opt));
    if (tip) m.bindTooltip(tip, { direction: "top" });
    if (onClick) m.on("click", onClick);
    return m.addTo(over);
  }
  function gatewayMarker(ll, tip) {
    L.marker(ll, { icon: L.divIcon({ className: "cs-gw", html: "<span>GW</span>", iconSize: [26, 26], iconAnchor: [13, 13] }), keyboard: true, title: "Gateway" })
      .bindTooltip(tip, { direction: "top" }).addTo(over);
  }

  // ---------------------------------------------------------------- proposed mode
  function proposedModel() {
    const g = gwSite();
    const sensors = C.proposed.sensors.filter(s => S.p.apps.has(s.app) && !s.src.includes(`OSM way ${g.id}`));
    const P = sensors.map(s => s.xy).concat([g.xy]);
    const G = graph(P), high = pickRisky(G, sensors.length), ra = riskAware(G, high);
    return { g, sensors, P, G, high, ra };
  }
  function renderProposed() {
    over.clearLayers();
    const M = proposedModel(), { G, sensors, high, ra, g } = M, LL = M.P.map(toLL), hs = new Set(high);
    if (S.p.links) G.adj.forEach((a, i) => a.forEach(j => { if (i < j) L.polyline([LL[i], LL[j]], { color: "#8592a3", weight: 1, dashArray: "3 3", opacity: 0.7, interactive: false }).addTo(over); }));
    const trees = S.p.view === "both" ? [["static", G.par], ["riskaware", ra.par]] : [[S.p.view, S.p.view === "static" ? G.par : ra.par]];
    trees.forEach(([p, par], ti) => {
      for (let i = 0; i < sensors.length; i++) if (par[i] >= 0) {
        const diff = S.p.view === "both" && G.par[i] !== ra.par[i];
        if (S.p.view === "both" && ti === 0 && !diff) continue;   // shared edges drawn once (Risk-Aware colour)
        L.polyline([LL[i], LL[par[i]]], { color: PROTO[p][1], weight: diff ? 4 : 2.5, opacity: diff ? 0.95 : 0.8, dashArray: diff && p === "static" ? "6 5" : null, interactive: false }).addTo(over);
      }
    });
    if (S.sel != null && S.sel < sensors.length) trees.forEach(([, par]) => L.polyline(walk(par, S.sel, G.gw).map(i => LL[i]), { color: "#1d5fd1", weight: 6, opacity: 0.85, interactive: false }).addTo(over));
    sensors.forEach((s, i) => {
      const a = APPS[s.app], h = hs.has(i);
      marker(LL[i], { fillColor: h ? "#a3261b" : a.color, color: i === S.sel ? "#1d5fd1" : h ? "#a3261b" : "#fff", radius: i === S.sel ? 8 : h ? 7.5 : 5.5, weight: i === S.sel ? 3 : 1.5 },
        `<strong>${a.label}</strong> · sensor ${i}${h ? " · <b style='color:#a3261b'>high-risk</b>" : ""}<br>${esc(s.src)}`,
        () => { if (S.p.rule === "manual" && S.p.k > 0) { S.p.manual.has(i) ? S.p.manual.delete(i) : S.p.manual.size < S.p.k && S.p.manual.add(i); } S.sel = i; renderProposed(); });
    });
    gatewayMarker(LL[G.gw], `<strong>Proposed gateway</strong><br>${esc(g.name)}`);
    const unreach = G.hop.slice(0, sensors.length).filter(h => h < 0).length, rer = sensors.filter((_, i) => G.par[i] !== ra.par[i]).length;
    const deg = G.adj.reduce((a, x) => a + x.length, 0) / G.n;
    const cnt = Object.keys(APPS).filter(k => S.p.apps.has(k)).map(k => `${sensors.filter(s => s.app === k).length} ${APPS[k].label.toLowerCase()}`).join(", ");
    $("cs-summary").innerHTML = `<div class="panel-head"><h3>Proposed deployment (conceptual)</h3><span class="tag planned">illustration, not simulated</span></div>` +
      `<p class="panel-sub" style="margin:0 0 6px"><strong>${sensors.length} sensors</strong> (${cnt}) and one gateway at <strong>${esc(g.name)}</strong>.</p>` +
      `<p class="panel-sub" style="margin:0 0 6px">Under the 90 m link model: up to <strong>${Math.max(...G.hop)} hops</strong> to the gateway, ${deg.toFixed(1)} links per node on average, ${unreach} sensor(s) with no route.` +
      (high.length ? ` High-risk relays: <strong>${high.join(", ")}</strong>; Risk-Aware re-routes <strong>${rer}</strong> of ${sensors.length} sensors around them.` : " No high-risk relay selected.") +
      (S.p.rule === "manual" && S.p.k > 0 ? ` <em>Click up to ${S.p.k} sensors to mark them high-risk (${S.p.manual.size} marked).</em>` : "") + `</p>` +
      `<p class="panel-sub" style="margin:0">Trees are computed in your browser with the simulator's Static (BFS) and Risk-Aware (Dijkstra, β = 10, r = 0.5) rules on these conceptual positions. No packet was simulated for this layout, so it has no PDR, delay or exposure. OLSR and AODV build routes from radio control traffic and cannot be computed without simulation.</p>`;
    renderInfoProposed(M);
    $("cs-mapnote").innerHTML = `Sensor sites follow a fixed rule from OpenStreetMap features (${Object.values(APPS).map(a => a.rule).join("; ")}). They are not surveyed or installed locations.`;
  }
  function costTerms(path, isHigh, gw) {
    const t = path.slice(1).map(v => (v !== gw && isHigh(v)) ? 1 + BETA * -Math.log1p(-R_HIGH) : 1);
    return `${t.map(x => x > 1 ? `<strong style="color:#a3261b">${x.toFixed(2)}</strong>` : "1").join(" + ")} = <strong>${t.reduce((a, b) => a + b, 0).toFixed(2)}</strong>`;
  }
  function renderInfoProposed(M) {
    const i = S.sel, box = $("cs-info");
    if (i == null || i >= M.sensors.length) { box.innerHTML = '<p class="panel-sub" style="margin:0">Click a sensor on the map to see what it is derived from, its route to the gateway and the route cost.</p>'; return; }
    const s = M.sensors[i], hs = new Set(M.high), name = v => v === M.G.gw ? "GW" : String(v);
    if (M.G.hop[i] < 0) { box.innerHTML = `<h3>Sensor ${i}</h3><p class="panel-sub">${esc(s.src)}. No chain of 90 m links reaches the gateway.</p>`; return; }
    const sp = walk(M.G.par, i, M.G.gw), rp = walk(M.ra.par, i, M.G.gw);
    box.innerHTML = `<div class="panel-head"><h3>Sensor ${i} · ${APPS[s.app].label}</h3><span class="tag planned">conceptual</span></div><p class="panel-sub" style="margin:0 0 8px">Derived from: ${esc(s.src)}.</p>` +
      `<div class="topo-route"><div class="k" style="color:${PROTO.static[1]}">Static route (fewest hops)</div><div class="topo-path">${sp.map(name).join(" → ")}</div><div class="panel-sub" style="margin:4px 0 0">${sp.length - 1} hops · Risk-Aware cost ${costTerms(sp, v => hs.has(v), M.G.gw)}</div></div>` +
      `<div class="topo-route" style="margin-top:8px"><div class="k" style="color:${PROTO.riskaware[1]}">Risk-Aware route</div><div class="topo-path">${rp.map(name).join(" → ")}</div><div class="panel-sub" style="margin:4px 0 0">${rp.length - 1} hops · cost ${costTerms(rp, v => hs.has(v), M.G.gw)}</div></div>`;
  }

  // ---------------------------------------------------------------- validated mode
  async function loadT() {
    fixV();
    const meta = vMeta();
    try { T = tcache[meta.file] || (tcache[meta.file] = await fetch("data/topology/" + meta.file).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })); }
    catch (e) { console.warn("topology file unavailable:", e); $("cs-summary").textContent = "Topology data file unavailable."; return; }
    render();
  }
  function simToMap(p) { const g = gwSite().xy; return toLL([g[0] + p[0] - FIELD / 2, g[1] + p[1] - FIELD / 2]); }
  function renderValidated() {
    over.clearLayers();
    const run = T.runs.find(r => r.protocol === S.v.proto && r.place === String(S.v.place) && r.rate === S.v.rate && r.k === S.v.k);
    const LL = T.pos.map(simToMap), gw = T.N, hs = new Set(run.high), col = PROTO[S.v.proto][1];
    L.polygon([[0, 0], [FIELD, 0], [FIELD, FIELD], [0, FIELD]].map(simToMap), { color: "#123b84", weight: 2, dashArray: "6 4", fill: false, interactive: false }).addTo(over);
    if (S.v.links) T.links.forEach(([i, j]) => L.polyline([LL[i], LL[j]], { color: "#8592a3", weight: 0.7, opacity: 0.6, interactive: false }).addTo(over));
    if (S.v.traffic) {
      const mx = Math.max(...run.uses.map(u => u[2]));
      run.uses.forEach(([a, b, n]) => L.polyline([LL[a], LL[b]], { color: col, weight: 1 + 7 * Math.sqrt(n / mx), opacity: 0.4 }).bindTooltip(`${a} → ${b}: ${n.toLocaleString()} packets observed`).addTo(over));
    }
    const tree = run.protocol === "static" ? T.bfs : run.protocol === "riskaware" ? run.ra : null;
    if (S.v.routes && tree) for (let i = 0; i < T.N; i++) if (tree[i] >= 0) L.polyline([LL[i], LL[tree[i]]], { color: col, weight: 2.5, opacity: 0.85, interactive: false }).addTo(over);
    if (S.sel != null && S.sel < T.N) {
      const path = tree ? walk(tree, S.sel, gw) : ((run.paths[S.sel][0] || [0, 0, []])[2]);
      if (path.length > 1) L.polyline(path.map(i => LL[i]), { color: "#1d5fd1", weight: 6, opacity: 0.85, interactive: false }).addTo(over);
    }
    for (let i = 0; i < T.N; i++) {
      const h = hs.has(i);
      marker(LL[i], { fillColor: h ? "#a3261b" : "#ffffff", color: i === S.sel ? "#1d5fd1" : h ? "#a3261b" : "#3d4a5c", radius: i === S.sel ? 7 : h ? 6.5 : 4.5, weight: i === S.sel ? 3 : 1.4 },
        `ns-3 sensor ${i}${h ? " · <b style='color:#a3261b'>high-risk</b>" : ""}<br>position (${T.pos[i][0].toFixed(1)}, ${T.pos[i][1].toFixed(1)}) m in the ns-3 field`, () => { S.sel = i; renderValidated(); });
    }
    gatewayMarker(LL[gw], `<strong>ns-3 gateway</strong> (node ${gw}, field centre)<br>placed at ${esc(gwSite().name)}`);
    // where do simulated positions fall on campus?
    const ring = C.campus.ring.map(toXY), bld = C.buildings.map(b => b.ring.map(toXY)), wat = C.water.map(w => w.ring.map(toXY));
    let inB = 0, inW = 0, out = 0;
    T.pos.slice(0, T.N).forEach(p => { const q = toXY(simToMap(p)); if (!inside(q, ring)) out++; else if (bld.some(b => inside(q, b))) inB++; else if (wat.some(w => inside(q, w))) inW++; });
    const m = run.metrics;
    $("cs-summary").innerHTML = `<div class="panel-head"><h3>Validated ns-3 run</h3><span class="tag measured">measured positions and routes</span></div>` +
      `<p class="panel-sub" style="margin:0 0 6px"><strong>${PROTO[S.v.proto][0]}</strong>, N = ${T.N}, topology seed ${T.seed}, ${S.v.place === "subtree" ? "subtree placement" : "uniform placement P" + S.v.place}, ${S.v.rate} kbps per sensor, k = ${S.v.k}. Run <code>${esc(run.id)}</code>.</p>` +
      `<p class="panel-sub" style="margin:0 0 6px">In the simulation: nominal PDR <strong>${m.pdr_nominal_pct.toFixed(2)} %</strong>, risk exposure <strong>${m.exposure_rate_pct.toFixed(2)} %</strong>, p95 delay ${m.delay_p95_ms.toFixed(0)} ms, gateway airtime ${m.gw_airtime.toFixed(3)}. These are ns-3 results in an open field, not campus performance.</p>` +
      `<p class="panel-sub" style="margin:0">On the map, ${inB} of ${T.N} simulated sensors fall inside an OSM building footprint, ${inW} in water and ${out} outside the campus boundary. The simulator places them uniformly at random and ignores buildings.${!tree && !S.v.traffic ? ' <strong>Turn on "Observed traffic" to see this protocol\'s packet paths.</strong>' : ""}</p>`;
    const i = S.sel, box = $("cs-info");
    if (i == null || i >= T.N) box.innerHTML = '<p class="panel-sub" style="margin:0">Click a simulated sensor to see its measured route and packet counts. The Network topology explorer shows Static and Risk-Aware side by side with full cost breakdowns.</p>';
    else {
      const s = run.src[i], top = run.paths[i].map(([pk, dl, p]) => `<li><span class="topo-path">${p.map(v => v === gw ? "GW" : v).join(" → ")}</span>${p.length === 1 ? " (lost before the first hop)" : ""}: ${pk.toLocaleString()} packets, ${dl.toLocaleString()} delivered</li>`).join("");
      box.innerHTML = `<div class="panel-head"><h3>ns-3 sensor ${i}${hs.has(i) ? ' <span class="tag risk">high-risk</span>' : ""}</h3><span class="tag measured">measured</span></div>` +
        `<p class="panel-sub" style="margin:0 0 6px">ns-3 position (${T.pos[i][0].toFixed(1)}, ${T.pos[i][1].toFixed(1)}) m · ${T.hop[i]} hop(s) by BFS · sent ${s[0].toLocaleString()}, delivered ${s[1].toLocaleString()}, risk-dropped ${s[2].toLocaleString()}.</p>` +
        (tree ? `<div class="topo-route"><div class="k" style="color:${col}">Installed ${PROTO[S.v.proto][0]} route</div><div class="topo-path">${walk(tree, i, gw).map(v => v === gw ? "GW" : v).join(" → ")}</div></div>` : "") +
        `<p class="panel-sub" style="margin:8px 0 2px">Observed paths (${run.n_paths[i]} distinct${run.n_paths[i] > 3 ? ", 3 most used" : ""}):</p><ul class="topo-paths">${top}</ul>`;
    }
    $("cs-mapnote").innerHTML = `The 250 m × 250 m ns-3 field (dashed square) is drawn at true scale with its gateway at ${esc(gwSite().name)}. Sensor positions, routes and traffic are from the validated run; their placement on campus is a visual overlay only.`;
  }

  // ---------------------------------------------------------------- static panels
  function renderTransform() {
    const g = gwSite(), f = C.frame;
    $("cs-transform").innerHTML = [
      `<strong>Scale 1 : 1.</strong> One metre in ns-3 is drawn as one metre on the map. Nothing is stretched, so the 90 m link model keeps its physical length.`,
      `<strong>Anchor.</strong> The ns-3 gateway, at the field centre (125, 125) m, is placed on the selected gateway site: <strong>${esc(g.name)}</strong>, at ${g.ll[0].toFixed(6)}, ${g.ll[1].toFixed(6)} (centroid of the OSM building footprint). The default is the administration building, about 25 m from the campus centre.`,
      `<strong>Orientation.</strong> ns-3 x points east and y points north. No rotation.`,
      `<strong>Projection.</strong> Local equirectangular: lat = ${f.lat0.toFixed(6)} + y / ${f.m_per_deg_lat.toFixed(0)}, lon = ${f.lon0.toFixed(6)} + x / ${f.m_per_deg_lon.toFixed(1)} (metres from the campus centre). The error is below 0.1 % over 1 km at this latitude.`,
      `<strong>The same frame</strong> places the proposed sensor sites, which are computed in metres from the OSM features.`
    ].map(x => `<li>${x}</li>`).join("");
  }
  function renderApps() {
    $("cs-apps").innerHTML = Object.entries(APPS).map(([k, a]) => {
      const n = C.proposed.sensors.filter(s => s.app === k).length;
      return `<div class="panel cs-app"><div class="cs-app-h"><span class="cs-app-dot" style="background:${a.color}"></span><h3>${a.label}</h3></div>` +
        `<p class="panel-sub" style="margin:0 0 6px">${a.examples}.</p><p class="panel-sub" style="margin:0"><strong>${n}</strong> proposed sites: ${a.rule}. Relevant study metrics: ${k === "flood" ? "PDR and delay (alerts must arrive), robustness to failing relays" : k === "traffic" ? "delay and gateway congestion at higher rates" : k === "lighting" ? "PDR over many hops along roads" : "PDR and risk exposure of routine readings"}.</p></div>`;
    }).join("");
  }
  function renderResults() {
    if (!RP) { $("cs-results").innerHTML = "<tbody><tr><td>Results file unavailable.</td></tr></tbody>"; return; }
    const bp = (rate, p) => RP.by_protocol.find(x => x.rate === rate && x.protocol === p);
    const f = (v, d) => `${v[0].toFixed(d)} <span style="color:var(--text-faint);font-size:.72rem">[${v[2].toFixed(d)}, ${v[3].toFixed(d)}]</span>`;
    const head = "<thead><tr><th>Rate per sensor</th><th>Protocol</th><th>Nominal PDR (%)</th><th>Risk exposure (%)</th><th>p95 delay (ms)</th><th>Gateway airtime</th></tr></thead>";
    const body = [8, 32].flatMap(rate => ["static", "riskaware", "olsr"].map(p => {
      const r = bp(rate, p);
      return `<tr><td>${rate} kbps</td><td>${PROTO[p][0]}</td><td class="num">${f(r.pdr_nominal_pct, 2)}</td><td class="num">${f(r.exposure_rate_pct, 2)}</td><td class="num">${f(r.delay_p95_ms, 0)}</td><td class="num">${f(r.gw_airtime, 3)}</td></tr>`;
    })).join("");
    $("cs-results").innerHTML = head + "<tbody>" + body + "</tbody>";
    const pr = (rate, a, b, m) => RP.paired.find(x => x.rate === rate && x.A === a && x.B === b && x.metric === m);
    const air32 = bp(32, "olsr").gw_airtime[0], air8 = bp(8, "static").gw_airtime[0];
    $("cs-results-notes").innerHTML = [
      `<strong>Gateway congestion is the first limit to plan for.</strong> In simulation, gateway airtime rises from ${air8.toFixed(2)} at 8 kbps to ${air32.toFixed(2)} at 32 kbps per sensor, and PDR falls to ${bp(32, "olsr").pdr_nominal_pct[0].toFixed(0)}–${bp(32, "riskaware").pdr_nominal_pct[0].toFixed(0)} %. For a campus, this points to keeping per-sensor traffic low or adding gateways. That is a design question to test, not a measured campus result.`,
      `<strong>Risk-aware routing helps when risky relays sit on the routes.</strong> Against OLSR, Risk-Aware lowered exposure in 12/12 draws (${pr(8, "riskaware", "olsr", "exposure_rate_pct").diff[0].toFixed(2)} pp at 8 kbps; statistically supported). Against Static, it changed the outcome only in the 5 draws with a risky node on Static's tree, where its PDR gains are descriptive, not significant.`,
      `<strong>Not transferable as numbers.</strong> The simulated field is open, 250 m wide and at most 2–3 hops deep. A whole-campus mesh would be deeper and shaped by buildings, so these values are not predictions for PSU Phuket.`
    ].map(x => `<li>${x}</li>`).join("");
  }
  function renderArch() {
    const box = (t, s, cls) => `<div class="cs-box ${cls || ""}"><div class="cs-box-t">${t}</div><div class="cs-box-s">${s}</div></div>`;
    const arr = '<div class="cs-arr" aria-hidden="true">→</div>';
    $("cs-arch").innerHTML =
      `<div class="cs-row"><div class="cs-row-h">Proposed campus system (conceptual)</div><div class="cs-flow">` +
      box("Campus sensors", "environmental · lighting · traffic · flood", "concept") + arr +
      box("Multi-hop mesh relays", "sensors forward each other's packets over Wi-Fi", "concept") + arr +
      box("Routing decision", "Static: fewest hops · Risk-Aware: avoid risky relays · OLSR / AODV: discovered", "concept") + arr +
      box("Gateway", "collects all sensor data", "concept") + arr +
      box("Campus server", "storage and alerts (outside this study)", "concept muted") + `</div></div>` +
      `<div class="cs-link" aria-hidden="true">studied in ns-3 as ↓</div>` +
      `<div class="cs-row"><div class="cs-row-h">How this research studies it (validated)</div><div class="cs-flow">` +
      box("Scenario parameters", "N, topology seed, rate, k, risk placement", "study") + arr +
      box("ns-3 802.11ax simulation", "topology, routing protocols, risk drops at high-risk relays", "study") + arr +
      box("Per-packet traces", "path, fate and delay of every packet; validation gates", "study") + arr +
      box("Metrics", "PDR, delay, gateway congestion, risk exposure", "study") + arr +
      box("Dashboard analysis", "paired statistics, figures, this case study", "study") + `</div></div>`;
  }

  function render() {
    renderControls();
    if (S.mode === "proposed") renderProposed(); else if (T) renderValidated(); else loadT();
    renderTransform();
  }

  async function init() {
    if (!$("view-campus")) return;
    if (typeof L === "undefined") { $("cs-map").innerHTML = '<p class="panel-sub" style="padding:16px">The map library could not be loaded.</p>'; }
    try { C = await fetch("data/campus/campus.json").then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }); }
    catch (e) { console.warn("campus.json unavailable:", e); $("cs-summary").textContent = "Campus data file unavailable."; return; }
    [RP, IDX] = await Promise.all([
      fetch("data/wifi6-randplace.json").then(r => r.ok ? r.json() : null).catch(() => null),
      fetch("data/topology/index.json").then(r => r.ok ? r.json() : null).catch(() => null)]);
    S.gw = C.proposed.default_gateway;
    const sel = $("cs-gw");
    sel.innerHTML = C.proposed.gateways.map(g => `<option value="${g.id}">${esc(g.name)}${g.id === C.proposed.default_gateway ? " (administration building, default)" : ""}</option>`).join("");
    sel.value = String(S.gw);
    sel.addEventListener("change", () => { S.gw = +sel.value; S.sel = null; S.p.manual.clear(); render(); });
    $("cs-sources").innerHTML = `Base map tiles and campus geometry: ${esc(C.attribution)}, <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">openstreetmap.org/copyright</a>. ` +
      `The campus is OSM way <a href="https://www.openstreetmap.org/way/${C.osm_snapshot.campus_way}" target="_blank" rel="noopener">${C.osm_snapshot.campus_way}</a> (${esc(C.campus.name)}, ${esc(C.campus.name_th)}; ${(C.campus.area_m2 / 1e6).toFixed(2)} km²), located with Nominatim. ` +
      `Buildings, roads and water come from an Overpass snapshot (OSM data as of ${esc(C.osm_snapshot.osm_timestamp)}, file <code>${esc(C.osm_snapshot.file)}</code>, sha256 <code>${C.osm_snapshot.sha256.slice(0, 12)}…</code>): ${C.buildings.length} buildings (${C.buildings.filter(b => b.name).length} named), ${C.roads.length} road and path segments, ${C.water.length} water bodies. OSM is crowd-sourced and was not surveyed for this project. ` +
      `Tiles are served by tile.openstreetmap.org under the OSM tile usage policy. Map library: Leaflet 1.9.4 (BSD-2-Clause). Built by <code>${esc(C.generated_by)}</code>.`;
    renderApps(); renderResults(); renderArch();
    if (typeof L !== "undefined") initMap();
    if (!IDX) $("cs-mode").title = "Validated topologies unavailable";
    render();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
