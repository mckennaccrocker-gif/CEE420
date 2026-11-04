"""The September 2021 side panel is a name check, not a score."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dashboard.name_check import build_name_check
from dashboard.name_check import refuse_scored_name_check

UNTOUCHED = (
    "data/processed/princeton_accessibility.geojson",
    "data/processed/accessibility_stats.json",
    "data/processed/flood_exposure_stats.json",
    "data/processed/princeton_centerline_exposure.geojson",
)


def test_five_rows_match_the_stage_note(project_root: Path) -> None:
    before = {path: (project_root / path).read_bytes() for path in UNTOUCHED}
    features = json.loads((project_root / UNTOUCHED[0]).read_text(encoding="utf-8"))["features"]
    payload = build_name_check(features)
    assert payload["interpolated"] is False
    assert payload["enso_scales_depths"] is False
    assert payload["rises_m"] == [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0]
    assert payload["validated"] is False
    assert payload["hurricane_ida_depth"] is False
    assert payload["event_time"] is None
    assert payload["depths_recomputed"] is False
    assert payload["label"] == "A name check, not a validation. It was not scored."
    roads = [row["road"] for row in payload["rows"]]
    assert roads == [
        "Quaker Road",
        "Mercer Road",
        "Stockton Street / Route 206",
        "South Harrison Street",
        "Rosedale Road",
    ]
    by_road = {row["road"]: row for row in payload["rows"]}
    mercer = by_road["Mercer Road"]
    assert mercer["plus_1_00"] == "missed"
    assert mercer["plus_2_00"] == "captured"
    assert mercer["captured_of"] == "2 of 14"
    assert mercer["n_centerlines"] == 14
    for road in ("Quaker Road", "Stockton Street / Route 206", "South Harrison Street", "Rosedale Road"):
        assert by_road[road]["plus_1_00"] == "missed"
        assert by_road[road]["plus_2_00"] == "missed"
        assert "captured_of" not in by_road[road]
    assert by_road["Quaker Road"]["n_centerlines"] == 10
    assert by_road["Stockton Street / Route 206"]["n_centerlines"] == 11
    assert by_road["South Harrison Street"]["n_centerlines"] == 4
    assert by_road["Rosedale Road"]["n_centerlines"] == 12
    assert "not a closure log" in by_road["Rosedale Road"]["detail"]
    for road in roads:
        half = next(step for step in by_road[road]["steps"] if step["id"] == "0.50")
        assert half["result"] == "missed"
        assert "captured_of" not in half
    mercer_one_half = next(step for step in mercer["steps"] if step["id"] == "1.50")
    assert mercer_one_half["result"] == "captured"
    assert mercer_one_half["captured_of"] == "1 of 14"
    for road in ("Quaker Road", "Stockton Street / Route 206", "South Harrison Street", "Rosedale Road"):
        one_half = next(step for step in by_road[road]["steps"] if step["id"] == "1.50")
        assert one_half["result"] == "missed"
    for path, content in before.items():
        assert (project_root / path).read_bytes() == content


def test_refuses_precision_or_recall(project_root: Path) -> None:
    features = json.loads((project_root / UNTOUCHED[0]).read_text(encoding="utf-8"))["features"]
    payload = build_name_check(features)
    refuse_scored_name_check(payload)
    with pytest.raises(ValueError, match="precision or recall"):
        refuse_scored_name_check({**payload, "precision": 0.2})
    with pytest.raises(ValueError, match="precision or recall"):
        refuse_scored_name_check({**payload, "recall": 0.2})
    with pytest.raises(ValueError, match="validation"):
        refuse_scored_name_check({**payload, "validated": True})


def test_name_check_panel_is_in_the_page(project_root: Path) -> None:
    html = (project_root / "web" / "index.html").read_text(encoding="utf-8")
    assert 'id="name-check"' in html
    assert "Name check" in html
    assert "not a validation" in html
    script = (project_root / "web" / "app.js").read_text(encoding="utf-8")
    assert "renderNameCheck" in script
    assert "showNameCheck(stage)" in script
    assert "/api/name-check" in script
    assert "function focusReportedRoad" in script
    assert "feature.properties.title === row.road" in script
    assert "setReportsVisible(true)" in script
    assert "row.detail" in script
    assert 'color: "#111111"' in script
    assert "not a validation" in script
