"""Write the dashboard as static files for a public web host.

The files are the same payloads the local server already builds from saved
results. This script does not recompute depths, interpolate a rise, scale
depths by ENSO, or sample bridge decks.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dashboard.routing import build_routing_network  # noqa: E402
from network.roads import load_settings  # noqa: E402
from network.roads import resolve  # noqa: E402


def _server():
    spec = importlib.util.spec_from_file_location("dashboard_server", ROOT / "scripts" / "dashboard.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

WEB = ROOT / "web"
FILES = {
    "summary.json": "summary",
    "roads.geojson": "roads",
    "boundary.geojson": "boundary",
    "enso.json": "enso",
    "ida.json": "ida",
    "bridge-decks.json": "decks",
    "fema.json": "fema",
    "fema-zones.geojson": "fema_zones",
    "observed-reports.geojson": "observed_reports",
    "name-check.json": "name_check",
}


def export_site(context: dict, web: Path = WEB) -> Path:
    if context.get("summary", {}).get("hurricane_ida_depth") is not False:
        raise ValueError("Refusing to publish a page that is not marked hurricane_ida_depth false.")
    if context.get("summary", {}).get("interpolated") is not False:
        raise ValueError("Refusing to publish an interpolated dashboard.")
    if context.get("summary", {}).get("enso_scales_depths") is not False:
        raise ValueError("Refusing to publish a dashboard that scales depths by ENSO.")
    out = web / "data"
    out.mkdir(parents=True, exist_ok=True)
    for name, key in FILES.items():
        payload = context[key]
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        (out / name).write_text(text, encoding="utf-8")
    return out


def main() -> None:
    settings = load_settings()
    out = export_site(_server().build_context(settings))
    routing = build_routing_network(resolve(settings, "graphml"), resolve(settings, "accessibility_geojson"))
    if routing.get("hurricane_ida_depth") is not False:
        raise ValueError("Refusing to publish a route network marked as Hurricane Ida.")
    (out / "routing.json").write_text(
        json.dumps(routing, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"Wrote static dashboard data to {out}")


if __name__ == "__main__":
    main()
