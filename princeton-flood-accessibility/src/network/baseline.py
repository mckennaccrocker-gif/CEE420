"""Assemble, check, and save the stage-1 baseline network."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

from geospatial.crs import GEOGRAPHIC_EPSG
from geospatial.crs import PROJECTED_EPSG
from geospatial.crs import require_crs
from geospatial.inventory import station_inventory
from network.roads import annotate_edges
from network.roads import assert_graph_crs
from network.roads import configure_osmnx
from network.roads import download_drive_graph
from network.roads import edges_to_frame
from network.roads import geographic_polygon
from network.roads import load_boundary
from network.roads import load_settings
from network.roads import nodes_to_frame
from network.roads import project_drive_graph
from network.roads import project_root
from network.roads import resolve
from network.roads import transformation_note
from network.roads import validate_princeton_boundary
from network.stats import dead_end_count
from network.stats import intersection_count
from network.stats import largest_weak_component_nodes
from network.stats import strongly_connected_component_count
from network.stats import sum_attr
from network.stats import weakly_connected_component_count
from visualization.baseline_map import save_baseline_map


def build_baseline(settings_path: Path | None = None) -> dict[str, Any]:
    """Download, project, check, and write the Princeton drive network.

    Returns the stats dictionary that was written to disk.
    """
    settings = load_settings(settings_path)
    if settings["thresholds"].get("applied_in_stage_1"):
        raise ValueError("Depth thresholds are not applied in stage 1.")

    boundary = load_boundary(resolve(settings, "boundary"))
    boundary_summary = validate_princeton_boundary(boundary, settings)
    polygon = geographic_polygon(boundary)

    configure_osmnx(settings)
    graph = annotate_edges(download_drive_graph(polygon, settings))
    projected = project_drive_graph(graph)
    assert_graph_crs(projected)

    centerlines = edges_to_frame(projected, centerlines_only=True)
    centerlines = _add_clipped_lengths(centerlines, boundary)
    directed = edges_to_frame(projected, centerlines_only=False)
    nodes = nodes_to_frame(projected)
    _require_frames(nodes, directed, centerlines, boundary)

    stats = _statistics(projected, centerlines, directed, boundary_summary, settings)
    _require_plausible_lengths(stats)
    stats["inventory"] = {
        "aadt": station_inventory(
            resolve(settings, "aadt_csv"),
            boundary,
            lon_column="Longitude",
            lat_column="Latitude",
            label="NJDOT AADT stations, 2024, community name contains Princeton in Mercer County",
        ),
        "usgs_ida_high_water_marks": station_inventory(
            resolve(settings, "hwm_csv"),
            boundary,
            lon_column="longitude_dd",
            lat_column="latitude_dd",
            label="USGS New Jersey Hurricane Ida high-water marks, September 2021",
        ),
        "note": (
            "Point counts are not assigned to road edges. "
            "No AADT value on a station was copied onto a centerline."
        ),
    }

    boundary_plan = boundary.to_crs(PROJECTED_EPSG)
    _write_gpkg(resolve(settings, "gpkg"), nodes, directed, centerlines, boundary_plan)
    _write_geojson(resolve(settings, "nodes_geojson"), nodes)
    _write_geojson(resolve(settings, "edges_geojson"), directed)
    _write_geojson(resolve(settings, "centerlines_geojson"), centerlines)
    _write_graphml(resolve(settings, "graphml"), projected)
    _read_back_crs(settings)

    map_stats = {
        "centerline_length_inside_km": stats["network"]["centerline_length_inside_m"] / 1000.0,
        "n_intersections": stats["network"]["n_intersections"],
        "n_components": stats["network"]["n_weakly_connected_components"],
    }
    save_baseline_map(boundary_plan, centerlines, map_stats, resolve(settings, "map_png"))
    stats["files"] = _file_records(settings)
    _write_stats(stats, resolve(settings, "stats_json"), resolve(settings, "stats_csv"))
    return stats


def _add_clipped_lengths(centerlines: gpd.GeoDataFrame, boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Length of each centerline that lies inside the municipal polygon.

    The intersection is computed in EPSG:3424. ``length`` of that result is
    US survey feet. ``length_m_inside`` converts those feet with 1200/3937.
    Segments kept by ``truncate_by_edge`` lose the portion outside the town.
    """
    from geospatial.crs import us_survey_feet_to_m

    polygon = boundary.to_crs(PROJECTED_EPSG).geometry.iloc[0]
    clipped = centerlines.geometry.intersection(polygon)
    result = centerlines.copy()
    result["length_ftus_inside"] = clipped.length
    result["length_m_inside"] = result["length_ftus_inside"].map(us_survey_feet_to_m)
    return result


