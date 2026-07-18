"""Quick API smoke test for the RTPCC FastAPI backend.

This script uses only the Python standard library so it can run in a clean
environment without installing requests.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from urllib import parse, request


BASE_URL = os.getenv("RTPCC_API_BASE", "http://127.0.0.1:8000")


def http_json(method: str, path: str, payload: dict | None = None):
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
    with request.urlopen(req) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    graph = http_json("GET", "/venue/graph")
    print("Initial graph nodes:", len(graph["nodes"]))
    print("Initial graph edges:", len(graph["edges"]))

    route_before = http_json("GET", "/route?" + parse.urlencode({"start": "n1", "end": "n6"}))
    print("Route before:", route_before)

    for _ in range(3):
        update = http_json("POST", "/simulate/density", {"edge_id": "e6", "density": 5.4})
        print("Update:", update["edge_id"], update["status"], update["cost"])

    route_after = http_json("GET", "/route?" + parse.urlencode({"start": "n1", "end": "n6"}))
    print("Route after:", route_after)

    alerts = http_json("GET", "/alerts")
    print("Alerts:")
    for alert in alerts["alerts"]:
        print(alert)

    statuses = {event["event_type"] for event in alerts["alerts"]}
    assert "STATUS_CHANGE" in statuses, "Expected STATUS_CHANGE alert"
    assert "REROUTE" in statuses, "Expected REROUTE alert"
    assert route_before["path"] != route_after["path"], "Expected reroute to change the path"

    print("Smoke test passed at", datetime.now(timezone.utc).isoformat())


if __name__ == "__main__":
    main()
