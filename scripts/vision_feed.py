from __future__ import annotations

import argparse
import os
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from scripts.csrnet_infer import load_model, predict_density_map
from scripts.zones import ZoneConfig, compute_zone_density, load_zone_configs

API_BASE = os.getenv("RTPCC_API_BASE", "http://127.0.0.1:8000").rstrip("/")
REQUEST_TIMEOUT_SECONDS = 5.0
CONFIDENCE_WINDOW_SIZE = 3
MAX_JUMP_RATIO = 3.0
MAX_READ_RETRIES = 3
READ_RETRY_DELAY_SECONDS = 0.5

STATUS_LABELS = {
    "stampede": "STAMPEDE_RISK",
    "critical": "CRITICAL_BOTTLENECK",
    "high": "HIGH_DENSITY",
    "free": "FREE_FLOW",
}


def _classify(d: float) -> str:
    if d >= 5.0:
        return STATUS_LABELS["stampede"]
    if d >= 4.0:
        return STATUS_LABELS["critical"]
    if d >= 2.0:
        return STATUS_LABELS["high"]
    return STATUS_LABELS["free"]


def post_density(session: requests.Session, edge_id: str, density: float) -> bool:
    try:
        response = session.post(
            f"{API_BASE}/simulate/density",
            json={"edge_id": edge_id, "density": round(density, 2)},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return True
    except requests.RequestException as exc:
        print(f"  [POST ERROR] {edge_id}: {exc}")
        return False


def draw_zones(frame: np.ndarray, zones: list[ZoneConfig], readings: dict[str, float]) -> None:
    for zone in zones:
        pts = np.array(zone.polygon, dtype=np.int32).reshape((-1, 1, 2))
        d = readings.get(zone.edge_id, 0.0)
        status = _classify(d)
        if status == STATUS_LABELS["stampede"]:
            color = (0, 0, 255)
        elif status == STATUS_LABELS["critical"]:
            color = (0, 165, 255)
        elif status == STATUS_LABELS["high"]:
            color = (0, 255, 255)
        else:
            color = (0, 255, 0)
        cv2.polylines(frame, [pts], True, color, 3)
        moments = cv2.moments(pts)
        if moments["m00"] > 0:
            cx = int(moments["m10"] / moments["m00"])
            cy = int(moments["m01"] / moments["m00"])
        else:
            cx, cy = int(pts[0][0][0]), int(pts[0][0][1])
        label = f"{zone.edge_id} {d:.2f} p/m2 ({status})"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(frame, (cx - 2, cy - th - 4), (cx + tw + 2, cy + 2), (0, 0, 0), -1)
        cv2.putText(frame, label, (cx, cy - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Live video pipeline: CSRNet inference -> zone density -> POST to RTPCC API."
    )
    parser.add_argument("--source", required=True, help="Video file path or webcam index (e.g. 0)")
    parser.add_argument(
        "--weights",
        default=str(REPO_ROOT / "models/partBmodel_best.pth.tar"),
        help="CSRNet checkpoint path",
    )
    parser.add_argument(
        "--zones",
        default=str(REPO_ROOT / "config/zones_test.json"),
        help="Zone config JSON path",
    )
    parser.add_argument("--interval", type=float, default=2.0, help="Seconds between processed frames")
    parser.add_argument("--show", action="store_true", help="Display live frame with zone overlays")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    weights_path = Path(args.weights)
    if not weights_path.is_file():
        raise SystemExit(f"Weights not found: {weights_path}")

    zones_path = Path(args.zones)
    if not zones_path.is_file():
        raise SystemExit(f"Zone config not found: {zones_path}")

    print(f"Loading model from {weights_path}...")
    model = load_model(str(weights_path))

    print(f"Loading zone config from {zones_path}...")
    zones = load_zone_configs(str(zones_path))
    if not zones:
        raise SystemExit("Zone config is empty — define at least one zone polygon.")
    print(f"Loaded {len(zones)} zone(s): {', '.join(z.edge_id for z in zones)}")

    try:
        source = int(args.source)
        source_desc = f"webcam index {source}"
    except ValueError:
        source = args.source
        source_desc = source

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise SystemExit(f"Could not open video source: {source_desc}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0
    frames_per_tick = max(1, int(fps * args.interval))
    print(f"Video source: {source_desc} ({fps:.1f} fps, processing every {frames_per_tick} frame(s))")

    if args.show:
        window_name = "RTPCC Vision Feed"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    session = requests.Session()
    confidence_windows: dict[str, deque] = {z.edge_id: deque(maxlen=CONFIDENCE_WINDOW_SIZE) for z in zones}
    last_readings: dict[str, float] = {}
    frame_count = 0
    tick = 0
    consecutive_read_failures = 0

    print(f"Connected to {API_BASE}. Press Ctrl+C to stop.\n")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                consecutive_read_failures += 1
                if consecutive_read_failures >= MAX_READ_RETRIES:
                    print(f"Frame read failed after {MAX_READ_RETRIES} attempts — exiting.")
                    break
                time.sleep(READ_RETRY_DELAY_SECONDS)
                continue
            consecutive_read_failures = 0
            frame_count += 1

            if frame_count % frames_per_tick != 0:
                if args.show:
                    draw_zones(frame, zones, last_readings)
                    cv2.imshow(window_name, frame)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        print("\nStopped by user (q key).")
                        break
                continue

            tick += 1
            density_map = predict_density_map(model, frame)
            tick_readings: dict[str, float] = {}
            skipped: list[str] = []
            posted: list[str] = []

            for zone in zones:
                result = compute_zone_density(density_map, zone)
                raw_density = result["calibrated_density"]

                window = confidence_windows[zone.edge_id]
                window.append(raw_density)
                if len(window) >= CONFIDENCE_WINDOW_SIZE:
                    recent_avg = sum(window) / len(window)
                    if recent_avg > 0 and raw_density > recent_avg * MAX_JUMP_RATIO:
                        held = last_readings.get(zone.edge_id, raw_density)
                        skipped.append(f"{zone.edge_id}={raw_density:.2f}(hold={held:.2f})")
                        tick_readings[zone.edge_id] = held
                        continue

                tick_readings[zone.edge_id] = raw_density
                last_readings[zone.edge_id] = raw_density
                if post_density(session, zone.edge_id, raw_density):
                    posted.append(zone.edge_id)

            timestamp = datetime.now().strftime("%H:%M:%S")
            parts = []
            for zone in zones:
                d = tick_readings.get(zone.edge_id, last_readings.get(zone.edge_id, 0.0))
                status = _classify(d)
                parts.append(f"{zone.edge_id}={d:.2f}({status})")
            summary = " ".join(parts)
            print(f"[{timestamp}] tick={tick} {summary}")
            for skip_msg in skipped:
                print(f"  [SKIPPED] low-confidence reading for zone {skip_msg}")

            if args.show:
                draw_zones(frame, zones, tick_readings)
                cv2.imshow(window_name, frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    print("\nStopped by user (q key).")
                    break

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\nVision feed stopped cleanly.")
    finally:
        cap.release()
        if args.show:
            cv2.destroyAllWindows()
        session.close()


if __name__ == "__main__":
    main()
