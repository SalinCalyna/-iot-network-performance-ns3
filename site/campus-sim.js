// PSU Phuket campus-specific ns-3 simulation results. Data: data/campus-sim.json, built by
// experiments/campus-sim/build_site_campus_sim.py (ns-3-dev) from the validated campus matrix (positions, installed
// trees, packet paths and statistics are simulation outputs); base map: data/campus/campus.json (OpenStreetMap, ODbL).
// Results are simulated on the proposed campus layout with an uncalibrated open-space radio model: not campus measurements.
(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const num = (x, d) => (x < 0 ? "−" : "") + Math.abs(x).toFixed(d);
  const sgn = (x, d) => (x > 0 ? "+" : x < 0 ? "−" : "±") + Math.abs(x).toFixed(d);
  const pfmt = p => p < 0.001 ? p.toExponential(1) : p.toPrecision(2);
  const PROTO = { static: ["Static", "#4C72B0", "var(--static)"], riskaware: ["Risk-Aware", "#DD8452", "var(--riskaware)"], olsr: ["OLSR", "#55A868", "var(--olsr)"] };
  const APPC = { environmental: "#0b5d53", traffic: "#5b3aa8", lighting: "#a85f0f", flood: "#0e6f9c" };
  const CLS = { supported: ["measured", "Supported"], consistent: ["intervention", "Consistent"], descriptive: ["planned", "Descriptive"], identical: ["repro", "Identical"] };
  const PLACE = p => p === "none" ? "No risk (k = 0)" : p === "subtree" ? "Subtree (worst case for Static)" : `Uniform P${p.slice(1)}`;
  let D = null, C = null, map = null, over = null;
  const S = { place: "subtree", rate: 8, proto: "riskaware", links: false, routes: true, traffic: false, sel: null, tabRate: 8, pairRate: 8 };

  const bp = (rate, p) => D.stats.by_protocol.find(x => x.rate_kbps === rate && x.protocol === p);
  const pair = (rate, a, b, m) => D.stats.paired.find(x => x.rate_kbps === rate && x.A === a && x.B === b && x.metric === m);
  const ci = (r, m, d) => `${num(r[m + "_mean"], d)} <span style="color:var(--text-faint);font-size:.72rem">[${num(r[m + "_ci95_lo"], d)}, ${num(r[m + "_ci95_hi"], d)}]</span>`;
  const tag = c => `<span class="tag ${CLS[c][0]}">${CLS[c][1]}</span>`;
  const gwId = () => D.nodes.length - 1;

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

  function renderHead() {
    $("cms-badge-runs").textContent = `${D.design.runs} RUNS · ${D.checks.split("checks ")[1].toUpperCase()}`;
    const e = pair(8, "riskaware", "static", "exposure_rate_pct"), p8 = pair(8, "riskaware", "static", "pdr_nominal_pct"), p32 = pair(32, "riskaware", "static", "pdr_nominal_pct");
    const po = pair(8, "riskaware", "olsr", "pdr_nominal_pct"), eo = pair(8, "riskaware", "olsr", "exposure_rate_pct");
    const word = c => c === "supported" ? "statistically supported" : c === "identical" ? "identical" : c === "consistent" ? "consistent (exploratory)" : "descriptive, not statistically significant";
    const pl = (p, pr) => D.stats.per_placement.find(x => x.rate_kbps === 8 && x.place === p && x.protocol === pr);
    const uni = D.design.placements.filter(p => p.startsWith("u")).map(p => pl(p, "static").exposure_rate_pct_mean);
    $("cms-kf").innerHTML = `<span class="kf-label">Key Finding (simulation)</span><span>On the proposed campus layout with three high-risk relays, Risk-Aware changed risk exposure by <strong>${sgn(e.diff_mean, 2)} pp</strong> against Static [95 % CI ${sgn(e.diff_ci95_lo, 2)}, ${sgn(e.diff_ci95_hi, 2)}] (${word(e.class)}) and nominal PDR by <strong>${sgn(p8.diff_mean, 2)} pp</strong> at 8 kbps (${word(p8.class)}) and ${sgn(p32.diff_mean, 2)} pp at 32 kbps (${word(p32.class)}). Against OLSR at 8 kbps: PDR ${sgn(po.diff_mean, 2)} pp (${word(po.class)}), exposure ${sgn(eo.diff_mean, 2)} pp (${word(eo.class)}). Most of the difference from Static comes from the subtree placement (Static exposure ${num(pl("subtree", "static").exposure_rate_pct_mean, 1)} % at 8 kbps, against ${num(Math.min(...uni), 1)}–${num(Math.max(...uni), 1)} % with uniform placements), so the placement-level interval [${sgn(e.placement_ci95_lo, 1)}, ${sgn(e.placement_ci95_hi, 1)}] includes 0. These are simulated values for one proposed layout with an uncalibrated open-space radio model, not campus measurements.</span>`;
    const kpi = (val, unit, lab, note, color) => `<div class="kpi"><div class="num"${color ? ` style="color:${color}"` : ""}>${val}<span class="unit">${unit}</span></div><div class="label">${lab}</div><div class="note">${note}</div></div>`;
    const s8 = bp(8, "static"), r8 = bp(8, "riskaware"), o32 = bp(32, "olsr"), r32 = bp(32, "riskaware");
    $("cms-kpis").innerHTML =
      kpi(num(r8.pdr_nominal_pct_mean, 2), "%", "Risk-Aware PDR · 8 kbps · k = 3", `Static ${num(s8.pdr_nominal_pct_mean, 1)} % · OLSR ${num(bp(8, "olsr").pdr_nominal_pct_mean, 1)} % · 15 draws`) +
      kpi(num(s8.exposure_rate_pct_mean, 1), "%", "Static exposure · 8 kbps · k = 3", `Risk-Aware ${num(r8.exposure_rate_pct_mean, 2)} % · OLSR ${num(bp(8, "olsr").exposure_rate_pct_mean, 1)} %`) +
      kpi(num(r32.pdr_nominal_pct_mean, 1), "%", "Risk-Aware PDR · 32 kbps", `Static ${num(bp(32, "static").pdr_nominal_pct_mean, 1)} % · OLSR ${num(o32.pdr_nominal_pct_mean, 1)} % (OLSR ${num(D.stats.k0_baseline.find(x => x.rate_kbps === 32 && x.protocol === "olsr").pdr_nominal_pct_mean, 1)} % without risk)`) +
      kpi(String(D.topology.max_hop), "hops", "Deepest route (90 m model)", `vs 2–3 in the generic 250 m fields · ${D.design.n_sensors} sensors`);
  }

  // ---------------------------------------------------------------- map
  function initMap() {
    map = L.map("cms-map", { scrollWheelZoom: false, zoomSnap: 0.25 });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors' }).addTo(map);
    const base = L.layerGroup().addTo(map);
    L.polygon(C.campus.ring, { color: "#123b84", weight: 2, dashArray: "6 4", fill: false, interactive: false }).addTo(base);
    C.water.forEach(w => L.polygon(w.ring, { color: "#0e6f9c", weight: 1, fillColor: "#7cc3e6", fillOpacity: 0.45, interactive: false }).addTo(base));
    C.roads.forEach(r => L.polyline(r.line, { color: "#9aa5b1", weight: r.kind === "footway" ? 1.2 : 2.5, opacity: 0.7, interactive: false }).addTo(base));
    C.buildings.forEach(b => L.polygon(b.ring, { color: "#6b7686", weight: 1, fillColor: "#c9ced6", fillOpacity: 0.5, interactive: false }).addTo(base));
    over = L.layerGroup().addTo(map);
    map.fitBounds(L.polygon(C.campus.ring).getBounds(), { padding: [10, 10] });
    if (typeof ResizeObserver !== "undefined") new ResizeObserver(() => map.invalidateSize()).observe($("cms-map"));
  }
  const runSel = () => D.runs.find(r => r.place === S.place && r.rate === S.rate && r.protocol === S.proto);
  const walk = (tree, i) => { const p = [i]; while (p[p.length - 1] !== gwId() && tree[p[p.length - 1]] >= 0 && p.length < 200) p.push(tree[p[p.length - 1]]); return p; };

  function renderControls() {
    pills($("cms-place"), D.design.placements.map(p => [p, PLACE(p)]), S.place, v => { S.place = v; renderMap(); renderControls(); });
    pills($("cms-rate"), D.design.rates.map(r => [r, `${r} kbps`]), S.rate, v => { S.rate = v; renderMap(); renderControls(); });
    pills($("cms-proto"), Object.keys(PROTO).map(p => [p, PROTO[p][0]]), S.proto, v => { S.proto = v; renderMap(); renderControls(); });
    const L_ = new Set(["links", "routes", "traffic"].filter(k => S[k]));
    pills($("cms-layers"), [["links", "90 m link model"], ["routes", "Installed routes"], ["traffic", "Observed traffic"]], L_, v => { S[v] = !S[v]; renderMap(); renderControls(); }, true);
    const line = (c, w, dash) => `<svg width="24" height="10" aria-hidden="true"><line x1="1" y1="5" x2="23" y2="5" stroke="${c}" stroke-width="${w}" ${dash ? `stroke-dasharray="${dash}"` : ""}/></svg>`;
    const dot = (c, ring) => `<svg width="14" height="14" aria-hidden="true"><circle cx="7" cy="7" r="5" fill="${c}" stroke="${ring || "#fff"}" stroke-width="1.5"/></svg>`;
    $("cms-legend").innerHTML = `<span class="item"><svg width="14" height="14" aria-hidden="true"><rect x="1" y="1" width="12" height="12" fill="#17202e"/></svg>Gateway</span><span class="item">${dot("#a3261b", "#a3261b")}High-risk relay</span>` +
      Object.entries(APPC).map(([k, c]) => `<span class="item">${dot(c)}${k[0].toUpperCase() + k.slice(1)} sensor</span>`).join("") +
      `<span class="item">${line("#8592a3", 1, "3 3")}90 m link model <em>(reconstructed)</em></span><span class="item">${line(PROTO[S.proto][1], 3)}Installed route <em>(simulation output)</em></span>` +
      `<span class="item">${line(PROTO[S.proto][1] + "88", 6)}Observed traffic <em>(simulation output)</em></span>`;
  }

  function renderMap() {
    if (!map) return;
    over.clearLayers();
    const run = runSel(), LL = D.nodes.map(n => n.ll), gw = gwId(), hs = new Set(run.high), col = PROTO[run.protocol][1];
    if (S.links) D.topology.links.forEach(([i, j]) => L.polyline([LL[i], LL[j]], { color: "#8592a3", weight: 1, dashArray: "3 3", opacity: 0.7, interactive: false }).addTo(over));
    if (S.traffic) {
      const mx = Math.max(...run.uses.map(u => u[2]));
      run.uses.forEach(([a, b, n]) => L.polyline([LL[a], LL[b]], { color: col, weight: 1 + 7 * Math.sqrt(n / mx), opacity: 0.4 }).bindTooltip(`${a} → ${b === gw ? "GW" : b}: ${n.toLocaleString()} packets (simulated)`).addTo(over));
    }
    if (S.routes && run.tree) for (let i = 0; i < gw; i++) if (run.tree[i] >= 0) L.polyline([LL[i], LL[run.tree[i]]], { color: col, weight: 2.5, opacity: 0.85, interactive: false }).addTo(over);
    if (S.sel != null) {
      const path = run.tree ? walk(run.tree, S.sel) : ((run.paths[S.sel][0] || [0, 0, []])[2]);
      if (path.length > 1) L.polyline(path.map(i => LL[i]), { color: "#1d5fd1", weight: 6, opacity: 0.85, interactive: false }).addTo(over);
    }
    D.nodes.forEach((n, i) => {
      if (i === gw) return;
      const h = hs.has(i), s = run.src[i], pdr = s[0] ? 100 * s[1] / s[0] : 0;
      L.circleMarker(LL[i], { radius: i === S.sel ? 8 : h ? 7 : 5.5, weight: i === S.sel ? 3 : 1.5, color: i === S.sel ? "#1d5fd1" : h ? "#a3261b" : "#fff", fillColor: h ? "#a3261b" : APPC[n.app], fillOpacity: 1 })
        .bindTooltip(`Sensor ${i} · ${esc(n.app)}${h ? " · <b style='color:#a3261b'>high-risk</b>" : ""}<br>simulated delivery ${pdr.toFixed(1)} % (${s[1].toLocaleString()} of ${s[0].toLocaleString()})`, { direction: "top" })
        .on("click", () => { S.sel = i; renderMap(); }).addTo(over);
    });
    L.marker(LL[gw], { icon: L.divIcon({ className: "cs-gw", html: "<span>GW</span>", iconSize: [26, 26], iconAnchor: [13, 13] }), title: "Gateway" }).bindTooltip("Gateway (administration building)").addTo(over);
    const m = run.metrics;
    $("cms-run").innerHTML = `<div class="panel-head"><h3>${PROTO[run.protocol][0]} · ${esc(PLACE(run.place))} · ${run.rate} kbps</h3><span class="tag measured">simulation output</span></div>` +
      `<p class="panel-sub" style="margin:0 0 6px">Run <code>${esc(run.id)}</code> (seed 1 shown on the map; tables use all 3 seeds).${run.high.length ? ` High-risk relays: <strong>${run.high.join(", ")}</strong>.` : ""}</p>` +
      `<p class="panel-sub" style="margin:0">Nominal PDR <strong>${m.pdr_nominal_pct.toFixed(2)} %</strong> · exposure <strong>${m.exposure_rate_pct.toFixed(2)} %</strong> · throughput ${m.sink_thr_kbps.toFixed(1)} kbps · p50 / p95 delay ${m.delay_p50_ms.toFixed(0)} / ${m.delay_p95_ms.toFixed(0)} ms · mean hops ${m.mean_hops_delivered.toFixed(2)} · gateway airtime ${m.gw_airtime.toFixed(3)}.` +
      (!run.tree && !S.traffic ? ' <strong>OLSR installs no fixed tree: turn on "Observed traffic".</strong>' : "") + `</p>`;
    const box = $("cms-info"), i = S.sel;
    if (i == null) box.innerHTML = '<p class="panel-sub" style="margin:0">Click a sensor to see its simulated route and packet counts.</p>';
    else {
      const s = run.src[i], n = D.nodes[i], fmt = p => p.map(v => v === gw ? "GW" : v).join(" → ");
      box.innerHTML = `<div class="panel-head"><h3>Sensor ${i} · ${esc(n.app)}${hs.has(i) ? ' <span class="tag risk">high-risk</span>' : ""}</h3><span class="tag measured">simulation output</span></div>` +
        `<p class="panel-sub" style="margin:0 0 6px">Site: ${esc(n.src)} · ${D.topology.hop[i]} hop(s) by BFS · sent ${s[0].toLocaleString()}, delivered ${s[1].toLocaleString()}, risk-dropped ${s[2].toLocaleString()} · forwarded ${run.fwd[i].toLocaleString()} packets for others.</p>` +
        (run.tree ? `<div class="topo-route"><div class="k" style="color:${PROTO[run.protocol][1]}">Installed route</div><div class="topo-path">${fmt(walk(run.tree, i))}</div></div>` : "") +
        `<p class="panel-sub" style="margin:8px 0 2px">Observed paths (${run.n_paths[i]} distinct${run.n_paths[i] > 3 ? ", 3 most used" : ""}):</p><ul class="topo-paths">` +
        run.paths[i].map(([pk, dl, p]) => `<li><span class="topo-path">${fmt(p)}</span>${p.length === 1 ? " (lost before the first hop)" : ""}: ${pk.toLocaleString()} packets, ${dl.toLocaleString()} delivered</li>`).join("") + "</ul>";
    }
    $("cms-mapnote").innerHTML = "Node positions are the proposed campus sites, used unchanged by ns-3. Routes and traffic are simulation outputs on an open-space radio model: buildings are drawn for orientation only and do not affect the simulated signal.";
  }

  // ---------------------------------------------------------------- tables and charts
  function renderTable() {
    const cols = [["pdr_nominal_pct", "Nominal PDR (%)", 2], ["sink_thr_kbps", "Throughput (kbps)", 1], ["lost_pkts", "Lost packets", 0], ["exposure_rate_pct", "Exposure (%)", 2],
      ["delay_p50_ms", "Delay p50 (ms)", 0], ["delay_p95_ms", "Delay p95 (ms)", 0], ["mean_hops_delivered", "Hops (delivered)", 2], ["gw_airtime", "Gateway airtime", 3]];
    $("cms-tab").innerHTML = "<thead><tr><th>Protocol</th>" + cols.map(c => `<th>${c[1]}</th>`).join("") + "<th>Zero-exposure draws</th></tr></thead><tbody>" +
      Object.keys(PROTO).map(p => { const r = bp(S.tabRate, p); return `<tr><td>${PROTO[p][0]}</td>` + cols.map(([m, , d]) => `<td class="num">${ci(r, m, d)}</td>`).join("") + `<td class="num">${r.zero_exposure_draws}/${r.n_draws}</td></tr>`; }).join("") + "</tbody>";
  }
  function bars(el, m, opts) {
    const series = {}, colors = {};
    Object.keys(PROTO).forEach(p => { series[PROTO[p][0]] = D.design.rates.map(rate => { const r = bp(rate, p); return { x: `${rate} kbps`, y: r[m + "_mean"], ci: r[m + "_ci95_hi"] - r[m + "_mean"], n: r.n_draws }; }); colors[PROTO[p][0]] = PROTO[p][2]; });
    groupedBar(el, series, Object.assign({ colors, yfmt: 0 }, opts));
    let cap = el.parentNode.querySelector(":scope > .ci-caption");
    if (!cap) { cap = document.createElement("div"); cap.className = "ci-caption"; el.insertAdjacentElement("afterend", cap); }
    cap.innerHTML = '<span class="ci-key whisker"></span>whiskers = mean ± 95% CI · Student t over 15 matched draws (df = 14); draws are nested in 5 risk placements';
  }
  function renderPairs() {
    const keep = ["pdr_nominal_pct", "exposure_rate_pct", "sink_thr_kbps", "lost_pkts", "delay_p95_ms", "mean_hops_delivered", "gw_airtime", "mpdu_retry_drop"];
    const lab = { pdr_nominal_pct: "Nominal PDR (%)", exposure_rate_pct: "Exposure (%)", sink_thr_kbps: "Throughput (kbps)", lost_pkts: "Lost packets", delay_p95_ms: "Delay p95 (ms)", mean_hops_delivered: "Hops (delivered)", gw_airtime: "Gateway airtime", mpdu_retry_drop: "MAC retry drops" };
    const dg = m => m === "gw_airtime" ? 3 : m.endsWith("pct") || m === "mean_hops_delivered" ? 2 : m === "sink_thr_kbps" ? 1 : 0;
    $("cms-pair").innerHTML = "<thead><tr><th>Comparison</th><th>Metric</th><th>A</th><th>B</th><th>A − B</th><th>95 % CI (draws)</th><th>95 % CI (placements)</th><th>A higher / equal / lower</th><th>Sign-flip p</th><th>Holm p</th><th>Result</th></tr></thead><tbody>" +
      D.stats.paired.filter(x => x.rate_kbps === S.pairRate && keep.includes(x.metric)).sort((a, b) => keep.indexOf(a.metric) - keep.indexOf(b.metric)).map(x => {
        const d = dg(x.metric), same = x.class === "identical";
        return `<tr${x.primary ? ' style="font-weight:600"' : ""}><td>${PROTO[x.A][0]} − ${PROTO[x.B][0]}</td><td>${lab[x.metric]}</td><td class="num">${num(x.A_mean, d)}</td><td class="num">${num(x.B_mean, d)}</td><td class="num">${sgn(x.diff_mean, d)}</td>` +
          `<td class="num">${same ? "—" : `[${sgn(x.diff_ci95_lo, d)}, ${sgn(x.diff_ci95_hi, d)}]`}</td><td class="num">${same ? "—" : `[${sgn(x.placement_ci95_lo, d)}, ${sgn(x.placement_ci95_hi, d)}]`}</td>` +
          `<td class="num">${x.draws_A_higher} / ${x.draws_equal} / ${x.draws_A_lower}</td><td class="num">${same ? "—" : pfmt(x.p_signflip_exact)}</td><td class="num">${x.p_signflip_holm == null ? (x.primary ? "—" : "secondary") : pfmt(x.p_signflip_holm)}</td><td>${tag(x.class)}</td></tr>`;
      }).join("") + "</tbody>";
  }
  function renderPlacements() {
    const places = [...new Set(D.stats.per_placement.map(x => x.place))];
    $("cms-place-tab").innerHTML = "<thead><tr><th>Placement</th><th>Rate</th><th>High-risk</th>" + Object.keys(PROTO).map(p => `<th>${PROTO[p][0]} PDR / exp. (%)</th>`).join("") + "</tr></thead><tbody>" +
      D.design.rates.flatMap(rate => places.map(pl => {
        const v = p => D.stats.per_placement.find(x => x.rate_kbps === rate && x.place === pl && x.protocol === p);
        return `<tr><td>${esc(PLACE(pl))}</td><td>${rate} kbps</td><td>${esc(v("static").high_risk_ids)}</td>` + Object.keys(PROTO).map(p => `<td class="num">${v(p).pdr_nominal_pct_mean.toFixed(2)} / ${v(p).exposure_rate_pct_mean.toFixed(2)}</td>`).join("") + "</tr>";
      })).join("") + "</tbody>";
    $("cms-k0").innerHTML = "<thead><tr><th>Rate</th><th>Protocol</th><th>Nominal PDR (%)</th><th>Delay p95 (ms)</th><th>Gateway airtime</th></tr></thead><tbody>" +
      D.stats.k0_baseline.map(r => `<tr><td>${r.rate_kbps} kbps</td><td>${PROTO[r.protocol][0]}</td><td class="num">${r.pdr_nominal_pct_mean.toFixed(2)} <span style="color:var(--text-faint);font-size:.72rem">(${r.pdr_nominal_pct_min.toFixed(2)}–${r.pdr_nominal_pct_max.toFixed(2)})</span></td><td class="num">${r.delay_p95_ms_mean.toFixed(0)}</td><td class="num">${r.gw_airtime_mean.toFixed(3)}</td></tr>`).join("") + "</tbody>";
    const k0 = (rate, p) => D.stats.k0_baseline.find(x => x.rate_kbps === rate && x.protocol === p);
    $("cms-k0-notes").innerHTML = `<li>Without risk, Static and Risk-Aware install the same tree, so their rows match. The differences between them in the k = 3 results come from routing around high-risk relays.</li>` +
      `<li>Going from 8 to 32 kbps per sensor without risk, OLSR's PDR changes from ${k0(8, "olsr").pdr_nominal_pct_mean.toFixed(1)} % to ${k0(32, "olsr").pdr_nominal_pct_mean.toFixed(1)} %, and Static's from ${k0(8, "static").pdr_nominal_pct_mean.toFixed(1)} % to ${k0(32, "static").pdr_nominal_pct_mean.toFixed(1)} % (simulated load effect).</li>`;
  }
  function renderMethod() {
    const d = D.design;
    $("cms-method").innerHTML = [
      `<strong>Simulator.</strong> <code>${esc(d.simulator)}</code> (sha256 <code>${d.source_sha256.slice(0, 8)}…</code>). This is the validated Wi-Fi 6 risk simulator plus one option that reads node positions from a file. Without that option its output is byte-identical to a validated run.`,
      `<strong>Topology.</strong> ${d.n_sensors} sensors at the proposed campus sites and the gateway at the administration building, from the positions file (sha256 <code>${d.positions_sha256.slice(0, 8)}…</code>). Node ids equal the dashboard ids. The 90 m link model is connected: up to ${D.topology.max_hop} hops, ${D.topology.mean_degree} links per node on average.`,
      `<strong>Radio and traffic.</strong> As in the validated study: 802.11ax HE MCS0, 2.4 GHz, 20 MHz, 20 dBm, log-distance exponent 3, 512-byte UDP CBR to the gateway, 30–300 s.`,
      `<strong>Design.</strong> Static, Risk-Aware and OLSR × {no risk, subtree, uniform P101–P104} × {8, 32} kbps × seeds {${d.seeds.join(", ")}} = ${d.runs} runs. Uniform sets: ${Object.entries(d.uniform_sets).map(([k, v]) => `${k} [${v.join(", ")}]`).join(", ")}. Within a (placement, seed) draw the protocols share traffic, risk set and every risk-drop decision.`,
      `<strong>Validation.</strong> A 6-run pilot (88 checks passed, 0 failed) came before the matrix. Matrix: ${esc(D.checks.split(": ")[1])}. The gates check exit status, packet accounting, the high-risk set against a reference model, every risk drop, delivered paths against the installed tree, matched traffic schedules, the 802.11ax mode, and that the simulator used the file's coordinates (P7). Every run has a provenance record and output checksums.`,
      `<strong>Runtime.</strong> ${D.runtime.total_run_hours} run-hours in total.`
    ].map(x => `<li>${x}</li>`).join("");
    $("cms-provenance").innerHTML = `Data: <a href="data/campus-sim.json">data/campus-sim.json</a>, built by <code>${esc(D.generated_by)}</code> from batch <code>${esc(D.batch)}</code> (${Object.keys(D.sources).length} source files with sha256). Base map © OpenStreetMap contributors (ODbL).`;
  }

  async function init() {
    if (!$("view-campus-sim")) return;
    try {
      [D, C] = await Promise.all(["data/campus-sim.json", "data/campus/campus.json"].map(u => fetch(u).then(r => { if (!r.ok) throw new Error(u + " " + r.status); return r.json(); })));
    } catch (e) {
      console.warn("campus simulation data unavailable:", e);
      document.querySelectorAll('[id^="cms-"]').forEach(el => { if (el.textContent.trim() === "—") el.textContent = "Data file unavailable."; });
      return;
    }
    renderHead();
    if (typeof L !== "undefined") initMap(); else $("cms-map").innerHTML = '<p class="panel-sub" style="padding:16px">The map library could not be loaded.</p>';
    renderControls(); renderMap();
    pills($("cms-tab-rate"), D.design.rates.map(r => [r, `${r} kbps`]), S.tabRate, function f(v) { S.tabRate = v; pills($("cms-tab-rate"), D.design.rates.map(r => [r, `${r} kbps`]), v, f); renderTable(); });
    renderTable();
    legend($("cms-chart-legend"), Object.keys(PROTO).map(p => [PROTO[p][0], resolveColor(PROTO[p][2])]));
    bars($("cms-chart-pdr"), "pdr_nominal_pct", { tipfmt: 2, unit: " %", ytitle: "Nominal PDR (%)" });
    bars($("cms-chart-exp"), "exposure_rate_pct", { yfmt: 1, tipfmt: 2, unit: " %", ytitle: "Exposure (%)" });
    pills($("cms-pair-rate"), D.design.rates.map(r => [r, `${r} kbps`]), S.pairRate, function f(v) { S.pairRate = v; pills($("cms-pair-rate"), D.design.rates.map(r => [r, `${r} kbps`]), v, f); renderPairs(); });
    renderPairs(); renderPlacements(); renderMethod();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
