# Princeton flood exposure and road accessibility

Princeton, New Jersey flood-exposure and road-accessibility project. Stage 1 is the baseline drivable road network. Stage 2 is a labeled flood-depth scenario on those centerlines. Stage 3 removes some of those centerlines under a preliminary fraction rule and recounts connectivity. It is not a dashboard.

The depth values 0.10 m and 0.30 m in `config/settings.yaml` are preliminary assumptions, not official NJDOT, FEMA, or Princeton closure standards, and they are not Hurricane Ida observations. Stage 2 only labels them. Stage 3 uses the same cuts to decide which centerlines leave the routable graph. That decision is still an assumption.

## What is already true about flood data

No Hurricane Ida flood-depth raster is in this repository, and none was found whose extent intersects the Princeton municipal boundary. The only Ida depth grids inspected are five USGS Pennsylvania community grids (Chadds Ford, Downingtown, Modena, Norristown, Perkiomen). Their extents are tens of kilometres from Princeton. See `data/processed/ida_raster_coverage_check.json` for the header values actually read (CRS, resolution, bounds, nodata, file time). Those GeoTIFFs do not declare vertical units. They are not used by the road network.

No agency depth raster was found whose extent meets the municipality. The substitute is a hypothetical USGS 3DEP channel-relative scenario (`scripts/flood_exposure.py`). It is not a Hurricane Ida simulation. Scenario depths are not observations. The search record is `data/processed/flood_raster_search.json`.

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
python3 scripts/flood_exposure.py
python3 scripts/accessibility.py
python3 scripts/check_raster_coverage.py /path/to/chaddsford_depth_grid.tif
python3 -m pytest
```

`download_roads.py` calls the Overpass API, writes the network, the stats, and the baseline map, and stops if the boundary is the wrong town, the graph is empty, the CRS is not EPSG:3424, or the ellipsoidal and State Plane lengths disagree by more than 2%. The OSMnx cache is `data/raw/osmnx_cache/` and is gitignored. Re-running the script rebuilds the baseline files and the map.

`flood_exposure.py` reads the saved centerlines. If `data/raw/usgs_3dep_princeton_10m.tif` or `data/raw/nhd_princeton_channels.geojson` is missing, it downloads that file once. It does not overwrite a raw file that is already there. It refuses to run unless the scenario is marked as not an Ida simulation. Bridge-tagged centerlines are left unmatched. The two stages in the config (1.0 m and 2.0 m above the channel DEM) are separate assumptions. They are not a time series.

`accessibility.py` reads the saved exposure and the saved graph. It does not recompute depths and it does not interpolate between the two stages. A centerline is removed only when at least half of its inside length is pieces at or above 0.30 m (`accessibility.closure_piece_fraction`). Bridge decks and centerlines with no channel match stay in the graph. If `data/raw/osm_destinations_princeton.geojson` is missing, the script downloads OSM amenities once and does not overwrite that file later. `dashboard.py` still exits with an error.

The Pennsylvania GeoTIFFs are not in the repository. The committed coverage JSON is the inspection from the URLs listed in `config/settings.yaml`. Passing those local GeoTIFFs to `check_raster_coverage.py` repeats the check. The script does not download rasters and does not sample Princeton depths.

## What each script does

| Script | Role |
| --- | --- |
| `scripts/download_roads.py` | Download the drive network, project it, write the files below, draw the baseline map. |
| `scripts/fetch_njdot_aadt.py` | Download the NJDOT 2024 AADT CSV and keep Mercer County rows whose community contains Princeton. |
| `scripts/fetch_usgs_ida_hwm.py` | Download the USGS New Jersey Ida high-water-mark CSV unchanged. |
| `scripts/check_raster_coverage.py` | Read local GeoTIFF headers and test whether each extent meets Princeton. |
| `scripts/flood_exposure.py` | Labeled 3DEP scenario depths on centerlines. Not an Ida reconstruction and not a road closure. |
| `scripts/accessibility.py` | Remove fraction-rule centerlines from the two scenario graphs and write connectivity, routes, and the disruption map. |
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
| `data/raw/usgs_3dep_princeton_10m.tif` | Resampled 3DEP bare-earth clip, about 10 m, EPSG:26918. Not a flood grid. |
| `data/raw/nhd_princeton_channels.geojson` | NHD flowlines and Carnegie Lake used as the channel reference. |
| `data/processed/flood_raster_search.json` | Agency products tested against the municipal polygon. None is used as a Princeton depth. |
| `data/processed/princeton_centerline_exposure.gpkg` | Scenario max and mean depth per centerline. EPSG:3424. |
| `data/processed/princeton_centerline_exposure.geojson` | The same table in EPSG:4326. |
| `data/processed/flood_exposure_stats.json` | Scenario assumptions and summary lengths. |
| `outputs/tables/centerline_flood_exposure.csv` | One row per centerline, no geometry. |
| `outputs/tables/flood_exposure_summary.csv` | One row per assumed stage. |
| `outputs/maps/princeton_scenario_exposure.png` | Static map of the +2.0 m assumption. Not a dashboard. |
| `data/raw/osm_destinations_princeton.geojson` | OSM hospital, school, fire, police, town hall, and ambulance amenities that intersect the municipality. |
| `data/processed/princeton_accessibility.gpkg` | Centerline routing status for both stages. EPSG:3424. |
| `data/processed/princeton_accessibility.geojson` | The same table in EPSG:4326. |
| `data/processed/accessibility_stats.json` | Closure counts, component lengths, routes, and the AADT snap summary. |
| `outputs/tables/accessibility_centerlines.csv` | One row per centerline, no geometry. |
| `outputs/tables/accessibility_components.csv` | Weak components and the inside length still in each. |
| `outputs/tables/accessibility_od_pairs.csv` | Baseline and scenario path length for the snapped destinations. |
| `outputs/tables/accessibility_critical_segments.csv` | Graph-theory bridges and centerlines on many of those paths. |
| `outputs/tables/accessibility_aadt_snap.csv` | Nearest-edge status of each AADT station-record. AADT is not summed. |
| `outputs/maps/princeton_accessibility_disruption.png` | Baseline and both stages. Red is the fraction rule, not a closure standard. |

`outputs/figures/` is reserved for later charts. Maps are under `outputs/maps/`.

## Data on hand and data still needed

**In this project**

- NJGIN municipal boundary of Princeton (public record, course snapshot).
- OSM drivable network built by `download_roads.py` (© OpenStreetMap contributors, ODbL 1.0).
- NJDOT 2024 AADT station table, Princeton rows only. Stage 3 snaps each station-record to the nearest centerline and reports the share whose nearest edge is assumed closed. The AADT values are not summed and are not a count of travelers.
- USGS high-water marks for Hurricane Ida in New Jersey (point elevations, NAVD88 feet in the source table). These are observations, not a depth grid. The exposure run counts 0 inside the municipality. The nearest is about 2.27 km outside. They are not the scenario water surface.
- A 10 m USGS 3DEP bare-earth clip and the NHD channel lines used by the scenario. The GeoTIFF does not itself state a vertical datum. Values are interpreted as metres NAVD88 because that is the 3DEP convention and the numeric range matches metres.

**Not in this project, and not invented**

- A Hurricane Ida depth or inundation raster that covers Princeton. The Pennsylvania grids do not. USGS and NOAA flood libraries near Princeton do not intersect the municipal polygon. An NJDEP note about an Ida depth grid for Manville Borough was not a file that could be inspected here, so it is not treated as Princeton inundation.
- NJOGIS road centerlines (https://njogis-newjersey.opendata.arcgis.com/maps/fc3d0a95921b4026b386643eef5ff088 and https://njgin.nj.gov/njgin/edata/roads/). Statewide, EPSG:3424, with names, address ranges, and elevation level. Not downloaded. Useful later as a supplement. The baseline graph is OSM because it is routable and keeps bridge tags. NJOGIS should not be assumed to match OSM segment for segment.
- NJDOT AADT on the rest of the state. The Princeton join is a nearest-edge snap with a 30 m limit and a 10 m ambiguity gap. It is not a traffic assignment.
- Bridge-deck elevations (National Bridge Inventory or a survey). OSM `bridge=yes` does not give the deck height, so terrain under the bridge is not the bridge.
- FEMA National Flood Hazard Layer polygons. A regulatory zone, not an Ida observation.
- A pinned historical Overpass date. The network is the OSM extract at the `retrieved_at_utc` timestamp in the stats file. Re-running the script can change the network.

## Repository layout

```
config/settings.yaml          paths, CRS, network options, scenario stages, label thresholds
data/raw/                     boundary, AADT extract, USGS HWM table, 3DEP clip, NHD channels
data/processed/               network files, scenario exposure, search record
src/geospatial/               CRS, extent test, scenario depth
src/network/                  download, centerline length, baseline writer, scenario disruption
src/visualization/            baseline map, scenario map, disruption map
scripts/                      command-line entry points
outputs/maps/                 baseline, exposure, and disruption maps
outputs/figures/              empty until a later stage
outputs/tables/               baseline, exposure, and accessibility tables
tests/                        length, CRS, closure rule, placeholders, saved outputs
```

## Tests

`python3 -m pytest` checks the US survey foot, the Princeton boundary identity, centerline de-duplication, the refusal of an unlabeled depth call, scenario nodata and bridge handling, the closure fraction, component length on a tiny graph, and the saved baseline, exposure, and accessibility files. The saved-file tests fail if `download_roads.py`, `flood_exposure.py`, or `accessibility.py` has not been run. `dashboard.py` is still required to exit.
