"""Regulatory FEMA zones stay a separate layer from the scenario depths."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import LineString
from shapely.geometry import Polygon

from geospatial.crs import require_crs
from geospatial.exposure import summarize_pieces
from geospatial.fema_overlay import ANALYSIS_CRS
from geospatial.fema_overlay import SOURCE_HORIZONTAL_CRS
from geospatial.fema_overlay import depth_from_flood_zone
from geospatial.fema_overlay import intersect_centerlines

QUAKER_LONG = "103969043_104044242_0_11643396;27354085;60536166;620669657;620669658;11639163"
SCENARIO_PATHS = (
    "data/processed/princeton_centerline_exposure.gpkg",
    "data/processed/princeton_centerline_exposure.geojson",
    "data/processed/flood_exposure_stats.json",
    "data/processed/princeton_accessibility.gpkg",
    "data/processed/princeton_accessibility.geojson",
    "data/processed/accessibility_stats.json",
    "data/processed/bridge_deck_join.json",
)


def test_zone_code_and_regulatory_water_surface_are_not_a_depth() -> None:
    refused = depth_from_flood_zone(
        fld_zone="AE",
        zone_subty="FLOODWAY",
        static_bfe=65.5,
        is_bridge=True,
        regulatory_water_surface_ft=65.5,
    )
    assert refused["zone_depth_m"] is None
    assert refused["zone_depth_assigned"] is False
    assert refused["regulatory_water_surface_used_as_deck"] is False
    assert refused["regulatory_water_surface_used_as_depth"] is False
    assert refused["static_bfe_used_as_depth"] is False
    assert refused["terrain_under_bridge_used_as_deck"] is False
    # The missing NFHL sentinel is not an elevation either.
    assert depth_from_flood_zone(static_bfe=-9999)["static_bfe_ft"] is None


def test_a_bridge_inside_a_zone_keeps_a_null_depth() -> None:
    # 3,937 US survey feet is exactly 1,200 m. The polygon is the whole line.
    line = LineString([(500000, 500000), (503937, 500000)])
    polygon = Polygon([(499000, 499000), (505000, 499000), (505000, 501000), (499000, 501000)])
    centerlines = gpd.GeoDataFrame(
        {
            "centerline_id": ["bridge"],
            "name": ["Quaker Road"],
            "is_bridge": [True],
            "length_m_inside": [1200.0],
        },
        geometry=[line],
        crs=ANALYSIS_CRS,
    )
    zones = gpd.GeoDataFrame(
        {
            "fld_zone": ["AE"],
            "zone_subty": ["FLOODWAY"],
            "sfha_tf": ["T"],
            "dfirm_id": ["34021C"],
        },
        geometry=[polygon],
        crs=ANALYSIS_CRS,
    )
    summary = intersect_centerlines(centerlines, zones)
    assert summary["hurricane_ida_depth"] is False
    assert summary["zone_depth_assigned"] is False
    assert summary["zones"][0]["length_m"] == pytest.approx(1200.0, abs=0.1)
    assert summary["zones"][0]["n_centerlines"] == 1
    assert summary["zones"][0]["n_bridge_centerlines"] == 1
    assert summary["zones"][0]["zone_depth_m"] is None
    assert summary["centerlines"][0]["zone_depth_m"] is None
    pieces = summarize_pieces(
        is_bridge=True,
        is_tunnel=False,
        piece_length_m=[20.0],
        road_elevation_m=[1.0],
        channel_elevation_m=[10.0],
        channel_distance_m=[5.0],
        max_channel_distance_m=500.0,
        stages_m=[1.0, 2.0],
        thresholds_m=[0.10, 0.30],
    )
    assert pieces["exposure_status"] == "bridge_deck_unmatched"
    assert pieces["depth_max_m_stage_1_00"] is None


def test_analysis_crs_is_required() -> None:
    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    bare = gpd.GeoDataFrame(geometry=[polygon])
    lines = bare.set_crs(ANALYSIS_CRS)
    with pytest.raises(ValueError, match="missing"):
        require_crs(None, ANALYSIS_CRS, "FEMA zones")
    with pytest.raises(ValueError, match="missing"):
        intersect_centerlines(lines, bare)
    with pytest.raises(ValueError, match="FEMA zones"):
        intersect_centerlines(lines, bare.set_crs("EPSG:3857"))


def test_saved_overlay_uses_nad83_and_state_plane(project_root: Path) -> None:
    zones = gpd.read_file(project_root / "data" / "processed" / "fema_flood_zones.gpkg")
    require_crs(zones.crs, ANALYSIS_CRS, "saved FEMA zones")
    display = gpd.read_file(project_root / "data" / "processed" / "fema_flood_zones.geojson")
    require_crs(display.crs, "EPSG:4326", "FEMA GeoJSON")
    provenance = json.loads((project_root / "data" / "raw" / "fema_nfhl_princeton.provenance.json").read_text())
    assert provenance["source_horizontal_crs"] == SOURCE_HORIZONTAL_CRS
    assert provenance["source_horizontal_datum"] == "NAD83"
    assert provenance["hurricane_ida_depth"] is False
    assert provenance["not_a_deck_elevation"] is True
    assert provenance["regulatory_water_surface_ft"] == 65.5
    assert provenance["regulatory_water_surface_datum"] == "NAVD 88"
    assert provenance["firm_panels"]["effective_date"] == "2016-07-20"
    assert set(zones["zone_depth_m"].dropna()) == set()


def test_saved_lengths_do_not_assign_a_zone_depth(project_root: Path) -> None:
    overlay = json.loads((project_root / "data" / "processed" / "fema_zone_intersection.json").read_text())
    assert overlay["hurricane_ida_depth"] is False
    assert overlay["event_time"] is None
    assert overlay["zone_depth_assigned"] is False
    assert overlay["rewrites_scenario_depths"] is False
    assert overlay["effective_date"] == "2016-07-20"
    assert overlay["regulatory_water_surface"]["value"] == 65.5
    assert overlay["regulatory_water_surface"]["datum"] == "NAVD 88"
    assert overlay["regulatory_water_surface"]["units"] == "feet"
    assert overlay["regulatory_water_surface"]["not_a_deck_elevation"] is True
    assert overlay["regulatory_water_surface"]["applied_to_centerlines"] is False
    by_zone = {item["zone"]: item for item in overlay["zones"]}
    assert by_zone["AE — FLOODWAY"]["length_m"] == pytest.approx(3952.4)
    assert by_zone["AE — FLOODWAY"]["n_centerlines"] == 54
    assert by_zone["AE"]["length_m"] == pytest.approx(5916.6)
    assert by_zone["AE"]["n_centerlines"] == 67
    assert by_zone["A"]["length_m"] == pytest.approx(383.3)
    assert by_zone["A"]["n_centerlines"] == 12
    assert by_zone["X — 0.2 PCT ANNUAL CHANCE FLOOD HAZARD"]["length_m"] == pytest.approx(2105.6)
    assert by_zone["X — 0.2 PCT ANNUAL CHANCE FLOOD HAZARD"]["n_centerlines"] == 71
    assert by_zone["X — AREA OF MINIMAL FLOOD HAZARD"]["length_m"] == pytest.approx(220627.8)
    assert by_zone["X — AREA OF MINIMAL FLOOD HAZARD"]["n_centerlines"] == 1266
    assert all(item["zone_depth_m"] is None for item in overlay["zones"])
    assert all(item["zone_depth_m"] is None for item in overlay["centerlines"])
    quaker = next(item for item in overlay["centerlines"] if item["centerline_id"] == QUAKER_LONG)
    assert quaker["is_bridge"] is True
    assert quaker["zone_depth_m"] is None
    assert {zone["zone"] for zone in quaker["zones"]} >= {"AE", "AE — FLOODWAY"}
    bridges = [item for item in overlay["centerlines"] if item["is_bridge"]]
    assert len(bridges) == 20
    assert all(item["zone_depth_m"] is None for item in bridges)


def test_scenario_files_are_unchanged(project_root: Path) -> None:
    overlay = json.loads((project_root / "data" / "processed" / "fema_zone_intersection.json").read_text())
    recorded = overlay["scenario_files_sha256"]
    for relative in SCENARIO_PATHS:
        path = project_root / relative
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert recorded[relative] == digest
    exposure = json.loads((project_root / "data" / "processed" / "flood_exposure_stats.json").read_text())
    assert exposure["product"] == "hypothetical_3dep_channel_relative_bathtub"
    assert exposure["hurricane_ida_simulation"] is False
    assert exposure["assumptions"]["stage_above_channel_dem_m"] == [1.0, 2.0]
    accessibility = json.loads((project_root / "data" / "processed" / "accessibility_stats.json").read_text())
    closed = {stage["stage_above_channel_dem_m"]: stage["n_assumed_closed"] for stage in accessibility["stages"]}
    assert closed[1.0] == 33
    assert closed[2.0] == 90
    roads = json.loads((project_root / "data" / "processed" / "princeton_accessibility.geojson").read_text())
    quaker = next(feature for feature in roads["features"] if feature["properties"]["centerline_id"] == QUAKER_LONG)
    assert quaker["properties"]["exposure_status"] == "bridge_deck_unmatched"
    assert quaker["properties"].get("fema_zone_depth_m") is None
