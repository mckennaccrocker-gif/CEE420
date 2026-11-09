"""Channel-relative 3DEP scenario depths on road centerlines.

This is not a Hurricane Ida reconstruction. Water level at a road sample is
the 3DEP elevation at the nearest mapped channel cell plus a configured
stage. The stage is an assumption. Nothing in this module interpolates
between stages or assigns them a clock time.

Bridge decks are not sampled. The ground under an OSM bridge tag is not
the deck elevation, and this module does not invent one.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from shapely.geometry import LineString
from shapely.geometry import MultiLineString
from shapely.geometry.base import BaseGeometry

from geospatial.crs import US_SURVEY_FOOT_M

SCENARIO_PRODUCT = "hypothetical_3dep_channel_relative_bathtub"
STATUS_BRIDGE = "bridge_deck_unmatched"
STATUS_TUNNEL = "tunnel_unmatched"
STATUS_OUTSIDE_TOWN = "outside_municipality"
STATUS_OUTSIDE_CHANNEL = "outside_channel_buffer"
STATUS_NODATA = "dem_nodata"
STATUS_DEPTH = "scenario_depth"


def _missing(value: float | None) -> bool:
    if value is None:
        return True
    return isinstance(value, float) and math.isnan(value)


def select_controlling_channel(
    road_elevation_m: float | None,
    channel_elevation_m: Sequence[float],
    channel_distance_m: Sequence[float],
    *,
    max_channel_distance_m: float,
    max_channel_above_road_m: float,
) -> tuple[float | None, float | None]:
    """Pick the nearest channel cell that can be a water surface for this road.

    A mapped channel cell that sits more than ``max_channel_above_road_m``
    above the road is uphill. It is not used. The nearest remaining cell
    inside the distance cap is the controlling cell. If every cell in the
    cap is uphill, the result is ``(None, None)`` and the caller leaves the
    sample unmatched instead of reporting a deep depth.

    ``(None, distance)`` means a channel is in range but the road elevation
    is nodata. ``(None, None)`` means there is no eligible channel.
    """
    if len(channel_elevation_m) != len(channel_distance_m):
        raise ValueError("Channel elevations and distances must be the same length.")
    if max_channel_above_road_m < 0:
        raise ValueError("The uphill allowance cannot be negative.")
    in_range: list[tuple[float, float]] = []
    for elevation, distance in zip(channel_elevation_m, channel_distance_m, strict=True):
        if _missing(distance) or float(distance) > max_channel_distance_m:
            continue
        if _missing(elevation):
            continue
        in_range.append((float(elevation), float(distance)))
    if not in_range:
        return None, None
    if _missing(road_elevation_m):
        nearest = min(distance for _elevation, distance in in_range)
        return None, nearest
    limit = float(road_elevation_m) + float(max_channel_above_road_m)
    eligible = [(elevation, distance) for elevation, distance in in_range if elevation <= limit]
    if not eligible:
        return None, None
    elevation, distance = min(eligible, key=lambda item: item[1])
    return elevation, distance


def depth_from_elevations(road_elevation_m: float, channel_elevation_m: float, stage_m: float) -> float:
    """Depth of an assumed water surface above the road cell.

    Both elevations are in the same vertical unit (metres, as interpreted
    for the 3DEP clip). The result is never negative: a road above the
    assumed water surface has depth 0. Nodata must be filtered before this
    call. This is not a measured water surface.
    """
    if _missing(road_elevation_m) or _missing(channel_elevation_m):
        raise ValueError("Nodata elevations cannot be turned into a depth of zero.")
    if stage_m < 0:
        raise ValueError(f"Scenario stage must be >= 0 m, got {stage_m}.")
    return max(0.0, float(channel_elevation_m) + float(stage_m) - float(road_elevation_m))


def illustrative_label(depth_max_m: float, thresholds_m: Sequence[float]) -> str:
    """Label a centerline maximum. Not a closure standard.

    ``thresholds_m`` is the configured pair, 0.10 m then 0.30 m unless the
    settings file changes. The words in the label say the cut is preliminary.
    """
    if len(thresholds_m) != 2:
        raise ValueError("Illustrative labels need exactly two depth thresholds.")
    lower, upper = float(thresholds_m[0]), float(thresholds_m[1])
    if not (0 <= lower < upper):
        raise ValueError(f"Thresholds must increase and be non-negative, got {thresholds_m}.")
    if _missing(depth_max_m):
        raise ValueError("A missing depth has no illustrative label.")
    lower_text = f"{lower:.2f}".replace(".", "_")
    upper_text = f"{upper:.2f}".replace(".", "_")
    if depth_max_m < lower:
        return f"below_{lower_text}m_preliminary"
    if depth_max_m < upper:
        return f"between_{lower_text}m_and_{upper_text}m_preliminary"
    return f"at_or_above_{upper_text}m_preliminary"


def stage_slug(stage_m: float) -> str:
    """Stable column suffix, e.g. 2.0 -> ``2_00``."""
    return f"{float(stage_m):.2f}".replace(".", "_")


def threshold_slug(depth_m: float) -> str:
    return f"{float(depth_m):.2f}".replace(".", "_")


def length_weighted_mean(piece_length_m: Sequence[float], depth_m: Sequence[float | None]) -> float | None:
    """Mean depth weighted by piece length. None depths are left out.

    A nodata piece is not a depth of zero. If every piece is missing, the
    mean is None rather than zero.
    """
    if len(piece_length_m) != len(depth_m):
        raise ValueError("Piece lengths and depths must be the same length.")
    total = 0.0
    weighted = 0.0
    for length, depth in zip(piece_length_m, depth_m, strict=True):
        if length < 0:
            raise ValueError("Piece length cannot be negative.")
        if _missing(depth):
            continue
        total += float(length)
        weighted += float(length) * float(depth)
    if total == 0.0:
        return None
    return weighted / total


def equal_piece_midpoints(line: LineString, spacing_crs: float) -> list[tuple[Any, float]]:
    """Midpoints of equal-length pieces, each shorter than ``spacing_crs``.

    The piece length is in the same units as the line (US survey feet for
    EPSG:3424). One short line becomes a single piece. A zero-length line
    contributes nothing.
    """
    if spacing_crs <= 0:
        raise ValueError("Sample spacing must be positive.")
    length = float(line.length)
    if length <= 0 or len(line.coords) < 2:
        return []
    n_pieces = max(1, math.ceil(length / spacing_crs))
    step = length / n_pieces
    return [(line.interpolate((index + 0.5) * step), step) for index in range(n_pieces)]


def line_parts(geometry: BaseGeometry) -> list[LineString]:
    """Extract line parts from a clipped centerline."""
    if geometry is None or geometry.is_empty:
        return []
    if isinstance(geometry, LineString):
        return [geometry]
    if isinstance(geometry, MultiLineString):
        return [part for part in geometry.geoms if isinstance(part, LineString)]
    geoms = getattr(geometry, "geoms", None)
    if geoms is None:
        return []
    parts: list[LineString] = []
    for part in geoms:
        parts.extend(line_parts(part))
    return parts


def sample_elevations(
    values_row_major: Sequence[Sequence[float]],
    transform: Sequence[float],
    nodata: float | None,
    xs: Sequence[float],
    ys: Sequence[float],
) -> list[float | None]:
    """Read elevations at coordinates. Outside the grid and nodata are None.

    ``transform`` is an affine (a, b, c, d, e, f) in rasterio order:
    x = a * col + b * row + c, y = d * col + e * row + f.
    Nodata is never returned as zero. A grid with no nodata flag still
    treats NaN as missing.
    """
    if len(transform) != 6:
        raise ValueError("Expected a 6-parameter affine transform.")
    if len(xs) != len(ys):
        raise ValueError("x and y sample coordinates differ in length.")
    nrows = len(values_row_major)
    ncols = len(values_row_major[0]) if nrows else 0
    a, b, c, d, e, f = (float(term) for term in transform)
    # Invert the affine. A north-up grid has b = d = 0.
    determinant = a * e - b * d
    if determinant == 0:
        raise ValueError("Raster affine is not invertible.")
    samples: list[float | None] = []
    for x_coord, y_coord in zip(xs, ys, strict=True):
        column = (e * (x_coord - c) - b * (y_coord - f)) / determinant
        row = (a * (y_coord - f) - d * (x_coord - c)) / determinant
        col_index = math.floor(column)
        row_index = math.floor(row)
        if row_index < 0 or col_index < 0 or row_index >= nrows or col_index >= ncols:
            samples.append(None)
            continue
        value = float(values_row_major[row_index][col_index])
        if math.isnan(value):
            samples.append(None)
        elif nodata is not None and value == float(nodata):
            samples.append(None)
        else:
            samples.append(value)
    return samples


def _empty_stage_fields(stages_m: Sequence[float], thresholds_m: Sequence[float]) -> dict[str, Any]:
    lower, upper = threshold_slug(thresholds_m[0]), threshold_slug(thresholds_m[1])
    fields: dict[str, Any] = {}
    for stage in stages_m:
        slug = stage_slug(stage)
        fields[f"depth_mean_m_stage_{slug}"] = None
        fields[f"depth_max_m_stage_{slug}"] = None
        fields[f"illustrative_label_stage_{slug}"] = None
        fields[f"length_m_below_{lower}_stage_{slug}"] = None
        fields[f"length_m_between_{lower}_and_{upper}_stage_{slug}"] = None
        fields[f"length_m_at_or_above_{upper}_stage_{slug}"] = None
    return fields


def summarize_pieces(
    *,
    is_bridge: bool,
    is_tunnel: bool,
    piece_length_m: Sequence[float],
    road_elevation_m: Sequence[float | None],
    channel_elevation_m: Sequence[float | None],
    channel_distance_m: Sequence[float | None],
    max_channel_distance_m: float,
    stages_m: Sequence[float],
    thresholds_m: Sequence[float],
) -> dict[str, Any]:
    """Summarize one centerline. Bridges are returned before any depth math.

    Passing elevations for a bridge does not affect the result. Those
    elevations are the terrain under the deck, and they are ignored.
    """
    if max_channel_distance_m <= 0:
        raise ValueError("The channel distance cap must be positive.")
    fields = _empty_stage_fields(stages_m, thresholds_m)
    fields.update(
        {
            "n_pieces": int(len(piece_length_m)),
            "n_valid": 0,
            "n_nodata": 0,
            "n_outside_channel": 0,
            "sampled_length_m": 0.0,
            "depth_product": SCENARIO_PRODUCT,
            "hurricane_ida_depth": False,
            "event_time": None,
        }
    )
    if is_bridge:
        fields["exposure_status"] = STATUS_BRIDGE
        fields["depth_sampled"] = False
        return fields
    if is_tunnel:
        fields["exposure_status"] = STATUS_TUNNEL
        fields["depth_sampled"] = False
        return fields
    count = len(piece_length_m)
    if not (count == len(road_elevation_m) == len(channel_elevation_m) == len(channel_distance_m)):
        raise ValueError("Piece sequences must be the same length.")
    if count == 0:
        fields["exposure_status"] = STATUS_OUTSIDE_TOWN
        fields["depth_sampled"] = False
        return fields

    valid_lengths: list[float] = []
    valid_depths: dict[float, list[float]] = {float(stage): [] for stage in stages_m}
    for length, road_z, channel_z, distance in zip(
        piece_length_m, road_elevation_m, channel_elevation_m, channel_distance_m, strict=True
    ):
        if _missing(distance) or float(distance) > max_channel_distance_m:
            fields["n_outside_channel"] += 1
            continue
        if _missing(road_z) or _missing(channel_z):
            fields["n_nodata"] += 1
            continue
        fields["n_valid"] += 1
        fields["sampled_length_m"] += float(length)
        valid_lengths.append(float(length))
        for stage in valid_depths:
            valid_depths[stage].append(depth_from_elevations(float(road_z), float(channel_z), stage))

    if fields["n_valid"] == 0:
        fields["depth_sampled"] = False
        fields["exposure_status"] = STATUS_NODATA if fields["n_nodata"] else STATUS_OUTSIDE_CHANNEL
        return fields

    lower, upper = float(thresholds_m[0]), float(thresholds_m[1])
    lower_text, upper_text = threshold_slug(lower), threshold_slug(upper)
    fields["depth_sampled"] = True
    fields["exposure_status"] = STATUS_DEPTH
    for stage, depths in valid_depths.items():
        slug = stage_slug(stage)
        fields[f"depth_mean_m_stage_{slug}"] = length_weighted_mean(valid_lengths, depths)
        fields[f"depth_max_m_stage_{slug}"] = max(depths)
        fields[f"illustrative_label_stage_{slug}"] = illustrative_label(max(depths), thresholds_m)
        below = between = above = 0.0
        for length, depth in zip(valid_lengths, depths, strict=True):
            if depth < lower:
                below += length
            elif depth < upper:
                between += length
            else:
                above += length
        fields[f"length_m_below_{lower_text}_stage_{slug}"] = below
        fields[f"length_m_between_{lower_text}_and_{upper_text}_stage_{slug}"] = between
        fields[f"length_m_at_or_above_{upper_text}_stage_{slug}"] = above
    return fields
