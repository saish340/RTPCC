/* ═══════════════════════════════════════════════════════════════════════════
   RTPCC — Dashboard Controller
   ═══════════════════════════════════════════════════════════════════════════ */

const DEFAULT_API_BASE = "http://127.0.0.1:8000";
const POLL_INTERVAL_MS = 2500;
const STATUS_COLORS = {
  FREE_FLOW: "#10B981",
  HIGH_DENSITY: "#FACC15",
  CRITICAL_BOTTLENECK: "#FB923C",
  STAMPEDE_RISK: "#EF4444",
};
const DENSITY_HISTORY_MAX = 60;

/* ─── State ─── */
const state = {
  graph: null,
  route: null,
  alerts: [],
  lastAlertCount: 0,
  lastRoutePath: null,
  densityHistory: {},
  previousKpis: {},
};

/* ─── DOM refs ─── */
const $ = (id) => document.getElementById(id);
const dom = {
  apiBase: $("apiBase"), startNode: $("startNode"), endNode: $("endNode"),
  refreshBtn: $("refreshBtn"), speechBtn: $("speechBtn"), statusLine: $("statusLine"),
  statusDot: $("statusDot"), statusLabel: $("statusLabel"),
  currentTime: $("currentTime"),
  graphSvg: $("graphSvg"), graphNodeCount: $("graphNodeCount"), graphEdgeCount: $("graphEdgeCount"),
  kpiActiveZones: $("kpiActiveZones"), kpiAlerts: $("kpiAlerts"),
  kpiMaxDensity: $("kpiMaxDensity"), kpiAvgDensity: $("kpiAvgDensity"),
  kpiRouteStatus: $("kpiRouteStatus"), kpiBackend: $("kpiBackend"),
  routeBadge: $("routeBadge"), routeSummary: $("routeSummary"),
  alertCount: $("alertCount"), alertsList: $("alertsList"),
  trendEdgeSelect: $("trendEdgeSelect"), trendChart: $("trendChart"),
  feedStatus: $("feedStatus"),
  healthApi: $("healthApi"), healthApiLabel: $("healthApiLabel"),
  healthVision: $("healthVision"), healthVisionLabel: $("healthVisionLabel"),
  healthRouting: $("healthRouting"), healthRoutingLabel: $("healthRoutingLabel"),
  healthSimulator: $("healthSimulator"), healthSimulatorLabel: $("healthSimulatorLabel"),
  healthModel: $("healthModel"), healthModelLabel: $("healthModelLabel"),
  healthCamera: $("healthCamera"), healthCameraLabel: $("healthCameraLabel"),
  edgeInfoPanel: $("edgeInfoPanel"), edgeInfoTitle: $("edgeInfoTitle"),
  edgeInfoBody: $("edgeInfoBody"), edgeInfoClose: $("edgeInfoClose"),
  viewToggleBtn: $("viewToggleBtn"), viewToggleLabel: $("viewToggleLabel"),
  viewToggleIcon: $("viewToggleIcon"), venueMapImg: $("venueMapImg"),
};

/* ─── Node positions for graph SVG (viewBox 0 0 500 400) ─── */
const NODE_POS = {
  n1: { x: 80, y: 340, label: "Main Entrance" },
  n2: { x: 80, y: 200, label: "Concourse A" },
  n3: { x: 200, y: 70, label: "Concourse B" },
  n4: { x: 250, y: 200, label: "Central Hub" },
  n5: { x: 400, y: 200, label: "West Wing" },
  n6: { x: 420, y: 340, label: "East Exit" },
  n7: { x: 350, y: 60, label: "North Exit" },
};

/* ─── Edge definitions for graph (from_node, to_node, edge_id) ─── */
const EDGE_DEFS = [
  { from: "n1", to: "n2", id: "e1" },
  { from: "n2", to: "n4", id: "e2" },
  { from: "n2", to: "n3", id: "e3" },
  { from: "n3", to: "n4", id: "e4" },
  { from: "n4", to: "n5", id: "e5" },
  { from: "n4", to: "n6", id: "e6" },
  { from: "n5", to: "n6", id: "e7" },
  { from: "n5", to: "n7", id: "e8" },
  { from: "n6", to: "n7", id: "e9" },
];

