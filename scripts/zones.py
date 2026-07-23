from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np


@dataclass
class ZoneConfig:
    edge_id: str
    polygon: list[list[float]]
    area_m2: float
    calibration_factor: float = 1.0
    label: str = ""


def load_zone_configs(path: str | Path) -> list[ZoneConfig]:
    import json

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    zones = []
    for item in data:
        cfg = ZoneConfig(
            edge_id=item["edge_id"],
            polygon=item["polygon"],
            area_m2=item["area_m2"],
            calibration_factor=item.get("calibration_factor", 1.0),
            label=item.get("label", ""),
        )
        zones.append(cfg)
    return zones


def save_zone_configs(path: str | Path, zones: list[ZoneConfig]) -> None:
    import json

    data: list[dict[str, Any]] = []
    for z in zones:
        data.append({
            "edge_id": z.edge_id,
            "polygon": z.polygon,
            "area_m2": z.area_m2,
            "calibration_factor": z.calibration_factor,
            "label": z.label,
        })
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def compute_zone_density(
    density_map: np.ndarray,
    zone: ZoneConfig,
) -> dict[str, float]:
    if density_map.ndim != 2:
        raise ValueError(f"density_map must be 2D (HxW), got shape {density_map.shape}")
    height, width = density_map.shape[:2]

    mask = np.zeros((height, width), dtype=np.uint8)
    pts = np.array(zone.polygon, dtype=np.int32).reshape((-1, 1, 2))
    cv2.fillPoly(mask, [pts], 1)

    raw_sum = float(density_map[mask == 1].sum())
    density_per_m2 = raw_sum / zone.area_m2 if zone.area_m2 > 0 else 0.0
    calibrated_density = density_per_m2 * zone.calibration_factor

    return {
        "edge_id": zone.edge_id,
        "label": zone.label,
        "raw_sum": raw_sum,
        "area_m2": zone.area_m2,
        "density_per_m2": density_per_m2,
        "calibration_factor": zone.calibration_factor,
        "calibrated_density": calibrated_density,
    }
