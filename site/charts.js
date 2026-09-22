// Lightweight SVG chart primitives with hover tooltips. No external dependency
// (kept self-contained for GitHub Pages reliability). All charts are pure functions
// of (container, series, opts) -> appends an <svg>+tooltip to container.

const NS = "http://www.w3.org/2000/svg";
function el(tag, attrs) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  return e;
}
function fmt(v, digits) { return typeof v === "number" ? v.toFixed(digits == null ? 1 : digits) : v; }

// Resolve a "var(--name)" color reference to its computed value. SVG presentation
// attributes (plain fill="..."/stroke="..." rather than a CSS class or style=)
// are not reliably re-evaluated for custom-property substitution in every
// rendering context, which previously left bars/lines/points invisible while
// CSS-class-driven axis text and gridlines still rendered. Resolving to a
// concrete color here removes that dependency entirely. Non-var() values and
// already-resolved colors pass through unchanged.
function resolveColor(v) {
  if (typeof v !== "string") return v;
  const m = v.match(/^var\((--[a-zA-Z0-9-]+)\)$/);
  if (!m) return v;
  const resolved = getComputedStyle(document.documentElement).getPropertyValue(m[1]).trim();
  return resolved || v;
}

function ensureTooltip(container) {
  let tip = container.querySelector(".tooltip");
  if (!tip) {
    tip = document.createElement("div");
    tip.className = "tooltip";
    container.style.position = "relative";
    container.appendChild(tip);
  }
  return tip;
}

function showTip(container, tip, x, y, html) {
  tip.innerHTML = html;
  tip.style.left = Math.min(x + 12, container.clientWidth - 160) + "px";
  tip.style.top = Math.max(y - 10, 0) + "px";
  tip.style.opacity = 1;
}
function hideTip(tip) { tip.style.opacity = 0; }

