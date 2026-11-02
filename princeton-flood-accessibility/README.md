# Princeton flood exposure and road accessibility

Stage 1 of a Princeton, New Jersey flood-exposure and road-accessibility project. This stage builds and checks the **baseline drivable road network** only.

It does **not** estimate flood depth, close roads, compute accessibility, or draw a flood map. The depth values 0.10 m and 0.30 m in `config/settings.yaml` are preliminary scenario assumptions for a later stage. They are not official NJDOT, FEMA, or Princeton closure standards, and they are not Hurricane Ida observations. Nothing in this stage compares a road to those depths.

## What is already true about flood data

No Hurricane Ida flood-depth raster is in this repository, and none was found whose extent intersects the Princeton municipal boundary. The only Ida depth grids inspected are five USGS Pennsylvania community grids (Chadds Ford, Downingtown, Modena, Norristown, Perkiomen). Their extents are tens of kilometres from Princeton. See `data/processed/ida_raster_coverage_check.json` for the header values actually read (CRS, resolution, bounds, nodata, file time). Those GeoTIFFs do not declare vertical units. They are not used by the road network.

A DEM bathtub model is **not** implemented. If a later stage can only use a bare-earth DEM, that result must stay a labeled scenario. It would not be a validated Ida simulation.

## Baseline definition

- **Place.** The Municipality of Princeton, New Jersey. The polygon is the NJGIN municipal-boundary snapshot shipped with the course as `P01/data/princeton_boundary.geojson` (retrieved 2026-09-07, public record), copied unchanged to `data/raw/princeton_boundary.geojson`.
- **Roads.** OpenStreetMap drivable ways from OSMnx `network_type="drive"`: public streets a motor vehicle can use. Service roads, footways, tracks, and `access=private` are excluded by that filter. The filter does not drop bridges.
- **Extent.** `truncate_by_edge=true` keeps a segment that crosses the municipal line, including the short piece outside the polygon. `retain_all=true` keeps disconnected pieces so the component count is not forced to 1.
- **Length.** A two-way street is stored as two directed edges. Centerline totals count it once, matched on the unordered endpoints and the OSM way id. `length_m` is the OSMnx ellipsoidal length in metres. `length_m_inside` is the EPSG:3424 length of the piece that falls inside the municipality, converted from US survey feet with the exact factor 1200/3937.
- **Bridges.** An OSM `bridge` tag other than `no` sets `is_bridge`. The flag applies to the whole centerline that carries the tag, so the summed "bridge length" is not a surveyed deck span. It is not a deck elevation. Later flood work must not sample the ground under a bridge and call it the depth on the deck. `layer>0` is stored separately as `is_positive_layer` and is not treated as a bridge.
- **Speed.** `maxspeed` is kept as published. A miles-per-hour value is parsed only when the tag says `mph` or `km/h`. Bare numbers are left unknown. Nothing is imputed.
- **AADT.** NJDOT 2024 station rows whose community name contains Princeton in Mercer County are stored as points. They are not copied onto edges and are not summed.

## Coordinate reference system

Analysis geometry is **EPSG:3424, NAD83 / New Jersey (ftUS)**. NJOGIS publishes the statewide road centerlines in that system (the hosted layer is titled "Road Centerlines of NJ, Hosted, 3424"). EPSG:6539 is the NAD83(2011) realization of the same zone. It was not used, so a later overlay does not mix datum realizations.

OSMnx length stays in ellipsoidal metres. Planar lengths start in US survey feet and are converted with 1200/3937 m, not the international foot 0.3048 m. GeoJSON files are written in EPSG:4326. The GeoPackage and the GraphML graph are EPSG:3424. The PROJ pipeline from EPSG:4326 to EPSG:3424 is recorded in `data/processed/baseline_stats.json`.

EPSG:26918 (metres) is used only to confirm the boundary area is the course snapshot, 47.66 km². A centroid outside a Princeton, NJ window aborts the build. That check exists because another Princeton is easy to load by mistake.

## How to run

From this directory, with the packages in `requirements.txt` installed:

```bash
pip install -r requirements.txt
python3 scripts/fetch_njdot_aadt.py
python3 scripts/fetch_usgs_ida_hwm.py
python3 scripts/download_roads.py
python3 scripts/check_raster_coverage.py /path/to/chaddsford_depth_grid.tif
python3 -m pytest
```

`download_roads.py` calls the Overpass API, writes the network, the stats, and the baseline map, and stops if the boundary is the wrong town, the graph is empty, the CRS is not EPSG:3424, or the ellipsoidal and State Plane lengths disagree by more than 2%. The OSMnx cache is `data/raw/osmnx_cache/` and is gitignored. Re-running the script rebuilds `data/processed/` and the map.

The Pennsylvania GeoTIFFs are not in the repository. The committed coverage JSON is the inspection from the URLs listed in `config/settings.yaml`. Passing those local GeoTIFFs to `check_raster_coverage.py` repeats the check. The script does not download rasters and does not sample Princeton depths.

