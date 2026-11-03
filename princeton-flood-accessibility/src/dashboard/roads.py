"""Slim centerlines for the map. Depths stay labeled as the scenario."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_road_collection(
    path: Path,
    deck_join: dict[str, Any] | None = None,
    fema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    decks = {
        item["centerline_id"]: item
        for item in (deck_join or {}).get("centerlines", [])
    }
    fema_rows = {
        item["centerline_id"]: item
        for item in (fema or {}).get("centerlines", [])
    }
    features = []
    for feature in payload["features"]:
        props = feature["properties"]
        if props.get("hurricane_ida_depth") is True:
            raise ValueError(f"Refusing a centerline marked as Ida depth: {props.get('centerline_id')}")
        deck = decks.get(props.get("centerline_id"))
        fema_row = fema_rows.get(props.get("centerline_id"))
        is_bridge = bool(props.get("is_bridge"))
        features.append(
            {
                "type": "Feature",
                "geometry": _round_geometry(feature["geometry"]),
                "properties": {
                    "centerline_id": props.get("centerline_id"),
                    "name": props.get("name") or None,
                    "road_class": props.get("road_class"),
                    "is_bridge": is_bridge,
                    "exposure_status": props.get("exposure_status"),
                    "length_m_inside": _round(props.get("length_m_inside"), 1),
                    "hurricane_ida_depth": False,
                    "event_time": None,
                    "status_1_00": props.get("routing_status_stage_1_00"),
                    "status_2_00": props.get("routing_status_stage_2_00"),
                    "depth_max_m_1_00": _round(props.get("depth_max_m_stage_1_00"), 3),
                    "depth_max_m_2_00": _round(props.get("depth_max_m_stage_2_00"), 3),
                    "wet_m_1_00": _round(props.get("length_m_at_or_above_0_30_stage_1_00"), 1),
                    "wet_m_2_00": _round(props.get("length_m_at_or_above_0_30_stage_2_00"), 1),
                    "deck_status": _deck_status(is_bridge, deck),
                    "deck_elevation_m": None if deck is None else deck.get("deck_elevation_m"),
                    "deck_note": None if deck is None else deck.get("note"),
                    "deck_structures": _structure_labels(deck),
                    "fema_zones": _fema_zones(fema_row),
                    "fema_zone_depth_m": None,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _deck_status(is_bridge: bool, deck: dict[str, Any] | None) -> str | None:
    if not is_bridge:
        return None
    if deck is None:
        return "bridge_deck_unmatched"
    status = deck.get("exposure_status")
    if status not in {"bridge_deck_unmatched", "bridge_deck_sampled"}:
        raise ValueError(f"Unexpected deck status {status!r}.")
    return status


def _fema_zones(row: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not row:
        return []
    zones = []
    for item in row.get("zones") or []:
        zones.append({"zone": item.get("zone"), "length_m": item.get("length_m"), "zone_depth_m": None})
    return zones


def _structure_labels(deck: dict[str, Any] | None) -> list[str]:
    if not deck:
        return []
    labels = []
    for item in deck.get("accepted_structures") or []:
        labels.append(
            f"{item['structure_number']}: {item['facility_carried']} over {item['feature_intersected']} "
            f"({item['structure_length_m']} m, {item['distance_m']} m from the centerline)"
        )
    return labels


def _round(value: Any, digits: int) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() in {"", "none", "nan"}:
        return None
    number = float(value)
    if number != number:
        return None
    return round(number, digits)


def _round_geometry(geometry: dict[str, Any]) -> dict[str, Any]:
    kind = geometry["type"]
    if kind == "LineString":
        return {"type": kind, "coordinates": [_pair(point) for point in geometry["coordinates"]]}
    if kind == "MultiLineString":
        return {
            "type": kind,
            "coordinates": [[_pair(point) for point in line] for line in geometry["coordinates"]],
        }
    raise ValueError(f"Unexpected road geometry: {kind}")


def _pair(point: list[float]) -> list[float]:
    return [round(float(point[0]), 6), round(float(point[1]), 6)]
