"""Qualitative comparison with September 2021 road reports.

Names are places to investigate. A news sentence is not a flooded-road
inventory, and this module does not score the scenario. There is no
precision and no recall. The model is not validated.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Contemporaneous local reporting, read on 2026-11-02. Hopewell's
# "Upper Stony Brook" is a different municipality and is not used.
PLACES: list[dict[str, Any]] = [
    {
        "place_id": "quaker_road",
        "title": "Quaker Road",
        "names": ["Quaker Road"],
        "verification": "documented",
        "claims": [
            {
                "source": "Planet Princeton",
                "published": "2021-09-02",
                "url": "https://planetprinceton.com/2021/09/02/thursday-morning-storm-update-routes-in-and-out-of-princeton-closed-as-flooding-continues/",
                "statement": "Evening update: Quaker Road, Mercer Road, and Stockton Street (Route 206) were still closed.",
            },
            {
                "source": "Princeton Patch",
                "published": "2021-09-02",
                "url": "https://patch.com/new-jersey/princeton/evacuations-state-emergency-ida-slams-mercer-county",
                "statement": "Listed Quaker Road among roads currently closed, with Mercer Road, Stockton Street (Rt. 206), and South Harrison Street.",
            },
            {
                "source": "Planet Princeton",
                "published": "2021-09-03",
                "url": "https://planetprinceton.com/2021/09/03/friday-morning-storm-update-most-roads-open-again-but-some-remain-closed-due-to-severe-storm-damage/",
                "statement": "Quaker Road between Mercer Street and the West Windsor border was still closed because of a large sinkhole.",
            },
            {
                "source": "Planet Princeton",
                "published": "2021-09-08",
                "url": "https://planetprinceton.com/2021/09/08/section-of-quaker-road-closed-indefinitely-due-to-storm-damage/",
                "statement": "Quaker Road between Mercer Road and Nassau Park Boulevard remained closed for a sinkhole and other damage. Municipal engineer Deanna Stockton had no reopening estimate.",
            },
            {
                "source": "Town Topics",
                "published": "2021-10-20",
                "url": "https://www.towntopics.com/2021/10/20/no-date-in-sight-for-reopening-of-quaker-road/",
                "statement": "Still closed between Province Line and Mercer roads. The Princeton/Lawrence side of the bridge over the Delaware and Raritan Canal had collapsed. A pipe toward the Stony Brook near Updike Farm needed repair.",
            },
            {
                "source": "Planet Princeton",
                "published": "2021-12-22",
                "url": "https://planetprinceton.com/2021/12/22/quaker-road-reopened-after-four-month-closure-due-to-damage-from-hurricane-ida/",
                "statement": "The stretch between Mercer Road and Province Line Road reopened after being closed since the beginning of September.",
            },
        ],
        "comparison_clause": (
            "The reports describe a multi-month closure and canal-embankment damage. "
            "Bridge-tagged pieces on this name have no deck depth, so the scenario does not call them flooded or dry."
        ),
    },
    {
        "place_id": "mercer_road",
        "title": "Mercer Road",
        "names": ["Mercer Road"],
        "verification": "documented",
        "claims": [
            {
                "source": "Planet Princeton",
                "published": "2021-09-02",
                "url": "https://planetprinceton.com/2021/09/02/thursday-morning-storm-update-routes-in-and-out-of-princeton-closed-as-flooding-continues/",
                "statement": "Mercer Road was still closed in the evening update.",
            },
            {
                "source": "Princeton Patch",
                "published": "2021-09-02",
                "url": "https://patch.com/new-jersey/princeton/evacuations-state-emergency-ida-slams-mercer-county",
                "statement": "Listed Mercer Road among roads currently closed.",
            },
            {
                "source": "Planet Princeton",
                "published": "2021-09-03",
                "url": "https://planetprinceton.com/2021/09/03/friday-morning-storm-update-most-roads-open-again-but-some-remain-closed-due-to-severe-storm-damage/",
                "statement": "Mercer Road opened Friday afternoon.",
            },
        ],
        "comparison_clause": (
            "The reported closure was for 2 September and was described as open again on 3 September. "
            "Mercer Street is a different name and is not counted here."
        ),
    },
    {
        "place_id": "stockton_206",
        "title": "Stockton Street / Route 206",
        "names": ["Stockton Street"],
        "verification": "documented",
        "claims": [
            {
                "source": "Planet Princeton",
                "published": "2021-09-02",
                "url": "https://planetprinceton.com/2021/09/02/thursday-morning-storm-update-routes-in-and-out-of-princeton-closed-as-flooding-continues/",
                "statement": "Stockton Street (Route 206) was still closed. Route 206 was open north of Route 27/Nassau Street.",
            },
            {
                "source": "Princeton Patch",
                "published": "2021-09-02",
                "url": "https://patch.com/new-jersey/princeton/evacuations-state-emergency-ida-slams-mercer-county",
                "statement": "Listed Stockton Street (Rt. 206) among roads currently closed.",
            },
            {
                "source": "Planet Princeton",
                "published": "2021-09-03",
                "url": "https://planetprinceton.com/2021/09/03/friday-morning-storm-update-most-roads-open-again-but-some-remain-closed-due-to-severe-storm-damage/",
                "statement": "Route 206 at the Stony Brook Bridge was reported open again. The same article shows storm damage on Route 206 in Princeton, including a wall that fell into the roadway.",
            },
        ],
        "comparison_clause": (
            "The 2 September closure and the 3 September reopening at the Stony Brook Bridge are news reports, not a depth measurement. "
            "Centerlines that only partly exceed 0.30 m stay routable under the fraction rule."
        ),
    },
    {
        "place_id": "south_harrison",
        "title": "South Harrison Street",
        "names": ["South Harrison Street"],
        "verification": "documented",
        "claims": [
            {
                "source": "Princeton Patch",
                "published": "2021-09-02",
                "url": "https://patch.com/new-jersey/princeton/evacuations-state-emergency-ida-slams-mercer-county",
                "statement": "Listed South Harrison Street among roads currently closed.",
            },
            {
                "source": "Planet Princeton",
                "published": "2021-09-02",
                "url": "https://planetprinceton.com/2021/09/02/thursday-morning-storm-update-routes-in-and-out-of-princeton-closed-as-flooding-continues/",
                "statement": "Harrison Street opened just before 5 p.m. The sentence does not say South Harrison.",
            },
            {
                "source": "Planet Princeton",
                "published": "2021-09-03",
                "url": "https://planetprinceton.com/2021/09/03/friday-morning-storm-update-most-roads-open-again-but-some-remain-closed-due-to-severe-storm-damage/",
                "statement": "Harrison Street is open. The sentence does not say South Harrison.",
            },
        ],
        "comparison_clause": (
            "Patch names South Harrison Street. Planet Princeton names Harrison Street without the South prefix. "
            "Those may be the same closure or different segments. North Harrison Street is not counted as South Harrison."
        ),
    },
    {
        "place_id": "stony_brook_crossings",
        "title": "Stony Brook crossings",
        "names": [],
        "verification": "partial",
        "claims": [
            {
                "source": "Planet Princeton",
                "published": "2021-09-03",
                "url": "https://planetprinceton.com/2021/09/03/friday-morning-storm-update-most-roads-open-again-but-some-remain-closed-due-to-severe-storm-damage/",
                "statement": "Route 206 at the Stony Brook Bridge was reported open again. That names one crossing. It is not a list of every Stony Brook crossing.",
            },
            {
                "source": "Planet Princeton",
                "published": "2021-09-02",
                "url": "https://planetprinceton.com/2021/09/02/thursday-morning-storm-update-routes-in-and-out-of-princeton-closed-as-flooding-continues/",
                "statement": "Rosedale Road opened again at about 4 p.m. The sentence does not name Stony Brook.",
            },
            {
                "source": "Carolyn Jones, hosted by Eastern Surplus",
                "published": "2023-10-10",
                "url": "https://www.easternsurplus.net/pdf/Princeton%20HWRV%20Article.pdf",
                "statement": "A later account of the night of 1 September 2021: the Stony Brook, which crosses Rosedale Road, rose and breached the bridge during a rescue. This is not a contemporaneous closure log.",
            },
            {
                "source": "Town Topics",
                "published": "2021-10-20",
                "url": "https://www.towntopics.com/2021/10/20/no-date-in-sight-for-reopening-of-quaker-road/",
                "statement": "A pipe from a ditch to the Stony Brook near Updike Farm on Quaker Road needed repair. That is damage beside the road, not a named crossing closure.",
            },
        ],
        "related": [
            {"label": "Stockton Street, including Route 206 at the Stony Brook Bridge", "names": ["Stockton Street"]},
            {"label": "Rosedale Road", "names": ["Rosedale Road"]},
        ],
        "unverified_note": (
            "Other Stony Brook crossings were not verified in the sources checked. "
            "Hopewell's Upper Stony Brook, south of Van Dyke, is outside Princeton and is not used. "
            "Stony Brook Lane is a street name in the road network, not this crossing."
        ),
        "comparison_clause": "Only the crossings named above are compared. The rest stay unverified.",
    },
]


def compare_places(places: list[dict[str, Any]], roads: list[dict[str, Any]]) -> dict[str, Any]:
    """Attach scenario counts to each place. Does not score agreement."""
    summarized = []
    for place in places:
        scenario = _count_names(roads, place.get("names") or [])
        related = []
        for item in place.get("related") or []:
            related.append({"label": item["label"], "scenario": _count_names(roads, item["names"])})
        text = _qualitative(place, scenario)
        if related:
            bits = []
            for item in related:
                low = item["scenario"]["by_stage"]["1.00"]["n_assumed_closed"]
                high = item["scenario"]["by_stage"]["2.00"]["n_assumed_closed"]
                bits.append(
                    f"{item['label']}: {item['scenario']['n_centerlines']} centerlines, "
                    f"assumed closed {low} at +1.0 m and {high} at +2.0 m."
                )
            text = text + " " + " ".join(bits)
        summarized.append(
            {
                "place_id": place["place_id"],
                "title": place["title"],
                "verification": place["verification"],
                "claims": place["claims"],
                "scenario": scenario,
                "related": related,
                "unverified_note": place.get("unverified_note"),
                "qualitative": text,
            }
        )
    return {
        "product": "ida_record_comparison",
        "hurricane_ida_depth": False,
        "validated": False,
        "method": "qualitative_only",
        "event": "Remnants of Hurricane Ida, 1–2 September 2021, as described by the cited reports",
        "note": (
            "Sources are news reports, not a flooded-segment inventory. "
            "Unverified places stay unverified. The scenario is not scored, and it is not validated."
        ),
        "places": summarized,
    }


def load_road_properties(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [feature["properties"] for feature in payload["features"]]


def write_comparison(roads_path: Path, output_path: Path) -> dict[str, Any]:
    result = compare_places(PLACES, load_road_properties(roads_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".partial")
    temporary.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output_path)
    return result


def _count_names(roads: list[dict[str, Any]], names: list[str]) -> dict[str, Any]:
    wanted = set(names)
    chosen = [road for road in roads if road.get("name") in wanted]
    return {
        "names": names,
        "n_centerlines": len(chosen),
        "by_stage": {
            "1.00": _stage_counts(chosen, "1_00"),
            "2.00": _stage_counts(chosen, "2_00"),
        },
    }


def _stage_counts(roads: list[dict[str, Any]], slug: str) -> dict[str, Any]:
    status_key = f"routing_status_stage_{slug}"
    wet_key = f"length_m_at_or_above_0_30_stage_{slug}"
    counts: dict[str, int] = {}
    wet = 0.0
    for road in roads:
        status = str(road.get(status_key) or "missing")
        counts[status] = counts.get(status, 0) + 1
        value = road.get(wet_key)
        if value is not None:
            wet += float(value)
    return {
        "status_counts": counts,
        "n_assumed_closed": counts.get("assumed_closed", 0),
        "n_bridge_deck_unmatched": counts.get("bridge_deck_unmatched", 0),
        "n_partial_above_0_30_not_closed": counts.get("partial_above_0_30_not_closed", 0),
        "wet_piece_length_m": round(wet, 1),
    }


def _qualitative(place: dict[str, Any], scenario: dict[str, Any]) -> str:
    if place["verification"] == "unverified":
        return (
            "Unverified. No closure or flooding record for this place was confirmed in the sources checked. "
            "The scenario is not treated as confirmation."
        )
    low = scenario["by_stage"]["1.00"]
    high = scenario["by_stage"]["2.00"]
    if not scenario["names"]:
        lead = "This entry is not one road name."
    else:
        lead = (
            f"{scenario['n_centerlines']} centerlines are named exactly {', '.join(scenario['names'])}. "
            f"Assumed closed at +1.0 m: {low['n_assumed_closed']}. "
            f"At +2.0 m: {high['n_assumed_closed']}. "
            f"Unmatched bridge decks: {low['n_bridge_deck_unmatched']}. "
            f"Piece length at or above 0.30 m: {low['wet_piece_length_m']} m at +1.0 m and "
            f"{high['wet_piece_length_m']} m at +2.0 m."
        )
    clause = place.get("comparison_clause", "")
    return f"{lead} {clause} This is not a validation."
