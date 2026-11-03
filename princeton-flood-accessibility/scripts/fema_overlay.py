"""Regulatory FEMA flood zones for Princeton.

Downloads the effective National Flood Hazard Layer polygons that meet the
municipality, intersects them with the saved centerlines, and writes a
separate overlay. It does not rewrite scenario depths and it does not sample
the terrain under a bridge.

Run from princeton-flood-accessibility:

    python3 scripts/fema_overlay.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from geospatial.crs import proj_pipeline  # noqa: E402
from geospatial.crs import require_crs  # noqa: E402
from geospatial.fema_overlay import ANALYSIS_CRS  # noqa: E402
from geospatial.fema_overlay import MERCER_DFIRM  # noqa: E402
from geospatial.fema_overlay import MERCER_EFFECTIVE_DATE  # noqa: E402
from geospatial.fema_overlay import MERCER_EFFECTIVE_LABEL  # noqa: E402
from geospatial.fema_overlay import SOURCE_HORIZONTAL_CRS  # noqa: E402
from geospatial.fema_overlay import STONY_BROOK_SECTION_M  # noqa: E402
from geospatial.fema_overlay import esri_rings_to_shape  # noqa: E402
from geospatial.fema_overlay import fill_class  # noqa: E402
from geospatial.fema_overlay import intersect_centerlines  # noqa: E402
from geospatial.fema_overlay import prepare_zone_frame  # noqa: E402
from geospatial.fema_overlay import zone_label  # noqa: E402
from network.baseline import _write_geojson  # noqa: E402
from network.roads import load_boundary  # noqa: E402
from network.roads import load_settings  # noqa: E402
from network.roads import resolve  # noqa: E402

NFHL = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer"
ZONE_LAYER = 28
PANEL_LAYER = 3
CROSS_SECTION_LAYER = 14
SCENARIO_KEYS = (
    "exposure_gpkg",
    "exposure_geojson",
    "exposure_stats",
    "accessibility_gpkg",
    "accessibility_geojson",
    "accessibility_stats",
    "bridge_deck_join",
)
USER_AGENT = "CEE420-princeton-flood-accessibility/fema-overlay"


def scenario_hashes(settings: dict[str, Any]) -> dict[str, str]:
    """SHA-256 of the scenario products this overlay must leave untouched."""
    hashes: dict[str, str] = {}
    for key in SCENARIO_KEYS:
        path = resolve(settings, key)
        hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def output_paths(settings: dict[str, Any]) -> list[Path]:
    return [
        resolve(settings, "fema_zones_gpkg"),
        resolve(settings, "fema_zones_geojson"),
        resolve(settings, "fema_overlay"),
        resolve(settings, "fema_provenance"),
    ]


def fetch_zones(boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Query Flood Hazard Zones for the municipal envelope. Source CRS is EPSG:4269."""
    envelope = _envelope(boundary)
    payload = _query(
        ZONE_LAYER,
        geometry=envelope,
        out_fields="DFIRM_ID,FLD_ZONE,ZONE_SUBTY,SFHA_TF,STATIC_BFE,V_DATUM,LEN_UNIT,SOURCE_CIT,FLD_AR_ID,STUDY_TYP",
    )
    features = payload.get("features") or []
    if payload.get("exceededTransferLimit"):
        raise RuntimeError("The NFHL zone query was truncated. Refusing a partial download.")
    if not features:
        raise RuntimeError("The NFHL zone query returned no polygons.")
    spatial = payload.get("spatialReference") or {}
    wkid = spatial.get("latestWkid") or spatial.get("wkid")
    if wkid != 4269:
        raise RuntimeError(f"NFHL returned horizontal CRS {wkid}, not EPSG:4269.")
    rows = []
    for feature in features:
        attributes = feature["attributes"]
        rows.append(
            {
                "dfirm_id": attributes.get("DFIRM_ID"),
                "fld_zone": attributes.get("FLD_ZONE"),
                "zone_subty": attributes.get("ZONE_SUBTY"),
                "sfha_tf": attributes.get("SFHA_TF"),
                "static_bfe": attributes.get("STATIC_BFE"),
                "v_datum": attributes.get("V_DATUM"),
                "len_unit": attributes.get("LEN_UNIT"),
                "source_cit": attributes.get("SOURCE_CIT"),
                "fld_ar_id": attributes.get("FLD_AR_ID"),
                "study_typ": attributes.get("STUDY_TYP"),
                "geometry": esri_rings_to_shape(feature["geometry"]["rings"]),
            }
        )
    frame = gpd.GeoDataFrame(rows, geometry="geometry", crs=SOURCE_HORIZONTAL_CRS)
    require_crs(frame.crs, SOURCE_HORIZONTAL_CRS, "downloaded NFHL zones")
    return frame


