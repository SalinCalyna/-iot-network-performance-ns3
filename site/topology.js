// Network topology explorer and architecture workflow (Wi-Fi 6 risk study). Topology data: data/topology/*.json,
// built by experiments/wifi6-risk/build_site_topology.py (ns-3-dev) from the validated runs' own output files.
// Coordinates, installed routes and packet paths are measured; only the 90 m link model is reconstructed (and
// verified against the simulator's degree for every node). Nothing here is simulated or estimated.
(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const LABEL = { static: "Static", riskaware: "Risk-Aware", olsr: "OLSR", aodv: "AODV" };
  const COLOR = { static: "var(--static)", riskaware: "var(--riskaware)", olsr: "var(--olsr)", aodv: "var(--aodv)" };
  const TEXT = { static: "var(--static-text)", riskaware: "var(--riskaware-text)", olsr: "var(--olsr-text)", aodv: "var(--aodv-text)" };
  const ORDER = ["static", "riskaware", "olsr", "aodv"];
  let IDX = null, T = null;
  const cache = {};
  const S = { n: 30, seed: 20, place: "subtree", rate: 8, k: 3, view: "compare", layers: { links: true, routes: true, traffic: false }, sel: null };

  function pills(container, options, active, onChange) {
    container.innerHTML = "";
    options.forEach(([val, text]) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "pill" + (val === active ? " active" : "");
      b.textContent = text;
      b.setAttribute("aria-pressed", val === active ? "true" : "false");
      b.addEventListener("click", () => onChange(val));
      container.appendChild(b);
    });
  }
  function toggles(container) {
    container.innerHTML = "";
    [["links", "90 m link model"], ["routes", "Installed routes"], ["traffic", "Observed traffic"]].forEach(([key, text]) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "pill" + (S.layers[key] ? " active" : "");
      b.textContent = text;
      b.setAttribute("aria-pressed", S.layers[key] ? "true" : "false");
      b.addEventListener("click", () => { S.layers[key] = !S.layers[key]; renderControls(); renderPanels(); });
      container.appendChild(b);
    });
  }

  const topoMeta = () => IDX.topologies.find(t => t.N === S.n && t.seed === S.seed);
  const opts = () => topoMeta().options.map(o => ({ place: o[0], rate: o[1], k: o[2], protocol: o[3] }));
  function fix() {   // keep every choice valid for the selected topology
    const seeds = IDX.topologies.filter(t => t.N === S.n).map(t => t.seed);
    if (!seeds.includes(S.seed)) S.seed = seeds[0];
    let o = opts();
    const pick = (key, list) => { const v = [...new Set(list.map(x => x[key]))]; if (!v.includes(S[key])) S[key] = key === "k" && v.includes(3) ? 3 : key === "place" && v.includes("subtree") ? "subtree" : v[0]; return v; };
    pick("place", o); o = o.filter(x => x.place === S.place);
    pick("rate", o); o = o.filter(x => x.rate === S.rate);
    pick("k", o); o = o.filter(x => x.k === S.k);
    const protos = ORDER.filter(p => o.some(x => x.protocol === p));
    const canCompare = protos.includes("static") && protos.includes("riskaware");
    if (S.view === "compare" ? !canCompare : !protos.includes(S.view)) S.view = canCompare ? "compare" : protos[0];
    return { protos, canCompare };
  }

  function renderControls() {
    const { protos, canCompare } = fix();
    pills($("topo-n"), [...new Set(IDX.topologies.map(t => t.N))].map(n => [n, `N = ${n}`]), S.n, v => { S.n = v; S.sel = null; load(); });
    pills($("topo-seed"), IDX.topologies.filter(t => t.N === S.n).map(t => [t.seed, String(t.seed)]), S.seed, v => { S.seed = v; S.sel = null; load(); });
    const places = [...new Set(opts().map(x => x.place))].sort((a, b) => (a !== "subtree") - (b !== "subtree") || String(a).localeCompare(String(b)));
    pills($("topo-place"), places.map(p => [p, p === "subtree" ? "Subtree (Static's worst case)" : `Uniform P${p}`]), S.place, v => { S.place = v; update(); });
    const o1 = opts().filter(x => x.place === S.place);
    pills($("topo-rate"), [...new Set(o1.map(x => x.rate))].sort((a, b) => a - b).map(r => [r, `${r} kbps`]), S.rate, v => { S.rate = v; update(); });
    const o2 = o1.filter(x => x.rate === S.rate);
    pills($("topo-k"), [...new Set(o2.map(x => x.k))].sort().map(k => [k, String(k)]), S.k, v => { S.k = v; update(); });
    pills($("topo-view"), (canCompare ? [["compare", "Static vs Risk-Aware"]] : []).concat(protos.map(p => [p, LABEL[p]])), S.view, v => { S.view = v; update(); });
    toggles($("topo-layers"));
    renderLegend();
  }

  function renderLegend() {
    const sw = (style, text) => `<span class="item"><span class="topo-sw" style="${style}"></span>${text}</span>`;
    $("topo-legend").innerHTML =
      `<span class="item"><svg width="14" height="14" aria-hidden="true"><rect x="1" y="1" width="12" height="12" fill="${resolveColor("var(--text)")}"/></svg>Gateway</span>` +
      `<span class="item"><svg width="14" height="14" aria-hidden="true"><circle cx="7" cy="7" r="5" fill="${resolveColor("var(--panel)")}" stroke="${resolveColor("var(--text-dim)")}" stroke-width="1.5"/></svg>Sensor</span>` +
      `<span class="item"><svg width="14" height="14" aria-hidden="true"><circle cx="7" cy="7" r="5" fill="${resolveColor("var(--bad)")}"/></svg>High-risk relay</span>` +
      sw(`border-top:1px solid ${resolveColor("var(--border)")}`, "90 m link model <em>(reconstructed)</em>") +
      sw(`border-top:3px solid ${resolveColor("var(--static)")}`, "Static tree <em>(measured)</em>") +
      sw(`border-top:3px solid ${resolveColor("var(--riskaware)")}`, "Risk-Aware tree <em>(measured)</em>") +
      sw(`border-top:4px solid ${toRgba("var(--text)", 0.35)}`, "Observed traffic, width ∝ packets <em>(measured)</em>") +
      sw(`border-top:4px solid ${resolveColor("var(--focus)")}`, "Selected sensor's route");
  }

  function runFor(protocol) {
    return T.runs.find(r => r.protocol === protocol && r.place === String(S.place) && r.rate === S.rate && r.k === S.k);
  }
  function walk(par, i) {
    const p = [i];
    while (p[p.length - 1] !== T.N && par[p[p.length - 1]] >= 0 && p.length <= T.N + 1) p.push(par[p[p.length - 1]]);
    return p;
  }
  const treeOf = run => run.protocol === "static" ? T.bfs : run.protocol === "riskaware" ? run.ra : null;

  function panel(container, run) {
    container.__redraw = () => panel(container, run);
    container.innerHTML = "";
    const W = Math.max(260, Math.min(container.clientWidth || 480, 640));
    container.__drawnW = container.clientWidth;
    const pad = 8, sc = (W - 2 * pad) / IDX.area_m, H = W;
    const X = p => pad + p[0] * sc, Y = p => pad + (IDX.area_m - p[1]) * sc;   // north up
    const P = T.pos, gw = T.N, high = new Set(run.high), tip = ensureTooltip(container);
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, class: "chart topo-svg", role: "img" });
    const ttl = el("title", {}); ttl.textContent = `${LABEL[run.protocol]} on N = ${T.N}, topology seed ${T.seed}, ${S.place === "subtree" ? "subtree placement" : "uniform placement " + S.place}, ${S.rate} kbps, k = ${S.k}`;
    svg.appendChild(ttl);
    svg.appendChild(el("rect", { x: pad, y: pad, width: W - 2 * pad, height: W - 2 * pad, fill: "none", stroke: resolveColor("var(--border-soft)") }));
    const ns = T.N > 50 ? 1 : 1.35, r0 = Math.max(2.6, Math.min(5.5, W / 110)) * ns;
    if (S.layers.links) {
      const g = el("g", { stroke: resolveColor("var(--border)"), "stroke-width": T.N > 50 ? 0.5 : 0.8, opacity: T.N > 50 ? 0.55 : 0.9 });
      T.links.forEach(([i, j]) => g.appendChild(el("line", { x1: X(P[i]), y1: Y(P[i]), x2: X(P[j]), y2: Y(P[j]) })));
      svg.appendChild(g);
    }
    if (S.layers.traffic) {
      const mx = Math.max(...run.uses.map(u => u[2]));
      const g = el("g", { stroke: toRgba(COLOR[run.protocol], 0.45), "stroke-linecap": "round" });
      run.uses.forEach(([a, b, n]) => {
        const l = el("line", { x1: X(P[a]), y1: Y(P[a]), x2: X(P[b]), y2: Y(P[b]), "stroke-width": (0.6 + 6 * Math.sqrt(n / mx)) * (W / 480) });
        const t = el("title", {}); t.textContent = `${a} → ${b}: ${n.toLocaleString()} packets observed (${Math.hypot(P[a][0] - P[b][0], P[a][1] - P[b][1]).toFixed(1)} m)`;
        l.appendChild(t); g.appendChild(l);
      });
      svg.appendChild(g);
    }
    const tree = treeOf(run);
    if (S.layers.routes && tree) {
      const other = run.protocol === "riskaware" ? T.bfs : run.ra;
      const g = el("g", { stroke: resolveColor(COLOR[run.protocol]), "stroke-linecap": "round" });
      for (let i = 0; i < T.N; i++) {
        const p = tree[i];
        if (p < 0) continue;
        const differs = S.view === "compare" && other[i] !== p;
        g.appendChild(el("line", { x1: X(P[i]), y1: Y(P[i]), x2: X(P[p]), y2: Y(P[p]), "stroke-width": (differs ? 3.2 : 1.6) * (W / 480) + (differs ? 0.6 : 0.3), opacity: differs ? 1 : 0.75 }));
      }
      svg.appendChild(g);
    }
    if (S.sel != null) {   // selected sensor: its installed route, or its most-used observed path
      const route = tree ? walk(tree, S.sel) : (run.paths[S.sel][0] || [0, 0, []])[2];
      if (route.length > 1) {
        const d = route.map((v, i) => `${i ? "L" : "M"}${X(P[v]).toFixed(1)} ${Y(P[v]).toFixed(1)}`).join("");
        svg.appendChild(el("path", { d, fill: "none", stroke: resolveColor("var(--panel)"), "stroke-width": 8, "stroke-linejoin": "round", "stroke-linecap": "round" }));
        svg.appendChild(el("path", { d, fill: "none", stroke: resolveColor("var(--focus)"), "stroke-width": 4.5, "stroke-linejoin": "round", "stroke-linecap": "round" }));
      }
    }
    const g = el("g", {});
    for (let i = 0; i <= T.N; i++) {
      const x = X(P[i]), y = Y(P[i]), isHigh = high.has(i), selected = i === S.sel;
      let m;
      if (i === gw) m = el("rect", { x: x - r0 * 1.5, y: y - r0 * 1.5, width: r0 * 3, height: r0 * 3, fill: resolveColor("var(--text)"), rx: 1.5 });
      else m = el("circle", { cx: x, cy: y, r: selected ? r0 * 1.5 : isHigh ? r0 * 1.3 : r0, fill: isHigh ? resolveColor("var(--bad)") : resolveColor("var(--panel)"),
        stroke: selected ? resolveColor("var(--focus)") : isHigh ? resolveColor("var(--bad)") : resolveColor("var(--text-dim)"), "stroke-width": selected ? 2.5 : 1.2 });
      m.style.cursor = "pointer";
      const show = ev => {
        const b = container.getBoundingClientRect();
        showTip(container, tip, ev.clientX - b.left, ev.clientY - b.top, tipHtml(run, i));
      };
      m.addEventListener("mousemove", show);
      m.addEventListener("mouseleave", () => hideTip(tip));
      if (i !== gw) m.addEventListener("click", () => { S.sel = S.sel === i ? null : i; renderPanels(); renderInfo(); });
      g.appendChild(m);
      if (T.N <= 30 || isHigh || selected || i === gw) {
        const t = el("text", { x: x + r0 + 1.5, y: y - r0 - 0.5, "font-size": Math.max(9, Math.min(11, W / 50)), fill: resolveColor(isHigh ? "var(--bad)" : "var(--text-dim)"), "pointer-events": "none" });
        t.textContent = i === gw ? "GW" : String(i);
        t.setAttribute("stroke", resolveColor("var(--panel)")); t.setAttribute("stroke-width", "3"); t.setAttribute("paint-order", "stroke");
        g.appendChild(t);
      }
    }
    svg.appendChild(g);
    container.appendChild(svg);
  }

  function tipHtml(run, i) {
    const row = (a, b) => `<div class="t-row"><span>${a}</span><span>${b}</span></div>`;
    if (i === T.N) return `<div class="t-title">Gateway (node ${i})</div>` + row("Position", `${T.pos[i][0].toFixed(1)}, ${T.pos[i][1].toFixed(1)} m`) + row("Links (90 m model)", T.degree[i]) + row("Packets received", run.src.reduce((a, s) => a + s[1], 0).toLocaleString()) + row("Airtime busy", (100 * run.busy[i]).toFixed(1) + " %");
    const s = run.src[i], high = run.high.includes(i);
    return `<div class="t-title">Sensor ${i}${high ? " · HIGH-RISK" : ""}</div>` + row("Position", `${T.pos[i][0].toFixed(1)}, ${T.pos[i][1].toFixed(1)} m`) +
      row("Hops (BFS) / links", `${T.hop[i] < 0 ? "unreachable" : T.hop[i]} / ${T.degree[i]}`) +
      row("Sent / delivered", `${s[0].toLocaleString()} / ${s[1].toLocaleString()}`) + row("Packets forwarded", run.fwd[i].toLocaleString()) +
      (high ? row("Transit risk-dropped", `${run.rdrop[i].toLocaleString()} of ${run.elig[i].toLocaleString()}`) : "") +
      `<div class="t-note">Click for its route and cost.</div>`;
  }

  function renderPanels() {
    const box = $("topo-panels");
    box.innerHTML = "";
    const list = S.view === "compare" ? ["static", "riskaware"] : [S.view];
    box.className = list.length > 1 ? "grid cols-2" : "grid";
    list.forEach(p => {
      const run = runFor(p);
      const div = document.createElement("div");
      div.className = "panel";
      const m = run.metrics;
      const changed = S.view === "compare" && p === "riskaware" ? T.bfs.slice(0, T.N).filter((v, i) => run.ra[i] !== v).length : null;
      div.innerHTML = `<div class="panel-head"><h3 style="color:${resolveColor(TEXT[p])}">${LABEL[p]}</h3><span class="tag ${treeOf(run) ? "measured" : "repro"}">${treeOf(run) ? "fixed tree installed at start" : "no fixed tree: observed traffic only"}</span></div>` +
        `<p class="panel-sub">Nominal PDR <strong>${m.pdr_nominal_pct.toFixed(2)} %</strong> · exposure <strong>${m.exposure_rate_pct.toFixed(2)} %</strong> · p95 delay ${m.delay_p95_ms.toFixed(0)} ms · gateway airtime ${m.gw_airtime.toFixed(3)}` +
        (changed != null ? ` · <strong>${changed}</strong> of ${T.N} sensors re-routed vs Static (thick lines)` : "") + `</p>`;
      const wrap = document.createElement("div");
      wrap.className = "chart-wrap topo-wrap";
      div.appendChild(wrap);
      const foot = document.createElement("p");
      foot.className = "panel-sub topo-run";
      foot.innerHTML = `Run <code>${esc(run.id)}</code> · ${esc(IDX.batches[run.batch].description)}${!treeOf(run) && !S.layers.traffic ? ' · <strong>turn on "Observed traffic" to see this protocol\'s paths</strong>' : ""}`;
      div.appendChild(foot);
      box.appendChild(div);
      panel(wrap, run);
      if (typeof _resizeObs !== "undefined" && _resizeObs && !wrap.__observed) { _resizeObs.observe(wrap); wrap.__observed = true; }
    });
  }

  function costRows(path, run) {   // entering each node after the source costs 1 + beta * tau
    const high = new Set(run.high), tau = Math.log(1 / (1 - run.risk_p));
    return path.slice(1).map(v => {
      const h = v !== T.N && high.has(v);
      return { v, h, w: 1 + (h ? run.beta * tau : 0) };
    });
  }
  function renderInfo() {
    const box = $("topo-info"), i = S.sel;
    if (i == null) { box.innerHTML = '<p class="panel-sub" style="margin:0">Click or tap a sensor to see its route to the gateway, the route cost under each metric and its packet counts.</p>'; return; }
    const st = runFor("static") || T.runs.find(r => r.place === String(S.place) && r.rate === S.rate && r.k === S.k);
    const fmtPath = p => p.map(v => v === T.N ? "GW" : String(v)).join(" → ");
    const block = (name, color, path, run, recorded) => {
      const rows = costRows(path, run), total = rows.reduce((a, r) => a + r.w, 0);
      const terms = rows.map(r => r.h ? `<strong style="color:${resolveColor("var(--bad)")}">${r.w.toFixed(2)}</strong>` : "1").join(" + ");
      return `<div class="topo-route"><div class="k" style="color:${resolveColor(color)}">${name}</div><div class="topo-path">${fmtPath(path)}</div>` +
        `<div class="panel-sub" style="margin:4px 0 0">${rows.length} hops · Risk-Aware cost = ${terms} = <strong>${total.toFixed(2)}</strong>${recorded != null ? ` <span style="color:var(--text-faint)">(recorded ${recorded.toFixed(2)})</span>` : ""} · ${rows.filter(r => r.h).length} high-risk transit(s)</div></div>`;
    };
    const any = T.runs.find(r => r.place === String(S.place) && r.rate === S.rate && r.k === S.k);
    const raRun = runFor("riskaware") || any;
    let html = `<div class="panel-head"><h3>Sensor ${i}${any.high.includes(i) ? ' <span class="tag risk">high-risk</span>' : ""}</h3><button type="button" class="pill" id="topo-clear">Clear selection</button></div>`;
    if (T.hop[i] < 0) html += `<p class="panel-sub">This sensor has no neighbour within 90 m chain to the gateway: Static and Risk-Aware install no route for it.</p>`;
    else {
      html += `<div class="grid cols-2" style="gap:12px">` + block("Static (BFS) route", "var(--static-text)", walk(T.bfs, i), raRun, st.cost_bfs ? st.cost_bfs[i] : null) +
        block("Risk-Aware route", "var(--riskaware-text)", walk(raRun.ra, i), raRun, raRun.cost_ra[i]) + `</div>`;
      html += `<p class="panel-sub" style="margin:10px 0 0">Both routes are priced with the Risk-Aware metric: 1 for each node entered, ${(1 + raRun.beta * Math.log(1 / (1 - raRun.risk_p))).toFixed(2)} for a high-risk relay (β = ${raRun.beta}, r = ${raRun.risk_p}). Risk-Aware installs the cheaper one; Static ignores risk and uses the fewest hops. "Recorded" is the value in <code>routes_planned.csv</code>.</p>`;
    }
    const obs = (S.view === "compare" ? ["static", "riskaware"] : [S.view]).map(p => {
      const run = runFor(p), s = run.src[i];
      const top = run.paths[i].map(([pk, dl, path]) => `<li><span class="topo-path">${fmtPath(path)}</span> — ${pk.toLocaleString()} packets, ${dl.toLocaleString()} delivered</li>`).join("");
      return `<div><div class="k" style="color:${resolveColor(TEXT[p])}">${LABEL[p]} · observed</div><p class="panel-sub" style="margin:2px 0">Sent ${s[0].toLocaleString()}, delivered ${s[1].toLocaleString()}, risk-dropped ${s[2].toLocaleString()} · ${run.n_paths[i]} distinct path(s)${run.n_paths[i] > 3 ? ", 3 most used:" : ":"}</p><ul class="topo-paths">${top}</ul></div>`;
    }).join("");
    html += `<h3 class="sub-h" style="margin-top:14px">Packet paths observed in the run</h3><div class="grid cols-2" style="gap:12px">${obs}</div>`;
    box.innerHTML = html;
    $("topo-clear").addEventListener("click", () => { S.sel = null; renderPanels(); renderInfo(); });
  }

  function update() { renderControls(); renderPanels(); renderInfo(); }
  async function load() {
    fix();
    const meta = topoMeta();
    $("topo-panels").innerHTML = '<p class="panel-sub">Loading topology…</p>';
    try {
      T = cache[meta.file] || (cache[meta.file] = await fetch("data/topology/" + meta.file).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }));
    } catch (e) {
      console.warn("topology file unavailable:", e);
      $("topo-panels").innerHTML = '<p class="panel-sub">Topology data file unavailable.</p>';
      return;
    }
    update();
  }

  // ------------------------------------------------------------------ architecture workflow
  const SRC = "scratch/iot-network-wifi6-risk-v2.cc";
  const STAGES = [
    { lane: "Inputs", t: "Run parameters", d: "Each run is one call of the simulator with explicit arguments, recorded in the run's <code>provenance.json</code> together with the exit code and the binary's sha256.",
      items: ["Fixed: <code>--standard=80211ax --trafficLevel=high --arpPrepopulate=1 --riskStudy=1 --perPacketTrace=1 --highRiskDropProb=0.5 --lowRiskDropProb=0 --riskBeta=10 --riskDropSeed=1</code>", "Varied: <code>--nSensors</code> (30, 100), <code>--seed</code> (topology), <code>--protocol</code>, <code>--numHighRisk</code> k = 0–3, <code>--offeredRateKbps</code> (8, 16, 32), <code>--riskSelect</code> = subtree or ids with <code>--highRiskIds</code>", "Simulated time 300 s, traffic from 30 s"],
      ref: "experiments/wifi6-risk/run_*.py · <batch>/batch.json" },
    { lane: "Inputs", t: "Topology generation", d: "Sensor positions are drawn once per topology seed. The gateway is an extra node at the field centre. Nodes do not move.",
      items: ["<code>std::mt19937(seed)</code>, x then y per sensor, uniform on [0, 250) m", "Gateway = node N at (125, 125) m", "Same generator as the V3 802.11b study"], ref: `${SRC} lines 830–846` },
    { lane: "Inputs", t: "Risk placement", d: "Chooses the k HIGH_RISK sensors before any routing is computed. It never depends on the protocol under test.",
      items: ["Subtree: relays with the most descendants in Static's BFS tree, then degree, then lower id. This is the worst case for Static", "Uniform: the k sensors with the smallest SplitMix64(SplitMix64(SplitMix64(P) ⊕ seed) ⊕ id), pre-registered for placement seeds P = 101–104", "Gateway never risky"], ref: `${SRC} lines 960–1015 · run_n100_randplace.py preregister()` },
    { lane: "ns-3 simulation", t: "Routing", d: "Static and Risk-Aware are computed offline on the 90 m link model and installed as fixed host routes. OLSR and AODV are the unmodified ns-3 modules and discover routes over the real radio channel.",
      items: ["Static: BFS shortest-hop tree from the gateway", "Risk-Aware: Dijkstra, entering node v costs 1 + β·(−ln(1 − r<sub>v</sub>))", "OLSR / AODV: ns-3 <code>olsr</code> / <code>aodv</code> modules, default parameters. AODV also runs the 5 s route sampler inherited from V3, which refreshes its route lifetimes (lines 634–677)"], ref: `${SRC} lines 884–957, 1018–1056` },
    { lane: "ns-3 simulation", t: "Radio and MAC", d: "One shared Wi-Fi channel. Every node uses the same settings, read back from every device into <code>wifi_readback.csv</code>.",
      items: ["IEEE 802.11ax HE single-user, ad hoc MAC, 2.4 GHz channel 1, 20 MHz, constant-rate HE MCS0, 800 ns guard interval", "20 dBm, log-distance propagation (exponent 3, 40 dB at 1 m)", "A-MPDU/A-MSDU off, ARP caches pre-filled, Block Ack starting-sequence fix (risk-v2)"], ref: `${SRC} lines 848–880` },
    { lane: "ns-3 simulation", t: "Traffic", d: "Every sensor sends constant-bit-rate UDP to the gateway; the gateway only receives.",
      items: ["OnOff application, always on, 512-byte payload", "8 kbps per sensor in the main study; 16 / 32 kbps in the saturated runs", "UDP port 9 to a PacketSink on the gateway, 30–300 s"], ref: `${SRC} lines 1124–1143` },
    { lane: "ns-3 simulation", t: "Risk drop", d: "A filter on each high-risk sensor decides deterministically whether to drop a data packet it forwards. It acts only on forwarded data, never on the sensor's own packets.",
      items: ["Drop iff U &lt; 0.5, U = SplitMix64 hash of (drop seed, node, source, sequence number)", "No ns-3 random stream is used, so the same packet gets the same decision under every protocol", "Logged per drop in <code>risk_drops.csv</code>"], ref: `${SRC} lines 459–520` },
    { lane: "Outputs & validation", t: "Traces and outputs", d: "Read-only trace sinks record every data packet and the routing state. The raw outputs stay outside Git, each listed with sha256.",
      items: ["<code>packet_paths.csv</code>: one row per packet (path, fate, delay)", "<code>routes_planned.csv</code>, <code>risk_nodes.csv</code>, <code>path_summary.csv</code>, <code>risk_summary.csv</code>", "<code>pernode/*.csv</code> (coordinates, airtime, forwarding), FlowMonitor and MAC counters"], ref: `${SRC} lines 1311–1815 · results/wifi6-risk/RAW_MANIFEST.csv` },
    { lane: "Outputs & validation", t: "Validation gates", d: "Each batch runs a 6-run subset first, checks it, then runs the rest and checks everything again. A failed check stops the batch.",
      items: ["P0 exit 0, empty stderr, validated binary · P1 packet accounting closes", "P2 high-risk set = reference model · P3 every risk drop reproduced from the hash · P4 delivered packets followed the installed path", "P5 identical traffic schedule across protocols · P6 802.11ax HE SU MCS0 only · R1–R3 placement checks"], ref: "experiments/wifi6-risk/analyze_*.py · <batch>/analysis/CHECKS.txt" },
    { lane: "Analysis & publication", t: "Metrics and statistics", d: "Metrics come from the per-packet traces, not from FlowMonitor. The statistics are paired because the same seed gives the same network, traffic and risk set under every protocol.",
      items: ["Nominal PDR = delivered ÷ scheduled packets; exposure = share of sent packets whose path crossed a high-risk relay", "N = 30: Student-t intervals, exact Wilcoxon, Holm adjustment", "Uniform placement: draw-paired intervals, exact sign-flip tests, topology-level intervals"], ref: "analyze_pilot_n30.py · analyze_paired_stats.py · analyze_randplace_stats.py" },
    { lane: "Analysis & publication", t: "Dashboard build", d: "Builder scripts read the analysis outputs, cross-check them, and write the JSON files this page loads, each listing its source files with sha256.",
      items: ["build_site_wifi6.py → data/wifi6-risk.json", "build_site_randplace.py → data/wifi6-randplace.json", "build_site_topology.py → data/topology/*.json"], ref: "experiments/wifi6-risk/build_site_*.py" },
    { lane: "Analysis & publication", t: "Publication", d: "A push to <code>main</code> deploys the static site to GitHub Pages. The page only reads finished results: it never runs or changes a simulation.",
      items: ["GitHub Actions workflow <code>deploy-pages.yml</code>", "Reproducibility guide: docs/wifi6-risk-reproducibility.md", "Raw-output manifests with sha256 per file"], ref: ".github/workflows/deploy-pages.yml" }
  ];
  let archSel = 0;
  function renderArch() {
    const flow = $("arch-flow");
    if (!flow) return;
    const lanes = [...new Set(STAGES.map(s => s.lane))];
    flow.innerHTML = lanes.map((lane, li) => `<div class="arch-lane" role="listitem"><div class="arch-lane-h">${li + 1} · ${esc(lane)}</div>` +
      STAGES.map((s, i) => s.lane !== lane ? "" : `<button type="button" class="arch-step${i === archSel ? " active" : ""}" data-i="${i}" aria-pressed="${i === archSel}"><span class="arch-num">${i + 1}</span>${esc(s.t)}</button>`).join("") +
      `</div>`).join('<div class="arch-arrow" aria-hidden="true">→</div>');
    flow.querySelectorAll(".arch-step").forEach(b => b.addEventListener("click", () => { archSel = +b.dataset.i; renderArch(); }));
    const s = STAGES[archSel];
    $("arch-detail").innerHTML = `<div class="arch-detail-h"><span class="arch-num">${archSel + 1}</span><h3>${esc(s.t)}</h3><span class="tag repro">${esc(s.lane)}</span></div><p>${s.d}</p><ul class="evidence-list">${s.items.map(x => `<li>${x}</li>`).join("")}</ul><p class="panel-sub" style="margin:6px 0 0">Implemented in: <code>${s.ref}</code></p>` +
      `<div class="arch-nav"><button type="button" class="pill" ${archSel === 0 ? "disabled" : ""} data-d="-1">← Previous</button><button type="button" class="pill" ${archSel === STAGES.length - 1 ? "disabled" : ""} data-d="1">Next →</button></div>`;
    $("arch-detail").querySelectorAll(".arch-nav .pill").forEach(b => b.addEventListener("click", () => { archSel = Math.max(0, Math.min(STAGES.length - 1, archSel + +b.dataset.d)); renderArch(); }));
  }

  async function init() {
    renderArch();
    if (!$("view-topology")) return;
    try {
      IDX = await fetch("data/topology/index.json").then(r => { if (!r.ok) throw new Error(r.status); return r.json(); });
    } catch (e) {
      console.warn("topology index unavailable:", e);
      $("topo-panels").innerHTML = '<p class="panel-sub">Topology data file unavailable.</p>';
      return;
    }
    $("topo-provenance").innerHTML = `Verification at build time: ${esc(IDX.verification)}. Generated by <code>${esc(IDX.generated_by)}</code>; batches: ` +
      Object.entries(IDX.batches).map(([b, v]) => `<code>${esc(b)}</code> (${esc(v.checks.split(": ")[1])})`).join(", ") + ". Data: <a href=\"data/topology/index.json\">data/topology/index.json</a>.";
    load();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
