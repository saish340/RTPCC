"""Hardcoded venue graph model for the RTPCC simulation prototype.

This module keeps the venue definition intentionally small and explicit so the
Step 1 threshold engine can be exercised without any API or routing layer.
"""

from __future__ import annotations

from typing import Dict, List, Literal

from math import inf

from pydantic import BaseModel, Field, field_serializer

NodeType = Literal["entry", "exit", "junction"]


class Node(BaseModel):
    """A venue node representing an entry, exit, or junction."""

    id: str
    name: str
    type: NodeType


class Edge(BaseModel):
    """A corridor or path between two nodes in the venue graph."""

    id: str
    from_node: str = Field(alias="from_node")
    to_node: str = Field(alias="to_node")
    base_distance: float
    current_density: float = 0.0
    current_status: str = "FREE_FLOW"
    current_cost: float = 0.0
    is_blocked: bool = False

    model_config = {"populate_by_name": True}

    @field_serializer("current_cost")
    def serialize_current_cost(self, value: float) -> float | str:
        return "inf" if value == inf else value


class VenueGraph(BaseModel):
    """A small venue graph with the current operational state of each edge."""

    nodes: List[Node]
    edges: List[Edge]

    def get_edge(self, edge_id: str) -> Edge:
        for edge in self.edges:
            if edge.id == edge_id:
                return edge
        raise KeyError(f"Unknown edge_id: {edge_id}")

    def get_node(self, node_id: str) -> Node:
        for node in self.nodes:
            if node.id == node_id:
                return node
        raise KeyError(f"Unknown node_id: {node_id}")

    def snapshot(self) -> Dict[str, List[dict]]:
        """Return a JSON-friendly snapshot of the venue state."""

        return {
            "nodes": [node.model_dump() for node in self.nodes],
            "edges": [edge.model_dump(by_alias=True) for edge in self.edges],
        }


def build_sample_venue_graph() -> VenueGraph:
    """Create a compact hardcoded venue graph for simulation and testing."""

    nodes = [
        Node(id="n1", name="Main Entrance", type="entry"),
        Node(id="n2", name="Lobby Junction", type="junction"),
        Node(id="n3", name="North Corridor", type="junction"),
        Node(id="n4", name="Atrium", type="junction"),
        Node(id="n5", name="South Corridor", type="junction"),
        Node(id="n6", name="Emergency Exit A", type="exit"),
        Node(id="n7", name="Emergency Exit B", type="exit"),
    ]

    edges = [
        Edge(id="e1", from_node="n1", to_node="n2", base_distance=12.0),
        Edge(id="e2", from_node="n2", to_node="n3", base_distance=10.0),
        Edge(id="e3", from_node="n3", to_node="n4", base_distance=9.0),
        Edge(id="e4", from_node="n4", to_node="n5", base_distance=11.0),
        Edge(id="e5", from_node="n5", to_node="n6", base_distance=8.0),
        Edge(id="e6", from_node="n4", to_node="n6", base_distance=14.0),
        Edge(id="e7", from_node="n2", to_node="n4", base_distance=15.0),
        Edge(id="e8", from_node="n3", to_node="n7", base_distance=16.0),
        Edge(id="e9", from_node="n5", to_node="n7", base_distance=13.0),
    ]

    return VenueGraph(nodes=nodes, edges=edges)