def fetch_mercer_effective_date(boundary: gpd.GeoDataFrame) -> dict[str, Any]:
    """Read FIRM panel effective dates for Mercer DFIRM 34021C over Princeton."""
    payload = _query(
        PANEL_LAYER,
        geometry=_envelope(boundary),
        out_fields="DFIRM_ID,FIRM_PAN,EFF_DATE,PANEL,SUFFIX",
        where=f"DFIRM_ID='{MERCER_DFIRM}'",
        return_geometry=False,
    )
    dates: set[str] = set()
    panels: list[str] = []
    for feature in payload.get("features") or []:
        attributes = feature["attributes"]
        dates.add(_epoch_day(attributes.get("EFF_DATE")))
        panels.append(str(attributes.get("FIRM_PAN")))
    if dates != {MERCER_EFFECTIVE_DATE}:
        raise RuntimeError(f"Mercer panels are effective on {sorted(dates)}, not only {MERCER_EFFECTIVE_DATE}.")
    return {
        "dfirm_id": MERCER_DFIRM,
        "effective_date": MERCER_EFFECTIVE_DATE,
        "effective_date_label": MERCER_EFFECTIVE_LABEL,
        "n_panels": len(panels),
        "panels": sorted(panels),
        "suffix": "F",
    }


def fetch_section_m(boundary: gpd.GeoDataFrame) -> dict[str, Any]:
    """Read Stony Brook cross section M. The water surface must be the published 65.5 ft."""
    del boundary
    where = "DFIRM_ID='34021C' AND WTR_NM='Stony Brook' AND XS_LTR='M' AND STREAM_STN=22120"
    payload = _query(
        CROSS_SECTION_LAYER,
        geometry="-74.70,40.30,-74.66,40.32",
        out_fields="DFIRM_ID,WTR_NM,XS_LTR,STREAM_STN,WSEL_REG,LEN_UNIT,V_DATUM",
        where=where,
        return_geometry=True,
    )
    features = payload.get("features") or []
    if len(features) != 1:
        raise RuntimeError(f"Expected one Stony Brook cross section M, found {len(features)}.")
    attributes = features[0]["attributes"]
    value = float(attributes["WSEL_REG"])
    datum = str(attributes.get("V_DATUM") or "").replace(" ", "").upper()
    if value != 65.5 or datum != "NAVD88" or str(attributes.get("LEN_UNIT")) != "Feet":
        raise RuntimeError(
            "NFHL cross section M did not state 65.5 feet NAVD88. "
            f"Got {value} {attributes.get('LEN_UNIT')} {attributes.get('V_DATUM')}."
        )
    geometry = esri_paths_to_geojson(features[0]["geometry"]["paths"])
    record = dict(STONY_BROOK_SECTION_M)
    record["sources"] = [
        {
            "name": "NFHL Cross-Sections, Flood Hazard Zones companion layer",
            "url": f"{NFHL}/{CROSS_SECTION_LAYER}",
            "dfirm_id": attributes.get("DFIRM_ID"),
            "field": "WSEL_REG",
            "len_unit": attributes.get("LEN_UNIT"),
            "v_datum": attributes.get("V_DATUM"),
            "wtr_nm": attributes.get("WTR_NM"),
            "xs_ltr": attributes.get("XS_LTR"),
            "stream_stn": attributes.get("STREAM_STN"),
        },
        {
            "name": "FEMA Flood Insurance Study 34021, Table 10, Stony Brook cross section M",
            "url": "https://map1.msc.fema.gov/data/34/S/PDF/34021CV001A.pdf",
            "profile_panel_url": "https://map1.msc.fema.gov/data/34/S/PDF/34021CV003A.pdf",
            "effective_date": MERCER_EFFECTIVE_DATE,
            "column": "BASE FLOOD WATER-SURFACE ELEVATION, REGULATORY",
        },
    ]
    record["geometry_epsg4269"] = geometry
    return record


