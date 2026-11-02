"""Download NJDOT 2024 AADT and keep Mercer County Princeton station rows.

The output is a table of count stations. It is not joined to road edges,
and station AADT values are not summed into a municipal total.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from urllib.request import Request
from urllib.request import urlopen

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from network.roads import load_settings  # noqa: E402
from network.roads import resolve  # noqa: E402


def main() -> None:
    settings = load_settings()
    url = settings["sources"]["aadt"]["url"]
    destination = resolve(settings, "aadt_csv")
    try:
        payload = _download(url)
    except Exception as exc:
        raise SystemExit(
            "Could not download the NJDOT AADT table. No AADT values were invented. "
            f"URL: {url}\nOriginal error: {exc}"
        ) from exc
    frame = _read_table(payload)
    required = {"County", "Community", "AADT", "Latitude", "Longitude", "AADT Year", "Direction"}
    missing = required - set(frame.columns)
    if missing:
        raise SystemExit(f"NJDOT AADT table is missing columns {sorted(missing)}. File not written.")
    county = frame["County"].astype(str).str.strip().str.casefold()
    community = frame["Community"].astype(str)
    mask = (county == "mercer") & community.str.contains("princeton", case=False, na=False)
    subset = frame.loc[mask].copy()
    if subset.empty:
        raise SystemExit(
            "The NJDOT table downloaded, but no Mercer County community containing "
            "'Princeton' was found. No empty AADT file was written."
        )
    if subset["AADT"].isna().any():
        raise SystemExit("Princeton AADT rows include missing AADT. Refusing to fill them in.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    subset.to_csv(destination, index=False)
    provenance = {
        "source_url": url,
        "publisher": "NJDOT",
        "filter": "County casefold equals 'mercer' AND Community contains 'princeton'",
        "rows_in_source": int(len(frame)),
        "rows_written": int(len(subset)),
        "aadt_year_values": sorted(int(year) for year in subset["AADT Year"].dropna().unique()),
        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "joined_to_road_edges": False,
        "note": (
            "Station records as published. Community still uses NJDOT's "
            "'Princeton' and 'Princeton Twp' labels. Values were not summed "
            "and were not copied onto road edges."
        ),
    }
    destination.with_suffix(".provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(f"Wrote {len(subset)} NJDOT AADT rows to {destination}")


def _download(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "princeton-flood-accessibility/0.1 (CEE420 educational research)"})
    with urlopen(request, timeout=120) as response:
        return response.read()


def _read_table(payload: bytes) -> pd.DataFrame:
    """NJDOT's CSV is not valid UTF-8 (it contains a 0xA0 byte)."""
    from io import BytesIO

    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return pd.read_csv(BytesIO(payload), encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise SystemExit("Could not decode the NJDOT AADT CSV as utf-8, cp1252, or latin-1.")


if __name__ == "__main__":
    main()