/* ─── Helpers ─── */
function apiBase() { return dom.apiBase.value.trim().replace(/\/+$/, "") || DEFAULT_API_BASE; }
function storageKey(name) { return `rtpcc.v2.${name}`; }

async function fetchJson(path) {
  const r = await fetch(`${apiBase()}${path}`, { signal: AbortSignal.timeout(5000) });
  if (!r.ok) { const msg = await r.text().catch(() => r.statusText); throw new Error(`${r.status} ${msg}`); }
  return r.json();
}

function saveSettings() {
  localStorage.setItem(storageKey("apiBase"), dom.apiBase.value);
  localStorage.setItem(storageKey("startNode"), dom.startNode.value);
  localStorage.setItem(storageKey("endNode"), dom.endNode.value);
}
function loadSettings() {
  dom.apiBase.value = localStorage.getItem(storageKey("apiBase")) || DEFAULT_API_BASE;
  dom.startNode.value = localStorage.getItem(storageKey("startNode")) || "n1";
  dom.endNode.value = localStorage.getItem(storageKey("endNode")) || "n6";
}

/* ─── Clock ─── */
function updateClock() {
  dom.currentTime.textContent = new Date().toLocaleTimeString("en-US", { hour12: false });
}

/* ─── SVG Graph Rendering ─── */
function nodeIdFromAttr(el) { return el?.getAttribute?.("data-node-id"); }
function edgeIdFromAttr(el) { return el?.getAttribute?.("data-edge-id"); }

function drawGraph() {
  const svg = dom.graphSvg;
  const g = state.graph;
  if (!g) return;
  dom.graphNodeCount.textContent = `${g.nodes.length} nodes`;
  dom.graphEdgeCount.textContent = `${g.edges.length} edges`;

  const routeEdgeIds = new Set();
  const r = state.route;
  if (r && Array.isArray(r.path) && r.path.length > 1) {
    for (let i = 0; i < r.path.length - 1; i++) {
      const a = r.path[i], b = r.path[i + 1];
      for (const edge of g.edges) {
        if ((edge.from_node === a && edge.to_node === b) || (edge.from_node === b && edge.to_node === a)) {
          routeEdgeIds.add(edge.edge_id);
          break;
        }
      }
    }
  }

  let edgeHtml = "";
  for (const def of EDGE_DEFS) {
    const p1 = NODE_POS[def.from], p2 = NODE_POS[def.to];
    if (!p1 || !p2) continue;
    const apiEdge = g.edges.find((e) => e.edge_id === def.id);
    const status = apiEdge ? (apiEdge.status || "FREE_FLOW") : "FREE_FLOW";
    const color = STATUS_COLORS[status] || "#64748B";
    const isRoute = routeEdgeIds.has(def.id);
    const classes = `edge-line${isRoute ? " route-edge" : ""}`;
    const density = apiEdge ? apiEdge.current_density.toFixed(2) : "?";
    edgeHtml += `<line class="${classes}" data-edge-id="${def.id}" x1="${p1.x}" y1="${p1.y}" x2="${p2.x}" y2="${p2.y}" stroke="${color}" stroke-width="${isRoute ? 3 : 2}" data-status="${status}" data-density="${density}"/>`;
  }

  let nodeHtml = "";
  for (const [id, pos] of Object.entries(NODE_POS)) {
    const apiNode = g.nodes.find((nd) => nd.id === id);
    const label = apiNode ? apiNode.name : pos.label;
    const isEntry = apiNode?.type === "entry";
    const isExit = apiNode?.type === "exit";
    const r = isEntry || isExit ? 7 : 5;
    const fill = isEntry ? "#10B981" : isExit ? "#3B82F6" : "#94A3B8";
    nodeHtml += `<circle class="node-circle" data-node-id="${id}" cx="${pos.x}" cy="${pos.y}" r="${r}" fill="${fill}" stroke="#1E293B" stroke-width="2"/>`;
    nodeHtml += `<text class="node-label" x="${pos.x}" y="${pos.y + r + 14}" text-anchor="middle" font-size="9" fill="#94A3B8">${label}</text>`;
  }

  svg.innerHTML = edgeHtml + nodeHtml;

  svg.querySelectorAll(".edge-line").forEach((el) => {
    el.addEventListener("click", (e) => {
      const id = e.currentTarget.getAttribute("data-edge-id");
      showEdgeInfo(id);
    });
  });
}