def build_overlay(settings: dict[str, Any], zones: gpd.GeoDataFrame, section_m: dict[str, Any], panels: dict[str, Any]) -> dict[str, Any]:
    """Intersect saved centerlines. Reads the network. Does not open scenario outputs for writing."""
    boundary = load_boundary(resolve(settings, "boundary")).to_crs(SOURCE_HORIZONTAL_CRS)
    prepared = prepare_zone_frame(zones, boundary)
    centerlines = _centerlines(settings)
    summary = intersect_centerlines(centerlines, prepared)
    summary["layer_label"] = f"Regulatory FEMA flood zones, effective {MERCER_EFFECTIVE_LABEL}"
    summary["regulatory"] = True
    summary["effective_date"] = panels["effective_date"]
    summary["effective_date_label"] = panels["effective_date_label"]
    summary["source"] = {
        "service": f"{NFHL}/{ZONE_LAYER}",
        "layer_name": "Flood Hazard Zones",
        "horizontal_crs": SOURCE_HORIZONTAL_CRS,
        "horizontal_datum": "NAD83",
        "analysis_crs": ANALYSIS_CRS,
        "proj_pipeline_4269_to_3424": proj_pipeline(SOURCE_HORIZONTAL_CRS, ANALYSIS_CRS),
        "dfirm_id": MERCER_DFIRM,
        "firm_panels": panels,
        "vertical_datum_on_zone_polygons": None,
        "static_bfe_populated": False,
        "static_bfe_sentinel": -9999,
        "note": (
            "Zone polygons in this extract have no populated vertical datum and no static base flood elevation. "
            "The only water-surface number kept from the regulatory study is Stony Brook cross section M."
        ),
    }
    summary["regulatory_water_surface"] = {
        key: value for key, value in section_m.items() if key != "geometry_epsg4269"
    }
    summary["regulatory_water_surface_geometry"] = _section_geometry_4326(section_m["geometry_epsg4269"])
    summary["zone_polygon_area_m2"] = _zone_areas(prepared)
    summary["neighbor_firms"] = neighbor_firm_lengths(summary)
    summary["neighbor_firm_note"] = _neighbor_note(summary["neighbor_firms"])
    summary["scenario_files_sha256"] = scenario_hashes(settings)
    _write_zones(settings, prepared, panels)
    return summary


def main() -> None:
    settings = load_settings()
    before = scenario_hashes(settings)
    boundary = load_boundary(resolve(settings, "boundary"))
    retrieved = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    zones = fetch_zones(boundary)
    panels = fetch_mercer_effective_date(boundary)
    section_m = fetch_section_m(boundary)
    summary = build_overlay(settings, zones, section_m, panels)
    summary["retrieved_at_utc"] = retrieved
    after = scenario_hashes(settings)
    if before != after:
        raise RuntimeError("FEMA overlay changed a scenario file. The write was refused.")
    path = resolve(settings, "fema_overlay")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    provenance = {
        "retrieved_at_utc": retrieved,
        "source_service": f"{NFHL}/{ZONE_LAYER}",
        "source_horizontal_crs": SOURCE_HORIZONTAL_CRS,
        "source_horizontal_datum": "NAD83",
        "n_polygons_in_envelope": int(len(zones)),
        "firm_panels": panels,
        "regulatory_water_surface_ft": 65.5,
        "regulatory_water_surface_datum": "NAVD 88",
        "regulatory_water_surface_units": "feet",
        "not_a_deck_elevation": True,
        "hurricane_ida_depth": False,
        "scenario_files_sha256": after,
    }
    resolve(settings, "fema_provenance").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print(
        f"Regulatory FEMA zones, effective {MERCER_EFFECTIVE_LABEL}. "
        f"{summary['n_centerlines']} centerlines. Zone depth assigned: {summary['zone_depth_assigned']}."
    )
    for zone in summary["zones"]:
        print(f"  {zone['zone']}: {zone['length_m']} m, {zone['n_centerlines']} centerlines")


