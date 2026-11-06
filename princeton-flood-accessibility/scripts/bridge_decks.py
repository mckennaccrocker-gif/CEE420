"""Join the 2025 National Bridge Inventory to the OSM bridge centerlines.

The inventory has no deck elevation. This script records the structures that
can be tied to a centerline and leaves every deck unmatched. It does not
sample the 3DEP cell under a bridge, and it does not rerun accessibility.

Run from princeton-flood-accessibility:

    python3 scripts/bridge_decks.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import geopandas as gpd
import networkx as nx
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from geospatial.bridge_decks import JOIN_DISTANCE_M  # noqa: E402
from geospatial.bridge_decks import SPAN_COVERS_CENTERLINE  # noqa: E402
from geospatial.bridge_decks import assess_centerline  # noqa: E402
from geospatial.bridge_decks import nbi_has_deck_elevation_column  # noqa: E402
from geospatial.bridge_decks import read_nbi_records  # noqa: E402
from network.roads import load_settings  # noqa: E402
from network.roads import resolve  # noqa: E402


def _osmid_key(value: Any) -> frozenset[str]:
    if isinstance(value, (list, tuple)):
        parts = [str(item).strip() for item in value]
    else:
        text = str(value).strip()
        if text.startswith("[") and text.endswith("]"):
            text = text[1:-1]
        parts = [part.strip().strip("'\"") for part in text.replace(",", ";").split(";")]
    return frozenset(part for part in parts if part and part.lower() != "none")


def _refs_by_osmid(graphml: Path) -> dict[frozenset[str], str | None]:
    graph = nx.read_graphml(graphml)
    refs: dict[frozenset[str], str | None] = {}
    for _u, _v, _key, data in graph.edges(keys=True, data=True):
        key = _osmid_key(data.get("osmid"))
        ref = data.get("ref")
        if ref is None or str(ref).strip().lower() in {"", "none", "nan"}:
            ref = None
        else:
            ref = str(ref)
        if key not in refs or (refs[key] is None and ref is not None):
            refs[key] = ref
    return refs


def build_join(settings: dict) -> dict[str, Any]:
    provenance = json.loads(resolve(settings, "nbi_provenance").read_text(encoding="utf-8"))
    columns, records, skipped_coordinates = read_nbi_records(resolve(settings, "nbi_delimited"))
    if nbi_has_deck_elevation_column(columns):
        raise SystemExit("The NBI file has an elevation column this script does not know how to join.")
    structures = gpd.GeoDataFrame(
        geometry=[Point(row["longitude"], row["latitude"]) for row in records],
        crs="EPSG:4326",
    ).to_crs(3424)
    structure_rows = records
    for row, geometry in zip(structure_rows, structures.geometry, strict=True):
        row["geometry"] = geometry

    centerlines = gpd.read_file(resolve(settings, "exposure_gpkg"), layer="centerline_exposure")
    bridges = centerlines[centerlines["is_bridge"] == True].copy()  # noqa: E712
    refs = _refs_by_osmid(resolve(settings, "graphml"))
    assessed = []
    for record in bridges.itertuples(index=False):
        ref = refs.get(_osmid_key(record.osmid))
        result = assess_centerline(
            name=None if record.name is None else str(record.name),
            ref=ref,
            line=record.geometry,
            length_m_inside=float(record.length_m_inside),
            structures=structure_rows,
        )
        assessed.append(
            {
                "centerline_id": record.centerline_id,
                "name": None if record.name is None else str(record.name),
                "ref": ref,
                "length_m_inside": round(float(record.length_m_inside), 1),
                "exposure_status": result["exposure_status"],
                "deck_elevation_m": result["deck_elevation_m"],
                "depth_m_by_stage": result["depth_m_by_stage"],
                "unmatched_reasons": result["unmatched_reasons"],
                "note": result["note"],
                "hurricane_ida_depth": False,
                "event_time": None,
                "terrain_used_as_deck": False,
                "accepted_structures": result["accepted_structures"],
                "nearest_structure": result["nearest_structure"],
            }
        )
    assessed.sort(key=lambda item: (str(item["name"]), -item["length_m_inside"], item["centerline_id"]))
    n_sampled = sum(1 for item in assessed if item["exposure_status"] == "bridge_deck_sampled")
    n_elevation = sum(1 for item in assessed if item["deck_elevation_m"] is not None)
    return {
        "computed_at_utc": provenance["retrieved_at_utc"],
        "hurricane_ida_depth": False,
        "event_time": None,
        "terrain_under_bridge_used_as_deck": False,
        "accessibility_rerun": False,
        "accessibility_rerun_reason": (
            "No bridge status can change. No published deck elevation was joined, "
            "so the stage-3 accessibility graph was left as it is."
            if n_sampled == 0
            else "A deck elevation changed at least one bridge. Accessibility must be rerun for those centerlines only."
        ),
        "n_bridge_centerlines": len(assessed),
        "n_with_deck_elevation": n_elevation,
        "n_sampled": n_sampled,
        "depth_rule": "max(0, scenario water surface - deck elevation), evaluated separately at +1.0 m and +2.0 m",
        "depth_rule_applied": n_sampled > 0,
        "join_distance_m": JOIN_DISTANCE_M,
        "span_covers_centerline_fraction": SPAN_COVERS_CENTERLINE,
        "join_crs": "EPSG:3424",
        "sources": [
            {
                "id": "fhwa_nbi_2025_nj",
                "used_for_join": True,
                "title": provenance["title"],
                "publisher": provenance["publisher"],
                "url": provenance["url"],
                "retrieved_at_utc": provenance["retrieved_at_utc"],
                "file_last_modified": provenance["http_last_modified"],
                "sha256": provenance["sha256"],
                "n_records": provenance["n_records"],
                "horizontal_datum": provenance["horizontal_datum"],
                "vertical_datum": provenance["vertical_datum"],
                "units": provenance["units"],
                "deck_elevation_column_present": False,
                "n_columns": len(columns),
                "n_records_skipped_bad_coordinate": skipped_coordinates,
            },
            {
                "id": "fhwa_snbi_2022",
                "used_for_join": False,
                "title": "Specifications for the National Bridge Inventory, March 2022",
                "publisher": "Federal Highway Administration",
                "url": "https://www.fhwa.dot.gov/bridge/snbi/snbi_march_2022_publication.pdf",
                "retrieved_at_utc": provenance["retrieved_at_utc"],
                "horizontal_datum": "NAD83 for B.L.05 latitude and B.L.06 longitude",
                "vertical_datum": None,
                "units": "B.G.13 Maximum Bridge Height is feet from the top of the deck down to the ground or water surface. It is not a deck elevation.",
                "deck_elevation_column_present": False,
                "note": "The geometry section has lengths, widths, and that height. It has no NAVD88 or NGVD29 deck elevation.",
            },
            {
                "id": "njdot_bridges_dvrpc",
                "used_for_join": False,
                "title": "NJDOT Bridges",
                "publisher": "Delaware Valley Regional Planning Commission, from NJDOT TransINFO",
                "url": "https://arcgis.dvrpc.org/portal/rest/services/transportation/njdot_bridges/FeatureServer/0",
                "catalog_url": "https://catalog.dvrpc.org/dataset/njdot-bridges",
                "retrieved_at_utc": provenance["retrieved_at_utc"],
                "catalog_metadata_last_modified": "2026-09-17",
                "condition_extracted": "2026-07-25",
                "horizontal_datum": "EPSG:4326 on this service. NJDOT's own GIS metadata stores source data in NAD83 New Jersey State Plane feet.",
                "vertical_datum": None,
                "has_z": False,
                "units": "Deck width, deck area, and structure length are measures. Deck condition is a rating.",
                "deck_elevation_column_present": False,
                "note": "The feature service field list has deck condition, deck width, and deck area. It has no elevation field.",
            },
            {
                "id": "njogis_burlington_structures",
                "used_for_join": False,
                "title": "Engineering Bridges Culverts and Crossdrains (combined)",
                "publisher": "Burlington County, published on NJGIN Open Data",
                "url": "https://njogis-newjersey.opendata.arcgis.com/datasets/9abdd9d2bb084fbea0a7b9daa408532a",
                "retrieved_at_utc": provenance["retrieved_at_utc"],
                "horizontal_datum": "NAD83 / New Jersey (ftUS), EPSG:3424",
                "vertical_datum": None,
                "has_z": False,
                "deck_elevation_column_present": False,
                "note": "This is Burlington County, not Mercer County or Princeton. It was checked and not used.",
            },
        ],
        "not_used": [
            {
                "id": "usgs_3dep_at_bridge_point",
                "reason": "A 3DEP elevation at the bridge coordinate is the terrain under the deck. It was not sampled and was not called a deck elevation.",
            }
        ],
        "centerlines": assessed,
    }


def main() -> None:
    settings = load_settings(ROOT / "config" / "settings.yaml")
    payload = build_join(settings)
    destination = resolve(settings, "bridge_deck_join")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {destination}. "
        f"{payload['n_with_deck_elevation']} of {payload['n_bridge_centerlines']} "
        "bridge centerlines have a deck elevation. Accessibility was not rerun."
    )


if __name__ == "__main__":
    main()