/* ─── Edge Info Panel ─── */
function showEdgeInfo(edgeId) {
  if (!state.graph) return;
  const edge = state.graph.edges.find((e) => e.edge_id === edgeId);
  if (!edge) return;
  dom.edgeInfoTitle.textContent = `Edge ${edge.edge_id}`;
  const costText = edge.cost === "inf" ? "Blocked (∞)" : edge.cost.toFixed(2);
  dom.edgeInfoBody.innerHTML = `
    <div class="ei-row"><span class="ei-label">From → To</span><span>${edge.from_node} → ${edge.to_node}</span></div>
    <div class="ei-row"><span class="ei-label">Density</span><span>${edge.current_density.toFixed(2)} p/m²</span></div>
    <div class="ei-row"><span class="ei-label">Status</span><span style="color:${STATUS_COLORS[edge.status] || '#94A3B8'}">${edge.status.replace(/_/g, " ")}</span></div>
    <div class="ei-row"><span class="ei-label">Base Distance</span><span>${edge.base_distance.toFixed(1)} m</span></div>
    <div class="ei-row"><span class="ei-label">Current Cost</span><span>${costText}</span></div>
    <div class="ei-row"><span class="ei-label">Last Updated</span><span style="font-size:0.7rem">${new Date(edge.last_updated).toLocaleTimeString()}</span></div>
  `;
  dom.edgeInfoPanel.style.display = "block";
}
dom.edgeInfoClose.addEventListener("click", () => { dom.edgeInfoPanel.style.display = "none"; });

/* ─── KPI Updates with Animation ─── */
function animateValue(el, newVal, suffix = "") {
  const oldVal = state.previousKpis[el.id];
  if (oldVal === newVal && el.textContent !== "--") return;
  state.previousKpis[el.id] = newVal;
  const display = typeof newVal === "number" ? newVal.toFixed(2) : String(newVal);
  el.textContent = display + suffix;
  el.style.transition = "transform 0.15s ease";
  el.style.transform = "scale(1.15)";
  setTimeout(() => { el.style.transform = "scale(1)"; }, 150);
}

function updateKpis() {
  const g = state.graph;
  if (!g) return;

  const activeZones = g.edges.filter((e) => e.current_density > 0.5).length;
  const maxD = g.edges.length ? Math.max(...g.edges.map((e) => e.current_density)) : 0;
  const avgD = g.edges.length ? g.edges.reduce((s, e) => s + e.current_density, 0) / g.edges.length : 0;
  const routeStable = state.route && !state.route.rerouted;
  const routeActive = state.route && state.route.path && state.route.path.length > 0;

  animateValue(dom.kpiActiveZones, activeZones);
  animateValue(dom.kpiAlerts, state.alerts.length);
  animateValue(dom.kpiMaxDensity, maxD);
  animateValue(dom.kpiAvgDensity, avgD);

  if (routeActive) {
    dom.kpiRouteStatus.textContent = routeStable ? "Stable" : "Rerouted";
    dom.kpiRouteStatus.style.color = routeStable ? "var(--success)" : "var(--danger)";
  } else {
    dom.kpiRouteStatus.textContent = "--";
    dom.kpiRouteStatus.style.color = "";
  }

  dom.kpiBackend.textContent = "Connected";
  dom.kpiBackend.style.color = "var(--success)";
}

