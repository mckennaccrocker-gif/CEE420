"""Name check for the five September 2021 roads.

Captured means the saved scenario assumed at least one centerline of that
name closed at that rise. Missed means it assumed none closed. The counts
are read from the saved routing status. This module does not sample a DEM,
does not interpolate a rise, and does not score the comparison.
"""

from __future__ import annotations

from typing import Any

# Exact OpenStreetMap names. The display names match the news-report layer.
ROADS: tuple[dict[str, Any], ...] = (
    {"road": "Quaker Road", "exact_names": ("Quaker Road",)},
    {"road": "Mercer Road", "exact_names": ("Mercer Road",)},
    {"road": "Stockton Street / Route 206", "exact_names": ("Stockton Street",)},
    {
        "road": "South Harrison Street",
        "exact_names": ("South Harrison Street",),
        "note": "The wording gap is left as written.",
    },
    {
        "road": "Rosedale Road",
        "exact_names": ("Rosedale Road",),
        "note": "The 2 September sentence is a reopening time, not a closure log.",
    },
)

RISES_M: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0)


def refuse_scored_name_check(payload: dict[str, Any]) -> None:
    """Raise if the name check is treated as a validation score."""
    if payload.get("validated") is True:
        raise ValueError("Refusing to call the September 2021 name check a validation.")
    if payload.get("interpolated") is True:
        raise ValueError("Refusing an interpolated name check.")
    blob = " ".join(_text_bits(payload))
    lowered = blob.lower()
    if "precision" in lowered or "recall" in lowered:
        raise ValueError("Refusing to score precision or recall on the name check.")
    for row in payload.get("rows") or []:
        for stage in ("plus_1_00", "plus_2_00"):
            if row.get(stage) not in {"captured", "missed"}:
                raise ValueError(f"Refusing an unscored result label: {row.get(stage)!r}.")
        for step in row.get("steps") or []:
            if step.get("result") not in {"captured", "missed"}:
                raise ValueError(f"Refusing an unscored result label: {step.get('result')!r}.")


def build_name_check(features: list[dict[str, Any]]) -> dict[str, Any]:
    """Count assumed closures on the saved centerlines. No depth is recomputed."""
    properties = [_properties(feature) for feature in features]
    rows = [_row(spec, properties) for spec in ROADS]
    payload = {
        "product": "september_2021_name_check",
        "label": "A name check, not a validation. It was not scored.",
        "validated": False,
        "hurricane_ida_depth": False,
        "event_time": None,
        "depths_recomputed": False,
        "interpolated": False,
        "enso_scales_depths": False,
        "rises_m": list(RISES_M),
        "rows": rows,
    }
    refuse_scored_name_check(payload)
    return payload


def _row(spec: dict[str, Any], properties: list[dict[str, Any]]) -> dict[str, Any]:
    matched = [props for props in properties if props.get("name") in spec["exact_names"]]
    steps = []
    for rise in RISES_M:
        slug = f"{rise:.2f}".replace(".", "_")
        status_key = f"routing_status_stage_{slug}"
        if matched and status_key not in matched[0] and f"status_{slug}" not in matched[0]:
            raise ValueError(f"Saved centerlines have no routing status for +{rise:.2f} m.")
        closed = sum(1 for props in matched if _status(props, slug) == "assumed_closed")
        step: dict[str, Any] = {
            "stage_m": rise,
            "id": f"{rise:.2f}",
            "result": "captured" if closed else "missed",
            "n_assumed_closed": closed,
        }
        if closed:
            step["captured_of"] = f"{closed} of {len(matched)}"
        steps.append(step)
    by_id = {step["id"]: step for step in steps}
    detail = _detail(len(matched), steps, spec.get("note"))
    row: dict[str, Any] = {
        "road": spec["road"],
        "n_centerlines": len(matched),
        "plus_1_00": by_id["1.00"]["result"],
        "plus_2_00": by_id["2.00"]["result"],
        "detail": detail,
        "steps": steps,
    }
    if "captured_of" in by_id["2.00"]:
        row["captured_of"] = by_id["2.00"]["captured_of"]
    return row


def _detail(count: int, steps: list[dict[str, Any]], note: str | None) -> str:
    captured = [step for step in steps if step["result"] == "captured"]
    if not captured:
        sentence = f"None of the {count} is assumed closed at any computed rise."
    else:
        parts = [f"+{step['stage_m']:.2f} m ({step['captured_of']})" for step in captured]
        sentence = "Assumed closed at " + ", ".join(parts) + "."
    if note:
        return sentence + " " + note
    return sentence


def _status(props: dict[str, Any], slug: str) -> str | None:
    if f"routing_status_stage_{slug}" in props:
        return props.get(f"routing_status_stage_{slug}")
    return props.get(f"status_{slug}")


def _properties(feature: dict[str, Any]) -> dict[str, Any]:
    if "properties" in feature and isinstance(feature["properties"], dict):
        return feature["properties"]
    return feature


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
