"""Closure rule, component length, and bridge edges that stay routable."""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import networkx as nx
import pytest

from network.disruption import STATUS_BRIDGE
from network.disruption import STATUS_CLOSED
from network.disruption import STATUS_NO_CHANNEL
from network.disruption import STATUS_PARTIAL
from network.disruption import bridge_centerline_keys
from network.disruption import centerline_key
from network.disruption import choose_destinations
from network.disruption import closure_decision
from network.disruption import component_records
from network.disruption import osmid_key
from network.disruption import route_between
from network.disruption import without_closed_centerlines
from network.stats import weakly_connected_component_count


def _decision(**overrides):
    values = {
        "exposure_status": "scenario_depth",
        "is_bridge": False,
        "length_m_inside": 100.0,
        "wet_piece_length_m": 0.0,
        "between_piece_length_m": 0.0,
        "depth_max_m": 0.0,
        "closure_fraction": 0.50,
        "accessible_below_m": 0.10,
        "closed_at_m": 0.30,
    }
    values.update(overrides)
    return closure_decision(**values)


def test_a_wet_end_does_not_close_the_centerline() -> None:
    decision = _decision(wet_piece_length_m=10.0, depth_max_m=1.2)
    assert decision["assumed_closed"] is False
    assert decision["routing_status"] == STATUS_PARTIAL
    assert decision["max_based_at_or_above_closure_depth"] is True
    assert decision["wet_fraction_of_inside_length"] == 0.10
    assert decision["hurricane_ida_depth"] is False
    assert decision["event_time"] is None


def test_half_the_inside_length_is_the_closure_rule() -> None:
    decision = _decision(wet_piece_length_m=50.0, depth_max_m=0.8)
    assert decision["assumed_closed"] is True
    assert decision["routing_status"] == STATUS_CLOSED
    assert decision["not_a_closure_standard"] is True


def test_bridge_deck_is_not_closed_from_terrain() -> None:
    decision = _decision(
        exposure_status="bridge_deck_unmatched",
        is_bridge=True,
        wet_piece_length_m=100.0,
        depth_max_m=2.0,
    )
    assert decision["assumed_closed"] is False
    assert decision["routing_status"] == STATUS_BRIDGE
    assert decision["max_based_at_or_above_closure_depth"] is False


def test_missing_channel_is_not_called_dry_or_closed() -> None:
    decision = _decision(exposure_status="outside_channel_buffer", wet_piece_length_m=None, depth_max_m=None)
    assert decision["assumed_closed"] is False
    assert decision["routing_status"] == STATUS_NO_CHANNEL
    assert decision["wet_fraction_of_inside_length"] is None


def test_osmid_list_matches_semicolon_text() -> None:
    assert osmid_key([48787153, 500296560]) == osmid_key("500296560;48787153")
    assert centerline_key(2, 1, [10, 3]) == centerline_key(1, 2, "3;10")


def test_removing_one_link_splits_components_and_keeps_the_bridge() -> None:
    graph = nx.MultiDiGraph()
    graph.add_edge(1, 2, key=0, osmid=10, length_m=5.0, is_bridge=True)
    graph.add_edge(2, 1, key=0, osmid=10, length_m=5.0, is_bridge=True)
    graph.add_edge(2, 3, key=0, osmid=11, length_m=8.0, is_bridge=False)
    graph.add_edge(3, 2, key=0, osmid=11, length_m=8.0, is_bridge=False)
    graph.add_edge(3, 4, key=0, osmid=12, length_m=4.0, is_bridge=False)
    graph.add_edge(4, 3, key=0, osmid=12, length_m=4.0, is_bridge=False)
    assert weakly_connected_component_count(graph) == 1
    kept = without_closed_centerlines(graph, {centerline_key(2, 3, 11)})
    assert kept.has_edge(1, 2)
    assert kept.has_edge(2, 1)
    assert not kept.has_edge(2, 3)
    assert not kept.has_edge(3, 2)
    assert weakly_connected_component_count(kept) == 2
    records = [
        {"endpoints": (1, 2), "length_m_inside": 5.0, "assumed_closed": False},
        {"endpoints": (2, 3), "length_m_inside": 8.0, "assumed_closed": True},
        {"endpoints": (3, 4), "length_m_inside": 4.0, "assumed_closed": False},
    ]
    components = component_records(kept, records)
    assert [component["n_nodes"] for component in components] == [2, 2]
    assert components[0]["length_m_inside"] == 5.0
    assert components[1]["length_m_inside"] == 4.0
    assert centerline_key(1, 2, 10) in bridge_centerline_keys(kept)
    assert centerline_key(2, 3, 11) not in bridge_centerline_keys(kept)


