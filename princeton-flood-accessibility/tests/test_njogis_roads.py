"""NJOGIS centerlines stay a comparison. They do not replace the OSM graph."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import LineString
from shapely.geometry import Polygon

from geospatial.crs import require_crs
from geospatial.njogis_roads import ANALYSIS_CRS
from geospatial.njogis_roads import classify_fields
from geospatial.njogis_roads import clip_centerlines
from geospatial.njogis_roads import compare_centerlines
from geospatial.njogis_roads import elevation_level_as_deck
from geospatial.njogis_roads import nearby_name_keys
from geospatial.njogis_roads import name_key_tuple
from geospatial.njogis_roads import names_equivalent
from geospatial.njogis_roads import normalize_road_name

# 3,937 US survey feet is 1,200 m. y offsets below are in those feet.
SPAN = 3937.0
QUAKER = LineString([(500000, 500000), (500000 + SPAN, 500000)])
CANAL = LineString([(500000, 500040), (500000 + SPAN, 500040)])
BETWEEN = LineString([(500000, 500020), (500000 + SPAN, 500020)])
OSM_ONLY = LineString([(500000, 500700), (500000 + SPAN, 500700)])
NJOGIS_ONLY = LineString([(500000, 500850), (500000 + SPAN, 500850)])
TOWN = Polygon([(499000, 499000), (510000, 499000), (510000, 501000), (499000, 501000)])

GRAPH_AND_SCENARIO = (
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


def test_normalize_expands_a_trailing_abbreviation() -> None:
    assert normalize_road_name("Quaker Rd") == "QUAKER ROAD"
    assert normalize_road_name("Unnamed Segment") is None
    assert normalize_road_name(None) is None
    assert name_key_tuple("Bunn Drive;Herrontown Road") == ("BUNN DRIVE", "HERRONTOWN ROAD")
    assert names_equivalent("BROADMEAD", "BROADMEAD STREET")
    assert not names_equivalent("HERRONTOWN LANE", "HERRONTOWN ROAD")
    assert not names_equivalent("SHADYBROOK LANE", "SHADY BROOK LANE")


def test_relative_level_and_terrain_are_not_a_deck() -> None:
    refused = elevation_level_as_deck(1, 0, terrain_elevation_m=64.2)
    assert refused["deck_elevation_m"] is None
    assert refused["deck_elevation_assigned"] is False
    assert refused["terrain_elevation_used_as_deck"] is False
    assert refused["relative_level_used_as_deck"] is False
    assert refused["elevtyp_from_label"] == "Level 1"
    assert elevation_level_as_deck(0, 0)["elevtyp_from_label"] == "At Grade"
    fields = classify_fields(["PRIMENAME", "ELEVTYP_F", "ELEVTYP_T", "ROADCLASS"])
    assert fields["bridge_attribute_present"] is False
    assert fields["elevation_level_fields"] == ["ELEVTYP_F", "ELEVTYP_T"]
    assert fields["deck_elevation_m"] is None
    assert classify_fields(["BRIDGE"])["bridge_attribute_present"] is True


def test_proximity_can_see_two_names_and_does_not_assign_a_partner() -> None:
    boundary = gpd.GeoDataFrame(geometry=[TOWN], crs=ANALYSIS_CRS)
    osm = gpd.GeoDataFrame(
        {"name": ["Quaker Road", "Canal Road", "Only OSM"], "length_m_inside": [1200.0, 1200.0, 1200.0]},
        geometry=[QUAKER, CANAL, OSM_ONLY],
        crs=ANALYSIS_CRS,
    )
    njogis = gpd.GeoDataFrame(
        {
            "prime_name": ["Quaker Rd", "Far Road"],
            "road_class": ["S1400", "S1400"],
            "elevtyp_from": [1, 0],
            "elevtyp_to": [1, 0],
        },
        geometry=[BETWEEN, NJOGIS_ONLY],
        crs=ANALYSIS_CRS,
    )
    osm_clip = clip_centerlines(osm, boundary)
    njogis_clip = clip_centerlines(njogis, boundary)
    osm_clip["name_key"] = osm_clip["name"].map(normalize_road_name)
    osm_clip["prime_name"] = osm_clip["name"]
    njogis_clip["name_key"] = njogis_clip["prime_name"].map(normalize_road_name)
    found = compare_centerlines(osm_clip, njogis_clip)
    assert found["assigns_one_partner"] is False
    assert "matched_centerline_id" not in found
    assert found["njogis"]["length_m"] == pytest.approx(2400.0, abs=0.1)
    # The line between Quaker Road and Canal Road is within 20 m of both.
    names = nearby_name_keys(BETWEEN, osm_clip)
    assert names == {"QUAKER ROAD", "CANAL ROAD"}
    assert found["njogis"]["length_m_name_agrees"] == pytest.approx(1200.0, abs=0.1)
    assert found["njogis"]["n_mostly_one_source"] == 1
    assert found["osm"]["length_m_beyond_proximity"] == pytest.approx(1200.0, abs=0.1)
    assert found["names_only_in_osm"]["n_names"] >= 1


def test_analysis_crs_is_required() -> None:
    bare = gpd.GeoDataFrame(geometry=[TOWN])
    lines = gpd.GeoDataFrame(
        {"name_key": ["QUAKER ROAD"], "length_m": [10.0]},
        geometry=[QUAKER],
        crs=ANALYSIS_CRS,
    )
    with pytest.raises(ValueError, match="missing"):
        clip_centerlines(lines, bare)
    with pytest.raises(ValueError, match="NJOGIS"):
        compare_centerlines(lines, bare.set_crs("EPSG:3857"))
    require_crs(lines.crs, ANALYSIS_CRS, "state plane")


def test_saved_njogis_extract_is_state_plane(project_root: Path) -> None:
    raw = gpd.read_file(project_root / "data" / "raw" / "njogis_princeton_centerlines.gpkg")
    clipped = gpd.read_file(project_root / "data" / "processed" / "njogis_princeton_centerlines.gpkg")
    require_crs(raw.crs, ANALYSIS_CRS, "saved NJOGIS centerlines")
    require_crs(clipped.crs, ANALYSIS_CRS, "clipped NJOGIS centerlines")
    provenance = json.loads((project_root / "data" / "raw" / "njogis_princeton_centerlines.provenance.json").read_text())
    digest = hashlib.sha256((project_root / "data" / "raw" / "njogis_princeton_centerlines.gpkg").read_bytes()).hexdigest()
    assert digest == provenance["sha256"]
    assert provenance["horizontal_crs"] == ANALYSIS_CRS
    assert provenance["horizontal_datum"] == "NAD83"
    assert provenance["service_latest_wkid"] == 3424
    assert provenance["vertical_datum"] is None
    assert provenance["bridge_attribute_present"] is False
    assert provenance["not_a_deck_elevation"] is True
    assert provenance["terrain_elevation_used_as_deck"] is False
    assert provenance["replaces_routable_graph"] is False
    assert provenance["service_data_last_edit_utc"] == "2026-09-23T17:43:11Z"
    assert provenance["item_modified_utc"] == "2026-09-23T19:36:12Z"
    assert "ELEVTYP_F" in provenance["service_field_names"]
    assert not any("BRIDGE" in name.upper() for name in provenance["service_field_names"])
    assert raw.geometry.iloc[0].interpolate(0.5, normalized=True).x > 1000


def test_graph_scenario_and_fema_files_are_unchanged(project_root: Path) -> None:
    comparison = json.loads((project_root / "data" / "processed" / "njogis_osm_comparison.json").read_text())
    assert comparison["replaces_routable_graph"] is False
    assert comparison["rewrites_scenario_depths"] is False
    assert comparison["rewrites_fema_zone_lengths"] is False
    assert comparison["deck_search_reopened"] is False
    assert comparison["terrain_elevation_used_as_deck"] is False
    assert comparison["crs"] == ANALYSIS_CRS
    assert comparison["comparison"]["assigns_one_partner"] is False
    assert comparison["njogis_clip"]["deck_elevation_assigned"] is False
    assert comparison["njogis_clip"]["bridge_attribute_present"] is False
    recorded = comparison["unchanged_files_sha256"]
    for relative in GRAPH_AND_SCENARIO:
        digest = hashlib.sha256((project_root / relative).read_bytes()).hexdigest()
        assert recorded[relative] == digest
    assert comparison["osm"]["length_m_saved"] == pytest.approx(232984.8, abs=0.05)
    assert comparison["osm"]["n_centerlines_saved"] == 1298
    assert comparison["osm"]["n_centerlines"] == 1291
    assert comparison["njogis_clip"]["n_centerlines"] == 1612
    assert comparison["njogis_clip"]["length_m"] == pytest.approx(262462.2, abs=0.05)
    assert comparison["comparison"]["length_difference_m"] == pytest.approx(29477.3, abs=0.1)
    assert comparison["njogis_clip"]["raised_centerlines"] == []
    assert comparison["njogis_clip"]["elevation_level_counts"][0]["n_centerlines"] == 1612
    assert comparison["njogis_clip"]["elevation_level_counts"][0]["elevtyp_from"] == 0
    assert comparison["comparison"]["njogis"]["length_m_name_agrees"] == pytest.approx(218096.5, abs=0.1)
    assert comparison["comparison"]["osm"]["length_m_name_agrees"] == pytest.approx(214573.8, abs=0.1)
    assert comparison["comparison"]["njogis"]["length_m_beyond_proximity"] == pytest.approx(27472.0, abs=0.1)
    assert comparison["comparison"]["osm"]["length_m_beyond_proximity"] == pytest.approx(3023.1, abs=0.1)
    exposure = json.loads((project_root / "data" / "processed" / "flood_exposure_stats.json").read_text())
    assert exposure["product"] == "hypothetical_3dep_channel_relative_bathtub"
    assert exposure["assumptions"]["stage_above_channel_dem_m"] == [1.0, 2.0]
    accessibility = json.loads((project_root / "data" / "processed" / "accessibility_stats.json").read_text())
    closed = {stage["stage_above_channel_dem_m"]: stage["n_assumed_closed"] for stage in accessibility["stages"]}
    assert closed[1.0] == 33
    assert closed[2.0] == 90
    overlay = json.loads((project_root / "data" / "processed" / "fema_zone_intersection.json").read_text())
    by_zone = {item["zone"]: item["length_m"] for item in overlay["zones"]}
    assert by_zone["AE — FLOODWAY"] == pytest.approx(3952.4)
    assert by_zone["AE"] == pytest.approx(5916.6)
    assert by_zone["A"] == pytest.approx(383.3)
    assert by_zone["X — 0.2 PCT ANNUAL CHANCE FLOOD HAZARD"] == pytest.approx(2105.6)
    assert by_zone["X — AREA OF MINIMAL FLOOD HAZARD"] == pytest.approx(220627.8)
