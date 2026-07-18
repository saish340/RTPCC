"""Live density simulator for the RTPCC FastAPI backend.

This script nudges a small set of venue edges over time and POSTs the updates
to the running API server. It also queries the current route so a reroute can
be observed from the terminal while the simulation runs.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from dataclasses import dataclass
from typing import Any, Iterable
from urllib import error, parse, request


@dataclass(slots=True)
class EdgeState:
    edge_id: str
    density: float


def http_json(method: str, url: str, payload: dict[str, Any] | None = None, timeout: float = 5.0) -> Any:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else None
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed: {exc.code} {body}") from exc


def clamp(value: float, lower: float = 0.0, upper: float = 6.0) -> float:
    return max(lower, min(upper, value))


def choose_edges(graph_payload: dict[str, Any], preferred: Iterable[str]) -> list[str]:
    available = {edge["id"] for edge in graph_payload.get("edges", [])}
    chosen = [edge_id for edge_id in preferred if edge_id in available]
    if chosen:
        return chosen
    return sorted(available)[:3]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the RTPCC density simulator against a live API.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Base URL of the FastAPI server")
    parser.add_argument("--start", default="n1", help="Start node for route checks")
    parser.add_argument("--end", default="n6", help="End node for route checks")
    parser.add_argument("--interval", type=float, default=2.0, help="Seconds between update batches")
    parser.add_argument("--steps", type=int, default=0, help="Number of batches to run; 0 runs until interrupted")
    parser.add_argument("--seed", type=int, default=7, help="Random seed for repeatable walks")
    parser.add_argument(
        "--edges",
        nargs="*",
        default=["e6", "e5", "e4", "e3"],
        help="Preferred edge IDs to simulate",
    )
    args = parser.parse_args()

    random.seed(args.seed)
    venue = http_json("GET", f"{args.base_url}/venue/graph")
    edge_ids = choose_edges(venue, args.edges)
    if not edge_ids:
        raise SystemExit("No edges available from /venue/graph")

    states = [EdgeState(edge_id=edge_id, density=random.uniform(0.8, 2.2)) for edge_id in edge_ids]
    previous_alert_count = 0
    batch = 0
    surge_remaining = 0

    print(f"Using edges: {', '.join(edge_ids)}")
    print(f"Monitoring route: {args.start} -> {args.end}")
    print("Press Ctrl+C to stop.\n")

    while True:
        batch += 1
        print(f"Batch {batch}")
        if surge_remaining == 0 and batch % 6 == 0:
            surge_remaining = 3
            print(f"  Surge starting on {states[0].edge_id}")

        for index, state in enumerate(states):
            drift = random.uniform(-0.35, 0.6)
            if index == 0 and surge_remaining > 0:
                next_density = random.uniform(5.0, 5.6)
            else:
                next_density = clamp(state.density + drift)

            state.density = next_density
            response = http_json(
                "POST",
                f"{args.base_url}/simulate/density",
                {"edge_id": state.edge_id, "density": round(state.density, 2)},
            )
            edge = response["edge"]
            print(
                f"  {edge['id']}: density={edge['current_density']:.2f} "
                f"status={edge['current_status']} cost={edge['current_cost']}"
            )

        if surge_remaining > 0:
            surge_remaining -= 1

        route = http_json("GET", f"{args.base_url}/route?{parse.urlencode({'start': args.start, 'end': args.end})}")
        if route.get("rerouted"):
            print(f"  Route rerouted: {route['route']} cost={route['total_cost']} reason={route['reroute_reason']}")
        else:
            print(f"  Route: {route['route']} cost={route['total_cost']}")

        alerts = http_json("GET", f"{args.base_url}/alerts")
        alert_count = len(alerts.get("alerts", []))
        if alert_count > previous_alert_count:
            for alert in alerts["alerts"][previous_alert_count:alert_count]:
                details = alert.get("details", {})
                print(f"  Alert: {alert['event_type']} - {alert['message']} ({details})")
            previous_alert_count = alert_count

        print()

        if args.steps and batch >= args.steps:
            break

        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
