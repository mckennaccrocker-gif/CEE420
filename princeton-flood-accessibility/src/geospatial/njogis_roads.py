"""Compare NJOGIS road centerlines with the saved OSM drive centerlines.

The OSM graph stays the routable network. This module does not build a
graph, does not assign a flood depth, and does not read a bridge deck or a
terrain elevation. NJOGIS ``ELEVTYP_F`` and ``ELEVTYP_T`` are relative
intersection levels from the NG9-1-1 domain. They are not elevations in a
vertical datum.
"""

from __future__ import annotations

import math
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString
from shapely.geometry import MultiLineString
from shapely.geometry import MultiPolygon
from shapely.geometry import Polygon
from shapely.validation import make_valid

from geospatial.crs import PROJECTED_EPSG
from geospatial.crs import US_SURVEY_FOOT_M
from geospatial.crs import require_crs
from geospatial.crs import us_survey_feet_to_m

ANALYSIS_CRS = f"EPSG:{PROJECTED_EPSG}"
# A neighbor within this distance is nearby. It is not declared the same segment.
PROXIMITY_M = 20.0
MIN_PIECE_M = 0.05
# A name or a centerline shorter than this is kept in the totals and left off the example lists.
EXAMPLE_MIN_M = 50.0
MOSTLY_BEYOND_FRACTION = 0.5

# NENA / Census MTFCC S-series codes published on the hosted layer.
ROAD_CLASS_LABELS = {
    "S1100": "Primary",
    "S1200": "Secondary",
    "S1400": "Local",
    "S1500": "Vehicular Trail",
    "S1630": "Ramp",
    "S1640": "Service Drive",
    "S1710": "Walkway",
    "S1720": "Stairway",
    "S1730": "Alley",
    "S1740": "Private Road Service Vehicles",
    "S1780": "Parking Lot",
    "S1820": "Trail",
    "S1830": "Bridle Path",
    "99999": "Other",
}
# Motor-vehicle classes other than service, private, and parking. Reported
# beside the full total. The full total is the comparison.
DRIVE_LIKE_CLASSES = ("S1100", "S1200", "S1400", "S1630")

ELEVATION_TYPE_LABELS = {
    0: "At Grade",
    1: "Level 1",
    2: "Level 2",
    3: "Level 3",
}

_SUFFIXES = {
    "RD": "ROAD",
    "ST": "STREET",
    "AVE": "AVENUE",
    "AV": "AVENUE",
    "BLVD": "BOULEVARD",
    "DR": "DRIVE",
    "LN": "LANE",
    "CT": "COURT",
    "PL": "PLACE",
    "TER": "TERRACE",
    "TERR": "TERRACE",
    "CIR": "CIRCLE",
    "HWY": "HIGHWAY",
    "PKWY": "PARKWAY",
    "TRL": "TRAIL",
    "WY": "WAY",
}
_UNNAMED = {"", "UNNAMED", "UNNAMED SEGMENT", "NONE", "NULL", "NAN"}


def normalize_road_name(value: Any) -> str | None:
    """Uppercase a street name and expand a trailing abbreviation.

    ``Unnamed Segment`` and a blank name return None. The result is a label
    for agreement, not a segment identifier. A value with several OSM names
    separated by semicolons is handled by ``name_key_tuple``.
    """
    text = _text(value)
    if text is None:
        return None
    cleaned = text.upper().replace("'", "").replace(".", " ").replace("-", " ").replace(",", " ")
    parts = cleaned.split()
    if not parts or " ".join(parts) in _UNNAMED:
        return None
    if parts[-1] in _SUFFIXES:
        parts[-1] = _SUFFIXES[parts[-1]]
    return " ".join(parts)


def name_key_tuple(value: Any) -> tuple[str, ...]:
    """Split an OSM multi-name tag, then normalize each name."""
    text = _text(value)
    if text is None:
        return ()
    keys: list[str] = []
    for piece in str(value).split(";"):
        key = normalize_road_name(piece)
        if key and key not in keys:
            keys.append(key)
    return tuple(keys)


def _stem(name: str) -> str | None:
    parts = name.split()
    if len(parts) > 1 and parts[-1] in set(_SUFFIXES.values()):
        return " ".join(parts[:-1])
    return None


def names_equivalent(left: str, right: str) -> bool:
    """True when two labels are the same name, including a missing street suffix.

    ``Broadmead`` and ``Broadmead Street`` agree. ``Herrontown Lane`` and
    ``Herrontown Road`` do not. Spacing differences do not agree.
    """
    if left == right:
        return True
    left_stem = _stem(left)
    right_stem = _stem(right)
    if left_stem is not None and left_stem == right:
        return True
    if right_stem is not None and right_stem == left:
        return True
    return False


