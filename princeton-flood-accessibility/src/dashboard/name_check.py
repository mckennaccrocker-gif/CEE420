"""Name check for the five September 2021 roads.

The rows are the scenario sentences already written in the stage-9 note.
This module does not read a depth, does not recount centerlines, and does
not score the comparison.
"""

from __future__ import annotations

from typing import Any

# Captured means the stage-9 note says the scenario assumed at least one
# centerline of that name closed. Missed means it says the scenario assumed
# none closed. Mercer Road is the only captured cell, and only at +2.0 m.
ROWS: tuple[dict[str, Any], ...] = (
    {
        "road": "Quaker Road",
        "n_centerlines": 10,
        "plus_1_00": "missed",
        "plus_2_00": "missed",
        "detail": "None of the 10 is assumed closed at either assumption.",
    },
    {
        "road": "Mercer Road",
        "n_centerlines": 14,
        "plus_1_00": "missed",
        "plus_2_00": "captured",
        "captured_of": "2 of 14",
        "detail": "Not closed at +1.0 m. At +2.0 m the scenario assumed 2 of the 14 closed.",
    },
    {
        "road": "Stockton Street / Route 206",
        "n_centerlines": 11,
        "plus_1_00": "missed",
        "plus_2_00": "missed",
        "detail": "None of the 11 centerlines named Stockton Street is assumed closed.",
    },
    {
        "road": "South Harrison Street",
        "n_centerlines": 4,
        "plus_1_00": "missed",
        "plus_2_00": "missed",
        "detail": "None of the 4 is assumed closed. The wording gap is left as written.",
    },
    {
        "road": "Rosedale Road",
        "n_centerlines": 12,
        "plus_1_00": "missed",
        "plus_2_00": "missed",
        "detail": "None of the 12 is assumed closed. The 2 September sentence is a reopening time, not a closure log.",
    },
)


def refuse_scored_name_check(payload: dict[str, Any]) -> None:
    """Raise if the name check is treated as a validation score."""
    if payload.get("validated") is True:
        raise ValueError("Refusing to call the September 2021 name check a validation.")
    blob = " ".join(_text_bits(payload))
    lowered = blob.lower()
    if "precision" in lowered or "recall" in lowered:
        raise ValueError("Refusing to score precision or recall on the name check.")
    for row in payload.get("rows") or []:
        for stage in ("plus_1_00", "plus_2_00"):
            if row.get(stage) not in {"captured", "missed"}:
                raise ValueError(f"Refusing an unscored result label: {row.get(stage)!r}.")


def build_name_check() -> dict[str, Any]:
    """Return the five rows. No depth file is opened."""
    payload = {
        "product": "september_2021_name_check",
        "label": "A name check, not a validation. It was not scored.",
        "validated": False,
        "hurricane_ida_depth": False,
        "event_time": None,
        "depths_recomputed": False,
        "rows": [dict(row) for row in ROWS],
    }
    refuse_scored_name_check(payload)
    return payload


def _text_bits(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        bits: list[str] = []
        for key, item in value.items():
            bits.append(str(key))
            bits.extend(_text_bits(item))
        return bits
    if isinstance(value, list):
        bits = []
        for item in value:
            bits.extend(_text_bits(item))
        return bits
    return []
