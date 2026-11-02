"""Scenario road closure and connectivity.

Depths come from the labeled 3DEP scenario. Nothing here is a Hurricane Ida
observation, and the two stages are not a time series. A bridge deck with no
depth stays in the graph. A centerline with no channel match stays in the
graph and is not called dry.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from collections.abc import Sequence
from typing import Any

import networkx as nx

METRES_PER_MILE = 1609.344

STATUS_CLOSED = "assumed_closed"
STATUS_ACCESSIBLE = "accessible_routable"
STATUS_AT_RISK = "at_risk_routable"
STATUS_PARTIAL = "partial_above_0_30_not_closed"
STATUS_BRIDGE = "bridge_deck_unmatched"
STATUS_NO_CHANNEL = "unmatched_no_channel"
STATUS_OUTSIDE = "outside_municipality"
STATUS_NODATA = "dem_nodata"

_UNMATCHED_ROUTABLE = {
    "outside_channel_buffer": STATUS_NO_CHANNEL,
    "dem_nodata": STATUS_NODATA,
    "outside_municipality": STATUS_OUTSIDE,
    "tunnel_unmatched": "tunnel_unmatched",
}


def osmid_key(value: Any) -> tuple[str, ...]:
    """Stable OSM way id, whether the edge stores an int, a list, or 'a;b'."""
    if isinstance(value, (list, tuple)):
        parts = [str(item) for item in value]
    else:
        text = str(value).strip()
        if text.startswith("[") and text.endswith("]"):
            text = text[1:-1]
        parts = [part.strip() for part in text.replace(",", ";").split(";")]
    cleaned = tuple(sorted(part for part in parts if part and part.lower() != "none"))
    if not cleaned:
        raise ValueError(f"Edge is missing osmid: {value!r}")
    return cleaned


def centerline_key(u: Any, v: Any, osmid: Any) -> tuple[Any, ...]:
    """Identity shared by both directions of one physical centerline."""
    return (tuple(sorted((int(u), int(v)))), osmid_key(osmid))


def _missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return False


def _float_or_none(value: Any) -> float | None:
    if _missing(value):
        return None
    return float(value)


def wet_fraction(wet_piece_length_m: Any, length_m_inside: Any) -> float | None:
    """Share of the inside centerline whose pieces are at or above the cut.

    The denominator is the centerline length inside the municipality, not
    the wet pieces alone. A short wet end therefore stays a small fraction.
    """
    inside = _float_or_none(length_m_inside)
    if inside is None or inside <= 0:
        return None
    wet = _float_or_none(wet_piece_length_m)
    if wet is None:
        wet = 0.0
    if wet < 0:
        raise ValueError("Wet piece length cannot be negative.")
    return wet / inside


def closure_decision(
    *,
    exposure_status: str,
    is_bridge: bool,
    length_m_inside: Any,
    wet_piece_length_m: Any,
    between_piece_length_m: Any,
    depth_max_m: Any,
    closure_fraction: float,
    accessible_below_m: float,
    closed_at_m: float,
) -> dict[str, Any]:
    """Decide whether one centerline is removed from the routable graph.

    The centerline is assumed closed only when ``closure_fraction`` of its
    inside length has pieces at or above ``closed_at_m``. A maximum that
    crosses the cut does not close the street by itself. Bridge decks and
    centerlines with no channel match are never closed. The depth cuts are
    preliminary assumptions, not a closure standard.
    """
    if not 0 < closure_fraction <= 1:
        raise ValueError("closure_fraction must be in (0, 1].")
    if not 0 <= accessible_below_m < closed_at_m:
        raise ValueError("The accessible cut must be below the assumed-closure cut.")
    max_depth = _float_or_none(depth_max_m)
    max_based = (
        exposure_status == "scenario_depth"
        and max_depth is not None
        and max_depth >= closed_at_m
    )
    fraction = None
    if is_bridge or exposure_status == "bridge_deck_unmatched":
        status = STATUS_BRIDGE
        closed = False
    elif exposure_status in _UNMATCHED_ROUTABLE:
        status = _UNMATCHED_ROUTABLE[exposure_status]
        closed = False
    elif exposure_status != "scenario_depth":
        raise ValueError(f"Unrecognized exposure status {exposure_status!r}.")
    else:
        fraction = wet_fraction(wet_piece_length_m, length_m_inside)
        wet = _float_or_none(wet_piece_length_m) or 0.0
        between = _float_or_none(between_piece_length_m) or 0.0
        if fraction is not None and fraction >= closure_fraction:
            status = STATUS_CLOSED
            closed = True
        elif wet > 0:
            status = STATUS_PARTIAL
            closed = False
        elif between > 0:
            status = STATUS_AT_RISK
            closed = False
        else:
            status = STATUS_ACCESSIBLE
            closed = False
    return {
        "routing_status": status,
        "assumed_closed": closed,
        "wet_fraction_of_inside_length": fraction,
        "max_based_at_or_above_closure_depth": max_based,
        "hurricane_ida_depth": False,
        "event_time": None,
        "not_a_closure_standard": True,
    }


def edge_speed_mph(data: dict[str, Any]) -> float | None:
    """Explicit miles per hour already stored on the edge. Never imputed."""
    raw = data.get("maxspeed_mph")
    if _missing(raw):
        return None
    text = str(raw).strip()
    if text.lower() in {"", "none", "nan"}:
        return None
    try:
        speed = float(text)
    except ValueError:
        return None
    if not math.isfinite(speed) or speed <= 0:
        return None
    return speed


def without_closed_centerlines(graph: nx.MultiDiGraph, closed_keys: set[tuple[Any, ...]]) -> nx.MultiDiGraph:
    """Copy the graph and drop both directions of each closed centerline."""
    kept = graph.copy()
    drop = [
        (u, v, key)
        for u, v, key, data in kept.edges(keys=True, data=True)
        if centerline_key(u, v, data.get("osmid")) in closed_keys
    ]
    kept.remove_edges_from(drop)
    return kept


def ordered_weak_components(graph: nx.MultiDiGraph) -> list[set[Any]]:
    """Largest component first. Ties break on the smallest node id."""
    components = list(nx.weakly_connected_components(graph))
    return sorted(components, key=lambda nodes: (-len(nodes), min(nodes) if nodes else 0))


def component_records(
    graph: nx.MultiDiGraph,
    centerlines: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Weak components, with the inside length of the centerlines still in each.

    Length is not a neighborhood population. A new component can be one
    dangling node. This function does not call any component isolated from
    services.
    """
    node_component: dict[Any, int] = {}
    ordered = ordered_weak_components(graph)
    summaries = []
    for index, nodes in enumerate(ordered):
        for node in nodes:
            node_component[node] = index
        summaries.append(
            {
                "component_id": index,
                "n_nodes": len(nodes),
                "n_centerlines": 0,
                "length_m_inside": 0.0,
                "largest": index == 0,
            }
        )
    for record in centerlines:
        if record.get("assumed_closed"):
            continue
        key_nodes = record.get("endpoints")
        if not key_nodes:
            continue
        u, v = key_nodes
        comp_u = node_component.get(u)
        comp_v = node_component.get(v)
        if comp_u is None or comp_u != comp_v:
            continue
        summaries[comp_u]["n_centerlines"] += 1
        summaries[comp_u]["length_m_inside"] += float(record["length_m_inside"])
    return summaries


