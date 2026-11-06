"""Compare a raster bounding box with the Princeton municipal polygon.

This module does not read cell values and does not build a flood surface.
"""

from __future__ import annotations

import geopandas as gpd
from shapely.geometry import box

from geospatial.crs import PROJECTED_EPSG
from geospatial.crs import us_survey_feet_to_m


def raster_extent_against_boundary(
    bounds: tuple[float, float, float, float],
    bounds_crs: str,
    boundary: gpd.GeoDataFrame,
) -> dict[str, float | bool]:
    """Test whether a raster extent meets Princeton, and measure the gap.

    ``bounds`` is (left, bottom, right, top) in ``bounds_crs``. Both the
    raster box and the municipal polygon are projected to EPSG:3424 before
    the predicate, so the distance is a State Plane length converted to
    metres. A geographic bounding box is not compared in degrees.
    """
    left, bottom, right, top = bounds
    if right < left or top < bottom:
        raise ValueError(f"Raster bounds are not ordered west-south-east-north: {bounds}")
    raster = gpd.GeoDataFrame(geometry=[box(left, bottom, right, top)], crs=bounds_crs)
    raster_plan = raster.to_crs(PROJECTED_EPSG)
    municipal = boundary.to_crs(PROJECTED_EPSG)
    polygon = municipal.geometry.iloc[0]
    extent = raster_plan.geometry.iloc[0]
    intersects = bool(extent.intersects(polygon))
    distance_m = us_survey_feet_to_m(float(extent.distance(polygon)))
    return {
        "intersects_princeton": intersects,
        "distance_to_princeton_m": distance_m,
        "distance_to_princeton_km": distance_m / 1000.0,
    }