def _require_frames(
    nodes: gpd.GeoDataFrame,
    directed: gpd.GeoDataFrame,
    centerlines: gpd.GeoDataFrame,
    boundary: gpd.GeoDataFrame,
) -> None:
    require_crs(nodes.crs, PROJECTED_EPSG, "nodes")
    require_crs(directed.crs, PROJECTED_EPSG, "directed edges")
    require_crs(centerlines.crs, PROJECTED_EPSG, "centerlines")
    require_crs(boundary.to_crs(PROJECTED_EPSG).crs, PROJECTED_EPSG, "boundary")
    if len(centerlines) > len(directed):
        raise RuntimeError(
            "Centerline count exceeds directed edge count. "
            "Two-way streets were not collapsed."
        )


def _statistics(
    graph: Any,
    centerlines: gpd.GeoDataFrame,
    directed: gpd.GeoDataFrame,
    boundary_summary: dict[str, float],
    settings: dict[str, Any],
) -> dict[str, Any]:
    import osmnx as ox

    centerline_m = sum_attr(graph, "length_m", centerlines_only=True)
    planar_m = sum_attr(graph, "length_m_planar", centerlines_only=True)
    directed_m = sum_attr(graph, "length_m", centerlines_only=False)
    inside_m = float(centerlines["length_m_inside"].sum())
    # OSMnx's own undirected length, kept as a cross-check. It sums the
    # metre ``length`` attribute after collapsing reciprocal geometries.
    osmnx_length_m = float(ox.stats.street_length_total(ox.convert.to_undirected(graph)))
    n_nodes = int(graph.number_of_nodes())
    n_intersections = intersection_count(graph, min_streets=2)
    largest = largest_weak_component_nodes(graph)
    bridge = centerlines["is_bridge"].astype(bool)
    by_class = (
        centerlines.groupby("road_class", dropna=False)["length_m_inside"].sum().sort_values(ascending=False)
    )
    thresholds = [float(value) for value in settings["thresholds"]["depth_m"]]
    return {
        "stage": 1,
        "place": settings["place"]["name"],
        "retrieved_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "osmnx_version": ox.__version__,
        "flood_model": None,
        "observed_flood_depths_used": False,
        "crs": {
            "geographic": f"EPSG:{GEOGRAPHIC_EPSG}",
            "projected": f"EPSG:{PROJECTED_EPSG}",
            "projected_name": settings["crs"]["projected_name"],
            "linear_unit": "US survey foot",
            "metres_per_us_survey_foot": "1200/3937",
            "proj_pipeline_epsg4326_to_epsg3424": transformation_note(),
            "node_xy_and_geometry": "EPSG:3424 US survey feet",
            "geojson": "EPSG:4326",
            "length_m": "OSMnx ellipsoidal metres on the unprojected graph, once per centerline",
            "length_m_planar": "EPSG:3424 geometry length converted with 1200/3937, once per centerline",
            "length_m_inside": "EPSG:3424 length of the centerline intersected with the municipal polygon, converted with 1200/3937",
        },
        "boundary": boundary_summary,
        "network": {
            "network_type": settings["network"]["network_type"],
            "simplify": bool(settings["network"]["simplify"]),
            "retain_all": bool(settings["network"]["retain_all"]),
            "truncate_by_edge": bool(settings["network"]["truncate_by_edge"]),
            "definition": (
                "Public drivable OpenStreetMap ways meeting the Princeton "
                "municipal polygon. Service roads are excluded by the OSMnx "
                "drive filter. Two-way streets are counted once in centerline lengths."
            ),
            "n_nodes": n_nodes,
            "n_intersections": n_intersections,
            "n_junctions_min_streets_3": intersection_count(graph, min_streets=3),
            "n_dead_ends": dead_end_count(graph),
            "n_directed_edges": int(graph.number_of_edges()),
            "n_centerlines": int(len(centerlines)),
            "n_weakly_connected_components": weakly_connected_component_count(graph),
            "n_strongly_connected_components": strongly_connected_component_count(graph),
            "largest_weak_component_nodes": largest,
            "largest_weak_component_fraction": largest / n_nodes,
            "centerline_length_m": centerline_m,
            "centerline_length_m_planar": planar_m,
            "centerline_length_inside_m": inside_m,
            "directed_length_m": directed_m,
            "directed_over_centerline_ratio": directed_m / centerline_m,
            "osmnx_street_length_total_m": osmnx_length_m,
            "n_bridge_centerlines": int(bridge.sum()),
            "bridge_centerline_length_inside_m": float(centerlines.loc[bridge, "length_m_inside"].sum()),
            "n_tunnel_centerlines": int(centerlines["is_tunnel"].astype(bool).sum()),
            "n_positive_layer_centerlines": int(centerlines["is_positive_layer"].astype(bool).sum()),
            "n_centerlines_with_explicit_maxspeed": int(centerlines["maxspeed_mph"].notna().sum()),
            "maxspeed_imputed": False,
            "aadt_on_edges": False,
            "length_inside_by_road_class_m": {str(key): float(value) for key, value in by_class.items()},
            "n_directed_rows_in_gpkg": int(len(directed)),
        },
        "flood": {
            "model": None,
            "observed_depths_used": False,
            "depth_thresholds_m": thresholds,
            "depth_thresholds_status": settings["thresholds"]["status"],
            "depth_thresholds_applied": False,
            "note": (
                "0.10 m and 0.30 m are preliminary scenario assumptions, "
                "not official closure standards and not Hurricane Ida measurements."
            ),
        },
    }


