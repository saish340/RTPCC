"""Venue graph endpoint."""

from __future__ import annotations

from math import inf

from fastapi import APIRouter

from app.models import GraphStateResponse, NodeState, EdgeState
from app.state import edge_updated_at, service

router = APIRouter(tags=["venue"])


@router.get("/venue/graph", response_model=GraphStateResponse)
def get_venue_graph() -> GraphStateResponse:
    nodes = [NodeState.model_validate(node.model_dump()) for node in service.venue.nodes]
    edges = []
    for edge in service.venue.edges:
        edges.append(
            EdgeState(
                edge_id=edge.id,
                from_node=edge.from_node,
                to_node=edge.to_node,
                base_distance=edge.base_distance,
                current_density=edge.current_density,
                status=edge.current_status,
                cost="inf" if edge.current_cost == inf else edge.current_cost,
                last_updated=edge_updated_at[edge.id],
            )
        )
    return GraphStateResponse(nodes=nodes, edges=edges)
