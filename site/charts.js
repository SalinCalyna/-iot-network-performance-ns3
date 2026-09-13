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

// ---------------------------------------------------------------- grouped bars
function groupedBar(container, series, opts) {
  container.innerHTML = "";
  const tip = ensureTooltip(container);
  const W = opts.width || 520, H = opts.height || 240, pad = { l: 40, r: 10, t: 10, b: 28 };
  const names = Object.keys(series);
  const xs = series[names[0]].map(d => d.x);
  const allY = names.flatMap(n => series[n].map(d => d.y));
  const yMax = Math.max(...allY) * 1.15 || 1;
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart" });
  const plotW = W - pad.l - pad.r, plotH = H - pad.t - pad.b;
  const groupW = plotW / xs.length;
  const barW = (groupW * 0.72) / names.length;
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
      rect.addEventListener("mousemove", ev => {
        const r = container.getBoundingClientRect();
        showTip(container, tip, ev.clientX - r.left, ev.clientY - r.top,
          `<div class="t-title">${opts.xlabel ? opts.xlabel(x) : x}</div><div class="t-row"><span>${n.toUpperCase()}</span><span>${fmt(d.y, opts.yfmt)}${opts.unit || ""}</span></div>`);
      });
      rect.addEventListener("mouseleave", () => hideTip(tip));
      svg.appendChild(rect);
    });
    const t = el("text", { x: pad.l + xi * groupW + groupW / 2, y: H - 8, "text-anchor": "middle" });
    t.textContent = opts.xlabel ? opts.xlabel(x) : x; svg.appendChild(t);
  });
  container.appendChild(svg);
}

// ---------------------------------------------------------------- line chart
function lineChart(container, series, opts) {
  container.innerHTML = "";
  const tip = ensureTooltip(container);
  const W = opts.width || 520, H = opts.height || 240, pad = { l: 40, r: 14, t: 10, b: 28 };
  const names = Object.keys(series);
  const xs = series[names[0]].map(d => d.x);
  const allY = names.flatMap(n => series[n].map(d => d.y));
  const yMax = Math.max(...allY) * 1.15 || 1;
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
  names.forEach(n => {
    const pts = series[n].map((d, i) => `${xScale(i)},${yScale(d.y)}`).join(" ");
    svg.appendChild(el("polyline", { points: pts, fill: "none", stroke: resolveColor(opts.colors[n]), "stroke-width": 2.5 }));
    series[n].forEach((d, i) => {
      const c = el("circle", { cx: xScale(i), cy: yScale(d.y), r: 4, fill: resolveColor(opts.colors[n]), stroke: "#0d1117", "stroke-width": 1.5 });
      c.addEventListener("mousemove", ev => {
        const r = container.getBoundingClientRect();
        showTip(container, tip, ev.clientX - r.left, ev.clientY - r.top,
          `<div class="t-title">${n} @ ${d.x}</div><div class="t-row"><span>value</span><span>${fmt(d.y, opts.yfmt)}${opts.unit || ""}</span></div>`);
      });
      c.addEventListener("mouseleave", () => hideTip(tip));
      svg.appendChild(c);
    });
  });
  container.appendChild(svg);
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