def _require_plausible_lengths(stats: dict[str, Any]) -> None:
    """Stop before writing if the length definitions disagree by more than a CRS slip would allow."""
    network = stats["network"]
    centerline_m = network["centerline_length_m"]
    planar_m = network["centerline_length_m_planar"]
    inside_m = network["centerline_length_inside_m"]
    ratio = network["directed_over_centerline_ratio"]
    if centerline_m <= 0 or inside_m <= 0:
        raise RuntimeError("Road length is zero. Outputs were not written.")
    if not 1.15 <= ratio <= 2.05:
        raise RuntimeError(
            f"Directed length / centerline length is {ratio:.3f}. "
            "Expected a value from 1.15 to 2 because most Princeton streets "
            "have two directions and each physical street is counted once. "
            "A value near 1 means two-way streets were double-counted. "
            "Outputs were not written."
        )
    relative_planar = abs(centerline_m - planar_m) / centerline_m
    if relative_planar > 0.02:
        raise RuntimeError(
            f"Ellipsoidal length and EPSG:3424 length differ by {relative_planar:.2%}. "
            "A missed feet-to-metres conversion looks like this. Outputs were not written."
        )
    if inside_m > planar_m + 1.0:
        raise RuntimeError(
            "Length inside the boundary exceeds the full planar length. "
            "The clip is in the wrong units. Outputs were not written."
        )
    osmnx_m = network["osmnx_street_length_total_m"]
    relative_osmnx = abs(centerline_m - osmnx_m) / centerline_m
    network["osmnx_length_relative_difference"] = relative_osmnx
    if relative_osmnx > 0.01:
        raise RuntimeError(
            f"Centerline length and OSMnx street_length_total differ by {relative_osmnx:.2%}. "
            "Outputs were not written."
        )


