"""Density simulation endpoint."""

from __future__ import annotations

from datetime import datetime, timezone
from math import inf

from fastapi import APIRouter, HTTPException

from app.models import DensityUpdateRequest, EdgeState, AlertEvent
from app.state import alerts, edge_updated_at, last_routes, service
from app.routers.routing import edge_ids_for_path

router = APIRouter(tags=["simulate"])


def _alert_payload(event_type: str, edge_id: str, old_status: str | None, new_status: str, message: str) -> AlertEvent:
    return AlertEvent(
        timestamp=datetime.now(timezone.utc),
        edge_id=edge_id,
        event_type=event_type,
        old_status=old_status,
        new_status=new_status,
        message=message,
    )


@router.post("/simulate/density", response_model=EdgeState)
def simulate_density(payload: DensityUpdateRequest) -> EdgeState:
    try:
        edge = service.venue.get_edge(payload.edge_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    previous_status = edge.current_status
    previous_cost = edge.current_cost
    result = service.risk_engine.update_edge_density(edge.id, payload.density, edge.base_distance)

    edge.current_density = payload.density
    edge_updated_at[edge.id] = datetime.now(timezone.utc)
    if result.committed:
        edge.current_status = result.committed_status.value
        edge.current_cost = result.cost
        edge.is_blocked = result.blocked

        if previous_status != edge.current_status:
            alerts.append(
                _alert_payload(
                    event_type="STATUS_CHANGE",
                    edge_id=edge.id,
                    old_status=previous_status,
                    new_status=edge.current_status,
                    message=f"Edge {edge.id} changed from {previous_status} to {edge.current_status}",
                ).model_dump()
            )

        # A changed edge can make an alternative route preferable, even if it
        # was not part of the cached recommendation, so recompute all routes.
        for route_key, route_info in list(last_routes.items()):
            try:
                recomputed = service.get_route(*route_key)
                new_path = recomputed["route"]
                total_cost = recomputed["total_cost"]
            except ValueError:
                new_path = []
                total_cost = float("inf")

            path_changed = new_path != route_info["path"]
            if path_changed:
                alerts.append(
                    _alert_payload(
                        event_type="REROUTE",
                        edge_id=edge.id,
                        old_status=previous_status,
                        new_status=edge.current_status,
                        message=f"Route {route_key[0]}->{route_key[1]} rerouted from {route_info['path']} to {new_path}",
                    ).model_dump()
                )

            last_routes[route_key] = {
                "path": new_path,
                "edge_ids": edge_ids_for_path(new_path),
                "total_cost": total_cost,
                "reroute_pending": path_changed,
                "previous_path": route_info["path"] if path_changed else None,
            }

    return EdgeState(
        edge_id=edge.id,
        from_node=edge.from_node,
        to_node=edge.to_node,
        base_distance=edge.base_distance,
        current_density=edge.current_density,
        status=edge.current_status,
        cost="inf" if edge.current_cost == inf else edge.current_cost,
        last_updated=edge_updated_at[edge.id],
    )
