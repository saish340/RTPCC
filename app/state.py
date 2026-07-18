"""Shared in-memory state for the RTPCC API."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from rtpcc.service import CrowdSafetyService


service = CrowdSafetyService()
alerts: list[dict] = []
last_routes: dict[tuple[str, str], dict] = {}
edge_updated_at: dict[str, datetime] = {
    edge.id: datetime.now(timezone.utc) for edge in service.venue.edges
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
