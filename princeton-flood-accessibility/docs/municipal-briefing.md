# Princeton road flood briefing

For municipal staff. Every figure below is taken from the project stage reports. This note does not add a new measurement.

The map is a screening picture of the public drivable streets in Princeton. It shows two hypothetical water-surface assumptions on a USGS 3DEP bare-earth elevation clip: **+1.0 m** and **+2.0 m** above the elevation of a nearby mapped channel. Those two cases are separate assumptions. They are not hours of a storm, they are not a clock, and the screen has no time slider. They were not interpolated, and they were not scaled by El Niño.

They are not a reconstruction of Hurricane Ida on 1–2 September 2021. No flood-depth raster whose extent meets the municipality was found. The scenario was computed 2 November 2026 at 22:36 UTC. Every flood row is marked as not an Ida depth, and the event time is blank.

The banner on the map says the same thing: the depths are a hypothetical 3DEP channel-relative scenario, and 0.10 m, 0.30 m, and the half-length fraction are preliminary assumptions, not closure standards.

## The street network the colors sit on

The streets are the OpenStreetMap drivable network retrieved 2 November 2026 at 21:58 UTC. Service roads, alleys, and private roads are left out by that filter. The town outline is the NJGIN municipal polygon, about 47.66 km².

| | |
| --- | ---: |
| Centerlines (a two-way street counted once) | 1,298 |
| Length inside the municipality | 232,984.8 m (232.98 km) |
| Nodes / intersections | 932 / 800 |
| Connected pieces before any flood assumption | 1 |
| Bridge-tagged centerlines | 20, totaling 8,866.8 m inside the town |

A bridge tag applies to the whole OpenStreetMap way, not to a surveyed span. The longest tagged way is Quaker Road, about 2.8 km inside the boundary in the baseline, and 2,826.5 m on the centerline used later. NJDOT’s 2024 traffic counts contribute 39 station-records at 13 points. Those counts were not added up, and they were not copied onto the streets.

## What +1.0 m and +2.0 m do to access

Depth at a point on a street is the channel elevation, plus 1.0 m or 2.0 m, minus the road elevation, and never below zero. The channel has to be within 500 m and no more than 2.0 m above the road. A higher channel is treated as uphill and is not used. Because of that rule, a scenario depth cannot exceed the assumed stage plus 2.0 m. The deepest samples sit on that ceiling: 2.992 m in the +1.0 m case and 3.992 m in the +2.0 m case.

A street is removed from the routable map only when at least half of its inside length is in pieces at or above 0.30 m. A wet end on a long street does not close the street. The 0.10 m, 0.30 m, and one-half rules are labeled preliminary assumptions. They are not an NJDOT, FEMA, or Princeton closure standard.

The shares below use the full 232,984.8 m as the denominator, including bridges and streets with no channel match. The accessibility count was run 2 November 2026 at 22:54 UTC and was not rerun after the later bridge, FEMA, or NJOGIS work.

| | +1.0 m | +2.0 m |
| --- | ---: | ---: |
| Length of road in pieces at or above 0.30 m | 8,307.0 m (3.57%) | 19,159.8 m (8.22%) |
| Streets removed by the half-length rule | 33 (2.54% of streets) | 90 (6.93%) |
| Inside length of those removed streets | 3,732.3 m (1.60%) | 14,327.2 m (6.15%) |
| Streets whose deepest sample is at or above 0.30 m, including streets that stay open | 143 | 234 |
| Remaining connected pieces | 13 | 42 |
| Largest remaining piece | 228,600.2 m, 913 nodes | 173,693.1 m, 754 nodes |
| Routes to the snapped hospital | connected | disconnected |
| Traffic-count records whose nearest street is removed | 0 of 39 | 0 of 39 |

