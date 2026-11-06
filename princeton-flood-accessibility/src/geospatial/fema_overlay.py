"""Effective FEMA flood-hazard zones on Princeton centerlines.

This is a regulatory overlay. It is not a Hurricane Ida depth, not a deck
elevation, and it does not replace the +1.0 m or +2.0 m scenario. A zone
code is never turned into a depth. The 65.5 ft NAVD 88 figure is the
published base-flood water surface at Stony Brook cross section M. It is
not a deck elevation and it is not subtracted from a scenario water surface.
"""

from __future__ import annotations

import math
from typing import Any

import geopandas as gpd
from shapely.geometry import MultiPolygon
from shapely.geometry import Polygon
from shapely.validation import make_valid

from geospatial.crs import PROJECTED_EPSG
from geospatial.crs import US_SURVEY_FOOT_M
from geospatial.crs import require_crs
from geospatial.crs import us_survey_feet_to_m

SOURCE_HORIZONTAL_CRS = "EPSG:4269"
ANALYSIS_CRS = f"EPSG:{PROJECTED_EPSG}"
# NFHL uses -9999 when a numeric flood attribute was not populated.
NFHL_MISSING = -9999.0
MIN_PIECE_M = 0.05
MERCER_DFIRM = "34021C"
MERCER_EFFECTIVE_DATE = "2016-07-20"
MERCER_EFFECTIVE_LABEL = "20 July 2016"

# Published on NFHL cross-section M and in FIS Table 10. Not a deck.
STONY_BROOK_SECTION_M = {
    "stream": "Stony Brook",
    "cross_section": "M",
    "stream_station_ft": 22120.0,
    "stream_station_note": "Feet above the confluence with the Millstone River.",
    "value": 65.5,
    "units": "feet",
    "datum": "NAVD 88",
    "kind": "regulatory_base_flood_water_surface",
    "not_a_deck_elevation": True,
    "not_a_scenario_depth": True,
    "applied_to_centerlines": False,
}


def depth_from_flood_zone(
    *,
    fld_zone: str | None = None,
    zone_subty: str | None = None,
    static_bfe: float | None = None,
    is_bridge: bool = False,
    regulatory_water_surface_ft: float | None = None,
) -> dict[str, Any]:
    """Refuse to turn a zone, a static BFE, or the 65.5 ft water surface into a depth.

    The arguments are accepted so a caller can pass the values it might be
    tempted to use. None of them becomes a depth, including on a bridge.
    """
    del fld_zone, zone_subty, is_bridge
    return {
        "zone_depth_m": None,
        "zone_depth_assigned": False,
        "static_bfe_used_as_depth": False,
        "regulatory_water_surface_used_as_deck": False,
        "regulatory_water_surface_used_as_depth": False,
        "terrain_under_bridge_used_as_deck": False,
        "static_bfe_ft": _blank_sentinel(static_bfe),
        "regulatory_water_surface_ft": regulatory_water_surface_ft,
        "reason": "A flood-zone code is not a depth, and a regulatory water surface is not a deck elevation.",
    }


def zone_label(fld_zone: str | None, zone_subty: str | None) -> str:
    """Published zone code plus subtype, when the subtype is populated."""
    zone = _text(fld_zone) or "UNKNOWN"
    subtype = _text(zone_subty)
    if subtype is None:
        return zone
    return f"{zone} — {subtype}"


def fill_class(fld_zone: str | None, zone_subty: str | None) -> str:
    """Map style key. These names are not the scenario road colors."""
    subtype = (_text(zone_subty) or "").upper()
    zone = (_text(fld_zone) or "").upper()
    if subtype == "FLOODWAY":
        return "floodway"
    if "0.2 PCT" in subtype:
        return "moderate"
    if subtype.startswith("AREA OF MINIMAL"):
        return "minimal"
    if zone == "AE":
        return "ae"
    if zone == "A":
        return "a"
    return "other"


