"""Flood products that were tested against the Princeton municipal polygon.

Bounds were read from the services on 2026-11-02. Distances are not stored
here; ``coverage_against_princeton`` recomputes them with the same extent
test used for the Pennsylvania Ida grids. None of these products is a
Princeton depth surface.
"""

from __future__ import annotations

from typing import Any

import geopandas as gpd

from geospatial.coverage import raster_extent_against_boundary


# Queried from the services on this date. Not a flood time.
QUERY_DATE = "2026-11-02"

# (left, bottom, right, top) in the named CRS.
CANDIDATES: list[dict[str, Any]] = [
    {
        "id": "usgs_fim_01463500_delaware_trenton",
        "title": "USGS Flood Inundation Mapper library, Delaware River at Trenton NJ (01463500, AHPS tren4)",
        "product_type": "flood_extent_polygons",
        "is_depth_raster": False,
        "is_hurricane_ida": False,
        "time": None,
        "time_note": "Stage library, not an event time. HAS_GRIDS was 0 in the site catalog. Extent below is the bounding box of floodExtents polygons for this site.",
        "crs": "EPSG:4326",
        "resolution": None,
        "vertical_datum": None,
        "units": None,
        "nodata": None,
        "bounds": [-74.8603638492707, 40.20725524298179, -74.75953172795923, 40.27086772314373],
        "bounds_crs": "EPSG:4326",
        "source": "https://gis1.wim.usgs.gov/server/rest/services/FIMMapper/floodExtents/MapServer/0",
    },
    {
        "id": "usgs_fim_01389534_peckman_verona",
        "title": "USGS FIM library, Peckman River at Verona NJ (01389534)",
        "product_type": "flood_extent_polygons",
        "is_depth_raster": False,
        "is_hurricane_ida": False,
        "time": None,
        "time_note": "Stage library. Not an Ida reconstruction.",
        "crs": "EPSG:4326",
        "resolution": None,
        "vertical_datum": None,
        "units": None,
        "nodata": None,
        "bounds": [-74.24532394105603, 40.82977155099414, -74.20202041023992, 40.89365103036977],
        "bounds_crs": "EPSG:4326",
        "source": "https://gis1.wim.usgs.gov/server/rest/services/FIMMapper/floodExtents/MapServer/0",
    },
    {
        "id": "usgs_fim_01391500_saddle_lodi",
        "title": "USGS FIM library, Saddle River at Lodi NJ (01391500)",
        "product_type": "flood_extent_polygons",
        "is_depth_raster": False,
        "is_hurricane_ida": False,
        "time": None,
        "time_note": "Stage library.",
        "crs": "EPSG:4326",
        "resolution": None,
        "vertical_datum": None,
        "units": None,
        "nodata": None,
        "bounds": [-74.09675370073116, 40.867069493382694, -74.07660483925132, 40.89870823341452],
        "bounds_crs": "EPSG:4326",
        "source": "https://gis1.wim.usgs.gov/server/rest/services/FIMMapper/floodExtents/MapServer/0",
    },
    {
        "id": "usgs_fim_01390500_saddle_ridgewood",
        "title": "USGS FIM library, Saddle River at Ridgewood NJ (01390500)",
        "product_type": "flood_extent_polygons",
        "is_depth_raster": False,
        "is_hurricane_ida": False,
        "time": None,
        "time_note": "Stage library.",
        "crs": "EPSG:4326",
        "resolution": None,
        "vertical_datum": None,
        "units": None,
        "nodata": None,
        "bounds": [-74.1022520747862, 40.95095216597516, -74.08791049103817, 41.00164531931512],
        "bounds_crs": "EPSG:4326",
        "source": "https://gis1.wim.usgs.gov/server/rest/services/FIMMapper/floodExtents/MapServer/0",
    },
    {
        "id": "usgs_fim_01391000_hohokus",
        "title": "USGS FIM library, Hohokus Brook at Ho-Ho-Kus NJ (01391000)",
        "product_type": "flood_extent_polygons",
        "is_depth_raster": False,
        "is_hurricane_ida": False,
        "time": None,
        "time_note": "Stage library.",
        "crs": "EPSG:4326",
        "resolution": None,
        "vertical_datum": None,
        "units": None,
        "nodata": None,
        "bounds": [-74.13027548899488, 40.96707572665479, -74.10493984040448, 41.01516421727112],
        "bounds_crs": "EPSG:4326",
        "source": "https://gis1.wim.usgs.gov/server/rest/services/FIMMapper/floodExtents/MapServer/0",
    },
    {
        "id": "usgs_fim_01390450_saddle_upper",
        "title": "USGS FIM library, Saddle River at Upper Saddle River NJ (01390450)",
        "product_type": "flood_extent_polygons",
        "is_depth_raster": False,
        "is_hurricane_ida": False,
        "time": None,
        "time_note": "Stage library. HAS_GRIDS was 0. Extent is still published as floodExtents polygons.",
        "crs": "EPSG:4326",
        "resolution": None,
        "vertical_datum": None,
        "units": None,
        "nodata": None,
        "bounds": [-74.1022515861027, 41.02893450664402, -74.08164306118354, 41.07772551546568],
        "bounds_crs": "EPSG:4326",
        "source": "https://gis1.wim.usgs.gov/server/rest/services/FIMMapper/floodExtents/MapServer/0",
    },
    {
        "id": "usgs_fim_01411390_cape_may",
        "title": "USGS FIM library, Cape May Harbor NJ (01411390)",
        "product_type": "flood_extent_polygons",
        "is_depth_raster": False,
        "is_hurricane_ida": False,
        "time": None,
        "time_note": "Coastal stage library. Not the Millstone or Stony Brook.",
        "crs": "EPSG:4326",
        "resolution": None,
        "vertical_datum": None,
        "units": None,
        "nodata": None,
        "bounds": [-74.97270134839944, 38.9273532793008, -74.80223381692969, 39.047189144651654],
        "bounds_crs": "EPSG:4326",
        "source": "https://gis1.wim.usgs.gov/server/rest/services/FIMMapper/floodExtents/MapServer/0",
    },
    {
        "id": "noaa_catfim_bkwn4_major_extent",
        "title": "NOAA stage-based CatFIM major-flood extent, Millstone River at Blackwells Mills NJ (AHPS bkwn4, USGS 01402000)",
        "product_type": "flood_extent_polygons",
        "is_depth_raster": False,
        "is_hurricane_ida": False,
        "time": None,
        "time_note": "NWS flood-category library (major), not a dated Hurricane Ida surface. The geometry is a polygon library; the box below is that library's extent.",
        "crs": "EPSG:4326",
        "resolution": None,
        "vertical_datum": "NGVD29 gage datum on the AHPS site record, not a raster datum",
        "units": "gage stage on the library, not a depth grid",
        "nodata": None,
        "bounds": [-74.67070681572206, 40.41109670500371, -74.54564455123635, 40.54044221233757],
        "bounds_crs": "EPSG:4326",
        "source": "https://maps.water.noaa.gov/server/rest/services/fim_libs/static_stage_based_catfim/MapServer/12",
    },
    {
        "id": "noaa_catfim_bkwn4_record_extent",
        "title": "NOAA stage-based CatFIM record-flood extent, Millstone River at Blackwells Mills NJ (bkwn4)",
        "product_type": "flood_extent_polygons",
        "is_depth_raster": False,
        "is_hurricane_ida": False,
        "time": None,
        "time_note": "Record-category library extent, not an Ida time.",
        "crs": "EPSG:4326",
        "resolution": None,
        "vertical_datum": "NGVD29 gage datum on the AHPS site record",
        "units": "gage stage, not a depth grid",
        "nodata": None,
        "bounds": [-74.67487952884434, 40.409581761673564, -74.53358342887198, 40.54371305797092],
        "bounds_crs": "EPSG:4326",
        "source": "https://maps.water.noaa.gov/server/rest/services/fim_libs/static_stage_based_catfim/MapServer/13",
    },
    {
        "id": "noaa_catfim_bkwn4_action_extent",
        "title": "NOAA stage-based CatFIM action-stage extent, Millstone River at Blackwells Mills NJ (bkwn4)",
        "product_type": "flood_extent_polygons",
        "is_depth_raster": False,
        "is_hurricane_ida": False,
        "time": None,
        "time_note": "Action-stage library extent, not an Ida time.",
        "crs": "EPSG:4326",
        "resolution": None,
        "vertical_datum": "NGVD29 gage datum on the AHPS site record",
        "units": "gage stage, not a depth grid",
        "nodata": None,
        "bounds": [-74.65283959870706, 40.41230267918355, -74.55851360309593, 40.54025711844988],
        "bounds_crs": "EPSG:4326",
        "source": "https://maps.water.noaa.gov/server/rest/services/fim_libs/static_stage_based_catfim/MapServer/3",
    },
    {
        "id": "fema_mercer_county_pennsylvania_1pct_depth",
        "title": "FEMA 1% annual-chance depth grid, Mercer County, Pennsylvania (not Mercer County, New Jersey)",
        "product_type": "depth_raster",
        "is_depth_raster": True,
        "is_hurricane_ida": False,
        "time": "2009-12-18 publication date on the PASDA metadata; not an event time",
        "time_note": "Regulatory-style depth grid for a Pennsylvania county. Depths were not read.",
        "crs": "EPSG:2272",
        "resolution": "variable; metadata describes survey feet",
        "vertical_datum": "not read from a local GeoTIFF; PASDA metadata is a Pennsylvania state-plane product",
        "units": "feet, from the PASDA layer description, not from a file opened here",
        "nodata": "not read; the GeoTIFF was not downloaded",
        "bounds": [1205777.059, 650085.117, 1351975.254, 797662.674],
        "bounds_crs": "EPSG:2272",
        "source": "https://services.pasda.psu.edu/server/rest/services/pasda/FEMADepthGrids/MapServer/27",
    },
]