The dashboard rounds the same run to 8.3 km wet and 3.7 km removed at +1.0 m, and 19.2 km wet and 14.3 km removed at +2.0 m. Use the metre table above if a meeting needs the unrounded figures. “Wet length” is the length of the deep pieces. “Removed” is the whole street once half of it is that deep. Many streets are deep at one end and stay on the map, which is why 143 and 234 streets have a deep sample while only 33 and 90 are removed.

At +1.0 m the town is still mostly one piece: 228.6 km and 913 nodes. Nine of the 13 pieces are single leftover nodes with no street length. At +2.0 m the largest piece is 173.7 km and 754 nodes. Thirty of the 42 pieces are leftover nodes. Two splits are large enough to name. One is about 37.3 km on the west side, including Great Road, Cherry Hill Road, Province Line Road, Pretty Brook Road, and Stuart Road. None of the routed public buildings is in that piece. The other is 2,786.9 m along Cherry Valley Road and nearby streets. The hospital snap sits there, so the hospital routes break only in the +2.0 m case.

The places used for those routes are one OpenStreetMap feature each: Princeton House Behavioral Health (the only hospital tag in the extract), Princeton High School, Princeton Fire Department, Princeton Police, and Princeton Municipal Building at Witherspoon Hall. Police and Witherspoon Hall snap to the same corner, so the path between them has length zero. No ambulance station was in the extract, and none was added. Travel time is reported only for the fire-to-police path in the baseline and at +1.0 m, 293.5 m and 31.1 seconds, because that is the only path where every segment has a posted speed. Speeds were not filled in.

## Quaker Road

Local reporting documents a real closure. Planet Princeton on 2 September 2021 still listed Quaker Road closed that evening, with Mercer Road and Stockton Street. Princeton Patch listed it the same day. On 3 September, Planet Princeton said the stretch from Mercer Street to the West Windsor border was still closed for a sinkhole. On 8 September, municipal engineer Deanna Stockton was quoted as having no reopening estimate. Town Topics on 20 October described the canal-bridge collapse. Planet Princeton on 22 December reported the reopening.

The scenario does not reproduce that closure. Ten centerlines are named Quaker Road. None is removed at either assumption. The length of Quaker Road pieces at or above 0.30 m is 0 m. Two of those centerlines are bridge decks with no elevation, so the model does not call them flooded and does not call them dry.

The long bridge way is 2,826.5 m, carries County Route 533, and matches two National Bridge Inventory structures. Neither has a published deck elevation or low-chord elevation in a named vertical datum.

| Structure | Crossing | Inventoried length | Built | Deck elevation |
| --- | --- | --- | ---: | --- |
| 1100082 | Quaker Road (CR 533) over Stony Brook | 24.7 m | 2013 | None found |
| 3000154 | Quaker Road over the Delaware & Raritan Canal | 14.6 m | 1951, reconstructed 2020 | None found |

Structure 1100082 sits 1.3 m from the mapped way. Structure 3000154 sits 23.7 m from it. One elevation, had one been found, would still not be copied onto the whole 2,826.5 m way. The short Quaker Road bridge way is 386.4 m and has no accepted structure. The nearest inventory point is US 206 structure 1129155, 49.8 m away, which is outside the project’s 40 m join.

A search of the Flood Insurance Study, the NJDOT Route 533 straight-line diagram, inspection extracts, and news accounts did not produce a deck elevation. A legislative summary lists a minimum vertical clearance of 99.99 feet for 3000154. In the National Bridge Inventory that figure is the unlimited-clearance code, not a height above sea level. The USGS Stony Brook gage at Route 206 (01401000) has a datum of 61.35 feet NAVD 88. A National Weather Service note that Quaker Road floods at 9 feet is a stage at that gage. Those two numbers were not added, and neither is the deck.

Of the other named closures in the same news check: Mercer Road has 0 streets removed at +1.0 m and 2 at +2.0 m, with 117.5 m and 510.7 m of deep pieces. Stockton Street / Route 206 has 0 streets removed at either stage. South Harrison Street has 0 streets removed and 0 m of deep pieces. That comparison was not scored. It is not a validation of the model.

