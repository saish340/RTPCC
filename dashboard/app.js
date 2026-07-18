const DEFAULT_API_BASE = "http://127.0.0.1:8000";
const POLL_INTERVAL_MS = 2000;

const state = {
  graph: null,
  route: null,
  alerts: [],
  lastAlertCount: 0,
  lastRouteKey: "",
  lastUpdatedAt: null,
};

const elements = {
  apiBase: document.getElementById("apiBase"),
  startNode: document.getElementById("startNode"),
  endNode: document.getElementById("endNode"),
  refreshBtn: document.getElementById("refreshBtn"),
  speechBtn: document.getElementById("speechBtn"),
  statusLine: document.getElementById("statusLine"),
  routeBadge: document.getElementById("routeBadge"),
  rerouteState: document.getElementById("rerouteState"),
  routeTrail: document.getElementById("routeTrail"),
  nodesList: document.getElementById("nodesList"),
  edgesList: document.getElementById("edgesList"),
  routeSummary: document.getElementById("routeSummary"),
  alertsList: document.getElementById("alertsList"),
  alertCount: document.getElementById("alertCount"),
};

function storageKey(name) {
  return `rtpcc.dashboard.${name}`;
}

function loadSettings() {
  elements.apiBase.value = localStorage.getItem(storageKey("apiBase")) || DEFAULT_API_BASE;
  elements.startNode.value = localStorage.getItem(storageKey("startNode")) || "n1";
  elements.endNode.value = localStorage.getItem(storageKey("endNode")) || "n6";
}

function saveSettings() {
  localStorage.setItem(storageKey("apiBase"), elements.apiBase.value.trim());
  localStorage.setItem(storageKey("startNode"), elements.startNode.value.trim());
  localStorage.setItem(storageKey("endNode"), elements.endNode.value.trim());
}

function apiBase() {
  return elements.apiBase.value.trim().replace(/\/$/, "");
}

async function fetchJson(path) {
  const response = await fetch(`${apiBase()}${path}`);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(`${response.status} ${message || response.statusText}`);
  }
  return response.json();
}

function statusClass(status) {
  return String(status || "").toLowerCase();
}

function statusLabel(status) {
  return String(status || "UNKNOWN").replaceAll("_", " ");
}

function edgeKey(fromNode, toNode) {
  return [fromNode, toNode].sort().join("::");
}

function routeEdgeIds(graph, route) {
  if (!graph || !route || !Array.isArray(route.route)) {
    return new Set();
  }
  const edgeMap = new Map(
    graph.edges.map((edge) => [edgeKey(edge.from_node, edge.to_node), edge.id])
  );
  const ids = new Set();
  for (let index = 0; index < route.route.length - 1; index += 1) {
    const key = edgeKey(route.route[index], route.route[index + 1]);
    const edgeId = edgeMap.get(key);
    if (edgeId) {
      ids.add(edgeId);
    }
  }
  return ids;
}

function nodeName(graph, nodeId) {
  const node = graph?.nodes?.find((item) => item.id === nodeId);
  return node ? node.name : nodeId;
}

function routeLabel(graph, route) {
  if (!route?.route?.length) {
    return "No route available";
  }
  return route.route.map((id) => nodeName(graph, id)).join(" → ");
}

function renderNodes(graph) {
  elements.nodesList.innerHTML = graph.nodes
    .map(
      (node) => `
        <div class="node-card">
          <strong>${node.name}</strong>
          <div class="meta">${node.id}</div>
          <div class="meta">Type: ${node.type}</div>
        </div>`
    )
    .join("");
}

function renderEdges(graph, routeSet) {
  elements.edgesList.innerHTML = graph.edges
    .map((edge) => {
      const badgeClass = statusClass(edge.current_status);
      const routeClass = routeSet.has(edge.id) ? " route-edge" : "";
      const costText = edge.current_cost === "inf" ? "Blocked" : edge.current_cost.toFixed(2);
      return `
        <div class="edge-card${routeClass}">
          <strong>${edge.id}</strong>
          <div class="meta">${nodeName(graph, edge.from_node)} → ${nodeName(graph, edge.to_node)}</div>
          <div class="meta">Base distance: ${edge.base_distance.toFixed(2)}</div>
          <div class="meta">Density: ${edge.current_density.toFixed(2)}</div>
          <div class="meta">Cost: ${costText}</div>
          <div class="badge ${badgeClass}">${statusLabel(edge.current_status)}</div>
        </div>`;
    })
    .join("");
}

function renderRouteTrail(graph, route) {
  if (!route?.route?.length) {
    elements.routeTrail.innerHTML = `<div class="trail-chip">No active route</div>`;
    return;
  }

  elements.routeTrail.innerHTML = route.route
    .map((nodeId, index) => {
      const isLast = index === route.route.length - 1;
      return `
        <div class="trail-chip">
          ${nodeName(graph, nodeId)}
          ${isLast ? "" : " →"}
        </div>`;
    })
    .join("");
}

