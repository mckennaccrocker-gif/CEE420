"""Saved drive network for directions on the public page.

Edges and lengths come from the saved graph. A centerline is left out of a
rise only when that rise already marks it assumed closed. This module does
not recompute a depth, interpolate a rise, scale by ENSO, or sample a deck.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from pyproj import Transformer

GRAPHML_NS = {"g": "http://graphml.graphdrawing.org/xmlns"}
TO_LONLAT = Transformer.from_crs("EPSG:3424", "EPSG:4326", always_xy=True)


def build_routing_network(graphml_path: Path, accessibility_path: Path) -> dict[str, Any]:
    """Compact directed network plus the saved assumed-closed marks."""
    closed_by_key, stages = _closed_marks(accessibility_path)
    nodes, edges = _read_graph(graphml_path)
    seen = set()
    for edge in edges:
        identity = (edge.pop("_pair"), _osmid_key(edge.pop("_osmid")))
        bits = closed_by_key.get(identity, 0)
        if bits:
            edge["c"] = bits
            seen.add(identity)
    missing = set(closed_by_key) - seen
    if missing:
        raise ValueError(f"{len(missing)} assumed-closed centerlines are not in the saved graph.")
    if not edges:
        raise ValueError(f"No edges in {graphml_path}.")
    if not closed_by_key:
        raise ValueError("The saved accessibility file has no assumed-closed centerline.")
    return {
        "hurricane_ida_depth": False,
        "interpolated": False,
        "enso_scales_depths": False,
        "closure": "assumed_closed centerlines are removed. Other saved statuses stay routable.",
        "stages": stages,
        "closed_counts": [
            sum(1 for bits in closed_by_key.values() if bits & (1 << index))
            for index in range(len(stages))
        ],
        "nodes": nodes,
        "edges": edges,
    }


def _closed_marks(path: Path) -> tuple[dict[tuple[tuple[int, int], str], int], list[str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    stages: list[str] | None = None
    closed: dict[tuple[tuple[int, int], str], int] = {}
    for feature in payload["features"]:
        props = feature["properties"]
        if stages is None:
            stages = _stage_ids(props)
        identity = _centerline_identity(str(props["centerline_id"]), str(props.get("osmid", "")))
        bits = 0
        for index, stage in enumerate(stages):
            slug = stage.replace(".", "_")
            if props.get(f"routing_status_stage_{slug}") == "assumed_closed":
                bits |= 1 << index
        if bits:
            closed[identity] = bits
    if not stages:
        raise ValueError(f"No routing statuses in {path}.")
    return closed, stages


def _stage_ids(props: dict[str, Any]) -> list[str]:
    slugs = [
        key.removeprefix("routing_status_stage_")
        for key in props
        if key.startswith("routing_status_stage_")
    ]
    ordered = sorted(slugs, key=lambda slug: float(slug.replace("_", ".")))
    return [f"{float(slug.replace('_', '.')):.2f}" for slug in ordered]


def _centerline_identity(centerline_id: str, osmid: str) -> tuple[tuple[int, int], str]:
    parts = centerline_id.split("_")
    if len(parts) < 4:
        raise ValueError(f"Unexpected centerline id {centerline_id!r}.")
    left, right = int(parts[0]), int(parts[1])
    return (tuple(sorted((left, right))), _osmid_key(osmid or "_".join(parts[3:])))


def _osmid_key(value: str) -> str:
    text = value.strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    parts = [part.strip().strip("'\"") for part in text.replace(",", ";").split(";")]
    return ";".join(sorted(part for part in parts if part and part.lower() not in {"", "none"}))


def _read_graph(path: Path) -> tuple[list[list[float]], list[dict[str, Any]]]:
    root = ET.parse(path).getroot()
    names = {item.attrib["id"]: item.attrib["attr.name"] for item in root.findall("g:key", GRAPHML_NS)}
    graph = root.find("g:graph", GRAPHML_NS)
    if graph is None:
        raise ValueError(f"{path} has no graph.")
    nodes: list[list[float]] = []
    coordinates: dict[int, tuple[float, float]] = {}
    for node in graph.findall("g:node", GRAPHML_NS):
        values = _data(node, names)
        node_id = int(node.attrib["id"])
        lon, lat = _lonlat(float(values["x"]), float(values["y"]))
        coordinates[node_id] = (lon, lat)
        nodes.append([node_id, lon, lat])
    edges: list[dict[str, Any]] = []
    for edge in graph.findall("g:edge", GRAPHML_NS):
        values = _data(edge, names)
        start = int(edge.attrib["source"])
        end = int(edge.attrib["target"])
        line = _edge_line(values.get("geometry"), coordinates[start], coordinates[end])
        record: dict[str, Any] = {
            "u": start,
            "v": end,
            "m": round(float(values["length_m"]), 1),
            "g": line,
            "_pair": tuple(sorted((start, end))),
            "_osmid": str(values.get("osmid", "")).strip(),
        }
        name = values.get("name")
        if name and str(name).strip().lower() not in {"", "none", "nan"}:
            record["name"] = str(name)
        edges.append(record)
    return nodes, edges


def _data(element: ET.Element, names: dict[str, str]) -> dict[str, str]:
    values = {}
    for item in element.findall("g:data", GRAPHML_NS):
        label = names.get(item.attrib.get("key", ""))
        if label and item.text:
            values[label] = item.text
    return values


def _edge_line(text: str | None, start: tuple[float, float], end: tuple[float, float]) -> list[list[float]]:
    if not text or "LINESTRING" not in text:
        return [[start[0], start[1]], [end[0], end[1]]]
    body = text[text.find("(") + 1 : text.rfind(")")]
    points = []
    for pair in body.split(","):
        east, north = pair.split()
        lon, lat = _lonlat(float(east), float(north))
        points.append([lon, lat])
    return points or [[start[0], start[1]], [end[0], end[1]]]


def _lonlat(east: float, north: float) -> tuple[float, float]:
    lon, lat = TO_LONLAT.transform(east, north)
    return (round(lon, 6), round(lat, 6))


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    payload = build_routing_network(
        root / "data" / "processed" / "princeton_drive_network.graphml",
        root / "data" / "processed" / "princeton_accessibility.geojson",
    )
    out = root / "web" / "data" / "routing.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {out} ({out.stat().st_size} bytes, {len(payload['edges'])} edges)")


if __name__ == "__main__":
    main()
