"""Download the USGS New Jersey Hurricane Ida high-water-mark table unchanged.

These are surveyed point elevations (NAVD88), not a depth raster, and they
are not assigned to roads.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from urllib.request import Request
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from network.roads import load_settings  # noqa: E402
from network.roads import resolve  # noqa: E402


def main() -> None:
    settings = load_settings()
    source = settings["sources"]["hwm"]
    destination = resolve(settings, "hwm_csv")
    try:
        payload = _download(source["url"])
    except Exception as exc:
        raise SystemExit(
            "Could not download the USGS Ida high-water-mark table. "
            "No high-water marks were invented. "
            f"URL: {source['url']}\nOriginal error: {exc}"
        ) from exc
    if b"latitude" not in payload.splitlines()[0].lower():
        raise SystemExit("Downloaded file does not look like the USGS HWM CSV. File not written.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    provenance = {
        "source_url": source["url"],
        "doi": source["doi"],
        "sciencebase_item": source["item"],
        "publisher": "USGS",
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "edited": False,
        "line_endings": "CRLF, as downloaded",
        "note": (
            "Point observations of high-water-mark elevation after Hurricane Ida. "
            "Not a flood-depth raster and not joined to the road network."
        ),
    }
    destination.with_suffix(".provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(f"Wrote USGS HWM table ({len(payload)} bytes) to {destination}")


def _download(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "princeton-flood-accessibility/0.1 (CEE420 educational research)"})
    with urlopen(request, timeout=120) as response:
        return response.read()


if __name__ == "__main__":
    main()