def elevation_level_as_deck(
    elevtyp_from: Any = None,
    elevtyp_to: Any = None,
    terrain_elevation_m: float | None = None,
) -> dict[str, Any]:
    """Refuse to treat a relative level, or a terrain elevation, as a deck.

    The arguments are the values a caller might try to use. None of them
    becomes a deck elevation.
    """
    del terrain_elevation_m
    from_code = _optional_int(elevtyp_from)
    to_code = _optional_int(elevtyp_to)
    return {
        "deck_elevation_m": None,
        "deck_elevation_assigned": False,
        "terrain_elevation_used_as_deck": False,
        "relative_level_used_as_deck": False,
        "bridge_attribute_present": False,
        "elevtyp_from": from_code,
        "elevtyp_to": to_code,
        "elevtyp_from_label": ELEVATION_TYPE_LABELS.get(from_code) if from_code is not None else None,
        "elevtyp_to_label": ELEVATION_TYPE_LABELS.get(to_code) if to_code is not None else None,
        "reason": (
            "ELEVTYP_F and ELEVTYP_T are relative intersection levels "
            "(at grade, level 1, level 2, level 3). They are not elevations "
            "in a vertical datum, and a terrain elevation is not a deck."
        ),
    }


def classify_fields(names: list[str]) -> dict[str, Any]:
    """Say whether the layer has a bridge column or a relative-level column."""
    bridge = [name for name in names if _looks_like_bridge_field(name)]
    levels = [name for name in names if name.upper() in {"ELEVTYP_F", "ELEVTYP_T"}]
    return {
        "bridge_attribute_present": bool(bridge),
        "bridge_fields": bridge,
        "elevation_level_fields": levels,
        "deck_elevation_m": None,
        "terrain_elevation_used_as_deck": False,
        "relative_level_used_as_deck": False,
    }


