"""Routing endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models import RouteResponse
from app.state import last_routes, service

router = APIRouter(tags=["routing"])


def edge_ids_for_path(path: list[str]) -> list[str]:
    """Map a node path to its venue edge IDs."""
    ids: list[str] = []
    for start, end in zip(path, path[1:]):
        for edge in service.venue.edges:
            if {edge.from_node, edge.to_node} == {start, end}:
                ids.append(edge.id)
                break
    return ids


@router.get("/route", response_model=RouteResponse)
def get_route(start: str, end: str) -> RouteResponse:
    try:
        route = service.get_route(start, end)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if route["route"]:
        edge_statuses = []
        edge_ids = []
        for index in range(len(route["route"]) - 1):
            pair = {route["route"][index], route["route"][index + 1]}
            for edge in service.venue.edges:
                if {edge.from_node, edge.to_node} == pair:
                    edge_statuses.append(edge.current_status)
                    edge_ids.append(edge.id)
                    break
    else:
        edge_statuses = []
        edge_ids = []

    previous = last_routes.get((start, end))
    rerouted = bool(previous and (previous.get("reroute_pending") or previous["path"] != route["route"]))
    previous_path = previous.get("previous_path") if previous and previous.get("reroute_pending") else None
    if rerouted and previous_path is None and previous:
        previous_path = previous["path"]
    last_routes[(start, end)] = {
        "path": route["route"],
        "edge_ids": edge_ids,
        "total_cost": route["total_cost"],
        "reroute_pending": False,
        "previous_path": None,
    }

    return RouteResponse(
        path=route["route"],
        total_cost=route["total_cost"],
        edge_statuses=edge_statuses,
        rerouted=rerouted,
        previous_path=previous_path,
    )