# Products that were identified and are not extent-tested as rasters.
NOTES: list[dict[str, Any]] = [
    {
        "id": "usgs_fim_catalog_no_stony_brook",
        "title": "USGS Flood Inundation Mapper site catalog (187 sites)",
        "finding": (
            "The catalog query on 2026-11-02 returned 187 sites. "
            "USGS 01401000 Stony Brook at Princeton is not in it. "
            "No site title or community contains Stony Brook, Princeton, Millstone, or Carnegie Lake. "
            "The seven New Jersey libraries are Delaware at Trenton, three Saddle River sites, "
            "Hohokus Brook, Peckman River, and Cape May Harbor."
        ),
        "used_as_princeton_depth": False,
    },
    {
        "id": "noaa_catfim_no_princeton_gage",
        "title": "NOAA stage-based CatFIM site layer",
        "finding": (
            "A query for AHPS pctn4 and USGS 01401000 returned no site. "
            "Action, minor, moderate, major, and record polygons intersect the municipal polygon in 0 features. "
            "Nearby mapped gages are Millstone at Blackwells Mills, Assunpink at Trenton, and the Delaware. "
            "Those are polygons of a flood category, not a depth raster and not an Ida time."
        ),
        "used_as_princeton_depth": False,
    },
    {
        "id": "noaa_nwm_analysis_inundation",
        "title": "NOAA National Water Model analysis inundation extent",
        "finding": (
            "The experimental analysis layer is a polygon of current high-water extent, not a depth raster and not an archived Ida surface. "
            "A spatial query of the municipal polygon on 2026-11-02 returned 0 features. "
            "It was not sampled."
        ),
        "source": "https://maps.water.noaa.gov/server/rest/services/nwm/ana_inundation_extent/MapServer/0",
        "used_as_princeton_depth": False,
    },
    {
        "id": "fema_mercer_nj_vectors",
        "title": "FEMA hosted Mercer County, New Jersey flood-hazard layers",
        "finding": (
            "Mercer_County_Effective_Flood_Hazard_Zones is a polygon feature layer. "
            "Mercer_County_NJ_Effective_Base_Flood_Elevations is a polyline feature layer whose layer name says NGVD29. "
            "Neither is a depth raster. A spatial count against the Princeton envelope returned a service error, "
            "so intersection was not measured. No depth was sampled from them. "
            "They are not Hurricane Ida observations."
        ),
        "source": "https://hazards.fema.gov/geoplatformserver/rest/services/Hosted",
        "used_as_princeton_depth": False,
    },
    {
        "id": "sciencebase_queries",
        "title": "USGS ScienceBase catalog search",
        "finding": (
            "Queries for flood inundation at Stony Brook Princeton, Stony Brook at Princeton inundation, "
            "Hurricane Ida flood depth New Jersey raster, Millstone River flood inundation depth grid, "
            "and Carnegie Lake flood depth each returned total 0."
        ),
        "used_as_princeton_depth": False,
    },
    {
        "id": "njdep_manville_ida_grid",
        "title": "NJDEP Blue Acres mention of a Manville Borough Ida depth grid",
        "finding": (
            "The Blue Acres page says Rutgers built Ida flood simulations for Manville. "
            "No downloadable raster was found, and the page does not give a file whose extent can be tested. "
            "It was not assumed to cover Princeton and was not sampled."
        ),
        "source": "https://dep.nj.gov/blueacres/flood-risk-reduction-policy-manville/",
        "used_as_princeton_depth": False,
    },
    {
        "id": "usgs_nj_ida_high_water_marks",
        "title": "USGS New Jersey Ida high-water marks",
        "finding": (
            "Point elevations in feet NAVD88. Not a raster. "
            "The exposure run recounts how many fall inside the municipal polygon. "
            "They are not turned into a depth surface."
        ),
        "used_as_princeton_depth": False,
    },
    {
        "id": "pennsylvania_ida_depth_grids",
        "title": "USGS Pennsylvania Hurricane Ida depth grids",
        "finding": (
            "Already tested in data/processed/ida_raster_coverage_check.json. "
            "Five grids, none intersecting Princeton. Not reused as a Princeton depth surface."
        ),
        "used_as_princeton_depth": False,
    },
]


def coverage_against_princeton(boundary: gpd.GeoDataFrame) -> list[dict[str, Any]]:
    """Attach the municipal extent test to every candidate that has bounds."""
    records = []
    for candidate in CANDIDATES:
        bounds = tuple(candidate["bounds"])
        compared = raster_extent_against_boundary(bounds, candidate["bounds_crs"], boundary)
        record = dict(candidate)
        record["intersects_princeton"] = compared["intersects_princeton"]
        record["distance_to_princeton_m"] = compared["distance_to_princeton_m"]
        record["distance_to_princeton_km"] = compared["distance_to_princeton_km"]
        record["used_as_princeton_depth"] = False
        records.append(record)
    return records