def _write_gpkg(
    path: Path,
    nodes: gpd.GeoDataFrame,
    directed: gpd.GeoDataFrame,
    centerlines: gpd.GeoDataFrame,
    boundary: gpd.GeoDataFrame,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    nodes.to_file(path, layer="nodes", driver="GPKG")
    directed.to_file(path, layer="edges", driver="GPKG", mode="a")
    centerlines.to_file(path, layer="centerlines", driver="GPKG", mode="a")
    boundary.to_file(path, layer="boundary", driver="GPKG", mode="a")


def _write_geojson(path: Path, frame: gpd.GeoDataFrame) -> None:
    """GeoJSON is stored in EPSG:4326. The GeoPackage keeps EPSG:3424."""
    path.parent.mkdir(parents=True, exist_ok=True)
    geographic = frame.to_crs(GEOGRAPHIC_EPSG)
    require_crs(geographic.crs, GEOGRAPHIC_EPSG, path.name)
    geographic.to_file(path, driver="GeoJSON")


def _write_graphml(path: Path, graph: Any) -> None:
    import osmnx as ox

    path.parent.mkdir(parents=True, exist_ok=True)
    # GraphML has no CRS standard. The string on the graph is the contract.
    graph.graph["crs"] = f"EPSG:{PROJECTED_EPSG}"
    ox.save_graphml(graph, path)


def _read_back_crs(settings: dict[str, Any]) -> None:
    """Reload saved layers and refuse the build if a CRS was dropped."""
    gpkg = resolve(settings, "gpkg")
    for layer in ("nodes", "edges", "centerlines", "boundary"):
        saved = gpd.read_file(gpkg, layer=layer)
        require_crs(saved.crs, PROJECTED_EPSG, f"GeoPackage layer {layer}")
    for key in ("nodes_geojson", "edges_geojson", "centerlines_geojson"):
        saved = gpd.read_file(resolve(settings, key))
        require_crs(saved.crs, GEOGRAPHIC_EPSG, key)


def _file_records(settings: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records = {}
    for key in (
        "gpkg",
        "graphml",
        "centerlines_geojson",
        "nodes_geojson",
        "edges_geojson",
        "map_png",
    ):
        path = resolve(settings, key)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        records[key] = {
            "path": path.relative_to(project_root()).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": digest,
        }
    return records


def _write_stats(stats: dict[str, Any], json_path: Path, csv_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(_json_ready(stats), indent=2) + "\n", encoding="utf-8")
    network = stats["network"]
    rows = [
        ("n_nodes", network["n_nodes"], "count", "Nodes in the directed drive graph, including dead ends"),
        ("n_intersections", network["n_intersections"], "count", "Nodes with at least 2 physical streets (OSMnx definition)"),
        ("n_junctions_min_streets_3", network["n_junctions_min_streets_3"], "count", "Nodes with at least 3 physical streets"),
        ("n_dead_ends", network["n_dead_ends"], "count", "Nodes with exactly 1 physical street"),
        ("n_directed_edges", network["n_directed_edges"], "count", "Directed edges, so a two-way street appears twice"),
        ("n_centerlines", network["n_centerlines"], "count", "Physical street segments, two-way streets counted once"),
        ("n_weakly_connected_components", network["n_weakly_connected_components"], "count", "Weakly connected components of the directed graph"),
        ("n_strongly_connected_components", network["n_strongly_connected_components"], "count", "Strongly connected components"),
        ("centerline_length_m", network["centerline_length_m"], "m", "Ellipsoidal centreline length of retained segments, including overhang outside the boundary"),
        ("centerline_length_m_planar", network["centerline_length_m_planar"], "m", "Same segments, EPSG:3424 length converted from US survey feet"),
        ("centerline_length_inside_m", network["centerline_length_inside_m"], "m", "EPSG:3424 length clipped to the municipal polygon, in metres"),
        ("n_bridge_centerlines", network["n_bridge_centerlines"], "count", "Centerlines with an OSM bridge tag other than no"),
        ("bridge_centerline_length_inside_m", network["bridge_centerline_length_inside_m"], "m", "Clipped length of bridge centerlines. Not a deck elevation"),
        ("n_centerlines_with_explicit_maxspeed", network["n_centerlines_with_explicit_maxspeed"], "count", "Centerlines whose maxspeed tag states mph or km/h. Bare numbers were not converted"),
    ]
    table = pd.DataFrame(rows, columns=["metric", "value", "unit", "definition"])
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(csv_path, index=False)


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, Path):
        return value.as_posix()
    if hasattr(value, "item"):
        return value.item()
    return value