/* ─── Route Display ─── */
function renderRoute() {
  const r = state.route;
  const el = dom.routeSummary;
  if (!r || !Array.isArray(r.path) || r.path.length === 0) {
    dom.routeBadge.textContent = "No Route";
    dom.routeBadge.style.background = "rgba(148,163,184,0.10)";
    dom.routeBadge.style.color = "var(--muted-text)";
    el.innerHTML = `<div class="route-skeleton">No route available</div>`;
    return;
  }

  const isRerouted = r.rerouted;
  dom.routeBadge.textContent = isRerouted ? "Rerouted" : "Stable";
  dom.routeBadge.style.background = isRerouted ? "rgba(239,68,68,0.15)" : "rgba(16,185,129,0.15)";
  dom.routeBadge.style.color = isRerouted ? "var(--danger)" : "var(--success)";

  const costText = Number.isFinite(r.total_cost) ? r.total_cost.toFixed(1) : "No path";

  let pathHtml = r.path.map((nid) => {
    const name = state.graph?.nodes?.find((nd) => nd.id === nid)?.name || nid;
    return `<span class="route-node">${name}</span>`;
  }).join(`<span class="route-arrow"> → </span>`);

  let prevHtml = "";
  if (isRerouted && Array.isArray(r.previous_path) && r.previous_path.length > 0) {
    prevHtml = `<div class="route-previous">Previous: ${r.previous_path.join(" → ")}</div>`;
  }

  el.innerHTML = `
    <div class="route-path-display">${pathHtml}</div>
    <div class="route-meta">
      <div class="route-meta-item">
        <span class="route-meta-label">Total Cost</span>
        <span class="route-meta-value">${costText}</span>
      </div>
      <div class="route-meta-item">
        <span class="route-meta-label">Status</span>
        <span class="route-meta-value" style="color:${isRerouted ? "var(--danger)" : "var(--success)"}">${isRerouted ? "Rerouted" : "Active"}</span>
      </div>
    </div>
    ${prevHtml}
  `;
}

/* ─── Alert Feed ─── */
function renderAlerts() {
  dom.alertCount.textContent = `${state.alerts.length}`;
  const list = dom.alertsList;
  list.innerHTML = state.alerts.slice().reverse().slice(0, 30).map((a) => {
    const isCritical = a.event_type === "STATUS_CHANGE" && a.new_status === "STAMPEDE_RISK";
    const isWarning = a.event_type === "STATUS_CHANGE" && (a.new_status === "HIGH_DENSITY" || a.new_status === "CRITICAL_BOTTLENECK");
    const cat = isCritical ? "critical" : isWarning ? "warning" : "info";
    const ts = new Date(a.timestamp).toLocaleTimeString("en-US", { hour12: false });
    const msg = a.message || `${a.edge_id}: ${a.old_status || "?"} → ${a.new_status}`;
    const edgeLabel = a.edge_id ? `Edge ${a.edge_id}` : "";
    return `<div class="alert-item ${cat}">
      <div class="alert-top">
        <span class="alert-type ${cat}">${a.event_type.replace(/_/g, " ")}</span>
        <span class="alert-time">${ts}</span>
      </div>
      <div class="alert-message">${msg}</div>
      ${edgeLabel ? `<div class="alert-edge">${edgeLabel}</div>` : ""}
    </div>`;
  }).join("");
}

/* ─── Density History & Trend Chart ─── */
function updateDensityHistory() {
  const g = state.graph;
  if (!g) return;
  const now = Date.now();
  for (const edge of g.edges) {
    if (!state.densityHistory[edge.edge_id]) state.densityHistory[edge.edge_id] = [];
    const h = state.densityHistory[edge.edge_id];
    h.push({ t: now, v: edge.current_density });
    if (h.length > DENSITY_HISTORY_MAX) h.shift();
  }
}

