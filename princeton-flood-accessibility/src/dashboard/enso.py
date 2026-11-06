"""NOAA Climate Prediction Center Niño-3.4 observations.

The weekly anomaly is not an ENSO phase. The phase is recorded only when the
ENSO Diagnostic Discussion states an alert status. These numbers are Pacific
context. They are not Princeton road depths.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from datetime import timezone
from html import unescape
from pathlib import Path
from typing import Any
from typing import Callable
from urllib.request import Request
from urllib.request import urlopen

WEEKLY_URL = "https://www.cpc.ncep.noaa.gov/data/indices/wksst9120.for"
ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
DISCUSSION_URL = "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml"

CONTEXT = (
    "ENSO is a large-scale Pacific ocean-atmosphere pattern. NOAA uses it as "
    "context for Atlantic tropical cyclone activity. It does not set the depth "
    "on a Princeton road, and this app does not scale the scenario by ENSO."
)

_MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}

_SEASONS = {
    "DJF": "December–February",
    "JFM": "January–March",
    "FMA": "February–April",
    "MAM": "March–May",
    "AMJ": "April–June",
    "MJJ": "May–July",
    "JJA": "June–August",
    "JAS": "July–September",
    "ASO": "August–October",
    "SON": "September–November",
    "OND": "October–December",
    "NDJ": "November–January",
}

_NUMBER = re.compile(r"[+-]?\d+\.\d+")
_WEEK = re.compile(r"^\s*(\d{2}[A-Z]{3}\d{4})\s+(.*)$")
_ONI = re.compile(r"^\s*([A-Z]{3})\s+(\d{4})\s+([+-]?\d+\.\d+)\s+([+-]?\d+\.\d+)\s*$")
_STATUS = re.compile(r"ENSO Alert System Status:\s*(.+?)\s+Synopsis:", re.IGNORECASE)
_ISSUED = re.compile(
    r"\b(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+\d{4})\b"
)


def parse_weekly(text: str) -> dict[str, Any]:
    """Last Niño-3.4 row in the CPC weekly OISST file.

    Columns are Niño 1+2, Niño 3, Niño 3.4, Niño 4, each as SST then anomaly.
    A negative anomaly is sometimes glued to the SST (``26.5-0.2``).
    """
    last: dict[str, Any] | None = None
    for line in text.splitlines():
        match = _WEEK.match(line)
        if not match:
            continue
        numbers = [float(item) for item in _NUMBER.findall(match.group(2))]
        if len(numbers) != 8:
            continue
        last = {
            "week_centered": _cpc_week(match.group(1)),
            "nino34_sst_c": numbers[4],
            "nino34_anomaly_c": numbers[5],
            "source": WEEKLY_URL,
            "source_note": "Week-centered Niño-3.4 SST and anomaly from wksst9120.for. Not a phase.",
        }
    if last is None:
        raise ValueError("The weekly file has no Niño-3.4 row.")
    return last


def parse_oni(text: str) -> dict[str, Any]:
    """Last Oceanic Niño Index row. The file has no phase column."""
    last: dict[str, Any] | None = None
    for line in text.splitlines():
        match = _ONI.match(line)
        if not match:
            continue
        season = match.group(1)
        last = {
            "season": season,
            "year": int(match.group(2)),
            "season_label": _SEASONS.get(season, season),
            "sst_c": float(match.group(3)),
            "anomaly_c": float(match.group(4)),
            "phase_stated_in_file": False,
            "source": ONI_URL,
            "source_note": "Three-month mean (TOTAL) and anomaly (ANOM) as printed. No phase is read from this row.",
        }
    if last is None:
        raise ValueError("The ONI file has no data row.")
    return last


def parse_discussion(html: str) -> dict[str, Any] | None:
    """Official alert status, only if the discussion states one.

    A page with no ``ENSO Alert System Status`` returns None. The weekly
    anomaly is never used to fill that gap.
    """
    text = unescape(re.sub(r"<[^>]+>", " ", html))
    text = re.sub(r"\s+", " ", text).strip()
    status = _STATUS.search(text)
    if not status:
        return None
    issued = _ISSUED.search(text)
    return {
        "status": status.group(1).strip(" .:"),
        "issued": issued.group(1) if issued else None,
        "source": DISCUSSION_URL,
        "classified_from_weekly_anomaly": False,
        "note": "Quoted from the ENSO Diagnostic Discussion. Not classified from the weekly anomaly.",
    }


def assemble(
    weekly_text: str,
    oni_text: str,
    discussion_html: str | None,
    *,
    fetched_at_utc: str,
) -> dict[str, Any]:
    phase = parse_discussion(discussion_html) if discussion_html else None
    return {
        "ok": True,
        "using_saved_observation": False,
        "fetched_at_utc": fetched_at_utc,
        "fetch_error": None,
        "weekly": parse_weekly(weekly_text),
        "oni": parse_oni(oni_text),
        "official_phase": phase,
        "official_phase_note": (
            "NOAA stated this status in the diagnostic discussion."
            if phase
            else "The retrieved discussion did not state an ENSO Alert System Status, so no phase is shown."
        ),
        "context": CONTEXT,
        "enso_scales_depths": False,
        "hurricane_ida_depth": False,
    }


def fetch_text(url: str, timeout_s: float = 40) -> str:
    request = Request(
        url,
        headers={"User-Agent": "princeton-flood-accessibility/0.1 (CEE420 educational research)"},
    )
    with urlopen(request, timeout=timeout_s) as response:
        return response.read().decode("utf-8", errors="replace")


def refresh(
    cache_path: Path,
    *,
    fetch: Callable[[str], str] = fetch_text,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Download the three CPC products and replace the cache.

    If the download fails and a previous success is on disk, that observation
    is returned with its original date. A weekly anomaly is still not turned
    into a phase.
    """
    moment = now or datetime.now(timezone.utc)
    stamp = moment.strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        record = assemble(fetch(WEEKLY_URL), fetch(ONI_URL), fetch(DISCUSSION_URL), fetched_at_utc=stamp)
    except Exception as exc:
        saved = _read_cache(cache_path)
        if saved is None:
            raise RuntimeError(f"ENSO fetch failed and no saved observation exists: {exc}") from exc
        saved = dict(saved)
        saved["using_saved_observation"] = True
        saved["ok"] = True
        saved["fetch_error"] = str(exc)
        saved["enso_scales_depths"] = False
        saved["hurricane_ida_depth"] = False
        return saved
    _write_cache(cache_path, record)
    return record


def load_cached(cache_path: Path) -> dict[str, Any]:
    """Read the last successful observation. Does not contact NOAA."""
    saved = _read_cache(cache_path)
    if saved is None:
        raise FileNotFoundError(f"No saved ENSO observation at {cache_path}. Run scripts/update_enso.py.")
    saved = dict(saved)
    saved["using_saved_observation"] = False
    saved["enso_scales_depths"] = False
    saved["hurricane_ida_depth"] = False
    return saved


def _cpc_week(token: str) -> str:
    month = _MONTHS.get(token[2:5])
    if month is None:
        raise ValueError(f"Unrecognised CPC week token: {token}")
    return f"{int(token[5:]):04d}-{month:02d}-{int(token[:2]):02d}"


def _read_cache(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "fetched_at_utc" not in payload:
        return None
    return payload


def _write_cache(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
