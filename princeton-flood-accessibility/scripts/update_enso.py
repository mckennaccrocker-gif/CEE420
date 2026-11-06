"""Refresh the NOAA CPC Niño-3.4 cache.

Weekly anomaly, monthly ONI, and the diagnostic-discussion alert status are
stored under data/processed. A failed fetch keeps the previous success and
its date. No secret is written.

Run from princeton-flood-accessibility:

    python3 scripts/update_enso.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dashboard.enso import refresh  # noqa: E402
from network.roads import load_settings  # noqa: E402
from network.roads import resolve  # noqa: E402


def main() -> None:
    settings = load_settings()
    cache = resolve(settings, "enso_cache")
    try:
        record = refresh(cache)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    weekly = record["weekly"]
    oni = record["oni"]
    phase = record.get("official_phase")
    if record.get("using_saved_observation"):
        print(f"Fetch failed. Kept the observation from {record['fetched_at_utc']}.")
        print(record.get("fetch_error"))
        raise SystemExit(1)
    print(f"Wrote {cache}")
    print(
        f"Weekly Niño-3.4 anomaly {weekly['nino34_anomaly_c']} °C, "
        f"week centered {weekly['week_centered']}."
    )
    print(f"ONI {oni['season']} {oni['year']} anomaly {oni['anomaly_c']} °C.")
    if phase:
        print(f"Official status: {phase['status']} ({phase.get('issued')}). Not taken from the weekly anomaly.")
    else:
        print("No official phase was stated in the retrieved discussion.")


if __name__ == "__main__":
    main()
