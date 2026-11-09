"""Scenario accessibility for the two saved depth assumptions.

The +1.0 m and +2.0 m stages are analyzed separately. They are not a time
series and they are not Hurricane Ida. Bridge decks and centerlines with
no channel match stay in the routable graph.

Run from princeton-flood-accessibility:

    python3 scripts/accessibility.py
"""

from __future__ import annotations

import hashlib
import itertools
import json
import sys
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
import osmnx as ox  # noqa: E402
import pandas as pd  # noqa: E402
from shapely import STRtree  # noqa: E402
from shapely import distance as shapely_distance  # noqa: E402
from shapely import points as shapely_points  # noqa: E402

from geospatial.crs import PROJECTED_EPSG  # noqa: E402
from geospatial.crs import US_SURVEY_FOOT_M  # noqa: E402
from geospatial.crs import require_crs  # noqa: E402
from network.disruption import STATUS_CLOSED  # noqa: E402
from network.disruption import bridge_centerline_keys  # noqa: E402
from network.disruption import centerline_key  # noqa: E402
from network.disruption import choose_destinations  # noqa: E402
from network.disruption import closure_decision  # noqa: E402
from network.disruption import component_records  # noqa: E402
from network.disruption import edges_on_many_paths  # noqa: E402
from network.disruption import ordered_weak_components  # noqa: E402
from network.disruption import route_between  # noqa: E402
from network.disruption import without_closed_centerlines  # noqa: E402
from network.roads import load_boundary  # noqa: E402
from network.roads import load_settings  # noqa: E402
from network.roads import resolve  # noqa: E402
from visualization.accessibility_map import save_disruption_map  # noqa: E402

USER_AGENT = "princeton-flood-accessibility/0.1 (CEE420 educational research)"
POI_TAGS = {"amenity": ["hospital", "school", "fire_station", "police", "townhall", "ambulance_station"]}


def main() -> None:
    settings = load_settings()
    _require_scenario(settings)
    exposure = gpd.read_file(resolve(settings, "exposure_gpkg"), layer="centerline_exposure")
    network = gpd.read_file(resolve(settings, "gpkg"), layer="centerlines")
    require_crs(exposure.crs, f"EPSG:{PROJECTED_EPSG}", "exposure")
    require_crs(network.crs, f"EPSG:{PROJECTED_EPSG}", "centerlines")
    graph = ox.load_graphml(resolve(settings, "graphml"))
    if graph.graph.get("crs") != f"EPSG:{PROJECTED_EPSG}":
        raise SystemExit(f"Graph CRS is {graph.graph.get('crs')}; expected EPSG:{PROJECTED_EPSG}.")
    boundary = load_boundary(resolve(settings, "boundary"))
    table = _attach_endpoints(exposure, network)
    stages = [float(value) for value in settings["scenario"]["stage_above_channel_dem_m"]]
    thresholds = [float(value) for value in settings["thresholds"]["depth_m"]]
    fraction = float(settings["accessibility"]["closure_piece_fraction"])
    decisions = {
        stage: _decide(table, stage, fraction=fraction, accessible_below_m=thresholds[0], closed_at_m=thresholds[1])
        for stage in stages
    }
    places = _load_or_fetch_places(settings, boundary)
    chosen = choose_destinations(places)
    snapped = _snap_destinations(graph, chosen["destinations"], float(settings["accessibility"]["destination_snap_max_m"]))
    baseline_routes = _pair_routes(graph, snapped)
    stage_payloads = []
    frames = []
    for stage in stages:
        payload, frame = _one_stage(
            stage,
            table,
            decisions[stage],
            graph,
            baseline_routes,
            snapped,
            settings,
            boundary,
        )
        stage_payloads.append(payload)
        frames.append(frame)
    merged = _merge_stage_frames(table, frames)
    aadt = _aadt_join(settings, boundary, merged, stages)
    stats = _stats(settings, stages, thresholds, fraction, stage_payloads, chosen, snapped, aadt, places)
    _write(settings, merged, boundary, stats, stage_payloads, aadt)
    _print(stats)