// ---------------------------------------------------------------- 95% CI helpers
// A data point may carry {ci, n, nTotal, excludedSeeds}: ci is the two-sided 95% CI HALF-WIDTH
// (Student t, computed in experiments/build_v3_site_stats.py) around the mean y.  Points without
// `ci` render exactly as before -- a missing interval is never drawn as zero-width.
function toRgba(color, alpha) {
  const c = resolveColor(color);
  let m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(c);
  if (m) {
    let h = m[1]; if (h.length === 3) h = h.split("").map(x => x + x).join("");
    return `rgba(${parseInt(h.slice(0, 2), 16)},${parseInt(h.slice(2, 4), 16)},${parseInt(h.slice(4, 6), 16)},${alpha})`;
  }
  m = /^rgba?\((\d+)[ ,]+(\d+)[ ,]+(\d+)/.exec(c);
  return m ? `rgba(${m[1]},${m[2]},${m[3]},${alpha})` : c;
}
const hasCi = d => d && typeof d.ci === "number" && isFinite(d.ci);
// Displayed interval. The physical lower bound (default 0: every plotted metric is non-negative) clamps only the
// DRAWN lower limit; mean, CI half-width and upper limit are never altered and the raw limit is disclosed in the tooltip.
function ciLimits(d, opts) {
  if (!hasCi(d)) return null;
  const bound = opts.lowerBound === undefined ? 0 : opts.lowerBound;
  const rawLo = d.y - d.ci, hi = d.y + d.ci;
  const lo = bound == null ? rawLo : Math.max(bound, rawLo);
  return { lo, hi, rawLo, clamped: bound != null && rawLo < bound };
}
function pointTipHtml(title, seriesName, d, opts) {
  const tf = opts.tipfmt != null ? opts.tipfmt : Math.max(opts.yfmt || 0, 2), u = opts.unit || "";
  let h = `<div class="t-title">${title}</div><div class="t-row"><span>${seriesName}</span><span></span></div>`;
  h += `<div class="t-row"><span>Mean</span><span>${fmt(d.y, tf)}${u}</span></div>`;
  const L = ciLimits(d, opts);
  if (L) {
    h += `<div class="t-row"><span>95% CI</span><span>${fmt(L.lo, tf)} – ${fmt(L.hi, tf)}${u}</span></div>`;
    if (L.clamped) h += `<div class="t-note">Raw lower limit ${fmt(L.rawLo, tf)}${u}; drawn at 0 (physical lower bound). Mean and CI unchanged.</div>`;
  } else if (d.n != null && d.n < 2) {
    h += `<div class="t-row"><span>95% CI</span><span>n/a (n = ${d.n})</span></div>`;
  }
  if (d.n != null) {
    const of = d.nTotal != null && d.n < d.nTotal ? ` of ${d.nTotal}` : "";
    h += `<div class="t-row"><span>n</span><span>${d.n}${of}</span></div>`;
    if (d.nTotal != null && d.n < d.nTotal) {
      const k = d.nTotal - d.n;
      h += `<div class="t-note">${k} ${k === 1 ? "seed" : "seeds"} excluded: undefined because no packets were received (in at least one of ${k === 1 ? "its" : "their"} runs). Not counted as 0.</div>`;
    }
  }
  return h;
}
function ciYMax(names, series, opts) {
  const tops = names.flatMap(n => series[n].map(d => (ciLimits(d, opts) ? ciLimits(d, opts).hi : d.y)));
  return Math.max(...tops) * 1.12 || 1;
}

// ---------------------------------------------------------------- grouped bars (optional Mean +/- 95% CI whiskers)
function groupedBar(container, series, opts) {
  container.innerHTML = "";
  const tip = ensureTooltip(container);
  const W = opts.width || 520, H = opts.height || 240, pad = { l: 40, r: 10, t: 10, b: 28 };
  const names = Object.keys(series);
  const xs = series[names[0]].map(d => d.x);
  const anyCi = names.some(n => series[n].some(hasCi));
  const yMax = anyCi ? ciYMax(names, series, opts) : (Math.max(...names.flatMap(n => series[n].map(d => d.y))) * 1.15 || 1);
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart" });
  const plotW = W - pad.l - pad.r, plotH = H - pad.t - pad.b;
  const groupW = plotW / xs.length;
  const barW = (groupW * 0.72) / names.length;
  const yScale = v => pad.t + plotH - (v / yMax) * plotH;
  for (let i = 0; i <= 4; i++) {
    const y = pad.t + plotH - (i / 4) * plotH;
    svg.appendChild(el("line", { x1: pad.l, x2: W - pad.r, y1: y, y2: y, class: "gridline" }));
    const t = el("text", { x: 2, y: y + 3 }); t.textContent = fmt(yMax * i / 4, opts.yfmt); svg.appendChild(t);
  }
  xs.forEach((x, xi) => {
    names.forEach((n, ni) => {
      const d = series[n][xi];
      const h = (d.y / yMax) * plotH;
      const bx = pad.l + xi * groupW + groupW * 0.14 + ni * barW;
      const by = pad.t + plotH - h;
      const rect = el("rect", { x: bx, y: by, width: barW * 0.82, height: Math.max(h, 1), fill: resolveColor(opts.colors[n]), rx: 2 });
      const title = opts.xlabel ? opts.xlabel(x) : x;
      const onMove = ev => {
        const r = container.getBoundingClientRect();
        showTip(container, tip, ev.clientX - r.left, ev.clientY - r.top,
          hasCi(d) || d.n != null ? pointTipHtml(title, n.toUpperCase(), d, opts)
            : `<div class="t-title">${title}</div><div class="t-row"><span>${n.toUpperCase()}</span><span>${fmt(d.y, opts.yfmt)}${opts.unit || ""}</span></div>`);
      };
      rect.addEventListener("mousemove", onMove);
      rect.addEventListener("mouseleave", () => hideTip(tip));
      svg.appendChild(rect);
      const L = ciLimits(d, opts);
      if (L) {   // whisker: mean +/- 95% CI half-width (never SD)
        const cx = bx + (barW * 0.82) / 2, cap = Math.min(barW * 0.3, 5);
        const g = el("g", { class: "ci-whisker", stroke: resolveColor("var(--text)"), "stroke-width": 1.4, "stroke-linecap": "round", opacity: 0.85 });
        g.appendChild(el("line", { x1: cx, x2: cx, y1: yScale(L.lo), y2: yScale(L.hi) }));
        g.appendChild(el("line", { x1: cx - cap, x2: cx + cap, y1: yScale(L.hi), y2: yScale(L.hi) }));
        if (!L.clamped) g.appendChild(el("line", { x1: cx - cap, x2: cx + cap, y1: yScale(L.lo), y2: yScale(L.lo) }));
        g.addEventListener("mousemove", onMove); g.addEventListener("mouseleave", () => hideTip(tip));
        svg.appendChild(g);
      }
    });
    const t = el("text", { x: pad.l + xi * groupW + groupW / 2, y: H - 8, "text-anchor": "middle" });
    t.textContent = opts.xlabel ? opts.xlabel(x) : x; svg.appendChild(t);
  });
  container.appendChild(svg);
}

// ---------------------------------------------------------------- line chart (optional shaded 95% CI band)
function lineChart(container, series, opts) {
  container.innerHTML = "";
  const tip = ensureTooltip(container);
  const W = opts.width || 520, H = opts.height || 240, pad = { l: 40, r: 14, t: 10, b: 28 };
  const names = Object.keys(series);
  const xs = series[names[0]].map(d => d.x);
  const anyCi = names.some(n => series[n].some(hasCi));
  const allY = names.flatMap(n => series[n].map(d => d.y));
  const yMax = anyCi ? ciYMax(names, series, opts) : (Math.max(...allY) * 1.15 || 1);
  const yMin = opts.yMinZero === false ? Math.min(...allY) * 0.9 : 0;
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart" });
  const plotW = W - pad.l - pad.r, plotH = H - pad.t - pad.b;
  const xScale = i => pad.l + (xs.length === 1 ? plotW / 2 : (i / (xs.length - 1)) * plotW);
  const yScale = v => pad.t + plotH - ((v - yMin) / (yMax - yMin || 1)) * plotH;
  for (let i = 0; i <= 4; i++) {
    const y = pad.t + plotH - (i / 4) * plotH;
    svg.appendChild(el("line", { x1: pad.l, x2: W - pad.r, y1: y, y2: y, class: "gridline" }));
    const t = el("text", { x: 2, y: y + 3 }); t.textContent = fmt(yMin + (yMax - yMin) * i / 4, opts.yfmt); svg.appendChild(t);
  }
  xs.forEach((x, i) => { const t = el("text", { x: xScale(i), y: H - 8, "text-anchor": "middle" }); t.textContent = x; svg.appendChild(t); });
  // bands first (under every line), one closed polygon per series over its contiguous points that have a CI
  names.forEach(n => {
    const col = opts.colors[n];
    let run = [];
    const flush = () => {
      if (run.length > 1) {
        const up = run.map(r => `${xScale(r.i)},${yScale(r.L.hi)}`);
        const lo = run.slice().reverse().map(r => `${xScale(r.i)},${yScale(r.L.lo)}`);
        svg.appendChild(el("polygon", { points: up.concat(lo).join(" "), fill: toRgba(col, 0.16), stroke: "none", class: "ci-band" }));
      }
      run = [];
    };
    series[n].forEach((d, i) => { const L = ciLimits(d, opts); if (L) run.push({ i, L }); else flush(); });
    flush();
  });
  names.forEach(n => {
    const pts = series[n].map((d, i) => `${xScale(i)},${yScale(d.y)}`).join(" ");
    svg.appendChild(el("polyline", { points: pts, fill: "none", stroke: resolveColor(opts.colors[n]), "stroke-width": 2.5 }));
    series[n].forEach((d, i) => {
      const c = el("circle", { cx: xScale(i), cy: yScale(d.y), r: 4, fill: resolveColor(opts.colors[n]), stroke: resolveColor("var(--panel)"), "stroke-width": 1.5 });
      c.addEventListener("mousemove", ev => {
        const r = container.getBoundingClientRect();
        showTip(container, tip, ev.clientX - r.left, ev.clientY - r.top,
          hasCi(d) || d.n != null ? pointTipHtml(`${n.toUpperCase()} @ ${d.x}`, "", d, opts)
            : `<div class="t-title">${n} @ ${d.x}</div><div class="t-row"><span>value</span><span>${fmt(d.y, opts.yfmt)}${opts.unit || ""}</span></div>`);
      });
      c.addEventListener("mouseleave", () => hideTip(tip));
      svg.appendChild(c);
    });
  });
  container.appendChild(svg);
}

// Caption under a CI chart: what the band / whiskers are, and the per-chart undefined-metric disclosure.
function ciCaption(container, kind, extraHtml) {
  let cap = container.parentNode.querySelector(":scope > .ci-caption");
  if (!cap) { cap = document.createElement("div"); cap.className = "ci-caption"; container.insertAdjacentElement("afterend", cap); }
  const what = kind === "band" ? `<span class="ci-key band"></span>shaded band = 95% CI of the mean`
                               : `<span class="ci-key whisker"></span>whiskers = mean ± 95% CI`;
  cap.innerHTML = `${what} · Student t, n = 11 seeds, df = 10${extraHtml ? `<div class="ci-caption-extra">${extraHtml}</div>` : ""}`;
}

// ---------------------------------------------------------------- horizontal stacked comparison (two-value bar)
function twoBar(container, a, b, opts) {
  container.innerHTML = "";
  const W = opts.width || 320, H = opts.height || 90;
  const max = Math.max(a.value, b.value) * 1.1 || 1;
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart" });
  const barH = 22, gap = 14, labelW = 74;
  [a, b].forEach((d, i) => {
    const y = i * (barH + gap) + 6;
    const t = el("text", { x: 0, y: y + barH / 2 + 3, "font-size": 11, fill: resolveColor("var(--text-dim)") }); t.textContent = d.label; svg.appendChild(t);
    svg.appendChild(el("rect", { x: labelW, y, width: W - labelW - 46, height: barH, rx: 4, fill: resolveColor("var(--panel-2)") }));
    const w = ((W - labelW - 46) * d.value) / max;
    svg.appendChild(el("rect", { x: labelW, y, width: Math.max(w, 2), height: barH, rx: 4, fill: resolveColor(d.color) }));
    const vt = el("text", { x: W - 4, y: y + barH / 2 + 3, "text-anchor": "end", "font-size": 11, fill: resolveColor("var(--text)"), "font-weight": 700 });
    vt.textContent = fmt(d.value, opts.yfmt) + (opts.unit || ""); svg.appendChild(vt);
  });
  container.appendChild(svg);
}

function legend(container, entries) {
  const div = document.createElement("div"); div.className = "legend";
  entries.forEach(([label, color, shape]) => {
    const span = document.createElement("span"); span.className = "item";
    span.innerHTML = `<span class="${shape === "dot" ? "dotc" : "sw"}" style="background:${color}"></span>${label}`;
    div.appendChild(span);
  });
  container.appendChild(div);
}

function healthBar(container, label, valuePct, displayVal, statusFn) {
  const status = statusFn(valuePct);
  const colors = { normal: "var(--ok)", degraded: "var(--warn)", congested: "#f5b869", critical: "var(--bad)" };
  const row = document.createElement("div"); row.className = "health-row";
  row.innerHTML = `
    <div class="health-label">${label}</div>
    <div class="health-bar"><div class="fill" style="width:${Math.min(valuePct,100)}%;background:${colors[status]}"></div></div>
    <div class="health-val">${displayVal}</div>
    <div class="status-pill ${status}">${status}</div>`;
  container.appendChild(row);
}
