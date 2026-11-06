"""Length, connectivity, and intersection counts.

Directed OSMnx edges store both directions of a two-way street. Summing
those edges double-counts centerline length. Counts below use one edge per
physical street segment, identified by the unordered endpoint pair plus the
OSM way id (or ids, after simplification).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import networkx as nx
import osmnx as ox

from geospatial.crs import us_survey_feet_to_m


def canonical_osmid(value: Any) -> tuple[str, ...]:
    """Stable identity for an OSM way id or a list of ids on a simplified edge."""
    if isinstance(value, (list, tuple)):
        return tuple(sorted(str(item) for item in value))
    if value is None:
        raise ValueError("Edge is missing osmid; cannot pair the two directions of a street.")
    return (str(value),)


def centerline_identity(u: Any, v: Any, data: dict[str, Any]) -> tuple[Any, ...]:
    """Identity shared by the two directed copies of one street segment."""
    return (tuple(sorted((int(u), int(v)))), canonical_osmid(data.get("osmid")))


def iter_centerlines(graph: nx.MultiDiGraph) -> Iterable[tuple[Any, Any, Any, dict[str, Any]]]:
    """Yield one directed edge record for each physical centerline.

    The first edge seen for an identity is kept. Opposite directions of the
    same OSM way collapse. Distinct parallel ways between the same nodes do
    not, because their OSM ids differ.
    """
    chosen: dict[tuple[Any, ...], tuple[Any, Any, Any, dict[str, Any]]] = {}
    for u, v, key, data in graph.edges(keys=True, data=True):
        identity = centerline_identity(u, v, data)
        if identity not in chosen:
            chosen[identity] = (u, v, key, data)
    return chosen.values()


def sum_attr(graph: nx.MultiDiGraph, attr: str, *, centerlines_only: bool) -> float:
    """Sum an edge attribute, optionally once per physical centerline."""
    records = iter_centerlines(graph) if centerlines_only else graph.edges(keys=True, data=True)
    total = 0.0
    for record in records:
        data = record[-1]
        if attr not in data or data[attr] is None:
            raise ValueError(f"Edge is missing {attr}.")
        total += float(data[attr])
    return total


def weakly_connected_component_count(graph: nx.MultiDiGraph) -> int:
    """Number of pieces in the directed graph, ignoring one-way direction."""
    return int(nx.number_weakly_connected_components(graph))


def strongly_connected_component_count(graph: nx.MultiDiGraph) -> int:
    """Number of pieces in which every node can reach every other by direction."""
    return int(nx.number_strongly_connected_components(graph))


def largest_weak_component_nodes(graph: nx.MultiDiGraph) -> int:
    """Node count of the largest weakly connected component."""
    if graph.number_of_nodes() == 0:
        return 0
    return max(len(component) for component in nx.weakly_connected_components(graph))


def intersection_count(graph: nx.MultiDiGraph, *, min_streets: int = 2) -> int:
    """OSMnx intersection count: nodes with at least ``min_streets`` physical streets.

    The default of 2 matches OSMnx: a node is an intersection when it is not
    a dead end. Nodes with exactly two streets can remain after simplification
    where a tag changes or the municipal cut ends a segment. Junctions of
    three or more streets are available with ``min_streets=3``.
    """
    return int(ox.stats.intersection_count(graph, min_streets=min_streets))


def dead_end_count(graph: nx.MultiDiGraph) -> int:
    """Nodes with exactly one incident physical street in this graph."""
    streets = ox.stats.count_streets_per_node(graph)
    return int(sum(1 for count in streets.values() if count == 1))


def planar_length_m_from_feet(length_ftus: float) -> float:
    """State-plane length in feet to metres. Thin wrapper so tests name the step."""
    return us_survey_feet_to_m(length_ftus)
