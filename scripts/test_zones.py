from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from scripts.csrnet_infer import load_model, predict_density_map
from scripts.zones import ZoneConfig, compute_zone_density, save_zone_configs


def main() -> None:
    image_path = REPO_ROOT / "data/test_images/test 1.jpg"
    weights_path = REPO_ROOT / "models/partBmodel_best.pth.tar"
    overlay_output = REPO_ROOT / "artifacts/csrnet_overlay_overhead.png"

    if not image_path.is_file():
        raise SystemExit(f"Image not found: {image_path}")
    if not weights_path.is_file():
        raise SystemExit(f"Weights not found: {weights_path}")

    print(f"Loading model from {weights_path}...")
    model = load_model(str(weights_path))

    print(f"Loading image {image_path} ({cv2.imread(str(image_path)).shape[1]}x{cv2.imread(str(image_path)).shape[0]})...")
    frame = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if frame is None:
        raise SystemExit("Could not read image")

    print("Computing density map...")
    density_map = predict_density_map(model, frame)
    print(f"Density map shape: {density_map.shape}, total sum: {density_map.sum():.2f}")

    height, width = frame.shape[:2]

    zones = [
        ZoneConfig(
            edge_id="e1",
            label="Central dense cluster",
            polygon=[
                [width * 0.35, height * 0.30],
                [width * 0.65, height * 0.30],
                [width * 0.65, height * 0.60],
                [width * 0.35, height * 0.60],
            ],
            area_m2=120.0,
            calibration_factor=0.055,
        ),
        ZoneConfig(
            edge_id="e2",
            label="Mid-left corridor",
            polygon=[
                [width * 0.05, height * 0.20],
                [width * 0.25, height * 0.20],
                [width * 0.25, height * 0.70],
                [width * 0.05, height * 0.70],
            ],
            area_m2=200.0,
            calibration_factor=0.055,
        ),
        ZoneConfig(
            edge_id="e3",
            label="Top-right periphery",
            polygon=[
                [width * 0.70, height * 0.05],
                [width * 0.95, height * 0.05],
                [width * 0.95, height * 0.30],
                [width * 0.70, height * 0.30],
            ],
            area_m2=180.0,
            calibration_factor=0.055,
        ),
    ]

    print(f"\nImage: {width}x{height}")
    print(f"CSRNet raw count (full frame): {density_map.sum():.2f}")
    print(f"{'Zone':<25} {'Raw sum':<12} {'Area m²':<10} {'p/m² raw':<12} {'Cal factor':<10} {'p/m² cal':<10}")
    print("-" * 85)

    for zone in zones:
        result = compute_zone_density(density_map, zone)
        print(
            f"{result['label']:<25} "
            f"{result['raw_sum']:<12.2f} "
            f"{result['area_m2']:<10.1f} "
            f"{result['density_per_m2']:<12.2f} "
            f"{result['calibration_factor']:<10.3f} "
            f"{result['calibrated_density']:<10.2f}"
        )

    save_zone_configs(REPO_ROOT / "config/zones_test.json", zones)
    print(f"\nZone config saved to config/zones_test.json")

    print("\nCalibrated density readings ready to POST to /simulate/density:")
    for zone in zones:
        result = compute_zone_density(density_map, zone)
        d = result["calibrated_density"]
        print(f"  POST /simulate/density {{edge_id: {result['edge_id']}, density: {d:.2f}}}")
        print(f"    -> status: {'FREE_FLOW' if d < 2.0 else 'HIGH_DENSITY' if d < 4.0 else 'CRITICAL_BOTTLENECK' if d < 5.0 else 'STAMPEDE_RISK'}")


if __name__ == "__main__":
    main()
