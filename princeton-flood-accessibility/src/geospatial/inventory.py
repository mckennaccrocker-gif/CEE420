"""Counts for station files that are not joined to road edges.

AADT and high-water marks stay point observations. Assigning them to a
nearby edge would be a model choice, and stage 1 does not make it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

from geospatial.crs import PROJECTED_EPSG
from geospatial.crs import US_SURVEY_FOOT_M


def _display_path(path: Path) -> str:
    """Prefer a project-relative path so the stats file is not tied to one machine."""
    resolved = path.resolve()
    for parent in [resolved, *resolved.parents]:
        if parent.name == "princeton-flood-accessibility":
            return resolved.relative_to(parent).as_posix()
    return path.as_posix()


def station_inventory(
    path: Path,
    boundary: gpd.GeoDataFrame,
    *,
    lon_column: str,
    lat_column: str,
    label: str,
) -> dict[str, Any]:
    """Count published points inside the municipal polygon.

    Coordinates are read as EPSG:4326 because that is how both source tables
    are published (decimal degrees). The inside test is done after projecting
    points and the boundary to EPSG:3424, so the predicate is planar and uses
    the same CRS as the road network. A 25 m buffer is reported separately
    and is not counted as inside.
    """
    if not path.is_file():
        return {
            "label": label,
            "available": False,
            "path": _display_path(path),
            "joined_to_road_edges": False,
        }
    table = pd.read_csv(path)
    missing = [column for column in (lon_column, lat_column) if column not in table.columns]
    if missing:
        raise ValueError(f"{path} is missing coordinate columns {missing}.")
    coordinates = table.dropna(subset=[lon_column, lat_column]).copy()
    points = gpd.GeoDataFrame(
        coordinates,
        geometry=gpd.points_from_xy(coordinates[lon_column], coordinates[lat_column]),
        crs="EPSG:4326",
    )
    # Inside / distance are evaluated in State Plane feet, then the 25 m
    # tolerance is converted with the US survey foot. It is not a 25 degree buffer.
    projected = points.to_crs(PROJECTED_EPSG)
    polygon = boundary.to_crs(PROJECTED_EPSG).geometry.iloc[0]
    inside = projected.within(polygon)
    distance_m = projected.distance(polygon) * US_SURVEY_FOOT_M
    buffer_ftus = 25.0 / US_SURVEY_FOOT_M
    within_25m = projected.distance(polygon) <= buffer_ftus
    return {
        "label": label,
        "available": True,
        "path": _display_path(path),
        "joined_to_road_edges": False,
        "n_rows": int(len(table)),
        "n_with_coordinates": int(len(coordinates)),
        "n_unique_coordinates": int(coordinates.groupby([lon_column, lat_column]).ngroups),
        "n_missing_coordinates": int(len(table) - len(coordinates)),
        "n_inside_boundary": int(inside.sum()),
        "n_within_25m_of_boundary": int(within_25m.sum()),
        "distance_to_boundary_m_min": float(distance_m.min()) if len(distance_m) else None,
        "coordinate_crs_assumed": "EPSG:4326",
        "predicate_crs": f"EPSG:{PROJECTED_EPSG}",
    }