def esri_rings_to_shape(rings: list[list[list[float]]]) -> Polygon | MultiPolygon:
    """Convert an Esri polygon ring list. Exterior rings are clockwise."""
    polygons: list[Polygon] = []
    shell: list[list[float]] | None = None
    holes: list[list[list[float]]] = []
    for ring in rings:
        if _is_clockwise(ring):
            if shell is not None:
                polygons.append(Polygon(shell, holes))
            shell = ring
            holes = []
        elif shell is None:
            shell = ring
        else:
            holes.append(ring)
    if shell is not None:
        polygons.append(Polygon(shell, holes))
    if not polygons:
        return Polygon()
    if len(polygons) == 1:
        return polygons[0]
    return MultiPolygon(polygons)


def prepare_zone_frame(zones: gpd.GeoDataFrame, boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Clip source zones to the municipality and require the analysis CRS.

    ``zones`` must already carry the NFHL horizontal CRS, EPSG:4269.
    Lengths are not computed here. A missing CRS is refused.
    """
    require_crs(zones.crs, SOURCE_HORIZONTAL_CRS, "NFHL flood zones")
    require_crs(boundary.crs, SOURCE_HORIZONTAL_CRS, "municipal boundary")
    cleaned = zones.copy()
    cleaned["geometry"] = cleaned.geometry.map(_polygonal)
    cleaned = cleaned[~cleaned.geometry.is_empty].copy()
    clipped = gpd.clip(cleaned, boundary)
    clipped["geometry"] = clipped.geometry.map(_polygonal)
    clipped = clipped[~clipped.geometry.is_empty].copy()
    if clipped.empty:
        raise ValueError("No FEMA flood-hazard polygons intersect Princeton.")
    projected = clipped.to_crs(ANALYSIS_CRS)
    require_crs(projected.crs, ANALYSIS_CRS, "clipped FEMA zones")
    return projected


def intersect_centerlines(centerlines: gpd.GeoDataFrame, zones: gpd.GeoDataFrame) -> dict[str, Any]:
    """Length and count of centerlines inside each flood zone.

    Both frames must be EPSG:3424. Length is the intersection length in US
    survey feet, converted with 1200/3937. Bridge rows are included in that
    length. They do not receive a zone depth, and this function does not
    read or write scenario depths.
    """
    require_crs(centerlines.crs, ANALYSIS_CRS, "centerlines")
    require_crs(zones.crs, ANALYSIS_CRS, "FEMA zones")
    zones = zones.copy()
    zones["zone_label"] = [
        zone_label(zone, subtype)
        for zone, subtype in zip(zones["fld_zone"], zones["zone_subty"], strict=True)
    ]
    zones["fill_class"] = [
        fill_class(zone, subtype)
        for zone, subtype in zip(zones["fld_zone"], zones["zone_subty"], strict=True)
    ]
    lines = centerlines[
        ["centerline_id", "name", "is_bridge", "length_m_inside", "geometry"]
    ].copy()
    pieces = gpd.overlay(
        lines,
        zones[["zone_label", "fld_zone", "zone_subty", "sfha_tf", "dfirm_id", "fill_class", "geometry"]],
        how="intersection",
        keep_geom_type=True,
    )
    if pieces.empty:
        piece_rows: list[dict[str, Any]] = []
    else:
        pieces = pieces[pieces.geometry.geom_type.isin(["LineString", "MultiLineString"])].copy()
        pieces["length_m"] = pieces.geometry.length.map(lambda length: us_survey_feet_to_m(float(length)))
        pieces = pieces[pieces["length_m"] >= MIN_PIECE_M]
        piece_rows = pieces.to_dict("records")

    by_line: dict[str, dict[str, Any]] = {}
    for record in lines.to_dict("records"):
        by_line[str(record["centerline_id"])] = {
            "centerline_id": str(record["centerline_id"]),
            "name": None if record["name"] is None else str(record["name"]),
            "is_bridge": bool(record["is_bridge"]),
            "length_m_inside": round(float(record["length_m_inside"]), 1),
            "zones": {},
            "zone_depth_m": None,
        }
    for piece in piece_rows:
        line_id = str(piece["centerline_id"])
        label = str(piece["zone_label"])
        bucket = by_line[line_id]["zones"].setdefault(
            label,
            {
                "zone": label,
                "fld_zone": piece["fld_zone"],
                "zone_subty": _blank(piece["zone_subty"]),
                "sfha": _sfha(piece["sfha_tf"]),
                "dfirm_id": piece["dfirm_id"],
                "fill_class": piece["fill_class"],
                "length_m": 0.0,
            },
        )
        bucket["length_m"] += float(piece["length_m"])

    centerline_rows = []
    for item in by_line.values():
        zones_for_line = sorted(item["zones"].values(), key=lambda row: (-row["length_m"], row["zone"]))
        for zone_row in zones_for_line:
            zone_row["length_m"] = round(zone_row["length_m"], 1)
            zone_row["zone_depth_m"] = None
        item["zones"] = zones_for_line
        item["zone_depth_m"] = None
        centerline_rows.append(item)

    zone_totals: dict[str, dict[str, Any]] = {}
    for item in centerline_rows:
        for zone_row in item["zones"]:
            total = zone_totals.setdefault(
                zone_row["zone"],
                {
                    "zone": zone_row["zone"],
                    "fld_zone": zone_row["fld_zone"],
                    "zone_subty": zone_row["zone_subty"],
                    "sfha": zone_row["sfha"],
                    "fill_class": zone_row["fill_class"],
                    "length_m": 0.0,
                    "n_centerlines": 0,
                    "n_bridge_centerlines": 0,
                    "zone_depth_m": None,
                },
            )
            total["length_m"] += float(zone_row["length_m"])
            total["n_centerlines"] += 1
            if item["is_bridge"]:
                total["n_bridge_centerlines"] += 1
    for total in zone_totals.values():
        total["length_m"] = round(total["length_m"], 1)

    order = {"floodway": 0, "ae": 1, "a": 2, "moderate": 3, "minimal": 4, "other": 5}
    totals = sorted(zone_totals.values(), key=lambda row: (order.get(row["fill_class"], 9), row["zone"]))
    return {
        "product": "fema_nfhl_regulatory_flood_zones",
        "hurricane_ida_depth": False,
        "event_time": None,
        "not_a_scenario_depth": True,
        "zone_depth_assigned": False,
        "rewrites_scenario_depths": False,
        "terrain_under_bridge_used_as_deck": False,
        "regulatory_water_surface_used_as_deck": False,
        "min_piece_m": MIN_PIECE_M,
        "length_crs": ANALYSIS_CRS,
        "length_unit": "metre",
        "length_conversion": "1200/3937",
        "n_centerlines": len(centerline_rows),
        "n_bridge_centerlines": sum(1 for item in centerline_rows if item["is_bridge"]),
        "zones": totals,
        "centerlines": centerline_rows,
    }


def _polygonal(geometry: Any) -> Any:
    """Keep polygonal parts and drop line or point debris from a clip."""
    geometry = make_valid(geometry)
    if geometry.geom_type == "GeometryCollection":
        polygons = [part for part in geometry.geoms if part.geom_type in {"Polygon", "MultiPolygon"}]
        if not polygons:
            return Polygon()
        geometry = polygons[0] if len(polygons) == 1 else MultiPolygon(
            [geom for part in polygons for geom in (part.geoms if part.geom_type == "MultiPolygon" else [part])]
        )
    if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
        return Polygon()
    return geometry


def _is_clockwise(ring: list[list[float]]) -> bool:
    signed = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:], strict=False):
        signed += (x2 - x1) * (y2 + y1)
    return signed > 0


def _text(value: Any) -> str | None:
    return _blank(value)


def _blank(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    if text == "" or text.lower() in {"none", "nan", "<na>"}:
        return None
    return text


def _blank_sentinel(value: float | None) -> float | None:
    if value is None:
        return None
    if abs(float(value) - NFHL_MISSING) < 1e-6:
        return None
    return float(value)


def _sfha(value: Any) -> bool:
    return str(value).strip().upper() == "T"