function renderRouteSummary(graph, route) {
  if (!route) {
    elements.routeBadge.className = "pill neutral";
    elements.routeBadge.textContent = "Route not loaded";
    elements.routeSummary.innerHTML = `<div class="route-summary-item">Waiting for route data...</div>`;
    return;
  }

  elements.routeBadge.className = `pill ${route.rerouted ? "stampede_risk" : "free_flow"}`;
  elements.routeBadge.textContent = route.rerouted ? "Rerouted" : "Stable route";

  elements.routeSummary.innerHTML = `
    <div class="route-summary-item">
      <strong>${routeLabel(graph, route)}</strong>
      <div class="meta">${route.start} → ${route.end}</div>
      <div class="meta">Total cost: ${Number.isFinite(route.total_cost) ? route.total_cost.toFixed(2) : "No path"}</div>
      <div class="meta">Rerouted: ${route.rerouted ? "Yes" : "No"}</div>
      <div class="meta">Reason: ${route.reroute_reason || "-"}</div>
    </div>`;

  elements.rerouteState.className = `pill ${route.rerouted ? "stampede_risk" : "free_flow"}`;
  elements.rerouteState.textContent = route.rerouted ? "Reroute active" : "Stable route";
}

function renderAlerts(graph, alerts) {
  elements.alertCount.textContent = `${alerts.length} alerts`;
  elements.alertsList.innerHTML = alerts
    .slice()
    .reverse()
    .slice(0, 20)
    .map((alert) => {
      const details = alert.details || {};
      const isCritical = alert.event_type === "status_change" && details.new_status === "STAMPEDE_RISK";
      const edge = graph?.edges?.find((item) => item.id === details.edge_id);
      const edgeLabel = edge ? `${edge.id}: ${nodeName(graph, edge.from_node)} → ${nodeName(graph, edge.to_node)}` : details.edge_id || "n/a";
      return `
        <div class="alert-card${isCritical ? " new" : ""}">
          <div class="timestamp">${new Date(alert.timestamp).toLocaleString()}</div>
          <strong>${alert.event_type.replaceAll("_", " ")}</strong>
          <div>${alert.message}</div>
          <div class="meta">Edge: ${edgeLabel}</div>
          <div class="meta">Details: ${JSON.stringify(details)}</div>
        </div>`;
    })
    .join("");
}

function setStatus(message, tone = "neutral") {
  elements.statusLine.textContent = message;
}

function announceCriticalAlert(alert, graph) {
  if (!window.speechSynthesis) {
    return;
  }

  const details = alert.details || {};
  const edge = graph?.edges?.find((item) => item.id === details.edge_id);
  const zone = edge
    ? `${nodeName(graph, edge.from_node)} to ${nodeName(graph, edge.to_node)}`
    : details.edge_id || "an affected zone";
  const utterance = new SpeechSynthesisUtterance(
    `Alert: high risk detected in ${zone}. Please follow alternate route signage.`
  );
  utterance.rate = 0.95;
  utterance.pitch = 1;
  utterance.volume = 1;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utterance);
}

async function refreshDashboard() {
  try {
    saveSettings();
    const [graph, route, alerts] = await Promise.all([
      fetchJson("/venue/graph"),
      fetchJson(`/route?start=${encodeURIComponent(elements.startNode.value.trim())}&end=${encodeURIComponent(elements.endNode.value.trim())}`),
      fetchJson("/alerts"),
    ]);

    state.graph = graph;
    state.route = route;
    state.alerts = alerts.alerts || [];

    const routeSet = routeEdgeIds(graph, route);
    renderNodes(graph);
    renderEdges(graph, routeSet);
    renderRouteTrail(graph, route);
    renderRouteSummary(graph, route);
    renderAlerts(graph, state.alerts);

    const newAlerts = state.alerts.slice(state.lastAlertCount);
    for (const alert of newAlerts) {
      const details = alert.details || {};
      if (alert.event_type === "status_change" && details.new_status === "STAMPEDE_RISK") {
        announceCriticalAlert(alert, graph);
      }
    }
    state.lastAlertCount = state.alerts.length;

    const routeKey = JSON.stringify(route.route || []);
    state.lastRouteKey = routeKey;
    state.lastUpdatedAt = new Date();
    setStatus(`Updated ${state.lastUpdatedAt.toLocaleTimeString()}`, route.rerouted ? "stampede_risk" : "free_flow");
  } catch (error) {
    elements.routeBadge.className = "pill stampede_risk";
    elements.routeBadge.textContent = "API unavailable";
    setStatus(`API error: ${error.message}`);
  }
}

function testSpeech() {
  if (!window.speechSynthesis) {
    setStatus("Speech synthesis unavailable in this browser.", "critical_bottleneck");
    return;
  }
  const utterance = new SpeechSynthesisUtterance(
    "Alert: high risk detected in the selected zone. Please follow alternate route signage."
  );
  utterance.rate = 0.95;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utterance);
  setStatus("Speech test played.", "high_density");
}

loadSettings();
elements.refreshBtn.addEventListener("click", refreshDashboard);
elements.speechBtn.addEventListener("click", testSpeech);
elements.apiBase.addEventListener("change", refreshDashboard);
elements.startNode.addEventListener("change", refreshDashboard);
elements.endNode.addEventListener("change", refreshDashboard);

refreshDashboard();
setInterval(refreshDashboard, POLL_INTERVAL_MS);