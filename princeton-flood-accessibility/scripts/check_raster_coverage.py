"""Record whether local GeoTIFF extents intersect Princeton.

The script reads raster headers and, for documentation, the raw numeric
range of each file. It does not treat those numbers as Princeton flood depths.
Pass the GeoTIFF paths on the command line. This script does not download them.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from datetime import timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from geospatial.coverage import raster_extent_against_boundary  # noqa: E402
from network.roads import load_boundary  # noqa: E402
from network.roads import load_settings  # noqa: E402
from network.roads import resolve  # noqa: E402


def main(argv: list[str] | None = None) -> None:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        raise SystemExit(
            "Usage: python scripts/check_raster_coverage.py RASTER [RASTER ...]\n"
            "No rasters were passed, so no coverage result was written."
        )
    try:
        import rasterio
        from pyproj import Geod
    except ImportError as exc:
        raise SystemExit(
            "rasterio and pyproj are required to read GeoTIFF headers. "
            "pip install -r requirements.txt\n"
            f"Original error: {exc}"
        ) from exc

    settings = load_settings()
    boundary = load_boundary(resolve(settings, "boundary"))
    catalog = {
        item["name"]: item["url"]
        for item in settings["sources"]["ida_pa_depth_grids"]["files"]
    }
    geod = Geod(ellps="WGS84")
    records = []
    for raw_path in arguments:
        path = Path(raw_path)
        if not path.is_file():
            raise SystemExit(f"Raster not found: {path}")
        records.append(_inspect(path, boundary, catalog, rasterio, geod))
    output = resolve(settings, "coverage_json")
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "checked_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "princeton_boundary": "data/raw/princeton_boundary.geojson",
        "these_are_not_princeton_flood_depths": True,
        "rasters_in_repository": False,
        "unit_note": (
            "The GeoTIFF files do not declare vertical units. The USGS FGDC "
            "processing steps for these Pennsylvania products convert high-water-mark "
            "elevations from feet to metres using the international-foot factor 0.3048 "
            "and subtract a DEM. That narrative is not a unit tag in the file. "
            "Negative raw values are present, so the grids are not positive-only depth masks. "
            "None of these extents intersect Princeton, NJ."
        ),
        "metadata_url": settings["sources"]["ida_pa_depth_grids"]["metadata_url"],
        "rasters": records,
    }
    output.write_text(json.dumps(payload, indent=2, default=_json_default) + "\n")
    for record in records:
        print(
            f"{record['file']}: intersects_princeton={record['intersects_princeton']} "
            f"distance_km={record['distance_to_princeton_km']:.1f}"
        )
    print(f"Wrote {output}")


def _inspect(path: Path, boundary, catalog: dict[str, str], rasterio, geod) -> dict:
    with rasterio.open(path) as dataset:
        bounds = dataset.bounds
        crs = dataset.crs
        if crs is None:
            raise SystemExit(f"{path} has no CRS. Coverage was not inferred.")
        left, bottom, right, top = bounds.left, bounds.bottom, bounds.right, bounds.top
        comparison = raster_extent_against_boundary(
            (left, bottom, right, top),
            crs.to_string(),
            boundary,
        )
        values = dataset.read(1, masked=True)
        raw_min = float(values.min()) if values.count() else None
        raw_max = float(values.max()) if values.count() else None
        ground_m = _ground_metres(dataset, geod, left, bottom, right, top)
        return {
            "file": path.name,
            "source_url": catalog.get(path.name),
            "crs": crs.to_string(),
            "width": int(dataset.width),
            "height": int(dataset.height),
            "dtype": dataset.dtypes[0],
            "resolution_x": float(dataset.res[0]),
            "resolution_y": float(dataset.res[1]),
            "resolution_axis": "degrees" if crs.is_geographic else "projected_units",
            "approximate_pixel_width_m": ground_m[0],
            "approximate_pixel_height_m": ground_m[1],
            "bounds": {"left": left, "bottom": bottom, "right": right, "top": top},
            "nodata": None if dataset.nodata is None else float(dataset.nodata),
            "vertical_units_in_geotiff": None,
            "geotiff_tags": dataset.tags(),
            "band_descriptions": list(dataset.descriptions),
            "file_mtime_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "raw_value_min": raw_min,
            "raw_value_max": raw_max,
            "raw_value_meaning": (
                "Uninterpreted cell values from this file only. "
                "Not a Princeton depth and not used by the road network."
            ),
            **comparison,
        }


def _json_default(value):
    if hasattr(value, "item"):
        return value.item()
    return str(value)


def _ground_metres(dataset, geod, left: float, bottom: float, right: float, top: float):
    """Approximate one pixel in metres. Geographic rasters store degrees, not metres."""
    if not dataset.crs.is_geographic:
        return float(dataset.res[0]), float(dataset.res[1])
    center_x = (left + right) / 2
    center_y = (bottom + top) / 2
    _az12, _az21, width_m = geod.inv(center_x, center_y, center_x + dataset.res[0], center_y)
    _az12, _az21, height_m = geod.inv(center_x, center_y, center_x, center_y + dataset.res[1])
    return abs(float(width_m)), abs(float(height_m))


if __name__ == "__main__":
    main()