def clip_centerlines(lines: gpd.GeoDataFrame, boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Intersect centerlines with the municipal polygon in EPSG:3424.

    One input row stays one row. A piece shorter than 0.05 m is dropped.
    ``length_m`` is the clipped length in metres, converted with 1200/3937.
    """
    require_crs(lines.crs, ANALYSIS_CRS, "centerlines")
    require_crs(boundary.crs, ANALYSIS_CRS, "municipal boundary")
    if lines.empty:
        out = lines.copy()
        out["length_m"] = pd.Series(dtype=float)
        return out
    polygon = _as_polygon(boundary.geometry.union_all())
    clipped = lines.copy()
    clipped.geometry = [_line_parts(geom.intersection(polygon)) for geom in clipped.geometry]
    clipped["length_m"] = clipped.geometry.length.map(us_survey_feet_to_m)
    keep = clipped.geometry.geom_type.isin(["LineString", "MultiLineString"]) & (clipped["length_m"] >= MIN_PIECE_M)
    return clipped.loc[keep].reset_index(drop=True)


def summarize_clip(lines: gpd.GeoDataFrame, field_names: list[str]) -> dict[str, Any]:
    """Length, count, road class, and the elevation-level codes on a clip."""
    require_crs(lines.crs, ANALYSIS_CRS, "clipped NJOGIS centerlines")
    if "length_m" not in lines.columns:
        raise ValueError("Clipped centerlines need length_m.")
    roles = classify_fields(field_names)
    refused = elevation_level_as_deck()
    classes = _class_rows(lines)
    drive_like = lines[lines["road_class"].isin(DRIVE_LIKE_CLASSES)] if "road_class" in lines.columns else lines.iloc[0:0]
    raised = _raised_rows(lines)
    return {
        "n_centerlines": int(len(lines)),
        "length_m": float(lines["length_m"].sum()) if len(lines) else 0.0,
        "drive_like_n_centerlines": int(len(drive_like)),
        "drive_like_length_m": float(drive_like["length_m"].sum()) if len(drive_like) else 0.0,
        "drive_like_classes": list(DRIVE_LIKE_CLASSES),
        "road_classes": classes,
        "status_counts": _value_counts(lines, "status_type"),
        "access_counts": _value_counts(lines, "access_type"),
        "elevation_level_counts": _elevation_counts(lines),
        "raised_centerlines": raised,
        "bridge_attribute_present": roles["bridge_attribute_present"],
        "bridge_fields": roles["bridge_fields"],
        "elevation_level_fields": roles["elevation_level_fields"],
        "deck_elevation_m": refused["deck_elevation_m"],
        "deck_elevation_assigned": False,
        "terrain_elevation_used_as_deck": False,
        "relative_level_used_as_deck": False,
        "elevation_level_reason": refused["reason"],
    }


def compare_centerlines(
    osm: gpd.GeoDataFrame,
    njogis: gpd.GeoDataFrame,
    *,
    proximity_m: float = PROXIMITY_M,
) -> dict[str, Any]:
    """Compare two clipped centerline layers without pairing segments.

    A length agrees in name when it lies within ``proximity_m`` of at least
    one centerline whose normalized name is equivalent. An OSM semicolon tag
    contributes each name. A missing street suffix still agrees. A centerline
    may be near several names. Nothing in the result is a chosen partner.
    """
    require_crs(osm.crs, ANALYSIS_CRS, "OSM centerlines")
    require_crs(njogis.crs, ANALYSIS_CRS, "NJOGIS centerlines")
    osm = _with_keys(osm)
    njogis = _with_keys(njogis)
    _require_columns(osm, "OSM centerlines")
    _require_columns(njogis, "NJOGIS centerlines")
    distance_ftus = float(proximity_m) / US_SURVEY_FOOT_M
    osm_side = _coverage(osm, njogis, distance_ftus)
    njogis_side = _coverage(njogis, osm, distance_ftus)
    osm_names = _name_lengths(osm)
    njogis_names = _name_lengths(njogis)
    return {
        "assigns_one_partner": False,
        "proximity_m": float(proximity_m),
        "length_difference_m": njogis_side["length_m"] - osm_side["length_m"],
        "osm": osm_side,
        "njogis": njogis_side,
        "names_only_in_osm": _exclusive_names(osm_names, njogis_names),
        "names_only_in_njogis": _exclusive_names(njogis_names, osm_names),
    }


def nearby_name_keys(geometry: Any, others: gpd.GeoDataFrame, proximity_m: float = PROXIMITY_M) -> set[str]:
    """Normalized names of every other centerline within the proximity.

    The set can contain more than one name. It does not pick a partner.
    """
    require_crs(others.crs, ANALYSIS_CRS, "other centerlines")
    if "name_key" not in others.columns:
        raise ValueError("Other centerlines need name_key.")
    if others.empty:
        return set()
    distance_ftus = float(proximity_m) / US_SURVEY_FOOT_M
    near = others.loc[others.geometry.distance(geometry) <= distance_ftus + 1e-6]
    return {str(key) for key in near["name_key"] if _text(key)}


def _coverage(source: gpd.GeoDataFrame, other: gpd.GeoDataFrame, distance_ftus: float) -> dict[str, Any]:
    within_m, near_named_m, agree_m = _proximity_lengths(source, other, distance_ftus)
    length_m = source["length_m"].astype(float)
    within_m = pd.Series(within_m, index=source.index).clip(upper=length_m)
    near_named_m = pd.Series(near_named_m, index=source.index).clip(upper=within_m)
    agree_m = pd.Series(agree_m, index=source.index).clip(upper=near_named_m)
    beyond_m = length_m - within_m
    fraction = beyond_m / length_m.where(length_m > 0)
    mostly = (fraction >= MOSTLY_BEYOND_FRACTION) & (length_m >= EXAMPLE_MIN_M)
    examples = _beyond_examples(source, beyond_m, length_m, mostly)
    return {
        "n_centerlines": int(len(source)),
        "length_m": float(length_m.sum()),
        "length_m_within_proximity": float(within_m.sum()),
        "length_m_beyond_proximity": float(beyond_m.sum()),
        "length_m_near_named": float(near_named_m.sum()),
        "length_m_name_agrees": float(agree_m.sum()),
        "n_mostly_one_source": int(mostly.sum()),
        "mostly_one_source": examples,
        "unnamed_length_m": float(length_m[_key_column(source).map(lambda keys: len(keys) == 0)].sum()) if len(source) else 0.0,
    }


def _proximity_lengths(
    source: gpd.GeoDataFrame,
    other: gpd.GeoDataFrame,
    distance_ftus: float,
) -> tuple[list[float], list[float], list[float]]:
    if source.empty:
        return [], [], []
    any_buffer = _buffer_union(other.geometry, distance_ftus)
    other_keys = _key_column(other)
    named = other.loc[other_keys.map(lambda keys: len(keys) > 0)]
    named_buffer = _buffer_union(named.geometry, distance_ftus)
    within = _metres(source.geometry.intersection(any_buffer))
    near_named = _metres(source.geometry.intersection(named_buffer))
    agree = _agreement_lengths(source, other, distance_ftus)
    return within, near_named, agree


def _beyond_examples(
    source: gpd.GeoDataFrame,
    beyond_m: pd.Series,
    length_m: pd.Series,
    mostly: pd.Series,
) -> list[dict[str, Any]]:
    rows = []
    name_column = "prime_name" if "prime_name" in source.columns else "name"
    for index in source.index[mostly]:
        rows.append(
            {
                "name": _text(source.at[index, name_column]) if name_column in source.columns else None,
                "name_key": _text(source.at[index, "name_key"]),
                "length_m": float(length_m.at[index]),
                "length_m_beyond_proximity": float(beyond_m.at[index]),
            }
        )
    rows.sort(key=lambda item: (-item["length_m_beyond_proximity"], item["name"] or ""))
    return rows[:15]


def _agreement_lengths(source: gpd.GeoDataFrame, other: gpd.GeoDataFrame, distance_ftus: float) -> list[float]:
    """Length of each source centerline that is near an equivalent name."""
    source_keys = _key_column(source)
    other_keys = _key_column(other)
    buffers: dict[str, Any] = {}
    atomic = {key for keys in other_keys for key in keys}
    for key in atomic:
        mask = other_keys.map(lambda keys, wanted=key: wanted in keys)
        buffers[key] = _buffer_union(other.loc[mask].geometry, distance_ftus)
    matched: dict[str, Any] = {}
    for key in {key for keys in source_keys for key in keys}:
        parts = [buffer for other_key, buffer in buffers.items() if names_equivalent(key, other_key)]
        if parts:
            matched[key] = parts[0] if len(parts) == 1 else gpd.GeoSeries(parts, crs=ANALYSIS_CRS).union_all()
    lengths: list[float] = []
    for geom, keys in zip(source.geometry, source_keys, strict=True):
        parts = [matched[key] for key in keys if key in matched]
        if not parts:
            lengths.append(0.0)
            continue
        cover = parts[0] if len(parts) == 1 else gpd.GeoSeries(parts, crs=ANALYSIS_CRS).union_all()
        lengths.append(us_survey_feet_to_m(geom.intersection(cover).length))
    return lengths


def _with_keys(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    out = frame.copy()
    if "name_keys" not in out.columns:
        if "name_key" not in out.columns:
            raise ValueError("Centerlines need name_key or name_keys.")
        out["name_keys"] = out["name_key"].map(name_key_tuple)
    out["name_keys"] = out["name_keys"].map(lambda value: tuple(value) if isinstance(value, (list, tuple)) else name_key_tuple(value))
    return out


def _key_column(frame: gpd.GeoDataFrame) -> pd.Series:
    if "name_keys" in frame.columns:
        return frame["name_keys"].map(lambda value: tuple(value) if isinstance(value, (list, tuple)) else name_key_tuple(value))
    return frame["name_key"].map(name_key_tuple)


def _name_lengths(frame: gpd.GeoDataFrame) -> dict[str, float]:
    totals: dict[str, float] = {}
    for keys, length in zip(_key_column(frame), frame["length_m"], strict=True):
        for name in keys:
            totals[name] = totals.get(name, 0.0) + float(length)
    return totals


def _exclusive_names(left: dict[str, float], right: dict[str, float]) -> dict[str, Any]:
    other = set(right)
    only = {name: length for name, length in left.items() if not any(names_equivalent(name, candidate) for candidate in other)}
    listed = [
        {"name": name, "length_m": length}
        for name, length in sorted(only.items(), key=lambda item: (-item[1], item[0]))
        if length >= EXAMPLE_MIN_M
    ]
    return {
        "n_names": len(only),
        "length_m": float(sum(only.values())),
        "names_at_least_50_m": listed,
    }


def _class_rows(lines: gpd.GeoDataFrame) -> list[dict[str, Any]]:
    if lines.empty or "road_class" not in lines.columns:
        return []
    grouped = lines.groupby(lines["road_class"].map(_class_code), dropna=False)["length_m"].agg(["sum", "count"])
    rows = []
    for code, row in grouped.iterrows():
        label = ROAD_CLASS_LABELS.get(str(code), str(code))
        rows.append(
            {
                "road_class": None if str(code) == "NONE" else str(code),
                "label": label,
                "n_centerlines": int(row["count"]),
                "length_m": float(row["sum"]),
                "drive_like": str(code) in DRIVE_LIKE_CLASSES,
            }
        )
    rows.sort(key=lambda item: (-item["length_m"], item["label"]))
    return rows


def _raised_rows(lines: gpd.GeoDataFrame) -> list[dict[str, Any]]:
    if lines.empty or "elevtyp_from" not in lines.columns:
        return []
    from_level = lines["elevtyp_from"].map(_optional_int).fillna(-1).astype(int)
    to_level = lines["elevtyp_to"].map(_optional_int).fillna(-1).astype(int)
    raised = lines.loc[(from_level != 0) | (to_level != 0)]
    rows = []
    for _, row in raised.iterrows():
        rows.append(
            {
                "name": _text(row.get("prime_name")),
                "elevtyp_from": _optional_int(row.get("elevtyp_from")),
                "elevtyp_to": _optional_int(row.get("elevtyp_to")),
                "length_m": float(row["length_m"]),
                "deck_elevation_m": None,
            }
        )
    rows.sort(key=lambda item: (-item["length_m"], item["name"] or ""))
    return rows


def _elevation_counts(lines: gpd.GeoDataFrame) -> list[dict[str, Any]]:
    if lines.empty or "elevtyp_from" not in lines.columns:
        return []
    counts: dict[tuple[int | None, int | None], int] = {}
    for from_value, to_value in zip(lines["elevtyp_from"], lines["elevtyp_to"], strict=True):
        key = (_optional_int(from_value), _optional_int(to_value))
        counts[key] = counts.get(key, 0) + 1
    rows = []
    for (from_code, to_code), count in sorted(counts.items(), key=lambda item: (-(item[1]), str(item[0]))):
        rows.append(
            {
                "elevtyp_from": from_code,
                "elevtyp_from_label": ELEVATION_TYPE_LABELS.get(from_code if from_code is not None else -1),
                "elevtyp_to": to_code,
                "elevtyp_to_label": ELEVATION_TYPE_LABELS.get(to_code if to_code is not None else -1),
                "n_centerlines": count,
                "deck_elevation_m": None,
            }
        )
    return rows


def _value_counts(lines: gpd.GeoDataFrame, column: str) -> list[dict[str, Any]]:
    if column not in lines.columns or lines.empty:
        return []
    counts = lines[column].map(lambda value: _text(value) or "blank").value_counts()
    return [{"value": str(value), "n_centerlines": int(count)} for value, count in counts.items()]


def _buffer_union(geometries: Any, distance_ftus: float) -> Any:
    if geometries is None or len(geometries) == 0:
        return Polygon()
    return geometries.buffer(distance_ftus).union_all()


def _metres(geometries: Any) -> list[float]:
    return [us_survey_feet_to_m(geom.length) for geom in geometries]


def _require_columns(frame: gpd.GeoDataFrame, label: str) -> None:
    missing = [column for column in ("length_m", "name_key") if column not in frame.columns]
    if missing:
        raise ValueError(f"{label} need {', '.join(missing)}.")


def _as_polygon(geometry: Any) -> Any:
    geometry = _polygonal(geometry)
    if geometry.is_empty:
        raise ValueError("Municipal boundary has no polygon.")
    return geometry


def _polygonal(geometry: Any) -> Any:
    geometry = make_valid(geometry)
    if geometry.geom_type == "GeometryCollection":
        polygons = [part for part in geometry.geoms if part.geom_type in {"Polygon", "MultiPolygon"}]
        if not polygons:
            return Polygon()
        parts = [geom for part in polygons for geom in (part.geoms if part.geom_type == "MultiPolygon" else [part])]
        geometry = parts[0] if len(parts) == 1 else MultiPolygon(parts)
    if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
        return Polygon()
    return geometry


def _line_parts(geometry: Any) -> Any:
    geometry = make_valid(geometry)
    if geometry.is_empty:
        return LineString()
    if geometry.geom_type == "LineString":
        return geometry
    if geometry.geom_type == "MultiLineString":
        return geometry
    lines: list[LineString] = []
    parts = geometry.geoms if hasattr(geometry, "geoms") else []
    for part in parts:
        if part.geom_type == "LineString" and not part.is_empty:
            lines.append(part)
        elif part.geom_type == "MultiLineString":
            lines.extend(line for line in part.geoms if not line.is_empty)
    if not lines:
        return LineString()
    if len(lines) == 1:
        return lines[0]
    return MultiLineString(lines)


def _class_code(value: Any) -> str:
    text = _text(value)
    return text if text is not None else "NONE"


def _looks_like_bridge_field(name: str) -> bool:
    token = name.upper().replace("-", "_")
    return any(piece in token for piece in ("BRIDGE", "DECK", "LOW_CHORD", "LOWCHORD"))


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if text == "" or text.lower() in {"none", "nan", "<na>"}:
        return None
    return text