function drawTrendChart() {
  const canvas = dom.trendChart;
  const rect = canvas.parentElement.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const w = rect.width || 400, h = rect.height || 140;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  canvas.style.width = w + "px";
  canvas.style.height = h + "px";
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);

  const selected = dom.trendEdgeSelect.value;
  ctx.clearRect(0, 0, w, h);

  const pad = { t: 8, b: 12, l: 8, r: 8 };
  const cw = w - pad.l - pad.r;
  const ch = h - pad.t - pad.b;

  let allData = [];
  if (selected === "__all__") {
    for (const h of Object.values(state.densityHistory)) allData = allData.concat(h);
  } else {
    allData = state.densityHistory[selected] || [];
  }

  if (allData.length < 2) {
    ctx.fillStyle = "#64748B";
    ctx.font = "11px Inter, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("Waiting for data...", w / 2, h / 2 + 4);
    return;
  }

  const minT = allData[0].t;
  const maxT = allData[allData.length - 1].t;
  const tRange = maxT - minT || 1;
  const values = allData.map((d) => d.v);
  const minV = 0;
  const maxV = Math.max(Math.max(...values), 1);

  ctx.strokeStyle = "#3B82F6";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  for (let i = 0; i < allData.length; i++) {
    const x = pad.l + ((allData[i].t - minT) / tRange) * cw;
    const y = pad.t + ch - ((allData[i].v - minV) / (maxV - minV)) * ch;
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  }
  ctx.stroke();

  const gradient = ctx.createLinearGradient(0, pad.t, 0, pad.t + ch);
  gradient.addColorStop(0, "rgba(59,130,246,0.15)");
  gradient.addColorStop(1, "rgba(59,130,246,0.01)");
  ctx.fillStyle = gradient;
  ctx.lineTo(pad.l + cw, pad.t + ch);
  ctx.lineTo(pad.l, pad.t + ch);
  ctx.closePath();
  ctx.fill();

  ctx.fillStyle = "#64748B";
  ctx.font = "9px Inter, sans-serif";
  ctx.textAlign = "left";
  ctx.fillText(maxV.toFixed(1), pad.l, pad.t + 10);
  ctx.fillText("0", pad.l, pad.t + ch);
}

/* ─── System Health ─── */
function updateHealth() {
  const ok = state.graph !== null;
  const hasRoute = state.route && Array.isArray(state.route.path) && state.route.path.length > 0;
  const hasAlerts = state.alerts.length > 0;

  setHealth(dom.healthApi, dom.healthApiLabel, ok, ok ? "Connected" : "Error");
  setHealth(dom.healthRouting, dom.healthRoutingLabel, hasRoute, hasRoute ? "Active" : "Idle");
  setHealth(dom.healthVision, dom.healthVisionLabel, false, "Offline");
  setHealth(dom.healthSimulator, dom.healthSimulatorLabel, ok, ok ? "Detected" : "Unknown");
  setHealth(dom.healthModel, dom.healthModelLabel, false, "Offline");
  setHealth(dom.healthCamera, dom.healthCameraLabel, false, "Offline");

  dom.feedStatus.textContent = ok ? "API Connected" : "Disconnected";
  dom.feedStatus.style.background = ok ? "rgba(16,185,129,0.15)" : "rgba(239,68,68,0.15)";
  dom.feedStatus.style.color = ok ? "var(--success)" : "var(--danger)";
}

function setHealth(dot, label, healthy, text) {
  dot.className = "health-indicator " + (healthy ? "healthy" : "error");
  label.textContent = text;
}

/* ─── Speech ─── */
function checkNewAlerts() {
  if (!state.alerts || state.alerts.length <= state.lastAlertCount) return;
  const newAlerts = state.alerts.slice(state.lastAlertCount);
  state.lastAlertCount = state.alerts.length;
  for (const a of newAlerts) {
    if (a.event_type === "STATUS_CHANGE" && a.new_status === "STAMPEDE_RISK") {
      speakAlert(a);
    }
  }
}

function speakAlert(alert) {
  if (!window.speechSynthesis) return;
  const zone = alert.edge_id || "an affected zone";
  const msg = `Alert: stampede risk detected in zone ${zone}. Please follow alternate route signage.`;
  const utt = new SpeechSynthesisUtterance(msg);
  utt.rate = 0.95;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utt);
}