def bridge_centerline_keys(graph: nx.MultiDiGraph) -> set[tuple[Any, ...]]:
    """Centerlines whose removal increases the weak-component count.

    A node pair with two distinct centerlines is not a bridge: either one
    can be removed and the pair stays connected. The test is on the
    undirected skeleton, which matches weakly connected components.
    """
    pair_keys: dict[tuple[int, int], set[tuple[Any, ...]]] = {}
    for u, v, _key, data in graph.edges(keys=True, data=True):
        pair = tuple(sorted((int(u), int(v))))
        pair_keys.setdefault(pair, set()).add(centerline_key(u, v, data.get("osmid")))
    skeleton = nx.Graph()
    skeleton.add_nodes_from(int(node) for node in graph.nodes)
    for pair, keys in pair_keys.items():
        if keys:
            skeleton.add_edge(pair[0], pair[1])
    bridges = {tuple(sorted((int(u), int(v)))) for u, v in nx.bridges(skeleton)}
    critical: set[tuple[Any, ...]] = set()
    for pair, keys in pair_keys.items():
        if pair in bridges and len(keys) == 1:
            critical.add(next(iter(keys)))
    return critical


def _length_weight(_u: Any, _v: Any, data: dict[str, Any]) -> float:
    """Edge length for Dijkstra on a Graph or a MultiDiGraph.

    A callable weight is not unwrapped by NetworkX. On a MultiDiGraph the
    third argument is ``{edge key: attribute dict}``. GraphML also reloads
    ``length_m`` as text, so the value is cast before it is added.
    """
    if data and all(isinstance(value, dict) for value in data.values()):
        return min(float(attributes["length_m"]) for attributes in data.values())
    return float(data["length_m"])