def neighbor_firm_lengths(summary: dict[str, Any]) -> list[dict[str, Any]]:
    """Centerline length whose flood polygon is not the Mercer DFIRM.

    The northwest municipal line meets Somerset panels 34035C0238E and
    34035C0239E, effective 28 September 2007. That date was read from NFHL
    layer 3 on 3 November 2026. It is not applied to the Mercer panels.
    """
    totals: dict[str, dict[str, Any]] = {}
    for item in summary["centerlines"]:
        for zone in item["zones"]:
            dfirm = zone.get("dfirm_id")
            if dfirm == MERCER_DFIRM:
                continue
            bucket = totals.setdefault(
                dfirm,
                {"dfirm_id": dfirm, "length_m": 0.0, "n_centerlines": 0, "zones": set()},
            )
            bucket["length_m"] += float(zone["length_m"])
            bucket["n_centerlines"] += 1
            bucket["zones"].add(zone["zone"])
    rows = []
    for bucket in totals.values():
        rows.append(
            {
                "dfirm_id": bucket["dfirm_id"],
                "length_m": round(bucket["length_m"], 1),
                "n_centerlines": bucket["n_centerlines"],
                "zones": sorted(bucket["zones"]),
                "mercer_effective_date_applies": False,
            }
        )
    rows.sort(key=lambda item: item["dfirm_id"])
    return rows


