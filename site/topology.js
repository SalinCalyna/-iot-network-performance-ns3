// Network topology visualization.
// Uses REAL per-node positions (x,y, hop distance, airtime) captured from the frozen
// research's instrumented probe runs where available (OLSR/Static, N=30/50/75/100,
// medium/high traffic, seed 20). For combinations without captured per-node data
// (AODV at any N, N=10/20, or "low" traffic), it generates an illustrative topology
// using the SAME placement algorithm the simulator uses (uniform-random in a 250x250 m
// field, seeded, gateway fixed at the field centre, 90 m nominal range) -- this
// reproduces the real generation method rather than inventing a result, and is
// labelled as illustrative whenever real captured data is not the source.

function seededRandom(seed) {
  let s = seed % 2147483647; if (s <= 0) s += 2147483646;
  return () => (s = (s * 16807) % 2147483647) / 2147483647;
}

function generateTopology(n, seed) {
  const rnd = seededRandom(seed || 20);
  const area = 250, gw = { x: area / 2, y: area / 2 };
  const nodes = [{ id: n, is_gw: 1, x: gw.x, y: gw.y, hop: 0 }];
  const pts = [];
  for (let i = 0; i < n; i++) pts.push({ x: rnd() * area, y: rnd() * area });
  // BFS hop distance over disk connectivity (range 90m), matching the simulator's method
  const all = [gw, ...pts];
  const range = 90;
  const adj = Array.from({ length: all.length }, () => []);
  for (let i = 0; i < all.length; i++) for (let j = i + 1; j < all.length; j++) {
    const dx = all[i].x - all[j].x, dy = all[i].y - all[j].y;
    if (Math.sqrt(dx * dx + dy * dy) <= range) { adj[i].push(j); adj[j].push(i); }
  }
  const hop = new Array(all.length).fill(-1); hop[0] = 0;
  const q = [0];
  while (q.length) { const u = q.shift(); for (const v of adj[u]) if (hop[v] < 0) { hop[v] = hop[u] + 1; q.push(v); } }
  const out = [{ id: 0, is_gw: 1, x: gw.x, y: gw.y, hop: 0 }];
  pts.forEach((p, i) => out.push({ id: i + 1, is_gw: 0, x: p.x, y: p.y, hop: hop[i + 1] }));
  return out;
}

const HOP_COLORS = ["#4da3ff", "#3ecf8e", "#f0a94e", "#ef5f6f", "#a78bfa"];
function hopColor(h) { if (h < 0) return "#4b5768"; return HOP_COLORS[Math.min(h, HOP_COLORS.length - 1)]; }

function renderTopology(container, nodes, opts) {
  container.innerHTML = "";
  const W = 400, H = 400, area = 250, pad = 24;
  const scale = (W - pad * 2) / area;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  const px = v => pad + v * scale;

  // range rings around gateway (illustrative of 1/2/3-hop reach)
  const gwNode = nodes.find(n => n.is_gw);
  if (gwNode) {
    [90, 180, 270].forEach((r, i) => {
      const ring = document.createElementNS(svg.namespaceURI, "circle");
      ring.setAttribute("cx", px(gwNode.x)); ring.setAttribute("cy", px(gwNode.y));
      ring.setAttribute("r", r * scale); ring.setAttribute("fill", "none");
      ring.setAttribute("stroke", i === 0 ? "rgba(240,169,78,.35)" : "rgba(255,255,255,.06)");
      ring.setAttribute("stroke-width", i === 0 ? 1.4 : 1);
      ring.setAttribute("stroke-dasharray", "3 4");
      svg.appendChild(ring);
    });
  }

  // edges: connect each node to its nearest lower-hop neighbour within range (visual only)
  const range = 90 * scale;
  for (let i = 0; i < nodes.length; i++) {
    const a = nodes[i]; if (a.is_gw) continue;
    let best = null, bestD = Infinity;
    for (let j = 0; j < nodes.length; j++) {
      const b = nodes[j]; if (i === j) continue;
      if (b.hop !== a.hop - 1) continue;
      const dx = px(a.x) - px(b.x), dy = px(a.y) - px(b.y), d = Math.hypot(dx, dy);
      if (d < range * 1.4 && d < bestD) { bestD = d; best = b; }
    }
    if (best) {
      const line = document.createElementNS(svg.namespaceURI, "line");
      line.setAttribute("x1", px(a.x)); line.setAttribute("y1", px(a.y));
      line.setAttribute("x2", px(best.x)); line.setAttribute("y2", px(best.y));
      const congested = opts.congestionLevel > 0.75 && a.hop <= 1;
      line.setAttribute("stroke", congested ? "rgba(239,95,111,.55)" : "rgba(77,163,255,.28)");
      line.setAttribute("stroke-width", congested ? 1.6 : 1);
      svg.appendChild(line);
    }
  }

  // nodes
  nodes.forEach(nd => {
    const c = document.createElementNS(svg.namespaceURI, "circle");
    c.setAttribute("cx", px(nd.x)); c.setAttribute("cy", px(nd.y));
    c.setAttribute("r", nd.is_gw ? 8 : 4.2);
    c.setAttribute("fill", nd.is_gw ? "#fff" : hopColor(nd.hop));
    c.setAttribute("stroke", nd.is_gw ? "var(--accent)" : "#0d1117");
    c.setAttribute("stroke-width", nd.is_gw ? 2.5 : 1);
    if (nd.is_gw) {
      const pulse = document.createElementNS(svg.namespaceURI, "circle");
      pulse.setAttribute("cx", px(nd.x)); pulse.setAttribute("cy", px(nd.y)); pulse.setAttribute("r", 8);
      pulse.setAttribute("fill", "none"); pulse.setAttribute("stroke", "var(--accent)"); pulse.setAttribute("stroke-width", 1.5);
      pulse.innerHTML = `<animate attributeName="r" from="8" to="22" dur="2s" repeatCount="indefinite"/><animate attributeName="opacity" from="0.6" to="0" dur="2s" repeatCount="indefinite"/>`;
      svg.appendChild(pulse);
    }
    svg.appendChild(c);
  });
  container.appendChild(svg);
}
