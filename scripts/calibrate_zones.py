from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np


_POINTS: list[tuple[int, int]] = []
_DRAGGING = False
_IMAGE: np.ndarray | None = None


def _mouse_callback(event: int, x: int, y: int, flags: int, param: object) -> None:
    global _POINTS, _DRAGGING, _IMAGE
    if event == cv2.EVENT_LBUTTONDOWN:
        _POINTS.append((x, y))
        _DRAGGING = True
        _redraw()
    elif event == cv2.EVENT_MOUSEMOVE and _DRAGGING and _POINTS:
        img = _IMAGE.copy()
        pts = _POINTS + [(x, y)]
        _draw_overlay(img, pts)
        cv2.imshow("Zone Calibration", img)
    elif event == cv2.EVENT_LBUTTONUP:
        _DRAGGING = False
        _redraw()
    elif event == cv2.EVENT_RBUTTONDOWN:
        if _POINTS:
            _POINTS.pop()
            _redraw()


def _draw_overlay(img: np.ndarray, pts: list[tuple[int, int]]) -> None:
    for i, (px, py) in enumerate(pts):
        cv2.circle(img, (px, py), 5, (0, 0, 255), -1)
        if i > 0:
            cv2.line(img, pts[i - 1], (px, py), (0, 255, 0), 2)
    if len(pts) >= 3:
        poly = np.array(pts, dtype=np.int32).reshape((-1, 1, 2))
        overlay = img.copy()
        cv2.fillPoly(overlay, [poly], (0, 255, 0))
        cv2.addWeighted(overlay, 0.25, img, 0.75, 0, img)
        cv2.polylines(img, [poly], True, (0, 255, 0), 2)


def _redraw() -> None:
    global _IMAGE
    if _IMAGE is None:
        return
    img = _IMAGE.copy()
    _draw_overlay(img, _POINTS)
    cv2.imshow("Zone Calibration", img)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Click to define zone polygons for zone mapping calibration. "
        "Left-click to add points, right-click to undo last point. "
        "Press Enter/Space when done, Esc to cancel."
    )
    parser.add_argument("--image", required=True, help="Image path to calibrate against")
    parser.add_argument(
        "--output",
        default="config/zones.json",
        help="Output JSON path for zone configs (default: config/zones.json)",
    )
    parser.add_argument(
        "--density-map",
        help="Optional: path to a saved .npy density map to compute zone densities inline",
    )
    args = parser.parse_args()

    global _IMAGE, _POINTS

    _IMAGE = cv2.imread(args.image, cv2.IMREAD_COLOR)
    if _IMAGE is None:
        raise SystemExit(f"Could not read image: {args.image}")

    cv2.namedWindow("Zone Calibration")
    cv2.setMouseCallback("Zone Calibration", _mouse_callback)
    _redraw()
    print(f"Image: {args.image} ({_IMAGE.shape[1]}x{_IMAGE.shape[0]})")
    print("Left-click to add polygon vertices | Right-click to undo last | Enter/Space to finish | Esc to cancel")

    while True:
        key = cv2.waitKey(20) & 0xFF
        if key in (13, 32):
            break
        if key == 27:
            _POINTS = []
            break

    cv2.destroyAllWindows()

    if len(_POINTS) < 3:
        print("Cancelled — need at least 3 points for a polygon.")
        return

    print(f"\nPolygon vertices ({len(_POINTS)} points):")
    coord_str = json.dumps([[float(x), float(y)] for x, y in _POINTS])
    print(coord_str)

    edge_id = input("Edge ID (e.g. e1): ").strip()
    label = input("Zone label (e.g. Main Concourse): ").strip()
    area_m2_str = input("Area in m²: ").strip()
    try:
        area_m2 = float(area_m2_str)
    except ValueError:
        print("Invalid area, defaulting to 100.0")
        area_m2 = 100.0

    cal_str = input("Calibration factor (default 0.055 ≈ 1/18 for CSRNet overcount): ").strip()
    calibration_factor = float(cal_str) if cal_str else 0.055

    output_path = Path(args.output)
    existing_zones: list[dict] = []
    if output_path.is_file():
        existing_zones = json.loads(output_path.read_text(encoding="utf-8"))

    new_zone = {
        "edge_id": edge_id,
        "polygon": [[float(x), float(y)] for x, y in _POINTS],
        "area_m2": area_m2,
        "calibration_factor": calibration_factor,
        "label": label,
    }
    existing_zones.append(new_zone)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(existing_zones, indent=2), encoding="utf-8")
    print(f"\nZone saved to {output_path.resolve()}")

    if args.density_map:
        from scripts.zones import ZoneConfig, compute_zone_density

        dm = np.load(args.density_map)
        cfg = ZoneConfig(**new_zone)
        result = compute_zone_density(dm, cfg)
        print(f"\nDensity result for {edge_id} ({label}):")
        for k, v in result.items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
