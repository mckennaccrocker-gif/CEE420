"""The September 2021 news layer is not a scenario depth."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dashboard.observed_reports import NEWS_STYLE
from dashboard.observed_reports import build_observed_reports
from dashboard.observed_reports import refuse_report_as_depth
from dashboard.roads import build_road_collection

EXACT_NAMES = {
    "Quaker Road": 10,
    "Mercer Road": 14,
    "Stockton Street": 11,
    "South Harrison Street": 4,
    "Rosedale Road": 12,
}

UNTOUCHED = (
    "data/processed/princeton_accessibility.geojson",
    "data/processed/accessibility_stats.json",
    "data/processed/flood_exposure_stats.json",
    "data/processed/princeton_centerline_exposure.geojson",
)


def _layer(project_root: Path) -> dict:
    roads = build_road_collection(project_root / "data" / "processed" / "princeton_accessibility.geojson")
    return build_observed_reports(roads)


def test_refuses_a_depth_on_the_report_layer() -> None:
    bare = {
        "hurricane_ida_depth": False,
        "is_model_depth": False,
        "scenario_depth_assigned": False,
        "scenario_depth_m": None,
        "style": NEWS_STYLE,
    }
    refuse_report_as_depth(bare)
    with pytest.raises(ValueError, match="depth"):
        refuse_report_as_depth({**bare, "scenario_depth_m": 0.3})
    with pytest.raises(ValueError, match="Ida depth"):
        refuse_report_as_depth({**bare, "hurricane_ida_depth": True})
    with pytest.raises(ValueError, match="model depth"):
        refuse_report_as_depth({**bare, "is_model_depth": True})
    with pytest.raises(ValueError, match="scenario color"):
        refuse_report_as_depth({**bare, "color": "#c0392b"})


def test_saved_layer_is_not_a_depth_and_does_not_rewrite_depths(project_root: Path) -> None:
    before = {path: (project_root / path).read_bytes() for path in UNTOUCHED}
    roads = build_road_collection(project_root / "data" / "processed" / "princeton_accessibility.geojson")
    depths_before = [
        (feature["properties"].get("depth_max_m_1_00"), feature["properties"].get("depth_max_m_2_00"))
        for feature in roads["features"]
    ]
    layer = build_observed_reports(roads)
    depths_after = [
        (feature["properties"].get("depth_max_m_1_00"), feature["properties"].get("depth_max_m_2_00"))
        for feature in roads["features"]
    ]
    assert depths_after == depths_before
    assert layer["default_visible"] is False
    assert layer["is_model_depth"] is False
    assert layer["scenario_depth_assigned"] is False
    assert layer["hurricane_ida_depth"] is False
    assert layer["event_time"] is None
    counts: dict[str, int] = {}
    for feature in layer["features"]:
        props = feature["properties"]
        refuse_report_as_depth(props)
        assert props["style"] == NEWS_STYLE
        assert props["scenario_depth_m"] is None
        assert "depth_max_m_1_00" not in props
        assert "status_1_00" not in props
        counts[props["name"]] = counts.get(props["name"], 0) + 1
    assert counts == EXACT_NAMES
    for path, content in before.items():
        assert (project_root / path).read_bytes() == content


def test_click_text_follows_the_documented_scenario(project_root: Path) -> None:
    by_place = {}
    for feature in _layer(project_root)["features"]:
        by_place.setdefault(feature["properties"]["place_id"], feature["properties"])
    quaker = by_place["quaker_road"]
    mercer = by_place["mercer_road"]
    stockton = by_place["stockton_206"]
    harrison = by_place["south_harrison"]
    rosedale = by_place["rosedale_road"]
    assert quaker["scenario_did_not_close"] is True
    assert quaker["scenario_note"].startswith("The scenario did not close this road.")
    assert "2 September 2021" in quaker["news_date"]
    assert mercer["scenario_did_not_close"] is False
    assert "did not close this road at +1.0 m" in mercer["scenario_note"]
    assert "2 of 14" in mercer["scenario_note"]
    assert mercer["scenario_note"] != "The scenario did not close this road."
    assert "Mercer Street" in mercer["scenario_note"]
    assert stockton["scenario_note"].startswith("The scenario did not close this road.")
    assert "north of Route 27/Nassau Street" in stockton["news_note"]
    assert harrison["scenario_note"].startswith("The scenario did not close this road.")
    assert "without the word South" in harrison["news_note"]
    assert rosedale["scenario_note"].startswith("The scenario did not close this road.")
    assert "not a closure log" in rosedale["news_note"]
    assert "2 September 2021" in rosedale["news_date"]


def test_reports_toggle_is_not_on_the_page(project_root: Path) -> None:
    html = (project_root / "web" / "index.html").read_text(encoding="utf-8")
    assert 'id="reports-toggle"' not in html
    assert "September 2021 news reports" not in html
