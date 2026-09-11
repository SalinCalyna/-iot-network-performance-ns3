// Final research dashboard -- renders analysis/final-report-data figures as lightweight inline SVG.
// No external chart library dependency (kept self-contained for GitHub Pages reliability).

const COLORS = { olsr: "#5fb3ff", static: "#7ee8b8", aodv: "#f2b84b", v4: "#c792ea" };

function svg(tag, attrs) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const k in attrs) el.setAttribute(k, attrs[k]);
  return el;
}

function groupedBarChart(container, series, opts) {
  // series: {name: [{x, y}, ...]}
  const W = opts.width || 480, H = opts.height || 260, pad = { l: 42, r: 12, t: 14, b: 34 };
  const names = Object.keys(series);
  const xs = series[names[0]].map(d => d.x);
  const yMax = Math.max(...names.flatMap(n => series[n].map(d => d.y))) * 1.12;
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, width: "100%", height: H });
  const plotW = W - pad.l - pad.r, plotH = H - pad.t - pad.b;
  const groupW = plotW / xs.length;
  const barW = (groupW * 0.7) / names.length;
  // axes
  for (let i = 0; i <= 4; i++) {
    const y = pad.t + plotH - (i / 4) * plotH;
    s.appendChild(svg("line", { x1: pad.l, x2: W - pad.r, y1: y, y2: y, stroke: "#232d3b", "stroke-width": 1 }));
    const t = svg("text", { x: 4, y: y + 3 }); t.textContent = (yMax * i / 4).toFixed(opts.yfmt || 0); s.appendChild(t);
  }
  xs.forEach((x, xi) => {
    names.forEach((n, ni) => {
      const d = series[n][xi];
      const h = (d.y / yMax) * plotH;
      const bx = pad.l + xi * groupW + groupW * 0.15 + ni * barW;
      const by = pad.t + plotH - h;
      s.appendChild(svg("rect", { x: bx, y: by, width: barW * 0.85, height: h, fill: opts.colors[n] }));
    });
    const t = svg("text", { x: pad.l + xi * groupW + groupW / 2, y: H - 10, "text-anchor": "middle" });
    t.textContent = opts.xlabel ? opts.xlabel(x) : x; s.appendChild(t);
  });
  container.appendChild(s);
}

function lineChart(container, series, opts) {
  const W = opts.width || 480, H = opts.height || 260, pad = { l: 42, r: 12, t: 14, b: 34 };
  const names = Object.keys(series);
  const xs = series[names[0]].map(d => d.x);
  const yMax = Math.max(...names.flatMap(n => series[n].map(d => d.y))) * 1.12;
  const yMin = Math.min(0, Math.min(...names.flatMap(n => series[n].map(d => d.y))));
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, width: "100%", height: H });
  const plotW = W - pad.l - pad.r, plotH = H - pad.t - pad.b;
  const xScale = i => pad.l + (i / (xs.length - 1)) * plotW;
  const yScale = v => pad.t + plotH - ((v - yMin) / (yMax - yMin)) * plotH;
  for (let i = 0; i <= 4; i++) {
    const y = pad.t + plotH - (i / 4) * plotH;
    s.appendChild(svg("line", { x1: pad.l, x2: W - pad.r, y1: y, y2: y, stroke: "#232d3b", "stroke-width": 1 }));
    const t = svg("text", { x: 4, y: y + 3 }); t.textContent = (yMin + (yMax - yMin) * i / 4).toFixed(opts.yfmt || 0); s.appendChild(t);
  }
  xs.forEach((x, i) => { const t = svg("text", { x: xScale(i), y: H - 10, "text-anchor": "middle" }); t.textContent = x; s.appendChild(t); });
  names.forEach(n => {
    const pts = series[n].map((d, i) => `${xScale(i)},${yScale(d.y)}`).join(" ");
    s.appendChild(svg("polyline", { points: pts, class: "line", stroke: opts.colors[n] }));
    series[n].forEach((d, i) => s.appendChild(svg("circle", { cx: xScale(i), cy: yScale(d.y), r: 3.5, fill: opts.colors[n] })));
  });
  container.appendChild(s);
}

function legend(container, entries) {
  const div = document.createElement("div"); div.className = "legend";
  entries.forEach(([label, color]) => {
    const span = document.createElement("span");
    span.innerHTML = `<span class="dot" style="background:${color}"></span>${label}`;
    div.appendChild(span);
  });
  container.appendChild(div);
}

