"""Deck elevations come from a published inventory, not from the ground under the span."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from shapely.geometry import LineString
from shapely.geometry import Point

from dashboard.roads import build_road_collection
from geospatial.bridge_decks import assess_centerline
from geospatial.bridge_decks import decide_deck
from geospatial.bridge_decks import decode_nbi_coordinate
from geospatial.bridge_decks import depth_above_deck
from geospatial.bridge_decks import identity_match
from geospatial.bridge_decks import nbi_has_deck_elevation_column
from geospatial.exposure import summarize_pieces

QUAKER_LONG = "103969043_104044242_0_11643396;27354085;60536166;620669657;620669658;11639163"
QUAKER_SHORT = "104007542_104055790_0_651619439;651619438;11643983"


def _script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "bridge_decks.py"
    spec = importlib.util.spec_from_file_location("bridge_decks_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_terrain_under_a_bridge_is_not_a_deck_elevation() -> None:
    # The road cell is 9 m below the water surface. summarize_pieces still
    # refuses to report that as a deck depth.
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
    # Passing the terrain elevation into the deck function does not fill a depth.
    # Water 12 m, terrain 1 m, no deck: the forbidden answer would be 11 m.
    refused = depth_above_deck(12.0, None, terrain_elevation_m=1.0)
    assert refused["exposure_status"] == "bridge_deck_unmatched"
    assert refused["depth_m"] is None
    assert refused["deck_elevation_m"] is None
    assert refused["terrain_used_as_deck"] is False
    assert refused["terrain_refused"] is True
    # A real deck of 10 m over a 12 m water surface is 2 m, not the 11 m
    # gap down to the terrain.
    sampled = depth_above_deck(12.0, 10.0, terrain_elevation_m=1.0)
    assert sampled["exposure_status"] == "bridge_deck_sampled"
    assert sampled["depth_m"] == pytest.approx(2.0)
    assert sampled["terrain_used_as_deck"] is False


def test_missing_elevation_stays_unmatched_and_undefined_water_does_too() -> None:
    missing = decide_deck(
        accepted_structures=[{"structure_number": "1", "structure_length_m": 100.0}],
        deck_elevation_m=None,
        water_surfaces_m={"1.00": 20.0, "2.00": 21.0},
        length_m_inside=100.0,
    )
    assert missing["exposure_status"] == "bridge_deck_unmatched"
    assert missing["depth_m_by_stage"] is None
    assert "no_published_deck_elevation" in missing["unmatched_reasons"]
    assert missing["hurricane_ida_depth"] is False

    undefined = decide_deck(
        accepted_structures=[{"structure_number": "1", "structure_length_m": 100.0}],
        deck_elevation_m=15.0,
        water_surfaces_m={"1.00": None, "2.00": None},
        length_m_inside=100.0,
    )
    assert undefined["exposure_status"] == "bridge_deck_unmatched"
    assert undefined["depth_m_by_stage"] is None
    assert "water_surface_undefined" in undefined["unmatched_reasons"]

    covered = decide_deck(
        accepted_structures=[{"structure_number": "1", "structure_length_m": 100.0}],
        deck_elevation_m=15.0,
        water_surfaces_m={"1.00": 16.0, "2.00": 17.5},
        length_m_inside=100.0,
    )
    assert covered["exposure_status"] == "bridge_deck_sampled"
    assert covered["depth_m_by_stage"]["1.00"] == pytest.approx(1.0)
    assert covered["depth_m_by_stage"]["2.00"] == pytest.approx(2.5)


def test_a_short_span_is_not_applied_to_the_whole_centerline() -> None:
    # One published elevation on a 14.6 m span does not describe a 2.8 km way.
    decision = decide_deck(
        accepted_structures=[{"structure_number": "3000154", "structure_length_m": 14.6}],
        deck_elevation_m=18.0,
        water_surfaces_m={"1.00": 20.0, "2.00": 21.0},
        length_m_inside=2826.5,
    )
    assert decision["exposure_status"] == "bridge_deck_unmatched"
    assert decision["depth_m_by_stage"] is None
    assert "span_shorter_than_centerline" in decision["unmatched_reasons"]


def test_old_alignment_does_not_inherit_the_current_route() -> None:
    assert identity_match("OLD NJ 27", "Main Street;Princeton-Kingston Road", "NJ 27") is None
    assert identity_match("NJ 27", "Princeton-Kingston Road", "NJ 27") == "route_ref"
    assert identity_match("QUAKER RD", "Quaker Road", "CR 533") == "facility_name"
    assert identity_match("POE ROAD", "Poe Road", None) == "facility_name"
    assert identity_match("OLD NJ 27", "Old Lincoln Highway", None) is None
    assert decode_nbi_coordinate("40181800", "lat") == pytest.approx(40.305)
    assert decode_nbi_coordinate("074410600", "lon") == pytest.approx(-74.685)
    assert nbi_has_deck_elevation_column(["DECK_COND_058", "DECK_WIDTH_MT_052", "LAT_016"]) is False


def test_quaker_road_has_no_deck_elevation(settings: dict) -> None:
    payload = _script().build_join(settings)
    assert payload["hurricane_ida_depth"] is False
    assert payload["event_time"] is None
    assert payload["terrain_under_bridge_used_as_deck"] is False
    assert payload["accessibility_rerun"] is False
    assert payload["n_bridge_centerlines"] == 20
    assert payload["n_with_deck_elevation"] == 0
    assert payload["n_sampled"] == 0
    assert payload["sources"][0]["vertical_datum"] is None
    assert payload["sources"][0]["deck_elevation_column_present"] is False
    by_id = {item["centerline_id"]: item for item in payload["centerlines"]}
    long_way = by_id[QUAKER_LONG]
    short_way = by_id[QUAKER_SHORT]
    assert long_way["name"] == "Quaker Road"
    assert long_way["ref"] == "CR 533"
    assert long_way["exposure_status"] == "bridge_deck_unmatched"
    assert long_way["deck_elevation_m"] is None
    assert long_way["depth_m_by_stage"] is None
    assert long_way["terrain_used_as_deck"] is False
    numbers = {item["structure_number"] for item in long_way["accepted_structures"]}
    assert numbers == {"3000154", "1100082"}
    canal = next(item for item in long_way["accepted_structures"] if item["structure_number"] == "3000154")
    brook = next(item for item in long_way["accepted_structures"] if item["structure_number"] == "1100082")
    assert canal["feature_intersected"] == "DELAWARE&RARITAN CANAL"
    assert canal["structure_length_m"] == pytest.approx(14.6)
    assert canal["deck_elevation_m"] is None
    assert brook["feature_intersected"] == "STONY BROOK"
    assert brook["structure_length_m"] == pytest.approx(24.7)
    assert "multiple_structures_on_centerline" in long_way["unmatched_reasons"]
    assert "no_published_deck_elevation" in long_way["unmatched_reasons"]
    assert short_way["exposure_status"] == "bridge_deck_unmatched"
    assert short_way["accepted_structures"] == []
    assert short_way["deck_elevation_m"] is None
    assert "no_inventory_match" in short_way["unmatched_reasons"]
    # The US 206 bridge sits near this short way. It is not a Quaker Road join.
    assert short_way["nearest_structure"]["structure_number"] in {"1129154", "1129155"}
    assert short_way["nearest_structure"]["accepted"] is False


def test_saved_join_matches_the_quaker_rule(project_root: Path, settings: dict) -> None:
    path = project_root / "data" / "processed" / "bridge_deck_join.json"
    if not path.is_file():
        pytest.fail("Bridge-deck join is missing. Run python3 scripts/bridge_decks.py.")
    saved = json.loads(path.read_text(encoding="utf-8"))
    fresh = _script().build_join(settings)
    assert saved["n_with_deck_elevation"] == fresh["n_with_deck_elevation"] == 0
    saved_long = next(item for item in saved["centerlines"] if item["centerline_id"] == QUAKER_LONG)
    fresh_long = next(item for item in fresh["centerlines"] if item["centerline_id"] == QUAKER_LONG)
    assert saved_long["exposure_status"] == fresh_long["exposure_status"] == "bridge_deck_unmatched"
    assert {item["structure_number"] for item in saved_long["accepted_structures"]} == {
        item["structure_number"] for item in fresh_long["accepted_structures"]
    }


def test_dashboard_keeps_a_sampled_deck_distinct(project_root: Path, settings: dict) -> None:
    join = json.loads((project_root / "data" / "processed" / "bridge_deck_join.json").read_text())
    collection = build_road_collection(
        project_root / "data" / "processed" / "princeton_accessibility.geojson",
        join,
    )
    bridges = [feature for feature in collection["features"] if feature["properties"]["is_bridge"]]
    assert len(bridges) == 20
    assert all(feature["properties"]["deck_status"] == "bridge_deck_unmatched" for feature in bridges)
    assert all(feature["properties"]["deck_elevation_m"] is None for feature in bridges)
    quaker = [
        feature["properties"]
        for feature in bridges
        if feature["properties"]["centerline_id"] in {QUAKER_LONG, QUAKER_SHORT}
    ]
    assert len(quaker) == 2
    assert all("No published deck elevation" in item["deck_note"] for item in quaker)
    page = (project_root / "web" / "app.js").read_text(encoding="utf-8")
    assert 'bridge_deck_sampled: "#0e7c86"' in page
    assert 'bridge_deck_unmatched: "#6d4ea8"' in page
    # A sampled status on one feature has to take the teal color, not purple.
    sampled = dict(bridges[0])
    sampled["properties"] = dict(sampled["properties"])
    sampled["properties"]["deck_status"] = "bridge_deck_sampled"
    assert sampled["properties"]["deck_status"] != bridges[0]["properties"]["deck_status"]
    assert settings["paths"]["bridge_deck_join"].endswith("bridge_deck_join.json")


def test_name_and_distance_both_have_to_hold() -> None:
    # 100 US survey feet is 30.48 m, inside the 40 m cap. The name matches.
    line = LineString([(0, 0), (1000, 0)])
    near = Point(500, 100)
    far = Point(500, 200)  # 200 ft is about 61 m, outside the cap.
    structures = [
        {
            "structure_number": "3000154",
            "facility_carried": "QUAKER RD",
            "feature_intersected": "DELAWARE&RARITAN CANAL",
            "location": "1/2 MI WEST OF RT US 1",
            "latitude": 40.305,
            "longitude": -74.685,
            "structure_length_m": 14.6,
            "max_span_m": 4.6,
            "deck_width_m": 13.2,
            "year_built": "1951",
            "year_reconstructed": "2020",
            "inspection_month": "2023-06",
            "deck_condition_code": "7",
            "deck_elevation_m": None,
            "geometry": near,
        },
        {
            "structure_number": "999",
            "facility_carried": "QUAKER RD",
            "feature_intersected": "SOMEWHERE",
            "location": "",
            "latitude": 0.0,
            "longitude": 0.0,
            "structure_length_m": 10.0,
            "deck_elevation_m": 12.0,
            "geometry": far,
        },
    ]
    result = assess_centerline(
        name="Quaker Road",
        ref="CR 533",
        line=line,
        length_m_inside=400.0,
        structures=structures,
    )
    assert [item["structure_number"] for item in result["accepted_structures"]] == ["3000154"]
    assert result["exposure_status"] == "bridge_deck_unmatched"
    assert result["deck_elevation_m"] is None
    # The far structure has an elevation and the right name. It is still not used.
    assert result["depth_m_by_stage"] is None
