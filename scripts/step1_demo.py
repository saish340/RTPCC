"""Small console demo for the Step 1 venue and risk engine.

Run this script to see density readings transition through the threshold tiers.
The output intentionally includes both raw status and committed status so it is
clear when the smoothing window has accepted a change.
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rtpcc.risk import RiskThresholdEngine
from rtpcc.venue import build_sample_venue_graph


def main() -> None:
    venue = build_sample_venue_graph()
    engine = RiskThresholdEngine(window_size=3)

    edge_id = "e3"
    edge = venue.get_edge(edge_id)
    readings = [1.2, 1.4, 1.6, 2.3, 2.4, 2.5, 4.2, 4.3, 4.1, 5.4, 5.2, 5.1]

    print("Venue nodes:")
    for node in venue.nodes:
        print(f"  {node.id}: {node.name} ({node.type})")

    print(f"\nTesting edge {edge_id} ({edge.from_node} -> {edge.to_node}) with base distance {edge.base_distance}")
    print("density | raw status | committed status | cost | notes")
    print("-" * 72)

    for density in readings:
        result = engine.update_edge_density(edge_id=edge_id, density=density, base_distance=edge.base_distance)
        print(
            f"{density:>6.2f} | {result.raw_status.value:<18} | {result.committed_status.value:<20} | "
            f"{('inf' if result.cost == float('inf') else f'{result.cost:.2f}'):>8} | {result.reason}"
        )

    print("\nInterpretation:")
    print("- The raw status changes immediately with each density reading.")
    print("- The committed status only changes after three consecutive readings in a new tier.")
    print("- STAMPEDE_RISK commits to infinity cost and marks the edge as blocked.")


if __name__ == "__main__":
    main()
