"""Dashboard payload, ENSO parsing, and the Ida record comparison."""

from __future__ import annotations

import json
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread

import pytest

from dashboard.enso import assemble
from dashboard.enso import parse_discussion
from dashboard.enso import parse_oni
from dashboard.enso import parse_weekly
from dashboard.enso import refresh
from dashboard.ida_check import compare_places
from dashboard.roads import build_road_collection
from dashboard.summary import build_summary

WEEKLY = """
                Nino1+2      Nino3        Nino34        Nino4
 Week          SST SSTA     SST SSTA     SST SSTA     SST SSTA
 02SEP1981     20.6-0.1     24.8-0.1     26.5-0.2     28.3-0.3
 28OCT2026     26.7 5.4     29.5 4.4     30.2 3.4     30.1 1.4
"""

ONI = """
 SEAS  YR   TOTAL   ANOM
  JAS 2026  29.12   2.16
"""

DISCUSSION = (
    "DIAGNOSTIC DISCUSSION issued by CLIMATE PREDICTION CENTER 8 October 2026 "
    "ENSO Alert System Status: El Niño Advisory Synopsis: El Niño continues to strengthen."
)


def test_glued_negative_anomaly_and_latest_week() -> None:
    row = parse_weekly(WEEKLY)
    assert row["week_centered"] == "2026-10-28"
    assert row["nino34_sst_c"] == 30.2
    assert row["nino34_anomaly_c"] == 3.4


def test_oni_row_has_no_phase() -> None:
    row = parse_oni(ONI)
    assert row["season"] == "JAS"
    assert row["year"] == 2026
    assert row["anomaly_c"] == 2.16
    assert row["phase_stated_in_file"] is False


def test_weekly_anomaly_does_not_set_the_phase() -> None:
    assert parse_discussion("Niño-3.4 anomaly is +3.4 C and no alert line is present.") is None
    record = assemble(WEEKLY, ONI, "no status here", fetched_at_utc="2026-11-02T00:00:00Z")
    assert record["official_phase"] is None
    assert record["weekly"]["nino34_anomaly_c"] == 3.4
    assert record["enso_scales_depths"] is False
    stated = assemble(WEEKLY, ONI, DISCUSSION, fetched_at_utc="2026-11-02T00:00:00Z")
    assert stated["official_phase"]["status"] == "El Niño Advisory"
    assert stated["official_phase"]["classified_from_weekly_anomaly"] is False
    assert stated["official_phase"]["issued"] == "8 October 2026"


def test_failed_fetch_keeps_the_saved_observation(tmp_path: Path) -> None:
    cache = tmp_path / "enso_latest.json"
    cache.write_text(
        json.dumps({"fetched_at_utc": "2026-01-15T00:00:00Z", "ok": True, "weekly": {"nino34_anomaly_c": 0.2}}),
        encoding="utf-8",
    )

    def boom(_url: str) -> str:
        raise OSError("NOAA unreachable")

    saved = refresh(cache, fetch=boom)
    assert saved["using_saved_observation"] is True
    assert saved["fetched_at_utc"] == "2026-01-15T00:00:00Z"
    assert saved["weekly"]["nino34_anomaly_c"] == 0.2
    assert saved["hurricane_ida_depth"] is False


def test_summary_keeps_the_two_stages_separate(project_root: Path) -> None:
    stats = json.loads((project_root / "data" / "processed" / "accessibility_stats.json").read_text())
    summary = build_summary(stats)
    assert summary["hurricane_ida_depth"] is False
    assert summary["interpolated"] is False
    assert summary["enso_scales_depths"] is False
    assert summary["event_time"] is None
    by_id = {stage["id"]: stage for stage in summary["stages"]}
    assert by_id["1.00"]["n_assumed_closed"] == 33
    assert by_id["1.00"]["n_weak_components"] == 13
    assert by_id["1.00"]["hospital_disconnected"] is False
    assert by_id["2.00"]["n_assumed_closed"] == 90
    assert by_id["2.00"]["n_weak_components"] == 42
    assert by_id["2.00"]["hospital_disconnected"] is True
    assert summary["hospital"]["disconnects_only_at_2_00"] is True
    assert by_id["1.00"]["aadt_nearest_edge_assumed_closed"] == 0
    assert by_id["2.00"]["aadt_records"] == 39
    with pytest.raises(ValueError):
        build_summary({"hurricane_ida_depth": True})


def test_roads_are_not_marked_as_ida(project_root: Path) -> None:
    collection = build_road_collection(project_root / "data" / "processed" / "princeton_accessibility.geojson")
    assert len(collection["features"]) == 1298
    assert all(feature["properties"]["hurricane_ida_depth"] is False for feature in collection["features"])


def test_unverified_place_is_not_scored() -> None:
    places = [
        {
            "place_id": "missing",
            "title": "Nowhere Road",
            "names": ["Nowhere Road"],
            "verification": "unverified",
            "claims": [],
        }
    ]
    roads = [
        {
            "name": "Quaker Road",
            "routing_status_stage_1_00": "assumed_closed",
            "routing_status_stage_2_00": "assumed_closed",
            "length_m_at_or_above_0_30_stage_1_00": 10,
            "length_m_at_or_above_0_30_stage_2_00": 10,
        }
    ]
    result = compare_places(places, roads)
    assert result["validated"] is False
    assert result["hurricane_ida_depth"] is False
    assert "precision" not in result
    assert "recall" not in result
    assert result["places"][0]["verification"] == "unverified"
    assert result["places"][0]["qualitative"].startswith("Unverified.")