def _shortest_edge(graph: nx.MultiDiGraph, u: Any, v: Any) -> dict[str, Any]:
    choices = graph.get_edge_data(u, v)
    if not choices:
        raise nx.NetworkXNoPath(f"No edge remains between {u} and {v}.")
    return min(choices.values(), key=lambda data: float(data["length_m"]))


def route_between(graph: nx.MultiDiGraph, origin: Any, destination: Any) -> dict[str, Any]:
    """Directed shortest path by ``length_m``.

    Travel time is the sum of length/speed only when every edge on the path
    has an explicit maxspeed. A missing speed is left missing. No path is
    ``disconnected``, not an infinite time.
    """
    if origin == destination:
        return {
            "status": "same_node",
            "path_length_m": 0.0,
            "n_edges": 0,
            "travel_time_s": 0.0,
            "travel_time_status": "zero_length",
            "centerline_keys": [],
        }
    try:
        nodes = nx.shortest_path(graph, origin, destination, weight=_length_weight)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return {
            "status": "disconnected",
            "path_length_m": None,
            "n_edges": None,
            "travel_time_s": None,
            "travel_time_status": "disconnected",
            "centerline_keys": [],
        }
    length_m = 0.0
    time_s = 0.0
    missing_speed = False
    keys = []
    for start, end in zip(nodes, nodes[1:]):
        data = _shortest_edge(graph, start, end)
        edge_length = float(data["length_m"])
        length_m += edge_length
        keys.append(centerline_key(start, end, data.get("osmid")))
        speed = edge_speed_mph(data)
        if speed is None:
            missing_speed = True
        else:
            time_s += edge_length / (speed * METRES_PER_MILE / 3600.0)
    if missing_speed:
        return {
            "status": "connected",
            "path_length_m": length_m,
            "n_edges": len(keys),
            "travel_time_s": None,
            "travel_time_status": "maxspeed_missing",
            "centerline_keys": keys,
        }
    return {
        "status": "connected",
        "path_length_m": length_m,
        "n_edges": len(keys),
        "travel_time_s": time_s,
        "travel_time_status": "explicit_maxspeed",
        "centerline_keys": keys,
    }


def edges_on_many_paths(
    paths: Iterable[Sequence[tuple[Any, ...]]],
    *,
    min_fraction: float,
) -> dict[tuple[Any, ...], int]:
    """Centerlines used by at least ``min_fraction`` of the routed paths.

    Paths that are disconnected are not in ``paths``. The fraction is of
    the paths that were actually passed in.
    """
    if not 0 < min_fraction <= 1:
        raise ValueError("min_fraction must be in (0, 1].")
    counts: dict[tuple[Any, ...], int] = {}
    n_paths = 0
    for path in paths:
        n_paths += 1
        for key in set(path):
            counts[key] = counts.get(key, 0) + 1
    if n_paths == 0:
        return {}
    minimum = max(1, math.ceil(min_fraction * n_paths))
    return {key: count for key, count in counts.items() if count >= minimum}


def choose_destinations(places: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Pick one real place for each role. Do not fill a missing role.

    ``places`` are already limited to features inside the municipality.
    School preference is a name containing "High School". Fire preference
    is a name containing "Fire Department". Ties break on the smaller OSM id.
    """
    available = [place for place in places if place.get("inside") is True]
    missing = []
    chosen = []

    def take(role: str, candidates: list[dict[str, Any]], prefer: str | None) -> None:
        if not candidates:
            missing.append(role)
            return
        def sort_key(place: dict[str, Any]) -> tuple[int, int]:
            name = str(place.get("name") or "")
            preferred = 0 if prefer and prefer.lower() in name.lower() else 1
            return (preferred, int(place["osm_id"]))
        pick = sorted(candidates, key=sort_key)[0]
        chosen.append({**pick, "role": role})

    take("hospital", [p for p in available if p.get("amenity") == "hospital"], None)
    take("school", [p for p in available if p.get("amenity") == "school"], "High School")
    take("fire_station", [p for p in available if p.get("amenity") == "fire_station"], "Fire Department")
    take("police", [p for p in available if p.get("amenity") == "police"], None)
    take("municipal", [p for p in available if p.get("amenity") == "townhall"], "Municipal")
    return {"destinations": chosen, "missing_roles": missing}
