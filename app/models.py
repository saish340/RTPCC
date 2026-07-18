"""Pydantic models used by the RTPCC API layer."""

from __future__ import annotations

from datetime import datetime

from typing import Literal

from pydantic import BaseModel, Field


class DensityUpdateRequest(BaseModel):
    edge_id: str
    density: float = Field(ge=0.0)


class NodeState(BaseModel):
    id: str
    name: str
    type: str


class EdgeState(BaseModel):
    edge_id: str
    from_node: str
    to_node: str
    base_distance: float
    current_density: float
    status: str
    # STAMPEDE_RISK edges have infinite engine cost; use a JSON-safe marker.
    cost: float | Literal["inf"]
    last_updated: datetime


class GraphStateResponse(BaseModel):
    nodes: list[NodeState]
    edges: list[EdgeState]


class RouteResponse(BaseModel):
    path: list[str]
    total_cost: float
    edge_statuses: list[str]
    rerouted: bool
    previous_path: list[str] | None = None


class AlertEvent(BaseModel):
    timestamp: datetime
    edge_id: str
    event_type: str
    old_status: str | None = None
    new_status: str
    message: str


class AlertsResponse(BaseModel):
    alerts: list[AlertEvent]