These scripts exit with an error if you run them now. They are not partial flood or accessibility models:

```bash
python3 scripts/flood_exposure.py
python3 scripts/accessibility.py
python3 scripts/dashboard.py
```

## What each script does

| Script | Role |
| --- | --- |
| `scripts/download_roads.py` | Download the drive network, project it, write the files below, draw the baseline map. |
| `scripts/fetch_njdot_aadt.py` | Download the NJDOT 2024 AADT CSV and keep Mercer County rows whose community contains Princeton. |
| `scripts/fetch_usgs_ida_hwm.py` | Download the USGS New Jersey Ida high-water-mark CSV unchanged. |
| `scripts/check_raster_coverage.py` | Read local GeoTIFF headers and test whether each extent meets Princeton. |
| `scripts/flood_exposure.py` | Placeholder. Exits with an error. |
| `scripts/accessibility.py` | Placeholder. Exits with an error. |
| `scripts/dashboard.py` | Placeholder. Exits with an error. |

## Outputs

| Path | Contents |
| --- | --- |
| `data/processed/princeton_drive_network.gpkg` | Layers `nodes`, `edges` (directed), `centerlines` (one row per physical segment), `boundary`. EPSG:3424. |
| `data/processed/princeton_drive_network.graphml` | Directed graph. Node coordinates are EPSG:3424 feet. `length` and `length_m` remain metres. |
| `data/processed/princeton_drive_centerlines.geojson` | Centerlines in EPSG:4326. |
| `data/processed/princeton_drive_nodes.geojson` | Nodes in EPSG:4326. |
| `data/processed/princeton_drive_edges.geojson` | Directed edges in EPSG:4326. Summing `length_m` here double-counts two-way streets. Use `centerlines` for length. |
| `data/processed/baseline_stats.json` | Counts, lengths, CRS, and file hashes from the run. |
| `outputs/tables/baseline_road_stats.csv` | The same headline metrics. |
| `outputs/maps/princeton_baseline_drive_network.png` | Baseline map. Red means an OSM bridge tag, not flooding. |
| `data/processed/ida_raster_coverage_check.json` | Header inspection of the Pennsylvania Ida grids and their distance to Princeton. |

`outputs/figures/` is reserved for later charts. The map is under `outputs/maps/`.

## Data on hand and data still needed

**In this project**

- NJGIN municipal boundary of Princeton (public record, course snapshot).
- OSM drivable network built by `download_roads.py` (© OpenStreetMap contributors, ODbL 1.0).
- NJDOT 2024 AADT station table, Princeton rows only, not joined to edges.
- USGS high-water marks for Hurricane Ida in New Jersey (point elevations, NAVD88 feet in the source table). These are observations, not a depth grid. Many of the marks are outside the municipality; the inside count is in `baseline_stats.json`.

**Not in this project, and not invented**

- A Hurricane Ida depth or inundation raster that covers Princeton. The Pennsylvania grids do not. An NJDEP note about an Ida depth grid for Manville Borough was not a file that could be inspected here, so it is not treated as Princeton inundation.
- USGS 3DEP elevation for a later scenario. Not downloaded.
- NJOGIS road centerlines (https://njogis-newjersey.opendata.arcgis.com/maps/fc3d0a95921b4026b386643eef5ff088 and https://njgin.nj.gov/njgin/edata/roads/). Statewide, EPSG:3424, with names, address ranges, and elevation level. Not downloaded. Useful later as a supplement. The baseline graph is OSM because it is routable and keeps bridge tags. NJOGIS should not be assumed to match OSM segment for segment.
- NJDOT AADT on the rest of the state, and any join from a station point to an edge. The join is a later decision.
- Bridge-deck elevations (National Bridge Inventory or a survey). OSM `bridge=yes` does not give the deck height, so terrain under the bridge is not the bridge.
- FEMA National Flood Hazard Layer polygons. A regulatory zone, not an Ida observation.
- A pinned historical Overpass date. The network is the OSM extract at the `retrieved_at_utc` timestamp in the stats file. Re-running the script can change the network.

## Repository layout

```
config/settings.yaml          paths, CRS, network options, unused depth thresholds
data/raw/                     boundary, AADT extract, USGS HWM table, OSMnx cache
data/processed/               network files and stats
src/geospatial/               CRS, point inventory, raster-extent test, flood placeholder
src/network/                  download, centerline length, baseline writer
src/visualization/            baseline map
scripts/                      command-line entry points
outputs/maps/                 baseline map
outputs/figures/              empty until a later stage
outputs/tables/               baseline stats table
tests/                        length, CRS, placeholders, saved outputs
```

## Tests

`python3 -m pytest` checks the US survey foot, the Princeton boundary identity, centerline de-duplication, the refusal of the flood placeholder, and the saved files against `baseline_stats.json`. The saved-file tests fail if `download_roads.py` has not been run.
