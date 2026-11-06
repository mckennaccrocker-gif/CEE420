"""Download Princeton NJOGIS centerlines and compare them with the OSM graph.

The raw download is written once. Later runs reuse it and do not overwrite
it. The routable graph, the scenario depths, and the FEMA zone lengths are
only hashed. They are not opened for writing.

Run from princeton-flood-accessibility:

    python3 scripts/njogis_roads.py
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
from shapely.geometry import LineString
from shapely.geometry import MultiLineString

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from geospatial.crs import proj_pipeline  # noqa: E402
from geospatial.crs import require_crs  # noqa: E402
from geospatial.njogis_roads import ANALYSIS_CRS  # noqa: E402
from geospatial.njogis_roads import PROXIMITY_M  # noqa: E402
from geospatial.njogis_roads import classify_fields  # noqa: E402
from geospatial.njogis_roads import clip_centerlines  # noqa: E402
from geospatial.njogis_roads import compare_centerlines  # noqa: E402
from geospatial.njogis_roads import name_key_tuple  # noqa: E402
from geospatial.njogis_roads import summarize_clip  # noqa: E402
from network.roads import load_boundary  # noqa: E402
from network.roads import load_settings  # noqa: E402
from network.roads import resolve  # noqa: E402

ITEM_URL = "https://njogis-newjersey.opendata.arcgis.com/maps/fc3d0a95921b4026b386643eef5ff088"
ITEM_ID = "fc3d0a95921b4026b386643eef5ff088"
FEATURE_SERVER = "https://services2.arcgis.com/XVOqAjTOJ5P6ngMu/arcgis/rest/services/Tran_road/FeatureServer"
LAYER_ID = 0
USER_AGENT = "CEE420-princeton-flood-accessibility/njogis-roads"
PAGE_SIZE = 2000
# The municipal envelope is a few thousand segments. Stop before a statewide pull.
MAX_FEATURES = 20000

OUT_FIELDS = ",".join(
    [
        "OBJECTID",
        "RCL_NGUID",
        "GLOBALID",
        "SOURCE",
        "DATEUPDATE",
        "EFFECTIVE",
        "EXPIRE",
        "PRIMENAME",
        "ST_NAME",
        "ST_PREDIR",
        "ST_PRETYP",
        "ST_POSTYP",
        "ST_POSDIR",
        "LST_PNAME",
        "SHLD_TYPE",
        "SHLDSUBTYP",
        "SHLD_NUM",
        "ROADCLASS",
        "ONEWAY",
        "SPEEDLIMIT",
        "JURISDICTN",
        "ELEVTYP_F",
        "ELEVTYP_T",
        "ACCESSSTYP",
        "STATUSTYP",
        "INCMUNI_L",
        "INCMUNI_R",
        "COUNTY_L",
        "COUNTY_R",
        "STATE_L",
        "STATE_R",
        "SRI",
        "Shape__Length",
    ]
)

# Files this comparison must leave byte-for-byte unchanged.
UNCHANGED_PATHS = (
    "data/processed/princeton_drive_network.gpkg",
    "data/processed/princeton_drive_network.graphml",
    "data/processed/princeton_drive_centerlines.geojson",
    "data/processed/princeton_drive_nodes.geojson",
    "data/processed/princeton_drive_edges.geojson",
    "data/processed/baseline_stats.json",
    "data/processed/princeton_centerline_exposure.gpkg",
    "data/processed/princeton_centerline_exposure.geojson",
    "data/processed/flood_exposure_stats.json",
    "data/processed/princeton_accessibility.gpkg",
    "data/processed/princeton_accessibility.geojson",
    "data/processed/accessibility_stats.json",
    "data/processed/bridge_deck_join.json",
    "data/processed/fema_flood_zones.gpkg",
    "data/processed/fema_flood_zones.geojson",
    "data/processed/fema_zone_intersection.json",
    "data/raw/fema_nfhl_princeton.provenance.json",
)


def main() -> None:
    settings = load_settings(ROOT / "config" / "settings.yaml")
    before = _hashes()
    raw_path = resolve(settings, "njogis_raw")
    provenance_path = resolve(settings, "njogis_provenance")
    _refuse_protected_outputs(settings)
    if raw_path.exists():
        if not provenance_path.exists():
            raise SystemExit(f"NJOGIS centerlines exist at {raw_path} but provenance is missing. Refusing to overwrite them.")
        print(f"Using the saved NJOGIS download at {raw_path}")
    else:
        _download(settings)
    after_download = _hashes()
    if after_download != before:
        raise SystemExit("A graph, scenario, or FEMA file changed while reading NJOGIS. Refusing to continue.")
    comparison = _compare(settings, before)
    _write_json(resolve(settings, "njogis_comparison"), _publish(comparison))
    after = _hashes()
    if after != before:
        raise SystemExit("A graph, scenario, or FEMA file changed during the comparison.")
    njogis = comparison["njogis_clip"]
    osm_length = comparison["osm"]["length_m_saved"]
    print("NJOGIS centerlines compared with the saved OSM drive centerlines")
    print(f"  NJOGIS clipped length: {njogis['length_m']:.1f} m ({njogis['n_centerlines']} centerlines)")
    print(f"  OSM inside length: {osm_length:.1f} m ({comparison['osm']['n_centerlines']} centerlines)")
    print(f"  length difference (NJOGIS minus OSM): {comparison['comparison']['length_difference_m']:.1f} m")
    print(f"  bridge attribute: {njogis['bridge_attribute_present']}")
    print(f"  wrote {resolve(settings, 'njogis_comparison')}")


def _download(settings: dict[str, Any]) -> None:
    boundary = load_boundary(resolve(settings, "boundary"))
    envelope = _envelope(boundary)
    layer = _get_json(f"{FEATURE_SERVER}/{LAYER_ID}?f=json")
    spatial = layer.get("extent", {}).get("spatialReference") or layer.get("sourceSpatialReference") or {}
    latest = spatial.get("latestWkid") or spatial.get("wkid")
    if latest != 3424 and spatial.get("wkid") != 102711:
        raise RuntimeError(f"Tran_road spatial reference is {spatial}, not EPSG:3424.")
    field_names = [field["name"] for field in layer.get("fields") or []]
    roles = classify_fields(field_names)
    if roles["bridge_attribute_present"]:
        print(f"  bridge fields on the service: {roles['bridge_fields']}")
    features, page_sr = _fetch_envelope(envelope)
    if not features:
        raise RuntimeError("The NJOGIS query returned no centerlines for the Princeton envelope.")
    frame, has_z = _features_to_frame(features, page_sr)
    boundary_plan = boundary.to_crs(ANALYSIS_CRS)
    require_crs(boundary_plan.crs, ANALYSIS_CRS, "municipal boundary")
    clipped = clip_centerlines(frame, boundary_plan)
    keep = set(clipped["object_id"])
    saved = frame.loc[frame["object_id"].isin(keep)].reset_index(drop=True)
    if saved.empty:
        raise RuntimeError("No NJOGIS centerline intersects the municipal polygon.")
    raw_path = resolve(settings, "njogis_raw")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = raw_path.with_name(raw_path.stem + ".writing.gpkg")
    if temporary.exists():
        temporary.unlink()
    saved.to_file(temporary, layer="centerlines", driver="GPKG")
    temporary.replace(raw_path)
    digest = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    dates = [value for value in saved["date_update"] if isinstance(value, str)]
    provenance = {
        "retrieved_at_utc": _now(),
        "title": "Road Centerlines of NJ, Hosted, 3424",
        "publisher": "New Jersey Office of Information Technology, Office of GIS (NJOGIS)",
        "item_url": ITEM_URL,
        "item_id": ITEM_ID,
        "feature_service": FEATURE_SERVER,
        "layer_id": LAYER_ID,
        "layer_name": layer.get("name") or "Tran_road",
        "service_data_last_edit_utc": _epoch_ms(layer.get("editingInfo", {}).get("dataLastEditDate")),
        "item_modified_utc": _item_modified(),
        "feature_date_update_min": min(dates) if dates else None,
        "feature_date_update_max": max(dates) if dates else None,
        "horizontal_crs": ANALYSIS_CRS,
        "horizontal_crs_name": "NAD83 / New Jersey (ftUS)",
        "horizontal_datum": "NAD83",
        "service_wkid": spatial.get("wkid"),
        "service_latest_wkid": spatial.get("latestWkid"),
        "linear_unit": "US survey foot",
        "length_conversion": "1200/3937",
        "vertical_datum": None,
        "vertical_units": None,
        "has_z": has_z,
        "bridge_attribute_present": roles["bridge_attribute_present"],
        "bridge_fields": roles["bridge_fields"],
        "elevation_level_fields": roles["elevation_level_fields"],
        "elevation_type_domain": _elevation_domain(layer),
        "elevation_type_is_not_an_elevation": True,
        "not_a_deck_elevation": True,
        "terrain_elevation_used_as_deck": False,
        "replaces_routable_graph": False,
        "query": {
            "geometry": envelope,
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "outSR": "3424",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": OUT_FIELDS,
            "where": "1=1",
        },
        "n_features_in_envelope": int(len(frame)),
        "n_features_saved": int(len(saved)),
        "saved_features": "Centerlines whose unclipped geometry intersects the municipal polygon with at least 0.05 m inside it. Geometries in the file are the unclipped source segments.",
        "service_field_names": field_names,
        "sha256": digest,
        "proj_pipeline_4326_to_3424": proj_pipeline("EPSG:4326", ANALYSIS_CRS),
    }
    _write_json(resolve(settings, "njogis_provenance"), provenance)
    print(f"  saved {len(saved)} centerlines from an envelope of {len(frame)}")
    print(f"  service data last edit: {provenance['service_data_last_edit_utc']}")


def _compare(settings: dict[str, Any], hashes: dict[str, str]) -> dict[str, Any]:
    raw = gpd.read_file(resolve(settings, "njogis_raw"))
    require_crs(raw.crs, ANALYSIS_CRS, "saved NJOGIS centerlines")
    provenance = json.loads(resolve(settings, "njogis_provenance").read_text())
    boundary = load_boundary(resolve(settings, "boundary")).to_crs(ANALYSIS_CRS)
    require_crs(boundary.crs, ANALYSIS_CRS, "municipal boundary")
    clipped = clip_centerlines(raw, boundary)
    clipped_path = resolve(settings, "njogis_clipped")
    clipped_path.parent.mkdir(parents=True, exist_ok=True)
    if clipped_path.exists():
        clipped_path.unlink()
    clipped.to_file(clipped_path, layer="centerlines", driver="GPKG")
    osm_raw = gpd.read_file(resolve(settings, "gpkg"), layer="centerlines")
    require_crs(osm_raw.crs, ANALYSIS_CRS, "OSM centerlines")
    saved_osm_length = float(osm_raw["length_m_inside"].sum())
    osm = clip_centerlines(osm_raw, boundary)
    osm["name_keys"] = osm["name"].map(name_key_tuple)
    osm["name_key"] = osm["name_keys"].map(lambda keys: "; ".join(keys) if keys else None)
    osm["prime_name"] = osm["name"]
    clip_sum = float(osm["length_m"].sum())
    if abs(clip_sum - saved_osm_length) > 1.0:
        raise RuntimeError(
            f"Clipping the saved OSM centerlines gave {clip_sum:.1f} m, "
            f"not the saved inside length {saved_osm_length:.1f} m."
        )
    njogis = clipped.copy()
    njogis["name_keys"] = njogis["prime_name"].map(name_key_tuple)
    njogis["name_key"] = njogis["name_keys"].map(lambda keys: "; ".join(keys) if keys else None)
    field_names = list(provenance.get("service_field_names") or raw.columns)
    summary = summarize_clip(njogis, field_names)
    comparison = compare_centerlines(osm, njogis, proximity_m=PROXIMITY_M)
    # The published OSM total is the saved graph length. The clip matched it.
    comparison["osm"]["length_m_saved"] = saved_osm_length
    comparison["length_difference_m"] = summary["length_m"] - saved_osm_length
    return {
        "product": "njogis_osm_centerline_comparison",
        "replaces_routable_graph": False,
        "routable_graph": "osm_drive",
        "hurricane_ida_depth": False,
        "event_time": None,
        "rewrites_scenario_depths": False,
        "rewrites_fema_zone_lengths": False,
        "deck_search_reopened": False,
        "terrain_elevation_used_as_deck": False,
        "relative_level_used_as_deck": False,
        "deck_elevation_assigned": False,
        "crs": ANALYSIS_CRS,
        "crs_name": "NAD83 / New Jersey (ftUS)",
        "linear_unit_of_geometry": "US survey foot",
        "length_unit": "metre",
        "length_conversion": "1200/3937",
        "source": {
            "title": provenance.get("title"),
            "item_url": provenance.get("item_url"),
            "feature_service": f"{FEATURE_SERVER}/{LAYER_ID}",
            "service_data_last_edit_utc": provenance.get("service_data_last_edit_utc"),
            "item_modified_utc": provenance.get("item_modified_utc"),
            "retrieved_at_utc": provenance.get("retrieved_at_utc"),
            "horizontal_crs": provenance.get("horizontal_crs"),
            "horizontal_datum": provenance.get("horizontal_datum"),
            "vertical_datum": None,
            "bridge_attribute_present": provenance.get("bridge_attribute_present"),
            "sha256": provenance.get("sha256"),
        },
        "method": {
            "clip": "Each centerline is intersected with the municipal polygon in EPSG:3424. Length is US survey feet times 1200/3937. A piece under 0.05 m is dropped.",
            "proximity_m": PROXIMITY_M,
            "proximity": (
                "A centerline is near the other source where its clipped geometry "
                "falls inside a 20 m buffer of that source. Twenty metres covers a "
                "lane-scale offset between two digitizations. It is not a segment match."
            ),
            "name_agreement": (
                "Names are uppercased, apostrophes and hyphens are removed, and a "
                "trailing abbreviation such as RD or ST is expanded. An OSM tag with "
                "several names separated by semicolons contributes each name. A name "
                "with no street suffix agrees with the same words plus one suffix, "
                "so Broadmead agrees with Broadmead Street. Different suffixes do not "
                "agree, and a spacing difference does not agree. A length agrees when "
                "it lies within 20 m of at least one equivalent name. A centerline may "
                "be near several names. No centerline is assigned a partner id."
            ),
            "one_source": (
                "Length beyond the 20 m buffer is in one source only for this "
                "proximity. A centerline is listed as mostly one source when at "
                "least half of its clipped length, and at least 50 m, is beyond "
                "the buffer. Names present in one inventory only are a separate "
                "list: the same road can carry two names."
            ),
            "drive_like": (
                "Primary, secondary, local, and ramp (S1100, S1200, S1400, S1630) "
                "are reported beside the full NJOGIS total. The full total is the "
                "length compared with OSM."
            ),
        },
        "njogis_clip": summary,
        "osm": {
            "n_centerlines_saved": int(len(osm_raw)),
            "n_centerlines": int(len(osm)),
            "n_centerlines_below_min_piece": int(len(osm_raw) - len(osm)),
            "length_m": clip_sum,
            "length_m_saved": saved_osm_length,
            "below_min_piece_m": saved_osm_length - clip_sum,
            "source": "data/processed/princeton_drive_network.gpkg layer centerlines",
            "note": (
                "The saved drive graph has one row per centerline, including rows whose "
                "inside length is under 0.05 m. The comparison uses the rows at or above "
                "that cut. Their summed length is the saved inside length."
            ),
        },
        "comparison": comparison,
        "unchanged_files_sha256": hashes,
    }


def _fetch_envelope(envelope: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    features: list[dict[str, Any]] = []
    spatial: dict[str, Any] = {}
    offset = 0
    while offset < MAX_FEATURES:
        payload = _query(envelope, offset)
        if "error" in payload:
            raise RuntimeError(f"NJOGIS query failed: {payload['error']}")
        spatial = payload.get("spatialReference") or spatial
        batch = payload.get("features") or []
        features.extend(batch)
        if not batch or not payload.get("exceededTransferLimit"):
            break
        offset += len(batch)
    if offset >= MAX_FEATURES:
        raise RuntimeError("The NJOGIS query exceeded the Princeton envelope cap. Refusing a statewide download.")
    latest = spatial.get("latestWkid") or spatial.get("wkid")
    if latest not in {3424, 102711}:
        raise RuntimeError(f"NJOGIS returned CRS {spatial}, not EPSG:3424.")
    return features, spatial


def _features_to_frame(features: list[dict[str, Any]], spatial: dict[str, Any]) -> tuple[gpd.GeoDataFrame, bool]:
    del spatial
    rows = []
    has_z = False
    seen: set[int] = set()
    for feature in features:
        attributes = feature.get("attributes") or {}
        object_id = attributes.get("OBJECTID")
        if object_id in seen:
            continue
        seen.add(object_id)
        geometry, feature_z = _paths_to_geometry((feature.get("geometry") or {}).get("paths") or [])
        has_z = has_z or feature_z
        if geometry.is_empty:
            continue
        rows.append(
            {
                "object_id": object_id,
                "rcl_nguid": attributes.get("RCL_NGUID"),
                "global_id": attributes.get("GLOBALID"),
                "source": attributes.get("SOURCE"),
                "date_update": _epoch_ms(attributes.get("DATEUPDATE")),
                "effective": _epoch_ms(attributes.get("EFFECTIVE")),
                "expire": _epoch_ms(attributes.get("EXPIRE")),
                "prime_name": attributes.get("PRIMENAME"),
                "street_name": attributes.get("ST_NAME"),
                "street_pre_dir": attributes.get("ST_PREDIR"),
                "street_pre_type": attributes.get("ST_PRETYP"),
                "street_post_type": attributes.get("ST_POSTYP"),
                "street_post_dir": attributes.get("ST_POSDIR"),
                "legacy_prime_name": attributes.get("LST_PNAME"),
                "shield_type": attributes.get("SHLD_TYPE"),
                "shield_subtype": attributes.get("SHLDSUBTYP"),
                "shield_number": attributes.get("SHLD_NUM"),
                "road_class": attributes.get("ROADCLASS"),
                "oneway": attributes.get("ONEWAY"),
                "speed_limit": attributes.get("SPEEDLIMIT"),
                "jurisdiction": attributes.get("JURISDICTN"),
                "elevtyp_from": attributes.get("ELEVTYP_F"),
                "elevtyp_to": attributes.get("ELEVTYP_T"),
                "access_type": attributes.get("ACCESSSTYP"),
                "status_type": attributes.get("STATUSTYP"),
                "muni_left": attributes.get("INCMUNI_L"),
                "muni_right": attributes.get("INCMUNI_R"),
                "county_left": attributes.get("COUNTY_L"),
                "county_right": attributes.get("COUNTY_R"),
                "state_left": attributes.get("STATE_L"),
                "state_right": attributes.get("STATE_R"),
                "sri": attributes.get("SRI"),
                "shape_length_ftus": attributes.get("Shape__Length"),
                "geometry": geometry,
            }
        )
    if not rows:
        raise RuntimeError("NJOGIS features had no line geometry.")
    frame = gpd.GeoDataFrame(rows, geometry="geometry", crs=ANALYSIS_CRS)
    require_crs(frame.crs, ANALYSIS_CRS, "downloaded NJOGIS centerlines")
    sample_x = float(frame.geometry.iloc[0].interpolate(0.5, normalized=True).x)
    if sample_x < 1000:
        raise RuntimeError(f"A sample easting is {sample_x}. Expected EPSG:3424 feet, not degrees.")
    return frame, has_z


def _query(envelope: str, offset: int) -> dict[str, Any]:
    params = {
        "where": "1=1",
        "geometry": envelope,
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": OUT_FIELDS,
        "returnGeometry": "true",
        "outSR": "3424",
        "orderByFields": "OBJECTID",
        "resultOffset": str(offset),
        "resultRecordCount": str(PAGE_SIZE),
        "f": "json",
    }
    url = f"{FEATURE_SERVER}/{LAYER_ID}/query"
    request = urllib.request.Request(url, data=urllib.parse.urlencode(params).encode(), headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def _paths_to_geometry(paths: list[list[list[float]]]) -> tuple[Any, bool]:
    lines: list[LineString] = []
    has_z = False
    for path in paths:
        coordinates = []
        for point in path:
            if len(point) > 2:
                has_z = True
            coordinates.append((float(point[0]), float(point[1])))
        if len(coordinates) >= 2:
            lines.append(LineString(coordinates))
    if not lines:
        return LineString(), has_z
    if len(lines) == 1:
        return lines[0], has_z
    return MultiLineString(lines), has_z


def _elevation_domain(layer: dict[str, Any]) -> list[dict[str, Any]]:
    for field in layer.get("fields") or []:
        if field.get("name") == "ELEVTYP_F":
            domain = field.get("domain") or {}
            return [
                {"code": item.get("code"), "label": item.get("name")}
                for item in domain.get("codedValues") or []
            ]
    return []


def _item_modified() -> str | None:
    payload = _get_json(f"https://www.arcgis.com/sharing/rest/content/items/{ITEM_ID}?f=json")
    return _epoch_ms(payload.get("modified"))


def _get_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=90) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if "error" in payload:
        raise RuntimeError(f"Request failed for {url}: {payload['error']}")
    return payload


def _envelope(boundary: gpd.GeoDataFrame) -> str:
    geographic = boundary.to_crs("EPSG:4326")
    minx, miny, maxx, maxy = geographic.total_bounds
    return f"{minx},{miny},{maxx},{maxy}"


def _hashes() -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in UNCHANGED_PATHS:
        path = ROOT / relative
        hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def _refuse_protected_outputs(settings: dict[str, Any]) -> None:
    outputs = {
        resolve(settings, key).resolve()
        for key in ("njogis_raw", "njogis_provenance", "njogis_clipped", "njogis_comparison")
    }
    protected = {(ROOT / relative).resolve() for relative in UNCHANGED_PATHS}
    overlap = outputs & protected
    if overlap:
        raise RuntimeError(f"NJOGIS outputs overlap protected files: {sorted(overlap)}")


def _epoch_ms(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        instant = datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None
    return instant.strftime("%Y-%m-%dT%H:%M:%SZ")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _publish(value: Any, key: str | None = None) -> Any:
    if isinstance(value, dict):
        return {name: _publish(item, name) for name, item in value.items()}
    if isinstance(value, list):
        return [_publish(item) for item in value]
    if isinstance(value, float) and key and ("length_m" in key or key.endswith("_m")):
        return round(value, 1)
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


if __name__ == "__main__":
    main()
