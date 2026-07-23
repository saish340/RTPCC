# RTPCC — Real-Time Predictive Crowd Control

A simulation-first crowd-safety pipeline built as a final-year engineering project. Models the full flow: crowd density → risk analytics → dynamic route rerouting → simulated signage/alerts.

## System Architecture

```
Video Feed / Simulator  →  CSRNet Density Map  →  Zone Aggregation  →  Risk Engine  →  Route Recompute  →  Dashboard
```

| Layer | Technology | Purpose |
|---|---|---|
| **Density Estimation** | CSRNet (PyTorch) | Predicts crowd-density heatmap from overhead video |
| **Zone Mapping** | OpenCV polygon masking | Sums density per venue zone, applies calibration factor |
| **Risk Engine** | Python (custom smoothing) | 4-tier threshold logic with 3-reading temporal smoothing |
| **Routing** | NetworkX (Dijkstra/A*) | Shortest-path by dynamic cost; auto-reroute on blocked edges |
| **API** | FastAPI + Pydantic | REST endpoints for graph state, density updates, routes, alerts |
| **Dashboard** | HTML/CSS/JS + Lucide icons | Dark command-center UI with live graph, alerts, trend chart |
| **Simulator** | Python (requests) | Random-walk density generator for testing without video |

## Venue Floor Plan

```
                                    ┌──────────────┐
                                    │ n7 · Exit B  │
                                    │  (Emergency) │
                                    └──────┬───────┘
                                           │ e8
              ┌──────────────┐    ┌────────┴────────┐    ┌──────────────┐
              │ n3 · North   │ e3 │   n4 · Atrium   │ e6 │  n6 · Exit A │
              │   Corridor   ├────┤   (Central Hub) ├────┤  (Emergency) │
              └──────┬───────┘    └────────┬────────┘    └──────────────┘
                     │ e2                  │ e7                  │ e5
              ┌──────┴───────┐    ┌────────┴────────┐    ┌──────┴───────┐
              │ n2 · Lobby   │ e4 │   n5 · South    │ e9 │  n7 · Exit B │
              │   Junction   ├────┤   Corridor      ├────┤  (Emergency) │
              └──────┬───────┘    └─────────────────┘    └──────────────┘
                     │ e1
              ┌──────┴───────┐
              │ n1 · Main    │
              │   Entrance   │
              └──────────────┘
```

- 7 nodes (1 entry, 2 exits, 4 junctions) connected by 9 bi-directional edges
- Each edge has a `base_distance` (m) and dynamically computed `cost` based on density

## Risk Threshold Logic

| Density (p/m²) | Status | Cost Formula | Effect |
|---|---|---|---|
| D < 2.0 | FREE_FLOW | `base_distance` | Normal routing |
| 2.0 ≤ D < 4.0 | HIGH_DENSITY | `base_distance × (1 + 0.3×D)` | Telemetry warning logged |
| 4.0 ≤ D < 5.0 | CRITICAL_BOTTLENECK | `base_distance × (1 + 0.8×D)` | Simulation-mode flag |
| D ≥ 5.0 | STAMPEDE_RISK | ∞ (blocked) | Edge excluded from graph → reroute |

Status changes only commit after **3 consecutive readings** in the same tier (temporal smoothing prevents flicker).

## Getting Started

### Prerequisites

- Python 3.11+
- PyTorch (CPU or CUDA)
- OpenCV

### Setup

```bash
# Virtual environment
python -m venv .venv
.venv\Scripts\activate     # Windows
source .venv/bin/activate  # Linux/Mac

# Install core dependencies
pip install -e .

# Install vision dependencies (for CSRNet inference)
pip install -e ".[vision]"
```

### Download CSRNet weights

The model requires the official ShanghaiTech Part B checkpoint:
- **File:** `models/partBmodel_best.pth.tar` (124 MB)
- **Download:** [Google Drive](https://drive.google.com/file/d/1zKn6YlLW3Z9ocgPbP99oz7r2nC7_TBXK/view)

### Download a test image

```bash
python scripts/fetch_test_image.py
```

### Run the full system

```bash
# Terminal 1: API server
.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir . --host 127.0.0.1 --port 8000

# Terminal 2: Dashboard
python -m http.server 4173 --directory dashboard

# Terminal 3: Simulator (random density data)
.venv\Scripts\python.exe scripts/simulate.py --demo-route n1 n6

# OR: Vision feed (live video inference)
.venv\Scripts\python.exe scripts/vision_feed.py --source data/test_videos/crowd_test.mp4 --show
```

Open **http://127.0.0.1:4173/** in your browser.

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/venue/graph` | Full graph state (nodes + edges with densities/statuses) |
| `POST` | `/simulate/density` | `{edge_id, density}` — update an edge's density reading |
| `GET` | `/route?start=X&end=Y` | Current best route + cost + reroute status |
| `GET` | `/alerts` | Event log (status changes, reroutes, telemetry warnings) |

## Project Structure

```
RTPCC/
├── app/                  # FastAPI application
│   ├── main.py           # Entrypoint, CORS, middleware
│   ├── models.py         # Pydantic schemas
│   ├── state.py          # In-memory state
│   └── routers/          # Route handlers per endpoint
├── config/               # Zone polygon configuration
├── dashboard/            # Frontend
│   ├── index.html        # Command-center dashboard
│   ├── styles.css        # Dark theme, glassmorphism
│   ├── app.js            # Graph viz, alerts, trend chart
│   └── venue_map.svg     # Convention-hall floor plan
├── data/                 # Test images and videos
├── models/               # CSRNet checkpoint
├── scripts/              # Python utilities
│   ├── csrnet_infer.py   # CSRNet model wrapper
│   ├── vision_feed.py    # Live video pipeline
│   ├── zones.py          # Zone aggregation + calibration
│   ├── simulate.py       # Random-walk data generator
│   └── calibrate_zones.py# Interactive polygon tool
└── src/rtpcc/            # Core engine
    ├── venue.py          # Graph model
    ├── risk.py           # Threshold + smoothing
    └── service.py        # Routing + alert management
```

## Dashboard Features

- **Dark command-center UI** with glassmorphism cards and real-time clock
- **SVG venue graph** with color-coded edges (green/yellow/orange/red)
- **Floor plan view** — toggle to see the venue map with labeled zones and exits
- **Animated KPI cards** — active zones, alerts, max/avg density, route status
- **Live alert feed** with slide-in animations and critical/warning/info badges
- **Density trend chart** — selectable per-edge line chart
- **System health panel** — status indicators for all services
- **Text-to-speech** announcements for STAMPEDE_RISK events
- **Responsive** — adapts from large monitors to tablets

## Calibration

The CSRNet model (trained on ShanghaiTech Part B) overcounts by ~15-38× on non-training footage. A `calibration_factor` (default 0.055 ≈ 1/18) per zone brings density values into plausible ranges:

```
calibrated_density = (raw_sum / area_m²) × calibration_factor
```

This is documented as expected domain mismatch — fine-tuning on real venue footage would remove the need for manual calibration.
