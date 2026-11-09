"""Centerline length must not double-count a two-way street."""

from __future__ import annotations

import networkx as nx
import pytest

from geospatial.flood import FloodModelNotAvailable
from geospatial.flood import depth_on_roads
from network.stats import iter_centerlines
from network.stats import sum_attr
from network.stats import weakly_connected_component_count
from network.tags import is_bridge_tag
from network.tags import is_positive_layer
from network.tags import is_tunnel_tag
from network.tags import parse_explicit_maxspeed_mph


def _graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    graph.add_node(1, x=0, y=0)
    graph.add_node(2, x=1, y=0)
    graph.add_node(3, x=2, y=0)
    graph.add_node(4, x=0, y=1)
    graph.add_node(5, x=1, y=1)
    # Two directions of one street.
    graph.add_edge(1, 2, key=0, osmid=10, length_m=100.0)
    graph.add_edge(2, 1, key=0, osmid=10, length_m=100.0)
    # A different parallel way between the same nodes.
    graph.add_edge(1, 2, key=1, osmid=12, length_m=40.0)
    # One-way street.
    graph.add_edge(2, 3, key=0, osmid=11, length_m=50.0)
    # Separate component.
    graph.add_edge(4, 5, key=0, osmid=20, length_m=25.0)
    graph.add_edge(5, 4, key=0, osmid=20, length_m=25.0)
    return graph


def test_two_way_length_is_not_doubled() -> None:
    graph = _graph()
    assert sum_attr(graph, "length_m", centerlines_only=False) == pytest.approx(340.0)
    assert sum_attr(graph, "length_m", centerlines_only=True) == pytest.approx(215.0)
    assert len(list(iter_centerlines(graph))) == 4


def test_parallel_ways_stay_separate() -> None:
    graph = _graph()
    identities = {edge[3]["osmid"] for edge in iter_centerlines(graph) if {edge[0], edge[1]} == {1, 2}}
    assert identities == {10, 12}


def test_simplified_edge_osmid_list_matches_either_order() -> None:
    graph = nx.MultiDiGraph()
    graph.add_edge(1, 2, key=0, osmid=[3, 4], length_m=10.0)
    graph.add_edge(2, 1, key=0, osmid=[4, 3], length_m=10.0)
    assert sum_attr(graph, "length_m", centerlines_only=True) == pytest.approx(10.0)


def test_component_count() -> None:
    assert weakly_connected_component_count(_graph()) == 2


def test_bridge_tag_does_not_treat_missing_as_bridge() -> None:
    assert is_bridge_tag("yes")
    assert is_bridge_tag("viaduct")
    assert is_bridge_tag(["yes", "no"])
    assert not is_bridge_tag("no")
    assert not is_bridge_tag(None)
    assert not is_bridge_tag("nan")
    assert is_tunnel_tag("yes")
    assert not is_tunnel_tag("no")
    assert is_positive_layer("1")
    assert is_positive_layer(["0", "2"])
    assert not is_positive_layer("0")
    assert not is_positive_layer(None)


def test_maxspeed_without_units_is_not_invented() -> None:
    assert parse_explicit_maxspeed_mph("25 mph") == pytest.approx(25.0)
    assert parse_explicit_maxspeed_mph("40 km/h") == pytest.approx(40 * 1000 / 1609.344)
    assert parse_explicit_maxspeed_mph("25") is None
    assert parse_explicit_maxspeed_mph(["25 mph", "35 mph"]) is None
    assert parse_explicit_maxspeed_mph(None) is None


def test_flood_helper_refuses_to_invent_depth() -> None:
    with pytest.raises(FloodModelNotAvailable):
        depth_on_roads([1, 2, 3])
