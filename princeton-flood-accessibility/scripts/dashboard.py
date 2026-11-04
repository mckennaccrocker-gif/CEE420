"""Princeton road-accessibility dashboard.

Serves the saved channel-relative rises. It does not interpolate them and
it does not scale depths by ENSO.

Run from princeton-flood-accessibility:

    python3 scripts/dashboard.py

Then open http://127.0.0.1:8765/
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dashboard.enso import load_cached  # noqa: E402
from dashboard.name_check import build_name_check  # noqa: E402
from dashboard.observed_reports import build_observed_reports  # noqa: E402
from dashboard.roads import build_road_collection  # noqa: E402
from dashboard.summary import build_summary  # noqa: E402
from network.roads import load_settings  # noqa: E402
from network.roads import resolve  # noqa: E402

WEB = ROOT / "web"
_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".png": "image/png",
    ".json": "application/json; charset=utf-8",
    ".geojson": "application/geo+json; charset=utf-8",
}


def build_context(settings: dict) -> dict:
    stats = json.loads(resolve(settings, "accessibility_stats").read_text(encoding="utf-8"))
    summary = build_summary(stats)
    boundary = json.loads(resolve(settings, "boundary").read_text(encoding="utf-8"))
    enso_path = resolve(settings, "enso_cache")
    ida_path = resolve(settings, "ida_comparison")
    enso = load_cached(enso_path) if enso_path.is_file() else {
        "ok": False,
        "using_saved_observation": False,
        "enso_scales_depths": False,
        "hurricane_ida_depth": False,
        "fetched_at_utc": None,
        "fetch_error": "No saved ENSO observation. Run scripts/update_enso.py.",
    }
    ida = json.loads(ida_path.read_text(encoding="utf-8")) if ida_path.is_file() else {
        "validated": False,
        "hurricane_ida_depth": False,
        "note": "No comparison file yet. Run scripts/validate_ida.py.",
        "places": [],
    }
    deck_path = resolve(settings, "bridge_deck_join")
    decks = json.loads(deck_path.read_text(encoding="utf-8")) if deck_path.is_file() else {
        "hurricane_ida_depth": False,
        "n_bridge_centerlines": None,
        "n_with_deck_elevation": None,
        "n_sampled": None,
        "centerlines": [],
        "note": "No bridge-deck join yet. Run scripts/bridge_decks.py.",
    }
    fema_path = resolve(settings, "fema_overlay")
    fema = json.loads(fema_path.read_text(encoding="utf-8")) if fema_path.is_file() else {
        "hurricane_ida_depth": False,
        "zone_depth_assigned": False,
        "regulatory": True,
        "effective_date_label": None,
        "zones": [],
        "centerlines": [],
        "note": "No FEMA overlay yet. Run scripts/fema_overlay.py.",
    }
    zones_path = resolve(settings, "fema_zones_geojson")
    fema_zones = json.loads(zones_path.read_text(encoding="utf-8")) if zones_path.is_file() else {
        "type": "FeatureCollection",
        "features": [],
    }
    accessibility_path = resolve(settings, "accessibility_geojson")
    roads = build_road_collection(accessibility_path, decks, fema)
    accessibility = json.loads(accessibility_path.read_text(encoding="utf-8"))
    fema_public = dict(fema)
    fema_public.pop("centerlines", None)
    return {
        "summary": summary,
        "roads": roads,
        "boundary": boundary,
        "enso": enso,
        "ida": ida,
        "decks": decks,
        "fema": fema_public,
        "fema_zones": fema_zones,
        "observed_reports": build_observed_reports(roads),
        "name_check": build_name_check(accessibility["features"]),
    }


def make_handler(context: dict) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/api/summary":
                self._json(context["summary"])
                return
            if path == "/api/roads.geojson":
                self._json(context["roads"])
                return
            if path == "/api/boundary.geojson":
                self._json(context["boundary"])
                return
            if path == "/api/enso":
                self._json(context["enso"])
                return
            if path == "/api/ida":
                self._json(context["ida"])
                return
            if path == "/api/bridge-decks":
                self._json(context["decks"])
                return
            if path == "/api/fema":
                self._json(context["fema"])
                return
            if path == "/api/fema-zones.geojson":
                self._json(context["fema_zones"])
                return
            if path == "/api/observed-reports.geojson":
                self._json(context["observed_reports"])
                return
            if path == "/api/name-check":
                self._json(context["name_check"])
                return
            if path == "/":
                self._file(WEB / "index.html")
                return
            if path.startswith("/vendor/") or path in {"/app.js", "/styles.css"}:
                self._file(WEB / path.lstrip("/"))
                return
            self.send_error(404)

        def _json(self, payload: object) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _file(self, path: Path) -> None:
            resolved = path.resolve()
            if not str(resolved).startswith(str(WEB.resolve())) or not resolved.is_file():
                self.send_error(404)
                return
            body = resolved.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", _TYPES.get(resolved.suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: object) -> None:
            print(f"{self.address_string()} {fmt % args}")

    return Handler


def serve(host: str, port: int, context: dict) -> None:
    server = ThreadingHTTPServer((host, port), make_handler(context))
    print(f"Princeton scenario dashboard at http://{host}:{port}/")
    print("Not Hurricane Ida. Each rise is computed on its own, not a forecast.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopped.")
    finally:
        server.server_close()


def main() -> None:
    settings = load_settings()
    host = str(settings.get("dashboard", {}).get("host", "127.0.0.1"))
    port = int(settings.get("dashboard", {}).get("port", 8765))
    if len(sys.argv) >= 2:
        port = int(sys.argv[1])
    serve(host, port, build_context(settings))


if __name__ == "__main__":
    main()
