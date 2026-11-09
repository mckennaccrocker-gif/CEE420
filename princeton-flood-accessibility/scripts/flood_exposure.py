"""Label a hypothetical 3DEP flood scenario on the Princeton centerlines.

This is not a Hurricane Ida simulation. It does not download or invent an
agency depth grid. If a raw DEM or hydrography file is already present, it
is left unchanged.

Run from princeton-flood-accessibility:

    python3 scripts/flood_exposure.py
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from pyproj import Transformer  # noqa: E402
from shapely import STRtree  # noqa: E402
from shapely import distance as shapely_distance  # noqa: E402
from shapely import get_coordinates  # noqa: E402
from shapely import points as shapely_points  # noqa: E402
from shapely import segmentize  # noqa: E402
from shapely.geometry import LineString  # noqa: E402
from shapely.geometry import MultiLineString  # noqa: E402
from shapely.geometry import shape  # noqa: E402

from geospatial.crs import PROJECTED_EPSG  # noqa: E402
from geospatial.crs import US_SURVEY_FOOT_M  # noqa: E402
from geospatial.crs import require_crs  # noqa: E402
from geospatial.exposure import SCENARIO_PRODUCT  # noqa: E402
from geospatial.exposure import equal_piece_midpoints  # noqa: E402
from geospatial.exposure import line_parts  # noqa: E402
from geospatial.exposure import sample_elevations  # noqa: E402
from geospatial.exposure import select_controlling_channel  # noqa: E402
from geospatial.exposure import stage_slug  # noqa: E402
from geospatial.exposure import summarize_pieces  # noqa: E402
from geospatial.exposure import threshold_slug  # noqa: E402
from geospatial.flood_catalog import NOTES  # noqa: E402
from geospatial.flood_catalog import QUERY_DATE  # noqa: E402
from geospatial.flood_catalog import coverage_against_princeton  # noqa: E402
from geospatial.inventory import station_inventory  # noqa: E402
from network.roads import load_boundary  # noqa: E402
from network.roads import load_settings  # noqa: E402
from network.roads import resolve  # noqa: E402
from visualization.exposure_map import save_exposure_map  # noqa: E402

USER_AGENT = "princeton-flood-accessibility/0.1 (CEE420 educational research)"
DEM_URL = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage"
DEM_SERVICE = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer"
NHD_FLOW = "https://hydro.nationalmap.gov/arcgis/rest/services/nhd/MapServer/6/query"
NHD_WATER = "https://hydro.nationalmap.gov/arcgis/rest/services/nhd/MapServer/12/query"


def main() -> None:
    settings = load_settings()
    scenario = settings["scenario"]
    if scenario.get("not_a_hurricane_ida_simulation") is not True:
        raise SystemExit("Refusing to run: the scenario is not marked as not-an-Ida-simulation.")
    if scenario["product"] != SCENARIO_PRODUCT:
        raise SystemExit(f"Unknown scenario product {scenario['product']}.")
    stages = [float(value) for value in scenario["stage_above_channel_dem_m"]]
    primary = float(scenario["primary_stage_m"])
    if primary not in stages:
        raise SystemExit("primary_stage_m is not one of the configured stages.")
    thresholds = [float(value) for value in settings["thresholds"]["depth_m"]]
    if settings["thresholds"].get("applied_as_labels") is not True:
        raise SystemExit("Illustrative labels are turned off in config. Nothing was written.")

    boundary = load_boundary(resolve(settings, "boundary"))
    dem_path = resolve(settings, "dem")
    dem_provenance_path = resolve(settings, "dem_provenance")
    hydro_path = resolve(settings, "hydrography")
    hydro_provenance_path = resolve(settings, "hydrography_provenance")
    envelope = _buffered_envelope(boundary, float(scenario["channel_buffer_m"]))

    if not dem_path.is_file():
        _download_dem(dem_path, dem_provenance_path, envelope, float(scenario["dem_pixel_m"]))
    elif not dem_provenance_path.is_file():
        raise SystemExit(f"DEM exists at {dem_path} but provenance is missing. Refusing to overwrite the DEM.")
    if not hydro_path.is_file():
        _download_hydrography(hydro_path, hydro_provenance_path, envelope, scenario["hydrography"])
    elif not hydro_provenance_path.is_file():
        raise SystemExit(f"Hydrography exists at {hydro_path} but provenance is missing. Refusing to overwrite it.")

    centerlines = gpd.read_file(resolve(settings, "gpkg"), layer="centerlines")
    require_crs(centerlines.crs, f"EPSG:{PROJECTED_EPSG}", "centerlines")
    exposure, dem_info = build_exposure(
        centerlines,
        boundary,
        dem_path,
        hydro_path,
        stages_m=stages,
        thresholds_m=thresholds,
        max_channel_distance_m=float(scenario["max_channel_distance_m"]),
        sample_spacing_m=float(scenario["sample_spacing_m"]),
        max_channel_above_road_m=float(scenario["max_channel_above_road_m"]),
    )
    stats = _stats(
        exposure,
        settings,
        dem_info,
        stages,
        primary,
        thresholds,
        boundary,
    )
    _write_outputs(exposure, boundary, settings, stats, primary)
    _print_headline(stats, primary)


def build_exposure(
    centerlines: gpd.GeoDataFrame,
    boundary: gpd.GeoDataFrame,
    dem_path: Path,
    hydro_path: Path,
    *,
    stages_m: list[float],
    thresholds_m: list[float],
        max_channel_distance_m: float,
        max_channel_above_road_m: float,
        sample_spacing_m: float,
    ) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    """Sample the scenario. The DEM file is read, not modified."""
    import rasterio

    require_crs(centerlines.crs, f"EPSG:{PROJECTED_EPSG}", "centerlines")
    municipal = boundary.to_crs(centerlines.crs).geometry.iloc[0]
    with rasterio.open(dem_path) as dataset:
        require_crs(dataset.crs, "EPSG:26918", "3DEP clip")
        grid = dataset.read(1)
        transform = tuple(dataset.transform)[:6]
        nodata = None if dataset.nodata is None else float(dataset.nodata)
        dem_info = {
            "path": _relative(dem_path),
            "crs": dataset.crs.to_string(),
            "width": int(dataset.width),
            "height": int(dataset.height),
            "pixel_size_x_m": float(dataset.res[0]),
            "pixel_size_y_m": float(dataset.res[1]),
            "nodata": nodata,
            "dtype": dataset.dtypes[0],
            "bounds": [float(value) for value in dataset.bounds],
            "tags": dataset.tags(),
            "vertical_units_in_geotiff": None,
            "vertical_datum_in_geotiff": None,
        }
    finite = grid[np.isfinite(grid)]
    if nodata is not None:
        finite = finite[finite != nodata]
    if finite.size == 0:
        raise SystemExit("The DEM clip has no finite elevations.")
    median = float(np.median(finite))
    dem_info["elevation_min"] = float(np.min(finite))
    dem_info["elevation_max"] = float(np.max(finite))
    dem_info["elevation_median"] = median
    if not 5.0 <= median <= 200.0:
        raise SystemExit(
            f"DEM median elevation is {median:.2f}. That is outside the metre range "
            "expected for Princeton. Refusing to treat the grid as metres."
        )
    dem_info["vertical_unit_interpretation"] = "metre"
    dem_info["vertical_datum_interpretation"] = "NAVD88"
    dem_info["vertical_interpretation_note"] = (
        "The GeoTIFF tags do not state a vertical unit or datum. "
        "USGS 3DEP bare-earth elevations for the conterminous United States are metres "
        "relative to NAVD88. The numeric range of this clip matches metres, not feet. "
        "The interpretation is that program convention plus the range check, not a tag in the file."
    )

    channels = _channel_points(hydro_path, grid, transform, nodata, sample_spacing_m)
    tree = STRtree(channels["geometry"])
    to_dem = Transformer.from_crs(centerlines.crs, "EPSG:26918", always_xy=True)
    spacing_ft = sample_spacing_m / US_SURVEY_FOOT_M

    rows: list[dict[str, Any]] = []
    point_rows: list[int] = []
    point_x: list[float] = []
    point_y: list[float] = []
    point_length: list[float] = []
    for index, centerline in centerlines.iterrows():
        record = _identity(centerline)
        is_bridge = _truthy(centerline.get("is_bridge"))
        is_tunnel = _truthy(centerline.get("is_tunnel"))
        record["is_bridge"] = is_bridge
        record["is_tunnel"] = is_tunnel
        record["is_positive_layer"] = _truthy(centerline.get("is_positive_layer"))
        if is_bridge or is_tunnel:
            summary = summarize_pieces(
                is_bridge=is_bridge,
                is_tunnel=is_tunnel,
                piece_length_m=[],
                road_elevation_m=[],
                channel_elevation_m=[],
                channel_distance_m=[],
                max_channel_distance_m=max_channel_distance_m,
                stages_m=stages_m,
                thresholds_m=thresholds_m,
            )
            record.update(summary)
            record["geometry"] = centerline.geometry
            rows.append(record)
            continue
        clipped = centerline.geometry.intersection(municipal)
        pieces = []
        for part in line_parts(clipped):
            pieces.extend(equal_piece_midpoints(part, spacing_ft))
        record["_n_local"] = len(pieces)
        record["geometry"] = centerline.geometry
        row_position = len(rows)
        rows.append(record)
        for point, step_ft in pieces:
            x_dem, y_dem = to_dem.transform(point.x, point.y)
            point_rows.append(row_position)
            point_x.append(x_dem)
            point_y.append(y_dem)
            point_length.append(step_ft * US_SURVEY_FOOT_M)

    if point_x:
        road_z = sample_elevations(grid, transform, nodata, point_x, point_y)
        road_points = shapely_points(np.column_stack([point_x, point_y]))
        channel_z, distances = _controlling_channels(
            road_points,
            road_z,
            channels,
            tree,
            max_channel_distance_m=max_channel_distance_m,
            max_channel_above_road_m=max_channel_above_road_m,
        )
    else:
        road_z, distances, channel_z = [], [], []

    grouped: dict[int, list[int]] = {position: [] for position in range(len(rows))}
    for sample_index, row_position in enumerate(point_rows):
        grouped[row_position].append(sample_index)

    for position, record in enumerate(rows):
        if "exposure_status" in record:
            continue
        chosen = grouped[position]
        summary = summarize_pieces(
            is_bridge=False,
            is_tunnel=False,
            piece_length_m=[point_length[item] for item in chosen],
            road_elevation_m=[road_z[item] for item in chosen],
            channel_elevation_m=[_as_float(channel_z[item]) for item in chosen],
            channel_distance_m=[_as_float(distances[item]) for item in chosen],
            max_channel_distance_m=max_channel_distance_m,
            stages_m=stages_m,
            thresholds_m=thresholds_m,
        )
        record.update(summary)
        record.pop("_n_local", None)

    frame = gpd.GeoDataFrame(rows, geometry="geometry", crs=centerlines.crs)
    frame["hurricane_ida_depth"] = False
    frame["event_time"] = None
    frame["depth_product"] = SCENARIO_PRODUCT
    return frame, dem_info


def _controlling_channels(
    road_points,
    road_elevation_m: list[float | None],
    channels: dict[str, Any],
    tree: STRtree,
    *,
    max_channel_distance_m: float,
    max_channel_above_road_m: float,
) -> tuple[list[float | None], list[float | None]]:
    """Nearest in-range channel cell that is not uphill of each road sample."""
    n_samples = len(road_elevation_m)
    chosen_z: list[float | None] = [None] * n_samples
    chosen_distance: list[float | None] = [None] * n_samples
    if n_samples == 0:
        return chosen_z, chosen_distance
    pairs = tree.query(road_points, predicate="dwithin", distance=max_channel_distance_m)
    if pairs.size == 0:
        return chosen_z, chosen_distance
    road_index = pairs[0]
    channel_index = pairs[1]
    pair_distance = np.asarray(
        shapely_distance(road_points[road_index], channels["geometry"][channel_index]),
        dtype=float,
    )
    grouped: dict[int, list[tuple[float, float]]] = {}
    elevations = channels["elevation_m"]
    for sample_index, channel_i, distance in zip(road_index, channel_index, pair_distance, strict=True):
        grouped.setdefault(int(sample_index), []).append((float(elevations[int(channel_i)]), float(distance)))
    for sample_index, candidates in grouped.items():
        channel_z, distance = select_controlling_channel(
            road_elevation_m[sample_index],
            [item[0] for item in candidates],
            [item[1] for item in candidates],
            max_channel_distance_m=max_channel_distance_m,
            max_channel_above_road_m=max_channel_above_road_m,
        )
        chosen_z[sample_index] = channel_z
        chosen_distance[sample_index] = distance
    return chosen_z, chosen_distance


def _channel_points(
    hydro_path: Path,
    grid: np.ndarray,
    transform: tuple[float, ...],
    nodata: float | None,
    spacing_m: float,
) -> dict[str, Any]:
    hydro = gpd.read_file(hydro_path)
    require_crs(hydro.crs, "EPSG:4326", "NHD hydrography")
    projected = hydro.to_crs("EPSG:26918")
    coordinates: list[tuple[float, float]] = []
    for geometry in projected.geometry:
        if geometry is None or geometry.is_empty:
            continue
        dense = segmentize(geometry, spacing_m)
        for x_coord, y_coord in get_coordinates(dense):
            coordinates.append((float(x_coord), float(y_coord)))
    if not coordinates:
        raise SystemExit("NHD hydrography produced no channel coordinates.")
    xs, ys = zip(*coordinates, strict=True)
    elevations = sample_elevations(grid, transform, nodata, xs, ys)
    kept_x: list[float] = []
    kept_y: list[float] = []
    kept_z: list[float] = []
    for x_coord, y_coord, elevation in zip(xs, ys, elevations, strict=True):
        if elevation is None:
            continue
        kept_x.append(x_coord)
        kept_y.append(y_coord)
        kept_z.append(elevation)
    if not kept_z:
        raise SystemExit("Every channel sample was DEM nodata. No scenario depth was written.")
    return {
        "geometry": shapely_points(np.column_stack([kept_x, kept_y])),
        "elevation_m": np.asarray(kept_z, dtype=float),
        "n_vertices": len(coordinates),
        "n_with_elevation": len(kept_z),
    }


def _identity(centerline: pd.Series) -> dict[str, Any]:
    osmid = centerline.get("osmid")
    osmid_text = str(int(osmid)) if _is_number(osmid) and float(osmid).is_integer() else str(osmid)
    return {
        "centerline_id": f"{int(centerline['u'])}_{int(centerline['v'])}_{int(centerline['key'])}_{osmid_text}",
        "osmid": osmid_text,
        "name": None if _missing_attr(centerline.get("name")) else str(centerline.get("name")),
        "road_class": None if _missing_attr(centerline.get("road_class")) else str(centerline.get("road_class")),
        "length_m": float(centerline["length_m"]),
        "length_m_inside": float(centerline["length_m_inside"]),
        "length_m_planar": float(centerline["length_m_planar"]),
    }


def _stats(
    exposure: gpd.GeoDataFrame,
    settings: dict[str, Any],
    dem_info: dict[str, Any],
    stages: list[float],
    primary: float,
    thresholds: list[float],
    boundary: gpd.GeoDataFrame,
) -> dict[str, Any]:
    scenario = settings["scenario"]
    hydro_provenance = json.loads(resolve(settings, "hydrography_provenance").read_text())
    dem_provenance = json.loads(resolve(settings, "dem_provenance").read_text())
    lower, upper = threshold_slug(thresholds[0]), threshold_slug(thresholds[1])
    by_status = {}
    for status, group in exposure.groupby("exposure_status"):
        by_status[str(status)] = {
            "n_centerlines": int(len(group)),
            "length_m_inside": float(group["length_m_inside"].sum()),
        }
    stage_stats = {}
    for stage in stages:
        slug = stage_slug(stage)
        sampled = exposure[exposure["depth_sampled"] == True]  # noqa: E712
        mean_column = f"depth_mean_m_stage_{slug}"
        max_column = f"depth_max_m_stage_{slug}"
        above_column = f"length_m_at_or_above_{upper}_stage_{slug}"
        between_column = f"length_m_between_{lower}_and_{upper}_stage_{slug}"
        below_column = f"length_m_below_{lower}_stage_{slug}"
        weights = sampled["sampled_length_m"].astype(float)
        weighted_mean = None
        if not sampled.empty and float(weights.sum()) > 0:
            weighted_mean = float(np.average(sampled[mean_column].astype(float), weights=weights))
        label_column = f"illustrative_label_stage_{slug}"
        by_label = {}
        for label, group in sampled.groupby(label_column):
            by_label[str(label)] = {
                "n_centerlines": int(len(group)),
                "length_m_inside": float(group["length_m_inside"].sum()),
            }
        stage_stats[f"{stage:.2f}"] = {
            "stage_above_channel_dem_m": stage,
            "n_centerlines_with_depth": int(len(sampled)),
            "sampled_length_m": float(sampled["sampled_length_m"].sum()) if len(sampled) else 0.0,
            "length_weighted_mean_depth_m": weighted_mean,
            "max_of_centerline_max_depth_m": float(sampled[max_column].max()) if len(sampled) else None,
            "piece_length_m_below_lower_threshold": float(sampled[below_column].sum()) if len(sampled) else 0.0,
            "piece_length_m_between_thresholds": float(sampled[between_column].sum()) if len(sampled) else 0.0,
            "piece_length_m_at_or_above_upper_threshold": float(sampled[above_column].sum()) if len(sampled) else 0.0,
            "centerlines_by_max_label": by_label,
            "label_uses": "maximum sampled depth on the centerline",
            "not_a_clock_time": True,
        }
    hwm = station_inventory(
        resolve(settings, "hwm_csv"),
        boundary,
        lon_column="longitude_dd",
        lat_column="latitude_dd",
        label="USGS NJ Ida high-water marks",
    )
    hwm["used_as_depth_surface"] = False
    hwm["note"] = (
        "Regional check only. Elevations were not interpolated onto roads "
        "and were not used as the scenario water surface."
    )
    search = {
        "query_date": QUERY_DATE,
        "extent_test": "raster_extent_against_boundary in EPSG:3424, the same test as the Pennsylvania Ida grids",
        "suitable_depth_raster_intersects_princeton": False,
        "fallback": SCENARIO_PRODUCT,
        "candidates": coverage_against_princeton(boundary),
        "notes": NOTES,
        "pennsylvania_ida_grids": "data/processed/ida_raster_coverage_check.json",
    }
    if any(item["intersects_princeton"] for item in search["candidates"]):
        raise SystemExit("A catalogued flood extent intersects Princeton. Refusing to overwrite it with a bathtub.")
    return {
        "product": SCENARIO_PRODUCT,
        "hurricane_ida_simulation": False,
        "observed_flood_depths_used": False,
        "event_time": None,
        "interpolated": False,
        "enso_scales_depths": False,
        "time_note": (
            "Each configured rise is a separate channel-relative computation. "
            "The rises were not interpolated, they are not hours, they are not a forecast, "
            "and they are not the time of Hurricane Ida."
        ),
        "computed_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "assumptions": {
            "stage_above_channel_dem_m": stages,
            "primary_stage_m": primary,
            "max_channel_distance_m": scenario["max_channel_distance_m"],
            "sample_spacing_m": scenario["sample_spacing_m"],
            "channel_buffer_m": scenario["channel_buffer_m"],
            "formula": "depth = max(0, elevation_at_controlling_channel_cell_m + stage_m - elevation_at_road_cell_m)",
            "max_channel_above_road_m": scenario["max_channel_above_road_m"],
            "formula_limits": (
                "The controlling channel cell is the nearest National Hydrography Dataset "
                "vertex within max_channel_distance_m whose DEM elevation is at most "
                "max_channel_above_road_m above the road cell. A higher vertex is uphill "
                "and is not used as a water surface. If every vertex in the cap is uphill, "
                "the sample is unmatched rather than given the vertical gap as a depth. "
                "A sample with no vertex in the cap is not coded as depth zero. "
                "Nodata samples are dropped, not coded as zero. "
                "The channel elevation is the DEM at a hydrography vertex, which is bare earth "
                "or a hydroflattened water surface depending on the 3DEP source, not a measured stage."
            ),
        },
        "thresholds": {
            "depth_m": thresholds,
            "status": settings["thresholds"]["status"],
            "applied_as_labels": True,
            "not_closure_standards": True,
            "network_disruption_analysis": False,
            "label_uses": "maximum sampled depth on the centerline",
        },
        "n_centerlines": int(len(exposure)),
        "by_status": by_status,
        "stages": stage_stats,
        "bridges_not_sampled": by_status.get("bridge_deck_unmatched", {"n_centerlines": 0, "length_m_inside": 0.0}),
        "dem": dem_info,
        "dem_provenance": dem_provenance,
        "hydrography_provenance": hydro_provenance,
        "high_water_marks": hwm,
        "search": search,
    }


def _write_outputs(
    exposure: gpd.GeoDataFrame,
    boundary: gpd.GeoDataFrame,
    settings: dict[str, Any],
    stats: dict[str, Any],
    primary: float,
) -> None:
    gpkg_path = resolve(settings, "exposure_gpkg")
    geojson_path = resolve(settings, "exposure_geojson")
    csv_path = resolve(settings, "exposure_csv")
    summary_path = resolve(settings, "exposure_summary_csv")
    stats_path = resolve(settings, "exposure_stats")
    search_path = resolve(settings, "flood_search_json")
    map_path = resolve(settings, "exposure_map")
    for path in (gpkg_path, geojson_path, csv_path, summary_path, stats_path, search_path, map_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    if gpkg_path.exists():
        gpkg_path.unlink()
    exposure.to_file(gpkg_path, layer="centerline_exposure", driver="GPKG")
    boundary.to_crs(exposure.crs).to_file(gpkg_path, layer="boundary", driver="GPKG", mode="a")
    geographic = exposure.to_crs("EPSG:4326")
    geographic.to_file(geojson_path, driver="GeoJSON")
    table = pd.DataFrame(exposure.drop(columns="geometry"))
    table.to_csv(csv_path, index=False)
    _summary_table(stats).to_csv(summary_path, index=False)
    search_path.write_text(json.dumps(stats["search"], indent=2) + "\n")
    stats_to_save = dict(stats)
    stats_to_save["search"] = _relative(search_path)
    stats_path.write_text(json.dumps(stats_to_save, indent=2) + "\n")
    label_column = f"illustrative_label_stage_{stage_slug(primary)}"
    save_exposure_map(
        boundary,
        exposure,
        primary_stage_m=primary,
        label_column=label_column,
        path=map_path,
    )
    print(f"Wrote {gpkg_path}")
    print(f"Wrote {geojson_path}")
    print(f"Wrote {csv_path}")
    print(f"Wrote {summary_path}")
    print(f"Wrote {stats_path}")
    print(f"Wrote {search_path}")
    print(f"Wrote {map_path}")


def _summary_table(stats: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for stage_key, stage in stats["stages"].items():
        rows.append(
            {
                "product": stats["product"],
                "hurricane_ida_simulation": False,
                "event_time": None,
                "stage_above_channel_dem_m": stage["stage_above_channel_dem_m"],
                "length_weighted_mean_depth_m": stage["length_weighted_mean_depth_m"],
                "max_depth_m": stage["max_of_centerline_max_depth_m"],
                "piece_length_m_below_0_10": stage["piece_length_m_below_lower_threshold"],
                "piece_length_m_0_10_to_0_30": stage["piece_length_m_between_thresholds"],
                "piece_length_m_at_or_above_0_30": stage["piece_length_m_at_or_above_upper_threshold"],
                "n_centerlines_with_depth": stage["n_centerlines_with_depth"],
                "bridge_centerlines_unmatched": stats["bridges_not_sampled"]["n_centerlines"],
                "bridge_length_m_inside_unmatched": stats["bridges_not_sampled"]["length_m_inside"],
                "thresholds_are_closure_standards": False,
            }
        )
    return pd.DataFrame(rows)


def _print_headline(stats: dict[str, Any], primary: float) -> None:
    key = f"{primary:.2f}"
    stage = stats["stages"][key]
    bridges = stats["bridges_not_sampled"]
    print("Scenario, not Hurricane Ida.")
    print(
        f"Primary assumption +{primary:.1f} m above the channel DEM: "
        f"length-weighted mean depth {stage['length_weighted_mean_depth_m']:.3f} m, "
        f"max {stage['max_of_centerline_max_depth_m']:.3f} m."
    )
    print(
        "Piece length at or above 0.30 m (preliminary label, not a closure): "
        f"{stage['piece_length_m_at_or_above_upper_threshold']:.1f} m."
    )
    print(
        f"Bridge decks unmatched: {bridges['n_centerlines']} centerlines, "
        f"{bridges['length_m_inside']:.1f} m inside the municipality."
    )


def _download_dem(
    path: Path,
    provenance_path: Path,
    envelope: tuple[float, float, float, float],
    pixel_m: float,
) -> None:
    import rasterio
    from pyproj import Transformer

    minx, miny, maxx, maxy = envelope
    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:26918", always_xy=True)
    corners = [to_utm.transform(x_coord, y_coord) for x_coord, y_coord in (
        (minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy)
    )]
    width_m = max(x for x, _y in corners) - min(x for x, _y in corners)
    height_m = max(y for _x, y in corners) - min(y for _x, y in corners)
    width = int(math.ceil(width_m / pixel_m))
    height = int(math.ceil(height_m / pixel_m))
    if width > 4000 or height > 4000:
        raise SystemExit(f"Requested DEM is {width} by {height} pixels, above the export limit.")
    params = {
        "bbox": f"{minx},{miny},{maxx},{maxy}",
        "bboxSR": "4326",
        "imageSR": "26918",
        "size": f"{width},{height}",
        "format": "tiff",
        "pixelType": "F32",
        "interpolation": "RSP_NearestNeighbor",
        "f": "image",
    }
    url = DEM_URL + "?" + urllib.parse.urlencode(params)
    temporary = path.with_suffix(".tif.partial")
    path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=180) as response:
        payload = response.read()
        content_type = response.headers.get("Content-Type", "")
    if payload[:1] in (b"{", b"<") or "tiff" not in content_type.lower():
        raise SystemExit(f"3DEP export did not return a GeoTIFF ({content_type}). The DEM was not written.")
    temporary.write_bytes(payload)
    with rasterio.open(temporary) as dataset:
        require_crs(dataset.crs, "EPSG:26918", "downloaded 3DEP clip")
        if dataset.width < 10 or dataset.height < 10:
            temporary.unlink(missing_ok=True)
            raise SystemExit("Downloaded DEM is too small to be the municipal clip.")
    temporary.replace(path)
    provenance = {
        "source": DEM_SERVICE,
        "export_url_pattern": DEM_URL,
        "request": params,
        "retrieved_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
        "interpolation": "RSP_NearestNeighbor",
        "requested_pixel_m": pixel_m,
        "note": (
            "Resampled export from the USGS 3DEP ImageServer, which serves a multi-resolution "
            "bare-earth mosaic at about 1 m in Web Mercator. This file is the requested 10 m "
            "nearest-neighbor sample, not the native lidar cloud and not a flood-depth grid. "
            "Do not replace this file in place; write a new name if a later clip is needed."
        ),
        "not_a_flood_depth": True,
    }
    provenance_path.write_text(json.dumps(provenance, indent=2) + "\n")
    print(f"Downloaded {path}")


def _download_hydrography(
    path: Path,
    provenance_path: Path,
    envelope: tuple[float, float, float, float],
    hydro_settings: dict[str, Any],
) -> None:
    minx, miny, maxx, maxy = envelope
    geometry = {
        "xmin": minx,
        "ymin": miny,
        "xmax": maxx,
        "ymax": maxy,
        "spatialReference": {"wkid": 4326},
    }
    flow_types = ", ".join(str(int(value)) for value in hydro_settings["flowline_ftypes"])
    canal_names = hydro_settings["named_canals"]
    canal_clause = " OR ".join(f"gnis_name = '{name.replace(chr(39), chr(39)+chr(39))}'" for name in canal_names)
    flow_where = f"ftype IN ({flow_types})"
    if canal_clause:
        flow_where = f"{flow_where} OR (ftype = 336 AND ({canal_clause}))"
    water_names = hydro_settings["waterbodies"]
    water_where = " OR ".join(f"GNIS_NAME = '{name.replace(chr(39), chr(39)+chr(39))}'" for name in water_names)
    flow_features = _query_nhd(NHD_FLOW, geometry, flow_where, ["ftype", "fcode", "gnis_name", "permanent_identifier"])
    water_features = _query_nhd(NHD_WATER, geometry, water_where, ["FTYPE", "FCODE", "GNIS_NAME", "PERMANENT_IDENTIFIER"])
    records = []
    for feature in flow_features:
        geometry_value = _esri_geometry(feature["geometry"])
        if geometry_value is None:
            continue
        attributes = feature["attributes"]
        records.append(
            {
                "permanent_identifier": attributes.get("permanent_identifier"),
                "ftype": attributes.get("ftype"),
                "fcode": attributes.get("fcode"),
                "gnis_name": attributes.get("gnis_name"),
                "nhd_layer": "flowline",
                "geometry": geometry_value,
            }
        )
    for feature in water_features:
        geometry_value = _esri_geometry(feature["geometry"])
        if geometry_value is None:
            continue
        attributes = feature["attributes"]
        records.append(
            {
                "permanent_identifier": attributes.get("PERMANENT_IDENTIFIER"),
                "ftype": attributes.get("FTYPE"),
                "fcode": attributes.get("FCODE"),
                "gnis_name": attributes.get("GNIS_NAME"),
                "nhd_layer": "waterbody",
                "geometry": geometry_value,
            }
        )
    if not records:
        raise SystemExit("NHD query returned no channel features. No scenario was written.")
    frame = gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:4326")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".geojson.partial")
    frame.to_file(temporary, driver="GeoJSON")
    temporary.replace(path)
    provenance = {
        "source_flowline": NHD_FLOW,
        "source_waterbody": NHD_WATER,
        "retrieved_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bbox_epsg4326": [minx, miny, maxx, maxy],
        "flowline_where": flow_where,
        "waterbody_where": water_where,
        "n_features": int(len(frame)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "note": (
            "National Hydrography Dataset flowlines (StreamRiver 460 and Artificial Path 558) "
            "plus named CanalDitch features and named waterbodies from config. "
            "Connectors, pipelines, and unnamed ditches are not included. "
            "This file is the channel reference for the scenario. It is not a flood extent."
        ),
    }
    provenance_path.write_text(json.dumps(provenance, indent=2) + "\n")
    print(f"Downloaded {path} ({len(frame)} features)")


def _query_nhd(url: str, geometry: dict[str, Any], where: str, fields: list[str]) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    offset = 0
    while True:
        body = urllib.parse.urlencode(
            {
                "geometry": json.dumps(geometry),
                "geometryType": "esriGeometryEnvelope",
                "inSR": "4326",
                "outSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
                "where": where,
                "outFields": ",".join(fields),
                "returnGeometry": "true",
                "resultOffset": str(offset),
                "resultRecordCount": "2000",
                "f": "json",
            }
        ).encode()
        request = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = json.load(response)
        if payload.get("error"):
            raise SystemExit(f"NHD query failed: {payload['error']}")
        page = payload.get("features", [])
        features.extend(page)
        if not payload.get("exceededTransferLimit"):
            break
        offset += len(page)
        if not page:
            break
    return features


def _esri_geometry(geometry: dict[str, Any]):
    if not geometry:
        return None
    if "paths" in geometry:
        lines = [LineString(path) for path in geometry["paths"] if len(path) >= 2]
        if not lines:
            return None
        if len(lines) == 1:
            return lines[0]
        return MultiLineString(lines)
    if "rings" in geometry:
        return shape({"type": "Polygon", "coordinates": geometry["rings"]})
    return None


def _buffered_envelope(boundary: gpd.GeoDataFrame, buffer_m: float) -> tuple[float, float, float, float]:
    buffered = boundary.to_crs(PROJECTED_EPSG).buffer(buffer_m / US_SURVEY_FOOT_M)
    bounds = gpd.GeoSeries(buffered, crs=f"EPSG:{PROJECTED_EPSG}").to_crs("EPSG:4326").total_bounds
    return float(bounds[0]), float(bounds[1]), float(bounds[2]), float(bounds[3])


def _as_float(value: float | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _truthy(value: object) -> bool:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "t"}
    return bool(value)


def _missing_attr(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return False


def _is_number(value: object) -> bool:
    try:
        float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return True


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    main()