## Name check, not a validation

The side panel compares these five September 2021 named roads with the scenario. It is a name check, not a validation. It was not scored. There is no precision and no recall. Depths were not recomputed. Click a name in that list to turn on the news-report dashes, zoom to those centerlines, and read the captured or missed result beside the name.

Captured means the scenario assumed at least one centerline of that name closed. Missed means it assumed none closed.

| Road | +1.0 m | +2.0 m |
| --- | --- | --- |
| Quaker Road | Missed | Missed |
| Mercer Road | Missed | Captured, 2 of 14 |
| Stockton Street / Route 206 | Missed | Missed |
| South Harrison Street | Missed | Missed |
| Rosedale Road | Missed | Missed |

Quaker Road is 10 centerlines, none assumed closed at either assumption. Mercer Road is 14 centerlines, not closed at +1.0 m, and 2 assumed closed at +2.0 m. Stockton Street is 11 centerlines, none assumed closed. South Harrison Street is 4 centerlines, none assumed closed, and the wording gap is left as written. Rosedale Road is 12 centerlines, none assumed closed. Its 2 September sentence is a reopening time, not a closure log.

## The FEMA layer is a regulation map

The flood-zone polygons are the effective FEMA National Flood Hazard Layer for Mercer County DFIRM 34021C, retrieved 3 November 2026. Twenty panels over the municipal envelope are effective **20 July 2016**. The layer is regulatory. It is not Hurricane Ida, it is not a deck elevation, and it does not change the +1.0 m or +2.0 m depths. A zone letter was not turned into a depth of water.

Centerline length inside each zone:

| Zone | Length | Centerlines |
| --- | ---: | ---: |
| AE floodway | 3,952.4 m | 54 |
| AE | 5,916.6 m | 67 |
| A | 383.3 m | 12 |
| X, 0.2% annual chance | 2,105.6 m | 71 |
| X, minimal flood hazard | 220,627.8 m | 1,266 |

Zones A and AE, including the floodway, together cover 10,252.3 m of centerline. That is the regulatory special flood hazard overlap. It is not a scenario depth. Most of the town is zone X, minimal hazard: about 41.2 km² of the polygon and 220,627.8 m of centerline. That length is not a depth of zero, and it does not mean the scenario left those streets dry.

The only water-surface number stored with this layer is **65.5 feet NAVD 88**. It is the regulatory base-flood water surface at Stony Brook cross section M, 22,120 feet above the Millstone River, from the Flood Insurance Study table and from the FEMA cross-section layer. The zone polygons themselves have no base-flood elevation filled in. The 65.5-foot figure was not copied onto a road and was not used as the Quaker Road deck.

On the long Quaker Road bridge way, the OpenStreetMap line falls in AE for 1,672.0 m, in the floodway for 975.5 m, in the 0.2% zone for 92.3 m, and in minimal zone X for 86.7 m. Those are lengths of the mapped way, not depths on structures 1100082 or 3000154.

A checkbox labeled **Regulatory flood zones** draws this layer. It is on by default. The line under it reads “Regulatory. Effective 20 July 2016. Not Hurricane Ida. Not a scenario depth.” The same date is in the legend and in the side panel. The road colors stay the scenario colors. Unchecking the box removes the polygons.

## El Niño is context, not a depth

The Pacific numbers were fetched 2 November 2026 at 23:14 UTC. They are not used to raise or lower a Princeton street.

| Product | Value | Date on the product |
| --- | --- | --- |
| Weekly Niño-3.4 sea-surface anomaly | +3.4 °C (sea-surface temperature 30.2 °C) | Week centered 28 October 2026 |
| Oceanic Niño Index | +2.16 °C (three-month mean sea-surface temperature 29.12 °C) | July–September 2026 |
| Official alert | El Niño Advisory | Diagnostic discussion issued 8 October 2026 |