def test_saved_ida_comparison_is_not_a_validation(project_root: Path) -> None:
    path = project_root / "data" / "processed" / "ida_record_comparison.json"
    if not path.is_file():
        pytest.skip("validate_ida.py has not been run")
    result = json.loads(path.read_text())
    assert result["validated"] is False
    assert result["hurricane_ida_depth"] is False
    assert "precision" not in result
    assert "recall" not in result
    titles = [place["title"] for place in result["places"]]
    assert "Quaker Road" in titles
    assert "Stony Brook crossings" in titles


def test_server_serves_the_scenario_summary(settings: dict, project_root: Path) -> None:
    from test_placeholders import _load

    dashboard = _load("dashboard.py")
    context = dashboard.build_context(settings)
    handler = dashboard.make_handler(context)
    from http.server import ThreadingHTTPServer

    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
        connection.request("GET", "/api/summary")
        response = connection.getresponse()
        body = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert body["hurricane_ida_depth"] is False
        assert body["interpolated"] is False
        assert [stage["id"] for stage in body["stages"]] == [
            "0.00", "0.25", "0.50", "0.75", "1.00", "1.25", "1.50", "1.75", "2.00",
        ]
        wet = {stage["id"]: stage["wet_piece_length_m"] for stage in body["stages"]}
        assert wet["0.50"] == pytest.approx(4775.748, abs=0.05)
        assert wet["1.00"] == pytest.approx(8306.970, abs=0.05)
        assert wet["1.50"] == pytest.approx(13202.237, abs=0.05)
        assert wet["2.00"] == pytest.approx(19159.784, abs=0.05)
        connection.request("GET", "/")
        page = connection.getresponse()
        html = page.read().decode("utf-8")
        assert page.status == 200
        assert "Road accessibility" in html
        assert 'id="stage-slider"' in html
        assert 'step="0.25"' in html
        assert "chosen rise above the channel, not a forecast." in html
        assert 'id="scenario-summary"' in html
        assert 'id="stage-caption"' in html
        assert 'id="fema-toggle"' in html
        assert "Regulatory flood zones" in html
        assert 'id="reports-toggle"' in html
        assert 'id="reports-toggle" type="checkbox" checked' not in html
        assert 'id="enso-panel"' in html
        assert html.count('type="range"') == 1
        script = (project_root / "web" / "app.js").read_text(encoding="utf-8")
        assert "nearestStageId" in script
        assert "function showScenarioSummary" in script
        assert "function wetCaption" in script
        assert "not a threshold on the weekly anomaly" in script
        assert "does not set Princeton road depths" in script
        assert "last saved observation" in script
        connection.request("GET", "/api/fema")
        fema_response = connection.getresponse()
        fema = json.loads(fema_response.read().decode("utf-8"))
        assert fema_response.status == 200
        assert fema["hurricane_ida_depth"] is False
        assert fema["zone_depth_assigned"] is False
        assert fema["effective_date"] == "2016-07-20"
        assert fema["regulatory_water_surface"]["value"] == 65.5
        assert fema["regulatory_water_surface"]["not_a_deck_elevation"] is True
        connection.request("GET", "/api/roads.geojson")
        roads = json.loads(connection.getresponse().read().decode("utf-8"))
        assert all(feature["properties"]["fema_zone_depth_m"] is None for feature in roads["features"])
        connection.request("GET", "/api/observed-reports.geojson")
        reports_response = connection.getresponse()
        reports = json.loads(reports_response.read().decode("utf-8"))
        assert reports_response.status == 200
        assert reports["default_visible"] is False
        assert reports["is_model_depth"] is False
        assert reports["scenario_depth_assigned"] is False
        assert all(feature["properties"]["scenario_depth_m"] is None for feature in reports["features"])
        connection.request("GET", "/api/name-check")
        check_response = connection.getresponse()
        check = json.loads(check_response.read().decode("utf-8"))
        assert check_response.status == 200
        assert check["validated"] is False
        assert check["depths_recomputed"] is False
        assert "precision" not in check
        assert "recall" not in check
        assert [row["road"] for row in check["rows"]][1] == "Mercer Road"
        assert check["rows"][1]["plus_2_00"] == "captured"
        assert check["rows"][1]["captured_of"] == "2 of 14"
        connection.request("GET", "/api/enso")
        enso_response = connection.getresponse()
        enso = json.loads(enso_response.read().decode("utf-8"))
        assert enso_response.status == 200
        assert enso["enso_scales_depths"] is False
        assert enso["weekly"]["nino34_anomaly_c"] == 3.4
        assert enso["weekly"]["week_centered"] == "2026-10-28"
        assert enso["oni"]["anomaly_c"] == 2.16
        assert enso["oni"]["season"] == "JAS"
        assert enso["oni"]["year"] == 2026
        assert enso["official_phase"]["status"] == "El Niño Advisory"
        assert enso["official_phase"]["issued"] == "8 October 2026"
        assert enso["official_phase"]["classified_from_weekly_anomaly"] is False
    finally:
        server.shutdown()
        server.server_close()
