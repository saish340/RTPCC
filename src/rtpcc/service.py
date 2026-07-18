"""Shared application service for routing, alerts, and density updates."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from math import inf, isfinite
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx

from .risk import EdgeStatus, RiskThresholdEngine
from .venue import VenueGraph, build_sample_venue_graph


@dataclass(slots=True)
class CachedRoute:
    """Track the current recommended route for a start/end pair."""

    start: str
    end: str
    path: List[str]
    total_cost: float
    available: bool
    reroute_pending: bool = False
    reroute_reason: str = ""


class CrowdSafetyService:
    """Own the venue state, density updates, and current route recommendations."""

    def __init__(self, venue: Optional[VenueGraph] = None, smoothing_window: int = 3) -> None:
        self.venue = venue or build_sample_venue_graph()
        self.risk_engine = RiskThresholdEngine(window_size=smoothing_window)
        self.alerts: List[Dict[str, Any]] = []
        self._route_cache: Dict[Tuple[str, str], CachedRoute] = {}

        for edge in self.venue.edges:
            edge.current_density = 0.0
            edge.current_status = EdgeStatus.FREE_FLOW.value
            edge.current_cost = edge.base_distance
            edge.is_blocked = False

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _json_safe_value(self, value: Any) -> Any:
        if isinstance(value, float) and not isfinite(value):
            return "inf"
        if isinstance(value, list):
            return [self._json_safe_value(item) for item in value]
        if isinstance(value, dict):
            return {key: self._json_safe_value(item) for key, item in value.items()}
        return value

    def _append_alert(self, event_type: str, message: str, **details: Any) -> Dict[str, Any]:
        alert = {
            "timestamp": self._timestamp(),
            "event_type": event_type,
            "message": message,
            "details": self._json_safe_value(details),
        }
        self.alerts.append(alert)
        return alert

    def _build_graph(self) -> nx.Graph:
        graph = nx.Graph()
        for node in self.venue.nodes:
            graph.add_node(node.id, name=node.name, type=node.type)

        for edge in self.venue.edges:
            if edge.is_blocked or edge.current_cost == inf:
                continue
            graph.add_edge(
                edge.from_node,
                edge.to_node,
                id=edge.id,
                cost=edge.current_cost,
                base_distance=edge.base_distance,
                status=edge.current_status,
            )

        return graph

    def _compute_route(self, start: str, end: str) -> CachedRoute:
        graph = self._build_graph()

        if not graph.has_node(start):
            raise KeyError(f"Unknown start node: {start}")
        if not graph.has_node(end):
            raise KeyError(f"Unknown end node: {end}")

        try:
            path = nx.shortest_path(graph, source=start, target=end, weight="cost")
            total_cost = float(nx.path_weight(graph, path, weight="cost"))
            return CachedRoute(start=start, end=end, path=path, total_cost=total_cost, available=True)
        except nx.NetworkXNoPath:
            return CachedRoute(start=start, end=end, path=[], total_cost=inf, available=False)

    def _refresh_cached_routes(self, changed_edge_id: str) -> List[Dict[str, Any]]:
        reroute_events: List[Dict[str, Any]] = []
        for cached_route in self._route_cache.values():
            recomputed_route = self._compute_route(cached_route.start, cached_route.end)
            route_changed = recomputed_route.available != cached_route.available or recomputed_route.path != cached_route.path
            if route_changed:
                previous_path = cached_route.path
                cached_route.path = recomputed_route.path
                cached_route.total_cost = recomputed_route.total_cost
                cached_route.available = recomputed_route.available
                cached_route.reroute_pending = True
                cached_route.reroute_reason = f"edge {changed_edge_id} changed route availability"
                reroute_events.append(
                    self._append_alert(
                        "reroute",
                        "Recommended route changed after density update",
                        start=cached_route.start,
                        end=cached_route.end,
                        changed_edge_id=changed_edge_id,
                        previous_path=previous_path,
                        new_path=recomputed_route.path,
                        available=recomputed_route.available,
                    )
                )
            elif recomputed_route.available:
                cached_route.total_cost = recomputed_route.total_cost
        return reroute_events

    def update_density(self, edge_id: str, density: float) -> Dict[str, Any]:
        edge = self.venue.get_edge(edge_id)
        previous_status = edge.current_status
        previous_cost = edge.current_cost

        result = self.risk_engine.update_edge_density(edge_id=edge.id, density=density, base_distance=edge.base_distance)
        edge.current_density = density

        if result.committed:
            edge.current_status = result.committed_status.value
            edge.current_cost = result.cost
            edge.is_blocked = result.blocked

            if previous_status != edge.current_status:
                self._append_alert(
                    "status_change",
                    "Edge risk status committed",
                    edge_id=edge.id,
                    previous_status=previous_status,
                    new_status=edge.current_status,
                    density=density,
                    previous_cost=previous_cost,
                    new_cost=edge.current_cost,
                    blocked=edge.is_blocked,
                )

            reroutes = self._refresh_cached_routes(changed_edge_id=edge.id)
        else:
            reroutes = []

        if result.telemetry_warning:
            self._append_alert(
                "telemetry_warning",
                "Non-public telemetry warning: elevated density detected",
                edge_id=edge.id,
                density=density,
                committed_status=result.committed_status.value,
                raw_status=result.raw_status.value,
            )

        payload = asdict(result)
        payload.update(
            {
                "edge": edge.model_dump(by_alias=True),
                "reroutes": reroutes,
            }
        )
        return payload

    def get_route(self, start: str, end: str) -> Dict[str, Any]:
        route = self._compute_route(start=start, end=end)
        cached_route = self._route_cache.get((start, end))

        rerouted = False
        reroute_reason = ""

        if cached_route is None:
            self._route_cache[(start, end)] = route
        else:
            rerouted = cached_route.reroute_pending or cached_route.path != route.path or cached_route.available != route.available
            reroute_reason = cached_route.reroute_reason
            cached_route.path = route.path
            cached_route.total_cost = route.total_cost
            cached_route.available = route.available
            cached_route.reroute_pending = False
            cached_route.reroute_reason = ""

        if not route.available:
            raise ValueError(f"No available route from {start} to {end}")

        return {
            "start": start,
            "end": end,
            "route": route.path,
            "total_cost": route.total_cost,
            "rerouted": rerouted,
            "reroute_reason": reroute_reason,
        }

    def graph_snapshot(self) -> Dict[str, Any]:
        return self.venue.snapshot()

    def alert_log(self) -> List[Dict[str, Any]]:
        return list(self.alerts)
