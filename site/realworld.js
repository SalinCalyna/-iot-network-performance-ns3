// Real-World IoT Application Simulation section.
// Renders an embedded Leaflet/OpenStreetMap view of Phuket, Thailand (real-world
// geographic context only) alongside a mini NS-3 topology abstraction, using
// analysis-sourced simulation data on one side and dashboard/data/phuket-locations.json
// (kept deliberately separate from simulation metrics) on the other.
//
// IMPORTANT: this section is a CONCEPTUAL APPLICATION SCENARIO. Only one coordinate
// (the campus anchor) is sourced from the existing repository; every other marker is an
// explicit placeholder pending researcher confirmation -- see phuket-locations.json.

let RW_MAP = null;
let RW_LOCATIONS = null;
let RW_STUDY_ON = false;

const MARKER_COLOR = {
  "real-world-context": "#4da3ff",
  "conceptual-gateway": "#f0a94e",
  "conceptual-server": "#a78bfa",
  "sensor-environmental": "#3ecf8e",
  "sensor-parking": "#4da3ff",
  "sensor-security": "#ef5f6f",
  "sensor-lighting": "#f0d24e",
  "sensor-emergency": "#ef5f6f"
};
const ROLE_LABEL = {
  "real-world-context": "Real-world geographic context",
  "conceptual-gateway": "Conceptual IoT gateway (placeholder)",
  "conceptual-server": "Conceptual server / monitoring centre (placeholder)",
  "sensor-environmental": "Conceptual sensor — environmental monitoring",
  "sensor-parking": "Conceptual sensor — parking monitoring",
  "sensor-security": "Conceptual sensor — security monitoring",
  "sensor-lighting": "Conceptual sensor — smart lighting",
  "sensor-emergency": "Conceptual sensor — emergency monitoring"
};

function circleDivIcon(color, shape, size) {
  size = size || 14;
  const shapeCss = shape === "diamond" ? "transform:rotate(45deg);border-radius:3px;"
    : shape === "square" ? "border-radius:3px;"
    : "border-radius:50%;";
  return L.divIcon({
    className: "",
    html: `<div style="width:${size}px;height:${size}px;background:${color};${shapeCss}border:2px solid #1a2332;box-shadow:0 0 0 2px ${color}55"></div>`,
    iconSize: [size, size], iconAnchor: [size / 2, size / 2]
  });
}

function popupHtml(name, role, desc) {
  return `<div class="rw-pop-title">${name}</div><div class="rw-pop-role">${role}</div><div class="rw-pop-desc">${desc}</div>`;
}

function initMap(locations) {
  RW_LOCATIONS = locations;
  const anchor = locations.anchor;
  RW_MAP = L.map("rw-map", { zoomControl: true, attributionControl: true }).setView([anchor.latitude, anchor.longitude], 14);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }).addTo(RW_MAP);

  drawMarkers();
}

function clearLayer() {
  if (!RW_MAP) return;
  RW_MAP.eachLayer(l => { if (l instanceof L.Marker) RW_MAP.removeLayer(l); });
}

function addMarker(loc, shape) {
  const color = MARKER_COLOR[loc.type] || "#aab8c9";
  const m = L.marker([loc.latitude, loc.longitude], { icon: circleDivIcon(color, shape) }).addTo(RW_MAP);
  m.bindPopup(popupHtml(loc.name, ROLE_LABEL[loc.type] || loc.type, loc.description));
  return m;
}

function drawMarkers() {
  clearLayer();
  const d = RW_LOCATIONS;
  if (RW_STUDY_ON) {
    addMarker(d.anchor, "circle");
    (d.study_locations || []).forEach(s => addMarker(s, "circle"));
  } else {
    addMarker(d.conceptual_deployment.gateway, "diamond");
    addMarker(d.conceptual_deployment.server, "square");
    d.conceptual_deployment.sensors.forEach(s => addMarker(s, "circle"));
  }
}

function initStudyToggle() {
  const btn = document.getElementById("rw-study-toggle");
  if (!btn) return;
  btn.addEventListener("click", () => {
    RW_STUDY_ON = !RW_STUDY_ON;
    btn.classList.toggle("active", RW_STUDY_ON);
    btn.textContent = RW_STUDY_ON ? "Showing: Study Anchor" : "Showing: Conceptual Deployment";
    drawMarkers();
  });
}

// ---------------------------------------------------------------- mini topology (right panel)
function drawMiniTopo() {
  const container = document.getElementById("rw-mini-topo");
  if (!container || typeof renderTopology !== "function") return;
  const real = (window.DASHBOARD_DATA && window.DASHBOARD_DATA.topology_real) || {};
  const nodes = real["olsr-30-medium"] || generateTopology(15, 20);
  renderTopology(container, nodes, { congestionLevel: 0.4 });
}

// ---------------------------------------------------------------- presentation mode
function initPresentationMode() {
  const btn = document.getElementById("rw-present-btn");
  const overlay = document.getElementById("rw-present-overlay");
  if (!btn || !overlay) return;
  btn.addEventListener("click", () => overlay.classList.add("show"));
  overlay.querySelector(".close").addEventListener("click", () => overlay.classList.remove("show"));
  overlay.addEventListener("click", e => { if (e.target === overlay) overlay.classList.remove("show"); });
}

async function initRealWorldSection(dashboardData) {
  window.DASHBOARD_DATA = dashboardData;
  try {
    const locations = await fetch("data/phuket-locations.json").then(r => r.json());
    initMap(locations);
    initStudyToggle();
  } catch (e) {
    const mapEl = document.getElementById("rw-map");
    if (mapEl) mapEl.innerHTML = '<div style="padding:20px;color:var(--text-faint);font-size:.8rem">Map data unavailable.</div>';
    console.error("Real-world map failed to load:", e);
  }
  drawMiniTopo();
  initPresentationMode();
}