function testSpeech() {
  if (!window.speechSynthesis) { dom.statusLine.textContent = "Speech not available"; return; }
  const utt = new SpeechSynthesisUtterance("Alert: test announcement. This is a simulated public safety message.");
  utt.rate = 0.95;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utt);
  dom.statusLine.textContent = "Speech test played";
}

/* ─── Connection Status ─── */
function setConnection(ok, msg) {
  dom.statusDot.className = "status-dot " + (ok ? "connected" : "error");
  dom.statusLabel.textContent = ok ? "Connected" : "Error";
  dom.statusLine.textContent = msg;
}

/* ─── Main Poll ─── */
async function refreshDashboard() {
  try {
    saveSettings();
    const [graph, route, alertsResp] = await Promise.all([
      fetchJson("/venue/graph"),
      fetchJson(`/route?start=${encodeURIComponent(dom.startNode.value.trim())}&end=${encodeURIComponent(dom.endNode.value.trim())}`),
      fetchJson("/alerts"),
    ]);

    state.graph = graph;
    state.route = route;
    state.alerts = alertsResp.alerts || [];

    drawGraph();
    updateKpis();
    renderRoute();
    renderAlerts();
    updateDensityHistory();
    drawTrendChart();
    updateHealth();
    checkNewAlerts();
    setConnection(true, `Updated ${new Date().toLocaleTimeString("en-US", { hour12: false })}`);

    if (route && Array.isArray(route.path)) {
      const key = route.path.join("::");
      if (state.lastRoutePath !== null && state.lastRoutePath !== key && route.rerouted) {
        dom.statusLine.textContent = `Reroute detected`;
      }
      state.lastRoutePath = key;
    }

    populateEdgeSelect();
  } catch (err) {
    setConnection(false, `API: ${err.message}`);
    dom.routeBadge.textContent = "Unavailable";
    dom.routeBadge.style.background = "rgba(239,68,68,0.15)";
    dom.routeBadge.style.color = "var(--danger)";
    dom.kpiBackend.textContent = "Error";
    dom.kpiBackend.style.color = "var(--danger)";
    dom.healthApi.className = "health-indicator error";
    dom.healthApiLabel.textContent = "Disconnected";
  }
}

/* ─── Edge Select Populate ─── */
function populateEdgeSelect() {
  if (!state.graph) return;
  const sel = dom.trendEdgeSelect;
  const currentVal = sel.value;
  sel.innerHTML = `<option value="__all__">All Zones</option>`;
  for (const edge of state.graph.edges) {
    const opt = document.createElement("option");
    opt.value = edge.edge_id;
    opt.textContent = `${edge.edge_id} (${edge.from_node}→${edge.to_node})`;
    sel.appendChild(opt);
  }
  sel.value = currentVal;
  if (!sel.value) sel.value = "__all__";
}

/* ─── View Toggle (Graph / Floor Plan) ─── */
let showFloorPlan = false;
function toggleView() {
  showFloorPlan = !showFloorPlan;
  dom.graphSvg.style.display = showFloorPlan ? "none" : "block";
  dom.venueMapImg.style.display = showFloorPlan ? "block" : "none";
  dom.viewToggleLabel.textContent = showFloorPlan ? "Graph" : "Map";
  dom.viewToggleIcon.setAttribute("data-lucide", showFloorPlan ? "git-branch" : "map");
  lucide.createIcons();
}

/* ─── Init ─── */
window.addEventListener("DOMContentLoaded", () => {
  loadSettings();
  lucide.createIcons();
  updateClock();
  setInterval(updateClock, 1000);

  dom.refreshBtn.addEventListener("click", refreshDashboard);
  dom.speechBtn.addEventListener("click", testSpeech);
  dom.apiBase.addEventListener("change", refreshDashboard);
  dom.startNode.addEventListener("change", refreshDashboard);
  dom.endNode.addEventListener("change", refreshDashboard);
  dom.trendEdgeSelect.addEventListener("change", drawTrendChart);
  dom.viewToggleBtn.addEventListener("click", toggleView);

  refreshDashboard();
  setInterval(refreshDashboard, POLL_INTERVAL_MS);

  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(drawTrendChart, 200);
  });
});