async function main() {
  const data = await fetch("data/final_research.json").then(r => r.json());

  // Stat cards
  const stats = data.stats;
  document.getElementById("stat-v3").textContent = stats.v3_runs.toLocaleString();
  document.getElementById("stat-v4").textContent = stats.v4_matched.toLocaleString();
  document.getElementById("stat-bottleneck").textContent = stats.bottleneck_runs.toLocaleString();
  document.getElementById("stat-repro").textContent = `${stats.repro_pass}/${stats.repro_total - stats.repro_na}`;

  // Fig 1: PDR vs node count
  const fig1 = document.getElementById("fig1");
  legend(fig1, [["AODV", COLORS.aodv], ["OLSR", COLORS.olsr], ["Static", COLORS.static]]);
  groupedBarChart(fig1, {
    aodv: data.baseline_pdr.aodv.map(d => ({ x: d.n, y: d.pdr })),
    olsr: data.baseline_pdr.olsr.map(d => ({ x: d.n, y: d.pdr })),
    static: data.baseline_pdr.static.map(d => ({ x: d.n, y: d.pdr }))
  }, { colors: COLORS, xlabel: x => `N=${x}` });

  // Fig 2: gateway airtime vs N (OLSR/Static, high traffic)
  const fig2 = document.getElementById("fig2");
  legend(fig2, [["OLSR / high", COLORS.olsr], ["Static / high", COLORS.static]]);
  groupedBarChart(fig2, {
    olsr: data.bottleneck_airtime["olsr-high"].map(d => ({ x: d.n, y: d.gw_airtime })),
    static: data.bottleneck_airtime["static-high"].map(d => ({ x: d.n, y: d.gw_airtime }))
  }, { colors: COLORS, yfmt: 2, xlabel: x => `N=${x}` });

  // Fig 5: OLSR PDR vs offered rate (N=50/75/100)
  const fig5 = document.getElementById("fig5");
  legend(fig5, [["N=50", "#9fd3ff"], ["N=75", COLORS.olsr], ["N=100", "#2f6fb0"]]);
  lineChart(fig5, {
    "N=50": data.olsr_pdr_vs_rate["50"].map(d => ({ x: `${d.rate}k`, y: d.pdr })),
    "N=75": data.olsr_pdr_vs_rate["75"].map(d => ({ x: `${d.rate}k`, y: d.pdr })),
    "N=100": data.olsr_pdr_vs_rate["100"].map(d => ({ x: `${d.rate}k`, y: d.pdr }))
  }, { colors: { "N=50": "#9fd3ff", "N=75": COLORS.olsr, "N=100": "#2f6fb0" } });

  // Fig 6: OLSR gateway airtime vs offered rate
  const fig6 = document.getElementById("fig6");
  legend(fig6, [["N=75", COLORS.olsr], ["N=100", "#2f6fb0"]]);
  lineChart(fig6, {
    "N=75": data.olsr_airtime_vs_rate["75"].map(d => ({ x: `${d.rate}k`, y: d.airtime })),
    "N=100": data.olsr_airtime_vs_rate["100"].map(d => ({ x: `${d.rate}k`, y: d.airtime }))
  }, { colors: { "N=75": COLORS.olsr, "N=100": "#2f6fb0" }, yfmt: 2 });

  // Fig 7: Static N=50 PDR vs rate
  const fig7 = document.getElementById("fig7");
  legend(fig7, [["Static N=50", COLORS.static]]);
  lineChart(fig7, { "Static N=50": data.static_n50_pdr_vs_rate.map(d => ({ x: `${d.rate}k`, y: d.pdr })) },
    { colors: { "Static N=50": COLORS.static } });

  // Retry table
  const retryTbl = document.getElementById("retry-table-body");
  data.retry.forEach(r => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${r.protocol.toUpperCase()}</td><td>${r.n}</td><td>${r.traffic}</td><td>${r.retry_pct.toFixed(2)}%</td><td>${r.macq_pct.toFixed(2)}%</td>`;
    retryTbl.appendChild(tr);
  });

  // V4 Tier-1 table
  const v4Tbl = document.getElementById("v4-table-body");
  data.v4_tier1.forEach(r => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${r.condition}</td><td>${r.route_change_pct}</td><td>${r.activated}</td><td>${r.pdr_v4.toFixed(2)}%</td><td>${r.pdr_static.toFixed(2)}%</td>`;
    v4Tbl.appendChild(tr);
  });

  // Static N=50 diagnostic table
  const diagTbl = document.getElementById("diag-table-body");
  data.static_n50_residual.forEach(r => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${r.rate} kbps</td><td>${r.seed}</td><td>${r.attributable_pct.toFixed(2)}%</td><td>${r.residual_pct.toFixed(2)}%</td>`;
    diagTbl.appendChild(tr);
  });
}

document.addEventListener("DOMContentLoaded", main);
