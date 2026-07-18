"""Threshold and temporal smoothing logic for density-based crowd risk.

The key design goal is to avoid status flicker from a single noisy reading.
An edge only commits to a new status after three consecutive readings fall into
that same risk tier.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
from math import inf
from typing import Deque, Dict, List, Optional, Tuple


class EdgeStatus(str, Enum):
    FREE_FLOW = "FREE_FLOW"
    HIGH_DENSITY = "HIGH_DENSITY"
    CRITICAL_BOTTLENECK = "CRITICAL_BOTTLENECK"
    STAMPEDE_RISK = "STAMPEDE_RISK"


@dataclass(slots=True)
class DensityUpdateResult:
    """Outcome of a single density reading after smoothing is applied."""

    edge_id: str
    density: float
    raw_status: EdgeStatus
    committed_status: EdgeStatus
    committed: bool
    cost: float
    telemetry_warning: bool
    simulation_mode: bool
    blocked: bool
    reason: str


class DensityWindowTracker:
    """Track recent densities for a single edge and gate status changes.

    A status change only commits once the same tier appears three times in a row.
    The tracker keeps both the latest raw status and the currently committed one.
    """

    def __init__(self, window_size: int = 3) -> None:
        if window_size < 3:
            raise ValueError("window_size must be at least 3 for the smoothing rule")
        self.window_size = window_size
        self.recent_densities: Deque[float] = deque(maxlen=window_size)
        self._current_status: EdgeStatus = EdgeStatus.FREE_FLOW
        self._current_density: float = 0.0
        self._pending_status: Optional[EdgeStatus] = None
        self._pending_count: int = 0

    @staticmethod
    def classify_density(density: float) -> EdgeStatus:
        if density < 2.0:
            return EdgeStatus.FREE_FLOW
        if density < 4.0:
            return EdgeStatus.HIGH_DENSITY
        if density < 5.0:
            return EdgeStatus.CRITICAL_BOTTLENECK
        return EdgeStatus.STAMPEDE_RISK

    @staticmethod
    def compute_cost(base_distance: float, density: float) -> float:
        status = DensityWindowTracker.classify_density(density)
        if status == EdgeStatus.FREE_FLOW:
            return base_distance
        if status == EdgeStatus.HIGH_DENSITY:
            return base_distance * (1 + 0.3 * density)
        if status == EdgeStatus.CRITICAL_BOTTLENECK:
            return base_distance * (1 + 0.8 * density)
        return inf

    def update(self, density: float, base_distance: float) -> Tuple[EdgeStatus, float, bool, EdgeStatus, str, bool, bool]:
        """Process a new raw density reading.

        Returns a tuple containing:
        committed_status, committed_cost, committed_now, raw_status, reason,
        telemetry_warning, simulation_mode
        """

        self.recent_densities.append(density)
        raw_status = self.classify_density(density)

        committed_now = False
        reason = "status held by smoothing window"

        if raw_status == self._current_status:
            self._pending_status = None
            self._pending_count = 0
            self._current_density = density
            committed_cost = self.compute_cost(base_distance, density)
            telemetry_warning = raw_status == EdgeStatus.HIGH_DENSITY
            simulation_mode = raw_status == EdgeStatus.CRITICAL_BOTTLENECK
            return (
                self._current_status,
                committed_cost,
                committed_now,
                raw_status,
                reason,
                telemetry_warning,
                simulation_mode,
            )

        if self._pending_status == raw_status:
            self._pending_count += 1
        else:
            self._pending_status = raw_status
            self._pending_count = 1

        if self._pending_count >= self.window_size:
            self._current_status = raw_status
            self._current_density = density
            self._pending_status = None
            self._pending_count = 0
            committed_now = True
            reason = f"committed after {self.window_size} consecutive {raw_status.value} readings"
        else:
            density = self._current_density

        committed_cost = self.compute_cost(base_distance, density)
        telemetry_warning = self._current_status == EdgeStatus.HIGH_DENSITY
        simulation_mode = self._current_status == EdgeStatus.CRITICAL_BOTTLENECK
        return (
            self._current_status,
            committed_cost,
            committed_now,
            raw_status,
            reason,
            telemetry_warning,
            simulation_mode,
        )


class RiskThresholdEngine:
    """Apply the threshold rules and smoothing state per edge."""

    def __init__(self, window_size: int = 3) -> None:
        self.window_size = window_size
        self._trackers: Dict[str, DensityWindowTracker] = {}

    def _tracker_for(self, edge_id: str) -> DensityWindowTracker:
        tracker = self._trackers.get(edge_id)
        if tracker is None:
            tracker = DensityWindowTracker(window_size=self.window_size)
            self._trackers[edge_id] = tracker
        return tracker

    def update_edge_density(self, edge_id: str, density: float, base_distance: float) -> DensityUpdateResult:
        tracker = self._tracker_for(edge_id)
        committed_status, committed_cost, committed_now, raw_status, reason, telemetry_warning, simulation_mode = tracker.update(
            density=density,
            base_distance=base_distance,
        )
        blocked = committed_status == EdgeStatus.STAMPEDE_RISK
        return DensityUpdateResult(
            edge_id=edge_id,
            density=density,
            raw_status=raw_status,
            committed_status=committed_status,
            committed=committed_now,
            cost=committed_cost,
            telemetry_warning=telemetry_warning,
            simulation_mode=simulation_mode,
            blocked=blocked,
            reason=reason,
        )

    @staticmethod
    def summarize_result(result: DensityUpdateResult) -> str:
        details: List[str] = [
            f"edge={result.edge_id}",
            f"density={result.density:.2f}",
            f"raw={result.raw_status.value}",
            f"committed={result.committed_status.value}",
            f"cost={'inf' if result.cost == inf else f'{result.cost:.2f}'}",
        ]
        if result.committed:
            details.append("commit=yes")
        if result.telemetry_warning:
            details.append("telemetry=warn")
        if result.simulation_mode:
            details.append("simulation_mode=on")
        if result.blocked:
            details.append("blocked=yes")
        return ", ".join(details)