The advisory is the status line in that 8 October discussion. It was not reclassified from the later weekly anomaly. The panel states that ENSO is large-scale context for Atlantic tropical cyclone activity and that it does not set a Princeton road depth. The phase is NOAA’s sentence, not a threshold on the weekly anomaly, and ENSO does not set Princeton road depths.

## NJOGIS and OpenStreetMap

The New Jersey Office of GIS road centerlines, hosted as “Road Centerlines of NJ, Hosted, 3424” and last edited as a service on 23 September 2026, were clipped to the town and compared with the OpenStreetMap drive network. NJOGIS has 1,612 centerlines and 262,462.2 m inside the municipality. OpenStreetMap has 1,298 centerlines and 232,984.8 m. NJOGIS is longer by 29,477.3 m. The two files were not matched segment for segment, and NJOGIS was not substituted for the routable map. Part of the gap is streets the drive extract does not keep, including 11,716.2 m of unnamed NJOGIS segments. NJOGIS has no bridge column. Its elevation fields are relative level codes, and all 1,612 clipped centerlines are coded at grade. That code is not a deck elevation and it is not a statement that Princeton has no bridges.

## Before using this in a meeting

- Say “hypothetical 3DEP scenario,” not “Ida inundation” and not “the flood at hour N.” The two buttons are two assumptions.
- Say which number you mean. Wet piece length, removed-street length, and “a deep sample somewhere on the street” are three different counts. At +2.0 m they are 19,159.8 m, 14,327.2 m, and 234 streets.
- A larger count of connected pieces is not, by itself, a neighborhood cut off from services. Most of the new pieces are single nodes.
- Purple on the map is an unknown bridge deck, still treated as passable. Gray is a street with no channel match, not a street certified dry. A low deck can keep a path on the map that would flood, and the model will not say so. Zero of the 20 bridge centerlines has a published deck elevation.
- The Quaker Road news closure is real in the 2021 record. The scenario leaves those centerlines in place because the deck elevation is missing. Do not tell a meeting that the model checked the Quaker Road bridges and found them dry.
- The 65.5-foot NAVD 88 number is a regulatory water surface at one Stony Brook cross section. It is not the height of the Quaker Road deck and it is not the scenario depth.
- Zone X is the regulatory “minimal hazard” class. It is not a measured dry street.
- A small length of centerline at the northwest corner, 62.7 m on Cherry Valley Road, Great Road, and Mountain View Road, falls on the Somerset County flood map, effective 28 September 2007. The 20 July 2016 Mercer date does not apply to that piece.
- Zero of 39 traffic-count records sits on a removed street. That is a share of station-records under a 30 m snap, not a count of vehicles, and not a statement that no counted road is near water. The nearest count to a removed street is 150.4 m away at +1.0 m and 49.7 m away at +2.0 m.
- The hospital in the route check is Princeton House Behavioral Health, snapped 140.9 m from the building point to the nearest drive node. Other schools and the other two fire companies were not routed.
- The September 2021 news check is qualitative. It was not scored, and the model is not validated.
- The elevation file is interpreted as metres, NAVD 88, because that is the 3DEP convention and the values fall in a metre range. The file itself does not say NAVD 88.
- The street file is the OpenStreetMap extract at the time it was downloaded. A later download can change the counts. NJOGIS is a comparison, not a second routing network.

## How to open it

On the project machine, from `/agent/repos/CEE420/princeton-flood-accessibility`:

```bash
python3 scripts/dashboard.py
```

Then open http://127.0.0.1:8765/ in a browser on that same machine. The page is not a public website. The **Regulatory flood zones** checkbox is at the top right and starts on. Green is treated as passable, yellow is in the 0.10–0.30 m band, orange is partly at or above 0.30 m but still routed, red is removed by the half-length rule, purple is an unknown deck, and gray is unmatched.

The project pull request is https://github.com/mckennaccrocker-gif/CEE420/pull/1.
