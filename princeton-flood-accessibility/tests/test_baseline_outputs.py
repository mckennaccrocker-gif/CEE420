"""Saved baseline files must match the statistics written by download_roads.py."""

from __future__ import annotations

import json

import geopandas as gpd
import osmnx as ox
import pytest

from geospatial.coverage import raster_extent_against_boundary
from geospatial.crs import require_crs
from network.stats import weakly_connected_component_count


def _require(path, what: str):
    if not path.is_file():
        pytest.fail(f"{what} is missing at {path}. Run scripts/download_roads.py.")
    return path


def test_saved_network_matches_stats(project_root) -> None:
    stats_path = _require(project_root / "data" / "processed" / "baseline_stats.json", "baseline stats")
    stats = json.loads(stats_path.read_text())
    network = stats["network"]
    assert stats["flood_model"] is None
    assert stats["observed_flood_depths_used"] is False
    assert stats["flood"]["depth_thresholds_applied"] is False
    assert stats["flood"]["depth_thresholds_m"] == pytest.approx([0.10, 0.30])
    assert network["aadt_on_edges"] is False
    assert network["maxspeed_imputed"] is False

    gpkg = project_root / "data" / "processed" / "princeton_drive_network.gpkg"
    centerlines = gpd.read_file(_require(gpkg, "GeoPackage"), layer="centerlines")
    nodes = gpd.read_file(gpkg, layer="nodes")
    edges = gpd.read_file(gpkg, layer="edges")
    boundary = gpd.read_file(gpkg, layer="boundary")
    for layer, frame in (
        ("centerlines", centerlines),
        ("nodes", nodes),
        ("edges", edges),
        ("boundary", boundary),
    ):
        require_crs(frame.crs, "EPSG:3424", layer)

    assert len(nodes) == network["n_nodes"]
    assert len(edges) == network["n_directed_edges"]
    assert len(centerlines) == network["n_centerlines"]
    assert "aadt" not in {column.lower() for column in edges.columns}
    assert float(centerlines["length_m"].sum()) == pytest.approx(network["centerline_length_m"], rel=1e-6)
    assert float(centerlines["length_m_inside"].sum()) == pytest.approx(
        network["centerline_length_inside_m"], rel=1e-6
    )
    assert float(centerlines["length_m_planar"].sum()) == pytest.approx(
        network["centerline_length_m_planar"], rel=1e-6
    )
    assert network["centerline_length_inside_m"] <= network["centerline_length_m_planar"] + 1.0
    assert int(centerlines["is_bridge"].astype(bool).sum()) == network["n_bridge_centerlines"]
    # State Plane feet, not longitude. Princeton eastings are hundreds of thousands.
    assert float(nodes.geometry.x.median()) > 100_000

    for name in (
        "princeton_drive_centerlines.geojson",
        "princeton_drive_nodes.geojson",
        "princeton_drive_edges.geojson",
    ):
        geographic = gpd.read_file(project_root / "data" / "processed" / name)
        require_crs(geographic.crs, "EPSG:4326", name)
        assert float(geographic.geometry.total_bounds[0]) < -74

    graph = ox.load_graphml(project_root / "data" / "processed" / "princeton_drive_network.graphml")
    assert graph.graph["crs"] == "EPSG:3424"
    assert graph.number_of_nodes() == network["n_nodes"]
    assert graph.number_of_edges() == network["n_directed_edges"]
    assert weakly_connected_component_count(graph) == network["n_weakly_connected_components"]

    map_path = _require(
        project_root / "outputs" / "maps" / "princeton_baseline_drive_network.png",
        "baseline map",
    )
    assert map_path.stat().st_size > 20_000
    assert map_path.read_bytes().startswith(b"\x89PNG")


def test_recorded_ida_rasters_do_not_meet_princeton(project_root, boundary) -> None:
    path = _require(
        project_root / "data" / "processed" / "ida_raster_coverage_check.json",
        "Ida raster coverage check",
    )
    payload = json.loads(path.read_text())
    assert payload["these_are_not_princeton_flood_depths"] is True
    assert payload["rasters"]
    for record in payload["rasters"]:
        assert record["vertical_units_in_geotiff"] is None
        assert record["intersects_princeton"] is False
        bounds = record["bounds"]
        recomputed = raster_extent_against_boundary(
            (bounds["left"], bounds["bottom"], bounds["right"], bounds["top"]),
            record["crs"],
            boundary,
        )
        assert recomputed["intersects_princeton"] is False
        assert recomputed["distance_to_princeton_km"] > 20
        assert record["distance_to_princeton_km"] == pytest.approx(
            recomputed["distance_to_princeton_km"], rel=1e-6
        )
