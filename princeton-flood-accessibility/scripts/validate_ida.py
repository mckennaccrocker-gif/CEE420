"""Compare named September 2021 reports with the scenario, qualitatively.

Does not compute precision or recall and does not claim the model is validated.

Run from princeton-flood-accessibility:

    python3 scripts/validate_ida.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dashboard.ida_check import write_comparison  # noqa: E402
from network.roads import load_settings  # noqa: E402
from network.roads import resolve  # noqa: E402


def main() -> None:
    settings = load_settings()
    result = write_comparison(resolve(settings, "accessibility_geojson"), resolve(settings, "ida_comparison"))
    if result["validated"] is not False or result["hurricane_ida_depth"] is not False:
        raise SystemExit("Refusing to write a comparison that claims validation or an Ida depth.")
    if "precision" in result or "recall" in result:
        raise SystemExit("Refusing to write precision or recall.")
    print(f"Wrote {resolve(settings, 'ida_comparison')}")
    print(result["note"])
    for place in result["places"]:
        print(f"{place['title']}: {place['verification']}")
        print(f"  {place['qualitative']}")


if __name__ == "__main__":
    main()
