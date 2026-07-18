"""Alert retrieval endpoint."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter

from app.models import AlertsResponse, AlertEvent
from app.state import alerts

router = APIRouter(tags=["alerts"])


@router.get("/alerts", response_model=AlertsResponse)
def get_alerts(since: datetime | None = None) -> AlertsResponse:
    events = [AlertEvent.model_validate(item) for item in reversed(alerts)]
    if since is not None:
        events = [event for event in events if event.timestamp > since]
    return AlertsResponse(alerts=events)
