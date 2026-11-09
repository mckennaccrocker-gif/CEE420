"""Side-panel numbers from the saved accessibility stats.

Each rise is a saved channel-relative computation. Nothing here interpolates
a depth between rises or scales a depth by ENSO.
"""

from __future__ import annotations

from typing import Any


def build_summary(stats: dict[str, Any]) -> dict[str, Any]:
    if stats.get("hurricane_ida_depth") is not False:
        raise ValueError("Refusing to summarize a product that is not marked hurricane_ida_depth false.")
    stages = []
    hospital_by_stage: dict[str, dict[str, Any]] = {}
    for stage in stats["stages"]:
        key = f"{float(stage['stage_above_channel_dem_m']):.2f}"
        largest = next(component for component in stage["components"] if component["largest"])
        aadt = stats["aadt"]["by_stage"][key]
        hospital = _hospital_state(stage)
        hospital_by_stage[key] = hospital
        counts = stage.get("routing_status_counts") or {}
        stages.append(
            {
                "id": key,
                "stage_above_channel_dem_m": float(stage["stage_above_channel_dem_m"]),
                "label": f"+{float(stage['stage_above_channel_dem_m']):.1f} m assumption",
                "hurricane_ida_depth": False,
                "event_time": None,
                "wet_piece_length_m": stage["piece_length_m_at_or_above_0_30"],
                "wet_piece_percent_of_network": stage["percent_inside_length_piece_at_or_above_0_30"],
                "n_assumed_closed": stage["n_assumed_closed"],
                "n_still_open": counts.get("accessible_routable"),
                "assumed_closed_length_m": stage["assumed_closed_length_m_inside"],
                "assumed_closed_percent_of_network": stage["percent_inside_length_assumed_closed"],
                "n_weak_components": stage["n_weak_components"],
                "largest_component_length_m": largest["length_m_inside"],
                "largest_component_n_nodes": largest["n_nodes"],
                "hospital_disconnected": hospital["disconnected"],
                "hospital_n_connected": hospital["n_connected"],
                "hospital_n_disconnected": hospital["n_disconnected"],
                "facility_routes": _facility_routes(stage),
                "aadt_records": aadt["n_station_records_snapped"],
                "aadt_nearest_edge_assumed_closed": aadt["n_station_records_nearest_edge_assumed_closed"],
            }
        )
    disconnected = [
        item["stage_above_channel_dem_m"]
        for item in stages
        if item["hospital_disconnected"]
    ]
    saved_ids = [item["id"] for item in stages]
    computed_ids = [item["id"] for item in stages if item["facility_routes"]]
    every_mark = bool(saved_ids) and computed_ids == saved_ids
    if every_mark:
        facility_note = (
            "Hospital, fire, and police routes are already saved for every mark "
            "from 0 m to 2.0 m by 0.25 m. No route was added."
        )
    elif computed_ids:
        shown = ", ".join(f"+{item['stage_above_channel_dem_m']:.2f} m" for item in stages if item["facility_routes"])
        facility_note = (
            "Hospital, fire, and police routes are saved only for "
            + shown
            + ". They are not shown for the other marks. No route was added."
        )
    else:
        facility_note = "No hospital, fire, or police route is saved. None was added."
    return {
        "product": "scenario_accessibility_dashboard",
        "depth_product": stats.get("depth_product"),
        "hurricane_ida_depth": False,
        "event_time": None,
        "interpolated": False,
        "enso_scales_depths": False,
        "not_a_closure_standard": True,
        "time_note": (
            "Each slider mark is a saved channel-relative rise. "
            "The marks were not interpolated, they are not hours, and they are not a forecast."
        ),
        "thresholds_m": stats["thresholds_m"],
        "closure_piece_fraction": stats["closure_piece_fraction"],
        "network_length_m_inside": stats["stages"][0]["length_m_inside"],
        "n_centerlines": stats["stages"][0]["n_centerlines"],
        "computed_at_utc": stats.get("computed_at_utc"),
        "banner": (
            "Not Hurricane Ida. Depths are a hypothetical 3DEP channel-relative scenario. "
            "0.10 m, 0.30 m, and the 0.50 length fraction are preliminary assumptions, not closure standards. "
            "Each slider mark is its own rise above the channel. The marks were not interpolated, "
            "they are not a forecast, and ENSO does not scale them."
        ),
        "stages": stages,
        "hospital": {
            "name": "Princeton House Behavioral Health",
            "disconnects_only_at_2_00": disconnected == [2.0],
            "disconnected_rises_m": disconnected,
            "by_stage": hospital_by_stage,
        },
        "facility_routes": {
            "computed_for_every_saved_mark": every_mark,
            "computed_stage_ids": computed_ids,
            "note": facility_note,
        },
        "aadt_note": (
            "The count is station-records whose nearest edge is assumed closed. "
            "AADT is not summed and is not a count of travelers."
        ),
        "component_note": "A weak-component count is not evidence that a neighborhood is isolated.",
    }


def _facility_routes(stage: dict[str, Any]) -> list[dict[str, Any]]:
    """Saved hospital, fire, and police pairs only. Unknown statuses are omitted."""
    routes = []
    for row in stage.get("od_pairs") or []:
        roles = {row.get("origin_role"), row.get("destination_role")}
        if not roles & {"hospital", "fire_station", "police"}:
            continue
        status = row.get("scenario_status")
        if status == "disconnected":
            plain = "blocked"
        elif status in {"connected", "same_node"}:
            plain = "still open"
        else:
            continue
        length = row.get("scenario_path_length_m")
        routes.append(
            {
                "origin": row.get("origin"),
                "destination": row.get("destination"),
                "origin_role": row.get("origin_role"),
                "destination_role": row.get("destination_role"),
                "origin_osm_id": row.get("origin_osm_id"),
                "destination_osm_id": row.get("destination_osm_id"),
                "scenario_status": status,
                "scenario_path_length_m": None if length is None else float(length),
                "plain": plain,
            }
        )
    return routes


def attach_facility_places(summary: dict[str, Any], places: list[dict[str, Any]]) -> dict[str, Any]:
    """Copy saved destination coordinates onto the routes. No path is computed."""
    lookup: dict[int, tuple[float, float]] = {}
    for place in places:
        osm_id = place.get("osm_id")
        lon = place.get("lon")
        lat = place.get("lat")
        if osm_id is None or lon is None or lat is None:
            continue
        lookup[int(osm_id)] = (float(lon), float(lat))
    for stage in summary.get("stages") or []:
        for route in stage.get("facility_routes") or []:
            origin = lookup.get(_as_int(route.get("origin_osm_id")))
            destination = lookup.get(_as_int(route.get("destination_osm_id")))
            if origin:
                route["origin_lon"], route["origin_lat"] = origin
            if destination:
                route["destination_lon"], route["destination_lat"] = destination
    return summary


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _hospital_state(stage: dict[str, Any]) -> dict[str, Any]:
    connected = 0
    disconnected = 0
    for row in stage.get("od_pairs", []):
        roles = {row.get("origin_role"), row.get("destination_role")}
        blob = f"{row.get('origin', '')} {row.get('destination', '')}"
        if "hospital" not in roles and "Behavioral Health" not in blob:
            continue
        status = row.get("scenario_status")
        if status == "connected":
            connected += 1
        elif status == "disconnected":
            disconnected += 1
    return {
        "n_connected": connected,
        "n_disconnected": disconnected,
        "disconnected": disconnected > 0 and connected == 0,
    }
