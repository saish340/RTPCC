"""FastAPI application for the RTPCC simulation prototype."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .service import CrowdSafetyService

app = FastAPI(title="RTPCC API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

service = CrowdSafetyService()


class DensityUpdateRequest(BaseModel):
    edge_id: str = Field(..., examples=["e3"])
    density: float = Field(..., ge=0.0, examples=[2.4])


class RouteResponse(BaseModel):
    start: str
    end: str
    route: list[str]
    total_cost: float
    rerouted: bool
    reroute_reason: str = ""


@app.post("/simulate/density")
def simulate_density(payload: DensityUpdateRequest) -> Dict[str, Any]:
    try:
        return service.update_density(edge_id=payload.edge_id, density=payload.density)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/venue/graph")
def venue_graph() -> Dict[str, Any]:
    return service.graph_snapshot()


@app.get("/route", response_model=RouteResponse)
def route(start: str, end: str) -> Dict[str, Any]:
    try:
        return service.get_route(start=start, end=end)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/alerts")
def alerts() -> Dict[str, Any]:
    return {"alerts": service.alert_log()}


__all__ = ["app", "service"]