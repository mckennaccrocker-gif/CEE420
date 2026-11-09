"""Join published bridge-inventory points to OSM bridge centerlines.

A deck depth is max(0, scenario water surface − deck elevation). The ground
under an OSM bridge tag is not a deck elevation, and this module will not
substitute it. A missing elevation stays ``bridge_deck_unmatched``.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Iterable
from collections.abc import Mapping
from collections.abc import Sequence
from typing import Any

from geospatial.crs import US_SURVEY_FOOT_M

STATUS_UNMATCHED = "bridge_deck_unmatched"
STATUS_SAMPLED = "bridge_deck_sampled"

# A published point is not a survey tie to the OpenStreetMap way. Forty metres
# in EPSG:3424 keeps the Delaware & Raritan Canal structure on the long Quaker
# Road way (about 24 m off the centerline) and leaves the US 206 structure
# beside the short Quaker Road way (about 50 m) unmatched.
JOIN_DISTANCE_M = 40.0
# One deck elevation describes the centerline only when the inventoried span
# is essentially that centerline. A 15 m canal span is not a 2.8 km way.
SPAN_COVERS_CENTERLINE = 0.80

_GENERIC = {
    "ROAD",
    "RD",
    "STREET",
    "ST",
    "LANE",
    "LN",
    "DRIVE",
    "DR",
    "AVENUE",
    "AVE",
    "HIGHWAY",
    "HWY",
    "PIKE",
    "PK",
    "ROUTE",
    "RT",
    "THE",
    "OF",
    "AND",
    "COUNTY",
    "CO",
    # Qualifiers. "OLD NJ 27" must not match a street merely because both say old.
    "OLD",
    "NEW",
    "NORTH",
    "SOUTH",
    "EAST",
    "WEST",
}
_ROUTE = re.compile(r"(US|NJ|CR)\s*0*([0-9]+)")


def _missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and value != value:
        return True
    return False


def decode_nbi_coordinate(text: str, kind: str) -> float | None:
    """Unpack an NBI item 16 or 17 value to decimal degrees.

    Latitude is eight digits, DDMMSSSS. Longitude is nine digits, DDDMMSSSS.
    The seconds field includes hundredths. A blank or all-zero value is missing.
    """
    raw = str(text).strip().strip("'")
    if not raw or set(raw) <= {"0"}:
        return None
    if kind == "lat":
        if len(raw) != 8 or not raw.isdigit():
            raise ValueError(f"NBI latitude must be 8 digits, got {text!r}.")
        degrees, minutes, seconds, hundredths = int(raw[0:2]), int(raw[2:4]), int(raw[4:6]), int(raw[6:8])
        sign = 1.0
    elif kind == "lon":
        if len(raw) != 9 or not raw.isdigit():
            raise ValueError(f"NBI longitude must be 9 digits, got {text!r}.")
        degrees, minutes, seconds, hundredths = int(raw[0:3]), int(raw[3:5]), int(raw[5:7]), int(raw[7:9])
        sign = -1.0
    else:
        raise ValueError("kind must be 'lat' or 'lon'.")
    # A few NBI records store 60 in the seconds field. That is the next minute.
    if seconds == 60:
        seconds = 0
        minutes += 1
    if minutes == 60:
        minutes = 0
        degrees += 1
    if minutes >= 60 or seconds >= 60:
        # The remaining bad values are not a second coordinate format. Skip them
        # rather than invent a decimal-degree reading.
        return None
    magnitude = degrees + minutes / 60.0 + (seconds + hundredths / 100.0) / 3600.0
    return sign * magnitude


def inspection_month(text: str) -> str | None:
    """Item 90 is a month and a two-digit year, such as 623 for June 2023."""
    raw = str(text).strip()
    if not raw or raw in {"0", "00", "000", "0000"}:
        return None
    if not raw.isdigit() or len(raw) not in {3, 4}:
        return None
    month = int(raw[:-2])
    year = 2000 + int(raw[-2:])
    if not 1 <= month <= 12:
        return None
    return f"{year:04d}-{month:02d}"


def route_ids(text: str | None) -> set[str]:
    """Route designators written as 'US 206', 'NJ 27', or 'CR 583'."""
    if not text:
        return set()
    found = set()
    for kind, number in _ROUTE.findall(str(text).upper()):
        found.add(f"{kind} {int(number)}")
    return found


def name_tokens(text: str | None) -> set[str]:
    """Distinctive words. Generic suffixes and bare numbers are dropped."""
    if not text:
        return set()
    parts = re.findall(r"[A-Z0-9]+", str(text).upper().replace("&", " "))
    return {part for part in parts if part not in _GENERIC and not part.isdigit() and len(part) >= 3}


def identity_match(facility: str, osm_name: str | None, osm_ref: str | None) -> str | None:
    """Return how a carried facility matches an OSM centerline, or None.

    An 'OLD' alignment does not inherit the current route number. 'OLD NJ 27'
    is not a match to a centerline whose ref is NJ 27.
    """
    facility_text = str(facility or "")
    routes = set() if re.search(r"\bOLD\b", facility_text.upper()) else route_ids(facility_text)
    if routes & route_ids(osm_ref):
        return "route_ref"
    shared = name_tokens(facility_text) & name_tokens(osm_name)
    if shared:
        return "facility_name"
    return None


def distance_m(line: Any, point: Any) -> float:
    """Metres between an EPSG:3424 line and point. The axis unit is the US survey foot."""
    return float(line.distance(point)) * US_SURVEY_FOOT_M


def depth_above_deck(
    water_surface_m: float | None,
    deck_elevation_m: float | None,
    terrain_elevation_m: float | None = None,
) -> dict[str, Any]:
    """Depth of one scenario water surface over a published deck elevation.

    ``terrain_elevation_m`` is the ground under the bridge. It is never
    written into the deck elevation and never subtracted from the water
    surface. A missing deck elevation or a missing water surface stays
    unmatched. A deck above the water surface has depth 0.
    """
    refused_terrain = terrain_elevation_m is not None and _missing(deck_elevation_m)
    if _missing(deck_elevation_m):
        return {
            "exposure_status": STATUS_UNMATCHED,
            "depth_m": None,
            "deck_elevation_m": None,
            "terrain_used_as_deck": False,
            "terrain_refused": refused_terrain,
            "unmatched_reason": "no_published_deck_elevation",
            "hurricane_ida_depth": False,
            "event_time": None,
        }
    if _missing(water_surface_m):
        return {
            "exposure_status": STATUS_UNMATCHED,
            "depth_m": None,
            "deck_elevation_m": float(deck_elevation_m),
            "terrain_used_as_deck": False,
            "terrain_refused": False,
            "unmatched_reason": "water_surface_undefined",
            "hurricane_ida_depth": False,
            "event_time": None,
        }
    return {
        "exposure_status": STATUS_SAMPLED,
        "depth_m": max(0.0, float(water_surface_m) - float(deck_elevation_m)),
        "deck_elevation_m": float(deck_elevation_m),
        "terrain_used_as_deck": False,
        "terrain_refused": False,
        "unmatched_reason": None,
        "hurricane_ida_depth": False,
        "event_time": None,
    }


def decide_deck(
    *,
    accepted_structures: Sequence[Mapping[str, Any]],
    deck_elevation_m: float | None,
    water_surfaces_m: Mapping[str, float | None] | None,
    length_m_inside: float,
) -> dict[str, Any]:
    """Decide whether one centerline may receive a deck depth.

    The elevation has to be published, tied to exactly one accepted
    structure, and that structure's inventoried length has to cover the
    OSM centerline. The water surface for every requested stage has to be
    defined. Otherwise the centerline stays unmatched and no depth is filled in.
    """
    if length_m_inside <= 0:
        raise ValueError("Inside length must be positive.")
    reasons: list[str] = []
    if _missing(deck_elevation_m):
        reasons.append("no_published_deck_elevation")
    if len(accepted_structures) == 0:
        reasons.append("no_inventory_match")
    elif len(accepted_structures) > 1:
        reasons.append("multiple_structures_on_centerline")
    else:
        span = accepted_structures[0].get("structure_length_m")
        if _missing(span) or float(span) < SPAN_COVERS_CENTERLINE * float(length_m_inside):
            reasons.append("span_shorter_than_centerline")
    surfaces = dict(water_surfaces_m or {})
    if not _missing(deck_elevation_m) and (
        not surfaces or any(_missing(value) for value in surfaces.values())
    ):
        reasons.append("water_surface_undefined")
    if reasons:
        return {
            "exposure_status": STATUS_UNMATCHED,
            "deck_elevation_m": None if _missing(deck_elevation_m) else float(deck_elevation_m),
            "depth_m_by_stage": None,
            "unmatched_reasons": reasons,
            "hurricane_ida_depth": False,
            "event_time": None,
            "terrain_used_as_deck": False,
        }
    depths = {
        stage: max(0.0, float(surfaces[stage]) - float(deck_elevation_m))
        for stage in surfaces
    }
    return {
        "exposure_status": STATUS_SAMPLED,
        "deck_elevation_m": float(deck_elevation_m),
        "depth_m_by_stage": depths,
        "unmatched_reasons": [],
        "hurricane_ida_depth": False,
        "event_time": None,
        "terrain_used_as_deck": False,
    }


def _float_field(text: str) -> float | None:
    raw = str(text).strip()
    if raw == "" or raw.upper() in {"N", "NA"}:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def read_nbi_records(path: Any) -> tuple[list[str], list[dict[str, Any]]]:
    """Read the comma-delimited NBI file. Single quote is the text qualifier."""
    with open(path, newline="", encoding="latin-1") as handle:
        reader = csv.DictReader(handle, quotechar="'")
        if reader.fieldnames is None:
            raise ValueError(f"{path} has no header.")
        columns = list(reader.fieldnames)
        records = []
        skipped = 0
        for row in reader:
            lat = decode_nbi_coordinate(row["LAT_016"], "lat")
            lon = decode_nbi_coordinate(row["LONG_017"], "lon")
            if lat is None or lon is None:
                skipped += 1
                continue
            records.append(
                {
                    "structure_number": row["STRUCTURE_NUMBER_008"].strip(),
                    "county_code": row["COUNTY_CODE_003"].strip(),
                    "facility_carried": row["FACILITY_CARRIED_007"].strip(),
                    "feature_intersected": row["FEATURES_DESC_006A"].strip(),
                    "location": row["LOCATION_009"].strip(),
                    "latitude": lat,
                    "longitude": lon,
                    "structure_length_m": _float_field(row["STRUCTURE_LEN_MT_049"]),
                    "max_span_m": _float_field(row["MAX_SPAN_LEN_MT_048"]),
                    "deck_width_m": _float_field(row["DECK_WIDTH_MT_052"]),
                    "year_built": row["YEAR_BUILT_027"].strip() or None,
                    "year_reconstructed": None
                    if row["YEAR_RECONSTRUCTED_106"].strip() in {"", "0"}
                    else row["YEAR_RECONSTRUCTED_106"].strip(),
                    "inspection_month": inspection_month(row["DATE_OF_INSPECT_090"]),
                    "deck_condition_code": row["DECK_COND_058"].strip() or None,
                    "deck_elevation_m": None,
                }
            )
    return columns, records, skipped


def nbi_has_deck_elevation_column(columns: Iterable[str]) -> bool:
    """True only for a column that is an elevation, not a condition or a width."""
    for name in columns:
        lowered = name.lower()
        if "elev" in lowered or "navd" in lowered or "ngvd" in lowered:
            return True
    return False


def match_centerline(
    *,
    name: str | None,
    ref: str | None,
    line: Any,
    structures: Sequence[Mapping[str, Any]],
    join_distance_m: float = JOIN_DISTANCE_M,
) -> dict[str, Any]:
    """Accept inventory points that share a name or route ref inside the distance cap.

    The nearest point is always reported, including when it is rejected.
    Rejection is not a join.
    """
    if join_distance_m <= 0:
        raise ValueError("The join distance must be positive.")
    ranked: list[dict[str, Any]] = []
    for structure in structures:
        point = structure["geometry"]
        how = identity_match(str(structure["facility_carried"]), name, ref)
        distance = distance_m(line, point)
        ranked.append(
            {
                "structure_number": structure["structure_number"],
                "facility_carried": structure["facility_carried"],
                "feature_intersected": structure["feature_intersected"],
                "location": structure.get("location"),
                "latitude": structure["latitude"],
                "longitude": structure["longitude"],
                "structure_length_m": structure.get("structure_length_m"),
                "max_span_m": structure.get("max_span_m"),
                "deck_width_m": structure.get("deck_width_m"),
                "year_built": structure.get("year_built"),
                "year_reconstructed": structure.get("year_reconstructed"),
                "inspection_month": structure.get("inspection_month"),
                "deck_condition_code": structure.get("deck_condition_code"),
                "deck_elevation_m": structure.get("deck_elevation_m"),
                "distance_m": round(distance, 1),
                "identity": how,
                "accepted": how is not None and distance <= join_distance_m,
            }
        )
    ranked.sort(key=lambda item: item["distance_m"])
    accepted = [item for item in ranked if item["accepted"]]
    nearest = ranked[0] if ranked else None
    return {"accepted_structures": accepted, "nearest_structure": nearest}


def _note(reasons: Sequence[str], accepted: Sequence[Mapping[str, Any]]) -> str:
    sentences = []
    if "no_published_deck_elevation" in reasons:
        sentences.append(
            "No published deck elevation was joined. The ground under the bridge was not used as the deck."
        )
    if "no_inventory_match" in reasons:
        sentences.append(
            "No National Bridge Inventory structure shared this centerline's name or route ref within 40 m."
        )
    if "multiple_structures_on_centerline" in reasons:
        listed = ", ".join(
            f"{item['structure_number']} ({item['structure_length_m']} m)" for item in accepted
        )
        sentences.append(
            f"More than one inventoried structure meets this centerline ({listed}), so one elevation would not describe the OSM way."
        )
    if "span_shorter_than_centerline" in reasons and accepted:
        span = accepted[0].get("structure_length_m")
        sentences.append(
            f"Structure {accepted[0]['structure_number']} is {span} m long, shorter than this OSM centerline, so its elevation would not be applied to the whole way."
        )
    if "water_surface_undefined" in reasons:
        sentences.append("The scenario water surface at this bridge is not defined, so no depth was computed.")
    if not sentences:
        sentences.append(
            "Depth is max(0, scenario water surface minus the published deck elevation)."
        )
    return " ".join(sentences)


def assess_centerline(
    *,
    name: str | None,
    ref: str | None,
    line: Any,
    length_m_inside: float,
    structures: Sequence[Mapping[str, Any]],
    water_surfaces_m: Mapping[str, float | None] | None = None,
    join_distance_m: float = JOIN_DISTANCE_M,
) -> dict[str, Any]:
    """Match inventory points and decide the deck status for one centerline."""
    matched = match_centerline(
        name=name,
        ref=ref,
        line=line,
        structures=structures,
        join_distance_m=join_distance_m,
    )
    elevations = [
        item["deck_elevation_m"]
        for item in matched["accepted_structures"]
        if not _missing(item.get("deck_elevation_m"))
    ]
    # A single published elevation is usable only when exactly one structure was accepted.
    deck_elevation = elevations[0] if len(matched["accepted_structures"]) == 1 and len(elevations) == 1 else None
    decision = decide_deck(
        accepted_structures=matched["accepted_structures"],
        deck_elevation_m=deck_elevation,
        water_surfaces_m=water_surfaces_m,
        length_m_inside=length_m_inside,
    )
    return {
        **matched,
        **decision,
        "note": _note(decision["unmatched_reasons"], matched["accepted_structures"]),
    }
