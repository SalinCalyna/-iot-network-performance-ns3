// Wi-Fi 6 uniform random risk-placement section. Every number comes from data/wifi6-randplace.json, built by
// experiments/wifi6-risk/build_site_randplace.py (ns-3-dev) from analyze_randplace.py / analyze_randplace_stats.py
// outputs; the JSON lists each source file with its sha256. A result is called significant only when the analysis
// classed it "supported"; Risk-Aware vs Static is descriptive by design (7 of 12 draws identical).
(function () {
  "use strict";
  let RP = null;
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const $ = id => document.getElementById(id);
  const num = (x, d) => (x < 0 ? "−" : "") + Math.abs(x).toFixed(d);
  const sgn = (x, d) => (x > 0 ? "+" : x < 0 ? "−" : "±") + Math.abs(x).toFixed(d);
  const pfmt = p => p < 0.001 ? p.toExponential(2).replace("e-", " × 10^−") : p.toPrecision(3);
  const COLORS = { static: "var(--static)", riskaware: "var(--riskaware)", olsr: "var(--olsr)" };
  const CLS = { supported: ["measured", "Supported"], consistent: ["intervention", "Consistent"], descriptive: ["planned", "Descriptive"], identical: ["repro", "Identical"] };
  const tag = c => `<span class="tag ${CLS[c][0]}">${CLS[c][1]}</span>`;

  const label = p => RP.protocols.find(x => x.key === p).label;
  const metric = k => RP.metrics.find(m => m.key === k);
  const bp = (rate, p) => RP.by_protocol.find(x => x.rate === rate && x.protocol === p);
  const pair = (rate, a, b, m) => RP.paired.find(x => x.rate === rate && x.A === a && x.B === b && x.metric === m);
  const cond = (rate, c, a, b, m) => RP.conditional.find(x => x.rate === rate && x.condition === c && x.A === a && x.B === b && x.metric === m);
  const ci = (v, d) => `[${num(v[2], d)}, ${num(v[3], d)}]`;
  const dci = (v, d) => `[${sgn(v[2], d)}, ${sgn(v[3], d)}]`;

  function pills(container, options, active, onChange) {
    container.innerHTML = "";
    options.forEach((o, i) => {
      const b = document.createElement("button");
      b.className = "pill" + (i === active ? " active" : "");
      b.type = "button";
      b.textContent = o;
      b.setAttribute("aria-pressed", i === active ? "true" : "false");
      b.addEventListener("click", () => {
        [...container.children].forEach(c => { c.classList.remove("active"); c.setAttribute("aria-pressed", "false"); });
        b.classList.add("active");
        b.setAttribute("aria-pressed", "true");
        onChange(i);
      });
      container.appendChild(b);
    });
  }

  function renderHead() {
    const eRO8 = pair(8, "riskaware", "olsr", "exposure_rate_pct"), eRO32 = pair(32, "riskaware", "olsr", "exposure_rate_pct");
    const pRO32 = pair(32, "riskaware", "olsr", "pdr_nominal_pct"), pSO32 = pair(32, "static", "olsr", "pdr_nominal_pct");
    const eSO8 = pair(8, "static", "olsr", "exposure_rate_pct"), eSO32 = pair(32, "static", "olsr", "exposure_rate_pct");
    const onTree = RP.draws.filter(d => d.on_tree).length;
    $("rp-kf").innerHTML = `<span class="kf-label">Key Finding</span><span>With risk placed independently of every protocol, <strong>Static and OLSR are about equally exposed</strong>: Static − OLSR exposure ${sgn(eSO8.diff[0], 2)} pp ${dci(eSO8.diff, 2)} at 8 kbps and ${sgn(eSO32.diff[0], 2)} pp ${dci(eSO32.diff, 2)} at 32 kbps, so no difference is detected. The 37 pp gap of the subtree design does not appear. <strong>Risk-Aware is less exposed than OLSR in 12/12 draws</strong> (${sgn(eRO8.diff[0], 2)} and ${sgn(eRO32.diff[0], 2)} pp, Holm p = ${pfmt(eRO8.p_holm)}). Against Static, Risk-Aware changes the outcome only in the ${onTree} draws where a risky node lies on Static's tree, and those PDR gains are descriptive, not statistically significant.</span>`;
    const kpi = (val, unit, lab, note, color) => `<div class="kpi"><div class="num"${color ? ` style="color:${color}"` : ""}>${val}<span class="unit">${unit}</span></div><div class="label">${lab}</div><div class="note">${note}</div></div>`;
    $("rp-kpis").innerHTML =
      kpi(sgn(eSO8.diff[0], 2), "pp", "Static − OLSR exposure · 8 kbps", `95 % CI ${dci(eSO8.diff, 2)} · no difference detected`) +
      kpi(sgn(eRO32.diff[0], 2), "pp", "Risk-Aware − OLSR exposure · 32 kbps", `95 % CI ${dci(eRO32.diff, 2)} · 12/12 draws · supported`, "var(--ok)") +
      kpi(sgn(pRO32.diff[0], 1), "pp", "Risk-Aware − OLSR PDR · 32 kbps", `95 % CI ${dci(pRO32.diff, 1)} · 12/12 · supported (Static − OLSR ${sgn(pSO32.diff[0], 1)} pp)`, "var(--ok)") +
      kpi(`${onTree}/${RP.draws.length}`, "draws", "Risk-Aware ≠ Static", `${RP.draws.length - onTree} draws identical on every metric · gains vs Static descriptive`);
  }

  let tabRate = 8;
  function renderTable() {
    const cols = ["exposure_rate_pct", "pdr_nominal_pct", "delay_p95_ms", "gw_airtime", "mpdu_retry_drop"];
    $("rp-tab-title").textContent = `${tabRate} kbps per sensor · 12 draws per protocol`;
    const head = "<thead><tr><th>Protocol</th>" + cols.map(c => `<th>${esc(metric(c).label)} (${esc(metric(c).unit)})</th>`).join("") + "<th>Zero-exposure draws</th></tr></thead>";
    const body = RP.protocols.map(p => {
      const r = bp(tabRate, p.key);
      return `<tr><td>${esc(p.label)}</td>` + cols.map(c => {
        const d = metric(c).digits, v = r[c];
        return `<td class="num">${num(v[0], d)}<br><span style="color:var(--text-faint);font-size:.72rem">${ci(v, d)}</span></td>`;
      }).join("") + `<td class="num">${r.zero_exposure_draws}/12</td></tr>`;
    }).join("");
    $("rp-tab").innerHTML = head + "<tbody>" + body + "</tbody>";
  }

  function rateBars(container, m, opts) {
    const series = {};
    RP.protocols.forEach(p => {
      series[p.label] = RP.design.rates_kbps.map(rate => {
        const v = bp(rate, p.key)[m];
        return { x: `${rate} kbps`, y: v[0], ci: v[3] - v[0], n: 12 };
      });
    });
    const colors = {};
    RP.protocols.forEach(p => { colors[p.label] = COLORS[p.key]; });
    groupedBar(container, series, Object.assign({ colors, yfmt: 0 }, opts));
    let cap = container.parentNode.querySelector(":scope > .ci-caption");
    if (!cap) { cap = document.createElement("div"); cap.className = "ci-caption"; container.insertAdjacentElement("afterend", cap); }
    cap.innerHTML = '<span class="ci-key whisker"></span>whiskers = mean ± 95% CI · Student t over n = 12 matched draws (df = 11). Draws are nested in 3 topologies (see the statistical limitations).';
  }

  let drawRate = 8;
  function drawChart(container) {
    remember(container, drawChart, [container]);
    container.innerHTML = "";
    const tip = ensureTooltip(container);
    const { W } = chartSize(container, {}), H = W < 420 ? 260 : 280;
    const pad = { l: 44, r: 8, t: 12, b: 52 }, plotW = W - pad.l - pad.r, plotH = H - pad.t - pad.b;
    const D = RP.draws, n = D.length, gw = plotW / n;
    const vals = D.flatMap(d => RP.protocols.map(p => d.values[String(drawRate)][p.key].exposure_rate_pct));
    const yMax = niceMax(Math.max(...vals) * 1.08);
    const y = v => pad.t + plotH - (v / yMax) * plotH;
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, class: "chart", role: "img" });
    const t0 = el("title", {}); t0.textContent = `Risk exposure per draw at ${drawRate} kbps for Static, Risk-Aware and OLSR`; svg.appendChild(t0);
    D.forEach((d, i) => { if (d.on_tree) svg.appendChild(el("rect", { x: pad.l + i * gw, y: pad.t, width: gw, height: plotH, fill: toRgba("var(--riskaware)", 0.12) })); });
    for (let i = 0; i <= 4; i++) {
      const yy = pad.t + plotH - (i / 4) * plotH;
      svg.appendChild(el("line", { x1: pad.l, x2: W - pad.r, y1: yy, y2: yy, class: "gridline" }));
      const t = el("text", { x: pad.l - 5, y: yy + 4, "text-anchor": "end" }); t.textContent = fmt(yMax * i / 4, 1); svg.appendChild(t);
    }
    axisTitles(svg, W, H, pad, { ytitle: "Exposure (%)" });
    const off = { static: -0.24, riskaware: 0, olsr: 0.24 };
    const shape = { static: "circle", riskaware: "diamond", olsr: "square" };
    D.forEach((d, i) => {
      const cx0 = pad.l + (i + 0.5) * gw;
      RP.protocols.forEach(p => {
        const v = d.values[String(drawRate)][p.key].exposure_rate_pct, cx = cx0 + off[p.key] * gw, cy = y(v), r = Math.max(3.2, Math.min(5, gw / 7));
        const fill = resolveColor(COLORS[p.key]);
        const m = shape[p.key] === "circle" ? el("circle", { cx, cy, r, fill })
          : shape[p.key] === "square" ? el("rect", { x: cx - r, y: cy - r, width: 2 * r, height: 2 * r, fill })
            : el("path", { d: `M${cx} ${cy - r * 1.3}L${cx + r * 1.3} ${cy}L${cx} ${cy + r * 1.3}L${cx - r * 1.3} ${cy}Z`, fill });
        m.setAttribute("stroke", "#fff"); m.setAttribute("stroke-width", "1");
        const onMove = ev => {
          const b = container.getBoundingClientRect(), vv = d.values[String(drawRate)];
          showTip(container, tip, ev.clientX - b.left, ev.clientY - b.top,
            `<div class="t-title">Topology ${d.seed} · placement ${d.place}</div><div class="t-note">High-risk sensors ${esc(d.high_risk_ids)}${d.on_tree ? ` · on Static's tree (${d.static_sources_exposed} sources)` : " · not on Static's tree"}</div>` +
            RP.protocols.map(q => `<div class="t-row"><span>${q.label}</span><span>${vv[q.key].exposure_rate_pct.toFixed(2)} %</span></div>`).join(""));
        };
        m.addEventListener("mousemove", onMove); m.addEventListener("mouseleave", () => hideTip(tip));
        svg.appendChild(m);
      });
      const t = el("text", { x: cx0, y: pad.t + plotH + 14, "text-anchor": "middle", "font-size": 10 }); t.textContent = d.place; svg.appendChild(t);
    });
    [...new Set(D.map(d => d.seed))].forEach(s => {
      const idx = D.map((d, i) => d.seed === s ? i : -1).filter(i => i >= 0), a = pad.l + idx[0] * gw + 3, b = pad.l + (idx[idx.length - 1] + 1) * gw - 3;
      svg.appendChild(el("line", { x1: a, x2: b, y1: pad.t + plotH + 22, y2: pad.t + plotH + 22, stroke: resolveColor("var(--border)"), "stroke-width": 1 }));
      const t = el("text", { x: (a + b) / 2, y: pad.t + plotH + 36, "text-anchor": "middle", "font-size": 11 }); t.textContent = `topology ${s}`; svg.appendChild(t);
    });
    container.appendChild(svg);
    let lg = container.parentNode.querySelector(":scope > .rp-shape-legend");
    if (!lg) { lg = document.createElement("div"); lg.className = "legend rp-shape-legend"; container.insertAdjacentElement("beforebegin", lg); }
    const sym = { static: "●", riskaware: "◆", olsr: "■" };
    lg.innerHTML = RP.protocols.map(p => `<span class="item"><span style="color:${resolveColor(COLORS[p.key])};font-size:1rem;line-height:1">${sym[p.key]}</span> ${esc(p.label)}</span>`).join("") +
      `<span class="item"><span class="sw" style="background:${toRgba("var(--riskaware)", 0.25)}"></span>risky node on Static's tree</span>`;
  }

  function renderDraws() {
    drawChart($("rp-chart-draws"));
    const s = bp(drawRate, "static"), o = bp(drawRate, "olsr");
    $("rp-draws-note").innerHTML = `<strong>${drawRate} kbps.</strong> Static: exposure 0 in ${s.zero_exposure_draws}/12 draws and up to ${s.exposure_max.toFixed(2)} % in the rest (concentrated). OLSR: non-zero in ${12 - o.zero_exposure_draws}/12 draws but at most ${o.exposure_max.toFixed(2)} % (diffuse). Risk-Aware: 0 in all 12 draws. The pattern matches the pre-registered hypothesis H4; it is descriptive.`;
  }

  function renderCases() {
    const onTree = RP.draws.filter(d => d.on_tree).length;
    $("rp-cases-sub").textContent = `Risk-Aware's Dijkstra re-routes only around risky nodes that lie on a route. In ${RP.draws.length - onTree} draws no high-risk sensor lies on Static's BFS tree, so Risk-Aware installs the same routes, and its runs equal Static's on every metric at both rates (checked when the data file is built). In the other ${onTree} draws it re-routes the affected sources.`;
    const head = "<thead><tr><th>Draw</th><th>High-risk sensors</th><th>Outcome</th><th>Static sources through a risky node</th><th>Exposure % Static → Risk-Aware</th><th>PDR Risk-Aware − Static, 8 kbps (pp)</th><th>PDR Risk-Aware − Static, 32 kbps (pp)</th></tr></thead>";
    const rows = RP.draws.slice().sort((a, b) => (b.on_tree - a.on_tree) || a.seed - b.seed || a.place - b.place).map(d => {
      const v8 = d.values["8"], v32 = d.values["32"];
      const dp = v => v.riskaware.pdr_nominal_pct - v.static.pdr_nominal_pct;
      return `<tr><td style="white-space:nowrap">${d.seed} / ${d.place}</td><td style="white-space:nowrap">${esc(d.high_risk_ids)}</td><td>${d.on_tree ? '<span class="tag intervention" style="white-space:nowrap">Re-routed</span>' : '<span class="tag repro" style="white-space:nowrap">Identical</span>'}</td>` +
        `<td class="num">${d.static_sources_exposed}</td><td class="num">${v8.static.exposure_rate_pct.toFixed(2)} → ${v8.riskaware.exposure_rate_pct.toFixed(2)}</td>` +
        `<td class="num">${d.on_tree ? sgn(dp(v8), 2) : "0"}</td><td class="num">${d.on_tree ? sgn(dp(v32), 2) : "0"}</td></tr>`;
    }).join("");
    $("rp-cases").innerHTML = head + "<tbody>" + rows + "</tbody>";
    const c8 = cond(8, "on_tree", "riskaware", "static", "pdr_nominal_pct"), c32 = cond(32, "on_tree", "riskaware", "static", "pdr_nominal_pct");
    const ce = cond(8, "on_tree", "riskaware", "static", "exposure_rate_pct");
    const p8 = pair(8, "riskaware", "static", "pdr_nominal_pct"), p32 = pair(32, "riskaware", "static", "pdr_nominal_pct");
    $("rp-cases-note").innerHTML = `<strong>Descriptive, not statistically significant.</strong> In the ${c8.n} re-routed draws Risk-Aware removes all exposure (${sgn(ce.mean, 2)} pp, range ${sgn(ce.min, 2)} to ${sgn(ce.max, 2)}) and its nominal PDR is higher than Static's by ${sgn(c8.mean, 2)} pp at 8 kbps (range ${sgn(c8.min, 2)} to ${sgn(c8.max, 2)}, ${c8.higher}/${c8.n} higher) but only ${sgn(c32.mean, 2)} pp at 32 kbps (range ${sgn(c32.min, 2)} to ${sgn(c32.max, 2)}). Over all 12 draws the PDR gain vs Static is ${sgn(p8.diff[0], 2)} pp (sign-flip p = ${pfmt(p8.p_signflip)}, Holm ${pfmt(p8.p_holm)}) at 8 kbps and ${sgn(p32.diff[0], 2)} pp (p = ${pfmt(p32.p_signflip)}) at 32 kbps. With 7 zero differences the smallest attainable p is 0.0625, so this comparison cannot reach significance. The smaller gain at 32 kbps fits hypothesis H1, but rests on n = ${c8.n} draws.`;
  }

  let pairRate = 8;
  function niceStep(span) {
    const raw = span / 4, mag = Math.pow(10, Math.floor(Math.log10(raw)));
    return [1, 2, 2.5, 5, 10].map(m => m * mag).find(v => v >= raw);
  }
  function halo(t) {   // keep labels legible where they cross gridlines or intervals
    t.setAttribute("stroke", resolveColor("var(--panel)")); t.setAttribute("stroke-width", "4");
    t.setAttribute("paint-order", "stroke"); t.setAttribute("stroke-linejoin", "round");
    return t;
  }
  // Forest plot: one block per primary metric, each on its own x scale (exposure and PDR differ ~10x in range).
  function forest(container) {
    remember(container, forest, [container]);
    container.innerHTML = "";
    const { W } = chartSize(container, {});
    const small = W < 460, labW = small ? 0 : 150, rh = small ? 40 : 28, pad = { l: 10 + labW, r: 16 };
    const cmp = [["static", "olsr"], ["riskaware", "static"], ["riskaware", "olsr"]];
    const blocks = [["exposure_rate_pct", "Risk exposure"], ["pdr_nominal_pct", "Nominal PDR"]];
    const blockH = 22 + cmp.length * rh + 38;
    const H = blocks.length * blockH + 6;
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, class: "chart", role: "img" });
    const t0 = el("title", {}); t0.textContent = `Paired differences with 95 % intervals at ${pairRate} kbps`; svg.appendChild(t0);
    blocks.forEach(([m, mlab], bi) => {
      const rs = cmp.map(([a, b]) => pair(pairRate, a, b, m)), top = bi * blockH;
      const lo = Math.min(0, ...rs.map(r => Math.min(r.diff[2], r.topo_ci[0]))), hi = Math.max(0, ...rs.map(r => Math.max(r.diff[3], r.topo_ci[1])));
      const step = niceStep(hi - lo || 1), x0 = Math.floor(lo / step) * step, x1 = Math.ceil(hi / step) * step;
      const x = v => pad.l + (v - x0) / (x1 - x0) * (W - pad.l - pad.r);
      const head = el("text", { x: 4, y: top + 14, "font-size": 12, "font-weight": 700, fill: resolveColor("var(--text)") });
      head.textContent = `${mlab}, A − B (pp)`; svg.appendChild(head);
      const y0 = top + 22, y1 = y0 + cmp.length * rh;
      for (let v = x0; v <= x1 + 1e-9; v += step) {
        const xx = x(v);
        svg.appendChild(el("line", { x1: xx, x2: xx, y1: y0, y2: y1, class: "gridline" }));
        const t = el("text", { x: xx, y: y1 + 14, "text-anchor": "middle", "font-size": 10 }); t.textContent = fmt(v, step < 1 ? 1 : 0); svg.appendChild(t);
      }
      svg.appendChild(el("line", { x1: x(0), x2: x(0), y1: y0, y2: y1, stroke: resolveColor("var(--text)"), "stroke-width": 1.2 }));
      rs.forEach((r, i) => {
        const good = r.cls === "supported", yy = y0 + i * rh + (small ? rh - 10 : rh / 2);
        const lt = small ? el("text", { x: pad.l, y: yy - 11, "font-size": 11 }) : el("text", { x: 6, y: yy + 4, "font-size": 11 });
        lt.textContent = `${label(r.A)} − ${label(r.B)}${good ? " ✓" : ""}`;
        lt.setAttribute("fill", resolveColor(good ? "var(--ok)" : "var(--text-dim)"));
        const col = resolveColor(good ? "var(--ok)" : "var(--text-faint)");
        svg.appendChild(el("line", { x1: x(r.topo_ci[0]), x2: x(r.topo_ci[1]), y1: yy, y2: yy, stroke: col, "stroke-width": 1.2, opacity: 0.7 }));
        svg.appendChild(el("line", { x1: x(r.diff[2]), x2: x(r.diff[3]), y1: yy, y2: yy, stroke: col, "stroke-width": 5, "stroke-linecap": "round", opacity: 0.85 }));
        svg.appendChild(el("circle", { cx: x(r.diff[0]), cy: yy, r: 4, fill: resolveColor("var(--text)") }));
        svg.appendChild(halo(lt));
      });
    });
    container.appendChild(svg);
    let cap = container.parentNode.querySelector(":scope > .ci-caption");
    if (!cap) { cap = document.createElement("div"); cap.className = "ci-caption"; container.insertAdjacentElement("afterend", cap); }
    cap.innerHTML = "✓ and green = supported (Holm-adjusted). Grey = not supported, including every Risk-Aware − Static row, which cannot reach significance with 7 identical draws. The two blocks use different scales.";
  }

  function renderPaired() {
    forest($("rp-chart-forest"));
    $("rp-pair-title").textContent = `Paired differences A − B at ${pairRate} kbps (12 draws)`;
    const order = RP.metrics.map(m => m.key);
    const cmp = [["static", "olsr"], ["riskaware", "static"], ["riskaware", "olsr"]];
    const head = "<thead><tr><th>Comparison</th><th>Metric</th><th>A</th><th>B</th><th>A − B</th><th>95 % CI (draws)</th><th>95 % CI (topologies)</th><th>A higher / equal / lower</th><th>Sign-flip p</th><th>Holm p</th><th>Result</th></tr></thead>";
    const body = RP.paired.filter(x => x.rate === pairRate).sort((a, b) => cmp.findIndex(c => c[0] === a.A && c[1] === a.B) - cmp.findIndex(c => c[0] === b.A && c[1] === b.B) || order.indexOf(a.metric) - order.indexOf(b.metric)).map(x => {
      const m = metric(x.metric), d = m.digits, same = x.equal === 12;
      return `<tr${x.primary ? ' style="font-weight:600"' : ""}><td>${label(x.A)} − ${label(x.B)}</td><td>${esc(m.label)} (${esc(m.unit)})${x.primary ? "" : ""}</td>` +
        `<td class="num">${num(x.A_mean, d)}</td><td class="num">${num(x.B_mean, d)}</td><td class="num">${sgn(x.diff[0], d)}</td>` +
        `<td class="num">${same ? "—" : dci(x.diff, d)}</td><td class="num">${same ? "—" : `[${sgn(x.topo_ci[0], d)}, ${sgn(x.topo_ci[1], d)}]`}</td>` +
        `<td class="num">${x.higher} / ${x.equal} / ${x.lower}</td><td class="num">${same ? "—" : pfmt(x.p_signflip)}</td>` +
        `<td class="num">${x.p_holm == null ? (x.primary ? "—" : "secondary") : pfmt(x.p_holm)}</td><td>${tag(x.cls)}</td></tr>`;
    }).join("");
    $("rp-pair").innerHTML = head + "<tbody>" + body + "</tbody>";
  }

  function renderCongestion() {
    rateBars($("rp-chart-air"), "gw_airtime", { yfmt: 2, tipfmt: 3, unit: "", ytitle: "Airtime (fraction)" });
    rateBars($("rp-chart-retry"), "mpdu_retry_drop", { yfmt: 0, tipfmt: 0, unit: "", ytitle: "MPDUs per run" });
    const a8 = pair(8, "static", "olsr", "gw_airtime"), a32 = pair(32, "static", "olsr", "gw_airtime");
    const r8 = pair(8, "riskaware", "olsr", "mpdu_retry_drop"), r32 = pair(32, "riskaware", "olsr", "mpdu_retry_drop");
    const d8 = pair(8, "riskaware", "olsr", "delay_p95_ms"), d32 = pair(32, "riskaware", "olsr", "delay_p95_ms");
    const pSO8 = pair(8, "static", "olsr", "pdr_nominal_pct");
    $("rp-cong-notes").innerHTML = [
      `${tag(a8.cls)} <strong>Gateway airtime</strong> is lower with tree routing than with OLSR: Static − OLSR ${sgn(a8.diff[0], 3)} ${dci(a8.diff, 3)} at 8 kbps (${bp(8, "static").gw_airtime[0].toFixed(2)} vs ${bp(8, "olsr").gw_airtime[0].toFixed(2)}) and ${sgn(a32.diff[0], 3)} at 32 kbps, where all three protocols are near saturation (≈ 0.75–0.77). 12/12 draws; a secondary metric, so this is exploratory.`,
      `${tag(r8.cls)} <strong>MAC retry-limit drops</strong>: Risk-Aware − OLSR ${sgn(r8.diff[0], 0)} per run at 8 kbps and ${sgn(r32.diff[0], 0)} at 32 kbps, 12/12 draws (exploratory).`,
      `${tag(pair(32, "static", "olsr", "pdr_nominal_pct").cls)} <strong>The PDR advantage of tree routing over OLSR at 32 kbps</strong> (Static − OLSR ${sgn(pair(32, "static", "olsr", "pdr_nominal_pct").diff[0], 1)} pp; Risk-Aware − OLSR ${sgn(pair(32, "riskaware", "olsr", "pdr_nominal_pct").diff[0], 1)} pp) comes with this congestion difference, not with risk: at 8 kbps Static and OLSR deliver the same (${sgn(pSO8.diff[0], 2)} pp ${dci(pSO8.diff, 2)}).`,
      `${tag("descriptive")} <strong>Delay</strong>: OLSR's p95 delay is higher by ${num(-d8.diff[0], 0)} ms at 8 kbps and ${num(-d32.diff[0], 0)} ms at 32 kbps in 12/12 draws. Reported descriptively, because delay covers delivered packets only.`
    ].map(s => `<li>${s}</li>`).join("");
  }

  function renderInterpretation() {
    const st = (rate, p, m) => RP.subtree.find(x => x.rate === rate && x.protocol === p && x.metric === m);
    const head = "<thead><tr><th>Rate</th><th>Protocol</th><th>Exposure %</th><th>Nominal PDR %</th></tr></thead>";
    const body = RP.design.rates_kbps.flatMap(rate => RP.protocols.map(p => {
      const e = st(rate, p.key, "exposure_rate_pct"), d = st(rate, p.key, "pdr_nominal_pct");
      return `<tr><td>${rate} kbps</td><td>${esc(p.label)}</td><td class="num">${e.subtree.toFixed(2)} → ${e.uniform.toFixed(2)}</td><td class="num">${d.subtree.toFixed(2)} → ${d.uniform.toFixed(2)}</td></tr>`;
    })).join("");
    $("rp-subtree").innerHTML = head + "<tbody>" + body + "</tbody>";
    const s8 = st(8, "static", "exposure_rate_pct"), sp8 = st(8, "static", "pdr_nominal_pct");
    $("rp-findings").innerHTML = [
      `<strong>The earlier Static penalty came from the placement.</strong> Subtree placement puts the risky nodes on Static's backbone by construction. Placed uniformly, Static's exposure falls from ${s8.subtree.toFixed(1)} % to ${s8.uniform.toFixed(2)} %, and its 8 kbps PDR rises from ${sp8.subtree.toFixed(1)} % to ${sp8.uniform.toFixed(2)} %. OLSR barely changes.`,
      `<strong>Static vs OLSR exposure: no difference detected.</strong> This holds at both rates; the intervals exclude a gap of the subtree size, but not ±1 pp.`,
      `<strong>The earlier Risk-Aware gains over Static describe Static's worst case, not a typical placement.</strong> Both the N = 30 and the N = 100 subtree results put risk on Static's tree. With uniform placement at N = 100, Risk-Aware differs from Static only when a risky node lies on Static's tree (5 of 12 draws), and those gains are descriptive. Whether this carries over to N = 30 was not tested.`,
      `<strong>Supported here:</strong> Risk-Aware has lower exposure than OLSR, and higher PDR than OLSR, at both rates. Static also has higher PDR than OLSR at 32 kbps. All hold in 12/12 draws and in all 3 topologies. The 32 kbps PDR gap tracks gateway congestion.`
    ].map(s => `<li>${s}</li>`).join("");
    $("rp-provenance").innerHTML = `Provenance: ${esc(RP.generated_by)}; ${Object.keys(RP.sources).length} source files with sha256 in <a href="data/wifi6-randplace.json">data/wifi6-randplace.json</a>. Batch <code>${esc(RP.batch)}</code>: ${esc(RP.checks.split(": ")[1])}. Simulator binary <code>${RP.design.binary_sha256.slice(0, 8)}…</code>, unchanged. Full report: <a href="https://github.com/SalinCalyna/-iot-network-performance-ns3/blob/main/analysis/wifi6-randplace-report/SUMMARY.md" target="_blank" rel="noopener">analysis/wifi6-randplace-report/SUMMARY.md</a>.`;
  }

  async function init() {
    if (!$("view-w6-randplace")) return;
    try {
      RP = await fetch("data/wifi6-randplace.json").then(r => { if (!r.ok) throw new Error(r.status); return r.json(); });
    } catch (e) {
      console.warn("wifi6-randplace.json unavailable:", e);
      document.querySelectorAll('[id^="rp-"]').forEach(el => { if (el.textContent.trim() === "—") el.textContent = "Data file unavailable."; });
      return;
    }
    renderHead();
    const rl = RP.design.rates_kbps.map(r => `${r} kbps`);
    pills($("rp-tab-rate"), rl, 0, i => { tabRate = RP.design.rates_kbps[i]; renderTable(); });
    renderTable();
    legend($("rp-legend"), RP.protocols.map(p => [p.label, resolveColor(COLORS[p.key])]));
    rateBars($("rp-chart-pdr"), "pdr_nominal_pct", { yfmt: 0, tipfmt: 2, unit: " %", ytitle: "Nominal PDR (%)" });
    rateBars($("rp-chart-exp"), "exposure_rate_pct", { yfmt: 1, tipfmt: 2, unit: " %", ytitle: "Exposure (%)" });
    pills($("rp-draw-rate"), rl, 0, i => { drawRate = RP.design.rates_kbps[i]; renderDraws(); });
    renderDraws();
    renderCases();
    pills($("rp-pair-rate"), rl, 0, i => { pairRate = RP.design.rates_kbps[i]; renderPaired(); });
    renderPaired();
    renderCongestion();
    renderInterpretation();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
