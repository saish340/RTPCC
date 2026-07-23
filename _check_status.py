from __future__ import annotations
import requests

BASE = "http://127.0.0.1:8000"

r = requests.get(f"{BASE}/venue/graph", timeout=3)
edges = r.json()["edges"]
print(f"=== Graph ({len(edges)} edges) ===")
for e in edges[:6]:
    print(f"  {e['edge_id']}: D={e['current_density']:.2f} {e['current_status']} cost={e['current_cost']}")

r2 = requests.get(f"{BASE}/alerts", timeout=3)
alerts = r2.json()["alerts"]
print(f"\n=== Alerts ({len(alerts)}) ===")
for a in alerts[-5:]:
    print(f"  {a['event_type']}: {a['message'][:90]}")

r3 = requests.get(f"{BASE}/route", params={"start": "n1", "end": "n6"}, timeout=3)
route = r3.json()
path = " -> ".join(route["path"])
print(f"\n=== Route n1->n6 ===")
print(f"  Path: {path}")
print(f"  Cost: {route['total_cost']}")
print(f"  Rerouted: {route['rerouted']}")
