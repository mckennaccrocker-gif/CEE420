"""Load settings, check the municipal boundary, download and project the network."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import networkx as nx
import yaml
from pyproj import CRS
from shapely.geometry import LineString
from shapely.geometry import MultiPolygon
from shapely.geometry import Polygon

from geospatial.crs import AREA_CHECK_EPSG
from geospatial.crs import GEOGRAPHIC_EPSG
from geospatial.crs import PROJECTED_EPSG
from geospatial.crs import US_SURVEY_FOOT_M
from geospatial.crs import proj_pipeline
from geospatial.crs import require_crs
from geospatial.crs import us_survey_feet_to_m
from network.tags import collapse_highway
from network.tags import is_bridge_tag
from network.tags import is_positive_layer
from network.tags import is_tunnel_tag
from network.tags import parse_explicit_maxspeed_mph

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def project_root() -> Path:
    return PROJECT_ROOT


def load_settings(path: Path | None = None) -> dict[str, Any]:
    """Read ``config/settings.yaml``. Paths in the file stay relative to the project."""
    settings_path = path or (PROJECT_ROOT / "config" / "settings.yaml")
    if not settings_path.is_file():
        raise FileNotFoundError(f"Settings file not found: {settings_path}")
    with settings_path.open(encoding="utf-8") as handle:
        settings = yaml.safe_load(handle)
    if not isinstance(settings, dict):
        raise ValueError(f"Settings file did not contain a mapping: {settings_path}")
    return settings


def resolve(settings: dict[str, Any], key: str) -> Path:
    """Resolve a path from ``settings['paths']`` against the project root."""
    relative = settings["paths"][key]
    return PROJECT_ROOT / relative


def load_boundary(path: Path) -> gpd.GeoDataFrame:
    """Read the municipal polygon and require a CRS."""
    if not path.is_file():
        raise FileNotFoundError(
            f"Municipal boundary not found at {path}. "
            "The stage-1 snapshot is data/raw/princeton_boundary.geojson."
        )
    boundary = gpd.read_file(path)
    if boundary.crs is None:
        raise ValueError(f"{path} has no CRS. Refusing to guess one.")
    if boundary.empty:
        raise ValueError(f"{path} contains no features.")
    return boundary


def validate_princeton_boundary(boundary: gpd.GeoDataFrame, settings: dict[str, Any]) -> dict[str, float]:
    """Refuse the build if this polygon is not the Princeton, NJ municipality.

    Area is computed in EPSG:26918 (metres), the same check the course uses
    on this snapshot (47.66 km²). The centroid is computed in EPSG:3424 and
    then transformed back to longitude and latitude so the window test is
    not a centroid of degree coordinates.
    """
    if len(boundary) != 1:
        raise ValueError(
            f"Expected one municipal polygon, found {len(boundary)}. "
            "Refusing to download a network for an ambiguous boundary."
        )
    name = str(boundary.iloc[0].get("name", ""))
    if "Princeton" not in name or "Jersey" not in name:
        raise ValueError(
            f"Boundary name is {name!r}, not Princeton, New Jersey. "
            "This check exists because a different Princeton is easy to load by mistake."
        )

    place = settings["place"]
    area_m2 = boundary.to_crs(AREA_CHECK_EPSG).geometry.area.iloc[0]
    area_km2 = float(area_m2) / 1e6
    expected = float(place["expected_area_km2"])
    tolerance = float(place["area_tolerance_km2"])
    if abs(area_km2 - expected) > tolerance:
        raise ValueError(
            f"Boundary area is {area_km2:.2f} km² in EPSG:{AREA_CHECK_EPSG}, "
            f"expected {expected:.2f} ± {tolerance:.2f}. "
            "Refusing to build a road network for the wrong polygon."
        )

    # Project first, then take the centroid, then return to geographic
    # coordinates. A centroid of longitude/latitude is not used.
    centroid_ll = (
        boundary.to_crs(PROJECTED_EPSG).geometry.centroid.to_crs(GEOGRAPHIC_EPSG).iloc[0]
    )
    lon_min, lon_max = place["lon_range"]
    lat_min, lat_max = place["lat_range"]
    if not (lon_min <= centroid_ll.x <= lon_max and lat_min <= centroid_ll.y <= lat_max):
        raise ValueError(
            f"Boundary centroid ({centroid_ll.x:.4f}, {centroid_ll.y:.4f}) "
            "is outside the Princeton, NJ window."
        )

    area_ft2 = float(boundary.to_crs(PROJECTED_EPSG).geometry.area.iloc[0])
    area_km2_state_plane = area_ft2 * (US_SURVEY_FOOT_M ** 2) / 1e6
    return {
        "area_km2_epsg26918": area_km2,
        "area_km2_epsg3424": area_km2_state_plane,
        "centroid_lon": float(centroid_ll.x),
        "centroid_lat": float(centroid_ll.y),
    }


def geographic_polygon(boundary: gpd.GeoDataFrame) -> Polygon | MultiPolygon:
    """Municipal polygon in EPSG:4326 for the Overpass query.

    ``osmnx.graph_from_polygon`` interprets coordinates as longitude and
    latitude. Passing a State Plane polygon would query a nonsense area.
    """
    geographic = boundary.to_crs(GEOGRAPHIC_EPSG)
    require_crs(geographic.crs, GEOGRAPHIC_EPSG, "boundary prepared for Overpass")
    polygon = geographic.geometry.iloc[0]
    if not isinstance(polygon, (Polygon, MultiPolygon)):
        raise TypeError(f"Boundary geometry is {polygon.geom_type}, not a polygon.")
    if not polygon.is_valid:
        raise ValueError("Municipal polygon is invalid. Refusing to query Overpass.")
    minx, miny, maxx, maxy = polygon.bounds
    if not (-180 <= minx <= maxx <= 180 and -90 <= miny <= maxy <= 90):
        raise ValueError(
            f"Boundary bounds {polygon.bounds} are not longitude/latitude degrees."
        )
    return polygon


def configure_osmnx(settings: dict[str, Any]) -> None:
    """Point OSMnx at the project cache and keep bridge, speed, and layer tags."""
    try:
        import osmnx as ox
    except ImportError as exc:
        raise SystemExit(
            "osmnx is not installed, so the drivable network cannot be downloaded. "
            "From princeton-flood-accessibility run: pip install -r requirements.txt"
        ) from exc

    cache = resolve(settings, "osmnx_cache")
    cache.mkdir(parents=True, exist_ok=True)
    ox.settings.use_cache = True
    ox.settings.cache_folder = cache
    ox.settings.log_console = True
    ox.settings.requests_timeout = int(settings["network"]["requests_timeout_s"])
    ox.settings.http_user_agent = (
        "princeton-flood-accessibility/0.1 (CEE420 educational research)"
    )
    tags = list(ox.settings.useful_tags_way)
    for extra in ("layer",):
        if extra not in tags:
            tags.append(extra)
    ox.settings.useful_tags_way = tags


def download_drive_graph(polygon: Polygon | MultiPolygon, settings: dict[str, Any]) -> nx.MultiDiGraph:
    """Download the public drivable OSM network that meets the municipality."""
    import osmnx as ox

    network = settings["network"]
    try:
        graph = ox.graph_from_polygon(
            polygon,
            network_type=network["network_type"],
            simplify=bool(network["simplify"]),
            retain_all=bool(network["retain_all"]),
            truncate_by_edge=bool(network["truncate_by_edge"]),
        )
    except Exception as exc:
        raise RuntimeError(
            "The OpenStreetMap download failed for the Princeton municipal polygon. "
            "The Overpass API may be unavailable or rate-limiting this machine. "
            "Retry scripts/download_roads.py. Cached responses, if any, are under "
            "data/raw/osmnx_cache and are not a finished network. "
            f"Original error: {exc}"
        ) from exc
    if graph.number_of_edges() == 0 or graph.number_of_nodes() == 0:
        raise RuntimeError(
            "OSMnx returned an empty drive network inside the Princeton boundary. "
            "No road file was written."
        )
    return graph


def annotate_edges(graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """Preserve length in metres and mark bridges before the CRS changes.

    OSMnx stores ``length`` as an ellipsoidal metre length on the unprojected
    graph. That value is copied to ``length_m`` so a later planar length in
    feet cannot be mistaken for it.

    ``is_bridge`` records the OSM bridge tag. It does not contain a deck
    elevation. Flood code must not sample the ground under a bridge and
    treat that elevation as the road deck.
    """
    for _u, _v, _key, data in graph.edges(keys=True, data=True):
        if "length" not in data:
            raise ValueError("OSMnx edge is missing length; refusing to invent one.")
        data["length_m"] = float(data["length"])
        data["is_bridge"] = is_bridge_tag(data.get("bridge"))
        data["is_tunnel"] = is_tunnel_tag(data.get("tunnel"))
        data["is_positive_layer"] = is_positive_layer(data.get("layer"))
        data["road_class"] = collapse_highway(data.get("highway"))
        parsed = parse_explicit_maxspeed_mph(data.get("maxspeed"))
        # Keep unknown speeds as missing. Do not impute a free-flow speed.
        data["maxspeed_mph"] = parsed
    return graph


def project_drive_graph(graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """Project node and edge geometry to EPSG:3424 without rewriting ``length_m``.

    OSMnx 2.1 ``project_graph`` reprojects coordinates and leaves the metre
    ``length`` attribute unchanged. Planar feet are added afterwards from the
    projected geometry.
    """
    import osmnx as ox

    projected = ox.project_graph(graph, to_crs=f"EPSG:{PROJECTED_EPSG}")
    projected.graph["crs"] = f"EPSG:{PROJECTED_EPSG}"
    projected.graph["length_attribute_units"] = (
        "length and length_m are ellipsoidal metres from the WGS84 graph. "
        "length_ftus_planar is the EPSG:3424 geometry length in US survey feet. "
        "length_m_planar converts those feet with 1200/3937."
    )
    _add_planar_lengths(projected)
    _reject_unprojected_coordinates(projected)
    return projected


def _add_planar_lengths(graph: nx.MultiDiGraph) -> None:
    """Write planar length from projected edge geometry back onto the graph.

    Straight OSMnx edges sometimes have no geometry attribute. Filling those
    from the projected node coordinates keeps the planar length in feet
    rather than in degrees.
    """
    import osmnx as ox

    edges = ox.graph_to_gdfs(graph, nodes=False, fill_edge_geometry=True)
    require_crs(edges.crs, PROJECTED_EPSG, "projected edges")
    for (u, v, key), row in edges.iterrows():
        length_ftus = float(row.geometry.length)
        graph.edges[u, v, key]["geometry"] = row.geometry
        graph.edges[u, v, key]["length_ftus_planar"] = length_ftus
        graph.edges[u, v, key]["length_m_planar"] = us_survey_feet_to_m(length_ftus)


def _reject_unprojected_coordinates(graph: nx.MultiDiGraph) -> None:
    """EPSG:3424 eastings in Princeton are hundreds of thousands of feet.

    Degree coordinates left over from EPSG:4326 would sit near -74. That
    mistake would make every length wrong by orders of magnitude.
    """
    xs = [float(data["x"]) for _node, data in graph.nodes(data=True)]
    median_x = sorted(xs)[len(xs) // 2]
    if median_x < 1000:
        raise RuntimeError(
            f"Median node easting is {median_x}. Expected EPSG:3424 US survey feet, "
            "not longitude degrees. The projected graph was not saved."
        )


def edges_to_frame(graph: nx.MultiDiGraph, *, centerlines_only: bool) -> gpd.GeoDataFrame:
    """GeoDataFrame of directed edges, or one row per physical centerline."""
    from network.stats import iter_centerlines

    records = iter_centerlines(graph) if centerlines_only else graph.edges(keys=True, data=True)
    rows: list[dict[str, Any]] = []
    for u, v, key, data in records:
        geometry = data.get("geometry")
        if geometry is None:
            geometry = LineString(
                [(graph.nodes[u]["x"], graph.nodes[u]["y"]), (graph.nodes[v]["x"], graph.nodes[v]["y"])]
            )
        row = {name: value for name, value in data.items() if name != "geometry"}
        row["u"] = int(u)
        row["v"] = int(v)
        row["key"] = int(key)
        row["geometry"] = geometry
        rows.append(row)
    frame = gpd.GeoDataFrame(rows, geometry="geometry", crs=f"EPSG:{PROJECTED_EPSG}")
    require_crs(frame.crs, PROJECTED_EPSG, "edge frame")
    return _sanitize_attributes(frame)


def nodes_to_frame(graph: nx.MultiDiGraph) -> gpd.GeoDataFrame:
    import osmnx as ox

    nodes = ox.graph_to_gdfs(graph, edges=False).reset_index(names="osmid")
    require_crs(nodes.crs, PROJECTED_EPSG, "nodes")
    return _sanitize_attributes(nodes)


def _sanitize_attributes(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Turn list-valued OSM tags into strings so GeoPackage and GeoJSON can store them."""
    cleaned = frame.copy()
    for column in list(cleaned.columns):
        if column == cleaned.geometry.name:
            continue
        if cleaned[column].map(lambda value: isinstance(value, (list, tuple, dict))).any():
            cleaned[column] = cleaned[column].map(_stringify_complex)
    return cleaned


def _stringify_complex(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return ";".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return value


def transformation_note() -> str:
    """Record the PROJ pipeline from OSM longitude/latitude to EPSG:3424."""
    try:
        return proj_pipeline(f"EPSG:{GEOGRAPHIC_EPSG}", f"EPSG:{PROJECTED_EPSG}")
    except Exception as exc:  # pragma: no cover - provenance only
        return f"unavailable ({exc})"


def assert_graph_crs(graph: nx.MultiDiGraph) -> None:
    require_crs(CRS.from_user_input(graph.graph.get("crs")), PROJECTED_EPSG, "projected graph")
