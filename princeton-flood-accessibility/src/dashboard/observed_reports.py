"""September 2021 news reports as their own map layer.

The sentences are the ones already written in the stage-4 dashboard note and
the municipal briefing. This module does not read a new article, does not
score agreement, and does not copy a scenario depth onto a line.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

# Scenario and deck colors already used on the road layer. A news mark must
# not reuse them, or the dash would read as a depth.
SCENARIO_DEPTH_COLORS = frozenset(
    {
        "#1f7a4d",
        "#c4920a",
        "#c0392b",
        "#e07a2f",
        "#6d4ea8",
        "#0e7c86",
        "#8a8a8a",
        "#b7b1a6",
    }
)

NEWS_STYLE = "black_dash_not_a_depth"

_DEPTH_KEYS = (
    "depth_m",
    "scenario_depth_m",
    "depth_max_m_1_00",
    "depth_max_m_2_00",
    "wet_m_1_00",
    "wet_m_2_00",
    "zone_depth_m",
    "fema_zone_depth_m",
    "deck_elevation_m",
)

# Exact OpenStreetMap names. Mercer Street, North Harrison Street, Harrison
# Street, and Stony Brook Lane are different names and are not included.
REPORTS: tuple[dict[str, Any], ...] = (
    {
        "place_id": "quaker_road",
        "title": "Quaker Road",
        "exact_names": ("Quaker Road",),
        "n_centerlines": 10,
        "scenario_did_not_close": True,
        "news_date": "2 September 2021; 3 September 2021; 8 September 2021; 20 October 2021; 22 December 2021",
        "news_note": (
            "Planet Princeton and Princeton Patch on 2 September 2021 listed Quaker Road closed. "
            "On 3 September the stretch from Mercer Street to the West Windsor border was still closed for a sinkhole. "
            "On 8 September there was no reopening estimate. "
            "Town Topics on 20 October described the canal-bridge collapse. "
            "Planet Princeton on 22 December reported the reopening."
        ),
        "scenario_note": (
            "The scenario did not close this road. "
            "Ten centerlines named Quaker Road, none assumed closed at +1.0 m or +2.0 m, "
            "and 0 m of pieces at or above 0.30 m. "
            "Two bridge decks are unmatched. The scenario does not call those decks flooded or dry."
        ),
    },
    {
        "place_id": "mercer_road",
        "title": "Mercer Road",
        "exact_names": ("Mercer Road",),
        "n_centerlines": 14,
        "scenario_did_not_close": False,
        "news_date": "2 September 2021; 3 September 2021",
        "news_note": (
            "Planet Princeton on 2 September 2021 still listed Mercer Road closed that evening. "
            "Princeton Patch listed it the same day. "
            "Planet Princeton on 3 September said it opened Friday afternoon."
        ),
        "scenario_note": (
            "The scenario did not close this road at +1.0 m. "
            "At +2.0 m it assumed 2 of 14 Mercer Road centerlines closed. "
            "Mercer Street is a different name and is not on this layer."
        ),
    },
    {
        "place_id": "stockton_206",
        "title": "Stockton Street / Route 206",
        "exact_names": ("Stockton Street",),
        "n_centerlines": 11,
        "scenario_did_not_close": True,
        "news_date": "2 September 2021; 3 September 2021",
        "news_note": (
            "Planet Princeton on 2 September 2021 said Stockton Street (Route 206) was still closed, "
            "and that Route 206 was open north of Route 27/Nassau Street. "
            "Princeton Patch listed Stockton Street (Rt. 206) the same day. "
            "On 3 September, Route 206 at the Stony Brook Bridge was reported open again. "
            "This layer marks centerlines named Stockton Street. "
            "It does not mark the stretch reported open north of Nassau Street."
        ),
        "scenario_note": (
            "The scenario did not close this road. "
            "Eleven centerlines named Stockton Street, none assumed closed at either assumption. "
            "Some pieces are deep, 88.8 m at +1.0 m and 176.0 m at +2.0 m, "
            "and the fraction rule still leaves the centerlines routable."
        ),
    },
    {
        "place_id": "south_harrison",
        "title": "South Harrison Street",
        "exact_names": ("South Harrison Street",),
        "n_centerlines": 4,
        "scenario_did_not_close": True,
        "news_date": "2 September 2021; 3 September 2021",
        "news_note": (
            "Princeton Patch on 2 September 2021 listed South Harrison Street closed. "
            "Planet Princeton the same day said Harrison Street opened just before 5 p.m., "
            "and on 3 September said Harrison Street was open, without the word South. "
            "Those may be the same closure or different segments. "
            "North Harrison Street is not on this layer."
        ),
        "scenario_note": (
            "The scenario did not close this road. "
            "Four centerlines named exactly South Harrison Street, none assumed closed, "
            "and 0 m of deep pieces at either assumption."
        ),
    },
    {
        "place_id": "rosedale_road",
        "title": "Rosedale Road",
        "exact_names": ("Rosedale Road",),
        "n_centerlines": 12,
        "scenario_did_not_close": True,
        "news_date": "2 September 2021",
        "news_note": (
            "Planet Princeton on 2 September 2021 said Rosedale Road opened again at about 4 p.m. "
            "and did not name the brook. "
            "A 10 October 2023 recollection that the Stony Brook breached the Rosedale Road bridge "
            "is not a closure log. This mark is not a documented closure."
        ),
        "scenario_note": (
            "The scenario did not close this road. "
            "Twelve centerlines, none assumed closed, and 0 m of deep pieces. "
            "One bridge deck is unmatched. This dash is not that deck elevation."
        ),
    },
)


def refuse_report_as_depth(properties: dict[str, Any]) -> None:
    """Raise if a news-report feature is being used as a depth."""
    if properties.get("hurricane_ida_depth") is True:
        raise ValueError("Refusing to treat a September 2021 news report as an Ida depth.")
    if properties.get("is_model_depth") is True:
        raise ValueError("Refusing to treat a September 2021 news report as a model depth.")
    if properties.get("scenario_depth_assigned") is True:
        raise ValueError("Refusing to assign a scenario depth to a news report.")
    for key in _DEPTH_KEYS:
        value = properties.get(key)
        if value is not None:
            raise ValueError(f"Refusing a depth on a news report: {key}={value!r}.")
    color = properties.get("color")
    if isinstance(color, str) and color.lower() in SCENARIO_DEPTH_COLORS:
        raise ValueError(f"Refusing a scenario color on a news report: {color}.")
    style = properties.get("style")
    if style not in (None, NEWS_STYLE):
        raise ValueError(f"Refusing an unmarked style on a news report: {style!r}.")


def build_observed_reports(roads: dict[str, Any]) -> dict[str, Any]:
    """Copy matching centerline geometry. Do not copy depth fields."""
    features = []
    for report in REPORTS:
        allowed = set(report["exact_names"])
        matched = [
            feature
            for feature in roads.get("features") or []
            if feature.get("properties", {}).get("name") in allowed
        ]
        if len(matched) != report["n_centerlines"]:
            raise ValueError(
                f"{report['title']} matched {len(matched)} centerlines, "
                f"not the documented {report['n_centerlines']}."
            )
        for feature in matched:
            properties = {
                "centerline_id": feature["properties"].get("centerline_id"),
                "name": feature["properties"].get("name"),
                "place_id": report["place_id"],
                "title": report["title"],
                "news_date": report["news_date"],
                "news_note": report["news_note"],
                "scenario_note": report["scenario_note"],
                "scenario_did_not_close": report["scenario_did_not_close"],
                "layer": "september_2021_news_report",
                "style": NEWS_STYLE,
                "is_model_depth": False,
                "scenario_depth_assigned": False,
                "scenario_depth_m": None,
                "hurricane_ida_depth": False,
                "event_time": None,
            }
            refuse_report_as_depth(properties)
            features.append(
                {
                    "type": "Feature",
                    "geometry": deepcopy(feature["geometry"]),
                    "properties": properties,
                }
            )
    return {
        "type": "FeatureCollection",
        "layer": "september_2021_news_report",
        "default_visible": False,
        "is_model_depth": False,
        "scenario_depth_assigned": False,
        "hurricane_ida_depth": False,
        "event_time": None,
        "style": NEWS_STYLE,
        "note": (
            "Black dashes mark roads named in the September 2021 news check. "
            "They are not a scenario depth and they do not replace the road color."
        ),
        "features": features,
    }
