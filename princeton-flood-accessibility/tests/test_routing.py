"""Directions use the saved graph and the saved assumed-closed marks."""

from pathlib import Path

from dashboard.routing import build_routing_network


def _network(project_root: Path) -> dict:
    return build_routing_network(
        project_root / "data" / "processed" / "princeton_drive_network.graphml",
        project_root / "data" / "processed" / "princeton_accessibility.geojson",
    )


def test_closed_marks_come_from_the_saved_statuses(project_root: Path) -> None:
    network = _network(project_root)
    assert network["hurricane_ida_depth"] is False
    assert network["interpolated"] is False
    assert network["enso_scales_depths"] is False
    stage = network["stages"].index("0.25")
    assert network["closed_counts"][stage] == 15
    assert _closed_edge_count(network, stage) >= 15
    high = network["stages"].index("2.00")
    assert network["closed_counts"][high] == 90


def test_an_open_path_does_not_use_a_closed_edge(project_root: Path) -> None:
    network = _network(project_root)
    stage = network["stages"].index("0.25")
    start = _node_on(network, "Nassau Street", stage)
    end = _node_on(network, "Witherspoon Street", stage)
    path = _shortest(network, start, end, stage)
    assert path is not None
    assert path["metres"] > 100
    assert all((edge.get("c", 0) & (1 << stage)) == 0 for edge in path["edges"])


def _closed_edge_count(network: dict, stage: int) -> int:
    return sum(1 for edge in network["edges"] if edge.get("c", 0) & (1 << stage))


def _node_on(network: dict, name: str, stage: int) -> int:
    open_edges = [
        edge for edge in network["edges"]
        if edge.get("name") == name and (edge.get("c", 0) & (1 << stage)) == 0
    ]
    assert open_edges
    best = max(open_edges, key=lambda edge: edge["m"])
    return best["u"]


def _shortest(network: dict, start: int, end: int, stage: int) -> dict | None:
    outgoing: dict[int, list[dict]] = {}
    for edge in network["edges"]:
        outgoing.setdefault(edge["u"], []).append(edge)
    dist = {start: 0.0}
    prev: dict[int, dict] = {}
    seen: set[int] = set()
    while True:
        current = None
        best = None
        for node, value in dist.items():
            if node in seen:
                continue
            if best is None or value < best:
                best = value
                current = node
        if current is None or best is None:
            return None
        if current == end:
            break
        seen.add(current)
        for edge in outgoing.get(current, []):
            if edge.get("c", 0) & (1 << stage):
                continue
            nxt = best + edge["m"]
            if nxt < dist.get(edge["v"], float("inf")):
                dist[edge["v"]] = nxt
                prev[edge["v"]] = edge
    edges = []
    cursor = end
    while cursor != start:
        edge = prev.get(cursor)
        if edge is None:
            return None
        edges.append(edge)
        cursor = edge["u"]
    return {"metres": dist[end], "edges": edges}