def _require_scenario(settings: dict[str, Any]) -> None:
    if settings["scenario"].get("not_a_hurricane_ida_simulation") is not True:
        raise SystemExit("Refusing to run: the scenario is not marked as not-an-Ida-simulation.")
    if settings["thresholds"].get("not_closure_standards") is not True:
        raise SystemExit("Depth thresholds must stay marked as not closure standards.")
    if settings["accessibility"].get("hurricane_ida_depth") is not False:
        raise SystemExit("Accessibility output must keep hurricane_ida_depth false.")


def _attach_endpoints(exposure: gpd.GeoDataFrame, network: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    network = network.copy()
    network["centerline_id"] = [
        f"{int(row.u)}_{int(row.v)}_{int(row.key)}_{row.osmid}"
        for row in network.itertuples(index=False)
    ]
    endpoints = network[["centerline_id", "u", "v"]].drop_duplicates("centerline_id")
    merged = exposure.merge(endpoints, on="centerline_id", how="left")
    if merged["u"].isna().any():
        raise SystemExit("Some exposure centerlines do not match the baseline network.")
    return merged


def _decide(
    table: gpd.GeoDataFrame,
    stage_m: float,
    *,
    fraction: float,
    accessible_below_m: float,
    closed_at_m: float,
) -> pd.DataFrame:
    slug = _slug(stage_m)
    rows = []
    for record in table.itertuples(index=False):
        decision = closure_decision(
            exposure_status=str(record.exposure_status),
            is_bridge=bool(record.is_bridge),
            length_m_inside=record.length_m_inside,
            wet_piece_length_m=getattr(record, f"length_m_at_or_above_0_30_stage_{slug}"),
            between_piece_length_m=getattr(record, f"length_m_between_0_10_and_0_30_stage_{slug}"),
            depth_max_m=getattr(record, f"depth_max_m_stage_{slug}"),
            closure_fraction=fraction,
            accessible_below_m=accessible_below_m,
            closed_at_m=closed_at_m,
        )
        decision["centerline_id"] = record.centerline_id
        rows.append(decision)
    return pd.DataFrame(rows)


def _one_stage(
    stage_m: float,
    table: gpd.GeoDataFrame,
    decisions: pd.DataFrame,
    graph,
    baseline_routes: dict[tuple[str, str], dict[str, Any]],
    snapped: list[dict[str, Any]],
    settings: dict[str, Any],
    boundary: gpd.GeoDataFrame,
) -> tuple[dict[str, Any], pd.DataFrame]:
    del boundary
    slug = _slug(stage_m)
    joined = table.merge(decisions, on="centerline_id", how="left")
    closed_keys = {
        centerline_key(row.u, row.v, row.osmid)
        for row in joined.itertuples(index=False)
        if bool(row.assumed_closed)
    }
    remaining = without_closed_centerlines(graph, closed_keys)
    records = [
        {
            "endpoints": (int(row.u), int(row.v)),
            "length_m_inside": float(row.length_m_inside),
            "assumed_closed": bool(row.assumed_closed),
            "key": centerline_key(row.u, row.v, row.osmid),
        }
        for row in joined.itertuples(index=False)
    ]
    components = component_records(remaining, records)
    node_component = {}
    for index, nodes in enumerate(ordered_weak_components(remaining)):
        for node in nodes:
            node_component[node] = index
    joined[f"component_id_stage_{slug}"] = [
        None if row.assumed_closed else node_component.get(int(row.u))
        for row in joined.itertuples(index=False)
    ]
    bridges = bridge_centerline_keys(remaining)
    scenario_routes = _pair_routes(remaining, snapped)
    path_keys = []
    od_rows = []
    for (origin_name, dest_name), scenario in scenario_routes.items():
        baseline = baseline_routes[(origin_name, dest_name)]
        if scenario["status"] == "connected":
            path_keys.append(scenario["centerline_keys"])
        od_rows.append(_od_row(stage_m, origin_name, dest_name, baseline, scenario))
    many = edges_on_many_paths(path_keys, min_fraction=float(settings["accessibility"]["critical_path_min_fraction"]))
    joined[f"routing_status_stage_{slug}"] = joined["routing_status"]
    joined[f"assumed_closed_stage_{slug}"] = joined["assumed_closed"]
    joined[f"wet_fraction_stage_{slug}"] = joined["wet_fraction_of_inside_length"]
    joined[f"max_based_closure_stage_{slug}"] = joined["max_based_at_or_above_closure_depth"]
    joined[f"graph_bridge_stage_{slug}"] = [
        centerline_key(row.u, row.v, row.osmid) in bridges for row in joined.itertuples(index=False)
    ]
    joined[f"n_od_paths_stage_{slug}"] = [
        many.get(centerline_key(row.u, row.v, row.osmid), 0) for row in joined.itertuples(index=False)
    ]
    inside = float(joined["length_m_inside"].sum())
    closed_length = float(joined.loc[joined["assumed_closed"], "length_m_inside"].sum())
    wet_column = f"length_m_at_or_above_0_30_stage_{slug}"
    between_column = f"length_m_between_0_10_and_0_30_stage_{slug}"
    wet_piece = float(joined[wet_column].fillna(0).sum())
    exposed_piece = wet_piece + float(joined[between_column].fillna(0).sum())
    n_centerlines = int(len(joined))
    n_closed = int(joined["assumed_closed"].sum())
    n_max_based = int(joined["max_based_at_or_above_closure_depth"].sum())
    payload = {
        "stage_above_channel_dem_m": stage_m,
        "hurricane_ida_depth": False,
        "event_time": None,
        "not_a_closure_standard": True,
        "closure_rule": (
            "A centerline is removed only when closure_piece_fraction of its "
            "length inside the municipality is made of pieces at or above the "
            "upper depth cut. The maximum sample is reported separately and "
            "does not by itself close the centerline."
        ),
        "n_centerlines": n_centerlines,
        "n_assumed_closed": n_closed,
        "percent_centerlines_assumed_closed": 100.0 * n_closed / n_centerlines,
        "n_max_based_at_or_above_closure_depth": n_max_based,
        "percent_centerlines_max_based": 100.0 * n_max_based / n_centerlines,
        "length_m_inside": inside,
        "assumed_closed_length_m_inside": closed_length,
        "percent_inside_length_assumed_closed": 100.0 * closed_length / inside,
        "piece_length_m_at_or_above_0_30": wet_piece,
        "percent_inside_length_piece_at_or_above_0_30": 100.0 * wet_piece / inside,
        "piece_length_m_at_or_above_0_10": exposed_piece,
        "percent_inside_length_piece_at_or_above_0_10": 100.0 * exposed_piece / inside,
        "n_weak_components": len(components),
        "components": components,
        "component_note": (
            "Weak-component count is not evidence that a neighborhood is isolated. "
            "A component can be a single node left behind when its only edge is removed."
        ),
        "n_graph_bridge_centerlines": len(bridges),
        "n_centerlines_on_many_od_paths": int((joined[f"n_od_paths_stage_{slug}"] > 0).sum()),
        "routing_status_counts": joined["routing_status"].value_counts().astype(int).to_dict(),
        "od_pairs": od_rows,
    }
    keep = [
        "centerline_id",
        f"routing_status_stage_{slug}",
        f"assumed_closed_stage_{slug}",
        f"wet_fraction_stage_{slug}",
        f"max_based_closure_stage_{slug}",
        f"component_id_stage_{slug}",
        f"graph_bridge_stage_{slug}",
        f"n_od_paths_stage_{slug}",
    ]
    return payload, joined[keep]


def _merge_stage_frames(table: gpd.GeoDataFrame, frames: list[pd.DataFrame]) -> gpd.GeoDataFrame:
    merged = table.copy()
    for frame in frames:
        merged = merged.merge(frame, on="centerline_id", how="left")
    merged["hurricane_ida_depth"] = False
    merged["event_time"] = None
    merged["depth_product"] = table["depth_product"]
    return merged


def _load_or_fetch_places(settings: dict[str, Any], boundary: gpd.GeoDataFrame) -> list[dict[str, Any]]:
    path = resolve(settings, "destinations")
    provenance_path = resolve(settings, "destinations_provenance")
    if not path.is_file():
        _download_places(path, provenance_path, boundary)
    elif not provenance_path.is_file():
        raise SystemExit(f"Destinations exist at {path} but provenance is missing. Refusing to overwrite them.")
    frame = gpd.read_file(path)
    require_crs(frame.crs, "EPSG:4326", "OSM destinations")
    places = []
    for row in frame.itertuples(index=False):
        places.append(
            {
                "osm_id": int(row.osm_id),
                "osm_element": row.osm_element,
                "amenity": row.amenity,
                "name": None if _blank(row.name) else str(row.name),
                "inside": bool(row.inside),
                "lon": float(row.lon),
                "lat": float(row.lat),
            }
        )
    return places


def _download_places(path: Path, provenance_path: Path, boundary: gpd.GeoDataFrame) -> None:
    polygon = boundary.to_crs("EPSG:4326").geometry.iloc[0]
    try:
        raw = ox.features.features_from_polygon(polygon, POI_TAGS)
    except Exception as exc:
        raise SystemExit(
            "OSM destinations could not be downloaded. No facilities were invented. "
            f"Original error: {exc}"
        ) from exc
    frame = raw.reset_index()
    points = frame.geometry.representative_point()
    projected_points = gpd.GeoSeries(points, crs=frame.crs).to_crs(PROJECTED_EPSG)
    municipal = boundary.to_crs(PROJECTED_EPSG).geometry.iloc[0]
    geographic = gpd.GeoSeries(points, crs=frame.crs).to_crs("EPSG:4326")
    records = gpd.GeoDataFrame(
        {
            "osm_element": frame["element"].astype(str),
            "osm_id": frame["id"].astype(int),
            "amenity": frame["amenity"].astype(str) if "amenity" in frame.columns else None,
            "name": frame["name"] if "name" in frame.columns else None,
            "inside": projected_points.within(municipal).to_numpy(),
            "lon": geographic.x.to_numpy(),
            "lat": geographic.y.to_numpy(),
        },
        geometry=geographic,
        crs="EPSG:4326",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".geojson.partial")
    records.to_file(temporary, driver="GeoJSON")
    temporary.replace(path)
    provenance = {
        "source": "OpenStreetMap via OSMnx features_from_polygon",
        "tags": POI_TAGS,
        "retrieved_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n_features": int(len(records)),
        "n_inside": int(records["inside"].sum()),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "note": (
            "Amenities that intersect the municipal polygon. The inside flag uses "
            "the representative point. This is not a flood layer. Do not overwrite the file."
        ),
    }
    provenance_path.write_text(json.dumps(provenance, indent=2) + "\n")
    print(f"Downloaded {path}")


def _snap_destinations(graph, destinations: list[dict[str, Any]], max_snap_m: float) -> list[dict[str, Any]]:
    node_ids = []
    coordinates = []
    for node, data in graph.nodes(data=True):
        node_ids.append(node)
        coordinates.append((float(data["x"]), float(data["y"])))
    node_points = shapely_points(np.array(coordinates))
    tree = STRtree(node_points)
    snapped = []
    for place in destinations:
        east, north = _lonlat_to_3424(place["lon"], place["lat"])
        origin = shapely_points([(east, north)])[0]
        index = int(np.asarray(tree.nearest(origin)))
        distance_m = float(shapely_distance(origin, node_points[index])) * US_SURVEY_FOOT_M
        record = dict(place)
        record["snap_distance_m"] = distance_m
        if distance_m > max_snap_m:
            record["node"] = None
            record["snap_status"] = "too_far"
        else:
            record["node"] = node_ids[index]
            record["snap_status"] = "snapped"
        snapped.append(record)
    return snapped


def _pair_routes(graph, snapped: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    usable = [place for place in snapped if place.get("node") is not None]
    routes = {}
    for origin, destination in itertools.combinations(usable, 2):
        label = (str(origin["name"] or origin["osm_id"]), str(destination["name"] or destination["osm_id"]))
        routes[label] = route_between(graph, origin["node"], destination["node"])
        routes[label]["origin_role"] = origin["role"]
        routes[label]["destination_role"] = destination["role"]
        routes[label]["origin_osm_id"] = origin["osm_id"]
        routes[label]["destination_osm_id"] = destination["osm_id"]
    return routes


def _od_row(stage_m: float, origin: str, destination: str, baseline: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    increase = None
    if baseline["status"] == "connected" and scenario["status"] == "connected":
        increase = float(scenario["path_length_m"]) - float(baseline["path_length_m"])
    return {
        "stage_above_channel_dem_m": stage_m,
        "origin": origin,
        "destination": destination,
        "origin_role": baseline.get("origin_role"),
        "destination_role": baseline.get("destination_role"),
        "origin_osm_id": baseline.get("origin_osm_id"),
        "destination_osm_id": baseline.get("destination_osm_id"),
        "baseline_status": baseline["status"],
        "baseline_path_length_m": baseline["path_length_m"],
        "baseline_travel_time_s": baseline["travel_time_s"],
        "baseline_travel_time_status": baseline["travel_time_status"],
        "scenario_status": scenario["status"],
        "scenario_path_length_m": scenario["path_length_m"],
        "scenario_travel_time_s": scenario["travel_time_s"],
        "scenario_travel_time_status": scenario["travel_time_status"],
        "path_length_increase_m": increase,
        "hurricane_ida_depth": False,
    }


def _aadt_join(
    settings: dict[str, Any],
    boundary: gpd.GeoDataFrame,
    centerlines: gpd.GeoDataFrame,
    stages: list[float],
) -> dict[str, Any]:
    path = resolve(settings, "aadt_csv")
    if not path.is_file():
        return {"available": False, "reason": "AADT file is missing. No station was joined."}
    table = pd.read_csv(path)
    if not {"Latitude", "Longitude", "Location ID"}.issubset(table.columns):
        return {"available": False, "reason": "AADT file is missing coordinate columns. No station was joined."}
    points = gpd.GeoDataFrame(
        table,
        geometry=gpd.points_from_xy(table["Longitude"], table["Latitude"]),
        crs="EPSG:4326",
    ).to_crs(PROJECTED_EPSG)
    require_crs(centerlines.crs, f"EPSG:{PROJECTED_EPSG}", "centerlines for AADT")
    tree = STRtree(centerlines.geometry.to_numpy())
    max_snap_ft = float(settings["accessibility"]["aadt_max_snap_m"]) / US_SURVEY_FOOT_M
    gap_ft = float(settings["accessibility"]["aadt_ambiguity_gap_m"]) / US_SURVEY_FOOT_M
    rows = []
    for point_index, point in enumerate(points.geometry):
        queried = np.asarray(tree.query(point, predicate="dwithin", distance=max_snap_ft * 1.5))
        if queried.size == 0:
            indexes = []
        elif queried.ndim == 2:
            indexes = queried[1].tolist()
        else:
            indexes = queried.tolist()
        if not indexes:
            distances = []
        else:
            distances = sorted(
                (
                    float(shapely_distance(point, centerlines.geometry.iloc[int(item)])),
                    int(item),
                )
                for item in indexes
            )
        status = "too_far"
        chosen = None
        nearest_m = None
        second_m = None
        if distances:
            nearest_m = distances[0][0] * US_SURVEY_FOOT_M
            if len(distances) > 1:
                second_m = distances[1][0] * US_SURVEY_FOOT_M
            if distances[0][0] > max_snap_ft:
                status = "too_far"
            elif second_m is not None and (distances[1][0] - distances[0][0]) < gap_ft:
                status = "ambiguous"
            else:
                status = "snapped"
                chosen = distances[0][1]
        record = {
            "location_id": str(table.iloc[point_index]["Location ID"]),
            "direction": None if _blank(table.iloc[point_index].get("Direction")) else str(table.iloc[point_index]["Direction"]),
            "snap_status": status,
            "nearest_distance_m": nearest_m,
            "second_distance_m": second_m,
            "centerline_id": None if chosen is None else str(centerlines.iloc[chosen]["centerline_id"]),
        }
        for stage in stages:
            slug = _slug(stage)
            column = f"assumed_closed_stage_{slug}"
            record[column] = None if chosen is None else bool(centerlines.iloc[chosen][column])
        rows.append(record)
    detail = pd.DataFrame(rows)
    snapped = detail[detail["snap_status"] == "snapped"]
    by_stage = {}
    for stage in stages:
        slug = _slug(stage)
        column = f"assumed_closed_stage_{slug}"
        n_snapped = int(len(snapped))
        n_closed = int(snapped[column].sum()) if n_snapped else 0
        by_stage[f"{stage:.2f}"] = {
            "n_station_records_snapped": n_snapped,
            "n_station_records_nearest_edge_assumed_closed": n_closed,
            "share_of_snapped_records_nearest_edge_assumed_closed": (n_closed / n_snapped) if n_snapped else None,
        }
    return {
        "available": True,
        "joined_as_nearest_edge": True,
        "aadt_summed": False,
        "note": (
            "Each published station-record is one row, including direction splits "
            "that share a coordinate. The share is the share of unambiguous snapped "
            "records whose nearest centerline is assumed closed. AADT values are not "
            "summed and are not a count of travelers."
        ),
        "n_station_records": int(len(detail)),
        "n_ambiguous": int((detail["snap_status"] == "ambiguous").sum()),
        "n_too_far": int((detail["snap_status"] == "too_far").sum()),
        "max_snap_m": settings["accessibility"]["aadt_max_snap_m"],
        "ambiguity_gap_m": settings["accessibility"]["aadt_ambiguity_gap_m"],
        "by_stage": by_stage,
        "records": detail.to_dict(orient="records"),
    }


def _stats(
    settings: dict[str, Any],
    stages: list[float],
    thresholds: list[float],
    fraction: float,
    stage_payloads: list[dict[str, Any]],
    chosen: dict[str, Any],
    snapped: list[dict[str, Any]],
    aadt: dict[str, Any],
    places: list[dict[str, Any]],
) -> dict[str, Any]:
    aadt_summary = {key: value for key, value in aadt.items() if key != "records"}
    return {
        "product": "scenario_accessibility",
        "depth_product": settings["scenario"]["product"],
        "hurricane_ida_depth": False,
        "hurricane_ida_simulation": False,
        "event_time": None,
        "interpolated": False,
        "enso_scales_depths": False,
        "time_note": (
            "Each configured rise is a separate channel-relative computation. "
            "The rises were not interpolated, they are not hours, and they are not a forecast."
        ),
        "computed_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "not_a_closure_standard": True,
        "thresholds_m": {
            "accessible_below": thresholds[0],
            "at_risk_from": thresholds[0],
            "at_risk_below": thresholds[1],
            "assumed_closed_at_or_above": thresholds[1],
            "status": settings["thresholds"]["status"],
        },
        "closure_piece_fraction": fraction,
        "closure_denominator": "length_m_inside",
        "network_disruption_analysis": True,
        "dashboard": False,
        "stages": stage_payloads,
        "destinations": {
            "osm_query_tags": POI_TAGS,
            "n_features_in_file": len(places),
            "n_inside": sum(1 for place in places if place["inside"]),
            "missing_roles": chosen["missing_roles"],
            "used": [
                {
                    "role": place["role"],
                    "name": place["name"],
                    "osm_id": place["osm_id"],
                    "osm_element": place["osm_element"],
                    "lon": place["lon"],
                    "lat": place["lat"],
                    "snap_status": place["snap_status"],
                    "snap_distance_m": place["snap_distance_m"],
                    "node": None if place["node"] is None else int(place["node"]),
                }
                for place in snapped
            ],
            "note": (
                "Only OpenStreetMap amenities whose representative point is inside "
                "the municipal polygon are eligible. A role with no such feature is "
                "listed as missing and is not filled with an invented facility."
            ),
        },
        "aadt": aadt_summary,
    }


def _write(
    settings: dict[str, Any],
    merged: gpd.GeoDataFrame,
    boundary: gpd.GeoDataFrame,
    stats: dict[str, Any],
    stage_payloads: list[dict[str, Any]],
    aadt: dict[str, Any],
) -> None:
    gpkg_path = resolve(settings, "accessibility_gpkg")
    geojson_path = resolve(settings, "accessibility_geojson")
    csv_path = resolve(settings, "accessibility_csv")
    components_path = resolve(settings, "accessibility_components_csv")
    od_path = resolve(settings, "accessibility_od_csv")
    critical_path = resolve(settings, "accessibility_critical_csv")
    aadt_path = resolve(settings, "accessibility_aadt_csv")
    stats_path = resolve(settings, "accessibility_stats")
    map_path = resolve(settings, "accessibility_map")
    for path in (gpkg_path, geojson_path, csv_path, components_path, od_path, critical_path, aadt_path, stats_path, map_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    if gpkg_path.exists():
        gpkg_path.unlink()
    merged.to_file(gpkg_path, layer="centerline_accessibility", driver="GPKG")
    boundary.to_crs(merged.crs).to_file(gpkg_path, layer="boundary", driver="GPKG", mode="a")
    merged.to_crs("EPSG:4326").to_file(geojson_path, driver="GeoJSON")
    pd.DataFrame(merged.drop(columns="geometry")).to_csv(csv_path, index=False)
    component_rows = []
    od_rows = []
    critical_rows = []
    for payload in stage_payloads:
        for component in payload["components"]:
            component_rows.append({"stage_above_channel_dem_m": payload["stage_above_channel_dem_m"], **component})
        od_rows.extend(payload["od_pairs"])
    for stage in settings["scenario"]["stage_above_channel_dem_m"]:
        slug = _slug(float(stage))
        critical = merged[(merged[f"graph_bridge_stage_{slug}"] == True) | (merged[f"n_od_paths_stage_{slug}"] > 0)]  # noqa: E712
        for row in critical.itertuples(index=False):
            critical_rows.append(
                {
                    "stage_above_channel_dem_m": float(stage),
                    "centerline_id": row.centerline_id,
                    "name": row.name,
                    "graph_bridge": bool(getattr(row, f"graph_bridge_stage_{slug}")),
                    "n_od_paths": int(getattr(row, f"n_od_paths_stage_{slug}")),
                    "assumed_closed": bool(getattr(row, f"assumed_closed_stage_{slug}")),
                    "routing_status": getattr(row, f"routing_status_stage_{slug}"),
                    "hurricane_ida_depth": False,
                }
            )
    pd.DataFrame(component_rows).to_csv(components_path, index=False)
    pd.DataFrame(od_rows).to_csv(od_path, index=False)
    pd.DataFrame(critical_rows).to_csv(critical_path, index=False)
    if aadt.get("records"):
        pd.DataFrame(aadt["records"]).to_csv(aadt_path, index=False)
    else:
        pd.DataFrame([{"available": False, "reason": aadt.get("reason")}]).to_csv(aadt_path, index=False)
    stats_path.write_text(json.dumps(stats, indent=2) + "\n")
    save_disruption_map(
        boundary,
        merged,
        stages_m=[float(value) for value in settings["scenario"]["stage_above_channel_dem_m"]],
        path=map_path,
    )
    print(f"Wrote {gpkg_path}")
    print(f"Wrote {geojson_path}")
    print(f"Wrote {stats_path}")
    print(f"Wrote {map_path}")


def _print(stats: dict[str, Any]) -> None:
    print("Scenario accessibility. Not Hurricane Ida.")
    for stage in stats["stages"]:
        print(
            f"+{stage['stage_above_channel_dem_m']:.1f} m: "
            f"{stage['n_assumed_closed']} centerlines assumed closed "
            f"({stage['percent_inside_length_assumed_closed']:.2f}% of inside length), "
            f"piece length >= 0.30 m {stage['piece_length_m_at_or_above_0_30']:.0f} m, "
            f"{stage['n_weak_components']} weak components, "
            f"max-based count {stage['n_max_based_at_or_above_closure_depth']}."
        )


def _slug(stage_m: float) -> str:
    return f"{float(stage_m):.2f}".replace(".", "_")


def _blank(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and np.isnan(value):
        return True
    return str(value).strip().lower() in {"", "none", "nan"}


def _lonlat_to_3424(lon: float, lat: float) -> tuple[float, float]:
    from pyproj import Transformer

    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{PROJECTED_EPSG}", always_xy=True)
    east, north = transformer.transform(lon, lat)
    return float(east), float(north)


if __name__ == "__main__":
    main()