def _neighbor_note(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "Every centerline piece falls in Mercer DFIRM 34021C."
    parts = []
    for row in rows:
        zones = ", ".join(row["zones"])
        parts.append(
            f"{row['length_m']} m of centerline falls in DFIRM {row['dfirm_id']} ({zones}). "
            "The Mercer panel date is not applied to that piece."
        )
    parts.append(
        "Panels 34035C0238E and 34035C0239E at the northwest corner are Somerset County, "
        "effective 28 September 2007. A 3.9 m² Middlesex DFIRM 34023C floodway sliver contains no centerline length."
    )
    return " ".join(parts)


def _centerlines(settings: dict[str, Any]) -> gpd.GeoDataFrame:
    frame = gpd.read_file(resolve(settings, "gpkg"), layer="centerlines")
    require_crs(frame.crs, ANALYSIS_CRS, "saved centerlines")
    frame = frame.copy()
    frame["centerline_id"] = frame.apply(_identity, axis=1)
    frame["is_bridge"] = frame["is_bridge"].map(lambda value: str(value).lower() in {"true", "1", "yes"})
    frame["name"] = frame["name"].map(lambda value: None if pd.isna(value) else str(value))
    expected = _expected_ids(settings)
    found = set(frame["centerline_id"])
    if found != expected:
        raise RuntimeError(
            f"Centerline ids do not match the saved accessibility file ({len(found)} vs {len(expected)})."
        )
    return frame


def _identity(row: pd.Series) -> str:
    osmid = row["osmid"]
    if _is_number(osmid) and float(osmid).is_integer():
        osmid_text = str(int(osmid))
    else:
        osmid_text = str(osmid)
    return f"{int(row['u'])}_{int(row['v'])}_{int(row['key'])}_{osmid_text}"


def _expected_ids(settings: dict[str, Any]) -> set[str]:
    payload = json.loads(resolve(settings, "accessibility_geojson").read_text(encoding="utf-8"))
    return {feature["properties"]["centerline_id"] for feature in payload["features"]}


def _write_zones(settings: dict[str, Any], zones: gpd.GeoDataFrame, panels: dict[str, Any]) -> None:
    """Write the overlay geometries. Scenario paths are not in this list."""
    frame = zones.copy()
    frame["zone_label"] = [
        zone_label(zone, subtype) for zone, subtype in zip(frame["fld_zone"], frame["zone_subty"], strict=True)
    ]
    frame["fill_class"] = [
        fill_class(zone, subtype) for zone, subtype in zip(frame["fld_zone"], frame["zone_subty"], strict=True)
    ]
    frame["regulatory"] = True
    frame["effective_date"] = [
        panels["effective_date"] if dfirm == MERCER_DFIRM else None for dfirm in frame["dfirm_id"]
    ]
    frame["hurricane_ida_depth"] = False
    frame["zone_depth_m"] = None
    frame["static_bfe"] = frame["static_bfe"].map(lambda value: None if value is None or float(value) == -9999 else float(value))
    keep = [
        "dfirm_id",
        "fld_zone",
        "zone_subty",
        "zone_label",
        "fill_class",
        "sfha_tf",
        "static_bfe",
        "v_datum",
        "fld_ar_id",
        "regulatory",
        "effective_date",
        "hurricane_ida_depth",
        "zone_depth_m",
        "geometry",
    ]
    frame = frame[keep]
    gpkg = resolve(settings, "fema_zones_gpkg")
    gpkg.parent.mkdir(parents=True, exist_ok=True)
    if gpkg.exists():
        gpkg.unlink()
    frame.to_file(gpkg, layer="zones", driver="GPKG")
    _write_geojson(resolve(settings, "fema_zones_geojson"), frame)
    written = set(output_paths(settings))
    forbidden = {resolve(settings, key) for key in SCENARIO_KEYS}
    if written & forbidden:
        raise RuntimeError("The overlay output list includes a scenario file.")


def _zone_areas(zones: gpd.GeoDataFrame) -> list[dict[str, Any]]:
    frame = zones.copy()
    frame["zone_label"] = [
        zone_label(zone, subtype) for zone, subtype in zip(frame["fld_zone"], frame["zone_subty"], strict=True)
    ]
    # geometry.area is square US survey feet. Convert with the square of 1200/3937.
    factor = (1200 / 3937) ** 2
    frame["area_m2"] = frame.geometry.area.map(lambda area: float(area) * factor)
    grouped = frame.groupby(["zone_label", "dfirm_id"], dropna=False)["area_m2"].sum()
    rows = []
    for (label, dfirm), area in grouped.items():
        rows.append({"zone": label, "dfirm_id": dfirm, "area_m2": round(float(area), 1)})
    rows.sort(key=lambda item: (-item["area_m2"], item["zone"]))
    return rows


def _section_geometry_4326(geometry: dict[str, Any]) -> dict[str, Any]:
    transformer = Transformer.from_crs(SOURCE_HORIZONTAL_CRS, "EPSG:4326", always_xy=True)
    coordinates = []
    for ring in geometry["coordinates"]:
        coordinates.append([list(transformer.transform(x, y)) for x, y in ring])
    return {"type": "MultiLineString", "coordinates": _round_lines(coordinates)}


def _round_lines(lines: list[list[list[float]]]) -> list[list[list[float]]]:
    return [[[round(x, 6), round(y, 6)] for x, y in line] for line in lines]


def esri_paths_to_geojson(paths: list[list[list[float]]]) -> dict[str, Any]:
    return {"type": "MultiLineString", "coordinates": paths}


def _query(
    layer: int,
    *,
    geometry: str,
    out_fields: str,
    where: str = "1=1",
    return_geometry: bool = True,
) -> dict[str, Any]:
    params = {
        "where": where,
        "geometry": geometry,
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": out_fields,
        "returnGeometry": "true" if return_geometry else "false",
        "outSR": "4269",
        "resultRecordCount": "2000",
        "f": "json",
    }
    url = f"{NFHL}/{layer}/query?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=90) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if "error" in payload:
        raise RuntimeError(f"NFHL layer {layer} query failed: {payload['error']}")
    return payload


def _envelope(boundary: gpd.GeoDataFrame) -> str:
    geographic = boundary.to_crs("EPSG:4326")
    minx, miny, maxx, maxy = geographic.total_bounds
    return f"{minx},{miny},{maxx},{maxy}"


def _epoch_day(value: Any) -> str:
    if value is None:
        raise RuntimeError("A FIRM panel has no effective date.")
    instant = datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc)
    return instant.strftime("%Y-%m-%d")


def _is_number(value: object) -> bool:
    try:
        float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return True


if __name__ == "__main__":
    main()
