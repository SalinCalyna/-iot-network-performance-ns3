// Network topology visualization.
// Uses REAL per-node positions (x,y, hop distance, airtime) captured from the frozen
// research's instrumented probe runs where available (OLSR/Static, N=30/50/75/100,
// medium/high traffic, mobility=static, seed 20). For combinations without captured
// per-node data (AODV or Sigmoid at any N, any mobility other than static, any seed
// other than 20, or N=10/20, or "low" traffic), it generates an illustrative topology
// using the SAME placement algorithm the simulator uses (uniform-random in a 250x250 m
// field, seeded, gateway fixed at the field centre, 90 m nominal range) -- this
// reproduces the real generation method rather than inventing a result, and is
// labelled as illustrative/conceptual whenever real captured data is not the source.

function seededRandom(seed) {
  let s = seed % 2147483647; if (s <= 0) s += 2147483646;
  return () => (s = (s * 16807) % 2147483647) / 2147483647;
}

function generateTopology(n, seed) {
  const rnd = seededRandom(seed || 20);
  const area = 250, gw = { x: area / 2, y: area / 2 };
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

// Nearest-neighbour-at-hop-minus-1 heuristic, shared by edge drawing and path building
// so the animated route always highlights an edge that is actually drawn.
function findParent(node, nodes) {
  if (node.is_gw || node.hop <= 0) return null;
  let best = null, bestD = Infinity;
  for (const b of nodes) {
    if (b === node || b.hop !== node.hop - 1) continue;
    const dx = node.x - b.x, dy = node.y - b.y, d = Math.hypot(dx, dy);
    if (d < 90 * 1.4 && d < bestD) { bestD = d; best = b; }
  }
  return best;
}

// Builds an illustrative hop-by-hop path from the farthest reachable sensor back to the
// gateway, using the same neighbour heuristic as the rendered edges. Returns an array of
// nodes ordered [source, ..., gateway]. This is a topology-visualization aid only -- it is
// NOT a packet-level route trace and must always be presented as illustrative.
function buildHopPath(nodes) {
  const reachable = nodes.filter(n => !n.is_gw && n.hop >= 0);
  if (!reachable.length) return [];
  const maxHop = Math.max(...reachable.map(n => n.hop));
  const source = reachable.find(n => n.hop === maxHop) || reachable[0];
  const path = [source];
  let cur = source;
  let guard = 0;
  while (cur && !cur.is_gw && guard++ < 50) {
    const parent = findParent(cur, nodes);
    if (!parent) break;
    path.push(parent);
    cur = parent;
  }
  return path;
}

function renderTopology(container, nodes, opts) {
  opts = opts || {};
  container.innerHTML = "";
  const W = 400, H = 400, area = 250, pad = 24;
  const scale = (W - pad * 2) / area;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  const px = v => pad + v * scale;

  const pathIds = new Set((opts.highlightPath || []).map(n => n.id));
  const pathEdgeKey = (a, b) => a.id < b.id ? a.id + "_" + b.id : b.id + "_" + a.id;
  const pathEdges = new Set();
  (opts.highlightPath || []).forEach((n, i, arr) => { if (i > 0) pathEdges.add(pathEdgeKey(n, arr[i - 1])); });

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
    const best = findParent(a, nodes);
    if (best) {
      const line = document.createElementNS(svg.namespaceURI, "line");
      line.setAttribute("x1", px(a.x)); line.setAttribute("y1", px(a.y));
      line.setAttribute("x2", px(best.x)); line.setAttribute("y2", px(best.y));
      const onPath = pathEdges.has(pathEdgeKey(a, best));
      const congested = opts.congestionLevel > 0.75 && a.hop <= 1;
      line.setAttribute("stroke", onPath ? "#3ecf8e" : (congested ? "rgba(239,95,111,.55)" : "rgba(77,163,255,.28)"));
      line.setAttribute("stroke-width", onPath ? 2.6 : (congested ? 1.6 : 1));
      svg.appendChild(line);
    }
  }

  // nodes
  nodes.forEach(nd => {
    const c = document.createElementNS(svg.namespaceURI, "circle");
    c.setAttribute("cx", px(nd.x)); c.setAttribute("cy", px(nd.y));
    const onPath = pathIds.has(nd.id);
    c.setAttribute("r", nd.is_gw ? 8 : (onPath ? 5.6 : 4.2));
    c.setAttribute("fill", nd.is_gw ? "#fff" : hopColor(nd.hop));
    c.setAttribute("stroke", nd.is_gw ? resolveColor("var(--accent)") : (onPath ? "#3ecf8e" : "#1a2332"));
    c.setAttribute("stroke-width", nd.is_gw ? 2.5 : (onPath ? 2 : 1));
    if (nd.is_gw) {
      const pulse = document.createElementNS(svg.namespaceURI, "circle");
      pulse.setAttribute("cx", px(nd.x)); pulse.setAttribute("cy", px(nd.y)); pulse.setAttribute("r", 8);
      pulse.setAttribute("fill", "none"); pulse.setAttribute("stroke", resolveColor("var(--accent)")); pulse.setAttribute("stroke-width", 1.5);
      pulse.innerHTML = `<animate attributeName="r" from="8" to="22" dur="2s" repeatCount="indefinite"/><animate attributeName="opacity" from="0.6" to="0" dur="2s" repeatCount="indefinite"/>`;
      svg.appendChild(pulse);
    }
    svg.appendChild(c);
  });

  // moving traversal marker: opts.markerStep is a float index into opts.highlightPath
  // (source=0 .. gateway=path.length-1); interpolates smoothly between the two endpoints.
  if (opts.highlightPath && opts.highlightPath.length > 1 && typeof opts.markerStep === "number" && opts.markerStep >= 0) {
    const path = opts.highlightPath;
    const clamped = Math.max(0, Math.min(opts.markerStep, path.length - 1));
    const i0 = Math.floor(clamped), i1 = Math.min(i0 + 1, path.length - 1), frac = clamped - i0;
    const a = path[i0], b = path[i1];
    const mx = px(a.x) + (px(b.x) - px(a.x)) * frac;
    const my = px(a.y) + (px(b.y) - px(a.y)) * frac;
    const marker = document.createElementNS(svg.namespaceURI, "circle");
    marker.setAttribute("cx", mx); marker.setAttribute("cy", my); marker.setAttribute("r", 4.5);
    marker.setAttribute("fill", "#ffd43b"); marker.setAttribute("stroke", "#1a2332"); marker.setAttribute("stroke-width", 1.2);
    marker.setAttribute("class", "rw-traversal-marker");
    svg.appendChild(marker);
  }

  container.appendChild(svg);
}