def test_string_length_on_a_multigraph_is_a_numeric_weight() -> None:
    graph = nx.MultiDiGraph()
    graph.add_edge(1, 2, key=0, osmid=1, length_m="100.0", maxspeed_mph="60")
    graph.add_edge(1, 2, key=1, osmid=3, length_m="40.0")
    graph.add_edge(2, 3, key=0, osmid=2, length_m="50.5")
    result = route_between(graph, 1, 3)
    assert result["status"] == "connected"
    assert result["path_length_m"] == pytest.approx(90.5)


def test_saved_run_keeps_bridges_routable_and_is_not_ida() -> None:
    root = Path(__file__).resolve().parents[1]
    stats = json.loads((root / "data" / "processed" / "accessibility_stats.json").read_text())
    assert stats["hurricane_ida_depth"] is False
    assert stats["event_time"] is None
    assert stats["dashboard"] is False
    assert stats["aadt"]["aadt_summed"] is False
    by_stage = {stage["stage_above_channel_dem_m"]: stage for stage in stats["stages"]}
    assert by_stage[1.0]["n_assumed_closed"] == 33
    assert by_stage[1.0]["n_max_based_at_or_above_closure_depth"] == 143
    assert by_stage[1.0]["n_weak_components"] == 13
    assert by_stage[2.0]["n_assumed_closed"] == 90
    assert by_stage[2.0]["n_max_based_at_or_above_closure_depth"] == 234
    assert by_stage[2.0]["n_weak_components"] == 42
    for stage in stats["stages"]:
        remaining = sum(component["length_m_inside"] for component in stage["components"])
        assert remaining + stage["assumed_closed_length_m_inside"] == pytest.approx(stage["length_m_inside"])
    table = gpd.read_file(root / "data" / "processed" / "princeton_accessibility.gpkg", layer="centerline_accessibility")
    bridges = table["exposure_status"] == "bridge_deck_unmatched"
    assert int(bridges.sum()) == 20
    assert not bool(table.loc[bridges, "assumed_closed_stage_1_00"].any())
    assert not bool(table.loc[bridges, "assumed_closed_stage_2_00"].any())
    unmatched = table["exposure_status"] == "outside_channel_buffer"
    assert set(table.loc[unmatched, "routing_status_stage_1_00"]) == {"unmatched_no_channel"}
    assert set(table.loc[unmatched, "routing_status_stage_2_00"]) == {"unmatched_no_channel"}


def test_travel_time_needs_an_explicit_speed_and_a_gap_is_not_infinite() -> None:
    graph = nx.MultiDiGraph()
    graph.add_edge(1, 2, key=0, osmid=1, length_m=1609.344, maxspeed_mph="60")
    connected = route_between(graph, 1, 2)
    assert connected["status"] == "connected"
    assert connected["path_length_m"] == 1609.344
    assert abs(connected["travel_time_s"] - 60.0) < 1e-6
    graph.edges[1, 2, 0]["maxspeed_mph"] = None
    missing = route_between(graph, 1, 2)
    assert missing["status"] == "connected"
    assert missing["travel_time_s"] is None
    assert missing["travel_time_status"] == "maxspeed_missing"
    disconnected = route_between(graph, 1, 9)
    assert disconnected["status"] == "disconnected"
    assert disconnected["path_length_m"] is None
    assert disconnected["travel_time_s"] is None


def test_a_missing_hospital_is_not_invented() -> None:
    places = [
        {"amenity": "school", "name": "Other School", "osm_id": 2, "inside": True},
        {"amenity": "school", "name": "Princeton High School", "osm_id": 9, "inside": True},
        {"amenity": "school", "name": "Outside High School", "osm_id": 1, "inside": False},
        {"amenity": "townhall", "name": "Princeton Municipal Building", "osm_id": 4, "inside": True},
    ]
    chosen = choose_destinations(places)
    assert "hospital" in chosen["missing_roles"]
    assert "fire_station" in chosen["missing_roles"]
    assert "police" in chosen["missing_roles"]
    by_role = {place["role"]: place["name"] for place in chosen["destinations"]}
    assert by_role["school"] == "Princeton High School"
    assert by_role["municipal"] == "Princeton Municipal Building"
