"""Generate live-looking density sensor data for a running RTPCC API.

Run ``python scripts/simulate.py --demo-route n1 n6`` after starting Uvicorn.
The simulator discovers edges from ``/venue/graph`` rather than depending on a
specific venue topology.
"""

from __future__ import annotations

import argparse
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime

import requests


API_BASE = os.getenv("RTPCC_API_BASE", "http://127.0.0.1:8000").rstrip("/")
TICK_INTERVAL_SECONDS = 2.0
REQUEST_TIMEOUT_SECONDS = 5.0
MEANINGFUL_CHANGE = 0.05


@dataclass(slots=True)
class SimulatedEdge:
    edge_id: str
    density: float
    last_sent_density: float | None = None
    status: str = "FREE_FLOW"


@dataclass(slots=True)
class Surge:
    edge_id: str
    phase: str = "ramp"
    ramp_ticks_remaining: int = 0
    decay_ticks_remaining: int = 0


def clamp(value: float, minimum: float = 0.0, maximum: float = 7.0) -> float:
    return max(minimum, min(maximum, value))


def fetch_graph(session: requests.Session, base_url: str) -> dict:
    response = session.get(f"{base_url}/venue/graph", timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def post_density(session: requests.Session, base_url: str, edge: SimulatedEdge) -> dict:
    response = session.post(
        f"{base_url}/simulate/density",
        json={"edge_id": edge.edge_id, "density": round(edge.density, 2)},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send live density simulation data to the RTPCC API.")
    parser.add_argument("--base-url", default=API_BASE, help="API base URL (default: RTPCC_API_BASE or localhost)")
    parser.add_argument("--interval", type=float, default=TICK_INTERVAL_SECONDS, help="Seconds between ticks")
    parser.add_argument("--ticks", type=int, default=0, help="Number of ticks to run; 0 means until Ctrl+C")
    parser.add_argument("--seed", type=int, help="Optional seed for a repeatable demo")
    parser.add_argument(
        "--demo-route",
        nargs=2,
        metavar=("START", "END"),
        help="Poll and print the recommended route between these node IDs each tick",
    )
    return parser.parse_args()


def start_surge(edges: list[SimulatedEdge], rng: random.Random) -> Surge:
    selected = rng.choice(edges)
    surge = Surge(edge_id=selected.edge_id, ramp_ticks_remaining=rng.randint(4, 6))
    print(f"[SURGE START] edge {surge.edge_id} -> ramping density")
    return surge


def advance_density(edge: SimulatedEdge, surge: Surge | None, rng: random.Random) -> None:
    """Apply either ordinary random drift or the active surge behaviour."""
    if surge is None or edge.edge_id != surge.edge_id:
        edge.density = clamp(edge.density + rng.gauss(0.0, 0.3))
        return

    if surge.phase == "ramp":
        edge.density = clamp(edge.density + rng.uniform(1.5, 2.5))
        surge.ramp_ticks_remaining -= 1
        # Keep the ramp at its peak until its scheduled end.  This guarantees
        # several consecutive STAMPEDE_RISK readings for the API's 3-reading
        # smoothing window before the simulated crowd disperses.
        if surge.ramp_ticks_remaining == 0:
            surge.phase = "decay"
            surge.decay_ticks_remaining = rng.randint(5, 8)
            print(f"[SURGE END] edge {surge.edge_id} -> decaying")
    else:
        edge.density = clamp(edge.density - rng.uniform(0.65, 1.15))
        surge.decay_ticks_remaining -= 1


def poll_route(
    session: requests.Session,
    base_url: str,
    start: str,
    end: str,
    previous_path: list[str] | None,
    active_surge: Surge | None,
) -> list[str] | None:
    try:
        response = session.get(
            f"{base_url}/route",
            params={"start": start, "end": end},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        route = response.json()
    except requests.RequestException as exc:
        print(f"  [ROUTE ERROR] {exc}")
        return previous_path

    path = route["path"]
    display = " -> ".join(path)
    if previous_path is not None and path != previous_path:
        old_display = " -> ".join(previous_path)
        cause = active_surge.edge_id if active_surge else "a density update"
        print(f"  !!! REROUTE TRIGGERED: {old_display} -> {display} due to {cause}")
    else:
        print(f"  Route: {display} (cost {route['total_cost']:.1f})")
    return path


def main() -> None:
    args = parse_args()
    if args.interval <= 0:
        raise SystemExit("--interval must be greater than zero")
    if args.ticks < 0:
        raise SystemExit("--ticks cannot be negative")

    base_url = args.base_url.rstrip("/")
    rng = random.Random(args.seed)
    session = requests.Session()
    try:
        graph = fetch_graph(session, base_url)
    except requests.RequestException as exc:
        print(f"Could not reach RTPCC API at {base_url}: {exc}")
        print("Start it first with: python -m uvicorn app.main:app --reload")
        return

    edges = [
        SimulatedEdge(edge_id=item["edge_id"], density=rng.uniform(0.5, 1.5), status=item["status"])
        for item in graph.get("edges", [])
    ]
    if not edges:
        print("The API returned a graph with no edges; nothing to simulate.")
        return

    print(f"Connected to {base_url}; simulating {len(edges)} discovered edges.")
    if args.demo_route:
        print(f"Demo route: {args.demo_route[0]} -> {args.demo_route[1]}")
    print("Press Ctrl+C to stop.\n")

    tick = 0
    next_surge_tick = rng.randint(15, 20)
    active_surge: Surge | None = None
    previous_path: list[str] | None = None

    try:
        while args.ticks == 0 or tick < args.ticks:
            tick += 1
            if active_surge is None and tick >= next_surge_tick:
                active_surge = start_surge(edges, rng)
                next_surge_tick = tick + rng.randint(15, 20)

            for edge in edges:
                advance_density(edge, active_surge, rng)
                if edge.last_sent_density is not None and abs(edge.density - edge.last_sent_density) < MEANINGFUL_CHANGE:
                    continue
                try:
                    result = post_density(session, base_url, edge)
                    edge.last_sent_density = edge.density
                    edge.status = result["status"]
                except requests.RequestException as exc:
                    print(f"  [POST ERROR] {edge.edge_id}: {exc}")

            summary = " ".join(
                f"{edge.edge_id}={edge.density:.1f}({edge.status}){'*' if active_surge and edge.edge_id == active_surge.edge_id else ''}"
                for edge in edges
            )
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {summary}")

            if args.demo_route:
                previous_path = poll_route(
                    session, base_url, args.demo_route[0], args.demo_route[1], previous_path, active_surge
                )

            if active_surge and active_surge.phase == "decay" and active_surge.decay_ticks_remaining <= 0:
                print(f"[SURGE COMPLETE] edge {active_surge.edge_id} returned to normal drift\n")
                active_surge = None

            if args.ticks == 0 or tick < args.ticks:
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nSimulation stopped cleanly.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
